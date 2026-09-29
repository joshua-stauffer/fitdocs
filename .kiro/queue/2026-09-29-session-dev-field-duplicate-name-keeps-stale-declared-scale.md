---
id: 2026-09-29-session-dev-field-duplicate-name-keeps-stale-declared-scale
title: A duplicated session developer-field name leaves the name in developer_fields_declared_scale after a later unscaled description wins, so the render skips the hundredths fallback on a raw value
status: open
importance: low
importance_why: Latent -- no corpus file is reported to carry a duplicate name -- but when it fires a supplemental row renders 100x too large with no signal, the defect class the 2026-07-25 fixes closed.
effort: S
kind: bug
area: fit-ingest, running-dynamics, src/fitdocs/ingest/summary.py, src/fitdocs/render/sections.py
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, running-dynamics writer)
pinned_at: f500dc1
resume_command: "do: after running-dynamics lands (it moves this decoding into ingest/developer.py but keeps the session loop), make the session reader's declared-scale set follow the same last-described-wins rule as the value -- discard the name when a later description of it declares neither scale nor offset -- and decide in the same change what a later scale-0 duplicate does; add a builder fixture with two session descriptions of one name (first scaled, second not) and pin that the name is absent from developer_fields_declared_scale"
context:
  - src/fitdocs/ingest/summary.py
  - src/fitdocs/render/sections.py
  - .kiro/specs/running-dynamics/research.md
  - .kiro/specs/running-dynamics/design.md
blocked_by: [running-dynamics]
---

## What
The session developer-field reader loops over descriptions; a later
description with the same `field_name` overwrites `resolved[name]`, but
`declared_scale.add(name)` is never undone. If an earlier description of the
name declared a scale and a later one did not, the raw later value wins
while the name stays in `developer_fields_declared_scale`, and
`_supplemental_rows` then uses scale `1.0` instead of the hundredths
fallback. running-dynamics' new record-level reader is not affected; its
session-reader change keeps this loop ("keeps ... its last-described-wins
name rule").

## Why it matters
`AVG METs` and `SESSION WEATHER HUMIDITY` would render 100x too large under
a correct label. Also untidy: a later scale-0 duplicate is skipped, so the
earlier value survives, which is not last-described-wins either.

## Evidence
- `src/fitdocs/ingest/summary.py:211-224` -- the loop; `:222` overwrite,
  `:223-224` add without discard; `:220-221` scale-0 skip.
- `src/fitdocs/render/sections.py:256-258` -- scale `1.0` when the key is in
  `developer_fields_declared_scale`.
- `.kiro/specs/running-dynamics/research.md` § "One shared per-value decoder"
  (~:200-216) and § "Last-described wins on a duplicated name" (~:218-222).
- "No corpus file has a duplicate name" is the running-dynamics writer's
  report from the maintainer's archive; not re-checked here.

## How to pick it up
1. Read the loop where running-dynamics left it (`ingest/summary.py` or
   `ingest/developer.py`).
2. Write the failing fixture test first (builder: two descriptions, one
   name, first with a scale).
3. Fix the set; done when the test is green and the scale-0 duplicate case
   has a stated, pinned behaviour.
