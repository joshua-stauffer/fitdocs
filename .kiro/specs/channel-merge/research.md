# Research & Design Decisions: channel-merge

## Summary
- **Feature**: `channel-merge`
- **Discovery Scope**: Extension (integration-focused, light discovery). Run
  in-context by the spec writer against the branch `chore/p8-channel-merge`
  (base a5792f2 plus the wave-1 spec commits); no research subagent was
  dispatched because the writer ran as a subagent without an Agent tool. No
  external research was needed: no new library, API or standard is involved.
- **Key Findings**:
  1. The training-load pass and the benchmark-derivation pass never read a
     page's body. Each re-parses the page's **last listed archived file**
     (`src/fitdocs/load/engine.py:454-469`, `:618-645`;
     `src/fitdocs/performance/engine.py:266-293`, `:350-366`). The brief's
     "the load pass reads the composed page as it reads any page, no code
     change" is therefore false as written: without a change, a heart-rate
     channel donated to a ride page would appear in the page's summary and
     telemetry but never in its load. Both passes must compose the page's
     listed files by the same rule the page task uses.
  2. Every scalar metric is "session value when recorded, else derived from
     the channel" (`src/fitdocs/metrics/aggregates.py:47`,
     `_session_or_channel`). Running `compute_metrics` over a composed
     activity whose `summary` is the base's therefore already satisfies both
     halves of "summaries follow the channels": a donated channel feeds every
     value whose session counterpart the base lacks, and no value the base
     recorded is replaced. No summary recomputation code is needed.
  3. `activity-identity` computes the page's filename, `uuid` and base-identity
     keys from the base's own parse before its `_render_activity(roles,
     parsed)` seam runs, and hands the seam every resolved member already
     parsed. Composition in `sync` reads no archived file itself.

## Research Log

### How a page is rendered after activity-identity
- **Context**: Where does composition plug in, and what does it receive?
- **Sources Consulted**: `.kiro/specs/activity-identity/design.md` § "Cross-spec
  seams" (channel-merge bullet), § SyncEngine (page task steps 1-12),
  § PrecedenceAndRoles; `.kiro/specs/activity-identity/tasks.md` task 4.1.
- **Findings**:
  - Page task step 7: `render_activity = _render_activity(roles, parsed)`;
    metrics, the map plan and tiles come from its result. It returns
    `parsed[roles.base.ref]` until this spec replaces the body.
  - `PageRoles.extras` are in descending rank (best first); `PageRoles.sources`
    = unresolved refs, then extras worst to best, then the base last.
  - `parsed` maps every resolved member's ref to its `Activity`; members that
    do not resolve are `unresolved` and never parsed.
  - Identity keys and `uuid` come from `source_identity(parsed[roles.base.ref])`
    plus retention, and reach render through `DocContext.identity`.
- **Implications**: `_render_activity` keeps its name and parameters; its
  return type becomes the composition result so the page task can pass both the
  composed activity and its provenance on. No archive read happens in `sync`
  for composition; the archive reads of the extras land in the load and
  benchmark passes (finding 1), as the roadmap's Phase 8 `sync.py` seam states
  since its correction at the spec batch.

### What the channel set is after running-dynamics
- **Context**: The roadmap requires composition to be generic over the channel
  set or to cover running-dynamics' channels by name.
- **Sources Consulted**: `.kiro/specs/running-dynamics/design.md` § ModelChannels,
  § "Cross-spec seams" (channel-merge bullet); `src/fitdocs/model.py:96-115`.
- **Findings**:
  - `Samples` grows to 22 per-sample channels plus `time_s`; the twelve dynamics
    fields default to `()` and `__post_init__` fills them to all-`None` of
    `len(time_s)`, raising `ValueError` on a wrong length.
  - Every value is final at ingest: the placeholder-zero and gate rules run per
    file; a gate pair may legitimately come from two files.
  - `Activity.record_developer_fields` is aligned to its own file's samples.
  - No `SessionSummary` or `DerivedMetrics` field is fed by a dynamics channel.
- **Implications**: donation enumerates `dataclasses.fields(Samples)` minus
  `time_s` (generic; a channel added later is donated without an edit), with
  one declared multi-channel unit (position). A composed `Samples` is built by
  `dataclasses.replace` on the base's, so its length rule holds by
  construction.

### Where the page shows channels today
- **Context**: Requirement 4 needs a place to state provenance.
- **Sources Consulted**: `src/fitdocs/render/sections.py:119-128`
  (`_COVERAGE_CHANNELS`), `:503` (`devices_section`), `:567`
  (`_coverage_table`); `src/fitdocs/render/views.py:179, 210, 244`;
  running-dynamics' `render/dynamics.py` design (`DYNAMICS_DISPLAY` labels,
  and `render.dynamics` imports `render.sections`).
- **Findings**:
  - The coverage table has eight rows (`latitude_deg` labelled `GPS`); the
    dynamics channels are covered in the Running Dynamics section's own table,
    not the coverage table.
  - `render.dynamics` imports `render.sections` (for `chart_axis`), so
    `render.sections` cannot import `render.dynamics` without a cycle.
- **Implications**: provenance is a new section of its own, `## Channel
  Sources`, assembled by the views after `## Device & Data Quality`, in a new
  module `render/provenance.py` that owns one label table for every channel;
  a test holds that table equal to the coverage and Running Dynamics labels.
  A page without extras is untouched.

