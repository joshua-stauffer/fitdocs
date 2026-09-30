---
id: 2026-09-30-docs-site-link-extraction-gaps
title: docs-site link extraction misses escaped destinations, container reference definitions, srcset and poster
status: open
importance: low
importance_why: Each gap lets a broken asset link publish; Zensical's strict mode never reports missing assets, so the link checker is the only guard.
effort: M
kind: gap
area: docs-site, scripts/sitebuild/links.py
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "do: extend scripts/sitebuild/links.py extraction for escaped destinations, container reference definitions, srcset and poster; add tests"
context:
  - scripts/sitebuild/links.py
  - tests/sitebuild/test_links.py
blocked_by: []
---

## What
- An escaped character in a destination hides the link: `extract_links("[a](x\\(1\\).png)")` returns ().
- Reference definitions inside list items or blockquotes are not extracted (`* [x]: y.png`).
- `srcset` and `poster` URLs are neither checked nor rewritten by Zensical, so they 404 on non-index pages.
- `github_slugs` slugs raw heading source (emphasis, inline links and entities diverge from GitHub; no current docs/ heading is affected) and uses Python's Unicode data (14+) where github-slugger uses 13.

## Evidence
docs-site 2.8 reviewer probes and Zensical probe builds (2026-09-30).

## How to pick it up
Extend `_mask`/`extract_links` for escapes and containers; check `srcset`/`poster` like unquoted values; document or handle the slug limits.
