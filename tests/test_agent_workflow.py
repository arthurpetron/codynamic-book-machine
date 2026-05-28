"""Tests for real authoring-agent workflow orchestration."""

from pathlib import Path

from scripts.book import AuthoringAgentWorkflow, AuthoringLoop, BookRepository, CompileResult


def create_book(tmp_path: Path) -> BookRepository:
    book = {
        "work": {
            "id": "agent_book",
            "title": "Agent Book",
            "summary": "A book for workflow tests.",
            "metadata": {},
            "structure": [
                {
                    "id": "ch01",
                    "type": "chapter",
                    "title": "Opening",
                    "content": [
                        {
                            "id": "intro",
                            "type": "section",
                            "title": "Intro",
                            "summary": "Introduce the argument.",
                            "goal": "Orient the reader.",
                            "dependencies": {"structural": [], "narrative": ""},
                            "prerequisites": [],
                            "content_file": "content/sections/intro.md",
                        },
                        {
                            "id": "blocked",
                            "type": "section",
                            "title": "Blocked",
                            "summary": "Depends on missing material.",
                            "goal": "Show blocker handling.",
                            "dependencies": {
                                "structural": [
                                    {"section_id": "missing", "dependency_type": "builds_on"}
                                ],
                                "narrative": "",
                            },
                            "prerequisites": [],
                            "content_file": "content/sections/blocked.md",
                        },
                    ],
                }
            ],
            "citations": {"entries": []},
            "diagrams": [],
            "media": [],
        }
    }
    repository = BookRepository(tmp_path / "agent_book")
    repository.save_book(book)
    repository.save_section(
        "intro",
        "This section already has enough words to pass claim clarity checks for the deterministic gardener. "
        "It states a concrete claim, gives context, names the audience, and explains why the section matters "
        "before later verification work expands the details.\n",
    )
    return repository


def compile_result(tmp_path: Path, status: str = "passed") -> CompileResult:
    return CompileResult(
        status=status,
        tex_path=tmp_path / "section.tex",
        pdf_path=tmp_path / "section.pdf" if status == "passed" else None,
        log_path=tmp_path / "section.log",
        command=["latexmk"],
        errors=[] if status == "passed" else ["! Undefined control sequence."],
    )


def test_hypervisor_builds_dependency_blocker_graph(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    graph = workflow.dependency_graph()

    assert "intro" in graph["ready"]
    assert "blocked" in graph["blocked"]
    blocked = next(node for node in graph["nodes"] if node["section_id"] == "blocked")
    assert "Missing dependency: missing" in blocked["blockers"]
    assert workflow.commit_log.load()[-1]["action"] == "dependency_graph"


def test_hypervisor_spawns_starts_and_stops_agents(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    spawned = workflow.spawn_agents(section_ids=["intro"])
    started = workflow.start_agent("section_agent__intro")
    stopped = workflow.stop_agent("section_agent__intro", reason="Test complete.")

    assert "section_agent__intro" in spawned
    assert started["status"] == "running"
    assert stopped["status"] == "stopped"
    event_types = [event["event_type"] for event in AuthoringLoop(repository.book_root).history.load()]
    assert "agent_spawned" in event_types
    assert "agent_started" in event_types
    assert "agent_stopped" in event_types


def test_section_agent_drafts_tex_proposal_and_checkpoint(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    proposal = workflow.draft_section("intro")

    assert proposal.status == "pending"
    assert proposal.target_path == "content/sections/intro.tex"
    assert "\\section{Intro}" in proposal.proposed_content
    checkpoint = workflow.commit_log.load()[-1]
    assert checkpoint["action"] == "draft_section"
    assert checkpoint["metadata"]["proposal_id"] == proposal.proposal_id


def test_gardener_runs_checks_and_writes_verification_history(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    monkeypatch.setattr(
        "scripts.book.agent_workflow.LatexBuildService.compile_section",
        lambda self, section_id: compile_result(tmp_path),
    )

    event = workflow.run_gardener_checks("intro")

    assert event["status"] == "pass"
    assert event["metadata"]["compile"]["status"] == "passed"
    assert workflow.commit_log.load()[-1]["action"] == "run_checks"


def test_diagram_agent_fulfills_pending_media_requests(tmp_path):
    repository = create_book(tmp_path)
    loop = AuthoringLoop(repository.book_root)
    request = loop.media.request_media("intro", "section_agent__intro", "A feedback loop.", media_type="svg")
    workflow = AuthoringAgentWorkflow(repository.book_root)

    fulfilled = workflow.fulfill_media_requests()

    assert fulfilled[0]["request_id"] == request["request_id"]
    assert fulfilled[0]["path"].startswith("media/diagrams/")
    assert (repository.book_root / fulfilled[0]["path"]).read_text().startswith("<svg")


def test_document_design_agent_proposes_style_fix_from_failed_compile(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    result = workflow.review_document_design(compile_result=compile_result(tmp_path, status="failed"))

    assert result["status"] == "fail"
    assert result["proposal"]["target_path"] == "style/document_design_fixes.tex"
    assert "Undefined commands detected" in result["proposal"]["proposed_content"]


def test_hypervisor_summarizes_drift_from_verification_history(tmp_path):
    repository = create_book(tmp_path)
    loop = AuthoringLoop(repository.book_root)
    loop.record_gardener_check("intro", "pass", "pass", "warn", "pass", rationale="Claims are thin.")
    workflow = AuthoringAgentWorkflow(repository.book_root)

    drift = workflow.summarize_drift()

    assert drift["status"] == "warn"
    assert "intro" in drift["rationale"]
