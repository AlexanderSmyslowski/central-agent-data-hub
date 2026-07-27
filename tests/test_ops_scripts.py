import hashlib
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_script(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def native_script_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "backups").mkdir()
    command_log = tmp_path / "commands.log"
    fake_python = bin_dir / "python"
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
for argument in "$@"; do
  if [[ "$argument" == *native-secret* ]]; then
    exit 97
  fi
done
if [[ "${1:-}" == *scripts/db_client.py ]]; then
  exec "$REAL_PYTHON" "$@"
fi
if [[ "${1:-}" == "-c" && "${2:-}" == *"psycopg.connect"* ]]; then
  exit 0
fi
if [[ "${1:-}" == "-c" ]]; then
  exec "$REAL_PYTHON" "$@"
fi
if [[ "${1:-}" == "-" ]]; then
  exec "$REAL_PYTHON" "$@"
fi
printf 'python %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
case " $* " in
  *" agent_hub.cli migrate --status "*)
    echo "001_init.sql: applied"
    ;;
  *" agent_hub.cli projects --format json "*)
    echo '[{"slug": "central-agent-data-hub"}]'
    ;;
  *)
    echo "ok"
    ;;
esac
""",
    )
    for command, body in {
        "docker": """printf 'docker %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
exit 91
""",
        "pg_dump": """printf 'pg_dump %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
printf 'native-dump\n'
""",
        "psql": """printf 'psql %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
payload="$(cat)"
if [[ -n "$payload" ]]; then
  printf 'psql-stdin %s\n' "$payload" >> "$FAKE_RUNTIME_LOG"
fi
""",
        "pg_restore": """printf 'pg_restore %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
if [[ " $* " == *" --file=- "* ]]; then
  cat >/dev/null
  printf 'SELECT 1;\n'
  exit 0
fi
if [[ " $* " != *" --dbname=agent_hub_verify_"* ]]; then exit 97; fi
dump_path="${!#}"
if [[ ! -f "$dump_path" ]]; then exit 97; fi
""",
    }.items():
        write_executable(
            bin_dir / command,
            f"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$PGHOST" != "localhost" ]]; then exit 97; fi
if [[ "$PGPORT" != "55432" ]]; then exit 97; fi
if [[ "$PGUSER" != "native" ]]; then exit 97; fi
if [[ "$PGPASSWORD" != "native-secret" ]]; then exit 97; fi
if [[ "$PGDATABASE" != "agent_hub" ]]; then exit 97; fi
{body}""",
        )

    env = os.environ.copy()
    env.pop("AGENT_HUB_BACKUP_REMOTE", None)
    env.pop("AGENT_HUB_NATIVE_POSTGRES_SERVICE", None)
    env.pop("AGENT_HUB_PUBLIC_DEMO", None)
    env.update(
        {
            "AGENT_HUB_IGNORE_ENV_FILE": "1",
            "AGENT_HUB_BACKUP_DIR": str(tmp_path / "backups"),
            "DATABASE_URL": "postgresql://native:native-secret@localhost:55432/agent_hub",
            "FAKE_RUNTIME_LOG": str(command_log),
            "OBSIDIAN_EXPORT_DIR": str(tmp_path / "obsidian"),
            "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHON": str(fake_python),
            "REAL_PYTHON": sys.executable,
        }
    )
    return env, command_log


