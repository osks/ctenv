"""Command-line interface for ctenv.

This module handles argument parsing, command routing, and user interaction.
"""

import argparse
import shlex
import sys
from pathlib import Path

from .version import __version__

from .config import (
    CtenvConfig,
    ContainerConfig,
    RuntimeContext,
    Verbosity,
    convert_notset_strings,
    resolve_project_dir,
    resolve_relative_paths_in_container_config,
    NOTSET,
)
from .container import parse_container_config, ContainerRunner
from .image import build_container_image, parse_build_spec


def get_verbosity(args) -> Verbosity:
    """Convert args to Verbosity level."""
    if args.quiet:
        return Verbosity.QUIET
    elif args.verbose >= 2:
        return Verbosity.VERY_VERBOSE
    elif args.verbose >= 1:
        return Verbosity.VERBOSE
    else:
        return Verbosity.NORMAL


def _resolve_container_config(args, command, runtime):
    # Load configuration early
    explicit_configs = [Path(c) for c in args.config] if args.config else None
    ctenv_config = CtenvConfig.load(
        runtime.project_dir, explicit_config_files=explicit_configs, verbosity=args.verbosity
    )

    # Convert CLI overrides to ContainerConfig and resolve paths
    # convert "NOTSET" string to NOTSET sentinel
    cli_args_dict = {
        "image": args.image,
        "container_name": args.name,
        "command": command,
        # Target path in container for project
        "project_target": args.project_target,
        "auto_project_mount": False if args.no_auto_project_mount else None,
        "subpaths": args.subpaths,
        "workdir": args.workdir,
        "env": args.env,
        "volumes": args.volumes,
        "sudo": args.sudo,
        "network": args.network,
        "gosu_path": args.gosu_path,
        "platform": args.platform,
        "post_start_commands": args.post_start_commands,
        "run_args": args.run_args,
        "runtime": args.runtime,
    }

    # Handle build arguments
    if any(
        [
            args.build_dockerfile,
            args.build_dockerfile_content,
            args.build_context,
            args.build_tag,
            args.build_args,
        ]
    ):
        build_dict = {}
        if args.build_dockerfile:
            build_dict["dockerfile"] = args.build_dockerfile
        if args.build_dockerfile_content:
            build_dict["dockerfile_content"] = args.build_dockerfile_content
        if args.build_context:
            build_dict["context"] = args.build_context
        if args.build_tag:
            build_dict["tag"] = args.build_tag
        if args.build_args:
            # Convert build args from list of "KEY=VALUE" to dict
            build_dict["args"] = {}
            for arg in args.build_args:
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    build_dict["args"][key] = value
                else:
                    raise ValueError(f"Invalid build argument format: {arg}. Expected KEY=VALUE")

        cli_args_dict["build"] = build_dict

    cli_overrides = resolve_relative_paths_in_container_config(
        ContainerConfig.from_dict(convert_notset_strings(cli_args_dict)),
        runtime.cwd,
    )

    container = (args.container or ctenv_config.default_container)
    # Get merged ContainerConfig
    if container is None:
        container_config = ctenv_config.get_default(overrides=cli_overrides)
    else:
        # If the container doesn't exist, it will (and should) fail,
        # which is handled by get_container raising.
        container_config = ctenv_config.get_container(
            container=container, overrides=cli_overrides
        )

    return container_config


