# Requirements Document

## Project Description (Input)
**Who has the problem.** The operator of a fitdocs relay with a public URL,
who needs a policy address to give each platform's developer program.
Strava (for the publish relay) and intervals.icu (for the OAuth application
`relay-intervals` is gated on) ask for a privacy policy URL before they
approve an application, and Garmin's public push-tier request form makes one
a required field. Garmin's public agreement also asks for end-user
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

*(Revised 2026-11-03, maintainer: the relay ships no terms text and no
operator commitments of its own; a deployment contributes them. See Boundary
Context.)*

Discovery context: `brief.md` in this directory, and the Phase 14 extension
section of `.kiro/steering/roadmap.md`.

## Introduction

Every platform the relay connects to asks for a privacy policy address
before it approves the developer application that grants the relay its
credentials, and some also require end-user terms. Today the relay can
show only a Strava policy, and only once Strava's credentials are
configured, so no application can cite a policy that covers what the relay
will do.

This feature gives the relay one privacy policy, composed from fixed
fitdocs text and from sections a deployment contributes, and a terms page
composed only from what a deployment contributes. A provider's section appears only while that provider is
configured or announced: announcing lets an operator publish the section
before the platform has issued credentials, and the page says plainly that
the connection is not offered yet. The common sections state the
operator, security, an AI statement, retention for each provider, contact,
and the latest date any of the page's text was written. They state facts
about the relay's code; the operator's own commitments (terms, breach
notice, how requests are handled) are the deployment's to contribute. Strava's statements move into the composition word
for word; the intervals.icu relay route's section is written now; the
hosted deployment adds its own provider and operator sections through the
extension seam.

## Boundary Context

- **In scope**:
  - serving `/privacy` whenever at least one provider section applies,
    whether or not a target is configured, and `/terms` whenever a
    deployment also contributes terms;
  - the composition and its fixed order;
  - the common sections, the Strava section (moved) and the intervals.icu
    relay-route section;
  - announcing a provider ahead of its credentials;
  - contributions of policy sections, terms sections and terms clauses
    through the extension seam;
  - links to the policy from every page the relay serves, and to the terms
    while they exist, with the operator's own addresses overriding them;
  - the deploy-contract rows, documentation, code tests, and the records
    this change owes other specs.
- **Out of scope**:
  - end-user terms text and the operator's own commitments (breach notice,
    handling of access, export and deletion requests): a deployment
    contributes them, and the relay ships none (maintainer, 2026-11-03);
  - any Garmin section text and any operator-specific content (legal
    entity, jurisdiction, sub-processor names): a deployment contributes
    them;
  - legal advice, translation and cookie banners (the pages set no
    cookies);
  - enforcing anything the policy states, including an operator command
    that exports what the relay holds about one athlete;
  - the intervals.icu connect page and consent text (relay-intervals);
  - provider registration and the consent machinery (relay-providers);
  - the held-item retention section (relay-held-files contributes it);
  - automated tests of documentation, the changelog or specs, and tests that
    pin the wording of the served pages: only code is under test, and the
    pages are tested for structure (maintainer, 2026-11-03).
- **Adjacent expectations**:
  - relay-providers registers providers whose policy sections and terms
    clauses use the contribution shape defined here, with no second
    composition;
  - relay-held-files contributes its held-data section through the same
    shape;
  - relay-intervals consumes the composition and the intervals.icu section
    instead of building them, and owns keeping that section true when it
    implements the route;
  - the hosted deployment supplies its provider and operator sections and
    must be answering at its public address before any application can
    cite it.

## Requirements

### Requirement 1: Serving the Privacy Policy and Terms Pages
**Objective:** As an operator applying for a platform's developer access, I want my relay to serve a privacy policy and a terms page as soon as it has something to describe, so that the application can cite stable addresses before the platform issues credentials.

