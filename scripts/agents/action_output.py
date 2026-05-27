"""Standardized action output records for agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


VALID_OUTPUT_TYPES = {"proposal", "patch", "message", "artifact"}


@dataclass
class ActionOutput:
    """A durable, typed output emitted by an agent action."""

    output_type: str
    agent_id: str
    action_id: str
    payload: dict[str, Any]
    output_id: str = field(default_factory=lambda: f"out_{uuid4().hex}")
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "created"

    def __post_init__(self):
        if self.output_type not in VALID_OUTPUT_TYPES:
            raise ValueError(f"Invalid output_type: {self.output_type}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id,
            "output_type": self.output_type,
            "agent_id": self.agent_id,
            "action_id": self.action_id,
            "created_at": self.created_at,
            "status": self.status,
            "payload": self.payload,
        }
