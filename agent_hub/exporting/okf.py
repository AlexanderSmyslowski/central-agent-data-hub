"""Open Knowledge Format export preview."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_hub.db import connect
from agent_hub.errors import NotFoundError
from agent_hub.exporting.helpers import id_suffix, slugify
from agent_hub.statuses import REVIEWED_MEMORY_STATUSES

OKF_VERSION = "0.1"


@dataclass(frozen=True)
class OkfSpec:
    item_type: str
    table: str
    folder: str
    okf_type: str
    title_field: str
    description_field: str
    columns: str
    order_by: str = "created_at, id"


@dataclass(frozen=True)
class OkfFile:
    relative_path: Path
    content: str


OKF_SPECS: tuple[OkfSpec, ...] = (
    OkfSpec(
        item_type="fact",
        table="facts",
        folder="facts",
        okf_type="ADH Fact",
        title_field="statement",
        description_field="statement",
        columns="id, statement, source, confidence, status, metadata, created_at, updated_at",
    ),
    OkfSpec(
        item_type="decision",
        table="decisions",
        folder="decisions",
        okf_type="ADH Decision",
        title_field="decision",
        description_field="decision",
        columns="id, decision, rationale, consequences, status, metadata, created_at, updated_at",
    ),
    OkfSpec(
        item_type="risk",
        table="risks",
        folder="risks",
        okf_type="ADH Risk",
        title_field="title",
        description_field="impact",
        columns="id, title, severity, impact, mitigation, status, metadata, created_at, updated_at",
    ),
    OkfSpec(
        item_type="open_question",
        table="open_questions",
        folder="open_questions",
        okf_type="ADH Open Question",
        title_field="question",
        description_field="question",
        columns="id, question, answer, status, resolved_at, metadata, created_at, updated_at",
    ),
    OkfSpec(
        item_type="report",
        table="reports",
        folder="reports",
        okf_type="ADH Report",
        title_field="title",
        description_field="summary",
        columns="id, title, report_type, summary, body, status, metadata, created_at, updated_at",
    ),
)


def _string(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _one_line(value: object, *, limit: int = 180) -> str:
    text = " ".join(_string(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _timestamp(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _as_date(value: object) -> str:
    timestamp = _timestamp(value)
    if not timestamp:
        return datetime.now(timezone.utc).date().isoformat()
    return timestamp[:10]


def _metadata_tags(row: dict[str, Any], item_type: str, project_slug: str) -> list[str]:
    tags = ["agent-data-hub", project_slug, item_type]
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        raw_tags = metadata.get("tags")
        if isinstance(raw_tags, list):
            tags.extend(_string(tag) for tag in raw_tags if _string(tag))
    return list(dict.fromkeys(tags))


def _filename(row: dict[str, Any], field: str) -> str:
    stem = slugify(_string(row.get(field)) or "untitled")
    suffix = id_suffix(row)
    return f"{stem}-{suffix}.md" if suffix else f"{stem}.md"


def _frontmatter(
    *,
    spec: OkfSpec,
    row: dict[str, Any],
    project: dict[str, Any],
) -> dict[str, Any]:
    timestamp = _timestamp(row.get("updated_at") or row.get("created_at"))
    frontmatter: dict[str, Any] = {
        "type": spec.okf_type,
        "title": _one_line(row.get(spec.title_field), limit=100),
        "description": _one_line(row.get(spec.description_field), limit=180),
        "resource": f"adh://{project['slug']}/{spec.item_type}/{row['id']}",
        "tags": _metadata_tags(row, spec.item_type, str(project["slug"])),
        "timestamp": timestamp,
        "adh_id": str(row["id"]),
        "adh_type": spec.item_type,
        "adh_status": row.get("status"),
        "review_status": "reviewed",
        "project": project["slug"],
    }
    if spec.item_type == "fact" and row.get("source"):
        frontmatter["source"] = row["source"]
    if spec.item_type == "fact" and row.get("confidence") is not None:
        frontmatter["confidence"] = float(row["confidence"])
    return {key: value for key, value in frontmatter.items() if value not in ("", None)}


def _markdown_file(frontmatter: dict[str, Any], body: str) -> str:
    yaml_text = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{yaml_text}\n---\n\n{body.strip()}\n"


def _fact_body(row: dict[str, Any]) -> str:
    lines = ["# Summary", "", _string(row.get("statement"))]
    lines.extend(["", "# Provenance", "", f"- Status: `{row.get('status')}`"])
    if row.get("source"):
        lines.append(f"- Source: {_string(row.get('source'))}")
    if row.get("confidence") is not None:
        lines.append(f"- Confidence: {row['confidence']}")
    source = _string(row.get("source"))
    if source.startswith(("http://", "https://")):
        lines.extend(["", "# Citations", "", f"[1] [{source}]({source})"])
    return "\n".join(lines)


def _decision_body(row: dict[str, Any]) -> str:
    lines = ["# Decision", "", _string(row.get("decision"))]
    if row.get("rationale"):
        lines.extend(["", "# Rationale", "", _string(row.get("rationale"))])
    if row.get("consequences"):
        lines.extend(["", "# Consequences", "", _string(row.get("consequences"))])
    lines.extend(["", "# Provenance", "", f"- Status: `{row.get('status')}`"])
    return "\n".join(lines)


def _risk_body(row: dict[str, Any]) -> str:
    lines = ["# Risk", "", _string(row.get("title"))]
    if row.get("severity"):
        lines.extend(["", "# Severity", "", _string(row.get("severity"))])
    if row.get("impact"):
        lines.extend(["", "# Impact", "", _string(row.get("impact"))])
    if row.get("mitigation"):
        lines.extend(["", "# Mitigation", "", _string(row.get("mitigation"))])
    lines.extend(["", "# Provenance", "", f"- Status: `{row.get('status')}`"])
    return "\n".join(lines)


def _open_question_body(row: dict[str, Any]) -> str:
    lines = ["# Question", "", _string(row.get("question"))]
    if row.get("answer"):
        lines.extend(["", "# Answer", "", _string(row.get("answer"))])
    lines.extend(["", "# Provenance", "", f"- Status: `{row.get('status')}`"])
    if row.get("resolved_at"):
        lines.append(f"- Resolved at: {_timestamp(row.get('resolved_at'))}")
    return "\n".join(lines)


def _report_body(row: dict[str, Any]) -> str:
    lines = ["# Summary", "", _string(row.get("summary"))]
    if row.get("body"):
        lines.extend(["", "# Body", "", _string(row.get("body"))])
    lines.extend(["", "# Provenance", "", f"- Status: `{row.get('status')}`"])
    if row.get("report_type"):
        lines.append(f"- Report type: {_string(row.get('report_type'))}")
    return "\n".join(lines)


BODY_RENDERERS = {
    "fact": _fact_body,
    "decision": _decision_body,
    "risk": _risk_body,
    "open_question": _open_question_body,
    "report": _report_body,
}


def build_okf_files(
    *,
    project: dict[str, Any],
    rows_by_type: dict[str, list[dict[str, Any]]],
    generated_at: datetime | None = None,
) -> list[OkfFile]:
    generated = generated_at or datetime.now(timezone.utc)
    files: list[OkfFile] = []
    directory_entries: dict[str, list[tuple[str, str, str]]] = {}

    for spec in OKF_SPECS:
        entries: list[tuple[str, str, str]] = []
        for row in rows_by_type.get(spec.item_type, []):
            filename = _filename(row, spec.title_field)
            title = _one_line(row.get(spec.title_field), limit=100)
            description = _one_line(row.get(spec.description_field), limit=180)
            body = BODY_RENDERERS[spec.item_type](row)
            files.append(
                OkfFile(
                    Path(spec.folder) / filename,
                    _markdown_file(
                        _frontmatter(spec=spec, row=row, project=project),
                        body,
                    ),
                )
            )
            entries.append((title, filename, description))
        directory_entries[spec.folder] = entries
        files.append(OkfFile(Path(spec.folder) / "index.md", _directory_index(spec, entries)))

    files.insert(0, OkfFile(Path("index.md"), _root_index(project, directory_entries, generated)))
    files.append(OkfFile(Path("log.md"), _log_file(project, generated)))
    return files


def _directory_index(spec: OkfSpec, entries: list[tuple[str, str, str]]) -> str:
    title = spec.folder.replace("_", " ").title()
    lines = [f"# {title}", ""]
    if not entries:
        lines.append("No reviewed memory exported in this section.")
        return "\n".join(lines) + "\n"
    for item_title, filename, description in entries:
        suffix = f" - {description}" if description else ""
        lines.append(f"* [{item_title}]({filename}){suffix}")
    return "\n".join(lines) + "\n"


def _root_index(
    project: dict[str, Any],
    directory_entries: dict[str, list[tuple[str, str, str]]],
    generated_at: datetime,
) -> str:
    lines = [
        f"# {project['name']} OKF Export",
        "",
        "This bundle is generated from reviewed Agent Data Hub memory.",
        "",
        f"- OKF target: {OKF_VERSION}",
        f"- Project: `{project['slug']}`",
        f"- Generated at: {generated_at.isoformat()}",
        "- Included: reviewed facts, accepted decisions, active risks, open or answered questions, and published reports.",
        "- Excluded: drafts, proposed items, archived items, rejected decisions, resolved risks, and superseded reports.",
        "",
        "# Contents",
        "",
    ]
    for spec in OKF_SPECS:
        count = len(directory_entries.get(spec.folder, []))
        label = spec.folder.replace("_", " ").title()
        lines.append(f"* [{label}]({spec.folder}/) - {count} reviewed item(s)")
    return "\n".join(lines) + "\n"


def _log_file(project: dict[str, Any], generated_at: datetime) -> str:
    day = generated_at.date().isoformat()
    return (
        "# Directory Update Log\n\n"
        f"## {day}\n"
        f"* **Export**: Generated OKF preview bundle for `{project['slug']}` from reviewed Agent Data Hub memory.\n"
    )


def fetch_okf_project(cur, project_slug: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, name, slug, description, status, metadata, created_at, updated_at
        FROM projects
        WHERE slug = %s
        """,
        (project_slug,),
    )
    project = cur.fetchone()
    if not project:
        raise NotFoundError(f"Project not found: {project_slug}")
    return dict(project)


