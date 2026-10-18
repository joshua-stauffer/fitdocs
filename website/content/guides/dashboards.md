---
title: Dashboards
description: Write a markdown page with a few chart directives, and fitdocs draws each chart from the analytics index and keeps it current as you train.
section: Guides
order: 10
---

# Dashboards

A dashboard is a markdown page that you, or your agent, write in the `dashboards/` folder of your data root. Each chart on it is a short directive: an id, a chart kind, a title, and the SQL that feeds it. Fitdocs runs the SQL against the [analytics index](analytics.md), draws the chart as an SVG image, and keeps it current as you train. Everything else on the page is yours: the headings, the prose, the frontmatter, and the directives themselves.

## Your first dashboard

Create `dashboards/weekly-volume.md`. A page name uses lowercase letters and digits joined by hyphens.

```markdown
# Weekly volume

<!-- fitdocs:chart
id: weekly-km
kind: bar
mode: relative
title: Weekly distance
window: last 12 weeks
sql: |
  SELECT date_trunc('week', start_utc)::DATE AS week_start,
         sum(distance_m) / 1000.0 AS distance_km
  FROM activities
  WHERE start_utc::DATE >= $today - 84
  GROUP BY 1
  ORDER BY 1
channels:
  x: week_start
  y: distance_km
-->
```

Then draw it:

```sh
fitdocs dashboard refresh
```

Fitdocs puts the chart directly below its directive, between two markers, with a caption that gives the window and the latest date in the data:

```markdown
<!-- fitdocs:begin:chart:weekly-km -->
![Weekly distance](assets/weekly-volume/weekly-km.svg)
…
<!-- fitdocs:end:chart:weekly-km -->
```

The image is an ordinary SVG in `dashboards/assets/`, so it shows up in Obsidian, VS Code, GitHub, or any other markdown viewer.

A few rules keep the directive readable to fitdocs. The directive opens with `<!-- fitdocs:chart` and closes with `-->`, each at the very start of its line. `id`, `kind`, `mode`, `title`, and `sql` are required, and `sql` is written as a `sql: |` block. The SQL is one `SELECT` returning at most 10,000 rows, and `$today` is the only value you can put in it. Obsidian’s Live Preview shows the directive as dimmed source text, which is expected.

## Charts that move, and charts that don’t

A **relative** chart (`mode: relative`) is redrawn on every refresh, so “the last 12 weeks” always means the last 12 weeks.

A **frozen** chart (`mode: frozen`) is a record. The first time it’s drawn, fitdocs runs its SQL once, with `$today` set to that day, and saves the rows as a snapshot next to the image. From then on its SQL never runs again, so the chart keeps showing exactly what it showed that day. It’s the right choice for “how the block went” at the end of a training block. To take a fresh snapshot, freeze it again by page and chart id:

```sh
fitdocs dashboard freeze autumn-block:block-summary
```

The new snapshot is saved beside the old ones. Snapshots are the one thing fitdocs never changes or deletes. Only you can remove one.

## Keeping charts current

`fitdocs sync`, `pull --sync`, `regen`, and `load` refresh every dashboard right after they refresh the index. That pass never builds the index, never fails the command, and stays quiet when you have no dashboards. You can also run the command yourself:

```sh
fitdocs dashboard check                # report problems, write nothing
fitdocs dashboard refresh              # draw every chart
fitdocs dashboard refresh weekly-volume                  # one page
fitdocs dashboard freeze autumn-block:block-summary      # retake a frozen chart’s snapshot
fitdocs dashboard kinds                # list every chart kind and its settings
```

`check` reports each problem with a code, a message, and the fix. Add `--format json` for output an agent can read. A chart that fails is reported on its own, and the rest of the page still renders.

## Chart kinds

`line`, `area`, `bar`, `hbar` (ranked horizontal bars), `scatter` (with an optional trend line), `histogram`, `stat` (one headline number), `table`, `calendar-heatmap` (one cell per day), `heatmap`, `dual-axis` (two series on two scales), `band` (a low-to-high range), `box` (box and whisker), `mean-max` (best-effort curves), `small-multiples` (a grid of small charts, one per group), `stacked-100` (shares of 100%), and `reference-band` (points against a reference range).

`stat` and `table` write markdown instead of an image. `fitdocs dashboard kinds` lists each kind’s columns, options, and row limit.

## With an LLM

Install the packaged **`fitdocs-dashboards`** skill alongside `fitdocs-analytics` (see [Inside your wiki or vault](wiki-integration.md#agent-skills)). It teaches your agent to work out the SQL first, write the directive, choose between relative and frozen, and run `fitdocs dashboard check` until the page is clean. Then ask:

> *“Make me a dashboard page with weekly running distance for the last six months, time in each heart-rate zone per week, and my resting heart rate over the same period.”*

## Who owns what

You own the page. Fitdocs owns only what’s between each chart’s begin and end markers, and the images and snapshots it writes in `dashboards/assets/`. It never creates, renames, or deletes a dashboard page. An image is cleaned up once no dashboard page uses it, so if you link a chart from a page outside `dashboards/`, that link isn’t protected.

If your wiki is in git, commit your dashboard pages and their snapshots. A snapshot (`*.snapshot-<n>.json`) is the only copy of the rows a frozen chart was drawn from, so don’t ignore it, even if you ignore the images.

Every directive key, the SQL rules, and every chart kind’s settings are in the [dashboards reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/dashboards.md).
