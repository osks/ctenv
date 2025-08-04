import os
import subprocess
import pytest
from pathlib import Path


@pytest.mark.integration
def test_basic_container_execution(test_images, temp_workspace):
    """Test basic container execution with ubuntu."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--",
            "whoami",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0
    # Note: The user will be different in container, but command should succeed


@pytest.mark.integration
def test_working_directory_is_mounted_path(test_images, temp_workspace):
    """Test that working directory inside container matches workspace mount."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--",
            "pwd",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0
    # With workspace "auto", the working directory matches the host directory path
    # (resolve symlinks for macOS compatibility where /var -> /private/var)
    expected_path = str(Path(temp_workspace).resolve())
    assert result.stdout.strip() == expected_path


@pytest.mark.integration
def test_file_permission_preservation(test_images, temp_workspace):
    """Test that files created in container have correct ownership on host."""
    test_file = "test_permissions.txt"

    # Create file in container
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--",
            "touch",
            test_file,
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0

    # Check file exists and has correct ownership
    file_path = Path(temp_workspace) / test_file
    assert file_path.exists()

    stat_info = file_path.stat()

    # In CI environments, files may be created as root (UID 0) due to container behavior
    # In local environments with real gosu, files should have correct user ownership
    expected_uid = os.getuid()

    # Allow for CI environment where container runs as root
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        # In CI, the file might be created as root (0) or the expected user
        assert stat_info.st_uid in (0, expected_uid), (
            f"File UID {stat_info.st_uid} not in expected range [0, {expected_uid}]"
        )
    else:
        # Local environment should preserve exact user/group
        assert stat_info.st_uid == expected_uid


@pytest.mark.integration
def test_environment_variables_passed(test_images, temp_workspace):
    """Test that user environment is correctly set up."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--",
            "env",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0
    # Should show environment variables including HOME
    assert "HOME=" in result.stdout


@pytest.mark.integration
def test_error_handling_invalid_image(temp_workspace):
    """Test error handling for invalid image."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--image",
            "nonexistent:image",
            "--",
            "echo",
            "hello",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode != 0
    assert "Error response from daemon" in result.stderr or "pull access denied" in result.stderr


@pytest.mark.integration
def test_volume_mounting(test_images, temp_workspace):
    """Test that current directory is properly mounted."""
    # Create a test file in the workspace
    test_file = Path(temp_workspace) / "host_file.txt"
    test_file.write_text("hello from host")

    # Access the file from within the container
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--",
            "cat",
            "host_file.txt",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0
    assert "hello from host" in result.stdout


@pytest.mark.integration
def test_config_command(temp_workspace):
    """Test that config command runs without errors."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "config",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0
    # Check that config shows expected values (format-agnostic)
    assert "image" in result.stdout and "ubuntu" in result.stdout
    assert "bash" in result.stdout


@pytest.mark.integration
def test_config_show_command(temp_workspace):
    """Test that config show command runs without errors."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "config",
            "show",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0
    # Check that config shows expected values (format-agnostic)
    assert "image" in result.stdout and "ubuntu" in result.stdout
    assert "bash" in result.stdout


@pytest.mark.integration
def test_config_with_user_config_file(temp_workspace):
    """Test that config command loads user config from ~/.ctenv.toml."""
    import os
    from pathlib import Path

    # Create a fake home directory in temp space
    fake_home = Path(temp_workspace) / "fake_home"
    fake_home.mkdir()

    # Create user config file
    user_config = fake_home / ".ctenv.toml"
    user_config.write_text("""
[defaults]
image = "python:3.12"
sudo = true

[containers.test_user]
image = "alpine:latest"
""")

    # Run config command with fake home
    env = os.environ.copy()
    env["HOME"] = str(fake_home)

    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "config",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
        env=env,
    )

    assert result.returncode == 0
    # Check that config shows expected values (format-agnostic)
    assert "python:3.12" in result.stdout  # Should show user config default image
    assert "bash" in result.stdout  # Default command
    assert "test_user" in result.stdout  # Should show user config container
    assert "alpine:latest" in result.stdout  # Container image


@pytest.mark.integration
def test_config_with_project_config_file(temp_workspace):
    """Test that config command loads project config from .ctenv.toml."""
    from pathlib import Path

    # Create project config file in temp workspace
    project_config = Path(temp_workspace) / ".ctenv.toml"
    project_config.write_text("""
[defaults]
image = "node:18"

[containers.test_project]
image = "ubuntu:22.04"
env = ["DEBUG=1"]
""")

    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "config",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    assert result.returncode == 0
    # Check that config shows expected values (format-agnostic)
    assert "image" in result.stdout and "ubuntu" in result.stdout
    assert "bash" in result.stdout
    assert "node:18" in result.stdout  # Should show project config default
    assert "test_project" in result.stdout  # Should show project config container


@pytest.mark.integration
def test_post_start_commands_execution(test_images, temp_workspace):
    """Test that post-start commands work correctly in shell environments."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--post-start-command",
            "echo 'post-start executed' > post_start_test.txt",
            "--",
            "cat",
            "post_start_test.txt",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    # This should reproduce the "read: Illegal option -d" error
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")

    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "post-start executed" in result.stdout


@pytest.mark.integration
def test_relative_volume_path_handling(test_images, temp_workspace):
    """Test that relative volume paths are handled correctly and result in absolute container paths."""
    # Create a test directory to mount
    test_dir = Path(temp_workspace) / "test_volume"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("test content")
    
    # Use relative path for volume (this should trigger the bug)
    # The container path should resolve to the absolute path of the temp workspace + test_volume
    expected_container_path = str(Path(temp_workspace).resolve() / "test_volume")
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--volume", "./test_volume",
            "--",
            "cat",
            f"{expected_container_path}/test.txt",  # Expected absolute container path
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )
    
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")
    
    # This should fail with the current bug showing "invalid mount path: './test_volume' mount path must be absolute"
    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "test content" in result.stdout


@pytest.mark.integration
def test_multiple_post_start_commands(test_images, temp_workspace):
    """Test multiple post-start commands to stress test the parsing."""
    result = subprocess.run(
        [
            "python3",
            "-m",
            "ctenv",
            "run",
            "--post-start-command",
            "echo 'first command'",
            "--post-start-command",
            "echo 'second command'",
            "--post-start-command",
            "touch /tmp/marker_file",
            "--",
            "sh",
            "-c",
            "echo 'Commands completed' && ls -la /tmp/marker_file",
        ],
        capture_output=True,
        text=True,
        cwd=temp_workspace,
    )

    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")

    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "Commands completed" in result.stdout
    assert "/tmp/marker_file" in result.stdout
