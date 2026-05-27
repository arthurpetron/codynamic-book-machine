"""Artifact tracking for canonical book projects."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

import yaml


ARTIFACT_DIRECTORIES = {
    "tex": ("tex", ".tex"),
    "section_payload": ("tex/section_payloads", ".tex"),
    "content_section": ("content/sections", ".md"),
    "diagram": ("media/diagrams", None),
    "media": ("media", None),
    "image": ("images", None),
    "artwork": ("artwork", None),
    "render": ("renders", None),
    "log": ("logs", None),
}


@dataclass(frozen=True)
class Artifact:
    """A file produced by or attached to a book project."""

    artifact_id: str
    kind: str
    path: str
    reusable: bool = False
    source_section_id: str | None = None
    title: str | None = None


class ArtifactRegistry:
    """Load, save, and discover book artifacts under a book root."""

    def __init__(self, book_root: Path):
        self.book_root = Path(book_root)
        self.registry_path = self.book_root / "artifacts" / "registry.yaml"

    def load(self) -> dict[str, Any]:
        """Load the persisted artifact registry, if present."""
        if not self.registry_path.exists():
            return {"artifacts": []}
        with open(self.registry_path, "r") as f:
            data = yaml.safe_load(f) or {}
        data.setdefault("artifacts", [])
        return data

    def save(self, artifacts: Iterable[Artifact | dict[str, Any]]) -> None:
        """Persist artifacts to the book's artifact registry."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for artifact in artifacts:
            payload.append(asdict(artifact) if isinstance(artifact, Artifact) else artifact)
        with open(self.registry_path, "w") as f:
            yaml.safe_dump({"artifacts": payload}, f, sort_keys=False)

    def discover(self) -> list[Artifact]:
        """Scan conventional artifact directories and return tracked files."""
        artifacts = []
        for kind, (relative_dir, suffix) in ARTIFACT_DIRECTORIES.items():
            directory = self.book_root / relative_dir
            if not directory.exists():
                continue
            for path in sorted(p for p in directory.rglob("*") if p.is_file()):
                if suffix and path.suffix != suffix:
                    continue
                relative_path = path.relative_to(self.book_root).as_posix()
                artifact_id = f"{kind}__{relative_path.replace('/', '__').replace('.', '_')}"
                artifacts.append(
                    Artifact(
                        artifact_id=artifact_id,
                        kind=kind,
                        path=relative_path,
                        reusable=kind in {"diagram", "media", "image", "artwork", "section_payload"},
                    )
                )
        return artifacts

    def refresh(self) -> list[Artifact]:
        """Discover artifacts and persist the registry."""
        artifacts = self.discover()
        self.save(artifacts)
        return artifacts
