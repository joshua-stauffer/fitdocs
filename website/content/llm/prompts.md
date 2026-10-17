---
title: Prompt library
description: Copy-and-paste prompts for setting up fitdocs, processing workouts, writing notes, reviewing training, tagging races, and building training blocks with any LLM agent.
section: Working with LLMs
order: 2
---

# Prompt library

These prompts are written for an agent that can run commands and read files in your data root, such as Claude Code, Codex, or a local agent. Each one works as written. Adapt freely.

Replace anything in `<angle brackets>`.

---

## Setup

### Install and set up standalone

```text
Install the fitdocs CLI with `uv tool install fitdocs` (fall back to pipx).
Create a data root at <~/fitdocs-data> and export FITDOCS_DATA to it in my
shell profile. Then run `fitdocs sync <folder with my .fit files>` and show
me the summary. Open one generated workout page and walk me through its
sections.
```

### Add fitdocs to my existing wiki

```text
Add fitdocs to this wiki following https://fitdocs.ai/guides/wiki-integration:
make this directory the data root with a .fitdocs/data-root pointer file,
create fitdocs.toml with an [inbox] table pointing at <inbox folder>, install
the packaged fitdocs-workouts skill into your skills directory by symlink
(use `fitdocs skill fitdocs-workouts` to find it), and add a short pointer to
the fitdocs AGENTS.md files in this wiki's root instructions. Then run
`fitdocs sync --no-prompt` and `fitdocs check` and report the results.
Don't touch anything outside the folders fitdocs owns.
```

---

## Every day

### Process new workouts

With the `fitdocs-workouts` skill installed, a few words is enough:

```text
Process my workouts.
```

Without the skill:

```text
Run `fitdocs sync --no-prompt`, then `fitdocs check`. Summarize what was
written, and tell me about anything deferred, quarantined, or failed. Don't
retry quarantined files or run `fitdocs regen` unless I ask.
```

### Post-workout debrief into my notes

```text
Open today's workout page in workouts/. Ask me three or four short questions
about how it went: effort, how my body felt, conditions, anything unusual.
Then write my answers into the page's Notes section (between the
fitdocs:begin:notes and fitdocs:end:notes markers) as a short recap in my
own words. Change nothing else on the page.
```

### Log a strength session

```text
Open today's strength workout page. I'll tell you what I did. Write it into
the Workout section (between the fitdocs:begin:workout / end:workout markers)
as a table of exercise, sets, reps, and weight. Change nothing else.
```

### Write a public post, sharing only what I choose

```text
Read <workout page>. Write a short, friendly activity description I could
post publicly: the session, one or two headline numbers, and how it felt
from my notes. Leave out the route, location, start time, and any health
details. Give me the text only. Don't post it anywhere.
```

---

## Understanding your training

### Explain one workout

```text
Read <workout page> and explain the session to me like a coach would:
how it was structured (use the laps), how heart rate responded to effort
(the Telemetry section), what the load number means and which channel it
came from, and any data-quality warnings. Use only numbers from the page.
```

### Weekly review

```text
Read the frontmatter of every workout page dated in the last 7 days and in
the 4 weeks before that. Total load_value by sport and overall for this
week, and compare it to the 4-week weekly average. Point out any page with no
load, or with warnings in its Training Load section. Then read my Notes from
this week and summarize how I seemed to be feeling. Keep it to one screen.
```

### Can I trust my heart-rate data?

```text
Go through my runs from the last <30> days. For each one, report the
cadence-lock and divergence warnings from the Training Load section and the
heart-rate coverage from Device & Data Quality. Which sessions look like
wrist-sensor data I shouldn't trust, and is there a pattern (a particular
device, cold weather, short runs)?
```

### Compare two sessions

```text
Compare <page A> and <page B>. Line up their laps, pace or power, and heart
rate for the matching parts of each session. Did I get fitter, or were
conditions different? Use my Notes for context and only use numbers from
the pages.
```

### Where am I on the fitness curve?

```text
Run `fitdocs history`, then read history/training-load-history.md. Tell me
where my fitness, fatigue, and form stand compared with the weeks before my
last three tagged races. Point out any periods where the curve is blank
because load is missing.
```

---

## Benchmarks

### Find and tag my races

```text
Search my workout pages from <2023–2025> for likely races: titles, my Notes,
distances close to 5k/10k/half/marathon, and hard even pacing. List the
candidates with date, distance, and time, and ask me to confirm each one and
give the official time. For each confirmed race, add the effort: race,
effort_distance_m, effort_time_s, and effort_event frontmatter keys to that
page, changing nothing else. Then run `fitdocs derive-benchmarks --dry-run`
and explain what would be derived and what was declined.
```

### After a test or race

```text
I just did <a 30-minute threshold test / a 10k race> — it's today's
workout page. Tag it with the right effort keys (ask me for the official
time), run `fitdocs derive-benchmarks`, then `fitdocs load` so newer pages
pick up the new benchmark. Tell me what changed in athlete.toml.
```

---

## Training blocks

These use the packaged `build-training-block` skill. Install it the same way as `fitdocs-workouts`.

### Build a block

```text
I want to build a training block. Use the build-training-block skill to
interview me. My goal is <race and target>, on <date>. Once I've answered
everything, write the plan source, run `fitdocs plan`, and show me the
first mesocycle.
```

### Change the plan midstream

```text
I'm travelling <dates>. Use the build-training-block skill to add an
amendment to my <block> plan: move <session> to <day> and drop <session>.
Don't edit earlier entries. Then run `fitdocs plan` and confirm the change.
```

### Settle a match

```text
Run `fitdocs plan` and look for ambiguous or unresolved sessions in the
report. For each one, show me the planned session and the candidate
workouts, and ask which is right. Record my answer as an override in the
plan source.
```

### Mid-block check-in

```text
Read my current block page in blocks/. For each mesocycle so far, compare
actual load against the target, list sessions that are not logged or
skipped, and summarize what my Notes say about fatigue. What should I talk
through before next week? Suggest questions only. The training decisions
are mine.
```

---

## Maintenance

### After upgrading fitdocs

```text
I just upgraded fitdocs. Run `fitdocs --version` and `fitdocs check`. If
check says pages need regenerating, run `fitdocs regen` and check again.
If you installed the skills by copying, refresh them from
`fitdocs skill <name>`. Summarize what changed using the release's
changelog entry.
```

### Health check

```text
Run `fitdocs check` and `fitdocs plugins`. Explain any findings or plugin
load errors in plain language and what to do about each.
```

---

**Have a prompt that works well?** Share it in a [GitHub issue](https://github.com/joshua-stauffer/fitdocs/issues), and we’ll consider it for this collection.
