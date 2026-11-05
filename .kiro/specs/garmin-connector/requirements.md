# Requirements Document

## Project Description (Input)
An athlete who records on Garmin creates their own key for Garmin's Connect
Personal API, connects it once with `fitdocs connect garmin`, and from then on
`fitdocs pull` brings their activities and daily wellness straight from Garmin,
history included, into the same inbox a hand-dropped file lands in. There is no
relay, no data export and no intervals.icu account. The connector is built into
the `fitdocs` wheel, uses the standard library only through
`fitdocs.connectors.http`, is read-only at Garmin, and never sends the key
anywhere but Garmin's token call. Women's health, courses and training are out.
It derives only from Garmin's public Personal API material and from measurement.
Source: `.kiro/specs/garmin-connector/brief.md`; Phase 15 of
`.kiro/steering/roadmap.md`.

## Introduction

The athlete creates a key on Garmin Connect, names the connector in
`fitdocs.toml`, runs `fitdocs connect` once, and from then on `fitdocs pull` (by
hand or from a schedule) fetches every activity Garmin holds that the athlete
does not yet have, into the same inbox a hand-dropped file lands in. With wellness
enabled, it does the same for daily wellness. Everything after delivery is the
existing drain.

Three properties shape the requirements. **What arrives is the device's original,
byte for byte**: Garmin serves each original in a ZIP, and fitdocs hands over that
one file unchanged, or skips it by name if it is not a FIT file. **The key is
personal and Garmin is treated gently**: Garmin's terms make the key "personal to
you" and let Garmin throttle or suspend access without notice, so the key goes
nowhere but Garmin's token call, requests are paced, and a refusal ends the pull
instead of being retried. **The first pull covers full history, in steps**: a
decade of activities cannot safely be one long run, so each pull handles a bounded
share, oldest first, and the next pull continues by itself.

The service shapes used here come from Garmin's public Swagger page, its public
Apache-2.0 client, and two read-only checks with the maintainer's own key on
2026-11-05 (`brief.md`, "Measured"). Those checks saw no real HRV record, which is
why HRV is archived but not read.

## Boundary Context
- **In scope**: the Garmin connector (its declaration, the key check at connect,
  the activity listing, pacing and the per-pull limit, the original download and
  ZIP handling, failure reporting, wellness listing and packaging); the Garmin
  wellness delivery format and its source, read into the wellness series; the
  documentation for setting the connector up, including the terms and what a first
  pull does to an existing wiki; the live check; the amendment records on
  `connectors` and `wellness-store`; the steering sentences this makes false.
- **Out of scope**:
  - Garmin's women's health, courses, training and golf data;
  - any relay, hosted or shared path for a key, now or as a later option of this
    connector;
  - writing anything to Garmin;
  - reading GPX or TCX;
  - Garmin's activity summary JSON as page content;
  - Garmin's China service;
  - a Garmin export-zip importer;
  - reading HRV or VO2max into the series (the first follow-on, once a real record
    and a source for what it measures exist).
- **Adjacent expectations**:
  - `connectors` supplies the protocol, the credential store and its environment
    override, the ledger, the transport (fitdocs User-Agent, timeouts, bounded
    retries, a single-attempt mode, credential headers never sent to a redirect
    target), the FIT-header backstop, delivery into `<inbox>/<instance>/`, the
    deferred and skipped report channels, and the `connect` and `pull` commands.
    This spec amends none of that behavior.
  - `activity-identity` and `channel-merge` decide which page a delivered file
    belongs to and which file is its base, from the file's own content. A Garmin
    original ranks first under the default precedence, so pulling into an existing
    wiki changes the base of pages built from other copies. This spec adds no
    identity logic; Requirement 12 makes that visible.
  - `wellness-store` owns the series, the merge rules and the value ranges. This
    spec adds one source and one format.
  - `workout-docs` and `render/attribution` already attribute Garmin from file
    content and value origins, so this spec adds no attribution logic.
  - `plugin-api`'s connector plugin slot is separate and stays open for other
    sources.

## Requirements

### Requirement 1: Connecting with a Personal Key
**Objective:** As an athlete, I want to connect my Garmin account once with a key I created myself, so that later pulls run unattended and neither my password nor a session is ever stored.

