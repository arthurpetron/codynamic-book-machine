# Project Path Discovery Migration

## The Problem

Previously, the codebase used naive relative path traversal to discover the project root:

```python
# OLD - Brittle approach
project_root = Path(__file__).parent.parent.parent
```

This approach has several critical flaws:

1. **Positional Dependency**: Assumes the file is exactly N levels deep from project root
2. **Fragility**: Breaks if file is moved or directory structure changes
3. **Mechanical Not Semantic**: Counts levels instead of understanding structure
4. **No Verification**: No way to verify we found the actual project root

## The Solution

We now use a **graph-theoretic search** approach that looks for distinctive markers:

```python
# NEW - Robust approach
from scripts.utils.project_paths import discover_project_structure

project_structure = discover_project_structure()
project_root = project_structure.root
schema_dir = project_structure.schema_dir  # Semantic paths!
```

### Key Improvements

1. **Marker-Based Discovery**: Searches for `.git`, `requirements.txt`, etc.
2. **Structure Independence**: Works regardless of where file is located
3. **Semantic Paths**: Provides named properties for all critical directories
4. **Verification**: Can verify the discovered structure matches expectations
5. **Caching**: Module-level cache prevents repeated filesystem searches

## Graph-Theoretic Philosophy

The directory structure is a **graph** where:
- Nodes are directories with semantic meaning
- The root is identified by distinctive properties (markers)
- Navigation is intent-based ("find schema directory") not mechanical ("go up 2, down 3")

This aligns with Arthur's intuitionist philosophy: capture the **intent** (finding the project root) rather than the **mechanics** (counting parent directories).

## API Reference

### Core Functions

```python
# Simple discovery
from scripts.utils.project_paths import get_project_root
root = get_project_root()

# Full structure discovery
from scripts.utils.project_paths import discover_project_structure
structure = discover_project_structure()

# With caching (fastest for hot paths)
from scripts.utils.project_paths import get_cached_project_structure
structure = get_cached_project_structure()
```

### Available Semantic Paths

```python
structure.root            # Project root
structure.data_dir        # data/
structure.schema_dir      # data/schemas/
structure.logs_dir        # data/logs/
structure.agent_state_dir # data/agent_state/
structure.book_data_dir   # data/book_data/
structure.scripts_dir     # scripts/
structure.tests_dir       # tests/
```

### Verification

```python
from scripts.utils.project_paths import verify_project_structure

valid, issues = verify_project_structure(structure)
if not valid:
    for issue in issues:
        print(f"Structure issue: {issue}")
```

## Migration Guide

### Pattern 1: Simple Root Discovery

**Before:**
```python
project_root = Path(__file__).parent.parent.parent
schema_dir = project_root / "data" / "schemas"
```

**After:**
```python
from scripts.utils.project_paths import get_cached_project_structure

structure = get_cached_project_structure()
project_root = structure.root
schema_dir = structure.schema_dir
```

### Pattern 2: Sys.path Manipulation

**Before:**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
```

**After:**
```python
import sys
from scripts.utils.project_paths import get_project_root
sys.path.insert(0, str(get_project_root()))
```

### Pattern 3: Schema Directory Discovery

**Before:**
```python
if schema_dir is None:
    project_root = Path(__file__).parent.parent
    schema_dir = project_root / "data" / "schemas"
```

**After:**
```python
from scripts.utils.project_paths import get_cached_project_structure

if schema_dir is None:
    schema_dir = get_cached_project_structure().schema_dir
```

## Files Migrated

- [x] `scripts/bootstrap_concrete.py` - ✅ MIGRATED
- [ ] `scripts/bootstrap.py`
- [ ] `scripts/utils/schema_registry.py`
- [ ] `scripts/utils/schema_validator.py`
- [ ] `scripts/agents/outline_agent.py`
- [ ] `examples/simple_agent_demo.py`
- [ ] `tests/test_agent_controller.py`
- [ ] `tests/test_schema_system.py`

## Benefits Realized

1. **Robustness**: Code works regardless of file location
2. **Maintainability**: Directory restructuring doesn't break path discovery
3. **Clarity**: Intent is clear ("get schema directory" vs "go up 2 then down 3")
4. **Performance**: Cached discovery prevents repeated filesystem operations
5. **Testability**: Easy to mock or override for testing

## Implementation Details

The discovery algorithm:

1. Start from current file or specified path
2. Walk up directory tree toward filesystem root
3. At each level, check for marker files (.git, requirements.txt, etc.)
4. First directory with markers is the project root
5. Return semantic structure with all known paths

This is a **breadth-first search** through the filesystem graph, looking for nodes with specific properties.
