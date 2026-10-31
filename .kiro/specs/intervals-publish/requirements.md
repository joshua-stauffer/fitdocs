# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who pulls workouts from intervals.icu
into a fitdocs wiki, and who wants each workout's post (its title and the
description fitdocs composes) to appear on the matching intervals.icu
activity, with a link back from the workout page. intervals.icu already holds
most of the athlete's activities: Garmin rides arrive through Garmin's partner
API, and phone-app copies arrive as uploads from an authorized app.

**Current situation.** `publish-core` gives fitdocs a target-neutral
publishing core: per-page opt-in, composition, a dry-run-default `fitdocs
publish`, a closed outcome vocabulary, a publish ledger and a `published`
region on the page. It ships no target, so no post reaches any service. The
intervals.icu connector declares only the pull-activities and pull-wellness
capabilities and makes read requests only. The connector transport knows
only `GET` and `POST`, and retries a data `POST` on rate limits, server errors
and network failures. The connector's ledger maps each pulled activity's
identifier to the content digest of the file it delivered, and the
intervals-connector spec states that a later push uses that record to trace a
page's file back to its remote activity. The connector's pull and key check
quote up to 300 characters of the service's own text in their messages.
`activity-identity` owns the one cross-source match rule.

**What should change.** An intervals.icu connector instance becomes a
publish target, using the personal API key the athlete already configured.
`fitdocs publish --yes` sets the name and description of the intervals.icu
activity that records the same session as each opted-in page whose post is new
or changed. The activity is found by evidence: the activity the page's post
last landed on, then the pull record, then a listing around the page's start
time matched with activity-identity's strict rule, one-to-one. Ambiguity is a
code, never a pick. When no activity exists and the instance allows uploads,
the page's own base `.fit` file is uploaded exactly once. Every outcome is a
publish-core code; nothing intervals.icu returns is printed, logged or
written, except the direct link to the activity, which the page's `published`
region carries.

Source: `.kiro/specs/intervals-publish/brief.md`; Phase 14 of
`.kiro/steering/roadmap.md` (wave 2, parallel with `strava-publish`).
Dependencies: `publish-core`. Downstream: `relay-intervals`. Extends
`connectors`, `intervals-connector` and, as the first publish target to land
or after it, `distribution`. Reuses `activity-identity`'s strict rule
unchanged.

## Introduction

This feature is the first concrete publish target. It plugs the existing
intervals.icu connector into publish-core's target contract: it answers each
publish request publish-core hands it by finding the page's activity on
intervals.icu, setting that activity's name and description, or uploading the
page's own file when nothing exists and uploads are enabled, and it answers
with exactly one publish code and, when the post landed, the activity's direct
link.

Terms used below:
- An **instance** is a `[connectors.<name>]` table naming the intervals.icu
  connector. Every instance is a publish target.
- The **page's activity** is the intervals.icu activity that records the same
  session as the workout page.
- The **pull record** is the instance's own connector ledger, which records,
  for each activity a pull fetched, the content digest of the file it
  delivered.
- The **recorded link** is the link publish-core recorded for the page and
  this target from an earlier landed post, handed to the target with each
  request.
- The **publication id** is publish-core's random identifier for one page on
  one target, the same on every request for that pair.
- The **direct link** is `https://intervals.icu/activities/<id>`, built by
  fitdocs from the activity's identifier.
- The **strict rule** is activity-identity's strict tier (its Amendment 1):
  start times within 1 second, distances within the larger of 5 metres and 20
  percent of the longer distance, and elapsed times within 10 seconds compared
  only when either distance is missing.
- A **Strava-imported activity** is one intervals.icu lists with the source
  `STRAVA`. Its API documents that such activities cannot be updated.
- An **update** sets an existing activity's name and description. An
  **upload** sends a file that creates an activity.
- The publish codes (posted, uploaded, not found, ambiguous, not updatable,
  missing activity file, missing activity facts, rejected credentials, missing
  permission, rate limited, unavailable, refused as invalid, unconfirmed, and
  local record unreadable) are publish-core's, with publish-core's fixed
  explanations; this feature appends none.

