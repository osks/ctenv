---
id: task-26
title: Add ulimit configuration support
status: Done
assignee: []
created_date: '2025-07-15'
updated_date: '2025-07-15'
labels:
  - enhancement
dependencies: []
---

## Description

Add support for configuring ulimits (resource limits) for containers. This is needed for certain build systems like bitbake that require specific file descriptor limits.

## Requirements

### Configuration
```toml
[contexts.bitbake]
ulimits = { nofile = 1024, nproc = 2048 }
```

### Docker Integration
- Convert to Docker `--ulimit` flags during container creation
- Support common ulimit types: `nofile`, `nproc`, `core`, `fsize`, etc.
- Use same format as Docker CLI

### Implementation
1. **Add ulimits field** to `ContainerConfig` dataclass
2. **Parse from context** configuration 
3. **Generate --ulimit flags** in `ContainerRunner.build_run_args()`

## Example Usage

### Bitbake File Descriptor Limit
```toml
[contexts.bitbake]
image = "builder:latest"
ulimits = { nofile = 1024 }
```

Generates: `docker run --ulimit=nofile=1024 ...`

### Multiple Limits
```toml
[contexts.development]
ulimits = { 
    nofile = 2048,
    nproc = 1024,
    core = 0
}
```

Generates: `docker run --ulimit=nofile=2048 --ulimit=nproc=1024 --ulimit=core=0 ...`

## Implementation Notes

- Simple dictionary-to-flags conversion
- Validate ulimit names against known types
- Support both hard and soft limits if needed: `{ nofile = "1024:2048" }`
- About 10-15 lines of code addition
