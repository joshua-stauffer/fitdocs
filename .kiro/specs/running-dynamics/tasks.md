# Implementation Plan

## Ground rules for every task

- **Existing goldens are the evidence for 9.1.** Every golden document and
  chart under `tests/render/golden_docs/` that exists before this spec must
  stay byte-identical, unregenerated, through tasks 1.1-4.2. Only task 5.1
  regenerates them, and there the diff of each pre-existing golden is its
  `doc_version` line alone. A task before 5.1 that finds it must regenerate a
  pre-existing golden has broken 9.1: stop and report, do not regenerate.
- **Mutations run through `uv run pytest` only** (`change-protocol.md`
  § Fixture Discrimination: a bare `uv run python -c` can read stale
  bytecode). Each task's named mutations are applied to production code
  (for task 1.2's fixture self-tests, to `tests/fixtures/builder.py`, the
  code those self-tests test), observed red, reverted, observed green, and
  recorded in the task's Implementation Notes.
- **`src/fitdocs/model.py`'s source text, docstrings included, never contains
  `garmin_fit_sdk`, `from fitdocs` or `import fitdocs`**
  (`tests/test_model.py:80-84` scan it).
- **No module other than `src/fitdocs/contract.py` imports or names `uuid`**
  (`tests/test_contract_consumers.py:516-528`). The application id's hex form
  is built from the 16 ints (for example `bytes(values).hex()`), never through
  `uuid.UUID`.
- **No Stryd web address anywhere** (10.5). Before a task is done,
  `grep -rniE "https?://[^ )]*stryd" <files the task changed>` prints nothing.
  Stryd's developer-field names are file-format knowledge and are fine.
- **Sibling seams** are design.md § "Cross-spec seams", whose Shared files
  list names every file a sibling also edits (append-only; the second lander
  keeps both sides). In particular: `DOC_VERSION` advances by one from the
  value on the branch when task 5.1 runs (never a hard-coded result); after
  the final rebase the implementer checks it equals `main`'s value plus one
  and re-pins if a sibling landed a bump first (cross-spec ruling R1);
  `activity-identity` appends to `Activity`, `fitdocs.__all__`,
  `docs/plugins.md`'s surface list, `parse_fit`'s wiring and the model
  goldens in parallel; `channel-merge` and `intervals-connector` also edit
  `render/views.py`; `ingest/summary.py:372-385` (`_product_name`) belongs to
  `intervals-connector` and is not touched here; the fixture builder's
  `_file_id` and `_device_info` parameters and `developer_field_run_fit_bytes`
  (task 1.2) are shared, append-only fixture seams (`activity-identity` uses
  `_file_id`'s; `channel-merge` extends the helper).

- [ ] 1. Foundation: the model's channel set and the synthesized fixtures

- [x] 1.1 Add the twelve running-dynamics channels, their registry and the developer-channel type to the activity model
  - In `src/fitdocs/model.py`: `DYNAMICS_CHANNELS` (the twelve names, in the
    design's order); the twelve `Samples` fields appended after
    `temperature_c`, each `tuple[float | None, ...] = ()`;
    `Samples.__post_init__` filling an empty dynamics channel to
    `(None,) * len(time_s)` when `time_s` is non-empty and raising
    `ValueError` naming the field when a dynamics channel's length is neither
    `0` nor `len(time_s)`; the frozen `DeveloperChannel` dataclass;
    `Activity.record_developer_fields`, defaulting to an empty read-only
    mapping, appended after `developer_fields_declared_scale`. The module
    docstring's unit list gains mm, ms, pct, kN/m and bw. `SCHEMA_VERSION`
    stays `"1.0"`
  - Export `DeveloperChannel` from the package root (`TYPE_CHECKING` block,
    `_LAZY_EXPORTS`, `__all__` in `src/fitdocs/__init__.py`) and append it to
    `_EXPECTED` in `tests/test_public_api.py`
  - Append `DeveloperChannel` to `docs/plugins.md`'s public import surface
    list (the ``From `fitdocs`:`` block). This one line is the stated
    exception to design.md's out-of-boundary `docs/` rule (cross-spec ruling
    R11: `activity-identity` lists `FileIdentity` the same way); the existing
    `tests/test_docs_guarantees.py::test_every_name_in_the_plugins_doc_public_surface_list_actually_imports`
    covers it
  - Regenerate `tests/golden/{run,ride,strength,minimal}.json` with
    `uv run python -m tests.golden.generate`; `git diff` shows only added keys
    (twelve all-`null` arrays in each `samples`, and
    `"record_developer_fields": {}`), with no existing value changed
  - Pins in `tests/test_model.py`: `DYNAMICS_CHANNELS` equals the twelve names
    in order and has no duplicates; each name is a `Samples` field whose
    annotation is `tuple[float | None, ...]` and whose default is `()`
    (`dataclasses.fields`, never `hasattr`); a `Samples` built with only the
    ten existing keywords and three samples holds `(None, None, None)` in every
    dynamics channel, and with zero samples holds `()`; a dynamics channel of
    length 2 beside three samples raises `ValueError` whose message names it;
    an `Activity` built without the new argument has an empty, read-only
    `record_developer_fields`
  - Named mutations: delete the fill in `__post_init__` (the three-sample
    pin reds); delete the length check (the `ValueError` pin reds); drop one
    name from `DYNAMICS_CHANNELS` (the order pin reds); delete
    `DeveloperChannel`'s `_LAZY_EXPORTS` entry, leaving `__all__` alone (the
    plugins-doc surface test reds on `hasattr(fitdocs, "DeveloperChannel")`,
    which shows the listed name is read)
  - Done: `uv run pytest` is green with no existing test edited other than
    `_EXPECTED`, and no golden document changed; `mypy` clean
  - _Requirements: 1.1, 1.3, 3.3, 3.4_

