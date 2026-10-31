# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete whose workouts are seen by others on
Strava, where an automatic sync usually lands each activity first under a
generic name. They want each workout's post (the title and description
fitdocs composes for the page) on that Strava activity, and a link to it
from the workout page. Strava's API needs a registered application, which
needs a paid Strava subscription since 2026-06-01, and its client secret
cannot ship in an open-source CLI.

**Current situation.** Nothing in fitdocs talks to Strava. The connector
framework reserves the browser-consent authentication style and
`fitdocs connect` refuses it. publish-core (Phase 14, wave 1) gives
`fitdocs publish`, the closed outcome vocabulary, the target contract, the
ledger and the page's links region, but no target. relay-server (wave 1)
gives a self-hostable relay with operator-minted relay tokens, principals,
an envelope with closed relay codes, one storage interface on two backends,
a deploy contract, and the fitdocs relay connector with `fitdocs connect`
and `fitdocs disconnect`, but no target. Strava's API Agreement and API
Policy (both in force since 2026-06-01) bound what an application may store,
show and re-expose.

**What should change.** A Strava target that reaches Strava only through a
relay holding one Strava application. `fitdocs connect` for a Strava
instance opens the relay's connect page, where the athlete connects their
Strava account to their relay principal, and waits until the relay reports
the connection made. `fitdocs publish --to <instance> --yes` asks the relay,
for each opted-in page whose post is new or changed, to post it: the relay
finds the athlete's activity by start time on every publish, with
activity-identity's strict one-to-one rule, and sets its name and
description; when none exists and the instance enables uploads, it uploads
the page's activity file once instead. Nothing the Strava API returns
leaves the relay: fitdocs receives only outcome codes, and the page links
to the relay's `/go/<publication id>` address, which finds the activity at
click time. Strava tokens are stored encrypted and rotate atomically;
disconnecting, a Strava-side revocation or deleting the principal removes
them at once. The relay counts its Strava calls against the application's
shared limits. The relay serves the privacy policy and consent text, and
everything is worded to Strava's brand rules.

Source: `.kiro/specs/strava-publish/brief.md`; Phase 14 of
`.kiro/steering/roadmap.md` (wave 2, parallel with `intervals-publish`).
Dependencies: `publish-core`, `relay-server`; upstream rule from
`activity-identity`. Downstream: `relay-intervals` reuses the relay's
connect machinery. Extends `connectors`, `relay-server`,
`activity-identity`, and the steering. The website is not edited by any
Phase 14 spec; its copy is recorded as a follow-up for the next release.

## Introduction

This feature adds the first target that publishes through a relay. It has
two halves that meet only at the relay's envelope: the relay side (connect,
token custody, resolution and writes on Strava, the link redirect,
revocation, the call budget, the pages) and the fitdocs side (the Strava
connector kind, its `connect`, `disconnect` and publish behaviour).

Terms used below (publish-core's and relay-server's terms keep their
meaning):
- A **Strava instance** is a configured connector instance of the built-in
  Strava connector. It is a publish target.
- Its **bound relay instance** is the relay instance (relay-server) its
  settings name. The Strava instance reaches the relay at that instance's
  URL.
- A **connection** is the relay's authorization, from one Strava account,
  to update that account's activities on behalf of one principal. A
  principal holds at most one Strava connection.
- A **connect session** is one attempt to make a connection, started from
  `fitdocs connect`; it carries a short **user code**, shown both in the
  terminal and on the connect page, and a private **poll secret**.
- A **connection token** is the relay token the relay issues to a Strava
  instance when its connection completes. It belongs to the same principal
  as the relay token that started the session.
- The **match facts** of a page are what publish-core hands a target about
  the page's activity: its sport, its start time with offset, its elapsed
  time and its distance.
- The **strict rule** is activity-identity's strict evidence tier of the
  match rule: the same sport, starts within one second, and distances
  within the strict tolerance or, where a distance is absent, elapsed times
  within the strict tolerance.
- The **link** of a page on a Strava instance is the relay address
  `<bound relay URL>/go/<publication id>`, shown as "View on Strava".
- **Strava Data** is anything the Strava API returns, as Strava's API
  Agreement defines it; an activity identifier is Strava Data.
