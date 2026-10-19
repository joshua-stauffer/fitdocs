---
title: Training blocks
description: Write a training plan as a small file you own. fitdocs renders it into pages and matches your logged workouts against it.
section: Guides
order: 8
---

# Training blocks

Your workout pages record what you *did*. A training block says what you *plan* to do: a goal, a start and end date, a repeating cycle of weeks (called mesocycles), and the sessions on each day. fitdocs renders the plan as pages and checks your logged workouts against it.

## Create your plan
LLMs make it easy to learn fast, but they don’t replace your judgement. Think through why you’re training, and what you’d like to achieve, and decide how much time you can sustainably devote to training each week. Then, have your agent use the **`build-training-block`** skill to write a plan file. The agent **asks you** for the goal, dates, mesocycle length, key sessions, weekly shape, cross-training, and load targets, and writes down what you say. See [Wiki integration](wiki-integration.md) to install it, and prompts to use it.

The block page has a **Notes** section that belongs to you, just like a workout page.

The full plan grammar (every key and rule) is in the skill itself: run `fitdocs skill build-training-block` to find it.

## How it works

1. **You own the plan source.** Each block is one TOML file in your plan folder (default `<data-root>/plans/`). fitdocs only reads this folder. It never writes, renames, or deletes anything there. You can write it by hand, or describe what you’d like and have your agent write it.
2. **fitdocs renders the pages.** `fitdocs plan` writes a **block page** to `blocks/` and a **planned-workout page** for every session, so each planned session has its own page before you've done it.
3. **It matches as you go.** Each planned session is matched against your logged workout pages and shown as one of:

| Status | Meaning |
|---|---|
| `matched` | A logged workout fits. It's labelled `exact` (one candidate), `absorbed` (a session split across several recordings), or `ambiguous` (two planned sessions on the same day are competing for the same workouts). |
| `overridden` | You've pinned it to specific workouts with an override. |
| `skipped` | You've marked it as not done with an override. |
| `not logged` | The date has passed and nothing matched. |
| `upcoming` | It's still in the future. |

The block page also adds up your actual load for each mesocycle and compares it to your target.

The matching is recalculated from your pages every time and never stored. If a better match is logged later, it simply takes over. Nothing is ever written back into your workout pages or your plan file.

The pass runs automatically at the end of `sync`, `pull --sync`, and `regen`, and whenever you run:

```sh
fitdocs plan
```

## A minimal plan

```toml
# <data-root>/plans/autumn-10k.toml
title = "Autumn 10k"
starts = 2026-10-05
ends = 2026-11-29
goal = "Sub-34 at the November 10k. Keep one strength day a week."
mesocycle_days = 14

[[mesocycle]]
number = 1
target_load = 600
focus = "aerobic base"

[[workout]]
id = "w1-tue"
date = 2026-10-06
sport = "Run"
title = "Threshold intervals"
summary = "5 × 1000 m at threshold"
prescription = "2 km warm-up, 5 × 1000 m @ 3:20/km with 2:30 jog, 2 km cool-down."

[[workout]]
id = "w1-sat"
date = 2026-10-10
sport = "Run"
title = "Long run"
summary = "Zone 2 endurance"
prescription = "90 minutes steady."
```

## Plans change, and the page keeps a record

When things change, **don't edit earlier entries**. Add a dated amendment to the end of the file:

```toml
[[amendment]]
date = 2026-10-14
reason = "Travel week"

[[amendment.update]]
id = "w1-sat"
date = 2026-10-11
```

Amendments can move, add, or remove sessions and change mesocycle targets. The block page shows the current plan next to the original, with each change. The plan file becomes a history of how the plan changed.

## Match a workout to the plan yourself

When the matching is `ambiguous`, or you want to decide, add an override to the plan file:

```toml
[[override]]
date = 2026-10-07
id = "w1-tue"
stems = ["2026-10-06-run-0700"]    # the workout page(s) that count as this session
reason = "the morning run was the intervals"
```

Overrides go in the plan file, not on the workout page, because they're a decision about the plan.

An override names workout pages by filename. If fitdocs renames a page (see [When a page is renamed](workout-pages.md#when-a-page-is-renamed)), update the name in your override, or `fitdocs plan` reports it as not found.

