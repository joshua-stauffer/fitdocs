# fitdocs Ownership Contract

**Contract version:** `2`

This document is the authoritative, published statement of what fitdocs owns
in your data root, what you own, and the exact limits of every operation that
writes there. It is restated, in shorter form, inside the two owned
directories a human or agent browses (`workouts/AGENTS.md` and
`fit-archive/AGENTS.md`, generated on the first `sync` or `regen`) and
stamped onto every generated document as a provenance banner — the
`AGENTS.md` texts and the provenance banner are generated from the same
code-level constants. This document's own enumerated lists (owned paths,
preserved regions, managed keys, and the contract version above) are held
equal to those same constants by a conformance test; its narrative
paragraphs are reviewed by hand at each contract-version bump.

The version above changes whenever a guarantee stated in this document
changes — a new owned path, a changed overwrite rule, a different managed
key set. It is distinct from a document's own `doc_version` (see
[Document-Format Versions and Migration](#document-format-versions-and-migration)
below), which versions the file format, not this contract's guarantees.

## Owned Paths

fitdocs creates, writes, and deletes files only under the following
data-root-relative directories, and states plainly: **fitdocs writes nowhere
else** under the data root except these paths and the configured locations
named in the next section.

- `workouts/` — one generated markdown document per workout.
- `workouts/assets/` — chart images (SVG) referenced by workout documents.
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
replaces **everything outside the preserved regions**: the frontmatter
block in full, the document body, the provenance banner, and every chart
asset. It carries **every preserved region's content over verbatim** —
`notes`, `workout`, and `load` — including while forced re-processing
(`--force`) is in effect. There is no operation that discards user-owned
region content; see
[Overwrite Semantics](#overwrite-semantics-of-every-writing-operation) below
for the one honest exception to this guarantee (a *deleted* document has no
content to preserve).

## Frontmatter Ownership

The frontmatter block of a generated workout document is entirely
tool-owned and is rewritten in full on every regeneration.

## Managed Frontmatter Keys

The complete set of keys fitdocs manages — every key it writes and will
restore on the next `regen`, including the three keys the training-load
pass writes — is:

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

Any other key present in a document is **unmanaged**: fitdocs did not write
it and will drop it the next time that document is rewritten. If a
regeneration would drop an unmanaged key, fitdocs reports the affected
document and the dropped key names as a warning before proceeding — the run
still succeeds, but you get a chance to notice.

The supported place for hand-authored content in a generated document is the
`notes` region (or, for a strength document, the `workout` region) — not the
frontmatter block. Anything you add to frontmatter directly should be
treated as temporary: it survives only until the document is next
regenerated.

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
  is carried over verbatim, and the archived source for a file that is
  already archived is left untouched (never re-archived, never rewritten).
  `sync` then runs a training-load pass over **every** workout document in
  the data root, not only the ones this run wrote (interactively prompting
  for missing inputs, unless run with `--no-prompt` or when stdin is not a
  terminal); see the `load` bullet below for exactly what that pass is
  allowed to touch.
- **`sync --force`** — re-processes every discovered file even when its
  source is already archived, but forced re-processing does **not** bypass
  the preserved-region guarantee: `notes`, `workout`, and `load` are still
  carried over verbatim. Forcing widens which sources get *rendered again*,
  never which content is discarded.
- **`regen`** — rebuilds every document from the data root alone (the
  archive, the athlete profile, the configured timezone, and the tile
  source — see re-derivability below), re-rendering each from its currently
  recorded archived source. Every preserved region is again carried over
  verbatim from the existing document. `regen` then runs a training-load
  pass too, always non-interactively -- it never prompts. For a document
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
  of the frontmatter — is left untouched by construction; `load` never
  re-serializes the document's YAML block wholesale. By default this pass
  never overwrites a hand-authored (non-fitdocs) `load` region: it leaves
  that region and its frontmatter keys untouched and reports the document as
  skipped. `load --recompute` is the only thing in fitdocs that
  overwrites **hand-authored** `load`-region content: it discards whatever
  the region holds and recomputes it from scratch. Nothing is written if
  the recompute is declined or fails, so the existing content survives a
  run that produces no result.

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

Every document's **generated** content — everything outside its preserved
regions — is re-derivable: fitdocs can rebuild it from the archived source
in `fit-archive/`, the athlete profile (`athlete.toml`), the configured
timezone, and the configured tile source. This is what makes `regen`
possible without the original `.fit` source directory. Content *inside* a
document's preserved regions is not re-derived by regeneration — it is
carried over from the document itself, so regenerating a document you
deleted brings back only the generated content, never the notes, workout
log, or load-region content it used to hold.

## Document-Format Versions and Migration

Every generated document records a `doc_version` (a plain integer,
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
```

in a `.gitattributes` at the root of your wiki tells those tools to collapse
diffs of generated documents and archived sources by default.

**fitdocs does not write a `.gitattributes` file itself** — this is
guidance for you to apply if and how you see fit, not a configuration
fitdocs manages or enforces.

## Referencing `workouts/AGENTS.md` from Your Wiki's Root Instructions

If your wiki already has its own root-level agent-instructions file (for
example, a root `AGENTS.md` or `CLAUDE.md` that you author and own), it is
enough to point at `workouts/AGENTS.md` and `fit-archive/AGENTS.md` from
there rather than duplicating their contents. A short pointer such as:

```markdown
See `workouts/AGENTS.md` for what fitdocs owns under `workouts/`, and
`fit-archive/AGENTS.md` for the source archive's immutability rule.
```

is sufficient: those two files are generated and kept current by fitdocs on
every `sync`/`regen`, so a pointer from your own root file stays accurate
without you having to maintain it. Your root instructions file itself is
never written or modified by fitdocs — it belongs entirely to you.
