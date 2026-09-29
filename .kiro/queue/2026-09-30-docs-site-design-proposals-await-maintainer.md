---
id: 2026-09-30-docs-site-design-proposals-await-maintainer
title: Confirm or amend the docs-site design proposals the --auto run approved on the maintainer's behalf
status: open
importance: medium
importance_why: Brand, hero shape and two contract rules become code and fixtures in /kiro-impl docs-site tasks 1.3 and 3.1; changing them after that is rework across tests, fixtures and docs/website.md.
effort: S
kind: spec-work
area: docs-site, .kiro/specs/docs-site/design.md
created: 2026-09-30
surfaced_by: /kiro-spec-quick docs-site --auto
pinned_at: 73a4ea5
resume_command: "do: Read .kiro/specs/docs-site/design.md § Theme, § SiteModel and § Data Models, then have the maintainer confirm or amend the four proposals in this item before /kiro-impl docs-site reaches tasks 1.3 and 3.1; record the answer in design.md and close this item"
context:
  - .kiro/specs/docs-site/design.md
  - .kiro/specs/docs-site/research.md
  - .kiro/specs/docs-site/requirements.md
  - .kiro/specs/docs-site/tasks.md
blocked_by: []
---

## What
The requirements leave the brand's concrete values to the design, which the
maintainer approves (requirements.md Introduction; 4.5). `/kiro-spec-quick
--auto` set every approval flag without an interactive review. Four design
choices therefore stand unconfirmed:
1. **Brand values**:
   - graphite header `#1f2933`;
   - accent `#b8324b` in light mode and `#f07d8e` in dark mode, derived from
     the hero chart's heart-rate red;
   - system font stacks with `theme.font: false`, so no third-party font
     request is made;
   - a placeholder page-and-pulse logo;
   - Material `variant: classic`.
2. **The `hero_actions` shape**: `{label, href, primary?}`. A relative `href`
   is a trailing-slash site path, such as `get-started/install/`, not a `.md`
   path. The maintainer's out-of-repo draft may use another shape.
3. **Dotfile exclusion**: names beginning with `.` are excluded like `_`
   names. Requirement 1.4 originally named only `_`, and was amended to
   match (item 5). The design argues it is observably equivalent, because Zensical skips dotfiles and the Pages
   artifact excludes them.
4. **Symbolic links refused**: a symlink anywhere in the content directory
   is a contract violation, rather than being followed or dropped.
5. **Requirements amended to match** (2026-09-30, quick-spec sanity
   review):
   - 1.4 adds `.`-prefixed exclusion;
   - 1.6 and 3.3 add the one `template` line injected into the home
     page's built copy;
   - 2.3 defines the `hero_actions` shape;
   - 2.10 limits page links to markdown syntax;
   - 6.5 reports each generator problem as one line;
   - new 2.11 fails on symlinks and on a root `llms.txt` /
     `llms-full.txt`;
   - new 2.12 fails on a raw-HTML link to a `.md` page;
   - the boundary names the `CHANGELOG.md` `[Unreleased]` entry.

   These were applied to requirements.md after `--auto` approval, so they
   too await the maintainer's confirmation.

## Why it matters
- Task 1.3 bakes these choices into the fixture site, and task 3.1 into
  `brand.css`, `logo.svg` and `home.html`.
- Task 6.1 states them in `docs/website.md` as the content contract.
- If the maintainer's draft uses a different `hero_actions` shape, it fails
  the contract on import.
- A brand change after implementation means re-pinned tests.

## Evidence
- design.md § Theme (the brand table), § SiteModel (`HERO_ACTION_KEYS`),
  § ContentLoader (discovery rules) and § Data Models (content contract
  table).
- research.md § Design Decisions: "Brand values (proposed, maintainer
  approval at design review)" and "Dotfiles and symbolic links in the
  content directory".
- spec.json `phase_note` records that `--auto` approved without review.

## How to pick it up
1. Show the maintainer the five items above, with the design.md sections
   they live in (requirements.md for item 5).
2. For each item, record "confirmed" or the new value in design.md, and in
   requirements.md for item 5. Reverting an item 5 amendment means
   revisiting the design choice it records.
3. Close this item with `/kiro-queue close`.

## Open questions
- Does the maintainer's draft `index.md` already carry `hero_actions`, and in
  what shape?
