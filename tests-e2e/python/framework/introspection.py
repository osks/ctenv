"""Fluent assertion helpers for container introspection.

These helpers provide a readable way to assert container state:

    assert_user(container).matches_host_user()
    assert_file(container, "/repo/test.txt").exists().owned_by(os.getuid())
    assert_env(container).has_var("MY_VAR", "value")
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import ContainerHandle


@dataclass
class UserAssertion:
    """Helper for user identity assertions."""

    container: ContainerHandle

    def has_uid(self, expected_uid: int) -> UserAssertion:
        """Assert the container user has the expected UID."""
        info = self.container.get_user_info()
        assert info["uid"] == expected_uid, (
            f"Expected UID {expected_uid}, got {info['uid']}"
        )
        return self

    def has_gid(self, expected_gid: int) -> UserAssertion:
        """Assert the container user has the expected GID."""
        info = self.container.get_user_info()
        assert info["gid"] == expected_gid, (
            f"Expected GID {expected_gid}, got {info['gid']}"
        )
        return self

    def matches_host_user(self) -> UserAssertion:
        """Assert container user matches host user."""
        return self.has_uid(os.getuid()).has_gid(os.getgid())

    def has_username(self, expected: str) -> UserAssertion:
        """Assert the container username."""
        info = self.container.get_user_info()
        assert info["user"] == expected, (
            f"Expected username {expected}, got {info['user']}"
        )
        return self


@dataclass
class FileAssertion:
    """Helper for file-related assertions."""

    container: ContainerHandle
    path: str

    def exists(self) -> FileAssertion:
        """Assert file exists."""
        assert self.container.file_exists(self.path), (
            f"File {self.path} does not exist in container"
        )
        return self

    def not_exists(self) -> FileAssertion:
        """Assert file does not exist."""
        assert not self.container.file_exists(self.path), (
            f"File {self.path} unexpectedly exists in container"
        )
        return self

    def contains(self, expected: str) -> FileAssertion:
        """Assert file contains text."""
        content = self.container.read_file(self.path)
        assert expected in content, (
            f"File {self.path} does not contain '{expected}'"
        )
        return self

    def owned_by(self, uid: int, gid: Optional[int] = None) -> FileAssertion:
        """Assert file ownership."""
        owner = self.container.get_file_owner(self.path)
        assert owner["uid"] == uid, (
            f"File {self.path} owned by UID {owner['uid']}, expected {uid}"
        )
        if gid is not None:
            assert owner["gid"] == gid, (
                f"File {self.path} has GID {owner['gid']}, expected {gid}"
            )
        return self


@dataclass
class EnvironmentAssertion:
    """Helper for environment variable assertions."""

    container: ContainerHandle

    def has_var(self, name: str, value: Optional[str] = None) -> EnvironmentAssertion:
        """Assert environment variable exists (and optionally has value)."""
        env = self.container.get_env()
        assert name in env, f"Environment variable {name} not set"
        if value is not None:
            assert env[name] == value, (
                f"Env {name}={env[name]}, expected {value}"
            )
        return self

    def missing_var(self, name: str) -> EnvironmentAssertion:
        """Assert environment variable is not set."""
        env = self.container.get_env()
        assert name not in env, (
            f"Environment variable {name} unexpectedly set to {env.get(name)}"
        )
        return self


@dataclass
class MountAssertion:
    """Helper for mount/volume assertions."""

    container: ContainerHandle

    def has_mount_at(self, container_path: str) -> MountAssertion:
        """Assert a volume is mounted at the given path."""
        mounts = self.container.get_mounts()
        destinations = [m.get("Destination") for m in mounts]
        assert container_path in destinations, (
            f"No mount at {container_path}. Mounts: {destinations}"
        )
        return self

    def has_mount_from(self, host_path: str, container_path: str) -> MountAssertion:
        """Assert a specific host path is mounted at container path."""
        mounts = self.container.get_mounts()
        for mount in mounts:
            if mount.get("Destination") == container_path:
                assert mount.get("Source") == host_path, (
                    f"Mount at {container_path} from {mount.get('Source')}, "
                    f"expected {host_path}"
                )
                return self
        raise AssertionError(f"No mount at {container_path}")


def assert_user(container: ContainerHandle) -> UserAssertion:
    """Start a fluent user assertion chain."""
    return UserAssertion(container)


def assert_file(container: ContainerHandle, path: str) -> FileAssertion:
    """Start a fluent file assertion chain."""
    return FileAssertion(container, path)


def assert_env(container: ContainerHandle) -> EnvironmentAssertion:
    """Start a fluent environment assertion chain."""
    return EnvironmentAssertion(container)


def assert_mounts(container: ContainerHandle) -> MountAssertion:
    """Start a fluent mount assertion chain."""
    return MountAssertion(container)
