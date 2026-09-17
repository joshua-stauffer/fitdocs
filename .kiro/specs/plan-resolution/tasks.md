# Implementation Plan

## Upstream Prerequisites

- **`training-blocks` must be implemented first.** This plan consumes its
  parsed block, its resolution seam, its `blocks/` location with the `plan`
  entry point, its pass's resolver hook, and its package boundary test, all
  exactly as `.kiro/specs/training-blocks/design.md` states them under
  "Cross-spec obligations (training-blocks ↔ plan-resolution)". A task that
  finds a seam shaped differently from that section stops and reports; it
  never redefines, renames or widens one.
- **`wiki-contract`** owns the document contract leaf. This plan adds key
  constants, readers and one value type to it (the way `document_date` was
  added for `athlete-benchmarks`) and does not move `CONTRACT_VERSION`,
  `MANAGED_KEYS`' value, `USER_KEYS`, `PRESERVED_REGIONS` or `DOC_VERSION`.
- **`load-history`** owns the one-methodology rule. Its two published
  helpers are widened to a structural record type; nothing else under
  `src/fitdocs/history/` changes, and its unpublished scan is never
  imported.
- **`training-load`** owns the load keys and the pass this one runs after;
  load values are read and summed, never computed or altered.
- **`workout-docs`** owns `render/frontmatter.py`; this plan changes only
  the spelling of five keys there, to the contract's constants, and no
  output byte.

**Hard rules for every task**

- No task writes into the plan-source directory or into a workout document,
  in code or in a test's assertion about code. A test that needs either
  writes it as fixture setup before the run and hashes it afterwards.
- No module under `src/fitdocs/plans/` names a clock function -- in code or
  in a docstring; the wave-1 clock scan reads docstrings too. The parameter
  is called `today` and is a date value the command resolved.
- No module under `src/fitdocs/plans/` imports `fitdocs.ingest`,
  `fitdocs.render`, `fitdocs.sync`, `fitdocs.audit`, `yaml`, any
  `fitdocs.history.<submodule>`, or any `fitdocs.load.<submodule>` other
  than `fitdocs.load.settings` from the pass module alone; the history
  package root is imported only by the pass module, the aggregator and the
  placement module (the last for the two methodology types alone, because
  the per-block reconciliation record is defined there -- design.md,
  Placement).
- Only `plans/page.py`, `plans/engine.py` and `plans/corpus.py` import
  `fitdocs.contract`.
- The vocabulary words live in the placement module and nowhere else; the
  report prints the placement's own sentences.
- A task that finds it needs a new dependency, a change to a wave-1 seam's
  shape, a new owned path, or a contract-version advance, stops and reports.

## Shared source files

- **`src/fitdocs/contract.py`** -- task 1.1 only. `CONTRACT_VERSION` is
  asserted to read `"4"` before any edit and is not changed; another value
  means a peer moved it -- stop and report.
- **`src/fitdocs/render/frontmatter.py`**, **`src/fitdocs/plans/page.py`**
  -- task 1.1 only (five key spellings; four key spellings plus the
  `INDOOR_WORD` display constant). The wave-1 renderers (`block_page.py`,
  `planned_page.py`) are edited by **no** task.
- **`src/fitdocs/history/series.py`**, **`src/fitdocs/history/__init__.py`**
  -- task 1.2 only. **`src/fitdocs/layout.py`** -- task 1.3 only.
- **`src/fitdocs/cli.py`** -- task 3.2 only. **`src/fitdocs/declaration.py`**
  -- task 3.4 only. **`pyproject.toml`** -- task 3.3 only.
  **`.kiro/steering/roadmap.md`** -- task 3.4 only, one checkbox (the Phase
  7 `workout-docs` Existing Spec Update).
- **Three files are append-only, one append per module task, in the same
  change as the module** -- because two wave-1 pins go red the moment a
  module or a published name exists that they do not list, and a task may
  not merge red: `src/fitdocs/plans/__init__.py` (the published list),
  `tests/plans/test_boundary.py` (its hand-maintained module list is
  checked against the package directory both ways, and each module's import
  targets are pinned by equality) and `tests/test_public_api.py`
  (`_PLANS_SURFACE` pins the published list exactly, with an owners map).
  Tasks 2.1, 2.2, 2.3, 2.4 and 3.1 each append their own module's entry and
  names to all three; 2.2 and 2.3 are parallel and both append -- the
  controller merges the two appends, and a wholesale rewrite by either is a
  defect. One expected exception to "append": 2.3 introduces the exemption
  map, which also changes the body of the wave-1 forbidden-target check to
  consult it -- a hunk inside that function beside the list appends, not a
  rewrite; 2.2's entry needs no exemption and touches no check body; 2.4
  and 3.1 each append their own exemption entry to the map 2.3 introduced.
  Task 3.3 adds only what no single module owns (the exemption map's
  positive control, the threshold-closure assertion, the final
  whole-surface identity check, the mypy list).
- **`tests/test_contract_consumers.py`** -- 1.1 (the five literals; the
  frontmatter and page binding extensions) then 2.1 (the corpus module's
  registration), both appends.
- **`tests/test_public_api.py`** -- 1.1 (`_CONTRACT_SURFACE`), 1.2
  (`_HISTORY_SURFACE` and owners), then the per-module `_PLANS_SURFACE`
  appends above; each edits only its own pin.
- **Wave-1 files this plan edits by exception, each in one task**:
  `tests/test_cli_plan.py` and `tests/test_plan_e2e.py` (3.2, the two
  re-anchored pins training-blocks design § Cross-spec obligations item 5
  names), `.kiro/specs/training-blocks/{requirements.md,spec.json}` (3.4,
  a record of that re-anchoring -- an appended paragraph and one
  amendments entry; no criterion reworded). This list and training-blocks
  tasks.md "Cross-spec shared files" agree file for file and task for
  task.

## Test File Ownership

