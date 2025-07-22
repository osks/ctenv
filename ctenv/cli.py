#!/usr/bin/env -S uv run -q --script
#
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "tomli; python_version < '3.11'",
# ]
# ///

"""
ctenv - Run programs in containers as current user
"""

__version__ = "0.1"

import argparse
import collections.abc
import copy
import getpass
import grp
import logging
import os
import platform
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import shlex
import hashlib

try:
    import tomllib
except ImportError:
    # For python < 3.11
    import tomli as tomllib
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple


def substitute_template_variables(text: str, variables: Dict[str, str]) -> str:
    """Substitute ${var} and ${var|filter} patterns in text."""
    pattern = r"\$\{([^}|]+)(?:\|([^}]+))?\}"

    def replace_match(match):
        var_name, filter_name = match.groups()

        # Get value
        if var_name.startswith("env:"):
            value = os.environ.get(var_name[4:], "")
        else:
            value = variables.get(var_name, "")

        # Apply filter
        if filter_name == "slug":
            value = value.replace(":", "-").replace("/", "-")
        elif filter_name is not None:
            raise ValueError(f"Unknown filter: {filter_name}")

        return value

    return re.sub(pattern, replace_match, text)


def substitute_in_context(
    context_data: Dict[str, Any], variables: Dict[str, str]
) -> Dict[str, Any]:
    """Apply variable substitution to all string values in context."""
    result = {}
    for key, value in context_data.items():
        if isinstance(value, str):
            result[key] = substitute_template_variables(value, variables)
        elif isinstance(value, list):
            result[key] = [
                substitute_template_variables(item, variables)
                if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            result[key] = value
    return result


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


def find_default_gosu_path(start_dir: Optional[Path] = None, target_platform: Optional[str] = None) -> Optional[Path]:
    """Find default gosu binary - should always use bundled binary.

    Args:
        start_dir: Unused (kept for API compatibility)
        target_platform: Target container platform (e.g., "linux/amd64")

    Returns:
        Path to bundled gosu binary, or None if package is corrupted
    """
    # Get platform-specific binary name
    platform_gosu = get_platform_specific_gosu_name(target_platform)
    
    # First, try to find bundled binary
    try:
        # With zip_safe=False, we can use direct paths to package files
        import ctenv
        package_dir = Path(ctenv.__file__).parent
        bundled_gosu = package_dir / 'binaries' / platform_gosu
        
        if bundled_gosu.exists() and bundled_gosu.is_file():
            logging.debug(f"Using bundled gosu: {bundled_gosu}")
            return bundled_gosu
    except (ImportError, AttributeError):
        # Package not found, continue with other methods
        pass

    # No more .ctenv directory traversal - bundled binaries make this unnecessary

    # No fallback to system PATH - bundled binaries should always work
    logging.debug("No gosu binary found")
    return None


def find_gosu_binary(
    start_dir: Optional[Path] = None, explicit_path: Optional[str] = None, target_platform: Optional[str] = None
) -> Optional[Path]:
    """Find gosu binary using fallback strategy.

    Search order:
    1. explicit_path if provided
    2. Default gosu search with platform consideration

    Args:
        start_dir: Starting directory for search
        explicit_path: Explicit path to gosu binary
        target_platform: Target container platform (e.g., "linux/amd64")

    Returns:
        Path to gosu binary if found, None otherwise
    """
    if explicit_path:
        explicit_gosu = Path(explicit_path)
        if explicit_gosu.exists() and explicit_gosu.is_file():
            logging.debug(f"Using explicit gosu path: {explicit_gosu}")
            return explicit_gosu
        else:
            logging.warning(f"Explicit gosu path not found: {explicit_gosu}")
            return None

    return find_default_gosu_path(start_dir, target_platform)


def get_default_config_dict() -> Dict[str, Any]:
    """Get default configuration values as a dict."""
    import os

    user_info = pwd.getpwuid(os.getuid())
    group_info = grp.getgrgid(os.getgid())

    return {
        # User identity (defaults to current user)
        "user_name": user_info.pw_name,
        "user_id": user_info.pw_uid,
        "group_name": group_info.gr_name,
        "group_id": group_info.gr_gid,
        "user_home": user_info.pw_dir,
        # Required paths
        "working_dir": str(Path(os.getcwd())),
        "gosu_path": None,  # Will be resolved later with platform consideration
        # Mount points
        "working_dir_mount": "/repo",
        "gosu_mount": "/gosu",
        # Container settings
        "image": "ubuntu:latest",
        "command": "bash",
        "container_name": None,
        "env": [],
        "volumes": [],
        "post_start_commands": [],
        "ulimits": None,
        "sudo": False,
        "network": None,
        "tty": sys.stdin.isatty(),
    }


def _load_config_file(config_path: Path) -> Dict[str, Any]:
    """Load and parse TOML configuration file."""
    try:
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
        logging.debug(f"Loaded config from {config_path}")
        return config_data
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Invalid TOML in {config_path}: {e}") from e
    except (OSError, IOError) as e:
        raise ValueError(f"Error reading {config_path}: {e}") from e


@dataclass
class ConfigFile:
    """Represents a single configuration file with contexts and defaults."""

    contexts: Dict[str, Dict[str, Any]]
    defaults: Optional[Dict[str, Any]]
    path: Optional[Path]  # None for built-in defaults

    @classmethod
    def builtin(cls) -> "ConfigFile":
        """Create a ConfigFile with built-in defaults."""
        return cls(
            contexts={},
            defaults=None,
            path=None,
        )

    @classmethod
    def from_file(cls, config_path: Path) -> "ConfigFile":
        """Load configuration from a specific file."""
        if not config_path.exists():
            raise ValueError(f"Config file not found: {config_path}")

        config_data = _load_config_file(config_path)
        raw_contexts = config_data.get("contexts", {})
        raw_defaults = config_data.get("defaults")  # None if not present

        logging.debug(f"Loaded config from {config_path}")
        return cls(
            contexts=raw_contexts,
            defaults=raw_defaults,
            path=config_path,
        )


def merge_config(config, overrides):
    result = copy.deepcopy(config)
    for k, v in overrides.items():
        if isinstance(v, collections.abc.Mapping):
            result[k] = merge_config(result.get(k, {}), v)
        elif isinstance(v, list):
            result[k] = result.get(k, []) + v
        else:
            result[k] = copy.deepcopy(v)
    return result


def load_user_config(start_dir: Optional[Path] = None) -> Optional[ConfigFile]:
    """Load user configuration (~/.ctenv/ctenv.toml)."""
    user_config_path = Path.home() / ".ctenv" / "ctenv.toml"

    if not user_config_path.exists() or not user_config_path.is_file():
        return None

    return ConfigFile.from_file(user_config_path)


def load_project_config(start_dir: Optional[Path] = None) -> Optional[ConfigFile]:
    """Load project configuration (searched upward from start_dir)."""
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()
    while True:
        config_path = current / ".ctenv" / "ctenv.toml"
        if config_path.exists() and config_path.is_file():
            return ConfigFile.from_file(config_path)

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    return None


@dataclass
class CtenvConfig:
    """Represents the computed ctenv configuration.

    Contains pre-computed defaults and contexts from all config sources.
    Config sources are processed in priority order during load():
    - Explicit config files (if provided via --config)
    - Project config (./.ctenv/ctenv.toml found via upward search)
    - User config (~/.ctenv/ctenv.toml)
    - System defaults
    """

    defaults: Dict[str, Any]  # Computed defaults (system + first file defaults found)
    contexts: Dict[
        str, Dict[str, Any]
    ]  # All contexts from all files (higher priority wins)

    def find_context(self, context_name: str) -> Optional[Dict[str, Any]]:
        """Find context by name.

        Returns the context dict if found, or None if not found.
        """
        return self.contexts.get(context_name)

    def resolve_container_config(
        self,
        context: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> "ContainerConfig":
        """Resolve a complete ContainerConfig for the given context with CLI overrides.

        Priority order:
        1. Precomputed defaults
        2. Context config (if specified)
        3. CLI overrides (highest priority)

        All merging is done with raw dicts, ContainerConfig is created only at the end.
        """
        if cli_overrides is None:
            cli_overrides = {}

        # Start with precomputed defaults
        result_dict = self.defaults.copy()

        # Layer 2: Context config (if specified)
        if context is not None:
            context_config = self.find_context(context)
            if context_config is None:
                available = sorted(self.contexts.keys())
                raise ValueError(f"Unknown context '{context}'. Available: {available}")

            result_dict = merge_config(result_dict, context_config)
        else:
            logging.debug("No context specified")

        # Layer 3: CLI overrides
        if cli_overrides:
            # Filter out None values from CLI overrides
            filtered_overrides = {
                k: v for k, v in cli_overrides.items() if v is not None
            }

            result_dict = merge_config(result_dict, filtered_overrides)

        # Create ContainerConfig from complete merged dict
        return ContainerConfig.from_dict(result_dict)

    @classmethod
    def load(
        cls,
        explicit_config_files: Optional[List[Path]] = None,
        start_dir: Optional[Path] = None,
    ) -> "CtenvConfig":
        """Load and compute configuration from files in priority order.

        Priority order (highest to lowest):
        1. Explicit config files (in order specified via --config)
        2. Project config (./.ctenv/ctenv.toml)
        3. User config (~/.ctenv/ctenv.toml)
        4. System defaults
        """
        config_files = []

        # Highest priority: explicit config files (in order)
        if explicit_config_files:
            for config_file in explicit_config_files:
                try:
                    loaded_config = ConfigFile.from_file(config_file)
                    config_files.append(loaded_config)
                except Exception as e:
                    raise ValueError(
                        f"Failed to load explicit config file {config_file}: {e}"
                    )

        # Project config (if no explicit configs)
        if not explicit_config_files:
            project_config = load_project_config(start_dir)
            if project_config:
                config_files.append(project_config)

        # User config
        user_config = load_user_config(start_dir)
        if user_config:
            config_files.append(user_config)

        # Compute defaults (system defaults + first file defaults found)
        defaults = get_default_config_dict()
        for config_file in config_files:
            if config_file.defaults:
                defaults = merge_config(defaults, config_file.defaults)
                break  # Stop after first [defaults] section found

        # Compute contexts (merge all contexts, higher priority wins)
        contexts = {}
        # Process in reverse order so higher priority overrides
        for config_file in reversed(config_files):
            contexts.update(config_file.contexts)

        return cls(defaults=defaults, contexts=contexts)


@dataclass
class ContainerConfig:
    """Configuration for ctenv container operations.

    User identity and core paths are always required.
    Other fields are optional and represent explicit configuration.
    When None, they can be filled with defaults during resolution.
    """

    # User identity (always required)
    user_name: str
    user_id: int
    group_name: str
    group_id: int
    user_home: str

    # Core paths (always required)
    working_dir: Path
    gosu_path: Optional[Path] = None

    # Mount points (structural, always set)
    working_dir_mount: str = "/repo"
    gosu_mount: str = "/gosu"

    # Container settings (optional - None means "not specified")
    image: Optional[str] = None
    command: Optional[str] = None
    container_name: Optional[str] = None

    # Options (optional - None/empty means "not specified")
    env: Optional[List[str]] = None
    volumes: Optional[List[str]] = None
    post_start_commands: Optional[List[str]] = None
    ulimits: Optional[Dict[str, Any]] = None
    sudo: Optional[bool] = None
    network: Optional[str] = None
    tty: Optional[bool] = None
    platform: Optional[str] = None

    def get_container_name(self) -> str:
        """Generate container name based on working directory."""
        if self.container_name:
            return self.container_name
        # Replace / with - to make valid container name
        dir_id = str(self.working_dir).replace("/", "-")
        return f"ctenv-{dir_id}"

    def resolve_missing_paths(self) -> "ContainerConfig":
        """Return a new ContainerConfig with missing paths resolved.
        
        Resolves paths that depend on other config values:
        - gosu_path: resolved based on platform
        """
        import dataclasses
        
        # Create a copy to modify
        resolved_data = dataclasses.asdict(self)
        
        # Resolve gosu_path if not set
        if self.gosu_path is None:
            resolved_gosu = find_gosu_binary(target_platform=self.platform)
            if resolved_gosu is None:
                raise FileNotFoundError("No gosu binary found. This suggests a corrupted package installation.")
            resolved_data['gosu_path'] = resolved_gosu
            
        return ContainerConfig.from_dict(resolved_data)

    def resolve_templates(
        self, variables: Optional[Dict[str, str]] = None
    ) -> "ContainerConfig":
        """Return a new ContainerConfig with template variables resolved."""
        from dataclasses import asdict

        if variables is None:
            variables = {
                "USER": getpass.getuser(),
                "image": self.image or "",
            }

        # Convert to dict
        config_dict = asdict(self)

        # Apply templates to appropriate fields
        for key, value in config_dict.items():
            if isinstance(value, str):
                config_dict[key] = substitute_template_variables(value, variables)
            elif isinstance(value, (list, tuple)) and value:
                config_dict[key] = [
                    substitute_template_variables(item, variables)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]

        # Convert back
        return ContainerConfig.from_dict(config_dict)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ContainerConfig":
        """Create ContainerConfig instance from configuration dict.

        No fallback logic - expects a complete dict with all required fields.
        """
        # Get all valid field names from the dataclass
        import dataclasses
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        
        kwargs = {}
        unknown_keys = []

        for key, value in config_dict.items():
            # Check if this is a known field
            if key not in valid_fields:
                unknown_keys.append(key)
                continue
                
            if value is None:
                # Skip None values - let dataclass defaults handle them
                continue

            # Handle path fields
            if key in ("working_dir", "gosu_path") and isinstance(value, str):
                kwargs[key] = Path(value) if value else None
            # Handle list fields
            elif key in ("env", "volumes", "post_start_commands") and isinstance(
                value, (list, tuple)
            ):
                kwargs[key] = list(value)
            # Everything else passes through
            else:
                kwargs[key] = value

        # Warn about unknown keys
        if unknown_keys:
            logging.warning(
                f"Ignoring unknown configuration options: {', '.join(sorted(unknown_keys))}"
            )

        return cls(**kwargs)


def build_entrypoint_script(
    config: ContainerConfig, chown_paths: List[str] = None, verbose: bool = False
) -> str:
    """Generate bash script for container entrypoint."""
    chown_paths = chown_paths or []

    # Build chown commands for volumes marked with :chown
    chown_commands = ""
    if chown_paths:
        chown_commands = """
# Fix ownership of chown-enabled volumes
log "Checking volumes for ownership fixes"
"""
        for path in chown_paths:
            # Safely quote the path to prevent injection
            quoted_path = shlex.quote(path)
            # For logging, escape quotes in the original path
            escaped_path = path.replace('"', '\\"')
            chown_commands += f'log "Checking chown volume: {escaped_path}"\n'
            chown_commands += f'if [ -d {quoted_path} ]; then\n'
            chown_commands += f'    log "Fixing ownership of volume: {escaped_path}"\n'
            chown_commands += f'    chown -R "$USER_ID:$GROUP_ID" {quoted_path}\n'
            chown_commands += "else\n"
            chown_commands += f'    log "Chown volume does not exist: {escaped_path}"\n'
            chown_commands += "fi\n"
    else:
        chown_commands = """
# No volumes require ownership fixes
log "No chown-enabled volumes configured"
"""

    # Build post-start commands section
    post_start_commands = ""
    if config.post_start_commands:
        post_start_commands = """
# Execute post-start commands
log "Executing post-start commands"
"""
        for cmd in config.post_start_commands:
            # Escape the command for safe display in log
            escaped_cmd = cmd.replace('"', '\\"')
            post_start_commands += (
                f'log "Executing post-start command: {escaped_cmd}"\n'
            )
            # Execute command normally - users expect shell interpretation
            post_start_commands += f"{cmd}\n"
    else:
        post_start_commands = """
# No post-start commands configured
log "No post-start commands to execute"
"""

    script = f"""#!/bin/bash
set -e

# Verbose logging setup
VERBOSE={1 if verbose else 0}

log() {{
    if [ "$VERBOSE" = "1" ]; then
        echo "$*" >&2
    fi
}}

# User and group configuration
USER_NAME="{config.user_name}"
USER_ID="{config.user_id}"
GROUP_NAME="{config.group_name}"
GROUP_ID="{config.group_id}"
USER_HOME="{config.user_home}"
ADD_SUDO={1 if config.sudo else 0}

log "Starting ctenv container setup"
log "User: $USER_NAME (UID: $USER_ID)"
log "Group: $GROUP_NAME (GID: $GROUP_ID)"
log "Home: $USER_HOME"

# Create group if needed
log "Checking if group $GROUP_ID exists"
if getent group "$GROUP_ID" >/dev/null 2>&1; then
    GROUP_NAME=$(getent group "$GROUP_ID" | cut -d: -f1)
    log "Using existing group: $GROUP_NAME"
else
    log "Creating group: $GROUP_NAME (GID: $GROUP_ID)"
    groupadd -g "$GROUP_ID" "$GROUP_NAME"
fi

# Create user if needed
log "Checking if user $USER_NAME exists"
if ! getent passwd "$USER_NAME" >/dev/null 2>&1; then
    log "Creating user: $USER_NAME (UID: $USER_ID)"
    useradd --no-create-home --home-dir "$USER_HOME" \\
        --shell /bin/bash -u "$USER_ID" -g "$GROUP_ID" \\
        -o -c "" "$USER_NAME"
else
    log "User $USER_NAME already exists"
fi

# Setup home directory
export HOME="$USER_HOME"
log "Setting up home directory: $HOME"
if [ ! -d "$HOME" ]; then
    log "Creating home directory: $HOME"
    mkdir -p "$HOME"
    chown "$USER_ID:$GROUP_ID" "$HOME"
else
    log "Home directory already exists"
fi

# Set ownership of home directory (non-recursive)
log "Setting ownership of home directory"
chown "$USER_NAME" "$HOME"

{chown_commands}
{post_start_commands}

# Setup sudo if requested
if [ "$ADD_SUDO" = "1" ]; then
    log "Setting up sudo access for $USER_NAME"
    # Install sudo and configure passwordless access
    if command -v apt-get >/dev/null 2>&1; then
        log "Installing sudo using apt-get"
        apt-get update -qq && apt-get install -y -qq sudo
    elif command -v yum >/dev/null 2>&1; then
        log "Installing sudo using yum"
        yum install -y -q sudo
    elif command -v apk >/dev/null 2>&1; then
        log "Installing sudo using apk"
        apk add --no-cache sudo
    fi

    # Add user to sudoers
    log "Adding $USER_NAME to sudoers"
    echo "$USER_NAME ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
else
    log "Sudo not requested"
fi

# Set environment
log "Setting up shell environment"
export PS1="[ctenv] $ "

# Execute command as user
log "Starting command as $USER_NAME: {config.command}"
exec {config.gosu_mount} "$USER_NAME" {config.command}
"""
    return script


class ContainerRunner:
    """Manages Docker container operations."""

    @staticmethod
    def parse_volumes(
        volumes: Optional[Tuple[str, ...]],
    ) -> Tuple[List[str], List[str]]:
        """Parse volume strings and extract chown paths.

        Returns:
            tuple of (processed_volumes, chown_paths)
        """
        chown_paths = []
        processed_volumes = []

        if volumes is None:
            return processed_volumes, chown_paths

        for volume in volumes:
            if ":" not in volume:
                raise ValueError(
                    f"Invalid volume format: {volume}. Use HOST:CONTAINER format."
                )

            # Parse volume string: HOST:CONTAINER[:options]
            parts = volume.split(":")
            if len(parts) < 2:
                raise ValueError(
                    f"Invalid volume format: {volume}. Use HOST:CONTAINER format."
                )

            host_path = parts[0]
            container_path = parts[1]

            # Parse options (everything after second colon)
            options = []

            if len(parts) > 2:
                # Split comma-separated options
                option_parts = parts[2].split(",")
                for opt in option_parts:
                    opt = opt.strip()
                    if opt == "chown":
                        chown_paths.append(container_path)
                    else:
                        options.append(opt)

            # Rebuild volume string without chown option
            if options:
                volume_arg = f"{host_path}:{container_path}:{','.join(options)}"
            else:
                volume_arg = f"{host_path}:{container_path}"

            processed_volumes.append(volume_arg)

        return processed_volumes, chown_paths

    @staticmethod
    def build_run_args(
        config: ContainerConfig, entrypoint_script_path: str, verbose: bool = False
    ) -> List[str]:
        """Build Docker run arguments with provided script path."""
        logging.debug("Building Docker run arguments")

        args = [
            "docker",
            "run",
            "--rm",
            "--init",
        ]
        
        # Add platform flag only if specified
        if config.platform:
            args.append(f"--platform={config.platform}")
            
        args.append(f"--name={config.get_container_name()}")

        # Parse volume options
        processed_volumes, chown_paths = ContainerRunner.parse_volumes(config.volumes)

        # Volume mounts
        volume_args = [
            f"--volume={config.working_dir}:{config.working_dir_mount}:z,rw",
            f"--volume={config.gosu_path}:{config.gosu_mount}:z,ro",
            f"--volume={entrypoint_script_path}:/entrypoint.sh:z,ro",
            f"--workdir={config.working_dir_mount}",
        ]
        args.extend(volume_args)

        logging.debug("Volume mounts:")
        logging.debug(
            f"  Working dir: {config.working_dir} -> {config.working_dir_mount}"
        )
        logging.debug(f"  Gosu binary: {config.gosu_path} -> {config.gosu_mount}")
        logging.debug(
            f"  Entrypoint script: {entrypoint_script_path} -> /entrypoint.sh"
        )

        # Additional volume mounts
        if processed_volumes:
            logging.debug("Additional volume mounts:")
            for volume in processed_volumes:
                # Add :z option, merging with existing options if present
                if ":" in volume and len(volume.split(":")) > 2:
                    # Volume already has options, append z
                    volume_with_z = f"{volume},z"
                else:
                    # Volume has no options, add z
                    volume_with_z = f"{volume}:z"
                args.extend([f"--volume={volume_with_z}"])
                logging.debug(f"  {volume_with_z}")

        if chown_paths:
            logging.debug("Volumes with chown enabled:")
            for path in chown_paths:
                logging.debug(f"  {path}")

        # Environment variables
        if config.env:
            logging.debug("Environment variables:")
            for env_var in config.env:
                if "=" in env_var:
                    # Set specific value: NAME=VALUE
                    args.extend([f"--env={env_var}"])
                    logging.debug(f"  Setting: {env_var}")
                else:
                    # Pass from host: NAME
                    args.extend([f"--env={env_var}"])
                    value = os.environ.get(env_var, "<not set>")
                    logging.debug(f"  Passing: {env_var}={value}")

        # Resource limits (ulimits)
        if config.ulimits:
            logging.debug("Resource limits (ulimits):")
            for limit_name, limit_value in config.ulimits.items():
                args.extend([f"--ulimit={limit_name}={limit_value}"])
                logging.debug(f"  {limit_name}={limit_value}")

        # Network configuration
        if config.network:
            if config.network == "none":
                args.extend(["--network=none"])
            elif config.network == "host":
                args.extend(["--network=host"])
            elif config.network == "bridge":
                args.extend(["--network=bridge"])
            else:
                # Custom network name
                args.extend([f"--network={config.network}"])
            logging.debug(f"Network mode: {config.network}")
        else:
            # Default: no networking for security
            args.extend(["--network=none"])
            logging.debug("Network mode: none (default)")

        # TTY flags if running interactively
        if config.tty:
            args.extend(["-t", "-i"])
            logging.debug("TTY mode: enabled")
        else:
            logging.debug("TTY mode: disabled")

        # Set entrypoint to our script
        args.extend(["--entrypoint", "/entrypoint.sh"])

        # Container image
        args.append(config.image)
        logging.debug(f"Container image: {config.image}")

        return args

    @staticmethod
    def run_container(
        config: ContainerConfig, verbose: bool = False, dry_run: bool = False
    ) -> subprocess.CompletedProcess:
        """Execute Docker container with the given configuration."""
        logging.debug("Starting container execution")

        # Check if Docker is available
        docker_path = shutil.which("docker")
        if not docker_path:
            raise FileNotFoundError("Docker not found in PATH. Please install Docker.")
        logging.debug(f"Found Docker at: {docker_path}")

        # Verify gosu binary exists
        logging.debug(f"Checking for gosu binary at: {config.gosu_path}")
        if not config.gosu_path.exists():
            raise FileNotFoundError(
                f"gosu binary not found at {config.gosu_path}. Please ensure gosu is available."
            )

        if not config.gosu_path.is_file():
            raise FileNotFoundError(f"gosu path {config.gosu_path} is not a file.")

        # Verify current directory exists
        logging.debug(f"Verifying working directory: {config.working_dir}")
        if not config.working_dir.exists():
            raise FileNotFoundError(f"Directory {config.working_dir} does not exist.")

        if not config.working_dir.is_dir():
            raise FileNotFoundError(f"Path {config.working_dir} is not a directory.")

        # Parse volumes to get chown paths for script generation
        _, chown_paths = ContainerRunner.parse_volumes(config.volumes)

        # Generate entrypoint script content
        script_content = build_entrypoint_script(config, chown_paths, verbose)

        if dry_run:
            # Dry-run mode: don't create any files, use placeholder path
            entrypoint_script_path = "/tmp/entrypoint.sh"  # Placeholder for display
            docker_args = ContainerRunner.build_run_args(
                config, entrypoint_script_path, verbose
            )

            logging.debug(f"Executing Docker command: {' '.join(docker_args)}")

            # Print the command that would be executed
            print(" ".join(docker_args))

            # Show entrypoint script in verbose mode
            if verbose:
                print("\n" + "=" * 60, file=sys.stderr)
                print("Entrypoint script that would be executed:", file=sys.stderr)
                print("=" * 60, file=sys.stderr)
                print(script_content, file=sys.stderr)
                print("=" * 60 + "\n", file=sys.stderr)

            # Return a mock successful result
            result = subprocess.CompletedProcess(docker_args, 0)
            logging.debug("Dry-run mode: Docker command printed, not executed")
            return result
        else:
            # Real execution: create temporary script file
            script_fd, entrypoint_script_path = tempfile.mkstemp(
                suffix=".sh", text=True
            )
            logging.debug(
                f"Created temporary entrypoint script: {entrypoint_script_path}"
            )

            try:
                with os.fdopen(script_fd, "w") as f:
                    f.write(script_content)
                os.chmod(entrypoint_script_path, 0o755)

                # Build Docker arguments with actual script path
                docker_args = ContainerRunner.build_run_args(
                    config, entrypoint_script_path, verbose
                )

                logging.debug(f"Executing Docker command: {' '.join(docker_args)}")

                result = subprocess.run(docker_args, check=False)
                if result.returncode != 0:
                    logging.debug(f"Container exited with code: {result.returncode}")
                return result
            except subprocess.CalledProcessError as e:
                logging.error(f"Container execution failed: {e}")
                raise RuntimeError(f"Container execution failed: {e}")
            finally:
                # Clean up temporary script file
                try:
                    os.unlink(entrypoint_script_path)
                    logging.debug(
                        f"Cleaned up temporary script: {entrypoint_script_path}"
                    )
                except OSError:
                    pass


def setup_logging(verbose, quiet):
    """Configure logging based on verbosity flags."""
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG, format="%(message)s", stream=sys.stderr
        )
    elif quiet:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)


