#!/usr/bin/env python3
"""
Main entry point for the Codynamic Book Machine.

This script demonstrates proper bootstrap usage and provides
a command-line interface to the system.
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.bootstrap import BootstrapSystem, BootstrapError, BootPhase


def cmd_bootstrap(args):
    """Bootstrap the system and show status."""
    try:
        print("Bootstrapping Codynamic Book Machine...\n")
        
        system = BootstrapSystem.auto_bootstrap(verbose=args.verbose)
        
        print()
        system.print_status()
        
        if system.config.current_phase == BootPhase.READY:
            print("✓ System is READY")
            return 0
        else:
            print("✗ System is NOT ready")
            return 1
    
    except BootstrapError as e:
        print(f"\n✗ Bootstrap failed: {e}")
        for error in e.errors:
            print(f"  - {error}")
        return 1


def cmd_status(args):
    """Show system status without full bootstrap."""
    system = BootstrapSystem()
    system.phase_0_seed()
    system.phase_1_discovery()
    
    system.print_status()
    return 0


def cmd_validate_outline(args):
    """Validate an outline file."""
    try:
        # Bootstrap first
        if not args.skip_bootstrap:
            print("Bootstrapping system...")
            system = BootstrapSystem.auto_bootstrap(verbose=False)
            print()
        
        # Now validate
        from scripts.agents.outline_agent import OutlineAgent
        
        outline_path = Path(args.outline)
        if not outline_path.exists():
            print(f"✗ Outline not found: {outline_path}")
            return 1
        
        print(f"Validating outline: {outline_path}\n")
        
        agent = OutlineAgent(outline_path)
        is_valid = agent.run(verbose=True)
        
        return 0 if is_valid else 1
    
    except Exception as e:
        print(f"✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_registry(args):
    """Show schema registry information."""
    try:
        # Minimal bootstrap
        if not args.skip_bootstrap:
            system = BootstrapSystem.bootstrap_to_phase(
                BootPhase.DISCOVERY, 
                verbose=False
            )
        
        from scripts.utils.schema_registry import get_registry
        
        registry = get_registry()
        registry.print_registry_summary()
        
        return 0
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Codynamic Book Machine - Multi-agent book authoring system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bootstrap the system
  ./main.py bootstrap
  
  # Check system status
  ./main.py status
  
  # Validate an outline
  ./main.py validate outline.yaml
  
  # Show schema registry
  ./main.py registry
        """
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Bootstrap command
    bootstrap_parser = subparsers.add_parser(
        'bootstrap',
        help='Bootstrap the system and verify it is ready'
    )
    bootstrap_parser.set_defaults(func=cmd_bootstrap)
    
    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show current system status'
    )
    status_parser.set_defaults(func=cmd_status)
    
    # Validate command
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate an outline file'
    )
    validate_parser.add_argument(
        'outline',
        help='Path to outline YAML file'
    )
    validate_parser.add_argument(
        '--skip-bootstrap',
        action='store_true',
        help='Skip bootstrap phase (faster but may fail)'
    )
    validate_parser.set_defaults(func=cmd_validate_outline)
    
    # Registry command
    registry_parser = subparsers.add_parser(
        'registry',
        help='Show schema registry information'
    )
    registry_parser.add_argument(
        '--skip-bootstrap',
        action='store_true',
        help='Skip bootstrap phase'
    )
    registry_parser.set_defaults(func=cmd_registry)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run command
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
