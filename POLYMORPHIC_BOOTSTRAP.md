# Polymorphic Bootstrap Architecture

## Overview

The Book Machine now has a **polymorphic bootstrap framework** that can bootstrap ANY entity from seed state to operational state. This is not hardcoded to "bootstrap the system" - it's a general pattern that can be reused for agents, documents, services, pipelines, and more.

## The Key Insight

**Bootstrap is a PATTERN, not a specific implementation.**

### Before (Concrete)
```python
# Can only bootstrap one thing
BootstrapSystem.auto_bootstrap()  # Hardcoded to "the system"
```

### After (Polymorphic)
```python
# Can bootstrap ANYTHING
Bootstrapper[SchemaSystem].bootstrap()      # Bootstrap schema system
Bootstrapper[Agent].bootstrap()             # Bootstrap an agent
Bootstrapper[Document].bootstrap()          # Bootstrap a document
Bootstrapper[MessageRouter].bootstrap()     # Bootstrap a service
Bootstrapper[Pipeline].bootstrap()          # Bootstrap a pipeline
```

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────┐
│           Polymorphic Bootstrap Framework           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  BootPhase[T]         - Abstract phase interface   │
│  BootContext[T]       - State passed between phases│
│  BootstrapExecutor[T] - Executes phase sequence    │
│  Bootstrapper[T]      - High-level API             │
│                                                     │
└─────────────────────────────────────────────────────┘
                         ▲
                         │
                         │ Uses
                         │
         ┌───────────────┴───────────────┐
         │                               │
    ┌────▼─────┐                  ┌─────▼────┐
    │ Concrete │                  │ Concrete │
    │  Book    │                  │  Agent   │
    │ Machine  │                  │ Bootstrap│
    │Bootstrap │                  └──────────┘
    └──────────┘
```

### Type Parameter T

The framework is **generic over T**, where T is the entity being bootstrapped:

- `T = BookMachineSystem` → Bootstrap the whole system
- `T = Agent` → Bootstrap an agent
- `T = Document` → Bootstrap a document  
- `T = MessageRouter` → Bootstrap a service
- `T = Pipeline` → Bootstrap a pipeline

## Key Features

### 1. Generic Over Entity Type

```python
from typing import Generic, TypeVar

T = TypeVar('T')  # What we're bootstrapping

class BootPhase(Generic[T]):
    def execute(self, context: BootContext[T]) -> PhaseResult:
        pass
```

### 2. Composable Phases

Phases are first-class objects that can be composed:

```python
# Build bootstrapper from phases
bootstrapper = Bootstrapper.from_phases(
    LoadConfigPhase(),
    ValidateConfigPhase(),
    InitializeServicePhase(),
    name="My Service"
)
```

### 3. Dependency Resolution

Phases declare dependencies; executor automatically orders them:

```python
class ValidatePhase(BootPhase[T]):
    def __init__(self):
        super().__init__(
            "validate",
            dependencies=["load_config"]  # Runs after load_config
        )
```

### 4. Shared Context

Context flows between phases carrying state:

```python
class Phase1(BootPhase[Agent]):
    def execute(self, context: BootContext[Agent]) -> PhaseResult:
        # Create entity
        context.entity = Agent(...)
        # Store data for next phase
        context.set_result("phase1", {"config": {...}})
        return PhaseResult(PhaseStatus.COMPLETED)

class Phase2(BootPhase[Agent]):
    def execute(self, context: BootContext[Agent]) -> PhaseResult:
        # Access entity
        agent = context.entity
        # Access previous phase data
        config = context.get_result("phase1")
        return PhaseResult(PhaseStatus.COMPLETED)
```

### 5. Conditional Phases

Phases can be skipped if not needed:

```python
class OptionalDatabasePhase(BootPhase[App]):
    def can_skip(self, context: BootContext[App]) -> bool:
        # Skip if no database URL configured
        return context.entity.database_url is None
```

### 6. Functional Phases

Quick phases without creating classes:

```python
def load_config(context: BootContext[T]) -> PhaseResult:
    # Simple function
    context.entity = MyEntity(...)
    return PhaseResult(PhaseStatus.COMPLETED)

