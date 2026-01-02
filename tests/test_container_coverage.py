"""Tests for container module coverage gaps."""

import pytest
from unittest.mock import Mock, patch
import subprocess
from io import StringIO

from ctenv.container import (
    get_platform_specific_gosu_name,
    is_installed_package,
    expand_tilde_in_path,
    check_podman_rootless_ready,
    ContainerRunner,
)
from ctenv.config import VolumeSpec, Verbosity, ContainerRuntime


class TestPlatformDetection:
    """Tests for platform-specific functionality."""

    def test_get_platform_specific_gosu_name_arm64_target(self):
        """Test ARM64 platform detection from target platform."""
        result = get_platform_specific_gosu_name("linux/arm64")
        assert result == "gosu-arm64"

    def test_get_platform_specific_gosu_name_amd64_target(self):
        """Test AMD64 platform detection from target platform."""
        result = get_platform_specific_gosu_name("linux/amd64")
        assert result == "gosu-amd64"

    def test_get_platform_specific_gosu_name_unknown_target(self):
        """Test unknown platform defaults to amd64."""
        result = get_platform_specific_gosu_name("linux/unknown")
        assert result == "gosu-amd64"

    @patch("platform.machine")
    def test_get_platform_specific_gosu_name_host_arm64(self, mock_machine):
        """Test ARM64 host platform detection."""
        mock_machine.return_value = "aarch64"
        result = get_platform_specific_gosu_name(None)
        assert result == "gosu-arm64"

    @patch("platform.machine")
    def test_get_platform_specific_gosu_name_host_arm64_variant(self, mock_machine):
        """Test ARM64 variant host platform detection."""
        mock_machine.return_value = "arm64"
        result = get_platform_specific_gosu_name(None)
        assert result == "gosu-arm64"

    @patch("platform.machine")
    def test_get_platform_specific_gosu_name_host_x86_64(self, mock_machine):
        """Test x86_64 host platform detection."""
        mock_machine.return_value = "x86_64"
        result = get_platform_specific_gosu_name(None)
        assert result == "gosu-amd64"

    @patch("platform.machine")
    def test_get_platform_specific_gosu_name_host_unknown(self, mock_machine):
        """Test unknown host platform defaults to amd64."""
        mock_machine.return_value = "unknown_arch"
        result = get_platform_specific_gosu_name(None)
        assert result == "gosu-amd64"


class TestPackageDetection:
    """Tests for package detection functionality."""

    @patch("importlib.util.find_spec")
    def test_is_installed_package_true(self, mock_find_spec):
        """Test detection when running as installed package."""
        mock_spec = Mock()
        mock_find_spec.return_value = mock_spec
        assert is_installed_package() is True

    @patch("importlib.util.find_spec")
    def test_is_installed_package_false(self, mock_find_spec):
        """Test detection when not running as installed package."""
        mock_find_spec.return_value = None
        assert is_installed_package() is False

    @patch("importlib.util.find_spec")
    def test_is_installed_package_import_error(self, mock_find_spec):
        """Test import error handling in package detection."""
        mock_find_spec.side_effect = ImportError("Module not found")
        assert is_installed_package() is False


class TestHomeDirectoryExpansion:
    """Tests for home directory expansion functionality."""

    def test_expand_tilde_in_path_bare_tilde(self):
        """Test expansion of bare tilde."""
        runtime = Mock()
        runtime.user_home = "/home/testuser"

        result = expand_tilde_in_path("~", runtime)
        assert result == "/home/testuser"

    def test_expand_tilde_in_path_tilde_with_path(self):
        """Test expansion of tilde with path."""
        runtime = Mock()
        runtime.user_home = "/home/testuser"

        result = expand_tilde_in_path("~/documents", runtime)
        assert result == "/home/testuser/documents"

    def test_expand_tilde_in_path_no_tilde(self):
        """Test no expansion when no tilde present."""
        runtime = Mock()
        runtime.user_home = "/home/testuser"

        result = expand_tilde_in_path("/absolute/path", runtime)
        assert result == "/absolute/path"


