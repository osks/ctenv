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
    config = Config.from_cli_options()

    assert config.user_name == os.getenv("USER")
    assert config.user_id == os.getuid()
    assert config.group_id == os.getgid()
    assert config.image == "ubuntu:latest"
    assert config.dir_mount == "/repo"


@pytest.mark.unit
def test_config_with_mock_user():
    """Test Config with custom values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Config(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            script_dir=Path(tmpdir),
            working_dir=Path(tmpdir),
        )

        assert config.user_name == "testuser"
        assert config.user_id == 1000
        assert config.script_dir == Path(tmpdir)
        assert config.working_dir == Path(tmpdir)


@pytest.mark.unit
def test_container_name_generation():
    """Test consistent container name generation."""
    config1 = Config.from_cli_options(dir="/path/to/project")
    config2 = Config.from_cli_options(dir="/path/to/project")
    config3 = Config.from_cli_options(dir="/different/path")

    name1 = config1.get_container_name()
    name2 = config2.get_container_name()
    name3 = config3.get_container_name()

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
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["run", "--debug"])

    assert result.exit_code == 0
    # Debug output should go to stderr
    assert "Configuration:" in result.stderr
    assert "Docker command:" in result.stderr


@pytest.mark.unit
def test_verbose_mode():
    """Test verbose logging output."""
    runner = CliRunner(mix_stderr=False)
    
    # Test that verbose flag is accepted and doesn't break anything
    result = runner.invoke(cli, ["--verbose", "--version"])
    assert result.exit_code == 0
    assert "0.1" in result.output
    
    # Test verbose with run --debug
    result = runner.invoke(cli, ["--verbose", "run", "--debug"])
    assert result.exit_code == 0
    assert "Configuration:" in result.stderr  # Debug output goes to stderr
    # Note: verbose DEBUG logging may not show up in CliRunner tests
    # The main thing is that verbose mode doesn't break anything


@pytest.mark.unit
def test_quiet_mode():
    """Test quiet mode suppresses output."""
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(cli, ["--quiet", "run", "--debug"])
    
    assert result.exit_code == 0
    # In quiet mode with debug, we should only see the debug output, not [ctenv] run
    assert "[ctenv] run" not in result.stderr
    assert "Configuration:" in result.stderr  # Debug output still shows


@pytest.mark.unit
def test_stdout_stderr_separation():
    """Test that ctenv output goes to stderr, leaving stdout clean."""
    runner = CliRunner(mix_stderr=False)
    
    # Test with debug mode
    result = runner.invoke(cli, ["run", "--debug"])
    assert result.exit_code == 0
    
    # stdout should be empty (no ctenv output)
    assert result.output == ""
    
    # stderr should contain all ctenv output
    assert "[ctenv] run" in result.stderr
    assert "Configuration:" in result.stderr
    assert "Docker command:" in result.stderr
    
    # Test with quiet mode too
    result = runner.invoke(cli, ["--quiet", "run", "--debug"])
    assert result.exit_code == 0
    
    # stdout should still be empty
    assert result.output == ""
    
    # stderr should contain debug output but not [ctenv] run
    assert "[ctenv] run" not in result.stderr
    assert "Configuration:" in result.stderr
