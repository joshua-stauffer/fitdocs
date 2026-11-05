# Implementation Plan

## Before You Start

- **Provenance (Req 14.1, 14.2).** Work only from this spec and from Garmin's public Personal API material named in `brief.md`. Do not open Garmin's developer portal, the hosted deployment's private notes, or any third party's copy of Garmin's documents. Write the code here; do not copy from Garmin's client.
- **No key.** No task here uses a real key or a network. Only 7.2 touches Garmin, and it belongs to the maintainer. Build every request from the design's "Service routes" table.
- **No documentation tests (Req 14.4).** Add no test that reads a doc, changelog or spec. If a task's change turns a documentation-binding test red, delete that test function in that task, and do not update it. A code guard in such a file moves first; that is 1.1.
- **Versions.** `CONTRACT_VERSION`, `DOC_VERSION`, the CLI command count and the connectors `__all__` count should not move. If one must, stop and record why in `design.md`.
- **Clock scan.** The boundary guard's clock scan is a raw substring match, so avoid spellings such as `x_time.timestamp()` in the connector module.

## Tasks

- [ ] 1. Foundation

- [x] 1.1 Move the service-neutral scan to its own test file
  - Move the `NeutralScan` guard and its tests out of the connector documentation test file, unchanged, into a test file of its own.
  - Change no assertion and no exemption entry in this move.
  - Done when the same scan tests pass from the new file, none remain in the old one, and the real-tree scan still flags an unadmitted host.
  - _Requirements: 14.4_

- [x] 1.2 Add the opt-in transport option for rate-limit retries
  - Add the `retry_rate_limits` request option, defaulting to today's behavior, and the matching keyword on the client's GET helper.
  - When it is off, a 429 returns after one attempt, while server errors and transport errors keep their bounded retries.
  - Done when tests show a 429 returned at once with the option off, a 503 still retried with it off, and an unchanged retry sequence with the default; each test fails if the check is removed or the default flips.
  - _Requirements: 4.7_
  - _Boundary: retry_rate_limits_

- [ ] 2. The Garmin wellness format

- [ ] 2.1 (P) Read the delivery into wellness values
  - Add the delivery envelope's recognition and the day reader beside the existing Garmin formats, sharing the existing sleep derivation by naming the respiration field it reads.
  - Map every row of the design's metric table, including grams to kilograms and `lastNightAvg` as RMSSD; attribute every value to origin `garmin`; give each day the full metric set as `covers` and `fetched_at` as its revision.
  - A section that is not an object, or a value that is not a finite number within the metric's accepted range, leaves only that metric absent. Only an envelope outside the documented form refuses the file.
  - The shared derivation refuses a non-number, so the new reader drops non-number and non-finite fields from a section before calling it. The export keeps refusing as it does today.
  - Do not read VO2max, and never read `hydration` as the subjective rating.
  - Done when tests cover each mapped metric, each absent form, the hydration decoy, one string stage leaving only that stage absent, a later `fetched_at` replacing and retracting an earlier value, a refused envelope, and the existing Garmin export tests still pass.
  - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.9, 10.10, 10.11, 14.3_
  - _Boundary: PERSONAL_FORMAT_

- [ ] 2.2 Register the source and format
  - Register `garmin-personal` as a device source and the delivery as its format, so that the default order becomes `garmin-export`, `garmin-personal`, `apple-health`, `intervals-icu`.
  - Update the behavior tests that pin the source and format lists and that order; delete any documentation-binding test this turns red.
  - Done when a delivery is recognized by exactly one format, no export recognizer claims it, it claims no export file, `validate_registry` passes, and a test shows the export's value stays canonical on overlap with both source values kept.
  - _Requirements: 10.1, 10.8, 14.4, 14.6_
  - _Boundary: PERSONAL_FORMAT_

- [ ] 3. The connector: declaration and activities

