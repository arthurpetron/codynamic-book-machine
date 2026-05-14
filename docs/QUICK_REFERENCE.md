# System Architecture Summary

## Overview

The **Codynamic Book Machine** is analyzed here from a functional programming and category theory perspective, viewing the system as a collection of **typed morphisms** (functions) that compose according to **operadic principles**.

## Key Architectural Documents

1. **ARCHITECTURE_SUMMARY.md** - Complete textual description of all 6 layers
2. **operadic_architecture.html** - Visual SVG diagram showing functional composition
3. This document - Quick reference guide

---

## The Six Layers (Bottom-Up)

### 1. Foundation (Data & Schema)
**What**: Semantic and structural data definitions
**Key Components**:
- Work Outline Schema v2.1 (recursive hierarchy)
- Citation database (relational graph)
- Agent state storage (persistent queues)

**Type**: `Outline → ValidatedOutline`

---

### 2. Provider Abstraction (LLM Interface)
**What**: Polymorphic interface to multiple LLM backends
**Key Components**:
- Abstract LLMProvider base class
- Concrete providers (OpenAI, Claude)
- Factory with fallback chains

**Type**: `[Message] → (Config → LLMResponse)`

---

### 3. Agent Controller (Execution Engine)
**What**: Core agent lifecycle and task execution
**Key Components**:
- AgentController base class
- 8 specialized agents (Section, Gardener, Outline, Hypervisor, etc.)
- Task queue management
- Message inbox handling

**Types**:
```
Agent :: (Intent → Output)
SectionAgent :: Intent → LaTeX
GardenerAgent :: LaTeX → Validation
OutlineAgent :: Outline → [Intent]
```

---

### 4. Message Router (Communication Layer)
**What**: Inter-agent message passing
**Key Components**:
- MessageRouter (pub/sub pattern)
- Message schema validation
- Topic-based routing
- Persistent logging

**Type**: `Message → IO Bool`

---

### 5. Orchestration (System Coordination)
**What**: Launch and coordinate all agents
**Key Components**:
- AgentOrchestrator (spawns agents)
- Bootstrap system (environment setup)
- Health monitoring

**Type**: `Config → [Agent] → IO ()`

---

### 6. Compilation Pipeline (Output Generation)
**What**: Transform intermediate to final outputs
**Key Components**:
- Document assembler
- LaTeX compiler
- Multi-format exporter (PDF, HTML, EPUB)

**Type**: `[LaTeX] → (Settings → PDF)`

---

## Operadic Composition Principles

### What is an Operad?
An **operad** is a mathematical structure that describes how operations compose. In this system:
- **Objects** = Data types (Outline, Intent, LaTeX, PDF, etc.)
- **Morphisms** = Agents and their actions
- **Composition** = Connecting outputs to inputs

### Key Properties

#### 1. Type Safety
```
If Agent₁ :: A → B and Agent₂ :: B → C
Then compose(Agent₁, Agent₂) :: A → C
```

#### 2. Identity
```
id :: A → A (does nothing, preserves data)
id ∘ f = f ∘ id = f
```

#### 3. Associativity
```
(f ∘ g) ∘ h = f ∘ (g ∘ h)
Order of grouping doesn't matter
```

#### 4. Multi-arity Operations
```
SectionAgent :: (Intent × Feedback × Context) → LaTeX
Takes multiple inputs, produces one output
```

### Why This Matters

1. **Predictability**: Type signatures tell you exactly what an agent does
2. **Composability**: Agents can be chained together safely
3. **Modularity**: Swap implementations without breaking system
4. **Reasoning**: Formal guarantees about behavior

---

## Data Flow Patterns

### Top-Down Flow (Creation)
```
Outline
  ↓ OutlineAgent extracts intents
[Intent₁, Intent₂, ..., Intentₙ]
  ↓ SectionAgents draft content (parallel)
[LaTeX₁, LaTeX₂, ..., LaTeXₙ]
  ↓ GardenerAgent validates
Validation Reports
  ↓ DocumentAssembler compiles
Final PDF
```

### Bottom-Up Flow (Feedback)
```
Compiled PDF
  ↓ GardenerAgent checks coherence
Feedback Messages
  ↓ MessageRouter delivers
SectionAgents receive and revise
  ↓ SectionAgents execute revisions
Updated LaTeX
```

### Lateral Flow (Peer Coordination)
```
SectionAgent₁ ←→ Messages ←→ SectionAgent₂
Siblings coordinate on style, continuity, etc.
```

### Supervisory Flow (Hypervisor)
```
HypervisorAgent monitors all agent state
  ↓ Detects drift or inefficiency
Nudge Messages
  ↓ MessageRouter delivers
Agents self-correct
```

---

## Current Status

