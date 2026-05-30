"""Export table specifications."""

from __future__ import annotations

TYPE_BY_TABLE = {
    "projects": "project",
    "documents": "document",
    "reports": "report",
    "decisions": "decision",
    "facts": "fact",
    "open_questions": "open_question",
    "risks": "risk",
    "agent_actions": "agent_action",
}

EXPORTS = [
    {
        "table": "projects",
        "template": "project.md.j2",
        "folder": "Projects",
        "title_fields": ("slug", "name"),
        "query": """
            SELECT id, name, slug, description, status, metadata, created_at, updated_at
            FROM projects
            ORDER BY slug
        """,
    },
    {
        "table": "documents",
        "template": "document.md.j2",
        "folder": "Documents",
        "title_fields": ("slug", "title"),
        "query": """
            SELECT id, project_id, title, slug, path, content, frontmatter,
                   content_hash, status, metadata, created_at, updated_at
            FROM documents
            ORDER BY slug
        """,
    },
    {
        "table": "reports",
        "template": "report.md.j2",
        "folder": "Reports",
        "title_fields": ("title",),
        "query": """
            SELECT id, project_id, title, report_type, summary, body, status,
                   metadata, created_at, updated_at
            FROM reports
            ORDER BY title, id
        """,
    },
    {
        "table": "decisions",
        "template": "decision.md.j2",
        "folder": "Decisions",
        "title_fields": ("decision",),
        "query": """
            SELECT id, project_id, decision, rationale, consequences, status,
                   metadata, created_at, updated_at
            FROM decisions
            ORDER BY created_at, id
        """,
    },
    {
        "table": "facts",
        "template": "fact.md.j2",
        "folder": "Facts",
        "title_fields": ("statement",),
        "query": """
            SELECT id, project_id, statement, source, confidence, status,
                   metadata, created_at, updated_at
            FROM facts
            ORDER BY created_at, id
        """,
    },
    {
        "table": "open_questions",
        "template": "open_question.md.j2",
        "folder": "Open Questions",
        "title_fields": ("question",),
        "query": """
            SELECT id, project_id, question, answer, status, resolved_at,
                   metadata, created_at, updated_at
            FROM open_questions
            ORDER BY created_at, id
        """,
    },
    {
        "table": "risks",
        "template": "risk.md.j2",
        "folder": "Risks",
        "title_fields": ("title",),
        "query": """
            SELECT id, project_id, title, severity, impact, mitigation, status,
                   metadata, created_at, updated_at
            FROM risks
            ORDER BY severity, title, id
        """,
    },
    {
        "table": "agent_actions",
        "template": "agent_action.md.j2",
        "folder": "Agent Actions",
        "title_fields": ("action",),
        "query": """
            SELECT id, agent_id, action, object_type, object_id, input, output,
                   status, error, metadata, created_at, updated_at
            FROM agent_actions
            ORDER BY created_at, id
        """,
    },
]
