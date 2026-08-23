---
id: 2026-08-13-invariant-1-and-2-diagnostics-print-raw-tokens
title: Positive-control assertions print raw identifying tokens into pytest output — the originally-named invariant tests were deleted at task 9.3, but the class survived in the retained guard module
status: open
importance: medium
importance_why: These assertions fire precisely when the purge has failed to redact something, so the one run that produces output is the run that prints the forbidden values into pytest output, CI logs and review reports. The same hazard was closed on the neighbouring assertions in the same file during the 6.4 remediation.
effort: S
kind: gap
area: encumbered-content-purge, tests
created: 2026-08-13
pinned_at: c3d2201
resume_command: "do: mask the raw forbidden values printed by the positive controls in tests/test_forbidden_strings.py (see Surviving instances) -- the originally-named tests were deleted at task 9.3 but the class survived the retirement"
context:
  - tests/test_forbidden_strings.py
  - docs/reference/history-rewrites.md
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

> **UPDATE 2026-08-23 (task 9.3/9.4 run): the two named tests are GONE, but the
> defect class SURVIVED the retirement and this item is still live.**
> Task 9.3 deleted `tests/purge/` entire, taking both
> `test_invariant_1_...` and `test_invariant_2_...` with it. The original
> subject below is therefore moot. **Do not close this item on that basis** —
> the same shape survives in a guard module that was retained, and a real
> forbidden value was printed into an agent report during this very run. The
> live sites are listed under *Surviving instances* below; retarget the item to
> those.

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

## Surviving instances (2026-08-23, the live subject)

Both in `tests/test_forbidden_strings.py`, which task 9.3 **retained**:

- `:875-877` — the path-surface positive control:
  `assert (Path(f"{supplied}-in-the-name.txt"), "path") in by_path_surface`,
  where `supplied = forbidden_strings.values[0]`. pytest prints the operands of
  a failed `in` comparison, so the raw value appears verbatim in the output.
- `:1335-1337` — three assertions of the form
  `assert _count_notice_phrase(planted_flat) == 1, planted_flat`, where the
  message *is* the planted text and spells out the notice phrase.

Confirmed reachable, not theoretical: the task 9.4 reviewer hit `:875-877`
while mutating the guard's walk, and the raw value appeared in its run output.

Independently, an implementer subagent this run printed a real forbidden value
verbatim into its status report, using it as a liveness control — the same
class arriving through a different door. **Positive-control results should be
reported as counts and shapes ("9 of 9 planted values detected"), never as the
matched strings.** That convention was applied to every later probe this run and
is worth writing into the guards' own docstrings.

## How to pick it up

The original masking helper (`_masked_address` in
`scripts/purge/replacements.py`) was deleted at task 9.3, so the pattern must be
re-created rather than reused. Its rationale survives in
`docs/reference/history-rewrites.md`'s guard sections.

1. For `:875-877`, restructure so the assertion compares a boolean or a masked
   key rather than a tuple containing the value — pytest cannot print what the
   comparison does not carry.
2. For `:1335-1337`, replace the bare `planted_*` message with a masked
   description (length, category, match count), keeping the count assertion
   itself unchanged.
3. Keep what is asserted identical — this is a diagnostic change, not a coverage
   change. **Confirm by mutation that each assertion still reds**, and revert
   from a snapshot copy rather than `git checkout`.
4. Consider a guard-of-a-guard: a test asserting no assertion message in the
   module interpolates a `forbidden_strings.values` element. Without it this
   class will return a fourth time.

## Done when

A forced failure of any positive control in `tests/test_forbidden_strings.py`
reports masked tags, counts and shapes, and no raw identifying token appears in
pytest output or in any agent report.
