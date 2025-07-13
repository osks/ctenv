#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.9"
# dependencies = ["click"]
# ///

__version__ = "0.1"

import click

@click.group()
@click.version_option()
def cli():
    """ctenv is a tool for running a program in a container as current user"""


@cli.command()
@click.option(
    "--image",
    help="Container image to use (default: ubuntu:latest)",
    default="ubuntu:latest"
)
@click.argument(
    "command",
    nargs=-1,
    required=False
)
def run(image, command):
    """Run command in container
    
    Examples:
        ctenv run                           # Interactive bash
        ctenv run -- ls -la                # Run specific command
        ctenv run --image alpine -- whoami # Use custom image
    """
    if not command:
        # Default to interactive bash
        command = ("bash",)
    
    # For now, just show what would be executed
    click.echo(f"[ctenv] run")
    click.echo(f"Image: {image}")
    click.echo(f"Command: {' '.join(command)}")
    click.echo("TODO: Implement container execution")


if __name__ == "__main__":
    cli()
