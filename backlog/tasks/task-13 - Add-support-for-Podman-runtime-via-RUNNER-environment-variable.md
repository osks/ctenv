---
id: task-13  
title: Add support for Podman runtime via --runtime option and config
status: To Do
assignee: []
created_date: '2025-07-13'
updated_date: '2025-07-22'
labels: [enhancement, runtime, compatibility]
dependencies: []
priority: medium
---

## Description

Add support for Podman as an alternative container runtime to Docker. The Python implementation should support both CLI and configuration-based runtime selection.

**Phase 1**: Basic Podman support working exactly like Docker (rootful mode)
**Phase 2**: Future enhancement for rootless Podman with user namespace mapping

## Current State Analysis

**Existing Docker Dependencies:**
- `"docker"` hardcoded in `ContainerRunner.build_run_args()` line 789
- `shutil.which("docker")` runtime detection in `run_container()` line 902  
- Docker-specific error messages and logging
- Volume mount SELinux `:z` labeling (compatible with both runtimes)

**Shell Script Reference:**
The existing `ctenv.sh` supports runtime selection via `RUNNER="${RUNNER:-docker}"` environment variable. It includes Podman-specific `--uidmap=+$UID:@$UID` for rootless mode, which we'll implement in Phase 2.

## Implementation Plan

### 1. Add Runtime Configuration Support

**ContainerConfig additions:**
```python
@dataclass
class ContainerConfig:
    # ... existing fields ...
    runtime: Optional[str] = None  # "docker" or "podman"
```

**Default configuration:**
```python
def get_default_config_dict():
    return {
        # ... existing defaults ...
        "runtime": "docker",  # Default to docker
    }
```

### 2. CLI Option Addition

Add `--runtime` option to run command:
```python
run_parser.add_argument(
    "--runtime", 
    choices=["docker", "podman"],
    help="Container runtime to use (default: docker)"
)
```

### 3. Context Configuration Support

Allow runtime specification in TOML contexts:
```toml
[contexts.podman-dev]
runtime = "podman"
image = "registry.fedoraproject.org/fedora:latest"
```

### 4. Abstract Runtime Operations

**Add runtime abstraction to ContainerRunner:**
```python
class ContainerRunner:
    @staticmethod
    def get_runtime_command(runtime: str) -> str:
        """Get the base runtime command."""
        return runtime  # "docker" or "podman"
        
    @staticmethod 
    def validate_runtime_available(runtime: str) -> bool:
        """Check if specified runtime is available."""
        runtime_path = shutil.which(runtime)
        if not runtime_path:
            raise FileNotFoundError(f"{runtime.title()} not found in PATH. Please install {runtime}.")
        return True
```

**Phase 1 Note**: No runtime-specific arguments needed! Both Docker and Podman rootful mode work identically with gosu user switching.

### 5. Update build_run_args Method

Replace hardcoded "docker" with runtime parameter:
```python
@staticmethod
def build_run_args(
    config: ContainerConfig, entrypoint_script_path: str, verbose: bool = False
) -> List[str]:
    runtime = config.runtime or "docker"
    
    args = [
        runtime,  # Instead of "docker"  
        "run",
        "--rm",
        "--init",
    ]
    
    # ... rest of method unchanged (no special args needed for Phase 1) ...
```

### 6. Update Runtime Detection

Modify `run_container` method:
```python
@staticmethod
def run_container(config: ContainerConfig, verbose: bool = False, dry_run: bool = False):
    runtime = config.runtime or "docker"
    
    # Check if specified runtime is available
    ContainerRunner.validate_runtime_available(runtime)
    
    # ... rest of method with runtime-aware logging ...
```

## Key Design Decisions

### Runtime Option Naming: `--runtime`
**Chosen over alternatives:**
- ❌ `--runner` (matches shell script but less clear)
- ❌ `--engine` (Docker-specific terminology)
- ✅ `--runtime` (industry standard, clear, extensible)

