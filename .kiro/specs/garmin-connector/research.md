# Research & Design Decisions: garmin-connector

## Summary
- **Feature**: `garmin-connector`
- **Discovery Scope**: Extension (a built-in connector on the existing framework, plus one wellness format)
- **Key Findings**:
  - Everything the connector needs is public: Garmin's OpenAPI spec, its Apache-2.0 client, the FAQ and the Supplemental Terms. Two live checks measured the rest.
  - The framework fits with one opt-in addition: the transport retries 429s itself, at 2 s and 4 s, which works against a limit over a fixed period.
  - Reusing the `garmin-export` source would let API revisions silently beat the export's unrevised values, so the format gets a source of its own.

## Research Log

### What Garmin publishes
- **Sources**: the FAQ, the Swagger page, `garmin/connect-personal-api-python`, the Supplemental Terms strings. Copies are kept outside this repository.
- **Findings**:
  - The key cannot call data endpoints. `POST /personalapitoken-service/personal-api/personal-api-key/token` with `Authorization: ApiKey <key>` returns a token; data calls use `Authorization: Bearer <token>`. Life is 24 hours or until the key expires, with no refresh tokens.
  - The OpenAPI spec is embedded in the Swagger page's public JavaScript bundle: OpenAPI 3.0.1, 26 paths, no license or confidentiality text. Servers are `personal.connectapi.garmin.com` and `personal.connectapi.garmin.cn`.
  - Published range limits: sleep summaries 31 days, daily summaries 1 year. The listing defaults to `limit=99`, with `excludeChildren=true`, `sortOrder`, and date filters on local start time.
- **Implications**: no source outside the public material is needed. The provenance rule costs nothing.

### Measured (2026-11-05, maintainer's key, read-only)
Two checks: about 40 requests, then 10, all at 2.5 s spacing. No 401, 403 or 429 on the real key, and no limit headers.

| Question | Finding |
|---|---|
| Token | Bare token as `text/plain`, 24.0 h life |
| A bad key | 401, empty body, no `Content-Type` |
| User-Agent | `fitdocs/<version>` accepted |
| Listing | 1,070 activities back to 2014. Pages of 200 work; `limit=1000` answers 500 with an empty body. `sortOrder=asc` with a date filter returns oldest first |
| Listing fields | `activityId`, `startTimeGMT` (`YYYY-MM-DD HH:MM:SS`, no zone), `elapsedDuration`, `activityType.typeKey`. `isParent` and `parent` false on all rows; `manualActivity` false on all rows |
| Downloads | One-member ZIP, `application/x-zip-compressed`. 5 FIT, 1 GPX |
| File fidelity | 4 of 4 comparable FIT files byte-identical to the export's `UploadedFiles` originals, undocumented messages included |
| Daily summaries | `{"data":[...]}`. 7, 32 and 366 days work, and 2019 answers. Days with no data are missing. Two fetches of 90 days were byte-identical |
| Daily fields | `heartRate.{restingValue,minValue,maxValue}`; `movement.steps.value`; `stress.avgLevel`; `bodyBattery.{maxValue,minValue}`; `respiration.avgValue`; `pulseOx.{avgValue,minValue}` (empty on this account) |
| Sleep | A list. 32 days works, 366 answers 400 with `{}`. `deep`, `light`, `rem` and `awakeSleepSeconds`, `averageRespirationValue` |
| Weight | `dailyWeightSummaries[].{summaryDate,latestWeight.weight}`; the value is grams, `timestampGMT` is epoch ms |
| HRV | 204 with no body, every window tried. The public schema is `{hrvSummaries:[{calendarDate,weeklyAvg,lastNightAvg,lastNight5MinHigh,baseline,status,...}]}` |

