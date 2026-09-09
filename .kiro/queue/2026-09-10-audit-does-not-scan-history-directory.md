---
id: 2026-09-10-audit-does-not-scan-history-directory
title: fitdocs check does not audit the new history/ owned directory
status: open
importance: low
importance_why: A stale or foreign file under history/ is reported only when a history run happens, so the one command that promises a whole-root audit will be silent about one owned directory.
effort: S
kind: gap
area: load-history, src/fitdocs/audit.py
created: 2026-09-10
surfaced_by: /kiro-spec-batch (load-history design, wave 2)
pinned_at: 1251a98
resume_command: "do: once load-history has shipped, extend audit.audit() in src/fitdocs/audit.py to scan history/ (page and assets) for stale or foreign files the way it scans workouts/*.md, add the matching FindingKind, and update the fitdocs check docs; if the maintainer prefers the history run to stay the only auditor, record that in load-history's design instead"
context:
  - src/fitdocs/audit.py
  - .kiro/specs/load-history/design.md
  - .kiro/specs/wiki-contract/design.md
blocked_by: [load-history]
---

## What
`audit.audit()` walks `workouts/*.md` only. load-history adds a second owned
directory, `history/` (with `history/assets/`), and declares in its design
that auditing it is a non-goal for that spec: a stale page or a foreign file
there is noticed only by a `fitdocs history` run.

## Why it matters
`fitdocs check` is documented as the whole-root audit. Once a second owned
directory exists, the command under-reports by construction, and an athlete
who cleans up after a rename will not be told about a leftover chart.

## Evidence
- `src/fitdocs/audit.py:431-433` — `workouts_dir = data_root / WORKOUTS_DIR`
  and the single `glob("*.md")` loop; no other directory is scanned.
- `.kiro/specs/load-history/design.md` — Non-goals / Open Questions name the
  audit gap explicitly.

## How to pick it up
1. Read the audit function and the load-history design's owned-path section.
2. Decide the finding kinds a history scan needs (stale page, orphan asset,
   foreign file) and mirror the workouts loop for `history/`.
3. Extend the audit tests with a synthetic root carrying each case; keep
   personal data out of fixtures.
