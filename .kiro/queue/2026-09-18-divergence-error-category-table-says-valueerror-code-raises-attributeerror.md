---
id: 2026-09-18-divergence-error-category-table-says-valueerror-code-raises-attributeerror
title: design.md's Error Categories table promises ValueError for the selected-channel programming-error case; the shipped code deliberately raises AttributeError instead
status: open
importance: low
importance_why: Unreachable from any user-controlled path (it's a calculator precondition violation, not user data), so nothing is at risk in practice -- pure prose/code mismatch.
effort: S
kind: inconsistency
area: activity-qa-flags, .kiro/specs/activity-qa-flags/design.md
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags feature-level validation pass (Finding G-3)
pinned_at: d26b682
resume_command: "do: change design.md's Error Categories table row for 'Selected channel is not a ChannelLoad' (around design.md:1615) from ValueError to AttributeError, matching src/fitdocs/load/qa/divergence.py's own documented, deliberate choice"
context:
  - .kiro/specs/activity-qa-flags/design.md
  - src/fitdocs/load/qa/divergence.py
---

## What

`design.md`'s Error Categories table (`design.md:1615`) says the
"Programming error: Selected channel is not a `ChannelLoad`" case raises
`ValueError`. The shipped `divergence.py` deliberately lets this raise
`AttributeError` instead -- documented explicitly in two places in that
module (lines 99, 170-171): treating a `ChannelInsufficient` as a
`ChannelLoad` naturally raises `AttributeError` on `.intensity`, and the
module comments this is intentional rather than a guarded `ValueError`.

## Why it matters

This is a precondition violation unreachable from any real activity or
configuration -- the calculator only calls `evaluate_flags` after a
successful selection, so `outcomes[selected]` is always a `ChannelLoad` in
practice. The mismatch is between two documents (design.md and the shipped
module's own comments), not a behavioral risk.

## Evidence

Verified at `d26b682`:
- `.kiro/specs/activity-qa-flags/design.md:1615`: `| Programming error |
  Selected channel is not a `ChannelLoad` | `ValueError`; unreachable from
  user data |`
- `src/fitdocs/load/qa/divergence.py:99`: "...gets an `AttributeError` from
  treating it as a..."
- `src/fitdocs/load/qa/divergence.py:170-171`: "`ChannelInsufficient` here
  is a programming error and raises naturally (`AttributeError` on
  `.intensity`) rather than being guarded against"

## How to pick it up

1. Open `.kiro/specs/activity-qa-flags/design.md`, find the Error
   Categories table (`grep -n "Programming error"`).
2. Change `ValueError` to `AttributeError` in that row, matching what
   `divergence.py` actually raises and documents.

Done looks like: the table and the code agree.

## Open questions

None.
