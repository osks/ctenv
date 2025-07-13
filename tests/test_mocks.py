import pytest
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv import ContainerRunner, Config


@pytest.mark.unit  
def test_docker_command_examples():
    """Test and display actual Docker commands that would be generated."""
    
    # Create config with test data
    mock_user_info = {
        "user_name": "testuser",
        "user_id": 1000,
        "group_name": "testgroup", 
        "group_id": 1000,
        "user_home": "/home/testuser"
    }
    config = Config(user_info=mock_user_info, script_dir=Path("/test"))
    runner = ContainerRunner(config)
    
    # Test scenario 1: Basic bash command
    test_config = {
        "IMAGE": "ubuntu:latest",
        "COMMAND": "bash",
        "NAME": "test-container",
        "DIR": "/workspace",
        "DIR_MOUNT": "/repo",
        "GOSU": "/test/gosu",
        "GOSU_MOUNT": "/gosu",
        "USER_NAME": "testuser",
        "USER_ID": 1000,
        "GROUP_NAME": "testgroup",
        "GROUP_ID": 1000,
        "USER_HOME": "/home/testuser"
    }
    
    args = runner.build_run_args(test_config)
    
    # Clean up the script path before asserting
    script_path = test_config.get('_SCRIPT_PATH')
    if script_path:
        try:
            import os
            os.unlink(script_path)
        except OSError:
            pass
    
    # Verify command structure
    assert args[0] == "docker"
    assert "run" in args
    assert "--rm" in args
    assert "--init" in args
    assert "--platform=linux/amd64" in args
    assert "--name=test-container" in args
    assert "--volume=/workspace:/repo:z,rw" in args
    assert "--volume=/test/gosu:/gosu:z,ro" in args
    assert "--workdir=/repo" in args
    assert "--entrypoint" in args
    assert "/entrypoint.sh" in args
    assert "ubuntu:latest" in args
    
    # Print the command for documentation purposes
    print("\nExample Docker command for 'bash':")
    print(f"  {' '.join(args[:args.index('ubuntu:latest')+1])}")


@pytest.mark.unit
def test_docker_command_scenarios():
    """Show Docker commands for different common scenarios."""
    import os
    
    mock_user_info = {
        "user_name": "developer",
        "user_id": 1001,
        "group_name": "developers",
        "group_id": 1001,
        "user_home": "/home/developer"
    }
    config = Config(user_info=mock_user_info, script_dir=Path("/usr/local/bin"))
    runner = ContainerRunner(config)
    
    scenarios = [
        {
            "name": "Interactive bash",
            "config": {
                "IMAGE": "ubuntu:20.04",
                "COMMAND": "bash",
                "DIR": "/project",
            }
        },
        {
            "name": "Python script execution", 
            "config": {
                "IMAGE": "python:3.9",
                "COMMAND": "python script.py",
                "DIR": "/app",
            }
        },
        {
            "name": "Alpine with ls command",
            "config": {
                "IMAGE": "alpine:latest", 
                "COMMAND": "ls -la",
                "DIR": "/data",
            }
        }
    ]
    
    print(f"\n{'='*60}")
    print("Docker Command Examples")
    print(f"{'='*60}")
    
    for scenario in scenarios:
        # Build full config
        full_config = {
            "NAME": f"ctenv-test-{hash(scenario['name']) % 10000}",
            "DIR_MOUNT": "/repo",
            "GOSU": "/usr/local/bin/gosu",
            "GOSU_MOUNT": "/gosu",
            "USER_NAME": "developer",
            "USER_ID": 1001,
            "GROUP_NAME": "developers", 
            "GROUP_ID": 1001,
            "USER_HOME": "/home/developer",
            **scenario["config"]
        }
        
        try:
            args = runner.build_run_args(full_config)
            
            # Format command nicely
            print(f"\n{scenario['name']}:")
            print(f"  Image: {full_config['IMAGE']}")
            print(f"  Command: {full_config['COMMAND']}")
            print(f"  Working Dir: {full_config['DIR']} -> /repo")
            
            # Show the docker command (excluding the temp script path)
            docker_cmd = []
            skip_next = False
            for i, arg in enumerate(args):
                if skip_next:
                    skip_next = False
                    continue
                if arg == "--volume" and "/tmp" in args[i+1]:
                    # Skip the temp script volume mount for readability
                    skip_next = True
                    continue
                if arg.startswith("--volume=/tmp") or arg.startswith("--volume=/var/folders"):
                    # Skip temp script volume mount
                    continue
                docker_cmd.append(arg)
            
            print(f"  Docker: {' '.join(docker_cmd)}")
            
        finally:
            # Cleanup temp script file
            script_path = full_config.get('_SCRIPT_PATH')
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
    
    print(f"\n{'='*60}")


