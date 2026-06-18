"""Deterministic authoring-agent workflows for canonical book projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Any

import yaml

from scripts.agents.session import AgentSessionStore
from scripts.api import LLMProvider, LLMProviderError, LLMResponse, get_provider
from scripts.book.authoring import AuthoringLoop, EditProposal
from scripts.book.repository import BookRepository
from scripts.book.typesetting import CompileResult, LatexBuildService
from scripts.messaging.message_router import MessageRouter
from scripts.utils.latex import find_latex_compiler


AGENT_IDS = {
    "hypervisor": "hypervisor_agent",
    "section": "section_agent",
    "gardener": "gardener_agent",
    "diagram": "diagram_agent",
    "document_design": "document_design_agent",
    "references": "references_agent",
}

AGENT_DEFINITION_FILES = {
    "hypervisor": "hypervisor_agent.yaml",
    "section": "section_agent.yaml",
    "gardener": "gardener_agent.yaml",
    "diagram": "diagram_agent.yaml",
    "document_design": "document_designer_agent.yaml",
    "references": "references_agent.yaml",
}


@dataclass(frozen=True)
class SectionGraphNode:
    """One section in the contextual dependency/blocker graph."""

    section_id: str
    title: str
    parent_id: str | None
    dependencies: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    status: str = "ready"


@dataclass(frozen=True)
class DiagramBrief:
    """Typed input boundary for a diagram request."""

    section_id: str
    title: str
    summary: str
    goal: str
    description: str
    source_material: str
    current_latex: str
    prior_memory: list[dict[str, Any]] = field(default_factory=list)


DIAGRAM_KINDS = [
    "architecture_map",
    "lifecycle",
    "dependency_graph",
    "state_surface_map",
    "queue_flow",
    "artifact_pipeline",
    "comparison_matrix",
    "feedback_loop",
]

DIAGRAM_NOISE_TERMS = {
    "agent_id",
    "created_at",
    "current_latex",
    "finish_reason",
    "generated_prompt",
    "latex_body",
    "latency_ms",
    "media_type",
    "metadata",
    "model",
    "provider",
    "request_id",
    "requesting_agent",
    "section_id",
    "source_material",
    "status",
    "task_id",
    "tokens_used",
    "updated_at",
    "completeness_percent",
    "completeness_rationale",
}

GENERIC_DIAGRAM_LABELS = {
    "agent",
    "context",
    "diagram",
    "input",
    "mechanism",
    "output",
    "process",
    "problem",
    "result",
    "section",
    "source",
    "target",
}


class AgentCommitLog:
    """Append-only log of agent-authored checkpoints and proposal diffs."""

    def __init__(self, book_root: Path | str):
        self.path = Path(book_root) / "logs" / "agent_commit_log.jsonl"

    def record(
        self,
        agent_id: str,
        action: str,
        subject: str,
        rationale: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "checkpoint_id": f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "agent_id": agent_id,
            "action": action,
            "subject": subject,
            "rationale": rationale,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


class AgentRuntimeRegistry:
    """Book-local runtime state for spawned authoring agents."""

    def __init__(self, repository: BookRepository):
        self.repository = repository
        self.path = repository.book_root / "logs" / "agent_runtime.json"
        self.loop = AuthoringLoop(repository.book_root)
        self._lock = threading.RLock()

    def spawn(
        self,
        agent_id: str,
        role: str,
        section_id: str | None = None,
        supervisor: str = AGENT_IDS["hypervisor"],
        definition_path: str | None = None,
    ) -> dict[str, Any]:
        state = self._load()
        record = state.setdefault(agent_id, {})
        record.update({
            "agent_id": agent_id,
            "role": role,
            "section_id": section_id,
            "supervisor": supervisor,
            "definition_path": definition_path or record.get("definition_path"),
            "status": record.get("status") or "spawned",
            "desired_status": record.get("desired_status") or "running",
            "task_queue": record.get("task_queue") or [],
            "spawned_at": record.get("spawned_at") or datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })
        self._save(state)
        self.loop.history.record_event(
            event_type="agent_spawned",
            agent_id=AGENT_IDS["hypervisor"],
            subject=agent_id,
            status="warn",
            rationale=f"Spawned {role} agent.",
            metadata=record,
        )
        return record

    def start(self, agent_id: str) -> dict[str, Any]:
        record = self._ensure(agent_id)
        record["status"] = "running"
        record["desired_status"] = "running"
        record["started_at"] = datetime.now().isoformat()
        record["updated_at"] = record["started_at"]
        self._write_record(agent_id, record)
        self.loop.history.record_event(
            event_type="agent_started",
            agent_id=AGENT_IDS["hypervisor"],
            subject=agent_id,
            status="warn",
            rationale=f"Started {agent_id}.",
            metadata=record,
        )
        return record

    def stop(self, agent_id: str, reason: str = "") -> dict[str, Any]:
        record = self._ensure(agent_id)
        record["status"] = "stopped"
        record["desired_status"] = "stopped"
        record["stopped_at"] = datetime.now().isoformat()
        record["updated_at"] = record["stopped_at"]
        if reason:
            record["stop_reason"] = reason
        self._write_record(agent_id, record)
        self.loop.history.record_event(
            event_type="agent_stopped",
            agent_id=AGENT_IDS["hypervisor"],
            subject=agent_id,
            status="warn",
            rationale=reason or f"Stopped {agent_id}.",
            metadata=record,
        )
        return record

    def enqueue_task(
        self,
        agent_id: str,
        action_id: str,
        context: dict[str, Any] | None = None,
        priority: int = 50,
        assigned_by: str = AGENT_IDS["hypervisor"],
        dedupe: bool = True,
    ) -> dict[str, Any]:
        record = self._ensure(agent_id)
        context = context or {}
        queue = record.setdefault("task_queue", [])
        pending_before = [task for task in queue if task.get("status") == "pending"]
        top_pending_before = sorted(
            pending_before,
            key=lambda item: (item.get("priority", 50), item.get("added_at", "")),
        )[0] if pending_before else None
        if dedupe:
            for task in queue:
                if (
                    task.get("status") == "pending"
                    and task.get("action_id") == action_id
                    and task.get("context") == context
                ):
                    return task
        task = {
            "task_id": f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            "action_id": action_id,
            "context": context,
            "priority": priority,
            "status": "pending",
            "assigned_by": assigned_by,
            "added_at": datetime.now().isoformat(),
        }
        queue.append(task)
        queue.sort(key=lambda item: (item.get("priority", 50), item.get("added_at", "")))
        record["status"] = "running"
        record["desired_status"] = "running"
        record["started_at"] = record.get("started_at") or datetime.now().isoformat()
        top_pending_after = next((item for item in queue if item.get("status") == "pending"), None)
        should_refresh_prompt = (
            not pending_before
            or (
                top_pending_after
                and top_pending_after.get("task_id") == task["task_id"]
                and top_pending_before
                and top_pending_before.get("task_id") != task["task_id"]
            )
        )
        if should_refresh_prompt:
            prompt = self._generate_task_prompt(record, task)
            task["generated_prompt"] = prompt
            record["current_prompt"] = prompt
            record["current_task_id"] = task["task_id"]
            record.setdefault("prompt_history", []).append({
                "task_id": task["task_id"],
                "action_id": action_id,
                "prompt": prompt,
                "created_at": datetime.now().isoformat(),
            })
        record["updated_at"] = datetime.now().isoformat()
        self._write_record(agent_id, record)
        self.loop.history.record_event(
            event_type="agent_task_queued",
            agent_id=assigned_by,
            subject=agent_id,
            status="warn",
            rationale=f"Queued {action_id} for {agent_id}.",
            metadata={"task": task},
        )
        return task

    def _generate_task_prompt(self, record: dict[str, Any], task: dict[str, Any]) -> str:
        definition = self._load_definition(record)
        action = self._action_definition(definition, task.get("action_id", ""))
        context = task.get("context") or {}
        rendered_action_prompt = self._render_template(action.get("prompt_template", ""), context)
        capabilities = {
            "tasks": definition.get("tasks") or [],
            "inputs": definition.get("inputs") or [],
            "outputs": definition.get("outputs") or [],
            "permissions": definition.get("permissions") or [],
            "skills": definition.get("skills") or definition.get("capabilities") or [],
            "actions": [
                {"id": item.get("id"), "description": item.get("description", "")}
                for item in definition.get("actions", []) or []
                if item.get("id")
            ],
        }
        task_selection = []
        if definition.get("name") == "section_agent":
            task_selection = [
                "",
                "Section-agent task selection:",
                (
                    "Before executing, map the current queued task to one or more declared tasks "
                    "from your YAML, identify any prerequisite callback/research/registration work, "
                    "and then use the action that best performs that work."
                ),
                (
                    "For process_message callbacks, decide whether the message should trigger "
                    "revise_section_from_feedback, do_research_on_the_web, sibling coordination, "
                    "or only an acknowledgement."
                ),
            ]
        return "\n".join([
            f"You are {definition.get('name') or record.get('agent_id')}.",
            f"Role: {definition.get('role') or record.get('role', 'agent')}",
            "",
            "Prompt header:",
            str(definition.get("prompt_header") or "(No prompt header declared.)").strip(),
            "",
            "Declared capabilities from your agent definition YAML:",
            yaml.safe_dump(capabilities, sort_keys=False, allow_unicode=True).strip(),
            *task_selection,
            "",
            "Current queued task:",
            yaml.safe_dump({
                "task_id": task.get("task_id"),
                "action_id": task.get("action_id"),
                "priority": task.get("priority"),
                "assigned_by": task.get("assigned_by"),
                "context": context,
            }, sort_keys=False, allow_unicode=True).strip(),
            "",
            "Task-specific prompt:",
            rendered_action_prompt or f"Execute {task.get('action_id')} with the provided context.",
        ]).rstrip() + "\n"

    def _load_definition(self, record: dict[str, Any]) -> dict[str, Any]:
        definition_path = record.get("definition_path")
        if not definition_path:
            return {}
        path = Path(definition_path)
        if not path.is_absolute():
            path = Path(".") / path
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}

    def _action_definition(self, definition: dict[str, Any], action_id: str) -> dict[str, Any]:
        for action in definition.get("actions", []) or []:
            if action.get("id") == action_id:
                return action
        return {"id": action_id, "description": "", "prompt_template": ""}

    def _render_template(self, template: str, context: dict[str, Any]) -> str:
        import re

        def replace(match):
            key = match.group(1)
            if key not in context:
                return match.group(0)
            return self._stringify_prompt_value(context[key])

        return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, template)

    def _stringify_prompt_value(self, value: Any) -> str:
        if isinstance(value, (dict, list)):
            return yaml.safe_dump(value, sort_keys=False, allow_unicode=True).strip()
        return "" if value is None else str(value)

    def next_task(self, agent_id: str) -> dict[str, Any] | None:
        record = self._ensure(agent_id)
        pending = [task for task in record.get("task_queue", []) if task.get("status") == "pending"]
        if not pending:
            return None
        pending.sort(key=lambda item: (item.get("priority", 50), item.get("added_at", "")))
        return pending[0]

    def mark_task(
        self,
        agent_id: str,
        task_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> dict[str, Any]:
        record = self._ensure(agent_id)
        for task in record.get("task_queue", []):
            if task.get("task_id") == task_id:
                task["status"] = status
                task["updated_at"] = datetime.now().isoformat()
                if result is not None:
                    task["result"] = result
                if error:
                    task["error"] = error
                record["updated_at"] = task["updated_at"]
                self._write_record(agent_id, record)
                return task
        raise KeyError(f"Task not found for {agent_id}: {task_id}")

    def list(self) -> dict[str, Any]:
        return self._load()

    def _ensure(self, agent_id: str) -> dict[str, Any]:
        state = self._load()
        if agent_id not in state:
            raise KeyError(f"Agent has not been spawned: {agent_id}")
        return state[agent_id]

    def _write_record(self, agent_id: str, record: dict[str, Any]) -> None:
        with self._lock:
            state = self._load()
            state[agent_id] = record
            self._save(state)

    def _load(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                return {}
            return json.loads(self.path.read_text())

    def _save(self, state: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


class AuthoringAgentWorkflow:
    """Coordinate hypervisor, section, gardener, diagram, and design agents."""

    def __init__(
        self,
        book_root: Path | str,
        mode: str = "proposal",
        project_root: Path | str = Path("."),
        llm_mode: str = "never",
        provider: LLMProvider | None = None,
        provider_name: str = "openai",
        model: str | None = None,
    ):
        self.repository = BookRepository(Path(book_root))
        self.book_root = self.repository.book_root
        self.mode = mode
        self.project_root = Path(project_root)
        self.llm_mode = llm_mode
        self._provider = provider
        self.provider_name = provider_name
        self.model = model
        self.loop = AuthoringLoop(self.book_root, mode=mode)
        self.runtime = AgentRuntimeRegistry(self.repository)
        self.session_store = AgentSessionStore(self.book_root / "logs" / "agent_sessions")
        self.commit_log = AgentCommitLog(self.book_root)
        self.message_router = MessageRouter(log_dir=self.book_root / "logs" / "message_log")

    def dependency_graph(self) -> dict[str, Any]:
        """Build the hypervisor's contextual dependency and blocker graph."""
        service = self.repository.outline_service()
        raw_nodes = list(service._walk_raw(service.work.get("structure", [])))
        node_lookup = {node.get("id"): node for node, _, _ in raw_nodes}
        parent_lookup = {node.get("id"): parent_id for node, _, parent_id in raw_nodes}
        leaf_ids = [
            node["id"]
            for node, _, _ in raw_nodes
            if node.get("id") and not (node.get("content") or [])
        ]
        pending_targets = {
            proposal.target_path
            for proposal in self.loop.proposals.list(status="pending")
        }
        failed_subjects = {
            event["subject"]
            for event in self.loop.history.load()
            if event.get("status") in {"fail", "warn"}
            and event.get("event_type") in {"verification_check", "section_compile", "book_compile"}
        }
        media_blockers = {
            request["section_id"]
            for request in self.loop.media.load_requests()
            if request.get("status") == "pending"
        }

        graph_nodes = []
        edges = []
        for section_id in leaf_ids:
            node = node_lookup[section_id]
            dependencies = self._dependency_ids(node)
            blockers = []
            for dep_id in dependencies:
                edges.append({"from": dep_id, "to": section_id, "type": "structural"})
                if dep_id not in node_lookup:
                    blockers.append(f"Missing dependency: {dep_id}")
                elif dep_id in failed_subjects:
                    blockers.append(f"Dependency needs verification: {dep_id}")

            content = self.repository.load_section(section_id).strip()
            if not content:
                blockers.append("No section payload yet.")
            content_file = node.get("content_file") or f"content/sections/{section_id}.tex"
            if content_file in pending_targets:
                blockers.append("Pending proposal requires user review.")
            if section_id in media_blockers:
                blockers.append("Pending media request.")
            if section_id in failed_subjects:
                blockers.append("Recent verification warning or failure.")

            graph_nodes.append(SectionGraphNode(
                section_id=section_id,
                title=node.get("title", section_id),
                parent_id=parent_lookup.get(section_id),
                dependencies=dependencies,
                blockers=blockers,
                status="blocked" if blockers else "ready",
            ))

        payload = {
            "generated_at": datetime.now().isoformat(),
            "nodes": [asdict(node) for node in graph_nodes],
            "edges": edges,
            "ready": [node.section_id for node in graph_nodes if node.status == "ready"],
            "blocked": [node.section_id for node in graph_nodes if node.status == "blocked"],
        }
        self.commit_log.record(
            AGENT_IDS["hypervisor"],
            "dependency_graph",
            "book",
            "Built contextual dependency and blocker graph.",
            payload,
        )
        return payload

    def spawn_agents(self, section_ids: list[str] | None = None) -> dict[str, Any]:
        """Spawn the canonical long-lived agents and selected section agents."""
        section_ids = section_ids or self.dependency_graph()["ready"]
        records = {
            "hypervisor": self.runtime.spawn(
                AGENT_IDS["hypervisor"],
                "hypervisor",
                definition_path=str(self._definition_path("hypervisor")),
            ),
            "gardener": self.runtime.spawn(
                AGENT_IDS["gardener"],
                "gardener",
                definition_path=str(self._definition_path("gardener")),
            ),
            "diagram": self.runtime.spawn(
                AGENT_IDS["diagram"],
                "diagram",
                definition_path=str(self._definition_path("diagram")),
            ),
            "document_design": self.runtime.spawn(
                AGENT_IDS["document_design"],
                "document_design",
                definition_path=str(self._definition_path("document_design")),
            ),
            "references": self.runtime.spawn(
                AGENT_IDS["references"],
                "references",
                definition_path=str(self._definition_path("references")),
            ),
        }
        for section_id in section_ids:
            agent_id = f"{AGENT_IDS['section']}__{section_id}"
            records[agent_id] = self.runtime.spawn(
                agent_id,
                "section",
                section_id=section_id,
                definition_path=str(self._definition_path("section")),
            )
        return records

    def start_agent(self, agent_id: str) -> dict[str, Any]:
        return self.runtime.start(agent_id)

    def stop_agent(self, agent_id: str, reason: str = "") -> dict[str, Any]:
        return self.runtime.stop(agent_id, reason=reason)

    def supervise_agents(
        self,
        section_ids: list[str] | None = None,
        queue_work: bool = True,
    ) -> dict[str, Any]:
        """Hypervisor reconciliation: spawn, keep running, and assign durable work."""
        graph = self.dependency_graph()
        ready_sections = graph["ready"] if section_ids is None else section_ids
        desired_agents = {
            AGENT_IDS["hypervisor"]: {"role": "hypervisor", "section_id": None},
            AGENT_IDS["gardener"]: {"role": "gardener", "section_id": None},
            AGENT_IDS["diagram"]: {"role": "diagram", "section_id": None},
            AGENT_IDS["document_design"]: {"role": "document_design", "section_id": None},
            AGENT_IDS["references"]: {"role": "references", "section_id": None},
        }
        for section_id in ready_sections:
            desired_agents[f"{AGENT_IDS['section']}__{section_id}"] = {
                "role": "section",
                "section_id": section_id,
            }

        before = self.runtime.list()
        spawned = []
        restarted = []
        queued = []
        for agent_id, spec in desired_agents.items():
            record = before.get(agent_id)
            if not record:
                record = self.runtime.spawn(
                    agent_id,
                    spec["role"],
                    section_id=spec["section_id"],
                    definition_path=str(self._definition_path(spec["role"])),
                )
                spawned.append(agent_id)
            if record.get("status") != "running" or record.get("desired_status") != "running":
                self.runtime.start(agent_id)
                restarted.append(agent_id)

        if queue_work:
            queued.extend(self._queue_supervised_work(ready_sections))

        state = self.runtime.list()
        self._register_runtime_message_handlers()
        event = self.loop.history.record_event(
            event_type="hypervisor_supervision_cycle",
            agent_id=AGENT_IDS["hypervisor"],
            subject="agent_runtime",
            status="pass",
            rationale="Hypervisor reconciled desired agents, running state, and task queues.",
            metadata={
                "spawned": spawned,
                "restarted": restarted,
                "queued_task_count": len(queued),
                "desired_agents": sorted(desired_agents),
            },
        )
        self.commit_log.record(
            AGENT_IDS["hypervisor"],
            "supervise_agents",
            "agent_runtime",
            "Reconciled desired agents, running state, and task queues.",
            {
                "spawned": spawned,
                "restarted": restarted,
                "queued": queued,
                "event_id": event["event_id"],
            },
        )
        return {
            "spawned": spawned,
            "restarted": restarted,
            "queued": queued,
            "runtime": state,
            "event": event,
        }

    def queue_agent_task(
        self,
        agent_id: str,
        action_id: str,
        context: dict[str, Any] | None = None,
        priority: int = 50,
    ) -> dict[str, Any]:
        """Hypervisor-owned public task assignment API."""
        self._register_runtime_message_handlers()
        self._validate_agent_action(agent_id, action_id)
        context = self._enrich_agent_task_context(agent_id, action_id, context)
        task = self.runtime.enqueue_task(
            agent_id,
            action_id,
            context=context,
            priority=priority,
            assigned_by=AGENT_IDS["hypervisor"],
        )
        self.commit_log.record(
            AGENT_IDS["hypervisor"],
            "queue_task",
            agent_id,
            f"Queued {action_id}.",
            {"task": task},
        )
        self._publish_task_assignment(agent_id, task)
        return task

    def _enrich_agent_task_context(
        self,
        agent_id: str,
        action_id: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        context = self._enrich_section_task_context(agent_id, action_id, context)
        context = self._enrich_diagram_task_context(agent_id, action_id, context)
        return context

    def _enrich_section_task_context(
        self,
        agent_id: str,
        action_id: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not agent_id.startswith(f"{AGENT_IDS['section']}__"):
            return context
        enriched = dict(context or {})
        section_id = enriched.get("section_id") or agent_id.split("__", 1)[1]
        enriched.setdefault("section_id", section_id)
        registered_references = self._registered_reference_context()
        enriched.setdefault(
            "registered_references",
            yaml.safe_dump(registered_references, sort_keys=False, allow_unicode=True),
        )
        enriched.setdefault("references_bib_path", registered_references["bib_path"])
        enriched.setdefault("references_bib", registered_references["bibtex"])
        if action_id == "plan_section_work":
            node = self.repository.outline_service().get_node(section_id) or {}
            work = self.repository.outline_service().work
            enriched.setdefault("document_tex", LatexBuildService(self.book_root).assembler.assemble_book())
            enriched.setdefault("existing_latex", self.repository.load_latex_section(section_id))
            enriched.setdefault("source_material", self.repository.load_section(section_id))
            enriched.setdefault("section_outline", yaml.safe_dump(node, sort_keys=False, allow_unicode=True))
            enriched.setdefault("book_outline", yaml.safe_dump(work, sort_keys=False, allow_unicode=True))
        return enriched

    def _enrich_diagram_task_context(
        self,
        agent_id: str,
        action_id: str,
        context: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if agent_id != AGENT_IDS["diagram"] or action_id not in {"create_diagram_asset", "fulfill_media_requests"}:
            return context
        enriched = dict(context or {})
        section_id = enriched.get("section_id")
        if section_id:
            enriched.setdefault("section_context", self._diagram_section_context(str(section_id)))
        else:
            enriched.setdefault("pending_media_requests", self._pending_media_request_context())
        enriched.setdefault("diagram_memory", self._diagram_memory_context())
        return enriched

    def _diagram_section_context(self, section_id: str) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id) or {}
        return {
            "section_id": section_id,
            "outline": node,
            "source_material": self.repository.load_section(section_id)[:2000],
            "current_latex": self.repository.load_latex_section(section_id)[:2000],
        }

    def _pending_media_request_context(self) -> list[dict[str, Any]]:
        return [
            {
                "request_id": request.get("request_id"),
                "section_id": request.get("section_id"),
                "requesting_agent": request.get("requesting_agent"),
                "media_type": request.get("media_type"),
                "description": request.get("description"),
                "diagram_spec": request.get("diagram_spec"),
                "section_context": self._diagram_section_context(str(request.get("section_id")))
                if request.get("section_id")
                else {},
            }
            for request in self.loop.media.load_requests()
            if request.get("status") == "pending"
        ]

    def _diagram_memory_context(self, limit: int = 12) -> list[dict[str, Any]]:
        return self.list_diagram_memory(limit=limit)

    def run_agent_task(self, agent_id: str) -> dict[str, Any]:
        """Execute the next durable task for one running agent."""
        runtime = self.runtime.list().get(agent_id)
        if not runtime:
            raise KeyError(f"Agent has not been spawned: {agent_id}")
        if runtime.get("status") != "running":
            raise RuntimeError(f"Agent is not running: {agent_id}")
        task = self.runtime.next_task(agent_id)
        if not task:
            return {"agent_id": agent_id, "status": "idle", "task": None}

        self.runtime.mark_task(agent_id, task["task_id"], "running")
        self.session_store.record_event(
            agent_id,
            "task_started",
            task_id=task["task_id"],
            action_id=task.get("action_id"),
            metadata={"context": task.get("context") or {}},
        )
        try:
            result = self._dispatch_agent_task(agent_id, task)
        except Exception as exc:
            failed = self.runtime.mark_task(agent_id, task["task_id"], "failed", error=str(exc))
            self.session_store.record_event(
                agent_id,
                "task_failed",
                task_id=task["task_id"],
                action_id=task.get("action_id"),
                metadata={"error": str(exc)},
            )
            self.commit_log.record(
                AGENT_IDS["hypervisor"],
                "task_failed",
                agent_id,
                str(exc),
                {"task": failed},
            )
            raise

        completed = self.runtime.mark_task(agent_id, task["task_id"], "complete", result=result)
        self.session_store.record_event(
            agent_id,
            "task_completed",
            task_id=task["task_id"],
            action_id=task.get("action_id"),
            metadata={"result": result},
        )
        self.commit_log.record(
            agent_id,
            "task_complete",
            task["action_id"],
            f"Completed {task['action_id']}.",
            {"task": completed},
        )
        self._publish_task_completion(agent_id, task, result)
        return {"agent_id": agent_id, "status": "complete", "task": completed, "result": result}

    def run_supervised_tasks(self, limit: int | None = None) -> dict[str, Any]:
        """Run pending tasks across supervised running agents."""
        completed = []
        idle = []
        failures = []
        runnable_agent_ids = [
            agent_id
            for agent_id, record in sorted(self.runtime.list().items())
            if record.get("status") == "running"
            and any(task.get("status") == "pending" for task in record.get("task_queue", []))
        ]
        if limit is not None:
            runnable_agent_ids = runnable_agent_ids[:limit]

        max_workers = max(1, min(len(runnable_agent_ids), 8))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self.run_agent_task, agent_id): agent_id
                for agent_id in runnable_agent_ids
            }
            for future in as_completed(futures):
                agent_id = futures[future]
                try:
                    result = future.result()
                    if result["status"] == "idle":
                        idle.append(agent_id)
                    else:
                        completed.append(result)
                except Exception as exc:
                    failures.append({"agent_id": agent_id, "error": str(exc)})
        return {"completed": completed, "idle": idle, "failures": failures}

    def run_supervision_loop(
        self,
        section_ids: list[str] | None = None,
        interval_seconds: float = 5.0,
        cycles: int | None = None,
        run_tasks: bool = True,
    ) -> dict[str, Any]:
        """Keep reconciling hypervisor state until cycles are exhausted or interrupted."""
        cycle_results = []
        cycle_count = 0
        while cycles is None or cycle_count < cycles:
            supervision = self.supervise_agents(section_ids=section_ids, queue_work=True)
            task_result = self.run_supervised_tasks() if run_tasks else {"completed": [], "idle": [], "failures": []}
            cycle_results.append({
                "cycle": cycle_count + 1,
                "supervision": {
                    "spawned": supervision["spawned"],
                    "restarted": supervision["restarted"],
                    "queued_task_count": len(supervision["queued"]),
                },
                "tasks": task_result,
            })
            cycle_count += 1
            if cycles is not None and cycle_count >= cycles:
                break
            time.sleep(interval_seconds)
        return {"cycles": cycle_results, "runtime": self.runtime.list()}

    def summarize_drift(self) -> dict[str, Any]:
        """Summarize global drift from verification history."""
        events = self.loop.history.load()
        relevant = [
            event for event in events
            if event.get("event_type") in {
                "verification_check",
                "section_compile",
                "book_compile",
                "document_design_review",
                "global_drift_check",
            }
        ]
        failures = [event for event in relevant if event.get("status") == "fail"]
        warnings = [event for event in relevant if event.get("status") == "warn"]
        status = "fail" if failures else "warn" if warnings else "pass"
        rationale = self._drift_rationale(failures, warnings, relevant)
        event = self.loop.record_hypervisor_drift(
            subject="book",
            status=status,
            rationale=rationale,
            metadata={
                "event_count": len(relevant),
                "failure_count": len(failures),
                "warning_count": len(warnings),
                "recent_subjects": [event["subject"] for event in relevant[-5:]],
            },
        )
        return {"status": status, "rationale": rationale, "event": event}

    def draft_section(
        self,
        section_id: str,
        action_id: str = "draft_initial_section",
        task_context: dict[str, Any] | None = None,
    ) -> EditProposal:
        """Have the section agent draft or revise a TeX payload proposal for a section."""
        service = self.repository.outline_service()
        node = service.get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        graph = self.dependency_graph()
        graph_node = next((item for item in graph["nodes"] if item["section_id"] == section_id), {})
        response = None
        task_context = task_context or {}
        try:
            content, response = self._section_task_content(node, graph_node, action_id, task_context)
        except LLMProviderError:
            if self.llm_mode == "always":
                raise
            content = (
                self.repository.load_latex_section(section_id).strip()
                if action_id in {"revise_section_from_feedback", "fix_latex_compile_error"}
                else ""
            )
            if content:
                content += "\n"
            else:
                content = self._section_tex(node, graph_node)
        target = Path("content") / "sections" / f"{section_id}.tex"
        action_label = "Revised" if action_id != "draft_initial_section" else "Drafted"
        proposal = self.loop.proposals.propose_file_edit(
            agent_id=f"{AGENT_IDS['section']}__{section_id}",
            target_path=target,
            proposed_content=content,
            rationale=f"{action_label} TeX payload for {node.get('title', section_id)} via {action_id}.",
            metadata={
                "section_id": section_id,
                "kind": "section_tex_draft",
                "action_id": action_id,
                "task_context": task_context,
                "dependency_graph": graph_node,
                "content_file_update": str(target),
                "llm": self._llm_metadata(response),
            },
            mode=self.mode,
        )
        self.commit_log.record(
            proposal.agent_id,
            action_id,
            section_id,
            proposal.rationale,
            {
                "proposal_id": proposal.proposal_id,
                "target_path": proposal.target_path,
                "diff": proposal.diff,
                "status": proposal.status,
            },
        )
        self.loop.history.record_event(
            event_type="section_revised" if action_id != "draft_initial_section" else "section_drafted",
            agent_id=proposal.agent_id,
            subject=section_id,
            status="warn",
            rationale=proposal.rationale,
            metadata={"proposal_id": proposal.proposal_id, "target_path": proposal.target_path},
        )
        return proposal

    def run_gardener_checks(self, section_id: str) -> dict[str, Any]:
        """Run real section checks and append verification history."""
        node = self.repository.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        content = self.repository.load_section(section_id)
        known_ids = {item.id for item in self.repository.outline_service().tree()}
        dependencies = self._dependency_ids(node)
        missing_dependencies = [dep_id for dep_id in dependencies if dep_id not in known_ids]
        compile_result = LatexBuildService(self.book_root, project_root=self.project_root).compile_section(section_id)
        checks = {
            "intent": "pass" if (node.get("goal") or node.get("summary")) else "warn",
            "dependencies": "fail" if missing_dependencies else "pass",
            "claim_clarity": self._claim_clarity_status(content),
            "latex": "pass" if compile_result.status == "passed" else "fail",
        }
        rationale = self._gardener_rationale(checks, missing_dependencies, compile_result)
        event = self.loop.record_gardener_check(
            section_id=section_id,
            intent=checks["intent"],
            dependencies=checks["dependencies"],
            claim_clarity=checks["claim_clarity"],
            latex=checks["latex"],
            rationale=rationale,
        )
        event["metadata"].update({
            "compile": compile_result.as_dict(),
            "missing_dependencies": missing_dependencies,
        })
        self._rewrite_history_event(event)
        self.commit_log.record(
            AGENT_IDS["gardener"],
            "run_checks",
            section_id,
            rationale,
            {"event_id": event["event_id"], "checks": checks},
        )
        return event

    def run_gardener_heartbeat(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Backward-compatible alias for a maintenance cycle."""
        context = context or {}
        return self.run_gardener_maintenance_cycle({
            **context,
            "trigger": context.get("trigger") or "legacy_heartbeat",
        })

    def run_gardener_maintenance_cycle(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run the gardener's recurring maintenance cycle and emit queueable work."""
        context = context or {}
        trigger = context.get("trigger") or self._gardener_cycle_trigger(context)
        document_context = self.gardener_document_context(
            section_ids=context.get("section_ids"),
            max_tex_chars=context.get("max_tex_chars", 12000),
        )
        pending_media = [
            request for request in self.loop.media.load_requests()
            if request.get("status") == "pending"
        ]
        runtime = self.runtime.list()
        pending_section_agents = [
            agent_id
            for agent_id, record in runtime.items()
            if agent_id.startswith(f"{AGENT_IDS['section']}__")
            and any(task.get("status") in {"pending", "running"} for task in record.get("task_queue", []))
        ]
        inspected_sections = [section["section_id"] for section in document_context["sections"]]
        editorial_issues = self._detect_editorial_continuity_issues(document_context)
        scholarly_support_issues = self._detect_scholarly_support_issues(document_context)
        revision_tasks = self._queue_gardener_revision_briefs(editorial_issues)
        reference_tasks = self._queue_reference_support_requests(scholarly_support_issues)
        global_drift = self._gardener_global_drift(editorial_issues, scholarly_support_issues)
        rationale = (
            f"Gardener maintenance cycle triggered by {trigger}: inspected {len(inspected_sections)} section(s), "
            f"found {len(editorial_issues)} editorial issue(s), {len(scholarly_support_issues)} support issue(s), "
            f"{len(pending_section_agents)} section agent(s) with queued work, and {len(pending_media)} pending media request(s)."
        )
        status = "warn" if (
            pending_media
            or pending_section_agents
            or editorial_issues
            or scholarly_support_issues
            or global_drift
        ) else "pass"
        event = self.loop.history.record_event(
            event_type="gardener_maintenance_cycle",
            agent_id=AGENT_IDS["gardener"],
            subject="book",
            status=status,
            rationale=rationale,
            metadata={
                "trigger": trigger,
                "inspected_sections": inspected_sections,
                "pending_media_request_count": len(pending_media),
                "pending_section_agent_count": len(pending_section_agents),
                "editorial_issues": editorial_issues,
                "scholarly_support_issues": scholarly_support_issues,
                "revision_task_ids": [task.get("task_id") for task in revision_tasks],
                "reference_support_task_ids": [task.get("task_id") for task in reference_tasks],
                "global_drift": global_drift,
                "document_context": {
                    "document_tex_path": document_context.get("document_tex_path"),
                    "document_tex_chars": document_context.get("document_tex_chars"),
                    "section_count": len(document_context.get("sections", [])),
                },
                "context": context,
            },
        )
        self.commit_log.record(
            AGENT_IDS["gardener"],
            "run_maintenance_cycle",
            "book",
            rationale,
            {"event_id": event["event_id"]},
        )
        result = {
            "cycle_status": status,
            "trigger": trigger,
            "event": event,
            "document_context": document_context,
            "inspected_sections": inspected_sections,
            "editorial_issues": editorial_issues,
            "scholarly_support_issues": scholarly_support_issues,
            "section_revision_tasks": revision_tasks,
            "reference_support_tasks": reference_tasks,
            "global_drift_escalation": global_drift,
            "unresolved_blockers": self._gardener_unresolved_blockers(editorial_issues, scholarly_support_issues),
        }
        if global_drift:
            self._publish_global_drift_escalation(global_drift)
        return result

    def gardener_document_context(
        self,
        section_ids: list[str] | None = None,
        max_tex_chars: int = 12000,
    ) -> dict[str, Any]:
        """Return ordered TeX context for whole-document gardener inspection."""
        service = self.repository.outline_service()
        raw_nodes = list(service._walk_raw(service.work.get("structure", [])))
        parent_lookup = {node.get("id"): parent_id for node, _, parent_id in raw_nodes if node.get("id")}
        children_by_parent: dict[str | None, list[str]] = {}
        leaf_ids = []
        for node, _, parent_id in raw_nodes:
            node_id = node.get("id")
            if not node_id:
                continue
            children_by_parent.setdefault(parent_id, []).append(node_id)
            if not (node.get("content") or []):
                leaf_ids.append(node_id)
        selected = list(dict.fromkeys(section_ids or leaf_ids))
        selected = [section_id for section_id in selected if service.get_node(section_id)]
        downstream_by_dependency: dict[str, list[str]] = {}
        for node, _, _ in raw_nodes:
            node_id = node.get("id")
            if not node_id:
                continue
            for dependency_id in self._dependency_ids(node):
                downstream_by_dependency.setdefault(dependency_id, []).append(node_id)
        build_tex = self._latest_document_tex_path()
        assembled_sections = []
        for section_id in selected:
            node = service.get_node(section_id) or {}
            parent_id = parent_lookup.get(section_id)
            sibling_ids = [
                sibling_id
                for sibling_id in children_by_parent.get(parent_id, [])
                if sibling_id != section_id
            ]
            latex = self.repository.load_latex_section(section_id)
            source = self.repository.load_section(section_id)
            assembled_sections.append({
                "section_id": section_id,
                "section_agent_id": f"{AGENT_IDS['section']}__{section_id}",
                "title": node.get("title", section_id),
                "summary": node.get("summary", ""),
                "goal": node.get("goal", ""),
                "parent_id": parent_id,
                "sibling_ids": sibling_ids,
                "dependency_ids": self._dependency_ids(node),
                "downstream_ids": downstream_by_dependency.get(section_id, []),
                "latex_body": latex,
                "source_excerpt": source[:2400],
                "latex_line_count": len(latex.splitlines()),
                "source_line_count": len(source.splitlines()),
            })
        assembled_tex = "\n\n".join(
            f"% Section: {section['section_id']}\n{section['latex_body'] or section['source_excerpt']}"
            for section in assembled_sections
        )
        document_tex = build_tex.read_text() if build_tex and build_tex.exists() else assembled_tex
        if len(document_tex) > max_tex_chars:
            document_tex = document_tex[:max_tex_chars] + "\n% ... truncated for gardener context ...\n"
        return {
            "document_tex_path": str(build_tex.relative_to(self.book_root)) if build_tex else None,
            "document_tex": document_tex,
            "document_tex_chars": len(document_tex),
            "sections": assembled_sections,
        }

    def _gardener_cycle_trigger(self, context: dict[str, Any]) -> str:
        changed_line_count = self._changed_line_count_since_last_gardener_cycle()
        completed_section_tasks = self._completed_section_tasks_since_last_gardener_cycle()
        pending_media = len([
            request for request in self.loop.media.load_requests()
            if request.get("status") == "pending"
        ])
        if context.get("force"):
            return "forced"
        if changed_line_count >= int(context.get("changed_line_threshold", 40)):
            return f"changed_line_count:{changed_line_count}"
        if completed_section_tasks >= int(context.get("completed_section_task_threshold", 1)):
            return f"completed_section_agent_tasks:{completed_section_tasks}"
        if pending_media:
            return f"pending_media_requests:{pending_media}"
        return "scheduled_maintenance"

    def _latest_document_tex_path(self) -> Path | None:
        candidates = sorted((self.book_root / "build" / "tex").glob("*.tex"))
        if not candidates:
            return None
        return max(candidates, key=lambda path: path.stat().st_mtime)

    def _changed_line_count_since_last_gardener_cycle(self) -> int:
        latest_cycle_time = self._latest_gardener_cycle_time()
        count = 0
        for path in sorted((self.book_root / "tex" / "section_payloads").glob("*.tex")):
            if latest_cycle_time is not None and path.stat().st_mtime <= latest_cycle_time:
                continue
            count += len(path.read_text().splitlines())
        for proposal in self.loop.proposals.list(status="accepted"):
            if "content/sections/" in proposal.target_path or "tex/section_payloads/" in proposal.target_path:
                count += len(proposal.proposed_content.splitlines())
        return count

    def _completed_section_tasks_since_last_gardener_cycle(self) -> int:
        latest_cycle_iso = None
        for event in reversed(self.loop.history.load()):
            if event.get("event_type") == "gardener_maintenance_cycle":
                latest_cycle_iso = event.get("created_at")
                break
        count = 0
        for entry in self.commit_log.load():
            if entry.get("action") != "task_complete":
                continue
            if not str(entry.get("agent_id", "")).startswith(f"{AGENT_IDS['section']}__"):
                continue
            if latest_cycle_iso and str(entry.get("created_at", "")) <= latest_cycle_iso:
                continue
            count += 1
        return count

    def _latest_gardener_cycle_time(self) -> float | None:
        latest_iso = None
        for event in reversed(self.loop.history.load()):
            if event.get("event_type") == "gardener_maintenance_cycle":
                latest_iso = event.get("created_at")
                break
        if not latest_iso:
            return None
        try:
            return datetime.fromisoformat(latest_iso).timestamp()
        except ValueError:
            return None

    def _detect_editorial_continuity_issues(self, document_context: dict[str, Any]) -> list[dict[str, Any]]:
        issues = []
        sections = document_context.get("sections", [])
        seen_titles: dict[str, str] = {}
        for section in sections:
            section_id = section["section_id"]
            text = section.get("latex_body") or section.get("source_excerpt") or ""
            paragraphs = [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]
            normalized_title = str(section.get("title", "")).strip().lower()
            if normalized_title and normalized_title in seen_titles:
                issues.append(self._editorial_issue(
                    section,
                    "repeated_claims",
                    "Section title or framing repeats another section's title/framing.",
                    f"Potential duplicate with {seen_titles[normalized_title]}.",
                ))
            elif normalized_title:
                seen_titles[normalized_title] = section_id
            if len(paragraphs) <= 1 and text.strip():
                issues.append(self._editorial_issue(
                    section,
                    "thin_transitions",
                    "Section has little paragraph structure, which usually leaves transitions thin.",
                    "Only one substantive paragraph was detected.",
                ))
            if section.get("dependency_ids") and not any(dep_id in text for dep_id in section["dependency_ids"]):
                issues.append(self._editorial_issue(
                    section,
                    "dependency_mismatch",
                    "Section declares dependencies but does not visibly connect to them in its current TeX/source.",
                    f"Dependencies: {', '.join(section['dependency_ids'])}.",
                ))
            if section.get("sibling_ids") and text.strip().endswith("TODO:"):
                issues.append(self._editorial_issue(
                    section,
                    "abrupt_ending",
                    "Section appears to end as a placeholder instead of handing off to siblings/downstream sections.",
                    "Text ends with TODO marker.",
                ))
        return issues

    def _editorial_issue(
        self,
        section: dict[str, Any],
        issue_type: str,
        issue: str,
        evidence: str,
    ) -> dict[str, Any]:
        section_id = section["section_id"]
        return {
            "issue_type": issue_type,
            "severity": "major" if issue_type in {"dependency_mismatch", "repeated_claims"} else "minor",
            "section_id": section_id,
            "section_agent_id": f"{AGENT_IDS['section']}__{section_id}",
            "affected_sections": [section_id],
            "affected_section_agents": [f"{AGENT_IDS['section']}__{section_id}"],
            "issue": issue,
            "evidence": evidence,
            "recommended_fix": (
                "Revise the section to make the relationship to parent, sibling, dependency, "
                "and downstream context explicit without replacing useful prose wholesale."
            ),
        }

    def _detect_scholarly_support_issues(self, document_context: dict[str, Any]) -> list[dict[str, Any]]:
        issues = []
        citation_entries = self.repository.load_book()["work"].get("citations", {}).get("entries", [])
        registered_keys = {entry.get("id") for entry in citation_entries if entry.get("id")}
        for section in document_context.get("sections", []):
            text = section.get("latex_body") or section.get("source_excerpt") or ""
            lower = text.lower()
            if any(marker in lower for marker in ["citation needed", "needs citation", "unsupported"]):
                issues.append(self._support_issue(
                    section,
                    "citation",
                    "Unsupported assertion or explicit citation need.",
                    self._first_matching_line(text, ["citation needed", "needs citation", "unsupported"]),
                ))
            if any(marker in lower for marker in ["undefined", "define ", "needs definition", "missing definition"]):
                issues.append(self._support_issue(
                    section,
                    "definition",
                    "Missing or weak definition support.",
                    self._first_matching_line(text, ["undefined", "define ", "needs definition", "missing definition"]),
                ))
            for citation_key in self._citation_keys_in_text(text):
                if citation_key not in registered_keys:
                    issues.append(self._support_issue(
                        section,
                        "citation",
                        f"Citation key {citation_key} appears in section text but is not registered.",
                        f"Unregistered citation key: {citation_key}.",
                        claim_or_term=citation_key,
                    ))
        return issues

    def _support_issue(
        self,
        section: dict[str, Any],
        support_type: str,
        issue: str,
        evidence: str,
        claim_or_term: str | None = None,
    ) -> dict[str, Any]:
        section_id = section["section_id"]
        claim_or_term = claim_or_term or evidence[:240] or section.get("title", section_id)
        return {
            "support_type": support_type,
            "severity": "major",
            "section_id": section_id,
            "section_agent_id": f"{AGENT_IDS['section']}__{section_id}",
            "claim_or_term": claim_or_term,
            "issue": issue,
            "evidence": evidence,
            "context": {
                "title": section.get("title", section_id),
                "summary": section.get("summary", ""),
                "goal": section.get("goal", ""),
                "link_targets": [],
                "raw_text_needed": (
                    "Retrieve source text or definition wording sufficient to support this claim or term. "
                    "Return candidate references or definition-support notes to references_agent."
                ),
                "intended_use": "Support a section revision without inventing unregistered citation keys.",
            },
        }

    def _first_matching_line(self, text: str, markers: list[str]) -> str:
        for line in text.splitlines():
            lower = line.lower()
            if any(marker in lower for marker in markers):
                return line.strip()
        return ""

    def _citation_keys_in_text(self, text: str) -> list[str]:
        import re

        keys = []
        for match in re.findall(r"\\cite\w*\{([^}]+)\}", text):
            keys.extend(key.strip() for key in match.split(",") if key.strip())
        return list(dict.fromkeys(keys))

    def _queue_gardener_revision_briefs(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        queued = []
        runtime = self.runtime.list()
        for issue in issues:
            section_id = issue.get("section_id")
            if not section_id:
                continue
            section_agent_id = f"{AGENT_IDS['section']}__{section_id}"
            if section_agent_id not in runtime:
                continue
            feedback = yaml.safe_dump({
                "source": AGENT_IDS["gardener"],
                "kind": "editorial_continuity_issue",
                "section_id": section_id,
                "issue": issue,
                "instructions": (
                    "Address this focused editorial issue. Preserve useful prose, make the smallest "
                    "coherent revision, and leave citation/definition support to references_agent if needed."
                ),
            }, sort_keys=False, allow_unicode=True)
            queued.append(self.queue_agent_task(
                section_agent_id,
                "revise_section_from_feedback",
                {
                    "section_id": section_id,
                    "phase": "gardener_editorial_maintenance",
                    "feedback": feedback,
                },
                priority=15,
            ))
        return queued

    def _queue_reference_support_requests(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        queued = []
        runtime = self.runtime.list()
        for issue in issues:
            section_id = issue.get("section_id")
            if not section_id:
                continue
            section_agent_id = issue.get("section_agent_id") or f"{AGENT_IDS['section']}__{section_id}"
            if section_agent_id not in runtime:
                continue
            queued.append(self.queue_agent_task(
                AGENT_IDS["references"],
                "request_citation_definition_support",
                {
                    "requesting_agent": AGENT_IDS["gardener"],
                    "section_id": section_id,
                    "section_agent_id": section_agent_id,
                    "support_type": issue.get("support_type", "citation"),
                    "claim_or_term": issue.get("claim_or_term", ""),
                    "context": issue.get("context", {}),
                    "gardener_issue": issue,
                },
                priority=12,
            ))
        return queued

    def _gardener_global_drift(
        self,
        editorial_issues: list[dict[str, Any]],
        support_issues: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        all_issues = editorial_issues + support_issues
        affected_sections = sorted({issue.get("section_id") for issue in all_issues if issue.get("section_id")})
        if len(affected_sections) < 2:
            return None
        affected_agents = [f"{AGENT_IDS['section']}__{section_id}" for section_id in affected_sections]
        recommended_assignments = [
            {
                "agent_id": issue.get("section_agent_id") or f"{AGENT_IDS['section']}__{issue.get('section_id')}",
                "action_id": "revise_section_from_feedback",
                "section_id": issue.get("section_id"),
                "feedback": issue,
            }
            for issue in editorial_issues
        ]
        if support_issues:
            recommended_assignments.append({
                "agent_id": AGENT_IDS["references"],
                "action_id": "request_citation_definition_support",
                "section_ids": [issue.get("section_id") for issue in support_issues],
                "feedback": support_issues,
            })
        return {
            "status": "drift_detected",
            "affected_sections": affected_sections,
            "affected_section_agents": affected_agents,
            "drift_type": "editorial_and_scholarly_support_drift" if support_issues else "editorial_continuity_drift",
            "rationale": (
                "Gardener maintenance found related issues spanning multiple sections. "
                "Hypervisor should direct each affected section agent and coordinate reference support."
            ),
            "recommended_assignments": recommended_assignments,
        }

    def _publish_global_drift_escalation(self, drift: dict[str, Any]) -> None:
        self.message_router.publish({
            "from": AGENT_IDS["gardener"],
            "to": AGENT_IDS["hypervisor"],
            "reply_to": AGENT_IDS["gardener"],
            "subject": "Global editorial drift detected",
            "body": yaml.safe_dump(drift, sort_keys=False, allow_unicode=True),
        })

    def _gardener_unresolved_blockers(
        self,
        editorial_issues: list[dict[str, Any]],
        support_issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "section_id": issue.get("section_id"),
                "waiting_on": AGENT_IDS["references"],
                "reason": issue.get("issue"),
            }
            for issue in support_issues
        ] + [
            {
                "section_id": issue.get("section_id"),
                "waiting_on": issue.get("section_agent_id"),
                "reason": issue.get("issue"),
            }
            for issue in editorial_issues
            if issue.get("severity") == "major"
        ]

    def fulfill_media_requests(self) -> list[dict[str, Any]]:
        """Have the single diagram agent fulfill pending media requests."""
        fulfilled = []
        for request in self.loop.media.load_requests():
            if request.get("status") != "pending":
                continue
            extension = self._media_extension(request.get("media_type", "tikz"))
            diagram_spec = self._diagram_spec_for_request(request)
            content, review = self._render_and_review_media_content(request, extension, diagram_spec)
            result = self.fulfill_diagram_request(request, diagram_spec, content, extension, review)
            self.loop.history.record_event(
                event_type="media_fulfilled",
                agent_id=AGENT_IDS["diagram"],
                subject=request["section_id"],
                status="pass",
                rationale=f"Fulfilled media request {request['request_id']}.",
                metadata=result,
            )
            self.commit_log.record(
                AGENT_IDS["diagram"],
                "fulfill_media",
                request["section_id"],
                request.get("description", ""),
                {"request_id": request["request_id"], "path": result["path"]},
            )
            fulfilled.append(result)
        return fulfilled

    def create_diagram_asset(self, context: dict[str, Any]) -> dict[str, Any]:
        """Create one diagram asset and preserve requester metadata for response routing."""
        section_id = context.get("section_id")
        if not section_id:
            raise ValueError("create_diagram_asset requires section_id.")
        requesting_agent = context.get("requesting_agent") or f"{AGENT_IDS['section']}__{section_id}"
        description = context.get("description") or "Requested diagram."
        media_type = context.get("media_type") or "tikz"
        request = self.loop.media.request_media(
            section_id=section_id,
            requesting_agent=requesting_agent,
            description=description,
            media_type=media_type,
            diagram_spec=context.get("diagram_spec"),
        )
        extension = self._media_extension(media_type)
        diagram_spec = self._diagram_spec_for_request(request)
        content, review = self._render_and_review_media_content(request, extension, diagram_spec)
        result = self.fulfill_diagram_request(request, diagram_spec, content, extension, review)
        self.loop.history.record_event(
            event_type="diagram_asset_created",
            agent_id=AGENT_IDS["diagram"],
            subject=section_id,
            status="pass",
            rationale=f"Created diagram asset for {section_id}: {result['path']}.",
            metadata=result,
        )
        self.commit_log.record(
            AGENT_IDS["diagram"],
            "create_diagram_asset",
            section_id,
            description,
            {"request_id": result["request_id"], "path": result["path"], "requesting_agent": requesting_agent},
        )
        return result

    def fulfill_diagram_request(
        self,
        request: dict[str, Any],
        final_spec: dict[str, Any],
        content: str,
        extension: str,
        render_review: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.loop.media.fulfill_request(
            request_id=request["request_id"],
            diagram_agent=AGENT_IDS["diagram"],
            content=content,
            extension=extension,
        )
        result = self._attach_diagram_review(result, render_review)
        result["diagram_kind"] = final_spec.get("diagram_kind")
        result["similarity"] = final_spec.get("similarity", {})
        self._record_diagram_memory(request, result, final_spec)
        return result

    def _insert_diagram_asset_into_section(self, item: dict[str, Any]) -> dict[str, Any]:
        section_id = item.get("section_id")
        path = item.get("path")
        if not section_id or not path:
            return {"status": "skipped", "reason": "Missing section_id or path."}
        existing = self.repository.load_latex_section(section_id)
        if path in existing:
            return {"status": "skipped", "reason": "Diagram path already present.", "path": path}
        description = item.get("description") or "Generated diagram"
        block = self._diagram_latex_block(path, description)
        updated = existing.rstrip() + "\n\n" + block + "\n"
        target = self.repository.save_latex_section(section_id, updated)
        event = self.loop.history.record_event(
            event_type="diagram_inserted",
            agent_id=AGENT_IDS["diagram"],
            subject=section_id,
            status="pass",
            rationale=f"Inserted diagram asset {path} into section LaTeX.",
            metadata={"path": path, "target": str(target.relative_to(self.book_root))},
        )
        self.commit_log.record(
            AGENT_IDS["diagram"],
            "insert_diagram_asset",
            section_id,
            description,
            {"path": path, "target": str(target.relative_to(self.book_root)), "event_id": event["event_id"]},
        )
        return {"status": "inserted", "path": path, "target": str(target.relative_to(self.book_root))}

    def _diagram_latex_block(self, path: str, description: str) -> str:
        caption = self._escape_tex(description).rstrip(".")
        if path.endswith(".tikz"):
            body = f"\\centering\n\\input{{{path}}}"
        else:
            body = f"\\centering\n\\includegraphics[width=0.82\\linewidth]{{{path}}}"
        return (
            "\\begin{figure}[!htbp]\n"
            f"{body}\n"
            f"\\caption{{{caption}.}}\n"
            "\\end{figure}"
        )

    def review_document_design(self, compile_result: dict[str, Any] | CompileResult | None = None) -> dict[str, Any]:
        """Inspect compile results and propose class/style fixes when needed."""
        if isinstance(compile_result, CompileResult):
            result = compile_result.as_dict()
        elif compile_result is None:
            result = self._latest_compile_result()
        else:
            result = compile_result

        errors = result.get("errors") or []
        if result.get("status") == "passed" and not errors:
            event = self.loop.history.record_event(
                event_type="document_design_review",
                agent_id=AGENT_IDS["document_design"],
                subject="document",
                status="pass",
                rationale="Compiled PDF is available and no LaTeX errors were reported.",
                metadata={"compile": result},
            )
            return {"status": "pass", "event": event, "proposal": None}

        proposed = self._style_fix_content(result)
        proposal = self.loop.proposals.propose_file_edit(
            agent_id=AGENT_IDS["document_design"],
            target_path=Path("style") / "document_design_fixes.tex",
            proposed_content=proposed,
            rationale="Proposed class/style fixes after compile inspection.",
            metadata={"compile": result, "kind": "document_design_fix"},
            mode=self.mode,
        )
        event = self.loop.history.record_event(
            event_type="document_design_review",
            agent_id=AGENT_IDS["document_design"],
            subject="document",
            status="fail",
            rationale="Compile output needs document design or class/style attention.",
            metadata={"proposal_id": proposal.proposal_id, "compile": result},
        )
        self.commit_log.record(
            AGENT_IDS["document_design"],
            "review_compile",
            "document",
            "Proposed class/style fixes after compile inspection.",
            {"proposal_id": proposal.proposal_id, "errors": errors},
        )
        return {"status": "fail", "event": event, "proposal": proposal.__dict__}

    def _definition_path(self, role: str) -> Path:
        filename = AGENT_DEFINITION_FILES[role]
        return self.project_root / "scripts" / "agents" / "agent_definitions" / filename

    def _validate_agent_action(self, agent_id: str, action_id: str) -> None:
        runtime = self.runtime.list().get(agent_id)
        if not runtime:
            raise KeyError(f"Agent has not been spawned: {agent_id}")
        definition_path = runtime.get("definition_path")
        if not definition_path:
            raise ValueError(f"Agent has no definition_path recorded: {agent_id}")
        with open(definition_path, "r") as f:
            definition = yaml.safe_load(f) or {}
        actions = {
            action.get("id")
            for action in definition.get("actions", []) or []
            if action.get("id")
        }
        if action_id not in actions:
            raise ValueError(
                f"Action {action_id!r} is not declared by {definition_path} for {agent_id}."
            )

    def _queue_supervised_work(self, section_ids: list[str]) -> list[dict[str, Any]]:
        queued = []
        queued.append(self.queue_agent_task(
            AGENT_IDS["hypervisor"],
            "summarize_drift",
            {
                "subject": "book",
                "unprocessed_chat_log_lines": self.unprocessed_chat_log_lines(),
            },
            priority=10,
        ))
        for section_id in section_ids:
            node = self.repository.outline_service().get_node(section_id) or {}
            queued.append(self.queue_agent_task(
                f"{AGENT_IDS['section']}__{section_id}",
                "draft_initial_section",
                {
                    "section_id": section_id,
                    "title": node.get("title", section_id),
                    "content_summary": node.get("summary", ""),
                    "goal": node.get("goal", ""),
                },
                priority=20,
            ))
            queued.append(self.queue_agent_task(
                AGENT_IDS["gardener"],
                "run_section_checks",
                {
                    "section_id": section_id,
                    **self._section_coherence_context(section_id),
                },
                priority=30,
            ))
        if any(request.get("status") == "pending" for request in self.loop.media.load_requests()):
            queued.append(self.queue_agent_task(
                AGENT_IDS["diagram"],
                "fulfill_media_requests",
                {},
                priority=40,
            ))
        queued.append(self.queue_agent_task(
            AGENT_IDS["document_design"],
            "review_document_design",
            {},
            priority=50,
        ))
        queued.extend(self._queue_gardener_maintenance_cycle())
        return queued

    def _queue_gardener_heartbeat(self) -> list[dict[str, Any]]:
        return self._queue_gardener_maintenance_cycle(trigger="legacy_heartbeat")

    def _queue_gardener_maintenance_cycle(self, trigger: str | None = None) -> list[dict[str, Any]]:
        runtime = self.runtime.list()
        gardener = runtime.get(AGENT_IDS["gardener"]) or {}
        has_pending_cycle = any(
            task.get("status") == "pending" and task.get("action_id") == "run_maintenance_cycle"
            for task in gardener.get("task_queue", [])
        )
        if has_pending_cycle:
            return []
        return [self.queue_agent_task(
            AGENT_IDS["gardener"],
            "run_maintenance_cycle",
            {
                "trigger": trigger or self._gardener_cycle_trigger({
                    "runtime_agent_count": len(runtime),
                }),
                "pending_media_requests": len([
                    request for request in self.loop.media.load_requests()
                    if request.get("status") == "pending"
                ]),
                "runtime_agent_count": len(runtime),
            },
            priority=60,
        )]

    def _dispatch_agent_task(self, agent_id: str, task: dict[str, Any]) -> dict[str, Any]:
        action_id = task.get("action_id")
        context = task.get("context") or {}
        task_context = {**context, "task_id": task.get("task_id")}
        if action_id == "process_message":
            return self._process_agent_message_task(agent_id, task)
        if agent_id == AGENT_IDS["hypervisor"]:
            if action_id == "summarize_drift":
                return self.summarize_drift()
            if action_id == "supervise_agents":
                return self.supervise_agents(
                    section_ids=context.get("section_ids"),
                    queue_work=bool(context.get("queue_work", True)),
                )
        if agent_id.startswith(f"{AGENT_IDS['section']}__"):
            section_id = context.get("section_id") or agent_id.split("__", 1)[1]
            if action_id == "plan_section_work":
                return self._plan_section_work(section_id, agent_id, context)
            if action_id == "draft_initial_section":
                proposal = self.draft_section(section_id, action_id=action_id, task_context=task_context)
                return {
                    "proposal_id": proposal.proposal_id,
                    "target_path": proposal.target_path,
                    "status": proposal.status,
                    "metadata": proposal.metadata,
                }
            if action_id == "coordinate_with_sibling_sections":
                return self._coordinate_section_context(section_id, context)
            if action_id == "propose_section_improvements":
                return self._propose_section_improvements(section_id, context)
            if action_id == "propose_section_visuals":
                return self._propose_section_visuals(section_id, context)
            if action_id == "do_research_on_the_web":
                return self._research_references_for_section(section_id, context)
            if action_id in {"revise_section_from_feedback", "fix_latex_compile_error"}:
                proposal = self.draft_section(section_id, action_id=action_id, task_context=task_context)
                return {
                    "proposal_id": proposal.proposal_id,
                    "target_path": proposal.target_path,
                    "status": proposal.status,
                    "metadata": {
                        **proposal.metadata,
                        "feedback": context.get("feedback", ""),
                        "phase": context.get("phase", ""),
                    },
                }
        if agent_id == AGENT_IDS["gardener"] and action_id == "run_section_checks":
            return self.run_gardener_checks(context["section_id"])
        if agent_id == AGENT_IDS["gardener"] and action_id == "run_maintenance_cycle":
            return self.run_gardener_maintenance_cycle(context)
        if agent_id == AGENT_IDS["gardener"] and action_id == "heartbeat":
            return self.run_gardener_heartbeat(context)
        if agent_id == AGENT_IDS["diagram"] and action_id == "create_diagram_asset":
            return self.create_diagram_asset(context)
        if agent_id == AGENT_IDS["diagram"] and action_id == "fulfill_media_requests":
            return {"fulfilled": self.fulfill_media_requests()}
        if agent_id == AGENT_IDS["references"] and action_id == "add_bib_entries":
            return self.add_bib_entries(context)
        if agent_id == AGENT_IDS["references"] and action_id == "request_citation_definition_support":
            return self.request_citation_definition_support(context)
        if agent_id == AGENT_IDS["document_design"] and action_id == "review_document_design":
            return self.review_document_design()
        raise ValueError(f"No dispatcher for {agent_id} action {action_id}")

    def _section_coherence_context(self, section_id: str) -> dict[str, Any]:
        for event in reversed(self.loop.history.load()):
            if event.get("subject") != section_id:
                continue
            metadata = event.get("metadata") or {}
            if "completeness_percent" in metadata:
                return {
                    "section_agent_coherence_percent": metadata.get("completeness_percent"),
                    "section_agent_coherence_rationale": metadata.get("completeness_rationale", ""),
                }
        return {
            "section_agent_coherence_percent": None,
            "section_agent_coherence_rationale": "No section-agent coherence estimate has been recorded yet.",
        }

    def _register_runtime_message_handlers(self) -> None:
        for agent_id in self.runtime.list():
            self.message_router.subscribe(
                agent_id,
                agent_id,
                lambda message, target_agent_id=agent_id: self._queue_inbound_message_task(target_agent_id, message),
            )

    def _queue_inbound_message_task(self, agent_id: str, message: dict[str, Any]) -> None:
        subject = str(message.get("subject", ""))
        if subject.startswith("Task queued:"):
            return
        priority = 0 if agent_id == AGENT_IDS["hypervisor"] and subject.startswith("LaTeX compile failed:") else 5
        context = {"message": message}
        if agent_id == AGENT_IDS["hypervisor"]:
            context["unprocessed_chat_log_lines"] = (
                self.unprocessed_chat_log_lines() + [MessageRouter.chat_line(message)]
            )[-20:]
        try:
            self.runtime.enqueue_task(
                agent_id,
                "process_message",
                context=context,
                priority=priority,
                assigned_by=message.get("from", AGENT_IDS["hypervisor"]),
                dedupe=True,
            )
        except KeyError:
            return

    def unprocessed_chat_log_lines(self, limit: int = 20) -> list[str]:
        """Return chat lines for process_message tasks not yet completed."""
        lines = []
        for record in self.runtime.list().values():
            for task in record.get("task_queue", []):
                if task.get("action_id") != "process_message":
                    continue
                if task.get("status") not in {"pending", "running"}:
                    continue
                message = (task.get("context") or {}).get("message") or {}
                lines.append(MessageRouter.chat_line(message))
        return lines[-limit:]

    def _process_agent_message_task(self, agent_id: str, task: dict[str, Any]) -> dict[str, Any]:
        message = (task.get("context") or {}).get("message") or {}
        result = {
            "agent_id": agent_id,
            "processed_message_id": message.get("message_id"),
            "subject": message.get("subject"),
            "from": message.get("from"),
            "status": "acknowledged",
        }
        if agent_id == AGENT_IDS["hypervisor"] and str(message.get("subject", "")).startswith("LaTeX compile failed:"):
            result["queued_repairs"] = self._queue_compile_failure_repairs_from_message(message)
            result["status"] = "repair_tasks_queued"
        if agent_id == AGENT_IDS["hypervisor"] and message.get("subject") == "Global editorial drift detected":
            result["queued_drift_assignments"] = self._queue_global_drift_assignments_from_message(message)
            result["status"] = "drift_assignments_queued"
        if agent_id.startswith(f"{AGENT_IDS['section']}__"):
            followup = self._queue_section_callback_followup(agent_id, message)
            if followup:
                result["queued_followup"] = followup
                result["status"] = "section_callback_followup_queued"
            plan_tasks = self._queue_section_plan_tasks_from_message(agent_id, message)
            if plan_tasks:
                result["queued_plan_tasks"] = plan_tasks
                result["status"] = "section_plan_tasks_queued"
        return result

    def _queue_section_callback_followup(
        self,
        agent_id: str,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        subject = str(message.get("subject") or "")
        from_agent = str(message.get("from") or "")
        section_id = agent_id.split("__", 1)[1]
        body = str(message.get("body") or "")
        if from_agent == AGENT_IDS["diagram"] and subject.startswith("Diagram asset ready:"):
            return self.queue_agent_task(
                agent_id,
                "revise_section_from_feedback",
                {
                    "section_id": section_id,
                    "phase": "diagram_callback",
                    "feedback": yaml.safe_dump({
                        "source": from_agent,
                        "subject": subject,
                        "message_body": body,
                        "instruction": (
                            "Process this diagram callback. Verify the asset is relevant to this section, "
                            "then include or confirm the appropriate LaTeX input/include command."
                        ),
                    }, sort_keys=False, allow_unicode=True),
                },
                priority=6,
            )
        if from_agent == AGENT_IDS["references"] and subject.startswith("References registered:"):
            return self.queue_agent_task(
                agent_id,
                "revise_section_from_feedback",
                {
                    "section_id": section_id,
                    "phase": "references_callback",
                    "feedback": yaml.safe_dump({
                        "source": from_agent,
                        "subject": subject,
                        "message_body": body,
                        "instruction": (
                            "Process this references callback. Verify registered keys exist in "
                            "references/references.bib, then cite only verified keys where they support "
                            "the section."
                        ),
                    }, sort_keys=False, allow_unicode=True),
                },
                priority=6,
            )
        return None

    def _queue_section_plan_tasks_from_message(
        self,
        agent_id: str,
        message: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if message.get("from") != agent_id:
            return []
        if not str(message.get("subject") or "").startswith("Section action plan:"):
            return []
        try:
            payload = yaml.safe_load(message.get("body") or "") or {}
        except yaml.YAMLError:
            return []
        if not isinstance(payload, dict):
            return []
        section_id = payload.get("section_id") or agent_id.split("__", 1)[1]
        queued = []
        for item in payload.get("recommended_tasks", []) or []:
            if not isinstance(item, dict):
                continue
            action_id = item.get("action_id")
            if not action_id:
                continue
            context = item.get("context") if isinstance(item.get("context"), dict) else {}
            context.setdefault("section_id", section_id)
            if action_id == "revise_section_from_feedback":
                context.setdefault("feedback", yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
            if action_id == "propose_section_visuals":
                context.setdefault("diagram_requests", payload.get("diagram_recommendations", []))
                context.setdefault("max_diagrams", 2)
            try:
                priority = int(item.get("priority", 20))
            except (TypeError, ValueError):
                priority = 20
            queued.append(self.queue_agent_task(
                agent_id,
                action_id,
                context,
                priority=priority,
            ))
        return queued

    def _plan_section_work(
        self,
        section_id: str,
        agent_id: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id) or {}
        work = self.repository.outline_service().work
        existing_latex = self.repository.load_latex_section(section_id)
        source_material = self.repository.load_section(section_id)
        document_tex = LatexBuildService(self.book_root).assembler.assemble_book()
        has_latex = bool(existing_latex.strip())
        diagram_recommendations = self._section_visual_candidates(
            section_id,
            node,
            {"max_diagrams": 2},
        )[:2]
        recommended_tasks = []
        if has_latex:
            recommended_tasks.append({
                "action_id": "coordinate_with_sibling_sections",
                "priority": 12,
                "context": {
                    "section_id": section_id,
                    "phase": "manual_introspective_plan",
                    "sibling_context": [],
                },
            })
            recommended_tasks.append({
                "action_id": "propose_section_improvements",
                "priority": 13,
                "context": {
                    "section_id": section_id,
                    "phase": "manual_introspective_plan",
                },
            })
            recommended_tasks.append({
                "action_id": "revise_section_from_feedback",
                "priority": 14,
                "context": {
                    "section_id": section_id,
                    "phase": "manual_introspective_plan",
                },
            })
        else:
            recommended_tasks.append({
                "action_id": "draft_initial_section",
                "priority": 12,
                "context": {
                    "section_id": section_id,
                    "title": node.get("title", section_id),
                    "content_summary": node.get("summary", ""),
                    "goal": node.get("goal", ""),
                    "phase": "manual_introspective_plan",
                },
            })
        if diagram_recommendations:
            recommended_tasks.append({
                "action_id": "propose_section_visuals",
                "priority": 15,
                "context": {
                    "section_id": section_id,
                    "phase": "manual_introspective_plan",
                    "diagram_requests": diagram_recommendations,
                    "max_diagrams": 2,
                },
            })
        plan = {
            "section_id": section_id,
            "section_agent_id": agent_id,
            "plan_summary": (
                "Revise existing section content from a document-level review."
                if has_latex
                else "Draft this section from outline and source context."
            ),
            "rationale": {
                "document_tex_chars": len(document_tex),
                "existing_latex_chars": len(existing_latex),
                "source_material_chars": len(source_material),
                "section_title": node.get("title", section_id),
                "section_summary": node.get("summary", ""),
                "manual_context": context,
            },
            "recommended_tasks": recommended_tasks,
            "diagram_recommendations": diagram_recommendations,
            "front_matter_diagrams_allowed": not self._is_front_matter_node(section_id, node),
        }
        self.message_router.publish({
            "from": agent_id,
            "to": agent_id,
            "reply_to": agent_id,
            "subject": f"Section action plan: {section_id}",
            "body": yaml.safe_dump(plan, sort_keys=False, allow_unicode=True),
        })
        return {
            "section_id": section_id,
            "status": "plan_sent_to_self",
            "plan": plan,
        }

    def _queue_global_drift_assignments_from_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            payload = yaml.safe_load(message.get("body") or "") or {}
        except yaml.YAMLError:
            payload = {}
        queued = []
        for assignment in payload.get("recommended_assignments", []) or []:
            agent_id = assignment.get("agent_id")
            action_id = assignment.get("action_id")
            if not agent_id or not action_id:
                continue
            if not self.runtime.list().get(agent_id):
                continue
            if agent_id.startswith(f"{AGENT_IDS['section']}__") and action_id == "revise_section_from_feedback":
                section_id = assignment.get("section_id") or agent_id.split("__", 1)[1]
                feedback = yaml.safe_dump({
                    "source": AGENT_IDS["hypervisor"],
                    "reason": "Global editorial drift detected by gardener_agent.",
                    "drift": payload,
                    "assignment": assignment,
                }, sort_keys=False, allow_unicode=True)
                queued.append(self.queue_agent_task(
                    agent_id,
                    action_id,
                    {
                        "section_id": section_id,
                        "phase": "global_drift_repair",
                        "feedback": feedback,
                    },
                    priority=3,
                ))
            elif agent_id == AGENT_IDS["references"] and action_id == "request_citation_definition_support":
                for issue in assignment.get("feedback", []) or []:
                    section_id = issue.get("section_id")
                    if not section_id:
                        continue
                    queued.append(self.queue_agent_task(
                        agent_id,
                        action_id,
                        {
                            "requesting_agent": AGENT_IDS["hypervisor"],
                            "section_id": section_id,
                            "section_agent_id": issue.get("section_agent_id") or f"{AGENT_IDS['section']}__{section_id}",
                            "support_type": issue.get("support_type", "citation"),
                            "claim_or_term": issue.get("claim_or_term", ""),
                            "context": issue.get("context", {}),
                            "gardener_issue": issue,
                        },
                        priority=4,
                    ))
        return queued

    def _queue_compile_failure_repairs_from_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            payload = yaml.safe_load(message.get("body") or "") or {}
        except yaml.YAMLError:
            payload = {"errors": [message.get("body", "")]}
        target_section_ids = [
            section_id for section_id in payload.get("target_section_ids", []) or []
            if section_id
        ]
        responsible_section_ids = [
            section_id for section_id in payload.get("responsible_section_ids", []) or []
            if section_id
        ]
        if responsible_section_ids:
            target_section_ids = responsible_section_ids
        if not target_section_ids:
            target_section_ids = self.dependency_graph()["ready"]
        errors = self._compile_error_lines(payload.get("errors") or [])
        feedback = yaml.safe_dump({
            "source": AGENT_IDS["hypervisor"],
            "reason": "Top-priority LaTeX compile failure.",
            "scope": payload.get("scope"),
            "errors": errors,
            "diagnostic_summary": payload.get("diagnostic_summary", ""),
            "responsible_section_ids": target_section_ids,
            "responsible_section_titles": payload.get("responsible_section_titles") or [],
            "log_path": payload.get("log_path"),
            "tex_path": payload.get("tex_path"),
            "instructions": (
                "This is top-priority repair work. Fix the LaTeX error(s) causing compilation to fail. "
                "Preserve useful content and make the smallest valid repair."
            ),
        }, sort_keys=False, allow_unicode=True)
        queued = []
        for section_id in dict.fromkeys(target_section_ids):
            queued.append(self.queue_agent_task(
                f"{AGENT_IDS['section']}__{section_id}",
                "fix_latex_compile_error",
                {
                    "section_id": section_id,
                    "phase": "compile_repair",
                    "feedback": feedback,
                    "diagnostic_summary": payload.get("diagnostic_summary", ""),
                    "errors": errors,
                    "log_path": payload.get("log_path"),
                    "tex_path": payload.get("tex_path"),
                },
                priority=0,
            ))
        return queued

    def _compile_error_lines(self, errors: Any) -> list[str]:
        if isinstance(errors, str):
            return [errors]
        if not isinstance(errors, list):
            errors = [errors]
        lines = []
        for error in errors:
            if isinstance(error, dict):
                lines.extend(f"{key}: {value}" for key, value in error.items())
            elif error is not None:
                lines.append(str(error))
        return lines

    def _publish_task_assignment(self, agent_id: str, task: dict[str, Any]) -> None:
        self.message_router.publish({
            "from": AGENT_IDS["hypervisor"],
            "to": agent_id,
            "reply_to": AGENT_IDS["hypervisor"],
            "subject": f"Task queued: {task.get('action_id')}",
            "body": yaml.safe_dump({
                "action_id": task.get("action_id"),
                "task_id": task.get("task_id"),
                "context": task.get("context") or {},
                "priority": task.get("priority"),
            }, sort_keys=False, allow_unicode=True),
        })

    def _publish_task_completion(self, agent_id: str, task: dict[str, Any], result: dict[str, Any]) -> None:
        action_id = task.get("action_id")
        if agent_id.startswith(f"{AGENT_IDS['section']}__") and action_id in {
            "draft_initial_section",
            "revise_section_from_feedback",
            "fix_latex_compile_error",
        }:
            section_id = (task.get("context") or {}).get("section_id") or agent_id.split("__", 1)[1]
            section_completion_payload = {
                "section_id": section_id,
                "section_agent_id": agent_id,
                "action_id": action_id,
                "task_id": task.get("task_id"),
                "result": result,
            }
            self.message_router.publish({
                "from": agent_id,
                "to": AGENT_IDS["hypervisor"],
                "reply_to": agent_id,
                "subject": f"Section task complete: {section_id}",
                "body": yaml.safe_dump({
                    **section_completion_payload,
                    "request": "Record this section-agent completion and decide whether follow-up supervision is needed.",
                }, sort_keys=False, allow_unicode=True),
            })
            self.message_router.publish({
                "from": agent_id,
                "to": AGENT_IDS["gardener"],
                "reply_to": agent_id,
                "subject": f"Section payload ready: {section_id}",
                "body": yaml.safe_dump({
                    **section_completion_payload,
                    "request": "Run gardener validation and return feedback to the section agent.",
                }, sort_keys=False, allow_unicode=True),
            })
            self._queue_section_visual_decision_after_pass(agent_id, task, section_id)
        if agent_id == AGENT_IDS["gardener"] and action_id == "run_section_checks":
            section_id = (task.get("context") or {}).get("section_id")
            if section_id:
                self.message_router.publish({
                    "from": AGENT_IDS["gardener"],
                    "to": f"{AGENT_IDS['section']}__{section_id}",
                    "reply_to": AGENT_IDS["gardener"],
                    "subject": f"Gardener feedback: {section_id}",
                    "body": yaml.safe_dump(result, sort_keys=False, allow_unicode=True),
                })
        if agent_id == AGENT_IDS["diagram"] and action_id in {"create_diagram_asset", "fulfill_media_requests"}:
            fulfilled_items = result.get("fulfilled") if isinstance(result.get("fulfilled"), list) else [result]
            for item in fulfilled_items:
                if not isinstance(item, dict) or not item.get("path"):
                    continue
                section_id = item.get("section_id")
                requesting_agent = item.get("requesting_agent") or (
                    f"{AGENT_IDS['section']}__{section_id}" if section_id else None
                )
                if not requesting_agent:
                    continue
                inserted = self._insert_diagram_asset_into_section(item) if item.get("section_id") else None
                self.message_router.publish({
                    "from": AGENT_IDS["diagram"],
                    "to": requesting_agent,
                    "reply_to": AGENT_IDS["diagram"],
                    "subject": f"Diagram asset ready: {section_id}",
                    "body": yaml.safe_dump({
                        "section_id": section_id,
                        "request_id": item.get("request_id"),
                        "path": item.get("path"),
                        "media_type": item.get("media_type"),
                        "description": item.get("description", ""),
                        "latex_hint": (
                            f"Use \\\\input{{{item.get('path')}}} for TikZ assets."
                            if str(item.get("path", "")).endswith(".tikz")
                            else f"Use \\\\includegraphics{{{item.get('path')}}} for image assets."
                        ),
                        "inserted": inserted,
                    }, sort_keys=False, allow_unicode=True),
                })

    def _queue_section_visual_decision_after_pass(
        self,
        agent_id: str,
        task: dict[str, Any],
        section_id: str,
    ) -> dict[str, Any] | None:
        action_id = task.get("action_id")
        if action_id not in {"draft_initial_section", "revise_section_from_feedback"}:
            return None
        node = self.repository.outline_service().get_node(section_id) or {}
        if self._is_front_matter_node(section_id, node):
            return None
        task_context = task.get("context") or {}
        if task_context.get("phase") in {"compile_repair", "diagram_callback"}:
            return None
        for queued in self.runtime.list().get(agent_id, {}).get("task_queue", []):
            if queued.get("status") != "pending":
                continue
            if queued.get("action_id") != "propose_section_visuals":
                continue
            queued_context = queued.get("context") or {}
            if queued_context.get("section_id") == section_id:
                return queued
        return self.queue_agent_task(
            agent_id,
            "propose_section_visuals",
            {
                "section_id": section_id,
                "phase": "post_section_pass_visual_decision",
                "after_action": action_id,
                "max_diagrams": 2,
                "instruction": (
                    "Decide whether the latest section draft/revision would benefit from 0, 1, "
                    "or 2 diagrams. If diagrams would help, queue diagram_agent:create_diagram_asset "
                    "requests with concrete descriptions. If not, return no_diagrams."
                ),
            },
            priority=25,
        )

    def _dependency_ids(self, node: dict[str, Any]) -> list[str]:
        ids = []
        for dep in node.get("dependencies", {}).get("structural", []) or []:
            dep_id = dep.get("section_id") or dep.get("id") or dep.get("target")
            if dep_id:
                ids.append(dep_id)
        for prereq in node.get("prerequisites", []) or []:
            if isinstance(prereq, str):
                ids.append(prereq)
            elif isinstance(prereq, dict):
                dep_id = prereq.get("section_id") or prereq.get("id")
                if dep_id:
                    ids.append(dep_id)
        return list(dict.fromkeys(ids))

    def _draft_section_content(
        self,
        node: dict[str, Any],
        graph_node: dict[str, Any],
    ) -> tuple[str, Any | None]:
        return self._section_task_content(node, graph_node, "draft_initial_section", {})

    def _section_task_content(
        self,
        node: dict[str, Any],
        graph_node: dict[str, Any],
        action_id: str,
        task_context: dict[str, Any],
    ) -> tuple[str, Any | None]:
        if self.llm_mode == "never":
            if action_id in {"revise_section_from_feedback", "fix_latex_compile_error"}:
                existing = self.repository.load_latex_section(node.get("id", "")).strip()
                return (existing + "\n") if existing else self._section_tex(node, graph_node), None
            return self._section_tex(node, graph_node), None
        prompt = (
            self._section_revision_prompt(node, graph_node, action_id, task_context)
            if action_id in {"revise_section_from_feedback", "fix_latex_compile_error"}
            else self._section_draft_prompt(node, graph_node)
        )
        system_prompt = (
            "You are the section revision agent for the Codynamic Book Machine. "
            "Return only valid LaTeX body content for the requested section. "
            "Do not wrap the answer in Markdown fences. Use the provided feedback as binding task context. "
            "Preserve useful existing LaTeX and make the smallest change that satisfies the feedback."
            if action_id in {"revise_section_from_feedback", "fix_latex_compile_error"}
            else
            "You are the section authoring agent for the Codynamic Book Machine. "
            "Return only valid LaTeX body content for the requested section. "
            "Do not wrap the answer in Markdown fences. Preserve proposal-first discipline: "
            "write draft content for human review, not final claims of completion."
        )
        section_id = node.get("id", "")
        response = self._call_agent_provider(
            f"{AGENT_IDS['section']}__{section_id}",
            prompt=prompt,
            system_prompt=system_prompt,
            action_id=action_id,
            task_id=task_context.get("task_id"),
            model=self.model,
            temperature=0.2 if action_id in {"revise_section_from_feedback", "fix_latex_compile_error"} else 0.35,
            max_tokens=2200,
        )
        return self._clean_llm_tex(response.content), response

    def _coordinate_section_context(self, section_id: str, context: dict[str, Any]) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id) or {}
        sibling_context = context.get("sibling_context") or []
        return {
            "section_id": section_id,
            "title": node.get("title", section_id),
            "status": "complete",
            "coordination_notes": (
                "Reviewed sibling context for scope, continuity, and style. "
                "Use these notes as context for propose_section_improvements or revise_section_from_feedback."
            ),
            "sibling_context": sibling_context,
        }

    def _propose_section_improvements(self, section_id: str, context: dict[str, Any]) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id) or {}
        existing_latex = self.repository.load_latex_section(section_id)
        source = self.repository.load_section(section_id)
        feedback = yaml.safe_dump({
            "source": f"{AGENT_IDS['section']}__{section_id}",
            "action": "propose_section_improvements",
            "section_id": section_id,
            "title": node.get("title", section_id),
            "proposal": (
                "Revise the current section against the supplied outline intent, source material, "
                "sibling context, and any gardener or diagram feedback. Preserve working LaTeX and "
                "make concrete improvements rather than replacing the section wholesale."
            ),
            "current_latex_chars": len(existing_latex),
            "source_chars": len(source),
            "context": context,
        }, sort_keys=False, allow_unicode=True)
        return {
            "section_id": section_id,
            "status": "complete",
            "feedback": feedback,
            "recommended_next_action": "revise_section_from_feedback",
        }

    def _propose_section_visuals(self, section_id: str, context: dict[str, Any]) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id) or {}
        candidates = self._section_visual_candidates(section_id, node, context)
        max_diagrams = self._max_diagram_count(context.get("max_diagrams", 2))
        media_type = context.get("media_type") or "tikz"
        selected = candidates[:max_diagrams]
        tasks = [
            self.queue_agent_task(
                AGENT_IDS["diagram"],
                "create_diagram_asset",
                {
                    "section_id": section_id,
                    "requesting_agent": f"{AGENT_IDS['section']}__{section_id}",
                    "media_type": candidate.get("media_type", media_type),
                    "description": candidate["description"],
                    "diagram_spec": candidate.get("diagram_spec"),
                    "insert_into_section": bool(context.get("insert_into_section", True)),
                },
                priority=context.get("priority", 15),
            )
            for candidate in selected
        ]
        return {
            "section_id": section_id,
            "status": "queued" if tasks else "no_diagrams",
            "description": selected[0]["description"] if selected else "",
            "decision_rationale": (
                f"Queued {len(tasks)} diagram request(s)."
                if tasks
                else "No diagram would materially improve this section pass."
            ),
            "media_type": media_type,
            "diagram_count": len(tasks),
            "diagram_tasks": tasks,
            "diagram_task": tasks[0] if tasks else None,
        }

    def _max_diagram_count(self, raw_value: Any) -> int:
        try:
            count = int(raw_value)
        except (TypeError, ValueError):
            count = 2
        return max(0, min(2, count))

    def _section_visual_candidates(
        self,
        section_id: str,
        node: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, str]]:
        if self._is_front_matter_node(section_id, node):
            return []
        explicit = context.get("diagrams") or context.get("diagram_requests") or []
        if isinstance(explicit, (str, dict)):
            explicit = [explicit]
        candidates = []
        for item in explicit:
            if isinstance(item, str):
                description = item.strip()
                media_type = context.get("media_type") or "tikz"
            elif isinstance(item, dict):
                description = str(item.get("description") or item.get("prompt") or "").strip()
                media_type = str(item.get("media_type") or context.get("media_type") or "tikz")
            else:
                continue
            if description:
                candidate = {"description": description, "media_type": media_type}
                if isinstance(item, dict) and isinstance(item.get("diagram_spec"), dict):
                    candidate["diagram_spec"] = item["diagram_spec"]
                candidates.append(candidate)
        if candidates:
            return candidates
        if context.get("description"):
            return [{"description": str(context["description"]), "media_type": context.get("media_type") or "tikz"}]
        if not self._section_visual_would_help(section_id, node):
            return []
        return [{"description": self._default_diagram_description(section_id, node), "media_type": context.get("media_type") or "tikz"}]

    def _section_visual_would_help(self, section_id: str, node: dict[str, Any]) -> bool:
        if self._is_front_matter_node(section_id, node):
            return False
        existing_latex = self.repository.load_latex_section(section_id)
        if "media/diagrams/" in existing_latex or "\\includegraphics" in existing_latex or "\\input{media/diagrams/" in existing_latex:
            return False
        if any(request.get("section_id") == section_id for request in self.loop.media.load_requests()):
            return False
        source = self.repository.load_section(section_id)
        text = " ".join(str(value or "") for value in [
            node.get("title"),
            node.get("summary"),
            node.get("goal"),
            source,
            existing_latex,
        ]).lower()
        abstract_mentions = [
            "diagram agent",
            "diagram memory",
            "diagram request",
            "diagram requests",
            "diagram support",
            "diagram generation",
            "generated diagram",
        ]
        if any(mention in text for mention in abstract_mentions) and not any(
            term in text
            for term in [
                "architecture",
                "dependency graph",
                "feedback loop",
                "message flow",
                "pipeline",
                "queue flow",
                "state surface",
            ]
        ):
            return False
        structural_terms = [
            "architecture",
            "artifact pipeline",
            "callback",
            "dependency",
            "feedback loop",
            "lifecycle",
            "message flow",
            "pipeline",
            "queue",
            "runtime state",
            "state surface",
            "workflow",
        ]
        visual_verbs = [
            "compare",
            "connect",
            "coordinate",
            "depends",
            "flows",
            "handoff",
            "loop",
            "maps",
            "passes",
            "routes",
            "transitions",
        ]
        if "diagram of" in text and any(term in text for term in structural_terms):
            return True
        return any(term in text for term in structural_terms) and any(verb in text for verb in visual_verbs)

    def _is_front_matter_node(self, section_id: str, node: dict[str, Any]) -> bool:
        matter = str(node.get("matter") or node.get("section_matter") or "").lower()
        if matter in {"main", "main_matter", "back", "back_matter", "appendix", "appendices"}:
            return False
        if matter in {"front", "front_matter"}:
            return True
        front_ids = self._front_matter_ids()
        if section_id in front_ids or node.get("id") in front_ids:
            return True
        content_file = str(node.get("content_file") or "").lower()
        if "/front_matter/" in content_file or content_file.startswith("front_matter/"):
            return True
        title = str(node.get("title") or section_id).strip().lower().replace("-", "_").replace(" ", "_")
        conventional_front = {
            "abstract",
            "title_page",
            "table_of_contents",
            "toc",
            "dedication",
            "epigraph",
            "foreword",
            "preface",
            "acknowledgements",
            "acknowledgments",
        }
        return section_id in conventional_front or title in conventional_front

    def _front_matter_ids(self) -> set[str]:
        front = self.repository.outline_service().work.get("front_matter") or {}
        ids: set[str] = set()
        if isinstance(front, list):
            for item in front:
                if isinstance(item, str):
                    ids.add(item)
                elif isinstance(item, dict):
                    ids.update(str(value) for key, value in item.items() if key in {"id", "section_id"} and value)
        elif isinstance(front, dict):
            for key, value in front.items():
                ids.add(str(key))
                if isinstance(value, dict):
                    ids.update(str(value[item_key]) for item_key in {"id", "section_id"} if value.get(item_key))
        return ids

    def _default_diagram_description(self, section_id: str, node: dict[str, Any]) -> str:
        title = node.get("title", section_id)
        summary = node.get("summary") or node.get("goal") or ""
        source = self.repository.load_section(section_id).strip()
        basis = summary or source[:240] or title
        return f"Create one section-specific visual for '{title}' that clarifies the highest-value structure in this section: {basis}"

    def _research_references_for_section(self, section_id: str, context: dict[str, Any]) -> dict[str, Any]:
        entries = context.get("entries") or context.get("candidate_entries") or []
        if isinstance(entries, dict):
            entries = [entries]
        result = {
            "section_id": section_id,
            "status": "complete" if entries else "needs_research",
            "research_topic": context.get("research_topic", ""),
            "claim_or_need": context.get("claim_or_need", ""),
            "candidate_entry_count": len(entries),
            "queued_reference_registration": None,
        }
        if entries:
            task = self.queue_agent_task(
                AGENT_IDS["references"],
                "add_bib_entries",
                {
                    "requesting_agent": f"{AGENT_IDS['section']}__{section_id}",
                    "section_id": section_id,
                    "entries": entries,
                },
                priority=10,
            )
            self.message_router.publish({
                "from": f"{AGENT_IDS['section']}__{section_id}",
                "to": AGENT_IDS["references"],
                "reply_to": f"{AGENT_IDS['section']}__{section_id}",
                "subject": f"Reference candidates ready: {section_id}",
                "body": yaml.safe_dump({
                    "section_id": section_id,
                    "entries": entries,
                    "task_id": task.get("task_id"),
                    "request": "Register these candidate references in the shared bibliography.",
                }, sort_keys=False, allow_unicode=True),
            })
            result["queued_reference_registration"] = task
        return result

    def add_bib_entries(self, context: dict[str, Any]) -> dict[str, Any]:
        entries = context.get("entries") or []
        if isinstance(entries, dict):
            entries = [entries]
        bib_path = self.book_root / "references" / "references.bib"
        bib_path.parent.mkdir(parents=True, exist_ok=True)
        existing_bib = bib_path.read_text() if bib_path.exists() else ""
        existing_keys = set(self._bib_keys(existing_bib))
        book = self.repository.load_book()
        citations = book["work"].setdefault("citations", {}).setdefault("entries", [])
        citation_ids = {entry.get("id") for entry in citations if entry.get("id")}
        registered = []
        rejected = []
        additions = []
        for raw_entry in entries:
            normalized = self._normalize_reference_entry(raw_entry)
            key = normalized.get("id")
            bibtex = normalized.get("bibtex", "").strip()
            if not key or not bibtex:
                rejected.append({"entry": raw_entry, "reason": "Missing citation key or BibTeX content."})
                continue
            if key not in existing_keys:
                additions.append(bibtex.rstrip() + "\n")
                existing_keys.add(key)
            if key not in citation_ids:
                citations.append({
                    "id": key,
                    "title": normalized.get("title", key),
                    "author": normalized.get("author", ""),
                    "year": normalized.get("year", ""),
                    "source": "references_agent",
                    "bib_path": "references/references.bib",
                })
                citation_ids.add(key)
            registered.append(key)
        if additions:
            separator = "\n" if existing_bib and not existing_bib.endswith("\n\n") else ""
            bib_path.write_text(existing_bib + separator + "\n".join(additions))
            self.repository.save_book(book)
        elif registered:
            self.repository.save_book(book)
        result = {
            "status": "complete",
            "registered_keys": registered,
            "rejected": rejected,
            "bib_path": str(bib_path.relative_to(self.book_root)),
            "section_id": context.get("section_id"),
        }
        requesting_agent = context.get("requesting_agent")
        if requesting_agent:
            self.message_router.publish({
                "from": AGENT_IDS["references"],
                "to": requesting_agent,
                "reply_to": AGENT_IDS["references"],
                "subject": f"References registered: {context.get('section_id', 'book')}",
                "body": yaml.safe_dump(result, sort_keys=False, allow_unicode=True),
            })
        self.loop.history.record_event(
            event_type="references_registered",
            agent_id=AGENT_IDS["references"],
            subject=context.get("section_id") or "book",
            status="pass" if registered else "warn",
            rationale=f"Registered {len(registered)} reference key(s).",
            metadata=result,
        )
        return result

    def request_citation_definition_support(self, context: dict[str, Any]) -> dict[str, Any]:
        """Ask the relevant section agent to retrieve citation or definition support."""
        section_id = context.get("section_id")
        if not section_id:
            raise ValueError("request_citation_definition_support requires section_id.")
        section_agent_id = context.get("section_agent_id") or f"{AGENT_IDS['section']}__{section_id}"
        support_type = context.get("support_type") or "citation"
        claim_or_term = context.get("claim_or_term") or ""
        support_context = context.get("context") or {}
        retrieval_context = {
            "source": AGENT_IDS["references"],
            "requested_by": context.get("requesting_agent") or AGENT_IDS["gardener"],
            "section_id": section_id,
            "support_type": support_type,
            "claim_or_term": claim_or_term,
            "gardener_issue": context.get("gardener_issue", {}),
            "link_targets": support_context.get("link_targets", []),
            "raw_text_needed": support_context.get("raw_text_needed", ""),
            "claim_text": claim_or_term if support_type == "citation" else "",
            "term_text": claim_or_term if support_type == "definition" else "",
            "intended_use": support_context.get("intended_use", ""),
            "instructions": (
                "Retrieve citation or definition support with enough context for references_agent "
                "to validate and register the source. Return candidate BibTeX entries, structured "
                "reference metadata, source links, or raw definition text as appropriate."
            ),
        }
        task = self.queue_agent_task(
            section_agent_id,
            "do_research_on_the_web",
            {
                "section_id": section_id,
                "research_topic": f"{support_type} support for {claim_or_term}".strip(),
                "claim_or_need": yaml.safe_dump(retrieval_context, sort_keys=False, allow_unicode=True),
                "requested_by": AGENT_IDS["references"],
            },
            priority=8,
        )
        self.message_router.publish({
            "from": AGENT_IDS["references"],
            "to": section_agent_id,
            "reply_to": AGENT_IDS["references"],
            "subject": f"Retrieve {support_type} support: {section_id}",
            "body": yaml.safe_dump({
                **retrieval_context,
                "task_id": task.get("task_id"),
            }, sort_keys=False, allow_unicode=True),
        })
        result = {
            "status": "section_agent_notified",
            "section_id": section_id,
            "section_agent_id": section_agent_id,
            "support_type": support_type,
            "claim_or_term": claim_or_term,
            "queued_task": task,
        }
        self.loop.history.record_event(
            event_type="reference_support_requested",
            agent_id=AGENT_IDS["references"],
            subject=section_id,
            status="warn",
            rationale=f"Requested {support_type} support retrieval from {section_agent_id}.",
            metadata=result,
        )
        return result

    def _registered_reference_context(self) -> dict[str, Any]:
        bib_rel_path = "references/references.bib"
        bib_path = self.book_root / bib_rel_path
        bibtex = bib_path.read_text() if bib_path.exists() else ""
        book = self.repository.load_book()
        citations = (
            book.get("work", {})
            .get("citations", {})
            .get("entries", [])
        )
        return {
            "bib_path": bib_rel_path,
            "registered_keys": self._bib_keys(bibtex),
            "bibtex": bibtex,
            "canonical_entries": citations,
        }

    def _bib_keys(self, bibtex: str) -> list[str]:
        import re

        return re.findall(r"@\w+\s*\{\s*([^,\s]+)", bibtex)

    def _normalize_reference_entry(self, entry: Any) -> dict[str, Any]:
        if isinstance(entry, str):
            key = self._bib_keys(entry)
            return {"id": key[0] if key else "", "bibtex": entry}
        if not isinstance(entry, dict):
            return {}
        bibtex = str(entry.get("bibtex") or "").strip()
        key = entry.get("id") or entry.get("key") or (self._bib_keys(bibtex) or [""])[0]
        if not bibtex and key:
            title = str(entry.get("title") or key)
            author = str(entry.get("author") or "")
            year = str(entry.get("year") or "")
            entry_type = str(entry.get("type") or "misc")
            fields = [f"  title = {{{title}}}"]
            if author:
                fields.append(f"  author = {{{author}}}")
            if year:
                fields.append(f"  year = {{{year}}}")
            if entry.get("url"):
                fields.append(f"  url = {{{entry['url']}}}")
            bibtex = f"@{entry_type}{{{key},\n" + ",\n".join(fields) + "\n}"
        return {
            "id": str(key),
            "bibtex": bibtex,
            "title": entry.get("title"),
            "author": entry.get("author"),
            "year": entry.get("year"),
        }

    def _get_provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = get_provider(self.provider_name, default_model=self.model)
        return self._provider

    def _call_agent_provider(
        self,
        agent_id: str,
        *,
        prompt: str,
        system_prompt: str,
        action_id: str | None = None,
        task_id: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call an LLM provider with durable per-agent session context."""
        provider = self._get_provider()
        messages = self.session_store.build_messages(
            agent_id,
            system_prompt=system_prompt,
            user_prompt=prompt,
        )
        call = getattr(provider, "call", None)
        if callable(call):
            response = call(messages=messages, **kwargs)
        else:
            response = provider.simple_prompt(
                prompt=self._prompt_with_session_context(messages, prompt),
                system_prompt=system_prompt,
                **kwargs,
            )
        self.session_store.record_exchange(
            agent_id,
            user_prompt=prompt,
            response=response,
            task_id=task_id,
            action_id=action_id,
            metadata={"provider_kwargs": kwargs},
        )
        return response

    def _prompt_with_session_context(self, messages: list[Any], prompt: str) -> str:
        prior = [
            f"{message.role}: {message.content}"
            for message in messages[1:-1]
            if getattr(message, "content", "").strip()
        ]
        if not prior:
            return prompt
        return (
            "Persistent session context for this agent:\n"
            + "\n\n".join(prior)
            + "\n\nCurrent task:\n"
            + prompt
        )

    def _section_draft_prompt(self, node: dict[str, Any], graph_node: dict[str, Any]) -> str:
        section_id = node.get("id", "")
        dependencies = graph_node.get("dependencies") or []
        dependency_payloads = {
            dep_id: self.repository.load_section(dep_id)[:1800]
            for dep_id in dependencies
            if self.repository.load_section(dep_id).strip()
        }
        current_payload = self.repository.load_section(section_id)
        graph_analysis = self.repository.knowledge_graph().analyze().as_dict()
        relevant_graph = {
            "missing_citations": [
                item for item in graph_analysis.get("missing_citations", [])
                if item.get("section_id") == section_id
            ],
            "orphan_claims": [
                item for item in graph_analysis.get("orphan_claims", [])
                if item.get("section_id") == section_id
            ],
            "invalid_dependencies": [
                item for item in graph_analysis.get("invalid_dependencies", [])
                if item.get("section_id") == section_id
            ],
            "dependency_node": graph_node,
        }
        work = self.repository.outline_service().work
        context = {
            "book": {
                "title": work.get("title", ""),
                "summary": work.get("summary", ""),
                "intent": work.get("intent", {}),
            },
            "section": {
                "id": section_id,
                "title": node.get("title", ""),
                "summary": node.get("summary", ""),
                "goal": node.get("goal", ""),
                "prerequisites": node.get("prerequisites", []),
                "key_concepts": node.get("key_concepts", []),
                "citations": node.get("citations", []),
            },
            "dependencies": dependencies,
            "dependency_payloads": dependency_payloads,
            "current_payload": current_payload[:2400],
            "graph_diagnostics": relevant_graph,
            "registered_references": self._registered_reference_context(),
        }
        return (
            "Draft a LaTeX section payload for this canonical book node.\n\n"
            "Requirements:\n"
            "- Begin with exactly one \\section{...} heading using the section title.\n"
            "- Write rigorous but provisional technical prose suitable for an early book draft.\n"
            "- Use citations only when a concrete citation key is supplied in the context.\n"
            "- Avoid TODO placeholders and avoid inventing bibliography keys.\n"
            "- Include short paragraphs and, where useful, displayed equations or definitions.\n"
            "- If dependencies are missing or diagnostics are present, acknowledge the limitation in prose.\n\n"
            "Structured context:\n"
            f"{json.dumps(context, indent=2, sort_keys=True)}"
        )

    def _section_revision_prompt(
        self,
        node: dict[str, Any],
        graph_node: dict[str, Any],
        action_id: str,
        task_context: dict[str, Any],
    ) -> str:
        section_id = node.get("id", "")
        existing_latex = self.repository.load_latex_section(section_id)
        source_material = self.repository.load_section(section_id)
        work = self.repository.outline_service().work
        context = {
            "action_id": action_id,
            "task_context": task_context,
            "book": {
                "title": work.get("title", ""),
                "summary": work.get("summary", ""),
                "intent": work.get("intent", {}),
                "structure": work.get("structure", []),
            },
            "section": {
                "id": section_id,
                "title": node.get("title", ""),
                "summary": node.get("summary", ""),
                "goal": node.get("goal", ""),
                "prerequisites": node.get("prerequisites", []),
                "key_concepts": node.get("key_concepts", []),
                "citations": node.get("citations", []),
            },
            "dependency_node": graph_node,
            "source_material": source_material[:3000],
            "existing_latex": existing_latex[:6000],
            "registered_references": self._registered_reference_context(),
        }
        if action_id == "fix_latex_compile_error":
            instructions = [
                "Repair the concrete LaTeX compiler failure described in task_context.",
                "Make the smallest local body-level change that fixes the error.",
                "Do not rewrite for style, coherence, or completeness.",
                "Do not require new preamble packages when a local LaTeX replacement is possible.",
            ]
        else:
            instructions = [
                "Revise the section using the specific feedback in task_context.",
                "If task_context contains a prior propose_section_improvements result, treat its feedback as the revision brief.",
                "If task_context contains a routed message, apply it only if it is relevant to this section.",
                "Preserve useful existing LaTeX and avoid wholesale replacement unless the feedback requires it.",
            ]
        return (
            f"Revise the LaTeX body for section {section_id}.\n\n"
            "Requirements:\n"
            "- Return LaTeX body content only, with no Markdown fence.\n"
            "- Do not include documentclass, preamble, \\begin{document}, or \\end{document}.\n"
            "- Do not include a duplicated top-level \\section or \\subsection heading.\n"
            + "".join(f"- {item}\n" for item in instructions)
            + "\nStructured revision context:\n"
            f"{json.dumps(context, indent=2, sort_keys=True)}"
        )

    def _clean_llm_tex(self, content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        return stripped + "\n"

    def _llm_metadata(self, response: Any | None) -> dict[str, Any]:
        if response is None:
            return {"mode": self.llm_mode, "used": False}
        return {
            "mode": self.llm_mode,
            "used": True,
            "provider": response.provider,
            "model": response.model,
            "tokens_used": response.tokens_used,
            "latency_ms": response.latency_ms,
            "metadata": response.metadata or {},
        }

    def _section_tex(self, node: dict[str, Any], graph_node: dict[str, Any]) -> str:
        title = node.get("title", "Untitled section")
        summary = node.get("summary") or "This section needs a focused draft."
        goal = node.get("goal") or "Clarify the section's intent for the reader."
        dependencies = graph_node.get("dependencies") or []
        dependency_text = ", ".join(dependencies) if dependencies else "none"
        return (
            f"% Agent draft for {node.get('id')}\n"
            f"% Dependencies: {dependency_text}\n\n"
            f"\\section{{{self._escape_tex(title)}}}\n\n"
            f"{self._escape_tex(summary)}\n\n"
            f"\\paragraph{{Intent.}}\n"
            f"{self._escape_tex(goal)}\n\n"
            "\\paragraph{Draft notes.}\n"
            "TODO: Replace this scaffold with the authored argument, examples, citations, "
            "and any requested diagrams after user review.\n"
        )

    def _claim_clarity_status(self, content: str) -> str:
        stripped = content.strip()
        if not stripped or "TODO" in stripped:
            return "warn"
        return "pass" if len(stripped.split()) >= 30 else "warn"

    def _gardener_rationale(
        self,
        checks: dict[str, str],
        missing_dependencies: list[str],
        compile_result: CompileResult,
    ) -> str:
        issues = []
        if checks["intent"] != "pass":
            issues.append("intent is underspecified")
        if missing_dependencies:
            issues.append(f"missing dependencies: {', '.join(missing_dependencies)}")
        if checks["claim_clarity"] != "pass":
            issues.append("claim clarity needs expansion")
        if checks["latex"] != "pass":
            issues.append("LaTeX compile failed")
        if not issues:
            return "Gardener checks passed for intent, dependencies, claims, and LaTeX."
        detail = "; ".join(issues)
        if compile_result.errors:
            detail += f"; first LaTeX error: {compile_result.errors[0]}"
        return detail

    def _media_extension(self, media_type: str) -> str:
        if media_type == "svg":
            return ".svg"
        if media_type in {"tikz", "diagram"}:
            return ".tikz"
        return ".txt"

    def _render_media_content(
        self,
        request: dict[str, Any],
        extension: str,
        diagram_spec: dict[str, Any],
    ) -> str:
        description = request.get("description", "Requested media")
        if extension == ".svg":
            return self._svg_for_diagram_spec(diagram_spec)
        if extension == ".tikz":
            return self._tikz_for_diagram_spec(diagram_spec)
        return f"{description}\n"

    def _render_and_review_media_content(
        self,
        request: dict[str, Any],
        extension: str,
        diagram_spec: dict[str, Any],
        max_attempts: int = 3,
    ) -> tuple[str, dict[str, Any]]:
        """Render non-image diagrams to an image preview and self-review until accepted."""
        if extension != ".tikz":
            content = self._render_media_content(request, extension, diagram_spec)
            return content, {
                "status": "skipped",
                "reason": "Media type is already image-like or does not require render review.",
                "attempts": [],
            }

        current_spec = dict(diagram_spec)
        attempts = []
        content = ""
        for attempt in range(1, max_attempts + 1):
            content = self._render_media_content(request, extension, current_spec)
            render = self.render_diagram(request, current_spec, content, attempt)
            review = self._review_rendered_diagram(
                request=request,
                diagram_spec=current_spec,
                tikz_code=content,
                render=render,
                attempt=attempt,
                max_attempts=max_attempts,
            )
            attempts.append(review)
            if review["verdict"] == "good enough":
                diagram_spec.clear()
                diagram_spec.update(current_spec)
                return content, {
                    "status": "good enough",
                    "attempts": attempts,
                    "final_attempt": attempt,
                    "preview_path": review.get("preview_path"),
                    "render": render,
                }
            current_spec = self._revise_diagram_spec_after_review(current_spec, review, attempt, request)

        diagram_spec.clear()
        diagram_spec.update(current_spec)
        return content, {
            "status": "not good enough",
            "attempts": attempts,
            "final_attempt": len(attempts),
            "preview_path": attempts[-1].get("preview_path") if attempts else None,
            "render": attempts[-1].get("render") if attempts else {},
        }

    def render_diagram(
        self,
        request: dict[str, Any],
        diagram_spec: dict[str, Any],
        tikz_code: str,
        attempt: int,
    ) -> dict[str, Any]:
        """Render TikZ through local tools when possible, with an SVG fallback preview."""
        render_dir = self.repository.book_root / "media" / "diagrams" / "renders"
        render_dir.mkdir(parents=True, exist_ok=True)
        slug = f"{request['section_id']}__{request['request_id']}__review_{attempt}"
        svg_path = render_dir / f"{slug}.svg"
        svg_path.write_text(self._svg_for_diagram_spec(diagram_spec))
        tex_path = render_dir / f"{slug}.tex"
        tex_path.write_text(
            "\n".join([
                "\\documentclass[tikz,border=6pt]{standalone}",
                "\\usetikzlibrary{arrows.meta,positioning}",
                "\\begin{document}",
                tikz_code,
                "\\end{document}",
                "",
            ])
        )
        render: dict[str, Any] = {
            "status": "fallback_svg",
            "preview_path": str(svg_path.relative_to(self.repository.book_root)),
            "fallback_preview_path": str(svg_path.relative_to(self.repository.book_root)),
            "source_path": str(tex_path.relative_to(self.repository.book_root)),
            "diagnostics": [],
        }
        compiler = find_latex_compiler("pdflatex")
        if not compiler:
            render["diagnostics"].append("No pdflatex compiler available; reviewed SVG fallback generated from DiagramSpec.")
            return render
        compiler_path = str(getattr(compiler, "path", compiler))
        try:
            completed = subprocess.run(
                [
                    compiler_path,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    f"-output-directory={render_dir}",
                    str(tex_path),
                ],
                cwd=self.repository.book_root,
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            render["diagnostics"].append(f"TikZ render command failed: {error}")
            return render
        render["command"] = completed.args
        render["stdout"] = completed.stdout[-4000:]
        render["stderr"] = completed.stderr[-4000:]
        pdf_path = render_dir / f"{slug}.pdf"
        if completed.returncode != 0 or not pdf_path.exists():
            render["status"] = "failed"
            render["diagnostics"].append("Standalone TikZ compile failed; reviewed SVG fallback instead.")
            return render
        render["pdf_path"] = str(pdf_path.relative_to(self.repository.book_root))
        converter = shutil.which("pdftoppm")
        if not converter:
            render["status"] = "compiled_pdf"
            render["preview_path"] = render["pdf_path"]
            render["diagnostics"].append("TikZ compiled to PDF; pdftoppm unavailable, so no PNG preview was created.")
            return render
        png_stem = render_dir / slug
        converted = subprocess.run(
            [converter, "-png", "-singlefile", str(pdf_path), str(png_stem)],
            cwd=self.repository.book_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        png_path = render_dir / f"{slug}.png"
        if converted.returncode == 0 and png_path.exists():
            render["status"] = "compiled_png"
            render["preview_path"] = str(png_path.relative_to(self.repository.book_root))
            return render
        render["status"] = "compiled_pdf"
        render["preview_path"] = render["pdf_path"]
        render["diagnostics"].append("TikZ compiled to PDF, but PNG conversion failed.")
        render["conversion_stdout"] = converted.stdout[-1000:]
        render["conversion_stderr"] = converted.stderr[-1000:]
        return render

    def _review_rendered_diagram(
        self,
        request: dict[str, Any],
        diagram_spec: dict[str, Any],
        tikz_code: str,
        render: dict[str, Any],
        attempt: int,
        max_attempts: int,
    ) -> dict[str, Any]:
        preview_path = str(render.get("preview_path") or render.get("fallback_preview_path") or "")
        fallback_path = str(render.get("fallback_preview_path") or preview_path)
        preview_text = (self.repository.book_root / fallback_path).read_text() if fallback_path else ""
        if self.llm_mode == "never":
            return {
                "attempt": attempt,
                "verdict": "good enough",
                "review_text": "good enough: deterministic render review accepted the generated preview.",
                "preview_path": preview_path,
                "render": render,
            }
        prompt = (
            "You are diagram_agent reviewing a rendered diagram image preview before it is returned to a section agent.\n"
            "You must begin your response with exactly one of these verdicts: good enough OR not good enough.\n"
            "Say good enough only if the rendered image is legible, non-generic, matches the request, and is suitable for LaTeX inclusion.\n"
            "Say not good enough if labels are generic, relationships are unclear, the layout is crowded, or it does not match the request.\n\n"
            f"Attempt: {attempt} of {max_attempts}\n"
            f"Section: {request.get('section_id')}\n"
            f"Request description: {request.get('description')}\n"
            f"Preview image path: {preview_path}\n"
            f"Render status and diagnostics:\n{json.dumps(render, indent=2, sort_keys=True)[:3000]}\n\n"
            f"Diagram spec:\n{json.dumps(diagram_spec, indent=2, sort_keys=True)}\n\n"
            f"Fallback SVG image markup for visual inspection:\n{preview_text[:6000]}\n\n"
            f"TikZ source:\n{tikz_code[:4000]}\n"
        )
        try:
            response = self._get_provider().simple_prompt(
                prompt=prompt,
                system_prompt=(
                    "You are a strict diagram review agent. Your first words must be exactly "
                    "'good enough' or 'not good enough'."
                ),
                model=self.model,
                temperature=0.1,
                max_tokens=500,
            )
            review_text = response.content.strip()
        except LLMProviderError as error:
            review_text = f"good enough: provider unavailable during diagram render review ({error})."
        verdict = "not good enough" if review_text.lower().startswith("not good enough") else "good enough"
        return {
            "attempt": attempt,
            "verdict": verdict,
            "review_text": review_text,
            "preview_path": preview_path,
            "render": render,
        }

    def _revise_diagram_spec_after_review(
        self,
        diagram_spec: dict[str, Any],
        review: dict[str, Any],
        attempt: int,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        brief = self._diagram_brief_for_request(request)
        rejected = {str(diagram_spec.get("diagram_kind") or "")}
        revised = self.propose_diagram_spec(brief, rejected_kinds=rejected, attempt=attempt + 1)
        similarity = self.check_diagram_similarity(revised, brief.prior_memory)
        if similarity.get("status") == "fail":
            revised = self._diversify_diagram_spec(revised, brief, similarity, attempt + 1)
            similarity = self.check_diagram_similarity(revised, brief.prior_memory)
        revised["similarity"] = similarity
        revised["why_distinct"] = (
            f"Revised after diagram self-review attempt {attempt}: "
            f"{str(review.get('review_text') or '').splitlines()[0][:180]}"
        )
        return revised

    def _attach_diagram_review(self, result: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
        requests = self.loop.media.load_requests()
        updated = dict(result)
        updated["render_review"] = review
        updated["render_preview_path"] = review.get("preview_path")
        for request in requests:
            if request.get("request_id") == result.get("request_id"):
                request["render_review"] = review
                request["render_preview_path"] = review.get("preview_path")
                break
        self.loop.media._save_requests(requests)
        return updated

    def _diagram_memory_path(self) -> Path:
        return self.repository.book_root / "media" / "diagrams" / "diagram_agent_memory.json"

    def _load_diagram_memory(self) -> list[dict[str, Any]]:
        path = self._diagram_memory_path()
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []

    def list_diagram_memory(self, section_id: str | None = None, limit: int = 12) -> list[dict[str, Any]]:
        items = self._load_diagram_memory()
        if section_id:
            items = [item for item in items if item.get("section_id") == section_id]
        return [
            {
                "section_id": item.get("section_id"),
                "path": item.get("path"),
                "description": item.get("description"),
                "purpose": item.get("purpose"),
                "diagram_kind": item.get("diagram_kind"),
                "layout": item.get("layout"),
                "nodes": item.get("nodes"),
                "edges": item.get("edges"),
                "edge_labels": [edge.get("label") for edge in item.get("edges", []) if isinstance(edge, dict)],
                "why_distinct": item.get("why_distinct"),
                "render_preview_path": item.get("render_preview_path"),
                "render_review": item.get("render_review"),
                "similarity": item.get("similarity"),
            }
            for item in items[-limit:]
        ]

    def _record_diagram_memory(
        self,
        request: dict[str, Any],
        result: dict[str, Any],
        diagram_spec: dict[str, Any],
    ) -> None:
        memory = self._load_diagram_memory()
        entry = {
            "request_id": request.get("request_id"),
            "section_id": request.get("section_id"),
            "requesting_agent": request.get("requesting_agent"),
            "path": result.get("path"),
            "description": request.get("description", ""),
            "purpose": diagram_spec.get("purpose", ""),
            "diagram_kind": diagram_spec.get("diagram_kind", ""),
            "layout": diagram_spec.get("layout", ""),
            "nodes": diagram_spec.get("nodes", []),
            "edges": diagram_spec.get("edges", []),
            "created_at": datetime.now().isoformat(),
            "why_distinct": diagram_spec.get("why_distinct", ""),
            "similarity": diagram_spec.get("similarity", {}),
            "render_review": result.get("render_review", {}),
            "render_preview_path": result.get("render_preview_path"),
        }
        memory.append(entry)
        path = self._diagram_memory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(memory, indent=2, sort_keys=True) + "\n")

    def _diagram_spec_for_request(self, request: dict[str, Any]) -> dict[str, Any]:
        brief = self._diagram_brief_for_request(request)
        explicit = request.get("diagram_spec")
        if isinstance(explicit, dict):
            spec = dict(explicit)
            spec.setdefault("purpose", request.get("description", ""))
            spec["nodes"] = self._normalize_diagram_nodes(spec.get("nodes"))
            spec["edges"] = self._normalize_diagram_edges(spec.get("edges"), spec["nodes"])
            spec.setdefault("diagram_kind", self._choose_diagram_kind(brief))
            spec.setdefault("layout", self._layout_for_kind(str(spec.get("diagram_kind"))))
            spec.setdefault("title", brief.title)
            spec["purpose"] = self._clean_diagram_label(str(spec.get("purpose") or brief.description or brief.summary), max_length=160)
        else:
            spec = self.propose_diagram_spec(brief)
        similarity = self.check_diagram_similarity(spec, brief.prior_memory)
        attempts = 0
        while similarity.get("status") == "fail" and attempts < 3:
            attempts += 1
            spec = self._diversify_diagram_spec(spec, brief, similarity, attempts)
            similarity = self.check_diagram_similarity(spec, brief.prior_memory)
        spec["similarity"] = similarity
        spec["why_distinct"] = self._diagram_distinction(spec, similarity)
        return spec

    def _diagram_brief_for_request(self, request: dict[str, Any]) -> DiagramBrief:
        section_id = str(request.get("section_id") or "")
        node = self.repository.outline_service().get_node(section_id) or {}
        return DiagramBrief(
            section_id=section_id,
            title=str(node.get("title") or self._titleize(section_id) or "Section"),
            summary=str(node.get("summary") or ""),
            goal=str(node.get("goal") or ""),
            description=str(request.get("description") or ""),
            source_material=self._clean_diagram_text(self.repository.load_section(section_id))[:3000],
            current_latex=self._clean_diagram_text(self.repository.load_latex_section(section_id))[:3000],
            prior_memory=self.list_diagram_memory(limit=12),
        )

    def propose_diagram_spec(
        self,
        brief: DiagramBrief,
        preferred_kind: str | None = None,
        rejected_kinds: set[str] | None = None,
        attempt: int = 1,
    ) -> dict[str, Any]:
        rejected_kinds = rejected_kinds or set()
        diagram_kind = preferred_kind if preferred_kind in DIAGRAM_KINDS else self._choose_diagram_kind(brief, rejected_kinds)
        terms = self._diagram_terms_from_brief(brief)
        nodes = self._nodes_for_kind(diagram_kind, terms, brief)
        edges = self._edges_for_kind(diagram_kind, nodes)
        return {
            "title": brief.title,
            "purpose": self._diagram_purpose(brief),
            "diagram_kind": diagram_kind,
            "layout": self._layout_for_kind(diagram_kind),
            "nodes": nodes,
            "edges": edges,
            "why_distinct": f"Initial {diagram_kind} proposal for {brief.section_id} attempt {attempt}.",
        }

    def check_diagram_similarity(
        self,
        spec: dict[str, Any],
        memory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        memory = memory if memory is not None else self.list_diagram_memory(limit=12)
        labels = self._normalized_label_set([node.get("label", "") for node in spec.get("nodes", []) if isinstance(node, dict)])
        edge_labels = self._normalized_label_set([edge.get("label", "") for edge in spec.get("edges", []) if isinstance(edge, dict)])
        spec_kind = str(spec.get("diagram_kind") or "")
        spec_layout = str(spec.get("layout") or "")
        nearest: dict[str, Any] | None = None
        nearest_score = 0.0
        for item in memory[-12:]:
            prior_labels = self._normalized_label_set([node.get("label", "") for node in item.get("nodes", []) if isinstance(node, dict)])
            prior_edges = self._normalized_label_set([edge.get("label", "") for edge in item.get("edges", []) if isinstance(edge, dict)])
            label_score = self._jaccard(labels, prior_labels)
            edge_score = self._jaccard(edge_labels, prior_edges)
            same_kind = bool(spec_kind and spec_kind == item.get("diagram_kind"))
            kind_bonus = 0.25 if same_kind else 0.0
            layout_bonus = 0.1 if spec_layout and spec_layout == item.get("layout") else 0.0
            score = min(1.0, label_score * 0.55 + edge_score * 0.25 + kind_bonus + layout_bonus)
            if same_kind and edge_score >= 0.4:
                score = max(score, 0.72)
            if score > nearest_score:
                nearest_score = score
                nearest = {
                    "path": item.get("path"),
                    "section_id": item.get("section_id"),
                    "diagram_kind": item.get("diagram_kind"),
                    "layout": item.get("layout"),
                    "score": round(score, 3),
                }
        status = "fail" if nearest_score >= 0.62 else "pass"
        return {
            "status": status,
            "score": round(nearest_score, 3),
            "nearest": nearest,
            "reason": (
                "Proposed diagram is too similar to recent diagram memory."
                if status == "fail"
                else "Proposed diagram is sufficiently distinct from recent diagram memory."
            ),
        }

    def _diversify_diagram_spec(
        self,
        spec: dict[str, Any],
        brief: DiagramBrief,
        similarity: dict[str, Any],
        attempt: int,
    ) -> dict[str, Any]:
        used = {str(spec.get("diagram_kind") or "")}
        nearest = similarity.get("nearest") or {}
        if nearest.get("diagram_kind"):
            used.add(str(nearest["diagram_kind"]))
        diversified = self.propose_diagram_spec(brief, rejected_kinds=used, attempt=attempt)
        diversified["why_distinct"] = (
            f"Regenerated as {diversified['diagram_kind']} after similarity gate rejected "
            f"{spec.get('diagram_kind')} with score {similarity.get('score')}."
        )
        return diversified

    def _normalize_diagram_nodes(self, raw_nodes: Any) -> list[dict[str, str]]:
        labels: list[str] = []
        if isinstance(raw_nodes, str):
            labels = [raw_nodes]
        elif isinstance(raw_nodes, list):
            for item in raw_nodes:
                if isinstance(item, dict):
                    label = str(item.get("label") or item.get("name") or item.get("id") or "").strip()
                else:
                    label = str(item or "").strip()
                if label:
                    labels.append(label)
        clean_labels = []
        for label in labels:
            clean = self._clean_diagram_label(label)
            if clean and not self._is_noise_diagram_label(clean) and clean.lower() not in {item.lower() for item in clean_labels}:
                clean_labels.append(clean)
        nodes = [{"id": f"n{index}", "label": label[:42]} for index, label in enumerate(clean_labels[:5], start=1)]
        while len(nodes) < 3:
            fallback = ["Section claim", "Mechanism", "Reader payoff"][len(nodes)]
            nodes.append({"id": f"n{len(nodes) + 1}", "label": fallback})
        return nodes

    def _normalize_diagram_edges(
        self,
        raw_edges: Any,
        nodes: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        if not isinstance(raw_edges, list):
            return self._sequential_edges(nodes)
        node_ids = {node["id"] for node in nodes}
        edges: list[dict[str, str]] = []
        for index, item in enumerate(raw_edges[:6]):
            if isinstance(item, dict):
                source = str(item.get("from") or item.get("source") or "").strip()
                target = str(item.get("to") or item.get("target") or "").strip()
                label = str(item.get("label") or item.get("relationship") or "").strip()
            else:
                source = nodes[index % len(nodes)]["id"]
                target = nodes[(index + 1) % len(nodes)]["id"]
                label = str(item or "").strip()
            if source not in node_ids:
                source = nodes[index % len(nodes)]["id"]
            if target not in node_ids:
                target = nodes[(index + 1) % len(nodes)]["id"]
            label = self._clean_diagram_label(label, max_length=28)
            if source != target:
                edges.append({"from": source, "to": target, "label": label or "supports"})
        return edges or self._sequential_edges(nodes)

    def _diagram_terms_from_brief(self, brief: DiagramBrief) -> list[str]:
        text = self._clean_diagram_text(" ".join([
            brief.title,
            brief.summary,
            brief.goal,
            brief.description,
            brief.source_material,
            brief.current_latex,
        ]))
        phrases = re.findall(r"'([^']{3,42})'|\"([^\"]{3,42})\"", text)
        terms = [first or second for first, second in phrases]
        words = [
            word
            for word in re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", text)
            if word.lower()
            not in {
                "agent",
                "agents",
                "book",
                "content",
                "context",
                "current",
                "diagram",
                "diagrams",
                "figure",
                "latex",
                "section",
                "this",
                "that",
                "with",
                "from",
                "would",
            }
        ]
        terms.extend(self._titleize(word) for word in words[:10])
        unique: list[str] = []
        for term in terms:
            clean = self._clean_diagram_label(term)
            if clean and not self._is_noise_diagram_label(clean) and clean.lower() not in {item.lower() for item in unique}:
                unique.append(clean)
            if len(unique) >= 5:
                break
        return unique or [brief.title, "Key mechanism", "Reader payoff"]

    def _nodes_for_kind(self, diagram_kind: str, terms: list[str], brief: DiagramBrief) -> list[dict[str, str]]:
        section = self._clean_diagram_label(brief.title, max_length=34) or "Section"
        first = terms[0] if terms else section
        second = terms[1] if len(terms) > 1 else "Agent handoff"
        third = terms[2] if len(terms) > 2 else "Revision artifact"
        labels_by_kind = {
            "architecture_map": [section, f"{first} surface", "Task router", "Agent workspace", "Compiled artifact"],
            "lifecycle": ["Section brief", "Draft pass", "Review signal", "Revision pass", "Stable section"],
            "dependency_graph": [f"{section} claim", f"{first} prerequisite", f"{second} constraint", "Downstream use", "Revision risk"],
            "state_surface_map": [f"{section} outline state", "Source prose", "Section TeX", "Task queue", "Build output"],
            "queue_flow": ["Specific task", "Section queue", "Agent choice", "Callback payload", "Section revision"],
            "artifact_pipeline": [f"{section} source", "Structured brief", "Generated asset", "Rendered preview", "LaTeX inclusion"],
            "comparison_matrix": [f"{first} before", f"{first} after", f"{second} tradeoff", "Revision choice"],
            "feedback_loop": [f"{section} draft", "Compile or review signal", "Responsible agent", "Targeted repair", "Verified prose"],
        }
        labels = labels_by_kind.get(diagram_kind, [section, first, second, third])
        clean_labels = []
        for label in labels:
            clean = self._clean_diagram_label(label)
            if clean and not self._is_noise_diagram_label(clean) and clean.lower() not in {item.lower() for item in clean_labels}:
                clean_labels.append(clean)
        while len(clean_labels) < 3:
            clean_labels.append(["Section claim", "Mechanism", "Reader payoff"][len(clean_labels)])
        return [{"id": f"n{index}", "label": label[:42]} for index, label in enumerate(clean_labels[:5], start=1)]

    def _edges_for_kind(
        self,
        diagram_kind: str,
        nodes: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        labels_by_kind = {
            "architecture_map": ["routes", "assigns", "persists", "renders"],
            "lifecycle": ["starts", "checks", "requests", "settles"],
            "dependency_graph": ["requires", "constrains", "informs", "pressures"],
            "state_surface_map": ["feeds", "materializes", "queues", "builds"],
            "queue_flow": ["enqueues", "selects", "returns", "revises"],
            "artifact_pipeline": ["frames", "generates", "renders", "includes"],
            "comparison_matrix": ["contrasts", "clarifies", "chooses"],
            "feedback_loop": ["signals", "assigns", "repairs", "verifies"],
        }
        labels = labels_by_kind.get(diagram_kind, ["leads to", "shapes", "supports", "stabilizes"])
        edges = []
        for index in range(len(nodes) - 1):
            edges.append({"from": nodes[index]["id"], "to": nodes[index + 1]["id"], "label": labels[index % len(labels)]})
        if diagram_kind in {"feedback_loop", "dependency_graph"} and len(nodes) >= 4:
            edges.append({"from": nodes[0]["id"], "to": nodes[-1]["id"], "label": labels[-1]})
        return edges

    def _sequential_edges(self, nodes: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            {"from": nodes[index]["id"], "to": nodes[index + 1]["id"], "label": "supports"}
            for index in range(len(nodes) - 1)
        ]

    def _select_diagram_layout(self, request: dict[str, Any], nodes: list[dict[str, str]]) -> str:
        previous = self._load_diagram_memory()
        used_layouts = [str(item.get("layout") or "") for item in previous[-4:]]
        description = str(request.get("description") or "").lower()
        if any(term in description for term in ["loop", "feedback", "cycle", "callback"]):
            preferred = "cycle"
        elif any(term in description for term in ["dependency", "graph", "sibling"]):
            preferred = "diamond"
        elif len(nodes) >= 5:
            preferred = "stack"
        else:
            preferred = "flow"
        layouts = ["flow", "diamond", "stack", "cycle"]
        if used_layouts and all(layout == preferred for layout in used_layouts[-2:]):
            return layouts[(layouts.index(preferred) + 1) % len(layouts)]
        return preferred

    def _choose_diagram_kind(self, brief: DiagramBrief, rejected_kinds: set[str] | None = None) -> str:
        rejected_kinds = rejected_kinds or set()
        text = " ".join([brief.title, brief.summary, brief.goal, brief.description, brief.source_material]).lower()
        signals = [
            ("feedback_loop", ["feedback", "loop", "repair", "review", "compile error"]),
            ("queue_flow", ["queue", "callback", "task", "message"]),
            ("artifact_pipeline", ["artifact", "render", "preview", "compile", "latex inclusion", "diagram"]),
            ("dependency_graph", ["dependency", "depends", "prerequisite", "downstream"]),
            ("state_surface_map", ["state", "surface", "repository", "runtime"]),
            ("architecture_map", ["architecture", "component", "system"]),
            ("lifecycle", ["lifecycle", "cycle", "phase", "pass"]),
            ("comparison_matrix", ["compare", "tradeoff", "versus", "contrast"]),
        ]
        recent_kinds = [str(item.get("diagram_kind") or "") for item in brief.prior_memory[-4:]]
        for kind, terms in signals:
            if kind not in rejected_kinds and any(term in text for term in terms):
                if recent_kinds[-2:].count(kind) < 2:
                    return kind
        for kind in DIAGRAM_KINDS:
            if kind not in rejected_kinds and kind not in recent_kinds[-2:]:
                return kind
        return next((kind for kind in DIAGRAM_KINDS if kind not in rejected_kinds), DIAGRAM_KINDS[0])

    def _layout_for_kind(self, diagram_kind: str) -> str:
        return {
            "architecture_map": "diamond",
            "comparison_matrix": "stack",
            "dependency_graph": "diamond",
            "feedback_loop": "cycle",
            "lifecycle": "flow",
            "queue_flow": "flow",
            "artifact_pipeline": "flow",
            "state_surface_map": "diamond",
        }.get(diagram_kind, "flow")

    def _diagram_purpose(self, brief: DiagramBrief) -> str:
        raw = brief.description or brief.summary or brief.goal or f"Clarify {brief.title}."
        first_sentence = re.split(r"(?<=[.!?])\s+", raw.strip())[0]
        return self._clean_diagram_label(first_sentence, max_length=160)

    def _diagram_distinction(self, spec: dict[str, Any], similarity: dict[str, Any] | None = None) -> str:
        previous = self._load_diagram_memory()
        if not previous:
            return "First recorded diagram for this book."
        if similarity and similarity.get("status") == "pass":
            return (
                f"Passes diversity gate as {spec.get('diagram_kind')} with nearest score "
                f"{similarity.get('score')}."
            )
        prior_labels = {
            node.get("label", "").lower()
            for item in previous[-6:]
            for node in item.get("nodes", [])
            if isinstance(node, dict)
        }
        labels = {node.get("label", "").lower() for node in spec.get("nodes", [])}
        new_labels = sorted(label for label in labels - prior_labels if label)
        if new_labels:
            return f"Uses distinct section-specific labels: {', '.join(new_labels[:3])}."
        return f"Varies diagram kind as {spec.get('diagram_kind', 'unknown')} to avoid repeating prior diagrams."

    def _clean_diagram_text(self, text: str) -> str:
        cleaned_lines = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            key = line.split(":", 1)[0].strip().strip('"{}[]').lower()
            key = key.replace("-", "_").replace(" ", "_")
            if key in DIAGRAM_NOISE_TERMS:
                continue
            if re.match(r'["\']?(latex_body|completeness_percent|completeness_rationale|task_id|agent_id)["\']?\s*[:=]', line, re.I):
                continue
            cleaned_lines.append(raw_line)
        return "\n".join(cleaned_lines)

    def _clean_diagram_label(self, label: str, max_length: int = 42) -> str:
        clean = re.sub(r"[_{}\\]+", " ", str(label or ""))
        clean = re.sub(r"\s+", " ", clean).strip(" .:;,-")
        if self._is_noise_diagram_label(clean):
            return ""
        return clean[:max_length].strip()

    def _is_noise_diagram_label(self, label: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(label or "").lower()).strip("_")
        if not normalized:
            return True
        if normalized in DIAGRAM_NOISE_TERMS:
            return True
        words = normalized.split("_")
        if len(words) == 1 and words[0] in GENERIC_DIAGRAM_LABELS:
            return True
        return False

    def _normalized_label_set(self, labels: list[str]) -> set[str]:
        normalized = set()
        for label in labels:
            clean = re.sub(r"[^a-z0-9]+", " ", str(label).lower()).strip()
            if clean and not self._is_noise_diagram_label(clean):
                normalized.add(clean)
        return normalized

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _tikz_for_diagram_spec(self, spec: dict[str, Any]) -> str:
        nodes = spec.get("nodes") or []
        edges = spec.get("edges") or []
        positions = self._tikz_positions(str(spec.get("layout") or "flow"), len(nodes))
        lines = [
            "\\begin{tikzpicture}[>=stealth, node distance=2.2cm,",
            "  concept/.style={draw, rounded corners, align=center, text width=3.1cm, minimum height=1cm},",
            "  relation/.style={font=\\scriptsize, fill=white, inner sep=1pt}]",
        ]
        for index, node in enumerate(nodes):
            x, y = positions[index]
            lines.append(
                f"\\node[concept] ({node['id']}) at ({x},{y}) {{{self._escape_tex(node['label'])}}};"
            )
        for edge in edges:
            label = self._escape_tex(edge.get("label", "supports"))
            lines.append(f"\\draw[->] ({edge['from']}) -- node[relation] {{{label}}} ({edge['to']});")
        lines.append("\\end{tikzpicture}\n")
        return "\n".join(lines)

    def _tikz_positions(self, layout: str, count: int) -> list[tuple[float, float]]:
        if layout == "diamond":
            return [(0, 0), (3.4, 1.4), (3.4, -1.4), (6.8, 0), (10.2, 0)][:count]
        if layout == "stack":
            return [(0, -index * 1.55) for index in range(count)]
        if layout == "cycle":
            return [(0, 0), (3.4, 1.2), (6.8, 0), (3.4, -1.2), (10.2, 0)][:count]
        return [(index * 3.4, 0) for index in range(count)]

    def _svg_for_diagram_spec(self, spec: dict[str, Any]) -> str:
        nodes = spec.get("nodes") or []
        edges = spec.get("edges") or []
        layout = str(spec.get("layout") or "flow")
        raw_positions = self._tikz_positions(layout, len(nodes))
        positions = [(70 + x * 58, 135 - y * 42) for x, y in raw_positions]
        node_positions = {node["id"]: positions[index] for index, node in enumerate(nodes)}
        lines = [
            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"760\" height=\"260\" viewBox=\"0 0 760 260\">",
            "  <rect width=\"760\" height=\"260\" fill=\"#f8faf8\"/>",
            "  <defs><marker id=\"arrow\" markerWidth=\"10\" markerHeight=\"10\" refX=\"8\" refY=\"3\" orient=\"auto\"><path d=\"M0,0 L0,6 L9,3 z\" fill=\"#1f2a27\"/></marker></defs>",
            f"  <text x=\"24\" y=\"28\" font-family=\"serif\" font-size=\"13\" fill=\"#55615d\">{self._escape_xml(str(spec.get('diagram_kind') or 'diagram'))}</text>",
        ]
        for edge in edges:
            start = node_positions.get(edge["from"])
            end = node_positions.get(edge["to"])
            if start and end:
                lines.append(f"  <path d=\"M{start[0]} {start[1]} L{end[0]} {end[1]}\" stroke=\"#1f2a27\" stroke-width=\"2\" marker-end=\"url(#arrow)\"/>")
        for node in nodes:
            x, y = node_positions[node["id"]]
            lines.append(f"  <rect x=\"{x - 52}\" y=\"{y - 28}\" width=\"104\" height=\"56\" rx=\"8\" fill=\"#fdfdfb\" stroke=\"#1f2a27\"/>")
            lines.append(f"  <text x=\"{x}\" y=\"{y + 5}\" text-anchor=\"middle\" font-family=\"serif\" font-size=\"13\">{self._escape_xml(node['label'])}</text>")
        purpose = self._clean_diagram_label(str(spec.get("purpose") or ""), max_length=96)
        lines.append(f"  <text x=\"380\" y=\"238\" text-anchor=\"middle\" font-family=\"serif\" font-size=\"13\">{self._escape_xml(purpose)}</text>")
        lines.append("</svg>\n")
        return "\n".join(lines)

    def _titleize(self, value: str) -> str:
        return " ".join(word.capitalize() for word in re.split(r"[_\-\s]+", str(value)) if word)

    def _media_content(self, request: dict[str, Any], extension: str) -> str:
        return self._render_media_content(request, extension, self._diagram_spec_for_request(request))

    def _latest_compile_result(self) -> dict[str, Any]:
        log_dir = self.book_root / "build" / "logs"
        logs = sorted(log_dir.glob("*.log")) if log_dir.exists() else []
        for path in reversed(logs):
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                continue
        return {
            "status": "failed",
            "errors": ["No compile result was available for document design review."],
            "log_path": None,
            "pdf_path": None,
        }

    def _style_fix_content(self, result: dict[str, Any]) -> str:
        errors = result.get("errors") or ["No compile result was available."]
        lines = [
            "% Proposed by document_design_agent.",
            "% Review before including from the document preamble or class file.",
            "",
        ]
        error_blob = "\n".join(errors)
        if "Undefined control sequence" in error_blob:
            lines.append("% Undefined commands detected: add package imports or define missing macros here.")
        if "LaTeX Error: File" in error_blob or "not found" in error_blob:
            lines.append("% Missing class/package detected: verify TEXINPUTS and document style selection.")
        if "No LaTeX compiler" in error_blob:
            lines.append("% Install latexmk/xelatex or configure the app compiler path before retrying.")
        lines.append("% Latest errors:")
        lines.extend(f"% - {error}" for error in errors[:10])
        return "\n".join(lines) + "\n"

    def _drift_rationale(
        self,
        failures: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        relevant: list[dict[str, Any]],
    ) -> str:
        if failures:
            subjects = ", ".join(sorted({event["subject"] for event in failures})[:5])
            return f"Blocking drift remains in {subjects}."
        if warnings:
            subjects = ", ".join(sorted({event["subject"] for event in warnings})[:5])
            return f"Non-blocking drift or user review remains in {subjects}."
        if not relevant:
            return "No verification history exists yet."
        return "No current drift detected from verification history."

    def _rewrite_history_event(self, updated_event: dict[str, Any]) -> None:
        events = self.loop.history.load()
        for index, event in enumerate(events):
            if event["event_id"] == updated_event["event_id"]:
                events[index] = updated_event
                break
        self.loop.history.path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in events)
        )

    def _escape_tex(self, value: str) -> str:
        replacements = {
            "\\": "\\textbackslash{}",
            "&": "\\&",
            "%": "\\%",
            "$": "\\$",
            "#": "\\#",
            "_": "\\_",
            "{": "\\{",
            "}": "\\}",
        }
        return "".join(replacements.get(char, char) for char in str(value))

    def _escape_xml(self, value: str) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
