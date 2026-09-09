# Research & Design Decisions: performance-benchmarks

## Summary
- **Feature**: `performance-benchmarks`
- **Discovery Scope**: Extension (integration-focused discovery against the
  existing benchmark store, the load pass and the channels sufficiency gate),
  with a science/citation review carried over from the Phase 6 discovery
  viability check (2026-09-09).
- **Key Findings**:
  - The store's write path already *reserved* the seam this feature needs.
    `fitdocs/load/profile.py:517-583` (`_merge_benchmarks_document`) preserves
    an unrecognised key on an existing entry and names "a `source` a future
    feature wrote" as the case it protects. The parser ignores unknown entry
    keys; the serializer emits only `value`, `measured_on`, `note`. So the
    amendment is three coordinated edits (parser, serializer, `with_benchmark`)
    plus the merge's overlay list, not a schema redesign.
  - Reconciliation falls out of the existing merge for free.
    `_merge_benchmarks_document` replaces the entry list of every
    `(scope, kind)` group the fresh entries cover
    (`profile.py:576 existing_scope[kind_key] = merged_entries`), so a derived
    entry that is no longer derived disappears simply by not being in the
    rebuilt entry set — no delete API is needed, only a profile method that
    rebuilds the whole derived subset in one call.
  - Reusing `fitdocs.load.channels.sufficiency.evaluate` rather than mirroring
    it is legal and cheap. The channels purity guard
    (`tests/load/channels/test_purity.py`) constrains what *channels* imports,
    not who imports channels; `tests/load/threshold/test_boundary.py` pins the
    *calculator's* imports, and nothing in this feature is imported by the
    calculator. Reuse also gets the shared `InsufficiencyReason` vocabulary,
    which is what Req 7.4 ("the same vocabulary the load pass reports in")
    asks for.
  - No new settings key is needed. The stream-coverage minima this pass wants
    are exactly the `[load].sufficiency` minima the athlete already configured
    (`fitdocs/load/settings.py:195-296`), and every other number in the feature
    is a cited constant that must *not* be configurable.
  - The 2026-07-15 HealthFit sample carried no cycling power, so on the
    maintainer's own archive the FTP derivation may derive nothing. This is a
    reporting requirement (7.7), not a defect.

## Research Log

### The benchmark entry shape and where provenance can live
- **Context**: Req 5 needs a provenance record on a benchmark entry that
  survives hand editing, round-trips, and does not disturb the existing store.
- **Sources Consulted**: `src/fitdocs/benchmarks.py` (`Benchmark`,
  `parse_benchmarks`, `benchmarks_to_document`); `src/fitdocs/load/profile.py`
  (`AthleteProfile.with_benchmark`, `save_profile`,
  `_merge_benchmarks_document`, `_canonicalize_benchmarks_region`);
  `.kiro/specs/athlete-benchmarks/design.md` and `requirements.md`.
- **Findings**:
  - `Benchmark(kind, discipline, value, measured_on, note)` is frozen; adding
    an optional field with a default is source-compatible with every existing
    construction site.
  - The parser validates `value`, `measured_on`, `note` and ignores every other
    key; `benchmarks_to_document` emits `value`, `measured_on` and `note` only.
  - `save_profile` re-parses the assembled document before writing
    (`profile.py:376-383`), so a serializer/parser disagreement about `source`
    becomes a loud pre-write failure rather than a corrupted file.
  - Verified empirically with the project's own `tomli_w` 1.2.0 that a nested
    mapping inside an array-of-tables element round-trips exactly:
    `[[benchmarks.run.threshold_pace_s_per_km]]` followed by
    `[benchmarks.run.threshold_pace_s_per_km.source]`, with multiple entries
    interleaved correctly and `tomllib.loads(dumps(doc)) == doc`.
- **Implications**: `source` is a sub-table on the entry, written by the
  existing serializer, validated by the existing parser, merged by the existing
  overlay once `source` joins the recognised-field list.

