# Implementation Plan

## Upstream Prerequisites

- **Both upstream specs must be merged to `main` before task 1.1 starts**:
  `activity-identity` (roles, the page task, `_render_activity(roles, parsed)`,
  `DocContext.identity`, the identity fixtures in `tests/fixtures/identity.py`,
  its part of the wiki-contract Amendment 4 section) and `running-dynamics`
  (the 22-channel `Samples`, `DYNAMICS_CHANNELS`,
  `Activity.record_developer_fields`, the
  Running Dynamics section, `stryd_run_fit_bytes` and the developer-field
  encoding helper `developer_field_run_fit_bytes`, with its keyword-only
  `session_fields` option, in `tests/fixtures/builder.py`). A task that finds a
  published upstream shape different from design.md § "Cross-spec seams" stops
  and reports rather than adapting silently.
- **Siblings in flight** (`connectors`, `intervals-connector`, `docs-site`):
  no code dependency; the shared files are listed below. One seam is decided
  by landing order: whichever of this spec and `intervals-connector` lands
  second wires `render/views.py::_head` to pass the donating extras' devices
  to `attribution_line` and adds the ride-pair attribution pin (design.md
  § "Cross-spec seams"; task 3.3).

**Hard rules for every task**

- No module under `src/fitdocs/compose/` imports `fitdocs.sync`,
  `fitdocs.render`, `fitdocs.load`, `fitdocs.metrics`, `fitdocs.performance`,
  `fitdocs.history`, `fitdocs.plans`, `fitdocs.audit`, `fitdocs.cli`,
  `fitdocs.tiles`, `fitdocs.inbox`, `fitdocs.connectors`, `yaml`, `urllib`,
  `socket` or `time`, or names a clock function. Only `compose/archive.py`
  touches the filesystem or imports `fitdocs.contract`, `fitdocs.layout` or
  `fitdocs.ingest`. No module under `src/fitdocs/render/` imports
  `fitdocs.compose.archive`.
- No alignment constant (`PAUSE_GAP_S`, `MAX_LAG_S`, `MIN_MATCHED_SAMPLES`,
  `ALIGNMENT_KEYS`) is changed to make a test pass; a fixture the rule does not
  read as intended is re-shaped so the test's premise holds.
- Absent is `None`: no task writes a default, a `0`, an interpolated or a
  carried-forward value for a sample no file recorded at that instant.
- No fixture holds personal data: every `.fit` input is synthesized through
  `tests/fixtures/builder.py`, `tests/fixtures/identity.py` or
  `tests/fixtures/merge.py`; no value comes from the athlete's archive.
- No module under `src/fitdocs` other than `contract.py` names `uuid` as an
  identifier (`tests/test_contract_consumers.py:502-529`); no registered
  contract consumer defines a name in `FORBIDDEN_LOCAL_NAMES` (`:149-163`) or
  spells a `FORBIDDEN_LITERALS` value (`:298`).
- `DOC_VERSION` and `CONTRACT_VERSION` each advance by **one from the value on
  the branch when the task runs**; after the final rebase the implementer checks
  each equals `main`'s value plus one and re-pins if a sibling landed a bump
  first. No task hard-codes a resulting number.
- After the final rebase, if `intervals-connector` landed on `main` while this
  branch was open and `render/views.py::_head` does not yet pass donor
  devices, task 3.3's attribution step runs then, with its pins and named
  mutations (this spec is the second lander).
- No Stryd web or service address anywhere (Req 9.3): before a task is done,
  `grep -rniE "https?://[^ )]*stryd" <files the task changed>` prints nothing.
  Stryd developer-field names are file-format knowledge and are fine.
- Mutations run through `uv run pytest` only (`change-protocol.md`
  § Fixture Discrimination); each named mutation is applied, observed red,
  reverted, observed green, and recorded in the task's Implementation Notes.
  A task that cannot make a listed mutation red stops and reports it as
  UNPINNED rather than weakening the assertion's wording.
