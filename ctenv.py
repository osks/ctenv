#!/usr/bin/env -S uv run -q --script
#
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

__version__ = "0.1"

import argparse
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
import tomllib
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any


def substitute_template_variables(text: str, variables: dict[str, str]) -> str:
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


def substitute_in_context(context_data: dict, variables: dict[str, str]) -> dict:
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


def get_current_user_info():
    """Get current user and group information."""
    user_info = pwd.getpwuid(os.getuid())
    group_info = grp.getgrgid(os.getgid())

    return {
        "user_name": user_info.pw_name,
        "user_id": user_info.pw_uid,
        "group_name": group_info.gr_name,
        "group_id": group_info.gr_gid,
        "user_home": user_info.pw_dir,
    }


def get_platform_specific_gosu_name() -> str:
    """Get platform-specific gosu binary name.

    Note: gosu only provides Linux binaries since containers run Linux
    regardless of the host OS.
    """
    machine = platform.machine().lower()

    # Map machine types to standard names
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = "amd64"  # Default fallback

    # Always use Linux binaries since containers run Linux
    return f"gosu-{arch}"


def find_gosu_binary(
    start_dir: Optional[Path] = None, explicit_path: Optional[str] = None
) -> Optional[Path]:
    """Find gosu binary using fallback strategy.

    Search order:
    1. explicit_path if provided
    2. Platform-specific binary in .ctenv directories
    3. Generic gosu in .ctenv directories
    4. System PATH (shutil.which)

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

    # Get platform-specific binary name
    platform_gosu = get_platform_specific_gosu_name()

    # Search for .ctenv/gosu using same discovery as config files
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    # Search upward for platform-specific gosu first, then generic
    while True:
        # Try platform-specific first
        ctenv_platform_gosu = current / ".ctenv" / platform_gosu
        if ctenv_platform_gosu.exists() and ctenv_platform_gosu.is_file():
            logging.debug(f"Found platform-specific gosu: {ctenv_platform_gosu}")
            return ctenv_platform_gosu

        # Fall back to generic gosu
        ctenv_gosu = current / ".ctenv" / "gosu"
        if ctenv_gosu.exists() and ctenv_gosu.is_file():
            logging.debug(f"Found gosu in project .ctenv: {ctenv_gosu}")
            return ctenv_gosu

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    # Check global .ctenv/gosu (platform-specific first)
    global_platform_gosu = Path.home() / ".ctenv" / platform_gosu
    if global_platform_gosu.exists() and global_platform_gosu.is_file():
        logging.debug(
            f"Found platform-specific gosu in global .ctenv: {global_platform_gosu}"
        )
        return global_platform_gosu

    global_gosu = Path.home() / ".ctenv" / "gosu"
    if global_gosu.exists() and global_gosu.is_file():
        logging.debug(f"Found gosu in global .ctenv: {global_gosu}")
        return global_gosu

    # Fall back to system PATH
    system_gosu = shutil.which("gosu")
    if system_gosu:
        gosu_path = Path(system_gosu)
        logging.debug(f"Found gosu in system PATH: {gosu_path}")
        return gosu_path

    logging.debug("No gosu binary found in .ctenv directories or PATH")
    return None


def find_all_config_files(
    start_dir: Optional[Path] = None,
) -> tuple[Optional[Path], Optional[Path]]:
    """Find all ctenv config files (global, project).

    Returns:
        tuple of (global_config_path, project_config_path)
        Either can be None if not found.
    """
    if start_dir is None:
        start_dir = Path.cwd()

    # Find global config
    global_config = Path.home() / ".ctenv" / "ctenv.toml"
    global_config_path = (
        global_config if (global_config.exists() and global_config.is_file()) else None
    )
    if global_config_path:
        logging.debug(f"Found global config: {global_config_path}")

    # Find project config (search upward)
    current = start_dir.resolve()
    project_config_path = None

    while True:
        config_path = current / ".ctenv" / "ctenv.toml"
        if config_path.exists() and config_path.is_file():
            project_config_path = config_path
            logging.debug(f"Found project config: {project_config_path}")
            break

        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent

    if not global_config_path and not project_config_path:
        logging.debug("No config files found")

    return global_config_path, project_config_path


def find_config_file(start_dir: Optional[Path] = None) -> Optional[Path]:
    """Find ctenv config file using git-style upward traversal.

    Kept for backward compatibility. Returns the primary config file to use.
    """
    global_config, project_config = find_all_config_files(start_dir)

    # Return project config if available, otherwise global
    return project_config or global_config


def load_config_file(config_path: Path) -> Dict[str, Any]:
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


def get_builtin_default_context() -> Dict[str, Any]:
    """Get the builtin 'default' context definition."""
    return {"image": "ubuntu:latest"}


@dataclass
class ConfigFile:
    """Represents file-based configuration with contexts."""

    contexts: Dict[str, Dict[str, Any]]
    source_files: list[Path]

    @classmethod
    def load(
        cls,
        explicit_config_file: Optional[Path] = None,
        start_dir: Optional[Path] = None,
    ) -> "ConfigFile":
        """Load configuration from files with builtin default context."""
        # Start with empty contexts
        merged_contexts = {}
        source_files = []

        if explicit_config_file:
            # Use only the explicit config file
            if not explicit_config_file.exists():
                raise ValueError(f"Config file not found: {explicit_config_file}")
            user_config = load_config_file(explicit_config_file)
            # Only extract contexts, ignore any [defaults] section
            merged_contexts.update(user_config.get("contexts", {}))
            source_files = [explicit_config_file]
            logging.debug(f"Loaded explicit config from {explicit_config_file}")
        else:
            # Auto-discover and merge global and project config files
            global_config_path, project_config_path = find_all_config_files(start_dir)

            # Load global config
            if global_config_path:
                global_config = load_config_file(global_config_path)
                merged_contexts.update(global_config.get("contexts", {}))
                source_files.append(global_config_path)
                logging.debug(f"Merged global config from {global_config_path}")

            # Overlay project config (contexts with same name override)
            if project_config_path:
                project_config = load_config_file(project_config_path)
                merged_contexts.update(project_config.get("contexts", {}))
                source_files.append(project_config_path)
                logging.debug(f"Merged project config from {project_config_path}")

        # Ensure builtin default context is available (user can override)
        builtin_default = get_builtin_default_context()
        if "default" in merged_contexts:
            # Merge user default with builtin (user takes precedence)
            final_default = builtin_default.copy()
            final_default.update(merged_contexts["default"])
            merged_contexts["default"] = final_default
            logging.debug("Merged user 'default' context with builtin default")
        else:
            merged_contexts["default"] = builtin_default
            logging.debug("Added builtin 'default' context")

        return cls(contexts=merged_contexts, source_files=source_files)

    def resolve_context(self, context: str) -> Dict[str, Any]:
        """Resolve configuration values for a specific context."""
        if context not in self.contexts:
            available = list(self.contexts.keys())
            raise ValueError(f"Unknown context '{context}'. Available: {available}")

        context_data = self.contexts[context].copy()

        # Prepare template variables
        variables = {
            "USER": getpass.getuser(),
            "image": context_data.get("image", ""),
        }

        # Apply templating
        resolved = substitute_in_context(context_data, variables)
        logging.debug(f"Resolved context '{context}' configuration with templating")
        return resolved


@dataclass
class ContainerConfig:
    """Resolved configuration for ctenv container operations."""

    # User identity (required)
    user_name: str
    user_id: int
    group_name: str
    group_id: int
    user_home: str

    # Paths (required)
    script_dir: Path
    working_dir: Path
    gosu_path: Path

    # Container settings with defaults
    image: str = "ubuntu:latest"
    command: str = "bash"
    container_name: Optional[str] = None

    # Mount points
    dir_mount: str = "/repo"
    gosu_mount: str = "/gosu"

    # Options
    env_vars: tuple[str, ...] = ()
    volumes: tuple[str, ...] = ()
    entrypoint_commands: tuple[str, ...] = ()
    ulimits: Dict[str, Any] = None
    sudo: bool = False
    network: Optional[str] = None
    tty: bool = False

    def get_container_name(self) -> str:
        """Generate container name based on working directory."""
        if self.container_name:
            return self.container_name
        # Replace / with - to make valid container name
        dir_id = str(self.working_dir).replace("/", "-")
        return f"ctenv-{dir_id}"

    @classmethod
    def from_cli_options(
        cls,
        context: Optional[str] = None,
        config_file: Optional[str] = None,
        **cli_options,
    ) -> "ContainerConfig":
        """Create ContainerConfig from CLI options, config files, and system defaults."""
        logging.debug("Creating ContainerConfig from CLI options")

        # Load file-based configuration
        try:
            explicit_config = Path(config_file) if config_file else None
            config_file_obj = ConfigFile.load(explicit_config_file=explicit_config)
        except Exception as e:
            raise ValueError(str(e)) from e

        # Resolve config values with context (context is never None now)
        if not context:
            context = "default"
        file_config = config_file_obj.resolve_context(context)

        # Get user info if not provided
        user_info = get_current_user_info()
        logging.debug(
            f"User info: {user_info['user_name']} (UID: {user_info['user_id']})"
        )

        # Get script directory
        script_dir = Path(__file__).parent.resolve()
        logging.debug(f"Script directory: {script_dir}")

        # Get working directory
        dir_param = cli_options.get("dir") or file_config.get("dir")
        working_dir = Path(dir_param) if dir_param else Path(os.getcwd())
        logging.debug(f"Working directory: {working_dir}")

        # Helper function to get value with precedence: CLI > config file > default
        def get_config_value(key: str, cli_key: str = None, default=None):
            cli_key = cli_key or key
            cli_value = cli_options.get(cli_key)
            if cli_value is not None:
                return cli_value
            file_value = file_config.get(key)
            if file_value is not None:
                return file_value
            return default

        # Discover gosu binary path
        gosu_path_override = get_config_value("gosu_path")
        gosu_binary = find_gosu_binary(
            start_dir=working_dir, explicit_path=gosu_path_override
        )
        if gosu_binary is None:
            platform_name = get_platform_specific_gosu_name()
            raise FileNotFoundError(
                f"gosu binary not found.\n\n"
                f"To fix this, either:\n\n"
                f"1. Run setup (recommended):\n"
                f"   ctenv setup\n\n"
                f"2. Download manually:\n"
                f"   mkdir -p ~/.ctenv\n"
                f"   wget -O ~/.ctenv/{platform_name} https://github.com/tianon/gosu/releases/latest/download/{platform_name}\n"
                f"   chmod +x ~/.ctenv/{platform_name}\n\n"
                f"3. Install from package manager:\n"
                f"   Ubuntu/Debian:  sudo apt install gosu\n"
                f"   macOS:          brew install gosu"
            )
        logging.debug(f"Found gosu binary: {gosu_binary}")

        return cls(
            # User identity
            user_name=user_info["user_name"],
            user_id=user_info["user_id"],
            group_name=user_info["group_name"],
            group_id=user_info["group_id"],
            user_home=user_info["user_home"],
            # Paths
            script_dir=script_dir,
            working_dir=working_dir,
            gosu_path=gosu_binary,
            # Container settings (CLI > config file > defaults)
            image=get_config_value("image", default="ubuntu:latest"),
            command=get_config_value("command", default="bash"),
            container_name=get_config_value("container_name"),
            # Options (CLI > config file > defaults)
            env_vars=tuple(get_config_value("env", "env_vars", [])),
            volumes=tuple(get_config_value("volumes", default=[])),
            entrypoint_commands=tuple(
                list(get_config_value("entrypoint_commands", default=[]))
                + list(cli_options.get("entrypoint_cmd", []))
            ),
            ulimits=get_config_value("ulimits"),
            sudo=get_config_value("sudo", default=False),
            network=get_config_value("network"),
            tty=cli_options.get(
                "tty", False
            ),  # TTY is determined at runtime, not from config
        )


def build_entrypoint_script(
    config: ContainerConfig, chown_paths: list[str] = None, verbose: bool = False
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
            chown_commands += f'log "Checking chown volume: {path}"\n'
            chown_commands += f'if [ -d "{path}" ]; then\n'
            chown_commands += f'    log "Fixing ownership of volume: {path}"\n'
            chown_commands += f'    chown -R "$USER_ID:$GROUP_ID" "{path}"\n'
            chown_commands += "else\n"
            chown_commands += f'    log "Chown volume does not exist: {path}"\n'
            chown_commands += "fi\n"
    else:
        chown_commands = """