### Sufficiency: reuse or mirror
- **Context**: Req 3.4 and 4.5 gate a derivation on stream coverage. The
  roadmap allows either reuse or a mirror.
- **Sources Consulted**: `src/fitdocs/load/channels/sufficiency.py`,
  `src/fitdocs/load/channels/types.py`, `tests/load/channels/test_purity.py`,
  `tests/load/threshold/test_boundary.py`.
- **Findings**: `sufficiency.evaluate(samples, values, channel=, stream=,
  settings=, minimum=)` returns `StreamCoverage | ChannelInsufficient`; the
  coverage is time-weighted over the raw arrays, never resampled; the gate
  never raises. The purity guard is inward-facing (it restricts what the
  channels package imports). The threshold boundary guard is likewise
  inward-facing for the calculator's five modules.
- **Implications**: reuse. `fitdocs.performance` may import
  `fitdocs.load.channels.sufficiency` and `...channels.types`; no channels
  module and no calculator module may import `fitdocs.performance`, which is
  asserted structurally by this feature's own guard.

### The science, and what may be written
- **Context**: Req 8 gates every number on a citation record with an honest
  verification status. The Phase 6 discovery viability check (2026-09-09) had
  already mapped the ground; this step confirmed how it lands in the codebase's
  existing citation vocabulary.
- **Sources Consulted**: `src/fitdocs/citation.py` (`Citation`,
  `FitdocsChoice`, `Corroboration`, `Departure`, `CitedConstant`,
  `VerificationStatus`); `src/fitdocs/load/channels/sources.py` (the
  `BLOCKED_CITATIONS` named-exception mechanism and its enforcement test);
  `tests/metrics/test_constant_guard.py` (the numeric-literal scan);
  `.kiro/steering/roadmap.md` Phase 6 Constraints;
  `.kiro/specs/performance-benchmarks/brief.md`.
- **Findings**:
  - The vocabulary already models everything this feature needs: exactly one
    governing `SourceRecord` per constant, any number of `Corroboration`s, and
    `FitdocsChoice` for a step no work states (its `verification` field is
    typed to a single literal, so a choice cannot masquerade as primary text).
  - `fitdocs.load.channels.sources` already ships a Coggan (2003) citation
    (`COGGAN_TSS`, `PRIMARY_TEXT`, with a page-level locator) for the *TSS/NP*
    formulas of the same work whose FTP *definition* this feature needs.
  - The channels layer's `BLOCKED_CITATIONS` + enforcement test is the exact
    mechanism Req 8.4 describes; it is adopted rather than re-derived.
  - The Allen & Coggan 0.95 × 20-minute rule's book page is unverified. The
    roadmap lists verifying it as a Direct Implementation Candidate and
    requires that the unverified locator block *that constant*, not the spec.
- **Implications**: the 20-minute FTP path ships **blocked** — declared,
  tested, and refused at runtime with a reason naming what must be read —
  while the Coggan-definition FTP path, the Riegel path and the LTHR path all
  ship. Unblocking is a one-constant change with no structural work.

### Where the effort is, inside the file
- **Context**: LTHR and FTP average a stream over "the effort". The tag may
  carry an official time; the file may contain a warm-up.
- **Sources Consulted**: `.kiro/specs/effort-tags/design.md` (cross-spec
  obligations 3 and 4), the roadmap's "hand-tagged efforts only" decision.
- **Findings**: locating an effort inside a longer recording is mean-maximal
  mining — the `effort-detection` follow-on the roadmap explicitly did not
  schedule. Nothing in the tag says where inside the file the effort sits.
- **Implications**: the effort span is the whole recorded activity. Where the
  tag carries `effort_time_s` and the recorded span disagrees with it beyond a
  stated tolerance, the derivation is declined naming both durations (Req
  3.6). This refuses rather than guesses, and the athlete's remedy —
  tag the file that *is* the effort — is stated in the decline.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Derivation inside the calculator | The threshold calculator estimates an anchor when none is on file | No new command | Contradicts `threshold-load` 11.4/11.6; the derived number is invisible to the athlete | Rejected at discovery |
