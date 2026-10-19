---
id: 2026-09-11-regen-destroys-load-keys-on-foreign-or-superseded-region
title: fitdocs regen permanently destroys the three load keys when the load region is FOREIGN or SUPERSEDED
status: done
importance: high
importance_why: Silent, permanent loss of computed data on a documented-as-safe command, and the published contract promises the opposite.
effort: M
kind: bug
area: src/fitdocs/load/engine.py, src/fitdocs/render/frontmatter.py, docs/ownership-contract.md
created: 2026-09-11
surfaced_by: review of queue item 2026-09-11-ownership-doc-placement-unconditional
pinned_at: 1dc8633
resume_command: "do: land the finished fix on origin/chore/q-regen-load-keys -- rebase onto main, resolve the CHANGELOG.md and wiki-contract spec conflicts (contract version is now 16 on main), re-run the three gates, merge per change-protocol.md, then close this item"
context:
  - src/fitdocs/load/engine.py
  - src/fitdocs/load/docedit.py
  - src/fitdocs/render/frontmatter.py
  - docs/ownership-contract.md
blocked_by: []
---

## What

`fitdocs regen` (and `sync`) is two passes. The engine rebuilds the frontmatter
block from scratch via `build_frontmatter`, which never emits `load_value`,
`load_methodology` or `load_basis` -- so any existing occurrences are dropped
with the rest of the old block. The training-load pass then runs separately
(`cli.py::_run_load_pass`) and normally puts them back.

When the load pass *skips* the document, nothing puts them back and the three
keys are gone permanently. Two reachable states do this:

- **FOREIGN** -- the user hand-authored the `load` region. The pass leaves it
  alone by design.
- **SUPERSEDED** -- the region holds a prior-format payload. `LOAD_PAYLOAD_VERSION`
  is `2` (`src/fitdocs/load/render.py:63`), so v1 documents are a shipped
  artifact, not hypothetical. `src/fitdocs/load/engine.py:381-387` classifies and
  skips without ever calling `apply_frontmatter_load`.

The rebuild's drop and the pass's skip are each individually defensible. The
combination is data loss, and no single component is obviously at fault -- which
is likely why it survived this long.

## Why it matters

A user runs `regen` -- a command whose whole promise is that regenerating is
safe -- and silently loses computed training-load values, with no warning and no
way to tell it happened without diffing. Restoring them requires a recompute,
which for a SUPERSEDED payload is exactly what the user was avoiding.

The published contract promises the opposite. `docs/ownership-contract.md:368-372`
says the load pass "leaves that region and its frontmatter keys untouched" for a
hand-authored region. That is true of the pass in isolation and false of `regen`
end to end -- the sentence a user consults to decide whether their hand-authored
region is safe.

## Evidence

Both reproduced through the real CLI during the review at `1dc8633`:

FOREIGN region -- document had a computed result, its `load` region replaced with
hand-authored text:
```
before: ... sources, load_value: 42, load_methodology: probe-field-free, load_basis: probe basis
after cli regen (FOREIGN region): ... sources     <- load_value survived? False
```

SUPERSEDED region -- region holding a v1 payload stamped "computed":
```
region state: RegionState.SUPERSEDED | load_value present: True
after cli regen: ... sources                      <- load_value survived? False
```

Mechanism: `src/fitdocs/render/frontmatter.py:107-154` never inserts a `load_*`
key into `data`; `src/fitdocs/load/engine.py:381-399` is the skip.

## Open questions

Whose defect is it? Three shapes, and the choice needs a view on the ownership
model rather than a local patch:

1. The rebuild carries the three keys forward when it cannot re-derive them --
   but they are tool-owned, and carrying tool-owned keys through a rebuild is
   what the contract says fitdocs does not do.
2. The load pass restores the previous values when it skips -- but then a
   SUPERSEDED payload's stale value outlives the format it was computed in.
3. It stays as it is and the contract documents it, with a warning emitted when
   a skip is about to drop keys -- cheapest, and at least makes the loss visible.

## How to pick it up

1. Reproduce both states first -- the FOREIGN one is easier: sync a document,
   compute a load result, hand-edit the region body, then `regen` and diff.
2. Read `engine.py:381-399` alongside `cli.py::_run_load_pass` to see the
   two-pass structure; the bug lives in the seam, not in either pass.
3. Decide among the three shapes above before writing code, and check the answer
   against `docs/ownership-contract.md`'s Overwrite Semantics bullets -- whatever
   you choose, that section and lines 368-372 must end up true.
4. Whatever lands needs a test for BOTH states; a fix pinned only on FOREIGN
   leaves the SUPERSEDED path to regress silently.

Done looks like: `regen` over a document in either state either keeps the keys or
tells the user it is dropping them, and the published contract says which.

## Update 2026-10-19 -- a finished fix exists and never landed

Found by the 0.2 release-readiness triage at `4f1c1f4`. Branch
`origin/chore/q-regen-load-keys` (6 commits, 2026-10-18, no PR) takes shape 1
above: `cf4d342 fix(sync): carry load keys over a FOREIGN or SUPERSEDED load
region on rewrite`, plus contract/changelog prose and wiki-contract Amendment 11
(criterion 6.10). CI is green at its tip (run 39126612617). None of its commits
is patch-equivalent to anything on `main` (`git cherry origin/main
origin/chore/q-regen-load-keys` -> 6 `+`). The agent log holds no record of why
it stopped; it was reset to 4 lines before 2026-10-19.

`git merge-tree --write-tree origin/main origin/chore/q-regen-load-keys` at
`4f1c1f4`: code merges cleanly; conflicts only in `CHANGELOG.md`,
`.kiro/specs/wiki-contract/requirements.md` and `.kiro/specs/wiki-contract/spec.json`.

Release weight, re-read for 0.2: SUPERSEDED is unreachable from any PyPI
install -- `LOAD_PAYLOAD_VERSION` is `2` at both `v0.1.0` and HEAD
(`src/fitdocs/load/render.py:63`), so v1 payloads exist only in pre-release
data roots. FOREIGN still stands but needs a load region the user replaced by
hand. Not a 0.2 blocker on that reading; landing it before the cut is still
cheaper than after, because it is a governed-contract change that would
otherwise need its own changelog entry in 0.3.

## Resolution

Done 2026-10-19: `chore/q-regen-load-keys` landed (rebased onto main, wiki-contract
amendment renumbered 11 -> 12 after the local-time fix took 11). Shape 1: the
rebuild carries the three `load_*` lines verbatim over a FOREIGN or SUPERSEDED
region (`src/fitdocs/sync.py` `load_key_lines` carry; `contract.load_key_lines`),
wiki-contract criterion 6.10, and the ownership contract's `regen` and `load`
bullets state it. Pinned by
`tests/load/test_feature_e2e.py::test_real_regen_keeps_load_keys_over_a_region_the_pass_skips`
(`[foreign]`, `[superseded]`): replacing the carry at `sync.py:2143` with
`carried = (*carried,)` reds both cases; reverted, both green.
