---
id: 2026-08-18-replacement-verification-table-halves-disagree
title: The ReplacementVerification table's fresh-clone row and its per-row subject column disagree about what runs against C
status: open
importance: medium
importance_why: A driver implementing task 8.3 from either half alone runs a different set of rows against the verification clone.
effort: S
kind: inconsistency
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/design.md
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.4 review)
pinned_at: b7c5a3d
resume_command: "do: reconcile design.md's ReplacementVerification fresh-clone row (re-run the rows above) against the per-row Run-against column, which marks only one of those rows as C"
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - scripts/purge/verify.py
blocked_by: []
---

## What

`design.md` › `#### ReplacementVerification` states the fresh-clone row as
"re-run the rows above" against `C`. Its per-row **Run against** column marks
nine of those rows `F` and/or `W` only, and exactly one — "Old identifiers
refused" — as `W, C`.

So the table says two different things about what the verification clone is
for.

## Why it matters

Task 8.3 is "Take the reachable-only verification clone … re-run the rows
against it". An implementer reading the prose re-runs everything; one reading
the column re-runs the refusal row. The two produce materially different
evidence for the one verification pass that happens after the swap and before
any remote action.

Task 7.4 implemented a third reading. **Updated 2026-08-18 after its first
review round**: the set is now **four** rows — tree identity, path/blob token,
message token, and old identifiers refused — the last added because the
reviewer found the `C`-marked refusal row was the one row the composition
could not produce, having no `old_ids` operand. Reflog and unreachable stay
excluded, though the *reason* also had to be corrected: not "vacuous against a
fresh clone" (true only of the unreachable half) but that a `--no-local` clone
writes its own `clone: from ...` reflog entries, so the row would report **not
clean on every run by construction**.

## Evidence

Measured at `b7c5a3d` in `design.md` › `#### ReplacementVerification`: the
fresh-clone row reads "re-run the rows above"; the per-row column marks
`Old identifiers refused` as `W, C` and the remaining single-subject rows as
`F` and/or `W`.

Reported by the task 7.4 reviewer, which also observed the downstream
consequence: `check_fresh_clone` takes no `old_ids` operand, so the
composition cannot run the one row the column actually assigns to `C`.

## How to pick it up

Decide which half is authoritative and make the other match. The reflog and
unreachable rows genuinely are vacuous against a fresh clone, so "re-run the
rows above" cannot be literal. Likely outcome: an explicit `C` set in the
column, and the prose row restated to name it. Done when 8.3 can be
implemented from the table without a judgment call.
