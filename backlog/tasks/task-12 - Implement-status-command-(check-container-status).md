---
id: task-12
title: Implement status command (check container status)
status: Future
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-13'
labels: []
dependencies: []
priority: high
---

## Description

Implement the 'status' command that displays information about the current container.

Key features:
- Show whether the named container exists and is running
- Display container ID, image, creation time, and uptime
- Show port mappings and volume mounts
- Display resource usage (CPU, memory) if available
- Use clear, human-readable output format
- Handle case where no container exists gracefully
- Support --json flag for machine-readable output
- Show container logs tail with --logs flag

This provides visibility into the container state and helps users understand what's running and troubleshoot issues.
