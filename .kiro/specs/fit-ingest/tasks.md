# Implementation Plan

- [x] 1. Foundation: package skeleton, activity model, and synthetic fixtures
- [x] 1.1 Set up the installable package project and quality tooling
  - Create the uv-managed Python 3.11+ project in src layout with the FIT parsing SDK (>= 21.208.0) as the only runtime dependency and pytest/ruff/mypy in the dev group
  - Configure strict type checking over the package source and lint/format per steering; no console entry point (owned by workout-docs)
  - Observable: dependency sync, an empty test run, lint, and strict type check all complete cleanly from a fresh checkout
  - _Requirements: 13.1_
- [x] 1.2 Define the versioned activity model contract
  - Immutable typed model for activities: provenance, session summary, laps with sample index ranges, parallel sample channels, strength sets, devices, normalized sport/modality labels, indoor flag
  - Schema version constant stamped on every activity; FIT epoch constant plus the shared FIT-epoch-to-UTC conversion helper (stdlib-only, timezone-aware) that all extractors apply; every device-omittable field optional with None (never zero) for absent data; tuples for all sequences
  - Observable: the model module imports without any internal or FIT-SDK dependency and passes strict type checking
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 12.3_
- [x] 1.3 Build deterministic synthetic .fit fixtures
  - Test-support builder that encodes synthetic activities with the SDK encoder: outdoor run (GPS, HR, cadence, laps), ride (power, HR, cadence), strength session (sets with deliberately missing fields), minimal file without a session message, and corrupt variants (non-FIT bytes, truncated file)
  - A bad-message variant crafted to produce message-level decoder errors while still decoding overall; if crafted bytes cannot coax the SDK into message-level errors, cover that path by stubbing the decoder read result instead (same fallback spirit as the encoder caveat)
  - Fixed timestamps and series so outputs are reproducible; verify encoded fixtures pass the SDK integrity check (research follow-up), falling back to committing the generated synthetic binaries if encoding gaps appear
  - Observable: pytest fixtures hand valid .fit bytes for run/ride/strength/minimal cases to any test
  - _Requirements: 13.2_

- [x] 2. Implement FIT decoding and validation with a typed error taxonomy
  - Accept a file path or raw bytes; distinct descriptive errors for non-FIT input vs integrity failure; reference decode flags with raw datetime handling; reset the stream between validation and read
  - Collect message-level decoder errors as strings instead of raising; compute the content hash of the source bytes; never modify the source file
  - Observable: random bytes raise the non-FIT error, a truncated fixture raises the integrity error, a valid fixture returns all message lists plus hash, and the bad-message fixture (or stubbed equivalent) yields non-empty collected errors
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.3_

- [x] 3. Extract normalized data from decoded messages
- [x] 3.1 (P) Extract per-sample channel arrays
  - Parallel equal-length arrays for time offset, heart rate, power, cadence, speed, distance, altitude, position, temperature with None holes preserved across channels
  - Prefer enhanced speed/altitude variants; convert semicircle coordinates to degrees; normalize units; store raw values without smoothing; drop only records lacking a timestamp; return absolute record timestamps for later lap projection
  - Observable: record dicts with gaps produce aligned arrays with None exactly at the gaps
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - _Boundary: RecordExtractor_
- [x] 3.2 (P) Extract session summary, activity fallback, and device info
  - Session summary fields exposed with None for anything unrecorded; fall back to activity-level totals when no session message exists; devices deduplicated keeping the last report per device with battery status and identifiers
  - Observable: session-less fixture messages yield a summary with fallback totals and all other fields None
  - _Requirements: 4.1, 4.2, 4.5_
  - _Boundary: SummaryExtractor_
- [x] 3.3 (P) Project laps onto sample index ranges
  - Inclusive start/end sample indices derived from matching lap start times against record timestamps; laps that match no records keep their summary with a None index range
  - Tests use hand-constructed record-timestamp tuples per the design contract; integration with the record extractor is verified in the composition task
  - Observable: a three-lap fixture yields non-overlapping inclusive ranges covering every record
  - _Requirements: 4.3, 4.4_
  - _Boundary: LapProjector_
- [x] 3.4 (P) Extract strength sets faithfully
  - One entry per set message in recorded order: set type, start time, duration, repetitions, weight, category; any unrecorded field stays None and recorded zeros (bodyweight) are preserved
  - Resolve exercise names via the SDK profile category/subtype lookup, refined by exercise-title messages when a structured workout provides them; unresolvable names stay None; activities without sets yield an empty collection without error
  - Observable: the strength fixture yields sets with resolved names where resolvable and None for every unrecorded field
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 12.3_
  - _Boundary: SetExtractor_
- [x] 3.5 (P) Detect sport, modality, and indoor flag
  - Normalized sport labels per the reference map with Workout as the never-failing fallback for unknown or absent sports; exactly one modality per activity with strength training winning over the sport mapping; machine-bound indoor sub-sports flagged; session values preferred over sport messages
  - Observable: table-driven cases pass for every mapped sport, unknown-sport fallback, strength modality, and treadmill indoor flag
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - _Boundary: SportDetector_
- [x] 3.6 Expose session-scoped developer fields
  - Extend the frozen activity model with the read-only name-to-raw-value developer-field mapping (empty when absent, never a fabricated entry) and build it by applying the described field names from field description messages to the decoded session message
  - Values pass through as decoded with array values preserved as tuples (a 16-entry identifier stays a 16-entry tuple); no interpretation, derivation, or renaming of described field names
  - Sequential after 3.2 — extends the same summary-extractor module (not parallel-safe); the model addition is additive-only
  - Observable: message dicts with field descriptions yield a mapping keyed by the described names with raw values, and message dicts without them yield an empty mapping
  - _Requirements: 14.1, 14.2, 14.3, 14.4_
  - _Boundary: SummaryExtractor, ActivityModel_
  - _Depends: 1.2, 3.2_

- [x] 4. Compose the public parsing entry point
  - Wire decoding and all extractors into one call that returns a frozen activity: extractors apply the model-owned epoch conversion helper (this task creates no conversion logic), activity start-time policy (session start, else first record), provenance carrying hash/path/decoder errors, schema version stamped
  - Purely composes — performs no extraction logic and no writes, prompts, or network access
  - Observable: parsing each synthetic fixture returns a complete activity with correct sport, modality, laps, sets, and provenance
  - _Requirements: 1.1, 1.4, 2.1, 2.2, 2.3, 2.4, 13.1_

- [x] 5. Compute derived metrics as pure functions
- [x] 5.1 Define metric input and result contracts
  - Caller-supplied athlete inputs (thresholds and zone dividers) all optional; zone specification validates ascending dividers and fails fast on malformed input; result type with every metric independently None-able
  - Observable: malformed zone dividers raise at construction; all contracts pass strict type checking
  - _Requirements: 10.4, 12.1_
  - _Boundary: MetricTypes_
- [x] 5.2 (P) Compute motion, heart-rate, power, and cadence aggregates
  - Session-recorded values preferred with channel-derived fallbacks via one shared helper: moving time (timer total, else documented speed/distance heuristic), elapsed time, distance, average pace, average/max speed, HR, power, cadence
  - Every metric None when inputs are missing while independent metrics still compute
  - Observable: hand-computed unit cases pass, including None propagation for absent channels
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 12.1, 12.2_
  - _Boundary: AggregateMetrics_
