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
