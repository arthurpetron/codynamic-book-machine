# Codynamic Book Machine: Architecture Summary

## System Overview

The Codynamic Book Machine is a **multi-agent agentic system** that embodies the principles of Codynamic Theory through its own architecture. It transforms structured outlines into complete scholarly works through recursive refinement and distributed coordination.

## Core Philosophy: Intent-Driven Composition

The system treats document creation as an **operadic composition** where:
- **Atomic operations** (agent actions) compose into complex transformations
- **Type safety** is ensured through schema validation
- **Recursive structure** mirrors the recursive nature of the content
- **Message passing** enables decentralized coordination

## Architectural Layers

### Layer 1: Foundation (Data & Schema)
**Purpose**: Provide the semantic and structural foundation

**Components**:
- **Work Outline Schema (v2.1)**: Complete specification for written works
  - Infinite recursive hierarchy (Part → Chapter → Section → ...)
  - Dual dependency system (structural + narrative)
  - Comprehensive metadata (8 categories)
  - Intent capture at every level
  
- **Citation Database**: Web of Science-style relationship tracking
  - `cites`, `cited_by`, `related_to`, `used_in`
  - Ready for graph visualization
  
- **Agent State Storage**: Persistent task queues and execution logs

**Key Files**:
- `data/schemas/work_outline_schema_2.1.0.yaml`
- `data/book_data/*/outline/*.yaml`
- `data/agent_state/*/`

---

### Layer 2: Provider Abstraction (LLM Interface)
**Purpose**: Polymorphic access to multiple LLM backends

**Components**:
- **LLMProvider (Abstract Base)**: Unified interface for all providers
  - `Message` type for conversation structure
  - `LLMResponse` type for standardized outputs
  - Usage tracking and statistics
  
- **Concrete Providers**:
  - OpenAIProvider (GPT-4)
  - ClaudeProvider (Claude 3.x, 3.5)
  
- **ProviderFactory**: Automatic fallback chains
  - Primary → Secondary → Tertiary
  - Graceful degradation

**Key Files**:
- `scripts/api/llm_provider.py`
- `scripts/api/openai_provider.py`
- `scripts/api/claude_provider.py`
- `scripts/api/provider_factory.py`

**Type Signatures** (in operadic terms):
```
LLMProvider :: [Message] → (Config → LLMResponse)
Message :: {role: String, content: String}
LLMResponse :: {content: String, model: String, tokens: Int, ...}
```

---

### Layer 3: Agent Controller (Execution Engine)
**Purpose**: Core agent lifecycle and task execution

**Components**:
- **AgentController (Base Class)**:
  - Loads agent definitions from YAML
  - Manages task queues (persistent)
  - Executes actions via LLM calls
  - Handles message inbox
  - Logs all activities
  - Threading support
  
- **Specialized Agents** (extend AgentController):
  - SectionAgent: Writes LaTeX content
  - GardenerAgent: Validates alignment
  - OutlineAgent: Manages structure
  - HypervisorAgent: System-wide coherence
  - (5 more specialized agents)

**Key Files**:
- `scripts/agents/agent_controller.py`
- `scripts/agents/section_agent.py` (to be built)
- `scripts/agents/gardener_agent.py` (to be built)
- `scripts/agents/agent_definitions/*.yaml` (8 agents defined)

**Type Signatures**:
```
AgentController :: (AgentDef, LLMProvider) → Agent
Agent.execute_action :: (ActionId, Context) → LLMResponse
Agent.add_task :: (ActionId, Context) → TaskQueue
Agent.loop :: () → IO ()
```

---

### Layer 4: Message Router (Communication Layer)
**Purpose**: Inter-agent message passing and coordination

**Components**:
- **MessageRouter**:
  - Pub/sub pattern for agent communication
  - Validates messages against schema
  - Persistent message logging
  - Topic-based routing
  
- **Message Schema**:
  - `subject`, `from`, `to`, `reply_to`, `body`
  - Typed and validated
  
- **Agent Subscriptions**:
  - Declarative routing configuration
  - Dynamic subscription management

**Key Files**:
- `scripts/messaging/message_router.py`
- `scripts/messaging/message_schema.yaml`
- `scripts/messaging/agent_subscriptions.yaml`

**Type Signatures**:
```
MessageRouter :: () → Router
Router.subscribe :: (AgentId, Topic, Callback) → ()
Router.publish :: Message → IO Bool
Message :: {subject: String, from: AgentId, to: AgentId, body: String}
```

---

### Layer 5: Orchestration (System Coordination)
**Purpose**: Launch and coordinate all agents

**Components**:
- **AgentOrchestrator** (to be built):
  - Spawns all agents from definitions
  - Initializes message router
  - Monitors agent health
  - Graceful shutdown
  
- **Bootstrap System**:
  - Environment setup
  - Path discovery
  - Configuration loading

