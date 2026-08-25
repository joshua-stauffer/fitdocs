---
id: 2026-08-25-target-granularity-import-allowlists-are-defeatable
title: Stdlib modules re-export sys and builtins, so any import allowlist checked at target granularity is defeatable in one line
status: open
importance: medium
importance_why: A guard pattern this repo now relies on has a general defeat that took three review rounds to find; the lesson belongs in steering before the next session writes the same shape.
effort: S
kind: docs
area: .kiro/steering/change-protocol.md, tests/load/channels/test_purity.py
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 4.2 round-3 review; reproduced by the parent session)
pinned_at: 4390887
resume_command: "do: add a note to .kiro/steering/change-protocol.md's Fixture Discrimination section recording that an AST import allowlist must pin imported NAMES, not import targets, because stdlib modules re-export sys and builtins as ordinary attributes"
context:
  - .kiro/steering/change-protocol.md
  - tests/load/channels/test_purity.py
blocked_by: []
---

## What

An AST guard that allowlists **import targets** — "this module may only import from
`{dataclasses, enum, typing, …}`" — is defeated by a single line, because several
stdlib modules re-export `sys` and `builtins` as ordinary module attributes:

```python
from dataclasses import sys as _sys     # target "dataclasses" is allowlisted -> passes
_sys.modules["fitdocs.load.registry"].available()
```

`sys.modules` is a live handle to every module already imported in the process, so
one sanctioned-looking import yields the filesystem, the network, the clock, stdin,
and any first-party module the parent package happened to load. No further import
appears anywhere.

The fix is to pin imported **names**, not targets: an exact
`(target → frozenset[name])` mapping. That is finite, small, and terminates.

## Why it matters

This is not hypothetical and it is not narrow to one guard. Task 4.2 of
`load-channels` spent **three review rounds and a debug escalation** arriving at an
allowlist design specifically because denylisting AST spellings does not terminate —
and the allowlist it landed on was defeated by this in one line, with the entire
2755-test suite green.

The failure is seductive because the guard *looks* exhaustive. Its own completeness
argument was written down and read as sound by an implementer, a debugger and a
reviewer before a second reviewer executed it. The argument — "a module's namespace
is what it imports, what it binds, what it defines, plus builtins" — is true; the
implementation checked the wrong half of the import statement.

The repo's own recorded lesson applies: a guard that claims more than it delivers is
worse than no guard, because it tells the next session the property is pinned.

## Evidence

Measured by the parent session at `4390887`:

```
$ uv run python -c "..."
dataclasses        re-exports: ['sys', 'builtins']
enum               re-exports: ['sys', 'bltns']
typing             re-exports: ['sys']
collections.abc    re-exports: (none)
math               re-exports: (none)
```

The live reach, measured by the task 4.2 round-3 reviewer with the line inserted
into `src/fitdocs/load/channels/power.py`:

- `36/36` purity tests pass; full suite `2755 passed, 5 skipped`
- `power._sys.modules['fitdocs.load.registry']` resolves to the real module
- from there: `builtins.open`, `builtins.input`, `time.time`, `socket.socket`,
  `fitdocs.load.settings.DEFAULT_LOAD_SETTINGS`, `fitdocs.load.registry.available()`,
  `fitdocs.benchmarks.parse_benchmarks`, and `fitdocs.load.channels.heart_rate.compute`
  — i.e. Reqs 1.10, 9.1, 9.2, 9.4 and 9.7 all defeated at once

`from typing import sys` and `from enum import sys` work identically;
`from dataclasses import builtins as _b` then `_b.open(...)` leaves all 36 purity
tests green.

**Scope check:** `grep -rln "_ALLOWED_IMPORT_TARGETS\|_FORBIDDEN_IO_MODULES\|_CLOCK_ATTRS" tests/`
returns only `tests/load/channels/test_purity.py`, so no other test module in the
repo currently uses this shape. This item is about preventing the next one.

## How to pick it up

1. Read the surviving guard in `tests/load/channels/test_purity.py` (the
   `(target → names)` mapping) — that is the corrected pattern to describe.
2. Add a short entry to `.kiro/steering/change-protocol.md`'s
   `## Fixture Discrimination` § **Named anti-patterns** table, in the same
   one-line-rule style as its neighbours. Something of the shape: *"Target-granularity
   import allowlist — allowlisting the module a name is imported **from** admits
   `from dataclasses import sys`, and `sys.modules` reaches everything already
   loaded → allowlist the imported **names**, not the targets."*
3. Verify the claim before writing it: the one-liner in Evidence above takes seconds
   and `math` / `collections.abc` are genuinely clean, so the note should not
   overstate that *every* stdlib module leaks.
4. Steering edits are non-trivial per the change protocol — worktree, branch,
   merge-back — and the validation for that class is the edited doc read end to end
   plus a grep for statements the edit contradicts.

**Done** looks like: the anti-pattern table names this, with the fix (pin names, not
targets) stated in the same line.

## Open questions

- Is a bare `import math` acceptable under the corrected rule? It binds a whole
  module, but `math` re-exports nothing reachable (measured). The `load-channels`
  guard keeps it with that reason stated. Worth deciding whether the steering note
  should say "bare module imports are acceptable only for modules with no reachable
  attributes, and that must be measured, not assumed."
