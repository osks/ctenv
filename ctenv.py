#!/usr/bin/env -S uv run -q --script
#
# /// script
# requires-python = ">=3.11"
# dependencies = ["click"]
# ///

__version__ = "0.1"

import os
import pwd
import grp
import subprocess
import sys
import shutil
import logging
import tomllib
import re
import getpass
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

import click


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
    """Get platform-specific gosu binary name."""
    import platform

    system = platform.system().lower()
    machine = platform.machine().lower()

    # Map machine types to standard names
    if machine in ("x86_64", "amd64"):
        arch = "amd64"
    elif machine in ("aarch64", "arm64"):
        arch = "arm64"
    else:
        arch = "amd64"  # Default fallback

    if system == "darwin":
        return f"gosu-darwin-{arch}"
    else:
        # Linux containers regardless of host OS
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
    global_config = Path.home() / ".ctenv" / "config.toml"
    global_config_path = (
        global_config if (global_config.exists() and global_config.is_file()) else None
    )
    if global_config_path:
        logging.debug(f"Found global config: {global_config_path}")

    # Find project config (search upward)
    current = start_dir.resolve()
    project_config_path = None

    while True:
        config_path = current / ".ctenv" / "config.toml"
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
        explicit_config = Path(config_file) if config_file else None
        config_file_obj = ConfigFile.load(explicit_config_file=explicit_config)

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
                get_config_value("entrypoint_commands", default=[])
            ),
            ulimits=get_config_value("ulimits"),
            sudo=get_config_value("sudo", default=False),
            network=get_config_value("network"),
            tty=cli_options.get(
                "tty", False
            ),  # TTY is determined at runtime, not from config
        )


def build_entrypoint_script(
    config: ContainerConfig, chown_paths: list[str] = None
) -> str:
    """Generate bash script for container entrypoint."""
    chown_paths = chown_paths or []

    # Build chown commands for volumes marked with :chown
    chown_commands = ""
    if chown_paths:
        chown_commands = "\n# Fix ownership of chown-enabled volumes\n"
        for path in chown_paths:
            chown_commands += f'if [ -d "{path}" ]; then\n'
            chown_commands += (
                f'    chown -R {config.user_id}:{config.group_id} "{path}"\n'
            )
            chown_commands += "fi\n"

    # Build entrypoint commands section
    entrypoint_commands = ""
    if config.entrypoint_commands:
        entrypoint_commands = "\n# Execute entrypoint commands\n"
        for cmd in config.entrypoint_commands:
            # Escape quotes in the command
            escaped_cmd = cmd.replace('"', '\\"')
            entrypoint_commands += f"echo 'Executing: {escaped_cmd}'\n"
            entrypoint_commands += f"{cmd}\n"

    script = f"""#!/bin/bash
set -e

# Create group if needed
if getent group {config.group_id} >/dev/null 2>&1; then
    GROUP_NAME=$(getent group {config.group_id} | cut -d: -f1)
else
    groupadd -g {config.group_id} {config.group_name}
    GROUP_NAME={config.group_name}
fi

# Create user if needed
if ! getent passwd {config.user_name} >/dev/null 2>&1; then
    useradd --no-create-home --home-dir {config.user_home} \\
        --shell /bin/bash -u {config.user_id} -g {config.group_id} \\
        -o -c "" {config.user_name}
fi

# Setup home directory
export HOME={config.user_home}
if [ ! -d "$HOME" ]; then
    mkdir -p "$HOME"
    chown {config.user_id}:{config.group_id} "$HOME"
fi

# Set ownership of home directory (non-recursive)
chown {config.user_name} "$HOME"{chown_commands}{entrypoint_commands}

# Setup sudo if requested
{
        f'''
# Install sudo and configure passwordless access
if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq sudo
elif command -v yum >/dev/null 2>&1; then
    yum install -y -q sudo
elif command -v apk >/dev/null 2>&1; then
    apk add --no-cache sudo
fi

# Add user to sudoers
echo "{config.user_name} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
'''
        if config.sudo
        else "# Sudo not requested"
    }

# Set environment
export PS1="[ctenv] $ "

# Execute command as user
exec {config.gosu_mount} {config.user_name} {config.command}
"""
    return script


