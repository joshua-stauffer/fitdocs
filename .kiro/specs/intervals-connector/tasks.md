# Implementation Plan

## Upstream Prerequisites

- **`connectors` is merged to `main` before any task here starts.** Its plan
  names this one as its dependent (`.kiro/specs/connectors/tasks.md:12-17`).
  This plan implements its protocol and uses its `HttpClient`, `FakeTransport`,
  registry, `load_connectors_settings`, `env_var_name`, `run_pull`,
  `run_connect`, the CLI's `_connector_transport` seam, the
  `tests/connectors/conftest.py` socket guard and environment isolation, the
  boundary guard (`tests/connectors/test_boundary.py`), the docs test
  (`tests/connectors/test_docs.py`) and `docs/connectors.md`. A task that finds
  a landed shape differing from `connectors`' design.md only in a name adapts
  to what landed and says so in its report; a task that finds a behavioural
  difference (an operation's signature, a fetch answer, a retry bound, the
  credential or ledger form) stops and reports rather than changing
  `connectors`' code.
- **`activity-identity` is not an implementation prerequisite.** It is a
  prerequisite of *real use*: nobody points this connector at a real data root
  that already holds other copies of the same rides until identity has merged
  (roadmap Phase 8 constraint; documented by 4.2).
- **Siblings touching the same files** (`running-dynamics`,
  `activity-identity`, `channel-merge`): `src/fitdocs/render/views.py`
  (shared with `running-dynamics` and `channel-merge`, append-only),
  `src/fitdocs/render/__init__.py` (shared with `channel-merge` and
  `activity-identity`, append-only; read, not edited, by this plan),
  `tests/fixtures/builder.py`, `src/fitdocs/contract.py`'s `DOC_VERSION` and
  its pins, `tests/render/golden_docs/`, `CHANGELOG.md` `[Unreleased]`.
  Rebase and keep both sides; the version rule is below.
- **Task 1.1 belongs to the maintainer** and carries a `_Blocked:_` line,
  which is what `/kiro-impl` skips (`.claude/skills/kiro-impl/SKILL.md:86`):
  it needs an intervals.icu key that no agent holds and that this repository
  never holds. No task depends on it except 5.2, which is `_Blocked:_` too;
  list order does not make 2.1 onward wait for it.
- **Where the merge happens.** 5.1 is the last task before the branch merges
  to `main` (change-protocol lifecycle step 4) and does the roadmap
  bookkeeping at that merge. 5.2 runs later, on its own branch under
  change-protocol, once 1.1's findings are in `research.md`.

## Hard rules for every task

- **No network, no real credentials.** Every connector test lives under
  `tests/connectors/`, where `conftest.py`'s autouse fixtures make
  constructing a socket raise and isolate `FITDOCS_CREDENTIALS_DIR`, `HOME`,
  `XDG_CONFIG_HOME` and every `FITDOCS_CONNECTOR_*` variable. Requests reach
  only `FakeTransport` or the CLI's patched transport seam.
- **No personal data.** The key is the synthetic `ik-synthetic-7Q2x9`;
  activity ids are synthetic (`i9000001`, `i9000002`, …); dates derive from
  `tests/fixtures/builder.py`'s fixed epoch; FIT bytes come from the builder;
  GPX and TCX bodies are written in the test. No value from any real account
  appears in a test, fixture, doc or spec file.
- **The key and its encoded form** appear only in the `Authorization` header
  the connector registers as a secret; never in a URL, message, report, ledger
  or file.
- **Imports** (design.md "Allowed Dependencies"): `connectors/intervals.py`
  imports only the standard library and, by absolute import,
  `fitdocs.connectors.{errors,http,protocol,secrets}`; never the standard
  library's `http` package, `urllib.request`, `urllib.error`, `socket` or
  `ssl`; no clock call (`session.now` only). `render/attribution.py` imports
  only the standard library and `fitdocs.model`. No new runtime dependency
  (`tests/test_determinism.py:672-712`, `tests/test_packaging.py:503-519`).
- **Absent is `None`**: no default, `0` or empty string for a value the
  service or the file did not state.
- **Versions** (cross-spec ruling R1, `DOC_VERSION` half): every lander
  advances `DOC_VERSION` by one from `main`'s value when it lands, never
  sharing a sibling's bump. It advances once, in 2.3, by one from the value
  on the branch when that task runs; after the final rebase 5.1 checks it
  equals `main`'s value plus one and, if a sibling landed a bump first,
  re-pins every site and regenerates the goldens. No
  task hard-codes the resulting number outside `contract.py`'s docstring and
  the re-pin sites. `CONTRACT_VERSION` and `MANAGED_KEYS` never move here.
- **Contract-consumer guards**: no module under `src/fitdocs` other than
  `contract.py` names `uuid` (`tests/test_contract_consumers.py:502-529`);
  `render/views.py` is a registered consumer, so no new name there appears in
  `FORBIDDEN_LOCAL_NAMES` (`:149-163`).
