---
id: 2026-10-13-chart-body-accepts-kit-markdown-that-corrupts-the-region
title: region.chart_body refuses kit lines that start with a fitdocs comment marker but not fence-opening lines, and assumes the kit's markdown is newline-joined with no trailing newline
status: open
importance: low
importance_why: Not reachable with today's markdown kinds (stat, table); the first markdown kind that emits a code fence, a trailing newline or a CR writes a region that scans back unclosed or carries a stray blank line.
effort: S
kind: gap
area: dashboards, chart-kit, src/fitdocs/dashboards/region.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 4.1 reviewer)
pinned_at: 0a98d5c
resume_command: "do: state the markdown-output contract the region relies on (no unclosed fence, no CR, no trailing newline) in the chart-kit design and have region.chart_body refuse a violating kit text with a ValueError the engine already treats as a chart failure; pin each with a test [queue: .kiro/queue/2026-10-13-chart-body-accepts-kit-markdown-that-corrupts-the-region.md]"
context:
  - src/fitdocs/dashboards/region.py
  - src/fitdocs/dashboards/grammar.py
  - src/fitdocs/render/charts/kit/kinds/stat.py
  - src/fitdocs/render/charts/kit/kinds/table.py
  - .kiro/specs/chart-kit/design.md
  - .kiro/specs/dashboards/design.md
blocked_by:
  - dashboards
---

## What
`chart_body` (`src/fitdocs/dashboards/region.py:76`) builds a region body from
the kit's rendered text. For markdown output it splits the text on `"\n"`
(`_kit_lines`, line 64) and refuses only a line that starts with the
`<!-- fitdocs:` prefix (`_refuse_markers`, line 68). Three things pass through:
a line that opens a code fence with no closer, a trailing newline, and a CR.
The page scanner treats a fence opened inside a region body as running to the
end of the page (ruling R1 of task 3.1), so the region then scans back as
unclosed. The trailing newline and the CR produce a doubled blank line and a
`\r` at the end of a body line.

## Why it matters
`stat` and `table` cannot produce any of these, so nothing is wrong today.
The contract is implicit, though: the chart kit's design does not promise it
and the region does not enforce it, so a new markdown kind could corrupt a
user's page (an unclosed region is refused on every later run, Req 16) without
any test noticing.

## Evidence
Probe `/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/e6978888-5f66-4ba4-8392-5c49f509f8bf/scratchpad/4.1-reviewer/probe.py`
(wiped on reboot; the output is quoted). Re-run against 0a98d5c:

```
F6 [('a', None)] ()          # kit text "```\ncode" written below a directive, then re-scanned:
                             # region 'a' has end_line None (unclosed) and scan_page reports no problem
F7 ('**T:** 1', '', '')      # kit text "**T:** 1\n" -> two trailing blank lines
F7b ('a\r', 'b', '')         # kit text "a\r\nb" -> the CR stays on line 1
```

The only markdown-output kinds in the kit today are `stat`
(`kinds/stat.py:166`) and `table` (`kinds/table.py:131`).

## How to pick it up
1. Read `chart_body`, `_kit_lines` and `_refuse_markers` in `region.py` and the fence handling in `scan_page` (`grammar.py`, search `intruder`).
2. Decide the contract: the cheapest is for `chart_body` to raise `ValueError` for a kit text that contains `\r`, ends with `\n`, or leaves a fence open, which the engine's chart-failure handling already covers (see the IN-SPEC 5.2 note: a `ValueError` from `chart_body` is a chart failure).
3. Add a test per violation (one fence-opening line, one trailing newline, one CR) and state the contract in the chart-kit design's markdown-output section. Done means a synthetic kit with each violation yields a chart failure and no region change.
