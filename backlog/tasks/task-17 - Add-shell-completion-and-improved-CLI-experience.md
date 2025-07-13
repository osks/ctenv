---
id: task-17
title: Add shell completion and improved CLI experience
status: Future
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-13'
labels: []
dependencies: []
priority: low
---

## Description

Improve the command-line user experience with shell completions and better help.

Key features:
- Generate shell completions for bash, zsh, fish
- Complete container names for exec/stop/status commands
- Complete image names from Docker registry
- Complete file paths for volume mounts
- Add more detailed help text with examples
- Implement 'ctenv --install-completion' command
- Add command aliases (e.g., 'ctenv r' for 'ctenv run')
- Improve error messages with suggestions
- Add --dry-run flag to show what would be executed

This makes ctenv more user-friendly and reduces typing for common operations.
