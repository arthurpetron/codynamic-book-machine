# Operadic Composition Diagrams

This document contains Mermaid diagrams that visualize the functional architecture of the Codynamic Book Machine. These diagrams can be rendered directly in GitHub, VS Code, or any Mermaid-compatible viewer.

## 1. System Layers (Vertical Composition)

```mermaid
flowchart TB
    subgraph Layer6["Layer 6: Compilation Pipeline"]
        Assembler[Document Assembler<br/>Outline × Sections → TeXDoc]
        Compiler[LaTeX Compiler<br/>TeXDoc → PDF]
        Exporter[Multi-Format Export<br/>PDF | HTML | EPUB]
    end
    
    subgraph Layer5["Layer 5: Orchestration"]
        Orchestrator[Agent Orchestrator<br/>Spawns & Coordinates Agents]
        Bootstrap[Bootstrap System<br/>Environment Setup]
    end
    
    subgraph Layer4["Layer 4: Message Router"]
        Router[Message Router<br/>Message → IO Bool]
        Schema[Message Schema<br/>Validation]
        Subs[Agent Subscriptions<br/>Topic-based Routing]
    end
    
    subgraph Layer3["Layer 3: Agent Controller"]
        Controller[AgentController Base<br/>ActionId × Context → Response]
        Section[SectionAgent<br/>Intent → LaTeX]
        Gardener[GardenerAgent<br/>LaTeX → Validation]
        Outline[OutlineAgent<br/>Outline → Intents]
        Hyper[HypervisorAgent<br/>AgentState → Messages]
    end
    
    subgraph Layer2["Layer 2: Provider Abstraction"]
        Provider[LLMProvider Abstract<br/>Messages → Response]
        OpenAI[OpenAIProvider<br/>GPT-4]
        Claude[ClaudeProvider<br/>Claude 3.x]
        Factory[ProviderFactory<br/>Fallback Chains]
    end
    
    subgraph Layer1["Layer 1: Foundation"]
        SchemaDB[Work Outline Schema v2.1<br/>Outline → ValidatedOutline]
        Citations[Citation Database<br/>RefId → Citation]
        State[Agent State Storage<br/>AgentId → TaskQueue × Logs]
    end
    
    Layer1 -.depends.-> Layer2
    Layer2 -.uses.-> Layer3
    Layer3 <-.messages.-> Layer4
    Layer5 -.controls.-> Layer3
    Layer5 -.controls.-> Layer4
    Layer3 ==data==> Layer6
    Layer6 ==feedback==> Layer3
    
    style Layer1 fill:#e8f4f8,stroke:#0088aa
    style Layer2 fill:#fff8e8,stroke:#cc8800
    style Layer3 fill:#f0e8f4,stroke:#8844cc
    style Layer4 fill:#e8f8e8,stroke:#44aa44
    style Layer5 fill:#ffe8e8,stroke:#cc4444
    style Layer6 fill:#f8e8ff,stroke:#aa44cc
```

## 2. Data Flow (Top-Down Creation)

