# Research & Design Decisions

## Summary
- **Feature**: `running-dynamics`
- **Discovery Scope**: Extension (light discovery). The feature widens the
  existing ingest layer and adds one section to the existing run view; no new
  dependency, service or storage. Research was done in the spec writer's own
  context (no research subagents were dispatched).
- **Key Findings**:
  - `garmin-fit-sdk` already hands back record-level developer data on every
    decoded message as `developer_fields`, keyed by the position of the
    `field_description` message, with raw values: no declared scale applied,
    no invalid sentinel filtered, float32 values widened to Python floats
    with their binary noise. The session reader already solves the keying
    and the scale; it lacks the sentinel and float rules.
  - `Samples` is constructed at 46 call sites across 34 files (3 in two
    `src/` modules, `ingest/records.py` and `load/channels/weighting.py`;
    43 in tests). Adding required fields is not viable; defaulted fields
    normalized in `__post_init__` keep every call site valid and keep the
    equal-length invariant true for every instance.
  - Nothing in `src/` reads `session.num_laps` or a session message's
    `timestamp`: two of the Stryd quirks are already harmless by construction
    and need regression pins, not code.

## Research Log

### How the SDK exposes developer data
- **Context**: Requirement 1 needs a record-level reader; the brief lists four
  SDK behaviors consumers must handle.
- **Sources Consulted**: `garmin_fit_sdk/decoder.py` in the project venv
  (profile 21.208.0): the developer-data branch of message decoding,
  `__add_field_description_to_profile`, `__build_dev_data_struct_string`,
  `__lookup_developer_data_field`; `garmin_fit_sdk/fit.py`
  `BASE_TYPE_DEFINITIONS`; a throwaway probe file encoded and decoded in the
  spec writer's scratch directory (not committed).
- **Findings**:
  - Values are stored as `developer_fields[field_profile['key']]`, where
    `key` is the index of the `field_description` message in
    `field_description_mesgs` (`message['key'] = len(...)` at decode time).
    The probe confirmed a description at key 0 with definition number 11.
  - The SDK comment `#NOTE possible point to scrub invalids????` marks the
    spot where no invalid filtering happens. A UINT16 `65535` came back as
    `65535`.
  - A float32 value comes back as a Python float: `11.37` encoded came back
    as `11.369999885559082`.
  - `__lookup_developer_data_field` returns the first registered field whose
    definition number matches, so a re-described (index, definition number)
    pair is decoded against the first description. The later description
    still receives its own `key`, but no value is ever stored under it.
  - `fit_base_type_id` decodes as the raw integer, endian flag included
    (`132` for UINT16, `136` for FLOAT32, as a real writer encodes it; `4`
    or `8` when a test encoder is given the masked value). Masking with
    `0x1F` (the SDK's `BASE_TYPE_MASK`) yields the base type in both cases.
  - `native_mesg_num` is decoded and stored on the description (the probe's
    `6` came back as `6`) and never used by the SDK.
  - `developer_data_id_mesgs` carries `developer_data_index` and a 16-entry
    `application_id` list.
  - A single-element developer value is returned as a scalar; a multi-element
    one as a list. String values are converted by the SDK; an empty string is
    `None` and is not stored at all.
  - The SDK's own float invalid check (`raw != 0xFFFFFFFF` on an unpacked
    float) can never fire, because the all-ones float32 pattern unpacks to a
    NaN. A reader must test "non-finite" instead.
- **Implications**: pair by `key` (as `summary.py` does today); filter the
  base type's sentinel after the SDK; round float32 values; parse the base
  type by masking; never read `native_mesg_num` / `native_field_num`.

### Native running-dynamics fields in the FIT profile
- **Sources Consulted**: `garmin_fit_sdk.profile.Profile['messages'][20]`.
- **Findings** (record message, field number, type, scale, units):
  `vertical_oscillation` 39, uint16, 10, mm; `stance_time_percent` 40, uint16,
  100, percent; `stance_time` 41, uint16, 10, ms; `fractional_cadence` 53,
  uint8, 128, rpm; `vertical_ratio` 83, uint16, 100, percent;
  `stance_time_balance` 84, uint16, 100, percent; `step_length` 85, uint16,
  10, mm. The SDK applies native scale and filters native sentinels, so these
  arrive in their profile units or absent.
