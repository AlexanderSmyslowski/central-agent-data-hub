"""Mini-eval for prepare context pack selection.

These cases check that task-aware prepare selection picks the expected
reviewed items for hand-labeled tasks, not only that the command runs.

The fake cursor emulates the PostgreSQL `'simple'` full-text contract
deterministically: lowercase token equality, AND across task tokens, no
stemming, ordering `task_score DESC, created_at DESC, id DESC`. Cases that
exercise this contract (flexion limit, tie-breaking) are documented
expectations of the current selection mode, mirrored here so a future
live-database eval can replace the fake without changing case definitions.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from agent_hub.commands.prepare import (
    PREPARE_SPECS,
    merge_prepare_rows,
    select_ranked_prepare_rows,
    select_safety_floor_rows,
)


PROJECT_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")

TASK_MATCH_REASON = "included by deterministic task text match"
FALLBACK_AFTER_MATCH_REASON = "included as recent fallback after task-ranked context"
FALLBACK_NO_MATCH_REASON = (
    "included as recent fallback because task text matched no reviewed items in this type"
)
RISK_FLOOR_REASON = "included by safety floor for active risks"
QUESTION_FLOOR_REASON = "included by safety floor for unresolved open questions"


def simple_tokens(text: str) -> list[str]:
    """Tokenize like the `'simple'` text search configuration: lowercase
    alphanumeric tokens, no stemming, no stopword removal."""
    return re.findall(r"\w+", text.lower())


def search_fields(key: str) -> list[str]:
    """Derive the searched fields from the spec's concat_ws() expression so
    the fake stays aligned with PREPARE_SPECS."""
    spec = PREPARE_SPECS[key]
    inner = re.fullmatch(r"concat_ws\(' ', (.+)\)", spec["search"]).group(1)
    return [field.strip() for field in inner.split(",")]


class FakeSimpleFtsCursor:
    """Read-only cursor over an in-memory store of reviewed rows.

    Emulates the two prepare query shapes: recent rows ordered by
    `updated_at DESC, created_at DESC, id DESC`, and task matches with
    AND-of-tokens `'simple'` semantics ordered by
    `task_score DESC, created_at DESC, id DESC`.
    """

    def __init__(self, store: dict[str, list[dict[str, object]]]) -> None:
        self.store = store
        self.results: list[dict[str, object]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        if re.search(r"\b(INSERT|UPDATE|DELETE)\b", query.upper()):
            raise AssertionError("prepare must stay read-only")
        table = re.search(r"FROM (\w+)", query).group(1)
        rows = self.store.get(table, [])
        if "plainto_tsquery" in query:
            task, _project_id, *excluded, limit = params
            self.results = self._task_match_rows(table, rows, str(task), excluded, limit)
        else:
            _project_id, *excluded, limit = params
            self.results = self._recent_rows(rows, excluded, limit)

    def fetchall(self) -> list[dict[str, object]]:
        return self.results

    def _active_rows(
        self, rows: list[dict[str, object]], excluded: list[object]
    ) -> list[dict[str, object]]:
        return [row for row in rows if row["status"] not in excluded]

    def _recent_rows(
        self, rows: list[dict[str, object]], excluded: list[object], limit: object
    ) -> list[dict[str, object]]:
        active = self._active_rows(rows, excluded)
        ordered = sorted(
            active,
            key=lambda row: (row["updated_at"], row["created_at"], str(row["id"])),
            reverse=True,
        )
        return [dict(row) for row in ordered[: int(limit)]]

    def _task_match_rows(
        self,
        table: str,
        rows: list[dict[str, object]],
        task: str,
        excluded: list[object],
        limit: object,
    ) -> list[dict[str, object]]:
        task_tokens = simple_tokens(task)
        fields = search_fields(table)
        matches = []
        for row in self._active_rows(rows, excluded):
            document = " ".join(str(row[field]) for field in fields if row.get(field))
            document_tokens = simple_tokens(document)
            if not all(token in document_tokens for token in task_tokens):
                continue
            scored = dict(row)
            scored["task_score"] = float(
                sum(document_tokens.count(token) for token in task_tokens)
            )
            matches.append(scored)
        ordered = sorted(
            matches,
            key=lambda row: (row["task_score"], row["created_at"], str(row["id"])),
            reverse=True,
        )
        return ordered[: int(limit)]


def stored_row(
    key: str,
    id_suffix: str,
    *,
    status: str,
    created: str,
    updated: str | None = None,
    **fields: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": uuid.UUID(f"20000000-0000-4000-8000-000000000{id_suffix}"),
        "status": status,
        "created_at": datetime.fromisoformat(created),
        "updated_at": datetime.fromisoformat(updated or created),
    }
    row.update(fields)
    return row


def fact_row(id_suffix: str, statement: str, *, created: str, **overrides: object) -> dict[str, object]:
    return stored_row(
        "facts",
        id_suffix,
        status=str(overrides.pop("status", "verified")),
        created=created,
        statement=statement,
        source=overrides.pop("source", "README.md"),
        confidence=0.9,
        **overrides,
    )


def reasons(rows: list[dict[str, object]]) -> list[str]:
    return [str(row["prepare_reason"]) for row in rows]


def test_eval_task_match_fact_ranks_before_recent_fallback() -> None:
    # Documented expectation: plainto_tsquery ANDs all task tokens, so the
    # task must stay close to reviewed wording ("hub view", not
    # "harden hub view path") to reach the matching fact at all.
    cur = FakeSimpleFtsCursor(
        {
            "facts": [
                fact_row("101", "Backups are verified before writeback.", created="2026-06-08"),
                fact_row("102", "Hub View renders reviewed memory locally.", created="2026-06-01"),
                fact_row("103", "Import allowlist rejects secret patterns.", created="2026-06-05"),
            ]
        }
    )

    rows = select_ranked_prepare_rows(
        cur, project_id=PROJECT_ID, key="facts", task="hub view", limit=3
    )

    assert rows[0]["statement"] == "Hub View renders reviewed memory locally."
    assert rows[0]["prepare_reason"] == TASK_MATCH_REASON
    assert rows[0]["task_score"] > 0
    assert reasons(rows[1:]) == [FALLBACK_AFTER_MATCH_REASON] * 2


def test_eval_task_match_decision_selected_over_newer_unrelated_decision() -> None:
    cur = FakeSimpleFtsCursor(
        {
            "decisions": [
                stored_row(
                    "decisions",
                    "201",
                    status="accepted",
                    created="2026-06-09",
                    decision="Keep writeback reviewed.",
                    rationale="Unreviewed context must not become truth.",
                    consequences=None,
                ),
                stored_row(
                    "decisions",
                    "202",
                    status="accepted",
                    created="2026-06-02",
                    decision="Use deterministic ranking for prepare.",
                    rationale="Selection must stay explainable.",
                    consequences=None,
                ),
            ]
        }
    )

    rows = select_ranked_prepare_rows(
        cur,
        project_id=PROJECT_ID,
        key="decisions",
        task="deterministic prepare ranking",
        limit=2,
    )

    assert rows[0]["decision"] == "Use deterministic ranking for prepare."
    assert rows[0]["prepare_reason"] == TASK_MATCH_REASON
    assert rows[1]["prepare_reason"] == FALLBACK_AFTER_MATCH_REASON


def test_eval_unrelated_risk_stays_on_safety_floor() -> None:
    cur = FakeSimpleFtsCursor(
        {
            "risks": [
                stored_row(
                    "risks",
                    "301",
                    status="open",
                    created="2026-06-03",
                    title="Backup dumps silently outdated",
                    severity="high",
                    impact="Writeback could rely on stale state.",
                    mitigation="Verify backups before writeback.",
                ),
            ]
        }
    )

    rows = select_safety_floor_rows(
        cur, project_id=PROJECT_ID, key="risks", task="polish hub view css", limit=5
    )

    assert len(rows) == 1
    assert rows[0]["prepare_reason"] == RISK_FLOOR_REASON
    assert rows[0].get("task_score") is None


def test_eval_open_question_matching_task_is_labeled_not_promoted() -> None:
    cur = FakeSimpleFtsCursor(
        {
            "open_questions": [
                stored_row(
                    "open_questions",
                    "401",
                    status="open",
                    created="2026-06-06",
                    question="Should release checks include Hub View smoke?",
                    answer=None,
                ),
                stored_row(
                    "open_questions",
                    "402",
                    status="open",
                    created="2026-06-04",
                    question="Where should schema friction notes live?",
                    answer=None,
                ),
            ]
        }
    )

    rows = select_safety_floor_rows(
        cur,
        project_id=PROJECT_ID,
        key="open_questions",
        task="release checks",
        limit=5,
    )

    assert len(rows) == 2
    matching = next(row for row in rows if "release" in str(row["question"]).lower())
    other = next(row for row in rows if row is not matching)
    assert matching["prepare_reason"] == f"{QUESTION_FLOOR_REASON}; also matched task text"
    assert matching["task_score"] > 0
    assert other["prepare_reason"] == QUESTION_FLOOR_REASON


def test_eval_no_match_falls_back_to_recent_with_explicit_reason() -> None:
    cur = FakeSimpleFtsCursor(
        {
            "facts": [
                fact_row("111", "Backups are verified before writeback.", created="2026-06-08"),
                fact_row("112", "Hub View renders reviewed memory locally.", created="2026-06-01"),
            ]
        }
    )

    rows = select_ranked_prepare_rows(
        cur, project_id=PROJECT_ID, key="facts", task="quarterly tax filing", limit=2
    )

    assert reasons(rows) == [FALLBACK_NO_MATCH_REASON] * 2
    assert rows[0]["statement"] == "Backups are verified before writeback."


def test_eval_simple_fts_does_not_stem_flexion_variants() -> None:
    # Documented expectation of the 'simple' configuration: no stemming, so
    # "deployments" does not reach a fact that only says "deployment".
    cur = FakeSimpleFtsCursor(
        {
            "facts": [
                fact_row("121", "Deployment requires explicit human approval.", created="2026-06-07"),
            ]
        }
    )

    rows = select_ranked_prepare_rows(
        cur, project_id=PROJECT_ID, key="facts", task="deployments", limit=1
    )

    assert reasons(rows) == [FALLBACK_NO_MATCH_REASON]


def test_eval_mixed_german_english_task_matches_exact_tokens() -> None:
    cur = FakeSimpleFtsCursor(
        {
            "facts": [
                fact_row(
                    "131",
                    "Backup verification läuft täglich über db_backup_health.sh.",
                    created="2026-06-05",
                ),
                fact_row("132", "Hub View bleibt eine lokale Review-Oberfläche.", created="2026-06-09"),
            ]
        }
    )

    rows = select_ranked_prepare_rows(
        cur,
        project_id=PROJECT_ID,
        key="facts",
        task="Backup verification täglich",
        limit=2,
    )

    assert rows[0]["statement"].startswith("Backup verification läuft täglich")
    assert rows[0]["prepare_reason"] == TASK_MATCH_REASON


def test_eval_equal_scores_break_ties_by_created_at_then_id() -> None:
    # Documented expectation of the ordering contract:
    # task_score DESC, created_at DESC, id DESC.
    cur = FakeSimpleFtsCursor(
        {
            "facts": [
                fact_row("141", "Receipts confirm exported memory.", created="2026-06-01"),
                fact_row("143", "Receipts gate writeback claims.", created="2026-06-05"),
                fact_row("142", "Receipts stay reviewable artifacts.", created="2026-06-05"),
            ]
        }
    )

    rows = select_ranked_prepare_rows(
        cur, project_id=PROJECT_ID, key="facts", task="receipts", limit=3
    )

    assert [str(row["id"])[-3:] for row in rows] == ["143", "142", "141"]
    assert len({row["task_score"] for row in rows}) == 1


def test_eval_merge_respects_limit_and_deduplicates_matches() -> None:
    shared = fact_row("151", "Hub View renders reviewed memory.", created="2026-06-08")
    shared_match = dict(shared)
    shared_match["task_score"] = 2.0
    older = fact_row("152", "Backups are verified before writeback.", created="2026-06-02")

    rows = merge_prepare_rows(
        [shared_match],
        [shared, older],
        limit=2,
        primary_reason=TASK_MATCH_REASON,
        fallback_reason=FALLBACK_AFTER_MATCH_REASON,
    )

    assert [str(row["id"])[-3:] for row in rows] == ["151", "152"]
    assert reasons(rows) == [TASK_MATCH_REASON, FALLBACK_AFTER_MATCH_REASON]
    assert rows[0]["task_score"] == 2.0
