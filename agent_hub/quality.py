"""Health and memory-quality queries for Agent Data Hub."""

from __future__ import annotations

from agent_hub.relations import (
    RELATION_TARGETS,
    RELATION_TYPES,
    fetch_project_relations,
)

CORE_TABLES = (
    "projects",
    "documents",
    "reports",
    "decisions",
    "facts",
    "open_questions",
    "risks",
    "agent_actions",
    "sync_events",
)

PROJECT_SCOPED_TABLES = (
    "documents",
    "reports",
    "decisions",
    "facts",
    "open_questions",
    "risks",
    "agent_actions",
)


def fetch_table_counts(cur) -> dict[str, int]:
    counts = {}
    for table in CORE_TABLES:
        cur.execute(f"SELECT count(*) AS count FROM {table}")
        row = cur.fetchone()
        counts[table] = row["count"]
    return counts


def table_has_column(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema = 'public'
            AND table_name = %s
            AND column_name = %s
        ) AS exists
        """,
        (table, column),
    )
    return cur.fetchone()["exists"]


def find_missing_project_references(cur) -> list[tuple[str, int]]:
    missing = []
    for table in PROJECT_SCOPED_TABLES:
        if not table_has_column(cur, table, "project_id"):
            continue
        cur.execute(f"SELECT count(*) AS count FROM {table} WHERE project_id IS NULL")
        count = cur.fetchone()["count"]
        if count:
            missing.append((table, count))
    return missing


def find_broken_relation_side(cur, side: str) -> list[dict[str, object]]:
    broken = []
    type_column = f"{side}_type"
    id_column = f"{side}_id"
    for object_type, table in RELATION_TARGETS.items():
        cur.execute(
            f"""
            SELECT r.id, r.relation_type, r.{type_column}, r.{id_column}
            FROM relations r
            LEFT JOIN {table} target ON target.id = r.{id_column}
            WHERE r.{type_column} = %s
              AND target.id IS NULL
            ORDER BY r.created_at, r.id
            """,
            (object_type,),
        )
        for row in cur.fetchall():
            broken.append(
                {
                    "relation_id": row["id"],
                    "relation_type": row["relation_type"],
                    "side": side,
                    "object_type": row[type_column],
                    "object_id": row[id_column],
                }
            )
    return broken


def find_unknown_relation_types(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, relation_type, source_type, source_id, target_type, target_id
        FROM relations
        WHERE relation_type <> ALL(%s)
        ORDER BY created_at, id
        """,
        (list(RELATION_TYPES),),
    )
    return list(cur.fetchall())


def fetch_low_confidence_facts(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, statement, confidence, status
        FROM facts
        WHERE confidence < 0.6
          AND status <> 'draft'
        ORDER BY confidence, created_at, id
        """
    )
    return list(cur.fetchall())


def fetch_open_questions(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, question, status
        FROM open_questions
        WHERE status NOT IN ('draft', 'answered', 'closed', 'resolved', 'archived')
        ORDER BY created_at, id
        """
    )
    return list(cur.fetchall())


