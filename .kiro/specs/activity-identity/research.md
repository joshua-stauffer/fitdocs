# Research & Design Decisions: activity-identity

## Summary
- **Feature**: `activity-identity`
- **Discovery Scope**: Extension -- a complex integration inside the existing
  engine (ingest model, document contract, sync/regen/drain pipeline, audit),
  with no new runtime dependency and no network. Light discovery was run
  in-context by the spec writer (no research subagents were dispatched: the
  spec batch runs this writer as a subagent without an Agent tool, so every
  investigation below was done directly against the live tree at
  `a5792f2`).
- **Key Findings**:
  - Three readers resolve "the current source" as the **last** entry of a
    page's `sources` list: `sync._last_source_archive`
    (`src/fitdocs/sync.py:1444-1466`), the training-load pass
    (`src/fitdocs/load/engine.py:639-642`) and the performance pass
    (`src/fitdocs/performance/engine.py:284-287`). Keeping the base as the
    last entry leaves all three correct without an edit.
  - `fitdocs check` must read no `.fit` file (wiki-contract Req 8.8), so every
    identity fact it reports -- a page's base identity, a held file's
    candidates -- has to live in the page's frontmatter or in owned tool
    state, never be re-derived from the archive at inspection time.
  - Every synthetic fixture in `tests/fixtures/builder.py` starts its session
    at the same instant (`FIT_TIMESTAMP_BASE`, `builder.py:86`), and the run
    family (`run`, `run_native_power_sparse_hr`, `run_no_gps`,
    `session_dev_fields`, `reexport_a/b`) all record 9 s elapsed and 28.8-29.7 m.
    Under any calibrated rule they are one session; two existing tests put
    such a pair in one data root expecting two pages.

## Research Log

### The current identity path
- **Context**: what decides today whether a file updates a page.
- **Sources Consulted**: `src/fitdocs/sync.py`, `src/fitdocs/layout.py`,
  `src/fitdocs/render/frontmatter.py`, `src/fitdocs/contract.py`.
- **Findings**:
  - `_process_file` (`sync.py:1126`) skips a file whose
    `fit-archive/<sha>.fit` exists unless forced (`sync.py:1166-1170`), then
    calls `find_document` (`sync.py:236-291`): the first page in sorted
    order whose `uuid` equals the file's identity wins; otherwise the first
    page whose `sources` contains the file's ref.
  - `layout.activity_uid` (`layout.py:193-212`) is the formatted
    `SESSION UUID` developer field, else the sha.
    `build_frontmatter` writes `uuid` only when the rendered activity itself
    carries the field (`frontmatter.py:121-125`), so re-rendering a page from
    a file without one drops it.
  - A matched page keeps `match.path` while `doc_stem` is recomputed and
    every asset is named from the new stem (`sync.py:1269-1273`): a corrected
    start time leaves a stale filename and orphaned assets.
  - The source history is appended in arrival order with the new ref last
    (`sync.py:1255-1259`); arrival order therefore decides which file a page
    renders from today.
  - `find_document` re-scans every `workouts/*.md` frontmatter once per
    incoming file -- O(pages) reads per file.
- **Implications**: identity needs one scan per run, a canonical (not
  arrival) order, a rename step, and a session-UUID rule that is a function
  of the page's files rather than of the file being rendered.

### What `file_id` decodes to
- **Context**: Requirement 1 needs the raw identity values and their types.
- **Sources Consulted**: `garmin_fit_sdk/decoder.py` (installed version,
  profile 21.208.0); a scratch decode of `builder.run_fit_bytes()` and of
  encoded `file_id` messages with manufacturers `development`, `stryd` and
  `garmin`.
