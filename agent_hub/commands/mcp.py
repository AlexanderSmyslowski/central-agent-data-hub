"""MCP server command handler."""

from __future__ import annotations

import argparse

from agent_hub.commands.common import error, exception_error, require_database_url
from agent_hub.mcp_server import MissingMCPDependency, run_stdio_server


def run_mcp_serve(_args: argparse.Namespace) -> int:
    if error_code := require_database_url():
        return error_code

    try:
        run_stdio_server()
    except MissingMCPDependency as exc:
        return error(exc, 2)
    except Exception as exc:
        return exception_error(exc)
    return 0
