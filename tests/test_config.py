import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv import (
    find_config_file,
    load_config_file,
    ConfigFile,
    ContainerConfig,
    substitute_template_variables,
    substitute_in_context,
)


@pytest.mark.unit
def test_find_config_file_project():
    """Test finding project config file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create .ctenv/ctenv.toml
        config_dir = tmpdir / ".ctenv"
        config_dir.mkdir()
        config_file = config_dir / "ctenv.toml"
        config_file.write_text('[defaults]\nimage = "test:latest"')

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
        config_file = config_dir / "ctenv.toml"
        config_file.write_text('[defaults]\nimage = "global:latest"')

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
        config_file = tmpdir / "ctenv.toml"

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
        config_file = tmpdir / "ctenv.toml"
        config_file.write_text("invalid toml [[[")

        with pytest.raises(ValueError, match="Invalid TOML"):
            load_config_file(config_file)


@pytest.mark.unit
def test_resolve_config_values_defaults():
    """Test resolving config values with default context (no config file defaults)."""
    config_file = ConfigFile(
        contexts={
            "default": {"image": "ubuntu:latest", "network": "bridge", "sudo": True}
        },
        source_files=[],
    )

    resolved = config_file.resolve_context("default")

    assert resolved["image"] == "ubuntu:latest"
    assert resolved["network"] == "bridge"
    assert resolved["sudo"] is True


@pytest.mark.unit
def test_resolve_config_values_context():
    """Test resolving config values with context (no config file defaults)."""
    config_file = ConfigFile(
        contexts={
            "dev": {
                "image": "node:18",
                "network": "bridge",
                "sudo": False,
                "env": ["DEBUG=1"],
            }
        },
        source_files=[],
    )

    resolved = config_file.resolve_context("dev")

    assert resolved["image"] == "node:18"
    assert resolved["network"] == "bridge"
    assert resolved["sudo"] is False
    assert resolved["env"] == ["DEBUG=1"]


@pytest.mark.unit
def test_resolve_config_values_unknown_context():
    """Test error for unknown context."""
    config_file = ConfigFile(contexts={"dev": {"image": "node:18"}}, source_files=[])

    with pytest.raises(ValueError, match="Unknown context 'unknown'"):
        config_file.resolve_context("unknown")


@pytest.mark.unit
def test_config_create_with_file():
    """Test Config creation with config file (contexts only, no defaults section)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with context-specific settings
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[contexts.default]
image = "alpine:latest"
network = "bridge"
sudo = true
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        config = ContainerConfig.create(
            config_file=str(config_file),
            # Override image via CLI
            image="ubuntu:22.04",
        )

        # CLI should override config file
        assert config.image == "ubuntu:22.04"
        # Config file values should be used for non-overridden options (from default context)
        assert config.sudo is True  # From default context in config file
        assert config.network == "bridge"  # From default context in config file


@pytest.mark.unit
def test_config_create_with_context():
    """Test Config creation with context."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with context
        config_file = tmpdir / "ctenv.toml"
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
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        config = ContainerConfig.create(
            context="test", config_file=str(config_file)
        )

        # Should use context values
        assert config.image == "alpine:latest"
        assert config.network == "bridge"
        assert config.env_vars == ("CI=true",)


@pytest.mark.unit
def test_builtin_default_context():
    """Test that builtin default context is always available."""
    import tempfile
    from ctenv import get_builtin_default_context, ConfigFile

    # Test builtin default context content (just the context definition)
    builtin = get_builtin_default_context()
    assert builtin["image"] == "ubuntu:latest"

    # Test that ConfigFile.load always includes default context (with no config files)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        config_file = ConfigFile.load(start_dir=tmpdir)  # No config files in empty dir
        assert "default" in config_file.contexts
        assert config_file.contexts["default"]["image"] == "ubuntu:latest"


@pytest.mark.unit
def test_default_context_merging():
    """Test that user-defined default context merges with builtin."""
    import tempfile
    from ctenv import ContainerConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with custom default context
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[defaults]
sudo = false

[contexts.default]
sudo = true
network = "bridge"
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        config = ContainerConfig.create(
            config_file=str(config_file), context="default"
        )

        # Should merge builtin default with user default
        assert config.image == "ubuntu:latest"  # From builtin default
        assert config.sudo is True  # From user default context (overrides defaults)
        assert config.network == "bridge"  # From user default context


@pytest.mark.unit
def test_config_precedence():
    """Test configuration precedence: CLI > context > defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file
        config_file = tmpdir / "ctenv.toml"
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
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        config = ContainerConfig.create(
            context="dev",
            config_file=str(config_file),
            # CLI override
            image="alpine:latest",
        )

        # CLI should take precedence
        assert config.image == "alpine:latest"
        # Context should override defaults
        assert config.network == "bridge"
        # Defaults should be used when not overridden
        assert config.sudo is False


