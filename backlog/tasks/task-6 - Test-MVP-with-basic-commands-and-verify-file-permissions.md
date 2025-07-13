---
id: task-6
title: Test MVP with basic commands and verify file permissions
status: To Do
assignee: []
created_date: '2025-07-13'
labels: []
dependencies: []
---

## Description

Thoroughly test the MVP implementation to ensure core functionality works correctly.

## Tasks

- [ ] Test basic command execution:
  - `ctenv run -- ls -la` (verify output and file permissions)
  - `ctenv run -- whoami` (verify user identity in container)
  - `ctenv run -- pwd` (verify working directory is `/repo`)
- [ ] Test interactive mode:
  - `ctenv run` (should start bash shell)
  - Verify PS1 prompt shows "[ctenv] $ "
  - Create files and verify ownership on host matches current user
- [ ] Test custom image option:
  - `ctenv run --image ubuntu:latest -- cat /etc/os-release`
  - Verify it works with different base images
- [ ] Test file permissions:
  - Create files in container: `ctenv run -- touch test-file`
  - Verify file ownership on host matches current user
  - Test writing to mounted directory from container
- [ ] Test error conditions:
  - Missing gosu binary
  - Invalid image name
  - Docker not available
- [ ] Write basic pytest tests:
  - Test Config class user detection
  - Test ContainerRunner argument building
  - Test entrypoint script generation
- [ ] Update README.md with MVP usage examples

## Acceptance Criteria

- All basic commands execute successfully
- File permissions are preserved correctly between host and container
- Interactive mode works with proper prompt
- Custom images work correctly
- Error conditions are handled gracefully
- Basic test suite passes
- Usage examples are documented
