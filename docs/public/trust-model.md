# Trust Model

Agent Data Hub is a reviewed context system.

Reviewed memory means:

- a human or approved local review path accepted the item
- the item carries a type, status, source, and project boundary
- review actions are explicit and auditable where drafts are accepted or rejected
- agents can see context trails, gaps, and review status before using the item

Reviewed memory does not mean:

- ADH does not prove the real-world claim is objectively true
- the item is complete or current forever
- the reviewer cannot be wrong
- an agent definitely read or followed the context
- unreviewed signals are safe to use as facts

## Status Names

Facts can still have the database status `verified`. That is a domain status
inside ADH's reviewed-memory model. It should be read as "accepted as a reviewed
fact for this project", not as a universal truth guarantee.

## Context-Pack Compatibility

The JSON context-pack key `verified_project_state` remains part of
`context_pack_version: 1`. It is kept for compatibility with existing consumers.
Treat that key as reviewed project-state facts from ADH.

Changing the key name would require a future context-pack version bump. The
current public wording uses "reviewed" to avoid overstating what ADH can prove.
