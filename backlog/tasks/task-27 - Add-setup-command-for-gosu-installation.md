---
id: task-27
title: Add setup command for gosu installation
status: To Do
assignee: []
created_date: '2025-07-15'
updated_date: '2025-07-15'
labels: [enhancement, user-experience]
dependencies: []
---

## Description

Add a `ctenv setup` command that downloads gosu binaries for all platforms. This eliminates the need for users to manually install gosu while keeping `ctenv run` fast with no network operations.

## Requirements

### Download all platform variants
Download gosu binaries for all supported platforms to `~/.ctenv/`:
- `gosu-amd64` - For linux/amd64 containers
- `gosu-arm64` - For linux/arm64 containers  
- `gosu-darwin-amd64` - For macOS/amd64 hosts
- `gosu-darwin-arm64` - For macOS/arm64 hosts

### User experience
```bash
$ ctenv setup
🔧 Setting up ctenv...

Downloading gosu binaries for all platforms...
✓ Downloaded gosu-amd64 (linux/amd64)
✓ Downloaded gosu-arm64 (linux/arm64)
✓ Downloaded gosu-darwin-amd64 (macOS/amd64)
✓ Downloaded gosu-darwin-arm64 (macOS/arm64)

ctenv is ready to use! Try: ctenv run -- echo hello
```

### Error handling
When gosu is not found during `ctenv run`:
```
Error: gosu binary not found

To fix this, either:

1. Run setup (recommended):
   ctenv setup

2. Download manually:
   wget -O ~/.ctenv/gosu-amd64 https://github.com/tianon/gosu/releases/latest/download/gosu-amd64

3. Install from package manager:
   Ubuntu/Debian:  sudo apt install gosu
   macOS:         brew install gosu
```

### Implementation details

1. **Add setup command**:
   - Download from `https://github.com/tianon/gosu/releases/latest/download/`
   - Support `--force` flag to re-download
   - Show progress for each download
   - Set executable permissions (0o755)

2. **Update find_gosu_binary()**:
   - Search for platform-specific binaries first (e.g., `gosu-amd64`)
   - Fall back to generic `gosu` if needed
   - Keep existing search paths (.ctenv directories, PATH)

3. **Improve error messages**:
   - Clear instructions for running setup
   - Platform-specific download commands
   - Package manager alternatives

## Benefits

- **Zero friction**: New users just run `ctenv setup` once
- **Fast execution**: No network calls during `ctenv run`
- **Multi-arch support**: Works with different container architectures on same host
- **Clear guidance**: Actionable error messages when gosu is missing