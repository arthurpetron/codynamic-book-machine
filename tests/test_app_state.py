"""Tests for real desktop app state projection."""

from pathlib import Path
from types import SimpleNamespace

import yaml

from scripts.book import BookAppState, BookRepository
from scripts.outline_converter.converter import OutlineConverter
from scripts.utils.latex import LatexCompiler


LEGACY_OUTLINE = """
outline:
  title: "Desktop Book"
  summary: "A real UI state fixture."
  intent:
    audience: "Authors"
    writing_style: "Clear"
    author_persona: "Guide"
    reader_takeaway: "A usable desktop app"
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
    outline = yaml.safe_load(OutlineConverter().convert(LEGACY_OUTLINE, interactive=False, quiet=True))
    repository = BookRepository(tmp_path / "desktop_book")
    repository.save_book(outline)
    repository.save_section("intro", "Initial section body.\n")
    return repository


def test_snapshot_uses_canonical_outline_and_section_payload(tmp_path):
    repository = create_book(tmp_path)

    state = BookAppState(repository.book_root, data_root=tmp_path / "data").snapshot()

    assert state["book"]["title"] == "Desktop Book"
    assert state["outline"][0]["title"] == "Opening"
    assert state["outline"][0]["items"][0]["id"] == "intro"
    assert state["selectedSection"]["source"] == "Initial section body.\n"


def test_save_section_updates_payload_and_verification_history(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    section = app.save_section("intro", "Edited body.\n")
    state = app.snapshot("intro")

    assert section["source"] == "Edited body.\n"
    assert state["selectedSection"]["score"] == 94
    assert repository.load_section("intro") == "Edited body.\n"


def test_request_review_is_reflected_in_state_history(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    event = app.request_review()
    state = app.snapshot("intro")

    assert event["event_type"] == "review_requested"
    assert state["verification"][-1]["event_type"] == "review_requested"


def test_create_section_updates_outline_and_payload(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    section = app.create_section("New Argument", parent_id="ch01")
    state = app.snapshot(section["id"])

    assert section["id"] == "new_argument"
    assert state["selectedSection"]["title"] == "New Argument"
    assert any(item["id"] == "new_argument" for item in state["outline"][0]["items"])
    assert "\\section{New Argument}" in repository.load_section("new_argument")


def test_create_chapter_and_update_outline_node(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    chapter = app.create_chapter("Later Material")
    renamed = app.update_outline_node(chapter["id"], "Appendix Material")
    state = app.snapshot("intro")

    assert renamed["title"] == "Appendix Material"
    assert state["outline"][-1]["title"] == "Appendix Material"


def test_accept_and_reject_proposal_from_app_state(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")
    accepted = repository.authoring_loop().propose_section_draft("intro", "Accepted body.\n")
    rejected = repository.authoring_loop().propose_section_draft("intro", "Rejected body.\n")

    accepted_payload = app.accept_proposal(accepted.proposal_id, note="Looks good.")
    rejected_payload = app.reject_proposal(rejected.proposal_id, note="Needs work.")

    assert accepted_payload["status"] == "accepted"
    assert rejected_payload["status"] == "rejected"
    assert repository.load_section("intro") == "Accepted body.\n"


def test_revise_proposal_from_app_state(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")
    proposal = repository.authoring_loop().propose_section_draft("intro", "Original proposal.\n")

    revised = app.revise_proposal(proposal.proposal_id, "Revised proposal.\n", note="Use this version.")

    assert revised["status"] == "pending"
    assert revised["metadata"]["revised_from"] == proposal.proposal_id
    assert repository.proposals.load(proposal.proposal_id).status == "revised"


def test_compile_section_returns_structured_result(tmp_path, monkeypatch):
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

    result = BookAppState(repository.book_root, data_root=tmp_path / "data").compile_section("intro")

    assert result["status"] == "passed"
    assert result["pdf_path"].endswith("intro.pdf")


def test_compile_book_returns_structured_result(tmp_path, monkeypatch):
    repository = create_book(tmp_path)

    def fake_run(command, cwd, env, capture_output, text, timeout, check):
        output_dir = Path(cwd) / "build" / "pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "desktop_book.pdf").write_text("fake pdf")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(
        "scripts.book.typesetting.find_latex_compiler",
        lambda engine=None: LatexCompiler(name="latexmk", path="/usr/bin/latexmk"),
    )
    monkeypatch.setattr("scripts.book.typesetting.subprocess.run", fake_run)

    result = BookAppState(repository.book_root, data_root=tmp_path / "data").compile_book()

    assert result["status"] == "passed"
    assert result["pdf_path"].endswith("desktop_book.pdf")
