"""Authoring and review loop primitives for canonical book projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import difflib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


PROPOSAL_STATUSES = {"pending", "accepted", "rejected", "revised"}
CHECK_STATUSES = {"pass", "fail", "warn"}


@dataclass
class EditProposal:
    """A proposed file edit produced by an agent."""

    proposal_id: str
    agent_id: str
    target_path: str
    status: str
    rationale: str
    diff: str
    proposed_content: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    reviewed_at: str | None = None
    review_note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        agent_id: str,
        target_path: str,
        current_content: str,
        proposed_content: str,
        rationale: str,
        metadata: dict[str, Any] | None = None,
    ) -> "EditProposal":
        diff = "".join(difflib.unified_diff(
            current_content.splitlines(keepends=True),
            proposed_content.splitlines(keepends=True),
            fromfile=target_path,
            tofile=target_path,
        ))
        return cls(
            proposal_id=f"proposal_{uuid4().hex[:12]}",
            agent_id=agent_id,
            target_path=target_path,
            status="pending",
            rationale=rationale,
            diff=diff,
            proposed_content=proposed_content,
            metadata=metadata or {},
        )


class ProposalStore:
    """JSON-backed proposal-first editing store."""

    def __init__(self, book_root: Path | str):
        self.book_root = Path(book_root)
        self.proposals_dir = self.book_root / "proposals"
        self.history = VerificationHistory(self.book_root)

    def propose_file_edit(
        self,
        agent_id: str,
        target_path: Path | str,
        proposed_content: str,
        rationale: str,
        metadata: dict[str, Any] | None = None,
        mode: str = "proposal",
    ) -> EditProposal:
        """Create a pending proposal, or accept immediately in full-auto mode."""
        target = self._resolve_target(target_path)
        current_content = target.read_text() if target.exists() else ""
        relative_target = self._relative(target)
        proposal = EditProposal.create(
            agent_id=agent_id,
            target_path=relative_target,
            current_content=current_content,
            proposed_content=proposed_content,
            rationale=rationale,
            metadata=metadata,
        )
        self._write(proposal)
        if mode == "full-auto":
            self.accept(proposal.proposal_id, reviewer="full-auto", note="Accepted automatically.")
        return proposal

    def list(self, status: str | None = None) -> list[EditProposal]:
        proposals = []
        for path in sorted(self.proposals_dir.glob("*.json")):
            data = json.loads(path.read_text())
            if status is None or data.get("status") == status:
                proposals.append(EditProposal(**data))
        return proposals

    def load(self, proposal_id: str) -> EditProposal:
        path = self._path(proposal_id)
        if not path.exists():
            raise KeyError(f"Proposal not found: {proposal_id}")
        return EditProposal(**json.loads(path.read_text()))

    def accept(self, proposal_id: str, reviewer: str = "user", note: str = "") -> EditProposal:
        proposal = self.load(proposal_id)
        target = self.book_root / proposal.target_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(proposal.proposed_content)
        return self._review(proposal, "accepted", reviewer, note)

    def reject(self, proposal_id: str, reviewer: str = "user", note: str = "") -> EditProposal:
        return self._review(self.load(proposal_id), "rejected", reviewer, note)

    def revise(
        self,
        proposal_id: str,
        proposed_content: str,
        reviewer: str = "user",
        note: str = "",
    ) -> EditProposal:
        original = self.load(proposal_id)
        target = self.book_root / original.target_path
        current_content = target.read_text() if target.exists() else ""
        revised = EditProposal.create(
            agent_id=original.agent_id,
            target_path=original.target_path,
            current_content=current_content,
            proposed_content=proposed_content,
            rationale=note or original.rationale,
            metadata={**original.metadata, "revised_from": original.proposal_id},
        )
        self._review(original, "revised", reviewer, note)
        self._write(revised)
        return revised

    def _review(self, proposal: EditProposal, status: str, reviewer: str, note: str) -> EditProposal:
        if status not in PROPOSAL_STATUSES:
            raise ValueError(f"Invalid proposal status: {status}")
        proposal.status = status
        proposal.reviewed_at = datetime.now().isoformat()
        proposal.review_note = note
        self._write(proposal)
        self.history.record_event(
            event_type=f"proposal_{status}",
            agent_id=proposal.agent_id,
            subject=proposal.target_path,
            status="pass" if status == "accepted" else "warn",
            rationale=note or proposal.rationale,
            metadata={"proposal_id": proposal.proposal_id, "reviewer": reviewer},
        )
        return proposal

    def _write(self, proposal: EditProposal) -> None:
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self._path(proposal.proposal_id).write_text(json.dumps(asdict(proposal), indent=2) + "\n")

    def _path(self, proposal_id: str) -> Path:
        return self.proposals_dir / f"{proposal_id}.json"

    def _resolve_target(self, target_path: Path | str) -> Path:
        target = Path(target_path)
        if target.is_absolute():
            return target
        return self.book_root / target

    def _relative(self, target: Path) -> str:
        try:
            return str(target.relative_to(self.book_root))
        except ValueError:
            return str(target)


class VerificationHistory:
    """Append-only memory of checks, failures, rationale, and review decisions."""

    def __init__(self, book_root: Path | str):
        self.book_root = Path(book_root)
        self.path = self.book_root / "logs" / "verification_history.jsonl"

    def record_check(
        self,
        agent_id: str,
        subject: str,
        checks: dict[str, str],
        rationale: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        overall = "pass"
        if any(status == "fail" for status in checks.values()):
            overall = "fail"
        elif any(status == "warn" for status in checks.values()):
            overall = "warn"
        return self.record_event(
            event_type="verification_check",
            agent_id=agent_id,
            subject=subject,
            status=overall,
            rationale=rationale,
            metadata={"checks": checks, **(metadata or {})},
        )

    def record_event(
        self,
        event_type: str,
        agent_id: str,
        subject: str,
        status: str,
        rationale: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in CHECK_STATUSES:
            raise ValueError(f"Invalid verification status: {status}")
        event = {
            "event_id": f"event_{uuid4().hex[:12]}",
            "event_type": event_type,
            "agent_id": agent_id,
            "subject": subject,
            "status": status,
            "rationale": rationale,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


class MediaRequestRegistry:
    """Single diagram-agent media request and response registry."""

    def __init__(self, book_root: Path | str):
        self.book_root = Path(book_root)
        self.media_dir = self.book_root / "media"
        self.request_path = self.media_dir / "requests.json"

    def request_media(
        self,
        section_id: str,
        requesting_agent: str,
        description: str,
        media_type: str = "tikz",
    ) -> dict[str, Any]:
        request = {
            "request_id": f"media_req_{uuid4().hex[:12]}",
            "section_id": section_id,
            "requesting_agent": requesting_agent,
            "description": description,
            "media_type": media_type,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        requests = self.load_requests()
        requests.append(request)
        self._save_requests(requests)
        return request

    def fulfill_request(
        self,
        request_id: str,
        diagram_agent: str,
        content: str,
        extension: str = ".tikz",
    ) -> dict[str, Any]:
        requests = self.load_requests()
        for request in requests:
            if request["request_id"] == request_id:
                media_path = self._media_path(request, extension)
                media_path.parent.mkdir(parents=True, exist_ok=True)
                media_path.write_text(content)
                request.update({
                    "status": "fulfilled",
                    "diagram_agent": diagram_agent,
                    "path": str(media_path.relative_to(self.book_root)),
                    "fulfilled_at": datetime.now().isoformat(),
                })
                self._save_requests(requests)
                return request
        raise KeyError(f"Media request not found: {request_id}")

    def load_requests(self) -> list[dict[str, Any]]:
        if not self.request_path.exists():
            return []
        data = json.loads(self.request_path.read_text())
        if not isinstance(data, list):
            raise ValueError(f"Media request registry must be a list: {self.request_path}")
        return data

    def _save_requests(self, requests: list[dict[str, Any]]) -> None:
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.request_path.write_text(json.dumps(requests, indent=2, sort_keys=True) + "\n")

    def _media_path(self, request: dict[str, Any], extension: str) -> Path:
        suffix = extension if extension.startswith(".") else f".{extension}"
        name = f"{request['section_id']}__{request['request_id']}{suffix}"
        if request.get("media_type") in {"tikz", "diagram", "svg"}:
            return self.media_dir / "diagrams" / name
        return self.media_dir / name


class AuthoringLoop:
    """High-level section drafting and review facade."""

    def __init__(self, book_root: Path | str, mode: str = "proposal"):
        self.book_root = Path(book_root)
        self.mode = mode
        self.proposals = ProposalStore(self.book_root)
        self.history = VerificationHistory(self.book_root)
        self.media = MediaRequestRegistry(self.book_root)

    def propose_section_draft(
        self,
        section_id: str,
        content: str,
        agent_id: str = "section_agent",
        rationale: str = "Draft section payload.",
        extension: str = ".md",
    ) -> EditProposal:
        target = Path("content") / "sections" / f"{section_id}{extension}"
        return self.proposals.propose_file_edit(
            agent_id=agent_id,
            target_path=target,
            proposed_content=content,
            rationale=rationale,
            metadata={"section_id": section_id, "kind": "section_draft"},
            mode=self.mode,
        )

    def record_gardener_check(
        self,
        section_id: str,
        intent: str,
        dependencies: str,
        claim_clarity: str,
        latex: str,
        rationale: str = "",
    ) -> dict[str, Any]:
        return self.history.record_check(
            agent_id="gardener_agent",
            subject=section_id,
            checks={
                "intent": intent,
                "dependencies": dependencies,
                "claim_clarity": claim_clarity,
                "latex": latex,
            },
            rationale=rationale,
        )

    def record_hypervisor_drift(
        self,
        subject: str,
        status: str,
        rationale: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.history.record_event(
            event_type="global_drift_check",
            agent_id="hypervisor_agent",
            subject=subject,
            status=status,
            rationale=rationale,
            metadata=metadata,
        )


class CommunicationMemory:
    """Summarize communication logs into reusable action patterns and questions."""

    def __init__(self, data_root: Path | str = Path("data")):
        self.data_root = Path(data_root)
        self.memory_path = self.data_root / "log_memory" / "patterns.json"

    def build(self) -> dict[str, Any]:
        """Build and persist a compact memory summary from message and user-chat logs."""
        messages = self._load_agent_messages()
        user_questions = self._load_user_questions()
        memory = {
            "generated_at": datetime.now().isoformat(),
            "common_action_patterns": self._common_patterns(messages),
            "common_questions": self._common_questions(user_questions),
            "message_count": len(messages),
            "user_question_count": len(user_questions),
        }
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory_path.write_text(json.dumps(memory, indent=2, sort_keys=True) + "\n")
        return memory

    def load(self) -> dict[str, Any]:
        if not self.memory_path.exists():
            return {}
        return json.loads(self.memory_path.read_text())

    def _load_agent_messages(self) -> list[dict[str, Any]]:
        messages = []
        for path in sorted((self.data_root / "agent_state").glob("*/message_log.yaml")):
            try:
                import yaml

                entries = yaml.safe_load(path.read_text()) or []
            except Exception:
                entries = []
            for entry in entries:
                message = entry.get("message") if isinstance(entry, dict) else None
                if isinstance(message, dict):
                    messages.append(message)
        return messages

    def _load_user_questions(self) -> list[dict[str, Any]]:
        queue = self.data_root / "user_chat" / "queue.json"
        if not queue.exists():
            return []
        data = json.loads(queue.read_text())
        return [item for item in data if isinstance(item, dict)]

    def _common_patterns(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for message in messages:
            key = f"{message.get('from', 'unknown')}->{message.get('to', 'unknown')}:{message.get('subject', '')}"
            counts[key] = counts.get(key, 0) + 1
        return [
            {"pattern": pattern, "count": count}
            for pattern, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ]

    def _common_questions(self, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for question in questions:
            subject = question.get("subject") or "Untitled question"
            counts[subject] = counts.get(subject, 0) + 1
        return [
            {"question": question, "count": count}
            for question, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ]