- The **budget** is the relay's own count of its Strava calls against the
  application's shared rate limits.

## Boundary Context

- **In scope**:
  - on the fitdocs side: the built-in Strava connector and its settings
    (the bound relay instance and the upload opt-in); the browser-consent
    authentication style made driven for it; `fitdocs connect` with its
    `--no-browser` option for a Strava instance; `fitdocs disconnect` for
    a Strava instance; the publish operation that talks to the relay; the
    code mapping;
  - on the relay side: the connect session, the connect page and Strava's
    authorization callback; encrypted, rotating token custody with key
    rotation; resolution by start time with the strict rule; the name and
    description update and the single upload with status polling; the
    `/go/` redirect; the disconnect route, the deauthorization webhook and
    its operator commands; the call budget; the privacy, consent and
    result pages; the storage operations, migrations and conformance tests
    they need; the deploy-contract variables;
  - the shared modules pinned into the relay (publish-core's outcome
    vocabulary, the Strava wire format, the strict rule) and the
    activity-identity extraction that makes the rule shareable;
  - the documentation, network statements, steering and changelog changes
    these make true.
- **Out of scope**: reading anything from Strava for display, storage, the
  index or a page (there is no Strava pull); fields beyond name and
  description (gear, type, visibility, tags), photos and media; deleting
  activities; composing posts, the opt-in, the publish ledger, the links
  region and `fitdocs publish` itself (publish-core); relay tokens,
  principals, the envelope, the deploy contract's existing rows and the
  relay connector (relay-server); hosting or operating any relay; asking
  Strava for an athlete-capacity review; charging for the feature; any edit
  to the website's content. Neither `CONTRACT_VERSION` nor `DOC_VERSION`
  changes: the page contract and layout stay publish-core's.
- **Adjacent expectations**: publish-core hands the target one request per
  page with the publication id, the post and the match facts, keeps the
  ledger and writes the links region, and exposes a single-attempt request
  mode in the transport; relay-server provides the relay token, the
  envelope and its codec, the relay's token and client rate limits, the
  storage interface with its extension rule and conformance suite, the
  deploy contract's variable table, the pinned-copy cross-check, and the
  relay connector whose URL and token a Strava instance relies on;
  activity-identity owns the match rule and its tolerances;
  `intervals-publish` (parallel) owns `PUT` in fitdocs's transport, which
  this feature does not need because Strava's update happens inside the
  relay. A relay's operator owns their own Strava application, its
  callback domain and its subscription.

## Requirements

### Requirement 1: Strava Target Instances
**Objective:** As an athlete who uses a relay, I want to configure a Strava publish target that names the relay instance it goes through, so that fitdocs knows which relay holds my Strava connection and nothing in fitdocs talks to Strava directly.

#### Acceptance Criteria
1. The fitdocs CLI shall provide a built-in Strava connector whose instances are publish targets that resolve, annotate and push activities, authenticate by browser consent at a relay, and reach Strava only through their bound relay instance.
2. A Strava instance shall take a required `relay` key naming a configured relay instance and an optional `upload` key, a boolean that defaults to false.
3. If a Strava instance's `relay` key is missing, is not a string, or names no configured relay instance, or its `upload` key is not a boolean, the fitdocs CLI shall stop with a configuration error naming the settings file, the instance and the key, before any network request.
4. The fitdocs CLI shall send every request for a Strava instance to its bound relay instance's URL, and the fitdocs source shall name no Strava host.
5. The fitdocs CLI shall keep a Strava instance's connection token in the existing per-user credential store under that instance's own name, overridable from that instance's own environment variable exactly as a relay token is.
6. When `fitdocs publish --targets` lists a Strava instance, the fitdocs CLI shall show it as ready while a connection token is stored or its environment variable is set and as not connected otherwise, and shall make no request.
7. The Strava instance's link label shall be "View on Strava".
8. The fitdocs CLI shall make no request for a Strava instance during `fitdocs pull`, and a bare `fitdocs pull` shall not select a Strava instance.

### Requirement 2: Connecting Strava from the CLI
**Objective:** As an athlete, I want `fitdocs connect` for my Strava instance to open my relay's connect page and wait until the connection is made, so that I connect my Strava account once, without registering an application of my own.

