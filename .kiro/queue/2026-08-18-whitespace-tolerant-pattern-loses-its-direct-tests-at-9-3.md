---
id: 2026-08-18-whitespace-tolerant-pattern-loses-its-direct-tests-at-9-3
title: A surviving helper's two direct unit tests live in a module task 9.3 deletes
status: open
importance: medium
importance_why: The helper survives Req 12 retirement while its only direct tests do not; coverage would drop silently at the deletion commit.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_replacements.py, tests/_forbidden_strings.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 review round 1)
pinned_at: dac1a7a
resume_command: "do: at task 9.3, relocate test_whitespace_tolerant_pattern_joins_words_with_flexible_whitespace and test_whitespace_tolerant_pattern_matches_across_a_line_wrap out of tests/purge/test_replacements.py before deleting it, or record that the helper is pinned only indirectly through matches()"
context:
  - tests/purge/test_replacements.py
  - tests/_forbidden_strings.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Task 7.2 moved `_whitespace_tolerant_pattern` into `tests/_forbidden_strings.py`,
where it survives the Req 12 retirement. Its two direct unit tests stayed in
`tests/purge/test_replacements.py`, which task 9.3 deletes entire.

## Why it matters

After 9.3 the helper would have no direct test. Coverage does survive
indirectly -- breaking the helper reds five `test_matches_*` tests in the
surviving module -- so this is a real but bounded loss. The problem is that it
would happen as an unremarked side effect of a deletion commit rather than as
a decision, which is precisely what Req 12.2 exists to prevent ("every
required guard survives and still demonstrably fails").

## Evidence

Confirmed at `dac1a7a`:

    tests/purge/test_replacements.py:119
      def test_whitespace_tolerant_pattern_joins_words_with_flexible_whitespace
    tests/purge/test_replacements.py:124
      def test_whitespace_tolerant_pattern_matches_across_a_line_wrap

Task 9.3's deletion list: `tests/purge/` less two named relocations
(`test_content_oracle.py`, `test_content_fingerprints_shape.py`) -- neither is
`test_replacements.py`.

Indirect coverage reported by the task 7.2 reviewer, which measured it:
`_whitespace_tolerant_pattern` joining with a literal space instead of `\s+`
reds nine tests, five of them `test_matches_*` in
`tests/test_forbidden_strings.py`.

## How to pick it up

At task 9.3, before deleting `tests/purge/test_replacements.py`, move the two
named tests to `tests/test_forbidden_strings.py` alongside the helper they
test. If instead you judge the indirect coverage sufficient, say so in the
provenance record's section 8 under Req 12.4's given-up-capability heading.
Done when the helper's pinning status after retirement is explicit.
