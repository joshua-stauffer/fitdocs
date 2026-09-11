# Implementation Plan

## Upstream Prerequisites

- **`effort-tags` must be implemented first.** This plan calls
  `contract.effort_tag` and switches on `EffortKind`, and it sets
  `contract.CONTRACT_VERSION` to `"3"` on the assumption that `effort-tags` has
  already set it to `"2"`. The roadmap already orders the two specs. A task that
  finds `effort_tag` absent stops and reports rather than defining a reader.
- **`wiki-contract`** owns `src/fitdocs/contract.py`, `src/fitdocs/declaration.py`,
  `docs/ownership-contract.md` and its conformance test, and the `AGENTS.md`
  goldens. This plan extends the declaration and the published contract and
  leaves every existing guarantee in force.
- **`training-load`** owns the load keys and the load pass. This plan reads the
  keys and changes nothing about the pass. It is deliberately independent of the
  wave-0 prompt-date decision: a page with no `load_value` is a counted gap under
  every candidate semantic, and no task here waits on it.
- **`workout-docs`** owns `render/frontmatter.py` and `render/charts/hero.py`.
  Neither is imported, edited or extended.

**Hard rules for every task**

- No task adds a key, a type, a reader or a region to `src/fitdocs/contract.py`.
  The single exception is stated under "Shared source file" below.
- No task adds a field, a key or a sub-table to `src/fitdocs/load/settings.py`.
  Reading `LoadSettings.default_calculator` is a read, not an extension.
- No task touches `src/fitdocs/load/profile.py`, `athlete.toml`, the benchmark
  parser or serializer (`performance-benchmarks` owns those), or
  `src/fitdocs/render/charts/hero.py`.
- No module under `src/fitdocs/history/` names a clock function, imports a YAML
  parser, or names the string `docs/reference`.
- A task that finds it needs a new dependency, a second command, or a widening of
  the owned set beyond the two prefixes this plan adds stops and reports.

## Shared source file

`src/fitdocs/contract.py` is edited by exactly one task in this plan (1.2) and by
exactly one line: `CONTRACT_VERSION` advances from `"2"` to `"3"`, because a new
owned path changes a guarantee the published contract states. `effort-tags` sets
it to `"2"`; this plan sets it to `"3"`; the roadmap orders the two specs so the
edits are sequential. No `_Boundary:_` line below claims that file, and no other
task in this plan opens it for writing.

`src/fitdocs/layout.py` is edited by task 1.1 only. `src/fitdocs/declaration.py`
and `tests/test_declaration_goldens.py` by task 1.2 only. `src/fitdocs/cli.py` by
task 5.3 only. `src/fitdocs/render/charts/palette.py` by task 4.1 only.

Three files inside the new package have more than one writer, so each has a
stated rule:

- **`src/fitdocs/history/__init__.py`** -- **append only**. Task 2.1 creates it
  with an empty published-surface list; every later task that publishes a name
  (2.2, 3.2, 4.2, 5.1, 5.2) appends only its own module's names and rewrites
  nothing already there; task 5.4 pins the final list once. A wholesale rewrite
  by a late task silently drops an earlier one's names, and the pin catches that
  only after the fact -- hence the rule here.
- **`src/fitdocs/history/sources.py`** -- created by 2.1. Task 2.3 makes exactly
  one further edit to it, and only the measurement-string correction its own
  bullets license. No other task opens it for writing.
- **`src/fitdocs/history/series.py`** -- created by 3.2 and extended by 3.3, 3.4
  and 3.5 in that order. The four are strictly sequential, none is marked `(P)`,
  and each adds only its own functions and its own headed section of the shared
  test module.

**Cross-spec shared files (wave 2)**

`performance-benchmarks` is the other wave-2 spec and is meant to be implementable
in parallel with this one. Five files are written by both plans:

- `tests/test_confinement.py` -- peer editor `performance-benchmarks` task 4.5
  (appends an `EntryPoint`); here task 5.4 (appends an `EntryPoint` only;
  `OWNED_PATHS` is widened in `src/fitdocs/layout.py` by task 1.1 and the guard
  reads it directly).
- `tests/test_contract_consumers.py` -- peer editor `performance-benchmarks`
  task 4.5; here task 5.4.
- `tests/test_public_api.py` -- peer editor `performance-benchmarks` task 4.5;
  here task 5.4.
- `src/fitdocs/cli.py` -- peer editor `performance-benchmarks` task 4.4; here
  task 5.3.
- `README.md` -- peer editor `performance-benchmarks` task 4.4 (the paragraph
  naming its command); here task 1.3.

**The partition rule, for all five**: append a row, an entry or a block, and
nothing else. Never rewrite or reorder an existing one; never touch the peer's
row. A conflict in one of these files means the rule was broken, not that the two
specs disagree.

`docs/ownership-contract.md` is also edited by `effort-tags` tasks 4.1 (its
version line) and 4.2 (the user-owned-keys and effort-tag sections), which land
first -- the roadmap orders `effort-tags` before this spec -- so task 1.3 amends
a document that already carries those sections, not the one in the tree today.
The "Upstream Prerequisites" note above names `wiki-contract` as that document's
owner, which it is; `effort-tags` is nonetheless the immediately preceding
writer. `README.md`'s Ownership paragraph has the same prior writer:
`effort-tags` task 4.2.

## Test File Ownership

Each task owns the test modules named here, so no two tasks write the same
assertions.

- `tests/test_layout.py` (the ownership-constant section) → 1.1.
- `tests/test_declaration.py`; `tests/test_declaration_goldens.py` -- **edited**:
  its hand-maintained golden-name mapping is a literal dictionary with one entry
  per declared directory, not a derivation over the declared set, so 1.2 adds the
  history entry there and only then runs the module as the generator; all three
  files under `tests/declaration_golden/` (one of them new), produced by that
  generator and never hand-edited; `tests/test_declaration_refresh.py` → 1.2.
- `tests/test_ownership_contract.py`, `tests/test_docs_guarantees.py` (run, not
  edited) → 1.3.
- `tests/history/test_sources.py` → 2.1.
- `tests/history/test_constant_guard.py` → 2.1 owns the scan itself. Any later
  task that legitimately needs a numeric literal under the package appends its
  own exemption entry there and appends nothing else -- an exemption is a claim
  about that task's own code, so it cannot live anywhere but with the task that
  writes the literal, and 2.1's no-unused-entry assertion is what keeps the table
  from growing unexamined.
