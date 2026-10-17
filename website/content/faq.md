---
title: FAQ
description: Short answers about devices, platforms, privacy, LLMs, Obsidian, and what fitdocs isn't.
section: Project
order: 3
---

# FAQ

**Which devices does it work with?**
Anything that records a `.fit` file, which covers most Garmin, Coros, Wahoo, Suunto, Hammerhead, and Stryd devices, plus Zwift and the Apple Watch (exported through an app like HealthFit). GPX and TCX aren't supported. When tested, they carried nothing a `.fit` file doesn't.

**Does it download my activities from Garmin or Strava?**
No. Both Garmin and Strava have adopted increasingly unfriendly API terms, and fitdocs doesn’t read directly from either of them. We recommend syncing your data through intervals.icu. It’s free, community-supported, developer friendly, and supports syncing with most major fitness hardware. Once the data is in intervals.icu, use the fitdocs connector to sync it directly into your wiki. You can also write your own connector to integrate directly with any source you’d like, as long as you follow their TOS.

**Does it upload anything?**
No. The only network requests are for map tiles, which only reveal your approximate location, are cached, and can be turned off. See [Privacy and the network](guides/privacy-and-network.md).

**Do I need an LLM?**
No. fitdocs is a normal command-line tool, and the pages are readable on their own. It's designed to work *well* with an LLM, with any provider or a local model. See [Working with an LLM](llm/index.md).

**Does it work with Obsidian?**
Yes. Point it at your vault (or a folder inside it). Pages use standard frontmatter and ordinary image links, so charts show up and Dataview or Bases can query them. No plugin needed.

**Can I edit the generated pages?**
You can edit the parts that are yours: the **Notes** section, the **Workout** section on strength pages, and the race-tag frontmatter keys. Those are kept through every rebuild. Everything else is rebuilt from the archived `.fit` file, so edits there won't last. See [Your workout pages](guides/workout-pages.md).

**Why doesn't my swim, strength session, or yoga have a training load?**
The built-in calculator scores running, cycling, walking, and hiking. For other sports it leaves the load blank and says so, rather than inventing a number. Other methods can be added as [plugins](extend/load-calculators.md).

**Why does my run say "not computed"?**
The calculator needs thresholds that applied on that date, such as threshold pace, FTP, or heart-rate values. Run `fitdocs load` and answer the prompts, or [tag your races](guides/benchmarks.md) and let fitdocs derive them.

**Will my numbers match intervals.icu, TrainingPeaks, or Garmin?**
They'll be close, and they're built to be comparable. fitdocs uses the same families of methods (TSS from power, TRIMP/HRSS from heart rate, grade-adjusted pace) on the same "one hour at threshold = 100" scale. Exact numbers depend on your thresholds and each platform's details.

**What happens to my data if I stop using fitdocs?**
Nothing. It's a folder of markdown, SVG, and your original `.fit` files. Uninstalling removes the tool and leaves every file where it is.

**Can I run it on a schedule?**
Yes. fitdocs doesn't schedule anything itself, but `fitdocs sync --no-prompt` is safe to run from cron, launchd, or your LLM agent's daily routine.

**Is it free?**
Yes. It's open source under the MIT license.

**How do I report a bug or ask a question?**
[GitHub Issues](https://github.com/joshua-stauffer/fitdocs/issues).