### ✅ Complete
- Schema definition (v2.1 with 8 metadata categories)
- LLM provider abstraction (OpenAI + Claude)
- Agent controller base class
- Agent definitions (8 agents in YAML)
- Comprehensive test suite (29 tests)
- Message router implementation
- Bootstrap system

### 🔄 In Progress
- Specialized agent implementations (Section, Gardener, Outline)
- Launch orchestrator
- End-to-end testing

### 📋 Planned
- Frontend UI (React/Electron)
- Real-time collaboration
- Version control integration
- Plugin system

---

## Key Insights

### 1. Self-Similar Architecture
The system **embodies the principles it's meant to explain**:
- Recursive refinement (agents iterate on content)
- Distributed coordination (no central controller)
- Intent preservation (every operation maintains alignment)
- Structural evolution (agents can modify own prompts)

### 2. Intent-Driven Design
Every component captures **why it exists**, not just what it does:
- Sections have `goal`, `summary`, `prerequisites`
- Dependencies are both structural (machine) and narrative (human)
- Agents have explicit `role`, `tasks`, `permissions`

### 3. Dual Representation
Information exists in two forms:
- **Machine-readable**: Schema-validated, type-safe
- **Human-expressible**: Natural language descriptions
This honors your intuitionist philosophy of capturing intent.

### 4. Eventual Consistency
The system uses **asynchronous message passing** for coordination:
- No global locks or synchronization
- Agents operate independently
- Feedback loops drive convergence
- System reaches coherent state over time

---

## File Organization

```
codynamic-book-machine/
├── docs/
│   ├── ARCHITECTURE_SUMMARY.md       # This document (detailed)
│   ├── operadic_architecture.html    # Visual diagram (interactive)
│   └── QUICK_REFERENCE.md            # This summary
│
├── data/
│   ├── schemas/                      # Schema definitions
│   ├── book_data/                    # Book content and outlines
│   └── agent_state/                  # Persistent agent state
│
├── scripts/
│   ├── api/                          # LLM provider abstraction
│   ├── agents/                       # Agent implementations
│   ├── messaging/                    # Message router
│   ├── utils/                        # Utilities and helpers
│   └── outline_converter/            # Format conversion tools
│
├── tests/                            # Comprehensive test suite
└── examples/                         # Demo scripts
```

---

## Type Signature Quick Reference

```haskell
-- Foundation
Outline → ValidatedOutline
RefId → Citation
AgentId → (TaskQueue × Logs)

-- Providers
LLMProvider :: [Message] → (Config → LLMResponse)

-- Agents
SectionAgent :: Intent → LaTeX
GardenerAgent :: LaTeX → Validation
OutlineAgent :: Outline → [Intent]
HypervisorAgent :: [AgentState] → [Message]

-- Messages
Message :: {from: AgentId, to: AgentId, body: String}
Router.publish :: Message → IO Bool
Router.subscribe :: (AgentId × Topic × Callback) → ()

-- Composition
compose :: Agent₁ → Agent₂ → ComposedAgent
  where Agent₁.output_type = Agent₂.input_type

-- Compilation
Assembler :: (Outline × [Section]) → TeXDocument
Compiler :: TeXDocument → (Settings → PDF)
```

---

## Next Steps

### Immediate (This Week)
1. Implement specialized agent subclasses
2. Build launch orchestrator
3. Run first end-to-end test (Outline → PDF)

### Near-term (This Month)
1. Web UI for outline editing
2. Citation management tools
3. Dependency graph visualization
4. Performance optimization

### Long-term (This Quarter)
1. Multi-user collaboration
2. Version control integration
3. Plugin architecture
4. Cloud deployment

---

## Questions to Explore

1. **Concurrency Model**: Should agents run in threads, processes, or async?
2. **Error Recovery**: Retry strategies for failed LLM calls?
3. **Prompt Engineering**: How to balance context vs token budget?
4. **State Management**: Centralized vs distributed state?
5. **Testing Strategy**: How to test LLM-dependent behavior?

---

## Key Design Decisions

|      Decision       |           Rationale           |
|---------------------|-------------------------------|
| Multi LLM support   | Resilience via fallback       |
| YAML for config     | Human-readable, versionable   |
| Persistent queues   | Survive process restarts      |
| Pub/sub messaging   | Loose coupling between agents |
| Schema validation   | Catch errors early            |
| Recursive structure | Mirrors content hierarchy     |
| Intent capture      | Honors intuitionist philosophy|

---

## Resources

- **Main README**: `/codynamic-book-machine/README.md`
- **Progress Log**: `/codynamic-book-machine/PROGRESS.md`
- **Schema Docs**: `/data/schemas/SCHEMA_DOCUMENTATION.md`
- **Test Suite**: `/tests/`
- **Examples**: `/examples/simple_agent_demo.py`

---

*The Codynamic Book Machine: Where structure follows intent, and composition enables emergence.*
