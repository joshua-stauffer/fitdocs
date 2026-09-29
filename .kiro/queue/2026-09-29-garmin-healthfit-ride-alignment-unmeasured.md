---
id: 2026-09-29-garmin-healthfit-ride-alignment-unmeasured
title: channel-merge's ride alignment assumes per-sample exact power equality between a Garmin original and its HealthFit copy, which nobody has measured
status: open
importance: medium
importance_why: If the premise fails, every ride stretch falls back to exact timestamps and says so on the page, and the ride fixtures pin a behaviour real pairs never show; one local measurement settles it before implementation hardens it.
effort: S
kind: research
area: channel-merge, .kiro/specs/channel-merge/brief.md, .kiro/specs/channel-merge/research.md, .kiro/specs/channel-merge/design.md
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, channel-merge writer)
pinned_at: f500dc1
resume_command: "do: on one maintainer-local Garmin-original plus HealthFit-copy ride pair, measure (a) per-sample equality of power at 1 W and distance at 0.01 m for each lag -2..+2 s in each pause-delimited stretch, (b) the distribution of gaps between the Garmin file's samples (smart recording), and (c) how many stretches reach MIN_MATCHED_SAMPLES = 5 matches with a unique majority lag; record shapes, counts and ratios only (no file name, date or value) in .kiro/specs/channel-merge/research.md, and amend design.md's ALIGNMENT_KEYS / PAUSE_GAP_S / MIN_MATCHED_SAMPLES sources and the ride-pair fixture if the premise fails; best before or during /kiro-impl channel-merge"
context:
  - .kiro/specs/channel-merge/brief.md
  - .kiro/specs/channel-merge/research.md
  - .kiro/specs/channel-merge/design.md
  - .kiro/specs/channel-merge/tasks.md
blocked_by: []
---

## What
channel-merge aligns an extra to the base by exact per-sample equality on
distance (0.01 m) and then power (1 W), searched over lags -2..+2 s per
pause-delimited stretch. The measurements behind that rule are three
Stryd-to-HealthFit **run** pairs. For Garmin-to-HealthFit **ride** pairs the
brief measured only start time, session distance (within 5 m) and power
coverage (about 99% against 100%) -- not whether HealthFit's per-sample power
equals Garmin's. The design's ride-pair fixture builds exactly that equality
in. Two further inputs are unmeasured: Garmin smart recording (2-7 s gaps)
would make every gap a pause under `PAUSE_GAP_S = 1`, shortening ride
stretches, and `MIN_MATCHED_SAMPLES = 5` is labelled a design choice, not a
measurement.

## Why it matters
If HealthFit's ride power is resampled or rounded differently, no ride
stretch establishes a lag and every ride page reports a timestamp fallback.
That may be acceptable (starts agree to the second), but it should be a
known outcome, not a surprise found on the real wiki, and the ride fixtures
and mutation pins should model what real pairs do.

## Evidence
- `.kiro/specs/channel-merge/brief.md:41-42` -- the only ride-pair facts:
  start, distance, power coverage.
- `.kiro/specs/channel-merge/research.md` § "The measured alignment facts"
  (~:117-142; sources are the three run pairs) and § Risks (~:290-293,
  smart recording).
- `.kiro/specs/channel-merge/design.md` alignment constants table (~:726-731:
  `MIN_MATCHED_SAMPLES` "Design choice, not measured"; `ALIGNMENT_KEYS`
  justified by "the channels HealthFit reproduced exactly") and the ride-pair
  fixture (~:1239-1256: "power equal to the Garmin power at the same instant
  on every sample but one").

## How to pick it up
1. Read the three design passages above and the brief's measured facts.
2. Run the measurement in a scratch directory outside the repository and the
   data root, reading the pair from the maintainer's local archive; print
   only counts and ratios.
3. Record the result in channel-merge's research.md; if the premise holds,
   say so beside the constants and close this item; if not, amend the design
   and fixture before task implementation depends on them.

## Open questions
- Whether a whole-ride timestamp fallback is acceptable to the maintainer if
  the measurement shows no ride stretch ever aligns.
