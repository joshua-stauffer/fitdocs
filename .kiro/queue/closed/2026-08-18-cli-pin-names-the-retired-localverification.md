---
id: 2026-08-18-cli-pin-names-the-retired-localverification
title: The CLI dispatch pin still maps verify-local to the retired LocalVerification component
status: done
importance: low
importance_why: Task 7.6 edits this dispatch and will red on the exact-equality pins; the stale label should move in the same change rather than be discovered as a surprise.
effort: S
kind: chore
area: encumbered-content-purge, tests/purge/test_cli.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.4 review)
pinned_at: b7c5a3d
resume_command: "do: at task 7.6, re-scope tests/purge/test_cli.py's verify-local label from LocalVerification to ReplacementVerification in the same change that registers the replace subcommand"
context:
  - tests/purge/test_cli.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`tests/purge/test_cli.py` maps `"verify-local"` to `"LocalVerification"` in its
stub-signature pin. Amendment 1 replaced that component with
`ReplacementVerification`; `design.md` now names `LocalVerification` only as
the thing it superseded.

## Why it matters

Small, and it has a natural owner. Task 7.6 adds the `replace` subcommand to
the CLI dispatch and must extend **both** exact-equality pins (the name set and
the name-to-callable dispatch) in the same change, because both red the moment
the subcommand registers. The stale label sits in that same structure, so
moving it then costs nothing — whereas leaving it means the CLI test module
keeps naming a component that no longer exists in the design.

The same class of residue was already found in `verify.py` and
`test_verify.py` during the 7.4 review and is being fixed there.

## Evidence

Measured at `b7c5a3d`: `tests/purge/test_cli.py` contains
`"verify-local": "LocalVerification",` in its stub-signature mapping.
`design.md` retains `LocalVerification` only in its Amendment 1 section, as the
component `ReplacementVerification` replaced.

Reported by the task 7.4 reviewer and routed to follow-ups rather than fixed,
because `tests/purge/test_cli.py` is outside task 7.4's boundary and inside
task 7.6's.

## How to pick it up

At task 7.6, when extending the two exact-equality CLI pins for the new
`replace` subcommand, re-scope the `verify-local` label in the same edit. Done
when no CLI pin names a retired component.

## Resolution (2026-08-18, done)

Resolved at task 7.4, earlier than this item anticipated. The item deferred the
relabel to task 7.6 on the grounds that 7.6 owns the CLI dispatch edit; in the
event, 7.4's Finding 4 required re-scoping `verify_local`'s echoed message from
`LocalVerification` to `ReplacementVerification`, and `test_cli.py`'s
`_STUB_COMMAND_SIGNATURES` pins that literal substring — so the pin had to move
in the same change or the suite stays red.

Recorded as forced rather than opportunistic, under the precedent in
`tasks.md` › Implementation Notes: "A `(P)` redaction may be forced into a
peer's test file, and that is not scope creep."

Verified: reverting `"verify-local": "ReplacementVerification"` to
`"LocalVerification"` reds exactly one test. `ReplacementVerification` is
emitted by `scripts/purge/verify.py` alone among the seven stubs — the
reviewer invoked all seven and captured their output — so the pin's
discrimination property is preserved.

**One correction to the record.** The controller inferred from a file-content
grep that the old label was already non-discriminating, because
`LocalVerification` appears in both `rewrite.py` and `verify.py`. That
inference was wrong: the pin matches **echoed output**, not file content, and
`rewrite.py`'s single occurrence is a docstring at `:328` that is never
echoed (`rewrite.run` emits `HistoryRewrite`). A `verify-local` → `rewrite.run`
mis-wire would have been caught under the old label too. The change is right;
the reason first given for it was stronger than the facts supported.

Task 7.6 should not re-open this pin.
