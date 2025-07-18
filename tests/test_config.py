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
        defaults={},
        source_files=[],
        context_sources={},
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
        defaults={},
        source_files=[],
        context_sources={},
    )

    resolved = config_file.resolve_context("dev")

    assert resolved["image"] == "node:18"
    assert resolved["network"] == "bridge"
    assert resolved["sudo"] is False
    assert resolved["env"] == ["DEBUG=1"]


@pytest.mark.unit
def test_resolve_config_values_unknown_context():
    """Test error for unknown context."""
    config_file = ConfigFile(contexts={"dev": {"image": "node:18"}}, defaults={}, source_files=[], context_sources={})

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
            context="default",  # Explicitly specify the context
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

        config = ContainerConfig.create(context="test", config_file=str(config_file))

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

    # Test that ConfigFile.load works with no config files (no default context added)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        config_file = ConfigFile.load(start_dir=tmpdir)  # No config files in empty dir
        assert len(config_file.contexts) == 0  # No contexts should be present
        assert len(config_file.defaults) == 0  # No defaults should be present


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

        config = ContainerConfig.create(config_file=str(config_file), context="default")

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
def test_volumes_from_config_file():
    """Test that volumes from config file are properly loaded into ContainerConfig."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file with volumes
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[contexts.dev]
image = "node:18"
volumes = ["./node_modules:/app/node_modules", "./src:/app/src:ro"]
network = "bridge"
env = ["NODE_ENV=development", "DEBUG=true"]
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)
        
        # Create config from dev context
        config = ContainerConfig.create(
            context="dev", 
            config_file=str(config_file)
        )
        
        # Check that volumes are loaded correctly
        assert config.volumes == ("./node_modules:/app/node_modules", "./src:/app/src:ro")
        assert config.image == "node:18"
        assert config.network == "bridge"
        assert config.env_vars == ("NODE_ENV=development", "DEBUG=true")


@pytest.mark.unit  
def test_volumes_cli_merge():
    """Test that CLI volumes are appended to config file volumes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file with volumes
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[contexts.dev]
image = "node:18" 
volumes = ["./node_modules:/app/node_modules"]
env = ["NODE_ENV=development"]
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)
        
        # Create config with CLI additions
        config = ContainerConfig.create(
            context="dev",
            config_file=str(config_file),
            volumes=["./data:/data", "./cache:/cache"],
            env_vars=["DEBUG=true", "LOG_LEVEL=info"]
        )
        
        # CLI volumes should be appended to config file volumes
        assert config.volumes == ("./node_modules:/app/node_modules", "./data:/data", "./cache:/cache")
        # CLI env vars should be appended to config file env vars
        assert config.env_vars == ("NODE_ENV=development", "DEBUG=true", "LOG_LEVEL=info")
        assert config.image == "node:18"  # Other settings preserved


@pytest.mark.unit
def test_volumes_cli_only():
    """Test CLI volumes when no config file volumes exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file without volumes
        config_file = tmpdir / "ctenv.toml" 
        config_content = """
[contexts.test]
image = "alpine:latest"
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)
        
        # Create config with only CLI volumes
        config = ContainerConfig.create(
            context="test",
            config_file=str(config_file),
            volumes=["./data:/data"],
            env_vars=["TEST=true"]
        )
        
        # Should only contain CLI volumes/env
        assert config.volumes == ("./data:/data",)
        assert config.env_vars == ("TEST=true",)
        assert config.image == "alpine:latest"


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