- [x] 1.2 (P) Build the synthesized fixture families and the developer-field encoding helper
  - In `tests/fixtures/builder.py`, `_file_id`'s keyword parameters: add them
    unless `activity-identity` already added them on the branch; reuse them.
    They are keyword-only and defaulted, `manufacturer: str = "garmin"`,
    `product: int = 1`, `time_created: int = FIT_TIMESTAMP_BASE`, beside the
    positional serial; the defaults are today's values, so every existing
    caller (in `builder.py` and the five test modules that call
    `builder._file_id`) and every existing fixture's bytes are unchanged
  - Give `_device_info` a keyword-only `manufacturer: str = "garmin"`
    parameter replacing its hard-coded `"garmin"` (`builder.py:157-168`),
    under the same rule (add it unless a sibling already has; reuse it). The
    default is today's value, so every existing caller (in `builder.py` and
    the same five test modules) and every existing fixture's bytes are
    unchanged (cross-spec ruling R12)
  - Add `DevFieldSpec` and `developer_field_run_fit_bytes` with exactly the
    keyword-only signature in design.md § StrydFixtures (cross-spec ruling
    R10): `descriptions: Sequence[DevFieldSpec]`, `records:
    Sequence[tuple[Mapping[str, object], Mapping[int, object]]]`,
    `session_fields: Mapping[int, object] | None = None`, `serial: int =
    _DEV_FIELD_RUN_SERIAL`, `manufacturer: str = "garmin"`, `product: int =
    1`, `time_created: int = FIT_TIMESTAMP_BASE`, `device_manufacturer: str |
    None = None`, where `None` follows `manufacturer` (cross-spec ruling R17,
    matching `activity-identity`'s `session_fit_bytes`). Session developer
    fields are supported through `session_fields` (position in
    `descriptions` -> value on the session; `None` writes none). It
    assembles its default message list in one place (no lap message; one
    running session spanning the records) and hands it to one private
    Encoder routine that registers every field with
    `Encoder.add_developer_field` before the first write, as
    `_encode_run_with_developer_fields` does, so `channel-merge` can later
    append `laps`, `session_start`, `session_elapsed_s`,
    `session_distance_m` and `sport` as keyword-only, defaulted parameters.
    Tasks 2.1-2.4 build every synthetic developer-field case with it instead
    of writing Encoder code
  - `stryd_run_fit_bytes(*, manufacturer: str = "stryd")` and
    `run_native_dynamics_fit_bytes()`, exactly as design.md § "Supporting
    References" specifies (the twelve-description table, the zeros at record 0
    and across a three-record pause, the uint16 sentinel, the float32 values,
    the diverging developer Speed and Distance, humidity 104, four laps without
    heart rate or cadence, `num_laps` 1, the session timestamp equal to the
    fourth lap's start, no session heart rate, Run Profile; and the
    HealthFit-copy shape with a `SESSION UUID` containing 255). The Stryd
    fixture writes `manufacturer` into both its `file_id` and its
    `device_info` at device index 0 (`stryd` by default, so a Stryd page is
    never attributed to Garmin once `intervals-connector` lands) and uses the
    helper's private Encoder routine for its own message list. Built from the
    module's shared private helpers and deterministic constants; the module
    docstring's family list gains all three builders. The 255-containing
    identifier is a new constant, never an edit to `_SESSION_UUID_BYTES` or
    `_SESSION_DEV_FIELD_VALUES`
  - Shape self-tests in `tests/fixtures/test_builder.py`, decoding with
    `decode_messages` (these are the preconditions later tasks' assertions
    rely on, so each asserts the raw shape is present before any fitdocs code
    sees it): every description's `key` differs from its
    `field_definition_number`; key 0 is `Air Power` at definition 11;
    `native_mesg_num` is 6, 5 and 13 on Speed, Distance and Stryd Temperature;
    record 0 and the pause carry raw 0 heart rate (four records in total) and
    raw 0 dynamics; one record carries raw Form Power `65535`; a Leg Spring
    Stiffness value decodes to a float that is not its two-decimal source;
    Stryd Humidity reaches 104; four `lap_mesgs` without `avg_heart_rate`;
    session `num_laps == 1`, session `timestamp` equals the last lap's
    `start_time`, no session `avg_heart_rate`; the native-dynamics fixture's
    records carry `vertical_oscillation`, `stance_time`, `vertical_ratio` and
    no `stance_time_balance` or `step_length`, and its `SESSION UUID` contains
    255. The Stryd fixture's `device_info_mesgs` entry with `device_index` 0
    has manufacturer `stryd`. `stryd_run_fit_bytes(manufacturer="garmin")`
    decodes to messages equal to the default's in every message list except
    `file_id_mesgs` and `device_info_mesgs`, where the variant's
    manufacturer is `garmin` and nothing else differs. The helper's output
    decodes each given name at its given key and definition number; given
    `session_fields`, the session message carries
    each given value under its description's key, and without it the session
    carries no developer field; `device_manufacturer="stryd"` alone puts
    `stryd` on device index 0 and leaves `garmin` in `file_id`;
    `manufacturer="stryd"` alone (`device_manufacturer` left `None`) puts
    `stryd` in both `file_id` and device index 0; the all-default output
    decodes `garmin` in both. Building each fixture twice yields identical
    bytes
  - Named mutations (in the builder, the code these self-tests test): put the
    hard-coded `"garmin"` back in `_device_info` (the Stryd `device_info`
    pin reds); write `manufacturer` into the Stryd fixture's `file_id` only
    (the `manufacturer="garmin"` equality pin reds on `device_info_mesgs`);
    drop `session_fields` from the helper's session message (the
    session-field pin reds); ignore `device_manufacturer`, always writing
    `manufacturer` to device index 0 (the `device_manufacturer="stryd"` pin
    reds); default `device_manufacturer` back to `"garmin"` (the
    `manufacturer="stryd"`-alone pin reds on device index 0)
  - Done: the three builders exist and their self-tests pass; the existing
    fixture tests and every golden stay green unchanged, which is the
    evidence that the new `_file_id` and `_device_info` defaults move no
    existing fixture's bytes; no file under `src/` changed
  - _Requirements: 10.3_
  - _Boundary: StrydFixtures_
  - Parallel with 1.1: touches only `tests/fixtures/`, and no fixture needs
    the new model fields to be encoded

