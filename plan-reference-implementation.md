# Implementation Plan: Reference Section Features

This plan addresses discrepancies between the README Reference section and the actual implementation.

## Summary of Changes

1. **Project directory volume syntax** - Add support for `-p /host:/container` syntax
2. **Volume subpath remapping** - Mount project subpaths relative to project container path
3. **Workspace subdirectory validation** - Warn when workspace is outside project directory
4. **Config file relative paths** - Resolve relative paths relative to the config file, not project directory
5. **Container config precedence** - Project container configs completely replace (not merge with) user configs of the same name

---

## 1. Project Directory Volume Syntax ✅ DONE

**Goal:** Support `-p .:/repo` to specify both host path and container mount point.

**Design:** CLI uses volume syntax, config uses `project_mount` for clarity:

```toml
# ~/.ctenv.toml - always mount project at /repo
[defaults]
project_mount = "/repo"       # Where project mounts in container

# Or per-container
[containers.build]
project_mount = "/repo"
```

CLI supports volume syntax: `-p .:/repo` (host:mount)

**Config restriction:** `project_mount` is a simple absolute path string (e.g., `/repo`). It only sets where the project mounts in the container - the host path is always determined at runtime.

**Precedence (highest to lowest):**
1. CLI `-p /host:/mount` - both parts from CLI
2. CLI `-p /host` + config `project_mount = "/repo"` - host from CLI, mount from config
3. CLI `-p /host` alone - mount path = host path
4. Auto-detect + config `project_mount = "/repo"` - host auto-detected, mount from config
5. Auto-detect alone - mount path = host path (current behavior)

### Changes to `config.py`

**Add `project_mount` to ContainerConfig:**

```python
@dataclass(kw_only=True)
class ContainerConfig:
    # ... existing fields ...
    project_mount: Union[str, NotSetType] = NOTSET  # Absolute path (e.g., "/repo")
```

**RuntimeContext stays unchanged** - it keeps `project_dir` as the detected/specified host path (Path type).

**Add validation for config file project_mount:**

```python
def validate_config_project_mount(project_mount_str: str, config_path: Path) -> None:
    """Validate project_mount from config file.

    project_mount should be a simple absolute path string.
    """
    if not project_mount_str or not project_mount_str.strip():
        raise ValueError(f"In config file {config_path}: project_mount cannot be empty")

    if not project_mount_str.startswith("/"):
        raise ValueError(
            f"In config file {config_path}: project_mount must be an absolute path. "
            f"Got: '{project_mount_str}'"
        )
```

### Changes to `cli.py`

**Parse `--project-dir` with volume syntax:**

```python
def _parse_project_dir_arg(project_dir_arg: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Parse --project-dir argument, which may include volume syntax.

    Returns:
        (host_path, container_path) - either can be None if not specified
    """
    if project_dir_arg is None:
        return None, None

    if ":" in project_dir_arg:
        # Volume syntax: /path:/container or ./path:/container
        spec = VolumeSpec.parse(project_dir_arg)
        host = spec.host_path if spec.host_path else None
        container = spec.container_path if spec.container_path else None
        return host, container
    else:
        return project_dir_arg, None
```

**Update `cmd_run` to pass container path as config override:**

```python
def cmd_run(args, command):
    # Parse project-dir with volume syntax support
    project_dir, project_mount = _parse_project_dir_arg(args.project_dir)

    runtime = RuntimeContext.current(
        cwd=Path.cwd(),
        project_dir=project_dir,  # Host path only (None = auto-detect)
    )

    # ... load config ...

    # Add project_mount to CLI overrides if container path specified
    cli_args_dict = {
        # ... existing fields ...
        "project_mount": project_mount,  # Simple path string (e.g., "/repo")
    }
```

### Changes to `container.py`

**Resolve project mount path in `parse_container_config`:**

```python
def parse_container_config(config: ContainerConfig, runtime: RuntimeContext) -> ContainerSpec:
    # Resolve project mount path early (needed for workspace/volume parsing)
    # project_mount is a simple absolute path string (e.g., "/repo")
    if config.project_mount is not NOTSET:
        project_mount = config.project_mount
    else:
        project_mount = str(runtime.project_dir)  # Default: same as host

    # Use project_mount when parsing workspace and volumes
    # (see #2 and #3 for details)
```

---

## 2. Volume Subpath Remapping ✅ DONE

**Goal:** When a volume is a subpath of project directory and has no explicit container path, mount it relative to project container path.

**Note:** These functions receive `project_dir` (from RuntimeContext) and `project_mount` (resolved from ContainerConfig in `parse_container_config`) as separate parameters.

### Changes to `container.py`

**Update `_parse_volume` signature and logic:**