def cmd_run(args, command):
    """Run command in container."""
    if args.verbosity >= Verbosity.NORMAL:
        print("[ctenv] run", file=sys.stderr)

    # Get runtime context once at the start
    cwd = Path.cwd()
    project_dir = resolve_project_dir(cwd, args.project_dir)
    runtime = RuntimeContext.current(cwd=cwd, project_dir=project_dir)

    # Create config from loaded CtenvConfig and CLI options
    try:
        container_config = _resolve_container_config(args, command, runtime)
        spec, build_spec = parse_container_config(container_config, runtime)
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbosity >= Verbosity.VERBOSE:
        # Use resolved spec for debugging output to show final values
        print(f"Project dir: {runtime.project_dir}", file=sys.stderr)
        print("Configuration:", file=sys.stderr)
        print(f"  Image: {spec.image}", file=sys.stderr)
        print(f"  Command: {spec.command}", file=sys.stderr)
        print(f"  User: {spec.user_name} (UID: {spec.user_id})", file=sys.stderr)
        print(f"  Group: {spec.group_name} (GID: {spec.group_id})", file=sys.stderr)
        print(f"  Working directory: {spec.workdir}", file=sys.stderr)
        print(f"  Container name: {spec.container_name}", file=sys.stderr)
        print(f"  Environment variables: {spec.env}", file=sys.stderr)
        print(f"  Volumes: {[vol.to_string() for vol in spec.volumes]}", file=sys.stderr)
        print(f"  Network: {spec.network or 'default (Docker default)'}", file=sys.stderr)
        print(f"  Sudo: {spec.sudo}", file=sys.stderr)
        print(f"  TTY: {spec.tty}", file=sys.stderr)
        print(f"  Platform: {spec.platform or 'default'}", file=sys.stderr)
        print(f"  Gosu binary: {spec.gosu.to_string()}", file=sys.stderr)

    # Execute container (or dry-run)
    try:
        if build_spec is not None:
            build_container_image(build_spec, runtime, verbosity=args.verbosity)

        result = ContainerRunner.run_container(spec, verbosity=args.verbosity, dry_run=args.dry_run)
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
        cwd = Path.cwd()
        project_dir = resolve_project_dir(cwd, args.project_dir)
        runtime = RuntimeContext.current(cwd=cwd, project_dir=project_dir)

        # Load configuration early
        explicit_configs = [Path(c) for c in getattr(args, "config", None) or []]
        ctenv_config = CtenvConfig.load(
            runtime.project_dir, explicit_config_files=explicit_configs, verbosity=args.verbosity
        )

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


