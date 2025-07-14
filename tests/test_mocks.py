import pytest
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv import ContainerRunner, Config, build_entrypoint_script


@pytest.mark.unit  
def test_docker_command_examples():
    """Test and display actual Docker commands that would be generated."""
    import os
    
    # Create config with test data
    config = Config(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        script_dir=Path("/test"),
        working_dir=Path("/workspace"),
        image="ubuntu:latest",
        command="bash"
    )
    
    args, script_path = ContainerRunner.build_run_args(config)
    
    try:
        # Verify command structure
        assert args[0] == "docker"
        assert "run" in args
        assert "--rm" in args
        assert "--init" in args
        assert "--platform=linux/amd64" in args
        assert f"--name={config.get_container_name()}" in args
        assert "--volume=/workspace:/repo:z,rw" in args
        assert "--volume=/test/gosu:/gosu:z,ro" in args
        assert "--workdir=/repo" in args
        assert "--entrypoint" in args
        assert "/entrypoint.sh" in args
        assert "ubuntu:latest" in args
        
        # Print the command for documentation purposes
        print("\nExample Docker command for 'bash':")
        print(f"  {' '.join(args[:args.index('ubuntu:latest')+1])}")
        
    finally:
        # Clean up the script path
        try:
            os.unlink(script_path)
        except OSError:
            pass


@pytest.mark.unit
def test_docker_command_scenarios():
    """Show Docker commands for different common scenarios."""
    import os
    
    base_config = Config(
        user_name="developer",
        user_id=1001,
        group_name="developers",
        group_id=1001,
        user_home="/home/developer",
        script_dir=Path("/usr/local/bin"),
        working_dir=Path("/workspace")
    )
    
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
            # Create a Config object for this scenario
            scenario_config = Config(
                user_name="developer",
                user_id=1001,
                group_name="developers",
                group_id=1001,
                user_home="/home/developer",
                script_dir=Path("/usr/local/bin"),
                working_dir=Path(full_config["DIR"]),
                image=full_config["IMAGE"],
                command=full_config["COMMAND"]
            )
            args, script_path = ContainerRunner.build_run_args(scenario_config)
            
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
            if 'script_path' in locals():
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
    
    print(f"\n{'='*60}")


@pytest.mark.unit
def test_new_cli_options():
    """Test Docker commands generated with new CLI options."""
    import os
    
    # Create config with new CLI options
    config = Config(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        script_dir=Path("/test"),
        working_dir=Path("/workspace"),
        image="ubuntu:latest",
        command="bash",
        container_name="test-container",
        env_vars=("TEST_VAR=hello", "USER"),
        volumes=("/host/data:/container/data",),
        sudo=True,
        network="bridge"
    )
    
    try:
        args, script_path = ContainerRunner.build_run_args(config)
        
        # Test environment variables
        assert "--env=TEST_VAR=hello" in args
        assert "--env=USER" in args
        
        # Test additional volumes
        assert "--volume=/host/data:/container/data:z" in args
        
        # Test networking
        assert "--network=bridge" in args
        
        # Test basic structure is still there
        assert "docker" == args[0]
        assert "run" in args
        assert "--rm" in args
        assert "ubuntu:latest" in args
        
        print("\nExample with new CLI options:")
        print(f"  Environment: {config.env_vars}")
        print(f"  Volumes: {config.volumes}")
        print(f"  Sudo: {config.sudo}")
        print(f"  Network: {config.network}")
        
    finally:
        # Cleanup temp script file
        if 'script_path' in locals():
            try:
                os.unlink(script_path)
            except OSError:
                pass


@pytest.mark.unit
def test_sudo_entrypoint_script():
    """Test entrypoint script generation with sudo support."""
    config_with_sudo = Config(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        script_dir=Path("/test"),
        working_dir=Path("/test"),
        command="bash",
        sudo=True
    )
    
    config_without_sudo = Config(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        script_dir=Path("/test"),
        working_dir=Path("/test"),
        command="bash",
        sudo=False
    )
    
    script_with_sudo = build_entrypoint_script(config_with_sudo)
    script_without_sudo = build_entrypoint_script(config_without_sudo)
    
    # Test sudo installation is included when requested
    assert "apt-get install" in script_with_sudo
    assert "NOPASSWD:ALL" in script_with_sudo
    
    # Test sudo installation is not included when not requested
    assert "apt-get install" not in script_without_sudo
    assert "Sudo not requested" in script_without_sudo
    
    print("\nSudo script includes package installation and sudoers configuration")
    print("Non-sudo script excludes sudo setup")


@pytest.mark.unit
@patch("subprocess.run")
def test_docker_command_construction(mock_run):
    """Test that Docker commands are constructed correctly."""
    import os
    mock_run.return_value.returncode = 0

    # Create config with test data
    config = Config(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        script_dir=Path("/test"),
        working_dir=Path("/test"),
        image="ubuntu:latest",
        command="echo hello",
        container_name="test-container"
    )

    # Test argument building
    args, script_path = ContainerRunner.build_run_args(config)
    
    try:
        # Check command structure
        assert args[0] == "docker"
        assert "run" in args
        assert "--rm" in args
        assert "--init" in args
        assert "ubuntu:latest" in args
        assert f"--name={config.container_name}" in args
    finally:
        # Cleanup temp script file
        try:
            os.unlink(script_path)
        except OSError:
            pass


@pytest.mark.unit
@patch("shutil.which")
@patch("subprocess.run")
def test_docker_not_available(mock_run, mock_which):
    """Test behavior when Docker is not available."""
    mock_which.return_value = None  # Docker not found in PATH

    config = Config(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        script_dir=Path("/test"),
        working_dir=Path("/test")
    )

    with pytest.raises(FileNotFoundError, match="Docker not found"):
        ContainerRunner.run_container(config)


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
        config = Config(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            script_dir=Path("/test"),
            working_dir=Path("/test"),
            image="invalid:image",
            command="echo test",
            container_name="test-container"
        )

        result = ContainerRunner.run_container(config)
        assert result.returncode == 1


@pytest.mark.unit
def test_tty_detection():
    """Test TTY flag handling."""
    import os
    
    # Test with TTY enabled
    config_with_tty = Config(
        user_name="test",
        user_id=1000,
        group_name="test",
        group_id=1000,
        user_home="/home/test",
        script_dir=Path("/test"),
        working_dir=Path("/test"),
        image="ubuntu",
        command="bash",
        tty=True,
    )

    args, script_path = ContainerRunner.build_run_args(config_with_tty)
    assert "-t" in args and "-i" in args
    
    # Cleanup
    try:
        os.unlink(script_path)
    except OSError:
        pass

    # Test without TTY
    config_without_tty = Config(
        user_name="test",
        user_id=1000,
        group_name="test",
        group_id=1000,
        user_home="/home/test",
        script_dir=Path("/test"),
        working_dir=Path("/test"),
        image="ubuntu",
        command="bash",
        tty=False,
    )

    args, script_path = ContainerRunner.build_run_args(config_without_tty)
    assert "-t" not in args and "-i" not in args
    
    # Cleanup
    try:
        os.unlink(script_path)
    except OSError:
        pass
