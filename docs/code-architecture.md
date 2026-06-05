# Code Architecture

This note describes the current Python module boundaries. It is intentionally
short: the code should stay easier to read than the document that explains it.

## Guiding Rule

Keep the Hub small, explicit, and boring:

- PostgreSQL stores the **Gedächtnis**: reviewed project facts, decisions,
  risks, open questions, reports, and relations.
- Start, compile, and context commands assemble the **Arbeitskontext** for one
  run.
- Skills, `AGENTS.md`, and repo documents hold the **Arbeitsregeln**.
- Obsidian and Hub View are read/review surfaces, not competing sources of
  truth.
- CLI commands orchestrate workflows; they should not hide domain logic.
- Domain modules own domain rules.
- Compatibility facades are allowed when they keep public imports stable.

Before adding another layer, ask whether it makes daily agent work simpler,
safer, or easier to review. If not, leave the code alone.

## CLI Boundary

`agent_hub/cli.py` is the public entrypoint for the console script:

```text
agent-hub = agent_hub.cli:main
```

It should stay thin. Command registration lives in `agent_hub/commands/parser.py`.
Command handlers live in focused command modules:

- `commands/system.py`: status, check, migration, export, project listing.
- `commands/read.py`: read-only entrypoints and dispatch.
- `commands/briefs.py`: brief and compiled project memory.
- `commands/summaries.py`: daily, handoff, and review summaries.
- `commands/search.py`: search and context packs.
- `commands/quality_views.py`: quality and receipt views.
- `commands/write.py`: remember, import, and sync command handlers.
- `commands/graph.py`: relation read/write command handlers.
- `commands/common.py`: parser validators, formatting, and shared CLI helpers.

CLI modules may format output and call domain functions. They should avoid
large SQL bodies or business rules when a domain module can own them.

## Import Boundary

`agent_hub/import_obsidian.py` is a compatibility facade. New import and sync
work should go into `agent_hub/importing/`.

The importing package is split by responsibility:

- `models.py`: dataclasses used across import and sync workflows.
- `constants.py`: allowed types, fields, statuses, and safety patterns.
- `allowlist.py`: allowlist loading, root checks, and Markdown discovery.
- `markdown.py`: frontmatter parsing, safety scan, and item normalization.
- `identity.py`: import keys, data hashes, import metadata, and field diffs.
- `store.py`: database reads/writes and audit rows.
- `workflow.py`: import, sync, and sync-event orchestration.

The desired dependency shape is simple: parsing and identity code should not
know about database writes; store code should not parse Markdown; workflow code
is the place where those pieces meet.

## Export Boundary

`agent_hub/export_obsidian.py` is also a compatibility facade. Export logic
lives in `agent_hub/exporting/`.

The exporting package is split by output concern:

- `specs.py`: export specifications for memory tables.
- `helpers.py`: file names, titles, frontmatter, and human-note preservation.
- `relations.py`: relation collection and Obsidian Wikilink rendering.
- `overviews.py`: compiled project pages and the Hub start page.
- `workflow.py`: `export_all()` orchestration.

The export pipeline should preserve existing file names, frontmatter, human
notes, and Wikilink behavior unless a change is deliberate and tested.

## What Not To Split Yet

`rendering.py`, `retrieval.py`, and `quality.py` are still compact enough to
stay whole. Split them only when a smaller module would have an obvious name,
clear ownership, and tests that make the behavior safer.

Do not split code just to lower line counts. A good module boundary should make
the next bug easier to find.

## Test Shape

Tests should follow behavior, not internal cleverness:

- CLI behavior remains tested through `agent_hub.cli.main`.
- Import allowlist, Markdown parsing, workflow, and sync behavior have separate
  tests.
- Facades may be tested lightly for compatibility, but domain behavior belongs
  near the owning package.

When moving code, preserve command names, arguments, exit codes, JSON shapes,
text output, file names, and export behavior.
