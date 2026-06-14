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
    invalid_dependencies: list[dict[str, str]] = field(default_factory=list)
    circular_dependencies: list[list[str]] = field(default_factory=list)
    citation_occurrences: list[dict[str, str]] = field(default_factory=list)
    concept_graph_visualization: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "citation_network": self.citation_network,
            "dependency_graph": self.dependency_graph,
            "concept_graph": self.concept_graph,
            "orphan_claims": self.orphan_claims,
            "missing_citations": self.missing_citations,
            "invalid_dependencies": self.invalid_dependencies,
            "circular_dependencies": self.circular_dependencies,
            "citation_occurrences": self.citation_occurrences,
            "concept_graph_visualization": self.concept_graph_visualization,
        }


class KnowledgeGraphAnalyzer:
    """Build book graphs and detect common structural issues."""

    CLAIM_PATTERN = re.compile(
        r"(\b(claim|thesis|proposition|conjecture|lemma|theorem|corollary)\b\s*[:.]|"
        r"\b(we show|we prove|this shows|therefore|hence)\b)",
        re.IGNORECASE,
    )
    LATEX_CITE_PATTERN = re.compile(
        r"\\(?:[A-Za-z]*cite[A-Za-z]*|citeauthor|citeyear)"
        r"(?:\s*\[[^\]]*\]){0,2}\s*\{([^}]+)\}"
    )
    MARKDOWN_CITE_PATTERN = re.compile(r"(?<![\w.-])@([A-Za-z0-9_./:-]+)")

    def __init__(self, repository: BookRepository):
        self.repository = repository

    def analyze(self) -> GraphAnalysis:
        book = self.repository.load_book()
        work = book["work"]
        citation_ids = {entry.get("id") for entry in work.get("citations", {}).get("entries", [])}
        citation_occurrences = self._citation_occurrences(work.get("structure", []))
        citation_network = self._citation_network(work, citation_occurrences)
        dependency_graph = self._dependency_graph(work.get("structure", []))
        concept_graph = self._concept_graph(work.get("structure", []))
        missing_citations = self._missing_citations(citation_ids, citation_occurrences)
        invalid_dependencies = self._invalid_dependencies(dependency_graph)
        orphan_claims = self._orphan_claims(work.get("structure", []))
        circular_dependencies = self._cycles(dependency_graph)
        concept_graph_visualization = self._concept_graph_visualization(concept_graph)
        return GraphAnalysis(
            citation_network=citation_network,
            dependency_graph=dependency_graph,
            concept_graph=concept_graph,
            orphan_claims=orphan_claims,
            missing_citations=missing_citations,
            invalid_dependencies=invalid_dependencies,
            circular_dependencies=circular_dependencies,
            citation_occurrences=citation_occurrences,
            concept_graph_visualization=concept_graph_visualization,
        )

    def _citation_network(
        self,
        work: dict[str, Any],
        citation_occurrences: list[dict[str, str]],
    ) -> dict[str, list[str]]:
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
        for occurrence in citation_occurrences:
            ref_id = occurrence["ref_id"]
            section_id = occurrence["section_id"]
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

    def _citation_occurrences(self, nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
        occurrences = []
        seen = set()
        for node, _, _ in self.repository.outline_service()._walk_raw(nodes):
            children = node.get("content") or []
            if children:
                continue
            section_id = node.get("id")
            text = self.repository.load_section(section_id)
            for line_number, line in enumerate(text.splitlines(), 1):
                for ref_id, syntax in self._extract_citations(line):
                    key = (section_id, ref_id, line_number, syntax)
                    if key in seen:
                        continue
                    seen.add(key)
                    occurrences.append({
                        "section_id": section_id,
                        "ref_id": ref_id,
                        "line": str(line_number),
                        "syntax": syntax,
                    })
        return occurrences

    def _extract_citations(self, text: str) -> list[tuple[str, str]]:
        citations = []
        for match in self.LATEX_CITE_PATTERN.finditer(text):
            for ref_id in self._split_ref_ids(match.group(1)):
                citations.append((ref_id, "latex"))
        for match in self.MARKDOWN_CITE_PATTERN.finditer(text):
            ref_id = match.group(1).rstrip(".,;:])}")
            if ref_id:
                citations.append((ref_id, "markdown"))
        return citations

    def _split_ref_ids(self, value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    def _missing_citations(
        self,
        citation_ids: set[str],
        citation_occurrences: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        missing = []
        seen = set()
        for occurrence in citation_occurrences:
            ref_id = occurrence["ref_id"]
            if ref_id in citation_ids:
                continue
            key = (occurrence["section_id"], ref_id)
            if key in seen:
                continue
            seen.add(key)
            missing.append({
                "section_id": occurrence["section_id"],
                "ref_id": ref_id,
                "line": occurrence.get("line", ""),
                "syntax": occurrence.get("syntax", ""),
            })
        return missing

    def _invalid_dependencies(self, dependency_graph: dict[str, list[str]]) -> list[dict[str, str]]:
        node_ids = set(dependency_graph)
        invalid = []
        for section_id, dependencies in dependency_graph.items():
            for dep_id in dependencies:
                if dep_id not in node_ids:
                    invalid.append({
                        "section_id": section_id,
                        "dependency_id": dep_id,
                        "reason": "Dependency target is not a canonical outline node id.",
                    })
        return invalid

    def _orphan_claims(self, nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
        orphaned = []
        for node, _, _ in self.repository.outline_service()._walk_raw(nodes):
            children = node.get("content") or []
            if children:
                continue
            section_id = node.get("id")
            text = self.repository.load_section(section_id)
            node_citations = node.get("citations") or []
            for paragraph in self._paragraphs_with_lines(text):
                if not self.CLAIM_PATTERN.search(paragraph["text"]):
                    continue
                if self._extract_citations(paragraph["text"]) or node_citations:
                    continue
                orphaned.append({
                    "section_id": section_id,
                    "line": str(paragraph["line"]),
                    "excerpt": paragraph["text"][:180],
                    "reason": "Claim-like paragraph has no section citation or inline citation.",
                })
        return orphaned

    def _paragraphs_with_lines(self, text: str) -> list[dict[str, Any]]:
        paragraphs = []
        current: list[str] = []
        start_line = 1
        for line_number, line in enumerate(text.splitlines(), 1):
            if line.strip():
                if not current:
                    start_line = line_number
                current.append(line.strip())
                continue
            if current:
                paragraphs.append({"line": start_line, "text": " ".join(current)})
                current = []
        if current:
            paragraphs.append({"line": start_line, "text": " ".join(current)})
        return paragraphs

    def _concept_graph_visualization(self, concept_graph: dict[str, list[str]]) -> dict[str, Any]:
        nodes = sorted(set(concept_graph) | {item for related in concept_graph.values() for item in related})
        edges = [
            {"from": term, "to": related}
            for term, related_terms in sorted(concept_graph.items())
            for related in related_terms
        ]
        mermaid_lines = ["flowchart LR"]
        for node in nodes:
            mermaid_lines.append(f"  {self._mermaid_id(node)}[\"{self._escape_mermaid(node)}\"]")
        for edge in edges:
            mermaid_lines.append(
                f"  {self._mermaid_id(edge['from'])} --> {self._mermaid_id(edge['to'])}"
            )
        return {"nodes": nodes, "edges": edges, "mermaid": "\n".join(mermaid_lines)}

    def _mermaid_id(self, value: str) -> str:
        clean = re.sub(r"[^A-Za-z0-9_]", "_", value).strip("_")
        return f"concept_{clean or 'node'}"

    def _escape_mermaid(self, value: str) -> str:
        return str(value).replace('"', '\\"')

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