- `tests/history/test_model.py`, `tests/history/test_worked_examples.py` → 2.2.
- `tests/history/test_coverage_threshold_measurement.py` → 2.3.
- `tests/history/test_documents.py` → 3.1.
- `tests/history/test_series.py` — one headed section per task: methodology →
  3.2, daily series → 3.3, weeks and coverage → 3.4, criterion points → 3.5.
  No task edits another's section.
- `tests/render/charts/test_calendar.py` → 4.1;
  `tests/render/charts/test_palette.py` is run, not edited, by 4.1 -- it walks
  every palette entry and reconverts its oklch source, so it covers the three
  new colours the moment they are registered.
- `tests/history/test_page.py` -- one headed section per task: the document
  vocabulary and the frontmatter emitter → 4.2; the body sections and the two
  goldens beneath `tests/history/golden/` → 4.3. Neither edits the other's
  section.
- `tests/history/test_settings.py` → 5.1.
- `tests/history/test_engine.py` → 5.2.
- `tests/test_cli_history.py` (new) → 5.3.
- `tests/test_confinement.py`, `tests/history/test_boundary.py`,
  `tests/test_public_api.py` (`_HISTORY_SURFACE`), `tests/test_contract_consumers.py`
  → 5.4.
- `.kiro/specs/wiki-contract/{requirements.md,design.md,spec.json}` → 5.5.
- `tests/test_history_e2e.py` (new) → 5.6.

**Every new assertion names its mutation** (change-protocol § Fixture
Discrimination): each task's detail bullets name the production mutation that
must redden the assertion, and the implementer runs it through `uv run pytest`,
observes red, reverts, observes green, and says so in the report.

**No personal data**: every fixture is a synthetically written page tree under
`tmp_path`. No `.fit` file is read by any task in this plan, and the athlete's
real wiki is never a fixture.

- [x] 1. Foundation: the new owned location and every guard that reads it

**Group 1 is one atomic change, and its three tasks are red in between.** The
owned-path set, the contract version, the declaration goldens and the published
contract document are held equal to one another by three separate conformance
tests, so no ordering of these tasks leaves a green suite at each step:

- after 1.1 alone, `tests/test_declaration_goldens.py` raises `KeyError` (a
  newly declared directory with no golden-name entry) and
  `tests/test_ownership_contract.py::test_owned_paths_equal_layout_owned_paths_exactly`
  reds, because the published document still lists five owned paths;
- after 1.2 alone, `tests/test_ownership_contract.py::test_contract_version_matches_code`
  reds, because the document's version line still states the previous version.

Each of 1.1 and 1.2 therefore names the tests it is *expected* to leave red and
until when; **the group is validated as a unit at 1.3**, and no implementer may
report a green suite before then. If the group is executed by a single
implementer, running 1.1-1.3 back to back before validating is the intended
shape.


- [x] 1.1 Add the history location to the layout leaf and move its constant pins
  - Add the directory name, the assets subdirectory (reusing the existing assets
    name so the two locations cannot diverge), the document stem and the chart
    name as named constants, plus three pure path helpers: the document's
    filesystem path, the chart's filesystem path, and the chart's link relative
    to the document's own directory, built by plain string joins so separators
    stay forward slashes everywhere
  - Extend the owned-path set with the history directory and its assets
    subdirectory, and the declared-directory set with the history directory
    alone -- the assets subdirectory is excluded for the same reason the
    workouts assets subdirectory is, because the parent's declaration already
    covers what is beneath it
  - The module performs no file I/O, exactly as it does today
  - Pins: the exact owned-path tuple and the exact declared-directory tuple; no
    duplicates and every entry ending in a separator; the declared set is a
    subset of the owned set; no owned prefix is a prefix of another except the
    two assets pairs; the relative chart link resolved against the document's
    parent equals the chart's filesystem path
  - Named mutations: drop the assets prefix from the owned set (the round-trip
    and subset pins still pass, but the confinement guard reds once 5.2 lands --
    so this task additionally asserts the assets prefix is present by value);
    place the history directory in the declared set without the owned set (the
    subset pin reds)
  - Expected red until 1.2 and 1.3: the declaration goldens (a declared directory
    with no golden-name entry) and the ownership-contract conformance test (the
    published document still lists five owned paths). Both are the group's stated
    red window, not a defect
  - Observable: `uv run pytest tests/test_layout.py` green; a Python shell
    resolves the history document path to `<root>/history/training-load-history.md`
    and the chart link to `assets/training-load-history-fitness.svg`
  - _Requirements: 5.1, 5.9, 7.1, 7.2_
  - _Boundary: HistoryLocation_

- [x] 1.2 Advance the ownership contract version and give the history directory its own declaration
  - **Before editing, assert `contract.CONTRACT_VERSION == "2"`**; if it reads
    `"1"`, `effort-tags` has not landed -- stop and report rather than advancing
  - Advance the published contract version by one, because a new owned path
    changes a guarantee the contract states. This is the only edit this plan
    makes inside the document-contract leaf and it is one string literal
  - Restructure the declaration text builder from its current two-branch
    if/else into an explicit dispatch over the declared directories with **no
    fall-through branch**: an unrecognised directory raises rather than
    inheriting another directory's prose, which is the defect the current else
    invites the moment a third directory exists
  - The workouts branch by this point carries `effort-tags`' user-owned-keys
    fragment (`_USER_KEYS`, selected after `_REGIONS` and before
    `_REDERIVABILITY_DOCS`); the dispatch must select it for `workouts/` and not
    for `history/` (the history page has no frontmatter the athlete owns). The
    goldens are regenerated by the generator, so silently dropping the fragment
    would produce a green golden --
    `tests/test_declaration.py::test_workouts_declaration_names_every_user_owned_key`
    is the guard, and this task runs it
  - Add two named claim fragments for the history directory, written into the
    existing fragment table with the anchor comment naming the code that makes
    each true: one stating the directory holds one generated longitudinal page
    and its chart image, both rewritten in full on every history run, with no
    user-owned region of any kind; one stating the page is re-derivable from the
    workout documents alone, so deleting it costs only a re-run. No fragment
    quantifies over documents and no fragment names a region the page does not
    have
  - Add the history entry to the goldens module's hand-maintained golden-name
    mapping **before** running its generator: the mapping is a literal dictionary
    with one entry per declared directory, not a derivation over the declared
    set, so a third directory without an entry makes both the generator and the
    parameterized test raise rather than fail an assertion
  - Regenerate every declaration golden by running the goldens module's own
    generator -- all three change, because the owner block carries the contract
    version -- and never hand-edit one
  - Pins: all three goldens exist and match; the text for the history directory
    names no region id; a directory outside the declared set raises; the existing
    "declaration text differs between directories" assertion is widened from the
    workouts-versus-archive pair to a pairwise-distinct assertion over all three;
    the refresh path rewrites a stale declaration and leaves a foreign one alone,
    unchanged from today for all three directories
  - Named mutations: restore the else fall-through (the history golden comes
    back with workout prose and reds); leave the contract version at its
    previous value (all three goldens red)
  - Expected red until 1.3: the published contract's version line still states
    the previous version, so the ownership-contract conformance test reds. That
    is the group's stated red window, not a defect
  - Observable: `uv run pytest tests/test_declaration.py tests/test_declaration_goldens.py tests/test_declaration_refresh.py`
    green; `tests/declaration_golden/` holds three goldens whose owner blocks all
    state the new version
  - _Depends: 1.1_
  - _Requirements: 7.2, 7.3_
  - _Boundary: HistoryDeclaration_

