---
id: 2026-10-02-task-4-2-bullet-overstates-the-filename-uuid-pin
title: channel-merge tasks.md task 4.2 bullet 3 says the page filename and uuid are held by activity-identity's ordering, but they are fixture-satisfied whichever file is the base
status: open
importance: low
importance_why: Spec wording only; the truth is already recorded in the 4.2 Implementation Note, so the cost is a reader taking the bullet at face value.
effort: S
kind: docs
area: channel-merge, .kiro/specs/channel-merge/tasks.md
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: reword .kiro/specs/channel-merge/tasks.md task 4.2 bullet 3 (and check the 6.1 line that calls Req 1.6 held by activity-identity) to say what pins it: the recorded base-identity keys, not the filename or uuid [queue: .kiro/queue/2026-10-02-task-4-2-bullet-overstates-the-filename-uuid-pin.md]"
context:
  - .kiro/specs/channel-merge/tasks.md
  - tests/test_compose_e2e.py
  - .kiro/specs/activity-identity/requirements.md
blocked_by: []
---

## What
Task 4.2's third bullet says the composed page's filename and `uuid` equal those
the HealthFit copy alone produces, "a regression check held by
`activity-identity`'s ordering, recorded as reached by no mutation of this
plan". "Held by activity-identity's ordering" reads as if reversing the
precedence would red that check. It would not: on the trio fixture all three
files compute the same stem, and only the HealthFit copy carries a uuid, so the
filename and uuid do not change when the base changes. What does move under a
reversed precedence is the recorded base-identity keys on the page.

## Why it matters
A later reader (or a reviewer ticking Req 1.6) can take the bullet as the pin
for "identity comes from the base alone" and stop looking. The pin that
actually holds it is a different one.

## Evidence
At 5c41759.
- `.kiro/specs/channel-merge/tasks.md:586-588`: the bullet's text, "a regression
  check held by `activity-identity`'s ordering, recorded as reached by no
  mutation of this plan".
- `.kiro/specs/channel-merge/tasks.md:771` (the 4.2 Implementation Note):
  "Filename and `uuid` are fixture-satisfied whichever file is the base (all
  three files compute stem 2042-04-13-run-2320; only the HealthFit copy carries
  a uuid) -- reached by no mutation of this plan, a regression check; Req 1.6 is
  pinned instead by the recorded base identity lines (source_kind/elapsed/
  distance/device equal HealthFit-alone's; identity from an extra or reversed
  precedence reds it)."
- `.kiro/specs/channel-merge/tasks.md:735` (task 6.1): "1.6 is recorded as held
  by activity-identity", with `:779` listing it PRESERVED-ONLY.
- The test itself already says it: `tests/test_compose_e2e.py:383-396`
  (`test_the_page_filename_and_uuid_are_those_the_healthfit_copy_alone_produces`)
  calls the filename and `uuid` lines "a regression check only" and names
  `source_kind`, `source_elapsed_s`, `source_distance_m` and `source_device` as
  what discriminates, with the two mutations that red it (identity from the
  first extra's parse; the reversed precedence).
- The reversed-precedence observation (filename and uuid unchanged, only the
  base-identity keys move) is from the reviewer's mutation, reported by reviewer
  subagent, unverified in this run; the Implementation Note above records it.

## How to pick it up
1. Reword bullet 3 to say the filename and uuid check is a regression check that
   the fixture cannot make red, and that Req 1.6 is pinned by the recorded
   base-identity lines (name `tests/test_compose_e2e.py:383`).
2. Check whether the 6.1 line at `:735` needs the same correction (the
   PRESERVED-ONLY note at `:779` already qualifies it).
3. Done when no sentence in `tasks.md` attributes the Req 1.6 pin to
   `activity-identity`'s ordering alone.
