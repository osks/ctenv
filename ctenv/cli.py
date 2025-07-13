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
