"""Allowlist-based Obsidian Markdown import."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

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
    db_id: str | None
    import_key: str
    content_hash: str


@dataclass
class ImportResult:
    imported: list[dict[str, Any]] = field(default_factory=list)
    planned: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


@dataclass
class SyncResult:
    planned: list[dict[str, Any]] = field(default_factory=list)
    applied: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def blocking_actions(self) -> list[dict[str, Any]]:
        return [
            item
            for item in self.planned
            if item.get("action") in {"conflict", "reject", "error"}
        ]


TYPE_DEFAULT_FIELDS = {
    "fact": {"statement", "source", "confidence", "status", "metadata"},
    "decision": {"decision", "rationale", "consequences", "status", "metadata"},
    "open_question": {"question", "answer", "status", "metadata"},
    "risk": {"title", "severity", "impact", "mitigation", "status", "metadata"},
    "report": {"title", "report_type", "summary", "body", "status", "metadata"},
}

TYPE_TABLES = {
    "fact": "facts",
    "decision": "decisions",
    "open_question": "open_questions",
    "risk": "risks",
    "report": "reports",
}

TYPE_COLUMNS = {
    "fact": ("statement", "source", "confidence", "status"),
    "decision": ("decision", "rationale", "consequences", "status"),
    "open_question": ("question", "answer", "status"),
    "risk": ("title", "severity", "impact", "mitigation", "status"),
    "report": ("title", "report_type", "summary", "body", "status"),
}

TYPE_DEFAULT_VALUES = {
    "fact": {"confidence": 0.9, "status": "verified"},
    "decision": {"status": "accepted"},
    "open_question": {"status": "open"},
    "risk": {"severity": "medium", "status": "open"},
    "report": {"report_type": "status", "status": "published"},
}

FIELD_OWNERS = {
    memory_type: {column: "obsidian" for column in columns}
    for memory_type, columns in TYPE_COLUMNS.items()
}

STATUS_VALUES = {
    "fact": {"proposed", "verified", "disputed", "deprecated", "archived"},
    "decision": {"proposed", "accepted", "rejected", "superseded", "archived"},
    "open_question": {"open", "answered", "deferred", "closed", "archived"},
    "risk": {"open", "mitigating", "accepted", "resolved", "archived"},
    "report": {"draft", "published", "superseded", "archived"},
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


def relative_import_path(path: Path, allowlist: ImportAllowlist) -> str:
    resolved = path.resolve()
    for root in allowlist.roots:
        if is_relative_to(resolved, root):
            return str(resolved.relative_to(root))
    return str(resolved)


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


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        normalize_value(value),
        default=json_default,
        ensure_ascii=False,
        sort_keys=True,
    )


def hash_payload(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def item_values(item: ImportItem) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in TYPE_COLUMNS[item.memory_type]:
        values[column] = item.data.get(
            column,
            TYPE_DEFAULT_VALUES[item.memory_type].get(column),
        )
    return values


def row_values(memory_type: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        column: normalize_value(row.get(column))
        for column in TYPE_COLUMNS[memory_type]
    }


def user_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if key != "agent_hub_import"}


def import_metadata(item: ImportItem, existing_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(user_metadata(existing_metadata or {}))
    metadata.update(dict(item.data.get("metadata") or {}))
    now = datetime.now(timezone.utc).isoformat()
    metadata["agent_hub_import"] = {
        "import_key": item.import_key,
        "source_path": str(item.path),
        "content_hash": item.content_hash,
        "data_hash": hash_payload(item_values(item)),
        "data": normalize_value(item_values(item)),
        "last_imported_at": now,
        "imported_by": "agent-hub import",
    }
    return metadata


def derive_import_key(
    path: Path,
    allowlist: ImportAllowlist,
    frontmatter: dict[str, Any],
    memory_type: str,
    project_slug: str,
) -> str:
    explicit = frontmatter.get("import_key")
    if explicit is not None:
        if not isinstance(explicit, str) or not explicit.strip():
            raise RuntimeError("import_key must be a non-empty string")
        return explicit.strip()

    db_id = frontmatter.get("db_id")
    if db_id is not None:
        return f"{memory_type}:{db_id}"

    relative_path = relative_import_path(path, allowlist)
    return f"{project_slug}:{memory_type}:{relative_path}"


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
    if "status" in data and data["status"] not in STATUS_VALUES[memory_type]:
        raise RuntimeError(
            f"Unsupported status for {memory_type}: {data['status']}"
        )
    if memory_type == "report" and "body" in allowed_fields and "body" not in data:
        data["body"] = body

    missing = REQUIRED_FIELDS[memory_type] - data.keys()
    if missing:
        raise RuntimeError(
            f"Missing required field(s) for {memory_type}: {', '.join(sorted(missing))}"
        )

    db_id = frontmatter.get("db_id")
    if db_id is not None and not isinstance(db_id, str):
        raise RuntimeError("db_id must be a string when provided")
    import_key = derive_import_key(path, allowlist, frontmatter, memory_type, project_slug)
    content_hash = hash_payload(
        {
            "type": memory_type,
            "project": project_slug,
            "data": data,
        }
    )

    return ImportItem(
        path=path,
        frontmatter=frontmatter,
        body=body,
        project_slug=project_slug,
        memory_type=memory_type,
        data=data,
        db_id=db_id,
        import_key=import_key,
        content_hash=content_hash,
    )


def fetch_project(cur, project_slug: str) -> dict[str, Any]:
    cur.execute("SELECT id, name, slug FROM projects WHERE slug = %s", (project_slug,))
    project = cur.fetchone()
    if not project:
        raise RuntimeError(f"Project not found: {project_slug}")
    return project


def ensure_import_agent(cur, project_id: Any) -> dict[str, Any]:
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
        (project_id,),
    )
    return cur.fetchone()


def log_import_action(
    cur,
    agent_id: Any,
    action: str,
    object_type: str,
    object_id: Any,
    item: ImportItem,
    output: dict[str, Any],
) -> None:
    cur.execute(
        """
        INSERT INTO agent_actions (
          agent_id, action, object_type, object_id, input, output, status, metadata
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb,
                'succeeded', %s::jsonb)
        """,
        (
            agent_id,
            action,
            object_type,
            object_id,
            json.dumps(
                {
                    "path": str(item.path),
                    "type": item.memory_type,
                    "import_key": item.import_key,
                }
            ),
            json.dumps(output, default=json_default),
            json.dumps({"created_by": "agent-hub import"}),
        ),
    )


def insert_import_item(cur, item: ImportItem) -> dict[str, Any]:
    project = fetch_project(cur, item.project_slug)
    agent = ensure_import_agent(cur, project["id"])
    metadata = import_metadata(item)

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
    log_import_action(
        cur,
        agent["id"],
        "import_obsidian_note",
        object_type,
        row["id"],
        item,
        {"project_id": str(project["id"]), "object_id": str(row["id"])},
    )
    return {
        "action": "create",
        "path": str(item.path),
        "project": project["slug"],
        "type": object_type,
        "id": str(row["id"]),
        "import_key": item.import_key,
    }


def fetch_existing_import(cur, item: ImportItem, project_id: Any) -> dict[str, Any] | None:
    table = TYPE_TABLES[item.memory_type]
    columns = ", ".join(TYPE_COLUMNS[item.memory_type])
    if item.db_id:
        cur.execute(
            f"""
            SELECT id, project_id, metadata, updated_at, {columns}
            FROM {table}
            WHERE id = %s AND project_id = %s
            """,
            (item.db_id, project_id),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"db_id not found for {item.memory_type}: {item.db_id}")
        return row

    cur.execute(
        f"""
        SELECT id, project_id, metadata, updated_at, {columns}
        FROM {table}
        WHERE project_id = %s
          AND metadata #>> '{{agent_hub_import,import_key}}' = %s
        ORDER BY updated_at DESC, id
        """,
        (project_id, item.import_key),
    )
    rows = cur.fetchall()
    if len(rows) > 1:
        raise RuntimeError(f"Multiple rows found for import_key: {item.import_key}")
    return rows[0] if rows else None


def values_equal(left: Any, right: Any) -> bool:
    return canonical_json(left) == canonical_json(right)


def build_field_diffs(item: ImportItem, existing: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = existing.get("metadata") or {}
    import_state = metadata.get("agent_hub_import") or {}
    last_data = import_state.get("data")
    if not isinstance(last_data, dict):
        last_data = {}

    database_values = row_values(item.memory_type, existing)
    markdown_values = item_values(item)
    diffs: list[dict[str, Any]] = []
    for field in TYPE_COLUMNS[item.memory_type]:
        database_value = normalize_value(database_values.get(field))
        markdown_value = normalize_value(markdown_values.get(field))
        last_value = normalize_value(last_data.get(field)) if field in last_data else None
        changed = not values_equal(database_value, markdown_value)
        changed_from_last = (
            field in last_data
            and (
                not values_equal(database_value, last_value)
                or not values_equal(markdown_value, last_value)
            )
        )
        if changed or changed_from_last:
            diffs.append(
                {
                    "field": field,
                    "database_value": database_value,
                    "markdown_value": markdown_value,
                    "last_imported_value": last_value,
                    "owner": FIELD_OWNERS[item.memory_type].get(field, "postgres"),
                }
            )
    return diffs


def changed_fields_from_last(
    memory_type: str,
    current_values: dict[str, Any],
    last_values: dict[str, Any],
) -> set[str]:
    return {
        field
        for field in TYPE_COLUMNS[memory_type]
        if field in last_values
        and not values_equal(current_values.get(field), last_values.get(field))
    }


def plan_import_item(
    cur,
    item: ImportItem,
    on_duplicate: str = "skip",
) -> dict[str, Any]:
    project = fetch_project(cur, item.project_slug)
    existing = fetch_existing_import(cur, item, project["id"])
    base = {
        "path": str(item.path),
        "project": project["slug"],
        "type": item.memory_type,
        "import_key": item.import_key,
    }
    if not existing:
        return {**base, "action": "create"}

    base["id"] = str(existing["id"])
    if on_duplicate == "error":
        return {**base, "action": "error", "reason": "duplicate import target"}
    if on_duplicate == "skip":
        return {**base, "action": "skip", "reason": "duplicate import target"}

    metadata = existing.get("metadata") or {}
    import_state = metadata.get("agent_hub_import") or {}
    previous_content_hash = import_state.get("content_hash")
    previous_data_hash = import_state.get("data_hash")
    last_data = import_state.get("data")
    if not isinstance(last_data, dict):
        last_data = {}
    database_values = row_values(item.memory_type, existing)
    markdown_values = item_values(item)
    current_data_hash = hash_payload(database_values)
    note_changed = previous_content_hash != item.content_hash
    database_changed = bool(previous_data_hash and previous_data_hash != current_data_hash)
    diffs = build_field_diffs(item, existing)

    if previous_content_hash == item.content_hash:
        if database_changed:
            database_fields = sorted(
                changed_fields_from_last(item.memory_type, database_values, last_data)
            )
            return {
                **base,
                "action": "skip",
                "reason": "database changed since last import; markdown unchanged",
                "database_changed_fields": database_fields,
            }
        return {**base, "action": "skip", "reason": "unchanged import content"}
    if note_changed and database_changed:
        database_fields = changed_fields_from_last(
            item.memory_type,
            database_values,
            last_data,
        )
        markdown_fields = changed_fields_from_last(
            item.memory_type,
            markdown_values,
            last_data,
        )
        conflicting_fields = sorted(database_fields & markdown_fields)
        return {
            **base,
            "action": "conflict",
            "reason": "database and markdown changed since last import",
            "diffs": diffs,
            "conflicting_fields": conflicting_fields,
        }
    return {**base, "action": "update", "diffs": diffs}


def update_import_item(
    cur,
    item: ImportItem,
    planned: dict[str, Any],
) -> dict[str, Any]:
    project = fetch_project(cur, item.project_slug)
    agent = ensure_import_agent(cur, project["id"])
    existing = fetch_existing_import(cur, item, project["id"])
    if not existing:
        raise RuntimeError(f"Import target disappeared: {item.import_key}")

    values = item_values(item)
    columns = list(values)
    set_clause = ", ".join([f"{column} = %s" for column in columns])
    metadata = import_metadata(item, existing.get("metadata") or {})
    params = [values[column] for column in columns]
    params.extend([json.dumps(metadata, default=json_default), existing["id"]])
    table = TYPE_TABLES[item.memory_type]
    if item.memory_type == "open_question":
        set_clause += (
            ", resolved_at = CASE "
            "WHEN status IN ('answered', 'closed') THEN COALESCE(resolved_at, now()) "
            "ELSE NULL END"
        )
    cur.execute(
        f"""
        UPDATE {table}
        SET {set_clause}, metadata = %s::jsonb
        WHERE id = %s
        RETURNING id
        """,
        params,
    )
    row = cur.fetchone()
    log_import_action(
        cur,
        agent["id"],
        "sync_obsidian_note",
        item.memory_type,
        row["id"],
        item,
        {"project_id": str(project["id"]), "object_id": str(row["id"])},
    )
    return {
        **planned,
        "action": "update",
        "id": str(row["id"]),
    }


def apply_import_item(cur, item: ImportItem, planned: dict[str, Any]) -> dict[str, Any]:
    if planned["action"] == "create":
        return insert_import_item(cur, item)
    if planned["action"] == "update":
        return update_import_item(cur, item, planned)
    return planned


def load_import_items(
    path: Path,
    allowlist_path: Path,
) -> tuple[ImportAllowlist, list[Path], ImportResult]:
    allowlist = load_allowlist(allowlist_path)
    result = ImportResult()
    try:
        files = iter_markdown_files(path, allowlist)
    except Exception as exc:
        result.errors.append({"path": str(path), "error": str(exc)})
        return allowlist, [], result
    return allowlist, files, result


def import_markdown(
    path: Path,
    allowlist_path: Path,
    conn,
    dry_run: bool = False,
    on_duplicate: str = "skip",
) -> ImportResult:
    allowlist, files, result = load_import_items(path, allowlist_path)
    with conn.cursor() as cur:
        for file in files:
            try:
                item = normalize_import_item(file, allowlist)
                planned = plan_import_item(cur, item, on_duplicate=on_duplicate)
                if planned["action"] in {"error", "conflict", "reject"}:
                    result.errors.append(
                        {
                            "path": str(file),
                            "error": planned.get("reason", planned["action"]),
                        }
                    )
                    continue
                if dry_run or planned["action"] == "skip":
                    result.planned.append(planned)
                    continue
                result.imported.append(apply_import_item(cur, item, planned))
            except Exception as exc:
                result.errors.append({"path": str(file), "error": str(exc)})

    return result


def sync_markdown(
    path: Path,
    allowlist_path: Path,
    conn,
    apply: bool = False,
) -> SyncResult:
    allowlist, files, import_result = load_import_items(path, allowlist_path)
    result = SyncResult(errors=import_result.errors)
    normalized: list[tuple[ImportItem, dict[str, Any]]] = []

    with conn.cursor() as cur:
        for file in files:
            try:
                item = normalize_import_item(file, allowlist)
                planned = plan_import_item(cur, item, on_duplicate="update")
                result.planned.append(planned)
                normalized.append((item, planned))
            except Exception as exc:
                result.planned.append(
                    {
                        "path": str(file),
                        "project": None,
                        "type": None,
                        "import_key": None,
                        "action": "reject",
                        "reason": str(exc),
                    }
                )

        blockers = result.blocking_actions
        if apply:
            if blockers or result.errors:
                log_sync_event(
                    cur,
                    status="failed",
                    payload={"planned": result.planned},
                    error="Sync apply blocked by conflicts or rejected notes",
                )
                return result
            for item, planned in normalized:
                if planned["action"] in {"create", "update"}:
                    result.applied.append(apply_import_item(cur, item, planned))
            log_sync_event(
                cur,
                status="succeeded",
                payload={
                    "planned": result.planned,
                    "applied": result.applied,
                },
            )

    return result


def log_sync_event(
    cur,
    status: str,
    payload: dict[str, Any],
    error: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO sync_events (source, direction, status, payload, error, metadata)
        VALUES ('obsidian', 'inbound', %s, %s::jsonb, %s, %s::jsonb)
        """,
        (
            status,
            json.dumps(payload, default=json_default),
            error,
            json.dumps({"created_by": "agent-hub sync"}),
        ),
    )
