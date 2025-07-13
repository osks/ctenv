---
id: task-7
title: Implement comprehensive testing strategy for ctenv MVP
status: Done
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-13'
labels: []
dependencies:
  - task-1
  - task-2
  - task-3
  - task-4
  - task-5
---

## Description

Implement a multi-layered testing strategy to ensure ctenv MVP works correctly across different scenarios and environments.

## Tasks

### Unit Tests
- [ ] Create `tests/test_config.py`:
```python
import os
import pwd
import pytest
from ctenv import Config

def test_config_detects_user_identity():
    config = Config()
    assert config.user_id == os.getuid()
    assert config.user_name == pwd.getpwuid(os.getuid()).pw_name
    assert config.group_id == os.getgid()

def test_container_name_generation():
    config = Config()
    name1 = config.get_container_name("/path/to/project")
    name2 = config.get_container_name("/path/to/project")
    name3 = config.get_container_name("/different/path")
    
    assert name1 == name2  # Consistent naming
    assert name1 != name3  # Different paths produce different names
    assert name1.startswith("ctenv-")

def test_config_defaults():
    config = Config()
    assert "IMAGE" in config.defaults
    assert "GOSU_MOUNT" in config.defaults
    assert config.defaults["DIR_MOUNT"] == "/repo"
```

- [ ] Create `tests/test_container_runner.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
from ctenv import ContainerRunner, Config

@pytest.fixture
def config():
    return Config()

@pytest.fixture
def runner(config):
    return ContainerRunner(config)

def test_build_run_args_contains_required_flags(runner, config):
    test_config = {
        "IMAGE": "ubuntu:latest",
        "COMMAND": "bash",
        "NAME": "test-container",
        "USER_ID": 1000,
        "GROUP_ID": 1000,
    }
    args = runner.build_run_args(test_config)
    
    assert "--rm" in args
    assert "--init" in args
    assert "ubuntu:latest" in args
    assert "--name=test-container" in args

def test_volume_mounts_format(runner, config):
    test_config = {
        "DIR": "/current/dir",
        "DIR_MOUNT": "/repo",
        "GOSU": "/path/to/gosu",
        "GOSU_MOUNT": "/gosu"
    }
    args = runner.build_run_args(test_config)
    
    volume_args = [arg for arg in args if arg.startswith("--volume=")]
    assert any("/current/dir:/repo" in arg for arg in volume_args)
    assert any("/path/to/gosu:/gosu" in arg for arg in volume_args)

@patch('subprocess.run')
def test_run_container_calls_docker(mock_run, runner):
    mock_run.return_value.returncode = 0
    config = {"IMAGE": "ubuntu", "COMMAND": "echo test"}
    
    runner.run_container(config)
    
    mock_run.assert_called_once()
    called_args = mock_run.call_args[0][0]
    assert called_args[0] == "docker"
    assert "run" in called_args
```

- [ ] Create `tests/test_entrypoint.py`:
```python
import pytest
from ctenv import build_entrypoint_script

def test_entrypoint_script_contains_user_setup():
    config = {
        "USER_NAME": "testuser",
        "USER_ID": 1000,
        "GROUP_NAME": "testgroup", 
        "GROUP_ID": 1000,
        "USER_HOME": "/home/testuser",
        "COMMAND": "bash"
    }
    script = build_entrypoint_script(config)
    
    assert "useradd" in script
    assert "testuser" in script
    assert "1000" in script
    assert "exec /gosu testuser bash" in script

def test_script_handles_group_creation():
    config = {
        "GROUP_ID": 1001,
        "GROUP_NAME": "newgroup",
        "USER_NAME": "user",
        "USER_ID": 1001,
        "USER_HOME": "/home/user",
        "COMMAND": "bash"
    }
    script = build_entrypoint_script(config)
    
    assert "getent group 1001" in script
    assert "groupadd -g 1001 newgroup" in script

def test_script_sets_home_directory():
    config = {
        "USER_HOME": "/custom/home",
        "USER_ID": 1000,
        "GROUP_ID": 1000,
        "USER_NAME": "user",
        "COMMAND": "bash"
    }
    script = build_entrypoint_script(config)
    
    assert "export HOME=/custom/home" in script
    assert "mkdir -p" in script
    assert "chown 1000:1000" in script
```

