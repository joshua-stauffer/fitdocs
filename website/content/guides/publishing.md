---
title: Publishing posts
description: Turn a workout page into a post with `fitdocs publish`. Opt the page in, write its post or let a template write it, preview it, and send it.
section: Guides
order: 13
---

# Publishing posts

Fitdocs can turn a workout page into a post, which is a title and a description, and send it to a publish target. A target is a [connector](connectors.md) instance that can publish. The connectors guide says which connectors can, and how each one finds the activity it updates.

A page is posted only to the targets its `publish` key names, and only when you run `fitdocs publish --yes`.

```sh
fitdocs publish --targets   # which targets are configured, and whether each is ready
fitdocs publish             # dry run: shows what would be posted
fitdocs publish --yes       # posts it
```

A page written by an older fitdocs that opts in to a target reports `page_out_of_date`, and nothing is sent from it. Run `fitdocs regen` to bring it up to date.

## Opt a page in

Add the `publish` key to a page’s frontmatter, with one target name or a list of names. A target’s name is the name in its `[connectors.<name>]` table.

```yaml
publish: club-feed
```

```yaml
publish: [club-feed, team-log]
```

Fitdocs never writes the key, and keeps its line through every rebuild. An empty list opts the page in to nothing.

If a page stops naming a target it was posted to, fitdocs sends nothing more for it, deletes nothing at the target, and keeps the link on the page.

## Preview it

`fitdocs publish` sends no request and writes nothing. It prints a line for each page and each target it opts in to, the text it would send, and an explanation of each code it printed:

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

A workout page has a `post` region that’s yours. A fresh one holds a hidden comment that renders as nothing. To give a page its own post, write the title on one line, then a blank line, then the description:

```markdown
<!-- fitdocs:begin:post -->
{title}: a day I wanted to run

Felt strong from the first kilometre.
{?Average heart rate: {avg_hr_bpm} bpm}
<!-- fitdocs:end:post -->
```

A region with only a title line posts an empty description. A second line that isn’t blank reports `post_invalid`. Hidden comments aren’t posted. The same words go to every target the page opts in to. Fitdocs writes in this region only when a [post template](#fill-posts-from-a-post-template) fills it.

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

A placeholder outside a clause with no value on the page reports `value_missing`, and nothing is posted from that page to that target. Fitdocs never fills in an absent value with a `0` or an empty string. A value the page records as zero is written as zero.

The placeholders are `title`, `sport`, `date`, `start_time`, `distance_km`, `distance_mi`, `moving_time`, `elapsed_time`, `pace_per_km`, `pace_per_mi`, `speed_kmh`, `avg_hr_bpm`, `avg_power_w`, `elevation_gain_m`, `calories_kcal`, `load_value`, and `load_methodology`. The [publishing reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md#placeholders) gives each one’s format and when it has no value.

A mistake in `[publish]` stops `fitdocs publish` with exit code 2 before anything is sent or written. The message names the table and the key.

## Fill posts from a post template

A post template writes each new page’s post. It can include numbers the page doesn’t hold, like this workout’s load in the week so far, because its variables are SQL over the [analytics index](analytics.md). Without the file, nothing in this section applies.

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
- A query with no rows, or a NULL, has no value. An optional clause that needs it is dropped, and a variable outside a clause with no value leaves the page unfilled. Cast decimals, as the example does with `::INT`.

Fitdocs doesn’t write to this file.

From then on, `fitdocs sync` and `fitdocs pull --sync` fill the `post` region of each page they create, and `fitdocs publish` sends that text as it would send words you wrote. A filled post stays as it is through later workouts, a rebuilt index, `fitdocs regen`, or a change to the template.

Fitdocs writes only a region that’s waiting (empty, or holding just its own hidden comments) or one it filled that you haven’t touched. Once you edit it, fitdocs leaves it alone. To hand a page back to the template, empty its `post` region.

Two commands check and redo the work:

```sh
fitdocs post-template check            # problems in the file or its SQL, and how many pages the next sync would fill
fitdocs post-template check PAGE       # one page: its state, each variable's value, and the post it would get
fitdocs post-template refill           # dry run: what a refill would change
fitdocs post-template refill --yes     # recompute the posts
```

A bare `refill` takes every unposted page dated on or after `since` that is waiting or filled, and leaves published pages alone. Naming a page refills it even if it’s been posted, and the report tells you when publishing it again would update the target.

With a template in place, `fitdocs publish` sends nothing for an opted-in page still waiting for its post, rather than the default template, and reports `post_waiting`. Run `fitdocs sync` to fill it, `fitdocs post-template check PAGE` to see why it wasn’t filled, or write the post yourself.

The [post templates reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md#post-templates) has the full rules for values, the checks on each query, and every exit code.

## Send it

`fitdocs publish --yes` works through the pages in file-name order. For each page and target it posts for the first time, updates an earlier post whose title or description changed, or does nothing if the post is unchanged. A post that didn’t land is tried again on the next run.

Each result is one code. `posted` and `uploaded` mean the post landed, and a link is shown with them when the target gave a usable one. When a result like `rate_limited` or `auth_rejected` stops a target, the rest of that target’s posts in the run are `not_attempted`, and other targets carry on. `unconfirmed` means a request was sent but its result isn’t known, so the next run checks the target before sending again.

The command exits `0` when no result is a failure, `1` when one is, and `2` for a configuration error found before any request or write. If you interrupt it, it stops sending, keeps every outcome it already received, and exits `130`. Add `--format json` for one JSON document instead of text.

## What fitdocs records

When a post lands, its link goes in the page’s `published` region, near the top of the page, above Notes:

```markdown
Published: [Club feed](https://example.invalid/a/1) · [Team log](https://example.invalid/b/2)
```

Fitdocs owns that region, so a hand edit is replaced the next time `fitdocs publish --yes` considers the page. A posting run writes nothing else on a page.

Each target also keeps a record at `.fitdocs/publish/<target>.toml` of what landed and where, so a later run knows what changed. Don’t edit it. If you delete it, the next `--yes` run treats every page that opts in to that target as never posted and sends the posts again. A target looks for an existing activity before it creates one, so it’s expected to find the earlier activity rather than make a second.

Beyond the code and the link, fitdocs doesn’t print or write anything a target returns.

The [publishing reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md) has every code, the rules for links, and the record’s format.
