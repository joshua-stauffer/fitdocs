# Connectors

A connector is a source fitdocs can pull activity `.fit` files and, where
enabled, wellness files from automatically. You configure named **instances**
of a connector in `<data-root>/fitdocs.toml`,
run `fitdocs connect` once for any instance that needs credentials, and run
`fitdocs pull` — by hand, or on a schedule — to fetch what's new. Everything a
pull delivers lands in the existing inbox, where the existing drain (`fitdocs
sync`, or `pull --sync`) picks it up exactly as it would a file you dropped
there yourself.

This page documents the connector *framework*: the commands, the settings
keys, the credential rules, and the four connectors fitdocs ships: `folder`,
which needs no service at all; `intervals`, for an intervals.icu account
([its section](#intervalsicu) below); `relay`, for a fitdocs relay
([its section](#the-relay-connector) below); and `strava`, for a Strava
account through a relay. Outside those two sections, the
framework sections of this page describe no online service and no network
protocol; the services they mention (intervals.icu, the relay, and Strava)
are named only to say which connector they belong to.

## Configuring an instance

Each instance is a `[connectors.<name>]` table. `<name>` is a lowercase slug
you choose (letters, digits, and hyphens).

```toml
[connectors.<name>]
connector = "folder"     # optional; defaults to the instance name
lookback_days = 30       # optional; whole days, 0-3650; defaults to 30
```

| Key | Meaning | Default |
| --- | --- | --- |
| `connector` | Which connector implementation this instance uses. | the instance's own name |
| `lookback_days` | For a connector that supports it, how many days before the *watermark* — the newest activity already recorded — its listing starts. An instance's first pull, with no ledger yet, has no watermark, so this key does not apply: each connector chooses where such a pull starts (`folder` considers everything under its source; `intervals` starts as its [section](#intervalsicu) says). Also the wellness re-check window before its own wellness watermark. The `folder` connector ignores it; it always considers everything under its source. A pull given `--since` starts from that date instead, for activities and wellness alike, so this key does not apply to it. | `30` |
| `wellness` | Enable only for a connector that pulls wellness; `true` is refused otherwise. | `false` |

Any other key in the table is passed to the connector itself; each connector
documents its own keys (`folder`'s are below). A key that collides with one
of a connector's own *credential* field names is refused — credentials never
belong in this file (see [Credentials](#credentials)).

## The folder connector

`folder` is the connector for a local directory: it needs no authentication
and makes no network request of any kind.

```toml
[connectors.<name>]
connector = "folder"
path = "/absolute/or/data-root-relative/path"   # required
settle_seconds = 2                              # optional
```

- `path`: the directory to read from. An absolute path is used as given; a
  relative path is resolved against the data root. It must not equal, sit
  inside, or contain your configured inbox.
- `settle_seconds`: how long a candidate file must sit unchanged before it is
  considered stable, exactly as the inbox's own settle check works. Defaults
  to the inbox's own default. Must be a finite number, at least `0`.

`folder` only ever reads from its source directory — it never writes, moves,
renames, or deletes anything there.

## intervals.icu

`intervals` is the connector for an [intervals.icu](https://intervals.icu)
account. It pulls: it lists the activities of the account the key belongs to
and fetches each one's original `.fit` file, with wellness available when
enabled below. It also publishes: for a page that opts in, `fitdocs publish
--yes` sets an activity's name and description (see
[Publishing](#publishing)). It writes only an activity's name and description,
plus the page's base file while `publish_upload` is on.

### Connecting

1. In `<data-root>/fitdocs.toml`, add the instance. An empty table is
   enough, because every key of it is optional (see
   [Configuring](#configuring)):

   ```toml
   [connectors.intervals]
   ```

   `fitdocs connect intervals` exits `2` with "not a configured connector
   instance" until the table exists.
2. In intervals.icu, open Settings, then Developer Settings, and create a
   personal API key.
3. Run `fitdocs connect intervals`. fitdocs asks for the key without echoing
   it, makes one read request to intervals.icu to check it, and saves it to
   the credentials store described under [Credentials](#credentials).

At a terminal that is not interactive, `fitdocs connect` exits `2` instead of
prompting and names the variable below.

An instance named `intervals` needs no `connector` key, because the
connector defaults to the instance's own name. An instance with any other
name sets `connector = "intervals"`, and its override variable is built by
the rule under [Credentials](#credentials).

To supply the key without storing it, set the override variable for an
instance named `intervals`:

```
FITDOCS_CONNECTOR_INTERVALS_API_KEY
```

A key intervals.icu refuses ends `fitdocs connect` with a message saying so,
and nothing is saved; create a new key and run `fitdocs connect intervals`
again.

### Configuring

```toml
[connectors.intervals]
sources = ["GARMIN_CONNECT"]   # optional; this is the default
publish_upload = false         # optional; this is the default
```

`sources` is a non-empty list of upper-case source names. intervals.icu
records, for every activity, which source it came from; a pull keeps only the
activities whose source is in the list. The default is `["GARMIN_CONNECT"]`,
so that your other copies of the same activities, such as uploads from a
phone app, are not fetched a second time. intervals.icu publishes these
names: `STRAVA`, `UPLOAD`, `MANUAL`, `GARMIN_CONNECT`, `OAUTH_CLIENT`,
`DROPBOX`, `POLAR`, `SUUNTO`, `COROS`, `WAHOO`, `ZWIFT`, `ZEPP`, `CONCEPT2`
and `HUAWEI`. fitdocs also accepts a well-formed name that is not in that
list, so a source the service adds later needs no fitdocs release. A
malformed `sources` value (not a list, an empty list, or a name that is not
upper case) is a configuration error, reported before any request is made.
The framework's `lookback_days` key applies as described under
[Configuring an instance](#configuring-an-instance), as does `wellness`.

`publish_upload` is `true` or `false`, and is `false` when absent. It matters
only to `fitdocs publish`: see [Publishing](#publishing). A `publish_upload`
that is not `true` or `false` is a configuration error for every command that
reads the connectors table, `fitdocs pull` included, because they share one
settings loader. No key other than `sources` and `publish_upload` is read by
this connector, besides the framework's keys above.

### What a pull fetches

The first pull lists the last 30 days. To go further back, run `fitdocs pull
intervals --since YYYY-MM-DD`, which lists from the start of that local day.
A long backfill can run into intervals.icu's rate limits, so step `--since`
back in stages, for example one season at a time: the ledger remembers what
each run delivered, so a later run fetches only what earlier ones did not.
The pull lists activities in date windows and fetches each new, available
activity's original file.

What a pull skips, and why. Each skip is recorded in the ledger, so the
activity is not asked about again, and it shows in the report's `skipped`
row with its reason:

- **Strava stubs.** intervals.icu returns only a stub for an activity that
  came from Strava and shares no file for it.
- **Originals that are not FIT.** An activity whose original is a GPX or TCX
  file is skipped, whether the listing says so or the file itself shows it.
  fitdocs ingests FIT files only.
- **Activities without a file.** An activity with no original file, such as
  one entered by hand, is skipped as having no original file.

What fails, and when it is retried. A single activity whose download fails
(an unreadable or oversized file, or an unexpected status from the service)
is reported as failed, and the next pull tries it again. These end the whole
instance's run instead, and the other configured instances still run:

- **A refused key.** The report names the rejection; run `fitdocs connect
  intervals` again with a working key.
- **A blocked client.** If intervals.icu refuses fitdocs itself rather than
  your key, the message quotes the service's reason; report it to the
  fitdocs project.
- **A rate limit.** If intervals.icu is still limiting requests after
  fitdocs's own retries, the pull stops and says so. This page states no
  request limits: intervals.icu decides them.
- **An unavailable service.** Handled the same way: the pull stops.

Picking up after a stop or a failed download. A pull without `--since` lists
from the watermark less `lookback_days`, and the watermark never moves past
an activity that is not yet recorded. So the next plain pull resumes where a
stopped pull left off, and retries a failed download, when that activity falls
inside its window. A `--since` backfill into an instance that has pulled
before is the exception: the backfill does not move the watermark back, so
the next plain pull misses whatever the stopped run left unfinished, or
failed to download, before that window. Run the same `fitdocs pull intervals
--since YYYY-MM-DD` again to continue; the ledger means it fetches only what
earlier runs did not.

What leaves your machine. Requests go to intervals.icu only. Each carries the
one fitdocs User-Agent and, in the `Authorization` header, your key. The key
is sent to intervals.icu itself and never to the target of a redirect, and it
never appears in an address. A pull's addresses carry date bounds and activity
ids; what a publish sends is described under [Publishing](#publishing).

What you get. The file a pull delivers is the copy intervals.icu holds. For an
activity whose source is `GARMIN_CONNECT` (the default), that is Garmin's own
partner-API copy of a ride recorded on a Garmin device. It is not
byte-identical to the file the device itself wrote, but it carries the
same messages, so a page that holds both reads the same whichever of the two
is its base. Before the first pull into a data root that already holds
pages, run `fitdocs regen`, so that the pages written before cross-source
identity are recognized when the same ride arrives; see
[Regenerating before a first pull](#regenerating-before-a-first-pull).

### Wellness

Set `wellness = true` in `[connectors.intervals]` to enable wellness alongside
activities. The first wellness pull reads from 2010-01-01, or from
`--since YYYY-MM-DD` when given, rather than the activity pull's last 30 days.
Later pulls re-check `lookback_days` before the wellness mark and compare each
day's `updated` revision. A missing `updated` uses a content hash instead.
The pull makes one wellness listing GET per window of up to a year, plus one
athlete-settings GET per packaged file. Some platforms' wellness reaches
intervals.icu only when you open intervals.icu; the look-back re-check picks
up late arrivals.

Attribution comes from the athlete's per-platform wellness import settings,
not from guessing from values. These settings describe current imports, not
per-value history: manually entered, corrected or historically imported
values can be misattributed. A field claimed by multiple platforms has no
platform attribution. Review your import settings when attribution changes;
use an original export when you need reliable historical provenance.

The private and ICU namespaces do not name source platforms.
A known platform's wellness-download switch must be boolean true when present;
an absent switch keeps list-based compatibility.
The Garmin health switch does not enable wellness imports.
Only enabled platform lists count toward ambiguity; a field claimed by multiple
enabled platforms has no platform attribution.

A 403 message may mean intervals.icu is withholding wellness received from
Garmin. Set `wellness = false` to stop wellness requests while keeping activity
pulls. Use Garmin's own data export through the [wellness guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/wellness.md)
for Garmin wellness.

Computed fields (`ctl`, `atl`, `rampRate`, `ctlLoad`, `atlLoad` and `sportInfo`)
are delivered but never imported into the wellness series. The delivered file
holds every field intervals.icu sent, including wellness comments and null
values. A day deleted on intervals.icu is not removed from fitdocs.

### Publishing

This is the intervals.icu side of `fitdocs publish`, whose command, outcome
codes and ledger are described in
[Publishing](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md).
A page opts in with `publish: <name>` in its frontmatter, where `<name>` is the name of the
intervals instance (`intervals` unless you named the instance otherwise).
Nothing is sent unless you run `fitdocs publish --yes`.

A publish makes the activity on intervals.icu carry the page's post: its name
is the post's title and its description is the post's description. It finds
the activity in this order, and stops at the first step that finds one:

1. **The recorded link.** The link an earlier publish recorded for this page
   and this instance, when it is exactly in the form fitdocs writes.
2. **The pull record.** The instance's [ledger](#the-ledger) names the
   activities a pull delivered, with the digest of what was delivered. fitdocs
   looks up the digest of the page's base file, and only when that names no
   activity, the digests of the page's other files. One activity answers;
   several are `ambiguous`.
3. **A listing around the start.** One request lists the account's activities
   from one day before the page's start date (in UTC) to two days after it,
   asking for the fields `id`, `source`, `start_date`, `start_date_local`,
   `distance`, `elapsed_time` and `external_id`. The page must have a recorded
   clock offset and a distance or an elapsed time; without them the answer is
   `activity_facts_missing`, and no listing is sent. An activity matches
   when it carries the page's publication id as its `external_id`, or else
   when it has the same start (to within a second) and a matching distance
   or, if either has no distance, a matching elapsed time, by the same rule
   fitdocs uses to recognise one activity recorded twice. The sport is not
   compared.

If a step finds an activity but intervals.icu answers its update with a `404`
(it does not exist), the activity is set aside and the search goes on. If
several activities match in one step, the answer is `ambiguous` and nothing is changed: fitdocs
never chooses one.

An activity that intervals.icu imported from Strava is never updated. It is
never matched, but when no other activity matches and a Strava activity starts
within a second of the page's start, the answer is `not_updatable`. A Strava
activity that lists no start time is compared by its local wall-clock start
against the page's recorded wall-clock start, so it is recognised only when
both were recorded in the same time zone; otherwise it goes unrecognised, and
with `publish_upload` on a publish can create a second copy.

`publish_upload` decides what happens when none of these steps finds an
activity and the instance's ledger could be read (an unreadable one is
described below). While it is `false` (the default) nothing is created and the answer is
`not_found`. While it is `true`, fitdocs uploads the page's base file, and
then sets the name and description of the activity that results. The file must be in the
archive and hash to the digest the page records for its base file; otherwise
the answer is `activity_file_missing` and no upload is sent.

What each request sends:

- **The update** is a `PUT` to the activity. Its body is the name and the
  description, and nothing else. intervals.icu's answer text is never read.
- **The upload** is a `POST` to the account's activities, a
  `multipart/form-data` form holding the base file, unmodified, under the file
  name `activity.fit`. The one value in its query is the page's publication
  id, as `external_id`. The upload is sent once and never retried.
- **The listing** is a `GET` of the account's activities. Its query carries
  only the date window and the field names above.

Every request carries your key as described under
[What a pull fetches](#what-a-pull-fetches). When a publish lands
(`posted` or `uploaded`), the answer carries a direct link to the activity,
labelled `intervals.icu`, which fitdocs records for the page and shows in its
published region.

The answer to each reply, by the kind of request. A dash means that the reply
fixes no code by itself: a success, or for an update a `404`, is decided by the
step, as in the notes below. The table applies to every request except the
update that follows an upload, which uses the Update column with two
exceptions, given below.

| Answer | Listing | Update | Upload |
|---|---|---|---|
| success | — | — | — |
| 401 | `auth_rejected` | `auth_rejected` | `auth_rejected` |
| 403 | `permission_denied` | `permission_denied` | `permission_denied` |
| 404 | `rejected` | — | `rejected` |
| 429 | `rate_limited` | `rate_limited` | `rate_limited` |
| other 4xx | `rejected` | `rejected` | `rejected` |
| 5xx | `unavailable` | `unavailable` | `unconfirmed` |
| other status | `unavailable` | `unconfirmed` | `unconfirmed` |
| network failure | `unavailable` | `unavailable` | `unconfirmed` |

A success is a `200` for the listing and the update, and a `200` or a `201`
for the upload; any other status outside the rows above is an "other status".

The codes are the ones in the
[outcome codes](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/publishing.md#outcome-codes).
For intervals.icu, in the order a publish meets them:

- **An update through the link, the pull record or the listing.** A success is
  `posted`, with the link. A `404` sets the activity aside and the search goes
  on. Any other reply follows the table's Update column.
- **A pull record that names several activities** for the page's base file,
  or, when it names none for it, for the page's other files, is `ambiguous`,
  and nothing is changed.
- **A page without the facts for a listing** is `activity_facts_missing`.
- **The listing.** A reply that is not a `200` follows the table's Listing
  column. A `200` whose body is not a list of activities, each with a usable
  id, is `unavailable`. That is why the Listing column has a dash for a
  success: a readable body is decided by the matching below.
- **The listing's match.** Several matching activities are `ambiguous`, and
  nothing is changed. When none matches but a Strava import starts within a
  second of the page's start, the answer is `not_updatable`.
- **Nothing found.** If the instance's ledger could not be read, the answer is
  `local_record_unreadable` (see below). Otherwise, with `publish_upload` off,
  it is `not_found`. With it on and no usable base file, it is
  `activity_file_missing`, and no upload is sent.
- **The upload.** A reply that is not a success follows the table's Upload
  column. A success reply that does not name exactly one activity, or names one
  that was set aside after a `404`, is `unconfirmed`.
- **The update after an upload** follows the table's Update column, with two
  exceptions. After a `201` (intervals.icu created the activity), a success is
  `uploaded`, with the link, and any other reply, including a `404` or a `429`,
  is `unconfirmed`. After a `200` (intervals.icu answered with an activity it
  already held), a success is `posted`, with the link, and a `404` is
  `unconfirmed`, so the search does not go on; any other reply follows the
  table.

`unconfirmed` means a request was sent but its result is not known. The next
publish searches again before it sends an upload.

If the instance's ledger cannot be read, an unreadable record never stops an
update through the recorded link or the listing: an activity found either way
is updated just as it is with a readable record. When neither finds the
activity, the answer is `local_record_unreadable` whether or not uploads are
on, never `not_found` and never an upload, because fitdocs cannot rule out that
the activity is already in the pull record. The earlier answers keep their own
codes: a listing that fails, or whose `200` body is unreadable, answers as
above; a listing that matches several activities is `ambiguous`; a Strava
import at the start is `not_updatable`; and a page without the facts for a
listing is `activity_facts_missing`. `fitdocs pull` on the same instance
reports the ledger file it cannot read and names it; fix or restore that file.

## Connecting

`fitdocs connect <name>` authenticates one configured instance and stores
what it needs to make requests later.

- An instance whose connector needs no authentication (like `folder`) prints
  that there is nothing to connect and exits.
- Otherwise, at an interactive terminal, fitdocs prompts for each credential
  field the connector declares — secret fields without echo — then makes one
  authentication attempt.
- At a non-interactive terminal (no TTY to prompt at), fitdocs exits `2`
  immediately instead of hanging; for an API-key-style connector, it also
  names the environment variable for each field you could set instead (see
  [Environment overrides](#credentials) below — a login-style connector has
  no such override, so none is named).
- On success, the credentials are saved and fitdocs prints where, and which
  scopes (if any) the attempt was granted.
- On refusal or an unreachable service, fitdocs prints what kind of failure
  it was, a redacted message, and a next step, then exits `1`. Nothing is
  written anywhere.

`fitdocs connect` writes only to the credentials store below. It never writes
anything under your data root.

## Credentials

Credentials live in one directory, entirely outside your data root, resolved
in this order:

1. `FITDOCS_CREDENTIALS_DIR`, if set to a non-empty value (which must then be
   an absolute path).
2. `$XDG_CONFIG_HOME/fitdocs/credentials`, if `XDG_CONFIG_HOME` is set to a
   non-empty absolute path.
3. `<your home directory>/.config/fitdocs/credentials` otherwise.

A directory that is, or lies inside, your data root is refused outright:
credentials must never travel with your notes, and must never end up in a
git repository or a shared wiki.

The directory is created accessible only to you (`0700`) the first time it's
needed. Separately, each instance gets its own file, written atomically and
readable and writable only by you (`0600`). A file any other account on the
machine could read or write is refused, naming the fix.

**Environment overrides.** For a connector whose credentials are simple,
non-rotating values (a personal API key, for example), each field can be
overridden by an environment variable instead of being stored on disk:

```
FITDOCS_CONNECTOR_<INSTANCE>_<FIELD>
```

with the instance name upper-cased (hyphens become underscores) and the
field name upper-cased. An instance named `myservice` with a credential
field named `api_key` reads `FITDOCS_CONNECTOR_MYSERVICE_API_KEY`; an
instance named `another-service` with a field named `client_secret` reads
`FITDOCS_CONNECTOR_ANOTHER_SERVICE_CLIENT_SECRET`. A variable that is set and
non-empty always wins over whatever is stored.

**The login-style limitation.** A connector whose authentication issues a
token that fitdocs itself rotates over time reads its credentials only from
the store — there is no environment override for it, because a rotated token
has nowhere to be written back to in the environment. Run `fitdocs connect`
for that kind of instance instead.

## Pulling

```
fitdocs pull [NAMES...] [--since YYYY-MM-DD] [--dry-run] [--sync] [--no-prompt]
```

- `NAMES`: pull only the named instances; omit to pull every configured
  instance whose connector pulls activities or wellness (see
  [Pulling a relay instance](#pulling-a-relay-instance)).
- `--since`: list only activities from the start of that local day onward
  (a connector that cannot filter by time lists everything regardless). It
  also starts the wellness listing on that date.
- `--dry-run`: list and report what would be fetched; writes nothing under
  the data root or the inbox. The one exception: if a login-style instance's
  access token needs renewing first, fitdocs still saves the renewed token to
  the credentials store (outside the data root) so the next command doesn't
  have to renew it again.
- `--sync`: after pulling, drain the inbox exactly as a bare `fitdocs sync`
  does, in the same run. Combined with `--dry-run`, fitdocs exits `2` before
  any network request instead — a dry run writes nothing, so there is
  nothing for the chained drain to do.
- `--no-prompt`: as with `fitdocs sync`, never prompt.

With no `[connectors]` table configured at all, `fitdocs pull --sync
--no-prompt` does exactly what `fitdocs sync --no-prompt` does — it prints
that no connectors are configured and still runs the drain.

`fitdocs pull` exits `0` when every instance completed without a failure
(deferrals and skips are not failures — see below); `1` when at least one
instance reported a failure, or, with `--sync`, the drain itself did; and `2`
for a configuration problem caught before any request or write (an unknown
instance name, an unparseable `--since`, and the like).

### Reading the report

Each instance gets its own table, with a row for every one of these
channels, always present (even at zero). The left column is the report
field's name; the right is the label the printed table shows for that row.

| Pull channel | Printed as | Meaning |
| --- | --- | --- |
| `listed` | Listed | How many remote activities the connector reported. |
| `delivered` | Delivered | Fetched and written into the inbox this run. |
| `would_fetch` | Would fetch | Under `--dry-run`, what would be fetched. |
| `held` | Already held | The remote id already has a final outcome in the ledger, or its bytes are already held — archived, or still pending in the inbox as an earlier delivery of this same instance. Nothing is delivered for it: an id already final in the ledger is not fetched at all, while one recognized by its bytes was fetched to compare them. A byte-identical file you dropped in by hand, sitting unarchived in the inbox, is not recognized this way: this check never scans the inbox for other files. It is left exactly where it is — never adopted into the ledger — and the fetched activity is delivered alongside it, under a content-derived name if your file occupies the name the delivery would otherwise take. |
| `skipped` | Skipped | The connector or fitdocs declined this one on purpose (not a FIT file, no original available, and similar). |
| `deferred` | Deferred | Not resolved yet — try again next time; not an error. |
| `failed` | Failed | This one activity could not be fetched or delivered. |
| `removed` | Removed | An earlier delivery of this instance's own, now archived, cleaned out of the inbox. |
| `error` | Error | The whole instance stopped early (for example, a rejected credential). Other configured instances still run. |

### Reading the wellness report

When wellness runs, a separate table follows the activity report, with all
eight rows even at zero. Day counts and file counts are distinct:

| Wellness channel | Printed as | Meaning |
| --- | --- | --- |
| `listed` | Days listed | Wellness days returned by the listing. |
| `unchanged` | Days unchanged | Days whose revision matches the ledger; no delivery needed. |
| `delivered` | Delivered | Calendar-year files written into the inbox this run. |
| `would_deliver` | Would deliver | New or changed wellness days that a dry run would deliver, listed by date. |
| `held` | Already held | Packaged files whose identical bytes are already archived or pending for this instance. |
| `failed` | Failed | Wellness days or calendar-year groups that failed; the next pull retries them. |
| `notices` | Notices | Attribution changes that may need the athlete to review import settings. |
| `error` | Error | The wellness step stopped early; activity results remain in their own table. |

## Delivery and removal

A fetched file is written atomically into `<inbox>/<name>/` under the
configured inbox, named from whatever hint the connector gave (or the remote
id), sanitized to a safe file name ending in `.fit`. If a file already holds
that name, it is reused in place — nothing new is written — only when this
instance itself recorded delivering these exact bytes at that name (still
pending in the ledger, or delivered earlier in the same run) **and** the
file at that name still holds them; any other file already at that name,
identical bytes or not, is left exactly as it is, and the delivery instead
gets a name derived from its own content, so a file you or your own tools
placed there — or an earlier delivery's file you overwrote — is never
adopted and two distinct files never collide.

If a later pull fetches the same remote activity again while its earlier
delivery is still sitting in the inbox (not yet archived): identical bytes
change nothing — the existing delivery stays exactly where it is, and the
activity is reported as `held`. Different bytes release the old copy — it
becomes an ordinary untracked inbox file for the drain to pick up on its own
— and the new bytes are delivered in its place, unless the archive, or another
of this instance's pending deliveries, already holds those exact bytes: then
nothing new is written, the ledger records the activity as already held, and
the report lists it as `held`, not `delivered`.

A pull that is killed outright (power loss or `kill -9`, not Ctrl-C or an
error, which still save the ledger) between writing a file and saving the
ledger leaves that file in the inbox with no ledger entry. The drain then
treats it as any other file you dropped in, and a pull never removes it; the
next pull fetches the same activity again and delivers a second copy —
unless the drain has archived the first copy by then, in which case it is
recorded as already held. A hidden `.<name>-….tmp` file can also remain
beside it; the drain ignores it and it can be deleted.

Once the drain has archived a pull's delivery, the archive holds a copy of
those exact bytes, and the *next* pull removes fitdocs's own now-redundant
copy from the inbox. A delivery that vanished before being archived is
forgotten. This check runs before the pull lists anything, so the same pull
fetches the activity again when its listing includes it: `folder` always
lists its whole source, while `intervals` lists from the watermark less
`lookback_days`. An `intervals` activity older than that window is not listed
again, so fetch it with `fitdocs pull intervals --since YYYY-MM-DD`, using a
date on or before the activity's. A delivery whose bytes changed
underneath fitdocs *after* being archived is released silently, with nothing
reported — it, too, becomes an ordinary file the drain can pick up. Only a
removal that actually fails, or a pending file that could not be read while
checking it, is reported, as a deferral. **Nothing you or your own tools put
in the inbox is ever touched by a connector** — only a connector's own prior
deliveries are ever candidates for removal. fitdocs recognizes its own
delivery by the path it wrote and the bytes it wrote there, not by which
program last wrote the file: a file holding exactly a still-pending
delivery's bytes, placed at that delivery's own path (after deleting or
overwriting it), cannot be told apart from it and is removed the same way
once the archive holds those bytes.

Wellness uses the same instance inbox subdirectory: one file per calendar
year of new or changed days, named
`wellness-<first-day>_<last-day><extension>`. The connector declares the
extension (`.json` for `intervals`); the package is checked by extension
before delivery; an invalid package is reported as failed. Name collisions
follow the same ownership and content-derived naming rules as activity files.
The next pull removes its own wellness delivery only once the wellness archive
holds identical bytes. If a wellness delivery disappears before archival,
its days are forgotten and the wellness mark moves back so they can be fetched
again. Pull writes neither the wellness archive nor the normalized series;
the drain handles those through `sync` or `pull --sync`.

## The ledger

Each instance keeps a small record at
`<data-root>/.fitdocs/connectors/<name>.toml` — fitdocs's own tool state,
alongside the quarantine record, never something you edit by hand. It
remembers, per remote activity, whether it was delivered, already held, or
skipped, and the content hash of what was delivered. A second pull against
the same source fetches nothing new: **the ledger decides what's new, not
the connector's listing.** Removing the ledger file makes fitdocs re-list
and re-fetch everything the connector currently reports; any deliveries
still sitting in the inbox are left exactly where they are (fitdocs can no
longer tell them from your own files, so no later pull removes them), and
a re-fetched activity whose bytes are not yet archived is delivered again
alongside them.

The `[wellness]` records hold the wellness mark, per-day revisions,
attribution and pending wellness deliveries. A ledger holding wellness
records uses format 2; an older fitdocs refuses it. Activity-only ledgers
keep their existing format until wellness records are first written.

Publishing to an [intervals.icu](#intervalsicu) instance reads that instance's
ledger and never writes it.

## What leaves your machine

The only requests any connector instance makes are the ones `fitdocs
connect <name>` (including a relay instance's registration), `fitdocs
disconnect <name>` (a relay revocation, unless `--local-only`), `fitdocs
pull` and `fitdocs publish --yes` make for that instance, while you are
running one of those four commands — carrying the one fitdocs User-Agent and
whatever credentials that instance needs (and, when a relay registration
starts, your email address).

An [intervals.icu](#intervalsicu) instance's publish requests go to
intervals.icu; what each one sends is described under
[Publishing](#publishing). `fitdocs publish` without `--yes` and `fitdocs
publish --targets` make no request, and no other fitdocs command ever makes a
connector request, configured or not.

The only other network access anywhere in fitdocs is fetching basemap map
tiles for an outdoor activity's Map section — see
[Configuration](configuration.md#tiles-the-map-tile-provider-and-the-offline-opt-out)
for what that sends and how to turn it off. Between the two, that is every
network request fitdocs ever makes.

To stop an instance from ever being contacted again, delete its
`[connectors.<name>]` table from `fitdocs.toml`. There is no separate
opt-out switch to find — an instance with no table simply isn't there for
any of those commands to use.

## The terms-first policy

fitdocs ships a connector for a given service only when that service's own
terms of use permit this kind of automated, personal access. The one
third-party service connector fitdocs ships is the [intervals.icu](#intervalsicu)
one. The [relay](#the-relay-connector) connector talks to a fitdocs relay (the
maintainer's, or one you or another operator run), not to a third-party
service's API. The only web addresses of online services this page gives are
intervals.icu's and the relay's.

## Regenerating before a first pull

fitdocs recognizes a fetched file whose bytes are already archived, or
still waiting in the inbox as an earlier delivery of the same instance —
that's the `held` channel above, and such a file is not delivered again.
Recognizing the *same activity* across two different files — a re-export
in a different format, or the same activity pulled from a second source —
is cross-source identity's job, not a connector's. A data root whose pages
predate cross-source identity is regenerated with `fitdocs regen` before
its first pull, so every existing page carries the identity information a
pulled duplicate needs to be recognized rather than turned into a second
page.

## Running on a schedule

`fitdocs pull` does not schedule itself — nothing in fitdocs watches a clock
or runs in the background. To pull on a schedule, invoke it the same way you
would `fitdocs sync`: from `cron`, or a `launchd` user agent, with
`--no-prompt` so it never waits on a terminal that isn't there:

```
fitdocs pull --sync --no-prompt
```

A `cron` line running that once an hour, with the data root set the same way
[`docs/install.md`](install.md) describes:

```
0 * * * * FITDOCS_DATA=/path/to/data-root /path/to/fitdocs pull --sync --no-prompt
```

## The relay connector

`relay` is the connector for a fitdocs relay: a small service that issues a
token and answers a few requests about it. It pulls nothing — it has no
activities or wellness to fetch — so `fitdocs pull` never contacts it
([Pulling a relay instance](#pulling-a-relay-instance) below). What it adds today is a token you connect once,
check, and can later revoke.

### The relay and its address

Add the instance to `<data-root>/fitdocs.toml`. The table can be empty,
because its one key is optional:

```toml
[connectors.relay]
url = "https://api.fitdocs.ai"   # optional; this is the default
```

`url` defaults to the maintainer's relay (https://api.fitdocs.ai). It must be
an absolute `https` address with no query, fragment, or user information; a
trailing slash is dropped. Plain `http` is accepted only for exactly
`localhost`, `127.0.0.1` and `::1`, which is for testing a relay you run
yourself. A refused `url` is reported by name; the message
never repeats the value, because an address may carry a password.

To use more than one relay, name each instance and set `connector = "relay"`
in its table, as for any other connector.

### The token

A relay token is a value the relay's operator issues, or that registration
issues to you (below). `fitdocs connect` stores it in the credentials store
described under [Credentials](#credentials), as `relay-token` style
credentials: one file per instance, outside your data root, readable only by
you.

A set, non-empty `FITDOCS_CONNECTOR_RELAY_TOKEN` (the instance's name,
upper-cased, then `TOKEN`) overrides the stored token wherever fitdocs
resolves the instance's credentials, as a personal key's variable does (see
[Credentials](#credentials)). It is how an unattended command supplies a
token: without a terminal, `fitdocs connect` exits `2` and names the variable,
except with `--register --email ADDRESS`. `fitdocs connect` prints the
variable's name when it is set. `fitdocs disconnect` revokes only the stored
token, never the variable; only when nothing is stored does it say the
variable is not revoked and remains set.

### Connecting by paste

```
fitdocs connect relay
```

At a terminal, fitdocs prompts `Relay token:` without echo, then makes one
request to check the token. The token is stored only when the relay accepts
it; on success fitdocs prints where, and the relay's address. A pasted value
that is not shaped like a relay token is refused before any request, with a
message that does not repeat it. A refusal or an unreachable relay prints the
relay's reason in fitdocs's own words and a next step, stores nothing, and
exits `1`. Connecting again replaces the stored token and revokes nothing.

### Connecting by registration

```
fitdocs connect relay --register [--email ADDRESS]
```

For a relay that offers registration, `--register` replaces the paste.
fitdocs prompts `Email address:` unless `--email` gave it, checks the
address's shape, and only then asks the relay whether it offers registration;
a relay that does not is reported as such, with a next step to ask its
operator for a token. Otherwise registration starts and fitdocs prints a
code:

```
Registering ADDRESS.
Your code: CODE
```

Confirm the registration at the relay's confirmation page **only if it shows
the same code**; that match is what stops someone else's registration from
being confirmed as yours. fitdocs polls the relay until the registration is
confirmed, refused, or expired (it prints how long that takes, and `fitdocs
connect relay --register` starts a new one), then stores the issued token.
Press Ctrl-C to stop waiting; nothing is stored.

`--register` and `--email` apply only to a relay instance, and `--email`
needs `--register`; either mistake exits `2` before any request. With
`--register --email ADDRESS` the command needs no terminal.

### Disconnecting

```
fitdocs disconnect relay
fitdocs disconnect relay --local-only
```

`fitdocs disconnect relay` asks the relay to revoke the stored token, then
removes the instance's credentials file. A token the relay reports as already
revoked or unknown is treated as revoked, and the file is removed. If the
relay cannot confirm the revocation, the file is kept exactly as it was and
the command prints the relay code, fitdocs's explanation and a next step (run
it again, or add `--local-only`), exiting `1`.

`--local-only` removes the file without contacting the relay and without
reading it, so it also removes a file fitdocs cannot read. It prints that the
token stays valid at the relay until its operator revokes it. Without a stored
file, the command says there is nothing to disconnect and exits `0`.

Disconnecting never removes anything else: not the credentials directory, not
another instance's file, nothing under your data root.

### What each command sends

Requests carry the one fitdocs User-Agent and go only to the instance's `url`.

- `fitdocs connect relay` (paste): one request carrying the pasted token as a
  bearer credential, to check it.
- `fitdocs connect relay --register`: a request asking what the relay offers,
  then your email address when registration starts, then repeated requests
  carrying a secret that identifies this registration until it ends. The
  issued token is received, never sent in those requests.
- `fitdocs disconnect relay`: one request carrying the stored token, to
  revoke it. The environment variable is never used here.
- `fitdocs disconnect relay --local-only`: nothing leaves your machine.

### Pulling a relay instance

A bare `fitdocs pull` (no names) pulls only the instances whose connector
fetches activities or wellness, so it skips a relay instance and never
contacts it. When instances are configured but none of them is such a
connector, it prints "No configured connector instance pulls activities or
wellness; nothing to pull." and exits `0`. With no connectors configured at
all, it still prints that none are configured. Naming an instance
(`fitdocs pull relay`) selects it and reports that it is not connected, or
that it does not pull activities or wellness, and exits `1`; it makes no
request either way.
