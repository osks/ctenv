"""Tests for CLI parsing behavior."""

import pytest
from unittest.mock import patch, MagicMock
from io import StringIO
from ctenv.cli import create_parser, cmd_run


def create_test_ctenv_config(contexts, defaults=None):
    """Helper to create CtenvConfig for testing."""
    from ctenv.cli import CtenvConfig, get_default_config_dict, merge_config

    # Compute defaults (system defaults + file defaults if any)
    computed_defaults = get_default_config_dict()
    if defaults:
        computed_defaults = merge_config(computed_defaults, defaults)

    return CtenvConfig(defaults=computed_defaults, contexts=contexts)


@pytest.mark.unit
class TestRunCommandParsing:
    """Test CLI parsing for the run command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = create_parser()

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_no_arguments(self, mock_run_container, mock_config_file_load):
        """Test: ctenv run (should use default bash command with default context)."""
        mock_ctenv_config = MagicMock()
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        args = self.parser.parse_args(["run"])

        with patch("sys.exit"):
            cmd_run(args)

        # Should call resolve_container_config with bash command and None context
        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert call_kwargs["cli_overrides"]["command"] == "bash"
        assert call_kwargs["context"] is None

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_with_valid_context(self, mock_run_container, mock_config_file_load):
        """Test: ctenv run dev (should use context with default command)."""
        mock_ctenv_config = MagicMock()
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        args = self.parser.parse_args(["run", "dev"])

        with patch("sys.exit"):
            cmd_run(args)

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert call_kwargs["cli_overrides"]["command"] == "bash"
        assert call_kwargs["context"] == "dev"

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_with_invalid_context(self, mock_config_file_load):
        """Test: ctenv run invalid (should fail)."""
        mock_config_file = create_test_ctenv_config(
            contexts={"dev": {"image": "ubuntu"}}
        )
        mock_config_file_load.return_value = mock_config_file

        args = self.parser.parse_args(["run", "invalid"])

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(args)

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Unknown context 'invalid'" in stderr_output
            assert "Available: ['dev']" in stderr_output

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_with_command_only(self, mock_config_file_load):
        """Test: ctenv run echo test (command without explicit context)."""
        mock_config_file_load.return_value = create_test_ctenv_config(
            contexts={"default": {"image": "ubuntu:latest"}}
        )

        # With argparse, no context means first arg is treated as context
        # To specify command only, we need to use default context explicitly
        args = self.parser.parse_args(["run", "echo", "test"])

        # argparse treats first positional as context, rest as command
        assert args.context == "echo"  # First arg becomes context
        assert args.command == ["test"]  # Rest becomes command

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_with_context_and_command(
        self, mock_run_container, mock_config_file_load
    ):
        """Test: ctenv run dev -- echo test (should use context with command)."""
        mock_ctenv_config = MagicMock()
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        args = self.parser.parse_args(["run", "dev", "--", "echo", "test"])

        with patch("sys.exit"):
            cmd_run(args)

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert call_kwargs["cli_overrides"]["command"] == "echo test"
        assert call_kwargs["context"] == "dev"

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_ambiguous_parsing_context_command(
        self, mock_run_container, mock_config_file_load
    ):
        """Test: ctenv run dev echo test (context + command works)."""
        mock_ctenv_config = MagicMock()
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        args = self.parser.parse_args(["run", "dev", "echo", "test"])

        with patch("sys.exit"):
            cmd_run(args)

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        # With argparse, this should parse correctly
        assert call_kwargs["cli_overrides"]["command"] == "echo test"
        assert call_kwargs["context"] == "dev"

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_no_config_file_with_context(self, mock_config_file_load):
        """Test: ctenv run dev (only default context available - should fail)."""
        mock_config_file = create_test_ctenv_config(
            contexts={"default": {"image": "ubuntu:latest"}}
        )
        mock_config_file_load.return_value = mock_config_file

        args = self.parser.parse_args(["run", "dev"])

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(args)

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Unknown context 'dev'" in stderr_output

    @patch("ctenv.cli.CtenvConfig.load")
    @patch("ctenv.cli.ContainerRunner.run_container")
    def test_run_context_with_options(self, mock_run_container, mock_config_file_load):
        """Test: ctenv run dev --image alpine (context with options)."""
        mock_ctenv_config = MagicMock()
        mock_config_file_load.return_value = mock_ctenv_config

        mock_container_config = MagicMock()
        mock_ctenv_config.resolve_container_config.return_value = mock_container_config
        mock_run_container.return_value = MagicMock(returncode=0)

        args = self.parser.parse_args(["run", "dev", "--image", "alpine:latest"])

        with patch("sys.exit"):
            cmd_run(args)

        mock_ctenv_config.resolve_container_config.assert_called_once()
        call_kwargs = mock_ctenv_config.resolve_container_config.call_args[1]
        assert call_kwargs["cli_overrides"]["command"] == "bash"  # Default command
        assert (
            call_kwargs["cli_overrides"]["image"] == "alpine:latest"
        )  # CLI option override
        assert call_kwargs["context"] == "dev"


@pytest.mark.unit
class TestRunCommandEdgeCases:
    """Test edge cases in CLI parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = create_parser()

    @patch("ctenv.cli.CtenvConfig.load")
    def test_run_command_that_looks_like_context(self, mock_config_file_load):
        """Test: ctenv run echo (echo looks like command but treated as context)."""
        mock_config_file_load.return_value = create_test_ctenv_config(
            contexts={"dev": {"image": "ubuntu"}}
        )

        args = self.parser.parse_args(["run", "echo"])

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(args)

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Unknown context 'echo'" in stderr_output

    @patch("ctenv.cli.CtenvConfig.load")
    def test_load_config_error(self, mock_config_file_load):
        """Test handling of configuration loading errors."""
        mock_config_file_load.side_effect = Exception("Config error")

        args = self.parser.parse_args(["run", "dev"])

        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with pytest.raises(SystemExit) as exc_info:
                cmd_run(args)

            assert exc_info.value.code == 1
            stderr_output = mock_stderr.getvalue()
            assert "Configuration error: Config error" in stderr_output
