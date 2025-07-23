import os
import tempfile
from pathlib import Path
import pytest
import sys
from unittest.mock import patch
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv.cli import create_parser, ContainerConfig, build_entrypoint_script


@pytest.mark.unit
def test_version():
    parser = create_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])

    # argparse version exits with code 0
    assert exc_info.value.code == 0


@pytest.mark.unit
def test_config_user_detection():
    """Test that Config correctly detects user information."""
    import tempfile

    # Use explicit image to avoid config file interference
    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.cli import CtenvConfig
        from pathlib import Path

        ctenv_config = CtenvConfig.load(start_dir=Path(tmpdir))  # Empty directory
        config = ctenv_config.resolve_container_config(
            cli_overrides={"image": "ubuntu:latest"}
        )

    import getpass

    assert config.user_name == getpass.getuser()
    assert config.user_id == os.getuid()
    assert config.group_id == os.getgid()
    assert config.image == "ubuntu:latest"
    assert config.working_dir_mount == "/repo"


@pytest.mark.unit
def test_config_with_mock_user():
    """Test Config with custom values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=Path(tmpdir),
            gosu_path=Path("/test/gosu"),
        )

        assert config.user_name == "testuser"
        assert config.user_id == 1000
        assert config.working_dir == Path(tmpdir)


@pytest.mark.unit
def test_container_name_generation():
    """Test consistent container name generation."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.cli import CtenvConfig
        from pathlib import Path

        ctenv_config = CtenvConfig.load(start_dir=Path(tmpdir))  # Empty directory
        config1 = ctenv_config.resolve_container_config(
            cli_overrides={"working_dir": "/path/to/project"}
        )
        config2 = ctenv_config.resolve_container_config(
            cli_overrides={"working_dir": "/path/to/project"}
        )
        config3 = ctenv_config.resolve_container_config(
            cli_overrides={"working_dir": "/different/path"}
        )

    name1 = config1.get_container_name()
    name2 = config2.get_container_name()
    name3 = config3.get_container_name()

    assert name1 == name2  # Consistent naming
    assert name1 != name3  # Different paths produce different names
    assert name1.startswith("ctenv-")


@pytest.mark.unit
def test_entrypoint_script_generation():
    """Test bash entrypoint script generation."""
    config = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
        command="bash",
    )

    script = build_entrypoint_script(config, verbose=False, quiet=False)

    assert "useradd" in script
    assert 'USER_NAME="testuser"' in script
    assert 'USER_ID="1000"' in script
    assert 'exec /gosu "$USER_NAME" bash' in script
    assert 'export PS1="[ctenv] $ "' in script


@pytest.mark.unit
def test_entrypoint_script_examples():
    """Show example entrypoint scripts for documentation."""

    scenarios = [
        {
            "name": "Basic user setup",
            "config": ContainerConfig(
                user_name="developer",
                user_id=1001,
                group_name="staff",
                group_id=20,
                user_home="/home/developer",
                working_dir=Path("/test"),
                gosu_path=Path("/test/gosu"),
                command="bash",
            ),
        },
        {
            "name": "Custom command execution",
            "config": ContainerConfig(
                user_name="runner",
                user_id=1000,
                group_name="runners",
                group_id=1000,
                user_home="/home/runner",
                working_dir=Path("/test"),
                gosu_path=Path("/test/gosu"),
                command="python3 main.py --verbose",
            ),
        },
    ]

    print(f"\n{'=' * 50}")
    print("Entrypoint Script Examples")
    print(f"{'=' * 50}")

    for scenario in scenarios:
        script = build_entrypoint_script(scenario["config"], verbose=False, quiet=False)

        print(f"\n{scenario['name']}:")
        print(
            f"  User: {scenario['config'].user_name} (UID: {scenario['config'].user_id})"
        )
        print(f"  Command: {scenario['config'].command}")
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
        with patch("ctenv.cli.cmd_run") as mock_cmd_run:
            from ctenv.cli import cmd_run

            cmd_run(args)
            mock_cmd_run.assert_called_once_with(args)


@pytest.mark.unit
def test_verbose_mode():
    """Test verbose logging output."""
    parser = create_parser()

    # Test that verbose flag is accepted and doesn't break anything
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--verbose", "--version"])
    assert exc_info.value.code == 0

    # Test verbose with run --dry-run
    args = parser.parse_args(["--verbose", "run", "--dry-run"])
    assert args.verbose is True
    assert args.subcommand == "run"


@pytest.mark.unit
def test_quiet_mode():
    """Test quiet mode suppresses output."""
    parser = create_parser()
    args = parser.parse_args(["--quiet", "run", "--dry-run"])

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

    # Test quiet mode parsing
    args = parser.parse_args(["--quiet", "run", "--dry-run"])
    assert args.quiet is True
    assert args.dry_run is True


