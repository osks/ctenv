"""Test handling of unknown configuration options."""

import pytest
import tempfile
from pathlib import Path
import logging

from ctenv.cli import CtenvConfig, ContainerConfig


@pytest.mark.unit
def test_unknown_config_options_in_from_dict(caplog):
    """Test that unknown options in from_dict are ignored with warning."""
    config_dict = {
        # Required fields
        "user_name": "testuser",
        "user_id": 1000,
        "group_name": "testgroup",
        "group_id": 1000,
        "user_home": "/home/testuser",
        "working_dir": "/test",
        # Valid optional field
        "image": "ubuntu:latest",
        # Unknown fields that should trigger warnings
        "entrypoint_commands": ["echo hello"],  # Old name
        "unknown_option": "value",
        "another_unknown": 123,
    }

    # Set logging to capture warnings
    with caplog.at_level(logging.WARNING):
        config = ContainerConfig.from_dict(config_dict)

    # Should create config successfully
    assert config.user_name == "testuser"
    assert config.image == "ubuntu:latest"
    
    # Should not have unknown attributes
    assert not hasattr(config, "entrypoint_commands")
    assert not hasattr(config, "unknown_option")
    assert not hasattr(config, "another_unknown")

    # Should have logged a warning
    assert len(caplog.records) == 1
    warning = caplog.records[0]
    assert warning.levelname == "WARNING"
    assert "Ignoring unknown configuration options" in warning.message
    assert "entrypoint_commands" in warning.message
    assert "unknown_option" in warning.message
    assert "another_unknown" in warning.message


@pytest.mark.unit
def test_unknown_config_options_in_file(caplog):
    """Test that unknown options in config files are handled gracefully."""
    config_content = """
[defaults]
image = "ubuntu:latest"
entrypoint_commands = ["echo hello"]
unknown_option = "test"

[contexts.test]
image = "alpine:latest"
another_unknown = 123
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        with caplog.at_level(logging.WARNING):
            ctenv_config = CtenvConfig.load(explicit_config_files=[Path(config_file)])
            config = ctenv_config.resolve_container_config()

        # Should load valid options
        assert config.image == "ubuntu:latest"

        # Should have warnings about unknown options
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        warning_text = " ".join(w.message for w in warnings)
        assert "entrypoint_commands" in warning_text
        assert "unknown_option" in warning_text

    finally:
        import os
        os.unlink(config_file)


@pytest.mark.unit
def test_unknown_config_options_in_context(caplog):
    """Test that unknown options in contexts are handled gracefully."""
    config_content = """
[contexts.mycontext]
image = "ubuntu:20.04"
command = "bash"
invalid_field = "should be ignored"
deprecated_option = true
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(config_content)
        config_file = f.name

    try:
        with caplog.at_level(logging.WARNING):
            ctenv_config = CtenvConfig.load(explicit_config_files=[Path(config_file)])
            config = ctenv_config.resolve_container_config(context="mycontext")

        # Should use valid options
        assert config.image == "ubuntu:20.04"
        assert config.command == "bash"

        # Should warn about unknown options
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        warning_text = " ".join(w.message for w in warnings)
        assert "invalid_field" in warning_text
        assert "deprecated_option" in warning_text

    finally:
        import os
        os.unlink(config_file)


@pytest.mark.unit
def test_valid_config_options_no_warnings(caplog):
    """Test that valid config options don't produce warnings."""
    config_dict = {
        # All valid fields
        "user_name": "testuser",
        "user_id": 1000,
        "group_name": "testgroup",
        "group_id": 1000,
        "user_home": "/home/testuser",
        "working_dir": "/test",
        "gosu_path": "/usr/local/bin/gosu",
        "working_dir_mount": "/repo",
        "gosu_mount": "/gosu",
        "image": "ubuntu:latest",
        "command": "bash",
        "container_name": "mycontainer",
        "env": ["FOO=bar"],
        "volumes": ["/data:/data"],
        "post_start_commands": ["echo ready"],
        "ulimits": {"nofile": 1024},
        "sudo": True,
        "network": "host",
        "tty": True,
    }

    with caplog.at_level(logging.WARNING):
        config = ContainerConfig.from_dict(config_dict)

    # Should create config with all fields
    assert config.user_name == "testuser"
    assert config.image == "ubuntu:latest"
    assert config.env == ["FOO=bar"]
    assert config.sudo is True

    # Should have no warnings
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 0