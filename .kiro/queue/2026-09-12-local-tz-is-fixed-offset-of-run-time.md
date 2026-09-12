---
id: 2026-09-12-local-tz-is-fixed-offset-of-run-time
title: Documents are stamped with the UTC offset in force when the command ran, not the activity's DST-aware local zone
status: open
importance: high
importance_why: Wrong local time reaches every document rendered in the opposite DST half-year -- start_time, the -HHMM filename stem, and near-midnight the date -- across a real 2,600-doc wiki today.
effort: S
kind: bug
area: workout-docs, wiki-contract, src/fitdocs/cli.py, src/fitdocs/layout.py, src/fitdocs/render/frontmatter.py
created: 2026-09-12
surfaced_by: Final Surge coaching-notes backfill (matching FS times against document start_time)
pinned_at: 719ed3e
resume_command: "do: replace cli._local_tz's fixed-offset tzinfo with a DST-aware ZoneInfo of the system zone (or a fitdocs.toml `timezone` key), add a test that a January and a July activity rendered in one run get different offsets, and confirm regen renames the affected docs without duplicating them [queue: .kiro/queue/2026-09-12-local-tz-is-fixed-offset-of-run-time.md]"
context:
  - src/fitdocs/cli.py
  - src/fitdocs/layout.py
  - src/fitdocs/render/frontmatter.py
  - .kiro/specs/workout-docs/design.md
  - .kiro/queue/2026-07-26-frontmatter-date-vs-filename-date-unasserted.md
blocked_by: []
---

## What
`src/fitdocs/cli.py:665-674` (`_local_tz`) returns
`datetime.now().astimezone().tzinfo`. That is a **fixed-offset** tzinfo for
*now* (`CEST` when checked on 2026-09-12), not a zone. It is threaded into
`sync`/`regen` and used by `layout.doc_stem` (filename `-HHMM`) and
`render/frontmatter.py:81,123` (`start_time`, `date`) for every activity,
regardless of the activity's own date. An activity recorded in January is
rendered at +02:00 when the build runs in July.

## Why it matters
Every winter document in a summer-built wiki carries a local time one hour
late: `start_time` offset is wrong, the `-HHMM` stem is wrong, and an activity
between 23:00 and 00:00 true local time lands on the next day's `date`
(which also feeds date-scoped benchmark selection and load-history's daily
series). The no-fabrication rule is about exactly this: a document that states
a local time the athlete never saw. The reverse (winter build, summer
activities) is one hour early. A regen after the fix renames roughly half the
documents.

## Evidence
- `src/fitdocs/cli.py:672`: `local = datetime.now().astimezone().tzinfo`.
- Python, run 2026-09-12 on this machine:
  `datetime.now().astimezone().tzinfo` -> `CEST`;
  `datetime(2024,11,3,8,27,tzinfo=ZoneInfo('Europe/Berlin')).utcoffset()` -> `1:00:00`.
- Real wiki (`~/Library/Mobile Documents/com~apple~CloudDocs/pkm-data/wiki/workouts`,
  built 2026-08-23 and 2026-09-12, both in CEST):
  `grep -h '^start_time' 202[2-6]-*.md | grep -oE '[+-][0-9]{2}:[0-9]{2}'"'"'$' | sort | uniq -c`
  -> `1858 +02:00'` -- not one `+01:00`. Specific docs:
  `2024-11-03-run-0827.md` has `start_time: '2024-11-03T08:27:05+02:00'`
  (Berlin was +01:00 that day); `2024-01-10-run-1805.md` has
  `'2024-01-10T18:05:21+02:00'`.
- Cross-check from an independent clock: Final Surge shows the 2024-11-03
  activity at 01:27:05 US Eastern (EST, UTC-5) = 06:27:05 UTC = 07:27 Berlin,
  not 08:27.

## How to pick it up
1. Read `cli._local_tz` and its call sites (`grep -n _local_tz src/fitdocs/cli.py`),
   then `layout.doc_stem` and `render/frontmatter.py:81,123` to see where the
   tzinfo is applied per activity.
2. Replace the fixed offset with a real zone: `ZoneInfo` of the system zone
   (read `/etc/localtime`'s link target, or `time.tzname` is not enough), or a
   user-owned `timezone = "Europe/Berlin"` key in `fitdocs.toml` with the
   system zone as the fallback. `datetime.astimezone(zone)` then yields the
   correct offset per activity.
3. Test: one render pass with a January and a July activity must emit
   `+01:00` and `+02:00` respectively (Europe/Berlin), and `doc_stem` must
   agree with the frontmatter `date` (see the linked 2026-07-26 item -- fix
   both together).
4. Done means: the test above is green, `fitdocs regen --force` on a data root
   with winter docs renames them (identity match by `uuid`/`sources` keeps
   them one document each -- verify no duplicates), and `fitdocs check` is
   clean afterwards.

## Open questions
- Whether the zone should come from settings (`fitdocs.toml`) or only from the
  system: an athlete who moves between zones (this wiki has runs in both
  New York and Berlin) gets the *machine's* zone either way, which is still
  one honest, consistent choice -- but the activity's own recorded zone, when a
  FIT file carries one, would be better and is a larger change.
