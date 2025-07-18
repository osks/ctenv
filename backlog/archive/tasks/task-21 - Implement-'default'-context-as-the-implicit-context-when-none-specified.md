---
id: task-21
title: Implement 'default' context as the implicit context when none specified
status: Done
assignee: []
created_date: '2025-07-14'
updated_date: '2025-07-14'
labels: []
dependencies: []
---

## Description

Simplify the configuration system by treating everything as contexts. When no context is specified, use a predefined "default" context instead of raw config defaults.

## Goal

Make the system more consistent by ensuring all operations use contexts, eliminating special-case handling for "no context" scenarios.

## Current Behavior
- `ctenv run` uses raw config defaults (no context)
- `ctenv run dev` uses "dev" context with config defaults as base
- Context resolution: `Config defaults → [Context OR nothing] → CLI options`

## Proposed Behavior  
- `ctenv run` uses "default" context (implicitly)
- `ctenv run dev` uses "dev" context with config defaults as base
- Context resolution: `Config defaults → Context (always) → CLI options`
- All contexts (including "default") inherit from config defaults, not from each other

## ✅ Decisions Made

### Q1: What should the builtin "default" context contain?
**DECISION:** Minimal - only `image = "ubuntu:latest"`

### Q2: Should builtin "default" context appear in `ctenv contexts` output?
**DECISION:** Yes, show it in both `contexts` and `config` output for discoverability.

### Q3: How should user-defined "default" context interact with builtin?
**DECISION:** Context merging - contexts with same names should merge at the option level. Each individual option can be overridden.

Example:
- Builtin "default": `{ image = "ubuntu:latest" }`
- Global ~/.ctenv/config.toml "default": `{ image = "alpine:latest", sudo = true }`  
- Project .ctenv/config.toml "default": `{ network = "bridge" }`
- **Final "default"**: `{ image = "alpine:latest", sudo = true, network = "bridge" }`

This means users can selectively override just the image in their HOME config while keeping other builtin defaults.

### Q4: Should context validation change?
**DECISION:** Keep current validation - `ctenv run foo` fails if "foo" context doesn't exist. Don't fall back to "default".

## Implementation Tasks

1. **Define builtin "default" context**
   - Add minimal builtin "default" context: `{ image = "ubuntu:latest" }`
   - Inject during config loading, before user configs are merged
   - Ensure it merges properly with user-defined "default" contexts (option-level merging)

2. **Update CLI parsing in `run()` command**
   - Change `context = None` default to `context = "default"`
   - Remove special case handling

3. **Update `resolve_config_values()`**
   - Remove `context is None` branches  
   - Always expect a context name

4. **Update context validation**
   - Ensure "default" is always available
   - Keep validation for other contexts

5. **Update `contexts` command**
   - Always show "default" context in output
   - Show merged "default" (builtin + user overrides)

6. **Update documentation and help text**
   - Update examples to reflect that everything uses contexts
   - Clarify that "default" is used when no context specified

7. **Update tests**
   - Test builtin "default" context behavior
   - Test option-level merging of "default" context (builtin + global + project)
   - Test that "default" appears in `contexts` and `config show` output
   - Ensure existing functionality works unchanged

## Architecture Notes

The hierarchy should be:
```
Config defaults → Context (either "default" or user-specified) → CLI options
```

The builtin "default" context should be injected during config loading, before user configs are merged, so it can be merged naturally at the option level.

**Context merging hierarchy for "default":**
1. Start with builtin "default": `{ image = "ubuntu:latest" }`
2. Merge with global ~/.ctenv/config.toml "default" (if exists)
3. Merge with project .ctenv/config.toml "default" (if exists)
4. Each level can override individual options without replacing the entire context

## Backward Compatibility
This should be fully backward compatible:
- `ctenv run` behavior unchanged (still uses same defaults, just via "default" context)
- `ctenv run dev` behavior unchanged  
- User configs continue to work the same way

## Benefits
- **Consistency:** Everything uses contexts, no special cases
- **Simplicity:** Cleaner code with fewer conditional branches  
- **Discoverability:** Users can see and override the "default" context
- **Maintainability:** Single code path for context resolution