#### Acceptance Criteria
1. The Garmin connector shall declare exactly one credential field, the athlete's Personal API key, marked secret, and shall declare the pull-activities and pull-wellness capabilities and no other.
2. When `fitdocs connect` verifies a key for a Garmin instance, the Garmin connector shall make exactly one token request with that key, shall discard the token it receives, and shall never repeat the request, whatever Garmin answers.
3. When Garmin issues a token during verification, the Garmin connector shall report that no scopes were granted, recording the scopes as absent rather than as an empty grant, and shall record no expiry, because a key's expiry is stated only on Garmin Connect.
4. If Garmin answers the token request as unauthorized or forbidden, the Garmin connector shall report a rejected key, stating that the key may be wrong, expired or deleted, and naming the next step: create a new key on Garmin Connect and run `fitdocs connect` again.
5. If Garmin answers the token request as rate-limited, the Garmin connector shall report a rate limit with any wait Garmin states; if it answers with a server error or any other status that is not success, the Garmin connector shall report the service as unavailable, naming the status.
6. If Garmin answers the token request as a success with a body that is not a token, the Garmin connector shall report that the answer was not understood, and shall not quote the body.
7. The Garmin connector shall take no service address, account identifier or credential from the settings file.

### Requirement 2: Configuring the Connector
**Objective:** As an athlete, I want the connector to work with no settings of its own, so that there is nothing to get wrong and no way to configure access Garmin might throttle.

#### Acceptance Criteria
1. Where a connectors instance names the Garmin connector, the Garmin connector shall accept no settings beyond those the fitdocs CLI defines for every instance.
2. The Garmin connector shall ignore instance keys it does not recognize.
3. The Garmin connector shall apply the pacing and the per-pull limits of Requirements 4 and 9 as fixed values that no setting changes.

### Requirement 3: Listing Activities
**Objective:** As an athlete, I want each pull to list exactly the Garmin activities in its window, and my whole history the first time, so that I need no data export and nothing already handled is fetched again.

#### Acceptance Criteria
1. When a pull lists a Garmin instance with an earliest start time, the Garmin connector shall list every activity of the key's owner that starts at or after that time, through the moment of the pull, and shall list no activity whose stated start is earlier.
2. While a pull gives no earliest start time (the instance has never recorded a watermark and no `--since` date is given), the Garmin connector shall list the key owner's whole activity history.
3. The Garmin connector shall list each Garmin activity at most once per pull, however the listing is split into requests, including when an activity arrives on Garmin while the listing is in progress.
4. The Garmin connector shall list a multisport activity once, as Garmin's default listing does, and shall not list its legs separately.
5. The Garmin connector shall carry each listed activity's start time as a UTC instant, its sport and its elapsed duration when Garmin states them in its documented form, and shall carry each as absent otherwise, never as zero, an empty string or a default; it shall state no revision, because an activity's original file does not change.
6. If a listing response is not a list of activity objects, or an entry has no positive whole-number identifier, the Garmin connector shall end that instance's pull with an error naming what was malformed, shall not quote the response, and shall never guess at the entry.
7. The Garmin connector shall keep nothing else from a listing entry: no activity name, location, owner field or summary value reaches a report, the ledger, the inbox or any file under the data root.

### Requirement 4: Pacing and the Per-Pull Limit
**Objective:** As an athlete with years of history, I want the first pull to proceed in safe steps that resume by themselves, so that I never risk my access by flooding Garmin and never lose progress to one long run.

#### Acceptance Criteria
1. The Garmin connector shall leave at least 2.5 seconds between the end of one request to Garmin and the start of the next distinct request, not counting the transport's bounded retries of one request.
2. The Garmin connector shall offer at most 200 activities for fetching in one pull, oldest first, counting only activities not already finally recorded in the instance's ledger.
3. While more activities remain than the limit allows, the fitdocs CLI shall report one deferred entry stating how many remain and that the next `fitdocs pull` continues, and that a pull started with `--since` continues only when given the same `--since`.
4. When a pull stops at the limit and nothing failed, the fitdocs CLI shall exit with the success code.
5. When `fitdocs pull` runs again without `--since` after a first pull stopped at the limit, the Garmin connector shall continue from where that pull stopped, shall fetch nothing already recorded, and shall reach the end of the history in as many pulls as the limit requires.
6. Where `--since` is given on an instance's first pull, the Garmin connector shall list only activities from that date on, under the same pacing and limit.

### Requirement 5: Downloading the Original File
**Objective:** As an athlete, I want the file fitdocs delivers to be exactly what my device recorded, so that a page is built from real device data and an upload from another app is named rather than mistaken for one.

