---
id: 2026-10-13-derive-benchmarks-newer-profile-schema-may-traceback
title: "fitdocs derive-benchmarks likely ends in a Python traceback, not exit 2, when athlete.toml declares a profile_version newer than this fitdocs supports (verify first)"
status: open
importance: medium
importance_why: An athlete who shares one data root between two fitdocs versions (an install and a checkout, or a roll-back) gets a traceback from a command whose contract is exit 2 with a message; the same call path is about to grow a second stage in hr-derivation.
effort: S
kind: bug
area: src/fitdocs/cli.py, src/fitdocs/load/profile.py, src/fitdocs/athlete.py, hr-derivation
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (hr-derivation spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: first reproduce (fitdocs derive-benchmarks --out <scratch root> over an athlete.toml with profile_version = 99 and no other content; expect exit 2 and a one-line message, suspect a traceback), then add AthleteFileError to the except clause of derive_benchmarks_command in src/fitdocs/cli.py, add the test to tests/test_cli_derive.py, and fix hr-derivation design.md:1078-1079 the same way [queue: .kiro/queue/2026-10-13-derive-benchmarks-newer-profile-schema-may-traceback.md]"
context:
  - src/fitdocs/cli.py
  - src/fitdocs/load/profile.py
  - src/fitdocs/athlete.py
  - src/fitdocs/performance/engine.py
  - tests/test_cli_derive.py
  - tests/test_cli.py
  - .kiro/specs/hr-derivation/design.md
blocked_by: []
---

## What

Static reading says `fitdocs derive-benchmarks` does not map a newer-schema
`athlete.toml` to a configuration error. **Not run: verify first.**

- The command catches only `ProfileError` and `SettingsError`.
- `AthleteProfile.__post_init__` calls `check_schema_version` before it parses
  any benchmark, and that function raises the base class `AthleteFileError`
  directly when `profile_version` is greater than `ATHLETE_SCHEMA_VERSION`.
- `ProfileError` is a subclass of `AthleteFileError`, not the other way round,
  so `except ProfileError` does not catch its parent.
- The pass loads the profile through `load_profile`, which constructs
  `AthleteProfile(data=...)`, so the error would surface from inside
  `derive_benchmarks`, past the handler.

The load pass already handles this: `_run_load_pass`, shared by `sync` and
`load`, lists `AthleteFileError` explicitly.

## Why it matters

The error text is good ("... which is newer than the schema version this
fitdocs supports ...; install a newer fitdocs to read it") but it is only
delivered to an athlete as a traceback tail, and the command's documented
contract is exit 2. The derive command is also where hr-derivation adds a
second stage, and that spec's CLI section repeats the narrow handler.

## Evidence

Read at `86cdf14`; nothing run.

- `src/fitdocs/cli.py:1611-1614` -- `try: report = derive_benchmarks(...)`
  `except (ProfileError, SettingsError) as exc: _config_error(str(exc))`.
- `src/fitdocs/load/profile.py:139-141` -- `__post_init__` calls
  `check_schema_version(self.data, path)`; `:448-466` -- `load_profile` builds
  `AthleteProfile(data=data)`; `:93` -- `class ProfileError(AthleteFileError)`.
- `src/fitdocs/athlete.py:63-91` -- `check_schema_version` raises
  `AthleteFileError` for a non-integer, a value below 1 and a value above
  `ATHLETE_SCHEMA_VERSION` (`:41`, currently 2); `:51` -- the class.
- `src/fitdocs/performance/engine.py:415` -- `load_profile(data_root)` inside
  `derive_benchmarks`.
- `src/fitdocs/cli.py:1778` (`_run_load_pass`) and `:1807-1812` -- its handler:
  `except (ProfileError, AthleteFileError, UnknownCalculatorError, SettingsError)`.
  `tests/test_cli.py:440-452` records why both are listed.
- `tests/test_cli_derive.py:719-735` -- the only profile-fault test for the
  command writes `"not [ valid toml"` (a `ProfileError`); none uses a newer
  `profile_version`.
- `.kiro/specs/hr-derivation/design.md:1078-1079` -- the planned CLI mapping
  is again `ProfileError` and `SettingsError` -> exit 2, while `:920` says
  `ProfileError`/`AthleteFileError` "propagate (the CLI maps them to exit 2)".
- Related, not the same: `.kiro/queue/2026-07-26-profileerror-redundant-in-config-errors.md`
  (the `load` handler's tuple) and
  `.kiro/queue/2026-10-05-index-refresh-fails-whole-on-unloadable-athlete-toml.md`.

## How to pick it up

1. Reproduce: a scratch data root with an `athlete.toml` containing only
   `profile_version = 99` (the error is raised before anything else is read),
   then `fitdocs derive-benchmarks --out <root>`. Done with this step when you
   know whether it is exit 2 or a traceback.
2. If it is a traceback, add `AthleteFileError` to the tuple at
   `src/fitdocs/cli.py:1613` (import is already present at `:188`) and add a
   test next to `test_malformed_athlete_toml_is_a_configuration_fault_exiting_two`
   in `tests/test_cli_derive.py` with a newer `profile_version`. Mutation:
   remove `AthleteFileError` from the tuple and the test reds.
3. Amend hr-derivation `design.md:1078-1079` (and its task 3.5, which owns the
   command wiring) so the second stage's wiring does not reintroduce the
   narrow handler. If step 1 shows exit 2, close this item with the
   reproduction as evidence and leave hr-derivation's wording alone.
