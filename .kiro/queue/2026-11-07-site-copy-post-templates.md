---
id: 2026-11-07-site-copy-post-templates
title: Update the website copy for post templates and the new post-template command
status: open
importance: medium
importance_why: The site's publishing and CLI pages become stale the day the next release ships post templates; push to main deploys fitdocs.ai.
effort: S
kind: docs
area: website/content/, post-templates
created: 2026-11-07
surfaced_by: /kiro-impl post-templates 6.3
pinned_at: b62f8145
resume_command: "do: update website/content/ for post templates per .kiro/queue/2026-11-07-site-copy-post-templates.md, after post-templates is merged and released; fold into draft PR #5 if still open"
context:
  - .kiro/specs/post-templates/requirements.md
  - .kiro/specs/post-templates/design.md
  - docs/publishing.md
  - CHANGELOG.md
  - website/content/
blocked_by: []
---

## What
The post-templates feature (Phase 16) adds `post-template.toml`, an automatic
fill of a new workout page's `post` region in `fitdocs sync` and `pull --sync`,
the `fitdocs post-template check|refill` command (the CLI count goes from 17 to
18), the `post_waiting` publish outcome (exit 1), and a second named exception
to "the index is never read back". The feature edited no site page, by
decision (the same rule as publish-core Req 16.2). Whether any site line is now
stale is unknown: the surfacing session did not read the site.

## Why it matters
The site is the public description of the tool, and a push to main deploys it.
If the site describes the command list, the `post` region or the "never read
back" rule, it will disagree with the release that ships this feature.

## Evidence
- Known: `website/content/reference/cli.md` has no publish section on this tree (`grep -n -i publish website/content/reference/cli.md`); that copy is in draft PR #5.
- Unknown: which other pages under `website/content/` mention publishing, the `post` region, the command count or the index rule.
- `docs/publishing.md` holds the post-templates section and the `post_waiting` row: the source for any copy.
- `CHANGELOG.md` Unreleased names the contract change.
- Draft PR #5 holds other site copy for the next release and is held unmerged until the release is on PyPI.

## How to pick it up
1. Wait for post-templates to be merged and the release containing it cut. Check `gh pr view 5` and that the draft PR is still open.
2. Read `docs/publishing.md` (post-templates section) and `CHANGELOG.md`, then grep `website/content/` for the publishing guide, the command reference and any line about the `post` region, the command count or "never read back". List each by file and line.
3. Edit them (on PR #5's branch if it is still open, otherwise a new branch via the change protocol). Voice stays as the existing site copy. Done when no site line contradicts the docs.

## Open questions
Whether a worked template example belongs on the site or only in `docs/publishing.md`.
