# Requirements Document

## Project Description (Input)
The athlete moves `.fit` files into the inbox by hand. HealthFit exports land
in an iCloud folder and are copied over; Garmin rides are exported from
Connect one at a time; anything the phone-side store never received is missed
unless the athlete notices. The athlete wants a configured tool that fetches
every file they do not yet have, and the same tool should later push to
platforms and pull thresholds and plans back. None of that later work is this
spec, but this spec's protocol, state and credential store must not need
rebuilding to admit it.

This spec builds the connector framework (Phase 8 of the roadmap, wave 1): a
published connector protocol and capability vocabulary (pull activities
implemented; the follow-ons' kinds named and reserved, each flagged reversible
or irreversible); a built-in registry and the registration surface the later
connector plugin kind validates against; per-user credential and token storage
outside the data root; a ledger per configured source under the data root's
tool-state directory; an HTTP transport with an explicit User-Agent, timeouts,
bounded retries for data calls and none for authentication; atomic delivery
into the inbox; the `fitdocs connect` and `fitdocs pull` commands, the pull
optionally chaining the drain; the folder connector; the revised network
statements and guards; the packaged skill's routine. It also lands this
spec's part of the wiki-contract Amendment 4 (credentials never under the data
root; the ledger is owned tool state) and the distribution update (the
packaged `fitdocs-workouts` skill learns the pull).
Source: `.kiro/specs/connectors/brief.md`; Phase 8 of
`.kiro/steering/roadmap.md`.

## Introduction

Until now every `.fit` file reached fitdocs because the athlete put it in the
inbox. Phase 8 lets a configured **connector** do that: it lists what a source
holds, fetches what the athlete does not yet have, and delivers it into the
same inbox a hand-dropped file lands in. Everything after delivery is the
existing drain, so a pulled file, a HealthFit export and a hand drop are
ingested identically. A connector never knows what a page is.

Three properties shape every requirement below. **Nothing secret touches the
data root**: the data root may be a git repository or a shared wiki, so keys
and tokens live in a per-user location readable only by the user, are
overridable from the environment for unattended runs, and never appear in any
output. **Authentication is attempted once**: a rate limit, an extra
verification step or a lockout at login is reported with the service's own
words and the next step, never retried, because some services extend a lockout
on every retry. **The ledger, not a listing, decides what is new**: a cloud
folder that lists only part of its contents on one run is caught up by
whichever later run sees the rest, and a second pull fetches nothing it has
already fetched.

The one inbox behavior this spec adds is deliberate: under the default
leave-in-place disposition every drain re-reads every file ever dropped, so
pulled files would otherwise accumulate beside their archived copies and be
re-hashed forever. A file a connector delivered is fitdocs's own transient
copy of bytes that exist at the source and, once drained, in the archive; the
next pull removes it once — and only once — the archive holds identical bytes.
The drain itself still never deletes anything, and nothing the athlete or the
athlete's own tools put in the inbox is ever removed.

## Boundary Context

- **In scope**: the connector protocol, its capability and authentication-style
  vocabularies and the reversible/irreversible flag; the registry and its
  validation gate; the `[connectors]` settings table and its reader; the
  per-user credential and token store and its environment overrides; the
  per-instance ledger; the HTTP transport; delivery into the inbox and removal
  of archived deliveries; `fitdocs connect`; `fitdocs pull` with `--since`,
  `--dry-run`, instance selection and `--sync`; the folder connector; the
  revised network statements and a guard confining network code; the
  ownership-contract statements for credentials, the ledger and the two
  commands; write-confinement registration; the connectors documentation page
  and the settings, inbox, compatibility and changelog updates; the packaged
  `fitdocs-workouts` skill's routine and its pins; the technology steering's
  network and credential rules.
- **Out of scope**: any connector for an online service (`intervals-connector`
  and user-installed plugins); discovering connectors from installed
  distributions or local plugin files and listing them (the plugin platform's
  connector kind, a later update against this protocol); cross-source identity
  and base selection (`activity-identity`) and channel composition
  (`channel-merge`); every capability other than pulling activities (reserved
  names only); a browser-consent authentication flow (reserved as a style,
  built with the first connector that needs it); a daemon, watcher or
  scheduler; any connector for a service whose terms forbid the access.
