from __future__ import annotations

from pathlib import Path


ALLOWLIST = """
projects:
  - demo-website
roots:
  - notes
types:
  - fact
  - decision
  - open_question
  - risk
  - report
fields:
  fact: [statement, source, confidence, status, metadata]
  decision: [decision, rationale, consequences, status, metadata]
  open_question: [question, answer, status, metadata]
  risk: [title, severity, impact, mitigation, status, metadata]
  report: [title, report_type, summary, body, status, metadata]
"""


def write_allowlist(tmp_path: Path) -> Path:
    (tmp_path / "notes").mkdir()
    path = tmp_path / "import_allowlist.yml"
    path.write_text(ALLOWLIST, encoding="utf-8")
    return path


def write_note(path: Path, frontmatter: str, body: str = "") -> Path:
    path.write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return path