```python
def _parse_volume(vol_str: str, project_dir: Path, project_mount: str) -> VolumeSpec:
    """Parse volume specification with project-aware path defaulting.

    If the volume's host path is a subpath of project_dir and no container
    path is specified, the container path is computed relative to
    project_mount.
    """
    if vol_str is NOTSET or vol_str is None:
        raise ValueError(f"Invalid volume: {vol_str}")

    spec = VolumeSpec.parse(vol_str)

    if not spec.host_path:
        raise ValueError(f"Volume host path cannot be empty: {vol_str}")

    # Smart defaulting for container path
    if not spec.container_path:
        # Check if this is a subpath of project directory
        try:
            rel_path = os.path.relpath(spec.host_path, project_dir)
            if not rel_path.startswith(".."):
                # It's a subpath - mount relative to project container path
                if rel_path == ".":
                    spec.container_path = project_mount
                else:
                    spec.container_path = os.path.join(
                        project_mount, rel_path
                    )
            else:
                # Outside project - mount at same path as host
                spec.container_path = spec.host_path
        except ValueError:
            # Different drives on Windows, can't compute relative path
            spec.container_path = spec.host_path

    return spec
```

**Update call sites in `parse_container_config`:**

```python
# In parse_container_config, after resolving project_mount (see #1):
if config.project_mount is not NOTSET:
    project_mount = config.project_mount  # Simple absolute path
else:
    project_mount = str(runtime.project_dir)

# Then when parsing volumes:
vol_spec = _parse_volume(vol_str, runtime.project_dir, project_mount)
```

### Changes to `_parse_workspace`

**Update to use `project_mount`:**

```python
def _parse_workspace(workspace_str: str, project_dir: Path, project_mount: str) -> VolumeSpec:
    """Parse workspace configuration and return VolumeSpec.

    Uses project_mount for container path defaulting.
    """
    if workspace_str is NOTSET or workspace_str is None:
        raise ValueError(f"Invalid workspace: {workspace_str}")

    spec = VolumeSpec.parse(workspace_str)

    # Default host path to project directory
    if not spec.host_path:
        spec.host_path = "auto"
    if spec.host_path == "auto":
        spec.host_path = str(project_dir)

    # Default container path using project_mount
    if spec.container_path == "auto" or not spec.container_path:
        try:
            rel_path = os.path.relpath(spec.host_path, project_dir)
            if not rel_path.startswith(".."):
                if rel_path == ".":
                    spec.container_path = project_mount
                else:
                    spec.container_path = os.path.join(
                        project_mount, rel_path
                    )
            else:
                # Outside project directory
                spec.container_path = spec.host_path
        except ValueError:
            spec.container_path = spec.host_path

    # Add 'z' option if not already present (for SELinux)
    if "z" not in spec.options:
        spec.options.append("z")

    return spec
```

**Update signature:** Change from `(workspace_str, project_dir)` to `(workspace_str, project_dir, project_mount)`.

---

## 3. Workspace Subdirectory Validation ✅ DONE

**Goal:** Warn (not error) when workspace is outside project directory.