- [x] 3.1 (P) Declare and register the connector, and verify a key
  - Add the Garmin connector with its one secret credential field, the two capabilities, API-key auth, and settings that accept nothing and ignore unknown keys. Register it after Strava, and keep it out of `__all__`.
  - Verification makes exactly one token request with the given key and discards the token. It reports absent scopes and no expiry, and maps refused, rate-limited, unavailable and not-a-token answers per the design's error table, never quoting a body.
  - The registry requires the pull operations once the capabilities are declared, so define the four as stubs raising a named connector error; 3.3, 3.5, 4.1 and 4.2 replace them.
  - Add the module to the boundary guard's module list, and pin in its import set only what this task imports. Update all three registry order pins (intervals, relay, Strava publish tests). Delete any documentation-binding test this turns red.
  - Add the Personal API host to the neutral scan's table, admitting the connector module and all four named connector test files up front, because its keys are exact paths.
  - Build the token request from the design's "Service routes" table.
  - Done when `fitdocs connect` against a scripted transport stores the key after one request, each refused answer produces the design's message with no retry, and the key appears in no report or exception.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.1, 2.2, 7.1, 14.2, 14.5_
  - _Boundary: GarminConnector_
  - _Depends: 1.1_

- [x] 3.2 Add the per-pull state, pacing and rate-limit waits
  - Hold the per-pull state on the connector, keyed by the session's client: the token, the first-request flag, the waits so far, the consecutive failure count, and any token failure.
  - Mint at most one token per pull, on first need and in a single attempt. A failed mint, including a transport failure converted to the kept connector error, raises the same error again with no second request. Register the token and its header form as secrets before use, and never store them.
  - Send every Garmin GET through one helper that spaces distinct requests by 1 second through the injected sleep and turns the transport's 429 retries off.
  - In a pull, a token answer of 401 or 403 raises the rejected-key failure, 429 raises the rate-limit failure with no wait, and a server error, any other status, a body that is not a token, or a transport failure raises the kept connector error, so that wellness is suppressed only by the first two.
  - Extend the module's import pin with what this task adds.
  - On a 429: wait the stated time when it is at most 5 minutes, otherwise 30, 60, 120 and 240 seconds, at most 4 repeats of one request, and at most 15 minutes per pull; then stop with a rate-limit failure. A success restarts the schedule.
  - Done when tests record the exact sleeps: 1 second between requests and none before the first, each wait sequence, an over-long stated wait stopping at once, the 15-minute budget stopping across requests, a repeating short stated wait stopping after 4, a success restarting the wait schedule, each token answer mapped as above, and exactly one token request across repeated requests on one session, including after a failure.
  - _Requirements: 2.3, 4.1, 4.7, 4.8, 4.9, 6.1, 6.3, 7.2, 7.3, 7.4_
  - _Depends: 1.2_

- [ ] 3.3 List activities
  - Use the design's "Service routes" table. Page the listing oldest first in pages of 200 until a short page, always sending both date filters: the start is one day before any given start time, or the design's earliest date with none. With a start time, each entry is then filtered by its UTC start. Leave Garmin's default of excluding multisport legs.
  - Map each entry to a remote activity: Garmin's identifier unchanged, the UTC start, sport and elapsed duration when stated and absent otherwise, with no revision and nothing else kept.
  - List each identifier once. End the instance's pull with a named problem on a malformed answer, never quoting it.
  - Map refused, rate-limited, unavailable and other answers per the design's error table, using `REJECTED` rather than `BLOCKED` for a 403 so the report never says to report a bug.
  - Done when tests cover the window around a near-midnight start, the whole-history case, a repeated identifier across pages, each malformed form, each status, and a listing entry's name and owner fields appearing nowhere in the result.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.1, 6.2, 6.3, 6.4, 6.7, 6.8, 7.5, 8.1_

- [ ] 3.4 Apply the per-pull limit
  - Read the instance's ledger, keep every final entry plus the first 200 not final in start order, with an activity that has no start sorting last as the engine does, and report the remainder as one deferred listing entry giving the count and both resume rules. A ledger read failure ends the pull with a named error. Extend the module's import pin with the ledger.
  - Done when tests show exactly 200 offered from a larger history, final entries not counted, an activity with no start not raising and sorting last, the deferral text carrying the count, and no deferral at or under the limit.
  - _Requirements: 4.2, 4.3, 4.6_

