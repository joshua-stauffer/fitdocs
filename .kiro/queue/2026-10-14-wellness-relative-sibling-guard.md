---
id: 2026-10-14-wellness-relative-sibling-guard
title: Resolve relative sibling imports correctly in the wellness guard
status: open
importance: medium
importance_why: A valid lower-ranked sibling import is falsely rejected by the shared guard.
effort: S
kind: bug
area: wellness-store, tests/wellness/test_boundary.py
created: 2026-10-14
surfaced_by: /kiro-impl apple-health-import task 1.1 independent review
pinned_at: eef2997
resume_command: "do: Read .kiro/queue/2026-10-14-wellness-relative-sibling-guard.md and repair relative sibling resolution with discriminating controls in the shared wellness boundary guard"
context:
  - tests/wellness/test_boundary.py
  - .kiro/specs/apple-health-import/design.md
  - .kiro/specs/wellness-store/design.md
blocked_by: []
---

## What

The guard treats `from . import records` in apple.reader as importing the
higher-ranked apple.__init__, whereas `from .records import RawRecord` is
accepted. Both reach the allowed lower-ranked records module. Actual source
uses the direct form. Task 1.1 permits only rank/list additions to this shared
test, leaving guard-body repair to wellness-store.

## Why it matters

Valid sibling imports fail the architectural gate; authors have to change
spelling to satisfy it, and the guard does not model the import graph correctly.

## Evidence

At eef2997, test_boundary.py:120 special-cases only three parent packages when
resolving imported aliases. Parent and independent-review pytest probes both
passed these two controls (within a six-test observation run):

```python
from tests.wellness.test_boundary import _violations

def test_existing_false_rejection():
    assert _violations("from . import records\n", "formats.apple.reader") == {
        "rank:formats.apple.__init__",
    }

def test_direct_control():
    assert _violations("from .records import RawRecord\n", "formats.apple.reader") == set()
```

Run a temporary test through `uv run pytest` with the repository on PYTHONPATH.
The first expected set records current wrong behavior, not the desired result.

## How to pick it up

Read `_from_base`, `_wellness_module` and `visit_ImportFrom`. Add controls for
relative and absolute package-member imports, allowed downward siblings and
forbidden upward siblings. Repair module resolution without weakening rank or
network enforcement, then mutate the resolution back to prove the controls fail.
Run wellness boundary tests and static checks.
