---
id: 2026-08-27-prompt-date-strands-historical-documents
title: Benchmarks answered at the prompt are dated today, so every historical activity is unscorable
status: done
importance: critical
importance_why: A first-time athlete scores nothing except activities dated today or later, and is never re-asked, so it is unrecoverable without hand-editing athlete.toml. fitdocs' primary use case is an archive of past .fit files.
effort: M
kind: cross-spec-conflict
area: training-load, athlete-benchmarks, threshold-load, src/fitdocs/load/engine.py, src/fitdocs/load/prompts.py
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
maintainer_ruling: "2026-08-29 -- accepted as a known limitation; threshold-load merges as-is. The design is to be EXTENDED to handle past dates as follow-up work, rather than the merge being blocked on it."

pinned_at: 3e14ab9
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-08-27-prompt-date-strands-historical-documents.md] Decide how a prompt-answered benchmark is dated, then implement"
context:
  - src/fitdocs/load/engine.py
  - src/fitdocs/load/prompts.py
  - src/fitdocs/benchmarks.py
  - src/fitdocs/load/threshold/anchors.py
  - .kiro/specs/threshold-load/requirements.md
blocked_by: []
---

## What

Three individually-correct rules compose into a feature that does nothing for
historical documents.

- `src/fitdocs/load/engine.py:504` passes `on=today` to `collect_missing_fields`.
- `src/fitdocs/load/prompts.py:122-124` persists the answer at `measured_on=on`,
  i.e. today.
- `threshold-load` Req 4.1 resolves anchors at the **activity's own local
  calendar date** (`calculator.py:409`), which is correct: the document is
  named from that date and scoring must agree with the file name.
- `BenchmarkSet.applicable` (`src/fitdocs/benchmarks.py:148`) never returns an
  entry dated after the activity, which is also correct.

So an athlete who answers the prompts today has seven benchmarks on file and
**every activity older than today resolves none of them**.

It is unrecoverable in normal use: `collect_missing_fields`' presence check is
deliberately undated (`prompts.py:110-116`, Req 8.3/8.4 "ask once"), so the
athlete is never re-asked; and the absent anchor routes to `NotComputed`
rather than `MissingInputs`, so the engine is never told anything is missing
either.

## Why it matters

fitdocs exists to turn an archive of `.fit` files into documents. A user with
years of history who runs `fitdocs load` for the first time gets every one of
those documents marked *not computed*, with reasons that read "no
functional-threshold-power benchmark was supplied" while seven benchmarks sit
in `athlete.toml`. Only activities from today forward will ever score, and
nothing prompts them to fix it.

## Evidence

Measured on `3e14ab9` with the shipped store, persisting exactly what
`collect_missing_fields` persists:

```
benchmarks persisted        : 7
has_benchmark(run ftp)      : True
applicable AT ACTIVITY DATE : None          # activity 2026-06-01
applicable AT TODAY         : Benchmark(... measured_on=2026-08-27)
```

End-to-end, an activity dated 2026-06-01 with all five HR/power/pace
benchmarks answered today yields:

```
NotComputed: no channel produced a load: Power: no functional-threshold-power
benchmark was supplied, or its value is not positive; Heart rate: missing: ...;
Pace: no threshold-pace benchmark was supplied, or its value is not positive
```

No test covers prompt -> score for a historical activity:
`tests/load/threshold/test_feature_e2e.py` writes benchmarks via
`with_benchmark` at a chosen date, bypassing the prompt path entirely.

## Maintainer ruling (2026-08-29)

**Accepted as a known limitation. `threshold-load` merged as-is at the
maintainer's direction**, rather than blocking the branch on a cross-spec
product decision. The design is to be **extended to handle past dates** as
follow-up work.

This does not narrow the item: the defect, its evidence and its four candidate
fixes below all stand, and the work is still owned by `training-load` /
`athlete-benchmarks`. What changed is only that it is planned follow-up rather
than a merge blocker. Anyone picking this up should treat option 1 or 2 as the
likely shape, since "extend the design to handle past dates" is what was
asked for.

## How to pick it up

**This needs a product decision before any code.** The four candidate fixes sit
in three different specs' boundaries:

1. **Prompt for the measurement date** (`training-load` — `prompts.py`/`engine.py`).
   Honest, costs the athlete a question per benchmark.
2. **Date prompt answers to the earliest activity in the pass, or to
   `date.min`** (`athlete-benchmarks` — semantics of an undated answer).
   Contradicts nothing in the store, but redefines what `measured_on` means for
   an unmeasured answer.
3. **Let a calculator opt into "latest known" resolution** (contract-level,
   `training-load`). Widest blast radius.
4. **Accept and document**, with a CLI hint telling the athlete to set
   `measured_on` by hand. Cheapest, worst UX.

First three moves: read `prompts.py:100-130` and `engine.py:495-510`; read
`benchmarks.py:126-152` for the never-future rule and its rationale; then read
`threshold-load` Req 4.1 and `athlete-benchmarks`' own requirements on
`measured_on`. Done looks like: a chosen semantic, recorded as an amendment in
the owning spec, and an end-to-end test that drives prompt -> score for an
activity older than the prompt date.

## Resolution

**Closed 2026-09-10** — resolved by training-load Amendment 4, merged to `main`
at `664960a` (tasks 7.1–7.4 all `[x]`).

Semantic chosen: the pass date stays the entry's `measured_on`, and the athlete
may declare a separate, optional, trailing `applies_from` (never later than
`measured_on`) that reaches the measurement back to earlier activities. The
prompt flow asks for it — `collect_missing_fields(*, on, activity_date)` puts
the retroactive question through `session.confirm(default=True)` only for a
benchmark field on an activity dated strictly before the pass date — so an
athlete who accepts the default scores the activity that prompted the question.

Recorded as amendments in all three owning specs:
- `training-load` requirements Amendment 4 (3.7–3.9), design §Amendment 4
- `athlete-benchmarks` requirements Amendment 1 (1.12, 2.11, 3.10, 3.11, 6.10)
- `threshold-load` — anchor resolution consumes the two-tier `applicable`

Evidence:
- `src/fitdocs/benchmarks.py:101` `Benchmark.applies_from`; `:160-193` two-tier
  `BenchmarkSet.applicable` (tier 1 latest `measured_on <= on`, else tier 2
  earliest `measured_on` among entries whose `applies_from <= on`)
- `src/fitdocs/load/prompts.py:147-183` the retroactive question and its wording
- `src/fitdocs/load/engine.py:408-511` threads the document's own
  `activity_date` through to the prompt flow
- `tests/load/test_prompt_date_e2e.py` — feature-level prompt → score for an
  activity older than the prompt date: **3 passed** (re-run at close, 2026-09-10)

Follow-ups that fell out of this work were queued separately, not folded in:
`2026-09-10-performance-benchmarks-design-predates-applies-from`,
`2026-09-10-activity-qa-flags-staleness-guard-neutralises-retroactive-anchors`,
and the load-channels anchor-date rendering item.
