---
id: 2026-07-30-fourth-choice-search-basis-not-web-remediated
title: The fourth FitdocsChoice's search basis rests on re-reading three held texts, not on the live web search its siblings were remediated with
status: open
importance: medium
importance_why: Nothing dishonest ships — both fields are scoped honestly and are pinned by whole-value equality — but two of the four choice records were deliberately re-done with a real search tool and the newest one was not, so Req 15.9's evidence standard now differs per record with no ruling saying that is intended.
effort: S
kind: inconsistency
area: fit-ingest, src/fitdocs/metrics/sources.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, round-5 review follow-up)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-fourth-choice-search-basis-not-web-remediated.md] Decide whether POWER_ABSENT_SAMPLE_CHOICE's search basis needs a live literature search like its two remediated siblings"
context:
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_sources.py
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

> **LIKELY MOOT as of 2026-07-30 — awaiting the maintainer's close.** This item
> is entirely about `POWER_ABSENT_SAMPLE_CHOICE`, the fourth `FitdocsChoice`.
> That record was **deleted** at `dd10f9f`: an absent power sample no longer
> resamples as a fabricated `0.0` and a leading dropout truncates the grid, so
> no fill value exists anywhere and the choice had nothing left to justify.
> `src/fitdocs/metrics/sources.py` now holds three `FitdocsChoice` records, all
> three of which were remediated with a live web search — so the per-record
> inconsistency in Req 15.9's evidence standard that this item reports no
> longer exists.
>
> Verified from the live module on 2026-07-30: `FitdocsChoice` count is 3, and
> `hasattr(sources, "POWER_ABSENT_SAMPLE_CHOICE")` is `False`.
>
> Not closed here — closing is the maintainer's call
> (`.claude/skills/kiro-queue/SKILL.md`). The one thing worth deciding before
> closing: this item also carried the *general* question of whether every
> `FitdocsChoice` owes a live search rather than a re-read of held texts. That
> question survives its example. If it matters, re-file it as a standing rule
> rather than losing it with this record.

## What

Req 15.9 asks each `FitdocsChoice` to record what was searched and what was
found. The four records in `src/fitdocs/metrics/sources.py` now meet that at
two different standards:

- `MOVING_THRESHOLD_CHOICE` and `ALTITUDE_WINDOW_CHOICE` were **remediated
  with a live web-search tool**, and their verbatim queries are pinned in
  `tests/metrics/test_sources.py`.
- `NP_MIN_SPAN_CHOICE` predates that tool and says so plainly — its basis
  discloses that no live literature-search tool was available, and a test
  enforces that disclosure.
- `POWER_ABSENT_SAMPLE_CHOICE`, added by task 12.2 **after** the tool existed,
  rests on re-reading the three primary texts already in hand and carries no
  such disclosure.

## Why it matters

This is a judgment call for the maintainer, not a defect, and the reviewer was
explicit that **nothing dishonest ships**: both fields are scoped honestly
("no published work *this layer cites*", "none of *these three*"), and both are
pinned by whole-value equality, which is strictly stronger than the substring
disclosure checks the other records carry.

What makes it worth a ruling is that the newest record was written when the
better evidence standard was already available and did not use it. Left
unaddressed, Req 15.9 means "I re-read what I had" for some records and "I ran
a live search and here are the queries" for others, with nothing recording
which is intended. The next `FitdocsChoice` author has two precedents and no
rule.

There is a substantive question underneath it. The claim `POWER_ABSENT_SAMPLE_CHOICE`
rests on is a **negative**: that no published work prescribes how to fill an
unrecorded power sample. A negative claim is exactly the kind that a search of
three already-held texts supports weakly — those three were selected for other
reasons, and none of them is about gap-filling. A live search either confirms
the negative much more strongly or finds the prescription that changes the
record entirely.

## Evidence

At `ab1038d`:

- `src/fitdocs/metrics/sources.py` — `POWER_ABSENT_SAMPLE_CHOICE`'s
  `search_basis`, which cites re-reading `COGGAN_2003` (pp. 8-11),
  `BANISTER_1991` and `MORTON_1990` and finding no step addressing a missing
  sample.
- `tests/metrics/test_sources.py` — `test_moving_threshold_and_altitude_window_do_not_claim_no_search_tool`
  and the pinned verbatim queries for the two remediated records;
  `test_np_min_span_choice_search_basis_states_no_search_tool_was_available`
  for the pre-tool record.
- Round-5 reviewer, follow-up 4, importance medium: *"not a false claim … it is
  a maintainer judgment call about whether the unremediated pattern is
  acceptable for a new record now that the tool exists."*

Related, and worth reading together: an earlier reviewer noted that
`COGGAN_2003`'s pinned note transcribes steps 1-4 and 8 only, so the negative
claim over *all eight* steps rests on the author's unrecorded reading rather
than on text quoted in-repo.

## How to pick it up

1. Read all four `search_basis` values in `src/fitdocs/metrics/sources.py`
   side by side — the difference in standard is obvious once they are adjacent.
2. Decide between: (a) run the live search for the fourth record and pin its
   queries like the two remediated ones; (b) add the pre-tool-style disclosure
   saying the basis is a re-reading rather than a search; (c) record a ruling
   that re-reading the cited corpus is sufficient when the claim is scoped to
   that corpus.
3. If (a), note the claim under test is a negative about gap-filling in power
   data — search terms should target resampling and missing-sample handling,
   not the metric formulas already held.
4. Whichever is chosen, the whole-value backstops in
   `tests/metrics/test_sources.py` pin the exact text, so the expected literals
   move in the same change or the suite reds.

Done looks like: all four records meet one stated standard, or a recorded
ruling explains why they differ.
