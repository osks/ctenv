---
id: task-34
title: Rename 'context' to 'container' throughout codebase for clarity
status: To Do
assignee: []
created_date: '2025-07-23'
labels: []
dependencies: []
---

## Description

The term "context" is currently used throughout the codebase to refer to named container configurations. This is confusing because "context" is an overloaded term in software. Renaming to "container" would make the purpose clearer - these are predefined container configurations.

## Impact Analysis

### 1. Configuration File Format
- **Breaking change**: `[contexts.*]` sections → `[containers.*]`
- `default_context` field → `default_container`
- Affects: example/ctenv.toml, user config files

### 2. CLI Interface
- **Breaking change**: Position argument `context` → `container`
- Commands affected: `ctenv run <context>`, `ctenv config show <context>`
- Help text updates needed

### 3. Code Changes Required

**Core implementation (ctenv/cli.py):**
- Classes: `contexts` field in `SingleConfigFile`, `CtenvConfig`
- Functions: `substitute_in_context()` → `substitute_in_container()`
- Methods: `find_context()` → `find_container()`
- ~50+ variable name changes
- Error messages and logging statements

**Test files:**
- test_cli_parsing.py
- test_config.py
- test_ctenv.py
- test_unknown_config.py
- Test function names, test data, assertions

**Documentation:**
- README.md examples
- Backlog task files referencing contexts
- Inline comments and docstrings

### 4. Estimated Scope
- **Files affected**: ~15 files
- **Lines to change**: ~300+ lines
- **Breaking changes**: Yes - config file format and CLI args

### 5. Migration Strategy
- **No backward compatibility** - clean break
- Direct rename without supporting old format
- Update all references in one go
- No version bump needed (pre-release)

## Implementation Notes
- Use search and replace carefully - "context" appears in other contexts (pun intended)
- Ensure all error messages are updated for clarity
- Update bash completion if implemented