#### Acceptance Criteria
1. When a pull fetches a Garmin activity, the Garmin connector shall download that activity's original file.
2. When the download is a ZIP archive with exactly one member and that member is a FIT file, the Garmin connector shall hand over that member's bytes unmodified, adding no marker, so that the drain and every later identity decision see exactly the file Garmin stored.
3. If the one member is a GPX or TCX document, the Garmin connector shall decline the activity with a reason naming the format, so that the fitdocs CLI records it as skipped, delivers nothing and never downloads it again.
4. If the one member is neither a FIT file nor a GPX or TCX document, the fitdocs CLI shall record the activity as skipped because the original is not a FIT file, and shall deliver nothing.
5. If Garmin reports that it holds no file for the activity, the Garmin connector shall decline the activity with a reason saying so.
6. If the download is not a readable ZIP archive, has no member or several members, or its member would exceed the transport's response-size bound, the Garmin connector shall report that activity's fetch as failed, so that it stays unrecorded and the next pull tries it again.
7. The Garmin connector shall never use a ZIP member's name as a path, and shall write neither the archive nor a member anywhere except through the framework's delivery.

### Requirement 6: Failures and Rate Limits
**Objective:** As an athlete, I want a refused key, a restriction, a rate limit or an outage reported by name with my next step, so that I can act on it and nothing keeps hitting Garmin after it has said no.

#### Acceptance Criteria
1. If Garmin answers the token request during a pull as unauthorized or forbidden, or a listing or download request as unauthorized, the fitdocs CLI shall end that instance's pull, report a rejected key with the step to create a new key and reconnect, and shall not repeat the request.
2. If Garmin answers a listing or download request as forbidden, the fitdocs CLI shall end that instance's pull and report that Garmin refused the request, that Garmin's terms let it restrict access, and that the key's status can be checked on Garmin Connect; the report shall not tell the athlete to report a fitdocs bug.
3. If a listing or download request is still rate-limited after the transport's bounded retries, the fitdocs CLI shall end that instance's pull, stating that Garmin is limiting requests and that the next pull resumes where this one stopped.
4. If a listing request still meets a server error after the transport's bounded retries, the fitdocs CLI shall end that instance's pull, stating that Garmin is unavailable and that the next pull resumes where this one stopped.
5. If a download request still meets a server error after the transport's bounded retries, the Garmin connector shall report that activity's fetch as failed, naming the status, and shall continue with the instance's remaining activities.
6. If five consecutive downloads in one pull meet a server error, the fitdocs CLI shall end that instance's pull, stating that Garmin appears unavailable and that the next pull resumes where this one stopped.
7. If a listing request is answered with any other status that is not success, the fitdocs CLI shall end that instance's pull naming the status; if a download request is, the Garmin connector shall report that activity's fetch as failed, naming the status, and shall continue.
8. The Garmin connector shall report statuses and its own wording, and shall never print or record a response body from Garmin.

### Requirement 7: The Key, the Token and What Reaches Garmin
**Objective:** As an athlete bound by Garmin's terms, I want my key kept to Garmin's token call and my access kept read-only, so that I never breach "personal to you" through fitdocs.

#### Acceptance Criteria
1. The Garmin connector shall send the key only in the token request to Garmin's token address, and shall never send it to any other host, including any relay or service fitdocs operates.
2. When a pull first needs Garmin's data, the Garmin connector shall obtain one token in a single attempt, shall keep it only in memory for that pull, and shall never store it.
3. The Garmin connector shall never place the key, the token or any encoded form of either in a request address, a report, a ledger, an exception message, a delivery, the inbox or any file under the data root.
4. The Garmin connector shall send every request through the fitdocs transport, addressed only to Garmin's documented Personal API host, so that each carries the fitdocs User-Agent.
5. The Garmin connector shall make no request that changes anything at Garmin, and shall request nothing beyond the token, the activity listing, activity files and the wellness records Requirement 9 names.

### Requirement 8: What the Ledger Records
**Objective:** As an athlete, I want each pulled activity recorded against Garmin's own id, so that a second pull fetches nothing new and a page's source file can be traced back to the remote activity.

#### Acceptance Criteria
1. The Garmin connector shall identify each listed activity by Garmin's own activity identifier, unchanged, so that the instance's ledger maps each fetched file's content hash to that identifier.
2. When a pull runs twice over the same range with no new activity on Garmin, the fitdocs CLI shall fetch nothing in the second pull.
3. When a Garmin original is byte-identical to a file already in the archive, the fitdocs CLI shall record it as already held and deliver no second copy.

### Requirement 9: Listing and Packaging Wellness
**Objective:** As an athlete who wears a Garmin device, I want my daily wellness delivered with the same command, so that months or years of it arrive without an export and a changed day is delivered again.

