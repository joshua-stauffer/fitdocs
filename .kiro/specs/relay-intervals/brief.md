# Brief: relay-intervals

## Problem

Publishing to intervals.icu directly needs a personal API key in the
athlete's fitdocs credential store, which is `intervals-publish`'s default
route. Two kinds of athlete would rather connect intervals.icu once to
their relay account, in a browser, the same way they connect Strava:

- an athlete who does not want to handle an API key;
- an athlete whose fitdocs runs somewhere they would rather not keep one.

The maintainer chose to offer both routes, with direct as the default
(2026-10-31).

## Current State

- `intervals-publish` (planned) implements resolve, annotate and push
  against intervals.icu with the personal key. It returns publish-core
  codes and writes a direct activity link.
- `strava-publish` (planned) builds the relay's OAuth-connect machinery:
  connect sessions, callback, encrypted token custody and revocation.
- **intervals.icu OAuth** (forum t/2759 and the OpenAPI docs, checked
  2026-10-31):
  - an app is requested at <https://intervals.icu/oauth/apply> and shows
    "Pending" until approved. The OAuth flow does not work before then, and
    no approval criteria are published;
  - scopes come as READ or WRITE per area; `ACTIVITY:WRITE` implies read;
  - the code must be exchanged within 2 minutes, and PKCE (S256) is
    optional;
  - there are access tokens only, no refresh tokens. `DELETE
    /api/v1/disconnect-app` revokes;
  - an OAuth app gets 100 calls per user per day, up to 500 users, plus
    10 req/s per IP;
  - the terms (effective 2025-10-23) permit any lawful use, commercial
    included, and have no relay or AI clause.

## Desired Outcome

- An intervals.icu target instance can select the relay route.
  `fitdocs connect` for it then opens the relay's intervals.icu connect
  page, and fitdocs holds no intervals.icu key.
- `fitdocs publish --to <instance> --yes` behaves exactly as on the direct
  route: the same resolution order, the same codes and the same direct
  activity link. The only difference is that the relay makes the calls.
- Disconnecting revokes the relay's intervals.icu token.

## Approach

Reuse rather than rebuild.

- The relay's OAuth machinery comes from `strava-publish`, with
  intervals.icu as a second provider.
- The resolve, annotate and push semantics come from `intervals-publish`.
  - They exclude the ledger step: the relay has no access to the athlete's
    pull ledger. It resolves through the listing window and the identity
    rule.
  - The design decides between sharing code with the fitdocs connector and
    keeping a pinned relay-side copy.
- The relay may return the intervals.icu activity id, which the link needs.
  Only Strava is bound by the "nothing comes back" rule; intervals.icu's
  terms allow it.

## Scope

- **In**:
  - the intervals.icu provider in the relay's connect machinery;
  - the relay's intervals.icu publish endpoint, with service responses
    mapped to publish-core codes;
  - the per-instance route setting (direct or relay; direct by default),
    and the matching `fitdocs connect` behaviour;
  - documentation, including the self-hosting note that a self-hosted relay
    needs its own approved intervals.icu OAuth app.
- **Out**:
  - planned workouts, thresholds, wellness through the relay;
  - any change to the direct route.

## Boundary Candidates

- Relay provider registration and token custody, against the relay publish
  endpoint, against fitdocs route selection.

## Out of Boundary

- The direct route (`intervals-publish`).
- Accounts and deployment (`relay-accounts`).

## Upstream / Downstream

- **Upstream**: `strava-publish` (the OAuth machinery), `intervals-publish`
  (the semantics), `relay-accounts`, `publish-core`.
- **Downstream**: none planned.

## Existing Spec Touchpoints

- **Extends**: `connectors` (the route setting on the intervals instance)
  and `docs-site`.
- **Adjacent**: `intervals-connector`.

## Constraints

- **Gated on approval.** Implementation waits on intervals.icu approving the
  maintainer's OAuth app. Applying is a maintainer action. Specs can be
  written before then.
- **Budget.** 100 calls per user per day. A publish that would exceed it
  returns a rate-limited code.
- **Codes only.** No intervals.icu response text crosses the relay
  boundary.
- **Credentials.** Tokens are encrypted at rest with the same key handling
  as `strava-publish`.
