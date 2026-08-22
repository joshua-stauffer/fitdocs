---
id: 2026-08-02-purge-guard-of-a-guard-unpinned
title: Three purge-tooling assertions survive mutation because nothing observes their subject
status: open
importance: low
importance_why: None can cause a missed site or a misclassified hit; each costs a duplicate record, a diagnostic string, or one extra skip that the spec's own skip-count reconciliation already surfaces.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_rewrite_map_extraction.py, scripts/purge/sweep.py
created: 2026-08-02
surfaced_by: /kiro-impl encumbered-content-purge (tasks 3.1 and 3.2, reviewer rounds 3)
pinned_at: 9612d28
resume_command: "do: close the three surviving mutations recorded in this item's Evidence -- assert UnreadableFile.reason is non-empty and specific, pin run_full_sweep's unreadable composition per-source, and give _PRIOR_MAP_PATH a typo-resistant check -- re-running each named mutation to confirm it now reds"
context:
  - tests/purge/test_rewrite_map_extraction.py
  - tests/purge/test_sweep.py
  - scripts/purge/sweep.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Three assertions in the purge's own tooling survive single-line mutation with the whole
suite green. All three were found by reviewer subagents that designed their own
mutations, all three were judged non-blocking at the time, and all three are recorded
here rather than left in a review transcript that nobody will read again.

1. **`run_full_sweep`'s unreadable composition is unpinned per-source.** `unreadable =
   tp_unreadable + vm_unreadable` (`scripts/purge/sweep.py:968`) survives dropping
   *either* half, because both content-reading passes report the same paths. Each half is
   pinned at the function level, so no file becomes unreported — the only effect is
   losing a duplicate record and `unreadable_count` going 2 → 1.
2. **`UnreadableFile.reason` is unpinned.** Blanking it survives. The *path* is pinned by
   `test_report_unreadable_names_every_offending_path`; `reason` is a diagnostic string
   only.
3. **`_PRIOR_MAP_PATH` is shared subject state between a guard and its guard.**
   `tests/purge/test_rewrite_map_extraction.py:35` feeds both
   `_resolve_prior_map_pre_deletion_text` and the independence probe
   `_prior_map_is_reachable_from_head` (line 223). Typing it wrong makes both agree
   "unreachable", so the pairing assertion passes and the row-count pin skips. Separately,
   `return False` at the head of the probe itself survives, because its value is only read
   inside `if text is None:` — a state a healthy repo never reaches.

## Why it matters

Each is bounded and none can cause the purge to miss a site or misclassify a hit — that
was the standard the reviewers applied, and it is why they did not block on them.

The reason to record them: item 3 degrades to a **visible extra skip** (2505 passed / 2
skipped rather than a green pass), and this spec's validation already obliges every task
to reconcile the skip count explicitly, so it surfaces rather than hides. But that
obligation lives in prose. If a later task stops reconciling skip counts, a typo in one
string constant silently disables the assertion that ties the extracted rewrite-map rows
to the real pre-deletion map — and after Major 7 rewrites history, that assertion cannot
be reconstructed.

Items 1 and 2 are cosmetic by comparison and are bundled only because they are the same
shape and the same edit session.

## Evidence

At `9612d28`, verified by reviewer subagents that applied each mutation through
`uv run pytest` and observed the suite stay green:

- `scripts/purge/sweep.py:968` — `unreadable = tp_unreadable + vm_unreadable`; dropping
  either operand leaves 2573 passed / 1 skipped.
- `scripts/purge/sweep.py:185` — `reason: str`; blanking the value at the four
  construction sites (lines 231, 234, 278, 281) leaves the suite green.
- `tests/purge/test_rewrite_map_extraction.py:35` — `_PRIOR_MAP_PATH` is consumed at
  lines 187, 194, 203, 214 (the resolver) and 241, 250 (the independence probe), plus the
  full-argv fake constants at 274-276. Corrupting it yields 2505 passed / **2** skipped
  rather than a failure.
- `tests/purge/test_rewrite_map_extraction.py:223` — `_prior_map_is_reachable_from_head`;
  `return False` at its head leaves 2506 passed.

Reported by reviewer subagents across two tasks; the line numbers and the composition at
`sweep.py:968` were re-verified directly in this session. The mutation results themselves
are the reviewers' and were not re-run by the coordinator.

## How to pick it up

1. Read `tests/purge/test_rewrite_map_extraction.py` first — item 3 is the only one with
   real consequence. The fix is to make a wrong `_PRIOR_MAP_PATH` *fail* rather than skip:
   assert the constant names a path that existed at some commit reachable from `HEAD`
   (`git rev-list -1 HEAD -- <path>` returning non-empty **or** `HEAD:<path>` resolving),
   so a typo reds instead of quietly disabling the pin. Note this check must itself
   self-retire after Major 7, when the blob genuinely becomes unreachable — mirror the
   existing gating in that module rather than inventing a second mechanism.
2. For items 1 and 2, in `tests/purge/test_sweep.py`: assert `run_full_sweep`'s
   `unreadable` contains a record from *each* source rather than merely being non-empty,
   and assert `UnreadableFile.reason` is non-empty and mentions the failure kind.
3. Re-apply each mutation named in Evidence and confirm it now reds, per
   `.kiro/steering/change-protocol.md` § Fixture Discrimination. Export
   `FITDOCS_FORBIDDEN_STRINGS` for every run or token checks degrade to a skip.

Done means: all four mutations red, and the suite still green when reverted.

## Open questions

Whether item 3's fix belongs here or inside task 4.3's standing forbidden-string guard.
It is a test-integrity check rather than a content check, so this item assumes it stays
local to the module — but a picking-up session should confirm 4.3 has not since grown a
surface that covers it.
