"""Queries and normalization for canonical v2.1 work outlines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from scripts.outline_converter.converter import OutlineConverter
from scripts.utils.schema_validator import SchemaValidator


@dataclass(frozen=True)
class OutlineNode:
    """Flattened view of a structural outline element."""

    id: str
    type: str
    title: str
    depth: int
    parent_id: str | None
    content_file: str | None = None


class OutlineService:
    """Operate on the canonical `work.structure[*].content` tree."""

    def __init__(self, outline: dict[str, Any]):
        self.outline = self.normalize_outline(outline)
        self.work = self.outline["work"]

    @classmethod
    def from_any(cls, data: Any) -> "OutlineService":
        """Create a service from canonical YAML, old YAML, dicts, or raw text."""
        return cls(cls.normalize_outline(data))

    @staticmethod
    def normalize_outline(data: Any) -> dict[str, Any]:
        """
        Convert any outline-like data into the canonical work outline dict.

        This is the behind-the-scenes conversion point for GUI/file inputs.
        """
        if isinstance(data, Path):
            data = data.read_text()

        if isinstance(data, dict):
            if "work" in data:
                return data
            data = yaml.safe_dump(data, sort_keys=False)

        if not isinstance(data, str):
            raise TypeError(f"Unsupported outline input: {type(data)!r}")

        loaded = None
        try:
            loaded = yaml.safe_load(data)
        except yaml.YAMLError:
            loaded = None

        if isinstance(loaded, dict) and "work" in loaded:
            return loaded

        converter = OutlineConverter()
        converted = converter.convert(data, interactive=False, quiet=True)
        return yaml.safe_load(converted)

    def validate(self) -> tuple[bool, list[str]]:
        """Validate the normalized outline against the registered schema."""
        return SchemaValidator().validate(self.outline)

    def tree(self) -> list[OutlineNode]:
        """Return the structural tree as a flattened pre-order list."""
        return list(self._walk_nodes(self.work.get("structure", [])))

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Return a structural node by id."""
        for node, _, _ in self._walk_raw(self.work.get("structure", [])):
            if node.get("id") == node_id:
                return node
        return None

    def dependencies(self) -> dict[str, list[dict[str, Any]]]:
        """Return structural dependencies keyed by node id."""
        result = {}
        for node, _, _ in self._walk_raw(self.work.get("structure", [])):
            deps = node.get("dependencies", {}).get("structural", [])
            if deps:
                result[node["id"]] = deps
        return result

    def missing_fields(self) -> dict[str, list[str]]:
        """Return recommended missing fields using the schema validator."""
        return SchemaValidator().check_completeness(self.outline)

    def completion_status(self) -> dict[str, Any]:
        """Summarize outline completeness for GUI status displays."""
        nodes = self.tree()
        leaf_nodes = [node for node in nodes if not self.get_node(node.id).get("content")]
        leaves_with_content = [
            node
            for node in leaf_nodes
            if self.get_node(node.id).get("content_file")
            or self.get_node(node.id).get("content_text")
        ]
        missing = self.missing_fields()
        valid, errors = self.validate()
        return {
            "schema_valid": valid,
            "schema_errors": errors,
            "node_count": len(nodes),
            "leaf_count": len(leaf_nodes),
            "leaf_content_count": len(leaves_with_content),
            "recommended_missing_count": sum(len(items) for items in missing.values()),
            "recommended_missing": missing,
        }

    def _walk_nodes(
        self,
        nodes: Iterable[dict[str, Any]],
        depth: int = 0,
        parent_id: str | None = None,
    ) -> Iterable[OutlineNode]:
        for node in nodes:
            yield OutlineNode(
                id=node["id"],
                type=node.get("type", "section"),
                title=node.get("title", ""),
                depth=depth,
                parent_id=parent_id,
                content_file=node.get("content_file"),
            )
            yield from self._walk_nodes(node.get("content", []) or [], depth + 1, node["id"])

    def _walk_raw(
        self,
        nodes: Iterable[dict[str, Any]],
        depth: int = 0,
        parent_id: str | None = None,
    ) -> Iterable[tuple[dict[str, Any], int, str | None]]:
        for node in nodes:
            yield node, depth, parent_id
            yield from self._walk_raw(node.get("content", []) or [], depth + 1, node["id"])
