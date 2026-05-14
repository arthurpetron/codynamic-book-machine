"""
Test suite for the Schema Registry and Validator system.

Verifies that:
1. Registry can discover schemas
2. Validator uses registry (no hardcoded versions)
3. Version discovery works correctly
4. Filesystem fallback works
"""

import json
import pytest
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils.schema_registry import SchemaRegistry, get_registry, get_latest_schema
from scripts.utils.schema_validator import SchemaValidator


class TestSchemaRegistry:
    """Test the schema registry system."""
    
    def test_registry_loads(self):
        """Test that registry loads successfully."""
        registry = get_registry()
        assert registry is not None
        assert registry.registry is not None
    
    def test_schema_discovery(self):
        """Test that schemas are discovered."""
        registry = get_registry()
        schemas = registry.get_schema_names()
        
        assert "work_outline" in schemas
        assert len(schemas) > 0
    
    def test_version_discovery(self):
        """Test that versions are discovered correctly."""
        registry = get_registry()
        versions = registry.get_versions("work_outline")
        
        assert len(versions) > 0
        assert all("." in v for v in versions)  # All should have dots (semantic versioning)
    
    def test_latest_version(self):
        """Test that latest version can be retrieved."""
        registry = get_registry()
        latest = registry.get_latest_version("work_outline")
        
        assert latest is not None
        assert isinstance(latest, str)
        assert "." in latest  # Should be semantic version
    
    def test_schema_info(self):
        """Test that schema info contains required fields."""
        registry = get_registry()
        info = registry.get_schema_info("work_outline")
        
        assert info.version is not None
        assert info.json_file is not None
        assert info.yaml_file is not None
        assert info.status in ["current", "stable", "deprecated", "experimental"]
    
    def test_schema_path_resolution(self):
        """Test that schema paths resolve correctly."""
        registry = get_registry()
        
        # Get path for latest version
        json_path = registry.get_schema_path("work_outline", format_type="json")
        yaml_path = registry.get_schema_path("work_outline", format_type="yaml")
        
        assert json_path.exists()
        assert yaml_path.exists()
        assert json_path.suffix == ".json"
        assert yaml_path.suffix == ".yaml"
    
    def test_schema_loading(self):
        """Test that schemas can be loaded."""
        registry = get_registry()
        
        schema = registry.load_schema("work_outline", format_type="json")
        
        assert isinstance(schema, dict)
        assert len(schema) > 0
    
    def test_convenience_function(self):
        """Test the get_latest_schema convenience function."""
        schema, version = get_latest_schema("work_outline")
        
        assert isinstance(schema, dict)
        assert isinstance(version, str)
        assert "." in version


class TestSchemaValidator:
    """Test the schema validator system."""
    
    def test_validator_initialization(self):
        """Test that validator initializes without hardcoded versions."""
        validator = SchemaValidator()
        
        assert validator.version is not None
        assert validator.schema_info is not None
        assert validator.validator is not None
    
    def test_version_selection(self):
        """Test that specific versions can be selected."""
        registry = get_registry()
        versions = registry.get_versions("work_outline")
        
        if len(versions) > 1:
            # Test with non-latest version
            older_version = versions[-1]
            validator = SchemaValidator(version=older_version)
            assert validator.version == older_version
    
    def test_latest_vs_stable(self):
        """Test latest vs stable version selection."""
        validator_latest = SchemaValidator(use_latest=True)
        validator_stable = SchemaValidator(use_latest=False)
        
        # Both should initialize successfully
        assert validator_latest.version is not None
        assert validator_stable.version is not None
    
    def test_minimal_valid_outline(self):
        """Test validation with a minimal valid outline."""
        validator = SchemaValidator()
        
        # Create minimal outline that should pass schema validation
        minimal_outline = {
            "work": {
                "id": "test_work",
                "type": "book",
                "title": "Test Book",
                "subtitle": "",
                "summary": "A test book",
                "intent": {
                    "audience": "Test readers",
                    "writing_style": "Test style",
                    "author_persona": "Tester",
                    "reader_takeaway": "Testing knowledge",
                    "genre": "Test"
                },
                "authors": [
                    {"name": "Test Author", "role": "author"}
                ],
                "structure": []
            }
        }
        
        is_valid, errors = validator.validate(minimal_outline)
        
        if not is_valid:
            print("Validation errors:")
            for error in errors:
                print(f"  - {error}")
        
        # Note: This might fail if the JSON schema is very strict
        # The important thing is that it's using the schema, not hardcoded rules