#### Acceptance Criteria
1. Where an instance has not enabled wellness, the Garmin connector shall make no wellness request.
2. While a wellness pull gives no earliest date, the Garmin connector shall start from the date of the key owner's oldest activity, or from one year before the pull when the account has no activity.
3. The Garmin connector shall cover at most 1,096 consecutive days of wellness in one pull, oldest first and through the day after the pull's date in UTC, so that the next pull continues from where this one stopped with no `--since`.
4. The Garmin connector shall request daily summaries, sleep summaries, HRV summaries and weight records, shall keep each request within Garmin's published range limit for that record type, and shall list each date at most once.
5. The Garmin connector shall merge what Garmin returns for one date into one wellness day, and shall list no day for a date on which Garmin returned nothing.
6. If Garmin answers that it has no data for a window, the Garmin connector shall treat that as no records for that window and not as an error.
7. The Garmin connector shall give each day a revision derived from the content of its records, so that a day is delivered again only when its records change.
8. When the Garmin connector packages days, it shall produce one named, versioned delivery form holding each day's records verbatim, sorted by date with no date repeated, stamped with the time they were fetched so that a later delivery of a day is recognizably later.
9. If a wellness response is not in its documented form, the Garmin connector shall end the wellness pull with an error naming what was malformed, shall not quote the response, and shall never guess at the record.

### Requirement 10: Reading the Delivery into the Wellness Series
**Objective:** As an athlete, I want Garmin's daily values in my wellness series, tagged by source and consistent with my data export, so that recovery and workout pages use them and absent values stay absent.

#### Acceptance Criteria
1. The wellness inbox shall recognize the delivery as a format of its own under a source of its own, distinct from the Garmin export format and its source.
2. When the fitdocs CLI reads a delivery, it shall take resting, minimum and maximum heart rate, steps, average stress level, the highest and lowest body battery, and average SpO2 from the day's daily summary, and respiration from the day's sleep summary.
3. When the fitdocs CLI reads a day's sleep summary, it shall derive total sleep and the deep, light, REM and awake stages the same way it does for the Garmin export, and shall read no sleep metric when the stage total is not positive.
4. When the fitdocs CLI reads a day's weight records, it shall take the day's latest weight, converted from grams to kilograms.
5. If a value is missing, null or outside the metric's accepted range, the fitdocs CLI shall leave that metric absent for that day, never zero or a default.
6. The fitdocs CLI shall not read HRV or VO2max from a delivery, and shall keep HRV records in the archived delivery, so that a later version can read them with no new pull.
7. The fitdocs CLI shall never read Garmin's hydration figures as the subjective hydration rating.
8. Where the Garmin export and this source both supply a day's metric, the fitdocs CLI shall keep both source values and shall leave the export's value canonical, so that existing canonical values do not change.
9. When a day is delivered again, the fitdocs CLI shall let the later delivery's values replace the earlier delivery's values from this source.
10. The fitdocs CLI shall attribute every value read from a delivery to Garmin, so that the existing wellness attribution names Garmin wherever such a value is shown.
11. If a delivery cannot be read, the fitdocs CLI shall refuse it with a message like any other wellness format, leave the series unchanged by it, and name it in the drain's report.
12. When a data root with existing wellness first runs a version that registers this source, the fitdocs CLI shall rebuild the series once with no action from the athlete and no loss of values.

### Requirement 11: Wellness Failures
**Objective:** As an athlete, I want a failed wellness request reported once with my next step, so that my activities still arrive and nothing retries in a loop.

#### Acceptance Criteria
1. If an instance's activity pull ended with a rejected key, a refusal or a rate limit, the fitdocs CLI shall make no wellness request for that instance in that pull.
2. If an instance's activity pull ended for any other reason, the fitdocs CLI shall still run that instance's wellness pull.
3. If Garmin answers a wellness request as unauthorized, the fitdocs CLI shall end the instance's pull and report a rejected key with the step to create a new key and reconnect, and shall not repeat the request.
4. If Garmin answers a wellness request as forbidden, the fitdocs CLI shall end the wellness pull and report that Garmin refused the request, that Garmin's terms let it restrict access, and that setting `wellness = false` stops the request.
5. If a wellness request is still rate-limited, or still meets a server error, after the transport's bounded retries, or is answered with any other status that is not success, the fitdocs CLI shall end the wellness pull, stating which and that the next pull resumes where this one stopped.
6. If a wellness pull ends early, the fitdocs CLI shall keep every wellness delivery already made and recorded, deliver no day from the incomplete window, and leave the wellness mark where it was.

