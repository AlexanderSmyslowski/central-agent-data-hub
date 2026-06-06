# Agent Data Hub Overview

Agent Data Hub is a local reviewed context system for humans and agents.

It exists because ordinary chat memory is often too opaque for serious project
work. Context gets mixed, old assumptions linger, and it is hard to see what is
actually known. Agent Data Hub turns that into a smaller, inspectable workflow.

## The Basic Shape

Agent Data Hub has three parts:

- **Reviewed memory** lives in PostgreSQL.
- **Working context** is compiled for each agent run.
- **Working rules** stay in repo-local instructions such as `AGENTS.md`, skills,
  and project documents.

That split matters. It keeps the Hub from becoming a dump for every instruction
or every chat fragment.

## What It Stores

The durable memory layer stores a controlled set of project objects:

- facts
- decisions
- risks
- open questions
- reports
- relations
- agent actions for auditability

Each object is meant to be reviewed, project-bound, and non-sensitive.

## What It Does Not Store

Agent Data Hub is intentionally narrow. It should not store:

- raw chat logs
- passwords, API keys, tokens, or FTP credentials
- private customer data
- raw invoice data
- deployment secrets
- speculative or cross-project claims

## How Agents Use It

An agent starts with a compact brief:

```bash
scripts/agent_start.sh --project <project-slug> --query "<current focus>" --review
```

That start step loads reviewed project context, checks project boundaries, and
prints a working contract for the run.

After the work, the agent finishes with:

```bash
scripts/agent_finish.sh --project <project-slug> --review
```

Only useful, reviewed residue should be written back.

## How Humans Use It

Humans can inspect the same memory in two calmer forms:

- Markdown and Obsidian projection for reading and graph navigation
- Hub View as a small local read-only interface

These are review surfaces. They are not the operational source of truth.

## Why This Is Different From Normal Chat Memory

Normal chat memory is easy to use, but hard to verify. Agent Data Hub adds:

- explicit project boundaries
- reviewed writeback
- quality checks
- receipts
- backups
- human-readable projection

The goal is not more memory. The goal is better context.

## Technical Preview Status

Agent Data Hub is already useful for local operator workflows, but it should be
understood as an early local-first technical preview rather than a finished
general-purpose product.