- **`connectors`-owned files** are edited only where design.md "Shared-file
  touches" says, append-only: one import and one registration in
  `src/fitdocs/connectors/__init__.py`, two set entries in
  `tests/connectors/test_boundary.py`, the heading pin and the
  `intervals.icu` entry in the service-neutral scan's exemption table in
  `tests/connectors/test_docs.py`, one section of
  `docs/connectors.md`, any registry-exactness assertion 3.1 names, and any
  statement 4.2's sweep corrects (in `docs/connectors.md`, the connectors
  package's docstrings or a sentence `tests/connectors/test_docs.py` pins),
  each listed in that task's report.
- **Fixture Discrimination** (`change-protocol.md`): every new assertion owes
  the named mutation listed in its task, applied to production code, run
  through `uv run pytest` (never `uv run python -c`), observed red, reverted
  green. Fixtures violate the property the code establishes; preconditions are
  asserted before postconditions. A task reports any listed mutation it could
  not make red.

## Shared files inside this plan

- `src/fitdocs/connectors/intervals.py` and `tests/connectors/test_intervals.py`:
  created by 3.1, extended by 3.2, 3.3 and 3.4, strictly in that order.
- `tests/connectors/test_docs.py`: 3.1 (the exemption-table entry), then 4.2
  (the heading pin).
- `tests/fixtures/builder.py`: 2.1 only (append).
- `src/fitdocs/render/views.py`, `src/fitdocs/contract.py`, the `DOC_VERSION`
  re-pin sites and `tests/render/golden_docs/`: 2.3, and after the final
  rebase 5.1 (the `DOC_VERSION` re-pin, and the donor wiring if
  `channel-merge` landed while this branch was open).

- [x] 1. The live viability check (maintainer only)

- [x] 1.1 Run the live viability check against the athlete's own intervals.icu account and record what it finds
  - Performed by the maintainer with their own key, following design.md
    "LiveCheckProcedure" steps 1-8, in a temporary directory outside the
    repository and the data root, deleted afterwards; the key is read without
    echo and never written anywhere. No agent performs, records or ticks this
    task
  - Answers the brief's three questions (intervals.icu receives the Edge rides
    from Garmin directly, not through Strava; the original is a gzip FIT
    carrying power, pedal dynamics and the full record set; whether its bytes
    equal the Garmin Connect export's original) and confirms or contradicts
    each of TBC-1 to TBC-9
  - TBC-9, locally and with no intervals.icu request (design.md
    "LiveCheckProcedure" step 7; cross-spec ruling R15): open one HealthFit
    copy of a Garmin ride and one HealthFit run copy locally and record the
    `device_info` index-0 manufacturer/product of each (shape only, never
    committed)
  - Observable: `research.md` "Live check findings" names the check date and
    each of TBC-1 to TBC-9 as confirmed or contradicted, with shapes,
    vocabulary values, booleans and counts only — no activity or athlete id,
    date of an activity, name, location, file or key. This record is the only
    place a TBC item is marked; 5.2 reads it and does not re-mark it
  - _Requirements: 9.1, 9.2, 9.3, 9.5_
  - _Done 2026-10-02: at the maintainer's explicit request (Req 9.5 as amended), the `/kiro-impl` controller session ran it with the maintainer's key from the gitignored `.env`, never passed to a subagent or written; findings in `research.md` "Live check findings" (TBC-5, TBC-6, TBC-8 contradicted; TBC-6 repaired in 3.4; TBC-5/TBC-8 need no code change)_

- [ ] 2. Garmin product names and the attribution line

- [x] 2.1 (P) Resolve Garmin product names at ingest from the FIT SDK's profile, with a shared multi-device ride fixture
  - Append to the builder a ride whose one device message is replaced by four
    with pairwise-distinct serials: the recording device (index 0) made by
    Garmin with code 3843 and no recorded name; index 1 made by Dynastream with
    code 3300; index 2 made by Garmin with code 65000; index 3 made by Wahoo
    with code 3843. No existing builder function or default changes
  - Resolution: after the recorded name and a text product, the decoded
    Garmin-product sub-field when the SDK has turned it into a name; an
    unresolved code (still a number) leaves the name absent; no table of
    fitdocs's own; the function's docstring states the order
  - Pins (`tests/ingest/test_summary.py`, `tests/ingest/test_parse.py`):
    - preconditions: the fixture's decoded device messages carry the
      Garmin-product values `edge_1040`, `hrm_pro`, the number 65000, and no
      such value on the Wahoo device; 65000 is not a key of the SDK profile's
      Garmin-product table
    - parsing the fixture names the four devices `edge_1040`, `hrm_pro`,
      absent, absent
    - a decoded device carrying both the recorded name `SyntheticRideComputer`
      and a textual Garmin-product value `hrm1` (asserted present) keeps the
      recorded name
    - each resolved name equals the SDK profile's own entry for its code
    - `test_devices_product_name_falls_back_to_string_product`
      (`tests/ingest/test_summary.py:307-317`) passes unchanged
  - Named mutations: delete the new branch (the `edge_1040` pin reds); accept
    a numeric value as text (the 65000-is-absent pin reds); move the new branch
    above the recorded-name branch (the precedence pin reds); resolve only the
    recording device, index 0 (the `hrm_pro` pin reds — resolution is per
    device message, so no file context can change it); return a hand-written
    "Edge 1040" for code 3843 (the profile-equality pin reds)
  - Observable: `uv run pytest tests/ingest tests/test_golden.py
    tests/render/test_golden_docs.py` green with `git diff --stat tests/golden
    tests/render/golden_docs` empty — every existing fixture records a device
    name, which keeps winning
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - _Boundary: ProductNameResolution_

