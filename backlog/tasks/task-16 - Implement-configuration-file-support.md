---
id: task-16
title: Implement configuration file support
status: Future
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-13'
labels: []
dependencies: []
priority: low
---

## Description

Add support for configuration files to set default options and avoid repetitive command-line arguments.

Key features:
- TOML - switch to requiring python 3.11 (update github actions also) instead of 3.9.
- Config file ctenv.toml in current directory (for now)
- Configuration precedence: CLI args > local config > defaults
- Support for all CLI options in config file format
- Environment variable expansion in config files
- --config flag to specify custom config file path
- --print-config command to show effective configuration
- Examples and documentation for common config patterns

This improves usability for projects with consistent container requirements and reduces command-line verbosity for complex setups.
