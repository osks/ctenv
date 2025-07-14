---
id: task-20
title: Implement configuration contexts for different settings
status: todo
assignee: []
created_date: '2025-07-14'
updated_date: '2025-07-14'
labels: []
dependencies: [task-16]
priority: low
---

## Description

**Note**: This task is now largely covered by the updated task-16 (configuration file support), which includes integrated context support. This task focuses on advanced context features and refinements.

Implement advanced configuration context features that build upon the basic context support in task-16.

## Motivation

Different development scenarios often require different container configurations:
- **Development**: Interactive shell with full networking and sudo access
- **Testing**: Isolated environment with specific test image and volumes
- **Production**: Minimal configuration with security restrictions
- **CI/CD**: Automated builds with specific environment variables and volumes

Currently, users must specify all options via command line each time, which is verbose and error-prone.

## Proposed Behavior

### Advanced Context Features (builds on task-16)

Task-16 provides basic context support within `.ctenv/config.toml`. This task adds:

#### Context Inheritance
```toml
[contexts.base]
image = "node:18"
network = "none"
sudo = false

[contexts.dev]
extends = "base"  # Inherit from base
network = "bridge"
sudo = true
env = ["NODE_ENV=development"]

[contexts.test]
extends = "dev"   # Inherit from dev, override specific settings
env = ["NODE_ENV=test", "CI=true"]
command = "npm test"
```

#### Separate Context Files
```
.ctenv/
├── config.toml           # Base configuration
└── contexts/
    ├── dev.toml         # Development context
    ├── test.toml        # Testing context
    └── prod.toml        # Production context
```

### Command Line Usage

```bash
# Use default context
ctenv run

# Use specific context (positional argument)
ctenv run dev
ctenv run test
ctenv run prod

# Override context settings with CLI options
ctenv run dev --image alpine:latest  # Uses dev context but different image

# Context with command
ctenv run test -- npm test
ctenv run dev -- bash

# List available contexts
ctenv contexts

# Show context configuration
ctenv contexts show dev
```

## Implementation Details

### Config File Structure
- Contexts are defined under `[contexts.CONTEXT_NAME]` sections
- `default` context is used when no `--context` flag is provided
- Each context can define any configuration option available via CLI
- CLI options override context settings (highest precedence)

### Context Resolution Order
1. **CLI arguments**: Highest precedence
2. **Selected context**: Via `--context` flag
3. **Default context**: From config file
4. **System defaults**: Hardcoded defaults

### New CLI Options
- `ctenv run [CONTEXT]`: Select configuration context as positional argument
- `ctenv contexts`: List available contexts
- `ctenv contexts show CONTEXT`: Show context configuration

### Config Class Updates
- Add `context` parameter to `Config.from_cli_options()`
- Add `load_context_from_file()` method
- Update precedence logic to incorporate context settings
- Add validation for context names and settings

## Benefits

- **Reduced verbosity**: No need to repeat common option combinations
- **Environment-specific configs**: Easy switching between dev/test/prod setups
- **Team consistency**: Shared contexts ensure consistent environments
- **Discoverability**: `ctenv contexts` shows available configurations
- **Flexibility**: CLI options can still override context settings

## Example Use Cases

### Development Team Setup
```toml
[contexts.default]
image = "ubuntu:22.04"
network = "bridge"
sudo = true

[contexts.node]
image = "node:18"
network = "bridge"
sudo = true
env = ["NODE_ENV=development"]
volumes = ["./node_modules:/app/node_modules"]

[contexts.python]
image = "python:3.11"
network = "bridge"
sudo = true
env = ["PYTHONPATH=/app"]
volumes = ["./.venv:/app/.venv"]
```

### CI/CD Pipeline
```toml
[contexts.build]
image = "node:18-alpine"
network = "none"
sudo = false
env = ["NODE_ENV=production", "CI=true"]
command = "npm run build"

[contexts.test]
image = "node:18-alpine"
network = "none"
sudo = false
env = ["NODE_ENV=test", "CI=true"]
command = "npm test"
```

## Acceptance Criteria

**Note**: Basic context functionality is covered in task-16. This task adds:

- [ ] Implement context inheritance with `extends` keyword
- [ ] Support separate context files in `.ctenv/contexts/` directory
- [ ] Add advanced context validation (circular dependencies, etc.)
- [ ] Implement context templates and scaffolding
- [ ] Add context-specific environment file loading (`.ctenv/contexts/dev.env`)
- [ ] Support conditional contexts based on environment variables
- [ ] Add context composition (multiple inheritance)
- [ ] Implement context linting and validation tools
- [ ] Add context migration tools for config updates
- [ ] Support dynamic context generation based on git branch
- [ ] Add integration with external config sources (environment-specific)
- [ ] Implement context documentation generation

## Related Tasks

- **Depends on**: task-16 (configuration file support)
- **Enhances**: All CLI options become configurable per context
- **Future**: Could enable context-specific aliases or shortcuts

## Technical Considerations

- Context names should be validated (no special characters, reasonable length)
- Invalid context references should provide helpful error messages
- Context inheritance could be added later (`[contexts.dev-extended] extends = "dev"`)
- Consider caching parsed contexts for performance
- Verbose mode should show which context is being used
