---
title: Publishing posts
description: Turn a workout page into a post with `fitdocs publish`. Opt the page in, write the post or use a template, preview it, and send it to the targets you configured.
section: Guides
order: 13
---

# Publishing posts

Fitdocs can turn a workout page into a post, which is a title and a description, and send it to a publish target. A target is a [connector](connectors.md) instance that can publish. The connectors guide says which connectors can, and how each one finds the activity it updates.

A target exists only if you configured it, a page is posted to a target only if the page’s `publish` key names it, and nothing is sent unless you run `fitdocs publish --yes`.

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

The key is yours. Fitdocs never writes it, and keeps its line through every rebuild. A page with no `publish` key, or an empty list, is posted nowhere.

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

A region with only a title line posts an empty description. A second line that isn’t blank reports `post_invalid`. Hidden comments are removed and never posted. The same words go to every target the page opts in to, and fitdocs never changes this region.

## Or use a template

With nothing in the `post` region, the post comes from a template. The built-in one uses the page’s title, then writes one line for each of distance, time, pace, speed, average heart rate, average power, and elevation gain, leaving out any the page doesn’t record:

```text
Morning Run

Distance: 12.50 km
Time: 58:20
Pace: 4:40 /km
Average heart rate: 149 bpm
Average power: 231 W
Elevation gain: 88 m
```

To change it, set `[publish]` in `fitdocs.toml`. For each field, a target’s own table comes first, then `[publish]`, then the built-in template.

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

A mistake in `[publish]` stops every `fitdocs publish` run with exit code 2, before any request and before any write. The message names the table and the key.

## Send it

`fitdocs publish --yes` works through the pages in file-name order. For each page and target it posts for the first time, updates an earlier post whose title or description changed, or does nothing because the post is unchanged. So a second run with nothing changed sends nothing, and a post that didn’t land is tried again on the next run.

Each result is one code, and the report explains each code it prints. `posted` and `uploaded` mean the post landed, and a link is shown with them when the target gave a usable one. When a result like `rate_limited` or `auth_rejected` stops a target, the rest of that target’s posts in the run are `not_attempted`, and other targets carry on. `unconfirmed` means a request was sent but its result isn’t known, so the next run checks the target before sending again.

The command exits `0` when no result is a failure, `1` when one is, and `2` for a configuration error found before any request or write. If you interrupt it, it stops sending, keeps every outcome it already received, and exits `130`. Add `--format json` for one JSON document instead of text.

## What fitdocs records

When a post lands, its link goes in the page’s `published` region, near the top of the page, above Notes:

```markdown
Published: [Club feed](https://example.invalid/a/1) · [Team log](https://example.invalid/b/2)
```

Fitdocs owns that region, so a hand edit is replaced the next time `fitdocs publish --yes` considers the page. A posting run writes nothing else on a page.

Each target also has a ledger at `.fitdocs/publish/<target>.toml`, which records what landed and where, so a later run knows what changed. Don’t edit it. If you delete a ledger, the next `--yes` run treats every page that opts in to that target as never posted and sends the posts again. A target looks for an existing activity before it creates one, so it’s expected to find the earlier activity rather than make a second.

A target’s answer becomes one code and, for a post that landed, one link. Fitdocs doesn’t print or write anything else a target returns.

The [publishing reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md) has every code, the rules for links, and the ledger’s format.