- [ ] 2. Core ingest: one developer decoding rule, record-level developer fields, the placeholder rules, the dynamics channels

- [x] 2.1 Build the shared developer-value decoder and move the session reader onto it
  - Create `src/fitdocs/ingest/developer.py` per design.md
    § DeveloperDecoding: `FieldDescription`, `parse_field_descriptions`, the
    FIT base-type invalid-value table, `decode_developer_value` (sentinel,
    then float32 shortest decimal, then declared scale), `application_ids`,
    and `apply_declared_scale`, moved verbatim from `summary._developer_value`
    and `_scale_one` with their docstrings
  - In `src/fitdocs/ingest/summary.py`, the session reader keeps both public
    signatures, key pairing, scale-0 omission, the declared-scale set and the
    last-described-wins name rule, and passes each recorded value through
    `decode_developer_value`, omitting a key whose result is `None`. Module
    and function docstrings say so. `_product_name` and everything outside
    the developer-field functions are untouched
  - `tests/ingest/test_summary.py`: only the `_developer_value` import
    changes (aliased from `fitdocs.ingest.developer.apply_declared_scale`); no
    test body is edited. New session cases, built with
    `developer_field_run_fit_bytes` (task 1.2) through its `session_fields`: a
    uint16 field recorded as `65535` is omitted; a 16-entry uint8 identifier
    containing 255 comes back as the same 16-tuple and
    `contract.format_session_uuid` formats it; a float32 session value comes
    back as its shortest decimal
  - `tests/ingest/test_developer.py`: the invalid-value table equals
    `garmin_fit_sdk.fit.BASE_TYPE_DEFINITIONS[code]["invalid"]` for each of the
    fourteen integer base-type codes (with an assertion that fourteen were
    compared); scalar sentinels for at least uint8, uint16, sint16, uint32z and
    byte; non-finite float32 scalar is `None`; an integer array of all
    sentinels is `None` while one with a single valid element is unchanged; a
    float array with one NaN keeps its finite elements; float32 shortest
    decimal for a two-decimal value and for a value that needs nine digits;
    a declared scale applied after rounding; an absent or unknown base type
    passes through; `application_ids` accepts only a 16-entry byte list
  - Named mutations: delete the sentinel check (the `65535` session case and
    the scalar sentinel cases red — M2's session half); filter integer arrays
    element by element (the identifier-with-255 case reds — M4); skip the
    float32 rounding (both float32 cases red — M5); apply the scale before
    rounding (the scale-after-rounding case reds)
  - Preserved, unedited: `test_hero_stats_supplementals_recognized_unknown_ignored`
    and `test_declared_scale_developer_field_is_not_double_scaled` in
    `tests/render/test_sections.py` (the humidity and METs rows) and the
    session-identity tests stay green
  - Done: the session reader's whole existing suite is green with only its
    import changed, and the new tests pass
  - _Requirements: 1.4, 1.5, 1.6, 1.7, 1.12, 2.1, 2.2, 2.3_

- [ ] 2.2 Read record-level developer fields and put them on the activity, index-aligned with the samples
  - Add `extract_record_developer_fields` to `ingest/developer.py` (omitting a
    description that declares scale 0, like the session reader), and
    `retained_records` (the existing drop-records-without-a-timestamp rule,
    now the one place it lives) to `ingest/records.py`, used by
    `extract_samples` too
  - `parse_fit` reads `developer_data_id_mesgs`, computes the retained records
    once, and sets `Activity.record_developer_fields`; the `ingest/__init__.py`
    docstring says so
  - Tests on `stryd_run_fit_bytes()` through `parse_fit`: the mapping's keys
    are exactly the eleven record-level names (the session-only Run Profile is
    absent); every channel's `values` has `len(samples.time_s)` entries;
    provenance: units verbatim, developer data index 0, each definition number
    from the fixture table, the application id as 32 lowercase hex characters;
    Form Power, Leg Spring Stiffness, Impact and the three balances carry
    exactly the fixture's values at every sample, zeros included (the
    placeholder rule belongs to the dynamics channels, not this generic
    mapping), the sentinel sample `None` and the float32 values at their
    two-decimal form; `record_developer_fields["Stryd Humidity"].values`
    contains 104 (decoded, never bounded); native `speed_mps` and
    `distance_m` equal the fixture's native values at every running record,
    never the developer Speed and Distance
  - Tests on synthetic files built with `developer_field_run_fit_bytes`
    (task 1.2): a record field declaring scale 10 and an offset decodes each
    value to `value / scale - offset` and its channel has `declared_scale`
    true, while an undeclared field's is false; a record field declaring
    scale 0 is omitted and nothing raises; a second description repeating
    an earlier (index, definition number) is not exposed under its name; two recorded
    descriptions sharing a name expose the later one's values; a described but
    unrecorded field, and one whose every value is a sentinel, are omitted; a
    file with no descriptions yields an empty, read-only mapping
  - Named mutations: pair values with the description whose
    `field_definition_number` equals the key (the exact-value pins red, the
    fixture's definition numbers swapping three pairs — M1); drop the scale-0
    guard (the scale-0 case raises `ZeroDivisionError` and reds); hard-code
    `declared_scale=False` (the declared-scale case reds); keep the first
    same-named description (the last-described pin reds); expose a description
    with no values as all-`None` (the omission pin reds)
  - Done: `parse_fit` on the Stryd fixture exposes eleven attributed record
    developer channels; the four model goldens and every golden document are
    unchanged
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.8, 1.9, 1.10, 1.11, 6.5_

- [ ] 2.3 Treat a 0 bpm heart-rate sample as not recorded, and keep every other recorded zero
  - In `extract_samples`, a recorded heart rate of exactly 0 becomes `None`;
    every other existing channel is read exactly as before
  - Tests in `tests/ingest/test_records.py`: a record with heart rate 0 holds
    `None` and one with heart rate 1 holds 1; one synthetic record recording 0
    power, 0 cadence, 0 speed, 0 distance, 0 altitude and 0 temperature keeps
    each as 0. Through `parse_fit` on `stryd_run_fit_bytes()`: heart rate is
    `None` at record 0 and across the pause (four positions) and equals the
    fixture's values elsewhere; the same holds for
    `stryd_run_fit_bytes(manufacturer="garmin")`. Through
    `compute_metrics` on the Stryd fixture: average and maximum heart rate
    equal the mean and maximum of the fixture's non-zero heart-rate constants,
    computed in the test
  - Named mutations: keep heart rate 0 (the record-0 pin and the metrics
    average pin red — M3's heart-rate half); apply the same rule to power (the
    recorded-zero pin reds); apply it only when the `file_id` manufacturer is
    Stryd, and separately only when the index-0 `device_info` manufacturer
    is Stryd (the `manufacturer="garmin"` pin reds for each, because that
    variant writes `garmin` into both messages)
  - Done: heart-rate placeholders are gone from both the samples and the
    derived average; the four model goldens and every golden document are
    unchanged
  - _Requirements: 5.1, 5.5, 5.6, 6.1_

- [ ] 2.4 Build the running-dynamics channel policy and wire it into the samples
  - Create `src/fitdocs/ingest/dynamics.py` per design.md § DynamicsPolicy:
    the native-field map, the seven-entry Stryd name table, the
    placeholder-zero set, the gate pairs and `extract_dynamics` (native values
    through `_fields.float_or_none`; a recognized developer value that is not a
    real number is `None`; placeholders first, then gates, per sample)
  - `extract_samples` gains the keyword `developer` and fills the twelve
    channels from `extract_dynamics`; `parse_fit` passes the record developer
    mapping in. The records module docstring's "all ten channels"
    (`ingest/records.py:5`) and its channel policy are corrected
  - `tests/ingest/test_dynamics.py`: the native map's keys and the name
    table's values partition `DYNAMICS_CHANNELS` (5 and 7); the placeholder set
    and the gate keys partition it (7 and 5); every gate target is in the
    placeholder set. On the native-dynamics fixture: vertical oscillation,
    stance time and vertical ratio equal the fixture's values and the other
    nine dynamics channels are all `None`. On the Stryd fixture: at record 0 and
    across the pause every placeholder channel is `None`; stance time balance
    and Vertical Oscillation Balance are `None` there; the mid-run Vertical
    Oscillation Balance recorded as 0.0 is `0.0`; air power is `None` at the
    sentinel sample and `0` where recorded 0 beside non-zero form power;
    `stryd_run_fit_bytes(manufacturer="garmin")` yields the same twelve
    channels. With `developer_field_run_fit_bytes` (task 1.2): developer
    fields named `Form power`, `Stryd Form Power`, `Power` and
    `Stryd Humidity` fill no channel and stay generic; a recognized name
    carrying an array value yields `None` at that sample
  - Named mutations: remove `form_power_w` from the placeholder set (the pause
    pins red — M3's stride half); drop the stance-time-balance gate (the pause
    balance pin reds — M6); treat 0 as a placeholder in balances (the mid-run
    0.0 pin reds); match names case-insensitively (the `Form power` pin reds —
    M12); fill `speed_mps` from developer Speed (task 2.2's native-speed pin
    reds — M7)
  - Done: `parse_fit` gives both fixtures their dynamics channels; the four
    model goldens and every golden document are unchanged
  - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 5.2, 5.3, 5.4, 5.6_

- [ ] 3. Core render: the shared axis, the section and chart, the run view

- [x] 3.1 (P) Extract the shared chart axis and add the two dynamics series colors
  - In `src/fitdocs/render/sections.py`, add `ChartAxis` and `chart_axis`
    holding the x-axis block of `hero_chart_spec` (`:366-378`) verbatim, and
    make `hero_chart_spec` call it
  - In `src/fitdocs/render/charts/palette.py`, add `DYNAMICS_PRIMARY_COLOR`
    and `DYNAMICS_SECONDARY_COLOR` with their oklch sources and the two
    `SERIES_COLORS` entries per design.md § DynamicsPalette; correct the
    comment at `:48-50` that counts "all nine" series colors
  - Tests: `chart_axis` returns km with samples lacking a distance dropped
    when distance exists, minutes otherwise, and `None` when no sample has an
    x value; the palette module's existing oklch-conversion tests cover the two
    new entries (assert `SERIES_COLORS` holds both names). Every existing
    hero SVG golden stays byte-identical, which is the evidence the extraction
    changed nothing
  - Named mutations: make `chart_axis` return minutes when distance exists
    (the axis test and the hero goldens red); change a new hex by 2 in one
    channel (the palette conversion test reds)
  - Done: no golden regenerated; the palette and axis tests pass
  - _Requirements: 8.2, 8.4_
  - _Boundary: ChartAxis, DynamicsPalette_
  - Parallel: depends on nothing in majors 1-2 (render only, existing
    `Samples` fields only), so it may run alongside them

- [x] 3.2 Build the Running Dynamics section table and chart
  - Create `src/fitdocs/render/dynamics.py` per design.md § DynamicsSection:
    the display table, the chart precedence, `dynamics_rows`,
    `dynamics_chart_spec` and `dynamics_section`. It imports no ingest,
    metrics, load or `fitdocs.contract` module
  - `tests/render/test_dynamics.py`, on `Samples` built by keyword: one row per
    present channel, in display order, none for an all-`None` channel; average,
    10th and 90th percentile on 30 pairwise-distinct values; coverage
    percentage; vertical oscillation shown in cm and step length in m with the
    stated decimals; a value that rounds to zero prints unsigned; balance
    labels carry no side word; the chart plots the first two present channels
    of the precedence in order and is absent when only balances, air power and
    impact are present or when no sample has an x value; a run of `None` in a
    charted channel produces separate polylines for that series in the chart
    SVG, never one line across the gap; `None` samples are excluded from every
    figure, never counted as 0; the link is
    `![Running dynamics chart](assets/<stem>-dynamics.svg)` and the asset's
    `rel_path` matches it; rendering twice gives identical text and SVG
  - Named mutations: compute the rank as `math.ceil(k / 100 * n)` (with n = 30
    and k = 10 it yields 4 where the integer rule yields 3, so the 30-value pin
    reds — M11; `math.ceil(k * n / 100)` also yields 3 and would survive, so it
    is not this mutation); swap the first two precedence entries (the
    chart-order pin reds — M10); forward-fill `None` in a charted series
    before building the spec (the separate-polylines pin reds); count `None`
    as 0 in the average (the recorded-only pin reds); return an empty table
    instead of `None` (the omission pin reds)
  - Done: the module and its tests pass; no view calls it yet; no golden
    changed
  - _Requirements: 6.5, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.3, 8.4, 8.5_
  - _Depends: 1.1, 3.1_

- [x] 3.3 Place the section on run pages, and only there
  - In `render_run_ride`, after the Telemetry block and before Splits, add
    `## Running Dynamics` and its assets for run modality only; update the
    view docstrings' section order
  - Tests in `tests/render/test_views.py`: a run with dynamics channels has
    the heading after Telemetry and before Splits; a run with dynamics but no
    telemetry and no map has it directly after Summary; a ride, a strength
    session and a generic activity carrying dynamics channels have no such
    heading; a run without dynamics has none, and the existing run goldens stay
    byte-identical
  - Named mutations: drop the modality check (the ride pin reds — M9); place
    the section after Splits (the order pin reds)
  - Done: every existing golden unchanged; the view tests pass
  - _Requirements: 7.1, 7.6, 7.7_

- [ ] 4. Integration: the new golden pages and a Stryd file synced alone

- [ ] 4.1 Register the two new golden documents and pin their observables
  - Add `stryd_run` and `run_native_dynamics` to `FIXTURES` in
    `tests/render/test_golden_docs.py` (`:102-108`) and generate their
    goldens with `uv run python -m tests.render.test_golden_docs`; no
    pre-existing golden changes
  - Structural pins over the generated documents: the Stryd page's Running
    Dynamics table has eleven rows (no vertical ratio) and its chart legend
    reads Ground contact time then Leg spring stiffness; the native-dynamics
    page's table has three rows and its chart plots Ground contact time then
    Vertical oscillation; the Stryd page's Avg HR equals the mean of the
    fixture's non-zero heart-rate samples, computed in the test from the
    fixture's own constants; in the Stryd page's body (the text after the
    frontmatter's closing fence) neither `104%` nor any label naming a record
    developer field (`Stryd Humidity`, `Stryd Temperature`) appears; the Stryd
    page's coverage table has no Temperature row; the native-dynamics page's
    frontmatter `uuid` is the canonical form of its 255-containing
    `SESSION UUID`, and its Summary shows the Humidity and Avg METs rows at
    their hundredths-scaled values
  - Named mutations: keep heart rate 0 (the Avg HR pin reds); add a display
    row reading `record_developer_fields["Stryd Humidity"]` (the `104%` pin
    reds); filter integer arrays element by element in the shared decoder (the
    `uuid` pin reds)
  - Done: two new goldens committed with their assets; the golden suite green
  - _Requirements: 2.3, 6.1, 6.5, 7.1, 7.2, 8.1, 10.1_
  - _Depends: 1.2, 2.4, 3.3_

- [ ] 4.2 Sync a Stryd file on its own, end to end
  - `tests/test_running_dynamics_e2e.py`: in a temporary data root, sync only
    the Stryd fixture through the CLI, as the existing sync end-to-end tests
    do. It exits 0; one run page exists with the Running Dynamics section; the
    `-dynamics.svg` asset exists and its link resolves; the page's Avg HR and
    max HR come from the non-zero samples; the device-lap table has four rows
    whose heart-rate cells show the absence marker; the moving and elapsed
    times equal the session's timer and elapsed totals; the page body (after
    the frontmatter) contains no `104%`
  - Named mutations: truncate `activity.laps` to the session's `num_laps`
    (the four-row pin reds); derive elapsed time from the session timestamp
    minus its start (the elapsed pin reds); show a missing lap heart rate as 0
    (the absence-marker pin reds)
  - Done: the end-to-end test passes against a real data root
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.4_

- [ ] 5. Contract advance, regeneration, and the spec records

- [ ] 5.1 Advance the document-format version and move every pin of the old value
  - Read `DOC_VERSION` on the branch rebased onto `main`; advance it by one
    and append a docstring paragraph naming the three causes (run pages gain
    the section; a 0 bpm sample is not recorded; a session developer sentinel
    or float32 value is decoded). Record the old and new values in the task's
    Implementation Notes
  - In `tests/test_running_dynamics_e2e.py`, add
    `_PRE_RUNNING_DYNAMICS_DOC_VERSION: int = <the old value just read>` with a
    docstring stating its provenance, following the precedent of
    `_PRE_AMENDMENT_DOC_VERSION` (`tests/test_sync.py:1633`). The value is
    recorded at implementation time from `main`, never taken from this plan
  - Move every literal pin of the old value: at design time
    `tests/test_cli_check.py:196,198` (in whatever form the branch holds it;
    a sibling may already have rewritten it as
    `f"doc_version: {DOC_VERSION}"`), `tests/render/test_frontmatter.py:44,101`
    and `tests/metrics/test_sources.py:2270`; a repository grep for
    `doc_version: <old>` and `DOC_VERSION == <old>` decides the rest, not this
    list. The moved `DOC_VERSION == <new>` pin in
    `tests/render/test_frontmatter.py` is what pins "exactly one" (9.2)
  - `tests/metrics/test_sources.py:2270`
    (`CONSTANT_REGISTRY_ASOF_DOC_VERSION: Final[int] = <old>`) is a literal
    to re-pin to the new value, not an as-of constant that stays: while no
    `CONSTANT_SOURCES` binding carries a `previous_value` (true today, and
    this spec moves no cited constant),
    `test_constant_trigger_is_quiet_against_the_real_registry` asserts it
    equals `contract.DOC_VERSION`. The grep patterns above do not match it,
    so it is named here; `activity-identity`, `channel-merge` and
    `intervals-connector` re-pin it the same way. Observe the pin live
    before moving it: the advance alone reds that test
  - Regenerate every golden document; `git diff` of each pre-existing golden
    shows exactly one changed line, its `doc_version` (the 9.1 evidence); the
    two new goldens change the same line only
  - `CHANGELOG.md` `[Unreleased]`: an entry for the Running Dynamics section
    under `### Added`, and an entry naming the generated document format and
    the action `fitdocs regen` under `### Changed`, per the changelog's
    convention. Append each under the section's existing heading of that
    category; create the heading only if the section lacks it
    (`tests/test_changelog.py:516`: a category repeated within one section
    is a violation; cross-spec ruling R8)
  - `git diff` of `src/fitdocs/contract.py` touches only `DOC_VERSION` and its
    docstring: `CONTRACT_VERSION` and `MANAGED_KEYS` are unchanged
  - After the branch's final rebase onto `main`, before merging: check that
    `DOC_VERSION` equals `main`'s value plus one. If a sibling landed a bump
    first, re-pin: advance from `main`'s value, re-record
    `_PRE_RUNNING_DYNAMICS_DOC_VERSION` as `main`'s value, move every site
    above again and regenerate the goldens (cross-spec ruling R1). Record the
    check in Implementation Notes
  - Named mutation: advance by two (the moved literal pins and
    `test_constant_trigger_is_quiet_against_the_real_registry` red)
  - Done: full suite green, `tests/test_changelog.py` included
  - _Requirements: 9.1, 9.2, 9.4, 9.5_

- [ ] 5.2 Prove that regeneration brings a pre-feature run page current
  - In `tests/test_running_dynamics_e2e.py`: sync the native-dynamics fixture;
    age its page by removing the Running Dynamics section and its image link
    and setting `doc_version` to `_PRE_RUNNING_DYNAMICS_DOC_VERSION`; write text
    into the notes region and a valid effort tag into the frontmatter. First
    assert the precondition `contract.DOC_VERSION > _PRE_RUNNING_DYNAMICS_DOC_VERSION`
    (a forward assertion, so a later sibling advance leaves it true rather
    than turning it red). `fitdocs check` reports the page stale;
    `fitdocs regen` restores the section, keeps the notes and the effort-tag
    keys byte for byte, and stamps `contract.DOC_VERSION`; a second
    `fitdocs check` reports it current
  - Named mutations: revert task 5.1's advance (the aged page then records the
    current version, so the precondition and the stale pin red); skip the
    section in the run view (the restore pin reds)
  - Done: the regeneration test passes
  - _Requirements: 9.2, 9.3_
  - _Depends: 5.1_

