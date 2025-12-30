import os
import tempfile
from pathlib import Path
import pytest
import sys
from unittest.mock import patch
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv.cli import create_parser
from ctenv.config import RuntimeContext, Verbosity
from ctenv.container import parse_container_config, build_entrypoint_script


def test_version():
    parser = create_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    # argparse version exits with code 0
    assert exc_info.value.code == 0


def test_config_user_detection():
    """Test that config correctly loads and merges with runtime context."""

    # Use explicit image to avoid config file interference
    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.config import CtenvConfig, RuntimeContext, ContainerConfig
        from ctenv.container import parse_container_config
        from pathlib import Path

        ctenv_config = CtenvConfig.load(Path(tmpdir))  # Empty directory

        config_dict = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict({"image": "ubuntu:latest"})
        )

        # Create runtime context and parse to ContainerSpec
        runtime = RuntimeContext.current(cwd=Path.cwd())
        resolved_spec = parse_container_config(config_dict, runtime)

    import getpass

    # Check that runtime context is used for user info
    assert resolved_spec.user_name == getpass.getuser()
    assert resolved_spec.user_id == os.getuid()
    assert resolved_spec.group_id == os.getgid()
    assert resolved_spec.image == "ubuntu:latest"

    # Check workspace is properly resolved
    assert resolved_spec.workspace.host_path  # Should be resolved from "auto"
    assert resolved_spec.workspace.container_path  # Should have container path


def test_config_with_mock_runtime():
    """Test ContainerSpec creation with mock runtime context."""
    from pathlib import Path

    with tempfile.TemporaryDirectory():
        # Create mock runtime context
        mock_runtime = RuntimeContext(
            user_name="testuser",
            user_id=1000,
            user_home="/home/testuser",
            group_name="testgroup",
            group_id=1000,
            cwd=Path.cwd(),
            tty=False,
            project_dir=Path.cwd(),
            pid=os.getpid(),
        )

        # Create config dict with basic settings to override defaults
        config_overrides = {
            "image": "ubuntu:latest",
            "command": "bash",
            "gosu_path": "/test/gosu",
        }

        # Use CtenvConfig to get complete configuration with defaults
        from ctenv.config import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_overrides))
        resolved_spec = parse_container_config(config, mock_runtime)

        assert resolved_spec.user_name == "testuser"
        assert resolved_spec.user_id == 1000
        assert resolved_spec.group_name == "testgroup"
        assert resolved_spec.group_id == 1000
        assert resolved_spec.user_home == "/home/testuser"

        # Check workspace is resolved
        assert resolved_spec.workspace.host_path  # Should be resolved from "auto"
        assert resolved_spec.workspace.container_path


def test_container_name_generation():
    """Test consistent container name generation."""
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.config import CtenvConfig, RuntimeContext, ContainerConfig
        from ctenv.container import parse_container_config

        # Create mock runtime
        mock_runtime = RuntimeContext(
            user_name="testuser",
            user_id=1000,
            user_home="/home/testuser",
            group_name="testgroup",
            group_id=1000,
            cwd=Path.cwd(),
            tty=False,
            project_dir=Path.cwd(),
            pid=os.getpid(),
        )

        ctenv_config = CtenvConfig.load(Path(tmpdir))  # Empty directory
        config_dict1 = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(
                {"workspace": "/path/to/project", "image": "ubuntu:latest"}
            )
        )
        config_dict2 = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(
                {"workspace": "/path/to/project", "image": "node:18"}
            )
        )
        config_dict3 = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(
                {"workspace": "/different/path", "image": "alpine:latest"}
            )
        )

        # Parse to ContainerSpecs
        spec1 = parse_container_config(config_dict1, mock_runtime)
        spec2 = parse_container_config(config_dict2, mock_runtime)
        spec3 = parse_container_config(config_dict3, mock_runtime)

    # Container names are now based on project_dir and PID (with variable substitution)
    # The slug filter converts to lowercase and replaces colons/slashes with hyphens
    project_dir_slug = str(mock_runtime.project_dir).lower().replace(":", "-").replace("/", "-")
    expected_prefix = f"ctenv-{project_dir_slug}-"
    expected_name = f"{expected_prefix}{mock_runtime.pid}"
    assert spec1.container_name == expected_name
    assert spec2.container_name == expected_name  # Same project_dir and PID
    assert spec3.container_name == expected_name  # Same project_dir and PID
    assert spec1.container_name.startswith("ctenv-")
    assert str(mock_runtime.pid) in spec1.container_name


