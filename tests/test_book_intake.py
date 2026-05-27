"""Tests for conversational book intake."""

from scripts.book import BookIntakeService, BookRepository, OutlineService


def answer_required_intake(service: BookIntakeService) -> None:
    service.record_answer("title", "Practical Codynamics")
    service.record_answer("purpose", "Help builders reason about systems that revise themselves.")
    service.record_answer("audience", "Technical founders and research engineers.")
    service.record_answer("reader_takeaway", "They can design feedback-aware authoring systems.")
    service.record_answer("voice", "Precise, grounded, and exploratory guide.")
    service.record_answer("genre", "handbook")


def test_intake_records_answers_as_canonical_fields():
    service = BookIntakeService()

    book = service.record_answer("audience", "Researchers building authoring tools.")

    work = book["work"]
    assert work["intent"]["audience"] == "Researchers building authoring tools."
    assert work["metadata"]["descriptive"]["intended_audience"] == "Researchers building authoring tools."
    assert work["intake"]["answers"]["audience"]["field_paths"] == [
        "work.intent.audience",
        "work.metadata.descriptive.intended_audience",
    ]
    assert "audience: Researchers building authoring tools." in work["intake"]["conversation_summary"]


def test_intake_generates_initial_plan_with_uncertainties():
    service = BookIntakeService()
    answer_required_intake(service)
    service.record_answer(
        "artifact_structure",
        "Needs conceptual diagrams, one appendix, and eventual cover artwork.",
    )

    book = service.generate_initial_plan()
    service = OutlineService(book)
    valid, errors = service.validate()

    assert valid, errors
    assert [node.id for node in service.tree()][:2] == ["opening_orientation", "why_this_book"]
    assert book["work"]["diagrams"][0]["status"] == "todo"
    assert book["work"]["back_matter"]["appendices"][0]["id"] == "appendix_materials"
    assert book["work"]["intake"]["plan"]["todos"]


def test_intake_keeps_required_questions_explicit():
    service = BookIntakeService()
    service.record_answer("title", "Sparse Book")

    book = service.generate_initial_plan()
    open_ids = {question["question_id"] for question in book["work"]["intake"]["plan"]["open_questions"]}

    assert {"purpose", "audience", "reader_takeaway", "voice", "genre"}.issubset(open_ids)


def test_repository_persists_intake_answers_and_plan(tmp_path):
    book_root = tmp_path / "practical_codyn"
    repository = BookRepository(book_root)

    repository.record_intake_answer("title", "Practical Codynamics")
    repository.record_intake_answer("purpose", "Explain codynamic systems through practical examples.")
    repository.generate_initial_plan()

    reloaded = BookRepository(book_root).load_book()

    assert reloaded["work"]["title"] == "Practical Codynamics"
    assert reloaded["work"]["id"] == "practical_codynamics"
    assert reloaded["work"]["intake"]["answers"]["purpose"]["answer"].startswith("Explain")
    assert reloaded["work"]["structure"][0]["id"] == "opening_orientation"