#### Acceptance Criteria
1. While at least one provider section applies (Requirement 2), the relay server shall serve the privacy policy at `/privacy` as a fitdocs-written HTML page outside the envelope, whether or not any target is configured, and shall serve the terms at `/terms` as Requirement 7 states.
2. While no provider section applies, the relay server shall serve neither page and shall answer both paths as it answers a path it does not offer.
3. The relay server shall serve each of these pages with the same response headers as its other fitdocs-written pages (the restrictive content security policy, no referrer, no caching, no content sniffing), shall set no cookie on them and shall load no resource from another address.
4. The relay server shall answer a request other than GET to either page as it answers one to its other pages.
5. The relay server shall serve each of these pages while its database is unreachable or not ready, since neither page reads stored state.
6. The relay server shall link the privacy policy from every fitdocs-written page it serves, beside the operator's support contact, and shall link the terms from every such page while it serves its terms page or the operator configures their own terms address.
7. Where the operator configures their own privacy policy address, every page shall link that address instead of `/privacy`, and `/privacy` shall still be served; where the operator configures their own terms address, every page shall link that address, and `/terms` shall still be served where Requirement 7 provides it.
8. If at least one provider section applies and the operator's name or support contact is not configured, the relay server and its commands shall refuse to start with a configuration error naming the missing variable; where only a wrapper's contribution makes a section apply, the relay server shall refuse to start naming the wrapper and the missing variable.

### Requirement 2: Which Provider Sections Apply, and Announcing
**Objective:** As an operator, I want a provider's section on my pages exactly while I offer that provider or have announced it, so that the policy can be cited before credentials exist and never describes a connection I do not intend to offer.

