# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete whose daily wellness (resting HR, HRV,
sleep, SpO2, steps, VO2max, weight) reaches intervals.icu. It arrives there
from a watch or ring intervals.icu connects to (Garmin, COROS, Polar, Suunto,
Oura, WHOOP, Zepp, Huawei) or from Apple Health through a bridge app such as
HealthFit. For the maintainer that is 483 days relayed from Apple Health by
HealthFit since 2025-06-17. For athletes on other platforms intervals.icu is
the one practical aggregator.

**Current situation.** fitdocs pulls only activity files from intervals.icu.
The connector protocol reserves a pull-wellness capability, but nothing drives
it: a connector may declare it, registration checks no operation for it, and
no command invokes it. The pull pipeline is FIT-only: fetched bytes must carry
a FIT header, deliveries are always named `.fit`, the removal of archived
deliveries looks only in the FIT archive, and the ledger is keyed by remote
activity. Once `wellness-store` lands, the drain reads an intervals.icu
wellness file dropped into the inbox, but the athlete would have to export and
drop one by hand every day.

**What should change.** The athlete enables wellness on an intervals.icu
connector instance. `fitdocs pull` then lists the account's wellness days and
delivers into the inbox wellness files holding the days whose records changed
since the last pull, the whole account's history the first time, in the
delivery form `wellness-store` reads. It records what it delivered in the
instance's ledger and removes its own delivery once the drain has archived it.
A second pull with nothing changed delivers nothing. Fields intervals.icu
receives from Garmin are attributed to Garmin, as intervals.icu's API terms
require. The connector stays a thin fetcher: it never parses, merges or stores
wellness.

Source: `.kiro/specs/wellness-pull/brief.md`; Phase 12 of
`.kiro/steering/roadmap.md`. Dependencies: `wellness-store`. Extends
`connectors` and `intervals-connector`.

## Introduction

Phase 8 let a connector fill the inbox with activity files. This feature
extends that rule to wellness: a connector fills the inbox with wellness
files, and the drain, which `wellness-store` teaches to archive them and merge
them into the daily series, does the rest. A wellness file the pull delivers
and one the athlete saved by hand are handled identically.

Terms used below:
- A **wellness day** is a calendar date for which a service holds a wellness
  record. A **wellness record** is the service's own object for one wellness
  day, with all its fields.
- A day's **revision** is a token the service gives that changes whenever the
  day's record changes (for intervals.icu, the record's update time).
- A **wellness delivery** is one file the pull writes into the inbox, holding
  the records of some wellness days. A delivery is **pending** until a later
  pull finds it archived or gone.
- The **wellness archive** is `wellness-store`'s `wellness-archive/` in the
  data root.
- An instance's **wellness mark** is the newest date its last complete
  wellness pull covered. The **look-back** is the instance's existing
  `lookback_days` setting.
- A field's **origin** is the upstream platform intervals.icu imports that
  field from (`garmin`, `oura`, ...), where intervals.icu's settings say so.

## Boundary Context
- **In scope**: driving the pull-wellness capability (its operations, the
  registration rule and the per-capability run of a pull); the per-instance
  `wellness` setting; listing wellness days and detecting changed ones; the
  delivery of non-FIT files into the inbox and the check each one passes;
  the ledger's wellness records and its format version; removing archived
  wellness deliveries; the wellness report and exit codes; the intervals.icu
  wellness listing, packaging, attribution and failure mapping; the live check
  against the maintainer's account; the documentation, the packaged skill's
  report table, the changelog, and the amendment records on `connectors` and
  `intervals-connector`.
