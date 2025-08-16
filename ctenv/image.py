"""Container image building for ctenv.

This module handles image building functionality including:
- BuildImageSpec dataclass for resolved build configuration
- Image building logic and execution
- Build configuration parsing and validation
"""

import contextlib
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

from .config import (
    NOTSET,
    ContainerConfig,
    RuntimeContext,
    _substitute_variables_in_container_config,
)


@dataclass(kw_only=True)
class BuildImageSpec:
    """Resolved build specification ready for image building."""

    dockerfile: Optional[str]  # Path to dockerfile, None if using content
    dockerfile_content: Optional[str]  # Inline dockerfile content, None if using path
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
    dockerfile_set = build_config.dockerfile is not NOTSET and build_config.dockerfile is not None
    dockerfile_content_set = build_config.dockerfile_content is not NOTSET and build_config.dockerfile_content is not None
    
    if not dockerfile_set and not dockerfile_content_set:
        raise ValueError("Missing required build field: either 'dockerfile' or 'dockerfile_content' must be specified")
    if build_config.tag is NOTSET:
        raise ValueError("Missing required build field: tag")

    # Get platform from container config if available
    platform = None
    if substituted_config.platform is not NOTSET:
        platform = substituted_config.platform

    # Handle context: NOTSET means empty context (no files sent to Docker)
    context = build_config.context if build_config.context is not NOTSET else ""

    return BuildImageSpec(
        dockerfile=build_config.dockerfile if build_config.dockerfile is not NOTSET else None,
        dockerfile_content=build_config.dockerfile_content if build_config.dockerfile_content is not NOTSET else None,
        context=context,
        tag=build_config.tag,
        args=build_config.args if build_config.args is not NOTSET else {},
        platform=platform,
    )


def _resolve_dockerfile_input(spec: BuildImageSpec) -> Tuple[List[str], Optional[bytes]]:
    """Resolve dockerfile arguments and input data for subprocess.
    
    Returns:
        (dockerfile_args, input_data): Arguments for docker command and stdin data
    """
    if spec.dockerfile_content:
        return ["-f", "-"], spec.dockerfile_content.encode('utf-8')
    else:
        return ["-f", spec.dockerfile], None


def _resolve_context_path(spec: BuildImageSpec) -> str:
    """Resolve context path for docker build command.
    
    Returns:
        Context path: "-" for empty context (stdin), filesystem path otherwise
    """
    return "-" if spec.context == "" else spec.context


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

    # Resolve dockerfile and context independently
    dockerfile_args, input_data = _resolve_dockerfile_input(build_spec)
    context_path = _resolve_context_path(build_spec)
    
    # Handle special case: empty context with dockerfile file needs empty stdin
    if build_spec.context == "" and not build_spec.dockerfile_content:
        input_data = b""

    # Build command with all arguments
    build_cmd = [
        container_runtime, "build",
        *dockerfile_args,
        *(["--platform", build_spec.platform] if build_spec.platform else []),
        *[item for key, value in build_spec.args.items() for item in ["--build-arg", f"{key}={value}"]],
        "-t", build_spec.tag,
        context_path
    ]

    if verbose:
        print(f"[ctenv] Building image: {' '.join(build_cmd)}", file=sys.stderr)

    # Execute build
    try:
        result = subprocess.run(
            build_cmd, 
            cwd=runtime.project_dir, 
            input=input_data,
            capture_output=not verbose, 
            text=False,
            check=True
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
