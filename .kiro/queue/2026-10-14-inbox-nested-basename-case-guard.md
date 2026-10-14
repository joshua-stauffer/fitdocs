---
id: 2026-10-14-inbox-nested-basename-case-guard
title: Pin case normalization for nested basename-only inbox ignores
status: open
importance: low
importance_why: Existing helper is correct but its basename case normalization can be deleted without failing the suite.
effort: S
kind: gap
area: inbox, src/fitdocs/inbox.py, tests/test_inbox.py
created: 2026-10-14
surfaced_by: /kiro-impl wellness-store task 2.7 independent review
pinned_at: f8c67fc
resume_command: "/kiro-spec-tasks inbox [queue: .kiro/queue/2026-10-14-inbox-nested-basename-case-guard.md] Add one nested basename case-normalization regression task"
context:
  - .kiro/specs/inbox/requirements.md
  - .kiro/specs/inbox/design.md
  - src/fitdocs/inbox.py
  - tests/test_inbox.py
  - tests/connectors/test_folder.py
blocked_by:
  - wellness-store
---

## What

The existing `_matches_any_ignore_pattern` lowercases both basename and
relative path. Tests pin relative-path normalization, but no independent case
combines an uppercase nested filename with a slashless literal basename
pattern. Removing basename normalization is currently undetected. The helper
was unchanged by wellness-store task 2.7; the current implementation is correct.

## Why it matters

A future regression could stop honoring a basename ignore for an uppercase
file nested under a directory, even though lowercase and relative-pattern
examples still pass. A root-level filename cannot distinguish these rules,
because the relative-path matching arm can match it too.

## Evidence

At `f8c67fc`, the reviewer changed
`lowered_basename = basename.lower()` to `lowered_basename = basename` in
`src/fitdocs/inbox.py::_matches_any_ignore_pattern`. All **155** inbox/folder
tests remained green. Strengthening the existing configured-pattern fixture
from `("sub/day_hydration_total.json", "day_hydration_total.json")` to
`("sub/DAY_HYDRATION_TOTAL.JSON", "day_hydration_total.json")` made that same
production mutation fail alone; restored production passed. Source and test
were restored and the final original 155-test suite passed. Exact replay on
the originating machine: `/private/tmp/inbox2-7-reviewer-upstream-probe.py`.
This was independently executed by the reviewer; the controller inspected the
script and report rather than rerunning it during review ownership.

## How to pick it up

Read the helper and `test_wellness_applies_configured_patterns`, then add a
separate nested uppercase basename fixture without losing the existing
lowercase, wildcard and relative-path controls. Consider a FIT counterpart
because both selectors share this helper. Apply the one-line production
mutation above and observe precisely the new assertion fail; restore and
confirm green. Avoid a leading wildcard or slash in the ignore pattern, which
lets the relative-path arm absorb the basename behavior. Done means the
helper remains unchanged, the new assertion discriminates, and canonical
checks pass.
