# Implementation Plan

> **Cross-spec review amendments (2026-07-25)** — three ownership rulings are
> binding on this plan; full text in `design.md` → *Cross-Spec Amendments*.
> (1) `src/fitdocs/load/settings.py` belongs to `training-load`; task 2.2
> **extends** it and never creates a second `[load]` reader.
> (2) `ProfileView` stays a pure store view; the activity date and the staleness
> window ride `training-load`'s per-pass `LoadContext` (Amendment 3), so tasks
> 3.1, 4.1 and 5.2 add no per-pass state to the store or the view.
> (3) The `contract.document_date` accessor is **added by `training-load` task
> 4.1**, whose design re-validation claimed the incursion and superseded the
> first round's assignment to this spec. Task 5.1 consumes it and creates it only
> as a fallback, to the owner's exact signature — see task 5.1.

- [x] 1. Benchmark vocabulary, parsing, selection and staleness

- [x] 1.1 Define the benchmark value vocabulary as a top-level leaf module
  - Create `src/fitdocs/benchmarks.py` with the quantity enum (functional threshold power in watts, lactate threshold heart rate, threshold pace in seconds per kilometre, maximum heart rate, resting heart rate), the discipline-scoped and athlete-scoped quantity sets, the reserved athlete-wide scope token, the integral-valued quantity set, the immutable `Benchmark` value carrying quantity, discipline, value, measurement date and optional note, and the module's own domain error type
  - Discipline values reuse the shipped sport vocabulary; assert in a test that no sport value collides with the reserved athlete-wide token
  - The module imports no `fitdocs.load.*` module and performs no file I/O
  - Observable: `uv run mypy --strict src/` is clean and a unit test constructs a benchmark for a discipline-scoped and an athlete-scoped quantity and reads back its value, date and note
  - _Requirements: 1.2, 1.3, 1.4, 1.5_
  - _Boundary: BenchmarkVocabulary_

- [x] 1.2 Implement the single benchmark parser and serializer
  - Parse the decoded `[benchmarks]` region into a validated, immutable set: an absent region yields an empty set; unrecognized keys inside an entry are ignored
  - Reject with a message naming the offending path: a non-numeric or boolean value, a zero/negative/non-finite value, a fractional value for a whole-beat quantity, a missing or non-bare-date measurement date (a TOML date-time must be rejected even though it subclasses a date), an unrecognized discipline table, a quantity recorded in the wrong scope, two entries sharing discipline/quantity/date, and a scalar where a table or array of tables belongs
  - Implement the inverse serializer that emits entries grouped by scope and quantity and sorted ascending by measurement date
  - Observable: a table-driven unit test covers one case per rejection rule and asserts each message names the offending discipline, quantity or value; a round-trip test shows parse(serialize(entries)) equals the original set
  - _Requirements: 1.10, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.10, 6.6_
  - _Boundary: BenchmarkVocabulary_

- [x] 1.3 Implement date-aware selection and undated presence
  - Add applicability lookup over the parsed set: consider only entries for the requested quantity and scope whose measurement date is on or before the given date, and return the one with the latest such date
  - Add an undated presence query that ignores dates entirely, so callers can tell "none on file" from "none applicable yet"
  - Never fall back to another discipline, to the athlete-wide scope, or to any default; a scope that disagrees with the quantity is a programming error and raises
  - Observable: unit tests prove a same-day measurement applies, a later-dated measurement never applies to an earlier activity, an all-future history returns nothing while presence stays true, an empty history returns nothing with presence false, and repeated calls with equal inputs return equal results including the returned measurement date and note
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 3.9, 9.5_
  - _Boundary: BenchmarkSelection_

- [x] 1.4 Implement staleness as a pure computation
  - Add the age verdict value (age in days, the window compared against, and the stale flag) and the function computing it from an activity date, a measurement date and a window
  - The function reads no file and no clock; a measurement date after the activity date, or a window below one day, raises rather than reporting the benchmark as current
  - Observable: unit tests pin the exact boundary — an age equal to the window is current and one day beyond it is stale — assert the reported age and window accompany the verdict, and assert the precondition violations raise
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
  - _Boundary: StalenessCalculation_

- [x] 2. File-level guards and shared configuration

- [x] 2.1 (P) Add the athlete file's schema version guard
  - Introduce the schema version constant (current version 2: flat athlete inputs plus benchmarks) and the guard that reads the existing on-disk version key, keeping the key's name unchanged for file compatibility
  - An absent version means the earliest version and the file is read normally; a non-integer, boolean, sub-minimum or above-supported version fails with the file's existing error type naming the file, the declared version and the supported version; benchmarks present under an older declared version are still read
  - Call the guard from the athlete-inputs read path before any field is projected, leaving that path read-only: it still creates nothing, prompts for nothing and writes nothing
  - Observable: the existing athlete-inputs test suite passes unchanged, plus new tests for the absent, accepted, and refused version cases; a test asserts the data root is byte-identical after a read of an existing file
  - _Requirements: 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 9.1_
  - _Boundary: AthleteFileGuard_

