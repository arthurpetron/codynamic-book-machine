"""
Schema Validation Utility
Single source of truth for validating outlines against the Work Outline Schema.

Uses the Schema Registry for dynamic version discovery - NO HARDCODED VERSIONS.
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
import jsonschema
from jsonschema import Draft7Validator, ValidationError

from .schema_registry import SchemaRegistry, get_registry


class SchemaValidator:
    """
    Validates outlines against the Work Outline Schema.
    Uses SchemaRegistry for version discovery - the schema IS the operational definition.
    """
    
    def __init__(self, 
                 schema_dir: Optional[Path] = None,
                 version: Optional[str] = None,
                 use_latest: bool = True):
        """
        Initialize validator.
        
        Args:
            schema_dir: Path to schemas directory. If None, uses default.
            version: Specific schema version to use. If None, uses latest/stable.
            use_latest: If True and version is None, use latest. Otherwise use stable.
        """
        # Initialize registry - this discovers available schemas
        self.registry = get_registry(schema_dir)
        
        # Determine which version to use
        if version is None:
            if use_latest:
                self.version = self.registry.get_latest_version("work_outline")
            else:
                self.version = self.registry.get_stable_version("work_outline")
        else:
            # Validate that the requested version exists
            available = self.registry.get_versions("work_outline")
            if version not in available:
                raise ValueError(
                    f"Schema version '{version}' not found. "
                    f"Available: {', '.join(available)}"
                )
            self.version = version
        
        # Get schema info
        self.schema_info = self.registry.get_schema_info("work_outline", self.version)
        
        # Load the actual schemas
        self.json_schema = self.registry.load_schema("work_outline", self.version, "json")
        self.yaml_schema = self.registry.load_schema("work_outline", self.version, "yaml")
        
        # Create validator
        self.validator = Draft7Validator(self.json_schema)
        
        print(f"✓ Loaded Work Outline Schema v{self.version} ({self.schema_info.status})")
    
    def validate(self, outline: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate an outline against the schema.
        
        Args:
            outline: The outline dictionary to validate
            
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        try:
            # Validate against JSON Schema
            self.validator.validate(outline)
            return (True, [])
        
        except ValidationError as e:
            # Collect all validation errors
            errors = []
            for error in self.validator.iter_errors(outline):
                error_path = " -> ".join(str(p) for p in error.path) if error.path else "root"
                errors.append(f"Validation error at {error_path}: {error.message}")
            
            return (False, errors)
    
    def validate_and_report(self, outline: Dict[str, Any], 
                          verbose: bool = True) -> bool:
        """
        Validate outline and print human-readable report.
        
        Args:
            outline: The outline to validate
            verbose: Whether to print detailed error messages
            
        Returns:
            True if valid, False otherwise
        """
        is_valid, errors = self.validate(outline)
        
        if is_valid:
            if verbose:
                print(f"✓ Outline is valid according to Work Outline Schema v{self.version}")
            return True
        else:
            if verbose:
                print(f"✗ Outline validation failed with {len(errors)} error(s):")
                for error in errors:
                    print(f"  - {error}")
            return False
    
    def get_schema_version(self) -> str:
        """Get the schema version being used."""
        return self.version
    
    def check_completeness(self, outline: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Check for optional but recommended fields that are missing.
        This goes beyond strict validation to check for best practices.
        
        Returns:
            Dictionary with categories of missing recommended fields
        """
        missing = {
            'metadata': [],
            'intent': [],
            'front_matter': [],
            'back_matter': [],
            'structure': []
        }
        
        work = outline.get('work', {})
        
        # Check metadata completeness (v2.1+ comprehensive metadata)
        metadata = work.get('metadata', {})
        
        # Semantic metadata - critical for intuitionist approach
        semantic = metadata.get('semantic', {})
        if not semantic.get('thesis_statement'):
            missing['metadata'].append('metadata.semantic.thesis_statement - captures core argument')
        if not semantic.get('research_questions'):
            missing['metadata'].append('metadata.semantic.research_questions - defines inquiry')
        if not semantic.get('epistemological_stance'):
            missing['metadata'].append('metadata.semantic.epistemological_stance - e.g., intuitionism')
        
        # Administrative metadata
        admin = metadata.get('administrative', {})
        rights = admin.get('rights_and_access', {})
        if not rights.get('license'):
            missing['metadata'].append('metadata.administrative.rights_and_access.license')
        
        # Check intent completeness
        intent = work.get('intent', {})
        if not intent.get('epistemology'):
            missing['intent'].append('intent.epistemology - philosophical framework')
        
        # Check structure for dependencies
        structure = work.get('structure', [])
        for item in structure:
            if not item.get('dependencies', {}).get('structural'):
                missing['structure'].append(
                    f"{item.get('id', 'unknown')}: missing dependency information"
                )
        
        # Filter out empty categories
        return {k: v for k, v in missing.items() if v}
    
    def generate_validation_report(self, outline: Dict[str, Any]) -> str:
        """
        Generate a comprehensive validation report.
        
        Returns:
            Formatted report string
        """
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("OUTLINE VALIDATION REPORT")
        report_lines.append(f"Schema: Work Outline v{self.version}")
        report_lines.append(f"Status: {self.schema_info.status}")
        report_lines.append(f"Released: {self.schema_info.released}")
        report_lines.append("=" * 60)
        
        # Strict validation
        is_valid, errors = self.validate(outline)
        
        report_lines.append("\n1. SCHEMA VALIDATION")
        if is_valid:
            report_lines.append("   ✓ Passes strict schema validation")
        else:
            report_lines.append(f"   ✗ Failed with {len(errors)} error(s):")
            for error in errors:
                report_lines.append(f"     • {error}")
        
        # Completeness check
        missing = self.check_completeness(outline)
        
        report_lines.append("\n2. COMPLETENESS CHECK")
        if not missing:
            report_lines.append("   ✓ All recommended fields present")
        else:
            report_lines.append("   ⚠ Some recommended fields missing:")
            for category, items in missing.items():
                report_lines.append(f"\n   {category.upper()}:")
                for item in items:
                    report_lines.append(f"     • {item}")
        
        report_lines.append("\n" + "=" * 60)
        
        return "\n".join(report_lines)


def validate_outline_file(outline_path: Path, 
                         schema_dir: Optional[Path] = None,
                         version: Optional[str] = None,
                         verbose: bool = True) -> bool:
    """
    Convenience function to validate an outline file.
    
    Args:
        outline_path: Path to outline YAML file
        schema_dir: Optional path to schemas directory
        version: Optional specific schema version to use
        verbose: Whether to print detailed report
        
    Returns:
        True if valid, False otherwise
    """
    validator = SchemaValidator(schema_dir, version=version)
    
    with open(outline_path, 'r') as f:
        outline = yaml.safe_load(f)
    
    if verbose:
        print(validator.generate_validation_report(outline))
    
    is_valid, _ = validator.validate(outline)
    return is_valid


if __name__ == '__main__':
    """
    Test the validator with the codynamic theory outline.
    """
    import sys
    from scripts.utils.project_paths import get_cached_project_structure
    
    project_structure = get_cached_project_structure()
    outline_path = project_structure.book_data_dir / "codynamic_theory_book" / "outline" / "codynamic_theory.yaml"
    
    print(f"Testing schema validator on: {outline_path}\n")
    
    try:
        is_valid = validate_outline_file(outline_path, verbose=True)
        sys.exit(0 if is_valid else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
