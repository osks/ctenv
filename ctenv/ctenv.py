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

# Version format: MAJOR.MINOR[.devN]
# - Use .dev0 suffix during development
# - Remove .dev0 for stable releases
# - Increment MINOR for new features, MAJOR for breaking changes
__version__ = "0.3.dev0"

import argparse
import collections.abc
import copy
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
from dataclasses import dataclass, field, asdict, replace, fields
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


# Sentinel object for "not configured" values
class _NotSetType:
    """Sentinel type for not configured values."""

    def __repr__(self) -> str:
        return "NOTSET"

    def __deepcopy__(self, memo):
        """Always return the same singleton instance."""
        return self


NOTSET = _NotSetType()

# Type alias for clean type hints
if TYPE_CHECKING:
    NotSetType: TypeAlias = _NotSetType
else:
    NotSetType = _NotSetType


# Volume specification: (host_path, container_path, options)
@dataclass(kw_only=True)
class RuntimeContext:
    """Runtime context for container execution."""

    user_name: str
    user_id: int
    user_home: str
    group_name: str
    group_id: int
    cwd: Path
    tty: bool
    project_root: Path

    @classmethod
    def current(cls) -> "RuntimeContext":
        """Get current runtime context."""
        user_info = pwd.getpwuid(os.getuid())
        group_info = grp.getgrgid(os.getgid())
        current_cwd = Path.cwd()
        return cls(
            user_name=user_info.pw_name,
            user_id=user_info.pw_uid,
            user_home=user_info.pw_dir,
            group_name=group_info.gr_name,
            group_id=group_info.gr_gid,
            cwd=current_cwd,
            tty=sys.stdin.isatty(),
            project_root=(find_project_root(current_cwd) or current_cwd).resolve(),
        )


@dataclass
class VolumeSpec:
    """Volume specification with host path, container path, and options."""

    host_path: str
    container_path: str
    options: List[str] = field(default_factory=list)

    def to_string(self) -> str:
        """Convert volume spec back to Docker format string."""
        if self.container_path:
            if self.options:
                return (
                    f"{self.host_path}:{self.container_path}:{','.join(self.options)}"
                )
            else:
                return f"{self.host_path}:{self.container_path}"
        else:
            if self.options:
                return f"{self.host_path}::{','.join(self.options)}"
            else:
                # Special case: if both host and container are empty, return ":"
                if not self.host_path:
                    return ":"
                return self.host_path

    @classmethod
    def parse(cls, spec: str) -> "VolumeSpec":
        """
        Parse volume/workspace specification into VolumeSpec.

        This handles pure structural parsing only - no smart defaulting or validation.
        Smart defaulting and validation should be done by the calling functions.

        """
        if not spec:
            raise ValueError("Empty volume specification")

        # Parse standard format or single path
        match spec.split(":"):
            case [host_path]:
                # Single path format: container path defaults to host path
                container_path = host_path
                options_str = ""
            case [host_path, container_path]:
                # HOST:CONTAINER format - preserve empty container_path if specified
                options_str = ""
            case [host_path, container_path, options_str]:
                # HOST:CONTAINER:options format - preserve empty container_path if specified
                pass  # options_str is already set
            case _:
                # Fallback for malformed cases (too many colons, etc.)
                raise ValueError(f"Invalid volume format: {spec}")

        # Parse options into list
        options = []
        if options_str:
            options = [opt.strip() for opt in options_str.split(",") if opt.strip()]

        return cls(host_path, container_path, options)

    @classmethod
    def parse_as_volume(cls, spec: str) -> "VolumeSpec":
        """Parse as volume specification with volume-specific defaulting and validation."""
        vol_spec = cls.parse(spec)

        # Volume validation: must have explicit host path
        if not vol_spec.host_path:
            raise ValueError(f"Volume host path cannot be empty: {spec}")

        # Volume smart defaulting: empty container path defaults to host path
        # (This handles :: syntax where container_path is explicitly empty)
        if not vol_spec.container_path:
            vol_spec.container_path = vol_spec.host_path

        return vol_spec

    @classmethod
    def parse_as_workspace(cls, spec: str) -> "VolumeSpec":
        """Parse as workspace specification with workspace-specific defaulting."""
        workspace_spec = cls.parse(spec)

        # Workspace allows empty host path (for auto-detection)
        # Note: container_path defaults to host_path in parse() for single path format
        return workspace_spec


def resolve_relative_path(path: str, base_dir: Path) -> str:
    """Resolve relative paths (./, ../, . or ..) relative to base_dir."""
    if path in (".", "..") or path.startswith(("./", "../")):
        return str((base_dir / path).resolve())
    return path


def resolve_relative_volume_spec(vol_spec: str, base_dir: Path) -> str:
    """Resolve relative paths in volume specification relative to base_dir."""
    spec = VolumeSpec.parse(vol_spec)  # Use base parse for both

    # Only resolve relative paths in host path if it's not empty
    if spec.host_path:
        spec.host_path = resolve_relative_path(spec.host_path, base_dir)
    # Container paths are not resolved (they're paths inside the container)

    return spec.to_string()


