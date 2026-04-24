# Outline Converter Agent

Intelligent converter that transforms various outline formats into the standardized Work Outline Schema v2.0.

## Overview

The Outline Converter Agent can parse outlines in multiple formats and map them to the comprehensive v2.0 schema, preserving structure, intent, and metadata while adding standardized fields for dependencies, citations, and compilation settings.

## Supported Input Formats

### 1. Nested Nodes Format
Used for complex technical books with special annotations:

```
Title of the Work

### Summary of Understanding
High-level description...

<node-singleton> Title Page
<node-with-children> Front Matter
  Preface
    Motivation and scope
  Notation & Conventions
<node-with-children> Chapters
  Part I: Foundations
    1. Chapter Title
      Section content
    2. Next Chapter
```

### 2. Numbered Hierarchy Format
Standard numbered outline style:

```
Title of the Work

Front matter
* Dedication: Text here
* Preface: Description

Chapters
1. Chapter Title
   1.1 Section Title
      1.1.1 Subsection Title
      1.1.2 Another Subsection
   1.2 Another Section
2. Next Chapter
   2.1 Section
```

### 3. Markdown Headers
Clean markdown-style outlines:

```markdown
# Title of the Work

## Chapter 1: Introduction
### Section 1.1: Background
### Section 1.2: Overview

## Chapter 2: Main Content
### Section 2.1: First Topic
```

### 4. YAML v1.0
Original schema format (auto-detected and upgraded):

```yaml
outline:
  title: "Book Title"
  chapters:
    - id: "ch01"
      title: "Chapter Title"
      sections:
        - id: "ch01_sec01"
          title: "Section Title"
```

## Features

✅ **Automatic Format Detection**: Identifies input format automatically  
✅ **Structure Preservation**: Maintains hierarchy and relationships  
✅ **Intelligent Defaults**: Fills in required fields with sensible defaults  
✅ **ID Generation**: Creates valid section IDs from titles  
✅ **Recursive Nesting**: Handles unlimited depth (parts → chapters → sections → ...)  
✅ **Front/Back Matter Mapping**: Detects and categorizes prefaces, appendices, etc.  
✅ **Validation Ready**: Outputs conform to v2.0 JSON Schema  

## Installation

```bash
# Install dependencies
pip3 install pyyaml --break-system-packages

# Or if using virtual environment
python3 -m venv venv
source venv/bin/activate
pip install pyyaml
```

## Usage

### Command Line

```bash
# Convert an outline file
python3 converter.py input_outline.txt output_outline.yaml

# Convert with format override
python3 converter.py input.txt output.yaml --format numbered_hierarchy

# Interactive mode (prompts for missing info)
python3 converter.py input.txt output.yaml --interactive
```

### Python API

```python
from converter import OutlineConverter

# Initialize converter
converter = OutlineConverter()

# Convert from text
outline_text = """
Your outline content here...
"""

result = converter.convert(
    outline_text,
    output_path='output.yaml',
    format_type=None,  # Auto-detect
    interactive=True    # Prompt for missing fields
)

print(result)
```

### Programmatic Usage

```python
# For integration into other tools
from converter import OutlineConverter

converter = OutlineConverter()

# Step 1: Detect format
format_type = converter.detect_format(content)
print(f"Detected format: {format_type}")

# Step 2: Parse outline
parsed = converter.parse_outline(content, format_type)
print(f"Parsed {len(parsed['structure'])} elements")

# Step 3: Map to v2.0 schema
schema_v2 = converter.map_to_schema_v2(parsed, interactive=False)

# Step 4: Export as YAML
import yaml
yaml_output = yaml.dump(schema_v2, sort_keys=False)
```

## Output Structure

The converter generates a complete v2.0 schema outline with:

