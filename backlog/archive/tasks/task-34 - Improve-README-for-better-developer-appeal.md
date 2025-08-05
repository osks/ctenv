---
id: task-34
title: Improve README for better developer appeal
status: Done
assignee: []
created_date: '2025-07-24'
labels: []
dependencies: []
---

## Description

Based on analysis of effective READMEs (uv, llm, minijinja), the current README needs restructuring for better developer appeal.

## Suggested Improvements

### Key Changes:
1. **Clearer tagline** - Replace verbose opening with concise value proposition
2. **Better structure** - Lead with quick start, move design details down
3. **Simplified examples** - Focus on most common use cases first
4. **Remove marketing language** - More direct, technical communication
5. **Visual hierarchy** - Better use of headers and sections

### Structure Outline:
- Brief description + badges
- Quick installation 
- Basic usage example
- Key features (bullet points)
- Common use cases with examples
- Configuration details
- Design/architecture (moved down)

### Tone:
- Concise, developer-focused
- No overselling or marketing speech
- Clear technical benefits
- Practical examples over explanations

## Proposed New README

```markdown
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

# Use custom image
ctenv run --image python:3.11 -- python --version
```

## Why ctenv?

When running containers with mounted directories, files created inside often have root ownership or wrong permissions. ctenv solves this by:

- Creating a matching user (same UID/GID) dynamically in existing images at runtime
- Mounting your current directory at `/repo` with correct permissions  
- Using `gosu` to drop privileges after container setup

