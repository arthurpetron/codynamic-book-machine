"""
Polymorphic Bootstrap Examples

Demonstrates how the bootstrap framework can be applied to different entities:
- Agents
- Documents
- Services
- Pipelines

Each uses the same framework but bootstraps different things.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from scripts.utils.bootstrap_framework import (
    BootPhase, PhaseResult, PhaseStatus, BootContext,
    Bootstrapper, FunctionalPhase
)


# =============================================================================
# EXAMPLE 1: Bootstrap an Agent
# =============================================================================

@dataclass
class Agent:
    """A book-writing agent."""
    agent_id: str
    role: str
    llm_provider: str
    prompt_template: str
    config: dict
    state: Optional[dict] = None
    ready: bool = False


class LoadAgentConfigPhase(BootPhase[Agent]):
    """Load agent configuration from YAML."""
    
    def __init__(self, config_path: Path):
        super().__init__("load_config", "Load agent configuration")
        self.config_path = config_path
    
    def execute(self, context: BootContext[Agent]) -> PhaseResult:
        # Would load from YAML
        agent = Agent(
            agent_id="outline_agent",
            role="Outline Generator",
            llm_provider="openai",
            prompt_template="Generate outline...",
            config={"max_tokens": 4000}
        )
        context.entity = agent
        return PhaseResult(PhaseStatus.COMPLETED)


class InitializeAgentStatePhase(BootPhase[Agent]):
    """Initialize agent's runtime state."""
    
    def __init__(self):
        super().__init__(
            "init_state",
            "Initialize agent state",
            dependencies=["load_config"]
        )
    
    def execute(self, context: BootContext[Agent]) -> PhaseResult:
        agent = context.entity
        agent.state = {
            "tasks_completed": 0,
            "messages_sent": 0,
            "last_active": None
        }
        return PhaseResult(PhaseStatus.COMPLETED)


class ConnectAgentToLLMPhase(BootPhase[Agent]):
    """Connect agent to LLM provider."""
    
    def __init__(self):
        super().__init__(
            "connect_llm",
            "Connect to LLM provider",
            dependencies=["load_config"]
        )
    
    def execute(self, context: BootContext[Agent]) -> PhaseResult:
        agent = context.entity
        # Would initialize LLM connection here
        # For now, just mark as ready
        agent.ready = True
        return PhaseResult(PhaseStatus.COMPLETED)


def bootstrap_agent(config_path: Path) -> Agent:
    """Bootstrap an agent from configuration."""
    bootstrapper = Bootstrapper.from_phases(
        LoadAgentConfigPhase(config_path),
        InitializeAgentStatePhase(),
        ConnectAgentToLLMPhase(),
        name=f"Agent"
    )
    return bootstrapper.bootstrap()


# =============================================================================
# EXAMPLE 2: Bootstrap a Document
# =============================================================================

@dataclass
class Document:
    """A document being created."""
    outline_path: Path
    output_path: Path
    outline_data: Optional[dict] = None
    latex_structure: Optional[str] = None
    compiled: bool = False


def load_outline(context: BootContext[Document]) -> PhaseResult:
    """Load and parse outline."""
    doc = context.entity
    # Would load YAML outline here
    doc.outline_data = {"title": "Example Book", "chapters": []}
    return PhaseResult(PhaseStatus.COMPLETED, data=doc.outline_data)


def generate_latex(context: BootContext[Document]) -> PhaseResult:
    """Generate LaTeX structure from outline."""
    doc = context.entity
    # Would generate LaTeX here
    doc.latex_structure = "\\documentclass{book}..."
    return PhaseResult(PhaseStatus.COMPLETED)


def compile_pdf(context: BootContext[Document]) -> PhaseResult:
    """Compile LaTeX to PDF."""
    doc = context.entity
    # Would run pdflatex here
    doc.compiled = True
    return PhaseResult(PhaseStatus.COMPLETED)


def bootstrap_document(outline_path: Path, output_path: Path) -> Document:
    """Bootstrap a document from outline to compiled PDF."""
    # Create initial document
    initial_context = BootContext[Document]()
    initial_context.entity = Document(
        outline_path=outline_path,
        output_path=output_path
    )
    
    # Use functional phases for simplicity
    bootstrapper = Bootstrapper.from_phases(
        FunctionalPhase("load_outline", load_outline, "Load outline"),
        FunctionalPhase("generate_latex", generate_latex, "Generate LaTeX", 
                       dependencies=["load_outline"]),
        FunctionalPhase("compile_pdf", compile_pdf, "Compile PDF",
                       dependencies=["generate_latex"]),
        name="Document"
    )
    
    return bootstrapper.bootstrap(initial_context)


# =============================================================================
# EXAMPLE 3: Bootstrap a Service (Message Router)
# =============================================================================

@dataclass
class MessageRouter:
    """Message routing service for inter-agent communication."""
    subscriptions: dict
    message_log: Path
    routes: dict
    started: bool = False


class LoadSubscriptionsPhase(BootPhase[MessageRouter]):
    """Load agent subscriptions."""
    
    def __init__(self, subscriptions_path: Path):
        super().__init__("load_subscriptions", "Load subscriptions")
        self.subscriptions_path = subscriptions_path
    
    def execute(self, context: BootContext[MessageRouter]) -> PhaseResult:
        # Would load from YAML
        router = MessageRouter(
            subscriptions={"agent1": ["outline.updated"], "agent2": ["section.completed"]},
            message_log=Path("data/logs/messages.log"),
            routes={}
        )
        context.entity = router
        return PhaseResult(PhaseStatus.COMPLETED)