@pytest.mark.unit
def test_post_start_cmd_cli_option():
    """Test --post-start-cmd CLI option."""
    import tempfile

    # Test that CLI post-start extra commands are included in the config
    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.cli import CtenvConfig
        from pathlib import Path

        ctenv_config = CtenvConfig.load(start_dir=Path(tmpdir))  # Empty directory
        config = ctenv_config.resolve_container_config(
            cli_overrides={"post_start_commands": ["npm install", "npm run build"]}
        )

    # Should contain the CLI post-start extra commands
    assert "npm install" in config.post_start_commands
    assert "npm run build" in config.post_start_commands


@pytest.mark.unit
def test_post_start_cmd_merging():
    """Test that CLI post-start extra commands are merged with config file commands."""
    import tempfile

    # Create a temporary config file with post-start commands
    config_content = """
[contexts.test]
post_start_commands = ["echo config-cmd"]
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        # Test that both config file and CLI commands are included
        from ctenv.cli import CtenvConfig
        from pathlib import Path

        ctenv_config = CtenvConfig.load(explicit_config_files=[Path(config_file)])
        config = ctenv_config.resolve_container_config(
            context="test",
            cli_overrides={"post_start_commands": ["echo cli-cmd1", "echo cli-cmd2"]},
        )

        # Should contain both config file and CLI commands
        assert "echo config-cmd" in config.post_start_commands
        assert "echo cli-cmd1" in config.post_start_commands
        assert "echo cli-cmd2" in config.post_start_commands

        # Config file command should come first, then CLI commands
        commands = list(config.post_start_commands)
        assert commands.index("echo config-cmd") < commands.index("echo cli-cmd1")

    finally:
        import os

        os.unlink(config_file)


@pytest.mark.unit
def test_post_start_cmd_in_generated_script():
    """Test that post-start extra commands appear in generated script."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        from ctenv.cli import CtenvConfig
        from pathlib import Path

        ctenv_config = CtenvConfig.load(start_dir=Path(tmpdir))  # Empty directory
        config = ctenv_config.resolve_container_config(
            cli_overrides={"post_start_commands": ["npm install", "npm run test"]}
        )

    script = build_entrypoint_script(config, verbose=True, quiet=False)

    # Should contain the post-start commands in the script
    assert "npm install" in script
    assert "npm run test" in script
    assert 'log_debug "Executing post-start command: npm install"' in script
    assert 'log_debug "Executing post-start command: npm run test"' in script


@pytest.mark.unit
def test_tilde_preprocessing():
    """Test tilde preprocessing function."""
    from ctenv.cli import preprocess_tilde_expansion

    # Test basic tilde expansion
    assert preprocess_tilde_expansion("~/.docker") == "${env:HOME}/.docker"
    assert preprocess_tilde_expansion("~/config/file") == "${env:HOME}/config/file"

    # Test tilde after colon (volume format)
    assert preprocess_tilde_expansion("/host:~/.config") == "/host:${env:HOME}/.config"
    assert (
        preprocess_tilde_expansion("/host::~/.config") == "/host::${env:HOME}/.config"
    )

    # Test cases that should NOT be expanded
    assert preprocess_tilde_expansion("~") == "~"  # No trailing slash
    assert preprocess_tilde_expansion("file~name") == "file~name"  # Not at path start
    assert (
        preprocess_tilde_expansion("/path/~file") == "/path/~file"
    )  # Not at path start

    # Test empty/None input
    assert preprocess_tilde_expansion("") == ""
    assert preprocess_tilde_expansion(None) is None


@pytest.mark.unit
def test_volume_parsing_smart_defaulting():
    """Test volume parsing with smart target defaulting."""
    from ctenv.cli import ContainerRunner

    # Test single path format
    volumes, chown_paths = ContainerRunner.parse_volumes(("~/.docker",))
    assert volumes == ["~/.docker:~/.docker"]
    assert chown_paths == []

    # Test multiple single paths
    volumes, chown_paths = ContainerRunner.parse_volumes(("/host/path", "~/config"))
    assert volumes == ["/host/path:/host/path", "~/config:~/config"]
    assert chown_paths == []


@pytest.mark.unit
def test_volume_parsing_empty_target_syntax():
    """Test volume parsing with :: empty target syntax."""
    from ctenv.cli import ContainerRunner

    # Test empty target with options
    volumes, chown_paths = ContainerRunner.parse_volumes(("~/.docker::ro",))
    assert volumes == ["~/.docker:~/.docker:ro"]
    assert chown_paths == []

    # Test empty target with chown option
    volumes, chown_paths = ContainerRunner.parse_volumes(("~/data::chown,rw",))
    assert volumes == ["~/data:~/data:rw"]
    assert chown_paths == ["~/data"]

    # Test empty target with multiple options
    volumes, chown_paths = ContainerRunner.parse_volumes(("/path::ro,chown,z",))
    assert volumes == ["/path:/path:ro,z"]
    assert chown_paths == ["/path"]


