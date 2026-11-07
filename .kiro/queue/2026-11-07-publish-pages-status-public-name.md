---
id: 2026-11-07-publish-pages-status-public-name
title: Give publish.pages._status a public name
status: open
importance: low
importance_why: post_template.engine is the only module in src/fitdocs importing a private name from another module.
effort: S
kind: chore
area: publish-core, post-templates, src/fitdocs/publish/pages.py
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: rename or alias publish.pages._status as a public function (e.g. page_view) and use it from post_template.engine [queue: .kiro/queue/2026-11-07-publish-pages-status-public-name.md]"
context:
  - src/fitdocs/publish/pages.py
  - src/fitdocs/post_template/engine.py
  - .kiro/specs/post-templates/tasks.md
blocked_by: []
---

## What
`post_template.engine` imports `publish.pages._status` so a page is read once, with status and bytes from the same read (3.1 ruling).

## Why it matters
Private cross-package imports are easy to break in a publish refactor.

## Evidence
An AST scan of src/fitdocs by the 3.1 reviewer printed only `fitdocs.post_template.engine <- fitdocs.publish.pages _status`.

## How to pick it up
1. Add a public alias in pages.py.
2. Switch engine to it.
3. Keep the boundary tables equal.
