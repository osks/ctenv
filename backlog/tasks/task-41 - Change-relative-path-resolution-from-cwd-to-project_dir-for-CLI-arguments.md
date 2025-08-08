---
id: task-41
title: Change relative path resolution from config_dir to project_dir for config files
status: Done
assignee: []
created_date: '2025-08-08'
labels: []
dependencies: []
---

## Description

Change config file relative path resolution to use project directory instead of config file directory for consistency and predictability.

## Analysis

### Current Behavior

The system currently uses **two different resolution contexts**:

1. **Config file paths** → Resolved relative to the config file's directory (`config_dir`)
2. **CLI override paths** → Resolved relative to current working directory (`runtime.cwd`) ✅ (this is correct)

### Proposed Change Impact

Changing config file path resolution from `config_dir` to `project_dir` would affect:

#### 1. **Single Point of Change** ✅
- **Location**: Lines 498 and 507 in `ConfigFile.load()` method in `ctenv/ctenv.py` 
- **Current**: `config_dir = config_path.parent` (resolve relative to config file location)
- **New**: Use `project_dir` parameter (resolve relative to project directory)

#### 2. **Behavioral Changes**

**Before**: Config file relative paths resolve from config file location
```toml
# /home/user/project/config/.ctenv.toml
[defaults]
workspace = "./data"  # Resolves to /home/user/project/config/data
```

**After**: Config file relative paths resolve from project root
```toml
# /home/user/project/config/.ctenv.toml  
[defaults]
workspace = "./data"  # Resolves to /home/user/project/data
```

**CLI behavior remains unchanged** (relative to cwd where ctenv is invoked):
```bash
cd /home/user/project/subdir
ctenv run --workspace ./data  # Still resolves to /home/user/project/subdir/data
```

#### 3. **Affected Config File Types**
**All config files** resolve relative paths using project directory:
- **Project config** (`/project/.ctenv.toml`)
- **User config** (`~/.ctenv.toml`) 
- **Explicit config files** (via `--config` flag)

**Affected path fields in config files:**
- `workspace` with relative paths
- `volumes` with relative host paths  
- `gosu_path` with relative paths
- Any other path fields in config files

#### 4. **Benefits**
- **Industry Standard Consistency**: Aligns with how most development tools handle config file paths:
  - **Git**: `.gitignore` paths are relative to repository root, not `.gitignore` location
  - **Cargo**: `Cargo.toml` paths are relative to package root, not config file location  
  - **Jest**: `jest.config.js` paths resolve from project root
  - **Webpack**: `webpack.config.js` paths resolve from project root
  - **Rollup**: `rollup.config.js` paths resolve from project root
  - **Gradle**: `build.gradle` paths resolve from project root
- **Predictability**: Same config relative path always resolves to same absolute path within a project  
- **Intuitive**: Config files naturally reference project-relative paths, not config-file-relative paths
- **CLI behavior preserved**: Users still get expected shell-like behavior for CLI arguments

#### 5. **Potential Issues**
- **Breaking change**: Existing config files using relative paths would change behavior
- **Test updates needed**: Tests assuming config-dir-relative resolution would need updates
- **Documentation updates**: Config file examples would need updating

#### 6. **Test Impact**
Several tests would need updates, particularly:
- Tests checking config file path resolution in `test_config.py`
- Any integration tests using config files with relative paths
- Config file loading and path resolution unit tests

#### 7. **Implementation Complexity** 
**Medium complexity** - Requires modifying the `ConfigFile.load()` method to accept and use a `project_dir` parameter instead of using `config_path.parent`.

## Implementation Plan

1. **Core Change**: Modify `ConfigFile.load()` method to accept `project_dir` parameter
2. **Update Callers**: Update calls to `ConfigFile.load()` to pass the project directory
3. **Update Tests**: Modify affected tests to expect project-relative resolution for config files
4. **Update Documentation**: Revise config file examples and documentation
5. **Consider Migration**: Add version note for breaking change

## Technical Details

**Current Path Resolution Functions:**
- `resolve_relative_path(path: str, base_dir: Path) -> str` (line 196)
- `resolve_relative_volume_spec(vol_spec: str, base_dir: Path) -> str` (line 203)  
- `resolve_relative_paths_in_container_config(config: ContainerConfig, base_dir: Path)` (line 452)

**Key Change Locations:**
```python
# Lines 498 and 507 in ConfigFile.load()
config_dir = config_path.parent  # CHANGE: Don't use config file directory

defaults_config = resolve_relative_paths_in_container_config(
    defaults_config, config_dir  # CHANGE: Use project_dir instead
)

container_config = resolve_relative_paths_in_container_config(
    container_config, config_dir  # CHANGE: Use project_dir instead
)
```

**Method Signature Change Needed:**
```python
# Current
@staticmethod  
def load(config_path: Path) -> "ConfigFile":

# New
@staticmethod
def load(config_path: Path, project_dir: Path) -> "ConfigFile":
```

## Risk Assessment

- **Technical Risk**: Low - well-isolated change with existing infrastructure
- **Breaking Change Risk**: Medium - affects existing config files with relative paths
- **User Expectation Risk**: Low - aligns with industry standard behavior users expect from modern dev tools
- **Test Coverage**: Good - comprehensive test suite already exists

## Industry Precedent

This change follows the established pattern used by virtually all modern development tools where config file relative paths resolve from the project root, not the config file location. Users already have this mental model from working with:

- **Git**: `.gitignore`, `.gitattributes` paths
- **JavaScript/Node**: `package.json`, `jest.config.js`, `webpack.config.js`, `rollup.config.js` 
- **Rust**: `Cargo.toml` dependencies and paths
- **Java**: `build.gradle`, `pom.xml` paths
- **Python**: `pyproject.toml`, `setup.cfg` paths
- **Docker**: `Dockerfile` COPY/ADD paths (when using build context)

ctenv's current behavior (config-file-relative paths) is actually the outlier that breaks user expectations.
