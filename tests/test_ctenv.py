import os
import tempfile
from pathlib import Path
from click.testing import CliRunner
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv import cli, Config, build_entrypoint_script


@pytest.mark.unit
def test_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1" in result.output


@pytest.mark.unit
def test_config_user_detection():
    """Test that Config correctly detects user information."""
    config = Config()

    assert config.user_name == os.getenv("USER")
    assert config.user_id == os.getuid()
    assert config.group_id == os.getgid()
    assert "IMAGE" in config.defaults
    assert config.defaults["DIR_MOUNT"] == "/repo"


@pytest.mark.unit
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


@pytest.mark.unit
def test_container_name_generation():
    """Test consistent container name generation."""
    config = Config()

    name1 = config.get_container_name("/path/to/project")
    name2 = config.get_container_name("/path/to/project")
    name3 = config.get_container_name("/different/path")

    assert name1 == name2  # Consistent naming
    assert name1 != name3  # Different paths produce different names
    assert name1.startswith("ctenv-")


@pytest.mark.unit
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


@pytest.mark.unit
def test_entrypoint_script_examples():
    """Show example entrypoint scripts for documentation."""
    
    scenarios = [
        {
            "name": "Basic user setup",
            "config": {
                "USER_NAME": "developer",
                "USER_ID": 1001,
                "GROUP_NAME": "staff", 
                "GROUP_ID": 20,
                "USER_HOME": "/home/developer",
                "GOSU_MOUNT": "/gosu",
                "COMMAND": "bash",
            }
        },
        {
            "name": "Custom command execution",
            "config": {
                "USER_NAME": "runner",
                "USER_ID": 1000,
                "GROUP_NAME": "runners",
                "GROUP_ID": 1000, 
                "USER_HOME": "/home/runner",
                "GOSU_MOUNT": "/gosu",
                "COMMAND": "python3 main.py --verbose",
            }
        }
    ]
    
    print(f"\n{'='*50}")
    print("Entrypoint Script Examples")
    print(f"{'='*50}")
    
    for scenario in scenarios:
        script = build_entrypoint_script(scenario["config"])
        
        print(f"\n{scenario['name']}:")
        print(f"  User: {scenario['config']['USER_NAME']} (UID: {scenario['config']['USER_ID']})")
        print(f"  Command: {scenario['config']['COMMAND']}")
        print("  Script:")
        
        # Indent each line for better formatting
        for line in script.split('\n'):
            if line.strip():  # Skip empty lines
                print(f"    {line}")
    
    print(f"\n{'='*50}")


@pytest.mark.unit
def test_run_command_help():
    """Test run command help output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])

    assert result.exit_code == 0
    assert "--image" in result.output
    assert "Run command in container" in result.output


@pytest.mark.unit
def test_run_command_debug_mode():
    """Test run command debug output."""
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--debug"])

    assert result.exit_code == 0
    assert "Configuration:" in result.output
    assert "Docker command:" in result.output
