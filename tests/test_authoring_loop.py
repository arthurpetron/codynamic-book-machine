"""Tests for Phase 4 authoring and review loop primitives."""

import json
from pathlib import Path

import yaml

from scripts.agents.runtime_agents import DiagramAgent, SectionAgent
from scripts.book import AuthoringLoop, BookRepository, CommunicationMemory


def write_agent(path: Path, name: str):
    path.write_text(yaml.safe_dump({
        "name": name,
        "role": "Test agent",
        "permissions": ["write_proposals"],
        "actions": [],
    }))


def test_section_draft_is_proposal_first(tmp_path):
    loop = AuthoringLoop(tmp_path)

    proposal = loop.propose_section_draft(
        section_id="intro",
        content="Draft body\n",
        rationale="Initial section draft.",
    )

    assert proposal.status == "pending"
    assert "content/sections/intro.md" in proposal.diff
    assert not (tmp_path / "content" / "sections" / "intro.md").exists()
    assert loop.proposals.load(proposal.proposal_id).proposed_content == "Draft body\n"


def test_accepting_proposal_writes_file_and_history(tmp_path):
    loop = AuthoringLoop(tmp_path)
    proposal = loop.propose_section_draft("intro", "Accepted body\n")

    accepted = loop.proposals.accept(proposal.proposal_id, reviewer="user", note="Looks good.")

    assert accepted.status == "accepted"
    assert (tmp_path / "content" / "sections" / "intro.md").read_text() == "Accepted body\n"
    history = loop.history.load()
    assert history[-1]["event_type"] == "proposal_accepted"
    assert history[-1]["metadata"]["proposal_id"] == proposal.proposal_id


def test_full_auto_mode_still_records_proposal_checkpoint(tmp_path):
    loop = AuthoringLoop(tmp_path, mode="full-auto")

    proposal = loop.propose_section_draft("intro", "Auto body\n")

    assert loop.proposals.load(proposal.proposal_id).status == "accepted"
    assert (tmp_path / "content" / "sections" / "intro.md").read_text() == "Auto body\n"


def test_gardener_hypervisor_and_design_checks_share_verification_history(tmp_path):
    loop = AuthoringLoop(tmp_path)

    gardener = loop.record_gardener_check(
        section_id="intro",
        intent="pass",
        dependencies="warn",
        claim_clarity="pass",
        latex="fail",
        rationale="LaTeX command is malformed.",
    )
    drift = loop.record_hypervisor_drift(
        subject="book",
        status="warn",
        rationale="Chapter 2 is drifting from stated audience.",
    )

    history = loop.history.load()
    assert gardener["status"] == "fail"
    assert drift["event_type"] == "global_drift_check"
    assert [event["event_type"] for event in history] == [
        "verification_check",
        "global_drift_check",
    ]


def test_single_diagram_agent_fulfills_media_request_under_media_folder(tmp_path):
    loop = AuthoringLoop(tmp_path)
    request = loop.media.request_media(
        section_id="intro",
        requesting_agent="section_intro",
        description="A simple feedback loop.",
    )

    fulfilled = loop.media.fulfill_request(
        request["request_id"],
        diagram_agent="diagram_agent",
        content="\\begin{tikzpicture}\\end{tikzpicture}\n",
    )

    assert fulfilled["status"] == "fulfilled"
    assert fulfilled["path"].startswith("media/diagrams/")
    assert (tmp_path / fulfilled["path"]).read_text().startswith("\\begin{tikzpicture}")

    artifacts = BookRepository(tmp_path).refresh_artifacts()
    assert any(artifact.kind == "diagram" and artifact.path == fulfilled["path"] for artifact in artifacts)


def test_runtime_agents_expose_authoring_helpers(tmp_path):
    definitions = tmp_path / "defs"
    definitions.mkdir()
    section_def = definitions / "section_agent.yaml"
    diagram_def = definitions / "diagram_agent.yaml"
    write_agent(section_def, "section_agent")
    write_agent(diagram_def, "diagram_agent")

    section_agent = SectionAgent(str(section_def), "section_intro", data_root=tmp_path / "data")
    proposal = section_agent.propose_section_draft(
        book_root=tmp_path / "book",
        section_id="intro",
        content="Agent draft\n",
    )
    request = AuthoringLoop(tmp_path / "book").media.request_media(
        "intro",
        "section_intro",
        "A visual.",
    )
    diagram_agent = DiagramAgent(str(diagram_def), "diagram_agent", data_root=tmp_path / "data")
    fulfilled = diagram_agent.fulfill_media_request(
        book_root=tmp_path / "book",
        request_id=request["request_id"],
        content="<svg></svg>\n",
        extension=".svg",
    )

    assert proposal.status == "pending"
    assert fulfilled["path"].endswith(".svg")


def test_communication_memory_summarizes_logs_and_user_questions(tmp_path):
    agent_dir = tmp_path / "agent_state" / "section_intro"
    agent_dir.mkdir(parents=True)
    (agent_dir / "message_log.yaml").write_text(yaml.safe_dump([
        {"message": {"from": "section_intro", "to": "diagram_agent", "subject": "Need figure"}},
        {"message": {"from": "section_intro", "to": "diagram_agent", "subject": "Need figure"}},
    ]))
    queue = tmp_path / "user_chat" / "queue.json"
    queue.parent.mkdir(parents=True)
    queue.write_text(json.dumps([
        {"subject": "Clarify audience", "status": "pending"},
        {"subject": "Clarify audience", "status": "answered"},
    ]))

    memory = CommunicationMemory(tmp_path).build()

    assert memory["common_action_patterns"][0]["count"] == 2
    assert memory["common_questions"][0] == {"question": "Clarify audience", "count": 2}
    assert CommunicationMemory(tmp_path).load()["message_count"] == 2
