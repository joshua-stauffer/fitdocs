---
name: build-training-block
description: Builds, amends and settles a training-block plan source consumed by the fitdocs CLI. Use this skill when an athlete wants a new mesocycle-based training block written, an existing running block amended, or a plan render report's ambiguous or unresolved row settled.
license: MIT
compatibility: Requires the fitdocs command to be installed and on the agent's path, and a fitdocs data root already configured.
metadata:
  version: 0.1.0
---

# Build a training block

## When this applies

- A new training block: the athlete wants a mesocycle-based plan written from scratch.
- An amendment to a running block: the athlete's circumstances changed and an already-rendered block needs a dated change.
- Settling a resolution: a `plan` run's report called a row's match ambiguous, or could not honor an override, and a human decision is needed to move forward.

## Before you write: what to ask

Before writing a plan source, settle these with the athlete. A missing answer is asked for, never invented:

1. The goal -- what the block is building toward.
2. The start and end dates.
3. The mesocycle length, in days.
4. The key sessions and the days they fall on.
5. The weekly structure -- how the week is shaped around the key sessions.
6. Cross-training and strength work, if any.
7. Whether the athlete wants a load target per mesocycle and, if so, the numbers.

This skill proposes no sessions, paces or progressions of its own. The plan's content is the athlete's; this skill only writes it down in the grammar the tool reads.

## The plan source, by example

The plan source is a TOML file, one per block. This is a complete, valid example the shipped parser accepts:

```toml
# --- the plan as first written ---
title = "Example block"
starts = 2030-01-07
ends = 2030-02-17
goal = """
Build a durable aerobic base, then sharpen for a target tune-up race.
Balance running volume with one weekly strength session and full recovery.
"""
mesocycle_days = 14

[[mesocycle]]
number = 1
target_load = 600
focus = "aerobic base"

[[mesocycle]]
number = 3
focus = "sharpen"

[[workout]]
id = "w1-mon"
date = 2030-01-07
sport = "Run"
title = "Easy aerobic run"
summary = "Zone 2 easy effort"
prescription = "40 minutes easy, conversational pace."

[[workout]]
id = "w1-wed"
date = 2030-01-09
sport = "Workout"
modality = "strength"
indoor = true
title = "Strength circuit"
summary = "Full body maintenance"
prescription = "3 rounds of squat, row and plank, moderate load."

[[workout]]
id = "w1-sat"
date = 2030-01-12
sport = "Run"
title = "Long run"
summary = "Zone 2 endurance"
prescription = "90 minutes steady, fuel every 30 minutes."

[[workout]]
id = "w2-tue"
date = 2030-01-22
sport = "Run"
title = "Morning intervals"
summary = "Threshold intervals"
prescription = "6 x 3 minutes hard with 2 minutes easy between."

[[workout]]
id = "w2-tue-b"
date = 2030-01-22
sport = "Run"
title = "Evening shakeout"
summary = "Very easy shakeout"
prescription = "20 minutes very easy."

[[workout]]
id = "w3-thu"
date = 2030-02-07
sport = "Ride"
title = "Endurance ride"
summary = "Zone 2 endurance"
prescription = "75 minutes steady in the aero position."

# --- amendments: appended, never edited ---
[[amendment]]
date = 2030-01-15
reason = "Travel week"

[[amendment.update]]
id = "w1-sat"
date = 2030-01-14

[[amendment.add]]
id = "w2-sun"
date = 2030-01-27
sport = "Walk"
title = "Recovery walk"
summary = "Easy recovery"
prescription = "30 minutes easy walking."

[[amendment.remove]]
id = "w1-wed"

[[amendment.mesocycle]]
number = 2
target_load = 650

# --- overrides: appended when settling ---
[[override]]
date = 2030-01-23
id = "w2-tue"
stems = ["2030-01-22-run-0700"]
reason = "the morning session was the intervals"

[[override]]
date = 2030-01-23
id = "w2-tue-b"
skipped = true
reason = "shakeout dropped"
```

The block header and rows, by key:

| Key | Type | Required | Rule |
|-----|------|----------|------|
| `title` | string | yes | single line |
| `starts` | date | yes | bare TOML date |
| `ends` | date | yes | bare TOML date, not before `starts` |
| `goal` | string | yes | one or more lines |
| `mesocycle_days` | integer | yes | at least 1; divides the block into mesocycles of this length counted from `starts`, the last one shorter when the span does not divide evenly |
| `[[mesocycle]]` | array of tables | no | `number`, and optionally `target_load` (a positive number) and `focus` (single line) |
| `[[workout]]` | array of tables | no | `id`, `date`, `sport`, `title`, `summary`, `prescription` required; `modality` and `indoor` optional |
| `[[amendment]]` | array of tables | no | `date`, `reason`, and any of `[[amendment.update]]`, `[[amendment.add]]`, `[[amendment.remove]]`, `[[amendment.mesocycle]]` |
| `[[override]]` | array of tables | no | `date`, `id`, and either `stems` (a non-empty array) or `skipped = true`, plus an optional `reason` |

Sports: `Ride`, `Run`, `Swim`, `Walk`, `Hike`, `Rowing`, `Workout`.

Modalities: `run`, `bike`, `swim`, `strength`, `other`.

A `modality` is allowed only when `sport = "Workout"`; every other sport carries no modality.

A row's `id` matches `[a-z0-9][a-z0-9-]*` and is unique for the life of the block. Every date in the file is a bare TOML date (never quoted), and a row's date must fall inside the block's `starts..ends` bounds. The file's name, without its extension, is the block's id -- this example's companion file is named `example-block.toml`.