#### Acceptance Criteria
1. The relay server shall include a built-in provider's section only while that provider is configured or announced, and never otherwise.
2. The relay package shall offer one optional deploy-contract setting that names the built-in providers to announce.
3. If the announce setting names a provider the relay does not know, or names one twice, the relay server and its commands shall refuse to start with a configuration error naming the variable and the offending name.
4. While a provider is announced and not configured, the relay server shall begin its section with a fixed statement that this relay does not offer connecting to that platform yet and that the section describes what will apply once it does, and the common opening shall list that provider as announced rather than offered.
5. When an announced provider becomes configured, the relay server shall drop that statement and change nothing else in the provider's section except what that provider's own settings select (such as Strava's link setting).
6. While the intervals.icu relay route is not part of the relay, the relay server shall include the intervals.icu section only when intervals.icu is announced.
7. While a provider is announced and not configured, the relay server shall serve no route, connect page or capabilities entry for it, and announcing shall change no answer other than the two pages' content.
8. The relay server shall include a section a deployment contributes (Requirement 8) while the contributing wrapper is installed; where the wrapper marks its provider as announced, the relay server shall show the same statement as criterion 4 for it.

### Requirement 3: The Privacy Policy's Composition and Order
**Objective:** As a reader of the policy (an athlete or a platform's reviewer), I want one page that always presents the same parts in the same order, so that I can find what the relay does with each platform's data and what holds for all of them.

#### Acceptance Criteria
1. The relay server shall compose the privacy policy in this order: the common opening; one group per applying provider, each headed by that platform's name, built-in providers first in a fixed order (Strava, then intervals.icu), then deployment-contributed providers in wrapper installation order and each wrapper's own order; the common sections; operator sections a deployment contributes; the common closing.
2. For the same configuration and the same installed wrappers, the relay server shall serve the same policy page byte for byte on every request and after every restart.
3. The relay server shall put on the page only fitdocs-written text, the operator's configured name and support contact, and text a deployment contributed; it shall never put text any platform returned on the page.
4. The relay server shall show every operator-configured and contributed value as text, so that no configured or contributed value can add markup, a script, a style, a form or a resource load to the page.

### Requirement 4: The Strava Section Moves Unchanged
**Objective:** As the maintainer bound by Strava's terms, I want every statement of today's Strava policy kept word for word in the composed policy, so that what strava-publish Requirement 16.1 requires stays true and stays pinned.

#### Acceptance Criteria
1. While Strava is configured or announced, the relay server shall include in the privacy policy, as Strava's group, today's nine Strava policy sections word for word and in their current order (the relay's operator, what fitdocs sends, what the relay receives from Strava and keeps, what it sends to Strava, what it returns to fitdocs under the link setting, deletion, the athlete's choices, security, and contact), showing the operator's name and support contact where today's page shows them.
2. While Strava is announced and not configured, the Strava group's statement of what the relay returns to fitdocs shall follow the configured link setting, or its default when none is configured.
3. The Strava connect page's consent text and the "Connect with Strava" control shall be unchanged.
4. strava-publish's tests of the policy's statements and of the consent text shall keep every expected value they assert; a moved test may change only its imports, its setup and the place on the page where it looks for a section.

### Requirement 5: The intervals.icu Relay-Route Section
**Objective:** As the maintainer applying for intervals.icu's OAuth application, I want the policy to describe what the relay will do on the intervals.icu relay route, so that the application can cite a policy that is true of the route it would authorize.

#### Acceptance Criteria
1. Where intervals.icu applies, the relay server shall include in the privacy policy an intervals.icu group stating: what fitdocs sends the relay; what the relay receives from intervals.icu and keeps (the access token, encrypted, and a keyed hash of the athlete's identifier, and nothing else); what the relay sends to intervals.icu; what the relay returns to fitdocs (the identifier of the activity a post landed on, and nothing else intervals.icu supplied); when the relay deletes what it keeps; the athlete's choices (disconnecting, and revoking the application in intervals.icu's settings); and that intervals.icu tokens are encrypted and never logged.
2. Every statement in the intervals.icu group shall agree with relay-intervals' requirements as they stand when this feature lands, and the group shall describe only what the relay does on the relay route.
3. The intervals.icu group shall state that connecting intervals.icu directly with the athlete's own API key does not involve the relay.

### Requirement 6: The Common Sections
**Objective:** As an athlete, I want the policy to say who runs the relay, how my data is protected, whether AI touches it and how long it is kept, so that I can decide whether to connect.

#### Acceptance Criteria
1. The common opening shall name the operator, state that the relay is a service the operator runs to connect fitdocs to the platforms the page lists on the athlete's behalf, list each applying provider as offered or announced, and state that fitdocs works without the relay.
2. The common security section shall state that platform tokens are encrypted before they are stored, that relay tokens are kept only as an identifier and a keyed hash, and that the relay's logs carry no token, authorization code, platform response, request body or client network address.
3. The common AI section shall state that the relay processes none of the data it receives with artificial intelligence or machine learning, uses none of it to train such a system, and sends it nowhere except as the policy describes, and that what each platform does with what the relay sends it is governed by that platform's own policy.
4. The common retention section shall state, for each applying provider, how long the relay keeps that provider's data, as the provider declares it, and, for the relay as a whole: that relay-token records (identifier, keyed hash, label and times, revoked tokens included) are kept until the relay account is deleted, that a connect session lasts at most ten minutes, that request and call counters hold only counts, kept against a relay token, a relay account or a keyed hash of the client's network address (never the address itself), each of which may be deleted once its window has ended, and that how long log records are kept is the operator's choice.
5. Every retention statement shall name a trigger on which the relay deletes the data, or say only that the data may be deleted; no statement shall promise a deletion the relay does not perform.
6. The common contact and changes section shall show the operator's support contact, say that the operator may change the policy, and say that what it shows also follows the relay's configuration.
7. The common closing shall state the latest date on which any text the page shows was written: the later of the date of the fixed fitdocs text it shows and the latest date any contributed section it shows declares.

### Requirement 7: Terms Supplied by the Deployment
**Objective:** As the operator of a relay that serves other people, I want to publish my own end-user terms at the relay's address, while the relay ships none, so that the terms are mine, complete, and only present where a platform requires them.

#### Acceptance Criteria
1. While the relay serves its privacy policy and a deployment contributes terms (its own terms sections, or terms clauses for a provider it contributes), the relay server shall serve `/terms`, composed in this order: one group per applying provider that has terms clauses, in the order Requirement 3 criterion 1 gives providers; then each deployment's own terms sections, in wrapper installation order; then a closing with the latest date on which any text the page shows was written.
2. While no deployment contributes terms, the relay server shall serve no terms page and shall answer `/terms` as it answers a path it does not offer.
3. The relay package shall ship no terms text and no operator commitment of its own: no end-user terms, no breach-notice promise, no process for access, export or deletion requests, and no legal entity, governing law or jurisdiction shall appear on either page unless a deployment contributes it.
4. The terms page shall show the operator's support contact and link the privacy policy.

### Requirement 8: Deployment Contributions Through the Extension Seam
**Objective:** As someone running a hosted relay, I want my wrapper to add provider sections, operator sections and terms clauses to the relay's own pages, so that one policy and one terms page cover everything my deployment does without forking the relay's pages.

#### Acceptance Criteria
1. The extension seam shall let a wrapper contribute: provider groups for the privacy policy, each with the platform's name, its sections, its retention statement and whether it is announced; operator sections for the privacy policy (such as the operator's commitments on breach notice and on access, export and deletion requests, its legal entity, jurisdiction or sub-processors); and terms: its own terms sections and, for a provider it contributes, that provider's terms clauses. Each contribution shall carry headings, plain-text content and the date its text last changed.
2. If a wrapper's contribution is malformed (an empty or overlong heading or text, a heading repeated within one part, a platform name equal to a built-in provider's or to another contribution's, a provider group without a retention statement, or a missing or invalid date), the relay server shall refuse to start, naming the wrapper and the reason, as it refuses other wrapper errors.
3. The relay server shall read contributions once at start-up, so that they cannot change between requests.
4. A wrapper that contributes nothing shall leave the pages exactly as they would be without it.
5. The seam shall advance its version by one, recorded with a literal history in the relay changelog, which shall call the change out as breaking for every wrapper; a wrapper declaring any other version shall still be refused at start-up.
6. Built-in providers shall supply their sections in the same shape that wrappers contribute, so that a provider registered later supplies its sections without a second composition.

### Requirement 9: Deploy Contract, Documentation and Records
**Objective:** As an operator and as the maintainer, I want the new settings, the pages and their composition documented and bound to the code, and the specs this changes amended, so that a deployment can rely on them and later specs build on them.

#### Acceptance Criteria
1. The deploy contract's variable table shall gain the announce setting and an optional operator terms address (an `https` address, like the policy address), each with whether it is required, its default, whether it is secret and its meaning; the operator name and support contact rows shall say they are also required while any provider section applies; the operator name, support contact, privacy policy address and terms address shall be accepted whether or not a target is configured; `/terms` shall join the relay's reserved paths; and, since every change is additive, the deploy-contract version shall not move.
2. The relay documentation's privacy section shall describe the composition and its order, announcing and the announced statement, the terms page and that the relay ships no terms of its own, the addresses to give a platform's application (`<public address>/privacy`, and `<public address>/terms` where the deployment contributes terms), what a deployment must contribute (its operator sections, including any breach-notice and request-handling commitments its platforms require, a group for each provider it adds, and its terms), and that the text is not legal advice.
3. The relay documentation shall state the operator's obligations this feature adds: to keep every fixed statement true, publishing their own policy instead where their own additions would make one (such as the AI statement) untrue, and to contribute the terms and the operator commitments (breach notice, handling of access, export and deletion requests) that the platforms they connect to require.
4. The relay documentation's seam section shall document the contribution surface and the new seam version. No test this feature adds shall read the documentation, the changelog or a spec, and where an existing test reads a part of one of them that this feature changes, the test shall be removed rather than updated, and the amendments shall name each removed test.
5. The connectors documentation shall name the default relay's terms address beside its privacy policy address.
6. The pages and documentation shall use Strava's name only to name the service, describe the feature only as compatible with Strava, name no AI product or agent, and carry no Garmin section text, nothing from Garmin's developer documentation and no statement about any application or agreement with Garmin.
7. When this feature lands, the relay-server, strava-publish and relay-intervals specs shall each record an amendment at its next free number stating what moved: the seam's contributions and version, the new rows and reserved path, and pages served without a target (relay-server); the policy text moved into the composition, the terms link on every page while terms exist, and the policy page served while the database is unreachable (strava-publish); and the composition and the intervals.icu section delivered here (relay-intervals).
