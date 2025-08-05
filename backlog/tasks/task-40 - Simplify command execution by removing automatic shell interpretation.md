---
id: task-40
title: Add flexible shell support to direct command execution
status: To Do
priority: Medium
assignee: 
created: 2025-08-04
updated: 2025-08-04
tags: [execution, shell, enhancement, configuration]
---

# Task 40 - Add flexible shell support to direct command execution

## Background

During PS1 work, we removed automatic shell interpretation and switched to direct execution. However, this broke existing functionality.

**Current state:**
- Direct execution: `exec "$GOSU_MOUNT" "$USER_NAME" $COMMAND`
- **Problem**: Commands like `ctenv run -- sh -c "echo hello | grep h"` fail due to quoting issues
- **Root cause**: `$COMMAND` is a quoted string that can't be properly word-split for direct execution

**Key insight**: Direct execution works for simple commands but fails for shell commands that were originally parsed and quoted as strings.

## Problem Analysis

**Direct execution limitations:**
- ❌ `ctenv run -- sh -c "complex command"` fails (quoting issues)
- ❌ No shell features (pipes, variables, etc.)
- ❌ Only string command format in config
- ✅ Simple commands work: `ctenv run -- echo hello`

**Specific failing case from tests:**
```bash
# Command line that fails:
ctenv run --post-start-command "echo 'first command'" \
          --post-start-command "echo 'second command'" \
          --post-start-command "touch /tmp/marker_file" \
          -- sh -c "echo 'Commands completed' && ls -la /tmp/marker_file"

# This gets parsed as array: ["sh", "-c", "echo 'Commands completed' && ls -la /tmp/marker_file"]
# Problem: Even though "sh -c" is explicitly specified, the command gets 
# converted to a string like: sh -c "echo 'Commands completed' && ls -la /tmp/marker_file"
# When executed as: exec "$GOSU_MOUNT" "$USER_NAME" $COMMAND
# The nested quotes and shell operators can't be properly parsed by direct execution
```

**Root cause clarification:** The issue isn't that we can't run "echo" directly, but that even when explicitly using "sh -c", the command array gets converted to a quoted string that can't be properly word-split for direct execution. The shell quoting/parsing happens at the wrong layer.

**Need solution that:**
1. Supports both direct execution (simple/fast) and shell execution (complex commands)
2. Gives users explicit control over execution mode
3. Handles both string and array command formats
4. Maintains security by avoiding automatic shell interpretation

## Solution

**Add `--shell` flag for explicit shell execution:**

```bash
# Direct (default): ctenv run -- echo hello  
exec "$GOSU_MOUNT" "$USER_NAME" $COMMAND_ARGS

# Shell mode: ctenv run --shell bash -- echo \$HOME
exec "$GOSU_MOUNT" "$USER_NAME" bash -c "$COMMAND_STRING"
```

**Config enhancements:**
```toml
# String format (parsed with shlex.split)
command = "python -m pytest"

# Array format  
command = ["python", "-m", "pytest"]

# Optional shell
shell = "bash"  # Use shell mode for this container
```

**Key features:**
- `--shell ""` forces direct execution (override config)
- Support both string/array command formats
- Shell detection for interactive features (PS1, etc.)

**Examples:**
```bash
# Direct (current): ctenv run -- echo hello
# Shell: ctenv run --shell bash -- echo hello | grep h  
# Config: command = ["echo", "hello"] or "echo hello"
```

## Implementation

**Immediate need:** Fix current broken test by implementing basic shell detection or reverting to shell execution temporarily.

**Full implementation phases:**
1. Add `--shell` CLI option and `shell` config field
2. Support both string (via `shlex.split()`) and array command formats  
3. Implement dual execution modes in entrypoint script
4. Update tests and documentation

**Technical challenges:**
- Passing command arrays to bash script
- Handling both string/array config formats  
- Dual execution modes in entrypoint script

## Final Implementation Decision

**Reverted to shell execution for simplicity and reliability:**

We initially attempted direct execution (`exec "$GOSU_MOUNT" "$USER_NAME" $COMMAND`) to avoid shell interpretation complexity, but this broke existing functionality due to shell quoting issues with complex commands.

**Final approach:**
- **Shell execution**: `exec "$GOSU_MOUNT" "$USER_NAME" /bin/sh $INTERACTIVE -c "$COMMAND"`
- **TTY-aware interactive mode**: Use `/bin/sh -i` when TTY detected, regular `/bin/sh` otherwise
- **Variable for optional flag**: `INTERACTIVE="-i"` or `""` to avoid shell quoting issues

**Benefits of this approach:**
- ✅ Handles complex shell commands properly (including `sh -c` with nested quotes)
- ✅ Supports PS1 and interactive features when TTY is available
- ✅ Maintains compatibility with existing functionality
- ✅ Simple implementation without complex parsing logic

**Trade-offs accepted:**
- Commands are always interpreted by shell (security consideration for untrusted input)
- Slightly more overhead than direct execution
- Shell-specific behavior (but consistent with original implementation)

This resolves the immediate blocking issues while maintaining full functionality. The more complex `--shell` flag approach remains available for future enhancement if explicit control over execution mode becomes necessary.

**Key insight about PS1 complexity:** PS1 is difficult to set up due to multiple interacting factors:

1. **Interactive shell requirement**: PS1 only works in interactive shells (`/bin/sh -i`), not non-interactive shells
2. **Post-start command isolation**: Post-start commands run in subshells, so `export PS1="value"` in post-start commands doesn't affect the main environment (this is good for security/isolation)  
3. **Shell startup file conflicts**: Even when PS1 is passed via `--env`, shells like bash may override it during initialization by reading ~/.bashrc
4. **Direct execution limitations**: With direct execution (`exec ... $COMMAND`), there's no shell layer to preserve environment variables

**Result**: Setting PS1 requires careful coordination of TTY detection, interactive shell mode, and bypassing shell startup files (e.g., `bash --norc`) - making it much more complex than a simple environment variable.