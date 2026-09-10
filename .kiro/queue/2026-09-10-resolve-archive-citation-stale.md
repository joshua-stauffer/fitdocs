---
id: 2026-09-10-resolve-archive-citation-stale
title: performance-benchmarks design cites _resolve_archive at load/engine.py:613-641; it is at 618 and was before wave 0 too
status: open
importance: low
importance_why: A wrong line range sends an implementer of task 4.2 to the wrong place in a 600-line module; cheap to fix, but pre-existing and out of the applies_from amendment's scope, so it was not fixed there.
effort: S
kind: inconsistency
area: performance-benchmarks, src/fitdocs/load/engine.py
created: 2026-09-10
surfaced_by: /kiro-spec-design performance-benchmarks (Amendment 1 review gate, note N7)
pinned_at: 4b76906
resume_command: "/kiro-spec-design performance-benchmarks [queue: .kiro/queue/2026-09-10-resolve-archive-citation-stale.md] Correct the _resolve_archive line citation, and sweep the spec for other stale src/ line ranges while you are in it"
context:
  - .kiro/specs/performance-benchmarks/design.md
  - src/fitdocs/load/engine.py
blocked_by: []
---

## What
`design.md` (Existing Architecture Analysis) cites
`load/engine.py:613-641` for `_resolve_archive`. On `main` the function's `def`
is at line 618.

## Why it matters
Task 4.2 ("Resolve and re-parse a tagged page's archive") is told to reuse
exactly this rule so the two passes can never disagree about archive
resolution. An implementer following the citation lands 5 lines short of the
function in a module of ~1000 lines.

## Evidence
- `.kiro/specs/performance-benchmarks/design.md` — the string `613-641`.
- `grep -n "def _resolve_archive" src/fitdocs/load/engine.py` → 618.
- Checked at `664960a^` as well: it was 618 before wave 0 landed, so this is
  **not** fallout from `applies_from` — it is pre-existing imprecision from the
  Phase 6 batch, which is why the Amendment 1 run left it alone rather than
  widening its diff.

## How to pick it up
Correct the range, and while there, sweep the spec for other `src/` line
citations — the same review found `profile.py:517-583` stale (fixed in
Amendment 1, it *was* wave 0 fallout). A citation that names a symbol as well
as a line survives a refactor; one that names only lines does not.
