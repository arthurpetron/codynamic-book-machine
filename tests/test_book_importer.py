"""Tests for importing external book artifacts."""

import yaml

from scripts.book import BookImporter, BookRepository, OutlineService


LEGACY_OUTLINE = """
outline:
  title: "Imported Book"
  summary: "An outline created elsewhere."
  intent:
    audience: "Practitioners"
    writing_style: "Direct"
    author_persona: "Guide"
    reader_takeaway: "A usable plan"
    genre: "Nonfiction"
  chapters:
    - id: "ch01"
      title: "Start"
      sections:
        - id: "ch01_sec01"
          title: "First Move"
          content_summary: "Opening section."
"""


def test_import_outline_uses_converter_and_saves_canonical_book(tmp_path):
    source = tmp_path / "legacy_outline.yaml"
    source.write_text(LEGACY_OUTLINE)

    result = BookImporter(tmp_path / "book_data").import_outline(source, use_llm="never")
    book = BookRepository(result.book_root).load_book()
    service = OutlineService(book)
    valid, errors = service.validate()

    assert valid, errors
    assert result.work_id == "imported_book"
    assert result.outline_path.exists()
    assert result.report_path.exists()
    assert book["work"]["title"] == "Imported Book"
    assert service.get_node("ch01_sec01")["content_file"] == "content/sections/ch01_sec01.md"


def test_import_outline_accepts_canonical_outline_without_reconversion(tmp_path):
    source = tmp_path / "canonical_outline.yaml"
    source.write_text(yaml.safe_dump({
        "work": {
            "id": "canonical_direct",
            "type": "book",
            "title": "Canonical Direct",
            "summary": "Already canonical.",
            "metadata": {"version": "0.1.0", "updated": "2026-06-15"},
            "structure": [
                {
                    "id": "ch01",
                    "type": "chapter",
                    "title": "Opening",
                    "summary": "Open the book.",
                    "goal": "Open the book.",
                    "content": [
                        {
                            "id": "intro",
                            "type": "section",
                            "title": "Introduction",
                            "summary": "Introduce the direct import.",
                            "goal": "Introduce the direct import.",
                            "content_file": "content/sections/intro.md",
                        }
                    ],
                }
            ],
        }
    }, sort_keys=False))

    result = BookImporter(tmp_path / "book_data").import_outline(source, use_llm="never")
    book = BookRepository(result.book_root).load_book()

    assert result.work_id == "canonical_direct"
    assert book["work"]["title"] == "Canonical Direct"
    assert result.report_path.exists()


def test_import_outline_can_target_existing_book_root(tmp_path):
    source = tmp_path / "legacy_outline.yaml"
    target = tmp_path / "custom_book"
    source.write_text(LEGACY_OUTLINE)

    result = BookImporter(tmp_path / "book_data").import_outline(
        source,
        book_root=target,
        use_llm="never",
    )
    saved = yaml.safe_load(result.outline_path.read_text())

    assert result.book_root == target
    assert result.outline_path == target / "outline" / "custom_book.yaml"
    assert saved["work"]["id"] == "imported_book"


def test_import_markdown_outline_generates_unique_section_ids(tmp_path):
    source = tmp_path / "outline.md"
    source.write_text(
        """# Functional GUI Test Book

## Orientation

### What the Machine Should Do

State the user-visible loop.

### Testing a Fresh Outline

Confirm the imported outline appears in the workspace.

## Working Method

### Editorial Passes

Describe how edits feed back into the book.

### Export Surface

Describe the PDF preview.
"""
    )

    result = BookImporter(tmp_path / "book_data").import_outline(source, use_llm="never")
    book = BookRepository(result.book_root).load_book()
    nodes = book["work"]["structure"]
    leaf_ids = [
        child["id"]
        for chapter in nodes
        for child in chapter.get("content", [])
    ]

    assert len(leaf_ids) == 4
    assert len(leaf_ids) == len(set(leaf_ids))
    assert "what_the_machine_should_do" in leaf_ids
    assert "editorial_passes" in leaf_ids
    assert (
        result.book_root / "content" / "sections" / "what_the_machine_should_do.md"
    ).read_text() == "State the user-visible loop.\n"
    assert BookRepository(result.book_root).load_section("editorial_passes") == (
        "Describe how edits feed back into the book.\n"
    )