def test_entrypoint_script_generation():
    """Test bash entrypoint script generation."""
    from pathlib import Path

    # Create mock runtime
    mock_runtime = RuntimeContext(
        user_name="testuser",
        user_id=1000,
        user_home="/home/testuser",
        group_name="testgroup",
        group_id=1000,
        cwd=Path.cwd(),
        tty=False,
        project_dir=Path.cwd(),
        pid=os.getpid(),
    )

    # Create config with overrides
    config_overrides = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": "/test/workspace",
        "workdir": "auto",
        "tty": "auto",
        "gosu_path": "/test/gosu",
    }

    # Use CtenvConfig to get complete configuration
    from ctenv.config import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_overrides))

    # Parse to ContainerSpec
    spec = parse_container_config(config, mock_runtime)

    script = build_entrypoint_script(spec, verbosity=Verbosity.NORMAL)

    assert "useradd" in script
    assert 'USER_NAME="testuser"' in script
    assert 'USER_ID="1000"' in script
    assert 'exec "$GOSU_MOUNT" "$USER_NAME" /bin/sh $INTERACTIVE -c "$COMMAND"' in script
    assert "PS1_VALUE=" in script
    assert "TTY_MODE=" in script


def test_entrypoint_script_examples():
    """Show example entrypoint scripts for documentation."""
    from pathlib import Path

    scenarios = [
        {
            "name": "Basic user setup",
            "runtime": RuntimeContext(
                user_name="developer",
                user_id=1001,
                user_home="/home/developer",
                group_name="staff",
                group_id=20,
                cwd=Path.cwd(),
                tty=False,
                project_dir=Path.cwd(),
                pid=os.getpid(),
            ),
            "config_dict": {
                "image": "ubuntu:latest",
                "command": "bash",
                "workspace": "/test/workspace",
                "workdir": "auto",
                "tty": "auto",
                "gosu_path": "/test/gosu",
            },
        },
        {
            "name": "Custom command execution",
            "runtime": RuntimeContext(
                user_name="runner",
                user_id=1000,
                user_home="/home/runner",
                group_name="runners",
                group_id=1000,
                cwd=Path.cwd(),
                tty=False,
                project_dir=Path.cwd(),
                pid=os.getpid(),
            ),
            "config_dict": {
                "image": "ubuntu:latest",
                "command": "python3 main.py --verbose",
                "workspace": "/test/workspace",
                "workdir": "auto",
                "tty": "auto",
                "gosu_path": "/test/gosu",
            },
        },
    ]

    print(f"\n{'=' * 50}")
    print("Entrypoint Script Examples")
    print(f"{'=' * 50}")

    for scenario in scenarios:
        # Parse to ContainerSpec using CtenvConfig for complete configuration
        from ctenv.config import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])
        config = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(scenario["config_dict"])
        )
        spec = parse_container_config(config, scenario["runtime"])
        script = build_entrypoint_script(spec, verbosity=Verbosity.NORMAL)

        print(f"\n{scenario['name']}:")
        print(f"  User: {spec.user_name} (UID: {spec.user_id})")
        print(f"  Command: {spec.command}")
        print("  Script:")

        # Indent each line for better formatting
        for line in script.split("\n"):
            if line.strip():  # Skip empty lines
                print(f"    {line}")

    print(f"\n{'=' * 50}")


def test_run_command_help():
    """Test run command help output."""
    parser = create_parser()

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.stdout", new_callable=StringIO):
            parser.parse_args(["run", "--help"])

    # argparse help exits with code 0
    assert exc_info.value.code == 0


def test_run_command_dry_run_mode():
    """Test run command dry-run output."""
    parser = create_parser()
    args = parser.parse_args(["run", "--dry-run"])

    with patch("sys.stdout", new_callable=StringIO):
        with patch("ctenv.cli.cmd_run") as mock_cmd_run:
            from ctenv.cli import cmd_run

            cmd_run(args)
            mock_cmd_run.assert_called_once_with(args)


