# ctenv

[![GitHub repo](https://img.shields.io/badge/github-repo-green)](https://github.com/osks/ctenv)
[![PyPI](https://img.shields.io/pypi/v/ctenv.svg)](https://pypi.org/project/ctenv/)
[![Changelog](https://img.shields.io/github/v/release/osks/ctenv?include_prereleases&label=changelog)](https://github.com/osks/ctenv/releases)
[![Tests](https://github.com/osks/ctenv/actions/workflows/test.yml/badge.svg)](https://github.com/osks/ctenv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/osks/ctenv/blob/master/LICENSE)

Run commands in any container image while preserving your user identity and file permissions.

## Install

```bash
# Install with pip
pip install ctenv

# Install with uv
uv tool install ctenv

# Or run directly without installing
uv tool run ctenv --help
```

## Usage

```bash
# Interactive shell in ubuntu container
ctenv run --image ubuntu

# Run specific command
ctenv run -- npm test

# Run Claude Code with volumes and post-start setup
ctenv run --image node:20 --volume ~/.claude.json --volume ~/.claude --post-start-command "npm install -g @anthropic-ai/claude-code"
```

## Why ctenv?

When running containers with mounted directories, files created inside often have root ownership or wrong permissions. ctenv solves this by:

- Creating a matching user (same UID/GID) dynamically in existing images at runtime
- Mounting your current directory at `/repo` with correct permissions  
- Using `gosu` to drop privileges after container setup

This works with any existing Docker image without modification - no custom Dockerfiles needed. Provides similar functionality to Podman's `--userns=keep-id` but works with Docker. Also similar to Development Containers but focused on running individual commands rather than persistent development environments.

Under the hood, ctenv starts containers as root for file ownership setup, then drops privileges using bundled `gosu` binaries before executing your command. It generates bash entrypoint scripts dynamically to handle user creation and environment setup.

## Highlights

- Works with existing images without modifications  
- Files created have your UID/GID (preserves permissions)
- Convenient volume mounting like `-v ~/.gitconfig` (mounts to same path in container)
- Simple configuration with reusable `.ctenv.toml` setups

## Requirements

- Python 3.9+
- Docker (tested on Linux/macOS)

## Features

- User identity preservation (matching UID/GID in container)
- Volume mounting with shortcuts like `-v ~/.gitconfig` (mounts to same path)
- Volume ownership fixing with custom `:chown` option (similar to Podman's `:U` and `:chown`)
- Post-start commands for running setup as root before dropping to user permissions
- Template variables like `${USER}`, `${env.HOME}` in configurations
- Configuration file support with reusable container definitions
- Cross-platform support for linux/amd64 and linux/arm64 containers
- Bundled gosu binaries for privilege dropping
- Interactive and non-interactive command execution

## Configuration

Create `.ctenv.toml` for reusable container setups:

```toml
[defaults]
command = "zsh"

[containers.python]
image = "python:3.11"
volumes = ["~/.cache/pip"]

# Run Claude Code in isolation
[containers.claude]
image = "node:20"
post_start_commands = ["npm install -g @anthropic-ai/claude-code"]
volumes = ["~/.claude.json", "~/.claude"]
```

Then run:
```bash
ctenv run python -- python script.py
ctenv run claude
```

## Common Use Cases

### Development Tools
Run linters, formatters, or compilers from containers:
```bash
ctenv run --image rust:latest -- cargo fmt
ctenv run --image node:20 -- eslint src/
```

### Build Systems
Use containerized build environments:
```toml
[containers.build]
image = "some-build-system:v17"
volumes = ["build-cache:/var/cache:rw,chown"]
```

### Claude Code
Run Claude Code in isolation:
```toml
[containers.claude]
image = "node:20"
post_start_commands = ["npm install -g @anthropic-ai/claude-code"]
volumes = ["~/.claude.json", "~/.claude"]
```

## Detailed Examples

### Claude Code with Network Restrictions
For running Claude Code in isolation with network limitations:

```toml
[containers.claude]
image = "node:20"
network = "bridge"
run_args = ["--cap-add=NET_ADMIN"]
post_start_commands = [
    "apt update && apt install -y iptables",
    "iptables -A OUTPUT -d 192.168.0.0/24 -j DROP",
    "npm install -g @anthropic-ai/claude-code"
]
volumes = ["~/.claude.json", "~/.claude"]
```

Note: On macOS, Claude Code stores credentials in the keychain by default. When run in a container, it will create `~/.claude/.credentials.json` instead, which persists outside the container due to the volume mount.

### Build System with Caching
Complex build environment with shared caches:

```toml
[containers.build]
image = "registry.company.internal/build-system:v1"
env = [
    "BB_NUMBER_THREADS",
    "CACHE_MIRROR=http://build-cache.company.internal/",
    "BUILD_CACHES_DIR=/var/cache/build-caches/image-${image|slug}",
]
volumes = [
    "build-caches-user-${USER}:/var/cache/build-caches:rw,chown",
    "${env.HOME}/.ssh:/home/builduser/.ssh:ro"
]
post_start_commands = ["source /venv/bin/activate"]
```

This setup ensures the build environment matches the user's environment while sharing caches between different repository clones.
