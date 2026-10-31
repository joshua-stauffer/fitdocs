# Research & Design Decisions

## Summary
- **Feature**: `intervals-publish`
- **Discovery Scope**: Extension (an existing connector gains a publish
  operation against publish-core's target contract), with one external
  integration (three intervals.icu endpoints, two of them writes).
- **Process note (downgrade)**: research ran in-context. The batch writer
  cannot dispatch subagents, so the codebase analysis and the public-API
  reading that `kiro-spec-design` would delegate were done in this session.
- **Key Findings**:
  - The connector can reach everything resolution needs from the
    `ConnectorSession` publish-core already builds (`data_root`, `instance`,
    `settings`, `http`, `credentials`), so no framework change is needed
    beyond the transport's `PUT` method.
  - `identity.matching.pair_evidence` is not standard-library-only (it
    imports `identity.kinds`, which imports `contract` and `model`), and the
    connectors boundary pins every direct import, so the connector imports
    the rule lazily on its publish path and the boundary pin admits exactly
    that import.
  - The listing and the upload answer carry everything confirmation needs
    (`external_id`, `start_date`, `distance`, `UploadResponse.activities`), so
    an upload is confirmed by a follow-up idempotent update to the activity
    it names, never by a retry.

## Research Log

### The code the target plugs into (verified at 30ab3005)
- **Context**: what exists, and what publish-core changes before this lands.
- **Findings**:
  - `src/fitdocs/connectors/intervals.py:171`: capabilities are
    `{PULL_ACTIVITIES, PULL_WELLNESS}`; pinned by
    `tests/connectors/test_intervals.py:118-120` and
    `tests/connectors/test_intervals_wellness.py:822-825`.
  - `intervals.py:178-192`: `parse_settings` reads `sources` and ignores every
    other key (intervals-connector Req 2.4). `publish_upload` is a new key it
    reads; an unknown key stays ignored.
  - `intervals.py:557-566`: `_auth_headers` registers the bare token and the
    header value with the redactor, then returns them as `secret_headers`
    (unredirected). Reused unchanged.
  - `intervals.py:569-589`: `_service_text`/`_service_message` quote up to
    300 characters of the redacted service body. They are called from
    `verify` (`:211-219`), `_raise_for_status` (`:532`) and
    `_raise_for_wellness_status` (`:618`). None may be reachable from the
    publish operation.
  - `src/fitdocs/connectors/http.py:98`: `method: Literal["GET", "POST"]`.
    `:278-283`: `send` takes one transport call in AUTH mode, else
    `_send_data`. `:297-317`: `_send_data` retries every method on
    `TransportError` and on `RETRYABLE_STATUSES` (429, 500, 502, 503, 504) up
    to `MAX_DATA_ATTEMPTS` (3). `:337-353`: `post` exists; no connector calls
    it today (`grep -rn "\.post(" src/fitdocs` finds no caller). publish-core adds
    `HttpRequest.single_attempt` and `post(..., single_attempt=False)`; a
    marked request calls the transport once in either mode.
  - `urllib_transport` (`http.py:142-185`) passes `request.method` to
    `urllib.request.Request`, so `PUT` needs no transport change. urllib's
    redirect handler does not follow a redirect for `PUT`; it surfaces the
    3xx as a status.
  - `src/fitdocs/connectors/ledger.py:467`: `load_ledger(data_root, instance,
    *, connector_id)` reads `.fitdocs/connectors/<instance>.toml`; absent is
    an empty ledger and creates nothing; any other problem raises
    `LedgerError`. `LedgerEntry.sha256` is the archive digest of the
    delivered or already-held file (`:101-126`).
  - `src/fitdocs/connectors/protocol.py:277-300`: `ConnectorSession` carries
    `instance`, `settings`, `http`, `credentials`, `data_root`, `now`,
    `sleep`, `redactor`. `pull.py:715-724` builds it with
    `settings=instance.settings`; publish-core's `prepare_target` builds it
    the same way in DATA mode.
  - `tests/connectors/test_boundary.py:332-339`: the intervals module's
    allowed non-standard-library imports are `errors`, `http`, `protocol`,
    `secrets`. The forbidden list (`:424-440`) names `fitdocs.contract`
    directly; it scans direct imports only, function bodies included
    (`ast.walk`).
  - `tests/connectors/test_docs.py:661-670`: the neutral-scan exemption admits
    `intervals.icu` in `intervals.py`, three test modules, and the
    `docs/connectors.md#intervals.icu` section. A new test module that spells
    the host's URL needs its own entry. `:102-122`: `_EXPECTED_HEADINGS`.
  - `tests/connectors/test_intervals_docs.py:57-66`: the section's
    subsection list is pinned (four today).
  - `docs/connectors.md:66-68`: "It pulls only ... It never writes to the
    account." `:446-458`: "What leaves your machine" names `fitdocs connect`
    and `fitdocs pull` only.
  - `.kiro/steering/tech.md` "Network and Credentials": "Connector requests
    happen only during `fitdocs connect` ... and `fitdocs pull` ...". Its
    no-request list is pinned by literal in
    `tests/connectors/test_network_statements.py:664-697`,
    `tests/dashboards/test_published.py:159-166` and
    `tests/query/test_changelog_entry.py:132-141`, so the publish forms go
    into a separate sentence and the pinned list is left as it is.
  - `tests/connectors/test_network_statements.py:144-191`: the eight
    `REWRITTEN_PLACES`; relay-server adds the connectors page as a ninth and
    a `fitdocs disconnect` predicate.
  - `layout.archive_path(data_root, sha)` is `fit-archive/<sha>.fit`
    (`layout.py:363`); publish-core's `CompletedActivity.base_fit` is that
    path for the last (base) digest when it is a regular file.
- **Implications**: the connector change is local to `intervals.py` plus the
  transport's `PUT`; everything else is pins, docs and amendments.

### The match rule (`src/fitdocs/identity/matching.py`)
- **Findings**:
  - `pair_evidence(a, b)` returns `DEVICE`, `STRICT`, `SHIFTED` or `None`
    (`:139-187`). It first requires `a.sport == b.sport` and both starts
    present. `DEVICE` needs both `device` values; `SHIFTED` needs a
    `PHONE_COPY` kind on either side. With `device=None` and `kind=None` on
    both keys, only `STRICT` or `None` can come back.
  - Strict tier: start within `START_TOLERANCE_S` (1.0 s); with both
    distances, within `max(DISTANCE_TOLERANCE_M, DISTANCE_TOLERANCE_FRACTION *
    longer)` (5 m, 20 %); with either distance missing, elapsed within
    `ELAPSED_TOLERANCE_S` (10 s).
  - Imports: `fitdocs.identity.kinds` (which imports `fitdocs.contract` and
    `fitdocs.model`) and `fitdocs.model`. Not standard-library-only.
  - `TOLERANCE_SOURCES["DISTANCE_TOLERANCE_FRACTION"]`: "a start agreeing to
    the second already separates sessions (one same-sport pair within 60 s
    across 2,561 pages, a true duplicate)". That evidence is what lets the
    remote comparison drop the sport precondition (Decision below).
  - `tests/identity/test_boundary.py` pins what identity imports, "never who
    imports identity".

### intervals.icu API (OpenAPI served at `https://intervals.icu/api/v1/docs`, read 2026-10-31)
- **Findings** (paraphrased; at most short fragments quoted):
  - `PUT /api/v1/activity/{id}` (`updateActivity`): JSON body of the
    `Activity` schema; 200 returns the `Activity`. The description notes that
    "Strava activities cannot be updated".
  - `POST /api/v1/athlete/{id}/activities` (`uploadActivity`): the file goes
    as multipart form data in a field named `file`; `name`, `description`,
    `device_name`, `external_id` and `paired_event_id` are query parameters.
    Formats fit, tcx, gpx, or a zip or gz of one; multisport files are split
    into several activities; duplicates are detected by a hash of the file.
    201 when at least one new activity was created, 200 when all were
    duplicates. Response `UploadResponse`: `icu_athlete_id` (string), `id`
    (string), `activities` (array of `ActivityId`).
  - `GET /api/v1/athlete/{id}/activities` (`listActivities`): `oldest`
    (required) and `newest` (optional, inclusive) are local ISO-8601 dates or
    date-times; `fields` restricts the returned properties and also drops
    null values; Strava activities come back as stub objects.
  - `Activity` has `id`, `name`, `description`, `start_date`,
    `start_date_local`, `distance` (float), `elapsed_time` (int32),
    `external_id` (string), `source` (string enum) and `type`. The stub
    schema (`Hidden`) has `id`, `icu_athlete_id`, `start_date_local`,
    `source` and `_note`.
  - Live findings already recorded by intervals-connector
    (`.kiro/specs/intervals-connector/research.md`, 2026-10-02): `start_date`
    is UTC with a `Z` designator (TBC-2); `id` is `i` followed by digits
    (TBC-4); an explicit fitdocs User-Agent passes Cloudflare while urllib's
    default draws 403/1010; `source` values include `GARMIN_CONNECT`,
    `OAUTH_CLIENT`, `MANUAL`.
  - Limits (forum, relayed by the brief): 5,000 calls/day and 2,500 per
    15 minutes per key, 10 per second per IP. The design depends on none of
    the figures.
  - Terms (forum t/114087, effective 2025-10-23): "any lawful purpose,
    including commercial use"; Garmin attribution where Garmin-sourced data
    is shown. Writing a post to the athlete's own activity is within them.
- **Implications**: listing windows are local dates, so the window must
  cover every offset; the upload's answer names the created activity, which
  makes a confirming update possible; Strava stubs carry only a local start,
  so their detection compares wall-clock times.

### Assumptions to be confirmed (TBC-P*, the optional live check)
- **TBC-P1**: `PUT /activity/{id}` with a body of only `name` and
  `description` changes those two fields and no other, and answers 200; an
  unknown id answers 404; another athlete's activity answers 403 (then an
  instance whose key belongs to a different account maps to
  `permission_denied`, which stops the target; if it answers 404 instead,
  the flow treats it as absent and the mapping note is amended).
