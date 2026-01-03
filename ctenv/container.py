"""Container specification, entrypoint generation, and execution for ctenv.

This module handles all container-related functionality including:
- ContainerSpec dataclass for fully resolved container configuration
- Container configuration parsing and validation
- Entrypoint script generation for container setup
- Docker container execution and management
"""

import hashlib
import os
import platform
import pwd
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

from .version import __version__
from .config import (
    NOTSET,
    NotSetType,
    ContainerRuntime,
    EnvVar,
    VolumeSpec,
    RuntimeContext,
    ContainerConfig,
    Verbosity,
    _substitute_variables_in_container_config,
)

# Default PS1 prompt for containers
DEFAULT_PS1 = "[ctenv] $ "

# Pinned gosu version for security and reproducibility
GOSU_VERSION = "1.17"

# SHA256 checksums for gosu 1.17 binaries
# Source: https://github.com/tianon/gosu/releases/download/1.17/SHA256SUMS
GOSU_CHECKSUMS = {
    "gosu-amd64": "bbc4136d03ab138b1ad66fa4fc051bafc6cc7ffae632b069a53657279a450de3",
    "gosu-arm64": "c3805a85d17f4454c23d7059bcb97e1ec1af272b90126e79ed002342de08389b",
}


# =============================================================================
# Platform and Binary Management
# =============================================================================


def validate_platform(platform: str) -> bool:
    """Validate that the platform is supported."""
    supported_platforms = ["linux/amd64", "linux/arm64"]
    return platform in supported_platforms


def get_platform_specific_gosu_name(target_platform: Optional[str] = None) -> str:
    """Get platform-specific gosu binary name.

    Args:
        target_platform: Docker platform format (e.g., "linux/amd64", "linux/arm64")
                        If None, detects host platform.

    Note: gosu only provides Linux binaries since containers run Linux
    regardless of the host OS.
    """
    if target_platform:
        # Extract architecture from Docker platform format
        if target_platform == "linux/amd64":
            arch = "amd64"
        elif target_platform == "linux/arm64":
            arch = "arm64"
        else:
            # For unsupported platforms, default to amd64
            arch = "amd64"
    else:
        # Detect host platform
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            arch = "amd64"
        elif machine in ("aarch64", "arm64"):
            arch = "arm64"
        else:
            arch = "amd64"  # Default fallback

    # Always use Linux binaries since containers run Linux
    return f"gosu-{arch}"


