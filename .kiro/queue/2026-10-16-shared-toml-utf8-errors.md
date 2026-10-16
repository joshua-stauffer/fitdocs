---
id: 2026-10-16-shared-toml-utf8-errors
title: Wrap invalid UTF-8 in shared TOML readers as typed file errors
status: open
importance: medium
importance_why: Malformed configuration bypasses documented typed errors and can leave callers with a traceback instead of an actionable diagnostic; no corruption was observed.
effort: S
kind: bug
area: src/fitdocs/settings.py, src/fitdocs/load/profile.py, athlete-benchmarks
created: 2026-10-16
surfaced_by: /kiro-impl hr-derivation task 3.5 review and controller verification
pinned_at: 8e8a5b2
resume_command: "/kiro-discovery [queue: .kiro/queue/2026-10-16-shared-toml-utf8-errors.md] Give malformed UTF-8 settings and athlete files the documented typed errors and file-specific diagnostics while preserving unrelated runtime errors"
context:
  - src/fitdocs/settings.py
  - src/fitdocs/load/profile.py
  - src/fitdocs/athlete.py
  - src/fitdocs/cli.py
  - tests/test_settings.py
  - tests/load/test_profile.py
  - tests/test_athlete.py
  - tests/test_cli_derive.py
  - .kiro/specs/athlete-benchmarks/requirements.md
  - .kiro/specs/athlete-benchmarks/design.md
  - .kiro/specs/hr-derivation/tasks.md
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

The shared settings and profile readers let a real `UnicodeDecodeError`
escape for invalid UTF-8 bytes. Their documented file-error types are
`SettingsError` and `ProfileError` (an `AthleteFileError`). The
`derive-benchmarks` command now handles these bytes locally, but other
callers that catch only the documented types may still expose the raw
decoder failure. Normalize this at the owning reader boundary after
checking its contracts and callers.

## Why it matters

A file that cannot be decoded is configuration the athlete can fix. An
untyped decoder exception bypasses callers' configuration status and
file-specific diagnostic. The local HR command repair does not fix the
shared reader contract.

## Evidence

At `8e8a5b2`, `src/fitdocs/settings.py:65` calls `tomllib.load` and wraps
`TOMLDecodeError` and `OSError`, but not `UnicodeDecodeError`.
`src/fitdocs/load/profile.py:498` wraps only `TOMLDecodeError`.
Their docstrings promise typed errors for invalid TOML.

The controller ran a temporary canonical pytest probe under `tests/`
with the root bytecode-purge conftest:

```text
UV_CACHE_DIR=/private/tmp/fitdocs-hr-uv-cache UV_OFFLINE=true uv run --no-sync pytest tests/test_hr_shared_toml_queue_probe.py -q --tb=long
2 failed in 0.09s
settings: expected SettingsError, observed UnicodeDecodeError
profile: expected ProfileError, observed UnicodeDecodeError
```

The cases write `b'[wellness]\nprecedence = ["garmin-\xff"]\n'` to
`fitdocs.toml` or `b'max_hr_bpm = \xff\n'` to `athlete.toml`, call the real
reader, capture its exception and assert the documented type. Both fail
at that assertion. The probe was removed; no reader source was changed.
Local artifacts are `/private/tmp/hr-shared-toml-queue-probe.py` and
`/private/tmp/hr-shared-toml-queue-probe.log`; the inputs and reader calls
above suffice to reproduce without those artifacts.

Independent task 3.5 review also observed these bytes causing command
exit 1 with empty diagnostics before its local CLI fix. That command now
exits 2 with the correct file and codec reason. The third reader at
`src/fitdocs/athlete.py:114` has the same catch pattern, but its invalid-byte
behavior was inspected statically rather than independently executed here.

All 459 open queue frontmatters and matching bodies were inspected on
2026-10-16; no duplicate was found. The existing newer-profile-schema
command item concerns a different exception class and is tracked separately.
The roadmap has no open item for this reader normalization.

## How to pick it up

1. Read the two reader docstrings and athlete-benchmarks error contracts,
   then reproduce the exact bytes through the readers under canonical
   pytest. Check the third athlete-input reader separately.
2. Implement the smallest reader-owned typed-error mapping, naming the
   actual path and decoder problem. Preserve absent-file behavior,
   unrelated errors, schema validation and write-error handling; a broad
   catch around a whole stage would also hide write failures.
3. Add real-byte reader regressions and caller checks. Run the shared
   settings/profile/athlete tests and affected CLI/audit/index callers,
   with actual fault/restoration evidence. Reconcile the local command
   catch only if its behavior remains equivalent after the shared fix.