- **TBC-P2**: the listing with `fields=` returns `distance` in metres,
  `external_id` when set, and `start_date_local`; a Strava stub carries
  `id`, `source` and `start_date_local`.
- **TBC-P3**: an upload of a single-session FIT answers 201 with
  `activities` holding one object whose `id` is the new activity; a
  re-upload of the same bytes answers 200 with the existing activity in
  `activities`.
- **TBC-P4**: the `external_id` query parameter is stored and returned by
  the listing.
- **TBC-P5**: `https://intervals.icu/activities/<id>` opens the activity.
- Each has a bounded blast radius: one parse or mapping function and its
  tests.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Extend `intervals.py` | `IntervalsConnector.publish` plus private `_publish_*` helpers in the existing module | One module names the service (the neutral scan's exemption stays one module); the brief's "extend this connector" rule; reuses `_auth_headers`, `API_BASE`, `SELF_ATHLETE` | The module grows by roughly 350 lines | Selected |
| B. Sibling `connectors/intervals_publish.py` | Publish logic in its own module, the class method delegating | Keeps the pull module's boundary pin unchanged | Circular import (the class needs the module, the module needs the constants) or duplicated constants; a second module naming the host needs its own exemption | Rejected |
| C. Resolution in `fitdocs.publish` | The engine resolves the activity and hands the target an id | — | publish-core forbids `fitdocs.publish` importing `identity`, and makes resolution each target's own step (R8) | Rejected |

## Design Decisions

### Decision: resolution order
- **Context**: the controller settled "first the pull ledger, then a listing
  window with `pair_evidence`". publish-core hands every request the link it
  recorded from the last landed post.
- **Alternatives Considered**:
  1. Pull record, then listing (the settled order alone).
  2. Recorded link, then pull record, then listing.
- **Selected Approach**: 2. The recorded link is an update path, not a new
  resolution rule: it names the activity an earlier strict resolution (or an
  upload carrying the publication id) already chose. Resolution proper, for
  a first post or when that activity is gone, is the settled order.
- **Rationale**: without it, a page posted through the listing becomes
  ambiguous the day a second copy of the same session reaches intervals.icu
  (a phone-app upload beside a Garmin import), and its update would stop
  with `ambiguous` although fitdocs knows where its post lives.
- **Trade-offs**: one more parse rule; an update whose pull record now names
  a different copy of the same session keeps updating the first.
- **Follow-up**: flagged to the controller as an addition within the
  settled order.

### Decision: the remote match does not compare sports
- **Context**: `pair_evidence` requires equal `sport` strings. fitdocs
  records its own labels (`Ride`, `Run`, `Workout`, ...); intervals.icu's
  `type` is its own vocabulary (`VirtualRide`, `TrailRun`, `WeightTraining`,
  ...), not documented as a mapping from FIT sports.
- **Alternatives Considered**:
  1. A mapping table from intervals.icu types to fitdocs sports.
  2. The page's sport on both keys, so the sport precondition holds by
     construction.
- **Selected Approach**: 2, with `device=None` and `kind=None` on both keys
  and only `Evidence.STRICT` accepted.
- **Rationale**: a table is a guess, and its failure mode is the worst one:
  a type it maps differently makes the true activity a non-match, and with
  uploads on, a duplicate upload. activity-identity's own evidence is that a
  start agreeing to the second already separates sessions; the distance or
  elapsed comparison still applies.
- **Trade-offs**: two activities of different sports starting in the same
  second would both match, which is reported as `ambiguous`, never a pick.

### Decision: confirm an upload with an update
- **Context**: the upload is not idempotent and is sent once. Its query
  string can carry `name` and `description`, but a description is
  multi-line and unbounded and would make the address long.
- **Selected Approach**: the upload carries the file and `external_id` (the
  publication id) only. A 201 or 200 answer that names exactly one activity
  is followed by one update setting the name and description, which both
  confirms the activity exists and applies the post through the same code
  path every other branch uses. Uploaded when created (201), posted when
  already held (200).
- **Rationale**: no user text in any address; one way of setting the post;
  the next run finds a created activity by its external identifier if the
  confirmation is lost.
- **Trade-offs**: an upload whose confirming update fails leaves the
  activity with intervals.icu's default name until the next run;
  `unconfirmed` says so.

### Decision: retry the update, never the upload
- **Context**: the brief leaves to the design whether an idempotent `PUT`
  may retry.
- **Selected Approach**: the update is an unmarked DATA-mode request, so the
  transport's bounded retries apply; the upload is marked single-attempt
  (publish-core's `HttpRequest.single_attempt`).
- **Rationale**: setting the same two fields twice has the same effect as
  once.

### Decision: answers mapped by request kind
- **Context**: R8 asks that the mapping not assume every write targets an
  activity.
- **Selected Approach**: one table, keyed by answer class and by request
  kind (`read`, `update`, `create`); the activity flow alone decides what an
  update's 404 means for finding the activity.
- **Rationale**: a later events write is an `update` or a `create` and maps
  identically.

### Decision: an unreadable pull record bars the upload (controller ruling R11)
- **Context**: the first draft skipped an unreadable pull record silently,
  because no target code said so truthfully. The Step 3.5 review showed the
  hole: connectors Req 7.6 never treats an unreadable ledger as absent, and a
  page whose base is a phone copy shifted by whole hours (merged locally at
  the shifted tier) is reachable on intervals.icu only through the pull
  record's second tier; the strict listing then misses it, and with uploads
  on the page would be uploaded as a duplicate.
- **Selected Approach**: the controller folded a new code,
  `local_record_unreadable`, into publish-core (appended after `ready`; a
  target code, a failure, not landed, not stopping). `LedgerError` is noted;
  the read-only steps (recorded link, listing) still run and may still post;
  when they do not resolve the activity, the answer is
  `local_record_unreadable` whatever the upload setting (a refinement of
  R11 after the re-review: `not_found` would assert that no matching
  activity exists, which the unread record leaves unverified).
- **Rationale**: an upload cannot be undone, so it never runs on unreadable
  identity state; an update to an activity found by other evidence is still
  safe.
- **Trade-offs**: none beyond one code; `fitdocs pull` still names the file
  to fix.

### Decision: identity import on the publish path only
- **Context**: `identity.matching` is not standard-library-only; the
  connectors package's import closure is pinned module by module.
- **Selected Approach**: a function-level import of
  `fitdocs.identity.matching` inside the listing-match helper, admitted in the
  intervals entry of the boundary pin; a module-level import of
  `fitdocs.connectors.ledger`. Publish codes come through
  `fitdocs.connectors.protocol`'s re-export of `PublishCode` and
  `TARGET_CODES` (controller ruling R11), never from `fitdocs.publish`
  directly, which publish-core reserves to `protocol` and `registry`.
- **Rationale**: importing `fitdocs.connectors` (which the CLI does at load)
  loads no identity module; it already loads `contract`, `docmerge`, `model`
  and `yaml` through `folder` and `inbox`, so the claim is about identity
  only. The rule is reused, never restated.
- **Follow-up**: strava-publish extracts a standard-library-only core of
  the rule (`identity.strict`) for the relay. This connector keeps importing
  `identity.matching` in either landing order; switching it to
  `identity.strict` is relay-intervals' amendment (controller ruling R13,
  Revalidation Triggers).

## Synthesis
- **Generalization**: the three ways of finding an activity share one
  update step and one "absent" signal; the update is one helper used by
  every branch, including upload confirmation. The answer mapping is one
  table for every request kind.
- **Build vs. adopt**: the match rule, the transport, the credential
  helper, the pull ledger reader and the request and result types are all
  adopted unchanged. Multipart encoding is built: the standard library has
  no multipart encoder outside `email`, whose MIME output is not an HTTP
  form body; the body is one fixed part.
- **Simplification**: no new module, no new framework type, no client-side
  pacing, no polling (the upload answer is synchronous), no settings beyond
  one boolean.

## Risks & Mitigations
- A live answer differs from the description (TBC-P1..P5) — each is behind
  one helper and its tests; the optional live check confirms them.
- A Strava stub whose local start differs from the page's recorded local
  start (a time zone set differently on the two platforms) is not detected,
  and with uploads on the file is uploaded beside the stub — documented in
  the connectors page; uploads are off by default.
- The listing misses a true copy (the strict rule says it is another
  session) — the same false negative activity-identity accepts locally;
  uploads are off by default, and intervals.icu's file-hash de-duplication
  catches a byte-identical copy.
- A transport failure after the upload reached the service — `unconfirmed`;
  the next run finds the activity by its external identifier before
  uploading again.

## References
- intervals.icu OpenAPI description, `https://intervals.icu/api/v1/docs`
  (read 2026-10-31).
- "Intervals.icu API Terms and Conditions", forum topic 114087 (effective
  2025-10-23), as relayed by the brief.
- `.kiro/specs/publish-core/design.md` (target contract, codes,
  single-attempt mode), `.kiro/specs/intervals-connector/design.md` and
  `research.md` (listing shapes, live findings), `.kiro/specs/activity-identity/`
  (the strict rule, Amendment 1).
