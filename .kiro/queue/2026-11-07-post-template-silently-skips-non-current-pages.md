---
id: 2026-11-07-post-template-silently-skips-non-current-pages
title: "Report non-current pages a bare refill or check skips"
status: open
importance: low
importance_why: "After a DOC_VERSION bump an athlete sees only the Template line and no reason nothing was filled."
effort: S
kind: gap
area: "post-templates, src/fitdocs/post_template/engine.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-requirements post-templates [queue: .kiro/queue/2026-11-07-post-template-silently-skips-non-current-pages.md] Count pages a bare refill/check skips for being older-format or damaged"
context:
  - src/fitdocs/post_template/engine.py
  - src/fitdocs/post_template/report.py
  - .kiro/specs/post-templates/requirements.md
blocked_by: []
---

## What
A bare `refill`, and a bare `check`'s Eligible count, skip pages that are not current (older format or damaged), with no count or line.

## Why it matters
The common post-upgrade state looks like "nothing to do".

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. See `src/fitdocs/post_template/engine.py` around 722-725 (`if pages or isinstance(read, PageResult): ... continue`). The probe: `refill --yes` over 4 damaged pages exits 0 and prints only the Template line. Req 10.2 does not require counting them.

## How to pick it up
1. Add a `not_current_left_out` count to FillReport, or a line pointing at `fitdocs regen`.
2. Amend Req 10.6 and 9.2.
