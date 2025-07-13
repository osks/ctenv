---
id: task-9
title: Implement exec command (run in existing container or create new)
status: Future
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-13'
labels: []
dependencies: []
priority: high
---

## Description

Implement the 'exec' command that runs commands in an existing container, or creates a new one if it doesn't exist.

Key features:
- Check if named container is already running
- If running, execute command in existing container using 'docker exec'
- If not running, fall back to creating new container (same as 'run' command)
- Maintain same user identity and volume mounting behavior
- Support all the same CLI options as run command
- Handle TTY allocation properly for interactive commands

This command enables persistent development workflows where you start a container once and then run multiple commands in it, which is more efficient than creating new containers each time.