| `fitdocs/benchmarks/` grown into a package with a `derive` submodule | Keeps derivation next to the vocabulary | Short import paths | Turns a module into a package (churn across every importer); puts estimation inside the store `athlete-benchmarks` owns | Rejected |
| **New `fitdocs/performance/` package + a pass module inside it** | Pure derivation leaf modules plus one impure engine, mirroring `load/channels/*` + `load/engine.py` | Matches an existing, reviewed shape; keeps estimation out of the store; the pure half is guardable | One more top-level package | **Selected** |
| A top-level `fitdocs/derive.py` pass beside `sync.py`/`audit.py` | Pass modules already live at top level | Familiar | Splits one feature across two locations for no gain; name collides conceptually with the pure `derive` | Rejected |

## Design Decisions

### Decision: `source` is a sub-table with a closed origin class and an open method name
- **Context**: Req 5.2, 5.5, 5.10. The roadmap names one field, `source`.
- **Alternatives Considered**:
  1. `source` as a bare string (`"derived"`), with method/page/citation packed
     into `note`.
  2. `source` as a sub-table with a fully closed key *and* value vocabulary,
     including the method names.
  3. `source` as a sub-table whose *shape* and *origin class* the store
     validates, while the method-name vocabulary stays with the deriver.
- **Selected Approach**: (3). `source = { kind, method, document, inputs,
  citation }`; `kind` is a closed `BenchmarkSourceKind` (`derived`,
  `measured`); `method`, `document`, `inputs` and `citation` are validated as
  non-empty strings. The closed `DerivationMethod` vocabulary lives in
  `fitdocs/performance/types.py`.
- **Rationale**: (1) makes reconciliation depend on parsing free text — the
  pass must know which document produced an entry. (2) drags estimation
  vocabulary into the store `athlete-benchmarks` deliberately keeps free of it,
  and makes every new method a store change. (3) keeps the store's job
  ("is this entry well formed?") separate from the deriver's ("which methods
  exist?"), and keeps an entry written by a future release readable today.
- **Trade-offs**: a typo'd method name in a hand-edited file is not caught by
  the store. Mitigated by a test asserting the pass writes only
  `DerivationMethod` members, and by the fact that an unrecognised method still
  reads as *derived*, so the pass reconciles (and therefore repairs) it.
- **Follow-up**: the pass treats an entry whose `kind` it does not recognise as
  **not derived** — never overwritten — which is the safe default.

### Decision: reconcile by rebuilding the whole derived subset
- **Context**: Req 6.3, 6.4, 6.5.
- **Alternatives Considered**: per-entry upsert plus an explicit delete API;
  a full rebuild of the derived subset in one profile call.
- **Selected Approach**: `AthleteProfile.with_derived_benchmarks(entries)`
  drops every parsed entry whose `source.kind is DERIVED`, appends the supplied
  set, and hands the result to the existing merge. Non-derived entries, unknown
  keys, unknown quantity tables and every non-benchmark key are untouched.
- **Rationale**: idempotence and tag-removal reconciliation both fall out of
  one operation; no delete API is added to a store that has never had one.
- **Trade-offs**: the pass must always compute the complete derived set, so a
  partial run (one document) is not supported. That is acceptable: the pass is
  cheap relative to the sync it follows, and a partial mode would break Req 6.4.
- **Follow-up**: a collision with a non-derived entry at the same
  `(discipline, kind, measured_on)` drops the derived candidate and reports it
  (Req 6.2) — the derived entry is never written, so it can never shadow.

### Decision: no new settings table or key
- **Context**: `src/fitdocs/load/settings.py` is the repo's biggest choke
  point; nine specs cite it.
- **Alternatives Considered**: a `[benchmarks.derive]` table with coverage
  minima and validity windows; reuse of `[load].sufficiency` only; reuse plus
  a single opt-out key.
