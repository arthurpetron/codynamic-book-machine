# Environment Configuration Guide

## Environment Variables for Schema System

The schema system now supports full configuration via environment variables, enabling different configurations for development, testing, and production without code changes.

## Available Environment Variables

### 1. `SCHEMA_DIR`
**Purpose**: Override the schema directory location  
**Default**: `{project_root}/data/schemas`  
**Example**:
```bash
export SCHEMA_DIR="/opt/codynamic/schemas"
export SCHEMA_DIR="$HOME/.codynamic/schemas"
```

### 2. `SCHEMA_REGISTRY_FILE`
**Purpose**: Override registry filename (used with schema_dir)  
**Default**: `schema_registry.json`  
**Example**:
```bash
export SCHEMA_REGISTRY_FILE="production_registry.json"
export SCHEMA_REGISTRY_FILE="test_registry.json"
export SCHEMA_REGISTRY_FILE="schema_registry_v2.json"
```

### 3. `SCHEMA_REGISTRY_PATH`
**Purpose**: Full path to registry file (overrides dir + filename)  
**Default**: None (uses dir + filename)  
**Example**:
```bash
export SCHEMA_REGISTRY_PATH="/etc/codynamic/production_registry.json"
export SCHEMA_REGISTRY_PATH="$HOME/.config/codynamic/registry.json"
```

## Priority Order

When multiple configuration methods are used, priority is:

1. **Constructor parameters** (highest priority)
   ```python
   registry = SchemaRegistry(registry_path="/custom/registry.json")
   ```

2. **SCHEMA_REGISTRY_PATH** environment variable
   ```bash
   export SCHEMA_REGISTRY_PATH="/path/to/registry.json"
   ```

3. **SCHEMA_REGISTRY_FILE** + **SCHEMA_DIR** environment variables
   ```bash
   export SCHEMA_DIR="/custom/schemas"
   export SCHEMA_REGISTRY_FILE="custom_registry.json"
   # Results in: /custom/schemas/custom_registry.json
   ```

4. **SCHEMA_REGISTRY_FILE** + default schema_dir
   ```bash
   export SCHEMA_REGISTRY_FILE="test_registry.json"
   # Results in: {project}/data/schemas/test_registry.json
   ```

5. **Default convention** (lowest priority)
   - Location: `{project}/data/schemas/schema_registry.json`

## Use Cases

### Development Environment

```bash
# .env.development
export SCHEMA_REGISTRY_FILE="dev_registry.json"
export SCHEMA_DIR="/Users/arthur/dev/codynamic-schemas"
```

This allows experimentation with new schemas without affecting production.

### Testing Environment

```bash
# .env.test
export SCHEMA_REGISTRY_FILE="test_registry.json"
```

Or use constructor in test setup:
```python
# conftest.py
@pytest.fixture
def test_registry():
    return SchemaRegistry(registry_file="test_registry.json")
```

### Production Environment

```bash
# .env.production
export SCHEMA_REGISTRY_PATH="/etc/codynamic/production_registry.json"
export SCHEMA_DIR="/opt/codynamic/schemas"
```

### Multi-Project Setup

```bash
# Shared schemas, different registries per project
export SCHEMA_DIR="/shared/schemas"

# Project A
export SCHEMA_REGISTRY_FILE="project_a_registry.json"

# Project B  
export SCHEMA_REGISTRY_FILE="project_b_registry.json"
```

### Local User Configuration

```bash
# User-specific schemas
export SCHEMA_DIR="$HOME/.codynamic/schemas"
export SCHEMA_REGISTRY_FILE="my_registry.json"
```

## Example Configurations

### 1. Default Configuration
```python
# Uses {project}/data/schemas/schema_registry.json
registry = SchemaRegistry()
```

### 2. Custom Registry File
```python
# Uses {project}/data/schemas/experimental_registry.json
registry = SchemaRegistry(registry_file="experimental_registry.json")
```

### 3. Custom Directory
```python
# Uses /custom/path/schema_registry.json
registry = SchemaRegistry(schema_dir="/custom/path")
```

### 4. Full Custom Path
```python
# Uses exact path provided
registry = SchemaRegistry(registry_path="/exact/path/to/custom.json")
```