@pytest.mark.unit
def test_substitute_template_variables_basic():
    """Test basic variable substitution."""
    variables = {"USER": "alice", "image": "test:latest"}

    result = substitute_template_variables("Hello ${USER}", variables)
    assert result == "Hello alice"

    result = substitute_template_variables("Image: ${image}", variables)
    assert result == "Image: test:latest"


@pytest.mark.unit
def test_substitute_template_variables_env():
    """Test environment variable substitution."""
    import os

    os.environ["TEST_VAR"] = "test_value"

    variables = {"USER": "alice"}
    result = substitute_template_variables("Value: ${env:TEST_VAR}", variables)
    assert result == "Value: test_value"

    # Test missing env var
    result = substitute_template_variables("Missing: ${env:NONEXISTENT}", variables)
    assert result == "Missing: "

    # Clean up
    del os.environ["TEST_VAR"]


@pytest.mark.unit
def test_substitute_template_variables_slug_filter():
    """Test slug filter for filesystem-safe strings."""
    variables = {"image": "docker.example.com:5000/app:v1.0"}

    result = substitute_template_variables("Cache: ${image|slug}", variables)
    assert result == "Cache: docker.example.com-5000-app-v1.0"


@pytest.mark.unit
def test_substitute_template_variables_unknown_filter():
    """Test error handling for unknown filters."""
    variables = {"image": "test:latest"}

    with pytest.raises(ValueError, match="Unknown filter: unknown"):
        substitute_template_variables("Bad: ${image|unknown}", variables)


@pytest.mark.unit
def test_substitute_in_context():
    """Test context-wide variable substitution."""
    import os

    os.environ["TEST_ENV"] = "test_value"

    variables = {"USER": "alice", "image": "docker.io/app:v1"}
    context_data = {
        "image": "docker.io/app:v1",
        "volumes": ["cache-${USER}:/cache"],
        "env": ["USER=${USER}", "CACHE=${image|slug}", "TEST=${env:TEST_ENV}"],
        "sudo": True,  # Non-string values should be preserved
    }

    result = substitute_in_context(context_data, variables)

    assert result["image"] == "docker.io/app:v1"
    assert result["volumes"] == ["cache-alice:/cache"]
    assert result["env"] == ["USER=alice", "CACHE=docker.io-app-v1", "TEST=test_value"]
    assert result["sudo"] is True

    # Clean up
    del os.environ["TEST_ENV"]


@pytest.mark.unit
def test_config_file_resolve_context_with_templating():
    """Test that ConfigFile.resolve_context applies templating."""
    import tempfile
    import getpass

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config with templating
        config_content = """
[contexts.test]
image = "example.com/app:v1"
volumes = ["cache-${USER}:/cache"]
env = ["CACHE_DIR=/cache/${image|slug}"]
"""
        config_file = tmpdir / "ctenv.toml"
        config_file.write_text(config_content)

        # Load and resolve
        config_file_obj = ConfigFile.load(explicit_config_file=config_file)
        resolved = config_file_obj.resolve_context("test")

        expected_user = getpass.getuser()
        assert resolved["volumes"] == [f"cache-{expected_user}:/cache"]
        assert resolved["env"] == ["CACHE_DIR=/cache/example.com-app-v1"]
