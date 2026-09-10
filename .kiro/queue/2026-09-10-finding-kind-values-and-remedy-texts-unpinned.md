---
id: 2026-09-10-finding-kind-values-and-remedy-texts-unpinned
title: FindingKind's published string values and every _REMEDY_ constant can be changed with the whole suite green
status: open
importance: medium
importance_why: FindingKind is a published StrEnum in audit.__all__, so its values are a downstream-visible contract, and the remedy texts are normative in design.md -- both can drift without any test failing.
effort: S
kind: gap
area: audit, src/fitdocs/audit.py, tests/test_audit.py
created: 2026-09-10
surfaced_by: /kiro-impl effort-tags task 3 (adversarial review, own mutations M5/M8 plus baseline probes B1/B2)
pinned_at: ca45aa9
resume_command: "do: add one conformance test pinning every FindingKind value and every _REMEDY_ constant byte-exactly against the design, so a value or wording change cannot land green"
context:
  - src/fitdocs/audit.py
  - tests/test_audit.py
  - .kiro/specs/effort-tags/design.md
blocked_by: []
---

## What

`FindingKind` is a `StrEnum` exported in `fitdocs.audit.__all__`, so its **string
values** — not just its member names — are visible to anything that consumes a
finding. The `_REMEDY_*` constants are specified verbatim in `design.md`.

Neither is pinned. A reviewer changed `INVALID_EFFORT_TAG`'s value from
`"invalid_effort_tag"` to `"malformed_effort_tag"` and the **full suite stayed
green** (3261 passed). The same holds for the pre-existing members and remedies,
so this is a module-wide property rather than anything task 3 introduced.

Tests assert on `FindingKind.X` by member reference and on remedies by
*fragment*, so the value and the exact wording are both free to drift.

## Why it matters

A `StrEnum`'s value is what appears when a finding is serialised, logged,
compared against a string, or read by any downstream consumer. Renaming a member
is a visible refactor; changing its value silently changes an external contract
and nothing objects.

The remedy texts have a second reason: they are the words a user reads when
`fitdocs check` tells them what to do. `design.md` fixes them precisely so every
reporter prints the same sentence — the same reasoning that made the effort-tag
detail texts byte-exact — and there is no mechanism holding the code to the doc.

This is the same class the repo already solved elsewhere: `MANAGED_KEYS` has an
anti-drift test holding it equal to what the frontmatter builder emits, and the
ownership contract has a conformance test. `FindingKind` has neither.

## Evidence

At `ca45aa9`; measured on branch `impl/effort-tags` during task 3's review.

Four mutations, each run through `uv run pytest`, each leaving the **whole suite
green**:

- `INVALID_EFFORT_TAG = "invalid_effort_tag"` → `"malformed_effort_tag"` — green
  (3261 passed)
- `UNMANAGED_KEYS`'s value changed on the **pre-existing** enum — green (baseline
  probe, proving this is not new)
- a one-word edit to the new `_REMEDY_FIX_EFFORT_TAG` — green
- a one-word edit to the pre-existing `_REMEDY_MOVE_UNMANAGED` — green

The reviewer classified these as "the module's pre-existing assertion
granularity, not a regression this task introduced", and did not reject on them.

## How to pick it up

1. Read `src/fitdocs/audit.py` — `FindingKind` and the `_REMEDY_*` constants —
   and the remedy/finding-kind text in `.kiro/specs/effort-tags/design.md` and
   any other spec that specifies one.
2. Decide the source of truth. If the design documents are authoritative, the
   test should compare against text quoted in the test itself (the way the
   effort-tag rule table was pinned in task 1.2), not re-derive it from the code.
3. Add one conformance test asserting **every** `FindingKind` member's value and
   **every** `_REMEDY_*` constant byte-exactly. Prefer an exhaustive mapping
   compared with `==` over per-member asserts, so adding a member without
   updating the test fails rather than passing silently.
4. Name the mutation and run it: change one enum value and one remedy word, and
   confirm the new test reds for each. Done means neither can drift green.

## Open questions

Whether the remedy strings should live in the design docs at all, or whether the
code should be the source of truth with the docs generated or conformance-tested
against it — the repo already does the latter for the ownership contract, so
there is a precedent either way.
