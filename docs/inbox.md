# Inbox

fitdocs defines a standing inbox: get `.fit` files there, however you like —
HealthFit → iCloud, watch sync, a manual drop, your own script — and
`fitdocs sync`, run with no arguments, drains it. `fitdocs sync SOURCE` keeps
working exactly as before and never reads the inbox or its settings.

**Delivering files is entirely your concern. fitdocs performs no watching and
no scheduling of any kind** — there is no daemon, no filesystem watcher, and
no background process. A drain happens only when `fitdocs sync` is invoked,
one shot, by you, your cron job, or your wiki agent.

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
eligible candidates, applies the stability check, processes each stable
candidate through the same per-file pipeline an explicit-source `sync` uses,
then applies the configured disposition and runs the usual training-load
pass. The run's output names the inbox path being drained alongside the
existing written/skipped/failed summary, extended with deferred, quarantined,
moved, and failed-move counts. An inbox with no eligible files completes
successfully, reporting nothing written. `--out`, `--force`, and
`--no-prompt` all keep their explicit-source meanings on a drain.

## Safeguards

**Ignore rules.** Only regular files with a `.fit` extension (case-insensitive)
are candidates. Any candidate whose inbox-relative path has a path component
starting with a dot is ignored — this covers hidden files, AppleDouble `._*`
companions, and everything inside a hidden sync-tool staging directory (for
example `.stversions/`). A configured `ignore` pattern is checked in addition
to that dot-component rule and does exclude matching candidates. Ignored
files are excluded from processing entirely; they are never reported as
failures.

**Stability check.** Before a candidate is processed, fitdocs verifies it is
stable: its size and modification time are observed twice, separated by the
`settle_seconds` interval (once per drain for the whole batch of candidates,
never once per file). A candidate that changes or disappears between the two
observations is deferred — left completely untouched and reported by name —
and is simply re-considered, with no memory of the deferral, on the next
drain. `settle_seconds = 0` disables the wait and admits every candidate that
can be observed once.

**Quarantine record.** A file that fails processing because of a
source-level fault — the `.fit` bytes themselves cannot be decoded or
parsed — is recorded by content hash, name, and failure reason in
`<data-root>/.fitdocs/quarantine.toml`. A subsequent drain reports it once
from that record, in its own `quarantined` channel, without re-processing it
or failing the run on its account — so a known-bad file is surfaced once and
then remembered rather than looping as a fresh failure on every scheduled
run. The record is keyed on content, not name: a same-named file with
different bytes is treated as new. A failure that is instead a property of
an *existing document* — a damaged preserved region being the representative
case — is reported as a failure but is **not** recorded in the quarantine, so
simply repairing the document is enough to make the next drain succeed. Pass
`--retry-quarantined` to re-attempt every currently quarantined inbox file: a
renewed success clears its entry, and a renewed failure updates it.

## Disposition policy

The default disposition, `"leave"`, never writes, moves, renames, or deletes
an inbox file — processed files are simply left where they are, and the
archive's content dedupe makes subsequent drains skip them. **No configuration
ever deletes an inbox file: deletion is not an option fitdocs offers, under
any disposition.** The opt-in `"move"` disposition relocates a file out
of the inbox to `processed_dir` only once its content is confirmed present in
the archive, preserving both files on a name collision rather than ever
overwriting. A file that failed, was deferred, was quarantined, or whose
processing was skipped without an archived copy — including a document whose
existing `doc_version` is newer than this fitdocs produces — is never moved:
**it stays in the inbox and is retried on the next drain.** That includes a
file whose document could not be updated for any reason; leaving it in place
is what makes the retry possible.

## Ownership of the locations the inbox uses

The inbox directory and its optional `processed_dir` destination are
**user-configured locations fitdocs may create**, exactly as the
[published ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
defines that category: fitdocs may create and write there because your
settings name them, not because they are part of the fixed owned-path set.
The quarantine record's directory, `<data-root>/.fitdocs/`, is **tool-owned
state** — one of the fixed paths the ownership contract already lists fitdocs
as owning outright.
