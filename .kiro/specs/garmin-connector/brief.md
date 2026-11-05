# Brief: garmin-connector

## Problem

Athletes who record on Garmin devices have no automated route into fitdocs
that will last.
- **intervals.icu:** Phase 8's route is ending. Its developer said on
  2026-10-24: "You need to get your own connection to Garmin to get activity
  data" (<https://forum.intervals.icu/t/api-access-to-intervals-icu/609>, #883).
  It also needs an intervals.icu account, and it serves a partner copy of the
  file rather than the original.
- **Garmin's data export:** complete, but a manual step for each batch.
- **The hosted route:** Phase 14's extension planned to hold each user's
  activities and health data on a relay, on Garmin's push-only tier, with no
  history from before connecting. The maintainer shelved it on 2026-11-05 in
  favor of this connector.

Garmin's Connect Personal API (2026-10-21) lets each person create their own
key and read their own data. A fitdocs user already runs the CLI on their own
machine, so nothing needs to sit in between.

## Current State

- **Connectors:** `folder`, `intervals`, `relay`, `strava`. `intervals` is the
  closest model: a personal key, pull-activities and pull-wellness, on
  `fitdocs.connectors.http`.
- **Already working for Garmin files:** activity identity, channel merge,
  product names and the "Garmin <model>" attribution all read the file's bytes.
  A Garmin original joins any copy of the same activity with no new logic.
- **Wellness:** the `garmin-export` format parses Garmin's export JSON, and the
  intervals.icu format shows how a connector packages wellness for the inbox.
- **Nothing in fitdocs talks to Garmin today.**

### Public sources (the only sources)

