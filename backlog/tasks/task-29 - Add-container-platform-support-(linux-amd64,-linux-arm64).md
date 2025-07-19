---
id: task-29
title: 'Add container platform support (linux/amd64, linux/arm64)'
status: To Do
assignee: []
created_date: '2025-07-19'
labels: [enhancement, docker, architecture]
dependencies: []
---

## Description

Add support for specifying container platform architecture when running containers. Users should be able to run containers with `--platform linux/amd64` or `--platform linux/arm64` using Docker's standard platform notation.

## Implementation Requirements

### 1. CLI Support
- Add `--platform` argument to `run` command
- Support Docker platform format: `linux/amd64`, `linux/arm64`
- Default to host platform if not specified

### 2. Container Runtime Integration
- Pass `--platform` flag to docker/podman run commands
- Handle platform-specific container creation

### 3. Gosu Binary Selection
- Select correct gosu binary based on target platform (not host platform)
- Map platform to gosu filename:
  - `linux/amd64` → `gosu-amd64`
  - `linux/arm64` → `gosu-arm64`
- Update entrypoint script to use platform-specific gosu

### 4. Configuration Support
- Add `platform` field to `ContainerConfig` dataclass
- Allow platform specification in TOML config files
- Override hierarchy: CLI → config → host detection

```toml
# .ctenv.toml
platform = "linux/amd64"
```

## Implementation Notes

- Gosu binaries are already downloaded for both architectures
- Platform detection should default to host architecture
- Validate platform values against supported architectures
- Update container creation logic in `ContainerRunner`

## Example Usage
```bash
ctenv run --platform linux/amd64 ubuntu:22.04
ctenv run --platform linux/arm64 -- python script.py
```
