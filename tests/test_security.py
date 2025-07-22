"""Security tests for ctenv."""

import pytest
from pathlib import Path
import tempfile

from ctenv.cli import build_entrypoint_script, ContainerConfig, ContainerRunner


@pytest.mark.unit  
def test_post_start_commands_shell_functionality():
    """Test that post_start_commands support full shell functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=Path(tmpdir),
            command="bash",
            # Malicious commands with various injection attempts
            post_start_commands=[
                "echo 'hello'; touch /tmp/injected; echo 'done'",  # Semicolon injection
                "echo test && touch /tmp/injected2",  # AND operator injection
                "echo test || touch /tmp/injected3",  # OR operator injection
                "echo test | tee /tmp/output",  # Pipe injection
                "echo $(whoami)",  # Command substitution
                "echo $HOME",  # Variable expansion
                'echo "test" > /tmp/file',  # Redirect injection
            ],
        )

        script = build_entrypoint_script(config)

        # Commands should execute normally with shell interpretation
        assert "echo 'hello'; touch /tmp/injected; echo 'done'" in script
        assert "echo test && touch /tmp/injected2" in script
        assert "echo test || touch /tmp/injected3" in script
        assert "echo test | tee /tmp/output" in script
        assert "echo $(whoami)" in script
        assert "echo $HOME" in script
        assert 'echo "test" > /tmp/file' in script


@pytest.mark.unit
def test_volume_chown_path_injection_prevention():
    """Test that chown paths are properly escaped to prevent command injection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=Path(tmpdir),
            command="bash",
        )

        # Malicious paths with injection attempts
        malicious_paths = [
            '/tmp"; touch /tmp/pwned; echo "done',  # Quote injection
            '/tmp$(whoami)',  # Command substitution
            '/tmp && touch /tmp/injected',  # AND operator
            '/tmp; touch /tmp/injected2',  # Semicolon injection
            '/tmp | tee /tmp/output',  # Pipe injection
            '/tmp > /tmp/redirect',  # Redirect injection
        ]

        script = build_entrypoint_script(config, malicious_paths)

        # Paths should be safely quoted to prevent command injection
        assert "chown -R \"$USER_ID:$GROUP_ID\" '/tmp\"; touch /tmp/pwned; echo \"done'" in script
        assert "chown -R \"$USER_ID:$GROUP_ID\" '/tmp$(whoami)'" in script
        assert "chown -R \"$USER_ID:$GROUP_ID\" '/tmp && touch /tmp/injected'" in script
        
        # Malicious commands should not execute
        assert 'touch /tmp/pwned\n' not in script
        assert 'touch /tmp/injected\n' not in script


@pytest.mark.unit 
def test_complex_shell_scenarios():
    """Test complex shell scenarios work correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup", 
            group_id=1000,
            user_home="/home/testuser",
            working_dir=Path(tmpdir),
            command="bash",
            post_start_commands=[
                # Nested quotes and substitutions
                'echo "$(echo \'$(whoami)\')"',
                # Backticks (old-style command substitution)
                'echo `date`',
                # Multiple redirects
                'echo test > /tmp/out 2>&1',
                # Background execution attempt
                'sleep 60 &',
                # Null byte injection attempt (though Python strings can't contain null bytes)
                'echo test\x00malicious',
            ],
        )

        script = build_entrypoint_script(config)

        # All commands should execute normally with shell interpretation
        assert 'echo "$(echo' in script
        assert 'echo `date`' in script  
        assert 'sleep 60 &' in script


@pytest.mark.unit
def test_safe_commands_work_normally():
    """Test that legitimate commands work with normal shell interpretation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = ContainerConfig(
            user_name="testuser",
            user_id=1000,
            group_name="testgroup",
            group_id=1000,
            user_home="/home/testuser",
            working_dir=Path(tmpdir),
            command="bash",
            post_start_commands=[
                "npm install",
                "npm test",
                "python setup.py install",
                "/usr/local/bin/my-app --config /etc/app.conf",
            ],
        )

        script = build_entrypoint_script(config)

        # Commands should be present (unquoted for normal execution)
        assert "npm install" in script
        assert "npm test" in script  
        assert "python setup.py install" in script
        assert "/usr/local/bin/my-app --config /etc/app.conf" in script


@pytest.mark.unit
def test_parse_volumes_with_malicious_paths():
    """Test that volume parsing handles malicious paths safely."""
    # Test various malicious volume specifications
    test_cases = [
        # (volume_spec, should_raise)
        ('/host:/container"; rm -rf /', False),  # Should parse but path will be escaped later
        ('/host:/container:rw,chown"; rm -rf /', False),  # Should parse
        ('/host:/container:ro', False),  # Normal case
    ]

    for volume_spec, should_raise in test_cases:
        if should_raise:
            with pytest.raises(ValueError):
                ContainerRunner.parse_volumes([volume_spec])
        else:
            # Should parse without error
            processed, chown_paths = ContainerRunner.parse_volumes([volume_spec])
            assert len(processed) == 1