def fetch_okf_rows(cur, project_id: object) -> dict[str, list[dict[str, Any]]]:
    rows_by_type: dict[str, list[dict[str, Any]]] = {}
    for spec in OKF_SPECS:
        statuses = REVIEWED_MEMORY_STATUSES[spec.item_type]
        placeholders = ", ".join(["%s"] * len(statuses))
        cur.execute(
            f"""
            SELECT {spec.columns}
            FROM {spec.table}
            WHERE project_id = %s
              AND status IN ({placeholders})
            ORDER BY {spec.order_by}
            """,
            (project_id, *statuses),
        )
        rows_by_type[spec.item_type] = [dict(row) for row in cur.fetchall()]
    return rows_by_type


def write_okf_files(output_dir: Path, files: list[OkfFile]) -> list[Path]:
    written: list[Path] = []
    for item in files:
        path = output_dir / item.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.content, encoding="utf-8")
        written.append(path)
    return written


def export_project_okf(project_slug: str, output_dir: Path) -> list[Path]:
    with connect() as conn:
        with conn.cursor() as cur:
            project = fetch_okf_project(cur, project_slug)
            rows_by_type = fetch_okf_rows(cur, project["id"])
    files = build_okf_files(project=project, rows_by_type=rows_by_type)
    return write_okf_files(output_dir, files)
