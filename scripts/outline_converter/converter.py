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

from scripts.api import LLMProviderError, get_provider_with_fallback
from scripts.utils.schema_validator import SchemaValidator


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
        self.schema_version = "2.1.0"
        self.last_report: Dict[str, Any] = {}
        self.last_llm_error: Optional[str] = None
        
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

    def get_llm_provider(self):
        """Return an explicitly supplied provider or construct the configured fallback."""
        if self.llm_provider:
            return self.llm_provider
        try:
            self.llm_provider = get_provider_with_fallback()
            return self.llm_provider
        except LLMProviderError as e:
            self.last_llm_error = str(e)
            return None
    
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

    def convert_with_llm(self, content: str, source_format: str = "unknown") -> Dict[str, Any]:
        """
        Ask the configured LLM provider to convert arbitrary outline-like input.

        The result is accepted only if it parses as a dict and validates against
        the registered Work Outline schema.
        """
        provider = self.get_llm_provider()
        if not provider:
            raise ValueError(f"No LLM provider available: {self.last_llm_error}")

        output_contract = self._outline_agent_output_contract()
        system_prompt = (
            "You are the Codynamic Book Machine outline_agent. Convert the full "
            "source text into the canonical Work Outline Schema v2.1. Return only JSON "
            "with a single root key named work; do not wrap it in markdown fences "
            "and do not add commentary. Use the YAML contract below as the schema "
            "reference, but your response must be valid JSON with quoted strings.\n\n"
            "YAML schema reference:\n"
            f"{output_contract}\n\n"
            "Additional import rules:\n"
            "- The input below is the full imported outline/source text. Use all of it.\n"
            "- Preserve the source hierarchy recursively. Do not flatten nested A/B/C items, numbered sections, or subheadings into one top-level list.\n"
            "- Do not create generic wrapper nodes such as 'Outline' when the source already contains real numbered sections below that heading.\n"
            "- Put prose, bullets, numbered lists, and markdown tables into content_text as markdown. Do not use custom keys such as bullets, rows, table, or children.\n"
            "- Parent nodes may have both content_text and content. Use content for child sections and content_text for text directly under the parent heading.\n"
            "- For every node with content_text, also set content_file to content/sections/<node_id>.md.\n"
            "- Do not invent prose that is not in the source; concise summaries are allowed only in summary fields.\n"
            "- Use lowercase snake_case ids matching ^[a-z0-9_]+$."
        )
        prompt = f"""
Source format hint: {source_format}

Full imported outline/source text:
{content}

Return only the canonical JSON object.
"""
        response = provider.simple_prompt(
            prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=6000,
        )
        candidate = self._extract_structured_response(response.content)
        if "work" not in candidate and "outline" in candidate:
            parsed = self._parse_yaml_v1(yaml.safe_dump(candidate, sort_keys=False))
            candidate = self.map_to_schema_v2(parsed, interactive=False)
        elif "work" not in candidate:
            candidate = self.map_to_schema_v2(candidate, interactive=False)

        candidate = self._normalize_llm_candidate(candidate)
        valid, errors = SchemaValidator().validate(candidate)
        if not valid:
            raise ValueError(f"LLM conversion did not validate: {'; '.join(errors)}")

        return candidate

    def _outline_agent_output_contract(self) -> str:
        """Load the canonical YAML contract from the outline agent definition."""
        definition_path = Path(__file__).parents[1] / "agents" / "agent_definitions" / "outline_agent.yaml"
        try:
            definition = yaml.safe_load(definition_path.read_text()) or {}
            contract = definition.get("canonical_output_contract")
            if isinstance(contract, str) and contract.strip():
                return contract.strip()
        except Exception:
            pass
        return (
            "work:\n"
            "  id: lowercase_snake_case_work_id\n"
            "  type: book|paper|monograph|essay|article|thesis\n"
            "  title: Source title\n"
            "  metadata:\n"
            "    version: '0.1.0'\n"
            "    created: YYYY-MM-DD\n"
            "    updated: YYYY-MM-DD\n"
            "  structure:\n"
            "    - type: chapter|section|subsection|subsubsection|subsubsubsection\n"
            "      id: lowercase_snake_case_node_id\n"
            "      title: Source heading title\n"
            "      content_file: content/sections/lowercase_snake_case_node_id.md\n"
            "      content_text: |\n"
            "        Preserve source text here.\n"
        )

    def _normalize_llm_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Repair common near-canonical shapes returned by LLM conversion."""
        work = candidate.get("work")
        if not isinstance(work, dict):
            return candidate

        allowed_work_types = {"book", "paper", "monograph", "essay", "article", "thesis"}
        work_type = str(work.get("type") or "book").lower()
        if work_type == "document":
            work_type = "paper"
        work["type"] = work_type if work_type in allowed_work_types else "book"
        raw_work_id = str(work.get("id") or self._generate_id(str(work.get("title") or "imported_work")))
        work["id"] = re.sub(r"[^a-z0-9_]+", "_", raw_work_id.lower()).strip("_") or "imported_work"

        structure = work.get("structure")
        if isinstance(structure, dict):
            if isinstance(structure.get("children"), list):
                work["structure"] = structure["children"]
            elif isinstance(structure.get("content"), list):
                work["structure"] = structure["content"]
            else:
                work["structure"] = [structure]
        elif structure is None:
            work["structure"] = []

        used_ids: set[str] = set()
        work["structure"] = [
            self._normalize_llm_node(node, depth=0, used_ids=used_ids)
            for node in work.get("structure", [])
            if isinstance(node, dict)
        ]
        work["structure"] = self._promote_generic_outline_wrappers(work["structure"])
        return candidate

    def _normalize_llm_node(self, node: Dict[str, Any], depth: int, used_ids: set[str]) -> Dict[str, Any]:
        """Normalize one structural node from LLM output."""
        normalized = dict(node)
        children = normalized.pop("children", None)
        if children is not None and "content" not in normalized:
            normalized["content"] = children

        allowed_node_types = {"part", "chapter", "section", "subsection", "subsubsection", "subsubsubsection"}
        node_type = str(normalized.get("type") or "").lower()
        if node_type not in allowed_node_types:
            node_type = "chapter" if depth == 0 else "section" if depth == 1 else "subsection"
        normalized["type"] = node_type

        title = str(normalized.get("title") or normalized.get("id") or f"Section {len(used_ids) + 1}")
        normalized["title"] = title
        normalized["id"] = self._unique_node_id(str(normalized.get("id") or self._generate_id(title)), used_ids)

        content = normalized.get("content")
        if isinstance(content, list):
            normalized["content"] = [
                self._normalize_llm_node(child, depth=depth + 1, used_ids=used_ids)
                for child in content
                if isinstance(child, dict)
            ]
            if not normalized["content"]:
                normalized.pop("content", None)
                normalized.setdefault("content_file", f"content/sections/{normalized['id']}.md")
        elif content is not None:
            normalized.pop("content", None)

        if "content" not in normalized and not normalized.get("content_file") and not normalized.get("content_text"):
            normalized["content_file"] = f"content/sections/{normalized['id']}.md"
        if not normalized.get("content_text"):
            derived_content = self._content_text_from_llm_extras(normalized)
            if derived_content:
                normalized["content_text"] = derived_content
                normalized.setdefault("content_file", f"content/sections/{normalized['id']}.md")
        self._split_lettered_subsections(normalized, depth=depth, used_ids=used_ids)

        return normalized

    def _promote_generic_outline_wrappers(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove generic wrapper nodes such as Outline when they only contain real sections."""
        promoted: list[dict[str, Any]] = []
        for node in nodes:
            title = str(node.get("title") or "").strip().lower()
            node_id = str(node.get("id") or "").strip().lower()
            content_text = str(node.get("content_text") or "").strip()
            children = node.get("content")
            if title in {"outline", "contents", "table of contents"} and node_id in {"outline", "contents", "table_of_contents"} and isinstance(children, list) and not content_text:
                promoted.extend(children)
            else:
                promoted.append(node)
        return promoted

    def _split_lettered_subsections(self, node: Dict[str, Any], depth: int, used_ids: set[str]) -> None:
        """Turn markdown lettered items into child nodes when the model flattened them."""
        if node.get("content"):
            return
        content_text = node.get("content_text")
        if not isinstance(content_text, str) or not content_text.strip():
            return

        pattern = re.compile(
            r"^\s*(?:\*\*)?([A-Z])\.\s+([^*\n–-]+?)(?:\*\*)?\s*(?:[–-]\s*(.*))?$",
            re.MULTILINE,
        )
        matches = list(pattern.finditer(content_text))
        if len(matches) < 2:
            return

        children: list[dict[str, Any]] = []
        consumed_spans: list[tuple[int, int]] = []
        child_type = "section" if depth == 0 else "subsection" if depth == 1 else "subsubsection"
        for match in matches:
            label = match.group(1)
            title = match.group(2).strip()
            detail = (match.group(3) or "").strip()
            child_title = f"{label}. {title}"
            child_id = self._unique_node_id(self._generate_id(title), used_ids)
            child = {
                "type": child_type,
                "id": child_id,
                "title": child_title,
                "goal": "",
                "summary": detail,
                "prerequisites": [],
                "dependencies": {"structural": [], "narrative": ""},
                "key_concepts": [],
                "citations": [],
                "content_file": f"content/sections/{child_id}.md",
            }
            if detail:
                child["content_text"] = detail
            children.append(child)
            consumed_spans.append(match.span())

        remainder_parts: list[str] = []
        cursor = 0
        for start, end in consumed_spans:
            remainder_parts.append(content_text[cursor:start])
            cursor = end
        remainder_parts.append(content_text[cursor:])
        remainder = "\n".join(part.strip() for part in remainder_parts if part.strip()).strip()
        node["content"] = children
        if remainder:
            node["content_text"] = remainder
        else:
            node.pop("content_text", None)

    def _content_text_from_llm_extras(self, node: Dict[str, Any]) -> str:
        """Convert common non-schema LLM keys into markdown section content."""
        blocks: list[str] = []
        bullets = node.pop("bullets", None)
        if isinstance(bullets, list):
            lines = [f"- {item}" for item in bullets if item is not None]
            if lines:
                blocks.append("\n".join(lines))

        table = node.pop("table", None)
        if isinstance(table, dict):
            headers = table.get("headers")
            rows = table.get("rows")
            if isinstance(headers, list) and isinstance(rows, list) and headers:
                blocks.append(self._markdown_table(headers, rows))
        elif isinstance(table, str) and table.strip():
            blocks.append(table.strip())

        paragraphs = node.pop("paragraphs", None)
        if isinstance(paragraphs, list):
            text = "\n\n".join(str(item).strip() for item in paragraphs if str(item).strip())
            if text:
                blocks.insert(0, text)

        body = node.pop("body", None)
        if isinstance(body, str) and body.strip():
            blocks.insert(0, body.strip())

        return "\n\n".join(blocks).strip()

    def _markdown_table(self, headers: list[Any], rows: list[Any]) -> str:
        """Render simple tabular LLM output as a markdown table."""
        header_cells = [str(cell).strip() for cell in headers]
        lines = [
            "| " + " | ".join(header_cells) + " |",
            "| " + " | ".join("---" for _ in header_cells) + " |",
        ]
        for row in rows:
            if not isinstance(row, list):
                continue
            cells = [str(cell).strip() for cell in row]
            if len(cells) < len(header_cells):
                cells.extend("" for _ in range(len(header_cells) - len(cells)))
            lines.append("| " + " | ".join(cells[:len(header_cells)]) + " |")
        return "\n".join(lines)

    def _extract_structured_response(self, response_text: str) -> Dict[str, Any]:
        """Extract JSON or YAML from a model response."""
        cleaned = response_text.strip()
        fenced = re.search(r"```(?:json|yaml|yml)?\s*(.*?)```", cleaned, re.DOTALL)
        if fenced:
            cleaned = fenced.group(1).strip()

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if cleaned.startswith("{") and json_match:
            cleaned = json_match.group(0)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = yaml.safe_load(cleaned)

        if not isinstance(parsed, dict):
            raise ValueError("LLM response did not contain a structured object")
        return parsed
    
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
        current_node = None
        body_lines: list[str] = []

        def flush_body() -> None:
            nonlocal body_lines
            if current_node and body_lines:
                body = "\n".join(body_lines).strip()
                if body:
                    current_node["content_text"] = body
                    current_node["summary"] = current_node.get("summary") or self._summary_from_text(body)
            body_lines = []
        
        for line in lines:
            # Parse markdown headers
            header_match = re.match(r'^(#{1,6})\s+(.+)', line)
            if header_match:
                flush_body()
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
                current_node = node
            elif current_node is not None:
                body_lines.append(line)

        flush_body()
        
        return parsed
    
    def _parse_yaml_v1(self, content: str) -> Dict[str, Any]:
        """Parse original YAML v1.0 format."""
        data = yaml.safe_load(content)
        outline = data.get('outline', {})
        
        parsed = {
            'title': outline.get('title', 'Untitled Work'),
            'summary': outline.get('summary', ''),
            'intent': outline.get('intent', {}),
            'metadata': outline.get('metadata', {}),
            'diagrams': outline.get('diagrams', []),
            'artwork': outline.get('artwork', []),
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
            'authors': [self._create_author(parsed.get('metadata', {}))],
            'metadata': self._create_metadata(parsed.get('metadata', {})),
            'front_matter': self._map_front_matter(parsed.get('front_matter', {})),
            'structure': self._map_structure(parsed['structure'], used_ids=set()),
            'citations': {'entries': []},
            'diagrams': self._map_diagrams(parsed.get('diagrams', [])),
            'media': self._map_artwork(parsed.get('artwork', [])),
            'back_matter': self._map_back_matter(parsed.get('back_matter', {})),
            'compilation': self._create_default_compilation()
        }
        
        if interactive:
            work = self._interactive_fill(work)
        
        return {'work': work}

    def validate_canonical(self, outline: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate a canonical outline against the registered schema."""
        return SchemaValidator().validate(outline)
    
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

    def _create_author(self, source_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """Create author entry from source metadata when available."""
        source_metadata = source_metadata or {}
        author = self._create_default_author()
        if source_metadata.get('author'):
            author['name'] = source_metadata['author']
        return author
    
    def _create_metadata(self, source_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create comprehensive metadata with all 8 categories."""
        source_metadata = source_metadata or {}
        today = datetime.now().strftime('%Y-%m-%d')
        current_year = str(datetime.now().year)
        created = str(source_metadata.get('created', today))
        updated = str(source_metadata.get('updated', today))
        version = str(source_metadata.get('version', '0.1.0'))
        maintainer = source_metadata.get('maintained_by', 'author')
        author = source_metadata.get('author', 'TO BE SPECIFIED')
        
        return {
            'version': version,
            'created': created,
            'updated': updated,
            'maintained_by': maintainer,
            'language': 'en',
            'license': source_metadata.get('license', 'CC-BY-4.0'),
            'status': 'draft',
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
                    'maintainer': maintainer,
                    'created_by': ''
                },
                'versioning': {
                    'version': version,
                    'changelog': [
                        {
                            'version': version,
                            'date': updated,
                            'changes': 'Migrated to canonical work outline format'
                        }
                    ],
                    'release_notes': ''
                },
                'timestamps': {
                    'created': created,
                    'modified': updated,
                    'published': '',
                    'archived': ''
                },
                'rights_and_access': {
                    'license': 'CC-BY-4.0',
                    'copyright_holder': author,
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
                'schema_version': self.schema_version,
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
            'title_page': {'enabled': False},
            'copyright_page': {
                'enabled': True,
                'year': str(datetime.now().year),
                'holder': ''
            },
            'dedication': {'enabled': False, 'text': ''},
            'epigraph': {'enabled': False, 'quote': '', 'attribution': ''},
            'table_of_contents': {'enabled': False, 'depth': 3},
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
    
    def _map_structure(self, structure: List[Dict], used_ids: set[str] | None = None) -> List[Dict]:
        """Recursively map structure to v2.1 format."""
        used_ids = used_ids if used_ids is not None else set()
        result = []
        
        for idx, item in enumerate(structure, 1):
            fallback_id = f"{item.get('type', 'section')}_{idx:02d}"
            base_id = item.get('id') or self._generate_id(item.get('title', fallback_id)) or fallback_id
            node_id = self._unique_node_id(base_id, used_ids)
            node = {
                'type': item.get('type', 'chapter'),
                'id': node_id,
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
                node['content'] = self._map_structure(item['content'], used_ids=used_ids)
            else:
                # Leaf node - needs content_file or content_text
                node['content_file'] = f"content/sections/{node['id']}.md"
                if item.get('content_text'):
                    node['content_text'] = item['content_text']
            
            result.append(node)
        
        return result

    def _summary_from_text(self, text: str) -> str:
        """Create a compact node summary from imported body text."""
        normalized = " ".join(line.strip() for line in text.splitlines() if line.strip())
        return normalized[:240]

    def _unique_node_id(self, base_id: str, used_ids: set[str]) -> str:
        """Return a schema-safe node id unique within one canonical work."""
        normalized = re.sub(r'[^a-z0-9_]+', '_', base_id.lower()).strip('_') or "section"
        candidate = normalized
        counter = 2
        while candidate in used_ids:
            candidate = f"{normalized}_{counter}"
            counter += 1
        used_ids.add(candidate)
        return candidate

    def _map_diagrams(self, diagrams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map legacy diagram metadata into canonical diagram entries."""
        mapped = []
        for diagram in diagrams:
            mapped.append({
                'id': diagram.get('id') or self._generate_id(diagram.get('title', 'diagram')),
                'title': diagram.get('title', 'Untitled Diagram'),
                'caption': diagram.get('description', ''),
                'purpose': diagram.get('description', ''),
                'definition': {
                    'type': 'text',
                    'code': diagram.get('computational_definition', '')
                }
            })
        return mapped

    def _map_artwork(self, artwork: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Map legacy artwork entries into canonical media items."""
        mapped = []
        for item in artwork:
            mapped.append({
                'id': item.get('id') or self._generate_id(item.get('title', 'artwork')),
                'type': 'image',
                'title': item.get('title', 'Untitled Artwork'),
                'caption': item.get('description', ''),
                'file': item.get('file', ''),
                'purpose': item.get('description', '')
            })
        return mapped

    def build_report(
        self,
        source_format: str,
        source: Dict[str, Any],
        canonical: Dict[str, Any],
        llm_used: bool = False,
        validation_errors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build a human-readable migration report payload."""
        source_structure = source.get('structure', [])
        canonical_structure = canonical['work'].get('structure', [])
        leaf_count = self._count_leaves(canonical_structure)
        return {
            'timestamp': datetime.now().isoformat(),
            'source_format': source_format,
            'canonical_schema': f'work_outline_schema_{self.schema_version}',
            'work_id': canonical['work']['id'],
            'title': canonical['work']['title'],
            'top_level_elements': len(canonical_structure),
            'leaf_sections': leaf_count,
            'diagrams': len(canonical['work'].get('diagrams', [])),
            'media': len(canonical['work'].get('media', [])),
            'llm_used': llm_used,
            'llm_error': self.last_llm_error,
            'validation_errors': validation_errors or [],
            'notes': [
                'Converted to canonical work/structure/content outline.',
                f'Reusable section payloads are referenced under content/sections/ for {leaf_count} leaf sections.',
                f'Original top-level elements parsed: {len(source_structure)}.'
            ]
        }

    def format_report(self, report: Dict[str, Any]) -> str:
        """Render a migration report for humans."""
        lines = [
            'Outline Migration Report',
            '=' * 24,
            f"Timestamp: {report['timestamp']}",
            f"Source format: {report['source_format']}",
            f"Canonical schema: {report['canonical_schema']}",
            f"Work: {report['title']} ({report['work_id']})",
            f"Top-level elements: {report['top_level_elements']}",
            f"Leaf sections: {report['leaf_sections']}",
            f"Diagrams: {report['diagrams']}",
            f"Media: {report['media']}",
            f"LLM used: {report['llm_used']}",
            '',
            'Notes:',
        ]
        lines.extend(f"- {note}" for note in report['notes'])
        if report.get('llm_error'):
            lines.extend(['', 'LLM fallback:', f"- {report['llm_error']}"])
        if report.get('validation_errors'):
            lines.extend(['', 'Validation errors:'])
            lines.extend(f"- {error}" for error in report['validation_errors'])
        return '\n'.join(lines) + '\n'

    def write_report(self, report_path: str | Path, report: Optional[Dict[str, Any]] = None) -> None:
        """Write the latest migration report."""
        report = report or self.last_report
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(self.format_report(report))

    def _count_leaves(self, nodes: List[Dict[str, Any]]) -> int:
        count = 0
        for node in nodes:
            children = node.get('content') or []
            if children:
                count += self._count_leaves(children)
            else:
                count += 1
        return count
    
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
                format_type: str = None, interactive: bool = True,
                report_path: str = None, quiet: bool = False,
                use_llm: str | bool = "auto") -> str:
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
        if not quiet:
            print(f"🔍 Detecting format...")
        if format_type is None:
            format_type = self.detect_format(content)
        if not quiet:
            print(f"✓ Detected format: {format_type}")

        llm_requested = use_llm is True or use_llm == "always"
        llm_disabled = use_llm is False or use_llm == "never"
        llm_auto = use_llm == "auto" and format_type == "unknown"
        parsed = None
        llm_used = False
        validation_errors: List[str] = []
        llm_failure: Optional[str] = None

        if llm_requested or llm_auto:
            if not quiet:
                print("🤖 Requesting LLM-assisted conversion...")
            try:
                schema_v2 = self.convert_with_llm(content, format_type)
                llm_used = True
                parsed = {'title': schema_v2['work']['title'], 'structure': schema_v2['work'].get('structure', [])}
                if not quiet:
                    print("✓ LLM conversion produced valid canonical outline")
            except Exception as e:
                llm_failure = str(e)
                self.last_llm_error = llm_failure
                if llm_requested:
                    raise
                if not quiet:
                    print(f"⚠️  LLM conversion unavailable; using deterministic parser: {e}")

        if not llm_used:
            if not quiet:
                print(f"📖 Parsing outline...")
            try:
                parsed = self.parse_outline(content, format_type)
            except Exception as e:
                if use_llm == "auto" and not llm_disabled:
                    if not quiet:
                        print("🤖 Deterministic parsing failed; trying LLM conversion...")
                    try:
                        schema_v2 = self.convert_with_llm(content, format_type)
                        llm_used = True
                        parsed = {'title': schema_v2['work']['title'], 'structure': schema_v2['work'].get('structure', [])}
                    except Exception as llm_error:
                        llm_failure = str(llm_error)
                        self.last_llm_error = llm_failure
                        raise ValueError(
                            f"Deterministic parsing failed: {e}. LLM fallback failed: {llm_failure}"
                        ) from llm_error
                else:
                    raise
            if not quiet:
                print(f"✓ Parsed {len(parsed['structure'])} top-level elements")

            if not llm_used:
                if not quiet:
                    print(f"🗺️  Mapping to schema v2.1...")
                schema_v2 = self.map_to_schema_v2(parsed, interactive)
                valid, validation_errors = self.validate_canonical(schema_v2)
                if not valid and use_llm == "auto" and not llm_disabled:
                    if not quiet:
                        print("🤖 Deterministic conversion did not validate; trying LLM repair...")
                    try:
                        schema_v2 = self.convert_with_llm(content, format_type)
                        llm_used = True
                        validation_errors = []
                    except Exception as e:
                        llm_failure = str(e)
                        self.last_llm_error = llm_failure
                if not quiet:
                    print(f"✓ Mapped to standardized format with comprehensive metadata")

        valid, validation_errors = self.validate_canonical(schema_v2)
        if not valid:
            details = f"Converted outline is not schema-valid: {'; '.join(validation_errors)}"
            if use_llm == "auto" and llm_failure:
                details = f"{details}. LLM fallback failed: {llm_failure}"
            raise ValueError(details)

        self.last_report = self.build_report(
            format_type,
            parsed or {'title': schema_v2['work']['title'], 'structure': []},
            schema_v2,
            llm_used=llm_used,
            validation_errors=validation_errors,
        )
        
        # Convert to YAML
        yaml_output = yaml.dump(schema_v2, sort_keys=False, 
                                allow_unicode=True, default_flow_style=False)
        
        # Save if output path specified
        if output_path:
            with open(output_path, 'w') as f:
                f.write(yaml_output)
            if not quiet:
                print(f"💾 Saved to: {output_path}")
        if report_path:
            self.write_report(report_path)
            if not quiet:
                print(f"🧾 Report saved to: {report_path}")
        
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
