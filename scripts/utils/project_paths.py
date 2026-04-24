"""
Project Path Discovery

Graph-theoretic approach to discovering the project root and navigating
to known semantic locations within the project structure.

Philosophy:
- The project root is identified by MARKERS, not by relative position
- Directory structure is a GRAPH with semantic nodes
- Navigation is about INTENT (finding "the schema directory") not mechanics
  (going up 3 levels then down 2)
"""

from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class ProjectStructure:
    """
    Represents the semantic structure of the project.
    
    This is the INTENT - the graph structure we expect to find.
    """
    root: Path
    
    @property
    def data_dir(self) -> Path:
        """The data directory - semantic location for all project data."""
        return self.root / "data"
    
    @property
    def schema_dir(self) -> Path:
        """The schema directory - semantic location for schema definitions."""
        return self.data_dir / "schemas"
    
    @property
    def logs_dir(self) -> Path:
        """The logs directory - semantic location for runtime logs."""
        return self.data_dir / "logs"
    
    @property
    def agent_state_dir(self) -> Path:
        """The agent state directory - semantic location for agent state."""
        return self.data_dir / "agent_state"
    
    @property
    def book_data_dir(self) -> Path:
        """The book data directory - semantic location for book projects."""
        return self.data_dir / "book_data"
    
    @property
    def scripts_dir(self) -> Path:
        """The scripts directory - semantic location for executable code."""
        return self.root / "scripts"
    
    @property
    def tests_dir(self) -> Path:
        """The tests directory - semantic location for test code."""
        return self.root / "tests"
    
    def __repr__(self) -> str:
        return f"ProjectStructure(root={self.root})"


class ProjectRootNotFoundError(Exception):
    """Raised when we cannot discover the project root."""
    pass


def find_project_root(
    start_path: Optional[Path] = None,
    markers: Optional[List[str]] = None
) -> Path:
    """
    Discover the project root by looking for distinctive markers.
    
    This implements a SEARCH through the filesystem graph, looking for
    nodes that have the semantic properties we expect of a project root.
    
    Args:
        start_path: Where to start searching (defaults to current file's location)
        markers: List of markers to look for (defaults to standard markers)
        
    Returns:
        Path to the project root
        
    Raises:
        ProjectRootNotFoundError: If we cannot find the project root
        
    Algorithm:
        1. Start from start_path
        2. For each parent directory up to filesystem root:
           - Check if any marker exists in that directory
           - If found, that's our project root
        3. If we reach filesystem root without finding markers, fail
        
    Philosophy:
        We're not counting levels or making assumptions about structure.
        We're SEARCHING for a node with specific properties.
    """
    if start_path is None:
        # Start from this file's location
        start_path = Path(__file__).resolve()
    else:
        start_path = Path(start_path).resolve()
    
    if markers is None:
        # Standard markers that indicate a project root
        markers = [
            '.git',              # Git repository
            'pyproject.toml',    # Python project config
            'setup.py',          # Python package setup
            'requirements.txt',  # Python dependencies (weaker signal)
            'package.json',      # JavaScript project
        ]
    
    # Walk up the directory tree
    current = start_path if start_path.is_dir() else start_path.parent
    
    while True:
        # Check each marker
        for marker in markers:
            marker_path = current / marker
            if marker_path.exists():
                # Found a marker! This is our project root.
                return current
        
        # Move to parent
        parent = current.parent
        
        # Check if we've reached the filesystem root
        if parent == current:
            # We've exhausted the search without finding markers
            break
        
        current = parent
    
    raise ProjectRootNotFoundError(
        f"Could not find project root starting from {start_path}. "
        f"Looked for markers: {markers}"
    )


def discover_project_structure(
    start_path: Optional[Path] = None,
    markers: Optional[List[str]] = None
) -> ProjectStructure:
    """
    Discover the complete project structure.
    
    This is the high-level API that combines root discovery with
    semantic structure definition.
    
    Args:
        start_path: Where to start searching for project root
        markers: List of markers to look for
        
    Returns:
        ProjectStructure with all semantic paths defined
        
    Raises:
        ProjectRootNotFoundError: If we cannot find the project root
    """
    root = find_project_root(start_path, markers)
    return ProjectStructure(root=root)


def verify_project_structure(structure: ProjectStructure) -> Tuple[bool, List[str]]:
    """
    Verify that the expected project structure exists.
    
    This checks that the semantic nodes we expect to find actually exist
    in the filesystem graph.
    
    Args:
        structure: The project structure to verify
        
    Returns:
        Tuple of (all_valid, list_of_issues)
        
    Philosophy:
        After DISCOVERING the structure, we VERIFY it matches our expectations.
        This separates the "where is the project?" question from the
        "does the project have the structure we expect?" question.
    """
    issues = []
    
    # Critical directories that should exist
    critical_paths = [
        ("data directory", structure.data_dir),
        ("schema directory", structure.schema_dir),
        ("scripts directory", structure.scripts_dir),
    ]
    
    # Check each critical path
    for name, path in critical_paths:
        if not path.exists():
            issues.append(f"Missing {name}: {path}")
        elif not path.is_dir():
            issues.append(f"{name} exists but is not a directory: {path}")
    
    return (len(issues) == 0, issues)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_project_root() -> Path:
    """
    Get the project root, starting from this file.
    
    This is the most common use case - just give me the project root!
    """
    return find_project_root()


def get_project_structure() -> ProjectStructure:
    """
    Get the complete project structure, starting from this file.
    
    This is the most common use case - give me the whole structure!
    """
    return discover_project_structure()


# =============================================================================
# MODULE-LEVEL CACHE
# =============================================================================

# We cache the project structure at module level so we don't have to
# re-discover it every time. This is safe because the project root
# doesn't move during execution.
_PROJECT_STRUCTURE: Optional[ProjectStructure] = None


def get_cached_project_structure() -> ProjectStructure:
    """
    Get the project structure, using cached value if available.
    
    This is the FASTEST way to get project paths in hot paths.
    """
    global _PROJECT_STRUCTURE
    
    if _PROJECT_STRUCTURE is None:
        _PROJECT_STRUCTURE = get_project_structure()
    
    return _PROJECT_STRUCTURE


# =============================================================================
# TESTING/DEBUGGING
# =============================================================================

if __name__ == '__main__':
    """
    Test the project discovery system.
    """
    try:
        print("Discovering project structure...")
        structure = get_project_structure()
        
        print(f"\n✓ Found project root: {structure.root}")
        print(f"\nSemantic paths:")
        print(f"  data_dir:        {structure.data_dir}")
        print(f"  schema_dir:      {structure.schema_dir}")
        print(f"  logs_dir:        {structure.logs_dir}")
        print(f"  agent_state_dir: {structure.agent_state_dir}")
        print(f"  book_data_dir:   {structure.book_data_dir}")
        print(f"  scripts_dir:     {structure.scripts_dir}")
        print(f"  tests_dir:       {structure.tests_dir}")
        
        print(f"\nVerifying structure...")
        valid, issues = verify_project_structure(structure)
        
        if valid:
            print("✓ Structure is valid!")
        else:
            print("✗ Structure has issues:")
            for issue in issues:
                print(f"  - {issue}")
        
    except ProjectRootNotFoundError as e:
        print(f"✗ {e}")