- [x] 1.3 Publish the history location and the second document type in the ownership contract and the README
  - Add the two new owned paths to the published contract's owned-path list with
    one sentence each, and add the history directory to the sentence naming the
    directories that receive an in-tree declaration
  - State at the top of the document what changed at this contract version
  - Add a short subsection naming the second document type the data root now
    contains, stating that it is published by the history package rather than by
    the document-contract leaf and why, that the page carries no user-owned
    region, and that it is rewritten in full on every history run
  - Add one line to the README's command summary for the new command
  - Pins: the conformance test that holds the document's enumerated lists equal
    to the code constants passes with both new paths and the new version; every
    intra-documentation anchor link still resolves
  - Review and correct the two sections that today speak of a single document
    type and a single in-tree declaration -- the one telling a wiki's root
    instructions to reference the generated documents directory's declaration,
    and the one on document-format versions and migration. The anchor-link check
    cannot catch a section that is stale but still linkable, so this is a read of
    both sections, not a search-and-replace
  - Named mutation: add the owned paths to the code constants without adding
    them to the document (the conformance test reds)
  - Observable: **the whole group's validation point** -- `uv run pytest` green
    across `tests/test_layout.py`, `tests/test_declaration*.py`,
    `tests/test_ownership_contract.py` and `tests/test_docs_guarantees.py`
    together, with the published contract's owned-path list holding seven entries
  - _Depends: 1.1, 1.2_
  - _Requirements: 7.2, 7.3_
  - _Boundary: OwnershipDocs_

- [x] 2. The model: its provenance, its recursion, and its measured threshold

- [x] 2.1 (P) Declare the model's citation records, seed constants, choices and the blocked preset
  - Create the history package with its module marker and its published surface
    list, then declare, in the sources module: two citation records at the
    recursion's own locators -- the 1990 paper at its equations (4) and (5) and
    the 1991 chapter at the pages carrying the two time constants -- whose
    author, year and work strings are identical to the existing records for the
    same two works in the metrics layer, which cite the training impulse at
    different pages
  - Declare the two time-constant seeds as cited constants governed by the 1991
    chapter, each carrying a corroboration on the 1990 paper's fitted table with
    the "differs" agreement and a note giving the fitted values, and each with a
    note stating in words that the value is an illustrative starting value never
    fitted to any athlete
  - Declare the two weighting seeds, both one, governed by a fitdocs choice
    rather than a citation, with a departure record stating that both primary
    texts use two for the fatigue weighting illustratively and that fitdocs
    reports form as fitness minus fatigue instead, because fitting the
    weightings is the gated downstream spec's job
  - Declare the coverage threshold as a cited constant governed by a fitdocs
    choice whose search basis records that no work in this literature states a
    minimum-coverage rule, and whose measurement states the per-page
    understatement the shipped recursion has and names the test that reproduces
    it. **The measurement's numbers are transcribed here from the design and are
    not yet verified against running code** -- this task precedes the recursion.
    Task 2.3 measures them and owns the correction if they differ
  - Declare the recursion-form choice (exact exponential decay against the vendor
    reciprocal approximation, stating the per-step divergence at both the fitness
    and the fatigue seed) and the daily-average scale choice. The divergence
    figures are transcribed here and pinned by 2.3 on the same footing as the
    threshold's, so no stated number in this module goes unreproduced
  - Declare the constant set value object -- the two time constants, the two
    weightings, a closed provenance enumeration with members for seeds,
    configured and fitted, and a one-line origin string -- and build the seed
    instance by reading the four cited constants' values, never by spelling a
    number. The fitted provenance member is declared here and produced by no code
    in this plan; it exists so the downstream fitting spec adds no member
  - Declare the blocked preset record naming the 42-day / 7-day Performance
    Management Chart pair, the values, and exactly what must be verified before
    either becomes a cited constant. It is a declared absence, not an omission
  - Pins: a registry walk asserting every cited constant in the module appears
    exactly once in the registry, no two share a name, every non-agreeing
    corroboration carries a note, every departure subject is unique, the seed
    instance's four values are the four constants' values, and no shipped
    constant carries 42 or 7 as a time constant; a field-by-field equality test
    between this module's two citations and the metrics layer's, excluding key,
    locator and note; an independent numeric-literal scan over the package's
    source with an exemption table naming each permitted literal's site and
    category and an assertion that no exemption entry is unused -- the scan walks
    **whatever modules exist under the package** rather than a fixed list, so it
    neither reds before its siblings land nor silently skips a module a later
    task adds; a scan asserting the reference-directory string appears nowhere in
    the package
  - Named mutations: add a 42-day time constant (the blocked-preset assertion
    reds); drop the "differs" corroboration (the seeds-are-unfitted assertion
    reds); make the seed instance spell its numbers (the literal scan reds);
    change one citation's work string (the equality test reds)
  - Observable: `uv run pytest tests/history/test_sources.py tests/history/test_constant_guard.py`
    green; importing the seed constant set yields provenance "seeds" and the
    two time constants 45.0 and 15.0
  - _Requirements: 2.4, 2.5, 2.6, 2.8, 2.10, 3.4_
  - _Boundary: ModelSources_

