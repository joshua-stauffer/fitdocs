---
id: 2026-10-02-alignment-table-pin-ignores-units-and-new-constants
title: The ownership-contract alignment-table pin ignores units and enumerates a hard-coded constant dict, so two kinds of drift survive
status: open
importance: low
importance_why: The table is documentation read by humans; both drifts are quiet, but each needs a specific edit to the table or the module.
effort: S
kind: gap
area: channel-merge, tests/compose/test_contract_docs.py, src/fitdocs/compose/alignment.py, docs/ownership-contract.md
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: make tests/compose/test_contract_docs.py compare the keys row's units as well as its numbers, and enumerate the module's public constants from alignment.__all__ as tests/identity/test_contract_docs.py::_numeric_constants does [queue: .kiro/queue/2026-10-02-alignment-table-pin-ignores-units-and-new-constants.md]"
context:
  - tests/compose/test_contract_docs.py
  - tests/identity/test_contract_docs.py
  - src/fitdocs/compose/alignment.py
  - docs/ownership-contract.md
blocked_by: []
---

## What
`tests/compose/test_contract_docs.py` holds the alignment table in the
ownership contract equal to the code. Two holes:
1. The `ALIGNMENT_KEYS` row is read with `([a-z]+) \(([0-9.]+) `, which takes the
   label and the number and ignores what follows. Changing `0.01 m` to
   `0.01 km` (or `1 W` to `1 kW`) in the doc keeps every test green.
2. The set of scalar constants is `_scalar_constants()`, a hand-written dict of
   three names. A new public `Final` added to `compose/alignment.py` with no
   `ALIGNMENT_SOURCES` entry and no table row is never seen. Its identity twin
   enumerates `matching.__all__` instead and so catches the equivalent addition.

## Why it matters
The module docstring promises that "a constant added without a row" reds. For a
constant added to the module without a source entry, it does not.

## Evidence
At 5c41759.
- `tests/compose/test_contract_docs.py:92` the regex; its mechanism checked
  in this run: `re.findall(r'([a-z]+) \(([0-9.]+) ', ...)` returns
  `[('distance', '0.01'), ('power', '1')]` for both
  `distance (0.01 m), then power (1 W)` and
  `distance (0.01 km), then power (1 kW)`. That the full suite then stays green
  was reported by the validate-impl reviewer subagent (a mutation), unverified
  in this run.
- `tests/compose/test_contract_docs.py:57-62` `_scalar_constants()` hard-codes
  `PAUSE_GAP_S`, `MAX_LAG_S`, `MIN_MATCHED_SAMPLES`; `:71-73` compares the
  source map's keys with that same dict, so it can only agree.
- `src/fitdocs/compose/alignment.py:25-35` `__all__` lists the public names, of
  which the constants are `ALIGNMENT_KEYS`, `MAX_LAG_S`, `MIN_MATCHED_SAMPLES`,
  `PAUSE_GAP_S` (imported from `stretches.py:17`).
- `tests/identity/test_contract_docs.py:60-68` `_numeric_constants()` builds its
  set from `matching.__all__` (upper-case int or float), with a non-empty
  assertion.
- The doc row: `docs/ownership-contract.md:598`.

## How to pick it up
1. Replace the hand-written dict with the identity twin's enumeration over
   `alignment.__all__` (keep `PAUSE_GAP_S`, which is re-exported there) and keep
   a non-empty assertion.
2. Capture the unit after each number in the keys-row regex (`m`, `W`) and
   compare it with a unit recorded beside each `AlignmentKey` (add a field, or
   assert a small dict in the test).
3. Done when changing the doc's `m` to `km`, and adding an unsourced public
   `Final` to `alignment.py`, each red a test.
