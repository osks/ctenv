---
id: task-4
title: Implement embedded bash entrypoint script generation
status: To Do
assignee: []
created_date: '2025-07-13'
labels: []
dependencies: []
---

## Description

Implement the embedded bash script approach for container entrypoint (Option 2 from complete-plan.md).

## Tasks

- [ ] Create `build_entrypoint_script()` function that generates bash script
- [ ] Script should handle group creation/detection:
  - Check if group with target GID exists
  - Use existing group or create new one with target name/GID
- [ ] Script should handle user creation:
  - Check if user with target name exists
  - Create user with correct UID, GID, home directory if missing
- [ ] Script should set up home directory:
  - Create home directory if it doesn't exist
  - Set proper ownership (UID:GID)
- [ ] Script should set environment:
  - Export HOME variable
  - Set PS1 prompt to "[ctenv] $ "
- [ ] Script should execute final command:
  - Use `exec /gosu USER_NAME COMMAND` to drop privileges and run command
- [ ] Add script to ContainerRunner's docker arguments:
  - Set `--entrypoint /bin/sh`
  - Pass script via `-c` argument
- [ ] Handle shell escaping for special characters in script

## Acceptance Criteria

- Generated bash script properly creates users/groups
- Script correctly sets up home directory and permissions
- Final command execution drops privileges using gosu
- Script is properly escaped when passed to Docker
- Container starts with correct user identity