- [x] 2.2 Implement the recursion and prove it against the primary text's own worked figures
  - Add the pure recursion module: one step per element of the input sequence,
    each accumulator decaying by the exact exponential of minus the reciprocal
    of its time constant and then adding the day's load; accumulators start at
    zero because the archive begins with no accumulated history
  - Expose two entry points: the unscaled accumulators, and the reported series
    -- fitness and fatigue on the daily-average scale (each accumulator times
    its weighting times one minus its decay factor) and form as fitness minus
    fatigue. The module imports the constant set from 2.1 and holds no numeric
    literal of its own beyond arithmetic identities
  - The recursion runs over every day of the span with no knowledge of coverage
    or suppression; suppression is a reporting decision applied afterwards
  - Guard the inputs structurally: a non-positive or non-finite time constant, a
    negative or non-finite weighting, and a negative or non-finite load each
    raise, so a bad constant set cannot silently produce a curve
  - Prove it against the 1990 paper's own published figures: driving the model
    with that paper's stated inputs (a constant daily load of 100, a one-day
    interval, time constants of 45 and 15, weightings of 1 and 2) for 60 days
    must reproduce its printed weighted fitness and fatigue figures and their
    difference, and the continuous-training asymptote its equation (11) states.
    These are the weighted quantities, which is what fixes the fatigue weighting
    of two as the figures' own and rules out reading the second figure as a raw
    accumulator
  - Pins: the four published figures to the paper's own precision; a constant
    load converges to the weighting times that load; the reported series equals
    the unscaled accumulators times the constant rescaling elementwise and
    exactly; all three output tuples have the input's length; two runs on the
    same inputs are bit-identical
  - Named mutations: use the reciprocal of the time constant instead of one
    minus its exponential (the published figures red at the third significant
    figure); apply the weightings inside the recursion rather than at the
    combination (the day-60 pair reds); seed the accumulators with the first
    day's load twice (the off-by-one reds)
  - Observable: `uv run pytest tests/history/test_model.py tests/history/test_worked_examples.py`
    green; the day-60 pair reproduces the paper's printed figures
  - _Requirements: 2.1, 2.2, 2.3, 2.9, 2.10_
  - _Boundary: FitnessModel_

- [x] 2.3 Measure and pin every figure the provenance records state
  - Write the measurement the coverage threshold's provenance record names: from
    the shipped model, compute the relative understatement of daily-average
    fitness and of daily-average fatigue caused by exactly one uncomputed daily
    page at the seed time constants, and assert both figures equal the ones the
    record states, to the record's own precision
  - Measure the recursion-form choice's per-step divergence the same way -- the
    reciprocal weight against one minus the exponential, at both seed time
    constants -- and assert both figures equal the ones that record states, so
    no number in the sources module is stated without being reproduced
  - Assert the shipped threshold value admits at most one uncomputed page in
    five, which is the sentence the record makes, so the record and the number
    cannot drift apart
  - **This task may make one edit outside its own test module**: where a measured
    figure disagrees with the figure 2.1 transcribed, it corrects that string in
    the sources module, and it reports having done so. It changes no constant's
    *value* and no other prose there; a disagreement large enough to move the
    threshold itself is a stop-and-report, not a silent edit
  - Named mutations: change the shipped threshold without changing the record's
    stated bound (the consistency assertion reds); change a stated figure in
    either record (the corresponding measurement reds)
  - Observable: `uv run pytest tests/history/test_coverage_threshold_measurement.py`
    green; every numeric figure quoted in the sources module's provenance strings
    is reproduced by an assertion in that module
  - _Depends: 2.2_
  - _Requirements: 3.4_
  - _Boundary: ModelSources_

- [x] 3. Core: reading the archive and assembling the series

- [x] 3.1 (P) Read every workout document into typed page records through the one contract reader
  - The `(P)` here means concurrent with **group 1**, not with 2.1: the package
    directory and its published-surface list are created by 2.1, so this task
    cannot precede it (`_Depends: 2.1_` below). Its file set --
    `history/documents.py` and its own test module -- is disjoint from group 1's
    layout, declaration and documentation files
  - Add the package's one filesystem-reading module: it scans the generated
    documents directory's top-level markdown files in sorted order, exactly as
    the load pass and the audit do, and reads nothing else -- no source archive,
    no history directory, no `.fit` file
  - For each file, resolve the frontmatter through the shared document read;
    skip a file the read declines; skip a file that is not a workout document;
    skip, with a named reason, a document whose date cannot be read; take the
    load value and the methodology from the load keys, treating a missing,
    non-numeric, non-finite or boolean load value as no load at all and leaving
    the methodology unset whenever the load is unset; and resolve the effort tag
    through the contract's one reader, recording a malformed tag's own
    description as a problem on that page while still keeping the page's load
  - Emit two sorted tuples of frozen records -- the pages, ordered by date then
    path, and the skipped files, ordered by path -- with every path expressed
    relative to the data root in forward-slash form so no report or page ever
    leaks an absolute path or a machine-specific one
  - This module is the package's only importer of the shared document read and
    the document contract, imports no YAML parser, spells no frontmatter fence,
    no workout type literal and no effort key, defines no private duplicate of a
    contract reader, and never raises for a bad document
  - Fixtures are synthetically written page trees: a scored page, an unscored
    page, a page whose load value is a string, a page whose load value is
    boolean, a page with no date, a non-workout markdown file, a nested
    subdirectory that must not be descended into, a symlink, a valid race tag, a
    valid test tag with a time, a hard tag, a malformed tag, and two pages on one
    date
  - Named mutations: accept a boolean as a load value (the boolean fixture
    scores); treat a malformed tag as untagged (the malformed fixture silently
    gains a marker); sort by path only (the two same-day pages swap)
  - Observable: `uv run pytest tests/history/test_documents.py` green; scanning
    the fixture tree returns records whose load is unset exactly for the pages
    that record none
  - _Depends: 2.1_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.9, 3.9, 5.4_
  - _Boundary: DocumentScan_

- [x] 3.2 Resolve the methodology and partition the archive by it
  - Add the pure selection function: an explicitly requested methodology beats a
    configured one, which beats a single methodology observed across the
    archive. More than one observed with nothing requested or configured, and a
    requested or configured identifier that no page records, each yield a
    problem value naming every methodology found with its page count and the
    action that resolves it -- never a guess and never a silent majority
  - Partition the pages: a page recording the chosen methodology, and a page
    recording no load at all, are included; any page recording a different
    methodology is excluded and counted by methodology, sorted, so the counts
    render identically every run
  - Report which of the three sources produced the choice, so the page can say
    that a methodology was inferred rather than configured
  - Fixtures: one methodology only; two methodologies with one configured; two
    with one requested; two with neither; a requested identifier absent from the
    archive; an archive of unscored pages only
  - Named mutations: fall back to the most common methodology instead of
    returning a problem (the two-with-neither fixture stops failing); exclude
    unscored pages from the included partition (the coverage denominator drops
    and the coverage fixtures in 3.4 red)
  - Observable: `uv run pytest tests/history/test_series.py -k methodology`
    green; the ambiguous fixture returns a problem naming both identifiers with
    their counts
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Boundary: SeriesAssembly_

