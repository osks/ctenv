# ctenv

[![PyPI](https://img.shields.io/pypi/v/ctenv.svg)](https://pypi.org/project/ctenv/)
[![Changelog](https://img.shields.io/github/v/release/osks/ctenv?include_prereleases&label=changelog)](https://github.com/osks/ctenv/releases)
[![Tests](https://github.com/osks/ctenv/actions/workflows/test.yml/badge.svg)](https://github.com/osks/ctenv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/osks/ctenv/blob/master/LICENSE)

ctenv runs commands in containers by dynamically creating a matching user (same UID/GID) in existing images at runtime, ensuring files in mounted directories get your permissions.

## Why ctenv?

Docker's `--user` flag only works if the user already exists in the container image. Podman's `--userns=keep-id` only works in rootless mode. Neither provides dynamic user creation for any image.

**ctenv solves:**
- Creates matching user in ANY container image at runtime
- Files created with your UID/GID, not root
- Consistent mount paths prevent build cache invalidation

**You need ctenv when:**
- Container creates files in mounted volumes
- Build tools embed absolute paths
- Working with images you can't modify

## Common use cases

- **Build Systems**: Running containerized builds against local repositories
- **Development Tools**: Using formatters, linters, or compilers from containers on your code
- **Claude Code**: Running AI assistants in containers while maintaining file permissions
- **CI/CD Testing**: Replicating CI environments locally with proper permissions

ctenv is somewhat related to `devcontainers`, but has a much smaller
scope. It can start a new container directly for a command, rather than
keeping a container running in the background.

## Key Features

- **User Identity Preservation**: Automatically creates a matching user inside the container with your exact UID/GID and home directory path
- **Permission Management**: Optionally fixes ownership of mounted volumes with `:chown` (brings Podman's `:U`/`:chown` functionality to Docker)
- **Configurable Contexts**: Define reusable container configurations for different environments

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
# Basic usage
ctenv run                        # Interactive bash session
ctenv run -- ls -la              # Run a command
ctenv run --image node:20 -- npm install

# Use configuration contexts
ctenv run dev                    # Use 'dev' context from config
ctenv run test -- npm test

# Common options
ctenv run --sudo -- apt update   # Run with sudo access
ctenv run --network bridge       # Enable networking
ctenv run --volume /data:/data   # Mount additional volumes
```

Run `ctenv --help` for all options.

## Configuration

ctenv uses TOML configuration files:
- Project: `.ctenv/ctenv.toml` (searched upward from current directory)
- Global: `~/.ctenv/ctenv.toml`

Example `.ctenv/ctenv.toml`:
```toml
[defaults]
image = "node:18"
sudo = true

[contexts.dev]
image = "node:18"
network = "bridge"
env = ["NODE_ENV=development", "DEBUG=*"]

[contexts.test]
image = "node:18-alpine"
env = ["NODE_ENV=test", "CI=true"]
```

Configuration precedence: CLI args > project config > global config > defaults

```bash
ctenv contexts              # List available contexts
ctenv config show dev       # Show context configuration
ctenv run dev -- npm start  # Use 'dev' context
```

