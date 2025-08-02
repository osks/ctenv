import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv.ctenv import (
    _load_config_file,
    _substitute_variables,
    find_project_config,
    find_user_config,
    ConfigFile,
    ContainerConfig,
)


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

[containers.dev]
image = "node:18"
env = ["DEBUG=1", "NODE_ENV=development"]
"""
        config_file.write_text(config_content)

        config_data = _load_config_file(config_file)

        assert config_data["defaults"]["image"] == "ubuntu:latest"
        assert config_data["defaults"]["sudo"] is True
        assert config_data["containers"]["dev"]["image"] == "node:18"
        assert "NODE_ENV=development" in config_data["containers"]["dev"]["env"]


@pytest.mark.unit
def test_load_config_file_with_run_args():
    """Test loading TOML config file with run_args."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        config_file = tmpdir / "ctenv.toml"

        config_content = """
[defaults]
image = "ubuntu:latest"
run_args = ["--memory=1g", "--cpus=1"]

[containers.debug]
image = "ubuntu:latest"
run_args = ["--cap-add=SYS_PTRACE", "--security-opt=seccomp=unconfined"]
"""
        config_file.write_text(config_content)

        config_data = _load_config_file(config_file)

        assert config_data["defaults"]["run_args"] == ["--memory=1g", "--cpus=1"]
        assert config_data["containers"]["debug"]["run_args"] == [
            "--cap-add=SYS_PTRACE",
            "--security-opt=seccomp=unconfined",
        ]


@pytest.mark.unit
def test_load_config_file_invalid_toml():
    """Test error handling for invalid TOML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        config_file = tmpdir / "ctenv.toml"
        config_file.write_text("invalid toml [[[")

        with pytest.raises(ValueError, match="Invalid TOML"):
            _load_config_file(config_file)


@pytest.mark.unit
def test_resolve_config_values_defaults():
    """Test resolving config values with default container (no config file defaults)."""
    # Create a CtenvConfig with the test data
    from ctenv.ctenv import CtenvConfig

    def create_test_config(containers, defaults):
        """Helper to create CtenvConfig for testing."""
        from ctenv.ctenv import merge_dict, ContainerConfig

        # Compute defaults (system defaults + file defaults if any)
        computed_defaults = ContainerConfig.builtin_defaults().to_dict()
        if defaults:
            computed_defaults = merge_dict(computed_defaults, defaults)

        # Convert to ContainerConfig instances
        defaults_config = ContainerConfig.from_dict(computed_defaults)
        containers_config = {
            name: ContainerConfig.from_dict(container_dict)
            for name, container_dict in containers.items()
        }

        return CtenvConfig(defaults=defaults_config, containers=containers_config)

    ctenv_config = create_test_config(
        containers={
            "default": {"image": "ubuntu:latest", "network": "bridge", "sudo": True}
        },
        defaults={},
    )

    resolved = ctenv_config.get_container(container="default")

    assert resolved.image == "ubuntu:latest"
    assert resolved.network == "bridge"
    assert resolved.sudo is True


@pytest.mark.unit
def test_resolve_config_values_container():
    """Test resolving config values with container (no config file defaults)."""
    from ctenv.ctenv import CtenvConfig

    def create_test_config(containers, defaults):
        """Helper to create CtenvConfig for testing."""
        from ctenv.ctenv import merge_dict, ContainerConfig

        # Compute defaults (system defaults + file defaults if any)
        computed_defaults = ContainerConfig.builtin_defaults().to_dict()
        if defaults:
            computed_defaults = merge_dict(computed_defaults, defaults)

        # Convert to ContainerConfig instances
        defaults_config = ContainerConfig.from_dict(computed_defaults)
        containers_config = {
            name: ContainerConfig.from_dict(container_dict)
            for name, container_dict in containers.items()
        }

        return CtenvConfig(defaults=defaults_config, containers=containers_config)

    ctenv_config = create_test_config(
        containers={
            "dev": {
                "image": "node:18",
                "network": "bridge",
                "sudo": False,
                "env": ["DEBUG=1"],
            }
        },
        defaults={},
    )

    resolved = ctenv_config.get_container(container="dev")

    assert resolved.image == "node:18"
    assert resolved.network == "bridge"
    assert resolved.sudo is False
    assert resolved.env == ["DEBUG=1"]


@pytest.mark.unit
def test_resolve_config_values_unknown_container():
    """Test error for unknown container."""
    from ctenv.ctenv import CtenvConfig

    def create_test_config(containers, defaults):
        """Helper to create CtenvConfig for testing."""
        from ctenv.ctenv import merge_dict, ContainerConfig

        # Compute defaults (system defaults + file defaults if any)
        computed_defaults = ContainerConfig.builtin_defaults().to_dict()
        if defaults:
            computed_defaults = merge_dict(computed_defaults, defaults)

        # Convert to ContainerConfig instances
        defaults_config = ContainerConfig.from_dict(computed_defaults)
        containers_config = {
            name: ContainerConfig.from_dict(container_dict)
            for name, container_dict in containers.items()
        }

        return CtenvConfig(defaults=defaults_config, containers=containers_config)

    ctenv_config = create_test_config(
        containers={"dev": {"image": "node:18"}}, defaults={}
    )

    with pytest.raises(ValueError, match="Unknown container 'unknown'"):
        ctenv_config.get_container(container="unknown")


@pytest.mark.unit
def test_config_create_with_file():
    """Test Config creation with config file (containers only, no defaults section)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with container-specific settings
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[containers.default]
image = "alpine:latest"
network = "bridge"
sudo = true
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Load config and resolve
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(
            container="default",  # Explicitly specify the container
            overrides=ContainerConfig.from_dict(
                {
                    "image": "ubuntu:22.04",  # Override image via CLI
                }
            ),
        )

        # CLI should override config file
        assert config.image == "ubuntu:22.04"
        # Config file values should be used for non-overridden options (from default container)
        assert config.sudo is True  # From default container in config file
        assert config.network == "bridge"  # From default container in config file


