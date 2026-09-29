# Requirements Document

## Project Description (Input)
The athlete records rides on a Garmin Edge. Garmin's own copy of a ride reaches
fitdocs today only through a hand export from Garmin Connect: HealthFit's Apple
Health copies of Garmin rides stopped arriving on 2026-04-08, and they were
degraded anyway (HR-only in the "-Connect" style; no altitude, temperature,
pedal dynamics and usually no GPS in the "Health Sync" style). A direct Garmin
Connect login is not viable (business-only developer program, broken unofficial
clients, a login that drew HTTP 429 during discovery). The athlete keeps
intervals.icu current with every workout; intervals.icu receives Garmin rides
over Garmin's official partner API and serves them through a documented API
with a personal key.

This spec (Phase 8 of the roadmap, wave 2) builds the intervals.icu **activity
pull** on the `connectors` framework: a personal-key connector that lists the
athlete's activities by date range, skips Strava-sourced stubs and anything
without a downloadable FIT original, honours a configurable source filter,
downloads the original (gzip) and hands it to the framework's FIT check and
delivery. It also lands two existing-spec updates the roadmap assigns to it:
`fit-ingest` resolves Garmin product names (today `DeviceInfo.product_name` is
`None` for every Garmin device, `src/fitdocs/ingest/summary.py:372-385`), and
`workout-docs` renders "Garmin <model>" attribution, which intervals.icu's API
terms (§1.1, effective 2025-10-23) and Garmin's API Brand Guidelines
(V 6.30.2025) require. Its first task is a live viability check the maintainer
runs against their own account.
Source: `.kiro/specs/intervals-connector/brief.md`; Phase 8 of
`.kiro/steering/roadmap.md`.

## Introduction

The athlete connects intervals.icu once with a personal API key, names it in
`fitdocs.toml`, and from then on `fitdocs pull` (by hand, from cron or from the
packaged skill's routine) fetches every Garmin ride intervals.icu holds that the
athlete does not yet have, into the same inbox a hand-dropped file lands in.
Everything after delivery is the existing drain.

Three properties shape the requirements. **Only what is really a FIT original
is fetched**: a Strava-sourced entry is an empty stub, a GPX or TCX original is
not a FIT file, and intervals.icu's regenerated FIT is not an original; each is
skipped by name rather than delivered. **The key is a secret and the service is
treated gently**: the key never appears anywhere fitdocs writes or prints, a
refused key is reported once and never retried, and a rate limit ends the
source's pull instead of hammering it. **Garmin data is attributed**: every
page rendered from a file a Garmin device recorded says "Garmin <model>" (or
"Garmin") directly beneath its title, whichever way the file arrived; to name
the model, fitdocs finally turns the numeric Garmin product code into the name
the FIT SDK's own profile gives it.

The shapes intervals.icu's listing returns are taken from its published
OpenAPI description (served at `https://intervals.icu/api/v1/docs`, version
v1.0.0, read 2026-09-29). The maintainer's live check confirms them against a
real account before the connector is used on a real data root.

## Boundary Context
- **In scope**: the intervals.icu connector (its declaration, the key check at
  connect, listing by date range, the source filter, stub and non-FIT
  skipping, the original download and its decompression, failure reporting);
  its `[connectors.<name>]` settings; the live viability check; Garmin
  product-name resolution in ingest; Garmin attribution on workout pages and
  the resolved names in the devices table; the documentation for setting the
  connector up; the amendment records on `fit-ingest` and `workout-docs`;
  this connector's entry in the exemption table of `connectors`'
  service-neutral scan.
- **Out of scope**: every other intervals.icu capability (uploads, names and
  descriptions, planned workouts, thresholds, wellness, workout libraries and
  plans), which are the roadmap's Phase 8 follow-ons and use the capability
  names `connectors` reserves; OAuth app registration; a direct Garmin Connect
  connector or a Garmin export importer; deduplicating a ride against its
  HealthFit or hand-exported copy; composing channels from several files;
  attribution on pages that aggregate many workouts (the training-history
  page, training-block pages) and inside chart images (see design.md Open
  Questions); anything written to intervals.icu.
- **Adjacent expectations**:
  - `connectors` supplies the protocol, the credential store and its
    environment overrides, the ledger, the transport (explicit User-Agent,
    timeouts, bounded data-call retries, a single authentication attempt,
    credential headers never sent to a redirect target), the FIT-header
    backstop, delivery into `<inbox>/<instance>/` and the `connect` and `pull`
    commands; this spec amends none of their behaviour.
  - `activity-identity` decides which page a delivered file belongs to and
    which file is a page's base, from the file's own content. An intervals.icu
    download is Garmin's partner-API copy of a ride; this spec relies on
    identity ranking the device's own original above it (its within-kind rank
    puts the file with more undocumented messages first) and adds no marker to
    the file. Until identity has merged, pulling into a data root that already
    holds other copies of the same rides creates duplicate pages.
  - `channel-merge` decides which extras donate channels to a page and
    publishes each contributing file's own devices; the combined-source
    attribution wording is exercised on a composed page once whichever of the
    two specs lands second passes the donating files' devices to it.
  - `activity-qa-flags` reads sample channels and load outcomes only, so the
    messages Garmin strips from a partner-API copy (undocumented messages,
    workout steps) never reach a quality flag.
  - `route-maps` is unaffected: position is a documented record field and
    survives in the partner-API copy.

