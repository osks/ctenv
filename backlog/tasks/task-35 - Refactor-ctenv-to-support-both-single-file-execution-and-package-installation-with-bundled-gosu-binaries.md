# Task 35: Refactor ctenv to support both single-file execution and package installation with bundled gosu binaries

## Status
To Do

## Description
Refactor the ctenv implementation to work as both:
1. A standalone single-file Python script (`ctenv.py`) that can be run directly
2. An installable Python package that bundles the gosu binaries

## Requirements

### Single-File Mode
- Consolidate all functionality from `ctenv/cli.py` into a single `ctenv.py` file
- When run directly (`./ctenv.py` or `python ctenv.py`), it should work without bundled binaries
- Users must specify gosu binary paths manually via:
  - `--gosu-path` command line argument
  - Configuration file setting
- Provide error message when gosu binary is not found

### Package Mode
- When installed via pip/uv, the package should bundle gosu binaries
- Binary discovery should work automatically when installed as a package
- Maintain current binary bundling approach in `ctenv/binaries/`
- Support both execution methods:
  - `ctenv` (via entry point)
  - `python -m ctenv` (via __main__.py)

## Implementation Plan

### 1. Create Single-File Script
- Copy `ctenv/cli.py` to root as `ctenv.py`
- Make it self-contained with all necessary imports and functions
- Keep current shebang
- Ensure it can run independently without the package structure

### 2. Modify Binary Discovery Logic
```python
def find_gosu_binary():
    # 1. Check command line argument
    # 2. Check configuration file
    # 3. If running as installed package, check bundled location
    # 4. Return None if not found (single-file mode without binary)
```

### 3. Update Package Structure
**Source Structure:**
```
ctenv/
├── ctenv.py              # Single-file implementation (root)
├── pyproject.toml        # Package configuration
├── build_scripts.py      # Custom build logic
├── ctenv/
│   ├── __init__.py      # from .ctenv import *
│   ├── __main__.py      # Enable python -m ctenv
│   └── binaries/        # Bundled gosu binaries
│       ├── __init__.py
│       ├── gosu-amd64
│       └── gosu-arm64
```

**Build Directory Structure:**
```
build/
├── lib/
│   └── ctenv/
│       ├── __init__.py      # Copied from source
│       ├── __main__.py      # Copied from source
│       ├── ctenv.py         # Copied from root during build
│       └── binaries/        # Copied from source
```

### 4. Update pyproject.toml
```toml
[build-system]
requires = ["setuptools >= 77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ctenv"
# ... other settings ...

[project.scripts]
ctenv = "ctenv:main"

[tool.setuptools]
packages = ["ctenv", "ctenv.binaries"]
include-package-data = true

[tool.setuptools.package-data]
ctenv = ["binaries/*"]

[tool.setuptools.cmdclass]
build_py = "build_scripts:CustomBuildPy"
```

### 5. Build Script Strategy
**Create build_scripts.py:**
```python
from setuptools.command.build_py import build_py
import shutil
import os

class CustomBuildPy(build_py):
    def run(self):
        super().run()
        # Copy root ctenv.py into the built package
        build_lib = self.build_lib
        target = os.path.join(build_lib, 'ctenv', 'ctenv.py')
        shutil.copy('ctenv.py', target)
```

**Update ctenv/__init__.py:**
```python
# ctenv/__init__.py
from .ctenv import *
from .ctenv import __version__  # Import version from ctenv.py
```

## Technical Challenges to Resolve

### 1. Package vs Single-file Detection
- Detect if running as installed package vs single file
- Check if running from within package structure
- Example approach:
```python
def is_installed_package():
    try:
        # If we can import from package structure, we're installed
        import importlib.util
        spec = importlib.util.find_spec('ctenv.binaries')
        return spec is not None
    except ImportError:
        return False
```

### 2. Binary Path Resolution
- Installed package: Use `importlib.resources` or `pkg_resources`
- Single file: Require manual specification
- Fallback chain for robustness

### 3. Version Management
- Single file: Embed version constant in `ctenv.py`
- Package: Import version from copied `ctenv.py` (already handled by build strategy)
- No synchronization needed - single source of truth

### 4. Testing Strategy
- Test single-file execution
- Test package installation
- Test binary discovery in both modes

## Benefits
1. **Simplicity**: Users can grab single file for quick use
2. **Completeness**: Package installation provides full functionality
3. **Flexibility**: Works in restricted environments without package installation
4. **Distribution**: Easy to vendor or embed in other projects

## Migration Path
1. Create single-file `ctenv.py` from `ctenv/cli.py`
2. Create `build_scripts.py` with custom build logic
3. Update `pyproject.toml` with new build configuration
4. Update `ctenv/__init__.py` to import from copied file
5. Test both execution modes thoroughly
6. Update documentation for both usage patterns
7. Remove old `ctenv/cli.py` once migration is complete

## Success Criteria
- [ ] Single ctenv.py file works standalone
- [ ] Package installation includes gosu binaries
- [ ] Binary discovery works correctly in both modes
- [ ] All existing functionality preserved
- [ ] Clear documentation for both usage modes
- [ ] Tests pass for both execution methods

## Notes
- Binary discovery logic needs to handle both execution contexts
- Ensure LICENSE files are properly included in package
- Document the tradeoff between convenience and functionality
- Update CLAUDE.md to reflect new single-file approach
- **Backward compatibility not required** - project hasn't been released yet

## Assignee
Unassigned

## Blocked By
None

## Tags
refactoring, packaging, architecture