- **Findings**:
  - With the project's decode flags (`ingest/decode.py`:
    `convert_datetimes_to_dates=False`, SDK defaults otherwise), a
    `file_id` message decodes as
    `{'type': 'activity', 'manufacturer': 'garmin', 'product': 3843,
    'serial_number': 4242, 'time_created': 1000000000,
    'garmin_product': 'edge_1040'}`: `manufacturer` is the profile's name
    string, `product` stays the raw integer, `time_created` is raw FIT-epoch
    seconds, and `expand_sub_fields` adds a `garmin_product` name only for
    manufacturer `garmin` (name resolution is `intervals-connector`'s).
  - An unknown manufacturer number stays an `int`; the existing
    `ingest/_fields.str_or_none` already renders it as text faithfully.
  - A message whose global number the SDK profile lacks is decoded under the
    key `str(global_mesg_num)` (`decoder.py:260-266`). A scratch file with
    three spliced `0xFF01` messages (header data size and both CRCs
    recomputed with `garmin_fit_sdk.crc_calculator.CrcCalculator`) passed
    `is_fit` and `check_integrity` and decoded to `{'65281': [3 messages],
    ...}` with no decode error. Profile message keys all end in `_mesgs`, so
    "all-digit key" identifies exactly the undocumented messages.
- **Implications**: the undocumented-message count is computable from the
  decoded dict with no SDK change, and a test fixture can carry undocumented
  messages through a byte splice (the `Encoder` writes only profile
  messages).

### Distinguishing a partner-API copy from a device original
- **Context**: the roadmap decision (Phase 8, "Garmin rides come via
  intervals.icu") that a device original outranks the intervals.icu copy of
  the same ride, and this spec's constraint that kind is derived from the
  file's bytes, never from the connector that delivered it.
- **Sources Consulted**: `.kiro/steering/roadmap.md` Phase 8 Decisions;
  `.kiro/specs/intervals-connector/brief.md` (viability findings).
- **Findings**: intervals.icu serves Garmin's partner-API file, which keeps
  documented record fields but strips "undocumented messages and fields and
  workout steps" (between 2026-03-07 and 03-18 also messages 79, 140 and
  147). Nothing states that `file_id` differs, so a partner copy carries the
  device's manufacturer, serial and creation time. Whether it is
  byte-identical to Connect's "export original" is unverified.
- **Implications**: no absolute marker classifies a partner copy, but a
  *comparison* does: of two files of one recording, the partner copy carries
  fewer undocumented messages. The within-kind rank key "more undocumented
  messages first" realizes the decision without guessing; when the counts
  tie (a device that writes none, or two partner copies) the content-hash
  tie-break decides and no rendered value depends on it, because fitdocs
  reads no field Garmin strips.

### Who reads "the current source"
- **Context**: the brief's `sources` "stays the archive history"; the roles
  must not break existing readers.
- **Findings**: the three readers named in the Summary all take
  `sources[-1]`; `contract.source_refs`'s docstring
  (`contract.py:1071-1083`) and wiki-contract Req 1.3 state "the last entry
  is the current render source".
- **Implications**: the base is kept last. A canonical ascending-rank order
  (extras before, base last) is both order-independent and back-compatible.
  No separate "base" key is needed; a separate one would be a second truth
  a hand edit could make disagree with the first.

### `check` may not read `.fit` files
- **Context**: Requirement 8.
- **Sources Consulted**: `src/fitdocs/audit.py:1-60, 450-491`;
  wiki-contract Req 8.8.
- **Findings**: the audit reads `workouts/*.md` and the declarations only. A
  held file's identity cannot be recomputed there.
- **Implications**: the base identity goes on the page as managed keys; the
  held files and their candidates go into an owned record under `.fitdocs/`
  (the quarantine record, `src/fitdocs/quarantine.py`, is the pattern:
  content-keyed, sorted, atomic, write-if-different, no clock).

### The fixture corpus and the rule
- **Context**: an implementer will wire the rule into a suite whose fixtures
  were never built to be distinct sessions.
- **Sources Consulted**: `tests/fixtures/builder.py` (families and session
  values), every test module importing two or more builder fixtures.
- **Findings**:
  - Every builder `file_id` is `manufacturer="garmin", product=1,
    time_created=FIT_TIMESTAMP_BASE` with a per-fixture serial
    (`builder.py:146-154`); `session_dev_fields` and `ride_power_dropout`
    share serial 1014 but differ in sport.
  - Pairs that the strict rule joins and that existing tests put in one data
    root: `run` + `reexport_a` in
    `tests/test_sync.py::test_name_collision_between_activities_disambiguates`
    (`test_sync.py:556-572`, whose premise is "two DIFFERENT activities");
    `run_native_power_sparse_hr` + `run_no_gps` in `tests/test_portability.py`
    (`_FIXTURES`, `test_portability.py:68-74`, Δdistance 0.9 m).
  - `reexport_a`/`reexport_b` differ only in serial (1015/1016), so under a
    canonical rank their order falls to the content hash; four assertions pin
    the arrival order `[ref_a, ref_b]`: `tests/test_sync.py:610, 899, 916`
    and `tests/test_sync_e2e.py:299`.
  - `small_sport_fit_bytes` keeps `time_created` at `FIT_TIMESTAMP_BASE`
    whatever `timestamp_offset` is (`builder.py:351-399`), so a device rule
    that ignored the start would join two of its calls that share a serial;
    requiring the start to agree within 1 s removes the hazard.
- **Implications**: the rule is not widened or narrowed to suit the fixtures.
  The collided tests are re-shaped (distinct sessions made genuinely distinct;
  the re-export pair given distinct creation times so the rank reproduces
  the intended order), and the sweep is a task of its own, run after the
  planner is wired.

### Guards a new key, reader or version touches
- **Findings** (all verified):
  - `tests/test_contract.py:199-225` pins `MANAGED_KEYS` against a bare-string
    set, and `:260-298` derives the builder's emittable keys from every
    `data[<key>] = ...` assignment in `build_frontmatter`'s own AST -- so new
    keys must be assigned in that function, not in a helper.
  - `tests/test_contract_consumers.py:86-139` (`CONVERTED_MODULES`),
    `:170-296` (`CONTRACT_BINDINGS`, identity-checked) and `:298-306`
    (`FORBIDDEN_LITERALS`: the fence, `workout`, `date`, `start_time`,
    `sport`, `modality`, `indoor`). A module importing `fitdocs.contract`
    must be registered; a module that stops importing a bound name must be
    de-registered for that name.
  - `tests/metrics/test_sources.py:2270` holds
    `CONSTANT_REGISTRY_ASOF_DOC_VERSION = 5`, asserted **equal** to
    `contract.DOC_VERSION` while the constant registry is clean
    (`:2447-2470`); any `DOC_VERSION` advance re-pins it.
  - `tests/test_ownership_contract.py:81-137` pins the contract version, the
    owned paths, the regions and the managed and user-owned keys against
    `docs/ownership-contract.md`.
  - `tests/test_compatibility_policy.py:270` and `docs/compatibility.md:24,
    64` enumerate the settings file's tables ("six tables today"), and
    `docs/configuration.md:51-60` states the same count above a table with
    one row per table (a third site, found by the Phase 8 cross-spec review
    of 2026-09-29; controller ruling R4 advances all three per lander).
  - `tests/render/test_frontmatter.py:317-324` pins `DocContext`'s trailing
    field order (`field_names[-2:] == ["map_data", "user_frontmatter"]`), so
    appending `identity` reds it (found by the same review; task 3.1
    rewrites it position-relative).
  - `tests/golden/_serialize.py` walks every dataclass field of the model, so
    a new `Activity`/`Provenance` field changes `tests/golden/*.json`.
  - `tests/test_confinement.py:815-864` registers writing entry points; a
    rename deletes and creates paths the guard must see inside the permitted
    set.

### Plans reference logged pages by stem
- **Sources Consulted**: `src/fitdocs/plans/source.py:1014-1052` (override
  `stems`), `src/fitdocs/plans/corpus.py:112-191`, `src/fitdocs/cli.py:329,
  364, 449` (the plan pass chained after `sync`, drain and `regen`).
- **Findings**: block and planned pages are re-rendered by the chained pass,
  so their links follow a rename in the same command; an override in the
  athlete's plan source that names the old stem does not (fitdocs never
  writes the plan source) and surfaces as plan-resolution's own per-file
  failure.