- **Adjacent expectations**: the `inbox` spec owns candidate selection, the
  stability check, quarantine and the leave/move dispositions; delivered files
  are ordinary candidates to it, and the only change to its contract is the
  pull's removal of its own archived deliveries, which the drain never
  performs. The `sync` engine is chained exactly as `fitdocs sync` with no
  source runs it. `activity-identity` decides which page a delivered file
  belongs to from the file's own bytes; until it has shipped, pulling into a
  data root that already holds other copies of the same activities creates
  duplicate pages, and the documentation says so. `wiki-contract` owns the
  ownership contract and its version; this spec adds its statements to the
  shared Amendment 4. `distribution` owns the packaged skill; this spec moves
  its routine and pins. `route-maps` remains the other network user and keeps
  its own cache.
- **Downstream contract**: `intervals-connector` implements this protocol with
  a personal-key style, listing by window, per-activity fetch, the transport's
  retry policy and the ledger, with no amendment to this spec. The plugin
  platform's connector kind validates plugins with this spec's validation gate
  and registers them through this spec's registry. Follow-on push connectors
  use the reserved capabilities, the irreversible flag and the ledger's
  remote-id-to-content-hash records. A change to the protocol's shape, the
  vocabularies, the validation rules, the ledger's form or the credential
  store's location is a change each of these must re-check.

## Requirements

### Requirement 1: A Published Connector Protocol and Capability Vocabulary
**Objective:** As a connector author (the `intervals-connector` spec now, a user writing a plugin later), I want one published protocol that says what a connector declares and which operations each capability requires, so that a connector is written once against a fixed contract and later capabilities never force a rebuild.

#### Acceptance Criteria
1. The connector framework shall define a connector as a declaration of a unique connector id, a display name, exactly one authentication style, the set of capabilities it offers, and the credential fields it needs the user to supply, each field named, labeled, and marked secret or not secret.
2. The connector framework shall define a capability vocabulary of exactly nine members: pull activities, push activity, annotate remote activity, resolve remote activity, push planned workout, pull planned workouts, pull plans, pull thresholds, and pull wellness.
3. The connector framework shall mark each capability as changing state at the remote service or not, and as reversible or irreversible, marking push activity, annotate remote activity, and push planned workout as changing remote state and irreversible, and every other capability as not changing remote state and reversible.
4. The connector framework shall drive only the pull-activities capability in this version; where a connector declares any of the other eight, the connector framework shall accept the declaration without requiring any operation for it, and no command shall invoke it.
5. The connector framework shall define pulling activities as two operations: a listing of remote activities for an optional earliest start time, each listed activity carrying a stable remote id, whether an original file is available, and — where the service states them — its start time, sport, duration, a revision token that changes when the remote file changes, and a suggested file name; and a fetch of one listed activity's original bytes.
6. The connector framework shall let a fetch answer in exactly one of three ways: the file's bytes; a declination with a reason, meaning the activity has no usable original; or a deferral with a reason, meaning the original cannot be fetched yet.
7. The connector framework shall define four authentication styles — none, personal key, login (credentials exchanged once for renewable tokens), and browser consent — and shall treat browser consent as reserved: a connector may declare it, and `fitdocs connect` shall refuse it as unsupported by this version.
8. Where the service does not state a listed activity's start time, sport, duration, or revision, the connector framework shall carry that value as absent, never as zero, an empty string, or a default.
9. The connector framework shall give a connector its configuration, its credentials, the transport, and the clock as its only inputs, and shall take listings, fetched bytes, and credential updates as its only outputs; it shall never read, render, score, or write a workout document on a connector's behalf.

### Requirement 2: Registration and Validation (the Surface the Plugin Kind Validates Against)
**Objective:** As the maintainer of the plugin platform, I want connectors registered through one validation gate shaped like the load-calculator registry's, so that the later connector plugin kind can discover, validate, register and list connectors without redesigning this protocol.

