---
id: 2026-11-01-connector-network-statements-omit-disconnect
title: 'Roadmap and configuration docs still name only connect and pull as reading or contacting connectors'
status: open
importance: low
importance_why: `fitdocs disconnect` reads the [connectors] table and contacts a relay; the docs undercount it.
effort: S
kind: docs
area: .kiro/steering/roadmap.md, docs/configuration.md
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 8.5 review
pinned_at: 774a883c
resume_command: "do: edit docs/configuration.md:64 and :357-359 to name fitdocs disconnect as reading the [connectors] table, and annotate .kiro/steering/roadmap.md:3080-3082; see .kiro/queue/2026-11-01-connector-network-statements-omit-disconnect.md"
context:
  - .kiro/steering/roadmap.md
  - docs/configuration.md
  - .kiro/steering/tech.md
blocked_by: []
---

## What
Two statements list only `connect` and `pull`. The roadmap's Phase 12 constraint is historical and may stay as written with a pointer; the configuration page is current documentation and `disconnect` also reads the `[connectors]` table (not a network statement there).

## Why it matters
A reader concludes only two commands touch connector configuration; the site-copy item for relay-server separately covers the network statements.

## Evidence
- `.kiro/steering/roadmap.md:3080-3082`: "explicit `fitdocs connect` and `fitdocs pull` requests" (tech.md now names disconnect).
- `docs/configuration.md:64` and `:357-359`: "for `fitdocs connect` and `fitdocs pull`".

## How to pick it up
1. Edit configuration.md at both places to include `fitdocs disconnect`.
2. In the roadmap, add a one-line note that disconnect was added later (leave the historical constraint text).
3. Run the docs tests.

## Update 2026-11-02 (strava-publish 7.6 review, pinned 964cc419)
The same omission now also leaves out the Strava consent path, which contacts the relay's connect page and revokes at Strava via the relay. Current text at HEAD still reads "(revoking a relay token)":
- `README.md:71`: "`fitdocs disconnect` (revoking a relay token)"
- `docs/configuration.md:78`: "`fitdocs disconnect` (revoking a relay token)"
Reword both to cover browser-consent (Strava) revocation as well, in the same edit as the disconnect additions above. The `cli.py` module docstring and `tech.md` were already fixed on impl/strava-publish; the `disconnect` command's own docstring (`src/fitdocs/cli.py` ~1827-1836) was not re-read in this run.
