#!/usr/bin/env -S uv run -q --script
#
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "tomli; python_version < '3.11'",
# ]
# ///

# ctenv
# https://github.com/osks/ctenv
#
# Copyright 2025 Oskar Skoog
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__version__ = "0.3"

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


def preprocess_tilde_expansion(text: str) -> str:
    """Convert ~/ at start of paths to ${env.HOME}/ for template processing."""
    if not text:
        return text

    # Only expand ~/ at the beginning of the string or after : (for volume specs)
    # Pattern matches:
    # - ~/ at start: "~/.docker" -> "${env.HOME}/.docker"
    # - ~/ after colon: "/host:~/.docker" -> "/host:${env.HOME}/.docker"
    # - ~/ after double colon: "/host::~/.docker" -> "/host::${env.HOME}/.docker"
    pattern = r"(^|:)~/"
    return re.sub(pattern, r"\1${env.HOME}/", text)


def substitute_template_variables(text: str, variables: Dict[str, str]) -> str:
    """Substitute ${var} and ${var|filter} patterns in text."""
    pattern = r"\$\{([^}|]+)(?:\|([^}]+))?\}"

    def replace_match(match):
        var_name, filter_name = match.groups()

        # Get value
        if var_name.startswith("env."):
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


def substitute_in_container(
    container_data: Dict[str, Any], variables: Dict[str, str]
) -> Dict[str, Any]:
    """Apply variable substitution to all string values in container."""
    result = {}
    for key, value in container_data.items():
        if isinstance(value, str):
            # Apply tilde preprocessing first, then template expansion
            processed_value = preprocess_tilde_expansion(value)
            result[key] = substitute_template_variables(processed_value, variables)
        elif isinstance(value, list):
            result[key] = [
                substitute_template_variables(
                    preprocess_tilde_expansion(item), variables
                )
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


def is_installed_package():
    """Check if running as installed package vs single file."""
    try:
        import importlib.util

        spec = importlib.util.find_spec("ctenv.binaries")
        return spec is not None
    except ImportError:
        return False


def find_default_gosu_path(
    start_dir: Optional[Path] = None, target_platform: Optional[str] = None
) -> Optional[Path]:
    """Find default gosu binary.

    Args:
        start_dir: Unused (kept for API compatibility)
        target_platform: Target container platform (e.g., "linux/amd64")

    Returns:
        Path to bundled gosu binary, or None if not found
    """
    # Get platform-specific binary name
    platform_gosu = get_platform_specific_gosu_name(target_platform)

    # If running as installed package, try to find bundled binary
    if is_installed_package():
        try:
            # With zip_safe=False, we can use direct paths to package files
            import ctenv

            package_dir = Path(ctenv.__file__).parent
            bundled_gosu = package_dir / "binaries" / platform_gosu

            if bundled_gosu.exists() and bundled_gosu.is_file():
                logging.debug(f"Using bundled gosu: {bundled_gosu}")
                return bundled_gosu
        except (ImportError, AttributeError):
            # Package not found, continue with other methods
            pass

    # Single-file mode or package mode failed - no bundled binary available
    logging.debug("No bundled gosu binary found")
    return None


def find_gosu_binary(
    start_dir: Optional[Path] = None,
    explicit_path: Optional[str] = None,
    target_platform: Optional[str] = None,
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
        "workspace": "auto",  # Default to auto-detection
        "workdir": None,  # Default to None (preserve relative position)
        "gosu_path": None,  # Will be resolved later with platform consideration
        # Mount points
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


def _resolve_relative_paths(config_data: Dict[str, Any], config_dir: Path) -> Dict[str, Any]:
    """Resolve relative paths in config data relative to config file directory."""
    resolved_data = copy.deepcopy(config_data)
    
    # Fields that need path resolution
    path_fields = ["workspace", "workdir"]  # Add more as needed
    
    def resolve_path_in_dict(data_dict: Dict[str, Any]) -> None:
        for key, value in data_dict.items():
            if key in path_fields and isinstance(value, str):
                # Handle workspace with volume syntax
                if key == "workspace" and ":" in value:
                    # Parse host:container:options syntax
                    parts = value.split(":")
                    if len(parts) >= 2:
                        host_part = parts[0]
                        if host_part == ".":
                            # Resolve "." to config directory
                            parts[0] = str(config_dir)
                            data_dict[key] = ":".join(parts)
                elif key == "workspace" and value == ".":
                    # Simple "." -> resolve to config directory
                    data_dict[key] = str(config_dir)
                elif key == "workdir" and not value.startswith("/"):
                    # Relative workdir -> resolve relative to config directory
                    resolved_path = config_dir / value
                    data_dict[key] = str(resolved_path)
    
    # Resolve paths in defaults
    if "defaults" in resolved_data and isinstance(resolved_data["defaults"], dict):
        resolve_path_in_dict(resolved_data["defaults"])
    
    # Resolve paths in each container
    if "containers" in resolved_data:
        for container_name, container_config in resolved_data["containers"].items():
            if isinstance(container_config, dict):
                resolve_path_in_dict(container_config)
    
    return resolved_data


@dataclass
class ConfigFile:
    """Represents a single configuration file with containers and defaults."""

    containers: Dict[str, Dict[str, Any]]
    defaults: Optional[Dict[str, Any]]
    path: Optional[Path]  # None for built-in defaults

    @classmethod
    def builtin(cls) -> "ConfigFile":
        """Create a ConfigFile with built-in defaults."""
        return cls(
            containers={},
            defaults=None,
            path=None,
        )

    @classmethod
    def from_file(cls, config_path: Path) -> "ConfigFile":
        """Load configuration from a specific file."""
        if not config_path.exists():
            raise ValueError(f"Config file not found: {config_path}")

        config_data = _load_config_file(config_path)
        
        # Resolve relative paths before processing
        config_dir = config_path.parent
        resolved_data = _resolve_relative_paths(config_data, config_dir)
        
        raw_containers = resolved_data.get("containers", {})
        raw_defaults = resolved_data.get("defaults")  # None if not present

        logging.debug(f"Loaded config from {config_path}")
        return cls(
            containers=raw_containers,
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
    """Load user configuration (~/.ctenv.toml)."""
    user_config_path = Path.home() / ".ctenv.toml"

    if not user_config_path.exists() or not user_config_path.is_file():
        return None

    return ConfigFile.from_file(user_config_path)


def load_project_config(start_dir: Optional[Path] = None) -> Optional[ConfigFile]:
    """Load project configuration (searched upward from start_dir)."""
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()
    while True:
        config_path = current / ".ctenv.toml"
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

    Contains pre-computed defaults and containers from all config sources.
    Config sources are processed in priority order during load():
    - Explicit config files (if provided via --config)
    - Project config (./.ctenv/ctenv.toml found via upward search)
    - User config (~/.ctenv/ctenv.toml)
    - System defaults
    """

    defaults: Dict[str, Any]  # Computed defaults (system + first file defaults found)
    containers: Dict[
        str, Dict[str, Any]
    ]  # All containers from all files (higher priority wins)

    def find_container(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Find container by name.

        Returns the container dict if found, or None if not found.
        """
        return self.containers.get(container_name)

    def resolve_container_config(
        self,
        container: Optional[str] = None,
        cli_overrides: Optional[Dict[str, Any]] = None,
    ) -> "ContainerConfig":
        """Resolve a complete ContainerConfig for the given container with CLI overrides.

        Priority order:
        1. Precomputed defaults
        2. Container config (if specified)
        3. CLI overrides (highest priority)

        All merging is done with raw dicts, ContainerConfig is created only at the end.
        """
        if cli_overrides is None:
            cli_overrides = {}

        # Start with precomputed defaults
        result_dict = self.defaults.copy()

        # Layer 2: Container config (if specified)
        if container is not None:
            container_config = self.find_container(container)
            if container_config is None:
                available = sorted(self.containers.keys())
                raise ValueError(
                    f"Unknown container '{container}'. Available: {available}"
                )

            result_dict = merge_config(result_dict, container_config)
        else:
            logging.debug("No container specified")

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

        # Compute containers (merge all containers, higher priority wins)
        containers = {}
        # Process in reverse order so higher priority overrides
        for config_file in reversed(config_files):
            containers.update(config_file.containers)

        return cls(defaults=defaults, containers=containers)


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
    workspace: str = "auto"  # Can be "auto", ".", path, or volume syntax
    workdir: Optional[str] = None  # Where to cd inside container
    gosu_path: Optional[Path] = None

    # Mount points (structural, always set)
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
    run_args: Optional[List[str]] = None

    def get_container_name(self) -> str:
        """Generate container name based on working directory."""
        if self.container_name:
            return self.container_name
        # Use workspace source path for container name
        # Parse workspace to get source path
        workspace_parts = self.workspace.split(":")
        workspace_source = workspace_parts[0]
        if workspace_source in ("auto", "."):
            # Use current directory for now, will be resolved later
            workspace_source = str(Path.cwd())
        dir_id = workspace_source.replace("/", "-")
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
                raise FileNotFoundError("No gosu binary found.")
            resolved_data["gosu_path"] = resolved_gosu

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
                # Apply tilde preprocessing first, then template expansion
                processed_value = preprocess_tilde_expansion(value)
                config_dict[key] = substitute_template_variables(
                    processed_value, variables
                )
            elif isinstance(value, (list, tuple)) and value:
                config_dict[key] = [
                    substitute_template_variables(
                        preprocess_tilde_expansion(item), variables
                    )
                    if isinstance(item, str)
                    else item
                    for item in value
                ]

        # Convert back
        return ContainerConfig.from_dict(config_dict)
    
    def resolve_workspace(self) -> Tuple[Path, Path, str, Optional[Path]]:
        """Resolve workspace string to mount paths and working directory.
        
        Returns:
            Tuple of (workspace_source, workspace_target, mount_options, container_workdir)
        """
        # Parse workspace string with volume syntax
        parts = self.workspace.split(":")
        
        # Default mount options
        mount_options = "z,rw"
        
        # Handle different formats
        if len(parts) == 1:
            # Simple format: /path or auto or .
            source = parts[0]
            target = None  # Will be set to source after resolution
            options = None
        elif len(parts) == 2:
            # host:container format
            source = parts[0]
            target = parts[1]
            options = None
        elif len(parts) >= 3:
            # host:container:options format
            source = parts[0]
            target = parts[1]
            options = parts[2]
            if options:
                mount_options = f"{options},z"
        else:
            raise ValueError(f"Invalid workspace format: {self.workspace}")
        
        # Resolve source path
        if source in ("auto", "", "."):
            # Auto-detect workspace
            workspace_source = self._find_project_root() or Path.cwd()
        else:
            # Explicit path
            workspace_source = Path(source).resolve()
        
        # Resolve target path
        if target is None:
            # Same as source
            workspace_target = workspace_source
        else:
            workspace_target = Path(target)
        
        # Resolve container working directory
        if self.workdir is not None:
            # Explicit workdir
            if self.workdir.startswith("/"):
                # Absolute path
                container_workdir = Path(self.workdir)
            else:
                # Relative path - resolve relative to workspace target
                container_workdir = workspace_target / self.workdir
        else:
            # Preserve relative position
            try:
                rel_path = Path.cwd().relative_to(workspace_source)
                container_workdir = workspace_target / rel_path
            except ValueError:
                # Not in workspace, use workspace root
                container_workdir = workspace_target
        
        return workspace_source, workspace_target, mount_options, container_workdir
    
    def _find_project_root(self) -> Optional[Path]:
        """Find project root by searching for .ctenv.toml file."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".ctenv.toml").exists():
                return current
            current = current.parent
        return None

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
            if key == "gosu_path" and isinstance(value, str):
                kwargs[key] = Path(value) if value else None
            # Handle list fields
            elif key in (
                "env",
                "volumes",
                "post_start_commands",
                "run_args",
            ) and isinstance(value, (list, tuple)):
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
    config: ContainerConfig,
    chown_paths: List[str] = None,
    verbose: bool = False,
    quiet: bool = False,
) -> str:
    """Generate bash script for container entrypoint."""
    chown_paths = chown_paths or []

    # Build chown commands for volumes marked with :chown
    chown_commands = ""
    if chown_paths:
        chown_commands = """
# Fix ownership of chown-enabled volumes
log_debug "Checking volumes for ownership fixes"
"""
        for path in chown_paths:
            # Safely quote the path to prevent injection
            quoted_path = shlex.quote(path)
            # For logging, escape quotes in the original path
            escaped_path = path.replace('"', '\\"')
            chown_commands += f'log_debug "Checking chown volume: {escaped_path}"\n'
            chown_commands += f"if [ -d {quoted_path} ]; then\n"
            chown_commands += (
                f'    log_debug "Fixing ownership of volume: {escaped_path}"\n'
            )
            chown_commands += f'    chown -R "$USER_ID:$GROUP_ID" {quoted_path}\n'
            chown_commands += "else\n"
            chown_commands += (
                f'    log_debug "Chown volume does not exist: {escaped_path}"\n'
            )
            chown_commands += "fi\n"
    else:
        chown_commands = """
# No volumes require ownership fixes
log_debug "No chown-enabled volumes configured"
"""

    # Build post-start commands section
    post_start_commands = ""
    if config.post_start_commands:
        post_start_commands = """
# Execute post-start commands
log_debug "Executing post-start commands"
"""
        for cmd in config.post_start_commands:
            # Escape the command for safe display in log
            escaped_cmd = cmd.replace('"', '\\"')
            post_start_commands += (
                f'log_debug "Executing post-start command: {escaped_cmd}"\n'
            )
            # Execute command normally - users expect shell interpretation
            post_start_commands += f"{cmd}\n"
    else:
        post_start_commands = """
# No post-start commands configured
log_debug "No post-start commands to execute"
"""

    script = f"""#!/bin/bash
set -e

# Logging setup
VERBOSE={1 if verbose else 0}
QUIET={1 if quiet else 0}

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

# User and group configuration
USER_NAME="{config.user_name}"
USER_ID="{config.user_id}"
GROUP_NAME="{config.group_name}"
GROUP_ID="{config.group_id}"
USER_HOME="{config.user_home}"
ADD_SUDO={1 if config.sudo else 0}

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
    groupadd -g "$GROUP_ID" "$GROUP_NAME"
fi

# Create user if needed
log_debug "Checking if user $USER_NAME exists"
if ! getent passwd "$USER_NAME" >/dev/null 2>&1; then
    log_debug "Creating user: $USER_NAME (UID: $USER_ID)"
    useradd --no-create-home --home-dir "$USER_HOME" \\
        --shell /bin/bash -u "$USER_ID" -g "$GROUP_ID" \\
        -o -c "" "$USER_NAME"
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

{chown_commands}
{post_start_commands}

# Setup sudo if requested
if [ "$ADD_SUDO" = "1" ]; then
    log_debug "Setting up sudo access for $USER_NAME"
    # Install sudo and configure passwordless access
    if command -v apt-get >/dev/null 2>&1; then
        log_info "Installing sudo..."
        apt-get update -qq && apt-get install -y -qq sudo
    elif command -v yum >/dev/null 2>&1; then
        log_info "Installing sudo..."
        yum install -y -q sudo
    elif command -v apk >/dev/null 2>&1; then
        log_info "Installing sudo..."
        apk add --no-cache sudo
    fi

    # Add user to sudoers
    log_debug "Adding $USER_NAME to sudoers"
    echo "$USER_NAME ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
else
    log_debug "Sudo not requested"
fi

# Set environment
log_debug "Setting up shell environment"
export PS1="[ctenv] $ "

# Execute command as user
log_info "Starting command as $USER_NAME: {config.command}"
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

        Supports multiple formats:
        - HOST:CONTAINER[:options] - Standard format
        - HOST - Smart defaulting: HOST:HOST
        - HOST::options - Empty target with options: HOST:HOST:options

        Returns:
            tuple of (processed_volumes, chown_paths)
        """
        chown_paths = []
        processed_volumes = []

        if volumes is None:
            return processed_volumes, chown_paths

        for volume in volumes:
            # Handle different volume formats
            if "::" in volume:
                # Format: HOST::options -> HOST:HOST:options
                parts = volume.split("::", 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid volume format: {volume}")

                host_path = parts[0]
                container_path = host_path  # Smart defaulting
                options_str = parts[1]
            elif ":" in volume:
                # Standard format: HOST:CONTAINER[:options]
                parts = volume.split(":")
                if len(parts) < 2:
                    raise ValueError(
                        f"Invalid volume format: {volume}. Use HOST:CONTAINER format."
                    )

                host_path = parts[0]
                container_path = parts[1]
                options_str = ":".join(parts[2:]) if len(parts) > 2 else ""
            else:
                # Single path format: HOST -> HOST:HOST
                host_path = volume
                container_path = host_path  # Smart defaulting
                options_str = ""

            # Parse options
            options = []
            if options_str:
                option_parts = options_str.split(",")
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

        # Resolve workspace
        workspace_source, workspace_target, mount_options, container_workdir = config.resolve_workspace()

        # Volume mounts
        volume_args = [
            f"--volume={workspace_source}:{workspace_target}:{mount_options}",
            f"--volume={config.gosu_path}:{config.gosu_mount}:z,ro",
            f"--volume={entrypoint_script_path}:/entrypoint.sh:z,ro",
            f"--workdir={container_workdir}",
        ]
        args.extend(volume_args)

        logging.debug("Volume mounts:")
        logging.debug(
            f"  Workspace: {workspace_source} -> {workspace_target} (options: {mount_options})"
        )
        logging.debug(f"  Working directory: {container_workdir}")
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
            args.extend([f"--network={config.network}"])
            logging.debug(f"Network mode: {config.network}")
        else:
            # Default: use Docker's default networking (no --network flag)
            logging.debug("Network mode: default (Docker default)")

        # TTY flags if running interactively
        if config.tty:
            args.extend(["-t", "-i"])
            logging.debug("TTY mode: enabled")
        else:
            logging.debug("TTY mode: disabled")

        # Custom run arguments
        if config.run_args:
            logging.debug("Custom run arguments:")
            for run_arg in config.run_args:
                args.append(run_arg)
                logging.debug(f"  {run_arg}")

        # Set entrypoint to our script
        args.extend(["--entrypoint", "/entrypoint.sh"])

        # Container image
        args.append(config.image)
        logging.debug(f"Container image: {config.image}")

        return args

    @staticmethod
    def run_container(
        config: ContainerConfig,
        verbose: bool = False,
        dry_run: bool = False,
        quiet: bool = False,
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

        # Verify workspace exists
        workspace_source, _, _, _ = config.resolve_workspace()
        logging.debug(f"Verifying workspace directory: {workspace_source}")
        if not workspace_source.exists():
            raise FileNotFoundError(f"Workspace directory {workspace_source} does not exist.")

        if not workspace_source.is_dir():
            raise FileNotFoundError(f"Workspace path {workspace_source} is not a directory.")

        # Parse volumes to get chown paths for script generation
        _, chown_paths = ContainerRunner.parse_volumes(config.volumes)

        # Generate entrypoint script content
        script_content = build_entrypoint_script(config, chown_paths, verbose, quiet)

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


def cmd_run(args, command):
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

    # Parse container from args
    container = args.container

    # container can be None to use [defaults] section

    # Process CLI volumes with tilde expansion and template processing
    processed_volumes = None
    if args.volumes:
        processed_volumes = []
        # Create variables for template expansion (same as resolve_templates)
        template_variables = {
            "USER": getpass.getuser(),
            "image": args.image or "ubuntu:latest",  # Use provided image or default
        }

        for volume in args.volumes:
            # Apply tilde preprocessing
            volume_with_tilde = preprocess_tilde_expansion(volume)
            # Apply template expansion
            volume_expanded = substitute_template_variables(
                volume_with_tilde, template_variables
            )
            processed_volumes.append(volume_expanded)

    # Create config from loaded CtenvConfig and CLI options
    try:
        cli_overrides = {
            "image": args.image,
            "command": command,
            "workspace": args.workspace,
            "workdir": args.workdir,
            "env": args.env,
            "volumes": processed_volumes,
            "sudo": args.sudo,
            "network": args.network,
            "gosu_path": str(Path(args.gosu_path).resolve())
            if args.gosu_path
            else None,
            "platform": args.platform,
            "post_start_commands": args.post_start_commands,
            "run_args": args.run_args,
        }
        config = ctenv_config.resolve_container_config(
            container=container, cli_overrides=cli_overrides
        )

        # Validate platform if specified
        if config.platform and not validate_platform(config.platform):
            print(
                f"Error: Unsupported platform '{config.platform}'. Supported platforms: linux/amd64, linux/arm64",
                file=sys.stderr,
            )
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
        workspace_source, workspace_target, _, container_workdir = config.resolve_workspace()
        logging.debug(f"  Workspace: {workspace_source} -> {workspace_target}")
        logging.debug(f"  Working directory: {container_workdir}")
        logging.debug(f"  Container name: {config.get_container_name()}")
        logging.debug(f"  Environment variables: {config.env}")
        logging.debug(f"  Volumes: {config.volumes}")
        logging.debug(f"  Network: {config.network or 'default (Docker default)'}")
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
            resolved_config, verbose, dry_run=args.dry_run, quiet=quiet
        )
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_show(args):
    """Show configuration or container details."""
    container = getattr(args, "container", None)

    try:
        # Load configuration early
        explicit_configs = [Path(c) for c in getattr(args, "config", None) or []]
        ctenv_config = CtenvConfig.load(explicit_config_files=explicit_configs)

        if container:
            # Show specific container
            if container not in ctenv_config.containers:
                available = list(ctenv_config.containers.keys())
                print(
                    f"Container '{container}' not found. Available: {available}",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Show container name
            print(f"Container '{container}':")

            try:
                # Get the resolved container config for this container
                resolved_config = ctenv_config.resolve_container_config(
                    container=container
                )
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
                print(
                    f"  post_start_commands: {list(resolved_config.post_start_commands)}"
                )
        else:
            # Show all configuration
            print("Configuration:")

            # Show defaults section if present
            if ctenv_config.defaults:
                print("\nDefaults:")
                defaults_config = ctenv_config.defaults
                print(f"  image: {defaults_config.get('image')}")
                print(f"  command: {defaults_config.get('command')}")
                print(f"  network: {defaults_config.get('network')}")
                print(f"  sudo: {defaults_config.get('sudo')}")
                if defaults_config.get("env"):
                    print(f"  env: {list(defaults_config['env'])}")
                if defaults_config.get("volumes"):
                    print(f"  volumes: {list(defaults_config['volumes'])}")

            # Show containers
            if ctenv_config.containers:
                print("\nContainers:")
                for cnt_name in sorted(ctenv_config.containers.keys()):
                    print(f"  {cnt_name}")
            else:
                print("\nNo containers defined")

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
    ctenv run dev                      # Use 'dev' container with default command
    ctenv run dev -- npm test         # Use 'dev' container, run npm test
    ctenv run -- ls -la               # Use defaults, run ls -la
    ctenv run --image alpine dev      # Override image, use dev container
    ctenv run --dry-run dev           # Show Docker command without running
    ctenv run --post-start-command "npm install" --post-start-command "npm run build" # Run extra commands after container starts

Note: Use '--' to separate commands from container/options.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    run_parser.add_argument(
        "container", nargs="?", help="Container to use (default: 'default')"
    )
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
        "--workspace",
        help="Workspace to mount (supports volume syntax: /path, /host:/container, auto:/repo)",
    )
    run_parser.add_argument(
        "--workdir",
        help="Working directory inside container (where to cd)",
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
        "--run-arg",
        action="append",
        dest="run_args",
        help="Add custom argument to container run command (can be used multiple times)",
    )
    run_parser.add_argument(
        "--post-start-command",
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
        "show", help="Show configuration or container details"
    )
    config_show_parser.add_argument(
        "container", nargs="?", help="Container to show (default: show all)"
    )
    config_show_parser.add_argument(
        "--config",
        action="append",
        help="Path to configuration file (can be used multiple times, order matters)",
    )

    return parser


def main(argv=None):
    """Main entry point."""
    # Always use sys.argv[1:] when called without arguments
    if argv is None:
        argv = sys.argv[1:]

    # Split at '--' if present to separate ctenv args from command args
    if "--" in argv:
        separator_index = argv.index("--")
        ctenv_args = argv[:separator_index]
        command_args = argv[separator_index + 1 :]
        command = " ".join(command_args)
    else:
        ctenv_args = argv
        command = None

    # Parse only ctenv arguments
    parser = create_parser()
    args = parser.parse_args(ctenv_args)

    # Setup logging
    setup_logging(args.verbose, args.quiet)

    # Route to appropriate command handler
    if args.subcommand == "run":
        cmd_run(args, command)
    elif args.subcommand == "config":
        if args.config_command == "show" or args.config_command is None:
            cmd_config_show(args)
        else:
            parser.parse_args(["config", "--help"])
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
