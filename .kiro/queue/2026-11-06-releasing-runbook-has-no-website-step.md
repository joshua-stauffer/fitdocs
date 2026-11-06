---
id: 2026-11-06-releasing-runbook-has-no-website-step
title: docs/releasing.md has no website step, and the queue items disagree about when the site lands
status: open
importance: medium
importance_why: Six queue items schedule site edits for the cut and the runbook mentions none of them, so the public site's network statements can stay false after a release, or deploy before the version they describe is on PyPI.
effort: S
kind: gap
area: docs/releasing.md, website/content, .github/workflows/docs.yml
created: 2026-11-06
surfaced_by: queue ranking for the release after 0.2.0
pinned_at: 35311b53
resume_command: "do: ask the maintainer whether site edits land in the cut commit or after verify-published, then add that as a step in docs/releasing.md and correct .kiro/queue/2026-11-05-garmin-website-pages-at-release-cut.md to match [queue: .kiro/queue/2026-11-06-releasing-runbook-has-no-website-step.md]"
context:
  - docs/releasing.md
  - docs/website.md
  - .github/workflows/docs.yml
  - website/content/changelog.md
  - .kiro/queue/2026-11-05-garmin-website-pages-at-release-cut.md
blocked_by: []
---

## What
A push to `main` that touches `website/**` deploys the site, and the site describes released versions only. `docs/releasing.md` walks the release from gates to `verify-published` and never mentions the site, so nothing in the procedure carries the edits queued for the cut:

- `2026-10-31-publish-core-site-copy`
- `2026-10-31-intervals-publish-site-copy`
- `2026-10-31-relay-server-site-copy-at-next-release`
- `2026-10-31-strava-publish-site-copy`
- `2026-11-05-garmin-website-pages-at-release-cut`
- `2026-10-27-site-copy-contract-17-and-map-viewer-floor`

The items also disagree with what was done last time. `2026-11-05-garmin-website-pages-at-release-cut` says to make the edits "in the release cut's own change". Landing that commit on `main` deploys the site before the tag exists, and so before the version is on PyPI. At 0.2.0 the site PR merged after the publish.

## Why it matters
Until the edits land, the live site says "The connector never writes to your account" and "No other command contacts a connector", both false once `fitdocs publish` and `fitdocs disconnect` ship. If they land in the cut commit, the site describes commands that no installable version has yet, for as long as the release takes, including the wait on the `pypi` environment's approval.

## Evidence
- `grep -n -i -E 'website|site|fitdocs.ai' docs/releasing.md` matches only the word "opposite" (lines 149 and 345).
- `.github/workflows/docs.yml:15-16` triggers on `website/**`; `docs/website.md:291-293`: "a push to `main` then builds, checks and deploys it."
- `website/content/guides/privacy-and-network.md:50-52` holds the two sentences quoted above.
- `website/content/changelog.md:14` has `## Unreleased` above `## 0.2.0 — 2026-10-19`, so a dated entry is also owed.
- `git log -1 --format=%ci v0.2.0` gives `2026-10-19 23:17:09 +0200` (21:17:09Z); `2026-10-31-site-copy-0-2-claim-and-worktree-left-open` records PR #1 merged at 22:20:56Z.

## How to pick it up
1. Ask the maintainer which order holds. The 0.2.0 order, a site PR merged right after `verify-published`, keeps the site true throughout and is the recommended default.
2. Add the step to `docs/releasing.md`: the site PR, the dated `website/content/changelog.md` entry, and the build command from `.github/workflows/docs.yml`. Automation for it: none, since site copy is the maintainer's.
3. Correct the garmin item's "How to pick it up" to match.

Done when the runbook names the site step and no queue item contradicts it.
