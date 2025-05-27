# scripts/gardener_agent.py

import os
import subprocess
import yaml
from pathlib import Path
from datetime import datetime

BOOK_ROOT = Path("book_data/codynamic_theory_book")
OUTLINE_PATH = BOOK_ROOT / "outline/codynamic_theory.yaml"
SECTION_PAYLOAD_DIR = BOOK_ROOT / "tex/section_payloads"
RENDER_OUTPUT_DIR = BOOK_ROOT / "renders"
LOG_PATH = BOOK_ROOT / f"logs/gardener_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

RENDER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_outline():
    with open(OUTLINE_PATH, "r") as f:
        return yaml.safe_load(f)["outline"]


def compile_section_tex(section_id):
    tex_file = SECTION_PAYLOAD_DIR / f"{section_id}.tex"
    if not tex_file.exists():
        return False, f"Missing .tex file for {section_id}"

    tmp_dir = Path("/tmp/compile_test") / section_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_tex = tmp_dir / "snippet.tex"

    preamble = r"""
\documentclass[11pt]{article}
\usepackage[utf8]{inputenc}
\begin{document}
"""
    postamble = r"\end{document}"

    with open(tmp_tex, "w") as f:
        f.write(preamble)
        f.write(tex_file.read_text())
        f.write(postamble)

    try:
        subprocess.run(["pdflatex", "-halt-on-error", tmp_tex.name], cwd=tmp_dir, capture_output=True, timeout=10)
        pdf_file = tmp_dir / "snippet.pdf"
        if not pdf_file.exists():
            return False, f"LaTeX failed to compile for {section_id}"

        # Optionally generate PNG
        output_image = RENDER_OUTPUT_DIR / f"{section_id}.png"
        subprocess.run(["convert", "-density", "150", str(pdf_file), str(output_image)], timeout=10)
        return True, f"Rendered successfully to {output_image}"
    except subprocess.TimeoutExpired:
        return False, f"Compilation timed out for {section_id}"


def validate_outline_payloads():
    outline = load_outline()
    logs = []

    for chapter in outline.get("chapters", []):
        for section in chapter.get("sections", []):
            section_id = section["id"]
            success, message = compile_section_tex(section_id)
            logs.append((section_id, success, message))

    with open(LOG_PATH, "w") as log_file:
        for sid, success, msg in logs:
            line = f"[{sid}] {'OK' if success else 'FAIL'} - {msg}\n"
            print(line.strip())
            log_file.write(line)


if __name__ == "__main__":
    validate_outline_payloads()