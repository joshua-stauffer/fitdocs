---
id: 2026-09-12-ownership-contract-prose-stale-and-unpinned
title: docs/ownership-contract.md carries a stale inbox sentence, an over-broad scope paragraph, and several facts no test pins
status: open
importance: low
importance_why: The contract document is what plugin and wiki authors read; each unpinned sentence can drift from the code without a red test, and one sentence is already stale.
effort: S
kind: docs
area: wiki-contract, load-history, docs/ownership-contract.md, tests/test_ownership_contract.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 1.3 (reviewer rounds 2-3, FOLLOW_UPS)
pinned_at: 8cd0062
resume_command: "do: in docs/ownership-contract.md narrow the scope sentence ('exact limits of every operation that writes there', ~:14-16) and name drain and pull --sync among the declaration refreshers (head ~:16-25 and the root-instructions section), then pin the history overwrite bullet in tests/test_ownership_contract.py and reword load-history Req 7.6; the inbox sentence and the .gitattributes example are already fixed"
context:
  - docs/ownership-contract.md
  - tests/test_ownership_contract.py
  - .kiro/specs/load-history/requirements.md
blocked_by: []
---

## What
Narrowed 2026-10-19; see the last update below for what was resolved. Still
open:
- The scope sentence (`docs/ownership-contract.md:14-16`, "the exact limits
  of every operation that writes there") claims more than the contract
  describes; the history chart's marker is module-local (see the DOC_BANNER
  item) and is not described there.
- The declaration-refresher sentences (the head, ~:16-25, and the
  root-instructions section) do not name `drain` (`fitdocs sync` with no
  argument; `src/fitdocs/sync.py` `drain` calls `refresh_declarations`) or
  `pull --sync`, which runs the drain.
- No test pins the history overwrite bullet.
- load-history Req 7.6 says the declaration is "refreshed on every run";
  the shipped behaviour refreshes only on a run that reaches its write step.

## Evidence
1.3 review rounds 2-3 `FOLLOW_UPS`; `grep -n "only directory" docs/ownership-contract.md`.

## How to pick it up
Read tests/test_ownership_contract.py for the existing pin style; add
three assertions; reword the two sentences; amend Req 7.6.

## Update 2026-09-16 (training-blocks session, main 68fe42e)
- The `:105-107` inbox sentence is FIXED: training-blocks task 1.3 corrected
  "No fitdocs feature names such a location yet" to name the inbox, and added
  the configured *read* location (`[plans] path`) beside it.
- Two corrections to the item as first written: (a) the test module is
  `tests/test_ownership_contract.py` -- a `_doc` module never existed (paths
  above corrected in place); (b) the version note and the owned-path list ARE
  pinned there (`test_contract_version_matches_code`,
  `test_owned_paths_equal_layout_owned_paths_exactly`; each reds under
  mutation, verified by the 1.3 reviewer). Remaining scope: the `:233-237`
  scope paragraph (line refs no longer resolve; likely the ~:16-17 "exact
  limits of every operation that writes there" sentence), a pin for the
  history overwrite bullet, load-history Req 7.6 wording.
- Two more pre-existing omissions in the same document, found by the 1.3
  reviewer: the declaration-refresher sentences (~:17-27 and the
  root-instructions section) name `sync`, `regen`, `history`, `plan` but
  `drain` (`fitdocs sync` with no argument) also refreshes unconditionally
  (`src/fitdocs/sync.py:738`); and the `.gitattributes` example enumerates
  generated locations per directory but has never listed `workouts/assets/*`
  (training-blocks 1.3 added the `blocks/` lines).

## Update 2026-09-29 (Phase 8 spec batch)

One more stale sentence, reported by the Phase 8 spec writers:
`docs/ownership-contract.md:63-67`, the `.fitdocs/` bullet, still gives as
its example "a future ingestion feature's quarantine record"; quarantine
shipped (`src/fitdocs/quarantine.py`). Likely absorbed by Phase 8:
activity-identity's contract task rewrites this bullet to name "the
quarantine record and the hold record without an exhaustive claim"
(`.kiro/specs/activity-identity/design.md` DocumentContract section; task
6.2), and
connectors 8.1 names its ledgers "beside the quarantine record"
(`.kiro/specs/connectors/design.md` ~:1615-1617). Check after either lands
and drop this bullet from the item's scope if the word "future" is gone.

## Update 2026-10-19 (0.2 site-copy update)

The `.gitattributes` example under "Marking Generated Files in a
Version-Controlled Wiki" (`docs/ownership-contract.md`, at 90cd00b) still
lists only `workouts/`, `fit-archive/`, `history/` and `blocks/`. It has no
lines for the owned locations added since:

- `recovery/recovery.md` and `recovery/assets/*`
- `wellness/*` (the rebuilt yearly CSVs)
- `wellness-archive/**` (nested per-format folders)
- `dashboards/assets/**`

For `dashboards/assets/**`, note that `*.snapshot-<n>.json` must stay
committed (`docs/dashboards.md`, "Version control"). The site's wiki guide
(branch `chore/site-copy-0-2`, `website/content/guides/wiki-integration.md`)
now suggests:

- `recovery/*.md linguist-generated`
- `recovery/assets/* linguist-generated -diff`
- `wellness/* linguist-generated`
- `wellness-archive/** linguist-generated -diff`

When this item is picked up, make the contract's example agree with those
lines, and add `workouts/assets/*`.

## Update 2026-10-19 (chore/docs-0-2, docs gaps before 0.2.0)

Narrowed, not closed.
- **`.gitattributes` example: done** in 4abf6c7. It now marks
  `workouts/assets/*`, `recovery/*.md`, `recovery/assets/*`, `wellness/*`,
  `wellness-archive/**`, `dashboards/AGENTS.md` and
  `dashboards/assets/*/*.svg`, beside the earlier lines. Dashboard pages and
  `*.snapshot-<n>.json` stay unmarked, and the prose says to keep snapshots
  committed. Pinned with `git check-attr` in
  `tests/test_ownership_contract.py::test_gitattributes_example_marks_every_generated_location`
  and `::test_gitattributes_example_leaves_user_files_and_snapshots_unmarked`.
  Every owned path except `.cache/` and `.fitdocs/` needs a sample there, so
  a new owned path reds the test.
- **Quarantine "future" bullet: already gone.** `grep -n "future ingestion"
  docs/ownership-contract.md` prints nothing at 4179f3c.
- **Refresher sentences: partly addressed** in 9e33e08. Both now name
  `fitdocs recovery` as the fifth command. `drain` and `pull --sync` are
  still covered only implicitly, by "`sync`".