- [ ] 2.2 (P) Word the Garmin attribution for a page's contributing files
  - A pure module with design.md "GarminAttribution"'s three functions and
    signatures: the recording device of a device tuple (the first device with
    index 0); a Garmin label from a device tuple (its recording device's exact
    manufacturer `garmin`; the model with every whitespace run collapsed to
    one space; `Garmin` alone when the model is absent or blank; a model
    already reading `Garmin` or starting `Garmin ` in any case used as is);
    the line for a base activity and its donors' device tuples
    (`attribution_line(base: Activity, donor_devices: Sequence[Sequence[DeviceInfo]] = ())`),
    exactly as design.md words it (contributors are the base's devices then
    each donor tuple; labels deduplicated, base first; `Data source:` for one
    label with no other contributor, `Data sources:` with commas and a final
    "and" for several; `and other devices` whenever a contributor, an empty
    donor tuple included, has no Garmin label; no line without a Garmin
    label)
  - Pins (`tests/render/test_attribution.py`; `recording_device` and
    `garmin_label` called on hand-built device tuples, `attribution_line` on
    a base built by replacing the devices of a parsed
    `builder.ride_fit_bytes()` plus hand-built donor device tuples): Garmin
    creator `edge_1040` gives `Data source: Garmin edge_1040`; absent model
    gives `Data source: Garmin`; a `stryd` creator gives no line, and so does
    a Garmin device at index 1 listed before a `stryd` recording device; an
    empty device tuple and a lone index-1 Garmin device each give no
    recording device and no line; a model `Edge\n1040` gives one line
    `Data source: Garmin Edge 1040`; a model `Garmin Edge 1040` is not
    doubled; two index-0 devices, Garmin first then `stryd`, attribute the
    Garmin one; base Garmin with a `stryd` donor tuple, and base `stryd` with
    a Garmin donor tuple, give `Data sources: Garmin … and other devices`;
    base Garmin with a donor tuple whose index-1 Garmin device precedes its
    index-0 `stryd` device gives `Data sources: Garmin edge_1040 and other
    devices`; base Garmin with an empty donor tuple gives the same; base
    `fr965` with donor `edge_1040` gives `Data sources: Garmin fr965 and
    Garmin edge_1040` (a fixture in reverse alphabetical order); three Garmin
    models give `A, B and C`; a donor repeating the base's model gives one
    label; an import pin: the module imports nothing from `fitdocs` but
    `fitdocs.model`
  - Named mutations: iterate the devices in reverse (the two-creators pin
    reds); drop the index check (the index-1 pin reds); fall back to the
    first device when none has index 0 (the lone index-1 pin reds); take the
    first device without checking the tuple is non-empty (the empty-tuple pin
    reds); drop the whitespace collapse (the one-line pin reds); always
    prefix `Garmin ` (the not-doubled pin reds); format an absent model into
    the label (the `Data source: Garmin` pin reds); drop the others clause
    (both mixed-donor pins red); label a donor from its first device instead
    of through the recording-device rule (the donor-recording-device pin
    reds); skip empty donor tuples (the empty-donor pin reds); sort the
    labels (the reverse-order pin reds); drop the deduplication (the
    repeated-model pin reds); join every label with " and " (the three-model
    pin reds); import `fitdocs.connectors` in the module (the import pin
    reds)
  - Observable: `uv run pytest tests/render/test_attribution.py` green; the
    module has no caller yet
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_
  - _Boundary: GarminAttribution_

