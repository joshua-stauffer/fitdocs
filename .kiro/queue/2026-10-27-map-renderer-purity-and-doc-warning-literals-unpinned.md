---
id: 2026-10-27-map-renderer-purity-and-doc-warning-literals-unpinned
title: map.py's "no tiles/basemap import" rule and the docs' quoted BasemapError text are not tied to the code
status: open
importance: low
importance_why: Both drift silently. Nothing is wrong today, but a later change could break the design's dependency rule or stale the user docs without any red test.
effort: S
kind: gap
area: compact-chart-assets, tests/render/charts/test_map.py, tests/test_map_images_docs.py
created: 2026-10-27
surfaced_by: /kiro-impl compact-chart-assets (tasks 5.1 and 6.2 reviews)
pinned_at: 260c3ff8
resume_command: "do: extend test_map_module_does_not_import_pil to forbid fitdocs.tiles and fitdocs.basemap imports, and tie the docs' quoted 'cannot be decoded' warning to the message basemap actually emits"
context:
  - src/fitdocs/render/charts/map.py
  - src/fitdocs/basemap.py
  - tests/render/charts/test_map.py
  - tests/test_map_images_docs.py
  - .kiro/specs/compact-chart-assets/design.md
blocked_by: []
---

## What
1. The design's Allowed Dependencies section and map.py's docstring both say the map renderer never imports `fitdocs.tiles` or `fitdocs.basemap`. The only guard, `test_map_module_does_not_import_pil` (tests/render/charts/test_map.py:548), checks PIL alone.
2. README.md and docs/configuration.md quote the warning `BasemapError: tile z/x/y cannot be decoded: …` as a literal. tests/test_map_images_docs.py pins the docs' literal, but nothing compares it with the text `fitdocs.basemap` emits. Changing "cannot be decoded" in basemap.py fails only code-side tests.

## Why it matters
Each is a small, cheap guard against drift. Without (1), the map renderer could
start fetching or decoding tiles itself. Without (2), the docs could quote an
error the program no longer prints.

## Evidence
- tests/render/charts/test_map.py:548-560 collects imported names and asserts only on PIL. Verified in this run.
- The 6.2 reviewer subagent ran a mutation of the basemap.py message (~:87): it turned 7 basemap tests red and no docs test. I did not reproduce it.

## How to pick it up
1. In test_map.py, add `fitdocs.tiles` and `fitdocs.basemap` (and relative forms) to the forbidden set, and plant a violation to show it reds.
2. In test_map_images_docs.py, produce the warning from `basemap.compose_basemap` on an undecodable factory tile, then assert that the docs' quoted prefix is a prefix of `str(exc)`.
</content>
</invoke>