- **Implications**: the model keeps the profile's own units (mm, ms, %), so
  ingest performs no lossy conversion; display conversion (cm, m) is a render
  concern. `stance_time_percent` and `fractional_cadence` are not in this
  spec's scope.

### Stryd developer-field names
- **Context**: Requirement 4 recognizes Stryd's channels by exact name. The
  brief names form power, air power, leg spring stiffness and impact, and
  "three balance channels" without their spellings.
- **Sources Consulted**: the public Go package documentation for
  `github.com/wisborg/fitactivity` on pkg.go.dev, which registers the three
  Stryd balance developer-field keys and names the others; a web search on
  the three spellings. No Stryd site, service or endpoint was contacted and
  none is named anywhere in this spec.
- **Findings**: the developer-field names are `Form Power`, `Air Power`,
  `Leg Spring Stiffness`, `Impact`, `Leg Spring Stiffness Balance`,
  `Impact Loading Rate Balance` and `Vertical Oscillation Balance`. A Garmin
  watch running Stryd's Connect IQ field additionally records a developer
  field named `Power`.
- **Implications**: an exact-name table of seven entries. `Power` is not
  recognized: native power already exists and a second power channel is out
  of scope. Whether a Stryd balance is a left-side share or a signed
  difference is not established by any public source consulted, so the page
  never labels a side (7.5) and the pause rule for balances is a gate on the
  paired stride channel rather than "zero is a placeholder" (5.3).

### What the render layer and metrics already do
- `metrics/aggregates.py` `avg_heart_rate_bpm` / `max_heart_rate_bpm` already
  fall back from the session value to the heart-rate channel. A Stryd file's
  missing session heart rate is therefore already computed from the stream;
  the defect is only that the stream contains placeholder zeros.
- `render/splits.py` builds the device-lap table from `activity.laps` (one
  row per lap message); `num_laps` is never read.
- `grep` over `src/` finds no read of a session or activity `timestamp`;
  elapsed and moving time come from the session totals
  (`ingest/summary.py:310-311`).
- The coverage table (`render/sections.py:117-128`, `_coverage_table`
  `:567-585`) emits a row only for a channel with data, so channels added
  elsewhere cannot change a page that lacks them.
- `render/charts/hero.py` renders any one or two plain series over a
  prepared x-axis; it has no knowledge of which channels it draws.

### Golden and version pins the change must move
- `DOC_VERSION` is `5` at `src/fitdocs/contract.py:174`.
- Literal pins of that value: `tests/test_cli_check.py:196,198` and
  `tests/render/test_frontmatter.py:44,101`, plus the `doc_version: 5` line
  in each of the 9 golden documents under `tests/render/golden_docs/`.
- One more, found by the Phase 8 cross-spec review (2026-09-29):
  `tests/metrics/test_sources.py:2270`,
  `CONSTANT_REGISTRY_ASOF_DOC_VERSION: Final[int] = 5`. It reads like an
  as-of constant, but while the cited-constant registry is clean
  `test_constant_trigger_is_quiet_against_the_real_registry` asserts it
  equals `contract.DOC_VERSION`, so it moves with every advance. The
  `doc_version: <old>` / `DOC_VERSION == <old>` greps miss it; the design
  names it.
- `tests/golden/{run,ride,strength,minimal}.json` serialize every model field
  generically (`tests/golden/_serialize.py`), so any model field addition
  changes them; the serializer already handles dataclasses and mappings.
- `tests/test_public_api.py` pins `fitdocs.__all__` exactly.
- `docs/plugins.md`'s ``From `fitdocs`:`` list is the documented public
  surface; `tests/test_docs_guarantees.py` checks every listed name imports
  (no reverse check exists for `fitdocs`, only for `fitdocs.load`), so
  listing `DeveloperChannel` there is what makes it public (cross-spec
  ruling R11).

