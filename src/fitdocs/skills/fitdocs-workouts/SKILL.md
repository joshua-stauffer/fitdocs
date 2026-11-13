---
name: fitdocs-workouts
description: Pulls new .fit files from the athlete's configured connectors and drains the inbox into workout documents, then reads the resulting pull and drain reports. Use when new .fit files have arrived, or when the wiki's workouts look stale and a fresh sync is due.
license: MIT
compatibility: Requires the fitdocs command to be installed and on the agent's path.
metadata:
  version: 0.3.0
---

# Process the fitdocs inbox

## When this applies

- New `.fit` files have arrived in the configured inbox, however they got
  there -- a configured connector's pull, a watch export, a manual drop,
  another tool's script.
- The wiki's workouts look stale: no recent workout documents exist even
  though the athlete has presumably been training.
- The athlete asks to preview or publish a workout's post -- the title and
  description fitdocs composes from a workout page for the athlete's
  publish targets.

## Commands to run

Run, routinely, in this order:

1. `fitdocs pull --sync --no-prompt` -- fetches new activities from every
   configured connector instance, delivers them into the inbox, and then
   drains the inbox exactly as `fitdocs sync` would (admitting, writing,
   computing load, reconciling). `--no-prompt` keeps an unattended agent
   from ever blocking on a training-load prompt (it has the same effect
   stdin being a non-terminal already has for an unattended run; pass it
   explicitly rather than relying on that); any document the load pass
   would otherwise have prompted for is simply left uncomputed. With no
   connectors configured, this is exactly `fitdocs sync --no-prompt` --
   there is nothing to fetch, so the inbox drain is the whole of it. Run
   `fitdocs sync --no-prompt --retry-quarantined` instead, only when the
   user has asked you to re-attempt files already recorded as quarantined
   -- never on your own initiative (see Quarantined below). Never run
   `fitdocs connect`: it asks the athlete for secrets at a terminal, and an
   agent must never run it.
   Never run `fitdocs disconnect` either: it deletes an instance's stored
   credentials, which only the athlete can restore by connecting again, and
   for a relay instance it first revokes the token at the relay, which
   cannot be undone.
2. `fitdocs check` -- confirms the data root still matches the installed
   contract. Run it after a pull-and-drain to confirm the tree is healthy,
   or any time you want to check the tree without draining anything.

```bash
fitdocs pull --sync --no-prompt
fitdocs check
```

Run `fitdocs regen` separately, and only when it is actually called for --
either `fitdocs check` reported a document whose remedy reads "run
`fitdocs regen` to bring it to the current format", or a fitdocs upgrade's
release notes say the generated-document format changed. Never run it as
part of the routine pair above, and never run it speculatively.

```bash
fitdocs regen
```

Run `fitdocs recovery` after the routine pair when the drain report's
`Wellness archived` count is above zero or it printed a wellness series
summary, or when the athlete asks for the recovery page. Never run it
as part of the routine pair. See
[the recovery guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/recovery.md).

```bash
fitdocs recovery
```

## Reading the report

`fitdocs pull` prints, per configured instance, a counts table headed by
that instance's name and connector id. The row for how many items were
`listed` is a cross-cutting count, not a channel of its own; every listed
item lands in at most one of the channels below -- if the instance's pull
ends in an `error` partway through, the items it had not reached yet land
in none.

| Pull channel | Field | Meaning | Do |
|---------------|-------|---------|----|
| Delivered | `delivered` | A new activity was fetched from the connector and written into the inbox for the drain to admit. | Nothing needed -- the chained `--sync` drain already admitted it; on a plain `fitdocs pull` (no `--sync`), the next `fitdocs sync` will. |
| Would fetch | `would_fetch` | Non-empty only under `--dry-run` -- the routine above never passes it, so expect this empty. | Nothing needed in the routine above. |
| Already held | `held` | The item is already recorded as a final outcome in this instance's ledger, its bytes are already archived, or it is identical to this instance's delivery still waiting in the inbox -- nothing to fetch again. | Nothing needed. |
| Skipped | `skipped` | The item was recognized but not delivered, for a reason the report names (for example, the connector declines an activity, or its original file is unavailable, or the fetched bytes are not a FIT file). | Read the detail; nothing further needed -- it is not retried. |
| Deferred | `deferred` | The item could not be listed or fetched yet for a reason expected to resolve on its own (for example, a rate limit), or -- subject an inbox path rather than a remote id -- an earlier delivery that could not be removed from the inbox yet. | No action -- it is reconsidered automatically on the next pull. |
| Failed | `failed` | The item was listed but fetching it failed for a reason the report names, or the listing entry itself was malformed; the instance's pull continues. | Read the message; report it to the user if it recurs -- it is retried automatically on the next pull. |
| Removed | `removed` | An inbox-relative path, delivered by this instance on an earlier pull and now archived (hash-identical), that this pull's sweep removed from the inbox. Only this instance's own archived deliveries are ever removed -- never a hand-dropped file, other than an exact copy of a still-pending delivery placed at that delivery's own path, which is indistinguishable from it. | Nothing needed -- routine cleanup. |
| Error | `error` | This instance's pull ended early -- either before fetching anything (no credentials, rejected credentials, a rate-limited sign-in, an unreadable ledger, a permissive credentials file, a failed listing, or a missing source) or partway through (an authentication failure on a fetch; anything already delivered stays delivered). Other instances still ran. | Read the printed next step and report it to the user -- never run `fitdocs connect` yourself (it needs an interactive terminal the agent cannot use), and never retry on your own judgment. |

