---
id: 2026-10-05-zone-time-credits-negative-dt
title: Zone-time accumulation has no dt <= 0 guard, so out-of-order timestamps credit negative seconds
status: open
importance: low
importance_why: Only out-of-order record timestamps trigger it, but then rendered zone times (and the Phase 10 zone tables) are silently wrong.
effort: S
kind: bug
area: fit-ingest, src/fitdocs/metrics/zones.py
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-index spec writer)
pinned_at: 19fc92e
resume_command: "do: under the change ritual, add the same `if dt <= 0: continue` guard TRIMP uses (metrics/stress.py) to metrics/zones.py's accumulation loop, with a test whose time_s steps backwards and asserts no band goes negative"
context:
  - src/fitdocs/metrics/zones.py
  - src/fitdocs/metrics/stress.py
blocked_by: []
---

## What
`src/fitdocs/metrics/zones.py:69-75` adds `dt = time_s[i + 1] - time_s[i]` to
a band unconditionally. TRIMP's loop over the same series skips `dt <= 0`
(`src/fitdocs/metrics/stress.py:167-169`). A backwards or repeated timestamp
therefore subtracts (or adds zero) seconds from a zone band.

## Why it matters
Zone-time tables can show less time than was spent, or negative values, with
no data-quality flag. The two metrics disagree about the same series.

## Evidence
- `zones.py:72-74` at 19fc92e: `dt = time_s[i + 1] - time_s[i]; band = ...; seconds[band] += dt`.
- `stress.py:167-169`: `dt = ...; if dt <= 0: continue`.

## How to pick it up
1. Confirm whether fit-ingest's requirements say how non-monotonic time is handled (search "monotonic" in `.kiro/specs/fit-ingest/`).
2. Add the guard and a fixed-input test with a backwards step.
3. If rendered goldens move, it is a DOC_VERSION question -- record it.
