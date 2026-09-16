# Implementation Plan

## Upstream Prerequisites

- **`wiki-contract`** owns `src/fitdocs/contract.py`, `src/fitdocs/declaration.py`,
  `src/fitdocs/docmerge.py`, `docs/ownership-contract.md` and its conformance
  test, and the `AGENTS.md` goldens. This plan extends the declaration and the
  published contract, uses the region mechanism as published, and leaves
  every existing guarantee in force.
- **`load-history`** is the precedent, not a dependency: nothing under
  `src/fitdocs/history/` is imported, edited or extended. One history *test*
  constant moves -- `tests/history/test_engine.py`'s `_DECLARATION_PATHS`,
  a hand-maintained list of the declarations a history run may create,
  which a fourth declared directory would otherwise red (task 1.2). Its
  plan's group 1 (one atomic change with a stated red window) is reproduced
  here because the same three conformance tests hold the same four things
  equal.
- **`workout-docs`** owns `render/frontmatter.py` and the region placement
  on workout documents. Neither is imported; the block page places its
  `notes` region where a workout document does, by copying the convention,
  not the code.
- **`inbox`** established the configured-directory settings shape. Its reader
  is not imported; the shape is followed.
- **This plan has no upstream implementation prerequisite** -- every spec
  it builds on above has shipped -- **and it is the prerequisite of both
  downstream Phase 7 specs**: `plan-resolution` and `build-training-block`
  must not start until this plan is merged to `main`, because they consume
  the seams design.md states verbatim under "Cross-spec obligations"
  (`plan-resolution`'s tasks.md opens with exactly that prerequisite). A
  task that finds it must change a seam's shape stops and reports rather
  than changing it.

**Hard rules for every task**

- No task adds a key, a type, a reader or a region to
  `src/fitdocs/contract.py`. The single exception is stated under "Shared
  source file" below.
- No task writes, creates, renames or deletes anything under the resolved
  plan-source directory, in code or in a test's assertions about code -- a
  test that needs a source file writes it as fixture setup before the run
  and hashes it afterwards.
- No module under `src/fitdocs/plans/` imports `fitdocs.ingest`,
  `fitdocs.load`, `fitdocs.history`, `fitdocs.render`, `fitdocs.sync`,
  `fitdocs.audit` or `yaml`, names a clock function, or spells the literals
  `"---"` or `"workout"`.
- Only `src/fitdocs/plans/page.py` and `src/fitdocs/plans/engine.py` import
  `fitdocs.contract`. A renderer reaches the banner and the notes region
  through `page.py`.
- The words `each`, `every`, `all documents` and `any document` -- and any
  word containing `each` or `every` -- appear in no declaration fragment.
- A task that finds it needs a new dependency, a second command, a widening
  of the owned set beyond the one prefix this plan adds, or a change to a
  seam's shape, stops and reports.

## Shared source file

`src/fitdocs/contract.py` is edited by exactly one task in this plan (1.2)
and by exactly one line: `CONTRACT_VERSION` advances from `"3"` to `"4"`,
because a new owned path and two new document types change guarantees the
published contract states. The task asserts the literal reads `"3"` before
editing; any other value means a peer moved it and the task stops. No
`_Boundary:_` line below claims that file.

`src/fitdocs/layout.py` is edited by task 1.1 only. `src/fitdocs/declaration.py`
and `tests/test_declaration_goldens.py` by task 1.2 only. `src/fitdocs/cli.py`
by task 4.3 only. `pyproject.toml` by task 4.4 only.

Three files inside the new package have more than one writer, so each has a
stated rule:

- **`src/fitdocs/plans/__init__.py`** -- **append only**. Task 2.1 creates it
  seeded with its own names (the types and derivations `plan-resolution`
  reads); 2.2, 2.3, 3.1 and 4.1 append only their own module's names; **3.2
  and 3.3 do not touch it** (they are parallel, and two appends to one file
  in two worktrees is a conflict by construction) -- task 4.2 appends both
  renderer names when it wires them, and its own; task 4.4 pins the final
  list once. A wholesale rewrite by a late task silently drops an earlier
  one's names.
- **`src/fitdocs/plans/model.py`** -- created by 2.1 (types, identifiers,
  windows, row and target checks) and extended by 2.2 (amendments, the
  trail, overrides, `build_block`). Strictly sequential; 2.2 adds functions
  and dataclasses and changes nothing 2.1 wrote.
- **`src/fitdocs/plans/page.py`** -- written by 3.1 only. 3.2 and 3.3 import
  from it and add nothing to it; a helper either renderer finds missing is
  reported, not added in place.

**Cross-spec shared files.** `plan-resolution` is implemented after this
plan is merged and touches the following files this plan creates or edits
(each verified against `.kiro/specs/plan-resolution/tasks.md`; the task
numbers are that plan's). Written down so this plan's implementer shapes
each file for the append and writes each named pin knowing it moves.

*Append-only -- that plan adds a row, an entry, a block or a helper and
changes nothing this plan wrote:*

- `src/fitdocs/plans/__init__.py` (its module names, one append per module
  task: 2.1, 2.2, 2.3, 2.4, 3.1);
- `src/fitdocs/layout.py` (two logged-page link helpers and their docstring
  entries, 1.3) and `tests/test_layout.py` (two form-pin clauses and two
  round trips, 1.3);
- `src/fitdocs/cli.py` (three helpers and three chaining insertions after
  the load pass, 3.2) -- **except `plan_command`'s body, re-anchored below**;
- `tests/test_confinement.py` (a second `EntryPoint`, `reconcile`, with its
  negative half, 3.3);
- `tests/test_public_api.py` (`_CONTRACT_SURFACE` 1.1, `_HISTORY_SURFACE`
  1.2, `_PLANS_SURFACE` per module task, closed by 3.3);
- `tests/test_contract_consumers.py` (five forbidden literals and two
  binding extensions 1.1; the corpus module's registration 2.1);
- `tests/plans/test_boundary.py` (five module entries and an exemption map,
  one append per module task; and 3.3's positive control and threshold-closure assertion) -- **except two hunks re-anchored below**;
- `pyproject.toml` (four typed test modules in the mypy list, 3.3);
- `src/fitdocs/contract.py` (key constants, readers and their published
  names, 1.1; that plan asserts `CONTRACT_VERSION == "4"` before editing,
  so task 1.2 must leave the literal at exactly `"4"`);
- `docs/ownership-contract.md` (a paragraph in the two-further-types section
  and a clause appended to the `plan` overwrite bullet, 3.4; the version
  line does not move) and `README.md` (sentences appended to the plan
  paragraph, 3.4);
- `.kiro/steering/roadmap.md` (one checkbox each under Phase 7 `#### Existing
  Spec Updates`: this plan's 4.5 ticks `wiki-contract`, that plan's 3.4 ticks
  `workout-docs`, `build-training-block`'s 3.3 ticks `distribution`; different
  lines, and each plan is implemented after the previous one merges).

*Re-anchored by exception -- that plan edits, in place, something this plan
wrote; this plan writes each so the edit is one hunk:*

- `src/fitdocs/plans/page.py` (1.1): the four planned-page frontmatter key
  spellings `date`, `sport`, `modality`, `indoor` and the `INDOOR_WORD`
  constant are rebound to the contract's key constants as from-imports; no
  rendered byte changes. This plan spells each exactly once in `page.py`
  (task 3.1).
- `src/fitdocs/cli.py` `plan_command` (3.2): calls that plan's pass helper
  with its resolver instead of `run_plan` directly; the `except
  SettingsError` moves into the helper.
- `tests/test_cli_plan.py` (3.2): task 4.3's AST pin is re-stated (`run_plan`
  named nowhere in `cli.py`; the pass helper loaded at four sites).
- `tests/test_plan_e2e.py` (3.2): task 4.6's two-dates test gains the
  precondition that both local dates lie on the same side of every fixture
  row (design.md, Cross-spec obligations (training-blocks ↔
  plan-resolution), item 5).
- `tests/plans/test_boundary.py` (2.1, 2.3): the contract-importer pin
  widens from two modules (`page`, `engine`) to three (`corpus`), and the
  forbidden-target check's body gains a hunk consulting the exemption map.
- `src/fitdocs/declaration.py` `_BLOCKS_CONTENT` and its claim anchor (3.4):
  one clause naming the chained runs; `tests/declaration_golden/blocks.AGENTS.md`
  is regenerated by the goldens module's generator (the other three goldens
  are byte-identical because the version does not move).
- `.kiro/specs/training-blocks/{requirements.md,spec.json}` (3.4): that
  plan currently records an Amendment 1 against criteria 8.4 and 8.8;
  both are already scoped here to admit the resolver and the chaining, so
  whatever that plan lands there is a record, not a change of meaning.

**The partition rule** for any concurrent implementation: append a row, an
entry or a block, and nothing else; never rewrite or reorder an existing
one; never touch the peer's row -- the re-anchored hunks above are the
stated exceptions, each owned by one task of that plan. A conflict in one of
these files means the rule was broken, not that the two specs disagree.

## Test File Ownership

Each task owns the test modules named here, so no two tasks write the same
assertions.

- `tests/test_layout.py` (the whole module: the ownership-constant section
  and the plain-string-join form pin) → 1.1.
- `tests/test_declaration.py`; `tests/test_declaration_goldens.py` (edited:
  its hand-maintained golden-name mapping gains the `blocks` entry, then the
  module is run as the generator); all four files under
  `tests/declaration_golden/` (one new), produced by that generator and
  never hand-edited; `tests/test_declaration_refresh.py` (run);
  `tests/history/test_engine.py` (the `_DECLARATION_PATHS` constant only)
  → 1.2.
- `tests/test_ownership_contract.py` and `tests/test_docs_guarantees.py`
  (run; edited only if a by-value pin must move) → 1.3.
- `tests/plans/__init__.py` (the test package's module marker) → 2.1.
- `tests/plans/test_model.py` -- one headed section per task: identifiers,
  windows, rows and targets → 2.1; amendments, the trail, overrides,
  `build_block` → 2.2. Neither edits the other's section.
- `tests/plans/test_source.py`, `tests/plans/fixtures/*.toml` → 2.3, and 2.3
  alone: the "full source" fixture is the one block both renderer goldens
  render, so its property list is fixed in 2.3's bullets; 3.2 and 3.3 add
  nothing under `tests/plans/fixtures/`, and no task creates
  `tests/plans/conftest.py` (two parallel tasks creating it is a conflict
  by construction -- each renderer test loads the fixture through the
  parser itself).
- `tests/plans/test_resolution.py`, `tests/plans/test_page.py` → 3.1.
- `tests/plans/test_block_page.py`, `tests/plans/golden/block*.md` → 3.2.
- `tests/plans/test_planned_page.py`, `tests/plans/golden/planned*.md` → 3.3.
- `tests/plans/test_settings.py` → 4.1.
- `tests/plans/test_engine.py` → 4.2.
- `tests/test_cli_plan.py` (new) → 4.3.
- `tests/test_confinement.py`, `tests/plans/test_boundary.py`,
  `tests/test_public_api.py` (`_PLANS_SURFACE`),
  `tests/test_contract_consumers.py`, `pyproject.toml` → 4.4.
- `.kiro/specs/wiki-contract/{requirements.md,design.md,spec.json}` and the
  roadmap's Phase 7 `wiki-contract` checkbox → 4.5.
- `tests/test_plan_e2e.py` (new) → 4.6.

**Every new assertion names its mutation** (change-protocol § Fixture
Discrimination): each task's detail bullets name the production mutation
that must redden the assertion, and the implementer runs it through `uv run
pytest`, observes red, reverts, observes green, and says so in the report.

**No personal data**: every fixture is a synthetic plan source and a synthetic
page tree under `tests/plans/fixtures/` or `tmp_path`. No `.fit` file is read
by any task, and the athlete's real wiki is never a fixture.

- [ ] 1. Foundation: the new owned location and every guard that reads it

**Group 1 is one atomic change, and its three tasks are red in between.** The
owned-path set, the contract version, the declaration goldens and the
published contract document are held equal to one another by three separate
conformance tests, so no ordering of these tasks leaves a green suite at each
step:

- after 1.1 alone, **every writing pass raises**: `declaration_text` is an
  explicit dispatch that raises `ValueError` for a directory it does not
  recognise, and `ensure_declarations` calls it for every declared
  directory, so `sync`, `regen`, `load`, `drain` and `history` all fail on
  their declaration refresh until 1.2 adds the branch --
  `tests/test_declaration.py`, `tests/test_declaration_refresh.py`,
  `tests/test_confinement.py`, `tests/test_sync_e2e.py`, `tests/test_cli*.py`,
  `tests/test_history_e2e.py` and `tests/history/test_engine.py` are all red;
  `tests/test_declaration_goldens.py` raises `KeyError` (a newly declared
  directory with no golden-name entry); and
  `tests/test_ownership_contract.py`'s owned-paths equality reds, because the
  published document still lists seven owned paths;
- after 1.2 alone, `tests/test_ownership_contract.py`'s version pin reds,
  because the document's version line still states `3`.

Each of 1.1 and 1.2 names the tests it is *expected* to leave red and until
when; **the group is validated as a unit at 1.3**, and no implementer may
report a green suite before then. If the group is executed by a single
implementer, running 1.1-1.3 back to back before validating is the intended
shape.

- [x] 1.1 Add the blocks location and the plan-source default to the layout leaf and move its constant pins
  - Add the rendered directory name, the default plan-source directory name
    and the source-file suffix as named constants, plus five pure path
    helpers: the block page's filesystem path, the block's pages directory,
    a planned page's filesystem path, the planned page's link relative to
    the block page's directory, and the block page's link relative to a
    planned page's directory -- the two links built by plain string joins so
    separators stay forward slashes on every operating system
  - Extend the owned-path set with the rendered directory and the
    declared-directory set with the same directory. No subdirectory constant
    joins either set: a block's pages directory is named by the block, and
    the parent prefix covers it, so no new pair joins the allowed-nestings
    assertion
  - The default plan-source directory is **not** owned, the same treatment
    the default inbox directory receives; state it in the constant's
    docstring and pin it
  - Update the module docstring's list of layout directories
  - The module performs no file I/O, exactly as it does today
  - Pins: the exact owned-path tuple and the exact declared-directory tuple;
    the directory list the tuple tests iterate; the engines-write walk gains
    both page helpers and asserts both link round trips (block page's parent
    joined with the planned link equals the planned path; planned page's
    parent joined with the block link normalises to the block path); the
    planned link equals the literal `"<id>/<row>.md"` by string equality;
    the default plan-source directory is not owned; the existing
    plain-string-join form pin (no `os` import in the module; per helper no
    `Path(`, no `PurePath(`, no `os.`) gains a sibling clause for the two
    link helpers pinning their sanctioned spellings -- the `f"{block_id}/`
    token in the planned link and the `"../` token in the block link -- so a
    rewrite through `pathlib` or `posixpath` reds even where it would
    produce the same string
  - Named mutations: drop the rendered directory from the owned set (the
    tuple pin and the engines-write walk red); place it in the declared set
    without the owned set (the subset pin reds); drop the block directory
    from the planned link, emitting `<row>.md` (the round-trip pin reds);
    emit the block link without the parent step (its round trip reds);
    rewrite the planned link as `str(PurePosixPath(block_id) / f"{row_id}.md")`
    (the form pin reds; the value would be identical, which is why the form
    pin exists)
  - Expected red until 1.2 and 1.3: every writing pass's declaration
    refresh (the dispatch raises for the new directory until 1.2 adds its
    branch, so the sync, regen, load, drain, history, confinement and CLI
    suites red), the declaration goldens (a declared directory with no
    golden-name entry) and the ownership-contract conformance test (the
    published document still lists seven owned paths). All of it is the
    group's stated red window, not a defect; only `tests/test_layout.py` is
    this task's own green
  - Observable: `uv run pytest tests/test_layout.py` green; a Python shell
    resolves the block page path to `<root>/blocks/<id>.md`, a planned page
    to `<root>/blocks/<id>/<row>.md`, and the two links to `<id>/<row>.md`
    and `../<id>.md`
  - _Requirements: 4.1, 4.6, 4.10, 5.1, 7.1, 7.2_
  - _Boundary: BlockLocation_

- [x] 1.2 Advance the ownership contract version and give the blocks directory its own declaration
  - **Before editing, assert `contract.CONTRACT_VERSION == "3"`**; any other
    value means a peer moved it -- stop and report rather than advancing
  - Advance the published contract version by one. This is the only edit
    this plan makes inside the document-contract leaf and it is one string
    literal
  - Add a fourth branch to the declaration text's explicit dispatch, keyed
    on the rendered directory, with its own heading; the existing
    unrecognised-directory error stays the only fall-through; update the
    function's docstring, which today says it dispatches over exactly the
    three members of the declared set and lists them, to four and the new
    list -- no test pins that sentence, which is why it is named here
  - Add three named claim fragments into the existing fragment table, each
    followed by the anchor comment naming the code that makes it true: one
    stating that the directory holds generated training-block pages and, in
    a subdirectory named after its block, the planned-workout pages that
    block links to, rendered from the athlete's plan sources whenever the
    plan command runs; one stating that a block page carries one user-owned
    region, `notes`, carried over verbatim on rerender, and that a
    planned-workout page carries no user-owned region and is rewritten in
    full; one stating that the pages are re-derivable from the plan sources
    alone, that the sources live outside this directory in the athlete's
    plan directory, and that fitdocs never writes there. Write around the
    quantifier guard's substring list -- no `each`, `every`, `all
    documents`, `any document`, and no word containing `each` or `every`
  - Add the `blocks` entry to the goldens module's hand-maintained
    golden-name mapping **before** running its generator: the mapping is a
    literal dictionary with one entry per declared directory, so a fourth
    directory without an entry makes both the generator and the
    parameterised test raise rather than fail an assertion
  - Regenerate every declaration golden by running the goldens module's own
    generator -- all four change, because the owner block carries the
    contract version -- and never hand-edit one
  - Extend the outside-the-declared-set list with `blocks` and `blocks-old/`
    so the no-fall-through claim covers the new prefix's near-misses
  - Move the one history test constant a fourth declared directory reds:
    `tests/history/test_engine.py`'s `_DECLARATION_PATHS` is a hand-written
    set of the two declarations a history run may create, excluded from that
    test's before/after snapshot; once the rendered directory is declared, a
    history run also creates its declaration and the snapshot comparison
    reds. Derive the set from the declared directories and the declaration
    filename (minus the history entry, which the snapshot already excludes)
    so the next declared directory does not repeat this; touch nothing else
    in that module and nothing under `src/fitdocs/history/`
  - Pins: all four goldens exist and match; the blocks text names the `notes`
    region and no other region id; a directory outside the declared set
    raises; the pairwise-distinct assertion now spans four directories; the
    quantifier guard passes over the new text; the refresh path rewrites a
    stale declaration and leaves a foreign one alone, for all four
  - Named mutations: route the rendered directory through the history
    branch (the blocks golden comes back with history prose and reds); leave
    the version at its previous value (all four goldens red); write "every
    block page" into a fragment (the quantifier guard reds)
  - Expected red until 1.3: the published contract's version line still
    states the previous version, so the ownership-contract conformance test
    reds. That is the group's stated red window, not a defect
  - Observable: `uv run pytest tests/test_declaration.py tests/test_declaration_goldens.py tests/test_declaration_refresh.py`
    green; `tests/declaration_golden/` holds four goldens whose owner blocks
    all state the new version
  - _Depends: 1.1_
  - _Requirements: 7.2, 7.5, 7.6_
  - _Boundary: BlockDeclaration_

- [ ] 1.3 Publish the blocks location, the plan-source location and the two document types in the ownership contract and the README
  - State at the top of the document what changed at this contract version:
    a new owned path, a fourth declared directory, two further document
    types, and -- new in kind -- a user-owned plan-source location fitdocs
    only reads
  - Add the rendered directory to the owned-path list with one sentence
    (block pages at the top level, planned-workout pages in a subdirectory
    per block), and to the sentence naming the directories that receive an
    in-tree declaration
  - Add a new section after the training-history one for the two further
    document types: their type values, their version keys as plain integers,
    that both are published by the plans package rather than by the
    document contract and why; that the block page carries one user-owned
    region, `notes`, preserved by the same mechanism as a workout document's,
    while the regions section's list continues to describe workout documents
    and is not widened; that the planned page carries no user-owned region
    and is rewritten in full; that a removed row's page is deleted on the
    next run; that a file without the provenance marking at a page's path
    blocks that block; and that a page with no source is reported and kept
  - Add a fourth bullet to the shared-and-user-owned section for the
    plan-source directory: user-owned, read-only to fitdocs, never created,
    written, renamed or deleted; located by the `[plans] path` key, default
    `plans/`; must not be the data root or lie inside an owned path
  - In the configured-locations section, add one sentence distinguishing a
    configured *read* location, which grants nothing, from a configured
    *write* location, and correct its stale sentence claiming no feature
    names such a location yet (the inbox does)
  - Replace the settings-file bullet's "`[tiles]` today" with the live table
    list -- tiles, inbox, plugins, load, history, plans -- keeping its
    read-only statement (this absorbs queue item
    `2026-09-10-ownership-contract-fitdocs-toml-tables-stale`, and the
    configured-locations correction above partially absorbs
    `2026-09-12-ownership-contract-prose-stale-and-unpinned` -- say so in
    the report so the controller can close the first and update the second,
    which also names a test module that does not exist)
  - Add a `plan` bullet to the overwrite-semantics section, the two version
    keys to the format-versions section, and the fourth declaration to the
    root-instructions section
  - README: a numbered paragraph for the plan command beside the history
    one; a `[plans]` key table beside the inbox one (`path`: default
    `plans`; absolute used as given, relative against the data root; never
    created; must be outside the owned paths); the ownership paragraph
    extended with the rendered directory, the two types, the notes region on
    a block page, and the fourth declaration
  - Pins: the conformance test that holds the document's version line and
    owned-path list equal to the code passes with the new path and version;
    every intra-documentation anchor link still resolves; the regions
    section still equals the preserved-region tuple
  - Named mutation: add the owned path to the code constant without adding
    it to the document (the conformance test reds)
  - Observable: **the whole group's validation point** -- `uv run pytest`
    green across the **whole suite**, which is the only honest closing point
    for a window in which every writer's declaration refresh raised
    (`tests/test_layout.py`, `tests/test_declaration*.py`,
    `tests/test_ownership_contract.py`, `tests/test_docs_guarantees.py`,
    `tests/history/test_engine.py`, `tests/test_confinement.py`,
    `tests/test_sync_e2e.py`, `tests/test_cli*.py` and
    `tests/test_history_e2e.py` are the modules the window named) -- with the
    published
    contract's owned-path list holding eight entries and its version line
    stating `4`
  - _Depends: 1.1, 1.2_
  - _Requirements: 7.2, 7.3, 7.4, 7.5_
  - _Boundary: OwnershipDocs_

- [ ] 2. The source model: types, derivation, amendments, and the grammar

- [x] 2.1 Create the plans package and declare the model's types, identifiers, mesocycle windows, and the row and target checks
  - Create the package with its module marker and a published-surface list
    seeded with this task's own names, and create the test package's module
    marker (`tests/plans/__init__.py`, the shape every sibling test package
    has, needed because the new modules reuse basenames such as
    `test_engine.py`), then declare in the model module: the planned-workout
    value
    (id, date, sport from the activity model's sport enumeration, an optional
    modality from its modality enumeration, an optional tri-state indoor
    flag, single-line title and summary, a multi-line prescription); the
    mesocycle-target value (number, optional positive finite target load,
    optional focus); the plan state (rows in insertion order with unique ids,
    targets ascending by number) with its two lookups; the derived mesocycle
    (number, window, nominal length, target, focus, its rows) with its
    length and its shortness as properties; the problem record with its
    one-line description
  - Declare the identifier pattern (lowercase letters, digits and hyphens,
    beginning with a letter or digit) and the reserved block-id set, derived
    at import from the declaration filename's stem and compared
    case-insensitively -- never a second spelling of that name
  - Implement mesocycle-window derivation from the bounds and the length by
    arithmetic (the last window ends on the block's last day and may be
    short) and the window lookup for a date; the row check (a date outside
    the bounds is a problem naming the row by id); the target check (a
    number outside the derived range or named twice is a problem naming the
    number)
  - Pure: no path, no clock, no I/O, no TOML; imports the two enumerations
    from the activity model and the declaration filename constant from the
    declaration module, and nothing else from the package
  - Pins: windows for an exact multiple and for a short last window; a
    one-day block; a length longer than the block (one short window); the
    lookup at both edges of a boundary; a row on the last day (in) and the
    day after (out); the reserved id in both cases; the pattern rejecting an
    uppercase letter, a leading hyphen and an underscore
  - Named mutations: use a strict comparison for the window's last day (the
    row-on-the-last-day pin reds); compute the count with floor division
    (the short-window pin reds); compare the reserved id case-sensitively
    (the uppercase pin reds)
  - Observable: `uv run pytest tests/plans/test_model.py` green and
    `uv run mypy --strict tests/plans/test_model.py` green (4.4 registers the
    module and must find nothing to fix); a Python shell derives three
    windows from a 70-day block at 28 days with the last 14 days long
  - _Requirements: 1.4, 1.5, 2.4, 2.6, 2.8, 3.1, 3.2_
  - _Boundary: PlanModel_

- [ ] 2.2 Apply amendments in order, keep the revision trail, check overrides as of their date, and build the block
  - Declare the four operation shapes the source states (update by id with a
    typed field mapping, add a full row, remove by id, change a mesocycle's
    target or focus), the amendment specification (date, reason, operations),
    the four change records each carrying before and after, the amendment
    record (ordinal, date, reason, changes), the override value (date, row
    id, stems, skipped, optional reason), and the block aggregate
  - Apply amendments in file order to the plan as first written, producing
    the state after each amendment, the trail, and the problems: an update
    must name an existing row, change at least one field, change only the
    mutable fields, and yield a row that satisfies the original-row rules; an
    add must use an id never used in the block's history; a remove must name
    an existing row; a target change must name a number in range and carry
    at least one of load or focus -- and it may name a mesocycle with no
    stated target, in which case the change record's superseded value is
    the absent target (both fields unset), the state gains the target, and
    a field the change does not state keeps its current value. An amendment
    with any invalid operation
    stops application: later amendments are not applied and one problem says
    which ones were not checked. Dates must be non-decreasing in file order
  - Check overrides: a row id must exist in the state after every amendment
    dated on or before the override's date; nothing else about an override
    is judged
  - Build the block: current state, trail, and mesocycles whose rows are the
    current rows in each window ordered by date and then by position in the
    current row list, so source order holds within a day and added rows
    follow original ones
  - Append the new names to the package's published surface list
  - Pins (a headed section of the model test module): each rule with a
    fixture that violates it and a sibling that satisfies it; the stop rule
    (an amendment referencing a row a failed earlier amendment would have
    added yields the "not checked" problem, never a spurious unknown-id one);
    a move across a boundary changes the mesocycle and keeps the id; an
    override dated before the amendment that adds its row (problem) and on
    the same day (valid); an equal date pair (valid) and a descending pair
    (problem); remove then re-add the same id (problem); a two-workout day
    whose ids sort in the opposite order to their source positions renders
    in source order; the sum of mesocycle row counts equals the current row
    count; a target change on a mesocycle with no stated target (valid; the
    change record's superseded value has both fields unset and the
    resulting state holds the target)
  - Named mutations: let an add reuse a removed id (the history pin reds);
    check override existence against the final state (the before-add pin
    reds); keep applying after an invalid amendment (the "not checked" pin
    reds); order a day's rows by id (the source-order pin reds); take a
    moved row's mesocycle from its original date (the cross-boundary pin
    reds); reject a target change on an untargeted mesocycle (its pin reds)
  - Observable: `uv run pytest tests/plans/test_model.py` green and
    `uv run mypy --strict tests/plans/test_model.py` still green; the trail
    for a fixture with one move, one add, one remove and one target change
    carries four change records with the superseded values
  - _Requirements: 2.2, 2.9, 2.10, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 6.4_
  - _Boundary: PlanModel_

- [ ] 2.3 Parse and validate a plan source into a block, naming every problem
  - Add the source module: a pure parse over text and a thin file read that
    decodes UTF-8 and delegates. An unreadable or non-UTF-8 file is one
    problem naming the file; a TOML decode error is one problem carrying the
    decoder's message. This is the package's only file read
  - Implement the grammar exactly as design.md's table states it: required
    top-level fields; bare TOML dates only (a datetime or a quoted string is
    a problem whose message says to write it unquoted); booleans rejected
    wherever a number is expected; the sport must equal one of the seven
    enumeration values exactly and the message lists them; modality only
    with the generic sport and from its enumeration; single-line fields
    rejected on a line break; multi-line fields with CRLF normalised and any
    other control character (except tab) rejected; identifiers matched and
    the reserved block id refused; duplicate ids among original rows named
    at both entries; unknown keys at every level are problems naming the key;
    the override's stems-or-skipped exclusivity and the skipped flag's value
  - Collect every independently determinable problem across the document;
    the three structural faults (top level not a table; bounds missing,
    not dates, or reversed; mesocycle length missing or not a positive
    integer) stop parsing after being reported, because every later rule
    needs the bounds
  - Name entries positionally and by id (`workout[2] (id w1-thu)`,
    `amendment[1].update[0] (id w1-thu)`, `override[0] (id w1-thu)`); the
    file name is the engine's to prepend
  - After shape validation, delegate to the model's checks and amendment
    application, merge the problems in document order, and raise the
    validation error when any exist; otherwise build the block
  - Spell no fence literal and no lowercase workout literal; import no YAML
  - Append the new names to the package's published surface list
  - Pins (with synthetic fixtures): the minimal valid source; a full source
    with every optional key **and exactly the properties the two renderer
    goldens need, because 3.2 and 3.3 render this fixture and add none of
    their own**: a short last mesocycle, a rest day, a two-workout day whose
    ids sort opposite to their source order, a generic strength indoor row,
    a pipe in a summary, a bracket in a title, a multi-line goal, one
    targeted and one untargeted mesocycle, a three-line prescription, and
    two amendments covering all four change kinds including a
    cross-boundary move and a prescription change; one fixture per rule that
    violates it, asserting
    the entry, the field and a message fragment; a three-fault fixture
    yielding three problems in document order; the structural stop (reversed
    bounds plus a bad row yields one problem); a quoted date; a datetime; a
    boolean mesocycle length; an unknown key at the top level, in a workout,
    in an amendment and in an override; CRLF normalised; a control character
    rejected; the file read over a missing file, a non-UTF-8 file and a
    non-TOML file
  - Named mutations: accept the lowercase sport (its fixture reds); allow
    modality with a running row (its fixture reds); ignore unknown keys (the
    unknown-key fixtures red); report only the first problem (the
    three-fault fixture reds); accept a quoted date (its fixture reds)
  - Observable: `uv run pytest tests/plans/test_source.py` green and
    `uv run mypy --strict tests/plans/test_source.py` green; parsing the
    full fixture yields a block whose mesocycles, trail and overrides match
    the fixture by inspection
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.10, 2.12, 3.4, 3.8_
  - _Boundary: SourceParser_

- [ ] 3. Rendering: the seam, the vocabulary, and the two pages

- [ ] 3.1 Declare the resolution seam and both pages' vocabulary, and write the frontmatter emitter and the escaping helpers
  - Declare the seam exactly as design.md states it verbatim under the
    plan-resolution obligations: the row resolution (a single-line cell and
    section lines), the mesocycle resolution (lines before and after the
    table), the resolution (rows by id, mesocycles by number, block-level
    lines), the unresolved row constant, and the unresolved default
    constructor. No rendering logic and no downstream vocabulary live here
  - Declare in the page module both types' values, format versions, version
    keys and ordered frontmatter key tuples; import the shared vocabulary --
    fence, type key, generator key, generator, banner, notes region id and
    placeholder -- from the contract, never re-spelling it, and expose the
    banner and the notes region block through two helpers so the renderers
    import no contract name. This module and the engine are the package's
    only importers of the contract
  - Write the frontmatter emitter as plain ordered lines, never through a
    YAML library: one string helper that rejects any character neither
    printable nor newline nor tab, escapes backslash, double quote, newline
    and tab, and wraps in double quotes; **every string value is quoted,
    always**, with no bare-token path; integers bare; booleans bare; dates
    as quoted ISO strings; a `None` value omits its key
  - Add the cell helper (escapes the pipe), the link-text helper (also
    escapes square brackets), the locale-free weekday tuple, the day format,
    and the load format (integral values as integers, otherwise one decimal)
  - Add the three helpers both parallel renderers need, so neither has to
    add to this module or duplicate the other: the resolution structural
    check (raises a value error naming the offender for a row key that is
    not a current row id, a mesocycle key outside the derived range, or a
    cell containing a line break); the fence-line predicate (true for a line
    equal to the frontmatter fence, so a planned page's resolution section
    can refuse one without importing a contract name); and the sport phrase
    (the sport value alone, or with a parenthesised, comma-joined list of the
    stated modality and the word `indoor` when the flag is true -- `Run`,
    `Workout (strength)`, `Ride (indoor)`, `Workout (strength, indoor)`)
  - Emit the phrase's word `indoor` from one module-level constant,
    `INDOOR_WORD = "indoor"` -- the module's only spelling of that word
    outside the planned key tuple: it is
    deliberately the same spelling as the planned page's frontmatter key,
    which `plan-resolution` registers as a forbidden literal in the
    contract-consumer guard (this module is a registered consumer) and
    rebinds through the contract's constant with one edit to `INDOOR_WORD`.
    Likewise spell the four planned-page keys `date`, `sport`, `modality`
    and `indoor` exactly once each, in the key tuples, so that rebinding is
    confined to this module (design.md, Cross-spec obligations
    (training-blocks ↔ plan-resolution), item 6)
  - Append the new names to the package's published surface list
  - Pins: the unresolved default has empty mappings and the unresolved row's
    cell is the word `unresolved` with a one-line section; the two types
    differ from each other, from the workout type and from the history
    type's spelling; the two key tuples by value; the frontmatter round trip
    through the contract's parser returns `str` for every string including
    the tokens `1991`, `true`, `null`, `2024-01-01`, `0x1F` and `1_000`,
    `int` for integers and `bool` for booleans, in the given order; a
    multi-line goal round trips; a carriage return is rejected; the pipe
    and bracket escapes; the load format for `1200.0` and `1234.56`; the
    weekday for a known date with the process locale switched to a
    non-English one through `locale.setlocale` inside a try/finally (an
    environment variable alone does not change `strftime`), skipping when
    that locale is not installed; the structural check for an unknown row
    id, an unknown mesocycle number, a multi-line cell, and a valid value
    (no error); the fence predicate for the fence, a fence with trailing
    text, and an ordinary line; the sport phrase for all four shapes
  - Named mutations: emit a token bare when it matches the history emitter's
    pattern (the `true`/`1991` round trip reds); format the weekday with
    `strftime` (the locale pin reds); leave the pipe unescaped (the cell pin
    reds); change the unresolved cell's word (the pin reds, and 3.2's golden
    later); skip the mesocycle-range check (its pin reds); make the fence
    predicate a prefix match (the trailing-text pin reds); drop the `indoor`
    word from the phrase (its pin reds)
  - Observable: `uv run pytest tests/plans/test_resolution.py tests/plans/test_page.py`
    green and `uv run mypy --strict tests/plans/test_resolution.py` green
  - _Requirements: 4.2, 4.7, 4.11, 5.2, 5.4, 6.1_
  - _Boundary: ResolutionSeam, PageVocabulary_

- [ ] 3.2 (P) Render the block page
  - Add the block-page renderer, pure over the block and the resolution,
    importing neither the contract nor the region module directly: the
    banner and the notes region come from the page module
  - Validate the resolution first through the page module's structural
    check (every row key a current row id, every mesocycle key in range,
    every cell single-line, else a value error naming the offender)
  - Render the sections in design.md's stated order: frontmatter in the
    block key order; the banner; the title; the notes region bare after the
    title; the three summary lines (start, end with the day count, mesocycle
    length with the count and the last mesocycle's actual length); the goal
    heading and the goal verbatim; one section per mesocycle with the window
    and its length, the shortness clause when short, the focus when stated,
    the target line or the word `none`, the before-table lines, the day
    table with one row per calendar day (rest days as such, several
    workouts on a day as several rows repeating the day, in the mesocycle's
    row order, the sport cell from the page module's sport phrase, the
    title as a link to the planned page, the summary, the resolution cell),
    and the after-table lines; the block-level resolution
    section only when its lines are non-empty; the revision record with the
    as-first-written table and targets sentence, then one heading per
    amendment with its reason and one bullet per change showing the
    superseded value beside its replacement (single-line fields inline,
    strings double-quoted, an unset value marked as such; a multi-line
    field as nested was/now blockquotes; added and removed rows with date,
    sport, title and summary; target changes with old and new), or the
    no-amendments sentence
  - Every cell through the cell helper, every link text through the link
    helper, the arrow in ASCII
  - Do not touch the package's published surface list (task 4.2 appends this
    renderer's name) and add nothing under `tests/plans/fixtures/`: the
    golden renders 2.3's full fixture, loaded through the parser
  - `(P)` here means parallel with 3.3, after 3.1: both renderers import
    the page module and the model, and neither imports the other
  - Pins: a golden for 2.3's full fixture -- a synthetic block with a short
    last mesocycle, a rest day, a two-workout day whose ids sort opposite to
    their source order, a generic strength indoor row, a pipe in a summary,
    a bracket in a title,
    a multi-line goal, one targeted and one untargeted mesocycle, and two
    amendments covering all four change kinds including a cross-boundary
    move and a prescription change; a second golden for a block with no
    rows and no amendments; the date-coverage postcondition (the day tables
    together cover every date of the block exactly once); a placement test
    for a caller-built resolution asserting each fragment lands in its slot
    and nowhere else; the value error for an unknown row id, an unknown
    mesocycle number and a multi-line cell; a forbidden-phrase pin over the
    default render (`matched`, `skipped`, `upcoming`, `not logged`,
    `load_value`); byte-equality across two calls
  - Named mutations: sort a day's rows by id (the golden reds); drop the rest
    rows (the coverage pin reds); render an absent target as zero (the
    golden reds); place the after-table lines before the table (the
    placement pin reds); skip the unknown-id error (that pin reds)
  - Observable: `uv run pytest tests/plans/test_block_page.py` green; the
    golden reads end to end as a block page an athlete could plan from
  - _Depends: 2.3, 3.1_
  - _Requirements: 3.7, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 5.6, 6.2, 6.3_
  - _Boundary: BlockPage_

- [ ] 3.3 (P) Render the planned-workout page
  - Add the planned-page renderer, pure over the block, the row and the
    resolution, with the mesocycle number taken from the block's window
    lookup over the row's current date; it imports no region module (the
    page has no region) and no contract name
  - Validate the resolution through the page module's structural check, and
    reject a section line that satisfies the page module's fence predicate
  - Render: frontmatter in the planned key order (modality only when
    stated, indoor only when true), every key spelling taken from the page
    module's key tuple; the banner; the title; the planned-for
    line with the weekday and date, the page module's sport phrase, the
    mesocycle number and the link back to the block page with the block's
    title as link text; the summary in italics; the prescription heading and the
    prescription verbatim; the resolution heading and the row's section
    lines (the unresolved row's when the resolution names no entry)
  - Do not touch the package's published surface list (task 4.2 appends this
    renderer's name) and add nothing under `tests/plans/fixtures/`: the
    golden renders a row of 2.3's full fixture, loaded through the parser
  - `(P)` here means parallel with 3.2, after 3.1: the two renderers share
    only the page module and the model
  - Pins: a golden for the full fixture's generic strength indoor row with
    its three-line prescription; a running row asserting the modality and
    indoor keys are
    absent; the date reads back through the contract's date reader as the
    row's date; the mesocycle number for a row moved across a boundary,
    rendered from the amended block; a caller-built section landing under
    the resolution heading; no region marker anywhere on the page; the
    value error for an unknown id; byte-equality across two calls
  - Named mutations: emit the indoor key when false (the running-row pin
    reds); take the mesocycle from the original row's date (the moved-row
    pin reds); pass the prescription through the cell helper (a prescription
    containing a pipe reds the golden)
  - Observable: `uv run pytest tests/plans/test_planned_page.py` green
  - _Depends: 2.3, 3.1_
  - _Requirements: 3.6, 5.2, 5.3, 5.4, 5.7, 6.2, 6.3_
  - _Boundary: PlannedPage_

- [ ] 4. Integration: settings, the pass, the command, the guards, the amendment, and validation

- [ ] 4.1 Read the plans settings table and resolve the source directory
  - Add a peer settings reader beside the ones for tiles, inbox, plugins,
    load and history: it receives the already-parsed settings mapping and
    the settings path, validates only its own table, ignores unknown keys,
    and never opens a file. `path` is a non-empty string or absent;
    absent means unconfigured and is kept as `None`, never defaulted to the
    directory name inside the settings value
  - Add the lexical resolver: absolute used as given, relative against the
    data root, normalised without touching the filesystem; raise the
    table's error -- a subclass of the shared settings error, so the
    command's existing handler maps it to the configuration exit -- naming
    the file, the key and the resolved path when the result is the data root
    itself or lies inside any owned prefix. Existence is not checked here
  - Append the new names to the package's published surface list
  - Pins: absent file, absent table, empty table; a valid relative and a
    valid absolute path; a non-string, an empty string and a boolean; an
    unknown key ignored; `.`, the rendered directory, a path beneath it, the
    workouts directory, the tool-state directory and a parent-traversal that
    normalises to the root each refused naming the key; a directory whose
    name merely starts with an owned name (`blocks-mine`) accepted
  - Named mutations: skip the owned-prefix check (the rendered-directory pin
    reds); test the prefix on the string rather than on path components
    (the `blocks-mine` pin reds); accept a boolean (its pin reds)
  - Observable: `uv run pytest tests/plans/test_settings.py` green; a root
    with no settings file resolves to `<root>/plans`
  - _Requirements: 1.8, 1.9, 8.3_
  - _Boundary: PlanSettings_

- [ ] 4.2 Orchestrate the pass: discover, validate, resolve, render, write, remove, report
  - Add the package's one writing module. Read the settings document once,
    project the plans table, resolve the source directory. Apply the
    existence rule: absent and unconfigured yields a note and nothing else
    happens; absent and configured raises the settings error; present but
    not a directory raises it
  - Discover top-level source files by suffix, sorted by name, no recursion,
    a symlinked source reported as invalid with one problem; the block id is
    the file stem. Parse every source before any write; each yields a block
    or an invalid outcome carrying every problem
  - Scan the rendered directory for block pages and block directories with
    no source and list them in the report; never touch them; the
    declaration file at the top of the rendered directory is excluded from
    the scan, or every run after the first would report it
  - Refresh the ownership declarations once, before the first block write,
    only when at least one block is valid; record foreign outcomes in the
    report. Be explicit that the refresh iterates every declared directory,
    so a plan run may create the other three declarations -- inside the
    owned set, not a violation, and the reason the next task's negative half
    is phrased precisely
  - Per valid block, in order: call the resolver (default: the unresolved
    constructor) once with the parsed block; render every planned page and
    the block page (a renderer's value error is a failed outcome with its
    message); read the existing block page when present and generated and
    merge its region bodies into the fresh render (a region error is a
    failed outcome, page untouched); run the foreign check over the block
    page path, the pages directory and every planned page path (a symlink,
    an unreadable or non-UTF-8 file, a directory where a file belongs, or a
    file without the generated marker is foreign; absence is not) -- one
    foreign path makes the block blocked with nothing written or removed;
    compare bytes -- equal on every target with no stale page yields
    unchanged and nothing written; otherwise create the pages directory when
    the block has rows, write each differing planned page atomically with a
    plans-prefixed temp file and replace, remove every generated markdown
    file in the pages directory that is not a current row's page (a
    non-generated one is left and listed without blocking), then write the
    block page atomically last. An OS error on any step makes the block
    failed with the path and reason, skips the block's remaining steps, and
    lets the next block proceed
  - Take no date parameter and call no clock. Have no code path that writes
    under the resolved source directory. Report paths data-root-relative
    when inside the root, absolute otherwise
  - Append the renderer names from 3.2 and 3.3 and this module's own names
    to the package's published surface list
  - Pins: the rendered-then-unchanged pair with byte-identical files; an
    invalid source beside a valid one (the valid block rendered, the invalid
    one's pre-existing pages untouched byte for byte); a foreign block page
    and, separately, a foreign planned page (blocked, nothing written or
    removed); a stale generated planned page removed and a foreign markdown
    file in the directory kept and listed; an unsourced page and directory
    reported and kept; a damaged notes region (failed, untouched); a notes
    body carried verbatim across a source change; the default-absent and
    configured-absent directory pair; a symlinked source; a read-only pages
    directory (failed, no partial file, the next block still rendered); no
    declaration created by an all-invalid run; the resolver called exactly
    once per valid block with the parsed block; the declaration file never
    listed as unsourced on a second run; the source directory's bytes
    hashed before and after every scenario and unchanged
  - Named mutations: write the block page before the planned pages (a
    torn-state pin that fails the second planned write reds); skip the
    foreign check for planned pages (the foreign-planned pin reds); remove
    non-generated stale files (the kept-foreign pin reds); refresh
    declarations on the all-invalid run (its pin reds); report rendered when
    every target's bytes are equal (the unchanged pin reds); drop the
    declaration-file exclusion from the unsourced scan (the second-run pin
    reds)
  - Observable: `uv run pytest tests/plans/test_engine.py` green; running
    the pass twice over a fixture root produces identical bytes and the
    second report says unchanged for every block
  - _Depends: 2.3, 3.2, 3.3, 4.1_
  - _Requirements: 1.1, 1.2, 1.10, 2.11, 3.9, 4.1, 4.9, 5.1, 5.5, 5.6, 5.7, 6.3, 7.8, 7.9, 7.10, 8.1, 8.4, 8.5, 8.6, 8.7, 8.10_
  - _Boundary: PlanEngine_

- [ ] 4.3 Add the plan command and its run report
  - Add one command named `plan` with the shared data-root option and no
    other option: no force, no dry run, because the pages are always rebuilt
    and unchanged ones are detected by bytes
  - Reuse the module's existing helpers and exit constants for resolving the
    data root, reporting a configuration error and finishing; the settings
    error -- including the plans table's own -- maps to the configuration
    exit through the existing handler shape with no new branch; any invalid,
    blocked or failed block makes the run exit with the per-file-failure
    status
  - Print the report: the source directory; one line per block in its
    outcome's shape (rendered with the block page and the planned and
    removed counts; unchanged; invalid followed by one indented description
    per problem; blocked with each foreign path; failed with each path and
    reason); each unsourced path; each declaration that could not be placed;
    the note. Every detail line without markup or highlighting
  - Change nothing about the sync, regeneration, load or history commands,
    and add an AST assertion, in the shape the history command's test uses,
    that the pass's entry function is loaded by name exactly once, inside the
    plan command. Write it knowing it moves: `plan-resolution` chains the
    pass after sync, drain and regen and makes the plan command pass its
    resolver, then re-states this assertion in the same change (design.md,
    Cross-spec obligations (training-blocks ↔ plan-resolution), item 5), so
    state it in that shape and no wider
  - Update the module docstring's command list and exit-code paragraph
  - Pins: no data root gives the configuration exit naming the three ways to
    supply one; the success path prints every outcome line; an invalid
    source gives the per-file-failure exit with each problem line printed
    verbatim; a malformed plans table gives the configuration exit and
    creates no rendered directory; a configured absent directory gives the
    configuration exit; the default absent directory gives success with the
    note; a blocked block gives the per-file-failure exit naming the path;
    the command appears in the help text; its parameter set is exactly the
    data-root option; the AST pin
  - Named mutations: map the plans settings error to the per-file-failure
    exit (the configuration pin reds); call the pass from the sync command
    (the AST pin reds); return success when a block is invalid (the invalid
    pin reds)
  - Observable: `uv run pytest tests/test_cli_plan.py tests/test_cli.py`
    green; `uv run fitdocs plan --out <fixture root>` writes the pages and
    prints one line per source
  - _Depends: 4.2_
  - _Requirements: 8.2, 8.3, 8.6, 8.8, 8.9_
  - _Boundary: PlanCommand_

- [ ] 4.4 Register the pass in the confinement guard and pin the package's surface and boundary
  - Register the plan pass as a writing entry point in the confinement
    guard, with a fixture that stages one small valid source under the
    default plan directory inside the data root before the snapshot and a
    non-vacuity predicate that asserts a block page was written. No
    settings-location key is registered: the guard measures writes and this
    pass never writes there
  - Add the negative half explicitly and precisely: after the run the source
    file's bytes are unchanged and nothing under the plan directory was
    created, modified or deleted; no workout document, no history page, and
    neither the athlete profile nor the settings file was written. The other
    three in-tree declarations are deliberately **excluded** from the claim,
    because the declaration refresh may legitimately create them
  - Add the package boundary test in the history boundary test's shape: a
    hand-maintained module list checked against the package directory both
    ways; per-module import targets pinned by equality; the forbidden
    targets by name (the ingest layer, the load package, the history package,
    the render package, sync, audit, any YAML parser) matched by equality or
    dotted descent including aliased from-imports; the clock scan over the
    five spellings in code and docstrings; the reverse-reachability scan
    asserting no module under the load, ingest or history packages, nor the
    render views, sync or audit, imports the plans package in any form, with
    relative imports resolved against the enclosing package, the bare
    package namespace excluded from any allowance, and the synthetic
    controls proving each form is caught; and the no-source-write scan --
    no module under the package names `write_text`, `write_bytes`, an
    `open` in a writing mode, `os.replace`, `unlink`, `rmdir`, `rename` or
    `mkdir` except the engine, and the engine composes every write path
    from the layout helpers or the declaration refresh, never from the
    resolved source directory -- with a positive control (a synthetic module
    with a stray `write_text` is caught)
  - Pin the package's published surface name for name with an owner map and
    the identity assertion, and assert nothing from it is re-exported from
    the package root; register the page module (binding exactly the seven
    contract names it from-imports) and the engine module (binding the
    generated-marker predicate) in the contract-consumer guard, so its
    structural assertions apply to both; the region helpers come from the
    region module and are not bindings
  - Add the four typed test modules named in design.md to the mypy files
    list; the source tree is already covered
  - Named mutations: import the render views from the block renderer (the
    boundary test reds); call a clock in the engine (the clock scan reds);
    add a name to the surface without the pin (the surface pin reds); bind
    a local copy of the generated-marker predicate (the identity assertion
    reds); add a write call to the source module (the no-source-write scan
    reds); add an import of the plans package to the load engine (the
    reachability scan reds)
  - Observable: `uv run pytest tests/test_confinement.py tests/plans/test_boundary.py tests/test_public_api.py tests/test_contract_consumers.py`
    green and `uv run mypy` green; the confinement guard runs the plan entry
    point among the others
  - _Depends: 4.2_
  - _Requirements: 1.2, 3.9, 6.4, 7.2, 7.7, 8.4_
  - _Boundary: ConfinementRegistration, PackageBoundary, SurfacePins_

- [x] 4.5 Land the wiki-contract Existing Spec Update as Amendment 3
  - Amend the wiki-contract spec's requirements with an amendment block in
    the shape of Amendments 1 and 2, and three new criteria: on the
    published-ownership-contract requirement, the user-owned plan-source
    location stated in the shared-and-user-owned section (read-only to
    fitdocs, never created), and the rendered location named as
    fitdocs-owned and holding two further document types declared and
    versioned by this spec; on the in-tree-declaration requirement, what the
    rendered location's declaration states. Renumber no existing criterion
  - Add an amendment note to that spec's document-contract design block in
    the shape of the load-history note, naming the two types, their
    declaration site and the reason they are not published from the leaf;
    extend its owned-path-set bullet with the rendered directory and a
    sentence that a configured read location grants no write right; add the
    amendments entry to its spec metadata
  - Tick the roadmap's `wiki-contract` checkbox under Phase 7 `#### Existing
    Spec Updates` (`.kiro/steering/roadmap.md`) with "landed by
    training-blocks as Amendment 3", the way `build-training-block`'s 3.3
    ticks the `distribution` one; that checkbox is the only edit this plan
    makes to the roadmap
  - Observable: `/kiro-spec-status wiki-contract` reports the spec clean
    with its amendments entry listing this change, and that spec's
    requirements, design and metadata all name the plan-source location, the
    rendered location and the two document types; the roadmap's
    `wiki-contract` entry under Phase 7 reads `[x]`
  - _Requirements: 7.2, 7.3, 7.4, 7.5_
  - _Boundary: WikiContractSpecUpdate_

- [ ] 4.6 End-to-end and feature-level validation
  - Add the end-to-end test over a synthetic data root with two sources:
    run the command, assert the block pages and every planned page exist at
    the owned paths, assert the report lines, and assert a planned page's
    frontmatter reads back through the contract's parser with the stated
    keys and types
  - Assert byte-identical pages across two runs, and across two runs
    executed under two different fake system dates and time zones,
    importing the history e2e test's module-private fake-date context
    manager (`tests` is a package, so the import works; do not copy it) --
    the behavioural half of the clock scan. Write it knowing it moves:
    choose the two (timestamp, time zone) pairs so that both local dates
    already lie on the same side of every fixture row (for instance both
    after the block's last day) and say so in a comment naming
    `plan-resolution` -- with the default resolution any two dates prove
    the same thing, and this choice keeps that spec's re-anchoring to an
    added precondition assertion rather than a change of dates (design.md,
    Cross-spec obligations (training-blocks ↔ plan-resolution), item 5)
  - Assert the invalid-beside-valid, foreign-block-page, default-absent and
    configured-absent scenarios through the command with their exit codes
  - Assert the source directory's contents are byte-identical before and
    after every scenario
  - Run the whole suite plus the lint, format and strict type checks, and
    confirm the goldens, the ownership conformance test, the declaration
    goldens, the confinement guard and the public-surface pin are all green
    together
  - Observable: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
    and `uv run mypy` all green; the two dated runs produce identical bytes
  - _Depends: 4.3, 4.4, 4.5_
  - _Requirements: 1.2, 1.10, 2.11, 7.8, 8.1, 8.4, 8.6, 8.9_
