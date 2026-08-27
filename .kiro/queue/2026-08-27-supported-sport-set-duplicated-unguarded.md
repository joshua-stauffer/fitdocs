---
id: 2026-08-27-supported-sport-set-duplicated-unguarded
title: The supported-sport set exists twice (discipline.SUPPORTED_SPORTS and DEFAULT_CHANNEL_PRIORITY keys) with no cross-check
status: open
importance: medium
importance_why: Adding a sport to the declared owner alone leaves for_discipline() returning (), silently unscoring every such activity, and [load.priority] rejecting its key — with nothing failing.
effort: S
kind: inconsistency
area: threshold-load, src/fitdocs/load/priority.py, src/fitdocs/load/threshold/discipline.py, src/fitdocs/load/settings.py
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-supported-sport-set-duplicated-unguarded.md] Pin the two sport tables to each other"
context:
  - src/fitdocs/load/priority.py
  - src/fitdocs/load/threshold/discipline.py
  - src/fitdocs/load/settings.py
  - tests/load/test_priority.py
blocked_by: []
---

## What

`discipline.SUPPORTED_SPORTS` (`discipline.py:50`) is the declared owner per
`design.md:132`. `DEFAULT_CHANNEL_PRIORITY`'s key set (`priority.py:37-46`)
must agree with it — it does today — but nothing enforces that.
`discipline.py:96` asserts `ANCHOR_PLANS.keys() == SUPPORTED_SPORTS`; there is
**no analogue** for the priority table, and `tests/load/test_priority.py:83-86`
hard-codes the four sports rather than deriving them.

Worse, `settings.py:73-75` derives its **user-facing** "supported disciplines"
list from the priority copy rather than from the owner:

```python
_SUPPORTED_PRIORITY_SPORTS: Final[Mapping[str, Sport]] = MappingProxyType(
    {sport.value.lower(): sport for sport in DEFAULT_CHANNEL_PRIORITY}
)
```

`priority.py` deliberately cannot import `discipline.py` — the leaf constraint
exists so `settings.py` can import the priority value without pulling in the
calculator — so the coupling is convention-only by design.

## Why it matters

Adding a sport to `SUPPORTED_SPORTS` + `ANCHOR_PLANS` is design.md's own
revalidation trigger (`design.md:245-246`). Do it without touching
`priority.py` and `for_discipline()` returns `()` → `select` returns `None` →
`_missing_inputs` returns `()` → a silent `NotComputed` listing all three
channels as "not in the configured order". Drift the other way and
`settings.py` accepts a `[load.priority]` key whose configuration can never
take effect, while its own error message's "supported disciplines are ..."
names the priority table's notion of supported, not the owner's.

## Evidence

`3e14ab9`. `grep -rn "SUPPORTED_SPORTS" src/` shows `priority.py` never
references it. No test asserts the two key sets are equal.

## How to pick it up

The leaf constraint forbids `priority.py` importing `discipline.py`, so the
pin belongs in a **test**, not an import: assert
`set(DEFAULT_CHANNEL_PRIORITY) == SUPPORTED_SPORTS` in a module that may
import both (`tests/load/threshold/test_discipline.py` or
`test_boundary.py`). Verify by adding a sport to one table only and observing
red. Consider also pointing `settings.py`'s user-facing list at the owner.