#### Acceptance Criteria
1. The connector framework shall keep a registry of connectors addressed by connector id, and shall register the built-in folder connector whenever the connector package is loaded.
2. When a connector is offered for registration, the connector framework shall validate its declaration without calling any of its operations.
3. If an offered connector's id is not a lowercase slug, its display name is empty, its authentication style or any capability is outside the vocabulary, it declares no capability, its credential fields are malformed or share a name, it declares credential fields under the none style or none under another style, or it lacks an operation its authentication style or a driven capability requires, the connector framework shall reject it with a reason naming the first violated member and register nothing.
4. If a connector is offered under an id already registered, the connector framework shall reject it, keep the incumbent registration, and name the contested id.
5. When a connector id that is not registered is looked up, the connector framework shall report the unknown id together with every registered id.
6. The connector framework shall allow a registered connector to be unregistered by id.
7. The connector framework shall publish the protocol's types, the capability and authentication-style vocabularies, and the registration operations as one enumerated surface, and an automated test shall pin that surface so that a change to it is always deliberate.
8. The connector framework shall leave load-calculator plugin discovery, the `[plugins]` settings, and the `fitdocs plugins` listing unchanged.

### Requirement 3: Configuring Connectors
**Objective:** As an athlete, I want to name each source I pull from in my settings file, so that one command knows every connector I use and how each is configured, with no secret ever written there.

#### Acceptance Criteria
1. Where the settings file contains a connectors table with one named sub-table per source, the fitdocs CLI shall treat each sub-table as one configured connector instance identified by its name.
2. The fitdocs CLI shall take a configured instance's connector from the instance's `connector` key, and shall use the instance's own name as the connector id when that key is absent.
3. The fitdocs CLI shall accept per instance an optional listing look-back in whole days, defaulting to a documented value, and shall hand every other key of the instance to its connector for validation, ignoring keys neither recognizes, as every other settings table does.
4. If an instance name is not a lowercase slug, names an unregistered connector, carries a malformed look-back or connector key, or fails its connector's own validation, the fitdocs CLI shall stop with a configuration error naming the settings file, the instance, and the key, before any network request and before any write.
5. If an instance's table contains a key named like one of its connector's credential fields, the fitdocs CLI shall stop with a configuration error that names the key and states that credentials belong in `fitdocs connect` or the environment, never in the settings file.
6. If two configured instances would read the same credential environment variable, the fitdocs CLI shall stop with a configuration error naming both instances.
7. While the settings file or its connectors table is absent, the fitdocs CLI shall treat the configuration as having no connectors, never as an error.
8. The fitdocs CLI shall never write, create, or modify the settings file.
9. The fitdocs CLI shall resolve the data root for `fitdocs connect` and `fitdocs pull` by the same precedence every other tree command uses, and shall treat an unresolvable data root as a configuration error.

### Requirement 4: Credentials and Tokens Outside the Data Root
**Objective:** As an athlete whose data root may be a git repository, I want credentials stored per user, outside the data root, readable only by me, and overridable from the environment, so that no key or token can be committed, synced, or shared with my wiki.

#### Acceptance Criteria
1. The connector framework shall store each connected instance's credentials in one file per instance inside a per-user credentials directory, resolved in a documented order: a dedicated fitdocs environment variable, then the user's configuration-home environment variable, then a default location under the user's home directory.
2. If the resolved credentials directory is the data root or lies inside it, the fitdocs CLI shall refuse to read or write credentials there and stop with a configuration error naming the directory.
3. The connector framework shall create the credentials directory accessible only by the user, shall make each credentials file readable and writable only by the user, and shall write each file atomically so that an interruption never leaves a partial credentials file.
4. If a credentials file is readable or writable by anyone other than the user, the connector framework shall refuse to use it and shall report the file and the permission change that fixes it.
5. Where an environment variable named for the instance and a credential field is set, the connector framework shall use its value in place of the stored value for that field of a personal-key connector, and the variable shall satisfy that field even when nothing is stored.
6. The connector framework shall persist for a login-style connector only the tokens the service issued, their expiry, and the granted scopes, and shall never persist the password or any other value the user typed to obtain them.
7. When a login-style connector's service issues a new token set — at connect, or by renewing an expired token at the start of a pull — the connector framework shall persist the new set atomically before any further request uses it.
8. The connector framework shall record with each instance's credentials the connector they were issued for and the scopes the service reported as granted, recording unreported scopes as absent rather than as an empty grant.
9. If an instance's stored credentials were issued for a different connector than the instance now names, or record a newer credentials format than this version reads, the connector framework shall treat the instance as not connected and say why.

### Requirement 5: Connecting a Source (`fitdocs connect`)
**Objective:** As an athlete, I want one command that connects a configured source interactively, stores only what the source needs, and tells me plainly what went wrong when the service refuses, so that I never leak a secret, never lock my account by retrying, and always know my next step.