@pytest.mark.unit
def test_config_create_with_container():
    """Test Config creation with container."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with container
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[defaults]
image = "ubuntu:latest"
network = "none"

[containers.test]
image = "alpine:latest"
network = "bridge"
env = ["CI=true"]
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(container="test")

        # Should use container values
        assert config.image == "alpine:latest"
        assert config.network == "bridge"
        assert config.env == ["CI=true"]


@pytest.mark.unit
def test_empty_config_structure():
    """Test that CtenvConfig.load works with no config files."""
    import tempfile

    # Test that CtenvConfig.load works with no config files
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(
            start_dir=tmpdir
        )  # No config files in empty dir
        assert len(ctenv_config.containers) == 0  # No containers should be present
        # Check that defaults still work (contains system defaults)
        defaults_dict = ctenv_config.defaults.to_dict()
        assert defaults_dict["image"] == "ubuntu:latest"  # System default

        # But system defaults should be applied when resolving config
        config = ctenv_config.get_default()
        assert config.image == "ubuntu:latest"  # System default


@pytest.mark.unit
def test_default_container_merging():
    """Test that user-defined default container merges with builtin."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with custom default container
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[defaults]
sudo = false

[containers.default]
sudo = true
network = "bridge"
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(container="default")

        # Should merge builtin default with user default
        assert config.image == "ubuntu:latest"  # From builtin default
        assert config.sudo is True  # From user default container (overrides defaults)
        assert config.network == "bridge"  # From user default container


