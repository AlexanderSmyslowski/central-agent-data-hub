from __future__ import annotations

from agent_hub import export_obsidian, import_obsidian
from agent_hub.exporting import helpers as export_helpers
from agent_hub.exporting import workflow as export_workflow
from agent_hub.importing import allowlist as import_allowlist
from agent_hub.importing import identity as import_identity
from agent_hub.importing import markdown as import_markdown_parser
from agent_hub.importing import workflow as import_workflow


def test_import_obsidian_facade_reexports_stable_public_helpers() -> None:
    assert import_obsidian.load_allowlist is import_allowlist.load_allowlist
    assert import_obsidian.iter_markdown_files is import_allowlist.iter_markdown_files
    assert import_obsidian.parse_markdown is import_markdown_parser.parse_markdown
    assert import_obsidian.contains_secret is import_markdown_parser.contains_secret
    assert import_obsidian.hash_payload is import_identity.hash_payload
    assert import_obsidian.import_markdown is import_workflow.import_markdown
    assert import_obsidian.sync_markdown is import_workflow.sync_markdown


def test_export_obsidian_facade_reexports_stable_public_helpers() -> None:
    assert export_obsidian.filename_for is export_helpers.filename_for
    assert export_obsidian.normalize_row is export_helpers.normalize_row
    assert export_obsidian.wikilink is export_helpers.wikilink
    assert export_obsidian.export_all is export_workflow.export_all
