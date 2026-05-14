"""
Book Machine Bootstrap System

Implements multi-phase initialization similar to OS boot process:
    Phase 0: Seed State - Minimal filesystem structure
    Phase 1: Discovery - Find configuration and schemas
    Phase 2: Validation - Verify everything needed exists
    Phase 3: Initialization - Load schemas, create runtime state
    Phase 4: Ready - System operational

This ensures the system bootstraps from a minimal seed state into
a fully operational runtime environment with clear error reporting
at each phase.
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from scripts.utils.project_paths import discover_project_structure


class BootPhase(IntEnum):
    """Boot phases - like OS runlevels."""
    SEED = 0      # Minimal filesystem exists
    DISCOVERY = 1  # Configuration discovered
    VALIDATION = 2 # Configuration validated
    INIT = 3       # Services initialized
    READY = 4      # Fully operational


@dataclass
class BootstrapConfig:
    """Configuration discovered during bootstrap."""
    # Paths
    project_root: Path
    schema_dir: Path
    data_dir: Path
    logs_dir: Path
    
    # Schema registry
    registry_path: Path
    registry_data: Dict[str, Any] = field(default_factory=dict)
    
    # Environment
    environment: str = "development"  # development|testing|production
    
    # LLM Configuration
    llm_providers: List[str] = field(default_factory=list)
    openai_available: bool = False
    anthropic_available: bool = False
    
    # Runtime state
    current_phase: BootPhase = BootPhase.SEED
    bootstrap_time: str = field(default_factory=lambda: datetime.now().isoformat())
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class BootstrapSystem:
    """
    Multi-phase bootstrap system for the Book Machine.
    
    Usage:
        # Option 1: Full auto-bootstrap
        system = BootstrapSystem.auto_bootstrap()
        
        # Option 2: Manual phase-by-phase
        system = BootstrapSystem()
        system.phase_0_seed()
        system.phase_1_discovery()
        system.phase_2_validation()
        system.phase_3_initialization()
        system.phase_4_ready()
        
        # Option 3: Bootstrap to specific phase
        system = BootstrapSystem.bootstrap_to_phase(BootPhase.INIT)
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        """
        Initialize bootstrap system.
        
        Args:
            project_root: Project root directory. If None, autodiscover.
        """
        self.config: Optional[BootstrapConfig] = None
        
        if project_root is None:
            # Autodiscover using robust graph-theoretic search
            project_root = discover_project_structure().root
        
        self.project_root = Path(project_root)
        self.verbose = os.getenv('BOOTSTRAP_VERBOSE', 'true').lower() == 'true'
    
    def _log(self, phase: BootPhase, message: str, level: str = "INFO"):
        """Log a bootstrap message."""
        if self.verbose:
            prefix = {
                "INFO": "✓",
                "WARN": "⚠",
                "ERROR": "✗",
                "DEBUG": "→"
            }.get(level, "·")
            
            print(f"[Phase {phase.value}] {prefix} {message}")
    
    # =========================================================================
    # PHASE 0: SEED STATE
    # =========================================================================
    
    def phase_0_seed(self) -> BootstrapConfig:
        """
        Phase 0: Verify/create minimal filesystem structure.
        
        This is the "bootloader" phase - creates the absolute minimum
        needed for the system to discover configuration.
        
        Creates:
            - data/schemas/
            - data/logs/
            - scripts/utils/
            
        Returns:
            Initial bootstrap configuration
        """
        self._log(BootPhase.SEED, "Initializing seed state...")
        
        # Create minimal configuration
        config = BootstrapConfig(
            project_root=self.project_root,
            schema_dir=self.project_root / "data" / "schemas",
            data_dir=self.project_root / "data",
            logs_dir=self.project_root / "data" / "logs",
            registry_path=self.project_root / "data" / "schemas" / "schema_registry.json",
            current_phase=BootPhase.SEED
        )
        
        # Ensure critical directories exist
        critical_dirs = [
            config.data_dir,
            config.schema_dir,
            config.logs_dir,
            self.project_root / "scripts" / "utils"
        ]
        
        for directory in critical_dirs:
            if not directory.exists():
                self._log(BootPhase.SEED, f"Creating directory: {directory}")
                directory.mkdir(parents=True, exist_ok=True)
            else:
                self._log(BootPhase.SEED, f"Directory exists: {directory}", "DEBUG")
        
        # Check if project root looks valid
        if not (self.project_root / "scripts").exists():
            config.errors.append(
                f"Project root validation failed: {self.project_root}/scripts not found"
            )
        
        self.config = config
        self._log(BootPhase.SEED, "Seed state initialized")
        
        return config
    
    # =========================================================================
    # PHASE 1: DISCOVERY
    # =========================================================================
    
    def phase_1_discovery(self) -> BootstrapConfig:
        """
        Phase 1: Discover configuration from environment and filesystem.
        
        Discovers:
            - Environment variables
            - Schema registry location
            - Available LLM providers (API keys)
            - Deployment environment (dev/test/prod)
            
        Returns:
            Configuration with discovered settings
        """
        if self.config is None:
            self.phase_0_seed()
        
        self._log(BootPhase.DISCOVERY, "Discovering configuration...")
        
        # Discover environment
        env = os.getenv('ENVIRONMENT', os.getenv('ENV', 'development'))
        self.config.environment = env
        self._log(BootPhase.DISCOVERY, f"Environment: {env}")
        
        # Discover schema directory
        env_schema_dir = os.getenv('SCHEMA_DIR')
        if env_schema_dir:
            self.config.schema_dir = Path(env_schema_dir)
            self._log(BootPhase.DISCOVERY, f"Schema dir (from env): {env_schema_dir}")
        else:
            self._log(BootPhase.DISCOVERY, f"Schema dir (default): {self.config.schema_dir}")
        
        # Discover registry path
        env_registry_path = os.getenv('SCHEMA_REGISTRY_PATH')
        env_registry_file = os.getenv('SCHEMA_REGISTRY_FILE')
        
        if env_registry_path:
            self.config.registry_path = Path(env_registry_path)
            self._log(BootPhase.DISCOVERY, f"Registry (from SCHEMA_REGISTRY_PATH): {env_registry_path}")
        elif env_registry_file:
            self.config.registry_path = self.config.schema_dir / env_registry_file
            self._log(BootPhase.DISCOVERY, f"Registry (from SCHEMA_REGISTRY_FILE): {env_registry_file}")
        else:
            # Already set to default in phase_0
            self._log(BootPhase.DISCOVERY, f"Registry (default): {self.config.registry_path}")
        
        # Discover LLM providers
        if os.getenv('OPENAI_API_KEY'):
            self.config.openai_available = True
            self.config.llm_providers.append('openai')
            self._log(BootPhase.DISCOVERY, "OpenAI API key found")
        
        if os.getenv('ANTHROPIC_API_KEY'):
            self.config.anthropic_available = True
            self.config.llm_providers.append('anthropic')
            self._log(BootPhase.DISCOVERY, "Anthropic API key found")
        
        if not self.config.llm_providers:
            self.config.warnings.append(
                "No LLM API keys found. Some features will be unavailable."
            )
        
        self.config.current_phase = BootPhase.DISCOVERY
        self._log(BootPhase.DISCOVERY, "Configuration discovered")
        
        return self.config
    
    # =========================================================================
    # PHASE 2: VALIDATION
    # =========================================================================
    
    def phase_2_validation(self) -> BootstrapConfig:
        """
        Phase 2: Validate discovered configuration.
        
        Validates:
            - Schema directory exists and is readable
            - Registry file exists and is valid JSON
            - Required schemas exist
            - File permissions are correct
            
        Returns:
            Validated configuration
        """
        if self.config is None or self.config.current_phase < BootPhase.DISCOVERY:
            self.phase_1_discovery()
        
        self._log(BootPhase.VALIDATION, "Validating configuration...")
        
        # Validate schema directory
        if not self.config.schema_dir.exists():
            self.config.errors.append(
                f"Schema directory not found: {self.config.schema_dir}"
            )
        elif not self.config.schema_dir.is_dir():
            self.config.errors.append(
                f"Schema path is not a directory: {self.config.schema_dir}"
            )
        else:
            self._log(BootPhase.VALIDATION, f"Schema directory OK: {self.config.schema_dir}")
        
        # Validate registry file
        if not self.config.registry_path.exists():
            self.config.warnings.append(
                f"Registry file not found: {self.config.registry_path}. "
                "Will attempt filesystem discovery in Phase 3."
            )
        else:
            try:
                with open(self.config.registry_path, 'r') as f:
                    self.config.registry_data = json.load(f)
                self._log(BootPhase.VALIDATION, f"Registry file OK: {self.config.registry_path}")
            except json.JSONDecodeError as e:
                self.config.errors.append(
                    f"Registry file is invalid JSON: {e}"
                )
            except Exception as e:
                self.config.errors.append(
                    f"Failed to read registry: {e}"
                )
        
        # Validate logs directory is writable
        try:
            test_file = self.config.logs_dir / ".bootstrap_test"
            test_file.write_text("test")
            test_file.unlink()
            self._log(BootPhase.VALIDATION, "Logs directory writable")
        except Exception as e:
            self.config.errors.append(
                f"Logs directory not writable: {e}"
            )
        
        self.config.current_phase = BootPhase.VALIDATION
        
        if self.config.errors:
            self._log(BootPhase.VALIDATION, f"Validation failed with {len(self.config.errors)} error(s)", "ERROR")
        else:
            self._log(BootPhase.VALIDATION, "Validation passed")
        
        return self.config
    
    # =========================================================================
    # PHASE 3: INITIALIZATION
    # =========================================================================
    
    def phase_3_initialization(self) -> BootstrapConfig:
        """
        Phase 3: Initialize services and runtime state.
        
        Initializes:
            - Schema registry (load or discover)
            - Schema validator
            - Logging system
            - Runtime directories
            
        Returns:
            Initialized configuration
        """
        if self.config is None or self.config.current_phase < BootPhase.VALIDATION:
            self.phase_2_validation()
        
        # Don't proceed if validation failed
        if self.config.errors:
            self._log(BootPhase.INIT, "Cannot initialize - validation errors exist", "ERROR")
            return self.config
        
        self._log(BootPhase.INIT, "Initializing services...")
        
        # Initialize schema registry
        try:
            from scripts.utils.schema_registry import SchemaRegistry
            
            registry = SchemaRegistry(
                schema_dir=self.config.schema_dir,
                registry_path=self.config.registry_path
            )
            
            # Verify we can load schemas
            schemas = registry.get_schema_names()
            self._log(BootPhase.INIT, f"Schema registry loaded: {len(schemas)} schema(s)")
            
            # Verify work_outline schema exists
            if "work_outline" in schemas:
                latest = registry.get_latest_version("work_outline")
                self._log(BootPhase.INIT, f"Work Outline Schema v{latest} available")
            else:
                self.config.errors.append(
                    "work_outline schema not found in registry"
                )
        
        except Exception as e:
            self.config.errors.append(
                f"Failed to initialize schema registry: {e}"
            )
        
        # Create runtime directories
        runtime_dirs = [
            self.config.data_dir / "agent_state",
            self.config.data_dir / "logs" / "message_logs",
        ]
        
        for directory in runtime_dirs:
            directory.mkdir(parents=True, exist_ok=True)
        
        self._log(BootPhase.INIT, "Runtime directories created")
        
        self.config.current_phase = BootPhase.INIT
        self._log(BootPhase.INIT, "Initialization complete")
        
        return self.config
    
    # =========================================================================
    # PHASE 4: READY
    # =========================================================================
    
    def phase_4_ready(self) -> BootstrapConfig:
        """
        Phase 4: Final health check and mark system ready.
        
        Performs:
            - Health check of all subsystems
            - Write bootstrap log
            - Mark system as operational
            
        Returns:
            Ready configuration
        """
        if self.config is None or self.config.current_phase < BootPhase.INIT:
            self.phase_3_initialization()
        
        # Don't proceed if initialization failed
        if self.config.errors:
            self._log(BootPhase.READY, "Cannot mark ready - initialization errors exist", "ERROR")
            return self.config
        
        self._log(BootPhase.READY, "Performing health check...")
        
        # Health checks
        health_ok = True
        
        # Check: Schema system
        try:
            from scripts.utils.schema_registry import get_latest_schema
            schema, version = get_latest_schema("work_outline")
            self._log(BootPhase.READY, f"✓ Schema system operational (v{version})")
        except Exception as e:
            self.config.errors.append(f"Schema system health check failed: {e}")
            health_ok = False
        
        # Check: File system
        if self.config.schema_dir.exists() and self.config.logs_dir.exists():
            self._log(BootPhase.READY, "✓ File system operational")
        else:
            self.config.errors.append("File system health check failed")
            health_ok = False
        
        # Write bootstrap log
        log_path = self.config.logs_dir / "bootstrap.log"
        try:
            with open(log_path, 'a') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Bootstrap: {self.config.bootstrap_time}\n")
                f.write(f"Environment: {self.config.environment}\n")
                f.write(f"Phase: {self.config.current_phase.name}\n")
                f.write(f"Errors: {len(self.config.errors)}\n")
                f.write(f"Warnings: {len(self.config.warnings)}\n")
                if self.config.errors:
                    f.write("\nErrors:\n")
                    for error in self.config.errors:
                        f.write(f"  - {error}\n")
                if self.config.warnings:
                    f.write("\nWarnings:\n")
                    for warning in self.config.warnings:
                        f.write(f"  - {warning}\n")
                f.write(f"{'='*60}\n")
        except Exception as e:
            self.config.warnings.append(f"Could not write bootstrap log: {e}")
        
        if health_ok:
            self.config.current_phase = BootPhase.READY
            self._log(BootPhase.READY, "✓ System ready")
        else:
            self._log(BootPhase.READY, "✗ System NOT ready - health check failed", "ERROR")
        
        return self.config
    
    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================
    
    @classmethod
    def auto_bootstrap(cls, verbose: bool = True) -> 'BootstrapSystem':
        """
        Automatically bootstrap to ready state.
        
        This is the "turn on the computer" method - runs all phases.
        
        Args:
            verbose: Whether to print bootstrap messages
            
        Returns:
            Fully bootstrapped system
            
        Raises:
            BootstrapError: If bootstrap fails
        """
        system = cls()
        system.verbose = verbose
        
        # Run all phases
        system.phase_0_seed()
        system.phase_1_discovery()
        system.phase_2_validation()
        system.phase_3_initialization()
        system.phase_4_ready()
        
        # Check for errors
        if system.config.errors:
            raise BootstrapError(
                f"Bootstrap failed with {len(system.config.errors)} error(s)",
                system.config.errors
            )
        
        return system
    
    @classmethod
    def bootstrap_to_phase(cls, phase: BootPhase, verbose: bool = True) -> 'BootstrapSystem':
        """
        Bootstrap to a specific phase.
        
        Args:
            phase: Target phase
            verbose: Whether to print bootstrap messages
            
        Returns:
            System bootstrapped to target phase
        """
        system = cls()
        system.verbose = verbose
        
        # Run phases up to target
        if phase >= BootPhase.SEED:
            system.phase_0_seed()
        if phase >= BootPhase.DISCOVERY:
            system.phase_1_discovery()
        if phase >= BootPhase.VALIDATION:
            system.phase_2_validation()
        if phase >= BootPhase.INIT:
            system.phase_3_initialization()
        if phase >= BootPhase.READY:
            system.phase_4_ready()
        
        return system
    
    def print_status(self):
        """Print current system status."""
        if self.config is None:
            print("System not bootstrapped")
            return
        
        print("\n" + "="*60)
        print("BOOK MACHINE SYSTEM STATUS")
        print("="*60)
        print(f"Phase: {self.config.current_phase.name} ({self.config.current_phase.value})")
        print(f"Environment: {self.config.environment}")
        print(f"Project Root: {self.config.project_root}")
        print(f"Schema Dir: {self.config.schema_dir}")
        print(f"Registry: {self.config.registry_path}")
        
        if self.config.llm_providers:
            print(f"LLM Providers: {', '.join(self.config.llm_providers)}")
        else:
            print("LLM Providers: None (API keys not found)")
        
        if self.config.errors:
            print(f"\nErrors ({len(self.config.errors)}):")
            for error in self.config.errors:
                print(f"  ✗ {error}")
        
        if self.config.warnings:
            print(f"\nWarnings ({len(self.config.warnings)}):")
            for warning in self.config.warnings:
                print(f"  ⚠ {warning}")
        
        if not self.config.errors and not self.config.warnings:
            print("\n✓ No issues detected")
        
        print("="*60 + "\n")


class BootstrapError(Exception):
    """Raised when bootstrap fails."""
    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    """
    Test the bootstrap system.
    """
    import sys
    
    print("Book Machine Bootstrap System\n")
    
    try:
        # Auto-bootstrap
        system = BootstrapSystem.auto_bootstrap(verbose=True)
        
        print("\n")
        system.print_status()
        
        if system.config.current_phase == BootPhase.READY:
            print("✓ System is READY")
            sys.exit(0)
        else:
            print("✗ System is NOT ready")
            sys.exit(1)
    
    except BootstrapError as e:
        print(f"\n✗ Bootstrap failed: {e}")
        for error in e.errors:
            print(f"  - {error}")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
