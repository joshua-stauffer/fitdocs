# Implementation Plan

## Upstream Prerequisites

- **`effort-tags` must land first.** This plan reads a page's tag through
  `fitdocs.contract`'s published reader. Five names it needs do **not** exist on
  `main` today and arrive with that spec: `effort_tag`, `EffortKind`,
  `EffortTag`, `InvalidEffortTag` (and its `describe()`) and `USER_KEYS`. The
  contract names this plan also uses — `parse_frontmatter` (reached only
  through `docio.read_frontmatter`), `is_workout_document`, `document_date`,
  `source_refs`, `sha_of_ref` — all ship
  today and are not blockers. Every task that touches a tag stops and reports
  rather than defining a second reader, a second key spelling, or its own
  frontmatter parse.
- **`athlete-benchmarks`** owns `src/fitdocs/benchmarks.py` (the vocabulary,
  `Benchmark`, `parse_benchmarks`, `benchmarks_to_document`, `BenchmarkSet`),
  and its store contract: an entry's natural key is
  `(discipline, kind, measured_on)`, an unrecognised entry key is ignored on
  parse, and an unrecognised discipline is rejected. This plan extends that
  module with one field and changes no existing guarantee.
  **Read the post-Amendment-1 shape, not this plan's memory of it**
  (design.md § Amendment 1): `Benchmark` is
  `kind, discipline, value, measured_on, note, applies_from`; the serializer
  emits `value, measured_on, applies_from, note`; `with_benchmark` already takes
  `applies_from=`. Every "last", "after the note and the applies-from date" and
  "fifth" below means *after `applies_from`*. Re-adding or reordering `applies_from` is a stop-and-report.