# Use it
phase = FunctionalPhase("load", load_config, "Load configuration")
```

### 7. Nested Bootstrapping

Bootstrappers can call other bootstrappers:

```python
def bootstrap_pipeline(context: BootContext[Pipeline]) -> PhaseResult:
    pipeline = context.entity
    
    # Bootstrap sub-components
    pipeline.agent1 = bootstrap_agent(config1)  # Nested!
    pipeline.agent2 = bootstrap_agent(config2)  # Nested!
    pipeline.router = bootstrap_router()        # Nested!
    
    return PhaseResult(PhaseStatus.COMPLETED)
```

## Usage Patterns

### Pattern 1: Simple Entity Bootstrap

```python
from scripts.utils.bootstrap_framework import Bootstrapper, BootPhase

# Define what you're bootstrapping
@dataclass
class MyService:
    name: str
    config: dict
    running: bool = False

# Define phases
class LoadConfigPhase(BootPhase[MyService]):
    def execute(self, context):
        service = MyService(name="Example", config={})
        context.entity = service
        return PhaseResult(PhaseStatus.COMPLETED)

class StartServicePhase(BootPhase[MyService]):
    def execute(self, context):
        context.entity.running = True
        return PhaseResult(PhaseStatus.COMPLETED)

# Bootstrap it
bootstrapper = Bootstrapper.from_phases(
    LoadConfigPhase(),
    StartServicePhase(),
    name="My Service"
)

service = bootstrapper.bootstrap()
```

### Pattern 2: Functional Phases (Quick & Simple)

```python
def load(context: BootContext[MyService]) -> PhaseResult:
    context.entity = MyService(...)
    return PhaseResult(PhaseStatus.COMPLETED)

def start(context: BootContext[MyService]) -> PhaseResult:
    context.entity.running = True
    return PhaseResult(PhaseStatus.COMPLETED)

bootstrapper = Bootstrapper.from_phases(
    FunctionalPhase("load", load, "Load service"),
    FunctionalPhase("start", start, "Start service", dependencies=["load"]),
    name="My Service"
)
```

### Pattern 3: With Dependencies

```python
bootstrapper = Bootstrapper.from_phases(
    LoadPhase(),                    # No dependencies
    ValidatePhase(),                # Depends on Load
    InitDatabasePhase(),            # Depends on Validate
    StartServicePhase(),            # Depends on InitDatabase
    HealthCheckPhase(),             # Depends on StartService
    name="Complex Service"
)

# Executor automatically orders phases:
# Load → Validate → InitDatabase → StartService → HealthCheck
```

### Pattern 4: Conditional/Optional Phases

```python
class DatabasePhase(BootPhase[App]):
    def __init__(self):
        super().__init__("database", optional=True)
    
    def can_skip(self, context):
        # Skip if no database configured
        return not context.entity.has_database

# Phase is automatically skipped when not needed
```

### Pattern 5: Nested Bootstrapping

```python
def bootstrap_agents_phase(context: BootContext[System]) -> PhaseResult:
    system = context.entity
    
    # Each agent bootstrapped independently
    system.agent1 = bootstrap_agent("agent1.yaml")
    system.agent2 = bootstrap_agent("agent2.yaml")
    system.agent3 = bootstrap_agent("agent3.yaml")
    
    return PhaseResult(PhaseStatus.COMPLETED)

