import pytest
from unittest.mock import patch
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv.ctenv import (
    ContainerRunner,
    RuntimeContext,
    parse_container_config,
)


def create_test_runtime(
    user_name="testuser",
    user_id=1000,
    group_name="testgroup",
    group_id=1000,
    user_home="/home/testuser",
    tty=False,
):
    """Helper to create RuntimeContext for tests."""
    return RuntimeContext(
        user_name=user_name,
        user_id=user_id,
        user_home=user_home,
        group_name=group_name,
        group_id=group_id,
        cwd=Path.cwd(),
        tty=tty,
        project_dir=Path.cwd(),
        pid=os.getpid(),
    )


@pytest.mark.unit
def test_docker_command_examples():
    """Test and display actual Docker commands that would be generated."""

    # Create config dict with test data
    from pathlib import Path

    config_dict = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": ":",  # Auto-detect
        "gosu_path": "/test/gosu",
    }

    # Create runtime context
    runtime = create_test_runtime()

    # Parse config to get ContainerSpec using complete configuration
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
    container_spec = parse_container_config(config, runtime)

    # Create a test script path for build_run_args
    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(container_spec, test_script_path)

    try:
        # Verify command structure
        assert args[0] == "docker"
        assert "run" in args
        assert "--rm" in args
        assert "--init" in args
        # Platform flag should only be present if explicitly specified
        assert "--platform=linux/amd64" not in args
        assert f"--name={container_spec.container_name}" in args
        # With workspace=":", mounts current directory
        current_dir = str(Path.cwd())
        assert f"--volume={current_dir}:" in " ".join(args)  # Path will be in volume mount
        assert "--volume=/test/gosu:/ctenv/gosu:" in " ".join(args)  # Gosu mount
        assert "--workdir=" in " ".join(args)  # Working directory set
        assert "--entrypoint" in args
        assert "/ctenv/entrypoint.sh" in args
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

    # Test with platform specified
    config_dict_with_platform = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
        "platform": "linux/arm64",
    }

    runtime = create_test_runtime()

    # Parse config using complete configuration
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(
        overrides=ContainerConfig.from_dict(config_dict_with_platform)
    )
    container_spec = parse_container_config(config, runtime)
    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(container_spec, test_script_path)

    # Should include platform flag when specified
    assert "--platform=linux/arm64" in args

    # Test without platform
    config_dict_no_platform = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
        # No platform specified
    }

    ctenv_config2 = CtenvConfig.load(Path.cwd())
    config2 = ctenv_config2.get_default(
        overrides=ContainerConfig.from_dict(config_dict_no_platform)
    )
    container_spec_no_platform = parse_container_config(config2, runtime)
    args_no_platform = ContainerRunner.build_run_args(container_spec_no_platform, test_script_path)

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
            # Create a config dict for this scenario
            config_dict = {
                "image": full_config["IMAGE"],
                "command": full_config["COMMAND"],
                "workspace": ":",
                "gosu_path": "/usr/local/bin/gosu",
            }

            runtime = create_test_runtime(
                user_name="developer",
                user_id=1001,
                user_home="/home/developer",
                group_name="developers",
                group_id=1001,
            )

            # Parse config using complete configuration
            from ctenv.ctenv import CtenvConfig, ContainerConfig

            ctenv_config = CtenvConfig.load(Path.cwd())
            config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
            container_spec = parse_container_config(config, runtime)
            # Create a test script path for build_run_args
            test_script_path = "/tmp/test_entrypoint.sh"
            args = ContainerRunner.build_run_args(container_spec, test_script_path)

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
                if arg.startswith("--volume=/tmp") or arg.startswith("--volume=/var/folders"):
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

    # Create config dict with new CLI options
    config_dict = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
        "container_name": "test-container",
        "env": ["TEST_VAR=hello", "USER"],
        "volumes": ["/host/data:/container/data"],
        "sudo": True,
        "network": "bridge",
    }

    runtime = create_test_runtime()

    # Parse config using complete configuration
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
    container_spec = parse_container_config(config, runtime)

    try:
        # Create a test script path for build_run_args
        test_script_path = "/tmp/test_entrypoint.sh"
        args = ContainerRunner.build_run_args(container_spec, test_script_path)

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
        print(f"  Environment: {container_spec.env}")
        print(f"  Volumes: {[vol.to_string() for vol in container_spec.volumes]}")
        print(f"  Sudo: {container_spec.sudo}")
        print(f"  Network: {container_spec.network}")

    finally:
        # No cleanup needed for test script path
        pass


