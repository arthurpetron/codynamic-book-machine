"""Citation, dependency, and concept graph analysis for canonical books."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from scripts.book.repository import BookRepository


@dataclass(frozen=True)
class GraphAnalysis:
    """Knowledge graph analysis and diagnostics."""

    citation_network: dict[str, list[str]]
    dependency_graph: dict[str, list[str]]
    concept_graph: dict[str, list[str]]
    orphan_claims: list[dict[str, str]] = field(default_factory=list)
    missing_citations: list[dict[str, str]] = field(default_factory=list)
    circular_dependencies: list[list[str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "citation_network": self.citation_network,
            "dependency_graph": self.dependency_graph,
            "concept_graph": self.concept_graph,
            "orphan_claims": self.orphan_claims,
            "missing_citations": self.missing_citations,
            "circular_dependencies": self.circular_dependencies,
        }


class KnowledgeGraphAnalyzer:
    """Build book graphs and detect common structural issues."""

    CLAIM_PATTERN = re.compile(r"\b(claim|thesis|proposition)\b\s*[:.]", re.IGNORECASE)
    CITE_PATTERN = re.compile(r"\\(?:cite|citep|citet|shortcite)(?:\[[^\]]*\])?\{([^}]+)\}")

    def __init__(self, repository: BookRepository):
        self.repository = repository

    def analyze(self) -> GraphAnalysis:
        book = self.repository.load_book()
        work = book["work"]
        citation_ids = {entry.get("id") for entry in work.get("citations", {}).get("entries", [])}
        citation_network = self._citation_network(work)
        dependency_graph = self._dependency_graph(work.get("structure", []))
        concept_graph = self._concept_graph(work.get("structure", []))
        missing_citations = self._missing_citations(citation_ids, work.get("structure", []))
        orphan_claims = self._orphan_claims(work.get("structure", []))
        circular_dependencies = self._cycles(dependency_graph)
        return GraphAnalysis(
            citation_network=citation_network,
            dependency_graph=dependency_graph,
            concept_graph=concept_graph,
            orphan_claims=orphan_claims,
            missing_citations=missing_citations,
            circular_dependencies=circular_dependencies,
        )

    def _citation_network(self, work: dict[str, Any]) -> dict[str, list[str]]:
        network: dict[str, list[str]] = {}
        for entry in work.get("citations", {}).get("entries", []):
            ref_id = entry.get("id")
            if not ref_id:
                continue
            sections = []
            for used in entry.get("used_in", []) or []:
                if used.get("section_id"):
                    sections.append(used["section_id"])
            network[ref_id] = sorted(set(sections))
        for node, _, _ in self.repository.outline_service()._walk_raw(work.get("structure", [])):
            section_id = node.get("id")
            for citation in node.get("citations", []) or []:
                ref_id = citation.get("ref_id")
                if ref_id:
                    network.setdefault(ref_id, [])
                    if section_id not in network[ref_id]:
                        network[ref_id].append(section_id)
        return {key: sorted(value) for key, value in network.items()}

    def _dependency_graph(self, nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
        graph = {}
        for node, _, _ in self.repository.outline_service()._walk_raw(nodes):
            section_id = node.get("id")
            deps = []
            for dep in node.get("dependencies", {}).get("structural", []) or []:
                if dep.get("section_id"):
                    deps.append(dep["section_id"])
            graph[section_id] = deps
        return graph

    def _concept_graph(self, nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {}
        for node, _, _ in self.repository.outline_service()._walk_raw(nodes):
            for concept in node.get("key_concepts", []) or []:
                term = concept.get("term") or concept.get("id")
                if term:
                    graph[term] = sorted(set(concept.get("related_terms", []) or []))
        return graph

    def _missing_citations(self, citation_ids: set[str], nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
        missing = []
        for node, _, _ in self.repository.outline_service()._walk_raw(nodes):
            section_id = node.get("id")
            text = self.repository.load_section(section_id)
            for match in self.CITE_PATTERN.finditer(text):
                for ref_id in [part.strip() for part in match.group(1).split(",")]:
                    if ref_id and ref_id not in citation_ids:
                        missing.append({"section_id": section_id, "ref_id": ref_id})
        return missing

    def _orphan_claims(self, nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
        orphaned = []
        for node, _, _ in self.repository.outline_service()._walk_raw(nodes):
            children = node.get("content") or []
            if children:
                continue
            section_id = node.get("id")
            text = self.repository.load_section(section_id)
            if self.CLAIM_PATTERN.search(text) and not self.CITE_PATTERN.search(text) and not node.get("citations"):
                orphaned.append({
                    "section_id": section_id,
                    "reason": "Claim-like language has no section citation or inline citation.",
                })
        return orphaned

    def _cycles(self, graph: dict[str, list[str]]) -> list[list[str]]:
        cycles = []
        visiting: list[str] = []
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                start = visiting.index(node)
                cycles.append(visiting[start:] + [node])
                return
            if node in visited:
                return
            visiting.append(node)
            for dep in graph.get(node, []):
                visit(dep)
            visiting.pop()
            visited.add(node)

        for node in graph:
            visit(node)
        return cycles
