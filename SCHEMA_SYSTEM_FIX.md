# Schema System Architectural Fix

## What Was Wrong

**The Problem**: Hardcoded validation rules and version numbers throughout the codebase violated the fundamental principle that **the schema should be the single source of truth**.

### Specific Issues:

1. **outline_agent.py** had hardcoded validation:
   ```python
   REQUIRED_KEYS = ["title", "summary", "intent", "chapters"]  # ❌
   ```

2. **schema_validator.py** had hardcoded paths:
   ```python
   self.json_schema_path = schema_dir / "work_outline_schema_v2.json"  # ❌
   ```

3. **No version discovery** - the system couldn't automatically find the latest schema
4. **No compatibility tracking** - no way to know which versions work together
5. **Duplication of truth** - validation rules existed in both schema files AND code

## Why This Matters (Intuitionist Perspective)

From your intuitionist philosophy:

> "The schema should be the **constructive definition** that the system actually operates on, not just aspirational documentation."

Hardcoded validation means the schema is **decorative**, not **operational**. The system isn't actually grounded in the schema - it's grounded in whatever a developer happened to write in some Python file six months ago.

This defeats the entire purpose of having a schema.

## The Solution

### 1. Schema Registry System

Created a **dynamic registry** that:
- Tracks all schema versions with semantic versioning
- Defines which version is "latest" and "stable"
- Documents compatibility between versions
- Enables automatic discovery from filesystem as fallback

**File**: `data/schemas/schema_registry.json`

### 2. Registry API

Created `scripts/utils/schema_registry.py` that provides:
- `get_latest_version(schema_name)` → automatic discovery
- `get_schema_path(schema_name, version)` → no hardcoded paths
- `load_schema(schema_name, version)` → direct loading
- Filesystem discovery if registry is missing

### 3. Schema Validator Using Registry

Rewrote `scripts/utils/schema_validator.py` to:
- Use registry for version discovery (no hardcoded "v2")
- Load actual schema definition (no duplicate validation rules)
- Support version pinning when needed
- Default to latest version automatically

### 4. Agents Use Validator

Rewrote `scripts/agents/outline_agent.py` to:
- Use SchemaValidator exclusively
- Have ZERO hardcoded validation rules
- Operate on the actual schema definition
- Generate reports based on schema structure

### 5. Proper File Naming

Renamed schema files to follow convention:
- ~~`work_outline_schema_v2.json`~~ → `work_outline_schema_2.1.0.json`
- ~~`work_outline_schema_v2.yaml`~~ → `work_outline_schema_2.1.0.yaml`

This enables programmatic parsing of version numbers.

## Current Status

### ✅ What Now Works:

1. **Automatic version discovery** - code finds latest schema without hardcoding
2. **Single source of truth** - validation reads from actual schema
3. **Version tracking** - registry documents all versions and compatibility
4. **Graceful degradation** - system can discover schemas from filesystem if registry is missing
5. **Future-proof** - adding v3.0.0 just requires updating registry, no code changes

### 📋 What's Required:

1. Install `jsonschema` package:
   ```bash
   pip install jsonschema>=4.17.0
   ```
   (Already added to requirements.txt)

2. The existing `codynamic_theory.yaml` is still in old v1.0 format - should be upgraded to v2.1

## Example Usage

### Before (Hardcoded):
```python
# ❌ This breaks when we go to v3
REQUIRED_KEYS = ["title", "summary", "intent", "chapters"]

def validate(outline):
    for key in REQUIRED_KEYS:
        if key not in outline:
            print(f"Missing: {key}")
```

### After (Registry-based):
```python
# ✅ This automatically uses current schema
from utils.schema_validator import SchemaValidator

validator = SchemaValidator()  # Discovers latest version
is_valid, errors = validator.validate(outline)
```

## The Architectural Principle

**The schema IS the definition, not documentation OF the definition.**

This fix ensures that:
1. The schema files are the **authoritative source**
2. Code **discovers** structure from schema, doesn't **duplicate** it
3. Versions are **tracked** and **discoverable**, not **assumed**
4. The system is **grounded** in constructive definitions, not hardcoded assumptions

This aligns perfectly with the intuitionist principle that structures should be **constructively defined** based on what we can **actually compute and discover**, not based on abstract existence proofs (or in this case, hardcoded assumptions).

## Files Modified

- ✅ `requirements.txt` - Added jsonschema
- ✅ `data/schemas/schema_registry.json` - NEW: Version registry
- ✅ `data/schemas/work_outline_schema_2.1.0.json` - RENAMED from v2.json
- ✅ `data/schemas/work_outline_schema_2.1.0.yaml` - RENAMED from v2.yaml
- ✅ `data/schemas/REGISTRY.md` - NEW: Registry documentation
- ✅ `scripts/utils/` - NEW: Utils directory
- ✅ `scripts/utils/__init__.py` - NEW: Utils package
- ✅ `scripts/utils/schema_registry.py` - NEW: Registry implementation
- ✅ `scripts/utils/schema_validator.py` - REWRITTEN: Uses registry
- ✅ `scripts/agents/outline_agent.py` - REWRITTEN: No hardcoded validation

## Next Steps

You can now:

1. **Test the registry**:
   ```bash
   cd scripts/utils
   python schema_registry.py
   ```

2. **Validate an outline**:
   ```bash
   cd scripts/agents
   python outline_agent.py
   ```

3. **Add new versions** by:
   - Creating `work_outline_schema_X.Y.Z.json/yaml`
   - Updating `schema_registry.json`
   - NO CODE CHANGES NEEDED

The schema is now the operational definition, exactly as it should be.