- **Implications**: every rename is reported with both paths; fixing an
  override stays the athlete's.

### Sibling briefs and the default precedence
- **Context**: the parallel specs' briefs state expectations about which
  file is base.
- **Findings**: this spec's brief names "a Stryd run file" among device
  originals and asks for a default that ranks a device original above a
  phone-side copy. `.kiro/specs/channel-merge/brief.md` describes runs as "A
  HealthFit copy (the base ...) plus the Stryd file", and the roadmap's
  rejection of *best file wins* notes that only the HealthFit copy carries
  the session UUID, the session summaries and the HR laps.
- **Implications**: the two statements conflict for Stryd runs. The writer
  raised the conflict; the controller put it to the maintainer.
- **Resolution (maintainer decision 2026-09-29)**: "HealthFit base, by the
  reasoning that it's the source we got the fit file from. If garmin rides only
  come through healthfit, i would expect that they're marked a phone copy
  (HealthFit) as well." The default precedence is therefore `original:garmin`,
  `phone_copy`, `original`, `unknown`: Garmin files (device original, Connect
  export, partner-API copy) outrank the HealthFit copy on rides; the HealthFit
  copy outranks a Stryd file on runs, matching channel-merge's brief; a
  HealthFit copy is `phone_copy` whatever device recorded the activity, because
  HealthFit writes its own `file_id` (`development`).

