---
id: 2026-10-18-float-sum-interpreter-dependence
title: Builtin float sum() in metrics and render can differ in the last bit between Python 3.11 and 3.12+, so a value at a rounding boundary can render differently by interpreter
status: open
importance: low
importance_why: see body
effort: M
kind: research
area: fit-ingest, render, src/fitdocs/metrics, src/fitdocs/render
created: 2026-10-18
surfaced_by: queue-prerelease session (chore/q-ci-matrix implementer + review)
pinned_at: accccba
resume_command: "do: measure whether any rendered or persisted value differs between 3.11 and 3.12 across the golden fixtures and a real-archive sample for the listed sum() sites; replace with explicit accumulation (or math.fsum by decision) where it does [queue: .kiro/queue/2026-10-18-float-sum-interpreter-dependence.md]"
context:
  - src/fitdocs/metrics/aggregates.py
  - src/fitdocs/metrics/power.py
  - src/fitdocs/render/splits.py
  - src/fitdocs/render/dynamics.py
  - src/fitdocs/render/charts/series.py
blocked_by: []
---

Python 3.12 made float sum() compensated (Neumaier). accccba fixed the one site where it changed a
golden (render/charts/series.boxcar_smooth). Remaining builtin float sum() sites: metrics/aggregates.py
~65 and ~292 (trailing-boxcar altitude smoothing -> gain/loss), metrics/power.py ~201, ~242, ~327, ~330,
render/splits.py ~203, ~321, render/dynamics.py ~142, load/channels/grade.py ~166, history/series.py
~436. No test went red on 3.12/3.13, so any effect is below rounding today; unmeasured on real data.

Related (decision, not this item): a constant series smooths to non-constant floats and
normalize_band (render/charts/series.py ~65) stretches that noise to the full band, so a flat 28.8
km/h line draws as a zig-zag (visible in the ride_no_power golden). Fixing it changes goldens and
existing chart output -- a DOC_VERSION question for the maintainer.
