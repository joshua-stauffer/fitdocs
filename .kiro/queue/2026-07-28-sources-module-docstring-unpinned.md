---
id: 2026-07-28-sources-module-docstring-unpinned
title: metrics/sources.py's module docstring restates the records' claims but no test pins it
status: open
importance: low
importance_why: The docstring can drift out of agreement with the records it summarises, and the summary is what a reader meets first.
effort: S
kind: coverage-gap
area: fit-ingest, src/fitdocs/metrics/sources.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 9.2, round-3 reviewer)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest 12.1 [queue: .kiro/queue/2026-07-28-sources-module-docstring-unpinned.md] Pin the sources.py module docstring's restated citation claims the way the records themselves are pinned"
context:
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_sources.py
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

Every `Citation` and `FitdocsChoice` record in `src/fitdocs/metrics/sources.py`
is pinned by a whole-value literal-equality backstop in
`tests/metrics/test_sources.py` — that mechanism is what closed tasks 9.1 and
9.2, and it is sensitive to any character change.

The module docstring at the top of the same file restates several of those same
claims in summary form: that each value's search basis reports a search actually
performed, that the values are inherited from fitdocs.ai, and that fitdocs.ai is
"not a published work under criterion 15.1, so it is not itself treated as a
citable source". None of that summary is pinned by anything. It can be edited to
say the opposite of the records it summarises and the full suite stays green.

## Why it matters

The docstring is the first thing a reader — human or agent — meets when opening
the module, and it is the part most likely to be edited casually while the
records themselves feel load-bearing. A summary that has silently drifted from
its records is worse than no summary: it is an untested assertion sitting on top
of a carefully evidenced one, in the module whose entire purpose is that claims
are evidenced. This is the same "prose is not evidence" hazard that
`.kiro/steering/change-protocol.md` § Fixture Discrimination names, one level up
from the assertions.

Kept at `low` because the docstring governs no computed value and the records
underneath it remain correct and pinned.

## Evidence

At `03221ca`, `grep -n '__doc__\|MODULE_DOC' tests/metrics/test_sources.py`
returns no matches — no test reads `fitdocs.metrics.sources.__doc__`. The only
whole-source check in the module,
`test_no_record_field_names_a_working_document_under_docs_reference`
(`tests/metrics/test_sources.py:319-340`), greps for `docs/reference` and
`fitdocs-ai-reference` paths only; it does not assert docstring content.

The claims in question are at `src/fitdocs/metrics/sources.py:29-35`.

The round-3 reviewer subagent reports mutating lines 33-34 leaves the suite
green. The absence of any docstring assertion was independently confirmed in
this session by the grep above; the mutation itself was not re-run here.

## How to pick it up

1. Open `src/fitdocs/metrics/sources.py:1-50` and list which claims the
   docstring restates that also appear in a record. Those are the ones that can
   drift; general orientation prose is not the target.
2. Decide the cheaper of two fixes. Either (a) add a test asserting the
   docstring contains the specific claim strings, following the whole-value
   pattern already in `tests/metrics/test_sources.py`; or (b) cut the docstring
   down so it *points at* the records rather than restating them, removing the
   drift surface instead of pinning it. (b) is likely better — a summary that
   must be maintained character-for-character alongside six backstops is a
   maintenance cost with little payoff.
3. Whichever is chosen, prove it: mutate the docstring claim to its false form
   and confirm either a test reds (fix a) or that no claim remains to falsify
   (fix b). Run it through `uv run pytest`, never `uv run python -c`.

Done means: no claim in the module docstring can be falsified without either a
test reddening or the claim no longer being there to falsify.