- [ ] Create `tests/test_cli.py`:
```python
import pytest
from click.testing import CliRunner
from ctenv import cli

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert "0.1" in result.output

def test_run_command_help():
    runner = CliRunner()
    result = runner.invoke(cli, ['run', '--help'])
    assert result.exit_code == 0
    assert "--image" in result.output
    assert "Run command in container" in result.output

def test_run_command_with_image_option():
    runner = CliRunner()
    with patch('ctenv.ContainerRunner.run_container') as mock_run:
        result = runner.invoke(cli, ['run', '--image', 'ubuntu:latest', '--', 'echo', 'test'])
        assert result.exit_code == 0
        mock_run.assert_called_once()
```

### Integration Tests  
- [ ] Create `tests/test_integration.py`:
```python
import os
import subprocess
import tempfile
import pytest
from pathlib import Path

@pytest.fixture(scope="session")
def test_images():
    """Pull test images before running integration tests"""
    images = ["alpine:latest", "ubuntu:latest"]
    for image in images:
        subprocess.run(["docker", "pull", image], check=True, capture_output=True)
    return images

@pytest.fixture
def temp_dir():
    """Create temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        yield tmpdir
        os.chdir(original_cwd)

@pytest.mark.integration
def test_basic_container_execution(test_images, temp_dir):
    """Test basic container execution with alpine"""
    result = subprocess.run([
        "python", "ctenv.py", "run", 
        "--image", "alpine:latest", 
        "--", "whoami"
    ], capture_output=True, text=True, cwd=temp_dir)
    
    assert result.returncode == 0
    current_username = os.getenv("USER")
    assert current_username in result.stdout

@pytest.mark.integration
def test_working_directory_is_repo(test_images, temp_dir):
    """Test that working directory inside container is /repo"""
    result = subprocess.run([
        "python", "ctenv.py", "run",
        "--image", "alpine:latest",
        "--", "pwd"
    ], capture_output=True, text=True, cwd=temp_dir)
    
    assert result.returncode == 0
    assert "/repo" in result.stdout.strip()

@pytest.mark.integration
def test_file_permission_preservation(test_images, temp_dir):
    """Test that files created in container have correct ownership on host"""
    test_file = "test_permissions.txt"
    
    # Create file in container
    subprocess.run([
        "python", "ctenv.py", "run",
        "--image", "alpine:latest", 
        "--", "touch", f"/repo/{test_file}"
    ], check=True, cwd=temp_dir)
    
    # Check file exists and has correct ownership
    file_path = Path(temp_dir) / test_file
    assert file_path.exists()
    
    stat_info = file_path.stat()
    assert stat_info.st_uid == os.getuid()
    assert stat_info.st_gid == os.getgid()

@pytest.mark.integration  
def test_custom_image_option(test_images, temp_dir):
    """Test using custom image works correctly"""
    result = subprocess.run([
        "python", "ctenv.py", "run",
        "--image", "ubuntu:latest",
        "--", "cat", "/etc/os-release"
    ], capture_output=True, text=True, cwd=temp_dir)
    
    assert result.returncode == 0
    assert "Ubuntu" in result.stdout

@pytest.mark.integration
def test_environment_variables_passed(test_images, temp_dir):
    """Test that user environment is correctly set up"""
    result = subprocess.run([
        "python", "ctenv.py", "run",
        "--image", "alpine:latest",
        "--", "sh", "-c", "echo $HOME && echo $PS1"
    ], capture_output=True, text=True, cwd=temp_dir)
    
    assert result.returncode == 0
    assert os.path.expanduser("~") in result.stdout
    assert "[ctenv]" in result.stdout
```

- [ ] Add test image management and cleanup fixtures to `tests/conftest.py`