### What HRV measures
- **Sources**: [Garmin FIT SDK, `HrvStatusSummaryMesg`](https://github.com/garmin/fit-csharp-sdk/blob/main/Dynastream/Fit/Profile/Mesgs/HrvStatusSummaryMesg.cs), whose comments read "Last night RMSSD average over sleep", "7 day RMSSD average over sleep" and "5 minute high RMSSD value over sleep".
- **Findings**: the FIT fields `last_night_average`, `weekly_average`, `last_night_5_min_high` and the baselines line up with the API's `lastNightAvg`, `weeklyAvg`, `lastNight5MinHigh` and `baseline`. A web search alone could not settle this; secondary sources disagree.
- **Implications**: read `lastNightAvg` as `HRV_RMSSD_MS`. That the API field is the same number is an inference from the names, and no real record has been seen, so a record in any other form leaves the value absent.

### Pacing evidence
- **Sources**: the two checks; Garmin's clause 2 ("may throttle, delay, reject, suspend, or otherwise restrict API requests without notice"); third-party READMEs read only through a research summary (bursts drew 429 with no `Retry-After`; twelve requests 2 s apart succeeded; no limits seen at 4 requests a second).
- **Findings**: Garmin publishes no number. The maintainer's expectation is that bursts are supported, and that sustained traffic above about one request a second meets a limit over a fixed period.
- **Implications**: 1 s spacing with long waits on 429. The transport's 2 s and 4 s retries would land inside the same period, so GETs here opt out of them.

### Framework seams (code reading, file:line at discovery)
- `connectors/pull.py`: one `HttpClient` and one `ConnectorSession` per instance pull, shared by activities and wellness (`:712-724`). An `AuthFailure` from activities suppresses wellness; a `ConnectorError` does not (`:733-735`, `:839-844`, `:1006-1009`). Other exceptions from a fetch are per-activity failures (`:845-854`). The ledger saves only at instance end (`:1021-1031`).
- `connectors/pull.py` `_compute_watermark`: the newest start of the contiguous run of entirely final groups in the entries the connector returned (`:365-413`). A capped listing therefore self-resumes, because the remainder is always newer than the watermark. A backfill with `--since` older than an existing watermark does not, because the watermark never moves back (`.kiro/queue/2026-10-02-intervals-rate-limit-resume-claim-since-backfill.md`).
- `connectors/http.py`: `_send_data` retries 429, 500, 502, 503 and 504 with 2 s and 4 s (`:309-326`). `auth_failure_from` already parses `Retry-After` against the response's own `Date`.
- `connectors/errors.py`: `BLOCKED`'s next step tells the athlete to report a bug, so a 403 here uses `REJECTED`.
- `connectors/requirements.md` 4.6 forbids a login-style connector persisting the typed value. That rules out `LOGIN` for a key that must be kept to mint tokens.
- `wellness/merge.py` (`:46-58`): groups by source, day and metric, newest revision wins, and a metric missing from the newest retracts. So every delivered day must be complete.
- `wellness/registry.py`: `default_source_order` sorts by kind rank, then id.
- `wellness/intake.py`: only the intervals format has a newer-version message.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|---|---|---|---|---|
| Connector in one module, shaped like `intervals` | `connectors/garmin.py` | Follows the existing pattern; no framework change beyond one transport flag | A long module | **Selected** |
| Depend on Garmin's client | `garmin-connect-personal-api-python` | Less code | Python 3.12 and `requests`, against a 3.11 floor and the network allow-list | Rejected |
| Separate package through the plugin slot | `fitdocs-garmin` | Isolates a Garmin objection | Needs plugin-api first, plus a second release pipeline | Rejected at discovery by the maintainer |

## Design Decisions

### Decision: `API_KEY` auth, one token per pull
- **Context**: a key must be kept to mint tokens, and tokens have no refresh path.
- **Alternatives Considered**:
  1. `LOGIN` with `TokenSet`: persists the key as a token value, which breaks connectors Req 4.6, renews only at pull start, and no shipped connector uses it.
  2. `API_KEY` with a token minted on first use.
- **Selected Approach**: `API_KEY`. `verify` mints and discards; a pull mints once, single-attempt, and holds the token in memory for that session.
- **Trade-offs**: one extra request per pull, and no token on disk.

### Decision: per-pull state on the connector, keyed by the session's client
- **Context**: the token, the pacing flag, the wait budget and the failure count must survive across calls in one pull. The connector is a process singleton, and "a connector keeps no state between sessions".
- **Selected Approach**: `WeakKeyDictionary[HttpClient, _PullState]` on the connector. One client per instance pull, so state lives exactly as long as the pull.
- **Trade-offs**: a new pattern in the package, but it stays inside one module and needs no framework change.

### Decision: opt-in `retry_rate_limits` on the transport
- **Context**: the connector's own waits are pointless if the transport first spends three attempts inside the same limit period. `single_attempt` would also lose the 5xx and network retries.
- **Selected Approach**: `HttpRequest.retry_rate_limits: bool = True` and the same keyword on `HttpClient.get`. When false, `_send_data` returns a 429 at once and still retries 5xx and transport errors.
- **Trade-offs**: a small additive change to a shared module, with every existing caller unchanged.

### Decision: `garmin-personal`, a source of its own
- **Context**: `garmin-export` values carry no revision on daily and sleep records, so any API revision would beat them silently.
- **Selected Approach**: a new DEVICE source sorting after `garmin-export`, so the export's existing canonical values do not move, and values attributed to origin `garmin`.
- **Trade-offs**: every wiki with wellness rebuilds its series once, and the source list grows by one (Apple is the precedent).

### Decision: every delivered day is complete
- **Context**: a merge retracts any metric the newest revision lacks, so a transient gap could erase values.
- **Selected Approach**: one wellness listing is all-or-nothing, so no partial window is ever delivered. `covers` is therefore the format's full metric set on every day, and a later delivery replaces the earlier one outright.
- **Trade-offs**: a failure late in a 3-year slice wastes that pull's wellness requests. The next pull repeats them.

### Decision: a lenient parser for this format
- **Context**: the export parser refuses a whole file on a non-numeric value. Here that would leave a delivery stuck over a surprise in one field, and HRV's real form is unseen.
- **Selected Approach**: a value that is not a number, or a section that is not an object, leaves that metric absent. Only the envelope itself refuses the file.
- **Trade-offs**: a shape change at Garmin reads as missing data, not an error. The live check and the archived raw records cover that.

### Decision: hold the website guide for the release
- **Context**: a push to `main` deploys the website, and the connector reaches users only through a release. The site's own guide says fitdocs does not read Garmin Connect directly.
- **Selected Approach**: `docs/` changes land with the code. The website guide changes at the release cut, queued (precedent: PR #1 for 0.2).
- **Trade-offs**: the website stays one step behind until release, which is correct.

## Synthesis Outcomes
- **Generalization**: pacing, the rate-limit waits and the failure counter are one concern, so every Garmin GET goes through one `_get` helper. The helper stays private; no other connector has asked for this, and intervals is deliberately left unchanged.
- **Build vs adopt**: adopted `zipfile`, `auth_failure_from`, `is_fit`, `load_ledger`, the transport, and the existing `_put` and `_sleep` in `formats/garmin.py`. Built only the connector and the new format's reader. `_document_format` and the content-revision helper are small private functions in `intervals.py`, copied rather than promoted, so a shipped connector is not touched for this.
- **Simplification**: no settings, no shared pacing machinery, no JWT decoding, no token persistence, no new wellness module (the reader sits in `formats/garmin.py`), no framework report channel for waits, and no separate `covers` per section.

## Risks & Mitigations
- **"Operate" stays unruled**: the docs cite Garmin's wording and claim no permission. Accepted by the maintainer on 2026-11-05.
- **Sustained pacing unknown**: the backoff handles a limit over a fixed period, a longer one ends the pull cleanly, and the live check measures it.
- **A real wiki re-bases on first sync**: documented, with `pull` without `--sync` and `[identity] precedence` as the controls.
- **A whole-record revision may be volatile**: daily summaries were stable, sleep and weight are unmeasured. The worst case is re-delivering the look-back window on each pull. TBC-1 in the design.
- **A silent wait**: `fitdocs pull` shows no progress, so a rate-limit wait of several minutes looks like a hang. Queued rather than added here.

## References
- [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/)
- [Personal API Swagger page](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)
- [Garmin's Personal API client](https://github.com/garmin/connect-personal-api-python)
- [Garmin FIT SDK, HRV status message](https://github.com/garmin/fit-csharp-sdk/blob/main/Dynastream/Fit/Profile/Mesgs/HrvStatusSummaryMesg.cs)
