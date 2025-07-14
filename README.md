# ctenv

[![PyPI](https://img.shields.io/pypi/v/ctenv.svg)](https://pypi.org/project/ctenv/)
[![Changelog](https://img.shields.io/github/v/release/osks/ctenv?include_prereleases&label=changelog)](https://github.com/osks/ctenv/releases)
[![Tests](https://github.com/osks/ctenv/actions/workflows/test.yml/badge.svg)](https://github.com/osks/ctenv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/osks/ctenv/blob/master/LICENSE)

ctenv is a tool for running programs in Docker/Podman containers while preserving user identity and file permissions.

## Features

- **User Identity Preservation**: Automatically maps your current user/group into the container
- **Directory Mounting**: Mounts your current directory into the container at `/repo`
- **File Permissions**: Files created in containers have correct ownership on the host
- **Self-Contained**: Only requires `gosu` binary for privilege dropping
- **Container Runtime Support**: Works with both Docker and Podman

## Installation

Install this tool using `pip`:
```bash
pip install ctenv
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
```

### CLI Options

**Global options:**
- `--verbose`, `-v`: Enable verbose debug output with timestamps
- `--quiet`, `-q`: Suppress non-essential output
- `--version`: Show version information
- `--help`: Show help message

**Run command options:**
- `--image`: Container image to use (default: ubuntu:latest)
- `--env`: Set environment variable (NAME=VALUE) or pass from host (NAME)
- `--volume`: Mount additional volume (HOST:CONTAINER format)
- `--sudo`: Add user to sudoers with NOPASSWD inside container
- `--network`: Enable container networking (default: disabled for security)
- `--dir`: Directory to mount as workdir (default: current directory)
- `--debug`: Show configuration details without running container

For help, run:
```bash
ctenv --help
ctenv run --help
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

- **uv**: Modern Python package manager (recommended)
- **Docker or Podman**: Container runtime
- **gosu**: Binary for privilege dropping
