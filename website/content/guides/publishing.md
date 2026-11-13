---
title: Publishing posts
description: Turn a workout page into a post with `fitdocs publish`. Opt the page in, write its post or let a template write it, preview it, and send it.
section: Guides
order: 13
---

# Publishing posts

Fitdocs can turn a workout page into a post, which is a title and a description, and send it to a publish target. A target is a [connector](connectors.md) instance that can publish. The connectors guide says which connectors can.

A page is posted only to the targets its `publish` key names, and only when you run `fitdocs publish --yes`.

```sh
fitdocs publish --targets   # which targets are configured, and whether each is ready
fitdocs publish             # dry run: shows what would be posted
fitdocs publish --yes       # posts it
```

## Opt a page in

Add the `publish` key to a page’s frontmatter, with one target name or a list of names. A target’s name is the name in its `[connectors.<name>]` table.

```yaml
publish: club-feed
```

```yaml
publish: [club-feed, team-log]
```

Fitdocs keeps the key when it rebuilds the page.

If you take a target out of a page’s `publish` key, fitdocs stops posting to it and doesn’t delete the post already there.

## Preview it

`fitdocs publish` is a dry run. It prints what each page would post to each target it opts in to.

```text
fitdocs publish: dry run; nothing is sent (add --yes to post).
workouts/2026-10-28-run.md -> club-feed: value_missing (load_value)
workouts/2026-10-29-ride.md -> club-feed: unchanged
workouts/2026-10-30-run-1.md -> club-feed: would_post
  title: Morning Run
  description:
    Distance: 12.50 km
    Time: 58:20
1 would_post, 1 unchanged, 1 value_missing; 2 pages opted in to no selected target.

would_post: This page has no post on this target yet, and `fitdocs publish --yes` would post it.
unchanged: This target already carries this page's current post, so nothing is sent.
value_missing: A placeholder outside an optional clause has no value on this page, so nothing is sent.
```

Name pages to look at only those, by file name or path, and add `--to club-feed` to consider only that target. Repeat `--to` to name several.

## Write your own post

A workout page has a `post` region that’s yours. To give a page its own post, write the title on one line, then a blank line, then the description:

```markdown
<!-- fitdocs:begin:post -->
{title}: a day I wanted to run

Felt strong from the first kilometre.
{?Average heart rate: {avg_hr_bpm} bpm}
<!-- fitdocs:end:post -->
```

The same words go to every target the page opts in to. Fitdocs writes in this region only when a [post template](#fill-posts-from-a-post-template) fills it.

## Or use a publish template

With nothing in the `post` region, the post comes from a publish template. The built-in one uses the page’s title, then writes one line for each of distance, time, pace, speed, average heart rate, average power, and elevation gain, leaving out any the page doesn’t record:

```text
Morning Run

Distance: 12.50 km
Time: 58:20
Pace: 4:40 /km
Average heart rate: 149 bpm
Average power: 231 W
Elevation gain: 88 m
```

To change it, set `[publish]` in `fitdocs.toml`. For each field, `[publish.targets.<name>]` comes first, then `[publish]`, then the built-in template.

```toml
[publish]
title = "{title}{? - {distance_km} km}"
description = '''
{?Distance: {distance_km} km
}{?Time: {moving_time}
}'''

[publish.targets.club-feed]
description = "{?Load: {load_value} ({load_methodology})}"
```

Templates, and the text in a `post` region, can hold three things besides plain words:

- `{name}` is a placeholder, filled from the page.
- `{?...}` is an optional clause. Its text appears only when every placeholder inside it has a value.
- `{{` and `}}` are a literal `{` and `}`.

A placeholder outside a clause with no value on the page keeps that page from being posted to that target.

The placeholders are `title`, `sport`, `date`, `start_time`, `distance_km`, `distance_mi`, `moving_time`, `elapsed_time`, `pace_per_km`, `pace_per_mi`, `speed_kmh`, `avg_hr_bpm`, `avg_power_w`, `elevation_gain_m`, `calories_kcal`, `load_value`, and `load_methodology`. The [publishing reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md#placeholders) gives each one’s format and when it has no value.

## Fill posts from a post template

A post template writes each new page’s post. It can include numbers the page doesn’t hold, like this workout’s load in the week so far, because its variables are SQL over the [analytics index](analytics.md).

Build the index once with `fitdocs index`, then write `post-template.toml` at the top of your data root:

```toml
since = 2026-11-08

title = "{title}"
description = '''
{?{week_load} load so far this week.}
'''

[vars.week_load]
sql = '''
SELECT round(sum(load_value))::INT
FROM pages
WHERE load_methodology = 'threshold'
  AND date >= date_trunc('week', $as_of)
  AND start_time_local <= $as_of
'''
```

- **Set `since` to the day you create the file.** Only pages dated on or after it are filled. With a date in the past, the next sync fills every page since then that hasn’t been posted.
- `title` and `description` use the same placeholders and clauses as the templates above, plus the variables you declare under `vars`.
- Each variable is one `SELECT` that `fitdocs query` would accept, and it must use `$as_of`, the workout’s recorded start. Use it to look only at what existed when the workout began. `$page_key` names the page in the index.
- A query with no rows, or a NULL, has no value. Cast decimals, as the example does with `::INT`.

From then on, `fitdocs sync` and `fitdocs pull --sync` fill the `post` region of each page they create, and `fitdocs publish` sends that text as it would send words you wrote. A filled post stays as it is through later workouts, a rebuilt index, `fitdocs regen`, or a change to the template.

Fitdocs writes a `post` region only until you edit it. To hand a page back to the template, empty its `post` region.

Two commands check and redo the work:

```sh
fitdocs post-template check            # problems in the file or its SQL, and how many pages the next sync would fill
fitdocs post-template check PAGE       # one page: its state, each variable's value, and the post it would get
fitdocs post-template refill           # dry run: what a refill would change
fitdocs post-template refill --yes     # recompute the posts
```

A bare `refill` recomputes the post of every unposted page dated on or after `since` that you haven’t edited. Naming a page refills it even if it’s been posted.

The [post templates reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md#post-templates) has the full rules for values, the checks on each query, and every exit code.

## Send it

For each page and target, `fitdocs publish --yes` posts for the first time, updates an earlier post whose title or description changed, or does nothing if the post is unchanged. Add `--format json` for one JSON document instead of text.

## What fitdocs records

When a post lands, its link goes in the page’s `published` region, near the top of the page, above Notes:

```markdown
Published: [Club feed](https://example.invalid/a/1) · [Team log](https://example.invalid/b/2)
```

Fitdocs owns that region, so a hand edit is replaced the next time `fitdocs publish --yes` considers the page.

Each target also keeps a record at `.fitdocs/publish/<target>.toml` of what landed and where. Don’t edit it. If you delete it, the next `--yes` run treats every page that opts in to that target as never posted and sends the posts again.

The [publishing reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md) has every code, the rules for links, and the record’s format.