- [x] 2.2 (P) Extend the `[load]` settings reader with the staleness window
  - **Ownership: `training-load` owns `src/fitdocs/load/settings.py`** (its task 3.1). This task **extends** that module with one field — the staleness window, defaulted to a documented 84 days — and its validation. Never create a second reader for the `[load]` table, and never rename or reshape the owner's reader, error type or defaults constant
  - If the module has not landed yet, create it to **exactly** this pinned surface and to no other: `load_load_settings(document: Mapping[str, object], settings_file: Path) -> LoadSettings`, `class LoadSettingsError(SettingsError)`, and `DEFAULT_LOAD_SETTINGS: Final[LoadSettings]` with every field defaulted — so whichever spec lands second adds only a field. Do not invent `load_settings_from_document`; that name follows the older `tiles` variant and collides with the shipped `fitdocs.settings.load_settings_document`, which reads the *file*
  - The reader never opens, locates or re-reads the settings file itself; callers hand it the document produced by the shared settings read, and `settings_file` is used only to name the file in messages
  - An absent settings file, an absent table or an absent key yields the default and is never an error; a boolean, non-integer, zero or negative value fails naming the file, key and value; a non-table `[load]` value fails the same way; unrecognized keys **and unknown sub-tables** are ignored so sibling features can add their own
  - The staleness window reaches a calculator as `context.settings.benchmark_staleness_days` on the per-pass context, never through the profile view (Req 7.3); nothing in this task touches `ProfileView`
  - Tests go in the owner's `[load]` reader test module (`tests/load/test_settings.py`); the owner's existing cases stay green
  - Observable: unit tests cover default-on-absence for all three absence levels, every rejection case, and an unknown-key and unknown-sub-table case that returns the default without raising
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 7.3_
  - _Boundary: LoadSettingsExtension_

- [x] 3. Reconcile the athlete store onto one file

- [x] 3.1 Give the profile store benchmark reads
  - Make the profile error type a subclass of the athlete file error so one file has one catchable voice, and run the schema-version guard and the benchmark parser eagerly when a profile is constructed, re-raising the parser's domain error as a profile error naming the file
  - Add applicability and presence queries delegating to the selection functions, with the discipline and the activity date as explicit arguments; an applicability query given no date returns nothing, because an undated activity has no applicable benchmark and the store never assumes today's date
  - The store carries **no** configuration and **no** per-activity state: no staleness window, no bound activity date, no binding method. The window rides the per-pass context and the date is an argument, so one profile instance serves every document in a pass and the profile loader's signature is unchanged. An absent file still yields an empty profile and creates nothing
  - Repair the existing fixtures that construct a profile directly now that construction parses eagerly and can raise — the prompt-flow, profile-store and end-to-end load tests each build one by hand
  - Observable: constructing a profile over a malformed benchmark region raises the profile error before anything is written; a test asserts an undated query returns nothing, that an absent file yields an empty profile with no file created, and that the parsed benchmarks and the raw document never disagree; the whole existing load test suite passes unchanged in behavior
  - _Requirements: 1.1, 2.9, 2.10, 3.7, 7.1, 7.2, 7.4, 7.7, 9.5_
  - _Boundary: BenchmarkStore_

- [x] 3.2 Implement the dated-measurement write path
  - Add the benchmark mutation returning a new profile whose document contains the entry keyed by discipline, quantity and measurement date, replacing an entry with the same key instead of appending a duplicate, and rejecting a scope/quantity mismatch or an invalid value without storing anything
  - Stamp the current schema version on every save, emit benchmark entries date-sorted through the serializer, preserve every unmanaged key and table verbatim including the flat athlete-input keys and existing benchmark history, and keep the write atomic with no temporary file left behind
  - Retire the store's own profile-version constant in favour of the shared schema-version constant from task 2.1, updating its export list and the test that imports it by name; the on-disk key name does not change
  - Never create or update a flat threshold key from this path
  - Observable: a round-trip test writes two dated benchmarks for one discipline, re-reads them in ascending date order with the version stamped, shows an unmanaged table and the flat keys survived, and shows that persisting twice on one date leaves exactly one entry whose file still parses
  - _Requirements: 1.1, 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 9.2, 9.3, 9.4_
  - _Boundary: BenchmarkStore_

- [x] 4. Redefine the calculator contract and route the prompt flow

- [x] 4.1 Extend the profile view with benchmark queries and make benchmark fields declarable
  - Extend the profile view protocol with date-scoped benchmark applicability and undated benchmark presence alongside the existing keyed numeric access, all with discipline and date as explicit arguments and no structured data in key strings
  - **The view stays a pure store view**: do not add the staleness window, the activity date, or any other per-pass state to it. Both travel on the calculator's per-pass context (`training-load` Amendment 3) — the window as `context.settings.benchmark_staleness_days`, the date as `context.activity_date` — so a view member would duplicate an owned channel and give one profile instance per-document state
  - Add the benchmark reference value and the optional benchmark member on the declared athlete field, documenting that the field key identifies the table an entry lives in rather than a value path
  - Re-export the benchmark types and the staleness function on the plugin surface and update the public-surface pin to the extended shape
  - Update every test double annotated as or standing in for the profile view — the contract-type tests, the stub-calculator fixtures, the registry tests and the plugin regression test — so each satisfies the new member set. There is no `tests/load/withdrawn/`: the withdrawn calculator and its tests were deleted in `6386361`
  - Observable: the public API test passes against the new shape, `uv run mypy --strict src/` and the full test suite are clean, and the stub calculators that consume only keyed numeric access still type-check and pass their tests
  - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7, 8.1_
  - _Boundary: ProfileContract, PublicSurfacePin_

- [x] 4.2 Route benchmark fields through the existing prompt flow
  - Take the date an answer is provided as an explicit parameter of the collection flow, and branch the already-have-it check on whether a field declares a benchmark: undated presence for benchmark fields, keyed value presence for the rest
  - Persist an accepted benchmark answer as a dated measurement stamped with the provided date, immediately, through the store's mutation; a declined or non-interactive answer persists nothing and is returned still missing
  - Leave the questions asked, the range presentation, the re-ask loop, the skip keyword and the confirm hint unchanged
  - Integration step, required to keep the tree green: update the load pass's single call site of the collection flow, resolving the current local date once at the pass's entry point and making it injectable for tests — the remaining engine wiring lands in 5.1
  - Observable: tests show a benchmark field with nothing on file is prompted once and persisted with the provided date; a second call does not prompt again even when the activity being processed predates every entry on file, and the field is not reported as still missing in that case; a declined answer leaves the file untouched; a non-interactive session prompts nothing and completes; the full suite and `uv run mypy --strict src/` pass at the end of this task
  - _Requirements: 6.2, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  - _Boundary: PromptFlowIntegration, LoadEngineWiring_
  - _Depends: 3.2, 4.1_