```yaml
work:
  id: "generated_id"
  type: "book"
  title: "Extracted Title"
  summary: "Extracted summary"
  
  intent:
    audience: "TO BE SPECIFIED"  # User should fill
    writing_style: "TO BE SPECIFIED"
    # ... other intent fields
  
  authors:
    - name: "TO BE SPECIFIED"
      role: "author"
  
  metadata:
    version: "0.1.0"
    created: "2025-11-21"
    updated: "2025-11-21"
    status: "draft"
  
  front_matter:
    title_page:
      enabled: true
    table_of_contents:
      enabled: true
      depth: 3
    # ... detected front matter
  
  structure:
    - type: "chapter"
      id: "chapter_01"
      title: "Chapter Title"
      goal: ""
      summary: ""
      prerequisites: []
      dependencies:
        structural: []
        narrative: ""
      key_concepts: []
      citations: []
      content:
        - type: "section"
          # ... nested structure
  
  citations:
    entries: []
  
  diagrams: []
  
  media: []
  
  back_matter:
    bibliography:
      enabled: true
      style: "APA"
    # ... detected back matter
  
  compilation:
    output_formats: ["pdf"]
    validation:
      check_dependencies: true
      check_citations: true
```

## Field Mapping

### Automatic Extraction

The converter automatically extracts:

- ✅ Title (from first line or header)
- ✅ Summary (from "Summary" sections)
- ✅ Structure hierarchy (chapters, sections, subsections)
- ✅ Front matter elements (preface, dedication, TOC, etc.)
- ✅ Back matter elements (appendices, bibliography, index)

### Fields Requiring User Input

Some fields are marked "TO BE SPECIFIED" and should be filled manually:

- Author name and details
- Intent fields (audience, writing_style, reader_takeaway, etc.)
- Copyright holder
- Prerequisites for each chapter
- Goals and summaries for sections
- Citation details
- Dependencies between sections

## Testing

Run the test suite:

```bash
cd scripts/outline_converter
python3 test_converter.py
```

Tests include:
- Format detection accuracy
- Parsing of nested nodes format
- Parsing of numbered hierarchy format
- Conversion to v2.0 schema
- Output validation

## LLM Enhancement (Optional)

For intelligent extraction of semantic information, use the LLM enhancer:

```python
from llm_enhancer import LLMEnhancedConverter
from converter import OutlineConverter

# Initialize with API provider
enhancer = LLMEnhancedConverter(api_provider=your_api)

# Use with base converter
converter = OutlineConverter(llm_provider=enhancer)
result = converter.convert(outline_text)
```

The LLM enhancer can:
- Extract intent information from context
- Infer dependencies between sections
- Identify key concepts automatically
- Suggest section goals and summaries

## Integration with Book Machine

The converter integrates seamlessly with the Codynamic Book Machine:

1. **Convert** your outline to v2.0 format
2. **Fill in** the "TO BE SPECIFIED" fields
3. **Validate** using the book machine's validator
4. **Generate** the book using existing agents

```bash
# Convert outline
python3 converter.py my_outline.txt data/book_data/my_book/outline.yaml

# Edit and fill in missing fields
# (editor of your choice)

# Validate
python3 scripts/validate_outline.py data/book_data/my_book/outline.yaml

# Generate book
python3 scripts/launch_agents.py --book my_book
```

## Examples

See `test_converter.py` for complete examples of:
- Converting complex technical outlines
- Converting simple numbered outlines
- Handling front and back matter
- Recursive section nesting

## Limitations

Current limitations:
- Intent fields must be filled manually (or use LLM enhancer)
- Dependencies are not automatically inferred (structural hierarchy only)
- Citations must be added manually or extracted from references
- Key concepts are title-based (improve with LLM enhancer)

## Roadmap

Future enhancements:
- [ ] LLM-powered intent extraction
- [ ] Automatic dependency inference
- [ ] Citation extraction from reference lists
- [ ] Interactive TUI for field completion
- [ ] Batch conversion of multiple outlines
- [ ] Google Docs import
- [ ] Notion import
- [ ] LaTeX outline import

## Contributing

To add support for a new format:

1. Add detection logic to `detect_format()`
2. Implement `_parse_<format_name>()` method
3. Add test cases
4. Update documentation

## License

Part of the Codynamic Book Machine project.

## See Also

- [Work Outline Schema v2.0](../schemas/work_outline_schema_v2.yaml)
- [Schema Documentation](../schemas/SCHEMA_DOCUMENTATION.md)
- [Example Outlines](../schemas/example_paper.yaml)
- [Template](../schemas/template_blank.yaml)
