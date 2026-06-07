"""Import and sync workflow orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg

from agent_hub.importing.allowlist import iter_markdown_files, load_allowlist
from agent_hub.importing.identity import json_default
from agent_hub.importing.markdown import normalize_import_item
from agent_hub.importing.models import ImportAllowlist, ImportItem, ImportResult, SyncResult
from agent_hub.importing.store import apply_import_item, plan_import_item


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
    conn: psycopg.Connection,
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
    conn: psycopg.Connection,
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
    source: str = "obsidian",
    direction: str = "inbound",
) -> None:
    cur.execute(
        """
        INSERT INTO sync_events (source, direction, status, payload, error, metadata)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb)
        """,
        (
            source,
            direction,
            status,
            json.dumps(payload, default=json_default),
            error,
            json.dumps({"created_by": "agent-hub sync"}),
        ),
    )
