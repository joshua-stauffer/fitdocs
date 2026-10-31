# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who wants each workout's post on the
matching intervals.icu activity, as `intervals-publish` delivers it, but who
would rather not keep an intervals.icu personal API key in fitdocs: either
because they do not want to handle a key at all, or because their fitdocs
runs somewhere they would rather not keep one. They would connect
intervals.icu once, in a browser, to their relay, the same way they connect
Strava.

**Current situation.** `intervals-publish` (Phase 14, wave 2) makes the
intervals.icu connector a publish target with the athlete's personal API
key: it finds the page's activity by the recorded link, the pull record and
a listing matched with activity-identity's strict rule, sets the activity's
name and description, uploads the page's base file once when nothing exists
and uploads are enabled, maps every answer into publish-core's codes through
one table, and writes the direct activity link. `strava-publish` (wave 2)
builds a relay target with browser consent: connect sessions, the connect
page and callback, encrypted token custody, a call budget, revocation, and on
the fitdocs side the browser-consent authentication style, `fitdocs connect
--no-browser` and `fitdocs disconnect`. That machinery sits under the
relay's Strava package and in the Strava connector. intervals.icu offers
OAuth to applications it has approved; the maintainer's application request
is a maintainer action, and the OAuth flow does not work before approval.

**What should change.** An intervals.icu instance can take a relay route
instead of the direct one, chosen per instance, with direct the default.
`fitdocs connect` for a relay-routed instance opens the relay's intervals.icu
connect page and fitdocs holds no intervals.icu key. `fitdocs publish --to
<instance> --yes` behaves as on the direct route: the same order of finding
the activity, the same codes, the same direct activity link; the only
difference is that the relay makes the intervals.icu calls. The relay reuses
strava-publish's connect machinery for a second provider without a second
copy of it, and runs intervals-publish's resolution, write and answer rules
from one shared definition, so the two routes cannot drift apart.
Disconnecting revokes the relay's intervals.icu token. Implementation waits
on intervals.icu approving the maintainer's OAuth application.

