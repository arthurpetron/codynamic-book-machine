"""
Book Machine Concrete Bootstrap

This is the SPECIFIC bootstrap implementation for the Book Machine system,
built on top of the polymorphic bootstrap framework.

Demonstrates how to use the framework to bootstrap a real system.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List
from scripts.utils.bootstrap_framework import (
    BootPhase, PhaseResult, PhaseStatus, BootContext,
    Bootstrapper, FunctionalPhase
)
from scripts.utils.project_paths import (
    discover_project_structure, verify_project_structure
)


# =============================================================================
# BOOK MACHINE SYSTEM (what we're bootstrapping)
# =============================================================================

@dataclass
class BookMachineSystem:
    """The operational Book Machine system."""
    project_root: Path
    schema_dir: Path
    data_dir: Path
    logs_dir: Path
    registry_path: Path
    environment: str
    llm_providers: List[str]
    schema_registry: Optional[object] = None  # Will be SchemaRegistry instance
    
    def __repr__(self) -> str:
        return (
            f"BookMachineSystem("
            f"env={self.environment}, "
            f"providers={self.llm_providers})"
        )


# =============================================================================
# CONCRETE PHASES FOR BOOK MACHINE
# =============================================================================

class SeedPhase(BootPhase[BookMachineSystem]):
    """Phase 0: Create minimal filesystem structure."""
    
    def __init__(self):
        super().__init__(
            phase_id="seed",
            description="Create minimal filesystem structure",
            dependencies=[]
        )
    
    def execute(self, context: BootContext[BookMachineSystem]) -> PhaseResult:
        # Discover project structure using graph-theoretic approach
        # This finds the project root by looking for markers (.git, etc.)
        # rather than making brittle assumptions about directory depth
        project_structure = discover_project_structure()
        
        # Extract semantic paths from discovered structure
        project_root = project_structure.root
        schema_dir = project_structure.schema_dir
        data_dir = project_structure.data_dir
        logs_dir = project_structure.logs_dir
        
        # Create directories
        for directory in [data_dir, schema_dir, logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Create initial system object
        system = BookMachineSystem(
            project_root=project_root,
            schema_dir=schema_dir,
            data_dir=data_dir,
            logs_dir=logs_dir,
            registry_path=schema_dir / "schema_registry.json",
            environment="unknown",
            llm_providers=[]
        )
        
        context.entity = system
        
        return PhaseResult(
            PhaseStatus.COMPLETED,
            data={"directories_created": [str(d) for d in [data_dir, schema_dir, logs_dir]]}
        )


class DiscoveryPhase(BootPhase[BookMachineSystem]):
    """Phase 1: Discover configuration from environment."""
    
    def __init__(self):
        super().__init__(
            phase_id="discovery",
            description="Discover configuration from environment",
            dependencies=["seed"]
        )
    
    def execute(self, context: BootContext[BookMachineSystem]) -> PhaseResult:
        system = context.entity
        
        # Discover environment
        system.environment = os.getenv('ENVIRONMENT', os.getenv('ENV', 'development'))
        
        # Discover schema directory override
        env_schema_dir = os.getenv('SCHEMA_DIR')
        if env_schema_dir:
            system.schema_dir = Path(env_schema_dir)
        
        # Discover registry path
        env_registry_path = os.getenv('SCHEMA_REGISTRY_PATH')
        env_registry_file = os.getenv('SCHEMA_REGISTRY_FILE')
        
        if env_registry_path:
            system.registry_path = Path(env_registry_path)
        elif env_registry_file:
            system.registry_path = system.schema_dir / env_registry_file
        
        # Discover LLM providers
        if os.getenv('OPENAI_API_KEY'):
            system.llm_providers.append('openai')
        if os.getenv('ANTHROPIC_API_KEY'):
            system.llm_providers.append('anthropic')
        
        if not system.llm_providers:
            context.add_warning("No LLM API keys found. Some features unavailable.")
        
        return PhaseResult(
            PhaseStatus.COMPLETED,
            data={
                "environment": system.environment,
                "llm_providers": system.llm_providers
            }
        )


class ValidationPhase(BootPhase[BookMachineSystem]):
    """Phase 2: Validate discovered configuration."""
    
    def __init__(self):
        super().__init__(
            phase_id="validation",
            description="Validate discovered configuration",
            dependencies=["discovery"]
        )
    
    def execute(self, context: BootContext[BookMachineSystem]) -> PhaseResult:
        system = context.entity
        issues = []
        
        # Validate schema directory exists
        if not system.schema_dir.exists():
            issues.append(f"Schema directory not found: {system.schema_dir}")
        elif not system.schema_dir.is_dir():
            issues.append(f"Schema path is not a directory: {system.schema_dir}")
        
        # Validate registry file
        if not system.registry_path.exists():
            context.add_warning(
                f"Registry file not found: {system.registry_path}. "
                "Will attempt filesystem discovery."
            )
        
        # Validate logs directory is writable
        try:
            test_file = system.logs_dir / ".bootstrap_test"
            test_file.write_text("test")
            test_file.unlink()
        except Exception as e:
            issues.append(f"Logs directory not writable: {e}")
        
        if issues:
            return PhaseResult(
                PhaseStatus.FAILED,
                error="; ".join(issues)
            )
        
        return PhaseResult(PhaseStatus.COMPLETED)


class InitializationPhase(BootPhase[BookMachineSystem]):
    """Phase 3: Initialize services and runtime state."""
    
    def __init__(self):
        super().__init__(
            phase_id="initialization",
            description="Initialize services and runtime state",
            dependencies=["validation"]
        )
    
    def execute(self, context: BootContext[BookMachineSystem]) -> PhaseResult:
        system = context.entity
        
        try:
            # Import here to avoid circular dependencies during bootstrap
            from scripts.utils.schema_registry import SchemaRegistry
            
            # Initialize schema registry
            registry = SchemaRegistry(
                schema_dir=system.schema_dir,
                registry_path=system.registry_path
            )
            
            system.schema_registry = registry
            
            # Verify work_outline schema exists
            schemas = registry.get_schema_names()
            if "work_outline" not in schemas:
                return PhaseResult(
                    PhaseStatus.FAILED,
                    error="work_outline schema not found in registry"
                )
            
            # Create runtime directories
            runtime_dirs = [
                system.data_dir / "agent_state",
                system.data_dir / "logs" / "message_logs",
            ]
            
            for directory in runtime_dirs:
                directory.mkdir(parents=True, exist_ok=True)
            
            return PhaseResult(
                PhaseStatus.COMPLETED,
                data={"schemas_available": len(schemas)}
            )
        
        except Exception as e:
            return PhaseResult(
                PhaseStatus.FAILED,
                error=f"Failed to initialize: {e}"
            )


class ReadyPhase(BootPhase[BookMachineSystem]):
    """Phase 4: Final health check and mark ready."""
    
    def __init__(self):
        super().__init__(
            phase_id="ready",
            description="Final health check",
            dependencies=["initialization"]
        )
    
    def execute(self, context: BootContext[BookMachineSystem]) -> PhaseResult:
        system = context.entity
        
        # Health checks
        health_issues = []
        
        # Check: Schema system
        try:
            from scripts.utils.schema_registry import get_latest_schema
            schema, version = get_latest_schema("work_outline")
        except Exception as e:
            health_issues.append(f"Schema system health check failed: {e}")
        
        # Check: File system
        if not (system.schema_dir.exists() and system.logs_dir.exists()):
            health_issues.append("File system health check failed")
        
        # Write bootstrap log
        log_path = system.logs_dir / "bootstrap.log"
        try:
            with open(log_path, 'a') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Bootstrap: {context.started_at}\n")
                f.write(f"Environment: {system.environment}\n")
                f.write(f"Errors: {len(context.errors)}\n")
                f.write(f"Warnings: {len(context.warnings)}\n")
                f.write(f"{'='*60}\n")
        except Exception as e:
            context.add_warning(f"Could not write bootstrap log: {e}")
        
        if health_issues:
            return PhaseResult(
                PhaseStatus.FAILED,
                error="; ".join(health_issues)
            )
        
        return PhaseResult(PhaseStatus.COMPLETED)


# =============================================================================
# BOOK MACHINE BOOTSTRAPPER
# =============================================================================

def create_book_machine_bootstrapper() -> Bootstrapper[BookMachineSystem]:
    """
    Create the standard Book Machine bootstrapper.
    
    Returns:
        Configured bootstrapper
    """
    return Bootstrapper.from_phases(
        SeedPhase(),
        DiscoveryPhase(),
        ValidationPhase(),
        InitializationPhase(),
        ReadyPhase(),
        name="Book Machine"
    )


def bootstrap_book_machine() -> BookMachineSystem:
    """
    Convenience function to bootstrap the Book Machine.
    
    Returns:
        Operational Book Machine system
        
    Raises:
        RuntimeError: If bootstrap fails
    """
    bootstrapper = create_book_machine_bootstrapper()
    return bootstrapper.bootstrap()


# =============================================================================
# MAIN (for testing)
# =============================================================================

if __name__ == '__main__':
    """Test the Book Machine bootstrap."""
    import sys
    
    try:
        system = bootstrap_book_machine()
        
        print(f"\n✓ System ready: {system}")
        print(f"  Environment: {system.environment}")
        print(f"  LLM Providers: {', '.join(system.llm_providers) or 'None'}")
        print(f"  Registry: {system.registry_path}")
        
        sys.exit(0)
    
    except Exception as e:
        print(f"\n✗ Bootstrap failed: {e}")
        sys.exit(1)