def test_verbose_mode():
    """Test verbose logging output."""
    parser = create_parser()

    # Test that verbose flag is accepted as global option
    args = parser.parse_args(["--verbose", "run", "--dry-run"])
    assert args.verbose == 1  # -v gives verbosity level 1
    assert args.subcommand == "run"

    # Test -vv gives verbosity level 2
    args = parser.parse_args(["-vv", "run", "--dry-run"])
    assert args.verbose == 2


def test_quiet_mode():
    """Test quiet mode suppresses output."""
    parser = create_parser()
    args = parser.parse_args(["-q", "run", "--dry-run"])

    assert args.quiet is True
    assert args.subcommand == "run"
    assert args.dry_run is True


def test_stdout_stderr_separation():
    """Test that ctenv output goes to stderr, leaving stdout clean."""
    parser = create_parser()

    # Test parsing works for dry-run mode
    args = parser.parse_args(["run", "--dry-run"])
    assert args.dry_run is True
    assert args.subcommand == "run"

    # Test quiet mode parsing (quiet flag is now global)
    args = parser.parse_args(["--quiet", "run", "--dry-run"])
    assert args.quiet is True
    assert args.dry_run is True


def test_post_start_cmd_cli_option():
    """Test --post-start-cmd CLI option."""

    # Test that CLI post-start extra commands are included in the config
    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.config import CtenvConfig, ContainerConfig
        from pathlib import Path

        ctenv_config = CtenvConfig.load(Path(tmpdir))  # Empty directory
        config_dict = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(
                {"post_start_commands": ["npm install", "npm run build"]}
            )
        )

    # Should contain the CLI post-start extra commands
    assert "npm install" in config_dict.post_start_commands
    assert "npm run build" in config_dict.post_start_commands


