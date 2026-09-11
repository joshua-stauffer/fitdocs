---
id: 2026-09-11-contract-bindings-value-emptying-undetected
title: CONTRACT_BINDINGS value-emptying is undetected -- the completeness test compares key sets only
status: open
importance: medium
importance_why: A future session can silently delete registered bindings; the guard that exists to prevent a second contract reader would not notice.
effort: M
kind: gap
area: tests/test_contract_consumers.py
created: 2026-09-11
surfaced_by: /kiro-impl effort-tags 5.1 review, reconfirmed by 5.3 feature validation
pinned_at: d1147a0
resume_command: "do: make tests/test_contract_consumers.py detect an emptied CONTRACT_BINDINGS value, not only a dropped key"
context:
  - tests/test_contract_consumers.py
  - src/fitdocs/contract.py
blocked_by: []
---

## What

`tests/test_contract_consumers.py` guards against a module rebinding a contract
name to a local copy. `CONTRACT_BINDINGS` is a hand-curated dict of module id ->
tuple of names, and `test_every_converted_module_declares_its_contract_bindings`
(line ~364) asserts `set(CONTRACT_BINDINGS) == set(_MODULE_IDS)` -- **key sets
only**. Emptying a module's tuple is therefore invisible.

## Why it matters

The registry is the sole mechanism catching a second reader of the contract.
Task 5.1's review established that with the five new entries removed and five
same-named shadow copies installed, the entire suite stays green -- nothing else
in the repo catches it. A guard whose entries can be deleted without any test
failing degrades silently, and it now covers five bindings it did not before.

## Evidence

Executed during task 5.3 validation at `e39b35f`: setting
`"fitdocs.declaration": ()` in `tests/test_contract_consumers.py:169` **and**
installing a same-named shadow copy in `src/fitdocs/declaration.py` leaves the
entire suite green -- **3271 passed, 5 skipped**.

Deleting the whole key instead reds (`test_every_converted_module_declares_its_contract_bindings`).
Keeping the entry and installing only the shadow reds the identity test. So the
blind spot is exactly emptying the tuple.

A naive "every tuple is non-empty" assertion will not work: `"fitdocs.cli": ()`
is a legitimate entry.

## How to pick it up

1. Read `tests/test_contract_consumers.py` end to end -- especially the module
   docstring's "append to both, not one" contract and why `fitdocs.cli` is
   legitimately empty.
2. The likely shape: derive each module's expected tuple from its
   `from fitdocs.contract import (...)` AST rather than hand-curating it, so the
   registry becomes checkable rather than declarative. That also closes
   `2026-09-11-contract-objects-bound-but-unregistered`.
3. Whatever you build, prove it by mutation: empty a non-empty tuple and watch
   it red, and confirm `fitdocs.cli`'s legitimate empty entry still passes.

Done looks like: emptying any module's binding tuple reds, and the legitimately
empty entry does not.
