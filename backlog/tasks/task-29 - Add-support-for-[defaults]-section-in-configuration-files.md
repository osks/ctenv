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

## Overview

```
Configuration Merge Flow & Priority:

0. BUILTIN DEFAULTS (hardcoded):
   ContainerConfig.get_defaults() → image="ubuntu:latest", network=None, sudo=False, etc.

1. FILE LOADING (merge order):
   ~/.ctenv/ctenv.toml     → Load [defaults] and [contexts.*]
   ./.ctenv/ctenv.toml     → Override with project [defaults] and [contexts.*]
   
2. CONTEXT RESOLUTION:
   - Select context from CLI --context
   - Apply variable substitution (${USER}, ${image|slug}, etc.)

3. VALUE PRECEDENCE (highest to lowest):
   CLI args         → --image ubuntu:22.04
   ↓
   Context config   → [contexts.dev] image = "node:18"
   ↓
   File defaults    → [defaults] image = "ubuntu:20.04"  (merged: global → project)
   ↓
   Builtin defaults → ContainerConfig.get_defaults() → image = "ubuntu:latest"

Example:
   ~/.ctenv/ctenv.toml:    [defaults] network = "none"
   ./.ctenv/ctenv.toml:    [defaults] sudo = true
                           [contexts.dev] image = "node:18"
   
   Result for --context dev:
   - image: "node:18" (from context)
   - network: "none" (from global defaults)
   - sudo: true (from project defaults)
```

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
4. **Built-in defaults** (lowest priority) - hardcoded fallback values from `ContainerConfig.get_defaults()`

This maintains the existing fallback behavior but adds customizable user defaults in the chain.

### Multi-level Defaults
Project-specific defaults should override user config defaults:
- **Global config** (`~/.ctenv/config.toml`) `[defaults]` section
- **Project config** (`.ctenv/config.toml`) `[defaults]` section overrides global
- **Context** configuration inherits from applicable defaults

## Design

### Approach: User-Defined Defaults Layer
Instead of changing how contexts work, we'll add a new layer in the configuration hierarchy. The `[defaults]` section will provide user-customizable defaults that sit between context values and built-in defaults in the precedence chain.

### Key Design Decisions:
1. **Keep the current "default" context** - It remains as a regular context that users can override
2. **[defaults] is not a context** - It's a separate configuration layer
3. **Explicit is better** - Contexts don't automatically inherit defaults; the merge happens during config resolution
4. **Multi-level defaults** - Project defaults override global defaults

## Implementation

### 1. Update ConfigFile Class
Add a `defaults` field to store user-defined defaults separately from contexts:

```python
@dataclass
class ConfigFile:
    """Represents file-based configuration with contexts and defaults."""
    contexts: Dict[str, Dict[str, Any]]
    defaults: Dict[str, Any]  # NEW: User-defined defaults
    source_files: list[Path]

    @classmethod
    def load(cls, explicit_config_file: Optional[Path] = None, start_dir: Optional[Path] = None) -> "ConfigFile":
        """Load configuration from files with user-defined defaults."""
        merged_contexts = {}
        merged_defaults = {}  # NEW: Track user defaults separately
        source_files = []

        if explicit_config_file:
            # Use only the explicit config file
            if not explicit_config_file.exists():
                raise ValueError(f"Config file not found: {explicit_config_file}")
            user_config = load_config_file(explicit_config_file)
            merged_contexts.update(user_config.get("contexts", {}))
            merged_defaults.update(user_config.get("defaults", {}))  # NEW: Extract defaults
            source_files = [explicit_config_file]
        else:
            # Auto-discover and merge global and project config files
            global_config_path, project_config_path = find_all_config_files(start_dir)

            # Load global config
            if global_config_path:
                global_config = load_config_file(global_config_path)
                merged_contexts.update(global_config.get("contexts", {}))
                merged_defaults.update(global_config.get("defaults", {}))  # NEW
                source_files.append(global_config_path)

            # Overlay project config (contexts and defaults with same keys override)
            if project_config_path:
                project_config = load_config_file(project_config_path)
                merged_contexts.update(project_config.get("contexts", {}))
                merged_defaults.update(project_config.get("defaults", {}))  # NEW
                source_files.append(project_config_path)

        # Ensure builtin default context is available (user can override)
        builtin_default = get_builtin_default_context()
        if "default" in merged_contexts:
            # Merge user default with builtin (user takes precedence)
            final_default = builtin_default.copy()
            final_default.update(merged_contexts["default"])
            merged_contexts["default"] = final_default
        else:
            merged_contexts["default"] = builtin_default

        return cls(contexts=merged_contexts, defaults=merged_defaults, source_files=source_files)
```

### 2. Update ContainerConfig.create()
Modify the precedence logic to include user-defined defaults:

```python
@classmethod
def create(cls, context: Optional[str] = None, config_file: Optional[str] = None, **cli_options) -> "ContainerConfig":
    """Create ContainerConfig from CLI options, config files, and system defaults."""
    # Load file-based configuration
    try:
        explicit_config = Path(config_file) if config_file else None
        config_file_obj = ConfigFile.load(explicit_config_file=explicit_config)
    except Exception as e:
        raise ValueError(str(e)) from e

    # Resolve config values with context
    if not context:
        context = "default"
    file_config = config_file_obj.resolve_context(context)

    # Get default configuration values
    builtin_defaults = cls.get_defaults()
    user_defaults = config_file_obj.defaults  # NEW: Get user-defined defaults

    # Helper function with updated precedence: CLI > context > user defaults > builtin defaults
    def get_config_value(key: str, cli_key: str = None, default_value=None):
        cli_key = cli_key or key
        
        # 1. CLI options (highest priority)
        cli_value = cli_options.get(cli_key)
        if cli_value is not None:
            return cli_value
            
        # 2. Context configuration
        file_value = file_config.get(key)
        if file_value is not None:
            return file_value
            
        # 3. User-defined defaults (NEW)
        user_default = user_defaults.get(key)
        if user_default is not None:
            return user_default
            
        # 4. Built-in defaults or provided default
        if default_value is not None:
            return default_value
        return getattr(builtin_defaults, key, None)

    # Helper function to merge list values with defaults consideration
    def get_merged_list_value(key: str, cli_key: str = None):
        cli_key = cli_key or key
        
        # Start with user defaults if available, otherwise builtin defaults
        user_default_list = user_defaults.get(key)
        if user_default_list is not None:
            base_list = list(user_default_list)
        else:
            base_list = list(getattr(builtin_defaults, key, []))
        
        # Override with context values if specified
        file_value = file_config.get(key)
        if file_value is not None:
            base_list = list(file_value)
        
        # Add CLI values if provided
        cli_value = cli_options.get(cli_key)
        if cli_value:
            base_list.extend(cli_value)
        
        return base_list

    # Rest of the create() method remains the same...
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
