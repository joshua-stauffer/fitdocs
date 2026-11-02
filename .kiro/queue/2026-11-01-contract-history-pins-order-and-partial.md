---
id: 2026-11-01-contract-history-pins-order-and-partial
title: 'CONTRACT_VERSION history pins check membership only: paragraph order and one phrase are unguarded'
status: open
importance: low
importance_why: The history in contract.py is the only record of why each version was raised; reordering or weakening it reds nothing.
effort: S
kind: gap
area: src/fitdocs/contract.py, tests/test_asset_write_contract_docs.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 8.8 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-contract-history-pins-order-and-partial.md] Pin CONTRACT_VERSION history order and the 16-to-17 phrase"
context:
  - src/fitdocs/contract.py
  - tests/test_asset_write_contract_docs.py
blocked_by: []
---

## What
(1) Nothing pins the order of the "Raised from N to N+1" paragraphs in contract.py; moving 17-to-18 ahead of 16-to-17 turns no test red because tests check membership. (2) The 16-to-17 paragraph's "never a partial one" is no longer pinned in contract.py (it is pinned only in the docs section).

## Why it matters
The history can be silently reordered or edited down.

## Evidence
- `grep -n "Raised from" src/fitdocs/contract.py` lists the paragraphs from `:206`.
- `tests/test_asset_write_contract_docs.py:57-64` pins the 16-to-17 phrases but not "never a partial one"; that phrase appears at `tests/test_asset_write_contract_docs.py:48` only.

## How to pick it up
1. Add a test that extracts the "Raised from X to Y" headers in file order and asserts they ascend by one.
2. Add the missing phrase to the 16-to-17 pin.
3. Mutation: swap two paragraphs; the first test must go red.