- **Selected Approach**: reuse `[load].sufficiency` for stream coverage and
  minimum duration; ship every window, exponent, factor and tolerance as a
  cited constant that is deliberately not configurable.
- **Rationale**: the coverage question is literally the same question the load
  pass answers, and the athlete has answered it once. Making a validity window
  configurable would let a setting move a number away from the source that
  governs it, which Req 9.8 forbids and which the citation discipline exists to
  prevent. `load/settings.py` is not edited at all.
- **Trade-offs**: an athlete who wants a laxer coverage bar for derivation than
  for load cannot have one. Recorded as an accepted limitation.

### Decision: the effort span is the whole recorded activity
- See "Where the effort is, inside the file" above. Recorded as a
  `FitdocsChoice` (the tolerance) plus an explicit decline reason.

### Decision: adopt the channels layer's blocked-citation mechanism verbatim
- **Context**: Req 8.4, 8.5 and the unverified Allen & Coggan locator.
- **Selected Approach**: `fitdocs/performance/sources.py` declares
  `BLOCKED_CITATIONS` (citations carrying `SECONDARY_ATTESTATION` as tracked
  exceptions — Riegel today) and `BLOCKED_METHODS` (methods whose governing
  constant cannot be written yet — the 20-minute FTP factor today), each with a
  record stating what must be read. Tests enforce both.
- **Rationale**: the mechanism is already reviewed and already understood by
  maintainers; re-deriving it would invite a second, subtly different policy.

## Risks & Mitigations
- **A derived entry silently outranks a measured one** — mitigated by never
  writing a derived entry at a `(discipline, kind, measured_on)` an existing
  non-derived entry occupies, and by a test that starts from a hand-written
  profile and asserts byte-level preservation.
- **The store's overlay merge inherits a stale unknown key when a date is
  reused** — pre-existing, documented behaviour of
  `_merge_benchmarks_document`; unchanged by this feature and out of its
  boundary. Recorded so a reviewer does not read it as new.
- **`math.pow` / `math.exp` are libm-backed, so a golden fitted value could
  differ across platforms** — the Riegel solve is a single `pow`; golden tests
  assert to a stated tolerance rather than exact bytes for the *computed*
  value, while the *written file* is byte-pinned from fixed inputs.
- **The maintainer's archive may produce zero FTP entries** — a reporting
  requirement (7.7), tested with a fixture that carries no power.
- **Command-name collision with `load-history`** — this spec's command is named
  in the design and load-history names its own separately; both are stated in
  the two designs.

## References
- Riegel, P.S. (1981). "Athletic Records and Human Endurance." *American
  Scientist* 69(3):285–290. JSTOR-only; **not read by this project**. The 1.06
  running exponent was printed in Riegel's 1977 *Runner's World* article.
- Drake, K.M., Finke, A.J., Ferguson, R.A. (2024). *European Journal of Applied
  Physiology* 124:507–526 — peer-reviewed attestation of the Riegel exponent.
- McGehee, J.C., Tanner, C.J., Houmard, J.A. (2005). *Journal of Strength and
  Conditioning Research* 19(3):553–558 — 30-minute time-trial mean HR versus HR
  at the 4 mmol/L lactate threshold.
- Dumke, C.L., et al. (2006). *Journal of Strength and Conditioning Research*
  20(3):601–607 — 60-minute time-trial HR versus HR at the lactate threshold.
- Coggan, A.R. (2003). "Training and racing using a power meter: an
  introduction" (USA Cycling coaching-education chapter) — the FTP definition;
  in hand, and already cited in `src/fitdocs/load/channels/sources.py`.
- Allen, H., Coggan, A.R. *Training and Racing with a Power Meter*, 2nd ed.
  (VeloPress, 2010) — the 0.95 × 20-minute rule. **Chapter/page locator
  unverified**; blocks that constant only.
- Borszcz, F.K., et al. (2018). *International Journal of Sports Medicine*
  39(10):737–742 — measured attestation of the 20-minute protocol; limits of
  agreement about ±40 W.
