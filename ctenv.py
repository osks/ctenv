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
    "ctenv is a tool for running a program in a container as current user"


@cli.command(name="command")
@click.argument(
    "example"
)
@click.option(
    "-o",
    "--option",
    help="An example option",
)
def first_command(example, option):
    "Command description goes here"
    click.echo("Here is some output")


if __name__ == "__main__":
    cli()