- **`training-load`** owns `src/fitdocs/load/profile.py` — `AthleteProfile`,
  `with_benchmark`, `load_profile`, `save_profile`,
  `_merge_benchmarks_document` and its overlay rule (which already preserves an
  unrecognised key on an existing entry and names "a `source` a future feature
  wrote" as the case it protects). This plan adds methods and refines that
  overlay; it removes nothing.
- **`load-channels`** owns `src/fitdocs/load/channels/`. This plan **imports**
  `sufficiency.evaluate`, `SufficiencySettings`, `ChannelId` and
  `InsufficiencyReason` and adds **nothing** to that package. Its purity guard
  (`tests/load/channels/test_purity.py`) must keep passing untouched.
- **`threshold-load`** owns `src/fitdocs/load/threshold/`. Not edited, not
  imported, not made reachable; `tests/load/threshold/test_boundary.py` passes
  unchanged.

**Hard rules for every task.** No new settings key or table
(`src/fitdocs/load/settings.py` is not edited). No new owned path
(`src/fitdocs/layout.py`, `OWNED_PATHS` and `DECLARED_DIRS` are not edited —
`load-history` owns them). No edit to `src/fitdocs/contract.py` (`effort-tags`
owns it). No document is written by anything in this plan. No bare numeric
literal for a methodology constant. Absent data is `None`; a refused derivation
is an outcome with a reason, never a zero. A task that finds it needs one of the
forbidden edits stops and reports rather than widening.

## Test File Ownership

Each task owns the test modules named here, so no two tasks write the same
assertions.

- `tests/performance/test_types.py` (new) → 1.1.
- `tests/performance/test_sources.py` (new) → 1.2.
- `tests/performance/test_models.py` (new) → 1.3.
- `tests/performance/test_constant_guard.py` (new) → 1.3 creates it for the
  arithmetic module; 3.4 extends its scanned-module list to the derivation
  module.
- `tests/test_benchmarks.py` (extended) → 2.1.
- `tests/load/test_profile.py` (extended) → 2.2 owns the provenance-argument and
  overlay-rule sections; 2.3 owns the derived-subset sections. Each writes its
  own headed section and edits no other.
- `tests/performance/test_derive.py` (new) → 3.1 creates it with the
  threshold-pace section; 3.2, 3.3 and 3.4 each append their own headed section.
  No task edits another's section.
- `tests/performance/test_engine.py` (new) → 4.1 creates it; 4.2 appends the
  archive-and-failure section; 4.3 appends the write/reconciliation section.
- `tests/test_cli_derive.py` (new) → 4.4 creates it with the report and
  exit-status section; 5.2 appends the end-to-end section.
- `tests/test_confinement.py`, `tests/test_contract_consumers.py`,
  `tests/test_public_api.py` → 4.5 only.
- `tests/performance/test_single_writer.py` (new) → 4.5 only.
- `tests/performance/test_purity.py`, `tests/performance/test_reachability.py`
  (new) → 5.1 only. 4.5 writes neither: its single-writer assertion lives in its
  own module above, so the two tasks share no file and no ordering edge.
- `.kiro/specs/athlete-benchmarks/{requirements.md,design.md,spec.json}` and the
  roadmap's Phase 6 checkbox → 5.3.

**Shared source files.**
- `src/fitdocs/performance/__init__.py` — 1.1 creates it and publishes the pure
  names and their exact `__all__`; 4.3 appends the pass entry point and extends
  `__all__` by that one name. No other task writes it.
- `src/fitdocs/performance/derive.py` — 3.1, 3.2, 3.3, 3.4, strictly sequential;
  none marked `(P)`.
- `src/fitdocs/performance/engine.py` — 4.1, 4.2, 4.3, sequential.
- `src/fitdocs/load/profile.py` — 2.2 and 2.3, sequential.
- `src/fitdocs/cli.py` — 4.4 only.
- `src/fitdocs/benchmarks.py` — 2.1 only.

**Shared with `load-history`** (the other wave-2 spec, implementable in
parallel with this one). Five files are edited by both: `tests/test_confinement.py`
(4.5 here / `load-history` 5.4), `tests/test_contract_consumers.py` (4.5 / lh
5.4), `tests/test_public_api.py` (4.5 / lh 5.4), `src/fitdocs/cli.py` (4.4 / lh
5.3) and `README.md` (4.4 / lh 1.3). The partition rule in every one of them:
**append** a row, an entry, a command or a section; never rewrite or reorder an
existing one; never touch the peer spec's row. A conflict here means someone
edited rather than appended.

**Every new assertion names its mutation** (change-protocol § Fixture
Discrimination): each task's detail bullets name the production mutation that
must redden the assertion; the implementer runs it, observes red, reverts,
observes green, and says so in the report. Fixtures are synthetic activities and
synthetic pages — the athlete's real wiki never enters the repository.

- [ ] 1. Foundation: the pure vocabulary, the citation records and the arithmetic

- [x] 1.1 Publish the derivation vocabularies and outcome values
  - Create the package and its first module, holding the closed
    derivation-method vocabulary (four members: the race-equivalence model, the
    sustained-effort mean heart rate, the time-trial mean power, and the
    twenty-minute power factor) and the closed decline-reason vocabulary
  - Include in the decline-reason vocabulary, by identical string value, the
    three stream verdicts the shared sufficiency evaluation can actually return,
    plus the eight reasons this feature owns; add the conversion from a
    sufficiency verdict, which maps those three and raises the caller-error
    exception for every other member of the shared enumeration rather than
    inventing a reason for a verdict that cannot arrive
  - Add the two frozen outcome values — a derived benchmark carrying quantity,
    discipline, value, date, method, citation key, inputs text, note and source
    document; and a declined derivation carrying quantity, optional method,
    reason, detail and the optional observed/required pair — plus the sealed
    union of the two
  - Create the package's `__init__.py` publishing these names and an exact
    `__all__` covering exactly them; the pass entry point is appended later by
    4.3 and is deliberately absent here
  - Observable: importing the package binds every published name; iterating
    every member of the shared sufficiency-verdict enumeration shows each one is
    either mapped by identical value or rejected, so a member added upstream
    reddens here rather than falling through silently
  - Pins: the three shared reasons equal the sufficiency enumeration's own
    string values; the method vocabulary has exactly four members; the derived
    value is frozen and rejects attribute assignment. Mutation each dies on:
    renaming `stream_coverage` to `coverage` in the decline vocabulary
  - _Requirements: 5.10, 7.3, 7.4_
  - _Boundary: PerformanceTypes_

- [x] 1.2 Record every source, every constant and the two blocked sets
  - Add the citation module holding the six citations (Riegel 1981, Drake et al.
    2024, McGehee et al. 2005, Dumke et al. 2006, Coggan 2003, Borszcz et al.
    2018), each with authors, year, work, locator and an honest verification
    status, and the fitdocs-choice records for the one-hour solve target, the
    sustained-effort duration window, the effort-span tolerance, the
    short-protocol routing floor and the rounding offset
  - Bind each of the eleven shipped constants to exactly one governing record
    with its corroborators, per the design's constant table — the rounding
    offset among them, as a cited constant whose governing record is a fitdocs
    choice, so the arithmetic module reaches `0.5` through a bound record and
    the literal guard has nothing unclassified to explain
  - Record the coaching "final 20 of 30 minutes" protocol as a departure, with
    its unsourced 10-minute discard as the reason it is not implemented
  - Declare the tracked set of citations carrying secondary attestation (Riegel
    today, noting that the JSTOR 1981 text has not been read), the set of
    constants that may not be written because their locator is unverified (the
    0.95 twenty-minute factor today — recorded with no numeric value anywhere in
    this package), and the set of methods blocked by them, keyed by the method
    vocabulary 1.1 published
  - Write the reference document recording what was read, what was not, and
    exactly what unblocks the factor, following the existing Banister
    primary-sources document's shape
  - Observable: the module holds no arithmetic, and a test iterating every cited
    constant finds exactly one governing record each; a test fails on any
    secondary-attestation citation not named in the tracked set; a test asserts
    every pending constant has a blocking method
  - Pins: this module's Coggan record agrees with the shipped channels-layer
    Coggan record on authors, year and work while carrying its own locator; this
    module imports only the shared citation vocabulary, the method vocabulary
    and the standard library. Mutation each dies on: flipping the Riegel
    citation's status to primary text
  - _Requirements: 2.9, 3.7, 4.8, 8.1, 8.2, 8.4, 8.5, 8.6, 8.8, 9.8_
  - _Boundary: PerformanceSources_
  - _Depends: 1.1_

- [x] 1.3 Implement the pure arithmetic and its literal guard
  - Add the arithmetic module: the race-equivalence solve for the distance whose
    predicted time is the one-hour target, the pace that follows from it, the
    time-weighted mean over a sample array, the recorded span, and the
    whole-number rounding for beats per minute and for watts, both reaching the
    rounding offset through its cited constant
  - Make the time-weighted mean accumulate over exactly the consecutive-pair
    domain the shared coverage measure uses (each interval credited to the
    earlier sample), and say so in the docstring alongside why the shipped
    sample-count mean is not interchangeable here
  - Return the absent value rather than raising whenever inputs cannot support a
    result: fewer than two samples, a zero span, a wholly unrecorded stream
  - Add the numeric-literal guard over this module: every literal is either
    matched to a cited constant's recorded value or exempt by a registered
    reason (unit conversion, index or identity), and the scan is asserted
    non-vacuous
  - Observable: a hand-computed worked example (a 5 000 m race in 1 200 s)
    reproduces to a stated tolerance, and the rounding sends both `169.5` and
    `170.5` away from zero — the case the standard rounding built-in would send
    to an even value
  - Pins: mutation the worked example dies on is the exponent moving from 1.06
    to 1.0; mutation the mean dies on is crediting an interval to the later
    sample; mutation the guard dies on is inlining any constant's value
  - _Requirements: 2.1, 3.2, 3.7, 4.2, 8.3_
  - _Boundary: PerformanceModels_
  - _Depends: 1.2_

- [ ] 2. The benchmark store gains provenance (the athlete-benchmarks amendment)

- [x] 2.1 (P) Add the provenance record to the benchmark entry, its parser and its serializer
  - Extend the benchmark vocabulary with the closed origin class (derived,
    measured) and the frozen provenance value carrying the origin plus the
    optional method, document, inputs and citation, with a derived-origin
    predicate
  - Add the optional provenance field to the entry value, last and defaulted —
    after the athlete-declared applies-from date Amendment 1 left trailing — so
    no existing construction site changes and no existing field moves
  - Validate the record on parse in the module's existing voice: absent yields
    the absent value; a non-table is an error naming the entry path; a missing
    or unrecognised origin is an error naming the entry path; a derived origin
    requires all four detail fields as non-empty strings; a measured origin
    requires none; an unrecognised key inside the record is ignored on parse;
    the method name is validated as a non-empty string only, never against a
    vocabulary
  - Emit the record from the serializer **last**, after the applies-from date
    and the note (the file's order, which is not the value type's), with a fixed
    key order and every absent field omitted, leaving the group's
    measured-on-only sort key untouched
  - Observable: a decoded document carrying a derived entry and a measured entry
    parses into typed values whose fields match the file, and serializing those
    values back produces the same recognised keys in the same order — the
    unknown-inner-key preservation is a *merge* property and is proved by 2.2,
    not here, because the parser deliberately drops unknown keys
  - Pins: an entry with no record parses to the absent value and is therefore
    "not derived"; a record whose origin is an unrecognised string raises naming
    the entry path (the *file* name is added by the profile layer and is
    asserted in 2.2); a group mixing entries with and without the record still
    sorts by measured-on alone — belongs beside
    `tests/test_benchmarks.py::test_serializer_sorts_mixed_group_by_measured_on_not_applies_from`,
    which pins the same thing for the applies-from date. Mutation each dies on:
    accepting a derived origin with no citation field; making the record a sort
    tie-breaker
  - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.8, 5.10_
  - _Boundary: BenchmarkProvenance_

- [x] 2.2 Thread provenance through the profile write path and refine the merge overlay
  - Add the optional provenance argument to the existing single-benchmark write
    method, validated before anything is stored, with nothing stored on a
    violation
  - Change the merge overlay in two halves, because the record is the store's
    first nested recognised value and the entry-level update is too blunt for
    it: when a freshly emitted entry at a date carries **no** record, delete any
    record on the inherited raw entry before the overlay; when it **does** carry
    one, write the five recognised keys onto the inherited raw record rather
    than replacing the whole table, so an unrecognised key inside it survives a
    refresh
  - Keep the inherit-on-absent rule of **both** the note and the applies-from
    date untouched — the latter acquired it in Amendment 1 for the same reason —
    and document the asymmetry in the merge function's docstring: a note is
    commentary that can outlive a value and an applies-from date is the athlete's
    own declaration, but provenance is a claim about this value
  - Keep the merge scope-agnostic: it has no scope conditional today and must
    gain none. Give every overlay branch this task adds an athlete-wide fixture
    alongside its discipline-scoped one — no existing fixture varies scope
    through the merge, so an athlete-scope-only regression would pass the suite
    silently (the finding from the upstream task that added applies-from)
  - Observable: writing a prompt-style answer over a date that previously held a
    derived entry leaves no provenance record behind while a note *and an
    applies-from date* written earlier at that date both survive; refreshing a derived entry at a date whose
    raw record carries an unrecognised inner key leaves that key in the written
    file; every non-benchmark key, every quantity the write did not cover and
    every unrecognised table survive untouched
  - Pins: a malformed record in a loaded file raises naming **the file** and the
    entry path (the profile layer's own voice, Req 5.5); the pre-write re-parse
    the save path already performs now also proves the record round-trips, so a
    serializer that emitted a shape the parser rejects fails before any
    temporary file is created. Mutation each dies on: letting the provenance
    field inherit like the note and the applies-from date do; making the
    absent-→-removed rule also delete the inherited applies-from date
  - _Requirements: 5.3, 5.5, 5.6, 5.7, 5.9, 6.6_
  - _Boundary: BenchmarkProvenance, ProfileDerivedWrite_
  - _Depends: 2.1_

- [x] 2.3 Add the derived-subset write and the never-overwrite rule
  - Add the query that answers whether an entry exists at exactly a given
    discipline, quantity and date whose provenance is absent or not derived
  - Add the write that keeps every non-derived entry, replaces the whole derived
    subset with the supplied entries, and rebuilds the document through the
    existing merge
  - Close the one case that merge cannot reach: a discipline-and-quantity group
    whose every entry was derived and is now gone is covered by nothing in the
    rebuilt set, so the merge would leave the stale raw group in place — record
    which groups held a derived entry before the call and remove any such group
    the rebuilt set no longer covers, dropping a scope table left with no groups
    so the file never carries an empty table
  - Raise the caller-error exception, storing nothing, when a supplied entry
    lacks derived provenance or collides with a retained non-derived entry — a
    backstop behind the pass's own filter, proved directly rather than assumed
  - Observable: starting from a hand-written profile, writing a derived set
    twice produces byte-identical files; writing an empty derived set removes
    every derived entry — including the whole group and its scope table when
    they held nothing else — while leaving every hand-written entry, note,
    **applies-from date**, unknown key and unrecognised quantity table exactly
    as they were. Give at least one retained hand-written entry in that fixture
    an applies-from date, and one a note, so a group rebuild that drops either
    is caught: this task deletes and rebuilds whole groups, which is the most
    plausible place to lose a neighbour's field (the 7.1 lesson — enumerate
    layers × scopes × kinds × group shapes before the first report)
  - Pins: a refused write leaves the existing file untouched, and the write is
    atomic. Mutation each dies on: retaining derived entries instead of
    replacing them
  - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.7, 6.8_
  - _Boundary: ProfileDerivedWrite_
  - _Depends: 2.2_

- [ ] 3. The derivations

- [x] 3.1 Derive threshold pace from a tagged race
  - Add the derivation module with the threshold-pace derivation: solve the
    race-equivalence model for the one-hour distance and express the result as a
    pace in seconds per kilometre under the running discipline, dated at the
    page's own calendar date
  - Prefer the tag's official course distance and official time; fall back to
    the activity's recorded distance and recorded elapsed time; record which
    pair anchored the number in the inputs text, including the mixed case where
    the tag carries a time alone
  - Decline, naming the observed duration and both bounds, when the effort's
    duration falls outside the model's validity window; decline naming the
    missing or invalid input when a distance or time is absent, non-positive or
    non-finite; decline when the tag's kind is not the race kind
  - Put the governing citation key into the derived value's provenance and the
    method's own statement into its note
  - Observable: a fixture race whose official pair and recorded pair give
    different answers derives from the official pair and says so in the inputs
    text; a 200-second race and a 4-hour race both decline with the window in
    the detail, and neither clamps
  - Pins: mutation each dies on: preferring the recorded pair over the official
    pair
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 8.7_
  - _Boundary: DerivationLeaf_
  - _Depends: 1.1, 1.3_

- [x] 3.2 Derive lactate-threshold heart rate from a sustained maximal effort
  - Add the heart-rate derivation for running and cycling and for all three
    effort kinds: the time-weighted average heart rate over the whole recorded
    effort, never a selected portion and never with a leading or trailing
    segment discarded, rounded to a whole number of beats per minute and
    recorded under the activity's own discipline
  - Gate the heart-rate stream through the shared sufficiency evaluation using
    the caller-supplied settings, and carry its verdict through as a decline
    reason with the observed and required values, so an absent stream, a sparse
    stream and a too-short recording stay three distinct reasons
  - Decline, naming the observed duration and both bounds, when the recorded
    duration falls outside the sustained-effort window; decline naming both
    durations when the tag carries an official time the recorded span disagrees
    with beyond the tolerance, with a detail stating that locating the effort
    inside a longer recording is out of scope
  - Put the whole-effort-average statement and the governing citation into the
    provenance
  - Observable: a 40-minute fixture effort with full heart-rate coverage derives
    a whole-number value; the same effort with coverage below the configured
    minimum declines with the observed fraction in the detail; a 90-minute
    effort declines on the window
  - Pins: the derived number is the time-weighted mean, not the sample-count
    mean, proved by a fixture whose sample spacing makes the two differ.
    Mutation each dies on: averaging only the final third of the effort
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 3.6, 3.8, 3.9_
  - _Boundary: DerivationLeaf_
  - _Depends: 3.1_

- [x] 3.3 Derive functional threshold power, with the unverified factor blocked
  - Add the power derivation for cycling races and tests: the time-weighted
    average power over the whole effort with no scaling factor, when the
    effort's duration falls inside the window the definition itself states,
    expressed in whole watts under the cycling discipline
  - Decline with the unverified-method reason — naming the work, the suspected
    chapter and what must be read — for a cycling effort between the
    short-protocol routing floor and the definition's lower bound, and leave
    every other derivation in the run unaffected
  - Decline naming the observed duration and the covered windows outside those
    two ranges; carry the power stream's sufficiency verdict through as a
    decline reason; decline explicitly, with its own reason text, when the file
    carries no power at all
  - Put the method's published limits of agreement into every derived value's
    note; derive no power benchmark for a running activity even when the file
    records running power
  - Observable: a 55-minute cycling time trial with full power coverage derives
    a whole-watt value whose note names the limits of agreement; a 20-minute
    cycling test in the same fixture set declines as unverified while the
    55-minute one still derives
  - Pins: no numeric value for the blocked factor appears anywhere under the
    derivation package or its citation records — the scan is scoped there, not
    repo-wide, because unrelated modules legitimately carry the same number.
    Mutation each dies on: removing the blocked method from the blocked set
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_
  - _Boundary: DerivationLeaf_
  - _Depends: 3.2_

- [x] 3.4 Route an activity and its tag to every quantity its discipline covers
  - Add the single pure entry point that takes a parsed activity, a valid tag,
    the page's date, the page's data-root-relative path and the sufficiency
    settings, and returns one outcome per quantity the discipline covers
  - Implement the routing table: running attempts threshold pace and heart rate,
    cycling attempts power and heart rate, every other sport yields one decline
    naming the sport; an unparseable page date yields one decline per attempted
    quantity naming that condition
  - Guarantee the entry point never raises, never returns an empty tuple, and
    returns every decline for a document rather than stopping at the first
  - Extend the numeric-literal guard's scanned-module list to cover this module
  - Observable: a swim page yields exactly one outcome, a decline naming the
    sport; a running race with a heart-rate stream yields exactly two outcomes;
    an undated running race yields two declines, both naming the undated
    condition
  - Pins: the routing switch over the tag's kind enumeration is exhaustive under
    the type checker. Mutation each dies on: returning after the first decline
  - _Requirements: 2.8, 7.5, 7.6, 7.9, 10.4, 10.5_
  - _Boundary: DerivationLeaf_
  - _Depends: 3.3_

- [ ] 4. The pass, its command and its registrations

- [ ] 4.1 Build the pass skeleton: discovery, the tag branch and the report types
  - Add the pass module: discover every generated workout document under the
    data root in sorted order, read each one's frontmatter once through the
    shared read, and branch on the contract reader's three outcomes — untagged,
    valid tag, malformed tag
  - Read the page's date through the contract's own reader and record it on the
    per-document record the derivation call 4.2 wires; consult no clock anywhere
    in the pass
  - Add the report types carrying the counts of documents considered and tagged,
    the per-document derived and declined outcomes, and the failures; read the
    stream-sufficiency settings from the existing training-load configuration
    and add no new key or table
  - Observable: over a data root holding one tagged and one untagged page, the
    report's considered count is two and its tagged count is one, with the
    untagged page contributing no outcome of any kind
  - Pins: the module binds the contract's readers and never a YAML parser or a
    fence literal of its own. Mutation each dies on: counting an untagged page
    as tagged
  - _Requirements: 1.2, 7.1, 7.2, 7.3, 9.3, 9.7, 10.3_
  - _Boundary: PassEngine_
  - _Depends: 3.4_

- [ ] 4.2 Resolve and re-parse a tagged page's archive, and classify every failure
  - Resolve a tagged document's archived source by the same rule the
    training-load pass uses — the document's last source reference, refusing a
    traversal reference — and re-parse it; never resolve or open an archive for
    an untagged document
  - Record a failure, naming the document and the cause, for an unreadable
    document, an unresolvable archive, an undecodable archive, and a malformed
    tag rendered through the contract's own problem text; continue over the
    remaining documents in every case
  - Add the equivalence test the design names as the mitigation for stating
    those rules in two passes: over one fixture data root this pass and the
    training-load pass discover the same document set — the same sorted
    top-level markdown glob under the workouts directory behind the same
    workout-document filter — and one fixture document is resolved by this pass
    and by the training-load pass's own resolver, with the two results asserted
    equal, including for a traversal reference where both must refuse
  - Observable: over a data root holding one tagged and one untagged page, only
    the tagged page's archive file is opened, proved by instrumenting the
    archive directory; a page whose archive is missing produces one failure and
    the run still processes the next page
  - Pins: mutation each dies on: resolving the archive before the tag branch,
    and accepting a traversal reference
  - _Requirements: 1.3, 1.4, 1.5, 1.6_
  - _Boundary: PassEngine_
  - _Depends: 4.1_

- [ ] 4.3 Reconcile, filter collisions and write once
  - Filter every candidate against the store's recorded-entry query after all
    documents are processed; turn a collision into a decline naming the existing
    entry's value and date, and drop the candidate so it can never shadow a
    recorded entry
  - Write the whole accepted derived set in a single call and persist it once;
    leave the profile untouched when nothing was accepted, and guarantee the
    preview mode produces the identical report while creating, modifying and
    deleting nothing
  - Add the per-quantity summary that states, for a quantity with no derivations
    anywhere in the run, that none was derived and the dominant reason — so an
    archive with no cycling power says so rather than reporting a silent success
  - Append the pass entry point to the package's published names and its exact
    `__all__`, the one addition to that file after 1.1
  - Observable: running the pass twice over an unchanged tag set leaves the
    profile byte-identical; removing a tag and running again removes exactly the
    entry that tag produced; the preview mode over the same fixture leaves every
    file's bytes unchanged
  - Pins: mutation each dies on: writing a candidate that collides with a
    hand-written entry
  - _Requirements: 1.7, 1.8, 6.2, 6.4, 6.5, 7.7, 9.1, 9.4, 9.5_
  - _Boundary: PassEngine_
  - _Depends: 2.3, 4.2_

- [ ] 4.4 Add the command and its report rendering
  - Add the flat command, named distinctly from every existing command and from
    the command the history spec adds, with the shared data-root option and a
    preview flag; resolve the data root through the existing precedence and fail
    loudly when it cannot be resolved
  - Render the report in the shape the load pass's report uses: a summary line,
    the derived entries with quantity, discipline, value and unit, date, method
    and document, then the declines grouped by document with reason, observed
    and required, then the failures; print bracketed reasons and paths literally
  - Exit non-zero when any document failed and zero when the run produced only
    derivations and declines; state in the preview mode's first line that
    nothing was written
  - Add the one README paragraph naming the command and what it writes
  - Observable: invoking the command over a synthetic data root prints every
    section, writes the profile once and exits zero; a run whose only defect is
    a malformed tag on one page still writes the other page's benchmark and
    exits non-zero
  - Pins: mutation each dies on: treating a decline as a failure in the exit
    status
  - _Requirements: 1.1, 1.9, 1.10, 7.1, 7.2, 7.3, 7.8, 9.6_
  - _Boundary: DeriveCommand_
  - _Depends: 4.3_

- [ ] 4.5 (P) Register the pass with the shared guards and pin its surface
  - Append the pass as one more writing entry point to the existing
    write-confinement registry, reusing the shared-file allowance the profile
    already has; add no owned path and change nothing else in that module
  - Register the pass module in the contract-consumer registry with the contract
    names it binds, so a second reader or a stray frontmatter parse fails there
  - Pin the new package's published surface exactly, each name asserted to be
    the same object its defining module exposes
  - Add the single-writer assertion in its own new test module: an
    abstract-syntax scan over every module in the package source tree finds the
    pass entry point imported by exactly one of them — the command layer — so no
    other command can derive, write or reconcile a derived benchmark; test
    modules are excluded from the scan
  - Observable: the confinement guard runs the pass over a sandbox and finds no
    create, modify or delete outside the profile file; adding a stray YAML
    import to the pass module reddens the consumer guard
  - Pins: the owned-path set and the declared-directory set are unchanged.
    Mutation each dies on: dropping the pass from the entry-point registry
  - _Requirements: 1.10, 9.4, 9.5, 10.3, 10.8_
  - _Boundary: ConfinementRegistration, Guards_
  - _Depends: 4.3_

- [ ] 5. Guards, end-to-end validation and the upstream amendment

- [ ] 5.1 (P) Guard the package's purity and its unreachability from the calculator
  - Add the layered guard over the four pure modules — an import-target and
    imported-name allowlist, a module-namespace allowlist, a dynamic-import call
    scan, an input-output-and-clock denylist, and a builtin-reference allowlist
    — adopted from the sibling channels guard rather than re-derived, with the
    module docstring pointing at it
  - Allow, in that import allowlist, exactly the sanctioned targets the design
    names, including the citation module and the sibling modules within this
    package; nothing from the render, sync or command layers
  - Add the reachability guard: an abstract-syntax scan over every module in the
    calculator package and the channels package asserting none imports this
    feature's package, in either import form and including an aliased
    whole-module import
  - Assert the same scan proves the pure modules reach no filesystem, no
    network, no clock, no prompt and no rendering
  - Observable: both guards are non-vacuous — each is demonstrated to catch a
    deliberately planted violation in a synthetic source string
  - Pins: the channels purity guard and the calculator boundary guard both pass
    unchanged. Mutation each dies on: adding an import of this package to a
    calculator module
  - _Requirements: 8.3, 9.2, 9.3, 10.1, 10.2, 10.6, 10.7_
  - _Boundary: Guards_
  - _Depends: 3.4_

- [ ] 5.2 End-to-end: determinism, the powerless archive and the mixed run
  - Drive the command end to end over a synthetic data root holding a tagged
    running race, a tagged cycling time trial, a tagged cycling ride with no
    power, an untagged page and a page with a malformed tag
  - Assert the profile's bytes are identical across two runs, across a sandbox
    rename that perturbs discovery order, across a pinned non-system time zone,
    and across a perturbed numeric locale — the axes the determinism requirement
    names alongside the machine
  - Assert the report states that no power benchmark was derived from the
    powerless file and why, that the malformed page is a failure carrying the
    contract's own problem text, and that the exit status separates declines
    from failures
  - Observable: the whole scenario passes offline with no network access, and
    the archive files the untagged page references are never opened
  - Pins: mutation each dies on: dating an entry from the run's today rather
    than from the page
  - _Requirements: 1.8, 1.9, 4.6, 6.5, 7.7, 9.1_
  - _Boundary: DeriveCommand_
  - _Depends: 4.4, 4.5_

- [x] 5.3 (P) Land the athlete-benchmarks Existing Spec Update
  - This lands as that spec's **Amendment 2**; its Amendment 1 (the
    athlete-declared applies-from date) is already on `main` and is what the
    entry shape below extends. Read its current requirements, design and
    `spec.json` before writing — the line numbers this plan was drafted against
    predate it — and add to its amendments list rather than replacing it
  - Add an amendment block to the benchmark store spec's requirements carrying
    the new criteria for the provenance field — its optionality, its closed
    origin class, the required fields for a derived origin, the ignored-unknown
    -key rule, its preservation on rewrite, the rule that fitdocs never
    modifies an entry without derived provenance, and the statement that the
    provenance field is the entry's fifth recognised field and neither displaces
    nor interacts with Amendment 1's applies-from date (a derived entry carries
    none, so it is tier-1 only in that amendment's two-tier resolution) —
    renumbering no existing criterion of either amendment
  - Amend that spec's out-of-scope line excluding estimation of any kind so it
    states that estimation is performed by this spec, which hands the store
    ordinary dated entries, and that the store still performs none itself; do
    the same for the matching line in its design document
  - Add the amendments entry to that spec's metadata naming this spec and the
    date, and tick the roadmap's Phase 6 Existing Spec Update checkbox for the
    benchmark store
  - Observable: the store spec's boundary line and this spec's existence no
    longer contradict each other, the amended criteria describe exactly the
    field shape that shipped, and the roadmap item is no longer open
  - _Requirements: 5.1, 10.9_
  - _Boundary: AthleteBenchmarksAmendment_

