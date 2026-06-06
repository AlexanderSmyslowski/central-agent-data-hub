# Signal Inbox

The Signal Inbox is the controlled input layer in front of Agent Data Hub.

It exists for one practical reason: useful signals often appear before anyone
knows whether they belong in durable project memory.

Examples:

- X or Twitter research
- Gmail observations
- notes from Hermes or Codex chats
- links, screenshots, and external findings
- half-formed product ideas

These are inputs, not reviewed memory.

## The Three Layers

Keep the layers separate:

1. `Signal Inbox`
   Unreviewed inputs that might matter later.

2. `Triage`
   A human or supervising agent checks what each signal means.

3. `Agent Data Hub`
   Only reviewed, project-bound memory is promoted here.

The Hub stays small only if this boundary stays strict.

## What Belongs Here

The Signal Inbox is appropriate for:

- interesting but unverified findings
- project hints that still need classification
- external links worth a second look
- research that may become a fact, risk, question, or skill hint

The Signal Inbox is not appropriate for:

- secrets
- tokens or passwords
- private customer data
- raw logs
- raw invoices
- automatic writeback into PostgreSQL

## Recommended Structure

Use a human-readable wiki path outside the Hub repo, for example:

```text
/path/to/wiki/inbox/signals/
  README.md
  x-research/
    inbox.md
  gmail/
    inbox.md
  codex/
    inbox.md
  hermes/
    inbox.md
  web-research/
    inbox.md
  triage/
    queue.md
    reviewed.md
    prompt.md
```

This keeps inputs grouped by source, while keeping triage separate from raw
capture.

If an existing source already writes elsewhere, do not force an abrupt move.
Treat that file as a legacy input until the source can be pointed at the new
folder structure.

Example:

- existing `x-research-inbox.md` may remain in place until the X research agent
  is updated
- future X research entries should go to `signals/x-research/inbox.md`

## Signal Entry Shape

Each signal should stay short and predictable:

```markdown
## 2026-06-06 21:00 CEST
- source: x-research
- link: https://example.com/post
- summary: One or two lines about the finding.
- why_interesting: Why it may matter.
- project_hint: central-agent-data-hub
- triage_hint: skill_candidate
- sensitivity: public
- status: new
```

Preferred values:

- `triage_hint`: `ignore`, `keep_in_wiki`, `open_question`,
  `fact_candidate`, `decision_candidate`, `risk_candidate`,
  `skill_candidate`, `project_note`, `needs_human_review`
- `sensitivity`: `public`, `internal`, `sensitive`
- `status`: `new`, `triaged`, `ignored`, `promoted`

The entry is still only a signal. The hint is not a decision.

## Triage Rules

The triage layer should make recommendations, not silent memory writes.

For each signal, the reviewer asks:

- Is this relevant at all?
- Which project does it belong to, if any?
- Is it only useful as wiki research?
- Does it point to a real open question?
- Does it support a future fact, decision, or risk?
- Is it really a memory item, or actually a skill or working-rule candidate?

The normal outcomes are:

- `ignore`
- `keep in wiki`
- `promote to open question`
- `promote to reviewed memory candidate`
- `treat as skill or policy candidate`
- `needs human review`

## Relationship To Agent Data Hub

The Signal Inbox is upstream from the Hub.

That means:

- no Signal Inbox data is automatically imported into PostgreSQL
- no new database tables are required for the first version
- the Hub remains the reviewed operational source of truth
- Obsidian and Hub View remain reading and review surfaces

Only the result of triage may become reviewed memory.

## Minimal First Implementation

The first implementation should stay simple:

- a documented folder structure
- a predictable signal-entry template
- a triage prompt or runbook
- a small initializer script

That is enough to connect Hermes, Codex, and outside research without turning
the Hub into a catch-all notebook.
