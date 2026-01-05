# ctenv

[![GitHub repo](https://img.shields.io/badge/github-repo-green)](https://github.com/osks/ctenv)
[![PyPI](https://img.shields.io/pypi/v/ctenv.svg)](https://pypi.org/project/ctenv/)
[![Changelog](https://img.shields.io/github/v/release/osks/ctenv?include_prereleases&label=changelog)](https://github.com/osks/ctenv/releases)
[![Tests](https://github.com/osks/ctenv/actions/workflows/test.yml/badge.svg)](https://github.com/osks/ctenv/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/osks/ctenv/blob/master/LICENSE)

Container runner that executes as your user with correct file permissions.

Bring your own image: existing build environments, CI images, custom
Dockerfile - any container image. Use for interactive work, AI coding
agents, or builds. Mounts your project and supports per-project
container definitions.

Containers with mounted directories often have file ownership issues
on the host. ctenv solves this by creating a matching user (same
UID/GID) at runtime and dropping privileges with gosu. No image
modifications needed. Works with both Docker and Podman (rootless).

Highlights:

- Per-project configurable containers. `.ctenv.toml` - which also identifies the project root.
- Auto-mounted project root
- Convenient mounts, defaults to same path in container as on host. Example: Claude Code config `-v ~/.claude`
- Post-start commands as root, before dropping privileges. Example: setup firewall rules.
- Supports Docker and Podman (rootless)


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

### Requirements

- Python 3.10+
- Docker (tested on Linux and macOS)


## Usage

```bash
# Interactive shell in ubuntu container
$ ctenv run --image ubuntu:latest -- bash

# Run a configured container
$ ctenv run my-node

# Run a custom command and mount a volume
$ ctenv run my-node --volume ./tests -- npm test
```

## Why ctenv?

When running containers with mounted directories, files created inside often have root ownership or wrong permissions. ctenv solves this by:

- Creating a matching user (same UID/GID) dynamically in existing images at runtime
- Mounting your current directory with correct permissions
- Using [`gosu`](https://github.com/tianon/gosu) to drop privileges after container setup

This works with any existing Docker image without modification - no
custom Dockerfiles needed. Provides similar functionality to Podman's
`--userns=keep-id` but also works with Docker. Also similar to
Development Containers but focused on running individual commands
rather than persistent development environments.

Under the hood, ctenv starts containers as root for file ownership
setup, then drops privileges using bundled `gosu` binaries before
executing your command. It generates bash entrypoint scripts
dynamically to handle user creation and environment setup.

## Features

- Simple configuration with reusable `.ctenv.toml` setups
- User identity preservation (matching UID/GID in container)
- Mount specific subpaths instead of entire project (useful for monorepos, supports `:ro`)
- Volume mounting with shortcuts like `-v ~/.gitconfig` (mounts to same path)
- Volume ownership fixing with custom `:chown` option (similar to Podman's `:U` and `:chown`)
- Post-start commands for running setup as root before dropping to user permissions
- Template variables with environment variables, like `${env.HOME}`
- Configuration file support with reusable container definitions
- Cross-platform support for linux/amd64 and linux/arm64 containers
- Works with existing images without modifications
- Works with Docker and Podman (rootless)
- Bundled gosu binaries for privilege dropping
- Interactive and non-interactive command execution

## Configuration

Create `.ctenv.toml` in your project root (also marks the project directory) or `~/.ctenv.toml` for user-wide settings. Run with `ctenv run <container>`.

```toml
[defaults]
network = "bridge"

[containers.dev]
image = "python:3.11"
volumes = ["~/.gitconfig:ro"]
env = ["DEBUG=1", "API_KEY"]  # Set value or pass from host

[containers.dev.build]        # Optional: build image instead of pulling
dockerfile_content = """
FROM python:3.11
RUN pip install pytest
"""
```

### Config File Priority

1. Explicit `--config` files (in order specified)
2. Project config (`.ctenv.toml` found via upward search)
3. User config (`~/.ctenv.toml`)
4. Built-in defaults

A container configured in the current project config will shadow
container with name defined in HOME/global config.


### General options

- Project directory (`-p`, `--project-dir`) (default: auto-detect)
  
  Specifies the _project directory_, the root of your
  project. Generally your git repo. Define the project by placing a
  `.ctenv.toml` there; ctenv will look for it automatically by
  searching upward from cwd.
  
  The _project directory_ is auto-mounted into the container by default.
  Use `--subpath` to mount only specific subpaths instead.


### Container Options

Options for `[containers.NAME]` sections and their CLI equivalents:

- **`image`** (default: `ubuntu:latest`) (`--image`)
  Container image. Mutually exclusive with `build`.

- **`command`** (default: `bash`)
  Command to execute. On CLI, specified after `--`.

- **`name`** (default: auto) (`--name`)
  Container name. Default template: `ctenv-{container}-{pid}`

- **`default`** (config only)
  Mark as default container (only one allowed).

- **`workdir`** (default: `auto`) (`--workdir`)
  Working directory in container. `auto` preserves relative position from project root.

- **`project_target`** (default: same as host) (`--project-target`)
  Where in the container the project directory should be mounted. For example,
  `--project-target /repo` to always mount at a fixed path. Supports volume
  options (e.g., `/repo:ro`). Volumes that are subpaths of the project
  directory will be mounted relative to this path.

- **`auto_project_mount`** (default: `true`) (`--no-auto-project-mount`)
  Auto-mount project directory. Set to `false` or use CLI flag when you don't
  need any project mounts (volumes and subpaths still work).

- **`volumes`** (default: `[]`) (`-v, --volume`)
  Paths to mount into the container. Supports Docker volume syntax (`host:container`)
  or just a path to mount at the same location. Subpaths of the project directory
  will be mounted relative to the project target. See Volume Syntax below.

- **`subpaths`** (default: `[]`) (`-s, --subpath`)
  Mount only specific subpaths instead of the entire project directory. Using
  subpaths disables auto project mount, so only the specified subpaths are
  mounted. Must be inside the project directory. Supports volume options
  (e.g., `./src:ro`). Can be used multiple times.

- **`env`** (default: `[]`) (`--env`)
  Environment variables. `NAME=value` sets a value, `NAME` passes from host.

- **`sudo`** (default: `false`) (`--sudo`)
  Add user to sudoers with NOPASSWD inside container.

- **`tty`** (default: `auto`) (`--no-tty`)
  TTY allocation. `auto` detects from stdin.

- **`detach`** (default: `false`) (`-d, --detach`)
  Run container in background.

- **`post_start_commands`** (default: `[]`) (`--post-start-command`)
  Commands to run as root after container starts but before the main command executes.

- **`runtime`** (default: `docker`) (`--runtime`)
  Container runtime: `docker` or `podman` (rootless with `--userns=keep-id`).

- **`network`** (`--network`)
  Network mode: `bridge`, `none`, `host`, or custom network name.

- **`platform`** (`--platform`)
  Target platform: `linux/amd64` or `linux/arm64`.

- **`run_args`** (default: `[]`) (`--run-arg`)
  Extra arguments passed directly to `docker run`.

- **`labels`** (default: `{}`) (`--label`)
  Container labels in KEY=VALUE format.

- **`ulimits`** (config only)
  Resource limits, e.g., `{ nofile = 4096 }`.


### Build Options

Use `[containers.NAME.build]` to build images on-demand instead of pulling:

- **`dockerfile`** (default: `Dockerfile`) (`--build-dockerfile`)
  Path to Dockerfile.

- **`dockerfile_content`** (`--build-dockerfile-content`)
  Inline Dockerfile content. Mutually exclusive with `dockerfile`.

- **`context`** (default: `.`) (`--build-context`)
  Build context directory.

- **`tag`** (default: auto) (`--build-tag`)
  Image tag. Default template: `ctenv-{project_dir|slug}:latest`

- **`args`** (default: `{}`) (`--build-arg`)
  Build arguments in KEY=VALUE format.


### Volume Syntax

```toml
volumes = [
    "~/.gitconfig",              # Mount at same path
    "./data:/app/data",          # Host:Container
    "./src:/app/src:ro",         # Read-only
    "named-cache-volume:/cache:rw,chown",   # Fix ownership to user
]
```

Options: `ro` (read-only), `rw` (read-write), `chown` (fix ownership), `z` (SELinux, auto-added)

Path handling: `~/` expands to home, `./` is relative to config file (or cwd on CLI), absolute paths as-is.


### Template Variables

| Variable                       | Description |
|--------------------------------|-------------|
| `${container}`                 | Container name from config |
| `${image}`                     | Image name |
| `${user_name}`, `${user_home}` | Current user's name and home directory |
| `${project_dir}`               | Project root path |
| `${pid}`                       | Process ID |
| `${env.VAR}`                   | Environment variable value |

Filter: `${var|slug}` converts to filesystem-safe string (lowercase, `/` and `:` become `-`)


### Defaults & Merging

The `[defaults]` section applies to all containers:
- Scalars (image, command, sudo, etc.): container value overrides default
- Lists (env, volumes, run_args, etc.): concatenated (defaults + container)
- Dicts (labels, ulimits): merged (container keys override)


### Path handling

- Config file: Relative paths are relative to the file.
- Command line: Relative paths are relative to the current working directory.


### Example

```toml
[defaults]
network = "bridge"
env = ["TERM=xterm-256color"]

[containers.dev]
default = true
image = "python:3.11"
volumes = ["~/.gitconfig:ro", "./data:/app/data:rw,chown"]
env = ["DEBUG=1", "API_KEY"]
post_start_commands = ["pip install -r requirements.txt"]

[containers.builder]
sudo = true
run_args = ["--memory=4g"]

[containers.builder.build]
dockerfile = "Dockerfile.build"
tag = "myapp-builder:${user_name}"
args = { BASE_IMAGE = "ubuntu:22.04" }
```

```bash
$ ctenv run              # Uses 'dev' (default)
$ ctenv run builder -- make build
```

## Common Use Cases

### Build Systems
Use containerized build environments:
```toml
[containers.build-system]
image = "some-build-system:v17"
volumes = ["build-cache:/var/cache:rw,chown"]
```

### Development Tools
Run linters, formatters, or compilers from containers:
```bash
$ ctenv run --image rust:latest -- cargo fmt
$ ctenv run --image my-node-env -- eslint src/
```

### Claude Code
Run Claude Code in a container for isolation with configuration for convenient usage:

`~/.ctenv.toml`:
```
# Run Claude Code in container
[containers.claude]
volumes = ["~/.claude.json", "~/.claude/"]
command = "claude" # Run claude directly

# Builds an image so you don't have to reinstall every time
[containers.claude.build]
dockerfile_content = """
FROM node:20
RUN npm install -g @anthropic-ai/claude-code
"""
```

Then start with: `ctenv run claude`


## Detailed Examples

### Claude Code

Basic example:

```shell
$ ctenv run --image node:20 -v ~/.claude.json -v ~/.claude/ --post-start-command "npm install -g @anthropic-ai/claude-code" -- claude
```

That would install it every time you run it. To avoid that, we can use
ctenv to build an image with Claude Code:

```shell
$ ctenv run --build-dockerfile-content "FROM node:20\nRUN npm install -g @anthropic-ai/claude-code" -v ~/.claude.json -v ~/.claude/ -- claude
```

You likely want to configure this for conveniency:
```
# Run Claude Code in container
[containers.claude]
volumes = ["~/.claude.json", "~/.claude/"]
command = "claude" # Run claude directly

# Builds an image so you don't have to reinstall every time
[containers.claude.build]
dockerfile_content = """
FROM node:20
RUN npm install -g @anthropic-ai/claude-code
"""
```

If you have an existing image with a build environment already, use that and install Claude Code:
```toml
[containers.claude]
volumes = ["~/.claude.json", "~/.claude/"]
command = "claude"

[containers.claude.build]
dockerfile_content = """
FROM my-build-env:latest
RUN npm install -g @anthropic-ai/claude-code
"""
```
and run with: `ctenv run claude`

ctenv by default mounts the current directory as "workspace" and
switches to it, so it would start Claude Code in with the current
directory mounted in the container.

If you don't already have an image with your development tools in
(`node:20` doesn't include that much), you likely want to write a
`Dockerfile` and install more tools in it for Claude and you to use.
```
[containers.claude.build]
dockerfile = "Dockerfile" # instead of dockerfile_content
```

Can for example also use iptables to restrict network access:
```toml
[containers.claude]
# ...
network = "bridge"
run_args = ["--cap-add=NET_ADMIN"]
post_start_commands = [
    "iptables -A OUTPUT -d 192.168.0.0/24 -j DROP",
]
```

Note: On macOS, Claude Code stores credentials in the keychain by default. When run in a container, it will create `~/.claude/.credentials.json` instead, which persists outside the container due to the volume mount.

Note: There are also other tools for running Claude Code in a container, such as devcontainers: https://docs.anthropic.com/en/docs/claude-code/devcontainer



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

The background of _ctenv_ is that I developed bash script at work
([Agama](https://www.agama.tv/)) for running our build system in a
container. Besides running the build, it was useful to also be able to
run and use the compiled code in the build system environment, which
had older libraries than the modern OSes that was used by the
developers.

The idea for _ctenv_ came from the need for isolating agents like
Claude Code and I had a bunch of ideas for how to make it more
generally useful than what the script at work was, and without the
many hard-coded aspects of it.

_ctenv_ is written in Python and has flexible and convient command
line usage, and also config file support.