## Boundary Context
- **In scope**: the intervals.icu connector as a publish target (its
  capabilities, its link label and its publish operation); the per-instance
  upload switch; finding the page's activity (the recorded link, the pull
  record, a listing matched by the strict rule, Strava-imported activities);
  the update of the name and description; the single upload and how its result
  is confirmed; the mapping of every intervals.icu answer into publish codes;
  the update request method the connector transport lacks today; this
  target's share of the network statements; the connectors documentation, the changelog, the
  amendment records and a site-copy queue item; an optional live check on the
  maintainer's own account.
- **Out of scope**: composition, the opt-in, the dry run, the publish ledger,
  the `published` region, the `fitdocs publish` command and its report
  (`publish-core`); the relay route to intervals.icu (`relay-intervals`);
  anything about Strava other than recognizing an activity intervals.icu
  imported from it; planned workouts, calendar events, thresholds, workout
  libraries and syncing a training block back to intervals.icu (the roadmap
  follow-on "Planned-workout push to intervals.icu"; push-planned-workout
  stays reserved and undriven); writing any activity field other than its name
  and description; deleting activities; any change to how the instance pulls
  activities or wellness, to its key check, or to its pull record.
- **Adjacent expectations**:
  - publish-core hands the connector one request per page and target whose
    decision is would-post or would-update, records the one code it answers,
    keeps a link only beside a landed code, and refuses offline every page
    that lacks its sport or its start time with the recorded offset.
  - activity-identity's strict rule is used as that spec defines it; this
    feature restates and changes none of it.
  - `relay-intervals` reuses this feature's way of finding the activity and
    its answer mapping on the relay side.
  - A later planned-workout push to intervals.icu reuses the transport's
    update method, the single-attempt request mode, the key's-own-athlete addressing and the
    answer mapping by request kind, and adds its own way of finding what it
    writes.

## Requirements

### Requirement 1: intervals.icu as a Publish Target
**Objective:** As an athlete who already pulls from intervals.icu, I want the same instance to be a publish target, so that posting needs no second connection.

#### Acceptance Criteria
1. The intervals.icu connector shall declare the annotate-remote-activity, resolve-remote-activity and push-activity capabilities beside pull-activities and pull-wellness, and no other capability.
2. The intervals.icu connector shall declare `intervals.icu` as its fixed link label.
3. When `fitdocs publish --targets` runs with an instance configured, the fitdocs CLI shall list that instance as a publish target with its three publish capabilities and its credential state, and shall make no request.
4. The intervals.icu connector shall publish with the instance's existing personal API key, read from the credential store or from the instance's override variable, and shall need no new credential, permission or `fitdocs connect` step.
5. The intervals.icu connector shall keep every pull request and its one key-check request exactly as the intervals-connector and wellness-pull specs state them.

### Requirement 2: Enabling Uploads per Instance
**Objective:** As an athlete, I want to decide per instance whether fitdocs may create activities on intervals.icu, so that by default publishing only edits activities that already exist.

#### Acceptance Criteria
1. The intervals.icu connector shall accept an optional `publish_upload` key in an instance's table, and shall treat an absent key as uploads off.
2. Where an instance sets `publish_upload = true`, the intervals.icu connector shall upload a page's activity file only as Requirement 6 states, and otherwise shall never send a request that creates an activity.
3. If `publish_upload` is present and is not a boolean, the fitdocs CLI shall stop with a configuration error naming the settings file, the instance, the key and the offending value, before any request and before any write.

### Requirement 3: Finding the Page's Activity
**Objective:** As an athlete, I want each post to land on the intervals.icu activity that records the same workout, found by evidence and never by guess, so that a post never lands on the wrong activity.