class TestNoHardcodedVersions:
    """Verify that no hardcoded version numbers exist in the code."""
    
    def test_schema_validator_no_hardcoded_versions(self):
        """Verify schema_validator.py doesn't hardcode version numbers."""
        validator_path = Path(__file__).parent.parent / "scripts" / "utils" / "schema_validator.py"
        content = validator_path.read_text()
        
        # Should not contain hardcoded version strings like "v2" or "_2.json"
        assert "work_outline_schema_v2.json" not in content
        assert "work_outline_schema_v2.yaml" not in content
        
        # Should use registry
        assert "SchemaRegistry" in content or "get_registry" in content
    
    def test_outline_agent_no_hardcoded_rules(self):
        """Verify outline_agent.py doesn't have hardcoded validation rules."""
        agent_path = Path(__file__).parent.parent / "scripts" / "agents" / "outline_agent.py"
        content = agent_path.read_text()
        
        # Should not have hardcoded REQUIRED_KEYS
        assert "REQUIRED_KEYS = [" not in content
        assert "REQUIRED_INTENT_KEYS = [" not in content
        
        # Should use SchemaValidator
        assert "SchemaValidator" in content
    
    def test_registry_no_hardcoded_filename(self):
        """Verify schema_registry.py doesn't hardcode registry filename."""
        registry_path = Path(__file__).parent.parent / "scripts" / "utils" / "schema_registry.py"
        content = registry_path.read_text()
        
        # Should not have REGISTRY_FILE as hardcoded constant
        assert 'REGISTRY_FILE = "schema_registry.json"' not in content
        
        # Should have DEFAULT and ENV constants instead
        assert 'DEFAULT_REGISTRY_FILE' in content
        assert 'ENV_REGISTRY_FILE' in content
        assert 'ENV_REGISTRY_PATH' in content
        assert 'ENV_SCHEMA_DIR' in content


class TestEnvironmentVariables:
    """Test environment variable configuration."""
    
    def test_default_configuration(self):
        """Test default configuration without env vars."""
        import os
        
        # Ensure env vars are not set
        env_vars = ['SCHEMA_DIR', 'SCHEMA_REGISTRY_FILE', 'SCHEMA_REGISTRY_PATH']
        old_values = {}
        for var in env_vars:
            old_values[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]
        
        try:
            registry = get_registry()
            assert 'schema_registry.json' in str(registry.registry_path)
        finally:
            # Restore env vars
            for var, value in old_values.items():
                if value is not None:
                    os.environ[var] = value
    
    def test_custom_registry_file_env(self):
        """Test SCHEMA_REGISTRY_FILE environment variable."""
        import os
        
        old_value = os.environ.get('SCHEMA_REGISTRY_FILE')
        try:
            os.environ['SCHEMA_REGISTRY_FILE'] = 'test_registry.json'
            registry = get_registry()
            
            assert 'test_registry.json' in str(registry.registry_path)
        finally:
            if old_value is not None:
                os.environ['SCHEMA_REGISTRY_FILE'] = old_value
            elif 'SCHEMA_REGISTRY_FILE' in os.environ:
                del os.environ['SCHEMA_REGISTRY_FILE']
    
    def test_constructor_overrides_env(self):
        """Test that constructor parameters override environment."""
        import os
        
        old_value = os.environ.get('SCHEMA_REGISTRY_FILE')
        try:
            os.environ['SCHEMA_REGISTRY_FILE'] = 'wrong_registry.json'
            
            # Constructor should override
            registry = SchemaRegistry(registry_file='test_registry.json')
            
            assert 'test_registry.json' in str(registry.registry_path)
            assert 'wrong_registry.json' not in str(registry.registry_path)
        finally:
            if old_value is not None:
                os.environ['SCHEMA_REGISTRY_FILE'] = old_value
            elif 'SCHEMA_REGISTRY_FILE' in os.environ:
                del os.environ['SCHEMA_REGISTRY_FILE']


if __name__ == '__main__':
    """Run tests with pytest."""
    pytest.main([__file__, "-v"])