- [ ] 3.5 Download and read the archive
  - Use the design's "Service routes" table, and extend the module's import pin with the delivery module for the FIT check. Download with the zip `Accept` types and classify members from their first bytes, never by name. Hand over exactly one FIT member's bytes unchanged, whatever else the archive holds.
  - Decline several FIT members with the count, no FIT member with GPX or TCX named when present, an empty archive as holding no FIT file, and a 404 as holding no file.
  - An unreadable archive or an over-size FIT member is a per-activity failure. A server error past the transport's retries, or a transport failure, is a per-activity failure, and the fifth in a row ends the activity pull. A success resets the count. Other statuses are per-activity failures naming the status. 401, 403 and 429 end the instance.
  - Done when tests cover every row of the design's archive table, a member named like a path traversal writes nothing, a CRC failure, a bomb-sized member stopped by the read bound, and the consecutive count stopping and resetting.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 6.8_

- [ ] 4. The connector: wellness

- [ ] 4.1 List wellness
  - Start from the given date, else the oldest activity's date, else one year before the pull, and cover everything from there through the day after the pull's UTC date in one listing.
  - Using the design's "Service routes" table, request daily, sleep, HRV and weight records in windows of 365, 31, 28 and 365 days. A 204 means no records.
  - Merge each date's records verbatim into one day, listing no day with no record, with a revision hashed from the merged record's canonical form.
  - A malformed response or an invalid date ends the wellness pull with a named problem, never quoting it.
  - Done when tests show each window bound, the three start cases, a multi-year range covered by one listing, the 204 case, a date merged across sections, a changed section changing the revision, and a repeated listing keeping the same revision.
  - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.9_

- [ ] 4.2 Package wellness days
  - Produce the delivery envelope with days sorted and none repeated, each stamped with its fetch time from the injected clock, in one canonical serialization, declaring the format `garmin-personal` and the origin `garmin`. Make no request.
  - Done when a test shows the packaged bytes are claimed by the reader from 2.1 and yield the expected values, and that the framework's package check accepts them.
  - _Requirements: 9.8_
  - _Depends: 2.1, 2.2_

- [ ] 4.3 Map wellness failures
  - Map refused, rate-limited, server-error and other answers per the design's error table, with the 403 wording naming `wellness = false`.
  - Because a wellness listing is all-or-nothing, any failure delivers no day from that pull and leaves the wellness mark where it was.
  - Done when tests cover each status, show nothing delivered and the mark unmoved after a failure part-way through a listing, and show deliveries from an earlier pull kept.
  - _Requirements: 11.3, 11.4, 11.5, 11.6_

- [ ] 5. Integration

- [ ] 5.1 Run activities through the real pull engine
  - Script a Garmin behind the real pull engine, ledger, inbox and drain.
  - Done when tests show: `pull --sync` produces a workout page with the FIT bytes unchanged in the archive and the Garmin attribution present; a second pull fetches nothing; a byte-identical file is recorded as already held; a first pull over the limit exits with success, and later plain pulls reach the end of the history; a `--since` backfill behind a watermark continues only with the same `--since`; a first pull with `--since` lists only from that date.
  - _Requirements: 4.4, 4.5, 4.6, 8.2, 8.3_
  - _Depends: 3.4, 3.5_

- [ ] 5.2 Run wellness through the real pull engine and series
  - Done when tests show: no wellness request unless enabled; a delivery reaches the series through the drain; a changed day is delivered again and replaces the earlier values while an unchanged day is not; a rate limit or refusal during activities suppresses wellness while a listing server error does not; the existing data root's series rebuilds once with no value lost; a delivery that cannot be read is named in the drain's report and leaves the series unchanged; a token server error ends activities with an error, wellness reports the same error, and exactly one token request was made; a multi-year wellness history is delivered by one plain pull, a second pull delivers only what changed, and a later `--since` older than the recorded coverage fills the gap in one pull.
  - _Requirements: 9.1, 9.3, 10.8, 10.9, 10.11, 10.12, 11.1, 11.2_
  - _Depends: 4.3, 5.1_

