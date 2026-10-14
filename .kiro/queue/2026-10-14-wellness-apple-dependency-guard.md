---
id: 2026-10-14-wellness-apple-dependency-guard
title: Enforce the narrower Apple dependency boundary in the wellness guard
status: open
importance: medium
importance_why: The guard accepts forbidden Apple dependencies although current source complies.
effort: S
kind: gap
area: wellness-store, tests/wellness/test_boundary.py
created: 2026-10-14
surfaced_by: /kiro-impl apple-health-import task 1.1 independent review
pinned_at: eef2997
resume_command: "do: Read .kiro/queue/2026-10-14-wellness-apple-dependency-guard.md and add discriminating Apple-specific dependency checks to the shared wellness boundary guard"
context:
  - tests/wellness/test_boundary.py
  - .kiro/specs/apple-health-import/design.md
  - .kiro/specs/wellness-store/design.md
blocked_by: []
---

## What

The shared wellness guard's `_EXTERNAL` allowance also applies to Apple
modules. Apple's design permits only stdlib, wellness model/spec/probe and
its lower-ranked internal modules; layout/settings/units/tomli_w are forbidden.
Current Apple source complies. Task 1.1 owns rank/list additions only, so the
guard-body correction belongs to wellness-store.

## Why it matters

A later Apple import of these dependencies could pass the architectural guard
while violating the approved narrow package boundary.

## Evidence

At eef2997, test_boundary.py:39 defines the broad allowance and :73 applies it
without checking the importing module. A parent pytest probe, independently
repeated by review, passed all four parameter cases below (plus two separate
relative-import controls: six passed):

```python
import pytest
from tests.wellness.test_boundary import _violations

@pytest.mark.parametrize("dependency", [
    "fitdocs.layout", "fitdocs.settings", "fitdocs.units", "tomli_w",
])
def test_existing_gap(dependency):
    assert _violations(f"import {dependency}\n", "formats.apple.records") == set()
```

Run a temporary test under `uv run pytest` with the repository on PYTHONPATH.
The current empty violation set demonstrates the gap, rather than the desired
future behavior.

## How to pick it up

Read the Apple Allowed Dependencies section and the existing guard first.
Add failing controls for prohibited dependencies in Apple modules, retaining
allowed upstream usages and model/spec/probe controls. Scope the allowance to
the caller, then run wellness boundary tests and static checks. Apply mutations
that remove the new caller restriction and confirm targeted assertion failures.
