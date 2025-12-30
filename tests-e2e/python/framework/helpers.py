"""Helper functions for running ctenv commands in tests.

These helpers make tests more readable by accepting string command lines
instead of arrays. Test containers are labeled with se.osd.ctenv.test=true
so they can be cleaned up without affecting real ctenv containers.
"""

import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Label added to test containers to distinguish from real usage
TEST_LABEL = "se.osd.ctenv.test=true"


def _build_args(cmd: str) -> list[str]:
    """Build command args, adding test label for 'run' commands."""
    if cmd.startswith("ctenv "):
        cmd = cmd[6:]

    args = [sys.executable, "-m", "ctenv"]

    # Insert test label for run commands
    parts = shlex.split(cmd)
    if parts and parts[0] == "run":
        # Use --run-arg=VALUE syntax to prevent argparse from treating --label as an option
        args.append("run")
        args.append(f"--run-arg=--label={TEST_LABEL}")
        args.extend(parts[1:])
    else:
        args.extend(parts)

    return args


def run_ctenv(
    cmd: str,
    cwd: Path,
    env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Run a ctenv command and wait for completion.

    Args:
        cmd: Command string like "ctenv run -- touch file.txt"
        cwd: Working directory
        env: Optional environment variables

    Returns:
        CompletedProcess with stdout/stderr

    Example:
        result = run_ctenv("ctenv run -- whoami", cwd=workspace)
        assert result.returncode == 0
    """
    return subprocess.run(
        _build_args(cmd),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def start_ctenv(
    cmd: str,
    cwd: Path,
    env: Optional[dict] = None,
) -> subprocess.Popen:
    """Start a ctenv command in the background.

    Args:
        cmd: Command string like "ctenv run -- sleep infinity"
        cwd: Working directory
        env: Optional environment variables

    Returns:
        Popen process (caller must terminate)

    Example:
        process = start_ctenv("ctenv run -- sleep infinity", cwd=workspace)
        try:
            container = wait_for_container()
            # ... inspect container ...
        finally:
            process.terminate()
            process.wait()
    """
    return subprocess.Popen(
        _build_args(cmd),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
