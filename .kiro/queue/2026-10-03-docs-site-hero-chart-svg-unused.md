---
id: 2026-10-03-docs-site-hero-chart-svg-unused
title: "website/assets/hero-chart.svg and scripts/make_hero_chart.py are no longer shown on the site"
status: open
importance: low
importance_why: "Dead asset shipped into every build plus a generator, tests and a docs.yml path trigger that guard nothing visible."
effort: S
kind: chore
area: docs-site, website/assets/hero-chart.svg, scripts/make_hero_chart.py
created: 2026-10-03
surfaced_by: applying the 2026-10-03 design handoff
pinned_at: 10cc15c
resume_command: "do: decide whether to retire website/assets/hero-chart.svg + scripts/make_hero_chart.py (and tests/sitebuild/test_hero_chart.py, the docs.yml path, the test_stage/test_pipeline/test_theme pins) or keep them for another page [queue: .kiro/queue/2026-10-03-docs-site-hero-chart-svg-unused.md]"
context:
  - website/overrides/home.html
  - scripts/make_hero_chart.py
  - tests/sitebuild/test_hero_chart.py
  - .github/workflows/docs.yml
  - .kiro/specs/docs-site/requirements.md
blocked_by: []
---

## What
Since 10cc15c the home hero shows `_brand/fitdocs-hero.*`. Nothing renders `hero-chart.svg` any more, but it is still staged into every build, regenerated/checked by `scripts/make_hero_chart.py`, pinned by `tests/sitebuild/test_hero_chart.py` and the asset-list pins, and listed as a path trigger in `.github/workflows/docs.yml`. docs-site requirements 3.5/3.6 still describe it as the hero chart; the maintainer chose not to amend them for this change.

## Why it matters
An unused asset and its tooling read as live to the next session and cost upkeep on every zensical bump.

## Evidence
- `git grep -n hero-chart -- website/overrides` returns nothing at 10cc15c.
- `scripts/make_hero_chart.py:33` still writes `website/assets/hero-chart.svg`.

## How to pick it up
1. Ask the maintainer: retire, or reuse the chart elsewhere.
2. If retiring: delete the svg, the script and its test; drop the docs.yml path and the three asset-list pins; run the site suite with `FITDOCS_REQUIRE_SITE_TOOLING=1`.
