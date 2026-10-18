---
id: 2026-10-18-wellness-conflict-within-one-file-unactionable
title: A wellness conflict between entries of one Garmin userBioMetrics file lists that file three times and prescribes deleting it
status: open
importance: low
importance_why: The real-corpus `check` emits a finding whose remedy would drop a whole archive file to fix one day's weight. Weight is not on workout pages.
effort: S
kind: bug
area: wellness-store, src/fitdocs/wellness/inspect.py, src/fitdocs/wellness/formats/garmin.py
created: 2026-10-18
surfaced_by: /kiro-validate-impl workout-wellness (real-corpus scratch rebuild)
pinned_at: a0e4b92
resume_command: "do: make the Garmin userBioMetrics reader pick the entry with the greatest metaData.sequence/version for a day and metric (or report within-file conflicts with entry positions and a remedy that does not delete the file) [queue: .kiro/queue/2026-10-18-wellness-conflict-within-one-file-unactionable.md]"
context:
  - src/fitdocs/wellness/inspect.py
  - src/fitdocs/wellness/formats/garmin.py
  - .kiro/specs/wellness-store/requirements.md
  - docs/wellness.md
blocked_by: []
---

## What

The maintainer's Garmin export `<profile-id>_userBioMetrics.json` holds
three manual weight entries for one day, with two distinct values. Each
entry carries `version` and `metaData.sequence`, and both are distinct
epoch-millisecond timestamps. The reader ignores them.

So wellness-store records a conflicting duplicate (Req 4.4: "nothing marks one
as newer"), and `fitdocs check` prints this (values and hashes elided):

```
wellness/<year>.csv
  <day> weight_kg garmin-export: kept <value> from wellness-archive/garmin-biometrics/<sha>.json; conflicting entries: wellness-archive/garmin-biometrics/<sha>.json, wellness-archive/garmin-biometrics/<sha>.json, wellness-archive/garmin-biometrics/<sha>.json
  if one of the entries is wrong, delete it from `wellness-archive/` and from the inbox, then run `fitdocs regen`; …
```

The same `<sha>` appears all three times.

All three "entries" are the same archive file (`inspect.py:79-89` lists
`kept_entry` plus each `other` ref). The remedy would delete the whole
biometrics archive, which is every Garmin weight and VO2max value, to fix one
day.

## Why it matters

The finding stays on every `check` run, and it cannot be resolved as written.
An agent following the remedy literally would destroy data.

## Evidence

- Scratch rebuild of the real data root at a0e4b92: `fitdocs check` exited 1
  with 15 findings. 14 are pre-existing identity "same session" pairs; this one
  is new from the staged Garmin biometrics.
- The three entries' `version` values are distinct. Here the kept value
  happens to equal the newest entry's value, so the choice is right by
  accident.

## How to pick it up

1. Read wellness-store Req 4.4/4.5 and the Garmin format section of
   `docs/wellness.md`. Garmin's `version`/`sequence` arguably *is* "something
   that marks one as newer".
2. Either resolve by the greatest sequence inside the Garmin reader, or keep
   the conflict but name entries by position. In the second case the remedy
   must not tell the user to delete a multi-day file.
3. Add a synthetic fixture with three same-day entries in one file.
