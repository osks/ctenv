"""Tests for container image build functionality."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from ctenv.config import (
    BuildConfig,
    ContainerConfig,
    RuntimeContext,
    NOTSET,
    CtenvConfig,
    convert_notset_strings,
    resolve_relative_paths_in_container_config,
)
from ctenv.image import BuildImageSpec, parse_build_spec, build_container_image
from ctenv.cli import cmd_run, cmd_build


@pytest.mark.unit
class TestBuildConfig:
    """Unit tests for BuildConfig dataclass."""

    def test_build_config_creation(self):
        """Test BuildConfig creation with default NOTSET values."""
        config = BuildConfig()
        assert config.dockerfile is NOTSET
        assert config.context is NOTSET
        assert config.tag is NOTSET
        assert config.args is NOTSET

    def test_build_config_with_values(self):
        """Test BuildConfig creation with explicit values."""
        config = BuildConfig(
            dockerfile="Dockerfile.test",
            context="./test",
            tag="my-app:test",
            args={"ENV": "test", "VERSION": "1.0"}
        )
        assert config.dockerfile == "Dockerfile.test"
        assert config.context == "./test"
        assert config.tag == "my-app:test"
        assert config.args == {"ENV": "test", "VERSION": "1.0"}

    def test_build_config_to_dict(self):
        """Test BuildConfig to_dict conversion."""
        config = BuildConfig(
            dockerfile="Dockerfile",
            context=".",
            tag="app:latest"
        )
        
        # Test with NOTSET values excluded (default)
        result = config.to_dict()
        expected = {
            "dockerfile": "Dockerfile",
            "context": ".",
            "tag": "app:latest"
        }
        assert result == expected
        
        # Test with NOTSET values included
        result_with_notset = config.to_dict(include_notset=True)
        assert result_with_notset["args"] is NOTSET

    def test_build_config_from_dict(self):
        """Test BuildConfig from_dict creation."""
        data = {
            "dockerfile": "Dockerfile.prod",
            "context": "./production",
            "tag": "prod:latest",
            "args": {"NODE_ENV": "production"},
            "unknown_field": "ignored"  # Should be filtered out
        }
        
        config = BuildConfig.from_dict(data)
        assert config.dockerfile == "Dockerfile.prod"
        assert config.context == "./production"
        assert config.tag == "prod:latest"
        assert config.args == {"NODE_ENV": "production"}


@pytest.mark.unit
class TestContainerConfigWithBuild:
    """Unit tests for ContainerConfig with build integration."""

    def test_container_config_with_build_dict(self):
        """Test ContainerConfig with build configuration from dict."""
        data = {
            "image": "ubuntu:latest",
            "build": {
                "dockerfile": "Dockerfile",
                "context": ".",
                "tag": "custom:latest"
            }
        }
        
        config = ContainerConfig.from_dict(data)
        assert config.image == "ubuntu:latest"
        assert isinstance(config.build, BuildConfig)
        assert config.build.dockerfile == "Dockerfile"
        assert config.build.context == "."
        assert config.build.tag == "custom:latest"

    def test_container_config_build_validation(self):
        """Test validation of mutually exclusive image and build."""
        from ctenv.config import validate_container_config
        
        # Test that image and build are mutually exclusive
        config = ContainerConfig(
            image="ubuntu:latest",
            build=BuildConfig(dockerfile="Dockerfile")
        )
        
        with pytest.raises(ValueError, match="Cannot specify both 'image' and 'build'"):
            validate_container_config(config)

    def test_apply_build_defaults(self):
        """Test application of build defaults."""
        from ctenv.config import apply_build_defaults
        
        config = ContainerConfig(
            image="ubuntu:latest",
            build=BuildConfig(dockerfile="Dockerfile.custom")
        )
        
        result = apply_build_defaults(config)
        
        # Image should be cleared when build is present
        assert result.image is NOTSET
        assert result.build.dockerfile == "Dockerfile.custom"
        # Defaults should be applied for missing fields
        assert result.build.context == "."
        assert result.build.tag == "ctenv-${project_dir|slug}:latest"
        assert result.build.args == {}

    def test_build_path_resolution(self):
        """Test that build paths are resolved relative to project directory."""
        config = ContainerConfig(
            build=BuildConfig(
                dockerfile="./docker/Dockerfile",
                context="../context"
            )
        )
        
        base_dir = Path("/project")
        resolved = resolve_relative_paths_in_container_config(config, base_dir)
        
        assert resolved.build.dockerfile == str((base_dir / "./docker/Dockerfile").resolve())
        assert resolved.build.context == str((base_dir / "../context").resolve())


@pytest.mark.unit
class TestBuildImageSpec:
    """Unit tests for BuildImageSpec and parsing."""

    def test_parse_build_spec_success(self):
        """Test successful parsing of build specification."""
        config = ContainerConfig(
            build=BuildConfig(
                dockerfile="Dockerfile",
                context=".",
                tag="test-app:latest",
                args={"ENV": "test"}
            ),
            platform="linux/amd64"
        )
        
        runtime = RuntimeContext(
            user_name="testuser",
            user_id=1000,
            user_home="/home/testuser",
            group_name="testgroup",
            group_id=1000,
            cwd=Path("/project"),
            tty=False,
            project_dir=Path("/project"),
            pid=12345,
        )
        
        spec = parse_build_spec(config, runtime)
        
        assert isinstance(spec, BuildImageSpec)
        assert spec.dockerfile == "Dockerfile"
        assert spec.context == "."
        assert spec.tag == "test-app:latest"
        assert spec.args == {"ENV": "test"}
        assert spec.platform == "linux/amd64"

    def test_parse_build_spec_no_build_config(self):
        """Test parsing when no build config is present."""
        config = ContainerConfig(image="ubuntu:latest")
        runtime = Mock()
        
        with pytest.raises(ValueError, match="No build configuration found"):
            parse_build_spec(config, runtime)

    def test_parse_build_spec_missing_required_fields(self):
        """Test parsing with missing required build fields."""
        config = ContainerConfig(
            build=BuildConfig(dockerfile="Dockerfile")  # Missing context and tag
        )
        runtime = Mock()
        
        with pytest.raises(ValueError, match="Missing required build field"):
            parse_build_spec(config, runtime)

    def test_parse_build_spec_variable_substitution(self):
        """Test that variables are substituted in build spec parsing."""
        config = ContainerConfig(
            build=BuildConfig(
                dockerfile="Dockerfile",
                context=".",
                tag="app-${project_dir|slug}:latest",
                args={"USER": "${user_name}"}
            )
        )
        
        runtime = RuntimeContext(
            user_name="testuser",
            user_id=1000,
            user_home="/home/testuser",
            group_name="testgroup",
            group_id=1000,
            cwd=Path("/My Project"),
            tty=False,
            project_dir=Path("/My Project"),
            pid=12345,
        )
        
        with patch.dict(os.environ, {}, clear=True):
            spec = parse_build_spec(config, runtime)
        
        assert spec.tag == "app--my project:latest"  # slug filter converts path, keeps spaces, replaces slashes
        assert spec.args == {"USER": "testuser"}


@pytest.mark.unit
class TestBuildContainerImage:
    """Unit tests for build_container_image function."""

    @patch('ctenv.image.subprocess.run')
    @patch.dict(os.environ, {'RUNNER': 'docker'})
    def test_build_container_image_success(self, mock_run):
        """Test successful container image build."""
        mock_run.return_value = Mock(stdout="Successfully built abc123\n")
        
        spec = BuildImageSpec(
            dockerfile="Dockerfile",
            context=".",
            tag="test-app:latest",
            args={"ENV": "test", "VERSION": "1.0"},
            platform="linux/amd64"
        )
        
        runtime = RuntimeContext(
            user_name="testuser",
            user_id=1000,
            user_home="/home/testuser",
            group_name="testgroup",
            group_id=1000,
            cwd=Path("/project"),
            tty=False,
            project_dir=Path("/project"),
            pid=12345,
        )
        
        result = build_container_image(spec, runtime, verbose=False)
        
        assert result == "test-app:latest"
        mock_run.assert_called_once()
        
        # Verify the build command structure
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "docker"
        assert call_args[1] == "build"
        assert "-f" in call_args
        assert "Dockerfile" in call_args
        assert "--platform" in call_args
        assert "linux/amd64" in call_args
        assert "--build-arg" in call_args
        assert "ENV=test" in call_args
        assert "VERSION=1.0" in call_args
        assert "-t" in call_args
        assert "test-app:latest" in call_args
        assert call_args[-1] == "."  # context should be last

    @patch('ctenv.image.subprocess.run')
    @patch.dict(os.environ, {'RUNNER': 'podman'})
    def test_build_container_image_podman(self, mock_run):
        """Test container image build with podman."""
        mock_run.return_value = Mock(stdout="")
        
        spec = BuildImageSpec(
            dockerfile="Dockerfile",
            context=".",
            tag="test:latest",
            args={}
        )
        
        runtime = Mock()
        runtime.project_dir = Path("/project")
        
        build_container_image(spec, runtime)
        
        # Verify podman is used
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "podman"

    @patch('ctenv.image.subprocess.run')
    def test_build_container_image_failure(self, mock_run):
        """Test handling of build failure."""
        from subprocess import CalledProcessError
        
        mock_run.side_effect = CalledProcessError(
            returncode=1, 
            cmd=["docker", "build"], 
            stderr="Build failed: missing file"
        )
        
        spec = BuildImageSpec(
            dockerfile="Dockerfile",
            context=".",
            tag="test:latest",
            args={}
        )
        
        runtime = Mock()
        runtime.project_dir = Path("/project")
        
        with pytest.raises(RuntimeError, match="Image build failed"):
            build_container_image(spec, runtime)

    @patch('ctenv.image.subprocess.run')
    def test_build_container_image_docker_not_found(self, mock_run):
        """Test handling when docker/podman is not found."""
        mock_run.side_effect = FileNotFoundError()
        
        spec = BuildImageSpec(
            dockerfile="Dockerfile",
            context=".",
            tag="test:latest",
            args={}
        )
        
        runtime = Mock()
        runtime.project_dir = Path("/project")
        
        with pytest.raises(RuntimeError, match="Container runtime .* not found"):
            build_container_image(spec, runtime)


@pytest.mark.integration
class TestBuildIntegration:
    """Integration tests for build functionality."""

    def test_config_file_build_integration(self):
        """Test loading build configuration from config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create config file with build configuration
            config_file = tmpdir / ".ctenv.toml"
            config_content = """
[containers.buildtest]
[containers.buildtest.build]
dockerfile = "Dockerfile.test"
context = "./build"
tag = "buildtest:latest"
args = { ENV = "test", DEBUG = "1" }
"""
            config_file.write_text(config_content)
            
            # Load configuration
            ctenv_config = CtenvConfig.load(tmpdir)
            container_config = ctenv_config.get_container("buildtest")
            
            # Verify build configuration is loaded correctly
            assert container_config.build is not NOTSET
            assert container_config.build.dockerfile == "Dockerfile.test"
            # Paths are resolved to absolute paths during loading
            assert container_config.build.context == str((tmpdir / "./build").resolve())
            assert container_config.build.tag == "buildtest:latest"
            assert container_config.build.args == {"ENV": "test", "DEBUG": "1"}

    @patch('ctenv.cli.build_container_image')
    @patch('ctenv.container.ContainerRunner.run_container')
    def test_cmd_run_with_build_config(self, mock_run_container, mock_build_image):
        """Test cmd_run with build configuration from config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create config file
            config_file = tmpdir / ".ctenv.toml"
            config_content = """