```mermaid
flowchart TD
    Input[User Outline<br/>Any Format]
    Convert[Outline Converter<br/>Format → v2.1 Schema]
    Validated[Validated Outline<br/>Complete Work Definition]
    
    Extract[OutlineAgent<br/>extract_section_intents]
    Intents[Intent₁, Intent₂, ..., Intentₙ]
    
    S1[SectionAgent₁<br/>draft_initial_section]
    S2[SectionAgent₂<br/>draft_initial_section]
    Sn[SectionAgentₙ<br/>draft_initial_section]
    
    LaTeX[LaTeX₁, LaTeX₂, ..., LaTeXₙ]
    
    Validate[GardenerAgent<br/>validate & check alignment]
    Feedback[Validation Reports<br/>Semantic Feedback]
    
    Revise1[SectionAgent₁<br/>revise_from_feedback]
    Revise2[SectionAgent₂<br/>revise_from_feedback]
    Revisen[SectionAgentₙ<br/>revise_from_feedback]
    
    Refined[Refined LaTeX]
    Compile[DocumentAssembler<br/>+ LaTeX Compiler]
    Output[Final PDF]
    
    Input --> Convert
    Convert --> Validated
    Validated --> Extract
    Extract --> Intents
    
    Intents --> S1
    Intents --> S2
    Intents --> Sn
    
    S1 --> LaTeX
    S2 --> LaTeX
    Sn --> LaTeX
    
    LaTeX --> Validate
    Validate --> Feedback
    
    Feedback -.->|via Router| Revise1
    Feedback -.->|via Router| Revise2
    Feedback -.->|via Router| Revisen
    
    Revise1 --> Refined
    Revise2 --> Refined
    Revisen --> Refined
    
    Refined --> Compile
    Compile --> Output
    
    Output -.feedback loop.-> Validate
    
    style Input fill:#e8f4f8
    style Validated fill:#e8f4f8
    style Intents fill:#e8f4f8
    style LaTeX fill:#e8f4f8
    style Refined fill:#e8f4f8
    style Output fill:#e8f4f8
```

## 3. Agent Composition (Operadic View)

```mermaid
graph LR
    subgraph "Input Types"
        I1[Outline]
        I2[Intent]
        I3[LaTeX]
        I4[AgentState]
    end
    
    subgraph "Agents as Morphisms"
        A1[OutlineAgent<br/>f: Outline → Intent]
        A2[SectionAgent<br/>g: Intent → LaTeX]
        A3[GardenerAgent<br/>h: LaTeX → Validation]
        A4[HypervisorAgent<br/>k: AgentState → Message]
    end
    
    subgraph "Output Types"
        O1[Intent]
        O2[LaTeX]
        O3[Validation]
        O4[Message]
    end
    
    I1 -->|apply| A1
    A1 -->|produces| O1
    
    I2 -->|apply| A2
    A2 -->|produces| O2
    
    I3 -->|apply| A3
    A3 -->|produces| O3
    
    I4 -->|apply| A4
    A4 -->|produces| O4
    
    subgraph "Composition"
        C1[f ∘ g: Outline → LaTeX]
        C2[g ∘ h: Intent → Validation]
    end
    
    O1 -.composes.-> A2
    O2 -.composes.-> A3
    
    style I1 fill:#e8f4f8
    style I2 fill:#e8f4f8
    style I3 fill:#e8f4f8
    style I4 fill:#e8f4f8
    style O1 fill:#ffe8e8
    style O2 fill:#ffe8e8
    style O3 fill:#ffe8e8
    style O4 fill:#ffe8e8
    style A1 fill:#f0e8f4
    style A2 fill:#f0e8f4
    style A3 fill:#f0e8f4
    style A4 fill:#f0e8f4
    style C1 fill:#e8ffe8
    style C2 fill:#e8ffe8
```

## 4. Message Flow (Inter-Agent Communication)

```mermaid
sequenceDiagram
    participant Outline as OutlineAgent
    participant Router as MessageRouter
    participant Section1 as SectionAgent₁
    participant Section2 as SectionAgent₂
    participant Gardener as GardenerAgent
    participant Hyper as HypervisorAgent
    
    Note over Outline: Extracts intents
    Outline->>Router: publish({to: "section_1", body: Intent₁})
    Router->>Section1: deliver(Intent₁)
    
    Outline->>Router: publish({to: "section_2", body: Intent₂})
    Router->>Section2: deliver(Intent₂)
    
    Note over Section1,Section2: Draft LaTeX in parallel
    
    Section1->>Router: publish({to: "gardener", body: LaTeX₁})
    Section2->>Router: publish({to: "gardener", body: LaTeX₂})
    
    Router->>Gardener: deliver(LaTeX₁)
    Router->>Gardener: deliver(LaTeX₂)
    
    Note over Gardener: Validates alignment
    
    Gardener->>Router: publish({to: "section_1", body: Feedback₁})
    Gardener->>Router: publish({to: "section_2", body: Feedback₂})
    
    Router->>Section1: deliver(Feedback₁)
    Router->>Section2: deliver(Feedback₂)
    
    Note over Section1,Section2: Revise based on feedback
    
    Note over Hyper: Monitors all activity
    Hyper->>Router: publish({to: "all_agents", body: "System coherence check"})
    Router->>Section1: broadcast
    Router->>Section2: broadcast
    Router->>Gardener: broadcast
```