class TestContainerExecutionErrors:
    """Tests for container execution error handling."""

    @patch("ctenv.container.subprocess.run")
    def test_container_execution_failure_non_dry_run(self, mock_run):
        """Test container execution failure handling in non-dry-run mode."""
        # Setup the mock to raise CalledProcessError
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["docker", "run"], stderr="Container failed"
        )

        runner = ContainerRunner()

        # Create a minimal container spec
        spec = Mock()
        spec.image = "test:latest"
        spec.command = ["echo", "hello"]
        spec.env_vars = []
        spec.volumes = []
        spec.run_args = []
        spec.workdir = "/workspace"
        spec.user_name = "testuser"
        spec.user_id = 1000
        spec.group_name = "testgroup"
        spec.group_id = 1000
        spec.user_home = "/home/testuser"
        spec.container_name = "test-container"
        spec.network = None
        spec.platform = None
        spec.ulimits = {}
        spec.sudo = False
        spec.post_start_commands = []
        spec.env = []  # Environment variables (iterable)
        spec.tty = False
        spec.runtime = ContainerRuntime.DOCKER_ROOTFUL
        # Required VolumeSpec attributes
        spec.gosu = VolumeSpec(
            host_path="/usr/local/bin/gosu", container_path="/ctenv/gosu", options=[]
        )
        spec.chown_paths = []  # No chown paths for this test
        spec.subpaths = [VolumeSpec(host_path="/project", container_path="/workspace", options=[])]

        # Mock the entrypoint script creation and path checks
        with (
            patch("ctenv.container.build_entrypoint_script") as mock_build_script,
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.is_dir") as mock_is_dir,
            patch("shutil.which") as mock_which,
        ):
            mock_build_script.return_value = "#!/bin/bash\necho test"
            mock_exists.return_value = True  # gosu and subpaths exist
            mock_is_file.return_value = True  # gosu is a file
            mock_is_dir.return_value = True  # subpaths verification
            mock_which.return_value = "/usr/bin/docker"  # docker exists

            with pytest.raises(RuntimeError, match="Container execution failed"):
                runner.run_container(spec, dry_run=False)

    @patch("ctenv.container.subprocess.run")
    def test_container_execution_success_dry_run(self, mock_run):
        """Test container execution success in dry-run mode."""
        # Mock won't be called in dry-run mode, but set it up anyway
        mock_run.return_value = Mock(returncode=0)

        runner = ContainerRunner()

        # Create a minimal container spec
        spec = Mock()
        spec.image = "test:latest"
        spec.command = ["echo", "hello"]
        spec.env_vars = []
        spec.volumes = []
        spec.run_args = []
        spec.workdir = "/workspace"
        spec.user_name = "testuser"
        spec.user_id = 1000
        spec.group_name = "testgroup"
        spec.group_id = 1000
        spec.user_home = "/home/testuser"
        spec.container_name = "test-container"
        spec.network = None
        spec.platform = None
        spec.ulimits = {}
        spec.sudo = False
        spec.post_start_commands = []
        spec.env = []  # Environment variables (iterable)
        spec.tty = False
        spec.runtime = ContainerRuntime.DOCKER_ROOTFUL
        # Required VolumeSpec attributes
        spec.gosu = VolumeSpec(
            host_path="/usr/local/bin/gosu", container_path="/ctenv/gosu", options=[]
        )
        spec.chown_paths = []  # No chown paths for this test
        spec.subpaths = [VolumeSpec(host_path="/project", container_path="/workspace", options=[])]

        # Mock the entrypoint script creation and path checks
        with (
            patch("ctenv.container.build_entrypoint_script") as mock_build_script,
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.is_dir") as mock_is_dir,
            patch("shutil.which") as mock_which,
        ):
            mock_build_script.return_value = "#!/bin/bash\necho test"
            mock_exists.return_value = True  # gosu and subpaths exist
            mock_is_file.return_value = True  # gosu is a file
            mock_is_dir.return_value = True  # subpaths verification
            mock_which.return_value = "/usr/bin/docker"  # docker exists

            # In dry-run mode, should return successful result without calling subprocess
            result = runner.run_container(spec, dry_run=True)
            assert result.returncode == 0
            # Verify subprocess.run was not called in dry-run mode
            mock_run.assert_not_called()

    @patch("ctenv.container.subprocess.run")
    def test_container_with_custom_run_args_logging(self, mock_run):
        """Test debug logging of custom run arguments."""
        mock_run.return_value = Mock(returncode=0)

        runner = ContainerRunner()

        # Create a container spec with custom run args
        spec = Mock()
        spec.image = "test:latest"
        spec.command = ["echo", "hello"]
        spec.env_vars = []
        spec.volumes = []
        spec.run_args = ["--privileged", "--cap-add=SYS_ADMIN"]  # Custom run args
        spec.workdir = "/workspace"
        spec.user_name = "testuser"
        spec.user_id = 1000
        spec.group_name = "testgroup"
        spec.group_id = 1000
        spec.user_home = "/home/testuser"
        spec.container_name = "test-container"
        spec.network = None
        spec.platform = None
        spec.ulimits = {}
        spec.sudo = False
        spec.post_start_commands = []
        spec.env = []  # Environment variables (iterable)
        spec.tty = False
        spec.runtime = ContainerRuntime.DOCKER_ROOTFUL
        # Required VolumeSpec attributes
        spec.gosu = VolumeSpec(
            host_path="/usr/local/bin/gosu", container_path="/ctenv/gosu", options=[]
        )
        spec.chown_paths = []  # No chown paths for this test
        spec.subpaths = [VolumeSpec(host_path="/project", container_path="/workspace", options=[])]

        # Mock the entrypoint script creation and path checks
        with (
            patch("ctenv.container.build_entrypoint_script") as mock_build_script,
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.is_file") as mock_is_file,
            patch("pathlib.Path.is_dir") as mock_is_dir,
            patch("shutil.which") as mock_which,
        ):
            mock_build_script.return_value = "#!/bin/bash\necho test"
            mock_exists.return_value = True  # gosu and subpaths exist
            mock_is_file.return_value = True  # gosu is a file
            mock_is_dir.return_value = True  # subpaths verification
            mock_which.return_value = "/usr/bin/docker"  # docker exists

            # Capture stderr to verify verbose output
            captured_stderr = StringIO()
            with patch("sys.stderr", captured_stderr):
                runner.run_container(spec, verbosity=Verbosity.VERBOSE, dry_run=True)

            # Verify verbose output includes custom run args
            output = captured_stderr.getvalue()
            assert "Custom run arguments:" in output
            assert "--privileged" in output
            assert "--cap-add=SYS_ADMIN" in output