@pytest.mark.unit
def test_config_file_volumes_through_cli_parsing():
    """Test that config file volumes work through actual CLI parsing (regression test for empty list override bug)."""
    import tempfile
    from unittest.mock import patch, Mock
    from ctenv import cmd_run
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file with volumes
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[contexts.dev]
image = "node:18"
volumes = ["./node_modules:/app/node_modules", "./data:/data"]
env = ["NODE_ENV=development"]
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)
        
        # Mock argparse args as if no CLI volumes/env were provided
        args = Mock()
        args.context = "dev"
        args.config = str(config_file)  # Note: cmd_run uses args.config, not args.config_file
        args.volume = None  # No CLI volumes provided
        args.env = None     # No CLI env provided  
        args.command = ["echo", "test"]
        args.verbose = False
        args.quiet = False
        args.dry_run = True  # Don't actually run container
        # Set other required attributes that cmd_run expects
        args.image = None
        args.dir = None
        args.sudo = None
        args.network = None
        args.gosu_path = str(gosu_path)
        args.post_start_cmd = None
        
        # Mock docker execution to capture the config
        captured_config = {}
        def mock_run_container(config, *args, **kwargs):
            captured_config.update({
                'volumes': config.volumes,
                'env_vars': config.env_vars,
                'image': config.image
            })
            # Return mock result object with returncode attribute
            mock_result = Mock()
            mock_result.returncode = 0
            return mock_result
            
        with patch('ctenv.ContainerRunner.run_container', side_effect=mock_run_container), \
             patch('sys.exit') as mock_exit:
            cmd_run(args)
            
        # Verify config file volumes were preserved (not overridden by empty CLI list)
        assert captured_config['volumes'] == ("./node_modules:/app/node_modules", "./data:/data")
        assert captured_config['env_vars'] == ("NODE_ENV=development",)
        assert captured_config['image'] == "node:18"


@pytest.mark.unit
def test_container_config_get_defaults():
    """Test that ContainerConfig.get_defaults() returns the expected default values."""
    from ctenv import ContainerConfig
    import os
    import pwd
    import grp
    from pathlib import Path
    
    defaults = ContainerConfig.get_defaults()
    
    # Check that it returns a ContainerConfig instance
    assert isinstance(defaults, ContainerConfig)
    
    # Check that user identity matches current user
    user_info = pwd.getpwuid(os.getuid())
    group_info = grp.getgrgid(os.getgid())
    
    assert defaults.user_name == user_info.pw_name
    assert defaults.user_id == user_info.pw_uid
    assert defaults.group_name == group_info.gr_name
    assert defaults.group_id == group_info.gr_gid
    assert defaults.user_home == user_info.pw_dir
    
    # Check container settings defaults
    assert defaults.image == "ubuntu:latest"
    assert defaults.command == "bash"
    assert defaults.container_name is None
    assert defaults.working_dir == Path(os.getcwd())
    assert defaults.env_vars == ()
    assert defaults.volumes == ()
    assert defaults.post_start_cmds == ()
    assert defaults.ulimits is None
    assert defaults.sudo is False
    assert defaults.network is None
    assert defaults.tty is False
    # gosu_path should be a Path object if found, or None if not found
    assert defaults.gosu_path is None or isinstance(defaults.gosu_path, Path)


@pytest.mark.unit
def test_working_dir_config():
    """Test that working_dir can be configured via CLI and config file."""
    import tempfile
    import os
    from ctenv import ContainerConfig
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create config file with working_dir
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[contexts.test]
image = "alpine:latest"
working_dir = "/custom/path"
"""
        config_file.write_text(config_content)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)
        
        # Test config file working_dir
        config = ContainerConfig.create(context="test", config_file=str(config_file))
        assert config.working_dir == Path("/custom/path")
        
        # Test CLI override
        config_cli = ContainerConfig.create(
            context="test", 
            config_file=str(config_file),
            dir="/cli/override"
        )
        assert config_cli.working_dir == Path("/cli/override")
        
        # Test default (no config file, no CLI)
        config_default = ContainerConfig.create()
        assert config_default.working_dir == Path(os.getcwd())


@pytest.mark.unit
def test_gosu_path_config():
    """Test that gosu_path can be configured via CLI and config file."""
    import tempfile
    import os
    from ctenv import ContainerConfig
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create a fake gosu binary in the temp directory
        fake_gosu = tmpdir / "fake_gosu"
        fake_gosu.write_text('#!/bin/sh\nexec "$@"')
        fake_gosu.chmod(0o755)
        
        # Create config file with gosu_path
        config_file = tmpdir / "ctenv.toml"
        config_content = f"""
