# Bootstrap System Architecture

## Overview

The Book Machine now has a formal **multi-phase bootstrap system** similar to OS initialization. This ensures the system transitions from a minimal seed state into a fully operational runtime environment with clear error reporting at each phase.

## The Five Boot Phases

```
Phase 0: SEED        → Minimal filesystem structure
Phase 1: DISCOVERY   → Find configuration and schemas  
Phase 2: VALIDATION  → Verify everything needed exists
Phase 3: INIT        → Load schemas, create runtime state
Phase 4: READY       → System fully operational
```

## Why Bootstrap?

### The Problem (Before)
```python
# Implicit initialization - fails deep in stack
registry = SchemaRegistry()  # Where's the registry?
validator = SchemaValidator()  # Does schema exist?
agent = OutlineAgent(...)     # Are directories created?
```

### The Solution (After)
```python
# Explicit bootstrap - fails early with clear errors
system = BootstrapSystem.auto_bootstrap()
# Now everything is verified and ready
```

## Usage Patterns

### 1. Automatic Bootstrap (Recommended)

```python
from scripts.bootstrap import BootstrapSystem

# Turn on the system
system = BootstrapSystem.auto_bootstrap()

# Now everything is ready
from scripts.utils.schema_registry import SchemaRegistry
registry = SchemaRegistry()  # Guaranteed to work
```

### 2. Manual Phase-by-Phase

```python
system = BootstrapSystem()

# Run each phase explicitly
system.phase_0_seed()
system.phase_1_discovery()
system.phase_2_validation()

# Check for issues before proceeding
if system.config.errors:
    print("Cannot proceed:", system.config.errors)
    exit(1)

system.phase_3_initialization()
system.phase_4_ready()
```

### 3. Bootstrap to Specific Phase

```python
from scripts.bootstrap import BootstrapSystem, BootPhase

# Only need discovery
system = BootstrapSystem.bootstrap_to_phase(BootPhase.DISCOVERY)

# Check what was discovered
print(f"Environment: {system.config.environment}")
print(f"LLM providers: {system.config.llm_providers}")
```

## What Each Phase Does

### Phase 0: SEED
**Purpose**: Create minimal filesystem structure  
**Creates**:
- `data/schemas/` directory
- `data/logs/` directory
- `scripts/utils/` directory

**Validates**:
- Project root exists
- Can create directories

**Errors if**:
- Project structure invalid
- Permission denied

---

### Phase 1: DISCOVERY
**Purpose**: Discover configuration from environment and filesystem  
**Discovers**:
- Environment variables (`SCHEMA_DIR`, `SCHEMA_REGISTRY_FILE`, etc.)
- Schema registry location
- Available LLM providers (API keys)
- Deployment environment (dev/test/prod)

**Sets**:
- `config.schema_dir`
- `config.registry_path`
- `config.environment`
- `config.llm_providers`

**Warnings if**:
- No LLM API keys found

---

### Phase 2: VALIDATION
**Purpose**: Validate discovered configuration  
**Validates**:
- Schema directory exists and is readable
- Registry file exists and is valid JSON
- Logs directory is writable
- File permissions correct

**Errors if**:
- Schema directory missing
- Registry file corrupt
- Directories not writable

**Warnings if**:
- Registry file missing (will attempt filesystem discovery)

---

### Phase 3: INITIALIZATION
**Purpose**: Initialize services and runtime state  
**Initializes**:
- Schema registry (load or discover)
- Schema validator
- Runtime directories

**Creates**:
- `data/agent_state/` directory
- `data/logs/message_logs/` directory

**Errors if**:
- Cannot load schema registry
- Required schemas missing
- Validation errors from Phase 2

---

### Phase 4: READY
**Purpose**: Final health check and mark ready  
**Performs**:
- Health check of all subsystems
- Write bootstrap log to `data/logs/bootstrap.log`
- Mark system as operational

**Errors if**:
- Schema system health check fails
- File system health check fails
- Initialization errors from Phase 3

---

## Integration Examples

### Command-Line Tool

```python
#!/usr/bin/env python3
"""run_agent.py - Run an agent with bootstrap"""

from scripts.bootstrap import BootstrapSystem
from scripts.agents.outline_agent import OutlineAgent

def main():
    # Bootstrap system
    print("Bootstrapping system...")
    system = BootstrapSystem.auto_bootstrap()
    
    # Now run agent
    agent = OutlineAgent("data/book_data/my_book/outline.yaml")
    agent.run()

if __name__ == '__main__':
    main()
```

### Web Server

```python
from fastapi import FastAPI
from scripts.bootstrap import BootstrapSystem

# Bootstrap on startup
system = BootstrapSystem.auto_bootstrap()

app = FastAPI()

@app.get("/health")
def health():
    return {
        "status": "ready" if system.config.current_phase == BootPhase.READY else "not_ready",
        "phase": system.config.current_phase.name,
        "errors": system.config.errors
    }
```

### Testing

