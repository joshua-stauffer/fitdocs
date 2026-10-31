---
id: 2026-10-31-relay-server-site-copy-at-next-release
title: fitdocs.ai site copy for the relay connector, `fitdocs connect --register` and `fitdocs disconnect`, at the release that ships relay-server
status: open
importance: medium
importance_why: Once relay-server ships, the public site says "no other command contacts a connector" and "fitdocs ships two connectors", which become false. It also has no relay or self-hosting guide. Pushing to main deploys the site, so the copy must wait for the release.
effort: S
kind: docs
area: website/content, relay-server
created: 2026-10-31
surfaced_by: /kiro-spec-batch Phase 14, relay-server Step 3.5 review (controller ruling R9)
pinned_at: d82996fb
resume_command: "do: when the release carrying relay-server is cut, draft the website/content edits listed in this item for the maintainer's approval, timed with the held site-copy PR (chore/site-copy-0-2 or its successor)"
context:
  - website/content/guides/privacy-and-network.md
  - website/content/guides/connectors.md
  - website/content/reference/cli.md
  - docs/relay.md
  - docs/connectors.md
  - .kiro/specs/relay-server/design.md
blocked_by:
  - relay-server
---

## What
relay-server adds three things:
- a relay connector;
- `fitdocs connect NAME --register [--email ADDRESS]`, a device-style
  registration that polls a relay;
- `fitdocs disconnect NAME [--local-only]`, which revokes a relay token
  with one request.

Under controller ruling R9, no Phase 14 spec edits `website/content/`. The
site describes released versions only. The repository docs (`docs/relay.md`,
`docs/connectors.md`) carry the new material, and the site needs, at the
release that ships it:
- `website/content/guides/privacy-and-network.md:50-52`. "`fitdocs connect`
  and `fitdocs pull` send requests ... No other command contacts a
  connector" goes stale. `fitdocs disconnect` contacts a relay, and
  `connect --register` polls it. The page should say what a relay instance
  sends (the token in a header; for registration, the typed email address),
  and when.
- `website/content/guides/connectors.md:12`. "Fitdocs ships two
  connectors:" becomes three.
- `website/content/reference/cli.md:50-56`. There is no `--register` or
  `--email` on `fitdocs connect`, and no `fitdocs disconnect` entry.
- A site guide to connecting fitdocs to a relay, and one to running your own
  relay (local SQLite run, the image from a pinned commit, migrate then
  serve, minting a token, switching to PostgreSQL). Each points at
  `docs/relay.md` by GitHub URL rather than restating the contract.

## Why it matters
The site is the public front door. Its network statement is a privacy
promise, and it becomes false the day relay-server ships.

## Evidence
- `grep -n "No other command contacts a connector" website/content/guides/privacy-and-network.md`
  gives line 52 (verified at d82996fb).
- `grep -n "ships two connectors" website/content/guides/connectors.md`
  gives line 12.
- `grep -n "^### \`fitdocs" website/content/reference/cli.md` lists
  `connect` at 50 and `pull` at 54, and no `disconnect`.
- R9 is in the Phase 14 controller's settled-names file, quoted in
  relay-server design.md under "Settled Seams Applied".

## How to pick it up
1. Read relay-server's landed `docs/relay.md` and the relay section of
   `docs/connectors.md`. These are the facts the site copy summarizes.
2. Draft the edits above in the maintainer's site voice (site copy is the
   maintainer's; agents draft, the maintainer approves), together with the
   next release's site PR.
3. Done when the three pages and the two guides read true for the released
   version, and the site build and content checks pass.

## Open questions
- Should the self-hosting guide live on the site at all, or should the site
  only link the repository page? The maintainer decides.
