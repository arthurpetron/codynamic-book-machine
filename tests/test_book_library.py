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


def test_library_create_version_from_outline_starts_clean_project(tmp_path):
    source = tmp_path / "meta_book.yaml"
    source.write_text(
        yaml.safe_dump({
            "work": {
                "id": "sample_work",
                "type": "paper",
                "title": "Sample Work",
                "summary": "Versioned sample.",
                "metadata": {"version": "0.2.0", "updated": "2026-06-14"},
                "structure": [
                    {
                        "id": "intro",
                        "type": "chapter",
                        "title": "Intro",
                        "content_file": "content/sections/intro.md",
                    }
                ],
            }
        }, sort_keys=False)
    )
    previous_root = tmp_path / "book_data" / "sample_work"
    (previous_root / "tex" / "section_payloads").mkdir(parents=True)
    (previous_root / "tex" / "section_payloads" / "intro.tex").write_text("old generated text\n")

    library = BookLibrary(tmp_path / "book_data")
    record, result = library.create_version_from_outline(source, use_llm="never")

    assert record.book_id == "sample_work__v0_2_0"
    assert result.book_root == tmp_path / "book_data" / "sample_work__v0_2_0"
    assert library.active().book_id == "sample_work__v0_2_0"
    repository = BookRepository(result.book_root)
    work = repository.load_book()["work"]
    assert work["id"] == "sample_work__v0_2_0"
    assert work["metadata"]["version"] == "0.2.0"
    assert work["metadata"]["version_family_id"] == "sample_work"
    assert (result.book_root / "content" / "sections" / "intro.md").exists()
    assert not (result.book_root / "tex" / "section_payloads" / "intro.tex").exists()
    assert not (result.book_root / "logs").exists()


def test_library_recreates_same_outline_version_from_scratch_with_force(tmp_path):
    source = tmp_path / "meta_book.yaml"
    source.write_text(
        yaml.safe_dump({
            "work": {
                "id": "sample_work",
                "type": "paper",
                "title": "Sample Work",
                "summary": "Versioned sample.",
                "metadata": {"version": "0.2.0", "updated": "2026-06-14"},
                "structure": [
                    {
                        "id": "intro",
                        "type": "chapter",
                        "title": "Intro",
                        "content_file": "content/sections/intro.md",
                    }
                ],
            }
        }, sort_keys=False)
    )
    library = BookLibrary(tmp_path / "book_data")
    record, result = library.create_version_from_outline(source, use_llm="never")
    generated = result.book_root / "tex" / "section_payloads" / "intro.tex"
    generated.parent.mkdir(parents=True)
    generated.write_text("old generated text\n")
    stale_log = result.book_root / "logs" / "agent_runtime.json"
    stale_log.parent.mkdir(parents=True)
    stale_log.write_text("{}\n")

    recreated, recreated_result = library.create_version_from_outline(source, use_llm="never", force=True)

    assert recreated.book_id == record.book_id
    assert recreated_result.book_root == result.book_root
    assert library.active().book_id == record.book_id
    assert not generated.exists()
    assert not stale_log.exists()
    assert (result.book_root / "content" / "sections" / "intro.md").exists()


def test_app_state_can_use_library_active_root(tmp_path):
    write_book(tmp_path / "book_data" / "alpha", "Alpha Book")
    write_book(tmp_path / "book_data" / "beta", "Beta Book")
    library = BookLibrary(tmp_path / "book_data")
    library.refresh()
    record = library.open_book("beta_book")

    state = BookAppState(Path(record.root), data_root=tmp_path / "data").snapshot()

    assert state["book"]["title"] == "Beta Book"
    assert state["selectedSection"]["source"] == "Beta Book body\n"