| Source | What it gives |
|---|---|
| [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/) | Who it is for, the token exchange, key expiry (30, 90, 180 or 365 days; shown once), no refresh tokens, token life of 24 hours or until the key expires |
| [Personal API Swagger page](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/) | The full OpenAPI 3.0.1 spec, 26 paths, served to anyone with no login. Sleep summaries take up to 31 days, daily summaries up to 1 year; the listing has `sortOrder`, `excludeChildren` (default true) and date filters on local start time |
| [`garmin/connect-personal-api-python`](https://github.com/garmin/connect-personal-api-python) | Garmin's own Apache-2.0 client: "other projects can reuse its parts independently". Endpoint table, request headers, and "the original activity file as ZIP bytes" |
| Garmin Connect Personal API Supplemental Terms | Shown when a key is created. The text is in Garmin's public strings file (`connect.garmin.com/web-translations/partner_portal/partner_portal.properties`) |

### Measured at discovery (2026-11-05)

The maintainer's own key, read-only, shapes only: about 40 requests at 2.5 s
spacing, with no 401, 403 or 429 and no limit headers.

- **Token:** a bare JWT as the response text, not JSON, with a 24.0 h life.
- **History:** complete. 1,070 activities back to 2014, against 1,067 in the
  maintainer's export two months earlier. Pages of 200 work; `limit=1000`
  returned 500 with an empty body.
- **Files:** a ZIP with one member. **4 of 4 comparable `.fit` files were
  byte-identical to the device originals in Garmin's data export**, undocumented
  messages included, across three device generations.
- **Non-FIT uploads:** a 2014 upload came back as a ZIP holding a `.gpx`. The
  account's 169 `other` activities match the known GPX-only count.
- **Wellness:**
  - daily summaries: 7, 32 and 366 days all work, and 2019 still answers;
  - sleep summaries: 32 days works although the spec says 31, and 366 days
    returned 400 with `{}`;
  - HRV: 204 with no body on this account, which has no HRV device;
  - weight and single-day SpO2 answer.

### Still unknown (first task, a live check)

The maintainer authorized the discovery check only, so this one needs their go.
- Whether Garmin accepts fitdocs's composed User-Agent. The check used another.
- What the token call answers for a deleted or expired key.
- The stress and body-battery shapes, and the weight unit (the export is in
  grams).
- A real HRV body. The spec documents `lastNightAvg`, `weeklyAvg` and more, but
  this account has none.
- Whether `vO2MaxValue` on a listing row ever appears. It is in the spec's
  schema and on no row of this account.
- Sustained pacing over hundreds of downloads. Third parties report 429 with no
  `Retry-After` on bursts, and Garmin publishes no numbers.
- Manual activities and multisport parents. This account has neither.

## Desired Outcome

- An athlete creates a key on Garmin Connect, adds `[connectors.garmin]` to
  `fitdocs.toml`, runs `fitdocs connect garmin`, then `fitdocs pull`.
- Every activity with a `.fit` original reaches the inbox byte for byte,
  history included, and the normal drain takes it from there.
- With `wellness = true`, daily wellness joins the series, tagged by its source.
- The key never leaves the athlete's machine, and no fitdocs service is
  involved.
- An athlete needs neither intervals.icu nor a data export.

## Approach

A built-in connector on `fitdocs.connectors.http`, standard library only, shaped
like `intervals`. It does not depend on Garmin's client: that needs Python 3.12
and `requests`, against fitdocs's 3.11 floor and its no-new-dependency rule for
connectors.

**Recommendations for requirements and design** (viability check, 2026-11-05):

1. **Auth is `API_KEY`.**
   - `verify` mints a token once and discards it.
   - A pull mints one token on first use, single-attempt, cached for that
     session and never stored.
   - A 401 or 403 from the token call says the key was refused or expired and
     names the remedy. A plain 403 would otherwise read as "report a bug".
   - `LOGIN` is rejected: connectors Req 4.6 forbids storing the value the user
     typed, and a token with minutes left would die mid-pull.
2. **First pull takes full history, oldest first.**
   - Spacing goes through the injected `session.sleep`, 2.5 s to start with.
     About 900 files then take about 38 minutes.
   - Each run is capped, and the rest is reported as a `ListingDeferral`,
     because the ledger saves only at the end of an instance and only a
     no-watermark pull resumes by itself.
   - `--since` narrows it. intervals' 30-day default does not fit a route whose
     point is having no export; the requirements phase confirms this with the
     maintainer.
3. **Failure mapping differs from intervals on purpose.**
   - A 5xx on one download stays per-activity, with a stop after several in a
     row. intervals' "5xx ends the instance" would let one bad activity stall
     everything newer, oldest first.
   - A 429 raises `AuthFailure(RATE_LIMITED)`, which also stops wellness.
   - A 200 that is not a ZIP raises, because a recorded skip would be permanent.
   - A `.gpx` member is `Declined`. Zero or several members is a failure.
   - The ZIP is bounded by member size and read limit + 1. Member names are
     never used as paths.
4. **Wellness is a new source and format, not `garmin-export`.**
   - Reusing `garmin-export` lets the API's revisions silently beat the export's
     unrevised values. Use a new DEVICE source, one enveloped format, origin
     `garmin` (attribution then needs no change), per-record fetch-time
     revisions and per-record `covers`.
   - Recommended id: `garmin-personal`. Canonical order sorts by id, so it must
     sort after `garmin-export` for existing canonical values to stay put.
   - Listing runs in forward slices, because `list_wellness` is all-or-nothing
     and a decade is about 150 requests.
   - Metrics:
     - filled: resting, min and max HR, steps, sleep total and stages,
       respiration, SpO2;
     - filled once verified: stress, body battery, weight, HRV;
     - left absent: any metric with no value, and VO2max unless the live check
       sees it.
   - Never map Garmin's `hydration` to `HYDRATION_RATING`, which is a 1-4
     subjective scale.
5. **Adoption on a real wiki uses the existing rules.** A Garmin original wins
   `original:garmin` precedence, so the first `sync` after a full pull re-bases
   and re-renders every page whose copy differs. Pages may move, and pages with
   hour-shifted phone copies retime. Preserved regions survive, `pull` without
   `--sync` holds the files, and `[identity] precedence` keeps an old base. The
   docs state this plainly, and the connector adds no identity logic.

## Scope

- **In**:
  - the `garmin` connector: connect, activity listing, download, wellness
    listing and packaging;
  - the wellness format and source, registered and documented;
  - settings: `wellness`, plus what the requirements phase decides on pacing and
    the per-run cap;
  - `docs/connectors.md`, `docs/wellness.md`, `docs/configuration.md`, the
    website's connector guide, README and CHANGELOG;
  - in the docs: creating and renewing a key, the terms the athlete accepts, a
    non-affiliation line, and what a first pull does to an existing wiki;
  - the first-task live check, on the maintainer's go.
- **Out**:
  - women's health, courses, training and golf;
  - any relay or hosted path for a Garmin key;
  - uploading or changing anything at Garmin (read-only);
  - parsing GPX (`2026-09-12-gpx-only-activities-in-a-garmin-export-are-unrepresentable`);
  - Garmin's activity summary JSON as page content (fitdocs renders the file);
  - Garmin's `.cn` server (no way to test it);
  - the Garmin export-zip importer (Phase 8 follow-on).

## Boundary Candidates

- Auth and the session token: key to token, refused-key wording.
- Activities: paged listing, fetch, ZIP handling, per-run cap, pacing.
- Wellness pull: slices, day merge, packaging.
- Wellness format: parser, source registration, metric mapping.
- Docs and the terms gate.

## Out of Boundary

- Identity, merge and base precedence, which this consumes unchanged.
- The connector plugin slot (`plugin-api`), which stays open for other sources.
- The `intervals` connector's Garmin-block detection
  (`2026-10-12-intervals-garmin-data-block-risk`).
- Shelved and deferred specs from Phase 14's extension.

## Upstream / Downstream

- **Upstream**: `connectors` (framework), `intervals-connector` (pattern),
  `wellness-store` (registry), `activity-identity` and `channel-merge`.
- **Downstream**: every Garmin user's pull. `plugin-api`'s docs may point at it
  as a worked example of a token source.

## Existing Spec Touchpoints

- **Extends**:
  - `connectors`: the built-in list and the docs' statements about it, and the
    terms gate (`.kiro/specs/connectors/requirements.md:87`);
  - `wellness-store`: one more source, which changes canonical order and
    rebuilds series once (`inputs_digest`).
- **Adjacent**:
  - `intervals-connector`: its "not viable" premise was about a password login,
    and a Personal key is not that login;
  - `plugin-api`.

## Constraints

- **Provenance.** The connector, its specs and its tests derive only from the
  public sources above and from measurement. Nothing comes from Garmin's
  developer portal, from the hosted deployment's private Garmin notes, or from
  any third party's copy of Garmin's documents. Implementers and reviewers do not
  open those. Code is written here, not copied from Garmin's client; any copied
  part owes Apache-2.0 attribution.
- **The key.** It is stored only in the per-user credential store, or read from
  `FITDOCS_CONNECTOR_GARMIN_API_KEY`. It is never sent anywhere but Garmin's
  token call, and never logged, written to the data root or sent to a relay. The
  terms say "personal to you" and bar sharing it with any third party.
- **The terms gate.** `docs/connectors.md:634` ships a connector only when the
  service's terms permit this kind of personal access, so the docs cite Garmin's
  wording: "programmatic access to their own data", and "applications, services,
  or tools that you develop or operate for your own use". They claim no
  permission and no endorsement. The maintainer accepted on 2026-11-05 that
  Garmin has not ruled on "operate".
- **Naming.** The name "Garmin" is used descriptively, with a non-affiliation
  line and no logo.
- **Absent is `None`.** A missing wellness value is absent, never `0`, and a 204
  means no data.
- **Network.** `fitdocs pull` and `fitdocs connect` are the only commands that
  touch Garmin. `tech.md`'s pull sentence covers a token mint only in login
  style, so it is reworded in the same change.
- **Tests.**
  - Fixtures are synthetic, with no personal data in this repository.
  - By maintainer ruling, tests cover code only: no new test reads a doc,
    changelog or spec, and a doc-binding test this work touches is deleted, not
    updated.
  - One catch: `NeutralScan` in `tests/connectors/test_docs.py` is a real code
    guard over `src/` and `tests/`, and the only host-confinement guard. Move it
    to its own file before deleting anything there.
- **Pins to expect:** the module list in `tests/connectors/test_boundary.py`,
  the registry order, the wellness source-order literals, and the clock scan's
  raw-substring trap. `__all__`, `CONTRACT_VERSION` and `DOC_VERSION` should not
  move (Apple added a source and format without moving them); confirm at landing.
- **Run the forbidden-strings gate** with its variable set. Its list lives
  outside the repository, so reading the code cannot clear it.