- [x] 5.3 Compute elevation, temperature, and calories metrics
  - Elevation gain/loss from session totals, else smoothed-altitude deltas per the documented boxcar heuristic; min/max altitude; temperature min/max/avg; calories passthrough only, never estimated
  - Sequential after 5.2 — extends the same aggregate-metrics module and shared helper (not parallel-safe)
  - Observable: smoothing-fallback and passthrough unit cases pass, with None for absent channels
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 11.3_
  - _Boundary: AggregateMetrics_
- [x] 5.4 (P) Compute advanced power and heart-rate series metrics
  - Normalized power per the documented formula (1 Hz resample with coasting as zero, 30-second trailing mean, fourth-power mean, None below 30 seconds of data); intensity factor only with caller-supplied FTP; variability index; efficiency factor by modality (power for bike, speed for run); aerobic decoupling across activity halves with None when either half lacks paired data
  - Observable: constant 200 W with FTP 200 yields NP 200 and IF 1.0; a variable series yields NP above average power; a constructed drifting series yields positive decoupling
  - _Requirements: 8.4, 8.5, 8.6, 8.7, 8.8_
  - _Boundary: PowerSeriesMetrics_
- [x] 5.5 (P) Compute time-in-zone occupancy
  - Generic band occupancy over any channel given ascending dividers: inter-sample duration attributed to the earlier sample's band, None-valued samples contributing to no band, arbitrary band counts, and no embedded default boundaries
  - Observable: constructed series occupancy matches hand computation including None exclusion
  - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - _Boundary: ZoneMetrics_
  - _Depends: 5.1_
- [x] 5.6 (P) Compute training stress metrics
  - Banister TRIMP per the documented formula (clamped heart-rate reserve per sample pair) requiring caller-supplied resting and max HR; power TSS per the documented formula from normalized power, moving time, and FTP; None whenever thresholds are missing; no methodology-based load of any kind
  - Observable: a worked TRIMP example and the one-hour-at-FTP TSS 100 case both pass
  - _Requirements: 11.1, 11.2, 11.4_
  - _Boundary: StressMetrics_

- [x] 6. Compose the metrics facade and public package surface
  - One-call derivation of the full metric set wiring aggregates, series metrics, zone occupancy (HR and power directly, pace derived per sample from speed), and stress metrics; time-in-zone None when boundaries or channel are absent; never raises for missing data
  - Package root exports the parse entry point, the metrics facade, model types, and error types as the public API
  - Observable: computing metrics over fixture activities with and without athlete inputs flips only threshold-dependent fields between values and None
  - _Requirements: 8.5, 10.1, 10.5, 11.1, 11.2, 12.1, 12.2, 13.3_

- [x] 7. Validation: golden files, determinism, and quality gates
- [x] 7.1 Golden snapshot suite over all fixtures
  - Parse and compute metrics for each synthetic fixture, serialize deterministically, and compare against committed JSON snapshots; snapshots (not binaries) live in the repo
  - Observable: golden tests pass for run, ride, strength, and minimal fixtures
  - _Requirements: 2.1, 13.2_
- [x] 7.2 Determinism, immutability, and full quality gates
  - Parse and compute twice over identical bytes and assert identical serialized results; assert the source file's bytes are unchanged after parsing; full test suite, lint, and strict type check all green
  - Observable: the complete suite passes with strict typing from a clean checkout
  - _Requirements: 1.5, 13.1, 13.2, 13.3_

> **Tasks 1–7 are the first pass and are complete.** Tasks 8–13 are Amendment 1
> (2026-07-26, design revised 2026-07-27): primary sourcing for every constant a
> reported metric is computed from, the citation record in code, the selectable
> training-impulse weighting, and correcting written documents by regeneration.
> No first-pass unit is rewritten. Amendment 2 (Requirement 14.2) is already
> implemented inside task 3.6 and adds no task here.

- [x] 8. Amendment 1 foundation: the shared citation vocabulary and the weighting selection contract
- [x] 8.1 Define the shared citation vocabulary at the bottom of the dependency graph
  - New dependency-free vocabulary module holding the record types any fitdocs layer states a number's origin in: the three-member verification status (keeping the secondary-attestation member the layer above uses), a published-work citation, a fitdocs-choice record carrying justification and search basis in place of authorship, the sealed two-member union of those two, a corroborating-work record carrying its own locator and an agrees/omits/differs relation, a deliberate-departure record, and the binding that ties a value to exactly one governing source plus any number of corroborators and the value it replaced
  - Imports nothing internal and never imports the FIT SDK; holds no arithmetic and no records — shapes only, so both the metrics layer below and the load layer above can depend on it
  - The fitdocs-choice record carries no field that can hold the primary-text status, so conflating a chosen value with a sourced one is unrepresentable rather than review-caught
  - Add this vocabulary's own test module to the type-check perimeter in the packaging config in this same change — that config names its checked test modules explicitly and says so, and the observable below is a type-check *result*, so a module the checker never reads would satisfy it vacuously
  - Observable: the module imports standalone with no internal import, passes strict type checking, and annotating a fitdocs-choice record with the primary-text status fails the type check rather than constructing — demonstrated from a module the checker actually reads
  - _Requirements: 15.2, 15.8, 15.9, 16.1, 16.4, 16.5, 16.6, 16.7_
  - _Boundary: CitationVocabulary_
- [x] 8.2 Re-point the load layer's citation types to the shared vocabulary
  - Delete the verification-status and citation *definitions* from the load-channels source module and import them from the shared vocabulary, re-exporting both so every existing import path keeps working; that module's divergence type, its six records, every status, note and table stay byte-identical
  - Explicit cross-boundary task: the module belongs to load-channels and this change is import-only — it confers no ownership and alters no record, status or obligation of that spec
  - Observable: the load-channels citation test module passes with no edit to it anywhere in this task's diff, and exactly one definition of the verification status exists in the tree
  - _Requirements: 16.1_
  - _Boundary: CitationVocabulary, load.channels.sources_
  - _Depends: 8.1_