#### Acceptance Criteria
1. When `fitdocs connect NAME` runs for a configured instance, the fitdocs CLI shall prompt for each credential field its connector declares, without echoing any field marked secret.
2. If the instance's connector requires no authentication, the fitdocs CLI shall report that there is nothing to connect and exit with the success code, prompting for nothing and writing nothing.
3. If NAME is not a configured instance, the fitdocs CLI shall exit with the configuration-error code naming every configured instance; if the instance's authentication style is reserved, it shall exit with the configuration-error code naming the style as unsupported by this version.
4. If standard input is not an interactive terminal, the fitdocs CLI shall prompt for nothing, exit with the configuration-error code, and, for a personal-key connector, name the environment variables an unattended pull can use instead.
5. When the service accepts the user's answers — for a personal-key connector, only after one read request made with them succeeds — the fitdocs CLI shall store the credentials, report the instance, the credentials file's location, and the granted scopes or that the service reported none, and exit with the success code.
6. If the service rejects the credentials, rate-limits the request, demands an additional verification step, reports the account locked, blocks the client, or cannot be reached, the fitdocs CLI shall name which of these occurred, quote the service's own message with every secret removed, name the next step the user should take, store nothing, and exit with the failure code.
7. The fitdocs CLI shall make exactly one authentication attempt per `fitdocs connect` invocation and never repeat it automatically, whatever the service answers.
8. When `fitdocs connect` succeeds for an instance that already has stored credentials, the fitdocs CLI shall replace them atomically.
9. The fitdocs CLI shall write nothing under the data root during `fitdocs connect`.

### Requirement 6: Pulling (`fitdocs pull`)
**Objective:** As an athlete, I want one command that fetches every activity file I do not yet have from all my configured sources, or from the ones I name, so that files arrive in my inbox without my moving them by hand.

#### Acceptance Criteria
1. When `fitdocs pull` runs without instance names, the fitdocs CLI shall pull from every configured instance in instance-name order; when names are given, it shall pull from exactly those.
2. If a named instance is not configured, the fitdocs CLI shall exit with the configuration-error code before any network request and before any write, naming every configured instance.
3. While no connector is configured, the fitdocs CLI shall report that no connectors are configured and complete with the success code.
4. The fitdocs CLI shall list each instance's remote activities from its ledger's watermark less the instance's look-back, or with no earliest start time when the ledger has no watermark; where `--since DATE` is given, it shall list from the start of that day in the local time zone instead.
5. The fitdocs CLI shall fetch each listed activity whose remote id is not recorded in the instance's ledger with a final outcome for the same revision, and shall never fetch one that is.
6. Where a listed activity is marked as having no available original, the fitdocs CLI shall not fetch it and shall record it as skipped with the connector's reason.
7. If a fetch returns bytes whose header does not identify a FIT file, the fitdocs CLI shall not deliver them and shall record the activity as skipped, stating that the original is not a FIT file.
8. When fetched bytes are identical to a file already in the archive, or to a delivery of the same instance still waiting in the inbox, the fitdocs CLI shall record the activity as already held and shall not deliver a second copy.
9. Where `--dry-run` is given, the fitdocs CLI shall list, report what each instance would fetch, and fetch, deliver, remove, and record nothing, writing nothing under the data root or in the inbox; a token renewal the listing requires shall still be persisted to the credentials store.
10. If an instance cannot pull — it is not connected, its credentials are rejected, its listing fails, its ledger is unusable, or its source cannot be reached — the fitdocs CLI shall report that instance's failure with its reason and next step, and continue with the remaining instances.
11. If one activity's fetch fails, the fitdocs CLI shall report that activity's failure, leave it unrecorded so that the next pull tries it again, and continue with the instance's remaining activities; if the failure is an authentication failure, the fitdocs CLI shall instead end that instance's pull.
12. Where a connector defers a listed entry or a fetch, the fitdocs CLI shall report the deferral with its reason, leave it unrecorded, and not count it as a failure.
13. The fitdocs CLI shall perform no scheduling, watching, or background activity: each `fitdocs pull` is one run that ends when every selected instance has been pulled.

