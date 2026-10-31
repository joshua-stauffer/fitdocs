# Brief: strava-publish

## Problem

Strava is where an athlete's training is seen by others. Garmin's
auto-sync usually lands the activity on Strava first, under a generic name.
The athlete wants the workout's post (its title and composed description)
on that activity, and a link to it from the workout page.

Strava's API needs a registered application. Registering one needs a paid
Strava subscription, since 2026-06-01, and the client secret cannot ship in
an open-source CLI. A relay holding one application lets athletes connect
their Strava accounts without each registering an app.

## Current State

- **Nothing in the code talks to Strava.** The intervals.icu connector
  declines Strava-sourced listing entries as stubs
  (`connectors/intervals.py`). `www.strava.com` is a not-permitted host in
  the service-neutral docs scan (`tests/connectors/test_intervals_docs.py:166`).
- **The OAuth style is reserved and refused.** `OAUTH_BROWSER` is reserved,
  and `fitdocs connect` refuses it (`connectors/protocol.py:146-159`;
  `cli.py:1360-1364`).
- **Phase 8 named this follow-on** ("Strava, push only", roadmap):
  - find the synced activity by time window and set its name and
    description; upload only when none exists;
  - the lookup's result may be used only to address the post;
  - nothing read from Strava ever reaches a page.