class TestPodmanRootlessCheck:
    """Tests for Podman rootless configuration check."""

    def test_check_podman_rootless_ready_both_configured(self):
        """Test when both subuid and subgid are configured."""
        import pwd
        import os

        username = pwd.getpwuid(os.getuid()).pw_name

        with patch("builtins.open") as mock_open:
            # Mock both files having the user entry
            def open_side_effect(path, *args, **kwargs):
                mock_file = Mock()
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)
                mock_file.__iter__ = Mock(return_value=iter([f"{username}:100000:65536\n"]))
                return mock_file

            mock_open.side_effect = open_side_effect

            ready, error = check_podman_rootless_ready()
            assert ready is True
            assert error is None

    def test_check_podman_rootless_ready_missing_subuid(self):
        """Test when subuid is not configured."""
        import pwd
        import os

        username = pwd.getpwuid(os.getuid()).pw_name

        with patch("builtins.open") as mock_open:

            def open_side_effect(path, *args, **kwargs):
                mock_file = Mock()
                mock_file.__enter__ = Mock(return_value=mock_file)
                mock_file.__exit__ = Mock(return_value=False)

                if "/etc/subuid" in str(path):
                    # subuid has no entry for user
                    mock_file.__iter__ = Mock(return_value=iter(["otheruser:100000:65536\n"]))
                else:
                    # subgid has entry
                    mock_file.__iter__ = Mock(return_value=iter([f"{username}:100000:65536\n"]))
                return mock_file

            mock_open.side_effect = open_side_effect

            ready, error = check_podman_rootless_ready()
            assert ready is False
            assert "/etc/subuid" in error
            assert "sudo usermod" in error

    def test_check_podman_rootless_ready_files_not_found(self):
        """Test when subuid/subgid files don't exist."""
        with patch("builtins.open") as mock_open:
            mock_open.side_effect = FileNotFoundError()

            ready, error = check_podman_rootless_ready()
            assert ready is False
            assert "/etc/subuid" in error
            assert "/etc/subgid" in error

    def test_check_podman_rootless_ready_permission_denied(self):
        """Test when files can't be read due to permissions."""
        with patch("builtins.open") as mock_open:
            mock_open.side_effect = PermissionError()

            # Should assume configured if we can't read
            ready, error = check_podman_rootless_ready()
            assert ready is True
            assert error is None