### Fixture builder facts the fixtures depend on
- `tests/fixtures/builder.py`'s `_device_info` hard-codes
  `manufacturer: "garmin"` (`:157-168`), and every family's device index 0
  comes from it. `intervals-connector`'s attribution line names Garmin when
  that device is a Garmin one, so a Stryd fixture built with the unchanged
  `_device_info` would render as a Garmin recording. Hence the keyword-only,
  defaulted `manufacturer` parameter (cross-spec ruling R12).
- `_file_id` and `_device_info` are also called directly by five test
  modules outside `builder.py`; keyword-only, defaulted parameters keep all
  of them valid and every existing fixture's bytes unchanged.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Channels on `Samples`, defaulted | 12 new tuple fields appended to `Samples`, default `()`, filled to `(None,)*n` in `__post_init__` | One channel set, enumerable by `dataclasses.fields`; every existing constructor keeps working; equal length holds for every instance | A new `__post_init__` pattern in the model | Selected |
| Required fields on `Samples` | Same fields, no default | Simplest type story | 46 constructor call sites across 34 files edited, colliding with every parallel session | Rejected |
| Companion `RunningDynamics` object | `Samples.dynamics: RunningDynamics \| None` | No change to existing fields | Two channel sets; `channel-merge` must special-case it, contrary to the roadmap's "generic over the channel set" | Rejected |
| Developer channels inside `Samples` | `Samples.developer: Mapping[...]` | Alignment co-located | A non-tuple field breaks generic channel iteration | Rejected; generic developer channels live on `Activity` |

## Design Decisions

### Decision: Twelve channels in the model's own units
- **Context**: 3.1, 4.1 and the brief's "units are normalized".
- **Alternatives Considered**:
  1. SI base units (m, s): `stance_time_s = 0.245`.
  2. The FIT profile's units (mm, ms, %), with W, kN/m and body weights for
     the Stryd channels.
- **Selected Approach**: option 2. The unit is carried in the field name, as
  every existing channel does (`_bpm`, `_mps`, `_deg`).
- **Rationale**: no lossy float division at ingest; the SDK's decoded values
  are stored verbatim, matching Requirement 3.6 of `fit-ingest`
  (raw values, no smoothing).
- **Trade-offs**: the model's unit vocabulary grows (mm, ms, pct, kN/m, bw).

### Decision: Placeholder zeros by physical possibility, balances by gate
- **Context**: Requirement 5; the brief's "zero-at-pause values do not become
  data" against `fit-ingest` 12.3's "a recorded true zero is data".
- **Alternatives Considered**:
  1. Treat 0 as absent in every dynamics channel.
  2. Detect pauses (speed or cadence 0) and null every dynamics channel there.
  3. Zero is a placeholder where zero is not a physically possible
     measurement; a channel where 0 is possible is gated on its paired
     stride channel.
- **Selected Approach**: option 3. Heart rate and the seven stride-describing
  channels (stance time, vertical oscillation, vertical ratio, step length,
  leg spring stiffness, impact, form power) treat 0 as a placeholder. The
  four balances are gated on their paired stride channel; air power is gated
  on form power.
- **Rationale**: option 1 would erase a genuine 0% signed balance; option 2
  depends on channels a file may not record and on a speed threshold that
  would need its own citation. Option 3 is local, per sample, and needs no
  threshold. It leaves `fit-ingest` 12.3 intact for every channel where a
  zero is physically possible.
- **Trade-offs**: a file recording a balance without its paired stride
  channel loses that balance (never fabricates it). No known writer does
  this.

### Decision: One shared per-value decoder for session and record fields
- **Context**: the brief's "sharing the scale and invalid handling"; the
  maintainer's 2026-07-25 HealthFit fixes must not regress.
- **Selected Approach**: `ingest/developer.py` owns sentinel filtering,
  float32 rounding and the declared scale (the latter moved verbatim from
  `summary.py`). The session reader keeps its signature, its key-based
  pairing, its scale-0 omission and its last-described-wins name rule, and
  calls the shared decoder per value. Arrays are filtered only as a whole
  for integer base types, so a 16-byte identifier containing `0xFF` stays
  intact.
