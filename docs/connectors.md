# Connectors

A connector is a source fitdocs can pull `.fit` files from automatically. You
configure named **instances** of a connector in `<data-root>/fitdocs.toml`,
run `fitdocs connect` once for any instance that needs credentials, and run
`fitdocs pull` — by hand, or on a schedule — to fetch what's new. Everything a
pull delivers lands in the existing inbox, where the existing drain (`fitdocs
sync`, or `pull --sync`) picks it up exactly as it would a file you dropped
there yourself.

This page documents the connector *framework*: the commands, the settings
keys, the credential rules, and the one connector fitdocs ships that needs no
service at all (`folder`). It names no online service and no network
protocol — this release includes no connector to any online service.

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
| `lookback_days` | For a connector that supports it, how many days before the *watermark* — the newest activity already recorded — its listing starts. An instance's first pull, with no ledger yet, lists everything regardless of this key. The `folder` connector ignores it; it always considers everything under its source. | `30` |

Any other key in the table is passed to the connector itself; each connector
documents its own keys (`folder`'s are below). A key that collides with one
of a connector's own *credential* field names is refused — credentials never
belong in this file (see [Credentials](#credentials)).

## The folder connector

`folder` is the one connector this framework ships: a local directory as a
source, requiring no authentication and making no network request of any
kind.

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
terms of use permit this kind of automated, personal access. This page
documents the framework only; it names no online service and no endpoint of
one, because this release includes no connector to any online service.

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