- [x] 5. Read the document date, then wire the load pass and the CLI

- [x] 5.1 Ensure the document-date accessor is available on the document contract
  - **Ownership: `training-load` task 4.1 adds `contract.document_date`.** Its design re-validation claimed the incursion because task 4.1 cannot build its per-pass context without the accessor and this spec had committed no task. This task **consumes** it: confirm the reader exists with the pinned signature and the behavior below, and never redefine, rename or reshape it
  - **Fallback, only if task 4.1 has not landed when this task runs**: create the reader to **exactly** this pinned surface and to no other — `document_date(frontmatter: Mapping[str, object] | None) -> date | None`, returning a document's own local calendar date from its parsed frontmatter, or nothing for an absent key, a wrong-typed value or a string that does not parse. Add one reader and one test case; change no existing reader, no key constant and no managed-key membership. Blocking instead was adjudicated closed: task 4.1 sits behind `training-load` tasks 3.2 and 3.3, so waiting would stall this spec's whole date path on a peer's mid-plan task
  - Either way, accept both on-disk forms: the quoted date string the renderer emits and the bare date a hand-edit produces; never raise and never guess a date
  - The accessor belongs to the document contract because that module already owns the key and is the only sanctioned place frontmatter is read from; the renderer emits the date as a quoted string, so a real accessor rather than a bare lookup is required
  - **Cross-spec coordination — `wiki-contract` owns this module and its test module.** Record the accessor as a `wiki-contract` revalidation item whichever spec landed it: any change there to the reader set, the managed keys, or the `date` key's on-disk form revalidates it
  - **Sequencing.** `training-load` task 2.4 edited the same module and the same test module for the managed-load-key rename and the document-format-version bump, and **landed** as the single atomic commit `a782034` — that hazard is retired. The live coordination is with task 4.1 alone, which touches those same two files for this accessor: check for it before writing, and never add a second `document_date` on top of it
  - Observable: unit tests cover the quoted string, the bare date, an absent key, a non-string non-date value and an unparseable string, and the existing document-contract tests still pass. If task 4.1 landed first, its cases already cover this and the task adds only what they leave uncovered
  - _Requirements: 3.6, 3.7_
  - _Boundary: DocumentDateAccessor_

- [x] 5.2 Thread configuration and the activity date through the load pass
  - At the start of the load pass, obtain the settings document through the shared settings read and project the `[load]` table from it once, so a configuration failure aborts the pass before any document is read or written
  - Thread the frontmatter mapping the pass already parses into the compute step and resolve each document's date through the contract accessor; supply that date and the resolved settings on the per-pass context handed to the calculator, not on the profile view. A document with no parseable date yields a context whose activity date is nothing, and no benchmark can apply
  - The context type and `compute`'s parameter list belong to `training-load` (Amendment 3): fill its fields, do not define or extend the type here. If Amendment 3 has not landed, stop and escalate rather than binding the values onto the profile view — that route was adjudicated closed
  - Observable: an integration test shows a configured window of 30 reaching the calculator as the context's settings value, a stub calculator seeing the document's own date on the context for a dated document and nothing for an undated one, and a malformed `[load]` value aborting the pass with every document unmodified
  - _Requirements: 2.9, 3.6, 3.7, 5.5, 8.2_
  - _Boundary: LoadEngineWiring_
  - _Depends: 2.2, 3.1, 4.2, 5.1; training-load Amendment 3 (`LoadContext`, its task 3.3), and `contract.document_date` from its task 4.1 — or 5.1's fallback standing in for 4.1_

- [x] 5.3 Surface settings failures at the CLI configuration exit
  - Add the shared settings error to the error types the load pass command already catches and routes to the configuration-error exit, so a table-level or file-level settings problem exits with the configuration code before anything is written
  - Sequenced after the engine wiring: until the pass reads the `[load]` table, no settings error can reach the command and the behavior is untestable
  - Observable: a CLI test runs the load command against a data root whose settings file carries an invalid staleness window and asserts the configuration exit code, the message naming the file and key, and an unmodified data root
  - _Requirements: 2.9, 5.5_
  - _Boundary: CLIErrorSurface_
  - _Depends: 2.2, 5.2_

- [x] 6. Feature validation

- [x] 6.1 Prove date-scoped selection end to end across a measurement-system boundary
  - Build a data root holding two dated running thresholds spanning a hardware change and workout documents on both sides of it, and drive a full load pass with a stub calculator that records which benchmark it resolved and what staleness verdict the context's configured window produced
  - Assert each document resolved the threshold current at its own date, that a document predating every threshold resolved nothing while presence stayed true and no prompt occurred, and that a second pass produces identical resolutions
  - Assert at the report level that the document with a benchmark on file but none applicable is reported not computed with a reason distinct from the one a document with no benchmark on file receives, so the two absences are separable by a reader of the pass output
  - Observable: the test asserts per-document resolved values, measurement dates, staleness verdicts and the two distinct skip reasons, and that re-running the pass changes no file
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.8, 4.3, 8.4_
  - _Depends: 5.2_

- [x] 6.2 Prove absent-store honesty and no rendered-output drift
  - Run a non-interactive load pass over a data root with no athlete file: every document is reported not computed with a reason, no file is created, and the pass exits cleanly
  - Run the full suite plus lint and strict type checking, confirming the shipped golden-file document tests are unchanged — evidence that the flat athlete-input keys and every rendered metric were untouched by this feature
  - Observable: `uv run pytest`, `uv run ruff check .` and `uv run mypy --strict src/` all pass with no golden file edited in this feature's diff
  - _Requirements: 1.9, 1.11, 8.6, 9.1, 9.2, 9.3, 9.4, 9.5_
  - _Depends: 5.2, 5.3_