# Top-level bootstrap delegates to sub-bootstraps
bootstrapper = Bootstrapper.from_phases(
    FunctionalPhase("agents", bootstrap_agents_phase),
    FunctionalPhase("router", bootstrap_router_phase),
    name="Complete System"
)
```

## Real Examples

### Example 1: Bootstrap an Agent

```python
agent = bootstrap_agent(Path("outline_agent.yaml"))
# Returns: Agent(agent_id="outline_agent", role="Outline Generator", ready=True)
```

**Phases**:
1. Load agent config from YAML
2. Initialize agent state
3. Connect to LLM provider

### Example 2: Bootstrap a Document

```python
document = bootstrap_document(
    Path("outline.yaml"),
    Path("output/book.pdf")
)
# Returns: Document(compiled=True, latex_structure="...", ...)
```

**Phases**:
1. Load outline
2. Generate LaTeX structure
3. Compile PDF

### Example 3: Bootstrap a Service

```python
router = bootstrap_message_router(Path("subscriptions.yaml"))
# Returns: MessageRouter(routes={...}, started=True)
```

**Phases**:
1. Load subscriptions
2. Build routing table
3. Start service

### Example 4: Bootstrap a Pipeline (Nested)

```python
pipeline = bootstrap_pipeline(
    Path("outline.yaml"),
    Path("output")
)
# Returns: BookPipeline(agents=[...], router=..., document=...)
```

**Phases**:
1. Bootstrap all agents (nested)
2. Bootstrap message router (nested)
3. Bootstrap document (nested)

## Benefits

### 1. Reusability

The same framework works for ANY entity:
- System bootstrap
- Agent bootstrap
- Document bootstrap
- Service bootstrap
- Pipeline bootstrap

### 2. Composability

Small bootstrappers compose into larger ones:
```python
System Bootstrap
  ├─> Agent Bootstrap
  ├─> Router Bootstrap  
  └─> Document Bootstrap
      ├─> Outline Bootstrap
      └─> LaTeX Bootstrap
```

### 3. Testability

Each phase can be tested independently:
```python
def test_load_config_phase():
    phase = LoadConfigPhase()
    context = BootContext[MyService]()
    result = phase.execute(context)
    assert result.succeeded
    assert context.entity is not None
```

### 4. Explicit Dependencies

Dependency graph is explicit and machine-readable:
```python
# Executor resolves this automatically
load -> validate -> init_db -> start_service -> health_check
```

### 5. Clear State Transitions

Each phase has clear pre/postconditions:
```python
Phase: LoadConfig
  Pre:  context.entity is None
  Post: context.entity is MyService(...)

Phase: ValidateConfig  
  Pre:  context.entity.config is not None
  Post: context.entity.validated = True
```

## Comparison to OS Bootstrap

| OS Concept | Bootstrap Framework | Book Machine Example |
|------------|-------------------|---------------------|
| BIOS/UEFI | Abstract BootPhase | SeedPhase |
| Bootloader | BootstrapExecutor | Phase ordering |
| Kernel | Concrete phases | DiscoveryPhase, ValidationPhase |
| Init system | Bootstrapper | create_book_machine_bootstrapper() |
| Services | Nested bootstraps | bootstrap_agent(), bootstrap_router() |
| Runlevels | PhaseStatus | PENDING, RUNNING, COMPLETED |

## Files

### Framework (Polymorphic)
- `scripts/utils/bootstrap_framework.py` - Core framework (generic over T)

### Concrete Implementations
- `scripts/bootstrap_concrete.py` - Book Machine system bootstrap
- `examples/bootstrap_examples.py` - Agent, Document, Service, Pipeline examples

### Legacy (for migration)
- `scripts/bootstrap.py` - Original concrete implementation (will be deprecated)

## Migration Path

### Old Code (Concrete)
```python
from scripts.bootstrap import BootstrapSystem
system = BootstrapSystem.auto_bootstrap()
```

### New Code (Polymorphic)
```python
from scripts.bootstrap_concrete import bootstrap_book_machine
system = bootstrap_book_machine()
```

## Future Possibilities

With polymorphic bootstrap, you can now:

1. **Bootstrap individual agents** when they start
2. **Bootstrap documents** as they're created
3. **Bootstrap the message router** independently
4. **Bootstrap sub-systems** in parallel
5. **Compose bootstrappers** hierarchically
6. **Test phases** in isolation
7. **Visualize dependency graphs**
8. **Hot-reload** by re-bootstrapping
9. **Graceful shutdown** with rollback
10. **Custom bootstrap** for user extensions

## The Intuitionist Principle

This polymorphic design embodies your philosophy:

> **Structures should be constructively defined based on what we can actually compute.**

The bootstrap process is now:
- **Generic** - Works for any entity T
- **Composable** - Small pieces combine
- **Explicit** - Dependencies are declared
- **Verifiable** - Each phase has clear contracts
- **Constructive** - Builds entities step-by-step

Instead of hardcoding "how to bootstrap the system", we've defined the **abstract process of bootstrapping** that can be applied to any entity. The framework is the **constructive definition** of multi-phase initialization.

This is exactly what you needed: **polymorphic infrastructure** ready to be employed wherever you need bootstrapping.
