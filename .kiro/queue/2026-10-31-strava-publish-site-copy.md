---
id: 2026-10-31-strava-publish-site-copy
title: fitdocs.ai site copy for the Strava target (Compatible with Strava), `fitdocs connect --no-browser` and the relay's privacy policy, at the release that ships strava-publish
status: open
importance: medium
importance_why: Once strava-publish ships, the site's network and privacy statements omit the Strava path, the connectors guide undercounts the built-in connectors, and the CLI reference lacks `--no-browser`. Pushing to main deploys the site, so the copy must wait for the release.
effort: S
kind: docs
area: website/content, strava-publish
created: 2026-10-31
surfaced_by: /kiro-spec-batch Phase 14, strava-publish design (controller ruling R9)
pinned_at: eb0d8033
resume_command: "do: when the release carrying strava-publish is cut, draft the website/content edits listed in this item for the maintainer's approval, timed with the next release's site-copy PR"
context:
  - website/content/guides/privacy-and-network.md
  - website/content/guides/connectors.md
  - website/content/reference/cli.md
  - website/content/faq.md
  - docs/connectors.md
  - docs/relay.md
  - .kiro/specs/strava-publish/design.md
blocked_by:
  - strava-publish
---

## What
strava-publish adds:
- a built-in `strava` connector, a publish target that reaches Strava only
  through a relay instance;
- `fitdocs connect NAME [--no-browser]` for it, which opens the relay's
  connect page and waits for the connection;
- `fitdocs disconnect NAME` for it, which asks the relay to revoke the
  Strava connection;
- a privacy policy and consent text served by the relay at `/privacy` and
  on the connect page.

Under controller ruling R9, no Phase 14 spec edits `website/content/`. The
repository docs (`docs/connectors.md`, `docs/relay.md`) carry the material.
At the release that ships it, the site needs:
- `website/content/guides/privacy-and-network.md:50-52`: a paragraph on what
  a Strava instance sends and to where (its relay only, never Strava; the
  post and its match facts; the activity file only on an upload), and a link
  to the default relay's privacy policy (`https://api.fitdocs.ai/privacy`).
- `website/content/guides/connectors.md:12`: the built-in connector count
  (relay-server's item already moves it to three; this makes four).
- `website/content/reference/cli.md:50-52`: `--no-browser` on
  `fitdocs connect`, and the browser-consent behaviour for a Strava
  instance.
- A guide section on publishing to Strava, worded as documentation
  ("Compatible with Strava"), pointing at `docs/connectors.md` by GitHub URL.
- `website/content/faq.md:13-14` stays true (fitdocs still reads nothing
  from Strava). If it gains a sentence about posting to Strava, that
  sentence must read as documentation, not an announcement.

## Why it matters
The site's network statement is a privacy promise and becomes incomplete the
day strava-publish ships. Strava's API Policy §4.6 forbids an announcement or
press release that references Strava without Strava's written consent, so
the copy must be descriptive and use only "Compatible with Strava".

## Evidence
- `grep -n "No other command contacts a connector" website/content/guides/privacy-and-network.md`
  gives line 52 (at eb0d8033).
- `grep -n "ships two connectors" website/content/guides/connectors.md`
  gives line 12.
- `grep -n "### \`fitdocs connect NAME\`" website/content/reference/cli.md`
  gives line 50; the entry has no `--no-browser`.
- `grep -n -i strava website/content/faq.md` gives lines 13-14.
- R9 is in the Phase 14 controller's settled-names file, quoted in
  strava-publish design.md under "Settled Seams Applied".

## How to pick it up
1. Read strava-publish's landed Strava section of `docs/connectors.md` and
   the Strava sections of `docs/relay.md`.
2. Draft the edits above in the maintainer's site voice (site copy is the
   maintainer's; agents draft, the maintainer approves), with the release's
   site PR. Use only the brand phrases "Connect with Strava", "View on
   Strava" and "Compatible with Strava".
3. Done when the pages read true for the released version and the site
   build and content checks pass.

## Open questions
- Should the site footer link the default relay's privacy policy? The
  maintainer decides.
