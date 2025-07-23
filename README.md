# ctenv

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
- Configurable contexts for reusable container setups

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

```
ctenv run --image "node:20" --post-start-command "npm install -g @anthropic-ai/claude-code"
```

To not have to login everytime and to keep history, we can mount Claude Code's files:

```
ctenv run --image "node:20" \
          --post-start-command "npm install -g @anthropic-ai/claude-code" \
          --volume "~/.claude.json:~/.claude.json" \
          --volume "~/.claude:~/.claude"
```



Note: On macOS Claude Code seem to store credentials in the keychain
if you have a Claude account. The credentials therefor won't be
available in the container. However, if you login in Claude Code in
the container, it will write credentials to
`~/.claude/.credentials.json` instead and continue to use them from
there. Since the above mounts that directory, be aware that the
credentials file will then exist outside the container in a file now,
instead of the keychain.



Example config:
```toml
[contexts.claude]
image = "node:20"
network = "bridge"
run_args = ["--cap-add=NET_ADMIN"]
post_start_commands = [
    "apt update && apt install -y iptables",
    "iptables -A OUTPUT -d 192.168.0.0/24 -j DROP",
    "npm install -g @anthropic-ai/claude-code"
]
volumes = ["${env:HOME}/.claude.json:${env:HOME}/.claude.json", "${env:HOME}/.claude:${env:HOME}/.claude"]
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
[contexts.build]
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
ctenv run --network bridge       # Specify network
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
network = "none"
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

