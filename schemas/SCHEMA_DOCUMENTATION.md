# Work Outline Schema v2.0 - Documentation

## Philosophy and Intent

This schema is designed with several core principles:

1. **Single Source of Truth**: One YAML file completely defines a written work
2. **Intent-Driven Structure**: Every element captures *why* it exists, not just *what* it contains
3. **Recursive Depth**: Unlimited nesting of sections (Parts → Chapters → Sections → Subsections...)
4. **Dependency Awareness**: Both machine-readable and human-expressible relationships between sections
5. **Professional Publishing Standards**: Aligned with how books are actually structured in academic and trade publishing

## Key Design Decisions

### 1. Introduction as First Chapter

Following your guidance, the Introduction is treated as the first chapter of the main matter, not as a separate front matter section. This reflects modern publishing practice where the Introduction sets up the argument and is numbered as Chapter 1 (or Chapter 0 in some technical works).

### 2. Recursive Section Hierarchy

The schema supports infinite recursion through the `content` field:

```yaml
structure:
  - type: "part"
    content:
      - type: "chapter"
        content:
          - type: "section"
            content:
              - type: "subsection"
                content:
                  - type: "subsubsection"
                    content:
                      - type: "subsubsubsection"
                        # ... continues as needed
```

Each level can contain:
- Metadata (id, number, title)
- Intent fields (goal, summary, prerequisites, dependencies, key_concepts)
- Either more nested content OR terminal content (content_file or content_text)

### 3. Dual Dependency System

Dependencies are captured in two complementary ways:

**Structural (Machine-Readable)**:
```yaml
dependencies:
  structural:
    - section_id: "ch00_sec01"
      dependency_type: "builds_on"
      required: true
```

This enables:
- Validation of the outline structure
- Detection of circular dependencies
- Automatic ordering suggestions
- Visualization of the concept graph

**Narrative (Human-Readable)**:
```yaml
dependencies:
  narrative: |
    This chapter builds directly on the notation established in the
    preface and extends the ideas first introduced in Part I.
```

This provides:
- Natural language context for readers
- Flexibility for expressing complex relationships
- Ability to include in the compiled text if desired

### 4. Citation Graph

The citation system is designed to enable Web of Science-style relationship tracking:

```yaml
citations:
  entries:
    - id: "cite_001"
      # ... bibliographic info ...
      relationships:
        cites: ["cite_042", "cite_103"]      # Forward citations
        cited_by: ["cite_201"]                # Back citations
        related_to: ["cite_055"]              # Thematic connections
      used_in:
        - section_id: "ch01_sec02"
          context: "theoretical_foundation"
```

This creates a rich network where:
- Citations know which sections use them and why
- Citations know their relationships to other works
- The system can trace influence paths
- Projected links can be generated to show citation context

## Professional Publishing Alignment

### Front Matter Order (Standard)

Professional books typically follow this front matter order:

1. Half-title page (optional)
2. Title page
3. Copyright page
4. Dedication (optional)
5. Epigraph (optional)
6. Table of Contents
7. List of Figures (if applicable)
8. List of Tables (if applicable)
9. Foreword (by someone else)
10. Preface (by author, about the book)
11. Acknowledgments
12. Introduction (now treated as Chapter 1)

The schema supports all of these with `enabled` flags and `order` parameters for custom sections.

### Main Matter Structure

**Academic/Technical Books**:
- Often use Parts to group related chapters
- Chapters are the primary unit
- Sections provide structure within chapters
- Deep nesting (subsections, subsubsections) is common in technical works

**Trade Nonfiction**:
- May skip Parts entirely
- Chapters as primary divisions
- Fewer levels of subsection nesting

**Papers/Articles**:
- Abstract → Introduction → Body Sections → Conclusion → References
- May use numbered sections without chapters

The schema accommodates all of these patterns.

### Back Matter Order (Standard)

1. Appendices
2. Glossary
3. Notes (endnotes if not using footnotes)
4. Bibliography/References
5. Index
6. About the Author

## Usage Patterns

### Minimal Example (Essay/Short Paper)

```yaml
work:
  id: "my_essay"
  type: "essay"
  title: "Thoughts on Recursion"
  
  structure:
    - type: "chapter"
      id: "ch01"
      title: "Introduction"
      content_text: |
        The actual essay content...
```

### Medium Complexity (Book with Chapters)

```yaml
work:
  id: "my_book"
  type: "book"
  title: "Understanding X"
  
  front_matter:
    title_page:
      enabled: true
    table_of_contents:
      enabled: true
  
  structure:
    - type: "chapter"
      id: "ch01"
      title: "Introduction"
      goal: "Introduce the problem"
      content:
        - type: "section"
          id: "ch01_sec01"
          title: "The Problem"
          content_file: "sections/ch01_sec01.md"
```

### High Complexity (Academic Book with Parts)

