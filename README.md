# ctenv

[![GitHub repo](https://img.shields.io/badge/github-repo-green)](https://github.com/osks/ctenv)
[![PyPI](https://img.shields.io/pypi/v/ctenv.svg)](https://pypi.org/project/ctenv/)
[![Changelog](https://img.shields.io/github/v/release/osks/ctenv?include_prereleases&label=changelog)](https://github.com/osks/ctenv/releases)
[![Tests](https://github.com/osks/ctenv/actions/workflows/test.yml/badge.svg)](https://github.com/osks/ctenv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/osks/ctenv/blob/master/LICENSE)

Run commands in containers from any image as current user, preserving user identity and permissions.

## Install

```bash
# Install with pip
$ pip install ctenv

# Install with uv
$ uv tool install ctenv

# Or run directly without installing
$ uv tool run ctenv --help
```

Recommend [installing uv](https://docs.astral.sh/uv/getting-started/installation/).


## Usage

```bash
# Interactive shell in ubuntu container
$ ctenv run --image ubuntu -- bash

# Run specific command
$ ctenv run -- npm test

# Run Claude Code in a container
$ ctenv run --image node:20 --volume ~/.claude.json --volume ~/.claude \
    --post-start-command "npm install -g @anthropic-ai/claude-code"
```

## Why ctenv?

When running containers with mounted directories, files created inside often have root ownership or wrong permissions. ctenv solves this by:

- Creating a matching user (same UID/GID) dynamically in existing images at runtime
- Mounting your current directory with correct permissions
- Using `gosu` to drop privileges after container setup

This works with any existing Docker image without modification - no custom Dockerfiles needed. Provides similar functionality to Podman's `--userns=keep-id` but works with Docker. Also similar to Development Containers but focused on running individual commands rather than persistent development environments.

Under the hood, ctenv starts containers as root for file ownership setup, then drops privileges using bundled `gosu` binaries before executing your command. It generates bash entrypoint scripts dynamically to handle user creation and environment setup.

## Highlights

- Works with existing images without modifications  
- Files created have your UID/GID (preserves permissions)
- Convenient volume mounting like `-v ~/.gitconfig` (mounts to same path in container)
- Simple configuration with reusable `.ctenv.toml` setups

## Requirements

- Python 3.10+
- Docker (tested on Linux/macOS)

## Features

- User identity preservation (matching UID/GID in container)
- Volume mounting with shortcuts like `-v ~/.gitconfig` (mounts to same path)
- Volume ownership fixing with custom `:chown` option (similar to Podman's `:U` and `:chown`)
- Post-start commands for running setup as root before dropping to user permissions
- Template variables with environment variables, like `${env.HOME}`
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

# For running Claude Code in container
[containers.claude]
image = "node:20"
post_start_commands = ["npm install -g @anthropic-ai/claude-code"]
volumes = ["~/.claude.json", "~/.claude"]
```

Then run:
```bash
$ ctenv run python -- python script.py
$ ctenv run claude
```

## Common Use Cases

### Claude Code
Run Claude Code in a container for isolation:

```shell
$ ctenv run --image node:20 -v ~/.claude.json -v ~/.claude/ --post-start-command "npm install -g @anthropic-ai/claude-code" -- claude
```

Or write as config in `~/.ctenv.toml`:
```toml
[containers.claude]
image = "node:20"
volumes = ["~/.claude.json", "~/.claude/"]
post_start_commands = ["npm install -g @anthropic-ai/claude-code"]
command = "claude"
```
and use with: `ctenv run claude`

You can also use Dev Containers for Claude Code: https://docs.anthropic.com/en/docs/claude-code/devcontainer

### Development Tools
Run linters, formatters, or compilers from containers:
```bash
$ ctenv run --image rust:latest -- cargo fmt
$ ctenv run --image node:20 -- eslint src/
```

### Build Systems
Use containerized build environments:
```toml
[containers.build]
image = "some-build-system:v17"
volumes = ["build-cache:/var/cache:rw,chown"]
```

## Detailed Examples

### Claude Code without installing every time

The most obvious way is to create a container image where you have installed Claude Code and run ctenv using that image.

```toml
[containers.claude]
image = "my-dev-image"
volumes = ["~/.claude.json", "~/.claude/"]
command = "claude"
```

One alternative is to use NVM and store the installation in a
volume. Below is example just to showcase the NVM "hack". For real
use, you likely want an image with more development tools installed.

In `.ctenv.toml`:

```toml
# Installing in volume called claude-nvm
[containers.claude-install]
image = "ubuntu:latest"
volumes = ["~/.claude.json", "~/.claude/", "claude-nvm:/nvm"]
env = ["NVM_DIR=/nvm"]
post_start_commands = [
    # Install curl (for nvm)
    "apt update && apt install -y curl",
    # Install nvm
    "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash",
    # node and claude code
    "/bin/bash -c 'source /nvm/nvm.sh && nvm install 20 && npm install -g @anthropic-ai/claude-code'"
]
command = "exit 0"

# Running
[containers.claude-run]
image = "ubuntu:latest"
volumes = ["~/.claude.json", "~/.claude/", "claude-nvm:/nvm"]
env = ["NVM_DIR=/nvm"]
command = "/bin/bash -c 'source /nvm/nvm.sh && claude'"
```

Run:
```shell
# Install (once)
$ ctenv run claude-install

# Run without installing again
$ ctenv run claude-run
```


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
    "build-caches-user-${env.USER}:/var/cache/build-caches:rw,chown",
    "${env.HOME}/.ssh:/home/builduser/.ssh:ro"
]
post_start_commands = ["source /venv/bin/activate"]
```

This setup ensures the build environment matches the user's environment while sharing caches between different repository clones.


## History

The background for ctenv was a bash script that I developed at work
([Agama](https://www.agama.tv/)) for running our build system in a
container. Besides running the build, it was useful to also be able to
run and use the compiled code in the build system environment, which
had older libraries than the modern OSes that was used by the
developers.

ctenv is a much more generic tool than that bash script and without
the many hard-coded parts. Written i Python and support for config
files and much more.
