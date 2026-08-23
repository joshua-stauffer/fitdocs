---
id: 2026-07-26-rewrite-map-not-durable
title: The pre/post history-rewrite SHA map survives only in one machine-local file
status: open
importance: medium
importance_why: Every commit SHA written down before 2026-07-26 — in closed queue items, prior transcripts, notes — resolves only through this map, and it lives untracked in .git on one machine with no backup.
effort: S
kind: chore
area: repo history, .kiro/queue/
created: 2026-07-26
surfaced_by: pushing the repo to GitHub after the author-email history rewrite
pinned_at: c3d2201
resume_command: "do: decide where the 2026-07-26 old->new commit SHA map lives durably -- commit it under docs/reference/ (or attach it to a git note/tag) rather than leaving it at .git/sha-rewrite-map-2026-07-26.tsv, and record whether refs/original/ may be expired once it is safe [queue: .kiro/queue/2026-07-26-rewrite-map-not-durable.md]"
context:
  - .kiro/queue/closed/
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

On 2026-07-26, every commit in this repo was rewritten to carry
`66793731+joshua-stauffer@users.noreply.github.com` as author and committer,
before the first push to GitHub. The rewrite was 1:1 and tree-identical, but it
changed all 174 SHAs.

Tracked files were repinned onto the new SHAs (`aa23908`, `b58cf81`), so the
repo itself is self-consistent. What is *not* durable is the ability to resolve
a pre-rewrite SHA that lives outside the repo — in an old session transcript, a
note, a closed queue item read from an old checkout, a browser tab. Two things
provide that today, and both are machine-local:

- `.git/sha-rewrite-map-2026-07-26.tsv` — the full 174-row old→new table.
  Untracked by construction (it is inside `.git/`), so it is in no clone, no
  push, and no backup.
- `refs/original/refs/heads/*` — the pre-rewrite tips left by `filter-branch`,
  which keep the old objects reachable. These are local-only refs and are
  exactly what one would delete to reclaim space; once expired, the old objects
  become unreachable and `git gc` drops them.

## Why it matters

The loss is silent and one-way. Nothing fails when the map disappears — an old
SHA simply stops resolving, and there is then no way to learn what it referred
to. This repo's whole methodology is evidence pinned to commits (see
`.kiro/queue/README.md`: "Evidence must be verifiable — `file:line`, a commit,
a command and its output"), so the pins are load-bearing, not decorative.

The exposure is bounded and known: 20 distinct pre-rewrite SHAs were cited in
tracked files, all repinned. The residual risk is citations that were never in
the repo.

## Evidence

At `b58cf81`:

```
$ git for-each-ref --format='%(refname) %(objectname:short)' refs/original/
refs/original/refs/heads/impl/athlete-benchmarks 39deef8
refs/original/refs/heads/impl/training-load      f34aee1
refs/original/refs/heads/main                    6c275c1

$ git ls-files --error-unmatch .git/sha-rewrite-map-2026-07-26.tsv
Did you forget to 'git add'?          # i.e. untracked
```

The map's own header records its provenance and that pairing was verified on
tree, parents, subject and author date for all 174 commits. The rewrite and the
repin are described in `aa23908`'s commit message.

Note the two impl branches were **not** pushed: `impl/athlete-benchmarks`
(`e50522c`) and `impl/training-load` (`2dcf75a`) exist only locally, so their
history — rewritten too — has no remote copy at all.

## How to pick it up

1. Read the header of `.git/sha-rewrite-map-2026-07-26.tsv` — it states the
   transformation, the date, and what was verified. Decide whether the map is
   repo history worth committing (e.g. `docs/reference/`) or metadata better
   carried as a git note or an annotated tag on the rewrite boundary.
2. Grep `.kiro/queue/closed/` for SHAs — those items are retained precisely so
   a reopened question can find prior reasoning, so they are the most likely
   consumers of the map.
3. Only after the map is durable, decide whether `refs/original/` may be
   expired (`git for-each-ref --format='delete %(refname)' refs/original |
   git update-ref --stdin`, then reflog expire + gc). Until then, leave it —
   it is the only copy of the pre-rewrite objects.

Done means: resolving a pre-rewrite SHA does not depend on one untracked file
on one machine, and the decision about `refs/original/` is written down rather
than left implicit.

