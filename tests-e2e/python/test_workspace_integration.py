import subprocess
import sys
import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def workspace_with_config():
    """Create a temporary workspace with .ctenv.toml"""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)

        # Create .ctenv.toml
        config_content = """
[defaults]
project_mount = "/repo"

[containers.test]
image = "ubuntu:22.04"
"""
        (workspace / ".ctenv.toml").write_text(config_content)

        # Create subdirectories
        (workspace / "src").mkdir()
        (workspace / "tests").mkdir()

        yield workspace


@pytest.fixture
def workspace_without_config():
    """Create a temporary workspace without .ctenv.toml"""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        (workspace / "src").mkdir()
        yield workspace


def run_ctenv(workspace_dir, args, cwd=None, global_args=None):
    """Helper to run ctenv with dry-run

    Args:
        workspace_dir: The workspace directory
        args: Arguments to pass after 'run'
        cwd: Current working directory (defaults to workspace_dir)
        global_args: Arguments to pass before 'run' (e.g., ['-p', '.:/repo'])
    """
    if cwd is None:
        cwd = workspace_dir
    if global_args is None:
        global_args = []

    cmd = [
        sys.executable,
        "-m",
        "ctenv",
        "--verbose",
    ] + global_args + [
        "run",
        "--dry-run",
        "--gosu-path",
        str(Path(__file__).parent.parent.parent / "ctenv" / "binaries" / "gosu-amd64"),
    ] + args

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


class TestWorkspaceAutoDetection:
    """Test workspace auto-detection functionality"""

    def test_project_dir_detection(self, workspace_with_config):
        """Test that project dir is detected from subdirectory"""
        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        # Check that it mounts to /repo and workdir is /repo/src
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo/src" in result.stdout
        assert "-> /repo" in result.stderr
        assert "Working directory: /repo/src" in result.stderr

    def test_no_project_detection(self, workspace_without_config):
        """Test behavior when no .ctenv.toml exists"""
        # Without config, runs from src subdir - project_dir defaults to cwd
        result = run_ctenv(
            workspace_without_config,
            ["--", "pwd"],
            cwd=workspace_without_config / "src",
        )

        assert result.returncode == 0
        # When no project is detected, mounts cwd (src directory) to itself
        assert ":z" in result.stdout and "src:" in result.stdout
        assert "--workdir=" in result.stdout and "src" in result.stdout


class TestProjectMountSyntax:
    """Test project mount syntax variations (replaces old workspace volume syntax)"""

    def test_auto_workspace(self, workspace_with_config):
        """Test default workspace (uses project_mount from config)"""
        result = run_ctenv(workspace_with_config, ["test", "--", "pwd"])

        assert result.returncode == 0
        # Config has project_mount = "/repo"
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo" in result.stdout

    def test_project_dir_with_mount(self, workspace_with_config):
        """Test -p .:/repo syntax"""
        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],
            global_args=["-p", ".:/custom"],
        )

        assert result.returncode == 0
        # Project mounted at /custom
        assert ":/custom:z" in result.stdout
        assert "--workdir=/custom" in result.stdout

    def test_workspace_subdirectory(self, workspace_with_config):
        """Test workspace as subdirectory of project"""
        result = run_ctenv(
            workspace_with_config,
            ["--workspace", "src", "test", "--", "pwd"],
        )

        assert result.returncode == 0
        # Workspace is src subdir, mounted relative to project_mount
        assert "src:/repo/src:z" in result.stdout
        assert "--workdir=/repo/src" in result.stdout


class TestWorkingDirectoryTranslation:
    """Test working directory path translation"""

    def test_relative_position_preserved(self, workspace_with_config):
        """Test that relative position is preserved when mounting to different path"""
        # Config has project_mount = "/repo"
        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo/src" in result.stdout
        assert "Working directory: /repo/src" in result.stderr

    def test_workdir_override(self, workspace_with_config):
        """Test --workdir override"""
        # Config has project_mount = "/repo"
        result = run_ctenv(
            workspace_with_config,
            [
                "--workdir",
                "/repo/tests",
                "test",
                "--",
                "pwd",
            ],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo/tests" in result.stdout
        assert "Working directory: /repo/tests" in result.stderr


class TestConfigFileWorkspace:
    """Test workspace settings in config files"""

    def test_config_project_mount_applied(self, workspace_with_config):
        """Test that config file project_mount is applied"""
        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        # Config has project_mount = "/repo"
        # Handle macOS path normalization (/private prefix)
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo/src" in result.stdout

    def test_cli_overrides_config(self, workspace_with_config):
        """Test that CLI -p overrides config project_mount"""
        # Use explicit path to project root (not . from src subdir)
        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],
            cwd=workspace_with_config / "src",
            global_args=["-p", f"{workspace_with_config}:/custom"],
        )

        assert result.returncode == 0
        # CLI should override config project_mount
        # Handle macOS path normalization (/private prefix)
        assert ":/custom:z" in result.stdout
        assert "--workdir=/custom/src" in result.stdout


class TestErrorHandling:
    """Test error handling scenarios"""

    def test_nonexistent_workspace(self, workspace_with_config):
        """Test error when workspace doesn't exist"""
        nonexistent_path = "/does/not/exist"
        result = run_ctenv(
            workspace_with_config,
            ["--workspace", nonexistent_path, "test", "--", "pwd"],
        )

        assert result.returncode != 0
        assert "does not exist" in result.stderr

    def test_workspace_not_directory(self, workspace_with_config):
        """Test error when workspace is not a directory"""
        file_path = workspace_with_config / "file.txt"
        file_path.write_text("not a directory")

        result = run_ctenv(
            workspace_with_config, ["--workspace", str(file_path), "test", "--", "pwd"]
        )

        assert result.returncode != 0
        assert "not a directory" in result.stderr


class TestRealWorldScenarios:
    """Test real-world usage scenarios from the task"""

    def test_build_reproducibility_scenario(self, workspace_with_config):
        """Test Use Case 5: Build reproducibility with fixed paths"""
        # This tests the scenario where different host paths mount to /repo
        # for build reproducibility (config has project_mount = "/repo")

        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        assert ":/repo:z" in result.stdout  # Mounts to /repo regardless of host path
        assert "--workdir=/repo/src" in result.stdout  # Working dir translated

        # Verify that paths inside container are predictable
        assert "Working directory: /repo/src" in result.stderr

    def test_multi_project_scenario(self, workspace_without_config):
        """Test Use Case 3: Multiple small projects without .ctenv.toml"""
        # Create structure: projects/web-scraper/
        projects_dir = workspace_without_config / "projects"
        web_scraper_dir = projects_dir / "web-scraper"
        web_scraper_dir.mkdir(parents=True)

        result = run_ctenv(
            workspace_without_config,
            [
                "--workspace",
                str(projects_dir),
                "--workdir",
                str(web_scraper_dir),
                "--",
                "pwd",
            ],
            cwd=web_scraper_dir,
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        assert ":z" in result.stdout and "projects" in result.stdout
        assert "--workdir=" in result.stdout and "web-scraper" in result.stdout