[containers.dev]
build = { dockerfile = "Dockerfile", context = ".", tag = "dev:latest" }
"""
            config_file.write_text(config_content)
            
            # Create mock Dockerfile
            dockerfile = tmpdir / "Dockerfile"
            dockerfile.write_text("FROM ubuntu:latest\n")
            
            # Ensure context directory exists (current directory in this case)
            assert tmpdir.exists()
            
            # Create fake gosu
            gosu_path = tmpdir / "gosu"
            gosu_path.write_text('#!/bin/sh\nexec "$@"')
            gosu_path.chmod(0o755)
            
            # Mock build returning image tag
            mock_build_image.return_value = "dev:latest"
            mock_run_container.return_value = Mock(returncode=0)
            
            # Create args mock
            args = Mock()
            args.container = "dev"
            args.config = [str(config_file)]
            args.verbose = False
            args.quiet = True
            args.dry_run = False
            args.project_dir = str(tmpdir)
            
            # Set all required attributes
            for attr in ["image", "workspace", "workdir", "env", "volumes", "sudo", 
                        "network", "post_start_commands", "platform", 
                        "run_args", "build_dockerfile", "build_context", "build_tag", 
                        "build_args"]:
                setattr(args, attr, None)
            
            # Set gosu_path to the fake gosu we created
            args.gosu_path = str(gosu_path)
            
            with patch('sys.exit'):
                cmd_run(args, "echo test")
            
            # Verify build was called
            mock_build_image.assert_called_once()
            
            # Verify container was run with built image
            mock_run_container.assert_called_once()
            run_call_args = mock_run_container.call_args[0]
            container_spec = run_call_args[0]
            assert container_spec.image == "dev:latest"

    @patch('ctenv.cli.build_container_image')
    def test_cmd_build_standalone(self, mock_build_image):
        """Test standalone ctenv build command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create config file
            config_file = tmpdir / ".ctenv.toml"
            config_content = """
[containers.api]
[containers.api.build]
dockerfile = "./api/Dockerfile.api"
context = "./api"
tag = "api:v1.0"
"""
            config_file.write_text(config_content)
            
            # Create the api directory and Dockerfile
            api_dir = tmpdir / "api"
            api_dir.mkdir()
            dockerfile = api_dir / "Dockerfile.api"
            dockerfile.write_text("FROM ubuntu:latest\n")
            
            # Mock successful build
            mock_build_image.return_value = "api:v1.0"
            
            # Create args mock
            args = Mock()
            args.container = "api"
            args.config = [str(config_file)]
            args.verbose = False
            args.quiet = True
            args.project_dir = str(tmpdir)
            
            # Set build-specific attributes
            for attr in ["build_dockerfile", "build_context", "build_tag", "build_args"]:
                setattr(args, attr, None)
            
            with patch('sys.exit'):
                cmd_build(args)
            
            # Verify build was called
            mock_build_image.assert_called_once()

    def test_build_cli_args_override_config(self):
        """Test that CLI build arguments override config file settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create config file with build config
            config_file = tmpdir / ".ctenv.toml"
            config_content = """
