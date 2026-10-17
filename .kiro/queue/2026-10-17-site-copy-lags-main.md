---
id: 2026-10-17-site-copy-lags-main
title: fitdocs.ai site copy still describes 0.1.0 on skills, commands, contract version, owned paths and connectors
status: open
importance: medium
importance_why: The rewritten Working-with-an-LLM page now names four skills, the index and eight AGENTS.md folders; its sibling pages contradict it until they are updated.
effort: M
kind: docs
area: docs-site, website content (iCloud: ~/Library/Mobile Documents/com~apple~CloudDocs/fitdocs.ai)
created: 2026-10-17
surfaced_by: maintainer-requested rewrite of the site's llm/index.md against the repository
pinned_at: 7b0837f
resume_command: "do: Update the fitdocs.ai site pages listed under Evidence to match main (four packaged skills, fifteen commands, the current contract version and owned paths, connectors shipped); keep each page's iA Writer Annotations block current (pkm skill ia-writer-annotations) and validate with: uv run --group docs python -m scripts.build_site build --content \"<content dir>\" --build-dir <scratch>"
context:
  - docs/website.md
  - docs/wiki-integration.md
  - docs/ownership-contract.md
  - docs/connectors.md
  - src/fitdocs/contract.py
  - src/fitdocs/cli.py
blocked_by: []
---

## What
The site content directory (outside the repo; `website/content/` holds only
`.gitkeep`) was drafted on 2026-09-28 against the published 0.1.0. The home
page and `llm/index.md` were rewritten on 2026-10-17 for current `main`,
so several sibling pages now contradict them.

## Why it matters
A reader who follows the LLM page's links lands on pages that say there are
two skills, nine commands, no connectors and contract version 4. The site
will publish those statements as current.

## Evidence
Checked 2026-10-17 at main 7b0837f against the content directory:

- `guides/wiki-integration.md` (site): skills table lists `fitdocs-workouts`
  and `build-training-block` only; "It only writes to its own folders" names
  five directories; the root-instructions pointer names four `AGENTS.md`
  files. Repo: `uv run fitdocs skill` lists four skills
  (build-training-block, fitdocs-workouts, fitdocs-analytics,
  fitdocs-dashboards); `docs/ownership-contract.md` "Owned Paths" adds
  `dashboards/`, `wellness/`, `wellness-archive/`, `recovery/` and names
  eight `AGENTS.md` files.
- `reference/ownership.md` (site): "currently version 4"; owned-paths table
  stops at `.fitdocs/`. Repo: `CONTRACT_VERSION: Final[str] = "14"` in `src/fitdocs/contract.py`.
- `reference/cli.md` (site): nine command headings. Repo:
  `uv run fitdocs --help` lists 15 commands (adds index, recovery, connect,
  pull, query, dashboard).
- `faq.md` (site): "Does it download my activities from Garmin or Strava?
  Not yet … Connectors, starting with intervals.icu, are next on the
  roadmap." Repo: `docs/connectors.md`, `fitdocs connect` / `fitdocs pull`
  shipped (connectors spec complete 2026-10-02).
- `getting-started/quickstart.md` (site): the last "Where to go next"
  bullet, "Let an LLM run it: Working with an LLM.", has no link while the
  other three do.
- `faq.md` ends in an `Annotations:` block whose SHA-256 no longer matches
  its content (file modified 2026-10-17 14:26 outside iA Writer), so its
  authorship spans are stale.

## How to pick it up
Read `docs/website.md` (content contract, link rules, annotation block),
then open each page above beside its repo source. Update facts only; keep
the maintainer's `@Josh` spans verbatim and regenerate each page's
`Annotations:` block. Done when the standalone build exits 0 and the pages
agree with the LLM page and the repo docs.

## Open questions
Whether the site should describe current `main` or the latest PyPI release
(0.1.0 is still the only tag). The home and LLM pages already describe
`main`.
