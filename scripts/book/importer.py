"""Import external book artifacts into canonical book projects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
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
        self._write_imported_section_payloads(repository, work.get("structure", []))
        self._strip_inline_section_payloads(work.get("structure", []))
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

    def import_versioned_outline(
        self,
        source_path: Path | str,
        use_llm: str | bool = "auto",
        force: bool = False,
    ) -> ImportResult:
        """Create a clean book project for the outline's metadata.version."""
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Outline file not found: {source}")

        canonical = self._load_or_convert_outline(source, use_llm=use_llm)
        work = canonical["work"]
        family_id = str(
            work.get("metadata", {}).get("version_family_id")
            or work.get("metadata", {}).get("family_id")
            or work.get("id")
            or ""
        ).strip()
        version = str(work.get("metadata", {}).get("version") or "").strip()
        if not family_id:
            raise ValueError("Versioned import requires work.id or metadata.version_family_id.")
        if not version:
            raise ValueError("Versioned import requires work.metadata.version.")

        versioned_id = self.versioned_work_id(family_id, version)
        target_root = self.book_data_dir / versioned_id
        if target_root.exists() and any(target_root.iterdir()) and not force:
            raise FileExistsError(
                f"Versioned book already exists: {target_root}. "
                "Choose a new metadata.version or recreate with force."
            )
        if target_root.exists() and force:
            shutil.rmtree(target_root)

        work["id"] = versioned_id
        metadata = work.setdefault("metadata", {})
        metadata["version"] = version
        metadata["version_family_id"] = family_id
        metadata["version_source_outline"] = str(source)
        metadata["versioned_from_scratch"] = True

        repository = BookRepository(target_root)
        repository.save_book(canonical)
        self._write_imported_section_payloads(repository, work.get("structure", []))
        self._strip_inline_section_payloads(work.get("structure", []))
        self._ensure_section_source_files(repository, work.get("structure", []))
        repository.save_book(canonical)

        report_path = target_root / "outline" / "reports" / f"{versioned_id}_import.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            "\n".join([
                f"# Versioned outline import: {work.get('title', versioned_id)}",
                "",
                f"- Source outline: `{source}`",
                f"- Version family: `{family_id}`",
                f"- Version: `{version}`",
                f"- Versioned work id: `{versioned_id}`",
                "",
                "This project was created from the outline only. Generated TeX, build outputs, logs, media, proposals, and agent runtime state were not copied from any previous version.",
                "",
            ])
        )

        return ImportResult(
            kind="versioned_outline",
            source_path=source,
            book_root=target_root,
            outline_path=repository.outline_path,
            report_path=report_path,
            work_id=versioned_id,
            title=work["title"],
        )

    def _load_or_convert_outline(self, source: Path, use_llm: str | bool = "auto") -> dict[str, Any]:
        raw = yaml.safe_load(source.read_text())
        if isinstance(raw, dict) and isinstance(raw.get("work"), dict):
            return raw
        converter = OutlineConverter()
        canonical_yaml = converter.convert(
            str(source),
            interactive=False,
            quiet=True,
            use_llm=use_llm,
        )
        return yaml.safe_load(canonical_yaml)

    @staticmethod
    def versioned_work_id(family_id: str, version: str) -> str:
        version_slug = re.sub(r"[^A-Za-z0-9]+", "_", version).strip("_").lower()
        if not version_slug:
            raise ValueError("Version cannot be converted to a book id suffix.")
        family_slug = re.sub(r"[^A-Za-z0-9_]+", "_", family_id).strip("_").lower()
        family_slug = re.sub(r"_+", "_", family_slug)
        return f"{family_slug}__v{version_slug}"

    def _write_imported_section_payloads(
        self,
        repository: BookRepository,
        nodes: list[dict[str, Any]],
    ) -> None:
        """Persist imported inline leaf body text to canonical section files."""
        for node in nodes:
            content = node.get("content_text")
            if content:
                repository.save_section(node["id"], f"{content.strip()}\n")
            children = node.get("content") or []
            if children:
                self._write_imported_section_payloads(repository, children)

    def _strip_inline_section_payloads(self, nodes: list[dict[str, Any]]) -> None:
        """Keep the saved outline structural by moving bodies to content files."""
        for node in nodes:
            node.pop("content_text", None)
            self._strip_inline_section_payloads(node.get("content") or [])

    def _ensure_section_source_files(
        self,
        repository: BookRepository,
        nodes: list[dict[str, Any]],
    ) -> None:
        """Create empty source files for outline leaves in a fresh version."""
        for node in nodes:
            children = node.get("content") or []
            if children:
                self._ensure_section_source_files(repository, children)
                continue
            content_file = node.get("content_file")
            if not content_file:
                continue
            path = repository.book_root / content_file
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("")