This works with any existing Docker image without modification - no custom Dockerfiles needed. Provides similar functionality to Podman's `--userns=keep-id` but works with Docker. Similar to Development Containers but focused on running individual commands rather than persistent development environments.

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
- Convenient volume mounting with shortcuts like `-v ~/.gitconfig` (mounts to same path)
- Volume ownership fixing with custom `:chown` option (similar to Podman's `:U`/`:chown`)
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
```

## Original README (for reference)

```markdown
# ctenv

[![GitHub repo](https://img.shields.io/badge/github-repo-green)](https://github.com/osks/ctenv)
[![PyPI](https://img.shields.io/pypi/v/ctenv.svg)](https://pypi.org/project/ctenv/)
[![Changelog](https://img.shields.io/github/v/release/osks/ctenv?include_prereleases&label=changelog)](https://github.com/osks/ctenv/releases)
[![Tests](https://github.com/osks/ctenv/actions/workflows/test.yml/badge.svg)](https://github.com/osks/ctenv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/osks/ctenv/blob/master/LICENSE)

ctenv runs commands in containers by dynamically creating a matching user (same UID/GID) in existing images at runtime, ensuring files in mounted directories get your permissions.

## Why ctenv?

- ctenv can run commands as your user in a container
- Can use existing images by creating a matching user in the container at runtime
- Files created with your UID/GID
- Provides similar functionality as Podman's `--userns=keep-id` but with Docker
- Optionally fixes ownership of mounted volumes with `:chown` (brings Podman's `:U` functionality to Docker)
- Configurable containers for reusable container setups

### Use cases

- **Build Systems**: Running containerized builds against local repositories
- **Development Tools**: Using formatters, linters, or compilers from containers on your code
- **Claude Code**: Running AI assistants in containers while maintaining file permissions
- **CI/CD Testing**: Replicating CI environments locally with proper permissions

ctenv is somewhat related to [Development
Containers](https://containers.dev/) (`devcontainers`), but has a
smaller scope. One thing ctenv can do but doesn't seem supported by
devcontainers, is starting a new container directly for a command,
rather than keeping a container running in the background.

## Design

ctenv starts the container as root to have permissions for chown, and
then drops permissions using `gosu` before running the command. It
does this by generating an entrypoint bash script that it mounts and
runs.

Implemented as a Python package requiring Python 3.9+. Can be installed via `uv` or `pip`.

## Installation

With `uv` you can just run `uv tool ctenv` to use it directly.

Install this tool using `pip`:
```bash
pip install ctenv
```

## Examples

### Claude Code

To limit what Claude Code can do, it's nice to be able to run it in a container.
Anthropic has [example on how to run Claude Code in Development Containers](https://docs.anthropic.com/en/docs/claude-code/devcontainer)
and here is the code for how it's set up: https://github.com/anthropics/claude-code/tree/main/.devcontainer

We can use ctenv to mount the code into the container and setup
the same user as yourself in the container, so permissions match.

Run Claude Code in a container using ctenv:

```shell
ctenv run --image "node:20" --post-start-command "npm install -g @anthropic-ai/claude-code"
```

To not have to login everytime and to keep history, we can mount Claude Code's files:

```shell
ctenv run --image "node:20" \
          --post-start-command "npm install -g @anthropic-ai/claude-code" \
          --volume ~/.claude.json \
          --volume ~/.claude
```

Note: On macOS Claude Code seem to store credentials in the keychain
if you have a Claude account. The credentials therefor won't be
available in the container. However, if you login in Claude Code in
the container, it will write credentials to
`~/.claude/.credentials.json` instead and continue to use them from
there. Since the above mounts that directory, be aware that the
credentials file will then exist outside the container in a file now,
instead of the keychain.

For convenience you can configure a container in `.ctenv.toml`:

```toml
[containers.claude]
image = "node:20"
post_start_commands = [
    "npm install -g @anthropic-ai/claude-code"
]
volumes = ["~/.claude.json", "~/.claude"]
```

and then you can start it with just: `ctenv run claude`


If you want to limit which networks claude can access:
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
volumes = ["${env.HOME}/.claude.json:${env.HOME}/.claude.json", "${env.HOME}/.claude:${env.HOME}/.claude"]
```



### Build system

The build system ctenv was originally written for had the build
environment in a container image. A custom script was used to run the
build and handle permissions in the container, similar to what ctenv
does. The custom script didn't make it easy to run anything else than
the build in that environment, and was tied to that repository. An
internal version of ctenv was developed, allowing developers to run
other commands in the same environment as the build system.

The build system also used a volume for storing a cache and the cached
files contained hard-coded paths, so it was important that the
environment in the container was as similar as possible to the regular
user environment outside the container. For sharing the cache between
different clones of the repository, the repository needed to be
mounted at a fixed path. The caching is also the reason for matching
the path to HOME (which is otherwise different on for example macOS vs
typical Linux distributions), making it possible to run the build also
on macOS.

The ctenv config for this case look something like this:

```toml
[containers.build]
image = "registry.company.internal/build-system:v1"
env = [
    "BB_NUMBER_THREADS",
    "CACHE_MIRROR=http://build-cache.company.internal/",
    "BUILD_CACHES_DIR=/var/cache/build-caches/image-${image|slug}",
]
volumes = [
    "build-caches-user-${USER}:/var/cache/build-caches:rw,chown"
]
post_start_commands = ["source /venv/bin/activate"]
```
```

## Analysis of Current README

### What Works Well:
- Clear badges showing project status
- Good technical explanation of the core problem and solution
- Comprehensive examples (Claude Code, build systems)
- Detailed configuration examples

### Issues to Address:
1. **Long, unfocused opening**: Current tagline is verbose and technical
2. **Poor information hierarchy**: "Why ctenv?" section buries the key value prop
3. **Example overload**: Claude Code example is very long and dominates the README
4. **Scattered features**: Key capabilities are spread throughout rather than highlighted
5. **Marketing language**: Phrases like "somewhat related to" and lengthy comparisons
6. **Design details too early**: Technical implementation details appear before use cases

### Key Changes Made:
1. **Concise tagline**: "Run commands in containers while preserving your user identity and file permissions"
2. **Quick start first**: Installation and basic usage examples upfront
3. **Clear value proposition**: Direct explanation of the permission problem and solution
4. **Balanced examples**: Multiple short use cases instead of one dominant example
5. **Feature highlights**: Bullet point list of key capabilities
6. **Technical details last**: Design/implementation moved to end
7. **Removed verbose sections**: Eliminated comparisons to devcontainers and build system backstory

## What Was Removed and Why

### Removed Content:
1. **Long opening paragraph** (line 9): "ctenv runs commands in containers by dynamically creating..." 
   - **Why**: Too technical and verbose for opening tagline
   - **Replaced with**: Simple, clear value statement

2. **Extensive Claude Code example** (lines 53-114): Detailed setup with login creds, keychain issues, network restrictions
   - **Why**: Dominated the README, too specific for one use case
   - **Replaced with**: Brief, focused example in "Common Use Cases"

3. **devcontainers comparison** (lines 27-31): "ctenv is somewhat related to Development Containers..."
   - **Why**: Marketing language, unnecessary positioning against other tools
   - **Replaced with**: Direct focus on ctenv's benefits

4. **Build system backstory** (lines 116-150): Long explanation of original use case and internal development
   - **Why**: Historical context not relevant to new users
   - **Replaced with**: Generic build system example

5. **Detailed volume caching explanation** (lines 126-134): Hard-coded paths, cache sharing between clones
   - **Why**: Too specific, advanced use case better suited for documentation
   - **Replaced with**: Simple build cache example

6. **"Use cases" section header** (lines 20-25): Listed specific scenarios
   - **Why**: Redundant with examples, created unnecessary structure
   - **Replaced with**: Integrated into "Common Use Cases" with examples

### What Was Added and Why

### Added Content:
1. **Concise tagline**: "Run commands in containers while preserving your user identity and file permissions"
   - **Why**: Immediately communicates core value proposition
   - **Replaces**: Verbose technical description

2. **Quick start section**: Basic usage examples with common patterns
   - **Why**: Gets users running quickly, follows successful README patterns
   - **New addition**: Not present in original

3. **"Why ctenv?" problem statement**: Direct explanation of permission issues with emphasis on runtime user creation
   - **Why**: Clearly articulates the problem ctenv solves and highlights that it works with existing images
   - **Replaces**: Scattered technical explanations

4. **Features bullet points**: Consolidated key capabilities
   - **Why**: Easy scanning of core functionality
   - **Replaces**: Features scattered throughout text

5. **Multiple use case examples**: Development tools, build systems, AI assistants
   - **Why**: Shows versatility without overwhelming detail
   - **Replaces**: Single dominant Claude Code example

6. **Removed Commands section**: Decided against including explicit commands list
   - **Why**: Commands are discoverable via help and don't need separate section

7. **Requirements section**: Clear technical prerequisites
   - **Why**: Sets expectations upfront
   - **Replaces**: Buried implementation details

8. **Streamlined configuration examples**: Simpler .ctenv.toml examples
   - **Why**: Shows power without complexity
   - **Replaces**: Complex specific examples

9. **Multiple installation methods**: Added `uv tool install` and `uv tool run` options
   - **Why**: Modern Python tooling, allows usage without installation
   - **Replaces**: Single pip installation method
