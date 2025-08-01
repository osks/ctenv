---
id: task-37
title: Dict-based config system refactoring
status: Done
assignee: []
created_date: '2025-07-31'
updated_date: '2025-08-01'
labels: []
dependencies: []
priority: high
---

## Description

Refactor the configuration system to use raw dicts throughout the loading/merging process, with ContainerSpec representing fully resolved, ready-to-run specifications (replacing the current ContainerConfig).

## Current Problems

1. **Early parsing**: ContainerConfig objects created too early, before all merging/resolution is complete
2. **Mixed states**: ContainerConfig represents both raw config file data and resolved runtime data
3. **Complex resolution**: Multiple resolve methods with unclear timing and dependencies
4. **Type confusion**: Optional fields used for both "not specified" and "actually optional"

## Target Architecture

```
Config Files → Raw Dicts → Merged Dict → parse_container_config() → ContainerSpec
                  ↓                              ↓
    config_resolve_relative_paths()      RuntimeContext + Variable substitution
                                                ↓
                                        Fully resolved, ready-to-execute
```

**Key distinction:**
- **Raw dicts**: Represent configuration as stored in files (unresolved paths, template variables, "auto" values)
- **RuntimeContext**: Runtime context (user info, cwd, tty) - separate from configuration
- **ContainerSpec**: Represents a fully resolved, validated, ready-to-execute container specification

**Note:** The existing ContainerSpec class will be removed/replaced as part of this refactoring.

## Key Design Decision: Runtime Context vs Configuration

**Problem:** Some data isn't really configuration - it's runtime context:
- User identity (user_name, user_id, etc.)
- Current working directory (_cwd)

**Solution:** Remove runtime context from configuration entirely. Instead:

1. **Remove from builtin defaults** - get_builtin_defaults() no longer includes user fields or _cwd
2. **Gather in cmd_run()** - Get runtime context once at CLI entry point
3. **Pass to ContainerSpec.create()** - Explicit parameters, no hidden side effects
4. **Naming:** RuntimeContext dataclass containing user info and cwd

**Updated signatures:**
```python
@dataclass  
class RuntimeContext:
    """Runtime context for container execution."""
    user_name: str
    user_id: int
    user_home: str
    group_name: str
    group_id: int
    cwd: Path
    
    @classmethod
    def current(cls) -> "RuntimeContext":
        """Get current runtime context."""
        user_info = pwd.getpwuid(os.getuid())
        group_info = grp.getgrgid(os.getgid())
        return cls(
            user_name=user_info.pw_name,
            user_id=user_info.pw_uid,
            user_home=user_info.pw_dir,
            group_name=group_info.gr_name,
            group_id=group_info.gr_gid,
            cwd=Path.cwd()
        )

# In ContainerSpec
@classmethod
def create(cls, config_dict: Dict[str, Any], context: RuntimeContext) -> "ContainerSpec":
    """Create ContainerSpec from config dict and runtime context."""
    # Use context.user_home for tilde expansion
    # Use context.cwd for resolving relative paths and "auto" workspace
    # Use all context fields for final ContainerSpec
```

**Benefits:**
- Cleaner separation: configuration vs runtime context
- Configs are more portable (no hardcoded paths or user info)
- Runtime context is always fresh from system
- Easier to test (can pass mock context)

## Implementation Plan

### 1. Update Data Structures

#### ConfigFile Changes
```python
@dataclass
class ConfigFile:
    containers: Dict[str, Dict[str, Any]]  # Raw dicts instead of ContainerConfig
    defaults: Optional[Dict[str, Any]]     # Raw dict instead of ContainerConfig
    path: Optional[Path]
```

#### CtenvConfig Changes
```python
@dataclass 
class CtenvConfig:
    defaults: Dict[str, Any]                    # Raw dict (merged system + file defaults)
    containers: Dict[str, Dict[str, Any]]       # Raw dicts from all files
```

#### Remove Current ContainerConfig
- Current ContainerConfig class will be removed
- Current ContainerSpec class will be removed

#### New ContainerSpec
- Represents fully resolved, ready-to-execute container specification
- All required fields are non-Optional
- Contains VolumeSpec objects instead of strings
- Has `create()` method that does full resolution

### 2. Update config_resolve_relative_paths

**Current signature:**
```python
def config_resolve_relative_paths(config: ContainerConfig, base_dir: Path) -> ContainerConfig
```

**New signature:**
```python
def config_resolve_relative_paths(config_dict: Dict[str, Any], base_dir: Path) -> Dict[str, Any]
```

**Changes:**
- Parse volume specs from strings when needed
- Process workspace, volumes, gosu_path fields in the dict
- Return modified dict instead of ContainerConfig

### 3. Update ConfigFile.load()

**Changes:**
- Remove ContainerConfig.from_dict() calls  
- Remove config_resolve_relative_paths() calls on ContainerConfig objects
- Add config_resolve_relative_paths() calls on raw dicts
- Store raw dicts in ConfigFile

**Example:**
```python
# OLD
defaults_config = ContainerConfig.from_dict(raw_defaults)
defaults_config = config_resolve_relative_paths(defaults_config, config_dir)

# NEW  
defaults_dict = config_resolve_relative_paths(raw_defaults, config_dir)
```

### 4. Update CtenvConfig.load()

