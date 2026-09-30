---
id: 2026-09-30-root-init-type-checking-block-unguarded
title: The root package's TYPE_CHECKING import block is checked by nothing
status: open
importance: low
importance_why: A dropped TYPE_CHECKING re-export silently breaks static typing for users of the public API; low because runtime is unaffected.
effort: S
kind: gap
area: src/fitdocs/__init__.py, tests/test_public_api.py
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: add a test that the TYPE_CHECKING imports in src/fitdocs/__init__.py equal _LAZY_EXPORTS keys and __all__"
context:
  - src/fitdocs/__init__.py
  - tests/test_public_api.py
blocked_by: []
---

## What
`src/fitdocs/__init__.py` declares each public name three times: a `TYPE_CHECKING` import, a `_LAZY_EXPORTS` entry, and an `__all__` entry. The tests check `_LAZY_EXPORTS` and `__all__`, but nothing checks the `TYPE_CHECKING` block against them.

## Why it matters
Removing a name's TYPE_CHECKING import leaves runtime imports working and mypy on the repo clean, while downstream type checkers lose the symbol. The block drifts one spec at a time as names are added (DeveloperChannel was added by running-dynamics).

## Evidence
Reported by the running-dynamics 1.1 reviewer subagent (mutation O9, not re-run here): deleting `from fitdocs.model import DeveloperChannel as DeveloperChannel` from the TYPE_CHECKING block left both `uv run pytest` and `uv run mypy` green.

## How to pick it up
1. Parse `src/fitdocs/__init__.py` with `ast`, collect the names imported under `if TYPE_CHECKING:`, and assert that set equals `set(_LAZY_EXPORTS)` and `set(__all__)`, less any documented non-lazy names.
2. Put the test in tests/test_public_api.py.
3. Done when deleting any single TYPE_CHECKING import reds it.
