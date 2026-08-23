---
id: 2026-07-30-min-span-guard-bypassable-by-a-leading-dropout
title: The normalized-power minimum-span guard measures the overall sample span, so a leading dropout lets a sub-minimum stream report an NP
status: open
importance: medium
importance_why: Two activities with byte-identical recorded power data report different things — one `None`, one a value — purely because of how much dead air preceded the first reading. The guard exists to refuse a number that rests on too little data, and a long enough lead-in defeats it.
effort: S
kind: bug
area: fit-ingest, src/fitdocs/metrics/power.py
created: 2026-07-30
surfaced_by: adversarial review of chore/power-absent-sample-fill, round 2 (queue-tier1 batch)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-min-span-guard-bypassable-by-a-leading-dropout.md] Decide whether NP_MIN_SPAN_S governs the overall sample span or the retained power grid, and make the guard measure whichever it is"
context:
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_power.py
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`normalized_power` refuses to report below `_NP_MIN_SPAN_S` (30 s). The guard
measures `time_s[-1] - time_s[0]` — the span of **all** samples, including any
leading stretch where power was never recorded.

Since `dd10f9f`, a leading dropout **truncates** the resample grid to the first
recorded sample. So the guard and the data it is guarding now measure different
things: the check sees the full span, while the value is computed from the
shorter retained grid.

The result is that dead air at the start of an activity can carry a stream past
a guard its real data would not pass.

## Why it matters

Two activities with **identical recorded power** report differently:

| lead-in dropout | recorded samples | overall span | passes guard | grid length | NP |
|---|---|---|---|---|---|
| 0 s | 30 | 29 s | no | — | `None` |
| 60 s | 30 | 89 s | yes | 30 | `300.0` |

Same thirty recorded samples, same 29 s of real data. One reports nothing; the
other reports 300 W, solely because the power meter took a minute to wake up.

The guard's whole purpose is to refuse a number that rests on too little data.
Whether 30 samples is "too little" is a legitimate question — but it should not
be answered differently depending on the length of a gap that contributes no
data at all.

This is a narrow band (the grid reaches 30 points at a truncated span of 29 s),
not a large error. It is filed because the asymmetry is silent and because the
right answer is a one-line change once the intent is settled.

## Evidence

Measured by the reviewer against `chore/power-absent-sample-fill` at `493b789`,
now merged as `dd10f9f`. Constructed streams, 300 W throughout the recorded
portion:

```
lead-in  real  overall span  passes guard  grid len  NP
   60      10       69.0          yes          10    None
   60      20       79.0          yes          20    None
   60      29       88.0          yes          29    None
   60      30       89.0          yes          30    300.0
   25      35       59.0          yes          35    300.0
    0      30       29.0          no            —    None
```

The rows returning `None` do so via the empty-`ra30` backstop, not the span
guard — so nothing is fabricated and nothing crashes. The defect is purely that
the last two rows disagree with the first on identical recorded data.

Guard site: `src/fitdocs/metrics/power.py:233`. Note the pre-existing
docstring/behaviour mismatch tracked alongside this: the docstring describes the
threshold as applying to "the power-stream span" while the code measures the
all-sample span. The truncation did not create that gap, but it made it
reachable.

## How to pick it up

1. Settle the intent first, because it decides the fix: does `NP_MIN_SPAN_S`
   govern **how long the activity is** or **how much power data there is**?
   Read the constant's `FitdocsChoice` record in `src/fitdocs/metrics/sources.py`
   and Req 8.4 — the record's own justification is the best evidence of what it
   was chosen to protect.
2. If it governs the power data (the likely reading, given the constant lives in
   the normalized-power module and the docstring already says "power-stream
   span"), measure the span of the retained grid rather than `time_s`. That also
   makes the docstring true.
3. Either way, add a test with the two-row shape from the table above — same
   recorded samples, different lead-in — asserting they agree. No such fixture
   exists, which is why nothing caught this.
4. Note `NP_MIN_SPAN_S == NP_ROLLING_WINDOW_S == 30` today, so the guard and the
   empty-`ra30` backstop coincide. They are independent records that can
   diverge, and `test_normalized_power_empty_ra30_guard_is_a_reachable_backstop`
   exists precisely because of that — do not collapse them.

## Open questions

- Should the min-span guard survive at all if it measures the retained grid?
  At that point it would fire in exactly the cases the empty-`ra30` backstop
  already covers, and the two would be redundant rather than complementary.
