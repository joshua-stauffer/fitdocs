---
id: 2026-09-18-btb-design-prose-defects-and-deviations
title: build-training-block design.md: three false prose lines and five recorded deviations to write up as Amendment 1
status: open
importance: low
importance_why: The design is now the reference for distribution 4.2; two of its pointers are wrong and five things shipped differently than it says.
effort: S
kind: docs
area: build-training-block, .kiro/specs/build-training-block/design.md
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: append '## Amendment 1' to .kiro/specs/build-training-block/design.md recording the five deviations listed in this item and correct the three prose lines; do not touch code"
context:
  - .kiro/specs/build-training-block/design.md
  - .kiro/specs/build-training-block/tasks.md
  - .kiro/specs/distribution/design.md
  - tests/test_skill_e2e.py
  - tests/test_docs_guarantees.py
blocked_by: []
---

## What
Prose defects: (1) `design.md:189` "One wheel builder exists in the suite" --
`tests/load/test_packaging.py:355` and `:597` run `uv build` inline; (2)
`design.md:991` labels the third version-identity statement "the Regression
section (`:883`)", but distribution's `design.md:883` (pre-amendment) was the
Unit Tests "Version resolution" bullet and the Regression section carries no
version statement -- task 3.3 amended by content; (3) `design.md:871` and
`tasks.md:92` cite `tests/history/test_engine.py:43-64` for `_page`; it is
`44-65`. Also unstated: whether `metadata` is a closed sub-key set (Req 2.5
closes the top level only; 2.2's controller ruling left it unpinned).

Deviations to record (none need code): `_fake_system_date` imported through
`importlib.import_module` (`tests/test_skill_e2e.py:53`, because
`tests/test_history_e2e.py` is untyped); `skill` named in a docstring
paragraph beside `plugins` rather than the data-root bullet list (the list's
follow-on sentence would be false for it); the `Report lines:` line carries a
trailing sentence; `tests/test_skill_e2e.py` imports `fitdocs.contract.DATE_KEY`
(not in Allowed Dependencies); the README pin is README-scoped with a
`## Plugins` adjacency clause (see the sibling item on relocation).

## Evidence
Each `file:line` above at `e45f114`; the Implementation Notes for 2.2, 3.1,
3.3, 3.4 in `.kiro/specs/build-training-block/tasks.md` record the rulings.

## How to pick it up
Read the four Implementation Notes, then the cited design lines; write the
amendment in the shape of `.kiro/specs/training-blocks/design.md`'s
Amendment 1. Done when `/kiro-spec-status build-training-block` is clean and
no cited line is false.
