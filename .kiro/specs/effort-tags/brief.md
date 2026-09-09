# Brief: effort-tags

## Problem

fitdocs has no notion of a race, a field test, or a hard effort. Every
workout page is an activity like every other. The athlete knows which of the
2,478 pages in the archive were races — those are the dated maximal
performances that define what "fit" meant on that day — and nothing in
fitdocs can be told.

The obvious place to say so is the page's own frontmatter, and today that
does not work: the frontmatter block is tool-owned and **rewritten in full on
every regeneration**. Any key outside the managed set is dropped by the next
`sync` or `regen`, with a warning naming it
(`src/fitdocs/contract.py` `unmanaged_keys`, surfaced by
`src/fitdocs/sync.py` `_unmanaged_keys_detail`). A hand-added `effort: race`
survives until the next pass and then silently stops existing. The body's
`notes` and `workout` regions *are* preserved verbatim, but they are free
text — a machine reading a tag out of prose is the fragile thing this feature
exists to avoid.

Three later specs need the tag: `performance-benchmarks` derives dated
thresholds from tagged efforts, `load-history` draws race markers on the
fitness/fatigue chart, and `performance-model-fit` uses tagged race results as
criterion performances. This spec is the seam they share.

## Current State

- `MANAGED_KEYS` (`contract.py:291-328`) is the exact set fitdocs writes: the
  keys `render/frontmatter.build_frontmatter` emits, union `LOAD_KEYS`. An
  anti-drift test pins the two together. There is no concept of a key fitdocs
  *preserves but never writes*.
- The ownership contract knows user-owned **regions** (`USER_REGIONS =
  ("notes", "workout")`, `contract.py:358-381`) carried verbatim by
  `docmerge.merge_regions`. The analogous idea for frontmatter does not exist.
- The training-load pass edits frontmatter surgically
  (`load/docedit.apply_frontmatter_load` keeps every non-managed line), so it
  would already leave a tag alone. `sync` and `regen` rebuild the block from
  the activity and drop the rest.
- `fitdocs check` audits documents and reports unmanaged keys as findings.
- No `race`, `event`, `competition`, `best-effort` or `PR` concept exists
  anywhere in `src/` (searched 2026-09-09). The FIT files carry none either:
  HealthFit exports from Apple Watch do not mark a workout as a race.
- The athlete's pkm already has race pages as wiki entities (product.md:
  "linked to daily notes, gear, races, and people"), so a tag that can carry a
  `[[wikilink]]` to the race page fits how the wiki is already organised.

## Desired Outcome

- An athlete can mark a workout page as a **race**, a **test** (a formal
  threshold protocol, e.g. a 20-minute power test or 30-minute time trial) or a
  **hard** effort by editing its frontmatter, and that mark survives every
  `sync`, `regen` and load pass, byte-for-byte.
- The tag can optionally carry the **official result** — course distance and
  chip/official time — because a certified 10 km is not the 10.2 km the watch
  measured and a chip time is not the elapsed time the watch recorded. It can
  optionally name the event, ideally as a wikilink to the race's own page.
- A malformed tag (unknown kind, a negative time, a distance with no time) is
  reported by `fitdocs check` and by the passes that read it, naming the page
  and the field, and never treated as "untagged".
- A typed reader in the contract module returns the tag for a page, so the
  three downstream specs never parse frontmatter themselves.
- fitdocs never writes a tag. Absent means untagged. There is no placeholder.

## Approach

Introduce **user-owned frontmatter keys** as a first-class class in the
document contract, parallel to `USER_REGIONS`: a published set of keys fitdocs
never emits from the activity, carries verbatim from the existing page into the
rebuilt block on regeneration, validates on read, and excludes from the
unmanaged-key warning and audit finding. The effort tag is the first member.

Vocabulary is the spec's to settle; the candidates are a flat set
(`effort`, `effort_distance_m`, `effort_time_s`, `effort_event`) or one nested
mapping under `effort`. Flat keys match every key fitdocs writes today and are
easier to grep from the shell; a mapping keeps the four fields together. Either
way the kind vocabulary is closed (`race | test | hard`) so a downstream spec
can switch on it without a string comparison it has to guess at.