#### Acceptance Criteria
1. When `fitdocs connect NAME` runs for a Strava instance, the fitdocs CLI shall first resolve the bound relay instance's relay token; if none is stored and its environment variable is unset, it shall make no request, name the relay instance and the command that connects it, and exit with the failure code.
2. When a relay token is available, the fitdocs CLI shall make one connect-start request to the relay with it; if the relay answers any code other than started, cannot be reached, or answers with something that is not a valid envelope, the fitdocs CLI shall print the instance, the relay code, its fitdocs-written explanation and the next step, store nothing, and exit with the failure code.
3. When the relay answers started, the fitdocs CLI shall print the connect page's address, which fitdocs composes from the bound relay URL and the validated user code, the user code, an instruction to continue only if the page shows the same code, and the time remaining; and unless `--no-browser` is given, it shall ask the operating system to open that address in a browser.
4. The fitdocs CLI shall print the user code only after it matches the documented user-code format and shall print no other value the relay returned; if a started answer's user code, poll secret, poll interval or expiry is outside the documented format or range, it shall treat the answer as malformed.
5. While the connection is pending, the fitdocs CLI shall poll the relay at the interval the relay stated, one request per poll, never repeating a poll request automatically.
6. When the relay answers granted with a token in the documented relay-token format, the fitdocs CLI shall store it as the Strava instance's connection token, replacing any stored one atomically, report the instance, the credentials file's location and any environment variable that will override it, and exit with the success code.
7. If the relay answers refused, expired, or any code other than pending and granted, or a poll cannot reach the relay or returns something that is not a valid envelope, or the session's stated expiry passes, the fitdocs CLI shall stop polling, print the relay code with its fitdocs-written explanation and next step, store nothing, and exit with the failure code.
8. If the user interrupts the connect, the fitdocs CLI shall stop polling, store nothing, and exit with the interrupt code.
9. The fitdocs CLI shall never print, store or write the poll secret, and shall prompt for nothing while connecting a Strava instance, so that the connect needs no interactive standard input.
10. If `--no-browser` is given for an instance that is not a Strava instance, or `--register` or `--email` is given for a Strava instance, the fitdocs CLI shall exit with the configuration-error code before any request.

### Requirement 3: The Relay's Connect Page and Strava Authorization
**Objective:** As an athlete, I want the relay's connect page to show me what I am agreeing to and send me to Strava's own authorization page, so that I grant access knowingly and the connection lands on my own relay principal only.

#### Acceptance Criteria
1. When a connect-start request authenticates with a valid relay token, the relay server shall start a connect session bound to that token's principal and to the Strava target, with a user code, a poll secret, a poll interval and an expiry of at most ten minutes, and shall answer started with them.
2. When a browser opens the connect page with a live session's user code, the relay server shall serve a fitdocs-written page, outside the envelope, showing the user code, an instruction to continue only if the user's own terminal shows the same code, the consent text, the operator's support contact, a link to the privacy policy, and a "Connect with Strava" control that links to Strava's authorization page.
3. The relay server shall request exactly the permission to read all of the athlete's activities, private ones included, and the permission to write activities, and shall attach to each authorization an unguessable, single-use state value that only that session's callback accepts.
4. The relay server shall serve each connect session to one browser only: the first browser to open its page claims it, a later browser gets a fitdocs-written page saying the code is in use elsewhere, and the authorization callback is accepted only from the claiming browser.
5. If the connect page is opened with a user code that is malformed, unknown, expired or already used, the relay server shall serve a fitdocs-written page saying so, with the next step, and shall change nothing.
6. When Strava's callback brings an authorization code for a live session and the granted permissions include both requested permissions, the relay server shall exchange the code once, store the resulting tokens as the session principal's Strava connection, mark the session granted, and serve a fitdocs-written page telling the user to return to the terminal.
7. If the callback reports that the athlete declined, or the granted permissions lack either requested permission, or the code exchange fails, the relay server shall store no token, mark the session refused, and serve a fitdocs-written page with the next step, never showing any text Strava returned.
8. When a poll presents a session's poll secret with a relay token of the session's principal, the relay server shall answer pending until the session is granted, refused or expired; on the first poll after the grant it shall issue a new relay token for that principal as the connection token, revoke the principal's earlier Strava connection token if any, and answer granted with the new token exactly once.
9. If a poll presents a relay token of a different principal, or an unknown poll secret, the relay server shall answer as for an unknown session and change nothing.
10. When a Strava account already connected to another principal is connected again, the relay server shall move the connection to the new principal and delete the earlier connection, its connection token and its link records in the same transaction, so that one Strava account is connected to at most one principal.
11. When a principal that holds a Strava connection connects again, the relay server shall replace the connection; where the newly connected Strava account differs from the earlier one, it shall also delete the principal's earlier link records.