## Implementation Notes

- **Write the fixture so the invariant is observable, then mutate to prove the
  assertion can fail.** Task 1.2 was rejected twice for tests that looked right
  but could not fail: the serializer's sort test supplied entries *already* in
  ascending order (deleting `sorted()` left all 36 green, Req 6.6 unpinned), and
  the int-storage test supplied `{"value": 190}`, already an `int` (deleting
  `int(numeric)` left all 1793 green). Both needed an input that distinguishes
  the behavior from its absence — descending input, and the whole float `190.0`.
  A sibling spec hit the same class of defect the same day.
- **A rejection case must pin its own rule.** Task 1.2's Req 2.5 case used a
  discipline-scoped kind under a bogus discipline, so deleting rule 2.5 entirely
  still raised — from rule 2.6 — and the assertion could not tell them apart.
  Using an *athlete-scoped* kind makes a deleted 2.5 raise nothing at all. When
  two rules can fire on one fixture, choose the fixture only the target rule
  rejects.
- **Two settled design ambiguities, both resolved from `design.md` itself:**
  discipline tables are matched **case-insensitively** (the Physical Data Model
  spells every table lowercase — `[[benchmarks.run.ftp_watts]]` — so a strict
  `Sport(value)` lookup would reject design's own documented example; no `Sport`
  value lowercases to `athlete`, so the reserved token cannot collide); and
  `INTEGRAL_KINDS` values are **stored as `int`** while `Benchmark.value` stays
  annotated `float` (design's invariants require the former, its service
  interface the latter — both are honored, and `bool` is rejected before any
  numeric path so `True` can never survive as `1`).
- An unrecognized *quantity* name under a recognized discipline is silently
  ignored (Req 1.10), while an unrecognized *discipline table* is rejected
  (Req 2.5). This asymmetry is design's, not an accident — but a typo'd
  `ftp_wats` is silently dropped in a hand-edited file. Queued, not fixed here.
- **For a selection function, assert the defining property, not the chosen
  entry.** Task 1.3 was rejected three times and needed a debug escalation
  because "no mutation a reviewer can think of survives" is an *unbounded*
  acceptance test: for any finite fixture, some substitute key
  (`min(value)`, `max(note)`, `max(month)`, `max(ordinal%365)`, …) agrees on
  those points, so each round closed one mutant and exposed the next. Fixture
  retuning also oscillates — round 2 fixed a max-by-value confound by
  inverting the values, which installed a min-by-value confound. What
  terminated it: sweep every date across a multi-year grid and assert
  `[e for e in qualifying if result.measured_on < e.measured_on <= on] == []`.
  That is maximality quantified over the other entries rather than a
  re-implementation of `max`, so every wrong key violates it by construction.
  It killed 20 of 21 mutants; the survivor,
  `max(key=(measured_on, value))`, is provably equivalent because Req 2.7
  rejects duplicate natural keys, making the tiebreaker unreachable.
- **Never claim in a comment what a test would catch.** A comment may state
  what a test asserts; it may not state which hypothetical wrong
  implementations it would detect. That claim class was false in four
  consecutive rounds of task 1.3, in both directions, and once the false claim
  sat in the very sentence that would have exposed a surviving mutation. Such
  claims are unverifiable at review time and rot silently as fixtures change.
  Delete them rather than correcting them.
- **Mutation checks need `PYTHONDONTWRITEBYTECODE=1` and a cleared
  `__pycache__`.** CPython invalidates `.pyc` on `(mtime_seconds, size)`, so a
  same-size edit within one second reuses stale bytecode and reports a false
  SURVIVES. Three false survivals were reproduced this way during task 1.3, and
  at least one earlier round's evidence may have been polluted by it.
- **Never revert a mutation with `git checkout -- <file>`.** Task-level work is
  uncommitted, so that discards the whole task, not the mutation. Task 1.4 hit
  this and had to re-apply its implementation by hand. Copy the file to a
  scratch path first and restore from that copy, then verify with `diff` or
  `shasum`.
- **A dataclass attribute that design mandates needs its own test.** Design
  specifies `@dataclass(frozen=True)` for the value objects, but removing
  `frozen=True` from `BenchmarkAge` left all 1834 tests green until task 1.4
  added `test_benchmark_age_is_immutable`. `Benchmark` had had this covered
  since task 1.1 — copy that pattern for every new value object.
- **Classify the function's shape before choosing a test strategy — it decides
  whether mutation-hunting terminates.** Task 1.3 oscillated for three rounds
  and needed a debug escalation; task 2.1 took four rounds but *converged*. The
  difference is structural, not effort. A **selection** function over a finite
  fixture admits infinitely many agreeing substitute keys (`min(value)`,
  `max(note)`, `max(ordinal%365)`, …), so "no mutation a reviewer can think of
  survives" is an unbounded acceptance test that closes one mutant and exposes
  the next; it terminates only by asserting the *defining property quantified
  over the fixture*. A **total function of one scalar over ordered regions** —
  a version or range guard — is exhausted by boundary + type + message +
  call-site cases, so an enumerated sweep genuinely terminates. Pick the
  strategy from the shape up front.
- **An exhaustive clause sweep is the terminating criterion, and it must
  enumerate members, not just classes.** Task 2.1's rounds 1–3 each closed a
  real defect found by guessing, and each time a new one appeared. What ended
  it was a 44-mutation sweep over every clause of the task and every AC of its
  requirements. It found the same two classes round 3 had named and zero new
  ones — but both classes had *unnamed members* (the constant gap was
  bidirectional: `= 1` survived as well as `= 7`; the ordering gap had a
  partial-move member, the guard shifted past only the *first* projection). A
  fix targeting only the named members would have forced a fifth round.
