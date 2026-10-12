---
id: 2026-10-12-chart-kit-stale-register-monkeypatches
title: Stale 'register before the registry does' monkeypatches now duplicate registered kinds
status: open
importance: low
importance_why: Dead test code; harmless (kind_named returns the first match) but misleading.
effort: S
kind: chore
area: chart-catalog tests; chart-kit tests
created: 2026-10-12
surfaced_by: /kiro-impl chart-catalog
pinned_at: c52da2d
resume_command: "do: remove the registry.KINDS monkeypatches that predate registration in test_mean_max.py, test_dual_axis.py and test_table.py"
context:
  - tests/render/charts/kit/test_mean_max.py
  - tests/render/charts/kit/test_dual_axis.py
  - tests/render/charts/kit/test_table.py
blocked_by: []
---

## What
`monkeypatch.setattr(registry, "KINDS", (*registry.KINDS, KIND))` in test_mean_max.py (~469) and test_dual_axis.py, and `_registered` in chart-kit's test_table.py (~213–215, docstring "before task 6.1 registers it"), were needed before registration; with the kinds registered they add a duplicate entry.

## Why it matters
Readers assume the kind is unregistered; a future test that iterates kind_names() under the patch would see duplicates.

## Evidence
3.1 reviewer subagent analysis (impl/chart-catalog c52da2d): the duplicate is visible only in kind_names(); api.validate_chart resolves the first (registered) entry.

## How to pick it up
Delete the patches, call api.validate_chart/render_chart directly, run the three modules.