### 5. Environment-Based
```bash
# Set in shell or .env file
export SCHEMA_DIR="/opt/schemas"
export SCHEMA_REGISTRY_FILE="prod_registry.json"
```
```python
# Automatically discovers from environment
registry = SchemaRegistry()
```

## .env File Support

Create different .env files for different environments:

**`.env.development`**:
```bash
SCHEMA_DIR=./data/schemas
SCHEMA_REGISTRY_FILE=dev_registry.json
```

**`.env.test`**:
```bash
SCHEMA_DIR=./test/schemas  
SCHEMA_REGISTRY_FILE=test_registry.json
```

**`.env.production`**:
```bash
SCHEMA_REGISTRY_PATH=/etc/codynamic/production_registry.json
SCHEMA_DIR=/opt/codynamic/schemas
```

Then load with python-dotenv:
```python
from dotenv import load_dotenv
load_dotenv('.env.production')

# Now SchemaRegistry will use production configuration
registry = SchemaRegistry()
```

## Docker Configuration

**Dockerfile**:
```dockerfile
ENV SCHEMA_DIR=/app/schemas
ENV SCHEMA_REGISTRY_FILE=production_registry.json

COPY schemas/ /app/schemas/
```

**docker-compose.yml**:
```yaml
services:
  book-machine:
    environment:
      - SCHEMA_DIR=/app/schemas
      - SCHEMA_REGISTRY_FILE=${REGISTRY_FILE:-production_registry.json}
    volumes:
      - ./schemas:/app/schemas
```

## CI/CD Integration

**GitHub Actions**:
```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    env:
      SCHEMA_REGISTRY_FILE: test_registry.json
    steps:
      - uses: actions/checkout@v2
      - run: pytest tests/
```

**GitLab CI**:
```yaml
test:
  variables:
    SCHEMA_REGISTRY_FILE: "test_registry.json"
  script:
    - pytest tests/
```

## Best Practices

1. **Use environment variables for deployment**
   - Don't hardcode paths in production code
   - Use .env files for local development

2. **Version your registries**
   - Keep old registries for rollback: `schema_registry_v1.json`, `schema_registry_v2.json`
   - Use git to track registry changes

3. **Separate environments**
   - Development: `dev_registry.json` with experimental schemas
   - Testing: `test_registry.json` with minimal schemas
   - Production: `production_registry.json` with stable schemas only

4. **Document your setup**
   - Include .env.example in your repository
   - Document which environment variables are required

5. **Validate configuration**
   ```python
   registry = SchemaRegistry()
   print(f"Using registry: {registry.registry_path}")
   print(f"Schema directory: {registry.schema_dir}")
   ```

## Migration from Hardcoded Paths

**Before** (hardcoded):
```python
schema_path = "/Users/arthur/schemas/work_outline_schema_v2.json"  # ❌
```

**After** (configurable):
```bash
# Set once in environment
export SCHEMA_DIR="/Users/arthur/schemas"
```
```python
# Automatically discovered
registry = SchemaRegistry()
schema = registry.load_schema("work_outline")  # ✅
```

## Troubleshooting

### Check Current Configuration
```python
from scripts.utils.schema_registry import SchemaRegistry

registry = SchemaRegistry()
print(f"Registry path: {registry.registry_path}")
print(f"Schema dir: {registry.schema_dir}")
print(f"Registry exists: {registry.registry_path.exists()}")
```

### Verify Environment Variables
```bash
echo $SCHEMA_DIR
echo $SCHEMA_REGISTRY_FILE
echo $SCHEMA_REGISTRY_PATH
```

### Debug Mode
```python
import os
print("Environment:")
print(f"  SCHEMA_DIR: {os.getenv('SCHEMA_DIR')}")
print(f"  SCHEMA_REGISTRY_FILE: {os.getenv('SCHEMA_REGISTRY_FILE')}")
print(f"  SCHEMA_REGISTRY_PATH: {os.getenv('SCHEMA_REGISTRY_PATH')}")

registry = SchemaRegistry()
print(f"\nResolved to: {registry.registry_path}")
```