#### Acceptance Criteria
1. When a publish request carries a recorded link to an intervals.icu activity, the intervals.icu connector shall update that activity first, so that a later post of the same page goes where the earlier one landed.
2. When a request carries no such link, or intervals.icu answers that the linked activity does not exist, the intervals.icu connector shall look in the instance's pull record for an activity whose pulled original file is one of the page's archived files, taking the page's base file first and the page's other files only when the base file names no activity.
3. If the pull record maps the page's base file, or failing it the page's other files, to more than one activity, the intervals.icu connector shall answer the ambiguous code and change nothing.
4. If the instance's pull record is absent, the intervals.icu connector shall continue as criterion 5 states; if it cannot be read, the intervals.icu connector shall still update an activity found through the recorded link or the listing, and shall never upload, as Requirement 6 criterion 8 states; in either case it shall never create, repair or rewrite the pull record.
5. When neither the recorded link nor the pull record identifies an existing activity, the intervals.icu connector shall list the key's athlete's activities in one request over a range of local dates that contains the page's start time in every time zone, so that a page dated at its device's recorded offset is found however intervals.icu dates the activity locally.
6. The intervals.icu connector shall take as the page's activity the one listed activity that carries the page's publication id as its external identifier, or, when none does, the one listed activity, not imported from Strava, for which the strict rule holds between it and the page, comparing start times as instants.
7. The intervals.icu connector shall apply the strict rule without comparing sports, because intervals.icu names activity types in a vocabulary of its own, and shall never accept a match by device or by a whole-hour start shift.
8. If more than one listed activity carries the publication id, or none does and more than one satisfies the strict rule, the intervals.icu connector shall answer the ambiguous code and change nothing, and shall never choose among them by order, recency or any other rule.
9. If neither the recorded link nor the pull record identifies an existing activity and the page records neither its distance nor its elapsed time, the intervals.icu connector shall answer the missing-activity-facts code, and shall list nothing and upload nothing.
10. The intervals.icu connector shall try each activity at most once per request, and shall treat an activity intervals.icu answered as not existing as absent for the rest of that request.

### Requirement 4: Activities Imported from Strava
**Objective:** As an athlete whose intervals.icu account imports from Strava, I want a Strava-imported activity reported rather than skipped or duplicated, so that I know why the post did not land.

#### Acceptance Criteria
1. If no listed activity is the page's activity and a listed Strava-imported activity starts within 1 second of the page's start, compared as local wall-clock times when intervals.icu states only a local start, the intervals.icu connector shall answer the not-updatable code, and shall neither update nor upload.
2. The intervals.icu connector shall never send an update to a Strava-imported activity.

### Requirement 5: Setting the Title and Description
**Objective:** As an athlete, I want the post's title and description to become the activity's name and description and nothing else, so that publishing never disturbs the rest of the activity.

#### Acceptance Criteria
1. When the page's activity is identified, the intervals.icu connector shall send one update setting the activity's name to the post's title and its description to the post's description, and shall change no other field of the activity.
2. When the post's description is empty, the intervals.icu connector shall set the activity's description to empty.
3. When intervals.icu confirms the update of an activity that existed before the request, the intervals.icu connector shall answer the posted code with the activity's direct link.
4. If intervals.icu answers the update of an activity found in the listing that the activity does not exist, the intervals.icu connector shall treat the page's activity as absent and continue as Requirement 6 states.
5. The intervals.icu connector shall let the transport repeat an update after a rate limit, a server error or a network failure, within the transport's bounded retries, because sending the same name and description again changes nothing more.
6. The intervals.icu connector shall send the title and description only in an update's body, never in a request address.

### Requirement 6: Uploading When No Activity Exists
**Objective:** As an athlete who records workouts that never reach intervals.icu, I want fitdocs to upload the page's own file once when I allow it, so that the post lands without ever creating a duplicate.

