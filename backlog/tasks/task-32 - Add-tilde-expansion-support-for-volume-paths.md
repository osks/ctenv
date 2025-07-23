---
id: task-32
title: Add tilde expansion support for volume paths
status: To Do
assignee: []
created_date: '2025-07-23'
labels: []
dependencies: []
---

## Description

Add support for expanding `~` (tilde) in volume paths within configuration files. While unquoted CLI arguments work fine (shell handles expansion), configuration files need application-level tilde expansion since the shell never processes their contents.

## Problem

Shell expansion handles tilde correctly for unquoted CLI arguments:

```bash
# This works - shell expands ~ before passing to ctenv
ctenv run --volume ~/.claude.json:/home/oskar/.claude.json -- command

# This is expected behavior - quotes prevent shell expansion
ctenv run --volume "~/.claude.json:/home/oskar/.claude.json" -- command
```

However, tilde expansion fails in configuration files where the shell doesn't perform expansion:

```toml
# This doesn't work - ~ is passed literally
volumes = ["~/.config:/home/user/.config"]
```

## Requirements

1. **Smart target defaulting**: Single path implies same source and target
   - CLI: `-v ~/.docker` → `~/.docker:~/.docker`  
   - Config: `volumes = ["~/.docker"]` → same behavior
   
2. **Empty target syntax with options**: Support `::` for options without explicit target
   - CLI: `-v ~/.docker::ro` → `~/.docker:~/.docker:ro`
   - CLI: `-v /path::opts` → `/path:/path:opts`

3. **Consistent expansion between CLI and config**: 
   - **Config files**: Support both `~` and `${env:HOME}` expansion
   - **CLI args**: Support `${env:HOME}` template expansion (currently missing)
   
4. **Cross-platform Support**: Handle expansion appropriately across different operating systems

5. **Security**: Ensure expansion only applies to user's own home directory

## Implementation Notes

- **Configuration Files**: Must implement application-level tilde expansion since shell never processes config file contents
- Could integrate with existing environment variable expansion by treating `~` as `$HOME`
- Consider using `os.path.expanduser()` in Python for reliable cross-platform expansion
- May need to handle cases where `$HOME` is not set or user has no home directory
- Should preserve original behavior for paths that don't start with `~`

## Analysis of Current Template System

ctenv already has a robust template variable substitution system that could naturally support tilde expansion:

**Current Template System (ctenv/cli.py:43-84):**
- Uses `${var}` and `${var|filter}` syntax
- Supports `${env:VAR}` for environment variables (e.g., `${env:HOME}`)
- Applied to all string values in contexts via `substitute_in_context()`
- Template resolution happens just before container execution via `config.resolve_templates()`

**Natural Integration Approach:**
Instead of special-casing `~` expansion, leverage the existing `${env:HOME}` capability:

1. **For developers**: Document that `${env:HOME}` can be used in config files:
   ```toml
   volumes = ["${env:HOME}/.config:/home/user/.config"]
   ```

2. **Enhanced approach**: Add automatic `~` -> `${env:HOME}` preprocessing in config loading
   - Convert `~/.config` to `${env:HOME}/.config` before template processing
   - Maintains consistency with existing system
   - Provides familiar `~` syntax while using robust env expansion

**Advantages:**
- Reuses existing, tested template infrastructure
- No new expansion logic needed
- Cross-platform compatible (leverages existing env variable handling)
- Consistent with ctenv's variable substitution patterns
- Handles edge cases like missing `$HOME` through existing error handling

**Developer Experience:**
- Familiar `~` syntax works as expected: `volumes = ["~/.docker:/root/.docker"]`
- Power users can use explicit `${env:HOME}` for clarity
- Both approaches resolve to the same reliable expansion mechanism

## Refined Scope: Consistency and Ergonomics

The key insight is that the current system has inconsistency between CLI and config capabilities:

**Current State:**
- **CLI**: Shell expands `~` (unquoted), no template expansion
- **Config**: Template expansion `${env:HOME}`, no `~` expansion

**Proposed Unified Approach:**

1. **Smart target defaulting** (both CLI and config):
   ```bash
   ctenv run -v ~/.docker        # → ~/.docker:~/.docker
   ctenv run -v ~/.docker::ro    # → ~/.docker:~/.docker:ro
   ```
   ```toml
   volumes = ["~/.docker", "${env:HOME}/.cache"]  # → same smart defaulting
   ```

2. **Consistent expansion everywhere**:
   - **Config files**: Support both `~` → `${env:HOME}` preprocessing AND existing `${env:HOME}`
   - **CLI args**: Add template expansion support so `--volume "${env:HOME}/.docker"` works

3. **Empty target syntax**: Support `::` separator for options without explicit target
   - Avoids confusion between paths and options
   - Enables concise syntax with options: `-v ~/.docker::ro,chown`

**Core Issue**: Currently impossible to use same volume specification in both CLI and config due to different expansion capabilities. This change makes them fully interchangeable.
