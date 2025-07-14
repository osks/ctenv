---
id: task-13
title: Add support for Podman runtime via RUNNER environment variable
status: future
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-14'
labels: []
dependencies: []
priority: medium
---

## Description

Add support for Podman as an alternative container runtime to Docker.

Key features:
- Check RUNNER environment variable (default: 'docker')
- Support RUNNER=podman to use Podman instead of Docker
- Abstract container runtime operations in ContainerRunner class
- Ensure all commands work with both Docker and Podman
- Handle runtime-specific differences (command syntax, features)
- Add runtime detection and validation
- Update help text and documentation to mention Podman support
- Add tests for both Docker and Podman paths

This increases compatibility and gives users choice in container runtime, especially useful in environments where Podman is preferred (e.g., rootless containers, RHEL/Fedora systems).
