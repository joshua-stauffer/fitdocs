---
id: 2026-07-30-purge-brief-carries-superseded-counts
title: The purge brief's history figures are stale, and one of them is wrong in a way that understates the rewrite
status: done
importance: medium
importance_why: Design reads brief.md as the evidence base for a one-shot destructive operation. Three of its counts have simply moved, which is harmless; but "11 commits touch these paths" is not a moved number, it is incorrect, and it invites a design that scopes the rewrite to a subset of history when in fact exactly one live commit -- the root -- introduces the material and every commit reaches it.
effort: S
kind: inconsistency
area: encumbered-content-purge
created: 2026-07-30
surfaced_by: /kiro-spec-requirements encumbered-content-purge -- research contradicted four figures in brief.md
pinned_at: c378229
resume_command: "do: correct the four superseded history figures in .kiro/specs/encumbered-content-purge/brief.md against a fresh measurement, keeping requirements.md's Introduction as the reconciled statement [queue: .kiro/queue/2026-07-30-purge-brief-carries-superseded-counts.md]"
context:
  - .kiro/specs/encumbered-content-purge/brief.md
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/steering/roadmap.md
blocked_by: []
closed: 2026-07-30
closed_by: 07f274e
---

## Resolution (2026-07-30, `07f274e`)

Done, and the fix went further than the item asked. Re-measuring on pickup
found the three "merely moved" figures had moved **again** in the ninety
minutes since the item was written — 415 → 422 commits, 160 → 162 pinned queue
files, 21 → 28 behind `origin` — which answers this item's own open question:
live counts do not belong in prose here at all. Every one was replaced by the
property it was evidence for, plus the command to re-derive it.

The substantive correction landed as the item predicted it should: `brief.md`
now says **exactly one** commit touches the paths, and says why that is *worse*
than eleven rather than better — the material is in the initial tree, so every
commit carries it and none can be rewritten in isolation.

Two things were also corrected that this item did not list: `"158 queue items
carry a pinned_at:"` understated the class (it is every item without exception,
162 of 162 files), and `requirements.md`'s own "facts of record" paragraph,
written earlier in the same session, was falsified by the re-measurement and
now rests on shape rather than number.

`roadmap.md` Phase 5's copies moved in the same change, per step 4. Four
`"merged at <sha> with N tests green"` records and `brief.md`'s account of the
guard incident were deliberately left frozen: they are snapshots of past
events, and "correcting" them would falsify the record.

**Not fixed here, filed instead**: reading Phase 5 end to end for the
steering-class validation surfaced that it still states three constraints the
requirements phase settled the other way — see
`.kiro/queue/2026-07-30-phase5-constraints-outrank-settled-requirements.md`
(high). That is rule movement, not count drift, and did not belong in this
change.

## What

`.kiro/specs/encumbered-content-purge/brief.md` states four figures about the
repository's history. Measured on 2026-07-30 at `c378229`, three have moved and
one is wrong:

| brief.md | says | actually |
|---|---|---|
| :64-66 | "**11 commits** touch the encumbered material's paths" | **1** on `main` (the root commit), plus 1 reachable only from `refs/original/*` |
| :66 | "rewrites all **401 commits** on `main`" | **415** |
| :72-73 | `origin/main` is "**seven** behind local `main`" | **21** behind |
| :248 | "**158** queue items carry a `pinned_at:` field" | **160** files: 113 open items + `README.md` + 46 closed |

`.kiro/steering/roadmap.md` Phase 5 repeats the 401 and 158 figures and has the
same drift.

`requirements.md` already restates all four correctly in its Introduction and
deliberately writes no acceptance criterion against any of them, so the spec is
not blocked on this. The brief is what is stale.

## Why it matters

The three moved numbers are ordinary drift and cost nothing — they are dated
facts about a repository that kept committing after discovery.

**The commit count is a different kind of error.** "11 commits touch these
paths" reads as though the encumbered material was added and edited across a
span of history, which would make a path-scoped rewrite of those commits sound
like a bounded operation. The measurement says the opposite: the material was
introduced by the root commit and never touched again, so *every* commit's tree
contains it and the rewrite is unavoidably total. The brief's own conclusion
("a purge rewrites all 401 commits") happens to be right, but it is right for a
reason the stated premise contradicts — and a design that trusts the premise
over the conclusion would scope the rewrite too narrowly.

## Evidence

Measured at `c378229` on `main`:

```
$ git log --oneline --full-history main -- <the writeup's and the extracted tables' paths> | wc -l
1
$ git log --oneline --full-history --all -- <the writeup's and the extracted tables' paths> | wc -l
2          # the second is reachable only from refs/original/*
$ git rev-list --max-parents=0 HEAD
32aed726eba17aaa517e56ab9e4717e7518c86c9    # the one commit that touches them
$ git rev-list --count main
415
$ git rev-list --count origin/main..main
21
$ grep -rl "pinned_at:" .kiro/queue/ | wc -l
160
```

## How to pick it up

1. Re-measure all four rather than copying the table above — the counts move
   with every merge, which is the whole point.
2. Correct `brief.md` in place. Keep the conclusion at :66; replace the premise
   with what the measurement actually shows (introduced at the root commit,
   never subsequently modified, therefore reachable from every commit).
3. Decide whether to date-stamp the figures ("as of <date>") so the next reader
   knows they are a snapshot, which is what `requirements.md`'s Introduction
   does.
4. `.kiro/steering/roadmap.md` Phase 5 carries the 401 and 158 figures too;
   move them in the same change or the inconsistency just relocates. Note this
   makes the change class `.kiro/steering/**`, not `.kiro/specs/**`.

## Open questions

- Is it worth carrying live counts in prose at all, given they are stale within
  a day? An alternative is to state the *property* (every commit reaches the
  material; every pin is invalidated) and leave the counts to measurement.