- **Out of scope**: recognizing, archiving, parsing, merging or storing
  wellness values (`wellness-store`); intervals.icu's own computed fields
  (fitness, fatigue, ramp rate, load, eFTP and W′), which pass through the
  delivered file unread and are never imported; writing anything to
  intervals.icu; intervals.icu custom wellness fields; connectors for other
  services; removing from fitdocs a day intervals.icu deletes; the Garmin
  export import (`wellness-store`'s route); any document, page, chart or
  index change; the recovery command's place in the no-network command list
  (`recovery`).
- **Adjacent expectations**:
  - `wellness-store` recognizes the delivered file by its content, archives
    it as its original bytes at the archive location the pull checks, and
    treats a day re-delivered with a later update time as replacing every
    field of the earlier record, including a field that became empty. It
    reads only the wellness fields it maps.
  - The drain treats a wellness delivery as it treats any inbox file. It
    never deletes one; only the next pull removes the pull's own archived
    delivery.
  - The activity pull keeps its behavior, its report channels and its FIT
    check. An instance without wellness enabled pulls exactly as before.
  - Pages that show wellness values (`recovery`, `workout-wellness`) show the
    Garmin attribution for values whose origin is `garmin`. This feature
    supplies the origin and shows nothing.

## Requirements

### Requirement 1: Driving the Pull-Wellness Capability
**Objective:** As a connector author (the intervals.icu connector now, a Garmin or HealthFit connector later), I want pulling wellness defined in the published protocol, so that a connector declares it once and every pull drives it the same way.

#### Acceptance Criteria
1. The connector framework shall drive the pull-wellness capability as well as the pull-activities capability, and shall keep the other seven capabilities reserved: a connector may declare one, registration requires no operation for it, and no command invokes it.
2. The connector framework shall define pulling wellness as two operations: a listing of wellness days from an optional earliest date, each listed day carrying its date, its revision where the service states one, and the service's record for that day; and a packaging of chosen listed days into the bytes of one file, together with the file's extension, the name of the wellness format that archives it, and the platforms it attributes fields to.
3. The connector framework shall hand each listed day's record back to the packaging operation without reading it, so that no part of fitdocs outside the connector and the wellness format interprets a service's record.
4. If a connector that declares the pull-wellness capability lacks either wellness operation, the connector framework shall reject its registration with a reason naming the missing operation, and shall register nothing.
5. Where a service states no revision for a listed day, the connector framework shall carry that revision as absent, never as an empty string or a default.
6. The connector framework shall give a wellness operation only the instance's configuration, its credentials, the transport and the clock, and shall take only wellness listings and packaged bytes from it; it shall never parse, merge, store or render a wellness value.
7. The connector framework shall add the wellness operations and their value types to its published surface, and the automated surface pin shall list them.

### Requirement 2: Enabling Wellness for an Instance
**Objective:** As an athlete, I want to switch wellness on for each connector instance myself, so that upgrading fitdocs never starts downloading my health data unasked.

#### Acceptance Criteria
1. Where an instance's connector declares the pull-wellness capability, the fitdocs CLI shall accept an optional `wellness` key in the instance's table, true or false, defaulting to false.
2. While wellness is not enabled for an instance, `fitdocs pull` shall make no wellness request for that instance, print no wellness report for it, and write its ledger exactly as it did before this feature.
3. If an instance's `wellness` key is not a boolean, or is true while the instance's connector does not declare the pull-wellness capability, the fitdocs CLI shall stop with a configuration error naming the settings file, the instance and the key, before any network request and before any write.
4. The fitdocs CLI shall treat `wellness` as one of the framework's own instance keys, as it treats `lookback_days`, and shall not hand it to the connector's own settings validation.
5. The folder connector shall not declare the pull-wellness capability, and shall continue to list only `.fit` files.
6. If an instance has nothing to pull (its connector declares no capability this version drives, or declares pull-wellness alone while wellness is not enabled), `fitdocs pull` shall report that instance's failure, saying it has nothing to pull and which setting would change that.

### Requirement 3: Listing Wellness and Detecting Changed Days
**Objective:** As an athlete running pulls on a schedule, I want each pull to fetch only the wellness days that are new or changed, re-checking recent days, so that late arrivals and corrections reach my series and unchanged days are never delivered twice.

#### Acceptance Criteria
1. When a pull runs wellness for an instance that has a wellness mark, the fitdocs CLI shall list wellness days from the wellness mark less the instance's look-back.
2. While an instance has no wellness mark and no `--since` date is given, the fitdocs CLI shall let the connector list from the earliest date the connector documents, so that the instance's first wellness pull covers the account's whole history.
3. Where `--since DATE` is given, the fitdocs CLI shall list wellness days from that date instead.
4. The fitdocs CLI shall treat a listed day as changed when the instance's ledger records no revision for its date, or records a different one, and shall deliver every changed day and no unchanged day.
5. The fitdocs CLI shall decide which days changed from the ledger alone, so that a day missing from one listing is delivered by whichever later pull lists it.
6. If a listed day is malformed (its date repeats an earlier listed day's, or its revision is empty, longer than 512 characters, or holds a control character), the fitdocs CLI shall report it as a failure naming the date, deliver nothing for it, and leave it unrecorded.
7. When a wellness pull completes with nothing failed, the fitdocs CLI shall advance the instance's wellness mark to the newest date the listing covered, and shall never advance it across dates no pull has listed.
8. Where `--dry-run` is given, the fitdocs CLI shall list wellness days, report which dates would be delivered, and package, deliver, remove and record nothing.
9. When a pull runs twice with no wellness change at the service, the second pull shall deliver nothing and leave the ledger byte-identical.
10. The fitdocs CLI shall never remove or alter a delivery, an archive entry or a ledger record because the service no longer lists a day.

### Requirement 4: Delivering Wellness into the Inbox
**Objective:** As an athlete, I want pulled wellness to arrive in the inbox as ordinary wellness files the drain reads, whole and in bounded pieces, so that a pulled file and one I saved by hand are handled identically.

#### Acceptance Criteria
1. When a pull has changed days to deliver, the fitdocs CLI shall package them into one file per calendar year of their dates, and shall deliver each file into the inbox, inside the instance's subdirectory, named `wellness-<first date>_<last date>` followed by the extension the connector declared.
2. The fitdocs CLI shall write each wellness delivery under a dot-prefixed temporary name and then rename it, and shall write the packaged bytes unmodified.
3. If a wellness delivery's name is already taken by another file, the fitdocs CLI shall deliver under a distinct name derived from the content, keeping the declared extension, and shall never overwrite an existing file.
4. If a package fails the check for its declared extension (a `.json` package that is not one well-formed JSON document, or is larger than the largest wellness file the drain recognizes; a package declaring an extension fitdocs has no wellness check for, `.fit` among them, or a format name that is not a lowercase slug), the fitdocs CLI shall deliver nothing for its days, report a failure naming their date span, and leave them unrecorded.
5. The fitdocs CLI shall keep the FIT check on fetched activity files exactly as it is, so that an activity file without a FIT header is still skipped and never delivered.
6. When a package's bytes are identical to an entry the wellness archive holds for its declared format, or to a still-pending wellness delivery of the same instance, the fitdocs CLI shall record its days as held and deliver no second copy.
7. If packaging or delivering one year's days fails for a reason other than authentication, the fitdocs CLI shall report a failure naming that year's date span, leave its days unrecorded, and continue with the remaining years.

### Requirement 5: The Ledger's Wellness Records
**Objective:** As an athlete, I want the instance's ledger to remember which wellness days it delivered and at which revision, so that unchanged days are never fetched again and a lost delivery is caught up.

#### Acceptance Criteria
1. The connector framework shall record in the instance's ledger: for each delivered or held wellness day, its date, the revision delivered and the content hash of the file that carried it; for each pending wellness delivery, its inbox-relative location, its content hash, and the wellness format and extension it was declared with; the instance's wellness mark; and the platforms the instance's last wellness delivery attributed fields to.
2. The connector framework shall write the wellness records in a stable order with no clock-derived value, so that a pull that changes nothing leaves the ledger byte-identical.
3. While an instance has never pulled wellness, the connector framework shall write its ledger exactly as before this feature, byte for byte, including its format version.
4. When a ledger holds wellness records, the connector framework shall record a newer ledger format version in it, so that a fitdocs version that does not read wellness records refuses the ledger instead of discarding them.
5. If a ledger's wellness records are not in their documented form, or appear under a format version that does not hold them, the connector framework shall fail that instance's pull with a message naming the file, and shall never overwrite or rebuild it.
6. The connector framework shall save the wellness records when the instance's pull ends, including in failure or on interruption, so that every wellness delivery already made is recorded.
7. The connector framework shall record wellness content hashes in the form the wellness archive names its entries by.

### Requirement 6: Removing Archived Wellness Deliveries
**Objective:** As an athlete, I want the pull to clean up its own wellness files once they are archived, and never anything else, so that my inbox does not fill with copies of the archive.

#### Acceptance Criteria
1. When a pull starts for an instance and `--dry-run` is not given, the fitdocs CLI shall remove each of the instance's pending wellness deliveries whose content hash names an entry of its declared format in the wellness archive and whose file's current bytes still have that hash, and shall report each removal.
2. The fitdocs CLI shall never remove an inbox file the ledger does not record as the instance's pending wellness delivery, a delivery whose current bytes differ from what was delivered, or a delivery the wellness archive does not hold, including one the drain quarantined or reported as unrecognized.
3. If a pending wellness delivery has disappeared from the inbox before the wellness archive held it, the fitdocs CLI shall forget each day whose latest recorded delivery it was, and shall move the wellness mark back before the earliest such day, so that the next pull lists and delivers those days again.
4. When a pending wellness delivery is archived and its file has since been moved, deleted or changed, the fitdocs CLI shall stop tracking it and leave any file at its location untouched.
5. If reading or removing a pending wellness delivery fails, the fitdocs CLI shall keep it pending and report a deferral naming its location.
6. The fitdocs CLI shall resolve an instance's pending wellness deliveries at every pull that is not a dry run, whether or not wellness is still enabled for the instance.

### Requirement 7: Wellness from intervals.icu
**Objective:** As an athlete whose wellness reaches intervals.icu, I want the intervals.icu connector to list and package my wellness records faithfully, so that months of wellness arrive with one command and nothing of intervals.icu's own model is mistaken for a measurement.

#### Acceptance Criteria
1. The intervals.icu connector shall declare the pull-activities and pull-wellness capabilities and no other.
2. When the intervals.icu connector lists wellness, it shall request the key's own athlete's wellness records over date windows of at most one year that together cover the earliest date through the day after the pull's date in UTC, shall list each date at most once, and shall take each day's date from the record's `id` and its revision from the record's `updated` time.
3. While no earliest date is given, the intervals.icu connector shall list wellness from 2010-01-01, so that the first wellness pull covers the account's whole history.
4. Where a record carries no `updated` time as text, the intervals.icu connector shall give the day a revision derived from the record's whole content, so that the day is delivered again only when its record changes.
5. If a wellness listing response is not a list of objects, or one of its records has no `id` of the form `YYYY-MM-DD`, the intervals.icu connector shall end the wellness pull with an error naming what was malformed, and shall never guess at the record.
6. The intervals.icu connector shall read nothing from a wellness record except its `id` and `updated` fields, and shall package every record verbatim, including intervals.icu's own fitness, fatigue, ramp-rate, load and sport-information fields, which fitdocs never imports.
7. When the intervals.icu connector packages days, it shall produce the intervals.icu wellness delivery form `wellness-store` reads: the delivery form's name and version, the chosen days' records sorted by date with no date repeated, and the attribution map when there is one, serialized in one canonical form with no time of the pull, so that two identical deliveries are byte-identical.
8. The intervals.icu connector shall make one listing request per date window and one request for the athlete's settings per package.

### Requirement 8: Attributing Wellness to the Platform That Measured It
**Objective:** As an athlete whose intervals.icu account relays Garmin's or another platform's wellness, I want each field attributed to the platform that supplies it, so that my wiki credits Garmin as intervals.icu's API terms require, and never credits Garmin for another device's data.

#### Acceptance Criteria
1. When the intervals.icu connector packages days, it shall read the athlete's per-platform wellness import settings, and shall attribute a field to a platform only when exactly one platform set to import wellness lists that field.
2. Where no platform, or more than one, lists a field, the intervals.icu connector shall attribute that field to no platform.
3. The intervals.icu connector shall name each platform by a lowercase token derived from intervals.icu's own name for the integration (`garmin` for Garmin), and shall attribute nothing to a platform it cannot name in that form.
4. The intervals.icu connector shall decide attribution from the athlete's settings at the time of the pull alone, never from a record's values.
5. If intervals.icu withholds or empties a field the delivery attributes to a platform, the intervals.icu connector shall deliver the record as intervals.icu sent it, so that fitdocs treats the missing value as absent, never as zero.
6. When a wellness delivery attributes no field to a platform that the instance's previous wellness delivery attributed fields to, the fitdocs CLI shall report a notice naming the platform and stating that the platform's own export remains a route for its wellness, without counting the notice as a failure.

### Requirement 9: Failures, Rate Limits and the Garmin Restriction
**Objective:** As an athlete, I want a refused, limited or broken wellness request reported once by name with my next step, so that I can act on it, my activities still arrive, and nothing retries in a loop.

#### Acceptance Criteria
1. If intervals.icu answers a wellness request as unauthorized, the fitdocs CLI shall end the instance's pull, report a rejected key with the step to reconnect, and not repeat the request.
2. If intervals.icu answers a wellness request as forbidden, the fitdocs CLI shall end the instance's wellness pull, quote the service's message with every secret removed, and name the next steps: that intervals.icu may be withholding data it received from Garmin, that setting `wellness = false` stops the request, and that Garmin's own data export is the route for Garmin wellness.
3. If a wellness request is still rate-limited, or still meets a server error, after the transport's bounded retries, the fitdocs CLI shall end the instance's wellness pull, stating which, and that the next pull resumes where this one stopped.
4. If a wellness listing request is answered with any other status that is not success, the fitdocs CLI shall end the instance's wellness pull, naming the status.
5. If an instance's wellness pull ends early, the fitdocs CLI shall keep every wellness delivery already made and recorded, leave the wellness mark where it was, and continue with the remaining instances.
6. If an instance's activity pull ends for a reason other than an authentication failure, the fitdocs CLI shall still run that instance's wellness pull; if it ends with an authentication failure, the fitdocs CLI shall not.
7. The fitdocs CLI shall not deliver a wellness day again because the drain could not use the delivery that carried it; that delivery stays pending in the inbox, and the drain's report names it.
8. The intervals.icu connector shall never place the key, or any encoded form of it, in a request address, a report, the ledger, an exception message, a wellness delivery, or any file under the data root.

### Requirement 10: The Wellness Pull Report and Exit Codes
**Objective:** As an athlete, or the agent running my routine, I want the pull report to say what wellness was listed, delivered, unchanged, held, failed or noticed, and the exit code to reflect wellness failures, so that a scheduled run is auditable.

#### Acceptance Criteria
1. When `fitdocs pull` completes, the fitdocs CLI shall print, for each instance that ran a wellness pull, a wellness counts table with one named row for each channel (days listed, files delivered, days unchanged, dates that would be delivered, held, failed, notices, and the wellness error), including when a channel is empty.
2. The fitdocs CLI shall list beneath the wellness counts each delivered file with its date span and number of days, each held date span, each failure and notice with its reason, and the wellness error with its next step.
3. Where `--dry-run` is given, the fitdocs CLI shall report, for each instance that would pull wellness, the dates it would deliver in place of delivered files.
4. The fitdocs CLI shall report a removed wellness delivery, and one that could not be removed yet, in the instance's existing removed and deferred channels.
5. The fitdocs CLI shall exit with the failure code when a wellness pull ended early or reported a failure, and shall not count unchanged days, held days or notices as failures.
6. The fitdocs CLI shall order every wellness report entry deterministically: delivered and held files by date span, would-deliver dates by date, and failures and notices by subject.
7. While an instance did not run a wellness pull, the fitdocs CLI shall print no wellness table for it.

### Requirement 11: The Live Check
**Objective:** As the maintainer, I want the assumptions the wellness pull and `wellness-store`'s intervals.icu format make about intervals.icu confirmed against my own account, so that nothing ships on an unverified field name.

#### Acceptance Criteria
1. The live check shall confirm against the maintainer's intervals.icu account how the wellness listing answers a dated window: the form of a record's `id` and `updated`, whether each date bound is inclusive, whether a window ending after today is accepted, whether a one-year window is accepted and how large its response is, and how many records were updated long after their own date.
2. The live check shall record the names of the record fields present, and, for every field `wellness-store`'s intervals.icu format maps and for `sleepQuality`, whether it exists, its value type, and its count of non-empty values.
3. The live check shall record the athlete settings' per-platform wellness lists by name, each list's element type and length, how many of its elements name record fields, and the name and type of any per-platform setting that turns wellness import on or off.
4. The live check shall be run by the implementation's controller session, never by an implementer subagent, with the maintainer's key read from the maintainer's own environment file, making read-only requests only; the key shall never be printed, passed to a subagent, written to a file or committed.
5. The live check shall record its findings as field names, value types, booleans and counts only, never a wellness value, a date, an identifier or the key.
6. If a finding contradicts an assumption the design marks as to be confirmed, the specification process shall amend the design and add a repair task before the feature is complete; where it contradicts a field name or a field's form that `wellness-store`'s intervals.icu format reads, the repair shall be an amendment to that format in `wellness-store`.
7. No implementation task shall wait for the live check except the completion gate.

### Requirement 12: Documentation, Records and the Packaged Skill
**Objective:** As an athlete setting wellness up, an agent running my routine, or a maintainer, I want the wellness pull documented and every contract it touches restated, so that nothing about it is a surprise.

#### Acceptance Criteria
1. The connectors documentation shall describe the `wellness` key, the wellness pull, its re-check of recent days by the look-back, its first pull's whole-history backfill and `--since`, the wellness report, the delivery and removal of wellness files, and the ledger's wellness records and newer format version.
2. The connectors documentation's intervals.icu section shall describe enabling wellness, the attribution rule and its limits, the freshness trap (some platforms reach intervals.icu only when the athlete opens it, which the re-check covers), the possible Garmin restriction and the Garmin export route, that intervals.icu's computed fields are delivered but never imported, and that a day intervals.icu deletes is not removed from fitdocs.
3. The wellness documentation shall name the intervals.icu pull as a way wellness files reach the inbox, and link the connectors documentation.
4. The ownership contract's statement of what `fitdocs pull` writes shall name wellness deliveries and state that the pull never writes the wellness archive or the series, keeping every guarantee it already states.
5. The packaged workouts skill shall document the wellness report's channels in a table that an automated test binds to the report's fields, and shall tell the agent which of them need the athlete.
6. The changelog's unreleased section shall record the wellness pull, the `wellness` key, the attribution and the ledger format change, with the action a user must take: enabling wellness, and knowing that an older fitdocs refuses a ledger holding wellness records.
7. The `connectors` and `intervals-connector` specs shall each carry an amendment record for the changes this feature makes to them.

### Requirement 13: Offline, Deterministic and Private
**Objective:** As an athlete, I want the wellness pull to keep fitdocs's network, determinism and privacy rules, so that it is safe to run unattended.

#### Acceptance Criteria
1. The fitdocs CLI shall make wellness requests only during `fitdocs pull`; `sync`, `regen`, `check`, `index`, `query` and rendering shall make none, whether or not wellness is enabled.
2. The wellness pull shall add no runtime dependency.
3. The same listing, settings and ledger shall always produce the same wellness deliveries and the same ledger bytes, with no run date, run time or machine-specific value in either.
4. The wellness pull's tests shall run with no network access, against synthesized responses that contain no personal data.
5. No wellness value, date or identifier from a real account shall be committed to the repository.
