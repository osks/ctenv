---
id: task-5
title: 'Add basic volume mounting (current dir to /repo, gosu binary)'
status: To Do
assignee: []
created_date: '2025-07-13'
labels: []
dependencies: []
---

## Description

Implement volume mounting functionality to mount the current directory and gosu binary into containers.

## Tasks

- [ ] Add volume mount for current directory:
  - Mount current working directory to `/repo` in container
  - Use read-write permissions
  - Add `z` SELinux label if on SELinux systems
- [ ] Add volume mount for gosu binary:
  - Mount local `./gosu` file to `/gosu` in container
  - Use read-only permissions
  - Ensure gosu binary is executable in container
- [ ] Set working directory in container to `/repo`
- [ ] Verify gosu binary exists before attempting to mount
- [ ] Add error handling for missing gosu binary
- [ ] Ensure volume mounts are properly formatted for Docker
- [ ] Test that mounted files have correct permissions

## Acceptance Criteria

- Current directory is accessible at `/repo` in container
- Files created in container have correct ownership on host
- gosu binary is available and executable at `/gosu` in container
- Working directory is set to `/repo` by default
- Clear error message if gosu binary is missing
- Volume mount syntax is correct for Docker
