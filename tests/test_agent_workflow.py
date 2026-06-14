"""Tests for real authoring-agent workflow orchestration."""

from pathlib import Path

from scripts.api import LLMResponse
from scripts.book import AuthoringAgentWorkflow, AuthoringLoop, BookRepository, CompileResult


class RecordingProvider:
    def __init__(self):
        self.calls = []

    def get_provider_name(self):
        return "mock"

    def simple_prompt(self, prompt, system_prompt=None, **kwargs):
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "kwargs": kwargs,
        })
        return LLMResponse(
            content="\\section{Intro}\n\nA real provider-shaped draft with enough substance for review.\n",
            model="mock-section-model",
            provider="mock",
            tokens_used=123,
            latency_ms=4.5,
            metadata={"finish_reason": "stop"},
        )


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


def test_hypervisor_supervises_running_agents_and_queues_work(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    supervision = workflow.supervise_agents(section_ids=["intro"])

    runtime = supervision["runtime"]
    assert runtime["hypervisor_agent"]["status"] == "running"
    assert runtime["section_agent__intro"]["supervisor"] == "hypervisor_agent"
    assert runtime["section_agent__intro"]["definition_path"].endswith("section_agent.yaml")
    assert runtime["section_agent__intro"]["status"] == "running"
    assert runtime["section_agent__intro"]["task_queue"][0]["action_id"] == "draft_initial_section"
    assert runtime["section_agent__intro"]["task_queue"][0]["context"]["title"] == "Intro"
    assert runtime["gardener_agent"]["task_queue"][0]["action_id"] == "run_section_checks"
    assert any(task["action_id"] == "run_maintenance_cycle" for task in runtime["gardener_agent"]["task_queue"])
    assert supervision["event"]["event_type"] == "hypervisor_supervision_cycle"


def test_hypervisor_can_start_only_core_agents_for_heartbeat(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    supervision = workflow.supervise_agents(section_ids=[], queue_work=False)

    assert "gardener_agent" in supervision["runtime"]
    assert "diagram_agent" in supervision["runtime"]
    assert "references_agent" in supervision["runtime"]
    assert not any(agent_id.startswith("section_agent__") for agent_id in supervision["runtime"])


def test_hypervisor_runs_queued_section_task_into_proposal(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    task = workflow.queue_agent_task(
        "section_agent__intro",
        "draft_initial_section",
        {"section_id": "intro"},
    )

    result = workflow.run_agent_task("section_agent__intro")

    assert result["status"] == "complete"
    assert result["task"]["task_id"] == task["task_id"]
    assert result["result"]["proposal_id"].startswith("proposal_")
    assert result["task"]["result"]["target_path"] == "content/sections/intro.tex"


def test_task_queue_uses_message_router_for_assignment_and_gardener_feedback(tmp_path, monkeypatch):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)

    monkeypatch.setattr(
        "scripts.book.agent_workflow.LatexBuildService.compile_section",
        lambda self, section_id: compile_result(tmp_path, status="passed"),
    )
    workflow.queue_agent_task(
        "section_agent__intro",
        "draft_initial_section",
        {"section_id": "intro"},
    )
    workflow.queue_agent_task(
        "gardener_agent",
        "run_section_checks",
        {"section_id": "intro"},
    )

    result = workflow.run_supervised_tasks()

    assert len(result["completed"]) == 2
    message_files = list((repository.book_root / "logs" / "message_log").glob("*.yaml"))
    message_text = "\n".join(path.read_text() for path in message_files)
    assert "Task queued: draft_initial_section" in message_text
    assert "Task queued: run_section_checks" in message_text
    assert "Section task complete: intro" in message_text
    assert "Section payload ready: intro" in message_text
    assert "Gardener feedback: intro" in message_text
    hypervisor_tasks = [
        task
        for task in workflow.runtime.list()["hypervisor_agent"]["task_queue"]
        if task["action_id"] == "process_message"
    ]
    assert hypervisor_tasks
    assert hypervisor_tasks[0]["context"]["message"]["subject"] == "Section task complete: intro"


def test_routed_message_becomes_process_message_task(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)

    workflow.message_router.publish({
        "from": "gardener_agent",
        "to": "section_agent__intro",
        "reply_to": "gardener_agent",
        "subject": "Gardener feedback: intro",
        "body": "Please clarify the opening claim.",
    })

    runtime = workflow.runtime.list()["section_agent__intro"]
    message_tasks = [task for task in runtime["task_queue"] if task["action_id"] == "process_message"]
    assert len(message_tasks) == 1
    assert message_tasks[0]["context"]["message"]["subject"] == "Gardener feedback: intro"
    assert runtime["status"] == "running"


def test_routed_message_becomes_hypervisor_task_and_starts_hypervisor(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.stop_agent("hypervisor_agent", reason="Manual hypervisor stop.")

    workflow.message_router.publish({
        "from": "section_agent__intro",
        "to": "hypervisor_agent",
        "reply_to": "section_agent__intro",
        "subject": "Section task complete: intro",
        "body": "Initial draft complete.",
    })

    runtime = workflow.runtime.list()["hypervisor_agent"]
    message_tasks = [task for task in runtime["task_queue"] if task["action_id"] == "process_message"]
    assert len(message_tasks) == 1
    assert message_tasks[0]["context"]["message"]["subject"] == "Section task complete: intro"
    assert runtime["status"] == "running"
    assert runtime["desired_status"] == "running"
    assert "current_prompt" in runtime


def test_hypervisor_process_message_gets_unprocessed_chat_log_tail(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)

    workflow.message_router.publish({
        "from": "gardener_agent",
        "to": "hypervisor_agent",
        "reply_to": "gardener_agent",
        "subject": "Global editorial drift detected",
        "body": "affected_section_agents:\n- section_agent__intro\n",
    })

    task = workflow.runtime.list()["hypervisor_agent"]["task_queue"][0]

    assert task["action_id"] == "process_message"
    assert task["context"]["unprocessed_chat_log_lines"]
    assert "gardener_agent --> hypervisor_agent:" in task["context"]["unprocessed_chat_log_lines"][-1]


def test_non_hypervisor_agent_runs_when_task_queue_is_nonzero(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.stop_agent("section_agent__intro", reason="Pause before queueing.")

    workflow.queue_agent_task(
        "section_agent__intro",
        "draft_initial_section",
        {"section_id": "intro"},
    )

    runtime = workflow.runtime.list()
    assert runtime["section_agent__intro"]["status"] == "running"
    assert runtime["section_agent__intro"]["desired_status"] == "running"


def test_non_hypervisor_agent_generates_prompt_when_queue_activates(tmp_path):
    repository = create_book(tmp_path)
    bib_path = repository.book_root / "references" / "references.bib"
    bib_path.parent.mkdir(parents=True, exist_ok=True)
    bib_path.write_text("@book{smith2024systems,\n  title = {Systems}\n}\n")
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)

    task = workflow.queue_agent_task(
        "section_agent__intro",
        "draft_initial_section",
        {
            "section_id": "intro",
            "title": "Intro",
            "content_summary": "Introduce the argument.",
        },
    )

    runtime = workflow.runtime.list()["section_agent__intro"]
    assert "current_prompt" in runtime
    assert runtime["current_task_id"] == task["task_id"]
    assert runtime["task_queue"][0]["generated_prompt"] == runtime["current_prompt"]
    assert "You are section_agent." in runtime["current_prompt"]
    assert "draft_initial_section" in runtime["current_prompt"]
    assert "Draft one initial LaTeX pass" in runtime["current_prompt"]
    assert "Reference workflow:" in runtime["current_prompt"]
    assert "diagram_agent:create_diagram_asset" in runtime["current_prompt"]
    assert "write_section_tex" in runtime["current_prompt"]
    assert "Section-agent task selection:" in runtime["current_prompt"]
    assert "references/references.bib" in runtime["current_prompt"]
    assert "smith2024systems" in runtime["current_prompt"]
    assert "Intro" in runtime["current_prompt"]


def test_agent_prompt_is_created_only_on_empty_to_nonempty_queue_transition(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)

    first = workflow.queue_agent_task(
        "section_agent__intro",
        "coordinate_with_sibling_sections",
        {"section_id": "intro", "sibling_context": []},
    )
    second = workflow.queue_agent_task(
        "section_agent__intro",
        "propose_section_improvements",
        {"section_id": "intro"},
    )

    runtime = workflow.runtime.list()["section_agent__intro"]
    assert runtime["current_task_id"] == first["task_id"]
    assert "coordinate_with_sibling_sections" in runtime["current_prompt"]
    assert "generated_prompt" not in second
    assert len(runtime["prompt_history"]) == 1


def test_hypervisor_starts_when_task_queue_is_nonzero(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.spawn_agents(section_ids=["intro"])
    workflow.stop_agent("hypervisor_agent", reason="Manual supervisor stop.")

    workflow.queue_agent_task(
        "hypervisor_agent",
        "summarize_drift",
        {"subject": "book"},
    )

    runtime = workflow.runtime.list()
    assert runtime["hypervisor_agent"]["status"] == "running"
    assert runtime["hypervisor_agent"]["task_queue"][0]["status"] == "pending"
    assert "current_prompt" in runtime["hypervisor_agent"]


def test_compile_failure_message_preempts_hypervisor_queue_and_prompt(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.queue_agent_task("hypervisor_agent", "summarize_drift", {"subject": "book"}, priority=10)

    workflow.message_router.publish({
        "from": "desktop_app",
        "to": "hypervisor_agent",
        "reply_to": "desktop_app",
        "subject": "LaTeX compile failed: section",
        "body": "intro.tex:12: Undefined control sequence.",
    })

    runtime = workflow.runtime.list()["hypervisor_agent"]
    assert runtime["task_queue"][0]["action_id"] == "process_message"
    assert runtime["task_queue"][0]["priority"] == 0
    assert runtime["task_queue"][0]["context"]["message"]["subject"] == "LaTeX compile failed: section"
    assert runtime["current_task_id"] == runtime["task_queue"][0]["task_id"]
    assert "LaTeX compile failed: section" in runtime["current_prompt"]


def test_hypervisor_processes_compile_failure_message_into_repair_tasks(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.message_router.publish({
        "from": "desktop_app",
        "to": "hypervisor_agent",
        "reply_to": "desktop_app",
        "subject": "LaTeX compile failed: section",
        "body": "target_section_ids:\n- intro\nerrors:\n- intro.tex:12: Undefined control sequence.\n",
    })

    result = workflow.run_agent_task("hypervisor_agent")

    assert result["result"]["status"] == "repair_tasks_queued"
    section_tasks = [
        task for task in workflow.runtime.list()["section_agent__intro"]["task_queue"]
        if task["action_id"] == "revise_section_from_feedback"
    ]
    assert section_tasks
    assert section_tasks[0]["priority"] == 0
    assert "Undefined control sequence" in section_tasks[0]["context"]["feedback"]


def test_hypervisor_rejects_tasks_not_declared_by_agent_yaml(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)

    try:
        workflow.queue_agent_task("section_agent__intro", "undeclared_action", {})
    except ValueError as exc:
        assert "section_agent.yaml" in str(exc)
    else:
        raise AssertionError("Expected undeclared YAML action to be rejected")


def test_hypervisor_supervision_loop_can_run_bounded_cycle(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    result = workflow.run_supervision_loop(
        section_ids=["intro"],
        interval_seconds=0,
        cycles=1,
        run_tasks=False,
    )

    assert len(result["cycles"]) == 1
    assert result["cycles"][0]["supervision"]["queued_task_count"] > 0
    assert result["runtime"]["section_agent__intro"]["status"] == "running"


def test_section_agent_drafts_tex_proposal_and_checkpoint(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)

    proposal = workflow.draft_section("intro")

    assert proposal.status == "pending"
    assert proposal.target_path == "content/sections/intro.tex"
    assert "\\section{Intro}" in proposal.proposed_content
    checkpoint = workflow.commit_log.load()[-1]
    assert checkpoint["action"] == "draft_initial_section"
    assert checkpoint["metadata"]["proposal_id"] == proposal.proposal_id


def test_section_agent_can_draft_with_provider_and_record_usage(tmp_path):
    repository = create_book(tmp_path)
    provider = RecordingProvider()
    workflow = AuthoringAgentWorkflow(
        repository.book_root,
        llm_mode="always",
        provider=provider,
        model="mock-section-model",
    )

    proposal = workflow.draft_section("intro")

    assert provider.calls
    assert '"id": "intro"' in provider.calls[0]["prompt"]
    assert proposal.proposed_content.startswith("\\section{Intro}")
    assert proposal.metadata["llm"]["used"] is True
    assert proposal.metadata["llm"]["provider"] == "mock"
    assert proposal.metadata["llm"]["tokens_used"] == 123


def test_queued_revision_uses_specific_feedback_in_provider_prompt(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section("intro", "Existing LaTeX body that should be preserved.\n")
    provider = RecordingProvider()
    workflow = AuthoringAgentWorkflow(
        repository.book_root,
        llm_mode="always",
        provider=provider,
        model="mock-section-model",
    )
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.queue_agent_task(
        "section_agent__intro",
        "revise_section_from_feedback",
        {
            "section_id": "intro",
            "feedback": "Gardener says: define the central invariant before using it.",
            "phase": "revision",
        },
        priority=0,
    )

    result = workflow.run_agent_task("section_agent__intro")

    assert result["status"] == "complete"
    assert provider.calls
    prompt = provider.calls[0]["prompt"]
    assert "Revise the LaTeX body for section intro" in prompt
    assert "Gardener says: define the central invariant" in prompt
    assert "Existing LaTeX body that should be preserved" in prompt
    assert "Draft a LaTeX section payload" not in prompt
    assert result["result"]["metadata"]["action_id"] == "revise_section_from_feedback"
    assert result["result"]["metadata"]["feedback"] == "Gardener says: define the central invariant before using it."


def test_section_agent_proposal_result_can_feed_revision_task(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.queue_agent_task(
        "section_agent__intro",
        "propose_section_improvements",
        {"section_id": "intro", "sibling_context": [{"id": "next", "title": "Next"}]},
    )

    proposal_result = workflow.run_agent_task("section_agent__intro")

    assert proposal_result["status"] == "complete"
    feedback = proposal_result["result"]["feedback"]
    assert "propose_section_improvements" in feedback
    assert proposal_result["result"]["recommended_next_action"] == "revise_section_from_feedback"

    workflow.queue_agent_task(
        "section_agent__intro",
        "revise_section_from_feedback",
        {
            "section_id": "intro",
            "feedback": feedback,
            "proposal_task": proposal_result["task"],
        },
    )
    revision = workflow.run_agent_task("section_agent__intro")

    assert revision["status"] == "complete"
    assert revision["result"]["metadata"]["action_id"] == "revise_section_from_feedback"
    assert "propose_section_improvements" in revision["result"]["metadata"]["feedback"]


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


def test_gardener_document_context_includes_whole_document_relationships(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section("intro", "\\section{Intro}\nIntro depends on context.\n")
    workflow = AuthoringAgentWorkflow(repository.book_root)

    context = workflow.gardener_document_context(section_ids=["intro"])

    assert "Intro depends on context" in context["document_tex"]
    section = context["sections"][0]
    assert section["section_id"] == "intro"
    assert section["section_agent_id"] == "section_agent__intro"
    assert section["parent_id"] == "ch01"
    assert "blocked" in section["sibling_ids"]


def test_gardener_maintenance_cycle_routes_reference_support_to_references_agent(tmp_path):
    repository = create_book(tmp_path)
    repository.save_latex_section(
        "intro",
        "\\section{Intro}\n\nThis important claim is unsupported and needs citation.\n",
    )
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)

    result = workflow.run_gardener_maintenance_cycle({"section_ids": ["intro"], "force": True})

    assert result["cycle_status"] == "warn"
    assert result["scholarly_support_issues"]
    refs_tasks = [
        task for task in workflow.runtime.list()["references_agent"]["task_queue"]
        if task["action_id"] == "request_citation_definition_support"
    ]
    assert refs_tasks
    assert refs_tasks[0]["context"]["section_agent_id"] == "section_agent__intro"


def test_references_agent_notifies_section_agent_to_retrieve_support(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.queue_agent_task(
        "references_agent",
        "request_citation_definition_support",
        {
            "requesting_agent": "gardener_agent",
            "section_id": "intro",
            "section_agent_id": "section_agent__intro",
            "support_type": "citation",
            "claim_or_term": "The system needs a durable queue.",
            "context": {
                "link_targets": ["https://example.test/queues"],
                "raw_text_needed": "Find source text about durable queues.",
                "intended_use": "Support the section's queue claim.",
            },
        },
    )

    result = workflow.run_agent_task("references_agent")

    assert result["result"]["status"] == "section_agent_notified"
    section_tasks = workflow.runtime.list()["section_agent__intro"]["task_queue"]
    research_tasks = [task for task in section_tasks if task["action_id"] == "do_research_on_the_web"]
    assert research_tasks
    assert "https://example.test/queues" in research_tasks[0]["context"]["claim_or_need"]


def test_hypervisor_queues_assignments_from_gardener_global_drift(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro", "blocked"], queue_work=False)
    workflow.message_router.publish({
        "from": "gardener_agent",
        "to": "hypervisor_agent",
        "reply_to": "gardener_agent",
        "subject": "Global editorial drift detected",
        "body": """
status: drift_detected
affected_sections:
  - intro
  - blocked
affected_section_agents:
  - section_agent__intro
  - section_agent__blocked
recommended_assignments:
  - agent_id: section_agent__intro
    action_id: revise_section_from_feedback
    section_id: intro
    feedback:
      issue: Tighten transition.
  - agent_id: section_agent__blocked
    action_id: revise_section_from_feedback
    section_id: blocked
    feedback:
      issue: Remove duplicated claim.
""",
    })

    result = workflow.run_agent_task("hypervisor_agent")

    assert result["result"]["status"] == "drift_assignments_queued"
    assert len(result["result"]["queued_drift_assignments"]) == 2
    intro_tasks = workflow.runtime.list()["section_agent__intro"]["task_queue"]
    assert any(task["action_id"] == "revise_section_from_feedback" for task in intro_tasks)


def test_diagram_agent_fulfills_pending_media_requests(tmp_path):
    repository = create_book(tmp_path)
    loop = AuthoringLoop(repository.book_root)
    request = loop.media.request_media("intro", "section_agent__intro", "A feedback loop.", media_type="svg")
    workflow = AuthoringAgentWorkflow(repository.book_root)

    fulfilled = workflow.fulfill_media_requests()

    assert fulfilled[0]["request_id"] == request["request_id"]
    assert fulfilled[0]["path"].startswith("media/diagrams/")
    assert (repository.book_root / fulfilled[0]["path"]).read_text().startswith("<svg")


def test_diagram_agent_returns_asset_path_to_requesting_section_queue(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    task = workflow.queue_agent_task(
        "diagram_agent",
        "create_diagram_asset",
        {
            "section_id": "intro",
            "requesting_agent": "section_agent__intro",
            "media_type": "tikz",
            "description": "A feedback loop between context and section.",
        },
    )

    result = workflow.run_agent_task("diagram_agent")

    assert result["task"]["task_id"] == task["task_id"]
    path = result["result"]["path"]
    assert path.startswith("media/diagrams/")
    assert path.endswith(".tikz")
    section_runtime = workflow.runtime.list()["section_agent__intro"]
    messages = [
        queued
        for queued in section_runtime["task_queue"]
        if queued["action_id"] == "process_message"
    ]
    assert messages
    assert "Diagram asset ready: intro" == messages[0]["context"]["message"]["subject"]
    assert path in messages[0]["context"]["message"]["body"]
    assert path in repository.load_latex_section("intro")
    assert "\\begin{figure}" in repository.load_latex_section("intro")

    callback = workflow.run_agent_task("section_agent__intro")

    assert callback["result"]["status"] == "section_callback_followup_queued"
    followups = [
        queued
        for queued in workflow.runtime.list()["section_agent__intro"]["task_queue"]
        if queued["action_id"] == "revise_section_from_feedback"
    ]
    assert followups
    assert followups[0]["context"]["phase"] == "diagram_callback"
    assert path in followups[0]["context"]["feedback"]


def test_section_visual_proposal_queues_diagram_and_inserts_asset(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    workflow.queue_agent_task(
        "section_agent__intro",
        "propose_section_visuals",
        {
            "section_id": "intro",
            "description": "A two-node flow from context to section argument.",
            "media_type": "tikz",
        },
    )

    proposal = workflow.run_agent_task("section_agent__intro")
    assert proposal["result"]["status"] == "queued"

    diagram = workflow.run_agent_task("diagram_agent")
    path = diagram["result"]["path"]

    assert path.startswith("media/diagrams/")
    section_latex = repository.load_latex_section("intro")
    assert f"\\input{{{path}}}" in section_latex
    assert "A two-node flow from context to section argument" in section_latex


def test_references_agent_registers_bib_entries_and_updates_canonical_citations(tmp_path):
    repository = create_book(tmp_path)
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    task = workflow.queue_agent_task(
        "references_agent",
        "add_bib_entries",
        {
            "requesting_agent": "section_agent__intro",
            "section_id": "intro",
            "entries": [
                {
                    "id": "doe2026widgets",
                    "type": "article",
                    "title": "Compositional Widgets",
                    "author": "Doe, Jane",
                    "year": "2026",
                    "url": "https://example.test/widgets",
                }
            ],
        },
    )

    result = workflow.run_agent_task("references_agent")

    assert result["task"]["task_id"] == task["task_id"]
    assert result["result"]["registered_keys"] == ["doe2026widgets"]
    bib_path = repository.book_root / "references" / "references.bib"
    assert "@article{doe2026widgets" in bib_path.read_text()
    citations = BookRepository(repository.book_root).load_book()["work"]["citations"]["entries"]
    assert any(entry["id"] == "doe2026widgets" for entry in citations)
    section_messages = [
        queued for queued in workflow.runtime.list()["section_agent__intro"]["task_queue"]
        if queued["action_id"] == "process_message"
    ]
    assert any("References registered: intro" == task["context"]["message"]["subject"] for task in section_messages)

    callback = workflow.run_agent_task("section_agent__intro")

    assert callback["result"]["status"] == "section_callback_followup_queued"
    followups = [
        queued for queued in workflow.runtime.list()["section_agent__intro"]["task_queue"]
        if queued["action_id"] == "revise_section_from_feedback"
    ]
    assert followups
    assert followups[0]["context"]["phase"] == "references_callback"
    assert followups[0]["context"]["references_bib_path"] == "references/references.bib"
    assert "@article{doe2026widgets" in followups[0]["context"]["references_bib"]
    assert "doe2026widgets" in followups[0]["context"]["registered_references"]


def test_section_research_task_queues_reference_registration(tmp_path):
    repository = create_book(tmp_path)
    bib_path = repository.book_root / "references" / "references.bib"
    bib_path.parent.mkdir(parents=True, exist_ok=True)
    bib_path.write_text("@book{existing2024widgets,\n  title = {Existing Widgets}\n}\n")
    workflow = AuthoringAgentWorkflow(repository.book_root)
    workflow.supervise_agents(section_ids=["intro"], queue_work=False)
    queued = workflow.queue_agent_task(
        "section_agent__intro",
        "do_research_on_the_web",
        {
            "section_id": "intro",
            "research_topic": "compositional widgets",
            "claim_or_need": "Need a source for the motivating widget example.",
            "entries": [
                {
                    "id": "roe2025widgets",
                    "bibtex": "@book{roe2025widgets,\n  title = {Widget Categories},\n  author = {Roe, Richard},\n  year = {2025}\n}",
                }
            ],
        },
    )

    assert queued["context"]["references_bib_path"] == "references/references.bib"
    assert "@book{existing2024widgets" in queued["context"]["references_bib"]
    assert "existing2024widgets" in queued["generated_prompt"]

    result = workflow.run_agent_task("section_agent__intro")

    assert result["result"]["candidate_entry_count"] == 1
    refs_tasks = [
        task for task in workflow.runtime.list()["references_agent"]["task_queue"]
        if task["action_id"] == "add_bib_entries"
    ]
    assert refs_tasks
    assert refs_tasks[0]["context"]["section_id"] == "intro"


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
