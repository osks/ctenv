"""Configuration management for ctenv.

This module handles loading, parsing, merging, and resolving configuration
from TOML files and CLI arguments.
"""

import collections.abc
import copy
import grp
import os
import pwd
import re
import shlex
import sys
from dataclasses import dataclass, field, asdict, replace, fields
from enum import Enum, IntEnum
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING

try:
    import tomllib
except ImportError:
    # For python < 3.11
    import tomli as tomllib

if TYPE_CHECKING:
    from typing_extensions import TypeAlias


class Verbosity(IntEnum):
    """Verbosity levels for CLI output."""

    QUIET = -1  # -q: errors only
    NORMAL = 0  # default: status messages
    VERBOSE = 1  # -v: detailed info
    VERY_VERBOSE = 2  # -vv: full debug output


class ContainerRuntime(Enum):
    """Container runtime and mode combinations.

    Each value represents a specific runtime + mode combination that determines
    how ctenv handles user identity preservation:

    - DOCKER_ROOTFUL: Docker with root-based user creation (current default)
    - PODMAN_ROOTLESS: Podman with --userns=keep-id (simplified entrypoint)
    """

    DOCKER_ROOTFUL = "docker"
    PODMAN_ROOTLESS = "podman"
    # Future:
    # PODMAN_ROOTFUL = "podman-rootful"
    # DOCKER_ROOTLESS = "docker-rootless"

    @property
    def command(self) -> str:
        """Return the container runtime command to execute."""
        _RUNTIME_COMMANDS = {
            ContainerRuntime.DOCKER_ROOTFUL: "docker",
            ContainerRuntime.PODMAN_ROOTLESS: "podman",
        }
        return _RUNTIME_COMMANDS[self]


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


@dataclass
class EnvVar:
    """Environment variable specification with name and optional value."""

    name: str
    value: Optional[str] = None  # None = pass from host environment

    def to_docker_arg(self) -> str:
        """Convert to Docker --env argument format."""
        if self.value is None:
            return f"--env={self.name}"  # Pass from host
        else:
            return f"--env={self.name}={shlex.quote(self.value)}"


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
                return f"{self.host_path}:{self.container_path}:{','.join(self.options)}"
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
                container_path = ""
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
    project_dir: Path
    pid: int

    @classmethod
    def current(cls, *, cwd: Path, project_dir: Path) -> "RuntimeContext":
        """Get current runtime context.

        Args:
            cwd: Current working directory
            project_dir: Resolved project directory (use resolve_project_dir to get this)
        """
        user_info = pwd.getpwuid(os.getuid())
        group_info = grp.getgrgid(os.getgid())
        return cls(
            user_name=user_info.pw_name,
            user_id=user_info.pw_uid,
            user_home=user_info.pw_dir,
            group_name=group_info.gr_name,
            group_id=group_info.gr_gid,
            cwd=cwd,
            tty=sys.stdin.isatty(),
            project_dir=project_dir,
            pid=os.getpid(),
        )


def resolve_project_dir(cwd: Path, project_dir_arg: Optional[str] = None) -> Path:
    """Resolve project directory from CLI arg or auto-detect.

    Args:
        cwd: Current working directory
        project_dir_arg: CLI --project-dir argument (None = auto-detect)

    Returns:
        Resolved absolute path to project directory
    """
    if project_dir_arg is None:
        return (find_project_dir(cwd) or cwd).resolve()
    else:
        return Path(project_dir_arg).resolve()


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

    # For container paths: resolve relative paths to absolute paths
    # This handles cases where container path defaults to a relative host path
    if spec.container_path and not os.path.isabs(spec.container_path):
        spec.container_path = resolve_relative_path(spec.container_path, base_dir)

    return spec.to_string()


def resolve_relative_subpath_spec(subpath_str: str, base_dir: Path) -> str:
    """Resolve relative paths in subpath specification.

    Subpath syntax: HOST_PATH[:OPTIONS]
    Example: ./src:ro -> /absolute/path/to/src:ro
    """
    if ":" in subpath_str:
        host_path, options = subpath_str.split(":", 1)
        resolved_host = resolve_relative_path(host_path, base_dir)
        return f"{resolved_host}:{options}"
    else:
        return resolve_relative_path(subpath_str, base_dir)


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
    return {k: (NOTSET if v == "NOTSET" else v) for k, v in container_config_dict.items()}


def _load_config_file(config_path: Path) -> Dict[str, Any]:
    """Load and parse TOML configuration file."""
    try:
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
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