## Open questions

- Whether the two unpushed impl branches should be pushed as well, so their
  rewritten history is backed up somewhere other than this laptop. That was a
  deliberate scope choice when `main` was pushed, not an oversight.

## Resolution (in progress)

**Correction (2026-08-05):** this section originally named a branch,
`chore/sha-map-durable`, that no longer exists as a ref -- it was merged to
`main` at commit `d8888b6` (`git merge-base --is-ancestor d8888b6 main`
confirms) and deleted afterward, the ordinary post-merge git workflow, not a
loss. A first correction attempt at this item claimed the map's committed
copy no longer exists anywhere, which was also false: `git ls-tree -r
--name-only refs/heads/main` and the same against `refs/remotes/origin/main`
both list the prior rewrite map's committed path today, at `main`
`85b3985` and `origin/main` `9e508e1`. The deletion is real, but it lives on
a *different*, unmerged branch: encumbered-content-purge's task 3.1 (commit
`a705490` on `impl/encumbered-content-purge`) removes the file (187 lines)
together with the `pyproject.toml` sdist-exclude section that had named it
(32 lines), and separately extracts the map's 174 data rows to an
out-of-repository scratch location (via tooling at `scripts/purge/
rewrite_map.py` and `tests/purge/test_rewrite_map_extraction.py`, which stay
in the repository -- they are the extraction code, not where the rows live)
before deleting it. `git merge-base --is-ancestor a705490 main` confirms
`a705490` is **not** an ancestor of `main` today. So the durable copy this
paragraph originally described is still on `main` and on the remote right
now; the deletion is scheduled but has not landed. The copy disappears, and
this item's durability question becomes live again, only once
`impl/encumbered-content-purge` merges to `main` -- not before.

**Correction (2026-08-09, encumbered-content-purge task 6.3):** this item's
own content carries the prior rewrite map's literal path in five places
(the `resume_command`, the bullet above, the evidence transcript, the
pick-up step 1, and this section) -- measured directly, not recalled: `grep
-n sha-rewrite-map-2026-07-26 .kiro/queue/2026-07-26-rewrite-map-not-durable.md`
at `f79622a`. Of those five, only **one** -- this section's "committed path"
reference two paragraphs up -- is a forbidden value at all: it names the
map's `docs/reference/`-rooted tracked path, which matches
`FITDOCS_FORBIDDEN_STRINGS`'s `path`-category entry for it literally. The
other four are `.git/sha-rewrite-map-2026-07-26.tsv` -- `.git/`-prefixed,
not `docs/reference/`-prefixed, so the fixed-string match against the
forbidden value never fires -- and Task 6.3 does not require redacting a
string that is not itself a forbidden value. Those four are restored to
their original literal form; only the one genuinely forbidden value (in the
"committed path" reference above) stays redacted. (An earlier
version of this paragraph replaced all five with descriptions and claimed
six places and a blanket Req 6.3 justification for every one of them; both
were wrong -- corrected here rather than re-asserted, per this item's own
"Correction" convention.) `scripts/purge/sweep.py`'s stale-basename probe
(`scripts/purge/sweep.py:505`) independently retains the same literal
basename `sha-rewrite-map-2026-07-26.tsv` as a needle, so restoring these
four does not create a gap that guard would otherwise have caught.

`refs/original/` still holds all three pre-rewrite tips
(`refs/original/refs/heads/{main,impl/athlete-benchmarks,impl/training-load}`,
reverified via `git for-each-ref refs/original/` — unchanged from the Evidence
section above). **Do not expire them yet.** Two reasons, both grounded in this
item's own text: (1) the map only becomes durable once this branch is merged
to `main` and, ideally, pushed — a merged-but-unpushed `main` is no more
backed-up than `refs/original` itself; (2) the two impl branches
(`impl/athlete-benchmarks`, `impl/training-load`) were deliberately never
pushed, so `refs/original` is their *only* copy of the rewritten history's
ancestry chain outside this one machine — expiring it would be one-way and
unrecoverable for objects with no other home. Revisit once
`chore/sha-map-durable` is merged to `main` and `main` is pushed; the
unpushed-impl-branches open question above is a precondition specifically for
expiring the two impl-branch `refs/original` entries, not just `main`'s.