def is_installed_package():
    """Check if running as installed package vs single file."""
    try:
        import importlib.util

        spec = importlib.util.find_spec("ctenv.binaries")
        return spec is not None
    except ImportError:
        return False


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def _find_next_subid_range(count: int = 65536) -> tuple[int, int]:
    """Find the next available subordinate UID/GID range.

    Parses /etc/subuid and /etc/subgid to find allocated ranges,
    then returns a free range starting after the highest used ID.

    Args:
        count: Number of IDs to allocate (default 65536)

    Returns:
        Tuple of (start, end) for the suggested range
    """
    max_end = 100000  # Default start if no entries exist

    for subid_file in ["/etc/subuid", "/etc/subgid"]:
        try:
            with open(subid_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split(":")
                    if len(parts) >= 3:
                        try:
                            start = int(parts[1])
                            length = int(parts[2])
                            end = start + length
                            if end > max_end:
                                max_end = end
                        except ValueError:
                            continue
        except (FileNotFoundError, PermissionError):
            pass

    return max_end, max_end + count - 1


def check_podman_rootless_ready() -> tuple[bool, str | None]:
    """Check if Podman rootless mode is properly configured.

    Podman rootless requires subordinate UID/GID ranges to be configured
    in /etc/subuid and /etc/subgid for the current user.

    Returns:
        Tuple of (is_ready, error_message). If ready, error_message is None.
    """

    try:
        username = pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return False, "Could not determine current username"

    subuid_ok = False
    subgid_ok = False

    # Check /etc/subuid
    try:
        with open("/etc/subuid", "r") as f:
            for line in f:
                if line.startswith(f"{username}:"):
                    subuid_ok = True
                    break
    except FileNotFoundError:
        pass
    except PermissionError:
        # If we can't read it, assume it might be configured
        subuid_ok = True

    # Check /etc/subgid
    try:
        with open("/etc/subgid", "r") as f:
            for line in f:
                if line.startswith(f"{username}:"):
                    subgid_ok = True
                    break
    except FileNotFoundError:
        pass
    except PermissionError:
        # If we can't read it, assume it might be configured
        subgid_ok = True

    if subuid_ok and subgid_ok:
        return True, None

    missing = []
    if not subuid_ok:
        missing.append("/etc/subuid")
    if not subgid_ok:
        missing.append("/etc/subgid")

    # Find a free range to suggest
    range_start, range_end = _find_next_subid_range()

    error_msg = (
        f"Podman rootless requires subordinate UID/GID configuration.\n"
        f"Missing entries for user '{username}' in: {', '.join(missing)}\n"
        f"Run: \n"
        f"  sudo usermod --add-subuids {range_start}-{range_end} --add-subgids {range_start}-{range_end} {username}\n"
        f"  podman system migrate"
    )
    return False, error_msg


# =============================================================================
# Path and Volume Utilities
# =============================================================================


def expand_tilde_in_path(path: str, runtime: RuntimeContext) -> str:
    """Expand ~ to user home directory in a path string."""
    if path.startswith("~/"):
        return runtime.user_home + path[1:]
    elif path == "~":
        return runtime.user_home
    return path


def _expand_tilde_in_volumespec(vol_spec: VolumeSpec, runtime: RuntimeContext) -> VolumeSpec:
    """Expand tilde (~/) in VolumeSpec paths using the provided user_home value."""
    # Create a copy to avoid mutating the original
    result = VolumeSpec(vol_spec.host_path, vol_spec.container_path, vol_spec.options[:])

    # Expand tildes in host path
    if result.host_path.startswith("~/"):
        result.host_path = runtime.user_home + result.host_path[1:]
    elif result.host_path == "~":
        result.host_path = runtime.user_home

    # Expand tildes in container path (usually not needed, but for completeness)
    if result.container_path.startswith("~/"):
        result.container_path = runtime.user_home + result.container_path[1:]
    elif result.container_path == "~":
        result.container_path = runtime.user_home

    return result


# =============================================================================
# Configuration Parsing Functions
# =============================================================================


def _parse_project_target(project_target_str: str) -> tuple[str, list[str]]:
    """Parse project_target string which may include options.

    Examples:
        "/repo" -> ("/repo", [])
        "/repo:ro" -> ("/repo", ["ro"])
        "/repo:ro,z" -> ("/repo", ["ro", "z"])

    Returns:
        Tuple of (target_path, options_list)
    """
    if ":" not in project_target_str:
        return (project_target_str, [])

    parts = project_target_str.split(":")
    target_path = parts[0]
    options = parts[1].split(",") if len(parts) > 1 and parts[1] else []
    return (target_path, options)


def _parse_volume(vol_str: str, project_dir: Path, project_target: str) -> VolumeSpec:
    """Parse volume specification with project-aware path defaulting.

    If the volume's host path is a subpath of project_dir and no container
    path is specified, the container path is computed relative to
    project_target.
    """
    if vol_str is NOTSET or vol_str is None:
        raise ValueError(f"Invalid volume: {vol_str}")

    spec = VolumeSpec.parse(vol_str)

    # Volume validation: must have explicit host path
    if not spec.host_path:
        raise ValueError(f"Volume host path cannot be empty: {vol_str}")

    # Smart defaulting for container path
    if not spec.container_path:
        # Only apply subpath remapping for absolute paths
        # Paths with ~ or relative paths can't be reliably compared to project_dir
        if os.path.isabs(spec.host_path):
            try:
                rel_path = os.path.relpath(spec.host_path, project_dir)
                if not rel_path.startswith(".."):
                    # It's a subpath - mount relative to project target
                    if rel_path == ".":
                        spec.container_path = project_target
                    else:
                        spec.container_path = os.path.join(project_target, rel_path)
                else:
                    # Outside project - mount at same path as host
                    spec.container_path = spec.host_path
            except ValueError:
                # Different drives on Windows, can't compute relative path
                spec.container_path = spec.host_path
        else:
            # Relative or tilde path - use as-is (will be expanded later)
            spec.container_path = spec.host_path

    return spec


def _parse_subpath(
    subpath_str: str,
    project_dir: Path,
    project_target: str,
) -> VolumeSpec:
    """Parse subpath specification and return VolumeSpec.

    Subpaths are always relative to project_dir. Supports options like :ro.

    Args:
        subpath_str: Subpath (file or dir), optionally with options (e.g., "src", "src:ro")
        project_dir: Project directory on host
        project_target: Target path in container (e.g., "/repo")
    """
    # Parse options from the string (e.g., "src:ro" -> "src", ["ro"])
    spec = VolumeSpec.parse(subpath_str)

    # Subpath is always relative to project_dir
    if os.path.isabs(spec.host_path):
        host_path = spec.host_path
    else:
        host_path = str((project_dir / spec.host_path).resolve())

    # Container path is always relative to project_target
    try:
        rel_path = os.path.relpath(host_path, project_dir)
        if not rel_path.startswith(".."):
            if rel_path == ".":
                container_path = project_target
            else:
                container_path = os.path.join(project_target, rel_path)
        else:
            raise ValueError(
                f"Subpath '{subpath_str}' resolves outside project directory '{project_dir}'"
            )
    except ValueError as e:
        if "different drive" in str(e).lower():
            raise ValueError(
                f"Subpath '{subpath_str}' is on a different drive than project directory '{project_dir}'"
            )
        raise

    # Build options: always include 'z' for SELinux, plus any user options
    options = ["z"]
    for opt in spec.options:
        if opt not in options:
            options.append(opt)

    return VolumeSpec(
        host_path=host_path,
        container_path=container_path,
        options=options,
    )


def _resolve_workdir_auto(primary_subpath: VolumeSpec, runtime: RuntimeContext) -> str:
    """Auto-resolve working directory, preserving relative position within primary subpath."""
    # Calculate relative position within primary subpath and translate
    try:
        rel_path = os.path.relpath(str(runtime.cwd), primary_subpath.host_path)
        if rel_path == "." or rel_path.startswith(".."):
            # At subpath root or outside - use container path
            return primary_subpath.container_path
        else:
            # Inside subpath - preserve relative position
            return os.path.join(primary_subpath.container_path, rel_path).replace("\\", "/")
    except (ValueError, OSError):
        # Fallback if path calculation fails
        return primary_subpath.container_path


def _resolve_workdir(
    workdir_config: Union[str, NotSetType, None],
    primary_subpath: Optional[VolumeSpec],
    runtime: RuntimeContext,
) -> str:
    """Resolve working directory based on configuration value."""
    if workdir_config == "auto":
        if primary_subpath is None:
            # No project mount, default to /
            return "/"
        return _resolve_workdir_auto(primary_subpath, runtime)
    elif isinstance(workdir_config, str) and workdir_config != "auto":
        return workdir_config
    else:
        raise ValueError(f"Invalid workdir value: {workdir_config}")


def _find_bundled_gosu_path() -> str:
    """Find the bundled gosu binary for the current architecture."""
    # Auto-detect gosu binary based on architecture
    arch = platform.machine().lower()
    if arch in ("x86_64", "amd64"):
        binary_name = "gosu-amd64"
    elif arch in ("aarch64", "arm64"):
        binary_name = "gosu-arm64"
    else:
        raise ValueError(f"Unsupported architecture: {arch}")

    # Look in package directory
    package_dir = Path(__file__).parent
    binary_path = package_dir / "binaries" / binary_name

    if binary_path.exists():
        return str(binary_path)

    raise FileNotFoundError(f"gosu binary not found at {binary_path}")


def _resolve_gosu_path_auto() -> str:
    """Auto-resolve gosu path by finding bundled binary."""
    return _find_bundled_gosu_path()


def _parse_gosu_spec(
    gosu_path_config: Union[str, NotSetType, None], runtime: RuntimeContext
) -> VolumeSpec:
    """Parse gosu configuration and return VolumeSpec for gosu binary mount."""
    # Resolve gosu_path based on configuration value
    if gosu_path_config == "auto":
        gosu_path = _resolve_gosu_path_auto()
    elif isinstance(gosu_path_config, str) and gosu_path_config != "auto":
        # User provided a path - expand tilde and use it
        gosu_path = expand_tilde_in_path(gosu_path_config, runtime)
    else:
        raise ValueError(f"Invalid gosu_path value: {gosu_path_config}")

    # Hard-coded mount point to avoid collisions
    gosu_mount = "/ctenv/gosu"

    return VolumeSpec(
        host_path=gosu_path,
        container_path=gosu_mount,
        options=["z", "ro"],  # SELinux and read-only
    )


def _resolve_tty(tty_config: Union[str, bool, NotSetType, None], runtime: RuntimeContext) -> bool:
    """Resolve TTY setting based on configuration value."""
    if tty_config == "auto":
        return runtime.tty
    elif isinstance(tty_config, bool):
        return tty_config
    else:
        raise ValueError(f"Invalid TTY value: {tty_config}")


def _parse_env(env_config: Union[List[str], NotSetType]) -> List[EnvVar]:
    """Parse environment variable configuration into EnvVar objects.

    Args:
        env_config: Environment variable configuration - either a list of strings
                   in format ["NAME=value", "NAME"] or NOTSET

    Returns:
        List of EnvVar objects (empty list if NOTSET)
    """
    if env_config is NOTSET:
        return []

    env_vars = []
    for env_str in env_config:
        if "=" in env_str:
            name, value = env_str.split("=", 1)
            env_vars.append(EnvVar(name=name, value=value))
        else:
            env_vars.append(EnvVar(name=env_str, value=None))  # Pass from host
    return env_vars


# =============================================================================
# Container Specification
# =============================================================================


@dataclass(kw_only=True)
class ContainerSpec:
    """Resolved container specification ready for execution.

    This represents a fully resolved configuration with all paths expanded,
    variables substituted, and defaults applied. All required fields are
    non-optional to ensure the container can be run.
    """

    # User identity (always resolved from runtime)
    user_name: str
    user_id: int
    user_home: str
    group_name: str
    group_id: int

    # Paths (always resolved)
    workdir: str  # Always resolved (defaults to first subpath root)
    gosu: VolumeSpec  # Gosu binary mount

    # Container settings (always have defaults)
    image: str  # From defaults or config
    command: str  # From defaults or config
    container_name: str  # Always generated if not specified
    tty: bool  # From defaults (stdin.isatty()) or config
    sudo: bool  # From defaults (False) or config
    runtime: ContainerRuntime = ContainerRuntime.DOCKER_ROOTFUL

    # Lists (use empty list as default instead of None)
    subpaths: List[VolumeSpec] = field(
        default_factory=list
    )  # Subpaths to mount (defaults to project root)
    env: List[EnvVar] = field(default_factory=list)
    volumes: List[VolumeSpec] = field(default_factory=list)
    chown_paths: List[str] = field(default_factory=list)  # Paths to chown inside container
    post_start_commands: List[str] = field(default_factory=list)
    run_args: List[str] = field(default_factory=list)

    # Truly optional fields (None has meaning)
    network: Optional[str] = None  # None = Docker default networking
    platform: Optional[str] = None  # None = Docker default platform
    ulimits: Optional[Dict[str, Any]] = None  # None = no ulimits


def build_entrypoint_script(spec: ContainerSpec, verbosity: Verbosity = Verbosity.NORMAL) -> str:
    """Generate bash script for container entrypoint.

    Args:
        spec: ContainerSpec instance with all container configuration
        verbosity: Verbosity level for script output

    Returns:
        Complete bash script as string
    """
    # Map verbosity to script's verbose/quiet flags
    verbose = verbosity >= Verbosity.VERBOSE
    quiet = verbosity < Verbosity.NORMAL

    # Extract PS1 from environment variables
    ps1_var = next((env for env in spec.env if env.name == "PS1"), None)
    ps1_value = ps1_var.value if ps1_var else DEFAULT_PS1

    # Build chown paths value using a rare delimiter
    chown_paths_value = ""
    if spec.chown_paths:
        # Use a rare delimiter sequence unlikely to appear in paths
        delimiter = "|||CTENV_DELIMITER|||"
        chown_paths_value = shlex.quote(delimiter.join(spec.chown_paths))
    else:
        chown_paths_value = "''"

    # Build post-start commands as newline-separated string
    post_start_commands_value = ""
    if spec.post_start_commands:
        # Join commands with actual newlines and quote the result
        commands_text = "\n".join(spec.post_start_commands)
        post_start_commands_value = shlex.quote(commands_text)
    else:
        post_start_commands_value = "''"

    script = f"""#!/bin/sh
# Use POSIX shell for compatibility with BusyBox/Alpine Linux
set -e

# Logging setup
VERBOSE={1 if verbose else 0}
QUIET={1 if quiet else 0}

# User and group configuration
USER_NAME="{spec.user_name}"
USER_ID="{spec.user_id}"
GROUP_NAME="{spec.group_name}"
GROUP_ID="{spec.group_id}"
USER_HOME="{spec.user_home}"
ADD_SUDO={1 if spec.sudo else 0}

# Container configuration
GOSU_MOUNT="{spec.gosu.container_path}"
COMMAND={shlex.quote(spec.command)}
TTY_MODE={1 if spec.tty else 0}
PS1_VALUE={shlex.quote(ps1_value)}

# Variables for chown paths and post-start commands (null-separated)
CHOWN_PATHS={chown_paths_value}
POST_START_COMMANDS={post_start_commands_value}


# Debug messages - only shown with --verbose
log_debug() {{
    if [ "$VERBOSE" = "1" ]; then
        echo "[ctenv] $*" >&2
    fi
}}

# Info messages - shown unless --quiet
log_info() {{
    if [ "$QUIET" != "1" ]; then
        echo "[ctenv] $*" >&2
    fi
}}

# Function to fix ownership of chown-enabled volumes
fix_chown_volumes() {{
    log_debug "Checking volumes for ownership fixes"
    if [ -z "$CHOWN_PATHS" ]; then
        log_debug "No chown-enabled volumes configured"
        return
    fi

    # Use POSIX-compatible approach to split on delimiter
    # Save original IFS and use delimiter approach for reliability
    OLD_IFS="$IFS"
    IFS='|||CTENV_DELIMITER|||'
    set -- $CHOWN_PATHS
    IFS="$OLD_IFS"

    # Process each path
    for path in "$@"; do
        [ -n "$path" ] || continue  # Skip empty paths
        log_debug "Checking chown volume: $path"
        if [ -d "$path" ]; then
            log_debug "Fixing ownership of volume: $path"
            chown -R "$USER_ID:$GROUP_ID" "$path"
        else
            log_debug "Chown volume does not exist: $path"
        fi
    done
}}

# Function to execute post-start commands
run_post_start_commands() {{
    log_debug "Executing post-start commands"
    if [ -z "$POST_START_COMMANDS" ]; then
        log_debug "No post-start commands to execute"
        return
    fi

    # Use printf and read loop for reliable line-by-line processing
    printf '%s\\n' "$POST_START_COMMANDS" | while IFS= read -r cmd || [ -n "$cmd" ]; do
        [ -n "$cmd" ] || continue  # Skip empty commands
        log_debug "Executing post-start command: $cmd"
        eval "$cmd"
    done
}}

# Detect if we're using BusyBox utilities
IS_BUSYBOX=0
if command -v adduser >/dev/null 2>&1 && adduser --help 2>&1 | grep -q "BusyBox"; then
    IS_BUSYBOX=1
    log_debug "Detected BusyBox utilities"
fi

log_debug "Starting ctenv container setup"
log_debug "User: $USER_NAME (UID: $USER_ID)"
log_debug "Group: $GROUP_NAME (GID: $GROUP_ID)"
log_debug "Home: $USER_HOME"

# Create group if needed
log_debug "Checking if group $GROUP_ID exists"
if getent group "$GROUP_ID" >/dev/null 2>&1; then
    GROUP_NAME=$(getent group "$GROUP_ID" | cut -d: -f1)
    log_debug "Using existing group: $GROUP_NAME"
else
    log_debug "Creating group: $GROUP_NAME (GID: $GROUP_ID)"
    if [ "$IS_BUSYBOX" = "1" ]; then
        addgroup -g "$GROUP_ID" "$GROUP_NAME"
    else
        groupadd -g "$GROUP_ID" "$GROUP_NAME"
    fi
fi

# Create user if needed
log_debug "Checking if user $USER_NAME exists"
if ! getent passwd "$USER_NAME" >/dev/null 2>&1; then
    log_debug "Creating user: $USER_NAME (UID: $USER_ID)"
    if [ "$IS_BUSYBOX" = "1" ]; then
        adduser -D -H -h "$USER_HOME" -s /bin/sh -u "$USER_ID" -G "$GROUP_NAME" "$USER_NAME"
    else
        useradd_err=$(useradd --no-create-home --home-dir "$USER_HOME" \\
            --shell /bin/sh -u "$USER_ID" -g "$GROUP_ID" \\
            -o -c "" "$USER_NAME" 2>&1) || true
        [ "$VERBOSE" = "1" ] && [ -n "$useradd_err" ] && echo "$useradd_err" >&2
    fi
else
    log_debug "User $USER_NAME already exists"
fi

# Setup home directory
export HOME="$USER_HOME"
log_debug "Setting up home directory: $HOME"
if [ ! -d "$HOME" ]; then
    log_debug "Creating home directory: $HOME"
    mkdir -p "$HOME"
    chown "$USER_ID:$GROUP_ID" "$HOME"
else
    log_debug "Home directory already exists"
fi

# Set ownership of home directory (non-recursive)
log_debug "Setting ownership of home directory"
chown "$USER_NAME" "$HOME"

# Fix ownership of chown-enabled volumes
fix_chown_volumes

# Execute post-start commands
run_post_start_commands

# Setup sudo if requested
if [ "$ADD_SUDO" = "1" ]; then
    log_debug "Setting up sudo access for $USER_NAME"

    # Check if sudo is already installed
    if ! command -v sudo >/dev/null 2>&1; then
        log_debug "sudo not found, installing..."
        # Install sudo based on available package manager
        log_info "Installing sudo..."
        if command -v apt-get >/dev/null 2>&1; then
            apt-get update -qq && apt-get install -y -qq sudo
        elif command -v yum >/dev/null 2>&1; then
            yum install -y -q sudo
        elif command -v apk >/dev/null 2>&1; then
            apk add --no-cache sudo
        else
            echo "ERROR: sudo not installed and no supported package manager found (apt-get, yum, or apk)" >&2
            exit 1
        fi
    else
        log_debug "sudo is already installed"
    fi

    # Add user to sudoers
    log_info "Adding $USER_NAME to /etc/sudoers"
    echo "$USER_NAME ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
else
    log_debug "Sudo not requested"
fi

# Set environment
log_debug "Setting up shell environment"
# PS1 environment variables are filtered out since this entrypoint script runs as
# non-interactive /bin/sh i the shebang, so we must explicitly set PS1 here for interactive sessions.
if [ "$TTY_MODE" = "1" ]; then
    export PS1="$PS1_VALUE"
fi

# Execute command as user
log_debug "Running command as $USER_NAME: $COMMAND"
# Uses shell to execute the command to handle shell quoting issues in commands.
# Need to specify interactive shell (-i) when TTY is available for PS1 to be passed.
if [ "$TTY_MODE" = "1" ]; then
    INTERACTIVE="-i"
else
    INTERACTIVE=""
fi
exec "$GOSU_MOUNT" "$USER_NAME" /bin/sh $INTERACTIVE -c "$COMMAND"
"""
    return script


def parse_container_config(config: ContainerConfig, runtime: RuntimeContext) -> ContainerSpec:
    """Create ContainerSpec from complete ContainerConfig and runtime context.

    This function expects a COMPLETE configuration with all required fields set.
    It does not apply defaults - that should be done by the caller (e.g., CtenvConfig).
    If any required fields are missing or invalid, this function will raise an exception
    rather than trying to find fallback values.

    Args:
        config: Complete merged ContainerConfig (no NOTSET values for required fields)
        runtime: Runtime context (user info, cwd, tty)

    Returns:
        ContainerSpec with all fields resolved and ready for execution

    Raises:
        ValueError: If required configuration fields are missing or invalid
    """
    # Apply variable substitution
    substituted_config = _substitute_variables_in_container_config(config, runtime, os.environ)

    # Resolve project target early (needed for workspace/volume parsing)
    # project_target can include options (e.g., "/repo:ro")
    # If not set, default to same as runtime.project_dir (host path)
    if substituted_config.project_target is not NOTSET:
        project_target, _ = _parse_project_target(substituted_config.project_target)
    else:
        project_target = str(runtime.project_dir)

    # Validate required fields are not NOTSET
    required_fields = {
        "image": substituted_config.image,
        "command": substituted_config.command,
        "workdir": substituted_config.workdir,
        "gosu_path": substituted_config.gosu_path,
        "container_name": substituted_config.container_name,
        "tty": substituted_config.tty,
    }

    missing_fields = [name for name, value in required_fields.items() if value is NOTSET]
    if missing_fields:
        raise ValueError(f"Required configuration fields not set: {', '.join(missing_fields)}")

    # Validate platform if specified
    if substituted_config.platform is not NOTSET and not validate_platform(
        substituted_config.platform
    ):
        raise ValueError(
            f"Unsupported platform '{substituted_config.platform}'. Supported platforms: linux/amd64, linux/arm64"
        )

    # Convert runtime string to enum (needed early for volume processing)
    container_runtime = ContainerRuntime.DOCKER_ROOTFUL  # default
    if substituted_config.runtime is not NOTSET:
        container_runtime = ContainerRuntime(substituted_config.runtime)

    # Process volumes (can't inline due to complexity and chown_paths extraction)
    volume_specs = []
    chown_paths = []
    volumes = substituted_config.volumes if substituted_config.volumes is not NOTSET else []
    for vol_str in volumes:
        vol_spec = _parse_volume(vol_str, runtime.project_dir, project_target)
        vol_spec = _expand_tilde_in_volumespec(vol_spec, runtime)

        # Check for chown option and handle it
        if "chown" in vol_spec.options:
            # Remove chown from options
            vol_spec.options = [opt for opt in vol_spec.options if opt != "chown"]
            if container_runtime == ContainerRuntime.PODMAN_ROOTLESS:
                # Podman: use native :U option for ownership mapping
                vol_spec.options.append("U")
            else:
                # Docker: handle in entrypoint script
                chown_paths.append(vol_spec.container_path)

        # Add 'z' option if not already present (for SELinux)
        if "z" not in vol_spec.options:
            vol_spec.options.append("z")

        volume_specs.append(vol_spec)

    # Build ContainerSpec systematically
    RUNTIME_FIELDS = ["user_name", "user_id", "user_home", "group_name", "group_id"]
    CONFIG_PASSTHROUGH_FIELDS = [
        "image",
        "command",
        "container_name",
        "sudo",
        "post_start_commands",
        "run_args",
        "network",
        "platform",
        "ulimits",
    ]

    # Check if project mounting is disabled
    no_project_mount = (
        substituted_config.no_project_mount is not NOTSET
        and substituted_config.no_project_mount is True
    )

    # Parse subpaths
    # - If no_project_mount=True: only mount explicitly specified subpaths (no default ".")
    # - If no_project_mount=False: always include "." plus any explicit subpaths
    subpaths_config = substituted_config.subpaths
    if subpaths_config is NOTSET or not subpaths_config:
        # No explicit subpaths specified
        if no_project_mount:
            subpaths_config = []  # Mount nothing
        else:
            subpaths_config = ["."]  # Default to project root
    else:
        # Explicit subpaths specified
        subpaths_config = list(subpaths_config)
        if not no_project_mount and "." not in subpaths_config:
            # Always include project root unless --no-project-mount is used
            subpaths_config.insert(0, ".")

    subpath_specs = []
    for subpath_str in subpaths_config:
        subpath_spec = _parse_subpath(subpath_str, runtime.project_dir, project_target)
        subpath_spec = _expand_tilde_in_volumespec(subpath_spec, runtime)
        subpath_specs.append(subpath_spec)

    # Use first subpath for workdir resolution (None if no subpaths)
    primary_subpath = subpath_specs[0] if subpath_specs else None

    spec_dict = {
        # Runtime fields (copied directly from RuntimeContext)
        **{field: getattr(runtime, field) for field in RUNTIME_FIELDS},
        # Config fields (copied from ContainerConfig, excluding NOTSET)
        **{
            field: getattr(substituted_config, field)
            for field in CONFIG_PASSTHROUGH_FIELDS
            if getattr(substituted_config, field) is not NOTSET
        },
        # Custom/resolved fields:
        # 1. Parsed from config strings → structured objects
        "subpaths": subpath_specs,  # config.subpaths (List[str]) → List[VolumeSpec]
        "gosu": _parse_gosu_spec(substituted_config.gosu_path, runtime),  # Inlined
        "volumes": volume_specs,  # config.volumes (List[str]) → List[VolumeSpec]
        "runtime": container_runtime,  # config.runtime (str) → ContainerRuntime enum
        # 2. Resolved/computed values
        "workdir": _resolve_workdir(substituted_config.workdir, primary_subpath, runtime),
        "tty": _resolve_tty(substituted_config.tty, runtime),  # Inlined
        # 3. Extracted/derived values
        "chown_paths": chown_paths,  # Extracted from volumes with "chown" option
        "env": _parse_env(substituted_config.env),
    }

    return ContainerSpec(**spec_dict)


# =============================================================================
# Container Execution
# =============================================================================


class ContainerRunner:
    """Manages Docker container operations."""

    @staticmethod
    def _safe_unlink(path: str) -> None:
        """Safely remove a file, ignoring errors."""
        try:
            os.unlink(path)
        except OSError:
            pass

    @staticmethod
    def build_run_args(
        spec: "ContainerSpec", entrypoint_script_path: str, verbosity: Verbosity = Verbosity.NORMAL
    ) -> List[str]:
        """Build Docker run arguments with provided script path.

        Args:
            spec: ContainerSpec instance
            entrypoint_script_path: Path to temporary entrypoint script
            verbosity: Verbosity level

        Returns:
            List of Docker run command arguments
        """
        if verbosity >= Verbosity.VERBOSE:
            print(f"Building {spec.runtime.command} run arguments", file=sys.stderr)

        # --user=root forces root to override any USER directive in Dockerfile.
        args = [
            spec.runtime.command,
            "run",
            "--rm",
            "--init",
            "--user=root",
        ]

        if spec.runtime == ContainerRuntime.PODMAN_ROOTLESS:
            # For podman-rootless, --userns=keep-id maps host UID to container UID
            args.append("--userns=keep-id")

        # Add platform flag only if specified
        if spec.platform:
            args.append(f"--platform={spec.platform}")

        args.append(f"--name={spec.container_name}")

        # Add ctenv labels for container identification and management
        args.extend(
            [
                "--label=se.osd.ctenv.managed=true",
                f"--label=se.osd.ctenv.version={__version__}",
            ]
        )

        # Process volume options from VolumeSpec objects (chown already handled in parse_container_config)

        # Volume mounts: use subpaths if specified, otherwise project root
        volume_args = [
            f"--volume={spec.gosu.to_string()}",
            f"--volume={entrypoint_script_path}:/ctenv/entrypoint.sh:z,ro",
            f"--workdir={spec.workdir}",
        ]

        # Mount subpaths (empty if no_project_mount is set)
        for subpath_spec in spec.subpaths:
            volume_args.insert(0, f"--volume={subpath_spec.to_string()}")

        args.extend(volume_args)

        if verbosity >= Verbosity.VERBOSE:
            print("Volume mounts:", file=sys.stderr)
            print("  Subpaths:", file=sys.stderr)
            for subpath_spec in spec.subpaths:
                print(f"    {subpath_spec.to_string()}", file=sys.stderr)
            print(f"  Working directory: {spec.workdir}", file=sys.stderr)
            print(f"  Gosu binary: {spec.gosu.to_string()}", file=sys.stderr)
            print(
                f"  Entrypoint script: {entrypoint_script_path} -> /ctenv/entrypoint.sh",
                file=sys.stderr,
            )

        # Additional volume mounts
        if spec.volumes:
            if verbosity >= Verbosity.VERBOSE:
                print("Additional volume mounts:", file=sys.stderr)
            for vol_spec in spec.volumes:
                volume_arg = f"--volume={vol_spec.to_string()}"
                args.append(volume_arg)
                if verbosity >= Verbosity.VERBOSE:
                    print(f"  {vol_spec.to_string()}", file=sys.stderr)

        if spec.chown_paths and verbosity >= Verbosity.VERBOSE:
            print("Volumes with chown enabled:", file=sys.stderr)
            for path in spec.chown_paths:
                print(f"  {path}", file=sys.stderr)

        # Environment variables
        if spec.env:
            if verbosity >= Verbosity.VERBOSE:
                print("Environment variables:", file=sys.stderr)
            for env_var in spec.env:
                args.append(env_var.to_docker_arg())
                if verbosity >= Verbosity.VERBOSE:
                    if env_var.value is None:
                        host_value = os.environ.get(env_var.name, "")
                        print(f"  Passing: {env_var.name}={host_value}", file=sys.stderr)
                    else:
                        print(f"  Setting: {env_var.name}={env_var.value}", file=sys.stderr)

        # Resource limits (ulimits)
        if spec.ulimits:
            if verbosity >= Verbosity.VERBOSE:
                print("Resource limits (ulimits):", file=sys.stderr)
            for limit_name, limit_value in spec.ulimits.items():
                args.extend([f"--ulimit={limit_name}={limit_value}"])
                if verbosity >= Verbosity.VERBOSE:
                    print(f"  {limit_name}={limit_value}", file=sys.stderr)

        # Network configuration
        if spec.network:
            args.extend([f"--network={spec.network}"])
            if verbosity >= Verbosity.VERBOSE:
                print(f"Network mode: {spec.network}", file=sys.stderr)
        elif verbosity >= Verbosity.VERBOSE:
            # Default: use Docker's default networking (no --network flag)
            print("Network mode: default (Docker default)", file=sys.stderr)

        # TTY flags if running interactively
        if spec.tty:
            args.extend(["-t", "-i"])
            if verbosity >= Verbosity.VERBOSE:
                print("TTY mode: enabled", file=sys.stderr)
        elif verbosity >= Verbosity.VERBOSE:
            print("TTY mode: disabled", file=sys.stderr)

        # Custom run arguments
        if spec.run_args:
            if verbosity >= Verbosity.VERBOSE:
                print("Custom run arguments:", file=sys.stderr)
            for run_arg in spec.run_args:
                args.append(run_arg)
                if verbosity >= Verbosity.VERBOSE:
                    print(f"  {run_arg}", file=sys.stderr)

        # Set entrypoint to our script
        args.extend(["--entrypoint", "/ctenv/entrypoint.sh"])

        # Container image
        args.append(spec.image)
        if verbosity >= Verbosity.VERBOSE:
            print(f"Container image: {spec.image}", file=sys.stderr)

        return args

    @staticmethod
    def run_container(
        spec: "ContainerSpec", verbosity: Verbosity = Verbosity.NORMAL, dry_run: bool = False
    ):
        """Execute Docker container with the given specification.

        Args:
            spec: ContainerSpec instance
            verbosity: Verbosity level
            dry_run: Show commands without executing

        Returns:
            subprocess.CompletedProcess result
        """
        if verbosity >= Verbosity.VERBOSE:
            print("Starting container execution", file=sys.stderr)

        # Check if container runtime is available
        runtime_path = shutil.which(spec.runtime.command)
        if not runtime_path:
            raise FileNotFoundError(
                f"{spec.runtime.command} not found in PATH. Please install {spec.runtime.command}."
            )
        if verbosity >= Verbosity.VERBOSE:
            print(f"Found {spec.runtime.command} at: {runtime_path}", file=sys.stderr)

        # Check Podman rootless configuration
        if spec.runtime == ContainerRuntime.PODMAN_ROOTLESS:
            ready, error_msg = check_podman_rootless_ready()
            if not ready:
                raise RuntimeError(error_msg)
            if verbosity >= Verbosity.VERBOSE:
                print("Podman rootless configuration verified", file=sys.stderr)

        # Verify gosu binary exists
        if verbosity >= Verbosity.VERBOSE:
            print(f"Checking for gosu binary at: {spec.gosu.host_path}", file=sys.stderr)
        gosu_path = Path(spec.gosu.host_path)
        if not gosu_path.exists():
            raise FileNotFoundError(
                f"gosu binary not found at {spec.gosu.host_path}. Please ensure gosu is available."
            )

        if not gosu_path.is_file():
            raise FileNotFoundError(f"gosu path {spec.gosu.host_path} is not a file.")

        # Verify subpaths exist
        for subpath in spec.subpaths:
            subpath_path = Path(subpath.host_path)
            if verbosity >= Verbosity.VERBOSE:
                print(f"Verifying subpath: {subpath_path}", file=sys.stderr)
            if not subpath_path.exists():
                raise FileNotFoundError(f"Subpath {subpath_path} does not exist.")

        # Generate entrypoint script content (chown paths are already in spec)
        script_content = build_entrypoint_script(spec, verbosity)

        # Handle script file creation
        if dry_run:
            entrypoint_script_path = "/tmp/entrypoint.sh"  # Placeholder for display
            script_cleanup = None
        else:
            script_fd, entrypoint_script_path = tempfile.mkstemp(suffix=".sh", text=True)
            if verbosity >= Verbosity.VERBOSE:
                print(
                    f"Created temporary entrypoint script: {entrypoint_script_path}",
                    file=sys.stderr,
                )
            with os.fdopen(script_fd, "w") as f:
                f.write(script_content)
            os.chmod(entrypoint_script_path, 0o755)
            script_cleanup = lambda: ContainerRunner._safe_unlink(entrypoint_script_path)

        try:
            # Build Docker arguments (same for both modes)
            docker_args = ContainerRunner.build_run_args(spec, entrypoint_script_path, verbosity)
            if verbosity >= Verbosity.VERBOSE:
                print(f"Executing Docker command: {' '.join(docker_args)}", file=sys.stderr)

            # Show what will be executed
            if dry_run:
                print(" ".join(docker_args))

            # Show entrypoint script only at very verbose level (-vv)
            if verbosity >= Verbosity.VERY_VERBOSE:
                print("\n" + "=" * 60, file=sys.stderr)
                print(
                    "Entrypoint script" + (" that would be executed:" if dry_run else ":"),
                    file=sys.stderr,
                )
                print("=" * 60, file=sys.stderr)
                print(script_content, file=sys.stderr)
                print("=" * 60 + "\n", file=sys.stderr)

            # Execute or mock execution
            if dry_run:
                if verbosity >= Verbosity.VERBOSE:
                    print("Dry-run mode: Docker command printed, not executed", file=sys.stderr)
                return subprocess.CompletedProcess(docker_args, 0)
            else:
                result = subprocess.run(docker_args, check=False)
                if result.returncode != 0 and verbosity >= Verbosity.VERBOSE:
                    print(f"Container exited with code: {result.returncode}", file=sys.stderr)
                return result

        except subprocess.CalledProcessError as e:
            if not dry_run:
                print(f"Error: Container execution failed: {e}", file=sys.stderr)
                raise RuntimeError(f"Container execution failed: {e}")
            raise
        finally:
            if script_cleanup:
                script_cleanup()