def fetch_memory_quality_warnings(cur) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []

    cur.execute(
        """
        SELECT id, 'fact' AS type, statement AS title,
               'missing source' AS issue
        FROM facts
        WHERE status NOT IN ('draft', 'archived')
          AND NULLIF(BTRIM(COALESCE(source, '')), '') IS NULL
        ORDER BY updated_at DESC, created_at DESC, id
        """
    )
    warnings.extend(cur.fetchall())

    cur.execute(
        """
        SELECT id, 'decision' AS type, decision AS title,
               'missing rationale' AS issue
        FROM decisions
        WHERE status NOT IN ('draft', 'archived')
          AND NULLIF(BTRIM(COALESCE(rationale, '')), '') IS NULL
        ORDER BY updated_at DESC, created_at DESC, id
        """
    )
    warnings.extend(cur.fetchall())

    cur.execute(
        """
        SELECT id, 'risk' AS type, title,
               'missing impact or mitigation' AS issue
        FROM risks
        WHERE status NOT IN ('draft', 'resolved', 'archived')
          AND (
            NULLIF(BTRIM(COALESCE(impact, '')), '') IS NULL
            OR NULLIF(BTRIM(COALESCE(mitigation, '')), '') IS NULL
          )
        ORDER BY updated_at DESC, created_at DESC, id
        """
    )
    warnings.extend(cur.fetchall())

    cur.execute(
        """
        SELECT id, 'report' AS type, title,
               'missing summary' AS issue
        FROM reports
        WHERE status NOT IN ('draft', 'archived')
          AND NULLIF(BTRIM(COALESCE(summary, '')), '') IS NULL
        ORDER BY updated_at DESC, created_at DESC, id
        """
    )
    warnings.extend(cur.fetchall())

    cur.execute(
        """
        SELECT id, 'open_question' AS type, question AS title,
               'answered or closed without answer' AS issue
        FROM open_questions
        WHERE status IN ('answered', 'closed')
          AND NULLIF(BTRIM(COALESCE(answer, '')), '') IS NULL
        ORDER BY updated_at DESC, created_at DESC, id
        """
    )
    warnings.extend(cur.fetchall())

    long_text_checks = (
        ("fact", "facts", "statement", "statement"),
        ("decision", "decisions", "decision", "decision"),
        ("risk", "risks", "title", "title"),
        ("open_question", "open_questions", "question", "question"),
        ("report", "reports", "title", "title"),
    )
    for memory_type, table, text_column, title_column in long_text_checks:
        cur.execute(
            f"""
            SELECT id, %s AS type, {title_column} AS title,
                   'very long memory entry; consider distilling' AS issue
            FROM {table}
            WHERE status NOT IN ('draft', 'archived')
              AND length(COALESCE({text_column}, '')) > 1200
            ORDER BY updated_at DESC, created_at DESC, id
            LIMIT 20
            """,
            (memory_type,),
        )
        warnings.extend(cur.fetchall())

    cur.execute(
        """
        SELECT id, 'fact' AS type, statement AS title,
               'possible duplicate fact' AS issue
        FROM facts
        WHERE status NOT IN ('draft', 'archived')
          AND lower(BTRIM(statement)) IN (
            SELECT lower(BTRIM(statement))
            FROM facts
            WHERE status NOT IN ('draft', 'archived')
            GROUP BY lower(BTRIM(statement))
            HAVING count(*) > 1
          )
        ORDER BY updated_at DESC, created_at DESC, id
        LIMIT 20
        """
    )
    warnings.extend(cur.fetchall())

    cur.execute(
        """
        SELECT oq.id, 'open_question' AS type, oq.question AS title,
               'possibly answered by a decision' AS issue
        FROM open_questions oq
        WHERE oq.status NOT IN ('draft', 'answered', 'closed', 'resolved', 'archived')
          AND EXISTS (
            SELECT 1
            FROM relations r
            WHERE r.relation_type = 'answers'
              AND (
                (r.source_type = 'decision'
                 AND r.target_type = 'open_question'
                 AND r.target_id = oq.id)
                OR
                (r.target_type = 'decision'
                 AND r.source_type = 'open_question'
                 AND r.source_id = oq.id)
              )
          )
        ORDER BY oq.updated_at DESC, oq.created_at DESC, oq.id
        LIMIT 20
        """
    )
    warnings.extend(cur.fetchall())

    return warnings


def fetch_latest_sync_event(cur) -> dict[str, object] | None:
    cur.execute(
        """
        SELECT id, source, direction, status, created_at, updated_at
        FROM sync_events
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """
    )
    return cur.fetchone()


def fetch_project_counts(cur, project_id: object) -> dict[str, int]:
    cur.execute(
        """
        SELECT
          (SELECT count(*) FROM documents WHERE project_id = %(project_id)s) AS documents,
          (
            SELECT count(*)
            FROM facts
            WHERE project_id = %(project_id)s
              AND status NOT IN ('draft', 'archived')
          ) AS facts,
          (
            SELECT count(*)
            FROM decisions
            WHERE project_id = %(project_id)s
              AND status NOT IN ('draft', 'archived')
          ) AS decisions,
          (
            SELECT count(*)
            FROM open_questions
            WHERE project_id = %(project_id)s
              AND status NOT IN (
                'draft', 'answered', 'closed', 'resolved', 'archived'
              )
          ) AS open_questions,
          (
            SELECT count(*)
            FROM risks
            WHERE project_id = %(project_id)s
              AND status NOT IN ('draft', 'resolved', 'archived')
          ) AS risks,
          (
            SELECT count(*)
            FROM reports
            WHERE project_id = %(project_id)s
              AND status NOT IN ('draft', 'archived')
          ) AS reports
        """,
        {"project_id": project_id},
    )
    return dict(cur.fetchone())