- [x] 3.3 Build the contiguous daily series with its known / unknown split
  - Add the day record -- the date, the load actually recorded, how many pages
    that date has, and how many of them record a load -- with derived unknown
    and complete views, so no consumer can ever hold the recorded sum without
    the counts that qualify it
  - Build the series from the first to the last contributing page date
    inclusive, where contributing means the page records a load under the chosen
    methodology, with one day record per calendar date and none omitted; count
    included pages that fall outside that span separately rather than dropping
    them; return nothing at all when no page records a load
  - A date with no pages is a genuine rest day: zero recorded, zero pages,
    complete. A date whose pages all lack a load is unknown: zero recorded, its
    pages counted, none of them known. The two must be distinguishable by value,
    not by convention
  - Fixtures: two pages on one date; a rest day inside the span; a fully unknown
    day; a partially known day; a page dated before the first contributing page;
    an archive where nothing records a load; a single-day archive
  - Named mutations: start the span at the first included page rather than the
    first contributing one (the leading-unknown fixture reds); collapse the page
    counts into the recorded sum (the rest-day and unknown-day fixtures become
    indistinguishable)
  - Observable: `uv run pytest tests/history/test_series.py -k series` green;
    the fixture's rest day and its fully unknown day compare unequal
  - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.8_
  - _Boundary: SeriesAssembly_

- [x] 3.4 Aggregate weeks and coverage, and apply the suppression rule
  - Add the coverage measure -- pages recording a load over pages -- defined as
    complete when a period has no pages at all, because nothing is missing from
    an empty period; report it per calendar year and once for the whole archive
  - Attribute the excluded counts per period as well as archive-wide: an excluded
    page is a page record and therefore has a date, so the aggregation takes the
    excluded records themselves rather than only the archive-wide totals the
    methodology choice carries
  - Do **not** attribute the skipped count to a period. A skipped document has no
    date to attribute by -- the commonest skip reason is that its date is
    precisely what could not be read -- so the skipped figure is an integer on
    the archive-wide row and unset on every period row, and the page prints
    nothing there rather than a zero that would read as "none were skipped"
  - Add the weekly aggregation over ISO weeks from the week containing the span's
    start to the week containing its end, each row carrying its year and week
    number, its Monday, how many of its days lie inside the span, its total
    recorded load, its session count, its page and known-page counts, and the
    three model values at the week's end
  - Apply the suppression rule: a week whose coverage is strictly below the
    threshold is suppressed; its row carries no model values and is flagged, and
    its days carry no value into the chart series. The recursion is not
    restarted and is not re-run -- suppression is applied to the values it
    already produced
  - Fixtures: an empty week; a week exactly at the threshold (not suppressed)
    and one just below (suppressed); a partial first week and a partial last
    week; an ISO week spanning a year boundary; two calendar years each holding
    excluded pages of a different methodology, asserting the per-year split; an
    archive with one skipped undated document, asserting the archive-wide row
    counts it and every period row leaves it unset
  - Named mutations: define an empty period's coverage as zero (a rest week is
    suppressed and the whole page changes); use less-than-or-equal for
    suppression (the at-threshold fixture reds); key weeks by calendar year
    instead of ISO year (the year-boundary fixture reds); attribute the skipped
    count to every period (the undated-skip fixture reds); take the archive-wide
    excluded totals instead of the excluded records (the two-year fixture reds
    because both years report the same total)
  - Observable: `uv run pytest tests/history/test_series.py -k "weeks or coverage"`
    green; the at-threshold week reports values and the just-below week reports
    suppression
  - _Depends: 2.2, 3.3_
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.10, 5.6_
  - _Boundary: SeriesAssembly_

- [x] 3.5 Count the archive's criterion points
  - Add the criterion-point count: pages carrying a valid effort tag whose kind
    is a race or a test and which record an official time. Break the count down
    by kind, sorted by the kind vocabulary's own order, and report the earliest
    and latest counted dates, or nothing at all when the count is zero
  - Group every other tagged page as an exclusion with a stated reason: a hard
    effort, of which no official result is required; a race or test recording no
    time; and a malformed tag, each of those named individually with its path
    and the reader's own description of what is wrong
  - Attach no judgement of any kind -- no sufficiency verdict, no confidence
    claim, no recommendation
  - Fixtures: a race with a time; a race with a time and a distance; a test with
    a time; a race with no time; a hard tag; a malformed tag; an untagged page;
    an archive with no tags at all
  - Named mutations: count hard efforts (both the count and the exclusion table
    red); count a race with no time (the same); sort the kind breakdown by count
    instead of by vocabulary order (the two-kind fixture reds)
  - Observable: `uv run pytest tests/history/test_series.py -k criterion` green;
    the fixture archive reports its count, its per-kind split and its three
    exclusion groups
  - _Requirements: 6.1, 6.2, 6.3_
  - _Boundary: SeriesAssembly_

- [ ] 4. Rendering: the chart and the page