- **Rationale**: one decoding rule; the only session-level values that change
  are sentinels (never real) and float32 values (the HealthFit descriptor
  surveys on record, in the two 2026-07-25 queue items, found only UINT8 and
  UINT16 base types).
- **Follow-up**: the render layer's hundredths fallback for `AVG METs` and
  `SESSION WEATHER HUMIDITY` is untouched and still keyed on
  `developer_fields_declared_scale`.

### Decision: Last-described wins on a duplicated name
- **Context**: 1.9. The session reader resolves a duplicated name by
  assignment in description order, so the last recorded description wins.
- **Selected Approach**: the record-level reader applies the same rule, so
  the two readers never disagree on which field a name denotes.

### Decision: Dynamics summaries are a render-time presentation
- **Context**: 7.2-7.3; `channel-merge` must know which summaries a donated
  channel feeds.
- **Selected Approach**: `render/dynamics.py` computes average, 10th and 90th
  percentile (nearest rank) and coverage from the channels when the page is
  rendered, as `render/splits.py` computes per-slice aggregates. No field is
  added to `SessionSummary` or `DerivedMetrics`, and no frontmatter key.
- **Rationale**: a donated dynamics channel then needs no summary
  recomputation, and the frontmatter contract is unchanged.

### Decision: Reuse the hero chart renderer for the dynamics chart
- **Context**: Requirement 8.
- **Alternatives Considered**: a new scatter chart (ground contact time vs
  pace); a new multi-panel chart; the existing hero renderer with two
  dynamics series.
- **Selected Approach**: the hero renderer, fed a `HeroChartSpec` built from
  the first two present channels of a fixed precedence, over the hero
  chart's own x-axis, with no altitude backdrop, and two new palette colors.
- **Rationale**: no new SVG code; smoothing, gap splitting, legend and
  determinism are already proven. The x-axis rule is extracted from
  `hero_chart_spec` into one helper so the two charts cannot diverge.

### Decision: Environmental developer values are never rendered
- **Context**: 6.5; Stryd writes humidity above 100%.
- **Alternatives Considered**: clamp to [0, 100]; drop out-of-range values
  at ingest; do not render.
- **Selected Approach**: do not render. Stryd's temperature and humidity stay
  generic record-level developer fields on the model, decoded but not
  interpreted.
- **Rationale**: bounding at ingest would be an undeclared convention, which
  `fit-ingest` 14.2 forbids. A plausibility guard on rendered humidity was
  considered and declined by the maintainer on 2026-07-25 (queue
  `2026-07-25-supplemental-scale-single-writer`); this spec does not reopen
  that decision.

## Risks & Mitigations
- A non-Stryd writer names a developer field `Impact` or `Form Power` with a
  different meaning. Mitigation: none beyond exact-name matching; the same
  single-writer risk the open supplemental-scale queue item records for
  HealthFit's names. Recorded, not solved.
- Stryd's balance convention is unknown. Mitigation: no side label on the
  page; the gate rule does not depend on the convention.
- Parallel model edits (`activity-identity`). Mitigation: append-only,
  defaulted fields; the second lander regenerates the model goldens and
  re-pins `fitdocs.__all__`.
- `DOC_VERSION` contention. Mitigation: advance by one from `main` at landing
  and move every literal pin in the same change; after the final rebase,
  check the value is `main`'s plus one and re-pin if a sibling landed first
  (cross-spec ruling R1).

## References
- `garmin-fit-sdk` 21.208.0 (project venv): `decoder.py`, `fit.py`,
  `profile.py` — developer-data decoding, base-type sentinels, record fields.
- [fitactivity Go package documentation](https://pkg.go.dev/github.com/wisborg/fitactivity)
  — Stryd developer-field names, including the three balance spellings.
- `.kiro/specs/fit-ingest/requirements.md` Requirement 14 and Amendment 2 —
  the decoding/interpretation line this spec extends.
- `.kiro/queue/2026-07-25-supplemental-scale-single-writer.md` — left alone.
