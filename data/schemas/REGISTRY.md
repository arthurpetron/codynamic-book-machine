# Schema Registry System

## Overview

The Codynamic Book Machine uses a **Schema Registry** for dynamic schema discovery and version management. This ensures that:

1. **No hardcoded version numbers** - schemas are discovered at runtime
2. **Single source of truth** - the registry defines what's current
3. **Proper semantic versioning** - major.minor.patch with compatibility tracking
4. **Automatic discovery** - can bootstrap from filesystem if registry is missing

## Registry Structure

The registry is defined in `schema_registry.json`:

```json
{
  "schemas": {
    "work_outline": {
      "latest": "2.1.0",
      "stable": "2.1.0",
      "versions": {
        "2.1.0": {
          "json_file": "work_outline_schema_2.1.0.json",
          "yaml_file": "work_outline_schema_2.1.0.yaml",
          "released": "2024-11-21",
          "status": "current",
          "breaking_changes": false,
          "changelog": "...",
          "compatible_with": ["2.0.0"]
        }
      }
    }
  }
}
```

## File Naming Convention

Schema files follow strict naming:
```
{schema_name}_{major}.{minor}.{patch}.{format}
```

Examples:
- `work_outline_schema_2.1.0.json`
- `work_outline_schema_2.1.0.yaml`
- `work_outline_schema_2.0.0.json`

## Usage

### Using the Registry Directly

```python
from scripts.utils.schema_registry import get_registry

# Get registry instance
registry = get_registry()

# List available schemas
schemas = registry.get_schema_names()

# Get latest version
latest = registry.get_latest_version("work_outline")

# Load a specific version
schema = registry.load_schema("work_outline", version="2.1.0")

# Load latest automatically
schema, version = get_latest_schema("work_outline")
```

### Using the Validator

```python
from scripts.utils.schema_validator import SchemaValidator

# Use latest version (default)
validator = SchemaValidator()

# Use specific version
validator = SchemaValidator(version="2.0.0")

# Use stable version instead of latest
validator = SchemaValidator(use_latest=False)

# Validate an outline
is_valid, errors = validator.validate(outline_dict)
```

### Command Line

Test the registry:
```bash
cd scripts/utils
python schema_registry.py
```

Validate an outline:
```bash
cd scripts/utils
python schema_validator.py
```

## Version Statuses

- **current**: The actively developed version
- **stable**: Recommended for production use
- **deprecated**: Old version, use newer version
- **experimental**: Preview/beta version

## Adding a New Schema Version

1. **Create the schema files** with proper naming:
   ```
   work_outline_schema_X.Y.Z.json
   work_outline_schema_X.Y.Z.yaml
   ```

2. **Update `schema_registry.json`**:
   ```json
   "X.Y.Z": {
     "json_file": "work_outline_schema_X.Y.Z.json",
     "yaml_file": "work_outline_schema_X.Y.Z.yaml",
     "released": "YYYY-MM-DD",
     "status": "current",
     "breaking_changes": true/false,
     "changelog": "What changed",
     "compatible_with": ["older", "versions"]
   }
   ```

3. **Update latest/stable pointers** if needed:
   ```json
   "latest": "X.Y.Z",
   "stable": "X.Y.Z"
   ```

## Semantic Versioning Rules

- **Patch (X.Y.Z)**: Bug fixes, clarifications, no breaking changes
- **Minor (X.Y.0)**: New optional fields, backward compatible
- **Major (X.0.0)**: Breaking changes, structural reorganization

## Automatic Discovery

If `schema_registry.json` is missing or corrupted, the system will:

1. Scan the schemas directory for files matching the naming pattern
2. Parse version numbers from filenames
3. Auto-generate a minimal registry
4. Print a warning and continue

This provides **graceful degradation** - the system can still function even if the registry is lost.

## Why This Matters (Intuitionist Perspective)

From an **intuitionist standpoint**, the schema is the **constructive definition** of what an outline is. Having a registry that:

- Tracks versions explicitly
- Documents compatibility
- Enables discovery

...ensures that the system's **operational behavior** is grounded in **actual, discoverable structure**, not hardcoded assumptions.

The registry itself is a schema - a meta-schema that defines how to find and interpret other schemas. This recursive structure is precisely aligned with codynamic principles.

## Migration from Hardcoded Versions

Old code that did:
```python
schema_path = schema_dir / "work_outline_schema_v2.json"  # ❌ BAD
```

Now does:
```python
registry = get_registry()
schema_path = registry.get_schema_path("work_outline")  # ✅ GOOD
```

## See Also

- `schema_registry.py` - Registry implementation
- `schema_validator.py` - Schema-based validation
- `CHANGELOG.md` - Version history
- `SCHEMA_DOCUMENTATION.md` - Full schema documentation
