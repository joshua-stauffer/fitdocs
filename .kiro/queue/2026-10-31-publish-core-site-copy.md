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
pinned_at: d1f8ae9b
resume_command: "do: at the release that carries publish-core, draft the site copy listed in .kiro/queue/2026-10-31-publish-core-site-copy.md for the maintainer, in the held site-copy PR (chore/site-copy-0-2 or its successor), never by a push to main"
context:
  - .kiro/specs/publish-core/design.md
  - docs/publishing.md
  - docs/ownership-contract.md
  - website/content/guides/workout-pages.md
  - website/content/reference/cli.md
  - website/content/reference/configuration.md
  - website/content/reference/ownership.md
  - CHANGELOG.md
blocked_by: [publish-core]
---

## What
publish-core adds `fitdocs publish`, the `[publish]` settings table, the
`publish` frontmatter key, the `post` and `published` regions on every
workout page, and advances `DOC_VERSION` and `CONTRACT_VERSION` by one each
(main + 1 at landing). By controller ruling R9 no Phase 14 spec edits
`website/content/`, so the site copy waits for the release:

- a publishing guide page in the Guides section (next free `order`),
  derived from `docs/publishing.md`, naming no service (each target's own
  guide is its spec's queue item);
- `website/content/reference/cli.md`: a `fitdocs publish [PAGES...] [--to
  TARGET] [--yes] [--targets] [--format text|json]` entry;
- `website/content/reference/configuration.md`: a `[publish]` entry beside
  `[connectors.<name>]`;
- `website/content/guides/workout-pages.md:25`: the example frontmatter shows
  `doc_version: 11`; it becomes the landed value, and the page could mention
  the `post` region and the `Published:` links line;
- `website/content/reference/ownership.md:10`: "currently version 16" (already
  stale per `2026-10-27-site-copy-contract-17-and-map-viewer-floor`) becomes
  the landed contract version, and line 74's causes list may need "a new
  region".

## Why it matters
The site is the public front door. A user reading it after the release would
find no publishing documentation and an example page that is a version
behind.

## Evidence
- `grep -n "doc_version" website/content/guides/workout-pages.md` → line 25
  (`doc_version: 11`), at d1f8ae9b.
- `grep -n "currently version" website/content/reference/ownership.md` →
  line 10, at d1f8ae9b.
- `website/content/reference/cli.md` and `configuration.md` headings list no
  `publish` entry (`grep -n "^### " website/content/reference/*.md`).

## How to pick it up
1. Read `docs/publishing.md` and publish-core's design ("PublishingDocs").
2. Draft the five changes above for the maintainer in the held site-copy PR;
   the site copy is the maintainer's voice, and a push to `main` deploys it.
3. Done when the site build and checks pass on the PR and the maintainer has
   approved the copy.