Source: `.kiro/specs/relay-intervals/brief.md`; Phase 14 of
`.kiro/steering/roadmap.md` (wave 3, last). Dependencies: `strava-publish`
(the relay's connect machinery), `intervals-publish` (the semantics),
`relay-server`, `publish-core`. Extends `connectors`, `strava-publish`,
`intervals-publish`, `intervals-connector`, `relay-server`, `publish-core`
and the steering. The website is not edited by any Phase 14 spec; its copy
is recorded as a follow-up for the next release.

## Introduction

This feature adds intervals.icu as a second relay target. On the fitdocs
side it adds a relay-routed intervals.icu connector kind and its connect,
publish and disconnect behaviour. On the relay side it adds the intervals.icu
provider to the connect machinery, the intervals.icu publish and upload
routes, the call budget and the deploy-contract variables. Between them it
moves the target-neutral parts of the Strava machinery to a place both
targets share, and moves the direct route's intervals.icu rules into a
shared module the relay runs as a pinned copy.

Terms used below (publish-core's, relay-server's, strava-publish's and
intervals-publish's terms keep their meaning):
- A **direct instance** is an instance of the intervals.icu connector
  (`intervals-publish`).
- A **relay-routed instance** is an instance of the built-in relay-routed
  intervals.icu connector. It is a publish target that reaches intervals.icu
  only through its **bound relay instance**.
- An instance's **route** is direct or relay, and is chosen by which of the
  two connectors the instance's table names.
- A **connection** is the relay's authorization, from one intervals.icu
  account, to read and write that account's activities on behalf of one
  principal. A principal holds at most one intervals.icu connection.
- The **connection token** is the relay token the relay issues to a
  relay-routed instance when its connection completes.
- The **known activities** of a page are the intervals.icu activities fitdocs
  already knows for it, in this order: the activity of the page's recorded
  link on the instance, then the activity the instance's pull record names
  for the page's files (the base file first, the other files only when the
  base file names none).
- The **strict rule**, the **pull record**, the **recorded link**, the
  **direct link**, a **Strava-imported activity**, an **update** and an
  **upload** mean what `intervals-publish` defines them to mean.
- The **answer table** is intervals-publish's table from an intervals.icu
  answer, by request kind and answer class, to a publish code.
- The **budget** is the relay's own count of its intervals.icu calls against
  the application's and each athlete's limits.

## Boundary Context
- **In scope**:
  - on the fitdocs side: the relay-routed intervals.icu connector and its
    settings (the bound relay instance and the upload switch); choosing the
    route per instance; keeping an instance's publish record across a route
    switch; `fitdocs connect`, `fitdocs publish --yes` and `fitdocs
    disconnect` for a relay-routed instance; the known activities it sends;
    the local refusals it makes before any request; the code mapping and the
    direct link;
  - on the relay side: the intervals.icu provider in the connect machinery
    (its page, its authorization, its callback); custody of intervals.icu
    tokens; finding the activity from the known activities and a listing
    matched by the strict rule; the update, the single upload and its
    confirmation; the call budget; the disconnect route; the intervals.icu
    consent text and privacy-policy sections; the deploy-contract variables;
  - the target-neutral connect machinery shared by both relay targets, on
    the relay and in fitdocs, without a second copy;
  - the shared module holding the direct route's intervals.icu rules, pinned
    into the relay;
  - the documentation, network statements, steering and changelog changes
    these make true; the implementation gate on intervals.icu's approval; an
    optional, maintainer-run live check.
- **Out of scope**: any change to the direct route's behaviour (its codes,
  its requests, its pull, its key check); planned workouts, calendar events,
  thresholds, wellness and pulling activities through the relay (the roadmap
  follow-on "Planned-workout push to intervals.icu" stays open, and
  push-planned-workout stays reserved and undriven); fields beyond name and
  description; deleting activities; composing posts, the opt-in, the publish
  ledger's format, the `published` region and `fitdocs publish` itself
  (publish-core); relay tokens, principals, the envelope, the storage
  interface's rule and the deploy contract's existing rows (relay-server);
  Strava's behaviour (strava-publish); applying for or operating the
  maintainer's intervals.icu application; hosting or operating any relay;
  any edit to the website's content. Neither `CONTRACT_VERSION` nor
  `DOC_VERSION` changes, and no command is added.
- **Adjacent expectations**:
  - publish-core hands the target one request per page with the publication
    id, the post, the match facts, the base file reference and the recorded
    link, keeps the ledger and writes the links region, and attempts a marked
    request exactly once;
  - intervals-publish owns the answer table, the activity identifier rule,
    the direct link, the listing window and match, the Strava-import rule,
    the upload's confirmation and the `publish_upload` meaning; this feature
    reuses them unchanged, from one shared definition;
  - strava-publish owns the browser-consent style, the connect session, the
    connect codes, token custody with key rotation, the relay-answer mapping
    and `fitdocs connect --no-browser`; this feature reuses them and moves
    their target-neutral parts to a shared place, keeping every Strava
    behaviour;
  - relay-server owns the relay token, the envelope, the storage interface
    and its conformance rule, and the deploy contract's variable table;
  - activity-identity owns the strict rule and its tolerances;
  - a relay's operator owns their own intervals.icu OAuth application, its
    approval and its registered callback address.

## Requirements

### Requirement 1: Choosing the Relay Route per Instance
**Objective:** As an athlete who would rather not keep an intervals.icu API key in fitdocs, I want to configure an intervals.icu publish target that goes through my relay, so that fitdocs publishes to intervals.icu without holding a key while every other intervals.icu instance stays direct.

