---
id: 2026-08-04-present-tense-claims-about-removed-material-survive-redaction
title: Present-tense claims about the removed material survive in four redacted files, correctly out of redaction-only scope
status: open
importance: medium
importance_why: Each asserts as current a state that ceased to exist at 3.1. They are approved spec text a later session will read as fact.
effort: S
kind: inconsistency
area: encumbered-content-purge, distribution, threshold-load
created: 2026-08-04
surfaced_by: /kiro-impl encumbered-content-purge (tasks 3.6-3.8 reviews)
pinned_at: c3d2201
resume_command: "/kiro-impl encumbered-content-purge [queue: .kiro/queue/2026-08-04-present-tense-claims-about-removed-material-survive-redaction.md] Past-tense the surviving claims about the removed material"
context:
  - .kiro/specs/encumbered-content-purge/brief.md
  - .kiro/specs/distribution/research.md
  - .kiro/specs/distribution/design.md
  - .kiro/specs/threshold-load/brief.md
blocked_by: []
---

## What

Four files assert in the present tense a state that ended when task 3.1 deleted
the encumbered material. Every one was **deliberately** left alone by task 3.8
under its redaction-only rule, and its reviewer confirmed each was already false
at HEAD — the token substitution changed no truth value, so correcting them was
out of that task's scope. They are collected here so the deferral is recorded
rather than inherited silently.

- `.kiro/specs/encumbered-content-purge/brief.md` — asserts `CLAUDE.md` "points
  at the writeup as a key reference and goes stale with it". Task 3.5 removed
  that bullet at `9d8ef1c`. The line also carries a line-number citation, which
  this spec's own execution rules forbid ("Line citations are not used… Locate
  by name").
- `.kiro/specs/distribution/research.md:64-65` — "`docs/` holds … the reference
  writeup, and the extracted tables". It does not.
- `.kiro/specs/distribution/design.md:82` — "The encumbered material is
  committed and packaged by design."
- `.kiro/specs/threshold-load/brief.md` — states the withdrawn calculator stays
  registered and untouched. False since `6386361` deleted that package.

## Why it matters

These are approved spec documents. A session reading `distribution/design.md`
to implement the packaging work will read that the encumbered material is
"committed and packaged by design" and plan around a state that no longer
exists. The `brief.md` line additionally points a reader at `CLAUDE.md`
expecting a reference that was removed three tasks ago.

None of this blocks the purge — the material is gone from the tree either way,
and no matcher flags any of these lines. It is a record-fidelity problem, which
is what Req 11.6 exists for.

## Evidence

```
# Drive the search from the out-of-repository match data rather than typing a
# token here -- Req 11.1 binds this file too, and a literal search command in a
# comment is how a bare token has repeatedly reached a tracked file in this spec.
$ FITDOCS_FORBIDDEN_STRINGS=... uv run python -c "..."   # matches() over CLAUDE.md
# no hit -- the key-references bullet was removed at 9d8ef1c (task 3.5)

$ git ls-files docs/reference/
docs/reference/fitdocs-ai-reference.md
docs/reference/history-rewrites.md
docs/reference/pkm-integration.md

$ git show --stat 6386361 -- src/fitdocs/load/
# the withdrawn calculator's package is deleted, not renamed
```

Each of the four lines is byte-identical at `HEAD` and at `34b4164` — task 3.8
never touched any of them in any of its three rounds.

## How to pick it up

1. Confirm all four sites still read in the present tense at the current tip.
2. Past-tense each **without** repointing at a removed path. Task 3.7 set the
   committed form (`f1ef31b`): replace the pointer with a role description. A
   de-tokenised path string names a file that has never existed — task 3.8 shipped
   that fabrication to 13 sites and it took two review rounds to remove.
3. Drop the line-number citation in `brief.md` rather than updating it, per the
   execution rule.
4. Done looks like: no surviving sentence asserts the material is present,
   tracked, packaged or registered; no new path string is introduced that
   `git rev-list --all | xargs -n1 git ls-tree -r --name-only | sort -u` does
   not contain.

## Open questions

Whether `distribution`'s and `threshold-load`'s documents should be corrected by
this spec at all, or left to their owning specs. They are approved documents of
other specs, and this spec's mandate over them is redaction, not revision — which
is precisely why 3.8 left them. The conservative reading defers all three
non-purge files to their owners and fixes only `brief.md`.

## Progress note (2026-08-23, `b4ccfa4`) — narrowed to the distribution half

Of the four files this item names, one is fixed and one was dropped:

- **`.kiro/specs/threshold-load/brief.md` — FIXED.** It stated the withdrawn
  calculator "stays registered and untouched". Amendment 1 now heads the file
  and each false claim is marked in place, per retain-the-record. This mattered
  more than the others: threshold-load is the next spec on the critical path,
  and the brief is the first thing its implementer reads. The correction also
  records what the deletion actually implies — `threshold` is the first and
  **only** built-in calculator, there is no arbitration contest, and shipping it
  is what makes training load computable at all.
- **`.kiro/specs/encumbered-content-purge/brief.md` — no longer in scope.** That
  spec completed 2026-08-23 and its internal documents are archival; the
  post-purge triage dropped the sibling items against them for that reason.

**Still open, both in `distribution`, which is unstarted:**

- `.kiro/specs/distribution/research.md:64-65` — "`docs/` holds … the reference
  writeup, and the extracted tables". It does not.
- `.kiro/specs/distribution/design.md:82` — "The encumbered material is
  committed and packaged by design."

These are the two the item's own "Why it matters" singled out as dangerous — a
session reading `design.md` to implement packaging will plan around a state
that no longer exists. Fold them into distribution's owed amendments rather
than fixing them in isolation; roadmap.md's Phase 5 entry already records that
two amendments are owed and should be written once against the final state.