def cmd_build(args):
    """Build container image."""
    # Get runtime context once at the start
    cwd = Path.cwd()
    project_dir = resolve_project_dir(cwd, args.project_dir)
    runtime = RuntimeContext.current(cwd=cwd, project_dir=project_dir)

    # Load configuration early
    try:
        explicit_configs = [Path(c) for c in args.config] if args.config else None
        ctenv_config = CtenvConfig.load(
            runtime.project_dir, explicit_config_files=explicit_configs, verbosity=args.verbosity
        )
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Create build config from CLI arguments
    try:
        # Build CLI overrides for build configuration
        cli_args_dict = {
            "runtime": args.runtime,
        }

        # Handle build arguments - always enable build for build command
        build_dict = {}
        if args.build_dockerfile:
            build_dict["dockerfile"] = args.build_dockerfile
        if args.build_dockerfile_content:
            build_dict["dockerfile_content"] = args.build_dockerfile_content
        if args.build_context:
            build_dict["context"] = args.build_context
        if args.build_tag:
            build_dict["tag"] = args.build_tag
        if args.build_args:
            # Convert build args from list of "KEY=VALUE" to dict
            build_dict["args"] = {}
            for arg in args.build_args:
                if "=" in arg:
                    key, value = arg.split("=", 1)
                    build_dict["args"][key] = value
                else:
                    raise ValueError(f"Invalid build argument format: {arg}. Expected KEY=VALUE")

        cli_args_dict["build"] = build_dict

        cli_overrides = resolve_relative_paths_in_container_config(
            ContainerConfig.from_dict(convert_notset_strings(cli_args_dict)),
            runtime.cwd,
        )

        # Get merged ContainerConfig
        container_config = ctenv_config.get_container(
            container=args.container, overrides=cli_overrides
        )

        # Ensure build configuration is present
        if container_config.build is NOTSET:
            print(
                "Error: No build configuration found. Use config file or CLI arguments to specify build options.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Parse build specification and build the image
        build_spec = parse_build_spec(container_config, runtime)
        built_image_tag = build_container_image(build_spec, runtime, verbosity=args.verbosity)

        if args.verbosity >= Verbosity.NORMAL:
            print(f"[ctenv] Successfully built image: {built_image_tag}", file=sys.stderr)

    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
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

    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v verbose, -vv very verbose)",
    )
    verbosity_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress non-essential output",
    )
    parser.add_argument(
        "--config",
        action="append",
        help="Path to configuration file (can be used multiple times, order matters)",
    )
    parser.add_argument(
        "--runtime",
        choices=["docker", "podman"],
        help="Container runtime: docker (rootful - the default) or podman (rootless with --userns=keep-id)",
    )
    parser.add_argument(
        "-p",
        "--project-dir",
        dest="project_dir",
        help="Project directory on host. Default: auto-detect from .ctenv.toml",
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
    run_parser.add_argument(
        "--gosu-path",
        help="Path to gosu binary (default: auto-discover from PATH or .ctenv/gosu)",
    )

    # Container options group
    container_group = run_parser.add_argument_group(
        "Container Options", "Configure the container runtime environment"
    )
    container_group.add_argument("--image", help="Container image to use")
    container_group.add_argument("--name", help="Container name")
    container_group.add_argument(
        "--workdir",
        help="Working directory inside container (where to cd) (default: cwd)",
    )
    container_group.add_argument(
        "--env",
        action="append",
        dest="env",
        help="Set environment variable (NAME=VALUE) or pass from host (NAME)",
    )
    container_group.add_argument(
        "--network", help="Enable container networking (default: disabled for security)"
    )
    container_group.add_argument(
        "--platform",
        help="Container platform (e.g., linux/amd64, linux/arm64)",
    )
    container_group.add_argument(
        "--sudo",
        action="store_true",
        help="Add user to sudoers with NOPASSWD inside container",
    )
    container_group.add_argument(
        "--run-arg",
        action="append",
        dest="run_args",
        help="Add custom argument to container run command (can be used multiple times)",
    )
    container_group.add_argument(
        "--post-start-command",
        action="append",
        dest="post_start_commands",
        help="Add extra command to run after container starts, but before the COMMAND is executed. Will be executed as the root user. (can be used multiple times)",
    )

    # Volume options group
    volume_group = run_parser.add_argument_group(
        "Volume Options", "Control how directories are mounted into the container"
    )
    volume_group.add_argument(
        "-v",
        "--volume",
        action="append",
        dest="volumes",
        help="Mount additional volume (HOST:CONTAINER format)",
    )
    volume_group.add_argument(
        "-s",
        "--subpath",
        action="append",
        dest="subpaths",
        help="Mount only this subpath instead of entire project (repeatable, disables auto project mount)",
    )
    volume_group.add_argument(
        "--project-target",
        dest="project_target",
        help="Target path in container for project (e.g., /repo). Default: same as host path",
    )
    volume_group.add_argument(
        "--no-auto-project-mount",
        action="store_true",
        dest="no_auto_project_mount",
        help="Skip auto-mounting project directory (volumes and subpaths will still be mounted)",
    )

    # Build options group
    build_group = run_parser.add_argument_group(
        "Build Options", "Options for building container image before running"
    )
    build_group.add_argument(
        "--build-dockerfile",
        help="Path to Dockerfile for building (default: Dockerfile)",
    )
    build_group.add_argument(
        "--build-dockerfile-content",
        help="Inline Dockerfile content (mutually exclusive with --build-dockerfile)",
    )
    build_group.add_argument(
        "--build-context",
        help="Build context directory (default: .)",
    )
    build_group.add_argument(
        "--build-tag",
        help="Custom image tag (default: auto-generated)",
    )
    build_group.add_argument(
        "--build-arg",
        action="append",
        dest="build_args",
        help="Build arguments in KEY=VALUE format (can be used multiple times)",
    )

    run_parser.add_argument("container", nargs="?", help="Container to use (default: 'default')")

    # config subcommand group
    config_parser = subparsers.add_parser("config", help="Configuration management commands")
    config_subparsers = config_parser.add_subparsers(
        dest="config_command", help="Config subcommands"
    )

    # config show
    config_subparsers.add_parser("show", help="Show configuration or container details")

    # build command
    build_parser = subparsers.add_parser(
        "build",
        help="Build container image",
        description="Build container image from build configuration",
    )
    build_parser.add_argument(
        "--build-dockerfile",
        help="Path to Dockerfile for building (default: Dockerfile)",
    )
    build_parser.add_argument(
        "--build-dockerfile-content",
        help="Inline Dockerfile content (mutually exclusive with --build-dockerfile)",
    )
    build_parser.add_argument(
        "--build-context",
        help="Build context directory (default: .)",
    )
    build_parser.add_argument(
        "--build-tag",
        help="Custom image tag (default: auto-generated)",
    )
    build_parser.add_argument(
        "--build-arg",
        action="append",
        dest="build_args",
        help="Build arguments in KEY=VALUE format (can be used multiple times)",
    )
    build_parser.add_argument("container", help="Container to use for build configuration")

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
    args.verbosity = get_verbosity(args)

    # Route to appropriate command handler
    if args.subcommand == "run":
        cmd_run(args, command)
    elif args.subcommand == "config":
        if args.config_command == "show" or args.config_command is None:
            cmd_config_show(args)
        else:
            parser.parse_args(["config", "--help"])
    elif args.subcommand == "build":
        cmd_build(args)
    else:
        parser.print_help()
        sys.exit(1)
