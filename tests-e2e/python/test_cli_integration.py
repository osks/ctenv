"""Integration tests for CLI functionality."""

import subprocess
import sys
import tempfile
from pathlib import Path


def test_cli_run_basic():
    """Test basic CLI run command."""
    result = subprocess.run(
        [sys.executable, "-m", "ctenv", "run", "--dry-run", "--", "echo", "hello"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr


def test_cli_run_with_image():
    """Test CLI run command with specific image."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ctenv",
            "run",
            "--image",
            "alpine:latest",
            "--dry-run",
            "--",
            "echo",
            "hello",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr


def test_cli_run_with_container_from_config():
    """Test CLI run command with container from config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file
        config_file = tmpdir / ".ctenv.toml"
        config_content = """
[containers.test]
image = "alpine:latest"
command = "echo test"
"""
        config_file.write_text(config_content)

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "ctenv",
                "--config",
                str(config_file),
                "run",
                "test",
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

        assert result.returncode == 0
        assert "[ctenv] run" in result.stderr


def test_cli_run_invalid_container():
    """Test CLI run command with invalid container name."""
    result = subprocess.run(
        [sys.executable, "-m", "ctenv", "run", "nonexistent", "--dry-run"],
        capture_output=True,
        text=True,
    )

    # Should fail with error about unknown container
    assert result.returncode != 0
    assert "Unknown container" in result.stderr


def test_cli_config_command():
    """Test CLI config command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [sys.executable, "-m", "ctenv", "config"], capture_output=True, text=True, cwd=tmpdir
        )

    assert result.returncode == 0
    # Check that config shows default values (format-agnostic)
    assert "ubuntu:latest" in result.stdout  # Default image
    assert "bash" in result.stdout  # Default command


def test_cli_help():
    """Test CLI help command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            [sys.executable, "-m", "ctenv", "--help"], capture_output=True, text=True, cwd=tmpdir
        )

    assert result.returncode == 0
    assert "ctenv" in result.stdout
    assert "run" in result.stdout


def test_cli_run_with_volumes():
    """Test CLI run command with volume mounting."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ctenv",
            "run",
            "--volume",
            "/tmp:/tmp:ro",
            "--dry-run",
            "--",
            "echo",
            "hello",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr


def test_cli_run_with_env():
    """Test CLI run command with environment variables."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ctenv",
            "run",
            "--env",
            "TEST_VAR=hello",
            "--dry-run",
            "--",
            "echo",
            "hello",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr


def test_cli_build_args_invalid_format():
    """Test error when build arg has no equals sign."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ctenv",
            "run",
            "--build-arg",
            "INVALID_ARG_NO_EQUALS",
            "--dry-run",
            "--",
            "echo",
            "hello",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Invalid build argument format" in result.stderr
    assert "Expected KEY=VALUE" in result.stderr


def test_cli_build_command_args_invalid_format():
    """Test error when build command build arg has no equals sign."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ctenv",
            "build",
            "--build-arg",
            "INVALID_ARG_NO_EQUALS",
            "default",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Invalid build argument format" in result.stderr
    assert "Expected KEY=VALUE" in result.stderr


def test_cli_invalid_subcommand():
    """Test help output for invalid subcommand."""
    result = subprocess.run(
        [sys.executable, "-m", "ctenv", "invalid_command"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2  # argparse returns 2 for invalid choices
    assert "usage:" in result.stderr or "usage:" in result.stdout


def test_cli_quiet_mode():
    """Test quiet mode logging configuration."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ctenv",
            "-q",  # Global flag must come before subcommand
            "run",
            "--dry-run",
            "--",
            "echo",
            "hello",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    # In quiet mode, should have minimal output
    assert len(result.stderr.strip()) < 50  # Very minimal stderr output


# -----------------------------------------------------------------------------
# Project directory and workdir tests
# -----------------------------------------------------------------------------


def _run_ctenv_dry(args, cwd=None, top_level_args=None):
    """Helper to run ctenv with dry-run and verbose output.

    Args:
        args: Arguments to pass after 'run --dry-run --gosu-path ...'
        cwd: Working directory
        top_level_args: Arguments to pass before 'run' (e.g., ['-p', '/path'])
    """
    gosu_path = Path(__file__).parent.parent.parent / "ctenv" / "binaries" / "gosu-amd64"
    cmd = [
        sys.executable,
        "-m",
        "ctenv",
        "--verbose",
    ]
    if top_level_args:
        cmd.extend(top_level_args)
    cmd.extend([
        "run",
        "--dry-run",
        "--gosu-path",
        str(gosu_path),
    ])
    cmd.extend(args)

    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


def test_project_dir_detection_from_subdirectory():
    """Test that project dir is detected when running from subdirectory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create .ctenv.toml
        config = workspace / ".ctenv.toml"
        config.write_text("""
[defaults]
project_target = "/repo"

[containers.test]
image = "ubuntu:22.04"
""")
        (workspace / "src").mkdir()

        result = _run_ctenv_dry(["test", "--", "pwd"], cwd=workspace / "src")

        assert result.returncode == 0
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo/src" in result.stdout
        assert "Working directory: /repo/src" in result.stderr


def test_project_behavior_without_config():
    """Test behavior when no .ctenv.toml exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        (workspace / "src").mkdir()

        result = _run_ctenv_dry(["--", "pwd"], cwd=workspace / "src")

        assert result.returncode == 0
        # When no project is detected, mounts cwd to itself
        assert ":z" in result.stdout and "src:" in result.stdout


def test_workdir_override():
    """Test --workdir flag overrides auto-detection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        config = workspace / ".ctenv.toml"
        config.write_text("""
[defaults]
project_target = "/repo"

[containers.test]
image = "ubuntu:22.04"
""")
        (workspace / "src").mkdir()
        (workspace / "tests").mkdir()

        result = _run_ctenv_dry(
            ["--workdir", "/repo/tests", "test", "--", "pwd"],
            cwd=workspace / "src",
        )

        assert result.returncode == 0
        assert "--workdir=/repo/tests" in result.stdout
        assert "Working directory: /repo/tests" in result.stderr


def test_cli_target_overrides_config():
    """Test that CLI -m overrides config project_target."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        config = workspace / ".ctenv.toml"
        config.write_text("""
[defaults]
project_target = "/repo"

[containers.test]
image = "ubuntu:22.04"
""")
        (workspace / "src").mkdir()

        result = _run_ctenv_dry(
            ["--project-target", "/custom", "test", "--", "pwd"],
            cwd=workspace / "src",
            top_level_args=["-p", str(workspace)],
        )

        assert result.returncode == 0
        assert ":/custom:z" in result.stdout
        assert "--workdir=/custom/src" in result.stdout


def test_subpath_outside_project_error():
    """Test error when subpath resolves outside project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        config = workspace / ".ctenv.toml"
        config.write_text("""
[containers.test]
image = "ubuntu:22.04"
""")

        result = _run_ctenv_dry(
            ["--subpath", "/outside/project", "test", "--", "pwd"],
            cwd=workspace,
        )

        assert result.returncode != 0
        assert "resolves outside project" in result.stderr
