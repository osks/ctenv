"""Tests for critical error handling scenarios."""

import pytest
import tempfile
from pathlib import Path
from ctenv.ctenv import validate_platform, VolumeSpec


@pytest.mark.unit
def test_platform_validation():
    """Test platform validation for supported/unsupported platforms."""
    # Supported platforms
    assert validate_platform("linux/amd64") is True
    assert validate_platform("linux/arm64") is True

    # Unsupported platforms should return False
    assert validate_platform("windows/amd64") is False
    assert validate_platform("darwin/arm64") is False
    assert validate_platform("invalid") is False
    assert validate_platform("") is False


@pytest.mark.unit
def test_volume_spec_edge_cases():
    """Test VolumeSpec parsing edge cases."""
    # Empty host path with container path should work
    spec = VolumeSpec.parse(":/container")
    assert spec.host_path == ""
    assert spec.container_path == "/container"

    # Special case: just ":" should work
    spec = VolumeSpec.parse(":")
    assert spec.host_path == ""
    assert spec.container_path == ""

    # Host path only (no colon) should set container_path = host_path
    spec = VolumeSpec.parse("/host/path")
    assert spec.host_path == "/host/path"
    assert spec.container_path == "/host/path"


@pytest.mark.unit
def test_volume_spec_malformed_formats():
    """Test that malformed volume specs raise errors."""
    # Too many colons should raise error
    with pytest.raises(ValueError, match="Invalid volume format"):
        VolumeSpec.parse("/host:/container:option1:option2:extra")

    # Invalid format with multiple consecutive colons
    with pytest.raises(ValueError, match="Invalid volume format"):
        VolumeSpec.parse("/host::/container::extra")


@pytest.mark.integration
def test_config_show_success():
    """Test config show command shows all configuration."""
    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with known containers
        config_file = tmpdir / ".ctenv.toml"
        config_content = """
[containers.valid]
image = "alpine:latest"
"""
        config_file.write_text(config_content)

        # Run config show (no longer accepts container argument)
        result = subprocess.run(
            [
                "python",
                "-m",
                "ctenv",
                "--config",
                str(config_file),
                "config",
                "show",
            ],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

        assert result.returncode == 0
        assert "defaults:" in result.stdout
        assert "containers:" in result.stdout
        assert "valid:" in result.stdout  # Container should be shown
        assert "alpine:latest" in result.stdout


@pytest.mark.integration
def test_config_invalid_toml_file():
    """Test behavior with invalid TOML config file."""
    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create invalid TOML file
        config_file = tmpdir / ".ctenv.toml"
        config_file.write_text("invalid toml [[[")

        result = subprocess.run(
            [
                "python",
                "-m",
                "ctenv",
                "--config",
                str(config_file),
                "run",
                "--dry-run",
                "--",
                "echo",
                "test",
            ],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )

        assert result.returncode != 0
        assert "Configuration error" in result.stderr


@pytest.mark.integration
def test_run_with_invalid_platform():
    """Test run command with invalid platform."""
    import subprocess

    result = subprocess.run(
        [
            "python",
            "-m",
            "ctenv",
            "run",
            "--platform",
            "windows/amd64",  # Invalid platform
            "--dry-run",
            "--",
            "echo",
            "test",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Unsupported platform" in result.stderr
    assert "Supported platforms: linux/amd64, linux/arm64" in result.stderr


@pytest.mark.integration
def test_help_and_invalid_commands():
    """Test help output and invalid command handling."""
    import subprocess

    # Test main help
    result = subprocess.run(
        ["python3", "-m", "ctenv", "--help"], capture_output=True, text=True
    )

    assert result.returncode == 0
    assert "ctenv" in result.stdout

    # Test invalid subcommand
    result = subprocess.run(
        ["python3", "-m", "ctenv", "invalid-command"], capture_output=True, text=True
    )

    assert result.returncode != 0


@pytest.mark.unit
def test_volume_spec_to_string_edge_cases():
    """Test VolumeSpec.to_string() edge cases for better coverage."""
    # Test empty host path case
    spec = VolumeSpec(host_path="", container_path="/container", options=[])
    result = spec.to_string()
    assert result == ":/container"

    # Test workspace format (empty container path with host path)
    spec = VolumeSpec(host_path="/host", container_path="", options=["opt1"])
    result = spec.to_string()
    assert result == "/host::opt1"

    # Test completely empty spec
    spec = VolumeSpec(host_path="", container_path="", options=[])
    result = spec.to_string()
    assert result == ":"
