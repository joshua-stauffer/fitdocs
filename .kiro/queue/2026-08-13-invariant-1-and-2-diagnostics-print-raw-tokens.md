---
id: 2026-08-13-invariant-1-and-2-diagnostics-print-raw-tokens
title: Task 6.4's invariant 1 and 2 failure diagnostics still print raw identifying tokens, while invariant 3 and the identity assertions were masked
status: open
importance: medium
importance_why: These assertions fire precisely when the purge has failed to redact something, so the one run that produces output is the run that prints the forbidden values into pytest output, CI logs and review reports. The same hazard was closed on the neighbouring assertions in the same file during the 6.4 remediation.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge
created: 2026-08-13
pinned_at: c3d2201
resume_command: "do: Mask the survivor diagnostics in test_invariant_1_zero_identifying_tokens_in_surviving_blob_content and test_invariant_2_zero_identifying_tokens_in_commit_messages so a failure reports blob/commit ids and masked token tags rather than the raw matched tokens, following _masked_address's pattern in scripts/purge/replacements.py."
context:
  - tests/purge/test_replacements.py
  - scripts/purge/replacements.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

Both invariants build a `survivors` mapping whose values are tuples of the
**raw matched tokens**, then interpolate the whole mapping into the assertion
message. A failure therefore prints the identifying tokens themselves.

The 6.4 remediation masked the neighbouring assertions in this same file —
invariant 3 and all five identity acceptance relations now compare masked tag
sets — and added `_masked_address` for exactly this purpose. These two were not
in that task's boundary and were left as they were.

## Evidence

Verified in this run on branch `impl/replacement-rules` (worktree
`../fitdocs-replacement-rules`). **Note the line numbers moved four times
during the 6.4 remediation rounds; locate by test name, not by line.**

- `tests/purge/test_replacements.py:1584` —
  `test_invariant_1_zero_identifying_tokens_in_surviving_blob_content`, whose
  final assertion is
  `assert not survivors, f"invariant 1 violated in {len(survivors)} blob(s): {survivors}"`
  with `survivors[blob_id] = hit` and
  `hit = tuple(token for token in tokens if token.lower() in lowered)`.
- `tests/purge/test_replacements.py:1602` —
  `test_invariant_2_zero_identifying_tokens_in_commit_messages`, identical
  shape keyed by commit id.
- Established by execution during the 6.4 review: **pytest prints both operands
  in full even when an explicit assertion message is supplied**, so attaching a
  message does not suppress the values — the operands themselves must be
  masked. This was the finding that drove the identity assertions to compare
  masked tag sets rather than real ones.

## Why it matters

Unlike a diagnostic that leaks on a routine failure, these two are silent until
the purge is genuinely broken. The run that prints them is the run someone
pastes into an issue, a review report, or a CI log — the same shape as the
2026-08-09 incident in which an incident record explaining an identity leak
reproduced it.

## How to pick it up

1. Read `_masked_address` in `scripts/purge/replacements.py` and the masking
   banner in `tests/purge/test_replacements.py` — the pattern and its rationale
   are already written down there.
2. Change both `survivors` mappings to carry masked token tags, keeping the
   blob and commit ids unmasked (the 6.4 review confirmed ids stay useful and
   masking them would make the diagnostic unusable).
3. Keep what is asserted identical — this is a diagnostic change, not a
   coverage change. Confirm by mutation that both assertions still red when a
   token survives.

## Done when

A forced failure of either invariant reports masked tags and real ids, and no
raw identifying token appears in pytest output.
