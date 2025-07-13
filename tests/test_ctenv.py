import os
import tempfile
from pathlib import Path
from click.testing import CliRunner
from ctenv import cli, Config, get_current_user_info, build_entrypoint_script


def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1" in result.output


def test_config_user_detection():
    """Test that Config correctly detects user information."""
    config = Config()

    assert config.user_name == os.getenv("USER")
    assert config.user_id == os.getuid()
    assert config.group_id == os.getgid()
    assert "IMAGE" in config.defaults
    assert config.defaults["DIR_MOUNT"] == "/repo"


def test_config_with_mock_user():
    """Test Config with injected user info."""
    mock_user = {
        "user_name": "testuser",
        "user_id": 1000,
        "group_name": "testgroup",
        "group_id": 1000,
        "user_home": "/home/testuser",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(user_info=mock_user, script_dir=Path(tmpdir))

        assert config.user_name == "testuser"
        assert config.user_id == 1000
        assert config.defaults["USER_NAME"] == "testuser"
        assert config.defaults["DIR"] == tmpdir


def test_container_name_generation():
    """Test consistent container name generation."""
    config = Config()

    name1 = config.get_container_name("/path/to/project")
    name2 = config.get_container_name("/path/to/project")
    name3 = config.get_container_name("/different/path")

    assert name1 == name2  # Consistent naming
    assert name1 != name3  # Different paths produce different names
    assert name1.startswith("ctenv-")


def test_entrypoint_script_generation():
    """Test bash entrypoint script generation."""
    config = {
        "USER_NAME": "testuser",
        "USER_ID": 1000,
        "GROUP_NAME": "testgroup",
        "GROUP_ID": 1000,
        "USER_HOME": "/home/testuser",
        "GOSU_MOUNT": "/gosu",
        "COMMAND": "bash",
    }

    script = build_entrypoint_script(config)

    assert "useradd" in script
    assert "testuser" in script
    assert "1000" in script
    assert "exec /gosu testuser bash" in script
    assert 'export PS1="[ctenv] $ "' in script


def test_run_command_help():
    """Test run command help output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])

    assert result.exit_code == 0
    assert "--image" in result.output
    assert "Run command in container" in result.output


def test_run_command_debug_mode():
    """Test run command debug output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--debug"])

    assert result.exit_code == 0
    assert "Configuration:" in result.output
    assert "Docker command:" in result.output