- **A test suite can pin that a guard is *called* without pinning *where*.**
  Deleting task 2.1's `check_schema_version` call died correctly, but *moving*
  it after field projection left all 1848 tests green — while changing which
  error a user sees (a field complaint instead of "your file is from a newer
  fitdocs"). Any ordering obligation (validate-before-project,
  check-before-write, guard-before-parse) needs a fixture where **both** paths
  would raise, asserting *which* error surfaces. A fixture that is valid in the
  later stage makes ordering unobservable — and task 2.1's docstring claimed
  the ordering property while using a valid field value.
- **`pytest.raises(SomeError)` is not a discriminator when the correct path and
  the mutant raise the same type.** Only message content separates them. A
  bare-raises variant of task 2.1's ordering test passed under both ordering
  mutants. Assert on the message body, and normalize the path out of it first
  (below) so the assertion cannot be satisfied by the path.
- **Never assert a bare digit against a message that embeds a path.** A pytest
  tmp dir (`.../pytest-2286/test_foo0/`) carries the session counter and always
  ends in `0`, so `assert "2" in message` and `assert "0" in message` match the
  *path*, not the body. Four such assertions in task 2.1 survived deleting the
  entire value-naming and supported-version interpolation. Fix:
  `body = message.replace(str(path), "<path>")`, assert tokens against `body`,
  and keep a separate un-normalized assertion that the path *is* named.
- **A fixture chosen to dodge that collision is by construction far from the
  boundary — one fixture cannot serve both jobs.** Task 2.1's round-1 fix moved
  the sub-minimum fixture from `0` to `-31337` and left `value < 1` mutatable
  to `value < 0` with the full suite green (version 0 silently accepted); the
  above-supported fixture at `N+997` likewise left `> N` → `> N+1` green,
  accepting the very next schema version. Keep a **distinctive** value for the
  message-content test and an **on-boundary** value (`0`, `N+1`) for the rule
  test. Once the path is normalized, on-boundary values are safe again.
- **Remediate additively; retuning an existing fixture is how coverage gets
  destroyed silently.** Every task 2.1 regression came from editing a fixture
  that was a sole pin. When a fix lands, name the do-not-modify set explicitly.
  Live example: `test_boolean_version_raises` sole-pins the
  `isinstance(value, bool)` clause **only because its fixture is `True`** —
  with `False`, deleting that clause survives the whole suite, because
  `False == 0` is caught by `value < 1` instead. `True == 1` sits inside the
  accepted range and is the only value that discriminates.
- **A rejection fixture must be order-comparable to the boundary it guards, or
  it kills type checks only by crashing.** Task 2.2's sole non-int fixture was
  the *string* `"84"`. Deleting `isinstance(value, int)` then raised an uncaught
  `TypeError` (`'<' not supported between 'str' and 'int'`) — the test went red,
  so the mutant looked killed, but nothing pinned the *rejection*. The float
  case had no test at all, and `isinstance(value, (int, float))` plus
  `return int(value)` survived `pytest`, `mypy --strict` and `ruff` **together**,
  silently truncating `benchmark_staleness_days = 84.5` to `84`. For a
  whole-number obligation the discriminating fixture is a **float**: a string
  only proves the code crashes on nonsense, not that it refuses fractions. This
  is the mirror image of task 1.2's note above, where an `int` fixture (`190`)
  hid a deleted `int()` cast and needed `190.0`.
- **Prefer a hardcoded literal path over `tmp_path` when the assertion is about
  a message.** `tests/load/test_settings.py` uses
  `_SETTINGS_FILE = Path("/vault/fitdocs.toml")`, which carries no digits, so
  the tmp-dir digit-collision hazard cannot arise there at all. The reader never
  opens the file — it only names it in messages — so no real path is needed.
  Where a real root *is* required, normalize instead (see above).
- **`git diff --numstat` showing zero deleted lines is a hard, mechanical proof
  that a change is additive.** Task 2.2 extended a module owned by a peer spec;
  `25 0` / `84 0` proves no owner fixture was retuned and the owner's 13 tests
  are byte-identical, without reading a line of the diff. Ask for it whenever a
  remediation is authorized as "additive only" — it is stronger evidence than
  any narrative claim, and it is the check that would have caught the round-2
  regression on task 2.1 immediately.
- **Writing a trap into these notes does not stop the next task walking into
  it — name the mutants that must die, as a checklist, in the brief.** Task 3.1
  reproduced the guard-before-parse ordering trap verbatim, despite it being
  recorded here twice, quoted in the implementer's brief, and the reason task
  2.1 needed four rounds: deleting `check_schema_version` from
  `__post_init__` left 1870/1870 green, and moving it after `parse_benchmarks`
  also left 1870/1870 green. The implementer's own sweep contained no mutant
  for that clause at all — half of its task's first bullet. A peer spec logged
  the same observation the same day, so this is three occurrences across two
  specs. The working hypothesis: **prose changes what an implementer writes,
  not what it tests.** What has actually worked is an explicit "these mutants
  must fail, name the killing test for each" list, which is how 3.1's
  remediation closed in one round.
- **Demand a contiguous, fully-annotated mutation table.** Task 3.1's first
  sweep reported M1–M4 and M7, silently skipping M5 and M6. A reviewer cannot
  tell an unreported mutant from an un-run one, so a gap reads as a complete
  argument. If a mutant is run, report it; if it is skipped, say why.
- **When a task's stated premise is wrong, say so rather than inventing work.**
  Task 3.1 instructed the implementer to repair prompt-flow, profile-store and
  end-to-end fixtures "that construct a profile by hand". None needed repair —
  every such fixture passes a plain dict carrying neither `benchmarks` nor
  `profile_version`, so eager construction succeeds and an absent version means
  the earliest version. The implementer reported this plainly and the reviewer
  independently confirmed it. That is the correct handling: a stale premise is
  a spec-accuracy observation, not a licence to edit fixtures that are fine.