@pytest.mark.unit
def test_config_precedence():
    """Test configuration precedence: CLI > container > defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[defaults]
image = "ubuntu:latest"
network = "none"
sudo = false

[containers.dev]
image = "node:18"
network = "bridge"
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(
            container="dev",
            overrides=ContainerConfig.from_dict(
                {
                    "image": "alpine:latest",  # CLI override
                }
            ),
        )

        # CLI should take precedence
        assert config.image == "alpine:latest"
        # Context should override defaults
        assert config.network == "bridge"
        # Defaults should be used when not overridden
        assert config.sudo is False


@pytest.mark.unit
def test_substitute_variables_basic():
    """Test basic variable substitution."""
    import os

    variables = {"USER": "alice", "image": "test:latest"}

    result = _substitute_variables("Hello ${USER}", variables, os.environ)
    assert result == "Hello alice"

    result = _substitute_variables("Image: ${image}", variables, os.environ)
    assert result == "Image: test:latest"


@pytest.mark.unit
def test_substitute_variables_env():
    """Test environment variable substitution."""
    import os

    os.environ["TEST_VAR"] = "test_value"

    variables = {"USER": "alice"}
    result = _substitute_variables("Value: ${env.TEST_VAR}", variables, os.environ)
    assert result == "Value: test_value"

    # Test missing env var
    result = _substitute_variables("Missing: ${env.NONEXISTENT}", variables, os.environ)
    assert result == "Missing: "

    # Clean up
    del os.environ["TEST_VAR"]


@pytest.mark.unit
def test_substitute_variables_slug_filter():
    """Test slug filter for filesystem-safe strings."""
    import os

    variables = {"image": "docker.example.com:5000/app:v1.0"}

    result = _substitute_variables("Cache: ${image|slug}", variables, os.environ)
    assert result == "Cache: docker.example.com-5000-app-v1.0"


@pytest.mark.unit
def test_substitute_variables_unknown_filter():
    """Test error handling for unknown filters."""
    import os

    variables = {"image": "test:latest"}

    with pytest.raises(ValueError, match="Unknown filter: unknown"):
        _substitute_variables("Bad: ${image|unknown}", variables, os.environ)


# Test removed - substitute_in_container was replaced by ContainerConfig.resolve()


@pytest.mark.unit
def test_volumes_from_config_file():
    """Test that volumes from config file are properly loaded into ContainerConfig."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with volumes
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[containers.dev]
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

        # Create config from dev container
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(container="dev")

        # Check that volumes are loaded correctly (paths should be resolved)
        expected_node_modules = str((tmpdir / "node_modules").resolve())
        expected_src = str((tmpdir / "src").resolve())
        expected_volumes = [
            f"{expected_node_modules}:/app/node_modules",
            f"{expected_src}:/app/src:ro",
        ]
        assert config.volumes == expected_volumes
        assert config.image == "node:18"
        assert config.network == "bridge"
        assert config.env == ["NODE_ENV=development", "DEBUG=true"]

        # The config dict is already resolved, so paths should be resolved relative to config file
        # (The assertions above already check the resolved volumes)


@pytest.mark.unit
def test_volumes_cli_merge():
    """Test that CLI volumes are appended to config file volumes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with volumes
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[containers.dev]
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
        from ctenv.ctenv import CtenvConfig, resolve_relative_paths_in_container_config

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])

        # CLI overrides need to be resolved relative to current working directory
        cli_overrides = {
            "volumes": ["./data:/data", "./cache:/cache"],
            "env": ["DEBUG=true", "LOG_LEVEL=info"],
        }
        resolved_cli_overrides = resolve_relative_paths_in_container_config(
            ContainerConfig.from_dict(cli_overrides), Path.cwd()
        )

        config = ctenv_config.get_container(
            container="dev",
            overrides=resolved_cli_overrides,
        )

        # Check that volumes are resolved strings
        expected_node_modules = str((tmpdir / "node_modules").resolve())
        expected_data = str(
            (Path.cwd() / "data").resolve()
        )  # CLI paths resolved from cwd
        expected_cache = str(
            (Path.cwd() / "cache").resolve()
        )  # CLI paths resolved from cwd
        expected_volumes = [
            f"{expected_node_modules}:/app/node_modules",  # From config file
            f"{expected_data}:/data",  # From CLI
            f"{expected_cache}:/cache",  # From CLI
        ]
        assert config.volumes == expected_volumes

        # The config dict is already resolved (assertions above verify this)
        # CLI env vars should be appended to config file env vars
        assert config.env == [
            "NODE_ENV=development",
            "DEBUG=true",
            "LOG_LEVEL=info",
        ]
        assert config.image == "node:18"  # Other settings preserved


@pytest.mark.unit
def test_volumes_cli_only():
    """Test CLI volumes when no config file volumes exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file without volumes
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[containers.test]
image = "alpine:latest"
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Create config with only CLI volumes
        from ctenv.ctenv import CtenvConfig, resolve_relative_paths_in_container_config

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])

        # CLI overrides need to be resolved relative to current working directory
        cli_overrides = {"volumes": ["./data:/data"], "env": ["TEST=true"]}
        resolved_cli_overrides = resolve_relative_paths_in_container_config(
            ContainerConfig.from_dict(cli_overrides), Path.cwd()
        )

        config = ctenv_config.get_container(
            container="test",
            overrides=resolved_cli_overrides,
        )

        # Check that volumes are resolved strings (CLI paths resolved from cwd)
        expected_data = str((Path.cwd() / "data").resolve())
        assert config.volumes == [f"{expected_data}:/data"]  # CLI volume
        assert config.env == ["TEST=true"]
        assert config.image == "alpine:latest"

        # The config dict is already resolved (assertion above verifies this)


