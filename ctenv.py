#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.9"
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
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

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
    def from_cli_options(cls, **cli_options) -> "Config":
        """Create Config from CLI options with system defaults."""
        logging.debug("Creating Config from CLI options")
        
        # Get user info if not provided
        user_info = get_current_user_info()
        logging.debug(f"User info: {user_info['user_name']} (UID: {user_info['user_id']})")
        
        # Get script directory
        script_dir = Path(__file__).parent.resolve()
        logging.debug(f"Script directory: {script_dir}")
        
        # Get working directory
        dir_param = cli_options.get("dir")
        working_dir = Path(dir_param) if dir_param else Path(os.getcwd())
        logging.debug(f"Working directory: {working_dir}")
        
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
            
            # Container settings
            image=cli_options.get("image", "ubuntu:latest"),
            command=cli_options.get("command", "bash"),
            container_name=cli_options.get("container_name"),
            
            # Options
            env_vars=cli_options.get("env_vars", ()),
            volumes=cli_options.get("volumes", ()),
            sudo=cli_options.get("sudo", False),
            network=cli_options.get("network"),
            tty=cli_options.get("tty", False),
        )
    
    @property
    def gosu_path(self) -> Path:
        """Path to gosu binary on host."""
        return self.script_dir / "gosu"
    
    def get_container_name(self) -> str:
        """Generate container name based on working directory."""
        if self.container_name:
            return self.container_name
        # Replace / with - to make valid container name  
        dir_id = str(self.working_dir).replace("/", "-")
        return f"ctenv-{dir_id}"
    
    def to_dict(self) -> dict:
        """Convert to dict for compatibility with existing functions."""
        return {
            "USER_NAME": self.user_name,
            "USER_ID": self.user_id,
            "GROUP_NAME": self.group_name,
            "GROUP_ID": self.group_id,
            "USER_HOME": self.user_home,
            "DIR": str(self.working_dir),
            "DIR_MOUNT": self.dir_mount,
            "GOSU": str(self.gosu_path),
            "GOSU_MOUNT": self.gosu_mount,
            "IMAGE": self.image,
            "COMMAND": self.command,
            "NAME": self.get_container_name(),
            "ENV_VARS": self.env_vars,
            "VOLUMES": self.volumes,
            "SUDO": self.sudo,
            "NETWORK": self.network,
            "TTY": self.tty,
        }


def build_entrypoint_script(config: dict) -> str:
    """Generate bash script for container entrypoint."""
    script = f"""#!/bin/bash
set -e

# Create group if needed
if getent group {config["GROUP_ID"]} >/dev/null 2>&1; then
    GROUP_NAME=$(getent group {config["GROUP_ID"]} | cut -d: -f1)
else
    groupadd -g {config["GROUP_ID"]} {config["GROUP_NAME"]}
    GROUP_NAME={config["GROUP_NAME"]}
fi

# Create user if needed
if ! getent passwd {config["USER_NAME"]} >/dev/null 2>&1; then
    useradd --no-create-home --home-dir {config["USER_HOME"]} \\
        --shell /bin/bash -u {config["USER_ID"]} -g {config["GROUP_ID"]} \\
        -o -c "" {config["USER_NAME"]}
fi

# Setup home directory
export HOME={config["USER_HOME"]}
if [ ! -d "$HOME" ]; then
    mkdir -p "$HOME"
    chown {config["USER_ID"]}:{config["GROUP_ID"]} "$HOME"
fi

# Set ownership of home directory (non-recursive)
chown {config["USER_NAME"]} "$HOME"

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
echo "{config["USER_NAME"]} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
''' if config.get("SUDO") else "# Sudo not requested"}

# Set environment
export PS1="[ctenv] $ "

# Execute command as user
exec {config["GOSU_MOUNT"]} {config["USER_NAME"]} {config["COMMAND"]}
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
        entrypoint_script = build_entrypoint_script(config.to_dict())
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
@click.option(
    "--image",
    help="Container image to use (default: ubuntu:latest)",
    default="ubuntu:latest",
)
@click.option("--debug", is_flag=True, help="Show configuration details")
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
@click.argument("command", nargs=-1, required=False)
@click.pass_context
def run(ctx, image, command, debug, env, volume, sudo, network, dir):
    """Run command in container

    Examples:
        ctenv run                          # Interactive bash
        ctenv run -- ls -la                # Run specific command
        ctenv run --image alpine -- whoami # Use custom image
    """
    verbose = ctx.obj.get('verbose', False)
    quiet = ctx.obj.get('quiet', False)
    
    if not command:
        # Default to interactive bash
        command = ("bash",)

    # Create config from CLI options
    config = Config.from_cli_options(
        image=image,
        command=" ".join(command),
        dir=dir,
        env_vars=env,
        volumes=volume,
        sudo=sudo,
        network=network,
        tty=sys.stdin.isatty(),
    )
    
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


if __name__ == "__main__":
    cli()
