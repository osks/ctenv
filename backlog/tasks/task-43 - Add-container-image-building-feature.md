---
id: task-43
title: Add container image building feature
status: To Do
assignee: []
created_date: '2025-08-15'
updated_date: '2025-08-15'
labels: []
dependencies: []
---

## Description

Add container image building functionality to ctenv to make it easier to customize existing images and maintain containerized development workflows.

## Features

- Build custom images from Dockerfiles or inline build context
- Auto-generated tag names by default (e.g., `ctenv-${project_dir|slug}:latest`)
- Support for build arguments and environment variables
- Integration with existing ctenv configuration
- Ability to specify custom image tags when needed


## Build Configuration Options

**Enable building**
- Config: `build = {}`
- Enable image building (uses defaults)

**Dockerfile path**
- Config: `build = { dockerfile = "Dockerfile.dev" }`
- CLI: `--build-dockerfile PATH`
- Path to Dockerfile (default: "Dockerfile")
- Relative paths resolved from project directory
- Mutually exclusive with `dockerfile_content`

**Dockerfile content (inline)**
- Config: `build = { dockerfile_content = "FROM ubuntu:latest\nRUN apt-get update..." }`
- CLI: `--build-dockerfile-content CONTENT`
- Inline Dockerfile content as string
- Creates temporary Dockerfile during build
- Supports variable substitution (e.g., `"FROM ${base_image}"`)
- Mutually exclusive with `dockerfile`

**Build context**
- Config: `build = { context = "./backend" }`
- CLI: `--build-context PATH`
- Build context directory (default: ".")
- Use `"-"` for empty context (no files sent to Docker)
- Relative paths resolved from project directory

**Custom tag**
- Config: `build = { tag = "my-app:v1.0" }`
- CLI: `--build-tag TAG`
- Custom image tag (default: auto-generated)

**Build arguments**
- Config: `build = { args = { NODE_VERSION = "18" } }`
- CLI: `--build-arg KEY=VALUE` (repeatable)
- Build arguments passed to Dockerfile

**Platform**
Use value from existing container option.


### Multi-line TOML Alternative
For complex configurations, use multi-line table syntax:
```toml
[containers.prod.build]
dockerfile = "Dockerfile.prod"
context = "."
tag = "my-project:prod"
args = { NODE_VERSION = "18", OPTIMIZE = "true" }
```

### Inline Dockerfile Content Examples
```toml
# Simple inline Dockerfile with empty context (no files sent)
[containers.simple]
build = { dockerfile_content = "FROM ubuntu:latest\nRUN apt-get update && apt-get install -y curl", context = "-" }

# Multi-line inline Dockerfile with build context
[containers.dev.build]
dockerfile_content = """
FROM ${base_image:-ubuntu:22.04}
RUN apt-get update && apt-get install -y \\
    curl \\
    git \\
    build-essential
WORKDIR /app
COPY . .
RUN npm install
CMD ["npm", "start"]
"""
context = "."
args = { NODE_ENV = "development" }
```

## Configuration Example

```toml
# Minimal build configuration (auto-generated tag: "ctenv-dev:latest")
[containers.dev]
working_dir = "/workspace"
environment = { NODE_ENV = "development" }
build = {}  # Uses defaults: dockerfile="Dockerfile", context="."

# Simple build with custom Dockerfile (auto-generated tag)
[containers.backend]
working_dir = "/app"
build = { dockerfile = "Dockerfile.backend" }

# Full build configuration with custom tag
[containers.prod]
working_dir = "/app"
environment = { NODE_ENV = "production", LOG_LEVEL = "info" }
volumes = ["/var/log/app:/logs:ro"]
ports = ["80:8080"]
restart_policy = "unless-stopped"

[containers.prod.build]
dockerfile = "Dockerfile.prod"
context = "."
tag = "my-project:prod"  # Custom tag overrides auto-generated
args = { OPTIMIZE = "true", BUILD_ENV = "production" }

# Container using pre-built image (mutually exclusive with build)
[containers.runtime]
image = "ubuntu:22.04"
working_dir = "/repo"
environment = { DEBUG = "1" }
volumes = ["/home/user/data:/data"]
ports = ["8080:8080"]
```

## CLI Usage Examples

```bash
# Build image before running (new command)
ctenv build

# Build and run in one command
ctenv run --build dev -- python app.py

# Build with custom dockerfile and context
ctenv run --build-dockerfile Dockerfile.dev --build-context ./backend dev

# Build with inline Dockerfile content
ctenv run --build-dockerfile-content "FROM node:18\nWORKDIR /app\nCOPY . .\nRUN npm install" dev

# Build with custom tag and build arguments
ctenv run --build-tag my-app:v1.0 --build-arg NODE_VERSION=20 --build-arg DEBUG=1 dev

# Build with advanced options
ctenv build --build-target production --platform linux/amd64 prod

# Use config file build settings with CLI overrides
ctenv run --build-arg OVERRIDE=true dev  # Uses container.build config + CLI override
```

## Implementation Notes

- Should integrate with existing configuration system
- Build command should be available as `ctenv build`
- If container has build instead of image, build before run (always? check if tag exist?)
- Consider caching strategies for faster rebuilds
- Ensure compatibility with both Docker and Podman
- **Path resolution**: Use same pattern as existing config options (`workspace`, `volumes`, `gosu_path`) - resolve relative paths from project directory where `.ctenv.toml` is located
- **Defaults alignment**: `dockerfile = "Dockerfile"` and `context = "."` both resolve relative to project root, which is the common location for Dockerfiles in projects

### Dockerfile Content Implementation