@pytest.mark.unit
def test_config_file_resolve_container_with_templating():
    """Test template variable substitution in container resolution."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config with templating
        config_content = """
[containers.test]
image = "example.com/app:v1"
volumes = ["cache-${user_name}:/cache"]
env = ["CACHE_DIR=/cache/${image|slug}"]
"""
        config_file = tmpdir / "ctenv.toml"
        config_file.write_text(config_content)

        # Load and resolve config
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(container="test")

        # Check that templates are preserved in the raw config dict (not yet resolved)
        assert config.volumes == ["cache-${user_name}:/cache"]
        assert config.env == ["CACHE_DIR=/cache/${image|slug}"]

        # Templates will be resolved later in parse_container_config() when creating ContainerSpec


@pytest.mark.unit
def test_config_file_volumes_through_cli_parsing():
    """Test that config file volumes work through actual CLI parsing (regression test for empty list override bug)."""
    import tempfile
    from unittest.mock import patch, Mock
    from ctenv.ctenv import cmd_run

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with volumes
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[containers.dev]
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
        args.container = "dev"
        args.config = [str(config_file)]  # Note: cmd_run uses args.config as a list now
        args.volumes = None  # No CLI volumes provided
        args.env = None  # No CLI env provided
        # Command is not used in this test since we pass it separately to cmd_run
        args.verbose = False
        args.quiet = False
        args.dry_run = True  # Don't actually run container
        # Set other required attributes that cmd_run expects
        args.image = None
        args.workspace = None  # Add workspace attribute
        args.workdir = None  # Fixed from working_dir
        args.sudo = None
        args.network = None
        args.gosu_path = str(gosu_path)
        args.post_start_commands = None
        args.platform = None
        args.run_args = None

        # Mock docker execution to capture the config
        captured_config = {}

        def mock_run_container(spec, *args, **kwargs):
            captured_config.update(
                {
                    "volumes": [vol.to_string() for vol in spec.volumes],
                    "env": spec.env,
                    "image": spec.image,
                }
            )
            # Return mock result object with returncode attribute
            mock_result = Mock()
            mock_result.returncode = 0
            return mock_result

        with (
            patch(
                "ctenv.ctenv.ContainerRunner.run_container",
                side_effect=mock_run_container,
            ),
            patch("sys.exit"),
        ):
            cmd_run(args, "echo test")

        # Verify config file volumes were preserved (not overridden by empty CLI list)
        # Paths should be resolved to absolute paths relative to config file directory
        # Use Path.resolve() to handle potential symlinks on macOS
        expected_node_modules = str((tmpdir / "node_modules").resolve())
        expected_data = str((tmpdir / "data").resolve())

        assert captured_config["volumes"] == [
            f"{expected_node_modules}:/app/node_modules:z",
            f"{expected_data}:/data:z",
        ]
        assert captured_config["env"] == ["NODE_ENV=development"]
        assert captured_config["image"] == "node:18"


@pytest.mark.unit
def test_get_builtin_defaults():
    """Test that ContainerConfig.builtin_defaults() returns the expected default values."""
    from ctenv.ctenv import ContainerConfig

    defaults_config = ContainerConfig.builtin_defaults()
    defaults = defaults_config.to_dict()

    # Check that it returns a dict
    assert isinstance(defaults, dict)

    # Check container settings defaults (user info is now in RuntimeContext)
    assert defaults["image"] == "ubuntu:latest"
    assert defaults["command"] == "bash"
    assert defaults["container_name"] == "ctenv-${project_root|slug}"  # Updated default
    assert defaults["workspace"] == "auto"  # Updated workspace field
    assert defaults["workdir"] == "auto"  # Updated workdir field
    assert defaults["env"] == []
    assert defaults["volumes"] == []
    assert defaults["post_start_commands"] == []
    assert defaults["sudo"] is False
    assert defaults["tty"] == "auto"
    assert defaults["gosu_path"] == "auto"

    # NOTSET values should be filtered out by to_dict()
    assert "ulimits" not in defaults
    assert "network" not in defaults
    assert "platform" not in defaults


@pytest.mark.unit
def test_working_dir_config():
    """Test that workdir can be configured via CLI and config file."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config file with workdir
        config_file = tmpdir / "ctenv.toml"
        config_content = """
[containers.test]
image = "alpine:latest"
workdir = "/custom/path"
"""
        config_file.write_text(config_content)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Test config file workdir
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(container="test")
        assert config.workdir == "/custom/path"

        # Test CLI override
        config_cli = ctenv_config.get_container(
            container="test",
            overrides=ContainerConfig.from_dict({"workdir": "/cli/override"}),
        )
        assert config_cli.workdir == "/cli/override"

        # Test default (no config file, no CLI)
        ctenv_config_default = CtenvConfig.load(start_dir=tmpdir)  # Empty directory
        config_default = ctenv_config_default.get_default()
        # workdir should be "auto" by default
        assert config_default.workdir == "auto"


