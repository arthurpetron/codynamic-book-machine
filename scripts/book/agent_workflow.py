"""Deterministic authoring-agent workflows for canonical book projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import threading
import time
from typing import Any

import yaml

from scripts.api import LLMProvider, LLMProviderError, get_provider
from scripts.book.authoring import AuthoringLoop, EditProposal
from scripts.book.repository import BookRepository
from scripts.book.typesetting import CompileResult, LatexBuildService
from scripts.messaging.message_router import MessageRouter


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
        return "\n".join([
            f"You are {definition.get('name') or record.get('agent_id')}.",
            f"Role: {definition.get('role') or record.get('role', 'agent')}",
            "",
            "Prompt header:",
            str(definition.get("prompt_header") or "(No prompt header declared.)").strip(),
            "",
            "Declared capabilities from your agent definition YAML:",
            yaml.safe_dump(capabilities, sort_keys=False, allow_unicode=True).strip(),
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
        try:
            result = self._dispatch_agent_task(agent_id, task)
        except Exception as exc:
            failed = self.runtime.mark_task(agent_id, task["task_id"], "failed", error=str(exc))
            self.commit_log.record(
                AGENT_IDS["hypervisor"],
                "task_failed",
                agent_id,
                str(exc),
                {"task": failed},
            )
            raise

        completed = self.runtime.mark_task(agent_id, task["task_id"], "complete", result=result)
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
            content = self._media_content(request, extension)
            result = self.loop.media.fulfill_request(
                request_id=request["request_id"],
                diagram_agent=AGENT_IDS["diagram"],
                content=content,
                extension=extension,
            )
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
        )
        extension = self._media_extension(media_type)
        result = self.loop.media.fulfill_request(
            request_id=request["request_id"],
            diagram_agent=AGENT_IDS["diagram"],
            content=self._media_content(request, extension),
            extension=extension,
        )
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
            "\\begin{figure}[htbp]\n"
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
            {"subject": "book"},
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
            if action_id == "draft_initial_section":
                proposal = self.draft_section(section_id, action_id=action_id, task_context=context)
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
                proposal = self.draft_section(section_id, action_id=action_id, task_context=context)
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
        try:
            self.runtime.enqueue_task(
                agent_id,
                "process_message",
                context={"message": message},
                priority=priority,
                assigned_by=message.get("from", AGENT_IDS["hypervisor"]),
                dedupe=True,
            )
        except KeyError:
            return

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
        return result

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
        feedback = yaml.safe_dump({
            "source": AGENT_IDS["hypervisor"],
            "reason": "Top-priority LaTeX compile failure.",
            "scope": payload.get("scope"),
            "errors": payload.get("errors") or [],
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
                "revise_section_from_feedback",
                {
                    "section_id": section_id,
                    "phase": "compile_repair",
                    "feedback": feedback,
                },
                priority=0,
            ))
        return queued

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
        provider = self._get_provider()
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
        response = provider.simple_prompt(
            prompt=prompt,
            system_prompt=system_prompt,
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
        description = context.get("description") or self._default_diagram_description(section_id, node)
        media_type = context.get("media_type") or "tikz"
        task = self.queue_agent_task(
            AGENT_IDS["diagram"],
            "create_diagram_asset",
            {
                "section_id": section_id,
                "requesting_agent": f"{AGENT_IDS['section']}__{section_id}",
                "media_type": media_type,
                "description": description,
                "insert_into_section": bool(context.get("insert_into_section", True)),
            },
            priority=context.get("priority", 15),
        )
        return {
            "section_id": section_id,
            "status": "queued",
            "description": description,
            "media_type": media_type,
            "diagram_task": task,
        }

    def _default_diagram_description(self, section_id: str, node: dict[str, Any]) -> str:
        title = node.get("title", section_id)
        summary = node.get("summary") or node.get("goal") or ""
        source = self.repository.load_section(section_id).strip()
        basis = summary or source[:240] or title
        return f"Conceptual diagram for '{title}': {basis}"

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

    def _media_content(self, request: dict[str, Any], extension: str) -> str:
        description = request.get("description", "Requested media")
        if extension == ".svg":
            return (
                "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"640\" height=\"240\" viewBox=\"0 0 640 240\">\n"
                "  <rect width=\"640\" height=\"240\" fill=\"#f8faf8\"/>\n"
                "  <circle cx=\"180\" cy=\"120\" r=\"46\" fill=\"#0f766e\"/>\n"
                "  <circle cx=\"460\" cy=\"120\" r=\"46\" fill=\"#d9a441\"/>\n"
                "  <path d=\"M230 120h180\" stroke=\"#1f2a27\" stroke-width=\"6\" marker-end=\"url(#arrow)\"/>\n"
                "  <defs><marker id=\"arrow\" markerWidth=\"10\" markerHeight=\"10\" refX=\"8\" refY=\"3\" orient=\"auto\"><path d=\"M0,0 L0,6 L9,3 z\" fill=\"#1f2a27\"/></marker></defs>\n"
                f"  <text x=\"320\" y=\"210\" text-anchor=\"middle\" font-family=\"serif\" font-size=\"20\">{self._escape_xml(description)}</text>\n"
                "</svg>\n"
            )
        if extension == ".tikz":
            return (
                "\\begin{tikzpicture}[node distance=3cm,>=stealth]\n"
                "\\node[draw, rounded corners] (a) {Context};\n"
                "\\node[draw, rounded corners, right of=a] (b) {Section};\n"
                "\\draw[->] (a) -- node[above] {request} (b);\n"
                f"\\node[below=1cm of a, text width=8cm] {{{self._escape_tex(description)}}};\n"
                "\\end{tikzpicture}\n"
            )
        return f"{description}\n"

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
