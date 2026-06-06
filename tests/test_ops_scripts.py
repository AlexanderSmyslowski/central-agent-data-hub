from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_script(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_preflight_uses_bounded_docker_checks() -> None:
    common = read_script("scripts/db_common.sh")
    preflight = read_script("scripts/agent_preflight.sh")

    assert "run_with_timeout()" in common
    assert "AGENT_HUB_DOCKER_TIMEOUT_SECONDS" in common
    assert "COMPOSE_PROJECT_NAME" in common
    assert "COMMON_GIT_DIR" in common
    assert "SHARED_ROOT" in common
    assert 'git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir' in common
    assert "docker_quick()" in common
    assert "compose_quick()" in common
    assert "postgres_ready()" in common
    assert "pg_isready -h localhost -p \"$DB_PORT\"" in common
    assert 'docker compose -p "$COMPOSE_PROJECT_NAME" -f "$COMPOSE_FILE"' in common
    assert 'elif [[ -x "$SHARED_ROOT/.venv/bin/python"' in common
    assert 'elif [[ -f "$SHARED_ROOT/.env" ]]' in common
    assert 'OBSIDIAN_EXPORT_DIR="$SHARED_ROOT/$OBSIDIAN_EXPORT_DIR"' in common
    assert 'AGENT_HUB_BACKUP_DIR="$SHARED_ROOT/$AGENT_HUB_BACKUP_DIR"' in common

    assert "docker_quick inspect \"$DB_CONTAINER\"" in preflight
    assert "Der zentrale Agent Data Hub laeuft lokal gerade nicht." in preflight
    assert "Bitte Docker starten oder kurz warten" in preflight
    assert "docker is not responding within" in preflight
    assert "Restart Docker Desktop" in preflight
    assert "postgres_ready" in preflight
    assert "compose exec -T \"$DB_SERVICE\" pg_isready" not in preflight


def test_db_status_uses_fast_healthcheck_paths() -> None:
    status = read_script("scripts/db_status.sh")

    assert "compose_quick ps" in status
    assert "docker_quick volume inspect" in status
    assert "postgres_ready" in status
    assert "compose exec -T \"$DB_SERVICE\" pg_isready" not in status


def test_agent_finish_surfaces_question_answer_dry_run() -> None:
    finish = read_script("scripts/agent_finish.sh")

    assert "scripts/project_answer_question.sh" in finish
    assert "--question-id <open-question-uuid>" in finish
    assert "after this finish step" in finish
    assert "agent-hub export directly" in finish
    assert "No unresolved open questions are currently visible for this project." in finish
    assert "No durable handoff is visible in this window" in finish
    assert "Export only if you write reviewed memory after this finish step." in finish
    assert "Backup only if you write or export important reviewed memory after this finish step." in finish
    assert "This finish step wrote a report; export now" in finish
    assert "This finish step wrote durable memory; run scripts/db_backup.sh after export." in finish


def test_agent_start_lock_error_points_to_status_and_force_lock() -> None:
    run_lock = read_script("scripts/agent_run_lock.sh")

    assert 'AGENT_HUB_RUN_LOCK_ROOT="${SHARED_ROOT:-$ROOT_DIR}"' in run_lock
    assert 'AGENT_HUB_RUN_LOCK_DIR="${AGENT_HUB_RUN_LOCK_ROOT}/.local/run-locks"' in run_lock
    assert "scripts/agent_lock_status.sh --repo" in run_lock
    assert "If this is your interrupted run, rerun agent_start.sh with --force-lock." in run_lock


def test_agent_start_and_project_context_use_compact_preflight() -> None:
    start = read_script("scripts/agent_start.sh")
    context = read_script("scripts/project_context.sh")

    assert '"$ROOT_DIR/scripts/agent_preflight.sh" --compact' in start
    assert '"$ROOT_DIR/scripts/agent_preflight.sh" --compact' in context


def test_agent_start_runs_project_guard_before_lock() -> None:
    start = read_script("scripts/agent_start.sh")

    guard_index = start.index('"$ROOT_DIR/scripts/agent_guard.sh" --project "$PROJECT" --cwd "$PWD"')
    lock_index = start.index("agent_run_lock_acquire")
    assert guard_index < lock_index


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

    assert 'apply_sql_file "seed/demo.sql"' in script
    assert 'run_agent_hub brief --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub compile --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub quality --project central-agent-data-hub-demo' in script
    assert 'apply_sql_file "seed/business_sites.sql"' not in script
    assert 'apply_sql_file "seed/agentic_projects.sql"' not in script


def test_public_demo_smoke_verifies_demo_exports() -> None:
    script = read_script("scripts/smoke_public_demo.sh")

    assert 'run_agent_hub brief --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub compile --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub quality --project central-agent-data-hub-demo' in script
    assert 'run_agent_hub export >/dev/null' in script
    assert 'central-agent-data-hub-demo.md' in script
    assert 'Compiled/central-agent-data-hub-demo.md' in script
