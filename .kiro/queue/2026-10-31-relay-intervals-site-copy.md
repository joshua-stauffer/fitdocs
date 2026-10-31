---
id: 2026-10-31-relay-intervals-site-copy
title: fitdocs.ai site copy for the relay route to intervals.icu (the `intervals-relay` connector), at the release that ships relay-intervals
status: open
importance: medium
importance_why: Once relay-intervals ships, the site's intervals.icu and network statements describe only the API-key route, and the connectors guide undercounts the built-in connectors. Pushing to main deploys the site, so the copy must wait for the release.
effort: S
kind: docs
area: website/content, relay-intervals
created: 2026-10-31
surfaced_by: /kiro-spec-batch Phase 14, relay-intervals design (controller ruling R9)
pinned_at: eb231b1a
resume_command: "do: when the release carrying relay-intervals is cut, draft the website/content edits listed in this item for the maintainer's approval, timed with the next release's site-copy PR"
context:
  - website/content/guides/privacy-and-network.md
  - website/content/guides/connectors.md
  - website/content/reference/cli.md
  - docs/connectors.md
  - docs/relay.md
  - .kiro/specs/relay-intervals/design.md
blocked_by:
  - relay-intervals
  - 2026-10-31-intervals-publish-site-copy
  - 2026-10-31-strava-publish-site-copy
---

## What
relay-intervals adds a second route to intervals.icu:
- a built-in `intervals-relay` connector, a publish-only target that reaches
  intervals.icu through a relay instance, chosen per instance with
  `connector = "intervals-relay"` and `relay = "<relay instance>"` (the
  API-key route stays the default);
- `fitdocs connect NAME [--no-browser]` for it, which opens the relay's
  intervals.icu connect page, and `fitdocs disconnect NAME`, which asks the
  relay to revoke its intervals.icu token;
- intervals.icu sections in the relay's privacy policy.

Under controller ruling R9, no Phase 14 spec edits `website/content/`. The
repository docs (`docs/connectors.md`, `docs/relay.md`) carry the material.
At the release that ships it, the site needs:
- `website/content/guides/privacy-and-network.md:50-52`: a sentence that a
  relay-routed intervals.icu instance sends its requests to its relay only,
  never to intervals.icu from fitdocs, and holds no API key.
- `website/content/guides/connectors.md:12-14`: the built-in connector count
  and list (the other Phase 14 items already move it; this adds
  `intervals-relay`), and a short note on the relay route beside the
  `intervals` entry.
- `website/content/reference/cli.md:50`: the browser-consent behaviour of
  `fitdocs connect` covers relay-routed intervals.icu instances too.
- A guide paragraph on choosing the route, pointing at `docs/connectors.md`
  by GitHub URL.

## Why it matters
The site's network statement is a privacy promise and becomes incomplete the
day relay-intervals ships: it says intervals.icu traffic carries the
athlete's API key, which a relay-routed instance never holds.

## Evidence
- `grep -n "The connector never writes to your account" website/content/guides/privacy-and-network.md`
  gives line 50; `grep -n "No other command contacts a connector"` gives
  line 52 (at eb231b1a).
- `grep -n "ships two connectors" website/content/guides/connectors.md`
  gives line 12; the `intervals` entry is line 14.
- `grep -n "### \`fitdocs connect NAME\`" website/content/reference/cli.md`
  gives line 50.
- R9 is in the Phase 14 controller's settled-names file, quoted in
  relay-intervals design.md under "Settled Seams Applied".

## How to pick it up
1. Read relay-intervals' landed "Publishing through a relay" subsection of
   `docs/connectors.md` and the intervals.icu sections of `docs/relay.md`.
2. Draft the edits above in the maintainer's site voice (site copy is the
   maintainer's; agents draft, the maintainer approves), after the
   intervals-publish and strava-publish site items, whose lines these
   follow.
3. Done when the pages read true for the released version and the site
   build and content checks pass.

## Open questions
- Should the site explain when to choose the relay route over the API key,
  or only that it exists? The maintainer decides.
