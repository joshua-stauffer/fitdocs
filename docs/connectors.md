# Connectors

A connector is a source fitdocs can pull `.fit` files from automatically. You
configure named **instances** of a connector in `<data-root>/fitdocs.toml`,
run `fitdocs connect` once for any instance that needs credentials, and run
`fitdocs pull` — by hand, or on a schedule — to fetch what's new. Everything a
pull delivers lands in the existing inbox, where the existing drain (`fitdocs
sync`, or `pull --sync`) picks it up exactly as it would a file you dropped
there yourself.

This page documents the connector *framework*: the commands, the settings
keys, the credential rules, and the two connectors fitdocs ships: `folder`,
which needs no service at all, and `intervals`, for an intervals.icu account
([its section](#intervalsicu) below). Outside that section, the framework
sections of this page describe no online service and no network protocol;
the one service they mention, intervals.icu, is named only to point to it.

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
| `lookback_days` | For a connector that supports it, how many days before the *watermark* — the newest activity already recorded — its listing starts. An instance's first pull, with no ledger yet, has no watermark, so this key does not apply: each connector chooses where such a pull starts (`folder` considers everything under its source; `intervals` starts as its [section](#intervalsicu) says). The `folder` connector ignores it; it always considers everything under its source. | `30` |

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
  to the inbox's own default.

`folder` only ever reads from its source directory — it never writes, moves,
renames, or deletes anything there.

## intervals.icu

`intervals` is the connector for an [intervals.icu](https://intervals.icu)
account. It pulls only: it lists the activities of the account the key
belongs to and fetches each one's original `.fit` file. It never writes to the
account.

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
[Configuring an instance](#configuring-an-instance); no other key is read.

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
  fitdocs's own retries, the pull stops and says so; the next pull resumes
  where it stopped. This page states no request limits: intervals.icu
  decides them.
- **An unavailable service.** Handled the same way: the pull stops, and the
  next one resumes.

What leaves your machine. Requests go to intervals.icu only. Each carries the
one fitdocs User-Agent and, in the `Authorization` header, your key. The key
is sent to intervals.icu itself and never to the target of a redirect, and it
never appears in an address. The addresses carry date bounds and activity
ids.

What you get. The file a pull delivers is the copy intervals.icu holds. For an
activity whose source is `GARMIN_CONNECT` (the default), that is Garmin's own
partner-API copy of a ride recorded on a Garmin device. It is not
byte-identical to the file the device itself wrote, but it carries the
same messages, so a page that holds both reads the same whichever of the two
is its base. Before the first pull into a data root that already holds
pages, run `fitdocs regen`, so that the pages written before cross-source
identity are recognized when the same ride arrives; see
[Regenerating before a first pull](#regenerating-before-a-first-pull).

### Garmin attribution

A page rendered from a file recorded by a Garmin device carries the line
`Data source: Garmin <model>` directly beneath its title, where `<model>` is
the device's product name, as recorded in the file or, for a Garmin
product code, as the FIT SDK's profile names it (just `Garmin` when neither
gives one).
The line is rebuilt on every render, so `fitdocs regen` adds it to existing
pages.

A page that takes channels from other files of the same workout counts every
file that donates a channel alongside its base (a file that donates nothing is
not counted). The line names each distinct Garmin recording device among those
files, the base's first, and ends with `and other devices` when any of them was
not recorded by a Garmin device: for example
`Data sources: Garmin <model> and other devices`, or
`Data sources: Garmin <model> and Garmin <other model>` when two Garmin models
contribute. A model recorded by two of the files is named once. A page none of
whose counted files was recorded by a Garmin device carries no line.

The reason is the terms the data comes under: intervals.icu's API terms,
§1.1 (effective 2025-10-23), and Garmin's API Brand Guidelines, version
V 6.30.2025. The line applies to every Garmin-recorded file, however it
reached your data root, whether pulled by this connector or dropped in the
inbox by hand.

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
  instance.
- `--since`: list only activities from the start of that local day onward
  (a connector that cannot filter by time lists everything regardless).
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
— and the new bytes are delivered in its place.

Once the drain has archived a pull's delivery, the archive holds a copy of
those exact bytes, and the *next* pull removes fitdocs's own now-redundant
copy from the inbox. A delivery that vanished before being archived is
simply forgotten, and fetched again on a later pull; one whose bytes changed
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

## What leaves your machine

The only requests any connector instance makes are the ones `fitdocs
connect <name>` and `fitdocs pull` make for that instance, while you are
running one of those two commands — carrying the one fitdocs User-Agent and
whatever credentials that instance needs. No other fitdocs command ever
makes a connector request, configured or not.

The only other network access anywhere in fitdocs is fetching basemap map
tiles for an outdoor activity's Map section — see
[Configuration](configuration.md#tiles-the-map-tile-provider-and-the-offline-opt-out)
for what that sends and how to turn it off. Between the two, that is every
network request fitdocs ever makes.

To stop an instance from ever being contacted again, delete its
`[connectors.<name>]` table from `fitdocs.toml`. There is no separate
opt-out switch to find — an instance with no table simply isn't there for
either command to use.

## The terms-first policy

fitdocs ships a connector for a given service only when that service's own
terms of use permit this kind of automated, personal access. The one service
connector fitdocs ships is the [intervals.icu](#intervalsicu) one, and the
only web address of an online service this page gives is intervals.icu's.

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
