"""Tests for CLI parsing behavior."""

import pytest
from unittest.mock import patch, MagicMock
from io import StringIO
from ctenv.cli import create_parser, cmd_run


def create_test_ctenv_config(containers, defaults=None):
    """Helper to create CtenvConfig for testing."""
    from ctenv.cli import CtenvConfig, get_default_config_dict, merge_config

    # Compute defaults (system defaults + file defaults if any)
    computed_defaults = get_default_config_dict()
    if defaults:
        computed_defaults = merge_config(computed_defaults, defaults)

    return CtenvConfig(defaults=computed_defaults, containers=containers)


@pytest.mark.unit
class TestRunCommandParsing:
    """Test CLI parsing for the run command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = create_parser()

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_no_arguments(self, mock_run_container, mock_config_file_load):
        """Test: ctenv run (should use default bash command with default container)."""
        from ctenv.cli import main

        mock_ctenv_config = MagicMock()
        # Mock the defaults to return the expected default command
        mock_ctenv_config.defaults = {"command": "bash"}
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        # Test the new main() function - no command means interactive bash
        with patch("sys.exit"):
            main(["run"])

        # Should call resolve_container_config with None command (default will be used) and None container
        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert (
            call_kwargs["cli_overrides"]["command"] is None
        )  # No command specified, default will be used
        assert call_kwargs["container"] is None

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_with_valid_container(self, mock_run_container, mock_config_file_load):
        """Test: ctenv run dev (should use container with default command)."""
        from ctenv.cli import main

        mock_ctenv_config = MagicMock()
        # Mock the defaults to return the expected default command
        mock_ctenv_config.defaults = {"command": "bash"}
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        # Test the new main() function with container but no command
        with patch("sys.exit"):
            main(["run", "dev"])

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert (
            call_kwargs["cli_overrides"]["command"] is None
        )  # No command specified, default will be used
        assert call_kwargs["container"] == "dev"

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_with_invalid_container(self, mock_config_file_load):
        """Test: ctenv run invalid (should fail)."""
        from ctenv.cli import main

        mock_config_file = create_test_ctenv_config(
            containers={"dev": {"image": "ubuntu"}}
        )
        mock_config_file_load.return_value = mock_config_file

        # Test the new main() function with invalid container
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                main(["run", "invalid"])

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Unknown container 'invalid'" in stderr_output
            assert "Available: ['dev']" in stderr_output

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_with_command_only(self, mock_config_file_load):
        """Test: ctenv run -- echo test (command without explicit container)."""
        from ctenv.cli import main

        mock_config_file_load.return_value = create_test_ctenv_config(
            containers={"default": {"image": "ubuntu:latest"}}
        )

        # Test the new main() function that handles '--' separator
        # This simulates: ctenv run -- echo test
        with patch("ctenv.cli.cmd_run") as mock_cmd_run:
            with patch("sys.exit"):
                main(["run", "--", "echo", "test"])

        # Verify cmd_run was called with correct args and command
        mock_cmd_run.assert_called_once()
        args, command = mock_cmd_run.call_args[0]
        assert args.container is None  # No container specified
        assert command == "echo test"  # Command after -- as string

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_with_container_and_command(
        self, mock_run_container, mock_config_file_load
    ):
        """Test: ctenv run dev -- echo test (should use container with command)."""
        from ctenv.cli import main

        mock_ctenv_config = MagicMock()
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        # Test the new main() function that handles '--' separator
        # This simulates: ctenv run dev -- echo test
        with patch("sys.exit"):
            main(["run", "dev", "--", "echo", "test"])

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert call_kwargs["cli_overrides"]["command"] == "echo test"
        assert call_kwargs["container"] == "dev"

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_ambiguous_parsing_container_command(
        self, mock_run_container, mock_config_file_load
    ):
        """Test: ctenv run dev -- echo test (container + command with separator)."""
        from ctenv.cli import main

        mock_ctenv_config = MagicMock()
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        # The new approach requires '--' separator to avoid ambiguity
        # This simulates: ctenv run dev -- echo test
        with patch("sys.exit"):
            main(["run", "dev", "--", "echo", "test"])

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        # With the new approach, parsing is unambiguous
        assert call_kwargs["cli_overrides"]["command"] == "echo test"
        assert call_kwargs["container"] == "dev"

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_no_config_file_with_container(self, mock_config_file_load):
        """Test: ctenv run dev (only default container available - should fail)."""
        mock_config_file = create_test_ctenv_config(
            containers={"default": {"image": "ubuntu:latest"}}
        )
        mock_config_file_load.return_value = mock_config_file

        args = self.parser.parse_args(["run", "dev"])

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(args, None)

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Unknown container 'dev'" in stderr_output

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_container_with_options(self, mock_run_container, mock_config_file_load):
        """Test: ctenv run dev --image alpine (container with options)."""
        mock_ctenv_config = MagicMock()
        # Mock the defaults to return the expected default command
        mock_ctenv_config.defaults = {"command": "bash"}
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        args = self.parser.parse_args(["run", "dev", "--image", "alpine:latest"])

        with patch("sys.exit"):
            cmd_run(args, None)

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert (
            call_kwargs["cli_overrides"]["command"] is None
        )  # No command specified, default will be used
        assert (
            call_kwargs["cli_overrides"]["image"] == "alpine:latest"
        )  # CLI option override
        assert call_kwargs["container"] == "dev"

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_with_run_args(self, mock_run_container, mock_config_file_load):
        """Test: ctenv run --run-arg='--cap-add=NET_ADMIN' --run-arg='--memory=2g' (run args option)."""
        mock_ctenv_config = MagicMock()
        # Mock the defaults to return the expected default command
        mock_ctenv_config.defaults = {"command": "bash"}
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_container_config.platform = None  # Avoid platform validation error
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        args = self.parser.parse_args(
            ["run", "dev", "--run-arg=--cap-add=NET_ADMIN", "--run-arg=--memory=2g"]
        )

        with patch("sys.exit"):
            cmd_run(args, None)

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert call_kwargs["cli_overrides"]["run_args"] == [
            "--cap-add=NET_ADMIN",
            "--memory=2g",
        ]
        assert (
            call_kwargs["cli_overrides"]["command"] is None
        )  # No command specified, default will be used
        assert call_kwargs["container"] == "dev"


@pytest.mark.unit
class TestRunCommandEdgeCases:
    """Test edge cases in CLI parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = create_parser()

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_command_that_looks_like_container(self, mock_config_file_load):
        """Test: ctenv run echo (echo looks like command but treated as container)."""
        mock_config_file_load.return_value = create_test_ctenv_config(
            containers={"dev": {"image": "ubuntu"}}
        )

        args = self.parser.parse_args(["run", "echo"])

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(args, None)

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Unknown container 'echo'" in stderr_output

    @patch("ctenv.cli.CtenvConfig.load")
    def test_load_config_error(self, mock_config_file_load):
        """Test handling of configuration loading errors."""
        mock_config_file_load.side_effect = Exception("Config error")

        args = self.parser.parse_args(["run", "dev"])

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(args, None)

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Config error" in stderr_output
