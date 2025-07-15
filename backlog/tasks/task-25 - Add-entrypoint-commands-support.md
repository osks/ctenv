---
id: task-25
title: Add entrypoint commands support
status: To Do
assignee: []
created_date: '2025-07-15'
updated_date: '2025-07-15'
labels: [enhancement]
dependencies: []
---

## Description

Add support for running custom commands in the container entrypoint before executing the main command. This enables setup tasks like activating virtual environments, creating directories, or other initialization.

## Requirements

### Configuration
```toml
[contexts.bitbake]
entrypoint_commands = [
    "source /bitbake-venv/bin/activate",
    "mkdir -p /var/cache/bitbake/subdirs",
    "echo 'Container initialized'"
]
```

### Execution Order
1. Container starts with ctenv entrypoint
2. User and group creation
3. Volume chown operations (if enabled)
4. **Execute entrypoint_commands** (as root, before gosu)
5. Switch to user with gosu
6. Execute main command

### Command Context
- Commands run as **root** (before gosu switch)
- Full access to system resources for setup tasks
- Environment variables available (including template-substituted ones)
- Can modify filesystem, install packages, etc.

## Example Use Cases

### Virtual Environment Activation
```toml
entrypoint_commands = ["source /bitbake-venv/bin/activate"]
```

### Directory Setup
```toml
entrypoint_commands = [
    "mkdir -p /var/cache/custom/dirs",
    "chmod 755 /var/cache/custom"
]
```

### Package Installation
```toml
entrypoint_commands = ["yum install -y git"]
```

## Implementation Notes

- Add `entrypoint_commands` field to context configuration
- Execute commands in sequence in entrypoint script
- Fail container startup if any command fails (exit non-zero)
- Log command execution in verbose mode
- Keep simple - just execute shell commands as-is