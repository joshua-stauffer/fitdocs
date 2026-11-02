---
id: 2026-10-31-publish-core-site-copy
title: fitdocs.ai site copy for publish-core (publishing guide, CLI and config reference, stale doc_version and contract version)
status: open
importance: medium
importance_why: The public site describes released versions only; once publish-core ships, the site has no publishing page and shows a stale page format and contract version.
effort: S
kind: docs
area: website/content, publish-core
created: 2026-10-31
surfaced_by: /kiro-spec-batch Phase 14 (publish-core Step 3.5 review, controller ruling R9)
pinned_at: fdc0a70c
resume_command: "do: at the release that carries publish-core, draft the site copy listed in .kiro/queue/2026-10-31-publish-core-site-copy.md for the maintainer, in the held site-copy PR (chore/site-copy-0-2 or its successor), never by a push to main"
context:
  - .kiro/specs/publish-core/design.md
  - docs/publishing.md
  - docs/ownership-contract.md
  - website/content/guides/workout-pages.md
  - website/content/reference/cli.md
  - website/content/reference/configuration.md
  - website/content/reference/ownership.md
  - website/content/guides/wiki-integration.md
  - website/content/guides/privacy-and-network.md
  - website/content/faq.md
  - website/content/llm/prompts.md
  - CHANGELOG.md
blocked_by: [publish-core]
---

## What
publish-core adds `fitdocs publish`, the `[publish]` settings table, the
`publish` frontmatter key, the `post` and `published` regions on every
workout page, and the `.fitdocs/publish/` ledgers. It advances `DOC_VERSION`
11 to 12 and `CONTRACT_VERSION` "17" to "18" (landed values, read from
`src/fitdocs/contract.py` at fdc0a70c). By controller ruling R9 no Phase 14
spec edits `website/content/`, so the site copy waits for the release. Every
line below is READ-only evidence from `website/content/`; the maintainer
writes the copy.

New copy:

- a publishing guide page in the Guides section (next free `order`),
  derived from `docs/publishing.md`, naming no service (each target's own
  guide is its spec's queue item);
- `website/content/reference/cli.md`: a `fitdocs publish [PAGES...] [--to
  TARGET] [--yes] [--targets] [--format text|json] [--out PATH]` entry (new
  `###` heading; the "Processing workouts" group at line 16 or a new group
  before "Inspecting" at line 132);
- `website/content/reference/configuration.md`: a `[publish]` entry beside
  `[connectors.<name>]` (line 152), and `.fitdocs/publish/` ledgers wherever
  `.fitdocs/` state is described.

Stale lines (each cites the landed value or fact it must show):

- `website/content/guides/workout-pages.md:25`: example frontmatter
  `doc_version: 11` becomes `doc_version: 12`; the example frontmatter
  (lines 21-45) could show the optional `publish` key.
- `website/content/guides/workout-pages.md:95-104` ("Editing rules, in one
  place"): add rows for the `post` region (you, kept exactly), the `publish`
  key (you, kept exactly) and the `published` region (fitdocs, refilled by
  `fitdocs publish --yes`; hand edits replaced); line 101's "Race tag keys
  in frontmatter (`effort`, ...)" row is where `publish` belongs. The page
  sections (lines 49-91) gain a `Post` and a `Published` section.
- `website/content/reference/ownership.md:10`: "currently version 16"
  becomes "currently version 18" (already stale per
  `2026-10-27-site-copy-contract-17-and-map-viewer-floor`).
- `website/content/reference/ownership.md:43-52` (the "Inside a generated
  page" table): add `post` (you, kept word for word), `published`
  (fitdocs, refilled by `fitdocs publish --yes`), and the `publish`
  frontmatter key beside line 51's effort keys (you, kept word for word).
- `website/content/reference/ownership.md:27`: the `.fitdocs/` row lists
  "the quarantine record, files held because they matched more than one
  page, and each connector's delivery record"; add each publish target's
  ledger under `.fitdocs/publish/`.
- `website/content/reference/ownership.md:74`: the contract-version causes
  list ("a new owned path, a new page type, or a new class of user-owned
  key") may add "a new region".
- `website/content/guides/wiki-integration.md:102`: the agent-pointer text
  "Notes and Workout sections of a workout page, the race-tag frontmatter
  keys" omits the `post` region and the `publish` key (the shipped
  README now names both).
- `website/content/faq.md:35`: "You can edit the parts that are yours: the
  Notes section, the Workout section on strength pages, and the race-tag
  frontmatter keys" omits the `post` region and the `publish` key.
- `website/content/reference/cli.md:34`: `regen` "Your Notes, Workout
  sections, race tags, and computed load are kept" omits the `post` region
  and the `publish` key; the line also says to run `regen` "after a release
  that changes the document format", which this release is (12).
- `website/content/changelog.md` (top of the file): the site changelog has
  no entry for this release; it needs the publishing, regions, `publish`
  key, "ownership contract version 17 to 18, document format 11 to 12: run
  `fitdocs regen`" lines, mirroring `CHANGELOG.md` `[Unreleased]`. Line 59
  records "4 to 16" and "5 to 11" for 0.2.0 and stays as history.
- `website/content/guides/privacy-and-network.md:12`, `:50`, `:52` and
  `website/content/faq.md:17`: "Only map tiles and connectors use the
  network", "The connector never writes to your account", "No other command
  contacts a connector" and "a connector you set up, which only reads from
  your own account" stop being true once a publish target exists
  (`fitdocs publish --yes` sends posts). publish-core ships no target, so
  these go stale with the first release that carries one (intervals-publish
  / strava-publish); the release that carries publish-core and a target must
  rewrite them. Their wording is the maintainer's.
- `website/content/llm/prompts.md:205` and `:281`: the race-tagging and
  rename prompts name only the race-tag keys and the Notes and Workout
  sections; a publishing prompt ("write my post in the `post` region") is a
  candidate addition.

Checked and not stale: no site line states a command count (the
`grep -rn -i "fifteen\|[0-9][0-9] commands"` search returns nothing), and
"four packaged skills" (`cli.md:144`, `prompts.md:34`) is unchanged because
publish-core adds a section to an existing skill, not a skill.

## Why it matters
The site is the public front door. A user reading it after the release would
find no publishing documentation and an example page that is a version
behind.

## Evidence
At fdc0a70c, all `website/content/`-relative:
- `grep -n "doc_version" guides/workout-pages.md` -> line 25 (`doc_version:
  11`).
- `grep -n "currently version" reference/ownership.md` -> line 10 ("currently
  version 16").
- `grep -n "^### " reference/cli.md reference/configuration.md` -> no
  `publish` entry (cli.md lists sync through `--version`; configuration.md
  ends its tables at `[connectors.<name>]`, line 152).
- `grep -n "effort_event" reference/ownership.md guides/workout-pages.md
  faq.md guides/wiki-integration.md` -> ownership.md:51, workout-pages.md:101
  (as "`effort`, ..."), wiki-integration.md:102 and faq.md:35 (as "race-tag
  frontmatter keys"): the user-owned set without `publish`.
- `grep -n "fitdocs:begin\|^| .notes. " reference/ownership.md` -> the region
  table at lines 45-52 lists `notes`, `workout`, `load`, `morning`, no `post`
  or `published`.
- `grep -n -i "never writes to your account\|only reads from\|no other
  command" guides/privacy-and-network.md faq.md` -> privacy-and-network.md:50
  and :52, faq.md:17.
- `grep -n "DOC_VERSION: Final\|CONTRACT_VERSION: Final"
  src/fitdocs/contract.py` -> `DOC_VERSION ... = 12`, `CONTRACT_VERSION ...
  = "18"`.

## How to pick it up
1. Read `docs/publishing.md` and publish-core's design ("PublishingDocs").
2. Draft the changes above for the maintainer in the held site-copy PR;
   the site copy is the maintainer's voice, and a push to `main` deploys it.
3. Done when the site build and checks pass on the PR and the maintainer has
   approved the copy.