#### Acceptance Criteria
1. While an instance's uploads are off, when the page's activity is not found and the instance's pull record is readable or absent, the intervals.icu connector shall answer the not-found code and send no request that creates an activity.
2. While an instance's uploads are on, when the page's activity is not found, the intervals.icu connector shall upload the page's base `.fit` file from the archive, unmodified, marked with the page's publication id as its external identifier.
3. If uploads are on and the page's base file is not in the archive, cannot be read, or does not hash to the digest it is archived under, the intervals.icu connector shall answer the missing-activity-file code and upload nothing.
4. The intervals.icu connector shall send each upload exactly once, and shall never repeat it, whatever intervals.icu answers and whatever network failure occurs.
5. When intervals.icu answers that the upload created an activity and names exactly one, the intervals.icu connector shall set that activity's name and description with one update, and on intervals.icu's confirmation of that update shall answer the uploaded code with the activity's direct link.
6. When intervals.icu answers that it already holds the uploaded file as an activity and names exactly one, the intervals.icu connector shall set that activity's name and description with one update, and on confirmation shall answer the posted code with the activity's direct link.
7. If an upload is answered with a server error, a network failure, or a success that does not name exactly one activity in the documented form or names one already answered as not existing in the same request; or intervals.icu answers the update of an activity the upload created with anything but a confirmation; or answers that an activity the upload named as already held does not exist, the intervals.icu connector shall answer the unconfirmed code, so that the next run looks for the activity, by its publication id among others, before it uploads again.
8. If the page's activity is not found through the recorded link or the listing and the instance's pull record cannot be read, the intervals.icu connector shall answer the local-record-unreadable code whatever the upload setting, and shall upload nothing, because the unreadable record may name the activity.

### Requirement 7: Mapping intervals.icu's Answers into Codes
**Objective:** As an athlete, I want every outcome stated as one fitdocs code that means the same on every target, so that I know what happened and what to do next.

#### Acceptance Criteria
1. The intervals.icu connector shall answer every publish request with exactly one code that a publish target may return, and with a link only beside the posted or uploaded code.
2. If intervals.icu answers a request as unauthorized, the intervals.icu connector shall answer the rejected-credentials code; if as forbidden, the missing-permission code.
3. If intervals.icu answers a request as rate-limited, after the transport's bounded retries for a listing or an update and at once for an upload, the intervals.icu connector shall answer the rate-limited code.
4. If a listing or an update still meets a server error or a network failure after the transport's bounded retries, or a listing's answer is not in intervals.icu's documented form, the intervals.icu connector shall answer the unavailable code.
5. If intervals.icu refuses a request with any other client-error status, including an upload of a file it cannot accept, the intervals.icu connector shall answer the refused-as-invalid code; an update's answer that the activity does not exist is not a refusal, and follows Requirement 3 criterion 10 and Requirement 5 criterion 4.
6. If an update or an upload is answered with a status that is neither its documented success nor a client or server error, the intervals.icu connector shall answer the unconfirmed code; if a listing is, the unavailable code.
7. The intervals.icu connector shall decide each code from the kind of request (a read, a write that is safe to repeat, or a write that creates something) and intervals.icu's answer alone, never from the kind of object written, so that a later write of another kind of intervals.icu object maps its answers the same way.
8. When intervals.icu does not confirm the update of an activity an upload created, the intervals.icu connector shall answer as Requirement 6 criterion 7 states in place of criteria 2 to 6, because the activity exists and only the post is unconfirmed.

### Requirement 8: Nothing from intervals.icu Reaches Output
**Objective:** As an athlete, I want nothing intervals.icu returns printed, logged or written except the link to my activity, so that publishing keeps fitdocs's rule that platforms speak only through fitdocs codes.

#### Acceptance Criteria
1. The intervals.icu connector shall never place any part of an intervals.icu response body, header, status text or message into a code, a link, an exception, a ledger, a page or any printed or written output.
2. The intervals.icu connector shall build the direct link as `https://intervals.icu/activities/` followed by the activity's identifier, and shall build it only from an identifier of letters and digits alone, at most 64 of them.
3. The intervals.icu connector shall send an update only to an activity identifier of that form, and shall treat an identifier of any other form as naming no activity when it comes from the recorded link, the pull record or an upload's answer, and as an answer not in its documented form when it comes from a listing.

### Requirement 9: Requests, Credentials and the Network
**Objective:** As a privacy-conscious athlete, I want to know exactly what publishing sends to intervals.icu and when, so that nothing leaves my machine I did not ask for.

