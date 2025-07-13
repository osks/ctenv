---
id: task-3
title: Create ContainerRunner class with Docker support
status: To Do
assignee: []
created_date: '2025-07-13'
labels: []
dependencies: []
---

## Description

Create a ContainerRunner class that builds and executes Docker commands for running containers.

## Tasks

- [ ] Import `subprocess` and `sys` modules
- [ ] Create ContainerRunner class with Config dependency
- [ ] Implement `build_run_args()` method that creates Docker run arguments:
  - Basic flags: `--rm`, `--init`, platform specification
  - Volume mounts for current directory and gosu binary
  - Environment variables for user identity (CTENV_USER_*, etc.)
  - Working directory setup
  - Entrypoint configuration
- [ ] Implement `run_container()` method:
  - Combine all arguments into docker run command
  - Handle TTY detection (`-ti` flag if interactive)
  - Execute command with `subprocess.run()`
  - Pass through exit code
- [ ] Add basic error handling for Docker not found
- [ ] Ensure generated commands match expected Docker run format

## Acceptance Criteria

- Docker run commands are properly formatted
- User identity environment variables are correctly set
- Volume mounts include current directory and gosu binary
- TTY flags are added when running interactively
- Exit codes are properly passed through from container
- Error handling for missing Docker binary
