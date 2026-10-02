---
id: 2026-10-02-connectors-contract-changelog-and-page-statements-unpinned
title: The connectors statements in the ownership contract, the changelog and docs/connectors.md's report table are pinned by no test
status: open
importance: medium
importance_why: The ownership contract is the published promise about what fitdocs writes and deletes; connectors changed it (CONTRACT_VERSION 5 -> 6) and reviewer mutations deleting those statements left the suite green.
effort: S
kind: gap
area: connectors, wiki-contract, docs/ownership-contract.md, CHANGELOG.md, docs/connectors.md, tests/
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-connectors-contract-changelog-and-page-statements-unpinned.md] Pin the connectors ownership-contract statements, changelog entries and connectors.md report table to the code that owns them"
context:
  - docs/ownership-contract.md
  - CHANGELOG.md
  - docs/connectors.md
  - src/fitdocs/contract.py
  - src/fitdocs/cli.py
  - tests/identity/test_contract_docs.py
  - tests/test_ownership_contract.py
  - tests/test_agent_skill.py
  - tests/connectors/test_network_statements.py
  - tests/test_packaging.py
  - .kiro/specs/connectors/requirements.md
  - .kiro/queue/2026-09-12-ownership-contract-prose-stale-and-unpinned.md
blocked_by: []
---

## What
A checklist; one session working in `tests/` fixes all of it.

- [ ] **Ownership contract, Req 15.1.** The connector statements in
  `docs/ownership-contract.md` -- the opening summary (`:6-14`), the
  `.fitdocs/connectors/` ledger clause (`:73-74`), the credentials-store
  bullet (`:581-594`), the `pull` and `connect` bullets (`:726-750`), and the
  `CONTRACT_VERSION` "5 to 6" paragraph in `src/fitdocs/contract.py:336-346`
  -- have no test. `grep -n -i connector tests/test_ownership_contract.py
  tests/identity/test_contract_docs.py` returns nothing.
- [ ] **`[connectors]` in the settings bullet, Req 15.6.** `:576` lists
  "`[load]`, `[history]`, `[plans]`, `[identity]`, and `[connectors]` today";
  nothing compares that list with the settings tables the code reads.
- [ ] **Changelog, Req 15.8.** `CHANGELOG.md` `[Unreleased]` carries the
  connectors entries (`:42-49` the commands, `:80-85` the inbox/contract
  lines); `tests/test_changelog.py` checks section shape only and never
  mentions connectors.
- [ ] **docs/connectors.md report table.** "Reading the report"
  (`docs/connectors.md:156-172`, columns *Pull channel* / *Printed as*) is
  not bound to `cli._PULL_REPORT_ROWS` (`src/fitdocs/cli.py:1172-1182`). The
  packaged skill's equivalent table is bound (`tests/test_agent_skill.py:571-610`);
  the docs page's is not. It matches today.
- [ ] **Retired-phrase scan scope.** `tests/connectors/test_network_statements.py`
  scans `src/fitdocs/**/*.py`, `README.md` and `docs/*.md` (module docstring
  `:19-20`), not `docs/reference/*.md` or `CHANGELOG.md`.
- [ ] **`[project.urls]`.** `Install`, `Compatibility` and `Wiki Integration`
  (`pyproject.toml:43-45`) have no own pin; `_NAMED_DOC_PAGES`
  (`tests/test_packaging.py:217-224`) names only four pages. No `Connectors`
  entry exists; decide whether one should (distribution owns this file).

## Why it matters
`docs/ownership-contract.md` is what wiki and plugin authors rely on for
"fitdocs never deletes X". The connectors statements are the newest and the
most delicate (pull removes files from the inbox). Unpinned, they can drift
from the code the next time delivery or credentials change, with no red test.

## Evidence
- Lines above read at `ad985b3`.
- Reviewer-observed mutations, not re-run in this session: the task 8.1
  reviewer deleted each connectors statement of the contract in turn
  (mutations O1-O6) and the suite stayed green; the task 9.2 requirement
  sweep recorded Req 15.1 (U1), 15.6 (U3) and 15.8 (U2) as unpinned, each
  mutation green; mutation M3 (renaming a report row in docs/connectors.md)
  survived in the task 7 review.
- Precedent for the pin style: `tests/identity/test_contract_docs.py` parses
  a contract section and compares it with the owning code's constants.

## How to pick it up
1. Read `tests/identity/test_contract_docs.py` and
   `tests/test_agent_skill.py:571-610` for the two pin styles (section parsed
   and compared with code; table rows compared with `_PULL_REPORT_ROWS`).
2. Add `tests/connectors/test_contract_docs.py` that compares the contract's
   connector statements with the code facts they state: the credentials
   directory resolution order (`credentials.py`), `layout`'s ledger
   directory, `CONTRACT_VERSION`, and the settings-table list against the
   real table constants.
3. Add the changelog and report-table pins; widen the retired-phrase scan to
   `docs/**/*.md` (excluding history it should not judge, if any).
4. Done when each named mutation above goes red. The older, non-connectors
   contract gaps stay in
   `2026-09-12-ownership-contract-prose-stale-and-unpinned`.