### Requirement 4: Custody of Strava Tokens
**Objective:** As an athlete who hands the relay my Strava authorization, I want my tokens encrypted, rotated safely and never exposed, so that a copy of the relay's database yields nothing usable and a concurrent refresh never loses my only valid token.

#### Acceptance Criteria
1. The relay server shall store a connection's Strava access and refresh tokens only under authenticated encryption with a key taken from the deploy environment, each ciphertext bound to its principal, target and field, so that a ciphertext moved to another row or field fails to decrypt.
2. The relay server shall accept several encryption keys, encrypting with the first and decrypting with any, and the relay package shall provide an operator command that re-encrypts every stored token under the first key and reports how many it re-encrypted and how many no configured key can read.
3. When a connection's access token expires within a documented margin, the relay server shall refresh it before use, and shall allow at most one refresh of a connection in flight at any time, so that no request uses or stores a refresh token that Strava has already replaced.
4. When a refresh succeeds, the relay server shall replace the connection's tokens in one atomic operation that succeeds only if the connection has not changed since that refresh began, and a request waiting on that refresh shall use the new tokens rather than refresh again.
5. If Strava refuses a refresh as invalid, the relay server shall delete the connection and its connection token in one transaction unless the connection changed meanwhile; if the refresh fails for a transient reason, it shall leave the stored tokens unchanged.
6. The relay server shall send a Strava token only in a request header, never in an address, and only to the configured Strava addresses, never to the target of a redirect.
7. If a connection's stored tokens cannot be decrypted with any configured key, the relay server shall treat the principal as not connected.
8. The relay server shall store no Strava athlete identifier; it shall keep only a keyed hash of it, sufficient to act on Strava's deauthorization events.
9. The relay documentation shall state how to generate an encryption key, how to rotate keys without downtime, and that changing the token-hashing secret also breaks the match between deauthorization events and stored connections.

### Requirement 5: Publishing a Post to Strava from the CLI
**Objective:** As an athlete, I want `fitdocs publish --to <strava instance> --yes` to hand each new or changed post to my relay and report one fitdocs code, so that the post lands on my Strava activity and nothing Strava says comes back to me.

#### Acceptance Criteria
1. When `fitdocs publish --yes` sends a post to a Strava instance, the fitdocs CLI shall send the relay one publish request carrying only the publication id, the activity's sport, its start time with offset, its elapsed time and distance (each absent value sent as absent, never as zero), and the post's title and description, and no activity file.
2. If neither the elapsed time nor the distance is known, the fitdocs CLI shall make no request for that page and return the activity-facts-missing code.
3. If the post's title or description exceeds the documented length, the fitdocs CLI shall make no request for that page and return the rejected code.
4. When the relay answers that no activity matches, the fitdocs CLI shall: where the instance's uploads are enabled and the page's activity file is in the archive and within the documented size, send the relay one upload request carrying the same fields and the file; where uploads are disabled, return the not-found code; where the file is absent or unreadable, return the activity-file-missing code; and where the file exceeds the documented size, return the rejected code without sending it.
5. Every request the fitdocs CLI sends to a relay shall be attempted exactly once, whatever the answer, so that the transport's data-mode retry never applies to it.
6. The fitdocs CLI shall turn each relay answer into exactly one publish-core code that a target may return, by a documented table, and shall accept a publish outcome from the relay only when it is a member of publish-core's vocabulary and of the outcomes that route may answer, treating any other answer as malformed.
7. If the relay cannot be reached, or answers with something that is not a valid envelope, or reports its own unexpected failure, the fitdocs CLI shall return the unavailable code for a publish request and the unconfirmed code for an upload request, because an upload's result is then unknown.
8. When the code is posted or uploaded, the fitdocs CLI shall return the link `<bound relay URL>/go/<publication id>`, composed by fitdocs, and shall return no link with any other code.
9. The fitdocs CLI shall print, log and write nothing a relay returned other than the codes, and shall never receive, hold or write a Strava identifier.