#### Acceptance Criteria
1. The fitdocs CLI shall provide a built-in relay-routed intervals.icu connector, `intervals-relay`, whose instances are publish targets that resolve, annotate and push activities, authenticate by browser consent at a relay, and reach intervals.icu only through their bound relay instance.
2. The fitdocs CLI shall give an instance the relay route exactly when its `connector` key names the relay-routed connector, and shall leave every instance of the intervals.icu connector, including an instance named `intervals` with no `connector` key, on the direct route unchanged.
3. A relay-routed instance shall take a required `relay` key naming a configured relay instance and an optional `publish_upload` key, a boolean that defaults to false and means what it means on the direct route.
4. If a relay-routed instance's `relay` key is missing, is not a string or names no configured relay instance, or its `publish_upload` key is not a boolean, the fitdocs CLI shall stop with a configuration error naming the settings file, the instance and the key, before any request and any write.
5. If a relay-routed instance sets `wellness = true`, the fitdocs CLI shall stop with the configuration error it gives every connector that does not pull wellness.
6. The fitdocs CLI shall send every request for a relay-routed instance to its bound relay instance's URL, and shall make no request to intervals.icu for it.
7. The fitdocs CLI shall keep a relay-routed instance's connection token in the existing per-user credential store under the instance's own name, overridable from that instance's own token environment variable exactly as a Strava instance's is.
8. When `fitdocs publish --targets` lists a relay-routed instance, the fitdocs CLI shall show it as ready while a connection token is stored or its environment variable is set and as not connected otherwise, and shall make no request.
9. The relay-routed instance's link label shall be `intervals.icu`, the direct route's label.
10. The fitdocs CLI shall make no request for a relay-routed instance during `fitdocs pull`, and a bare `fitdocs pull` shall not select it.

### Requirement 2: Switching an Instance's Route
**Objective:** As an athlete who already publishes through one route, I want to move an instance to the other route without losing what fitdocs recorded, so that pages already posted keep updating the same activities and are never posted twice.

#### Acceptance Criteria
1. When an instance's connector changes from the intervals.icu connector to the relay-routed connector, or back, `fitdocs publish` shall keep reading and writing that instance's existing publish record, so that a page whose post already landed is reported unchanged and a changed post is sent to the activity it last landed on.
2. If an instance's existing publish record was written for a connector other than the instance's own or the other intervals.icu route, the fitdocs CLI shall refuse it as it refuses any publish-record mismatch, before any request and any write.
3. After a route switch, the fitdocs CLI shall report the instance as not connected until `fitdocs connect` connects it on its new route, and shall never use the other route's credential for it.
4. While a relay-routed instance has a pull record under its own name, left from an earlier direct configuration of that instance, the fitdocs CLI shall read it, read-only, as the direct route does, and shall never write, repair or create it.

### Requirement 3: Connecting intervals.icu Through the Relay from the CLI
**Objective:** As an athlete, I want `fitdocs connect` for my relay-routed instance to open my relay's intervals.icu connect page and wait until the connection is made, so that I connect intervals.icu once, in a browser, without an API key.

#### Acceptance Criteria
1. When `fitdocs connect NAME` runs for a relay-routed instance, the fitdocs CLI shall behave as strava-publish Requirement 2 criteria 1 to 9 state for a Strava instance, naming intervals.icu wherever those criteria name the service: it resolves the bound relay instance's token first, makes one connect-start request, prints the connect page's address, the user code, the same-code instruction and the time remaining, asks the operating system to open the address unless `--no-browser` is given, polls at the stated interval with one request per poll, and stores the connection token only when the relay answers granted.
2. If `--register` or `--email` is given for a relay-routed instance, the fitdocs CLI shall exit with the configuration-error code before any request.
3. When the connection token is stored, the fitdocs CLI shall record it as belonging to the relay-routed connector, so that no other connector's instance of the same name reads it as its own.

### Requirement 4: The Relay's intervals.icu Connect Page and Authorization
**Objective:** As an athlete, I want the relay's intervals.icu connect page to show me what I am agreeing to and send me to intervals.icu's own authorization page, so that I grant access knowingly and the connection lands on my own relay principal only.