The example is split by three comment markers into the three situations section 1 names: the plan as first written, the amendments appended to it, and the overrides written to settle a resolution.

## Where the source lives

The plan source lives in `plans/` under the data root by default, or in the directory the `[plans]` setting's `path` in `fitdocs.toml` names. fitdocs never creates, writes, renames or deletes that directory or anything in it -- create it yourself if it does not already exist. One file per block; the file's stem is the block's id.

## Render it and read the report

Run:

```bash
fitdocs plan --out <data root>
```

The same reconciling pass also runs at the end of `fitdocs sync` and `fitdocs regen`, so a block's pages may already be current when you run this command directly.

| Outcome | Meaning | Do |
|---------|---------|----|
| `rendered` | The block was rendered (or re-rendered) from its source. | Open the page the report names and continue to the settling section if it reports anything to settle. |
| `unchanged` | The source parsed and produced no byte change. | Nothing. |
| `invalid` | The source has one or more problems. | Fix each problem the report lists at the entry and field it names, then rerun. |
| `blocked` | A foreign file occupies a path this block would write. | Move or inspect the file at the path the report names, then rerun. |
| `failed` | The block could not be written for a reason the report states. | Report the reason to the user; do not guess at a fix. |

`No source: <path>` names a rendered page or directory the tool found with no matching plan source; it is listed and left alone -- tell the user; do not write a plan source to match it. A declaration file the run could not place because a foreign file occupies its spot prints as `Declaration not placed (foreign): <path>`. A trailing note, when the report carries one, is printed in prose beneath the per-block lines.

Report lines: the reconciling pass that follows also prints lines beginning `reconciled`, `mesocycle`, `ambiguous:` and `methodology:`. Beneath a block's `reconciled` line, indented problem lines each describe one override problem the reconciler found -- read each one and follow the settling section below to resolve it.

| Exit | Meaning |
|------|---------|
| `0` | No invalid, blocked or failed block and no override problem. An ambiguous match still exits `0` -- read the `ambiguous:` line and the settling section. |
| `1` | An invalid, blocked or failed block, or an override problem (including a stem that could not be found). |
| `2` | A configuration error -- fix the setting or path the message names and rerun. |

## Amend midstream

To change a running block, append one `[[amendment]]` with a `date` and a `reason` -- never edit an earlier entry; the history of changes is part of the record. Inside it:

- `[[amendment.update]]` to move a row or change its fields -- **move a row, never remove and re-add it**, so it keeps its id and page and the record reads as a move.
- `[[amendment.add]]` to add a new row.
- `[[amendment.remove]]` to remove a row.
- `[[amendment.mesocycle]]` to set or change a mesocycle's target load or focus.

An update may change any of the seven mutable fields: `date`, `sport`, `modality`, `indoor`, `title`, `summary`, `prescription` (never `id` -- that is what names the row being changed). Amendment dates must be non-decreasing: each new amendment's `date` is on or after the previous one's.

After appending, rerun the command above and read the report.

## Settle an ambiguous match

When the report names a block whose page has something to settle, open the block page the `rendered` line names.

| State | Meaning | Do |
|-------|---------|----|
| `matched` | The row was matched to one or more logged workouts. | Nothing, unless the confidence label below says otherwise. |
| `overridden` | An override named this row's stems directly. | Nothing further; the override is in effect. |
| `skipped` | An override marked this row skipped. | Nothing. |
| `not logged` | The row's date has passed and no logged workout was matched to it. | Confirm the session happened and check whether it was logged under a different type or day. |
| `upcoming` | The row's date has not yet arrived. | Nothing yet. |

A `matched` row also carries a confidence label:

| Label | Rule | Do |
|-------|------|----|
| `exact` | One logged workout on the row's day is of its type, and no other planned row competes for it. | Nothing. |
| `absorbed` | Several logged workouts on the row's day are of its type, and no other planned row competes for them; all are taken as this one row. | Nothing. |
| `ambiguous` | Two or more planned rows of one type on one day compete for the day's logged workouts, and the assignment is a guess. | Settle it with an override entry naming this row and the logged workout stems. |

An ambiguous row's cell reads `matched (ambiguous): [stem](...)` on the block page, and its own planned page carries the sentence "Settle it with an override entry naming this row and the logged workout stems." The logged workout stems you need are found in three places: the link text of each competing row's cell in the block table, the bullets under a competing row's `Matched (ambiguous)` sentence on its planned page, and the `Unplanned:` list under the mesocycle's table for a logged workout no row claimed. A `Logged on this day:` listing appears only on a row that got no stem at all (`not logged` or `upcoming`).

To settle, append an `[[override]]` with `date`, `id` and either `stems = [...]` naming the logged workout stems that fulfil the row, or `skipped = true`; `reason` is optional. When a row has more than one override, the latest one -- by `date`, then by file position -- wins, so correct a mistake by appending a new override, never by editing an old one. A stem the tool cannot find is rendered as `not found`, listed under `Problems:` on the block page and printed as an indented problem line beneath `reconciled` in the report, and fails the run with exit `1` -- fix the stem and rerun.

After appending an override, rerun the command above and read the report.

## Ownership

fitdocs owns the rendered block and planned pages and rewrites them in full on every run; the plan source is the athlete's, and fitdocs only ever reads it. In each fitdocs-owned directory, the in-tree `AGENTS.md` declaration is the authority on what is owned; the [published ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) is the detail behind it.

## What this skill never does

- Edit a logged workout page.
- Edit a rendered block or planned page.
- Run `fitdocs regen`.
- Write anything other than the plan source and files the agent environment itself owns.
- Propose a plan of its own.