An instance with wellness enabled also prints a wellness table after its
activity report. Days listed is a cross-cutting count, not a channel. The
wellness channels describe days and delivered files separately; notices
annotate attribution changes rather than replacing a day's outcome.

| Wellness channel | Field | Meaning | Do |
|------------------|-------|---------|----|
| Days unchanged | `unchanged` | Listed days whose revision is already recorded in this instance's ledger. | Nothing needed. |
| Delivered | `delivered` | A wellness file holding new or changed days was written into the inbox. | Nothing needed -- the chained `--sync` drain admits it; on a plain pull, the next `fitdocs sync` will. |
| Would deliver | `would_deliver` | Under `--dry-run`, dates that would be packaged and delivered. | Nothing needed in the routine above. |
| Already held | `held` | A wellness package's identical bytes are already archived or still pending in this instance's inbox delivery. | Nothing needed. |
| Failed | `failed` | A listed day was malformed, or packaging, package validation or delivery failed for the reason printed; other years can still be delivered. | Read the reason and tell the athlete if it recurs; the next pull retries it. |
| Notices | `notices` | A platform previously attributed to this instance's wellness is no longer attributed. | Tell the athlete that a platform's attribution vanished; that platform's own export can fill the gap. |
| Error | `error` | This instance's wellness pull ended early; work already delivered stays delivered. | Report the printed next step to the athlete; never edit `fitdocs.toml` and never set `wellness = false` yourself. |

`fitdocs sync`'s own drain (chained here by `--sync`, or run directly by
`fitdocs sync`) prints an inbox path followed by twelve report rows. Workout
FIT outcomes use written / skipped / failed; warnings annotate those
outcomes. Wellness intake uses unrecognized / wellness archived / wellness
skipped / wellness failed. Deferred and quarantined apply to both kinds of
input. Moved and move-failures additionally describe eligible archived
inputs relocated out of the inbox. A changed wellness series adds its own
status and value-count summary after the table.

| Channel | Field | Meaning | Do |
|---------|-------|---------|----|
| Written | `written` | A workout document was produced or updated from an admitted file. | Nothing needed. |
| Skipped | `skipped` | The workout bytes were already archived, a newer-format page was left untouched, the file was held for an ambiguous match, or a declared non-activity FIT type was skipped with a warning. | Nothing needed for the already-archived case; for the newer-format case, nothing to do now -- it is retried automatically on a later run. |
| Failed | `failures` | The file could not be processed for a reason the report names. | Read the message; fix the source file if you can, or report the reason to the user. |
| Warnings | `warnings` | A non-fatal condition annotated alongside an admitted file's written/skipped/failed outcome -- never its own outcome, and never changes which of the three the file landed in. | Read it; it usually needs nothing further. |
| Deferred | `deferred` | The file was not yet observed stable across the settle interval, or a stable file could not be read -- left completely untouched either way. | No action -- it is reconsidered automatically on the next drain. |
| Quarantined | `quarantined` | The file previously failed for a source-level reason and is remembered rather than retried. | This needs the user, not the agent -- never retry a quarantined file on your own judgment. |
| Moved | `moved` | An eligible archived workout or wellness source was additionally relocated out of the inbox (only when disposition is configured to move files). | Nothing needed. |
| Move failures | `move_failures` | The file was processed successfully -- its content is already archived, counted as written or skipped for FIT, or archived or skipped for wellness -- but relocating it out of the inbox afterward failed. | Nothing to do: the file stays in the inbox and the move is retried automatically on the next drain. This is never a reason to reprocess the file. |
| Unrecognized | `unrecognized` | No supported wellness format recognized the `.json`, `.zip` or `.xml` file; it stays in the inbox. | Tell the user the reason; ask them to supply a supported export or add the unwanted file to `[inbox] ignore`. Never delete the file. |
| Wellness archived | `wellness_archived` | A wellness file was successfully parsed and archived. | Nothing needed; the daily series is rebuilt after wellness intake. |
| Wellness skipped | `wellness_skipped` | The wellness file's content is already archived. | Nothing needed; the archive already holds this content. |
| Wellness failed | `wellness_failures` | A wellness file could not be parsed and its content was quarantined. | Tell the user the reason and ask them to correct the export; retry the same quarantined content only with their direction. Never delete the file. |