[contexts.test]
image = "alpine:latest"
gosu_path = "{fake_gosu}"
"""
        config_file.write_text(config_content)
        
        # Create another fake gosu for the temp directory itself
        # (so tests can run even if system doesn't have gosu)
        temp_gosu = tmpdir / "gosu"
        temp_gosu.write_text('#!/bin/sh\nexec "$@"')
        temp_gosu.chmod(0o755)
        
        # Test config file gosu_path
        config = ContainerConfig.create(context="test", config_file=str(config_file))
        assert config.gosu_path == fake_gosu
        
        # Test CLI override
        cli_gosu = tmpdir / "cli_gosu"
        cli_gosu.write_text('#!/bin/sh\nexec "$@"')
        cli_gosu.chmod(0o755)
        
        config_cli = ContainerConfig.create(
            context="test", 
            config_file=str(config_file),
            gosu_path=str(cli_gosu)
        )
        assert config_cli.gosu_path == cli_gosu


@pytest.mark.unit
def test_volume_options_preserved():
    """Test that volume options like :ro are preserved and :z is properly merged."""
    from ctenv import ContainerRunner
    
    # Test volumes with various option combinations
    volumes = (
        "./data:/data",  # No options
        "./src:/app/src:ro",  # Read-only option
        "./cache:/cache:rw,chown",  # Multiple options including chown
        "./logs:/logs:ro,chown",  # Read-only + chown
    )
    
    processed_volumes, chown_paths = ContainerRunner.parse_volumes(volumes)
    
    # Verify chown paths were extracted
    assert "/cache" in chown_paths
    assert "/logs" in chown_paths
    
    # Verify processed volumes preserve options (except chown)
    assert "./data:/data" in processed_volumes
    assert "./src:/app/src:ro" in processed_volumes  
    assert "./cache:/cache:rw" in processed_volumes  # chown removed
    assert "./logs:/logs:ro" in processed_volumes    # chown removed
    
    # Test the volume-with-z logic
    for volume in processed_volumes:
        if ":" in volume and len(volume.split(":")) > 2:
            # Volume has options, should append ,z
            volume_with_z = f"{volume},z"
        else:
            # Volume has no options, should add :z
            volume_with_z = f"{volume}:z"
            
        # Verify the final volume format
        if volume == "./data:/data":
            assert volume_with_z == "./data:/data:z"
        elif volume == "./src:/app/src:ro":
            assert volume_with_z == "./src:/app/src:ro,z"
        elif volume == "./cache:/cache:rw":
            assert volume_with_z == "./cache:/cache:rw,z"
        elif volume == "./logs:/logs:ro":
            assert volume_with_z == "./logs:/logs:ro,z"


@pytest.mark.unit
def test_docker_args_volume_options():
    """Test that Docker args correctly merge :z with existing volume options."""
    import tempfile
    from ctenv import ContainerRunner, ContainerConfig
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)
        
        # Create config with volumes that have options
        config = ContainerConfig.create(
            volumes=["./src:/app/src:ro", "./data:/data", "./cache:/cache:rw"]
        )
        
        # Create temporary entrypoint script
        script_path = tmpdir / "entrypoint.sh"
        script_path.write_text("#!/bin/sh\necho test")
        
        # Build Docker run arguments
        args = ContainerRunner.build_run_args(config, str(script_path))
        
        # Find volume arguments in the Docker command
        volume_args = [arg for arg in args if arg.startswith("--volume=") and ("src" in arg or "data" in arg or "cache" in arg)]
        
        # Verify volume options are properly merged with :z
        volume_args_str = " ".join(volume_args)
        assert "--volume=./src:/app/src:ro,z" in volume_args_str  # :ro preserved, :z added
        assert "--volume=./data:/data:z" in volume_args_str       # only :z added
        assert "--volume=./cache:/cache:rw,z" in volume_args_str  # :rw preserved, :z added
