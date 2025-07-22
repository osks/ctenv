---
id: task-30
title: Bundle gosu binaries in Python package
status: Done
assignee: []
created_date: '2025-07-19'
labels: [enhancement, packaging, distribution, security]
dependencies: []
---

## Description

Bundle gosu binaries directly in the Python package instead of downloading them at setup time. This would eliminate the need for `ctenv setup` and provide immediate functionality after package installation.

## Benefits

- **Zero setup**: Works immediately after `pip install ctenv`
- **Offline usage**: No internet required after installation
- **Reliability**: No download failures or network issues
- **Faster startup**: No runtime binary discovery needed
- **Simpler UX**: Eliminates `ctenv setup` step entirely

## Consequences & Considerations

### Package Size Impact
- **Current**: ~50KB Python-only package
- **With gosu**: ~9MB total (gosu-amd64: ~2.4MB, gosu-arm64: ~2.4MB)
- **Comparison**: Similar to packages like `docker` (~8MB) or `tensorflow` (~500MB)

### Distribution Complexity
- Need platform-specific wheels or universal wheel with multiple binaries
- PyPI upload size increase (may hit limits for some CI systems)
- Installation time increase due to larger download

### Security Implications
- **Pro**: Verified binaries bundled at build time with known checksums
- **Con**: Package becomes attack target - compromised package = compromised gosu
- **Current**: Runtime download allows verification against live checksums
- **Mitigation**: Strong package signing, reproducible builds

### Platform Support
- Currently supports any platform where gosu binaries exist
- Bundling limits to pre-built architectures (linux/amd64, linux/arm64)
- Need architecture detection at runtime to select correct binary

### Licensing & Legal
- Must include gosu's Apache 2.0 license in package
- Verify redistribution compliance
- Consider whether bundling affects ctenv's license terms

## Critical Questions to Resolve

1. **Security model preference**: Accept larger attack surface for better UX? ✅ **Yes - acceptable compromise**
2. **Package size tolerance**: Is 9MB acceptable for the target audience? ✅ **Yes - package size is fine**
3. **Platform strategy**: Universal wheel with all binaries vs platform-specific wheels? ✅ **Universal wheel**
4. **Fallback behavior**: Should we keep download capability as backup? ✅ **Keep --gosu-path CLI arg to override bundled binaries**
5. **Update mechanism**: How to handle gosu security updates without new ctenv releases? ✅ **New ctenv releases (gosu updates are rare)**

## Implementation Approach

### Package Structure Migration
Move from single-file to proper package structure:
```
ctenv/
├── __init__.py       # Package init with version
├── __main__.py       # Enables `python -m ctenv`
├── cli.py            # Main logic (formerly ctenv.py)
└── binaries/
    ├── gosu-amd64
    └── gosu-arm64
```

### Universal Wheel Approach
- Single wheel containing all platform binaries
- Runtime platform detection to select correct binary
- `pyproject.toml` changes:
  ```toml
  [tool.setuptools]
  packages = ["ctenv"]  # Change from py-modules
  include-package-data = true
  
  [tool.setuptools.package-data]
  ctenv = ["binaries/*"]
  ```

### Benefits of Package Structure
- Enables `python -m ctenv` execution
- Clean separation of binaries from code
- Maintains both `ctenv` command and module interface
- Future extensibility for additional modules

### Override Mechanism
- Keep `--gosu-path` CLI argument to override bundled binaries
- Allows use without bundled binaries (e.g., for custom builds or testing)
- Priority: CLI arg > bundled binary > error

## Success Metrics

- Zero-setup installation working on both amd64/arm64
- No functionality regression
- Package size impact acceptable to users
- Build/release pipeline working reliably

## Dependencies

- Requires build system changes (pyproject.toml)
- CI/CD updates for binary inclusion
- Documentation updates to remove setup step
