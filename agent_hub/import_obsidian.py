"""Allowlist-based Obsidian Markdown import."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ALLOWED_TYPES = ("fact", "decision", "open_question", "risk", "report")
SENSITIVE_PATTERN = re.compile(
    r"("
    r"password|secret|token|api[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|"
    r"ftp://|ftp\s*credentials?|ftp[_ -]?(user|password|pass|host)|"
    r"raw[_ -]?invoice|invoice[_ -]?(number|data)|rechnungs(daten|nummer)|"
    r"kundendaten|private[_ -]?customer|customer[_ -]?(email|phone|data)"
    r")",
    re.IGNORECASE,
)


@dataclass
class ImportAllowlist:
    projects: set[str]
    roots: list[Path]
    types: set[str]
    fields: dict[str, set[str]]
    path: Path


@dataclass
class ImportItem:
    path: Path
    frontmatter: dict[str, Any]
    body: str
    project_slug: str
    memory_type: str
    data: dict[str, Any]


@dataclass
class ImportResult:
    imported: list[dict[str, Any]] = field(default_factory=list)
    planned: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


TYPE_DEFAULT_FIELDS = {
    "fact": {"statement", "source", "confidence", "status", "metadata"},
    "decision": {"decision", "rationale", "consequences", "status", "metadata"},
    "open_question": {"question", "answer", "status", "metadata"},
    "risk": {"title", "severity", "impact", "mitigation", "status", "metadata"},
    "report": {"title", "report_type", "summary", "body", "status", "metadata"},
}

REQUIRED_FIELDS = {
    "fact": {"statement", "source"},
    "decision": {"decision"},
    "open_question": {"question"},
    "risk": {"title"},
    "report": {"title"},
}


def load_allowlist(path: Path) -> ImportAllowlist:
    if not path.exists():
        raise RuntimeError(f"Import allowlist not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError("Import allowlist must be a YAML mapping")

    projects = raw.get("projects")
    roots = raw.get("roots")
    types = raw.get("types")
    fields = raw.get("fields")
    if not isinstance(projects, list) or not all(isinstance(v, str) for v in projects):
        raise RuntimeError("Import allowlist requires projects as a list of slugs")
    if not isinstance(roots, list) or not all(isinstance(v, str) for v in roots):
        raise RuntimeError("Import allowlist requires roots as a list of paths")
    if not isinstance(types, list) or not all(isinstance(v, str) for v in types):
        raise RuntimeError("Import allowlist requires types as a list")
    if not isinstance(fields, dict):
        raise RuntimeError("Import allowlist requires fields as a mapping")

    type_set = set(types)
    unsupported = type_set - set(ALLOWED_TYPES)
    if unsupported:
        raise RuntimeError(f"Unsupported allowlist type(s): {', '.join(sorted(unsupported))}")

    normalized_fields: dict[str, set[str]] = {}
    for memory_type in type_set:
        values = fields.get(memory_type)
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise RuntimeError(f"Import allowlist requires fields.{memory_type} as a list")
        allowed_fields = set(values)
        unsupported_fields = allowed_fields - TYPE_DEFAULT_FIELDS[memory_type]
        if unsupported_fields:
            raise RuntimeError(
                f"Unsupported field(s) for {memory_type}: "
                f"{', '.join(sorted(unsupported_fields))}"
            )
        normalized_fields[memory_type] = allowed_fields

    base = path.resolve().parent
    root_paths = [
        (base / root).resolve() if not Path(root).is_absolute() else Path(root).resolve()
        for root in roots
    ]

    return ImportAllowlist(
        projects=set(projects),
        roots=root_paths,
        types=type_set,
        fields=normalized_fields,
        path=path.resolve(),
    )


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def ensure_path_allowed(path: Path, allowlist: ImportAllowlist) -> Path:
    resolved = path.resolve()
    if not any(is_relative_to(resolved, root) for root in allowlist.roots):
        raise RuntimeError(f"Path is outside allowlisted import roots: {path}")
    return resolved


def iter_markdown_files(path: Path, allowlist: ImportAllowlist) -> list[Path]:
    resolved = ensure_path_allowed(path, allowlist)
    if resolved.is_file():
        if resolved.suffix.lower() != ".md":
            raise RuntimeError(f"Import path is not a Markdown file: {path}")
        return [resolved]
    if not resolved.is_dir():
        raise RuntimeError(f"Import path not found: {path}")
    return sorted(file for file in resolved.rglob("*.md") if file.is_file())


def parse_markdown(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise RuntimeError("Markdown file must start with YAML frontmatter")
    try:
        _, frontmatter_text, body = text.split("---", 2)
    except ValueError as exc:
        raise RuntimeError("Markdown file is missing closing frontmatter delimiter") from exc
    frontmatter = yaml.safe_load(frontmatter_text)
    if not isinstance(frontmatter, dict):
        raise RuntimeError("YAML frontmatter must be a mapping")
    return frontmatter, body.strip()


def contains_secret(frontmatter: dict[str, Any], body: str) -> bool:
    haystack = json.dumps(frontmatter, default=str, ensure_ascii=False) + "\n" + body
    return bool(SENSITIVE_PATTERN.search(haystack))


def normalize_import_item(path: Path, allowlist: ImportAllowlist) -> ImportItem:
    frontmatter, body = parse_markdown(path)
    if contains_secret(frontmatter, body):
        raise RuntimeError("Potential secret detected; refusing import")

    memory_type = frontmatter.get("type")
    if memory_type not in allowlist.types:
        raise RuntimeError(f"Unsupported or non-allowlisted type: {memory_type}")

    project_slug = frontmatter.get("project_slug") or frontmatter.get("project")
    if not isinstance(project_slug, str) or not project_slug:
        raise RuntimeError("Frontmatter requires project or project_slug")
    if project_slug not in allowlist.projects:
        raise RuntimeError(f"Project is not allowlisted: {project_slug}")

    allowed_fields = allowlist.fields[memory_type]
    data = {
        key: value
        for key, value in frontmatter.items()
        if key in allowed_fields and value is not None
    }
    if "metadata" in data and not isinstance(data["metadata"], dict):
        raise RuntimeError("metadata must be a mapping")
    if memory_type == "fact" and "confidence" in data:
        try:
            confidence = float(data["confidence"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("confidence must be a number from 0 to 1") from exc
        if confidence < 0 or confidence > 1:
            raise RuntimeError("confidence must be between 0 and 1")
        data["confidence"] = confidence
    if memory_type == "report" and "body" in allowed_fields and "body" not in data:
        data["body"] = body

    missing = REQUIRED_FIELDS[memory_type] - data.keys()
    if missing:
        raise RuntimeError(
            f"Missing required field(s) for {memory_type}: {', '.join(sorted(missing))}"
        )

    return ImportItem(
        path=path,
        frontmatter=frontmatter,
        body=body,
        project_slug=project_slug,
        memory_type=memory_type,
        data=data,
    )


def fetch_project(cur, project_slug: str) -> dict[str, Any]:
    cur.execute("SELECT id, name, slug FROM projects WHERE slug = %s", (project_slug,))
    project = cur.fetchone()
    if not project:
        raise RuntimeError(f"Project not found: {project_slug}")
    return project


def insert_import_item(cur, item: ImportItem) -> dict[str, Any]:
    project = fetch_project(cur, item.project_slug)

    cur.execute(
        """
        INSERT INTO agents (project_id, name, slug, role, status, metadata)
        VALUES (%s, 'Agent Hub Import', 'agent-hub-import', 'Obsidian import agent',
                'active', '{"interface": "agent-hub import"}'::jsonb)
        ON CONFLICT (project_id, slug) DO UPDATE SET
          name = EXCLUDED.name,
          role = EXCLUDED.role,
          status = EXCLUDED.status,
          metadata = agents.metadata || EXCLUDED.metadata
        RETURNING id
        """,
        (project["id"],),
    )
    agent = cur.fetchone()

    metadata = dict(item.data.get("metadata") or {})
    metadata.setdefault("imported_by", "agent-hub import")
    metadata.setdefault("import_source_path", str(item.path))

    if item.memory_type == "fact":
        cur.execute(
            """
            INSERT INTO facts (project_id, statement, source, confidence, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["statement"],
                item.data["source"],
                item.data.get("confidence", 0.9),
                item.data.get("status", "verified"),
                json.dumps(metadata),
            ),
        )
        object_type = "fact"
    elif item.memory_type == "decision":
        cur.execute(
            """
            INSERT INTO decisions (project_id, decision, rationale, consequences, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["decision"],
                item.data.get("rationale"),
                item.data.get("consequences"),
                item.data.get("status", "accepted"),
                json.dumps(metadata),
            ),
        )
        object_type = "decision"
    elif item.memory_type == "open_question":
        status = item.data.get("status", "open")
        cur.execute(
            """
            INSERT INTO open_questions (project_id, question, answer, status, resolved_at, metadata)
            VALUES (%s, %s, %s, %s,
                    CASE WHEN %s IN ('answered', 'closed', 'resolved') THEN now() ELSE NULL END,
                    %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["question"],
                item.data.get("answer"),
                status,
                status,
                json.dumps(metadata),
            ),
        )
        object_type = "open_question"
    elif item.memory_type == "risk":
        cur.execute(
            """
            INSERT INTO risks (project_id, title, severity, impact, mitigation, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["title"],
                item.data.get("severity", "medium"),
                item.data.get("impact"),
                item.data.get("mitigation"),
                item.data.get("status", "open"),
                json.dumps(metadata),
            ),
        )
        object_type = "risk"
    elif item.memory_type == "report":
        cur.execute(
            """
            INSERT INTO reports (project_id, title, report_type, summary, body, status, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
            """,
            (
                project["id"],
                item.data["title"],
                item.data.get("report_type", "status"),
                item.data.get("summary"),
                item.data.get("body", item.body),
                item.data.get("status", "published"),
                json.dumps(metadata),
            ),
        )
        object_type = "report"
    else:
        raise RuntimeError(f"Unsupported import type: {item.memory_type}")

    row = cur.fetchone()
    cur.execute(
        """
        INSERT INTO agent_actions (
          agent_id, action, object_type, object_id, input, output, status, metadata
        )
        VALUES (%s, 'import_obsidian_note', %s, %s, %s::jsonb, %s::jsonb,
                'succeeded', %s::jsonb)
        """,
        (
            agent["id"],
            object_type,
            row["id"],
            json.dumps({"path": str(item.path), "type": item.memory_type}),
            json.dumps({"project_id": str(project["id"]), "object_id": str(row["id"])}),
            json.dumps({"created_by": "agent-hub import"}),
        ),
    )
    return {
        "path": str(item.path),
        "project": project["slug"],
        "type": object_type,
        "id": str(row["id"]),
    }


def import_markdown(
    path: Path,
    allowlist_path: Path,
    conn,
    dry_run: bool = False,
) -> ImportResult:
    allowlist = load_allowlist(allowlist_path)
    result = ImportResult()

    try:
        files = iter_markdown_files(path, allowlist)
    except Exception as exc:
        result.errors.append({"path": str(path), "error": str(exc)})
        return result

    with conn.cursor() as cur:
        for file in files:
            try:
                item = normalize_import_item(file, allowlist)
                project = fetch_project(cur, item.project_slug)
                if dry_run:
                    result.planned.append(
                        {
                            "path": str(file),
                            "project": project["slug"],
                            "type": item.memory_type,
                        }
                    )
                    continue
                result.imported.append(insert_import_item(cur, item))
            except Exception as exc:
                result.errors.append({"path": str(file), "error": str(exc)})

    return result
