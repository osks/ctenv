import tempfile
from pathlib import Path
import pytest
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from ctenv.ctenv import (
    _load_config_file,
    substitute_template_variables,
    substitute_in_container,
    load_project_config,
    load_user_config,
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
        from ctenv.ctenv import get_default_config_dict, merge_config

        # Compute defaults (system defaults + file defaults if any)
        computed_defaults = get_default_config_dict()
        if defaults:
            computed_defaults = merge_config(computed_defaults, defaults)

        return CtenvConfig(defaults=computed_defaults, containers=containers)

    ctenv_config = create_test_config(
        containers={
            "default": {"image": "ubuntu:latest", "network": "bridge", "sudo": True}
        },
        defaults={},
    )

    resolved = ctenv_config.resolve_container_config(container="default")

    assert resolved.image == "ubuntu:latest"
    assert resolved.network == "bridge"
    assert resolved.sudo is True


@pytest.mark.unit
def test_resolve_config_values_container():
    """Test resolving config values with container (no config file defaults)."""
    from ctenv.ctenv import CtenvConfig

    def create_test_config(containers, defaults):
        """Helper to create CtenvConfig for testing."""
        from ctenv.ctenv import get_default_config_dict, merge_config

        # Compute defaults (system defaults + file defaults if any)
        computed_defaults = get_default_config_dict()
        if defaults:
            computed_defaults = merge_config(computed_defaults, defaults)

        return CtenvConfig(defaults=computed_defaults, containers=containers)

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

    resolved = ctenv_config.resolve_container_config(container="dev")

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
        from ctenv.ctenv import get_default_config_dict, merge_config

        # Compute defaults (system defaults + file defaults if any)
        computed_defaults = get_default_config_dict()
        if defaults:
            computed_defaults = merge_config(computed_defaults, defaults)

        return CtenvConfig(defaults=computed_defaults, containers=containers)

    ctenv_config = create_test_config(
        containers={"dev": {"image": "node:18"}}, defaults={}
    )

    with pytest.raises(ValueError, match="Unknown container 'unknown'"):
        ctenv_config.resolve_container_config(container="unknown")


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
        config = ctenv_config.resolve_container_config(
            container="default",  # Explicitly specify the container
            cli_overrides={
                "image": "ubuntu:22.04",  # Override image via CLI
            },
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
        config = ctenv_config.resolve_container_config(container="test")

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
        assert ctenv_config.defaults["image"] == "ubuntu:latest"  # System default

        # But system defaults should be applied when resolving config
        resolved_config = ctenv_config.resolve_container_config()
        assert resolved_config.image == "ubuntu:latest"  # System default


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
        config = ctenv_config.resolve_container_config(container="default")

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
        config = ctenv_config.resolve_container_config(
            container="dev",
            cli_overrides={
                "image": "alpine:latest",  # CLI override
            },
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
    result = substitute_template_variables("Value: ${env.TEST_VAR}", variables)
    assert result == "Value: test_value"

    # Test missing env var
    result = substitute_template_variables("Missing: ${env.NONEXISTENT}", variables)
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
def test_substitute_in_container():
    """Test container-wide variable substitution."""
    import os

    os.environ["TEST_ENV"] = "test_value"

    variables = {"USER": "alice", "image": "docker.io/app:v1"}
    container_data = {
        "image": "docker.io/app:v1",
        "volumes": ["cache-${USER}:/cache"],
        "env": ["USER=${USER}", "CACHE=${image|slug}", "TEST=${env.TEST_ENV}"],
        "sudo": True,  # Non-string values should be preserved
    }

    result = substitute_in_container(container_data, variables)

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
        config = ctenv_config.resolve_container_config(container="dev")

        # Check that volumes are loaded correctly
        assert config.volumes == [
            "./node_modules:/app/node_modules",
            "./src:/app/src:ro",
        ]
        assert config.image == "node:18"
        assert config.network == "bridge"
        assert config.env == ["NODE_ENV=development", "DEBUG=true"]


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
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.resolve_container_config(
            container="dev",
            cli_overrides={
                "volumes": ["./data:/data", "./cache:/cache"],
                "env": ["DEBUG=true", "LOG_LEVEL=info"],
            },
        )

        # CLI volumes should be appended to config file volumes
        assert config.volumes == [
            "./node_modules:/app/node_modules",
            "./data:/data",
            "./cache:/cache",
        ]
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
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.resolve_container_config(
            container="test",
            cli_overrides={"volumes": ["./data:/data"], "env": ["TEST=true"]},
        )

        # Should only contain CLI volumes/env
        assert config.volumes == ["./data:/data"]
        assert config.env == ["TEST=true"]
        assert config.image == "alpine:latest"


@pytest.mark.unit
def test_config_file_resolve_container_with_templating():
    """Test template variable substitution in container resolution."""
    import tempfile
    import getpass

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create config with templating
        config_content = """
[containers.test]
image = "example.com/app:v1"
volumes = ["cache-${USER}:/cache"]
env = ["CACHE_DIR=/cache/${image|slug}"]
"""
        config_file = tmpdir / "ctenv.toml"
        config_file.write_text(config_content)

        # Load and resolve config
        from ctenv.ctenv import CtenvConfig

        ctenv_config = CtenvConfig.load(explicit_config_files=[config_file])
        config = ctenv_config.resolve_container_config(container="test")

        # The resolved config should have templates applied automatically
        resolved_volumes = config.resolve_templates().volumes
        resolved_env = config.resolve_templates().env

        expected_user = getpass.getuser()
        assert f"cache-{expected_user}:/cache" in resolved_volumes
        assert "CACHE_DIR=/cache/example.com-app-v1" in resolved_env


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
        args.working_dir = None
        args.sudo = None
        args.network = None
        args.gosu_path = str(gosu_path)
        args.post_start_commands = None

        # Mock docker execution to capture the config
        captured_config = {}

        def mock_run_container(config, *args, **kwargs):
            captured_config.update(
                {
                    "volumes": config.volumes,
                    "env": config.env,
                    "image": config.image,
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
        assert captured_config["volumes"] == [
            "./node_modules:/app/node_modules",
            "./data:/data",
        ]
        assert captured_config["env"] == ["NODE_ENV=development"]
        assert captured_config["image"] == "node:18"


@pytest.mark.unit
def test_get_default_config_dict():
    """Test that get_default_config_dict() returns the expected default values."""
    from ctenv.ctenv import get_default_config_dict
    import os
    import pwd
    import grp
    from pathlib import Path

    defaults = get_default_config_dict()

    # Check that it returns a dict
    assert isinstance(defaults, dict)

    # Check that user identity matches current user
    user_info = pwd.getpwuid(os.getuid())
    group_info = grp.getgrgid(os.getgid())

    assert defaults["user_name"] == user_info.pw_name
    assert defaults["user_id"] == user_info.pw_uid
    assert defaults["group_name"] == group_info.gr_name
    assert defaults["group_id"] == group_info.gr_gid
    assert defaults["user_home"] == user_info.pw_dir

    # Check container settings defaults
    assert defaults["image"] == "ubuntu:latest"
    assert defaults["command"] == "bash"
    assert defaults["container_name"] is None
    assert defaults["workspace"] == "auto"  # New workspace field
    assert defaults["workdir"] is None  # New workdir field
    assert defaults["env"] == []
    assert defaults["volumes"] == []
    assert defaults["post_start_commands"] == []
    assert defaults["ulimits"] is None
    assert defaults["sudo"] is False
    assert defaults["network"] is None
    assert defaults["tty"] is False
    # gosu_path should be a string path if found, or None if not found
    assert defaults["gosu_path"] is None or isinstance(defaults["gosu_path"], str)


@pytest.mark.unit
def test_working_dir_config():
    """Test that workdir can be configured via CLI and config file."""
    import tempfile
    import os

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
        config = ctenv_config.resolve_container_config(container="test")
        assert config.workdir == "/custom/path"

        # Test CLI override
        config_cli = ctenv_config.resolve_container_config(
            container="test", cli_overrides={"workdir": "/cli/override"}
        )
        assert config_cli.workdir == "/cli/override"

        # Test default (no config file, no CLI)
        ctenv_config_default = CtenvConfig.load(start_dir=tmpdir)  # Empty directory
        config_default = ctenv_config_default.resolve_container_config()
        assert config_default.workdir is None


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
        config = ctenv_config.resolve_container_config(container="test")
        assert config.gosu_path == fake_gosu

        # Test CLI override
        cli_gosu = tmpdir / "cli_gosu"
        cli_gosu.write_text('#!/bin/sh\nexec "$@"')
        cli_gosu.chmod(0o755)

        config_cli = ctenv_config.resolve_container_config(
            container="test", cli_overrides={"gosu_path": str(cli_gosu)}
        )
        assert config_cli.gosu_path == cli_gosu


@pytest.mark.unit
def test_volume_options_preserved():
    """Test that volume options like :ro are preserved and :z is properly merged."""
    from ctenv.ctenv import ContainerRunner

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
    assert "./logs:/logs:ro" in processed_volumes  # chown removed

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
        config = ctenv_config.resolve_container_config(
            cli_overrides={
                "volumes": ["./src:/app/src:ro", "./data:/data", "./cache:/cache:rw"]
            }
        )

        # Create temporary entrypoint script
        script_path = tmpdir / "entrypoint.sh"
        script_path.write_text("#!/bin/sh\necho test")

        # Build Docker run arguments
        args = ContainerRunner.build_run_args(config, str(script_path))

        # Find volume arguments in the Docker command
        volume_args = [
            arg
            for arg in args
            if arg.startswith("--volume=")
            and ("src" in arg or "data" in arg or "cache" in arg)
        ]

        # Verify volume options are properly merged with :z
        volume_args_str = " ".join(volume_args)
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
        config = load_project_config(tmpdir)

        assert config is not None
        assert config.defaults["image"] == "ubuntu:20.04"
        assert config.containers["test"]["image"] == "node:18"


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
        config = load_project_config(subdir)

        assert config is not None
        assert config.containers["dev"]["image"] == "python:3.11"


@pytest.mark.unit
def test_load_project_config_returns_none_when_not_found():
    """Test that load_project_config returns None when no config file is found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # No config file created
        config = load_project_config(tmpdir)

        assert config is None


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
        config = load_user_config()

        assert config is not None
        assert config.defaults["image"] == "alpine:latest"
        assert config.defaults["sudo"] is True
        assert config.containers["home"]["image"] == "ubuntu:22.04"


@pytest.mark.unit
def test_load_user_config_returns_none_when_not_found(monkeypatch):
    """Test that load_user_config returns None when no config file is found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Mock Path.home() to return our temp directory
        monkeypatch.setattr(Path, "home", lambda: tmpdir)

        # No config file created
        config = load_user_config()

        assert config is None