### How the load and benchmark passes resolve a page's data
- **Context**: Finding 1.
- **Sources Consulted**: `src/fitdocs/load/engine.py:427-470, 618-645`;
  `src/fitdocs/performance/engine.py:1-30, 266-293, 346-380`;
  `tests/performance/test_engine.py:698-726, 1186-1235` (the shared
  behavioural test proving both resolvers agree).
- **Findings**:
  - Both passes resolve `sources[-1]` through `contract.sha_of_ref` and
    `layout.archive_path`, then call `parse_fit`. The performance module
    restates the load pass's private resolver by design and pins agreement
    with a behavioural test rather than an import.
  - `apply_load` restores an already computed region without recomputing
    (`load/engine.py:370-379`); placeholder and unsupported regions are
    computed on every pass.
  - Stream sufficiency is time-weighted coverage over the samples the
    activity carries (`load/channels/sufficiency.py`), default minimum 0.80
    (`load/channels/types.py:155`).
- **Implications**: both passes keep their base resolvers unchanged (so the
  shared resolver test keeps meaning what it says) and compose the resolved
  base with the page's other listed files through one shared function,
  `compose.archive.compose_listed`. A page whose load was computed before an
  extra arrived keeps its result until `fitdocs load --recompute`.

### The measured alignment facts and how they constrain the rule
- **Context**: Requirement 3.
- **Sources Consulted**: `brief.md` § Current State (viability check
  2026-09-24, three Stryd↔HealthFit pairs); roadmap Phase 8 § Constraints
  ("Identity never guesses", measured pairs); activity-identity
  `TOLERANCE_SOURCES`.
- **Findings**:
  - All timestamps are whole seconds; every Stryd timestamp exists in the
    HealthFit copy; HealthFit has 2-7 extra trailing samples.
  - Distance and power (and vertical oscillation, stance time, speed) match
    exactly at +1 s in some stretches and 0 s in others (one file: +1, +1, 0,
    +1, 0); a plain join is 1 s early for 52-100% of samples.
  - Heart rate sits at −1 or 0 s: not an alignment key.
  - Step length reads about 0.8% higher in Stryd; cadence differs by ±1: not
    exactly reproduced, not keys.
  - Garmin↔HealthFit rides: start identical, distance within 5 m (whole
    session), HealthFit power ~99% coverage.
  - 244 older HealthFit re-exports are shifted by whole hours; identity joins
    them by SHIFTED evidence.
- **Implications**: keys are distance, then power; the lag search window is
  −2..+2 s (the measured range 0..+1 plus one second each side); a stretch's
  lag must be unique and supported by a majority of compared samples and at
  least 5 matches, else the stretch falls back to exact timestamps; an extra
  whose start is a whole number of hours from the base's is first moved by
  those hours, reusing identity's own shift constants.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Pure core + one I/O adapter (selected) | `fitdocs.compose`: pure segmentation, alignment, donation and composition over `Activity`; one adapter (`compose.archive`) that resolves and parses listed files for the two passes | Golden- and mutation-testable in isolation; `sync` reuses its parsed members; load and benchmarks share one rule | A second package to guard | Mirrors `activity-identity`'s pure-core pattern |
