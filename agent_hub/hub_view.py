"""Local review surface for Agent Data Hub."""

from __future__ import annotations

from pathlib import Path

from agent_hub.commands.common import fetch_project
from agent_hub.commands.inbox import review_draft_by_id
from agent_hub.commands.prepare import prepare_markdown
from agent_hub.db import connect
from agent_hub.hub_view_models import (
    DEFAULT_AGENT_TASK,
    build_agent_context_view,
    build_codex_setup_view,
    build_detail_view,
    build_project_card,
    build_project_cards,
    draft_card,
    draft_counts_by_project,
    fetch_active_projects,
    fetch_latest_reports_by_project,
    fetch_latest_report,
    fetch_project_card_counts,
    fetch_recent_review_actions,
    format_timestamp,
    group_draft_cards,
    hub_view_templates_dir,
    known_project_local_path,
    load_agent_context_view_model,
    load_environment,
    load_inbox_view_model,
    load_review_activity_view_model,
    load_view_model,
    metadata_project_local_path,
    render_page,
    review_activity_cards,
    shell_command,
    translate_card_line_for_ui,
)
from agent_hub.repo_agent_memory import install_repo_agent_memory, plan_repo_agent_memory
from agent_hub.hub_view_server import (
    HubViewApplication,
    agent_context_redirect,
    application,
    build_parser,
    create_application,
    html_response,
    inbox_redirect,
    is_loopback_host,
    main,
    origin_is_loopback,
    port_is_available,
    project_action_slug,
    query_value,
    read_post_form,
    redirect_response,
    text_response,
    validate_lan_read_bind,
)


if __name__ == "__main__":
    raise SystemExit(main())
