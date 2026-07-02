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

    assert "`demo.sql` is the neutral public demo dataset" in seed_readme
    assert "`business_sites.sql` and `agentic_projects.sql` are maintainer-local operator" in seed_readme
    assert "scripts/db_start_public_demo.sh" in seed_readme
    assert "scripts/first_run_demo.sh" in seed_readme
    assert "scripts/db_start.sh" in seed_readme
    assert "not part of the public first-run path" in seed_readme
    assert "Do not add secrets" in seed_readme
    assert "[`seed/README.md`](seed/README.md)" in readme


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
    assert "maintainer-local operator seeds" in notes
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


def test_package_version_is_ready_for_next_public_patch_release() -> None:
    pyproject = read_script("pyproject.toml")
    checklist = read_script("docs/public/release-checklist.md")
    readme = read_script("README.md")

    assert 'version = "0.1.20"' in pyproject
    assert "[v0.1.20 release notes](docs/public/v0.1.20-release-notes.md)" in readme
    assert "version` matches the tag" in checklist
    assert "Do not move an already published tag" in checklist
    assert "[Release checklist](docs/public/release-checklist.md)" in readme


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
    assert "Native Windows is not a supported v0.2 target" in installation
    assert "A regular `pip install` can expose importable Python modules" in installation
    assert "checkout_script_path" in system
    assert "requires an Agent Data Hub repository checkout" in system


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

    assert "run_with_timeout()" in common
    assert "AGENT_HUB_DOCKER_TIMEOUT_SECONDS" in common
    assert "AGENT_HUB_DB_START_TIMEOUT_SECONDS" in common
    assert "COMPOSE_PROJECT_NAME" in common
    assert "COMMON_GIT_DIR" in common
    assert "SHARED_ROOT" in common
    assert 'git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir' in common
    assert "docker_quick()" in common
    assert "compose_quick()" in common
    assert "postgres_ready()" in common
    assert "postgres_container_state()" in common
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


def test_db_doctor_and_recover_are_safe_local_ops_paths() -> None:
    doctor = read_script("scripts/db_doctor.sh")
    recover = read_script("scripts/db_recover.sh")
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
    preflight = read_script("scripts/agent_preflight.sh")
    workflow = read_script("docs/agent-workflow.md")

    assert "--require-remote" in backup_health
    assert "AGENT_HUB_REQUIRE_REMOTE_BACKUP" in backup_health
    assert "mark_remote_problem()" in backup_health
    assert "Backup health:    ok (remote warning)" in backup_health
    assert "local backup checksum failed" in preflight
    assert "Remote backup parity can be made strict" in preflight
    assert "fresh verified local backup" in workflow
    assert "remote parity is" in workflow
    assert "strict only" in workflow


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
        assert "commcats-de" not in text
        assert "the-one-catering" not in text
        assert "lamour" not in text

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
    assert "scripts/register_project.sh" in daily_use
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
    assert "commcats-de" not in script
    assert "the-one-catering" not in script
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