### Environment Variable Support
Maintain compatibility with shell script by checking `RUNNER` environment variable as fallback:
```python
def get_default_config_dict():
    return {
        "runtime": os.environ.get("RUNNER", "docker"),  # Fallback to RUNNER env var
    }
```

### Runtime-Specific Differences (Phase 1)

**Both Docker and Podman (rootful mode):**
- ✅ Same command syntax (`run`, `exec`, `inspect`, etc.)
- ✅ Same `gosu` binary user switching approach  
- ✅ Same volume mounting with `:z` SELinux labeling
- ✅ Same networking model
- ✅ No special arguments needed

**Phase 2 Additions (rootless Podman):**
- Will add `--uidmap=+$UID:@$UID` for user namespace mapping
- Will require user namespace detection and handling

### Volume Mount Compatibility
Both Docker and Podman support `:z` SELinux labeling, so existing volume handling doesn't need changes.

## Testing Requirements

1. **Unit tests** for runtime abstraction methods
2. **Integration tests** for both Docker and Podman (when available)  
3. **Configuration tests** for CLI and context runtime selection
4. **Fallback tests** for RUNNER environment variable compatibility

## Success Metrics (Phase 1)

- ✅ `ctenv run --runtime podman` works with rootful Podman installations
- ✅ Context configuration `runtime = "podman"` works correctly  
- ✅ RUNNER environment variable compatibility maintained
- ✅ Runtime detection and error handling for missing runtimes
- ✅ All existing Docker functionality preserved with Podman
- ✅ No functionality regressions
- ✅ gosu user switching works identically in both runtimes

## Future Extensions

### Phase 2: Rootless Podman Support

**Major Challenges Identified:**

1. **Entrypoint `chown` Command Failures**
   - Current entrypoint script runs `chown "$USER_NAME" "$HOME"` and `chown -R "$USER_ID:$GROUP_ID" /path/to/volume`
   - In rootless mode: These commands fail with "Operation not permitted" errors
   - Container can only chown files within its user namespace mapping
   - Solution: Skip chown operations and rely on Podman's mount-time ownership handling

2. **Volume `:chown` Option Conflicts**
   - ctenv's custom `:chown` option: `volumes = ["cache:/var/cache:chown"]` 
   - Podman's native `:U` option: `podman run -v /host:/container:U`
   - Conflict: Both handle ownership but differently (runtime vs mount-time)
   - ctenv's `:chown` fails in rootless mode, Podman's `:U` works but has performance costs

3. **Implementation Questions to Resolve:**
   - How to detect rootless vs rootful Podman mode?
   - Should ctenv automatically convert `:chown` → `:U` for rootless Podman?
   - Should both syntaxes be supported with user choice?
   - How to handle entrypoint scripts that can't run chown commands?
   - Performance implications of Podman's `:U` recursive chown for large volumes?

**Implementation Areas:**
- Add user namespace detection (`podman unshare` check)  
- Implement `--uidmap=+$UID:@$UID` for rootless mode
- Add runtime mode detection (rootful vs rootless)
- Handle networking differences in rootless mode
- Resolve volume ownership handling strategy
- Adapt entrypoint script generation for rootless constraints

### Phase 3: Additional Runtimes
- containerd with nerdctl
- Docker Desktop alternatives  
- Custom runtime implementations

## Simplified Implementation for Phase 1

**Phase 1 is much simpler than initially planned because:**
1. **No special arguments needed** - Podman rootful works like Docker
2. **Same gosu approach** - No user namespace complexity  
3. **Just replace "docker" → runtime variable** - Minimal changes
4. **Same volume/network handling** - Existing code works unchanged
5. **No chown conflicts** - ctenv's `:chown` volume option works perfectly in rootful mode
6. **No entrypoint issues** - All `chown` commands work when container runs as root

This makes Phase 1 implementation very straightforward while keeping the door open for rootless enhancements later.

**Key Decision**: Starting with rootful Podman support avoids the complex ownership and permission challenges that emerge in rootless mode, allowing us to deliver basic Podman compatibility quickly and then address rootless mode as a separate, well-researched enhancement.
