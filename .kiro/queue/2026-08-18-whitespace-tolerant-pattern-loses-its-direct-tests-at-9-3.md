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
pinned_at: c3d2201
resume_command: "do: task 9.3 has run and the two direct tests were NOT relocated -- _whitespace_tolerant_pattern (tests/_forbidden_strings.py:162) is now pinned only indirectly through matches(). Either write direct unit tests for it in tests/test_forbidden_strings.py, or record at the helper site that indirect pinning is the accepted state."
context:
  - tests/test_forbidden_strings.py
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

## Triage note (2026-08-23)

Re-pointed during the post-purge queue triage. Task 9.3 deleted `scripts/purge/` entire and `tests/purge/` less three relocations, so this item's `resume_command` and `context:` named paths that no longer exist. The **subject** was checked against the tree rather than inferred from the path, per `.kiro/queue/closed/2026-08-23-forty-five-queue-items-cite-the-retired-purge-machinery.md`; it survives in the retained guards and the item still stands. Only the locators changed — the finding above is unedited.
