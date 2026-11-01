# Publishing

fitdocs can turn each workout page into a post (a title and a description)
and send it to the publish targets you configured. This page is the reference
for that: the command, the settings, the template language, every placeholder,
every outcome code, and the files and page regions publishing touches. It names
no service. Each target documents itself in its own connector page; see
[Connectors](connectors.md).

Publishing is opt-in at every level. A target exists only if you configured it,
a page is posted to a target only if the page's `publish` key names it, and
nothing is sent unless you run `fitdocs publish --yes`.

```bash
fitdocs publish --targets                 # which targets are configured, and are they ready
fitdocs publish                           # dry run: show what would be posted
fitdocs publish --yes                     # post it
```

## The command

```text
fitdocs publish [PAGES...] [--to TARGET]... [--yes] [--targets]
                [--format text|json] [--out PATH]
```

For each workout page, and each target that page opts in to, `fitdocs publish`
decides what to do: post the page for the first time, update an earlier post
whose text changed, or nothing because the post is unchanged. A run without
`--yes` sends no request and writes nothing; it prints those decisions and the
exact title and description it would post. With `--yes` it sends them.

A **publish target** is a connector instance (a `[connectors.<name>]` table in
the settings file) whose connector can publish posts. The target's name is the
instance's name. `PAGES` names workout pages: each a file name in `workouts/`
(with or without `.md`) or a path to a file directly in `workouts/`. Without
`PAGES`, every workout page in `workouts/` is considered, in file-name order.

### Options

| Option | Meaning |
|---|---|
| `--to TARGET` | Consider only this target. Repeat it to name several. A name that is not a configured publish target stops the run (exit 2) and the message names every configured publish target. |
| `--yes` | Post what the dry run shows. Without it nothing is sent or written. |
| `--targets` | List the configured publish targets instead of publishing. It cannot be combined with `PAGES`, `--to` or `--yes`. |
| `--format` | `text` (the default) or `json`: how the report is printed. |
| `--out PATH` | Use `PATH` as the data root, as every command that reads the data root does; the resolution order is in [Configuration](configuration.md). |

### Preflight

Every check below runs, in this order, before any request is sent and before
anything is written. A failure prints what to fix and exits 2.

1. The data root resolves.
2. `--targets` is not combined with `PAGES`, `--to` or `--yes`.
3. The settings file, its inbox settings and its `[connectors]` table are valid.
4. The `[publish]` table is valid. This check runs on every invocation,
   including a dry run, `--targets`, and a run where no page opts in to anything.
