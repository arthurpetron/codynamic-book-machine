"""Tests for canonical book object APIs and migration."""

from pathlib import Path

import yaml

from scripts.api import LLMResponse
from scripts.book import ArtifactRegistry, BookRepository, OutlineService
from scripts.outline_converter.converter import OutlineConverter


LEGACY_OUTLINE = """
outline:
  title: "Example Book"
  summary: "A short test outline."
  intent:
    audience: "Readers"
    writing_style: "Clear"
    author_persona: "Guide"
    reader_takeaway: "Understanding"
    genre: "Nonfiction"
  chapters:
    - id: "ch01"
      title: "Opening"
      goal: "Start"
      summary: "Introduces the book."
      sections:
        - id: "ch01_sec01"
          title: "First Section"
          content_summary: "The first section."
  diagrams:
    - id: "diag01"
      title: "Loop"
      description: "A feedback loop."
      computational_definition: "pending"
  artwork:
    - id: "img01"
      title: "Cover"
      description: "Cover art."
      file: "artwork/cover.png"
  metadata:
    author: "Example Author"
    version: 0.1
    created: 2026-05-26
    updated: 2026-05-26
    maintained_by: "author"
"""


def test_converter_outputs_canonical_valid_outline():
    converter = OutlineConverter()
    outline = yaml.safe_load(converter.convert(LEGACY_OUTLINE, interactive=False, quiet=True))

    service = OutlineService(outline)
    valid, errors = service.validate()

    assert valid, errors
    assert outline["work"]["structure"][0]["content"][0]["content_file"] == "content/sections/ch01_sec01.md"
    assert outline["work"]["diagrams"][0]["id"] == "diag01"
    assert outline["work"]["media"][0]["file"] == "artwork/cover.png"
    assert converter.last_report["source_format"] == "yaml_v1"


def test_outline_service_normalizes_text_and_reports_status():
    service = OutlineService.from_any(LEGACY_OUTLINE)

    tree = service.tree()
    status = service.completion_status()

    assert [node.id for node in tree] == ["ch01", "ch01_sec01"]
    assert status["schema_valid"] is True
    assert status["leaf_count"] == 1
    assert status["leaf_content_count"] == 1


def test_book_repository_loads_sections_and_artifacts(tmp_path):
    book_root = tmp_path / "example_book"
    outline_dir = book_root / "outline"
    section_dir = book_root / "content" / "sections"
    tex_dir = book_root / "tex"
    render_dir = book_root / "renders"
    outline_dir.mkdir(parents=True)
    section_dir.mkdir(parents=True)
    tex_dir.mkdir(parents=True)
    render_dir.mkdir(parents=True)

    outline = yaml.safe_load(OutlineConverter().convert(LEGACY_OUTLINE, interactive=False, quiet=True))
    (outline_dir / "example_book.yaml").write_text(yaml.safe_dump(outline, sort_keys=False))
    (section_dir / "ch01_sec01.md").write_text("Section body")
    (tex_dir / "example_book.tex").write_text("\\begin{document}\\end{document}")
    (render_dir / "page-1.png").write_text("fake image")

    repository = BookRepository(book_root)
    artifacts = repository.refresh_artifacts()

    assert repository.load_book()["work"]["title"] == "Example Book"
    assert repository.load_section("ch01_sec01") == "Section body"
    assert repository.diagrams()[0]["title"] == "Loop"
    assert repository.artwork()[0]["title"] == "Cover"
    assert {artifact.kind for artifact in artifacts} >= {"tex", "render"}


def test_artifact_registry_round_trips(tmp_path):
    registry = ArtifactRegistry(tmp_path)
    artifacts = registry.refresh()

    assert artifacts == []
    assert registry.load() == {"artifacts": []}


class MockOutlineProvider:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def simple_prompt(self, prompt, system_prompt=None, **kwargs):
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "kwargs": kwargs,
        })
        return LLMResponse(content=self.content, model="mock", provider="mock")


def test_converter_uses_llm_for_unknown_outline_text():
    canonical_json = """
{
  "work": {
    "id": "field_notes",
    "type": "book",
    "title": "Field Notes",
    "metadata": {
      "version": "0.1.0",
      "created": "2026-05-26",
      "updated": "2026-05-26"
    },
    "structure": [
      {
        "type": "chapter",
        "id": "arrival",
        "title": "Arrival",
        "content_file": "content/sections/arrival.md"
      }
    ]
  }
}
"""
    provider = MockOutlineProvider(canonical_json)
    converter = OutlineConverter(llm_provider=provider)

    output = converter.convert(
        "A loose idea for a book: Field Notes. First chapter: Arrival.",
        interactive=False,
        quiet=True,
        use_llm="auto",
    )
    outline = yaml.safe_load(output)

    assert outline["work"]["id"] == "field_notes"
    assert outline["work"]["structure"][0]["id"] == "arrival"
    assert converter.last_report["llm_used"] is True
    assert provider.calls


def test_converter_can_force_llm_for_known_format():
    provider = MockOutlineProvider(yaml.safe_dump(yaml.safe_load(OutlineConverter().convert(
        LEGACY_OUTLINE,
        interactive=False,
        quiet=True,
        use_llm="never",
    ))))
    converter = OutlineConverter(llm_provider=provider)

    output = converter.convert(
        LEGACY_OUTLINE,
        interactive=False,
        quiet=True,
        use_llm="always",
    )

    assert yaml.safe_load(output)["work"]["title"] == "Example Book"
    assert converter.last_report["llm_used"] is True
    assert len(provider.calls) == 1