def create_valid_backup(backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    dump_path = backup_dir / "agent_hub-20260727-120000.dump"
    payload = b"native-backup"
    dump_path.write_bytes(payload)
    checksum = hashlib.sha256(payload).hexdigest()
    dump_path.with_suffix(".dump.sha256").write_text(
        f"{checksum}  {dump_path}\n",
        encoding="utf-8",
    )
    return dump_path


def test_db_common_applies_native_service_loaded_from_repo_env(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/db_common.sh", scripts / "db_common.sh")
    (repo / ".env").write_text(
        "AGENT_HUB_NATIVE_POSTGRES_SERVICE=postgresql@16\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("AGENT_HUB_NATIVE_POSTGRES_SERVICE", None)
    env.pop("AGENT_HUB_IGNORE_ENV_FILE", None)

    result = subprocess.run(
        [
            "bash",
            "-c",
            'source scripts/db_common.sh; printf "%s\\n" "$NATIVE_POSTGRES_SERVICE"',
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "postgresql@16\n"


def test_public_env_template_keeps_native_service_opt_in() -> None:
    env_example = read_script(".env.example")

    assert "\nAGENT_HUB_NATIVE_POSTGRES_SERVICE=" not in env_example
    assert "# AGENT_HUB_NATIVE_POSTGRES_SERVICE=postgresql@16" in env_example


def test_db_client_maps_database_url_to_libpq_environment_without_secret_arguments(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_psql = bin_dir / "psql"
    write_executable(
        fake_psql,
        """#!/usr/bin/env bash
set -euo pipefail
for argument in "$@"; do
  if [[ "$argument" == *"p@ss:word"* ]]; then exit 97; fi
done
if [[ "$PGHOST" != "127.0.0.1" ]]; then exit 97; fi
if [[ "$PGPORT" != "65432" ]]; then exit 97; fi
if [[ "$PGUSER" != "native user" ]]; then exit 97; fi
if [[ "$PGPASSWORD" != "p@ss:word" ]]; then exit 97; fi
if [[ "$PGDATABASE" != "agent_hub" ]]; then exit 97; fi
if [[ "$PGSSLMODE" != "disable" ]]; then exit 97; fi
if [[ "$PGAPPNAME" != "hub-test" ]]; then exit 97; fi
if [[ -n "${PGSERVICE:-}" ]]; then exit 97; fi
if [[ -n "${PGSERVICEFILE:-}" ]]; then exit 97; fi
if [[ -n "${PGHOSTADDR:-}" ]]; then exit 97; fi
if [[ -n "${PGPASSFILE:-}" ]]; then exit 97; fi
printf 'safe-client-ok\n'
""",
    )
    env = os.environ.copy()
    env.pop("AGENT_HUB_NATIVE_POSTGRES_SERVICE", None)
    env.update(
        {
            "DATABASE_URL": (
                "postgresql://native%20user:p%40ss%3Aword@127.0.0.1:65432/"
                "agent_hub?sslmode=disable&application_name=hub-test"
            ),
            "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/sbin:/sbin",
            "PGHOSTADDR": "203.0.113.9",
            "PGPASSFILE": "/tmp/stale-pgpass",
            "PGSERVICE": "stale-service",
            "PGSERVICEFILE": "/tmp/stale-service.conf",
        }
    )
    result = subprocess.run(
        [sys.executable, "scripts/db_client.py", "psql", "--probe"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "safe-client-ok\n"
    assert "p@ss:word" not in result.stdout
    assert "p@ss:word" not in result.stderr


def test_db_client_builds_verification_url_without_putting_secret_in_arguments(
    tmp_path: Path,
) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = (
        "postgresql://native%20user:p%40ss%3Aword@127.0.0.1:65432/"
        "agent_hub?sslmode=disable"
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/db_client.py",
            "database-url",
            "agent_hub_verify_123",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "postgresql://native%20user:p%40ss%3Aword@127.0.0.1:65432/"
        "agent_hub_verify_123?sslmode=disable"
    )
    assert "p@ss:word" not in " ".join(result.args)


def test_direct_database_readiness_uses_database_url_without_exposing_password(
    tmp_path: Path,
) -> None:
    fake_python = tmp_path / "python"
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
for argument in "$@"; do
  if [[ "$argument" == *native-secret* ]]; then exit 97; fi
done
if [[ "${1:-}" != "-c" ]]; then exit 97; fi
if [[ "${DATABASE_URL:-}" != "postgresql://native:native-secret@localhost:55432/agent_hub" ]]; then
  exit 97
fi
exit 0
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "AGENT_HUB_IGNORE_ENV_FILE": "1",
            "DATABASE_URL": "postgresql://native:native-secret@localhost:55432/agent_hub",
            "PYTHON": str(fake_python),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-lc",
            """
set -euo pipefail
source scripts/db_common.sh
direct_database_ready
printf 'URL: %s\n' "$(mask_database_url "$DATABASE_URL")"
""",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "URL: postgresql://native:***@localhost:55432/agent_hub" in result.stdout
    assert "native-secret" not in result.stdout
    assert "native-secret" not in result.stderr


def test_direct_database_readiness_propagates_connection_failure(tmp_path: Path) -> None:
    fake_python = tmp_path / "python"
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" != "-c" ]]; then exit 97; fi
exit 1
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "AGENT_HUB_IGNORE_ENV_FILE": "1",
            "DATABASE_URL": "postgresql://native:native-secret@localhost:55999/agent_hub",
            "PYTHON": str(fake_python),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
set -euo pipefail
source scripts/db_common.sh
if direct_database_ready; then
  exit 97
fi
""",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_configured_native_service_pins_runtime_when_database_is_unreachable(
    tmp_path: Path,
) -> None:
    fake_python = tmp_path / "python"
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
exit 1
""",
    )
    env = os.environ.copy()
    env.update(
        {
            "AGENT_HUB_IGNORE_ENV_FILE": "1",
            "AGENT_HUB_NATIVE_POSTGRES_SERVICE": "postgresql@16",
            "DATABASE_URL": "postgresql://native:native-secret@localhost:55432/agent_hub",
            "PYTHON": str(fake_python),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
set -euo pipefail
source scripts/db_common.sh
select_database_runtime
database_runtime_label
""",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "direct (DATABASE_URL)\n"


def test_db_start_uses_reachable_direct_database_without_docker(tmp_path: Path) -> None:
    env, command_log = native_script_env(tmp_path)
    result = subprocess.run(
        ["bash", "scripts/db_start.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database runtime: direct (DATABASE_URL)" in result.stdout
    assert "native-secret" not in result.stdout
    assert "native-secret" not in result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "agent_hub.cli migrate --apply" in commands
    assert "docker " not in commands


def test_db_start_starts_configured_homebrew_service_before_docker(tmp_path: Path) -> None:
    env, command_log = native_script_env(tmp_path)
    ready_marker = tmp_path / "native-ready"
    fake_python = Path(env["PYTHON"])
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
for argument in "$@"; do
  if [[ "$argument" == *native-secret* ]]; then exit 97; fi
done
if [[ "${1:-}" == *scripts/db_client.py ]]; then
  exec "$REAL_PYTHON" "$@"
fi
if [[ "${1:-}" == "-c" ]]; then
  if [[ -f "$FAKE_NATIVE_READY_MARKER" ]]; then exit 0; fi
  exit 1
fi
printf 'python %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
case " $* " in
  *" agent_hub.cli migrate --status "*)
    echo "001_init.sql: applied"
    ;;
  *" agent_hub.cli projects --format json "*)
    echo '[{"slug": "central-agent-data-hub"}]'
    ;;
  *)
    echo "ok"
    ;;
esac
""",
    )
    write_executable(
        tmp_path / "bin" / "brew",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'brew %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
if [[ "$*" != "services start postgresql@16" ]]; then exit 97; fi
touch "$FAKE_NATIVE_READY_MARKER"
""",
    )
    env.update(
        {
            "AGENT_HUB_NATIVE_POSTGRES_SERVICE": "postgresql@16",
            "FAKE_NATIVE_READY_MARKER": str(ready_marker),
        }
    )

    result = subprocess.run(
        ["bash", "scripts/db_start.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Starting configured native database service: postgresql@16" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "brew services start postgresql@16" in commands
    assert "docker " not in commands


def test_db_start_recovers_when_direct_database_stops_after_runtime_selection(
    tmp_path: Path,
) -> None:
    env, command_log = native_script_env(tmp_path)
    ready_marker = tmp_path / "native-ready"
    readiness_count = tmp_path / "readiness-count"
    fake_python = Path(env["PYTHON"])
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == *scripts/db_client.py ]]; then
  exec "$REAL_PYTHON" "$@"
fi
if [[ "${1:-}" == "-c" ]]; then
  count=0
  if [[ -f "$FAKE_READINESS_COUNT" ]]; then
    count="$(<"$FAKE_READINESS_COUNT")"
  fi
  count=$((count + 1))
  printf '%s\n' "$count" > "$FAKE_READINESS_COUNT"
  if [[ "$count" -eq 1 || -f "$FAKE_NATIVE_READY_MARKER" ]]; then
    exit 0
  fi
  exit 1
fi
printf 'python %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
echo "ok"
""",
    )
    write_executable(
        tmp_path / "bin" / "brew",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'brew %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
if [[ "$*" != "services start postgresql@16" ]]; then exit 97; fi
touch "$FAKE_NATIVE_READY_MARKER"
""",
    )
    env.update(
        {
            "AGENT_HUB_NATIVE_POSTGRES_SERVICE": "postgresql@16",
            "FAKE_NATIVE_READY_MARKER": str(ready_marker),
            "FAKE_READINESS_COUNT": str(readiness_count),
        }
    )

    result = subprocess.run(
        ["bash", "scripts/db_start.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Starting configured native database service: postgresql@16" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "brew services start postgresql@16" in commands
    assert "docker " not in commands


def test_db_status_uses_reachable_direct_database_without_docker(tmp_path: Path) -> None:
    env, command_log = native_script_env(tmp_path)
    result = subprocess.run(
        ["bash", "scripts/db_status.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database runtime: direct (DATABASE_URL)" in result.stdout
    assert "Docker status: skipped" in result.stdout
    assert "native-secret" not in result.stdout
    assert "docker " not in command_log.read_text(encoding="utf-8")


def test_db_backup_uses_native_pg_dump_without_docker(tmp_path: Path) -> None:
    env, command_log = native_script_env(tmp_path)
    result = subprocess.run(
        ["bash", "scripts/db_backup.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    dumps = list((tmp_path / "backups").glob("agent_hub-*.dump"))
    assert len(dumps) == 1
    assert dumps[0].read_text(encoding="utf-8") == "native-dump\n"
    assert dumps[0].with_suffix(".dump.sha256").exists()
    commands = command_log.read_text(encoding="utf-8")
    assert "pg_dump --format=custom" in commands
    assert "docker " not in commands
    assert "native-secret" not in result.stdout


def test_db_backup_uses_clients_from_configured_homebrew_service(
    tmp_path: Path,
) -> None:
    env, command_log = native_script_env(tmp_path)
    service_prefix = tmp_path / "postgresql@16"
    service_bin = service_prefix / "bin"
    service_bin.mkdir(parents=True)
    write_executable(
        service_bin / "pg_dump",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'service-pg-dump %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
printf 'native-16-dump\n'
""",
    )
    write_executable(
        tmp_path / "bin" / "brew",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'brew %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
if [[ "$*" != "--prefix postgresql@16" ]]; then exit 97; fi
printf '%s\n' "$FAKE_SERVICE_PREFIX"
""",
    )
    env.update(
        {
            "AGENT_HUB_NATIVE_POSTGRES_SERVICE": "postgresql@16",
            "FAKE_SERVICE_PREFIX": str(service_prefix),
        }
    )

    result = subprocess.run(
        ["bash", "scripts/db_backup.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    commands = command_log.read_text(encoding="utf-8")
    assert "brew --prefix postgresql@16" in commands
    assert "service-pg-dump --format=custom" in commands
    assert "\npg_dump --format=custom" not in commands


def test_db_verify_backup_uses_isolated_native_database_without_docker(
    tmp_path: Path,
) -> None:
    env, command_log = native_script_env(tmp_path)
    dump_path = create_valid_backup(tmp_path / "backups")

    result = subprocess.run(
        ["bash", "scripts/db_verify_backup.sh", str(dump_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database runtime: direct (DATABASE_URL)" in result.stdout
    assert "Backup verification succeeded." in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert 'psql -X -v ON_ERROR_STOP=1 -d postgres -c CREATE DATABASE "' in commands
    assert "pg_restore --exit-on-error --no-owner" in commands
    assert "--dbname=agent_hub_verify_" in commands
    assert 'psql -X -v ON_ERROR_STOP=1 -d postgres -c DROP DATABASE IF EXISTS "' in commands
    assert "docker " not in commands
    assert "native-secret" not in result.stdout
    assert "native-secret" not in result.stderr


def test_db_restore_uses_native_postgres_clients_without_docker(tmp_path: Path) -> None:
    env, command_log = native_script_env(tmp_path)
    dump_path = tmp_path / "restore.dump"
    dump_path.write_bytes(b"restore-payload")
    result = subprocess.run(
        ["bash", "scripts/db_restore.sh", "--confirm", str(dump_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database runtime: direct (DATABASE_URL)" in result.stdout
    commands = command_log.read_text(encoding="utf-8")
    assert "psql -v ON_ERROR_STOP=1" in commands
    assert "pg_restore --file=- --no-owner" in commands
    assert "psql -X -v ON_ERROR_STOP=1" in commands
    assert "psql-stdin SELECT 1;" in commands
    assert "docker " not in commands
    assert "native-secret" not in result.stdout


def test_agent_preflight_accepts_reachable_direct_database_by_default(
    tmp_path: Path,
) -> None:
    env, command_log = native_script_env(tmp_path)
    create_valid_backup(tmp_path / "backups")
    result = subprocess.run(
        ["bash", "scripts/agent_preflight.sh", "--compact"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database: ok (direct)" in result.stdout
    assert "Schema migrations: ok" in result.stdout
    assert "Agent preflight result: ready" in result.stdout
    commands = (
        command_log.read_text(encoding="utf-8") if command_log.exists() else ""
    )
    assert "docker " not in commands
    assert "native-secret" not in result.stdout
    assert "native-secret" not in result.stderr


def test_preflight_refuses_silent_docker_fallback_for_configured_native_service(
    tmp_path: Path,
) -> None:
    env, command_log = native_script_env(tmp_path)
    fake_python = Path(env["PYTHON"])
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == *scripts/db_client.py ]]; then
  exec "$REAL_PYTHON" "$@"
fi
if [[ "${1:-}" == "-c" ]]; then
  exit 1
fi
printf 'python %s\n' "$*" >> "$FAKE_RUNTIME_LOG"
echo "ok"
""",
    )
    env["AGENT_HUB_NATIVE_POSTGRES_SERVICE"] = "postgresql@16"

    result = subprocess.run(
        ["bash", "scripts/agent_preflight.sh", "--compact"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "configured native database is not reachable" in result.stderr
    assert "scripts/db_start.sh" in result.stderr
    commands = (
        command_log.read_text(encoding="utf-8") if command_log.exists() else ""
    )
    assert "docker " not in commands


def test_db_doctor_diagnoses_reachable_direct_database_without_docker(
    tmp_path: Path,
) -> None:
    env, command_log = native_script_env(tmp_path)
    result = subprocess.run(
        ["bash", "scripts/db_doctor.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database runtime: direct (DATABASE_URL)" in result.stdout
    assert "Docker: skipped (not required for direct database access)" in result.stdout
    assert "Doctor result: ready" in result.stdout
    assert "docker " not in command_log.read_text(encoding="utf-8")
    assert "native-secret" not in result.stdout
    assert "native-secret" not in result.stderr


def test_db_doctor_points_native_runtime_failure_to_start_not_docker_recovery(
    tmp_path: Path,
) -> None:
    env, _ = native_script_env(tmp_path)
    fake_python = Path(env["PYTHON"])
    write_executable(
        fake_python,
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-c" ]]; then
  exit 1
fi
exit 97
""",
    )
    env["AGENT_HUB_NATIVE_POSTGRES_SERVICE"] = "postgresql@16"

    result = subprocess.run(
        ["bash", "scripts/db_doctor.sh"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "scripts/db_start.sh" in result.stdout
    assert "scripts/db_recover.sh --apply" not in result.stdout
    assert "Docker Postgres instance" not in result.stdout


def test_public_templates_leave_reviewer_identity_explicit() -> None:
    env_example = read_script(".env.example")
    reviewer_vars = [
        "AGENT_HUB_REVIEWERS",
        "AGENT_HUB_REVIEWER",
        "AGENT_HUB_DEFAULT_REVIEWER",
        "HUB_VIEW_REVIEWER",
    ]

    for variable in reviewer_vars:
        active_assignment = f"{variable}="
        assert active_assignment in env_example
        assert f"# {active_assignment}" in env_example
        assert all(
            line.lstrip().startswith("#") or not line.strip().startswith(active_assignment)
            for line in env_example.splitlines()
        )


def test_automation_boundaries_show_required_reviewer_for_inbox_review() -> None:
    docs = read_script("docs/automation-boundaries.md")

    assert "agent-hub inbox --accept <draft-id> --reviewer alice" in docs
    assert "agent-hub inbox --reject <draft-id> --reviewer alice" in docs
    assert "agent-hub inbox --accept <draft-id>\n" not in docs
    assert "agent-hub inbox --reject <draft-id>\n" not in docs
    assert "public templates leave it unset so review identity is chosen explicitly" in docs


def test_automation_boundaries_describe_guarded_codex_setup_action() -> None:
    docs = read_script("docs/automation-boundaries.md")

    assert "local Codex setup action" in docs
    assert "repo-local working-rule file, not Hub memory" in docs
    assert "each form includes a server-generated CSRF token" in docs
    assert "the browser does not provide the repo path" in docs
    assert "path from ADH metadata" in docs
    assert "public-demo checkout is preview/dry-run only" in docs
    assert "no shell command is executed from Hub View" in docs


def test_seed_readme_separates_public_demo_from_maintainer_ops() -> None:
    seed_readme = read_script("seed/README.md")
    readme = read_script("README.md")
    db_start = read_script("scripts/db_start.sh")

    assert "`demo.sql` is the neutral public demo dataset" in seed_readme
    assert "operator-specific seed files are not shipped" in seed_readme
    assert "scripts/db_start_public_demo.sh" in seed_readme
    assert "scripts/first_run_demo.sh" in seed_readme
    assert "scripts/db_start.sh --seed-file /path/to/local-operator-seed.sql" in seed_readme
    assert "Do not add secrets" in seed_readme
    assert "[`seed/README.md`](seed/README.md)" in readme
    assert "maintainer-specific seed data" in readme
    assert "--seed-file <path>" in db_start
    assert "Error: --seed-file requires a path." in db_start
    assert "No private operator seed files were applied." in db_start
    assert not (ROOT / "seed/business_sites.sql").exists()
    assert not (ROOT / "seed/agentic_projects.sql").exists()


def test_v015_release_notes_describe_guarded_codex_setup_without_overclaim() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.5-release-notes.md")

    assert "[v0.1.5 release notes](docs/public/v0.1.5-release-notes.md)" in readme
    assert "Guarded Codex Setup From Hub View" in notes
    assert "public demo" in notes
    assert "dry-run" in notes
    assert "no Hub-memory write path" in notes
    assert "no shell command execution from Hub View" in notes
    assert "does not run Codex" in notes
    assert "magically use context" in notes
    assert "Local Mobile Preview" in notes
    assert "trusted Wi-Fi" in notes
    assert "no mobile write path" in notes


def test_v016_release_notes_describe_maintenance_hardening() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.6-release-notes.md")
    protocol = read_script("docs/first-run-test-protocol.md")

    assert "[v0.1.6 release notes](docs/public/v0.1.6-release-notes.md)" in readme
    assert "[v0.1.6 release notes]" in readme.split("[v0.1.5 release notes]")[0]
    assert "Agent Data Hub v0.1.6" in notes
    assert "Safer LAN Read Behavior" in notes
    assert "--allow-lan-read" in notes
    assert "Hub View Structure" in notes
    assert "hub_view_models.py" in notes
    assert "hub_view_server.py" in notes
    assert "Faster Project Overview Loading" in notes
    assert "batch their memory counts and latest-report lookups" in notes
    assert "First-Run Reuse" in notes
    assert "reuses the existing local install" in notes
    assert "no schema change" in notes
    assert "no migration" in notes
    assert "no new Hub-memory write path" in notes


def test_v017_release_notes_describe_visible_agent_connection() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.7-release-notes.md")
    protocol = read_script("docs/first-run-test-protocol.md")

    assert "[v0.1.7 release notes](docs/public/v0.1.7-release-notes.md)" in readme
    assert "[v0.1.7 release notes]" in readme.split("[v0.1.6 release notes]")[0]
    assert "Agent Data Hub v0.1.7" in notes
    assert "Project Actions In Hub View" in notes
    assert "Hand context to an agent" in notes
    assert "Clearer Agent Connection Paths" in notes
    assert "Connection Verification" in notes
    assert "Codex setup verified" in notes
    assert "Demo preview only" in notes
    assert "manual or external checks" in notes
    assert "no schema change" in notes
    assert "no migration" in notes
    assert "no new Hub-memory write path" in notes
    assert "# First-Run Test Protocol (current main)" in protocol
    assert "does **not** test a historical" in protocol
    assert "Found Connect your agent" in protocol
    assert "Understood Choose your agent" in protocol
    assert "Found Connection verification" in protocol
    assert "Found Check handoff" in protocol
    assert "terminal fallback is temporary" in protocol


def test_v018_release_notes_describe_agent_connection_flow() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.8-release-notes.md")
    protocol = read_script("docs/first-run-test-protocol.md")

    assert "[v0.1.8 release notes](docs/public/v0.1.8-release-notes.md)" in readme
    assert "[v0.1.8 release notes]" in readme.split("[v0.1.7 release notes]")[0]
    assert "Agent Data Hub v0.1.8" in notes
    assert "Connect Your Agent" in notes
    assert "Agent Picker" in notes
    assert "Handoff Check" in notes
    assert "Choose your agent" in notes
    assert "Check the handoff" in notes
    assert "no schema change" in notes
    assert "no migration" in notes
    assert "no new Hub-memory write path" in notes
    assert "Found Connect your agent" in protocol
    assert "Understood Choose your agent" in protocol
    assert "Found Check handoff" in protocol


def test_v019_release_notes_describe_memory_explorer() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.9-release-notes.md")
    protocol = read_script("docs/first-run-test-protocol.md")

    assert "[v0.1.9 release notes](docs/public/v0.1.9-release-notes.md)" in readme
    assert "[v0.1.9 release notes]" in readme.split("[v0.1.8 release notes]")[0]
    assert "Agent Data Hub v0.1.9" in notes
    assert "Find Reviewed Memory" in notes
    assert "Search this page" in notes
    assert "Matching items appear directly below the search field" in notes
    assert "visible reviewed memory" in notes
    assert "does not search drafts" in notes
    assert "does not query hidden data" in notes
    assert "no schema change" in notes
    assert "no migration" in notes
    assert "no new Hub-memory write path" in notes
    assert "no autonomous search or background indexer" in notes
    assert "Found Find reviewed memory" in protocol
    assert "Used Search this page" in protocol
    assert "Saw matching items appear below the search field" in protocol
    assert "visible reviewed memory on the page" in protocol


def test_v013_release_notes_describe_first_run_compression() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.13-release-notes.md")
    getting_started = read_script("docs/public/getting-started.md")
    demo_session = read_script("docs/public/first-run-demo-session.md")

    assert "[v0.1.13 release notes](docs/public/v0.1.13-release-notes.md)" in readme
    assert "[v0.1.13 release notes]" in readme.split("[v0.1.12 release notes]")[0]
    assert "[First-run demo session](docs/public/first-run-demo-session.md)" in readme
    assert "Agent Data Hub v0.1.13" in notes
    assert "Public First-Run Compression" in notes
    assert "Local Ops Reliability" in notes
    assert "agent-hub doctor" in notes
    assert "scripts/db_recover.sh --apply" in notes
    assert "no automatic recovery without explicit `--apply`" in notes
    assert "What To Check First" in getting_started
    assert "[`first-run-demo-session.md`](first-run-demo-session.md)" in getting_started
    assert "What A Successful First Run Proves" in demo_session
    assert "It does not prove hosted deployment" in demo_session


def test_v014_release_notes_describe_seed_boundary_polish() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.14-release-notes.md")

    assert "[v0.1.14 release notes](docs/public/v0.1.14-release-notes.md)" in readme
    assert "[v0.1.14 release notes]" in readme.split("[v0.1.13 release notes]")[0]
    assert "Agent Data Hub v0.1.14" in notes
    assert "public-preview hygiene release" in notes
    assert "seed/README.md" in notes
    assert "neutral public demo seed" in notes
    assert "private operator seeds belong outside Git" in notes
    assert "no schema change" in notes
    assert "no new Hub-memory write path" in notes


def test_v015_release_notes_describe_public_demo_doctor_path() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.15-release-notes.md")

    assert "[v0.1.15 release notes](docs/public/v0.1.15-release-notes.md)" in readme
    assert "[v0.1.15 release notes]" in readme.split("[v0.1.14 release notes]")[0]
    assert "Agent Data Hub v0.1.15" in notes
    assert "public-demo reliability release" in notes
    assert "scripts/db_doctor.sh --public-demo" in notes
    assert "scripts/first_run_demo.sh" in notes
    assert "configured operator doctor path" in notes
    assert "no schema change" in notes
    assert "no migration" in notes
    assert "no new Hub-memory write path" in notes


def test_v016_release_notes_describe_root_aware_offline_hints() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.16-release-notes.md")

    assert "[v0.1.16 release notes](docs/public/v0.1.16-release-notes.md)" in readme
    assert "[v0.1.16 release notes]" in readme.split("[v0.1.15 release notes]")[0]
    assert "Agent Data Hub v0.1.16" in notes
    assert "operational-stability polish release" in notes
    assert "ADH-root-aware diagnosis and start" in notes
    assert "non-ADH working directories" in notes
    assert "no schema change" in notes
    assert "no migration" in notes
    assert "no new Hub-memory write path" in notes
    assert "no automatic recovery" in notes


def test_v017_release_notes_describe_daily_use_path() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.17-release-notes.md")

    assert "[v0.1.17 release notes](docs/public/v0.1.17-release-notes.md)" in readme
    assert "[v0.1.17 release notes]" in readme.split("[v0.1.16 release notes]")[0]
    assert "Agent Data Hub v0.1.17" in notes
    assert "product-coherence documentation release" in notes
    assert "docs/public/daily-use.md" in notes
    assert "public demo first" in notes
    assert "registered project" in notes
    assert "visible agent handoff" in notes
    assert "no schema change" in notes
    assert "no new Hub-memory write path" in notes


def test_v018_release_notes_describe_operational_reliability_smoke() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.18-release-notes.md")

    assert "[v0.1.18 release notes](docs/public/v0.1.18-release-notes.md)" in readme
    assert "[v0.1.18 release notes]" in readme.split("[v0.1.17 release notes]")[0]
    assert "Agent Data Hub v0.1.18" in notes
    assert "operational reliability release" in notes
    assert "scripts/smoke_public_demo.sh" in notes
    assert "demo `prepare` path" in notes
    assert "Context Trail" in notes
    assert "Known Gaps" in notes
    assert "exports OKF twice" in notes
    assert "stable OKF preview bundle" in notes
    assert "no schema change" in notes
    assert "no new Hub-memory write path" in notes


def test_v019_release_notes_describe_fresh_clone_ci_drill() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.19-release-notes.md")

    assert "[v0.1.19 release notes](docs/public/v0.1.19-release-notes.md)" in readme
    assert "[v0.1.19 release notes]" in readme.split("[v0.1.18 release notes]")[0]
    assert "Agent Data Hub v0.1.19" in notes
    assert "fresh-clone public demo job" in notes
    assert "documented manual public demo path" in notes
    assert "copy `.env.example`" in notes
    assert "public demo doctor" in notes
    assert "public demo smoke" in notes
    assert "clean Ubuntu runner" in notes
    assert "no schema change" in notes
    assert "no new product feature" in notes


def test_v020_release_notes_describe_v02_readiness_cleanup() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.20-release-notes.md")

    assert "[v0.1.20 release notes](docs/public/v0.1.20-release-notes.md)" in readme
    assert "[v0.1.20 release notes]" in readme.split("[v0.1.19 release notes]")[0]
    assert "Agent Data Hub v0.1.20" in notes
    assert "v0.2-readiness cleanup release" in notes
    assert "reviewed context" in notes
    assert "docs/public/trust-model.md" in notes
    assert "docs/public/installation.md" in notes
    assert "checkout is the installation unit" in notes
    assert "upgrade-drill" in notes
    assert "docs/operator/" in notes
    assert "no schema change" in notes
    assert "no new Hub-memory write path" in notes


def test_v021_release_notes_describe_v1_adoption_readiness_cleanup() -> None:
    readme = read_script("README.md")
    notes = read_script("docs/public/v0.1.21-release-notes.md")
    definition = read_script("docs/public/v1.0-definition.md")
    checklist = read_script("docs/public/release-checklist.md")
    daily_use = read_script("docs/public/daily-use.md")

    assert "[v0.1.21 release notes](docs/public/v0.1.21-release-notes.md)" in readme
    assert "[v0.1.21 release notes]" in readme.split("[v0.1.20 release notes]")[0]
    assert "Agent Data Hub v0.1.21" in notes
    assert "v1.0 adoption-readiness cleanup release" in notes
    assert "neutral demo seed data" in notes
    assert "Private operator seeds must live outside Git" in notes
    assert "neutral demo project names and placeholder paths" in notes
    assert "database-independent" in notes
    assert "initial 390 x 844 viewport" in notes
    assert "no packaging change" in notes
    assert "no new review channel" in notes
    assert "explicit deferral, not usability evidence" in notes
    assert "only open v1.0 release gate" in notes
    assert "Do not tag or broadly promote v1.0" in notes
    assert "missing first-run observation as an open release gate" in definition
    assert "first-time human understanding" in checklist
    assert "scripts/smoke_external_developer.sh" in daily_use
    assert "does not prove that a first-time user understands" in daily_use


def test_ci_runs_agent_offline_smoke() -> None:
    ci = read_script(".github/workflows/ci.yml")
    script = read_script("scripts/smoke_agent_offline.sh")

    assert "agent-offline-smoke:" in ci
    assert "Run agent offline-behavior smoke" in ci
    assert "scripts/smoke_agent_offline.sh" in ci

    assert "central-agent-data-hub-offline-smoke-postgres-missing" in script
    assert "AGENT_HUB_IGNORE_ENV_FILE=1" in script
    assert "scripts/agent_preflight.sh" in script
    assert "scripts/agent_start.sh" in script
    assert "scripts/agent_finish.sh" in script
    assert "Expected operational exit code 2" in script
    assert "Der zentrale Agent Data Hub laeuft lokal gerade nicht." in script
    assert "Operational error: durable DB container is missing." in script
    assert "== Offline Finish Protocol ==" in script
    assert "No reviewed memory was written by this finish attempt." in script
    assert "Do not mark Hub writeback, export, backup, or review-memory as complete." in script
    assert "AGENT_HUB_OFFLINE_FINISH_DIR" in script
    assert "central-agent-data-hub-demo-latest.md" in script
    assert "reviewed_memory_written: no" in script
    assert "export_completed: no" in script
    assert "backup_completed: no" in script
    assert "Recovery note:" in script
    assert "Offline-agent smoke: ok" in script


def test_ci_runs_external_developer_smoke() -> None:
    ci = read_script(".github/workflows/ci.yml")
    script = read_script("scripts/smoke_external_developer.sh")

    assert "external-developer-smoke:" in ci
    assert "Run first external-developer project smoke" in ci
    assert "scripts/smoke_external_developer.sh" in ci

    assert "agent_hub_external_dev_demo" in script
    assert "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" in script
    assert 'mkdir -p "$OBSIDIAN_EXPORT_DIR"' in script
    assert "agent_hub-external-developer-demo.dump" in script
    assert '"$ROOT_DIR/scripts/db_backup_health.sh" --require' in script
    assert 'export OBSIDIAN_EXPORT_DIR="$tmp_dir/obsidian-export"' in script
    assert "run_agent_hub register-project" in script
    assert "git -C \"$external_repo\" init" in script
    assert "Project slug: \\`$project_slug\\`" in script
    assert "scripts/agent_start.sh" in script
    assert "ADH Context Loaded" in script
    assert "run_agent_hub remember" in script
    assert "--metadata assigned_reviewer=demo-reviewer" in script
    assert "run_agent_hub inbox" in script
    assert "--accept \"$draft_id\"" in script
    assert "run_agent_hub prepare" in script
    assert "run_agent_hub handoff" in script
    assert "scripts/agent_finish.sh" in script
    assert "--export" in script
    assert "--backup" in script
    assert "== Obsidian Export ==" in script
    assert "== Database Backup Verification ==" in script
    assert "Backup verification succeeded." in script
    assert "scripts/memory_receipt.sh" in script
    assert "result: ok" in script
    assert "fact/verified" in script
    assert "exported: yes" in script
    assert "External-developer smoke: ok" in script


def test_hub_view_template_is_split_into_view_partials() -> None:
    page = read_script("templates/hub_view/page.html")
    base_css = read_script("templates/hub_view/static/base.css")
    layout_css = read_script("templates/hub_view/static/layout.css")
    project_overview_css = read_script("templates/hub_view/static/project_overview.css")
    memory_search_css = read_script("templates/hub_view/static/memory_search.css")
    agent_handoff_css = read_script("templates/hub_view/static/agent_handoff.css")
    responsive_css = read_script("templates/hub_view/static/responsive.css")
    copy_js = read_script("templates/hub_view/static/copy.js")
    shared_js = read_script("templates/hub_view/static/shared.js")
    memory_search_js = read_script("templates/hub_view/static/memory_search.js")
    project_nav_js = read_script("templates/hub_view/static/project_nav.js")
    inbox_filter_js = read_script("templates/hub_view/static/inbox_filter.js")
    connection_js = read_script("templates/hub_view/static/connection_checklist.js")

    for partial in (
        "templates/hub_view/views/inbox.html",
        "templates/hub_view/views/agent_context.html",
        "templates/hub_view/views/project_detail.html",
        "templates/hub_view/static/base.css",
        "templates/hub_view/static/layout.css",
        "templates/hub_view/static/project_overview.css",
        "templates/hub_view/static/workbench.css",
        "templates/hub_view/static/memory_library.css",
        "templates/hub_view/static/memory_search.css",
        "templates/hub_view/static/review_surfaces.css",
        "templates/hub_view/static/agent_handoff.css",
        "templates/hub_view/static/quality_detail.css",
        "templates/hub_view/static/memory_detail.css",
        "templates/hub_view/static/responsive.css",
        "templates/hub_view/static/shared.js",
        "templates/hub_view/static/copy.js",
        "templates/hub_view/static/memory_search.js",
        "templates/hub_view/static/project_nav.js",
        "templates/hub_view/static/inbox_filter.js",
        "templates/hub_view/static/connection_checklist.js",
    ):
        assert (ROOT / partial).is_file()

    assert '{% include "views/inbox.html" %}' in page
    assert '{% include "views/agent_context.html" %}' in page
    assert '{% include "views/project_detail.html" %}' in page
    assert "{% for asset in stylesheet_assets %}" in page
    assert "{% for asset in script_assets %}" in page
    assert "<style>" not in page
    assert "<script>" not in page
    assert "/* Base chrome */" in base_css
    assert ".workspace-link" in layout_css
    assert ".project-overview" in project_overview_css
    assert ".project-overview-focus" in project_overview_css
    assert ".memory-explorer" in memory_search_css
    assert ".agent-form" in agent_handoff_css
    assert "body.view-projects.has-selected-project" in responsive_css
    assert "data-copy-target" in copy_js
    assert "window.ADHHubView.searchTerms" in shared_js
    assert "itemHaystack" in memory_search_js
    assert "updateProjectSectionNav" in project_nav_js
    assert "inboxHaystack" in inbox_filter_js
    assert "updateConnectionChecklist" in connection_js


def test_hub_view_python_entrypoint_delegates_to_split_modules() -> None:
    entrypoint = read_script("agent_hub/hub_view.py")

    assert (ROOT / "agent_hub/hub_view_models.py").is_file()
    assert (ROOT / "agent_hub/hub_view_server.py").is_file()
    assert "from agent_hub.hub_view_models import" in entrypoint
    assert "from agent_hub.hub_view_server import" in entrypoint
    assert "raise SystemExit(main())" in entrypoint


def test_package_version_matches_v021_release_candidate() -> None:
    pyproject = read_script("pyproject.toml")
    checklist = read_script("docs/public/release-checklist.md")
    readme = read_script("README.md")

    assert 'version = "0.1.21"' in pyproject
    assert "[v0.1.21 release notes](docs/public/v0.1.21-release-notes.md)" in readme
    assert "version` matches the tag" in checklist
    assert "Do not move an already published tag" in checklist
    assert "[Release checklist](docs/public/release-checklist.md)" in readme


def test_release_checklist_tracks_v1_evidence_and_human_first_run_proof() -> None:
    checklist = read_script("docs/public/release-checklist.md")
    protocol = read_script("docs/first-run-test-protocol.md")

    assert "scripts/v1_readiness_check.sh" in checklist
    assert "v1.0-definition.md" in checklist
    assert "v0.7-definition.md" not in checklist
    assert "public demo receipt" in checklist
    assert "first external project smoke" in checklist
    assert "restore drill" in checklist
    assert "`agent-hub doctor`" in checklist
    assert "docs/first-run-test-protocol.md" in checklist
    assert "real technical tester" in checklist
    assert "Keep observation notes outside the repository" in checklist
    assert "If the human proof is deferred" in checklist
    assert "Do not imply that automated checks measured" in checklist
    assert "publicly reachable in an" in checklist
    assert "unauthenticated browser before using it in public copy" in checklist
    assert "A green unit-test job alone is not enough" in checklist
    assert "human proof path that complements" in protocol
    assert "`scripts/v1_readiness_check.sh`" in protocol
    assert "without maintainer memory" in protocol


def test_ci_uses_node24_github_actions() -> None:
    ci = read_script(".github/workflows/ci.yml")

    assert "actions/checkout@v7" in ci
    assert "actions/setup-python@v6" in ci
    assert "actions/checkout@v4" not in ci
    assert "actions/setup-python@v5" not in ci


def test_ci_runs_fresh_clone_public_demo_drill() -> None:
    ci = read_script(".github/workflows/ci.yml")

    assert "fresh-clone-public-demo:" in ci
    assert 'python-version: "3.12"' in ci
    assert "Run documented public demo path" in ci
    assert "python -m venv .venv" in ci
    assert ".venv/bin/python -m pip install -e ." in ci
    assert "cp .env.example .env" in ci
    assert "scripts/db_start_public_demo.sh" in ci
    assert "scripts/db_doctor.sh --public-demo" in ci
    assert "scripts/smoke_public_demo.sh" in ci
    assert "AGENT_HUB_DOCKER_TIMEOUT_SECONDS" in ci
    assert "AGENT_HUB_DB_START_TIMEOUT_SECONDS" in ci


def test_ci_runs_upgrade_drill_against_demo_database() -> None:
    ci = read_script(".github/workflows/ci.yml")
    script = read_script("scripts/upgrade_drill.sh")

    assert "upgrade-drill:" in ci
    assert "Run baseline-to-head upgrade drill" in ci
    assert "scripts/upgrade_drill.sh" in ci
    assert "AGENT_HUB_PUBLIC_DEMO=1" in script
    assert "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" in script
    assert 'apply_sql_file "migrations/001_init.sql"' in script
    assert "Tracking: missing" in script
    assert "run_agent_hub migrate --apply" in script
    assert 'apply_sql_file "seed/demo.sql"' in script
    assert '"$ROOT_DIR/scripts/smoke_public_demo.sh"' in script
    assert "refused non-demo database" in script


def test_ci_runs_multi_agent_trust_loop_smoke() -> None:
    ci = read_script(".github/workflows/ci.yml")
    script = read_script("scripts/smoke_trust_loop.sh")

    assert "trust-loop-smoke:" in ci
    assert "Run multi-agent trust-loop smoke" in ci
    assert "scripts/smoke_trust_loop.sh" in ci
    assert "AGENT_HUB_DOCKER_TIMEOUT_SECONDS" in ci
    assert "AGENT_HUB_DB_START_TIMEOUT_SECONDS" in ci

    assert "AGENT_HUB_PUBLIC_DEMO=1" in script
    assert "central-agent-data-hub-trust-loop" in script
    assert "agent_hub_trust_loop_demo" in script
    assert "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" in script
    assert "repo-review.md" in script
    assert "signal_file" in script
    assert "run_agent_hub remember" in script
    assert "--metadata assigned_reviewer=demo-reviewer" in script
    assert "run_agent_hub inbox" in script
    assert "--for demo-reviewer" in script
    assert "--accept \"$draft_id\"" in script
    assert "--reviewer demo-reviewer" in script
    assert "from agent_hub.review_api import" in script
    assert 'review_source="telegram"' in script
    assert "External Review Adapter" in script
    assert "run_agent_hub prepare" in script
    assert "drafts_pending_review" in script
    assert "verified_project_state" in script
    assert "run_agent_hub handoff" in script
    assert "mcp_server.prepare_context_pack_payload" in script
    assert "MCP context trail" in script
    assert "SELECT metadata, output" in script
    assert "inbox_accept" in script
    assert "review_source" in script
    assert "Trust-loop smoke: ok" in script


def test_public_trust_model_uses_reviewed_claim_and_documents_compat_key() -> None:
    readme = read_script("README.md")
    pyproject = read_script("pyproject.toml")
    boundaries = read_script("docs/automation-boundaries.md")
    workflow = read_script("docs/agent-workflow.md")
    daily_use = read_script("docs/public/daily-use.md")
    trust = read_script("docs/public/trust-model.md")

    assert "> reviewed context for humans and agents" in readme
    assert "Verified project memory for agentic work." not in pyproject
    assert "reviewed context for humans and agents" in boundaries
    assert "durably reviewed" in workflow
    assert "reviewed project state" in workflow
    assert "reviewed assumptions" in daily_use
    assert "# Trust Model" in trust
    assert "does not prove the real-world claim is objectively true" in trust
    assert "Facts can still have the database status `verified`" in trust
    assert "`verified_project_state` remains part of" in trust
    assert "[Trust model](docs/public/trust-model.md)" in readme


def test_installation_boundary_documents_checkout_as_installation_unit() -> None:
    readme = read_script("README.md")
    getting_started = read_script("docs/public/getting-started.md")
    installation = read_script("docs/public/installation.md")
    system = read_script("agent_hub/commands/system.py")

    assert "[Installation boundary](docs/public/installation.md)" in readme
    assert "repository checkout is the installation unit" in getting_started
    assert "# Installation Boundary" in installation
    assert "git checkout as the installation unit" in installation
    assert "Native Windows is not a supported target for this preview" in installation
    assert "v0.2 target" not in installation
    assert "A regular `pip install` can expose importable Python modules" in installation
    assert "checkout_script_path" in system
    assert "requires an Agent Data Hub repository checkout" in system


def test_v02_definition_keeps_milestone_scope_narrow_and_testable() -> None:
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    definition = read_script("docs/public/v0.2-definition.md")

    assert "[v0.2 definition](docs/public/v0.2-definition.md)" in readme
    assert "docs/public/v0.2-definition.md" in roadmap
    assert "reviewed context for humans and agents" in roadmap
    assert "verified memory for agentic work" not in roadmap

    assert "# v0.2 Definition" in definition
    assert "reviewed context for humans and agents" in definition
    assert "clone the repository, start the public demo" in definition
    assert "`agent-hub prepare` produces a task-specific context pack" in definition
    assert "Draft memory candidates stay outside reviewed memory" in definition
    assert "fresh-clone public demo job" in definition
    assert "baseline-to-head upgrade drill" in definition
    assert "write-capable MCP tools" in definition
    assert "non-checkout package installation as the main path" in definition
    assert "Telegram or other chat adapters inside this repository" in definition


def test_v03_definition_tracks_multi_agent_trust_loop_contract() -> None:
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    definition = read_script("docs/public/v0.3-definition.md")

    assert "[v0.3 definition](docs/public/v0.3-definition.md)" in readme
    assert "scripts/smoke_trust_loop.sh" in readme
    assert "docs/public/v0.3-definition.md" in roadmap
    assert "scripts/smoke_trust_loop.sh" in roadmap
    assert "# v0.3 Definition" in definition
    assert "multi-agent trust loop" in definition
    assert "Signal Inbox-style note" in definition
    assert "Deterministic routing stores ordinary candidates as `draft`" in definition
    assert "who reviewed it, which channel submitted the review" in definition
    assert "`review_source=telegram`" in definition
    assert "read-only MCP prepare payload" in definition
    assert "scripts/smoke_trust_loop.sh" in definition
    assert "CI must run this smoke as its own job" in definition
    assert "automatic draft promotion" in definition
    assert "write-capable MCP tools" in definition
    assert "chat adapter code inside this repository" in definition


def test_v04_definition_tracks_operational_reliability_contract() -> None:
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    definition = read_script("docs/public/v0.4-definition.md")
    daily_use = read_script("docs/public/daily-use.md")
    run_loop = read_script("docs/agent-run-loop.md")

    assert "[v0.4 definition](docs/public/v0.4-definition.md)" in readme
    assert "scripts/smoke_agent_offline.sh" in readme
    assert "docs/public/v0.4-definition.md" in roadmap
    assert "scripts/smoke_agent_offline.sh" in roadmap
    assert "# v0.4 Definition" in definition
    assert "local daily agent loop is operationally reliable" in roadmap
    assert "agent_start.sh" in definition
    assert "agent_finish.sh" in definition
    assert "Offline Finish Protocol" in definition
    assert "no reviewed memory" in definition
    assert "automatic restart or recovery" in definition
    assert "automatic writeback after reconnect" in definition
    assert "offline-behavior smoke is green locally" in definition
    assert "in CI" in definition
    assert "finish stops before writing reviewed memory" in daily_use
    assert "rerun the same finish command" in daily_use
    assert ".local/offline-finish/" in daily_use
    assert "explicit markers" in daily_use
    assert "stop before any" in run_loop
    assert "reviewed_memory_written: no" in run_loop
    assert "not Hub memory" in run_loop
    assert "reviewed writeback" in run_loop
    assert "doctor/start path" in run_loop


def test_v05_definition_tracks_first_external_developer_contract() -> None:
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    definition = read_script("docs/public/v0.5-definition.md")
    daily_use = read_script("docs/public/daily-use.md")

    assert "[v0.5 definition](docs/public/v0.5-definition.md)" in readme
    assert "scripts/smoke_external_developer.sh" in readme
    assert "docs/public/v0.5-definition.md" in roadmap
    assert "scripts/smoke_external_developer.sh" in roadmap
    assert "# v0.5 Definition" in definition
    assert "first external developer success path" in definition
    assert "Register a new local Git repository" in definition
    assert "Install the repo-local Agent Data Hub instructions" in definition
    assert "Create one unreviewed memory candidate and keep it as a draft" in definition
    assert "Review the draft explicitly with reviewer attribution" in definition
    assert "CI must run this smoke as its own job" in definition
    assert "standalone package installation as the main path" in definition
    assert "hosted deployment" in definition
    assert "scripts/smoke_external_developer.sh" in daily_use
    assert "temporary local repository" in daily_use


def test_operator_notes_are_separated_from_public_path() -> None:
    operator_readme = read_script("docs/operator/README.md")
    workflow = read_script("docs/agent-workflow.md")
    active_projects = read_script("docs/operator/active-projects.md")

    assert "# Operator Notes" in operator_readme
    assert "not the public product path" in operator_readme
    assert "Public first-run and daily-use documentation lives under" in operator_readme
    assert "docs/operator/codex-memory-policy.md" in workflow
    assert "docs/operator/sensitive-access-handoffs.md" in workflow
    assert "docs/operator/sensitive-access-handoffs.md" in active_projects
    assert not (ROOT / "docs/active-projects.md").exists()
    assert not (ROOT / "docs/codex-memory-policy.md").exists()
    assert not (ROOT / "docs/sensitive-access-handoffs.md").exists()


def test_preflight_uses_bounded_docker_checks() -> None:
    common = read_script("scripts/db_common.sh")
    preflight = read_script("scripts/agent_preflight.sh")
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    definition = read_script("docs/public/v0.8-definition.md")

    assert "run_with_timeout()" in common
    assert "AGENT_HUB_DOCKER_TIMEOUT_SECONDS" in common
    assert "AGENT_HUB_DB_START_TIMEOUT_SECONDS" in common
    assert "AGENT_HUB_DISK_WARN_MB" in common
    assert "AGENT_HUB_DISK_ERROR_MB" in common
    assert "COMPOSE_PROJECT_NAME" in common
    assert "COMMON_GIT_DIR" in common
    assert "SHARED_ROOT" in common
    assert 'git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir' in common
    assert "docker_quick()" in common
    assert "compose_quick()" in common
    assert "postgres_ready()" in common
    assert "postgres_container_state()" in common
    assert "print_host_runtime_health()" in common
    assert "available_mb_for_path()" in common
    assert "check_temp_dir_writable()" in common
    assert "Repo free space:" in common
    assert "Temp free space:" in common
    assert "Temp writable:" in common
    assert "print_postgres_start_failure()" in common
    assert "did not become ready" in common
    assert "This script will not delete local Docker volumes automatically." in common
    assert "agent-hub doctor" in common
    assert "scripts/db_doctor.sh" in common
    assert "scripts/db_doctor.sh --public-demo" in common
    assert "Use the same AGENT_HUB_* overrides if this demo run used any." in common
    assert "$ROOT_DIR/scripts/db_recover.sh --apply" in common
    assert "AGENT_HUB_COMPOSE_PROJECT_NAME=adh-demo-fresh" in common
    assert 'docker_quick logs --tail 40 "$DB_CONTAINER"' in common
    assert "pg_isready -h localhost -p \"$DB_PORT\"" in common
    assert 'docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE"' in common
    assert 'elif [[ -x "$SHARED_ROOT/.venv/bin/python"' in common
    assert 'elif [[ -f "$SHARED_ROOT/.env" ]]' in common
    assert 'OBSIDIAN_EXPORT_DIR="$SHARED_ROOT/$OBSIDIAN_EXPORT_DIR"' in common
    assert 'AGENT_HUB_BACKUP_DIR="$SHARED_ROOT/$AGENT_HUB_BACKUP_DIR"' in common

    assert "print_host_runtime_health --compact" in preflight
    assert "Operational error: host runtime is not ready." in preflight
    assert "try_direct_db_preflight()" in preflight
    assert "durable DB container is not visible to this runtime." in preflight
    assert "direct read-only fallback was not usable; continuing with Docker diagnosis." in preflight
    assert "docker_quick inspect \"$DB_CONTAINER\"" in preflight
    assert "Der zentrale Agent Data Hub laeuft lokal gerade nicht." in preflight
    assert "Bitte Docker starten oder kurz warten" in preflight
    assert "docker is not responding within" in preflight
    assert "Restart Docker Desktop" in preflight
    assert "Diagnose:" in preflight
    assert "Start:" in preflight
    assert '$ROOT_DIR/scripts/db_doctor.sh' in preflight
    assert '$ROOT_DIR/scripts/db_start.sh' in preflight
    assert '$ROOT_DIR/scripts/db_status.sh' in preflight
    assert "postgres_ready" in preflight
    assert "compose exec -T \"$DB_SERVICE\" pg_isready" not in preflight
    assert "run_agent_hub projects --format json" in preflight
    assert "Project briefs: ok ($brief_count checked)" in preflight
    assert "brief --project demo-website" not in preflight
    assert "brief --project demo-catering" not in preflight

    assert "[v0.8 definition](docs/public/v0.8-definition.md)" in readme
    assert "docs/public/v0.8-definition.md" in roadmap
    assert "# v0.8 Definition" in definition
    assert "local runtime health" in definition
    assert "disk and temp-dir checks" in definition
    assert "automatic recovery" in definition


def test_db_doctor_and_recover_are_safe_local_ops_paths() -> None:
    doctor = read_script("scripts/db_doctor.sh")
    recover = read_script("scripts/db_recover.sh")
    verify_backup = read_script("scripts/db_verify_backup.sh")
    parser = read_script("agent_hub/commands/parser.py")
    system = read_script("agent_hub/commands/system.py")
    readme = read_script("README.md")
    workflow = read_script("docs/agent-workflow.md")
    boundaries = read_script("docs/automation-boundaries.md")
    architecture = read_script("docs/code-architecture.md")

    assert (ROOT / "scripts/db_doctor.sh").exists()
    assert os.access(ROOT / "scripts/db_doctor.sh", os.X_OK)
    assert (ROOT / "scripts/db_recover.sh").exists()
    assert os.access(ROOT / "scripts/db_recover.sh", os.X_OK)

    assert "Central Agent Data Hub doctor" in doctor
    assert "--public-demo" in doctor
    assert "export AGENT_HUB_PUBLIC_DEMO=1" in doctor
    assert doctor.index("export AGENT_HUB_PUBLIC_DEMO=1") < doctor.index(
        'source "$(cd "$(dirname "${BASH_SOURCE[0]}")"'
    )
    assert "bogus data in lock file" in doctor
    assert "$ROOT_DIR/scripts/db_recover.sh --apply" in doctor
    assert 'echo "  scripts/db_recover.sh --apply"' not in doctor
    assert "run_agent_hub status" in doctor
    assert "run_agent_hub check" in doctor
    assert "print_host_runtime_health" in doctor
    assert "Port listener:" in doctor
    assert 'lsof -nP -iTCP:"$DB_PORT" -sTCP:LISTEN' in doctor
    assert 'dump_path="$(latest_backup_dump)"' in verify_backup
    assert "-name '*.dump'" not in verify_backup
    assert "projects --format json" in verify_backup
    assert "brief --project \"$brief_project\"" in verify_backup
    assert "Project brief smoke skipped" in verify_backup
    assert "demo-website" not in verify_backup

    assert "Dry run only. No container or volume changes were made." in recover
    assert "Snapshot written" in recover
    assert "removed NUL-only postmaster.pid" in recover
    assert "compose rm -sf \"$DB_SERVICE\"" in recover
    assert "compose up -d \"$DB_SERVICE\"" in recover
    assert "run_agent_hub status" in recover
    assert "$ROOT_DIR/scripts/db_recover.sh --apply" in recover
    assert "$ROOT_DIR/scripts/db_start.sh if this is a new checkout." in recover

    for forbidden in ("docker volume rm", "DROP DATABASE", "DROP SCHEMA", "rm -rf"):
        assert forbidden not in doctor
        assert forbidden not in recover

    assert '"doctor"' in parser
    assert "run_doctor" in parser
    assert "db_doctor.sh" in system
    assert "agent-hub doctor" in readme
    assert "scripts/db_recover.sh --apply" in readme
    assert "never removes volumes or writes Hub memory" in workflow
    assert "`agent-hub doctor`" in boundaries
    assert "explicit local operator action" in boundaries
    assert "It must not delete volumes" in boundaries
    assert "drop databases" in boundaries
    assert "write Hub" in boundaries
    assert "doctor, migration" in architecture


def test_backup_verification_is_isolated_per_process_by_default() -> None:
    verify_backup = read_script("scripts/db_verify_backup.sh")

    assert 'central-agent-data-hub-backup-verify-$$' in verify_backup
    assert 'VERIFY_PORT="${AGENT_HUB_VERIFY_PORT:-}"' in verify_backup
    assert 'VERIFY_PORT_BINDING="127.0.0.1::5432"' in verify_backup
    assert 'docker port "$VERIFY_CONTAINER" 5432/tcp' in verify_backup
    assert 'VERIFY_PORT="${published_address##*:}"' in verify_backup
    assert 'central-agent-data-hub-backup-verify"' not in verify_backup
    assert 'AGENT_HUB_VERIFY_PORT:-55433' not in verify_backup


def test_public_demo_docs_use_demo_doctor_not_operator_doctor_for_first_run() -> None:
    readme = read_script("README.md")
    getting_started = read_script("docs/public/getting-started.md")
    demo_session = read_script("docs/public/first-run-demo-session.md")

    assert "run `scripts/db_doctor.sh --public-demo` if the demo Hub appears offline" in readme
    assert "scripts/db_doctor.sh --public-demo" in getting_started
    assert "scripts/db_doctor.sh --public-demo" in demo_session

    public_quickstart = readme.split("## Public Quickstart", 1)[1].split("## Agent Workflow", 1)[0]
    assert "agent-hub doctor" not in public_quickstart
    assert "agent-hub doctor\n# or, from this checkout:" not in getting_started
    assert "agent-hub doctor\n# or, from this checkout:" not in demo_session


def test_db_status_uses_fast_healthcheck_paths() -> None:
    status = read_script("scripts/db_status.sh")

    assert "compose_quick ps" in status
    assert "docker_quick volume inspect" in status
    assert "postgres_ready" in status
    assert "compose exec -T \"$DB_SERVICE\" pg_isready" not in status


def test_backup_health_keeps_remote_parity_explicit_not_default_blocking() -> None:
    backup_health = read_script("scripts/db_backup_health.sh")
    common = read_script("scripts/db_common.sh")
    verify_backup = read_script("scripts/db_verify_backup.sh")
    preflight = read_script("scripts/agent_preflight.sh")
    workflow = read_script("docs/agent-workflow.md")

    latest_backup = common.split("latest_backup_dump()", 1)[1].split("verify_backup_checksum()", 1)[0]
    assert "agent_hub-[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]" in latest_backup
    assert "-[0-9][0-9][0-9][0-9][0-9][0-9].dump" in latest_backup
    assert "-name 'agent_hub-*.dump'" in latest_backup
    assert latest_backup.index("-[0-9][0-9][0-9][0-9][0-9][0-9].dump") < latest_backup.index(
        "-name 'agent_hub-*.dump'"
    )
    assert 'dump_path="$(latest_backup_dump)"' in backup_health
    assert 'dump_path="$(latest_backup_dump)"' in verify_backup
    assert "--require-remote" in backup_health
    assert "AGENT_HUB_REQUIRE_REMOTE_BACKUP" in backup_health
    assert "mark_remote_problem()" in backup_health
    assert "Backup health:    ok (remote warning)" in backup_health
    assert "local backup checksum failed" in preflight
    assert "Remote backup parity can be made strict" in preflight
    assert "fresh verified local backup" in workflow
    assert "remote parity is" in workflow
    assert "strict only" in workflow
    assert "permits a narrower" in workflow
    assert "read-only fallback" in workflow
    assert "current agent runtime cannot inspect Docker" in workflow


def test_latest_backup_dump_prefers_timestamped_backups_and_allows_named_smoke_dump(tmp_path: Path) -> None:
    external_dump = tmp_path / "agent_hub-external-developer-demo.dump"
    timestamped_dump = tmp_path / "agent_hub-20260705-124118.dump"
    external_dump.write_text("external", encoding="utf-8")

    script = f"""
set -euo pipefail
export AGENT_HUB_BACKUP_DIR={shlex.quote(str(tmp_path))}
export AGENT_HUB_IGNORE_ENV_FILE=1
source scripts/db_common.sh
latest_backup_dump
"""
    result = subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.strip() == str(external_dump)

    timestamped_dump.write_text("timestamped", encoding="utf-8")
    result = subprocess.run(
        ["bash", "-lc", script],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert result.stdout.strip() == str(timestamped_dump)


def test_agent_finish_surfaces_question_answer_dry_run() -> None:
    finish = read_script("scripts/agent_finish.sh")

    assert "print_offline_finish_protocol()" in finish
    assert "== Offline Finish Protocol ==" in finish
    assert "No reviewed memory was written by this finish attempt." in finish
    assert "Do not mark Hub writeback, export, backup, or review-memory as complete." in finish
    assert "Keep the useful run summary in the current chat or working notes" in finish
    assert "AGENT_HUB_OFFLINE_FINISH_DIR" in finish
    assert "Offline Finish Recovery" in finish
    assert "reviewed_memory_written: no" in finish
    assert "export_completed: no" in finish
    assert "backup_completed: no" in finish
    assert "This file is a local recovery note only." in finish
    assert "Recovery note:" in finish
    assert "Retry:" in finish
    assert "scripts/project_answer_question.sh" in finish
    assert "scripts/project_update_decision.sh" in finish
    assert "--question-id <open-question-uuid>" in finish
    assert "--decision-id <decision-uuid>" in finish
    assert "after this finish step" in finish
    assert "agent-hub export directly" in finish
    assert "No unresolved open questions are currently visible for this project." in finish
    assert "No durable handoff is visible in this window" in finish
    assert "Export only if you write reviewed memory after this finish step." in finish
    assert "Backup only if you write or export important reviewed memory after this finish step." in finish
    assert "This finish step wrote a report; export now" in finish
    assert "Create and verify local/remote DB backup after finish." in finish
    assert "== Database Backup Verification ==" in finish
    assert "scripts/db_verify_backup.sh" in finish
    assert "database backup verification failed" in finish
    assert "This finish step wrote durable memory; run scripts/agent_finish.sh --project $PROJECT --review --backup" in finish


def test_project_update_decision_wrapper_has_change_guard() -> None:
    script = read_script("scripts/project_update_decision.sh")

    assert "--decision-id <uuid>" in script
    assert "--rationale <text>" in script
    assert "provide at least one change" in script
    assert "agent-hub update-decision" in script
    assert "Project decision update result: dry-run ok" in script


def test_agent_start_lock_error_points_to_status_and_force_lock() -> None:
    run_lock = read_script("scripts/agent_run_lock.sh")
    lock_status = read_script("scripts/agent_lock_status.sh")
    run_loop = read_script("docs/agent-run-loop.md")
    run_card = read_script("docs/agent-run-card.md")
    workflow = read_script("docs/agent-workflow.md")

    assert 'AGENT_HUB_RUN_LOCK_ROOT="${SHARED_ROOT:-$ROOT_DIR}"' in run_lock
    assert 'AGENT_HUB_RUN_LOCK_DIR="${AGENT_HUB_RUN_LOCK_ROOT}/.local/run-locks"' in run_lock
    assert "agent_run_lock_is_orphaned()" in run_lock
    assert '[[ -n "$repo" && ! -e "$repo" ]]' in run_lock
    assert "scripts/agent_lock_status.sh --repo" in run_lock
    assert "If this is your interrupted run, rerun agent_start.sh with --force-lock." in run_lock
    assert "--clean-orphaned" in lock_status
    assert "orphaned:" in lock_status
    assert "agent_run_lock_is_orphaned" in lock_status
    assert "rm -f \"$lock_path\"" in lock_status
    assert "Existing repo paths are never removed." in lock_status
    assert "scripts/agent_lock_status.sh --all --clean-orphaned" in run_loop
    assert "scripts/agent_lock_status.sh --all --clean-orphaned" in run_card
    assert "scripts/agent_lock_status.sh --all --clean-orphaned" in workflow


def test_agent_start_and_project_context_use_compact_preflight() -> None:
    start = read_script("scripts/agent_start.sh")
    context = read_script("scripts/project_context.sh")

    assert '"$ROOT_DIR/scripts/agent_preflight.sh" --compact --allow-direct-db' in start
    assert '"$ROOT_DIR/scripts/agent_preflight.sh" --compact' in context


def test_agent_start_runs_project_guard_before_lock() -> None:
    start = read_script("scripts/agent_start.sh")

    preflight_index = start.index('"$ROOT_DIR/scripts/agent_preflight.sh" --compact --allow-direct-db')
    guard_index = start.index('"$ROOT_DIR/scripts/agent_guard.sh" --project "$PROJECT" --cwd "$PWD"')
    lock_index = start.index("agent_run_lock_acquire")
    assert preflight_index < guard_index
    assert guard_index < lock_index


def test_agent_start_prints_context_receipt_before_compiled_memory() -> None:
    start = read_script("scripts/agent_start.sh")

    receipt = '"$PYTHON_BIN" -m agent_hub.context_receipt --project "$PROJECT" --task "$QUERY" --limit "$LIMIT"'
    assert receipt in start
    assert start.index(receipt) < start.index('"== Compiled Project Memory: $PROJECT =="')


def test_agent_guard_checks_project_paths_and_git_remote() -> None:
    guard = read_script("scripts/agent_guard.sh")

    assert "metadata.local_path" in guard
    assert "metadata.codex_workspace_root" in guard
    assert 'for key in ("local_path", "codex_workspace_root")' in guard
    assert "Agent guard: project/workdir mismatch." in guard
    assert "git_origin_url()" in guard
    assert 'reason:  $matched_reason' in guard


def test_schema_friction_wrapper_stores_marked_open_question() -> None:
    script = read_script("scripts/project_schema_friction.sh")

    assert "--type open-question" in script
    assert "--metadata schema_friction=true" in script
    assert "--metadata observed=" in script
    assert "--metadata why=" in script
    assert '"$ROOT_DIR/scripts/project_remember.sh"' in script


def test_public_demo_start_is_separate_from_maintainer_seed_path() -> None:
    script = read_script("scripts/db_start_public_demo.sh")

    assert "AGENT_HUB_PUBLIC_DEMO=1" in script
    assert "--dry-run" in script
    assert "Database:  $DB_NAME" in script
    assert 'echo "  scripts/smoke_public_demo.sh"' in script
    assert "AGENT_HUB_REVIEWERS=demo-reviewer" in script
    assert "HUB_VIEW_REVIEWER=demo-reviewer" in script
    assert 'apply_sql_file "seed/demo.sql"' in script
    assert "verify_public_demo_hygiene" in script
    assert 'run_agent_hub brief --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub compile --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub quality --project central-agent-data-hub-demo' in script
    assert 'apply_sql_file "seed/business_sites.sql"' not in script
    assert 'apply_sql_file "seed/agentic_projects.sql"' not in script


def test_public_demo_seed_is_neutral_and_public_safe() -> None:
    seed = read_script("seed/demo.sql")
    lower_seed = seed.lower()
    forbidden_terms = [
        "hermes",
        "reviewer-two",
        "telegram",
        "review_api",
        "review api",
        "demo-website",
        "demo-catering",
        "future-website",
        "smoke",
    ]

    for term in forbidden_terms:
        assert term not in lower_seed

    assert "Neutral demo project for showing how reviewed context is stored and read locally." in seed
    assert "Reviewed memory is context with a source and a review status" in seed
    assert "A Signal Inbox can hold interesting but unreviewed notes" in seed
    assert "demo_review_card" in seed
    assert '"assigned_reviewer": "demo-reviewer"' in seed
    assert "'draft'" in seed
    assert "Agents should use accepted demo memory as context" in seed
    assert "WHERE facts.id <> '00000000-0000-4000-8000-000000000203'" in seed
    assert "OR facts.status = 'draft';" in seed
    assert "Public Demo Context Report" in seed


def test_public_demo_start_refuses_stale_operator_artifacts_without_cleanup() -> None:
    script = read_script("scripts/db_start_public_demo.sh")

    assert "public demo database contains old smoke or operator traces" in script
    assert "This script will not clean or overwrite existing local data automatically." in script
    assert "Use a fresh isolated demo instance" in script
    assert "AGENT_HUB_COMPOSE_PROJECT_NAME=adh-demo-fresh" in script
    assert "AGENT_HUB_DB_VOLUME" in script
    assert "docker volume rm" not in script
    assert "DROP DATABASE" not in script
    assert "DROP SCHEMA" not in script
    assert "Findings:" not in script
    assert "table_name || ':' || item" not in script

    assert "non_demo_projects AS" in script
    assert "WHERE slug <> 'central-agent-data-hub-demo'" in script

    for term in ("'telegram'", "'review_api'", "'review api'", "'smoke'"):
        assert term in script

    for old_private_term in ("'hermes'", "'reviewer-two'", "'demo-website'", "'demo-catering'", "'future-website'"):
        assert old_private_term not in script


def test_first_run_demo_script_wraps_public_demo_path() -> None:
    path = ROOT / "scripts/first_run_demo.sh"
    script = read_script("scripts/first_run_demo.sh")

    assert path.exists()
    assert os.access(path, os.X_OK)
    assert "set -euo pipefail" in script
    assert "--no-hub-view" in script
    assert "install_fingerprint()" in script
    assert "local_cli_ready()" in script
    assert 'INSTALL_STAMP="$ROOT_DIR/.venv/.agent-data-hub-install"' in script
    assert '"$ROOT_DIR/.venv/bin/python" -m pip install -e "$ROOT_DIR"' in script
    assert "Using existing Agent Data Hub install in .venv" in script
    assert '"$ROOT_DIR/scripts/db_start_public_demo.sh"' in script
    assert '"$ROOT_DIR/scripts/smoke_public_demo.sh"' in script
    assert 'hub_view_host="127.0.0.1"' in script
    assert 'hub_view_args=(--host "$hub_view_host")' in script
    assert "hub_view_env=(AGENT_HUB_PUBLIC_DEMO=1)" in script
    assert "HUB_VIEW_REVIEWER=demo-reviewer" in script
    assert "AGENT_HUB_REVIEWERS=demo-reviewer" in script
    assert "Demo Review Inbox actions use reviewer" in script
    assert "This is local demo attribution, not authentication." in script
    assert '"$ROOT_DIR/scripts/hub_view.sh" "${hub_view_args[@]}"' in script
    assert "AGENT_HUB_PUBLIC_DEMO=1" in script
    assert "http://127.0.0.1:${hub_view_port}" in script
    assert "HUB_VIEW_PORT:-8765" in script


def test_first_run_demo_mobile_preview_is_explicit_and_non_loopback() -> None:
    script = read_script("scripts/first_run_demo.sh")
    readme = read_script("README.md")
    getting_started = read_script("docs/public/getting-started.md")
    boundaries = read_script("docs/automation-boundaries.md")

    assert "--mobile" in script
    assert "detect_lan_ip()" in script
    assert 'hub_view_host="0.0.0.0"' in script
    assert 'hub_view_args=(--host "$hub_view_host" --allow-lan-read)' in script
    assert "Open on a phone in the same Wi-Fi" in script
    assert "Use this only on a trusted local network." in script
    assert "Hub View read access is explicitly opened to the local network for this run." in script
    assert "Review and Codex setup actions stay disabled while mobile preview is active." in script
    assert "ipconfig getifaddr en0" in script

    assert "scripts/first_run_demo.sh --mobile" in readme
    assert "scripts/first_run_demo.sh --mobile" in getting_started
    assert "trusted Wi-Fi" in readme
    assert "trusted local network" in getting_started
    assert "--allow-lan-read" in readme
    assert "--allow-lan-read" in getting_started
    assert "Review Inbox and Codex setup writes" in getting_started
    assert "does not widen the write boundary" in boundaries
    assert "Review Inbox actions and Codex setup actions remain disabled" in boundaries
    assert "--allow-lan-read" in boundaries


def test_first_run_demo_preserves_existing_env_and_venv_contract() -> None:
    script = read_script("scripts/first_run_demo.sh")

    assert 'if [[ ! -f "$ROOT_DIR/.env" ]]' in script
    assert 'cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"' in script
    assert "Keeping existing .env" in script
    assert "source .venv/bin/activate" not in script
    assert ".venv/bin/activate" not in script
    assert "DOCKER_TIMEOUT_SECONDS" in script
    assert "run_with_timeout()" in script
    assert "Checking Docker..." in script
    assert "docker info" in script
    assert 'run_with_timeout "$DOCKER_TIMEOUT_SECONDS" docker info' in script
    assert "did not respond within" in script
    assert "Start or restart Docker Desktop" in script
    assert "sys.version_info >= (3, 11)" in script
    assert "distribution(\"central-agent-data-hub\")" in script
    assert "pyproject.toml" in script


def test_first_run_demo_stays_public_and_docs_reference_it() -> None:
    script = read_script("scripts/first_run_demo.sh")
    readme = read_script("README.md")
    getting_started = read_script("docs/public/getting-started.md")
    daily_use = read_script("docs/public/daily-use.md")

    for text in (script, readme, getting_started, daily_use):
        assert "demo-website" not in text
        assert "demo-catering" not in text
        assert "future-website" not in text

    assert "scripts/first_run_demo.sh" in readme
    assert "scripts/first_run_demo.sh" in getting_started
    assert "first-run-demo-session.md" in readme
    assert "first-run-demo-session.md" in getting_started
    assert "installs or reuses the local CLI" in readme
    assert "installs or reuses the local CLI" in getting_started
    assert "one neutral suggested memory change" in readme
    assert "one neutral suggested memory change" in getting_started
    assert "demo-reviewer" in readme
    assert "demo-reviewer" in getting_started
    assert "not authentication" in readme
    assert "not authentication" in getting_started


def test_public_daily_use_path_bridges_demo_to_real_project_loop() -> None:
    readme = read_script("README.md")
    getting_started = read_script("docs/public/getting-started.md")
    daily_use = read_script("docs/public/daily-use.md")

    assert "[`docs/public/daily-use.md`](docs/public/daily-use.md)" in readme
    assert "[`daily-use.md`](daily-use.md)" in getting_started
    assert "## After The Demo: Daily Local Use" in readme
    assert "register project -> connect agent -> start with reviewed context" in daily_use
    assert 'agent-hub register-project \\' in daily_use
    assert "scripts/register_project.sh" in daily_use
    assert "compatibility" in daily_use
    assert "scripts/install_repo_agent_memory.sh" in daily_use
    assert "agent-hub mcp-serve" in daily_use
    assert "scripts/agent_start.sh" in daily_use
    assert "agent-hub prepare" in daily_use
    assert "agent-hub inbox --accept <draft-id> --reviewer alice" in daily_use
    assert "scripts/agent_finish.sh --project <project-slug> --review" in daily_use
    assert "scripts/memory_receipt.sh --project <project-slug> --since 24h" in daily_use
    assert "agent-hub doctor" in daily_use
    assert "scripts/db_doctor.sh --public-demo" in daily_use
    assert "scripts/smoke_public_demo.sh" in daily_use
    assert "prepare context with Context Trail and" in daily_use
    assert "deterministic OKF export" in daily_use
    assert "there is no time-based auto-accept and no silent promotion" in daily_use
    assert "The goal is not to remember everything" in daily_use


def test_v06_definition_tracks_cli_first_bootstrap_contract() -> None:
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    definition = read_script("docs/public/v0.6-definition.md")
    v05_definition = read_script("docs/public/v0.5-definition.md")
    smoke = read_script("scripts/smoke_external_developer.sh")

    assert "[v0.6 definition](docs/public/v0.6-definition.md)" in readme
    assert "agent-hub register-project --repo /path/to/project" in readme
    assert "docs/public/v0.6-definition.md" in roadmap
    assert "Prefer `agent-hub register-project`" in roadmap
    assert "# v0.6 Definition" in definition
    assert "CLI-first real-project bootstrap" in definition
    assert "agent-hub register-project" in definition
    assert "scripts/register_project.sh" in definition
    assert "compatibility path" in definition
    assert "delegates to the CLI" in definition
    assert "agent-hub register-project" in v05_definition
    assert "run_agent_hub register-project" in smoke


def test_v07_definition_tracks_release_candidate_evidence() -> None:
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    checklist = read_script("docs/public/release-checklist.md")
    definition = read_script("docs/public/v0.7-definition.md")
    db_common = read_script("scripts/db_common.sh")
    release_check = read_script("scripts/release_candidate_check.sh")
    restore_drill = read_script("scripts/restore_drill.sh")

    assert "[`docs/public/v0.7-definition.md`](docs/public/v0.7-definition.md)" in readme
    assert "[v0.7 definition](docs/public/v0.7-definition.md)" in readme
    assert "docs/public/v0.7-definition.md" in roadmap
    assert "# v0.7 Definition" in definition
    assert "release candidate is evidence-led" in roadmap
    assert "Release Candidate Loop" in definition
    assert "scripts/smoke_public_demo.sh" in definition
    assert "scripts/db_start_public_demo.sh" in definition
    assert "scripts/smoke_external_developer.sh" in definition
    assert "scripts/smoke_trust_loop.sh" in definition
    assert "scripts/smoke_agent_offline.sh" in definition
    assert "scripts/upgrade_drill.sh" in definition
    assert "agent-hub status" in definition
    assert "agent-hub check" in definition
    assert "A green unit-test" in definition
    assert "not enough evidence for release readiness" in definition
    assert "production authentication or roles" in definition
    assert "write-capable MCP tools" in definition
    assert "separate behavioral" in checklist
    assert "scripts/release_candidate_check.sh" in checklist
    assert "scripts/release_candidate_check.sh" in definition
    assert "Release-candidate evidence check: ok" in release_check
    assert "AGENT_HUB_RELEASE_TMPDIR" in release_check
    assert "/var/tmp/agent-data-hub-release-candidate" in release_check
    assert 'mkdir -p "$TMPDIR"' in release_check
    assert "git -C \"$ROOT_DIR\" diff --check" in release_check
    assert 'bash -n "$ROOT_DIR"/scripts/*.sh' in release_check
    assert '"$PYTHON_BIN" -m compileall "$ROOT_DIR/agent_hub"' in release_check
    assert '"$PYTHON_BIN" -m pytest -q' in release_check
    assert "require_release_docker_runtime()" in release_check
    assert "Release Docker runtime gate:" in release_check
    assert "docker_quick info" in release_check
    assert "docker compose version" in release_check
    assert "restart Docker Desktop" in release_check
    assert "run_docker_step()" in release_check
    assert "-u DATABASE_URL" in release_check
    assert "AGENT_HUB_PUBLIC_DEMO=1" in release_check
    assert "-u OBSIDIAN_EXPORT_DIR" in release_check
    assert "-u AGENT_HUB_BACKUP_DIR" in release_check
    assert "-u AGENT_HUB_DB_CONTAINER" in release_check
    assert "-u AGENT_HUB_DB_VOLUME" in release_check
    assert "central-agent-data-hub-release-demo-postgres" in release_check
    assert "agent_hub_release_demo" in release_check
    assert "run_step \"Public demo startup\" run_docker_step run_public_demo_start" in release_check
    assert "run_step \"Public demo smoke\" run_docker_step run_public_demo_smoke" in release_check
    assert "run_step \"Public demo receipt\" run_docker_step run_public_demo_receipt" in release_check
    assert "scripts/memory_receipt.sh" in release_check
    assert "--project central-agent-data-hub-demo" in release_check
    assert "--type fact" in release_check
    assert "smoke_public_demo.sh" in release_check
    assert "db_start_public_demo.sh" in release_check
    assert "smoke_external_developer.sh" in release_check
    assert "smoke_trust_loop.sh" in release_check
    assert "smoke_agent_offline.sh" in release_check
    assert "upgrade_drill.sh" in release_check
    assert "run_step \"Upgrade drill\" run_docker_step clean_demo_env" in release_check
    assert "restore_drill.sh" in release_check
    assert "run_step \"Restore drill\" run_docker_step clean_demo_env" in release_check
    assert "AGENT_HUB_DB_CONTAINER" in restore_drill
    assert "central-agent-data-hub-restore-drill-postgres" in restore_drill
    assert "agent_hub_restore_demo" in restore_drill
    assert "scripts/db_backup.sh" in restore_drill
    assert "scripts/db_verify_backup.sh" in restore_drill
    assert "Restore drill: ok" in restore_drill
    assert "This script never targets the configured operator database." in restore_drill
    assert "AGENT_HUB_IGNORE_ENV_FILE=1" in restore_drill
    assert "unset AGENT_HUB_BACKUP_REMOTE" in restore_drill
    assert "never copies drill backups to a remote target" in restore_drill
    assert 'AGENT_HUB_IGNORE_ENV_FILE:-0' in db_common
    assert "run_step \"Agent Hub doctor\" run_agent_hub doctor" in release_check
    assert "run_agent_hub status" in release_check
    assert "run_agent_hub check" in release_check
    assert "git tag" not in release_check
    assert "gh release" not in release_check


def test_v10_definition_tracks_local_reliability_end_goal() -> None:
    ci = read_script(".github/workflows/ci.yml")
    readme = read_script("README.md")
    roadmap = read_script("ROADMAP.md")
    definition = read_script("docs/public/v1.0-definition.md")
    finish = read_script("scripts/agent_finish.sh")
    installation = read_script("docs/public/installation.md")
    protocol = read_script("docs/first-run-test-protocol.md")
    v1_readiness = read_script("scripts/v1_readiness_check.sh")

    assert "v1 readiness contract" in ci
    assert "scripts/v1_readiness_check.sh --contract-only" in ci
    assert "restore-drill" in ci
    assert "scripts/restore_drill.sh" in ci
    assert "human proof path that complements" in protocol
    assert "[`docs/public/v1.0-definition.md`](docs/public/v1.0-definition.md)" in readme
    assert "[v1.0 definition](docs/public/v1.0-definition.md)" in readme
    assert "docs/public/v1.0-definition.md" in roadmap
    assert "# v1.0 Definition" in definition
    assert "boringly reliable reviewed context infrastructure" in definition
    assert "verified context for humans and agents" in definition
    assert "scripts/v1_readiness_check.sh" in definition
    assert "scripts/release_candidate_check.sh" in definition
    assert "scripts/restore_drill.sh" in definition
    assert "docs/first-run-test-protocol.md" in definition
    assert "It does not replace the human proof" in definition
    assert "scripts/agent_finish.sh --project <project-slug> --review --export --backup" in definition
    assert "scripts/memory_receipt.sh --project <project-slug> --since 24h" in definition
    assert "agent-hub prepare --project <project-slug> --task \"<task>\" --format json" in definition
    assert "The readiness check must verify that this contract" in definition
    assert "restore drill" in definition
    assert "Backup completion" in definition
    assert "must mean a dump was written" in definition
    assert "latest timestamped local" in definition
    assert "backup was restored and checked" in definition
    assert "MCP remains read-only" in definition
    assert "Stale and orphaned run locks are visible" in definition
    assert "human observation proof" in definition
    assert "Observation notes stay local and outside Git" in definition
    assert "real person rather than maintainer memory" in definition
    assert "hosted SaaS" in definition
    assert "automatic promotion, demotion, or review" in definition
    assert "raw chats, secrets, private customer data" in definition
    assert "db_verify_backup.sh" in finish
    assert "v1.0 readiness check" in v1_readiness
    assert "--contract-only" in v1_readiness
    assert "scripts/v1_readiness_check.sh" in v1_readiness
    assert "scripts/release_candidate_check.sh" in v1_readiness
    assert "scripts/restore_drill.sh" in v1_readiness
    assert "docs/first-run-test-protocol.md" in v1_readiness
    assert "External-developer smoke" in v1_readiness
    assert "Restore drill" in v1_readiness
    assert "human proof path that complements" in v1_readiness
    assert "without maintainer memory" in v1_readiness
    assert "== Database Backup Verification ==" in v1_readiness
    assert "scripts/memory_receipt.sh" in v1_readiness
    assert "scripts/db_verify_backup.sh" in v1_readiness
    assert "reviewed_memory_written: no" in v1_readiness
    assert '"$RELEASE_CHECK"' in v1_readiness
    assert "clone is" in readme
    assert "installation, and `git pull`" in readme
    assert "native Windows is" in readme
    assert "not a supported target" in readme
    assert "clone is installation" in installation
    assert "git pull" in installation
    assert "`agent-hub` alone is not the full product surface" in installation


def test_register_project_script_is_cli_compatibility_wrapper() -> None:
    script = read_script("scripts/register_project.sh")

    assert "Compatibility wrapper" in script
    assert "agent-hub register-project" in script
    assert 'run_agent_hub register-project "$@"' in script
    assert "from agent_hub.project_registration import register_project" not in script
    assert "scripts/install_repo_agent_memory.sh" not in script
    assert "registered_by=\"scripts/register_project.sh\"" not in script


def test_public_demo_mode_forces_demo_database_when_database_url_is_set() -> None:
    env = os.environ.copy()
    env.pop("AGENT_HUB_DB_NAME", None)
    env.pop("AGENT_HUB_DB_PORT", None)
    env.pop("AGENT_HUB_DB_CONTAINER", None)
    env.pop("AGENT_HUB_DB_VOLUME", None)
    env.pop("AGENT_HUB_DB_USER", None)
    env["DATABASE_URL"] = "postgresql://postgres:secret@localhost:55432/agent_hub"

    result = subprocess.run(
        ["bash", "scripts/db_start_public_demo.sh", "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Database:  agent_hub_demo" in result.stdout
    assert "URL:       postgresql://postgres:***@localhost:55434/agent_hub_demo" in result.stdout
    assert "agent_hub\n" not in result.stdout
    assert "Dry run only. No Docker, migration, or seed command was run." in result.stdout


def test_public_demo_guard_refuses_non_demo_database_name() -> None:
    env = os.environ.copy()
    env["AGENT_HUB_DB_NAME"] = "agent_hub"
    env.pop("AGENT_HUB_DB_USER", None)

    result = subprocess.run(
        ["bash", "scripts/db_start_public_demo.sh", "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "expects a demo database name containing 'demo'" in result.stderr
    assert "Expected demo database name: agent_hub" in result.stderr
    assert "Effective database name: agent_hub" in result.stderr
    assert "postgresql://postgres:***@localhost" in result.stderr
    assert "secret" not in result.stderr


def test_public_demo_default_database_name_differs_from_ops_default() -> None:
    common = read_script("scripts/db_common.sh")

    assert 'PUBLIC_DEMO_DB_NAME="${AGENT_HUB_DB_NAME:-agent_hub_demo}"' in common
    assert 'DB_NAME="${AGENT_HUB_DB_NAME:-agent_hub}"' in common
    assert "require_demo_database_target" in common
    assert "configure_public_demo_database" in common
    assert "agent_hub_demo" != "agent_hub"


def test_public_demo_smoke_verifies_demo_exports() -> None:
    script = read_script("scripts/smoke_public_demo.sh")

    assert "AGENT_HUB_PUBLIC_DEMO=1" in script
    assert script.index('mkdir -p "$OBSIDIAN_EXPORT_DIR"') < script.index(
        "run_agent_hub status"
    )
    assert 'run_agent_hub brief --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub compile --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub quality --project central-agent-data-hub-demo' in script
    assert 'mkdir -p "$OBSIDIAN_EXPORT_DIR"' in script
    assert 'run_agent_hub export >/dev/null' in script
    assert "run_agent_hub prepare" in script
    assert '--task "review public demo reliability"' in script
    assert "--format json" in script
    assert "context_pack_version" in script
    assert "context_trail" in script
    assert "gap_summary" in script
    assert "deterministic_full_text" in script
    assert "## Known Gaps" in script
    assert "run_agent_hub export-okf --project central-agent-data-hub-demo" in script
    assert 'diff -ru "$okf_dir_one" "$okf_dir_two"' in script
    assert "Generated at" in script
    assert 'central-agent-data-hub-demo.md' in script
    assert 'Compiled/central-agent-data-hub-demo.md' in script
    assert 'HUB_VIEW_SMOKE_PORT:-9876' in script
    assert 'scripts/hub_view.sh" --host 127.0.0.1 --port "$hub_view_smoke_port"' in script
    assert "for _ in range(100)" in script
    assert "time.sleep(0.2)" in script
    assert "timeout=5" in script
    assert "TimeoutError" in script
    assert "AGENT_HUB_REVIEWERS=demo-reviewer" in script
    assert "HUB_VIEW_REVIEWER=demo-reviewer" in script
    assert "urllib.request" in script
    assert "local review surface" in script


def test_public_demo_smoke_does_not_write_durable_fake_memory() -> None:
    script = read_script("scripts/smoke_public_demo.sh")

    forbidden_write_markers = [
        " remember ",
        "project_remember",
        "review_draft",
        "inbox --accept",
        "inbox --reject",
        "INSERT INTO",
        "UPDATE ",
        "DELETE ",
    ]

    for marker in forbidden_write_markers:
        assert marker not in script


def test_public_hub_view_entrypoint_is_public_safe() -> None:
    script = read_script("scripts/hub_view.sh")

    assert "agent_preflight.sh" not in script
    assert "demo-website" not in script
    assert "demo-catering" not in script
    assert "run_agent_hub check" in script
    assert "scripts/db_start_public_demo.sh" in script
    assert "allow-lan-read" not in script
    assert 'exec "$PYTHON_BIN" -m agent_hub.hub_view "$@"' in script


def test_project_remember_dry_run_summary_python_is_shell_safe() -> None:
    script = read_script("scripts/project_remember.sh")

    assert 'print("Route:  {}".format(payload["tier"]))' in script
    assert 'print("Status: {}".format(payload["status"] or "default"))' in script
    assert 'print("Reason: {}".format(payload["reason"]))' in script
    assert 'payload[\\"tier\\"]' not in script
    assert 'payload[\\"status\\"]' not in script
    assert 'payload[\\"reason\\"]' not in script


def test_public_entrypoints_do_not_reference_maintainer_projects() -> None:
    public_scripts = [
        "scripts/hub_view.sh",
        "scripts/smoke_public_demo.sh",
        "scripts/project_context.sh",
        "scripts/agent_start.sh",
        "scripts/db_status.sh",
    ]

    for path in public_scripts:
        script = read_script(path)
        assert "demo-website" not in script
        assert "demo-catering" not in script

    project_context = read_script("scripts/project_context.sh")
    assert "metadata.project_type=website" in project_context
    assert 'load_project_slugs "website"' in project_context

    demo_start = read_script("scripts/db_start_public_demo.sh")
    assert "demo-website" not in demo_start
    assert "demo-catering" not in demo_start
    assert "apply_sql_file \"seed/business_sites.sql\"" not in demo_start
    assert "run_agent_hub brief --project demo-website" not in demo_start

    boundaries = read_script("docs/automation-boundaries.md")
    assert "likely private" not in boundaries
    assert "marks it as personal" in boundaries
    assert "never infers company or private status" in boundaries


def test_signal_inbox_init_script_is_lazy_by_default() -> None:
    script = read_script("scripts/init_signal_inbox.sh")

    assert "--path <directory>" in script
    assert "--scaffold-source <name>" in script
    assert 'write_file "$target_abs/README.md"' in script
    assert 'write_file "$target_abs/${source_slug}.md"' in script
    assert "create a source file only when the first real signal appears" in script
    assert "reviewed memory belongs in Agent Data Hub, not here" in script


def test_setup_assistant_stays_small_and_model_independent() -> None:
    script = read_script("scripts/setup_assistant.sh")

    assert "--dry-run" in script
    assert "--defaults" in script
    assert "Write this local setup now?" in script
    assert "Create a Signal Inbox?" in script
    assert "Include the public demo path in next steps?" in script
    assert "Use Hub View?" in script
    assert "Prepare a first real project registration?" in script
    assert "human or agent process" in script
    assert 'if [[ "$value" == "~" ]]' in script
    assert "none selected" in script
    assert "scripts/init_signal_inbox.sh" in script
    assert "run_agent_hub register-project" in script
    assert "agent-hub register-project" in script
    assert "does not write to Agent Data Hub memory" not in script
    assert "Hub model-independent" in script
