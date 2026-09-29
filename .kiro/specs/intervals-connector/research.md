# Research & Design Decisions: intervals-connector

## Summary
- **Feature**: `intervals-connector`
- **Discovery Scope**: Complex Integration (an external service behind a
  published protocol) for the connector; Extension (light discovery) for the
  fit-ingest and workout-docs updates.
- **Research mode**: in-context. The spec writer ran as a subagent without an
  Agent tool, so the research subagents the design skill suggests were not
  dispatched; every source below was read directly. The only network access
  was unauthenticated reads of public documentation (no key exists and none
  was used; no Garmin login; no Stryd endpoint).
- **Key Findings**:
  - intervals.icu publishes an OpenAPI 3.0.1 description, version `v1.0.0`,
    unauthenticated at `https://intervals.icu/api/v1/docs` (read
    2026-09-29, 244,836 bytes). It confirms HTTP Basic with username
    `API_KEY`, `listActivities` (`oldest` required, "desc date order", "an
    empty stub object is returned for Strava activities"), the original-file
    download, and a 14-value `source` vocabulary that differs from a
    third-party copy of the same description, so the source filter must be an
    open vocabulary.
  - The Garmin FIT SDK (`garmin-fit-sdk` 21.208.0, locked) already resolves
    Garmin product codes: its decoder adds a `garmin_product` key holding the
    profile name (`edge_1040`) for a known code and the raw integer for an
    unknown one. fitdocs discards it today. Resolution is one branch in
    `_product_name`, with no table of fitdocs's own.
  - Garmin's API Brand Guidelines (V 6.30.2025) require "Garmin [device
    model]" directly beneath or adjacent to the title of a data view, "Garmin"
    alone when the model is unknown, and, for combined data, Garmin listed as a
    distinct or contributing source without implying endorsement of other
    devices' data. A logo is optional.

## Research Log

### intervals.icu API surface
- **Context**: the connector's every request and the listing's field names.
- **Sources Consulted**:
  - OpenAPI description at `https://intervals.icu/api/v1/docs` (the Swagger
    UI's own initializer names `/api/v1/docs/swagger-config` as its config;
    the description itself is served at `/api/v1/docs`).
  - Forum "API access to Intervals.icu" (`forum.intervals.icu/t/609`).
  - Forum "Intervals.icu API Integration Cookbook" (`/t/80090`, posted
    2024-11-20).
  - A third-party copy of the description in a public GitHub repository
    (`eddmann/intervals-icu-mcp`, `openapi-spec.json`), used only to observe
    that the vocabulary moves.
