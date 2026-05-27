#!/usr/bin/env python3
"""Migrate outline-like inputs into the canonical work outline format."""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.outline_converter.converter import OutlineConverter


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert old YAML/text outlines to canonical work/structure/content YAML."
    )
    parser.add_argument("input", help="Input outline path or raw outline text")
    parser.add_argument("output", help="Output canonical YAML path")
    parser.add_argument(
        "--report",
        help="Human-readable migration report path. Defaults to <output>.migration.md",
    )
    parser.add_argument(
        "--format",
        dest="format_type",
        help="Optional source format override, e.g. yaml_v1, markdown, numbered_hierarchy.",
    )
    parser.add_argument(
        "--llm",
        choices=["auto", "always", "never"],
        default="auto",
        help="Use LLM-assisted conversion for unknown/ambiguous input, always, or never.",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else output_path.with_suffix(".migration.md")

    converter = OutlineConverter()
    converter.convert(
        args.input,
        output_path=str(output_path),
        report_path=str(report_path),
        format_type=args.format_type,
        interactive=False,
        use_llm=args.llm,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
