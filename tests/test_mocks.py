import pytest
from unittest.mock import patch
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv.cli import ContainerRunner, ContainerConfig, build_entrypoint_script


@pytest.mark.unit
def test_docker_command_examples():
    """Test and display actual Docker commands that would be generated."""

    # Create config with test data
    config = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/workspace"),
        image="ubuntu:latest",
        command="bash",
        gosu_path=Path("/test/gosu"),
    )

    # Create a test script path for build_run_args
    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(config, test_script_path)

    try:
        # Verify command structure
        assert args[0] == "docker"
        assert "run" in args
        assert "--rm" in args
        assert "--init" in args
        # Platform flag should only be present if explicitly specified
        assert "--platform=linux/amd64" not in args
        assert f"--name={config.get_container_name()}" in args
        assert "--volume=/workspace:/repo:z,rw" in args
        assert "--volume=/test/gosu:/gosu:z,ro" in args
        assert "--workdir=/repo" in args
        assert "--entrypoint" in args
        assert "/entrypoint.sh" in args
        assert "ubuntu:latest" in args

        # Print the command for documentation purposes
        print("\nExample Docker command for 'bash':")
        print(f"  {' '.join(args[: args.index('ubuntu:latest') + 1])}")

    finally:
        # No cleanup needed for test script path
        pass


@pytest.mark.unit
def test_platform_support():
    """Test platform support in Docker commands."""
    config_with_platform = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup", 
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/workspace"),
        image="ubuntu:latest",
        command="bash",
        gosu_path=Path("/test/gosu"),
        platform="linux/arm64",
    )
    
    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(config_with_platform, test_script_path)
    
    # Should include platform flag when specified
    assert "--platform=linux/arm64" in args
    
    # Test without platform
    config_no_platform = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000, 
        user_home="/home/testuser",
        working_dir=Path("/workspace"),
        image="ubuntu:latest",
        command="bash",
        gosu_path=Path("/test/gosu"),
    )
    
    args_no_platform = ContainerRunner.build_run_args(config_no_platform, test_script_path)
    
    # Should not include platform flag when not specified
    platform_args = [arg for arg in args_no_platform if arg.startswith("--platform")]
    assert len(platform_args) == 0


@pytest.mark.unit
def test_docker_command_scenarios():
    """Show Docker commands for different common scenarios."""

    # Base configuration template (unused but shows common config structure)

    scenarios = [
        {
            "name": "Interactive bash",
            "config": {
                "IMAGE": "ubuntu:20.04",
                "COMMAND": "bash",
                "DIR": "/project",
            },
        },
        {
            "name": "Python script execution",
            "config": {
                "IMAGE": "python:3.9",
                "COMMAND": "python script.py",
                "DIR": "/app",
            },
        },
        {
            "name": "Alpine with ls command",
            "config": {
                "IMAGE": "alpine:latest",
                "COMMAND": "ls -la",
                "DIR": "/data",
            },
        },
    ]

    print(f"\n{'=' * 60}")
    print("Docker Command Examples")
    print(f"{'=' * 60}")

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
            **scenario["config"],
        }

        try:
            # Create a Config object for this scenario
            scenario_config = ContainerConfig(
                user_name="developer",
                user_id=1001,
                group_name="developers",
                group_id=1001,
                user_home="/home/developer",
                working_dir=Path(full_config["DIR"]),
                gosu_path=Path("/usr/local/bin/gosu"),
                image=full_config["IMAGE"],
                command=full_config["COMMAND"],
            )
            # Create a test script path for build_run_args
            test_script_path = "/tmp/test_entrypoint.sh"
            args = ContainerRunner.build_run_args(scenario_config, test_script_path)

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
                if arg == "--volume" and "/tmp" in args[i + 1]:
                    # Skip the temp script volume mount for readability
                    skip_next = True
                    continue
                if arg.startswith("--volume=/tmp") or arg.startswith(
                    "--volume=/var/folders"
                ):
                    # Skip temp script volume mount
                    continue
                docker_cmd.append(arg)

            print(f"  Docker: {' '.join(docker_cmd)}")

        finally:
            # No cleanup needed for test script path
            pass

    print(f"\n{'=' * 60}")


@pytest.mark.unit
def test_new_cli_options():
    """Test Docker commands generated with new CLI options."""

    # Create config with new CLI options
    config = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/workspace"),
        gosu_path=Path("/test/gosu"),
        image="ubuntu:latest",
        command="bash",
        container_name="test-container",
        env=("TEST_VAR=hello", "USER"),
        volumes=("/host/data:/container/data",),
        sudo=True,
        network="bridge",
    )

    try:
        # Create a test script path for build_run_args
        test_script_path = "/tmp/test_entrypoint.sh"
        args = ContainerRunner.build_run_args(config, test_script_path)

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
        print(f"  Environment: {config.env}")
        print(f"  Volumes: {config.volumes}")
        print(f"  Sudo: {config.sudo}")
        print(f"  Network: {config.network}")

    finally:
        # No cleanup needed for test script path
        pass


