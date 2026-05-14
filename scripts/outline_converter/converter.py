"""
Outline Converter Agent
Converts various outline formats to the standardized Work Outline Schema v2.1
Enhanced with comprehensive metadata integration
"""

import yaml
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime


class OutlineConverter:
    """
    Main converter class that orchestrates parsing and mapping to v2.0 schema.
    """
    
    def __init__(self, llm_provider=None):
        """
        Initialize converter with optional LLM provider for semantic extraction.
        
        Args:
            llm_provider: Optional LLM interface for intelligent extraction
        """
        self.llm_provider = llm_provider
        self.schema_version = "2.1"
        
    def detect_format(self, content: str) -> str:
        """
        Detect the format of the input outline.
        
        Returns:
            Format type: 'nested_nodes', 'numbered_hierarchy', 'markdown', 'yaml_v1'
        """
        # Check for node-based format
        if '<node-singleton>' in content or '<node-with-children>' in content:
            return 'nested_nodes'
        
        # Check for numbered hierarchy (1., 1.1, 1.1.1, etc.)
        if re.search(r'^\s*\d+\.\s+\S', content, re.MULTILINE):
            return 'numbered_hierarchy'
        
        # Check for markdown headers
        if re.search(r'^#{1,6}\s+\S', content, re.MULTILINE):
            return 'markdown'
        
        # Check for YAML v1.0 format
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and 'outline' in data:
                return 'yaml_v1'
        except:
            pass
        
        return 'unknown'
    
    def parse_outline(self, content: str, format_type: str = None) -> Dict[str, Any]:
        """
        Parse outline content into intermediate representation.
        
        Args:
            content: Raw outline text
            format_type: Optional format override
            
        Returns:
            Parsed outline structure
        """
        if format_type is None:
            format_type = self.detect_format(content)
        
        if format_type == 'nested_nodes':
            return self._parse_nested_nodes(content)
        elif format_type == 'numbered_hierarchy':
            return self._parse_numbered_hierarchy(content)
        elif format_type == 'markdown':
            return self._parse_markdown(content)
        elif format_type == 'yaml_v1':
            return self._parse_yaml_v1(content)
        else:
            raise ValueError(f"Unknown format: {format_type}")
    
    def _parse_nested_nodes(self, content: str) -> Dict[str, Any]:
        """Parse nested node format (like the Digital Symmetries example)."""
        lines = content.split('\n')
        
        # Extract title from first line or header
        title_match = re.search(r'^(.+?)(?:\n|$)', content)
        title = title_match.group(1).strip() if title_match else "Untitled Work"
        
        # Extract summary if present
        summary_match = re.search(r'###\s*Summary of Understanding\s*\n(.*?)(?=<node-|$)', 
                                  content, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else ""
        
        parsed = {
            'title': title,
            'summary': summary,
            'structure': [],
            'front_matter': {},
            'back_matter': {}
        }
        
        current_section = None
        indent_stack = []
        
        for line in lines:
            # Skip empty lines and summary section
            if not line.strip() or line.strip().startswith('###'):
                continue
            
            # Detect node types
            singleton_match = re.match(r'<node-singleton>\s*(.+)', line)
            children_match = re.match(r'<node-with-children>\s*(.+)', line)
            
            if singleton_match or children_match:
                node_title = singleton_match.group(1) if singleton_match else children_match.group(1)
                node_title = node_title.strip()
                
                # Determine if this is front/back matter or main content
                if node_title.lower() in ['front matter', 'preface', 'notation', 
                                          'acknowledgments', 'methodological protocol']:
                    current_section = 'front_matter'
                elif node_title.lower() in ['bibliography', 'back matter', 'appendices',
                                            'glossary', 'index']:
                    current_section = 'back_matter'
                elif node_title.lower() in ['chapters', 'parts']:
                    current_section = 'structure'
                else:
                    # Regular structural element
                    node = {
                        'title': node_title,
                        'type': self._infer_type(node_title),
                        'content': []
                    }
                    
                    if current_section == 'structure':
                        parsed['structure'].append(node)
                        indent_stack = [node]
            else:
                # Regular indented line - parse as subsection
                indent = len(line) - len(line.lstrip())
                content_text = line.strip()
                
                if content_text and current_section == 'structure' and indent_stack:
                    # Add to current section
                    subsection = {
                        'title': content_text,
                        'type': 'section',
                        'content': []
                    }
                    indent_stack[-1]['content'].append(subsection)
        
        return parsed
    
    def _parse_numbered_hierarchy(self, content: str) -> Dict[str, Any]:
        """Parse numbered hierarchy format (like the Quantum Categories example)."""
        lines = content.split('\n')
        
        # Extract title from first line
        title = lines[0].strip() if lines else "Untitled Work"
        
        parsed = {
            'title': title,
            'summary': '',
            'structure': [],
            'front_matter': {},
            'back_matter': {}
        }
        
        current_section = None
        chapter_stack = []
        
        for line in lines[1:]:
            if not line.strip():
                continue
            
            # Detect section markers
            if line.strip().lower() == 'front matter':
                current_section = 'front_matter'
                continue
            elif line.strip().lower() == 'back matter':
                current_section = 'back_matter'
                continue
            elif line.strip().lower() == 'chapters':
                current_section = 'chapters'
                continue
            
            # Parse numbered items (1., 1.1, 1.1.1, etc.)
            numbered_match = re.match(r'^(\d+(?:\.\d+)*)\.\s+(.+)', line.strip())
            if numbered_match:
                number = numbered_match.group(1)
                title_text = numbered_match.group(2).strip()
                depth = number.count('.')
                
                node = {
                    'number': number,
                    'title': title_text,
                    'type': self._number_to_type(depth),
                    'content': []
                }
                
                if current_section == 'chapters':
                    if depth == 0:  # Chapter level
                        parsed['structure'].append(node)
                        chapter_stack = [node]
                    elif depth == 1 and chapter_stack:  # Section level
                        chapter_stack[0]['content'].append(node)
                        if len(chapter_stack) > 1:
                            chapter_stack = [chapter_stack[0], node]
                        else:
                            chapter_stack.append(node)
                    elif depth >= 2 and len(chapter_stack) >= 2:  # Subsection+
                        chapter_stack[-1]['content'].append(node)
            
            # Parse bullet points in front/back matter
            elif line.strip().startswith('*'):
                item_text = line.strip()[1:].strip()
                if ':' in item_text:
                    key, value = item_text.split(':', 1)
                    key = key.strip().lower().replace(' ', '_')
                    value = value.strip()
                    
                    if current_section == 'front_matter':
                        parsed['front_matter'][key] = value
                    elif current_section == 'back_matter':
                        parsed['back_matter'][key] = value
        
        return parsed
    
    def _parse_markdown(self, content: str) -> Dict[str, Any]:
        """Parse markdown-style outline with # headers."""
        lines = content.split('\n')
        
        # Extract title from first # header
        title_match = re.search(r'^#\s+(.+)', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Untitled Work"
        
        parsed = {
            'title': title,
            'summary': '',
            'structure': [],
            'front_matter': {},
            'back_matter': {}
        }
        
        current_chapter = None
        header_stack = []
        
        for line in lines:
            # Parse markdown headers
            header_match = re.match(r'^(#{1,6})\s+(.+)', line)
            if header_match:
                level = len(header_match.group(1))
                title_text = header_match.group(2).strip()
                
                node = {
                    'title': title_text,
                    'type': self._header_level_to_type(level),
                    'content': []
                }
                
                if level == 2:  # Chapter
                    parsed['structure'].append(node)
                    header_stack = [node]
                elif level >= 3 and header_stack:  # Section+
                    # Find appropriate parent
                    target_depth = level - 3
                    parent = header_stack[min(target_depth, len(header_stack)-1)]
                    parent['content'].append(node)
                    
                    # Update stack
                    header_stack = header_stack[:target_depth+1] + [node]
        
        return parsed
    
    def _parse_yaml_v1(self, content: str) -> Dict[str, Any]:
        """Parse original YAML v1.0 format."""
        data = yaml.safe_load(content)
        outline = data.get('outline', {})
        
        parsed = {
            'title': outline.get('title', 'Untitled Work'),
            'summary': outline.get('summary', ''),
            'intent': outline.get('intent', {}),
            'structure': [],
            'front_matter': {},
            'back_matter': {}
        }
        
        # Convert chapters to structure
        chapters = outline.get('chapters', [])
        for ch in chapters:
            chapter_node = {
                'id': ch.get('id', ''),
                'title': ch.get('title', ''),
                'type': 'chapter',
                'goal': ch.get('goal', ''),
                'summary': ch.get('summary', ''),
                'content': []
            }
            
            # Convert sections
            sections = ch.get('sections', [])
            for sec in sections:
                section_node = {
                    'id': sec.get('id', ''),
                    'title': sec.get('title', ''),
                    'type': 'section',
                    'summary': sec.get('content_summary', '')
                }
                chapter_node['content'].append(section_node)
            
            parsed['structure'].append(chapter_node)
        
        return parsed
    
    def _infer_type(self, title: str) -> str:
        """Infer structural type from title."""
        title_lower = title.lower()
        if 'part' in title_lower and title_lower.startswith('part'):
            return 'part'
        elif 'chapter' in title_lower or re.match(r'^\d+\.', title):
            return 'chapter'
        else:
            return 'section'
    
    def _number_to_type(self, depth: int) -> str:
        """Convert numbering depth to type."""
        types = ['chapter', 'section', 'subsection', 'subsubsection', 'subsubsubsection']
        return types[min(depth, len(types)-1)]
    
    def _header_level_to_type(self, level: int) -> str:
        """Convert markdown header level to type."""
        if level == 1:
            return 'part'
        elif level == 2:
            return 'chapter'
        elif level == 3:
            return 'section'
        elif level == 4:
            return 'subsection'
        else:
            return 'subsubsection'
    
    def map_to_schema_v2(self, parsed: Dict[str, Any], 
                         interactive: bool = True) -> Dict[str, Any]:
        """
        Map parsed outline to Work Outline Schema v2.1 (with comprehensive metadata).
        
        Args:
            parsed: Parsed outline structure
            interactive: Whether to prompt for missing information
            
        Returns:
            Complete v2.1 schema dictionary
        """
        # Create base structure
        work = {
            'id': self._generate_id(parsed['title']),
            'type': 'book',  # Default, can be overridden
            'title': parsed['title'],
            'subtitle': '',
            'summary': parsed.get('summary', ''),
            'intent': parsed.get('intent', self._create_default_intent()),
            'authors': [self._create_default_author()],
            'metadata': self._create_metadata(),
            'front_matter': self._map_front_matter(parsed.get('front_matter', {})),
            'structure': self._map_structure(parsed['structure']),
            'citations': {'entries': []},
            'diagrams': [],
            'media': [],
            'back_matter': self._map_back_matter(parsed.get('back_matter', {})),
            'compilation': self._create_default_compilation()
        }
        
        if interactive:
            work = self._interactive_fill(work)
        
        return {'work': work}
    
    def _generate_id(self, title: str) -> str:
        """Generate a valid ID from title."""
        # Convert to lowercase, replace spaces with underscores
        id_str = title.lower()
        id_str = re.sub(r'[^a-z0-9\s]', '', id_str)
        id_str = re.sub(r'\s+', '_', id_str)
        return id_str[:50]  # Limit length
    
    def _create_default_intent(self) -> Dict[str, str]:
        """Create default intent section."""
        return {
            'audience': 'TO BE SPECIFIED',
            'writing_style': 'TO BE SPECIFIED',
            'author_persona': 'TO BE SPECIFIED',
            'reader_takeaway': 'TO BE SPECIFIED',
            'genre': 'nonfiction'
        }
    
    def _create_default_author(self) -> Dict[str, str]:
        """Create default author entry."""
        return {
            'name': 'TO BE SPECIFIED',
            'affiliation': '',
            'email': '',
            'role': 'author'
        }
    
    def _create_metadata(self) -> Dict[str, Any]:
        """Create comprehensive metadata with all 8 categories."""
        today = datetime.now().strftime('%Y-%m-%d')
        current_year = str(datetime.now().year)
        
        return {
            'descriptive': {
                'abstract': '',
                'keywords': [],
                'subject': '',
                'language': 'en',
                'genre': 'nonfiction',
                'intended_audience': ''
            },
            
            'administrative': {
                'provenance': {
                    'authors': [],
                    'maintainer': 'author',
                    'created_by': ''
                },
                'versioning': {
                    'version': '0.1.0',
                    'changelog': [
                        {
                            'version': '0.1.0',
                            'date': today,
                            'changes': 'Initial outline created'
                        }
                    ],
                    'release_notes': ''
                },
                'timestamps': {
                    'created': today,
                    'modified': today,
                    'published': '',
                    'archived': ''
                },
                'rights_and_access': {
                    'license': 'CC-BY-4.0',
                    'copyright_holder': 'TO BE SPECIFIED',
                    'copyright_year': current_year,
                    'access_permissions': ['open_access'],
                    'embargo_date': '',
                    'usage_terms': '',
                    'distribution_rights': ''
                }
            },
            
            'structural': {
                'section_hierarchy': [],
                'page_count': 0,
                'word_count': 0,
                'figure_count': 0,
                'table_count': 0,
                'diagram_count': 0,
                'equation_count': 0,
                'file_manifest': [],
                'citation_map': {}
            },
            
            'technical': {
                'file_format': 'YAML',
                'encoding': 'UTF-8',
                'file_size_bytes': 0,
                'checksum': '',
                'page_dimensions': '',
                'dpi': 300,
                'font_info': [],
                'software_used': [],
                'dependencies': []
            },
            
            'semantic': {
                'ontology': [],
                'thesis_statement': '',
                'research_questions': [],
                'key_definitions': [],
                'argument_structure': '',
                'purpose': '',
                'methodology': '',
                'epistemological_stance': ''
            },
            
            'relational': {
                'references': [],
                'cited_by': [],
                'related_works': [],
                'supersedes': '',
                'superseded_by': '',
                'derived_from': '',
                'linked_uris': [],
                'companion_materials': []
            },
            
            'contextual': {
                'historical_context': '',
                'geographic_context': '',
                'cultural_context': '',
                'institutional_context': '',
                'funding_sources': [],
                'disclaimers': []
            },
            
            'computational': {
                'schema_version': '2.0',
                'unique_identifier': self._generate_uuid(),
                'machine_readable_format': 'YAML',
                'api_endpoints': [],
                'validation_status': {
                    'schema_valid': False,
                    'dependencies_resolved': False,
                    'citations_verified': False,
                    'last_validated': ''
                },
                'execution_logs': [
                    {
                        'timestamp': datetime.now().isoformat() + 'Z',
                        'agent': 'outline_converter',
                        'action': 'created_outline'
                    }
                ],
                'build_metadata': {
                    'last_build': '',
                    'build_system': '',
                    'output_artifacts': []
                },
                'machine_tags': ['auto-generated-outline']
            }
        }
    
    def _generate_uuid(self) -> str:
        """Generate a simple UUID-like identifier."""
        import hashlib
        timestamp = datetime.now().isoformat()
        hash_obj = hashlib.md5(timestamp.encode())
        return f"uuid-{hash_obj.hexdigest()[:16]}"
    
    def _map_front_matter(self, fm: Dict[str, Any]) -> Dict[str, Any]:
        """Map front matter to v2.0 structure."""
        return {
            'title_page': {'enabled': True},
            'copyright_page': {
                'enabled': True,
                'year': str(datetime.now().year),
                'holder': 'TO BE SPECIFIED'
            },
            'dedication': {'enabled': False, 'text': ''},
            'epigraph': {'enabled': False, 'quote': '', 'attribution': ''},
            'table_of_contents': {'enabled': True, 'depth': 3},
            'list_of_figures': {'enabled': False},
            'list_of_tables': {'enabled': False},
            'preface': {
                'enabled': 'preface' in str(fm).lower(),
                'content_file': ''
            },
            'acknowledgments': {
                'enabled': 'acknowledgment' in str(fm).lower(),
                'content_file': ''
            }
        }
    
    def _map_structure(self, structure: List[Dict]) -> List[Dict]:
        """Recursively map structure to v2.1 format."""
        result = []
        
        for idx, item in enumerate(structure, 1):
            node = {
                'type': item.get('type', 'chapter'),
                'id': item.get('id', f"{item['type']}_{idx:02d}"),
                'number': item.get('number', idx),
                'title': item['title'],
                'goal': item.get('goal', ''),
                'summary': item.get('summary', ''),
                'prerequisites': [],
                'dependencies': {'structural': [], 'narrative': ''},
                'key_concepts': [],
                'citations': []
            }
            
            # Recursively process children
            if 'content' in item and item['content']:
                node['content'] = self._map_structure(item['content'])
            else:
                # Leaf node - needs content_file or content_text
                node['content_file'] = f"sections/{node['id']}.md"
            
            result.append(node)
        
        return result
    
    def _map_back_matter(self, bm: Dict[str, Any]) -> Dict[str, Any]:
        """Map back matter to v2.1 structure."""
        return {
            'appendices': [],
            'glossary': {'enabled': 'glossary' in str(bm).lower(), 'entries': []},
            'bibliography': {'enabled': True, 'style': 'APA', 'source': 'citations.entries'},
            'index': {'enabled': False, 'auto_generate': False},
            'about_author': {'enabled': False, 'content_file': ''}
        }
    
    def _create_default_compilation(self) -> Dict[str, Any]:
        """Create default compilation settings."""
        return {
            'output_formats': ['pdf'],
            'pdf_settings': {
                'document_class': 'book',
                'paper_size': 'letter',
                'font_size': '11pt',
                'two_side': True
            },
            'validation': {
                'check_dependencies': True,
                'check_citations': True,
                'check_cross_refs': True,
                'orphan_detection': True
            }
        }
    
    def _interactive_fill(self, work: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interactively prompt for missing information.
        (This would be enhanced with actual user input in production)
        """
        # For now, just flag fields that need attention
        if work['authors'][0]['name'] == 'TO BE SPECIFIED':
            print("⚠️  Author name needs to be specified")
        
        if work['intent']['audience'] == 'TO BE SPECIFIED':
            print("⚠️  Intent fields need to be specified")
        
        return work
    
    def convert(self, input_content: str, output_path: str = None,
                format_type: str = None, interactive: bool = True) -> str:
        """
        Main conversion method.
        
        Args:
            input_content: Raw outline text or file path
            output_path: Where to save output YAML
            format_type: Optional format override
            interactive: Whether to prompt for missing info
            
        Returns:
            YAML string of converted outline
        """
        # Check if input is a file path (short string without newlines)
        if len(input_content) < 500 and '\n' not in input_content:
            try:
                if Path(input_content).exists():
                    with open(input_content, 'r') as f:
                        content = f.read()
                else:
                    content = input_content
            except (OSError, ValueError):
                content = input_content
        else:
            content = input_content
        
        # Parse the outline
        print(f"🔍 Detecting format...")
        if format_type is None:
            format_type = self.detect_format(content)
        print(f"✓ Detected format: {format_type}")
        
        print(f"📖 Parsing outline...")
        parsed = self.parse_outline(content, format_type)
        print(f"✓ Parsed {len(parsed['structure'])} top-level elements")
        
        # Map to v2.1 schema
        print(f"🗺️  Mapping to schema v2.1...")
        schema_v2 = self.map_to_schema_v2(parsed, interactive)
        print(f"✓ Mapped to standardized format with comprehensive metadata")
        
        # Convert to YAML
        yaml_output = yaml.dump(schema_v2, sort_keys=False, 
                                allow_unicode=True, default_flow_style=False)
        
        # Save if output path specified
        if output_path:
            with open(output_path, 'w') as f:
                f.write(yaml_output)
            print(f"💾 Saved to: {output_path}")
        
        return yaml_output


def main():
    """CLI interface for the converter."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python converter.py <input_file> [output_file]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    converter = OutlineConverter()
    
    try:
        result = converter.convert(input_file, output_file, interactive=True)
        
        if not output_file:
            print("\n" + "="*60)
            print("CONVERTED OUTLINE (v2.1 - Comprehensive Metadata)")
            print("="*60)
            print(result)
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