[containers.override]
build = { dockerfile = "Dockerfile.default", context = ".", tag = "default:latest" }
"""
            config_file.write_text(config_content)
            
            # Create CLI overrides
            cli_args_dict = {
                "build": {
                    "dockerfile": "Dockerfile.override",
                    "tag": "override:latest"
                    # context not specified - should use config default
                }
            }
            
            cli_overrides = resolve_relative_paths_in_container_config(
                ContainerConfig.from_dict(convert_notset_strings(cli_args_dict)),
                tmpdir,
            )
            
            # Load and merge configuration
            ctenv_config = CtenvConfig.load(tmpdir, explicit_config_files=[config_file])
            merged_config = ctenv_config.get_container("override", overrides=cli_overrides)
            
            # Verify CLI overrides take precedence
            assert merged_config.build.dockerfile == "Dockerfile.override"
            assert merged_config.build.tag == "override:latest"
            # Context is resolved to absolute path during loading
            assert merged_config.build.context == str(tmpdir.resolve())


@pytest.mark.integration
class TestBuildErrorHandling:
    """Integration tests for build error handling."""

    def test_build_missing_dockerfile(self):
        """Test error handling when Dockerfile is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            spec = BuildImageSpec(
                dockerfile="nonexistent.dockerfile",
                context=".",
                tag="test:latest",
                args={}
            )
            
            runtime = RuntimeContext(
                user_name="testuser",
                user_id=1000,
                user_home="/home/testuser",
                group_name="testgroup",
                group_id=1000,
                cwd=tmpdir,
                tty=False,
                project_dir=tmpdir,
                pid=12345,
            )
            
            # This should fail when trying to actually build (not mocked)
            with patch('ctenv.image.subprocess.run') as mock_run:
                from subprocess import CalledProcessError
                mock_run.side_effect = CalledProcessError(
                    returncode=1,
                    cmd=["docker", "build"],
                    stderr="unable to prepare context: unable to evaluate symlinks in Dockerfile"
                )
                
                with pytest.raises(RuntimeError, match="Image build failed"):
                    build_container_image(spec, runtime)

    def test_cmd_build_no_build_config(self):
        """Test cmd_build when no build configuration is found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Create config file without build configuration
            config_file = tmpdir / ".ctenv.toml"
            config_content = """
[containers.nobuild]
image = "ubuntu:latest"
"""
            config_file.write_text(config_content)
            
            # Create args mock
            args = Mock()
            args.container = "nobuild"
            args.config = [str(config_file)]
            args.verbose = False
            args.quiet = True
            args.project_dir = str(tmpdir)
            
            # Set build-specific attributes to None
            for attr in ["build_dockerfile", "build_context", "build_tag", "build_args"]:
                setattr(args, attr, None)
            
            with patch('sys.exit') as mock_exit:
                cmd_build(args)
                mock_exit.assert_called_with(1)