def find_project_root(start_dir: Path) -> Optional[Path]:
    """Find project root by searching for .ctenv.toml file.

    Args:
        start_dir: Directory to start search from

    Returns:
        Path to project root directory or None if not found
    """
    current = start_dir
    while current != current.parent:
        if (current / ".ctenv.toml").exists():
            return current
        current = current.parent
    return None


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


def convert_notset_strings(container_config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Convert "NOTSET" strings to NOTSET sentinel in container configuration.

    Processes a container configuration dictionary, converting any top-level
    values that are exactly "NOTSET" to the NOTSET sentinel object.

    "NOTSET" strings in nested structures (lists, nested dicts) are left
    unchanged and will cause validation errors later - this is intended
    behavior as nested "NOTSET" usage is invalid.

    Args:
        container_config_dict: Container configuration dictionary from CLI args or TOML

    Returns:
        Dictionary with top-level "NOTSET" strings converted to NOTSET sentinel
    """
    return {
        k: (NOTSET if v == "NOTSET" else v) for k, v in container_config_dict.items()
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


def find_user_config() -> Optional[Path]:
    """Find user configuration path (~/.ctenv.toml)."""
    user_config_path = Path.home() / ".ctenv.toml"

    if not user_config_path.exists() or not user_config_path.is_file():
        return None

    return user_config_path


def find_project_config(start_dir: Path) -> Optional[Path]:
    """Find project configuration path (searched upward from start_dir)."""
    current = start_dir.resolve()
    while True:
        config_path = current / ".ctenv.toml"
        if config_path.exists() and config_path.is_file():
            return config_path

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    return None


@dataclass(kw_only=True)
class ContainerConfig:
    """Parsed configuration object with NOTSET sentinel support.

    This represents configuration AFTER parsing from TOML/CLI but BEFORE
    final resolution. Raw TOML cannot contain NOTSET objects, but this
    parsed representation can.

    All fields default to NOTSET (meaning "not configured") to distinguish
    between explicit configuration and missing values. This allows
    ContainerConfig to represent partial configurations (e.g., from CLI
    overrides or individual config files) that can be merged together.

    Note: NOTSET fields do not indicate what is required by downstream
    consumers - they simply mean "not configured in this source".
    """

    # Container settings
    image: Union[str, NotSetType] = NOTSET
    command: Union[str, NotSetType] = NOTSET
    workspace: Union[str, NotSetType] = NOTSET
    workdir: Union[str, NotSetType] = NOTSET
    gosu_path: Union[str, NotSetType] = NOTSET
    container_name: Union[str, NotSetType] = NOTSET
    tty: Union[str, bool, NotSetType] = NOTSET
    sudo: Union[bool, NotSetType] = NOTSET

    # Network and platform settings
    network: Union[str, NotSetType] = NOTSET
    platform: Union[str, NotSetType] = NOTSET
    ulimits: Union[Dict[str, Any], NotSetType] = NOTSET

    # Lists (use NOTSET to distinguish from empty list)
    env: Union[List[str], NotSetType] = NOTSET
    volumes: Union[List[str], NotSetType] = NOTSET
    post_start_commands: Union[List[str], NotSetType] = NOTSET
    run_args: Union[List[str], NotSetType] = NOTSET

    # Metadata fields for resolution context
    _config_file_path: Union[str, NotSetType] = NOTSET

    def to_dict(self, include_notset: bool = False) -> Dict[str, Any]:
        """Convert to dictionary.

        Args:
            include_notset: If True, include NOTSET values. If False, filter out NOTSET and None values.
                          Default False for clean external representation.
        """
        result = asdict(self)

        if not include_notset:
            # Filter out None and NOTSET values for display/config files
            return {
                k: v for k, v in result.items() if v is not None and v is not NOTSET
            }

        return result

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], ignore_unknown: bool = True
    ) -> "ContainerConfig":
        """Create ContainerConfig from dictionary.

        Args:
            data: Dictionary to convert
            ignore_unknown: If True, filter out unknown fields. If False, pass all fields to constructor.
        """
        # Get field names if filtering unknown fields
        if ignore_unknown:
            field_names = {f.name for f in fields(cls)}
            filtered_data = {k: v for k, v in data.items() if k in field_names}
        else:
            filtered_data = data

        # Convert None to NOTSET and create instance in one step
        return cls(
            **{k: (NOTSET if v is None else v) for k, v in filtered_data.items()}
        )

    @classmethod
    def builtin_defaults(cls) -> "ContainerConfig":
        """Get built-in default configuration values.

        Note: User identity and cwd are runtime context, not configuration.
        """
        return cls(
            # Auto-detect behaviors
            workspace="auto",  # Auto-detect project root
            workdir="auto",  # Preserve relative position
            gosu_path="auto",  # Auto-detect bundled binary
            tty="auto",  # Auto-detect from stdin
            # Container settings with defaults
            image="ubuntu:latest",
            command="bash",
            container_name="ctenv-${project_root|slug}",
            sudo=False,
            # Lists with empty defaults
            env=[],
            volumes=[],
            post_start_commands=[],
            run_args=[],
            # Fields that remain unset (NOTSET)
            network=NOTSET,  # No network specified
            platform=NOTSET,  # No platform specified
            ulimits=NOTSET,  # No limits specified
            # Metadata fields
            _config_file_path=NOTSET,  # No config file for defaults
        )


def resolve_relative_paths_in_container_config(
    config: ContainerConfig, base_dir: Path
) -> ContainerConfig:
    """Return new ContainerConfig with relative paths resolved."""
    updates = {}

    # Only update fields that need path resolution
    if config.workspace is not NOTSET:
        updates["workspace"] = resolve_relative_volume_spec(config.workspace, base_dir)

    if config.volumes is not NOTSET:
        updates["volumes"] = [
            resolve_relative_volume_spec(vol, base_dir) for vol in config.volumes
        ]

    if config.gosu_path is not NOTSET:
        updates["gosu_path"] = resolve_relative_path(config.gosu_path, base_dir)

    # Return new ContainerConfig with only the changed fields
    return replace(config, **updates)


@dataclass
class ConfigFile:
    """Represents a single configuration file with containers and defaults."""

    containers: Dict[str, ContainerConfig]
    defaults: Optional[ContainerConfig]
    path: Optional[Path]  # None for built-in defaults

    @classmethod
    def load(cls, config_path: Path) -> "ConfigFile":
        """Load configuration from a specific file."""
        if not config_path.exists():
            raise ValueError(f"Config file not found: {config_path}")

        config_data = _load_config_file(config_path)

        raw_containers = config_data.get("containers", {})
        raw_defaults = config_data.get("defaults")

        config_dir = config_path.parent

        # Process defaults to ContainerConfig if present
        defaults_config = None
        if raw_defaults:
            defaults_config = ContainerConfig.from_dict(
                convert_notset_strings(raw_defaults)
            )
            defaults_config._config_file_path = str(config_path.resolve())
            defaults_config = resolve_relative_paths_in_container_config(
                defaults_config, config_dir
            )

        # Process containers to ContainerConfig objects
        container_configs = {}
        for name, container_dict in raw_containers.items():
            container_config = ContainerConfig.from_dict(
                convert_notset_strings(container_dict)
            )
            container_config._config_file_path = str(config_path.resolve())
            container_config = resolve_relative_paths_in_container_config(
                container_config, config_dir
            )
            container_configs[name] = container_config

        logging.debug(f"Loaded config from {config_path}")
        return cls(
            containers=container_configs,
            defaults=defaults_config,
            path=config_path,
        )


def merge_dict(config, overrides):
    # Handle NOTSET config by starting with empty dict
    if config is NOTSET:
        result = {}
    else:
        result = copy.deepcopy(config)
    
    for k, v in overrides.items():
        # Skip NOTSET values - they should not override existing config
        if v is NOTSET:
            continue
        elif isinstance(v, collections.abc.Mapping):
            base_value = result.get(k, {}) if result else {}
            result[k] = merge_dict(base_value, v)
        elif isinstance(v, list):
            result[k] = result.get(k, []) + v
        else:
            result[k] = copy.deepcopy(v)
    return result


def merge_container_configs(
    base: ContainerConfig, override: ContainerConfig
) -> ContainerConfig:
    """Merge two ContainerConfig objects, with override taking precedence.

    Uses the same logic as merge_dict:
    - NOTSET values in override don't replace base values
    - Lists are concatenated
    - Dicts are recursively merged
    - Other values from override replace base values
    """
    base_dict = base.to_dict(include_notset=True)  # Includes NOTSET values
    override_dict = override.to_dict(include_notset=True)  # Includes NOTSET values
    merged_dict = merge_dict(base_dict, override_dict)
    return ContainerConfig.from_dict(merged_dict)


@dataclass
class CtenvConfig:
    """Represents the computed ctenv configuration.

    Contains pre-computed defaults and containers from all config sources.
    Config sources are processed in priority order during load():
    - Explicit config files (if provided via --config)
    - Project config (./.ctenv/ctenv.toml found via upward search)
    - User config (~/.ctenv/ctenv.toml)
    - ctenv defaults
    """

    defaults: ContainerConfig  # System + file defaults as ContainerConfig
    containers: Dict[str, ContainerConfig]  # Container configs from all files

    def get_default(
        self, overrides: Optional[ContainerConfig] = None
    ) -> ContainerConfig:
        """Get default configuration with optional overrides.

        Args:
            overrides: Optional ContainerConfig overrides to merge

        Returns:
            Merged ContainerConfig ready for parse_container_config()
        """
        # Start with precomputed defaults
        result_config = self.defaults

        # Apply overrides if provided
        if overrides:
            result_config = merge_container_configs(result_config, overrides)

        return result_config

    def get_container(
        self,
        container: str,
        overrides: Optional[ContainerConfig] = None,
    ) -> ContainerConfig:
        """Get merged ContainerConfig for the specified container.

        Priority order:
        1. Precomputed defaults
        2. Container config
        3. Overrides (highest priority)

        Args:
            container: Container name (required)
            overrides: Optional ContainerConfig overrides to merge

        Returns:
            Merged ContainerConfig ready for parse_container_config()

        Raises:
            ValueError: If container name is unknown
        """
        # Get container config
        container_config = self.containers.get(container)
        if container_config is None:
            available = sorted(self.containers.keys())
            raise ValueError(f"Unknown container '{container}'. Available: {available}")

        # Start with precomputed defaults and merge container config
        result_config = merge_container_configs(self.defaults, container_config)

        # Apply overrides if provided
        if overrides:
            result_config = merge_container_configs(result_config, overrides)

        return result_config

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
                    loaded_config = ConfigFile.load(config_file)
                    config_files.append(loaded_config)
                except Exception as e:
                    raise ValueError(
                        f"Failed to load explicit config file {config_file}: {e}"
                    )

        # Project config (if no explicit configs)
        if not explicit_config_files:
            search_dir = start_dir or Path.cwd()
            project_config_path = find_project_config(search_dir)
            if project_config_path:
                config_files.append(ConfigFile.load(project_config_path))

        # User config
        user_config_path = find_user_config()
        if user_config_path:
            config_files.append(ConfigFile.load(user_config_path))

        # Compute defaults (system defaults + first file defaults found)
        defaults = ContainerConfig.builtin_defaults()
        for config_file in config_files:
            if config_file.defaults:
                defaults = merge_container_configs(defaults, config_file.defaults)
                break  # Stop after first (= highest prio) [defaults] section found

        # Compute containers (merge all containers, higher priority wins)
        containers = {}
        # Process in reverse order so higher priority overrides
        for config_file in reversed(config_files):
            for name, container_config in config_file.containers.items():
                if name in containers:
                    # Merge with existing (higher priority wins)
                    containers[name] = merge_container_configs(
                        containers[name], container_config
                    )
                else:
                    containers[name] = container_config

        return cls(defaults=defaults, containers=containers)


def _substitute_variables(
    text: str, variables: Dict[str, str], environ: Dict[str, str]
) -> str:
    """Substitute ${var} and ${var|filter} patterns in text."""
    pattern = r"\$\{([^}|]+)(?:\|([^}]+))?\}"

    def replace_match(match):
        var_name, filter_name = match.groups()

        # Get value
        if var_name.startswith("env."):
            value = environ.get(var_name[4:], "")
        else:
            value = variables.get(var_name, "")

        # Apply filter
        if filter_name == "slug":
            value = value.replace(":", "-").replace("/", "-")
        elif filter_name is not None:
            raise ValueError(f"Unknown filter: {filter_name}")

        return value

    return re.sub(pattern, replace_match, text)


def _substitute_variables_in_container_config(
    config: ContainerConfig, runtime: RuntimeContext, environ: Dict[str, str]
) -> ContainerConfig:
    """Substitute template variables in all string fields of ContainerConfig."""
    # Build variables dictionary
    variables = {
        "image": config.image if config.image is not NOTSET else "",
        "user_home": runtime.user_home,
        "user_name": runtime.user_name,
        "project_root": str(runtime.project_root),
    }

    def substitute_field(value):
        """Substitute variables in a field, handling NOTSET and different types."""
        if value is NOTSET:
            return NOTSET
        elif isinstance(value, str):
            return _substitute_variables(value, variables, environ)
        elif isinstance(value, list):
            return [
                _substitute_variables(item, variables, environ)
                if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            return value

    # Use replace() to create new instance with substituted fields
    updates = {}
    for field in fields(config):
        original_value = getattr(config, field.name)
        substituted_value = substitute_field(original_value)
        if substituted_value != original_value:
            updates[field.name] = substituted_value

    return replace(config, **updates)


def expand_tilde_in_path(path: str, runtime: RuntimeContext) -> str:
    """Expand ~ to user home directory in a path string."""
    if path.startswith("~/"):
        return runtime.user_home + path[1:]
    elif path == "~":
        return runtime.user_home
    return path


def _expand_tilde_in_volumespec(
    vol_spec: VolumeSpec, runtime: RuntimeContext
) -> VolumeSpec:
    """Expand tilde (~/) in VolumeSpec paths using the provided user_home value."""
    # Create a copy to avoid mutating the original
    result = VolumeSpec(
        vol_spec.host_path, vol_spec.container_path, vol_spec.options[:]
    )

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


def _parse_workspace(
    workspace_config: Union[str, NotSetType, None], runtime: RuntimeContext
) -> VolumeSpec:
    """Parse workspace configuration and return VolumeSpec.

    Handles auto-detection, project root expansion, tilde expansion, and SELinux options.
    """
    # Resolve workspace configuration
    if workspace_config == "auto":
        workspace_str = f"{runtime.project_root}:{runtime.project_root}"
    elif isinstance(workspace_config, str) and workspace_config != "auto":
        workspace_str = workspace_config
    else:
        raise ValueError(f"Invalid workspace value: {workspace_config}")

    spec = VolumeSpec.parse_as_workspace(workspace_str)

    # Fill in empty host path with project root (for ":" syntax)
    if not spec.host_path:
        spec.host_path = str(runtime.project_root)

        # If container path is also empty, use same path as default
        if not spec.container_path:
            spec.container_path = str(runtime.project_root)

    # Apply tilde expansion
    spec = _expand_tilde_in_volumespec(spec, runtime)

    # Add 'z' option if not already present (for SELinux)
    if "z" not in spec.options:
        spec.options.append("z")

    return spec


def _resolve_workdir_auto(workspace_spec: VolumeSpec, runtime: RuntimeContext) -> str:
    """Auto-resolve working directory, preserving relative position within workspace."""
    # Calculate relative position within workspace and translate
    try:
        rel_path = os.path.relpath(str(runtime.cwd), workspace_spec.host_path)
        if rel_path == "." or rel_path.startswith(".."):
            # At workspace root or outside workspace - use container workspace path
            return workspace_spec.container_path
        else:
            # Inside workspace - preserve relative position
            return os.path.join(workspace_spec.container_path, rel_path).replace(
                "\\", "/"
            )
    except (ValueError, OSError):
        # Fallback if path calculation fails
        return workspace_spec.container_path


def _resolve_workdir(
    workdir_config: Union[str, NotSetType, None],
    workspace_spec: VolumeSpec,
    runtime: RuntimeContext,
) -> str:
    """Resolve working directory based on configuration value."""
    if workdir_config == "auto":
        return _resolve_workdir_auto(workspace_spec, runtime)
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


def _resolve_tty(
    tty_config: Union[str, bool, NotSetType, None], runtime: RuntimeContext
) -> bool:
    """Resolve TTY setting based on configuration value."""
    if tty_config == "auto":
        return runtime.tty
    elif isinstance(tty_config, bool):
        return tty_config
    else:
        raise ValueError(f"Invalid TTY value: {tty_config}")


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
    workspace: VolumeSpec  # Fully resolved workspace mount
    workdir: str  # Always resolved (defaults to workspace root)
    gosu: VolumeSpec  # Gosu binary mount

    # Container settings (always have defaults)
    image: str  # From defaults or config
    command: str  # From defaults or config
    container_name: str  # Always generated if not specified
    tty: bool  # From defaults (stdin.isatty()) or config
    sudo: bool  # From defaults (False) or config

    # Lists (use empty list as default instead of None)
    env: List[str] = field(default_factory=list)
    volumes: List[VolumeSpec] = field(default_factory=list)
    chown_paths: List[str] = field(
        default_factory=list
    )  # Paths to chown inside container
    post_start_commands: List[str] = field(default_factory=list)
    run_args: List[str] = field(default_factory=list)

    # Truly optional fields (None has meaning)
    network: Optional[str] = None  # None = Docker default networking
    platform: Optional[str] = None  # None = Docker default platform
    ulimits: Optional[Dict[str, Any]] = None  # None = no ulimits

    def build_entrypoint_script(
        self,
        verbose: bool = False,
        quiet: bool = False,
    ) -> str:
        """Generate bash script for container entrypoint."""

        # Build chown paths value using a rare delimiter
        chown_paths_value = ""
        if self.chown_paths:
            # Use a rare delimiter sequence unlikely to appear in paths
            delimiter = "|||CTENV_DELIMITER|||"
            chown_paths_value = shlex.quote(delimiter.join(self.chown_paths))
        else:
            chown_paths_value = "''"

        # Build post-start commands as newline-separated string
        post_start_commands_value = ""
        if self.post_start_commands:
            # Join commands with actual newlines and quote the result
            commands_text = "\n".join(self.post_start_commands)
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
USER_NAME="{self.user_name}"
USER_ID="{self.user_id}"
GROUP_NAME="{self.group_name}"
GROUP_ID="{self.group_id}"
USER_HOME="{self.user_home}"
ADD_SUDO={1 if self.sudo else 0}

# Container configuration
GOSU_MOUNT="{self.gosu.container_path}"
COMMAND={shlex.quote(self.command)}

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
        useradd --no-create-home --home-dir "$USER_HOME" \\
            --shell /bin/sh -u "$USER_ID" -g "$GROUP_ID" \\
            -o -c "" "$USER_NAME"
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
        if command -v apt-get >/dev/null 2>&1; then
            log_info "Installing sudo..."
            apt-get update -qq && apt-get install -y -qq sudo
        elif command -v yum >/dev/null 2>&1; then
            log_info "Installing sudo..."
            yum install -y -q sudo
        elif command -v apk >/dev/null 2>&1; then
            log_info "Installing sudo..."
            apk add --no-cache sudo
        else
            echo "ERROR: sudo not installed and no supported package manager found (apt-get, yum, or apk)" >&2
            exit 1
        fi
    else
        log_debug "sudo is already installed"
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
log_info "Starting command as $USER_NAME: $COMMAND"
exec "$GOSU_MOUNT" "$USER_NAME" sh -c "$COMMAND"
"""
        return script


def parse_container_config(
    config: ContainerConfig, runtime: RuntimeContext
) -> ContainerSpec:
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
    substituted_config = _substitute_variables_in_container_config(
        config, runtime, os.environ
    )

    # Validate required fields are not NOTSET
    required_fields = {
        "image": substituted_config.image,
        "command": substituted_config.command,
        "workspace": substituted_config.workspace,
        "workdir": substituted_config.workdir,
        "gosu_path": substituted_config.gosu_path,
        "container_name": substituted_config.container_name,
        "tty": substituted_config.tty,
    }

    missing_fields = [
        name for name, value in required_fields.items() if value is NOTSET
    ]
    if missing_fields:
        raise ValueError(
            f"Required configuration fields not set: {', '.join(missing_fields)}"
        )

    # Validate platform if specified
    if substituted_config.platform is not NOTSET and not validate_platform(
        substituted_config.platform
    ):
        raise ValueError(
            f"Unsupported platform '{substituted_config.platform}'. Supported platforms: linux/amd64, linux/arm64"
        )

    # Process volumes (can't inline due to complexity and chown_paths extraction)
    volume_specs = []
    chown_paths = []
    volumes = (
        substituted_config.volumes if substituted_config.volumes is not NOTSET else []
    )
    for vol_str in volumes:
        vol_spec = VolumeSpec.parse_as_volume(vol_str)
        vol_spec = _expand_tilde_in_volumespec(vol_spec, runtime)

        # Check for chown option and extract it
        if "chown" in vol_spec.options:
            chown_paths.append(vol_spec.container_path)
            # Remove chown from options as it's not a Docker option
            vol_spec.options = [opt for opt in vol_spec.options if opt != "chown"]

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
        "env",
        "post_start_commands",
        "run_args",
        "network",
        "platform",
        "ulimits",
    ]

    # Parse workspace first since workdir depends on it
    workspace_spec = _parse_workspace(substituted_config.workspace, runtime)

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
        "workspace": workspace_spec,  # config.workspace (str) → VolumeSpec
        "gosu": _parse_gosu_spec(substituted_config.gosu_path, runtime),  # Inlined
        "volumes": volume_specs,  # config.volumes (List[str]) → List[VolumeSpec]
        # 2. Resolved/computed values
        "workdir": _resolve_workdir(
            substituted_config.workdir, workspace_spec, runtime
        ),  # Inlined
        "tty": _resolve_tty(substituted_config.tty, runtime),  # Inlined
        # 3. Extracted/derived values
        "chown_paths": chown_paths,  # Extracted from volumes with "chown" option
    }

    return ContainerSpec(**spec_dict)


