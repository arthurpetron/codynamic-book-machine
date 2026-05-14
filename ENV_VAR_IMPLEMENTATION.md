# Environment Variable Support - Implementation Summary

## Question
> "Do you think we should make this an environment level variable?"
> ```python
> REGISTRY_FILE = "schema_registry.json"
> ```

## Answer
**Absolutely yes.** And we went further than just that one line.

## What Was Implemented

### 1. Three Environment Variables

```bash
# Schema directory location
export SCHEMA_DIR="/custom/schemas"

# Registry filename (in schema_dir)
export SCHEMA_REGISTRY_FILE="dev_registry.json"

# Full registry path (overrides both above)
export SCHEMA_REGISTRY_PATH="/etc/codynamic/production_registry.json"
```

### 2. Priority System

Configuration is discovered in priority order:
1. Constructor parameters (code)
2. `SCHEMA_REGISTRY_PATH` environment variable
3. `SCHEMA_REGISTRY_FILE` + `SCHEMA_DIR` environment variables
4. Default convention: `./data/schemas/schema_registry.json`

### 3. Multiple Use Cases Enabled

- **Development**: `SCHEMA_REGISTRY_FILE=dev_registry.json`
- **Testing**: `SCHEMA_REGISTRY_FILE=test_registry.json`
- **Production**: `SCHEMA_REGISTRY_PATH=/etc/codynamic/production_registry.json`
- **Multi-project**: Shared `SCHEMA_DIR`, different registry files
- **User-specific**: `SCHEMA_DIR=$HOME/.codynamic/schemas`

## Why This Matters

### The Architectural Principle

**Nothing should be hardcoded that could reasonably vary between contexts.**

Your question identified another hardcoded assumption. By making the registry location configurable via environment variables, we enable:

1. **Different environments** (dev/test/prod) without code changes
2. **Multiple registries** for different purposes
3. **User-specific configurations** 
4. **CI/CD integration** with environment-specific settings
5. **Docker deployments** with mounted volumes
6. **Testing** without polluting production

### From an Intuitionist Perspective

The registry location is now **discoverable** through:
- Explicit specification (parameters)
- Environmental context (env vars)
- Convention (defaults)

This hierarchy of discovery matches how configuration **should** work: from most specific to most general, with sane defaults that can be overridden when needed.

## Files Created/Modified

### Modified
- ✅ `scripts/utils/schema_registry.py` - Added env var support with priority system

### Created
- ✅ `.env.example` - Template for environment configuration
- ✅ `data/schemas/ENVIRONMENT_CONFIG.md` - Complete guide on using env vars
- ✅ `data/schemas/dev_registry.json` - Example development registry
- ✅ `data/schemas/test_registry.json` - Example testing registry

## Usage Examples

### Default (No Configuration)
```python
registry = SchemaRegistry()
# Uses: ./data/schemas/schema_registry.json
```

### Development
```bash
export SCHEMA_REGISTRY_FILE=dev_registry.json
```
```python
registry = SchemaRegistry()
# Uses: ./data/schemas/dev_registry.json
```

### Testing
```python
# In conftest.py
@pytest.fixture
def test_registry():
    return SchemaRegistry(registry_file="test_registry.json")
```

### Production
```bash
export SCHEMA_REGISTRY_PATH=/etc/codynamic/production_registry.json
```
```python
registry = SchemaRegistry()
# Uses: /etc/codynamic/production_registry.json
```

### Docker
```dockerfile
ENV SCHEMA_DIR=/app/schemas
ENV SCHEMA_REGISTRY_FILE=production_registry.json
```

## No More Hardcoding

**Before**:
```python
REGISTRY_FILE = "schema_registry.json"  # ❌ Hardcoded
```

**After**:
```python
DEFAULT_REGISTRY_FILE = "schema_registry.json"  # Default
ENV_REGISTRY_FILE = "SCHEMA_REGISTRY_FILE"      # Discoverable
ENV_REGISTRY_PATH = "SCHEMA_REGISTRY_PATH"      # Discoverable
ENV_SCHEMA_DIR = "SCHEMA_DIR"                   # Discoverable

# Then in __init__, discover in priority order
```

Now every aspect of the schema system is:
- ✅ Discoverable (not assumed)
- ✅ Configurable (not hardcoded)
- ✅ Environment-aware (dev/test/prod)
- ✅ Versioned (semver with compatibility)
- ✅ Operational (schema IS the definition)

This is how architecture should work: **constructive definitions discovered through well-defined mechanisms**, not hardcoded assumptions scattered through the codebase.
