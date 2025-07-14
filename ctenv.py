#!/usr/bin/env -S uv run --script
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
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any

import click


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


def find_gosu_binary(start_dir: Optional[Path] = None, explicit_path: Optional[str] = None) -> Optional[Path]:
    """Find gosu binary using fallback strategy.
    
    Search order:
    1. explicit_path if provided
    2. System PATH (shutil.which)
    3. .ctenv directory (project-local)
    4. Global .ctenv directory
    
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
    
    # Check system PATH first
    system_gosu = shutil.which("gosu")
    if system_gosu:
        gosu_path = Path(system_gosu)
        logging.debug(f"Found gosu in system PATH: {gosu_path}")
        return gosu_path
    
    # Search for .ctenv/gosu using same discovery as config files
    if start_dir is None:
        start_dir = Path.cwd()
    
    current = start_dir.resolve()
    
    # Search upward for .ctenv/gosu
    while True:
        ctenv_gosu = current / ".ctenv" / "gosu"
        if ctenv_gosu.exists() and ctenv_gosu.is_file():
            logging.debug(f"Found gosu in project .ctenv: {ctenv_gosu}")
            return ctenv_gosu
        
        parent = current.parent
        if parent == current:  # Reached filesystem root
            break
        current = parent
    
    # Fall back to global .ctenv/gosu
    global_gosu = Path.home() / ".ctenv" / "gosu"
    if global_gosu.exists() and global_gosu.is_file():
        logging.debug(f"Found gosu in global .ctenv: {global_gosu}")
        return global_gosu
    
    logging.debug("No gosu binary found in PATH or .ctenv directories")
    return None


def find_all_config_files(start_dir: Optional[Path] = None) -> tuple[Optional[Path], Optional[Path]]:
    """Find all ctenv config files (global, project).
    
    Returns:
        tuple of (global_config_path, project_config_path)
        Either can be None if not found.
    """
    if start_dir is None:
        start_dir = Path.cwd()
    
    # Find global config
    global_config = Path.home() / ".ctenv" / "config.toml"
    global_config_path = global_config if (global_config.exists() and global_config.is_file()) else None
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


def get_builtin_defaults() -> Dict[str, Any]:
    """Get the built-in default values used by ctenv."""
    return {
        "image": "ubuntu:latest",
        "command": "bash",
        "container_name": None,
        "env": [],
        "volumes": [],
        "sudo": False,
        "network": None,  # None means --network=none for security
        "gosu_path": None,  # None means auto-discovery (resolved during Config creation)
    }


def merge_config_data(global_config: Dict[str, Any], project_config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge global and project config data.
    
    Project config takes precedence over global config.
    Contexts are merged (project contexts can override global contexts with same name).
    """
    merged = global_config.copy()
    
    # Merge defaults
    if "defaults" in project_config:
        if "defaults" not in merged:
            merged["defaults"] = {}
        merged["defaults"].update(project_config["defaults"])
        logging.debug("Merged project defaults over global defaults")
    
    # Merge contexts
    if "contexts" in project_config:
        if "contexts" not in merged:
            merged["contexts"] = {}
        merged["contexts"].update(project_config["contexts"])
        logging.debug("Merged project contexts over global contexts")
    
    return merged