### Performance of one scan per run
- **Findings**: `find_document` reads every page per incoming file; the
  2026-09-12 adoption (772 files, ~2500 pages) paid ~1.9 M frontmatter reads.
  A per-run page index is read once.
- **Implications**: the planner reads the index once per run; each task
  re-reads only its own page's text for the merge.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Sequential per-file matching | Each file is matched against the corpus as it stands when the file is processed | Smallest change to `_process_file` | Two files that each match a page but not each other are decided by processing order; a run's own new files cannot be grouped symmetrically | Rejected: contradicts "arrival order decides nothing" |
| Per-run plan (selected) | All of a run's files are identified first, grouped and assigned by a pure planner over a one-scan page index; pages are then written per task | Order-independent within a run; one corpus scan per run; the planner is pure and permutation-testable | New files are parsed twice (plan, then task); the pipeline restructures from per-file to per-task | The parse cost falls only on files not yet archived |
| Per-member identity on the page | Every file of a page records its identity values in frontmatter | Matching against extras, no member parse on join | Verbose frontmatter; a second copy of what the archive holds; channel-merge parses extras anyway | Rejected in favour of base values on the page and member parses at write time |
| Base identity on the page (selected) | Only the base's identity values are managed keys | Compact; `check` can compare pages; one truth per page | A file matching only an extra is not matched through it | Under the default precedence a device file becomes base when it joins, so later copies meet the true values |
| Ambiguous file becomes its own page | Today's behaviour for any unmatched file | No new state | A duplicate page and double-counted load; the defect this spec removes | Rejected |
| Ambiguous file left unarchived in the inbox | Version-gate precedent | No page, retried every run | `check` cannot see it without a record keyed to a file outside the data root; stale records | Rejected |
| Ambiguous file archived and held (selected) | Archived, no page, recorded under `.fitdocs/` | "Archive presence = processed" holds; inbox disposes of it; `check` reports it; regeneration re-derives the record | One more owned state file | The record is re-derivable: every held file is an archived file no page lists |

## Design Decisions

### Decision: the base stays the last `sources` entry, in canonical rank order
- **Context**: roles on the page without breaking three `sources[-1]`
  readers, and byte-identical pages whatever the arrival order.
- **Alternatives Considered**:
  1. A separate `base_source` key -- a second truth.
  2. Arrival-order history with the base moved last -- order-dependent bytes.
- **Selected Approach**: `sources` lists every file in ascending rank;
  unresolvable refs first in their existing relative order; the base last.
- **Rationale**: zero edits to the load, performance and regen readers; the
  page is a function of its file set.
- **Trade-offs**: `sources` no longer shows arrival order. Nothing reads it.
- **Follow-up**: re-pin the four arrival-order assertions (research above).

