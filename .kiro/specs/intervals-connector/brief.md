# Brief: intervals-connector

## Problem

The athlete records rides on a Garmin Edge. Garmin's own copy reaches fitdocs
today only through hand exports from Garmin Connect, because HealthFit's
Apple Health copies of Garmin rides stopped arriving on 2026-04-08. Those
copies were degraded anyway: HR-only in the "-Connect" export style, and
missing altitude, temperature, pedal dynamics and usually GPS in the "Health
Sync" style.

A direct Garmin Connect login is not viable for fitdocs:
- the developer program is business-only;
- the unofficial clients broke in 2026-03;
- the one surviving client needs Python ≥3.12 and a native TLS-impersonation
  wheel;
- the discovery probe's login drew HTTP 429.

The athlete keeps intervals.icu current with all their workouts. intervals.icu
receives Garmin rides over Garmin's official partner API and serves them
through a documented API with a personal key. It is also the service the
athlete later wants two-way integration with (posts, planned workouts,
thresholds, plans). This spec builds only the pull.

## Current State

- `connectors` (upstream) provides the protocol, the pull-activities
  capability, the ledger, the credential store, the HTTP seam, delivery and
  the pull command.
- **intervals.icu API**, per the discovery research of 2026-09-23 and the
  viability check of 2026-09-24:
  - **Auth**: HTTP Basic, username `API_KEY`, password the athlete's key
    (from Settings → Developer Settings). Athlete id `0` means self.
  - **Listing**: `GET /api/v1/athlete/{id}/activities?oldest=&newest=`
    (`oldest` required), newest first. Items carry `id`, `source`
    (`GARMIN_CONNECT`, `UPLOAD`, `OAUTH_CLIENT`, `STRAVA`, …), `external_id`,
    `device_name`, start time and sport.
  - **Strava-sourced activities** come back as empty stubs and cannot be
    downloaded.
  - **Original file**: `GET /api/v1/activity/{id}/file`, gzip-compressed.
    It may be FIT, GPX or TCX.
  - `/fit-file` is a regenerated FIT and must not be used as a source.
  - **Rate limits**: 30 requests/s over 1 s and 132 per 10 s, per the
    developer's forum post; one research summary also reports 5,000 requests
    a day for an API key.
  - **Cloudflare** returns 403 "error code: 1010" to urllib's default
    User-Agent, and passes an explicit one.
  - **API terms §1.1** (effective 2025-10-23): an application displaying
    information derived from Garmin-sourced data must attribute Garmin as
    Garmin's brand guidelines require. The guidelines ask for "Garmin
    [device model]" in detailed and historical views, and require derived or
    combined data not to imply that Garmin endorses other devices' data. No
    logo is required.
- **The file is Garmin's partner-API copy, not the device's.** Garmin strips
  undocumented messages and fields and workout-step messages before sending.
  Between 2026-03-07 and 03-18 it also stripped messages 79, 140 and 147; that
  was rolled back, but rides synced in that window stay stripped. Documented
  record fields (power, pedal dynamics, developer fields) survive. Whether a
  file is byte-identical to Connect's "export original" is unverified.
- **Garmin product names are not rendered.** fitdocs never turns a numeric
  product code into a name, so `DeviceInfo.product_name` is `None` for every
  Garmin device (`src/fitdocs/ingest/summary.py:372-385`). The SDK resolves
  the name (e.g. `edge_1040`). Attribution needs it.
- **No live check yet.** The maintainer's `.env` holds no intervals.icu key,
  so the Garmin connection and the originals' content have not been checked
  against the real account.

## Desired Outcome

- **Auth by personal key.** The connect command stores the API key (static;
  no refresh flow) in the credential store, with an environment override.
  It verifies the key with one read call.
- **Pulling activities.**
  - List by date range, paging by window; the ledger watermark sets the
    next window.
  - Skip Strava stubs, and anything without a downloadable original.
  - Honor a configurable source filter. The default is a documented choice,
    e.g. `GARMIN_CONNECT` only, so the athlete's other copies are not
    fetched twice.
  - Download the original, gunzip it, and accept it only with a FIT header.
    A GPX or TCX original is reported as skipped, never delivered.
