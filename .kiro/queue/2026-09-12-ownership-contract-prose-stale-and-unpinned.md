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
resume_command: "do: in docs/ownership-contract.md narrow the scope sentence ('exact limits of every operation that writes there', ~:16-17), name drain among the declaration refreshers (~:17-27 and the root-instructions section), add workouts/assets/* to the .gitattributes example, then pin the history overwrite bullet in tests/test_ownership_contract.py and reword load-history Req 7.6; the inbox sentence is already fixed"
context:
  - docs/ownership-contract.md
  - tests/test_ownership_contract.py
  - .kiro/specs/load-history/requirements.md
blocked_by: []
---

## What
- :105-107 still describes the inbox as "the only directory fitdocs writes
  outside the workout tree" -- untrue since `training-history/`.
- :233-237 scope paragraph claims the contract covers "every file fitdocs
  writes"; the history chart's marker is module-local (see the DOC_BANNER
  item) and is not described there.
- No test asserts the `CONTRACT_VERSION = "3"` note, the seven-entry path
  list, or the history overwrite bullet; only the migration section is
  pinned. Req 7.6's wording ("refreshed on every run") disagrees with the
  shipped behaviour (refreshed only on a run that reaches its write step).

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