@pytest.mark.unit
@patch("subprocess.run")
def test_docker_command_construction(mock_run):
    """Test that Docker commands are constructed correctly."""
    mock_run.return_value.returncode = 0

    # Create config with test data
    mock_user_info = {
        "user_name": "testuser",
        "user_id": 1000,
        "group_name": "testgroup",
        "group_id": 1000,
        "user_home": "/home/testuser",
    }
    config = Config(user_info=mock_user_info, script_dir=Path("/test"))
    runner = ContainerRunner(config)

    test_config = {
        "IMAGE": "ubuntu:latest",
        "COMMAND": "echo hello",
        "NAME": "test-container",
        "DIR": "/test",
        "DIR_MOUNT": "/repo",
        "GOSU": "/test/gosu",
        "GOSU_MOUNT": "/gosu",
        "USER_NAME": "testuser",
        "USER_ID": 1000,
        "GROUP_NAME": "testgroup",
        "GROUP_ID": 1000,
        "USER_HOME": "/home/testuser",
    }

    # Test argument building
    args = runner.build_run_args(test_config)

    # Check command structure
    assert args[0] == "docker"
    assert "run" in args
    assert "--rm" in args
    assert "--init" in args
    assert "ubuntu:latest" in args
    assert f"--name={test_config['NAME']}" in args


@pytest.mark.unit
@patch("shutil.which")
@patch("subprocess.run")
def test_docker_not_available(mock_run, mock_which):
    """Test behavior when Docker is not available."""
    mock_which.return_value = None  # Docker not found in PATH

    config = Config()
    runner = ContainerRunner(config)

    with pytest.raises(FileNotFoundError, match="Docker not found"):
        runner.run_container({"GOSU": "/test/gosu", "DIR": "/test"})


@pytest.mark.unit
@patch("subprocess.run")
def test_container_failure_handling(mock_run):
    """Test handling of container execution failures."""
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "Container failed to start"

    # Mock the path checks
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.is_dir", return_value=True),
        patch("shutil.which", return_value="/usr/bin/docker"),
    ):
        config = Config()
        runner = ContainerRunner(config)

        result = runner.run_container(
            {
                "GOSU": "/test/gosu",
                "DIR": "/test",
                "DIR_MOUNT": "/repo",
                "GOSU_MOUNT": "/gosu",
                "IMAGE": "invalid:image",
                "COMMAND": "echo test",
                "NAME": "test-container",
                "USER_NAME": "testuser",
                "USER_ID": 1000,
                "GROUP_NAME": "testgroup",
                "GROUP_ID": 1000,
                "USER_HOME": "/home/testuser",
            }
        )
        assert result.returncode == 1


@pytest.mark.unit
@patch("sys.stdin.isatty")
def test_tty_detection(mock_isatty):
    """Test TTY flag handling."""
    mock_isatty.return_value = True

    config = Config()
    runner = ContainerRunner(config)

    test_config = {
        "IMAGE": "ubuntu",
        "COMMAND": "bash",
        "NAME": "test",
        "DIR": "/test",
        "DIR_MOUNT": "/repo",
        "GOSU": "/gosu",
        "GOSU_MOUNT": "/gosu",
        "USER_NAME": "test",
        "USER_ID": 1000,
        "GROUP_NAME": "test",
        "GROUP_ID": 1000,
        "USER_HOME": "/home/test",
    }

    args = runner.build_run_args(test_config)
    assert "-t" in args and "-i" in args

    # Test when not a TTY
    mock_isatty.return_value = False
    args = runner.build_run_args(test_config)
    assert "-t" not in args and "-i" not in args