`Morning of:` lines follow the drain report.
`Morning of: 1 page updated, 1 block removed.` means blocks were
refreshed, or cleared when their wellness figures disappeared;
no athlete action is needed. Counts use singular or plural, and a
zero-count clause is omitted.
`Morning of: could not update <doc>: <detail>` means that page could
not be refreshed: read the reason and tell the athlete; damaged
markers need a human.
`Morning of: 1 page has no morning-of region (written by an older fitdocs, or the region markers were removed); run 'fitdocs regen' to add it.`
(or `2 pages have` for two) means a region is missing.
Run `fitdocs regen` only when `fitdocs check` or the release notes
call for it; never run it as part of the routine pair.
`Morning of: not refreshed; the wellness series could not be read: <reason>.`
means the series was unavailable.
`Morning of: not refreshed; <ExceptionType>: <message>.` means the
pass raised an error. Neither `not refreshed` line needs athlete
action; the next run retries.

**Wellness in `fitdocs check`.** For `wellness_series_stale`, run `fitdocs
sync` to rebuild; if the remedy names invalid settings, tell the user to fix
`fitdocs.toml` first. For `wellness_orphaned_entry`,
`wellness_series_occupied` or `wellness_conflict`, tell the user the finding
and remedy. Never delete archive entries, inbox files or occupied paths to
resolve these findings yourself. The user decides which data to keep.

**Heart-rate benchmarks in `fitdocs check`.** These findings concern the
athlete's recorded benchmark timeline:

- `hr_benchmark_takeover`: derived resting or maximum heart rate has taken
  over from a hand-recorded value. Relay the takeover's values, dates,
  evidence and remedy to the athlete; the athlete decides whether to record
  a new hand value or leave the derived value. Never answer the takeover
  yourself. A new hand entry wins from its date; leaving the derived entry
  accepts it. The listing ends when a later entry of that kind exists.
- `hr_benchmark_inconsistent`: the selected heart-rate benchmarks are
  inconsistent, so heart-rate load is not computed in the printed period.
  Tell the athlete the inconsistent period and recorded values, and suggest
  recording the correct value by hand for the one that is wrong.
- `athlete_profile_unreadable`: the profile could not be read or validated.
  Tell the athlete to fix `athlete.toml`; load and derive-benchmarks refuse
  to run until it is valid.

A changed benchmark timeline affects existing computed load only after an
explicit recomputation. Never run `fitdocs load --recompute` unless the
athlete asks.

## Publishing posts

fitdocs can publish workout posts to the publish targets the athlete has
configured -- several at once, and this skill names none of them: which
targets exist is the athlete's configuration, never something to assume.

List them with `fitdocs publish --targets`. It prints each configured
target with its state and the explanation of every state it printed, and it
sends and writes nothing. If it reports that no publish target is
configured, there is nothing to publish to; tell the athlete.

A workout page opts in with the `publish` key in its frontmatter: one target
name, or a list of distinct target names. A page without the key is sent
nowhere. The key is the athlete's, so do not add or change it unless the
athlete asks you to.

A page carries a `post` region; pages written by an older fitdocs gain it
with `fitdocs regen`. Left empty (or holding only its hidden comment), the
configured template composes the post, unless the athlete has a post template
(see below) waiting to fill an in-window, unpublished page, in which case
`fitdocs publish` refuses the page with `post_waiting`. An emptied region is
filled again from the post template by the next `fitdocs sync` only when the
page is in the window and has no landed post.
To give one page its own post, write the title on one line, then a blank line,
then the description.
The text may use placeholders such as `{title}`, `{distance_km}` and
`{moving_time}`, and optional clauses: `{?Distance: {distance_km} km}`
renders only when every placeholder inside it has a value. Write `{{` and
`}}` for literal braces. A placeholder outside a clause that has no value on
that page refuses the page rather than posting a blank.

