"""Durable per-agent conversation sessions.

The task queues decide what an agent should do next.  This module preserves
what the agent has already seen and answered so future LLM calls can reuse the
same working context instead of starting from a cold prompt every time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any

from scripts.api import LLMResponse, Message


def _now() -> str:
    return datetime.now().isoformat()


def _safe_agent_id(agent_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", agent_id).strip("_") or "agent"


def _excerpt(text: str, limit: int = 700) -> str:
    clean = " ".join(str(text).split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


@dataclass
class AgentSession:
    agent_id: str
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    summary: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    compactions: list[dict[str, Any]] = field(default_factory=list)
    token_total: int = 0
    provider_session_id: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any], agent_id: str) -> "AgentSession":
        return cls(
            agent_id=str(payload.get("agent_id") or agent_id),
            created_at=str(payload.get("created_at") or _now()),
            updated_at=str(payload.get("updated_at") or _now()),
            summary=str(payload.get("summary") or ""),
            messages=list(payload.get("messages") or []),
            events=list(payload.get("events") or []),
            compactions=list(payload.get("compactions") or []),
            token_total=int(payload.get("token_total") or 0),
            provider_session_id=payload.get("provider_session_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "summary": self.summary,
            "messages": self.messages,
            "events": self.events,
            "compactions": self.compactions,
            "token_total": self.token_total,
            "provider_session_id": self.provider_session_id,
        }


class AgentSessionStore:
    """File-backed store for reusable agent sessions."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_recent_messages: int = 10,
        max_context_chars: int = 24000,
        summary_chars: int = 6000,
    ):
        self.root = Path(root)
        self.max_recent_messages = max_recent_messages
        self.max_context_chars = max_context_chars
        self.summary_chars = summary_chars
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, agent_id: str) -> Path:
        return self.root / f"{_safe_agent_id(agent_id)}.json"

    def load(self, agent_id: str) -> AgentSession:
        path = self.path_for(agent_id)
        if not path.exists():
            return AgentSession(agent_id=agent_id)
        return AgentSession.from_dict(json.loads(path.read_text()), agent_id=agent_id)

    def save(self, session: AgentSession) -> AgentSession:
        session.updated_at = _now()
        path = self.path_for(session.agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(session.to_dict(), indent=2, sort_keys=True) + "\n")
        tmp_path.replace(path)
        return session

    def build_messages(
        self,
        agent_id: str,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> list[Message]:
        """Build a provider message list with prior session context."""
        self.compact_if_needed(agent_id)
        session = self.load(agent_id)
        messages = [Message(role="system", content=system_prompt)]
        if session.summary.strip():
            messages.append(Message(
                role="system",
                content=(
                    "Persistent session memory for this agent. Use it as prior working "
                    "context, but prefer the current task when there is a conflict.\n\n"
                    f"{session.summary.strip()}"
                ),
            ))
        for item in session.messages[-self.max_recent_messages:]:
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and content:
                messages.append(Message(role=role, content=str(content)))
        messages.append(Message(role="user", content=user_prompt))
        return messages

    def record_exchange(
        self,
        agent_id: str,
        *,
        user_prompt: str,
        response: LLMResponse,
        task_id: str | None = None,
        action_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentSession:
        session = self.load(agent_id)
        common = {
            "task_id": task_id,
            "action_id": action_id,
            "created_at": _now(),
            "metadata": metadata or {},
        }
        session.messages.append({
            **common,
            "role": "user",
            "content": user_prompt,
        })
        session.messages.append({
            **common,
            "role": "assistant",
            "content": response.content,
            "response": {
                "provider": response.provider,
                "model": response.model,
                "tokens_used": response.tokens_used,
                "latency_ms": response.latency_ms,
                "metadata": response.metadata or {},
            },
        })
        if response.tokens_used:
            session.token_total += int(response.tokens_used)
        saved = self.save(session)
        self.compact_if_needed(agent_id)
        return self.load(agent_id) if saved.messages else saved

    def record_event(
        self,
        agent_id: str,
        event_type: str,
        *,
        task_id: str | None = None,
        action_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentSession:
        session = self.load(agent_id)
        session.events.append({
            "event_type": event_type,
            "task_id": task_id,
            "action_id": action_id,
            "metadata": metadata or {},
            "created_at": _now(),
        })
        if len(session.events) > 200:
            session.events = session.events[-200:]
        return self.save(session)

    def compact_if_needed(self, agent_id: str) -> AgentSession:
        session = self.load(agent_id)
        message_chars = sum(len(str(item.get("content") or "")) for item in session.messages)
        if len(session.messages) <= self.max_recent_messages or message_chars <= self.max_context_chars:
            return session

        keep_count = max(2, self.max_recent_messages)
        older = session.messages[:-keep_count]
        session.messages = session.messages[-keep_count:]
        summary_lines = []
        for item in older:
            role = item.get("role", "message")
            action = item.get("action_id") or "unknown_action"
            task = item.get("task_id") or "unknown_task"
            summary_lines.append(f"- {role} for {action} ({task}): {_excerpt(str(item.get('content') or ''))}")

        joined = "\n".join(summary_lines)
        if session.summary.strip():
            joined = session.summary.strip() + "\n" + joined
        if len(joined) > self.summary_chars:
            joined = joined[-self.summary_chars:].lstrip()
        session.summary = joined
        session.compactions.append({
            "created_at": _now(),
            "compacted_message_count": len(older),
            "remaining_message_count": len(session.messages),
            "summary_chars": len(session.summary),
        })
        return self.save(session)
