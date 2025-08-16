"""Container image building for ctenv.

This module handles image building functionality including:
- BuildImageSpec dataclass for resolved build configuration
- Image building logic and execution
- Build configuration parsing and validation
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Dict

from .config import (
    NOTSET,
    ContainerConfig,
    RuntimeContext,
    _substitute_variables_in_container_config,
)


@dataclass(kw_only=True)
class BuildImageSpec:
    """Resolved build specification ready for image building."""

    dockerfile: str
    context: str
    tag: str
    args: Dict[str, str]
    platform: Optional[str] = None


def parse_build_spec(config: ContainerConfig, runtime: RuntimeContext) -> BuildImageSpec:
    """Parse BuildImageSpec from ContainerConfig.

    Args:
        config: Container configuration with build settings
        runtime: Runtime context for variable substitution

    Returns:
        BuildImageSpec ready for image building

    Raises:
        ValueError: If build configuration is missing or invalid
    """
    if config.build is NOTSET:
        raise ValueError("No build configuration found")

    # Apply variable substitution
    substituted_config = _substitute_variables_in_container_config(config, runtime, os.environ)

    build_config = substituted_config.build

    # Validate required fields are present
    if build_config.dockerfile is NOTSET:
        raise ValueError("Missing required build field: dockerfile")
    if build_config.context is NOTSET:
        raise ValueError("Missing required build field: context")
    if build_config.tag is NOTSET:
        raise ValueError("Missing required build field: tag")

    # Get platform from container config if available
    platform = None
    if substituted_config.platform is not NOTSET:
        platform = substituted_config.platform

    return BuildImageSpec(
        dockerfile=build_config.dockerfile,
        context=build_config.context,
        tag=build_config.tag,
        args=build_config.args if build_config.args is not NOTSET else {},
        platform=platform,
    )


def build_container_image(
    build_spec: BuildImageSpec, runtime: RuntimeContext, verbose: bool = False
) -> str:
    """Build container image and return the image tag.

    Args:
        build_spec: Resolved build specification
        runtime: Runtime context (used for working directory)
        verbose: Enable verbose output

    Returns:
        Image tag of the built image

    Raises:
        RuntimeError: If build fails
    """
    # Determine container runtime (docker or podman)
    container_runtime = os.environ.get("RUNNER", "docker")

    # Build the docker build command
    build_cmd = [container_runtime, "build"]

    # Add dockerfile
    build_cmd.extend(["-f", build_spec.dockerfile])

    # Add platform if specified
    if build_spec.platform:
        build_cmd.extend(["--platform", build_spec.platform])

    # Add build arguments
    if build_spec.args:
        for key, value in build_spec.args.items():
            build_cmd.extend(["--build-arg", f"{key}={value}"])

    # Add tag
    build_cmd.extend(["-t", build_spec.tag])

    # Add context (this should be last)
    build_cmd.append(build_spec.context)

    if verbose:
        print(f"[ctenv] Building image: {' '.join(build_cmd)}", file=sys.stderr)

    # Execute build
    try:
        result = subprocess.run(
            build_cmd, cwd=runtime.project_dir, capture_output=not verbose, text=True, check=True
        )

        if verbose and result.stdout:
            print(result.stdout, file=sys.stderr)

        return build_spec.tag

    except subprocess.CalledProcessError as e:
        error_msg = f"Image build failed with exit code {e.returncode}"
        if e.stderr:
            error_msg += f": {e.stderr}"
        raise RuntimeError(error_msg) from e
    except FileNotFoundError:
        raise RuntimeError(
            f"Container runtime '{container_runtime}' not found. Please install Docker or Podman."
        ) from None
