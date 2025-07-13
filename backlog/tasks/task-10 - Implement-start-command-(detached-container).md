---
id: task-10
title: Implement start command (detached container)
status: Future
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-13'
labels: []
dependencies: []
priority: high
---

## Description

Implement the 'start' command that creates a long-running detached container for persistent development sessions.

Key features:
- Create container in detached mode (--detach flag)
- Run with a long-lived command (like 'sleep infinity' or 'tail -f /dev/null')
- Apply all standard ctenv setup (user creation, volume mounts, etc.)
- Use consistent container naming so other commands can find it
- Check if container already exists and handle appropriately
- Support same CLI options as run command for consistency
- Provide feedback about container creation and name

This enables workflows where developers start a persistent container once and then use 'exec' to run multiple commands in it, which is much more efficient for iterative development.
