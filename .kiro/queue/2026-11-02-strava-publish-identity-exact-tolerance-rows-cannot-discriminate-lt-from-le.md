---
id: 2026-11-02-strava-publish-identity-exact-tolerance-rows-cannot-discriminate-lt-from-le
title: "Identity tolerance tests with exact-tolerance rows cannot tell < from <= because of a 1e-9 slack"
status: open
importance: low
importance_why: "Inclusivity of the tolerance edge is pinned by one test only."
effort: S
kind: chore
area: "tests/identity/test_matching.py, tests/identity/test_strict.py, src/fitdocs/identity"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 1.1 review"
pinned_at: 964cc419
resume_command: "do: make the exact-tolerance rows use values one ulp apart so < and <= differ, or state that test_within_is_inclusive is the sole pin (read .kiro/queue/2026-11-02-strava-publish-identity-exact-tolerance-rows-cannot-discriminate-lt-from-le.md first)"
context:
  - tests/identity/test_strict.py
  - tests/identity/test_matching.py
  - src/fitdocs/identity
blocked_by: []
---

## What
The exact-tolerance rows pass through a `1e-9` slack in the comparison, so the rows would pass with either comparison; only `test_within_is_inclusive` pins inclusivity.

## Why it matters
A refactor to `<` would pass most of the tests.

## Evidence
`tests/identity/test_strict.py:59` (`(1.0 * (1.0 + 1e-9), 1.0, True),  # the slack's own edge`) and `:65` `def test_within_is_inclusive`. The test_matching.py half is reported by reviewer subagent, unverified.

## How to pick it up
Run the named mutation (change `<=` to `<` in the comparison) and see which tests fail; add a row if only one does.
