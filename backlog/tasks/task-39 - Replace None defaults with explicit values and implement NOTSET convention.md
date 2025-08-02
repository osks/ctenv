---
id: task-39
title: Replace None defaults with explicit values and implement NOTSET convention
status: Done
priority: High
assignee: 
created: 2025-08-02
updated: 2025-08-02
tags: [config, refactoring]
---

# Task 39 - Replace None defaults with explicit values and implement NOTSET convention

## Background

We have a fundamental design issue with None values in configuration merging:

### The Problem
We use `None` to mean two different things:
1. **"Not set"** (shouldn't override defaults when merging)
2. **"Default value is None"** (should override with None as the intended value)

This creates confusion during configuration merging where `None` from "not set" incorrectly overrides meaningful defaults.

### Example of the Issue
```python
# Scenario: User wants to override workdir to "/app" in container, but CLI sets it back to None
# Builtin defaults
{"workdir": None}  # Means "preserve relative position"

# Container config from TOML
{"workdir": "/app"}  # User wants specific directory

# CLI overrides (user didn't specify --workdir, so argparse sets it to None)
{"workdir": None}  # None from "not specified" 

# After merge_dict(defaults, container, cli_overrides)
{"workdir": None}  # Wrong! CLI None overrode container "/app" even though user didn't specify CLI workdir

# What we want: CLI None should mean "don't override" not "set to None"
```

### Current Config Keys Using None as Default Value

From `get_builtin_defaults()`:

**Path/Location fields:**
- `workdir: None` - Preserve relative position between host CWD and workspace mount
- `gosu_path: None` - Auto-detect from bundled binaries
- `container_name: None` - Auto-generate based on workspace

**Container settings:**
- `network: None` - Use Docker's default networking 
- `tty: None` - Auto-detect from stdin at runtime
- `platform: None` - Use Docker's default platform
- `ulimits: None` - No resource limits

**Metadata:**
- `_config_file_path: None` - No config file for defaults

## Solution Approach

### 1. NOTSET Sentinel Object
Introduce a sentinel object to clearly distinguish "not configured" from actual values:

```python
class _NotSetType:
    """Sentinel type for not configured values."""
    def __repr__(self) -> str:
        return "NOTSET"

NOTSET = _NotSetType()  # Sentinel for "not configured"

# Type alias for clean type hints
NotSetType = type(NOTSET)
```

**Why a custom class instead of `object()`?**
- Better repr for debugging (`NOTSET` instead of `<object object at 0x...>`)
- Enables proper type hints without exposing internal class name
- More explicit and self-documenting

**Why the type alias `NotSetType = type(NOTSET)`?**
- Clean type hints: `Union[str, NotSetType]` instead of `Union[str, _NotSetType]`
- Hides implementation detail (`_NotSetType`) from public interface
- Works perfectly with type checkers and runtime checks
- More readable and maintainable than exposing private class names

### 2. Unified String Convention
The string "NOTSET" in TOML and CLI is parsed to the NOTSET sentinel:

```toml
# TOML
[containers.web]
network = "NOTSET"  # Parsed to NOTSET sentinel
# Missing keys also → NOTSET sentinel

# CLI
ctenv run --network NOTSET  # Parsed to NOTSET sentinel
```

### 3. Updated Default Values
Replace None with explicit values or NOTSET:

```python
get_builtin_defaults() = {
    # Auto-detect behaviors
    "workdir": "auto",        # Preserve relative position
    "gosu_path": "auto",      # Auto-detect bundled binary
    "container_name": "auto", # Auto-generate name
    "tty": "auto",           # Auto-detect from stdin
    
    # Not configured (NOTSET)
    "network": NOTSET,        # No network specified
    "platform": NOTSET,       # No platform specified
    "ulimits": NOTSET,       # No limits specified
    
    # Actual defaults
    "image": "ubuntu:latest",
    "command": "bash",
    "env": [],
    "volumes": [],
    "sudo": False,
    
    # Metadata (stays None)
    "_config_file_path": None,  # Internal metadata, not user-configurable
}
```

### 4. Type System and Data Flow

**Important distinction**: `ContainerConfig` represents **parsed configuration objects** (internal representation), not raw TOML/CLI data.

**Key Decision: NOTSET Fields + Explicit builtin_defaults()**
Initial approach of putting defaults in dataclass fields caused config show to display all defaults for every container. We need to distinguish "not configured" from "configured with default value".

**Why NOTSET fields are needed:**
- ContainerConfig represents partial configurations (from TOML/CLI parsing)
- Fields default to NOTSET = "not configured in this source"
- Only explicitly set values are preserved during merging
- Config show only displays actually configured values, not inherited defaults

```python
@dataclass(kw_only=True)
class ContainerConfig:
    """Parsed configuration object with NOTSET sentinel support.
    
    All fields default to NOTSET (meaning "not configured") to distinguish
    between explicit configuration and missing values.
    """
    
    # Container settings (all default to NOTSET)
    image: Union[str, NotSetType] = NOTSET
    command: Union[str, NotSetType] = NOTSET
    workspace: Union[str, NotSetType] = NOTSET
    workdir: Union[str, NotSetType] = NOTSET
    gosu_path: Union[str, NotSetType] = NOTSET
    container_name: Union[str, NotSetType] = NOTSET
    tty: Union[str, bool, NotSetType] = NOTSET
    sudo: Union[bool, NotSetType] = NOTSET
    
    # Network and platform settings
    network: Union[str, NotSetType] = NOTSET
    platform: Union[str, NotSetType] = NOTSET
    ulimits: Union[Dict[str, Any], NotSetType] = NOTSET
    
    # Lists (use NOTSET to distinguish from empty list)
    env: Union[List[str], NotSetType] = NOTSET
    volumes: Union[List[str], NotSetType] = NOTSET
    post_start_commands: Union[List[str], NotSetType] = NOTSET
    run_args: Union[List[str], NotSetType] = NOTSET
    
    # Metadata fields for resolution context
    _config_file_path: Optional[str] = None
    
    @classmethod
    def builtin_defaults(cls) -> "ContainerConfig":
        """Provide actual built-in default values."""
        return cls(
            workspace="auto",  # Auto-detect project root
            workdir="auto",   # Preserve relative position
            gosu_path="auto", # Auto-detect bundled binary
            tty="auto",       # Auto-detect from stdin
            image="ubuntu:latest",
            command="bash",
            container_name="ctenv-${image|slug}",
            sudo=False,
            env=[], volumes=[], post_start_commands=[], run_args=[],
            # network, platform, ulimits stay NOTSET
        )
```

**Key Type Simplifications:**
1. **No None needed**: Most fields use NOTSET, eliminating Optional types  
2. **Cleaner unions**: `Union[str, NotSetType]` instead of `Union[str, NotSetType, None]`
3. **Container name**: Uses variable substitution (`${image|slug}`) instead of "auto" pattern
4. **Built-in defaults**: `builtin_defaults()` explicitly provides default values
5. **Config display**: Only shows explicitly configured values, not inherited defaults

**Data flow:**
1. **Raw TOML/CLI**: Contains strings like `"NOTSET"`, `"auto"`, or missing keys
2. **Parsing step**: `"NOTSET"` → `NOTSET` object, `"auto"` → `"auto"` string, missing → `NOTSET` (dataclass default)
3. **ContainerConfig**: Contains mix of strings, NOTSET objects (partial configs)
4. **Merging**: NOTSET values are filtered out (don't override), defaults applied via `builtin_defaults()`
5. **ContainerSpec**: Final resolved values ready for execution

**Result: Clean config display that only shows explicitly configured values**

### 5. Parsing Logic
Convert "NOTSET" strings to sentinel:

```python
def parse_config_value(value: Any) -> Any:
    """Convert "NOTSET" string to NOTSET sentinel."""
    if value == "NOTSET":
        return NOTSET
    return value
 
# Apply during:
# - TOML parsing (ConfigFile.from_dict)
# - CLI string arguments ("NOTSET" → NOTSET)
# - CLI defaults (argparse default=NOTSET)
# - Missing TOML keys → NOTSET
```

### 6. Merge Logic
Filter NOTSET values during merge:

```python
def merge_dict(config, overrides):
    # Filter NOTSET values (don't override)
    filtered = {k: v for k, v in overrides.items() if v is not NOTSET}
    # ... rest of merge logic
```

## Benefits

1. **Clear semantics**: NOTSET sentinel explicitly means "not configured"
2. **Type safety**: No None in Union types, cleaner type hints
3. **Self-documenting**: `if v is not NOTSET` clearly shows intent
4. **Unified approach**: Same "NOTSET" string convention in TOML and CLI
5. **Single filtering point**: Filter NOTSET only during merge

## Implementation Steps

### Phase 1: Define NOTSET Sentinel
1. Add `NOTSET = object()` at module level
2. Update type imports for `Literal` if needed

### Phase 2: Update ContainerConfig with NOTSET Defaults ✅ COMPLETED
1. **✅ Use NOTSET as field defaults:**
   - All ContainerConfig fields default to NOTSET (meaning "not configured")
   - Keeps `builtin_defaults()` method to provide actual default values
   - Fixes config show to only display explicitly configured values

2. **✅ Update field types to remove None:**
   - `workspace: Optional[str] = None` → `workspace: Union[str, NotSetType] = NOTSET`
   - `workdir: Optional[str] = None` → `workdir: Union[str, NotSetType] = NOTSET`
   - `gosu_path: Optional[str] = None` → `gosu_path: Union[str, NotSetType] = NOTSET`
   - `container_name: Optional[str] = None` → `container_name: Union[str, NotSetType] = NOTSET`
   - `tty: Optional[bool] = None` → `tty: Union[str, bool, NotSetType] = NOTSET`
   - `network: Optional[str] = None` → `network: Union[str, NotSetType] = NOTSET`
   - `platform: Optional[str] = None` → `platform: Union[str, NotSetType] = NOTSET`
   - `ulimits: Optional[Dict] = None` → `ulimits: Union[Dict[str, Any], NotSetType] = NOTSET`

3. **✅ Update value handling code:**
   - `_parse_workspace()` handles `workspace == "auto"` (auto-detect project root)
   - `_resolve_workdir()` handles `workdir == "auto"`
   - `_parse_gosu_spec()` handles `gosu_path == "auto"`
   - `_resolve_tty()` handles `tty == "auto"`
   - Resolution functions are strict about invalid values (no None fallbacks)

### Phase 3: Update Parsing and Merging ✅ COMPLETED
1. **✅ Update `to_dict()` to filter NOTSET values** (and None for metadata fields)
2. **✅ Update merge logic** - `merge_dict()` now skips NOTSET values during merging
3. **✅ Config display filtering** - NOTSET values hidden in `config show` output

### Phase 4: Update Parsing ✅ COMPLETED
1. **✅ TOML parsing**: COMPLETE - `convert_notset_strings()` function exists and is used in `ConfigFile.load()`
2. **✅ CLI parsing**: COMPLETE - `convert_notset_strings()` applied to CLI args in `cmd_run()`
3. **✅ Missing keys** → NOTSET (handled by dataclass defaults)

**Current Status**: 
- ✅ **TOML**: `network = "NOTSET"` correctly creates ContainerConfig with `network=NOTSET` sentinel
- ✅ **CLI**: `ctenv run --network NOTSET` now converts `"NOTSET"` string to NOTSET object

**Implementation Complete**:
**CLI argument processing** (in `cmd_run()` lines 1610-1625):
```python
cli_overrides = resolve_relative_paths_in_container_config(
    ContainerConfig.from_dict(
        convert_notset_strings(
            {
                "image": args.image,
                "command": command,
                "workspace": args.workspace,
                # ... other CLI args
            }
        )
    ),
    runtime.cwd,
)
```

### Phase 5: Update Merge Logic ✅ COMPLETED
1. **✅ Change merge_dict to filter `v is not NOTSET`**
2. **✅ Remove None filtering from other locations**

### Phase 6: Update Tests ❌ NOT IMPLEMENTED YET
1. Replace None checks with NOTSET checks
2. Add tests for "NOTSET" string in TOML/CLI
3. Update expected defaults

## Final Status

**✅ IMPLEMENTATION COMPLETE**: All core NOTSET functionality has been implemented:

1. **✅ NOTSET Sentinel**: `_NotSetType` class with proper repr and type alias
2. **✅ ContainerConfig Fields**: All fields default to NOTSET with proper Union types
3. **✅ Built-in Defaults**: `builtin_defaults()` method provides actual default values
4. **✅ String Parsing**: `convert_notset_strings()` converts "NOTSET" → NOTSET in both TOML and CLI
5. **✅ Merge Logic**: `merge_dict()` and `merge_container_configs()` properly filter NOTSET values
6. **✅ Config Display**: `to_dict(include_notset=False)` hides NOTSET values in `config show`
7. **✅ Type Safety**: Clean Union types without None, proper NOTSET handling throughout

**Remaining Work**: Only tests need to be updated to work with the new NOTSET convention.

**✅ User Impact**: Users can now use `"NOTSET"` in both TOML files and CLI arguments to explicitly not override defaults:
- TOML: `network = "NOTSET"`  
- CLI: `ctenv run --network NOTSET`

## Implementation Decisions

**Simple and concise approach - minimal code changes:**

1. **Config show output**: Hide NOTSET values (`if v is not NOTSET`)
2. **Error messages**: Show "NOTSET" as-is (simplest, no special formatting)
3. **Case sensitivity**: Only "NOTSET" (exact match, case-sensitive)
4. **Migration**: No backward compatibility (development phase, no existing users)
5. **Type hints**: Keep simple, use existing patterns

## Open Questions

### Should overrides be ContainerConfig or dict in CtenvConfig?

**Current approach**: Overrides are passed as `Dict[str, Any]` and converted to ContainerConfig internally.

**Alternative**: Accept `ContainerConfig` directly as overrides parameter.

**Considerations:**
- **CLI integration**: CLI args naturally produce dicts with only specified fields
- **Partial configs**: Dict allows sparse/partial configs without NOTSET defaults for every field
- **Type safety vs Flexibility**: ContainerConfig gives type safety but dict is more flexible for overrides
- **Conversion point**: Current design converts in one place (inside method) which is clean
- **API consistency**: Should match original CtenvConfig API for easy migration

**Decision**: TBD - need to consider implications for CLI parsing and overall architecture