- [x] 4.1 (P) Add the calendar-axis, absolutely-scaled multi-series chart
  - Add a new chart module beside the existing ones, built on the shared SVG
    primitives and the shared gap-splitting helper. The hero chart is neither
    imported, extended nor changed
  - One shared value scale across every series, computed from the values
    actually present and padded to include zero, with a zero line always drawn
    because form is routinely negative. No series is normalised against another
  - A calendar horizontal axis: one tick per January the first inside the span
    plus the span's own endpoints, labelled with the year and formatted without
    any locale-dependent call, so the bytes are identical on every machine
  - A missing value breaks the polyline rather than being interpolated across;
    a suppressed span additionally receives a low-opacity backdrop band and one
    legend entry, so a break reads as suppressed rather than as no data
  - Markers are numbered glyphs on the axis carrying their number as their only
    text, which is what keeps thirty of them legible; the labels live in the
    markdown beside the chart
  - Add the three series colours to the shared palette module, which is the one
    home for colour in the render layer, rather than declaring them locally.
    That module is not a bag of hex strings: its series table maps each name to a
    hex value **and** the oklch source it was converted from, and an existing test
    reconverts every entry's source through the module's own pipeline and asserts
    equality within one unit per channel. So each new colour is chosen as an oklch
    value first, converted through that pipeline, and registered with its source
    -- a hand-picked hex with an absent or invented source reds a test this task
    does not otherwise touch
  - Pins: a golden SVG for a small synthetic span; two series of different
    magnitudes keep their ratio (the anti-normalisation assertion); a run of
    missing values produces two path elements rather than one; the value range
    includes zero; two calls produce identical bytes; no locale-dependent
    formatting call appears in the module
  - Named mutations: normalise each series independently (the ratio assertion
    reds); join across a missing run (the two-path assertion reds); drop the
    zero line (the golden reds); format the axis labels with a month name (the
    locale assertion reds)
  - Observable: `uv run pytest tests/render/charts/test_calendar.py tests/render/charts/test_palette.py`
    green -- the palette test unchanged and covering the three new entries; the
    golden SVG renders in a browser with three distinguishable curves, a zero
    line and numbered markers
  - _Requirements: 3.8, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: CalendarChart_

- [x] 4.2 Declare the document's vocabulary and emit its frontmatter
  - Declare the document's own vocabulary in this module and nowhere else: its
    type value, its title, its format version and version key, and the ordered
    tuple of frontmatter keys. Import the shared vocabulary -- the frontmatter
    fence, the type and generator key names, the generator name, the generated
    banner -- from the document contract rather than re-spelling any of it, and
    assert the type value differs from the workout type. Append these names to
    the package's published-surface list, appending only and rewriting nothing
    already there
  - Emit the frontmatter as ordered plain lines rather than through a YAML
    library: every value is machine-generated and drawn from a closed set, and
    the one free value -- the methodology identifier -- is emitted bare when it
    is a plain token and double-quoted with escaping otherwise, while a control
    character or newline in an identifier is a hard failure rather than a
    silently broken block. The package's YAML emitter is neither imported nor
    touched
  - Every number is formatted by an explicit rule so no platform's default
    representation can leak into the bytes; a value that is genuinely unknown is
    omitted rather than emitted as zero
  - Pins: the exact key order; a round trip asserting the document contract's own
    parser reads back every key with the expected type, including the
    criterion-point count as an integer; the quoting rule over a plain
    identifier, a dotted identifier, one with a space and one with a quote; a
    control character in an identifier raises
  - Named mutations: reorder the keys (the order pin reds); emit the methodology
    bare regardless (the quoted-identifier fixture reds because the block no
    longer parses); emit an unknown value as zero (the round-trip type assertion
    reds)
  - Observable: `uv run pytest tests/history/test_page.py -k frontmatter` green;
    the emitted block parses through the contract's parser and its type value is
    not the workout type. The names this task appends to the package's surface
    are pinned at 5.4, not here -- the surface pin does not exist yet
  - _Requirements: 5.8, 6.4_
  - _Boundary: HistoryPage_

- [ ] 4.3 Render the document's body sections and pin them as goldens
  - Assemble the sections in a fixed order after the frontmatter block: the
    generated banner, the title, the chart with its numbered race list, the
    constants-and-scale paragraph, the coverage statement, the
    criterion-performance section, the weekly table, and the
    skipped-and-excluded list
  - The constants paragraph names the four values, says whether they are seeds,
    the athlete's own or fitted, prints the origin line verbatim, names the
    daily-average scale, and states in plain words that the shipped values were
    never fitted to anybody. The caveat paragraph states, every time, that the
    accumulators start at zero so the first weeks understate, and that values
    following a suppressed period understate by whatever load is missing
  - The coverage statement gives, per calendar year, the pages, the pages
    recording a load and the excluded counts by methodology, and gives the
    skipped count on the archive-wide line only -- period rows print nothing
    there, because a document whose date could not be read belongs to no period
  - The criterion-performance section carries the count, the per-kind split, the
    earliest and latest dates, the exclusion groups with their reasons, each
    malformed tag named with its path and the reader's own description, and the
    sentence that fitdocs draws no conclusion from the count
  - A race with no recorded result is listed with its date and no fabricated
    result; a suppressed week's three model values are shown as a dash with the
    suppression named, never as zero
  - Every number in the body is formatted by the same kind of explicit rule the
    frontmatter uses -- loads and model values to one decimal, coverage as a
    percentage to one decimal -- so no platform's default representation of a
    float can reach the bytes. A golden alone would not catch this: it pins
    whatever the implementer's machine produced
  - The page contains no forecast, no zone, no readiness verdict, no
    recommendation and no plan, cycle or block content
  - Pins: a golden markdown document and a golden SVG for a synthetic archive
    exercising a suppressed week, a rest week, a marked race with a result and
    one without, one excluded methodology, one skipped undated document and one
    malformed tag; a forbidden-phrase assertion over the rendered page; a copy
    assertion for the never-fitted sentence and for both caveat sentences
  - Named mutations: omit the exclusion list from the criterion section (the
    golden reds); drop the never-fitted sentence (the copy assertion reds);
    render a suppressed week's fitness as zero rather than as a dash (the golden
    reds); print a zero skipped count on a period row (the golden reds); format a
    model value with the language's default string conversion instead of the
    explicit rule (the golden reds wherever that conversion differs, which is
    exactly what pinning the rule is for)
  - Observable: `uv run pytest tests/history/test_page.py` green; the golden page
    reads end to end as a document an athlete could act on, with every count in
    it traceable to the fixture archive
  - _Depends: 3.4, 3.5, 4.1, 4.2_
  - _Requirements: 2.2, 2.5, 2.7, 2.11, 3.5, 3.7, 3.10, 5.4, 5.5, 5.6, 5.7, 5.9, 5.10, 6.1, 6.2, 6.3, 6.5_
  - _Boundary: HistoryPage_

- [ ] 5. Integration: settings, the pass, the command, the guards, and validation

