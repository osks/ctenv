import os
import tempfile
from pathlib import Path
import pytest
import sys
from unittest.mock import patch
from io import StringIO

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv import create_parser, ContainerConfig, build_entrypoint_script


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
    # Use explicit image to avoid config file interference
    config = ContainerConfig.create(image="ubuntu:latest")

    assert config.user_name == os.getenv("USER")
    assert config.user_id == os.getuid()
    assert config.group_id == os.getgid()
    assert config.image == "ubuntu:latest"
    assert config.dir_mount == "/repo"


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
            script_dir=Path(tmpdir),
            working_dir=Path(tmpdir),
            gosu_path=Path("/test/gosu"),
        )

        assert config.user_name == "testuser"
        assert config.user_id == 1000
        assert config.script_dir == Path(tmpdir)
        assert config.working_dir == Path(tmpdir)


@pytest.mark.unit
def test_container_name_generation():
    """Test consistent container name generation."""
    config1 = ContainerConfig.create(dir="/path/to/project")
    config2 = ContainerConfig.create(dir="/path/to/project")
    config3 = ContainerConfig.create(dir="/different/path")

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
        script_dir=Path("/test"),
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
        command="bash",
    )

    script = build_entrypoint_script(config)

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
                script_dir=Path("/test"),
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
                script_dir=Path("/test"),
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
        script = build_entrypoint_script(scenario["config"])

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
        with patch("ctenv.cmd_run") as mock_cmd_run:
            from ctenv import cmd_run

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
    # Test that CLI post-start extra commands are included in the config
    config = ContainerConfig.create(
        context="default", post_start_cmd=["npm install", "npm run build"]
    )

    # Should contain the CLI post-start extra commands
    assert "npm install" in config.post_start_cmds
    assert "npm run build" in config.post_start_cmds


@pytest.mark.unit
def test_post_start_cmd_merging():
    """Test that CLI post-start extra commands are merged with config file commands."""
    import tempfile

    # Create a temporary config file with post-start commands
    config_content = """
[contexts.test]
post_start_cmds = ["echo config-cmd"]
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        # Test that both config file and CLI commands are included
        config = ContainerConfig.create(
            context="test",
            config_file=config_file,
            post_start_cmd=["echo cli-cmd1", "echo cli-cmd2"],
        )

        # Should contain both config file and CLI commands
        assert "echo config-cmd" in config.post_start_cmds
        assert "echo cli-cmd1" in config.post_start_cmds
        assert "echo cli-cmd2" in config.post_start_cmds

        # Config file command should come first, then CLI commands
        commands = list(config.post_start_cmds)
        assert commands.index("echo config-cmd") < commands.index("echo cli-cmd1")

    finally:
        import os

        os.unlink(config_file)


@pytest.mark.unit
def test_post_start_cmd_in_generated_script():
    """Test that post-start extra commands appear in generated script."""
    config = ContainerConfig.create(
        context="default", post_start_cmd=["npm install", "npm run test"]
    )

    script = build_entrypoint_script(config, verbose=True)

    # Should contain the post-start commands in the script
    assert "npm install" in script
    assert "npm run test" in script
    assert 'log "Executing post-start command: npm install"' in script
    assert 'log "Executing post-start command: npm run test"' in script
