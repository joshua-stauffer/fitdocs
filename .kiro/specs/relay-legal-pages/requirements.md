# Requirements Document

## Project Description (Input)
**Who has the problem.** The operator of a fitdocs relay with a public URL,
and the maintainer applying for developer access on the hosted relay's
behalf. Strava (for the publish relay), intervals.icu (for the OAuth
application `relay-intervals` is gated on) and Garmin (whose push-tier
request form requires one) each ask for a privacy policy URL before they
approve an application. Garmin's public agreement also asks for end-user
terms carrying protections for the platform's benefit, a conspicuous policy
with withdrawable consent before collection, access/export/deletion rights,
and an AI transparency statement.

**Current situation.** The relay serves one Strava-only privacy policy
(`relay/src/fitdocs_relay/strava/policy.py`, rendered by
`strava/pages.py:privacy_page` under `PAGE_HEADERS`), and only while Strava
is configured. There is no terms page. A deployment cannot add a section:
the `FITDOCS_RELAY_EXTENSIONS` seam loads `RelayExtension` objects that can
only add token issuance. `FITDOCS_RELAY_PRIVACY_POLICY_URL` lets an operator
point the consent pages at a policy hosted elsewhere. relay-intervals'
design already plans a target-neutral composition
(`fitdocs_relay/targets/policy.py`: `COMMON_OPENING`, provider groups,
`COMMON_CLOSING`), unimplemented and gated on intervals.icu's approval.

**What should change.** A relay with a public URL serves one privacy policy
at `/privacy` and one terms page at `/terms` whenever at least one section
applies, whether or not Strava is configured. Both are composed in a fixed
order: a common opening (the operator; what the relay is and does), one
section per provider (Strava's existing text unchanged where strava-publish
Req 16.1 pins it; an intervals.icu relay-route section written now;
sections a deployment contributes through the extension seam), common
sections (security, breach notice, access/export/delete rights and how to
exercise them, an AI statement, retention stated per provider, contact and
changes), and a common closing. A provider's section can be announced before
its credentials exist so an application can cite the policy; the policy
never describes a provider that is neither configured nor announced. The
terms page carries the common end-user terms (disclaimers, limitation of
liability, protections for the platforms' benefit), and providers or a
deployment add clauses the same way. The consent pages link both; an
operator's own URLs still override the relay's pages. `docs/relay.md`
describes the composition, announcing and what a deployment must
contribute.

**Constraints.** Every statement is true in every configuration. Retention
wording never promises a deletion the relay does not perform. No platform
text crosses into the pages. Page headers and CSP stay `PAGE_HEADERS`;
contributed sections are escaped or structured, never raw HTML. Phase 14
wording rules hold ("Compatible with Strava", no agent named), and the
extension's public-text rule means no Garmin text in this repository. Out of
scope: the Garmin section and operator-specific content (contributed by the
hosted deployment), legal advice, translation, cookie banners, and
enforcing anything the policy states. Keep the spec small: it unblocks the
rest of the Phase 14 extension.

Discovery context: `brief.md` in this directory, and the Phase 14 extension
section of `.kiro/steering/roadmap.md`.

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
