---
title: Training history
description: One page showing fitness, fatigue, and form across your whole archive, built only from the load already on your workout pages.
section: Guides
order: 5
---

# Training history

```sh
fitdocs history
```

This builds one page, `history/training-load-history.md`, with a chart of **fitness, fatigue, and form** across your whole archive and a list of your tagged races on the timeline.

## The model

This is the fitness–fatigue model from Banister and colleagues, the same idea behind "CTL / ATL / TSB" in other tools:

- **Fitness** is a slow-moving average of your load (45-day time constant by default).
- **Fatigue** is a fast-moving average (15 days by default).
- **Form** is fitness minus fatigue. When it's positive, you're fresh.

The page lists the constants it used and says whether they're fitdocs' **defaults** (starting values from the original papers, not fitted to you) or **values you set**:

```toml
# <data-root>/fitdocs.toml
[history]
tau_fitness_days = 42
tau_fatigue_days = 7
```

## Low signal data

A fitness curve is only as accurate as the underlying data points. If fewer than 80% of a period's workouts have a load (configurable with `coverage_threshold`), the curve is **left blank** for that period instead of dipping toward zero. To fill the gaps, give fitdocs more thresholds, usually by [tagging your races](benchmarks.md) and running `fitdocs load`.

## When to rebuild

`history` is never run automatically. Rebuild it whenever you want a fresh picture, such as after a sync, after adding benchmarks, or once a week. It always rebuilds the whole page.

If you've installed more than one load calculator, pick which one's numbers to use with `--methodology <id>` or `[history].methodology`.
