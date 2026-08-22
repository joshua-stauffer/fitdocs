---
id: 2026-07-28-citation-test-module-absent-from-design
title: fit-ingest design.md's File Structure Plan omits `tests/test_citation.py`, which task 8.1 mandates
status: open
importance: low
importance_why: Pure spec/tree drift with nothing computing wrong. The design's Amendment 1 test listing names `metrics/test_sources.py` and `metrics/test_constant_guard.py` but not `tests/test_citation.py`, even though task 8.1 bullet 4 requires that module and its mypy-perimeter entry. A reader auditing the design against the tree finds a shipped test module the plan never mentions.
effort: S
kind: inconsistency
area: fit-ingest, .kiro/specs/fit-ingest/design.md
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 8.1 review, round 2 FOLLOW_UPS)
pinned_at: 8e3cb05
resume_command: "/kiro-spec-design fit-ingest [queue: .kiro/queue/2026-07-28-citation-test-module-absent-from-design.md] Add tests/test_citation.py to the File Structure Plan's Amendment 1 test listing"
context:
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/tasks.md
  - tests/test_citation.py
blocked_by: []
---

## What

`design.md`'s File Structure Plan lists the Amendment 1 test additions as
`tests/metrics/test_sources.py` and `tests/metrics/test_constant_guard.py`. It
does not list `tests/test_citation.py`, although tasks.md 8.1 bullet 4 mandates
that module *and* its addition to the type-check perimeter, and the task's
observable depends on it existing ("demonstrated from a module the checker
actually reads").

The module shipped in `8e3cb05`. The design's own `CitationVocabulary`
component section describes the module under test in full; only the file
listing is missing the test file.

## Why it matters

Low. Nothing computes wrong and no requirement is unmet — the module exists,
is inside the mypy perimeter, and carries all eight of the task's requirements
as PINNED assertions.

The cost is to a reader auditing design against tree, which is a real activity
in this repo: the File Structure Plan is the canonical index of what Amendment 1
adds, and a shipped test module absent from it reads either as unplanned work
or as a stale plan. This is the same drift species already open four times over
for plugin-api's public-surface enumeration
(`2026-07-27-design-md-enumeration-unguarded`,
`2026-07-27-plugin-api-enumeration-restaled-by-benchmarks`), where the repeated
fix was a mechanical guard rather than another manual reconciliation.

## Evidence

- `.kiro/specs/fit-ingest/design.md` File Structure Plan, Amendment 1 test
  entries: names `metrics/test_sources.py` and `metrics/test_constant_guard.py`;
  no `test_citation.py`.
- `.kiro/specs/fit-ingest/tasks.md` task 8.1, bullet 4: *"Add this vocabulary's
  own test module to the type-check perimeter in the packaging config in this
  same change"*.
- `tests/test_citation.py` exists at `8e3cb05` (committed in that change), and
  `pyproject.toml`'s `[tool.mypy].files` lists it — `uv run mypy` reports 71
  source files, up from 69 before the task.

## How to pick it up

1. Open `.kiro/specs/fit-ingest/design.md` and find the File Structure Plan's
   directory tree and its Amendment 1 additions.
2. Add `tests/test_citation.py` alongside the two metrics test modules, with a
   one-line note matching the style of its siblings (it is the
   `CitationVocabulary` component's test module, and it is inside the mypy
   perimeter deliberately — that is what makes the Req 16.4 static negative
   non-vacuous).
3. Check whether the plan should also name the `pyproject.toml`
   `[tool.mypy].files` edit in its Modified Files table; task 8.1 required it
   and the table is the design's record of cross-file edits.
4. Done looks like: every file task 8.1 actually shipped appears in the design's
   plan. Validation for the `.kiro/specs/**` class is
   `/kiro-spec-status fit-ingest` clean with `spec.json` approvals reflecting
   what happened — note that editing an approved `design.md` is a spec change
   and follows the change protocol's worktree ritual.

## Open questions

Whether this is worth fixing on its own or should be folded into the next
`design.md` revision this spec takes. It is a one-line addition; the argument
for folding it in is that a `.kiro/specs/**` change owes its own worktree,
branch and approval-state check, which is disproportionate for one line.