#### Acceptance Criteria
1. When a connect-start request for the intervals.icu target authenticates with a valid relay token, the relay server shall start a connect session bound to that token's principal and to the intervals.icu target, with a user code, a poll secret, a poll interval and an expiry of at most ten minutes, and shall answer started with them.
2. When a browser opens the intervals.icu connect page with a live intervals.icu session's user code, the relay server shall serve a fitdocs-written page, outside the envelope, showing the user code, an instruction to continue only if the user's own terminal shows the same code, the intervals.icu consent text, the operator's support contact, a link to the privacy policy, and a control labelled "Connect to intervals.icu" that links to intervals.icu's authorization page.
3. The relay server shall request exactly the permission to write the athlete's activities, which includes reading them, and shall attach to each authorization an unguessable, single-use state value that only that session's callback accepts, and only from the browser that claimed the session.
4. If the connect page is opened with a user code that is malformed, unknown, expired, already used, or belongs to another target's session, the relay server shall serve a fitdocs-written page saying so, with the next step, and shall change nothing.
5. When intervals.icu's callback brings an authorization code for a live session, the relay server shall exchange the code once; when the exchange's answer grants activity-write permission and names the athlete, the relay server shall store the resulting token as the session principal's intervals.icu connection, mark the session granted, and serve a fitdocs-written page telling the user to return to the terminal.
6. If the callback reports that the athlete declined, or the exchange fails, or its answer lacks activity-write permission or does not name the athlete, the relay server shall store no token, ask intervals.icu once, when the budget allows, to revoke any token the exchange returned, mark the session refused, and serve a fitdocs-written page with the next step, never showing any text intervals.icu returned.
7. The relay server shall answer polls for an intervals.icu session as for a Strava session: pending until the session is granted, refused or expired; on the first poll after the grant, a new relay token for that principal issued as the connection token, the principal's earlier intervals.icu connection token revoked, and granted answered with the new token exactly once; a poll from another principal or with an unknown poll secret answered as for an unknown session.
8. When an intervals.icu account already connected to another principal is connected again, the relay server shall move the connection to the new principal, deleting the earlier connection and revoking its connection token in the same transaction, so that one intervals.icu account is connected to at most one principal.

### Requirement 5: Custody of intervals.icu Tokens
**Objective:** As an athlete who hands the relay my intervals.icu authorization, I want my token encrypted, never exposed and deleted once it no longer works, so that a copy of the relay's database yields nothing usable and no dead token lingers.

#### Acceptance Criteria
1. The relay server shall store an intervals.icu connection's token only under the authenticated encryption, configured keys and key rotation the Strava target uses, each ciphertext bound to its principal, target and field.
2. The relay server shall record no expiry and attempt no renewal for an intervals.icu token, and shall treat it as usable until intervals.icu refuses it.
3. When intervals.icu answers a call made with a connection's token as unauthorized, the relay server shall delete that connection and revoke its connection token in one transaction unless the connection changed since the token was read, and shall answer with the rejected-credentials outcome unless criterion 8.6 states otherwise.
4. The relay server shall send an intervals.icu token only in a request header, never in an address, and only to the configured intervals.icu addresses, never to the target of a redirect.
5. If a connection's token cannot be decrypted with any configured key, the relay server shall treat the principal as not connected.
6. The relay server shall store no intervals.icu athlete identifier; it shall keep only a keyed hash of it, sufficient to keep one account connected to at most one principal.
7. The relay's re-encryption command shall re-encrypt intervals.icu connections together with every other target's, and report one count of re-encrypted and one count of unreadable connections.

### Requirement 6: Publishing to intervals.icu Through the Relay from the CLI
**Objective:** As an athlete, I want `fitdocs publish --to <relay-routed instance> --yes` to hand each new or changed post to my relay with what fitdocs already knows about the activity, and report one fitdocs code, so that the post lands where the direct route would put it.