- **Findings**:
  - `components.securitySchemes.APIKey`: `type: http`, `scheme: basic`,
    "Username is API_KEY, Password is your API key found in /settings".
    `AccessToken` is bearer (OAuth), out of scope.
  - Athlete id `0` "will use the athlete for the API key or bearer token used
    to make the call" (API access thread).
  - `GET /api/v1/athlete/{id}/activities` (`listActivities`): "List
    activities for a date range in desc date order"; description "An empty
    stub object is returned for Strava activities". Parameters: `oldest`
    (required; "Local ISO-8601 date or date and time e.g. 2019-07-22T16:18:49
    or 2019-07-22"), `newest` ("… defaults to now"), `route_id`, `limit`
    ("Return at most this many activities"), `fields` ("Comma separated list
    of field names to include in the returned objects (default is all), also
    excludes null values"). 200: array of `Activity`. No cursor or offset.
  - `Activity` has 184 properties, none required. Those the design reads:
    `id` (string), `source` (string enum), `start_date` (string),
    `start_date_local` (string), `type` (string), `elapsed_time` (int32),
    `file_type` (string), `external_id` (string), `device_name` (string).
  - `source` enum in the served description: `STRAVA`, `UPLOAD`, `MANUAL`,
    `GARMIN_CONNECT`, `OAUTH_CLIENT`, `DROPBOX`, `POLAR`, `SUUNTO`, `COROS`,
    `WAHOO`, `ZWIFT`, `ZEPP`, `CONCEPT2`, `HUAWEI` (14). The third-party copy
    lists 7 (`STRAVA`, `ICU`, `GARMIN_CONNECT`, `WAHOO`, `SUUNTO`, `COROS`,
    `POLAR`), including `ICU`, which the served one does not.
  - `Hidden` schema (the Strava stub, one of `getActivity`'s response
    shapes): `id`, `icu_athlete_id`, `start_date_local`, `source`, `_note` —
    no `start_date`, no `file_type`.
  - `GET /api/v1/activity/{id}/file` (`downloadActivityFile`): "Download
    original activity file, Strava activities not supported"; 200 with no
    declared content type. The cookbook: "The system delivers these files
    with gzip compression applied. Supported formats include FIT, GPX, and
    TCX files."
  - `GET /api/v1/activity/{id}/fit-file`: "Download Intervals.icu generated
    activity fit file" (with `power`/`hr` switches) — a regenerated file,
    never a source.
  - Rate limits: the API access thread states "5000 requests per day and 2500
    requests per rolling 15 minute window" for API-key callers, plus "10 calls
    per second per IP address". The brief relays a different pair (30 per
    1 s, 132 per 10 s) from a developer post. The figures disagree and may
    change; the design depends on neither.
  - Cloudflare: the API access thread warns that `Python-urllib` "may be
    challenged or blocked" and suggests a browser-like agent. The maintainer's
    viability check (2026-09-24) found an explicit, honest User-Agent passes
    and urllib's default draws 403 "error code: 1010". fitdocs sends its own
    agent and never impersonates a browser.
- **Implications**: listing is by date windows the connector computes;
  `oldest`/`newest` are athlete-local with no zone, so the connector widens
  the first window by a day and filters by the zoned `start_date`; the source
  filter is an open, pattern-checked vocabulary; the regenerated file is
  never requested.

### Terms and attribution
- **Sources Consulted**: "Intervals.icu API Terms and Conditions"
  (`forum.intervals.icu/t/114087`, effective 2025-10-23); forum "Garmin
  attribution requirements" (`/t/108507`, 2025-07-02 and 2025-07-09 posts);
  Garmin "API Brand Guidelines" PDF (`developer.garmin.com/downloads/brand/
  Garmin-Developer-API-Brand-Guidelines.pdf`, footer "V 6.30.2025").
- **Findings**:
  - intervals.icu terms §1.1, verbatim: "Activity data obtained through the
    Intervals.icu API may include data that requires attribution to Garmin.
    Therefore, if your application displays information derived from
    Garmin-sourced data, you must display attribution to Garmin in the form
    and manner required by Garmin's brand guidelines."
  - Garmin, "Title-level or primary displays": "must include a 'Garmin
    [device model]' attribution … If the device model is not provided or
    unknown via the API, list Garmin as the data source." "Position the
    Garmin attribution directly beneath or adjacent to the primary title or
    heading of the data view … above the fold … Never bury the Garmin
    attribution in tooltips, footnotes or expandable containers." "The
    attribution can include the Garmin tag logo followed by the device model
    or simply be listed in appropriately sized text."
  - "Secondary screens": detailed and historical views need the attribution;
    "For multi-entry displays, you can apply the attribution globally — such
    as in a header — or per entry."
  - "Combined or derived data": "The attribution must list Garmin as a
    distinct or contributing data source (depending on what is true) and must
    not imply Garmin endorsement of data from other devices." Acceptable:
    "Insights derived in part from Garmin device-sourced data."; "Model
    incorporates Garmin [device model] data."
  - "Visual and social media": exported visual assets (social images,
    infographics, maps, charts) must show the attribution "in every image".
  - The intervals.icu developer (2025-07-09) called deciding whether Garmin
    data is included "tricky" and attributes cautiously.
- **Implications**: the page carries a plain-text line beneath its H1; the
  model is the recording device's; a composed page uses contributing-source
  wording. Two readings stay open for the maintainer (design.md Open
  Questions): chart SVGs as "visual assets", and the aggregate history and
  block pages as "derived data" views.

### Garmin product names in the FIT SDK
- **Context**: `DeviceInfo.product_name` is `None` for every Garmin device
  (`src/fitdocs/ingest/summary.py:372-385` returns a name only when
  `product_name` or `product` is a `str`).
- **Sources Consulted**: `garmin_fit_sdk` 21.208.0 in the worktree
  (`decoder.py` sub-field expansion at `:532-564`, type conversion at
  `:583-600`, `profile.py`); synthesized messages encoded and decoded with
  `tests/fixtures/builder.py`'s `encode`/`decode_messages`.
- **Findings**:
  - `product` is a dynamic field with two sub-fields: `garmin_product` (type
    `garmin_product`, 479 entries) when the message's `manufacturer` is
    `garmin` (1), `dynastream` (15), `dynastream_oem` (13) or `tacx` (89);
    `favero_product` for `favero_electronics` (263). The same map exists on
    `file_id`, `device_info`, `slave_device` and `training_file`.
  - With the SDK defaults fitdocs keeps (`expand_sub_fields`,
    `convert_types_to_strings`; `ingest/decode.py:91-95` sets only
    `apply_scale_and_offset`, `expand_components`,
    `convert_datetimes_to_dates`), a decoded `device_info` gains
    `garmin_product: 'edge_1040'` for code 3843 and keeps `product: 3843`.
  - Measured (synthesized): garmin 3843 → `edge_1040`; dynastream 3300 →
    `hrm_pro`; garmin 65000 → `garmin_product: 65000` (an `int`: unknown to
    the profile); `wahoo_fitness` 3843 → no `garmin_product` key; every
    `parse_fit` today yields `product_name=None` for all five.
  - Every synthesized fixture's device (`tests/fixtures/builder.py:157-168`)
    is `manufacturer: garmin`, `product: 1` (`hrm1`) with a `product_name`
    string, so a recorded name keeps winning and no model golden
    (`tests/golden/*.json`) moves.
- **Implications**: resolution reads the decoded `garmin_product` key when it
  is a `str`; the recorded `product_name` keeps precedence; nothing imports
  the SDK outside `ingest/decode.py`. Resolution is a function of the file's
  bytes, so it applies to every Garmin file whatever its route.

### Codebase integration points
- **Findings**:
  - The protocol, transport, credential store, ledger, delivery and commands
    are `connectors`' (design.md there, "Cross-spec seams" `:1822-1840`),
    unimplemented on this branch; this design consumes their published
    shapes.
  - `connectors` task 7 pins a service-neutral scan over "the connectors
    package, its tests and the page (every URL is the project's own or a
    reserved example host)" (`.kiro/specs/connectors/tasks.md:696-700`),
    and Req 14.6 says the framework, its tests and documentation "shall name
    no online service's endpoint". This connector lives in that package and
    must name `intervals.icu`: a scoped exemption and an amendment record
    are required.
  - Render: every view emits the H1 then the bare `notes` region
    (`src/fitdocs/render/views.py:156-157, 191-192, 225-226`); docmerge
    recognizes a region marker only as a whole line at column zero
    (`src/fitdocs/docmerge.py:63-66`, `re.MULTILINE`), so a single-line
    attribution between them cannot create or break a region. The view tests
    pin order by index, not adjacency (`tests/render/test_views.py:113`).
  - The devices table's name cell is `product_name or manufacturer or
    "Unknown device"` (`src/fitdocs/render/sections.py:533-537`).
  - `parse_fit` reads only record, session, activity, lap, set,
    exercise_title, device_info, sport and field_description messages
    (`src/fitdocs/ingest/__init__.py:58-66`); the quality flags read samples,
    metrics and channel outcomes (`src/fitdocs/load/qa/flags.py:207-215`).
    Messages Garmin strips from a partner-API copy reach neither.
  - `DOC_VERSION` is `5` (`src/fitdocs/contract.py:174`); literal pins at
    `tests/test_cli_check.py:196,198`, `tests/render/test_frontmatter.py:44,
    101`, `tests/metrics/test_sources.py:2270`
    (`CONSTANT_REGISTRY_ASOF_DOC_VERSION`, which tracks the current version
    while the constant registry is clean) and the nine render goldens under
    `tests/render/golden_docs/`. No doc page states the number.
  - `activity-identity` exposes the raw `FileIdentity.product`, never reads
    `garmin_product` and never reads a product name; running-dynamics edits
    only the developer-field functions of `ingest/summary.py` (`:129-301`).

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Attribute by the recording device (selected) | The device the file names as its creator (`device_index` 0) decides; its manufacturer `garmin` means Garmin data | Uses today's model only; a function of the bytes; HealthFit and Stryd files (creator `development`, `stryd`) are not attributed | A Garmin-written file with no `device_info` at all is not attributed | No dependency on `activity-identity` landing first |
| Attribute by `file_id` manufacturer | `FileIdentity.manufacturer == "garmin"` | The canonical "who wrote the file" | Needs `activity-identity`'s `FileIdentity`, and a second resolution of `file_id`'s product | Rejected: couples two wave specs' merge order |
| Attribute by delivery route | Mark pages whose file came through intervals.icu | Mirrors the terms' literal scope | Arrival order changes the page; a hand-exported Garmin original is unattributed; the ledger would reach render | Rejected: breaks "arrival order never changes the page" |
| Attribute by listing `device_name` | intervals.icu's forum advice | Available in the listing | Needs the connector to write page metadata; unavailable for hand drops | Rejected: connectors never know pages |

## Design Decisions

### Decision: No revision token
- **Context**: `RemoteActivity.revision` lets a changed remote file be fetched
  again.
- **Selected Approach**: `None`. An intervals.icu activity's original file is
  what was uploaded; an edit changes intervals.icu's analysis (and
  `/fit-file`), not the original, and a new upload is a new activity id.
- **Trade-offs**: if the original ever did change, the new bytes would not be
  fetched; `icu_sync_date` or `analyzed` as a revision would re-download
  (and re-hash to already-held) after every re-analysis.

### Decision: Date windows, overlapped and deduplicated
- **Selected Approach**: consecutive windows of `WINDOW_DAYS = 90`, each
  request's `newest` one day past the next window's `oldest`; the last window
  omits `newest` (the service's "now"). Entries are deduplicated by `id`
  across windows (the framework fails a repeated entry). The first `oldest`
  is the UTC date of the earliest start less one day, and entries whose
  stated `start_date` is earlier than the requested earliest start are
  dropped.
- **Rationale**: the API has no cursor; `oldest`/`newest` are athlete-local
  with unknown inclusivity; the overlap makes coverage independent of both.

### Decision: A fixed 30-day first pull
- **Selected Approach**: with no earliest start (no watermark, no `--since`),
  list the last `FIRST_PULL_DAYS = 30` days. No settings key; backfill is
  `fitdocs pull <name> --since DATE`.
- **Rationale**: a full-history first pull could exhaust the daily request
  budget and, before `activity-identity` merges, duplicate every held ride.
  Matches `connectors`' `DEFAULT_LOOKBACK_DAYS = 30`.

### Decision: Filtered activities are omitted, not recorded
- **Selected Approach**: an activity whose source is outside the filter is
  left out of the listing entirely.
- **Rationale**: a `skipped` ledger record is final for its id, so recording
  filtered activities would make a later widening of the filter silently
  ineffective.

### Decision: Only a stated non-FIT format is skipped at listing time
- **Selected Approach**: `file_type` present and not `fit` (any case) →
  unavailable, reason naming the format; `file_type` absent → fetched, and the
  bytes decide (GPX/TCX declined by content, anything else left to the
  framework's FIT-header check).
- **Rationale**: absence must not become a final skip; if the live check
  finds `file_type` missing from real listings, nothing is lost.

### Decision: Bounded decompression instead of `gzip.decompress`
- **Selected Approach**: a body starting with the gzip magic (`1f 8b`) is read
  through `gzip.GzipFile(...).read(MAX_FILE_BYTES + 1)`; more than
  `MAX_FILE_BYTES` (the transport's 64 MiB response bound) is an error; a
  body without the magic is used as received.
- **Rationale**: `gzip.decompress` (the brief's wording) has no output bound,
  so a small hostile body could expand without limit; `GzipFile` is the same
  stdlib codec with a bounded read and handles multi-member streams.

### Decision: Data-call 429 and 5xx end the instance with a connector error
- **Selected Approach**: after the transport's bounded retries, a 429 or 5xx
  on the listing or a download raises `ConnectorError` with a message naming
  the condition and that the next pull resumes; 401/403 raise the
  `AuthFailure` `auth_failure_from` builds.
- **Rationale**: the framework's rate-limited next step speaks of a sign-in;
  a data-call rate limit is a different situation, and further downloads in
  the same run would meet the same limit.

### Decision: Verify with a one-entry listing
- **Selected Approach**: `verify` makes one `GET
  /api/v1/athlete/0/activities?oldest=<yesterday>&limit=1&fields=id`.
- **Rationale**: it exercises exactly the read permission a pull needs and
  returns almost nothing; `GET /api/v1/athlete/0` returns the athlete's
  profile, which fitdocs has no use for.

### Decision: Model names verbatim from the profile
- **Selected Approach**: `Garmin edge_1040`, not a prettified "Garmin Edge
  1040".
- **Rationale**: a heuristic prettifier gets many models wrong (`fr965` is a
  Forerunner 965, `hrm_pro_plus` an HRM-Pro Plus); the profile identifier is
  exact and deterministic. A display-name table is an open question, not
  this spec.

### Decision: The attribution is generated body content
- **Selected Approach**: one plain-text line between the H1 and the `notes`
  region, from a pure function in a new `render/attribution.py`; no
  frontmatter key, no `CONTRACT_VERSION` or `MANAGED_KEYS` change; one
  `DOC_VERSION` advance so existing pages are regenerated into compliance.

### Synthesis outcomes
- **Generalization**: the attribution function takes the base and the
  donating files, so the one wording rule covers today's single-file pages
  and `channel-merge`'s composed pages; the interface is general, the only
  caller today passes no donors.
- **Build vs adopt**: product names are adopted from the SDK's profile;
  decompression, JSON, Basic credentials and URL encoding from the stdlib;
  transport, retries, credentials, ledger and delivery from `connectors`.
  Built: the listing and download mapping, the source filter, the wording.
- **Simplification**: no settings key beyond the filter (no athlete id, no
  base URL, no first-pull days); no client-side pacing; no revision; no
  dependency on `FileIdentity`; no new frontmatter key.

## To be confirmed by the live check (task 1)
Assumptions the design takes from the public description and marks
**(TBC-n)** where it relies on them:
- **TBC-1**: an Edge ride intervals.icu received from Garmin is listed with
  `source` `GARMIN_CONNECT` (not `STRAVA`, not `OAUTH_CLIENT`).
- **TBC-2**: `start_date` is an ISO-8601 instant with a zone designator;
  `start_date_local` has none.
- **TBC-3**: `file_type` appears on listed activities with lower-case format
  names (`fit`, `gpx`, `tcx`), and not on Strava stubs.
- **TBC-4**: `fields=` restricts objects as documented; Strava stubs still
  carry `id` and `source`.
- **TBC-5**: `/file` answers 200 with a gzip body holding the original bytes,
  with or without a redirect (record which).
- **TBC-6**: an activity with no file (e.g. a manual entry) answers `/file`
  with 404.
- **TBC-7**: the one-entry listing answers 200 for a valid key and 401 for an
  invalid one, and an explicit fitdocs User-Agent is not blocked.
- **TBC-8**: the intervals.icu copy carries fewer undocumented messages than
  the device's own original of the same ride (`activity-identity`'s
  within-kind rank), unless the two are byte-identical.

## Live check findings
_Not yet run (2026-09-29): the maintainer's `.env` holds no intervals.icu
key. Task 1 records its findings here as shapes and vocabulary only._

## Risks & Mitigations
- The published description drifts from the service — every relied-on shape
  is TBC-marked, the live check gates completion, and a malformed listing
  ends the instance loudly (Req 3.8) rather than being guessed at.
- A daily or windowed rate limit during a large `--since` backfill — the
  instance stops on a persistent 429 and the next pull resumes; the docs
  recommend backfilling in slices.
- Duplicate pages before `activity-identity` merges — documented; no
  connector is pointed at a real data root before identity lands (roadmap
  constraint).
- A partner-API copy outranking the device original — decided by
  `activity-identity`'s rank; TBC-8 measures the premise.
- Device-recorded free text in the attribution — collapsed to one line, so it
  cannot form a region marker or a heading line.

## References
- intervals.icu OpenAPI description, `https://intervals.icu/api/v1/docs`
  (v1.0.0, read 2026-09-29).
- "API access to Intervals.icu", `https://forum.intervals.icu/t/api-access-to-intervals-icu/609`.
- "Intervals.icu API Integration Cookbook", `https://forum.intervals.icu/t/intervals-icu-api-integration-cookbook/80090`.
- "Intervals.icu API Terms and Conditions", `https://forum.intervals.icu/t/intervals-icu-api-terms-and-conditions/114087` (effective 2025-10-23).
- "Garmin attribution requirements", `https://forum.intervals.icu/t/garmin-attribution-requirements/108507`.
- Garmin API Brand Guidelines, V 6.30.2025, `https://developer.garmin.com/downloads/brand/Garmin-Developer-API-Brand-Guidelines.pdf`.
- `garmin-fit-sdk` 21.208.0 (`uv.lock`), `garmin_fit_sdk/decoder.py`, `garmin_fit_sdk/profile.py`.
- `.kiro/specs/connectors/design.md` (protocol, transport, cross-spec seams);
  `.kiro/specs/activity-identity/design.md` § Cross-spec seams;
  `.kiro/specs/running-dynamics/design.md` § Cross-spec seams.
