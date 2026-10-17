# Inbox

fitdocs defines a standing inbox: get workout `.fit` files and supported
wellness exports there, however you like —
HealthFit → iCloud, watch sync, a manual drop, your own script — and
`fitdocs sync`, run with no arguments, drains it. `fitdocs sync SOURCE` keeps
working exactly as before and never reads the inbox or its settings.

**Delivering files is your concern, unless you configure a connector. fitdocs
performs no watching and no scheduling of any kind** — there is no daemon, no
filesystem watcher, and no background process. A drain happens only when
`fitdocs sync` is invoked, one shot, by you, your cron job, or your wiki
agent.

## Default location and configuration

The inbox is configured in the `[inbox]` table of `<data-root>/fitdocs.toml` —
the same user-owned, fitdocs-only-reads settings file `[tiles]` and
`[plugins]` share. Every key is optional and defaults independently; omit the
table entirely to accept every default below.

| Key | Meaning | Default |
|-----|---------|---------|
| `path` | The inbox location. An absolute path is used as given; a relative path resolves against the data root. Created automatically if it lies inside the data root and is missing; an absent path outside the data root is a configuration error (guarding against typos and unmounted cloud storage). | `"inbox"` (i.e. `<data-root>/inbox/`) |
| `settle_seconds` | The stability-check settle interval, in seconds. `0` disables the wait entirely. | `2` |
| `ignore` | Additional glob patterns to ignore, matched against a candidate's basename or inbox-relative path (case-normalized). Applied *in addition to* the built-in ignore rules described under Safeguards below, never in place of them. | `[]` (no additional patterns) |
| `disposition` | What happens to a file once it has been successfully processed: `"leave"` (never touch it) or `"move"` (relocate it to `processed_dir`). Deletion is not a disposition fitdocs offers under any configuration. | `"leave"` |
| `processed_dir` | The processed-files destination; required when `disposition = "move"`, and must not equal or be nested inside the inbox. Same resolution and auto-creation rule as `path`. | `null` (unset) |

## Drain semantics

Bare `fitdocs sync` drains the resolved inbox exactly once: it selects
eligible workout and wellness candidates and applies one stability check to
the combined batch. It recognizes and archives stable wellness exports,
rebuilds the daily series when archive inputs or settings change, then
processes workout FIT files through the explicit-source `sync` pipeline.
Successful archives use the configured disposition; the usual training-load
and later refresh passes follow.

The run's output names the inbox path being drained. The report always
prints twelve channels: Written, Skipped, Failed, Warnings, Deferred,
Quarantined, Moved, Move failures, Unrecognized, Wellness archived, Wellness
skipped and Wellness failed. The four wellness channels include details when
nonempty. A changed wellness series adds a summary of its status, changed
values and days,
written or removed series paths, notes and conflict counts. A workout
failure, wellness failure, failed series rebuild, load failure or plan
failure makes the drain fail; unrecognized, deferred and already-quarantined
files alone do not. An inbox with no eligible files reports no workout
writes; series and later refresh passes can still run. `--out`, `--force`,
and `--no-prompt` all keep their explicit-source meanings on a drain.

An Apple Health import can take minutes; on a terminal, progress shows the percentage
of its main XML document read.

## Safeguards

**Ignore rules.** Regular `.fit` files are workout candidates. Wellness
candidates use the supported formats' extensions, currently `.json`, `.zip` and
`.xml`, with case-insensitive matching. Both selectors exclude symlinks and share the
same ignore rules. Any candidate whose inbox-relative path has a path
component starting with a dot is ignored — this covers hidden files,
AppleDouble `._*` companions, and everything inside a hidden sync-tool staging
directory (for example `.stversions/`). A configured `ignore` pattern is checked in addition
to that dot-component rule and does exclude matching candidates. Ignored
files are excluded from processing entirely; they are never reported as
failures. To silence an unwanted file, add its basename or relative path to
the user-owned settings, for example:

```toml
[inbox]
ignore = ["unrelated.json", "garmin-export.zip", "unrelated.xml", "old-exports/*"]
```