@pytest.mark.unit
def test_gosu_path_config():
    """Test that gosu_path can be configured via CLI and config file."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create a fake gosu binary in the temp directory
        fake_gosu = tmpdir / "fake_gosu"
        fake_gosu.write_text('#!/bin/sh\nexec "$@"')
        fake_gosu.chmod(0o755)

        # Create config file with gosu_path
        config_file = tmpdir / "ctenv.toml"
        config_content = f"""
[containers.test]
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
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.get_container(container="test")

        # Check that gosu_path is in the raw config dict
        assert config.gosu_path == str(fake_gosu)

        # Test CLI override
        cli_gosu = tmpdir / "cli_gosu"
        cli_gosu.write_text('#!/bin/sh\nexec "$@"')
        cli_gosu.chmod(0o755)

        config_cli = ctenv_config.get_container(
            container="test",
            overrides=ContainerConfig.from_dict({"gosu_path": str(cli_gosu)}),
        )

        # Check that CLI gosu_path is in the raw config dict
        assert config_cli.gosu_path == str(cli_gosu)


@pytest.mark.unit
def test_volume_options_preserved():
    """Test that volume options are properly parsed and preserved."""
    from ctenv.ctenv import VolumeSpec

    # Test parsing various volume specification formats
    test_cases = [
        ("./data:/data", "./data", "/data", []),
        ("./src:/app/src:ro", "./src", "/app/src", ["ro"]),
        ("./cache:/cache:rw,chown", "./cache", "/cache", ["rw", "chown"]),
        ("./logs:/logs:ro,chown", "./logs", "/logs", ["ro", "chown"]),
    ]

    for spec_str, expected_host, expected_container, expected_options in test_cases:
        vol_spec = VolumeSpec.parse_as_volume(spec_str)

        assert vol_spec.host_path == expected_host
        assert vol_spec.container_path == expected_container
        assert vol_spec.options == expected_options

        # Test that it can be converted back to string
        reconstructed = vol_spec.to_string()
        # Note: to_string() might reorder or normalize, so we just check key components
        assert expected_host in reconstructed
        assert expected_container in reconstructed
        for option in expected_options:
            assert option in reconstructed


@pytest.mark.unit
def test_docker_args_volume_options():
    """Test that Docker args correctly merge :z with existing volume options."""
    import tempfile
    from ctenv.ctenv import ContainerRunner

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create fake gosu
        gosu_path = tmpdir / "gosu"
        gosu_path.write_text('#!/bin/sh\nexec "$@"')
        gosu_path.chmod(0o755)

        # Create config with volumes that have options
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(start_dir=tmpdir)  # Empty directory
        config = ctenv_config.get_default(
            overrides=ContainerConfig.from_dict(
                {"volumes": ["./src:/app/src:ro", "./data:/data", "./cache:/cache:rw"]}
            )
        )

        # Parse config to get ContainerSpec
        from ctenv.ctenv import parse_container_config, RuntimeContext
        import os
        import getpass

        import grp

        runtime = RuntimeContext(
            user_name=getpass.getuser(),
            user_id=os.getuid(),
            user_home=os.path.expanduser("~"),
            group_name=grp.getgrgid(os.getgid()).gr_name,
            group_id=os.getgid(),
            cwd=Path.cwd(),
            tty=False,
            project_root=Path.cwd(),
        )

        resolved_config = parse_container_config(config, runtime)

        # Create temporary entrypoint script
        script_path = tmpdir / "entrypoint.sh"
        script_path.write_text("#!/bin/sh\necho test")

        # Build Docker run arguments
        args = ContainerRunner.build_run_args(resolved_config, str(script_path))

        # Find volume arguments in the Docker command
        volume_args = [
            arg
            for arg in args
            if arg.startswith("--volume=")
            and ("src" in arg or "data" in arg or "cache" in arg)
        ]

        # Verify volume options are properly merged with :z
        volume_args_str = " ".join(volume_args)

        # Check that :z is properly added to existing options
        assert (
            "--volume=./src:/app/src:ro,z" in volume_args_str
        )  # :ro preserved, :z added
        assert "--volume=./data:/data:z" in volume_args_str  # only :z added
        assert (
            "--volume=./cache:/cache:rw,z" in volume_args_str
        )  # :rw preserved, :z added


