# fitdocs Ownership Contract

**Contract version:** `3`

**What changed at this version:** two new owned paths, `history/` and
`history/assets/`, and a third declared directory alongside `workouts/` and
`fit-archive/` — the data root now also carries a second published document
type, `training-history` (see
[A Second Document Type: Training History](#a-second-document-type-training-history)
below), rendered by `fitdocs history` rather than by `sync` or `regen`.

This document is the authoritative, published statement of what fitdocs owns
in your data root, what you own, and the exact limits of every operation that
writes there. It is restated, in shorter form, inside the three owned
directories a human or agent browses (`workouts/AGENTS.md`,
`fit-archive/AGENTS.md`, and `history/AGENTS.md` — each generated on the
first `sync` or `regen` run, or the first `fitdocs history` run that has a
page to write, because all three refresh every declared directory's file
when they write, not only the one their own output lands in) and stamped
onto every generated document as a provenance banner —
the `AGENTS.md` texts and the provenance banner are generated from the same
code-level constants. This document's own enumerated lists (owned paths,
preserved regions, managed keys, and the contract version above) are held
equal to those same constants by a conformance test; its narrative
paragraphs are reviewed by hand at each contract-version bump.

The version above changes whenever a guarantee stated in this document
changes — a new owned path, a changed overwrite rule, a different managed
key set, a new class of user-owned frontmatter key, or a new document type
the data root contains. It is distinct from a document's own `doc_version`
(see
[Document-Format Versions and Migration](#document-format-versions-and-migration)
below), which versions the file format, not this contract's guarantees —
and the `training-history` page does not use `doc_version` at all (see that
section for what it uses instead).

## Owned Paths

fitdocs creates, writes, and deletes files only under the following
data-root-relative directories, and states plainly: **fitdocs writes nowhere
else** under the data root except these paths and the configured locations
named in the next section.

- `workouts/` — one generated markdown document per workout.
- `workouts/assets/` — chart images (SVG) referenced by workout documents.
- `history/` — one longitudinal training-history document, rewritten in full
  by every `fitdocs history` run (see
  [A Second Document Type: Training History](#a-second-document-type-training-history)
  below).
- `history/assets/` — the chart image (SVG) referenced by the training-history
  document.
- `fit-archive/` — the immutable archive of every `.fit` source fitdocs has
  processed, named by content hash.
- `.cache/` — re-fetchable, re-derivable cache state (today: basemap tiles).
  Deleting anything under here costs only work, never data.
- `.fitdocs/` — tool-owned run state under the data root that is not a
  document, an asset, an archived source, or a cache entry (for example, a
  future ingestion feature's quarantine record). Dot-prefixed because nobody
  browses it; it carries no ownership declaration of its own.

Two files at the top of the data root are explicitly **not** owned by
fitdocs even though fitdocs reads and, in one case, writes into them —
`fitdocs.toml` and `athlete.toml`. Both are covered under
[Shared and User-Owned Files](#shared-and-user-owned-files) below, not here,
because "owned" in this contract means "fitdocs may create, rewrite, or
delete wholesale, on its own initiative." `fitdocs.toml` is never written
at all. `athlete.toml` fitdocs does create when absent and does rewrite in
full -- but only key-wise, at your request, preserving every key it does
not manage; it is never deleted. See
[Shared and User-Owned Files](#shared-and-user-owned-files) for the exact
guarantee, including what re-serialization does not preserve.

## A Second Document Type: Training History

The data root now carries a second kind of fitdocs-generated document,
`training-history` (`type: training-history` in its frontmatter), alongside
the per-workout documents (`type: workout`) under `workouts/`. It lives at
`history/training-load-history.md`, with its chart image at
`history/assets/training-load-history-fitness.svg`, and is published by the
`fitdocs history` command and the history package rather than by the
document-contract leaf (`src/fitdocs/contract.py`) that defines the workout
vocabulary: the leaf is owned by a different spec in this development wave,
and a second spec adding a second document type's vocabulary to that same
leaf in the same wave is exactly the ownership conflict fitdocs' boundary
rules are meant to prevent, so the training-history document declares its own
vocabulary (`type`, `history_version`, and the rest of its frontmatter keys)
in its own module instead.

The training-history page carries **no user-owned region and no user-owned
frontmatter key** — nothing under `history/` is a place to hand-author
content, unlike the `notes`/`workout` regions and the effort-tag keys a
workout document reserves. It is **rewritten in full on every `fitdocs
history` run**: there is no partial merge, no carried-over content, and
no `--force` or `--recompute` option, because there is nothing on the page
a re-run could discard. Deleting it loses nothing that cannot be
regenerated from the workout documents already in `workouts/` — see
[Document-Format Versions and Migration](#document-format-versions-and-migration)
below for how its own `history_version` key differs from the `doc_version`
every workout document carries.

## Configured Locations fitdocs May Create

A location your `fitdocs.toml` settings file names as a place fitdocs should
write is created and written by fitdocs **because that configuration grants
the right** — not because the location is one of the fixed owned paths
above. No fitdocs feature names such a location yet; the planned ingestion
feature's intake directory and its optional `processed/` destination will be
the first. When a setting names one, this rule — not the fixed owned-path
set — is what grants fitdocs the right to create and write there.

Three things follow from that. These locations are named in your settings
file (`fitdocs.toml`), not fixed by this contract — nothing in this document
enumerates them, because they vary by installation. Configuring one such
location **widens nothing else**: it does not grant fitdocs any right
outside that specific configured path, and it does not add to, or change
the meaning of, the fixed owned-path set above. The full set of places a
given run of fitdocs may write is therefore always *the owned paths above,
union whatever your settings currently configure* — never more.

## User-Owned and Tool-Filled Regions

Every generated workout document reserves a small number of named regions,
delimited by HTML-comment markers, that regeneration always carries over
verbatim rather than replacing:

- `notes` — user-owned. Free-form notes about the workout. fitdocs writes an
  instructive placeholder into a brand-new document and never touches this
  region again.
- `workout` — user-owned. The workout as actually performed (used by
  strength documents to record exercises, sets, reps, and load). Like
  `notes`, fitdocs writes only the initial placeholder and never overwrites
  hand-authored content.
- `load` — tool-filled. The training-load pass writes into this region, but
  regeneration still carries its existing content over rather than
  overwriting it, on the same footing as the user-owned regions.

Not every document reserves every region — only a strength document's
`workout` region is emitted, for example. The region markers actually
present in a given document are authoritative for which of them it reserves;
check the document itself rather than assuming.

To edit a user-owned region, edit the text between its `<!-- fitdocs:begin:
... -->` and `<!-- fitdocs:end:... -->` markers directly. Never add a region
marker to a document that does not already have one: `regen`/`sync` refuse
to rewrite a document whose existing markers name a region the fresh render
does not, so an added marker blocks that document's regeneration until it is
removed by hand.

## What Regeneration Replaces and Preserves

Regeneration (`fitdocs regen`, and the rewrite path inside `fitdocs sync`)
replaces **everything outside the preserved regions and the user-owned
frontmatter keys**: the rest of the frontmatter block, the document body,
the provenance banner, and every chart asset. It carries **every preserved
region's content over verbatim** — `notes`, `workout`, and `load` — and
every [user-owned frontmatter key](#user-owned-frontmatter-keys)'s line
over verbatim alongside them, including while forced re-processing
(`--force`) is in effect. There is no operation that discards user-owned
region or frontmatter-key content; see
[Overwrite Semantics](#overwrite-semantics-of-every-writing-operation) below
for the one honest exception to this guarantee (a *deleted* document has no
content to preserve).

## Frontmatter Ownership

The frontmatter block of a generated workout document is tool-owned, **except**
the [user-owned frontmatter keys](#user-owned-frontmatter-keys): those keys
are carried over verbatim, unchanged, in the order they appeared in the
document being regenerated. Two distinct operations write to the block, each
with its own placement rule for the carried lines:

- **A full rebuild** — every `regen`, and the rewrite path inside `sync` —
  rewrites every managed key *except* the three the training-load pass owns
  (below) from a single `yaml.safe_dump`, then places the carried
  user-owned lines immediately after that block and before the closing
  fence; any key that is neither managed nor user-owned is dropped, not
  rewritten (see [Managed Frontmatter Keys](#managed-frontmatter-keys)
  below). `load_value`, `load_methodology`, and `load_basis` are not part of
  what this step writes, so the rebuilt block never contains them: any
  existing occurrences of those three lines are dropped along with the rest
  of the old block, the same as any other key this step does not manage.
  Whether they come back afterward is a question for the training-load
  pass that runs next (see the next bullet), and for which documents
  that pass can and cannot restore them on, see the `load` and
  `regen` entries under
  [Overwrite Semantics](#overwrite-semantics-of-every-writing-operation).
- **The training-load pass** (`fitdocs load`, and the pass `sync` and `regen`
  each run automatically once their own rebuild finishes) never re-serializes
  the block. It only upserts its own three keys: it removes any existing
  `load_value` / `load_methodology` / `load_basis` lines and appends fresh
  ones immediately before the closing fence, after every other line already
  there — including a user-owned line a preceding rebuild just placed. So on
  a document that carries both a user-owned key and a computed load result,
  the load keys are the ones that end up *last*, after the carried lines —
  the opposite of every other managed key's position, and true regardless of
  whether that load computation was triggered by a standalone `fitdocs load`
  or ran automatically inside `sync`/`regen`.

## Managed Frontmatter Keys

The complete set of keys fitdocs manages on a workout document — every key
it writes and will restore on the next `regen`, including the three keys
the training-load pass writes — is:

- `avg_hr_bpm`
- `avg_power_w`
- `calories_kcal`
- `date`
- `distance_km`
- `doc_version`
- `elevation_gain_m`
- `generator`
- `indoor`
- `load_basis`
- `load_methodology`
- `load_value`
- `modality`
- `moving_time`
- `sources`
- `sport`
- `start_time`
- `title`
- `type`
- `uuid`

Any key that is neither managed nor listed under
[User-Owned Frontmatter Keys](#user-owned-frontmatter-keys) below is
**unmanaged**: fitdocs did not write it and will drop it the next time that
document is rewritten. If a regeneration would drop an unmanaged key,
fitdocs reports the affected document and the dropped key names as a
warning before proceeding — the run still succeeds, but you get a chance to
notice.

The supported places for hand-authored content in a generated document are
the `notes` region (or, for a strength document, the `workout` region) and
the user-owned frontmatter keys below — not the rest of the frontmatter
block. Anything else you add to frontmatter directly should be treated as
temporary: it survives only until the document is next regenerated.

## User-Owned Frontmatter Keys

In addition to the [user-owned regions](#user-owned-and-tool-filled-regions)
above, fitdocs recognizes one class of user-owned *frontmatter keys*: the
four keys of the [effort tag](#the-effort-tag), a hand-added mark of a race,
test, or otherwise maximal effort.

- `effort`
- `effort_distance_m`
- `effort_time_s`
- `effort_event`

fitdocs **never writes** any of these keys — not from the activity, not
from the athlete profile, not from a computed value, and not as a default.
A document that carries none of them is simply untagged: there is no
placeholder, no empty value, and no default written for any of them. Once
you add one by hand, its frontmatter line — including any continuation
lines its value spans, for example a multi-line `effort_event` block
scalar — is carried forward byte-for-byte through every operation that
rewrites the document:
`sync`, `sync --force`, `regen`, and the training-load pass (`load`,
including `load --recompute`). This holds regardless of whether the tag is
well-formed: a malformed tag (see [The Effort Tag](#the-effort-tag) below)
is preserved exactly as written, never dropped, corrected, or replaced —
only reported.

When a document's frontmatter block is *rebuilt in full* (`regen`, and the
rewrite path inside `sync`), the carried user-owned lines are placed after
every key that rebuild writes and before the closing fence, in the order
they appeared in the document being regenerated. That rebuild never writes
`load_value` / `load_methodology` / `load_basis`, so this does not describe
where those three end up: the training-load pass listed above writes them
separately, by a different rule, and places them *after* the carried
user-owned lines instead — see
[Frontmatter Ownership](#frontmatter-ownership) above for the full picture.

To edit a user-owned key, edit its line directly, the same as any other
frontmatter key — there is no separate region syntax for these. A comment
line (a line whose first non-space character is `#`) immediately following
a user-owned key's line is treated as part of that key's entry and carried
along with it, exactly like a continuation line.

**Known limitation:** if a document's frontmatter carries the same
user-owned key more than once — a state only a hand edit can produce, since
fitdocs never writes these keys itself — every occurrence's lines are
carried forward on regeneration, but the reader that interprets the effort
tag reads only the last occurrence's value; the duplicate is not reported
as an error.

**Deleted-document exception:** like the user-owned regions, a user-owned
key's content is *copied forward from the existing document*, not derived
from the archive. If a document is deleted from `workouts/` and later
regenerated, the regenerated document is untagged, with no warning — the
same exception [stated for regions](#overwrite-semantics-of-every-writing-operation)
applies here.

## The Effort Tag

The effort tag is a hand-added mark that a workout was a race, a
certification test, or otherwise a maximal or near-maximal effort, so that
later features can find your dated best performances without reading your
notes. It attaches to any workout document, regardless of sport or
modality, and in this version of fitdocs it has **no consequence**: nothing
computed, rendered, or charted changes because a document carries one. It
exists for downstream features — such as benchmark derivation — to read.

A tag is recognized once you add any of the four keys above by hand. It is
one of three things: **absent** (none of the four keys present — an
ordinary, untagged document), **valid** (every effort key present satisfies
its rule below), or **malformed** (at least one does not). A malformed tag
is never silently read as absent and never silently repaired.

### Kinds

The `effort` key accepts exactly one of three values, matched exactly and
case-sensitively:

| Kind | Meaning |
|------|---------|
| `race` | A competitive race result. |
| `test` | A certification or benchmark test (for example a time trial). |
| `hard` | A hard effort that was neither a race nor a formal test. |

Any other value of `effort` is malformed, never a fourth kind.

### Fields

| Key | Unit | Rule |
|-----|------|------|
| `effort` | — (one of `race`, `test`, `hard`) | Required whenever any other effort key is present. |
| `effort_distance_m` | metres | A positive, finite number. Requires `effort_time_s` to also be present — a course distance is an official result only together with its time. |
| `effort_time_s` | seconds | A positive, finite number. May stand alone (without `effort_distance_m`) — a timed test protocol has a duration and no course. |
| `effort_event` | — (text) | Text whose value is non-empty after stripping leading/trailing whitespace (a whitespace-only value is malformed); stored exactly as written, unstripped. A wikilink such as `[[Boston Marathon 2024]]` must be quoted, or YAML reads it as a list rather than text. |

A number typed as text (for example a quoted `"42.2"`) is never parsed into
a number — fitdocs does not coerce a malformed value into a valid one.
`effort_event`'s text, including a wikilink, is kept exactly as written:
fitdocs never creates, resolves, or verifies the linked page.

### Malformed Tags

A malformed tag — an unknown `effort` value, a value of the wrong type, a
non-positive or non-finite number, empty event text, a distance without a
time, or an effort field present without `effort` — is:

- preserved exactly as written (see
  [User-Owned Frontmatter Keys](#user-owned-frontmatter-keys) above) — never
  dropped, corrected, or replaced, and not in effect until you fix it;
- reported by `fitdocs check` as a finding of its own kind, distinct from
  the unmanaged-key finding, naming the offending key(s) and what was
  expected;
- reported by `sync` and `regen` as a warning naming the document and the
  offending key(s) when either rewrites that document — the run still
  succeeds.

A well-formed tag produces no warning and no finding.

## Shared and User-Owned Files

Two files at the top of the data root are not part of the owned-path set
above, and each has a distinct contract:

- **`athlete.toml`** — your athlete profile (tested max heart rate, a
  threshold pace, or whatever else the calculators you have installed
  declare they need). fitdocs writes to this
  file only when you answer a training-load prompt, and it writes **one
  field at a time**: the value you supplied is validated and stored, then
  the whole document is rewritten with every other key and table it does
  not manage preserved. That preservation covers keys, tables, and values;
  it does **not** cover comments or formatting, because the file is parsed
  and re-serialized rather than edited in place. An absent file is never an
  error — it is simply treated as empty. A benchmark answer is dated the
  day you gave it (`measured_on`); if you were asked whether it also
  applies to earlier activities and said yes, the entry also carries the
  earlier activity's date as `applies_from`. Both are plain dates in the
  entry's table — no different from any other key here — so a hand edit
  can change either one.
- **`fitdocs.toml`** — your settings file (`[tiles]` today; more tables as
  more features land). This file is **read-only to fitdocs**: nothing in
  fitdocs ever creates, writes, or modifies it. An absent file, or an absent
  table within it, degrades to defaults.
- **`.fitdocs/data-root`** — the pointer file that tells fitdocs which
  directory is the data root. This file lives in your *source* tree
  (found by walking upward from the working directory), not inside the
  data root itself, and is **read-only to fitdocs**. Do not confuse it with
  the `.fitdocs/` directory listed under Owned Paths above, which is a
  directory *inside* the data root; the two share a name and nothing else.

## Overwrite Semantics of Every Writing Operation

- **`sync`** — discovers new `.fit` files, renders a document for each, and
  merges it against any existing matching document: every preserved region
  and every user-owned frontmatter key is carried over verbatim, and the
  archived source for a file that is already archived is left untouched
  (never re-archived, never rewritten). `sync` then runs a training-load
  pass over **every** workout document in the data root, not only the ones
  this run wrote (interactively prompting for missing inputs, unless run
  with `--no-prompt` or when stdin is not a terminal); see the `load` bullet
  below for exactly what that pass is allowed to touch.
- **`sync --force`** — re-processes every discovered file even when its
  source is already archived, but forced re-processing does **not** bypass
  the preserved-region or user-owned-key guarantee: `notes`, `workout`, and
  `load`, and every user-owned frontmatter key, are still carried over
  verbatim. Forcing widens which sources get *rendered again*, never which
  content is discarded.
- **`regen`** — rebuilds every workout document from the data root alone (the
  archive, the athlete profile, the configured timezone, and the tile
  source — see re-derivability below), re-rendering each from its currently
  recorded archived source. Every preserved region, and every user-owned
  frontmatter key, is again carried over verbatim from the existing
  document. `regen` then runs a training-load pass too, always
  non-interactively -- it never prompts. For a document
  whose `load` region already holds a fitdocs-computed result, that pass only
  re-derives the `load_value` / `load_methodology` / `load_basis` frontmatter
  keys from the region. For a document whose `load` region is still a
  placeholder, or holds a previously-written "unsupported" block, it runs the
  full computation and may rewrite the region. A hand-authored `load` region
  is left untouched.
- **`load`** — the training-load pass touches only two things in an
  existing document: the `load` region's inner content, and the three
  `load_value` / `load_methodology` / `load_basis` frontmatter keys. Every
  other byte of the document — other regions, the generated body, the rest
  of the frontmatter, and every user-owned frontmatter key's line — is left
  untouched by construction; `load` never re-serializes the document's YAML
  block wholesale. By default this pass
  never overwrites a hand-authored (non-fitdocs) `load` region: it leaves
  that region and its frontmatter keys untouched and reports the document as
  skipped. `load --recompute` is the only thing in fitdocs that
  overwrites **hand-authored** `load`-region content: it discards whatever
  the region holds and recomputes it from scratch. Nothing is written if
  the recompute is declined or fails, so the existing content survives a
  run that produces no result.

- **`history`** — its outputs are `history/training-load-history.md` and
  its chart `history/assets/training-load-history-fitness.svg`, each
  rewritten in full whenever it is written: there is no preserved region and
  no user-owned frontmatter key on the training-history page to carry over
  (see
  [A Second Document Type: Training History](#a-second-document-type-training-history)
  above), so this operation has no `--force` and no `--recompute` option — a
  fresh run already rebuilds everything a forced or recomputed run would.
  Before writing either output it reads any existing file at that path; if
  the file exists and does not carry fitdocs' generated-file marker, it is
  left untouched, the outcome is recorded in the run report, and the run
  does not fail. On a run that reaches the point of writing its outputs, it
  first refreshes the ownership declaration in every declared directory —
  `workouts/AGENTS.md`, `history/AGENTS.md`, and `fit-archive/AGENTS.md` —
  through the same function `sync` and `regen` run at the start of every
  run. If no workout document in the data root records a usable load,
  nothing is written at all — neither output and no declaration — any
  existing history page and chart are left untouched, and the run reports
  this without failing. Aside from that declaration refresh,
  `history` never writes, alters, or deletes a `workouts/*.md` document, a
  `workouts/assets/` chart, or a `fit-archive/*` archived source.

**No fitdocs operation discards user-owned region content**, with one
precise exception worth stating plainly rather than glossing over: if a
document is *deleted* from `workouts/`, its region content is gone with it.
A subsequent `regen` from the archive does not fail and does not warn — it
silently rebuilds the document with fresh placeholder text, because region
content is *copied forward from the existing document* on regeneration, not
derived from the archive. Deleting a document therefore is the one action
that puts your writing at risk; editing, moving, or renaming the data root
does not.

A `workouts/*.md` **symlink** is never followed by `sync` or `regen` — its
target may sit outside the data root, and following it would risk writing
through the link at the far end (a symlink is treated exactly the same way by
`fitdocs check`, which reports it as unreadable). Because its content can
never be read, a symlinked document is invisible to identity matching and to
regeneration's "which archive is still referenced" accounting: a re-export of
the activity it stands in for, or a `regen` of the archive it was rendered
from (if no other document references that archive), is written as a *new*,
separate document rather than updating the one behind the symlink. Unlike
the silent deleted-document case above, this **is** reported, but not as a
per-file side effect: at the *start* of every `sync` and `regen` run — before
any file is processed, alongside the ownership-declaration refresh — every
`workouts/*.md` entry is scanned once for symlinks, and each symlinked
*document* found gets a warning naming the path and this exact
consequence. A symlinked `AGENTS.md` is reported separately, as a foreign
ownership declaration, rather than by this scan. Because that scan
runs unconditionally on every invocation, it fires even on a run that
processes zero new files (for example a second `sync` over a source
directory whose contents are all already archived), so a symlinked document
is never a surprise found only by inspecting the tree afterward.

## Commit Ordering and Re-Derivability

Per file, `sync` writes chart assets first, then the document itself, then
the archived copy of the source **last**. The archived source's presence is
what marks a file as fully processed (see
[Document-Format Versions](#document-format-versions-and-migration) below
for why this matters even more once a version gate is involved): if a run is
interrupted before the archive write, nothing records the file as done and
it is reprocessed idempotently on the next run.

Every workout document's **generated** content — everything outside its
preserved regions — is re-derivable: fitdocs can rebuild it from the
archived source in `fit-archive/`, the athlete profile (`athlete.toml`), the
configured timezone, and the configured tile source. This is what makes
`regen` possible without the original `.fit` source directory. Content
*inside* a document's preserved regions is not re-derived by regeneration —
it is carried over from the document itself, so regenerating a document you
deleted brings back only the generated content, never the notes, workout
log, or load-region content it used to hold.

The training-history page is re-derived differently: it has no archived
`.fit` source of its own to rebuild from. Instead it is re-derived entirely
from the workout documents already in `workouts/` — the load values and
dates their frontmatter already records — which is
why deleting it loses nothing a subsequent `fitdocs history` run cannot
reconstruct.

## Document-Format Versions and Migration

This section describes `workouts/*.md` documents specifically, not every
generated document: the training-history page carries no `doc_version` at
all, and has nothing to migrate — see
[A Second Document Type: Training History](#a-second-document-type-training-history)
above for why (it is rewritten in full on every run, so there is no older
copy to bring current and no gate to consult). Everything below refers to
`doc_version`, a key only workout documents carry.

In place of `doc_version`, the training-history page carries its own
`history_version` key: a plain integer, `1` today, that versions the page's
own format rather than this contract's guarantees. It is not a migration
gate: fitdocs does not consult any older copy of the page, because
`fitdocs history` rewrites `history/training-load-history.md`
in full on every run (see
[A Second Document Type: Training History](#a-second-document-type-training-history)
above) — an older page is silently replaced, never reported as out of date
and never left in place pending a `regen`-equivalent migration step, because
`fitdocs history` has no such step.

Every generated workout document records a `doc_version` (a plain integer,
independent of this contract's own version number above). When fitdocs
encounters an existing document whose recorded `doc_version` is **older**
than the version it produces, it reports the document as out of date and
names regeneration (`fitdocs regen`, or `fitdocs check` to see the report
without writing) as the action that brings it current — regeneration is the
one and only migration path; there is no in-place transformation of an
older document. A missing or unusable `doc_version` is treated the same way:
out of date, never as newer.

If an existing document records a `doc_version` **newer** than the installed
fitdocs produces, the sync/regen rewrite leaves that document's frontmatter,
body, and regions untouched, reports it as written by a newer fitdocs, and
continues the run rather than rewriting it at an older format. The
training-load pass that follows `sync` and `regen` also consults
`doc_version`: it leaves that same document completely untouched — including
its `load` region and its three load keys — and reports it skipped for the
same reason, so the newer-version refusal holds for the whole document, not
only the part `sync`/`regen` rewrite directly.

**A version-gated document counts as *skipped* only because `skipped` is
the report's shared presentation bucket — it is not a completed file.** No
disposition, cleanup, or archival policy may act on it. In `sync`, the
corresponding `.fit` source is left unarchived so the same run retried later
picks it up again; in `regen`, the already-archived source is left exactly
as it was, with no archive interaction at all. Presence in the archive —
never the `skipped` label — is the authoritative discriminator for a
fully-processed source. A downstream policy that relocated or deleted a
version-gated source on the strength of a "skipped" report would orphan that
source and permanently defeat the retry this guarantee exists to preserve.

## Marking Generated Files in a Version-Controlled Wiki

If you keep your wiki under version control, you may want tools like `git
diff` and code-review UIs to treat fitdocs' generated files as
machine-generated rather than hand-authored — GitHub, GitLab, and `git`
itself recognize a `linguist-generated` attribute in a `.gitattributes` file
for exactly this purpose. A line such as

```
workouts/*.md linguist-generated
fit-archive/* linguist-generated -diff
history/*.md linguist-generated
history/assets/* linguist-generated -diff
```

in a `.gitattributes` at the root of your wiki tells those tools to collapse
diffs of generated documents and archived sources by default.

**fitdocs does not write a `.gitattributes` file itself** — this is
guidance for you to apply if and how you see fit, not a configuration
fitdocs manages or enforces.

## Referencing `workouts/AGENTS.md` from Your Wiki's Root Instructions

If your wiki already has its own root-level agent-instructions file (for
example, a root `AGENTS.md` or `CLAUDE.md` that you author and own), it is
enough to point at `workouts/AGENTS.md`, `fit-archive/AGENTS.md`, and
`history/AGENTS.md` from there rather than duplicating their contents. A
short pointer such as:

```markdown
See `workouts/AGENTS.md` for what fitdocs owns under `workouts/`,
`fit-archive/AGENTS.md` for the source archive's immutability rule, and
`history/AGENTS.md` for the training-history page.
```

is sufficient: those three files are generated and kept current by fitdocs
on every `sync` and `regen` run and on every `fitdocs history` run that
writes its page — each of the three refreshes every declared directory's
file, not only the one its own output lands in — so a pointer from your own
root file stays accurate without you
having to maintain it. Your root instructions file itself is never written
or modified by fitdocs — it belongs entirely to you.