#### Acceptance Criteria
1. When `fitdocs publish --yes` sends a post to a relay-routed instance, the fitdocs CLI shall first gather the page's known activities: the activity of the page's recorded link on this instance, then the activity the instance's pull record names for the page's base file or, only when the base file names none, for the page's other files, each identifier in the direct route's identifier form, without repeats.
2. If the pull record names more than one activity in the tier it takes, the fitdocs CLI shall make no request and return the ambiguous code.
3. If no activity is known and the page records neither its distance nor its elapsed time, the fitdocs CLI shall make no request and return the activity-facts-missing code.
4. If the post's title or description exceeds the documented length, the fitdocs CLI shall make no request and return the rejected code.
5. The fitdocs CLI shall send the relay one publish request carrying only the publication id, the activity's sport, its start time with offset, its elapsed time and distance (each absent value sent as absent, never as zero), the post's title and description, and the known activities in their order, and no activity file.
6. When the relay answers that no activity matches, the fitdocs CLI shall: where the instance's pull record exists but could not be read, return the local-record-unreadable code whatever the upload setting and send nothing more; otherwise, where uploads are disabled, return the not-found code; where the page's base file is absent from the archive, unreadable, or does not hash to the digest it is archived under, return the activity-file-missing code; where it exceeds the documented size, return the rejected code without sending it; and otherwise send the relay one upload request carrying the same fields, without the known activities, and the file.
7. The fitdocs CLI shall send an upload request only after a definite not-found outcome for the same page in the same run, never after a malformed, failed or missing answer.
8. Every request the fitdocs CLI sends to a relay for a relay-routed instance shall be attempted exactly once, whatever the answer.
9. The fitdocs CLI shall turn each relay answer into exactly one code a target may return, by the documented table every relay-routed target uses, accepting a publish outcome only when it is a member of publish-core's vocabulary and of the outcomes that route may answer, and treating a posted or uploaded outcome that does not carry an intervals.icu activity identifier in the documented form as a malformed answer.
10. When the code is posted or uploaded, the fitdocs CLI shall return the direct link to the identified activity, built exactly as the direct route builds it, and shall return no link with any other code.
11. The fitdocs CLI shall print, log and write nothing a relay returned other than the codes and the direct link.

### Requirement 7: Finding the Page's Activity on the Relay
**Objective:** As an athlete, I want the relay to find my activity in the same order and by the same rule as the direct route, so that a post never lands on the wrong activity and choosing the relay route changes nothing about where it lands.

#### Acceptance Criteria
1. On a publish request, the relay server shall first update each known activity the request names, in its order, until one accepts the update, and shall treat an activity intervals.icu answers as not existing as absent for the rest of that request.
2. When no known activity accepts the update and the request carries neither a distance nor an elapsed time, the relay server shall answer the activity-facts-missing outcome and shall list nothing.
3. Otherwise, the relay server shall list the athlete's activities in one request over the range of local dates the direct route lists, and shall take as the page's activity the one listed activity, not imported from Strava and not already absent, that carries the publication id as its external identifier, or, when none does, the one such listed activity for which the strict rule holds between it and the page without comparing sports, comparing start times as instants.
4. The relay server shall apply the strict rule through a byte-identical copy of the fitdocs module that fitdocs's own match rule uses, and the listing window, the fields it reads and the one-to-one match through a byte-identical copy of the fitdocs module the direct route uses, so that the two routes cannot decide one listing differently.
5. If more than one listed activity carries the publication id, or none does and more than one satisfies the strict rule, the relay server shall answer the ambiguous outcome and change nothing, and shall never choose among them by order, recency or any other rule.
6. If no listed activity is the page's activity and a listed Strava-imported activity starts within one second of the page's start, compared as local wall-clock times when intervals.icu states only a local start, the relay server shall answer the not-updatable outcome and shall neither update nor upload.
7. When no known activity accepts the update and no listed activity is the page's activity, the relay server shall answer the not-found outcome on a publish request and change nothing.
8. If the listing's answer is not in intervals.icu's documented form, the relay server shall answer the unavailable outcome.
9. The relay server shall keep no record that maps a page, a publication or a known activity to an intervals.icu activity.
10. If a publish request names more than two known activities, names one twice, or names one outside the documented identifier form, the relay server shall refuse it as malformed and make no intervals.icu call.

### Requirement 8: Writing the Post on intervals.icu Through the Relay
**Objective:** As an athlete, I want the relay to set only my activity's name and description, and to create an activity only once when none exists, so that a publish through the relay never duplicates or damages my intervals.icu history.

