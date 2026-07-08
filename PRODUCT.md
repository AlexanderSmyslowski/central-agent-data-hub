# Product

## Register

product

## Users

Agent Data Hub is used by technical operators, maintainers, and project
decision-makers who work with local agents and need to see what context is
already reviewed, what still needs review, and which project boundary an agent
should respect before work starts.

## Product Purpose

Agent Data Hub is a local-first reviewed-context system for humans and agents.
It stores durable project memory in PostgreSQL, keeps unreviewed input separate
as drafts or signals, and exposes reviewed context through CLI, MCP, Markdown,
and Hub View. Success means a user can understand the current workspace, hand a
task-specific context pack to an agent, review proposed memory explicitly, and
trust that no silent promotion happened.

## Brand Personality

Clear, careful, and operational. The interface should feel like a serious local
tool: calm enough for repeated use, explicit about boundaries, and honest about
what is reviewed, unreviewed, demo-only, or missing.

## Anti-references

Avoid marketing dashboards, "company brain" overclaiming, decorative card
grids, AI-workflow theater, hidden review state, and interfaces that bury risks
or drafts behind happy metrics. Hub View should not look like a SaaS landing
page, a generic analytics wall, or a chat-memory grabber.

## Design Principles

- Show trust state before volume: reviewed, draft, risk, empty, and demo status
  matter more than raw counts.
- Make project boundaries visible so agents and humans do not mix unrelated
  work.
- Prefer compact comparison over decoration when a user is deciding where to
  look next.
- Keep write boundaries obvious: reading is broad; promotion requires explicit
  human review.
- Treat missing knowledge as useful information rather than hiding it.

## Accessibility & Inclusion

Target WCAG 2.1 AA for contrast, focus visibility, keyboard navigation, and
responsive layout. Product screens should remain usable on narrow mobile
viewports for read-only inspection, with no text overflow and no motion that is
required to understand state.