### Requirement 6: Finding the Strava Activity on Every Publish
**Objective:** As an athlete, I want the relay to find my activity afresh on every publish, by fitdocs's own strict rule, so that a post never lands on the wrong activity and no lasting map of my pages to Strava exists.

#### Acceptance Criteria
1. On every publish and upload request, the relay server shall list the athlete's Strava activities whose start lies within a documented window around the page's start, and shall keep no record that maps a page or a publication to a Strava activity.
2. The relay server shall decide that a listed activity is the page's activity only by the strict rule, comparing Strava's sport type through a documented table of the fitdocs sports it corresponds to; an activity whose sport type that table does not name shall never match.
3. The relay server shall apply the strict rule through a byte-identical copy of the fitdocs module that fitdocs's own match rule uses, so that the relay and fitdocs cannot decide one pair differently.
4. When exactly one listed activity matches, the relay server shall treat it as the page's activity; when more than one matches, it shall answer the ambiguous outcome and change nothing; when none matches on a publish request, it shall answer the not-found outcome and change nothing.
5. If a listing returns its documented maximum number of activities, the relay server shall answer the ambiguous outcome and change nothing, rather than decide from a listing that may be incomplete.

### Requirement 7: Writing the Post on Strava
**Objective:** As an athlete, I want the relay to set only my activity's name and description, and to create an activity only once when none exists, so that a publish never duplicates or damages my Strava history.

#### Acceptance Criteria
1. When exactly one activity matches, the relay server shall set that activity's name to the post's title and its description to the post's description in one update, and shall answer the posted outcome when Strava accepts the update.
2. If an update fails transiently, the relay server shall repeat that identical update at most once, within the budget, and shall make no other repeat of any Strava write.
3. When an upload request finds no matching activity, the relay server shall create the activity by uploading the file exactly once, with the post's title and description and the publication id as its external identifier, and shall never repeat the upload.
4. After uploading, the relay server shall poll the upload's status no more often than once per second until it reports a created activity, reports a failure, or a documented deadline passes, and shall then answer the uploaded outcome, resolve again as in 7.5, or answer the unconfirmed outcome, respectively.
5. If Strava reports the upload as failed, the relay server shall resolve the activity again by listing, never by reading the failure's text: one match is updated as in 7.1, several answer the ambiguous outcome, and none answers the rejected outcome.
6. The relay server shall change no field of a Strava activity other than its name and description, and shall delete nothing on Strava.
7. The relay server shall finish each publish request and each upload request within a documented deadline shorter than fitdocs's request timeout, answering the unavailable outcome (publish) or the unconfirmed outcome (upload, once the file was sent) when that deadline passes.

### Requirement 8: One fitdocs Code for Every Answer
**Objective:** As an athlete, I want every Strava answer turned into one fitdocs code with fitdocs's own explanation, so that I always know what happened without seeing anything Strava said.

#### Acceptance Criteria
1. The relay server shall map each class of Strava answer (an authentication refusal, a permission refusal, a missing activity, a rate limit, another client error, a server error, a timeout or network failure, an answer it cannot read, and an upload failure) to one publish-core code by a documented table that depends on the step (listing, update, upload, status poll, token refresh), and shall answer fitdocs with that code alone.
2. The relay server shall answer a publish or upload request from a principal with no usable Strava connection with the not-connected outcome.
3. An automated test at the relay's Strava client seam shall pin that table row by row against scripted Strava answers, and no test shall make a request to Strava.
4. The fitdocs CLI's Strava target shall map every relay code it can receive to one publish-core code by a documented table, pinned by tests over a scripted transport.

### Requirement 9: The Strava Call Budget
**Objective:** As the operator of a relay whose one Strava application serves every connected athlete, I want the relay to count its own Strava calls against the application's limits and stop before Strava does, so that one run cannot exhaust the limit for everyone and nothing is retried past the budget.

