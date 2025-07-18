---
id: task-24
title: Add volume chown option support
status: Done
assignee: []
created_date: '2025-07-15'
updated_date: '2025-07-15'
labels:
  - enhancement
dependencies: []
---

## Description

Add support for `:chown` option in volume mount strings to automatically fix ownership of mounted volumes to the container user. This provides a clean way to handle permission issues with Docker volumes.

## Requirements

### Syntax
Extend existing volume syntax to support chown option:
```toml
[contexts.bitbake]
volumes = [
    "bitbake-caches-user-${USER}:/var/cache/bitbake:rw,chown",
    "data-volume:/data:chown"
]
```

### Behavior
- Parse `:chown` option from volume mount strings
- During container startup (in entrypoint script), run `chown -R ${USER_ID}:${GROUP_ID}` on mount points marked with chown
- Works with both named volumes and bind mounts
- Similar to Podman's `:U` option but implemented generically

### Implementation
1. **Parse volume options** in `ContainerRunner.build_run_args()`
2. **Track chown volumes** and pass list to entrypoint
3. **Add chown logic** to entrypoint script after user creation
4. **Support existing options** like `:ro`, `:rw`, `:z`, `:Z` alongside `:chown`

## Example Usage

```toml
[contexts.bitbake]
volumes = ["cache-${USER}:/var/cache:rw,chown"]
```

Results in:
- Volume mounted normally to container
- After user creation: `chown -R user:group /var/cache`
- User can write to cache directory without permission issues