### Requirement 12: Documentation and the Terms
**Objective:** As an athlete, I want the docs to say plainly how to set this up, what I agree to with Garmin, and what a first pull does to my wiki, so that I decide with my eyes open.

#### Acceptance Criteria
1. The fitdocs documentation shall state how to create a key on Garmin Connect, how to name the connector in `fitdocs.toml`, how to run `fitdocs connect`, the environment override, and how to enable wellness.
2. The fitdocs documentation shall state that a key expires after the period chosen when creating it (30, 90, 180 or 365 days), that Garmin sends a reminder, that a key is shown once, and that renewing means creating a new key and running `fitdocs connect` again.
3. The fitdocs documentation shall state that the athlete accepts Garmin's own terms when creating a key, quote the terms' words that a key is "personal to you" and for "applications, services, or tools that you develop or operate for your own use", and state that Garmin may throttle or restrict access and revoke a key.
4. The fitdocs documentation shall state that fitdocs is not affiliated with or endorsed by Garmin, shall use the name Garmin only descriptively, shall show no Garmin logo, and shall claim no permission from Garmin.
5. The fitdocs documentation shall state what a first pull does: full history oldest first, about how long each step takes, the per-pull limit and how it resumes, and how `--since` narrows it.
6. The fitdocs documentation shall state that on an existing wiki the first `sync` after a pull makes a Garmin original the main file of pages built from other copies, so that those pages re-render, some may move or change time, and regions the athlete owns are kept; it shall name `pull` without `--sync` as the way to hold files back and `[identity] precedence` as the way to keep an existing base.
7. The fitdocs documentation shall state what the connector does not do: uploads from other apps are skipped as GPX or TCX, women's health, courses and training are not pulled, HRV and VO2max are not read yet, and accounts on Garmin's China service are not supported.
8. The fitdocs documentation shall state that an athlete moving from intervals.icu can stop fetching Garmin's copies there through that connector's `sources` setting.
9. The fitdocs documentation shall correct every statement this connector makes false, including the terms-first policy's list of connectors, the list of built-in connectors and the wellness source order, and shall add a changelog entry with the settings-schema note and the action an athlete takes.

### Requirement 13: The Live Check
**Objective:** As the maintainer, I want the finished connector exercised against my own account before release, so that nothing ships on a guess about a service fitdocs cannot test offline.

#### Acceptance Criteria
1. The Maintainer shall run the connector end to end against the maintainer's own Garmin account, into a scratch data root and never the real wiki: connect, one pull up to the per-pull limit, the drain, and a wellness pull.
2. The Maintainer shall record whether that run met any rate limit, how long it took, what a deleted or wrong key reports, and whether any activity fell outside the shapes the design assumes.
3. The Maintainer shall record the findings in the spec's research record as shapes and vocabulary only, never an activity identifier, account identifier, date, name, location, file or key.
4. If a finding contradicts an assumption the design marks as to be confirmed, the Specification Process shall amend the design and every affected task before the spec is marked complete.
5. The Specification Process shall treat the live check as the maintainer's own task: no automated agent performs it, records it or marks it done unless the maintainer explicitly asks a session to run it with the maintainer's key, no subagent is given the key, and no other implementation task waits for it except the final completion gate.

### Requirement 14: Provenance, Privacy and the Project's Limits
**Objective:** As the maintainer of a public repository, I want this connector built only from public material, offline-tested and small in surface, so that nothing confidential crosses over and nothing else has to change.

#### Acceptance Criteria
1. The Specification Process shall derive the connector, its documents and its tests only from Garmin's public Personal API material and from recorded measurement, never from Garmin's developer portal, the hosted deployment's private notes, or any third party's copy of Garmin's documents; implementers and reviewers shall not open those.
2. The Specification Process shall write the connector's code in this repository and copy none from Garmin's client without the attribution its Apache-2.0 license requires.
3. The Garmin connector's tests shall run with no network access, against synthesized service responses and synthesized FIT bytes that contain no personal data.
4. The Specification Process shall add no test that reads documentation, changelogs or specs, shall delete rather than update a documentation-binding test this work would otherwise have to change, and shall keep every code guard in such a test file enforced by moving it first.
5. The Garmin connector shall add no runtime dependency, no fitdocs command and no name to the connectors package's public surface.
6. The Garmin connector shall leave the document-format and contract versions unchanged, unless the design records why one must move.
7. The Specification Process shall record the amendments this makes to `connectors` and `wellness-store`, and shall correct the `fitdocs pull` sentence in `.kiro/steering/tech.md` and the connector list in `.kiro/steering/structure.md`, in the change that lands them.
