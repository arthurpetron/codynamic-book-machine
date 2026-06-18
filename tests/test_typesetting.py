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
    repository.save_latex_section("intro", "This is section text with $x$.\n")
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
    assert "\\usepackage{tikz}" in full_tex
    assert "\\usetikzlibrary{positioning,arrows.meta}" in full_tex
    assert "\\section{Opening}" in full_tex
    assert "\\subsection{Introduction}" in full_tex
    assert "% CBM-SECTION-START:intro:Introduction" in full_tex
    assert "\\maketitle" not in full_tex
    assert "\\tableofcontents" not in full_tex
    assert "This is section text with $x$." in section_tex


def test_assembler_strips_leading_chapter_heading_from_section_payload(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section("intro", "\\chapter{Introduction}\n\nThis body should remain.\n")

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert "\\chapter{Introduction}" not in full_tex
    assert "This body should remain." in full_tex


def test_assembler_strips_wrapping_appendices_environment_from_section_payload(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section("intro", "\\begin{appendices}\n\nAppendix body.\n\n\\end{appendices}\n")

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert "\\begin{appendices}" not in full_tex
    assert "\\end{appendices}" not in full_tex
    assert "Appendix body." in full_tex


def test_front_matter_can_be_enabled_from_design_settings(tmp_path):
    repository = create_book(tmp_path)
    repository.design_settings().update({
        "title_page_enabled": True,
        "table_of_contents_enabled": True,
    })

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert "\\maketitle" in full_tex
    assert "\\tableofcontents" in full_tex


def test_assembler_skips_imported_title_page_node_when_disabled(tmp_path):
    repository = create_book(tmp_path)
    book = repository.load_book()
    book["work"]["structure"].insert(0, {
        "id": "title_page",
        "type": "section",
        "title": "Title Page(s)",
        "content_file": "content/sections/title_page.md",
    })
    repository.save_book(book)
    repository.save_latex_section("title_page", "\\begin{titlepage}Imported title\\end{titlepage}\n")

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert "Imported title" not in full_tex
    assert "\\begin{titlepage}" not in full_tex


def test_assembler_strips_duplicate_section_heading_from_payload(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section("intro", "\\section{Introduction}\n\nBody only.\n")

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert full_tex.count("\\subsection{Introduction}") == 1
    assert "\\section{Introduction}" not in full_tex
    assert "Body only." in full_tex


def test_assembler_escapes_caret_in_outline_titles(tmp_path):
    repository = create_book(tmp_path)
    book = repository.load_book()
    book["work"]["structure"][0]["content"][0]["title"] = r"Learning on \(\mathbb{B}^n\)"
    repository.save_book(book)

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert "\\textasciicircum{}n" in full_tex


def test_assembler_unwraps_structured_agent_latex_payload(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section("intro", '{"latex_body":"Body from JSON payload.","completeness_percent":78}\n')

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert '{"latex_body"' not in full_tex
    assert "Body from JSON payload." in full_tex


def test_assembler_unwraps_legacy_malformed_agent_latex_payload(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section(
        "intro",
        '{"latex_body":"This uses \\emph{raw LaTeX} and \\\\(x\\\\).\\nNext paragraph.","completeness_percent":78}\n',
    )

    full_tex = repository.latex_builder().assembler.assemble_book()

    assert '{"latex_body"' not in full_tex
    assert "This uses \\emph{raw LaTeX} and \\(x\\)." in full_tex
    assert "Next paragraph." in full_tex


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


def test_compile_extracts_split_file_line_latex_errors(tmp_path, monkeypatch):
    repository = create_book(tmp_path)

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout="./build/tex/typeset_book.tex:84:\nUndefined control sequence.\nl.84 \\mathbb{B} \\coloneqq\n",
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert result.status == "failed"
    assert result.errors == ["typeset_book.tex:84: Undefined control sequence. l.84 \\mathbb{B} \\coloneqq"]


def test_compile_extracts_missing_math_mode_errors(tmp_path, monkeypatch):
    repository = create_book(tmp_path)

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout="./build/tex/typeset_book.tex:132:\n Missing $ inserted.\nl.132 {\"latex_\n",
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert result.errors == ['typeset_book.tex:132: Missing $ inserted. l.132 {"latex_']


def test_compile_maps_book_error_line_to_responsible_section(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    assembled = repository.latex_builder().assembler.assemble_book()
    error_line = next(
        index
        for index, line in enumerate(assembled.splitlines(), start=1)
        if "This is section text" in line
    )

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout=f"./build/tex/typeset_book.tex:{error_line}: Undefined control sequence.\\nl.{error_line} \\\\broken\n",
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert result.status == "failed"
    assert result.responsible_section_ids == ["intro"]
    assert result.responsible_section_titles == ["Introduction"]
    assert result.diagnostic_summary.startswith("Compile failed in Introduction:")


def test_compile_maps_tex_capacity_error_to_responsible_section(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    assembled = repository.latex_builder().assembler.assemble_book()
    error_line = next(
        index
        for index, line in enumerate(assembled.splitlines(), start=1)
        if "This is section text" in line
    )

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout=(
                f"./build/tex/typeset_book.tex:{error_line}: TeX capacity \n"
                "exceeded, sorry [input stack size=10000].\n"
                "\\curr@fontshape ->\\f@encoding\n"
                f"l.{error_line} ... \\texttt{{\\cite\\{{...\\}}}}\n"
                "./build/tex/typeset_book.tex:132:  ==> Fatal er\n"
                "ror occurred, no output PDF file produced!\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert "TeX capacity exceeded" in result.errors[0]
    assert result.responsible_section_ids == ["intro"]
    assert result.responsible_section_titles == ["Introduction"]


def test_compile_extracts_wrapped_missing_math_mode_error(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    repository.save_latex_section("intro", "This mentions references_agent directly.\n")
    assembled = repository.latex_builder().assembler.assemble_book()
    error_line = next(
        index
        for index, line in enumerate(assembled.splitlines(), start=1)
        if "references_agent" in line
    )

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout=(
                f"./build/tex/compiler_test_book.tex:{error_line}: Missing $ ins\n"
                "erted.\n"
                "<inserted text>\n"
                "                $\n"
                f"l.{error_line} This mentions references_\n"
                "                             agent directly.\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert result.status == "failed"
    assert "Missing $ inserted" in result.errors[0]
    assert result.responsible_section_ids == ["intro"]
    assert result.responsible_section_titles == ["Introduction"]


def test_compile_extracts_wrapped_latexmk_file_line_errors(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    assembled = repository.latex_builder().assembler.assemble_book()
    error_line = next(
        index
        for index, line in enumerate(assembled.splitlines(), start=1)
        if "This is section text" in line
    )

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout=(
                "./build/tex/typeset_book.t\n"
                f"ex:{error_line}: Undefined control sequence.\n"
                f"l.{error_line} \\\\toprule\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert result.errors == [f"typeset_book.tex:{error_line}: Undefined control sequence. l.{error_line} \\\\toprule"]
    assert result.responsible_section_ids == ["intro"]


def test_compile_extracts_wrapped_undefined_control_sequence(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    assembled = repository.latex_builder().assembler.assemble_book()
    error_line = next(
        index
        for index, line in enumerate(assembled.splitlines(), start=1)
        if "This is section text" in line
    )

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout=(
                f"./build/tex/typeset_book.tex:{error_line}: Undefined control seque\n"
                "nce.\n"
                f"l.{error_line} \\\\chapter\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert result.errors == [f"typeset_book.tex:{error_line}: Undefined control sequence. l.{error_line} \\\\chapter"]
    assert result.responsible_section_ids == ["intro"]


def test_compile_extracts_wrapped_environment_error(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    assembled = repository.latex_builder().assembler.assemble_book()
    error_line = next(
        index
        for index, line in enumerate(assembled.splitlines(), start=1)
        if "This is section text" in line
    )

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        return SimpleNamespace(
            returncode=1,
            stdout=(
                f"./build/tex/typeset_book.tex:{error_line}: LaTeX Error: Environmen\n"
                "t appendices undefined.\n"
                f"l.{error_line} \\\\begin{{appendices}}\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = repository.latex_builder().compile_book()

    assert result.errors == [f"typeset_book.tex:{error_line}: LaTeX Error: Environment appendices undefined. l.{error_line} \\\\begin{{appendices}}"]
    assert result.responsible_section_ids == ["intro"]


def test_export_html_writes_canonical_content(tmp_path):
    repository = create_book(tmp_path)

    output = LatexBuildService(repository.book_root).export_html()

    assert output.exists()
    assert "Typeset Book" in output.read_text()
    assert "This is section text" in output.read_text()