## Requirements

### Requirement 1: Connecting intervals.icu with a Personal Key
**Objective:** As an athlete, I want to connect my intervals.icu account once with the personal API key from its developer settings, so that later pulls run unattended without my password ever being stored.

#### Acceptance Criteria
1. The intervals.icu connector shall declare exactly one credential field, the athlete's personal API key, marked secret, and shall declare the pull-activities capability and no other.
2. When `fitdocs connect` verifies a key for an intervals.icu instance, the intervals.icu connector shall make exactly one read request for the key's own athlete, authenticated with that key, and shall never repeat it, whatever intervals.icu answers.
3. When intervals.icu accepts the verification request, the intervals.icu connector shall report that no scopes were granted, recording the scopes as absent rather than as an empty grant.
4. If intervals.icu answers the verification request as unauthorized, the intervals.icu connector shall report a rejected key; if it answers as forbidden, a blocked client; if it answers as rate-limited, a rate limit with any wait the service states; if it answers with a server error, or with any other status that is not success, the service as unavailable, naming the status.
5. The intervals.icu connector shall address every request to the athlete who owns the key, and shall take no athlete identifier, service address or credential from the settings file.

### Requirement 2: Configuring the Connector
**Objective:** As an athlete, I want to choose which of intervals.icu's sources are pulled, so that copies I already receive another way are not fetched twice.

#### Acceptance Criteria
1. Where a connectors instance names the intervals.icu connector, the intervals.icu connector shall accept an optional source filter listing intervals.icu source names, and shall default it to only the activities intervals.icu received from Garmin Connect.
2. If the source filter is not a non-empty list, or any entry is not a source name written in intervals.icu's upper-case form (letters, digits and underscores, starting with a letter), the fitdocs CLI shall stop with a configuration error naming the settings file, the instance, the key and the offending value, before any request and before any write.
3. When the source filter names a well-formed source name that intervals.icu's published vocabulary does not list, the intervals.icu connector shall accept it, so that a source intervals.icu adds later can be pulled without a fitdocs upgrade.
4. The intervals.icu connector shall ignore instance keys it does not recognize.

### Requirement 3: Listing Activities by Date Range
**Objective:** As an athlete running pulls on a schedule, I want each pull to list exactly the intervals.icu activities that started within its window, so that new rides arrive and nothing already handled is fetched again.

#### Acceptance Criteria
1. When a pull lists an intervals.icu instance with an earliest start time, the intervals.icu connector shall list every activity of the key's athlete that starts at or after that time, through the moment of the pull, and shall list no activity whose stated start is earlier.
2. While a pull gives no earliest start time (the instance has never recorded a watermark and no `--since` date is given), the intervals.icu connector shall list the activities that started in the 30 days before the pull.
3. The intervals.icu connector shall list each intervals.icu activity at most once per pull, however the listing is split into requests.
4. The intervals.icu connector shall omit from the listing every activity whose source is not in the source filter, including an activity whose source intervals.icu does not state.
5. Where a listed activity's source is Strava, the intervals.icu connector shall list it as having no available original, with a reason stating that intervals.icu returns only a stub for Strava activities and shares no file for them.
6. Where intervals.icu states that an activity's original file is in a format other than FIT, the intervals.icu connector shall list it as having no available original, with a reason naming that format.
7. The intervals.icu connector shall carry each listed activity's start time, sport and elapsed duration when intervals.icu states them in its documented form, and shall carry each as absent otherwise, never as zero, an empty string or a default; it shall state no revision, because an intervals.icu activity's original file never changes.
8. If a listing response is not in intervals.icu's documented form — not a list of activity objects, or an entry without a text identifier — the intervals.icu connector shall end that instance's pull with an error naming what was malformed, and shall never guess at the entry.

