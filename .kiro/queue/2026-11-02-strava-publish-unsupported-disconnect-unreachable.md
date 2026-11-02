---
id: 2026-11-02-strava-publish-unsupported-disconnect-unreachable
title: "The CLI's `UnsupportedDisconnect` branch is unreachable and the contract sentence that justifies it is vacuous"
status: open
importance: low
importance_why: "Dead, untested code plus two spec sentences describing a style nothing uses; harmless until someone trusts them."
effort: S
kind: inconsistency
area: "src/fitdocs/cli.py, docs/ownership-contract.md, .kiro/specs/relay-server/requirements.md"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 5.7 review and 7.6 review"
pinned_at: 964cc419
resume_command: "do: drop or test the UnsupportedDisconnect branch in cli.py and reword the ownership-contract sentence at the next contract edit (no version bump) (read .kiro/queue/2026-11-02-strava-publish-unsupported-disconnect-unreachable.md first)"
context:
  - src/fitdocs/cli.py
  - docs/ownership-contract.md
  - .kiro/specs/relay-server/requirements.md
  - src/fitdocs/connectors/disconnect.py
blocked_by: []
---

## What
No current auth style makes `run_disconnect` raise `UnsupportedDisconnect`, so the CLI branch that handles it cannot run, and the reserved-style CLI test that once covered it is gone. The ownership contract still says a style this version does not support is refused, and relay-server Req 14.5 has a "where its style is reserved" clause that applies to no style now.

## Why it matters
Untested dead code, and contract prose that promises behaviour no style can exercise.

## Evidence
- `src/fitdocs/cli.py:253` imports `UnsupportedDisconnect`; `:1880` `except UnsupportedDisconnect as exc:`.
- `docs/ownership-contract.md:1235`: "A style this version does not support is refused as a ...".
- `.kiro/specs/relay-server/requirements.md:295`: "where its style is reserved, it shall exit with the configuration-error code".
- Unreachability itself is the reviewers' claim (5.7, 7.6); the grep shows no raise site was looked for beyond these lines - verify with `grep -rn UnsupportedDisconnect src`.

## How to pick it up
1. `grep -rn UnsupportedDisconnect src tests` to confirm there is no raiser.
2. Either keep the branch with a unit test that injects a raising stub, or delete it; reword the contract sentence in the next contract edit (rewording alone needs no CONTRACT_VERSION bump per the reviewer's reading - confirm with docs/ownership-contract.md's own bump rules).
