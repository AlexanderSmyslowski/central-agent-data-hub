# Release Checklist

Use this short checklist before tagging a public release.

1. Update `pyproject.toml` so `[project].version` matches the tag without the
   leading `v`.
2. Update or add the matching release notes under `docs/public/`.
3. Run the local verification checks from the release notes.
4. Run `scripts/v1_readiness_check.sh`. It calls
   `scripts/release_candidate_check.sh` for the release-candidate evidence from
   [`v1.0-definition.md`](v1.0-definition.md): public demo startup, public demo
   smoke, public demo receipt, first external project smoke, trust-loop smoke,
   offline-agent smoke, upgrade drill, restore drill, `agent-hub doctor`,
   `agent-hub status`, and `agent-hub check`.
5. For a v1.0 release or any release that changes first-run behavior, run
   [`docs/first-run-test-protocol.md`](../first-run-test-protocol.md) with a
   real technical tester, or explicitly record why that human proof is deferred.
   Keep observation notes outside the repository.
6. If the human proof is deferred, say that plainly in the release notes before
   tagging or broader promotion. Do not imply that automated checks measured
   first-time human understanding.
7. Push `main` and wait for CI to pass, including the separate behavioral
   smoke jobs. A green unit-test job alone is not enough.
8. Verify that the GitHub repository link is publicly reachable in an
   unauthenticated browser before using it in public copy.
9. Tag the checked commit and create the GitHub release from the release notes.

Do not move an already published tag. If a release needs a correction after it
is public, publish the next patch version instead.