Preview with `fitdocs publish`, optionally naming pages. Without `--yes` it
changes nothing: it sends no request, writes no file, and shows what would be
posted to each target.

```bash
fitdocs publish
```

Run `fitdocs publish --yes` only when the athlete has asked you to post.
Posting is irreversible: show the athlete the preview first, and never add
`--yes` on your own initiative, to a scheduled run, or to retry a failure.

Each result line of the report carries a code; the report prints each code's
explanation once, below the results. Relay the explanation rather than
guessing from the code. `posted` and `uploaded` mean the post landed;
`would_post` and `would_update` are previews; `unchanged` and `not_opted_in`
need nothing; every other code is a failure (it counts toward exit status 1):
tell the athlete which page and target it concerns and what the explanation
says, and do not retry it on your own judgment. `not_connected`,
`auth_rejected` and `permission_denied` mean the athlete must run
`fitdocs connect` for that target; `credentials_unreadable` means the athlete
must fix the credentials file or connect again. Never run `fitdocs connect`
yourself.

### Post templates

An athlete can keep a `post-template.toml` at the top of the data root, so that
`fitdocs sync` writes each new page's post, numbers included, into its `post`
region. The file is the athlete's: never create or edit it unless they ask.
The values come from the analytics index, so `fitdocs index` must have been run
once. `fitdocs post-template check [PAGES...]` reads the file, checks its SQL and
shows what a page would get, and writes nothing. `fitdocs post-template refill
[PAGES...]` recomputes posts and writes only with `--yes`; a bare `refill`
leaves published pages alone, and naming a page refills it. Only run `refill
--yes` when the athlete asks. A region the athlete wrote or edited is theirs
and is never overwritten; emptying it returns it to the template, which
`fitdocs sync` fills again only for an in-window page with no landed post, and
otherwise `fitdocs index` then `fitdocs post-template refill PAGE --yes`
(the index must be current) does. Warn the athlete that
emptying an already-published page's region and then running
`fitdocs publish --yes` sends the target's own template and updates the posted
activity; publish does not refuse it. A page
refused by `fitdocs publish` as `post_waiting` is waiting for its post: tell the
athlete, and suggest `fitdocs index`, then `fitdocs sync`, or writing the post by
hand.

A worked recipe: say how much training load the week holds up to and including
this workout, for one methodology. It sums each page's own `pages.load_value`
for that methodology up to the workout's start, so the number is the week as
of this workout. It never reads the week's running total. The numbers below are
invented.

```toml
# Set `since` to the day you create this file. A date in the past fills every
# page since then.
since = 2026-11-07

title = "{title}"
description = """
{?{week_load} load points this week so far.}
"""

[vars.week_load]
sql = """
SELECT round(sum(load_value))::INT
FROM pages
WHERE load_methodology = 'threshold'
  AND date >= date_trunc('week', $as_of)
  AND start_time_local <= $as_of
"""
```

With three threshold workouts in a week, of load 35, 45 and 25, their posts
read `35`, `80` and `105`. The `::INT` is needed because a sum is a
floating-point number, which a post template refuses; a week with no matching
workout gives no value, and the clause is dropped. When the athlete asks you to
write this file, set `since` to the day you create it, and tell them why.

See
[the publishing guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md)
for the full template grammar, every placeholder and every code.

## Ownership boundary

The fitdocs-owned tree -- the directories fitdocs writes generated content
into -- is tool-owned: an agent maintaining this wiki never hand-edits
generated content there. Some regions inside those documents are the
author's own and are preserved across every fitdocs write. The authority
for exactly which paths and regions are owned, in this data root, is the
`AGENTS.md` declaration fitdocs emits inside the owned tree itself; the
[published ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
is the detail behind it. Read those rather than assuming a boundary from
this skill.

## Further reading

- [Querying the analytics index](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md) — use the `fitdocs-analytics` skill for statistical questions and query guidance.
- [Inbox interface](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md) -- default location, every settings key, drain semantics, and the safeguards.
- [Connectors](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md) -- what a connector is, `[connectors.<name>]` keys, `fitdocs connect`/`fitdocs pull`, credentials, and what leaves the machine.
- [Ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) -- the published detail behind the in-tree declaration.
- [Configuration](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md) -- the data-root contract and `fitdocs.toml`.