# No volumes require ownership fixes
log "No chown-enabled volumes configured"
"""

    # Build entrypoint commands section
    entrypoint_commands = ""
    if config.entrypoint_commands:
        entrypoint_commands = """
# Execute entrypoint commands
log "Executing entrypoint commands"
"""
        for cmd in config.entrypoint_commands:
            # Escape quotes in the command
            escaped_cmd = cmd.replace('"', '\\"')
            entrypoint_commands += (
                f'log "Executing entrypoint command: {escaped_cmd}"\n'
            )
            entrypoint_commands += f"{cmd}\n"
    else:
        entrypoint_commands = """
# No entrypoint commands configured
log "No entrypoint commands to execute"
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
{entrypoint_commands}

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
    def parse_volumes(volumes: tuple[str, ...]) -> tuple[list[str], list[str]]:
        """Parse volume strings and extract chown paths.
        
        Returns:
            tuple of (processed_volumes, chown_paths)
        """
        chown_paths = []
        processed_volumes = []

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
        config: ContainerConfig, script_path: str, verbose: bool = False
    ) -> list[str]:
        """Build Docker run arguments with provided script path."""
        logging.debug("Building Docker run arguments")

        args = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--platform=linux/amd64",
            f"--name={config.get_container_name()}",
        ]

        # Parse volume options 
        processed_volumes, chown_paths = ContainerRunner.parse_volumes(config.volumes)

        # Volume mounts
        volume_args = [
            f"--volume={config.working_dir}:{config.dir_mount}:z,rw",
            f"--volume={config.gosu_path}:{config.gosu_mount}:z,ro",
            f"--volume={script_path}:/entrypoint.sh:z,ro",
            f"--workdir={config.dir_mount}",
        ]
        args.extend(volume_args)

        logging.debug("Volume mounts:")
        logging.debug(f"  Working dir: {config.working_dir} -> {config.dir_mount}")
        logging.debug(f"  Gosu binary: {config.gosu_path} -> {config.gosu_mount}")
        logging.debug(f"  Entrypoint script: {script_path} -> /entrypoint.sh")

        # Additional volume mounts
        if processed_volumes:
            logging.debug("Additional volume mounts:")
            for volume in processed_volumes:
                args.extend([f"--volume={volume}:z"])
                logging.debug(f"  {volume}")

            if chown_paths:
                logging.debug("Volumes with chown enabled:")
                for path in chown_paths:
                    logging.debug(f"  {path}")

        # Environment variables
        if config.env_vars:
            logging.debug("Environment variables:")
            for env_var in config.env_vars:
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
        
        # Create temporary script file
        script_fd, script_path = tempfile.mkstemp(suffix=".sh", text=True)
        logging.debug(f"Created temporary entrypoint script: {script_path}")
        
        try:
            with os.fdopen(script_fd, "w") as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)
            
            # Build Docker arguments with known script path
            docker_args = ContainerRunner.build_run_args(config, script_path, verbose)

            logging.debug(f"Executing Docker command: {' '.join(docker_args)}")

            # Execute Docker command or print for dry-run
            if dry_run:
                # Print the command that would be executed
                print(" ".join(docker_args))
                # Return a mock successful result
                result = subprocess.CompletedProcess(docker_args, 0)
                logging.debug("Dry-run mode: Docker command printed, not executed")
                return result
            else:
                result = subprocess.run(docker_args, check=False)
                if result.returncode != 0:
                    logging.debug(f"Container exited with code: {result.returncode}")
                return result
        except subprocess.CalledProcessError as e:
            logging.error(f"Container execution failed: {e}")
            raise RuntimeError(f"Container execution failed: {e}")
        finally:
            # Always clean up temporary script file
            try:
                os.unlink(script_path)
                logging.debug(f"Cleaned up temporary script: {script_path}")
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

    # Use "default" context if none specified
    if not context:
        context = "default"

    # Create config from CLI options and discovered configuration
    try:
        config = ContainerConfig.from_cli_options(
            context=context,
            config_file=args.config,
            image=args.image,
            command=" ".join(command),
            dir=args.dir,
            env_vars=args.env or [],
            volumes=args.volume or [],
            sudo=args.sudo,
            network=args.network,
            gosu_path=args.gosu_path,
            entrypoint_cmd=args.entrypoint_cmd or [],
            tty=sys.stdin.isatty(),
        )
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        logging.debug("Configuration:")
        logging.debug(f"  Image: {config.image}")
        logging.debug(f"  Command: {config.command}")
        logging.debug(f"  User: {config.user_name} (UID: {config.user_id})")
        logging.debug(f"  Group: {config.group_name} (GID: {config.group_id})")
        logging.debug(f"  Working directory: {config.working_dir}")
        logging.debug(f"  Container name: {config.get_container_name()}")
        if config.env_vars:
            logging.debug(f"  Environment variables: {config.env_vars}")
        if config.volumes:
            logging.debug(f"  Additional volumes: {config.volumes}")
        logging.debug(f"  Network: {config.network or 'none'}")
        logging.debug(f"  Sudo: {config.sudo}")
        logging.debug(f"  TTY: {config.tty}")
        logging.debug(f"  Gosu binary: {config.gosu_path}")

    if not quiet:
        print("[ctenv] run", file=sys.stderr)

    # Execute container (or dry-run)
    try:
        result = ContainerRunner.run_container(config, verbose, dry_run=args.dry_run)
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
    config = args.config

    try:
        # Load file-based configuration
        explicit_config = Path(config) if config else None
        config_file = ConfigFile.load(explicit_config_file=explicit_config)

        if context:
            # Show specific context
            if context not in config_file.contexts:
                available = list(config_file.contexts.keys())
                print(
                    f"Context '{context}' not found. Available: {available}",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Show which config files are being used
            if len(config_file.source_files) == 0:
                print(f"Context '{context}' (builtin default only):")
            elif len(config_file.source_files) == 1:
                print(f"Context '{context}' from {config_file.source_files[0]}:")
            else:
                print(f"Context '{context}' from merged configs:")
                for source_file in config_file.source_files:
                    print(f"  {source_file}")

            # Show context configuration with templating applied
            resolved_context = config_file.resolve_context(context)
            for key, value in resolved_context.items():
                print(f"  {key}: {value}")
        else:
            # Show all configuration
            print("Configuration:")

            # Show which config files are being used
            if len(config_file.source_files) == 0:
                print("\nUsing builtin contexts only")
            elif len(config_file.source_files) == 1:
                print(f"\nUsing config file: {config_file.source_files[0]}")
            else:
                print("\nUsing merged config files:")
                for source_file in config_file.source_files:
                    print(f"  {source_file}")

            # Show contexts (there's always at least the default context)
            if config_file.contexts:
                print("\nContexts:")
                for ctx_name in sorted(config_file.contexts.keys()):
                    print(f"  {ctx_name}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_path(args):
    """Show path to configuration file being used."""
    config = args.config

    if config:
        config_path = Path(config)
        if config_path.exists():
            print(str(config_path.resolve()))
        else:
            print(f"Config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
    else:
        discovered_config = find_config_file()
        if discovered_config:
            print(str(discovered_config))
        else:
            print("No configuration file found", file=sys.stderr)
            sys.exit(1)


def cmd_contexts(args):
    """List available contexts."""
    config = args.config

    try:
        # Load file-based configuration
        explicit_config = Path(config) if config else None
        config_file = ConfigFile.load(explicit_config_file=explicit_config)

        if config_file.contexts:
            if config:
                print(f"Contexts from {config}:")
            else:
                print("Available contexts:")
            for ctx_name in sorted(config_file.contexts.keys()):
                print(f"  {ctx_name}")
        else:
            # This should never happen since we always have at least builtin default
            print("No contexts available")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_setup(args):
    """Download gosu binaries for all platforms."""
    force = args.force

    print("🔧 Setting up ctenv...")
    print()

    # Ensure .ctenv directory exists
    ctenv_dir = Path.home() / ".ctenv"
    ctenv_dir.mkdir(exist_ok=True)

    # Platform binaries to download
    # Note: Only Linux binaries are available since containers run Linux
    binaries = [
        ("gosu-amd64", "linux/amd64"),
        ("gosu-arm64", "linux/arm64"),
    ]

    print("Downloading gosu binaries for all platforms...")

    success_count = 0

    for binary_name, platform_desc in binaries:
        binary_path = ctenv_dir / binary_name

        # Skip if already exists and not forcing
        if binary_path.exists() and not force:
            print(f"✓ {binary_name} already exists ({platform_desc})")
            success_count += 1
            continue

        # Download the binary
        url = f"https://github.com/tianon/gosu/releases/latest/download/{binary_name}"

        try:
            print(f"  Downloading {binary_name}...", end="")
            urllib.request.urlretrieve(url, binary_path)
            binary_path.chmod(0o755)
            print(f" ✓ Downloaded {binary_name} ({platform_desc})")
            success_count += 1
        except urllib.error.URLError as e:
            print(f" ✗ Failed to download {binary_name}: {e}")
        except Exception as e:
            print(f" ✗ Error downloading {binary_name}: {e}")

    print()

    if success_count == len(binaries):
        print("ctenv is ready to use! Try: ctenv run -- echo hello")
    elif success_count > 0:
        print(
            f"Setup partially complete ({success_count}/{len(binaries)} binaries available)"
        )
        print("ctenv should work for most use cases.")
    else:
        print("Setup failed. Please check your internet connection and try again.")
        sys.exit(1)


def create_parser():
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog="ctenv",
        description="ctenv is a tool for running a program in a container as current user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    ctenv run --entrypoint-cmd "npm install" --entrypoint-cmd "npm run build" # Run extra commands before main command

Note: Use '--' to separate commands from context/options.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    run_parser.add_argument(
        "context", nargs="?", help="Context to use (default: 'default')"
    )
    run_parser.add_argument("command", nargs="*", help="Command to run (default: bash)")
    run_parser.add_argument(
        "--image", help="Container image to use (default: ubuntu:latest)"
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show Docker command without running container",
    )
    run_parser.add_argument("--config", help="Path to configuration file")
    run_parser.add_argument(
        "--env",
        action="append",
        help="Set environment variable (NAME=VALUE) or pass from host (NAME)",
    )
    run_parser.add_argument(
        "--volume",
        action="append",
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
        "--dir", help="Directory to mount as workdir (default: current directory)"
    )
    run_parser.add_argument(
        "--gosu-path",
        help="Path to gosu binary (default: auto-discover from PATH or .ctenv/gosu)",
    )
    run_parser.add_argument(
        "--entrypoint-cmd",
        action="append",
        help="Add extra command to run before main command (can be used multiple times)",
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
    config_show_parser.add_argument("--config", help="Path to configuration file")

    # config path
    config_path_parser = config_subparsers.add_parser(
        "path", help="Show path to configuration file being used"
    )
    config_path_parser.add_argument("--config", help="Path to configuration file")

    # contexts command
    contexts_parser = subparsers.add_parser("contexts", help="List available contexts")
    contexts_parser.add_argument("--config", help="Path to configuration file")

    # setup command
    setup_parser = subparsers.add_parser(
        "setup", help="Download gosu binaries for all platforms"
    )
    setup_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download gosu binaries even if they exist",
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
        elif args.config_command == "path":
            cmd_config_path(args)
        else:
            parser.parse_args(["config", "--help"])
    elif args.subcommand == "contexts":
        cmd_contexts(args)
    elif args.subcommand == "setup":
        cmd_setup(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
