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

## CLI Design Decision

### Chosen Approach: Option B (Separate Flags)

After analysis, Option B provides better usability and handles edge cases more cleanly.

### Flag Design

**Primary flags:**
- `--workdir PATH` - Where to cd inside container (matches Docker's convention)
- `--[MOUNT_FLAG] PATH` - Which directory to mount as workspace

**Auto-mounting behavior:**
- When no mount flag specified: auto-detect workspace (project root or cwd)
- When mount flag specified: use that directory as workspace
- Working directory defaults to preserving user's relative position in workspace

### Flag Name Candidates

**Still evaluating:**
- `--dir PATH` - Short, familiar, generic
- `--workspace PATH` - Descriptive, pairs conceptually with `--workdir`

### Design Proposal: --workspace with volume syntax

**Proposed behavior:**
- `--workspace /path` - Mount `/path` to `/path`, preserve current working directory behavior  
- `--workspace /host:/container` - Mount `/host` to `/container`, preserve current working directory behavior
- `--workspace /host:/container:ro` - Mount with options, preserve current working directory behavior

**Key insight from Conflict 1:** `--workspace` should only control mounting, not working directory. The default working directory behavior (preserving user's relative position) should remain the same whether using auto-detection or explicit workspace.

**This resolves:** Use Case 1 works consistently between auto-detection and explicit workspace specification.

### Design Clarifications for Volume Syntax Proposal

**Clarification 1: Workspace flag should preserve working directory behavior** *(from Use Case 1)*

*Reference: Use Case 1 - Developer working in project subdirectory*

```bash
# User in: /home/user/myproject/src/
# Use Case 1 with auto-detection: mount project root, preserve relative position
ctenv run -- python -m pytest ../tests/  # Works in /home/user/myproject/src/

# With updated proposal - explicit workspace preserves working directory behavior:
ctenv run --workspace /home/user/myproject -- python -m pytest ../tests/
# Fixed: Still runs from /home/user/myproject/src/ - consistent with auto-detection
```

**Clarification 2: Auto-detection is the intended default** *(from Use Case 2)*

*Reference: Use Case 2 - Project work requiring different working directory*

This isn't actually a conflict because auto-detection is the intended default behavior:

```bash
# User in: /home/user/myproject/src/components/
# Use Case 2 - normal usage relies on auto-detection (no --workspace needed):
ctenv run --workdir ../../build -- make

# User would only specify --workspace when overriding auto-detection:
ctenv run --workspace /different/project --workdir /different/project/build -- make
# This verbosity is expected since user is doing something non-standard
```

*The volume syntax is intended for Use Cases 3 & 4 where auto-detection doesn't give the desired workspace.*

**Clarification 3: Clear separation of flag responsibilities**

With the updated design where `--workspace` only controls mounting:

```bash
# This is now clear: --workspace controls mount, --workdir controls where to cd
ctenv run --workspace /home/user/myproject --workdir /home/user/myproject/src -- npm test
# Mount: /home/user/myproject → /home/user/myproject
# Working dir: /home/user/myproject/src
# No conflict - each flag has a distinct purpose
```

*Since `--workspace` no longer implies a working directory, there's no precedence ambiguity.*

### CLI Examples

```bash
# Auto-detection (most common case)
ctenv run -- npm test                          # Auto-mount workspace, preserve cwd

# Override working directory only  
ctenv run --workdir /workspace/build -- make   # Auto-mount, cd to /workspace/build

# Explicit workspace (simple form)
ctenv run --workspace /path/to/project -- npm test    # Mount and cd to /path/to/project

# Explicit workspace with different workdir
ctenv run --workspace /path/to/project --workdir /path/to/project/src -- npm test

# Volume-style options
ctenv run --workspace /host:/container:ro -- ls       # Mount with options, cd to /container
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
ctenv run --[MOUNT_FLAG] /home/user/projects --workdir /home/user/projects/web-scraper -- python scrape.py

# Now you can access other projects:
ctenv run --[MOUNT_FLAG] /home/user/projects --workdir /home/user/projects/web-scraper -- ls ../shared-utils/
ctenv run --[MOUNT_FLAG] /home/user/projects --workdir /home/user/projects/web-scraper -- python ../data-processor/clean.py
```

**Use Case 4: Advanced: Explicit workspace control**

*Scenario:* You're doing cross-project development or need to mount a specific directory that's not your current location or auto-detected project root. For example, you're in project A but need to run tools that operate on project B.

```bash
# Force specific directory as workspace, with custom working directory
ctenv run --[MOUNT_FLAG] /path/to/project-b --workdir /path/to/project-b/tools -- ./deploy.sh
```

### Auto-Detection Algorithm

**Step 1: Determine workspace**
1. If mount flag provided: use specified directory
2. If no mount flag: search for `.ctenv.toml` starting from current directory, traversing up
3. If `.ctenv.toml` found: workspace = that directory
4. If no `.ctenv.toml` found: workspace = current working directory

**Step 2: Determine working directory**
1. If `--workdir` provided: use specified path
2. If no `--workdir`: preserve user's current location relative to workspace

**Step 3: Mount and execute**
1. Mount: `workspace_path → workspace_path` (same path in container)
2. Set container working directory to computed working directory
3. Execute command

**Navigation benefits:**
- `cd ..` works naturally to navigate up to parent directories
- Relative paths work as expected
- Project structure preserved in container

### Configuration File Design

**Configuration supports the same flags as CLI:**

```toml
[defaults]
# Default workspace (when auto-detection doesn't apply)
# Flag name TBD: "dir" or "workspace"
dir = "/workspace"              # Mount workspace to /workspace
workdir = "/workspace"          # cd to /workspace

[containers.dev]
image = "node:20"
workdir = "/workspace/app"      # Override working directory for this container

[containers.build]
image = "alpine:latest"
dir = "/build"                  # Override workspace mount for this container
workdir = "/build"
```

**Precedence (highest to lowest):**
1. CLI flags
2. Container-specific config
3. Default config  
4. Auto-detection

### Examples

**Project structure:**
```
myproject/
├── .ctenv.toml
├── src/
│   └── components/
└── tests/
```

**Running from subdirectory:**
```bash
$ pwd
/home/user/myproject/src/components

$ ctenv run --image node:20 -- pwd
/home/user/myproject/src/components

$ ctenv run --image node:20 -- ls ../..
src  tests  .ctenv.toml  # Can see project root!
```

## Documentation Updates

### README Changes
1. **Update feature description**: Replace `/repo` examples with real paths
2. **Add project detection explanation**: How `.ctenv.toml` enables smart mounting
3. **Update CLI examples**: Show `--workdir` and mount flag usage
4. **Migration note**: Warn about breaking change, provide migration examples

### New Documentation
- **Migration guide**: How to update scripts expecting `/repo`
- **Project configuration**: Document `.ctenv.toml` project detection
- **Advanced usage**: Complex mounting scenarios and flag combinations

## Open Questions

1. **Final flag name decision**: `--dir` vs `--workspace`
2. **Volume syntax proposal**: Should mount flag support Docker-style `host:container:options` syntax?
3. **Working directory behavior**: If mount flag sets both mount and workdir, how does this interact with:
   - Project auto-detection preserving user's relative position?  
   - Option precedence when both mount flag and `--workdir` are specified?
4. **Relative path support**: Should `--workdir` support relative paths (like `../../build`)?
5. **Error handling**: What happens when project root isn't accessible/readable?
6. **Nested projects**: Behavior when multiple `.ctenv.toml` files exist in hierarchy?