def cmd_run(args):
    """Run command in container."""
    verbose = args.verbose
    quiet = args.quiet

    # Load configuration early
    try:
        explicit_configs = [Path(c) for c in args.config] if args.config else None
        ctenv_config = CtenvConfig.load(explicit_config_files=explicit_configs)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse context and command from args
    context = args.context
    command_args = args.command

    # Simple parsing logic
    if command_args:
        # Command specified
        command = command_args
    else:
        # No command, default to bash
        command = ["bash"]

    # context can be None to use [defaults] section

    # Create config from loaded CtenvConfig and CLI options
    try:
        cli_overrides = {
            "image": args.image,
            "command": " ".join(command),
            "working_dir": args.working_dir,
            "env": args.env,
            "volumes": args.volumes,
            "sudo": args.sudo,
            "network": args.network,
            "gosu_path": args.gosu_path,
            "platform": args.platform,
            "post_start_commands": args.post_start_commands,
        }
        config = ctenv_config.resolve_container_config(
            context=context, cli_overrides=cli_overrides
        )
        
        # Validate platform if specified
        if config.platform and not validate_platform(config.platform):
            print(f"Error: Unsupported platform '{config.platform}'. Supported platforms: linux/amd64, linux/arm64", file=sys.stderr)
            sys.exit(1)
        
        # Resolve any missing paths (like gosu_path)
        config = config.resolve_missing_paths()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        logging.debug("Configuration:")
        logging.debug(f"  Image: {config.image}")
        logging.debug(f"  Command: {config.command}")
        logging.debug(f"  User: {config.user_name} (UID: {config.user_id})")
        logging.debug(f"  Group: {config.group_name} (GID: {config.group_id})")
        logging.debug(f"  Working directory: {config.working_dir}")
        logging.debug(f"  Container name: {config.get_container_name()}")
        logging.debug(f"  Environment variables: {config.env}")
        logging.debug(f"  Volumes: {config.volumes}")
        logging.debug(f"  Network: {config.network or 'none'}")
        logging.debug(f"  Sudo: {config.sudo}")
        logging.debug(f"  TTY: {config.tty}")
        logging.debug(f"  Platform: {config.platform or 'default'}")
        logging.debug(f"  Gosu binary: {config.gosu_path}")

    if not quiet:
        print("[ctenv] run", file=sys.stderr)

    # Execute container (or dry-run)
    try:
        # Resolve templates just before running the container
        resolved_config = config.resolve_templates()
        result = ContainerRunner.run_container(
            resolved_config, verbose, dry_run=args.dry_run
        )
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_show(args):
    """Show configuration or context details."""
    context = args.context

    try:
        # Load configuration early
        explicit_configs = [Path(c) for c in args.config] if args.config else None
        ctenv_config = CtenvConfig.load(explicit_config_files=explicit_configs)

        if context:
            # Show specific context
            if context not in ctenv_config.contexts:
                available = list(ctenv_config.contexts.keys())
                print(
                    f"Context '{context}' not found. Available: {available}",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Show context name
            print(f"Context '{context}':")

            try:
                # Get the resolved container config for this context
                resolved_config = ctenv_config.resolve_container_config(context=context)
                resolved_config = resolved_config.resolve_missing_paths()
            except FileNotFoundError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

            # Show key configuration values
            print(f"  image: {resolved_config.image}")
            print(f"  command: {resolved_config.command}")
            print(f"  network: {resolved_config.network}")
            print(f"  sudo: {resolved_config.sudo}")
            if resolved_config.env:
                print(f"  env: {list(resolved_config.env)}")
            if resolved_config.volumes:
                print(f"  volumes: {list(resolved_config.volumes)}")
            if resolved_config.post_start_commands:
                print(f"  post_start_commands: {list(resolved_config.post_start_commands)}")
        else:
            # Show all configuration
            print("Configuration:")

            # Show which config files are being used
            source_files = ctenv_config.source_files
            if len(source_files) == 0:
                print("\nUsing builtin contexts only")
            elif len(source_files) == 1:
                print(f"\nUsing config file: {source_files[0]}")
            else:
                print("\nUsing config files (highest to lowest priority):")
                for i, source_file in enumerate(source_files, 1):
                    print(f"  {i}. {source_file}")

            # Show defaults section if present
            if ctenv_config.defaults:
                print("\nDefaults:")
                defaults_config = ctenv_config.defaults
                print(f"  image: {defaults_config.image}")
                print(f"  command: {defaults_config.command}")
                print(f"  network: {defaults_config.network}")
                print(f"  sudo: {defaults_config.sudo}")
                if defaults_config.env:
                    print(f"  env: {list(defaults_config.env)}")
                if defaults_config.volumes:
                    print(f"  volumes: {list(defaults_config.volumes)}")

            # Show contexts
            if ctenv_config.contexts:
                print("\nContexts:")
                for ctx_name in sorted(ctenv_config.contexts.keys()):
                    print(f"  {ctx_name}")
            else:
                print("\nNo contexts defined")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


# Pinned gosu version for security and reproducibility
GOSU_VERSION = "1.17"

# SHA256 checksums for gosu 1.17 binaries
# Source: https://github.com/tianon/gosu/releases/download/1.17/SHA256SUMS
GOSU_CHECKSUMS = {
    "gosu-amd64": "bbc4136d03ab138b1ad66fa4fc051bafc6cc7ffae632b069a53657279a450de3",
    "gosu-arm64": "c3805a85d17f4454c23d7059bcb97e1ec1af272b90126e79ed002342de08389b",
}



def create_parser():
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog="ctenv",
        description="ctenv is a tool for running a program in a container as current user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,  # Require full option names
    )

    parser.add_argument("--version", action="version", version=f"ctenv {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress non-essential output"
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run command in container",
        description="""Run command in container

Examples:
    ctenv run                          # Interactive bash with defaults
    ctenv run dev                      # Use 'dev' context with default command
    ctenv run dev -- npm test         # Use 'dev' context, run npm test
    ctenv run -- ls -la               # Use defaults, run ls -la
    ctenv run --image alpine dev      # Override image, use dev context
    ctenv run --dry-run dev           # Show Docker command without running
    ctenv run --post-start-cmd "npm install" --post-start-cmd "npm run build" # Run extra commands after container starts

Note: Use '--' to separate commands from context/options.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    run_parser.add_argument(
        "context", nargs="?", help="Context to use (default: 'default')"
    )
    run_parser.add_argument("command", nargs="*", help="Command to run")
    run_parser.add_argument("--image", help="Container image to use")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show Docker command without running container",
    )
    run_parser.add_argument(
        "--config",
        action="append",
        help="Path to configuration file (can be used multiple times, order matters)",
    )
    run_parser.add_argument(
        "--env",
        action="append",
        dest="env",
        help="Set environment variable (NAME=VALUE) or pass from host (NAME)",
    )
    run_parser.add_argument(
        "--volume",
        action="append",
        dest="volumes",
        help="Mount additional volume (HOST:CONTAINER format)",
    )
    run_parser.add_argument(
        "--sudo",
        action="store_true",
        help="Add user to sudoers with NOPASSWD inside container",
    )
    run_parser.add_argument(
        "--network", help="Enable container networking (default: disabled for security)"
    )
    run_parser.add_argument(
        "--dir",
        dest="working_dir",
        help="Directory to mount as workdir (default: current directory)",
    )
    run_parser.add_argument(
        "--gosu-path",
        help="Path to gosu binary (default: auto-discover from PATH or .ctenv/gosu)",
    )
    run_parser.add_argument(
        "--platform",
        help="Container platform (e.g., linux/amd64, linux/arm64)",
    )
    run_parser.add_argument(
        "--post-start-cmd",
        action="append",
        dest="post_start_commands",
        help="Add extra command to run after container starts (can be used multiple times)",
    )

    # config subcommand group
    config_parser = subparsers.add_parser(
        "config", help="Configuration management commands"
    )
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", help="Config subcommands"
    )

    # config show
    config_show_parser = config_subparsers.add_parser(
        "show", help="Show configuration or context details"
    )
    config_show_parser.add_argument(
        "context", nargs="?", help="Context to show (default: show all)"
    )
    config_show_parser.add_argument(
        "--config",
        action="append",
        help="Path to configuration file (can be used multiple times, order matters)",
    )


    return parser


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose, args.quiet)

    # Route to appropriate command handler
    if args.subcommand == "run":
        cmd_run(args)
    elif args.subcommand == "config":
        if args.config_command == "show":
            cmd_config_show(args)
        else:
            parser.parse_args(["config", "--help"])
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
