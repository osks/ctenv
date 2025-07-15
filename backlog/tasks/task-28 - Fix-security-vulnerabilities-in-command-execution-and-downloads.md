---
id: task-28
title: Fix security vulnerabilities in command execution and downloads
status: To Do
assignee: []
created_date: '2025-07-15'
labels: [security, high-priority, vulnerability]
dependencies: []
---

## Description

Address critical security vulnerabilities identified in code review that could allow command injection and compromised binary downloads. These issues pose significant security risks and should be fixed before any production use.

## Critical Vulnerabilities

### 1. Command Injection in Entrypoint Commands
**Location**: `build_entrypoint_script()` lines 490-494
**Risk**: HIGH - Arbitrary command execution
**Issue**: User-provided entrypoint commands are directly injected into bash scripts without escaping:
```python
entrypoint_commands += f"{cmd}\n"
```

**Attack Vector**: Malicious config files with commands like:
```toml
entrypoint_commands = ["echo 'hello'; rm -rf /; echo 'world'"]
```

### 2. Path Injection in Volume Chown
**Location**: `build_entrypoint_script()` lines 480-484  
**Risk**: HIGH - Arbitrary command execution
**Issue**: Container paths aren't escaped in chown commands:
```python
chown_commands += f'if [ -d "{path}" ]; then\n'
chown_commands += f'    chown -R {config.user_id}:{config.group_id} "{path}"\n'
```

**Attack Vector**: Volume paths like:
```toml
volumes = ["host:/tmp\"; rm -rf /; echo \""]
```

### 3. Unverified Binary Downloads
**Location**: `setup()` command lines 1090-1093
**Risk**: MEDIUM - Supply chain compromise
**Issue**: Downloads gosu binaries without checksum verification:
```python
urllib.request.urlretrieve(url, binary_path)
```

**Attack Vector**: MITM attacks or compromised GitHub releases could serve malicious binaries

## Required Fixes

### Fix 1: Proper Command Escaping
```python
import shlex

# For entrypoint commands
def build_entrypoint_script(config: ContainerConfig, chown_paths: list[str] = None) -> str:
    # ... existing code ...
    if config.entrypoint_commands:
        entrypoint_commands = "\n# Execute entrypoint commands\n"
        for cmd in config.entrypoint_commands:
            # Safely escape the command for display
            escaped_cmd = cmd.replace('"', '\\"')
            entrypoint_commands += f"echo 'Executing: {escaped_cmd}'\n"
            # Use shell escaping for the actual command
            entrypoint_commands += f"{shlex.quote(cmd)}\n"
```

### Fix 2: Path Sanitization
```python
# For volume chown paths
def build_entrypoint_script(config: ContainerConfig, chown_paths: list[str] = None) -> str:
    # ... existing code ...
    if chown_paths:
        chown_commands = "\n# Fix ownership of chown-enabled volumes\n"
        for path in chown_paths:
            # Validate and escape the path
            if not path.startswith('/'):
                raise ValueError(f"Invalid container path: {path}")
            escaped_path = shlex.quote(path)
            chown_commands += f'if [ -d {escaped_path} ]; then\n'
            chown_commands += f'    chown -R {config.user_id}:{config.group_id} {escaped_path}\n'
            chown_commands += 'fi\n'
```

### Fix 3: Checksum Verification
```python
import hashlib

# Add checksum verification for gosu downloads
GOSU_CHECKSUMS = {
    "gosu-amd64": "expected_sha256_hash_here",
    "gosu-arm64": "expected_sha256_hash_here", 
    "gosu-darwin-amd64": "expected_sha256_hash_here",
    "gosu-darwin-arm64": "expected_sha256_hash_here",
}

def verify_checksum(file_path: Path, expected_hash: str) -> bool:
    """Verify SHA256 checksum of downloaded file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest() == expected_hash

# In setup() command:
try:
    urllib.request.urlretrieve(url, binary_path)
    
    # Verify checksum
    expected_hash = GOSU_CHECKSUMS.get(binary_name)
    if expected_hash and not verify_checksum(binary_path, expected_hash):
        binary_path.unlink()  # Remove bad file
        raise ValueError(f"Checksum verification failed for {binary_name}")
    
    binary_path.chmod(0o755)
    click.echo(f" ✓ Downloaded {binary_name} ({platform_desc})")
```

## Implementation Notes

- **Test thoroughly**: All fixes must include security test cases
- **Backwards compatibility**: Ensure legitimate use cases still work
- **Error handling**: Provide clear error messages for security violations
- **Documentation**: Update security considerations in documentation

## Security Test Cases

1. **Command injection tests**: Verify malicious commands are escaped
2. **Path injection tests**: Verify malicious paths are sanitized  
3. **Checksum verification**: Verify bad downloads are rejected
4. **Integration tests**: Ensure fixes don't break legitimate functionality

## Definition of Done

- [ ] All command injection vulnerabilities fixed with proper escaping
- [ ] All path injection vulnerabilities fixed with validation/escaping
- [ ] Checksum verification implemented for gosu downloads
- [ ] Security test cases added and passing
- [ ] Code review focused on security implications
- [ ] Documentation updated with security considerations