- Every task that creates a typed test or fixture module type-checks it clean
  with `uv run mypy <its paths>`; task 6.1 registers them all in
  `pyproject.toml` (the file's own rule, `pyproject.toml:97-98`), so parallel
  tasks never share `pyproject.toml`.
- Every task's Observable includes `uv run ruff check <files it changed>` and
  `uv run ruff format --check <files it changed>` clean, so lint and format
  debt never accumulates for the final task.
- A task that finds it needs a new runtime dependency, a new command, a new
  owned path, a frontmatter key, or a change to an upstream seam's shape beyond
  what design.md § "Cross-spec seams" authorizes stops and reports.

## Shared source files

Each file below has more than one writer in this plan; its writers are
sequential (never both `(P)` at once).

- `src/fitdocs/compose/types.py` -- 1.2 only; later tasks import it and never
  edit it (a missing field is a stop-and-report).
- `tests/compose/builders.py` -- 1.2 only; later tasks build activities with it
  and keep any extra helper local to their own test module.
- `tests/compose/test_boundary.py` -- 1.2 (created, subset positive control),
  3.1 (tightened to the exact seven-module set).
- `src/fitdocs/render/views.py` -- 3.3 only (its attribution step, when
  deferred to the final rebase, is still 3.3's). `src/fitdocs/render/__init__.py`
  -- 3.2 only. `src/fitdocs/sync.py` -- 4.1 only.
  `src/fitdocs/load/engine.py`, `src/fitdocs/performance/engine.py` -- 4.3
  only.
- `src/fitdocs/contract.py` -- 5.1 (`DOC_VERSION`), 5.2 (`CONTRACT_VERSION`).
- `tests/render/test_frontmatter.py` -- 3.2 (the `DocContext` field-order pin),
  5.1 (the `DOC_VERSION` literal pins).
- `tests/render/test_golden_docs.py` and `tests/render/golden_docs/*` -- 3.3
  (the `composed_run` case), 5.1 (every golden's `doc_version` line).
- `tests/test_compose_e2e.py` -- 4.1 (seam section), 4.2 (composed-page
  sections), 5.1 (aged-page section); each edits only its own headed section.
- Pre-existing tests of multi-file pages -- 4.1 updates those whose page body
  moves; 4.3 updates those whose load or benchmark outcome moves. 4.3 runs after
  4.2 and may amend a test 4.1 already updated, listing it.
- `pyproject.toml` -- 6.1 only.

**Cross-spec shared files** (append a field, a row, an entry or a block; never
rewrite or reorder a sibling's):
- `src/fitdocs/render/__init__.py` and `src/fitdocs/render/views.py`, shared
  with `activity-identity`, `running-dynamics` and `intervals-connector`,
  append-only: `DocContext` (identity appended `identity`; this plan appends
  `channel_provenance`); the views (running-dynamics adds its Running
  Dynamics section call, `intervals-connector` its `_head` and attribution
  line; this plan appends the Channel Sources call per view and, as second
  lander only, the `donor_devices` argument at `_head`'s one call).
- `src/fitdocs/contract.py` (`DOC_VERSION`, `CONTRACT_VERSION`; every Phase 8
  spec advances each once), `tests/test_contract_consumers.py`, the golden
  directories, `tests/declaration_golden/*`.
- `docs/ownership-contract.md` (each lander replaces "What changed at this
  version" with its own changes), `CHANGELOG.md` `[Unreleased]` (append under
  an existing category heading; create it only if absent).
- `.kiro/specs/wiki-contract/requirements.md` Amendment 4 (created by
  whichever of `activity-identity`, `connectors` and `channel-merge` lands
  first; each appends its own paragraph), and the amendment records of
  `workout-docs` (running-dynamics, activity-identity and intervals-connector
  also amend it): numbers are taken on the branch at landing.
- `.kiro/steering/structure.md` (the dependency line: `activity-identity`
  appends `identity`, `connectors` its package, this plan `compose`) and
  `.kiro/steering/roadmap.md` (Phase 8 Existing Spec Updates annotations and
  ticks).
- `tests/fixtures/builder.py`: this plan appends to running-dynamics'
  `developer_field_run_fit_bytes` only the keyword-only, defaulted parameters
  design.md § "Cross-spec seams" pre-authorizes (`laps`, `session_start`,
  `session_elapsed_s`, `session_distance_m`, `sport`), each only if the
  merged helper lacks that capability, each default equal to the helper's
  current behaviour; the `SESSION UUID` goes through the helper's existing
  `session_fields` option.

## Test File Ownership

- `tests/fixtures/merge.py`, `tests/fixtures/test_merge_fixtures.py`, and the
  `tests/fixtures/test_builder.py` pin for any appended helper parameter → 1.1.
- `tests/compose/__init__.py`, `tests/compose/builders.py`,
  `tests/compose/test_types.py`, `tests/compose/test_boundary.py` → 1.2 (3.1
  tightens `test_boundary.py`).
- `tests/compose/test_stretches.py` → 2.1; `test_donation.py` → 2.2;
  `test_alignment.py` → 2.3; `test_composer.py` → 2.4 (unit section) and 2.5
  (measured-pair section; 2.5 adds its own headed section and edits nothing of
  2.4's).
- `tests/compose/test_archive.py`, the `fitdocs.compose.archive` entries in
  `tests/test_contract_consumers.py` → 3.1.
- `tests/render/test_provenance.py` (section and reverse-direction guard),
  `tests/render/test_frontmatter.py:317-324` (the field-order pin) → 3.2.
- `tests/render/test_golden_docs.py` (`composed_run`), a views section in
  `tests/render/test_provenance.py` (with the attribution pins when this spec
  is the second lander) → 3.3.
- `tests/test_compose_e2e.py` → 4.1 (seam section), 4.2 (arrival order, regen,
  drain, ride average heart rate, filename and `uuid`), 5.1 (aged page).
- The pre-existing multi-file page tests whose body moves → 4.1; whose load or
  benchmark outcome moves → 4.3.
- `tests/test_compose_passes_e2e.py` → 4.3.
- `tests/compose/test_contract_docs.py`, `tests/declaration_golden/*`
  (regenerated) → 5.2.
- DOC_VERSION literal re-pins (`tests/render/test_frontmatter.py:44, 101`,
  `tests/metrics/test_sources.py:2270`, grep decides) → 5.1.

---

- [x] 1. Foundation: measured-shape fixtures and the package skeleton

- [x] 1.1 Synthesize the run, trio and ride fixtures with the measured alignment shapes
  - First, check the merged developer-field helper
    `developer_field_run_fit_bytes` in `tests/fixtures/builder.py` against
    what these fixtures need through it: per-file laps (count and values,
    heart rate included), session start, elapsed time and distance, a cycling
    sport, the HealthFit `SESSION UUID` session developer field (through the
    helper's existing keyword-only `session_fields` option), and `file_id`
    and recording-device manufacturers that are not Garmin (through its
    existing `manufacturer`, which defaults to `garmin`, and
    `device_manufacturer`, whose `None` default follows `manufacturer`;
    every file passes both explicitly: each Stryd file `"stryd"` for both,
    each HealthFit copy, run and ride, `"development"` for both). For each of
    `laps`, `session_start`, `session_elapsed_s`, `session_distance_m` and
    `sport` the helper lacks, append that keyword-only parameter, defaulting
    to the helper's current behaviour, and pin in
    `tests/fixtures/test_builder.py` that the helper's default output bytes
    are unchanged (named mutation: change one appended parameter's default --
    the default-bytes pin reds). Any other missing capability: stop and
    report. The Garmin ride original, which carries no developer field, may be
    built from the existing `builder.encode(mesgs)` primitives instead
  - In a new fixture module, build the run pair (a HealthFit-shaped copy and a
    Stryd-shaped file of one synthetic run), the run trio (the pair plus a
    second Stryd file with a later creation time and form power one watt higher
    everywhere) and the ride pair (a Garmin-shaped original without heart rate
    and a HealthFit-shaped copy carrying heart rate, with keyword options for
    the copy's power and a whole-hour shift), exactly as design.md
    § "Supporting References" specifies: five stretches with lags +1, +1, 0,
    +1, 0 on distance and power; heart rate at −1; three trailing base samples;
    step length 0.8% higher and cadence ±1 in the extra; the HealthFit copy
    recording every non-dynamics channel the Stryd file records (heart rate,
    power, distance, speed, cadence); pairwise-distinct values within every
    channel of every stretch; the ride's identical start, ~99% copy power
    coverage, per-sample distance that never agrees with the original's; the
    Stryd files built with `manufacturer="stryd"` and
    `device_manufacturer="stryd"`, the HealthFit copies with
    `"development"` for both
  - Shape self-tests decode the raw messages (no fitdocs code between) and
    assert every premise later tasks rely on: per stretch, the HealthFit
    distance and power at `t + L_k` equal the Stryd values at `t` for every
    compared sample and at no other lag in −2..+2 for at least half of them;
    heart rate agrees at −1 and at neither 0 nor +1; the three trailing
    instants; the step-length ratio and cadence offsets; the channels the Stryd
    file records and the HealthFit copy does not are a subset of
    `DYNAMICS_CHANNELS`; the Stryd file has no position; lap counts differ
    (Stryd 4, HealthFit 5, HealthFit's with heart rate); the ride copy's power
    is missing on exactly one sample and equals the original's at the same
    instant elsewhere; in every ride stretch, at every lag in −2..+2, the copy's
    distance matches the original's (to 0.005 m) at fewer than
    `MIN_MATCHED_SAMPLES` samples or at no more than half of the compared ones,
    while the session totals are within 5 m; the ride original's `device_info`
    at index 0 names manufacturer `garmin` and the ride copy's names
    `development` (the premise of the ride-pair attribution pin, design.md
    § "Cross-spec seams"); the run pair's and trio's recording devices
    (`device_info` index 0) are non-Garmin -- `stryd` on each Stryd file,
    `development` on the HealthFit copy -- and so are their `file_id`
    manufacturers (the premise that the `composed_run` golden carries no
    `Data source` line); building each fixture twice gives identical bytes
  - The HealthFit copies' `development` recording device is a synthetic
    variant pending `intervals-connector`'s live-check TBC-9 (what a real
    HealthFit copy records at `device_info` index 0; design.md § "Supporting
    References", Ride pair, "HealthFit recording device"); no value changes
    now. Implementation Notes name the pins that rest on it and are
    revisited if the check finds a Garmin device there: the ride-pair
    attribution pin (M25, or `intervals-connector`'s 2.3 pin) and the
    `composed_run` golden's no-`Data source`-line claim (3.3), with the
    recording-device self-tests above
  - Assert that `activity-identity`'s rule joins each pair and the trio
    (`pair_evidence` between every two files' session keys is not `None`: STRICT
    for the run files and the unshifted ride, SHIFTED for the shifted ride), and
    that under the default precedence the HealthFit copy ranks above both Stryd
    files, `stryd_b` above `stryd_a`, and the Garmin original above the ride
    copy
  - Discrimination: no production code is involved; for each self-test, record
    in Implementation Notes the fixture edit that makes it fail (e.g. setting
    `L_3` to +1 reds the per-stretch lag self-test; dropping speed from the
    HealthFit copy reds the subset self-test; giving the ride copy a Garmin
    recording device reds the ride recording-device self-test; building a
    Stryd file with `device_manufacturer="garmin"` reds the run
    recording-device self-test)
  - Observable: `uv run pytest tests/fixtures/` green; `uv run mypy
    tests/fixtures/merge.py tests/fixtures/test_merge_fixtures.py` clean; ruff
    check and format clean on the changed files; no file under `src/` changed;
    every pre-existing fixture test unchanged
  - _Requirements: 9.1, 9.3_

- [x] 1.2 Create the composition package, its result types and its boundary guard
  - Create the package as a marker that re-exports nothing, and its types
    module with the stretch lag, extra alignment, placement, source
    contribution, channel provenance and composition values exactly as
    design.md § ComposeTypes states (frozen, typed, `SourceKind` from
    `activity-identity`), the source contribution carrying `devices:
    tuple[DeviceInfo, ...]` (the contributing file's own `Activity.devices`,
    which `intervals-connector`'s attribution reads) between `manufacturer`
    and `channels`
  - A seam pin (`tests/compose/test_types.py`): the source contribution's
    field names, in order, are `sha256, kind, manufacturer, devices,
    channels, alignment`, and `devices` is annotated
    `tuple[DeviceInfo, ...]`; its value is pinned by 2.4
  - Add the hand-built activity builders the pure unit tests use: an activity
    from a recorded start, a list of per-sample offsets and keyword channel
    arrays (every omitted channel all-`None`), with optional laps, session
    values, file identity and devices; no FIT bytes
  - Add the import-closure guard over `src/fitdocs/compose/`: a per-module
    allowlist for all seven planned modules (design.md § Allowed Dependencies),
    the forbidden-import and clock-name checks, and a positive control that
    every scanned module has an allowlist entry and the walk found the types
    module
  - Pin the package marker's `__all__` as empty and that the root package
    re-exports no composition name
  - Named mutations: add `import fitdocs.sync` to the types module (the guard
    reds); point the walk at an empty directory (the positive control reds);
    drop `devices` from the source contribution, or move it after `channels`
    (the seam pin reds, design.md M24)
  - Observable: `uv run pytest tests/compose/` green; `uv run mypy
    src/fitdocs/compose tests/compose` clean; ruff check and format clean; the
    full suite still green with no existing test edited
  - _Requirements: 7.2_

- [x] 2. Core: the pure composition rules

- [x] 2.1 (P) Put samples on a whole-second clock and cut stretches at the pauses of either file
  - Instants: each sample's recorded start plus its offset as a whole POSIX
    second; `None` when the activity records no start or the instant is not a
    whole second
  - Resume instants: the first instant after every gap of more than 1 second
  - Stretches of an extra: cut points are the resume instants of the extra and
    of the base; a sample belongs to the stretch numbered by how many cut
    points are at or before its instant; samples without an instant belong to
    none
  - Tests (hand-built, pairwise-distinct instants): a 1 s step never splits and
    a 2 s step does; a base pause splits an otherwise continuous extra run; an
    extra pause the base lacks splits it; the sample exactly at a resume
    instant opens the new stretch; a non-whole offset has no instant; two
    activities with different starts and equal offsets have different instants
  - Named mutations: cut on the extra's pauses only; `>=` for the gap test;
    count cut points with `<`; compute instants from the offset without the
    start; round a non-whole instant instead of dropping it
  - Observable: `uv run pytest tests/compose/test_stretches.py` green with each
    mutation observed red; `uv run mypy` clean on the module and its test; ruff
    check and format clean
  - _Requirements: 3.1, 3.2_
  - _Boundary: Stretches_

- [x] 2.2 (P) Define the donation units and the base-wins rule
  - Donation units derived from the model's per-sample channel set at import:
    every channel but the time offset, in field order, each its own unit except
    latitude and longitude, which form one position unit at latitude's place
  - The base keeps a unit when it records any channel of it at any sample (the
    base-wins and partial-coverage rule in one test); an extra's placed values
    are, per base sample, the extra's value at the placed index or `None`
  - Tests: the units cover exactly every channel but the time offset, and
    contain every running-dynamics channel name (the positive control that the
    upstream channel set is enumerated); position is one unit of two; the base
    keeps a channel recorded on 51% of samples and one recorded at a single
    sample; placed values follow a non-identity placement and leave unplaced
    base samples `None`, never `0`
  - Named mutations: require every sample recorded for the base to keep a unit
    (the 51% test reds); split position into two units; drop one channel from
    the units (the coverage test reds); index placed values by base position
    instead of the placement; fill unplaced samples with `0`
  - Observable: `uv run pytest tests/compose/test_donation.py` green with each
    mutation observed red; the module imports only the types module, the model
    and the standard library (the boundary guard stays green); ruff check and
    format clean
  - _Requirements: 2.1, 2.2, 2.4, 2.5, 2.6, 2.8_
  - _Boundary: Donation_

- [x] 2.3 Establish each stretch's lag and place an extra on the base's timeline
  - The alignment keys (distance at 0.01 m resolution, then power at 1 W), the
    lag window −2..+2 s, the minimum of 5 matched samples, and a one-line source
    for each constant, as design.md § Alignment tabulates
  - The whole-hour shift from the two recorded starts, reusing identity's shift
    and start-tolerance constants by import
  - The lag rule: the unique lag with the most matches, at least 5 of them and
    more than half of the samples compared at that lag; distance first, then
    power; otherwise the stretch falls back to lag 0 and records no key
  - Placement: stretches and samples in file order; a sample lands on the first
    base sample holding its instant plus the stretch's lag, when that base
    sample exists and nothing was placed there before; otherwise it is dropped
  - Tests (hand-built): two stretches with lags +1 and 0 each placed by their
    own lag; heart rate matching at −1 against distance at +1 (the distance lag
    wins); distance establishing +1 where power would give 0; power used when
    the extra has no distance; a stationary stretch (distance constant) falls
    back; power matching 5 of 20 compared samples falls back; 4 matches fall
    back; duplicated base instants take the first index; two samples claiming
    one base sample (a base pause cutting a continuous extra run) keep the
    first; the hour shift at k = 1 and 36 applied, at 37 not, 1 s off a whole
    hour applied and 2 s off not
  - Named mutations: apply the first stretch's lag to every stretch; lead the
    keys with heart rate; put power before distance; drop the uniqueness
    condition; drop the majority condition; set the minimum to 0; place at
    instant minus lag; take the last index of a duplicated instant; let a later
    sample overwrite an earlier placement; drop the hour shift; allow k up to 37
  - Observable: `uv run pytest tests/compose/test_alignment.py` green with every
    mutation observed red; a test asserts the alignment keys are exactly
    distance then power; ruff check and format clean
  - _Requirements: 2.6, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - _Depends: 2.1_

- [x] 2.4 Compose one activity and its channel provenance from a base and ranked extras
  - With no extra, return a composition whose activity is the base object
    itself and whose provenance lists the base's recorded channels
  - Otherwise: open units are those the base does not keep; each extra in rank
    order that records any open unit's channel is aligned against the base
    alone, and every still-open unit whose placed values record every channel
    of the unit is donated from it and closed; donated channels replace the
    base's in a copy of the base's samples; everything else (laps, sets,
    devices, session values, session and record developer fields, provenance,
    sport, start) is the base's
  - Provenance: the base's contribution lists the channels it records; each
    extra's lists the channels donated from it, with its alignment only when it
    donated; every contribution carries its own file's content hash, source
    kind, recorded manufacturer and devices, whether or not it donated
  - Tests (hand-built, pairwise-distinct values): the composed offsets equal the
    base's; a channel the base records stays the base's; a base channel on 51%
    of samples keeps its gaps while an extra records all of it; two extras
    recording one open channel donate the higher-ranked one's values; an extra
    whose values land on no base instant is skipped for the next extra; position
    comes whole from the one extra recording both coordinates when a
    higher-ranked extra records only latitude; a donated balance keeps its
    values where the base's stance time is `None`; laps, session values and
    record developer fields equal the base's; an extra donating nothing has no
    channels and no alignment; with a base and two extras holding
    pairwise-distinct device tuples, one extra donating nothing, each
    contribution's devices equal its own file's and the composed activity's
    devices equal the base's; the same inputs compose to equal results twice
  - Named mutations: skip the base-keeps check; require every sample for the
    base to keep a unit; fill base gaps (keep the base's values and fill its
    `None` samples from the extra's placed values; the 51% test reds); iterate
    extras worst first; donate a unit when the extra records any (not every)
    channel of it; decide donation on the extra's raw values instead of its
    placed values; take the extra's laps; take the extra's session summary;
    carry the extra's record developer fields; insert a pass that nulls a
    donated balance where the composed stance time is `None`; return a rebuilt
    activity instead of the base object when there is no extra; attach an
    alignment to an extra that donated nothing; give every contribution the
    base's devices (the per-contribution devices test reds, design.md M23)
  - Observable: `uv run pytest tests/compose/test_composer.py` green with every
    mutation observed red; `uv run mypy` clean; ruff check and format clean
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.7, 3.10, 5.2, 5.4, 7.1_
  - _Depends: 2.2, 2.3_

- [x] 2.5 Prove the composition on the measured-shape fixtures
  - In its own headed section of the composer tests, parse the run pair, the
    run trio and the ride pair from `tests/fixtures/merge.py` and compose them
  - Run pair: at every stretch's first and last placed base sample, the composed
    form power equals the Stryd value at that instant minus the stretch's own
    lag; the stretches report key `distance` five times and lags +1, +1, 0, +1,
    0; the three trailing base samples hold `None` in every donated channel;
    composed step length and cadence equal the HealthFit values; composed laps
    equal the HealthFit laps; every donated channel is a running-dynamics
    channel, and `compute_metrics` of the composition equals that of the base
    alone in every field (no metric is fed by a dynamics channel)
  - Ride pair: heart rate is donated with every stretch aligned by power at lag
    0; the composition's average heart rate from `compute_metrics` equals the
    mean of the donated values while the base alone has none; every metric
    field not computed from heart rate equals the base-only value (the test
    names the heart-rate-fed fields it excludes, read from the metrics code);
    with no copy power every stretch falls back; with the copy shifted +1 h the
    alignment records `hour_shift_s == 3600` and heart rate lands on the same
    base samples as unshifted
  - Partial coverage on measured shapes: the run pair's HealthFit copy with its
    heart rate trimmed to 51% of samples composes to exactly the trimmed heart
    rate, gaps `None`
  - Named mutations, with Req 9.2's five mapped in Implementation Notes: apply
    one lag to every stretch (M1); skip the base-keeps check (M2); lead the keys
    with heart rate (M3); take the extra's laps (M4); fill base gaps from the
    extra's placed values (M5, the trimmed heart-rate test reds); require every
    sample for the base to keep a unit (the trimmed test reds too); return the
    base without donating (the average-heart-rate assertion reds); drop the
    hour shift (the shifted ride's heart rate reds)
  - Observable: the measured-pair section green with every mutation observed
    red; ruff check and format clean
  - _Requirements: 2.1, 2.2, 3.3, 3.5, 3.6, 3.8, 5.1, 5.3, 9.1, 9.2_
  - _Depends: 1.1_

- [x] 3. The archive adapter and the Channel Sources section

- [x] 3.1 (P) Compose a page's listed archived files for the passes that hold only `sources`
  - Given the data root, a page's listed refs and the activity the caller
    already parsed from the last ref: extras are the other refs in reverse list
    order; a ref that does not resolve to an archive ref, repeats the base's or
    an earlier extra's content hash, or names a missing archive file is
    skipped; each remaining one is parsed, with read and decode errors
    propagating; the result is the composition of the base and those extras
  - Register the module as a contract consumer binding only the archive-ref
    reader, and tighten the boundary guard so the scanned set equals the seven
    allowlisted modules exactly
  - Tests over temporary data roots holding fixture archives: two listed extras
    compose in reverse list order (distinct values decide); a missing file, a
    traversal-shaped ref and a foreign ref are skipped; a ref duplicating the
    base's hash and a ref duplicating an earlier extra's hash each leave
    `provenance.extras` without that duplicate (asserted on its length and
    hashes, since a duplicate never donates); a truncated extra raises the
    decode error; a page listing only its base returns the base object
  - Named mutations: keep list order instead of reversing; stop skipping missing
    files; drop the duplicate-of-the-base skip; drop the duplicate-of-an-earlier-
    extra skip; catch and skip decode errors; define a local `_sha_of_ref` (the
    consumer guard reds)
  - Observable: `uv run pytest tests/compose/ tests/test_contract_consumers.py`
    green with each mutation observed red; the boundary guard reports exactly
    seven modules; ruff check and format clean
  - _Requirements: 6.3, 7.2_
  - _Boundary: ArchiveComposition, Guards_
  - _Depends: 2.4_

- [x] 3.2 (P) Render the Channel Sources section from a composition's provenance
  - Append the provenance field to the render context (defaulting to `None` so
    every existing construction stays valid), and move the field-order pin
    `tests/render/test_frontmatter.py:317-324` from the position-relative
    shape `activity-identity` leaves it in (`user_frontmatter` directly after
    `map_data`, `identity` last) to: `user_frontmatter` directly after
    `map_data`, `channel_provenance` the last field, and `identity` directly
    before it
  - The section body exactly as design.md § ChannelSourcesSection states: the
    fixed sentence, the File / Role / Kind / Channels / Alignment table, one row
    for the base then one per extra in rank order, archive refs from the layout
    helper, kind text, labels in model order with position once as GPS, the
    absence marker for an extra that supplies nothing, the alignment text with
    its optional whole-hour prefix and zero counts omitted; `None` when there is
    no provenance or no extra
  - The channel label table for every channel but the time offset; tests hold
    it equal to the coverage table's labels and the Running Dynamics section's
    labels for every channel those name, and its key set equal to the model's
    channels
  - The reverse-direction guard (design.md § Guards): no module under
    `fitdocs/render` imports `fitdocs.compose.archive`, and the provenance
    module imports from `fitdocs.compose` only `types` and `alignment`, and
    nothing from `fitdocs.contract`, `render.sections` or `render.dynamics`; a
    positive control that the render walk scanned the provenance module
  - Tests with hand-built compositions: the exact text for a run composition,
    for a shifted ride with one stretch (singular), for a mix of distance, power
    and fallback stretches, and for a non-donating extra; `None` for a
    provenance without extras
  - Named mutations: render when the provenance has no extras; drop the label
    de-duplication (GPS twice); flip the shift sign; print zero counts; always
    write "stretches"; delete one label (the completeness test reds); change a
    label's case (the equality test reds); add `import fitdocs.compose.archive`
    to the provenance module (the reverse-direction guard reds); insert the new
    field before `user_frontmatter` (the field-order pin reds); insert it
    before `identity` (the field-order pin reds)
  - Observable: `uv run pytest tests/render/` green with each mutation observed
    red; `uv run mypy` clean; ruff check and format clean
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8_
  - _Boundary: ChannelSourcesSection, ViewWiring_
  - _Depends: 2.4_

- [x] 3.3 Place the section in every view and add the composed golden
  - The run/ride, strength and generic views each append the Channel Sources
    section immediately after Device & Data Quality when it has a body
  - Add a `composed_run` golden case: the run pair composed and rendered with
    its provenance and its two refs, pinned timezone and athlete inputs as the
    other goldens; regenerate only the new golden files. No run file's
    recording device is Garmin (1.1's self-test), so the golden carries no
    `Data source` line in either landing order, while the ride pair carries
    `Data sources: Garmin <model> and other devices` once `_head` is wired
  - Tests: in each of the three views a composed context places the section as
    the last `##` section, directly after Device & Data Quality; every
    pre-existing golden stays byte-identical and unregenerated
  - Named mutations: place the section before Device & Data Quality (the
    placement tests red); append it in the run/ride view only (the strength and
    generic tests red)
  - Garmin attribution on composed pages (design.md § "Cross-spec seams";
    `intervals-connector` Req 8.4): whichever of this spec and
    `intervals-connector` lands second does this step. If
    `intervals-connector`'s `_head` and `attribution_line(base,
    donor_devices)` are on `main` when this task runs (or when the final
    rebase brings them in), wire `_head` to pass `tuple(c.devices for c in
    ctx.channel_provenance.extras if c.channels)` as `donor_devices` to
    `attribution_line(ctx.activity, donor_devices)` when
    `ctx.channel_provenance` is not `None` (`()` otherwise), and add, in the
    views section of the provenance tests, the ride-pair pin: the ride pair
    (Garmin-original base, HealthFit copy donating heart rate) composed and
    rendered reads `Data sources: Garmin <model> and other devices`, `<model>`
    the original's recording-device label as `intervals-connector` derives
    it; plus a hand-built Garmin base whose only extra is non-Garmin and
    donates nothing, which reads `Data source: Garmin <model>`. Named
    mutations: pass `()` as `donor_devices` (the ride-pair pin reds, M25);
    drop the `if c.channels` filter (the non-donating pin reds, M26). If
    `intervals-connector` is not on `main`, leave `_head` untouched and record
    in Implementation Notes that `intervals-connector` wires it when it lands
  - Observable: `uv run pytest tests/render/` green; `git diff --stat
    tests/render/golden_docs/` shows only the new `composed_run` files; ruff
    check and format clean; Implementation Notes record which branch of the
    attribution step ran
  - _Requirements: 4.6, 4.7, 8.2_

- [x] 4. Integration: the engine and the two passes

- [x] 4.1 Render every page from its composition, and move the upstream tests that pin a base-only body
  - The render seam composes the base with the extras in the roles' rank order
    and returns the composition; the page task keeps computing identity, uid
    and stem from the base's own parse before the call, and takes metrics, the
    map plan and the render context's activity and provenance from the
    composition; `sync`, `drain`, `regen` and the settle pass all reach it
  - Run the full suite; update every pre-existing test whose multi-file page
    body now legitimately carries donated channels or a Channel Sources section
    (activity-identity's end-to-end tests of multi-file pages, any
    `tests/test_sync.py` re-export assertion on exact body text, identity's
    Req 5.8 "an extra contributes nothing" pin, a spy on the seam's return
    value) to the composed expectation, never weakening an identity rule; list
    each updated test in Implementation Notes
  - In the seam section of the composed-sync e2e module: the run pair synced
    gives one page whose Running Dynamics section has form power and whose
    Channel Sources section names both files; a single-file page is
    byte-identical to its render without provenance
  - Named mutations: compose from the base alone in the seam (the form-power
    test reds); pass no provenance to the render context (the Channel Sources
    assertion reds)
  - Observable: the full `uv run pytest` green; the updated-test list recorded;
    ruff check and format clean
  - _Requirements: 1.1, 5.1, 5.4_
  - _Depends: 3.3_

- [x] 4.2 Prove composed pages end to end: arrival order, regeneration, drain and summaries
  - In their own sections of the composed-sync e2e module, over temporary data
    roots with the default precedence
  - The run trio synced in every arrival order, in one run and across three,
    gives byte-identical pages and assets with form power from `stryd_b`;
    `regen` reproduces the synced bytes; `drain` of the run pair gives the same
    page as `sync`; the ride pair's page shows the average heart rate of the
    donated values and its Channel Sources section states power alignment
  - The page's filename and `uuid` equal those the HealthFit copy alone
    produces: a regression check held by `activity-identity`'s ordering,
    recorded as reached by no mutation of this plan
  - Named mutations: take extras in arrival (`parsed`) order instead of rank
    order in the seam (the trio and regen tests red); compute metrics from the
    base instead of the composition (the average-heart-rate test reds)
  - Observable: the full `uv run pytest` green with each mutation observed red;
    ruff check and format clean
  - _Requirements: 1.3, 1.6, 5.1, 7.1_

- [x] 4.3 Score load and derive benchmarks from the composed activity
  - The load pass keeps resolving and parsing the page's last listed file as
    today, then composes it with the page's other listed files through the
    archive adapter before metrics and arbitration; the benchmark pass does the
    same inside its existing read and decode failure handling; neither base
    resolver changes, and the shared resolver test stays green unedited
  - Run after 4.2 (not in parallel with 4.1 or 4.2): the CLI chains the load
    pass after every sync and drain (`src/fitdocs/cli.py:321-324, 358-360`), so
    composing in the passes can move the load or benchmark outcome of any
    pre-existing multi-file page test (identity's, load's, performance's, e.g.
    `tests/performance/test_engine.py:869-906`); run the full suite, update each
    one to the composed expectation, and list it in Implementation Notes
  - E2E over data roots (the ride pair synced, then the pass run directly): a
    spy on the load pass's metrics call and one on the benchmark pass's
    derivation call each receive an activity whose heart rate equals the donated
    values; the ride page's load is computed with heart rate available; with the
    ride copy's archive file removed after the sync, both passes compose from
    the base alone and neither fails; with the copy's archive truncated, each
    pass reports the page as a per-document failure and the page is
    byte-unchanged; a page whose load was computed before the copy arrived
    keeps its load region byte-identical through a later sync and its chained
    load pass
  - Update the two modules' docstrings that state the pass re-parses "the last
    `sources` entry" to say it composes the listed files by the page's rule
  - Named mutations: skip the adapter in the load pass (its spy test reds); skip
    it in the benchmark pass (its spy test reds); catch the adapter's decode
    error in the load pass (the load failure test reds); call the adapter
    outside the benchmark pass's existing `try` (the benchmark truncated-extra
    failure test reds, the error escaping the pass)
  - Observable: the full `uv run pytest` green with each mutation observed red;
    the updated-test list recorded; ruff check and format clean
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  - _Depends: 3.1_

- [x] 5. Contract advance, published statements and spec records

- [x] 5.1 Advance the document-format version and bring every pin with it
  - Read `DOC_VERSION` on the branch rebased onto `main`, advance it by one and
    append its docstring paragraph (pages with extras take the channels their
    base lacks and gain a Channel Sources section; pages without extras change
    only this line); record the old and new values in Implementation Notes.
    After the final rebase, assert it equals `main`'s value plus one and, if a
    sibling landed a bump first, re-pin it with every literal below
  - Move every literal pin of the old value (a repository grep for
    `doc_version: <old>` and `DOC_VERSION == <old>` decides; at design time
    `tests/render/test_frontmatter.py:44, 101` and
    `tests/metrics/test_sources.py:2270`); regenerate every golden document; the
    diff of each pre-existing golden is its `doc_version` line alone
  - In the composed-sync e2e module's own section, record
    `_PRE_CHANNEL_MERGE_DOC_VERSION` as the old value with a provenance
    docstring (the precedent is `_PRE_RUNNING_DYNAMICS_DOC_VERSION`); age the
    run pair's page to it and remove its Channel Sources section, assert the
    precondition `DOC_VERSION > _PRE_CHANNEL_MERGE_DOC_VERSION`, see
    `fitdocs check` report it out of date, `fitdocs regen` restore the section
    and the current version, and a second `fitdocs check` report it current
  - Confirm `MANAGED_KEYS` is unchanged (`git diff` of `contract.py` touches
    only `DOC_VERSION` and its docstring)
  - Named mutations: advance by two (the moved pins red); revert the advance (the
    aged-page precondition reds)
  - Observable: full `uv run pytest` green; each pre-existing golden's diff is
    one line; ruff check and format clean
  - _Requirements: 8.1, 8.2, 8.5_
  - _Depends: 4.1, 4.2, 4.3_

- [x] 5.2 Advance the contract version and publish the composition guarantees
  - Advance `CONTRACT_VERSION` by one from the branch's value, as Req 8.4
    states (every Phase 8 lander advances it once; research.md, Decision:
    Contract version rule), adding a paragraph to its docstring (what an extra
    contributes, the Channel Sources section, the two passes reading the
    composed activity); record the old and new values in Implementation Notes;
    always regenerate `tests/declaration_golden/*` with its own generator.
    After the final rebase, assert the value equals `main`'s plus one and, if
    a sibling landed a bump first, re-pin it and every literal that moved with
    it (the ownership contract's header, the declaration goldens)
  - In the ownership contract's section on source files and roles, add the
    subsection on channels a page takes from its extras (design.md
    § ContractDocs): donation and partial coverage, position, what stays the
    base's, the alignment table (constants, values, sources), the whole-hour
    shift, the Channel Sources section, no frontmatter key, the two passes
    composing by the page's rule, and that `fitdocs load --recompute` rescores a
    page whose composition changed after its load was computed; the header
    version; the "What changed at this version" paragraph **replaced** with
    this spec's changes (a sibling's earlier paragraph is not kept; the
    changelog is the cumulative record); and the overwrite semantics of
    `regen`, `load` and `derive-benchmarks`
  - A docs pin holds the published alignment table equal to the constants and
    their sources
  - `CHANGELOG.md` `[Unreleased]` `### Changed`: the generated document
    contract change with the actions `fitdocs regen` and
    `fitdocs load --recompute`, no version number, docs by project URL only;
    appended under the existing `### Changed` heading in `[Unreleased]`, the
    heading created only if absent (`tests/test_changelog.py:516` rejects a
    repeated category in one section)
  - Named mutations: change the lag window to 3 (the docs pin reds); leave the
    contract version unadvanced (the ownership-contract header pin reds)
  - Observable: full `uv run pytest` green, `tests/test_changelog.py`,
    `tests/test_ownership_contract.py` and `tests/test_docs_guarantees.py`
    included; ruff check and format clean
  - _Requirements: 6.6, 8.3, 8.4, 8.6_

- [x] 5.3 (P) Land the amendment records, roadmap annotations and the steering dependency line
  - wiki-contract: if no sibling has created Amendment 4, create it titled
    `## Amendment 4 (<first landing date>): source roles, connector state and
    channel provenance, landed by activity-identity, connectors and
    channel-merge`; else append to it. This spec's paragraph records its own
    `CONTRACT_VERSION` `"X"` to `"Y"` (`main`'s value before this spec's
    advance and that value plus one; after the final rebase, re-checked
    against the values 5.2 recorded and re-pinned with them). One criterion
    to Requirement 2 (next free number, tagged `_(added by Amendment 4)_`); a
    DocumentContract note in its design; an `amendments` entry in its spec.json
  - workout-docs: a new amendment appending one criterion each to
    Requirements 3, 6 and 13 (design.md § SpecRecords); training-load: a new
    amendment appending one criterion to Requirement 9; performance-benchmarks:
    a new amendment appending one criterion to Requirement 1; each with its
    spec.json entry; numbers are the next free ones on the branch
  - Roadmap Phase 8 Existing Spec Updates: annotate the wiki-contract and
    workout-docs lines "(channel-merge part landed)", ticking either only if
    every part it names is on `main`; tick the training-load and
    performance-benchmarks lines (landed by channel-merge alone) when every
    part of each is on `main`; write no merge SHA (the merged commit cannot
    know its own). Leave the Boundary Strategy's `sync.py` seam as it stands
    (it already states where the extras are read)
  - `.kiro/steering/structure.md`: append `compose` to the dependency line
    ("Dependencies point one way") as design.md § SpecRecords states, without
    rewording the existing chain or a sibling's appended package
  - Observable: `git diff` of every amended spec and of `structure.md` adds
    lines or appends only (nothing renumbered or reworded); every spec.json
    parses; `/kiro-spec-status` clean for the four amended specs
  - _Requirements: 8.3, 8.4_
  - _Boundary: SpecRecords_

- [x] 6. Validation

- [x] 6.1 Classify every criterion, re-run the named mutations and validate the whole change
  - For each of the 54 criteria record PINNED (test and mutation),
    PRESERVED-ONLY (the existing test) or UNPINNED (with the mutation run that
    shows it), per `change-protocol.md` § The completeness half; 7.3 is
    PRESERVED-ONLY by the frozen-dependency tests
    (`tests/test_determinism.py:672-712`, `tests/test_packaging.py:503-519`);
    1.6 is recorded as held by activity-identity
  - Re-run M1-M24 and M15b (design.md § Testing Strategy) on the finished tree
    through `uv run pytest` and record the test each reds, plus M25 and M26
    when this spec wired `_head` (3.3's attribution step); Req 9.2's five must
    each red at least one test
  - After the final rebase: `DOC_VERSION` and `CONTRACT_VERSION` each equal
    `main`'s value plus one (re-pinned by 5.1/5.2 if a sibling landed first);
    if `intervals-connector` landed while this branch was open, 3.3's
    attribution step has run
  - Register every new typed test and fixture module in `pyproject.toml`
    `[tool.mypy].files`
  - Run the prose-claim grep from `change-protocol.md` over every changed test
    file and re-test each surviving claim; run the no-Stryd-address grep over
    every changed file
  - Observable: the classification table in Implementation Notes, and
    `uv run pytest && uv run ruff check . && uv run ruff format --check . &&
    uv run mypy` green
  - _Requirements: 7.3, 9.2, 9.3_

## Implementation Notes

- 1.2: the guard's "seven modules" are the package marker plus the six design modules (types, stretches, alignment, donation, composer, archive); the marker may import nothing non-stdlib. The allowlist is a subset check until 3.1 tightens it to equality. Outside `archive.py` the guard also bars `os`, `shutil`, `tempfile`, `glob`, `io`. Clock spellings match word-bounded (`(?<![\w.])<s>\b`), so `start_time.timestamp()` and `datetime.timezone` are allowed (2.1 may use them). 3.1: the `.` in that lookbehind is unpinned and costs docstring detection of `datetime.datetime.now` -- consider `(?<!\w)` when tightening. `tests/compose/builders.make_activity`: passing `summary=` drops the default `summary.start_time`; there is no `record_developer_fields` option (use `dataclasses.replace` locally).
- 1.1 fixture edit per self-test (each observed red, reverted green): L_3 to +1 reds the per-stretch lag test; dropping enhanced_speed from the HealthFit copy reds the Stryd-only-channels subset test; ride copy device_manufacturer="garmin" reds the ride recording-device test; Stryd device_manufacturer="garmin" reds the run recording-device test (and the trio test); _RUN_STRIDE 16->12 reds the layout test; _RUN_TRAILING 3->2 reds the trailing test; stance-time modulus 13->11 reds the distinct test; HR at lag 0 reds the HR test; step divisor 1.008->1.0 reds the step-ratio test; HealthFit laps 5->4 reds the laps test; Stryd start +5 reds the STRICT identity test; shift 3600->1800 reds the SHIFTED test; dropping the HealthFit SESSION UUID reds the run precedence test; copy distance equal to the original's reds the ride-lag test; builder `sport` default "cycling" reds the default-bytes pin (named mutation).
- 1.1 pins resting on the synthetic `development` HealthFit recording device (revisit if intervals-connector's live check TBC-9 finds a Garmin device at device_info index 0 of a real HealthFit copy): the ride-pair attribution pin (M25 / intervals-connector 2.3), the composed_run golden's no-Data-source-line claim (3.3), and 1.1's two recording-device self-tests.
- 1.1 (review round 2): moving the helper's laps after the session or before the records reds the lap-placement test (raw stream order via `_message_numbers`); the ride copy's distance matches the original's at no lag in -2..+2 (`matched == 0`, stricter than the alignment rule needs). `fitdocs.compose.alignment.MIN_MATCHED_SAMPLES` is not referenced by the fixture tests.
- TBC-9 resolved 2026-10-02 by intervals-connector's live check (agent-log WARN 09:17:48Z): real HealthFit copies (rides and runs) record `development` at `device_info` index 0 and in `file_id`, so 1.1's `development` HealthFit fixtures match reality and the pins resting on them (M25 / intervals-connector 2.3, the composed_run no-Data-source-line claim) need no revisit.
- 2.1 named mutations, each observed red then reverted green: extra's pauses only (3 red, incl. test_base_pause_splits_a_continuous_extra); `>=` in the gap test (17 red, incl. test_one_second_step_is_not_a_pause); count cut points with `<` (7 red, incl. test_sample_exactly_at_a_resume_instant_opens_the_stretch); instants without the start (6 red, incl. test_start_is_part_of_the_instant); round a non-whole instant (3 red, incl. test_round_halves_and_near_wholes_are_not_whole). `split_stretches(extra, base)` returns `tuple[range, ...]` over the extra in file order and emits no empty range; equivalent mutants (shown by 200k-case comparison): dropping `sorted`, iterating `first` unsorted, keeping only base cuts the extra has a sample at.
- 2.2 named mutations, each observed red then reverted green: require every base sample to keep a unit (the 51% and single-sample tests red); split position into two units (literal-list and position tests); drop a channel (literal-list and coverage tests; a dynamics channel also reds the dynamics positive control); index placed values by base position (4 placed-values tests); fill unplaced with `0` (4, incl. the none-not-zero test). Review round 1 added O9b: `float()` on placed values reds `test_values_pass_through_exactly_as_decoded`, which now pins value, type and identity. `placed_values` reads a negative placement index from the end silently -- 2.3/2.4 must never produce one.
- 2.3 named mutations, each observed red then reverted green: first stretch's lag for all (2 red); heart rate leading the keys (2-3); power before distance; drop uniqueness (3); drop majority (2); minimum 0 (2); place at instant minus lag (8); last index of a duplicated instant (1); later sample overwrites (1); drop the hour shift (5); k up to 37 (4). Review round 1 added: lag/key carried into a following fallback stretch (O1/O2), majority measured at a lag other than the winning one (O3 lag 0, O4 max, O5 min), reversed placement within a stretch (O9) -- each now reds its own test. Equivalent mutant: `winners[-1]` (uniqueness runs first). Verified by the reviewer on the real fixtures: run pair lags +1,+1,0,+1,0 by distance (57 of 63 base samples placed, last three None); ride lag 0 by power, hour_shift_s 3600 when shifted, all fall back with no copy power. "Compared" at a lag = extra value, its instant, t+L on the base timeline and the base value there all present; match is `abs(v-b) < resolution/2`. No placement index is ever negative.
- 2.4: all 13 named mutations observed red then reverted green (skip base-keeps 9 red; every-sample 5; fill base gaps 4; worst first 6; any-not-every 1 (position); raw-vs-placed 2; extra's laps / summary / record developer fields 1 each; null balance 1; rebuilt activity when no extra 1; alignment on a non-donor 2; M23 base devices 1). Review round 1 added O1 (align against the composed-so-far activity -> TestAgainstTheBaseAlone) and O2 (lower-ranked extra fills a donor's gaps -> TestNoMixingOfOneChannel). `compose_activity(base, extras) -> Composition`; each contribution's sha256 is `activity.provenance.sha256` (the decoded bytes' hash = the archive name and `sources` ref, confirmed sync.py:1405), kind is `identity.kinds.source_kind`, manufacturer is `file_identity.manufacturer`, devices the file's own. An extra whose raw samples record no open channel is never aligned (unobservable beyond `alignment is None`). Reviewer e2e on merge.py: run pair donates exactly the 8 Stryd-only channels (all DYNAMICS_CHANNELS), form power at per-stretch lags with 0 mismatches; ride donates heart_rate_bpm only.
- 2.5 named mutations, each observed red then reverted green: one lag for every stretch M1 (8 red, incl. TestRunPair form-power first/last, whole-series, stretch-keys, trailing-None, and the trio); skip base-keeps M2 (16 red, incl. TestRunPair step-length/cadence, donated-channels, metrics equality, the ride's non-HR-fields test, the trimmed-HR test); heart rate leading the keys M3 (7 red, incl. TestRunPair form-power, whole-series, stretch-keys); the extra's laps M4 (TestRunPair test_the_laps_are_the_healthfit_laps); fill base gaps from the extra's placed values M5 (the trimmed-HR test, the only 2.5 test); every-sample-keeps (incl. the trimmed test); return the base without donating (37 red, incl. the ride avg-HR 139.5 test); drop the hour shift (the shifted-ride test). Req 9.2's five (per-file lag, base-recorded channel taken from an extra, heart-rate lag, extra's laps, partial fill) = M1, M2, M3, M4, M5. HR-fed metric fields excluded from the ride equality: avg/max_heart_rate_bpm, efficiency_factor, decoupling_pct, trimp, trimp_weighting, hr_time_in_zone_s. Unpinned: the ride ranking premise against precedence mutations that leave original:garmin first.
- 3.1 named mutations, each observed red then reverted green: keep list order (the reverse-order test alone); stop skipping missing files (the missing-file test); drop the base-duplicate skip; drop the earlier-extra-duplicate skip; catch and skip decode errors (an import-free `except Exception: continue` reds the decode and read tests); a local `_sha_of_ref` (two consumer-guard tests); boundary `==` weakened to `<=` (the seven-module equality test). Review round 1 added `is_file()` -> `exists()` (the directory-at-archive-path test alone). Dropping only the `sha is None` check is caught by mypy (`archive_path(root, None)` arg-type), not by a test. `compose_listed(data_root, refs, base) -> Composition`: extras are `reversed(refs[:-1])`; read/decode errors propagate. The clock regex lookbehind is now `(?<!\w)` (docstring `datetime.datetime.now` detected).
- 3.2: all 10 named mutations observed red then reverted green (no-extras render; GPS twice; shift sign; zero counts; always "stretches"; delete a label; label case; archive import in provenance.py; field before user_frontmatter; field before identity). Reverse guard took 4 review rounds (converging, not oscillating; controller ruling: no debug dispatch, the round-3 reviewer swept every guard part and named the last gap): relative imports resolved per file package (O9a/O9b/O17/O21), `_package_of` pinned by literals (R2/R3), `_archive_offenders` per-file package (R4), recursive walk reaching charts/ (R5), `_provenance_targets` package (Ni/Nj). Lesson for 3.3+: a guard's helpers are code too -- pin each helper with a fixed-input test, not only the real-tree scan. `DocContext.channel_provenance` is the last field, after `identity`, default None.
- 5.3: wiki-contract Amendment 4 gains the channel-merge paragraph + criterion 2.16 (CONTRACT_VERSION recorded "6" to "7" -- re-check against 5.2 and main after the final rebase); workout-docs Amendment 2 (3.7, 6.11, 13.4; criteria_map in spec.json), training-load Amendment 5 (9.4), performance-benchmarks Amendment 2 (1.11). Roadmap written for the state at merge: wiki-contract, training-load, performance-benchmarks ticked; workout-docs annotated, unticked (intervals-connector's attribution part pending) -- re-check if intervals-connector lands first. Review round 1 narrowed workout-docs 6.11 to the splits/devices sections (it had contradicted intervals-connector 8.4's donor attribution) and redefined 13.4's gap by placement (CM 2.6).
- 3.3: attribution step took the "intervals-connector NOT on main" branch (origin/main 16a42a1 has no `_head`/`attribution_line`): `_head` untouched, no M25/M26 pins -- intervals-connector wires donor devices when it lands second; if it lands first, the final rebase runs 3.3's attribution step here. Named mutations red: section before Device & Data Quality (10 red), run/ride only (strength and generic tests), drop the call (both golden tests). The composed_run golden's `source_refs` come from `identity.roles.rank_members(...).sources` (ascending rank, base LAST, as sync writes them); the Channel Sources table is `reversed(source_refs)`. The "no Data source line" claim is unpinned on this branch (no attribution line exists yet).
- 4.1: `sync._render_activity(roles, parsed)` returns `compose_activity(parsed[base], [parsed[m.ref] for m in roles.extras])` (`PageRoles.extras` is best first; `sources` is ascending rank, base last). Identity, uid and stem stay from the base's parse; metrics, map plan, `DocContext.activity` and `channel_provenance` come from the composition; sync, drain, regen and the settle pass reach the one `_page_task` call. Updated pre-existing tests (all tests/test_identity_e2e.py): test_reexport_pair_in_either_order_renders_byte_identical_pages and test_file_below_the_base_leaves_base_and_filename_unchanged (page gains a Channel Sources section; the extra's Channels cell pinned `–`), test_cli_partner_copy_arriving_later_changes_nothing_but_sources (the new section minus the partner row equals the old one exactly), test_metrics_and_map_come_from_the_render_activity and test_the_map_decision_follows_the_render_activitys_modality (seam spies return a Composition). No pre-existing multi-file test has an extra that could donate (reviewer instrumented the full suite). Mutations red: compose from base alone; no provenance; DocContext.activity from the base (M3); base channels `()` with 2+ extras (M9, partner test); an extra really donating heart rate (the `–` pins). The trio synced in all 6 arrival orders renders stryd_b's form power (63 W).
- 4.2: named mutations red: extras in arrival (`parsed`) order in the seam (14 red: all 12 trio cases, baseline, regen); metrics from the base (both ride cases: `| Avg HR | 140 bpm (max 189 bpm) |`, `avg_hr_bpm: 140`). The 6 one-run arrival orders really reach 6 distinct `parsed` orders (reviewer probe). Filename and `uuid` are fixture-satisfied whichever file is the base (all three files compute stem 2042-04-13-run-2320; only the HealthFit copy carries a uuid) -- reached by no mutation of this plan, a regression check; Req 1.6 is pinned instead by the recorded base identity lines (source_kind/elapsed/distance/device equal HealthFit-alone's; identity from an extra or reversed precedence reds it).
- 5.2: CONTRACT_VERSION "6" -> "7" (origin/main 16a42a1 holds "6"; matches 5.3's wiki-contract record). Named mutations red: MAX_LAG_S=3 (test_each_scalar_value_equals_its_constant + 2 alignment constant tests); version unadvanced (test_contract_version_matches_code + the 4 declaration goldens). Position pin ("records both latitude and longitude") reds alone under "records either". Out-of-boundary edit: tests/identity/test_contract_docs.py `_section()` now stops at `### Channels a Page Takes` (its extracted text is byte-identical to before). Review round 1 corrected three false doc statements (position "either" for extras; derive-benchmarks write is change-only and replaces the derived subset; the shift-constants pointer) and the athlete.toml bullet now names both writers. Narrative claims (placement after Device & Data Quality, lag-majority wording) are UNPINNED. The published "two passes compose" statement depends on 4.3 being merged before landing.
- 4.3: both passes keep their base resolver unchanged, then `compose_listed(data_root, refs, base)`; the load pass gets refs via `_listed_refs(markdown)` (contract `parse_frontmatter` + `source_refs`), the benchmark pass inside its existing `try`. No pre-existing test needed updating (no corpus page had a donating extra; tests/performance/test_engine.py:868-906 docstring reworded only). Named mutations red: skip adapter in load (4), skip in benchmark (2), catch decode error in load (1), adapter outside the benchmark `try` (1). Review round 1 added: extras reversed in either pass (O1/O1b -> the trio ranking tests, form power told apart by parity: stryd_a even, stryd_b odd) and the load failure detail equal to a truncated base's (O8). Sync's own preservation of the load region on re-render is PRESERVED-ONLY (existing restore-branch tests).
- 5.1: DOC_VERSION 7 -> 8 (origin/main 16a42a1 holds 7). Moved pins: tests/render/test_frontmatter.py (doc_version block, DOC_VERSION ==), tests/metrics/test_sources.py CONSTANT_REGISTRY_ASOF_DOC_VERSION, tests/load/test_render.py (2, 8) pair; tests/test_cli_check.py already relative. 12 goldens regenerated, each diff the doc_version line alone. `_PRE_CHANNEL_MERGE_DOC_VERSION = 7` in tests/test_compose_e2e.py's aged-page section (check -> regen -> check via CliRunner; assets deleted when aging). Named mutations red: advance by two (18 pins), revert (aged-page precondition `7 > 7`). Controller downgrade (stated): review round 1's only finding was the DOC_VERSION docstring paragraph defining an extra by donation; the controller rewrote that paragraph, the e2e module docstring, and added the `doc_version` 7 to 8 sentence to the CHANGELOG channel-merge entry (5.2's file, following the 5->6 / 6->7 precedent); a reviewer confirmed all three.
- FINAL REBASE (2026-10-02) onto main 1e1fe8c: intervals-connector landed first (agent-log MERGED 9d08482), so this spec is the second lander. Reconciled: DOC_VERSION re-pinned 8 -> 9 (contract.py "Raised from 8 to 9 by channel-merge" beside intervals-connector's 7 -> 8 paragraph; test_frontmatter, CONSTANT_REGISTRY_ASOF_DOC_VERSION, load/test_render pair (2, 9) "a sixth time", `_PRE_CHANNEL_MERGE_DOC_VERSION = 8`, all 12 goldens, CHANGELOG "`doc_version` 8 to 9"); CONTRACT_VERSION "7" is still main ("6") + 1. workout-docs: intervals-connector took Amendment 2 and criterion 6.11, so channel-merge's record is Amendment 3 with criteria 3.7, 6.12, 13.4 (spec.json entry and criteria_map renumbered); the 5.1 and 5.3 notes above that say 7 -> 8 / Amendment 2 / 6.11 describe the pre-rebase state. Roadmap: fit-ingest stays ticked (main), workout-docs now ticked (every part on main once this merges). Both CHANGELOG entries kept. 3.3's attribution step now runs (this spec lands second; ruling R2). Pre-rebase tip kept as branch backup/channel-merge-pre-rebase-2aaf3e5.
- 3.3 attribution step (ran after the final rebase; this spec landed second): `_head` passes `tuple(c.devices for c in ctx.channel_provenance.extras if c.channels)` (or `()`) to `attribution_line`. Pins in tests/render/test_provenance.py (cited intervals-connector Req 8.4): ride pair reads `Data sources: Garmin SyntheticGarminEdge and other devices`; a non-donating extra adds nothing; a non-donating Garmin extra is not named; a donating Garmin extra is named after the base; three extras in rank order read `Data sources: Garmin edge_1040, Garmin fenix_7 and Garmin fr965`. Mutations red: M25 (pass `()`), M26 (drop `if c.channels`), reversed donors, last extra only, first device only. Moved test: test_the_section_is_the_provenance_body_under_its_heading (its non-Garmin donor widens the line). Controller decisions (stated): the review asked for docs/connectors.md (intervals-connector's) and the CHANGELOG channel-merge entry to state the composed attribution rule; the round-2 prose fixes (views.py module docstring, connectors.md, CHANGELOG) were applied by the controller and confirmed by the reviewer. No golden changed; composed_run carries no Data source line.
- 6.1 classification (54 criteria; mutations re-run on the finished tree):
  - PINNED: 1.1 (M15, C11), 1.2 (no-extra returns the base object; M18), 1.3 (M15b, M7), 1.4 (C14, C39b), 1.5 (M4, M22, TestBaseOwnedFields, page-level lap table), 2.1 (M2), 2.2 (M5), 2.3 (M7, M20, TestNoMixingOfOneChannel), 2.4 (M8), 2.5 (M21, float() on placed values), 2.6 (zero-fill), 2.7 (C27), 2.8 (dropped unit), 3.1 (rounded instants), 3.2 (M13), 3.3 (M9, M10, M11, M12, MAX_LAG_S 1/3), 3.4 (power key removed, M12), 3.5 (M14, M1), 3.6 (M3), 3.7 (fallback key/lag), 3.8 (M6, tolerance/max +1), 3.9 (duplicate placement, clamping), 3.10 (align against composed-so-far), 4.1-4.7 (provenance text/role/kind/ref/order/GPS/alignment/absence/placement mutations; M18), 4.8 (frontmatter key added), 5.1 (M19, M15), 5.2 (TestSessionValueWins), 5.3 (M2 metrics equality), 5.4 (M4), 6.1 (M16, ranking O1), 6.2 (M17, O1b), 6.3 (missing-file skip), 6.4 (decode catch/wrap, adapter outside try), 6.6 (forced recompute; doc statement), 7.1 (M15b regen), 7.2 (static boundary guard only), 8.1 (DOC_VERSION 10/8 after the final rebase, audit gate), 8.2 (M18 + one-line goldens), 8.3 (doc-statement pins added in 6.1, incl. the base-identity sentence and both highest-ranked rules), 8.4 (CONTRACT_VERSION "6"; changed-at paragraph), 8.6 (CHANGELOG actions + 'names the file each channel came from' pins added in 6.1), 9.1 (fixture self-tests), 9.2 (M1-M5 each red), 9.3 (TestNoServiceAddress added in 6.1: scans every tracked file, `https?://[^\s)]*stryd`).
  - PRESERVED-ONLY: 1.6 (activity-identity; 4.2 recorded-identity pin; filename/uuid fixture-satisfied), 7.3 (tests/test_determinism.py:672-712, tests/test_packaging.py:503-519; adding a dependency reds both), 8.5 (tests/test_contract.py MANAGED_KEYS equality).
  - 6.5 split: "donated samples count toward coverage" PINNED (heart-rate load computed with donated HR; skipping the load-pass adapter reds it); "absent samples count against coverage" PRESERVED-ONLY (unchanged training-load channel code and its tests/load tests; no composition-specific pass-level fixture). Validation finding C1.
  - M-table: M1-M24 and M15b each red at least one test (M21, M22, M23, M24 each alone); M25 (6 red, incl. test_ride_pair_reads_garmin_and_other_devices) and M26 (4 red, incl. both non-donating pins) PINNED after the final rebase ran 3.3's attribution step.
  - 6.1 added: tests/test_compose_e2e.py::test_the_run_pair_pages_lap_table_is_the_base_laps_alone; tests/compose/test_composer.py::TestSessionValueWins; tests/compose/test_contract_docs.py (subsection guarantees, changed-at paragraph, CHANGELOG actions); tests/compose/test_boundary.py::TestNoServiceAddress (an address in compose/types.py had left the suite green). mypy: tests/fixtures/merge.py, test_merge_fixtures.py, tests/compose, tests/render/test_provenance.py, tests/test_compose_e2e.py, tests/test_compose_passes_e2e.py registered; the 4.1 render_document attr-defined error fixed. Gate after the final rebase: pytest 8639 passed / 43 skipped, ruff check + format clean, mypy 291 files clean.