- [ ] 5.3 (P) Land the fit-ingest and workout-docs amendment records and their roadmap lines
  - `.kiro/specs/fit-ingest/requirements.md`: a new
    `## Amendment N (<date>): record-level developer fields and running dynamics, landed by running-dynamics`
    section and appended criteria per design.md § AmendmentRecords, each
    marked `_(added by Amendment N)_`, with `N` and every criterion number the
    next free one on `main` at this point (never assumed from this plan); a
    matching `amendments` entry in `spec.json` naming the tests that pin each
    criterion
  - `.kiro/specs/workout-docs/requirements.md` and `spec.json`: the same for
    the Running Dynamics section and chart (Requirements 6 and 7), adding the
    `amendments` key, which does not exist there today (or appending an entry
    if a sibling has added the key by then)
  - Roadmap, the one stated exception to design.md's out-of-boundary roadmap
    rule (cross-spec ruling R14), done last, after the branch's final rebase
    onto `main`, when `main`'s state is known: in `.kiro/steering/roadmap.md`
    Phase 8 `#### Existing Spec Updates`, tick the `fit-ingest` line if every
    other part it names (`activity-identity`'s, `intervals-connector`'s) is
    already on `main`, otherwise annotate it "(running-dynamics part
    landed)"; the same for the `workout-docs` line (other parts:
    `intervals-connector`'s, `activity-identity`'s, `channel-merge`'s). No
    other roadmap line changes
  - Done: `git diff` of both specs adds lines only (no criterion renumbered or
    reworded); both `spec.json` files parse; `/kiro-spec-status fit-ingest`
    and `/kiro-spec-status workout-docs` are clean; the roadmap diff touches
    those two lines only, each ticked or carrying the annotation
  - _Requirements: 1.1, 3.4, 4.1, 5.1, 7.1, 8.1_
  - _Boundary: AmendmentRecords_
  - Parallel with 5.1 and 5.2: touches only the two spec directories, and
    the roadmap's two lines at the merge