### Mock Tests
- [ ] Create `tests/test_mocks.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
import subprocess
from ctenv import ContainerRunner, Config

@patch('subprocess.run')
def test_docker_command_construction(mock_run):
    """Test that Docker commands are constructed correctly"""
    mock_run.return_value.returncode = 0
    
    config = Config()
    runner = ContainerRunner(config)
    
    test_config = {
        "IMAGE": "ubuntu:latest",
        "COMMAND": "echo hello",
        "NAME": "test-container",
        "DIR": "/current/dir",
        "DIR_MOUNT": "/repo",
        "GOSU": "/path/to/gosu",
        "GOSU_MOUNT": "/gosu",
        "USER_NAME": "testuser",
        "USER_ID": 1000,
        "GROUP_ID": 1000,
        "USER_HOME": "/home/testuser"
    }
    
    runner.run_container(test_config)
    
    # Verify subprocess.run was called
    mock_run.assert_called_once()
    called_args = mock_run.call_args[0][0]
    
    # Check command structure
    assert called_args[0] == "docker"
    assert "run" in called_args
    assert "--rm" in called_args
    assert "ubuntu:latest" in called_args

@patch('shutil.which')
@patch('subprocess.run')
def test_docker_not_available(mock_run, mock_which):
    """Test behavior when Docker is not available"""
    mock_which.return_value = None  # Docker not found in PATH
    
    config = Config()
    runner = ContainerRunner(config)
    
    with pytest.raises(FileNotFoundError, match="Docker not found"):
        runner.run_container({"IMAGE": "ubuntu", "COMMAND": "echo test"})

@patch('subprocess.run')
def test_container_failure_handling(mock_run):
    """Test handling of container execution failures"""
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "Container failed to start"
    
    config = Config()
    runner = ContainerRunner(config)
    
    result = runner.run_container({"IMAGE": "invalid:image", "COMMAND": "echo test"})
    assert result.returncode == 1

@patch('subprocess.run')
def test_tty_detection(mock_run):
    """Test TTY flag handling"""
    mock_run.return_value.returncode = 0
    
    config = Config()
    runner = ContainerRunner(config)
    
    # Mock sys.stdin.isatty()
    with patch('sys.stdin.isatty', return_value=True):
        runner.run_container({"IMAGE": "ubuntu", "COMMAND": "bash"})
        
    called_args = mock_run.call_args[0][0]
    assert "-ti" in called_args
```

### Test Infrastructure
- [ ] Create `tests/conftest.py`:
```python
import pytest
import tempfile
import os
import subprocess
from pathlib import Path

@pytest.fixture(scope="session")  
def docker_available():
    """Check if Docker is available for integration tests"""
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available")

@pytest.fixture(scope="session")
def test_images(docker_available):
    """Pull test images once per test session"""
    images = ["alpine:latest", "ubuntu:latest"]
    for image in images:
        try:
            subprocess.run(["docker", "pull", image], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pytest.skip(f"Could not pull test image: {image}")
    return images

@pytest.fixture
def temp_workspace():
    """Create temporary directory and change to it for test isolation"""
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        
        # Create a fake gosu binary for testing
        gosu_path = Path(tmpdir) / "gosu"
        gosu_path.write_text("#!/bin/sh\nexec \"$@\"")
        gosu_path.chmod(0o755)
        
        yield tmpdir
        os.chdir(original_cwd)

@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        "IMAGE": "alpine:latest",
        "DIR": "/test/dir", 
        "DIR_MOUNT": "/repo",
        "GOSU": "/test/gosu",
        "GOSU_MOUNT": "/gosu",
        "USER_NAME": "testuser",
        "USER_ID": 1000,
        "GROUP_NAME": "testgroup", 
        "GROUP_ID": 1000,
        "USER_HOME": "/home/testuser",
        "COMMAND": "bash"
    }

def pytest_configure(config):
    """Configure custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests (fast)")
    config.addinivalue_line("markers", "integration: Integration tests with containers (slow)")
    config.addinivalue_line("markers", "slow: Slow tests requiring external resources")
```

- [ ] Update `pyproject.toml` test dependencies:
```toml
[project.optional-dependencies]
test = [
    "pytest",
    "pytest-mock", 
    "pytest-cov",
    "pytest-xdist",  # for parallel test execution
]
```

- [ ] Create `pytest.ini`:
```ini
[tool:pytest]
markers =
    unit: Unit tests (fast)
    integration: Integration tests with containers (slow) 
    slow: Slow tests requiring external resources

testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Default to unit tests only
addopts = -v -m "not integration and not slow"

# Coverage settings
addopts = --cov=ctenv --cov-report=term-missing --cov-report=html
```

### CI/CD Integration
- [ ] Update `.github/workflows/test.yml`:
  - Install Docker in CI environment
  - Run unit tests on all Python versions
  - Run integration tests on Linux only
  - Add test coverage reporting
- [ ] Add test commands to README:
  - `pytest tests/test_*.py -m unit` (fast unit tests)
  - `pytest tests/test_integration.py -m integration` (slower integration tests)
  - `pytest --cov=ctenv` (coverage report)

### Comparison Testing
- [ ] Create `tests/test_compatibility.py`:
  - Compare Python version output with shell script output
  - Test same commands produce same file permissions
  - Verify container names match between implementations

## Acceptance Criteria

- Unit tests cover all major functions and classes
- Integration tests verify core functionality with real containers
- Tests run successfully in CI environment
- Test coverage > 80% for core functionality
- Clear documentation for running different test suites
- Tests can run both with and without Docker available
- Performance: Unit tests complete in < 10s, integration tests < 60s
