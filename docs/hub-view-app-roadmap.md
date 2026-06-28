# Hub View App Roadmap

Hub View should become a local work app for Agent Data Hub, not a hosted
product shell. The app helps a human understand what reviewed project memory
exists, what still needs review, and what context is handed to a chatbot or
local agent before work starts.

## End State

Hub View is the human-facing local app for reviewed project memory:

- choose a project and understand its current work state
- inspect reviewed facts, decisions, risks, open questions, reports, and
  relations
- search the reviewed memory already visible in the project view
- review suggested memory changes through explicit accept/reject actions
- prepare and verify visible context handoffs for chatbots and local agents
- see quality, gaps, and review-health signals without treating them as
  automatic actions

PostgreSQL remains the source of truth. Hub View remains a local read surface
with the narrow review/write actions already documented for Draft accept/reject
and guarded Codex setup.

## Boundaries

Hub View must not become a second source of truth. It must not add background
agent execution, hosted access, auth/roles, or unreviewed auto-promotion.

Allowed directions:

- clearer navigation and app structure
- better project workbench hierarchy
- clearer Review Inbox interaction
- better agent handoff and connection checks
- clearer quality and current-work-state surfaces
- careful bilingual UI copy

Out of scope for this roadmap:

- schema changes just for UI polish
- background automation without explicit human gates
- hosted multi-user Hub View
- write actions beyond the documented review boundaries

## Loops

1. App shell and navigation: a persistent app navigation layer, clear locations,
   and no dead-feeling primary surfaces.
2. Project workbench hierarchy: make current state, memory, review, agent
   handoff, and quality feel like first-class app areas.
3. Review Inbox: make the review queue easier to scan, decide, and audit while
   keeping accept/reject explicit.
4. Agent connection: make chatbot, Codex, Claude Code, Hermes, and generic MCP
   handoffs easier to set up and verify.
5. Quality and gaps: help humans see missing or stale context without automatic
   demotion or hidden writes.
6. Polish: mobile ergonomics, accessibility, and bilingual terminology.

## Done Criteria

For each loop, the app should be better for a first-time local user without
weakening ADH boundaries:

- the user knows where they are
- visible actions either work or clearly explain why they cannot
- mobile layout remains usable
- English and German labels stay consistent
- automated checks cover the new orientation signal
- no new silent write path is introduced
