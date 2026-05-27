"""Tests for Phase 5 document assembly and typesetting."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from scripts.book import BookRepository, DocumentStyleRegistry, LatexBuildService
from scripts.outline_converter.converter import OutlineConverter
from scripts.utils.latex import LatexCompiler


LEGACY_OUTLINE = """
outline:
  title: "Typeset Book"
  summary: "A book for compiler tests."
  intent:
    audience: "Readers"
    writing_style: "Clear"
    author_persona: "Guide"
    reader_takeaway: "Confidence"
    genre: "Nonfiction"
  chapters:
    - id: "ch01"
      title: "Opening"
      sections:
        - id: "intro"
          title: "Introduction"
          content_summary: "Start here."
"""


def create_book(tmp_path: Path) -> BookRepository:
    book_root = tmp_path / "typeset_book"
    outline = yaml.safe_load(OutlineConverter().convert(LEGACY_OUTLINE, interactive=False, quiet=True))
    repository = BookRepository(book_root)
    repository.save_book(outline)
    repository.save_section("intro", "This is section text with $x$.\n")
    return repository


def test_style_registry_discovers_standard_and_arthur_style():
    styles = DocumentStyleRegistry(Path(".")).list_styles()
    ids = {style.style_id for style in styles}

    assert "standard_article" in ids
    assert "arthur_book" in ids


def test_design_settings_are_stored_in_canonical_book(tmp_path):
    repository = create_book(tmp_path)

    settings = repository.design_settings().update({
        "style_id": "standard_article",
        "page_size": "A4",
        "margin": "0.8in",
        "equation_style": "margin-numbered",
    })
    reloaded = BookRepository(repository.book_root).load_book()

    assert settings["page_size"] == "A4"
    assert reloaded["work"]["design_settings"]["margin"] == "0.8in"


def test_assembler_creates_full_book_and_section_tex(tmp_path):
    repository = create_book(tmp_path)
    builder = repository.latex_builder()

    full_tex = builder.assembler.assemble_book()
    section_tex = builder.assembler.assemble_section("intro")

    assert "\\documentclass[11pt]{article}" in full_tex
    assert "\\usepackage[margin=1in]{geometry}" in full_tex
    assert "\\section{Opening}" in full_tex
    assert "\\subsection{Introduction}" in full_tex
    assert "This is section text with $x$." in section_tex


def test_compile_without_compiler_writes_structured_failure_log(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    monkeypatch.setattr("scripts.book.typesetting.find_latex_compiler", lambda engine=None: None)

    result = repository.latex_builder().compile_section("intro")

    assert result.status == "failed"
    assert result.log_path.exists()
    assert "No LaTeX compiler found" in result.log_path.read_text()


def test_compile_with_latexmk_writes_pdf_artifact_and_log(tmp_path, monkeypatch):
    repository = create_book(tmp_path)

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        output_dir = Path(cwd) / "build" / "pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "intro.pdf").write_text("fake pdf")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_section("intro")

    assert result.status == "passed"
    assert result.pdf_path == repository.book_root / "build" / "pdf" / "intro.pdf"
    assert "-pdf" in result.command
    assert result.log_path.exists()


def test_export_html_writes_canonical_content(tmp_path):
    repository = create_book(tmp_path)

    output = LatexBuildService(repository.book_root).export_html()

    assert output.exists()
    assert "Typeset Book" in output.read_text()
    assert "This is section text" in output.read_text()
