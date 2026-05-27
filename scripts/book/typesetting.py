"""Document assembly, styles, and LaTeX compilation for book projects."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
import html
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

import yaml

from scripts.book.repository import BookRepository
from scripts.utils.latex import find_latex_compiler


DEFAULT_DESIGN_SETTINGS = {
    "style_id": "standard_article",
    "page_size": "letter",
    "margin": "1in",
    "font_size": "11pt",
    "title_treatment": "standard",
    "plot_placement": "inline",
    "image_placement": "inline",
    "equation_style": "numbered",
    "latex_engine": "latexmk",
}


@dataclass(frozen=True)
class DocumentStyle:
    """A selectable document style."""

    style_id: str
    label: str
    document_class: str
    class_options: list[str] = field(default_factory=list)
    tex_inputs: list[str] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class CompileResult:
    """Result of a LaTeX compile attempt."""

    status: str
    tex_path: Path
    pdf_path: Path | None
    log_path: Path
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    errors: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("tex_path", "pdf_path", "log_path"):
            value = payload[key]
            payload[key] = str(value) if value else None
        return payload


class DocumentStyleRegistry:
    """Discover built-in and custom LaTeX document styles."""

    def __init__(self, project_root: Path | str = Path(".")):
        self.project_root = Path(project_root)

    def list_styles(self) -> list[DocumentStyle]:
        styles = [
            DocumentStyle(
                style_id="standard_article",
                label="Standard Article",
                document_class="article",
                packages=["geometry", "graphicx", "amsmath", "amssymb", "hyperref"],
                description="Portable article layout for fast compilation.",
            )
        ]
        arthur_root = self.project_root / "docs" / "arthur_tex_style"
        if (arthur_root / "arthur-book.cls").exists():
            styles.append(
                DocumentStyle(
                    style_id="arthur_book",
                    label="Arthur Book",
                    document_class="arthur-book",
                    class_options=["wide-notes"],
                    tex_inputs=[
                        str(arthur_root),
                        str(arthur_root / "tex"),
                        str(arthur_root / "assets"),
                    ],
                    packages=["biblatex"],
                    description="Custom Tufte-style book layout with margin notes, figures, and math helpers.",
                )
            )
        return styles

    def get(self, style_id: str) -> DocumentStyle:
        for style in self.list_styles():
            if style.style_id == style_id:
                return style
        raise KeyError(f"Unknown document style: {style_id}")


class DesignSettingsService:
    """Persist document design settings in the canonical book object."""

    def __init__(self, repository: BookRepository, project_root: Path | str = Path(".")):
        self.repository = repository
        self.styles = DocumentStyleRegistry(project_root)

    def get(self) -> dict[str, Any]:
        book = self.repository.load_book()
        settings = DEFAULT_DESIGN_SETTINGS | book["work"].get("design_settings", {})
        return settings

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        if "style_id" in updates:
            self.styles.get(updates["style_id"])
        book = self.repository.load_book()
        settings = DEFAULT_DESIGN_SETTINGS | book["work"].get("design_settings", {})
        settings.update({key: value for key, value in updates.items() if value is not None})
        book["work"]["design_settings"] = settings
        book["work"].setdefault("metadata", {})["updated"] = datetime.now().strftime("%Y-%m-%d")
        self.repository.save_book(book)
        return settings


class LatexAssembler:
    """Assemble canonical book content into compilable LaTeX."""

    def __init__(self, repository: BookRepository, project_root: Path | str = Path(".")):
        self.repository = repository
        self.project_root = Path(project_root)

    def assemble_book(self) -> str:
        book = self.repository.load_book()
        work = book["work"]
        settings = DEFAULT_DESIGN_SETTINGS | work.get("design_settings", {})
        style = DocumentStyleRegistry(self.project_root).get(settings["style_id"])
        lines = [self._preamble(work, settings, style), "\\begin{document}", "\\maketitle"]
        for node in work.get("structure", []):
            lines.extend(self._node_tex(node, depth=0))
        lines.append("\\end{document}")
        return "\n\n".join(lines) + "\n"

    def assemble_section(self, section_id: str) -> str:
        book = self.repository.load_book()
        work = book["work"]
        settings = DEFAULT_DESIGN_SETTINGS | work.get("design_settings", {})
        style = DocumentStyleRegistry(self.project_root).get(settings["style_id"])
        node = self.repository.outline_service().get_node(section_id)
        if not node:
            raise KeyError(f"Unknown section id: {section_id}")
        return "\n\n".join([
            self._preamble(work, settings, style),
            "\\begin{document}",
            f"\\section*{{{self._escape_tex(node.get('title', section_id))}}}",
            self.repository.load_section(section_id),
            "\\end{document}",
        ]) + "\n"

    def _preamble(self, work: dict[str, Any], settings: dict[str, Any], style: DocumentStyle) -> str:
        options = list(style.class_options)
        font_size = settings.get("font_size")
        if font_size and font_size not in options:
            options.insert(0, font_size)
        option_text = f"[{','.join(options)}]" if options else ""
        lines = [
            f"\\documentclass{option_text}{{{style.document_class}}}",
            f"\\title{{{self._escape_tex(work.get('title', 'Untitled Work'))}}}",
            f"\\author{{{self._escape_tex(self._author(work))}}}",
        ]
        if style.style_id == "standard_article":
            margin = settings.get("margin", "1in")
            geometry_option = margin if "=" in margin else f"margin={margin}"
            lines.extend([
                f"\\usepackage[{geometry_option}]" + "{geometry}",
                "\\usepackage{graphicx}",
                "\\usepackage{amsmath,amssymb}",
                "\\usepackage{hyperref}",
            ])
        lines.append("\\graphicspath{{media/}{media/diagrams/}{images/}{artwork/}}")
        return "\n".join(lines)

    def _node_tex(self, node: dict[str, Any], depth: int) -> list[str]:
        command = ["section", "subsection", "subsubsection", "paragraph"][min(depth, 3)]
        lines = [f"\\{command}{{{self._escape_tex(node.get('title', 'Untitled'))}}}"]
        children = node.get("content") or []
        if children:
            for child in children:
                lines.extend(self._node_tex(child, depth + 1))
        else:
            lines.append(self.repository.load_section(node["id"]))
        return lines

    def _author(self, work: dict[str, Any]) -> str:
        authors = work.get("authors") or []
        if authors and authors[0].get("name") and authors[0]["name"] != "TO BE SPECIFIED":
            return authors[0]["name"]
        return work.get("intent", {}).get("author_persona", "Author")

    def _escape_tex(self, value: str) -> str:
        replacements = {
            "\\": "\\textbackslash{}",
            "&": "\\&",
            "%": "\\%",
            "$": "\\$",
            "#": "\\#",
            "_": "\\_",
            "{": "\\{",
            "}": "\\}",
        }
        return "".join(replacements.get(char, char) for char in str(value))


class LatexBuildService:
    """Assemble and compile full-book or section-level LaTeX artifacts."""

    def __init__(self, book_root: Path | str, project_root: Path | str = Path(".")):
        self.book_root = Path(book_root)
        self.project_root = Path(project_root)
        self.repository = BookRepository(self.book_root)
        self.assembler = LatexAssembler(self.repository, project_root=self.project_root)

    def compile_book(self, engine: str | None = None) -> CompileResult:
        work_id = self.repository.load_book()["work"]["id"]
        tex_path = self.book_root / "build" / "tex" / f"{work_id}.tex"
        return self._compile(tex_path, self.assembler.assemble_book(), engine=engine)

    def compile_section(self, section_id: str, engine: str | None = None) -> CompileResult:
        tex_path = self.book_root / "build" / "sections" / f"{section_id}.tex"
        return self._compile(tex_path, self.assembler.assemble_section(section_id), engine=engine)

    def export_html(self) -> Path:
        """Export a basic HTML artifact from canonical section content."""
        work = self.repository.load_book()["work"]
        output = self.book_root / "exports" / "html" / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        body = [f"<h1>{html.escape(work.get('title', 'Untitled Work'))}</h1>"]
        for node in work.get("structure", []):
            body.extend(self._html_node(node, depth=2))
        output.write_text("<!doctype html>\n<meta charset=\"utf-8\">\n" + "\n".join(body) + "\n")
        return output

    def _html_node(self, node: dict[str, Any], depth: int) -> list[str]:
        tag = f"h{min(depth, 6)}"
        lines = [f"<{tag}>{html.escape(node.get('title', 'Untitled'))}</{tag}>"]
        children = node.get("content") or []
        if children:
            for child in children:
                lines.extend(self._html_node(child, depth + 1))
        else:
            content = html.escape(self.repository.load_section(node["id"]))
            lines.append(f"<pre>{content}</pre>")
        return lines

    def _compile(self, tex_path: Path, tex_content: str, engine: str | None = None) -> CompileResult:
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        tex_path.write_text(tex_content)
        output_dir = self.book_root / "build" / "pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        log_dir = self.book_root / "build" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{tex_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        compiler = find_latex_compiler(engine or "latexmk")
        if not compiler:
            compiler = find_latex_compiler(engine)
        if not compiler:
            result = CompileResult(
                status="failed",
                tex_path=tex_path,
                pdf_path=None,
                log_path=log_path,
                command=[],
                errors=["No LaTeX compiler found on PATH."],
            )
            self._write_log(result)
            return result

        command = self._command(compiler.name, compiler.path, tex_path, output_dir)
        env = os.environ.copy()
        tex_inputs = self._tex_inputs()
        if tex_inputs:
            env["TEXINPUTS"] = os.pathsep.join(tex_inputs + [env.get("TEXINPUTS", "")])

        completed = subprocess.run(
            command,
            cwd=self.book_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        pdf_path = output_dir / f"{tex_path.stem}.pdf"
        errors = self._extract_errors(completed.stdout + "\n" + completed.stderr)
        status = "passed" if completed.returncode == 0 and pdf_path.exists() else "failed"
        result = CompileResult(
            status=status,
            tex_path=tex_path,
            pdf_path=pdf_path if pdf_path.exists() else None,
            log_path=log_path,
            command=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            errors=errors,
            artifacts=[str(pdf_path)] if pdf_path.exists() else [],
        )
        self._write_log(result)
        return result

    def _command(self, name: str, path: str, tex_path: Path, output_dir: Path) -> list[str]:
        relative_tex = str(tex_path.relative_to(self.book_root))
        relative_output = str(output_dir.relative_to(self.book_root))
        if name == "latexmk":
            return [
                path,
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                f"-output-directory={relative_output}",
                relative_tex,
            ]
        return [
            path,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            f"-output-directory={relative_output}",
            relative_tex,
        ]

    def _tex_inputs(self) -> list[str]:
        settings = DesignSettingsService(self.repository, self.project_root).get()
        style = DocumentStyleRegistry(self.project_root).get(settings["style_id"])
        return style.tex_inputs

    def _extract_errors(self, output: str) -> list[str]:
        errors = []
        for line in output.splitlines():
            if line.startswith("!") or re.search(r":\d+: (Emergency stop|Undefined control sequence|LaTeX Error)", line):
                errors.append(line)
        return errors[:25]

    def _write_log(self, result: CompileResult) -> None:
        result.log_path.write_text(json.dumps(result.as_dict(), indent=2) + "\n")
