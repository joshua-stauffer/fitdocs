# Brief: intervals-publish

## Problem

intervals.icu already holds most of the athlete's activities:

- Garmin rides arrive over Garmin's partner API;
- HealthFit uploads arrive as an OAuth client.

The athlete wants each workout's post (its title and the composed
description) to appear on the matching intervals.icu activity, and a link
back from the workout page. This is the first concrete publish target, and
it works with the personal API key the athlete has already configured for
pulling.

## Current State

- **The connector** (`connectors/intervals.py`):
  - it is the id `intervals` with `API_KEY` auth (HTTP Basic, username
    `API_KEY`);
  - it declares the capabilities `{PULL_ACTIVITIES, PULL_WELLNESS}`;
  - it calls GET endpoints only (`/athlete/0/activities`,
    `/activity/{id}/file`, `/athlete/0/wellness`, `/athlete/0`).
- **The transport** (`connectors/http.py`):
  - `HttpRequest.method` is `Literal["GET", "POST"]` (`:98`), so PUT does
    not exist;
  - `HttpClient.post` exists, but no connector uses it (`:337-353`);
  - DATA mode retries on 429, 5xx and transport errors, POST included
    (`:297-317`).
- **The pull ledger.**
  - It maps the intervals.icu `remote_id` to the `sha256` of the delivered
    `fit-archive/<sha256>.fit` (`connectors/ledger.py`).
  - The intervals-connector design intends a later push to use this record
    to map a page's archive source to `remote_id`
    (`.kiro/specs/intervals-connector/design.md:898-903`).
- **The spec's own rule.** The intervals-connector spec says follow-ons
  "extend this connector rather than start another"
  (`.kiro/specs/intervals-connector/brief.md:147-150`). Phase 12's
  `wellness-pull` followed that rule.
- **Service text.** `_service_text` puts up to 300 characters of the
  redacted service body into messages (`:106-118, 569-589`). Publish paths
  must not.
- **The identity rule.** `identity.matching.pair_evidence(SessionKey,
  SessionKey)` is the one cross-source match rule, Amendment 1's strict tier:
  - start time within 1 s;
  - distance within max(5 m, 20 %);
  - elapsed time compared only when distance is missing.
- **The intervals.icu API** (OpenAPI at <https://intervals.icu/api/v1/docs>,
  checked 2026-10-31):
  - `PUT /api/v1/activity/{id}` updates an activity. Its documentation says
    "Strava activities cannot be updated".
  - `POST /api/v1/athlete/{id}/activities` uploads a file, with `name`,
    `description`, `device_name` and `external_id`. "Activities are de-duped
    using a hash of the file": the response is 201 if at least one new
    activity was created and 200 if all were duplicates.
  - `GET /api/v1/athlete/{id}/activities` lists by `oldest`/`newest` local
    date-times. Strava-imported entries come back as empty stubs.
  - API-key limits: 5,000 calls/day and 2,500 per 15 min, plus 10 req/s per
    IP.
  - Terms (forum t/114087, effective 2025-10-23): "any lawful purpose,
    including commercial use". Garmin attribution is required where
    Garmin-sourced data is shown. There is no AI clause and no relay clause.

## Desired Outcome

- `fitdocs publish --to <intervals instance> --yes` acts on each opted-in
  page whose composed post is new or changed:
  - it sets the name and description of the matching intervals.icu
    activity;
  - if no matching activity exists and the instance allows uploads, it
    uploads the page's base `.fit` with that name and description.
- Every outcome is a code from publish-core's vocabulary. No intervals.icu
  response text is printed, logged or written.
- The page's links block carries `https://intervals.icu/activities/<id>`.
- A dry run makes no network call.

## Approach

Extend the existing intervals.icu connector by driving the reserved
capabilities `RESOLVE_REMOTE_ACTIVITY`, `ANNOTATE_REMOTE_ACTIVITY` and
`PUSH_ACTIVITY`. A page's activity is resolved in this order:

1. **The pull ledger.** If one of the page's `sources` sha256 values maps to
   a pulled `remote_id`, that is the activity.
2. **A listing window** around the page's start time, matched with
   `pair_evidence`:
   - one candidate is the activity;
   - two or more is an ambiguity code, and nothing is posted.
3. **Nothing found.** If uploads are enabled, upload the base `.fit` with
   `external_id` set to fitdocs's publication id. Otherwise return a
   not-found code.

A Strava stub (an entry intervals.icu imported from Strava) cannot be
updated through this API, so it gets its own code. It is never a silent skip.

## Scope

- **In**:
  - connectors amendment:
    - PUT in `HttpRequest`;
    - a single-attempt write path for non-idempotent POST uploads, separate
      from DATA-mode retries (the design decides whether an idempotent PUT
      may retry);
    - driving the three capabilities through optional operation protocols;
    - amended Req 1.2-1.4 wording;
    - `docs/connectors.md`'s network statements (publish is a network
      command), and the `tech.md` "Network and Credentials" section;
  - intervals-connector amendment:
    - the update and upload endpoints;
    - multipart upload encoding;
    - mapping every status to an outcome code;
    - the local-time handling of listing windows. Pages are dated by the
      FIT's recorded offset (DOC 11), and intervals.icu lists in local time;
    - Strava-stub detection on the resolve path;
    - re-pinning the capability-declaration mutation;
    - a per-instance `publish_upload` (or similar) setting, off by default;
  - the direct activity link for the links block;
  - the target's entry in publish-core's discovery listing;
  - tests at the `HttpClient` transport seam, with no live calls in the
    suite. A one-off live check on the maintainer's account follows the
    2026-10-02 precedent and needs the maintainer's say-so.
- **Out**:
  - the relay route to intervals.icu (`relay-intervals`);
  - planned workouts, thresholds, workout libraries;
  - writing any field other than name and description (gear, type, tags);
  - deleting activities.

## Boundary Candidates

- Resolve (read-only: ledger, then listing) against annotate (PUT) against
  push (POST upload).
- The service mapping (status to code) as one table the tests pin.

## Out of Boundary

- Composing the post, the opt-in, the publish ledger, the links block and
  the CLI command. publish-core owns all of these.
- Any Strava behaviour.

## Upstream / Downstream

- **Upstream**: publish-core (the vocabulary, the target contract, the
  publish request), connectors (credentials, transport), activity-identity
  (`pair_evidence`).
- **Downstream**: `relay-intervals` reuses the resolve and annotate
  semantics on the relay side.

## Existing Spec Touchpoints

- **Extends**: `connectors`, `intervals-connector`.
- **Adjacent**:
  - `wellness-pull`, the precedent for driving a reserved capability on
    this connector;
  - `activity-identity`.

## Constraints

- **Codes only.** No intervals.icu response body, header or error text
  reaches any output. `_service_text` is not used on publish paths.
- **No duplicates.** A non-idempotent upload is attempted once.
  intervals.icu's file-hash de-dup is a backstop, not the design.
- **Identity never guesses.** Matching is one-to-one, and ambiguity is
  reported, never settled by order.
- **Credentials.** The existing credential store and `FITDOCS_CONNECTOR_*`
  overrides are used, with no new secret. Authentication is never retried.
- **User-Agent.** The composed fitdocs User-Agent goes on every request;
  Cloudflare answers urllib's default agent with 403/1010.
