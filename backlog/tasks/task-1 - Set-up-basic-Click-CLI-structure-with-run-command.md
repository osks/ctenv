---
id: task-1
title: Set up basic Click CLI structure with run command
status: To Do
assignee: []
created_date: '2025-07-13'
labels: []
dependencies: []
---

## Description

Replace the current skeletal Click CLI in ctenv.py with a focused MVP structure.

## Tasks

- [ ] Remove placeholder command from current ctenv.py
- [ ] Set up main CLI group with version option
- [ ] Implement `run` command with these options:
  - `--image` for custom container image
  - Arguments for command to run (nargs=-1)
- [ ] Add basic error handling for missing arguments
- [ ] Ensure the CLI follows pattern: `ctenv run [--image IMAGE] [-- COMMAND]`

## Acceptance Criteria

- `ctenv run --help` shows proper usage
- `ctenv run` defaults to interactive bash
- `ctenv run -- ls` accepts commands after --
- `ctenv run --image ubuntu:latest -- whoami` accepts custom image