class BuildRoutingTablePhase(BootPhase[MessageRouter]):
    """Build message routing table."""
    
    def __init__(self):
        super().__init__(
            "build_routes",
            "Build routing table",
            dependencies=["load_subscriptions"]
        )
    
    def execute(self, context: BootContext[MessageRouter]) -> PhaseResult:
        router = context.entity
        # Build inverse index: message_type -> [subscribers]
        routes = {}
        for agent, subscriptions in router.subscriptions.items():
            for msg_type in subscriptions:
                if msg_type not in routes:
                    routes[msg_type] = []
                routes[msg_type].append(agent)
        router.routes = routes
        return PhaseResult(PhaseStatus.COMPLETED)


class StartRouterServicePhase(BootPhase[MessageRouter]):
    """Start the routing service."""
    
    def __init__(self):
        super().__init__(
            "start_service",
            "Start router service",
            dependencies=["build_routes"]
        )
    
    def execute(self, context: BootContext[MessageRouter]) -> PhaseResult:
        router = context.entity
        router.started = True
        return PhaseResult(PhaseStatus.COMPLETED)


def bootstrap_message_router(subscriptions_path: Path) -> MessageRouter:
    """Bootstrap the message router service."""
    bootstrapper = Bootstrapper.from_phases(
        LoadSubscriptionsPhase(subscriptions_path),
        BuildRoutingTablePhase(),
        StartRouterServicePhase(),
        name="Message Router"
    )
    return bootstrapper.bootstrap()


# =============================================================================
# EXAMPLE 4: Nested Bootstrap (Pipeline of Bootstrappers)
# =============================================================================

@dataclass
class BookPipeline:
    """Complete book creation pipeline."""
    outline_path: Path
    output_dir: Path
    agents: List[Agent]
    document: Optional[Document] = None
    router: Optional[MessageRouter] = None


def bootstrap_pipeline(outline_path: Path, output_dir: Path) -> BookPipeline:
    """
    Bootstrap an entire book creation pipeline.
    
    Demonstrates NESTED bootstrapping - each phase bootstraps a sub-component.
    """
    
    def bootstrap_agents_phase(context: BootContext[BookPipeline]) -> PhaseResult:
        """Bootstrap all agents."""
        pipeline = context.entity
        
        # Each agent is bootstrapped independently
        agents = [
            bootstrap_agent(Path("agents/outline_agent.yaml")),
            bootstrap_agent(Path("agents/section_agent.yaml")),
            bootstrap_agent(Path("agents/gardener_agent.yaml")),
        ]
        
        pipeline.agents = agents
        return PhaseResult(PhaseStatus.COMPLETED, data={"agent_count": len(agents)})
    
    def bootstrap_router_phase(context: BootContext[BookPipeline]) -> PhaseResult:
        """Bootstrap message router."""
        pipeline = context.entity
        
        # Router is bootstrapped independently
        router = bootstrap_message_router(Path("messaging/subscriptions.yaml"))
        pipeline.router = router
        
        return PhaseResult(PhaseStatus.COMPLETED)
    
    def bootstrap_document_phase(context: BootContext[BookPipeline]) -> PhaseResult:
        """Bootstrap document creation."""
        pipeline = context.entity
        
        # Document is bootstrapped independently
        document = bootstrap_document(
            pipeline.outline_path,
            pipeline.output_dir / "output.pdf"
        )
        pipeline.document = document
        
        return PhaseResult(PhaseStatus.COMPLETED)
    
    # Create initial pipeline
    initial_context = BootContext[BookPipeline]()
    initial_context.entity = BookPipeline(
        outline_path=outline_path,
        output_dir=output_dir,
        agents=[]
    )
    
    # Bootstrap the entire pipeline
    bootstrapper = Bootstrapper.from_phases(
        FunctionalPhase("agents", bootstrap_agents_phase, "Bootstrap agents"),
        FunctionalPhase("router", bootstrap_router_phase, "Bootstrap router",
                       dependencies=["agents"]),
        FunctionalPhase("document", bootstrap_document_phase, "Bootstrap document",
                       dependencies=["agents", "router"]),
        name="Book Pipeline"
    )
    
    return bootstrapper.bootstrap(initial_context)


# =============================================================================
# MAIN (run examples)
# =============================================================================

if __name__ == '__main__':
    """Run all bootstrap examples."""
    
    print("\n" + "="*60)
    print("POLYMORPHIC BOOTSTRAP EXAMPLES")
    print("="*60 + "\n")
    
    # Example 1: Bootstrap an agent
    print("\n### Example 1: Bootstrap an Agent ###\n")
    agent = bootstrap_agent(Path("agent_config.yaml"))
    print(f"✓ Agent ready: {agent.agent_id} ({agent.role})")
    
    # Example 2: Bootstrap a document
    print("\n### Example 2: Bootstrap a Document ###\n")
    document = bootstrap_document(
        Path("outline.yaml"),
        Path("output/book.pdf")
    )
    print(f"✓ Document ready: compiled={document.compiled}")
    
    # Example 3: Bootstrap a service
    print("\n### Example 3: Bootstrap a Service ###\n")
    router = bootstrap_message_router(Path("subscriptions.yaml"))
    print(f"✓ Router ready: {len(router.routes)} routes, started={router.started}")
    
    # Example 4: Bootstrap a pipeline (nested)
    print("\n### Example 4: Bootstrap a Pipeline (Nested) ###\n")
    pipeline = bootstrap_pipeline(
        Path("outline.yaml"),
        Path("output")
    )
    print(f"✓ Pipeline ready:")
    print(f"  Agents: {len(pipeline.agents)}")
    print(f"  Router: {pipeline.router.started}")
    print(f"  Document: {pipeline.document.compiled}")
    
    print("\n" + "="*60)
    print("✓ All examples completed successfully")
    print("="*60 + "\n")