```python
import pytest
from scripts.bootstrap import BootstrapSystem, BootPhase

@pytest.fixture(scope="session")
def bootstrapped_system():
    """Bootstrap system once for all tests."""
    return BootstrapSystem.auto_bootstrap()

def test_schema_system(bootstrapped_system):
    assert bootstrapped_system.config.current_phase == BootPhase.READY
    # Now test with confidence that system is ready
```

### Docker Container

```dockerfile
# Dockerfile
FROM python:3.11

COPY . /app
WORKDIR /app

# Bootstrap on container start
CMD ["python", "-c", "from scripts.bootstrap import BootstrapSystem; BootstrapSystem.auto_bootstrap(); exec(open('main.py').read())"]
```

## Error Handling

### Bootstrap Errors

```python
from scripts.bootstrap import BootstrapSystem, BootstrapError

try:
    system = BootstrapSystem.auto_bootstrap()
except BootstrapError as e:
    print(f"Bootstrap failed: {e}")
    for error in e.errors:
        print(f"  - {error}")
    exit(1)
```

### Graceful Degradation

```python
system = BootstrapSystem()
system.phase_0_seed()
system.phase_1_discovery()
system.phase_2_validation()

if system.config.errors:
    print("Running in degraded mode...")
    # Continue with limited functionality
else:
    system.phase_3_initialization()
    system.phase_4_ready()
```

## Environment-Specific Bootstrap

### Development

```bash
# .env.development
ENVIRONMENT=development
SCHEMA_REGISTRY_FILE=dev_registry.json
BOOTSTRAP_VERBOSE=true
```

```python
from dotenv import load_dotenv
load_dotenv('.env.development')

system = BootstrapSystem.auto_bootstrap()
# Uses dev_registry.json, verbose output
```

### Production

```bash
# .env.production
ENVIRONMENT=production
SCHEMA_REGISTRY_PATH=/etc/codynamic/production_registry.json
BOOTSTRAP_VERBOSE=false
```

```python
from dotenv import load_dotenv
load_dotenv('.env.production')

system = BootstrapSystem.auto_bootstrap()
# Uses production registry, quiet mode
```

## Status Checking

```python
system = BootstrapSystem.auto_bootstrap()

# Print detailed status
system.print_status()

# Output:
# ==============================================================
# BOOK MACHINE SYSTEM STATUS
# ==============================================================
# Phase: READY (4)
# Environment: development
# Project Root: /path/to/codynamic-book-machine
# Schema Dir: /path/to/data/schemas
# Registry: /path/to/schema_registry.json
# LLM Providers: openai, anthropic
# 
# ✓ No issues detected
# ==============================================================
```

## Logging

Bootstrap automatically logs to `data/logs/bootstrap.log`:

```
============================================================
Bootstrap: 2024-11-22T15:30:00.123456
Environment: development
Phase: READY
Errors: 0
Warnings: 1

Warnings:
  - No LLM API keys found. Some features will be unavailable.
============================================================
```

## Best Practices

### 1. Always Bootstrap First

```python
# ✓ GOOD
system = BootstrapSystem.auto_bootstrap()
agent = OutlineAgent(...)

# ✗ BAD
agent = OutlineAgent(...)  # What if schema missing?
```

### 2. Check Phase Before Operations

```python
if system.config.current_phase < BootPhase.READY:
    print("System not ready!")
    exit(1)

# Now safe to proceed
```

### 3. Use Environment Variables

```bash
# Don't hardcode - use environment
export SCHEMA_DIR=/custom/path
export ENVIRONMENT=production
```

### 4. Handle Bootstrap Errors

```python
try:
    system = BootstrapSystem.auto_bootstrap()
except BootstrapError as e:
    # Log, alert, fail gracefully
    logger.error(f"Bootstrap failed: {e.errors}")
    exit(1)
```

## Comparison to OS Bootstrap

| OS Concept | Book Machine Equivalent |
|------------|-------------------------|
| BIOS/UEFI | Phase 0: SEED |
| Bootloader | Phase 1: DISCOVERY |
| Kernel Init | Phase 2: VALIDATION |
| System Services | Phase 3: INIT |
| Login Ready | Phase 4: READY |
| Runlevels | BootPhase enum |
| systemd | BootstrapSystem |
| /var/log/boot.log | data/logs/bootstrap.log |

## Future Enhancements

Potential additions:
- **Phase 5: SHUTDOWN** - Graceful cleanup
- **Service dependencies** - Agent A requires Agent B
- **Hot reload** - Re-bootstrap without restart
- **Bootstrap plugins** - Custom initialization hooks
- **Health monitoring** - Continuous phase verification
- **Recovery mode** - Bootstrap to safe state on errors

## See Also

- `scripts/bootstrap.py` - Bootstrap implementation
- `ENVIRONMENT_CONFIG.md` - Environment variable guide
- `COMPLETE_ARCHITECTURE_FIX.md` - Schema system architecture