def load_merged_config(start_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load and merge global and project config files."""
    global_config_path, project_config_path = find_all_config_files(start_dir)
    
    merged_config = {}
    
    # Load global config first
    if global_config_path:
        global_config = load_config_file(global_config_path)
        merged_config = global_config
        logging.debug(f"Loaded global config from {global_config_path}")
    
    # Overlay project config
    if project_config_path:
        project_config = load_config_file(project_config_path)
        if merged_config:
            merged_config = merge_config_data(merged_config, project_config)
            logging.debug(f"Merged project config from {project_config_path}")
        else:
            merged_config = project_config
            logging.debug(f"Loaded project config from {project_config_path}")
    
    return merged_config


def resolve_config_values(config_data: Dict[str, Any], context: Optional[str] = None) -> Dict[str, Any]:
    """Resolve configuration values from defaults and context."""
    # Start with defaults
    resolved = config_data.get("defaults", {}).copy()
    
    # Apply context if specified
    if context:
        contexts = config_data.get("contexts", {})
        if context not in contexts:
            available = list(contexts.keys())
            raise ValueError(f"Unknown context '{context}'. Available: {available}")
        
        context_config = contexts[context]
        resolved.update(context_config)
        logging.debug(f"Applied context '{context}' configuration")
    
    return resolved


@dataclass
class Config:
    """Configuration for ctenv container operations."""
    
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
    sudo: bool = False
    network: Optional[str] = None
    tty: bool = False
    
    @classmethod
    def from_cli_options(cls, context: Optional[str] = None, config_file: Optional[str] = None, **cli_options) -> "Config":
        """Create Config from CLI options, config files, and system defaults."""
        logging.debug("Creating Config from CLI options")
        
        # Load configuration file(s)
        config_data = {}
        if config_file:
            # Explicit config file specified
            config_path = Path(config_file)
            if not config_path.exists():
                raise ValueError(f"Config file not found: {config_path}")
            config_data = load_config_file(config_path)
        else:
            # Discover and merge config files (global + project)
            config_data = load_merged_config()
        
        # Resolve config values with context
        file_config = resolve_config_values(config_data, context) if config_data else {}
        
        # Get user info if not provided
        user_info = get_current_user_info()
        logging.debug(f"User info: {user_info['user_name']} (UID: {user_info['user_id']})")
        
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
            start_dir=working_dir,
            explicit_path=gosu_path_override
        )
        if gosu_binary is None:
            raise FileNotFoundError(
                "gosu binary not found. Please install gosu in your PATH, "
                "place it in .ctenv/gosu, or specify path with --gosu-path option."
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
            sudo=get_config_value("sudo", default=False),
            network=get_config_value("network"),
            tty=cli_options.get("tty", False),  # TTY is determined at runtime, not from config
        )
    
    
    def get_container_name(self) -> str:
        """Generate container name based on working directory."""
        if self.container_name:
            return self.container_name
        # Replace / with - to make valid container name  
        dir_id = str(self.working_dir).replace("/", "-")
        return f"ctenv-{dir_id}"


def build_entrypoint_script(config: Config) -> str:
    """Generate bash script for container entrypoint."""
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
chown {config.user_name} "$HOME"

# Setup sudo if requested
{f'''
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
''' if config.sudo else "# Sudo not requested"}

# Set environment
export PS1="[ctenv] $ "

# Execute command as user
exec {config.gosu_mount} {config.user_name} {config.command}
"""
    return script


class ContainerRunner:
    """Manages Docker container operations."""

    @staticmethod
    def build_run_args(config: Config) -> tuple[list, str]:
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

        # Generate and write entrypoint script to temporary file
        entrypoint_script = build_entrypoint_script(config)
        script_fd, script_path = tempfile.mkstemp(suffix='.sh', text=True)
        logging.debug(f"Created temporary entrypoint script: {script_path}")
        try:
            with os.fdopen(script_fd, 'w') as f:
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
            if config.volumes:
                logging.debug("Additional volume mounts:")
                for volume in config.volumes:
                    if ':' in volume:
                        args.extend([f"--volume={volume}:z"])
                        logging.debug(f"  {volume}")
                    else:
                        raise ValueError(f"Invalid volume format: {volume}. Use HOST:CONTAINER format.")

            # Environment variables
            if config.env_vars:
                logging.debug("Environment variables:")
                for env_var in config.env_vars:
                    if '=' in env_var:
                        # Set specific value: NAME=VALUE
                        args.extend([f"--env={env_var}"])
                        logging.debug(f"  Setting: {env_var}")
                    else:
                        # Pass from host: NAME
                        args.extend([f"--env={env_var}"])
                        value = os.environ.get(env_var, '<not set>')
                        logging.debug(f"  Passing: {env_var}={value}")

            # Network configuration
            if config.network:
                if config.network == 'none':
                    args.extend(["--network=none"])
                elif config.network == 'host':
                    args.extend(["--network=host"])
                elif config.network == 'bridge':
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
    def run_container(config: Config) -> subprocess.CompletedProcess:
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
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet
    
    # Configure logging to stderr to keep stdout clean for command output
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format='[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S',
            stream=sys.stderr
        )
    elif quiet:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr)


