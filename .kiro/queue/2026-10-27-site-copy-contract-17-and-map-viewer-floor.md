---
id: 2026-10-27-site-copy-contract-17-and-map-viewer-floor
title: fitdocs.ai site copy says "currently version 16" and does not mention the WebP map viewer floor or Pillow
status: open
importance: medium
importance_why: Public site goes stale the moment compact-chart-assets ships (contract 17); push to main deploys, and the copy is the maintainer's own voice, so it needs his edit.
effort: S
kind: docs
area: website/content, compact-chart-assets
created: 2026-10-27
surfaced_by: /kiro-impl compact-chart-assets (tasks 6.1 and 6.2)
pinned_at: 260c3ff8
resume_command: "do: maintainer edit of website/content/reference/ownership.md (contract version 17; version-change causes include a changed write guarantee) and decide whether a site page should state the iOS 14 / macOS 11 WebP map floor and the Pillow dependency"
context:
  - website/content/reference/ownership.md
  - website/content/guides/workout-pages.md
  - website/content/guides/privacy-and-network.md
  - docs/compatibility.md
  - docs/ownership-contract.md
  - CHANGELOG.md
blocked_by: []
---

## What
- website/content/reference/ownership.md:10 says "a published, versioned contract (currently version 16)". compact-chart-assets raises CONTRACT_VERSION to 17.
- ownership.md:74 lists the version-change causes as "a new owned path, a new page type, or a new class of user-owned key". This bump is for a changed write guarantee: assets are written only when their bytes change, and never as partial files.
- No site page mentions Pillow or the map viewer floor (iOS 14 / macOS 11 for WebP inside SVG). The repo docs now cover both: docs/install.md and docs/compatibility.md § Map images.
- Not applicable: the workout-pages.md:59 phrase "your route drawn over real basemap tiles" and privacy-and-network.md:25 on tile caching are both still true, and neither describes per-tile embedding.

## Why it matters
The site is the public front door. A wrong version number, and a missing
viewer floor for older iOS and macOS, will confuse users once 0.x ships with
this change.

## Evidence
`grep -n "currently version\|new owned path" website/content/reference/ownership.md` → lines 10 and 74, verified in this run. No test pins either line.

## How to pick it up
Website copy is the maintainer's and is excluded from agent edits by design (compact-chart-assets design § Integration & Migration Notes). Also, a push to main deploys the site. Draft the changes for the maintainer to approve, and time them with the release that carries compact-chart-assets (see the held site-copy PR #1 for 0.2).
</content>
</invoke>
