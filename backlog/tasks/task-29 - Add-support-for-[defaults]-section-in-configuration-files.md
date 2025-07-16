---
id: task-29
title: 'Add support for [defaults] section in configuration files'
status: To Do
assignee: []
created_date: '2025-07-16'
labels: [enhancement, configuration]
dependencies: []
---

## Description

Add support for a `[defaults]` section in configuration files that allows users to customize the default values that contexts fall back to. This doesn't change how contexts work (they already fall back to defaults when values aren't specified), but allows users to customize what those defaults are instead of being limited to hardcoded built-in defaults.

## Current Behavior vs. What's Being Added

### Today (Current)
Contexts **fall back to built-in defaults** when values aren't specified:
```toml
[contexts.dev]
image = "node:18"
# Falls back to built-in defaults: network = "none", sudo = false, etc.
```

### What We're Adding
Contexts will **fall back to user-defined defaults** (then built-in defaults):
```toml
[defaults]
network = "bridge"
sudo = true

[contexts.dev]
image = "node:18"
# Falls back to user defaults: network = "bridge", sudo = true
```

## Current Issue

The README mentions `[defaults]` sections but this feature was removed during configuration simplification. Currently, users cannot customize the base defaults without repeating them in every context - they're stuck with hardcoded built-in defaults.

## Requirements

### Configuration Structure
```toml
[defaults]
image = "ubuntu:22.04"
network = "bridge"
sudo = true
env = ["TERM", "HOME"]

[contexts.dev]
image = "node:18"
# Inherits: network = "bridge", sudo = true, env = ["TERM", "HOME"]

[contexts.prod]
# Inherits all defaults: image = "ubuntu:22.04", network = "bridge", etc.
```

### Precedence Rules (Fallback Chain)
When resolving a configuration value, the system should check in this order:
1. **CLI options** (highest priority) - if specified, use this value
2. **Context configuration** - if specified in context, use this value  
3. **User-defined defaults** (`[defaults]` section) - if specified in defaults, use this value
4. **Built-in defaults** (lowest priority) - hardcoded fallback values

This maintains the existing fallback behavior but adds customizable user defaults in the chain.

### Multi-level Defaults
Project-specific defaults should override user config defaults:
- **Global config** (`~/.ctenv/config.toml`) `[defaults]` section
- **Project config** (`.ctenv/config.toml`) `[defaults]` section overrides global
- **Context** configuration inherits from applicable defaults

## Implementation

### 1. Update ConfigFile Class
Modify `ConfigFile.load()` to extract and merge `[defaults]` sections:

```python
@classmethod
def load(cls, explicit_config_file: Optional[Path] = None, start_dir: Optional[Path] = None) -> "ConfigFile":
    # Start with built-in defaults
    merged_defaults = get_builtin_defaults()
    
    # Load global config defaults
    if global_config_path:
        global_config = load_config_file(global_config_path)
        if "defaults" in global_config:
            merged_defaults.update(global_config["defaults"])
    
    # Load project config defaults (overrides global)
    if project_config_path:
        project_config = load_config_file(project_config_path)
        if "defaults" in project_config:
            merged_defaults.update(project_config["defaults"])
    
    # Apply defaults to contexts
    for context_name, context_data in contexts.items():
        resolved_context = merged_defaults.copy()
        resolved_context.update(context_data)
        contexts[context_name] = resolved_context
```

### 2. Update resolve_context()
Modify context resolution to use merged defaults:

```python
def resolve_context(self, context: str) -> Dict[str, Any]:
    if context not in self.contexts:
        available = list(self.contexts.keys())
        raise ValueError(f"Unknown context '{context}'. Available: {available}")
    
    # Context already includes merged defaults from load()
    context_data = self.contexts[context].copy()
    
    # Apply templating
    variables = {
        "USER": getpass.getuser(),
        "image": context_data.get("image", ""),
    }
    
    return substitute_in_context(context_data, variables)
```

### 3. Update ContainerConfig.from_cli_options()
Ensure CLI options still override everything:

```python
@classmethod
def from_cli_options(cls, context: Optional[str] = None, **cli_options) -> "ContainerConfig":
    # Load file config (now includes merged defaults)
    config_file_obj = ConfigFile.load(...)
    file_config = config_file_obj.resolve_context(context or "default")
    
    # CLI options override file config (including defaults)
    def get_config_value(key: str, cli_key: str = None, default=None):
        cli_key = cli_key or key
        cli_value = cli_options.get(cli_key)
        if cli_value is not None:
            return cli_value
        # file_config now includes merged defaults
        return file_config.get(key, default)
```

## Example Usage

### Global Configuration (~/.ctenv/config.toml)
```toml
[defaults]
image = "ubuntu:22.04"
network = "none"
sudo = false
env = ["TERM", "HOME", "USER"]

[contexts.dev]
image = "node:18"
network = "bridge"
# Inherits: sudo = false, env = ["TERM", "HOME", "USER"]
```

### Project Configuration (.ctenv/config.toml)
```toml
[defaults]
# Override global defaults
sudo = true
env = ["TERM", "HOME", "USER", "PATH"]

[contexts.test]
image = "alpine:latest"
# Inherits: sudo = true, env = ["TERM", "HOME", "USER", "PATH"]
# Plus global: network = "none" (not overridden)
```

### Result
When running `ctenv run test`:
- `image = "alpine:latest"` (from context)
- `sudo = true` (from project defaults)
- `network = "none"` (from global defaults)
- `env = ["TERM", "HOME", "USER", "PATH"]` (from project defaults)

## Testing Requirements

1. **Unit tests** for defaults merging logic
2. **Integration tests** for multi-level configuration
3. **Precedence tests** to ensure correct override behavior
4. **Template variable tests** with defaults
5. **CLI override tests** to ensure CLI still wins

## Documentation Updates

1. Update README with `[defaults]` section examples
2. Add configuration precedence documentation
3. Update example configurations
4. Add migration guide for users with repeated context settings

## Benefits

1. **Reduce repetition** - Set common defaults once
2. **Easier customization** - Users can set their preferred defaults
3. **Consistent behavior** - All contexts inherit same base settings
4. **Flexible override** - Project configs can override user configs
5. **Backward compatible** - Existing contexts without defaults continue to work

## Definition of Done

- [ ] `[defaults]` section parsing implemented
- [ ] Multi-level defaults merging (global → project) 
- [ ] Context values fall back to user-defined defaults (then built-in defaults)
- [ ] CLI option precedence maintained
- [ ] Template variable substitution works with defaults
- [ ] Unit tests for all defaults functionality
- [ ] Integration tests for multi-level configs
- [ ] Documentation updated with examples
- [ ] Existing functionality remains unchanged
