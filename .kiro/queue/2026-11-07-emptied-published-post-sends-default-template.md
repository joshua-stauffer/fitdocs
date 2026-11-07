---
id: 2026-11-07-emptied-published-post-sends-default-template
title: "Decide what publish does with an emptied post region on an already-published page"
status: open
importance: medium
importance_why: "Emptying a published page's post and running `publish --yes` overwrites the posted activity with the target's default text."
effort: M
kind: spec-work
area: "post-templates, publish-core, src/fitdocs/publish/engine.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-requirements post-templates [queue: .kiro/queue/2026-11-07-emptied-published-post-sends-default-template.md] Decide publish behavior for an emptied, landed post region"
context:
  - src/fitdocs/publish/engine.py
  - src/fitdocs/post_template/engine.py
  - .kiro/specs/post-templates/requirements.md
  - docs/publishing.md
blocked_by: []
---

## What
A page with a landed post is not Eligible, so sync does not refill an emptied region on it, and publish does not refuse it (Req 12.5). `publish --yes` therefore composes the target's own template and updates the activity. The docs now warn about this.

## Why it matters
One emptied region plus one `publish --yes` replaces a posted description with default text.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. The end-to-end probe in /kiro-validate-impl showed `would_update` with the default template after emptying a landed page. See `publish/engine.py` `_is_eligible` (no landed post required) and the `run_pass` eligible filter.

## How to pick it up
1. Read Req 6.3, 12.1, 12.5 and the docs warning in docs/publishing.md.
2. Options: refuse an emptied landed page with `post_waiting` or a new code; or have sync/refill refill it.
3. Spec the choice.

## Open questions
Which option the maintainer wants.
