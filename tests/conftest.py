import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch


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
def mock_gosu_discovery():
    """Mock gosu discovery for unit tests."""
    with patch("ctenv.container._find_bundled_gosu_path") as mock_find:
        mock_find.return_value = "/test/gosu"
        yield mock_find
