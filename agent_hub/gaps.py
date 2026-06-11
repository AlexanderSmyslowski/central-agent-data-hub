"""Read-only gap and staleness signals for prepare context packs."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import math
from typing import Any

from agent_hub.statuses import (
    DRAFT_STATUS,
    INACTIVE_OPEN_QUESTION_STATUSES,
    INBOX_REVIEW_TYPES,
    table_for_item_type,
)
from agent_hub.writeback_routing import REVIEWED_STATUSES


DEFAULT_STALE_AFTER_DAYS = 42

PREPARE_TYPE_KEYS = (
    ("facts", "fact"),
    ("decisions", "decision"),
    ("risks", "risk"),
    ("open_questions", "open_question"),
    ("reports", "report"),
)

TYPE_LABELS = {
    "fact": "Fakten",
    "decision": "Entscheidungen",
    "risk": "Risiken",
    "open_question": "offenen Fragen",
    "report": "Berichten",
}

TYPE_COUNT_KEYS = {
    "fact": "facts",
    "decision": "decisions",
    "risk": "risks",
    "open_question": "open_questions",
    "report": "reports",
}


def parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_days(value: object, now: datetime) -> int | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    seconds = max(0.0, (now.astimezone(timezone.utc) - parsed).total_seconds())
    return int(math.ceil(seconds / 86400))


def is_reviewed(row: dict[str, object], item_type: str) -> bool:
    return str(row.get("status")) in REVIEWED_STATUSES.get(item_type, set())


def item_age(row: dict[str, object], now: datetime) -> int | None:
    return age_days(row.get("updated_at") or row.get("created_at"), now)


def stale_item_reason(stale_after_days: int) -> str:
    return f"older than stale_after_days threshold ({stale_after_days} days)"


def collect_stale_items(
    compiled: dict[str, object],
    *,
    now: datetime,
    stale_after_days: int,
) -> list[dict[str, object]]:
    stale = []
    threshold = timedelta(days=stale_after_days)
    current = now.astimezone(timezone.utc)
    for payload_key, item_type in PREPARE_TYPE_KEYS:
        for row in compiled.get(payload_key, []):
            if not isinstance(row, dict) or not is_reviewed(row, item_type):
                continue
            updated_at = parse_datetime(row.get("updated_at") or row.get("created_at"))
            if updated_at is None or current - updated_at <= threshold:
                continue
            age = item_age(row, current)
            if age is None:
                continue
            stale.append(
                {
                    "type": item_type,
                    "id": row["id"],
                    "age_days": age,
                    "updated_at": updated_at.isoformat(),
                    "reason": stale_item_reason(stale_after_days),
                }
            )
    return stale


def collect_unanswered_questions(
    compiled: dict[str, object],
    *,
    now: datetime,
) -> list[dict[str, object]]:
    questions = []
    for row in compiled.get("open_questions", []):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        if status == DRAFT_STATUS or status in INACTIVE_OPEN_QUESTION_STATUSES:
            continue
        age = item_age(row, now)
        if age is None:
            continue
        questions.append(
            {
                "type": "open_question",
                "id": row["id"],
                "age_days": age,
                "updated_at": parse_datetime(
                    row.get("updated_at") or row.get("created_at")
                ).isoformat(),
                "reason": "open question remains unanswered",
            }
        )
    return questions


def collect_empty_types(compiled: dict[str, object]) -> list[dict[str, object]]:
    counts = compiled.get("active_counts")
    rows_by_type = {
        item_type: [
            row
            for row in compiled.get(payload_key, [])
            if isinstance(row, dict) and row.get("status") != DRAFT_STATUS
        ]
        for payload_key, item_type in PREPARE_TYPE_KEYS
    }
    empty = []
    for _payload_key, item_type in PREPARE_TYPE_KEYS:
        count_key = TYPE_COUNT_KEYS[item_type]
        count = counts.get(count_key) if isinstance(counts, dict) else None
        active_count = int(count) if count is not None else len(rows_by_type[item_type])
        if active_count == 0:
            empty.append(
                {
                    "type": item_type,
                    "reason": f"no active {item_type} items are recorded",
                }
            )
    return empty


def collect_task_blind_spots(
    compiled: dict[str, object],
    task: str,
) -> list[dict[str, object]]:
    blind_spots = []
    for payload_key, item_type in PREPARE_TYPE_KEYS:
        rows = [
            row
            for row in compiled.get(payload_key, [])
            if isinstance(row, dict) and row.get("status") != DRAFT_STATUS
        ]
        if not rows:
            continue
        matched = any(row.get("task_score") is not None for row in rows)
        explicit_no_match = any(
            "matched no reviewed items" in str(row.get("prepare_reason") or "")
            for row in rows
        )
        if not matched and (explicit_no_match or payload_key in {"risks", "open_questions"}):
            blind_spots.append(
                {
                    "type": item_type,
                    "task": task,
                    "reason": "task matched no reviewed items in this type",
                }
            )
    return blind_spots


def pending_drafts_summary(compiled: dict[str, object]) -> dict[str, object]:
    counts = compiled.get("pending_draft_counts")
    if isinstance(counts, dict):
        by_type = {
            key: int(counts.get(key, 0))
            for key in ("facts", "decisions", "risks", "open_questions", "reports")
        }
    else:
        drafts = compiled.get("drafts_pending_review", {})
        by_type = {
            key: len(drafts.get(key, [])) if isinstance(drafts, dict) else 0
            for key in ("facts", "decisions", "risks", "open_questions", "reports")
        }
    total = sum(by_type.values())
    return {
        "total": total,
        "by_type": by_type,
        "reason": "drafts require explicit review before they become reviewed memory",
    }


def collect_prepare_gaps(
    compiled: dict[str, object],
    task: str,
    now: datetime,
    *,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> dict[str, object]:
    """Collect read-only gap signals for a prepare pack.

    Items are considered stale only when they are older than the threshold.
    Exactly at the threshold they are still treated as fresh.
    """
    gaps = {
        "thresholds": {
            "stale_after_days": stale_after_days,
        },
        "stale_items": collect_stale_items(
            compiled,
            now=now,
            stale_after_days=stale_after_days,
        ),
        "unanswered_questions": collect_unanswered_questions(compiled, now=now),
        "empty_types": collect_empty_types(compiled),
        "task_blind_spots": collect_task_blind_spots(compiled, task),
        "pending_drafts": pending_drafts_summary(compiled),
    }
    gaps["summary"] = gap_summary(gaps)
    return gaps


def gap_summary(gaps: dict[str, object]) -> dict[str, object]:
    pending = gaps.get("pending_drafts")
    pending_total = pending.get("total", 0) if isinstance(pending, dict) else 0
    return {
        "stale": len(gaps.get("stale_items", [])),
        "unanswered": len(gaps.get("unanswered_questions", [])),
        "empty_types": len(gaps.get("empty_types", [])),
        "blind_spots": len(gaps.get("task_blind_spots", [])),
        "pending_drafts": int(pending_total),
        "thresholds": gaps.get("thresholds", {}),
    }


def fetch_pending_draft_counts(cur, project_id: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item_type in INBOX_REVIEW_TYPES:
        table = table_for_item_type(item_type)
        key = "open_questions" if item_type == "open_question" else f"{item_type}s"
        cur.execute(
            f"""
            SELECT count(*) AS count
            FROM {table}
            WHERE project_id = %s
              AND status = %s
            """,
            (project_id, DRAFT_STATUS),
        )
        counts[key] = int(cur.fetchone()["count"])
    return counts


def gap_markdown_lines(gaps: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for item in gaps.get("stale_items", []):
        lines.append(
            "Was fehlt: "
            f"{item['type']} {item['id']} ist seit {item['age_days']} Tagen nicht aktualisiert. "
            "Quelle: Prepare. "
            "Folge bei Irrtum: Der Agent nutzt veralteten Kontext."
        )
    for item in gaps.get("unanswered_questions", []):
        lines.append(
            "Was fehlt: "
            f"open_question {item['id']} ist seit {item['age_days']} Tagen offen. "
            "Quelle: Prepare. "
            "Folge bei Irrtum: Die Arbeit übersieht eine offene Entscheidung."
        )
    for item in gaps.get("empty_types", []):
        label = TYPE_LABELS.get(str(item["type"]), str(item["type"]))
        lines.append(
            f"Was fehlt: Zu {label} ist hier nichts erfasst. "
            "Quelle: Quality counts. "
            "Folge bei Irrtum: Der Agent unterschätzt diesen Bereich."
        )
    for item in gaps.get("task_blind_spots", []):
        label = TYPE_LABELS.get(str(item["type"]), str(item["type"]))
        lines.append(
            f"Was fehlt: Zum Task wurde bei {label} nichts gefunden. "
            "Quelle: Prepare. "
            "Folge bei Irrtum: Der Agent arbeitet ohne passenden geprüften Kontext."
        )
    pending = gaps.get("pending_drafts")
    if isinstance(pending, dict) and int(pending.get("total", 0)) > 0:
        lines.append(
            "Was fehlt: "
            f"{pending['total']} Entwürfe warten auf Review. "
            "Quelle: Inbox. "
            "Folge bei Irrtum: Nützlicher Kontext bleibt unbestätigt."
        )
    return lines


def known_gaps_markdown(gaps: dict[str, object]) -> str:
    lines = gap_markdown_lines(gaps)
    if not lines:
        return "- none"
    return "\n".join(f"- {line}" for line in lines)
