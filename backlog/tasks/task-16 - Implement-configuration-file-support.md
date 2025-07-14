---
id: task-16
title: Implement configuration file support with git-style discovery
status: todo
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-14'
labels: []
dependencies: []
priority: medium
---

## Description

Add support for configuration files with git-style directory traversal, allowing project-specific configurations that can be discovered from subdirectories.

## Configuration Discovery Strategy

### File Locations (in order of precedence)
1. **CLI override**: `--config path/to/config.toml`
2. **Project config**: `.ctenv/config.toml` (found via upward traversal)
3. **Global config**: `~/.ctenv/config.toml`
4. **System defaults**: Built-in defaults

### Directory Structure
```
project-root/
├── .ctenv/
│   ├── config.toml          # Project configuration
│   └── contexts/            # Future: context-specific configs
│       ├── dev.toml
│       └── test.toml
├── src/
│   └── subdir/              # ctenv works from here too
└── docs/
```

### Discovery Algorithm (Git-style)
1. Start from current working directory
2. Look for `.ctenv/config.toml`
3. If not found, move to parent directory
4. Repeat until found or reach filesystem root
5. Fall back to `~/.ctenv/config.toml` if no project config found

## Configuration Format (TOML)

### Basic Project Config (`.ctenv/config.toml`)
```toml
# Default settings for this project (used when no context specified)
[defaults]
image = "node:18"
network = "bridge"
sudo = true
env = ["NODE_ENV=development"]
volumes = ["./node_modules:/app/node_modules"]

# Project-specific contexts
[contexts.dev]
image = "node:18"
network = "bridge"
sudo = true
env = ["NODE_ENV=development", "DEBUG=*"]

[contexts.test]
image = "node:18-alpine"
network = "none"
sudo = false
env = ["NODE_ENV=test", "CI=true"]
command = "npm test"

[contexts.prod]
image = "node:18-alpine"
network = "none"
sudo = false
env = ["NODE_ENV=production"]
command = "npm start"
```

### Global Config (`~/.ctenv/config.toml`)
```toml
# Global defaults across all projects
[defaults]
image = "ubuntu:latest"
network = "none"
sudo = false

# Global contexts available everywhere
[contexts.debug]
network = "bridge"
sudo = true
env = ["DEBUG=1"]

[contexts.minimal]
image = "alpine:latest"
network = "none"
sudo = false
```

## Key Features

- **Git-style traversal**: Works from any subdirectory in a project
- **Project isolation**: Each project has its own configuration
- **Global fallback**: User-wide defaults in `~/.ctenv/config.toml`
- **Context support**: Multiple named configurations per project
- **Python 3.11+ requirement**: Use built-in TOML support
- **Environment expansion**: Support `${VAR}` substitution
- **Validation**: Comprehensive config validation with helpful errors

## Command Line Integration

```bash
# Use project config from any subdirectory
cd project-root/src/deep/subdir
ctenv run        # Uses [defaults] from ../../../.ctenv/config.toml
ctenv run dev    # Uses [contexts.dev] from config
ctenv run test   # Uses [contexts.test] from config

# Override config file
ctenv run dev --config ./custom.toml

# Show effective configuration
ctenv config show
ctenv config show dev

# Show config discovery path
ctenv config path  # Shows which config file is being used
```

### Configuration Resolution Examples

#### Example 1: No context specified
```bash
ctenv run  # Uses [defaults] from project config, falls back to global [defaults]
```

#### Example 2: Context specified
```bash
ctenv run dev  # Uses [contexts.dev], falls back to [defaults] for missing keys
```

#### Example 3: Context with CLI override
```bash
ctenv run dev --image alpine:latest  # Uses dev context but overrides image
```

#### Example 4: Context with command
```bash
ctenv run test -- npm test     # Uses test context, runs npm test
ctenv run dev -- bash          # Uses dev context, runs bash
ctenv run prod -- npm start    # Uses prod context, runs npm start
```

## Implementation Requirements

### Python Version
- **Upgrade to Python 3.11+**: Use built-in `tomllib` module
- **Update GitHub Actions**: Change matrix to support 3.11, 3.12, 3.13
- **Update pyproject.toml**: `requires-python = ">=3.11"`

### Config Discovery
- Implement `find_config_file()` function with upward traversal
- Cache discovered config path for performance not needed, use stat() only and rely on filesystem caching.
- Handle edge cases (filesystem boundaries, permissions)

### Configuration Precedence
1. CLI arguments (highest)
2. Selected context from project config
3. `[defaults]` section from project config (`.ctenv/config.toml` via traversal)
4. Selected context from global config
5. `[defaults]` section from global config (`~/.ctenv/config.toml`)
6. Built-in defaults (lowest)

### Error Handling
- Clear messages when config files have syntax errors
- Helpful suggestions for common configuration mistakes
- Show config discovery path in verbose mode

## Benefits

- **Project-centric**: Each project can have its own container requirements
- **Developer-friendly**: Works from any directory within a project
- **Team consistency**: Shared project configs ensure consistent environments
- **Personal customization**: Global configs for user preferences
- **Familiar pattern**: Git-style discovery is intuitive for developers
- **Scalable**: Supports both simple and complex project setups

## Acceptance Criteria

- [ ] Upgrade Python requirement to 3.11+ and update CI
- [ ] Implement git-style config discovery with upward traversal
- [ ] Support both project (`.ctenv/config.toml`) and global (`~/.ctenv/config.toml`) configs
- [ ] Implement proper configuration precedence
- [ ] Add TOML parsing with comprehensive error handling
- [ ] Support environment variable expansion in config values
- [ ] Add `ctenv config` commands for introspection
- [ ] Add `--config` CLI option to override discovery
- [ ] Update `ctenv run` to accept optional context as positional argument
- [ ] Implement context support within configuration files
- [ ] Add comprehensive tests for config discovery and precedence
- [ ] Update documentation with configuration examples
- [ ] Ensure backward compatibility with projects without configs

### Command Structure

```bash
# Basic usage
ctenv run [CONTEXT] [OPTIONS] [-- COMMAND...]

# Examples
ctenv run                           # Use defaults
ctenv run dev                       # Use dev context
ctenv run test --image alpine       # Use test context, override image
ctenv run prod -- npm start         # Use prod context, run npm start
```

### CLI Implementation Notes

- Context name is an optional positional argument to `ctenv run`
- Must handle ambiguity between context names and command arguments
- Context names should be validated (alphanumeric, hyphens, underscores)
- Helpful error messages for unknown contexts

## Future Enhancements

- **Context-specific files**: `contexts/dev.toml`, `contexts/test.toml`
- **Config inheritance**: Contexts extending base configurations
- **Schema validation**: JSON Schema or similar for config validation
- **Config generation**: `ctenv config init` to create template configs
- **Context aliases**: Short names for frequently used contexts
