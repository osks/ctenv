---
id: task-18
title: Refactor Config class to eliminate dual representation confusion
status: Done
assignee: []
created_date: '2025-07-14'
updated_date: '2025-07-14'
labels: []
dependencies: []
priority: high
---

## Description

The current Config class design is confusing because it maintains a dual representation of configuration data - both as instance attributes (self.user_name) and as dict values (self.defaults['USER_NAME']). Additionally, ContainerRunner receives a Config object in its constructor but never uses it, instead relying on dict representations passed to its methods.

## Current Problems:
- Config object has both attributes and dict values for the same data
- merge_options() returns a dict, not a Config object, creating inconsistent types
- ContainerRunner constructor takes Config but methods use dicts
- No clear separation between configuration data and behavior
- Confusing flow where Config is created, converted to dict, then passed around

## Option 1: Config as a Data Container (Recommended)
Make Config a proper dataclass that holds ALL configuration:

Benefits:
- Type safety with all fields typed and validated
- Single source of truth - no dual representation
- Clear API - Config object has all data and behavior
- Immutable - Config is created once, not modified
- Easy testing - simple to create test configs
- Backwards compatible via to_dict() method

Implementation approach:
- Use @dataclass for the Config class
- Include all configuration fields as typed attributes
- Add from_cli_options() class method for construction
- Add to_dict() for backwards compatibility
- Make ContainerRunner methods accept Config objects directly

## Option 2: Config as a Builder Pattern
Use a builder pattern for more flexible configuration:

Benefits:
- Flexible construction with method chaining
- Can validate incrementally as config is built
- Clear separation of building vs using config

Implementation approach:
- Create ConfigBuilder class with fluent interface
- Methods like with_image(), with_env(), etc.
- build() method returns final configuration
- Could return either dict or frozen Config object

## Future Requirement: Configuration Files
The design must accommodate loading configuration from files (.ctenvrc, ctenv.toml, etc.) with proper precedence:
CLI args > local config file > global config file > system defaults

This affects the design choice:

**Option 1 with Config Files:**
- EXCELLENT support - can deserialize directly into typed Config
- Add from_file() and from_multiple_sources() class methods
- Type validation happens automatically during deserialization
- Easy to provide helpful error messages for invalid config

**Option 2 with Config Files:**
- GOOD support - builder can load and merge from multiple sources
- More complex but very flexible for precedence handling

**Option 3: Layered Configuration (New)**
- Explicit layer system with ConfigLayer base class
- Can inspect where each value came from
- Very flexible but adds complexity

## Updated Recommendation:
Option 1 (dataclass) is still recommended because it provides the best balance of simplicity, type safety, and config file support. The dataclass approach works excellently with config file libraries and makes precedence clear.

## Acceptance Criteria:
- Eliminate dual representation (attributes + dict)
- Make configuration flow consistent throughout
- ContainerRunner should either use Config objects or be stateless
- Design must accommodate future config file loading with proper precedence
- Config precedence should be clear and debuggable
- All tests should pass after refactoring
- Type hints should be clear and consistent