## 5. Type Hierarchy

```mermaid
classDiagram
    class LLMProvider {
        <<abstract>>
        +call(messages) LLMResponse
        +simple_prompt(prompt) LLMResponse
        +get_stats() Stats
    }
    
    class OpenAIProvider {
        +call(messages) LLMResponse
        +validate_model(model) bool
    }
    
    class ClaudeProvider {
        +call(messages) LLMResponse
        +validate_model(model) bool
    }
    
    class AgentController {
        +execute_action(action_id, context) LLMResponse
        +add_task(action_id, context) void
        +run_next_task() bool
        +loop() void
    }
    
    class SectionAgent {
        +draft_initial_section() LaTeX
        +revise_from_feedback() LaTeX
        +validate_section_integrity() bool
    }
    
    class GardenerAgent {
        +validate_latex_syntax() Validation
        +check_semantic_alignment() Validation
        +generate_feedback() Feedback
    }
    
    class OutlineAgent {
        +extract_section_intents() Intents
        +modify_structure() Outline
        +broadcast_intent_updates() void
    }
    
    class HypervisorAgent {
        +detect_agent_drift() DriftReport
        +generate_refocus_message() Message
        +propose_optimizations() Suggestions
    }
    
    class MessageRouter {
        +publish(message) bool
        +subscribe(agent_id, topic, callback) void
        +unsubscribe(agent_id, topic) void
    }
    
    LLMProvider <|-- OpenAIProvider
    LLMProvider <|-- ClaudeProvider
    AgentController <|-- SectionAgent
    AgentController <|-- GardenerAgent
    AgentController <|-- OutlineAgent
    AgentController <|-- HypervisorAgent
    
    AgentController --> LLMProvider : uses
    AgentController --> MessageRouter : publishes to
    MessageRouter --> AgentController : delivers to
```

## 6. State Transitions

```mermaid
stateDiagram-v2
    [*] --> Initialized
    
    state Agent {
        Initialized --> Running: start()
        Running --> Idle: no tasks
        Idle --> Running: task added
        Running --> Executing: process task
        Executing --> Running: task complete
        Executing --> Running: task failed
        Running --> Stopped: stop()
    }
    
    state Task {
        Queued --> Executing: agent picks up
        Executing --> Completed: success
        Executing --> Failed: error
    }
    
    state Message {
        Published --> Routed: router receives
        Routed --> Delivered: subscriber exists
        Delivered --> Processed: agent handles
        Routed --> Dropped: no subscriber
    }
    
    Stopped --> [*]
```

## 7. Dependency Graph (Schema)