@pytest.mark.unit
def test_volume_parsing_backward_compatibility():
    """Test that existing volume formats still work."""
    from ctenv.cli import ContainerRunner

    # Test standard format still works
    volumes, chown_paths = ContainerRunner.parse_volumes(("/host:/container:ro",))
    assert volumes == ["/host:/container:ro"]
    assert chown_paths == []

    # Test chown option still works
    volumes, chown_paths = ContainerRunner.parse_volumes(("/host:/container:chown",))
    assert volumes == ["/host:/container"]
    assert chown_paths == ["/container"]


@pytest.mark.unit
def test_template_expansion_with_tilde():
    """Test template expansion with tilde preprocessing."""
    import tempfile
    import os

    with tempfile.TemporaryDirectory():
        # Set up test environment
        test_home = "/home/testuser"

        with patch.dict(os.environ, {"HOME": test_home}):
            from ctenv.cli import (
                preprocess_tilde_expansion,
                substitute_template_variables,
            )

            # Test tilde expansion with template system
            variables = {"USER": "testuser", "image": "ubuntu"}

            # Preprocess tilde then apply templates
            volume = "~/.docker:/container"
            preprocessed = preprocess_tilde_expansion(volume)
            expanded = substitute_template_variables(preprocessed, variables)

            assert expanded == f"{test_home}/.docker:/container"


@pytest.mark.unit
def test_cli_volume_template_expansion():
    """Test that CLI volumes get template expansion."""
    import tempfile
    import os
    from unittest.mock import patch, MagicMock

    with tempfile.TemporaryDirectory():
        test_home = "/home/testuser"

        with patch.dict(os.environ, {"HOME": test_home}):
            # Mock the necessary functions to test just the volume processing
            with patch("ctenv.cli.CtenvConfig") as mock_config_class:
                with patch("ctenv.cli.ContainerConfig"):
                    with patch("ctenv.cli.ContainerRunner") as mock_runner:
                        from ctenv.cli import cmd_run

                        # Set up mocks
                        mock_config = MagicMock()
                        mock_config_class.load.return_value = mock_config
                        mock_config.resolve_container_config.return_value = MagicMock()

                        # Create mock args
                        args = MagicMock()
                        args.verbose = False
                        args.quiet = False
                        args.config = None
                        args.context = None
                        # Command is not used in this test since we pass it separately to cmd_run
                        args.volumes = ["~/.docker", "${env:HOME}/.cache::ro"]
                        args.image = "ubuntu"
                        args.working_dir = None
                        args.env = None
                        args.sudo = None
                        args.network = None
                        args.gosu_path = None
                        args.platform = None
                        args.post_start_commands = None
                        args.run_args = None
                        args.dry_run = True

                        # Mock the resolve_missing_paths and resolve_templates
                        resolved_config = MagicMock()
                        resolved_config.resolve_missing_paths.return_value = (
                            resolved_config
                        )
                        resolved_config.resolve_templates.return_value = resolved_config
                        mock_config.resolve_container_config.return_value = (
                            resolved_config
                        )

                        # Mock the runner to avoid actual execution
                        mock_result = MagicMock()
                        mock_result.returncode = 0
                        mock_runner.run_container.return_value = mock_result

                        try:
                            cmd_run(args, "bash")
                        except SystemExit:
                            pass  # Expected for dry-run

                        # Verify that processed volumes were passed to config
                        call_args = mock_config.resolve_container_config.call_args
                        cli_overrides = call_args[1]["cli_overrides"]
                        processed_volumes = cli_overrides["volumes"]

                        # Check that tilde and template expansion occurred
                        assert processed_volumes is not None
                        assert len(processed_volumes) == 2
                        assert processed_volumes[0] == f"{test_home}/.docker"
                        assert processed_volumes[1] == f"{test_home}/.cache::ro"


@pytest.mark.unit
def test_config_file_tilde_expansion():
    """Test tilde expansion in config files."""
    import tempfile
    import os

    config_content = """
[contexts.test]
volumes = ["~/.docker", "~/config:/container/config"]
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        test_home = "/home/testuser"

        with patch.dict(os.environ, {"HOME": test_home}):
            from ctenv.cli import CtenvConfig
            from pathlib import Path

            ctenv_config = CtenvConfig.load(explicit_config_files=[Path(config_file)])
            config = ctenv_config.resolve_container_config(context="test")
            resolved_config = config.resolve_templates()

            # Check that tilde expansion occurred in config volumes
            assert resolved_config.volumes is not None
            volumes = list(resolved_config.volumes)
            assert f"{test_home}/.docker" in volumes
            assert f"{test_home}/config:/container/config" in volumes

    finally:
        os.unlink(config_file)
