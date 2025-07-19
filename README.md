# ctenv

[![PyPI](https://img.shields.io/pypi/v/ctenv.svg)](https://pypi.org/project/ctenv/)
[![Changelog](https://img.shields.io/github/v/release/osks/ctenv?include_prereleases&label=changelog)](https://github.com/osks/ctenv/releases)
[![Tests](https://github.com/osks/ctenv/actions/workflows/test.yml/badge.svg)](https://github.com/osks/ctenv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/osks/ctenv/blob/master/LICENSE)

ctenv is a tool for easily running commands in a container environment
similar to the current user environment.

Use cases:

- Running a build system container against a local repository

- Running Claude Code more contained

ctenv is somewhat related to `devcontainers`, but has a much smaller
scope. It can start a new container directly for a command, rather than
keeping a container running in the background.

- Makes sure that the container has a user that has the same name,
  same UID/GID and same path to HOME, so that permissions in mounted
  volumes match.

- Optionally chown:s mounted volumes (similar to Podman's `:U`
  option to volumes) so they match the UID/GID.

- Configurable contexts for specifying how the container should be
  created and what should be mounted, for easily starting different
  containers.

## Installation

With `uv` you can just run `uv tool ctenv` to use it directly.

Install this tool using `pip`:
```bash
pip install ctenv
```


## Design

ctenv starts the container as root to have permissions for chown, and
then drops permissions using `gosu` before running the command. It
does this by generating an entrypoint bash script that it mounts and
runs.

Implemented in a single Python file only depending on Python 3.11. Can
be used by itself, or installed via `uv` or `pip` (etc).


## Use cases

### Use case: Claude Code

Example config:
```toml
[contexts.claude]
image = "node:20"
network = "bridge"
post_start_commands = ["npm install -g @anthropic-ai/claude-code"]
volumes = ["${env:HOME}/.claude.json:${env:HOME}/.claude.json", "${env:HOME}/.claude:${env:HOME}/.claude"]
```

Note: Be aware that on macOS Claude Code seem to store the credentials
in the keychain if you have a Claude account. The credentials therefor
won't be available in the container. However, if you go through /login
in the container, it will write them to `~/.claude/.credentials.json`
instead and continue to use them from there. Since the above mounts
that directory, the credentials file will exist outside the container
also.


### Use case: Build system container

The build system it was originally written for contained the build
environment in a container image. An internal script similar to ctenv
was used to run the build. ctenv could then be used to start a shell
or run other commands in the same environment as the build system.

That build system also used a volume for storing a cache and the
cached files contained hard-coded paths, so it was important that the
environment in the container was as similar as possible to the regular
user environment outside the container. For sharing the cache between
different clones of the repository, the repository needed to be
mounted at a fixed path. The caching is also the reason for matching
the path to HOME (which is otherwise different on for example macOS vs
typical Linux distributions).

The ctenv config could look something like this, to show which
features that were used:

```toml
[contexts.build-system]
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


## Usage

```bash
# Run an interactive bash session
ctenv run

# Run a specific command
ctenv run -- ls -la

# Use a custom container image
ctenv run --image ubuntu:latest -- whoami

# Run with Alpine Linux
ctenv run --image alpine:latest -- sh

# Enable verbose output for debugging
ctenv --verbose run -- echo "Hello"

# Suppress non-essential output
ctenv --quiet run -- make build

# Use ctenv with commands that produce output (stdout stays clean)
ctenv run -- cat myfile.txt > output.txt  # Only file content goes to stdout
ctenv run -- ls -la | grep ".txt"          # Only ls output goes to stdout

# Use configuration contexts
ctenv run dev                    # Use 'dev' context from config
ctenv run test -- npm test       # Use 'test' context, run npm test
```

### CLI Options

**Global options:**
- `--verbose`, `-v`: Enable verbose debug output with timestamps
- `--quiet`, `-q`: Suppress non-essential output
- `--version`: Show version information
- `--help`: Show help message

**Run command options:**
- `ctenv run [CONTEXT]`: Use named configuration context
- `--config`: Path to configuration file
- `--image`: Container image to use (default: ubuntu:latest)
- `--env`: Set environment variable (NAME=VALUE) or pass from host (NAME)
- `--volume`: Mount additional volume (HOST:CONTAINER format)
- `--sudo`: Add user to sudoers with NOPASSWD inside container
- `--network`: Enable container networking (default: disabled for security)
- `--dir`: Directory to mount as workdir (default: current directory)
- `--dry-run`: Show Docker command without running container
- `--entrypoint-cmd`: Add extra command to run before main command (can be used multiple times)

**Configuration commands:**
- `ctenv config show [CONTEXT]`: Show configuration or specific context
- `ctenv config path`: Show path to configuration file being used
- `ctenv contexts`: List available contexts

For help, run:
```bash
ctenv --help
ctenv run --help
ctenv config --help
```

## Configuration

### Configuration Files

ctenv supports TOML configuration files for project-specific and global settings. Configuration files are discovered using git-style directory traversal:

1. Project config: `.ctenv/ctenv.toml` (searched upward from current directory)
2. Global config: `~/.ctenv/ctenv.toml`

### Configuration Format

#### Project Configuration (`.ctenv/ctenv.toml`)
```toml
# Default settings for this project
[defaults]
image = "node:18"
network = "bridge"
sudo = true
env = ["NODE_ENV=development"]

# Project-specific contexts
[contexts.dev]
image = "node:18"
network = "bridge"
sudo = true
env = ["NODE_ENV=development", "DEBUG=*"]
volumes = ["./node_modules:/app/node_modules"]

[contexts.test]
image = "node:18-alpine"
network = "none"
sudo = false
env = ["NODE_ENV=test", "CI=true"]
command = "npm test"

[contexts.prod]
image = "node:18-alpine"
network = "none"
sudo = false
env = ["NODE_ENV=production"]
```

#### Global Configuration (`~/.ctenv/ctenv.toml`)
```toml
# Global defaults across all projects
[defaults]
image = "ubuntu:latest"
network = "none"
sudo = false

# Global contexts available everywhere
[contexts.debug]
network = "bridge"
sudo = true
env = ["DEBUG=1"]
```

### Configuration Precedence

Configuration values are resolved in this order (highest to lowest priority):
1. Command-line arguments
2. Selected context from project config
3. `[defaults]` section from project config
4. Selected context from global config
5. `[defaults]` section from global config
6. Built-in defaults

### Examples

```bash
# Use project defaults
ctenv run

# Use 'dev' context
ctenv run dev

# Use 'test' context with command
ctenv run test -- npm test

# Override context settings
ctenv run --image alpine:latest dev

# Show configuration
ctenv config show
ctenv config show dev

# List available contexts
ctenv contexts
```

## Development

### Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd ctenv

# Setup development environment (requires uv)
make dev

# Run tests
make test
```

### Manual Setup

If you prefer manual setup or don't have `make`:

```bash
# Install uv if you haven't already
pip install uv

# Create virtual environment and install dependencies
uv venv
uv pip install -e '.[test]'
source .venv/bin/activate

# Run tests
uv run pytest tests/ -v
```

## Requirements

- **Python 3.11+**: Required for built-in TOML support
- **uv**: Modern Python package manager (recommended)
- **Docker or Podman**: Container runtime
- **gosu**: Binary for privilege dropping
