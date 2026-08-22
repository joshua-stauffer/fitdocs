---
id: 2026-08-22-the-Rm-verification-row-cannot-name-a-remote-url-as-its-subject
title: The Rm verification row cannot name a remote URL as its subject, and the design table still calls that remote "recreated"
status: open
importance: medium
importance_why: Amendment 2 requires every row to name its subject because two remotes may resolve at once, but RowResult.subject is typed Path and the Rm row is not implemented by the row machinery at all — so the one row where the ambiguity bites cannot express which URL it ran against.
effort: M
kind: inconsistency
area: encumbered-content-purge, scripts/purge
created: 2026-08-22
surfaced_by: kiro-review round 2 of chore/repo-rename
pinned_at: 1618b33
resume_command: "do: decide how the Rm verification row names its subject remote now that two URLs may resolve at once — widen RowResult.subject beyond Path, or state explicitly that Rm is reported by the RemoteReconciliation result types and not by RowResult"
context:
  - scripts/purge/verify.py
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Amendment 2 (2026-08-22) establishes that under the rename two remotes may
resolve simultaneously, so `"the remote"` is no longer self-naming and every
verification row must say which URL it ran against. Task 8.4's rows now do.

The `Rm` row cannot, for two independent structural reasons:

1. **`RowResult.subject` is typed `Path`** (`scripts/purge/verify.py:154`,
   with `:145` stating *"`subject` is the `Path` this specific call ran
   against"*). A remote URL is not a `Path`. Naming a subject URL is not
   expressible in the type.
2. **The `Rm` row is not implemented by the row machinery at all.**
   `scripts/purge/verify.py:198-203` records that it *"is implemented by the
   `RemoteReconciliation` functions below this section, which return
   `RefComparisonResult`/`ProbeResult`, never `RowResult`"*.

Separately, the design still describes that remote as recreated:

- `design.md:1661` — ``Rm` (a fresh clone from the **recreated remote**)`
- `design.md:1679` — the Req 8.2 table row: `| … | Rm | fresh clone from the
  **recreated remote** | … |`

Those two sit inside Amendment 2's "left standing" carve-out and so are
defensible as the record of Decision 6's design. But the carve-out's
justification is *"read, not executed"*, and this component's Intent line is
the design contract the executing task implements — which is the weakest place
for that justification to hold.

The shipped docstring at `scripts/purge/verify.py:11` was corrected on
`chore/repo-rename` (*"recreated remote"* → *"published remote"*) because it
ships in the certified tree under Req 10.3 with no later redaction step. The
`design.md` rows were deliberately left, and this item is that decision's
record.

## Why it matters

Req 8.2, 8.3 and 8.5 all say a bare `"the remote"` — they were written when
only one existed. Under the rename, evidence that does not name its subject
URL is exactly the "row run against the wrong one is not evidence" failure the
`Rm` row's own acceptance bullet warns about. Task 8.4 works around this by
naming subjects in its prose, but nothing in the machinery enforces it.

This is not blocking Major 8: 8.4's probes and ref comparison name their
subjects in the task text, and `RefComparisonResult`/`ProbeResult` are what
actually carry the remote evidence. It is a gap between what the amendment
asserts ("every row names its subject URL") and what the code can represent.

## How to pick it up

Two coherent options.

**(a) Widen the subject.** Make `RowResult.subject` accept a `Path | str`, or
add a distinct field for a remote subject, so an `Rm`-shaped row can carry a
URL. Costs a type change across the row machinery and its tests.

**(b) State the exception.** Amend the design to say that `Rm` is reported by
`RefComparisonResult`/`ProbeResult` — which should then be checked to carry
their own remote identity — and that `RowResult` is a local-repository
construct by design. Cheaper, and closer to what the code already does.

Whichever is chosen, also correct `design.md`'s *"recreated remote"* at
`:1675` and `:1693` (pinned at `236fc18`) if the row is being touched anyway.

**That last check has now been measured, and it found the real gap.** As of
`236fc18`, in `scripts/purge/verify.py`:

- `ProbeResult` **does** carry the remote identity — `identifier: str,
  url: str, status_code: int, served: bool`.
- `RefComparisonResult` **does not** — `passed: bool,
  missing_from_remote: tuple[str, ...], remote_only: tuple[str, ...]`, with no
  URL, path, or other subject field at all.

So the answer is half-and-half, and **the missing half is the ref comparison,
which is the Req 8.5 row** — one of the four criteria Amendment 2 singles out
as saying a bare `"the remote"`. Under two simultaneously-resolving remotes, a
`RefComparisonResult` cannot say which one it compared against, and neither
option (a) nor option (b) above closes that as written: (a) widens
`RowResult`, which the `Rm` row does not use, and (b) declares
`RefComparisonResult`/`ProbeResult` authoritative for `Rm` while one of them
carries no subject.

Treat this as the item's centre of gravity: **give `RefComparisonResult` a
remote-identity field**, matching `ProbeResult`'s `url`, and only then decide
the `RowResult` question. Task 8.4 currently compensates in prose by naming
`fitdocs` in the row's own text; that is a task-level workaround, not a
machinery-level one, and it does not survive into the recorded evidence.
