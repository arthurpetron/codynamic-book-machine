"""Tests for Phase 7 beyond-MVP capabilities."""

from pathlib import Path

import yaml

from scripts.book import (
    ArtworkSpec,
    BookRepository,
    ChangeSetManager,
    DiagramSpec,
    KnowledgeGraphAnalyzer,
)
from scripts.outline_converter.converter import OutlineConverter


LEGACY_OUTLINE = """
outline:
  title: "Graph Book"
  summary: "A book with graph diagnostics."
  intent:
    audience: "Researchers"
    writing_style: "Clear"
    author_persona: "Guide"
    reader_takeaway: "Graph discipline"
    genre: "Nonfiction"
  chapters:
    - id: "ch01"
      title: "Opening"
      sections:
        - id: "a"
          title: "First"
          content_summary: "First section."
        - id: "b"
          title: "Second"
          content_summary: "Second section."
"""


def create_book(tmp_path: Path) -> BookRepository:
    outline = yaml.safe_load(OutlineConverter().convert(LEGACY_OUTLINE, interactive=False, quiet=True))
    work = outline["work"]
    work["citations"]["entries"] = [
        {
            "id": "known2026",
            "type": "book",
            "title": "Known Work",
            "year": 2026,
            "used_in": [{"section_id": "a", "context": "support"}],
        }
    ]
    a = work["structure"][0]["content"][0]
    b = work["structure"][0]["content"][1]
    a["dependencies"]["structural"] = [{"section_id": "b", "dependency_type": "builds_on"}]
    b["dependencies"]["structural"] = [{"section_id": "a", "dependency_type": "builds_on"}]
    a["key_concepts"] = [
        {
            "id": "concept_a",
            "term": "Codynamic claim",
            "definition": "A claim about codynamics.",
            "related_terms": ["Dependency"],
        }
    ]
    repository = BookRepository(tmp_path / "graph_book")
    repository.save_book(outline)
    repository.save_section("a", "Claim: this needs support.\n")
    repository.save_section("b", "This cites a missing source \\cite{missing2026}.\n")
    return repository


def test_structured_diagram_is_saved_under_media_diagrams_and_book_object(tmp_path):
    repository = create_book(tmp_path)
    spec = DiagramSpec(
        diagram_id="flow",
        title="Flow",
        linguistic_description="A source flows into a target.",
        computational_definition={
            "nodes": [
                {"id": "source", "label": "Source", "x": 0, "y": 0},
                {"id": "target", "label": "Target", "x": 2, "y": 0},
            ],
            "edges": [{"from": "source", "to": "target", "label": "feeds"}],
        },
        section_id="a",
    )

    diagram = repository.diagram_artwork().create_diagram(spec)
    saved = repository.load_book()["work"]["diagrams"][-1]

    assert diagram["source_file"] == "media/diagrams/flow.tikz"
    assert (repository.book_root / "media" / "diagrams" / "flow.tikz").exists()
    assert "structured_tikz" == saved["definition"]["type"]
    assert saved["appears_in"][0]["section_id"] == "a"


def test_structured_artwork_spec_is_saved_under_media_artwork(tmp_path):
    repository = create_book(tmp_path)
    spec = ArtworkSpec(
        artwork_id="cover_direction",
        title="Cover Direction",
        linguistic_description="A clean abstract cover.",
        visual_style="minimal, high contrast",
        section_id="a",
    )

    media = repository.diagram_artwork().create_artwork(spec)

    assert media["file"] == "media/artwork/cover_direction.yaml"
    assert media["definition"]["type"] == "structured_artwork_spec"
    assert (repository.book_root / media["file"]).exists()


def test_knowledge_graph_detects_missing_citations_orphan_claims_and_cycles(tmp_path):
    repository = create_book(tmp_path)

    analysis = KnowledgeGraphAnalyzer(repository).analyze().as_dict()

    assert analysis["citation_network"]["known2026"] == ["a"]
    assert analysis["concept_graph"]["Codynamic claim"] == ["Dependency"]
    assert {"section_id": "missing2026"} not in analysis["missing_citations"]
    assert analysis["missing_citations"] == [{"section_id": "b", "ref_id": "missing2026"}]
    assert analysis["orphan_claims"][0]["section_id"] == "a"
    assert analysis["circular_dependencies"] == [["a", "b", "a"]]


def test_changeset_manager_writes_json_and_diff_bundle(tmp_path, monkeypatch):
    manager = ChangeSetManager(tmp_path)
    (tmp_path / "draft.txt").write_text("changed\n")
    monkeypatch.setattr(manager, "_git", lambda args, default="": "abc123" if args[0] == "rev-parse" else "diff --git a/draft.txt b/draft.txt\n")

    changeset = manager.create(
        title="Agent edits",
        agent_id="section_agent",
        files=["draft.txt"],
    )

    loaded = manager.load(changeset.changeset_id)
    assert loaded.base_ref == "abc123"
    assert loaded.branch_name.startswith("codex/section_agent/")
    assert (tmp_path / "proposals" / "changesets" / f"{changeset.changeset_id}.diff").read_text().startswith("diff --git")