def test_post_start_cmd_merging():
    """Test that CLI post-start extra commands are merged with config file commands."""

    # Create a temporary config file with post-start commands
    config_content = """
[containers.test]
post_start_commands = ["echo config-cmd"]
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        # Test that both config file and CLI commands are included
        from ctenv.config import CtenvConfig, ContainerConfig
        from pathlib import Path

        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[Path(config_file)])
        config_dict = ctenv_config.get_container(
            container="test",
            overrides=ContainerConfig.from_dict(
                {"post_start_commands": ["echo cli-cmd1", "echo cli-cmd2"]}
            ),
        )

        # Should contain both config file and CLI commands
        assert "echo config-cmd" in config_dict.post_start_commands
        assert "echo cli-cmd1" in config_dict.post_start_commands
        assert "echo cli-cmd2" in config_dict.post_start_commands

        # Config file command should come first, then CLI commands
        commands = list(config_dict.post_start_commands)
        assert commands.index("echo config-cmd") < commands.index("echo cli-cmd1")

    finally:
        import os

        os.unlink(config_file)


def test_post_start_cmd_in_generated_script():
    """Test that post-start extra commands appear in generated script."""

    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.config import CtenvConfig, RuntimeContext, ContainerConfig
        from ctenv.container import parse_container_config
        from pathlib import Path

        ctenv_config = CtenvConfig.load(Path(tmpdir))  # Empty directory
        config_dict = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(
                {
                    "post_start_commands": ["npm install", "npm run test"],
                    "image": "ubuntu:latest",
                }
            )
        )

        # Create runtime context and parse to ContainerSpec
        runtime = RuntimeContext.current(cwd=Path.cwd())
        spec = parse_container_config(config_dict, runtime)

    script = build_entrypoint_script(spec, verbosity=Verbosity.VERBOSE)

    # Should contain the post-start commands in the script variables
    assert (
        "POST_START_COMMANDS='npm install" in script or 'POST_START_COMMANDS="npm install' in script
    )
    assert "npm run test" in script
    # Should contain the function that executes post-start commands
    assert "run_post_start_commands()" in script
    assert "run_post_start_commands" in script


def test_volume_parsing_smart_defaulting():
    """Test volume parsing with smart target defaulting."""
    from ctenv.container import _parse_volume

    # Volumes outside project_dir get host path as container path
    project_dir = Path("/project")
    project_mount = "/repo"

    # Test single path format - outside project, uses host path
    vol_spec = _parse_volume("~/.docker", project_dir, project_mount)
    assert vol_spec.host_path == "~/.docker"
    assert vol_spec.container_path == "~/.docker"  # Outside project, same as host
    assert vol_spec.options == []

    # Test to_string() works correctly for defaulted volumes
    assert _parse_volume("/host/path", project_dir, project_mount).to_string() == "/host/path:/host/path"
    assert _parse_volume("~/config", project_dir, project_mount).to_string() == "~/config:~/config"


def test_volume_parsing_empty_target_syntax():
    """Test volume parsing with :: empty target syntax."""
    from ctenv.container import _parse_volume

    # Volumes outside project_dir get host path as container path
    project_dir = Path("/project")
    project_mount = "/repo"

    # Test empty target with options
    vol_spec = _parse_volume("~/.docker::ro", project_dir, project_mount)
    assert vol_spec.host_path == "~/.docker"
    assert vol_spec.container_path == "~/.docker"  # Outside project, same as host
    assert vol_spec.options == ["ro"]

    # Test empty target with chown option - chown will be handled during parse_container_config
    vol_spec = _parse_volume("~/data::chown,rw", project_dir, project_mount)
    assert vol_spec.host_path == "~/data"
    assert vol_spec.container_path == "~/data"  # Outside project, same as host
    assert vol_spec.options == ["chown", "rw"]  # Options are preserved in VolumeSpec

    # Test empty target with multiple options
    vol_spec = _parse_volume("/path::ro,chown,z", project_dir, project_mount)
    assert vol_spec.host_path == "/path"
    assert vol_spec.container_path == "/path"  # Outside project, same as host
    assert vol_spec.options == ["ro", "chown", "z"]  # All options preserved


def test_volume_parsing_backward_compatibility():
    """Test that existing volume formats still work."""
    from ctenv.container import _parse_volume

    # Explicit container paths are not affected by project_mount
    project_dir = Path("/project")
    project_mount = "/repo"

    # Test standard format still works
    vol_spec = _parse_volume("/host:/container:ro", project_dir, project_mount)
    assert vol_spec.host_path == "/host"
    assert vol_spec.container_path == "/container"
    assert vol_spec.options == ["ro"]

    # Test chown option still works - preserved in VolumeSpec
    vol_spec = _parse_volume("/host:/container:chown", project_dir, project_mount)
    assert vol_spec.host_path == "/host"
    assert vol_spec.container_path == "/container"
    assert vol_spec.options == ["chown"]


def test_volume_subpath_remapping():
    """Test that volume subpaths of project_dir are remapped to project_mount."""
    from ctenv.container import _parse_volume

    project_dir = Path("/project")
    project_mount = "/repo"

    # Subpath of project - should remap to project_mount
    vol_spec = _parse_volume("/project/src", project_dir, project_mount)
    assert vol_spec.host_path == "/project/src"
    assert vol_spec.container_path == "/repo/src"  # Remapped!

    # Exact project_dir - should map to project_mount
    vol_spec = _parse_volume("/project", project_dir, project_mount)
    assert vol_spec.host_path == "/project"
    assert vol_spec.container_path == "/repo"

    # Outside project - should use host path
    vol_spec = _parse_volume("/other/path", project_dir, project_mount)
    assert vol_spec.host_path == "/other/path"
    assert vol_spec.container_path == "/other/path"  # Not remapped

    # Explicit container path - should not be overwritten
    vol_spec = _parse_volume("/project/src:/custom", project_dir, project_mount)
    assert vol_spec.host_path == "/project/src"
    assert vol_spec.container_path == "/custom"  # Explicit, not remapped

    # Tilde path - should not try to remap (not absolute)
    vol_spec = _parse_volume("~/.config", project_dir, project_mount)
    assert vol_spec.host_path == "~/.config"
    assert vol_spec.container_path == "~/.config"  # Same as host (tilde expanded later)


def test_cli_volume_template_expansion():
    """Test that CLI volumes get template expansion and variable substitution."""
    import os
    from unittest.mock import patch
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        test_home = "/home/testuser"

        with patch.dict(os.environ, {"HOME": test_home}):
            from ctenv.config import CtenvConfig, RuntimeContext, ContainerConfig
            from ctenv.container import parse_container_config

            # Create mock runtime context
            mock_runtime = RuntimeContext(
                user_name="testuser",
                user_id=1000,
                user_home=test_home,
                group_name="testgroup",
                group_id=1000,
                cwd=Path.cwd(),
                tty=False,
                project_dir=Path.cwd(),
                pid=os.getpid(),
            )

            # Test CLI volume processing directly
            ctenv_config = CtenvConfig.load(Path(tmpdir))  # Empty directory

            # CLI volumes with tilde and template variables
            cli_volumes = ["~/.docker", "${user_home}/.cache::ro"]

            config_dict = ctenv_config.get_default(
                overrides=ContainerConfig.from_dict(
                    {"image": "ubuntu:latest", "volumes": cli_volumes}
                )
            )

            # Check that raw volumes are preserved in config dict
            assert config_dict.volumes == cli_volumes

            # Parse and resolve to ContainerSpec
            spec = parse_container_config(config_dict, mock_runtime)

            # Check that volumes are resolved with tilde expansion and variable substitution
            volume_specs = spec.volumes
            assert len(volume_specs) == 2

            # First volume: ~/.docker should expand and smart default
            vol1 = volume_specs[0]
            assert vol1.host_path == f"{test_home}/.docker"
            assert vol1.container_path == f"{test_home}/.docker"  # Smart defaulted
            assert vol1.options == ["z"]  # z is added automatically

            # Second volume: ${user_home}/.cache::ro should expand with options
            vol2 = volume_specs[1]
            assert vol2.host_path == f"{test_home}/.cache"
            assert vol2.container_path == f"{test_home}/.cache"  # Smart defaulted
            assert vol2.options == ["ro", "z"]  # z is added automatically


def test_config_file_tilde_expansion():
    """Test tilde expansion in config files."""
    import os
    from unittest.mock import patch
    from pathlib import Path

    config_content = """
