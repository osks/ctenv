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
from pathlib import Path

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


class Config:
    """Configuration class for ctenv."""

    def __init__(self, user_info=None, script_dir=None):
        # Use provided values or detect them explicitly
        if user_info is None:
            user_info = get_current_user_info()

        if script_dir is None:
            script_dir = Path(__file__).parent.resolve()

        self.user_name = user_info["user_name"]
        self.user_id = user_info["user_id"]
        self.group_name = user_info["group_name"]
        self.group_id = user_info["group_id"]
        self.user_home = user_info["user_home"]
        self.script_dir = script_dir

        # Set up defaults
        self.defaults = {
            "IMAGE": "ubuntu:latest",
            "DIR": str(self.script_dir),
            "DIR_MOUNT": "/repo",
            "GOSU": str(self.script_dir / "gosu"),
            "GOSU_MOUNT": "/gosu",
            "USER_NAME": self.user_name,
            "USER_ID": self.user_id,
            "GROUP_NAME": self.group_name,
            "GROUP_ID": self.group_id,
            "USER_HOME": self.user_home,
            "COMMAND": "bash",
        }

    def get_container_name(self, directory_path: str) -> str:
        """Generate container name based on directory path."""
        # Replace / with - to make valid container name
        dir_id = directory_path.replace("/", "-")
        return f"ctenv-{dir_id}"

    def merge_options(self, cli_options: dict) -> dict:
        """Merge CLI options with defaults."""
        config = self.defaults.copy()

        # Update with CLI options
        for key, value in cli_options.items():
            if value is not None:
                config[key] = value

        return config


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

# Set environment
export PS1="[ctenv] $ "

# Execute command as user
exec {config["GOSU_MOUNT"]} {config["USER_NAME"]} {config["COMMAND"]}
"""
    return script


class ContainerRunner:
    """Manages Docker container operations."""

    def __init__(self, config: Config):
        self.config = config

    def build_run_args(self, run_config: dict) -> list:
        """Build Docker run arguments."""
        import tempfile
        
        args = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--platform=linux/amd64",
            f"--name={run_config['NAME']}",
        ]

        # Generate and write entrypoint script to temporary file
        entrypoint_script = build_entrypoint_script(run_config)
        script_fd, script_path = tempfile.mkstemp(suffix='.sh', text=True)
        try:
            with os.fdopen(script_fd, 'w') as f:
                f.write(entrypoint_script)
            os.chmod(script_path, 0o755)
            
            # Store script path for cleanup later
            run_config['_SCRIPT_PATH'] = script_path
            
            # Volume mounts
            args.extend(
                [
                    f"--volume={run_config['DIR']}:{run_config['DIR_MOUNT']}:z,rw",
                    f"--volume={run_config['GOSU']}:{run_config['GOSU_MOUNT']}:z,ro",
                    f"--volume={script_path}:/entrypoint.sh:z,ro",
                    f"--workdir={run_config['DIR_MOUNT']}",
                ]
            )

            # TTY flags if running interactively
            if sys.stdin.isatty():
                args.extend(["-t", "-i"])

            # Set entrypoint to our script
            args.extend(["--entrypoint", "/entrypoint.sh"])

            # Container image
            args.append(run_config["IMAGE"])

            return args
        except Exception:
            # Cleanup on error
            try:
                os.unlink(script_path)
            except OSError:
                pass
            raise

    def run_container(self, run_config: dict) -> subprocess.CompletedProcess:
        """Execute Docker container with the given configuration."""
        # Check if Docker is available
        if not shutil.which("docker"):
            raise FileNotFoundError("Docker not found in PATH. Please install Docker.")

        # Verify gosu binary exists
        gosu_path = Path(run_config["GOSU"])
        if not gosu_path.exists():
            raise FileNotFoundError(
                f"gosu binary not found at {gosu_path}. Please ensure gosu is available."
            )

        if not gosu_path.is_file():
            raise FileNotFoundError(f"gosu path {gosu_path} is not a file.")

        # Verify current directory exists
        current_dir = Path(run_config["DIR"])
        if not current_dir.exists():
            raise FileNotFoundError(f"Directory {current_dir} does not exist.")

        if not current_dir.is_dir():
            raise FileNotFoundError(f"Path {current_dir} is not a directory.")

        # Generate container name
        run_config["NAME"] = self.config.get_container_name(run_config["DIR"])

        # Build Docker arguments
        docker_args = self.build_run_args(run_config)

        # Execute Docker command
        try:
            result = subprocess.run(docker_args, check=False)
            return result
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Container execution failed: {e}")
        finally:
            # Clean up temporary script file
            script_path = run_config.get('_SCRIPT_PATH')
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass


@click.group()
@click.version_option(version=__version__)
def cli():
    """ctenv is a tool for running a program in a container as current user"""


@cli.command()
@click.option(
    "--image",
    help="Container image to use (default: ubuntu:latest)",
    default="ubuntu:latest",
)
@click.option("--debug", is_flag=True, help="Show configuration details")
@click.argument("command", nargs=-1, required=False)
def run(image, command, debug):
    """Run command in container

    Examples:
        ctenv run                           # Interactive bash
        ctenv run -- ls -la                # Run specific command
        ctenv run --image alpine -- whoami # Use custom image
    """
    if not command:
        # Default to interactive bash
        command = ("bash",)

    # Create config and merge options
    config = Config()
    cli_options = {
        "IMAGE": image, 
        "COMMAND": " ".join(command),
        "DIR": os.getcwd()  # Use current working directory
    }
    merged_config = config.merge_options(cli_options)

    click.echo("[ctenv] run")

    if debug:
        click.echo(f"Image: {merged_config['IMAGE']}")
        click.echo(f"Command: {merged_config['COMMAND']}")
        click.echo("\nConfiguration:")
        click.echo(f"  User: {config.user_name} (UID: {config.user_id})")
        click.echo(f"  Group: {config.group_name} (GID: {config.group_id})")
        click.echo(f"  Home: {config.user_home}")
        click.echo(f"  Script dir: {config.script_dir}")
        click.echo(
            f"  Container name: {config.get_container_name(merged_config['DIR'])}"
        )

        # Show what Docker command would be executed
        runner = ContainerRunner(config)
        merged_config["NAME"] = config.get_container_name(merged_config["DIR"])
        docker_args = runner.build_run_args(merged_config)
        click.echo("\nDocker command:")
        click.echo(f"  {' '.join(docker_args)}")
        return

    # Execute container
    try:
        runner = ContainerRunner(config)
        result = runner.run_container(merged_config)
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    cli()
