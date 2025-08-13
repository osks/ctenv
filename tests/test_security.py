"""Security tests for ctenv."""

import pytest
import tempfile

from ctenv.config import RuntimeContext, CtenvConfig, ContainerConfig
from ctenv.container import parse_container_config


@pytest.mark.unit
def test_post_start_commands_shell_functionality():
    """Test that post_start_commands support full shell functionality."""
    with tempfile.TemporaryDirectory():
        # Create config dict with post_start_commands containing various shell constructs
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
            "post_start_commands": [
                "echo 'hello'; touch /tmp/injected; echo 'done'",  # Semicolon injection
                "echo test && touch /tmp/injected2",  # AND operator injection
                "echo test || touch /tmp/injected3",  # OR operator injection
                "echo test | tee /tmp/output",  # Pipe injection
                "echo $(whoami)",  # Command substitution
                "echo $HOME",  # Variable expansion
                'echo "test" > /tmp/file',  # Redirect injection
            ],
        }

        # Create runtime context
        import os
        import getpass
        import grp
        from pathlib import Path

        runtime = RuntimeContext(
            user_name=getpass.getuser(),
            user_id=os.getuid(),
            user_home=os.path.expanduser("~"),
            group_name=grp.getgrgid(os.getgid()).gr_name,
            group_id=os.getgid(),
            cwd=Path.cwd(),
            tty=False,
            project_dir=Path.cwd(),
            pid=os.getpid(),
        )

        # Parse config to get ContainerSpec using complete configuration
        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])  # No config files
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        from ctenv.container import build_entrypoint_script

        script = build_entrypoint_script(container_spec, verbose=False, quiet=False)

        # Commands should be stored and executed normally with shell interpretation
        # Check for the key content rather than exact format due to shell escaping
        assert "hello" in script and "touch /tmp/injected" in script and "done" in script
        assert "echo test && touch /tmp/injected2" in script
        assert "echo test || touch /tmp/injected3" in script
        assert "echo test | tee /tmp/output" in script
        assert "echo $(whoami)" in script or "whoami" in script  # May be escaped
        assert "echo $HOME" in script or "$HOME" in script
        assert 'echo "test" > /tmp/file' in script


@pytest.mark.unit
def test_volume_chown_path_injection_prevention():
    """Test that chown paths are properly escaped to prevent command injection."""
    with tempfile.TemporaryDirectory():
        # Create basic config dict
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
        }

        # Create runtime context
        import os
        import getpass
        import grp
        from pathlib import Path

        runtime = RuntimeContext(
            user_name=getpass.getuser(),
            user_id=os.getuid(),
            user_home=os.path.expanduser("~"),
            group_name=grp.getgrgid(os.getgid()).gr_name,
            group_id=os.getgid(),
            cwd=Path.cwd(),
            tty=False,
            project_dir=Path.cwd(),
            pid=os.getpid(),
        )

        # Parse config to get ContainerSpec using complete configuration
        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])  # No config files
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        # Malicious paths with injection attempts
        malicious_paths = [
            '/tmp"; touch /tmp/pwned; echo "done',  # Quote injection
            "/tmp$(whoami)",  # Command substitution
            "/tmp && touch /tmp/injected",  # AND operator
            "/tmp; touch /tmp/injected2",  # Semicolon injection
            "/tmp | tee /tmp/output",  # Pipe injection
            "/tmp > /tmp/redirect",  # Redirect injection
        ]

        # Add malicious paths to the spec
        container_spec.chown_paths = malicious_paths

        from ctenv.container import build_entrypoint_script

        script = build_entrypoint_script(container_spec, verbose=False, quiet=False)

        # Paths should be safely quoted in the CHOWN_PATHS variable to prevent command injection
        # The malicious path should be quoted and null-separated
        assert "CHOWN_PATHS=" in script
        # Should contain the function that safely processes chown paths
        assert "fix_chown_volumes()" in script
        assert 'chown -R "$USER_ID:$GROUP_ID" "$path"' in script

        # Malicious commands should not execute
        assert "touch /tmp/pwned\n" not in script
        assert "touch /tmp/injected\n" not in script


@pytest.mark.unit
def test_complex_shell_scenarios():
    """Test complex shell scenarios work correctly."""
    with tempfile.TemporaryDirectory():
        # Create config dict with complex post_start_commands
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
            "post_start_commands": [
                # Nested quotes and substitutions
                "echo \"$(echo '$(whoami)')\"",
                # Backticks (old-style command substitution)
                "echo `date`",
                # Multiple redirects
                "echo test > /tmp/out 2>&1",
                # Background execution attempt
                "sleep 60 &",
                # Null byte injection attempt (though Python strings can't contain null bytes)
                "echo test\x00malicious",
            ],
        }

        # Create runtime context
        import os
        import getpass
        import grp
        from pathlib import Path

        runtime = RuntimeContext(
            user_name=getpass.getuser(),
            user_id=os.getuid(),
            user_home=os.path.expanduser("~"),
            group_name=grp.getgrgid(os.getgid()).gr_name,
            group_id=os.getgid(),
            cwd=Path.cwd(),
            tty=False,
            project_dir=Path.cwd(),
            pid=os.getpid(),
        )

        # Parse config to get ContainerSpec using complete configuration
        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])  # No config files
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        from ctenv.container import build_entrypoint_script

        script = build_entrypoint_script(container_spec, verbose=False, quiet=False)

        # All commands should execute normally with shell interpretation
        assert 'echo "$(echo' in script
        assert "echo `date`" in script
        assert "sleep 60 &" in script


@pytest.mark.unit
def test_safe_commands_work_normally():
    """Test that legitimate commands work with normal shell interpretation."""
    with tempfile.TemporaryDirectory():
        # Create config dict with safe post_start_commands
        config_dict = {
            "image": "test:latest",
            "command": "bash",
            "workspace": ":",
            "post_start_commands": [
                "npm install",
                "npm test",
                "python setup.py install",
                "/usr/local/bin/my-app --config /etc/app.conf",
            ],
        }

        # Create runtime context
        import os
        import getpass
        import grp
        from pathlib import Path

        runtime = RuntimeContext(
            user_name=getpass.getuser(),
            user_id=os.getuid(),
            user_home=os.path.expanduser("~"),
            group_name=grp.getgrgid(os.getgid()).gr_name,
            group_id=os.getgid(),
            cwd=Path.cwd(),
            tty=False,
            project_dir=Path.cwd(),
            pid=os.getpid(),
        )

        # Parse config to get ContainerSpec using complete configuration
        ctenv_config = CtenvConfig.load(Path.cwd(), explicit_config_files=[])  # No config files
        config = ctenv_config.get_default(overrides=ContainerConfig.from_dict(config_dict))
        container_spec = parse_container_config(config, runtime)

        from ctenv.container import build_entrypoint_script

        script = build_entrypoint_script(container_spec, verbose=False, quiet=False)

        # Commands should be present (unquoted for normal execution)
        assert "npm install" in script
        assert "npm test" in script
        assert "python setup.py install" in script
        assert "/usr/local/bin/my-app --config /etc/app.conf" in script