#### Acceptance Criteria
1. The relay server shall take the application's overall and non-upload limits, each per fifteen minutes and per day, from the deploy environment, defaulting to Strava's published defaults.
2. Before each Strava call, the relay server shall count that call in the database against every limit it draws on, in windows aligned to Strava's (quarter hours, and days from midnight UTC), and shall not make a call that would exceed any of them.
3. Before an upload, the relay server shall reserve, in one operation, the upload and the most status polls and follow-up calls its flow may make, and shall not upload when that reservation fails.
4. If a call is not made because the budget is spent, or Strava answers that a limit was reached, the relay server shall answer the rate-limited outcome and make no further Strava call for that request, and where Strava answered it, shall record that window as spent.
5. The relay server shall keep a documented share of each non-upload window that resolving links may not use, so that following links cannot spend what publishing needs.
6. The relay server shall keep the budget's counts in the configured database only, so that a restart neither resets nor loses them.
7. The relay server shall let no single principal use more than a documented share of any window, so that one athlete's run cannot exhaust a limit for every athlete.

### Requirement 10: The "View on Strava" Link
**Objective:** As an athlete reading a workout page, I want its "View on Strava" link to open the activity on Strava, so that I can reach the post while neither the page nor fitdocs ever holds a Strava identifier.

#### Acceptance Criteria
1. When a publish or upload request lands, the relay server shall record the publication id with its principal and the page's match facts, and nothing from Strava.
2. When a browser requests `/go/<publication id>` for a recorded publication whose principal is connected, the relay server shall resolve the activity at that moment by the same listing and strict rule a publish uses, and redirect the browser to that activity's page on Strava with a temporary redirect.
3. If the publication id is malformed or unknown, its principal is not connected, or no single activity matches, the relay server shall serve a fitdocs-written not-found page and redirect nowhere.
4. The relay server shall serve the link without a relay token, limit link requests per client, and serve a fitdocs-written try-later page when the client limit or the budget refuses.
5. The relay server shall answer every link request with caching and referrer disabled, and shall not record the Strava activity it resolved.
6. If a publish or upload request carries a publication id the relay already records for another principal, the relay server shall answer the rejected outcome and change nothing.

### Requirement 11: Disconnecting and Revocation
**Objective:** As an athlete, I want disconnecting from the CLI, revoking access on Strava, or the operator deleting my principal to remove my Strava tokens at once, so that the relay can no longer act on my account the moment I withdraw.

#### Acceptance Criteria
1. When `fitdocs disconnect NAME` runs for a Strava instance with a stored connection token, the fitdocs CLI shall make exactly one disconnect request with that token; when the relay answers success, or answers that the token is unknown or revoked, it shall remove the instance's credentials file, report the code, and exit with the success code.
2. If that request cannot reach the relay, or the relay answers any other code, the fitdocs CLI shall keep the credentials file, print the code with its fitdocs-written explanation and the next step, and exit with the failure code.
3. Where `--local-only` is given for a Strava instance, the fitdocs CLI shall make no request, remove the instance's credentials file, and state that the Strava connection stays at the relay until it is disconnected there or access is revoked in Strava's settings.
4. While a Strava instance has no stored connection token, `fitdocs disconnect` shall report that there is nothing to disconnect, make no request, and exit with the success code.
5. When the relay receives a disconnect request from a principal, it shall ask Strava once to revoke the connection's authorization, then delete the connection's tokens, its connection token and its link records in one transaction whatever Strava answered, and shall answer success, also when the principal held no connection.
6. When Strava's deauthorization event for a connected account reaches the relay's webhook, the relay server shall delete that account's connection, tokens, connection token and link records at once, and answer within two seconds; it shall acknowledge every other event without storing anything from it.
7. The relay server shall accept webhook requests only at an address that carries the configured webhook secret, compared in constant time, shall answer Strava's subscription validation only when its verification token equals that secret, and shall answer any other webhook request with not-found.
8. When a principal is deleted, the relay server shall delete its Strava connection, tokens and link records in the same transaction.
9. The relay package shall provide operator commands that create, show and delete the application's one webhook subscription, printing only fitdocs-written states.
10. The relay server shall delete a connection's data immediately in each case above, which is within Strava's thirty-day limit.