- [x] 8.3 (P) Add the training-impulse weighting selection to the caller-input and result contracts
  - Weighting-selection enumeration in the metric types module with one member per fitted curve the cited text publishes, named for the curve rather than for the athlete; the caller-input record and the derived-metric result each gain an optional selection field defaulting to absent
  - The metric types module stays stdlib-only and citation-free: the selection *vocabulary* lives here while each selection's *values* live with the records, which is what keeps the caller-facing contract clear of the provenance layer
  - The selection reaches the library only through caller-supplied inputs — nothing in the metrics layer reads a profile or a configuration file
  - The member *names* are an open maintainer decision, not a settled one — they are flagged in `spec.json`'s open-decisions record and in `.kiro/queue/2026-07-27-trimp-weighting-default-is-sex-named.md`, and Req 17.6 puts the name in every rendered document. Implement the design's choice, and treat a later rename as expected rather than as rework; nothing downstream may pin behavior to the *name* (see task 11's value-pinned regression)
  - Parallel-safe with 8.1 and 8.2: no data dependency and a disjoint file set
  - Two contract pins move with the added field and must be updated in this task, not discovered by the suite: the derived-result field count and its exact name-and-type list, and the caller-input record's equivalent pin
  - Regenerate the committed model-and-metric snapshots for the added result field alone, landed as its own commit so the later value-moving change shows a diff of values only
  - Observable: each snapshot gains the new result key in **both** of its metric blocks — every golden file carries a no-athlete and a with-athlete block, so the diff is two added keys per file, not one — each carrying the absent value at this stage, and the full suite is green
  - _Requirements: 17.2, 17.3, 17.6_
  - _Boundary: MetricTypes_

- [x] 9. Amendment 1 sourcing: one record per source, one record per constant
- [x] 9.1 Transcribe and verify the published-work records
  - One citation record per publishing work the design's resolved classification names — the training-impulse book chapter, the corroborating journal paper, and the training-stress manuscript already identified and shipping one layer up — each carrying authors, year, work, locator and the primary-text status
  - Machine-local prerequisite, like the data-root file: neither text is redistributable and neither is committed, so the page scans and the publisher PDF exist only at the root of the maintainer's primary checkout and a fresh worktree has neither. Make them reachable before starting
  - **If they cannot be reached, stop and escalate — do not write the records against the committed extraction instead.** That extraction is evidence that a prior session read the texts, not a substitute the implementer may quietly accept: Req 15.1 requires the value to have been read from the work's own text, Req 15.5 forbids naming any working document under the reference directory as a constant's source, and Req 15.4 makes an unverifiable constant *block* rather than ship under a weaker status. Whether a prior reading discharges 15.1 is the maintainer's ruling, not this task's
  - Re-verify every locator against the text it names rather than against the design's table; a locator that does not check out blocks this amendment rather than being downgraded to a secondary attestation
  - Each record names the published work itself; no record, note or comment names any working document under the reference directory, which is where the extraction lives but is not what a constant is cited to
  - Note on the chapter's record that its year is the one element resting on the catalogue entry rather than on the book's own pages
  - Observable: each record's locator has been opened in the named text with the value it is cited for present there, and the records module imports and reads without computing any metric
  - _Requirements: 15.1, 15.2, 15.4, 15.5, 16.1, 16.6_
  - _Boundary: MetricsSources_
  - _Depends: 8.1_
- [x] 9.2 Record the three values no published work defines as fitdocs' own choices
  - One fitdocs-choice record each for the minimum power-stream span below which normalized power is refused, the moving-time movement threshold, and the altitude-smoothing window, each stating why this value and — where the choice rests on one — the measurement supporting it
  - Each also records what was searched and what was found, so "no published work defines this" stays an evidenced conclusion rather than becoming a cheaper answer than obtaining a text that exists
  - Sequential after 9.1 — same records module, not parallel-safe
  - Observable: all three records carry a non-empty justification and search basis, none carries a published-work status, and none names a working document under the reference directory
  - _Requirements: 15.5, 15.8, 15.9, 16.4, 16.6, 16.7_
  - _Boundary: MetricsSources_
  - _Depends: 9.1_
- [x] 9.3 Bind every covered value to its record
  - One cited constant per value the enumeration names — the training-impulse coefficient and exponent, the training-stress scale, the rolling-window width, the averaging exponent, the minimum span, the movement threshold and the smoothing window — each with exactly one governing source, with the corroborating work and its own locator and agrees/omits relation where the enumeration names two works, and with the value it replaced recorded wherever a text moved one
  - The coefficient and the exponent are instantiated once per fitted curve the selection offers, since the resolver may return either and every term a pair holds must also appear in the registry
  - The registry tuple naming them all, with unique names
  - Sequential after 9.2 — same records module
  - Observable: the registry names every value the enumeration lists, each bound to exactly one governing source, and importing it computes nothing
  - _Requirements: 15.3, 15.6, 16.2_
  - _Boundary: MetricsSources_
  - _Depends: 9.2_
- [x] 9.4 Resolve the weighting selection and record the deliberate departures
  - The weighting pairs keyed by selection, each holding the cited coefficient and exponent for that curve; the default pinned to the pair applied before this amendment; and a resolver total over a stated-or-absent selection that rejects an unrecognized one by naming it and every selection the source defines rather than substituting a pair
  - The departure table: applying one sex's fitted curve to every athlete who states nothing, integrating every consecutive sample pair where the texts sum over segments of near-constant heart rate, and shipping the chapter's coefficient over the paper that prints the weighting without one
  - Sequential after 9.3 — same records module; also needs the selection vocabulary from 8.3
  - Observable: the resolver returns the pre-amendment pair for an absent selection, an unrecognized selection raises an error naming every defined selection, and each departure states what the source specifies, what fitdocs does, and why
  - _Requirements: 16.5, 17.1, 17.2, 17.4_
  - _Boundary: MetricsSources_
  - _Depends: 8.3, 9.3_

- [x] 10. Metric modules read their constants from the records
- [x] 10.1 (P) Read the moving-time threshold and the altitude-smoothing window from their records
  - The movement threshold is a bare literal inside the moving-time fallback today — promote it to a named constant read from its record, since a movement threshold carries a methodological choice and is not exempt; point the altitude-smoothing window at its record too
  - Rewrite the module docstring and both constants' documentation to name their records instead of the working reference document
  - Observable: no numeric literal for either value remains in the module, the existing aggregate tests pass unchanged, and reported moving time, elevation gain and elevation loss are identical to before
  - _Requirements: 7.1, 9.1, 9.2, 15.1, 15.5, 15.6, 15.8_
  - _Boundary: AggregateMetrics_
  - _Depends: 9.3_
- [x] 10.2 (P) Read the normalized-power window, averaging exponent and minimum span from their records
  - The averaging exponent is two inline literals today — the fourth power and its root — so collapse them into one cited constant with the root taken as its reciprocal, making it impossible for the pair to drift apart; point the window width and the minimum span at their records
  - Rewrite the module docstring to name the records instead of the working reference document
  - No behavior change in this task: the rolling mean's start condition is a separate, value-moving unit
  - Observable: no numeric literal for any of the three remains in the module, and normalized power over the existing tests is unchanged to full precision
  - _Requirements: 8.4, 15.1, 15.5, 15.6, 15.8_
  - _Boundary: PowerSeriesMetrics_
  - _Depends: 9.3_
- [x] 10.3 (P) Read the training-stress scale and the default weighting pair from their records
  - The training-stress scale and both training-impulse weighting terms come from records; the weighting terms are read through the default pair so this module's signature is unchanged — threading a caller's selection is the integration unit that follows
  - Rewrite the module docstring to name the records instead of the working reference document, and drop its "sex-neutral" characterisation of the weighting, which the departure table now carries properly
  - Observable: no numeric literal for the scale, coefficient or exponent remains in the module, and both training-impulse and training-stress values over the existing tests are unchanged to full precision
  - _Requirements: 11.1, 11.2, 15.1, 15.5, 15.6_
  - _Boundary: StressMetrics_
  - _Depends: 9.4_

- [x] 11. Thread the caller's weighting selection from input to reported metric
  - Explicit integration task across the stress module, the metrics facade and the package surface: the training-impulse function takes a resolved pair and returns the value together with the selection that produced it, so no code path yields a training-impulse number without its weighting, and the facade unpacks both fields from that one result rather than deciding either itself
  - The facade resolves the caller's selection exactly once, before any metric is computed, and resolves it unconditionally — an unrecognized selection is a caller error that must fail loudly even when the heart-rate thresholds are absent and the metric would be absent anyway, while an absent selection defaults rather than erroring
  - The absent-threshold check still precedes any use of the pair, so the metric is absent under every selection when resting or maximum heart rate is missing
  - Export the selection type from the package root and extend the public-surface pin, since a caller cannot state a selection it cannot import. The published prose copy of that surface in the plugin docs is *not* guarded by any test and goes stale silently — update it here
  - Sequential after 10.3 — re-enters the same stress module. The claim that the facade is its only caller holds for `src/` **only**: the stress and facade test modules call the training-impulse function directly at roughly sixteen sites, every one comparing the result against a float, so migrating them to the new return shape is part of this task and not a discovery for the implementer
  - **The green-making trap.** The facade test asserts that every derived field *except* a named threshold list is identical with and without athlete inputs. The new weighting field now differs between those two calls, so that test reddens — and the cheapest fix, reporting the default weighting unconditionally, passes it while destroying the invariant this task exists to establish (the field is non-absent exactly when the metric is). Add the field to the threshold list; do not widen the reporting
  - Regenerate the committed snapshots: every one carries a non-absent training-impulse value in its with-athlete block, so the weighting field flips from absent to the default there while staying absent in the no-athlete block — that asymmetry across the two blocks is itself the 17.6 invariant made visible, and is worth reading rather than accepting
  - Observable: the two selections produce different training-impulse values for the same samples; stating no selection reproduces the pre-amendment value exactly, pinned by value rather than by member name so a later rename cannot weaken it; an unrecognized selection raises an error naming every defined selection; and the reported weighting is present exactly when the metric is
  - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6_
  - _Boundary: StressMetrics, MetricsFacade, PublicAPI_
  - _Depends: 9.4, 10.3_

- [x] 12. Make an uncited or dishonestly classified constant fail
- [x] 12.1 Guard the record set
  - Registry assertions over the records: every value the enumeration names present and classified; names unique; no record in this layer carrying the secondary-attestation status; every primary-text citation carrying a non-empty locator; every fitdocs-choice record carrying a non-empty justification and search basis; the selections and the weighting pairs corresponding one-to-one with every term a pair holds also present in the registry; departure subjects unique with every field populated; the records readable without computing a metric
  - The corroboration assertions the two-works criterion turns on: both weighting terms carry the corroborating work with a non-empty locator, the coefficient's relation is *omits* and the exponent's is *agrees*, every non-agreeing corroborator carries a note, no corroborator repeats its own constant's governing source, and no fitdocs-choice constant carries corroborators at all
  - This deliberately asserts *coverage* rather than the design's stricter "exactly once", because 9.3 instantiates the weighting terms once per fitted curve — a known seam between the design and Req 15.6, open at `.kiro/queue/2026-07-28-weighting-terms-appear-twice-in-registry.md`. The guard as written is therefore weaker than the design it implements, and completeness is half of what makes an unregistered constant fail; if that item is ruled before this task runs, tighten the assertion to match the ruling
  - Observable: dropping the corroborating work from either weighting term, or flipping the coefficient's relation to *agrees*, reddens a named assertion and ideally nothing else
  - _Requirements: 15.2, 15.4, 15.6, 15.8, 15.9, 16.2, 16.5, 16.6_
  - _Boundary: ConstantGuard_
  - _Depends: 9.4_
- [x] 12.2 (P) Guard the literal surface of the metric modules
  - Parse the three metric modules and collect every numeric literal; each must either be read from a cited constant or appear in an explicit exemption list whose entries each name the literal, its site, and the reason it carries no methodological choice — a unit conversion, an arithmetic identity, or a percentage scaling following from a definition already cited
  - Assert the exemption list holds no unused entries, so it cannot quietly accumulate an over-broad entry and re-open the hole this guard exists to close
  - One further assertion that the reference directory is named nowhere under the metrics package — not in a docstring, not in a comment — since the extraction document lives there and is not what any constant is cited to
  - Parallel-safe with 12.1: a separate test module with no shared state, though it needs the re-pointed modules from 10.1–10.3
  - Observable: the scan passes on the tree as shipped, a bare numeric literal inserted into a metric module reddens it, and removing one exemption entry reddens it — a guard never shown to fail is not a guard
  - _Requirements: 15.5, 15.7, 16.3_
  - _Boundary: ConstantGuard_
  - _Depends: 10.1, 10.2, 10.3_
- [x] 12.3 Reproduce each cited work's published worked example
  - For every constant classified as read from a published work, a test reproducing a worked example that work publishes, with the source, the inputs and the expected result recorded in the test itself; where the work publishes none, the test says so explicitly rather than inventing one
  - The training-impulse chapter is a trap rather than an omission: all three worked examples printed in its figure captions contradict its own equation and one is not even internally consistent, so that example is computed from the formula under test and labelled as computed, citing the text for the formula and explicitly not for the numbers, with a comment recording why the captions were not used
  - Read the exponential base as *e*, not as the value the chapter misprints for it
  - Observable: the manuscript's own intensity-factor example reproduces exactly, and the training-impulse test states in the file that its expected number is computed rather than quoted
  - _Requirements: 15.1_
  - _Boundary: StressMetrics, PowerSeriesMetrics_
  - _Depends: 10.2, 10.3_

- [x] 13. Bring normalized power into conformance and correct already-written documents
- [x] 13.1 Emit only complete rolling windows in normalized power
  - The trailing rolling mean averages a partial window over the leading points today; the cited step specifies a rolling average of the full width, so the series now starts at the first index where a complete window exists and the power mean is taken over that series alone
  - This is the only value-moving change in the amendment (a constant-power stream is unaffected, since the fourth-power mean of one repeated value equals itself under either algorithm): dropping the leading partial-window averages moves normalized power, and with it intensity factor, variability index, training-stress score and cycling efficiency factor, in whichever direction those dropped windows' mean fourth power differs from the retained series' — rising when the dropped windows sit below it (the common warm-up shape), falling when the activity opens at or above its own overall intensity. `tests/metrics/test_power.py` asserts the rise directly (`test_normalized_power_complete_window_raises_np_over_partial_window`); the fall is documented and its complete-window value exactly pinned by `test_normalized_power_exact_value_pins_fourth_power_exponent`, whose comment records the higher partial-window value it replaces (261.09384206589294 W vs. the pinned 244.03877169307256 W) without asserting that comparison directly. Task 13.4's Implementation Notes below record both directions confirmed on real files (53 rose, 1 fell)
  - No new absent case is introduced, since the minimum span is not narrower than the window; keep the existing empty-series guard as a total-function backstop rather than deleting it as dead code, because the two constants are independent records and a future narrowing of the span would otherwise turn a guarded absence into a crash
  - **The migration surface is a unit test, not the snapshots.** Every committed snapshot reports no normalized power at all — the fixtures are far shorter than the window — so "regenerate what moved" is vacuous here and an unchanged snapshot is *not* evidence that nothing moved. What actually reddens is the exact-value assertion in the power unit tests, pinned to full precision against the partial-window result. Re-derive that expected value by hand for complete windows, and state both numbers and the series they come from in the test, so the change is legible as conformance rather than as a number that drifted
  - That test's surrounding comment carries a mutation-discrimination argument in absolute watts — how far the exponent-2 mutation lands from the pinned value. Both figures move under complete windows, so recompute the comment or the test's stated discriminating power silently degrades into a claim nobody checked
  - Two prose sites document the behavior being removed — the module docstring's note about a shorter window at the start, and the rolling-mean helper's own docstring. Rewrite both here; 10.2 explicitly disclaims behavior change and the 12.2 guard scans literals, not prose, so nothing else catches them
  - Any numeric literal this change introduces is cited or exemption-listed, keeping the literal guard from 12.2 green
  - Sequential after 10.2 — re-enters the same module
  - Observable: a fixture whose partial-window and complete-window results provably differ pins the new behavior and the direction of the change, and a second case at exactly the minimum span still yields a value rather than an absent one
  - _Requirements: 8.4, 8.9_
  - _Boundary: PowerSeriesMetrics_
  - _Depends: 10.2_
- [x] 13.2 Advance the document-format version and pin the coupling in both directions
  - Advance the document-format version by one and extend the rationale recorded alongside the prior bumps; regenerate every committed golden document in the same change, as that constant's own documented rule requires
  - **Explicit cross-boundary task, like 8.2.** Two of the three edits land outside this spec: the version constant belongs to wiki-contract and the golden documents to workout-docs. Both are bounded and both are here only because Req 18.1 makes the advance a completion condition of this amendment — neither confers ownership, and no other behavior of either module changes
  - Two assertions outside this spec's test tree hard-code the current version and will red; neither appears in the design's modified-files table. One is a straightforward frontmatter equality. The other is a **deliberate cross-spec drift tripwire** pairing the load payload version with this one, and its failure message asks the editor to rule on whether both versions move together — that ruling is not this task's to make, so escalate it rather than editing the pair to green
  - Pin the coupling with two independent triggers: any cited constant carrying a replaced value implies the advance — currently vacuous by design, since every published-work value was confirmed, and asserted in both directions anyway so a future re-sourcing that does move one cannot land without the advance — and the rolling-window conformance change implies it independently, pinned by a case where the two behaviors provably differ so the trigger cannot go vacuous through a fixture edit
  - "No advance is required" is a conclusion only when both triggers are quiet, and the test states that rather than leaving it to omission; the pre-amendment version is a named constant in the test with its rationale, not a bare number
  - The metrics package imports the document-version module nowhere: the coupling lives only in the test layer, which is what keeps this library reading, writing and migrating no document
  - Observable: every committed golden document records the new version, no assertion anywhere still expects the old one, and deleting either trigger reddens the gate
  - _Requirements: 15.3, 18.1, 18.4, 18.5_
  - _Boundary: MigrationGate_
  - _Depends: 13.1_
- [x] 13.3 Rehearse the correction of an already-written document end to end
  - A document written at the pre-amendment version is reported stale by the audit and rewritten from its source file by the regeneration pass, with no in-place edit of its metric values — exercising the machinery that already exists rather than adding any
  - Runs unconditionally rather than inside a branch that might never be taken, because a value does move in this amendment
  - Observable: the rehearsal shows the document stale before and current after, with the rewritten values traceable to a re-parse of the source rather than to an edit of the old document
  - _Requirements: 18.2, 18.3_
  - _Boundary: MigrationGate_
  - _Depends: 13.2_
- [x] 13.4 Amendment 1 validation: full gates and a real-data pass
  - Full test suite, lint, format check and strict type check green from a clean checkout; determinism and immutability still hold with the added result field and the moved values
  - Re-parse and re-compute over the maintainer's real files so the conformance change is measured on real activities rather than only on constructed fixtures, and so nothing in ingestion regressed
  - Same machine-local prerequisite as 9.1, and it has bitten this gate before: real `.fit` files live outside the repo by the data-root contract, so a worktree without a data root cannot run this half. Recreate the data root before starting, or record explicitly that the real-data pass did not run and why — silently skipping it is how the first pass shipped a suite that was green while 16 of 22 real files crashed
  - Observable: every gate green after the change, with the normalized-power movement on real data measured and reported rather than asserted — or, where the data root was unavailable, that stated plainly as an unrun gate rather than omitted
  - _Requirements: 12.1, 13.1, 13.2, 13.3_
  - _Depends: 13.3_

## Implementation Notes

- **Real-data hardening (post-GO, `/kiro-validate-impl` against real HealthFit data, 2026-07-17):**
  `parse_fit` crashed on 16/22 of the maintainer's real `.fit` files with
  `TypeError: expected a numeric field value, got list` in `laps.py`. Root cause: with the
  reference decode flag `expand_components=True`, the decoder returns a lap's
  `enhanced_avg_speed` as a REDUNDANT array (e.g. `[3.17, 3.17]`) while plain `avg_speed`
  carries the same value as a clean scalar; the enhanced-preference helper picked the list
  and the strict numeric coercer raised. Synthetic `Encoder` fixtures only ever emit scalar
  enhanced fields, so the full suite was green while real data failed. Fix: promoted ONE shared
  `fitdocs.ingest._fields.prefer_enhanced(mesg, enhanced_key, basic_key)` that prefers the
  enhanced value only when it is a scalar (`int|float`), else falls back to the basic variant
  (no collapse/average/fabrication; the array elements are always identical AND equal the basic
  scalar). Removed the three divergent local `_prefer_enhanced` copies in `laps.py`/`summary.py`/
  `records.py` and wired them to the shared helper (session + record speed/altitude were latent
  but not yet firing on current data). Regression tests: `test_component_expanded_enhanced_*` in
  `test_laps`/`test_summary`/`test_records`. Re-validation: 22/22 real files parse OK, 0 invariant
  problems; suite 1057 passed, `mypy --strict` + `ruff` clean.
- **Metric-test rigor (learned in task 5.4, apply to 5.5/5.6/7.1):** pin formula-defining
  behavior with EXACT hand-computed expected values (`pytest.approx`, tight rel tol), NOT loose
  bounds. Task 5.4 was rejected round 1 because a `150 < NP < 300` bound let a fourth-power→
  quadratic exponent mutation pass silently, and no test fed a partial `None` gap to guard the
  None→0 coasting rule. Remediation added `test_normalized_power_exact_value_pins_fourth_power_exponent`
  (pinned NP = 261.09384206589294) and `test_normalized_power_none_gap_counts_as_zero_not_neighbor`;
  both parent-verified load-bearing via direct mutation. For TRIMP/TSS (5.6) pin the exact worked
  numbers from the reference/spec; for zone occupancy (5.5) assert exact per-band seconds.
- **Public API + facade (task 6):** package root `fitdocs/__init__.py` uses LAZY PEP 562
  `__getattr__` re-exports (with a `TYPE_CHECKING` block for static typing) — NOT eager imports —
  because an eager `from fitdocs.ingest import parse_fit` would pull `garmin_fit_sdk` into every
  `import fitdocs.model`, regressing model purity (Req 2.6). Keep this pattern. `compute_metrics(
  activity, athlete=None)` lives in `fitdocs.metrics.__init__`; it never imports `fitdocs.ingest`.
- **Short fixtures → NP None end-to-end (for task 7.1 golden):** the run/ride fixtures span ~9 s and
  NP needs ≥ 30 s, so `normalized_power_w`/`intensity_factor`/`variability_index`/`efficiency_factor`/
  `decoupling_pct`/`power_tss` are legitimately `None` in `compute_metrics` over the committed
  fixtures. Golden snapshots record None for those (fine — determinism/shape parity is the goal; NP
  is unit-tested in 5.4 and the facade flip test uses a synthetic 60 s activity). If 7.1 wants NP in a
  golden snapshot, add a longer synthetic activity INLINE (do NOT modify `tests/fixtures/builder.py`).
  Golden serialization must also convert `developer_fields` (MappingProxyType) via `dict(...)` — see
  the asdict landmine note above.

- **Fixtures (task 1.3):** builder in `tests/fixtures/builder.py`; conftest exposes byte
  fixtures `run_fit_bytes`/`ride_fit_bytes`/`strength_fit_bytes`/`minimal_fit_bytes`/
  `non_fit_bytes`/`truncated_fit_bytes`/`bad_message_fit_bytes`, plus decoded message-dict
  builders `run_messages`/`ride_messages`/`strength_messages`/`minimal_messages` for
  extractor unit tests. Byte-deterministic across processes. Encoder API confirmed on
  garmin-fit-sdk 21.208.0: `Encoder().write_mesg({'mesg_num':int, ...})` real-world units
  → `close()` bytes. mesg_num: file_id 0, sport 12, session 18, lap 19, record 20,
  device_info 23, activity 34, set 225.
- **Req 3.3 enhanced→basic fallback (for task 3.1):** decoding with `expand_components=True`
  SYNTHESIZES `enhanced_speed`/`enhanced_altitude` even when only basic `speed`/`altitude`
  were encoded, so the ride fixture does NOT exercise the "enhanced absent → fall back to
  basic" path after decode. Cover Req 3.3 fallback with a HAND-BUILT basic-only record dict,
  not by relying on a fixture.
- **Req 1.4 bad-message (for task 2 decode wrapper):** `bad_message_fit_bytes` decodes
  overall (is_fit True, check_integrity True) yet `Decoder.read()` returns a NON-EMPTY errors
  list (a chained-file RuntimeError). The decode wrapper must COLLECT read() errors into
  `provenance.decode_errors` as strings, never re-raise them.
- **SDK mypy import (task 2, for any ingest module importing the SDK, e.g. 3.4 sets.py):**
  `garmin_fit_sdk` ships no type stubs, so `mypy --strict` flags the import. Established
  pattern: a single narrowly-scoped `# type: ignore[import-untyped]` on the import line
  (NOT a file-level/uncoded ignore). `decode_fit(source) -> DecodeResult` lives in
  `fitdocs.ingest.decode`; `errors.py` holds `FitDecodeError`/`NotFitFileError`/`FitIntegrityError`
  and is SDK-free. `ingest/__init__.py` is still a bare package marker (task 4 adds `parse_fit`).
- **Summary extractor (task 3.2):** `fitdocs.ingest.summary` exposes `extract_summary(session_mesgs,
  activity_mesgs) -> SessionSummary` (first session mapped; session-less → only
  `total_timer_time_s` from first activity msg, all else None; activity `timestamp` is an END
  time, NOT used as start — no fabrication) and `extract_devices(device_info_mesgs)` (dedup by
  `(device_index, serial_number)`, last report wins). Session speed prefers
  `enhanced_avg_speed`/`enhanced_max_speed`. `extract_developer_fields` still belongs to 3.6.
- **RESOLVED IN TASK 4** (both findings below fixed & mutation-verified in commit for task 4):
  the crash-on-int-enum is gone (shared `fitdocs.ingest._fields.str_or_none` coerces a present
  non-str value to `str(value)`; summary.py + sets.py use it, no divergent copies), and
  `device_index 'creator'→0` is applied in both the stored field and the dedup key. Original
  finding text retained below for history.
- **TASK 4 MUST ADDRESS (two reviewer findings on 3.2, both non-blocking there but wire up at
  end-to-end):**
  1. *Unknown-enum-as-int crash (robustness) — CONFIRMED IN TWO MODULES:* the strict helper
     `_str_or_none` RAISES `TypeError` on a present-but-unexpected-type value in BOTH
     `summary.py` (used for `sport`/`sub_sport`/`manufacturer`/`battery_status`/`product_name`)
     AND `sets.py` (used for `set_type`; `category` is already safe via `_category`). Under the
     decoder's `convert_types_to_strings` default, an UNKNOWN enum stays a raw int and would
     abort whole-file ingest once the orchestrator wires these together. Task 4 parses every
     fixture end-to-end and owns the consistent policy: make `_str_or_none` RETURN None (or
     `str(value)` — pick one; SportDetector already maps unknown sport → Workout, and
     SessionSummary.sport is a raw string, so `str(value)` is the faithful choice) rather than
     crash. Reviewer-recommended: extract ONE shared defensive helper (e.g. in a small
     `ingest/_fields.py` or on the model) and use it in both summary.py and sets.py — do NOT
     leave two divergent copies. This is a justified same-spec cross-module fix. Add a regression
     test feeding an int-valued `sport`/`manufacturer` and an int-valued `set_type` and asserting
     no crash (None or coerced str), with the whole-file parse still succeeding.
  2. *device_index faithfulness (polish):* real `device_index` decodes to the string `'creator'`
     (FIT enum value 0). Currently stored as `None` (design-compliant `int|None`, but lossy and
     stored value ≠ dedup key). Reviewer-recommended in-boundary fix (NO model change): map
     `'creator' → 0` in both `_int_index_or_none` and the dedup key so the field is the true int
     0 and stored value == dedup key. Add a test asserting a `'creator'` report → `device_index == 0`.
- **Developer fields (task 3.6):** `fitdocs.ingest.summary.extract_developer_fields(field_description_mesgs,
  session_mesgs) -> Mapping[str, object]`. VERIFIED SDK convention (garmin-fit-sdk 21.208.0): the
  decoder stamps each `field_description` with an integer `key` = its DECODE POSITION (NOT
  `field_definition_number`), exposes the described name under `field_name`, and puts recorded dev
  values under `session_mesgs[0]['developer_fields']` keyed by that same integer `key`. The extractor
  pairs `description['field_name']` → `session['developer_fields'][description['key']]`; list values →
  tuples; unrecorded described fields omitted; returns a read-only `MappingProxyType` (empty by
  default). `Activity.developer_fields` is the additive last model field (default empty MappingProxyType).
  **Amendment 2 (2026-07-27):** each value is additionally decoded per that field's OWN declared
  `scale`/`offset` (`value / scale - offset`, undeclared term defaults to its identity) before being
  placed in the mapping — `_developer_value`/`_scale_one` in `summary.py`; see Req 14.2 as revised.
- **TASK 7.1 MUST ADDRESS (golden serialization — verified landmine):** `dataclasses.asdict(activity)`
  raises `TypeError: cannot pickle 'mappingproxy' object` on the `MappingProxyType` `developer_fields`
  — EVEN WHEN EMPTY, and it fails INSIDE asdict (a `json` `default=` hook cannot patch it). Decision
  (reviewer rec A, parent-confirmed): KEEP `MappingProxyType` (immutability is the model's core ethos;
  serialization is "a test concern, not a public contract" per design). The golden serializer must NOT
  call vanilla `dataclasses.asdict` on an Activity — it must use a bespoke recursive serializer (it
  already needs one for datetime→ISO-8601 and tuple→list) that converts `developer_fields` via
  `dict(activity.developer_fields)`. Same applies to any place that serializes an Activity.
- **Amendment 1 primary texts are gitignored (task 9.1):** neither the Banister (1991) page scans
  (`bannister_physiological_testing_of_the_high_performance_athlete/`) nor the Morton (1990)
  publisher PDF is committed — both are `.gitignore`d at the root of the primary checkout and are
  not redistributable. A fresh worktree therefore has NEITHER, exactly like `.fitdocs/data-root`.
  `docs/reference/banister-trimp-primary-sources.md` IS committed and carries the extraction with
  page and equation numbers, but it is itself a working document Req 15.5 forbids naming as any
  constant's source. Make the texts reachable before task 9.1, or record that locator verification
  ran against the extraction alone.
- **AST guards: scan everything, exempt nothing structurally (learned in task 8.1 over FOUR review
  rounds — read this before writing task 12.2's literal-surface guard, which is the same species).**
  The shapes-only guard in `tests/test_citation.py` was rejected three times, each time for the same
  clause, and the fix was always *less* code. (1) An **enumerate-which-statements-to-look-inside**
  design (`ast.iter_child_nodes`, collecting only `Assign`/`AnnAssign`/`Expr`, recursing only into
  `ClassDef`/`FunctionDef`) is invisible to `if`/`try`/`for`/`while`/`with`/`Return`/decorators/
  defaults — a records tuple plus arithmetic passed the full suite merely by being indented one
  level. Walk the WHOLE module with `ast.walk(tree)` and filter by node kind, never by statement
  form. (2) The **exclusion set was inert and actively harmful**: it was justified as a `|`-union
  accommodation, but `ast.BitOr` was never in the arithmetic-operator set, so it excluded nothing
  real while opening two blind spots (arithmetic inside `Annotated[...]` metadata, and inside the
  excluded assignment's own value). Deleting it entirely left the suite green and closed both holes.
  **Prove any exemption is load-bearing before writing it** — the converse probe (add `ast.BitOr` to
  the operator set and watch it red on the module's own `str | None`) is what shows the operator set
  is doing the work. (3) A `assert nodes_scanned` positive control must walk **the same node set the
  assertions iterate**, not a superset, or it certifies a walk that is looking elsewhere. (4) Four
  residuals are structural limits of any static-AST guard and should be DECLARED rather than chased:
  aliased-name construction in non-module scope, attribute-access construction, arithmetic via a
  called function, and `exec`/`eval`. (5) Three of the four rejections included a **false sentence in
  the guard's own docstring** explaining why a mechanism existed — and every one slipped the mandated
  `verified|caught|proven|...` grep, because the vocabulary does not cover justification prose. Read
  every sentence of a guard's docstring, comments and assert-failure strings against what the code
  actually does before reporting.
- **PIN PROVENANCE RECORDS BY WHOLE-VALUE EQUALITY, NOT BY SUBSTRINGS (task 9.1 — SIX review
  rounds, five remediations, all on this one point. Read before writing task 9.2's
  `FitdocsChoice` records, which carry free-text `justification` and `search_basis` and will hit
  this immediately; 9.3's `CitedConstant` notes and 12.3's worked-example comments too).**
  A citation record's prose asserts facts about texts a future reader cannot cheaply re-check, so
  a test that cannot tell a true claim from a false one is worse than no test. Three things,
  learned the expensive way:
  (1) **The mutation must be the FALSE VERSION of the claim, never deletion of the sentence.**
  "Delete phrase X → the test asserting X reds" is tautological: it proves the string is present.
  Every early mutation table here was that shape, and the suite would have shipped Morton's
  b-values swapped between the sexes, `OMITS`/`AGREES` reversed, Coggan's step 3 as "median", and
  a note claiming Banister's own page prints *e* correctly.
  (2) **Substring assertions on numbers are blind upward.** `assert "multiply by 100" in note`
  PASSES against "multiply by 1000" — the true token is a prefix of the false one. Same for
  `"4th power"` vs `"14th power"`. And `100 → 95` *does* red, so the assertion looks
  discriminating. Of the three constants Coggan governs, only the 30 s window was genuinely
  pinned until this was found.
  (3) **Per-clause inventories do not terminate.** An exhaustive clause-granular sweep found 29
  claims; an independent reviewer enumerating the same text found 43, with 21 falsifications
  still green. The falsifiable surface is every quoted substring, which is finer than any clause
  list. What terminated it: a **whole-note equality backstop** per record, plus **full equality on
  every one of the six `Citation` identity fields** — after which 53 mutations produced no
  survivor that falsifies anything. Keep targeted assertions underneath as diagnostics so a
  failure says *which* claim moved. Prefer a literal over a hash: when a digest reds the reflex is
  to regenerate it, when an equality reds the text diff reaches the next reviewer.
  Known residual, declared: `_normalized()` folds Unicode whitespace, so a space→NBSP substitution
  inside a note survives. Non-semantic; `work`/`locator` are immune (exact equality).
- **`load.channels.sources` re-exports the citation vocabulary EXPLICITLY, and nothing guards it
  (task 8.2).** `src/fitdocs/load/channels/sources.py` no longer defines `VerificationStatus` or
  `Citation`; it does `from fitdocs.citation import Citation as Citation` (and the same for
  `VerificationStatus`). The `as` aliasing is **load-bearing, not style**: `mypy` strict sets
  `no_implicit_reexport`, so under a plain `from ... import X` every module doing
  `from fitdocs.load.channels.sources import VerificationStatus` fails type checking. Proven by an
  out-of-band probe — plain form gives `Module "fitdocs.load.channels.sources" does not explicitly
  export attribute "Citation"`. **The whole validation set is blind to this**: collapsing the aliases
  leaves `pytest` (2112), `ruff check`, `ruff format --check` and `uv run mypy` all green, because
  `tests/load/channels/` is absent from `[tool.mypy].files`. Do not "tidy" those aliases.
  `Divergence` stays defined in that module — it is load-channels' own type and did not move.
- **The mypy perimeter is explicit and unguarded (task 8.1):** `[tool.mypy].files` in `pyproject.toml`
  names checked test modules one by one, so a new test module the checker never reads satisfies a
  type-check observable vacuously. Add the module in the same change and confirm the "checked N source
  files" count rises (8.1 took it 69 → 71). Nothing guards membership: deleting the line leaves both
  `pytest` and `mypy` green while silently reverting the static observable — queued at
  `2026-07-28-mypy-perimeter-membership-unguarded`.
- **A `FitdocsChoice`'s prose is an evidence claim, and the rejections are all about truth, not
  coverage (task 9.2, three review rounds).** 9.1's lesson (whole-value equality backstops) carried
  over and worked — the backstops caught every later prose edit. What rejected 9.2 three times was
  the *content*: (1) round 1, a `search_basis` recording a search that could not have found a
  defining work — re-reading Banister/Morton/Coggan, all heart-rate/power texts, for a GPS speed
  threshold and an altitude filter. That is a pre-satisfied fixture in prose: the finding was
  determined before the search ran, so Req 15.9's "evidenced conclusion" is unmet however honestly
  it is reported. An implementer subagent has no web tool — **the parent must run the search and
  hand over a dossier**, which is what closed it. (2) Round 2, fixing an omission by adding an
  *unverified* assertion ("fitdocs.ai is this project's own unpublished personal application" —
  unsupported in-repo, and `README.md:23` links it as a public repo). Assert only the load-bearing
  minimum: for 15.1/15.9 that is "not a published work", never ownership or provenance you have not
  sourced. The maintainer confirmed 2026-07-28 that he *does* own fitdocs.ai and ruled it stays out
  of this repo; the endorsed wording is "an application whose source this project read (linked from
  README.md)". (3) Also round 2: a sentence calling "unpublished" a Strava threshold the same
  sentence said Strava publishes, and "an order of magnitude" for figures that are 3.9x and 2x.
  **Re-read every record end to end as prose** — self-contradiction and bad arithmetic survive
  clause-level review and every mutation, because the tests pin the text, not its truth.
- **The rule the last three tasks kept relearning: ANY new field carrying a factual claim gets a
  whole-value backstop, not a non-emptiness check (task 9.3, two rounds).** 9.1 and 9.2 established
  the pattern and it works — but 9.3 added four `Corroboration` records beside six fully-pinned ones
  and asserted only `assert locator` / `assert note`. Four production mutations then shipped green:
  the locator set to a wrong Morton page, the locator set to *Banister's* own p. 408, the `OMITS`
  note inverted to say Morton prints the coefficient, and the `AGREES` note's quoted b-values
  changed to (2.92)/(2.67). Two of the four notes were asserted by nothing at all. If a field states
  what a source says, `assert field` is not coverage — it proves the string is non-empty, which no
  requirement asks for.
- **Docstrings that describe coverage are themselves factual claims, and they go stale one paragraph
  at a time (task 9.3, both rounds).** Every prose rejection in 9.3 was an *adjacent-sibling* miss:
  the body was updated and the docstring above it left predicting the opposite; one paragraph of a
  module docstring was corrected and the one 20 lines up left saying "task 9.3 will import
  `TrimpWeighting`" when 9.3 is the task that didn't. A test docstring claimed nothing pinned the
  TRIMP exponent while a test 1,000 lines below asserted exactly that. **Grep both files for
  `yet|later task|task 9|task 1[0-9]|do not exist|will ` and check every hit** — a whole-file sweep
  terminates where incremental fixing does not.
- **Counting claims in a docstring need the same evidence as a number in a record (task 9.3).** A
  closing edit written *in the parent session* asserted "the three values with no named module
  constant"; there are four — the female pair, the NP averaging exponent, and the moving threshold,
  which is a bare `0.5` at `aggregates.py:103`. The same sentence said seven values are pinned
  "against `stress.py`, `power.py` and `aggregates.py`", but the moving threshold is pinned against a
  literal transcribed into the test file: changing `aggregates.py:103` to `0.7` leaves the whole
  suite green. Both were caught only because the edit was sent for independent verification instead
  of being self-certified — do that for parent-authored prose too, not just subagent output.
- **THE CLOSING MECHANISM FOR A RECORDS TASK IS A CLAIM INVENTORY, NOT A READ-THROUGH (task 9.4,
  three rounds — the most useful note in this file).** 9.4 was rejected three times and each round
  found *new, real* prose defects the previous round missed: round 1 found four (an unsupported
  "near-uniformly sampled" rider; a `reason` that denied the very numerical difference the
  `Departure` exists to record; "demonstrates" where the source says "an inference from one
  example"; `WeightingPair`'s frozenness pinned by nothing), round 2 found two more **in a field
  round 1 never touched** (a `source_specifies` attributing a per-sex *coefficient* to Morton, who
  states none — so `DEPARTURES` shipped two records contradicting each other about the same page —
  and round 1's own coercion fix landing entirely unpinned). Reading was not converging. What closed
  it in one round: an **inventory** — every atomic falsifiable assertion in all three records' four
  fields plus the resolver docstrings, each with its settling evidence (a `file:line`, a §-locator,
  or the primary text) and a SUPPORTED / UNSUPPORTED / OVERSTATED verdict, then a completeness
  declaration. 52 claims, 0 false. An inventory terminates because an unsettleable claim is a
  *finding*; a read-through does not, because "looks fine" is always available.
  **Corollary worth internalising: a whole-value backstop pins TEXT, not TRUTH.** Every one of these
  defects was pinned character-for-character while being false — the Morton-coefficient claim had
  its own hand-typed backstop guarding it. Backstops stop drift; only evidence stops falsehood.
  **Read the primary texts, not the extraction.** Round 1's reviewer opened the B91 page scans and
  the Morton PDF, *withdrew one of its own findings* on that evidence, and found the extraction doc
  under-locates B91's session-summation sentence. Task 12.3 writes worked-example records and will
  need the same discipline.

- **Task 10.1 (the pattern for every 10.x unit).** Pointing a metric module at its
  records is a three-line production change and cost **three review rounds** — every
  rejection was *prose or coverage*, never the mechanism. Budget for that.
  **A rewritten docstring is a new factual claim.** 10.1's rewrite introduced a
  sentence the code five lines below it falsified ("for a speed-less channel" — a
  *present* sub-threshold speed also takes the distance branch), and the guard test's
  own justification prose falsely listed `1.0` among the module's literals. Both slipped
  the mandated `verified|caught|proven|...` grep because they are *justification* prose,
  not discrimination claims. Read the justification prose as prose, and settle each
  atomic claim against evidence before reporting.
  **Documenting a boundary obliges you to pin it.** 10.1's docstring newly made the
  strict/inclusive comparison explicit while `>` → `>=` left all 2198 tests green. If
  your rewrite makes a rule exact, add the fixture that defends it (here: speed exactly
  at threshold with a flat distance channel → `0.0`; just above → counted).
  **Restore module state where it leaks, not in a neighbour.** The record-swap tests
  `importlib.reload` the module, so a dropped `finally` leaks the mutated constant. The
  first fix asserted restoration in a *separate* test and was rejected: it passed
  vacuously when selected alone and went green when a neighbour was reordered ahead of
  it. Assert the transition *inside* the swapping test, after its `try`/`finally` closes.
  Note 10.1 left the **altitude** half unpinned this way (queued) — do not copy that half.
  **Stale cross-file prose is in scope.** `tests/metrics/test_sources.py` carried
  "it is a bare literal at `aggregates.py:103` — task 10.1 promotes it" and a hand-typed
  `0.5`; that transcribed literal was a real hole (deleting a restoration left the whole
  suite green). Grep `test_sources.py` for your constant before you start, drop bare
  `file.py:NNN` citations rather than renumbering them, and make its sync assertion read
  the live module attribute.
  **10.3 will red `tests/metrics/test_stress.py:292`** (`assert internal == {"fitdocs.model"}`)
  the moment `stress.py` imports its records — that is expected, and updating it is part
  of 10.3, not a discovery. `power.py` has no equivalent guard today, so 10.2 does not
  hit it.

- **Task 10.3, and the major-10 retrospective.** All three 10.x units were
  three-line production changes; together they cost **eight review rejections**,
  of which seven were prose and one was a guard the task itself broke. Read the
  10.1 note above first — everything in it recurred. Three additions.
  **A passing mutation can pin something narrower than it looks.** 10.3's route
  claim ("resolves the registry's *default* rather than naming a curve") was
  cleared in round 1 on the evidence that binding direct to
  `BANISTER_MALE_COEFFICIENT` reds. It does — but only because the swap test
  monkeypatches `WEIGHTING_PAIRS`, so *any* bind through the mapping survives,
  whichever key it uses. Hard-wiring `WEIGHTING_PAIRS[BANISTER_MALE]` left the
  full suite green. When a mutation reds, ask which of several nested claims it
  actually killed; the fix here was to monkeypatch `DEFAULT_TRIMP_WEIGHTING`
  itself and assert **by value** (0.86/1.67), never by member name.
  **Rewriting a guard can silently empty it.** 10.3's import collector was
  rewritten to admit only `fitdocs`-prefixed names, which made a sibling
  `assert not any("garmin" in name ...)` unreachable — `import garmin_fit_sdk`
  passed 28/28 under a comment saying the check was live — and dropped relative
  imports entirely (`node.module` is `None` when `level > 0`), so
  `from . import power` was invisible. `tests/metrics/test_sources.py` already
  had the `node.level` handling; copy it rather than re-deriving.
  **10.x inverted a dependency, which emptied assertions in another file.**
  `sources.X.value == module._X` was a real pin when the module held the
  literal; now the module reads *from* the record, it compares a value to
  itself and survives a record value change. Three such assertions are now
  value-insensitive by construction. They still catch a **wrong-record bind**,
  so they were kept with honest docstrings — but task 12.1 must not count them
  as independent value pins; the literal-anchored assertions are what carry
  Req 15's transcription check.

- **Amendment 1 real-data validation (task 13.4, 2026-07-30):** all 77 of the
  maintainer's `.fit` files parse and compute with zero failures (308
  `compute_metrics` calls across four athlete configurations). 54 of 77 yield a
  normalized power; the other 23 all have an entirely unrecorded power channel
  (strength, watch-only cycling, walking, hiking) — none hits the span guard.
  The 13.1 conformance change moves NP by **+0.48 W median (+0.17%)**, max
  **+1.01 W (+0.42%)**: **53 rose, 1 fell**. The faller is a hard opener
  spiking to 737–781 W, whose dropped partial windows averaged *above* the
  retained series — real-data confirmation that the direction is conditional,
  not the unconditional "raises" `tasks.md` line 262 originally implied (line
  262 is now corrected to state the conditional direction, citing this note).
  Every figure was reproduced by an independently written measurement.