## Implementation Notes
- (3.1) Gate ordering ruling: the undated gate (`on is None` -> `UNDATED_DOCUMENT`) runs FIRST in every leaf, before the kind gate, so an undated page yields one `UNDATED_DOCUMENT` per attempted quantity regardless of tag kind. 3.2/3.3 copy the order; 3.4 pins it at the routing level.
- (3.1 -> 3.4) `derive.py` carries one numeric literal, `value > 0` in `_finite_positive` -- an arithmetic identity the constant guard must register when 3.4 adds the module to the scanned tuple (mirror the `models.py` entry).
- (1.2 -> 5.1) AST import-allowlists that filter `node.level == 0` silently admit relative imports; the purity guard must assert `level == 0` explicitly.
- (3.2) Gate ordering ruling for the stream leaves: undated -> span agreement (when the tag carries `time_s`) -> sufficiency -> validity window, per design § Per-quantity gates (`Span -> Gate -> Window`). 3.3 copies it; 3.4 pins it at the routing level. A present-but-zero stream is gated with `_finite_positive` on the mean and declines `MISSING_INPUT` -- never a zero benchmark.
- (3.4) `lactate_threshold_hr` records `discipline=activity.sport` unconditionally; the router must never call it for a sport other than RUN/RIDE.
- (3.2) A `recorded_span_s` of `None` (fewer than two samples / zero span) declines `MISSING_INPUT` with `required=None` in the leaf rather than falling through to the shared sufficiency gate -- absent data is `None`, never a zero span handed to `evaluate`. This is a deliberate, documented departure from the training-load pass's `TOO_SHORT` wording for the same file (Req 7.4 covers the three verdicts the gate actually returns).