- **A parser that accepts a wider grammar than its serializer emits makes
  merge-on-write unsafe by construction.** Task 3.2 took five rounds and a debug
  pass on exactly this. `parse_benchmarks` resolves discipline tables
  case-insensitively (deliberate, pinned by `tests/test_benchmarks.py:390`)
  while `benchmarks_to_document` emits lowercase, so an entry-level merge that
  kept the *raw* on-disk scope key and wrote fresh groups under the *canonical*
  one emitted both `[benchmarks.Run]` and `[benchmarks.run]` — and the parser
  then rejected the result as a duplicate `measured_on`. `save_profile` did not
  re-parse, so it returned success having made the file permanently unloadable.
  `Sport.RUN.value` is literally `"Run"`, so fitdocs' own spelling triggered it.
  The invariant, now in the code: **the merge base must be keyed by the parser's
  canonical identity at every level where the parser's resolution is
  non-injective — never by the raw on-disk spelling.**
- **When reviewers keep finding one more case in the same class, stop hunting
  cases and ask what makes the class finite.** What ended 3.2's oscillation was
  a closure argument, not another example: everything written comes from a copy
  of a parse-clean region plus serializer output over entries from that same
  region, so the union can only fail on a cross-term collision, which requires
  the parser's key→identity resolution to be non-injective. Scope is
  many-to-one; kind and date are exact. That *is* the bounded defect set, and
  the injective axes become negative controls.
- **A byte-length-preserving mutation can be silently discarded by a stale
  `__pycache__`.** CPython validates a `.pyc` on source mtime *and size* only,
  so an equal-length edit within the same second can leave cached bytecode in
  use: the suite runs the original code and the mutant reports as killed by
  nothing — a false PINNED. Two of one reviewer's 22 mutations hit this, and
  one became a real survivor once cleared, on the acceptance clause task 3.2
  names verbatim. Run every mutation as
  `find . -name __pycache__ -type d -prune -exec rm -rf {} + ; uv run pytest -q -p no:cacheprovider`.
- **The fold's non-list branch is where the data goes.** 3.2's canonicaliser
  concatenated colliding *list* values correctly and had a last-spelling-wins
  `else` for everything else, so two case-variant scope tables carrying the same
  unrecognized *scalar* key silently lost one — and the only test covered
  list-valued collisions. When folding two key spaces, enumerate the value
  shapes (list / mapping / scalar / absent) and decide each explicitly.
- **A docstring justifying a safety net can be false in a way that makes an
  unreachable net look load-bearing.** Four consecutive rounds shipped a false
  claim about `save_profile`'s re-parse. The net has no reachable trigger today
  (every production construction is `AthleteProfile(data=...)`, which parses in
  `__post_init__`); it guards a *future* divergence between the canonicaliser's
  duplicated case rule and `benchmarks._resolve_scope`. Verify the net fires for
  the case its docstring names — the closing reviewer did, by building a
  `bike -> Ride` alias.
- **A type declaration is pinned by nothing unless a test reads it.** Task 4.1
  shipped a green round in which three declared types could be replaced
  wholesale — `BenchmarkRef.kind: BenchmarkKind` → `str`,
  `discipline: Sport | None` → `str | None`, `AthleteField.benchmark:
  BenchmarkRef | None` → `object | None` — plus `ProfileView.benchmark`'s
  `on: date | None` → `on: date`, all four surviving pytest, `ruff` and
  `mypy --strict src/`. Two blind spots combine: `inspect.signature(...)
  .parameters` **discards annotations**, so a names-and-order test sees none of
  it, and `dataclasses.fields()` is only as strong as the attributes you read
  (`.name` without `.type` pins half). mypy cannot cover for either — it does
  not check tests (`pyproject.toml` `files = ["src"]`) and a brand-new type has
  no `src/` consumer yet. Pin declared types via
  `[(f.name, f.type) for f in dataclasses.fields(X)]` and
  `signature(m).parameters["p"].annotation`; under
  `from __future__ import annotations` these are strings, but PEP 563 stores the
  normalized AST so spacing does not matter, and `ruff UP045` forbids the one
  equivalent spelling (`Optional[date]`) — so the string compare is effectively
  a type pin here. Return annotations are the residue: widening
  `has_benchmark() -> bool` to `-> object` is invisible to all three gates
  (queued).
- **A test double that gains a Protocol member nothing calls pins nothing.**
  Python performs no static Protocol enforcement, so 4.1's whole
  `test_stub_calculators.py` addition was revertible at green. The tell was
  asymmetry: the identical addition in `test_types.py` *was* pinned, because one
  test there calls through the `ProfileView`-typed reference. Give every
  conformance-only double at least one reachability call — and check the
  mutation reds for the *right* reason: deleting the methods *and* their
  now-unused imports reds with `NameError` (the import firing), while deleting
  only the methods reds with `AttributeError` (the actual pin).
- **The repo's structural pin for a declared contract type with no `src/`
  consumer is the contributing guide's worked example**
  (`tests/test_contributing_calculators_doc.py`), which runs `mypy --strict`
  over it. Widening the pre-existing `get_number` return reds that test while
  `mypy --strict src/` stays green. The example does not yet exercise
  `benchmark`/`has_benchmark`, so both new members inherit the gap until a real
  consumer lands in task 5.x.
- **If every test shares one instance of a lookup key, the code can stop
  reading that key and stay green.** All nine of task 4.2's new tests used the
  same `BenchmarkRef(FTP_WATTS, Sport.RUN)`, so in `prompts.py` *both*
  `discipline=ref.discipline` → `Sport.RUN` and `ref.kind` →
  `BenchmarkKind.FTP_WATTS` survived at full green, in the presence check and
  the persistence call — defeating Req 8.2/8.3's "of that quantity **and**
  scope" clause with entirely correct production code behind it. The
  athlete-wide scope (`discipline=None`) was never exercised at all. When a
  struct field is a *routing key*, at least two tests must carry different
  values for it and one should be the degenerate case; otherwise you have
  pinned that the code runs, not that it routes.
