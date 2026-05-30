"""Shared helpers for Agent Data Hub command modules."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta, timezone
import json
import re

from agent_hub.rendering import truncate


def concise_error(exc: Exception) -> str:
    return str(exc).splitlines()[0]


def json_default(value: object) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def confidence_value(value: str) -> float:
    try:
        confidence = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "confidence must be a number from 0 to 1"
        ) from exc
    if confidence < 0 or confidence > 1:
        raise argparse.ArgumentTypeError("confidence must be between 0 and 1")
    return confidence


def parse_metadata(values: list[str] | None) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(
                f"Metadata entry must use key=value format: {value}"
            )
        key, raw = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("Metadata key must not be empty")
        try:
            metadata[key] = json.loads(raw)
        except json.JSONDecodeError:
            metadata[key] = raw
    return metadata


def fetch_project(cur, slug: str) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT id, name, slug, description, status, metadata, created_at, updated_at
        FROM projects
        WHERE slug = %s
        """,
        (slug,),
    )
    return cur.fetchone()


def print_relations(rows: list[dict[str, object]]) -> None:
    if not rows:
        print("- none")
        return
    for row in rows:
        source = (
            f"{row['source_type']}:{row['source_id']} "
            f"({truncate(row.get('source_summary') or '', 72)})"
        )
        target = (
            f"{row['target_type']}:{row['target_id']} "
            f"({truncate(row.get('target_summary') or '', 72)})"
        )
        print(f"- {source} --{row['relation_type']}--> {target}")
        if row.get("metadata"):
            print(
                "  metadata: "
                + json.dumps(row["metadata"], default=json_default, ensure_ascii=False)
            )


def print_rows(title: str, rows: list[dict[str, object]], text_key: str) -> None:
    print(f"## {title}")
    if not rows:
        print("- none")
        print()
        return
    for row in rows:
        status = row.get("status", "unknown")
        updated_at = row.get("updated_at")
        text = truncate(row[text_key], 180)
        print(f"- [{status}] {text}")
        if updated_at:
            print(f"  updated_at: {updated_at}")
    print()


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def parse_since(value: str | None, default: str = "24h") -> datetime:
    raw = value or default
    match = re.fullmatch(r"\s*(\d+)\s*([hdw])\s*", raw, flags=re.IGNORECASE)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        else:
            delta = timedelta(weeks=amount)
        return datetime.now(timezone.utc) - delta

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            "--since must be a duration like 24h, 7d, 2w or an ISO date"
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        parsed = datetime.combine(parsed.date(), time.min, tzinfo=parsed.tzinfo)
    return parsed
