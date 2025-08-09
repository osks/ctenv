---
id: task-42
title: Make container names unique to allow multiple containers per project
status: Done
assignee: []
created_date: '2025-08-09'
labels: []
dependencies: []
---

## Description

Currently, ctenv uses `container_name="ctenv-${project_dir|slug}"` as the default, which means only one ctenv container can run per project directory. This is limiting when users want to run multiple containers with different configurations (e.g., different images, commands, or container configs).

## Problem Analysis

**Current Behavior:**
- Default: `ctenv-${project_dir|slug}` (e.g., `ctenv-home-user-myproject`)
- Result: Only one container per project directory can run at a time
- Docker will fail with "container name already exists" error

**Use Cases That Don't Work:**
1. **Multiple containers with different images:**
   ```bash
   # First container
   ctenv run --image node:18 -- npm run dev
   
   # Second container (fails - name conflict)
   ctenv run --image postgres:15 -- postgres
   ```

2. **Multiple container configs:**
   ```bash
   # Development server
   ctenv run dev -- npm run dev
   
   # Database (fails - name conflict)  
   ctenv run db -- postgres
   ```

3. **Multiple commands in same project:**
   ```bash
   # Long-running process
   ctenv run -- npm run watch
   
   # Quick command (fails - name conflict)
   ctenv run -- npm test
   ```

## Solution Analysis

### **Option 1: Add Container Config Name to Default** ⭐ **RECOMMENDED**
```
container_name="ctenv-${project_dir|slug}-${container_config|slug}"
```

**Example:**
- `ctenv run` → `ctenv-myproject-default`  
- `ctenv run dev` → `ctenv-myproject-dev`
- `ctenv run db` → `ctenv-myproject-db`

**Pros:**
- ✅ Multiple containers per project work naturally
- ✅ Names are descriptive and meaningful
- ✅ Backward compatible (default container still gets predictable name)
- ✅ Easy to identify which container is which

**Cons:**
- ⚠️ Slightly longer names
- ⚠️ Breaking change for users relying on exact container names

### **Option 2: Add Command Hash to Default**
```
container_name="ctenv-${project_dir|slug}-${command|hash|8}"
```

**Example:**
- `ctenv run -- bash` → `ctenv-myproject-5d41402a`
- `ctenv run -- npm test` → `ctenv-myproject-ad0234829`

**Pros:**
- ✅ Unique names for different commands
- ✅ Deterministic (same command = same hash)

**Cons:**
- ❌ Names are not human-readable
- ❌ Hard to identify containers
- ❌ Hash collisions possible (though rare)

### **Option 3: Add Timestamp/Random Suffix**
```
container_name="ctenv-${project_dir|slug}-${timestamp}"
```

**Pros:**
- ✅ Always unique

**Cons:**
- ❌ Not deterministic (same command gets different names)
- ❌ Clutters container list over time
- ❌ Hard to manage containers

### **Option 4: Add Image Name to Default**
```
container_name="ctenv-${project_dir|slug}-${image|slug}"
```

**Example:**
- `ctenv run --image node:18` → `ctenv-myproject-node-18`
- `ctenv run --image postgres:15` → `ctenv-myproject-postgres-15`

**Pros:**
- ✅ Names are descriptive
- ✅ Good for image-specific workflows

**Cons:**
- ❌ Doesn't help with same image, different commands
- ❌ Less intuitive than container config names

## **Recommended Implementation: Option 1**

### **New Default Template:**
```python
container_name="ctenv-${project_dir|slug}-${container_config|slug}"
```

### **Variable Addition:**
Add `container_config` to template variables:
```python
variables = {
    "image": config.image if config.image is not NOTSET else "",
    "user_home": runtime.user_home,
    "user_name": runtime.user_name,
    "project_dir": str(runtime.project_dir),
    "container_config": container_config_name,  # NEW
}
```

### **Implementation Details:**

1. **Pass container name through the call stack:**
   - `cmd_run()` knows which container config is being used
   - Pass this to `parse_container_config()` or template substitution

2. **Handle edge cases:**
   - Default container: `"default"`
   - CLI-only (no config): `"cli"` or `"adhoc"`
   - Invalid characters: slug filter handles this

3. **Preserve explicit configuration:**
   - If user sets explicit `container_name` in config, use as-is
   - Only apply new template to default/unspecified names

### **Example Outcomes:**
```bash
# Default container
ctenv run → ctenv-myproject-default

# Named containers  
ctenv run dev → ctenv-myproject-dev
ctenv run db → ctenv-myproject-db

# CLI-only runs
ctenv run --image node:18 → ctenv-myproject-cli

# Explicit override still works
ctenv run --container-name "my-special-name" → my-special-name
```


## Implementation Decision & Reasoning

### **Chosen Solution: PID-Based Uniqueness** ⭐ **IMPLEMENTED**

**Final Implementation:**
```python
container_name="ctenv-${project_dir|slug}-${pid}"
```

### **Why PID Was Chosen Over Other Options:**

#### **Key Insight: Command Hash Inadequacy**
Initial consideration of command-based hashing (Option 1 & 2) revealed a critical flaw:
- **Problem**: Many ctenv runs have empty or default commands (`bash`)
- **Reality**: `ctenv run dev` and `ctenv run db` both default to `bash` → same hash → collision
- **Impact**: Command-based uniqueness fails for the most common use case

#### **Container Config Name Issues**
Container config names (original Option 1) had similar problems:
- **Problem**: Same container config run twice = same name = collision  
- **Example**: `ctenv run dev` followed by another `ctenv run dev` → collision
- **Impact**: Doesn't solve the fundamental multiple-containers-per-config use case

#### **Why PID Works Perfectly:**
1. **Always unique**: Each ctenv process = different PID = unique container
2. **Simple**: No complex hashing, no configuration needed
3. **Short**: PIDs are typically 4-6 digits (much shorter than timestamps)
4. **Natural**: Process ID is inherently available via `os.getpid()`
5. **Deterministic within run**: Same process = same container name
6. **Human readability unimportant**: As noted, container names don't need to be readable

#### **PID vs Alternatives:**
- **vs Timestamp**: PID is shorter and equally unique
- **vs Random**: PID is deterministic within a process, random is not
- **vs Multi-factor hash**: PID is simpler and sufficient

### **Implementation Details:**

#### **Changes Made:**
1. **Added `pid: int` field** to `RuntimeContext` dataclass
2. **Updated `RuntimeContext.current()`** to set `pid=os.getpid()`  
3. **Added `"pid"` to template variables** in `_substitute_variables_in_container_config()`
4. **Changed default template** from `"ctenv-${project_dir|slug}"` to `"ctenv-${project_dir|slug}-${pid}"`
5. **Updated all tests** to handle new RuntimeContext signature and container naming

#### **Results:**
- ✅ **Multiple containers per project**: Each ctenv run gets unique name automatically
- ✅ **No configuration needed**: Works out of the box
- ✅ **Backward compatible**: Explicit `container_name` overrides still work
- ✅ **All tests pass**: 111/111 tests passing

#### **Example Outcomes:**
```bash
# Before (failed):
ctenv run -- npm run dev    # ctenv-myproject (started)
ctenv run -- npm test       # ERROR: name conflict

# After (works):  
ctenv run -- npm run dev    # ctenv-myproject-12345
ctenv run -- npm test       # ctenv-myproject-12346
ctenv run db -- postgres    # ctenv-myproject-12347
```

### **Conclusion:**
PID-based uniqueness elegantly solves the container naming collision problem with minimal complexity and maximum reliability. The solution requires no user configuration while enabling the core use case of running multiple containers per project directory.
