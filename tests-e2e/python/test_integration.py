"""Container integration tests for ctenv.

These tests run real Docker containers to verify ctenv functionality.
Each test shows a real ctenv command line that can be used as documentation.
"""

import os
from pathlib import Path

import pytest

from .framework import run_ctenv, start_ctenv, wait_for_container


def test_basic_container_execution(test_images, temp_workspace):
    """Test basic container execution with ubuntu."""
    result = run_ctenv("ctenv run -- whoami", cwd=temp_workspace)

    assert result.returncode == 0


def test_working_directory_is_mounted_path(test_images, temp_workspace):
    """Test that working directory inside container matches workspace mount."""
    result = run_ctenv("ctenv run -- pwd", cwd=temp_workspace)

    assert result.returncode == 0
    expected_path = str(Path(temp_workspace).resolve())
    assert result.stdout.strip() == expected_path


def test_file_permission_preservation(test_images, temp_workspace):
    """Test that files created in container have correct ownership on host."""
    result = run_ctenv("ctenv run -- touch test_permissions.txt", cwd=temp_workspace)

    assert result.returncode == 0

    file_path = Path(temp_workspace) / "test_permissions.txt"
    assert file_path.exists()

    stat_info = file_path.stat()
    expected_uid = os.getuid()

    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        assert stat_info.st_uid in (0, expected_uid), (
            f"File UID {stat_info.st_uid} not in expected range [0, {expected_uid}]"
        )
    else:
        assert stat_info.st_uid == expected_uid


def test_environment_variables_passed(test_images, temp_workspace):
    """Test that user environment is correctly set up."""
    result = run_ctenv("ctenv run -- env", cwd=temp_workspace)

    assert result.returncode == 0
    assert "HOME=" in result.stdout


def test_error_handling_invalid_image(temp_workspace):
    """Test error handling for invalid image."""
    result = run_ctenv(
        "ctenv run --image nonexistent:image -- echo hello",
        cwd=temp_workspace,
    )

    assert result.returncode != 0
    assert "Error response from daemon" in result.stderr or "pull access denied" in result.stderr


def test_volume_mounting(test_images, temp_workspace):
    """Test that current directory is properly mounted."""
    test_file = Path(temp_workspace) / "host_file.txt"
    test_file.write_text("hello from host")

    result = run_ctenv("ctenv run -- cat host_file.txt", cwd=temp_workspace)

    assert result.returncode == 0
    assert "hello from host" in result.stdout


def test_config_command(temp_workspace):
    """Test that config command runs without errors."""
    result = run_ctenv("ctenv config", cwd=temp_workspace)

    assert result.returncode == 0
    assert "image" in result.stdout and "ubuntu" in result.stdout
    assert "bash" in result.stdout


def test_config_show_command(temp_workspace):
    """Test that config show command runs without errors."""
    result = run_ctenv("ctenv config show", cwd=temp_workspace)

    assert result.returncode == 0
    assert "image" in result.stdout and "ubuntu" in result.stdout
    assert "bash" in result.stdout


def test_config_with_user_config_file():
    """Test that config command loads user config from ~/.ctenv.toml."""
    import tempfile

    # Use separate temp dirs to avoid project config inheritance
    with tempfile.TemporaryDirectory() as fake_home_dir:
        with tempfile.TemporaryDirectory() as plain_workspace_dir:
            fake_home = Path(fake_home_dir)
            plain_workspace = Path(plain_workspace_dir)

            user_config = fake_home / ".ctenv.toml"
            user_config.write_text("""
[defaults]
image = "python:3.12"
sudo = true

[containers.test_user]
image = "alpine:latest"
""")

            env = os.environ.copy()
            env["HOME"] = str(fake_home)

            # Run from plain_workspace (no project config) so user config defaults apply
            result = run_ctenv("ctenv config", cwd=plain_workspace, env=env)

            assert result.returncode == 0
            assert "python:3.12" in result.stdout
            assert "sudo = True" in result.stdout
            assert "test_user" in result.stdout
            assert "alpine:latest" in result.stdout


def test_config_with_project_config_file(temp_workspace):
    """Test that config command loads project config from .ctenv.toml."""
    project_config = Path(temp_workspace) / ".ctenv.toml"
    project_config.write_text("""
[defaults]
image = "node:18"

[containers.test_project]
image = "ubuntu:22.04"
env = ["DEBUG=1"]
""")

    result = run_ctenv("ctenv config", cwd=temp_workspace)

    assert result.returncode == 0
    assert "image" in result.stdout and "ubuntu" in result.stdout
    assert "bash" in result.stdout
    assert "node:18" in result.stdout
    assert "test_project" in result.stdout


def test_post_start_commands_execution(test_images, temp_workspace):
    """Test that post-start commands work correctly in shell environments."""
    result = run_ctenv(
        "ctenv run --post-start-command \"echo 'post-start executed' > post_start_test.txt\" -- cat post_start_test.txt",
        cwd=temp_workspace,
    )

    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")

    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "post-start executed" in result.stdout


def test_relative_volume_path_handling(test_images, temp_workspace):
    """Test that relative volume paths are handled correctly."""
    test_dir = Path(temp_workspace) / "test_volume"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("test content")

    expected_container_path = str(Path(temp_workspace).resolve() / "test_volume")

    result = run_ctenv(
        f"ctenv run --volume ./test_volume -- cat {expected_container_path}/test.txt",
        cwd=temp_workspace,
    )

    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")

    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "test content" in result.stdout


def test_multiple_post_start_commands(test_images, temp_workspace):
    """Test multiple post-start commands."""
    result = run_ctenv(
        'ctenv run --post-start-command "echo first" --post-start-command "echo second" --post-start-command "touch /tmp/marker_file" -- sh -c "echo done && ls -la /tmp/marker_file"',
        cwd=temp_workspace,
    )

    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        print(f"STDOUT: {result.stdout}")

    assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
    assert "done" in result.stdout
    assert "/tmp/marker_file" in result.stdout


def test_test_containers_have_test_label(test_images, temp_workspace, cleanup_registry):
    """Verify test framework adds test label to containers.

    This meta-test ensures test containers are labeled with se.osd.ctenv.test=true
    so they can be cleaned up separately from regular ctenv containers.
    """
    process = start_ctenv("ctenv run -- sleep infinity", cwd=temp_workspace)

    try:
        container = wait_for_container(timeout=15)
        cleanup_registry.register(container)

        # Check that the test label is present
        labels = container.inspect().get("Config", {}).get("Labels", {})
        assert labels.get("se.osd.ctenv.test") == "true", (
            f"Test container missing test label. Labels: {labels}"
        )
        # Also verify it has the managed label
        assert labels.get("se.osd.ctenv.managed") == "true"

    finally:
        process.terminate()
        process.wait()