### Requirement 12: Nothing from Strava Crosses the Relay Boundary
**Objective:** As an athlete and as the maintainer, I want the relay to keep everything Strava returns inside the request that needed it, so that no Strava Data reaches fitdocs, a log, or a lasting record.

#### Acceptance Criteria
1. Every relay answer to fitdocs shall carry only a relay code, a publish-core outcome and the fields its documented route defines, and no Strava response body, header, identifier, address or text.
2. The relay server shall never log a Strava response body, header, identifier or address, an authorization code, a state value, a Strava token or an encryption key; its log records about Strava calls shall carry only fitdocs-defined classifications.
3. The relay server shall store no Strava Data beyond the encrypted tokens of live connections: no activity, activity identifier, athlete identifier, profile or cache; its only lasting records for the Strava target shall be the encrypted tokens, the keyed account hash and fitdocs's own publication ids and match facts.
4. Every page the relay serves for this feature shall be fitdocs-written, shall interpolate only values fitdocs generated or validated, and shall show no text Strava returned.
5. The relay's Strava routes shall accept only fitdocs's connect, poll, publish, upload and disconnect requests, the link, the authorization callback and the webhook; they shall never forward a caller's request to Strava, and shall never use one principal's Strava tokens for another principal.

### Requirement 13: Relay Configuration for Strava
**Objective:** As a relay operator, I want the Strava target configured from the environment like everything else in the deploy contract, and absent until I configure it, so that a relay without a Strava application behaves exactly as before.

#### Acceptance Criteria
1. The relay package shall append to the deploy contract's variable table the Strava application's client id and client secret, the webhook secret, the encryption keys, the relay's public address, the operator's name and support contact, an optional privacy-policy address, the Strava addresses and the rate limits, each with whether it is required, its default, whether it is secret and its meaning.
2. The relay server shall offer the Strava target exactly when the Strava client id is configured; the other required Strava variables shall then be required, and if any is absent or invalid, the relay server and its commands shall refuse to start, naming the variable but never its value.
3. While the Strava target is not configured, the capabilities endpoint shall list no Strava target, every Strava envelope route shall answer not-offered, and every Strava page and webhook address shall answer not found, with every other relay behaviour unchanged.
4. When the Strava target is configured, the capabilities endpoint shall list `strava` among its targets.
5. The Strava addresses shall be configurable, defaulting to Strava's current addresses, so that the relay can move to Strava's announced new API address without a code change.
6. The relay documentation shall state that a self-hosted relay needs its own Strava application, registered under the operator's own Strava subscription with the relay's own callback domain, and may never use another operator's application credentials.

### Requirement 14: Storage for the Strava Target
**Objective:** As the maintainer, I want every new piece of relay state to go through the one storage interface and pass the conformance suite on both backends, so that an operator's choice of database never changes how custody behaves.

#### Acceptance Criteria
1. Every operation this feature adds to the relay's storage interface (connections and their token rotation, connection-token issuance, link records and the budget) shall join that interface and the conformance suite, and shall pass the suite on SQLite and PostgreSQL before it lands.
2. Each such operation shall be atomic on both backends: concurrent refresh claims on one connection shall leave exactly one holder, a token replacement shall never overwrite a newer one, a budget charge shall never be counted twice nor allowed past its limit, and connecting one Strava account to two principals at once shall leave it connected to exactly one.
3. The schema changes this feature needs shall be one numbered change pair, identically named for both backends and applied by the existing migration command.
4. Every row this feature adds that belongs to a principal shall be deleted with that principal.

### Requirement 15: Code Shared with fitdocs
**Objective:** As the maintainer, I want the relay to use fitdocs's own outcome vocabulary, wire format and match rule byte for byte, so that the two sides can never drift apart.

#### Acceptance Criteria
1. The relay package shall receive publish-core's outcome vocabulary, the Strava wire format and the strict rule as byte-identical copies of standard-library-only fitdocs modules, added to the existing pinned-copy cross-check, which shall fail on any drift.
2. The strict rule shall live in a standard-library-only fitdocs module that fitdocs's own match rule uses, with every existing match-rule result unchanged.
3. The relay server shall emit a publish outcome only when it is a member of the pinned vocabulary and of the outcomes its route may answer.
4. The relay code vocabulary shall gain the connect answers (started, pending, granted, refused and expired) by appending them, each with a fixed fitdocs-written explanation and status.

