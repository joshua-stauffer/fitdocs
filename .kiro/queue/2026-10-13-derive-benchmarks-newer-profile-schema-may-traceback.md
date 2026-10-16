---
id: 2026-10-13-derive-benchmarks-newer-profile-schema-may-traceback
title: "derive-benchmarks does not report profile schema-version faults as configuration errors"
status: open
importance: medium
importance_why: A newer or invalid profile version bypasses the command's exit-2 diagnostic, including after the HR stage was added.
effort: S
kind: bug
area: src/fitdocs/cli.py, src/fitdocs/load/profile.py, src/fitdocs/athlete.py, hr-derivation
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (hr-derivation spec, controller queue triage)
pinned_at: 8e8a5b2
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

Controller verification on 2026-10-16 confirms that `fitdocs
derive-benchmarks` does not map a newer or invalid profile schema version
to a configuration error. The original static concern below is now
reproduced, and hr-derivation task 3.5 is reopened for its local repair.

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

Original static evidence read at `86cdf14`; those original observations
were not executed at that time:

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

Controller runtime verification at `8e8a5b2` on 2026-10-16 used a temporary
canonical pytest probe under `tests/`, loading the root bytecode-purge
conftest:

```text
UV_CACHE_DIR=/private/tmp/fitdocs-hr-uv-cache UV_OFFLINE=true uv run --no-sync pytest tests/test_hr_schema_queue_probe.py -q --tb=long
2 failed in 0.30s
profile_version = 99: expected exit 2 and file/problem diagnostic; observed exit 1, AthleteFileError, empty stdout/stderr
profile_version = true: expected exit 2 and file/problem diagnostic; observed exit 1, AthleteFileError, empty stdout/stderr
```

Each case wrote only the named `profile_version` to a scratch
`athlete.toml` and invoked the real command through `CliRunner`. Both
failed at the intended configuration-contract assertion, and both kept
profile bytes unchanged. Temporary test removed. Local source and log:
`/private/tmp/hr-schema-queue-probe.py` and
`/private/tmp/hr-schema-queue-probe.log`. Current live source still raises
the base class at `athlete.py:77`/`:84`, called before benchmark parsing
by `AthleteProfile.__post_init__`; the command catches only the subclass.

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