#### Acceptance Criteria
1. When the page's activity is identified, the relay server shall send one update setting the activity's name to the post's title and its description to the post's description, an empty description set to empty, and shall answer the posted outcome with that activity's identifier when intervals.icu confirms the update.
2. If a listing or an update meets a server error or a network failure, the relay server shall repeat that identical request at most once, within the budget and the deadline, shall never repeat a request intervals.icu answered as rate-limited, and shall never repeat an upload.
3. On an upload request, the relay server shall find the activity again by listing and matching as Requirement 7 criteria 3 to 6 state, shall update an activity it finds there, and shall upload only when that listing was read completely and matched no activity.
4. When an upload request finds no activity, the relay server shall upload the request's file exactly once, unmodified, marked with the publication id as its external identifier, and shall never repeat the upload, whatever intervals.icu answers and whatever network failure occurs.
5. When intervals.icu answers that the upload created an activity, or that it already holds the file as an activity, and names exactly one activity, the relay server shall set that activity's name and description with one update, and on confirmation shall answer the uploaded outcome (created) or the posted outcome (already held), with that activity's identifier.
6. If an upload is answered with a server error, a network failure, or a success that does not name exactly one activity in the documented form; or the update of an activity the upload created is answered with anything but a confirmation; or an activity the upload named as already held is answered as not existing, the relay server shall answer the unconfirmed outcome.
7. The relay server shall finish each publish request and each upload request within a documented deadline shorter than fitdocs's request timeout, answering the unavailable outcome for a publish request, and for an upload request the unavailable outcome before the file was sent and the unconfirmed outcome after.
8. If any state the upload decision depends on cannot be read (a listing entry, the connection's token, the relay's own records or the budget reservation), the relay server shall end the request without uploading.
9. The relay server shall change no field of an intervals.icu activity other than its name and description, and shall delete nothing on intervals.icu.

### Requirement 9: One Meaning for Every intervals.icu Answer on Both Routes
**Objective:** As an athlete and as the maintainer, I want every intervals.icu answer to mean the same fitdocs code whichever route made the call, so that switching routes never changes what a code tells me.

#### Acceptance Criteria
1. The relay server shall map each intervals.icu answer to a publish-core code by the answer table, by request kind and answer class, that the direct route uses, so that one answer gives one code on either route.
2. The answer table, the activity identifier rule, the listing window, the fields the listing reads and how they are parsed, the one-to-one match, the reading of an upload's answer, and the shapes of the update, listing and upload requests shall each be defined once, in a standard-library-only fitdocs module that the direct route uses and that the relay runs as a byte-identical pinned copy, added to the existing pinned-copy cross-check, which shall fail on any drift.
3. An automated test on the fitdocs side and one on the relay side shall show that every code the answer table holds is a code a target may return.
4. The relay server shall answer a publish or upload request from a principal with no usable intervals.icu connection with the not-connected outcome.
5. Every result the direct route's tests pin shall be unchanged once those rules come from the shared module.
6. Where the two routes differ in how many times a transport repeats a request before the answer reaches the table, the documentation shall say so, and the code each final answer gives shall still be the same.

### Requirement 10: The intervals.icu Call Budget
**Objective:** As the operator of a relay whose one intervals.icu application serves every connected athlete, I want the relay to count its own intervals.icu calls against the application's and each athlete's limits and stop before intervals.icu does, so that one athlete's run cannot exhaust the limit for everyone.

#### Acceptance Criteria
1. The relay server shall take the application's daily limit, its fifteen-minute limit and the per-athlete daily limit from the deploy environment, each defaulting to the figure intervals.icu publishes for a new application.
2. Before each intervals.icu call, the relay server shall count that call in the database against the application's daily and fifteen-minute limits and the calling principal's daily limit, with days starting at midnight UTC, and shall not make a call that would exceed any of them.
3. The relay server shall count fifteen-minute windows so that no fifteen-minute span, however aligned, holds more counted calls than the application's fifteen-minute limit.
4. Before an upload, the relay server shall reserve, in one operation, the upload and the update that confirms it, and shall not upload when that reservation fails.
5. If a call is not made because the budget is spent, or intervals.icu answers that a limit was reached, the relay server shall answer the rate-limited outcome and make no further intervals.icu call for that request.
6. The relay server shall count the code exchange and the revocation calls like any other call.
7. The relay server shall keep the budget's counts in the configured database only, so that a restart neither resets nor loses them.

