#!/usr/bin/env python3
"""Run PostgreSQL clients with DATABASE_URL translated into libpq environment."""

from __future__ import annotations

import os
import sys
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit


SUPPORTED_CLIENTS = {"pg_dump", "pg_isready", "pg_restore", "psql"}
QUERY_ENV = {
    "application_name": "PGAPPNAME",
    "channel_binding": "PGCHANNELBINDING",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "gssencmode": "PGGSSENCMODE",
    "options": "PGOPTIONS",
    "sslcert": "PGSSLCERT",
    "sslcrl": "PGSSLCRL",
    "sslkey": "PGSSLKEY",
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
}
LIBPQ_CONNECTION_ENV = frozenset(QUERY_ENV.values()) | {
    "PGDATABASE",
    "PGHOST",
    "PGHOSTADDR",
    "PGPASSFILE",
    "PGPASSWORD",
    "PGPORT",
    "PGREQUIREPEER",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSSLCOMPRESSION",
    "PGSSLCRLDIR",
    "PGSSLSNI",
    "PGUSER",
}


def libpq_environment(database_url: str) -> dict[str, str]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("unsupported database URL scheme")
    if not parsed.hostname or not parsed.username or not parsed.path.lstrip("/"):
        raise ValueError("database URL is missing a required component")

    environment = os.environ.copy()
    for name in LIBPQ_CONNECTION_ENV:
        environment.pop(name, None)
    environment["PGHOST"] = unquote(parsed.hostname)
    environment["PGPORT"] = str(parsed.port or 5432)
    environment["PGUSER"] = unquote(parsed.username)
    environment["PGDATABASE"] = unquote(parsed.path.lstrip("/"))

    if parsed.password is None:
        environment.pop("PGPASSWORD", None)
    else:
        environment["PGPASSWORD"] = unquote(parsed.password)

    query = parse_qs(parsed.query, keep_blank_values=True)
    for query_name, environment_name in QUERY_ENV.items():
        values = query.get(query_name)
        if values:
            environment[environment_name] = values[-1]

    return environment


def database_url_for_name(database_url: str, database_name: str) -> str:
    parsed = urlsplit(database_url)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or not parsed.username
        or not database_name
    ):
        raise ValueError("invalid database URL or name")
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"/{quote(database_name, safe='')}",
            parsed.query,
            "",
        )
    )


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "database-url":
        if len(sys.argv) != 3:
            print("db client error: database-url requires one database name", file=sys.stderr)
            return 2
        try:
            print(database_url_for_name(os.environ.get("DATABASE_URL", ""), sys.argv[2]))
        except (TypeError, ValueError):
            print("db client error: DATABASE_URL is invalid", file=sys.stderr)
            return 2
        return 0

    if len(sys.argv) < 2:
        print("db client error: unsupported or missing PostgreSQL client", file=sys.stderr)
        return 2
    client_path = sys.argv[1]
    client = os.path.basename(client_path)
    if client not in SUPPORTED_CLIENTS:
        print("db client error: unsupported or missing PostgreSQL client", file=sys.stderr)
        return 2

    database_url = os.environ.get("DATABASE_URL", "")
    try:
        environment = libpq_environment(database_url)
    except (TypeError, ValueError):
        # The URL can contain a password, so configuration failures stay generic.
        print("db client error: DATABASE_URL is invalid", file=sys.stderr)
        return 2

    try:
        os.execvpe(client_path, [client, *sys.argv[2:]], environment)
    except OSError:
        print(f"db client error: {client} is unavailable", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
