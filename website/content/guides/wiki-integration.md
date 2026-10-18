---
title: Inside your wiki or vault
description: Point fitdocs at a markdown knowledge base you already keep (Obsidian, a git wiki, an LLM-maintained second brain) and install the agent skills.
section: Guides
order: 11
---

# Inside your wiki or vault

fitdocs works well on its own, but it was designed to live inside a larger markdown knowledge base, so your training sits next to your journal, your projects, and everything else you think about. Workout pages become ordinary pages in your wiki. You can link to them, search them, and query them together with the rest of your notes.

## How it stays out of your way

- **It only writes to its own folders:** `workouts/`, `fit-archive/`, `history/`, `blocks/`, `recovery/`, `wellness/`, `wellness-archive/`, and its hidden `.cache/` and `.fitdocs/`. In `dashboards/` it writes only `AGENTS.md`, the chart images and snapshots in `dashboards/assets/`, and the charts on the pages you create there. It also writes to the inbox and processed folder your settings name. Nothing else in your wiki is touched.
- **Some things live outside your wiki on purpose.** The [analytics index](analytics.md) is a disposable cache in your user’s cache folder, and connector keys are kept in your user’s config folder, so neither ends up in your notes or their git history.
- **Your notes can point at fitdocs; fitdocs never points back.** Link from your daily note to `[[2026-09-16-run-1132]]` as much as you like. fitdocs never reads or links to your other pages, apart from the dashboard pages you write for it. If fitdocs renames a page, links to its old name aren’t updated (see [When a page is renamed](workout-pages.md#when-a-page-is-renamed)).

## Setup: five steps

Run these from the root of your wiki.

**1. Install fitdocs** ([Install](../getting-started/install.md)).

**2. Make the wiki the data root.**

```sh
mkdir -p .fitdocs
echo "$(pwd)" > .fitdocs/data-root
```

Now any `fitdocs` command run from inside the wiki finds it.

**3. Configure the inbox.** Accept the default `inbox/`, or point at the folder where your sync app already drops files:

```sh
cat > fitdocs.toml <<'EOF'
[inbox]
# path = "/path/to/HealthFit/export/folder"
EOF
```

(Add `[tiles]` with `enabled = false` if you want no network access at all. See [Privacy](privacy-and-network.md).)

**4. Install the agent skills** (next section).

**5. First sync and check.**

```sh
fitdocs sync --no-prompt
fitdocs index          # build the analytics index once
fitdocs check          # exits 0 when everything is in order
```

## Agent skills

fitdocs includes agent skills: markdown instruction files in the open [SKILL.md](https://agentskills.io) format that tell an LLM agent how to operate fitdocs correctly. They ship inside the package, so they always match the version you have installed.

| Skill | What it teaches your agent |
|---|---|
| **`fitdocs-workouts`** | Pull from your [connectors](connectors.md), drain the inbox, run `check`, read the reports, and know what to do about deferred, quarantined, or failed files. It also knows *not* to run `regen` unless asked, and to leave quarantined files to you. |
| **`fitdocs-analytics`** | Answer counts, totals, and trends from the [analytics index](analytics.md) with read-only SQL, check that the index is current first, and show you the query behind each answer. |
| **`fitdocs-dashboards`** | Put an answer on a [dashboard](dashboards.md) page as a chart, check the page until it's clean, and keep your prose apart from fitdocs's charts. |
| **`build-training-block`** | Interview you about a training block, write the plan file, render it, add amendments, and settle ambiguous matches ([Training blocks](training-blocks.md)). |

**Find them:**

```sh
fitdocs skill                       # list packaged skills and where they're installed
fitdocs skill fitdocs-workouts      # print one skill's folder and a copy command
```

**Install:** copy or symlink each skill's folder into your agent's skills directory, keeping the skill's own name. Each agent looks in a different place, so check your agent's documentation for its skills directory (for example `.claude/skills/` in a Claude Code project).

```sh
# Symlink: picks up new versions automatically when you upgrade fitdocs
ln -s "$(fitdocs skill fitdocs-workouts | head -n1)" <skills-dir>/fitdocs-workouts

# Or copy (after an upgrade, delete the old copy and copy again)
cp -R "$(fitdocs skill fitdocs-workouts | head -n1)" <skills-dir>/fitdocs-workouts
```

To link all four at once:

```sh
for name in fitdocs-workouts fitdocs-analytics fitdocs-dashboards build-training-block; do
  ln -s "$(fitdocs skill "$name" | head -n1)" "<skills-dir>/$name"
done
```

**Check:** ask your agent to list its skills. All four should appear. Each copied `SKILL.md` has a `metadata.version` showing which fitdocs release it came from.

## Point your wiki's own instructions at fitdocs

If your wiki has its own root `AGENTS.md` or `CLAUDE.md`, a short pointer is enough. You don't need to copy the rules:

```markdown
## Workouts (fitdocs)
Training data is generated by fitdocs. See `workouts/AGENTS.md`,
`fit-archive/AGENTS.md`, `history/AGENTS.md`, `blocks/AGENTS.md`,
`dashboards/AGENTS.md`, `wellness/AGENTS.md`, `wellness-archive/AGENTS.md`,
and `recovery/AGENTS.md` for what it owns. Never edit generated content; the
Notes and Workout sections of a workout page, the race-tag frontmatter keys,
and dashboard pages outside their chart regions are the user's.
```

fitdocs keeps those eight files up to date. It never touches your root instructions file.

## If your wiki is in git

The generated pages and archive can make diffs noisy. You can mark them as generated in `.gitattributes` so git and GitHub collapse them:

```
workouts/*.md linguist-generated
fit-archive/* linguist-generated -diff
history/*.md linguist-generated
history/assets/* linguist-generated -diff
blocks/*.md linguist-generated
blocks/*/*.md linguist-generated
recovery/*.md linguist-generated
recovery/assets/* linguist-generated -diff
wellness/* linguist-generated
wellness-archive/** linguist-generated -diff
```

The heavy folders (`fit-archive/`, `wellness-archive/`, chart assets, `.cache/`) can also be left out of git entirely, since `fitdocs regen` can rebuild every workout page from the archives. Then `fitdocs index`, `fitdocs recovery`, and `fitdocs dashboard refresh` redraw the rest. Just make sure both archives are backed up somewhere. Keep your dashboard pages and their snapshot files (`dashboards/assets/**/*.snapshot-*.json`) in git, though: a snapshot is the only copy of the rows a frozen chart was drawn from.

## Obsidian

Nothing special is needed. Open the vault, and workout pages show up with their charts, because they're standard image links. The frontmatter works with Dataview and Bases. Wikilinks in `effort_event` show up as normal links. On a dashboard page, Live Preview shows each chart directive as dimmed source text above its chart. That's expected.