### Requirement 16: Privacy Policy, Consent, Support Contact and Strava Wording
**Objective:** As an athlete deciding whether to connect, and as the maintainer bound by Strava's terms, I want the relay's privacy policy, consent text and support contact published with the code and every Strava mention worded to Strava's rules, so that the obligations are met by any operator who runs the relay.

#### Acceptance Criteria
1. The relay server shall serve a privacy policy page that states what the relay receives, stores, sends to Strava and deletes, and when, naming the operator and their support contact; the relay documentation shall name `<public address>/privacy` as the address for a Strava application's privacy-policy field, unless the operator configures another policy address, which the relay's pages then link instead.
2. The connect page shall show the consent text before the "Connect with Strava" control, stating what the relay will do with the athlete's Strava access and what it will never do.
3. Every page the relay serves for this feature shall show the operator's support contact.
4. The relay and fitdocs shall use Strava's name only to name the service, with exactly these brand phrases: "Connect with Strava" on the control that starts authorization, "View on Strava" on the link, and "Compatible with Strava" in documentation; no product or Strava application name of fitdocs or the relay shall contain Strava's name (the connector's id and display name name the service it reaches).
5. The repository's changelog and documentation shall describe the feature only as compatible with Strava, and this feature shall publish no announcement that references Strava.
6. The relay documentation shall state the operator's obligations: the consent and privacy pages, a support contact, notice of a breach within 24 hours, the application's athlete capacity (one athlete at first, up to ten on the owner's request, more only after Strava's review), and never charging for the feature.

### Requirement 17: Documentation, Network Statements and Steering
**Objective:** As a fitdocs user or relay operator relying on what the repository says, I want every statement about the network, credentials and the relay to stay true once Strava publishing exists, so that nothing published contradicts what the code does.

#### Acceptance Criteria
1. The connectors documentation shall describe the Strava connector: its settings, connecting with and without a browser, publishing and uploads, the link, disconnecting, what leaves the machine, the code mapping table, and the default relay's privacy policy address, describing the feature as compatible with Strava.
2. The relay documentation shall describe the Strava target: its variables, encryption keys and their rotation, the webhook commands, the routes and pages, the data held and when it is deleted, the policy and consent, the operator obligations, and the self-hosting note.
3. Every repository statement that lists the commands which make network requests shall name `fitdocs publish --yes`, and the connectors documentation's "What leaves your machine" shall name the host a Strava instance's publish requests go to (its bound relay's), whichever Phase 14 target lands first; an automated test shall pin each such statement.
4. The technology steering's network and credentials section shall state, in its own sentence, the requests `fitdocs connect`, `fitdocs disconnect` and `fitdocs publish --yes` make for a Strava instance, and the structure steering shall describe the strict rule's standard-library-only module and its pinned copy.
5. The `fitdocs` changelog's unreleased section shall record the Strava connector, `fitdocs connect --no-browser` and Strava disconnect, and the relay changelog shall record the Strava target, its variables, routes and storage changes.
6. This feature shall edit no website page, and shall record the site copy it makes stale or newly needs as a follow-up for the next release.
7. Every new or changed document shall pass every existing documentation, network-statement and neutral-scan guard, and no new document shall mention a hosting provider, an email provider or a deployment's infrastructure.
8. This feature shall not change the packaged agent skill, whose publishing section names no target.

### Requirement 18: An Optional, Maintainer-Gated Live Check
**Objective:** As the maintainer, I want a documented way to check the whole path against a real Strava application once, so that the scripted tests' picture of Strava is confirmed before release.

#### Acceptance Criteria
1. Where the maintainer explicitly approves it at implementation time, a documented live check shall connect, publish an update, follow the link and disconnect against the maintainer's own Strava application and account, stating beforehand that it writes to that real account.
2. The live check shall be optional, shall never run in the test suite or in CI, and shall record only fitdocs codes and fitdocs-written observations, never Strava Data.
