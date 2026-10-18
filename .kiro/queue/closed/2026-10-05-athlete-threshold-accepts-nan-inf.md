---
id: 2026-10-05-athlete-threshold-accepts-nan-inf
title: athlete.toml numeric thresholds accept nan/inf, producing NaN IF/TSS instead of absent values
status: done
importance: medium
importance_why: Violates the hard rule that absent data is None -- a TOML `ftp_watts = nan` renders NaN load metrics into every affected document.
effort: S
kind: bug
area: fit-ingest, src/fitdocs/athlete.py, src/fitdocs/metrics/power.py, src/fitdocs/metrics/stress.py
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-index spec writer)
pinned_at: 19fc92e
resume_command: "do: under the change ritual, make athlete.py _optional_number (and any sibling numeric readers) reject non-finite floats with AthleteFileError naming the key, with a test per key that a TOML `nan`/`inf` is refused; check whether profile.py's benchmark readers share the gap"
context:
  - src/fitdocs/athlete.py
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/stress.py
  - src/fitdocs/load/profile.py
blocked_by: []
---

## What
`_optional_number` in `src/fitdocs/athlete.py:131-139` rejects bools and
non-numbers but accepts any float, and TOML has `nan` and `inf` literals. A
threshold such as `ftp_watts = nan` therefore reaches the metric code, which
computes IF and TSS from it (`metrics/power.py:255-257`,
`metrics/stress.py:198-203`) and yields NaN.

## Why it matters
CLAUDE.md's hard rule: absent data is `None`, never fabricated. A NaN
threshold is neither a value nor absent; documents may render `nan` load
values, and the Phase 10 index has to special-case non-finite values to NULL.

## Evidence
- `src/fitdocs/athlete.py:131-139` at 19fc92e: `if isinstance(value, bool) or not isinstance(value, (int, float)): raise ...; return float(value)` -- no `math.isfinite` check.

## How to pick it up
1. Read `athlete.py`'s numeric readers (`_optional_number`, `_optional_int`) and `load/profile.py`'s benchmark value readers.
2. Add a refusal for non-finite values with a message naming the key and path; test `nan`, `inf`, `-inf` per key.
3. Decide (and record) whether this is a fit-ingest amendment or a plain bug fix.

## Resolution (2026-10-18)

Fixed on main at 5e37ad3 (chore/q-athlete-nonfinite; two Opus review rounds, final APPROVED; full
suite 26801 passed; branch CI green). Non-finite numbers are refused with an error naming the key in:
athlete.py `_optional_number` and `_optional_zone` (AthleteFileError), `AthleteProfile.get_number`
(ProfileError), the profile write-side `_validate` (NaN had slipped past range checks and been written
to athlete.toml), `[load.flags]` cadence_lock_max_delta_bpm / divergence_max_intensity_delta /
aerobic_drift_max_pct, `[inbox] settle_seconds` and `[connectors.<folder>] settle_seconds`. Load prompts
(`ask_float`) re-ask on nan/inf. No version constant changed: a previously-valid-but-poisonous file
now fails loudly (exit 2) instead of producing NaN IF/TSS.

Not done (maintainer decision): `fitdocs check` never validates athlete inputs (audit.py ~620 reads
only `load_profile().benchmarks`), so an `ftp_watts = nan` that load/regen refuse is "No findings".
Queued: .kiro/queue/2026-10-18-check-does-not-validate-athlete-inputs.md.
