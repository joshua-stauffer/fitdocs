---
id: 2026-08-25-divergence-default-measurement-may-now-be-obtainable
title: The archive-scale corpus may now supply the two-channel measurement that activity-qa-flags' provisional divergence default was blocked on
status: open
importance: medium
importance_why: The default's own "what would settle it" is a measurement declared unavailable against a 74-file corpus; a 2478-file archive has since been run, so the blocker may simply be stale.
effort: M
kind: research
area: activity-qa-flags, load-channels
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 5.3 review follow-up; premise re-checked against the 2026-08-23 archive-scale run)
pinned_at: c6c1bb1
resume_command: "do: measure the distribution of abs(selected.intensity - hr.intensity) over the archive-scale corpus and report whether it can settle activity-qa-flags' provisional divergence_max_intensity_delta, which design.md:773 declares unmeasurable against the old 74-file corpus"
context:
  - .kiro/specs/activity-qa-flags/design.md
  - .kiro/specs/load-channels/design.md
  - src/fitdocs/load/channels/heart_rate.py
blocked_by: []
---

## What

`activity-qa-flags` ships `divergence_max_intensity_delta = 0.20` as an
explicitly **provisional** default. The design is unusually careful about it
(`design.md:773`, and the ruling at `:932`): the value was originally chosen
against the *broken* heart-rate intensity scale, was re-examined after the
correction, and was kept — because changing it "would be substituting one
unmeasured number for another".

The design also states exactly what would settle it:

> For each activity on which two channels both computed, record
> `abs(selected.intensity − hr.intensity)`; over a sample large enough to have
> a shape, set the tolerance at a stated percentile of that distribution.

and why that was impossible:

> The measurement is unavailable today: the **74-file corpus** computed **no**
> activity with two channels. Power is present on 2 of 10 rides and on no run;
> the pace channel needs a threshold-speed benchmark the corpus has none of.

**That premise is now stale.** On 2026-08-23 the tool was run at archive scale
for the first time — **2478 real `.fit` files, 2017-2026, six recording
sources** — completing 2478 written / 0 skipped / 0 failed / 0 warnings. That
corpus is 33× the one the "unavailable" finding rests on, spans nine years
rather than a slice, and draws on six recording sources rather than the
handful the 74-file subset covered.

Whether it actually contains two-channel activities is **unknown and untested**
— that is the research this item asks for, not a claim it makes.

## Why it matters

This is the last unmeasured number in the divergence path, and the design says
so in its own words rather than hiding it. If the archive supplies a real
distribution, a provisional default becomes a measured one and the ruling at
`design.md:932` can be closed rather than re-litigated by every session that
reads it.

There is a concrete reason to think the number matters. Measured during task
5.3 on this spec's own fixtures, for a 48/190/165 athlete:

| Anchor | Intensity delta between the two candidate HR definitions |
|---|---|
| 120 bpm | `0.2438070559437967` — **above** `0.20` |
| 140 bpm | `0.18807001780018195` — **below** `0.20` |

So under the *pre-amendment* heart-rate intensity, a 140 bpm session's
divergence would **not** have tripped the flag at its shipped default. Easy
aerobic sessions are precisely the scenario `activity-qa-flags` cites as its
motivation, and they are where the two definitions differ least in absolute
terms. A tolerance set from data rather than from reasoning-by-training-zone
might land somewhere that changes that.

This is not an argument that `0.20` is wrong. It is an argument that the
measurement its own design asks for may now be affordable.

## Evidence

The provisional entry and its blocker: `.kiro/specs/activity-qa-flags/design.md:773`
(the settings table row) and the ruling at `:932-950`, which states the 74-file
corpus "computed **no** activity on which two channels both produced a value".

The archive-scale run: shared agent log, `2026-08-23T13:01:52Z`,
`demo-fresh-wiki RELEASE` — "the first archive-scale run of the tool — 2478 real
.fit files, 2017-2026, six recording sources — came out 2478 written / 0 skipped
/ 0 failed / 0 WARNINGS in 27:58, and `fitdocs check` reports 0 findings over
all 2478."

The two deltas were measured this session through `BANISTER_TRIMP_MODEL` during
the task 5.3 review and are asserted as literals in
`tests/load/channels/test_intensity_semantic.py`.

**Not verified here:** whether the archive contains activities on which two
channels both compute. Power meters and threshold-speed benchmarks are both
required, and the 74-file finding suggests they may be rarer than file count
alone implies. Establishing that is step 1 below, and the honest outcome may be
"still not enough data", which is worth recording either way.

## How to pick it up

1. **First, test the premise cheaply.** Count activities in the archive on which
   two channels both produce a `ChannelLoad`. If the count is still zero or
   near-zero, stop and record that on the design's provisional entry — the
   blocker is then confirmed rather than stale, which is itself worth knowing.
2. If the count has a shape, record the distribution of
   `abs(selected.intensity − hr.intensity)` and report percentiles.
3. Take the result to the ruling at `.kiro/specs/activity-qa-flags/design.md:932`.
   Either set the tolerance at a stated percentile as the design prescribes, or
   record that the archive still cannot settle it.
4. **Personal data never enters this repo** — the data-root contract in
   `tech.md`. Report the distribution and the counts, not the files.

**Done** looks like: the provisional entry either cites a measurement, or cites
a second failed attempt with its corpus size, so the next session does not
re-derive the same blocker from a stale premise.

## Open questions

- Is a percentile over one athlete's nine-year archive a defensible basis for a
  shipped default, or does it just replace an unmeasured number with an
  over-fitted one? The design's own framing ("a sample large enough to have a
  shape") does not say whose sample. Worth settling before the measurement is
  taken, not after.
