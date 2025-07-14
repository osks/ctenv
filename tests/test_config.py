import os
import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv import find_config_file, load_config_file, resolve_config_values, Config


@pytest.mark.unit
def test_find_config_file_project():
    """Test finding project config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create .ctenv/config.toml
        config_dir = tmpdir / ".ctenv"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("[defaults]\nimage = \"test:latest\"")
        
        # Test finding from project root
        found = find_config_file(tmpdir)
        assert found.resolve() == config_file.resolve()
        
        # Test finding from subdirectory
        subdir = tmpdir / "subdir" / "nested"
        subdir.mkdir(parents=True)
        found = find_config_file(subdir)
        assert found.resolve() == config_file.resolve()


@pytest.mark.unit
def test_find_config_file_global():
    """Test finding global config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create fake home directory with global config
        home_dir = tmpdir / "home"
        home_dir.mkdir()
        config_dir = home_dir / ".ctenv"
        config_dir.mkdir()
        config_file = config_dir / "config.toml"
        config_file.write_text("[defaults]\nimage = \"global:latest\"")
        
        # Mock Path.home() to return our test directory
        original_home = Path.home
        Path.home = lambda: home_dir
        
        try:
            # Test from directory without project config
            test_dir = tmpdir / "project"
            test_dir.mkdir()
            found = find_config_file(test_dir)
            assert found == config_file
        finally:
            Path.home = original_home


@pytest.mark.unit
def test_find_config_file_none():
    """Test when no config file is found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Mock Path.home() to return directory without config
        original_home = Path.home
        Path.home = lambda: tmpdir / "home"
        
        try:
            found = find_config_file(tmpdir)
            assert found is None
        finally:
            Path.home = original_home


@pytest.mark.unit
def test_load_config_file():
    """Test loading TOML config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        config_file = tmpdir / "config.toml"
        
        config_content = """
[defaults]
image = "ubuntu:latest"
network = "bridge"
sudo = true
env = ["DEBUG=1"]

[contexts.dev]
image = "node:18"
env = ["DEBUG=1", "NODE_ENV=development"]
"""
        config_file.write_text(config_content)
        
        config_data = load_config_file(config_file)
        
        assert config_data["defaults"]["image"] == "ubuntu:latest"
        assert config_data["defaults"]["sudo"] is True
        assert config_data["contexts"]["dev"]["image"] == "node:18"
        assert "NODE_ENV=development" in config_data["contexts"]["dev"]["env"]


@pytest.mark.unit
def test_load_config_file_invalid_toml():
    """Test error handling for invalid TOML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        config_file = tmpdir / "config.toml"
        config_file.write_text("invalid toml [[[")
        
        with pytest.raises(ValueError, match="Invalid TOML"):
            load_config_file(config_file)


@pytest.mark.unit
def test_resolve_config_values_defaults():
    """Test resolving config values from defaults."""
    config_data = {
        "defaults": {
            "image": "ubuntu:latest",
            "network": "bridge",
            "sudo": True
        }
    }
    
    resolved = resolve_config_values(config_data)
    
    assert resolved["image"] == "ubuntu:latest"
    assert resolved["network"] == "bridge"
    assert resolved["sudo"] is True


@pytest.mark.unit
def test_resolve_config_values_context():
    """Test resolving config values with context."""
    config_data = {
        "defaults": {
            "image": "ubuntu:latest",
            "network": "none",
            "sudo": False
        },
        "contexts": {
            "dev": {
                "image": "node:18",
                "network": "bridge",
                "env": ["DEBUG=1"]
            }
        }
    }
    
    resolved = resolve_config_values(config_data, "dev")
    
    assert resolved["image"] == "node:18"  # Overridden by context
    assert resolved["network"] == "bridge"  # Overridden by context
    assert resolved["sudo"] is False  # From defaults
    assert resolved["env"] == ["DEBUG=1"]  # From context


@pytest.mark.unit
def test_resolve_config_values_unknown_context():
    """Test error for unknown context."""
    config_data = {
        "defaults": {"image": "ubuntu:latest"},
        "contexts": {"dev": {"image": "node:18"}}
    }
    
    with pytest.raises(ValueError, match="Unknown context 'unknown'"):
        resolve_config_values(config_data, "unknown")


@pytest.mark.unit
def test_config_from_cli_options_with_file():
    """Test Config creation with config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file
        config_file = tmpdir / "config.toml"
        config_content = """
[defaults]
image = "alpine:latest"
network = "bridge"
sudo = true
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text("#!/bin/sh\nexec \"$@\"")
        gosu_path.chmod(0o755)
        
        config = Config.from_cli_options(
            config_file=str(config_file),
            # Override image via CLI
            image="ubuntu:22.04"
        )
        
        # CLI should override config file
        assert config.image == "ubuntu:22.04"
        # Config file values should be used for non-overridden options
        assert config.sudo is True  # From config file
        assert config.network == "bridge"  # From config file


@pytest.mark.unit
def test_config_from_cli_options_with_context():
    """Test Config creation with context."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file with context
        config_file = tmpdir / "config.toml"
        config_content = """
[defaults]
image = "ubuntu:latest"
network = "none"

[contexts.test]
image = "alpine:latest"
network = "bridge"
env = ["CI=true"]
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text("#!/bin/sh\nexec \"$@\"")
        gosu_path.chmod(0o755)
        
        config = Config.from_cli_options(
            context="test",
            config_file=str(config_file)
        )
        
        # Should use context values
        assert config.image == "alpine:latest"
        assert config.network == "bridge"
        assert config.env_vars == ("CI=true",)


@pytest.mark.unit
def test_config_precedence():
    """Test configuration precedence: CLI > context > defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file
        config_file = tmpdir / "config.toml"
        config_content = """
[defaults]
image = "ubuntu:latest"
network = "none"
sudo = false

[contexts.dev]
image = "node:18"
network = "bridge"
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text("#!/bin/sh\nexec \"$@\"")
        gosu_path.chmod(0o755)
        
        config = Config.from_cli_options(
            context="dev",
            config_file=str(config_file),
            # CLI override
            image="alpine:latest"
        )
        
        # CLI should take precedence
        assert config.image == "alpine:latest"
        # Context should override defaults
        assert config.network == "bridge"
        # Defaults should be used when not overridden
        assert config.sudo is False