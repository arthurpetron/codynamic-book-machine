"""
Schema Registry - Dynamic Schema Discovery and Version Management

This module provides the single source of truth for schema discovery.
NO HARDCODED VERSION NUMBERS - everything is discoverable and versioned properly.

The registry supports:
- Semantic versioning (major.minor.patch)
- Automatic discovery of latest versions
- Explicit version selection
- Backward compatibility tracking
- Multiple schema types
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from scripts.utils.project_paths import get_cached_project_structure


@dataclass
class SchemaVersion:
    """Represents a specific version of a schema."""
    version: str  # Semantic version: "2.1.0"
    json_file: str
    yaml_file: str
    released: str
    status: str  # "current", "stable", "deprecated", "experimental"
    breaking_changes: bool
    changelog: str
    compatible_with: List[str]
    
    def __lt__(self, other):
        """Compare versions for sorting."""
        return self._parse_version() < other._parse_version()
    
    def _parse_version(self) -> Tuple[int, int, int]:
        """Parse semantic version into tuple for comparison."""
        match = re.match(r'(\d+)\.(\d+)\.(\d+)', self.version)
        if not match:
            raise ValueError(f"Invalid semantic version: {self.version}")
        return tuple(int(x) for x in match.groups())


class SchemaRegistry:
    """
    Dynamic schema registry with automatic version discovery.
    
    This is the ONLY way schemas should be accessed in the system.
    
    Registry location is discoverable via:
    1. Constructor parameter (highest priority)
    2. Environment variable SCHEMA_REGISTRY_PATH (full path)
    3. Environment variable SCHEMA_REGISTRY_FILE (filename in schema_dir)
    4. Default convention: schema_registry.json in schema_dir
    """
    
    DEFAULT_REGISTRY_FILE = "schema_registry.json"
    ENV_REGISTRY_PATH = "SCHEMA_REGISTRY_PATH"  # Full path to registry
    ENV_REGISTRY_FILE = "SCHEMA_REGISTRY_FILE"  # Just filename
    ENV_SCHEMA_DIR = "SCHEMA_DIR"  # Schema directory override
    
    def __init__(self, 
                 schema_dir: Optional[Path] = None,
                 registry_file: Optional[str] = None,
                 registry_path: Optional[Path] = None):
        """
        Initialize the schema registry with discoverable configuration.
        
        Priority order for registry location:
        1. registry_path parameter (if provided) - exact path
        2. SCHEMA_REGISTRY_PATH env var (if set) - exact path
        3. registry_file parameter + schema_dir - filename in directory
        4. SCHEMA_REGISTRY_FILE env var + schema_dir - filename in directory
        5. DEFAULT_REGISTRY_FILE + schema_dir - default convention
        
        Args:
            schema_dir: Path to schemas directory. If None, uses default or env var.
            registry_file: Registry filename. If None, uses env var or default.
            registry_path: Full path to registry. Overrides all other options.
        """
        import os
        
        # Determine schema directory
        if schema_dir is None:
            # Check environment variable
            env_schema_dir = os.getenv(self.ENV_SCHEMA_DIR)
            if env_schema_dir:
                schema_dir = Path(env_schema_dir)
            else:
                # Default to project structure using robust discovery
                schema_dir = get_cached_project_structure().schema_dir
        
        self.schema_dir = Path(schema_dir)
        
        # Determine registry path using priority order
        if registry_path is not None:
            # Explicit path provided - use it
            self.registry_path = Path(registry_path)
        else:
            # Check for full path in environment
            env_registry_path = os.getenv(self.ENV_REGISTRY_PATH)
            if env_registry_path:
                self.registry_path = Path(env_registry_path)
            else:
                # Determine filename
                if registry_file is None:
                    # Check environment for filename
                    registry_file = os.getenv(
                        self.ENV_REGISTRY_FILE, 
                        self.DEFAULT_REGISTRY_FILE
                    )
                
                # Combine directory and filename
                self.registry_path = self.schema_dir / registry_file
        
        # Load registry
        self.registry = self._load_registry()
    
    def _load_registry(self) -> Dict[str, Any]:
        """
        Load the schema registry.
        
        If registry file doesn't exist, attempt to discover schemas from filesystem.
        """
        if not self.registry_path.exists():
            print(f"⚠️  Registry not found at {self.registry_path}")
            print("   Attempting filesystem discovery...")
            return self._discover_schemas_from_filesystem()
        
        with open(self.registry_path, 'r') as f:
            return json.load(f)
    
    def _discover_schemas_from_filesystem(self) -> Dict[str, Any]:
        """
        Discover schemas by scanning the filesystem.
        
        This is a fallback when registry doesn't exist.
        Looks for files matching: {schema_name}_{major}.{minor}.{patch}.{format}
        """
        discovered = {
            "schemas": {},
            "metadata": {
                "registry_version": "auto-discovered",
                "last_updated": datetime.now().isoformat(),
                "naming_convention": "{schema_name}_{major}.{minor}.{patch}.{format}",
                "version_format": "semver"
            }
        }
        
        # Pattern: schema_name_X.Y.Z.json/yaml
        pattern = re.compile(r'^([a-z_]+)_(\d+\.\d+\.\d+)\.(json|yaml)$')
        
        schema_files = {}
        for file in self.schema_dir.glob('*_*.json'):
            match = pattern.match(file.name)
            if match:
                schema_name, version, format_type = match.groups()
                
                if schema_name not in schema_files:
                    schema_files[schema_name] = {}
                if version not in schema_files[schema_name]:
                    schema_files[schema_name][version] = {}
                
                schema_files[schema_name][version][f'{format_type}_file'] = file.name
        
        # Convert to registry format
        for schema_name, versions in schema_files.items():
            discovered["schemas"][schema_name] = {
                "name": schema_name.replace('_', ' ').title(),
                "description": "Auto-discovered schema",
                "latest": max(versions.keys()) if versions else None,
                "stable": max(versions.keys()) if versions else None,
                "versions": {}
            }
            
            for version, files in versions.items():
                discovered["schemas"][schema_name]["versions"][version] = {
                    **files,
                    "released": "unknown",
                    "status": "discovered",
                    "breaking_changes": False,
                    "changelog": "Auto-discovered from filesystem",
                    "compatible_with": []
                }
        
        print(f"✓ Discovered {len(schema_files)} schema(s) from filesystem")
        return discovered
    
    def get_schema_names(self) -> List[str]:
        """Get list of all available schema names."""
        return list(self.registry.get("schemas", {}).keys())
    
    def get_versions(self, schema_name: str) -> List[str]:
        """
        Get all versions for a schema, sorted newest to oldest.
        
        Args:
            schema_name: Name of the schema (e.g., "work_outline")
            
        Returns:
            List of version strings
        """
        schema = self.registry.get("schemas", {}).get(schema_name)
        if not schema:
            raise ValueError(f"Schema '{schema_name}' not found in registry")
        
        versions = list(schema.get("versions", {}).keys())
        # Sort by semantic version
        versions.sort(key=lambda v: tuple(int(x) for x in v.split('.')), reverse=True)
        return versions
    
    def get_latest_version(self, schema_name: str) -> str:
        """
        Get the latest version for a schema.
        
        Args:
            schema_name: Name of the schema
            
        Returns:
            Latest version string
        """
        schema = self.registry.get("schemas", {}).get(schema_name)
        if not schema:
            raise ValueError(f"Schema '{schema_name}' not found in registry")
        
        return schema.get("latest")
    
    def get_stable_version(self, schema_name: str) -> str:
        """
        Get the stable (recommended) version for a schema.
        
        Args:
            schema_name: Name of the schema
            
        Returns:
            Stable version string
        """
        schema = self.registry.get("schemas", {}).get(schema_name)
        if not schema:
            raise ValueError(f"Schema '{schema_name}' not found in registry")
        
        return schema.get("stable")
    
    def get_schema_info(self, schema_name: str, version: Optional[str] = None) -> SchemaVersion:
        """
        Get detailed information about a schema version.
        
        Args:
            schema_name: Name of the schema
            version: Optional version. If None, uses latest.
            
        Returns:
            SchemaVersion object with metadata
        """
        schema = self.registry.get("schemas", {}).get(schema_name)
        if not schema:
            raise ValueError(f"Schema '{schema_name}' not found in registry")
        
        if version is None:
            version = schema.get("latest")
        
        version_data = schema.get("versions", {}).get(version)
        if not version_data:
            available = ", ".join(self.get_versions(schema_name))
            raise ValueError(
                f"Version '{version}' not found for schema '{schema_name}'. "
                f"Available versions: {available}"
            )
        
        return SchemaVersion(
            version=version,
            json_file=version_data.get("json_file", ""),
            yaml_file=version_data.get("yaml_file", ""),
            released=version_data.get("released", "unknown"),
            status=version_data.get("status", "unknown"),
            breaking_changes=version_data.get("breaking_changes", False),
            changelog=version_data.get("changelog", ""),
            compatible_with=version_data.get("compatible_with", [])
        )
    
    def get_schema_path(self, schema_name: str, 
                       version: Optional[str] = None,
                       format_type: str = "json") -> Path:
        """
        Get the full path to a schema file.
        
        Args:
            schema_name: Name of the schema
            version: Optional version. If None, uses latest.
            format_type: "json" or "yaml"
            
        Returns:
            Path to schema file
        """
        info = self.get_schema_info(schema_name, version)
        
        if format_type == "json":
            filename = info.json_file
        elif format_type == "yaml":
            filename = info.yaml_file
        else:
            raise ValueError(f"Invalid format_type: {format_type}. Use 'json' or 'yaml'")
        
        if not filename:
            raise ValueError(f"No {format_type} file defined for {schema_name} v{info.version}")
        
        path = self.schema_dir / filename
        
        if not path.exists():
            raise FileNotFoundError(
                f"Schema file not found: {path}\n"
                f"Registry says it should be there, but it isn't. "
                f"Registry may be out of sync with filesystem."
            )
        
        return path
    
    def load_schema(self, schema_name: str,
                   version: Optional[str] = None,
                   format_type: str = "json") -> Dict[str, Any]:
        """
        Load a schema into memory.
        
        Args:
            schema_name: Name of the schema
            version: Optional version. If None, uses latest.
            format_type: "json" or "yaml"
            
        Returns:
            Schema as dictionary
        """
        path = self.get_schema_path(schema_name, version, format_type)
        
        if format_type == "json":
            with open(path, 'r') as f:
                return json.load(f)
        else:  # yaml
            import yaml
            with open(path, 'r') as f:
                return yaml.safe_load(f)
    
    def print_registry_summary(self):
        """Print a human-readable summary of the registry."""
        print("=" * 60)
        print("SCHEMA REGISTRY")
        print("=" * 60)
        
        metadata = self.registry.get("metadata", {})
        print(f"\nRegistry Version: {metadata.get('registry_version', 'unknown')}")
        print(f"Last Updated: {metadata.get('last_updated', 'unknown')}")
        print(f"Naming Convention: {metadata.get('naming_convention', 'unknown')}")
        
        schemas = self.registry.get("schemas", {})
        print(f"\nAvailable Schemas: {len(schemas)}")
        
        for schema_name, schema_data in schemas.items():
            print(f"\n  {schema_name}:")
            print(f"    Name: {schema_data.get('name', 'N/A')}")
            print(f"    Latest: {schema_data.get('latest', 'N/A')}")
            print(f"    Stable: {schema_data.get('stable', 'N/A')}")
            print(f"    Versions: {', '.join(self.get_versions(schema_name))}")
        
        print("\n" + "=" * 60)


# Convenience functions
def get_registry(schema_dir: Optional[Path] = None) -> SchemaRegistry:
    """Get a schema registry instance."""
    return SchemaRegistry(schema_dir)


def get_latest_schema(schema_name: str, 
                     schema_dir: Optional[Path] = None,
                     format_type: str = "json") -> Tuple[Dict[str, Any], str]:
    """
    Convenience function to get the latest version of a schema.
    
    Returns:
        Tuple of (schema_dict, version_string)
    """
    registry = get_registry(schema_dir)
    version = registry.get_latest_version(schema_name)
    schema = registry.load_schema(schema_name, version, format_type)
    return (schema, version)


if __name__ == '__main__':
    """
    Test the schema registry.
    """
    print("Testing Schema Registry\n")
    
    registry = get_registry()
    registry.print_registry_summary()
    
    print("\n\nLoading latest work_outline schema:")
    schema, version = get_latest_schema("work_outline")
    print(f"✓ Loaded work_outline schema version {version}")
    print(f"  Keys: {list(schema.keys())[:5]}...")
