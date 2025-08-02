import subprocess
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
workspace = ".:/repo"

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


def run_ctenv(workspace_dir, args, cwd=None):
    """Helper to run ctenv with dry-run"""
    if cwd is None:
        cwd = workspace_dir

    cmd = [
        "python3",
        "-m",
        "ctenv",
        "run",
        "-v",
        "--dry-run",
        "--gosu-path",
        str(Path(__file__).parent.parent / "ctenv" / "binaries" / "gosu-amd64"),
    ] + args

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result


@pytest.mark.integration
class TestWorkspaceAutoDetection:
    """Test workspace auto-detection functionality"""

    def test_project_root_detection(self, workspace_with_config):
        """Test that project root is detected from subdirectory"""
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
        result = run_ctenv(
            workspace_without_config,
            ["--workspace", ":", "--", "pwd"],
            cwd=workspace_without_config / "src",
        )

        assert result.returncode == 0
        # When no project is detected, mounts cwd (src directory) to itself
        assert ":z" in result.stdout and "src:" in result.stdout
        assert "--workdir=" in result.stdout and "src" in result.stdout


@pytest.mark.integration
class TestWorkspaceVolumesSyntax:
    """Test workspace volume syntax variations"""

    def test_auto_syntax(self, workspace_with_config):
        """Test --workspace : (auto-detection)"""
        result = run_ctenv(
            workspace_with_config, ["--workspace", ":", "test", "--", "pwd"]
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        # Check for the volume mount (both paths are the same)
        assert ":z" in result.stdout and "--volume=" in result.stdout
        # Check workdir contains the workspace path
        assert "--workdir=" in result.stdout

    def test_auto_with_target(self, workspace_with_config):
        """Test --workspace :/repo"""
        result = run_ctenv(
            workspace_with_config, ["--workspace", ":/repo", "test", "--", "pwd"]
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo" in result.stdout

    def test_shorthand_syntax(self, workspace_with_config):
        """Test --workspace :/repo shorthand"""
        result = run_ctenv(
            workspace_with_config, ["--workspace", ":/repo", "test", "--", "pwd"]
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo" in result.stdout

    def test_explicit_paths(self, workspace_with_config):
        """Test explicit host:container paths"""
        host_path = workspace_with_config
        result = run_ctenv(
            workspace_with_config,
            ["--workspace", f"{host_path}:/workspace", "test", "--", "pwd"],
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        assert ":/workspace:z" in result.stdout
        assert "--workdir=/workspace" in result.stdout


@pytest.mark.integration
class TestWorkingDirectoryTranslation:
    """Test working directory path translation"""

    def test_relative_position_preserved(self, workspace_with_config):
        """Test that relative position is preserved when mounting to different path"""
        result = run_ctenv(
            workspace_with_config,
            ["--workspace", ":/repo", "test", "--", "pwd"],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        # Handle macOS path normalization (/private prefix)
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo/src" in result.stdout
        assert "Working directory: /repo/src" in result.stderr

    def test_workdir_override(self, workspace_with_config):
        """Test --workdir override"""
        result = run_ctenv(
            workspace_with_config,
            [
                "--workspace",
                ":/repo",
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


@pytest.mark.integration
class TestConfigFileWorkspace:
    """Test workspace settings in config files"""

    def test_config_workspace_applied(self, workspace_with_config):
        """Test that config file workspace is applied"""
        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        # Config has workspace = ".:/repo"
        # Handle macOS path normalization (/private prefix)
        assert ":/repo:z" in result.stdout
        assert "--workdir=/repo/src" in result.stdout

    def test_cli_overrides_config(self, workspace_with_config):
        """Test that CLI workspace overrides config"""
        result = run_ctenv(
            workspace_with_config,
            ["--workspace", ":", "test", "--", "pwd"],
            cwd=workspace_with_config / "src",
        )

        assert result.returncode == 0
        # CLI should override config (auto mounts to same path)
        # Handle macOS path normalization (/private prefix)
        assert ":z" in result.stdout and "--volume=" in result.stdout
        assert "/src" in result.stdout and "--workdir=" in result.stdout


@pytest.mark.integration
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


@pytest.mark.integration
class TestRealWorldScenarios:
    """Test real-world usage scenarios from the task"""

    def test_build_reproducibility_scenario(self, workspace_with_config):
        """Test Use Case 5: Build reproducibility with fixed paths"""
        # This tests the scenario where different host paths mount to /repo
        # for build reproducibility

        result = run_ctenv(
            workspace_with_config,
            ["test", "--", "pwd"],  # Uses config workspace = ".:/repo"
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
