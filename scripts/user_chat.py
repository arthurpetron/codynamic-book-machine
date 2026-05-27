"""Durable queue for agent requests that need user attention."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


USER_CHAT_PERMISSIONS = {
    "ask_user",
    "interact_with_user",
    "queue_user_messages",
    "talk_to_user",
}


@dataclass
class UserChatMessage:
    """A request or question an agent has queued for the user."""

    message_id: str
    from_agent: str
    subject: str
    body: str
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    answered_at: Optional[str] = None
    answer: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        from_agent: str,
        subject: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "UserChatMessage":
        return cls(
            message_id=f"user_msg_{uuid4().hex[:12]}",
            from_agent=from_agent,
            subject=subject,
            body=body,
            metadata=metadata or {},
        )


class UserChatQueue:
    """JSON-backed user chat queue shared by agents and the Electron UI."""

    def __init__(self, data_root: Path | str = Path("data"), queue_path: Path | str | None = None):
        self.data_root = Path(data_root)
        self.queue_path = Path(queue_path) if queue_path else self.data_root / "user_chat" / "queue.json"

    def load_all(self) -> List[Dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        try:
            data = json.loads(self.queue_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid user chat queue JSON: {self.queue_path}") from exc
        if not isinstance(data, list):
            raise ValueError(f"User chat queue must be a list: {self.queue_path}")
        return [message for message in data if isinstance(message, dict)]

    def pending(self) -> List[Dict[str, Any]]:
        return [message for message in self.load_all() if message.get("status") == "pending"]

    def counts(self) -> Dict[str, int]:
        counts = {"pending": 0, "answered": 0, "dismissed": 0, "total": 0}
        for message in self.load_all():
            counts["total"] += 1
            status = str(message.get("status", "pending"))
            if status not in counts:
                counts[status] = 0
            counts[status] += 1
        return counts

    def add_request(
        self,
        from_agent: str,
        subject: str,
        body: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        subject = subject.strip()
        body = body.strip()
        if not subject:
            raise ValueError("User chat subject is required")
        if not body:
            raise ValueError("User chat body is required")

        message = UserChatMessage.create(
            from_agent=from_agent,
            subject=subject,
            body=body,
            metadata=metadata,
        )
        messages = self.load_all()
        messages.append(asdict(message))
        self._save(messages)
        return asdict(message)

    def answer(self, message_id: str, answer: str) -> Dict[str, Any]:
        answer = answer.strip()
        if not answer:
            raise ValueError("Answer is required")
        return self._update(message_id, status="answered", answer=answer, answered_at=datetime.now().isoformat())

    def dismiss(self, message_id: str) -> Dict[str, Any]:
        return self._update(message_id, status="dismissed", answered_at=datetime.now().isoformat())

    def _update(self, message_id: str, **updates: Any) -> Dict[str, Any]:
        messages = self.load_all()
        for message in messages:
            if message.get("message_id") == message_id:
                message.update(updates)
                self._save(messages)
                return message
        raise KeyError(f"User chat message not found: {message_id}")

    def _save(self, messages: List[Dict[str, Any]]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(messages, indent=2, sort_keys=True) + "\n")


def agent_can_talk_to_user(agent_def: Dict[str, Any]) -> bool:
    permissions = agent_def.get("permissions", []) or []
    return bool(USER_CHAT_PERMISSIONS.intersection(set(permissions)))