### Requirement 7: The Ledger
**Objective:** As an athlete running pulls on a schedule, I want a per-source record of everything already fetched, so that a second pull fetches nothing new, a lazily listed cloud folder is caught up later, and a later push can find the remote activity behind a page.

#### Acceptance Criteria
1. The connector framework shall keep one ledger per configured instance under the data root's tool-state directory, recording for each remote id its revision, its outcome — delivered, already held, or skipped — the content hash of its bytes where they were fetched, the reason where it was skipped, and, while a delivery waits in the inbox, the delivery's inbox-relative location.
2. The connector framework shall record in each ledger the connector id it belongs to and a watermark: the newest remote start time at or before which every listed activity with a start time has a final outcome; the watermark shall never move backward, and shall stay absent until an activity with a start time reaches a final outcome.
3. The connector framework shall write a ledger atomically, with its entries in a stable order and no clock-derived value, and shall skip the write when the content is unchanged, so that a pull that changes nothing leaves the ledger byte-identical.
4. The connector framework shall save an instance's ledger when that instance's pull ends, including when it ends in failure or is interrupted, so that every delivery already made is recorded.
5. While an instance has no ledger file, the connector framework shall treat the instance as having fetched nothing, and shall create no file until there is something to record.
6. If a ledger exists but cannot be read, is not in its documented form, records a newer ledger format than this version reads, or belongs to a different connector than the instance now names, the connector framework shall fail that instance's pull with a message naming the file, and shall never overwrite or rebuild it.
7. The connector framework shall decide whether a listed activity is new from the ledger's records alone, so that an activity missing from one listing — a cloud file not yet downloaded — is fetched by whichever later pull lists it.
8. The connector framework shall record content hashes in the form the archive names its files by, so that a page's recorded sources map to the remote ids they were pulled from.

### Requirement 8: Delivery into the Inbox and Removal of Archived Deliveries
**Objective:** As an athlete, I want pulled files to enter the same inbox my hand-dropped files do, arrive whole, and not pile up there once ingested, so that the drain treats every file alike and my inbox never fills with copies of the archive.

#### Acceptance Criteria
1. The fitdocs CLI shall deliver each new file into the configured inbox, inside a subdirectory named for the instance, by writing it under a dot-prefixed temporary name and then renaming it, so that the drain never selects a partially written delivery.
2. The fitdocs CLI shall deliver the fetched bytes unmodified, so that the drain and every later identity decision see exactly the bytes the source served.
3. If a delivery's name is already taken by another file, the fitdocs CLI shall deliver under a distinct name derived from the content and shall never overwrite an existing file.
4. The fitdocs CLI shall resolve and validate the inbox, and create it and the instance's delivery subdirectory when missing, by the inbox's own location rules and configuration errors.
5. When a pull starts for an instance (and `--dry-run` is not given), the fitdocs CLI shall remove each of that instance's earlier deliveries whose recorded content hash is present in the archive and whose file's current bytes still have that hash, and shall report each removal.
6. The fitdocs CLI shall never remove an inbox file that the instance's ledger does not record as that instance's pending delivery, a delivery whose current bytes differ from what was delivered, or a delivery whose bytes are not in the archive — including one that failed, was quarantined, or was left in place by the drain's newer-document-format gate.
7. If an earlier delivery has disappeared from the inbox before its bytes reached the archive, the fitdocs CLI shall forget that activity's ledger record so that the next pull fetches it again.
8. Where the inbox's move disposition is configured, the fitdocs CLI shall leave delivered files to the drain, which moves each one as it moves any processed file.
9. The drain shall select, settle, process, quarantine, and dispose of delivered files exactly as it does any other inbox file, and shall itself never delete an inbox file.

### Requirement 9: The Transport
**Objective:** As an athlete, I want every request a connector makes to identify fitdocs, give up in bounded time, retry data requests only a few times, and never retry a login, so that services do not block the tool and my account is never locked out by automation.