@pytest.mark.unit
def test_sudo_entrypoint_script():
    """Test entrypoint script generation with sudo support."""

    config_dict_with_sudo = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
        "sudo": True,
    }

    config_dict_without_sudo = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
        "sudo": False,
    }

    runtime = create_test_runtime()

    # Parse config using complete configuration
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict_with_sudo))
    container_spec_with_sudo = parse_container_config(config, runtime)
    # Parse config using complete configuration
    ctenv_config2 = CtenvConfig.load(Path.cwd())
    config2 = ctenv_config2.get_default(
        overrides=ContainerConfig.from_dict(config_dict_without_sudo)
    )
    container_spec_without_sudo = parse_container_config(config2, runtime)

    script_with_sudo = container_spec_with_sudo.build_entrypoint_script(verbose=False, quiet=False)
    script_without_sudo = container_spec_without_sudo.build_entrypoint_script(
        verbose=False, quiet=False
    )

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
    config_dict = {
        "image": "ubuntu:latest",
        "command": "echo hello",
        "workspace": ":",
        "gosu_path": "/test/gosu",
        "container_name": "test-container",
    }

    runtime = create_test_runtime()
    # Parse config using complete configuration
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
    container_spec = parse_container_config(config, runtime)

    # Test argument building
    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(container_spec, test_script_path)

    try:
        # Check command structure
        assert args[0] == "docker"
        assert "run" in args
        assert "--rm" in args
        assert "--init" in args
        assert "ubuntu:latest" in args
        assert f"--name={container_spec.container_name}" in args
    finally:
        # No cleanup needed for test script path
        pass


@pytest.mark.unit
@patch("shutil.which")
@patch("subprocess.run")
def test_docker_not_available(mock_run, mock_which):
    """Test behavior when Docker is not available."""
    mock_which.return_value = None  # Docker not found in PATH

    config_dict = {
        "image": "ubuntu:latest",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
    }

    runtime = create_test_runtime()
    # Parse config using complete configuration
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
    container_spec = parse_container_config(config, runtime)

    with pytest.raises(FileNotFoundError, match="Docker not found"):
        ContainerRunner.run_container(container_spec)


@pytest.mark.unit
@patch("subprocess.run")
def test_container_failure_handling(mock_run):
    """Test handling of container execution failures."""
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "Container failed to start"

    # Mock the path checks and config loading
    with (
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.is_file", return_value=True),
        patch("pathlib.Path.is_dir", return_value=True),
        patch("shutil.which", return_value="/usr/bin/docker"),
        patch("ctenv.ctenv.find_user_config", return_value=None),
    ):
        config_dict = {
            "image": "invalid:image",
            "command": "echo test",
            "workspace": ":",
            "gosu_path": "/test/gosu",
            "container_name": "test-container",
        }

        runtime = create_test_runtime()
        # Parse config using complete configuration
        from ctenv.ctenv import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])  # No config files
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        result = ContainerRunner.run_container(container_spec)
        assert result.returncode == 1