- **Ledger.** Each intervals.icu activity id is recorded with its sha and
  outcome, so a second pull fetches nothing new. The record is keyed so a
  later push can find the remote id from the page.
- **Precedence.** The file is marked (by what the file itself carries, or by
  a documented rule `activity-identity` consumes) as a partner-API copy, so
  a device original of the same ride outranks it as base.
- **Attribution.** Resolve Garmin product names from the SDK's
  `garmin_product` value. Every page whose base or any donated channel comes
  from a Garmin device shows "Garmin <model>", or "Garmin" when the model is
  unknown, beside the data it attributes. The wording must not imply that
  Garmin endorses data from other devices on a merged page.
- **Failure reporting.** 401 means a bad key, and 403 means a
  client-signature block (the User-Agent). Both are reported by name. A 429
  on data calls backs off within the bounds `connectors` sets.
- **A live check before building on it.** The first task confirms, against
  the athlete's account, three things: intervals.icu is linked to Garmin
  directly (not via Strava); `/file` returns a FIT with the Edge's power,
  pedal dynamics and full record set; and whether its bytes equal the Garmin
  export's original for one ride. The finding is recorded in the spec.

## Approach

An `intervals` connector module against the `connectors` protocol, using
the HTTP seam with Basic auth and an explicit User-Agent. The listing and
download mapping are pure over recorded, synthesized response fixtures. The
attribution change is split in two: the product-name resolution in ingest,
and the attribution line in render.

## Scope

- **In**:
  - the connector (auth, listing, filtering, download, decompression, FIT
    check, ledger use);
  - its `fitdocs.toml` configuration;
  - the live-check task;
  - Garmin product-name resolution;
  - Garmin attribution on pages;
  - docs for setting it up.
- **Out**:
  - every other intervals.icu capability: uploads, descriptions and post
    text, planned workouts, thresholds, wellness, library and plans. They
    are the roadmap's Phase 8 follow-ons, and the reserved capability names
    in `connectors` are theirs;
  - OAuth app registration;
  - a direct Garmin connector.

## Boundary Candidates

- Transport and auth (key, UA, error mapping).
- Listing and selection (date windows, stubs, source filter, ledger).
- Retrieval (download, gunzip, FIT check, delivery).
- Attribution (product names, the page line).

## Out of Boundary

- Deduplicating the ride against its HealthFit or hand-exported copy
  (`activity-identity`).
- Composing channels (`channel-merge`).
- Anything written to intervals.icu.

## Upstream / Downstream

- **Upstream**: `connectors`; `activity-identity` (precedence consumer,
  required before real use); `fit-ingest` (product names); `workout-docs`
  (the attribution line).
- **Downstream**: the intervals.icu follow-ons (push activity and post text,
  planned workouts from the `training-blocks` plan source, thresholds into
  athlete benchmarks, plans as proposals), which extend this connector
  rather than start another.

## Existing Spec Touchpoints

- **Extends**: `fit-ingest` (Garmin product names); `workout-docs` (the
  attribution line, and the devices table showing resolved names).
- **Adjacent**: `activity-qa-flags` (a partner-API copy's stripped messages
  must not trip flags meant for bad data); `route-maps` (position is
  unaffected).

## Constraints

- **Stdlib only.** Use `gzip.decompress`: urllib does not decode the body.
- **The explicit User-Agent is mandatory.** A test proves the default agent
  is never sent.
- **The key never appears in output, logs, the ledger or exceptions.**
- **No network in tests.** Fixtures are synthesized API responses and
  synthesized FIT bytes, with no personal data. Only the live-check task
  touches the real service, and it records shapes, not values.
- **Real use waits for `activity-identity`.** Rides the athlete already holds
  as hand exports would otherwise duplicate, because Garmin Connect
  re-encodes exported bytes.