- [ ] 2.3 Put the attribution beneath the title of every view and advance the document format
  - One head helper in the views module gives the H1 and, when the wording
    yields one, the attribution line; the run/ride, strength and generic views
    all start from it, so the line sits directly beneath the H1, before the
    notes region and every section, outside every region; the module docstring
    names the line. `render/views.py` is shared with `running-dynamics` and
    `channel-merge`: append-only toward their sections and fields
  - Donor wiring (cross-spec ruling R2; design.md "ViewHead"): whichever of
    `channel-merge` and this spec lands second wires the head helper to pass
    `tuple(c.devices for c in ctx.channel_provenance.extras if c.channels)`
    as the donor device tuples (`()` when `ctx.channel_provenance` is `None`)
    and adds the ride-pair and non-donating pins below. If `SourceContribution.devices` and
    `DocContext.channel_provenance` are on the branch when this task runs,
    wire it here; if not, pass no donor devices and record in the report
    that `channel-merge` wires it (or that 5.1 does, should `channel-merge`
    land before this branch merges). The base's recording device stays the
    index-0 device of `ctx.activity.devices` (`channel-merge` keeps the
    composed activity's devices as the base's)
  - Advance `DOC_VERSION` by one from the branch's value with a docstring
    paragraph (the attribution line and the resolved device names); re-pin, in
    whatever form the branch holds them, `tests/test_cli_check.py:196,198`,
    `tests/render/test_frontmatter.py:44,101` and
    `tests/metrics/test_sources.py:2270`; regenerate the render goldens with
    `uv run python -m tests.render.test_golden_docs`: every golden on the
    branch gains the new version; each whose recording device is Garmin also
    gains one attribution line beneath the H1 (`Data source: Garmin
    Synthetic…` for the builder's default device); `minimal.md` and
    `map_generic.md`, rendered from the device-less minimal file
    (`tests/fixtures/builder.py:579-590`), are the device-less cases and
    change only in the version; a golden whose recording device is not
    Garmin — `running-dynamics`' `stryd_run`, whose fixture writes its
    index-0 device with manufacturer `stryd`, if it is on the branch — gains
    no line; a composed golden (`channel-merge`'s `composed_run`, if on the
    branch) carries no `Data source` line (`channel-merge`'s run pair
    records no Garmin device). No golden count is written in a test or the
    report's claims; any further exact pin the full suite turns red is
    moved and listed in the report
  - Pins (`tests/render/test_views.py`): for a Garmin-recorded activity in
    each of the three views — the run/ride and strength views from their
    builder fixtures, the generic view from the parsed minimal activity, each
    with its devices replaced by a Garmin index-0 `edge_1040` device — the
    first non-blank line after the H1 (asserted present once) is `Data source:
    Garmin edge_1040` and precedes the notes begin marker; the line lies in
    no region's content (regions read with the region parser); a
    `stryd`-recorded activity renders no line starting `Data source`;
    rendering `builder.garmin_devices_ride_fit_bytes()` gives the line
    `Data source: Garmin edge_1040` and a devices table whose rows name
    `edge_1040` and `hrm_pro`; the committed `minimal.md` and
    `map_generic.md` goldens (no device list) carry no `Data source` line —
    the golden case of 8.3's "the file names no recording device"; when the
    donor wiring lands here, the ride-pair pin: `channel-merge`'s ride pair
    (`tests/fixtures/merge.py`, a Garmin-original base and a HealthFit copy
    donating heart rate), composed and rendered as the drain renders it,
    after asserting as a precondition that the donor's recording device is
    not Garmin-made, gives `Data sources: Garmin <model> and other devices`
    beneath the H1; and a hand-built Garmin base whose only extra is
    non-Garmin and donates no channel gives `Data source: Garmin <model>`
    (the same two pins `channel-merge` 3.3 adds when it lands second)
  - Named mutations: emit the line after the notes region (the placement pin
    reds); start only the run/ride view from the head helper (the strength and
    generic pins red); emit the line inside the notes region block (the
    outside-regions pin reds); delete 2.1's branch (the devices-table pin
    reds); leave `DOC_VERSION` at its previous value after regenerating (the
    golden and frontmatter pins red); label an activity with no recording
    device `Garmin` instead of giving no label (the device-less goldens
    `minimal.md` and `map_generic.md` gain a line and red); when the donor
    wiring lands here, pass no donor devices from the head helper (the
    ride-pair pin reds: the line reads `Data source: Garmin <model>`) and
    drop the `if c.channels` filter (the non-donating pin reds)
  - Observable: every Garmin-recorded golden carries the line beneath its
    H1, every golden the advanced version, and the device-less and
    non-Garmin-recorded ones no line; the full `uv run pytest` green; the
    report states whether the donor wiring landed here or is left to
    `channel-merge` / 5.1
  - _Requirements: 8.1, 8.3, 8.4, 8.5, 8.7, 8.8_
  - _Depends: 2.1, 2.2_

- [ ] 3. The intervals.icu connector