@pytest.mark.unit
def test_sudo_entrypoint_script():
    """Test entrypoint script generation with sudo support."""
    config_with_sudo = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
        command="bash",
        sudo=True,
    )

    config_without_sudo = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
        command="bash",
        sudo=False,
    )

    script_with_sudo = build_entrypoint_script(config_with_sudo, verbose=False, quiet=False)
    script_without_sudo = build_entrypoint_script(config_without_sudo, verbose=False, quiet=False)

    # Test sudo setup is properly configured with ADD_SUDO variable
    assert "ADD_SUDO=1" in script_with_sudo
    assert "apt-get install" in script_with_sudo
    assert "NOPASSWD:ALL" in script_with_sudo
    assert 'if [ "$ADD_SUDO" = "1" ]; then' in script_with_sudo

    # Test sudo is disabled but code is still present (guarded by ADD_SUDO=0)
    assert "ADD_SUDO=0" in script_without_sudo
    assert "apt-get install" in script_without_sudo  # Code is present but guarded
    assert "Sudo not requested" in script_without_sudo
    assert 'if [ "$ADD_SUDO" = "1" ]; then' in script_without_sudo

    print("\nSudo script sets ADD_SUDO=1 and includes conditional sudo setup")
    print("Non-sudo script sets ADD_SUDO=0 with same conditional logic")


@pytest.mark.unit
@patch("subprocess.run")
def test_docker_command_construction(mock_run):
    """Test that Docker commands are constructed correctly."""

    mock_run.return_value.returncode = 0

    # Create config with test data
    config = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
        image="ubuntu:latest",
        command="echo hello",
        container_name="test-container",
    )

    # Test argument building
    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(config, test_script_path)

    try:
        # Check command structure
        assert args[0] == "docker"
        assert "run" in args
        assert "--rm" in args
        assert "--init" in args
        assert "ubuntu:latest" in args
        assert f"--name={config.container_name}" in args
    finally:
        # No cleanup needed for test script path
        pass


@pytest.mark.unit
@patch("shutil.which")
@patch("subprocess.run")
def test_docker_not_available(mock_run, mock_which):
    """Test behavior when Docker is not available."""
    mock_which.return_value = None  # Docker not found in PATH

    config = ContainerConfig(
        user_name="testuser",
        user_id=1000,
        group_name="testgroup",
        group_id=1000,
        user_home="/home/testuser",
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
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
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=Path("/test"),
            gosu_path=Path("/test/gosu"),
            image="invalid:image",
            command="echo test",
            container_name="test-container",
        )

        result = ContainerRunner.run_container(config)
        assert result.returncode == 1


@pytest.mark.unit
def test_tty_detection():
    """Test TTY flag handling."""

    # Test with TTY enabled
    config_with_tty = ContainerConfig(
        user_name="test",
        user_id=1000,
        group_name="test",
        group_id=1000,
        user_home="/home/test",
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
        image="ubuntu",
        command="bash",
        tty=True,
    )

    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(config_with_tty, test_script_path)
    assert "-t" in args and "-i" in args

    # Test without TTY
    config_without_tty = ContainerConfig(
        user_name="test",
        user_id=1000,
        group_name="test",
        group_id=1000,
        user_home="/home/test",
        working_dir=Path("/test"),
        gosu_path=Path("/test/gosu"),
        image="ubuntu",
        command="bash",
        tty=False,
    )

    args = ContainerRunner.build_run_args(config_without_tty, test_script_path)
    assert "-t" not in args and "-i" not in args


