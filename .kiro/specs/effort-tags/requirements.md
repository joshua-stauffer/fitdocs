# Requirements Document

## Project Description (Input)
An athlete with a 2,478-page workout archive knows which pages were races,
field tests and hard efforts -- the dated maximal performances that define
what "fit" meant on a given day -- and nothing in fitdocs can be told. The
natural place to say so is the page's own frontmatter, and today that does not
work: the frontmatter block is tool-owned and rewritten in full on every
regeneration, so any key outside the managed set is dropped by the next `sync`
or `regen` (with a warning naming it). Three later specs need the mark:
`performance-benchmarks` derives dated thresholds from tagged efforts,
`load-history` draws race markers on the fitness/fatigue chart, and
`performance-model-fit` uses tagged race results as criterion performances.
This spec introduces user-owned frontmatter keys as a first-class class in the
document contract -- keys fitdocs never writes, carries verbatim through every
rewrite, validates on read, and excludes from the unmanaged-key warning -- with
the effort tag (`race | test | hard`, optional official distance, time and
event link) as the first member, read through one typed contract reader.
Source: `.kiro/specs/effort-tags/brief.md`; Phase 6 of
`.kiro/steering/roadmap.md`.

## Introduction

effort-tags is the seam the rest of Phase 6 shares. It records one fact about
a workout page -- *this was a race, a test, or a hard effort, and here is the
official result if there was one* -- in the page's own frontmatter, and makes
that fact survive everything fitdocs does to the page afterwards. It decides
nothing about the consequence of that fact: what a race means for thresholds,
load or fitness belongs to `performance-benchmarks`, `load-history` and
`performance-model-fit`, all of which read the tag through the one reader this
spec provides and none of which may define a second.

The change to the document contract is small and precise. Today the contract
knows two classes of frontmatter key: *managed* (fitdocs writes them and
restores them on every rewrite) and *unmanaged* (fitdocs drops them, with a
warning). This spec adds a third class, parallel to the user-owned *regions*
that already survive regeneration: **user-owned keys** -- a published set that
fitdocs never writes, never defaults, carries byte-for-byte through `sync`,
`sync --force`, `regen` and the training-load pass, validates loudly when it
reads, and never confuses with an unmanaged key. The effort tag is the first
member of that class; the class itself is what `wiki-contract`'s ownership
contract gains.

Four principles govern every requirement below. Absent means untagged and is
`None`, never a placeholder or a fabricated value. A malformed tag is named by
page and field and is never coerced, defaulted or read as absent -- a typo is a
finding, not a fourth kind. Preservation is byte-for-byte on the athlete's own
lines and deterministic across repeated regeneration. And the kind vocabulary
is closed and the field names are published, so a downstream spec switches on
an enumeration rather than guessing at strings.

## Boundary Context

- **In scope**: the user-owned frontmatter key class in the document contract
  and its published set; the effort-tag vocabulary (kind, optional official
  distance and time, optional event) and its validation rules; carrying the
  keys byte-for-byte through `sync`, `sync --force`, `regen` and the
  training-load pass; excluding them from the unmanaged-key warning and audit
  finding; a distinct `fitdocs check` finding and a `sync`/`regen` warning for
  a malformed tag; one typed reader in the contract module; the statement of
  the new key class in the published ownership contract, the README's
  ownership summary and the in-tree declaration for the generated-documents
  directory, with the contract version advanced because a stated guarantee
  changed; and the amendment of `wiki-contract`'s frontmatter-ownership
  requirement that records the class (the roadmap's Phase 6 Existing Spec
  Update for `wiki-contract`, landed here).
- **Out of scope**: deriving anything from a tag (`performance-benchmarks`);
  drawing or listing tags anywhere (`load-history`); fitting
  (`performance-model-fit`); rendering the tag into the page body; automatic
  detection or suggestion of races or best efforts (a listed follow-on); any
  change to which keys fitdocs writes from the activity or to the managed key
  set; a document-format version bump (existing pages are untouched by a key
  they do not carry); creating, resolving or verifying the wiki page an event
  link points at; sports restrictions on tagging (the derivation pass declines
  what it cannot use); preserving frontmatter keys outside the published
  user-owned set (they stay unmanaged and are still dropped with a warning).
- **Adjacent expectations**: `wiki-contract` owns the contract module, the
  managed key set, the ownership contract document, the in-tree declaration
  and the `check` command -- this spec extends each with the new key class and
  leaves every existing guarantee in force, including the anti-drift pin that
  holds the managed set equal to what the frontmatter builder emits.
  `workout-docs` owns the frontmatter builder and the golden documents; a
  golden changes only if it carries a user-owned key, and none does.
  `training-load` owns the load pass's line-level frontmatter surgery, which
  already leaves non-managed lines alone; this spec proves that with tests and
  changes none of its behavior. The wiki-contract version gate (a document
  written by a newer fitdocs is left untouched) is unchanged and applies
  before anything in this spec runs. The reference wiki's schema
  (`wiki-schema.md` in the pkm integration) states that a workout page's
  frontmatter is fitdocs' own and is not corrected toward the wiki's standard,
  so a flat set of fitdocs-named keys is a valid shape there.
