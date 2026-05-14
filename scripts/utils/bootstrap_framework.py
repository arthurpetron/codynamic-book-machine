"""
Polymorphic Bootstrap Framework

A general-purpose multi-phase initialization system that can bootstrap
ANY entity from seed state to operational state.

Design Principles:
1. Generic over entity type T (what's being bootstrapped)
2. Phases are first-class, composable objects
3. Context carries state between phases
4. Phases can be conditional, parallelizable, and reusable
5. Clear dependency tracking between phases

This is a FRAMEWORK, not a specific implementation.
Concrete bootstrappers are created by composing phases.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, List, Optional, Dict, Any, Set, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from datetime import datetime
import asyncio


# =============================================================================
# TYPE PARAMETERS
# =============================================================================

T = TypeVar('T')  # The entity being bootstrapped
C = TypeVar('C')  # The context type


# =============================================================================
# PHASE STATUS
# =============================================================================

class PhaseStatus(IntEnum):
    """Status of a bootstrap phase."""
    PENDING = 0      # Not yet started
    RUNNING = 1      # Currently executing
    COMPLETED = 2    # Successfully completed
    SKIPPED = 3      # Skipped (optional phase not needed)
    FAILED = 4       # Failed to complete
    ROLLED_BACK = 5  # Completed but then rolled back


# =============================================================================
# BOOTSTRAP CONTEXT
# =============================================================================

@dataclass
class BootContext(Generic[T]):
    """
    Context passed between bootstrap phases.
    
    This is the "state machine" of the bootstrap process.
    Each phase can read from and write to context.
    """
    # What we're building
    entity: Optional[T] = None
    
    # Phase execution state
    phase_results: Dict[str, Any] = field(default_factory=dict)
    phase_status: Dict[str, PhaseStatus] = field(default_factory=dict)
    
    # Error tracking
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Metadata
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def set_result(self, phase_id: str, result: Any):
        """Store result from a phase."""
        self.phase_results[phase_id] = result
    
    def get_result(self, phase_id: str) -> Optional[Any]:
        """Get result from a previous phase."""
        return self.phase_results.get(phase_id)
    
    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return len(self.errors) > 0
    
    def add_error(self, error: str):
        """Add an error."""
        self.errors.append(error)
    
    def add_warning(self, warning: str):
        """Add a warning."""
        self.warnings.append(warning)


# =============================================================================
# PHASE RESULT
# =============================================================================

@dataclass
class PhaseResult:
    """Result of executing a bootstrap phase."""
    status: PhaseStatus
    data: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    
    @property
    def succeeded(self) -> bool:
        return self.status in [PhaseStatus.COMPLETED, PhaseStatus.SKIPPED]
    
    @property
    def failed(self) -> bool:
        return self.status == PhaseStatus.FAILED


# =============================================================================
# ABSTRACT PHASE
# =============================================================================

class BootPhase(ABC, Generic[T]):
    """
    Abstract base class for a bootstrap phase.
    
    A phase is a discrete step in the bootstrap process that:
    - Has a unique identifier
    - Can declare dependencies on other phases
    - Can be conditional (skipped if not needed)
    - Can be rolled back if something fails later
    - Operates on a shared context
    """
    
    def __init__(self, 
                 phase_id: str,
                 description: str = "",
                 dependencies: Optional[List[str]] = None,
                 optional: bool = False):
        """
        Initialize a bootstrap phase.
        
        Args:
            phase_id: Unique identifier for this phase
            description: Human-readable description
            dependencies: IDs of phases this depends on
            optional: Whether this phase can be skipped
        """
        self.phase_id = phase_id
        self.description = description or phase_id
        self.dependencies = dependencies or []
        self.optional = optional
    
    @abstractmethod
    def execute(self, context: BootContext[T]) -> PhaseResult:
        """
        Execute this phase.
        
        Args:
            context: Shared bootstrap context
            
        Returns:
            Result of phase execution
        """
        pass
    
    def can_skip(self, context: BootContext[T]) -> bool:
        """
        Determine if this phase can be skipped.
        
        Args:
            context: Current bootstrap context
            
        Returns:
            True if phase can be skipped
        """
        return False
    
    def rollback(self, context: BootContext[T]):
        """
        Rollback this phase if needed.
        
        Override this if your phase has side effects that need cleanup.
        
        Args:
            context: Bootstrap context
        """
        pass
    
    def __repr__(self) -> str:
        return f"BootPhase({self.phase_id})"


# =============================================================================
# FUNCTIONAL PHASE (for simple phases)
# =============================================================================

class FunctionalPhase(BootPhase[T]):
    """
    A phase defined by a simple function.
    
    Useful for quick, simple phases without creating a class.
    """
    
    def __init__(self,
                 phase_id: str,
                 func: Callable[[BootContext[T]], PhaseResult],
                 description: str = "",
                 dependencies: Optional[List[str]] = None,
                 optional: bool = False,
                 skip_func: Optional[Callable[[BootContext[T]], bool]] = None):
        """
        Create a phase from a function.
        
        Args:
            phase_id: Unique identifier
            func: Function that executes the phase
            description: Human-readable description
            dependencies: Phase dependencies
            optional: Whether phase can be skipped
            skip_func: Optional function to determine if phase should skip
        """
        super().__init__(phase_id, description, dependencies, optional)
        self.func = func
        self.skip_func = skip_func
    
    def execute(self, context: BootContext[T]) -> PhaseResult:
        return self.func(context)
    
    def can_skip(self, context: BootContext[T]) -> bool:
        if self.skip_func:
            return self.skip_func(context)
        return super().can_skip(context)


# =============================================================================
# BOOTSTRAP EXECUTOR
# =============================================================================

class BootstrapExecutor(Generic[T]):
    """
    Executes a sequence of bootstrap phases.
    
    Handles:
    - Dependency resolution
    - Phase ordering
    - Error handling
    - Rollback on failure
    - Parallel execution (where possible)
    """
    
    def __init__(self, 
                 phases: List[BootPhase[T]],
                 fail_fast: bool = True,
                 rollback_on_failure: bool = False,
                 verbose: bool = False):
        """
        Initialize bootstrap executor.
        
        Args:
            phases: List of phases to execute
            fail_fast: Stop on first error
            rollback_on_failure: Rollback completed phases on failure
            verbose: Print detailed progress
        """
        self.phases = {p.phase_id: p for p in phases}
        self.fail_fast = fail_fast
        self.rollback_on_failure = rollback_on_failure
        self.verbose = verbose
    
    def _log(self, message: str, level: str = "INFO"):
        """Log a message if verbose."""
        if self.verbose:
            prefix = {"INFO": "→", "WARN": "⚠", "ERROR": "✗", "SUCCESS": "✓"}
            print(f"{prefix.get(level, '·')} {message}")
    
    def _resolve_dependencies(self) -> List[str]:
        """
        Resolve phase dependencies and return execution order.
        
        Returns:
            List of phase IDs in execution order
            
        Raises:
            ValueError: If circular dependency detected
        """
        # Topological sort
        visited: Set[str] = set()
        visiting: Set[str] = set()
        order: List[str] = []
        
        def visit(phase_id: str):
            if phase_id in visited:
                return
            if phase_id in visiting:
                raise ValueError(f"Circular dependency detected involving {phase_id}")
            
            visiting.add(phase_id)
            
            phase = self.phases[phase_id]
            for dep_id in phase.dependencies:
                if dep_id not in self.phases:
                    raise ValueError(f"Phase {phase_id} depends on unknown phase {dep_id}")
                visit(dep_id)
            
            visiting.remove(phase_id)
            visited.add(phase_id)
            order.append(phase_id)
        
        for phase_id in self.phases:
            visit(phase_id)
        
        return order
    
    def execute(self, context: Optional[BootContext[T]] = None) -> BootContext[T]:
        """
        Execute all phases in dependency order.
        
        Args:
            context: Optional initial context. Creates new if None.
            
        Returns:
            Final context after all phases
            
        Raises:
            RuntimeError: If bootstrap fails and fail_fast is True
        """
        if context is None:
            context = BootContext[T]()
        
        # Resolve execution order
        try:
            execution_order = self._resolve_dependencies()
            self._log(f"Phase execution order: {' → '.join(execution_order)}")
        except ValueError as e:
            context.add_error(str(e))
            raise RuntimeError(f"Cannot execute bootstrap: {e}")
        
        # Execute phases
        completed_phases: List[str] = []
        
        for phase_id in execution_order:
            phase = self.phases[phase_id]
            
            self._log(f"Phase: {phase.description} ({phase_id})")
            
            # Check if can skip
            if phase.can_skip(context):
                self._log(f"Skipping {phase_id} (not needed)", "INFO")
                context.phase_status[phase_id] = PhaseStatus.SKIPPED
                continue
            
            # Execute phase
            context.phase_status[phase_id] = PhaseStatus.RUNNING
            
            try:
                start_time = datetime.now()
                result = phase.execute(context)
                duration = (datetime.now() - start_time).total_seconds() * 1000
                result.duration_ms = duration
                
                # Store result
                context.set_result(phase_id, result.data)
                context.phase_status[phase_id] = result.status
                
                if result.succeeded:
                    self._log(f"✓ {phase_id} completed ({duration:.1f}ms)", "SUCCESS")
                    completed_phases.append(phase_id)
                else:
                    self._log(f"✗ {phase_id} failed: {result.error}", "ERROR")
                    context.add_error(f"{phase_id}: {result.error}")
                    
                    if self.fail_fast:
                        # Rollback if configured
                        if self.rollback_on_failure:
                            self._rollback_phases(completed_phases, context)
                        raise RuntimeError(f"Bootstrap failed at phase {phase_id}: {result.error}")
            
            except Exception as e:
                self._log(f"✗ Exception in {phase_id}: {e}", "ERROR")
                context.add_error(f"{phase_id}: {str(e)}")
                context.phase_status[phase_id] = PhaseStatus.FAILED
                
                if self.fail_fast:
                    if self.rollback_on_failure:
                        self._rollback_phases(completed_phases, context)
                    raise RuntimeError(f"Bootstrap exception at phase {phase_id}: {e}")
        
        # Check final state
        if context.has_errors() and self.fail_fast:
            raise RuntimeError(f"Bootstrap completed with errors: {context.errors}")
        
        return context
    
    def _rollback_phases(self, phase_ids: List[str], context: BootContext[T]):
        """Rollback completed phases in reverse order."""
        self._log("Rolling back completed phases...", "WARN")
        
        for phase_id in reversed(phase_ids):
            phase = self.phases[phase_id]
            try:
                phase.rollback(context)
                context.phase_status[phase_id] = PhaseStatus.ROLLED_BACK
                self._log(f"Rolled back {phase_id}")
            except Exception as e:
                self._log(f"Failed to rollback {phase_id}: {e}", "ERROR")


# =============================================================================
# BOOTSTRAPPER (High-level API)
# =============================================================================

class Bootstrapper(Generic[T]):
    """
    High-level bootstrapper that composes phases to create an entity T.
    
    This is the main API users interact with.
    """
    
    def __init__(self, 
                 phases: List[BootPhase[T]],
                 name: str = "Bootstrapper"):
        """
        Create a bootstrapper.
        
        Args:
            phases: Phases to execute
            name: Name of this bootstrapper
        """
        self.phases = phases
        self.name = name
        self.executor = BootstrapExecutor(phases, verbose=True)
    
    def bootstrap(self, 
                  initial_context: Optional[BootContext[T]] = None,
                  **config) -> T:
        """
        Execute bootstrap and return the entity.
        
        Args:
            initial_context: Optional starting context
            **config: Configuration passed to context.metadata
            
        Returns:
            The bootstrapped entity
            
        Raises:
            RuntimeError: If bootstrap fails
        """
        context = initial_context or BootContext[T]()
        context.metadata.update(config)
        
        print(f"\n{'='*60}")
        print(f"Bootstrapping: {self.name}")
        print(f"{'='*60}\n")
        
        final_context = self.executor.execute(context)
        
        if final_context.entity is None:
            raise RuntimeError(
                f"{self.name} bootstrap did not produce an entity. "
                "Make sure one of your phases sets context.entity"
            )
        
        print(f"\n{'='*60}")
        print(f"✓ {self.name} Ready")
        print(f"{'='*60}\n")
        
        return final_context.entity
    
    @classmethod
    def from_phases(cls, *phases: BootPhase[T], name: str = "Bootstrapper") -> 'Bootstrapper[T]':
        """
        Create bootstrapper from individual phases.
        
        Args:
            *phases: Variable number of phases
            name: Bootstrapper name
            
        Returns:
            New bootstrapper
        """
        return cls(list(phases), name=name)


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == '__main__':
    """
    Example: Bootstrap a simple configuration object.
    """
    
    @dataclass
    class AppConfig:
        name: str
        version: str
        debug: bool = False
        database_url: Optional[str] = None
    
    # Define phases
    class LoadConfigPhase(BootPhase[AppConfig]):
        def execute(self, context: BootContext[AppConfig]) -> PhaseResult:
            # Simulate loading config
            config = AppConfig(
                name="Example App",
                version="1.0.0",
                debug=True
            )
            context.entity = config
            return PhaseResult(PhaseStatus.COMPLETED, data=config)
    
    class ValidateConfigPhase(BootPhase[AppConfig]):
        def execute(self, context: BootContext[AppConfig]) -> PhaseResult:
            config = context.entity
            if not config.name:
                return PhaseResult(
                    PhaseStatus.FAILED,
                    error="Config name is required"
                )
            return PhaseResult(PhaseStatus.COMPLETED)
    
    class InitDatabasePhase(BootPhase[AppConfig]):
        def can_skip(self, context: BootContext[AppConfig]) -> bool:
            # Skip if no database URL configured
            return context.entity.database_url is None
        
        def execute(self, context: BootContext[AppConfig]) -> PhaseResult:
            # Would initialize database here
            return PhaseResult(PhaseStatus.COMPLETED, data="db_connection")
    
    # Create bootstrapper
    bootstrapper = Bootstrapper.from_phases(
        LoadConfigPhase("load", "Load configuration", dependencies=[]),
        ValidateConfigPhase("validate", "Validate configuration", dependencies=["load"]),
        InitDatabasePhase("database", "Initialize database", dependencies=["validate"], optional=True),
        name="Application"
    )
    
    # Bootstrap!
    app_config = bootstrapper.bootstrap()
    
    print(f"Bootstrapped: {app_config.name} v{app_config.version}")
