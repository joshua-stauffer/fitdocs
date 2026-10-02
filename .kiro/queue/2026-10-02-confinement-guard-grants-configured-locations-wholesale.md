---
id: 2026-10-02-confinement-guard-grants-configured-locations-wholesale
title: The confinement guard permits any create, modify or delete inside a configured location, so it cannot see a pull removing a user's own inbox file
status: open
importance: low
importance_why: The never-delete-a-user-file rule (connectors Req 8.6, inbox's never-delete guarantee) is pinned by unit tests in test_delivery/test_pull; the tree-wide guard that is supposed to back every writing entry point adds nothing for the inbox.
effort: S
kind: gap
area: wiki-contract, connectors, inbox, tests/test_confinement.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors (task 6.3 review)
pinned_at: ad985b3
resume_command: "do: in tests/test_confinement.py, stage a user-owned file inside the configured inbox before each drain/pull entry-point run and assert it is byte-identical and still present afterwards (or give configured locations a 'may create, may not delete pre-existing' grant), with a mutation that makes the pull remove it"
context:
  - tests/test_confinement.py
  - tests/connectors/test_delivery.py
  - tests/connectors/test_pull.py
  - .kiro/specs/connectors/requirements.md
  - .kiro/specs/wiki-contract/design.md
blocked_by: []
---

## What
`permitted_locations` (`tests/test_confinement.py:181-200`) returns
owned paths + shared files + `configured`, and the guard passes every
created, modified or deleted path that lies under any of them (`:229`,
`:252`). The configured inbox is in `configured` for the drain and pull
entry points, so a pull (or drain) that deletes, or rewrites, a file the
user put in the inbox is a pass. The pull entry point's run
(`:930-983`) asserts no transport call and no failed/deferred outcome, but
nothing about pre-existing inbox files.

## Why it matters
"Nothing you or your own tools put in the inbox is ever removed" is the
most user-visible connectors guarantee (Req 8.6, 15.4). It is covered by
unit tests of `sweep`/`deliver` and `run_pull`, but the confinement guard --
the one test that runs every writing entry point against a whole-tree
snapshot -- is blind to it, so a regression that bypasses the unit-tested
functions (a new code path in `run_pull`, a drain disposition change) would
not be caught there.

## Evidence
Read at `ad985b3`; the grant is by design (docstring `:184-196`: "a write
into a configured intake directory is a pass rather than a failure").
First reported by the connectors task 6.3 reviewer subagent; no mutation
was re-run in this session.

## How to pick it up
1. Read the module docstring and `permitted_locations` in
   `tests/test_confinement.py`, then the pull entry point (`:859-1000`).
2. Simplest: stage `inbox/user-notes.txt` (and an unrelated `.fit` with
   bytes not in the archive) before the drain and pull runs and assert both
   are unchanged afterwards. Broader: split `configured` into "may create
   new entries" and "pre-existing entries are read-only" grants.
3. Prove it with a mutation (make `sweep` remove every inbox `.fit`) that
   goes red here.