**Wellness intake.** A supported extension makes a file a candidate, not a
recognized format. Structure (and, for empty Garmin lists, the filename)
selects the format. An unrecognized file is reported with a reason, stays in
the inbox, is not quarantined and is reconsidered on the next drain. Tell
the user; never delete it to silence the report. Recognition or archive
access problems that prevent a safe attempt defer the file. A recognized
file that fails parsing is reported as Wellness failed and quarantined by
content hash; a successful parse is Wellness archived, and content already
present is Wellness skipped. Corrected bytes are new content and need no
retry flag. See the [wellness guide](wellness.md) for the supported exports,
source definitions, [wellness-day rule](wellness.md#wellness-day), precedence
and series readers. The standalone [`fitdocs recovery`](recovery.md) command
turns the series into a recovery page; morning-of workout blocks remain future work.
Other ZIP files (including Garmin export ZIPs) and unrelated XML are reported as
unrecognized and left in place; silence them with `[inbox] ignore`.

**Non-activity FIT files.** A FIT header declaring a type other than
`activity` is skipped with a warning: fitdocs creates no workout page and
leaves the file where it is, including under the move disposition when a
legacy archive copy exists. Activity headers and files with no usable type
keep the normal workout path. These skips are neither failures nor
quarantine entries. `fitdocs regen` skips unlisted non-activity archive
inputs, but keeps and rebuilds a page that already lists one. Under
`sync --force`, such an existing page is left untouched.

**Stability check.** Before a candidate is processed, fitdocs verifies it is
stable: its size and modification time are observed twice, separated by the
`settle_seconds` interval (once per drain for the whole batch of candidates,
never once per file). A candidate that changes or disappears between the two
observations is deferred — left completely untouched and reported by name —
and is simply re-considered, with no memory of the deferral, on the next
drain. `settle_seconds = 0` disables the wait and admits every candidate that
can be observed once.

**Quarantine record.** A file that fails processing because of a source-
level fault — the `.fit` bytes themselves cannot be decoded or parsed, or a
recognized wellness export cannot be parsed — is recorded by content hash,
name, and failure reason in `<data-root>/.fitdocs/quarantine.toml`. A
subsequent drain reports it once from that record, in its own `quarantined`
channel, without re-processing it or failing the run on its account — so a
known-bad file is surfaced once and then remembered rather than looping as a
fresh failure on every scheduled run. The record is keyed on content, not
name: a same-named file with different bytes is treated as new without a
retry flag; the old bad hash remains recorded. A failure that is instead a
property of an *existing document* — a damaged preserved region being the
representative case — is reported as a failure but is **not** recorded in
the quarantine, so simply repairing the document is enough to make the next
drain succeed. Pass `--retry-quarantined` to re-attempt every currently
quarantined inbox file: a renewed success clears that content hash's entry,
and a renewed failure updates it. For the same wellness bytes, retry after
the cause of the parse failure has been fixed; replacing the export's bytes
is already a new attempt.

## Disposition policy

The default disposition, `"leave"`, never writes, moves, renames, or deletes
an inbox file — processed files are simply left where they are, and the
archive's content dedupe makes subsequent drains skip them. **No configuration
ever deletes an inbox file: deletion is not an option fitdocs offers, under
any disposition.** The opt-in `"move"` disposition relocates a file out
of the inbox to `processed_dir` only once its content is confirmed present in
the appropriate archive (`fit-archive/` or `wellness-archive/`), preserving
both files on a name collision rather than ever
overwriting. A detected non-activity FIT file or an unrecognized wellness
candidate is never moved, even when a legacy FIT archive entry exists. A file
that failed, was deferred, was quarantined, or whose
processing was skipped without an archived copy — including a document whose
existing `doc_version` is newer than this fitdocs produces — is never moved:
**it stays in the inbox and is retried on the next drain.** That includes a
file whose document could not be updated for any reason; leaving it in place
is what makes the retry possible.

**Connector deliveries are the one carve-out.** The drain itself never
deletes anything — this is unchanged. A file `fitdocs pull` delivered under
`<inbox>/<name>/` is fitdocs's own copy of bytes already recorded in that
connector's ledger, not something you or your tools put there, and the
*next* pull removes it once the archive holds an identical-content copy.
Nothing you or your own tools put in the inbox is ever removed — only a
connector's own prior deliveries, already archived, are ever candidates for
removal. (fitdocs recognizes a delivery by its path and its bytes, so a file
you place at a still-pending delivery's own path holding exactly the bytes
delivered there counts as that delivery.)

**Held files.** A file that cannot be placed with certainty — its workout
matches two or more existing pages, or files of two different workouts in the
same run match the same page — is archived and held rather than added to a
page: fitdocs writes no page for it and records the hold in
`<data-root>/.fitdocs/held.toml`. A held file is archived and disposed of like
any processed file — left in place under the default `"leave"`, or moved to
`processed_dir` under `"move"` — and is never quarantined; a drain counts it among the skipped files, not among the
failures. `fitdocs check` lists each held file with the action that resolves
it.

## Ownership of the locations the inbox uses

The inbox directory and its optional `processed_dir` destination are
**user-configured locations fitdocs may create**, exactly as the
[published ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
defines that category: fitdocs may create and write there because your
settings name them, not because they are part of the fixed owned-path set.
The quarantine record's directory, `<data-root>/.fitdocs/`, is **tool-owned
state** — one of the fixed paths the ownership contract already lists fitdocs
as owning outright.