- **Strava's terms and API** (research 2026-10-31; primary sources quoted
  in the Phase 14 discovery). AGR is the API Agreement
  (<https://www.strava.com/legal/api>). POL is the API Policy
  (<https://www.strava.com/legal/api_policy>). Both took effect
  2026-06-01.
  - **Writes.**
    - `PUT /activities/{id}` sets `name`, `description` and a few other
      fields on any activity the athlete owns, whichever app created it.
      Scope: `activity:write`, plus `activity:read_all` for Only Me
      activities.
    - `POST /uploads` (`data_type=fit`, `name`, `description`,
      `external_id`) is asynchronous: poll at 1 s or slower; the mean
      processing time is under 2 s. A duplicate comes back as a
      human-readable English error containing the existing activity id.
    - There is no delete.
  - **Lookup.** `GET /athlete/activities` takes `after`/`before` epoch
    filters.
  - **OAuth.** Access tokens last 6 h. The refresh token rotates on every
    refresh and the old one is invalidated at once. Users can untick
    scopes, so the returned `scope` must be checked. The redirect URI must
    be within the app's one callback domain, so set it to `api.fitdocs.ai`
    exactly. `POST /oauth/revoke` is the deauthorization call.
  - **Webhooks.** A deauthorization webhook exists: one subscription per
    app, which must answer 200 within 2 s.
  - **Rate limits are per application and shared by all athletes.**
    - Overall: 200 per 15 min and 2,000 per day.
    - Non-upload: 100 per 15 min and 1,000 per day. PUT, list and
      upload-status polls draw on this bucket.
    - A self-serve upgrade doubles both.
  - **Athlete capacity.**
    - A new app starts at 1 athlete (Single Player Mode), and its owner can
      raise it to 10.
    - More needs Strava's review, which has no deadline.
    - The Standard tier needs an active Strava subscription (POL §3.3).
  - **Retention, storage, display.**
    - POL §6.2: Strava Data stays in cache at most 7 days, and is not
      stored otherwise.
    - POL §5.5: no persistent index of Strava Data.
    - POL §2.3: Strava Data is shown only to its athlete.
    - AGR §2.3: an activity id is Strava Data.
    - POL §6.3: deletions are reflected within 48 h.
    - POL §7.4: a user's data is deleted within 30 days of revocation.
  - **AI.** POL §5.3 bars using the API Materials or Strava Data in
    connection with any AI Application, including "ingestion into a
    context window or working memory". "AI Application" is not defined.
  - **Intermediaries.** POL §5.16 bars a pass-through proxy that re-exposes
    the API to third parties, and bars sharing or multiplexing tokens
    across services or end users. AGR §1.1 allows a single API token for a
    single Developer Application.
  - **Commercial.** POL §5.8 forbids charging end users for Strava
    functionality. POL §4.6 forbids an announcement or press release that
    references Strava without written consent.
  - **Brand** (guidelines revised 2025-09-29):
    - "Connect with Strava" must link to `/oauth/authorize`;
    - a link to an activity reads "View on Strava";
    - interoperability is described as "Compatible with Strava" or
      "Powered by Strava";
    - Strava's name never appears in the application's name.
  - **Upcoming.** The base URL `https://api-v3.strava.com` is available
    from 2027-01-04. Tokens travel in headers.
  - **Obligations.** Consent disclosures (AGR §2.1), a privacy policy
    (§7.3), a support contact (§2.4), and breach notice within 24 h
    (§8.3).

## Desired Outcome

- **Connecting.**
  - The athlete connects Strava once, to their relay token's principal.
  - `fitdocs connect <strava instance>` opens (or prints) the relay's
    connect page. That page carries the "Connect with Strava" button, and
    the CLI waits until the relay reports the connection made.
- **Posting.** `fitdocs publish --to <strava instance> --yes` asks the relay,
  for each opted-in page whose composed post is new or changed, to post it.
  The relay, each time:
  - finds the athlete's activity by start time and sets its name and
    description;
  - if none exists and uploads are enabled for the instance, uploads the
    page's base `.fit` with them instead.
- **Nothing comes back from Strava.**
  - Nothing the Strava API returns leaves the relay.
  - The relay answers fitdocs only with publish-core outcome codes.
  - fitdocs prints, logs and writes only those codes and the relay link.
- **The page link.**
  - The page's links block carries "View on Strava" pointing at the relay,
    `https://api.fitdocs.ai/go/<publication id>`. The publication id is
    fitdocs's own random identifier.
  - On a click, the relay finds the activity and redirects the browser to
    it.
  - The page and fitdocs never hold a Strava identifier (maintainer,
    2026-10-31).
- **Disconnecting.** Disconnecting, a Strava-side revocation, or deleting
  the principal removes the athlete's Strava tokens at once. Any Strava Data
  the relay holds goes within Strava's limits.

## Approach

Strava support is two pieces, the relay side and the fitdocs side.

**On the relay** (in `relay/`, on top of relay-server):

1. **Connect.**
   - A connect session is bound to the relay token's principal and carries an
     unguessable `state`.
   - It redirects to Strava's `/oauth/authorize` with the needed scopes.
   - The callback on `api.fitdocs.ai` exchanges the code and checks the
     granted scope.
   - The refresh token is stored encrypted (AES-GCM through
     `cryptography`, key from the environment).
   - Each rotation is one atomic operation on relay-server' storage
     interface, so a concurrent refresh can never lose the only valid
     token.
   - The operations this spec adds to that interface pass its conformance
     suite on both SQLite and PostgreSQL.
2. **Publish.** The endpoint accepts a publish request: the publication id,
   start time with offset, elapsed time, distance, sport, title and
   description, plus the base `.fit` when an upload is allowed. Then:
   1. It lists the athlete's activities in a window around the start time
      and applies the same strict one-to-one rule as activity-identity's
      `pair_evidence`. The design decides between a shared module and a
      pinned copy.
   2. Two or more candidates is an ambiguity code, and nothing is written.
   3. One candidate is updated with `PUT /activities/{id}`.
   4. No candidate, with uploads enabled, means `POST /uploads` is made
      once, with `external_id` set to the publication id. The upload status
      is polled until a bounded deadline.
   5. A duplicate refusal is resolved by re-listing, never by parsing its
      text.
3. **Redirect.** `GET /go/{publication id}` resolves the activity at click
   time from the stored match keys (fitdocs's data, not Strava's). Any
   cached Strava id lives 7 days at most. The browser is redirected with a
   302.
   - The endpoint is rate-limited.
   - An unknown or unresolvable id gets a fitdocs-owned "not found" page.
4. **Revocation.** The relay keeps one deauthorization webhook subscription
   and acts on its events. `/oauth/revoke` is called on a CLI disconnect.
   Deleting a principal cascades.

**In fitdocs**:

- a Strava target that talks only to the relay. fitdocs's code never names
  a Strava host;
- `OAUTH_BROWSER` driven for this instance kind (connectors amendment);
- the instance setting that enables uploads, off by default;
- the target's entry in publish-core's discovery listing.

## Scope

- **In**: everything in the Approach above, plus:
  - mapping every Strava response class (auth, scope, 4xx, 429 with the
    rate-limit headers, 5xx, upload error, timeout) to outcome codes. The
    mapping table is pinned by tests at the relay's HTTP-client seam, with
    no live Strava calls in the suite;
  - budgeting the shared rate limits. When a limit bites, a rate-limited
    code is returned and nothing is retried past the budget;
  - a configurable Strava base URL, header-only bearer tokens, and
    `/oauth/revoke`;
  - brand-compliant wording on the relay's connect page and in the links
    block;
  - the Strava sections of the privacy policy and the consent text
    (docs-site amendment), and the support contact;
  - two additions to relay-server' deploy contract: the encryption-key
    variable (with how a key rotation works), and the webhook-verification
    setting;
  - a self-hosting note: a self-hosted relay needs its own Strava
    application and subscription. It may never use the fitdocs.ai
    application's credentials (AGR §1.1-1.2).
- **Out**:
  - reading anything from Strava for display, storage, the index or a page.
    There is no Strava pull;
  - fields beyond name and description: gear, type, tags, visibility;
  - photos and media;
  - deleting activities (the API has none);
  - asking Strava for a capacity review (a maintainer action, beyond 10
    athletes);
  - charging for the feature (POL §5.8);
  - hosting and operating any relay instance.

## Boundary Candidates

- Relay: connect and token custody, publish resolution and writes, the
  redirect, revocation.
- fitdocs: the relay target and the connect flow.

## Out of Boundary

- Composing the post, the opt-in, the publish ledger, the links block and
  the `fitdocs publish` command. publish-core owns these.
- Relay tokens, principals, the envelope and the deploy contract.
  relay-server owns these.

## Upstream / Downstream

- **Upstream**:
  - publish-core: the outcome vocabulary, the target contract, the publish
    request;
  - relay-server: tokens and principals, the envelope, storage, the
    deploy contract;
  - activity-identity: the match rule.
- **Downstream**: `relay-intervals` reuses the relay's OAuth-connect
  machinery.

## Existing Spec Touchpoints

- **Extends**:
  - `connectors`: drive `OAUTH_BROWSER`; the Strava target instance kind;
  - `docs-site`: the Strava page, privacy policy sections, wording;
  - `wiki-contract`: link-block wording only, if publish-core leaves it to
    targets.
- **Adjacent**: `intervals-connector`, which already skips Strava stubs.

## Constraints

- **Nothing from the Strava API reaches fitdocs.**
  - Response bodies, headers, identifiers and URLs never cross the relay
    boundary.
  - The relay never logs them.
  - fitdocs prints, logs and writes only outcome codes and the relay link.
  - This is the design's answer to POL §5.3 and §6.2 and to the
    maintainer's rule.
- **Retention.**
  - The relay stores no Strava Data beyond a ≤7-day cache.
  - It keeps no persistent page-to-activity map; every publish and every
    redirect re-resolves.
  - Encrypted tokens and fitdocs's own match keys are the only lasting
    state.
- **One application.**
  - It is one Developer Application with per-athlete OAuth.
  - It never re-exposes the Strava API: the endpoints accept only
    fitdocs's publish request and the redirect.
  - Tokens are never shared or multiplexed across athletes.
  - The maintainer accepted the residual terms risk (roadmap Phase 14,
    decisions).
- **Writes.**
  - An upload is attempted once.
  - A PUT of the same name and description is idempotent, so the design may
    let it retry.
  - Matching is one-to-one, and ambiguity is never settled by order.
- **Capacity.** Single Player Mode, self-serve to 10 athletes. Above that
  is Strava's discretionary review.
- **Public wording.** Docs and site describe the feature as documentation
  ("Compatible with Strava"). No announcement that references Strava is
  published without Strava's written consent (POL §4.6).
