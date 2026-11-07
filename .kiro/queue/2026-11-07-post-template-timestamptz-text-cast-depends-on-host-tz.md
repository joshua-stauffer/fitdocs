---
id: 2026-11-07-post-template-timestamptz-text-cast-depends-on-host-tz
title: "Make a TIMESTAMPTZ-to-text cast in a post template independent of the host time zone"
status: open
importance: medium
importance_why: "The same template fills different text on different machines, which breaks the stable-post promise."
effort: S
kind: bug
area: "post-templates, analytics-query, src/fitdocs/query/sandbox.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-requirements post-templates [queue: .kiro/queue/2026-11-07-post-template-timestamptz-text-cast-depends-on-host-tz.md] Pin the sandbox TimeZone or lint TIMESTAMPTZ text casts"
context:
  - src/fitdocs/query/sandbox.py
  - src/fitdocs/post_template/resolve.py
  - .kiro/specs/analytics-query/design.md
blocked_by: []
---

## What
`SELECT CAST(to_timestamp(0) AS VARCHAR)` gives a string carrying the host's offset. The post-template lint does not refuse it, and the query sandbox sets no `TimeZone`.

## Why it matters
A post filled on one machine and refilled on another differs, and the refill then names a changed landed post.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. The probe gave `'1970-01-01 01:00:00+01'` on the maintainer's machine. `grep -rni timezone src/fitdocs/query` is empty.

## How to pick it up
1. Confirm with the probe in a scratch root.
2. Choose between setting `TimeZone='UTC'` in the sandbox connection, which changes `fitdocs query` output too (an analytics-query amendment), and linting TIMESTAMPTZ-to-text casts in post templates only.
3. Add a test.

## Open questions
Which of the two fixes; the first also changes dashboards.
