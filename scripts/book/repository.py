"""Repository API for canonical book projects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts.book.artifact_registry import ArtifactRegistry
from scripts.book.authoring import AuthoringLoop, MediaRequestRegistry, ProposalStore, VerificationHistory
from scripts.book.intake import BookIntakeService, IntakeQuestion
from scripts.book.outline_service import OutlineService


class BookRepository:
    """Read and write a book rooted under `data/book_data/<book_id>`."""

    def __init__(self, book_root: Path):
        self.book_root = Path(book_root)
        self.outline_path = self.book_root / "outline" / f"{self.book_root.name}.yaml"
        if not self.outline_path.exists():
            yaml_files = sorted((self.book_root / "outline").glob("*.yaml"))
            if yaml_files:
                self.outline_path = yaml_files[0]
        self.artifacts = ArtifactRegistry(self.book_root)
        self.proposals = ProposalStore(self.book_root)
        self.verification_history = VerificationHistory(self.book_root)
        self.media_requests = MediaRequestRegistry(self.book_root)

    def load_book(self) -> dict[str, Any]:
        """Load and normalize the book outline."""
        return OutlineService.normalize_outline(self.outline_path)

    def save_book(self, book: dict[str, Any]) -> None:
        """Save a canonical book outline."""
        canonical = OutlineService.normalize_outline(book)
        self.outline_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.outline_path, "w") as f:
            yaml.safe_dump(canonical, f, sort_keys=False, allow_unicode=True)

    def outline_service(self) -> OutlineService:
        """Return an outline service for the current book."""
        return OutlineService(self.load_book())

    def load_section(self, section_id: str) -> str:
        """Load section content by canonical content_file or legacy TeX payload."""
        node = self.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")

        content_file = node.get("content_file")
        candidates = []
        if content_file:
            candidates.append(self.book_root / content_file)
        candidates.append(self.book_root / "tex" / "section_payloads" / f"{section_id}.tex")

        for path in candidates:
            if path.exists():
                return path.read_text()
        return ""

    def save_section(self, section_id: str, content: str) -> Path:
        """Save section content to the canonical content_file location."""
        service = self.outline_service()
        node = service.get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")

        content_file = node.get("content_file") or f"content/sections/{section_id}.md"
        path = self.book_root / content_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def diagrams(self) -> list[dict[str, Any]]:
        """Return diagram metadata from the canonical book object."""
        return self.load_book()["work"].get("diagrams", [])

    def artwork(self) -> list[dict[str, Any]]:
        """Return image/artwork metadata from the canonical media list."""
        return [
            media
            for media in self.load_book()["work"].get("media", [])
            if media.get("type") in {"image", "cover"} or "artwork" in media.get("file", "")
        ]

    def metadata(self) -> dict[str, Any]:
        """Return canonical work metadata."""
        return self.load_book()["work"].get("metadata", {})

    def intake_service(self) -> BookIntakeService:
        """Return an intake service bound to the current canonical book."""
        if self.outline_path.exists():
            return BookIntakeService(self.load_book())
        return BookIntakeService()

    def next_intake_question(self) -> IntakeQuestion | None:
        """Return the next unanswered conversational intake question."""
        return self.intake_service().next_question()

    def record_intake_answer(
        self,
        question_id: str,
        answer: str,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        """Persist one intake answer into the canonical book object."""
        service = self.intake_service()
        book = service.record_answer(question_id, answer, rationale=rationale)
        self.save_book(book)
        return book

    def generate_initial_plan(self) -> dict[str, Any]:
        """Generate and persist the first conversation-derived plan."""
        service = self.intake_service()
        book = service.generate_initial_plan()
        self.save_book(book)
        return book

    def authoring_loop(self, mode: str = "proposal") -> AuthoringLoop:
        """Return the proposal-first authoring loop facade for this book."""
        return AuthoringLoop(self.book_root, mode=mode)

    def design_settings(self, project_root: Path | str = Path(".")) -> DesignSettingsService:
        """Return persisted design settings service for this book."""
        from scripts.book.typesetting import DesignSettingsService

        return DesignSettingsService(self, project_root=project_root)

    def latex_builder(self, project_root: Path | str = Path(".")) -> LatexBuildService:
        """Return LaTeX assembly and compile service for this book."""
        from scripts.book.typesetting import LatexBuildService

        return LatexBuildService(self.book_root, project_root=project_root)

    def diagram_artwork(self):
        """Return structured diagram/artwork service for this book."""
        from scripts.book.creative import DiagramArtworkService

        return DiagramArtworkService(self)

    def knowledge_graph(self):
        """Return citation/dependency/concept graph analyzer for this book."""
        from scripts.book.knowledge_graph import KnowledgeGraphAnalyzer

        return KnowledgeGraphAnalyzer(self)

    def refresh_artifacts(self):
        """Scan conventional artifact directories and persist artifact metadata."""
        return self.artifacts.refresh()
