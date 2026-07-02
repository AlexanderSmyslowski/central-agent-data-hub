# Agent Data Hub announcement pack

reviewed context for humans and agents

This file collects a small set of public-facing texts for the first open-source
release. The goal is clarity, not marketing volume.

## Short description

Agent Data Hub is a local-first system for reviewed project memory, compact
agent start context, and human-readable review surfaces.

## Plain-language explanation

Most agents work from scattered chats, partial notes, and stale assumptions.
Agent Data Hub gives them a smaller reviewed starting point and gives humans a
clear way to inspect what is actually known.

It separates three things:

- reviewed memory in PostgreSQL
- working context for one agent run
- working rules in repo-local files such as `AGENTS.md`

It can project reviewed memory into Markdown/Obsidian and show the same state
in a small local review app called Hub View.

## X / short post

Released Agent Data Hub v0.1.0.

It is a small local-first system for reviewed project memory, compact agent
start context, and human-readable review surfaces.

The aim is simple: less scattered chat memory, clearer project boundaries, and
a calmer way for humans to inspect what agents are actually working from.

Repo: https://github.com/AlexanderSmyslowski/central-agent-data-hub
Release: https://github.com/AlexanderSmyslowski/central-agent-data-hub/releases/tag/v0.1.0

## GitHub / longer post

Released Agent Data Hub v0.1.0.

Agent Data Hub is an early local-first reviewed-context system for humans and
agents.

It is built around a simple distinction:

- reviewed memory belongs in PostgreSQL
- working context should be compact
- working rules belong in repo-local instructions and project documents

The current public release includes:

- reviewed memory for facts, decisions, risks, open questions, reports, and relations
- disciplined start/finish wrappers for agent runs
- quality checks, receipts, and backup verification
- Markdown/Obsidian projection
- Hub View as a local review surface
- a neutral public demo path for first-time evaluation

Recommended first run:

```bash
scripts/db_start_public_demo.sh
scripts/smoke_public_demo.sh
scripts/hub_view.sh
```

Repo: https://github.com/AlexanderSmyslowski/central-agent-data-hub
Release notes: https://github.com/AlexanderSmyslowski/central-agent-data-hub/releases/tag/v0.1.0

## What to avoid saying

- Do not present this as a finished hosted product.
- Do not describe it as a raw chat-memory store.
- Do not imply autonomous schema creation.
- Do not oversell Hub View as the operational source of truth.

## Current honest framing

Agent Data Hub is a small serious v0.1 local-first system for reviewed context.
It is suitable for technical evaluation, local experiments, and disciplined
agent workflows. It is not yet a broad end-user product.
