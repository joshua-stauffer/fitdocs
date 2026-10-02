---
id: 2026-10-02-docs-site-dark-scheme-hero-buttons-unreadable
title: "Dark (slate) scheme: non-primary hero buttons render graphite on graphite, primary is white on #f07d8e"
status: open
importance: medium
importance_why: "The first hero_actions the home page gets will be near-invisible to every dark-mode visitor."
effort: S
kind: bug
area: docs-site, website/assets/brand.css
created: 2026-10-02
surfaced_by: seeding the fitdocs.ai Design canvas (dark home page)
pinned_at: 52d9169
resume_command: "do: give .md-button a slate-scheme color in website/assets/brand.css (and check .md-button--primary text contrast on #f07d8e), then build a page with hero_actions and look at it in dark mode [queue: .kiro/queue/2026-10-02-docs-site-dark-scheme-hero-buttons-unreadable.md]"
context:
  - website/assets/brand.css
  - website/overrides/home.html
  - website/mkdocs.template.yml
blocked_by: []
---

## What
Material's `.md-typeset .md-button` sets `color: var(--md-primary-fg-color)` in every scheme. `brand.css` sets `--md-primary-fg-color: #1f2933` for both `default` and `slate`, so in slate a non-primary hero button draws #1f2933 text and border on the slate background `hsla(225,15%,14%,1)` (about #1e2129). `.md-button--primary` gets `background-color: #f07d8e` with white text, roughly 2.6:1, under the 4.5:1 body-text bar.

## Why it matters
No page uses `hero_actions` yet, so nothing is broken today. The first home page with a hero ships unreadable buttons to dark-mode visitors, and no test looks at rendered colours.

## Evidence
- Built CSS (zensical 0.0.65): `assets/stylesheets/classic/main.*.min.css` has `.md-typeset .md-button{...color:var(--md-primary-fg-color)...}`; `palette.*.min.css` slate block sets `--md-default-bg-color:hsla(var(--md-hue), 15%, 14%, 1)`.
- `website/assets/brand.css:3-12` sets `--md-primary-fg-color: #1f2933` for `:root`, `default` and `slate` together; `:21-25` slate accent `#f07d8e`; `:27-30` primary button background = accent.

## How to pick it up
1. In `brand.css`, add a `[data-md-color-scheme="slate"] .md-typeset .md-button` rule with a light text/border colour, and choose a primary-button text colour that clears 4.5:1 on the slate accent (or darken the fill).
2. Build a content dir whose `index.md` sets `hero_actions` with one primary and one plain action; check both schemes.
3. Fold in whatever the 2026-10 Claude Design pass on the site decides for buttons, if it has landed.