@pytest.mark.unit
def test_load_project_config_direct_toml():
    """Test that load_project_config finds .ctenv.toml directly (not in .ctenv/ subdir)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create .ctenv.toml directly in the directory (not in .ctenv/ subdir)
        config_file = tmpdir / ".ctenv.toml"
        config_content = """
[defaults]
image = "ubuntu:20.04"

[containers.test]
image = "node:18"
"""
        config_file.write_text(config_content)

        # Test loading from the directory
        config_path = find_project_config(tmpdir)
        assert config_path is not None
        config = ConfigFile.load(config_path)
        assert config.defaults.image == "ubuntu:20.04"
        assert config.containers["test"].image == "node:18"


@pytest.mark.unit
def test_load_project_config_searches_upward():
    """Test that load_project_config searches upward through parent directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create nested directory structure
        subdir = tmpdir / "project" / "src"
        subdir.mkdir(parents=True)

        # Create .ctenv.toml in the root directory
        config_file = tmpdir / ".ctenv.toml"
        config_content = """
[containers.dev]
image = "python:3.11"
"""
        config_file.write_text(config_content)

        # Test loading from the nested subdirectory
        config_path = find_project_config(subdir)
        assert config_path is not None
        config = ConfigFile.load(config_path)
        assert config.containers["dev"].image == "python:3.11"


@pytest.mark.unit
def test_load_project_config_returns_none_when_not_found():
    """Test that load_project_config returns None when no config file is found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # No config file created
        config_path = find_project_config(tmpdir)

        assert config_path is None


@pytest.mark.unit
def test_load_user_config_direct_toml(monkeypatch):
    """Test that load_user_config finds ~/.ctenv.toml directly (not in ~/.ctenv/ subdir)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Mock Path.home() to return our temp directory
        monkeypatch.setattr(Path, "home", lambda: tmpdir)

        # Create .ctenv.toml directly in the home directory (not in .ctenv/ subdir)
        config_file = tmpdir / ".ctenv.toml"
        config_content = """
[defaults]
image = "alpine:latest"
sudo = true

[containers.home]
image = "ubuntu:22.04"
"""
        config_file.write_text(config_content)

        # Test loading user config
        config_path = find_user_config()
        assert config_path is not None
        config = ConfigFile.load(config_path)
        assert config.defaults.image == "alpine:latest"
        assert config.defaults.sudo is True
        assert config.containers["home"].image == "ubuntu:22.04"


@pytest.mark.unit
def test_load_user_config_returns_none_when_not_found(monkeypatch):
    """Test that load_user_config returns None when no config file is found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Mock Path.home() to return our temp directory
        monkeypatch.setattr(Path, "home", lambda: tmpdir)

        # No config file created
        config_path = find_user_config()

        assert config_path is None


@pytest.mark.unit
def test_resolve_relative_paths_with_notset_string():
    """Test that NOTSET strings are treated as literal paths (bad config case)."""
    from ctenv.ctenv import (
        ContainerConfig,
        NOTSET,
        resolve_relative_paths_in_container_config,
    )

    # This represents bad config - NOTSET strings should be converted to NOTSET objects
    # before reaching ContainerConfig, but if they somehow get through, they should
    # be treated as literal path values
    config = ContainerConfig(
        image="alpine",
        workspace="NOTSET",  # Bad: string instead of NOTSET object
        volumes=NOTSET,  # Good: NOTSET object
        gosu_path="./bin/gosu",
    )

    resolved_config = resolve_relative_paths_in_container_config(config, Path("/tmp"))

    # NOTSET string gets processed as literal volume spec
    assert resolved_config.workspace == "NOTSET:NOTSET"  # Becomes invalid volume spec

    # NOTSET object is left unchanged
    assert resolved_config.volumes is NOTSET

    # Regular paths are resolved normally
    assert str(resolved_config.gosu_path).endswith("/tmp/bin/gosu")

    # Original config should be unchanged (immutable)
    assert config.workspace == "NOTSET"
    assert config.gosu_path == "./bin/gosu"