#### Acceptance Criteria
1. The connector framework shall send with every request an explicit fitdocs User-Agent naming the installed fitdocs version and the project, and never the HTTP library's default agent.
2. The connector framework shall bound every request with a timeout.
3. When a listing or fetch request fails with a rate-limit response, a server error, or a network failure, the connector framework shall repeat it at most a bounded number of times with increasing waits, honoring a wait the service states when it is within a bounded maximum, and shall then report the failure.
4. The connector framework shall send each authentication request — a key check, a login, or a token renewal — exactly once, never repeating it whatever the response.
5. The connector framework shall never repeat a request the service answered as unauthorized or forbidden.
6. The connector framework shall not send a credential header to a host a response redirects the request to.
7. If a response body exceeds a bounded size, the connector framework shall abandon it and report that request as failed.
8. The connector framework shall let the transport be substituted, so that every connector and command is exercised in tests with no network access.

### Requirement 10: Secrets Are Never Exposed
**Objective:** As an athlete, I want no key, token, password or signed download link ever to appear anywhere fitdocs writes or prints, so that sharing a log, a report or my wiki never shares my accounts.

#### Acceptance Criteria
1. The fitdocs CLI shall never print, report, log, or write into any file other than the instance's credentials file a credential value, a token, a password, or a signed download location.
2. When a connector's error, a service's message, or any other reason the fitdocs CLI reports contains a credential value, a token, or a signed download location known to the run, the fitdocs CLI shall replace each occurrence with a redaction marker before reporting it.
3. The connector framework shall represent a secret value so that its text form and its representation, including inside an exception message, show only a redaction marker.
4. The connector framework shall describe a failed request by the service's host and path only, never by its query string or a signed download location.
5. The fitdocs CLI shall never record a secret in the ledger, the settings file, the inbox, or anywhere else under the data root.
6. If `fitdocs connect` or `fitdocs pull` ends with an unexpected error, the fitdocs CLI shall not print the values of local variables.

### Requirement 11: The Pull Report and Exit Codes
**Objective:** As an athlete, or the agent running my routine, I want a per-source report of what was listed, fetched, already held, skipped, deferred and failed, and an exit code that follows the CLI's convention, so that a scheduled run is auditable and its failures are unmistakable.

#### Acceptance Criteria
1. When `fitdocs pull` completes, the fitdocs CLI shall print the inbox path and, for each pulled instance, the number of activities listed and one named count for each channel — delivered, already held, skipped, deferred, failed, removed after archiving, and the instance's own failure — including when a channel is empty.
2. The fitdocs CLI shall list beneath the counts each delivered file, each skipped, deferred, and failed activity with its reason, each removed delivery, and each instance failure with its reason and the next step.
3. Where `--dry-run` is given, the fitdocs CLI shall report per instance the activities it would fetch, in place of delivered files, and shall state that nothing was fetched or written.
4. The fitdocs CLI shall exit with the failure code when any instance or any activity failed, with the configuration-error code for a configuration error, and with the success code otherwise, including a pull whose only exceptional entries are deferrals and skips.
5. The fitdocs CLI shall order every report deterministically: instances by name, and entries within an instance by remote id or delivered name.

### Requirement 12: Chaining the Drain
**Objective:** As an athlete scheduling fitdocs with cron or launchd, I want one command that fetches and then ingests, so that an unattended run needs no second step.

#### Acceptance Criteria
1. Where `--sync` is given, the fitdocs CLI shall, after every selected instance has been pulled, drain the configured inbox and run the training-load pass and the plan reconciling pass exactly as `fitdocs sync` with no source argument does, and shall print that drain's report after the pull report.
2. Where `--sync` is given, the fitdocs CLI shall run the chained drain even when some instances failed.
3. Where `--sync` and `--no-prompt` are both given, the fitdocs CLI shall run the chained training-load pass without prompting, exactly as `fitdocs sync --no-prompt` does.
4. If `--sync` and `--dry-run` are both given, the fitdocs CLI shall exit with the configuration-error code before any network request, because a dry run writes nothing.
5. Where `--sync` is given, the fitdocs CLI shall exit with the failure code when either the pull or the chained passes report a failure.

### Requirement 13: The Folder Connector
**Objective:** As an athlete whose phone app exports to a cloud folder, I want that folder as a source, so that its exports reach my inbox without my moving them, and a folder still syncing is caught up later rather than failed.

