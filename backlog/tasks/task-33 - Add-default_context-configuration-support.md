---
id: task-33
title: Add default_context configuration support
status: To Do
assignee: []
created_date: '2025-07-23'
labels: []
dependencies: []
---

## Description

Add support for configuring a default context to use when no explicit context is specified on the command line. This improves user experience by allowing common workflows to be simplified.

## Problem

Currently, when no context is specified, ctenv uses the `[defaults]` section configuration. Users often want to use a specific pre-configured context by default without having to type it every time.

```bash
# Current: always need to specify context
ctenv run dev -- npm test
ctenv run dev -- npm start

# Desired: configure 'dev' as default, then just run
ctenv run -- npm test
ctenv run -- npm start
```

## Requirements

1. **Top-level `default_context` setting**: Add support for specifying default context in config files
   ```toml
   default_context = "dev"
   
   [defaults]
   image = "ubuntu:latest"
   
   [contexts.dev]
   image = "node:18"
   volumes = ["~/.npm"]
   
   [contexts.prod]
   image = "node:18-alpine"
   ```

2. **Context resolution priority**:
   - Explicit context (CLI argument) - highest priority
   - `default_context` setting - if no explicit context provided
   - `[defaults]` section - fallback if no default_context configured

3. **Error handling**: Clear error message if `default_context` refers to non-existent context

4. **Config file support**: Works in all config file types (user, project, explicit)

## Implementation Approach

**Config loading changes:**
- Extend config file parsing to read top-level `default_context` setting
- Store in `CtenvConfig` class for use during context resolution

**Context resolution changes:**
- Modify `resolve_container_config()` to check for `default_context` when no explicit context provided
- Maintain existing behavior when context is explicitly specified

**Example flow:**
```python
# When user runs: ctenv run -- command
if explicit_context:
    use_context = explicit_context
elif config.default_context:
    use_context = config.default_context
else:
    use_context = None  # Use [defaults] as before
```

## Benefits

- **Simplified commands**: Common workflows don't need context specified
- **Project-specific defaults**: Different projects can have different default contexts
- **Backward compatible**: Existing behavior unchanged when `default_context` not configured
- **Clear precedence**: Explicit context always overrides default