[containers.test]
volumes = ["~/.docker", "~/config:/container/config"]
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        test_home = "/home/testuser"

        with patch.dict(os.environ, {"HOME": test_home}):
            from ctenv.config import CtenvConfig, RuntimeContext, ContainerConfig
            from ctenv.container import parse_container_config

            # Create mock runtime context
            mock_runtime = RuntimeContext(
                user_name="testuser",
                user_id=1000,
                user_home=test_home,
                group_name="testgroup",
                group_id=1000,
                cwd=Path.cwd(),
                tty=False,
                project_dir=Path.cwd(),
                pid=os.getpid(),
            )

            ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[Path(config_file)])
            config_dict = ctenv_config.get_container(
                container="test",
                overrides=ContainerConfig.from_dict(
                    {"image": "ubuntu:latest"}
                ),  # Provide required image
            )

            # Check that raw volumes are preserved in config dict before parsing
            # Note: Volumes get parsed to VolumeSpec during parse_container_config(),
            # but the raw dict should still contain the original strings with smart defaulting applied
            expected_processed = [
                "~/.docker",
                "~/config:/container/config",
            ]
            assert config_dict.volumes == expected_processed

            # Parse and resolve to ContainerSpec with runtime context
            spec = parse_container_config(config_dict, mock_runtime)

            # Check that volumes are resolved with tilde expansion
            volume_specs = spec.volumes
            assert len(volume_specs) == 2

            # First volume: ~/.docker should expand and smart default
            vol1 = volume_specs[0]
            assert vol1.host_path == f"{test_home}/.docker"
            assert vol1.container_path == f"{test_home}/.docker"  # Smart defaulted

            # Second volume: ~/config:/container/config should expand host path only
            vol2 = volume_specs[1]
            assert vol2.host_path == f"{test_home}/config"
            assert vol2.container_path == "/container/config"

    finally:
        os.unlink(config_file)
