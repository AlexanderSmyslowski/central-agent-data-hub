"""Schema migration helpers for Agent Data Hub."""

from __future__ import annotations

import hashlib
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BASELINE_MIGRATION_ID = "001"
TRACKING_MIGRATION_ID = "002"


def _concise_error(exc: Exception) -> str:
    return str(exc).splitlines()[0]


def migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def migration_parts(path: Path) -> tuple[str, str]:
    migration_id, separator, name = path.stem.partition("_")
    if not separator or not migration_id:
        return path.stem, path.stem
    return migration_id, name


def migration_checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT to_regclass(%s) IS NOT NULL AS exists",
        (f"public.{table_name}",),
    )
    row = cur.fetchone()
    return bool(row and row["exists"])


def base_schema_exists(cur) -> bool:
    return table_exists(cur, "projects")


def schema_migrations_exists(cur) -> bool:
    return table_exists(cur, "schema_migrations")


def migration_records(cur) -> dict[str, dict[str, object]]:
    if not schema_migrations_exists(cur):
        return {}
    cur.execute(
        """
        SELECT migration_id, name, checksum, status, applied_at, error
        FROM schema_migrations
        ORDER BY migration_id
        """
    )
    return {row["migration_id"]: row for row in cur.fetchall()}


def record_migration(
    cur,
    migration_id: str,
    name: str,
    checksum: str,
    status: str,
    error: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO schema_migrations (
          migration_id, name, checksum, status, applied_at, error
        )
        VALUES (%s, %s, %s, %s, now(), %s)
        ON CONFLICT (migration_id) DO UPDATE SET
          name = EXCLUDED.name,
          checksum = EXCLUDED.checksum,
          status = EXCLUDED.status,
          applied_at = EXCLUDED.applied_at,
          error = EXCLUDED.error
        """,
        (migration_id, name, checksum, status, error),
    )


def execute_migration_file(conn, path: Path) -> None:
    conn.commit()
    previous_autocommit = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = previous_autocommit


def migration_file_by_id(migration_id: str) -> Path | None:
    for path in migration_files():
        if migration_parts(path)[0] == migration_id:
            return path
    return None


def describe_migrations(conn) -> dict[str, object]:
    files = migration_files()
    with conn.cursor() as cur:
        tracking_exists = schema_migrations_exists(cur)
        base_exists = base_schema_exists(cur)
        records = migration_records(cur) if tracking_exists else {}

    migrations: list[dict[str, object]] = []
    for path in files:
        migration_id, name = migration_parts(path)
        checksum = migration_checksum(path)
        record = records.get(migration_id)
        status = "pending"
        applied_at = None
        error = None

        if record:
            status = str(record["status"])
            applied_at = record["applied_at"]
            error = record["error"]
            if record["checksum"] != checksum and status == "applied":
                status = "changed"
                error = "Migration file checksum differs from applied record."
        elif migration_id == BASELINE_MIGRATION_ID and base_exists:
            status = "applied-untracked"

        migrations.append(
            {
                "migration_id": migration_id,
                "name": name,
                "checksum": checksum,
                "status": status,
                "applied_at": applied_at,
                "error": error,
                "path": str(path),
            }
        )

    applied = [
        item
        for item in migrations
        if item["status"] in ("applied", "applied-untracked")
    ]
    open_items = [
        item
        for item in migrations
        if item["status"] in ("pending", "failed", "changed")
    ]
    failed_items = [
        item
        for item in migrations
        if item["status"] in ("failed", "changed")
    ]
    latest = applied[-1] if applied else None
    return {
        "tracking": "installed" if tracking_exists else "missing",
        "base_schema": base_exists,
        "current_version": latest["migration_id"] if latest else None,
        "open_count": len(open_items),
        "failed_count": len(failed_items),
        "latest": latest,
        "migrations": migrations,
    }


def print_migration_report(report: dict[str, object]) -> None:
    print("Schema migrations:")
    print(f"  Tracking: {report['tracking']}")
    current_version = report["current_version"] or "none"
    print(f"  Current version: {current_version}")
    print(f"  Open migrations: {report['open_count']}")
    latest = report["latest"]
    if latest:
        print(
            "  Last migration status: "
            f"{latest['status']} "
            f"({latest['migration_id']} {latest['name']})"
        )
    else:
        print("  Last migration status: none")
    print("  Migrations:")
    for item in report["migrations"]:
        print(f"    - {item['migration_id']} {item['name']}: {item['status']}")
        if item["error"]:
            print(f"      error: {item['error']}")


def apply_migrations(conn) -> tuple[list[str], list[str]]:
    files = migration_files()
    if not files:
        return [], [f"No migration files found in {MIGRATIONS_DIR}"]

    applied: list[str] = []
    errors: list[str] = []

    with conn.cursor() as cur:
        tracking_exists = schema_migrations_exists(cur)
        base_exists = base_schema_exists(cur)

    baseline_path = migration_file_by_id(BASELINE_MIGRATION_ID)
    tracking_path = migration_file_by_id(TRACKING_MIGRATION_ID)

    if not tracking_exists:
        if not tracking_path:
            return applied, [
                f"Tracking migration {TRACKING_MIGRATION_ID} is missing."
            ]

        if base_exists:
            try:
                execute_migration_file(conn, tracking_path)
            except Exception as exc:
                return applied, [
                    f"{TRACKING_MIGRATION_ID} failed: {_concise_error(exc)}"
                ]
            with conn.cursor() as cur:
                if baseline_path:
                    baseline_id, baseline_name = migration_parts(baseline_path)
                    record_migration(
                        cur,
                        baseline_id,
                        baseline_name,
                        migration_checksum(baseline_path),
                        "applied",
                    )
                tracking_id, tracking_name = migration_parts(tracking_path)
                record_migration(
                    cur,
                    tracking_id,
                    tracking_name,
                    migration_checksum(tracking_path),
                    "applied",
                )
            conn.commit()
            applied.append(
                f"{TRACKING_MIGRATION_ID} schema_migrations "
                "(bootstrapped existing schema)"
            )
        else:
            if not baseline_path:
                return applied, [
                    f"Baseline migration {BASELINE_MIGRATION_ID} is missing."
                ]
            try:
                execute_migration_file(conn, baseline_path)
                execute_migration_file(conn, tracking_path)
            except Exception as exc:
                return applied, [f"Migration failed: {_concise_error(exc)}"]
            with conn.cursor() as cur:
                for path in (baseline_path, tracking_path):
                    migration_id, name = migration_parts(path)
                    record_migration(
                        cur,
                        migration_id,
                        name,
                        migration_checksum(path),
                        "applied",
                    )
                    applied.append(f"{migration_id} {name}")
            conn.commit()

    with conn.cursor() as cur:
        records = migration_records(cur)
        base_exists = base_schema_exists(cur)
        if base_exists and baseline_path and BASELINE_MIGRATION_ID not in records:
            baseline_id, baseline_name = migration_parts(baseline_path)
            record_migration(
                cur,
                baseline_id,
                baseline_name,
                migration_checksum(baseline_path),
                "applied",
            )
            applied.append(f"{baseline_id} {baseline_name} (registered)")
        conn.commit()

    for path in files:
        migration_id, name = migration_parts(path)
        checksum = migration_checksum(path)
        with conn.cursor() as cur:
            records = migration_records(cur)
            record = records.get(migration_id)
        if record and record["status"] == "applied":
            if record["checksum"] != checksum:
                errors.append(
                    f"{migration_id} {name} checksum changed after apply"
                )
                break
            continue

        try:
            execute_migration_file(conn, path)
        except Exception as exc:
            message = _concise_error(exc)
            with conn.cursor() as cur:
                if schema_migrations_exists(cur):
                    record_migration(
                        cur,
                        migration_id,
                        name,
                        checksum,
                        "failed",
                        message,
                    )
            conn.commit()
            errors.append(f"{migration_id} {name} failed: {message}")
            break

        with conn.cursor() as cur:
            record_migration(cur, migration_id, name, checksum, "applied")
        conn.commit()
        applied.append(f"{migration_id} {name}")

    return applied, errors
