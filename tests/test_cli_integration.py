"""Integration tests for CLI functionality."""

import pytest
import subprocess
import tempfile
from pathlib import Path


@pytest.mark.integration
def test_cli_run_basic():
    """Test basic CLI run command."""
    result = subprocess.run([
        "python", "-m", "ctenv", "run", "--dry-run", "--", "echo", "hello"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr


@pytest.mark.integration
def test_cli_run_with_image():
    """Test CLI run command with specific image."""
    result = subprocess.run([
        "python", "-m", "ctenv", "run", "--image", "alpine:latest", 
        "--dry-run", "--", "echo", "hello"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr


@pytest.mark.integration  
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
        
        result = subprocess.run([
            "python", "-m", "ctenv", "run", "--config", str(config_file),
            "test", "--dry-run"
        ], capture_output=True, text=True, cwd=tmpdir)
        
        assert result.returncode == 0
        assert "[ctenv] run" in result.stderr


@pytest.mark.integration
def test_cli_run_invalid_container():
    """Test CLI run command with invalid container name."""
    result = subprocess.run([
        "python", "-m", "ctenv", "run", "nonexistent", "--dry-run"
    ], capture_output=True, text=True)
    
    # Should fail with error about unknown container
    assert result.returncode != 0
    assert "Unknown container" in result.stderr


@pytest.mark.integration
def test_cli_config_command():
    """Test CLI config command."""
    result = subprocess.run([
        "python", "-m", "ctenv", "config"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "Configuration:" in result.stdout


@pytest.mark.integration
def test_cli_help():
    """Test CLI help command."""
    result = subprocess.run([
        "python", "-m", "ctenv", "--help"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "ctenv" in result.stdout
    assert "run" in result.stdout


@pytest.mark.integration
def test_cli_run_with_volumes():
    """Test CLI run command with volume mounting."""
    result = subprocess.run([
        "python", "-m", "ctenv", "run", 
        "--volume", "/tmp:/tmp:ro",
        "--dry-run", "--", "echo", "hello"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr


@pytest.mark.integration 
def test_cli_run_with_env():
    """Test CLI run command with environment variables."""
    result = subprocess.run([
        "python", "-m", "ctenv", "run",
        "--env", "TEST_VAR=hello",
        "--dry-run", "--", "echo", "hello"
    ], capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "[ctenv] run" in result.stderr