- **Downstream contract**: `performance-benchmarks`, `load-history` and
  `performance-model-fit` read the tag only through the reader this spec
  publishes, switch on its closed kind enumeration, and treat a malformed tag
  as a reportable condition on that page -- never as untagged.

## Requirements

### Requirement 1: User-Owned Frontmatter Keys as a Contract Class
**Objective:** As an athlete who marks pages by hand, I want a published class of frontmatter keys that fitdocs preserves but never writes, so that a mark I add is mine and survives every fitdocs operation.

#### Acceptance Criteria
1. The fitdocs CLI shall publish the complete set of user-owned frontmatter keys as a class distinct from, and disjoint with, the managed key set.
2. The fitdocs CLI shall never write a user-owned key into a document from the activity, the athlete profile, a computed value, or any default -- a freshly rendered document carries none of them.
3. While a document carries none of the user-owned keys, the fitdocs CLI shall treat the document as untagged and shall write no placeholder, empty value, or default for any user-owned key.
4. The fitdocs CLI shall continue to treat a frontmatter key that is neither managed nor user-owned as unmanaged, with the existing drop-with-warning and audit-finding behavior unchanged.
5. The fitdocs CLI shall keep the published managed key set exactly equal to the set of keys it writes, unchanged by this feature, so that the existing anti-drift guarantee between the managed set and the frontmatter builder keeps holding.

### Requirement 2: The Effort Tag Vocabulary
**Objective:** As an athlete, I want to mark a workout page as a race, a test or a hard effort, optionally with the official result and the event, so that later features can find my dated maximal performances without reading my prose.

#### Acceptance Criteria
1. The fitdocs CLI shall recognize exactly four user-owned keys, all flat top-level frontmatter keys: `effort` (the kind), `effort_distance_m` (the official or certified course distance, in metres), `effort_time_s` (the official or chip time, in seconds), and `effort_event` (the event's name, ideally a wikilink to the event's own wiki page).
2. The fitdocs CLI shall accept exactly three effort kinds -- `race`, `test`, and `hard` -- matched exactly and case-sensitively, and shall treat any other value of `effort` as malformed rather than as a fourth kind.
3. Where a tag carries `effort_distance_m`, the value shall be a positive, finite number of metres; where it carries `effort_time_s`, the value shall be a positive, finite number of seconds; where it carries `effort_event`, the value shall be non-empty text.
4. Where a tag carries `effort_distance_m`, the tag shall also carry `effort_time_s`, because a course distance is an official result only together with its time; `effort_time_s` may stand alone, because a timed test protocol has a duration and no course.
5. If any of `effort_distance_m`, `effort_time_s`, or `effort_event` is present while `effort` is absent, the fitdocs CLI shall treat the tag as malformed rather than as untagged.
6. Where `effort_event` carries a wikilink, the fitdocs CLI shall keep the text exactly as written and shall not create, resolve, or verify the linked page.
7. The fitdocs CLI shall attach no consequence to a tag within this feature: it shall not render the tag into the document body and shall not change any computed metric, load value, or chart on account of it.
8. The fitdocs CLI shall accept a tag on any workout document regardless of its sport or modality.

### Requirement 3: Loud, Specific Validation
**Objective:** As an athlete who mistyped a tag, I want to be told which page and which field is wrong, so that a typo never silently becomes "untagged" or a wrong number.

#### Acceptance Criteria
1. If a document's effort keys fail validation -- an unknown kind, a value of the wrong type, a non-positive or non-finite number, empty event text, a distance without a time, or an effort field without `effort` -- the fitdocs CLI shall classify the tag as malformed, never as absent and never as a valid tag.
2. The fitdocs CLI shall never coerce, default, round, truncate, or otherwise repair a malformed value.
3. When reporting a malformed tag, the fitdocs CLI shall name the document, each offending key, and what was expected of it.
4. When `sync` or `regen` rewrites a document carrying a malformed tag, the fitdocs CLI shall report a warning naming the document and the offending keys, shall complete the run successfully with the exit status unchanged by the warning, and shall still carry the tag's lines unchanged into the rewritten document.
5. The `fitdocs check` inspection shall report a malformed tag as a finding of its own kind, distinct from the unmanaged-key finding, naming the affected path, the offending keys, and the action that resolves it.
6. While a document carries a well-formed tag, the fitdocs CLI shall produce no warning and no finding on account of it.
7. If `effort_event` is not read as text -- for example a wikilink written without quotes, which YAML reads as a nested list -- the fitdocs CLI shall report it as malformed and the report shall state that the value must be quoted text.