**Configuration Changes:**
- Add `dockerfile_content` field to `BuildConfig` dataclass (Union[str, NotSetType])
- Add mutual exclusion validation: `dockerfile` and `dockerfile_content` cannot both be specified
- Support variable substitution in `dockerfile_content` (same as other string fields)

**CLI Changes:**
- Add `--build-dockerfile-content CONTENT` argument to both `run` and `build` commands
- Mutual exclusion validation with `--build-dockerfile`

**Image Building Changes:**
- When `dockerfile_content` is specified:
  1. Use `docker build -f -` to read Dockerfile from stdin
  2. Pass dockerfile content through subprocess stdin
  3. No temporary files needed - cleaner and more secure
- When `dockerfile` is specified, use existing `-f path/to/Dockerfile` logic
- Example command: `docker build -f - -t tag:latest context/` with content piped to stdin

**Error Handling:**
- Clear error messages for mutual exclusion violations
- Handle subprocess communication errors when piping content to stdin
- Validation that dockerfile_content is not empty if specified

**Security Considerations:**
- No temporary files needed - more secure approach
- Docker/Podman will validate Dockerfile syntax
- Content passed directly through subprocess stdin

**Testing Requirements:**
- Unit tests for BuildConfig validation (mutual exclusion)
- Unit tests for stdin-based docker build command generation
- Integration tests for CLI argument parsing
- Integration tests for end-to-end build with dockerfile_content via stdin
- Tests for variable substitution in dockerfile_content
- Error handling tests for invalid configurations and subprocess communication

## Critical Analysis of Current Implementation

### Issues Identified for Simplification

#### 1. **Unnecessary Text Mode Variable**
**Current**: `use_text_mode = False` is always False in all code paths
**Problem**: Dead code - the variable serves no purpose
**Solution**: Remove `use_text_mode` variable entirely and hardcode `text=False`

#### 2. **Command Mutation Anti-pattern**
**Current**: 
```python
build_cmd.append("-")  # Add "-" 
# Later...
build_cmd[-1] = temp_dir  # Replace "-" with temp_dir
```
**Problem**: Mutating the command after building it is confusing and error-prone
**Solution**: Determine context path upfront, then build command once

#### 3. **Redundant Context Logic**
**Current**: Context handling is split between command building and execution phases
**Problem**: Same logic (`context == ""`) is checked in two places
**Solution**: Consolidate context resolution into single location

#### 4. **Resource Management Complexity**
**Current**: Manual cleanup in 3 separate exception handlers
**Problem**: Error-prone, repetitive, and easy to miss edge cases
**Solution**: Use context manager (`with tempfile.TemporaryDirectory()`) for automatic cleanup

#### 5. **Unclear Dockerfile/Context Relationship**
**Current**: Four separate conditional branches for dockerfile+context combinations
**Problem**: Logic is hard to follow and maintain
**Solution**: Separate concerns - resolve dockerfile input vs context path independently

### Proposed Simplified Implementation Strategy

#### **Step 1: Separate Input Resolution**
```python
def _resolve_dockerfile_input(spec):
    """Return (dockerfile_arg, input_data)"""
    if spec.dockerfile_content:
        return ["-f", "-"], spec.dockerfile_content.encode('utf-8')
    else:
        return ["-f", spec.dockerfile], None

def _resolve_context_path(spec):
    """Return (context_path, temp_dir_cm)"""
    if spec.context == "":
        if spec.dockerfile_content:
            # Need temp dir for empty context with dockerfile_content
            temp_dir_cm = tempfile.TemporaryDirectory()
            return temp_dir_cm.name, temp_dir_cm
        else:
            # Can use stdin for empty context with dockerfile file
            return "-", None
    else:
        return spec.context, None
```

#### **Step 2: Single Build Function**
```python
def build_container_image(spec, runtime, verbose=False):
    dockerfile_args, input_data = _resolve_dockerfile_input(spec)
    context_path, temp_dir_cm = _resolve_context_path(spec)
    
    with contextlib.ExitStack() as stack:
        if temp_dir_cm:
            stack.enter_context(temp_dir_cm)
            
        build_cmd = [
            container_runtime, "build",
            *dockerfile_args,
            *(["--platform", spec.platform] if spec.platform else []),
            *[arg for k, v in spec.args.items() for arg in ["--build-arg", f"{k}={v}"]],
            "-t", spec.tag,
            context_path
        ]
        
        result = subprocess.run(
            build_cmd, cwd=runtime.project_dir, 
            input=input_data, text=False, check=True,
            capture_output=not verbose
        )
        
        return spec.tag
```

### Benefits of Simplified Approach

1. **Clearer Logic**: Dockerfile and context resolution are independent
2. **Automatic Cleanup**: Context managers handle resource management
3. **No Command Mutation**: Build command once with correct values
4. **Fewer Branches**: From 4 conditional branches to 2 simple functions
5. **No Dead Code**: Remove unused `use_text_mode` variable
6. **Single Responsibility**: Each helper function has one clear purpose

### Lines of Code Reduction
- **Current**: ~63 lines in `build_container_image()`
- **Proposed**: ~25 lines in `build_container_image()` + 15 lines helpers = 40 total
- **Reduction**: ~37% fewer lines with clearer logic

### Maintainability Improvements
- Resource leaks impossible (context managers handle cleanup)
- Logic easier to test (helpers can be tested independently)  
- Adding new dockerfile sources or context types much simpler
- No error-prone manual cleanup code

### Recommendation
The current implementation is correct but unnecessarily complex. The proposed simplification maintains all functionality while significantly improving readability and maintainability. The key insight is separating dockerfile input resolution from context path resolution - they are independent concerns that got entangled.
