---
title: Benchmarks and race tags
description: Tag your races and hard efforts on their pages, and fitdocs turns them into dated threshold estimates, so years of training get a load. Resting and max heart rate come from your own data.
section: Guides
order: 5
---

# Benchmarks and race tags

A race is the best test of the shape you’re in. Sports science has turned race results into threshold estimates for decades. Tag a workout page as a race, and fitdocs can derive your equivalent threshold pace (run), threshold heart rate (run, ride), and FTP (ride). 

## 1. Tag the effort on its page

Add these keys to the frontmatter of any workout page. Fitdocs doesn’t write these, so they’ll persist through a regen:

```yaml
effort: race                  # race | test | hard
effort_distance_m: 21097.5    # official distance, in metres
effort_time_s: 4401           # official time, in seconds (1:13:21)
effort_event: "[[Lisbon Half 2025]]"   # optional; any text or a quoted wikilink
```

| Kind | Use it for |
|---|---|
| `race` | A race result |
| `test` | A formal test, such as a time trial or FTP test |
| `hard` | A near-maximal effort that wasn't a race or a test |

Use the *official* distance and time, not what your GPS measured. A course distance only counts together with its time. A timed test can have `effort_time_s` without a distance.

## 2. Derive

```sh
fitdocs derive-benchmarks --dry-run   # show what would be derived
fitdocs derive-benchmarks             # write it to athlete.toml
```

What fitdocs derives, and from which efforts:

| Sport | Threshold | Derived from |
|---|---|---|
| Run | **Threshold pace** | Races, using Riegel's race-equivalence model to project your one-hour pace |
| Run, Ride | **Threshold heart rate** | Races, tests, or hard efforts, as the average heart rate over the effort |
| Ride | **FTP** | Races and tests of the right length, as the average power over the effort |

Each result is written to `athlete.toml` as a **dated benchmark**, with a note saying which page it came from, which method was used, and which paper the method comes from.

## 3. Rescore

With dated benchmarks going back years, fill in the old pages:

```sh
fitdocs load
fitdocs history
```

Each activity is scored with the benchmark that applied on its date. Then the [history page](history.md) can draw your fitness over your whole archive.

`fitdocs load` fills in pages that don’t have a load yet. A page that already has one keeps it, so after new benchmarks change the picture, run `fitdocs load --recompute` to rescore those too.

## Heart-rate benchmarks

`derive-benchmarks` also works out two heart-rate values that need no tagging:

- **Resting heart rate** comes from your [wellness](wellness.md) data: the median of at least 14 days of values from one source within the last 28 days. Sources are never mixed.
- **Max heart rate** comes from your runs and rides: the median of your three highest 30-second peaks within a year, leaving out spikes, gaps, and stretches where the heart rate looks locked to your cadence. Other sports don’t count.

A new value is only written when the evidence holds up. Resting heart rate has to differ from the one in force by more than 3 bpm for 14 days in a row. Max heart rate has to beat the one in force by more than 2 bpm. A derived max never goes down, so if yours has really dropped, record the lower value by hand.

Values you entered by hand are never changed or deleted. Yours stays in force until later evidence passes those rules. When a derived value takes over, the run says so, and `fitdocs check` lists it so you can decide. To keep your own number, record a new entry dated after the takeover.

Deriving never rescores your pages by itself. Run `fitdocs load --recompute` when you want them rescored. On a large archive, the heart-rate stage can take several minutes.

> **With an LLM:** *"Go through my workouts from 2023–2025 and find the ones that look like races, based on titles, my notes, and pacing. List them with dates and distances and ask me to confirm official times. For each one I confirm, add the `effort`, `effort_distance_m`, `effort_time_s`, and `effort_event` frontmatter keys, and change nothing else on the page. Then run `fitdocs derive-benchmarks --dry-run` and walk me through the report."*
>
> More prompts like this are in the [prompt library](../llm/prompts.md).
