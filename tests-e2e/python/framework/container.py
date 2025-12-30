"""Container lifecycle management for integration tests.

This module provides ContainerHandle for introspecting running containers
and CleanupRegistry for ensuring cleanup even on test failure.

The framework does NOT abstract ctenv invocation - tests should call ctenv
directly with real command lines to serve as documentation of real use cases.
"""

from __future__ import annotations

import atexit
import json
import signal
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ExecResult:
    """Result from executing a command inside a container."""

    returncode: int
    stdout: str
    stderr: str
    command: list[str]

    @property
    def success(self) -> bool:
        return self.returncode == 0

    def check(self) -> ExecResult:
        """Raise if command failed."""
        if not self.success:
            raise RuntimeError(
                f"Command {self.command} failed with code {self.returncode}:\n"
                f"stdout: {self.stdout}\nstderr: {self.stderr}"
            )
        return self


class CleanupRegistry:
    """Registry to ensure container cleanup even on test failure or interruption.

    Uses multiple cleanup mechanisms:
    1. Context manager (with statement)
    2. atexit handler
    3. Signal handlers (SIGINT, SIGTERM)
    4. Pytest fixture finalizers
    """

    _global_instance: Optional[CleanupRegistry] = None

    def __init__(self) -> None:
        self._containers: set[ContainerHandle] = set()
        self._cleaned_up = False
        self._original_sigint: Any = None
        self._original_sigterm: Any = None

        # Register cleanup on process exit
        atexit.register(self._cleanup_all)

        # Register signal handlers for graceful cleanup on Ctrl+C
        self._original_sigint = signal.signal(signal.SIGINT, self._signal_handler)
        self._original_sigterm = signal.signal(signal.SIGTERM, self._signal_handler)

    @classmethod
    def get_global(cls) -> CleanupRegistry:
        """Get or create the global cleanup registry."""
        if cls._global_instance is None:
            cls._global_instance = cls()
        return cls._global_instance

    def register(self, container: ContainerHandle) -> None:
        """Register a container for cleanup."""
        self._containers.add(container)

    def unregister(self, container: ContainerHandle) -> None:
        """Unregister a container (already cleaned up manually)."""
        self._containers.discard(container)

    def _cleanup_all(self) -> None:
        """Clean up all registered containers."""
        if self._cleaned_up:
            return

        self._cleaned_up = True
        errors = []

        for container in list(self._containers):
            try:
                container.cleanup()
            except Exception as e:
                errors.append(f"{container.container_id}: {e}")

        self._containers.clear()

        if errors:
            import warnings

            warnings.warn(f"Cleanup errors: {errors}")

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle signals by cleaning up containers first."""
        self._cleanup_all()

        # Re-raise with original handler
        if signum == signal.SIGINT and self._original_sigint:
            signal.signal(signal.SIGINT, self._original_sigint)
            raise KeyboardInterrupt
        elif signum == signal.SIGTERM and self._original_sigterm:
            signal.signal(signal.SIGTERM, self._original_sigterm)
            raise SystemExit(128 + signum)

    def __enter__(self) -> CleanupRegistry:
        return self

    def __exit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any
    ) -> bool:
        self._cleanup_all()
        return False  # Don't suppress exceptions


def find_container(
    label_filter: str = "se.osd.ctenv.managed=true",
) -> Optional[ContainerHandle]:
    """Find the most recently started container matching the filter.

    Args:
        label_filter: Docker label filter (default: ctenv managed containers)

    Returns:
        ContainerHandle for the container, or None if not found
    """
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label={label_filter}",
            "--format",
            "{{.ID}}\t{{.Names}}\t{{.Image}}",
            "--latest",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    parts = result.stdout.strip().split("\t")
    if len(parts) < 3:
        return None

    container_id, container_name, image = parts[0], parts[1], parts[2]

    return ContainerHandle(
        container_id=container_id,
        container_name=container_name,
        image=image,
    )


def wait_for_container(
    timeout: float = 10.0,
    poll_interval: float = 0.5,
    label_filter: str = "se.osd.ctenv.managed=true",
) -> ContainerHandle:
    """Wait for a container to appear and return a handle to it.

    Args:
        timeout: Maximum time to wait in seconds
        poll_interval: Time between checks in seconds
        label_filter: Docker label filter

    Returns:
        ContainerHandle for the container

    Raises:
        TimeoutError: If no container appears within timeout
    """
    import time

    start = time.time()
    while time.time() - start < timeout:
        container = find_container(label_filter)
        if container is not None:
            return container
        time.sleep(poll_interval)

    raise TimeoutError(f"No container found within {timeout}s")


@dataclass
class ContainerHandle:
    """Handle to a running container for introspection.

    This class provides a high-level interface for:
    - Executing commands inside the container
    - Inspecting container metadata
    - Querying container state (user, files, env vars)
    - Cleanup

    Use find_container() or wait_for_container() to get a handle.
    Tests should start containers using explicit ctenv commands.
    """

    container_id: str
    container_name: str
    image: str
    _cleanup_registry: Optional[CleanupRegistry] = field(default=None, repr=False)

    def __hash__(self) -> int:
        return hash(self.container_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ContainerHandle):
            return False
        return self.container_id == other.container_id

    # --- Execution Methods ---

    def exec(
        self,
        command: list[str],
        user: Optional[str] = None,
        workdir: Optional[str] = None,
        check: bool = False,
    ) -> ExecResult:
        """Execute a command inside the container."""
        docker_cmd = ["docker", "exec"]

        if user:
            docker_cmd.extend(["--user", user])
        if workdir:
            docker_cmd.extend(["--workdir", workdir])

        docker_cmd.append(self.container_id)
        docker_cmd.extend(command)

        result = subprocess.run(docker_cmd, capture_output=True, text=True)

        exec_result = ExecResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            command=command,
        )

        if check:
            exec_result.check()

        return exec_result

    def exec_sh(self, script: str, user: Optional[str] = None) -> ExecResult:
        """Execute a shell script inside the container."""
        return self.exec(["sh", "-c", script], user=user)

    # --- Inspection Methods ---

    def inspect(self) -> dict[str, Any]:
        """Get full docker inspect output as dict."""
        result = subprocess.run(
            ["docker", "inspect", self.container_id],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker inspect failed: {result.stderr}")
        return json.loads(result.stdout)[0]

    def get_env(self) -> dict[str, str]:
        """Get environment variables configured for the container.

        Uses docker inspect to get the container's environment,
        which reflects what ctenv configured.
        """
        info = self.inspect()
        env_list = info.get("Config", {}).get("Env", [])
        env = {}
        for item in env_list:
            if "=" in item:
                key, value = item.split("=", 1)
                env[key] = value
        return env

    def get_env_via_exec(self, user: Optional[str] = None) -> dict[str, str]:
        """Get environment variables by running env inside container.

        Args:
            user: Optional user to run as (e.g., "1000" or "username")
        """
        result = self.exec(["env"], user=user, check=True)
        env = {}
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                key, value = line.split("=", 1)
                env[key] = value
        return env

    def get_user_info(self) -> dict[str, Any]:
        """Get user information for the main process in the container.

        Uses docker top to check what user the main process is running as,
        which is the correct way to verify ctenv's user identity setup.
        """
        # Use docker top to get the main process's user and PID
        result = subprocess.run(
            ["docker", "top", self.container_id, "-o", "user,pid,comm"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker top failed: {result.stderr}")

        # Parse output - skip header, find main process (e.g., sleep)
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            raise RuntimeError(f"Unexpected docker top output: {result.stdout}")

        # Look for a non-root process or the main command
        # Format: USER PID COMMAND
        target_user = None
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 3:
                user, _pid, comm = parts[0], parts[1], parts[2]
                # Return info for non-root user or the main command
                if user != "root" or comm in ("sleep", "bash", "sh"):
                    target_user = user
                    break

        if target_user is None:
            # Fallback to first process after header
            parts = lines[1].split()
            target_user = parts[0] if parts else "root"

        # Get UID/GID by running id command as that user
        # First, try to get the numeric UID from the user
        id_result = self.exec(["id", target_user])
        if id_result.success:
            # Parse output like: uid=501(oskar) gid=20(staff) groups=...
            import re
            uid_match = re.search(r"uid=(\d+)\(([^)]+)\)", id_result.stdout)
            gid_match = re.search(r"gid=(\d+)", id_result.stdout)

            if uid_match:
                uid = int(uid_match.group(1))
                username = uid_match.group(2)  # Get username from parentheses
            else:
                # Fallback: try simpler pattern
                simple_uid = re.search(r"uid=(\d+)", id_result.stdout)
                uid = int(simple_uid.group(1)) if simple_uid else -1
                username = target_user

            return {
                "user": username,
                "uid": uid,
                "gid": int(gid_match.group(1)) if gid_match else -1,
            }

        return {
            "user": target_user,
            "uid": -1,
            "gid": -1,
        }

    def get_exec_user_info(self) -> dict[str, Any]:
        """Get user info via docker exec (runs as container's default user).

        Note: This typically returns root unless the container was started
        with a specific user. Use get_user_info() to check the main process.
        """
        result = self.exec_sh(
            'echo "uid=$(id -u) gid=$(id -g) user=$(whoami)"'
        ).check()

        # Parse output like: uid=1000 gid=1000 user=oskar
        info: dict[str, Any] = {}
        for part in result.stdout.strip().split():
            key, value = part.split("=", 1)
            if key in ("uid", "gid"):
                info[key] = int(value)
            else:
                info[key] = value
        return info

    def file_exists(self, path: str) -> bool:
        """Check if a file exists in the container."""
        result = self.exec(["test", "-e", path])
        return result.success

    def read_file(self, path: str) -> str:
        """Read file contents from container."""
        return self.exec(["cat", path], check=True).stdout

    def get_file_owner(self, path: str) -> dict[str, int]:
        """Get UID/GID of a file in the container."""
        result = self.exec_sh(f'stat -c "%u %g" "{path}"').check()
        uid, gid = result.stdout.strip().split()
        return {"uid": int(uid), "gid": int(gid)}

    def get_mounts(self) -> list[dict[str, Any]]:
        """Get container mount points from inspect."""
        info = self.inspect()
        return info.get("Mounts", [])

    def get_labels(self) -> dict[str, str]:
        """Get container labels."""
        info = self.inspect()
        return info.get("Config", {}).get("Labels", {})

    # --- Lifecycle Methods ---

    def stop(self, timeout: int = 10) -> None:
        """Stop the container."""
        subprocess.run(
            ["docker", "stop", "-t", str(timeout), self.container_id],
            capture_output=True,
        )

    def remove(self, force: bool = True) -> None:
        """Remove the container."""
        cmd = ["docker", "rm"]
        if force:
            cmd.append("-f")
        cmd.append(self.container_id)
        subprocess.run(cmd, capture_output=True)

    def cleanup(self) -> None:
        """Stop and remove the container."""
        self.stop(timeout=1)
        self.remove(force=True)
        if self._cleanup_registry:
            self._cleanup_registry.unregister(self)

    def is_running(self) -> bool:
        """Check if container is still running."""
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                self.container_id,
            ],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip().lower() == "true"

    def logs(self) -> str:
        """Get container logs."""
        result = subprocess.run(
            ["docker", "logs", self.container_id],
            capture_output=True,
            text=True,
        )
        return result.stdout + result.stderr
