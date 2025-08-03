import pytest
import tempfile
import os
import subprocess
from pathlib import Path
from unittest.mock import patch


@pytest.fixture(scope="session")
def docker_available():
    """Check if Docker is available for integration tests."""
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")


@pytest.fixture(scope="session")
def test_images(docker_available):
    """Pull test images once per test session."""
    images = ["alpine:latest", "ubuntu:latest"]
    for image in images:
        try:
            subprocess.run(["docker", "pull", image], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pytest.skip(f"Could not pull test image: {image}")
    return images


@pytest.fixture
def temp_workspace():
    """Create temporary directory and change to it for test isolation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)

        # Create a fake gosu binary for testing in .ctenv directory
        ctenv_dir = Path(tmpdir) / ".ctenv"
        ctenv_dir.mkdir(exist_ok=True)
        gosu_path = ctenv_dir / "gosu"
        gosu_path.write_text(
            '#!/bin/sh\n# Fake gosu that drops the first argument (username) and runs the rest\nshift\nexec "$@"'
        )
        gosu_path.chmod(0o755)

        # Create a simple config file for integration tests
        config_file = ctenv_dir / "ctenv.toml"
        config_content = """[defaults]
image = "ubuntu:latest"

[contexts]
test = { image = "ubuntu:latest" }
"""
        config_file.write_text(config_content)

        yield tmpdir
        os.chdir(original_cwd)


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    return {
        "IMAGE": "alpine:latest",
        "DIR": "/test/dir",
        "DIR_MOUNT": "/repo",
        "GOSU": "/test/gosu",
        "GOSU_MOUNT": "/gosu",
        "USER_NAME": "testuser",
        "USER_ID": 1000,
        "GROUP_NAME": "testgroup",
        "GROUP_ID": 1000,
        "USER_HOME": "/home/testuser",
        "COMMAND": "bash",
    }


@pytest.fixture(autouse=True)
def mock_gosu_discovery(request):
    """Mock gosu discovery for tests that don't need actual gosu."""
    # Skip mocking for integration tests which need real gosu path resolution
    if "integration" in request.keywords:
        yield None
    else:
        with patch("ctenv.ctenv._find_bundled_gosu_path") as mock_find:
            # Return a fake gosu path for tests
            mock_find.return_value = "/test/gosu"
            yield mock_find


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests (fast)")
    config.addinivalue_line("markers", "integration: Integration tests with containers (slow)")
    config.addinivalue_line("markers", "slow: Slow tests requiring external resources")
