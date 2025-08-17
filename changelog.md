# Changelog

<!-- https://keepachangelog.com/ -->

## [Unreleased]

## v0.7

### Added

- ctenv can now build images from a Dockerfile. Add a `build` section to your container configuration to automatically build images before running containers. Mutually exclusive with the `image` option. Example:
  ```toml
  [containers.dev]
  # ... container options ...
  build = { dockerfile = "Dockerfile.dev", context = "." }
  ```
  The TOML structure below can be easier to read if there are many options:
  ```toml
  [containers.api]
  # ... container options ...
  
  [containers.api.build]
  dockerfile = "Dockerfile.dev"
  context = "./image"
  tag = "my-api:latest"
  args = { NODE_ENV = "development", API_VERSION = "1.0" }
  ```
  The image will be built before the container is started. This allows using existing images, but also simple to add extra to them. For example using and existing image but adding Claude Code. The Dockerfile content can also be inlined:
  ```toml
  [containers.claude.build]
  dockerfile_content = """
  FROM node:20
  RUN npm install -g @anthropic-ai/claude-code
  """
  ```


## v0.6

### Changed

- There is now a command line argument for specifying the project dir:
  `ctenv --project-dir PATH run ...`. The default is that project dir
  is still that it's auto-detected by locating `.ctenv.toml`, starting
  from current dir and traversing upwards. Note: HOME is not
  considered a project dir, since it a `.ctenv.toml` there is not
  meant to indicate a project.

- Relative paths in config files are now resolved relative to the
  project dir, instead of the directory where the config file is
  in. This means you can have a config file with `workspace =
  ./:/repo` to mount `.` to `/repo` in the container, and it adapts to
  where you run ctenv. This is also more consistent with other tools.

- Container name now had PID as variable in the name, so one can start
  multiple container for the same project dir.


## v0.5

### Fixed

- Fix handling of relative volume path. `--volume ./foo` didn't work
  as expected, the container path was not made absolute so starting
  the container failed.

- Fixed passing of the `PS1` environment variable (`--env
  PS1=...`). The entrypoint script has `#!/bin/sh` which means the
  script is not executed as interactive, and then PS1 is not part of
  the environment in the script, and hence not in the command (say
  bash, for interactive use). Now we handle this as a special case.

- Fixed `--workspace auto` handling and several edge-cases.


### Changed

- Moved `--verbose` and `--quiet` to be global options. Now they need
  to be specified before the command (`ctenv --verbose run ...`).
  `ctenv run` now has `-v` as short for `--volume`. This means `-v`
  has different meaning before and after the command. Example: `ctenv
  -v run -v foo:/bar` means verbose and mount volume.

- Project root finding stops traversing at HOME and HOME is no longer
  considered a project root.


## v0.4

Improved config handling and removed lots of hard-coded options.


## v0.3

First release
