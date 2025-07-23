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
- Provide clear error messages when gosu binary is not found

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

### 1. Import Detection
- Detect if running as installed package vs single file
- Use `__package__` or check for `ctenv.binaries` module availability
- Example approach:
```python
def is_installed_package():
    try:
        import ctenv.binaries
        return True
    except ImportError:
        return False
```

### 2. Binary Path Resolution
- Installed package: Use `importlib.resources` or `pkg_resources`
- Single file: Require manual specification
- Fallback chain for robustness

### 3. Version Management
- Single file: Embed version constant
- Package: Read from __init__.py or use importlib.metadata
- Keep versions synchronized

### 4. Testing Strategy
- Test single-file execution
- Test package installation
- Test binary discovery in both modes
- Ensure backward compatibility

## Benefits
1. **Simplicity**: Users can grab single file for quick use
2. **Completeness**: Package installation provides full functionality
3. **Flexibility**: Works in restricted environments without package installation
4. **Distribution**: Easy to vendor or embed in other projects

## Migration Path
1. Create and test single-file version
2. Update package to use single-file as source
3. Test both execution modes thoroughly
4. Update documentation for both usage patterns
5. Consider deprecation notice for current multi-file structure

## Success Criteria
- [ ] Single ctenv.py file works standalone
- [ ] Package installation includes gosu binaries
- [ ] Binary discovery works correctly in both modes
- [ ] All existing functionality preserved
- [ ] Clear documentation for both usage modes
- [ ] Backward compatibility maintained
- [ ] Tests pass for both execution methods

## Notes
- Consider using `__file__` and path manipulation carefully
- Ensure LICENSE files are properly included in package
- Document the tradeoff between convenience and functionality
- Consider providing a download script for gosu binaries in single-file mode

## Assignee
Unassigned

## Blocked By
None

## Tags
refactoring, packaging, architecture