@pytest.mark.unit
def test_tty_detection():
    """Test TTY flag handling."""

    # Test with TTY enabled
    config_dict_with_tty = {
        "image": "ubuntu",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
    }

    runtime_with_tty = create_test_runtime(tty=True)
    from ctenv.ctenv import CtenvConfig, ContainerConfig

    ctenv_config = CtenvConfig.load(Path.cwd())
    config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict_with_tty))
    container_spec_with_tty = parse_container_config(config, runtime_with_tty)

    test_script_path = "/tmp/test_entrypoint.sh"
    args = ContainerRunner.build_run_args(container_spec_with_tty, test_script_path)
    assert "-t" in args and "-i" in args

    # Test without TTY
    config_dict_without_tty = {
        "image": "ubuntu",
        "command": "bash",
        "workspace": ":",
        "gosu_path": "/test/gosu",
    }

    runtime_without_tty = create_test_runtime(tty=False)
    ctenv_config2 = CtenvConfig.load(Path.cwd())
    config2 = ctenv_config2.get_default(
        overrides=ContainerConfig.from_dict(config_dict_without_tty)
    )
    container_spec_without_tty = parse_container_config(config2, runtime_without_tty)

    args = ContainerRunner.build_run_args(container_spec_without_tty, test_script_path)
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
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
            "gosu_path": str(gosu_path),
            "volumes": [
                "cache-vol:/var/cache:rw,chown",
                "data-vol:/data:chown",
                "logs:/logs:ro",
            ],
        }

        runtime = create_test_runtime()
        # Parse config using complete configuration
        from ctenv.ctenv import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd())
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        # Test that build_run_args processes chown correctly
        test_script_path = "/tmp/test_entrypoint.sh"
        docker_args = ContainerRunner.build_run_args(container_spec, test_script_path)

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
            script_content = container_spec.build_entrypoint_script(verbose=False, quiet=False)

            # Should contain chown paths in the CHOWN_PATHS variable for cache and data, but not logs
            assert "/var/cache" in script_content
            assert "/data" in script_content
            assert "/logs" not in script_content
            # Should contain the chown function
            assert "fix_chown_volumes()" in script_content
            assert 'chown -R "$USER_ID:$GROUP_ID" "$path"' in script_content

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
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
            "gosu_path": str(gosu_path),
            "post_start_commands": [
                "source /bitbake-venv/bin/activate",
                "mkdir -p /var/cache/custom",
                "echo 'Setup complete'",
            ],
        }

        runtime = create_test_runtime()
        # Parse config using complete configuration
        from ctenv.ctenv import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd())
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        # Generate entrypoint script content directly
        script_content = container_spec.build_entrypoint_script(verbose=False, quiet=False)

        # Should contain post-start commands in the POST_START_COMMANDS variable
        assert "POST_START_COMMANDS=" in script_content
        assert "source /bitbake-venv/bin/activate" in script_content
        assert "mkdir -p /var/cache/custom" in script_content
        assert "Setup complete" in script_content  # Check for the content, not the exact quoting
        # Should contain the function to execute post-start commands
        assert "run_post_start_commands()" in script_content

        # Commands should be executed before the gosu command
        lines = script_content.split("\n")
        post_start_call = None
        gosu_line = None

        for i, line in enumerate(lines):
            if "run_post_start_commands()" in line:
                post_start_call = i
            elif 'exec "$GOSU_MOUNT"' in line:
                gosu_line = i
                break

        # Post-start commands function call should come before gosu
        assert post_start_call is not None
        assert gosu_line is not None
        assert post_start_call < gosu_line


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
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
            "gosu_path": str(gosu_path),
            "ulimits": {"nofile": 1024, "nproc": 2048, "core": "0"},
        }

        runtime = create_test_runtime()
        # Parse config using complete configuration
        from ctenv.ctenv import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd())
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        # Test that build_run_args generates ulimit flags
        test_script_path = "/tmp/test_entrypoint.sh"
        docker_args = ContainerRunner.build_run_args(container_spec, test_script_path)

        # Check that ulimit flags are present
        ulimit_args = [arg for arg in docker_args if arg.startswith("--ulimit=")]

        # Should have 3 ulimit flags
        assert len(ulimit_args) == 3
        assert "--ulimit=nofile=1024" in ulimit_args
        assert "--ulimit=nproc=2048" in ulimit_args
        assert "--ulimit=core=0" in ulimit_args


@pytest.mark.unit
def test_container_labels_added():
    """Test that ctenv adds identifying labels to containers."""
    from ctenv.ctenv import ContainerRunner, __version__, parse_container_config
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake gosu
        gosu_path = Path(tmpdir) / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Test config with minimal settings
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
            "gosu_path": str(gosu_path),
        }

        runtime = create_test_runtime()
        # Parse config using complete configuration
        from ctenv.ctenv import CtenvConfig, ContainerConfig

        ctenv_config = CtenvConfig.load(Path.cwd())
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        # Build Docker run arguments
        args = ContainerRunner.build_run_args(container_spec, "/tmp/entrypoint.sh")

        # Check that ctenv labels are present
        labels_found = []
        for arg in args:
            if arg.startswith("--label=se.osd.ctenv."):
                labels_found.append(arg)

        # Verify expected labels
        expected_labels = [
            "--label=se.osd.ctenv.managed=true",
            f"--label=se.osd.ctenv.version={__version__}",
        ]

        assert len(labels_found) == 2, (
            f"Expected 2 labels, found {len(labels_found)}: {labels_found}"
        )
        for expected_label in expected_labels:
            assert expected_label in labels_found, f"Missing label: {expected_label}"
