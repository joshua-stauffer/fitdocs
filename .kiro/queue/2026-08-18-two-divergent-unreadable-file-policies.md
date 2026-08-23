---
id: 2026-08-18-two-divergent-unreadable-file-policies
title: Two independent unreadable-file accounting policies over the same tracked tree, and 9.3 deletes one
status: open
importance: low
importance_why: Nothing pins the two agreeing today, and after 9.3 the survivor's hardcoded suffix allowlist becomes the sole policy by default rather than by decision.
effort: S
kind: inconsistency
area: encumbered-content-purge, tests/test_forbidden_strings.py, tests/purge/test_replacements.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 review round 3)
pinned_at: c3d2201
resume_command: "do: task 9.3 deleted one of the two unreadable-file accounting policies with tests/purge/. Record whether the surviving suffix allowlist in tests/test_forbidden_strings.py is the intended policy or a leftover of the pair."
context:
  - tests/test_forbidden_strings.py
blocked_by: []
---

## What

Two mechanisms account for tracked files that cannot be read as text:
`tests/purge/test_replacements.py`'s `_tracked_text_files` / `_UNREADABLE` /
`_assert_unreadable_set_is_known` (a mutable module-global populated as a side
effect of the last walk), and `tests/test_forbidden_strings.py`'s
`_notice_guard_tracked_texts` (a returned mapping with a hardcoded
`(".fit", ".png", ".gz")` suffix allowlist).

Task 9.3 deletes the former. The latter then becomes the only policy.

## Why it matters

Nothing pins the two agreeing today, so a divergence would be invisible. After
9.3 the survivor's allowlist is load-bearing for a standing guard that
outlives the purge, and it would arrive there by deletion rather than by
decision -- with no record of whether its suffix set was ever the considered
one.

An unreadable tracked file yields no hit and no report, so it passes the
scan clean. That property is already recorded in this spec's Implementation
Notes as a known hazard.

## Evidence

Reported by the task 7.2 reviewer, citing
`tests/purge/test_replacements.py:1522-1570` against
`tests/test_forbidden_strings.py:1240-1266`.

Confirmed at `dac1a7a`: `_notice_guard_tracked_texts` is defined at
`tests/test_forbidden_strings.py:1261` and returns a `(texts, unreadable)`
pair.

Task 9.3's deletion list covers `tests/purge/` less two named relocations,
neither of which is `test_replacements.py`.

## How to pick it up

Before 9.3 runs, compare the two policies against the current tracked tree and
confirm they agree. Then either pin the survivor's suffix allowlist with a
test that reds when a real unreadable file falls outside it, or state in the
provenance record that the allowlist is the retained policy and why. Done
when the survivor's policy is deliberate.

## Triage note (2026-08-23)

Re-pointed during the post-purge queue triage. Task 9.3 deleted `scripts/purge/` entire and `tests/purge/` less three relocations, so this item's `resume_command` and `context:` named paths that no longer exist. The **subject** was checked against the tree rather than inferred from the path, per `.kiro/queue/closed/2026-08-23-forty-five-queue-items-cite-the-retired-purge-machinery.md`; it survives in the retained guards and the item still stands. Only the locators changed — the finding above is unedited.
