"""Markdown rendering helpers for Obsidian exports."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader

HUMAN_NOTES_PATTERN = re.compile(
    r"(<!-- HUMAN-NOTES:START -->)(.*?)(<!-- HUMAN-NOTES:END -->)",
    re.DOTALL,
)


def default_templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates"


def load_environment(templates_dir: Path | None = None) -> Environment:
    template_path = templates_dir or default_templates_dir()
    return Environment(
        loader=FileSystemLoader(str(template_path)),
        autoescape=False,
    )


def render_markdown(
    template_name: str,
    context: Mapping[str, Any],
    templates_dir: Path | None = None,
) -> str:
    env = load_environment(templates_dir)
    return env.get_template(template_name).render(**context).rstrip() + "\n"


def extract_human_notes(markdown: str) -> str | None:
    match = HUMAN_NOTES_PATTERN.search(markdown)
    if not match:
        return None
    return match.group(2)


def preserve_human_notes(rendered: str, existing: str) -> str:
    notes = extract_human_notes(existing)
    if notes is None:
        return rendered

    def replace_notes(match: re.Match[str]) -> str:
        return f"{match.group(1)}{notes}{match.group(3)}"

    return HUMAN_NOTES_PATTERN.sub(replace_notes, rendered, count=1)


def write_markdown(path: Path, rendered: str) -> None:
    output = rendered
    if path.exists():
        output = preserve_human_notes(rendered, path.read_text(encoding="utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output, encoding="utf-8")