- [ ] 3.1 (P) Declare and register the connector, parse its settings, and admit its address only in its own files
  - The connector module with every constant, the settings value, the
    download error and the declaration design.md "IntervalsConnector" states
    (id `intervals`, display name `intervals.icu`, the personal-key style, one
    secret field `api_key`, pull-activities only); the settings parser (the
    optional source filter, its default, its validation, unknown keys
    ignored). The three operations exist, so the registry's gate accepts the
    connector, and raise "not implemented" until 3.2-3.4 replace them; no 3.1
    test calls them
  - Register it in the package after the folder connector (one import, one
    call; not in the published surface, which stays at 46 names); append this
    module's allowed-import set and the package initializer's new entry to the
    boundary guard; append the `intervals.icu` entry (host →
    `connectors/intervals.py`, its test modules, and the intervals.icu
    section of `docs/connectors.md`) to the service-neutral scan's exemption
    table `NEUTRAL_SCAN_EXEMPTIONS`, under the host `intervals.icu`, with
    the files `src/fitdocs/connectors/intervals.py`,
    `tests/connectors/test_intervals.py`,
    `tests/connectors/test_intervals_pull.py`,
    `tests/connectors/test_intervals_docs.py` and the section key
    `docs/connectors.md#intervals.icu` (matching 4.2's `## intervals.icu`
    heading), keeping the check that the exemption is actually used:
    `connectors`' conditional positive control now runs, and one assertion
    beside it pins that the scan finds `intervals.icu` in `intervals.py`
    itself (design.md "BoundaryGuardEntry and NeutralScanExemption"); no
    other part of the scan changes and no `connectors` spec record is
    touched; move any `tests/connectors` assertion that pins the
    built-in registry, or the registered-ids message, as the folder connector
    alone, and list each in the report
  - Pins (`tests/connectors/test_intervals.py`): after a fresh import the
    registry returns this connector for `intervals` and the gate accepts it;
    the declaration's field, style and capability set; an instance table
    `[connectors.intervals]` with no `connector` key resolves to it through the
    connectors table reader; settings: absent gives the default; a two-name
    list; an unpublished well-formed name accepted; an empty list, a bare
    string, a lower-case name and a non-text item each refused naming `sources`
    and the offending value; an unknown key ignored; `sources = []` in a
    settings file read through the connectors table reader raises the
    settings error whose message names that file's path, the instance
    `intervals` and `[]`, and names the key `sources` in the reader's
    key-naming form for a connector settings error — whatever structured
    phrase or attribute `connectors` landed with for that wrapping, asserted
    as that form, not as the bare word `sources` (a wrapped plain exception's
    text could contain the word). The "before any request or write" half of
    2.2 is the framework's preflight, classified PRESERVED-ONLY by 5.1 against
    `connectors`' preflight pins
  - Named mutations: delete the registration line (the registry pin reds); add
    pull-thresholds to the capabilities (the declaration pin reds); accept a
    lower-case name (its pin reds); accept an empty list (its pin reds); raise
    a plain `ValueError` carrying the same text instead of the connector
    settings error (the framework then wraps it in its connector-naming form,
    so the key-naming-form pin should red — the implementer runs it and
    records the result, and reports it if it cannot red, since the connectors
    design does not say whether that wrapping repeats the original text); add
    `import urllib.request` to the module (the guard's network allow-list
    reds); add `from fitdocs import layout` (the per-module import pin reds);
    put an `https://intervals.icu/` address in `connectors/pull.py` (the
    neutral scan reds); put one in the folder connector's section of
    `docs/connectors.md` (the neutral scan reds: the entry admits only the
    intervals.icu section); change the module's service host to `example.org`
    (the finds-it-in-`intervals.py` assertion reds)
  - Observable: `uv run pytest tests/connectors` green (the whole package:
    a second built-in changes what the registry and settings tests see);
    importing the package registers `folder` and `intervals`; `uv run mypy`
    green
  - _Requirements: 1.1, 1.5, 2.1, 2.2, 2.3, 2.4, 5.6, 10.2, 10.4_
  - _Boundary: IntervalsConnector, ConnectorRegistration, BoundaryGuardEntry, NeutralScanExemption_