- [ ] 5.3 Sweep for secrets and stray data
  - Run a scripted pull with a marker key and token and search every report, exception, ledger, delivery, inbox file and data-root file for them, in plain and encoded forms, and for a listing entry's name and owner fields.
  - Confirm every request went to the one Garmin host with the fitdocs User-Agent, and that no request other than the token call was anything but a GET.
  - Done when the sweep passes with no network access and fails when a marker is deliberately written to a report.
  - _Requirements: 3.7, 7.1, 7.3, 7.4, 7.5, 14.3_

- [ ] 6. Documentation and records

- [ ] 6.1 Write the connector's documentation
  - Add the Garmin section to the connectors page: creating a key, the settings table, `fitdocs connect`, the environment override and enabling wellness; expiry and renewal; the terms quoted, the non-affiliation line and no permission claimed; the first pull, the limit, resuming and `--since`, and that wellness has no such limit; what the first `sync` does to an existing wiki and its two controls; what the connector does not do; and the `sources` hint for intervals users.
  - Add the Garmin hosts this section links to into the neutral scan's table under the exact key `docs/connectors.md#Garmin`. Delete any documentation-binding test this turns red.
  - Done when the section states every point in Requirement 12.1 to 12.8, and the neutral scan passes.
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 14.4_

- [ ] 6.2 Correct what the connector makes false
  - Update the connectors page's preamble and connector count, "What leaves your machine" and the terms-first policy; the wellness guide's format list, source order and accepted source ids; the configuration guide; the README's connector list; and add the changelog entry with the settings-schema note and the action.
  - The neutral scan covers those sections too, so name Garmin's address there without a scheme, or link to the Garmin section.
  - Do not edit the website guide: a push to `main` deploys it.
  - Done when a search of the docs finds no remaining statement that fitdocs does not read Garmin directly or ships fewer connectors, and the changelog entry names the contract and the action.
  - _Requirements: 12.9, 14.4_

- [ ] 6.3 Land the records
  - Record the amendments to `connectors` and `wellness-store`, taking the next free numbers at landing, and correct `tech.md`'s `fitdocs pull` sentence.
  - Mark Phase 15's existing-spec updates and the spec's entry on the roadmap.
  - Queue the website changes for the release cut, naming all three pages (`website/content/guides/connectors.md`, `website/content/guides/wellness.md`, `website/content/reference/configuration.md`) and editing none of them now, and queue a follow-up for `fitdocs pull` showing no progress during a long wait. Close the README connector-count item.
  - Done when each record exists, and a search of the steering files finds no statement this contradicts.
  - _Requirements: 14.7_

- [ ] 7. Validation

- [ ] 7.1 Validate the whole feature
  - Run the full project validation, the forbidden-strings gate armed, and the branch's CI.
  - Confirm no version constant, CLI count or `__all__` count moved, no runtime dependency was added, and no file carries anything from the sources Req 14.1 forbids.
  - Done when validation is green with evidence recorded, and the branch is ready to merge.
  - _Requirements: 14.1, 14.2, 14.5, 14.6_

- [ ] 7.2 The live check (maintainer)
  - Maintainer's own task: run connect, one pull up to the limit, the drain and a wellness pull against the maintainer's own account, into a scratch data root and never the real wiki.
  - Record in `research.md`, as shapes and vocabulary only, never an activity identifier, account identifier, date, name, location, file or key: any rate limit and what cleared it, how long it took, what a deleted or wrong key reports, whether any activity fell outside the shapes the design assumes, and TBC-1 to TBC-3.
  - If a finding contradicts a TBC, amend the design and every affected task before the spec is marked complete. No agent runs this unless the maintainer explicitly asks a session to, and no subagent is given the key.
  - Done when the findings are recorded and any contradiction is resolved. No other task waits for this except the completion claim.
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_
  - _Blocked: the maintainer's own task, Req 13.5_