### Requirement 4: Byte-for-Byte Preservation Across Every Rewrite
**Objective:** As an athlete, I want the tag to survive `sync`, `sync --force`, `regen` and the training-load pass without a byte changing, so that tagging a page is a one-time act.

#### Acceptance Criteria
1. When `sync` -- with or without forced re-processing -- rewrites an existing document, the fitdocs CLI shall carry every user-owned key's frontmatter line, including any continuation lines its value spans, into the rewritten document byte-for-byte.
2. When `regen` rewrites an existing document, the fitdocs CLI shall carry every user-owned key's frontmatter line, including any continuation lines, into the rewritten document byte-for-byte.
3. When the training-load pass edits a document -- filling the load region, upserting or stripping the load frontmatter keys, restoring keys from the payload, or recomputing -- the fitdocs CLI shall leave every user-owned line byte-identical.
4. The fitdocs CLI shall carry user-owned lines regardless of their validity: a malformed tag is preserved unchanged, never dropped, altered, or replaced.
5. When the fitdocs CLI rebuilds a document's frontmatter block, it shall place the carried user-owned lines after every managed key and before the closing fence, in the order they appeared in the existing document, and this placement shall be stated as part of the contract.
6. When a document carrying an unchanged tag is regenerated twice, the two outputs shall be byte-identical; and when a document carrying no user-owned key is regenerated, its output shall be byte-identical to what fitdocs produced before this feature.
7. When a rewrite would drop unmanaged keys, the warning shall not name a user-owned key, and the `check` inspection's unmanaged-key finding shall not name one either.
8. If a document is deleted and later regenerated from the archive, the fitdocs CLI shall render a fresh untagged document without warning, because a user-owned key -- like a user-owned region -- is copied forward from the existing document and is not re-derivable from the archive.

### Requirement 5: One Typed Reader
**Objective:** As a downstream feature (benchmark derivation, the history page, the model fit), I want one reader that returns the tag for a page, so that no feature parses frontmatter for itself and all of them agree about what a page says.

#### Acceptance Criteria
1. The document contract shall provide one reader that, given a document's parsed frontmatter, yields exactly one of three outcomes: no tag, a valid tag carrying the kind and the optional fields, or a malformed tag carrying the named problems.
2. The reader shall never raise on any input and shall accept the absent value the frontmatter parser returns for an unreadable document, answering "no tag" for it.
3. The valid tag shall expose the kind as a closed enumeration a consumer can switch on without a string comparison, and each optional field as a typed value that is absent (`None`) when the page does not carry it, never a fabricated default.
4. The reader and the effort-key spellings shall have exactly one definition in fitdocs; no other module shall define a second reader, a second validation, or its own spelling of an effort key.
5. The reader, the kind enumeration, the tag types, and the published key set shall be part of the contract module's published surface, pinned so that an accidental addition, removal, or rename fails loudly.
6. The malformed outcome shall name each offending key and the expectation it failed, in one form that the `check` finding, the `sync`/`regen` warning, and any downstream report all render from, so that the same defect is described identically everywhere.

### Requirement 6: Published Contract, Declaration and Documentation
**Objective:** As a wiki maintainer or an LLM agent maintaining the wiki, I want the published ownership contract and the in-tree declaration to state which frontmatter keys are mine, so that I neither lose them nor "correct" them.

#### Acceptance Criteria
1. The published ownership contract shall list the complete set of user-owned frontmatter keys, state that fitdocs never writes them and carries them verbatim through every rewrite, state where a rebuilt block places them, and document the effort tag's kinds, fields, units, and validation rules.
2. The published ownership contract's statements about frontmatter ownership and unmanaged keys shall be amended so that "rewritten in full" and "any other key is dropped" apply only to keys that are neither managed nor user-owned.
3. The ownership contract's version identifier shall change, because a stated guarantee -- what regeneration preserves in the frontmatter block -- has changed.
4. The ownership declaration placed in the generated-documents directory shall name the user-owned frontmatter keys and state that fitdocs never writes them and carries them through regeneration, without claiming which documents carry them; the source-archive declaration shall be unchanged apart from the version identifier it restates.
5. The enumerated user-owned key list in the published contract shall be held equal to the published set in code by the same conformance mechanism that already holds the managed key list, so that the document cannot drift from behavior without a test failing.
6. The README's ownership summary shall mention that the effort-tag frontmatter keys are user-owned alongside the user-owned regions, pointing at the published contract for the detail.
