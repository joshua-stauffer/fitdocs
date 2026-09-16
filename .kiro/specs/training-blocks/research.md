# Research & Design Decisions: training-blocks

## Summary
- **Feature**: `training-blocks`
- **Discovery Scope**: Extension -- a new package on top of the existing
  document contract, region grammar, settings reader, layout leaf, declaration
  mechanism and ownership guards -- with two genuinely new elements: the first
  user-authored *content* file fitdocs reads (the plan source), and the
  project's first cross-document links.
- **Key Findings**:
  - **The non-activity-location ritual is fully worked out by `load-history`
    and every pin it named still holds at HEAD 3664a0d (re-created as 5dff756 after the 2026-09-16 .git loss, identical tree).** `layout.OWNED_PATHS`
    has seven entries (`layout.py:117-125`) and `DECLARED_DIRS` three
    (`:144-148`); `declaration_text` (`declaration.py:316`) is already an
    explicit three-way dispatch with no fall-through (`:379-401`); the goldens
    module's `_GOLDEN_NAMES` is a hand-maintained three-entry dict
    (`tests/test_declaration_goldens.py:41-45`) that raises `KeyError` for a
    fourth declared directory; `tests/test_layout.py:537-545, 548, 670,
    688-691` pin the tuples by value; `tests/test_ownership_contract.py:81-91`
    holds the document's version line and Owned Paths list equal to the code;
    `tests/test_confinement.py:568-588` defines `EntryPoint` with
    `non_vacuous` and `:606-611` registers `history` as the template;
    `CONTRACT_VERSION` reads `"3"` (`contract.py:264`). Line drift from the
    brief is cosmetic (`test_confinement.py` `EntryPoint` ends at `:588`, not
    `:591`; the ownership document's shared-files section is `:357-386`, not
    `:361-380`; the wikilink note is `contract.py:517-519`).
  - **The sport vocabulary is a `StrEnum` this spec can import, not
    re-spell.** `model.Sport` (`src/fitdocs/model.py:61-71`: `Ride`, `Run`,
    `Swim`, `Walk`, `Hike`, `Rowing`, `Workout`) and `model.Modality`
    (`:74-81`: `run`, `bike`, `swim`, `strength`, `other`) are pure enums
    re-exported from the package root. A generated workout document always
    carries `modality` (`render/frontmatter.py:127-131`, derived by
    `ingest/sport.py:82-115`: `Run→run`, `Ride→bike`, `Swim→swim`, everything
    else `other`, `strength_training→strength`) and carries `indoor` only
    when true. `sub_sport` never reaches frontmatter (`model.py:122-127`).
  - **The region grammar is generic and no test would object to a `notes`
    region on a page of another type.** `docmerge.merge_regions(fresh,
    existing)` splices an existing page's region bodies into a fresh render
    and raises `RegionError` only when the existing page carries a region the
    fresh one lacks (`docmerge.py:119-162`); `PRESERVED_REGIONS` is consumed
    by no code in `src/` (only pinned, `tests/test_contract.py:66-68`), and
    `tests/test_contract_consumers.py:471-497`'s "spell no region id" scan
    covers `fitdocs/render/` only. `contract.NOTES_REGION` and
    `contract.NOTES_PLACEHOLDER` (`contract.py:655, 680-682`) are importable.
  - **No cross-document link exists anywhere in `src/`.** Every `](` is an
    image link built from `layout.asset_rel_path` / `history_asset_rel_path`
    (`render/sections.py:334, 466, 495`; `history/page.py:462`); every `[[`
    is a `Callable[[...]]` annotation or a TOML `[[array]]` mention.
    `tests/test_portability.py` scans workout documents only (`:117,
    212-220`) and forbids `[[` in their bodies (`:141`).
  - **Frontmatter for a non-workout page is emitted as plain lines, and the
    bare-token rule is a known trap.** `history/page.py:173-252` writes
    `key: value` lines by hand, quoting with `_quote` (`:145-151`, rejects
    non-printables, escapes `\` and `"`) and emitting only `[A-Za-z0-9_.-]+`
    tokens bare -- which queue item
    `2026-09-12-history-methodology-id-bare-token-yaml-typed` shows reads
    back as `int`/`bool`/`None`/`date` for ids like `1991`, `true`, `null`,
    `2024-01-01`. `render/frontmatter.py` is the package's one YAML emitter
    (`tests/test_contract_consumers.py:120`) and quotes dates so they read
    back as strings; `contract.document_date` accepts a quoted ISO string
    (`contract.py:902-906`).
  - **TOML reading is a per-module `tomllib` idiom with no shared helper.**
    `settings.py:61-71` is specific to `fitdocs.toml`; `athlete.py:114`,
    `quarantine.py:156` and `load/profile.py:462` each hold their own
    `tomllib.load` with their own error type. The `[inbox] path` reader
    (`inbox.py:228-277, 352-363`) is the model for a configured directory:
    the string is kept verbatim, resolved lexically with `os.path.normpath`
    against the data root, and validated before any I/O.
  - **The atomic write is a private copy in every writing module** --
    `load/engine.py:652`, `history/engine.py:230`, `tiles.py:417`,
    `quarantine.py:234`, `load/profile.py:545` -- because the package
    boundary guards forbid importing a sibling engine. `history/engine.py`'s
    docstring (`:49-58`) records that choice explicitly. A sixth copy is the
    precedent; promoting one into `fitdocs.docio` is queued as follow-up work
    by this spec.
  - **`DOC_BANNER` is reusable but its wording is workout-specific.** It reads
    "everything outside the notes/workout/load regions is replaced on
    regeneration -- see this directory's AGENTS.md" (`contract.py:637-640`);
    `is_generated` recognises it by prefix (`:816-829`). The history page
    carries it as is; queue item
    `2026-09-10-doc-banner-wording-stale-once-user-keys-preserved` already
    tracks the wording. For a planned page two levels below the data root
    "this directory's AGENTS.md" is one level up; accepted and recorded.
  - **The declaration quantifier guard is a substring scan.**
    `tests/test_declaration.py:196` forbids `each`, `every`, `all documents`,
    `any document` in *any* line of *any* declaration text, by substring --
    so `reach`, `teach`, `everything` and `everyone` trip it too. New
    fragments are written around it.
  - **`fitdocs plan` is the fifth command shape copied from `history`**:
    `history_command` (`cli.py:451-478`) resolves the root, runs the engine
    inside `except SettingsError`, prints a report, and exits through
    `_finish(failed=...)`; exit constants at `cli.py:130-135`; the policy at
    `cli.py:38-50`. The three load-pass chaining sites the roadmap cites
    (`cli.py:279-284, 306-309, 385-386`) are exactly where `plan-resolution`
    will chain, and `tests/test_cli_history.py:660` shows how a "not chained"
    claim is AST-pinned.
  - **mypy already covers the new package.** `pyproject.toml:60-92`'s `files`
    list starts with `"src"`, so `src/fitdocs/plans/` is type-checked with no
    edit; only test modules are opt-in there (performance-benchmarks added
    nine). The roadmap's "mypy files list moves" item therefore reduces to
    adding the typed test modules this spec wants checked.

## Research Log

### Where a plan source can live, and why not inside an owned path
- **Context**: the roadmap's viability check (2026-09-15) and the brief both
  require the source outside every `OWNED_PATHS` prefix. The design needs the
  exact contract wording and the settings precedent.
- **Sources Consulted**: `docs/ownership-contract.md:37-71` (owned = "may
  create, rewrite, or delete wholesale"), `:101-118` (configured locations
  grant *write* rights), `:357-386` (shared and user-owned files);
  `layout.py:126-142` (`OWNED_PATHS` docstring: `fitdocs.toml` and
  `athlete.toml` are not owned; configured locations are a union);
  `layout.py:311-318` (`DEFAULT_INBOX_DIR` "is not part of OWNED_PATHS");
  `tests/test_layout.py:603-614, 639-644`; `inbox.py:228-277, 417-529`.
- **Findings**:
  - The configured-locations clause is about *write* grants. A plan-source
    directory is a configured *read* location; nothing in the contract or the
    guard models that today, and the contract's `:106` sentence ("No fitdocs
    feature names such a location yet") is already stale relative to inbox
    (queue item `2026-09-12-ownership-contract-prose-stale-and-unpinned`).
  - The confinement guard measures writes only (`test_confinement.py:624-672`):
    a read location needs no `SETTINGS_LOCATION_KEYS` entry. Staging a source
    under the data root before the `before` snapshot (`:655-659`) is the
    natural fixture shape.
  - An athlete could configure `[plans] path = "blocks"` or `"."`; the
    former puts the source inside an owned path (deletable wholesale), the
    latter makes the top-level `*.toml` glob pick up `fitdocs.toml` and
    `athlete.toml`. Both must be configuration errors.
- **Implications**: a `[plans] path` key, kept verbatim, resolved lexically;
  rejected when it resolves to the root or inside any owned prefix; never
  created by fitdocs; documented in the shared-and-user-owned section with a
  cross-reference from the configured-locations section distinguishing read
  from write grants.

### The rendered location and the shape of its pages
- **Context**: one block page plus N planned pages per block, with relative
  links between them and, later, to logged workout pages.
- **Sources Consulted**: `layout.py:28-33, 199-245, 248-278`;
  `structure.md` naming conventions; `tests/test_layout.py:563-600, 681-697`;
  `declaration.py:74` (`DECLARATION_FILENAME = "AGENTS.md"`).
- **Findings**:
  - A flat layout (`blocks/<id>.md` beside `blocks/<id>/<row>.md`) gives the
    block page a distinctive filename (what a PKM's quick switcher shows) and
    groups its planned pages under a same-named folder -- the "folder note"
    convention Obsidian users already know. A per-block directory holding an
    `index.md` would give five blocks five files called `index.md`.
  - One `OWNED_PATHS` entry (`blocks/`) covers the per-block subdirectories
    by prefix; unlike `history/assets/` there is no fixed subdirectory to
    name, so no new nesting pair joins
    `test_no_owned_prefix_is_a_prefix_of_another_except_the_two_assets_pairs`.
  - macOS filesystems are case-insensitive by default: a block whose id is
    `agents` would render to `blocks/agents.md`, which *is*
    `blocks/AGENTS.md` there. The id must be reserved.
  - A planned page's filename must be the row id, not a date-prefixed slug:
    a moved workout keeps its page (roadmap decision "rows carry a stable
    id"), and a filename carrying the date would be renamed by every move.
- **Implications**: `BLOCKS_DIR = "blocks"`; `block_doc_path`,
  `planned_doc_path`, `planned_rel_link` (`"<id>/<row>.md"` from the block
  page) and `block_rel_link` (`"../<id>.md"` from a planned page) built by
  string joins; ids `[a-z0-9][a-z0-9-]*` with `agents` reserved
  case-insensitively.

### The source grammar, and TOML's array-of-tables nesting
- **Context**: amendments are appended entries that name a row and the fields
  it changes, add or remove a row, or change a mesocycle's target; override
  entries share the grammar.
- **Sources Consulted**: the TOML 1.0 specification (array of tables:
  `[[amendment]]` followed by `[[amendment.update]]` attaches the nested
  array to the *last* `[[amendment]]` table); `tomllib` semantics (a bare
  `2026-09-21` is a `datetime.date`, a `2026-09-21T09:00:00` a `datetime`;
  `bool` subclasses `int`; multi-line strings may contain `\r\n`).
- **Findings**:
  - Typed sub-arrays (`[[amendment.update]]`, `[[amendment.add]]`,
    `[[amendment.remove]]`, `[[amendment.mesocycle]]`) read better and
    validate per shape than a single `[[amendment.change]]` array with an
    `op` discriminator, and are valid TOML with the attachment rule above.
  - `tomllib` returns separate top-level lists for `amendment` and
    `override`, so file order *between* the two arrays is not recoverable.
    Dates are the only shared timeline; requiring amendment dates to be
    non-decreasing makes "the plan as of date D" a well-defined prefix, which
    is what the override reference check needs.
  - Clearing a target load is not expressible (TOML has no null and `0` is
    forbidden as a stand-in for absent). Recorded as a known limitation of
    the v1 grammar; the amendment can restate a target, never clear it.
  - Unknown keys must be errors, not ignored: `summry` silently dropped is
    exactly the hand-written-source failure the loud-validation constraint
    exists for. `fitdocs.toml` tables ignore unknown keys because that file is
    shared across features; a plan source is not shared with anything.
- **Implications**: the grammar in design.md's "Plan-Source Grammar" table;
  amendments applied in file order with a non-decreasing date check;
  overrides checked against the prefix state as of their date; unknown keys
  at every level are problems.

### Frontmatter emission for two new page types
- **Context**: both pages need machine-readable frontmatter a PKM and the
  next spec can read, emitted without a YAML library.
- **Sources Consulted**: `history/page.py:127-252`; queue item
  `2026-09-12-history-methodology-id-bare-token-yaml-typed`;
  `render/frontmatter.py:85-154`; `contract.py:869-907` (`document_date`);
  `tests/test_contract_consumers.py:246-249, 261-343`.
- **Findings**: the history emitter's bare-token rule is the trap; a plan's
  `title` and `goal` are athlete-written free text, and the `goal` may span
  lines. Double-quoting every string always, with `\`, `"`, newline and tab
  escaped and any other control character rejected, is valid YAML, reads
  back as `str` through `contract.parse_frontmatter` for every value
  (including `1991`, `true`, `null` and `2024-01-01`), and keeps the emitter
  a dozen lines. Integers and booleans are emitted bare; dates are quoted ISO
  strings, as the workout document emits them, so `document_date` reads the
  planned page's `date` unchanged.
- **Implications**: `page.py` holds one `yaml_string` helper used for every
  string value on both pages; a round-trip test pins the six trap tokens.

### The resolution seam
- **Context**: `plan-resolution` must "plug a `Resolution` value into the
  render" (roadmap Boundary Strategy) without rewriting the renderer, while
  this spec must not embed downstream semantics (confidence labels, coverage
  statements, match states) in its own rendering.
- **Sources Consulted**: the roadmap's Phase 7 shared seams; the
  `plan-resolution` brief (row states, per-mesocycle sum beside the target,
  unplanned listing under the mesocycle, problems reported on the page);
  `load-history` design's `ModelConstants` seam (`FITTED` declared, never
  produced) and `training-load`'s load placeholder → fill pattern.
- **Findings**: a fully typed state enumeration defined here would fix the
  wording of states this spec never produces and pull `plan-resolution`'s
  vocabulary upstream. A *placement* contract -- typed slots holding
  rendered markdown fragments with stated placement and stated invariants --
  keeps the semantics downstream while guaranteeing no renderer change: the
  block table's resolution cell, the planned page's resolution section,
  lines before and after each mesocycle's table, and one block-level
  section. Links inside a fragment are the caller's to build, so the two
  page depths (one and two levels below the data root) are stated as part
  of the seam. The engine takes an optional `resolve: Callable[[Block],
  Resolution]`, called once per valid block, so the downstream pass reuses
  discovery, validation, writes and the report rather than re-implementing
  them.
- **Implications**: `plans/resolution.py` holds `RowResolution`,
  `MesocycleResolution`, `Resolution`, `UNRESOLVED_ROW` and `unresolved()`;
  the renderers validate a supplied value structurally (known ids, single
  line cells) and never interpret it.

### Determinism and the absence of a clock
- **Context**: byte-identical output for an unchanged source; the brief says
  "the only time this spec reads is the source's own dates".
- **Sources Consulted**: `tests/history/test_boundary.py:521-564` (the clock
  scan and its spellings), `tests/test_history_e2e.py:211-245, 467-515`
  (the fake-date contextmanager driving `time.time`, `TZ` and
  `SOURCE_DATE_EPOCH`).
- **Findings**: nothing here needs "today" -- "upcoming" versus "not logged"
  is `plan-resolution`'s distinction and takes the pass's resolved `today`
  there. Weekday names must not come from `strftime("%a")` (locale); a
  seven-entry tuple indexed by `date.weekday()` is locale-free.
- **Implications**: the clock scan, the fake-date e2e and the hardcoded
  weekday tuple are all adopted.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Pure core, one I/O shell (chosen) | `source.py` reads, `engine.py` writes, everything between is pure over frozen dataclasses | Golden-testable pages, mutation-testable rules, no shared state; matches `history/` and `load/` | Two I/O modules instead of one (the source read and the page write are different files) | The read module is pure over *text* (`parse_block`) with a thin `load_block` wrapper |
| Hand-authored block page with tool regions | The athlete writes the page; fitdocs fills regions | No source grammar to learn | Inverts the ownership model on one page; no revision record; makes LLM markdown an input format | Rejected at discovery (roadmap) |
| Typed resolution states defined upstream | This spec enumerates matched/skipped/upcoming and renders each | One renderer, no fragments | Fixes downstream wording upstream; states this spec never produces | Rejected: placement seam instead |

## Design Decisions

### Decision: One new owned directory, `blocks/`, flat block pages with a same-named subdirectory per block
- **Context**: Research log, "The rendered location".
- **Alternatives Considered**:
  1. `blocks/<id>/index.md` + `blocks/<id>/<row>.md` -- uniform depth, but
     five blocks give five `index.md` files.
  2. `blocks/<id>.md` + `blocks/<id>/<row>.md` -- distinctive filenames,
     folder-note convention, two depths.
  3. `blocks/<id>--<row>.md` flat -- no directories, but a block with forty
     rows floods the directory listing.
- **Selected Approach**: option 2. One `OWNED_PATHS` entry, one
  `DECLARED_DIRS` entry, no fixed subdirectory constant.
- **Rationale**: PKM ergonomics and the ownership contract's prefix model
  both favour it; the depth difference is a two-helper cost.
- **Trade-offs**: link helpers must know which page they are on;
  `plan-resolution` builds workout links at two depths (stated in the seam).
- **Follow-up**: `test_owned_paths_cover_every_path_the_engines_write` walks
  both helpers.

### Decision: Two document types, both declared in `fitdocs.plans.page`, not in the contract leaf
- **Context**: the `training-history` precedent (`wiki-contract` design
  amendment note, `history/page.py:73-119`, `docs/ownership-contract.md:73-99`).
- **Selected Approach**: `BLOCK_TYPE = "training-block"`,
  `PLANNED_TYPE = "planned-workout"`, each with its own integer version and
  version key (`block_version`, `planned_version`) and its own ordered
  frontmatter key tuple; `MANAGED_KEYS`, `USER_KEYS`, `PRESERVED_REGIONS` and
  `DOC_VERSION` untouched; `CONTRACT_VERSION` is the only edit in
  `contract.py`.
- **Rationale**: the contract leaf is the most heavily pinned file in the
  repository and the roadmap fixes this rule.
- **Trade-offs**: a third and fourth type outside the leaf; the published
  contract explains where each is declared, as it does for the history page.

### Decision: The block page's `notes` region reuses the generic grammar and does not join `PRESERVED_REGIONS`
- **Context**: Research log, "The region grammar is generic".
- **Selected Approach**: the block page renders
  `region_block(NOTES_REGION, NOTES_PLACEHOLDER)` after its title, exactly
  where a workout document places it; the engine merges an existing
  generated page's region bodies with `docmerge.merge_regions`; a
  `RegionError` is a per-block failure. `PRESERVED_REGIONS` stays
  `("notes", "workout", "load")` and continues to describe workout documents.
- **Rationale**: the published preserved-region list is pinned by exact
  equality and documented as the workout document's; widening it would
  restate a workout-document guarantee for a page it does not describe. The
  mechanism is generic by design (`docmerge.py:5-12`).
- **Trade-offs**: the ownership document must say, in the new section, that
  the block page's `notes` region is preserved by the same mechanism without
  being listed in the workout document's region list.

### Decision: Always-quoted frontmatter strings
- **Context**: Research log, "Frontmatter emission".
- **Selected Approach**: one `yaml_string` helper; every string value
  double-quoted with `\`, `"`, `\n`, `\t` escaped; any other non-printable
  rejected (validation already rejects it in the source, so the emitter's
  check is structural); integers and booleans bare; dates quoted ISO.
- **Rationale**: removes the bare-token class of defect entirely for
  athlete-written values; matches the workout document's quoted date.
- **Trade-offs**: `sport: "Run"` is quoted where the workout document writes
  `sport: Run`. Both read back as the same `str`.

### Decision: Loud validation collects every independent problem, and unknown keys are problems
- **Context**: Requirement 2; Research log, "The source grammar".
- **Selected Approach**: shape problems are collected across the whole
  source; a structural fault (unreadable, not TOML, top level not a table,
  invalid bounds) is reported alone because nothing else can be judged
  without it; amendments are applied in order, an amendment with any invalid
  operation stops further application and later amendments and overrides
  are reported as "not checked"; unknown keys at every level are problems.
- **Rationale**: a hand-written source should be corrected in one pass;
  cascading messages after a failed amendment would mislead, so the stop
  rule bounds them.
- **Trade-offs**: an athlete fixing a broken amendment may see a second round
  of problems in later entries; each round is short.

### Decision: The resolution seam is a placement contract, and the engine takes a resolver callable
- **Context**: Research log, "The resolution seam".
- **Selected Approach**: `RowResolution(cell, section)`,
  `MesocycleResolution(before_table, after_table)`, `Resolution(rows,
  mesocycles, block_lines)`; `UNRESOLVED_ROW` renders `unresolved`;
  `unresolved()` is the default; `run_plan(data_root, *, resolve=None)`
  calls `resolve(block)` once per valid block.
- **Rationale**: no renderer change downstream; no downstream vocabulary
  upstream; the callable lets the downstream pass reuse everything else.
- **Trade-offs**: fragments are strings with stated invariants rather than
  a closed enumeration. The renderers enforce the structural invariants
  (known ids, single-line cells, `|` escaped) and nothing semantic.
- **Follow-up**: `plan-resolution` adds the two workout-link helpers to
  `layout.py` (from a block page: `../workouts/<stem>.md`; from a planned
  page: `../../workouts/<stem>.md`) and its own `EntryPoint`.

### Decision: A foreign file at any target path blocks the whole block; stale generated pages are removed; unsourced pages are reported, never deleted
- **Context**: Requirements 5.6, 7.8-7.10; `history/engine.py:209-227`'s
  foreign-occupant rule; the ownership contract's "owned = deletable
  wholesale".
- **Selected Approach**: before any write for a block, every target path is
  checked; one foreign occupant (a file without the generated marker, a
  symlink, or a directory where a file belongs) makes the block `blocked`
  and nothing of it is written or removed. A generated `.md` inside the
  block's directory that corresponds to no current row is removed. A block
  page or directory with no source is reported as unsourced and left alone.
- **Rationale**: "never half-rendered" applies to a blocked block as much as
  to an invalid one; removing a removed row's page is the brief's explicit
  requirement; deleting a whole block's pages because a source vanished (a
  rename, an evicted cloud file) is too aggressive for a stateless pass, and
  the contract's "may delete wholesale" is a permission, not an obligation.
- **Trade-offs**: a renamed source leaves the old pages until the athlete
  deletes them; the report names them every run.

### Decision: `blocked` and `invalid` both make the run exit 1
- **Context**: Requirement 8.9; the exit policy at `cli.py:38-50`.
- **Selected Approach**: any block whose requested render did not happen --
  invalid source, foreign occupant, write or removal failure -- makes the run
  exit `1`; a configuration error exits `2` and writes nothing; no sources
  exits `0`.
- **Rationale**: the history pass treats a foreign file as exit 0 because it
  has one optional page; here the athlete asked for a block and did not get
  it, and a script wrapping the command should notice.
- **Trade-offs**: once `plan-resolution` chains the pass after `sync`, a
  foreign file makes every sync exit 1 until it is moved. That is the loud
  behaviour the ownership contract prefers.

### Decision: A sixth private atomic-write copy, with a queued follow-up
- **Context**: Research log, key finding on `_atomic_write`.
- **Selected Approach**: `plans/engine.py` holds its own
  temp-file-then-`os.replace` helper with a `.plans-` prefix, as
  `history/engine.py` does and for the same reason (the boundary guard
  forbids importing a sibling engine).
- **Follow-up**: queue item recorded by this spec proposing a shared
  `docio.write_text_atomic` once a writer outside a guarded package needs
  it.

### Decision: No clock, no `today`
- **Context**: Research log, "Determinism".
- **Selected Approach**: the package names no clock function; the e2e test
  runs the command under two fake system dates and asserts byte-identical
  pages; weekday names come from a fixed tuple.

## Risks & Mitigations
- **The declaration quantifier guard trips on ordinary English** (`reach`,
  `everything`) -- every new fragment is checked against
  `tests/test_declaration.py:196`'s list before the golden is generated, and
  the golden task runs that test.
- **`_GOLDEN_NAMES` raises `KeyError`** for a fourth declared directory
  (queue item `2026-09-10-declared-dir-enumerations-hand-maintained`) -- the
  layout and declaration tasks form one atomic group with a stated red
  window, as `load-history` did.
- **The consumers guard forbids the literal `"workout"`** in registered
  modules -- the plans modules use `Sport.WORKOUT` and never lowercase a
  sport name.
- **An athlete-written prescription may contain region-marker-shaped text**
  -- it is rendered only on planned pages, to which `merge_regions` is never
  applied, and the block page renders only titles and summaries (single
  line, `|` escaped). Accepted.
- **Case-insensitive filesystems** -- the `agents` block id is reserved; row
  ids live in a directory with no declaration file.
- **A stale unsourced block directory accumulates** after a source rename --
  reported every run; the athlete deletes it. Accepted.

## References
- `.kiro/steering/roadmap.md` Phase 7 (discovery 2026-09-15) -- decisions,
  constraints, shared seams.
- `.kiro/specs/load-history/{design.md,tasks.md}` -- the non-activity
  location precedent and the atomic group-1 pattern.
- `.kiro/specs/wiki-contract/requirements.md` Amendments 1 and 2 -- the
  amendment block shape this spec's Amendment 3 follows.
- `.kiro/specs/plan-resolution/brief.md`, `.kiro/specs/build-training-block/brief.md`
  -- what the downstream specs consume.
- `docs/ownership-contract.md` -- owned paths, configured locations, shared
  and user-owned files, the second document type section.
- TOML v1.0.0 specification, "Array of Tables" -- nested `[[a.b]]` attaches
  to the most recently defined `[[a]]`.