### Requirement 4: Downloading the Original File
**Objective:** As an athlete, I want the file fitdocs fetches to be the original my device recorded, decompressed and checked, so that a page is built from real device data and never from a stub, a GPS-only track or a regenerated copy.

#### Acceptance Criteria
1. When a pull fetches an intervals.icu activity, the intervals.icu connector shall download that activity's original file, and shall never download the FIT file intervals.icu regenerates from its own data.
2. When the downloaded body is gzip-compressed, the intervals.icu connector shall decompress it; when it is not, the intervals.icu connector shall use the body as received.
3. If the downloaded body is gzip data that cannot be decompressed, or its decompressed size would exceed the transport's response-size bound, the intervals.icu connector shall report that activity's fetch as failed, so that it stays unrecorded and the next pull tries it again.
4. If the decompressed file is a GPX or TCX document, the intervals.icu connector shall decline it with a reason naming the format, so that the fitdocs CLI records it as skipped and delivers nothing.
5. If intervals.icu reports that it holds no file for the activity, the intervals.icu connector shall decline it with a reason saying so.
6. If the decompressed file is neither a FIT file nor a GPX or TCX document, the fitdocs CLI shall record the activity as skipped because the original is not a FIT file, and shall deliver nothing.
7. The intervals.icu connector shall hand over the decompressed bytes unmodified, adding no marker, so that the drain and every later identity decision see exactly the file intervals.icu stored.

### Requirement 5: Failures, Rate Limits and the Key
**Objective:** As an athlete, I want a refused key, a blocked client, a rate limit or an outage reported by name, and my key kept out of everything fitdocs writes or prints, so that I know my next step and nothing leaks or gets my access suspended.

#### Acceptance Criteria
1. If intervals.icu answers a listing or download request as unauthorized, the fitdocs CLI shall end that instance's pull, report a rejected key with the step to reconnect, and shall not repeat the request.
2. If intervals.icu answers a listing or download request as forbidden, the fitdocs CLI shall end that instance's pull and report that intervals.icu refused this client, quoting the service's message with every secret removed.
3. If a listing or download request is still rate-limited after the transport's bounded retries, the fitdocs CLI shall end that instance's pull, stating that intervals.icu is limiting requests and that the next pull resumes where this one stopped.
4. If a listing or download request still meets a server error after the transport's bounded retries, the fitdocs CLI shall end that instance's pull, stating that intervals.icu is unavailable and that the next pull resumes where this one stopped.
5. If a listing request is answered with any other status that is not success, the fitdocs CLI shall end that instance's pull naming the status; if a download request is, the fitdocs CLI shall report that activity's fetch as failed, naming the status, and continue with the instance's remaining activities.
6. The intervals.icu connector shall send every request through the fitdocs transport, so that each carries the fitdocs User-Agent and never the HTTP library's default agent.
7. The intervals.icu connector shall never place the key, or any encoded form of it, in a request address, a report, a ledger, an exception message, the inbox or any file under the data root.
8. The intervals.icu connector's tests shall run with no network access, against synthesized service responses and synthesized FIT bytes that contain no personal data.

### Requirement 6: What the Ledger Records
**Objective:** As an athlete, and as the author of a later push capability, I want each pulled activity recorded against intervals.icu's own id, so that a second pull fetches nothing new and a page's source file can be traced back to the remote activity.

#### Acceptance Criteria
1. The intervals.icu connector shall identify each listed activity by intervals.icu's own activity identifier, unchanged, so that the instance's ledger maps each fetched file's content hash to that identifier.
2. When a pull runs twice over the same range with no new activity on intervals.icu, the fitdocs CLI shall fetch nothing in the second pull.
3. When an intervals.icu original is byte-identical to a file already in the archive, the fitdocs CLI shall record it as already held and deliver no second copy.

### Requirement 7: Garmin Product Names in Ingest (fit-ingest update)
**Objective:** As an athlete, I want the model of each Garmin device named on my pages, so that I can tell which device recorded a workout and attribution can name it.

#### Acceptance Criteria
1. When a device entry in a `.fit` file records no product name text but carries a product code that the FIT SDK's profile names as a Garmin product, the fit-ingest library shall expose that profile name as the device's product name.
2. If a device's product code is not named by the FIT SDK's profile, the fit-ingest library shall leave the device's product name absent, never a placeholder and never the code rendered as text.
3. Where a device entry records a product name as text, the fit-ingest library shall keep exposing that recorded text in preference to any name resolved from a code.
4. The fit-ingest library shall resolve product names from a file's own content alone, so that the same device is named alike whether its file arrived as a device original, a Garmin Connect export, an intervals.icu download or a hand drop.
5. The fit-ingest library shall take every resolved name from the FIT SDK's profile, and shall keep no product-name table of its own.