### Requirement 11: Disconnecting and Revocation
**Objective:** As an athlete, I want disconnecting from the CLI, revoking access at intervals.icu, or the operator deleting my principal to remove my intervals.icu token, so that the relay stops acting on my account when I withdraw.

#### Acceptance Criteria
1. When `fitdocs disconnect NAME` runs for a relay-routed instance, the fitdocs CLI shall behave as strava-publish Requirement 11 criteria 1 to 4 state for a Strava instance, naming intervals.icu wherever those criteria name the service.
2. Where `--local-only` is given for a relay-routed instance, the fitdocs CLI shall make no request, remove the instance's credentials file, and state that the intervals.icu connection stays at the relay until it is disconnected there or access is revoked in intervals.icu's settings.
3. When the relay receives a disconnect request for the intervals.icu target, it shall ask intervals.icu once to revoke the connection's token when the budget allows, then delete the connection and revoke its connection token in one transaction whatever intervals.icu answered, and shall answer success, also when the principal held no connection.
4. When access was revoked at intervals.icu, the relay server shall delete the connection the first time intervals.icu refuses its token, as Requirement 5 criterion 3 states.
5. When a principal is deleted, the relay server shall delete its intervals.icu connection in the same transaction.

### Requirement 12: Only the Activity Identifier Crosses the Relay Boundary
**Objective:** As an athlete and as the maintainer, I want the relay to return nothing intervals.icu said except the identifier the direct link needs, so that the relay route keeps fitdocs's rule that platforms speak only through fitdocs codes.

#### Acceptance Criteria
1. Every relay answer for the intervals.icu target shall carry only a relay code, a publish-core outcome, the fields its documented route defines, and, beside a posted or uploaded outcome only, the identifier of the intervals.icu activity the post landed on, in the documented identifier form; never an intervals.icu response body, header, status text, address or other identifier.
2. The relay server shall never log an intervals.icu response body, header, identifier or address, an authorization code, a state value, an intervals.icu token or an encryption key; its log records about intervals.icu calls shall carry only fitdocs-defined classifications.
3. The relay server shall store nothing intervals.icu returned beyond the encrypted token of each live connection and the keyed account hash: no activity, activity identifier, athlete identifier, name or response.
4. Every page the relay serves for the intervals.icu target shall be fitdocs-written, shall interpolate only values fitdocs generated or validated, and shall show no text intervals.icu returned.
5. The relay's intervals.icu routes shall accept only fitdocs's connect, poll, publish, upload and disconnect requests, the connect page and the authorization callback; they shall never forward a caller's request to intervals.icu, and shall never use one principal's token for another principal.

### Requirement 13: Relay Configuration for intervals.icu
**Objective:** As a relay operator, I want the intervals.icu target configured from the environment like everything else in the deploy contract, and absent until I configure it, so that a relay without an intervals.icu application behaves exactly as before.

#### Acceptance Criteria
1. The relay package shall append to the deploy contract's variable table the intervals.icu application's client id and client secret, intervals.icu's authorization, token and API addresses, and the call limits, each with whether it is required, its default, whether it is secret and its meaning.
2. The relay server shall offer the intervals.icu target exactly when its client id is configured; the other required intervals.icu variables shall then be required, and if any is absent or invalid, the relay server and its commands shall refuse to start, naming the variable but never its value.
3. The target-neutral variables (the relay's public address, the encryption keys, the operator's name and support contact) shall be required when any relay target is configured, and the variable table and the relay documentation shall say so.
4. While the intervals.icu target is not configured, the capabilities endpoint shall list no intervals.icu target, every intervals.icu envelope route shall answer not-offered, and every intervals.icu page shall answer not found, with every other relay behaviour, Strava's included, unchanged.
5. When the intervals.icu target is configured, the capabilities endpoint shall list `intervals` among its targets.
6. The intervals.icu addresses shall be configurable, each defaulting to intervals.icu's current address.
7. The relay documentation shall state that a self-hosted relay needs its own intervals.icu OAuth application, approved by intervals.icu, with the relay's own callback address registered on it, and may never use another operator's application credentials.

