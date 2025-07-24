---
id: task-33
title: Add default_container configuration support
status: To Do
assignee: []
created_date: '2025-07-23'
labels: []
dependencies: []
---

## Description

Add support for configuring a default container to use when no explicit container is specified on the command line. This improves user experience by allowing common workflows to be simplified.

## Problem

Currently, when no container is specified, ctenv uses the `[defaults]` section configuration. Users often want to use a specific pre-configured container by default without having to type it every time.

```bash
# Current: always need to specify container
ctenv run dev -- npm test
ctenv run dev -- npm start

# Desired: configure 'dev' as default, then just run
ctenv run -- npm test
ctenv run -- npm start
```

## Requirements

1. **Top-level `default_container` setting**: Add support for specifying default container in config files
   ```toml
   default_container = "dev"
   
   [defaults]
   image = "ubuntu:latest"
   
   [containers.dev]
   image = "node:18"
   volumes = ["~/.npm"]
   
   [containers.prod]
   image = "node:18-alpine"
   ```

2. **Container resolution priority**:
   - Explicit container (CLI argument) - highest priority
   - `default_container` setting - if no explicit container provided
   - `[defaults]` section - fallback if no default_container configured

3. **Error handling**: Clear error message if `default_container` refers to non-existent container

4. **Config file support**: Works in all config file types (user, project, explicit)

## Implementation Approach

**Config loading changes:**
- Extend config file parsing to read top-level `default_container` setting
- Store in `CtenvConfig` class for use during container resolution

**Container resolution changes:**
- Modify `resolve_container_config()` to check for `default_container` when no explicit container provided
- Maintain existing behavior when container is explicitly specified

**Example flow:**
```python
# When user runs: ctenv run -- command
if explicit_container:
    use_container = explicit_container
elif config.default_container:
    use_container = config.default_container
else:
    use_container = None  # Use [defaults] as before
```

## Benefits

- **Simplified commands**: Common workflows don't need container specified
- **Project-specific defaults**: Different projects can have different default containers
- **Backward compatible**: Existing behavior unchanged when `default_container` not configured
- **Clear precedence**: Explicit container always overrides default