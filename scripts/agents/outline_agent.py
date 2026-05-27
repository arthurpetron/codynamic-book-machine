"""
Outline Agent - Schema-Based Validation

This agent validates and proposes improvements to book outlines.
It uses the actual Work Outline Schema v2.1 as the single source of truth.

NO HARDCODED VALIDATION RULES - the schema is the operational definition.
"""

import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from scripts.agents.runtime_agents import OutlineAgentController
from scripts.utils.schema_validator import SchemaValidator

OutlineRuntimeAgent = OutlineAgentController


class OutlineAgent:
    """
    Agent for validating and improving book outlines.
    Uses the Work Outline Schema as the authoritative definition.
    """
    
    def __init__(self, outline_path: Path, schema_dir: Path = None):
        """
        Initialize the outline agent.
        
        Args:
            outline_path: Path to the outline YAML file
            schema_dir: Optional path to schemas directory
        """
        from scripts.utils.project_paths import get_cached_project_structure
        
        self.outline_path = Path(outline_path)
        # Use book-specific directories for logs and proposals
        book_dir = self.outline_path.parent.parent  # outline -> book_data/book_name
        self.log_path = book_dir / "logs" / "outline_agent_log.txt"
        self.proposal_path = book_dir / "proposals" / "outline_proposal.yaml"
        
        # Initialize schema validator - THIS is our source of truth
        self.validator = SchemaValidator(schema_dir)
        
        # Ensure directories exist
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.proposal_path.parent.mkdir(parents=True, exist_ok=True)
    
    def load_outline(self) -> Dict[str, Any]:
        """Load the outline from file."""
        if not self.outline_path.exists():
            raise FileNotFoundError(f"Outline not found: {self.outline_path}")
        
        with open(self.outline_path, 'r') as f:
            return yaml.safe_load(f)
    
    def validate_outline(self, outline: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate outline against the schema.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        return self.validator.validate(outline)
    
    def check_completeness(self, outline: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Check for optional but recommended fields.
        
        Returns:
            Dictionary of missing recommended fields by category
        """
        return self.validator.check_completeness(outline)
    
    def generate_validation_report(self, outline: Dict[str, Any]) -> str:
        """Generate comprehensive validation report."""
        return self.validator.generate_validation_report(outline)
    
    def propose_outline_edits(self, outline: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze outline and propose improvements.
        
        This is where LLM-based analysis would happen in production.
        For now, provides structural recommendations based on completeness check.
        """
        work = outline.get('work', {})
        title = work.get('title', 'Untitled')
        
        # Check what's missing
        missing = self.check_completeness(outline)
        
        proposal = {
            'timestamp': datetime.now().isoformat(),
            'outline_title': title,
            'validation_status': {
                'strict_valid': self.validate_outline(outline)[0],
                'completeness_issues': len(missing) > 0
            },
            'recommended_additions': []
        }
        
        # Propose additions based on missing fields
        if 'metadata' in missing:
            proposal['recommended_additions'].append({
                'category': 'metadata',
                'priority': 'high',
                'rationale': 'Metadata captures the intent and context - critical for intuitionist approach',
                'missing_fields': missing['metadata']
            })
        
        if 'intent' in missing:
            proposal['recommended_additions'].append({
                'category': 'intent',
                'priority': 'high',
                'rationale': 'Intent fields define the philosophical framework and audience',
                'missing_fields': missing['intent']
            })
        
        if 'structure' in missing:
            proposal['recommended_additions'].append({
                'category': 'structure',
                'priority': 'medium',
                'rationale': 'Dependencies track how sections build on each other',
                'missing_fields': missing['structure']
            })
        
        # Example structural proposals (in production, LLM would generate these)
        structure = work.get('structure', [])
        if structure:
            existing_ids = [ch.get('id', '') for ch in structure]
            
            # Only propose if we don't already have a conclusion chapter
            has_conclusion = any('conclusion' in ch.get('title', '').lower() for ch in structure)
            
            if not has_conclusion:
                proposal['suggested_chapters'] = [
                    {
                        'type': 'chapter',
                        'id': 'ch99',
                        'title': 'Conclusion: Codynamic Futures',
                        'goal': 'Synthesize key themes and suggest next research paths',
                        'summary': 'Wraps up the ideas and proposes practical applications.',
                        'position': 'end',
                        'rationale': 'Book needs a synthesizing conclusion'
                    }
                ]
        
        return proposal
    
    def write_log(self, messages: List[str]):
        """Write validation results to log file."""
        with open(self.log_path, 'a') as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Outline Agent Run: {datetime.now().isoformat()}\n")
            f.write(f"{'=' * 60}\n")
            for msg in messages:
                f.write(f"{msg}\n")
    
    def write_proposal(self, proposal: Dict[str, Any]):
        """Write improvement proposal to file."""
        with open(self.proposal_path, 'w') as f:
            yaml.dump(proposal, f, sort_keys=False, allow_unicode=True)
        print(f"[Outline Agent] Wrote proposal to: {self.proposal_path}")
    
    def run(self, verbose: bool = True) -> bool:
        """
        Main agent execution.
        
        Args:
            verbose: Whether to print detailed output
            
        Returns:
            True if outline is valid, False otherwise
        """
        if verbose:
            print(f"[Outline Agent] Loading outline: {self.outline_path}")
        
        # Load outline
        outline = self.load_outline()
        
        # Generate validation report
        report = self.generate_validation_report(outline)
        
        if verbose:
            print("\n" + report)
        
        # Log the report
        self.write_log(report.split('\n'))
        
        # Generate and write proposal
        proposal = self.propose_outline_edits(outline)
        self.write_proposal(proposal)
        
        # Return validation status
        is_valid, _ = self.validate_outline(outline)
        return is_valid


def run_outline_agent(outline_path: str = None):
    """
    Convenience function to run the outline agent.
    
    Args:
        outline_path: Optional path to outline. If None, uses default codynamic theory outline.
    """
    if outline_path is None:
        # Default to codynamic theory outline using robust discovery
        from scripts.utils.project_paths import get_cached_project_structure
        project_structure = get_cached_project_structure()
        outline_path = (
            project_structure.book_data_dir / "codynamic_theory_book" 
            / "outline" / "codynamic_theory.yaml"
        )
    
    agent = OutlineAgent(outline_path)
    is_valid = agent.run(verbose=True)
    
    if is_valid:
        print("\n✓ Outline validation passed")
        return 0
    else:
        print("\n✗ Outline has validation issues - see proposal for recommendations")
        return 1


if __name__ == "__main__":
    """
    Run the outline agent on the codynamic theory outline.
    """
    import sys
    
    # Allow passing outline path as command-line argument
    outline_path = sys.argv[1] if len(sys.argv) > 1 else None
    
    exit_code = run_outline_agent(outline_path)
    sys.exit(exit_code)