- [ ] 3.2 Check a key with one request, and keep the key and its encoded form out of everything but the header
  - The credential: the Basic value for username `API_KEY`, with the bare
    encoded token and the header value both registered as secrets and sent
    only as a secret header; the service-message helper (truncated, whitespace
    collapsed, passed through the session's redactor); the key check exactly as
    design.md words it (one listing request for athlete `0` with `limit=1`,
    no scopes on success, the status mapping)
  - Pins, calling the check with a session built from the published surface
    and a stub credential access: exactly one recorded request, path
    `/api/v1/athlete/0/activities`, `limit=1`, `fields=id`, `oldest` the day
    before the injected clock; the `Authorization` value equals the Basic form
    of the synthetic key and sits among the secret headers, not the ordinary
    ones; success grants absent scopes (not an empty tuple); 401, 403, 429
    with `Retry-After: 7`, 503 and 404 give rejected, blocked, rate-limited
    with a 7-second wait, unavailable, and unavailable naming 404; a 403 body
    echoing the bare encoded token raises a failure whose message shows the
    redaction marker and not the token; a 403 body echoing the raw key raises
    one whose message is already redacted before any framework code sees it;
    one run through the connect engine with a scripted 429 makes one request
    and stores nothing
  - Named mutations: pass the credential as an ordinary header (the
    secret-header pin reds); skip registering the bare token (the echoed-token
    pin reds); drop the redaction in the service-message helper (the raw-key
    pin reds); map 404 to rejected (its pin reds); grant an empty tuple of
    scopes (the absent-scopes pin reds); send the check twice (the one-request
    pin reds)
  - Observable: `uv run pytest tests/connectors/test_intervals.py` green
  - _Requirements: 1.2, 1.3, 1.4, 5.7_

- [ ] 3.3 List activities by overlapping date windows and map each entry onto a listed activity
  - The windows (design.md: first day one before the earliest start's UTC
    date, 90-day windows while the next start is before today, each upper
    bound one day past the next lower bound, the last without an upper bound,
    30 days when no earliest start is given); the listing request with the six
    fields; the response reader; the entry mapping in design.md's order; the
    status mapping for data calls, both its listing and download branches (the
    download branch is exercised in 3.4)
  - Pins: an earliest start 200 days back gives three requests with the
    stated bounds; 179 days back gives exactly two; none gives one request
    whose lower bound is 31 days before the injected clock; every request asks
    for exactly the six fields and none carries the key or its encoded form;
    with settings parsed from a table carrying `athlete = "i5"` and
    `api_base = "https://example.org"`, every request still goes to
    `API_BASE` under `/api/v1/athlete/0/`;
    one fixture listing whose entries each differ in one property from the
    others — an id present in two windows listed once; a source outside the
    filter and a missing source omitted; an entry stating a start before the
    earliest omitted while one without a start is kept; a Strava entry omitted
    under the default filter and listed unavailable with the Strava reason
    under a filter naming it; `gpx` listed unavailable naming `GPX`; `FIT` and
    an absent type both available; a start without an offset absent; an
    elapsed time of `true`, `-1` and `"3600"` each absent; no revision
    anywhere; each listed id equal to the service's id; a non-JSON body, a JSON
    object, an entry without an id and an entry with a numeric id each end the
    listing with a connector error naming the problem; 401 and 403 raise
    rejected and blocked failures; a persistent 429 and a persistent 503 raise
    connector errors carrying the two stated messages after exactly three
    requests (no-op sleep); 418 raises a connector error naming 418
  - Named mutations: drop the one-day overlap (the bounds pin reds); drop the
    one-day widening (the first-bound pin reds); use `≤` for `<` in the window
    condition (the 179-day pin reds); `FIRST_PULL_DAYS = 31` (the first-pull
    pin reds); drop the source filter (the outside-filter pin reds); apply the
    filter after the Strava rule (the default-filter Strava pin reds); keep
    entries starting before the earliest (the earliest pin reds); drop entries
    without a start (the kept-without-start pin reds); drop the non-FIT type
    rule (the `gpx` pin reds); treat an absent type as non-FIT (the
    absent-type pin reds); read a start without an offset as UTC (the
    naive-start pin reds); default an unstated duration to `0.0` (the duration
    pins red); keep duplicate ids (the listed-once pin reds); skip a malformed
    entry instead of raising (the malformed pins red); treat a listing 401 as a
    connector error (the rejected pin reds); raise an authentication failure
    for 429 (the rate-limit pin reds); prefix the listed id (the id-equality pin
    reds); add the key as a query parameter (the URL pin reds); honour an
    `athlete` key — keep it in the parsed settings and put it in the listing
    path (the athlete-`0` pin reds)
  - Observable: `uv run pytest tests/connectors/test_intervals.py` green; the
    fixture listing yields exactly the expected ids with the expected
    availability and reasons
  - _Requirements: 1.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 6.1_

- [ ] 3.4 Download originals: decompress within the bound, decline GPX, TCX and missing files, and map every status
  - The download of the original (never the regenerated file), the remote id
    percent-quoted into its path; bounded decompression of a gzip body and
    pass-through of any other; GPX/TCX recognition by content; the declination
    for a missing file; the remaining statuses through 3.3's mapping
  - Pins: gzip of `builder.ride_fit_bytes()` fetched equal to the input bytes;
    the same bytes uncompressed fetched unchanged; gzip of a GPX and of a TCX
    document declined naming the format; 404 and 422 (the live service's
    answer for an activity without a file, TBC-6, research.md "Live check
    findings") each declined with the no-file reason, which names no status;
    a truncated gzip and one expanding past a patched size bound raise the
    download error; the request path ends `/file`, never `/fit-file`, and an
    id containing `/` is quoted into one path segment; 401 and 403 raise the
    authentication failures; a persistent 429 and 503 raise the connector
    errors after three requests; 418 raises the download error naming 418 and
    carrying a redacted service message when the body echoes the token
  - Named mutations: return the compressed body (the equality pin reds); drop
    the size bound (the oversize pin reds); request `/fit-file` (the path pin
    reds); skip the quoting (the path-segment pin reds); drop GPX recognition
    (the GPX pin reds); drop TCX recognition (the TCX pin reds); fail a 404 instead of declining (its pin reds); fail a 422 instead of declining (its pin reds); raise a
    connector error for a download 418 (the download-error pin reds)
  - Observable: `uv run pytest tests/connectors/test_intervals.py` green; no
    operation raises "not implemented" any more
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7_

- [ ] 4. Integration, documentation and records

- [ ] 4.1 Pull through the framework into an attributed workout page
  - `tests/connectors/test_intervals_pull.py`, engine level: the registered
    connector through the pull engine with a scripted transport and a synthetic
    data root. First pull over a listing of four entries: a Garmin Connect FIT
    ride (the 2.1 fixture, gzip) delivered under `<inbox>/intervals/`; a Garmin
    Connect GPX-typed entry recorded skipped with no download request; a Garmin
    Connect entry whose downloaded body is neither FIT nor GPX/TCX recorded
    skipped as not a FIT file; an `UPLOAD` entry never requested and never
    recorded. The ledger entry of the delivered ride carries the service's id
    and the delivered bytes' hash (3.3's id-prefix mutation reds it too). A
    second pull, with the injected clock advanced, makes listing requests only
    and leaves the ledger byte-identical.
    For already held: the test seeds `<root>/fit-archive/<sha256>.fit` with a
    second builder ride that was never delivered, asserts as a precondition
    that no ledger entry is pending with that hash (so the engine's
    pending-delivery branch cannot answer first), then lists those bytes under
    a new id; the pull records it as already held and delivers nothing. Every recorded request carries
    `version.user_agent()` and none contains `Python-urllib`
  - CLI: `fitdocs pull intervals --sync --no-prompt --out <root>` with
    `[inbox]` and `[connectors.intervals]` in the settings file, the key in
    `FITDOCS_CONNECTOR_INTERVALS_API_KEY` and the transport seam patched: exit
    `0`; one workout page whose first non-blank line after the H1 is `Data
    source: Garmin edge_1040` and whose devices table names `edge_1040` and
    `hrm_pro`; the body of that page (below the provenance banner) equals the
    body `fitdocs sync <dir> --no-prompt` writes for the same bytes dropped by
    hand into a second sandbox
  - Named mutations: return filtered entries as available (the request-count
    and ledger pins red); take the revision from the injected clock (the
    second-pull pin reds); make the format sniff answer for every non-XML body
    (the not-a-FIT-file reason pin reds); drop the last byte of the fetched
    bytes (the file then fails its integrity check at the drain: the page, the
    exit-code and the hand-drop comparison pins red — an appended byte would
    not, because the decoder accepts trailing bytes); drop the head helper's
    attribution call (the page-line pin reds); in `connectors`' client, drop
    the User-Agent override (the agent pin reds); in `connectors`' pull engine,
    drop the archive-hash check (the already-held pin reds)
  - Observable: `uv run pytest tests/connectors/test_intervals_pull.py` green
    with the socket guard active
  - _Requirements: 3.4, 4.6, 4.7, 5.6, 5.8, 6.1, 6.2, 6.3, 8.1, 8.5, 8.6_
  - _Depends: 2.3, 3.4_

- [ ] 4.2 (P) Document the connector for the athlete and record it in the changelog
  - The `## intervals.icu` section of `docs/connectors.md` with the four
    subsections and every subject design.md "ConnectorsDocSection" lists;
    the heading pin in `tests/connectors/test_docs.py` gains the five headings
  - Cross-source identity (cross-spec ruling R7): if `activity-identity` is
    on `main`, state regenerate-before-first-pull instead of the
    duplicate-page caution (design.md "ConnectorsDocSection"); otherwise
    write the caution, which `activity-identity`'s task 6.1 replaces when it
    lands. The report says which was written and why
  - `CHANGELOG.md` `[Unreleased]`: the Added and Changed entries design.md
    "ChangelogEntry" lists, naming no version number, each appended under
    the existing `### Added` / `### Changed` heading in `[Unreleased]`; a
    heading is created only if absent (cross-spec ruling R8;
    `tests/test_changelog.py:516` rejects a category repeated within one
    section)
  - A sweep of `README.md`, `docs/*.md`, the connectors package's
    docstrings, the packaged skill and the changelog for any statement that
    the folder connector is the only built-in connector or that no connector
    for an online service ships, each corrected and listed in the report
  - Pins (`tests/connectors/test_intervals_docs.py`, reading the section by
    its heading): the variable it names equals the connectors naming
    function's result for instance `intervals` and field `api_key`; its
    `sources` example equals the connector's default; its first-pull day count
    equals the connector's constant; it cites `§1.1` and `V 6.30.2025`; every
    web address in it is on `intervals.icu` or the project's own
  - Named mutations: change the first-pull constant to 31 (the day-count pin
    reds); add `UPLOAD` to the default (the default pin reds); delete the
    `### Garmin attribution` heading (the heading pin reds); add a Garmin web
    address to the section (the address pin and the neutral scan red); add a
    non-canonical changelog category (`tests/test_changelog.py` reds); give
    the Added entry a second `### Added` heading of its own in
    `[Unreleased]` (`test_real_changelog_has_no_violations` reds: "repeats
    category")
  - Observable: `uv run pytest tests/connectors/test_docs.py
    tests/connectors/test_intervals_docs.py tests/test_changelog.py
    tests/test_install_docs.py tests/test_docs_guarantees.py
    tests/test_packaging.py` green
  - _Requirements: 10.1, 10.2, 10.3_
  - _Boundary: ConnectorsDocSection, ChangelogEntry_
  - _Depends: 3.1_

- [ ] 4.3 (P) Record the amendments on fit-ingest and workout-docs
  - `fit-ingest`: an Amendment block taking the next free number at landing,
    appending to Requirement 4 criteria equivalent to Req 7.1-7.5, each
    tagged with the amendment, and a `spec.json` `amendments` entry
  - `workout-docs`: an Amendment block appending to Requirement 5 criteria
    equivalent to Req 8.1-8.4, 8.6, 8.7 and to Requirement 6 one equivalent to
    8.5, with a `spec.json` `amendments` key or entry
  - No record on `connectors`: its Req 14.6 already exempts a shipped
    service connector's own module, tests and documentation section, and
    this spec's only touch there is 3.1's exemption-table entry
  - No roadmap line changes here: this branch has not merged yet, so its own
    part is not on `main`; 5.1 does the bookkeeping at the merge
  - Observable: `/kiro-spec-status fit-ingest` and `workout-docs` clean;
    each amendment names this spec; no existing criterion renumbered or
    reworded; `.kiro/specs/connectors/` unchanged by this branch
  - _Requirements: 10.4_
  - _Boundary: SpecRecords_

- [ ] 5. Validation and completion

- [ ] 5.1 Whole-suite gate and the exhaustive sweep
  - After rebasing onto `main`: `uv run pytest && uv run ruff check . && uv
    run ruff format --check . && uv run mypy` green; `DOC_VERSION` equals
    `main`'s value plus one (cross-spec ruling R1), and if a sibling landed a
    bump first, every re-pin site is re-pinned and the goldens regenerated
    under 2.3's golden rule (every golden on `main` gains the version, each
    Garmin-recorded one the line)
  - Siblings that landed while this branch was open, re-checked after the
    rebase: if `channel-merge` is now on `main` and did not wire the head
    helper's donor devices (it landed first), wire them and add the
    ride-pair and non-donating pins exactly as 2.3 states, with 2.3's two
    donor-wiring mutations observed red (ruling R2); if `activity-identity`
    is now on `main` and the intervals.icu section still carries the
    duplicate-page caution, replace it with the regenerate-before-first-pull
    statement (ruling R7); the `[Unreleased]` changelog keeps one heading per
    category (ruling R8). Each is listed in the report
  - The exhaustive sweep: every one of the 57 acceptance criteria classified
    PINNED (test and mutation), PRESERVED-ONLY (the existing test), UNPINNED
    (with the mutation run that shows it), or MAINTAINER (9.1-9.3), recorded in
    the report
  - Every changed test file passes the claim grep of `change-protocol.md`
    "Prose is not evidence", and every factual sentence in it has been
    executed, not reasoned about
  - Roadmap bookkeeping at the merge (after this task's rebase, when `main`'s
    state is known): the Phase 8 Existing Spec Updates `fit-ingest` and
    `workout-docs` lines are ticked if every other part they name is already on
    `main`, otherwise annotated "(intervals-connector part landed)"; the
    `intervals-connector` Specs line is not ticked (5.2 does, later). Then the
    branch merges to `main` under change-protocol, with 1.1 and 5.2 still
    blocked
  - Observable: the gate green; the sweep table in the report; every task but
    1.1 and 5.2 ticked; the two roadmap lines updated in the merged commit
  - _Requirements: 5.8, 8.4, 8.8, 10.1, 10.3_

- [ ] 5.2 Completion gate: reconcile the live check with the design
  - Runs after the merge, on its own branch under change-protocol, once 1.1's
    findings are in `research.md`. It reads that record and does not re-mark
    it (1.1 owns the record)
  - For each TBC item 1.1 records as contradicted: design.md is amended at
    the item's marker, and a new numbered repair task (6.1, 6.2, …) with its
    own pins and named mutations is appended to this plan; those tasks are
    implemented and pass 5.1's gate before this task is ticked. A TBC item
    recorded as confirmed needs no change
  - TBC-9 (design.md "GarminAttribution", HealthFit copies): a Garmin
    device at index 0 contradicts it, and its repair tasks re-point the
    ride-pair pin, `channel-merge`'s HealthFit fixtures and the
    `composed_run` golden. Either finding, the report states which sibling
    fixtures now record a device the finding does not match
    (`activity-identity`'s HealthFit species and `running-dynamics`'
    `run_native_dynamics` record `garmin`, `channel-merge`'s copies
    `development`) and whether each is aligned or kept as a stated
    synthetic variant
  - Then the roadmap's `intervals-connector` Specs line is ticked with the
    implementation's merge SHA, and `spec.json` records the completion
  - Observable: every TBC item recorded as contradicted has an amended design
    marker and a ticked repair task; `/kiro-spec-status intervals-connector`
    clean with every task ticked
  - _Requirements: 9.4, 9.5_
  - _Depends: 1.1, 5.1_
  - Reconciliation already applied on the impl branch 2026-10-02, before 3.4 ran: design.md download mapping (422), Cross-spec seams and ConnectorsDocSection (TBC-8 premise), 3.4's pins. No 6.x repair task was needed. 5.2 therefore runs on the impl branch after 5.1's gate rather than after the merge, and checks that every contradicted item has an amended marker and pinned behaviour
