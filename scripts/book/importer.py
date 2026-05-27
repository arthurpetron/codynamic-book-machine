"""Import external book artifacts into canonical book projects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.book.repository import BookRepository
from scripts.outline_converter.converter import OutlineConverter


@dataclass(frozen=True)
class ImportResult:
    """Result metadata for an imported artifact."""

    kind: str
    source_path: Path
    book_root: Path
    outline_path: Path
    report_path: Path
    work_id: str
    title: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "source_path": str(self.source_path),
            "book_root": str(self.book_root),
            "outline_path": str(self.outline_path),
            "report_path": str(self.report_path),
            "work_id": self.work_id,
            "title": self.title,
        }


class BookImporter:
    """Imports external artifacts through canonical conversion services."""

    def __init__(self, book_data_dir: Path | str = Path("data/book_data")):
        self.book_data_dir = Path(book_data_dir)

    def import_outline(
        self,
        source_path: Path | str,
        book_root: Path | str | None = None,
        use_llm: str | bool = "auto",
    ) -> ImportResult:
        """Convert an existing outline file and save it as a canonical book."""
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Outline file not found: {source}")

        converter = OutlineConverter()
        canonical_yaml = converter.convert(
            str(source),
            interactive=False,
            quiet=True,
            use_llm=use_llm,
        )
        canonical: dict[str, Any] = yaml.safe_load(canonical_yaml)
        work = canonical["work"]
        target_root = Path(book_root) if book_root else self.book_data_dir / work["id"]
        repository = BookRepository(target_root)
        repository.save_book(canonical)

        report_path = target_root / "outline" / "reports" / f"{work['id']}_import.md"
        converter.write_report(report_path)

        return ImportResult(
            kind="outline",
            source_path=source,
            book_root=target_root,
            outline_path=repository.outline_path,
            report_path=report_path,
            work_id=work["id"],
            title=work["title"],
        )
