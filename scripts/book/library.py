"""Library registry for managing many canonical book projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.book.importer import BookImporter, ImportResult
from scripts.book.intake import BookIntakeService
from scripts.book.repository import BookRepository


@dataclass(frozen=True)
class BookRecord:
    """A lightweight registry entry for one book project."""

    book_id: str
    title: str
    root: str
    outline_path: str
    status: str = "active"
    last_opened: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BookLibrary:
    """Registry and active-book store over many book roots."""

    def __init__(self, book_data_dir: Path | str = Path("data/book_data")):
        self.book_data_dir = Path(book_data_dir)
        self.registry_path = self.book_data_dir / "library.yaml"
        self.active_path = self.book_data_dir / ".active_book"

    def list_books(self, refresh: bool = False) -> list[BookRecord]:
        if refresh or not self.registry_path.exists():
            self.refresh()
        data = self._load_registry()
        return [BookRecord(**item) for item in data.get("books", [])]

    def search_books(self, query: str) -> list[BookRecord]:
        normalized = query.lower().strip()
        if not normalized:
            return self.list_books()
        return [
            record for record in self.list_books()
            if normalized in record.title.lower()
            or normalized in record.book_id.lower()
            or any(normalized in tag.lower() for tag in record.tags)
        ]

    def get(self, book_id: str) -> BookRecord:
        for record in self.list_books():
            if record.book_id == book_id:
                return record
        raise KeyError(f"Book not found: {book_id}")

    def active(self) -> BookRecord:
        if self.active_path.exists():
            active_id = self.active_path.read_text().strip()
            if active_id:
                try:
                    return self.get(active_id)
                except KeyError:
                    pass
        books = self.list_books(refresh=True)
        if not books:
            raise FileNotFoundError(f"No books found under {self.book_data_dir}")
        return self.open_book(books[0].book_id)

    def active_root(self) -> Path:
        return Path(self.active().root)

    def open_book(self, book_id: str) -> BookRecord:
        record = self.get(book_id)
        updated = BookRecord(
            **{
                **asdict(record),
                "last_opened": datetime.now().isoformat(),
            }
        )
        self.register(updated)
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        self.active_path.write_text(f"{book_id}\n")
        return updated

    def register(self, record: BookRecord | dict[str, Any]) -> BookRecord:
        record = record if isinstance(record, BookRecord) else BookRecord(**record)
        data = self._load_registry()
        books = [item for item in data.get("books", []) if item.get("book_id") != record.book_id]
        books.append(asdict(record))
        books.sort(key=lambda item: item["title"].lower())
        self._save_registry({"books": books})
        return record

    def create_book(
        self,
        title: str,
        book_id: str | None = None,
        tags: list[str] | None = None,
    ) -> BookRecord:
        service = BookIntakeService()
        service.record_answer("title", title)
        work_id = book_id or service.book["work"]["id"]
        book_root = self.book_data_dir / work_id
        repository = BookRepository(book_root)
        repository.save_book(service.book)
        record = self._record_from_repository(repository, tags=tags)
        self.register(record)
        return self.open_book(record.book_id)

    def import_outline(
        self,
        outline_path: Path | str,
        book_root: Path | str | None = None,
        use_llm: str | bool = "auto",
        tags: list[str] | None = None,
    ) -> tuple[BookRecord, ImportResult]:
        result = BookImporter(self.book_data_dir).import_outline(
            outline_path,
            book_root=book_root,
            use_llm=use_llm,
        )
        record = self._record_from_repository(BookRepository(result.book_root), tags=tags)
        self.register(record)
        return self.open_book(record.book_id), result

    def create_version_from_outline(
        self,
        outline_path: Path | str,
        use_llm: str | bool = "auto",
        force: bool = False,
        tags: list[str] | None = None,
    ) -> tuple[BookRecord, ImportResult]:
        """Create, register, and open a clean versioned book from an outline."""
        result = BookImporter(self.book_data_dir).import_versioned_outline(
            outline_path,
            use_llm=use_llm,
            force=force,
        )
        record = self._record_from_repository(
            BookRepository(result.book_root),
            tags=tags or ["versioned"],
        )
        self.register(record)
        return self.open_book(record.book_id), result

    def archive_book(self, book_id: str) -> BookRecord:
        record = self.get(book_id)
        archived = BookRecord(**{**asdict(record), "status": "archived"})
        return self.register(archived)

    def refresh(self) -> list[BookRecord]:
        records = []
        self.book_data_dir.mkdir(parents=True, exist_ok=True)
        for outline_dir in sorted(self.book_data_dir.glob("*/outline")):
            book_root = outline_dir.parent
            try:
                records.append(self._record_from_repository(BookRepository(book_root)))
            except Exception:
                continue
        data = self._load_registry()
        existing = {item["book_id"]: item for item in data.get("books", [])}
        merged = []
        for record in records:
            previous = existing.get(record.book_id, {})
            merged.append(asdict(BookRecord(**{
                **asdict(record),
                "last_opened": previous.get("last_opened"),
                "tags": previous.get("tags", record.tags),
                "status": previous.get("status", record.status),
                "metadata": {**record.metadata, **previous.get("metadata", {})},
            })))
        merged.sort(key=lambda item: item["title"].lower())
        self._save_registry({"books": merged})
        return [BookRecord(**item) for item in merged]

    def _record_from_repository(
        self,
        repository: BookRepository,
        tags: list[str] | None = None,
    ) -> BookRecord:
        book = repository.load_book()
        work = book["work"]
        return BookRecord(
            book_id=work.get("id") or repository.book_root.name,
            title=work.get("title") or repository.book_root.name,
            root=str(repository.book_root),
            outline_path=str(repository.outline_path.relative_to(repository.book_root)),
            tags=tags or [],
            metadata={
                "summary": work.get("summary", ""),
                "type": work.get("type", "book"),
                "version": work.get("metadata", {}).get("version"),
                "version_family_id": work.get("metadata", {}).get("version_family_id"),
                "updated": work.get("metadata", {}).get("updated"),
            },
        )

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"books": []}
        data = yaml.safe_load(self.registry_path.read_text()) or {}
        data.setdefault("books", [])
        return data

    def _save_registry(self, data: dict[str, Any]) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
