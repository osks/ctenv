---
id: task-35
title: Remove fixed /repo mount and implement smart project-aware directory mounting
status: To Do
assignee: []
created_date: '2025-07-25'
labels: []
dependencies: []
---

## Description

Remove the fixed `/repo` mount point. Instead mount directories using their actual paths and detect project root when possible for better navigation.

**Note: This is a breaking change with no backward compatibility** -
existing configurations and scripts expecting `/repo` will need
updates. Don't need migration documentation or anything like that,
just a clean change.

## Current Problem
- Always mounts to `/repo` - confusing abstraction
- Can't navigate up from subdirectories
- Not intuitive for general use

## Proposed Behavior

**With .ctenv.toml (project detected):**
```bash
# User cwd: /home/user/myproject/src/
# Mount: /home/user/myproject → /home/user/myproject
# Container cwd: /home/user/myproject/src/
```

**Without .ctenv.toml:**
```bash
# User cwd: /home/user/somedir/
# Mount: /home/user/somedir → /home/user/somedir
# Container cwd: /home/user/somedir
```

## Implementation Design

### Core Concepts

**Workspace**: The root directory that gets mounted into the container. This can be:
- Project root (when `.ctenv.toml` found by traversing up from current directory)
- Current working directory (when no project file found)
- Explicitly specified directory (via CLI flag)

**Working Directory**: Where to `cd` inside the container after mounting. This can be:
- User's current directory mapped to container paths (default)
- Explicitly specified path (via `--workdir` flag)

### Internal Settings Required

Internally, we need to track four distinct settings:

1. **Mount source** - Which host directory to mount (the workspace)
2. **Mount target** - Where to mount it in the container (same path as source)
3. **Mount options** - Volume options like `ro`, `rw`, `chown`
4. **Working directory** - Where to `cd` inside the container

These four settings allow for flexible scenarios:
- **Auto-detection**: Workspace and workdir derived from project detection + current location
- **Project override**: Mount project root, but cd to different subdirectory
- **Explicit control**: User specifies workspace and workdir independently

## CLI Design

### Flag Design