**Changes:**
- Work with raw dicts throughout
- defaults and containers fields store raw dicts
- No ContainerConfig creation during loading

### 5. Update CtenvConfig.get_container_config()

**Current flow:**
1. Merge dicts
2. Create ContainerConfig from merged dict
3. Return unresolved ContainerConfig

**New flow:**
1. Merge dicts (same as current)
2. Return merged dict
3. Caller uses ContainerSpec.create() to parse and resolve

**Method signature change:**
```python
# OLD
def get_container_config(self, container: Optional[str] = None, 
                        cli_overrides: Optional[ContainerConfig] = None) -> ContainerConfig

# NEW  
def get_container_config(self, container: Optional[str] = None,
                        cli_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]
```

**Usage pattern:**
```python
# Get merged config dict
config_dict = ctenv_config.get_container_config(container="dev", cli_overrides=cli_dict)

# Parse and resolve to ContainerSpec
spec = ContainerSpec.create(config_dict, context)
```

**Method signatures:**
```python
@classmethod
def create(cls, config_dict: Dict[str, Any], context: RuntimeContext) -> "ContainerSpec":
    """Create ContainerSpec from config dict and runtime context.
    
    Args:
        config_dict: Merged configuration dictionary
        context: Runtime context (user info and cwd)
    """
    # Use context.user_home for tilde expansion
    # Use context.cwd for resolving relative paths and "auto" workspace
    # Use all context fields for final ContainerSpec
```

**Usage in cmd_run():**
```python
def cmd_run(args, command):
    # Get runtime context once at the start
    context = RuntimeContext.current()
    
    # ... load config ...
    
    # Get merged config dict
    config_dict = ctenv_config.get_container_config(container="dev", cli_overrides=cli_dict)
    
    # Parse and resolve to ContainerSpec with runtime context
    spec = ContainerSpec.create(config_dict, context)
    
    # spec now has:
    # - user info from context (user_name, user_id, etc.)
    # - workspace resolved using context.cwd for "auto" detection
    # - relative paths resolved relative to context.cwd
```

### 6. Define New ContainerSpec

**Field Requirements Analysis:**

**Always required (non-Optional):**
```python
@dataclass
class ContainerSpec:
    # User identity - always resolved from system
    user_name: str
    user_id: int  
    group_name: str
    group_id: int
    user_home: str
    
    # Paths - always resolved
    workspace: VolumeSpec       # Fully resolved workspace mount
    workdir: str                # Always resolved (defaults to workspace root)
    gosu_path: str              # Absolute path to gosu binary
    gosu_mount: str             # Mount point (default "/gosu")
    
    # Container settings - always have defaults
    image: str                  # From defaults or config
    command: str                # From defaults or config  
    container_name: str         # Always generated if not specified
    tty: bool                   # From defaults (stdin.isatty()) or config
    sudo: bool                  # From defaults (False) or config
    
    # Lists - use empty list as default instead of None
    env: List[str] = field(default_factory=list)
    volumes: List[VolumeSpec] = field(default_factory=list)
    post_start_commands: List[str] = field(default_factory=list)
    run_args: List[str] = field(default_factory=list)
    
    # Truly optional fields (None has meaning)
    network: Optional[str] = None          # None = Docker default networking
    platform: Optional[str] = None         # None = Docker default platform
    ulimits: Optional[Dict[str, Any]] = None  # None = no ulimits
```

**Rationale for non-Optional fields:**
- `workdir`: Always resolved to container path (workspace root if not specified)
- `container_name`: Always generated from workspace path if not specified
- `tty`: Has default from stdin.isatty(), no need for None
- `sudo`: Has default False, no need for None
- Lists: Empty list is clearer than None for "no items"

**Rationale for Optional fields:**
- `network`: None means "use Docker's default", different from explicit network
- `platform`: None means "use Docker's default", different from explicit platform
- `ulimits`: None means "no ulimits", different from empty dict

### 7. Remove Old Classes and Methods

**Remove entirely:**
- Current `ContainerConfig` class
- Current `ContainerSpec` class
- All resolution methods (logic moves to new `ContainerSpec.create()`)

### 8. Update Container Execution

**ContainerRunner and related:**
- Expect fully resolved ContainerSpec
- Remove calls to resolve methods
- ContainerSpec fields are guaranteed to be resolved

### 9. Update CLI Processing  

**cmd_run() changes:**
- Apply config_resolve_relative_paths() to CLI override dict before passing to get_container_config()
- get_container_config() returns dict
- Call ContainerSpec.create() to get resolved spec
- Remove calls to config.resolve()

## Benefits

1. **Clear separation**: Raw config data vs. resolved runtime data
2. **Single resolution point**: All resolution happens in ContainerSpec.create()
3. **Type safety**: Required fields are non-Optional, truly optional fields are Optional
4. **Simplified execution**: ContainerRunner gets guaranteed-resolved config
5. **Better error handling**: Resolution errors happen early, with clear context

## Migration Steps

1. Update config_resolve_relative_paths to work on dicts
2. Update ConfigFile to store raw dicts
3. Update CtenvConfig to store raw dicts  
4. Update ContainerConfig field types and from_dict() method
5. Update get_container_config() to return fully resolved ContainerConfig
6. Remove old resolution methods
7. Update container execution code
8. Update CLI processing code
9. Update tests
