"""LaTeX tool discovery helpers."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Iterable, Optional


DEFAULT_LATEX_COMPILERS = ("latexmk", "pdflatex", "xelatex", "lualatex", "tectonic")


@dataclass(frozen=True)
class LatexCompiler:
    """A discovered LaTeX compiler executable."""

    name: str
    path: str


def find_latex_compilers(
    candidates: Iterable[str] = DEFAULT_LATEX_COMPILERS,
) -> list[LatexCompiler]:
    """Return available LaTeX compilers in preferred order."""
    discovered = []
    for name in candidates:
        path = shutil.which(name)
        if path:
            discovered.append(LatexCompiler(name=name, path=path))
    return discovered


def find_latex_compiler(preferred: Optional[str] = None) -> Optional[LatexCompiler]:
    """
    Return the preferred available LaTeX compiler.

    LATEX_ENGINE can force a specific executable name or absolute path. If it is
    unset, discovery falls back to DEFAULT_LATEX_COMPILERS in order.
    """
    requested = preferred or os.getenv("LATEX_ENGINE")
    if requested:
        path = shutil.which(requested)
        return LatexCompiler(name=requested, path=path) if path else None

    compilers = find_latex_compilers()
    return compilers[0] if compilers else None
