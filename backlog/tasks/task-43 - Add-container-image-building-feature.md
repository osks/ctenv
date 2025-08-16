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

**Build context**
- Config: `build = { context = "./backend" }`
- CLI: `--build-context PATH`
- Build context directory (default: ".")
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
ctenv run --build --build-dockerfile Dockerfile.dev --build-context ./backend dev

# Build with custom tag and build arguments
ctenv run --build --build-tag my-app:v1.0 --build-arg NODE_VERSION=20 --build-arg DEBUG=1 dev

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
