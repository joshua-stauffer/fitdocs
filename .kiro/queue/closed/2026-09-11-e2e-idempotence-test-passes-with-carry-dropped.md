---
id: 2026-09-11-e2e-idempotence-test-passes-with-carry-dropped
title: The e2e double-regen test passes on a build that deletes every effort tag
status: done
importance: low
importance_why: The test cannot distinguish "the tag survived twice" from "the tag was destroyed twice"; Req 4.6 is pinned elsewhere, so the risk is a false sense of coverage.
effort: S
kind: gap
area: tests/test_effort_tags_e2e.py
created: 2026-09-11
surfaced_by: /kiro-validate-impl effort-tags (task 5.3 feature validation)
pinned_at: d1147a0
resume_command: "do: add a precondition to the effort-tags e2e idempotence test so it cannot pass on a build that drops the carry"
context:
  - tests/test_effort_tags_e2e.py
  - tests/test_sync.py
  - src/fitdocs/render/frontmatter.py
blocked_by: []
---

## What

`tests/test_effort_tags_e2e.py::test_regenerating_twice_over_a_tagged_document_is_byte_identical`
regenerates twice and compares the bytes. It never asserts the tag is present in
the first regeneration's output, so a build that silently deletes every effort
tag regenerates idempotently too and the test passes.

Requirement 4.6 IS genuinely pinned -- by
`tests/test_sync.py::test_regenerating_a_tagged_page_twice_is_byte_identical`,
which does red under the same mutation. The defect is confined to the e2e file's
contribution.

## Why it matters

Low severity because the requirement is covered elsewhere, but the shape is the
one this spec spent three review rounds learning: an assertion whose scenario is
never reached. It teaches a later reader that the e2e file covers idempotence of
a *tagged* document when it covers idempotence of *any* document. If the
test_sync.py counterpart is ever moved or narrowed, the coverage vanishes with
nothing failing.

Worth noting where it surfaced: inside the very file whose own agent-log WARN
calls the unreachable-scenario species "the most transferable thing in the spec".
Two instances were found and fixed in that file during review; this third
survived both rounds.

## Evidence

Executed during task 5.3 validation at `e39b35f`. Mutation: `carried = ""` in
`src/fitdocs/render/frontmatter.py:153`, dropping the carry entirely.

- `uv run pytest tests/test_effort_tags_e2e.py::test_regenerating_twice_over_a_tagged_document_is_byte_identical`
  alone -> **1 passed**
- the same mutation across the suite -> **16 failed** in `test_effort_tags_e2e.py`
  and `test_sync.py`, including the `test_sync.py` idempotence counterpart

So the sibling tests catch the mutation; this one does not.

## How to pick it up

1. Read the test and the `_survives_sync_regen_load` helper above it -- the fix
   pattern already exists in the same file, added in 5.2 round 2 for the `load`
   leg: assert the precondition, not only the postcondition.
2. Add `assert _VALID_TAG in first_bytes` (or equivalent) before comparing the
   two regenerations.
3. Prove it: with `carried = ""` applied at
   `src/fitdocs/render/frontmatter.py:153`, this test alone must red. It
   currently passes.

Done looks like: the test reds when the carry is dropped, instead of passing on
two identically-empty renders.
