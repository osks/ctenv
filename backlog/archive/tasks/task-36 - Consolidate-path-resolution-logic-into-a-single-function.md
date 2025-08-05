---
id: task-36
title: Dict-based config system refactoring (COMPLETED via Task 37)
status: Done
assignee: []
created_date: '2025-07-26'
labels: []
dependencies: []
---

## COMPLETED ✅

This task has been superseded and completed by **Task 37**, which implemented a superior architecture that solved all the problems identified here.

## Problems Solved

**1. Multiple Resolution Points** ✅ SOLVED
- Single resolution point in `parse_container_config()`
- Path resolution centralized in `config_resolve_relative_paths()`

**2. Early Structure Conversion** ✅ SOLVED  
- Raw dicts used throughout loading/merging
- VolumeSpec parsing happens only at final resolution
- Template variables preserved until resolution

**3. Context Loss** ✅ SOLVED
- RuntimeContext provides user info, cwd, tty detection
- Config file paths resolved relative to config file directory
- CLI paths resolved relative to current working directory

**4. Variable Expansion** ✅ SOLVED
- Variable substitution in `_substitute_variables_in_dict()`
- Template variables like `${user_name}`, `${image|slug}` work correctly

## Implemented Architecture (Task 37)

```
Config Files → Raw Dicts → Merged Dict → parse_container_config() → ContainerSpec
                  ↓                              ↓
    config_resolve_relative_paths()      RuntimeContext + Variable substitution
                                                ↓
                                        Fully resolved, ready-to-execute
```

**Key Components:**

- **Raw Dicts**: Configuration stored as dictionaries throughout loading/merging
- **RuntimeContext**: Separate dataclass for user info, cwd, tty detection  
- **parse_container_config()**: Single resolution point that creates ContainerSpec
- **ContainerSpec**: Fully resolved, ready-to-execute specification
- **VolumeSpec**: Smart parsing with context-aware methods (parse_as_volume vs parse_as_workspace)

**Benefits Achieved:**
- ✅ **Single resolution point**: All processing in one place
- ✅ **Clean separation**: Config data vs runtime context vs resolved specs
- ✅ **Type safety**: Required fields non-Optional, optional fields Optional
- ✅ **No round-trip parsing**: Direct dict → resolved spec conversion
- ✅ **Context-aware path resolution**: Config file vs CLI paths handled correctly
- ✅ **Template variables**: `${user_name}`, `${image|slug}` work throughout
- ✅ **Tilde expansion**: Proper `~/` handling with runtime context

## Path Resolution Context (IMPLEMENTED ✅)

The implemented solution correctly handles different path resolution contexts:

1. **Config file paths**: `config_resolve_relative_paths()` resolves relative to config file directory
2. **CLI override paths**: `config_resolve_relative_paths()` resolves relative to current working directory  
3. **Mixed scenarios**: Each source uses appropriate base directory during resolution

This provides the path resolution behavior originally planned in this task, but with a cleaner architecture that eliminates the need for complex Union types and two-phase objects.