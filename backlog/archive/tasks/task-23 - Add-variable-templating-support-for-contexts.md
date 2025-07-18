---
id: task-23
title: Add variable templating support for contexts
status: Done
assignee: []
created_date: '2025-07-15'
updated_date: '2025-07-15'
labels: [enhancement]
dependencies: []
---

## Description

Add variable templating support to context configurations using `${variable}` syntax with filter support. This enables dynamic configuration values and supports use cases like bitbake cache directory naming.

## Requirements

### Core Variables
- `${USER}` - Current user name
- `${image}` - Container image name from context

### Environment Variables
- `${env:VAR_NAME}` - Environment variables from host

### Filters
- `${image|slug}` - Convert to filesystem-safe string (replace `:` and `/` with `-`)

### Scope
Support templating in:
- `volumes` array
- `env` array  
- Other string fields in contexts

## Example Usage

```toml
[contexts.bitbake]
image = "docker.office.internal:5000/builder/mainline:rocky8-v5"
volumes = ["bitbake-caches-user-${USER}:/var/cache/bitbake:rw,chown"]
env = [
    "BB_NUMBER_THREADS=${env:BB_NUMBER_THREADS}",
    "BITBAKE_CACHES_DIR=/var/cache/bitbake/bitbake-caches-${image|slug}"
]
```

## Implementation Notes

### Sample Implementation (~25 lines)

```python
import re
import os
import getpass

def substitute_template_variables(text: str, variables: dict[str, str]) -> str:
    """Substitute ${var} and ${var|filter} patterns in text."""
    pattern = r'\$\{([^}|]+)(?:\|([^}]+))?\}'
    
    def replace_match(match):
        var_name, filter_name = match.groups()
        
        # Get value
        if var_name.startswith("env:"):
            value = os.environ.get(var_name[4:], "")
        else:
            value = variables.get(var_name, "")
        
        # Apply filter
        if filter_name == "slug":
            value = value.replace(":", "-").replace("/", "-")
        elif filter_name is not None:
            raise ValueError(f"Unknown filter: {filter_name}")
        
        return value
    
    return re.sub(pattern, replace_match, text)

def substitute_in_context(context_data: dict, variables: dict[str, str]) -> dict:
    """Apply variable substitution to all string values in context."""
    result = {}
    for key, value in context_data.items():
        if isinstance(value, str):
            result[key] = substitute_template_variables(value, variables)
        elif isinstance(value, list):
            result[key] = [
                substitute_template_variables(item, variables) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value
    return result
```

### Integration Points

1. **In ConfigFile.resolve_context()** - Apply templating when resolving contexts:
   ```python
   def resolve_context(self, context_name: str) -> Dict[str, Any]:
       context_data = self.contexts.get(context_name, {}).copy()
       
       # Prepare template variables
       variables = {
           "USER": getpass.getuser(),
           "image": context_data.get("image", ""),
       }
       
       # Apply templating
       return substitute_in_context(context_data, variables)
   ```

2. **Total code addition**: ~25 lines for full templating support