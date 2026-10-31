---
id: 2026-10-31-intervals-publish-site-copy
title: Site copy for publishing to intervals.icu at the next release
status: open
importance: medium
importance_why: Once intervals-publish ships, two site pages state the intervals connector never writes to the account, which becomes false.
effort: S
kind: docs
area: intervals-publish, website/content/guides/connectors.md, website/content/guides/privacy-and-network.md, website/content/reference/configuration.md
created: 2026-10-31
surfaced_by: /kiro-spec-batch Phase 14 (intervals-publish spec writer)
pinned_at: bddc0a46
resume_command: "do: at the release that ships intervals-publish, update the site lines listed in .kiro/queue/2026-10-31-intervals-publish-site-copy.md on the site-copy branch (never on main before the release is on PyPI)"
context:
  - .kiro/specs/intervals-publish/design.md
  - docs/connectors.md
  - website/content/guides/connectors.md
  - website/content/guides/privacy-and-network.md
  - website/content/reference/configuration.md
  - .kiro/queue/2026-10-31-publish-core-site-copy.md
blocked_by:
  - intervals-publish
---

## What
The documentation site describes released versions only, and a push to
`main` deploys it, so intervals-publish edits nothing under
`website/content/` (controller ruling R9). Once it ships, these site lines
are stale or missing:

- `website/content/guides/connectors.md:14`: "It never writes to the
  account." The connector then writes an activity's name and description for
  pages that opt in, and, with `publish_upload = true`, uploads the page's
  base `.fit` file.
- `website/content/guides/privacy-and-network.md:50`: names only `fitdocs
  connect` and `fitdocs pull` as sending requests to intervals.icu, and says
  "The connector never writes to your account." `fitdocs publish --yes` also
  sends requests there (an update, a listing, an upload when enabled).
- `website/content/reference/configuration.md:156-163`: the
  `[connectors.<name>]` key table has no `publish_upload` row
  (`(intervals)`, default `false`).
- No site page explains publishing to intervals.icu: how a page opts in to
  the instance, the order in which the activity is found, Strava-imported
  activities, the direct link, and the codes that are specific to the
  target. The general publishing guide is publish-core's queue item
  (`2026-10-31-publish-core-site-copy.md`); this item adds the
  intervals.icu section of it.

## Why it matters
The site would tell users the connector never writes to their account after
a release in which it can. That is a false privacy statement.

## Evidence
At `bddc0a46` (branch `chore/p14-intervals-publish`):
- `website/content/guides/connectors.md:14`: "- **`intervals`** reads an
  [intervals.icu](https://intervals.icu) account with your own API key. It
  never writes to the account."
- `website/content/guides/privacy-and-network.md:50`: "... `fitdocs connect`
  and `fitdocs pull` send requests to intervals.icu while you run them. ...
  The connector never writes to your account."
- `website/content/reference/configuration.md:156-163`: the key table lists
  `connector`, `lookback_days`, `wellness`, `sources`, `path` and
  `settle_seconds`.

## How to pick it up
1. Read `docs/connectors.md`'s `### Publishing` subsection as landed (the
   repository's own statement of the behaviour) and re-check the line
   numbers above against the release tag.
2. Rewrite the three lines in the site's voice, and add the intervals.icu
   part of the publishing guide alongside publish-core's site copy.
3. Land it with the release's site update (draft PR on the site-copy branch),
   not on `main` before the release is on PyPI.
