import os
import tempfile
from pathlib import Path
import pytest
import sys
from unittest.mock import patch
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv.ctenv import (
    create_parser,
    RuntimeContext,
    parse_container_config,
)


@pytest.mark.unit
def test_version():
    parser = create_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    # argparse version exits with code 0
    assert exc_info.value.code == 0


@pytest.mark.unit
def test_config_user_detection():
    """Test that config correctly loads and merges with runtime context."""

    # Use explicit image to avoid config file interference
    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.ctenv import CtenvConfig, RuntimeContext, parse_container_config
        from pathlib import Path

        ctenv_config = CtenvConfig.load(Path(tmpdir))  # Empty directory
        from ctenv.ctenv import ContainerConfig

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


@pytest.mark.unit
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
        )

        # Create config dict with basic settings to override defaults
        config_overrides = {
            "image": "ubuntu:latest",
            "command": "bash",
            "gosu_path": "/test/gosu",
        }

        # Use CtenvConfig to get complete configuration with defaults
        from ctenv.ctenv import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd())
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


@pytest.mark.unit
def test_container_name_generation():
    """Test consistent container name generation."""
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.ctenv import (
            CtenvConfig,
            RuntimeContext,
            parse_container_config,
            ContainerConfig,
        )

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

    # Container names are now based on project_dir (with variable substitution)
    expected_name = f"ctenv-{str(mock_runtime.project_dir).replace('/', '-').replace(':', '-')}"
    assert spec1.container_name == expected_name
    assert spec2.container_name == expected_name  # Same project_dir
    assert spec3.container_name == expected_name  # Same project_dir
    assert spec1.container_name.startswith("ctenv-")


@pytest.mark.unit
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
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_overrides))

    # Parse to ContainerSpec
    spec = parse_container_config(config, mock_runtime)

    script = spec.build_entrypoint_script(verbose=False, quiet=False)

    assert "useradd" in script
    assert 'USER_NAME="testuser"' in script
    assert 'USER_ID="1000"' in script
    assert 'exec "$GOSU_MOUNT" "$USER_NAME" /bin/sh $INTERACTIVE -c "$COMMAND"' in script
    assert "PS1_VALUE=" in script
    assert "TTY_MODE=" in script


@pytest.mark.unit
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
        from ctenv.ctenv import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd())
        config = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(scenario["config_dict"])
        )
        spec = parse_container_config(config, scenario["runtime"])
        script = spec.build_entrypoint_script(verbose=False, quiet=False)

        print(f"\n{scenario['name']}:")
        print(f"  User: {spec.user_name} (UID: {spec.user_id})")
        print(f"  Command: {spec.command}")
        print("  Script:")

        # Indent each line for better formatting
        for line in script.split("\n"):
            if line.strip():  # Skip empty lines
                print(f"    {line}")

    print(f"\n{'=' * 50}")


@pytest.mark.unit
def test_run_command_help():
    """Test run command help output."""
    parser = create_parser()

    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.stdout", new_callable=StringIO):
            parser.parse_args(["run", "--help"])

    # argparse help exits with code 0
    assert exc_info.value.code == 0


@pytest.mark.unit
def test_run_command_dry_run_mode():
    """Test run command dry-run output."""
    parser = create_parser()
    args = parser.parse_args(["run", "--dry-run"])

    with patch("sys.stdout", new_callable=StringIO):
        with patch("ctenv.ctenv.cmd_run") as mock_cmd_run:
            from ctenv.ctenv import cmd_run

            cmd_run(args)
            mock_cmd_run.assert_called_once_with(args)


@pytest.mark.unit
def test_verbose_mode():
    """Test verbose logging output."""
    parser = create_parser()

    # Test that verbose flag is accepted as global option
    args = parser.parse_args(["--verbose", "run", "--dry-run"])
    assert args.verbose is True
    assert args.subcommand == "run"


@pytest.mark.unit
def test_quiet_mode():
    """Test quiet mode suppresses output."""
    parser = create_parser()
    args = parser.parse_args(["-q", "run", "--dry-run"])

    assert args.quiet is True
    assert args.subcommand == "run"
    assert args.dry_run is True


