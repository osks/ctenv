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
        "user_home": user_info.pw_dir
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
            "COMMAND": "bash"
        }
    
    def get_container_name(self, directory_path: str) -> str:
        """Generate container name based on directory path."""
        # Replace / with - to make valid container name
        dir_id = directory_path.replace('/', '-')
        return f"ctenv-{dir_id}"
    
    def merge_options(self, cli_options: dict) -> dict:
        """Merge CLI options with defaults."""
        config = self.defaults.copy()
        
        # Update with CLI options
        for key, value in cli_options.items():
            if value is not None:
                config[key] = value
        
        return config

@click.group()
@click.version_option(version=__version__)
def cli():
    """ctenv is a tool for running a program in a container as current user"""


@cli.command()
@click.option(
    "--image",
    help="Container image to use (default: ubuntu:latest)",
    default="ubuntu:latest"
)
@click.option(
    "--debug",
    is_flag=True,
    help="Show configuration details"
)
@click.argument(
    "command",
    nargs=-1,
    required=False
)
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
        "COMMAND": " ".join(command)
    }
    merged_config = config.merge_options(cli_options)
    
    # Show what would be executed
    click.echo(f"[ctenv] run")
    click.echo(f"Image: {merged_config['IMAGE']}")
    click.echo(f"Command: {merged_config['COMMAND']}")
    
    if debug:
        click.echo("\nConfiguration:")
        click.echo(f"  User: {config.user_name} (UID: {config.user_id})")
        click.echo(f"  Group: {config.group_name} (GID: {config.group_id})")
        click.echo(f"  Home: {config.user_home}")
        click.echo(f"  Script dir: {config.script_dir}")
        click.echo(f"  Container name: {config.get_container_name(merged_config['DIR'])}")
    
    click.echo("TODO: Implement container execution")


if __name__ == "__main__":
    cli()
