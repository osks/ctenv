---
id: task-36
title: Redesign config handling - consolidate resolution in ContainerConfig.from_dict
status: To Do
assignee: []
created_date: '2025-07-26'
labels: []
dependencies: []
---

## Current Problems

**1. Multiple Resolution Points** - Path resolution happens in scattered places:
- cmd_run processes CLI volumes early (with templates)
- ContainerConfig.from_dict parses volume specs immediately 
- resolve_templates tries to handle template expansion
- Various resolve functions handle path resolution

**2. Early Structure Conversion** - We convert strings to VolumeSpec objects too early in from_dict, which:
- "Locks in" variables like ${user_name} before resolution
- Loses original string representation needed for template processing  
- Does path resolution before knowing the final merged config

**3. Context Loss** - We lose important context (like config file directory) too early for proper path resolution

**4. Variable Expansion Issues** - Variable expansion doesn't work because we convert to structured objects before processing them

## Selected Design: Two-phase ContainerConfig approach

**Implementation plan:**

```python
class ContainerConfig:
    """Container configuration with resolved/unresolved states."""
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ContainerConfig":
        """Create unresolved ContainerConfig from merged dict."""
        # Simple type creation - metadata flows through normal merging
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        kwargs = {
            key: value for key, value in config_dict.items() 
            if key in valid_fields and value is not None
        }
        return cls(**kwargs)  # Create instance with raw values + metadata
    
    def resolve(self) -> "ContainerConfig":
        """Return fully resolved version of this config."""
        
        # 1. Variable expansion using config fields
        resolved_dict = self._expand_variables()
        
        # 2. Path resolution with metadata context  
        resolved_dict = self._resolve_paths(resolved_dict)
        
        # 3. Parse to structured objects
        resolved_dict = self._parse_to_objects(resolved_dict)
        
        # 4. Return new resolved instance
        return ContainerConfig(
            workspace=VolumeSpec(...),              # Fully resolved
            volumes=[VolumeSpec(...), ...],         # Fully resolved
            image="ubuntu:latest",                  # Fully resolved
            user_name="alice",                      # Same as before
            _config_file_path=self._config_file_path,
            _cwd=self._cwd
        )
```

**Implementation steps:**

1. **Update ContainerConfig dataclass fields to use Union types:**
   ```python
   @dataclass  
   class ContainerConfig:
       workspace: Union[str, VolumeSpec]              # Raw string or resolved object
       volumes: Union[List[str], List[VolumeSpec]]    # Raw strings or resolved objects  
       image: str                                     # Always string (raw or resolved)
       # ... existing fields
       _cwd: Path                                     # Metadata field (from defaults)
       _config_file_path: Optional[Path] = None       # Metadata field
   ```

2. **Add metadata to default config and config file loading:**
   ```python
   def get_default_config_dict() -> Dict[str, Any]:
       """Get default configuration values as a dict."""
       user_info = pwd.getpwuid(os.getuid())
       group_info = grp.getgrgid(os.getgid())
       
       return {
           "user_name": user_info.pw_name,
           "user_id": user_info.pw_uid,
           # ... other defaults
           "_cwd": Path.cwd(),                   # Captured at defaults creation
           "_config_file_path": None,            # No config file for defaults
           # ... rest of defaults
       }
   
   # In config file loading:
   @classmethod
   def from_file(cls, config_file_path: Path) -> Dict[str, Any]:
       """Load config from file with metadata."""
       config_data = _load_config_file(config_file_path)
       config_data["_config_file_path"] = config_file_path  # Add file path metadata
       return config_data
   ```

3. **Simplify from_dict to just create types:**
   ```python
   @classmethod
   def from_dict(cls, config_dict: Dict[str, Any]) -> "ContainerConfig":
       """Create unresolved ContainerConfig from merged raw dict."""
       # Simple type creation - metadata flows through normal merging
       valid_fields = {f.name for f in dataclasses.fields(cls)}
       kwargs = {
           key: value for key, value in config_dict.items() 
           if key in valid_fields and value is not None
       }
       return cls(**kwargs)  # Just create the instance with raw values
   ```

4. **Implement resolve() method:**
   ```python
   def resolve(self) -> "ContainerConfig":
       """Return new ContainerConfig with all values fully resolved."""
       # 1. Variable expansion: ${user_name}, ${image|slug}, etc.
       # 2. Path resolution: ., ~, relative paths using self._config_file_path and self._cwd
       # 3. Parse to structured objects: strings → VolumeSpec, etc.
       # 4. Return new resolved ContainerConfig instance
   ```

5. **resolve_container_config stays simple:**
   ```python
   def resolve_container_config(self, ...) -> "ContainerConfig":
       # Just merge configs - metadata already included from defaults and config files
       merged_dict = self._merge_all_configs(container, cli_overrides)
       return ContainerConfig.from_dict(merged_dict)  # Returns unresolved
   ```

6. **Update call sites to use resolve() when needed:**
   ```python
   # For debugging/validation: use unresolved config
   config = ctenv_config.resolve_container_config(container="dev")
   print(f"Raw workspace: {config.workspace}")  # Shows "."
   
   # For execution: use resolved config  
   resolved_config = config.resolve()
   print(f"Resolved workspace: {resolved_config.workspace}")  # Shows VolumeSpec(...)
   ```

**Benefits:**
- **Inspect both states**: Can examine config before and after resolution for debugging
- **Validate unresolved config**: Check if config structure is sound before any processing
- **Cleaner separation**: `from_dict` only handles merging/overrides, `resolve()` only handles processing
- **Lazy resolution**: Only resolve when actually needed (e.g., for container execution)
- **Immutable resolution**: Each `resolve()` call returns new instance, original stays unresolved
- **Type-based state tracking**: Field types indicate resolved vs unresolved (Union[str, VolumeSpec])
- **Better error messages**: Can show both original and partially-resolved config in errors
- **Testing**: Can test merging logic separately from resolution logic
- **Works with existing code**: Minimal changes needed to current dataclass structure