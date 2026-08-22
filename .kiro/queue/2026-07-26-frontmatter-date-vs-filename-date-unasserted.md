---
id: 2026-07-26-frontmatter-date-vs-filename-date-unasserted
title: Nothing asserts a document's frontmatter `date` equals the date its filename is built from
status: open
importance: medium
importance_why: Req 3.6 states the equivalence as a premise and date-scoped benchmark selection depends on it; a drift between the two independent formatting sites would break selection silently with every unit test green.
effort: S
kind: gap
area: wiki-contract, athlete-benchmarks, src/fitdocs/render/frontmatter.py, src/fitdocs/layout.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 5.1 completion verification)
pinned_at: c5ce672
resume_command: "do: add a test asserting a rendered document's frontmatter date equals the date component of its own filename, so the two independent f-string sites cannot drift [queue: .kiro/queue/2026-07-26-frontmatter-date-vs-filename-date-unasserted.md]"
context:
  - src/fitdocs/render/frontmatter.py
  - src/fitdocs/layout.py
  - src/fitdocs/contract.py
  - tests/render/test_frontmatter.py
blocked_by: []
---

## What
Two independent sites format the same local time into a calendar date:
`src/fitdocs/render/frontmatter.py:109` writes the frontmatter `date` as
`f"{local:%Y-%m-%d}"`, and `src/fitdocs/layout.py:193` builds the document's
filename from `f"{local:%Y-%m-%d}"`. Nothing asserts the two agree.

athlete-benchmarks Req 3.6 does not merely assume they agree — it states the
equivalence as a **premise**, describing the document's date as "the same value
the file name is built from". `LoadContext.activity_date`'s docstring
(`src/fitdocs/load/types.py`) repeats it. But the guarantee is currently
structural coincidence: two string literals that happen to match.

## Why it matters
Date-scoped benchmark selection resolves each document's threshold by the
document's own date (`contract.document_date` → `LoadContext.activity_date` →
`AthleteProfile.benchmark(on=...)`). If the frontmatter date and the filename
date ever disagreed — a time-zone change at one site, a format change, one site
switching to UTC — every document would still render, every unit test would
stay green, and benchmarks would silently resolve against a date that is not
the one the file claims. The failure is invisible precisely because each site
is individually correct and individually tested.

This is the same shape as the sort-site and reader-count problems already
tracked on this project: an invariant held jointly by two sites, with a test at
each site and none across them.

## Evidence
At `c5ce672`:

```
grep -n '%Y-%m-%d' src/fitdocs/render/frontmatter.py src/fitdocs/layout.py
src/fitdocs/render/frontmatter.py:109:        data["date"] = f"{local:%Y-%m-%d}"
src/fitdocs/layout.py:193:  ... f"{local:%Y-%m-%d}" ...
```

The reader half *is* well pinned — a task 5.1 verification pass ran 9
line-anchored mutations against `contract.document_date` with zero survivors,
including both `return date.today()` substitutions — and the absent-date chain
is pinned too (`tests/render/test_frontmatter.py:212` asserts `"date:" not in
out` when an activity has no `start_time`, because line 109 sits inside that
guard). What no test covers is the *cross-site* equality.

## How to pick it up
1. Read `src/fitdocs/layout.py:193` and `src/fitdocs/render/frontmatter.py:109` and confirm both still derive from the same `local` value — that is the property the test will pin.
2. Add one test that renders a document for an activity with a `start_time`, then asserts `contract.document_date(parse_frontmatter(text)) == ` the date parsed out of the document's own filename. Reading it back through `document_date` rather than by regex keeps the test honest about the on-disk form.
3. Done looks like: changing the format string or the source value at *either* site reddens it. Verify by mutating each site independently — a test that only reds when both change together pins nothing (and clear `__pycache__` / use `-p no:cacheprovider`, since a format-string edit can be length-preserving).

Related: [[2026-07-26-date-key-has-no-constant]] — the same `"date"` key is
hardcoded at three sites with no `Final[str]` constant, which is the other half
of how these two sites could drift apart.
