---
id: task-19
title: Improve gosu binary discovery with PATH fallback
status: Done
assignee: []
created_date: '2025-07-14'
updated_date: '2025-07-14'
labels: []
dependencies: []
priority: medium
---

## Description

Improve gosu binary discovery to be more flexible and user-friendly by implementing a fallback strategy that looks in multiple locations.

## Current Behavior

Currently, ctenv only looks for gosu in the script directory (`script_dir/gosu`). If the binary is not found there, ctenv fails with:
```
gosu binary not found at /path/to/script/gosu. Please ensure gosu is available.
```

## Proposed Behavior

Implement a fallback strategy that searches for gosu in the following order:

1. **PATH**: Check if `gosu` is available in the system PATH using `shutil.which("gosu")`
2. **Script directory**: Current behavior - look for `./gosu` in the script directory

## Implementation Details

- Add a `find_gosu_binary()` function that implements the search strategy
- Update `Config.gosu_path` property to use the discovery function
- Add verbose logging to show which gosu binary is being used
- Maintain backward compatibility with existing setups
- Add configuration option to override gosu path explicitly

## Benefits

- **Better user experience**: Users don't need to copy gosu to every project directory
- **System integration**: Works with system-installed gosu packages
- **Flexibility**: Supports both project-local and system-wide gosu installations
- **Reduced setup**: Less manual setup required for new projects

## Acceptance Criteria

- [ ] Implement `find_gosu_binary()` function with fallback strategy
- [ ] Update `Config.gosu_path` to use the discovery function
- [ ] Add verbose logging showing which gosu binary is selected
- [ ] Maintain backward compatibility with existing `./gosu` setups
- [ ] Add tests for different gosu discovery scenarios
- [ ] Update documentation with new gosu discovery behavior
- [ ] Add optional `--gosu-path` CLI option to override discovery
- [ ] Handle cases where gosu is not found anywhere with helpful error message

## Related Issues

- Addresses the need to manually download gosu in GitHub Actions
- Improves developer experience when setting up new projects
- Makes ctenv more suitable for system-wide installation