#### Acceptance Criteria
1. The fitdocs CLI shall provide a built-in folder connector that requires no authentication and takes a source directory, resolved against the data root when relative and used as given when absolute, and an optional settle interval defaulting to the inbox's default.
2. The folder connector shall list every regular file under its source directory, recursively, whose extension is `.fit` in any letter case, ignoring any file whose source-relative path has a dot-prefixed component or matches the inbox's built-in junk patterns, and shall identify each file by its source-relative path and each version of it by its size and modification time.
3. If a listed file's size or modification time changes across the settle interval, or the file cannot be read, the folder connector shall defer it to a later pull, never fail it.
4. When a file already recorded in the ledger is listed with a different size or modification time, the fitdocs CLI shall treat it as a new version and fetch it again.
5. The folder connector shall only read its source directory and shall never create, modify, move, or delete anything there.
6. If the source directory is missing or is not a directory when a pull runs, the fitdocs CLI shall fail that instance, naming the path.
7. If the configured source directory is the inbox, lies inside it, or contains it, the fitdocs CLI shall stop with a configuration error naming both paths.
8. The folder connector shall state no start time, sport, or duration for what it lists, so that its ledger keeps no watermark and every pull considers the whole folder.
9. The folder connector shall make no network request.

### Requirement 14: Network Confinement and Honest Statements
**Objective:** As a privacy-conscious athlete, I want network access limited to explicit connector commands and the existing map tiles, and every statement about the network to be true, so that I know exactly when fitdocs talks to the outside world.

#### Acceptance Criteria
1. The fitdocs CLI shall make connector requests only during `fitdocs connect` and `fitdocs pull`; `sync`, `regen`, `load`, `check`, `history`, `plan`, `derive-benchmarks`, and rendering shall make none, whether or not connectors are configured, and shall keep their existing map-tile behavior unchanged.
2. The fitdocs source shall hold network-capable code in exactly two places — the map-tile fetch and the connector transport — and an automated guard shall fail when any other module reaches for the network.
3. The connector package shall not depend on rendering, training load, metrics, `.fit` ingestion, or the sync engine, and an automated guard shall enforce it.
4. Every statement in the shipped code, the README, and the documentation that describes where fitdocs touches the network shall name both the map tiles and the connector commands, and none shall claim the map tiles are the only network access.
5. The fitdocs CLI shall add no runtime dependency for connectors, so that the frozen runtime dependency list stays unchanged.
6. The connector framework, its tests, and its documentation shall be service-neutral: they shall name no online service's endpoint, and this spec shall ship no connector for an online service.
7. The project's technology steering shall state the network rule, the credential rule, and the stdlib-only rule for connectors.

### Requirement 15: Contracts, Confinement, Documentation, and the Packaged Skill
**Objective:** As a user relying on fitdocs's published contracts, an LLM agent working my wiki, or a maintainer, I want every contract the connectors touch restated, guarded and documented, so that nothing about the new commands contradicts a published guarantee.

#### Acceptance Criteria
1. The ownership contract shall state that credentials never live under the data root, that each connector ledger is fitdocs-owned tool state in the tool-state directory, what `fitdocs pull` writes and removes (its deliveries in the configured inbox and its ledgers), and that `fitdocs connect` writes nothing under the data root.
2. The ownership contract's version shall advance for these statements, sharing one advance with the other parts of the same contract amendment that land before the next release.
3. `fitdocs pull` shall be registered with the write-confinement guard as a writing entry point with its own proof that the measured run wrote, and an automated test shall prove that `fitdocs connect` writes only its credentials file and nothing inside the data root or the source tree.
4. The inbox documentation and the compatibility policy shall state that the drain never deletes an inbox file, that nothing the athlete or the athlete's tools put in the inbox is ever deleted, and that a connector's own delivery is removed by the next pull once identical bytes are archived, keeping every existing never-delete statement true.
5. The shipped documentation shall describe connectors: configuring instances, the folder connector, connecting, where credentials live and their environment overrides, the pull and its options and report, delivery and removal, the ledger, what leaves the machine, the terms-first policy, and — while cross-source identity has not shipped — that pulling into a data root that already holds other copies of the same activities creates duplicate pages.
6. The settings documentation, the ownership contract, and the compatibility policy shall name the connectors table among the settings file's tables.
7. The packaged `fitdocs-workouts` skill's routine shall pull and drain in one command and then check the tree; the skill shall document the pull report's channels in a table an automated test binds to the pull report's fields, and shall tell the agent never to run `fitdocs connect` itself and never to retry a failed authentication.
8. The changelog's unreleased section shall record the two commands, the connectors table, and each governed-contract change together with the action a user must take.