**Key Files**:
- `scripts/launch_agents.py` (to be built)
- `scripts/bootstrap.py`
- `scripts/utils/project_paths.py`

**Type Signatures**:
```
Orchestrator :: (Config, [AgentDef]) → Orchestrator
Orchestrator.start :: () → IO [Agent]
Orchestrator.stop :: () → IO ()
```

---

### Layer 6: Compilation Pipeline (Output Generation)
**Purpose**: Transform intermediate representations to final outputs

**Components**:
- **LaTeX Compiler**:
  - Assembles section files
  - Runs pdflatex
  - Error handling
  
- **Document Assembly**:
  - Combines front matter, main content, back matter
  - Applies styling and themes
  
- **Multi-format Export**:
  - PDF (primary)
  - HTML
  - EPUB

**Key Files**:
- `scripts/compile_latex.js`
- `scripts/agents/document_assembly_agent.py`

**Type Signatures**:
```
Compiler :: [TeXFile] → (Settings → PDF)
Assembler :: (Outline, [Section]) → TeXDocument
```

---

## Operadic Composition View

The system is designed as a **typed operad** where:

### Operations (Agents as Morphisms)
Each agent is a morphism in the operad:
```
SectionAgent :: Intent → LaTeX
GardenerAgent :: LaTeX → Validation
OutlineAgent :: Outline → [Intent]
HypervisorAgent :: [AgentState] → [Message]
```

### Composition Rules
Agents compose via message passing:
```
compose :: Agent₁ → Agent₂ → ComposedAgent
  where Agent₁.output_type = Agent₂.input_type
```

### Identity and Associativity
- **Identity**: An agent that does nothing preserves information
- **Associativity**: Order of agent composition doesn't matter (eventual consistency)

### Multi-arity Operations
Some agents take multiple inputs:
```
SectionAgent :: (Intent, Feedback, SiblingContext) → LaTeX
```

### Partial Application
Tasks in queues are partially applied operations:
```
Task = ActionId × Context  // Waiting for execution
```

---

## Data Flow Patterns

### 1. Top-Down (Outline → Content)
```
Outline
  ↓ [OutlineAgent extracts intents]
Intent₁, Intent₂, ..., Intentₙ
  ↓ [SectionAgents draft content]
LaTeX₁, LaTeX₂, ..., LaTeXₙ
  ↓ [GardenerAgent validates]
Validation Reports
  ↓ [SectionAgents revise]
Refined LaTeX
  ↓ [DocumentAssembler compiles]
Final PDF
```

### 2. Bottom-Up (Feedback → Revision)
```
Compiled PDF
  ↓ [GardenerAgent checks coherence]
Feedback Messages
  ↓ [SectionAgents receive via router]
Revision Tasks
  ↓ [SectionAgents execute]
Updated LaTeX
```

### 3. Lateral (Peer Coordination)
```
SectionAgent₁ ←→ [Messages] ←→ SectionAgent₂
     ↕                              ↕
  Sibling                       Sibling
  Context                       Context
```

### 4. Supervisory (Hypervisor → Agents)
```
HypervisorAgent
     ↓ [Monitors all agent state]
  [Detects drift or inefficiency]
     ↓
  Nudge Messages
     ↓
  Agents (receive corrections)
```

---

## State Management

### Persistent State
- **Task Queues**: `data/agent_state/{agent_id}/task_queue.yaml`
- **Action Logs**: `data/agent_state/{agent_id}/action_log.yaml`
- **Error Logs**: `data/agent_state/{agent_id}/error_log.yaml`
- **Message Logs**: `data/logs/message_logs/*.yaml`

### Transient State
- **Message Inbox**: In-memory queue per agent
- **Running Flag**: Boolean for execution loop
- **Provider Cache**: Reused LLM connections

### State Transitions
```
Agent States:
  Initialized → Running → Idle → Running → ... → Stopped

Task States:
  Queued → Executing → Completed | Failed
  
Message States:
  Published → Routed → Delivered → Processed
```

---

## Key Design Patterns

### 1. Polymorphic Provider Pattern
Multiple implementations of `LLMProvider` interface allow swapping backends without changing agent logic.

### 2. Template Method Pattern
`AgentController` defines the execution skeleton; subclasses override specific behaviors (e.g., `_handle_action_output`).

### 3. Pub/Sub Pattern
Agents don't directly call each other; they publish messages to the router, which delivers to subscribers.

### 4. Strategy Pattern
Action execution uses prompt templates as strategies, configurable per agent.

### 5. Persistent Queue Pattern
Task queues survive process restarts, enabling resilient long-running operations.

---

## System Properties