- [x] 5.1 Read the history settings table and resolve the model constants
  - Add a fourth peer settings reader beside the ones for tiles, inbox, plugins
    and load: it receives the already-parsed settings mapping and validates only
    its own table, never opening a file. Nothing is added to the load table's
    reader, whose default-calculator field is read and nothing more
  - Every field defaults to unset, so an absent settings file or an absent table
    yields the defaults rather than an error, and unknown keys and unknown
    sub-tables are ignored, because the file is shared
  - Validate: each time constant a finite number greater than zero; each
    weighting a finite number not less than zero; the coverage threshold a
    finite number between zero and one inclusive; the methodology a non-empty
    string. Booleans are rejected wherever a number is expected. A fault raises
    an error type that subclasses the shared settings error, so the command's
    existing handler maps it to a configuration exit with no new branch
  - Resolve the constant set: with nothing configured, the result is the seed
    instance itself; with any of the four configured, the provenance is
    "configured" and the origin line names each configured key and each key left
    at its seed, so a partially configured set is never labelled as seeds
  - Named mutations: accept a boolean as a time constant; drop the range check on
    the threshold; label a partially configured set as seeds (the origin
    assertion reds)
  - Observable: `uv run pytest tests/history/test_settings.py` green; a data root
    with no settings file resolves to the seed constant set by identity
  - _Requirements: 2.7, 3.4, 8.3, 8.4_
  - _Boundary: HistorySettings_

- [ ] 5.2 Orchestrate the pass and write its two outputs
  - Add the package's one writing module: read the settings document once and
    project it through both table readers; scan the documents; resolve the
    methodology, raising a settings-error subclass on a problem so the command's
    existing handler maps it to a configuration exit; build the series; run the
    model; aggregate weeks, coverage and criterion points; render; write
  - Refresh the ownership declarations before writing, through the existing
    placement function. Be explicit about what that means, because the next task
    asserts the run's negative half: that function iterates **every** declared
    directory, so a history run may create or rewrite the generated-documents and
    source-archive declarations, and may create those two directories, on a data
    root that has never been synced. All of that is inside the owned set and is
    not a violation. What the pass must never do is write or alter a workout
    document, an asset, or an archived source
  - Write the chart first and the document second, the document by the same
    atomic temp-file-then-replace idiom the load pass uses, so a crash never
    leaves a half-written page
  - Before writing either output, read any file already at that path: a file
    that does not carry the generated marker is left untouched, recorded in the
    report, and does not fail the run
  - Take no date parameter and call no clock. Write no workout document, no
    workout asset and no archived source, and neither the athlete profile nor the
    settings file -- the narrowed form, because the declaration refresh above
    legitimately writes the two other in-tree declarations
  - Return a report carrying the two written paths or nothing, the pages read,
    contributing, without a load, excluded by methodology, and outside the span,
    every skipped file with its reason, the suppressed week count, the
    criterion-point count, the methodology, every foreign path left alone, every
    failure, and a note for the empty-archive case
  - When no page records a load: write nothing, leave any existing page
    untouched, set the note, and report no failure
  - Pins: two runs over an unchanged tree write byte-identical files and produce
    equal reports; the empty archive writes nothing; a foreign file at either
    output path survives unchanged and is reported; an unwritable output
    directory yields a failure entry and leaves no partial file
  - Named mutations: write the document before the chart (the torn-state
    assertion reds); overwrite a foreign file (that assertion reds); pass a
    system date into the page (the clock scan in 5.4 reds)
  - Observable: `uv run pytest tests/history/test_engine.py` green; running the
    pass twice over a fixture data root produces identical bytes
  - The declared dependencies reach the recursion and the three aggregations only
    through 4.3, which consumes them. That is correct as long as 4.3 stays after
    group 3; reordering it ahead of group 3 would break this task silently
  - _Depends: 3.1, 3.2, 4.3, 5.1_
  - _Requirements: 1.9, 1.10, 4.2, 7.4, 7.5, 7.6, 8.1, 8.5, 8.6_
  - _Boundary: HistoryEngine_

- [ ] 5.3 Add the history command and its run report
  - Add one command named distinctly from the sibling spec's derivation command,
    with the shared data-root option and one option naming a methodology. It has
    no force and no recompute option: the page is always rebuilt in full
  - Reuse the module's existing helpers and exit constants for resolving the
    data root, reporting a configuration error, and finishing; a settings error
    -- including the history table's error and the methodology problem -- maps to
    the configuration exit through the existing handler shape with no new branch
  - Print the report: both written paths, pages read, contributing and without a
    load, each excluded methodology with its count, the out-of-span count, the
    suppressed week count, the criterion-point count, each foreign path, and each
    skipped file with its reason
  - Change nothing about the sync, regeneration or load commands, and add an
    assertion that no other command's implementation reaches the history pass
  - Pins: the success path; the ambiguous-methodology path (configuration exit,
    nothing written, both identifiers and counts in the message); the
    malformed-settings path; the empty-archive path (success exit with the note
    printed); the write-failure path (failure exit)
  - Named mutations: map the methodology problem to the failure exit rather than
    the configuration exit; call the history pass from the load command (the
    absence assertion reds)
  - Observable: `uv run pytest tests/test_cli_history.py tests/test_cli.py` green;
    `uv run fitdocs history --out <fixture root>` writes both files and prints
    the criterion-point count
  - _Requirements: 4.4, 4.5, 8.1, 8.2, 8.4, 8.6, 8.7, 8.8_
  - _Boundary: HistoryCommand_

