---
id: task-8
title: 'Add missing CLI options to run command (--env, --volume, --sudo, --network)'
status: todo
assignee: []
created_date: '2025-07-13'
labels: []
dependencies: []
priority: high
---

## Description

Implement the missing command-line options for the run command to match ctenv.sh functionality:

- --env NAME=VALUE: Set environment variable in container
- --env NAME: Pass environment variable from host to container  
- --volume HOST:CONTAINER: Mount additional volumes beyond the default repo mount
- --sudo: Add user to sudoers with NOPASSWD inside container
- --network: Enable container networking (default is disabled for security)
- --dir PATH: Custom directory to mount as workdir (currently hardcoded to current directory)

These options are essential for practical development workflows and bring our implementation closer to feature parity with the original shell script.
