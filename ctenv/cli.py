"""Command-line interface for ctenv.

This module handles argument parsing, command routing, and user interaction.
"""

import argparse
import logging
import shlex
import sys
from pathlib import Path

from .version import __version__
from .config import (
    CtenvConfig,
    ContainerConfig,
    RuntimeContext,
    convert_notset_strings,
    resolve_relative_paths_in_container_config,
)
from .container import parse_container_config, ContainerRunner


def setup_logging(verbose, quiet):
    """Configure logging based on verbosity flags."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s", stream=sys.stderr)
    elif quiet:
        logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)


def cmd_run(args, command):
    """Run command in container."""
    verbose = args.verbose
    quiet = args.quiet

    # Get runtime context once at the start
    runtime = RuntimeContext.current(
        cwd=Path.cwd(),
        project_dir=args.project_dir,
    )

    # Load configuration early
    try:
        explicit_configs = [Path(c) for c in args.config] if args.config else None
        ctenv_config = CtenvConfig.load(runtime.project_dir, explicit_config_files=explicit_configs)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Create config from loaded CtenvConfig and CLI options
    try:
        # Convert CLI overrides to ContainerConfig and resolve paths
        # convert "NOTSET" string to NOTSET sentinel
        cli_overrides = resolve_relative_paths_in_container_config(
            ContainerConfig.from_dict(
                convert_notset_strings(
                    {
                        "image": args.image,
                        "command": command,
                        "workspace": args.workspace,
                        "workdir": args.workdir,
                        "env": args.env,
                        "volumes": args.volumes,
                        "sudo": args.sudo,
                        "network": args.network,
                        "gosu_path": args.gosu_path,
                        "platform": args.platform,
                        "post_start_commands": args.post_start_commands,
                        "run_args": args.run_args,
                    }
                )
            ),
            runtime.cwd,
        )

        # Get merged ContainerConfig
        if args.container is None:
            container_config = ctenv_config.get_default(overrides=cli_overrides)
        else:
            container_config = ctenv_config.get_container(
                container=args.container, overrides=cli_overrides
            )

        # Parse and resolve to ContainerSpec with runtime context
        spec = parse_container_config(container_config, runtime)

    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if verbose:
        # Use resolved spec for debugging output to show final values
        logging.debug("Configuration:")
        logging.debug(f"  Image: {spec.image}")
        logging.debug(f"  Command: {spec.command}")
        logging.debug(f"  User: {spec.user_name} (UID: {spec.user_id})")
        logging.debug(f"  Group: {spec.group_name} (GID: {spec.group_id})")
        logging.debug(f"  Workspace: {spec.workspace.host_path} -> {spec.workspace.container_path}")
        logging.debug(f"  Working directory: {spec.workdir}")
        logging.debug(f"  Container name: {spec.container_name}")
        logging.debug(f"  Environment variables: {spec.env}")
        logging.debug(f"  Volumes: {[vol.to_string() for vol in spec.volumes]}")
        logging.debug(f"  Network: {spec.network or 'default (Docker default)'}")
        logging.debug(f"  Sudo: {spec.sudo}")
        logging.debug(f"  TTY: {spec.tty}")
        logging.debug(f"  Platform: {spec.platform or 'default'}")
        logging.debug(f"  Gosu binary: {spec.gosu.to_string()}")

    if not quiet:
        print("[ctenv] run", file=sys.stderr)

    # Execute container (or dry-run)
    try:
        result = ContainerRunner.run_container(spec, verbose, dry_run=args.dry_run, quiet=quiet)
        sys.exit(result.returncode)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_show(args):
    """Show configuration or container details."""
    try:
        runtime = RuntimeContext.current(
            cwd=Path.cwd(),
            project_dir=args.project_dir,
        )

        # Load configuration early
        explicit_configs = [Path(c) for c in getattr(args, "config", None) or []]
        ctenv_config = CtenvConfig.load(runtime.project_dir, explicit_config_files=explicit_configs)

        # Show defaults section if present
        if ctenv_config.defaults:
            print("defaults:")
            defaults_dict = ctenv_config.defaults.to_dict(include_notset=False)
            for key, value in sorted(defaults_dict.items()):
                if not key.startswith("_"):  # Skip metadata fields
                    print(f"  {key} = {repr(value)}")
            print()

        # Show containers sorted by config name
        print("containers:")
        if ctenv_config.containers:
            for config_name in sorted(ctenv_config.containers.keys()):
                print(f"  {config_name}:")
                container_dict = ctenv_config.containers[config_name].to_dict(include_notset=False)
                for key, value in sorted(container_dict.items()):
                    if not key.startswith("_"):  # Skip metadata fields
                        print(f"    {key} = {repr(value)}")
                print()  # Empty line between containers
        else:
            print("# No containers defined")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def create_parser():
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog="ctenv",
        description="ctenv is a tool for running a program in a container as current user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,  # Require full option names
    )

    parser.add_argument("--version", action="version", version=f"ctenv {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress non-essential output")
    parser.add_argument(
        "--config",
        action="append",
        help="Path to configuration file (can be used multiple times, order matters)",
    )
    parser.add_argument(
        "-p",
        "--project-dir",
        help="Project directory, where .ctenv.toml is placed and the default workspace (default: dir with .ctenv.toml in, current or in parent tree (except HOME). Using cwd if no .ctenv.toml is found)",
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run command in container",
        usage="ctenv [global options] run [options] [container] [-- COMMAND ...]",
        description="""Run command in container