**Note:** This validation is added to `_parse_workspace` which now takes `project_dir` as a parameter (see #2).

### Changes to `container.py`

**Add validation in `_parse_workspace`:**

```python
def _parse_workspace(workspace_str: str, project_dir: Path, project_mount: str) -> VolumeSpec:
    # ... existing parsing logic ...

    # Validate workspace is within project directory (warning only)
    try:
        rel_path = os.path.relpath(spec.host_path, project_dir)
        if rel_path.startswith(".."):
            logging.warning(
                f"Workspace '{spec.host_path}' is outside project directory "
                f"'{project_dir}'. Project container path remapping will not apply."
            )
    except ValueError:
        # Different drives on Windows
        logging.warning(
            f"Workspace '{spec.host_path}' is on a different drive than project directory "
            f"'{project_dir}'. Project container path remapping will not apply."
        )

    return spec
```

---

## 4. Config File Relative Paths ✅ DONE

**Goal:** Resolve relative paths in config files relative to the config file's location, not project directory.

### Changes to `config.py`

**Update `ConfigFile.load` to use config file's directory:**

```python
@classmethod
def load(cls, config_path: Path, project_dir: Path) -> "ConfigFile":
    """Load configuration from a specific file.

    Relative paths in the config file are resolved relative to the
    config file's directory, not the project directory.
    """
    if not config_path.exists():
        raise ValueError(f"Config file not found: {config_path}")

    config_data = _load_config_file(config_path)

    # Use config file's parent directory for relative path resolution
    config_base_dir = config_path.parent.resolve()

    raw_containers = config_data.get("containers", {})
    raw_defaults = config_data.get("defaults")

    # Process defaults to ContainerConfig if present
    defaults_config = None
    if raw_defaults:
        defaults_config = ContainerConfig.from_dict(convert_notset_strings(raw_defaults))
        defaults_config._config_file_path = str(config_path.resolve())
        # Resolve relative to config file, not project_dir
        defaults_config = resolve_relative_paths_in_container_config(
            defaults_config, config_base_dir  # CHANGED
        )

    # Process containers to ContainerConfig objects
    container_configs = {}
    for name, container_dict in raw_containers.items():
        container_config = ContainerConfig.from_dict(convert_notset_strings(container_dict))
        container_config._config_file_path = str(config_path.resolve())
        # Resolve relative to config file, not project_dir
        container_config = resolve_relative_paths_in_container_config(
            container_config, config_base_dir  # CHANGED
        )
        container_configs[name] = container_config

    # ... rest of method
```

**Note:** The `project_dir` parameter is still passed but only used for other purposes (like variable substitution). Path resolution uses `config_path.parent`.

---

## 5. Container Config Precedence (No Merging) ✅ DONE

**Goal:** If a container name exists in both project config and user config, use the project config entirely - no merging.

**Current behavior:**
```python
# In CtenvConfig.load()
for config_file in reversed(config_files):
    for name, container_config in config_file.containers.items():
        if name in containers:
            # PROBLEM: Merges configs - lists concatenate, values layer
            containers[name] = merge_container_configs(containers[name], container_config)
        else:
            containers[name] = container_config
```

This causes confusing behavior where volumes/env from user config leak into project config.

### Changes to `config.py`

**Update `CtenvConfig.load` to replace instead of merge:**

```python
@classmethod
def load(cls, project_dir: Path, explicit_config_files: Optional[List[Path]] = None):
    # ... existing config file loading ...

    # Compute containers - higher priority completely replaces lower priority
    containers = {}
    # Process in reverse order so higher priority wins
    for config_file in reversed(config_files):
        for name, container_config in config_file.containers.items():
            # Simply overwrite - no merging
            containers[name] = container_config

    return cls(defaults=defaults, containers=containers)
```

**That's it** - just remove the `merge_container_configs` call and always overwrite.

### Behavior After Change

`~/.ctenv.toml`:
```toml
[containers.foobar]
image = "ubuntu:20.04"
volumes = ["~/.cache"]
env = ["FOO=bar"]
```

`/project/.ctenv.toml`:
```toml
[containers.foobar]
image = "ubuntu:22.04"
volumes = ["./build"]
```

**Result:**
```
image = "ubuntu:22.04"    # from project
volumes = ["./build"]     # from project only (no ~/.cache!)
env = []                  # from project (empty, not inherited)
```

The project config is self-contained. User config for "foobar" is completely ignored.

### Open Question: Defaults Merging

Currently `[defaults]` still merges. Whether this is correct is TBD - there's a need for users to override personal preferences (like PS1) without affecting project config. Possible solutions:
- `.ctenv.local.toml` (gitignored local overrides)
- User config wins for defaults
- Environment variable overrides

This is deferred for later consideration.

---

## Implementation Order

Recommended order to minimize conflicts:

1. **#5 - Container config precedence** ✅ DONE
2. **#4 - Config file relative paths** ✅ DONE
3. **#1 - Project container path in ContainerConfig** ✅ DONE
4. **#3 - Workspace validation** ✅ DONE
5. **#2 - Volume subpath remapping** ✅ DONE

---

## Testing Considerations

### Test cases for #1 (Project directory volume syntax):
- `-p /project` - host and container both `/project`
- `-p /project:/repo` - host `/project`, container `/repo`
- `-p .:/repo` - host is cwd resolved, container `/repo`
- Auto-detection when no `-p` specified
- Config `project_dir = ":/repo"` - sets container path, uses detected host
- Config `project_dir = "auto:/repo"` - same as above
- Config `project_dir = "/foo:/repo"` - ERROR (can't set host in config)
- CLI `-p /host:/container` overrides config `project_dir`

### Test cases for #2 (Volume subpath remapping):
- `-p /project:/repo -v /project/src` → mounts at `/repo/src`
- `-p /project:/repo -v /project/src:/custom` → mounts at `/custom` (explicit)
- `-p /project:/repo -v /other/path` → mounts at `/other/path` (outside project)
- `-p /project -v /project/src` → mounts at `/project/src` (no remapping needed)

### Test cases for #3 (Workspace validation):
- `-p /project -w /project/src` → no warning
- `-p /project -w /other/path` → warning logged
- `-w` not specified → defaults to project, no warning

### Test cases for #4 (Config relative paths):
- `~/.ctenv.toml` with `volumes = ["./cache"]` → resolves to `~/cache`
- `/project/.ctenv.toml` with `volumes = ["./build"]` → resolves to `/project/build`
- Absolute paths unchanged in both cases

### Test cases for #5 (Container config precedence):
- Container only in user config → used as-is
- Container only in project config → used as-is
- Container in both → project config used entirely, user config ignored
- Different containers in each → both available (no conflict)
- `[defaults]` still merges (only named containers replace)

---

## Files to Modify

| File | Changes |
|------|---------|
| `ctenv/config.py` | Add `project_mount` to ContainerConfig (absolute path), add validation ✅, fix ConfigFile.load path resolution ✅, remove container merging in CtenvConfig.load ✅ |
| `ctenv/cli.py` | Parse `--project-dir` with volume syntax, pass mount path as config override ✅ |
| `ctenv/container.py` | Resolve project_mount from config.project_mount ✅, update `_parse_workspace` and `_parse_volume` signatures ✅ |

---

## Backward Compatibility

**Note:** There are no external users yet, so backward compatibility is not a constraint. We can freely change behavior to match the documented/intended design.

**Breaking change in #5:** Container config merging is removed. Users who might have relied on defining base volumes in `~/.ctenv.toml` and extending in project would need to duplicate the full config. This is the correct behavior - merging was confusing.
