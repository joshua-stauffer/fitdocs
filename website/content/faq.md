---
title: FAQ
description: Short answers about devices, platforms, privacy, wellness, analytics, LLMs, Obsidian, and what fitdocs isn't.
section: Project
order: 3
---

# FAQ

**Which devices does it work with?**
Anything that records a `.fit` file, which covers most Garmin, Coros, Wahoo, Suunto, Hammerhead, and Stryd devices, plus Zwift and the Apple Watch (exported through an app like HealthFit). For sleep, HRV, and resting heart rate, it also reads an Apple Health export, Garmin's data export, and intervals.icu wellness. GPX and TCX aren't supported. When tested, they carried nothing a `.fit` file doesn't.

**Does it download my activities from Garmin or Strava?**
No. Both Garmin and Strava have adopted increasingly unfriendly API terms, and fitdocs doesn’t read directly from either of them. We recommend syncing your data through intervals.icu. It’s free and community-supported, its API terms are friendly to developers, and it syncs with most major fitness hardware. Once the data is in intervals.icu, use the fitdocs connector to sync it directly into your wiki. Connect your device to intervals.icu directly rather than through Strava, because intervals.icu doesn’t share the files of activities it got from Strava. For files you already have from anywhere else, the `folder` connector reads any folder, or you can drop them in the inbox. See [Pulling from intervals.icu](guides/connectors.md).

**Does it upload anything?**
No. fitdocs makes network requests in only two cases: map tiles, which only reveal your approximate location, are cached, and can be turned off; and a connector you set up, which only reads from your own account. See [Privacy and the network](guides/privacy-and-network.md).

**Do I need an LLM?**
No. fitdocs is a normal command-line tool, and the pages are readable on their own. It's designed to work *well* with an LLM, with any provider or a local model. See [Working with an LLM](llm/index.md).

**I record the same run on my watch and with HealthFit or Stryd. Will I get two pages?**
Usually not. Files of the same workout share one page, built from the best file, with anything it lacks, like Stryd's running dynamics, filled in from the others. If you had pages before fitdocs 0.2, run `fitdocs regen` first so they're recognized. See [Several files, one workout](guides/workout-pages.md#several-files-one-workout).

**Can I ask questions across all my workouts?**
Yes. `fitdocs index` builds a local DuckDB database of your whole training log, and `fitdocs query` runs SQL against it. Your LLM can write the SQL for you, and [dashboards](guides/dashboards.md) turn a query into a chart that stays up to date. See [The analytics index](guides/analytics.md).

**Does fitdocs tell me whether I'm ready to train?**
No. It shows your HRV, resting heart rate, and sleep next to your own recent normal, but it never gives a readiness score or tells you what to do. See [Wellness and recovery](guides/wellness.md).

**Does it work with Obsidian?**
Yes. Point it at your vault (or a folder inside it). Pages use standard frontmatter and ordinary image links, so charts show up without a plugin and Dataview or Bases can query them.

**Can I edit the generated pages?**
You can edit the parts that are yours: the **Notes** section, the **Workout** section on strength pages, and the race-tag frontmatter keys. Those are kept through every rebuild. Everything else is rebuilt from the archived `.fit` files and your wellness data, so edits there won't last. Dashboard pages are yours too, apart from the charts fitdocs draws on them. See [Your workout pages](guides/workout-pages.md).

**Why doesn't my swim, strength session, or yoga have a training load?**
The built-in calculator scores running, cycling, walking, and hiking. For other sports it leaves the load blank and says so, rather than inventing a number. Other methods can be added as [plugins](extend/load-calculators.md).

**Why does my run say "not computed"?**
The calculator needs thresholds that applied on that date, such as threshold pace, FTP, or heart-rate values. Run `fitdocs load` and answer the prompts, or [tag your races](guides/benchmarks.md) and let fitdocs derive them.

**Will my numbers match intervals.icu, TrainingPeaks, or Garmin?**
They'll be close, and they're built to be comparable. fitdocs uses the same families of methods (TSS from power, TRIMP/HRSS from heart rate, grade-adjusted pace) on the same "one hour at threshold = 100" scale. Exact numbers depend on your thresholds and each platform's details.

**What happens to my data if I stop using fitdocs?**
Nothing. It's a folder of markdown, SVG, CSV, and your original `.fit` and wellness files. Uninstalling removes the tool and leaves every file where it is. The analytics index is only a cache outside that folder, safe to delete.

**Can I run it on a schedule?**
Yes. fitdocs doesn't schedule anything itself, but `fitdocs sync --no-prompt` (or `fitdocs pull --sync --no-prompt`, if you use a connector) is safe to run from cron, launchd, or your LLM agent's daily routine.

**Is it free?**
Yes. It's open source under the MIT license.

**How do I report a bug or ask a question?**
[GitHub Issues](https://github.com/joshua-stauffer/fitdocs/issues).
