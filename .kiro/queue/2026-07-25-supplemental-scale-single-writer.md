---
id: 2026-07-25-supplemental-scale-single-writer
title: The supplemental unit scale is hardcoded for HealthFit with no writer check
status: open
importance: low
importance_why: Only misfires if a non-HealthFit writer emits these exact key names unscaled; no such writer is observed, but the failure is silent.
effort: S
kind: gap
area: workout-docs, src/fitdocs/render/sections.py
created: 2026-07-25
surfaced_by: /kiro-validate-design on the Avg METs scale defect
pinned_at: c3d2201
resume_command: 'do: Decide whether _SUPPLEMENTALS needs a plausibility guard or per-writer scale resolution, once a second FIT writer emitting these keys actually exists.'
context:
  - src/fitdocs/render/sections.py
  - .kiro/specs/workout-docs/design.md
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`_SUPPLEMENTALS` in `src/fitdocs/render/sections.py` now multiplies
`SESSION WEATHER HUMIDITY` and `AVG METs` by a hardcoded `0.01`, because
HealthFit encodes both as UINT16 hundredths. The scale is keyed on **field name
alone** — nothing checks which application wrote the file. A different FIT
writer emitting a field literally named `AVG METs` in true METs would render
`12` as `0.1`: the same class of falsehood the scale was added to remove, only
inverted.

A plausibility guard was considered during design review and deliberately
skipped by Josh on 2026-07-25 as speculative generality. This item records the
decision and its trigger condition.

## Why it matters

Currently harmless: every one of the 74 corpus files is a HealthFit export, and
`AVG METs` / `SESSION WEATHER HUMIDITY` are HealthFit-specific field names that
another writer is unlikely to reuse. It becomes real if fitdocs picks up users
on other export apps (see the `distribution` spec) whose writers happen to
collide on these names. The failure is silent — a plausible-looking wrong number
under a correct label, with nothing in the document indicating doubt.

## Evidence

Descriptor survey across all 74 files in `~/code/fitdocs-demo/inbox/` — every
occurrence carries an identical, scale-free descriptor, confirming a single
writer convention rather than a per-file declaration:

```
field_name                        rec  scale/offset/units/basetype
AVG METs                           64  [(None, None, None, 132)]
SESSION WEATHER HUMIDITY           16  [(None, None, None, 132)]
```

Base type 132 is UINT16, which cannot express 12.64 directly — storing
hundredths is the writer's workaround, and it is invisible to a generic decoder.
The filenames span several upstream sources (Stryd, WorkOutDoors, Health Sync,
Apple Watch), but all are HealthFit *exports*, so the corpus evidences exactly
one writer.

The separating property, if a guard is ever wanted: UINT16 hundredths land at
100–2500 for real METs, while a true-MET integer writer can only emit 1–25. The
ranges do not overlap, so a threshold near 50 distinguishes them cleanly.

**Path note (2026-08-23):** the demo project moved to
`~/Library/Mobile Documents/com~apple~CloudDocs/fitdocs-demo`. Paths above
name its former location, `~/code/fitdocs-demo`, which no longer exists.

## How to pick it up

1. Read the `_SUPPLEMENTALS` comment block in `src/fitdocs/render/sections.py`;
   it states the encoding and the verification behind the `0.01`.
2. Establish whether a second writer actually exists in any user's corpus. If
   not, close this `dropped` — the guard is not worth its own failure modes.
3. If one does, the choice is the same one design review framed: a range guard
   in the render layer (cheap, local) versus resolving scale per writer at
   ingest, which needs a writer-identity concept `fit-ingest` does not have and
   which reopens `fit-ingest` Req 14.2's verbatim contract. Done means a
   non-HealthFit file with these keys renders correctly or omits the row —
   never a wrong number.

## Open questions

- Does `distribution` intend fitdocs for non-HealthFit exporters at all? That
  answer decides whether this is worth any work.
