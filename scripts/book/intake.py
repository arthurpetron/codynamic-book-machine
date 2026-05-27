"""Conversational intake for creating a canonical book outline."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from scripts.outline_converter.converter import OutlineConverter


@dataclass(frozen=True)
class IntakeQuestion:
    """A Socratic intake prompt mapped to canonical book fields."""

    id: str
    field_paths: tuple[str, ...]
    prompt: str
    rationale: str
    required: bool = True


QUESTION_BANK: tuple[IntakeQuestion, ...] = (
    IntakeQuestion(
        id="title",
        field_paths=("work.title",),
        prompt="What working title names the book as you currently understand it?",
        rationale="The title anchors the canonical work id and future artifact names.",
    ),
    IntakeQuestion(
        id="purpose",
        field_paths=("work.summary", "work.metadata.semantic.purpose"),
        prompt="In your own words, why does this book need to exist?",
        rationale="Purpose keeps later structure accountable to the author's intent.",
    ),
    IntakeQuestion(
        id="audience",
        field_paths=(
            "work.intent.audience",
            "work.metadata.descriptive.intended_audience",
        ),
        prompt="Who is the reader, and what do they already know or care about?",
        rationale="Audience determines pacing, assumed context, and explanatory depth.",
    ),
    IntakeQuestion(
        id="reader_takeaway",
        field_paths=("work.intent.reader_takeaway",),
        prompt="What should the reader understand, feel, or be able to do by the end?",
        rationale="Takeaway gives the outline a destination before chapters are proposed.",
    ),
    IntakeQuestion(
        id="voice",
        field_paths=("work.intent.writing_style", "work.intent.author_persona"),
        prompt="How should the book sound, and what role should the authorial voice take?",
        rationale="Voice constrains prose generation without letting the model impersonate the author.",
    ),
    IntakeQuestion(
        id="genre",
        field_paths=("work.intent.genre", "work.metadata.descriptive.genre"),
        prompt="What kind of work is this: textbook, monograph, manifesto, handbook, or something else?",
        rationale="Genre shapes front matter, chapter rhythm, and reader expectations.",
    ),
    IntakeQuestion(
        id="design_spec",
        field_paths=("work.design_spec",),
        prompt="What design, typography, diagrams, or visual language should the book use?",
        rationale="Design intent becomes part of the book object before rendering starts.",
        required=False,
    ),
    IntakeQuestion(
        id="artifact_structure",
        field_paths=("work.intake.artifact_structure",),
        prompt="What artifacts do you already expect: chapters, appendices, diagrams, artwork, datasets, or code?",
        rationale="Known artifacts seed the initial plan and leave unknowns explicit.",
        required=False,
    ),
)


class BookIntakeService:
    """Guided zero-to-outline intake over a canonical book object."""

    def __init__(self, book: dict[str, Any] | None = None):
        self.book = deepcopy(book) if book else self.blank_book()
        self._ensure_intake()

    @staticmethod
    def blank_book(title: str = "Untitled Work") -> dict[str, Any]:
        """Return a schema-valid canonical book object ready for intake."""
        converter = OutlineConverter()
        canonical = converter.map_to_schema_v2(
            {
                "title": title,
                "summary": "",
                "structure": [
                    {
                        "id": "intake_placeholder",
                        "type": "chapter",
                        "title": "Intake Placeholder",
                        "summary": "Replaced when the conversational plan is generated.",
                    }
                ],
            },
            interactive=False,
        )
        canonical["work"]["structure"][0]["status"] = "todo"
        canonical["work"]["structure"][0]["uncertainty"] = "Pending conversational intake."
        return canonical

    def next_question(self) -> IntakeQuestion | None:
        """Return the next unanswered intake question."""
        answered = set(self.book["work"]["intake"].get("answers", {}))
        for question in QUESTION_BANK:
            if question.id not in answered:
                return question
        return None

    def progress(self) -> dict[str, int]:
        """Return simple intake completion counts."""
        answers = self.book["work"]["intake"].get("answers", {})
        required_ids = {question.id for question in QUESTION_BANK if question.required}
        answered_required = required_ids.intersection(answers)
        return {
            "answered": len(answers),
            "total": len(QUESTION_BANK),
            "required_answered": len(answered_required),
            "required_total": len(required_ids),
        }

    def record_answer(
        self,
        question_id: str,
        answer: str,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        """Persist one answer into canonical fields and intake history."""
        question = self._question(question_id)
        answer = answer.strip()
        if not answer:
            raise ValueError("Intake answer is required")

        for path in question.field_paths:
            self._set_path(path, self._field_value(question, path, answer))

        now = datetime.now().isoformat()
        intake = self.book["work"]["intake"]
        intake["answers"][question.id] = {
            "question_id": question.id,
            "field_paths": list(question.field_paths),
            "prompt": question.prompt,
            "answer": answer,
            "rationale": rationale or question.rationale,
            "answered_at": now,
        }
        intake["conversation"].append(
            {
                "role": "user",
                "question_id": question.id,
                "content": answer,
                "created_at": now,
            }
        )
        intake["conversation_summary"] = self._summarize_answers()
        self._touch_modified()
        return deepcopy(self.book)

    def socratic_prompt(self, question_id: str | None = None) -> str:
        """Return a user-facing prompt that asks for expression, not delegation."""
        question = self._question(question_id) if question_id else self.next_question()
        if question is None:
            return "The required intake is complete. Review the generated plan and answer the open questions."
        return (
            f"{question.prompt}\n"
            "Answer from your own position. Specific fragments, examples, tensions, "
            "and dislikes are more useful than polished wording."
        )

    def generate_initial_plan(self) -> dict[str, Any]:
        """Generate a conservative initial structure and explicit unknowns."""
        work = self.book["work"]
        answers = work["intake"].get("answers", {})
        title = work.get("title") or "Untitled Work"
        purpose = answers.get("purpose", {}).get("answer", work.get("summary", ""))
        takeaway = answers.get("reader_takeaway", {}).get("answer", "")
        artifacts = answers.get("artifact_structure", {}).get("answer", "")

        work["structure"] = [
            self._chapter(
                "opening_orientation",
                "Opening Orientation",
                "Establish the problem, promise, reader contract, and terms of engagement.",
                [self._section("why_this_book", "Why This Book", purpose)],
            ),
            self._chapter(
                "foundations",
                "Foundations",
                "Build the concepts and context the reader needs before the main argument.",
                [self._section("reader_grounding", "Reader Grounding", work["intent"].get("audience", ""))],
            ),
            self._chapter(
                "main_development",
                "Main Development",
                "Develop the central argument, method, or system in a narrative sequence.",
                [self._section("core_thread", "Core Thread", takeaway)],
            ),
            self._chapter(
                "applications_and_implications",
                "Applications and Implications",
                "Show consequences, examples, edge cases, and practical or conceptual reach.",
                [self._section("what_changes", "What Changes", takeaway)],
            ),
            self._chapter(
                "closing_synthesis",
                "Closing Synthesis",
                "Return to the promise of the book and make the unresolved work visible.",
                [self._section("open_questions", "Open Questions", "Resolve uncertainties gathered during intake.")],
            ),
        ]
        work["front_matter"]["preface"] = {
            "enabled": True,
            "content_file": "content/front_matter/preface.md",
        }
        work["back_matter"]["appendices"] = self._appendices_from_artifacts(artifacts)
        work["diagrams"] = self._diagrams_from_text(artifacts)
        work["media"] = self._media_from_design(work.get("design_spec", ""))
        work["intake"]["plan"] = {
            "generated_at": datetime.now().isoformat(),
            "status": "draft",
            "rationale": (
                f"Initial plan for {title!r} follows the intake sequence: orient the reader, "
                "build foundations, develop the core thread, test implications, then synthesize."
            ),
            "open_questions": self.open_questions(),
            "todos": [
                "Replace generic chapter titles with author-approved language.",
                "Attach concrete examples, citations, and source dependencies to each leaf section.",
                "Confirm visual/design requirements before rendering templates are chosen.",
            ],
        }
        self._touch_modified()
        return deepcopy(self.book)

    def open_questions(self) -> list[dict[str, str]]:
        """Return explicit unresolved intake questions."""
        questions = []
        answers = self.book["work"]["intake"].get("answers", {})
        for question in QUESTION_BANK:
            if question.required and question.id not in answers:
                questions.append({
                    "question_id": question.id,
                    "question": question.prompt,
                    "reason": "Required for a stable initial outline.",
                })
        if "artifact_structure" not in answers:
            questions.append({
                "question_id": "artifact_structure",
                "question": "Which diagrams, artwork, appendices, datasets, or code artifacts are expected?",
                "reason": "Artifacts and dependencies are still provisional.",
            })
        return questions

    def _ensure_intake(self) -> None:
        work = self.book.setdefault("work", {})
        intake = work.setdefault("intake", {})
        intake.setdefault("schema_version", "1.0")
        intake.setdefault("status", "in_progress")
        intake.setdefault("questions", [question.__dict__ for question in QUESTION_BANK])
        intake.setdefault("answers", {})
        intake.setdefault("conversation", [])
        intake.setdefault("conversation_summary", "")
        intake.setdefault("plan", {})

    def _question(self, question_id: str) -> IntakeQuestion:
        for question in QUESTION_BANK:
            if question.id == question_id:
                return question
        raise KeyError(f"Unknown intake question: {question_id}")

    def _set_path(self, path: str, value: Any) -> None:
        parts = path.split(".")
        current = self.book
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        current[parts[-1]] = value
        if path == "work.title":
            work = self.book["work"]
            if work.get("id") in {"untitled_work", "intake_placeholder"} or work.get("id", "").startswith("untitled"):
                work["id"] = self._slug(value)

    def _field_value(self, question: IntakeQuestion, path: str, answer: str) -> str:
        if question.id == "voice" and path.endswith("author_persona"):
            return answer
        if question.id == "genre":
            return answer.lower()
        return answer

    def _summarize_answers(self) -> str:
        lines = []
        for question in QUESTION_BANK:
            answer = self.book["work"]["intake"]["answers"].get(question.id)
            if answer:
                lines.append(f"{question.id}: {answer['answer']}")
        return "\n".join(lines)

    def _touch_modified(self) -> None:
        metadata = self.book["work"].setdefault("metadata", {})
        today = datetime.now().strftime("%Y-%m-%d")
        metadata["updated"] = today
        metadata.setdefault("created", today)
        metadata.setdefault("version", "0.1.0")
        admin = metadata.get("administrative")
        if isinstance(admin, dict):
            admin.setdefault("timestamps", {})["modified"] = today

    def _chapter(
        self,
        chapter_id: str,
        title: str,
        summary: str,
        sections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "type": "chapter",
            "id": chapter_id,
            "title": title,
            "goal": summary,
            "summary": summary,
            "prerequisites": [],
            "dependencies": {"structural": [], "narrative": ""},
            "key_concepts": [],
            "citations": [],
            "content": sections,
        }

    def _section(self, section_id: str, title: str, summary: str) -> dict[str, Any]:
        return {
            "type": "section",
            "id": section_id,
            "title": title,
            "goal": summary,
            "summary": summary,
            "prerequisites": [],
            "dependencies": {"structural": [], "narrative": ""},
            "key_concepts": [],
            "citations": [],
            "content_file": f"content/sections/{section_id}.md",
            "status": "todo" if not summary else "planned",
        }

    def _appendices_from_artifacts(self, artifacts: str) -> list[dict[str, str]]:
        if "appendix" not in artifacts.lower():
            return []
        return [{
            "id": "appendix_materials",
            "title": "Supporting Materials",
            "content_file": "content/back_matter/appendix_materials.md",
        }]

    def _diagrams_from_text(self, artifacts: str) -> list[dict[str, Any]]:
        if not re.search(r"\b(diagrams?|figures?|maps?|charts?|graphs?)\b", artifacts, re.I):
            return []
        return [{
            "id": "diagram_plan_overview",
            "title": "Planned Conceptual Overview",
            "caption": "TODO: refine during outline conversation.",
            "purpose": artifacts,
            "definition": {"type": "pending", "code": ""},
            "status": "todo",
        }]

    def _media_from_design(self, design_spec: str) -> list[dict[str, str]]:
        if not design_spec:
            return []
        return [{
            "id": "cover_direction",
            "type": "cover",
            "title": "Cover Direction",
            "caption": design_spec,
            "file": "",
            "purpose": "Capture intake-stage design direction.",
            "status": "todo",
        }]

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return slug or "untitled_work"