### Requirement 8: Garmin Attribution on Workout Pages (workout-docs update)
**Objective:** As an athlete whose pages are built from Garmin device data, I want each such page to attribute Garmin and the device model beside its data, so that my wiki meets intervals.icu's API terms and Garmin's brand guidelines without implying Garmin vouches for data from other devices.

#### Acceptance Criteria
1. When the fitdocs CLI renders a workout document from a file whose recording device — the device the file itself names as its creator — is made by Garmin, it shall show a line reading "Garmin" followed by that device's product name directly beneath the document's title and above every section.
2. If that Garmin recording device's product name is absent, the fitdocs CLI shall show "Garmin" alone in the line, never a placeholder model.
3. Where a document's recording device is not made by Garmin, or the file names no recording device, the fitdocs CLI shall show no Garmin attribution.
4. Where a document combines channels from files recorded by different devices and at least one of them is a Garmin device, the fitdocs CLI shall name each contributing Garmin device and state that other devices also contributed, and shall never present Garmin as the source of the whole document.
5. The devices table shall show each device's product name as the fit-ingest library resolves it.
6. The fitdocs CLI shall decide the attribution from the files' own content alone, so that the same files yield the same attribution however they arrived.
7. The fitdocs CLI shall render the attribution as generated content outside every preserved region, refreshed on every regeneration and byte-identical for identical inputs, and shall record it in no frontmatter key.
8. The fitdocs CLI shall advance the document-format version with this change, so that a document written before it is detected as needing regeneration and regeneration adds its attribution and resolved device names.

### Requirement 9: The Live Viability Check
**Objective:** As the maintainer, I want the connector's assumptions confirmed against my own intervals.icu account before it is pointed at my real data root, so that nothing is built on a guess about a service fitdocs cannot test offline.

#### Acceptance Criteria
1. The Maintainer shall confirm, against the athlete's own intervals.icu account and with the athlete's own key, that intervals.icu receives the athlete's Garmin rides directly from Garmin rather than through Strava, that the original file of one Edge ride is a gzip-compressed FIT carrying power, pedal dynamics and the full record set, and whether its bytes equal the original in the Garmin Connect export of the same ride.
2. The Maintainer shall also record the listing fields the design relies on (their names and value forms), the original-file formats intervals.icu states, whether a download is redirected, how many undocumented messages the intervals.icu copy and the device's own original of the same ride each carry, and which recording device (manufacturer and product) one HealthFit copy of a Garmin ride and one HealthFit run copy each name.
3. The Maintainer shall record the findings in the spec's research record as shapes and vocabulary only, never an activity identifier, athlete identifier, date, name, location, file or key.
4. If a finding contradicts an assumption the design marks as to be confirmed, the Specification Process shall amend the design and every affected task before the spec is marked complete.
5. The Specification Process shall treat the live check as the maintainer's own task: no automated agent performs it, records it or marks it done, and no other implementation task waits for it except the final completion gate.

### Requirement 10: Documentation and Records
**Objective:** As an athlete setting the connector up, and as a maintainer relying on the project's records, I want the connector documented and every contract it touches restated, so that setup needs no guesswork and no statement contradicts the code.

#### Acceptance Criteria
1. The connectors documentation shall describe the intervals.icu connector: where the athlete finds the personal key, connecting it, the environment variable that overrides it for an instance named `intervals`, the source filter and its default, the 30-day first pull and backfilling with `--since`, what is skipped and why (Strava stubs, non-FIT originals, activities without a file), how rate limits and a refused key are reported, what leaves the machine, the Garmin attribution on pages, and, while cross-source identity has not shipped, that pulling into a data root holding other copies of the same rides creates duplicate pages — or, once it has shipped, that a data root's existing documents are regenerated before the first pull.
2. The connectors documentation shall cite intervals.icu's API terms §1.1 and Garmin's API Brand Guidelines (by title and version) as the reason for the attribution, and shall give no web address of any online service other than intervals.icu.
3. The changelog's unreleased section shall record the intervals.icu connector, the Garmin product names, and the attribution line together with the action a user must take (regenerating existing documents).
4. The `fit-ingest` and `workout-docs` specs shall each carry an amendment record for the product-name and attribution changes, and the exemption table of the connectors service-neutral scan shall carry one entry admitting intervals.icu's address in exactly this connector's module, its tests and its section of the connectors documentation, so that every other part of the connector framework stays service-neutral.