### Safety Properties (What Never Happens)
1. **No Unvalidated Messages**: All messages checked against schema
2. **No Lost Tasks**: Queues persisted to disk
3. **No Orphaned Sections**: Dependency validation in schema
4. **No Unlogged Actions**: All LLM calls recorded

### Liveness Properties (What Eventually Happens)
1. **All Tasks Execute**: If queued, will be processed (unless agent stops)
2. **All Messages Deliver**: Published messages reach subscribers
3. **Eventual Consistency**: Feedback loops converge to coherent state
4. **Graceful Degradation**: Provider failures trigger fallbacks

### Emergent Properties
1. **Self-Similar Structure**: System architecture mirrors content structure
2. **Distributed Refinement**: No central coordinator; agents negotiate
3. **Intent Preservation**: Every operation maintains alignment with goal
4. **Recursive Improvement**: Agents can introspect and improve own prompts

---

## Operational Modes

### Mode 1: Initial Draft Generation
1. User provides outline (any format)
2. Outline converter transforms to v2.1 schema
3. Outline agent extracts section intents
4. Section agents draft initial content
5. Document assembler compiles to PDF

### Mode 2: Iterative Refinement
1. Gardener agent reviews compiled PDF
2. Generates feedback messages
3. Section agents revise based on feedback
4. Recompile and validate
5. Repeat until convergence

### Mode 3: Collaborative Editing
1. User modifies outline or adds notes
2. Outline agent propagates changes
3. Affected section agents update
4. Sibling coordination maintains consistency
5. Continuous integration of changes

### Mode 4: Supervisory Intervention
1. Hypervisor monitors agent behavior
2. Detects drift from stated purpose
3. Sends corrective messages
4. Agents self-correct
5. System realigns with intent

---

## Extension Points

### Adding New Agents
1. Create YAML definition in `agent_definitions/`
2. Optionally subclass `AgentController` for specialized behavior
3. Add subscriptions in `agent_subscriptions.yaml`
4. Orchestrator automatically discovers and launches

### Adding New Providers
1. Implement `LLMProvider` interface
2. Register in `provider_factory.py`
3. Set API key in environment
4. Agents can now use new provider

### Adding New Output Formats
1. Extend `compilation` section in schema
2. Create format-specific compiler
3. Document assembler routes to appropriate compiler

### Adding New Schema Fields
1. Update `work_outline_schema_v2.yaml`
2. Increment version number
3. Provide migration script for existing outlines
4. Update validation logic

---

## Testing Strategy

### Unit Tests
- LLM Provider implementations (14 tests)
- Agent Controller lifecycle (15 tests)
- Message Router validation
- Schema validation

### Integration Tests
- End-to-end outline → PDF pipeline
- Multi-agent coordination scenarios
- Provider fallback behavior
- State persistence and recovery

### Property Tests
- Schema compliance for generated outlines
- Message format validation
- Dependency graph acyclicity
- Task queue FIFO ordering

---

## Performance Considerations

### Bottlenecks
1. **LLM API Calls**: Rate limited by provider
2. **LaTeX Compilation**: CPU-bound, can be slow
3. **File I/O**: Many small YAML reads/writes

### Optimizations
1. **Provider Caching**: Reuse HTTP connections
2. **Parallel Agents**: Run multiple section agents concurrently
3. **Incremental Compilation**: Only rebuild changed sections
4. **Lazy Loading**: Load agent state on-demand
5. **Batch Operations**: Combine multiple small LLM calls

---

## Future Enhancements

### Near-Term
1. **Message Router Implementation**: Enable inter-agent communication
2. **Specialized Agent Implementations**: Section, Gardener, Outline
3. **Launch Orchestrator**: Coordinate system startup
4. **End-to-End Testing**: Validate full pipeline

### Medium-Term
1. **Web UI**: React frontend for visual outline editing
2. **Real-Time Collaboration**: Multi-user editing
3. **Citation Management**: Automated reference checking
4. **Version Control Integration**: Git-based workflow

### Long-Term
1. **LLM-Based Reviews**: Automated pull request feedback
2. **Multi-Format Export**: HTML, EPUB, interactive web
3. **Plugin System**: User-defined agents and actions
4. **Distributed Deployment**: Cloud-native architecture

---

## Glossary

**Agent**: An autonomous unit that executes tasks via LLM calls
**Action**: A defined operation an agent can perform (e.g., draft_section)
**Task**: A queued action with context, waiting for execution
**Message**: Inter-agent communication payload
**Intent**: The goal or purpose of a section/chapter/work
**Dependency**: A relationship between sections (structural or narrative)
**Provider**: An LLM backend (OpenAI, Claude, etc.)
**Controller**: The execution engine for an agent
**Router**: Message delivery system for inter-agent communication
**Orchestrator**: System-level coordinator that launches all agents

---

*This architecture embodies the very principles it's designed to explain: recursive refinement, distributed coordination, and intent-driven evolution.*
