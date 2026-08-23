---
id: 2026-07-30-metric-module-docstring-prose-is-unpinned
title: Metric-module docstring prose is pinned by nothing, and that is how two false claims shipped in one task
status: open
importance: medium
importance_why: Citation-record prose is guarded by whole-value backstops that red immediately; the same factual claims in a metric module's own docstring are guarded by nothing, and task 13.1 shipped two false ones there while its record prose was caught at once.
effort: M
kind: gap
area: fit-ingest, tests/metrics/test_constant_guard.py, src/fitdocs/metrics/power.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 13.1 and its follow-on correction, reviewer follow-up)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-metric-module-docstring-prose-is-unpinned.md] Decide how metric-module docstring claims get pinned, given records get whole-value backstops and modules get nothing"
context:
  - src/fitdocs/metrics/power.py
  - tests/metrics/test_constant_guard.py
  - tests/metrics/test_sources.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

The Amendment 1 citation layer guards prose asymmetrically:

- **Citation and choice records** (`src/fitdocs/metrics/sources.py`) have
  whole-value equality backstops in `tests/metrics/test_sources.py`. Any edit
  to a `justification`, `search_basis`, `note` or `locator` reds immediately.
- **Metric-module docstrings** (`power.py`, `aggregates.py`, `stress.py`) have
  nothing. `tests/metrics/test_constant_guard.py` scans numeric **literals**,
  not prose.

Those docstrings carry exactly the same kind of factual claim: what the
algorithm does, which index a series starts at, what a cited text says.

## Why it matters

This is not hypothetical — it is the observed mechanism by which task 13.1
shipped two false statements past review, in a spec whose entire purpose is
that claims carry sources.

Both were in `power.py`'s module docstring, and both were caught only because
a reviewer was told to read every sentence and verify by computation:

1. An off-by-one asserting points with "fewer than `_NP_ROLLING_WINDOW_S`
   **seconds** behind" are dropped. Its mismatch set against the real code was
   exactly `{29}` — the same samples-vs-seconds conflation that had just
   invalidated a citation record three lines below.
2. A claim that the module's reading of Coggan's step 1 was "**the mainstream
   interpretation**" — an assertion about other implementations, which this
   layer has no means to check and whose own `search_basis` says no
   literature-search tool was available.

Meanwhile the record-side prose in the *same* change was caught instantly:
mutating `"29.0 s, not 30.0 s"` to `"28.0 s"` reds its backstop as a sole
failure. The guarded half worked; the unguarded half shipped falsehoods.

`tasks.md:266` already anticipated this in a narrower form — *"the 12.2 guard
scans literals, not prose, so nothing else catches them"* — but treated it as
a one-task instruction to rewrite two sites rather than as a standing gap.

## Evidence

At `7a0d35e`, mutation run by the reviewer through `uv run pytest`:

```
Remove "(counting itself)" from power.py's rolling-mean docstring
  -> 2241 passed  (GREEN)
```

That parenthetical is load-bearing: without it the sentence's predicate
disagrees with the code at exactly index 29. Deleting it silently reintroduces
an off-by-one claim and no test notices.

Contrast, same session, same change:

```
sources.py justification "29.0 s, not 30.0 s" -> "28.0 s..."
  -> 1 failed, 2240 passed  (sole failure: the whole-value backstop)
```

## How to pick it up

1. Read `tests/metrics/test_sources.py`'s backstop pattern (the
   `BACKSTOP_*` constants and their equality tests) — that is the mechanism
   that works, and the question is how much of it to extend.
2. Decide the scope deliberately. Whole-value pinning every metric-module
   docstring is probably too much: docstrings are edited far more often than
   citation records, and a backstop that reds on every wording tweak trains
   people to update the expected text without reading it, which is worse than
   no guard. Candidate middle grounds:
   - Pin only the docstring paragraphs that state a *checkable arithmetic
     claim* (indices, window widths, sample counts), leaving explanatory prose
     free.
   - Assert the claims mechanically instead of textually — e.g. a test that
     computes the first kept index and asserts the docstring's stated index
     matches it, so the pin tracks the code rather than the wording.
   - Extend the `-E` prose sweep in the review protocol rather than the test
     suite, accepting that this class rests on review.
3. Whatever is chosen, note what this branch already learned: **a whole-value
   backstop pins text, not truth** — it guarded a false Departure record
   character-for-character earlier in this spec. Any mechanism chosen here
   should make a *wrong* claim fail, not merely a *changed* one.

Done looks like: a false arithmetic claim in a metric-module docstring reds
something, or a recorded ruling that this class is review-only and why.
