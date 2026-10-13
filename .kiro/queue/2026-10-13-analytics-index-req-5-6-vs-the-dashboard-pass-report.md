---
id: 2026-10-13-analytics-index-req-5-6-vs-the-dashboard-pass-report
title: analytics-index Req 5.6 still forbids reading the index for any command's output but `fitdocs index` and the analytics commands, while sync, regen, load and pull --sync now print a dashboard pass report built from index reads
status: open
importance: low
importance_why: A requirement that the shipped behaviour contradicts on its face; Amendment 1 excepted the dashboard chart regions and assets but not the pass report printed to the terminal.
effort: S
kind: inconsistency
area: analytics-index, dashboards, .kiro/specs/analytics-index/requirements.md
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 8.2 reviewer)
pinned_at: 0a98d5c
resume_command: "/kiro-spec-requirements analytics-index [queue: .kiro/queue/2026-10-13-analytics-index-req-5-6-vs-the-dashboard-pass-report.md] extend the Req 5.6 dashboards exception to the pass report the writing commands print"
context:
  - .kiro/specs/analytics-index/requirements.md
  - .kiro/specs/analytics-index/design.md
  - .kiro/specs/dashboards/requirements.md
  - src/fitdocs/cli.py
blocked_by:
  - dashboards
---

## What
Req 5.6 reads: "fitdocs shall never read the index to produce a document, a
document value, or the output of any command other than `fitdocs index` and the
analytics commands built on it, except the chart regions and chart assets of
dashboard pages under `dashboards/`, which are the only document content
produced from the index. _(amended by Amendment 1)_". The exception covers
document content only. The pass that `fitdocs sync`, `fitdocs regen`,
`fitdocs load` and `fitdocs pull --sync` run after the index refresh queries
the index and prints its report (counts, problems, notices) as part of those
commands' output.

## Why it matters
A reader checking the shipped behaviour against the requirement finds a
violation, and the amendment that was meant to reconcile the two did not reach
the printed output. It is the requirement, not the code, that is out of step:
dashboards Req 13.6 deliberately prints the report.

## Evidence
- `.kiro/specs/analytics-index/requirements.md:186` (Req 5.6 as amended) and `:310` (the "Amendment 1 (2026-10-13)" heading).
- `src/fitdocs/cli.py:575-620` `_run_dashboard_pass`: runs `run_dashboards(...)` over `source_opener(...)` and prints `render_text(report, chained=True)`; called from `sync_command` (`cli.py:827`), `_run_drain_passes` (`:914`; called at `:841` and, for `pull --sync`, at `:1544`), `regen_command` (`:1013`) and `load_command` (`:1049`).
- `.kiro/specs/dashboards/requirements.md:262-268`, Req 13.1 and 13.6 (the pass runs after those commands and prints its report).

## How to pick it up
1. Read analytics-index Amendment 1 (`requirements.md:310` onward) and Req 5.6.
2. Amend Req 5.6's exception to read "the chart regions and chart assets of dashboard pages under `dashboards/`, and the report of the dashboard pass that reads the index to produce them", or equivalent.
3. Keep the sentence that chart regions and assets are the only document content produced from the index. Check `design.md`'s traceability row for 5.6 and the ownership contract's statement of the same rule (`docs/ownership-contract.md`, search "only document content").

## Open questions
None beyond wording; this is a requirement amendment for the maintainer to approve under the three-phase workflow, hence `/kiro-spec-requirements`.