@cli.command()
@click.argument("context", required=False)
@click.argument("command_args", nargs=-1)
@click.option(
    "--image",
    help="Container image to use (default: ubuntu:latest)"
)
@click.option("--debug", is_flag=True, help="Show configuration details")
@click.option(
    "--config",
    help="Path to configuration file"
)
@click.option(
    "--env",
    multiple=True,
    help="Set environment variable (NAME=VALUE) or pass from host (NAME)"
)
@click.option(
    "--volume",
    multiple=True,
    help="Mount additional volume (HOST:CONTAINER format)"
)
@click.option(
    "--sudo",
    is_flag=True,
    help="Add user to sudoers with NOPASSWD inside container"
)
@click.option(
    "--network",
    help="Enable container networking (default: disabled for security)"
)
@click.option(
    "--dir",
    help="Directory to mount as workdir (default: current directory)"
)
@click.option(
    "--gosu-path",
    help="Path to gosu binary (default: auto-discover from PATH or .ctenv/gosu)"
)
@click.pass_context  
def run(ctx, context, command_args, image, debug, config, env, volume, sudo, network, dir, gosu_path):
    """Run command in container

    Examples:
        ctenv run                          # Interactive bash with defaults
        ctenv run dev                      # Use 'dev' context with default command
        ctenv run dev -- npm test         # Use 'dev' context, run npm test
        ctenv run -- ls -la               # Use defaults, run ls -la
        ctenv run --image alpine -- whoami # Override image, run whoami
    """
    verbose = ctx.obj.get('verbose', False)
    quiet = ctx.obj.get('quiet', False)
    
    # Simple Click-style parsing - this allows some ambiguous cases but is standard
    if command_args:
        # Command specified
        command = command_args
    else:
        # No command, default to bash
        command = ("bash",)
    
    # Validate context if provided
    if context:
        try:
            config_data = load_merged_config()
            if config_data:
                contexts = config_data.get("contexts", {})
                if context not in contexts:
                    available = list(contexts.keys())
                    click.echo(f"Error: Context '{context}' not found. Available: {available}", err=True)
                    sys.exit(1)
            else:
                click.echo(f"Error: No configuration file found. Context '{context}' is not available.", err=True)
                sys.exit(1)
        except Exception as e:
            click.echo(f"Error loading configuration: {e}", err=True)
            sys.exit(1)
    
    # Context validation was already done during parsing above

    # Create config from CLI options and discovered configuration
    try:
        config = Config.from_cli_options(
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
        logging.debug(f"Configuration:")
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
        # Load config file(s)
        config_data = {}
        config_files_used = []
        
        if config:
            config_path = Path(config)
            if not config_path.exists():
                click.echo(f"Config file not found: {config_path}", err=True)
                sys.exit(1)
            config_data = load_config_file(config_path)
            config_files_used = [config_path]
        else:
            # Get merged config and track which files were used
            global_config_path, project_config_path = find_all_config_files()
            
            if global_config_path:
                config_files_used.append(global_config_path)
            if project_config_path:
                config_files_used.append(project_config_path)
                
            if config_files_used:
                config_data = load_merged_config()
        
        # Get built-in defaults
        builtin_defaults = get_builtin_defaults()
        
        if context:
            # Show specific context
            if not config_data:
                click.echo(f"No configuration file found. Context '{context}' is not available.", err=True)
                click.echo("Effective defaults would be used:", err=True)
                for key, value in builtin_defaults.items():
                    click.echo(f"  {key}: {value}")
                sys.exit(1)
                
            contexts = config_data.get("contexts", {})
            if context not in contexts:
                available = list(contexts.keys())
                click.echo(f"Context '{context}' not found. Available: {available}", err=True)
                sys.exit(1)
            
            # Show which config files are being used
            if len(config_files_used) == 1:
                click.echo(f"Context '{context}' from {config_files_used[0]}:")
            else:
                click.echo(f"Context '{context}' from merged configs:")
                for config_file in config_files_used:
                    click.echo(f"  {config_file}")
            
            # Show effective configuration for this context (built-in defaults + file defaults + context)
            effective_config = builtin_defaults.copy()
            effective_config.update(config_data.get("defaults", {}))
            effective_config.update(contexts[context])
            
            for key, value in effective_config.items():
                click.echo(f"  {key}: {value}")
        else:
            # Show all configuration
            click.echo("Configuration:")
            
            if config_data:
                # Show which config files are being used
                if len(config_files_used) == 1:
                    click.echo(f"\nUsing config file: {config_files_used[0]}")
                else:
                    click.echo(f"\nUsing merged config files:")
                    for config_file in config_files_used:
                        click.echo(f"  {config_file}")
                
                # Show effective defaults (built-in + file)
                effective_defaults = builtin_defaults.copy()
                effective_defaults.update(config_data.get("defaults", {}))
                click.echo("\nEffective defaults:")
                for key, value in effective_defaults.items():
                    click.echo(f"  {key}: {value}")
                
                # Show contexts
                contexts = config_data.get("contexts", {})
                if contexts:
                    click.echo("\nContexts:")
                    for ctx_name in sorted(contexts.keys()):
                        click.echo(f"  {ctx_name}")
            else:
                click.echo("\nNo configuration files found.")
                click.echo("\nEffective defaults:")
                for key, value in builtin_defaults.items():
                    click.echo(f"  {key}: {value}")
    
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
        config_files_to_check = []
        
        if config:
            # Explicit config file specified
            config_path = Path(config)
            if not config_path.exists():
                click.echo(f"Config file not found: {config_path}", err=True)
                sys.exit(1)
            config_files_to_check.append(config_path.resolve())
        else:
            # Discover all config files (project + global)
            current = Path.cwd().resolve()
            
            # Search upward for project config
            while True:
                project_config = current / ".ctenv" / "config.toml"
                if project_config.exists() and project_config.is_file():
                    config_files_to_check.append(project_config)
                    break
                
                parent = current.parent
                if parent == current:  # Reached filesystem root
                    break
                current = parent
            
            # Check global config
            global_config = Path.home() / ".ctenv" / "config.toml"
            if global_config.exists() and global_config.is_file():
                config_files_to_check.append(global_config)
        
        if not config_files_to_check:
            click.echo("No configuration files found", err=True)
            sys.exit(1)
        
        total_contexts = 0
        for config_path in config_files_to_check:
            try:
                config_data = load_config_file(config_path)
                contexts_dict = config_data.get("contexts", {})
                
                if contexts_dict:
                    click.echo(f"\nContexts from {config_path}:")
                    for ctx_name in sorted(contexts_dict.keys()):
                        click.echo(f"  {ctx_name}")
                    total_contexts += len(contexts_dict)
            except Exception as e:
                click.echo(f"Error reading {config_path}: {e}", err=True)
        
        if total_contexts == 0:
            click.echo("No contexts defined in any configuration file")
    
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
