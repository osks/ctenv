"""Tests for CLI parsing behavior."""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from ctenv import cli


@pytest.mark.unit
class TestRunCommandParsing:
    """Test CLI parsing for the run command."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_no_arguments(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run (should use default bash command with default context)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"default": {"image": "ubuntu:latest"}}, source_files=[]
        )
        mock_config = MagicMock()
        mock_config_from_cli.return_value = mock_config
        mock_run_container.return_value = MagicMock(returncode=0)

        result = self.runner.invoke(cli, ["run"])

        assert result.exit_code == 0
        # Should call config with bash as default command and default context
        mock_config_from_cli.assert_called_once()
        call_kwargs = mock_config_from_cli.call_args[1]
        assert call_kwargs["command"] == "bash"
        assert call_kwargs["context"] == "default"

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_with_valid_context(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run dev (should use context with default command)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"dev": {"image": "ubuntu"}}, source_files=[]
        )
        mock_config = MagicMock()
        mock_config_from_cli.return_value = mock_config
        mock_run_container.return_value = MagicMock(returncode=0)

        result = self.runner.invoke(cli, ["run", "dev"])

        assert result.exit_code == 0
        mock_config_from_cli.assert_called_once()
        call_kwargs = mock_config_from_cli.call_args[1]
        assert call_kwargs["command"] == "bash"
        assert call_kwargs["context"] == "dev"

    @patch("ctenv.ConfigFile.load")
    def test_run_with_invalid_context(self, mock_config_file_load):
        """Test: ctenv run invalid (should fail)."""
        from ctenv import ConfigFile

        mock_config_file = ConfigFile(
            contexts={"dev": {"image": "ubuntu"}}, source_files=[]
        )
        mock_config_file_load.return_value = mock_config_file

        result = self.runner.invoke(cli, ["run", "invalid"])

        assert result.exit_code == 1
        assert "Context 'invalid' not found" in result.output
        assert "Available: ['dev']" in result.output

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_with_command_only(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run -- echo test (edge case: treats echo as context, fails as expected)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"default": {"image": "ubuntu:latest"}}, source_files=[]
        )

        result = self.runner.invoke(cli, ["run", "--", "echo", "test"])

        # This is an edge case with simplified Click parsing - echo is treated as context
        assert result.exit_code == 1
        assert "Context 'echo' not found" in result.output

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_with_context_and_command(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run dev -- echo test (should use context with command)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"dev": {"image": "ubuntu"}}, source_files=[]
        )
        mock_config = MagicMock()
        mock_config_from_cli.return_value = mock_config
        mock_run_container.return_value = MagicMock(returncode=0)

        result = self.runner.invoke(cli, ["run", "dev", "--", "echo", "test"])

        assert result.exit_code == 0
        mock_config_from_cli.assert_called_once()
        call_kwargs = mock_config_from_cli.call_args[1]
        assert call_kwargs["command"] == "echo test"
        assert call_kwargs["context"] == "dev"

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_ambiguous_parsing_context_command(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run dev echo test (ambiguous - should treat echo test as command)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"dev": {"image": "ubuntu"}}, source_files=[]
        )
        mock_config = MagicMock()
        mock_config_from_cli.return_value = mock_config
        mock_run_container.return_value = MagicMock(returncode=0)

        result = self.runner.invoke(cli, ["run", "dev", "echo", "test"])

        assert result.exit_code == 0
        mock_config_from_cli.assert_called_once()
        call_kwargs = mock_config_from_cli.call_args[1]
        # In simplified Click parsing, 'echo test' becomes the command
        assert call_kwargs["command"] == "echo test"
        assert call_kwargs["context"] == "dev"

    @patch("ctenv.ConfigFile.load")
    def test_run_no_config_file_with_context(self, mock_config_file_load):
        """Test: ctenv run dev (only default context available - should fail)."""
        from ctenv import ConfigFile

        mock_config_file = ConfigFile(
            contexts={"default": {"image": "ubuntu:latest"}}, source_files=[]
        )
        mock_config_file_load.return_value = mock_config_file

        result = self.runner.invoke(cli, ["run", "dev"])

        assert result.exit_code == 1
        assert "Context 'dev' not found" in result.output

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_with_options(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run --image alpine -- whoami (edge case: treats whoami as context, fails)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"default": {"image": "ubuntu:latest"}}, source_files=[]
        )

        result = self.runner.invoke(
            cli, ["run", "--image", "alpine:latest", "--", "whoami"]
        )

        # This is an edge case with simplified Click parsing - whoami is treated as context
        assert result.exit_code == 1
        assert "Context 'whoami' not found" in result.output

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_context_with_options(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run dev --image alpine (context with options)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"dev": {"image": "ubuntu"}}, source_files=[]
        )
        mock_config = MagicMock()
        mock_config_from_cli.return_value = mock_config
        mock_run_container.return_value = MagicMock(returncode=0)

        result = self.runner.invoke(cli, ["run", "dev", "--image", "alpine:latest"])

        assert result.exit_code == 0
        mock_config_from_cli.assert_called_once()
        call_kwargs = mock_config_from_cli.call_args[1]
        assert call_kwargs["command"] == "bash"  # Default command
        assert call_kwargs["image"] == "alpine:latest"  # CLI option override
        assert call_kwargs["context"] == "dev"

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_working_command_no_args(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run (no args, default bash with default context)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"default": {"image": "ubuntu:latest"}}, source_files=[]
        )
        mock_config = MagicMock()
        mock_config_from_cli.return_value = mock_config
        mock_run_container.return_value = MagicMock(returncode=0)

        result = self.runner.invoke(cli, ["run"])

        assert result.exit_code == 0
        mock_config_from_cli.assert_called()
        call_kwargs = mock_config_from_cli.call_args[1]
        assert call_kwargs["command"] == "bash"
        assert call_kwargs["context"] == "default"

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_working_context_with_command(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run dev hello (context + command works when context exists)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"dev": {"image": "ubuntu"}}, source_files=[]
        )
        mock_config = MagicMock()
        mock_config_from_cli.return_value = mock_config
        mock_run_container.return_value = MagicMock(returncode=0)

        result = self.runner.invoke(cli, ["run", "dev", "hello"])

        assert result.exit_code == 0
        mock_config_from_cli.assert_called()
        call_kwargs = mock_config_from_cli.call_args[1]
        assert call_kwargs["command"] == "hello"
        assert call_kwargs["context"] == "dev"


@pytest.mark.unit
class TestRunCommandEdgeCases:
    """Test edge cases in CLI parsing."""

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch("ctenv.ConfigFile.load")
    def test_run_command_that_looks_like_context(self, mock_config_file_load):
        """Test: ctenv run echo (echo looks like command but treated as context)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"dev": {"image": "ubuntu"}}, source_files=[]
        )

        result = self.runner.invoke(cli, ["run", "echo"])

        # Should fail because 'echo' is not a valid context
        assert result.exit_code == 1
        assert "Context 'echo' not found" in result.output

    @patch("ctenv.ConfigFile.load")
    @patch("ctenv.ContainerConfig.from_cli_options")
    @patch("ctenv.ContainerRunner.run_container")
    def test_run_multiple_commands(
        self, mock_run_container, mock_config_from_cli, mock_config_file_load
    ):
        """Test: ctenv run -- sh -c 'echo hello && echo world' (edge case: treats sh as context)."""
        from ctenv import ConfigFile

        mock_config_file_load.return_value = ConfigFile(
            contexts={"default": {"image": "ubuntu:latest"}}, source_files=[]
        )

        result = self.runner.invoke(
            cli, ["run", "--", "sh", "-c", "echo hello && echo world"]
        )

        # This is an edge case with simplified Click parsing - sh is treated as context
        assert result.exit_code == 1
        assert "Context 'sh' not found" in result.output

    @patch("ctenv.ConfigFile.load")
    def test_load_config_error(self, mock_config_file_load):
        """Test handling of configuration loading errors."""
        mock_config_file_load.side_effect = Exception("Config error")

        result = self.runner.invoke(cli, ["run", "dev"])

        assert result.exit_code == 1
        assert "Error loading configuration: Config error" in result.output