| Composition inside `sync.py` | Put the composer beside the page task | No new package | `load` and `performance` cannot import `sync` (dependency direction); the rule would be duplicated | Rejected |
| Provenance as a model field | Add `Activity.channel_sources` | Travels with the activity | Widens the model contract and every golden JSON for a render concern | Rejected |
| Provenance in frontmatter | A managed key mapping channels to files | Machine-readable | No reader needs it; widens `MANAGED_KEYS`, `FORBIDDEN_LITERALS`, the ownership contract's key list; the page's `sources` already names every file | Rejected (Req 4.8) |

## Design Decisions

### Decision: Partial coverage leaves the base alone
- **Context**: The brief requires one stated rule for a channel the base
  records only partly (e.g. heart rate on 51% of a ride).
- **Alternatives Considered**:
  1. Fill only the base's gaps from the extra.
  2. Leave the base alone: a channel the base records at any sample is the
     base's in full, gaps included.
- **Selected Approach**: 2.
- **Rationale**: Filling gaps splices two sensors into one series, which is
  the blending the brief puts out of scope, and it turns "which file did this
  channel come from" into a per-sample question the page cannot answer in one
  line. A base gap may be a genuine dropout; filling it asserts a measurement
  the base's sensor did not make. The brief's own donation definition ("only
  when the base lacks it: absent, or entirely `None`") is already rule 2.
- **Trade-offs**: A half-covered base heart rate stays half-covered even when
  an extra has all of it; the athlete can rank the extra higher through
  `[identity] precedence` if they prefer it.
- **Follow-up**: Named mutation "fill base gaps" must red the 51%-coverage
  test.

### Decision: Gate pairs are donated independently
- **Context**: running-dynamics leaves open whether a balance channel and its
  stride channel (or air power and form power) must come from one file.
- **Alternatives Considered**:
  1. Donate a gated channel only together with its gate channel.
  2. Donate every channel independently; values are final.
- **Selected Approach**: 2.
- **Rationale**: The reason to bring the Stryd file onto a HealthFit page is,
  among others, stance-time balance, while the HealthFit copy already records
  stance time. Option 1 would never donate it. running-dynamics states that a
  gate pair may legitimately come from two files and that donated values are
  final.
- **Trade-offs**: At a sample where the base's stance time is absent and the
  extra's is not, the page may hold a balance value beside no stance time.
  The value is still the extra's own gated measurement.

### Decision: Position is one donation unit
- **Context**: `route-maps` asks whether position may be donated.
- **Selected Approach**: latitude and longitude form one unit: donated only
  when the base records neither, and both from the one highest-ranked extra
  that records both. The route map is then planned from the composed position.
- **Rationale**: A base without GPS (a treadmill phone copy, an indoor
  export) gains a route from the file that has one; mixing latitude from one
  file with longitude from another would draw a route neither file recorded.

### Decision: The page names each channel's file in its own section, not in frontmatter
- **Context**: Requirement 4; wiki-contract Amendment 4 "if channel-merge
  records it".
- **Selected Approach**: a `## Channel Sources` section after
  `## Device & Data Quality`, on pages with at least one extra; no
  frontmatter key.
- **Rationale**: see the pattern table above. The Amendment 4 part this spec
  lands is therefore a published-contract statement, not a key.

### Decision: Each contribution carries its own file's devices
- **Context**: `intervals-connector` attributes a page to "Garmin <model>"
  and words a page with other contributors as "... and other devices"
  (its Req 8.4). On the default ride pair (a Garmin-original base, a HealthFit
  copy donating heart rate) render needs the donating file's recording
  device, but render holds only `DocContext`, whose activity is the composed
  one and whose devices are the base's (Req 1.5).
- **Selected Approach** (ratified at the Phase 8 cross-spec review,
  2026-09-29): `SourceContribution` gains `devices: tuple[DeviceInfo, ...]`,
  the contributing file's own `Activity.devices`; the composed activity's
  devices stay the base's. Whichever of this spec and `intervals-connector`
  lands second wires `render/views.py::_head` to pass the donating extras'
  device tuples to `attribution_line(base, donor_devices)` and adds the
  ride-pair pin.
- **Rationale**: the attribution's wording stays `intervals-connector`'s;
  this spec only carries the data it cannot otherwise reach, with no model
  change and no donor `Activity` in render.

### Decision: The load and benchmark passes compose by the page's recorded order
- **Context**: Finding 1.
- **Alternatives Considered**:
  1. Re-rank the page's files with the current `[identity]` precedence.
  2. Trust the page's `sources` order: base last, extras nearer the end rank
     higher.
- **Selected Approach**: 2.
- **Rationale**: `sources` is written in canonical rank order by the page task
  that rendered the page, so option 2 composes exactly what the page shows,
  needs no settings read in either pass, and keeps both passes' "last `sources`
  entry is the base" reading (`load/engine.py:639-642`,
  `performance/engine.py:284-287`) true. A precedence change takes effect on
  the next `regen`, which rewrites `sources`, exactly as identity specifies.
