---
id: 2026-08-18-verify-rewrite-already-current-branch-unpinned
title: verify_rewrite's already_current expected-branch is unpinned, though its docstring states it
status: open
importance: low
importance_why: Only reachable on a file mixing a repaired pin with an already-current one, which no apply_repair fixture writes and the real queue corpus never produces; the failure direction is a spurious raise, not a silent pass.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/pins.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.5 review round 3)
pinned_at: 9a006f0
resume_command: "do: add a verify_rewrite fixture mixing a repaired outcome with an already_current one, so dropping the `else outcome.original` branch from the expected-tuple construction reds"
context:
  - scripts/purge/pins.py
  - tests/purge/test_pins.py
blocked_by: []
---

## What

`verify_rewrite` builds its expected tuple as
`outcome.resolved if outcome.status == "repaired" else outcome.original`.
Dropping the `else outcome.original` half — leaving
`tuple(outcome.resolved for outcome in outcomes)` — survives the whole module.

The docstring states the branch explicitly: expected is "`epoch` for a
`repaired` outcome, the unchanged `original` value otherwise". That second
clause has no test behind it.

## Why it matters

Low, and the bound is worth writing down. `resolved` is `None` for an
`already_current` outcome, and `None` never matches a real on-disk value, so
the mutation can only cause a **spurious raise** — never a silent pass. It is
reachable only on a file that mixes a repaired pin with an already-current
one, which no `apply_repair` fixture writes and which the real queue corpus
does not produce (every tracked item carries exactly one `pinned_at:`).

Recorded because it is a correctness branch carrying a written claim and no
test, in the one module whose entire reason for existing is that a partial
write once read as complete.

## Evidence

Reported by the task 7.5 reviewer, which measured it: replacing the
expected-tuple construction with
`tuple(outcome.resolved for outcome in outcomes)` leaves all 32 tests in
`tests/purge/test_pins.py` green.

Classified non-blocking by that reviewer and explicitly routed to follow-ups
rather than treated as a rejection ground. Not independently re-derived by the
controller.

## How to pick it up

Add one `verify_rewrite` fixture whose `outcomes` mixes a `repaired` outcome
with an `already_current` one, and whose text carries both values correctly —
so the unmutated call does **not** raise, and the mutated one does (because
`None` replaces the already-current value). Verify the mutation reds it, then
revert. Done when the `else` branch has a test.
