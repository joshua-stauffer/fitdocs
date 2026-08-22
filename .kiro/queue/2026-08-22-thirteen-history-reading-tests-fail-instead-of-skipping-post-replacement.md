---
id: 2026-08-22-thirteen-history-reading-tests-fail-instead-of-skipping-post-replacement
title: Thirteen history-reading tests fail instead of skipping after the replacement — task 7.2's era re-scope covered one test and missed its siblings
status: open
importance: high
importance_why: They turn the post-replacement operator validation run red, which is the exact signal task 8.3 tells an operator to treat as a swap-back — so the next reader of a red suite must re-derive, under pressure, that these are expected. Task 9.3 retires them, but 9.1 and 9.2 run first and both expect a green battery.
effort: M
kind: gap
area: encumbered-content-purge, tests/purge
created: 2026-08-22
surfaced_by: Major 8 task 8.3, the real post-swap validation run
pinned_at: c3d2201
resume_command: "do: era-scope the thirteen history-reading tests so they skip with a named post-replacement reason rather than failing, the way task 7.2 scoped the source-liveness test"
context:
  - tests/purge/test_replacements.py
  - tests/purge/test_tree_removal.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

After task 8.2's swap, `uv run pytest` **with** `FITDOCS_FORBIDDEN_STRINGS`
supplied reports **6 failed, 7 errors** (4159 passed, 5 skipped). Without the
source it is fully green: 4140 passed, 37 skipped.

All thirteen have **one root cause**: they read pre-replacement history, which
the replacement destroyed by design.

The seven errors are a single module-scoped fixture in
`tests/purge/test_replacements.py` running
`git cat-file -p 7ae5117898cdcfe9eb2c6c15f14dcad039acc731` — exit 128:

- `test_invariant_1_zero_identifying_tokens_in_surviving_blob_content`
- `test_invariant_1b_zero_dotted_module_path_mangled_forms`
- `test_invariant_3_zero_identity_leaks`
- `test_invariant_4_zero_mangled_forms`
- `test_invariant_4b_zero_abbreviation_over_capitalisation`
- `test_invariant_5_zero_sentence_start_lowercasings`
- `test_acceptance_changed_python_blobs_still_ast_parse`

The six failures each lose a precondition history supplied:

- `test_removed_paths_actually_existed_before_the_deletion` — its
  `_existed_before_deletion` positive control cannot confirm the needle set
- `test_identity_denylist_is_exactly_the_leaks_the_tip_does_not_hold` —
  `len(token_domain) == 1` gets 0; the domain derives from historical blobs
- `test_identity_denylist_is_identical_in_a_clone[mirror]` and `[no-local]`
- `test_invariant_6_tip_no_op_over_the_working_tree` — the derived rule set
  collapses to 2 rules without history
- `test_acceptance_unrelated_copyright_population_is_untouched` — asserts
  `91 > 100`; the copyright-sign population is a **sample-size precondition**
  that only thousands of historical objects satisfied

## Why it matters

**These are not wrong tests and the replacement is not defective.** The
variable was isolated by measurement, not by reading:

| | replaced repo | archive |
|---|---|---|
| the 4 "never existed" paths | unverifiable | **2 commits each** |
| blob `7ae51178` | absent | **present** |
| objects | 754 | **5,774** |

Their claims are true and merely unverifiable from a single-commit
repository. The failures are evidence the replacement *worked*.

The cost is the signal. Task 8.3 tells the operator that any red in this
battery is a swap-back, and this red arrives at exactly that moment. It was
resolved here by diagnosis; the next reader gets the same red with less
context. Tasks 9.1 and 9.2 both run before 9.3 retires this machinery, and
both expect a green battery.

## The gap this exposes

Task 7.2 re-scoped the **era signal** so that the source-liveness test reports
a *named post-replacement skip* rather than a failure — and task 8.3's text
anticipates exactly that one test. That re-scope was correct and is working;
it simply covered one member of a class with at least thirteen.

The generalisable lesson, and it is the session's recurring one: an era signal
introduced for one call site is a mechanism, and a mechanism applied at one
site is not a policy. The sweep that should have followed 7.2 was "which other
tests read pre-replacement history?", and `git grep` for `cat-file`,
`rev-list` and `log --all` under `tests/purge/` answers it mechanically.

## How to pick it up

Apply 7.2's era signal to all thirteen so each **skips with a named
post-replacement reason**. Then run the mechanical sweep above and scope
whatever else it finds, rather than fixing these thirteen alone — the
enumeration is the deliverable, not the individual fixes.

Two traps, both already paid for elsewhere in this spec:

1. **Do not make them skip unconditionally.** A skip that fires pre-
   replacement destroys real coverage for anyone running the suite on a
   repository that still has history. The condition must be the era, tested,
   with a pre-replacement fixture proving the test still runs and still can
   fail there.
2. **`test_acceptance_unrelated_copyright_population_is_untouched` needs a
   decision, not a skip.** Its `> 100` threshold encodes a sample size that no
   longer exists; skipping it post-replacement is honest, but if the check is
   wanted at all afterwards it needs a threshold derived from the
   single-commit population (91) rather than the historical one.
