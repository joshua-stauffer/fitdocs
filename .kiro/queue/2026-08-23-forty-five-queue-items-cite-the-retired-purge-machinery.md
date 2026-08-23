---
id: 2026-08-23-forty-five-queue-items-cite-the-retired-purge-machinery
title: Forty-five open queue items carry resume commands or context paths under scripts/purge/, which task 9.3 deleted
status: open
importance: medium
importance_why: /kiro-queue hands these resume commands to fresh sessions as the way to pick the work up. Each one now names a path that does not exist, so a session with no context starts by discovering its instructions are stale — the exact cost the queue format exists to prevent.
effort: M
kind: gap
area: .kiro/queue, encumbered-content-purge
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge task 9.3 (reviewer follow-up), verified this run
pinned_at: c786326
resume_command: "do: triage the 45 open queue items citing scripts/purge/ or tests/purge/ -- close the ones the retirement made moot, and re-point the rest at their surviving subjects"
context:
  - .kiro/queue/README.md
  - docs/reference/history-rewrites.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Task 9.3 deleted `scripts/purge/` entire and `tests/purge/` less three
relocations. Forty-five open queue items still cite those paths — in
`resume_command`, in `context:`, or in their evidence sections.

Measured 2026-08-23 on `c786326`:

```
$ grep -rl "scripts/purge\|scripts\.purge" .kiro/queue/*.md | wc -l
45
```

A further four items cite scratch artifacts destroyed at task 9.4
(`rules.json`, `plan-content.tsv`, `plan-paths.tsv`).

## Why it matters

The queue's whole contract, stated in its own README, is that an item must let
"a session with **zero context** pick it up cold". A `resume_command` naming a
deleted module breaks exactly that, and it breaks it at the worst moment — the
first thing the fresh session does.

These are not all the same case, which is why this needs triage rather than a
sed:

- **Moot** — the item described a defect *in* the retired machinery. The
  retirement resolved it. Close, noting that retirement is the resolution.
- **Re-homed** — the subject moved into a surviving module (task 7.2 re-homed
  `_whitespace_tolerant_pattern` into `tests/_forbidden_strings.py`, and the
  notice/mark tip guard into `tests/test_forbidden_strings.py`). Re-point.
- **Still live, different home** — the item's real subject was never the
  machinery; it just cited it as the example. Re-point to the surviving
  example.

Guessing which is which from the path alone will close live items. That is the
risk this item exists to flag.

## Evidence

- 45 open items match `scripts/purge` or `scripts.purge`
- `scripts/` and `tests/purge/` no longer exist on `HEAD` (`ls` errors; task
  9.3, commit `c18ec26`, deleted 32 files and relocated 3)
- Known-moot example:
  `.kiro/queue/2026-08-13-invariant-1-and-2-diagnostics-print-raw-tokens.md`
  names `tests/purge/test_replacements.py` — deleted — but a live instance of
  its defect class survives in `tests/test_forbidden_strings.py`, so it is
  **re-point**, not close (already updated this run with that finding)
- Known-moot example:
  `.kiro/queue/2026-08-01-scratch-artifacts-not-durable.md` asks to relocate
  the scratch artifacts to a durable path; task 9.4 destroyed them under a
  maintainer ruling, so the item is superseded

## How to pick it up

Start from the list:

```
grep -rl "scripts/purge\|scripts\.purge" .kiro/queue/*.md
```

For each, read the `## What` section — **not** the path — and decide which of
the three cases above it is. The path is what went stale; the subject is what
tells you whether the item is still real.

`docs/reference/history-rewrites.md` section 8 is the authority on what was
deleted, what was relocated where, and what capability was given up; read it
before triaging, so a "moot" call is grounded in the retirement record rather
than in the file being absent.

Use `/kiro-queue close <id>` for the moot ones so the closure is recorded
rather than silent. Closed items keep their pins by design (Req 9.5) — do not
repair those.

Done when no open item's `resume_command` or `context:` names a path that does
not exist.