```mermaid
graph TD
    Work[Work Root]
    Meta[Metadata<br/>8 Categories]
    Front[Front Matter]
    Structure[Structure<br/>Recursive Hierarchy]
    Citations[Citations Database]
    Diagrams[Diagrams]
    Media[Media Assets]
    Back[Back Matter]
    Compile[Compilation Config]
    
    Work --> Meta
    Work --> Front
    Work --> Structure
    Work --> Citations
    Work --> Diagrams
    Work --> Media
    Work --> Back
    Work --> Compile
    
    Structure --> Part[Part]
    Part --> Chapter[Chapter]
    Chapter --> Section[Section]
    Section --> Subsection[Subsection]
    Subsection --> Subsubsection[Subsubsection]
    Subsubsection -.infinite recursion.-> Section
    
    Chapter --> Intent[Intent<br/>goal, summary, prerequisites]
    Section --> Intent
    Subsection --> Intent
    
    Chapter --> Deps[Dependencies<br/>structural + narrative]
    Section --> Deps
    
    Chapter --> Concepts[Key Concepts<br/>term + definition]
    Section --> Concepts
    
    Chapter --> Cites[Citation References]
    Section --> Cites
    Cites -.links to.-> Citations
    
    style Work fill:#e8f4f8,stroke:#0088aa
    style Structure fill:#f0e8f4,stroke:#8844cc
    style Intent fill:#e8f8e8,stroke:#44aa44
    style Deps fill:#ffe8e8,stroke:#cc4444
    style Concepts fill:#fff8e8,stroke:#cc8800
```

## 8. Operadic Composition Laws

```mermaid
graph TD
    subgraph "Identity Law"
        A1[f: A → B]
        ID1[id: A → A]
        ID2[id: B → B]
        
        ID1 -.id ∘ f = f.-> A1
        A1 -.f ∘ id = f.-> ID2
    end
    
    subgraph "Associativity Law"
        F[f: A → B]
        G[g: B → C]
        H[h: C → D]
        
        FG[f ∘ g<br/>A → C]
        GH[g ∘ h<br/>B → D]
        FGH1["(f ∘ g) ∘ h<br/>A → D"]
        FGH2["f ∘ (g ∘ h)<br/>A → D"]
        
        F --> FG
        G --> FG
        G --> GH
        H --> GH
        
        FG --> FGH1
        H --> FGH1
        
        F --> FGH2
        GH --> FGH2
        
        FGH1 -.=.-> FGH2
    end
    
    subgraph "Multi-arity"
        I1[Intent]
        I2[Feedback]
        I3[Context]
        
        Multi[SectionAgent<br/>Intent × Feedback × Context → LaTeX]
        
        I1 --> Multi
        I2 --> Multi
        I3 --> Multi
        
        Multi --> Out[LaTeX]
    end
    
    style ID1 fill:#e8f4f8
    style ID2 fill:#e8f4f8
    style FGH1 fill:#e8ffe8
    style FGH2 fill:#e8ffe8
    style Multi fill:#f0e8f4
```

---

## How to View These Diagrams

### GitHub
These Mermaid diagrams render automatically in GitHub when viewing this markdown file.

### VS Code
Install the "Mermaid Preview" extension:
1. Open Extensions (Cmd+Shift+X)
2. Search for "Mermaid Preview"
3. Install and restart
4. Right-click this file → "Preview Mermaid"

### Standalone Viewer
Visit [mermaid.live](https://mermaid.live/) and paste the code blocks.

### Command Line
```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i MERMAID_DIAGRAMS.md -o diagrams.pdf
```

---

## Diagram Interpretations

### Layers Diagram
Shows the vertical composition of the system, with dependencies flowing upward and data flowing downward. Each layer depends on the layer below it.

### Data Flow Diagram  
Illustrates the complete pipeline from user input to final PDF, including the feedback loop where validation results trigger revisions.

### Agent Composition Diagram
Demonstrates how agents are morphisms (functions) that can compose when their types align, embodying the operadic structure.

### Message Flow Diagram
Sequence diagram showing asynchronous message passing between agents via the router, enabling decentralized coordination.

### Type Hierarchy Diagram
Class diagram showing the inheritance relationships and dependencies between core system components.

### State Transitions Diagram
State machines for agents, tasks, and messages, showing the lifecycle of each component.

### Dependency Graph Diagram
The recursive structure of the work outline schema, showing how sections can nest infinitely.

### Composition Laws Diagram
Visual proof of the mathematical properties (identity, associativity, multi-arity) that make the system a valid operad.

---

*These diagrams provide multiple perspectives on the same system, each highlighting different aspects of the functional architecture.*