- [ ] 6. Validation: the evidence sweep

- [ ] 6.1 Classify every criterion, run the named mutations, and validate the whole change
  - For each of the 57 criteria, record PINNED (test and mutation),
    PRESERVED-ONLY (the existing test) or UNPINNED (with the mutation run that
    shows it), per `change-protocol.md` § The completeness half. 10.2 is
    PRESERVED-ONLY by the frozen-dependency tests
    (`tests/test_determinism.py:672-712`, `tests/test_packaging.py:503-519`);
    8.3 is pinned by task 3.2's separate-polylines case and preserved by
    `test_sparse_series_renders_multiple_segments_without_bridging`
    (`tests/render/charts/test_hero.py:238`)
  - Re-run M1-M12 (design.md § Testing Strategy) through `uv run pytest` on
    the finished tree and record which test reds for each; M1, M2 and M3 must
    each red at least one test (10.4)
  - Run the prose-claim grep from `change-protocol.md` over every changed test
    file and re-test each surviving claim; run the no-Stryd-web-address grep
    over every changed file (10.5)
  - Done: the classification table is in this task's Implementation Notes, and
    `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy`
    is green
  - _Requirements: 10.1, 10.2, 10.4, 10.5_

## Implementation Notes

- Main at 20e97a0 (maintainer-approved 2026-09-30) retired distribution's e74af37 `__all__`, golden-tree and render-package snapshot pins in `tests/test_preserved_guarantees.py`; before that they redded tasks 1.1 and 3.1 and would have redded every golden regen.
- 1.2: Stryd fixture = 44 records, placeholders (HR 0, dynamics 0) at record 0 and 20-22, uint16 sentinel at 10, VO Balance 0.0 at 12 (the one float32-exact developer value, by design), Air Power 0 at 14, humidity 104 at 30; laps (0,10),(11,21),(22,32),(33,43); serials 1201 helper / 1202 Stryd / 1203 native. Every other float32 developer series (positions 2-8) is float32-inexact. Native fixture: 20 records, `SESSION UUID` (255, 40..54). `device_info` index 0 decodes as `"creator"`; a `garmin` manufacturer adds a derived `garmin_product` key. `_file_id`/`_device_info` kwargs collide with activity-identity's (807c996): second lander keeps one set.
- 2.1: `ingest/developer.py` exposes `parse_field_descriptions`, `decode_developer_value` (returns `None` for a sentinel, a tuple for a list value), `application_ids`, `apply_declared_scale`, `INVALID_VALUES`; the caller omits scale 0. When 2.2 adds the record reader, name it as a second caller in `apply_declared_scale`'s scale-0 docstring bullet.
- 3.1: `chart_axis(samples) -> ChartAxis(unit, indices, x) | None`; pick series values by `axis.indices`.
- 3.2 / M11 (design § Testing Strategy, task 3.2, task 6.1): `math.ceil(k / 100 * n)` is an EQUIVALENT mutant of the integer nearest-rank rule (`10/100*30 == 3.0` exactly; identical for k in {10, 90}, n 1..1999). Use `(k*n)//100 + 1` as M11.
- 3.2: `dynamics_section(ctx)` returns `(body, assets)` with NO heading; the body ends with the image link when a chart exists. 3.3 prepends `## Running Dynamics` under `Modality.RUN` only and appends the assets after telemetry's. Round 3's two test-prose fixes were applied by the controller and re-reviewed (a downgrade from an implementer round).