Examples:
    ctenv run                          # Interactive bash with defaults
    ctenv run dev                      # Use 'dev' container with default command
    ctenv run dev -- npm test          # Use 'dev' container, run npm test
    ctenv run -- ls -la                # Use defaults, run ls -la
    ctenv run --image alpine dev       # Override image, use dev container
    ctenv --verbose run --dry-run dev # Show Docker command without running (verbose)
    ctenv -q run dev                   # Run quietly
    ctenv run --post-start-command "npm install" --post-start-command "npm run build" # Run extra commands after container starts

Note: Use '--' to separate commands from container/options.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show commands without running container",
    )

    run_parser.add_argument("--image", help="Container image to use")
    run_parser.add_argument(
        "--env",
        action="append",
        dest="env",
        help="Set environment variable (NAME=VALUE) or pass from host (NAME)",
    )
    run_parser.add_argument(
        "-v",
        "--volume",
        action="append",
        dest="volumes",
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
        "--workspace",
        help="Workspace to mount (supports volume syntax: /path, /host:/container, auto:/repo)",
    )
    run_parser.add_argument(
        "-w",
        "--workdir",
        help="Working directory inside container (where to cd) (default: cwd)",
    )
    run_parser.add_argument(
        "--platform",
        help="Container platform (e.g., linux/amd64, linux/arm64)",
    )
    run_parser.add_argument(
        "--gosu-path",
        help="Path to gosu binary (default: auto-discover from PATH or .ctenv/gosu)",
    )
    run_parser.add_argument(
        "--run-arg",
        action="append",
        dest="run_args",
        help="Add custom argument to container run command (can be used multiple times)",
    )
    run_parser.add_argument(
        "--post-start-command",
        action="append",
        dest="post_start_commands",
        help="Add extra command to run after container starts, but before the COMMAND is executed (can be used multiple times)",
    )
    run_parser.add_argument("container", nargs="?", help="Container to use (default: 'default')")

    # config subcommand group
    config_parser = subparsers.add_parser("config", help="Configuration management commands")
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", help="Config subcommands"
    )

    # config show
    config_subparsers.add_parser("show", help="Show configuration or container details")

    return parser


def main(argv=None):
    """Main entry point."""
    # Always use sys.argv[1:] when called without arguments
    if argv is None:
        argv = sys.argv[1:]

    # Split at '--' if present to separate ctenv args from command args
    if "--" in argv:
        separator_index = argv.index("--")
        ctenv_args = argv[:separator_index]
        command_args = argv[separator_index + 1 :]
        # Use shlex.join to properly quote arguments
        command = shlex.join(command_args)
        # command = ' '.join(command_args)
    else:
        ctenv_args = argv
        command = None

    # Parse only ctenv arguments
    parser = create_parser()
    args = parser.parse_args(ctenv_args)

    # Setup logging based on global verbose/quiet flags
    setup_logging(args.verbose, args.quiet)

    # Route to appropriate command handler
    if args.subcommand == "run":
        cmd_run(args, command)
    elif args.subcommand == "config":
        if args.config_command == "show" or args.config_command is None:
            cmd_config_show(args)
        else:
            parser.parse_args(["config", "--help"])
    else:
        parser.print_help()
        sys.exit(1)