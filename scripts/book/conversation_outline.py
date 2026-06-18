"""Open-ended conversation to canonical outline synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import re
from typing import Any

import yaml

from scripts.api import LLMProvider, LLMProviderError, get_provider_with_fallback
from scripts.outline_converter.converter import OutlineConverter


@dataclass(frozen=True)
class ConversationOutlineResult:
    """Persisted outline synthesized from a chat transcript."""

    outline: dict[str, Any]
    outline_path: Path
    title: str
    work_id: str
    provider: str
    model: str

    def as_dict(self) -> dict[str, str]:
        return {
            "outline_path": str(self.outline_path),
            "title": self.title,
            "work_id": self.work_id,
            "provider": self.provider,
            "model": self.model,
        }


class ConversationOutlineService:
    """Convert a free-form author conversation into a canonical work outline."""

    def __init__(
        self,
        book_data_dir: Path | str = Path("data/book_data"),
        provider: LLMProvider | None = None,
    ):
        self.book_data_dir = Path(book_data_dir)
        self.provider = provider

    def synthesize(
        self,
        messages: list[dict[str, Any]],
        use_llm: str | bool = "auto",
    ) -> dict[str, Any]:
        transcript = self._transcript(messages)
        if not transcript.strip():
            raise ValueError("Conversation is empty.")
        if use_llm != "never":
            try:
                return self._synthesize_with_llm(transcript)
            except LLMProviderError:
                if use_llm == "always":
                    raise
            except Exception:
                if use_llm == "always":
                    raise
        return self._synthesize_deterministically(transcript)

    def synthesize_to_file(
        self,
        messages: list[dict[str, Any]],
        use_llm: str | bool = "auto",
    ) -> ConversationOutlineResult:
        outline = self.synthesize(messages, use_llm=use_llm)
        outline = self._ensure_unique_work_id(outline)
        work = outline["work"]
        output_dir = self.book_data_dir / "_conversation_outlines"
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{work['id']}.yaml"
        path.write_text(yaml.safe_dump(outline, sort_keys=False, allow_unicode=True))
        metadata = work.get("metadata", {})
        return ConversationOutlineResult(
            outline=outline,
            outline_path=path,
            title=str(work.get("title") or work["id"]),
            work_id=str(work["id"]),
            provider=str(metadata.get("conversation_outline_provider") or "deterministic"),
            model=str(metadata.get("conversation_outline_model") or "fallback"),
        )

    def reply(
        self,
        messages: list[dict[str, Any]],
        use_llm: str | bool = "auto",
    ) -> str:
        """Return the next conversational response for outline discovery."""
        transcript = self._transcript(messages)
        if use_llm != "never":
            try:
                return self._reply_with_llm(transcript)
            except LLMProviderError:
                if use_llm == "always":
                    raise
            except Exception:
                if use_llm == "always":
                    raise
        return self._reply_deterministically(messages)

    def _reply_with_llm(self, transcript: str) -> str:
        provider = self.provider or get_provider_with_fallback()
        response = provider.simple_prompt(
            prompt=(
                "Continue this outline-discovery conversation for a new book.\n"
                "Ask one useful next question or, if enough has been supplied, say that the outline can be created now.\n"
                "Do not repeat a question already asked. Keep the response under 120 words.\n\n"
                f"Conversation transcript:\n{transcript[:16000]}"
            ),
            system_prompt=(
                "You are a concise Socratic outlining partner inside the Codynamic Book Machine. "
                "You help the author clarify title, audience, scope, structure, sources, diagrams, constraints, and desired output."
            ),
            temperature=0.35,
            max_tokens=260,
        )
        return response.content.strip()

    def _synthesize_with_llm(self, transcript: str) -> dict[str, Any]:
        provider = self.provider or get_provider_with_fallback()
        prompt = (
            "Convert the full author conversation into a detailed canonical YAML outline for the Codynamic Book Machine.\n"
            "Return only YAML. Do not wrap it in Markdown fences.\n\n"
            "Requirements:\n"
            "- Top-level key must be work.\n"
            "- Include work.id, work.title, work.summary, work.metadata, work.intent, work.structure, work.front_matter, work.back_matter, work.citations, work.diagrams, and work.media.\n"
            "- work.structure must contain chapters with stable ids, titles, goals, summaries, dependencies, prerequisites, and leaf sections.\n"
            "- Leaf sections must include id, type: section, title, goal, summary, dependencies, prerequisites, key_concepts, citations, and content_file.\n"
            "- Prefer 5 to 9 chapters and 2 to 5 sections per chapter unless the conversation clearly asks otherwise.\n"
            "- Preserve uncertainty explicitly in goals/summaries rather than inventing unsupported specifics.\n"
            "- The outline should be detailed enough for section agents to draft a complete PDF book.\n\n"
            "Conversation transcript:\n"
            f"{transcript[:28000]}\n"
        )
        response = provider.simple_prompt(
            prompt=prompt,
            system_prompt=(
                "You are an outline architect for the Codynamic Book Machine. "
                "You output schema-compatible YAML and preserve authorial intent."
            ),
            temperature=0.2,
            max_tokens=6000,
        )
        outline = self._parse_yaml_response(response.content)
        outline = self._normalize(outline)
        metadata = outline["work"].setdefault("metadata", {})
        metadata["conversation_outline_provider"] = response.provider
        metadata["conversation_outline_model"] = response.model
        metadata["conversation_outline_generated_at"] = datetime.now().isoformat()
        return outline

    def _synthesize_deterministically(self, transcript: str) -> dict[str, Any]:
        title = self._title_from_transcript(transcript)
        summary = self._summary_from_transcript(transcript)
        themes = self._themes(transcript)
        chapter_titles = self._chapter_titles(themes)
        structure = []
        for chapter_index, chapter_title in enumerate(chapter_titles, start=1):
            chapter_id = f"ch{chapter_index:02d}_{self._slug(chapter_title)[:28]}"
            sections = self._sections_for_chapter(chapter_id, chapter_title, chapter_index)
            structure.append({
                "id": chapter_id,
                "type": "chapter",
                "title": chapter_title,
                "goal": f"Develop the {chapter_title.lower()} dimension of {title}.",
                "summary": f"This chapter makes the {chapter_title.lower()} part of the project explicit and draftable.",
                "dependencies": {"structural": [], "narrative": ""},
                "prerequisites": [],
                "key_concepts": themes[:6],
                "citations": [],
                "content": sections,
            })
        canonical = OutlineConverter().map_to_schema_v2(
            {
                "title": title,
                "summary": summary,
                "structure": structure,
            },
            interactive=False,
        )
        work = canonical["work"]
        work["id"] = self._slug(title)
        work["intent"] = {
            "audience": "Readers identified through the outline conversation.",
            "reader_takeaway": "Understand the manuscript's core argument, architecture, and implications.",
            "writing_style": "Clear, technical, constructive, and concrete.",
            "genre": "book",
        }
        work["metadata"].update({
            "created": datetime.now().strftime("%Y-%m-%d"),
            "updated": datetime.now().strftime("%Y-%m-%d"),
            "version": "0.1.0",
            "conversation_outline_provider": "deterministic",
            "conversation_outline_model": "fallback",
            "conversation_outline_generated_at": datetime.now().isoformat(),
            "conversation_excerpt": transcript[:4000],
        })
        work.setdefault("front_matter", {})["preface"] = {
            "enabled": True,
            "content_file": "content/front_matter/preface.md",
        }
        work.setdefault("back_matter", {}).setdefault("appendices", [])
        work.setdefault("citations", {"entries": []})
        work.setdefault("diagrams", [])
        work.setdefault("media", [])
        return self._normalize(canonical)

    def _reply_deterministically(self, messages: list[dict[str, Any]]) -> str:
        transcript = self._transcript(messages).lower()
        asked = "\n".join(
            str(item.get("content") or "").lower()
            for item in messages
            if str(item.get("role") or "").lower() == "assistant"
        )
        checks = [
            (
                "audience",
                ["audience", "reader", "readers", "for technical", "for beginners", "for experts"],
                ["who is the reader", "who is it for", "primary reader", "what level"],
                "Who is the primary reader, and what level of pool or billiards knowledge should the book assume?",
            ),
            (
                "scope",
                ["apa", "bca", "english", "snooker", "poker", "games", "rules"],
                ["which rulesets", "which games", "mandatory", "what book are we making"],
                "Which rulesets or games are mandatory, and which can be treated as optional variants or appendices?",
            ),
            (
                "structure",
                ["chapter", "section", "part", "structure", "organize"],
                ["how should the book be organized", "major parts", "chapters"],
                "How should the book be organized: by governing body, by game family, by table/equipment type, or by learning path?",
            ),
            (
                "research",
                ["research", "source", "citation", "official", "reference"],
                ["source standard", "rules conflict", "official governing"],
                "What source standard should the book use when rules conflict: official governing-body rules, common house rules, or both with clear labels?",
            ),
            (
                "visuals",
                ["diagram", "figure", "table", "chart", "visual"],
                ["visual aids", "rack diagrams", "table layouts"],
                "What visual aids should be planned: rack diagrams, table layouts, foul/penalty tables, comparison matrices, or shot examples?",
            ),
            (
                "voice",
                ["voice", "style", "tone", "practical", "reference", "guide"],
                ["finished book read", "rules reference", "teaching guide"],
                "Should the finished book read like a rules reference, a teaching guide, a comparative encyclopedia, or a player handbook?",
            ),
        ]
        for key, signals, asked_markers, question in checks:
            if key in asked or any(marker in asked for marker in asked_markers):
                continue
            if not any(signal in transcript for signal in signals):
                return question
        if "create" not in asked and "outline" not in asked:
            return (
                "I have enough to create a first outline. Before you press the button, add any must-include games, "
                "official sources, or house-rule boundaries that should not be lost."
            )
        return "That gives me enough context. Press Create Outline from Conversation when you want me to turn this transcript into the book outline."

    def _normalize(self, outline: dict[str, Any]) -> dict[str, Any]:
        if isinstance(outline.get("work"), dict):
            canonical = outline
        else:
            canonical = OutlineConverter().map_to_schema_v2(outline, interactive=False)
        work = canonical["work"]
        work["id"] = self._slug(str(work.get("id") or work.get("title") or "conversation_book"))
        work.setdefault("metadata", {})
        work.setdefault("front_matter", {})
        work.setdefault("back_matter", {})
        work.setdefault("citations", {"entries": []})
        work.setdefault("diagrams", [])
        work.setdefault("media", [])
        self._normalize_nodes(work.get("structure", []))
        return canonical

    def _normalize_nodes(self, nodes: list[dict[str, Any]], chapter_prefix: str = "") -> None:
        for index, node in enumerate(nodes, start=1):
            title = str(node.get("title") or f"Untitled {index}")
            fallback_id = f"{chapter_prefix}{index:02d}_{self._slug(title)[:28]}".strip("_")
            node["id"] = self._slug(str(node.get("id") or fallback_id))
            node.setdefault("type", "chapter" if node.get("content") else "section")
            node.setdefault("goal", node.get("summary") or f"Develop {title}.")
            node.setdefault("summary", node.get("goal") or f"Develop {title}.")
            node.setdefault("dependencies", {"structural": [], "narrative": ""})
            node.setdefault("prerequisites", [])
            node.setdefault("key_concepts", [])
            node.setdefault("citations", [])
            children = node.get("content") or []
            if children:
                self._normalize_nodes(children, f"{node['id']}_")
            else:
                node.setdefault("content_file", f"content/sections/{node['id']}.md")

    def _ensure_unique_work_id(self, outline: dict[str, Any]) -> dict[str, Any]:
        work = outline["work"]
        base_id = self._slug(str(work.get("id") or work.get("title") or "conversation_book"))
        suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        work["id"] = f"{base_id}_{suffix}"
        metadata = work.setdefault("metadata", {})
        metadata["conversation_outline_base_id"] = base_id
        return outline

    def _parse_yaml_response(self, content: str) -> dict[str, Any]:
        text = content.strip()
        fenced = re.search(r"```(?:yaml|yml)?\s*(.*?)```", text, re.S | re.I)
        if fenced:
            text = fenced.group(1).strip()
        parsed = yaml.safe_load(text)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response did not contain a YAML mapping.")
        if "work" not in parsed:
            parsed = {"work": parsed}
        return parsed

    def _transcript(self, messages: list[dict[str, Any]]) -> str:
        lines = []
        for item in messages:
            role = str(item.get("role") or "user").strip().lower()
            content = str(item.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n\n".join(lines)

    def _title_from_transcript(self, transcript: str) -> str:
        for pattern in [
            r"(?:title|called|named)\s+['\"]([^'\"]{4,90})['\"]",
            r"(?:book|paper)\s+(?:about|on)\s+([A-Z][^\n.?!]{8,90})",
        ]:
            match = re.search(pattern, transcript, re.I)
            if match:
                return match.group(1).strip(" .")
        first = re.split(r"[.?!\n]", transcript.strip())[0]
        words = re.findall(r"[A-Za-z][A-Za-z0-9-]+", first)[:9]
        return " ".join(words).title() if words else "Conversation Book"

    def _summary_from_transcript(self, transcript: str) -> str:
        sentences = [item.strip() for item in re.split(r"(?<=[.?!])\s+", transcript) if len(item.strip()) > 40]
        return " ".join(sentences[:3])[:900] or "A book developed from an author conversation."

    def _themes(self, transcript: str) -> list[str]:
        stop = {
            "about", "after", "again", "book", "conversation", "could", "from", "have", "into",
            "like", "make", "need", "that", "their", "there", "this", "through", "with", "would",
        }
        counts: dict[str, int] = {}
        for word in re.findall(r"\b[A-Za-z][A-Za-z-]{4,}\b", transcript.lower()):
            if word not in stop:
                counts[word] = counts.get(word, 0) + 1
        ranked = sorted(counts, key=lambda item: (-counts[item], item))
        return [self._titleize(item) for item in ranked[:12]] or ["Intent", "Structure", "Practice"]

    def _chapter_titles(self, themes: list[str]) -> list[str]:
        base = [
            "Orientation",
            "Core Concepts",
            "System Architecture",
            "Working Process",
            "Examples and Implications",
            "Limits and Future Work",
        ]
        for theme in themes[:3]:
            candidate = f"{theme} in Practice"
            if candidate not in base:
                base.insert(-1, candidate)
        return base[:8]

    def _sections_for_chapter(self, chapter_id: str, chapter_title: str, chapter_index: int) -> list[dict[str, Any]]:
        section_titles = [
            f"The Question of {chapter_title}",
            f"Key Terms for {chapter_title}",
            f"How {chapter_title} Works",
            f"What {chapter_title} Changes",
        ]
        sections = []
        for section_index, title in enumerate(section_titles, start=1):
            section_id = f"{chapter_id}_sec{section_index:02d}_{self._slug(title)[:22]}"
            sections.append({
                "id": section_id,
                "type": "section",
                "title": title,
                "goal": f"Draft the {title.lower()} section with concrete claims and examples.",
                "summary": f"This section develops {title.lower()} for chapter {chapter_index}.",
                "dependencies": {"structural": [], "narrative": ""},
                "prerequisites": [],
                "key_concepts": [chapter_title],
                "citations": [],
                "content_file": f"content/sections/{section_id}.md",
            })
        return sections

    def _titleize(self, value: str) -> str:
        return " ".join(part.capitalize() for part in re.split(r"[_\-\s]+", value) if part)

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
        slug = re.sub(r"_+", "_", slug)
        return slug or "conversation_book"
