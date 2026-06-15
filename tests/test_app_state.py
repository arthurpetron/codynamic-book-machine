"""Tests for real desktop app state projection."""

from pathlib import Path
import json
from types import SimpleNamespace

import yaml

from scripts.book import BookAppState, BookRepository, CompileResult
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
    assert repository.load_section("intro") == "Initial section body.\n"


def test_snapshot_falls_back_when_selected_id_is_from_another_book(tmp_path):
    repository = create_book(tmp_path)

    state = BookAppState(repository.book_root, data_root=tmp_path / "data").snapshot("ch01_sec01")

    assert state["selectedId"] == "intro"
    assert state["selectedSection"]["id"] == "intro"


def test_save_section_updates_payload_and_verification_history(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    section = app.save_section("intro", "Edited body.\n")
    state = app.snapshot("intro")

    assert section["source"] == "Edited body.\n"
    assert state["selectedSection"]["score"] == 80
    assert repository.load_section("intro") == "Initial section body.\n"
    assert repository.load_latex_section("intro") == "Edited body.\n"


def test_editor_payload_unwraps_structured_agent_json(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section(
        "intro",
        json.dumps({
            "latex_body": "This opening section fixes the vocabulary.\n\nSecond paragraph.",
            "completeness_percent": 92,
            "completeness_rationale": "Strong coverage.",
        }) + "\n",
    )

    state = BookAppState(repository.book_root, data_root=tmp_path / "data").snapshot("intro")

    assert state["selectedSection"]["source"] == "This opening section fixes the vocabulary.\n\nSecond paragraph.\n"
    assert '{"latex_body"' not in state["selectedSection"]["source"]


def test_section_score_prefers_latest_completeness_over_later_status(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")
    loop = repository.authoring_loop()
    loop.history.record_event(
        event_type="section_agent_started",
        agent_id="section_agent__intro",
        subject="intro",
        status="pass",
        rationale="Drafted.",
        metadata={"completeness_percent": 92, "completeness_rationale": "Strong coverage."},
    )
    loop.record_gardener_check(
        section_id="intro",
        intent="pass",
        dependencies="pass",
        claim_clarity="warn",
        latex="pass",
        rationale="Claims need tightening.",
    )

    state = app.snapshot("intro")

    assert state["selectedSection"]["score"] == 92
    assert state["outline"][0]["items"][0]["score"] == 92


def test_request_review_is_reflected_in_state_history(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    event = app.request_review()
    state = app.snapshot("intro")

    assert event["event_type"] == "review_requested"
    assert state["verification"][-1]["event_type"] == "review_requested"


def test_start_section_agent_queues_introspective_plan_without_drafting(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")
    before_latex = repository.load_latex_section("intro")

    result = app.start_section_agent("intro")

    assert result["event"]["event_type"] == "section_agent_planned"
    assert result["planning_result"]["result"]["status"] == "plan_sent_to_self"
    assert repository.load_latex_section("intro") == before_latex
    runtime = json.loads((repository.book_root / "logs" / "agent_runtime.json").read_text())
    message_tasks = [
        task for task in runtime["section_agent__intro"]["task_queue"]
        if task["action_id"] == "process_message"
        and task["status"] == "pending"
    ]
    assert message_tasks
    assert message_tasks[0]["context"]["message"]["subject"] == "Section action plan: intro"


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


def test_hypervisor_runs_next_unscored_section_agent(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    class FakeProvider:
        def simple_prompt(self, prompt, system_prompt, temperature, max_tokens):
            return SimpleNamespace(
                content='{"latex_body":"Hypervisor draft.","completeness_percent":63,"completeness_rationale":"First pass."}',
                model="fake-model",
                provider="fake",
            )

    monkeypatch.setattr("scripts.book.app_state.get_provider_with_fallback", lambda providers: FakeProvider())
    monkeypatch.setattr(
        "scripts.book.agent_workflow.LatexBuildService.compile_section",
        lambda self, section_id: SimpleNamespace(
            status="passed",
            errors=[],
            as_dict=lambda: {"status": "passed", "errors": []},
        ),
    )

    result = app.run_hypervisor_once()

    assert result["targetSectionId"] == "intro"
    assert repository.load_latex_section("intro") == "Hypervisor draft.\n"
    assert app.snapshot("intro")["selectedSection"]["score"] == 63
    assert result["sectionAgent"]["gardener"]["status"] == "complete"


def test_hypervisor_draft_cycle_creates_diagram_when_section_needs_visual(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    repository.save_section("intro", "Explain this workflow with a diagram of the queue and agent loop.\n")
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    class FakeProvider:
        def simple_prompt(self, prompt, system_prompt, temperature, max_tokens):
            return SimpleNamespace(
                content='{"latex_body":"Hypervisor draft.","completeness_percent":63,"completeness_rationale":"First pass."}',
                model="fake-model",
                provider="fake",
            )

    monkeypatch.setattr("scripts.book.app_state.get_provider_with_fallback", lambda providers: FakeProvider())
    monkeypatch.setattr(
        "scripts.book.agent_workflow.LatexBuildService.compile_section",
        lambda self, section_id: SimpleNamespace(
            status="passed",
            errors=[],
            as_dict=lambda: {"status": "passed", "errors": []},
        ),
    )

    result = app.run_hypervisor_once()

    assert result["sectionAgent"]["visual"]["diagram_result"]["result"]["path"].startswith("media/diagrams/")
    assert "\\input{media/diagrams/" in repository.load_latex_section("intro")


def test_hypervisor_draft_cycle_skips_diagram_for_front_matter(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    book = repository.load_book()
    book["work"]["front_matter"] = {"abstract": {"enabled": True}}
    book["work"]["structure"] = [{
        "id": "abstract",
        "type": "chapter",
        "title": "Abstract",
        "summary": "Summarize the workflow and architecture.",
        "goal": "State the paper scope.",
        "dependencies": {"structural": [], "narrative": ""},
        "prerequisites": [],
        "content_file": "content/sections/abstract.md",
    }]
    repository.save_book(book)
    repository.save_section("abstract", "This abstract mentions a workflow diagram but is front matter.\n")
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    class FakeProvider:
        def simple_prompt(self, prompt, system_prompt, temperature, max_tokens):
            return SimpleNamespace(
                content='{"latex_body":"Abstract draft.","completeness_percent":63,"completeness_rationale":"First pass."}',
                model="fake-model",
                provider="fake",
            )

    monkeypatch.setattr("scripts.book.app_state.get_provider_with_fallback", lambda providers: FakeProvider())
    monkeypatch.setattr(
        "scripts.book.agent_workflow.LatexBuildService.compile_section",
        lambda self, section_id: SimpleNamespace(
            status="passed",
            errors=[],
            as_dict=lambda: {"status": "passed", "errors": []},
        ),
    )

    result = app.run_hypervisor_once()

    assert result["targetSectionId"] == "abstract"
    assert "visual" not in result["sectionAgent"]
    assert "media/diagrams/" not in repository.load_latex_section("abstract")


def test_snapshot_exposes_active_runtime_agents_for_titlebar(tmp_path):
    repository = create_book(tmp_path)
    from scripts.book.agent_workflow import AuthoringAgentWorkflow

    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.queue_agent_task("section_agent__intro", "draft_initial_section", {"section_id": "intro"})

    state = BookAppState(repository.book_root, data_root=tmp_path / "data").snapshot("intro")

    active_agents = state["agentStatus"]["activeAgents"]
    assert any(agent["agent_id"] == "section_agent__intro" for agent in active_agents)
    section_agent = next(agent for agent in active_agents if agent["agent_id"] == "section_agent__intro")
    assert section_agent["task_queue_length"] == 1
    assert section_agent["role"] == "section"


def test_hypervisor_returns_complete_when_all_session_sections_are_excluded(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")

    result = app.run_hypervisor_once(exclude_section_ids=["intro"])

    assert result["complete"] is True
    assert result["targetSectionId"] is None
    assert result["event"]["event_type"] == "hypervisor_idle"


def test_run_hypervisor_once_processes_urgent_compile_failure_before_drafting(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")
    from scripts.book.agent_workflow import AuthoringAgentWorkflow

    def fake_latex_pass(section_id, task_context=None):
        repository.save_latex_section(section_id, "\\section{Introduction}\n\nRepaired compile issue.\n")
        return {
            "event": {"event_type": "section_agent_started", "status": "pass"},
            "section": app.section_payload(section_id),
            "output_path": str(repository.book_root / "tex" / "section_payloads" / f"{section_id}.tex"),
        }

    monkeypatch.setattr(app, "_run_section_latex_pass", fake_latex_pass)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.message_router.publish({
        "from": "desktop_app",
        "to": "hypervisor_agent",
        "reply_to": "desktop_app",
        "subject": "LaTeX compile failed: section",
        "body": "target_section_ids:\n- intro\nerrors:\n- intro.tex:12: Undefined control sequence.\n",
    })

    result = app.run_hypervisor_once()

    assert result["phase"] == "compile_repair"
    assert result["event"]["event_type"] == "hypervisor_urgent_compile_failure_processed"
    assert result["executedRepairs"]
    runtime = json.loads((repository.book_root / "logs" / "agent_runtime.json").read_text())
    section_tasks = [
        task for task in runtime["section_agent__intro"]["task_queue"]
        if task["action_id"] == "fix_latex_compile_error"
    ]
    assert section_tasks
    assert section_tasks[0]["status"] == "complete"
    assert section_tasks[0]["priority"] == 0


def test_hypervisor_document_review_selects_revision_subset(tmp_path):
    repository = create_book(tmp_path)
    app = BookAppState(repository.book_root, data_root=tmp_path / "data")
    app.save_section("intro", "Existing draft.\n")

    result = app.review_document_for_revision_subset(limit=3)

    assert result["selectedSectionIds"] == ["intro"]
    assert result["documentChars"] > 0
    assert result["event"]["event_type"] == "hypervisor_document_reviewed"


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


def test_failed_section_compile_runs_agent_repair_loop_and_recompiles(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    failure = CompileResult(
        status="failed",
        tex_path=repository.book_root / "build" / "tex" / "intro.tex",
        pdf_path=None,
        log_path=repository.book_root / "build" / "logs" / "intro.log",
        command=["latexmk"],
        errors=["intro.tex:12: Undefined control sequence."],
    )
    success = CompileResult(
        status="passed",
        tex_path=repository.book_root / "build" / "tex" / "intro.tex",
        pdf_path=repository.book_root / "build" / "pdf" / "intro.pdf",
        log_path=repository.book_root / "build" / "logs" / "intro.log",
        command=["latexmk"],
        errors=[],
    )
    compile_results = [failure, success]

    def fake_compile(self, section_id):
        return compile_results.pop(0)

    class FakeProvider:
        def simple_prompt(self, prompt, system_prompt, temperature, max_tokens):
            return SimpleNamespace(
                content=json.dumps({
                    "latex_body": "Fixed body.",
                    "completeness_percent": 76,
                    "completeness_rationale": "Compile repair pass.",
                }),
                model="fake-model",
                provider="fake",
            )

    monkeypatch.setattr("scripts.book.app_state.LatexBuildService.compile_section", fake_compile)
    monkeypatch.setattr("scripts.book.app_state.get_provider_with_fallback", lambda providers: FakeProvider())

    result = BookAppState(repository.book_root, data_root=tmp_path / "data").compile_section("intro")

    assert result["status"] == "passed"
    assert result["repair_loop"]["status"] == "passed"
    assert len(result["repair_loop"]["attempts"]) == 1
    assert repository.load_latex_section("intro") == "Fixed body.\n"

    runtime = json.loads((repository.book_root / "logs" / "agent_runtime.json").read_text())
    repair_tasks = [
        task for task in runtime["section_agent__intro"]["task_queue"]
        if task["action_id"] == "fix_latex_compile_error"
    ]
    assert repair_tasks
    assert repair_tasks[0]["priority"] == 0
    assert runtime["hypervisor_agent"]["status"] == "running"


def test_failed_book_compile_runs_responsible_section_compile_fix_directly(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    failure = CompileResult(
        status="failed",
        tex_path=repository.book_root / "build" / "tex" / "desktop_book.tex",
        pdf_path=None,
        log_path=repository.book_root / "build" / "logs" / "desktop_book.log",
        command=["latexmk"],
        errors=["desktop_book.tex:42: Undefined control sequence. l.42 \\toprule"],
        responsible_section_ids=["intro"],
        responsible_section_titles=["Introduction"],
        diagnostic_summary="Compile failed in Introduction: Undefined control sequence. l.42 \\toprule",
    )
    success = CompileResult(
        status="passed",
        tex_path=repository.book_root / "build" / "tex" / "desktop_book.tex",
        pdf_path=repository.book_root / "build" / "pdf" / "desktop_book.pdf",
        log_path=repository.book_root / "build" / "logs" / "desktop_book.log",
        command=["latexmk"],
        errors=[],
    )
    compile_results = [failure, success]
    prompts = []

    def fake_compile(self):
        return compile_results.pop(0)

    class FakeProvider:
        def simple_prompt(self, prompt, system_prompt, temperature, max_tokens):
            prompts.append(prompt)
            return SimpleNamespace(
                content=json.dumps({
                    "latex_body": "Plain table body using \\hline.",
                    "completeness_percent": 77,
                    "completeness_rationale": "Fixed booktabs command locally.",
                }),
                model="fake-model",
                provider="fake",
            )

    monkeypatch.setattr("scripts.book.app_state.LatexBuildService.compile_book", fake_compile)
    monkeypatch.setattr("scripts.book.app_state.get_provider_with_fallback", lambda providers: FakeProvider())

    result = BookAppState(repository.book_root, data_root=tmp_path / "data").compile_book()

    assert result["status"] == "passed"
    assert result["repair_loop"]["status"] == "passed"
    assert repository.load_latex_section("intro") == "Plain table body using \\hline.\n"
    assert result["repair_loop"]["attempts"][0]["hypervisor"]["phase"] == "compile_repair"
    assert result["repair_loop"]["attempts"][0]["hypervisor"]["executed_repair_count"] == 1
    assert prompts
    assert "DIRECT LATEX COMPILE REPAIR" in prompts[0]
    assert "Undefined control sequence" in prompts[0]
    assert "\\toprule" in prompts[0]


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
