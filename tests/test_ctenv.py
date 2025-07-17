import os
import tempfile
from pathlib import Path
from click.testing import CliRunner
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv import cli, ContainerConfig, build_entrypoint_script


@pytest.mark.unit
def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1" in result.output


@pytest.mark.unit
def test_config_user_detection():
    """Test that Config correctly detects user information."""
    # Use explicit image to avoid config file interference
    config = ContainerConfig.from_cli_options(image="ubuntu:latest")

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
    config1 = ContainerConfig.from_cli_options(dir="/path/to/project")
    config2 = ContainerConfig.from_cli_options(dir="/path/to/project")
    config3 = ContainerConfig.from_cli_options(dir="/different/path")

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
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])

    assert result.exit_code == 0
    assert "--image" in result.output
    assert "Run command in container" in result.output


@pytest.mark.unit
def test_run_command_dry_run_mode():
    """Test run command dry-run output."""
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["run", "--dry-run"])

    assert result.exit_code == 0
    # Dry-run should show Docker command on stdout
    assert "docker run" in result.output
    assert "--rm" in result.output


@pytest.mark.unit
def test_verbose_mode():
    """Test verbose logging output."""
    runner = CliRunner(mix_stderr=False)

    # Test that verbose flag is accepted and doesn't break anything
    result = runner.invoke(cli, ["--verbose", "--version"])
    assert result.exit_code == 0
    assert "0.1" in result.output

    # Test verbose with run --dry-run
    result = runner.invoke(cli, ["--verbose", "run", "--dry-run"])
    assert result.exit_code == 0
    assert "docker run" in result.output  # Dry-run output goes to stdout
    # Note: verbose DEBUG logging may not show up in CliRunner tests
    # The main thing is that verbose mode doesn't break anything


@pytest.mark.unit
def test_quiet_mode():
    """Test quiet mode suppresses output."""
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["--quiet", "run", "--dry-run"])

    assert result.exit_code == 0
    # In quiet mode with dry-run, we should only see the dry-run output, not [ctenv] run
    assert "[ctenv] run" not in result.stderr
    assert "docker run" in result.output  # Dry-run output still shows


@pytest.mark.unit
def test_stdout_stderr_separation():
    """Test that ctenv output goes to stderr, leaving stdout clean."""
    runner = CliRunner(mix_stderr=False)

    # Test with dry-run mode
    result = runner.invoke(cli, ["run", "--dry-run"])
    assert result.exit_code == 0

    # stdout should contain Docker command
    assert "docker run" in result.output

    # stderr should contain ctenv status message
    assert "[ctenv] run" in result.stderr

    # Test with quiet mode too
    result = runner.invoke(cli, ["--quiet", "run", "--dry-run"])
    assert result.exit_code == 0

    # stdout should contain Docker command
    assert "docker run" in result.output

    # stderr should not contain [ctenv] run in quiet mode
    assert "[ctenv] run" not in result.stderr


@pytest.mark.unit
def test_entrypoint_cmd_cli_option():
    """Test --entrypoint-extra CLI option."""
    # Test that CLI entrypoint extra commands are included in the config
    config = ContainerConfig.from_cli_options(
        context="default", entrypoint_cmd=["npm install", "npm run build"]
    )

    # Should contain the CLI entrypoint extra commands
    assert "npm install" in config.entrypoint_commands
    assert "npm run build" in config.entrypoint_commands


@pytest.mark.unit
def test_entrypoint_cmd_merging():
    """Test that CLI entrypoint extra commands are merged with config file commands."""
    import tempfile

    # Create a temporary config file with entrypoint commands
    config_content = """
[contexts.test]
entrypoint_commands = ["echo config-cmd"]
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        # Test that both config file and CLI commands are included
        config = ContainerConfig.from_cli_options(
            context="test",
            config_file=config_file,
            entrypoint_cmd=["echo cli-cmd1", "echo cli-cmd2"],
        )

        # Should contain both config file and CLI commands
        assert "echo config-cmd" in config.entrypoint_commands
        assert "echo cli-cmd1" in config.entrypoint_commands
        assert "echo cli-cmd2" in config.entrypoint_commands

        # Config file command should come first, then CLI commands
        commands = list(config.entrypoint_commands)
        assert commands.index("echo config-cmd") < commands.index("echo cli-cmd1")

    finally:
        import os

        os.unlink(config_file)


@pytest.mark.unit
def test_entrypoint_cmd_in_generated_script():
    """Test that entrypoint extra commands appear in generated script."""
    config = ContainerConfig.from_cli_options(
        context="default", entrypoint_cmd=["npm install", "npm run test"]
    )

    script = build_entrypoint_script(config, verbose=True)

    # Should contain the entrypoint commands in the script
    assert "npm install" in script
    assert "npm run test" in script
    assert 'log "Executing entrypoint command: npm install"' in script
    assert 'log "Executing entrypoint command: npm run test"' in script