class ContainerRunner:
    """Manages Docker container operations."""

    @staticmethod
    def build_run_args(config: ContainerConfig) -> tuple[list, str]:
        """Build Docker run arguments. Returns (args, script_path) for cleanup."""
        import tempfile

        logging.debug("Building Docker run arguments")

        args = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--platform=linux/amd64",
            f"--name={config.get_container_name()}",
        ]

        # Parse volume options and track chown paths
        chown_paths = []
        processed_volumes = []

        for volume in config.volumes:
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

        # Generate and write entrypoint script to temporary file
        entrypoint_script = build_entrypoint_script(config, chown_paths)
        script_fd, script_path = tempfile.mkstemp(suffix=".sh", text=True)
        logging.debug(f"Created temporary entrypoint script: {script_path}")
        try:
            with os.fdopen(script_fd, "w") as f:
                f.write(entrypoint_script)
            os.chmod(script_path, 0o755)

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

            return args, script_path
        except Exception:
            # Cleanup on error
            try:
                os.unlink(script_path)
            except OSError:
                pass
            raise

    @staticmethod
    def run_container(config: ContainerConfig) -> subprocess.CompletedProcess:
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

        # Build Docker arguments
        docker_args, script_path = ContainerRunner.build_run_args(config)

        logging.debug(f"Executing Docker command: {' '.join(docker_args)}")

        # Execute Docker command
        try:
            result = subprocess.run(docker_args, check=False)
            if result.returncode != 0:
                logging.debug(f"Container exited with code: {result.returncode}")
            return result
        except subprocess.CalledProcessError as e:
            logging.error(f"Container execution failed: {e}")
            raise RuntimeError(f"Container execution failed: {e}")
        finally:
            # Clean up temporary script file
            if script_path:
                try:
                    os.unlink(script_path)
                    logging.debug(f"Cleaned up temporary script: {script_path}")
                except OSError:
                    pass


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--quiet", "-q", is_flag=True, help="Suppress non-essential output")
@click.pass_context
def cli(ctx, verbose, quiet):
    """ctenv is a tool for running a program in a container as current user"""
    # Store verbosity in context for subcommands to access
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    # Configure logging to stderr to keep stdout clean for command output
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
            stream=sys.stderr,
        )
    elif quiet:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)


@cli.command()
@click.argument("context", required=False)
@click.argument("command_args", nargs=-1)
@click.option("--image", help="Container image to use (default: ubuntu:latest)")
@click.option("--debug", is_flag=True, help="Show configuration details")
@click.option("--config", help="Path to configuration file")
@click.option(
    "--env",
    multiple=True,
    help="Set environment variable (NAME=VALUE) or pass from host (NAME)",
)
@click.option(
    "--volume", multiple=True, help="Mount additional volume (HOST:CONTAINER format)"
)
@click.option(
    "--sudo", is_flag=True, help="Add user to sudoers with NOPASSWD inside container"
)
@click.option(
    "--network", help="Enable container networking (default: disabled for security)"
)
@click.option(
    "--dir", help="Directory to mount as workdir (default: current directory)"
)
@click.option(
    "--gosu-path",
    help="Path to gosu binary (default: auto-discover from PATH or .ctenv/gosu)",
)
@click.pass_context
def run(
    ctx,
    context,
    command_args,
    image,
    debug,
    config,
    env,
    volume,
    sudo,
    network,
    dir,
    gosu_path,
):
    """Run command in container

    Examples:

        ctenv run                          # Interactive bash with defaults

        ctenv run dev                      # Use 'dev' context with default command

        ctenv run dev -- npm test         # Use 'dev' context, run npm test

        ctenv run -- ls -la               # Use defaults, run ls -la

        ctenv run --image alpine dev      # Override image, use dev context

    Note: Use '--' to separate commands from context/options.
    """
    verbose = ctx.obj.get("verbose", False)
    quiet = ctx.obj.get("quiet", False)

    # Simple Click-style parsing - this allows some ambiguous cases but is standard
    if command_args:
        # Command specified
        command = command_args
    else:
        # No command, default to bash
        command = ("bash",)

    # Use "default" context if none specified
    if not context:
        context = "default"

    # Validate context (including "default" which should always be available)
    try:
        config_file = ConfigFile.load()
        if context not in config_file.contexts:
            available = list(config_file.contexts.keys())
            click.echo(
                f"Error: Context '{context}' not found. Available: {available}",
                err=True,
            )
            sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)

    # Context validation was already done during parsing above

    # Create config from CLI options and discovered configuration
    try:
        config = ContainerConfig.from_cli_options(
            context=context,
            config_file=config,
            image=image,
            command=" ".join(command),
            dir=dir,
            env_vars=env,
            volumes=volume,
            sudo=sudo,
            network=network,
            gosu_path=gosu_path,
            tty=sys.stdin.isatty(),
        )
    except ValueError as e:
        click.echo(f"Configuration error: {e}", err=True)
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
        click.echo("[ctenv] run", err=True)

    if debug:
        click.echo(f"Image: {config.image}", err=True)
        click.echo(f"Command: {config.command}", err=True)
        click.echo("\nConfiguration:", err=True)
        click.echo(f"  User: {config.user_name} (UID: {config.user_id})", err=True)
        click.echo(f"  Group: {config.group_name} (GID: {config.group_id})", err=True)
        click.echo(f"  Home: {config.user_home}", err=True)
        click.echo(f"  Script dir: {config.script_dir}", err=True)
        click.echo(f"  Working dir: {config.working_dir}", err=True)
        click.echo(f"  Container name: {config.get_container_name()}", err=True)

        # Show what Docker command would be executed
        docker_args, script_path = ContainerRunner.build_run_args(config)
        click.echo("\nDocker command:", err=True)
        click.echo(f"  {' '.join(docker_args)}", err=True)
        # Clean up temp script file from debug mode
        try:
            os.unlink(script_path)
        except OSError:
            pass
        return

    # Execute container
    try:
        result = ContainerRunner.run_container(config)
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def config():
    """Configuration management commands"""
    pass


