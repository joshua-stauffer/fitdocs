# Brief: relay-legal-pages

## Problem

Every platform the relay talks to asks for a privacy policy URL before it
approves a developer application:
- Strava, for the publish relay (Phase 14, `strava-publish`);
- intervals.icu, for the OAuth app that `relay-intervals` is gated on (the
  maintainer is filling in that application now);
- Garmin, whose push-tier request form makes a privacy policy URL a
  required field.

Garmin's public agreement (FRM-0952 Rev. B) also asks for:
- terms with each end user that carry protections for Garmin's benefit
  (§5.3);
- a conspicuous privacy policy and withdrawable consent before any data is
  collected (§15.4);
- access, export and deletion rights (§15.4(d));
- an AI transparency statement wherever AI processes the data (§15.10).

The relay today serves one Strava-only policy, and only while Strava is
configured. It has no terms page, and a deployment cannot add a section.
So the hosted relay has no policy address that covers what it will actually
do, to give any platform that asks for one. This blocks every other item in the
extension.

## Current State

- **The policy text** is `relay/src/fitdocs_relay/strava/policy.py:16-154`.
  It is rendered by `privacy_page` (`strava/pages.py:186`), with
  `PAGE_HEADERS` for CSP and no caching (`strava/pages.py:27`).
- **The page is served only while Strava is configured**
  (`strava/routes.py:136-138,339`). `/privacy` is a reserved prefix
  (`routes.py:73-83`).
- **What it says:**
  - The relay keeps encrypted tokens and their expiry, a keyed account
    hash, publication ids and match facts, and "nothing else from Strava"
    (`policy.py:63-73`).
  - Data is deleted "at once" on disconnect, deauthorization, refused
    renewal or account deletion (`:91-98`).
  - The operator notifies Strava of a breach within 24 hours (`:105-109`).
  - The opening says the relay "publishes workouts from fitdocs to Strava"
    (`:51-55`).
  - The statements strava-publish Req 16.1 requires are pinned by its
    tests.
- **An operator's own policy:** `FITDOCS_RELAY_PRIVACY_POLICY_URL` points
  the consent pages at a policy hosted elsewhere (`contract.py:62,188-190`).
- **Configuration and composition:**
  - Operator name, support contact and policy URL are in `TargetsConfig`
    (`strava/config.py:70-77`).
  - relay-intervals' design already plans a composition:
    `fitdocs_relay/targets/policy.py` with `COMMON_OPENING`, per-provider
    groups, then `COMMON_CLOSING` (`.kiro/specs/relay-intervals/design.md:1111,1146`).
    It is unimplemented, and its spec is gated on intervals.icu's approval.
- **The wrapper seam:** `FITDOCS_RELAY_EXTENSIONS` loads `RelayExtension`
  objects (`contract.py:57,146-148`), but they can only add token issuance.
- **The hosted relay is not answering yet** at its address (checked
  2026-11-03). Getting it live is the hosted deployment's job, and a
  prerequisite for any platform's form to cite the URL.

## Desired Outcome

- **When the pages are served.** A relay with a public URL serves one
  privacy policy at `/privacy` and one terms page at `/terms` whenever at
  least one section applies, whether or not Strava is configured.
- **How they are composed,** in a fixed order:
  1. a common opening: the operator, and what the relay is and does;
  2. a section per provider:
     - Strava's existing text, unchanged;
     - intervals.icu's relay route, written now;
     - sections a deployment contributes through the extension seam (the
       hosted Garmin section);
  3. common sections:
     - security;
     - breach notice;
     - each user's rights to access, export and delete, and how to
       exercise them;
     - an AI statement (the relay processes nothing with AI);
     - retention, stated per provider;
     - contact, and changes to the policy;
  4. a common closing.
- **Publishing a section early.** A provider's section can be "announced"
  before its credentials exist, so an application can cite the policy.
  The policy never describes a provider that is neither configured nor
  announced.
- **The terms page** carries the common end-user terms: disclaimers,
  limitation of liability, and protections for the platforms' benefit. A
  provider or a deployment adds its own clauses the same way.
- **Linking.** The consent pages link both. An operator's own URLs still
  override the relay's pages. If a terms counterpart to
  `FITDOCS_RELAY_PRIVACY_POLICY_URL` is added, it is a deploy-contract row.
- **Docs.** `docs/relay.md`'s privacy section describes the composition,
  announcing, and what a deployment must contribute.

## Approach

- **Lift the policy into a target-neutral composition,** as relay-intervals
  designed it: `COMMON_OPENING`, provider groups, `COMMON_CLOSING`.
  - Keep Strava's text byte-for-byte where Req 16.1 pins it.
  - Add the intervals.icu relay-route section, describing what
    relay-intervals will store and send. relay-intervals then consumes the
    composition instead of building it.
- **Extend the extension seam** so a `RelayExtension` can contribute policy
  and terms sections, with a stable order and its own heading. The hosted
  wrapper supplies the Garmin section and the operator's particulars,
  including sub-processors, through it.
- **Add `/terms`, and the announce setting.** The design picks the shape:
  an environment row, or the extension declaring announced providers.

## Scope

- **In**:
  - the composition, and serving `/privacy` and `/terms`;
  - the common sections, the Strava section (moved) and the intervals.icu
    relay-route section;
  - the extension-seam hook for sections;
  - announcing;
  - consent-page links;
  - the deploy-contract rows it needs;
  - docs, and tests that pin the required statements.
- **Out**:
  - the Garmin section text, and any operator-specific content
    (sub-processor names, legal entity, jurisdiction). These are contributed
    by the hosted deployment.
  - legal advice;
  - translation;
  - cookie banners (the pages set no cookies);
  - enforcing anything the policy states.

## Boundary Candidates

- The composition engine and its ordering rules.
- The section content shipped here: the common sections, Strava and
  intervals.icu.
- The extension-seam contribution API: sections, headings and order.
- The announce mechanism.
- The terms page and the consent-page links.

## Out of Boundary

- Provider registration and consent machinery (relay-providers).
- Held-item retention statements beyond the common retention frame
  (relay-held-files adds its section when it lands).
- Anything Garmin-specific (the hosted deployment).

## Upstream / Downstream

- **Upstream**:
  - strava-publish: the policy text, the pages, and Req 16.1;
  - relay-server: the extension seam, the environment contract and the
    reserved prefixes.
- **Downstream**:
  - relay-providers: providers contribute sections through this API;
  - relay-held-files: the held-data retention section;
  - relay-intervals: it consumes the composition;
  - the hosted deployment's policy sections.

## Existing Spec Touchpoints

- **Extends**:
  - strava-publish: Req 16.1's text moves, and is still pinned;
  - relay-server: the extension seam gains section contribution, at the
    wrapper-seam version main + 1, plus the environment-table rows;
  - relay-intervals: its policy composition design is delivered here.
- **Adjacent**: relay-providers, which touches `strava/pages.py` and the
  route table next. Land this first.

## Constraints

- **Policy truth.** Every statement is true in every configuration, so a
  section appears only for what is configured or announced. Retention
  wording never promises a deletion the relay does not perform. The held
  items' "may be deleted after 30 days" is the model.
- **No platform text crosses into the pages.** All copy is fitdocs-written
  or deployment-contributed.
- **Page headers and CSP stay as `PAGE_HEADERS`.** Contributed sections are
  escaped or structured, never raw HTML.
- **The Phase 14 wording rules hold:** "Compatible with Strava", and no
  agent named. The extension's public-text rule for Garmin means no Garmin
  text here.
- **Speed matters.** This is the unblocker, so keep the spec small. The
  hosted relay must also be live before any application can cite the URL.
