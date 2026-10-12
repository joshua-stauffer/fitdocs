---
id: 2026-10-13-region-splice-regex-duplicated-for-morning
title: "The anchored region-splice regex in load/docedit.py is copied for the morning region; a generic docmerge.replace_region could serve both"
status: open
importance: low
importance_why: Both copies are short and tested, and a splice bug is bounded by the byte-preservation tests each carries; the cost is that a fix to one (a marker-grammar change, a CRLF rule) has to be found and repeated in the other.
effort: S
kind: chore
area: workout-wellness, src/fitdocs/load/docedit.py, src/fitdocs/docmerge.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (workout-wellness spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: once workout-wellness has landed, add replace_region(markdown, region_id, content) to src/fitdocs/docmerge.py beside extract_regions and region_block, switch fitdocs.load.docedit.replace_load_region and fitdocs.morning.docedit.replace_morning to it keeping their own error types, and keep the round-trip and byte-locality tests of both [queue: .kiro/queue/2026-10-13-region-splice-regex-duplicated-for-morning.md]"
context:
  - src/fitdocs/load/docedit.py
  - src/fitdocs/docmerge.py
  - .kiro/specs/workout-wellness/design.md
  - .kiro/specs/workout-wellness/tasks.md
  - tests/load/test_docedit.py
blocked_by: [workout-wellness]
---

## What

`fitdocs.load.docedit.replace_load_region` replaces only the inner content of
the `load` region, byte-preserving everything else, by an anchored,
non-greedy, column-zero regex over the begin and end marker lines.
workout-wellness plans `fitdocs.morning.docedit.replace_morning` with the same
pattern for the `morning` region: its allowed dependencies exclude the load
package, and the spec lists "`docmerge`'s grammar and merge, which stay
generic and unchanged" as out of its boundary (`design.md:77`). The pattern,
the function replacement that keeps backslashes literal, and the "region must
exist" check are the same logic twice, with only the region id and the error
type different. `docmerge` already owns the marker grammar (`begin_marker`,
`end_marker`, `region_block`, `extract_regions`) and is the natural home for a
`replace_region`.

## Why it matters

A change to the marker grammar or the splice rule (a different line-ending
rule, markers that may be indented) must be made in `docmerge.py`, in
`load/docedit.py` and in the morning copy, and nothing pins that the copies
agree. Two reserved regions are already enough to drift; a third region would
add a third copy.

## Evidence

Read at `86cdf14`.

- `src/fitdocs/load/docedit.py:208-243` -- `replace_load_region`: validates
  through `extract_regions`, then
  `re.compile(rf"^{re.escape(begin)}\n.*?\n{re.escape(end)}$", re.MULTILINE | re.DOTALL)`
  at `:233-236` and `pattern.subn(lambda _match: replacement, markdown, count=1)`
  at `:240`.
- `.kiro/specs/workout-wellness/design.md:572-592` -- `replace_morning` uses
  "the same anchored, non-greedy pattern `load/docedit.py:208-243` uses (a
  function replacement, so backslashes in `content` are literal)"; `:194-195`
  names the load pass as the precedent; `:77` leaves `docmerge` unchanged;
  `:97-98` already lets `morning.docedit` import `fitdocs.docmerge`.
- `.kiro/specs/workout-wellness/tasks.md:414-427` -- task 2.4 writes the
  morning copy with its own tests (`tests/morning/test_docedit.py`).
- `src/fitdocs/docmerge.py:79-99` -- the marker helpers and `extract_regions`
  where a generic splice would sit; `grep -n "begin_marker(" src/fitdocs`
  shows no other splice built from them.
- A third consumer that is not a copy: dashboards splices by line, between its
  own markers (`.kiro/specs/dashboards/design.md:792-846`, `apply_edits`), so
  it is out of scope here.

## How to pick it up

1. Wait for workout-wellness task 2.4 to land, then diff the two functions;
   they should differ only in `LOAD_REGION`/`MORNING_REGION` and the error
   class.
2. Add `replace_region(markdown, region_id, content)` to `docmerge.py` raising a
   small `RegionMissing` (or `ValueError`) that each caller wraps in its own
   error type; keep `extract_regions`' validation first.
3. Switch both callers and run `tests/load/test_docedit.py` and
   `tests/morning/test_docedit.py` unchanged. Add the shared function's own
   round-trip test (the invariant both docstrings state) in `tests/test_docmerge.py`.
   Mutation: change the anchor in the shared function and both suites red.
   Done when `grep -rn "re.DOTALL" src/fitdocs` no longer hits a splice outside
   `docmerge.py`.

## Open questions

- None for the design: `morning.docedit` may already import `docmerge`
  (`design.md:97-98`). Adding a function to `docmerge` touches a module whose
  grammar and merge workout-wellness declares out of its boundary, so it
  needs a line in that spec's amendments or a task of its own.
