"""Tests for the multi-book library registry."""

from pathlib import Path

import yaml

from scripts.book import BookAppState, BookLibrary, BookRepository
from scripts.outline_converter.converter import OutlineConverter


LEGACY_OUTLINE = """
outline:
  title: "{title}"
  summary: "Library test book."
  intent:
    audience: "Authors"
    writing_style: "Clear"
    author_persona: "Guide"
    reader_takeaway: "A book"
    genre: "Nonfiction"
  chapters:
    - id: "ch01"
      title: "Opening"
      sections:
        - id: "intro"
          title: "Introduction"
          content_summary: "Start."
"""


def write_book(book_root: Path, title: str) -> BookRepository:
    outline = yaml.safe_load(OutlineConverter().convert(
        LEGACY_OUTLINE.format(title=title),
        interactive=False,
        quiet=True,
    ))
    repository = BookRepository(book_root)
    repository.save_book(outline)
    repository.save_section("intro", f"{title} body\n")
    return repository


def test_library_refresh_discovers_books_and_persists_registry(tmp_path):
    write_book(tmp_path / "book_data" / "alpha", "Alpha Book")
    write_book(tmp_path / "book_data" / "beta", "Beta Book")

    library = BookLibrary(tmp_path / "book_data")
    records = library.refresh()

    assert [record.title for record in records] == ["Alpha Book", "Beta Book"]
    assert (tmp_path / "book_data" / "library.yaml").exists()
    assert library.search_books("beta")[0].title == "Beta Book"


def test_library_open_book_sets_active_book(tmp_path):
    write_book(tmp_path / "book_data" / "alpha", "Alpha Book")
    write_book(tmp_path / "book_data" / "beta", "Beta Book")
    library = BookLibrary(tmp_path / "book_data")
    library.refresh()

    opened = library.open_book("beta_book")

    assert opened.book_id == "beta_book"
    assert library.active().book_id == "beta_book"
    assert (tmp_path / "book_data" / ".active_book").read_text().strip() == "beta_book"


def test_library_create_book_registers_and_opens(tmp_path):
    library = BookLibrary(tmp_path / "book_data")

    record = library.create_book("New Library Book", tags=["draft"])

    assert record.book_id == "new_library_book"
    assert record.tags == ["draft"]
    assert Path(record.root).exists()
    assert library.active().book_id == "new_library_book"


def test_library_import_outline_registers_and_opens(tmp_path):
    source = tmp_path / "outline.yaml"
    source.write_text(LEGACY_OUTLINE.format(title="Imported Library Book"))
    library = BookLibrary(tmp_path / "book_data")

    record, result = library.import_outline(source, use_llm="never")

    assert record.book_id == "imported_library_book"
    assert result.outline_path.exists()
    assert library.active().book_id == "imported_library_book"


def test_app_state_can_use_library_active_root(tmp_path):
    write_book(tmp_path / "book_data" / "alpha", "Alpha Book")
    write_book(tmp_path / "book_data" / "beta", "Beta Book")
    library = BookLibrary(tmp_path / "book_data")
    library.refresh()
    record = library.open_book("beta_book")

    state = BookAppState(Path(record.root), data_root=tmp_path / "data").snapshot()

    assert state["book"]["title"] == "Beta Book"
    assert state["selectedSection"]["source"] == "Beta Book body\n"
