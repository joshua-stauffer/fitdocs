---
id: 2026-10-01-identity-boundary-guard-misses-a-contract-constant-re-exported-by-layout
title: The fitdocs.identity boundary guard does not see a contract constant imported through fitdocs.layout, so any identity module may spell the contract that way
status: open
importance: medium
importance_why: The guard exists so only `kinds` and `pages` reach the contract; a declared exclusion lets every other identity module do it through `layout` with the suite green, and the exclusion has no owner.
effort: S
kind: gap
area: activity-identity, tests/identity/test_boundary.py, src/fitdocs/layout.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-identity-boundary-guard-misses-a-contract-constant-re-exported-by-layout.md] Make the 7.1 boundary guard treat a contract name imported via fitdocs.layout as a contract import"
context:
  - tests/identity/test_boundary.py
  - src/fitdocs/layout.py
  - src/fitdocs/contract.py
  - .kiro/specs/activity-identity/design.md
blocked_by: []
---

## What
`tests/identity/test_boundary.py` (task 7.1) pins that only `identity.kinds` and
`identity.pages` import `fitdocs.contract`. It resolves objects imported from
`fitdocs.layout` to the module that defines them, which works for classes and
functions (they carry `__module__`) but not for a `str` or `int` constant. The
test's own header declares the gap: "a contract constant re-exported by another
`fitdocs` layer (`from fitdocs.layout import SESSION_UUID_FIELD`) ... Follow-up,
not pinned here". `layout.py` really re-exports it (it imports `SESSION_UUID_FIELD`
from the contract), and `fitdocs.layout` is on the guard's import allowlist for
every identity module.

## Why it matters
A future edit in `matching.py`, `roles.py`, `planning.py`, `holds.py` or
`settings.py` can reach the contract's vocabulary through `layout` and nothing
fails, defeating the "identity code reads the page only through `pages`" rule
that Req 3.10 and the design lean on. The header says "follow-up", but no item
owned it until now.

## Evidence
Verified at `fc5c06d` by calling the guard's own helpers:
`tb._closure_violations("fitdocs.identity.matching", "from fitdocs.layout import SESSION_UUID_FIELD\nx = SESSION_UUID_FIELD\n")`
returns `[]`, and `tb._contract_imports(...)` on the same source returns `False`,
while `from fitdocs.contract import SESSION_UUID_FIELD` returns `True`.
- `tests/identity/test_boundary.py:14-17` the declared exclusion;
  `:562` `test_only_kinds_and_pages_import_the_contract`; `:467-472`
  `_contract_imports`.
- `src/fitdocs/layout.py:48` `from fitdocs.contract import SESSION_UUID_FIELD, format_session_uuid`.

## How to pick it up
1. Add the evasion as a failing `_CLOSURE_CASES` / contract-import case in
   `tests/identity/test_boundary.py` (the file already has a table of mutated
   sources, around `:584-912`).
2. Fix by name, not by `__module__`: record, per allowed layer module, the
   contract names it re-exports (derive them from `fitdocs.contract.__all__`
   intersected with the layer module's namespace by identity, `is`), and treat
   `from fitdocs.layout import <such name>` as a contract import. Update the
   header to drop the exclusion.
3. Done when the case above reds in every identity module except `kinds` and
   `pages`, and the two real imports (`kinds.py`, `pages.py`) stay green.