class ContainerRunner:
    """Manages Docker container operations."""

    @staticmethod
    def _safe_unlink(path: str) -> None:
        """Safely remove a file, ignoring errors."""
        try:
            os.unlink(path)
            logging.debug(f"Cleaned up temporary script: {path}")
        except OSError:
            pass

    @staticmethod
    def build_run_args(
        spec: ContainerSpec, entrypoint_script_path: str, verbose: bool = False
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

        # Volume mounts
        volume_args = [
            f"--volume={spec.workspace.to_string()}",
            f"--volume={spec.gosu.to_string()}",
            f"--volume={entrypoint_script_path}:/ctenv/entrypoint.sh:z,ro",
            f"--workdir={spec.workdir}",
        ]
        args.extend(volume_args)

        logging.debug("Volume mounts:")
        logging.debug(f"  Workspace: {spec.workspace.to_string()}")
        logging.debug(f"  Working directory: {spec.workdir}")
        logging.debug(f"  Gosu binary: {spec.gosu.to_string()}")
        logging.debug(
            f"  Entrypoint script: {entrypoint_script_path} -> /ctenv/entrypoint.sh"
        )

        # Additional volume mounts
        if spec.volumes:
            logging.debug("Additional volume mounts:")
            for vol_spec in spec.volumes:
                volume_arg = f"--volume={vol_spec.to_string()}"
                args.append(volume_arg)
                logging.debug(f"  {vol_spec.to_string()}")

        if spec.chown_paths:
            logging.debug("Volumes with chown enabled:")
            for path in spec.chown_paths:
                logging.debug(f"  {path}")

        # Environment variables
        if spec.env:
            logging.debug("Environment variables:")
            for env_var in spec.env:
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
        if spec.ulimits:
            logging.debug("Resource limits (ulimits):")
            for limit_name, limit_value in spec.ulimits.items():
                args.extend([f"--ulimit={limit_name}={limit_value}"])
                logging.debug(f"  {limit_name}={limit_value}")

        # Network configuration
        if spec.network:
            args.extend([f"--network={spec.network}"])
            logging.debug(f"Network mode: {spec.network}")
        else:
            # Default: use Docker's default networking (no --network flag)
            logging.debug("Network mode: default (Docker default)")

        # TTY flags if running interactively
        if spec.tty:
            args.extend(["-t", "-i"])
            logging.debug("TTY mode: enabled")
        else:
            logging.debug("TTY mode: disabled")

        # Custom run arguments
        if spec.run_args:
            logging.debug("Custom run arguments:")
            for run_arg in spec.run_args:
                args.append(run_arg)
                logging.debug(f"  {run_arg}")

        # Set entrypoint to our script
        args.extend(["--entrypoint", "/ctenv/entrypoint.sh"])

        # Container image
        args.append(spec.image)
        logging.debug(f"Container image: {spec.image}")

        return args

    @staticmethod
    def run_container(
        spec: ContainerSpec,
        verbose: bool = False,
        dry_run: bool = False,
        quiet: bool = False,
    ) -> subprocess.CompletedProcess:
        """Execute Docker container with the given specification."""
        logging.debug("Starting container execution")

        # Check if Docker is available
        docker_path = shutil.which("docker")
        if not docker_path:
            raise FileNotFoundError("Docker not found in PATH. Please install Docker.")
        logging.debug(f"Found Docker at: {docker_path}")

        # Verify gosu binary exists
        logging.debug(f"Checking for gosu binary at: {spec.gosu.host_path}")
        gosu_path = Path(spec.gosu.host_path)
        if not gosu_path.exists():
            raise FileNotFoundError(
                f"gosu binary not found at {spec.gosu.host_path}. Please ensure gosu is available."
            )

        if not gosu_path.is_file():
            raise FileNotFoundError(f"gosu path {spec.gosu.host_path} is not a file.")

        # Verify workspace exists
        workspace_source = Path(spec.workspace.host_path)
        logging.debug(f"Verifying workspace directory: {workspace_source}")
        if not workspace_source.exists():
            raise FileNotFoundError(
                f"Workspace directory {workspace_source} does not exist."
            )

        if not workspace_source.is_dir():
            raise FileNotFoundError(
                f"Workspace path {workspace_source} is not a directory."
            )

        # Generate entrypoint script content (chown paths are already in spec)
        script_content = spec.build_entrypoint_script(verbose, quiet)

        # Handle script file creation
        if dry_run:
            entrypoint_script_path = "/tmp/entrypoint.sh"  # Placeholder for display
            script_cleanup = None
        else:
            script_fd, entrypoint_script_path = tempfile.mkstemp(
                suffix=".sh", text=True
            )
            logging.debug(
                f"Created temporary entrypoint script: {entrypoint_script_path}"
            )
            with os.fdopen(script_fd, "w") as f:
                f.write(script_content)
            os.chmod(entrypoint_script_path, 0o755)
            script_cleanup = lambda: ContainerRunner._safe_unlink(
                entrypoint_script_path
            )

        try:
            # Build Docker arguments (same for both modes)
            docker_args = ContainerRunner.build_run_args(
                spec, entrypoint_script_path, verbose
            )
            logging.debug(f"Executing Docker command: {' '.join(docker_args)}")

            # Show what will be executed
            if dry_run:
                print(" ".join(docker_args))

            # Show entrypoint script in verbose mode
            if verbose:
                print("\n" + "=" * 60, file=sys.stderr)
                print(
                    "Entrypoint script"
                    + (" that would be executed:" if dry_run else ":"),
                    file=sys.stderr,
                )
                print("=" * 60, file=sys.stderr)
                print(script_content, file=sys.stderr)
                print("=" * 60 + "\n", file=sys.stderr)

            # Execute or mock execution
            if dry_run:
                logging.debug("Dry-run mode: Docker command printed, not executed")
                return subprocess.CompletedProcess(docker_args, 0)
            else:
                result = subprocess.run(docker_args, check=False)
                if result.returncode != 0:
                    logging.debug(f"Container exited with code: {result.returncode}")
                return result

        except subprocess.CalledProcessError as e:
            if not dry_run:
                logging.error(f"Container execution failed: {e}")
                raise RuntimeError(f"Container execution failed: {e}")
            raise
        finally:
            if script_cleanup:
                script_cleanup()


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

    # Get runtime context once at the start
    runtime = RuntimeContext.current()

    # Load configuration early
    try:
        explicit_configs = [Path(c) for c in args.config] if args.config else None
        ctenv_config = CtenvConfig.load(explicit_config_files=explicit_configs)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Create config from loaded CtenvConfig and CLI options
    try:
        # Convert CLI overrides to ContainerConfig and resolve paths
        # convert "NOTSET" string to NOTSET sentinel
        cli_overrides = resolve_relative_paths_in_container_config(
            ContainerConfig.from_dict(
                convert_notset_strings(
                    {
                        "image": args.image,
                        "command": command,
                        "workspace": args.workspace,
                        "workdir": args.workdir,
                        "env": args.env,
                        "volumes": args.volumes,
                        "sudo": args.sudo,
                        "network": args.network,
                        "gosu_path": args.gosu_path,
                        "platform": args.platform,
                        "post_start_commands": args.post_start_commands,
                        "run_args": args.run_args,
                    }
                )
            ),
            runtime.cwd,
        )

        # Get merged ContainerConfig
        if args.container is None:
            container_config = ctenv_config.get_default(overrides=cli_overrides)
        else:
            container_config = ctenv_config.get_container(
                container=args.container, overrides=cli_overrides
            )

        # Parse and resolve to ContainerSpec with runtime context
        spec = parse_container_config(container_config, runtime)

    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        # Use resolved spec for debugging output to show final values
        logging.debug("Configuration:")
        logging.debug(f"  Image: {spec.image}")
        logging.debug(f"  Command: {spec.command}")
        logging.debug(f"  User: {spec.user_name} (UID: {spec.user_id})")
        logging.debug(f"  Group: {spec.group_name} (GID: {spec.group_id})")
        logging.debug(
            f"  Workspace: {spec.workspace.host_path} -> {spec.workspace.container_path}"
        )
        logging.debug(f"  Working directory: {spec.workdir}")
        logging.debug(f"  Container name: {spec.container_name}")
        logging.debug(f"  Environment variables: {spec.env}")
        logging.debug(f"  Volumes: {[vol.to_string() for vol in spec.volumes]}")
        logging.debug(f"  Network: {spec.network or 'default (Docker default)'}")
        logging.debug(f"  Sudo: {spec.sudo}")
        logging.debug(f"  TTY: {spec.tty}")
        logging.debug(f"  Platform: {spec.platform or 'default'}")
        logging.debug(f"  Gosu binary: {spec.gosu.to_string()}")

    if not quiet:
        print("[ctenv] run", file=sys.stderr)

    # Execute container (or dry-run)
    try:
        result = ContainerRunner.run_container(
            spec, verbose, dry_run=args.dry_run, quiet=quiet
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
    try:
        # Load configuration early
        explicit_configs = [Path(c) for c in getattr(args, "config", None) or []]
        ctenv_config = CtenvConfig.load(explicit_config_files=explicit_configs)

        # Show defaults section if present
        if ctenv_config.defaults:
            print("defaults:")
            defaults_dict = ctenv_config.defaults.to_dict(include_notset=False)
            for key, value in sorted(defaults_dict.items()):
                if not key.startswith("_"):  # Skip metadata fields
                    print(f"  {key} = {repr(value)}")
            print()

        # Show containers sorted by config name
        print("containers:")
        if ctenv_config.containers:
            for config_name in sorted(ctenv_config.containers.keys()):
                print(f"  {config_name}:")
                container_dict = ctenv_config.containers[config_name].to_dict(
                    include_notset=False
                )
                for key, value in sorted(container_dict.items()):
                    if not key.startswith("_"):  # Skip metadata fields
                        print(f"    {key} = {repr(value)}")
                print()  # Empty line between containers
        else:
            print("# No containers defined")

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
        "--config",
        action="append",
        help="Path to configuration file (can be used multiple times, order matters)",
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
        "-v", "--verbose", action="store_true", help="Enable verbose output"
    )
    run_parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress non-essential output"
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show commands without running container",
    )

    run_parser.add_argument(
        "container", nargs="?", help="Container to use (default: 'default')"
    )
    run_parser.add_argument("--image", help="Container image to use")
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
        "--platform",
        help="Container platform (e.g., linux/amd64, linux/arm64)",
    )
    run_parser.add_argument(
        "--gosu-path",
        help="Path to gosu binary (default: auto-discover from PATH or .ctenv/gosu)",
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
    config_subparsers.add_parser("show", help="Show configuration or container details")

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
        # Use shlex.join to properly quote arguments
        command = shlex.join(command_args)
    else:
        ctenv_args = argv
        command = None

    # Parse only ctenv arguments
    parser = create_parser()
    args = parser.parse_args(ctenv_args)

    # Route to appropriate command handler
    if args.subcommand == "run":
        # Setup logging for run command (which has verbose/quiet flags)
        setup_logging(args.verbose, args.quiet)
        cmd_run(args, command)
    elif args.subcommand == "config":
        # Setup basic logging for config command (no verbose/quiet flags)
        setup_logging(verbose=False, quiet=False)
        if args.config_command == "show" or args.config_command is None:
            cmd_config_show(args)
        else:
            parser.parse_args(["config", "--help"])
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
