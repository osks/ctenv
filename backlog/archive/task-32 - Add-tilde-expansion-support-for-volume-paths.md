---
id: task-32
title: Add volume path expansion and smart defaulting
status: Done
assignee: []
created_date: '2025-07-23'
labels: []
dependencies: []
---

## Description

Improve volume path ergonomics by adding smart target defaulting and consistent path expansion between CLI and configuration files. Currently, CLI and config files have different expansion capabilities, making them incompatible.

## Problem

**Inconsistent expansion capabilities:**
- **CLI**: Shell expands `~` (unquoted), no template expansion  
- **Config**: Template expansion `${env:HOME}`, no `~` expansion

This makes it impossible to use the same volume specification in both contexts:

```bash
# CLI: works (shell expands ~)
ctenv run -v ~/.docker:/home/user/.docker

# CLI: doesn't work (no template expansion)  
ctenv run -v "${env:HOME}/.docker:/home/user/.docker"
```

```toml  
# Config: works (has template expansion)
volumes = ["${env:HOME}/.docker:/home/user/.docker"]

# Config: doesn't work (no ~ expansion)
volumes = ["~/.docker:/home/user/.docker"]
```

**Verbose target paths:** Given ctenv's user identity preservation, specifying full home paths in targets is repetitive and user-specific.

## Requirements

1. **Smart target defaulting**: Single path implies same source and target
   ```bash
   ctenv run -v ~/.docker              # → ~/.docker:~/.docker  
   ctenv run -v /host/path             # → /host/path:/host/path
   ```

2. **Empty target syntax with options**: Support `::` separator for options without explicit target
   ```bash
   ctenv run -v ~/.docker::ro          # → ~/.docker:~/.docker:ro
   ctenv run -v /path::chown,rw        # → /path:/path:chown,rw
   ```

3. **Unified expansion support**:
   - **Config files**: Add `~` → `${env:HOME}` preprocessing (keeping existing `${env:HOME}` support)
   - **CLI args**: Add template expansion so `"${env:HOME}/.docker"` works

4. **Cross-platform compatibility**: Handle expansion on all supported platforms

## Implementation Approach

**Leverage existing template system** (ctenv/cli.py:43-84):
- Preprocessor: Convert `~` → `${env:HOME}` before existing template processing
- Add template expansion to CLI volume parsing
- Extend volume parsing to handle single-path and `::` syntax

**Volume parsing logic:**
```python
# Current: "~/.docker:/container/path:ro"
# Enhanced: 
#   "~/.docker" → "~/.docker:~/.docker" 
#   "~/.docker::ro" → "~/.docker:~/.docker:ro"
#   "~/.docker:/other:ro" → "~/.docker:/other:ro" (unchanged)
```

## Benefits

- **Consistency**: Same volume specs work in both CLI and config
- **Ergonomics**: Shorter syntax for common use cases (`~/.docker` vs `~/.docker:~/.docker`)  
- **Familiar**: Uses standard `~` and `${env:HOME}` patterns developers expect
- **Backward compatible**: Existing volume specifications continue to work
- **Leverages existing infrastructure**: Builds on proven template system
