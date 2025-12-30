"""Pytest fixtures for container integration tests.

These fixtures provide:
- Docker availability checking
- Test image pre-pulling
- Temporary workspace creation
- Container cleanup registration
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from .framework.container import CleanupRegistry, find_container, wait_for_container


@pytest.fixture(scope="session")
def docker_available():
    """Skip tests if Docker is not available."""
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")


@pytest.fixture(scope="session")
def test_images(docker_available):
    """Ensure test images are available."""
    images = ["ubuntu:22.04", "alpine:latest"]
    for image in images:
        subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
        )
    return images


@pytest.fixture
def cleanup_registry():
    """Provide a cleanup registry for the test function.

    All containers registered with this registry will be cleaned up
    after the test, even if the test fails.
    """
    registry = CleanupRegistry()
    yield registry
    registry._cleanup_all()


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory with a basic .ctenv.toml."""
    with tempfile.TemporaryDirectory(prefix="ctenv_integ_") as tmpdir:
        workspace = Path(tmpdir)

        # Create a basic .ctenv.toml
        (workspace / ".ctenv.toml").write_text(
            """
[defaults]
image = "ubuntu:22.04"
"""
        )

        yield workspace


@pytest.fixture
def find_ctenv_container():
    """Fixture that returns the find_container function."""
    return find_container


@pytest.fixture
def wait_for_ctenv_container():
    """Fixture that returns the wait_for_container function."""
    return wait_for_container
