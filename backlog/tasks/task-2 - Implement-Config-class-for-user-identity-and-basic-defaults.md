---
id: task-2
title: Implement Config class for user identity and basic defaults
status: To Do
assignee: []
created_date: '2025-07-13'
labels: []
dependencies: []
---

## Description

Create a Config class that handles user identity detection and basic container configuration.

## Tasks

- [ ] Import required modules: `pwd`, `grp`, `os`, `pathlib`
- [ ] Create Config class with `__init__` method
- [ ] Detect current user info using `pwd.getpwuid(os.getuid())`
- [ ] Detect current group info using `grp.getgrgid(os.getgid())`
- [ ] Set up basic defaults dictionary with:
  - Default container image
  - Current directory path
  - User/group names and IDs
  - Home directory path
  - Fixed paths for gosu and directory mounting
- [ ] Add method to generate container names based on directory path
- [ ] Add method to merge CLI options with defaults

## Acceptance Criteria

- Config class correctly detects current user identity
- Container names are consistently generated from directory paths
- Default image and paths are properly configured
- User/group IDs are correctly captured for passing to container
