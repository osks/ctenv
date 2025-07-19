---
id: task-30
title: Bundle gosu binaries in Python package
status: To Do
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

1. **Security model preference**: Accept larger attack surface for better UX?
2. **Package size tolerance**: Is 9MB acceptable for the target audience?
3. **Platform strategy**: Universal wheel with all binaries vs platform-specific wheels?
4. **Fallback behavior**: Should we keep download capability as backup?
5. **Update mechanism**: How to handle gosu security updates without new ctenv releases?

## Implementation Approach

### Option A: Universal Wheel
```
ctenv/
├── binaries/
│   ├── gosu-amd64
│   └── gosu-arm64
└── ctenv.py  # Updated to find bundled binaries
```

### Option B: Platform-Specific Wheels
- Separate wheels for each platform
- Smaller individual downloads
- More complex build/release process

### Option C: Hybrid Approach
- Bundle binaries but keep download fallback
- Best of both worlds but more complexity

## Success Metrics

- Zero-setup installation working on both amd64/arm64
- No functionality regression
- Package size impact acceptable to users
- Build/release pipeline working reliably

## Dependencies

- Requires build system changes (pyproject.toml)
- CI/CD updates for binary inclusion
- Documentation updates to remove setup step
