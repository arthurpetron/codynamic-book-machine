# Work Outline Schema v2.1

**Latest Update**: Comprehensive Metadata Integration (November 2024)

This directory contains the complete schema definition for structured authoring in the Codynamic Book Machine.

## What's New in v2.1

**Major Enhancement**: Integrated comprehensive metadata from `template_outline_metadata.yaml` into the core schema. The `metadata` section now includes **8 rich categories** that capture not just what the work is, but its **intellectual intent, scholarly context, and computational provenance**.

See `CHANGELOG.md` for complete details.

### The 8 Metadata Categories

1. **Descriptive**: What the work is about (keywords, subject, genre)
2. **Administrative**: Provenance, versioning, rights management
3. **Structural**: Physical characteristics (page count, citation map)
4. **Technical**: File format, encoding, rendering specs
5. **Semantic**: Thesis, research questions, epistemological stance
6. **Relational**: Scholarly network (cites, cited_by, related works)
7. **Contextual**: Historical, cultural, institutional context
8. **Computational**: Validation status, execution logs, build metadata

This enhancement embodies the **intuitionist principle** that structure should express **intent** - not just organizing content, but capturing *why* it exists and *how* it fits into the broader conversation.

## Files in This Directory

### Core Schema
- **`work_outline_schema_v2.yaml`** - The human-readable schema definition with extensive comments
- **`work_outline_schema_v2.json`** - JSON Schema for formal validation
- **`SCHEMA_DOCUMENTATION.md`** - Comprehensive documentation of design principles and usage

### Examples and Templates
- **`template_blank.yaml`** - Empty template to start new works (copy this!)
- **`example_paper.yaml`** - Complete example of a short academic paper
- **`../outline_template.yaml`** - Original template (v1.0, kept for reference)

## Quick Start

### Creating a New Work

1. Copy the blank template:
   ```bash
   cp template_blank.yaml ../book_data/my_new_book/outline.yaml
   ```

2. Fill in the basic information:
   - `id`: Unique identifier
   - `type`: book, paper, monograph, etc.
   - `title`: Your work's title
   - `summary`: What this work accomplishes
   - `intent`: Audience, style, takeaway

3. Define your structure:
   - Start with chapters for papers
   - Use parts → chapters for books
   - Nest sections as deeply as needed

4. Add dependencies:
   - Use `structural` for machine-readable dependencies
   - Use `narrative` for human-readable explanations

### Example Structure Patterns

**Simple Paper**:
```yaml
structure:
  - type: chapter
    id: ch01
    title: "Introduction"
    content:
      - type: section
        id: ch01_sec01
        title: "Background"
        content_file: "sections/ch01_sec01.md"
```

**Book with Parts**:
```yaml
structure:
  - type: part
    id: part_01
    title: "Foundations"
    content:
      - type: chapter
        id: ch01
        title: "Introduction"
        content:
          - type: section
            # ...
```

**Deep Nesting**:
```yaml
structure:
  - type: chapter
    content:
      - type: section
        content:
          - type: subsection
            content:
              - type: subsubsection
                content_file: "sections/deep_content.md"
```

## Key Features

### 1. Intent-Driven Structure
Every section can capture:
- `goal`: What should the reader gain?
- `summary`: What does this cover?
- `prerequisites`: What should they know first?
- `key_concepts`: What terms are introduced?

### 2. Dependency Tracking
Define relationships between sections:
```yaml
dependencies:
  structural:
    - section_id: "ch01_sec01"
      dependency_type: "builds_on"
      required: true
  narrative: |
    This extends the ideas from Section 1.1
```

### 3. Citation Management
Track citations with Web-of-Science-style relationships:
```yaml
citations:
  entries:
    - id: cite_001
      # ... bibliographic info ...
      relationships:
        cites: ["cite_002"]
        cited_by: ["cite_005"]
      used_in:
        - section_id: "ch01_sec02"
          context: "theoretical_foundation"
```

### 4. Validation
Enable automatic checks:
```yaml
compilation:
  validation:
    check_dependencies: true
    check_citations: true
    check_cross_refs: true
    orphan_detection: true
```

## Professional Publishing Standards

The schema aligns with standard publishing structure:

### Front Matter Order
1. Title page
2. Copyright page
3. Dedication
4. Epigraph
5. Table of Contents
6. List of Figures/Tables
7. Foreword
8. Preface
9. Acknowledgments

### Main Matter
- Parts (optional grouping)
- Chapters (primary divisions)
- Sections (chapter subdivisions)
- Subsections (and deeper...)

### Back Matter
1. Appendices
2. Glossary
3. Bibliography
4. Index
5. About the Author

## Validation

Use the JSON Schema for validation:

```python
import yaml
import jsonschema

# Load the schema
with open('work_outline_schema_v2.json') as f:
    schema = json.load(f)

# Load your outline
with open('my_outline.yaml') as f:
    outline = yaml.safe_load(f)

# Validate
jsonschema.validate(outline, schema)
```

Or use the book machine's built-in validation when you compile.

## Migration from v1.0

Key differences from the original template:

1. **More structured intent fields**: Added `epistemology`, expanded `intent` section
2. **Recursive structure**: Unlimited nesting depth via `content` arrays
3. **Dependency system**: Both structural (machine-readable) and narrative (human-readable)
4. **Citation relationships**: Web-of-Science-style connection tracking
5. **Front/back matter**: Comprehensive configuration options
6. **Validation rules**: Built-in checking for consistency

To migrate an old outline:
1. Map old `chapters` → new `structure` with `type: chapter`
2. Add dependency information if known
3. Expand citations to include relationship tracking
4. Add front matter configuration

## Design Principles

This schema embodies several key principles:

1. **Single Source of Truth**: One YAML file defines everything
2. **Intent Over Content**: Capture *why* before *what*
3. **Machine + Human**: Dual representation of dependencies
4. **Recursive by Design**: No arbitrary limits on nesting
5. **Professional Standards**: Aligned with actual publishing practice
6. **Validation-Friendly**: Structured for automated checks

## Next Steps

1. **Read** `SCHEMA_DOCUMENTATION.md` for full details
2. **Study** `example_paper.yaml` to see it in practice
3. **Copy** `template_blank.yaml` to start your work
4. **Validate** using the JSON schema or book machine tools

## Questions?

See the full documentation or examples for more guidance on:
- Complex dependency relationships
- Citation network tracking
- Diagram integration
- Custom compilation settings
- Migration from other formats
