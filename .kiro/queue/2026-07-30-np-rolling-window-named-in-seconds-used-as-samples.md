---
id: 2026-07-30-np-rolling-window-named-in-seconds-used-as-samples
title: _NP_ROLLING_WINDOW_S is named and documented in seconds but consumed as a sample count
status: open
importance: medium
importance_why: Correct today only because the resample is exactly 1 Hz; the _S suffix and three docstrings become wrong the moment that rate changes, and this exact conflation already produced two false statements and one invalidated citation record in a single task.
effort: S
kind: inconsistency
area: fit-ingest, src/fitdocs/metrics/power.py, src/fitdocs/metrics/sources.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 13.1 review, restated by the follow-on correction review)
pinned_at: 7a0d35e
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-np-rolling-window-named-in-seconds-used-as-samples.md] Resolve the seconds-vs-samples naming of the NP rolling-window constant"
context:
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_sources.py
blocked_by: []
---

## What

`_NP_ROLLING_WINDOW_S` carries an `_S` (seconds) suffix and is described in
seconds at three sites, but is passed to `_trailing_rolling_mean` as a
**sample count**:

- `src/fitdocs/metrics/power.py` — "Width in seconds of the trailing
  rolling-mean window"
- `src/fitdocs/metrics/power.py` — "the `_NP_ROLLING_WINDOW_S`-second trailing
  rolling mean"
- `src/fitdocs/metrics/sources.py` — "rolling-mean window width in seconds"
- against `power.py`'s call site: `_trailing_rolling_mean(resampled, _NP_ROLLING_WINDOW_S)`

At 1 Hz the two coincide numerically, so nothing is wrong today. A 30-sample
window spans 29 seconds of elapsed offset, not 30.

## Why it matters

The reviewer ruled — correctly — that these three sites are **labels under a
convention `power.py` now explicitly states** ("this module treats '30 s'/'30
second' as naming the window's *width* (30 samples)"), not false arithmetic
claims. So this is latent fragility, not a present falsehood, and it was
deliberately scoped out of the correction that fixed the real errors.

It is worth doing anyway because this precise conflation has already cost
real defects in a single task:

- It invalidated `NP_MIN_SPAN_CHOICE`'s justification, which reasoned in
  seconds about a window measured in samples and concluded that no complete
  window exists below 30 s. One exists at 29.0 s.
- It produced a false docstring predicate in `power.py` ("fewer than
  `_NP_ROLLING_WINDOW_S` **seconds** behind it"), whose mismatch set against
  the code was exactly `{29}`.

Both were fixed. The naming that invites the mistake was not, and the `_S`
suffix is an active invitation: a reader who trusts it will reason in seconds
and be wrong by one sample every time.

The fragility becomes a real bug the moment the 1 Hz resample changes.
`power.py`'s own docstring already flags the resample rate as "fitdocs' own
choice, not a value read from Coggan's text" — i.e. a value that can move.

## Evidence

At `7a0d35e`:

```
$ uv run python -c "
from fitdocs.metrics.power import _trailing_rolling_mean
vals=list(range(40))
out=_trailing_rolling_mean(vals,30)
print(out[0]==sum(vals[0:30])/30, len(vals)-len(out))"
True 29
```

The window covers 30 samples (indices 0..29), spanning 29 seconds of elapsed
offset, and the first output lands at index 29.

## How to pick it up

1. Decide between two shapes:
   - **Rename to units that match use** — e.g. `_NP_ROLLING_WINDOW_SAMPLES`,
     with the three docstrings restated in samples and the seconds figure
     mentioned as the 1 Hz equivalence. Honest, and removes the invitation.
   - **Keep seconds and convert at the call site** — `int(window_s * rate)` —
     which makes the constant's name true and localises the assumption. This is
     the better shape if the resample rate is ever expected to move.
2. Note the constraint: the *value* is a `CitedConstant` sourced to
   `COGGAN_2003`, whose text states the window in **seconds** ("a 30 second
   rolling average"). Whatever is chosen must keep the record faithful to the
   source's own units — which is an argument for keeping the record in seconds
   and converting, rather than renaming the record.
3. `sources.py`'s record description is pinned by a whole-value backstop in
   `tests/metrics/test_sources.py`; any wording change reds it and the
   expected literal moves in the same change.
4. `power.py` is one of the three literal-scanned modules — if the change adds
   any numeric literal (a conversion factor, a rate), it must be read from a
   record or exemption-listed, and the exemption entries are keyed
   `(line, col_offset, value)` so an edit shifting lines needs a fresh AST scan.

Done looks like: the constant's name and its docstrings agree with how it is
consumed, and changing the resample rate cannot silently falsify either.
