"""Foundation smoke tests for local setup and CLI behavior."""

import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.utils.latex import find_latex_compiler, find_latex_compilers


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_main_status_smoke():
    result = subprocess.run(
        [sys.executable, "main.py", "status"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "BOOK MACHINE SYSTEM STATUS" in result.stdout
    assert "Phase: DISCOVERY" in result.stdout


def test_outline_validation_smoke(tmp_path):
    outline_dir = tmp_path / "book" / "outline"
    outline_dir.mkdir(parents=True)
    outline_path = outline_dir / "smoke_outline.yaml"
    outline_path.write_text(
        yaml.safe_dump(
            {
                "work": {
                    "id": "smoke_book",
                    "type": "book",
                    "title": "Smoke Book",
                    "structure": [
                        {
                            "type": "chapter",
                            "id": "ch1",
                            "title": "Opening",
                        }
                    ],
                }
            },
            sort_keys=False,
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            "main.py",
            "validate",
            str(outline_path),
            "--skip-bootstrap",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Passes strict schema validation" in result.stdout


def test_latex_compile_discovery_smoke():
    discovered = find_latex_compilers()
    discovered_names = {compiler.name for compiler in discovered}
    expected_names = {
        name
        for name in ("latexmk", "pdflatex", "xelatex", "lualatex", "tectonic")
        if shutil.which(name)
    }

    assert discovered_names == expected_names
    if discovered:
        assert find_latex_compiler() == discovered[0]
    else:
        assert find_latex_compiler() is None
