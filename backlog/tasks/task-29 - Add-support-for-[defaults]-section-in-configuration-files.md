---
id: task-29
title: 'Implement [defaults] section and update configuration hierarchy'
status: To Do
assignee: []
created_date: '2025-07-16'
labels: [enhancement, configuration]
dependencies: []
---

## Description

Add support for a `[defaults]` section in configuration files that provides user-customizable defaults. Project [defaults] completely override user [defaults]. When no context is specified, the [defaults] section is used directly. This creates a new layer in the configuration hierarchy between context values and built-in defaults, with project configs avoiding [defaults] sections in favor of explicit contexts.

## Overview

Configuration files are loaded from user (`~/.ctenv/ctenv.toml`) and project (searched upward from current directory for `.ctenv/ctenv.toml`) locations. Project configurations completely override user ones - no merging for [defaults] and [contexts.*] sections. However, file [defaults] merge with built-in defaults at the individual value level.

Project configs should avoid defining a [defaults] section.

```
Configuration Override Flow & Priority:

0. BUILTIN DEFAULTS (hardcoded):
   image="ubuntu:latest", network=None, sudo=False, etc.

1. FILE LOADING (override order):
   ~/.ctenv/ctenv.toml     → Load [defaults] and [contexts.*]
   ./.ctenv/ctenv.toml     → Project overrides global (complete replacement)
   
2. CONTEXT RESOLUTION:
   - Select context from CLI --context, or use [defaults] if no context specified

3. VALUE PRECEDENCE (highest to lowest):
   CLI args         → --image ubuntu:22.04
   ↓
   Context config   → [contexts.dev] image = "node:18"  (or [defaults] if no context)
   ↓
   File defaults    → [defaults] image = "ubuntu:20.04"  (project overrides user)
   ↓
   Builtin defaults → image = "ubuntu:latest"

4. VARIABLE SUBSTITUTION:
   - Apply template variables (${USER}, ${image|slug}, etc.) to final resolved values

Example:
   ~/.ctenv/ctenv.toml:    [defaults] network = "none", sudo = false
                           [contexts.dev] image = "ubuntu:22.04"
   
   ./.ctenv/ctenv.toml:    [defaults] sudo = true
                           [contexts.dev] image = "node:18", network = "bridge"
   
   Result for --context dev:
   - image: "node:18" (from project context - completely overrides user)
   - network: "bridge" (from project context)
   - sudo: true (from project defaults - completely overrides user)
```

## Requirements

### Configuration Structure
```toml
[defaults]
image = "ubuntu:22.04"
network = "bridge"
sudo = true
env = ["TERM", "HOME"]

[contexts.dev]
image = "node:18"
# Uses defaults for: network = "bridge", sudo = true, env = ["TERM", "HOME"]
```

### Override Behavior
- **Project [defaults]** completely replace user [defaults]
- **Project [contexts.*]** completely replace user [contexts.*]
- **File [defaults]** merge with built-in defaults per value
- **No context specified** → use [defaults] directly

## Testing Requirements

1. **[defaults] section parsing** and file loading
2. **Project override behavior** for both [defaults] and [contexts.*]
3. **No context fallback** - using [defaults] directly
4. **Value precedence** - CLI > context > defaults > builtin
5. **Variable substitution** on final resolved values

## Benefits

1. **User customization** - Set preferred defaults once
2. **Project consistency** - Override user defaults when needed
3. **Reduced repetition** - Common settings in [defaults]
4. **Clear precedence** - Predictable configuration resolution
5. **Backward compatible** - Existing configs continue to work

## Definition of Done

- [ ] `[defaults]` section parsing implemented
- [ ] Project override behavior for [defaults] and [contexts.*]
- [ ] No context specified → use [defaults] directly
- [ ] Value precedence: CLI > context > defaults > builtin
- [ ] Variable substitution on final resolved values
- [ ] Context listing shows source config file for each context
- [ ] All tests pass
- [ ] Existing functionality remains unchanged