5. With `--targets`: when a configured target authenticates, the per-user
   credentials directory resolves and lies outside the data root; then the
   listing is printed and the command exits 0 (see
   [Listing the targets](#listing-the-targets)).
6. Every `--to` name is a configured publish target.
7. Every page in `PAGES` is a workout page directly in `workouts/`. A name that
   resolves to nothing, to a symbolic link, to a file elsewhere or to a
   readable file that is not a workout page is refused. A named page that
   cannot be read is not refused here; the run reports it as `page_unreadable`.
8. Every publish ledger is readable and usable (see
   [The publish ledger](#the-publish-ledger)).
9. With `--yes`, when a selected target authenticates: the per-user credentials
   directory resolves and lies outside the data root.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | No result carries a failure code (the **Failure** column of the [code table](#outcome-codes)). |
| `1` | At least one result carries a failure code. |
| `2` | A configuration error found by the preflight, before any request or write. |
| `130` | The run was interrupted. It stops sending and keeps every outcome it had already received. |

### Reading the report

A dry run prints one line per page and target, the post's text indented
beneath each page that would be posted or updated, a summary, and then each
printed code's explanation once, in the vocabulary's order:

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

Pages that opt in to none of the selected targets are counted, not listed,
except a page you named in `PAGES`, which is listed with `not_opted_in`. A
problem with the page as a whole (an invalid `publish` key, an unreadable
page, a region that could not be rewritten) is a line without a target. The
text in parentheses after a code is a detail fitdocs wrote itself, such as the
name of the placeholder that had no value.

In a posting run (one with `--yes`), each pair that was sent shows the outcome
code instead of the decision, and a post that landed shows its link. When a
target offered a link that fitdocs would not keep (see
[The published region](#the-published-region)), the pair's block ends with
`  link: refused`. Pages are listed in file-name order, and a target's pairs that
would be sent after one that stopped it are `not_attempted`.

```text
fitdocs publish: posting.
workouts/2026-10-22-run.md -> club-feed: posted
  link: https://example.invalid/a/1
workouts/2026-10-23-ride.md -> club-feed: posted
  link: refused
workouts/2026-10-26-run.md -> club-feed: rate_limited
workouts/2026-10-27-ride.md -> club-feed: not_attempted
2 posted, 1 rate_limited, 1 not_attempted; 2 pages opted in to no selected target.

posted: The target's activity now carries this page's title and description.
rate_limited: The target's rate limit was reached, so nothing more is sent to it in this run; try again later.
not_attempted: Nothing was sent, because an earlier result in this run stopped publishing to this target.
```

With `--format json` the report is one JSON document of a stable, versioned
shape. `format` is `1`. The document's keys follow.

The top-level keys, in order: `format`, `posting`, `results`, `counts`, `not_opted_in`, `explanations`.

Each result's keys, in order: `page`, `target`, `code`, `decision`, `title`, `description`, `link`, `link_refused`, `detail`.

`target` is `null` for a page-level result. `decision` is what the run decided
before sending (`would_post`, `would_update` or `unchanged`), and `null` for a
result that never reached a decision. `title` and `description` hold the post
the result carries, and are `null` when it carries none. `link` is set only on
a result whose code means the post landed. `counts` and `explanations` list
only the codes the run produced, in the vocabulary's order.

When no publish target is configured, the text report is followed by the
sentence `No publish target is configured.` (or consists of it, when there is
nothing else to report) and the command exits 0, unless a result carries a
failure code, in which case the report is printed alone. The JSON document is
printed unchanged.

### Listing the targets

`fitdocs publish --targets` lists every configured publish target in name
order: its name, its connector and the connector's display name, which of the
three publish capabilities it declares, and its state. The state is one code:
`ready`, `not_connected` or `credentials_unreadable`. The listing sends no
request and writes nothing. It reads credentials only to say what state they
are in, and it never shows a credential value.

```text
club-feed: example (Example feed); capabilities: push-activity, annotate-remote-activity; state: ready
team-log: example-two (Example log); capabilities: annotate-remote-activity; state: not_connected

not_connected: This target has no usable credentials; run `fitdocs connect` for it.
ready: This target is configured and has the credentials it needs.
```

When no publish target is configured it prints `No publish target is configured.` and exits 0.
With `--format json` it prints one JSON document.

The listing's keys, in order: `format`, `targets`.

Each target's keys, in order: `name`, `connector`, `display_name`, `capabilities`, `state`, `explanation`.

## Opting a page in

A workout page opts in to a target through the `publish` key in its
frontmatter. The value is one target name, or a list of distinct target names:

```yaml
publish: club-feed
```

```yaml
publish: [club-feed, team-log]
```

`publish` is yours: fitdocs never writes it, and carries its line through every
rewrite byte-for-byte, whether or not its value is valid. A page with no
`publish` key, or an empty list, is posted nowhere.

- A value that is neither a name nor a list of distinct names reports the page
  with `opt_in_invalid` and sends nothing from it.
- A name that is not a configured publish target reports that page and name
  with `unknown_target`, sends nothing for that name, and still considers the
  page's other names. When `--to` names fewer targets than are configured,
  unknown names are not reported: naming every configured target is the same
  as not using `--to`.
- When a page stops naming a target it was posted to, fitdocs sends nothing
  more for that page to that target, deletes nothing at the target, and keeps
  the recorded link on the page.

A page that opts in to a selected target is only published when it is current.
A page written by an older fitdocs reports `page_out_of_date` (run
`fitdocs regen` to bring it up to date), one written by a newer fitdocs reports
`page_newer`, and one whose region markers are damaged or missing reports
`page_damaged`. A page that records no sport, or no start time with the clock
offset its device recorded, or no archived file, reports
`activity_facts_missing`. A named page that cannot be read reports
`page_unreadable`; an unreadable page you did not name is skipped.

## The post

For each page and target, the post is composed offline, from the page and the
settings file alone, so the same page and settings always compose the same
bytes. The text comes from the page's own `post` region when it holds any, and
from the target's template otherwise. The title is one line.

### The `post` region

Every workout page carries an athlete-owned `post` region between the lines
`<!-- fitdocs:begin:post -->` and `<!-- fitdocs:end:post -->`. A fresh page
holds one hidden comment in it that renders as nothing. fitdocs carries its
content through every rewrite verbatim and never changes it, publishing
included. Write the page's own post there:

```markdown
<!-- fitdocs:begin:post -->
{title}: a day I wanted to run

Felt strong from the first kilometre.
{?Average heart rate: {avg_hr_bpm} bpm}
<!-- fitdocs:end:post -->
```

The rules, in order:

1. Hidden comments (`<!-- ... -->`) are authoring notes. They are removed
   wherever they appear and never posted. A comment that is never closed
   reports the page with `post_invalid`.
2. Blank lines at the start and the end are dropped. When nothing is left, the
   page uses the target's template.
3. Otherwise the first line, with surrounding whitespace removed, is the
   title. When another line follows, it must be blank, or the page reports
   `post_invalid`. The lines after that blank line are the description. A
   region with only a title line posts an empty description.
4. The title and the description are templates, filled exactly as a template
   in the settings file is (see [Template syntax](#template-syntax)). A syntax
   error or an unknown placeholder reports the page with `template_invalid`,
   naming the placeholder or the position.

The region replaces the template of every target the page opts in to, so the
same words go to each of them. Apart from placeholders, clauses and escapes,
your words are posted as you typed them. A placeholder is filled only from the
page's managed values, never from text you wrote.

### Templates and settings

Without a `post` region, the post comes from a title template and a description
template. The built-in default composes a post for every workout page whatever
optional values it lacks: the title is `{title}`, so only a page with no usable
title is refused (`value_missing`), and the description is one line for
each of distance, time, pace, speed, average heart rate, average power and
elevation gain, each written only when the page records the value.

For a run page, the built-in default composes:

```text
Morning Run

Distance: 12.50 km
Time: 58:20
Pace: 4:40 /km
Average heart rate: 149 bpm
Average power: 231 W
Elevation gain: 88 m
```

The `[publish]` table of `<data-root>/fitdocs.toml` changes the templates. Each
field is resolved separately, for each target: the target's own
`[publish.targets.<name>]` value, else the `[publish]` value, else the built-in
default.

```toml
[publish]
title = "{title}{? - {distance_km} km}"
description = '''
{?Distance: {distance_km} km
}{?Time: {moving_time}
}'''

[publish.targets.club-feed]
description = "{?Load: {load_value} ({load_methodology})}"

[publish.targets.team-log]
title = "{sport} on {date}"
```

| Table | Keys |
|---|---|
| `[publish]` | `title`, `description`, `targets` |
| `[publish.targets.<name>]` | `title`, `description` |

`fitdocs publish` stops with a configuration error (exit 2), before any request
and before any write, when:

- `[publish]`, `[publish.targets]` or an entry in it is not a table;
- a table holds a key not listed above, or a value that is not text;
- a title template holds a control character, such as a line break or a tab, or
  a line or paragraph separator (U+2028, U+2029), because a title is one line;
- a template has a syntax error or names an unknown placeholder;
- `[publish.targets]` names something that is not a configured publish target.

The message names the settings file, the table and the key, and, for a template,
the line, the column and the reason. The same checks run on every invocation.

### Template syntax

A template is plain text with three constructs, read left to right:

| Written | Means |
|---|---|
| `{name}` | The placeholder `name`, filled from the page. The name is lowercase letters, digits and underscores, starting with a letter, and must be in the [placeholder table](#placeholders). |
| `{{` and `}}` | A literal `{` and a literal `}`. |
| `{?...}` | An optional clause: its text is included only when every placeholder inside it has a value; otherwise it contributes nothing. A clause must hold at least one placeholder and cannot hold another clause. Inside a clause, `}}` is a literal `}` and a single `}` closes it. |

There are no expressions, no other conditionals, no attribute access, no
filters and no formatting options. Any other brace is a syntax error: a lone
`{` or `}`, `{ name}`, an unterminated placeholder or clause. Positions are
reported as a 1-based line and column; in a `post` region's description they
count from the description's first line. A value is inserted literally and is
never read as template text again.

When a placeholder outside an optional clause has no value, the page reports
`value_missing`, naming the placeholder, and nothing is posted from it to that
target. An absent value is never filled in as `0`, as an empty string or as any
other default. A value the page records as zero is rendered as zero.

### Placeholders

A placeholder is filled only from the page's own managed values, and from values
derived from them by fixed arithmetic. The table gives each name, its fixed
format, an example (from a run page; `speed_kmh` from a bike page), and when the
placeholder has no value. A derived value is computed only from positive,
present inputs.

| Placeholder | Format | Example | Has no value when |
|---|---|---|---|
| `title` | the page's title, as written | `Morning Run` | the title is missing or blank, or holds a control character or a line or paragraph separator (U+2028, U+2029) |
| `sport` | the page's recorded sport, as written | `Run` | the sport is missing or holds a control character or a line or paragraph separator (U+2028, U+2029) |
| `date` | `YYYY-MM-DD`, the local date | `2026-03-04` | the date is missing or malformed |
| `start_time` | `HH:MM`, at the offset the device recorded | `07:05` | the start time is missing or has no offset |
| `distance_km` | kilometres, two decimals | `12.50` | the distance is missing or malformed |
| `distance_mi` | miles (`distance_km` / 1.609344), two decimals | `7.77` | `distance_km` has no value or is zero |
| `moving_time` | `h:mm:ss` from one hour, otherwise `m:ss` | `58:20` | the moving time is missing or malformed |
| `elapsed_time` | as `moving_time` | `1:02:05` | the page records no elapsed time, or it is malformed |
| `pace_per_km` | `m:ss` per kilometre | `4:40` | the page's modality is not `run`, or the moving time or distance is missing or zero |
| `pace_per_mi` | `m:ss` per mile | `7:31` | as `pace_per_km` |
| `speed_kmh` | kilometres per hour, one decimal | `12.9` | the page's modality is not `bike`, or the moving time or distance is missing or zero |
| `avg_hr_bpm` | whole beats per minute | `149` | the average heart rate is missing or malformed |
| `avg_power_w` | whole watts | `231` | the average power is missing or malformed |
| `elevation_gain_m` | whole metres | `88` | the elevation gain is missing or malformed |
| `calories_kcal` | whole kilocalories | `811` | the calories are missing or malformed |
| `load_value` | the training load, a whole number | `62` | the page records no usable load |
| `load_methodology` | the load's methodology, as written | `TRIMP` | the page records no usable load |

### How a post is composed

fitdocs renders the title first, then the description. A placeholder outside a
clause with no value in the title gives `value_missing`; if the title has none,
the same in the description gives `value_missing`; only then is an empty title
refused with `title_empty`. A title that spans lines is folded to one line, with each run of
whitespace around a line break becoming one space, and its surrounding
whitespace is removed. A description has its line endings turned into newlines,
its leading blank lines dropped, and its trailing whitespace removed.

A post counts as changed exactly when its title or its description differs from
the last post that landed for that page and target, and for no other reason.
Each target's post is composed separately, so one page can send different posts
to two targets with different templates.

## Posting with `--yes`

A run without `--yes` sends no request and writes nothing: no ledger, no page,
no credentials. The decisions and the posts it prints are exactly the ones a
`--yes` run makes next, provided nothing changed in between:

- `would_post` when the ledger holds no landed post for the page and target;
- `would_update` when the ledger's landed post differs from the composed one;
- `unchanged` when they are equal.

With `--yes`, fitdocs hands each target one publish request for every pair
decided `would_post` or `would_update`, one request at a time, taking pages in
file-name order and each page's targets in target-name order, and records the
target's one outcome code. It sends nothing for a pair that is unchanged, not
opted in or refused. A second `--yes` run, after a run in which every sent pair
landed and with nothing else changed, sends nothing and leaves every ledger and
page byte-identical. A pair whose last outcome did not land (for example
`unconfirmed`, `rate_limited` or `not_attempted`) is decided and sent again.

- A target is prepared on its first pair. When it has no credentials or they
  cannot be read, every pair of that target in the run that would be sent gets
  that code (`not_connected` or `credentials_unreadable`) and no request is made
  to it; a pair decided `unchanged` or refused offline keeps its own code. Other
  targets carry on.
- When an outcome stops the target (the **Stops target** column), nothing more
  is sent to that target in this run, and its remaining pairs that would be sent
  are reported as `not_attempted`; a pair decided `unchanged` or refused offline
  keeps its own code. Other targets carry on.
- When a target fails unexpectedly, or answers with a code a target may not
  return, fitdocs records `target_error`, prints no part of the failure's
  message, and continues with the next pair.
- Each outcome is saved to the ledger before the next request is sent. An
  interruption stops sending, keeps every outcome already saved, and exits 130.
- When a target reports that a request was sent but its result is unknown, the
  outcome is `unconfirmed`. That does not count as landed, so the next run
  decides the pair again and sends it again; the target looks for the activity
  before creating one, so a repeat does not post twice.

## Outcome codes

Every result of `fitdocs publish` is one code from a closed vocabulary. The
vocabulary is append-only: a later version adds codes after these and never
removes, renames, reorders or redefines one. The explanations are fixed
sentences written by fitdocs.

- **Landed**: the target has confirmed that its activity carries the post's
  title and description.
- **Failure**: the code counts toward exit status 1.
- **Target may return**: a target is allowed to answer a request with it.
- **Stops target**: nothing more is sent to the target for the rest of the run.
- **Listing state**: `fitdocs publish --targets` may show it as a target's state.

| Code | Meaning | Landed | Failure | Target may return | Stops target | Listing state |
|---|---|---|---|---|---|---|
| `would_post` | This page has no post on this target yet, and `fitdocs publish --yes` would post it. | no | no | no | no | no |
| `would_update` | This page's post changed since it last landed on this target, and `fitdocs publish --yes` would update it. | no | no | no | no | no |
| `unchanged` | This target already carries this page's current post, so nothing is sent. | no | no | no | no | no |
| `not_opted_in` | This page's publish key does not name this target, so nothing is sent. | no | no | no | no | no |
| `opt_in_invalid` | This page's publish key is neither a target name nor a list of distinct target names, so nothing is sent from it. | no | yes | no | no | no |
| `unknown_target` | This page's publish key names something that is not a configured publish target, so nothing is sent to it. | no | yes | no | no | no |
| `page_out_of_date` | This page was written by an older fitdocs; run `fitdocs regen` before publishing it. | no | yes | no | no | no |
| `page_newer` | This page was written by a newer fitdocs, so this installation does not publish it. | no | yes | no | no | no |
| `page_damaged` | This page's region markers are damaged or missing; restore them by hand before publishing it. | no | yes | no | no | no |
| `page_unreadable` | This page could not be read as a workout page, so nothing is sent from it. | no | yes | no | no | no |
| `post_invalid` | This page's post region is not a title line, a blank line and a description, so nothing is sent from it. | no | yes | no | no | no |
| `template_invalid` | This page's post region has a template error, so nothing is sent from it. | no | yes | no | no | no |
| `value_missing` | A placeholder outside an optional clause has no value on this page, so nothing is sent. | no | yes | no | no | no |
| `title_empty` | The composed title is empty, so nothing is sent. | no | yes | no | no | no |
| `activity_facts_missing` | The facts that identify this page's activity are missing, so nothing is sent. | no | yes | yes | no | no |
| `ledger_conflict` | The publish ledger holds more than one record for this page, or one record matches several pages, so nothing is sent. | no | yes | no | no | no |
| `posted` | The target's activity now carries this page's title and description. | yes | no | yes | no | no |
| `uploaded` | No matching activity existed, so the target created one from this page's activity file with its title and description. | yes | no | yes | no | no |
| `not_found` | The target has no activity matching this page and uploading is not enabled for it, so nothing was changed. | no | yes | yes | no | no |
| `ambiguous` | More than one activity on the target matches this page, so nothing was changed. | no | yes | yes | no | no |
| `not_updatable` | The matching activity cannot be changed through this target, so nothing was changed. | no | yes | yes | no | no |
| `activity_file_missing` | Uploading needs this page's activity file, which is not in the archive, so nothing was changed. | no | yes | yes | no | no |
| `not_connected` | This target has no usable credentials; run `fitdocs connect` for it. | no | yes | yes | yes | yes |
| `credentials_unreadable` | This target's stored credentials could not be read or are not private to you; fix the file or connect it again. | no | yes | no | yes | yes |
| `auth_rejected` | The target refused the stored credentials; connect it again. | no | yes | yes | yes | no |
| `permission_denied` | The credentials do not allow this change; connect again and grant the permission it needs. | no | yes | yes | yes | no |
| `rate_limited` | The target's rate limit was reached, so nothing more is sent to it in this run; try again later. | no | yes | yes | yes | no |
| `unavailable` | The target could not be reached or failed on its side, so nothing more is sent to it in this run; try again later. | no | yes | yes | yes | no |
| `rejected` | The target refused the request as invalid, so nothing was changed. | no | yes | yes | no | no |
| `unconfirmed` | The request was sent but its result is unknown; the next run checks the target before sending again. | no | yes | yes | no | no |
| `target_error` | The target failed unexpectedly, which is a fitdocs defect, and nothing more was sent for this page. | no | yes | no | no | no |
| `not_attempted` | Nothing was sent, because an earlier result in this run stopped publishing to this target. | no | yes | no | no | no |
| `published_not_written` | The outcomes were recorded, but this page's published region could not be rewritten; the next `fitdocs publish --yes` rewrites it. | no | yes | no | no | no |
| `ready` | This target is configured and has the credentials it needs. | no | no | no | no | yes |
| `local_record_unreadable` | This target could not read its own local record of this connection's activities, so it could not rule out that the activity already exists and uploaded nothing. | no | yes | yes | no | no |

## The publish ledger

fitdocs keeps one publish ledger per target, a TOML file at
`.fitdocs/publish/<target>.toml` in the data root, in the tool-owned state
directory `.fitdocs/`. It records what was posted, so a run knows what is new, what changed
and where each post went.

```toml
ledger_version = 1
connector = "example"

[[publication]]
page = "workout:0f3ac1d96b5e7a2c48d0e91f3b6a7c5d2e8f4a1b9c0d3e6f7a8b5c4d1e2f3a6b"
id = "9c1e4a7b2d5f8031e6a9c4b7d0f3a625"
digest = "5b7d0e3a6c9f2b5e8a1d4c7f0b3e6a9d2c5f8b1e4a7d0c3f6b9e2a5d8c1f4b7e"
code = "posted"
at = 2026-10-31 09:15:02+00:00
link = "https://example.invalid/a/1"
label = "Example"
```

- `ledger_version` is `1`. fitdocs writes the version into every ledger and
  refuses to read a ledger of a newer version.
- `connector` names the ledger's identity, which is the target's connector id. A
  configured target's ledger written for another connector is refused.
- Each `[[publication]]` is one page on this target, keyed by `page`, which is
  `workout:` and the digest of the page's base archived file. A record matches
  a page when its digest is one of the digests the page lists, so a record
  survives the page's rename, a change of its base file and its regeneration.
- `id` is the **publication id**: 32 random lowercase hexadecimal characters, minted by
  fitdocs, not derived from the page, and saved before the first request for the
  page and target. The same id is handed to the target on every later request for
  that page and target, and is never reused for another, so a target can use it
  as an idempotency key.
- `digest` is the digest of the last post that landed, and is absent until a
  post lands. A post is compared with it to decide `would_update`.
- `code` and `at` (UTC) are the last outcome and when it was received, together.
- `link` and `label` are the last permitted link and its label, together, and
  change only when a link is kept. A later outcome that is not a landed one
  keeps the earlier link.
- A record with an `id` and no `code` is an attempt that was interrupted after
  the id was saved. The next run decides from `digest` as usual and reuses the `id`.

Writing a ledger is atomic, in a stable order, and happens only when its
content changes. Reading creates nothing: while a target has no ledger, every
page counts as never posted to it. The ledger holds nothing a target's service
returned except a permitted link.

`fitdocs publish` stops with a configuration error, before any request and
before any write, naming the file, when a ledger cannot be read, is not valid
TOML or has an unexpected shape, is of a newer version, was written for another
connector, or breaks one of its rules (for example two records for one page).
It never overwrites or rebuilds such a file. A publication id that appears in
the ledgers of two targets is refused too, naming the second file, so copying a
ledger file to rename a target is refused; delete one of the two files to
recover. If more than one record matches a page, or one record matches more
than one page, that page and target are reported with `ledger_conflict` and
nothing is sent for them.

Deleting a ledger forgets what was posted to that target. The next
`fitdocs publish --yes` treats every opted-in page as never posted, decides
`would_post`, mints new publication ids and sends the posts again. A target
looks for an existing activity before it creates one, so it is expected to find
the earlier activity rather than make a second. The links the deleted ledger
held leave the pages the next time `fitdocs publish --yes` considers them, and
return if the targets give them again.

## The published region

Every workout page carries a fitdocs-owned `published` region, between the lines
`<!-- fitdocs:begin:published -->` and `<!-- fitdocs:end:published -->`. A fresh
page leaves it empty, so it renders as nothing. When `fitdocs publish --yes`
considers a page, it rewrites that region from the ledgers as one line that
lists each recorded link with its label, in target-name order, or as empty when
no link is recorded:

```markdown
Published: [Club feed](https://example.invalid/a/1) · [Team log](https://example.invalid/b/2)
```

- fitdocs rewrites nothing else on the page, and does not write the page when
  the region is unchanged. It never writes the `post` region.
- A run without `--yes` never writes the region.
- A hand edit to the region is replaced the next time `fitdocs publish --yes`
  considers the page. Regeneration carries the region's content as generated
  content. The ownership of the region is stated in
  [The ownership contract](ownership-contract.md#the-published-region).
- A page written by an older or a newer fitdocs is never written; it is
  reported as described under [Opting a page in](#opting-a-page-in).
- A link is recorded only from a target's answer with a code that means the post
  landed, and only when it is an `https` link with a host, at most 2048
  characters long, with no whitespace, control character or any of
  ``<>()[]"`\``. Otherwise no link is recorded and the report says so with
  `  link: refused`.
- A target declares its link label as fixed text, and the label is the only text
  beside the link in the region. A label is 1 to 64 characters with no control
  character or square bracket.
- When the region cannot be rewritten (the write fails, or the ledger records
  that match the page are ambiguous), fitdocs keeps the
  recorded outcomes, reports the page with `published_not_written`, and rewrites
  the region on a later `fitdocs publish --yes`.

## What a target does

Each target is a connector whose own page documents how it authenticates, how it
finds its activity and what it permits. Every target meets the same contract.
The connector framework hands a target, per request, only:

- the publication id;
- the post's title and description;
- the subject being published: for a workout page, the completed activity it
  records. That is its sport, its start time with the recorded clock offset, its
  elapsed time and distance where recorded (otherwise absent), the content
  digests of the page's archived files in rank order, and the location of its
  base file when the archive holds it;
- the link recorded for that page and target by an earlier outcome, if any.

The request holds no page text, no frontmatter, no page path and no
credential. A target authenticates through its own connector session, which
carries the credentials it needs. In return the framework takes from a target
exactly one code from the **Target may return** column and, only with a code
that means the post landed, at most one link.

A target's obligations:

- It finds the remote activity, decides whether to upload, and maps every answer
  of its service into a code. `fitdocs publish` performs none of these steps.
- It must look for an existing activity before creating one, on every request, with
  the publication id as the idempotency key, so a request repeated after an
  unknown result finds the activity instead of creating a second one.
- It answers more than one matching activity with `ambiguous`, and an activity it
  cannot identify from the facts given with `activity_facts_missing`. It never
  chooses one of several, and never uploads in either case.
- It answers `local_record_unreadable`, and never uploads, when it cannot read its
  own local record of the connection's activities and resolution fails.
- It marks a request that is not idempotent as single-attempt. The transport
  sends a single-attempt request exactly once, whatever the response and whatever
  the network failure, while unmarked data requests keep their bounded retries,
  and authentication requests their single attempt.
- It never prints, logs or returns text its service sent.

A connector that can publish declares the annotate-remote-activity capability.
One that also declares resolve-remote-activity or push-activity must declare
annotate-remote-activity too. Any connector that declares one of the three
publish capabilities must provide the publish operation and a valid link label,
or its registration is rejected with a reason.

## Nothing from a service

Nothing a service returns is printed, logged or written, except a permitted link.

The outcome of a request is one code from the vocabulary above, with its
explanation. The report prints only those codes and explanations, the post
fitdocs composed from your page, the one permitted link of a post that landed,
and fitdocs's own text: page names, target
names, and details of problems fitdocs found offline. A target's answer is reduced to a code and,
with a code that means the post landed, one link that passes the rules in
[The published region](#the-published-region). Anything else the target
returns, including a failure's message, is discarded, and the ledger holds
nothing but the permitted link.

## Related pages

- [Configuration](configuration.md): the settings file and the `[publish]` table.
- [Connectors](connectors.md): configuring, connecting and running a target.
- [The ownership contract](ownership-contract.md): the `post` and `published`
  regions, the `publish` key and the ledger's place in the data root.