def find_project_dir(start_dir: Path) -> Optional[Path]:
    """Find project root by searching for .ctenv.toml file.

    Searches upward from start_dir but stops at the user's home directory
    (without including it). This prevents treating $HOME as a project root
    even if it contains .ctenv.toml, since $HOME/.ctenv.toml is intended
    for user-wide configuration, not as a project workspace marker.

    Args:
        start_dir: Directory to start search from

    Returns:
        Path to project root directory or None if not found
    """
    current = start_dir.resolve()
    home_dir = Path.home().resolve()

    while current != current.parent:
        # Stop before reaching home directory
        if current == home_dir:
            break

        if (current / ".ctenv.toml").exists():
            return current
        current = current.parent
    return None


@dataclass(kw_only=True)
class BuildConfig:
    """Container image build configuration.

    All fields default to NOTSET (meaning "not configured") to distinguish
    between explicit configuration and missing values. This allows
    BuildConfig to represent partial configurations that can be merged together.
    """

    dockerfile: Union[str, NotSetType] = NOTSET
    dockerfile_content: Union[str, NotSetType] = NOTSET
    context: Union[str, NotSetType] = NOTSET
    tag: Union[str, NotSetType] = NOTSET
    args: Union[Dict[str, str], NotSetType] = NOTSET

    def to_dict(self, include_notset: bool = False) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)

        if not include_notset:
            # Filter out NOTSET values for display/config files
            result = {k: v for k, v in result.items() if v is not NOTSET}

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BuildConfig":
        """Create BuildConfig from dictionary, ignoring unknown keys."""
        known_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)

    @classmethod
    def builtin_defaults(cls) -> "BuildConfig":
        """Get built-in default configuration values for build."""
        return cls(
            context=".",  # Default to current directory
            tag="ctenv-${project_dir|slug}:latest",
            args={},
        )


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
    build: Union[BuildConfig, NotSetType] = NOTSET
    command: Union[str, NotSetType] = NOTSET
    project_target: Union[str, NotSetType] = (
        NOTSET  # Target path in container for project (e.g., "/repo")
    )
    auto_project_mount: Union[bool, NotSetType] = NOTSET  # Auto-mount project directory (default: True)
    workdir: Union[str, NotSetType] = NOTSET
    gosu_path: Union[str, NotSetType] = NOTSET
    container_name: Union[str, NotSetType] = NOTSET
    tty: Union[str, bool, NotSetType] = NOTSET
    sudo: Union[bool, NotSetType] = NOTSET

    # Network and platform settings
    network: Union[str, NotSetType] = NOTSET
    platform: Union[str, NotSetType] = NOTSET
    runtime: Union[str, NotSetType] = NOTSET  # "docker" or "podman"
    ulimits: Union[Dict[str, Any], NotSetType] = NOTSET

    # Lists (use NOTSET to distinguish from empty list)
    subpaths: Union[List[str], NotSetType] = NOTSET
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
            return {k: v for k, v in result.items() if v is not None and v is not NOTSET}

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any], ignore_unknown: bool = True) -> "ContainerConfig":
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

        # Convert special fields and None to NOTSET
        converted_data = {}
        for k, v in filtered_data.items():
            if v is None:
                converted_data[k] = NOTSET
            elif k == "build" and isinstance(v, dict):
                # Convert build dict to BuildConfig
                converted_data[k] = BuildConfig.from_dict(v)
            else:
                converted_data[k] = v

        return cls(**converted_data)

    @classmethod
    def builtin_defaults(cls) -> "ContainerConfig":
        """Get built-in default configuration values.

        Note: User identity and cwd are runtime context, not configuration.
        """
        return cls(
            # Auto-detect behaviors
            workdir="auto",  # Preserve relative position
            gosu_path="auto",  # Auto-detect bundled binary
            tty="auto",  # Auto-detect from stdin
            # Container settings with defaults
            image="ubuntu:latest",
            build=NOTSET,  # Image and build are mutually exclusive
            command="bash",
            container_name="ctenv-${project_dir|slug}-${pid}",
            sudo=False,
            runtime="docker",  # Default container runtime
            # Lists with empty defaults
            subpaths=[],  # Empty = mount project root; non-empty = mount only these
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
    if config.volumes is not NOTSET:
        updates["volumes"] = [resolve_relative_volume_spec(vol, base_dir) for vol in config.volumes]

    if config.subpaths is not NOTSET:
        updates["subpaths"] = [
            resolve_relative_subpath_spec(sp, base_dir) for sp in config.subpaths
        ]

    if config.gosu_path is not NOTSET:
        updates["gosu_path"] = resolve_relative_path(config.gosu_path, base_dir)

    if config.build is not NOTSET:
        # Resolve relative paths in build configuration
        build_updates = {}
        if config.build.dockerfile is not NOTSET:
            build_updates["dockerfile"] = resolve_relative_path(config.build.dockerfile, base_dir)
        if config.build.context is not NOTSET:
            build_updates["context"] = resolve_relative_path(config.build.context, base_dir)

        if build_updates:
            # Type: ignore because we know config.build is BuildConfig here due to NOTSET check
            updates["build"] = replace(config.build, **build_updates)  # type: ignore[type-var]

    # Return new ContainerConfig with only the changed fields
    return replace(config, **updates)


def validate_build_config(build_config: BuildConfig) -> None:
    """Validate build configuration for logical consistency.

    Raises:
        ValueError: If build configuration is invalid
    """
    # Check mutual exclusion of dockerfile and dockerfile_content
    dockerfile_set = build_config.dockerfile is not NOTSET and build_config.dockerfile is not None
    dockerfile_content_set = (
        build_config.dockerfile_content is not NOTSET
        and build_config.dockerfile_content is not None
    )

    if dockerfile_set and dockerfile_content_set:
        raise ValueError(
            "Cannot specify both 'dockerfile' and 'dockerfile_content' - they are mutually exclusive"
        )

    # Validate dockerfile_content is not empty if specified
    if dockerfile_content_set and not build_config.dockerfile_content.strip():
        raise ValueError("dockerfile_content cannot be empty")


def validate_container_config(config: ContainerConfig) -> None:
    """Validate container configuration for logical consistency.

    Raises:
        ValueError: If configuration is invalid
    """
    # Check mutual exclusion of image and build
    if config.image is not NOTSET and config.build is not NOTSET:
        raise ValueError("Cannot specify both 'image' and 'build' - they are mutually exclusive")

    # Validate build configuration if present
    if config.build is not NOTSET:
        validate_build_config(config.build)


def validate_config_project_target(project_target_str: str, config_path: Path) -> None:
    """Validate project_target from config file.

    project_target should be a simple path string (target path in container for project).

    Raises:
        ValueError: If project_target is empty or invalid
    """
    if not project_target_str or not project_target_str.strip():
        raise ValueError(f"In config file {config_path}: project_target cannot be empty")

    # Must be an absolute path
    if not project_target_str.startswith("/"):
        raise ValueError(
            f"In config file {config_path}: project_target must be an absolute path. "
            f"Got: '{project_target_str}'"
        )


def apply_build_defaults(config: ContainerConfig) -> ContainerConfig:
    """Apply build defaults when build is configured.

    Returns new ContainerConfig with build defaults applied if needed.
    """
    if config.build is NOTSET:
        return config

    # Start with builtin defaults
    build_defaults = BuildConfig.builtin_defaults()

    # Apply build defaults based on what's configured
    if config.build.dockerfile_content is not NOTSET:
        # When using dockerfile_content, don't default dockerfile
        build_defaults = replace(build_defaults, dockerfile=NOTSET)
    else:
        # When using dockerfile path, provide default dockerfile
        build_defaults = replace(build_defaults, dockerfile="Dockerfile")

    # Merge build config with defaults
    merged_build = merge_build_configs(build_defaults, config.build)

    # Clear image field if build is configured (build takes precedence)
    updates = {"build": merged_build}
    if config.image is not NOTSET:
        updates["image"] = NOTSET

    return replace(config, **updates)


def merge_build_configs(base: BuildConfig, override: BuildConfig) -> BuildConfig:
    """Merge two BuildConfig objects, with override taking precedence."""
    updates = {}

    for field_info in fields(override):
        override_value = getattr(override, field_info.name)
        if override_value is not NOTSET:
            updates[field_info.name] = override_value

    return replace(base, **updates)


@dataclass
class ConfigFile:
    """Represents a single configuration file with containers and defaults."""

    containers: Dict[str, ContainerConfig]
    defaults: Optional[ContainerConfig]
    path: Optional[Path]  # None for built-in defaults

    @classmethod
    def load(cls, config_path: Path, project_dir: Path) -> "ConfigFile":
        """Load configuration from a specific file.

        Relative paths in the config file are resolved relative to the
        config file's directory, not the project directory.
        """
        if not config_path.exists():
            raise ValueError(f"Config file not found: {config_path}")

        config_data = _load_config_file(config_path)

        # Use config file's parent directory for relative path resolution
        config_base_dir = config_path.parent.resolve()

        raw_containers = config_data.get("containers", {})
        raw_defaults = config_data.get("defaults")

        # Process defaults to ContainerConfig if present
        defaults_config = None
        if raw_defaults:
            defaults_config = ContainerConfig.from_dict(convert_notset_strings(raw_defaults))
            defaults_config._config_file_path = str(config_path.resolve())
            # Validate project_target if set
            if defaults_config.project_target is not NOTSET:
                validate_config_project_target(defaults_config.project_target, config_path)
            defaults_config = resolve_relative_paths_in_container_config(
                defaults_config, config_base_dir
            )

        # Process containers to ContainerConfig objects
        container_configs = {}
        for name, container_dict in raw_containers.items():
            container_config = ContainerConfig.from_dict(convert_notset_strings(container_dict))
            container_config._config_file_path = str(config_path.resolve())
            # Validate project_target if set
            if container_config.project_target is not NOTSET:
                validate_config_project_target(container_config.project_target, config_path)
            container_config = resolve_relative_paths_in_container_config(
                container_config, config_base_dir
            )
            container_configs[name] = container_config

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


def merge_container_configs(base: ContainerConfig, override: ContainerConfig) -> ContainerConfig:
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

    def get_default(self, overrides: Optional[ContainerConfig] = None) -> ContainerConfig:
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

        # Apply build defaults and validate
        result_config = apply_build_defaults(result_config)
        validate_container_config(result_config)

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

        # Apply build defaults and validate
        result_config = apply_build_defaults(result_config)
        validate_container_config(result_config)

        return result_config

    @classmethod
    def load(
        cls,
        project_dir: Path,
        explicit_config_files: Optional[List[Path]] = None,
        verbosity: Verbosity = Verbosity.NORMAL,
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
                    if verbosity >= Verbosity.VERBOSE:
                        print(f"Loading explicit config: {config_file}", file=sys.stderr)
                    loaded_config = ConfigFile.load(config_file, project_dir)
                    config_files.append(loaded_config)
                except Exception as e:
                    raise ValueError(f"Failed to load explicit config file {config_file}: {e}")

        # Project config (if no explicit configs)
        if not explicit_config_files:
            project_config_path = project_dir / ".ctenv.toml"
            if project_config_path.exists():
                if verbosity >= Verbosity.VERBOSE:
                    print(f"Loading project config: {project_config_path}", file=sys.stderr)
                config_files.append(ConfigFile.load(project_config_path, project_dir))

        # User config
        user_config_path = find_user_config()
        if user_config_path:
            if verbosity >= Verbosity.VERBOSE:
                print(f"Loading user config: {user_config_path}", file=sys.stderr)
            config_files.append(ConfigFile.load(user_config_path, project_dir))

        # Compute defaults (system defaults + first file defaults found)
        defaults = ContainerConfig.builtin_defaults()
        for config_file in config_files:
            if config_file.defaults:
                defaults = merge_container_configs(defaults, config_file.defaults)
                break  # Stop after first (= highest prio) [defaults] section found

        # Compute containers (higher priority completely replaces lower priority)
        containers = {}
        # Process in reverse order so higher priority wins
        for config_file in reversed(config_files):
            for name, container_config in config_file.containers.items():
                # Simply overwrite - no merging between config files
                containers[name] = container_config

        return cls(defaults=defaults, containers=containers)


def _substitute_variables(text: str, variables: Dict[str, str], environ: Dict[str, str]) -> str:
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
            # Convert to lowercase and replace colons/slashes with hyphens
            value = value.lower()
            value = value.replace(":", "-").replace("/", "-")
        elif filter_name is not None:
            raise ValueError(f"Unknown filter: {filter_name}")

        return value

    return re.sub(pattern, replace_match, text)


def _substitute_variables_in_container_config(
    config: ContainerConfig, runtime: RuntimeContext, environ: Dict[str, str]
) -> ContainerConfig:
    """Substitute template variables in all string fields of ContainerConfig."""
    # Define variables dictionary
    variables = {
        "image": config.image if config.image is not NOTSET else "",
        "user_home": runtime.user_home,
        "user_name": runtime.user_name,
        "project_dir": str(runtime.project_dir),
        "pid": str(runtime.pid),
    }

    def substitute_field(value):
        """Substitute variables in a field, handling NOTSET and different types."""
        if value is NOTSET:
            return NOTSET
        elif isinstance(value, str):
            return _substitute_variables(value, variables, environ)
        elif isinstance(value, list):
            return [
                _substitute_variables(item, variables, environ) if isinstance(item, str) else item
                for item in value
            ]
        elif isinstance(value, dict):
            return {
                key: _substitute_variables(val, variables, environ) if isinstance(val, str) else val
                for key, val in value.items()
            }
        elif isinstance(value, BuildConfig):
            # Handle BuildConfig by substituting its string fields
            build_updates = {}
            for field_info in fields(value):
                field_value = getattr(value, field_info.name)
                substituted_value = substitute_field(field_value)
                if substituted_value != field_value:
                    build_updates[field_info.name] = substituted_value
            return replace(value, **build_updates) if build_updates else value
        else:
            return value

    # Use replace() to create new instance with substituted fields
    updates = {}
    for field_info in fields(config):
        original_value = getattr(config, field_info.name)
        substituted_value = substitute_field(original_value)
        if substituted_value != original_value:
            updates[field_info.name] = substituted_value

    return replace(config, **updates)