- **Trade-offs**: A page written before `activity-identity` lists its files in
  arrival order; until regenerated it composes in that order. `fitdocs check`
  already reports such pages out of date.

### Decision: Contract version rule
- **Context**: The batch rule relayed to this spec: each spec advances each
  version at most once, from the value on `main` when it lands. At writing,
  `activity-identity` advanced `CONTRACT_VERSION` by one per lander while
  `connectors` kept `main`'s value when a sibling had already advanced it
  since the 0.1.0 release. The Phase 8 cross-spec review (2026-09-29) ratified
  one rule for all five specs.
- **Selected Approach (the ratified rule)**: `CONTRACT_VERSION` advances by one
  from the value on `main` when this spec lands -- every lander advances it,
  none shares another's advance. Precedent: effort-tags `"1"` to `"2"`
  (1b940b1), load-history `"2"` to `"3"` the same day (a6a0cfc),
  training-blocks `"3"` to `"4"` (022db69); the roadmap's Phase 8 shared seams
  say "Each bump lands once, in merge order, and the second lander re-pins";
  `docs/compatibility.md:101-102` states a bump costs users nothing. The
  landing task (5.2) therefore: replaces `docs/ownership-contract.md`'s "What
  changed at this version" paragraph with this spec's changes (the
  `CHANGELOG.md` is the cumulative record); adds a paragraph to the
  `CONTRACT_VERSION` docstring; always regenerates the declaration goldens;
  and, after the final rebase, asserts the value equals `main`'s plus one,
  re-pinning if a sibling landed first. `DOC_VERSION` follows the same
  one-per-lander rule (task 5.1).
- **Rationale**: this spec changes a stated guarantee (what an extra
  contributes to a page, and what the load and benchmark passes read), so it
  advances the version like every other guarantee change.

## Synthesis Outcomes
- **Generalization**: donation is one rule over "donation units" derived from
  the model (every `Samples` channel is a unit of one, position a unit of two),
  not a per-channel table; alignment is one rule over an ordered key list
  (distance, power). A future multi-channel unit is a one-line addition to the
  unit declaration.
- **Build vs adopt**: nothing to adopt. Cross-correlation, resampling or
  dynamic time warping were rejected: the measured drift is a whole-second
  lag constant within a stretch, and exact equality of an exactly reproduced
  channel is both sufficient and falsifiable, where a correlation score would
  need a tuned threshold with no measured basis.
- **Simplification**: no summary recomputation code (finding 2); no
  provenance key (decision above); no per-extra re-ranking in the passes
  (decision above); composition of a page with no extra returns the base
  unchanged, so single-file pages cannot move.

## Risks & Mitigations
- Short stretches between brief pauses fall back to exact timestamps (fewer
  than 5 matches) — acceptable: at most one second of offset over a short
  stretch, stated on the page.
- A lag that changes inside a stretch (no pause) is not detected — the stretch
  takes its majority lag; the measured drift only changed at pauses.
- Garmin smart recording (gaps of 2-7 s between samples) makes every gap a
  pause, so ride stretches become short and may fall back — stated on the page;
  the measured Garmin↔HealthFit starts agree to the second, so exact
  timestamps are the right fallback.
- Upstream identity tests pinning "an extra contributes nothing" (its
  Req 5.8) turn red by design when composition lands — the wiring task
  updates them to the composed expectation and lists each.
- Two or more Phase 8 specs advancing `CONTRACT_VERSION` and `DOC_VERSION` in
  one release window — each advances by one from `main` at landing; after the
  final rebase task 5.1 and task 5.2 assert `main`'s value plus one and re-pin
  the literals if a sibling landed first (Decision: Contract version rule).

## References
- `.kiro/specs/channel-merge/brief.md` — measured alignment facts (2026-09-24).
- `.kiro/specs/activity-identity/design.md` — roles, the `_render_activity`
  seam, `SourceKind`, the shift constants.
- `.kiro/specs/running-dynamics/design.md` — the channel set and the
  finality of donated values.
- `.kiro/steering/change-protocol.md` § Fixture Discrimination — the evidence
  gate every named mutation below answers to.