Preservation is a change to the one place regeneration rebuilds the block:
read the existing page's user-owned keys before the rebuild, validate them, and
re-emit them after the managed keys. The load pass's line-level edit already
preserves them and needs only a test proving it.

## Scope

- **In**: the user-owned frontmatter key class in the contract module and its
  published set; the effort tag vocabulary and its validation rules; carrying
  the keys through `sync`, `regen` and the load pass; the audit finding for a
  malformed tag; the typed reader; documentation of the tag in the ownership
  contract the README points at.
- **Out**: deriving anything from the tag (`performance-benchmarks`);
  rendering the tag into the page body; automatic detection of races or best
  efforts (a listed follow-on, not this spec); the history page
  (`load-history`); any change to what fitdocs writes into frontmatter from the
  activity; a `doc_version` bump unless the design finds one forced — existing
  pages are untouched by a key they do not carry.

## Boundary Candidates

- Contract vocabulary and the typed reader (`src/fitdocs/contract.py`, owned by
  `wiki-contract`): the published key set, the kind enumeration, validation,
  the `EffortTag` type.
- Preservation mechanics in the regeneration path (`src/fitdocs/sync.py`,
  `src/fitdocs/render/frontmatter.py`): reading the existing keys before the
  rebuild and re-emitting them after.
- Audit surfacing (`src/fitdocs/audit.py`, `fitdocs check`): the finding for a
  malformed tag, distinct from the unmanaged-key finding.

## Out of Boundary

- The meaning of a race for load, thresholds or fitness — this spec records a
  fact about a page and decides nothing about its consequence.
- Which activities *should* be tagged. No heuristics, no suggestions.
- The pkm-side race page. The tag may link to it; fitdocs never creates it.

## Upstream / Downstream

- **Upstream**: `wiki-contract` (owner of `MANAGED_KEYS`, `USER_REGIONS`,
  `DOC_VERSION` and the contract module — this spec amends it, as
  `athlete-benchmarks` amended `training-load`'s settings reader);
  `workout-docs` (the frontmatter builder); `inbox` / the sync engine (the
  regeneration path that drops keys today); `training-load` (the load pass's
  frontmatter surgery, which must keep preserving the key).
- **Downstream**: `performance-benchmarks`, `load-history`,
  `performance-model-fit` — all three read the tag through this spec's reader
  and none may define a second one.

## Existing Spec Touchpoints

- **Extends**: `wiki-contract` — a new key class in the contract and its
  ownership documentation; the anti-drift pin on `MANAGED_KEYS` must keep
  holding for the managed set while a separate pin covers the user-owned set.
- **Adjacent**: `workout-docs` (frontmatter emission order and the golden
  files — a preserved key changes goldens only for pages that carry one);
  `plugin-api` (nothing here is a calculator surface); `tests/test_public_api.py`
  pins `contract.__all__` exactly, so the reader is an explicit addition.

## Constraints

- **The tag is user-owned data and the preservation guarantee is the whole
  feature.** A regeneration that loses or alters a tag is a data-loss bug of
  the same class as losing the notes region, and the spec's tests must prove
  survival through `sync --force`, `regen`, and the load pass, on a page that
  also carries user regions.
- **Validation is loud and specific.** A tag that fails validation is named by
  page and field; it is never coerced, defaulted, or read as absent. Absent data
  is `None`, never a fabricated value (tech.md).
- **The kind vocabulary is closed and the field names are published.** Downstream
  specs switch on the enumeration; a typo in a page is a finding, not a fourth
  kind.
- **Confirm the frontmatter shape against the pkm's `wiki-schema.md`** (the
  reference integration, tech.md) before choosing flat keys or a mapping — the
  page has to remain a valid wiki page there.
- **Determinism**: a page regenerated with an unchanged tag is byte-identical
  to the previous regeneration.
- No personal data in the repository: fixtures use synthetic pages, never the
  athlete's real archive.