- **Mutate the two call sites of a routing key separately, and choose a
  legality-preserving substitution.** Mutating read and write together, to a
  value that trips a scope guard, kills the test by *raising* — which is a real
  kill but would go quiet if the guard were ever relaxed, and observes nothing
  about where the entry landed. Mis-routing only `with_benchmark`, to a legal
  kind/scope pair, is what proves the persisted location is asserted: it reds
  `assert hr_entry is not None` as a sole failure.
- **Name the assertion a mutation reddens, never the narrative path.** Task
  4.2 shipped "the field would be prompted and reported still missing" for a
  mutation that actually reds with `IndexError: pop from an empty deque` —
  invalidated by round 2's own addition of a second field to that same test.
  Which observable fires depends on how many answers the fixture queues, so the
  route is not a durable claim; the sole-failure fact is.
- **A mutation applied by string replacement can land in a docstring.**
  Verifying 4.2's predicate swap, the parent's `replace(old, new, 1)` hit
  `prompts.py:82` — prose describing the predicate — instead of the call at
  `:111`, and the suite stayed green, reading as a survivor. It was caught only
  by diffing the mutated file. Anchor mutations by line number and assert the
  line's content first, then diff before trusting a green result. Same failure
  class as [[__pycache__]] staleness: the mutant was never really applied.
- **Task 5.1 closed with zero code changes, and that is the designed outcome,
  not a skip.** `training-load` task 4.1 landed `contract.document_date`
  (`src/fitdocs/contract.py:456`) with the signature 5.1 pins character-for-
  character, exported at `contract.py:115`; exactly one reader exists, so 5.1's
  fallback branch is dead; `engine.py:401` already consumes it and nothing in
  `src/fitdocs/load/` reads the frontmatter date another way; all five Observable
  cases are covered in `tests/test_contract.py:564-614`; and the `wiki-contract`
  revalidation clause is already recorded at that spec's `design.md:87-93` item
  5. Verified rather than assumed: 11 line-anchored mutations, zero survivors —
  9 on `document_date` and 2 on `AthleteProfile.benchmark`'s undated guard.
  Req 3.6 and 3.7 are both PINNED, 3.7 in two modules (the reader for date
  resolution, `profile.py:160` for `benchmark(on=None)`).
- **`date.today()` is caught twice over, and the second guard is the durable
  one.** `tests/test_contract.py::test_contract_performs_no_io_and_reads_no_clock`
  is a module-level invariant that reddens on *any* clock read, so mutating
  either of `document_date`'s absent-value returns to `date.today()` dies both
  by its case-specific test and by that guard. A module-scoped invariant is
  worth more than N case assertions: it covers the case nobody wrote a test for.
- **Task 5.2 needed almost no work, and the reason is worth recording: check
  the tree before trusting a task's own description of what is missing.** Its
  entire engine wiring had already landed with `training-load`'s Amendment 3
  (settings read once at `engine.py:267-271`, `document_date` at `:401`,
  `LoadContext` at `:503`), and that spec had also already shipped the
  malformed-`[load]`-aborts test *and* the undated-document test
  (`c5ee9f3`). The parent session asserted the undated case was uncovered; the
  implementer checked with `git log -S` and `git merge-base --is-ancestor`,
  found the test, and strengthened it instead of adding a duplicate. The only
  genuinely new coverage 5.2 owed was `benchmark_staleness_days` surviving the
  trip from `fitdocs.toml` to `compute` — the pre-existing echo test asserted
  `default_calculator`, which is a different spec's field.
- **A substring assertion on the trailing field of a composed string is a
  prefix match.** `assert "staleness=30" in basis` passed with the context
  carrying **300** — measured, whole suite green — because `staleness=` is the
  last field and nothing delimits its value. `basis.endswith("staleness=30")`
  reds that mutation as a sole failure. Whenever you assert against a
  concatenated diagnostic string, anchor the end or compare the whole thing.
- **A test's docstring citing several requirements is a coverage claim, and it
  is usually wrong.** 5.2's new test cited Req 2.9, 5.5 and 8.2 while being
  structurally unable to fail on any of them: its stub declares no athlete
  fields (no prompt path), its `[load]` table is valid (no abort path), and it
  never writes `athlete.toml`. It pins Req 7.3. Cite the requirement the
  assertions can actually redden, and name where the others are covered.
- **A mutation that removes a subclass from an `except` tuple listing its
  parent is inert, and reads as a coverage gap.** `ProfileError` subclasses
  `AthleteFileError` (`profile.py:92`, `athlete.py:51`) and `cli.py:580-585`
  catches both, so dropping `ProfileError` alone leaves the whole suite green.
  Task 5.3's round-1 reviewer measured exactly that and concluded "Req 2.9 is
  unpinned suite-wide"; the implementer refuted it from the class hierarchy and
  two later rounds confirmed the refutation by measurement. Before reporting a
  survivor as a coverage gap, ask whether the mutated clause is *reachable* —
  a redundant `except` entry, a guard implied by an earlier one, a default
  another layer also supplies. Same family as the stale-`__pycache__` false
  PINNED, opposite sign: there the mutation never applied; here it applied and
  could not matter.
- **"That other test proves the abort" is a coverage claim, and each abort
  *site* needs its own pin.** Task 5.3 shipped this defect twice in one task.
  A CLI fixture with no calculator registered writes nothing whether the pass
  aborts or runs to completion, so `read_bytes() == before` is vacuous — and
  `load_profile` (`engine.py:266`) and `load_load_settings` (`:269`) are
  different call sites, so a test covering one says nothing about the other.
  Deferring `load_profile` past the document loop left all 2010 tests green.
  The fix, verified twice: register a stub calculator and set
  `default_calculator` so the document is genuinely rewritten on the valid
  path, then assert the computable-and-uncomputed *precondition*. If you have a
  byte-identity assertion in a CLI abort test, it is probably vacuous now.