### Requirement 14: One Set of Relay-Target Machinery
**Objective:** As the maintainer, I want the relay and fitdocs to run one connect mechanism, one custody, one set of pages and one relay-answer mapping for every relay target, so that the second target adds only what is specific to intervals.icu and Strava keeps behaving as specified.

#### Acceptance Criteria
1. A relay offering both targets shall use one connect-session mechanism, one set of encryption keys, one re-encryption command and one privacy-policy address for both, and its privacy policy shall describe each configured target.
2. Every Strava behaviour strava-publish specifies shall be unchanged, and every Strava test shall pass with no change other than the modules it imports.
3. The fitdocs CLI's browser-consent connect and disconnect shall name the service of the instance they act on in every line that names a service.
4. Neither the relay package nor fitdocs shall hold a second copy of the connect-session, token-custody, page, policy or relay-answer mapping machinery for the intervals.icu target.

### Requirement 15: Documentation, Network Statements, Steering and Changelog
**Objective:** As a fitdocs user or relay operator relying on what the repository says, I want every statement about the network, credentials and the relay to stay true once the relay route exists, so that nothing published contradicts what the code does.

#### Acceptance Criteria
1. The connectors documentation shall describe the relay route: choosing it per instance and that direct is the default, its settings, connecting with and without a browser, publishing and uploads (the known activities sent, the local refusals, what leaves the machine), the direct link, the local-record-unreadable answer, switching an instance between routes, disconnecting, the code mapping, and the documented differences from the direct route (the longest post and the largest activity file the relay route sends).
2. The relay documentation shall describe the intervals.icu target: its variables, its routes and pages, the budget, the data held and when it is deleted, the policy and consent, and the self-hosting note; and shall describe the target-neutral variables, encryption keys and privacy policy once for every target.
3. Every repository statement that lists the commands which make network requests shall name `fitdocs publish --yes`, and the connectors documentation's "What leaves your machine" shall say that a relay-routed instance's requests go to its bound relay instance's URL and never to intervals.icu, whichever Phase 14 target lands first; an automated test shall pin each such statement.
4. The technology steering's network and credentials section shall state, in its own sentence, the requests `fitdocs connect`, `fitdocs disconnect` and `fitdocs publish --yes` make for a relay-routed instance, and the structure steering shall describe the shared intervals.icu rules module and its pinned copy.
5. The `fitdocs` changelog's unreleased section shall record the relay route to intervals.icu, and the relay changelog shall record the intervals.icu target, its variables, routes and storage change.
6. This feature shall edit no website page, and shall record the site copy it makes stale or newly needs as a follow-up for the next release.
7. Every new or changed document shall pass every existing documentation, network-statement and neutral-scan guard, and no new document shall mention a hosting provider, an email provider or a deployment's infrastructure.
8. This feature shall not change the packaged agent skill, whose publishing section names no target.

### Requirement 16: The Approval Gate and the Optional Live Check
**Objective:** As the maintainer, I want implementation to wait until intervals.icu has approved my OAuth application, and a written procedure for checking the whole path once against it, so that nothing is built on an OAuth contract that cannot yet be exercised and the scripted tests' picture of intervals.icu is confirmed before release.

#### Acceptance Criteria
1. The Specification Process shall start no implementation task of this feature until the maintainer has recorded that intervals.icu approved the maintainer's OAuth application, or has recorded in writing a decision to implement before approval.
2. The repository shall provide a live-check procedure for the maintainer to carry out against the maintainer's own approved intervals.icu application and account (connect, publish an update, follow the direct link, disconnect), stating first that it writes to that real account, and a record template for its results.
3. No implementation, review or validation session shall carry out any step of the live check; a session shall fill the record template only with the fitdocs codes and the response shapes the maintainer reports, never an identifier, name, date, token or secret, and the live check shall never run in the test suite or in CI.
4. If a finding contradicts an assumption the design marks as to be confirmed, the Specification Process shall amend the design and every affected task, and no other task shall wait for the live check.
