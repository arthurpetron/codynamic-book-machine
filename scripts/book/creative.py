"""Structured diagram and artwork generation helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any

import yaml

from scripts.book.repository import BookRepository


@dataclass(frozen=True)
class DiagramSpec:
    """A structured diagram request with linguistic and computational meaning."""

    diagram_id: str
    title: str
    linguistic_description: str
    computational_definition: dict[str, Any]
    section_id: str | None = None
    caption: str = ""


@dataclass(frozen=True)
class ArtworkSpec:
    """A structured artwork request for later image generation or design work."""

    artwork_id: str
    title: str
    linguistic_description: str
    visual_style: str
    computational_definition: dict[str, Any] = field(default_factory=dict)
    section_id: str | None = None


class DiagramArtworkService:
    """Persist structured diagrams and artwork under `media/`."""

    def __init__(self, repository: BookRepository):
        self.repository = repository

    def create_diagram(self, spec: DiagramSpec) -> dict[str, Any]:
        tikz = self._tikz_from_spec(spec)
        source_path = self.repository.book_root / "media" / "diagrams" / f"{spec.diagram_id}.tikz"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(tikz)

        book = self.repository.load_book()
        diagram = {
            "id": spec.diagram_id,
            "title": spec.title,
            "caption": spec.caption or spec.linguistic_description,
            "purpose": spec.linguistic_description,
            "source_file": source_path.relative_to(self.repository.book_root).as_posix(),
            "definition": {
                "type": "structured_tikz",
                "code": tikz,
                "spec": asdict(spec),
            },
            "appears_in": (
                [{"section_id": spec.section_id, "placement": "inline"}]
                if spec.section_id else []
            ),
        }
        diagrams = [item for item in book["work"].get("diagrams", []) if item.get("id") != spec.diagram_id]
        diagrams.append(diagram)
        book["work"]["diagrams"] = diagrams
        self.repository.save_book(book)
        return diagram

    def create_artwork(self, spec: ArtworkSpec) -> dict[str, Any]:
        spec_path = self.repository.book_root / "media" / "artwork" / f"{spec.artwork_id}.yaml"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(yaml.safe_dump(asdict(spec), sort_keys=False))

        book = self.repository.load_book()
        media = {
            "id": spec.artwork_id,
            "type": "image",
            "title": spec.title,
            "caption": spec.linguistic_description,
            "purpose": spec.visual_style,
            "file": spec_path.relative_to(self.repository.book_root).as_posix(),
            "alt_text": spec.linguistic_description,
            "definition": {
                "type": "structured_artwork_spec",
                "spec": asdict(spec),
            },
        }
        items = [item for item in book["work"].get("media", []) if item.get("id") != spec.artwork_id]
        items.append(media)
        book["work"]["media"] = items
        self.repository.save_book(book)
        return media

    def _tikz_from_spec(self, spec: DiagramSpec) -> str:
        definition = spec.computational_definition or {}
        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        if not nodes:
            label = self._escape_tikz(spec.title)
            return "\\begin{tikzpicture}\n  \\node[draw, rounded corners] {"+label+"};\n\\end{tikzpicture}\n"

        lines = [
            "\\begin{tikzpicture}[>=stealth, node distance=2.2cm]",
        ]
        for index, node in enumerate(nodes):
            node_id = self._safe_id(str(node.get("id") or f"n{index + 1}"))
            label = self._escape_tikz(str(node.get("label") or node_id))
            x = node.get("x", index * 2.4)
            y = node.get("y", 0)
            lines.append(f"  \\node[draw, rounded corners] ({node_id}) at ({x},{y}) {{{label}}};")
        for edge in edges:
            source = self._safe_id(str(edge.get("from")))
            target = self._safe_id(str(edge.get("to")))
            label = self._escape_tikz(str(edge.get("label", "")))
            label_text = f" node[midway, above] {{{label}}}" if label else ""
            lines.append(f"  \\draw[->] ({source}) --{label_text} ({target});")
        lines.append("\\end{tikzpicture}\n")
        return "\n".join(lines)

    def _safe_id(self, value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "_", value) or "node"

    def _escape_tikz(self, value: str) -> str:
        return value.replace("\\", "\\textbackslash{}").replace("&", "\\&").replace("%", "\\%")
