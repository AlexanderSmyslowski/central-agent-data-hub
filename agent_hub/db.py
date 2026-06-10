"""Database connection helpers."""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

from agent_hub.errors import ConfigurationError


def get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ConfigurationError(
            "DATABASE_URL is required, for example "
            "postgresql://postgres:changeme@localhost:55432/agent_hub"
        )
    return database_url


def connect(*, read_only: bool = False) -> psycopg.Connection:
    """Open a PostgreSQL connection that returns rows as dictionaries."""
    kwargs: dict[str, object] = {"row_factory": dict_row}
    if read_only:
        kwargs["options"] = "-c default_transaction_read_only=on"
    return psycopg.connect(get_database_url(), **kwargs)