def fetch_project_quality(cur, project: dict[str, object]) -> dict[str, object]:
    project_id = project["id"]
    cur.execute(
        """
        SELECT id, 'fact' AS type, statement AS title, 'missing source' AS issue
        FROM facts
        WHERE project_id = %s
          AND status NOT IN ('draft', 'archived')
          AND NULLIF(BTRIM(COALESCE(source, '')), '') IS NULL
        ORDER BY updated_at DESC, created_at DESC, id
        """,
        (project_id,),
    )
    facts_without_source = list(cur.fetchall())

    cur.execute(
        """
        SELECT id, 'decision' AS type, decision AS title, 'missing rationale' AS issue
        FROM decisions
        WHERE project_id = %s
          AND status NOT IN ('draft', 'archived')
          AND NULLIF(BTRIM(COALESCE(rationale, '')), '') IS NULL
        ORDER BY updated_at DESC, created_at DESC, id
        """,
        (project_id,),
    )
    decisions_without_rationale = list(cur.fetchall())

    cur.execute(
        """
        SELECT id, 'risk' AS type, title, 'missing impact or mitigation' AS issue
        FROM risks
        WHERE project_id = %s
          AND status NOT IN ('draft', 'resolved', 'archived')
          AND (
            NULLIF(BTRIM(COALESCE(impact, '')), '') IS NULL
            OR NULLIF(BTRIM(COALESCE(mitigation, '')), '') IS NULL
          )
        ORDER BY updated_at DESC, created_at DESC, id
        """,
        (project_id,),
    )
    risks_without_mitigation = list(cur.fetchall())

    cur.execute(
        """
        SELECT id, question, status, updated_at
        FROM open_questions
        WHERE project_id = %s
          AND status NOT IN ('draft', 'answered', 'closed', 'archived')
        ORDER BY updated_at DESC, created_at DESC, id
        """,
        (project_id,),
    )
    open_questions = list(cur.fetchall())

    cur.execute(
        """
        SELECT id, question, status, updated_at, metadata->>'suggestion' AS suggestion
        FROM open_questions
        WHERE project_id = %s
          AND status NOT IN ('draft', 'answered', 'closed', 'resolved', 'archived')
          AND metadata->>'schema_friction' = 'true'
        ORDER BY updated_at DESC, created_at DESC, id
        """,
        (project_id,),
    )
    schema_friction_questions = list(cur.fetchall())

    relations = fetch_project_relations(cur, project_id, limit=None)
    counts = fetch_project_counts(cur, project_id)
    memory_total = sum(
        counts[key]
        for key in ("facts", "decisions", "risks", "open_questions", "reports")
    )
    quality_items = (
        facts_without_source
        + decisions_without_rationale
        + risks_without_mitigation
    )
    relation_coverage = (
        0.0 if memory_total == 0 else min(1.0, len(relations) / memory_total)
    )
    score = 100
    score -= min(40, len(quality_items) * 8)
    score -= min(25, len(open_questions) * 4)
    if memory_total >= 3 and not relations:
        score -= 20
    elif relation_coverage < 0.2 and memory_total >= 5:
        score -= 10
    score = max(0, score)

    return {
        "project": project,
        "counts": counts,
        "score": score,
        "status": (
            "healthy" if score >= 85 else "needs_review" if score >= 65 else "weak"
        ),
        "facts_without_source": facts_without_source,
        "decisions_without_rationale": decisions_without_rationale,
        "risks_without_mitigation": risks_without_mitigation,
        "open_questions": open_questions,
        "schema_friction_questions": schema_friction_questions,
        "relations": relations,
        "relation_count": len(relations),
        "relation_coverage": relation_coverage,
    }