### Decision: tiered evidence, with timer time excluded
- **Context**: the measured pairs (roadmap Phase 8 Constraints).
- **Selected Approach**: `DEVICE` (same manufacturer, serial, creation time,
  sport, starts within 1 s), `STRICT` (sport, start within 1 s, elapsed within
  10 s, distance within 5 m when both record one), `SHIFTED` (one side a
  `phone_copy`, whole-hour shift of 1-36 h within 1 s, elapsed within 5 s,
  distance within 10 m). Any tier is evidence; the tier is kept only to report.
- **Rationale**: start agreement to the second is the discriminator the
  counter-example (two similar 10 k runs) lacked; elapsed and distance
  corroborate; the whole-hour shift is the only measured start disagreement
  and was measured only on HealthFit re-exports.
- **Tolerance derivation**: start 1 s -- every measured pair agreed to the
  second, and a writer that truncates a sub-second start differs from one
  that rounds it by at most 1 s; elapsed 10 s -- the largest measured
  difference (Stryd↔HealthFit, 9 s) plus that same 1 s; distance 5 m -- the
  measured Garmin↔HealthFit bound (Stryd↔HealthFit agree to 0.01 m);
  shifted 5 s / 10 m / 36 h -- the 2026-09-12 adoption rule, whose true pairs
  agreed to ≤ 1 s and ≤ 1 m (queue item's Evidence).

### Decision: a per-run planner with groups and claims
- **Selected Approach**: files pinned by the exact paths (sha in `sources`,
  equal `uuid`) always join; the rest form groups (connected components under
  the pair rule, including links through pinned files); a group joins the one
  page it matches when no other group claims that page; a group matching no
  page is one new page; everything else is held.
- **Rationale**: realizes both ambiguity clauses of the brief symmetrically.

### Decision: rename only on a base change, in a crash-healing order
- **Selected Approach**: new assets → previous render's assets removed →
  document moved (`os.replace`) → document written → archives last; a settle
  pass renames suffixed pages whose unsuffixed name freed up during the run.
- **Rationale**: every interruption leaves the page at exactly one path and
  the next run completes the rename (research: crash windows analysed in
  design.md, Page task). User renames and timezone changes keep today's
  filename behaviour.

### Decision: a digest, not the serial, on the page
- **Context**: wikis are often pushed to a remote; a device serial is a
  stable identifier of the athlete's hardware.
- **Selected Approach**: `source_device` is the first 16 hex digits of the
  SHA-256 of `<manufacturer>/<serial>/<creation time>`; matching needs only
  equality.

## Risks & Mitigations
- Fixture collisions redden unrelated tests when the planner lands --
  mitigated by the dedicated sweep task and a named list of expected
  collisions.
- `sync.py` restructuring touches the three entry points at once -- mitigated
  by landing roles/rendering (no planner) first, then rename, then the
  planner, each reviewer-gated.
- The Stryd default once conflicted with `channel-merge`'s brief -- resolved
  by the maintainer decision of 2026-09-29 (HealthFit copy above a Stryd file).
- A partner copy with as many undocumented messages as the original ranks by
  hash -- no rendered value depends on it (fitdocs reads no stripped field).
- Pages written before this feature match only by exact paths until
  regenerated -- the document-format advance makes `check` name every one,
  and the upgrade documentation says to regenerate before pulling.

## References
- `.kiro/specs/activity-identity/brief.md` -- scope, measured pairs, constraints.
- `.kiro/steering/roadmap.md` § Phase 8 -- decisions, constraints, seams.
- `.kiro/queue/closed/2026-09-12-adopting-a-higher-fidelity-re-export-needs-a-hand-edit.md` -- the 2026-09-12 rule and its evidence.
- `.kiro/specs/channel-merge/brief.md`, `.kiro/specs/intervals-connector/brief.md`, `.kiro/specs/running-dynamics/brief.md`, `.kiro/specs/connectors/brief.md` -- sibling expectations.
- Garmin FIT SDK (installed `garmin-fit-sdk`, profile 21.208.0) -- decoder behaviour for sub-fields and unknown messages.