- **Verify a preserved pin by re-running its mutation, never by reading the
  source.** Task 5.3's round-3 report certified four pins as intact because the
  assertions were "still present verbatim" — but the fixture around them had
  changed, which is precisely how this spec has lost coverage before
  (`tasks.md` notes on additive remediation). The round-3 reviewer re-ran all
  four and they held; the point is that reading could not have established it.
- **"Requirement X is pinned by test Y" is itself an untested claim, and it kept
  being false the same way — four rejection rounds across three tasks.** Tasks
  5.3 (twice), 6.1 and 6.2 (twice) each shipped a citation naming a test that did
  not cover the sentence it was attached to; in 6.2 the *replacement* citation
  written to fix a false citation was also false. The mechanism is always the
  same: a **multi-clause requirement gets glossed by whichever clause the author
  has in mind**, and a test covering a neighbouring clause is then cited as
  covering the quoted one. It reads perfectly and measures false. Before writing
  "pinned by Y", run the mutation that should kill Y and confirm Y is in the
  failure set; if the requirement has more than one clause, split it and classify
  each clause separately. Task 6.2's final docstring is the model — readability
  clause PINNED with its killing mutation named, prohibition clause UNPINNED with
  the mutation that proves it and a pointer to the queue item.
- **That discipline is what found the feature's one real coverage hole.** Req
  1.11's prohibition half — flat athlete-input keys must never be derived,
  overridden or reinterpreted from benchmarks — is pinned by nothing: making
  `load_athlete_inputs` prefer a benchmark entry leaves all 2012 tests green, and
  a probe returns 200 for flat `max_hr_bpm = 188` plus a benchmark of 200. No
  fixture anywhere pairs a flat key with a `[benchmarks]` table. Queued as
  `2026-07-27-req-1-11-prohibition-unpinned`.
- **Never cite `main` in a durable artifact — cite the merge-base SHA.** Task
  6.2's docstring named `git rev-parse main:tests/render == HEAD:...` as its proof
  that the feature edited no golden file. True when written; **false two hours
  later**, because a peer merged `4880a6c`, which regenerated
  `tests/golden/*.json`. Two of three tree pairs then returned NOT EQUAL and a
  reader running the cited command would conclude the opposite of the truth. The
  substance held throughout against the real merge-base `17ff340`. On a repo with
  concurrent sessions `main` is a moving ref, and any comparison pinned against it
  has a half-life measured in hours.
- **A mutation recipe written into prose must be reproducible verbatim.** 6.2's
  first wording of the Req 1.11 probe said the mutation falls back to the flat key
  "only when the benchmarks table is absent". Implemented literally that raises
  `KeyError: 'athlete'` on three fixtures whose `benchmarks` table has no athlete
  scope — crashes, not the prohibition being caught — so a next editor would
  conclude something *does* pin the clause. Word the recipe as the guard you
  actually ran, then run it from your own text.
- **The mandated prose-claim grep has a hole, and it passed clean on a file that
  contradicted itself.** At the time of task 6.1, `change-protocol.md`
  prescribed grepping changed tests for
  `verified|caught|proven|tracked|regardless|always|never|impossible`. That
  vocabulary returned 8 hits, *all* genuinely factual, while the three
  actually-false claims used none of those words — they said "stand on their
  own mutation **evidence**", "**implicit**: apply_load completed without
  raising", and "**immediate**, loud test failure". One of them directly
  contradicted the submission's own UNPINNED declaration. `change-protocol.md`
  has since widened the vocabulary further (read the current pattern there,
  not the one quoted above — it has moved twice since and this note would go
  stale again if it tried to keep its own copy) and now says plainly, in
  steering, that a clean grep is not evidence a claim is true: the only real
  check is re-running or deleting every sentence asserting what a test would
  catch, whether or not it matched.
- **A section-6 validation task cannot produce suite-wide sole failures, and
  should not claim them.** Task 6.1's eight mutations each redden 2–14 tests,
  because every line they touch is already pinned by tasks 1.x–5.x. The property
  that actually matters is different: the new test must never *survive* while
  its siblings die. Report the measured failure set and that property; do not
  write "sole failure" without the qualifier.
- **Two mutually redundant guards make a real behavior unpinnable by any
  single-line mutation.** Task 6.1 could not pin its second-pass byte-identity
  assertion, and the structural reason is that `apply_frontmatter_load`
  (`docedit.py:287`) strips managed lines *and* the engine strips them again at
  `engine.py:402`; deleting either leaves the suite green. That is an honest
  UNPINNED declaration, not a test defect — and it is distinct from a *vacuous*
  assertion, because a separate assertion proves the documents were genuinely
  recomputed. When you hit an unpinnable clause, prove the redundancy rather
  than asserting unpinnability, and say where the behavior *is* covered.
- **An identity assertion comparing two runs of the same code is unpinnable for
  its own reason**: any deterministic mutation perturbs both sides equally, so
  the equality survives. Do not attribute that to whatever structural redundancy
  explains a neighbouring assertion.
- **Check that a mutation lands on the clause the task's boundary owns.** Task
  5.3's round-3 evidence for the `ProfileError`/`AthleteFileError` route was
  gathered at `engine.py:_CONFIG_ERRORS` (an engine-boundary per-document
  guard), not the `cli.py:580-585` tuple `_Boundary: CLIErrorSurface_` owns —
  two distinct clauses whose sole failures are different tests. The property
  held when the reviewer mutated the right clause, but the report's citation
  would not have supported it.
