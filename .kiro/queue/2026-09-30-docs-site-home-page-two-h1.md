---
id: 2026-09-30-docs-site-home-page-two-h1
title: The docs-site home page renders two h1 elements
status: open
importance: low
importance_why: Two h1s on the home page (hero title plus Material's skip-link page title) is an accessibility wrinkle; which one should remain is a design decision.
effort: S
kind: gap
area: docs-site, website/overrides/home.html
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "do: during the docs-site visual-design iteration, decide with the maintainer which home-page h1 remains and adjust website/overrides/home.html"
context:
  - website/overrides/home.html
  - .kiro/specs/docs-site/design.md
blocked_by: []
---

## What
The hero `<h1 class="fd-hero__title">` is followed by Material's `<h1 id="__skip">` page title, which is also the skip-link target.

## Evidence
Reviewer smoke build during docs-site 3.1; zensical/templates/partials/content.html:5-7.

## How to pick it up
Decide with the maintainer during the planned visual-design iteration: demote the hero title, or suppress the page title on home while keeping the skip target.

## Open questions
Maintainer's call on the hero title vs page title.
