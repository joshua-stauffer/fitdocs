---
id: 2026-10-13-snapshot-generation-number-reused-after-delete
title: create_snapshot numbers a new snapshot one past the highest generation present, so a deleted generation's number is reused and a page recording the old path draws the new rows instead of reporting snapshot_missing
status: open
importance: low
importance_why: Needs the user to delete a snapshot and a second copy of a page to still record its path; the effect is a frozen chart silently showing different rows, which is what snapshots exist to prevent, but fitdocs never deletes a snapshot itself.
effort: M
kind: gap
area: dashboards, src/fitdocs/dashboards/storage.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 5.3 reviewer)
pinned_at: 0a98d5c
resume_command: "/kiro-spec-design dashboards [queue: .kiro/queue/2026-10-13-snapshot-generation-number-reused-after-delete.md] decide whether snapshot generation numbers may be reused after a delete (design Storage, Req 10.5)"
context:
  - src/fitdocs/dashboards/storage.py
  - .kiro/specs/dashboards/design.md
  - .kiro/specs/dashboards/requirements.md
  - tests/dashboards/test_storage.py
blocked_by:
  - dashboards
---

## What
`create_snapshot` picks the next generation as `max(existing generations) + 1`
(`src/fitdocs/dashboards/storage.py:332`), which is what design § Storage
specifies ("`n = 1 + max existing generation`", retrying with `n + 1` on
`FileExistsError`). If the highest-numbered snapshot file is deleted, the next
freeze creates a file with the same name and different contents.

## Why it matters
Req 10.5 says that when the snapshot a region records is missing, the chart is
left unchanged and `snapshot_missing` is reported. A page that still records
`assets/p/c.snapshot-2.json` (an older copy of the page, a page copied to
another name, a git checkout of an earlier version) gets no such report once
that name exists again: it silently draws the new snapshot's rows. A frozen
chart is meant to show the same thing forever (Req 10 objective).

## Evidence
Run against 0a98d5c (session script under
`/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/43144b56-a94d-45f3-a857-8e0a466250cf/scratchpad/gen_reuse.py`,
wiped on reboot):

```
create_snapshot x2                  -> ['assets/p/c.snapshot-1.json', 'assets/p/c.snapshot-2.json']
unlink assets/p/c.snapshot-2.json
create_snapshot again               -> assets/p/c.snapshot-2.json
contents of snapshot-2 now          -> second-2      (the new encode, not the deleted file's)
```

Reported by the 5.3 reviewer subagent; reproduced here.

## How to pick it up
1. Read `create_snapshot` and `_generations` in `storage.py` (lines 303-345) and design § Storage / Req 10.4-10.8.
2. Options: keep the rule and document the limit (fitdocs never deletes snapshots, a user deleting one is outside the guarantee); or never reuse a number by recording a high-water mark (a small file such as `assets/<page>/.generation`, which adds a written file Req 16.6 must allow) or by using a content-derived name. Each changes design and the ownership contract text, so this is a decision first.
3. Done means the chosen rule is in the design, and a test deletes the highest generation and asserts the new behaviour.

## Open questions
Is a user-deleted snapshot in scope for the Req 10.5 guarantee at all? The cheapest answer is no, with a sentence in docs/dashboards.md saying so.