@pytest.mark.unit
def test_volume_chown_option():
    """Test volume chown option parsing and entrypoint generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Test volume with chown option
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=tmpdir,
            gosu_path=gosu_path,
            image="test:latest",
            command="bash",
            volumes=(
                "cache-vol:/var/cache:rw,chown",
                "data-vol:/data:chown",
                "logs:/logs:ro",
            ),
        )

        # Test that build_run_args processes chown correctly
        test_script_path = "/tmp/test_entrypoint.sh"
        docker_args = ContainerRunner.build_run_args(config, test_script_path)

        try:
            # Check that chown was removed from volume args
            volume_args = [arg for arg in docker_args if arg.startswith("--volume=")]

            # Find the processed volumes
            cache_volume = None
            data_volume = None
            logs_volume = None
            for arg in volume_args:
                if "cache-vol:/var/cache" in arg:
                    cache_volume = arg
                elif "data-vol:/data" in arg:
                    data_volume = arg
                elif "logs:/logs" in arg:
                    logs_volume = arg

            # Chown should be removed but other options preserved, z properly merged
            assert cache_volume == "--volume=cache-vol:/var/cache:rw,z"
            assert data_volume == "--volume=data-vol:/data:z"
            assert logs_volume == "--volume=logs:/logs:ro,z"

            # Generate entrypoint script content to check for chown commands
            _, chown_paths = ContainerRunner.parse_volumes(config.volumes)
            script_content = build_entrypoint_script(config, chown_paths, verbose=False, quiet=False)

            # Should contain chown commands for cache and data, but not logs
            assert 'chown -R "$USER_ID:$GROUP_ID" /var/cache' in script_content
            assert 'chown -R "$USER_ID:$GROUP_ID" /data' in script_content
            assert 'chown -R "$USER_ID:$GROUP_ID" /logs' not in script_content

        finally:
            # No cleanup needed for test script path
            pass


@pytest.mark.unit
def test_post_start_commands():
    """Test post-start commands execution in container script."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Test config with post-start commands
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=tmpdir,
            gosu_path=gosu_path,
            image="test:latest",
            command="bash",
            post_start_commands=(
                "source /bitbake-venv/bin/activate",
                "mkdir -p /var/cache/custom",
                "echo 'Setup complete'",
            ),
        )

        # Generate entrypoint script content directly
        script_content = build_entrypoint_script(config, verbose=False, quiet=False)

        # Should contain post-start commands section
        assert "# Execute post-start commands" in script_content
        assert "source /bitbake-venv/bin/activate" in script_content
        assert "mkdir -p /var/cache/custom" in script_content
        assert "echo 'Setup complete'" in script_content

        # Commands should be executed before the gosu command
        lines = script_content.split("\n")
        post_start_start = None
        gosu_line = None

        for i, line in enumerate(lines):
            if "# Execute post-start commands" in line:
                post_start_start = i
            elif "exec /gosu" in line:
                gosu_line = i
                break

        # Post-start commands should come before gosu
        assert post_start_start is not None
        assert gosu_line is not None
        assert post_start_start < gosu_line


@pytest.mark.unit
def test_ulimits_configuration():
    """Test ulimits configuration and Docker flag generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Test config with ulimits
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=tmpdir,
            gosu_path=gosu_path,
            image="test:latest",
            command="bash",
            ulimits={"nofile": 1024, "nproc": 2048, "core": "0"},
        )

        # Test that build_run_args generates ulimit flags
        test_script_path = "/tmp/test_entrypoint.sh"
        docker_args = ContainerRunner.build_run_args(config, test_script_path)

        # Check that ulimit flags are present
        ulimit_args = [arg for arg in docker_args if arg.startswith("--ulimit=")]

        # Should have 3 ulimit flags
        assert len(ulimit_args) == 3
        assert "--ulimit=nofile=1024" in ulimit_args
        assert "--ulimit=nproc=2048" in ulimit_args
        assert "--ulimit=core=0" in ulimit_args


@pytest.mark.skip(reason="Test environment interference - TODO: fix isolation")
@pytest.mark.unit
def test_platform_specific_gosu_discovery():
    """Test that platform-specific gosu binaries are found correctly."""
    from ctenv.cli import get_platform_specific_gosu_name, find_gosu_binary
    from unittest.mock import patch

    # Test platform name generation
    platform_name = get_platform_specific_gosu_name()
    assert platform_name.startswith("gosu-")

    # Should be one of the expected platform names
    # Note: gosu only provides Linux binaries since containers run Linux
    expected_names = [
        "gosu-amd64",
        "gosu-arm64",
    ]
    assert platform_name in expected_names

    # Test that find_gosu_binary prefers platform-specific binaries
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        ctenv_dir = tmpdir / ".ctenv"
        ctenv_dir.mkdir()

        # Create both generic and platform-specific gosu
        generic_gosu = ctenv_dir / "gosu"
        platform_gosu = ctenv_dir / platform_name

        generic_gosu.write_text('#!/bin/sh\necho "generic"')
        generic_gosu.chmod(0o755)

        platform_gosu.write_text('#!/bin/sh\necho "platform-specific"')
        platform_gosu.chmod(0o755)

        # Mock home directory to point to our test dir and disable system PATH
        with (
            patch("pathlib.Path.home", return_value=tmpdir),
            patch("shutil.which", return_value=None),
        ):
            # Should prefer platform-specific
            found_gosu = find_gosu_binary(start_dir=tmpdir)
            assert found_gosu.resolve() == platform_gosu.resolve()
