"""Desktop app state projection for the Electron UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.book.authoring import AuthoringLoop, VerificationHistory
from scripts.book.repository import BookRepository
from scripts.book.typesetting import DesignSettingsService, DocumentStyleRegistry, LatexBuildService


class BookAppState:
    """Project canonical book data into a compact UI state payload."""

    def __init__(self, book_root: Path | str, data_root: Path | str = Path("data")):
        self.book_root = Path(book_root).resolve()
        self.data_root = Path(data_root).resolve()
        self.repository = BookRepository(self.book_root)

    def snapshot(self, selected_id: str | None = None) -> dict[str, Any]:
        book = self.repository.load_book()
        work = book["work"]
        outline = self._outline(work.get("structure", []))
        selected = selected_id or self._first_leaf_id(outline)
        return {
            "bookRoot": str(self.book_root),
            "book": {
                "id": work.get("id"),
                "title": work.get("title"),
                "summary": work.get("summary", ""),
            },
            "outline": outline,
            "selectedId": selected,
            "selectedSection": self.section_payload(selected) if selected else None,
            "design": DesignSettingsService(self.repository).get(),
            "styles": [style.__dict__ for style in DocumentStyleRegistry(Path(".")).list_styles()],
            "messages": self._messages(),
            "agentStatus": self._agent_status(),
            "artifacts": [artifact.__dict__ for artifact in self.repository.artifacts.discover()],
            "proposals": [proposal.__dict__ for proposal in self.repository.proposals.list()],
            "compile": self._latest_compile(),
            "verification": VerificationHistory(self.book_root).load()[-20:],
        }

    def section_payload(self, section_id: str) -> dict[str, Any]:
        node = self.repository.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        content = self.repository.load_section(section_id)
        if not content.strip():
            content = self._fallback_section_content(node)
        return {
            "id": section_id,
            "title": node.get("title", section_id),
            "number": node.get("number", ""),
            "type": node.get("type", "section"),
            "source": content,
            "summary": node.get("summary", ""),
            "contentFile": node.get("content_file"),
            "score": self._score_for(section_id),
            "tone": self._tone_for(section_id),
            "agent": self._agent_label(section_id),
        }

    def save_section(self, section_id: str, content: str) -> dict[str, Any]:
        path = self.repository.save_section(section_id, content)
        AuthoringLoop(self.book_root).history.record_event(
            event_type="section_saved",
            agent_id="desktop_app",
            subject=section_id,
            status="pass",
            rationale=f"Section saved to {path.relative_to(self.book_root)}",
        )
        return self.section_payload(section_id)

    def compile_section(self, section_id: str) -> dict[str, Any]:
        result = LatexBuildService(self.book_root).compile_section(section_id)
        AuthoringLoop(self.book_root).history.record_event(
            event_type="section_compile",
            agent_id="desktop_app",
            subject=section_id,
            status="pass" if result.status == "passed" else "fail",
            rationale="Selected section compile requested from UI.",
            metadata=result.as_dict(),
        )
        return result.as_dict()

    def request_review(self, subject: str = "book") -> dict[str, Any]:
        return AuthoringLoop(self.book_root).history.record_event(
            event_type="review_requested",
            agent_id="desktop_app",
            subject=subject,
            status="warn",
            rationale="User requested full review across outline, drafts, dependencies, and compile state.",
        )

    def _outline(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chapters = []
        for index, node in enumerate(nodes, 1):
            leaves = self._leaf_items(node)
            chapters.append({
                "id": node.get("id"),
                "chapter": str(node.get("number") or f"Chapter {index}"),
                "title": node.get("title", "Untitled"),
                "expanded": True,
                "items": leaves,
            })
        return chapters

    def _fallback_section_content(self, node: dict[str, Any]) -> str:
        title = node.get("title", node.get("id", "Untitled"))
        summary = node.get("summary") or node.get("goal") or "Draft this section."
        return f"\\section{{{title}}}\n\n{summary}\n"

    def _leaf_items(self, node: dict[str, Any]) -> list[dict[str, Any]]:
        children = node.get("content") or []
        if not children:
            section_id = node["id"]
            return [{
                "id": section_id,
                "number": str(node.get("number") or ""),
                "title": node.get("title", section_id),
                "score": self._score_for(section_id),
                "tone": self._tone_for(section_id),
                "agent": self._agent_label(section_id),
            }]
        items = []
        for child in children:
            items.extend(self._leaf_items(child))
        return items

    def _first_leaf_id(self, outline: list[dict[str, Any]]) -> str | None:
        for chapter in outline:
            if chapter.get("items"):
                return chapter["items"][0]["id"]
        return None

    def _score_for(self, section_id: str) -> int | None:
        latest = self._latest_verification_for(section_id)
        if not latest:
            return None
        return {"pass": 94, "warn": 67, "fail": 35}.get(latest.get("status"))

    def _tone_for(self, section_id: str) -> str:
        latest = self._latest_verification_for(section_id)
        if not latest:
            return "idle"
        return {"pass": "good", "warn": "warn", "fail": "warn"}.get(latest.get("status"), "idle")

    def _agent_label(self, section_id: str) -> str:
        latest = self._latest_verification_for(section_id)
        if latest:
            return latest.get("agent_id", "agent")
        return "Queued"

    def _latest_verification_for(self, section_id: str) -> dict[str, Any] | None:
        for event in reversed(VerificationHistory(self.book_root).load()):
            if event.get("subject") == section_id:
                return event
        return None

    def _messages(self) -> list[list[str]]:
        messages = []
        state_root = self.data_root / "agent_state"
        for path in sorted(state_root.glob("*/message_log.yaml")) if state_root.exists() else []:
            entries = yaml.safe_load(path.read_text()) or []
            for entry in entries[-10:]:
                message = entry.get("message", {})
                created = entry.get("timestamp", "")
                messages.append([
                    created[11:16] if len(created) >= 16 else "now",
                    f"{message.get('from', 'Agent')} -> {message.get('to', 'All')}",
                    message.get("body") or message.get("subject") or "",
                ])
        if messages:
            return messages[-20:][::-1]
        return [["now", "Desktop -> Book", "Loaded canonical book state."]]

    def _agent_status(self) -> dict[str, Any]:
        agents = list((self.data_root / "agent_state").glob("*")) if (self.data_root / "agent_state").exists() else []
        pending_proposals = len(self.repository.proposals.list(status="pending"))
        return {
            "active": len(agents),
            "total": max(len(agents), 1),
            "confidence": 72,
            "pendingProposals": pending_proposals,
        }

    def _latest_compile(self) -> dict[str, Any] | None:
        logs = sorted((self.book_root / "build" / "logs").glob("*.log"))
        if not logs:
            return None
        import json

        return json.loads(logs[-1].read_text())
