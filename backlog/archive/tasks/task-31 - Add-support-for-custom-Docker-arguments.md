---
id: task-31
title: Add support for custom Docker arguments
status: Done
assignee: []
created_date: '2025-07-19'
labels: []
dependencies: []
---

## Description

Add support for passing custom arguments directly to the container runtime (Docker/Podman) run command, enabling users to specify additional options like `--memory`, `--cpus`, `--security-opt`, etc.

## Requirements

### CLI Interface
- Add `--run-arg` option that can be used multiple times  
- Arguments should be passed directly to container runtime without validation
- Support in both Python implementation and eventually shell script

### Implementation Details
- **Option name**: `--run-arg` (container-runtime agnostic, matches "run" command)
- **Type**: `action="append"` to allow multiple arguments
- **Injection point**: After core Docker arguments but before image specification
- **Config support**: Allow specifying in TOML configuration files

### Example Usage
```bash
# Memory and CPU limits
ctenv run --run-arg="--memory=2g" --run-arg="--cpus=2" -- my-command

# Security options
ctenv run --run-arg="--security-opt=seccomp=unconfined" dev -- build-script

# Capabilities
ctenv run --run-arg="--cap-add=SYS_PTRACE" debug -- gdb my-program
```

### TOML Configuration Support
```toml
[contexts.dev]
image = "ubuntu:latest"
run_args = ["--memory=2g", "--cpus=2"]
```

## Implementation Tasks

1. **Python Implementation**:
   - Add `--run-arg` to CLI parser in `create_parser()`
   - Extend `ContainerConfig` dataclass with `run_args` field
   - Modify `ContainerRunner.build_run_args()` to inject custom arguments
   - Add configuration file parsing support

2. **Testing**:
   - Unit tests for argument parsing and injection
   - Integration tests with actual Docker commands
   - Test configuration file support

3. **Documentation**:
   - Update help text and examples
   - Document security considerations and user responsibility

## Notes

- No argument validation needed - container runtime will reject invalid arguments
- Arguments should be logged in verbose mode for debugging  
- User responsible for understanding container runtime argument implications
- Must maintain compatibility with existing argument structure
