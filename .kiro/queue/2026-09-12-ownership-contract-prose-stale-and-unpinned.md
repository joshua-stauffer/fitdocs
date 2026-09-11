---
id: 2026-09-12-ownership-contract-prose-stale-and-unpinned
title: docs/ownership-contract.md carries a stale inbox sentence, an over-broad scope paragraph, and several facts no test pins
status: open
importance: low
importance_why: The contract document is what plugin and wiki authors read; each unpinned sentence can drift from the code without a red test, and one sentence is already stale.
effort: S
kind: docs
area: wiki-contract, load-history, docs/ownership-contract.md, tests/test_ownership_contract_doc.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 1.3 (reviewer rounds 2-3, FOLLOW_UPS)
pinned_at: 8cd0062
resume_command: "do: fix ownership-contract.md:105-107 (inbox sentence predates the history directory), narrow :233-237 to the paths the contract actually owns, then pin the version-3 note, the seven-path list and the history overwrite bullet in tests/test_ownership_contract_doc.py; reword Req 7.6 in requirements.md to match"
context:
  - docs/ownership-contract.md
  - tests/test_ownership_contract_doc.py
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
Read tests/test_ownership_contract_doc.py for the existing pin style; add
three assertions; reword the two sentences; amend Req 7.6.