@config.command()
@click.argument("context", required=False)
@click.option("--config", help="Path to configuration file")
def show(context, config):
    """Show configuration or context details"""
    try:
        # Load file-based configuration
        explicit_config = Path(config) if config else None
        config_file = ConfigFile.load(explicit_config_file=explicit_config)

        if context:
            # Show specific context
            if context not in config_file.contexts:
                available = list(config_file.contexts.keys())
                click.echo(
                    f"Context '{context}' not found. Available: {available}", err=True
                )
                sys.exit(1)

            # Show which config files are being used
            if len(config_file.source_files) == 0:
                click.echo(f"Context '{context}' (builtin default only):")
            elif len(config_file.source_files) == 1:
                click.echo(f"Context '{context}' from {config_file.source_files[0]}:")
            else:
                click.echo(f"Context '{context}' from merged configs:")
                for source_file in config_file.source_files:
                    click.echo(f"  {source_file}")

            # Show context configuration with templating applied
            resolved_context = config_file.resolve_context(context)
            for key, value in resolved_context.items():
                click.echo(f"  {key}: {value}")
        else:
            # Show all configuration
            click.echo("Configuration:")

            # Show which config files are being used
            if len(config_file.source_files) == 0:
                click.echo("\nUsing builtin contexts only")
            elif len(config_file.source_files) == 1:
                click.echo(f"\nUsing config file: {config_file.source_files[0]}")
            else:
                click.echo("\nUsing merged config files:")
                for source_file in config_file.source_files:
                    click.echo(f"  {source_file}")

            # Show contexts (there's always at least the default context)
            if config_file.contexts:
                click.echo("\nContexts:")
                for ctx_name in sorted(config_file.contexts.keys()):
                    click.echo(f"  {ctx_name}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@config.command()
@click.option("--config", help="Path to configuration file")
def path(config):
    """Show path to configuration file being used"""
    if config:
        config_path = Path(config)
        if config_path.exists():
            click.echo(str(config_path.resolve()))
        else:
            click.echo(f"Config file not found: {config_path}", err=True)
            sys.exit(1)
    else:
        discovered_config = find_config_file()
        if discovered_config:
            click.echo(str(discovered_config))
        else:
            click.echo("No configuration file found", err=True)
            sys.exit(1)


@cli.command()
@click.option("--config", help="Path to configuration file")
def contexts(config):
    """List available contexts"""
    try:
        # Load file-based configuration
        explicit_config = Path(config) if config else None
        config_file = ConfigFile.load(explicit_config_file=explicit_config)

        if config_file.contexts:
            if config:
                click.echo(f"Contexts from {config}:")
            else:
                click.echo("Available contexts:")
            for ctx_name in sorted(config_file.contexts.keys()):
                click.echo(f"  {ctx_name}")
        else:
            # This should never happen since we always have at least builtin default
            click.echo("No contexts available")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--force", is_flag=True, help="Re-download gosu binaries even if they exist"
)
def setup(force):
    """Download gosu binaries for all platforms"""
    import urllib.request
    import urllib.error

    click.echo("🔧 Setting up ctenv...")
    click.echo()

    # Ensure .ctenv directory exists
    ctenv_dir = Path.home() / ".ctenv"
    ctenv_dir.mkdir(exist_ok=True)

    # Platform binaries to download
    binaries = [
        ("gosu-amd64", "linux/amd64"),
        ("gosu-arm64", "linux/arm64"),
        ("gosu-darwin-amd64", "macOS/amd64"),
        ("gosu-darwin-arm64", "macOS/arm64"),
    ]

    click.echo("Downloading gosu binaries for all platforms...")

    success_count = 0

    for binary_name, platform_desc in binaries:
        binary_path = ctenv_dir / binary_name

        # Skip if already exists and not forcing
        if binary_path.exists() and not force:
            click.echo(f"✓ {binary_name} already exists ({platform_desc})")
            success_count += 1
            continue

        # Download the binary
        url = f"https://github.com/tianon/gosu/releases/latest/download/{binary_name}"

        try:
            click.echo(f"  Downloading {binary_name}...", nl=False)
            urllib.request.urlretrieve(url, binary_path)
            binary_path.chmod(0o755)
            click.echo(f" ✓ Downloaded {binary_name} ({platform_desc})")
            success_count += 1
        except urllib.error.URLError as e:
            click.echo(f" ✗ Failed to download {binary_name}: {e}")
        except Exception as e:
            click.echo(f" ✗ Error downloading {binary_name}: {e}")

    click.echo()

    if success_count == len(binaries):
        click.echo("ctenv is ready to use! Try: ctenv run -- echo hello")
    elif success_count > 0:
        click.echo(
            f"Setup partially complete ({success_count}/{len(binaries)} binaries available)"
        )
        click.echo("ctenv should work for most use cases.")
    else:
        click.echo("Setup failed. Please check your internet connection and try again.")
        sys.exit(1)


if __name__ == "__main__":
    cli()
