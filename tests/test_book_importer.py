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