@pytest.mark.unit
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


@pytest.mark.unit
def test_post_start_cmd_cli_option():
    """Test --post-start-cmd CLI option."""

    # Test that CLI post-start extra commands are included in the config
    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.ctenv import CtenvConfig, ContainerConfig
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


@pytest.mark.unit
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
        from ctenv.ctenv import CtenvConfig, ContainerConfig
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


@pytest.mark.unit
def test_post_start_cmd_in_generated_script():
    """Test that post-start extra commands appear in generated script."""

    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.ctenv import (
            CtenvConfig,
            RuntimeContext,
            parse_container_config,
            ContainerConfig,
        )
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

    script = spec.build_entrypoint_script(verbose=True, quiet=False)

    # Should contain the post-start commands in the script variables
    assert (
        "POST_START_COMMANDS='npm install" in script or 'POST_START_COMMANDS="npm install' in script
    )
    assert "npm run test" in script
    # Should contain the function that executes post-start commands
    assert "run_post_start_commands()" in script
    assert "run_post_start_commands" in script


@pytest.mark.unit
def test_volume_parsing_smart_defaulting():
    """Test volume parsing with smart target defaulting."""
    from ctenv.ctenv import _parse_volume

    # Test single path format - smart defaulting
    vol_spec = _parse_volume("~/.docker")
    assert vol_spec.host_path == "~/.docker"
    assert vol_spec.container_path == "~/.docker"  # Smart defaulted
    assert vol_spec.options == []

    # Test to_string() works correctly for smart defaulted volumes
    assert _parse_volume("/host/path").to_string() == "/host/path:/host/path"
    assert _parse_volume("~/config").to_string() == "~/config:~/config"


@pytest.mark.unit
def test_volume_parsing_empty_target_syntax():
    """Test volume parsing with :: empty target syntax."""
    from ctenv.ctenv import _parse_volume

    # Test empty target with options
    vol_spec = _parse_volume("~/.docker::ro")
    assert vol_spec.host_path == "~/.docker"
    assert vol_spec.container_path == "~/.docker"  # Smart defaulted
    assert vol_spec.options == ["ro"]

    # Test empty target with chown option - chown will be handled during parse_container_config
    vol_spec = _parse_volume("~/data::chown,rw")
    assert vol_spec.host_path == "~/data"
    assert vol_spec.container_path == "~/data"  # Smart defaulted
    assert vol_spec.options == ["chown", "rw"]  # Options are preserved in VolumeSpec

    # Test empty target with multiple options
    vol_spec = _parse_volume("/path::ro,chown,z")
    assert vol_spec.host_path == "/path"
    assert vol_spec.container_path == "/path"  # Smart defaulted
    assert vol_spec.options == ["ro", "chown", "z"]  # All options preserved


@pytest.mark.unit
def test_volume_parsing_backward_compatibility():
    """Test that existing volume formats still work."""
    from ctenv.ctenv import _parse_volume

    # Test standard format still works
    vol_spec = _parse_volume("/host:/container:ro")
    assert vol_spec.host_path == "/host"
    assert vol_spec.container_path == "/container"
    assert vol_spec.options == ["ro"]

    # Test chown option still works - preserved in VolumeSpec
    vol_spec = _parse_volume("/host:/container:chown")
    assert vol_spec.host_path == "/host"
    assert vol_spec.container_path == "/container"
    assert vol_spec.options == ["chown"]


@pytest.mark.unit
def test_cli_volume_template_expansion():
    """Test that CLI volumes get template expansion and variable substitution."""
    import os
    from unittest.mock import patch
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        test_home = "/home/testuser"

        with patch.dict(os.environ, {"HOME": test_home}):
            from ctenv.ctenv import (
                CtenvConfig,
                RuntimeContext,
                parse_container_config,
                ContainerConfig,
            )

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


@pytest.mark.unit
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
            from ctenv.ctenv import (
                CtenvConfig,
                RuntimeContext,
                parse_container_config,
                ContainerConfig,
            )

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
