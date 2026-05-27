"""Runtime prompt construction tools for agents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from scripts.agents.lifecycle import (
    COMMUNICATION_STATES,
    OUTPUT_MUTATION_STATES,
    AgentLifecycleState,
)


class MemorySummarizer:
    """Build a compact deterministic summary from durable agent logs."""

    def __init__(self, agent_state_dir: Path, max_entries: int = 5):
        self.agent_state_dir = Path(agent_state_dir)
        self.max_entries = max_entries

    def summarize(self) -> dict[str, Any]:
        summary = {}
        for name in ("action_log", "message_log", "error_log", "outputs"):
            path = self.agent_state_dir / f"{name}.yaml"
            if not path.exists():
                summary[name] = []
                continue
            with open(path, "r") as f:
                entries = yaml.safe_load(f) or []
            summary[name] = entries[-self.max_entries:]
        return summary


class RoleContractRegistry:
    """Normalizes role, task, permission, action, input, and output contracts."""

    def __init__(self, agent_def: dict[str, Any]):
        self.agent_def = agent_def

    def contract(self) -> dict[str, Any]:
        return {
            "name": self.agent_def.get("name"),
            "role": self.agent_def.get("role", ""),
            "tasks": self.agent_def.get("tasks", []),
            "permissions": self.agent_def.get("permissions", []),
            "inputs": self.agent_def.get("inputs", []),
            "outputs": self.agent_def.get("outputs", []),
            "actions": [
                {
                    "id": action.get("id"),
                    "description": action.get("description", ""),
                }
                for action in self.agent_def.get("actions", [])
            ],
        }


class BookContextSelector:
    """Selects a bounded book/outline context for an agent prompt."""

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root)

    def select(self, agent_id: str, action_context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        action_context = action_context or {}
        book_data_dir = self.data_root / "book_data"
        if not book_data_dir.exists():
            return {}

        outlines = sorted(book_data_dir.glob("*/outline/*.yaml"))
        if not outlines:
            return {}

        with open(outlines[0], "r") as f:
            outline = yaml.safe_load(f) or {}
        work = outline.get("work", {})
        selected = {
            "work_id": work.get("id"),
            "title": work.get("title"),
            "summary": work.get("summary", ""),
        }

        section_id = action_context.get("section_id")
        if section_id:
            selected["section"] = self._find_node(work.get("structure", []), section_id)
        elif "outline" in agent_id:
            selected["structure"] = [
                {"id": node.get("id"), "title": node.get("title"), "type": node.get("type")}
                for node in work.get("structure", [])
            ]
        return selected

    def _find_node(self, nodes: list[dict[str, Any]], node_id: str) -> dict[str, Any] | None:
        for node in nodes:
            if node.get("id") == node_id:
                return node
            found = self._find_node(node.get("content", []) or [], node_id)
            if found:
                return found
        return None


class PromptContextBuilder:
    """Collect all structured facts needed to compose an agent system prompt."""

    def build(self, controller, action_context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        action_context = action_context or {}
        return {
            "agent_id": controller.agent_id,
            "lifecycle_state": controller.lifecycle_state.value,
            "role_contract": RoleContractRegistry(controller.agent_def).contract(),
            "allowed_recipients": controller.get_allowed_message_recipients(),
            "work_queue": controller.work_manager.get_queue_summary(),
            "task_queue_length": len(controller.task_queue),
            "memory": MemorySummarizer(controller.agent_state_dir).summarize(),
            "book_context": BookContextSelector(controller.data_root).select(
                controller.agent_id,
                action_context,
            ),
        }


class PromptComposer:
    """Compose a system prompt from structured prompt context."""

    def compose(self, context: dict[str, Any]) -> str:
        contract = context["role_contract"]
        lines = [
            f"You are {contract.get('name') or context['agent_id']}, an agent in the Codynamic Book Machine system.",
            "",
            f"Lifecycle state: {context['lifecycle_state']}",
            "",
            "Role:",
            contract.get("role", ""),
        ]

        self._append_list(lines, "Responsibilities", contract.get("tasks", []))
        self._append_list(lines, "Permissions", contract.get("permissions", []))
        self._append_list(lines, "Available actions", [a["id"] for a in contract.get("actions", []) if a.get("id")])

        allowed = context.get("allowed_recipients")
        if allowed is not None:
            lines.extend(["", "Messaging policy:"])
            if allowed:
                state = AgentLifecycleState(context["lifecycle_state"])
                if state in COMMUNICATION_STATES:
                    lines.append("You may send messages only to:")
                else:
                    lines.append("When messaging is enabled, configured outbound recipients are:")
                lines.extend(f"- {recipient}" for recipient in allowed)
            else:
                lines.append("You may not initiate messages to other agents.")

        lines.extend([
            "",
            "Runtime context:",
            yaml.safe_dump({
                "work_queue": context.get("work_queue", {}),
                "task_queue_length": context.get("task_queue_length", 0),
                "book_context": context.get("book_context", {}),
                "recent_memory": context.get("memory", {}),
            }, sort_keys=False),
        ])
        return "\n".join(lines).strip() + "\n"

    def _append_list(self, lines: list[str], title: str, values: list[Any]) -> None:
        if not values:
            return
        lines.extend(["", f"{title}:"])
        for value in values:
            if isinstance(value, dict):
                value = value.get("description") or value.get("id") or yaml.safe_dump(value, sort_keys=False).strip()
            lines.append(f"- {value}")


class PromptPolicyValidator:
    """Checks prompt content against runtime permission boundaries."""

    def validate(self, prompt: str, context: dict[str, Any]) -> tuple[bool, list[str]]:
        errors = []
        state = AgentLifecycleState(context["lifecycle_state"])
        allowed = context.get("allowed_recipients")

        if state not in COMMUNICATION_STATES and "You may send messages only to:" in prompt:
            errors.append(f"Prompt grants messaging while state is {state.value}")
        if state not in OUTPUT_MUTATION_STATES and "may advance its task queue pointer" in prompt:
            errors.append(f"Prompt grants output mutation while state is {state.value}")
        if allowed == [] and "You may send messages only to:" in prompt:
            errors.append("Prompt lists recipients despite empty allowed recipient set")
        return (len(errors) == 0, errors)


@dataclass
class PromptSnapshot:
    snapshot_id: str
    agent_id: str
    action_id: str
    created_at: str
    prompt_sha256: str
    prompt: str
    context: dict[str, Any]


class PromptSnapshotStore:
    """Persist exact prompts used for agent actions."""

    def __init__(self, agent_state_dir: Path):
        self.snapshot_dir = Path(agent_state_dir) / "prompt_snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def save(self, agent_id: str, action_id: str, prompt: str, context: dict[str, Any]) -> PromptSnapshot:
        created_at = datetime.now().isoformat()
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        snapshot_id = f"prompt_{created_at.replace(':', '').replace('.', '')}_{digest[:12]}"
        snapshot = PromptSnapshot(
            snapshot_id=snapshot_id,
            agent_id=agent_id,
            action_id=action_id,
            created_at=created_at,
            prompt_sha256=digest,
            prompt=prompt,
            context=context,
        )
        with open(self.snapshot_dir / f"{snapshot_id}.yaml", "w") as f:
            yaml.safe_dump(snapshot.__dict__, f, sort_keys=False, allow_unicode=True)
        return snapshot


def build_validated_system_prompt(controller, action_id: str = "", action_context: Optional[dict[str, Any]] = None) -> str:
    """Build, validate, and snapshot the runtime system prompt for an action."""
    context = PromptContextBuilder().build(controller, action_context)
    prompt = PromptComposer().compose(context)
    valid, errors = PromptPolicyValidator().validate(prompt, context)
    if not valid:
        raise ValueError(f"Prompt violates runtime policy: {'; '.join(errors)}")
    PromptSnapshotStore(controller.agent_state_dir).save(
        controller.agent_id,
        action_id or "system",
        prompt,
        context,
    )
    return prompt