- [ ] 5.4 Register the pass in the confinement guard and pin the package's surface and boundary
  - Register the history pass as a writing entry point in the confinement guard,
    with a fixture producing a small synthetic data root. The guard's permitted
    set already reads the owned paths directly, so nothing is hardcoded and the
    shared-files set is not extended, because this pass writes no shared file
  - Add the negative half explicitly, and state it precisely rather than broadly:
    the run creates, modifies or deletes no workout document, no file under the
    workout assets directory and no archived source, and writes neither the
    athlete profile nor the settings file. The two other in-tree ownership
    declarations are deliberately **excluded** from that claim -- the declaration
    refresh may legitimately create or rewrite them (see 5.2) -- and a blanket
    "touches nothing under the generated documents directory" assertion would be
    a false claim of exactly the kind the ownership work exists to prevent
  - Add the package boundary test: parse every module under the package and check
    its imports against the design's allowed list, failing by name on the ingest
    layer, the load engine, the threshold calculator, the channels package, the
    profile module, the render views, the hero chart and any YAML parser; assert
    no module names a clock function in code or in a docstring, giving that scan
    an explicit path list that also includes `src/fitdocs/render/charts/calendar.py`
    -- belt and braces, because that file is created by this spec but sits
    outside every `src/fitdocs/history/`-scoped guard by design: it holds only
    layout constants and a pure renderer and is otherwise covered by the render
    layer's existing guards; assert the reference-directory string appears
    nowhere in the package
  - Add the **reverse** half of the boundary: a reachability scan asserting that
    no module under `src/fitdocs/load/`, and neither `src/fitdocs/render/views.py`
    nor `src/fitdocs/sync.py` nor any module under `src/fitdocs/ingest/`, imports
    `fitdocs.history` -- in either import form, including an aliased
    whole-module import -- the shape `tests/performance/test_reachability.py`
    (performance-benchmarks) uses. Named mutation: add `import fitdocs.history`
    to `load/engine.py` and the scan must red
  - Pin the package's published surface name for name, asserting each name is the
    same object as its defining module's, and register the reading module in the
    contract-consumer guard binding exactly the load keys, the date reader, the
    effort-tag reader and the workout-document test by identity, so the guard's
    existing structural assertions apply to it unchanged. The binding list holds
    `fitdocs.contract` names **only** -- the guard resolves each through
    `getattr(fitdocs.contract, name)` -- so the shared read is deliberately
    **not** listed: the module obtains frontmatter through
    `docio.read_frontmatter`, a `fitdocs.docio` name, and `fitdocs.docio` is
    already a registered consumer in its own right (`fitdocs.audit` is the
    precedent: it binds contract names only)
  - Named mutations: import the hero chart from the calendar module (the boundary
    test reds); call a clock in the engine (the clock scan reds); add a name to
    the package's surface without the pin (the surface pin reds); bind a local
    copy of a contract reader (the identity assertion reds)
  - Observable: `uv run pytest tests/test_confinement.py tests/history/test_boundary.py tests/test_public_api.py tests/test_contract_consumers.py`
    green; the confinement guard runs the history entry point among the others
  - _Depends: 5.2_
  - _Requirements: 1.1, 2.4, 7.4, 7.5, 8.5_
  - _Boundary: ConfinementRegistration, PackageBoundary, SurfacePins_

- [x] 5.5 Land the wiki-contract Existing Spec Update
  - Amend the wiki-contract spec's requirements with an amendment block on the
    published-ownership-contract and in-tree-declaration requirements recording
    the new owned location, its declaration and the second document type the
    data root now contains; renumber no existing criterion
  - Add an amendment note to that spec's document-contract design block stating
    that a second document type exists, that it is declared in the history
    package rather than in the contract leaf, and the reason; add the amendments
    entry to its spec metadata
  - This is the second half of the roadmap's Phase 6 update for that spec; the
    user-owned-keys half was landed by the effort-tags spec, and neither half
    edits the other's text
  - Observable: `/kiro-spec-status wiki-contract` reports the spec clean with its
    amendments entry listing this change, and that spec's requirements, design
    and metadata all name the history location, its declaration and the second
    document type
  - _Requirements: 7.2, 7.3_
  - _Boundary: WikiContractSpecUpdate_

- [ ] 5.6 End-to-end and feature-level validation
  - Add the end-to-end test over a synthetic data root: run the command, assert
    both files exist at the owned paths, assert the report's counts, and assert
    the page's frontmatter carries the criterion-point count
  - Assert byte-identical output across two runs, and across two runs executed
    under two different fake system dates -- the behavioural half of the clock
    scan
  - Run the whole suite plus the lint, format and strict type checks, and confirm
    the goldens, the ownership conformance test, the declaration goldens, the
    confinement guard and the public-surface pin are all green together
  - Observable: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
    and `uv run mypy` all green; the two dated runs produce identical bytes
  - _Depends: 5.3, 5.4_
  - _Requirements: 1.10, 7.6, 8.5, 8.6_

## Implementation Notes

- **5.2 must gate the empty archive before methodology selection (controller
  decision, 2026-09-11).** `select_methodology` returns a `MethodologyProblem`
  for an archive where no page records a load (nothing observed), including
  when an id is configured or requested -- the design's own "chosen id observed
  nowhere" rule. The design's engine order (select first, then build the
  series) would turn that into a configuration exit, contradicting Req 1.10 and
  this plan's "the empty archive writes nothing, reports no failure" pin.
  `HistoryEngine` therefore checks "every `PageRecord.load is None`" BEFORE
  calling `select_methodology`, and on that path writes nothing at all -- no
  outputs and no declaration refresh; the refresh happens only on a run that
  reaches its write step (the published contract states it this way).
- **2.3's divergence figures are stated at tau = 45, 42 and 15 d.** tasks.md
  2.1/2.3 read the design's 1.20%/1.12% pair as "both seeds"; the design and
  research.md label it tau = 42 (blocked PMC candidate) vs 45. Both readings
  now hold: `RECURSION_FORM_CHOICE.measurement` carries all three, pinned.
- **Consumer-guard registration (5.4):** `documents.py` binds `LOAD_KEYS`,
  `document_date`, `effort_tag`, `is_workout_document` by from-import (the
  guard resolves `getattr(module, name) is getattr(contract, name)`);
  `page.py` also imports `fitdocs.contract` (the shared vocabulary), so 5.4
  registers BOTH modules, not only `documents.py` as the design's "only
  importer" sentence says.
- **Exemption table (`tests/history/test_constant_guard.py`):** keyed by AST
  site `(module, enclosing assignment target, keyword/positional slot, value)`
  and matched one-to-one by count -- a prose-only edit never reds it; a second
  copy of an exempted number does. Later tasks append entries and, when no
  existing category is honest, a category member.
- **Reviewers revert with `cp` from a snapshot, never `git checkout`** (one
  wiped an implementer's uncommitted file), and namespace scratch files by
  task (parallel agents share one scratchpad and clobbered each other).
- **For 4.3 / 5.2 (from 3.4/3.5 review):** `WeekRow.sessions` has no
  definition in the design and is implemented as `pages_with_load`; 4.3
  decides how the weekly table shows it. `CriterionPoints.by_kind` omits
  zero-count kinds -- 4.3 derives 0 for an unobserved kind when the template
  prints "a race, b test". `criterion_points` takes the FULL scan
  (`scan.pages`), not the partition, so every tagged page excluded from the
  count can be stated with a reason (Req 6.3); the design's blanket "pages is
  the included partition" precondition at design.md:1092 is wrong for it.
  `DayLoad`/`DailySeries`/`build_daily_series` are module-level in
  `history.series`, not on the package surface; 5.2 appends whatever the
  engine or page import off the surface before 5.4 pins it.
