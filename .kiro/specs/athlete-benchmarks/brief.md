# Brief: athlete-benchmarks

## Problem

Every threshold-anchored load number is only as good as the threshold behind
it. The "1 hour at threshold = 100" scale that makes load comparable across
disciplines requires a *per-discipline*, *current* benchmark: a running FTP, a
cycling FTP, an LTHR, a threshold pace. fitdocs has nowhere to put them.

Worse, thresholds go stale silently. A running FTP measured eight months ago
still produces a confident-looking TSS today — it is just wrong, and nothing in
the document says so. The research pass kept the staleness flag explicitly:
auto-FTP estimation exists but is not a clean drop-in, and the claim that
real-time FTP determination inherently avoids staleness was refuted 0-3.

There is also a measurement-system trap in Josh's own data. His runs cross a
hardware boundary — Apple Watch native running power through 2024, Stryd from
2026 — and these are different measurement systems. A running FTP measured on
Stryd applied retroactively to Apple Watch runs mis-scales years of history.

## Current State

Two stores exist and neither can hold this:

- `src/fitdocs/athlete.py` reads an optional `<data_root>/athlete.toml` into
  `AthleteInputs` — flat, **read-only by construction** (fit-ingest Req 8.3:
  never creates the file, never prompts, writes nothing on any path), with no
  discipline scoping and no dates. It carries `ftp_watts`, `resting_hr_bpm`,
  `max_hr_bpm`, and three `ZoneSpec`s. It ignores unknown keys for forward
  compatibility — deliberately, so this spec can add them.
- `src/fitdocs/load/profile.py` is a *second*, writable store driven by
  `AthleteField` declarations and the prompt flow, with dotted
  methodology-scoped keys (`withdrawn.hpl`). It persists what prompting collects.

So today one file is read-only and undated, the other is writable and
methodology-scoped, and neither knows what discipline a threshold belongs to or
when it was measured.

## Desired Outcome

- A single reconciled benchmark store: per-discipline thresholds, each with the
  date it was measured, readable without fitdocs installed and writable through
  the existing prompt flow.
- Staleness is computed, not guessed: given an activity date and a benchmark's
  `measured_on`, the store reports whether the benchmark was stale *at the time
  of that activity* — so regenerating an old document does not flag it against
  today's calendar.
- Benchmark selection is date-aware: scoring a 2023 activity picks the
  benchmark that was current in 2023, not the newest one on file.
- Absent means absent. A missing benchmark yields `None` and the dependent
  channel reports insufficiency; it never falls back to a default FTP.

## Approach

Extend `athlete.toml` with versioned per-discipline tables carrying
`measured_on` dates, and reconcile the two stores rather than adding a third:
`athlete.py` stays the read path and keeps its loud-on-malformed contract,
`load/profile.py`'s write path is redirected onto the same file. The schema
carries an explicit version key so later shape changes are migrations rather
than silent misreads.

Staleness window (the research suggests ~8–12 weeks) is configuration, not a
constant — it belongs in `fitdocs.toml` `[load]`, read through the shipped
`settings.py`.

## Scope

- **In**: the versioned per-discipline benchmark schema; the read path
  (extending `athlete.py`) and the write path (reconciling `load/profile.py`);
  `measured_on` dates; date-aware benchmark selection; staleness *computation*
  against a configured window; validation and loud failure on malformed input.
- **Out**: rendering the staleness flag into a document (activity-qa-flags
  owns the surfacing); auto-FTP / eFTP estimation of any kind; zone-definition
  changes (`ZoneSpec` stays as fit-ingest shipped it); prompting UX changes
  (the existing `AthleteField` flow is reused as-is).

## Boundary Candidates

- Schema + validation vs. read path vs. write-path reconciliation.
- Date-aware *selection* (which benchmark applies to this activity) as its own
  unit — it is the part with real edge cases (no benchmark yet, benchmark
  measured after the activity, several in the same discipline).
- Staleness computation as a pure function of `(activity_date, measured_on,
  window)` — trivially testable, keep it free of I/O.

## Out of Boundary

- What a stale benchmark *means* for the rendered document or the load value.
  This spec reports the fact; it does not decide the consequence.
- Any load math. No TSS, no HRSS, no channel logic.

## Upstream / Downstream

- **Upstream**: fit-ingest (`AthleteInputs`, `ZoneSpec`, `athlete.py`);
  settings-foundation (`settings.py`, `layout.settings_path`).
- **Downstream**: load-channels (anchors every channel), threshold-load
  (prompting for missing benchmarks), activity-qa-flags (surfaces staleness).

## Existing Spec Touchpoints

- **Extends**: fit-ingest — `athlete.py` gains keys and dates. Its read-only
  invariant (Req 8.3) is deliberate and must survive; the *write* path stays in
  the load layer.
- **Extends**: training-load — `load/profile.py` is its module; the
  reconciliation lands there.
- **Adjacent**: wiki-contract (`OWNED_PATHS` must already admit
  `athlete.toml`); plugin-api (calculators reach benchmarks through
  `ProfileView`, a pinned public type — do not break it).

## Constraints

- **`ProfileView` may be redefined.** Its current shape (`get_number(key) ->
  float | None`, pinned by `tests/test_public_api.py`) predates dates and
  discipline scoping, and forcing those through dotted string keys would be a
  contortion. fitdocs is pre-production with no external plugin authors, so
  prefer redefining the Protocol to express discipline and date directly, and
  update the pin. Do not encode structured data in key strings to preserve a
  signature nothing depends on.
- An absent `athlete.toml` yields no benchmarks, never an error — the shipped
  reader's behavior, and route-maps-style silent breakage if changed.
- Malformed input is loud (`AthleteFileError`), never silently dropped;
  Python's `bool`-is-an-`int` trap is already handled in `athlete.py` and the
  new numeric keys need the same treatment.
- Dates must be timezone-unambiguous and comparable to activity timestamps.
