"""Tests for user identity preservation in containers.

These tests verify that ctenv correctly creates a user inside the container
with the same UID/GID as the host user.

Each test shows a real ctenv command line that can be used as documentation.
"""

import os

import pytest

from .framework import (
    assert_user,
    assert_file,
    assert_env,
    run_ctenv,
    start_ctenv,
    wait_for_container,
)


class TestUserIdentityPreservation:
    """Test that ctenv preserves host user identity in containers."""

    def test_uid_gid_matches_host(
        self, docker_available, test_images, temp_workspace, cleanup_registry
    ):
        """Container user should have same UID/GID as host user.

        Use case: Running build tools in container without file permission issues.
        """
        process = start_ctenv("ctenv run -- sleep infinity", cwd=temp_workspace)

        try:
            container = wait_for_container(timeout=15)
            cleanup_registry.register(container)

            assert_user(container).matches_host_user()

        finally:
            process.terminate()
            process.wait()

    def test_username_created_in_container(
        self, docker_available, test_images, temp_workspace, cleanup_registry
    ):
        """User with matching name should be created in container.

        Use case: Tools that check username (git, etc.) work correctly.
        """
        process = start_ctenv("ctenv run -- sleep infinity", cwd=temp_workspace)

        try:
            container = wait_for_container(timeout=15)
            cleanup_registry.register(container)

            expected_username = os.environ.get("USER", os.getlogin())
            assert_user(container).has_username(expected_username)

        finally:
            process.terminate()
            process.wait()

    def test_home_directory_exists(
        self, docker_available, test_images, temp_workspace, cleanup_registry
    ):
        """Home directory should exist in container.

        Use case: Tools that need $HOME (npm, pip, etc.) work correctly.
        """
        process = start_ctenv("ctenv run -- sleep infinity", cwd=temp_workspace)

        try:
            container = wait_for_container(timeout=15)
            cleanup_registry.register(container)

            user_info = container.get_user_info()
            uid = user_info["uid"]

            env = container.get_env_via_exec(user=str(uid))
            assert "HOME" in env, "HOME environment variable not set for user"
            container_home = env["HOME"]

            assert_file(container, container_home).exists()

        finally:
            process.terminate()
            process.wait()


class TestFileOwnership:
    """Test that files created in container have correct ownership on host."""

    def test_file_created_with_host_uid(
        self, docker_available, test_images, temp_workspace, cleanup_registry
    ):
        """Files created in container should be owned by host user.

        Use case: Build artifacts have correct ownership, no need for chown.
        """
        result = run_ctenv("ctenv run -- touch created_by_container.txt", cwd=temp_workspace)

        assert result.returncode == 0, f"ctenv failed: {result.stderr}"

        host_file = temp_workspace / "created_by_container.txt"
        assert host_file.exists(), "File was not created"

        stat_info = host_file.stat()
        expected_uid = os.getuid()

        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            assert stat_info.st_uid in (0, expected_uid), (
                f"File UID {stat_info.st_uid} not in expected range [0, {expected_uid}]"
            )
        else:
            assert stat_info.st_uid == expected_uid, (
                f"File owned by UID {stat_info.st_uid}, expected {expected_uid}"
            )

    def test_file_with_content_has_correct_ownership(
        self, docker_available, test_images, temp_workspace, cleanup_registry
    ):
        """Files with content should have correct ownership.

        Use case: Writing build output, config files, etc.
        """
        result = run_ctenv(
            'ctenv run -- sh -c "echo test_content > output.txt"',
            cwd=temp_workspace,
        )

        assert result.returncode == 0, f"ctenv failed: {result.stderr}"

        host_file = temp_workspace / "output.txt"
        assert host_file.exists()
        assert "test_content" in host_file.read_text()

        stat_info = host_file.stat()
        if not (os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")):
            assert stat_info.st_uid == os.getuid()


class TestEnvironmentSetup:
    """Test environment variable handling in containers."""

    def test_custom_env_passed_to_container(
        self, docker_available, test_images, temp_workspace, cleanup_registry
    ):
        """Custom environment variables should be available in container.

        Use case: Passing build configuration, API keys, etc.
        """
        process = start_ctenv(
            "ctenv run --env MY_VAR=my_value --env DEBUG=1 -- sleep infinity",
            cwd=temp_workspace,
        )

        try:
            container = wait_for_container(timeout=15)
            cleanup_registry.register(container)

            assert_env(container).has_var("MY_VAR", "my_value")
            assert_env(container).has_var("DEBUG", "1")

        finally:
            process.terminate()
            process.wait()

    def test_env_from_host_passed_through(
        self, docker_available, test_images, temp_workspace, cleanup_registry
    ):
        """Environment variables from host should be passable.

        Use case: Passing through existing env vars like PATH additions.
        """
        env = os.environ.copy()
        env["CUSTOM_VAR"] = "passed_from_host"

        result = run_ctenv(
            "ctenv run --env CUSTOM_VAR -- printenv CUSTOM_VAR",
            cwd=temp_workspace,
            env=env,
        )

        assert result.returncode == 0, f"ctenv failed: {result.stderr}"
        assert "passed_from_host" in result.stdout