```yaml
work:
  id: "codynamic_theory"
  type: "book"
  title: "Codynamic Theory: Structure Is All You Need"
  
  structure:
    - type: "part"
      id: "part_01"
      number: "I"
      title: "Foundations"
      content:
        - type: "chapter"
          id: "ch01"
          title: "Introduction"
          dependencies:
            structural:
              - section_id: "preface"
                dependency_type: "builds_on"
          key_concepts:
            - id: "codynamic_loop"
              term: "Codynamic Loop"
              definition: "..."
          content:
            - type: "section"
              # ... nested structure
```

## Field Reference

### Required Fields

At minimum, every work needs:
- `id`: Unique identifier
- `type`: Work type
- `title`: Title
- `structure`: At least one structural element

### Recommended Fields

For a complete, professional work:
- `authors`: Author information
- `metadata.version`: Version tracking
- `intent`: Communication of purpose
- `front_matter.table_of_contents`: Navigation
- `citations`: References (for non-fiction)

### Optional But Powerful

- `prerequisites`: Learning scaffolding
- `dependencies.structural`: Structural validation
- `key_concepts`: Automated glossary generation
- `diagrams`: Computational figures
- `compilation.validation`: Quality checks

## Dependency Types

The schema defines several dependency relationship types:

- **builds_on**: This section extends or develops ideas from another
- **references**: This section mentions or cites another
- **extends**: This section takes concepts further
- **contradicts**: This section challenges ideas from another
- **contextualizes**: This section provides background for another
- **is_part_of**: Hierarchical containment
- **prerequisite_for**: This must be read before another
- **parallels**: This section covers related ideas independently

## Citation Context Types

When tracking where citations are used:

- **theoretical_foundation**: Establishing core concepts
- **empirical_validation**: Supporting claims with data
- **methodological**: Describing approaches or techniques
- **comparative**: Contrasting with other work
- **historical**: Providing background or timeline
- **critical**: Engaging with counterarguments

## Key Concepts Tracking

Key concepts serve multiple purposes:

1. **Glossary Generation**: Auto-populate glossary entries
2. **Index Creation**: Track where terms are defined/used
3. **Dependency Analysis**: Understand which sections introduce prerequisites
4. **Reader Navigation**: Help readers find definitions

Example:
```yaml
key_concepts:
  - id: "codynamic_loop"
    term: "Codynamic Loop"
    definition: "A recursive structure where system state feeds back into structure"
    introduced_in: "ch01_sec02"
    related_terms:
      - "structural_recursion"
      - "feedback_mechanism"
```

## Validation Capabilities

The schema enables several automated checks:

### Dependency Validation
- Verify all section_id references exist
- Detect circular dependencies
- Ensure required dependencies are satisfied
- Suggest optimal reading order

### Citation Validation
- Verify all ref_id citations exist
- Check for unused citation entries
- Validate bibliographic format
- Detect missing DOIs or URLs

### Cross-Reference Validation
- Check all section references
- Verify figure/table references
- Ensure media files exist
- Validate external content files

### Structural Validation
- Detect orphaned sections
- Check numbering consistency
- Verify hierarchy depth
- Ensure all leaf nodes have content

## Content File Organization

The schema supports flexible content storage:

**Inline Content** (for small sections):
```yaml
content_text: |
  The prose goes here directly in the YAML.
```

**External Files** (recommended for longer content):
```yaml
content_file: "sections/ch01_sec02.md"
```

Recommended directory structure:
```
book_project/
├── outline.yaml
├── sections/
│   ├── ch01_sec01.md
│   ├── ch01_sec02.md
│   └── ...
├── diagrams/
│   ├── diagram_001.py
│   └── diagram_001.png
├── media/
│   └── cover_art.png
├── citations/
│   └── references.yaml
└── front_matter/
    ├── preface.md
    └── acknowledgments.md
```

## Future Extensibility

The schema is designed to grow:

1. **Custom Fields**: Add project-specific metadata
2. **Plugin System**: Define custom section types
3. **Alternative Formats**: Add new output formats
4. **Collaboration**: Track authorship per section
5. **Review System**: Add review/approval workflows
6. **Translation**: Add multi-language support

## Comparison to Existing Standards

### Differs from Markdown/LaTeX
- **Markdown**: Great for simple documents, lacks semantic structure
- **LaTeX**: Excellent typesetting, but conflates content and presentation
- **This Schema**: Separates intent (YAML) from content (MD/LaTeX) from presentation (themes)

### Differs from DocBook/DITA
- **DocBook/DITA**: XML-based, enterprise-focused, complex
- **This Schema**: YAML-based, author-focused, intent-driven

### Differs from Pandoc Metadata
- **Pandoc**: Simple metadata headers, limited structure
- **This Schema**: Complete work definition with dependencies and relationships

## Migration Path

To migrate existing outlines:

1. **From Google Docs**: Extract headings → map to chapter/section structure
2. **From Markdown**: Parse headers → create hierarchy
3. **From LaTeX**: Extract `\chapter`, `\section` commands → convert to YAML
4. **From Existing YAML**: Map old fields to new schema

Would you like me to create a migration tool for your existing outlines?
