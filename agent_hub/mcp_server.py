"""Read-only MCP server for Agent Data Hub."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from agent_hub.commands.briefs import fetch_brief_payload
from agent_hub.commands.common import concise_error, fetch_project, json_default
from agent_hub.commands.prepare import (
    build_prepare_payload,
    fetch_prepare_payload,
)
from agent_hub.commands.search import fetch_search_payload
from agent_hub.db import connect


class MissingMCPDependency(RuntimeError):
    """Raised when the optional MCP dependency group is not installed."""


class MCPToolFailure(RuntimeError):
    """Clean, user-facing MCP tool failure."""


def json_ready(payload: object) -> object:
    return json.loads(json.dumps(payload, default=json_default, ensure_ascii=False))


def positive_limit(value: int | None, *, default: int, name: str = "limit") -> int:
    if value is None:
        return default
    if value < 1:
        raise MCPToolFailure(f"{name} must be a positive integer")
    return value


def project_or_error(cur, project_slug: str) -> dict[str, object]:
    project = fetch_project(cur, project_slug)
    if not project:
        raise MCPToolFailure(f"project '{project_slug}' not found")
    return project


def list_projects_payload(cur) -> list[dict[str, object]]:
    cur.execute(
        """
        SELECT id, slug, name, status
        FROM projects
        WHERE status = 'active'
        ORDER BY slug
        """
    )
    return list(cur.fetchall())


def prepare_context_pack_payload(
    cur,
    project: str,
    task: str,
    limit: int | None = None,
    stale_after_days: int | None = None,
) -> dict[str, object]:
    resolved_limit = positive_limit(limit, default=8)
    resolved_stale_after_days = positive_limit(
        stale_after_days,
        default=42,
        name="stale_after_days",
    )
    project_row = project_or_error(cur, project)
    compiled = fetch_prepare_payload(cur, project_row, task, resolved_limit)
    return build_prepare_payload(
        project=project_row,
        task=task,
        compiled=compiled,
        stale_after_days=resolved_stale_after_days,
    )


def search_memory_payload(
    cur,
    project: str,
    query: str,
    limit: int | None = None,
) -> dict[str, object]:
    resolved_limit = positive_limit(limit, default=10)
    project_row = project_or_error(cur, project)
    return fetch_search_payload(
        cur,
        project_row,
        query,
        "all",
        resolved_limit,
    )


def project_brief_payload(
    cur,
    project: str,
    limit: int | None = None,
) -> dict[str, object]:
    resolved_limit = positive_limit(limit, default=8)
    project_row = project_or_error(cur, project)
    return fetch_brief_payload(cur, project_row, resolved_limit)


def run_read_only_query(builder: Callable[[Any], object]) -> object:
    with connect(read_only=True) as conn:
        with conn.cursor() as cur:
            return json_ready(builder(cur))


def load_fastmcp():
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.server.fastmcp.exceptions import ToolError
    except ImportError as exc:
        raise MissingMCPDependency(
            "MCP support is optional. Install it with: pip install -e '.[mcp]'"
        ) from exc
    return FastMCP, ToolError


def create_mcp_server():
    FastMCP, ToolError = load_fastmcp()
    server = FastMCP(
        "Agent Data Hub",
        instructions=(
            "Read-only access to reviewed Agent Data Hub context. "
            "This server exposes no write tools."
        ),
        log_level="ERROR",
    )

    def tool_result(builder: Callable[[Any], object]) -> object:
        try:
            return run_read_only_query(builder)
        except MCPToolFailure as exc:
            raise ToolError(str(exc)) from None
        except Exception as exc:
            raise ToolError(concise_error(exc)) from None

    @server.tool(
        description="List active Agent Data Hub projects with id, slug, name, and status.",
        structured_output=True,
    )
    def list_projects() -> list[dict[str, object]]:
        return tool_result(list_projects_payload)

    @server.tool(
        description="Build the same read-only JSON context pack as agent-hub prepare.",
        structured_output=True,
    )
    def prepare_context_pack(
        project: str,
        task: str,
        limit: int | None = None,
        stale_after_days: int | None = None,
    ) -> dict[str, object]:
        return tool_result(
            lambda cur: prepare_context_pack_payload(
                cur,
                project,
                task,
                limit,
                stale_after_days,
            )
        )

    @server.tool(
        description="Search reviewed project memory using the same shape as agent-hub search JSON.",
        structured_output=True,
    )
    def search_memory(
        project: str,
        query: str,
        limit: int | None = None,
    ) -> dict[str, object]:
        return tool_result(lambda cur: search_memory_payload(cur, project, query, limit))

    @server.tool(
        description="Return the compact project brief JSON used by agent-hub brief.",
        structured_output=True,
    )
    def project_brief(
        project: str,
        limit: int | None = None,
    ) -> dict[str, object]:
        return tool_result(lambda cur: project_brief_payload(cur, project, limit))

    return server


def run_stdio_server() -> None:
    create_mcp_server().run(transport="stdio")
