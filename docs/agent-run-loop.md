# Agent Run Loop

Agent Data Hub should support better self-management without becoming a raw
thread log. The unit of improvement is a reviewed work run: one project, one
focus, one handoff, and only the useful residue saved as memory.

## Current Mechanism

Use the existing workflow:

```bash
scripts/agent_start.sh --project <project-slug> --query "<focus>" --review
scripts/agent_finish.sh --project <project-slug> --review --export --backup --run-id <id-from-start>
```

With `--backup`, the finish wrapper creates a backup and immediately verifies
the latest timestamped local dump with a restore smoke.

If `agent_finish.sh` cannot reach the local Hub, it must stop before any
reviewed writeback, export, or backup claim and print the Offline Finish
Protocol. It also writes a local recovery note under
`.local/offline-finish/` with the retry command and explicit
`reviewed_memory_written: no`, `export_completed: no`, and
`backup_completed: no` markers. That file is a local note only, not Hub memory.
Keep the run summary outside the Hub, restore the local database with the
documented doctor/start path, then rerun the same finish command.

To inspect recent audited agent writes and system actions:

```bash
agent-hub actions --project <project-slug> --since 7d
```

This reads the existing `agent_actions` table. It does not create a new session
table and it does not make `agent_start.sh` write to the database.

For single-project work, `agent_start.sh` creates a local worktree lock under
`SHARED_ROOT/.local/run-locks/`. Its key remains the SHA-256 of the canonical
physical worktree root: symlink aliases collide, separate worktrees do not.
Every successful locked start prints a new `run_id` and a safely quoted finish
command. Keep that caller-owned ID for the run:

```bash
scripts/agent_finish.sh --project <project-slug> --review --run-id <id-from-start>
```

Finish checks project, canonical repo and the caller-supplied ID before any
finish operations, then compares the exact snapshot again under the mutation
guard before releasing. It never borrows an ID from a lock file. Summary,
review, export, backup or action failures retain the lock and return nonzero.
An interrupted start cleans up only its own unchanged snapshot. `--no-lock`
creates/releases no lock; use it explicitly at both ends of an unlocked run.
Offline retry commands preserve the caller ID or `--no-lock` and quote arguments.
Older instructions that omit both options must be updated; use the finish command
printed by the matching start. The wrappers do not write memory or session rows.

Before the lock, the agent guard checks the selected project against the current
working directory. For parallel work, use a separate git worktree.

### Inspect and recover one lock

These commands are read-only, including when no lock directory exists:

```bash
scripts/agent_lock_status.sh --repo /path/to/project
scripts/agent_lock_status.sh --all
scripts/agent_lock_recover.sh --repo /path/to/project
```

Status emits JSON containing the exact lock path/key, SHA-256 digest, metadata,
and one of `owned/active`, `ownerless/legacy`, `unknown-owner` or `dead-owner`.
An absent lock is `unlocked`. A single-lock status exits 1 for a present lock,
0 when absent, and 2 on a read/usage error; `--all` exits 0 after listing. `stale`
and `orphaned` are independent boolean annotations (unknown is JSON `null`).
Age or a missing repo never proves death and never permits automatic removal.
Malformed metadata is reported as unknown and cannot be recovered by this tool;
symlink/nonregular targets fail closed. All existing entries block acquisition.

After inspecting the exact snapshot, resolve whether the run can still be working.
Recovery requires a full digest and explicit reason. Legacy ownership additionally
requires `--acknowledge-legacy`; unknown ownership requires `--acknowledge-unknown`.
Neither acknowledgement overrides an active owner or corrupt metadata.

```bash
scripts/agent_lock_recover.sh --repo /path/to/project \
  --digest <full-sha256-from-preview> --reason '<reviewed reason>' \
  --acknowledge-legacy
```

Use `--key <full-worktree-key>` instead of `--repo` to address a missing or moved
recorded repo without deriving a different key. Proven-dead owners need no
ownership acknowledgement. `--force-lock` and `--clean-orphaned` are disabled;
there is no bulk recovery or expiry. A changed snapshot aborts recovery.

### Owner evidence and persistence limits

The default owner is unknown. A run ID is an ownership correlation token, not
proof of liveness or a secret security credential. No harness thread/session ID,
wrapper PID, implicit parent PID or shared application PID is invented. A caller
may explicitly provide `agent_start.sh --owner-pid <durable-owner-pid>` only when
that process really represents the lifetime of the work. A process that outlives
or dies before its task gives unsuitable evidence; omit the option in that case.

PID binding records hostname, boot UUID, platform and native process birth:
Linux `/proc` start ticks or macOS libproc start seconds/microseconds. A matching
live owner blocks recovery even if stale or orphaned. A missing, zombie or reused
PID on the same host/boot is dead. Remote/different-boot identities, unsupported
probes and permission errors are unknown. Linux and macOS are supported; this
is a cooperating local-process protocol, not a distributed lease or an access
control boundary against someone who can rewrite the local files.

Every new mutation uses the same permanent `.guards/<key>` inode with an
OS-released exclusive flock. Never delete/recreate those guard files. Acquisition
publishes complete synced bytes by a no-replace hard link from `.pending/`.
Pending records are retained for recoverability; they are not active locks.
Release/recovery verifies digest and inode under the guard, persists original
bytes and `prepared.json` in `.archive/<event>/`, then moves the original to
`removed.lock` and writes `completed.json`. Archive/audit preparation failures
leave the lock intact. After a crash, `prepared.json` alone is not proof of
completion: inspect the live path, `removed.lock` and digest before acting.
A completion-marker write failure returns nonzero even if the move happened;
original bytes remain archived. No archive deletion is performed by the protocol.

These guarantees require a local filesystem supporting flock, atomic hard links,
rename and directory fsync. All writers must cooperate. **Mixed-version recovery
requires a quiescent interval:** old main/worktree scripts, manual writers and
unsupported filesystem clients ignore the new guard. Pause those writers,
recheck the exact digest and relevant repository state, and use the reviewed
checkout's recovery script. A fix worktree automatically uses the Hub's shared
lock root through `SHARED_ROOT`, so no installation or merge is required. App
inventory, old timestamps and lack of matching processes cannot prove that a
legacy run has ended. Stop if the snapshot or repository state changes.

Prepare parallel work without sharing a checkout:

```bash
scripts/agent_worktree.sh \
  --repo /path/to/project \
  --branch codex/focused-task \
  --project <project-slug> \
  --start \
  --query "<focus>" \
  --review
```

The helper refuses to overwrite existing paths and refuses branches that are
already checked out in another worktree. Its default worktree location is under
`.local/worktrees/`, so the Hub repo stays clean.

## Design Rules

- Do not store raw chat logs.
- Do not make start/finish wrappers write by default.
- Keep work runs project-bound.
- Do not let two write-capable agents share one working tree.
- Record durable outcomes through reports, facts, decisions, risks, questions,
  relations, and receipts.
- Add schema only when the existing audit trail is too weak for daily use.

## Future Option

If daily work shows that the existing audit trail is not enough, add a small
`work_sessions` table later. It should track only:

- project id
- focus
- start time
- finish time
- status
- optional branch or worktree path
- links to resulting reports, memories, and receipts

That table should not contain chat transcripts, secrets, or implementation
noise. Its purpose would be coordination and review, not memory hoarding.
