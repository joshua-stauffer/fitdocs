---
id: 2026-08-23-provenance-record-cites-seven-destroyed-scratch-files
title: The provenance record cites seven now-destroyed scratch files by name as its evidence sources, without stating they no longer exist
status: open
importance: high
importance_why: This is the shipped, durable record of a purge, and it points a reader at evidence that cannot be produced. An auditor following any of the seven citations finds nothing, with no way to tell deliberate destruction from a lost file — and the record is the only artifact that outlives the machinery.
effort: S
kind: inconsistency
area: encumbered-content-purge, docs/reference
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge task 9.4 (scratch destruction), and both 9.4 reviewers independently
pinned_at: c786326
resume_command: "do: add a stated-positions note to docs/reference/history-rewrites.md recording that the scratch artifacts it cites were destroyed at task 9.4 under Req 12.3, so a reader can tell deliberate destruction from a lost file"
context:
  - docs/reference/history-rewrites.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/requirements.md
blocked_by: []
---

## What

`docs/reference/history-rewrites.md` cites nine `~/.fitdocs-purge/` paths,
seven of them naming specific evidence files:

- `certification-8-1.txt`, `identifiers-8-1.json` (task 8.1's certification
  and the pre-replacement identifier sample)
- `plan-paths.tsv`, `plan-content.tsv`, `rules.json` (the retired mechanism's
  plan and rule set, named in section 4)
- `remote-8-4.txt`, `identifier-probes-8-4.tsv` (task 8.4's dated remote
  measurements and the per-identifier probe table, named in section 7)

Task 9.4 destroyed the scratch directory. Measured 2026-08-23 after the
deletion: `ls -A ~/.fitdocs-purge/` returns exactly `forbidden-strings.tsv`.

The record does not say this anywhere.

## Why it matters

The maintainer was shown this consequence before the destruction and ruled for
literal execution of task 9.4's text — so the destruction is settled and is
**not** what this item asks to revisit. What is missing is one note.

A record whose citations dangle is weaker than one that says plainly "this
evidence was destroyed, deliberately, at task 9.4, under Req 12.3". The first
reads as rot; the second is an auditable position. The measurements themselves
already stand recorded *in the record's own prose* — section 7 reproduces the
probe results row for row — so nothing substantive was lost. Only the pointer
is now unresolvable, and only the record can say so.

Both task 9.4 reviewers raised this independently, the second rating it
`importance: high`.

## Evidence

```
$ grep -c "fitdocs-purge/" docs/reference/history-rewrites.md
9
$ ls -A ~/.fitdocs-purge/
forbidden-strings.tsv
```

The seven names appear at `docs/reference/history-rewrites.md` sections 4 and
7 (search for `fitdocs-purge/`; the ninth hit is an elided `.../` form).

## How to pick it up

Open `docs/reference/history-rewrites.md` and find section 6, "Stated
positions" — that is where this belongs, alongside the existing accepted
positions on the source workbooks and the shared agent log.

Add one paragraph: the scratch artifacts this record cites were destroyed at
task 9.4, under Req 12.3 and the maintainer's 2026-08-23 ruling; the
measurements they carried are reproduced in sections 3, 4 and 7 of this
record; the `.git` archive is **not** scratch and survives, governed by
Decision 7.

Hold it to the record's own standard, which three review rounds established
this run: one falsifiable proposition per sentence, and every `§N` pointer
opened and confirmed to contain what you claim.

Done when a reader following any of the seven citations finds the note before
they find the absence.
