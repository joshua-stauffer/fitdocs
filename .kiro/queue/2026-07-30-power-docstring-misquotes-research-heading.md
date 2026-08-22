---
id: 2026-07-30-power-docstring-misquotes-research-heading
title: power.py quotes a research.md decision heading that a case-sensitive grep cannot find, and a test copied the same mis-quote
status: open
importance: low
importance_why: The quoted heading differs from the real one only in capitalisation, so the citation still resolves for a human but breaks any exact-match search — and the error has already propagated into a second file.
effort: S
kind: docs
area: fit-ingest, src/fitdocs/metrics/power.py, tests/metrics/test_constant_guard.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, reviewer follow-up round 1)
pinned_at: 2d69443
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-power-docstring-misquotes-research-heading.md] Correct the quoted research.md heading in power.py and the test that copied it"
context:
  - src/fitdocs/metrics/power.py
  - tests/metrics/test_constant_guard.py
  - .kiro/specs/fit-ingest/research.md
blocked_by: []
---

## What

`src/fitdocs/metrics/power.py`'s module docstring cites a decision in
`research.md` by quoting its heading:

> ``research.md`` ("Decision: pin the formulas the reference leaves
> undocumented")

The actual heading is capitalised differently:

> `### Decision: Pin the formulas the reference leaves undocumented`

A case-sensitive search for the quoted string finds nothing. The same
mis-quote was then copied into `tests/metrics/test_constant_guard.py`.

## Why it matters

Low. A human following the citation finds the section regardless, and no
behaviour depends on it.

It matters because quoted text inside quotation marks is a claim to be
verbatim, and this repo has an established practice of pinning such prose with
whole-value backstops precisely so it cannot drift. A quote that is already
wrong when the backstop is written gets pinned character-for-character in its
wrong form — which is the failure mode recorded at length in this branch's own
agent-log warnings ("a whole-value backstop pins text, not truth"). The
propagation into a second file is that mechanism starting to operate.

## Evidence

At `2d69443` plus the uncommitted task 12.2 work:

```
$ grep -n 'Decision: [Pp]in the formulas' .kiro/specs/fit-ingest/research.md
163:### Decision: Pin the formulas the reference leaves undocumented

$ grep -n 'pin the formulas\|Pin the formulas' src/fitdocs/metrics/power.py tests/metrics/test_constant_guard.py
src/fitdocs/metrics/power.py:70:``research.md`` ("Decision: pin the formulas the reference leaves
tests/metrics/test_constant_guard.py:508:        "pinned in research.md's 'Decision: pin the formulas the "
```

Both quote lowercase `pin`; the heading has `Pin`.

## How to pick it up

1. Fix the capitalisation at both sites so the quoted string matches
   `.kiro/specs/fit-ingest/research.md:163` exactly.
2. Check whether either site is covered by a whole-value equality backstop —
   if so, the backstop's expected text needs the same correction in the same
   change, or the suite reds.
3. While there, grep the metrics package for other quoted `research.md` and
   `design.md` headings and verify each resolves under a case-sensitive
   search. This one was found only because a reviewer happened to try the
   grep; there is no guard that would catch a second instance.

Done looks like: every quoted heading in the metrics package is findable by
exact match against its source document.
