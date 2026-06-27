import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_script(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


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
    assert "This finish step wrote durable memory; run scripts/db_backup.sh after export." in finish


def test_project_update_decision_wrapper_has_change_guard() -> None:
    script = read_script("scripts/project_update_decision.sh")

    assert "--decision-id <uuid>" in script
    assert "--rationale <text>" in script
    assert "provide at least one change" in script
    assert "agent-hub update-decision" in script
    assert "Project decision update result: dry-run ok" in script


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
    assert 'echo "  AGENT_HUB_PUBLIC_DEMO=1 scripts/hub_view.sh"' in script
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
        "ronak",
        "telegram",
        "review_api",
        "review api",
        "commcats-de",
        "the-one-catering",
        "lamour",
        "smoke",
    ]

    for term in forbidden_terms:
        assert term not in lower_seed

    assert "Neutral demo project for showing how reviewed context is stored and read locally." in seed
    assert "Reviewed memory is context with a source and a review status" in seed
    assert "A Signal Inbox can hold interesting but unreviewed notes" in seed
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

    for term in (
        "'hermes'",
        "'ronak'",
        "'telegram'",
        "'review_api'",
        "'commcats-de'",
        "'the-one-catering'",
        "'lamour'",
        "'smoke'",
    ):
        assert term in script


def test_first_run_demo_script_wraps_public_demo_path() -> None:
    path = ROOT / "scripts/first_run_demo.sh"
    script = read_script("scripts/first_run_demo.sh")

    assert path.exists()
    assert os.access(path, os.X_OK)
    assert "set -euo pipefail" in script
    assert "--no-hub-view" in script
    assert '"$ROOT_DIR/.venv/bin/python" -m pip install -e "$ROOT_DIR"' in script
    assert '"$ROOT_DIR/scripts/db_start_public_demo.sh"' in script
    assert '"$ROOT_DIR/scripts/smoke_public_demo.sh"' in script
    assert '"$ROOT_DIR/scripts/hub_view.sh" --host 127.0.0.1' in script
    assert "AGENT_HUB_PUBLIC_DEMO=1" in script
    assert "http://127.0.0.1:${hub_view_port}" in script
    assert "HUB_VIEW_PORT:-8765" in script


def test_first_run_demo_preserves_existing_env_and_venv_contract() -> None:
    script = read_script("scripts/first_run_demo.sh")

    assert 'if [[ ! -f "$ROOT_DIR/.env" ]]' in script
    assert 'cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"' in script
    assert "Keeping existing .env" in script
    assert "source .venv/bin/activate" not in script
    assert ".venv/bin/activate" not in script
    assert "docker info" in script
    assert "sys.version_info >= (3, 11)" in script


def test_first_run_demo_stays_public_and_docs_reference_it() -> None:
    script = read_script("scripts/first_run_demo.sh")
    readme = read_script("README.md")
    getting_started = read_script("docs/public/getting-started.md")

    for text in (script, readme, getting_started):
        assert "commcats-de" not in text
        assert "the-one-catering" not in text
        assert "lamour" not in text

    assert "scripts/first_run_demo.sh" in readme
    assert "scripts/first_run_demo.sh" in getting_started


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
    assert 'run_agent_hub brief --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub compile --project central-agent-data-hub-demo --limit 4' in script
    assert 'run_agent_hub quality --project central-agent-data-hub-demo' in script
    assert 'run_agent_hub export >/dev/null' in script
    assert 'central-agent-data-hub-demo.md' in script
    assert 'Compiled/central-agent-data-hub-demo.md' in script
    assert 'HUB_VIEW_SMOKE_PORT:-9876' in script
    assert 'scripts/hub_view.sh" --host 127.0.0.1 --port "$hub_view_smoke_port"' in script
    assert 'AGENT_HUB_PUBLIC_DEMO=1 "$ROOT_DIR/scripts/hub_view.sh"' in script
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
    assert "commcats-de" not in script
    assert "the-one-catering" not in script
    assert "run_agent_hub check" in script
    assert "scripts/db_start_public_demo.sh" in script
    assert 'exec "$PYTHON_BIN" -m agent_hub.hub_view "$@"' in script


def test_public_entrypoints_do_not_reference_maintainer_projects() -> None:
    public_scripts = [
        "scripts/hub_view.sh",
        "scripts/smoke_public_demo.sh",
    ]

    for path in public_scripts:
        script = read_script(path)
        assert "commcats-de" not in script
        assert "the-one-catering" not in script

    demo_start = read_script("scripts/db_start_public_demo.sh")
    assert "apply_sql_file \"seed/business_sites.sql\"" not in demo_start
    assert "run_agent_hub brief --project commcats-de" not in demo_start


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
    assert "scripts/register_project.sh" in script
    assert "does not write to Agent Data Hub memory" not in script
    assert "Hub model-independent" in script