**Primary flags:**
- `--workdir PATH` - Where to cd inside container (matches Docker's convention)
- `--workspace PATH` - Which directory to mount (supports volume syntax)

**Volume syntax:**
- `--workspace /path` - Mount `/path` to `/path`, preserve current working directory behavior  
- `--workspace /host:/container` - Mount `/host` to `/container`, preserve current working directory behavior
- `--workspace /host:/container:ro` - Mount with options, preserve current working directory behavior

**Auto-mounting behavior:**
- When no `--workspace` specified: auto-detect workspace (project root or cwd)
- When `--workspace` specified: use that directory as workspace
- Working directory always defaults to preserving user's relative position in workspace

**Key design principle:** `--workspace` only controls mounting, never working directory. This ensures consistent behavior between auto-detection and explicit specification.

### CLI Examples

```bash
# Auto-detection (most common case)
ctenv run -- npm test                          # Auto-mount workspace, preserve cwd

# Override working directory only  
ctenv run --workdir ../../build -- make        # Auto-mount, cd to relative path

# Explicit workspace (simple form)
ctenv run --workspace /path/to/project -- npm test    # Mount different project

# Explicit workspace with different workdir
ctenv run --workspace /path/to/project --workdir /path/to/project/src -- npm test

# Volume-style options
ctenv run --workspace /host:/container:ro -- ls       # Mount with options
```

### Key Use Cases

**Use Case 1: Developer working in project subdirectory**

*Scenario:* You're working on a Python project with tests. You're currently in `/home/user/myproject/src/` working on the source code. You want to run tests from your current location, but the test command needs to access the entire project structure (test files in `/tests/`, config files in project root, etc.).

*Need:* Mount the entire project so all files are accessible, but stay in your current subdirectory where you're working.

```bash
# User in: /home/user/myproject/src/
# Project root: /home/user/myproject/ (has .ctenv.toml)  
# Result: Mount /home/user/myproject → /home/user/myproject, cd to /home/user/myproject/src/
ctenv run -- python -m pytest ../tests/

# You can navigate naturally:
ctenv run -- ls ../pyproject.toml  # Access project root
ctenv run -- cat ../tests/test_main.py  # Access test files
```

**Use Case 2: Project work requiring different working directory**

*Scenario:* You're debugging a build issue. You're currently in `/home/user/myproject/src/components/` editing source files, but you need to run build commands that expect to be executed from the `/home/user/myproject/build/` directory. You want the entire project mounted (to access source files) but need to cd to the build directory.

*Why this matters:* Many build tools expect to run from specific directories but need access to the entire project tree.

```bash
# User in: /home/user/myproject/src/components/
# Project root: /home/user/myproject/ (has .ctenv.toml)
# Want: Mount entire project, but cd to /home/user/myproject/build/

# Option 1: Use --workdir with relative path (if supported)
ctenv run --workdir ../../build -- make

# Option 2: Change directory on host first  
(cd /home/user/myproject/build && ctenv run -- make)

# Both mount the entire project, but start in build/ directory
```

**Use Case 3: Multiple small projects without .ctenv.toml**

*Scenario:* You have multiple small projects organized under `/home/user/projects/`. Each project is simple enough that you don't want to bother with .ctenv.toml files. You're currently working in `/home/user/projects/web-scraper/` but you want to mount the entire projects directory so you can easily access shared utilities or data from other projects.

*Need:* Override the auto-mounting behavior (which would only mount the current project) to mount the broader projects directory, but still work in your specific project subdirectory.

```bash
# User in: /home/user/projects/web-scraper/
# No .ctenv.toml found (would normally mount just /home/user/projects/web-scraper/)
# Want: Mount entire projects directory but stay in current subdirectory
ctenv run --workspace /home/user/projects --workdir /home/user/projects/web-scraper -- python scrape.py

# Now you can access other projects:
ctenv run --workspace /home/user/projects --workdir /home/user/projects/web-scraper -- ls ../shared-utils/
ctenv run --workspace /home/user/projects --workdir /home/user/projects/web-scraper -- python ../data-processor/clean.py
```

**Use Case 4: Advanced: Explicit workspace control**

*Scenario:* You're doing cross-project development or need to mount a specific directory that's not your current location or auto-detected project root. For example, you're in project A but need to run tools that operate on project B.

```bash
# Force specific directory as workspace, with custom working directory
ctenv run --workspace /path/to/project-b --workdir /path/to/project-b/tools -- ./deploy.sh
```

**Use Case 5: Build reproducibility with fixed paths**

*Scenario:* You're building software where paths can leak into build artifacts (compiled binaries, debug info, cached files, etc.). You need builds to be identical regardless of where the project is located on different machines or CI systems. Using real host paths like `/home/user/myproject` vs `/home/jenkins/workspace/myproject` would create different build outputs.

*Need:* Always mount workspace to a fixed, predictable path like `/repo` to ensure build reproducibility, while preserving smart project detection and working directory logic. **This should work automatically without specifying paths manually.**

```bash
# User in: /home/user/myproject/src/
# Project root: /home/user/myproject/ (has .ctenv.toml)
# With config: workspace = ".:/repo"
$ pwd
/home/user/myproject/src
$ ctenv run -- python -m pytest /repo/tests/
# Auto-detects: /home/user/myproject → /repo
# Working dir: /repo/src (preserves relative position)

# User in: /home/user/scripts/ (no project)  
# Same config applies automatically
$ pwd
/home/user/scripts
$ ctenv run -- python /repo/process.py
# Auto-detects: /home/user/scripts → /repo
# Working dir: /repo

# This ensures identical builds regardless of host path:
# Developer machine: /home/alice/myproject → /repo
# CI system: /var/lib/jenkins/workspace/myproject → /repo  
# Both produce identical artifacts since all paths inside container are /repo/*
```

**Key requirement:** This must be configurable in `.ctenv.toml` so teams can set it as a project standard:

```toml
[defaults]
workspace = ".:/repo"      # Auto-detect source (.), always mount to /repo

[containers.build]  
workspace = ".:/repo"      # Ensure build reproducibility
```

**Alternative syntax:** Using `"."` for auto-detection is more intuitive than `"auto"` - it follows standard path conventions where `.` means "current context" (auto-detected workspace in this case).

Without this config option, users would have to manually specify the full host path every time, which defeats the purpose of auto-detection.

## Implementation Details

### Auto-Detection Algorithm

1. **Determine workspace**: Search for `.ctenv.toml` from current directory upward. If found, workspace = that directory. Otherwise, workspace = current directory.
2. **Determine working directory**: If `--workdir` provided, use it. Otherwise, preserve user's current location relative to workspace.
3. **Mount and execute**: Mount `workspace → workspace`, cd to computed working directory, execute command.

### Configuration File Design

```toml
[defaults]
workspace = "/workspace"        # Default workspace mount
workdir = "/workspace"          # Default working directory

[containers.dev]
image = "node:20"
workdir = "/workspace/app"      # Override working directory

[containers.build]
image = "alpine:latest"
workspace = "/build"            # Override workspace mount
workdir = "/build"
```

**Precedence**: CLI flags > container-specific config > default config > auto-detection

## Documentation & Testing

### Documentation Updates
- Replace `/repo` examples with real paths in README
- Document `.ctenv.toml` project detection behavior
- Add migration note about breaking change
- Document `--workspace` volume syntax and `--workdir` usage

### Testing Requirements
- Project detection algorithm (with/without `.ctenv.toml`, nested projects)
- CLI argument parsing and precedence
- Mount path logic and volume syntax
- Working directory calculation
- Cross-project scenarios and edge cases

## Implementation Notes

### Path Resolution for `.:/repo` Syntax

**Config file paths** (like `workspace = ".:/repo"`) should be resolved in `ConfigFile.from_file()` before config merging:

```python
# In ConfigFile.from_file()
config_dir = config_path.parent  
# Resolve "." in workspace = ".:/repo" to absolute project path
resolved_data = resolve_relative_paths(raw_config, config_dir)
```

**CLI paths** (like `--workspace .:/repo`) should be resolved during CLI processing relative to current working directory.

This approach:
- Resolves paths immediately when files are loaded, before merging
- Preserves file context where it's available  
- Handles multiple config sources cleanly
- No changes needed to `from_dict()` or downstream code

**Relative path support**: Both `--workspace` and `--workdir` should support relative paths. For CLI args, paths are resolved relative to current working directory. For config files, paths are resolved relative to the config file location (or workspace root for `--workdir`).

## Open Questions

1. **Error handling**: What happens when project root isn't accessible/readable?