- `tests/test_contract.py` (reader section; the named-constant test) → 1.1.
- `tests/history/test_series.py` (run; one by-identity assertion added) → 1.2.
- `tests/test_layout.py` (the form pin's two new clauses; the round trips) → 1.3.
- `tests/plans/test_corpus.py` → 2.1. `tests/plans/test_matching.py` → 2.2.
  `tests/plans/test_aggregate.py` → 2.3. `tests/plans/test_placement.py`,
  `tests/plans/golden/reconciled-*.md`, `tests/plans/fixtures/reconcile/*.toml`
  → 2.4 alone: 2.2 and 2.3 are parallel and build their sources as inline
  text through the wave-1 parser (`parse_block(text, block_id=...)`),
  creating no fixture file. `tests/plans/test_reconcile.py` → 3.1.
- `tests/plans/test_boundary.py` and `tests/test_public_api.py`
  (`_PLANS_SURFACE`) -- per-module appends by 2.1, 2.2, 2.3, 2.4, 3.1;
  the residual by 3.3 (see Shared source files).
- `tests/test_cli_reconcile.py` (new), `tests/test_cli_plan.py` (the AST pin
  only), `tests/test_plan_e2e.py` (the two-dates test only) → 3.2.
- `tests/test_confinement.py`, `pyproject.toml` → 3.3.
- `tests/test_declaration_goldens.py` (run as the generator),
  `tests/declaration_golden/blocks.AGENTS.md` (regenerated, never
  hand-edited), `tests/test_ownership_contract.py` and
  `tests/test_docs_guarantees.py` (run) → 3.4.
- `tests/test_reconcile_e2e.py` (new) → 3.5.
- Synthetic workout pages: every test module that needs one carries its own
  `_page(...)` helper in the shape of `tests/history/test_engine.py:43-64`,
  extended with `sport`, `modality`, `indoor` and `start_time` lines; no
  task creates a `tests/plans/conftest.py` (2.2 and 2.3 are parallel and
  would both need it).

**Every new assertion names its mutation** (change-protocol § Fixture
Discrimination): each task's bullets name the production mutation that must
redden the assertion; the implementer runs it through `uv run pytest`,
observes red, reverts, observes green, and says so. The six mutations the
brief names -- the split-session absorb, the competing-row ambiguity, the
override precedence, the cross-day non-match, the methodology exclusion and
the coverage count -- are 2.2's and 2.3's and are listed by name there.

**No personal data**: every fixture is a synthetic plan source and a synthetic
page tree under `tests/plans/` or `tmp_path`; no `.fit` file is read by any
task.

- [ ] 1. Foundation: the contract readers, the history record protocol, the logged-page links

- [x] 1.1 Give the contract one reader per matched field and make its key spellings the only ones
  - Assert the contract version literal reads `"4"` (wave 1 advanced it);
    any other value means a peer moved it -- stop and report
  - Add five key constants beside the existing session-identity and
    source-history constants -- the date, start-time, sport, modality and
    indoor keys -- and route the managed-key set's five members and the
    existing date reader through them, so the managed set's value is
    unchanged and the existing managed-key tests pass unedited (this
    absorbs queue item `2026-07-26-date-key-has-no-constant`; say so in the
    report so the controller can close it)
  - Add a frozen load-reading value (a finite value and a non-empty
    methodology) and five readers that degrade and never raise: sport and
    modality return the recorded non-empty string verbatim (the contract
    may not import the activity model, so the enum mapping is the
    caller's); indoor returns a genuine boolean or absent; start time
    returns an aware datetime from the emitted ISO string or from an
    unquoted hand-edited value and absent for anything naive, a bare date
    or malformed text; load returns the reading under exactly the rule the
    history package's private reader applies today -- a boolean, a
    non-finite or overflowing value, or a value without a methodology is
    absent. Append the eleven names to the module's published list
  - Route the workout frontmatter builder's five key writes through the
    constants (the anti-drift test resolves a bare name through the
    module's namespace by design) and, in the plans page module, route the
    planned page's four key spellings through the same constants as
    from-imports **and rebind the module's display constant** -- the
    wave-1 page module emits the sport phrase's word `indoor` from one
    module-level constant, `INDOOR_WORD` (training-blocks design § Cross-spec
    obligations item 6 / PageVocabulary), and that word is the fifth
    registered-module occurrence of a now-forbidden value: make it
    `INDOOR_WORD: Final[str] = INDOOR_KEY` with a comment that the display
    word and the frontmatter key are deliberately the same spelling, so the
    module carries no bare `"indoor"` constant (the guard walks every
    string constant of a registered module, key or not). If a wave-1
    renderer under the plans package turns out to spell one of them too,
    **report it as a queue item and do not edit it**: the renderers are
    outside this plan's boundary and the literal guard does not reach
    unregistered modules by design. No rendered byte changes: the workout
    goldens, the wave-1 planned golden and the page module's sport-phrase
    pins stay green unedited
  - Extend the converted-consumer guard: the five key values join the
    forbidden-literal tuple (by constant, never re-spelled); the frontmatter
    builder's binding list gains the five constants and the plans page
    module's gains the four it uses
  - Pins: each reader over absent, wrong type, boolean, empty string, the
    emitted form and the unquoted hand-edited form; start time over an
    aware string, an aware datetime, a naive string, a naive datetime, a
    bare date and `"tomorrow"`; load over `True`, infinity, `10**400`, a
    value without a methodology and a methodology without a value, plus a
    parity table asserting the reading is absent exactly when the history
    package's private reader returns its absent pair; the named-constant
    membership test gains the five; the contract surface pin gains the
    eleven names; the consumer guard green over every registered module,
    the plans page module included with its display word rebound
  - Named mutations: accept a naive start time (its pin reds); read indoor
    as truthy (`"yes"` pin reds); return a reading with no methodology (the
    parity pin reds); spell the sport key inline in the frontmatter builder
    (the literal guard reds); reintroduce the bare `"indoor"` literal for
    the page module's `INDOOR_WORD` (the literal guard's plans-page case
    reds -- the display-word occurrence, not a key); drop one constant from
    the managed set (the published-schema pin reds)
  - Observable: `uv run pytest tests/test_contract.py tests/test_contract_consumers.py tests/test_public_api.py tests/plans tests/test_sync_e2e.py`
    green, with `tests/plans/test_page.py`'s sport-phrase pins unedited and
    the consumer guard's literal scan green over `fitdocs.plans.page` (the
    scan compares whole string constants, so a comment or docstring that
    merely contains the word is not an occurrence -- only a constant equal
    to it is); a Python shell reads sport, modality, indoor, start time and
    load from a real generated document's frontmatter through the five
    readers
  - _Requirements: 1.2, 1.5_
  - _Boundary: ContractReaders, ConsumerGuard_

- [x] 1.2 (P) Let the history package's methodology helpers take any record that carries a methodology
  - Add a structural record protocol with one read-only property, the
    methodology or absent, to the series module; widen the selection
    function's and its private counting helper's page parameter to it, and
    make the partition function generic so a caller receives its own record
    type back. Bodies unchanged; the existing page record satisfies the
    protocol without edits
  - Append the protocol's name to the history package's published list and
    to the public-surface pin with its owner; the series module already
    imports `typing`, so the history boundary test's import-target pin does
    not move, and no numeric literal is added
  - Pins: the existing series tests green unedited; the surface pin and
    owner map gain the one name; an assertion in the series tests that the
    partition returns the caller's own instances by identity (the typed
    cross-check over the reconciler's record lives in 2.3)
  - Named mutations: make the partition return copies of each record via
    `dataclasses.replace` (the by-identity pin reds -- a runtime mutation;
    an annotation change alters nothing at runtime and cannot red it);
    revert the partition's parameter annotation to the page record (`uv run
    mypy` reds on the aggregator's typed call once 2.3 exists -- verified
    there, not here)
  - Observable: `uv run pytest tests/history tests/test_public_api.py`
    green and `uv run mypy` green
  - _Requirements: 6.2_
  - _Boundary: HistoryRecordProtocol_

- [x] 1.3 (P) Add the two logged-page link helpers to the layout leaf
  - Add the link to a logged workout page from a block page's directory
    (one level up, into the workouts directory) and from a planned page's
    directory (two levels up), both as plain string joins on the workouts
    directory constant, so separators stay forward slashes everywhere; list
    them in the module docstring
  - Pins: both round trips (the block page's parent joined with the link
    normalises to the workout document's path; the planned page's parent
    likewise); the form pin gains a clause per helper pinning the sanctioned
    spelling tokens (`f"../{WORKOUTS_DIR}/` and `f"../../{WORKOUTS_DIR}/`),
    with no `Path(`, `PurePath(` or `os.` in either
  - Named mutations: drop one parent step from the planned link (its round
    trip reds); rewrite the block link through a pure-POSIX path object (the
    form pin reds; the value would be identical)
  - Observable: `uv run pytest tests/test_layout.py` green; a Python shell
    returns `../workouts/x.md` and `../../workouts/x.md`
  - _Requirements: 7.5_
  - _Boundary: LoggedLinks_

- [ ] 2. Core: the corpus, the match rules, the sums, the words

- [x] 2.1 Scan the logged-workout corpus through the contract
  - Add the corpus module: a frozen logged-workout record (stem, data-root-
    relative path, day, sport, modality, indoor, aware start time, load,
    methodology -- the last two absent together) with one ordering key
    (undated last, then by instant, a missing start time last, then by
    stem); a frozen corpus with lookup by stem, the workouts on a day, and
    the dated workouts inside an inclusive window; and the scan, which walks
    the workouts directory's top level sorted, reads through the shared read
    helper, keeps exactly the recognized workout documents, reads the seven
    fields through the contract's readers and nothing else, maps sport and
    modality onto the activity model's enumerations by value (an unknown
    spelling is absent), and never raises for a bad page. An absent
    workouts directory is an empty corpus
  - Register the module in the converted-consumer guard with its seven
    contract bindings (the six readers and the workout-document test)
  - The three appends this module owes (Shared source files): its three
    names to the plans package's published list; its entry to the wave-1
    boundary test's module list with its import targets pinned by equality,
    widening that test's contract-importer pin from two modules to three;
    its three names with their owner to the plans surface pin
  - Pins (typed): a page of every shape -- full, undated, unknown sport,
    `indoor: true`, no start time, naive start time, unscored, scored under
    two methodologies -- and the exclusions -- a planned-workout page, a
    symlink to a valid page, a non-UTF-8 file, a page in a subdirectory;
    ordering for two same-day pages whose stems sort opposite to their start
    times; the window at both edges; a page whose load region carries a
    quality-flag line is still present; the consumer guard, the boundary
    test and the surface pin green with the module registered
  - Named mutations: read the sport inline (the literal guard reds); sort by
    stem only (the opposite-order pin reds); include undated pages in the
    window (its pin reds); follow the symlink (its pin reds -- the target is
    a valid page, so the exclusion is the only thing that can fail it)
  - Observable: `uv run pytest tests/plans tests/test_contract_consumers.py tests/test_public_api.py`
    green and `uv run mypy --strict tests/plans/test_corpus.py` green
  - _Depends: 1.1_
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7_
  - _Boundary: CorpusScan_

- [x] 2.2 Resolve every planned row: the states, the rules, the labels, the overrides
  - Add the matching module, pure: the five row states and the three
    confidence labels as enumerations whose values are the page words; the
    row outcome (state, stems, label, missing stems, override index and
    date, reason, competitors, same-day listing); the problem record with
    its one-line description; the match result (one outcome per current
    row in block order, the claimed stem set, the problems)
  - Effective overrides: per row the entry with the greatest date, then
    file position; its stems leave every other row's candidates before
    matching; a stem the corpus lacks is recorded on the row and reported
    as a problem naming the override entry (`override[i] (id r)`) and the
    stem, and the row is still overridden by the stems that exist; a stem
    named by two effective overrides is kept on both and reported once as a
    conflict naming both entries; a skipped override yields the skipped
    state with its date and reason
  - Candidates: same day, equal sport, equal modality when the row states
    one, indoor agreeing when the row states it (an unrecorded flag agrees
    only with `false`), nothing else consulted; undated and unknown-sport
    pages never qualify; a page on another day never qualifies
  - Competition groups per day among rows without an override: rows whose
    candidate sets intersect, transitively. One row: one candidate is
    exact, several are absorbed with all of them. Several rows: each row in
    block order takes the first unassigned candidate in its set by the
    ordering key; a row that takes one is matched ambiguous naming the
    other rows; a row that takes none is not logged or upcoming naming
    them; unassigned candidates stay unclaimed
  - The split: a row with nothing and no override is not logged when dated
    before today, else upcoming; today is used for nothing else. A not
    logged or upcoming row lists every logged workout of its day with the id
    of the row that claimed it, if any. Matched stems are in ordering-key
    order; overridden stems in the override's own order
  - The three appends this module owes: its names to the plans package's
    published list; its boundary entry; its names with owner to the plans
    surface pin (parallel with 2.3's appends to the same three files; the
    controller merges)
  - Pins (typed; one headed section per rule; blocks built as inline
    source text through the wave-1 parser, no fixture file): base case
    exact and a same-day other-sport page listed; **split session** (one
    row, three same-type pages, stems named opposite to start order →
    absorbed with all three in start order); **competing rows** (two rows,
    two pages → both ambiguous, first row takes the earlier page,
    competitors cross-referenced; two rows, one page → first ambiguous,
    second not logged naming the competitor; a third row of another type
    stays out of the group); partial overlap (a generic workout row and a
    strength row against one strength and one bike page → one group, both
    ambiguous); **cross-day** (the page dated one day after and one day
    before → not logged); type rules (strength row vs other-modality page;
    run row vs walk page; indoor true vs absent flag, vs `indoor: true`;
    indoor false vs absent flag); **override precedence** (an override
    replaces an exact match; the later of two wins, equal dates → later in
    the file; a claimed stem leaves another row's candidates so that row is
    not logged; a missing stem → recorded and one problem; two overrides on
    one stem → one conflict problem, both rows keep it; skipped with
    reason); the split at today minus one, today, today plus one; undated
    and unknown-sport pages never candidates; every invariant of the
    outcome (label iff matched; stems iff matched or overridden; one
    matched row per stem; claimed equals the union)
  - Named mutations (each reds exactly its pin): `<=` for the split (today
    pin); a one-day tolerance on the date (cross-day pins); collapse a
    multi-candidate row to exact with the first (absorbed pin); pair by stem
    order (ambiguous first-row pin); take the first override (precedence
    pin); keep override stems in other rows' candidates (leaves-candidates
    pin); drop the missing-stem problem (its pin); treat an absent indoor
    flag as true (its pin); ignore modality (strength/other pin)
  - Observable: `uv run pytest tests/plans tests/test_public_api.py` green
    and `uv run mypy --strict tests/plans/test_matching.py` green; a Python
    shell over the competing-rows source prints two ambiguous outcomes that
    name each other
  - _Depends: 2.1_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4_
  - _Boundary: Matcher_

- [x] 2.3 (P) Sum the actual load per mesocycle, state its coverage, and list the unplanned workouts
  - Add the aggregation module, pure: per mesocycle the dated workouts in
    its window (any sport, unknown ones included), partitioned through the
    history package's published partition function under the chosen
    methodology into scored, unscored and excluded; the total over the
    scored ones or absent when none is scored -- never zero; the lower-bound
    flag when any considered workout is unscored; the considered count
    (scored plus unscored, never the excluded); the integer percent of the
    target when both exist; the unplanned workouts -- those in the window
    whose stem no row of the block claims -- in ordering-key order. With no
    methodology chosen, every partition is empty and the total absent
  - The history package's selection and partition functions are the only
    methodology logic; nothing is re-implemented. Loads are read and summed,
    never computed
  - The three appends this module owes: its names to the plans package's
    published list; its boundary entry, **introducing the exemption map**
    with its first entry, the aggregator → the history package root (2.4
    and 3.1 append theirs; every history submodule stays forbidden from
    every module); its names with owner to the plans surface pin (parallel
    with 2.2's appends to the same three files; the controller merges)
  - `(P)` with 2.2 after 2.1: the two share only the corpus and the model,
    build their sources inline, and each appends its own entries
  - Pins (typed; sources as inline text through the wave-1 parser): three
    scored pages with pairwise-distinct loads sum exactly; a fourth unscored
    → lower bound, considered four, total unchanged; **methodology
    exclusion** (a page under another methodology → excluded, not
    considered, not summed, and the history helper returns the reconciler's
    own record instances -- the typed cross-check for 1.2); **coverage
    count** (`3 of 5` with two unscored; the excluded page not in the five);
    only unscored pages → total absent; an empty window; a page on the
    window's last day (in) and the day after (out); a stem the matcher
    claimed absent from unplanned, an override-claimed stem likewise, an
    unclaimed one present; no choice → partitions empty, total absent; the
    percent for 1180 of 1200 is 98 and absent without a target; an
    unmatched page still counts toward the sum; the boundary test green
    with the exemption in place
  - Named mutations: sum over every page in the window (the exclusion pin
    reds); count considered from the scored alone (the coverage pin reds);
    total zero when nothing is scored (the not-computed pin reds); a strict
    comparison at the window's last day (the edge pin reds); include
    claimed stems in unplanned (its pin reds); revert 1.2's annotation to
    the page record (`uv run mypy` reds here -- 1.2's deferred mutation)
  - Observable: `uv run pytest tests/plans tests/test_public_api.py` green
    and `uv run mypy --strict tests/plans/test_aggregate.py` green
  - _Depends: 2.1, 1.2_
  - _Requirements: 1.3, 1.4, 3.6, 4.2, 6.1, 6.2, 6.3, 6.4, 6.7, 6.8_
  - _Boundary: Aggregator_

- [x] 2.4 Place the words: the vocabulary, the per-block record and the resolution value
  - Add the placement module, pure: **the per-block reconciliation record**
    (block id, the row outcomes, the mesocycle loads, the run's methodology
    choice or problem, the problems) with its derived per-state counts,
    ambiguous row ids in block order and unplanned count -- defined here,
    not in the pass module, because this module reads it and the pass
    module sits above it in the import order (a type defined upstairs would
    force this module to import it, a cycle the boundary test reds; design
    Placement states the choice); its methodology field is typed by the
    history package's two published methodology types, which this module
    imports from the history root and nothing else of history; the
    vocabulary constants (the state and
    label words come from the matching enumerations; the not-computed,
    at-least, no-target, not-found and unscored words and the three line
    prefixes live here and nowhere else; the sport phrase's `indoor` word is
    the page module's constant, not a second spelling); the actual-load
    sentence over a mesocycle load, in exactly the grammar design.md
    tabulates, reused verbatim by the report; the row cell (one line, no
    pipe, links from the block page's depth; **the overridden cell is the
    `overridden: ` prefix plus one comma-join over the existing stems'
    links first and the missing stems' `` `stem` (not found) `` items
    after, so a row whose every named stem is missing reads exactly
    `` overridden: `stem` (not found) `` with no leading comma**); the row
    section (the label's rule in a sentence,
    one bullet per fulfilling logged page with its sport phrase, wall-clock
    time when recorded and load phrase, the override date and reason, the
    competitor sentence, the same-day listing, links from the planned
    page's depth); the mesocycle lines (the actual-load line before the
    table; the unplanned and excluded listings after it); the block-level
    lines (the per-state count line -- **the total, then, when there is at
    least one row, ` -- ` and only the states with a count of at least one
    in the fixed order matched, overridden, skipped, not logged, upcoming,
    the ambiguous parenthesis only when at least one row is ambiguous;
    zero-count states are omitted, so an all-upcoming block reads
    `Planned workouts: 3 -- 3 upcoming.` and a block with no rows
    `Planned workouts: 0.`** -- the methodology and how it was chosen or
    why none was, the ambiguous rows, the problems); and the resolution
    builder that fills the wave-1 seam for every current row and every
    mesocycle. Link text passes through the page module's link-text helper;
    numbers through its load format; times as hour and minute of the
    recorded local wall clock; never the pass's today
  - The three appends this module owes: its names (the record, the
    resolution builder, the actual-load sentence) to the plans package's
    published list; its boundary entry, **with its own exemption-map
    entry** admitting exactly this module → the history package root (the
    map 2.3 introduced); its names with owner to the plans surface pin
  - Pins (`tests/plans/test_placement.py` with goldens rendered through
    the wave-1 renderers): one block golden and two planned goldens from a
    synthetic block and corpus exercising every grammar row -- exact,
    absorbed three, an ambiguous pair, overridden with one missing stem,
    skipped with a reason, not logged with a same-day ride taken by another
    row, upcoming; one complete mesocycle with a target, one lower bound
    with an exclusion, one not computed, one with unplanned; a second block
    golden under a methodology problem; a placement test asserting each
    fragment lands in its slot and nowhere else; the wave-1 structural check
    passes over the built value; no cell holds a newline or a pipe; no
    section line is a fence line; **the no-today postcondition over the
    built resolution value** -- no cell, section line, before-table line,
    after-table line or block line contains the fixture today's ISO form --
    with today placed inside the block so that the wave-1 day table prints
    it on the page and only the value can be clean (a page-level assertion
    would be unsatisfiable), and with no override entry and no unplanned or
    excluded logged workout dated today, because the grammar legitimately
    prints those dates (the fixture states both constraints beside the
    assertion); the actual-load sentence for each case by
    exact string; a stem containing `]` escaped in the link text; two calls
    byte-equal; **the row cell for an overridden outcome with no existing
    stem and one missing stem is exactly `` overridden: `stem` (not found) ``**
    (by exact string, beside the golden's one-link-one-missing row);
    **the count line over a record whose every row is upcoming is exactly
    `Planned workouts: 3 -- 3 upcoming.`** and over a block with no rows
    exactly `Planned workouts: 0.`; the record's counts sum to the row
    count, its ambiguous ids name the pair in block order, its unplanned
    count sums the mesocycles; the boundary test green with this module's
    exemption entry in place
  - Named mutations: render an absent total as `0` (the golden reds); drop
    the at-least word (the lower-bound pin reds); count considered over
    every page in the aggregation module -- a cross-module mutation of
    2.3's coverage rule, seen from the wording side (the exclusion sentence
    reds); use the block-depth link on the planned page (the planned golden
    reds); append today's ISO form to the upcoming section line (the
    value-level no-today pin reds); write the matched word for an
    overridden row (the golden reds); prefix every not-found item with `, `
    regardless of how many links precede it (the zero-link overridden-cell
    pin reds on a leading comma); print zero-count states on the count line
    (the all-upcoming pin reds)
  - Observable: `uv run pytest tests/plans tests/test_public_api.py` green;
    the block golden reads end to end as a training record an athlete could
    review; a Python shell over an override naming only a missing stem
    prints `` overridden: `stem` (not found) ``
  - _Depends: 2.2, 2.3, 1.3_
  - _Requirements: 3.7, 4.3, 4.5, 5.3, 6.3, 6.4, 6.5, 6.6, 6.7, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_
  - _Boundary: Placement_

- [ ] 3. Integration: the pass, the CLI, the guards, the documents, and validation

- [x] 3.1 Run the reconciling pass through the plan pass's resolver hook
  - Add the pass module: the report (the plan report, the reconciliations
    in plan order, the methodology or none, and the failed flag -- the
    plan's failure or any problem); the pure per-block function composing
    the matcher and the aggregator into **the per-block reconciliation
    record 2.4 defined in the placement module** (imported from there,
    never redefined here -- the pass module sits above the placement in the
    import order, so the type lives below); the resolver object that scans the
    corpus and selects the methodology on its first call only, records each
    block's reconciliation, and returns the placed resolution; and the run
    function that reads the settings document once, projects the history
    and load tables (their errors propagate before anything else happens),
    composes the configured methodology the way the history engine does,
    and calls the wave-1 pass with the resolver. A methodology problem is
    carried, never raised. No clock, no write, no prompt; the second read
    of the settings file is the wave-1 pass's own and is stated in the
    docstring without naming a clock
  - The three appends this module owes (the last ones; 3.3 checks the
    whole): its names (the report, the per-block function, the run
    function -- the record is 2.4's) to the plans package's published list;
    its boundary entry with **its exemption-map entry** admitting exactly
    the history package root and the load settings module; its names with
    owner to the plans surface pin
  - Pins (typed, synthetic roots under `tmp_path`): the rendered block page
    carries the placed match text; a page added between runs flips a row
    from not logged to matched and the block from unchanged to rendered,
    removing it flips back; an override naming a missing stem makes the
    report failed while the block is still rendered; a configured
    methodology no page records → every mesocycle not computed, the report
    carries the problem, failed is false, every row still resolved; a
    malformed history table raises before the pass and writes nothing (the
    source directory and the rendered directory hashed before and after);
    no plan directory → the read helper is never called (a counting stub);
    two blocks, one invalid → one reconciliation; a row dated today renders
    upcoming; two runs with equal inputs → byte-identical pages and every
    block unchanged; the boundary test green with the exemption in place
  - Named mutations: scan the corpus eagerly (the count-zero pin reds);
    raise on a methodology problem (the not-computed pin reds); compute
    failed from the plan alone (the missing-stem pin reds); hand the matcher
    today plus one (the today pin reds)
  - Observable: `uv run pytest tests/plans tests/test_public_api.py` green
    and `uv run mypy --strict tests/plans/test_reconcile.py` green; running
    the function twice over a fixture root produces identical bytes and the
    second report says unchanged for every block
  - _Depends: 2.4_
  - _Requirements: 2.6, 4.3, 4.6, 5.1, 5.2, 5.4, 6.2, 6.6, 8.4, 8.6, 8.9_
  - _Boundary: ReconcilePass_

- [x] 3.2 Chain the pass after sync, drain and regen, and pass the resolver from the plan command
  - Add a today helper beside the local-timezone helper that returns the
    local calendar date **through `date.today()`** -- deliberately not
    through `datetime.now(...)`: the fake-date context manager the
    end-to-end tests reuse (`tests/test_history_e2e.py:211-245`) hooks the
    Python-level `time.time` and honours `TZ`, which `date.today()` reads
    and `datetime.now()` does not (verified on the interpreter during
    design); this is the only clock read this feature makes, and no guard
    forbids a clock in the CLI module
  - Add a pass helper in the load-pass helper's shape, taking today and a
    `chained` flag: the run function inside the shared settings-error
    handler mapping to the configuration exit; the wave-1 plan report
    printed in full when standalone, and **suppressed only when chained and
    the plan report has no block, no unsourced path and no foreign
    declaration** -- so the standalone plan command still prints the
    absent-directory note wave 1 pins; then the reconciliation printer: per
    block one summary line with the per-state counts (under the block
    page's count-line rule: zero-count states omitted, the ambiguous
    parenthesis only when there is one, no list for a block with no rows)
    and the unplanned count, one indented actual-load line per mesocycle reusing the
    placement's sentence, the ambiguous ids, one indented description per
    problem; then once the methodology chosen and how, or why none. Detail
    lines without markup or highlighting
  - Insert the pass helper, chained, after the load pass at the
    explicit-source sync branch, the inbox-drain branch and the
    regeneration command, folding its failed flag into each finishing call;
    make the plan command call the same helper unchained and finish on its
    flag. Leave the load, history and check commands untouched. Update the
    module docstring's command bullets and exit-code paragraph and the two
    command docstrings
  - Re-anchor the two wave-1 pins this change moves, in the same change --
    the two training-blocks design § Cross-spec obligations item 5 names,
    and the only two of that spec's tests this plan edits; its criteria
    8.4 and 8.8 already admit the resolver and the chaining, so no criterion
    is touched: the plan command's AST pin now asserts the wave-1 engine
    function is named nowhere in the module, the run function is imported
    once and loaded by name once inside the pass helper, and the pass
    helper is loaded exactly four times -- inside the sync command twice,
    the regeneration command and the plan command -- and nowhere else; the
    wave-1 two-dates end-to-end test gains, as a precondition assertion,
    that the local date under each of its (timestamp, time zone) pairs
    lies on the same side of every fixture row -- computed per pair,
    because a time zone change alone can cross midnight; training-blocks
    task 4.6 already chose such dates, so this is an added assertion, not
    a change of dates (this plan's own e2e pins the crossing case)
  - Pins (`tests/test_cli_reconcile.py`, CliRunner): sync with a source,
    the drain path and regen over a root with a plan and a matching
    generated page each leave the block page carrying the match text and
    print the reconciled line; sync over a root with no plan directory
    prints output byte-identical to the same run with the pass helper
    monkeypatched to a stub that prints nothing and returns a report whose
    failed flag is false (the call site folds the flag into the finishing
    call); the plan command over the default absent directory still prints
    the note (wave 1's pin, green unedited); a missing override stem
    through sync exits with the per-file-failure status and prints the
    problem line; a malformed history table exits with the configuration
    status; the load and history commands over a root with a plan leave
    the rendered directory's bytes and mtimes unchanged -- with two stated
    preconditions: the fixture ran the plan command first, so the rendered
    directory's declaration file exists and is current (the history
    engine's own declaration refresh would otherwise create it), and a
    matching workout page was added to the workouts directory after that
    run, so the pass, if it ran, would have something to rewrite (otherwise
    its byte comparison writes nothing and the named mutation below reds
    only the AST pin); the plan command
    exits success and the block page carries the match text; the
    re-anchored AST pin
  - Named mutations: call the pass helper from the load command (the AST
    pin and the untouched pin red); ignore the chained flag and always
    suppress the empty report (the standalone-note pin reds); always print
    the plan report (the quiet pin reds); drop the failed flag from one
    finishing call (that command's exit pin reds); resolve today inside the
    run function (the wave-1 clock scan reds); define the today helper
    through `datetime.now(...)` (3.5's crossing-row e2e reds, because the
    fake never moves it)
  - Observable: `uv run pytest tests/test_cli_reconcile.py tests/test_cli_plan.py tests/test_cli.py tests/test_plan_e2e.py`
    green; `uv run fitdocs sync <fixture source> --out <root>` prints a
    `reconciled` line for the fixture block (the methodology line and the
    plugin-error block follow it)
  - _Depends: 3.1_
  - _Requirements: 4.3, 5.5, 8.1, 8.2, 8.3, 8.5, 8.6, 8.7_
  - _Boundary: CliChaining, TrainingBlocksSpecUpdate_

- [x] 3.3 (P) Register the pass in the confinement guard and close the package's boundary and surface pins
  - Register a second writing entry point for the reconciling pass with a
    fixture that stages one valid source with one running row on a date and
    one synthetic generated workout page on that date with a load, a run
    that -- taking the guard's two-argument signature and ignoring the
    staged-source argument -- calls the run function with a today a week
    later, and a non-vacuity predicate stronger than the plan entry's: the
    block page and the planned page both written. Add a sibling behavioural
    test reading the block page after the guarded run and asserting the
    match text is present
  - State the negative half precisely, in the plan entry's own phrasing:
    the source's and the workout page's bytes unchanged; nothing created,
    modified or deleted under the plan directory; no workout document under
    the workouts directory created, modified or deleted -- the declaration
    file there excluded, because the measured run refreshes every declared
    directory's declaration; no history page; neither the athlete profile
    nor the settings file
  - Close the wave-1 boundary test after the per-module appends: a positive
    control that a synthetic import of the history documents module from any
    plans module is caught despite the exemption map; a one-line assertion
    that the plans package is absent from the threshold calculator package's
    transitive import closure (its own boundary test is preserved-only and
    named as such); the per-module allowed-target entries confirmed equal to
    the measured imports of all five modules
  - Close the plans surface pin: the final list confirmed name for name with
    owners and the identity assertion, and nothing re-exported from the
    package root; add the four typed test modules to the mypy files list
  - `(P)` with 3.2 after 3.1: no shared file (3.2 owns the CLI and its two
    re-anchored wave-1 tests; this task owns the confinement guard, the
    boundary residual and the mypy list)
  - Named mutations: use the plan entry's predicate (the predicate's own
    pin over a synthetic touched sequence reds: the block page alone is
    false, the block page with the planned page is true, and the plan
    entry's predicate answers true to both -- a run whose resolver returns
    the unresolved default would not discriminate, because wave 1 writes a
    planned page for every row regardless of the resolver);
    write a marker file under the workouts directory from the pass (the
    guard reds); import the history documents module from the corpus module
    (the positive control's real twin reds); name a clock in a pass-module
    docstring (the clock scan reds); publish a name without an owner (the
    owners pin reds)
  - Observable: `uv run pytest tests/test_confinement.py tests/plans/test_boundary.py tests/test_public_api.py`
    green and `uv run mypy` green with the four modules listed
  - _Depends: 3.1_
  - _Requirements: 4.6, 5.1, 5.5, 6.8, 7.6, 8.4, 8.8_
  - _Boundary: ConfinementRegistration, PackageBoundary, SurfacePins_

- [ ] 3.4 (P) Say who else writes into the rendered location: the declaration, the ownership contract, the README, the upstream record and the roadmap tick
  - Extend the rendered directory's declaration fragment with one clause:
    the pages are also rewritten at the end of the sync and regeneration
    commands, when the same pass reconciles the plan against the logged
    workout pages -- written around the quantifier guard (no `each`, `every`,
    `all documents`, `any document`, and no word containing `each` or
    `every`); extend its claim-anchor comment with the CLI pass helper.
    Regenerate the declaration goldens with the module's own generator and
    assert the three other goldens are byte-identical (the version did not
    move)
  - In the published ownership contract, add to the two-further-types
    section that the resolution cells and sections are filled by the
    reconciling pass from the logged workout pages' frontmatter, that it
    writes nothing into a workout page or the plan source, and that a match
    is re-derived on every run; extend the plan bullet of the overwrite-
    semantics section with the chained runs. The version line does not
    move. In the README, extend the plan paragraph with the five states,
    the ambiguous label, the override entry and the chaining
  - Record, in the training-blocks spec, the two test pins 3.2 re-anchored
    -- **rewording no criterion**: that spec's 8.4 and 8.8 are already
    scoped to admit this plan's resolver and chaining, and its design §
    Cross-spec obligations item 5 names both pins. Add one amendments entry
    to that spec's metadata (`spec.json`: date; requirement `8.4 / 8.8
    (record only); tests of tasks 4.3 and 4.6`; reason: the 4.3 AST pin and
    the 4.6 two-dates test now read as plan-resolution states them, no
    criterion changes meaning) and append one paragraph to its
    `requirements.md`, `## Amendment 1 (2026-09-16): the two test pins
    re-anchored, landed by plan-resolution`, in the shape wiki-contract's
    amendments use, saying exactly that. Renumber nothing; edit no
    criterion's text
  - Tick the roadmap's `workout-docs` checkbox under Phase 7 `#### Existing
    Spec Updates` (`.kiro/steering/roadmap.md`) as `[x]` with "no change: no
    back-link key is written (plan-resolution design § Decisions recorded
    for the roadmap)", the way training-blocks' 4.5 ticks the
    `wiki-contract` one and build-training-block's 3.3 ticks
    `distribution`; that checkbox is the only edit this plan makes to the
    roadmap
  - `(P)` with 3.3 after 3.2: no shared file
  - Pins: the goldens test green with the blocks golden regenerated and the
    other three unchanged; the quantifier guard green over the new text;
    the ownership conformance test and the documentation anchor-link check
    green unedited; `git diff .kiro/specs/training-blocks/requirements.md`
    shows only the appended paragraph (no line of Requirement 8 changed)
  - Named mutations: write "each planned workout" into the clause (the
    quantifier guard reds); change the clause without regenerating (the
    goldens test reds)
  - Observable: `uv run pytest tests/test_declaration.py tests/test_declaration_goldens.py tests/test_ownership_contract.py tests/test_docs_guarantees.py`
    green; `/kiro-spec-status training-blocks` clean with the amendments
    entry present; the roadmap's `workout-docs` entry under Phase 7 reads
    `[x]`
  - _Depends: 3.2_
  - _Requirements: 5.2, 8.1, 8.2, 8.8_
  - _Boundary: OwnershipDocs, TrainingBlocksSpecUpdate_

- [ ] 3.5 End-to-end and feature-level validation
  - Add the end-to-end test over a synthetic root with two plan sources and
    a synthetic corpus: sync from a fixture source, then assert the block
    pages carry the placed text, every planned page carries its section,
    every link resolves to an existing workout page path, and the report
    lines appear after the plan pass's own
  - Assert byte-identical pages across two runs; across two fake system
    dates whose local dates lie on the same side of every row (importing
    the history e2e test's fake-date context manager, not copying it); and,
    under a fake date whose local date crosses exactly one row, that
    exactly that row's table cell on the block page, that row's section on
    its planned page, and the block page's per-state count line change,
    and every other line of both pages is byte-identical (the count line
    necessarily moves with the row, so "nothing else changes" would be
    unsatisfiable) -- the assertion that proves the today helper reads the
    clock the fake reaches
  - Assert a page added to the corpus between runs changes exactly the row
    it matches and the mesocycle sum that includes it; assert a missing
    override stem through sync exits with the per-file-failure status while
    the block is rendered; assert the load and history commands leave the
    rendered directory untouched; assert the source directory and every
    workout page are byte-identical before and after every scenario
  - Named mutations: append today's ISO form to the block-level lines (the
    same-side byte-identity pin reds); swap the order of the plan report and
    the reconciliation report in the pass helper (the "after the plan
    pass's own" order pin reds); use the block-depth link on the planned
    page (the every-link-resolves pin reds); drop the failed flag from the
    sync command's finishing call (the missing-stem exit pin reds); define
    the today helper through `datetime.now(...)` (the crossing-row pin reds)
  - Run the whole suite plus the lint, format and strict type checks, and
    confirm the wave-1 goldens, the workout goldens, the declaration
    goldens, the ownership conformance test, the confinement guard, the
    consumer guard and the three surface pins are all green together
  - Observable: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
    and `uv run mypy` all green; the crossing-row run changes one row
  - _Depends: 3.2, 3.3, 3.4_
  - _Requirements: 4.3, 4.6, 5.2, 5.3, 5.4, 8.1, 8.3, 8.6, 8.7_

## Implementation Notes

- **1.1** `tests/plans/test_boundary.py::TestContractImporters::test_each_contract_importer_binds_exactly_its_registered_names` pins each contract importer's from-import *names* by set equality (`_CONTRACT_FROM_IMPORT_NAMES`), not only its import targets as design § Cross-spec obligations item 6 says. Any task that widens a plans module's `from fitdocs.contract import ...` line must widen that module's entry in the same change (1.1 did so for `page.py`: +DATE_KEY, INDOOR_KEY, MODALITY_KEY, SPORT_KEY). 2.1's corpus entry is a new key there, per Shared source files.
- **1.1** `document_load` mirrors `history/documents.py::_read_load` line for line, and that reader accepts an empty-string methodology today; the parity table pins that shape (`{"load_value": 150, "load_methodology": ""}`). Design's "non-empty methodology" comment on `LoadReading` is therefore not enforced by the reader — queued as a spec decision, not changed here. 2.3 sums through the history package's own partition, so it inherits the same rule.
- **1.1** The sport/modality readers return the recorded string verbatim; the emitted spellings are `Sport` values (`"Run"`, `"Ride"`, ...) and `Modality` values (`"run"`, `"bike"`, ...). Pin verbatim rules with values a normalisation changes (`" Trail Run "`), never with lowercase values a case-fold maps to themselves — a `.lower().strip()` reader survived the first fixture.
- **2.1** Three review rounds, all fixture-side. Round 2's sweep found what incremental review had not: ORDER of `within`/`on_day` results (set-equality fixtures cannot see a reversal — assert list equality with stems opposite to days), the stem tiebreak (only pinnable by constructing records directly, since `sorted(glob)` + stable sort masks it), and `indoor` absent-vs-`False` (both directions need their own pin). When a task's fixtures are all filesystem-built, add at least one direct-construction test per ordering rule. The `FORBIDDEN_LITERALS` guard holds only the five matched-field keys, not `LOAD_KEYS` — an inline `"load_methodology"` read is not structurally caught (queued).
- **2.3** The boundary test's forbidden-target scan resolves `from fitdocs.history import X` to the target `fitdocs.history.X`, which the exact-pair exemption map (`_FORBIDDEN_EXEMPTIONS`, introduced here) does NOT admit. Decision: 2.4 and 3.1 import the exempt roots whole-module (`import fitdocs.history`, `import fitdocs.load.settings`) and append one exact entry each; design's from-import sketches are read as signatures, not import forms. The map's positive control belongs to 3.3 and must also cover a non-exempt module's `import fitdocs.history` (a module-agnostic `_is_exempt` survives otherwise). Four review rounds here: every survivor was a fixture that could not see a rule the design names — per-mesocycle window EDGES (put a page on each mesocycle's first AND last day, assert both results), the no-choice `considered`, and `order_key`'s start-time component (a fixture without start times pins only day-then-stem). `total` now raises `ValueError` on a hand-built scored page without a load rather than fabricating `0.0`.
- **2.2** Five review rounds, every one fixture-side; production `matching.py` was byte-identical from round 1. What the incremental rounds kept finding in a 20-criterion matcher: a corpus declared already in start-time order (deleting the `order_key` sort survives); row ids that sort like block order (source-order pairing indistinguishable from `sorted(group)`); a chain fixture that catches one broken union-find but not the other three link directions (declare the linking row first AND last); enum VALUES pinned nowhere (identity checks pin names only — assert `[s.value for s in RowState]`); one missing stem per override (per-stem loops truncated to `[:1]` survive). The conflict-entry format `"override[i] (id a) and override[j] (id b)"` is 2.2's own choice (design gives none); 2.4/3.1 consume it as-is. Published surface is exactly the six design names; `effective_overrides`/`is_candidate` stay module-level.
- **2.4** Three rounds. A golden pins only the grammar rows its fixture reaches: the two planned goldens covered ambiguous + overridden, leaving exact/absorbed/upcoming/competitor sentences, the bullet's wall-clock time, `logged_phrase`'s branches and the conditional block lines (`Ambiguous:`/`Problems:`/`(k ambiguous)`) unpinned until exact-tuple unit tests over hand-built records were added — walk the design's grammar table row by row and name the test that pins each row, including each conditional's FALSE branch. A same-valued literal (`"indoor"` for `page.INDOOR_WORD`) cannot red at runtime; the AST constant scan in `TestIndoorWordIsNotRespelled` is the pin. A bare `"workout"` literal trips the wave-1 region-id scan — the singular/plural clause is inlined as two f-strings. `Unplanned:` prints `matches` for one workout (design's table shows only the plural; queued). Placement imports `fitdocs.history` whole-module per the 2.3 note. 3.1 imports `BlockReconciliation` and `place_resolution` from here.
- **3.1** `tests/load/test_settings.py::test_load_load_settings_is_called_from_exactly_the_licensed_modules` (training-load Req 14.1) pins the exact caller set of `load_load_settings`; `plans/reconcile.py` is the fourth pass (design § Allowed Dependencies licenses it; the guard's own docstring names widening as the sanctioned resolution, precedent queue item 2026-09-11-performance-pass-sufficiency-read-vs-single-reader-guard). The controller widened it in this task (four callers; every "three"/"fourth" count in its docstring moved) — the plan's Shared source files list omitted the guard; queued. Three rounds here, all fixture-side: the once-per-run scan needs a TWO-valid-block fixture with the counting stub at `== 1`; settings threading needs a page scored under a real methodology so `configured=None` would yield a choice; precedence needs both tables set and both methodologies recorded; `MethodologyChoice.source == "configured"` pins the `requested=`/`configured=` order (the page prints it); `failed`'s `plan.failed` half needs a problem-free block beside a broken source.
- **3.3** Approved in one round — the guard task whose tests were designed from the mutations up. The design's "four typed test modules" is five (`test_placement.py` is 2.4's, added after the design was written); all five are in `[tool.mypy].files`. The threshold-closure walk seeds from the production `fitdocs.load.threshold` directory, never from the sibling test module (pulling a test module into mypy's follow-imports scope surfaced five pre-existing errors outside the boundary). The exemption map's controls: a submodule import from an exempt module is caught; a whole-module `import fitdocs.history` from a NON-exempt module is caught; the same from an exempt module is accepted. The reconcile entry's negative-half `no_workout_write` filter is deliberately NOT `.md`-narrowed (the named marker mutation is a dotfile); the history clause still is (queued).
- **3.2** BLOCKED in round 1 on a spec gap, resolved by controller ruling (recorded here; design amendment queued): design § Cross-spec obligations / TrainingBlocksSpecUpdate claim only two wave-1 tests move, but once the resolver is chained (Req 8.2) FOUR more wave-1 tests exit 1 under Req 8.7, because `tests/plans/fixtures/full.toml`'s `w1-mon` override names `run-2026-01-06-am`, a stem no wave-1 CLI corpus provides. Ruling: those tests (`tests/test_cli_plan.py::test_success_prints_every_outcome_line_and_the_counts`; `tests/test_plan_e2e.py::test_two_sources_render_every_owned_page_with_report_and_frontmatter`, `::test_two_plain_runs_are_byte_identical_and_report_unchanged`, `::test_two_fake_dates_and_timezones_are_byte_identical`) stage that page (`_stage_w1_mon_override_stem`) so the fixture is coherent under reconciliation; the fixture and every existing assertion are untouched. The 4.6 two-dates precondition was already present at training-blocks be6c936, so 3.2 edits nothing else there. Also `tests/load/test_settings.py::test_load_load_settings_is_called_the_documented_number_of_times_per_command` widened: `sync`/`regen` read `[load]` TWICE (load pass + the reconciling pass's `default_calculator` read); its docstring cites this note. Four review rounds after the ruling, all fixture-side: the quiet rule (8.5) and the exit fold (8.7) need a pin PER CALL SITE (drain, regen, plan standalone — a single explicit-source test leaves the other sites' mutations green); "print nothing" must stub `_run_plan_pass` itself, not `run_reconcile`; ordering clauses (8.1 pass-after-load, 8.6 reconcile-after-plan-line) need `output.index` assertions; `markup=False, highlight=False, soft_wrap=True` needs a `[bold]` fixture per printed line. `_today()` via `datetime.now(...)` is pinned only by 3.5's crossing-row e2e — 3.5's reviewer must run it.
