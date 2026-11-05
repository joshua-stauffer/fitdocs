---
id: 2026-11-05-garmin-website-pages-at-release-cut
title: Update the three website pages for the Garmin connector at the release cut
status: open
importance: medium
importance_why: Until the cut, the published website says fitdocs pulls only from intervals.icu and a folder, and lists a wellness source order and settings the Garmin connector changes; a push to main deploys the site, so the pages must change only when the release that ships the connector is cut.
effort: S
kind: docs
area: website/content/guides/connectors.md, website/content/guides/wellness.md, website/content/reference/configuration.md
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector 6.3
pinned_at: 25a96806
resume_command: "do: at the release cut that ships the garmin connector, edit the three website pages named in .kiro/queue/2026-11-05-garmin-website-pages-at-release-cut.md from the repo docs, in the release's own change, then confirm the site build (read that item first)"
context:
  - docs/connectors.md
  - docs/wellness.md
  - docs/configuration.md
  - website/content/guides/connectors.md
  - website/content/guides/wellness.md
  - website/content/reference/configuration.md
  - website/content/guides/privacy-and-network.md
  - website/content/guides/inbox.md
  - .github/workflows/docs.yml
  - .kiro/specs/garmin-connector/design.md
  - CHANGELOG.md
blocked_by: [garmin-connector]
---

## What
garmin-connector's task 6.2 corrected `docs/connectors.md`, `docs/wellness.md`,
`docs/configuration.md`, the README and the changelog, and deliberately left
`website/` alone, because a push to `main` deploys the site and the site must not
describe a connector no release ships. The three website pages mirror those docs
and are now behind them:

- `website/content/guides/connectors.md` (titled "Pulling from intervals.icu"):
  gains the Garmin material from `docs/connectors.md`, the `## Garmin` section
  from line 1054 (creating and renewing a Personal API key, Garmin's own terms
  quoted as in "Garmin's terms", what a first pull does to an existing wiki,
  the one-second pacing and rate-limit waits, wellness under "Wellness from
  Garmin", and the non-affiliation line), the five-connector preamble, "What
  leaves your machine" and the terms-first policy.
- `website/content/guides/wellness.md`: gains the `garmin-personal` source and
  format, a Garmin connector subsection beside "intervals.icu" (line 40), the
  default order `garmin-export`, `garmin-personal`, `apple-health`,
  `intervals-icu` in the precedence passage (line 57), and the note that the
  series rebuilds once after upgrading. Its description (line 3) names only
  Apple Health, a Garmin export and intervals.icu.
- `website/content/reference/configuration.md`: the connector list and the
  settings of a `garmin` instance as `docs/configuration.md` states them (lines
  158 and 160 name only `intervals` and `folder`), including the built-in
  wellness precedence order (line 139 still lists three sources).
- Also at the cut, outside the three pages: `website/content/guides/privacy-and-network.md:50`
  says `fitdocs connect` and `fitdocs pull` send requests to intervals.icu, so
  Garmin's host belongs beside it, and `website/content/guides/inbox.md:43`
  lists wellness sources with no Garmin pull.

## Why it matters
The site is the first thing a user reads; after the cut it would say there is no
Garmin connector and give the wrong default wellness order.

## Evidence
- `grep -n "garmin-personal" docs/wellness.md docs/configuration.md` finds the
  repo docs current; `grep -n "garmin-personal" website/content/guides/wellness.md
  website/content/reference/configuration.md` finds nothing, and
  `website/content/reference/configuration.md:139` reads "built-in order:
  `garmin-export`, `apple-health`, `intervals-icu`".
- `website/content/guides/connectors.md:2-8` titles and describes the page for
  intervals.icu and a folder only.
- `.kiro/specs/garmin-connector/tasks.md` 6.2 ("Do not edit the website guide: a
  push to `main` deploys it") and 6.3 (this item).

## How to pick it up
1. Do this in the release cut's own change, after the version that contains the
   `garmin` connector is chosen; do not push it to `main` earlier.
2. Read the three `docs/` pages' Garmin passages and port them, following how the
   website pages differ from `docs/` today (frontmatter, relative links). Match
   the changelog entry's wording on the contract and the action.
3. Build the site with `uv run --group docs python -m scripts.build_site build`,
   as `.github/workflows/docs.yml` does, and check the pages render. Preview and
   deploy notes: `.kiro/specs/docs-site/`.

## Open questions
Whether the guide's title and filename stay "Pulling from intervals.icu" or
become a neutral "Connectors" title (a rename changes the page's URL).
