"""Container image building for ctenv.

This module handles image building functionality including:
- BuildImageSpec dataclass for resolved build configuration
- Image building logic and execution
- Build configuration parsing and validation
"""

import os
import subprocess
import sys
import tempfile
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
    dockerfile_content_set = (
        build_config.dockerfile_content is not NOTSET
        and build_config.dockerfile_content is not None
    )

    if not dockerfile_set and not dockerfile_content_set:
        raise ValueError(
            "Missing required build field: either 'dockerfile' or 'dockerfile_content' must be specified"
        )
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
        dockerfile_content=build_config.dockerfile_content
        if build_config.dockerfile_content is not NOTSET
        else None,
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
        # Convert literal \n sequences to actual newlines for better shell compatibility
        processed_content = spec.dockerfile_content.replace("\\n", "\n")
        return ["-f", "-"], processed_content.encode("utf-8")
    else:
        # spec.dockerfile should never be None due to validation in parse_build_spec
        assert spec.dockerfile is not None, "Either dockerfile or dockerfile_content must be set"
        return ["-f", spec.dockerfile], None


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

    # Resolve dockerfile input
    dockerfile_args, input_data = _resolve_dockerfile_input(build_spec)
    
    # Handle context: create temp directory for empty context
    temp_context_dir = None
    try:
        if build_spec.context == "":
            # Create empty temporary directory for empty context
            temp_context_dir = tempfile.mkdtemp(prefix="ctenv-empty-context-")
            context_path = temp_context_dir
        else:
            context_path = build_spec.context

        # Build command with all arguments
        build_cmd = [
            container_runtime,
            "build",
            *dockerfile_args,
            *(["--platform", build_spec.platform] if build_spec.platform else []),
            *[
                item
                for key, value in build_spec.args.items()
                for item in ["--build-arg", f"{key}={value}"]
            ],
            "-t",
            build_spec.tag,
            context_path,
        ]

        if verbose:
            print(f"[ctenv] Building image: {' '.join(build_cmd)}", file=sys.stderr)

        # Execute build
        result = subprocess.run(
            build_cmd,
            cwd=runtime.project_dir,
            input=input_data,
            capture_output=not verbose,
            text=False,
            check=True,
        )

        if verbose and result.stdout:
            print(result.stdout, file=sys.stderr)

        return build_spec.tag

    except subprocess.CalledProcessError as e:
        # Format Docker error output for better readability
        print(f"\n[ctenv] Image build failed with exit code {e.returncode}", file=sys.stderr)
        
        # Display Docker's error output in a readable format
        if e.stderr:
            docker_error = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else str(e.stderr)
            print(f"[ctenv] Docker build error:\n{docker_error}", file=sys.stderr)
        elif e.stdout:
            docker_output = e.stdout.decode('utf-8') if isinstance(e.stdout, bytes) else str(e.stdout)
            print(f"[ctenv] Docker build output:\n{docker_output}", file=sys.stderr)
            
        # Exit cleanly without showing Python traceback
        sys.exit(1)
    except FileNotFoundError:
        raise RuntimeError(
            f"Container runtime '{container_runtime}' not found. Please install Docker or Podman."
        ) from None
    finally:
        # Clean up temporary directory if created
        if temp_context_dir:
            import shutil
            try:
                shutil.rmtree(temp_context_dir)
            except OSError:
                pass  # Ignore cleanup errors