#### Acceptance Criteria
1. The intervals.icu connector shall make publish requests only during `fitdocs publish --yes`, and only for the page and target pairs publish-core hands it; `fitdocs publish` without `--yes` and `fitdocs publish --targets` shall make no request to intervals.icu.
2. The intervals.icu connector shall send every publish request through the fitdocs transport, carrying the one fitdocs User-Agent and the key only in the authorization header, which a redirect target never receives, and never placing the key or any encoded form of it in an address.
3. The intervals.icu connector shall address every publish request to intervals.icu and to the key's own athlete, and shall take no athlete identifier or service address from the settings file.
4. The intervals.icu connector shall send, for one publish request, at most one listing, at most one upload, and at most one update per activity it tries.
5. The intervals.icu connector shall put into request addresses only activity identifiers, the listing's date bounds and field names, and the publication id; it shall send the title and description only in an update's body and the base file only in an upload's body.
6. The intervals.icu connector's tests shall run with no network access, against synthesized intervals.icu answers and synthesized FIT bytes that contain no personal data.

### Requirement 10: The Network Statements
**Objective:** As a user who relies on fitdocs's statements about the network, I want every statement that lists the commands making requests to include publishing, so that none of them becomes false when publishing ships.

#### Acceptance Criteria
1. Every statement in the shipped code, the README, the documentation and the technology steering that lists the commands making network requests shall name `fitdocs publish --yes` among them, whichever publish target lands first.
2. Every such statement that lists the commands making no request shall name `fitdocs publish` without `--yes` and `fitdocs publish --targets` among them.
3. The connectors documentation's statement of what leaves the machine shall say that an intervals.icu instance's publish requests go to intervals.icu.
4. An automated test shall fail when any of these statements stops naming `fitdocs publish --yes`.

### Requirement 11: Documentation, Records and the Site Copy
**Objective:** As an athlete or a maintainer, I want publishing to intervals.icu documented where I already look and recorded against every spec it changes, so that it is usable and its contract changes are traceable.

#### Acceptance Criteria
1. The intervals.icu section of the connectors documentation shall describe publishing: opting a page in to the instance, `publish_upload` and its default, the order in which the activity is found, Strava-imported activities, what each publish request sends, the direct link, and what each code the connector answers means there.
2. The intervals.icu section shall no longer state that the connector never writes to the account, and shall state that it writes only a page's name and description and, while uploads are on, the page's base file.
3. The connectors documentation shall state the connector's mapping from intervals.icu's answers to codes as one table by request kind, and an automated test shall hold that table equal to the connector's own mapping.
4. The changelog's unreleased section shall describe publishing to intervals.icu, `publish_upload` and the changed network statements.
5. The specs this feature extends (`connectors`, `intervals-connector`, and `distribution` unless an earlier publish target already recorded its network change) shall each record an amendment, numbered as the next free amendment at landing, preserving every existing criterion and approval.
6. The feature shall edit no page of the documentation site, and shall record each site line it makes stale, by file and line, in a follow-up queue item for the next release's site update.
7. The project structure steering shall state the intervals.icu connector's new dependency on activity-identity's match rule, and that it names publish codes only through the connector protocol.

### Requirement 12: The Optional Live Check
**Objective:** As the maintainer, I want the target's assumptions about intervals.icu confirmed against my own account when I choose to, so that nothing is built on an unconfirmed guess about a service fitdocs cannot test offline.

#### Acceptance Criteria
1. Where the maintainer explicitly asks for it at implementation time, the Maintainer shall confirm against their own intervals.icu account, with their own key, the update's effect on one activity, the listing fields the connector reads, the upload's answers for a new file and for a duplicate, the round trip of the external identifier, and the direct link's form.
2. The Specification Process shall state, before the live check runs, that it writes to the maintainer's real account, and shall run it only with the maintainer's explicit go.
3. The Maintainer shall record the findings in the spec's research record as shapes, statuses and vocabulary only, never an activity identifier, athlete identifier, date, name, file or key.
4. If a finding contradicts an assumption the design marks as to be confirmed, the Specification Process shall amend the design and every affected task.
5. The Specification Process shall never let an automated agent run the live check, record it or mark it done unless the maintainer explicitly asks a session to run it with the maintainer's key, and no other task shall wait for it.
