# Brief: wellness-pull

## Problem

intervals.icu holds the athlete's daily wellness, but fitdocs pulls only
activity files from it. For the maintainer, that is 483 days of resting HR,
HRV, sleep, SpO2, steps, VO2max and weight, relayed from Apple Health by
HealthFit since 2025-06-17. For athletes on other platforms it is the one
practical aggregator. intervals.icu imports wellness from Garmin, COROS,
Polar, Suunto, Oura, WHOOP, Zepp and Huawei, and from Apple Health through
bridge apps (research 2026-10-12, <https://www.intervals.icu/features/wellness/>).
Without a pull, the athlete would export and drop a wellness file by hand
every day.

## Current State

- The connector protocol reserves `pull-wellness` but nothing drives it.
  - It is `Capability.PULL_WELLNESS` (`connectors/protocol.py:54`, `:132-138`),
    with `driven=False`.
  - "Reserved" means a connector may declare it, the registry checks no
    operation for it, and no command invokes it (`connectors/registry.py:127-129`;
    connectors `requirements.md:118-121`, Req 1.2-1.4).
- **The pull pipeline is file-centric and FIT-only:**
  - a fetch returns bytes (`Fetched`, `protocol.py:208-229`);
  - bytes must pass the `is_fit` header gate or are skipped as "not a FIT
    file" (`pull.py:589-598`, `delivery.py:63-74`);
  - delivery writes `.fit`-named files into `<inbox>/<instance>/`
    (`delivery.py:119-135`);
  - `run_pull` hard-codes the activity capability (`pull.py:420-445`) and has
    no dispatch table.
- The ledger (`.fitdocs/connectors/<instance>.toml`, `LEDGER_VERSION = 1`,
  `ledger.py:78`, `:87-121`) is keyed by remote activity id and holds one
  watermark per instance.
- Connectors may output only listings, bytes and credential updates
  (connectors Req 1.9). They may import only the stdlib, `layout`,
  `settings`, `inbox` and `version` (`connectors/__init__.py:13-18`).
- The intervals.icu connector:
  - declares exactly `{PULL_ACTIVITIES}` (`connectors/intervals.py:139`),
    pinned by the named mutation "add PULL_THRESHOLDS"
    (intervals-connector `design.md:939-942`);
  - lists activities over overlapping 90-day windows (`:189-225`, `:251-272`)
    and fetches `/activity/{id}/file` (`:227-248`).
- **Measured on the maintainer's account** (2026-10-12; one read-only GET,
  shapes only, at the maintainer's request):
  - `GET /api/v1/athlete/0/wellness?oldest=…&newest=…` returns a JSON list
    of 483 day records with 47 fields, 2025-06-17 to 2026-10-12.
  - Non-null counts:

    | Field | Days |
    |---|---|
    | `restingHR` | 452 |
    | `hrvSDNN` | 481 |
    | `hrv` (rMSSD) | 0 |
    | `sleepSecs` | 476 |
    | `sleepScore`, `avgSleepingHR`, `respiration`, `readiness` | 0 |
    | `spO2` | 479 |
    | `steps` | 481 |
    | `vo2max` | 242 |
    | `weight` | 29 |
    | subjective fields (`fatigue`, `mood`, `motivation`, `soreness`, `stress`, `injury`, `hydration`) | 10 |

  - Every record carries an `updated` timestamp.
  - Every record also carries intervals.icu's own `ctl`, `atl`, `rampRate`
    and `sportInfo`. intervals.icu computes these from its own model; they
    are not wellness inputs.
  - The athlete object carries per-integration `*_wellness_keys` lists
    (`icu_garmin_wellness_keys`, `oura_wellness_keys`, …). They name which
    fields each upstream supplies.

## Desired Outcome

- An intervals.icu connector instance can declare wellness.
- `fitdocs pull` then fetches the wellness days that changed since the last
  pull and delivers them into the inbox as a wellness file.
- The drain (`wellness-store`) ingests that file the same way it ingests one
  the athlete dropped there by hand.
- The pull stays one-shot and incremental. A second pull with nothing
  changed delivers nothing.

## Approach

**Connectors fill the inbox, and the engine reconciles** (maintainer,
2026-10-12; Phase 8's decision, extended to wellness). The connector stays a
thin fetcher:

- it lists and fetches;
- it delivers bytes atomically into the inbox, under a wellness file name the
  drain recognizes;
- it records what it delivered in its ledger.

It never parses wellness into the series and never writes outside the inbox
and its ledger.

## Scope

- **In**:
  - connectors amendment:
    - drive `PULL_WELLNESS` through a new optional operation (for example
      `WellnessPuller`);
    - a capability dispatch in place of the hard-coded activity branch;
    - a delivery gate keyed by declared format instead of FIT-only, so a
      wellness payload passes without loosening the FIT gate for activity
      fetches;
    - a wellness keyspace and watermark in the ledger, which may mean a
      ledger version bump;
    - amended Req 1.2-1.4 and 1.9 wording;
  - intervals-connector amendment:
    - the wellness endpoint and its date windows;
    - change detection on `updated`: the list endpoint has no updated-since
      filter, so re-pull a trailing window and diff;
    - the capability declaration, and the "add PULL_THRESHOLDS"-style
      mutation re-pinned;
    - a per-instance setting to enable wellness;
    - a first-pull history range, so the whole account can be backfilled
      once;
  - the delivered file format: the JSON records as intervals.icu returns
    them (changed days only), named so `wellness-store` recognizes them;
  - the source attribution that intervals.icu's API terms require for
    Garmin-sourced data. Derive it from the athlete's `*_wellness_keys` lists
    if the design confirms they map fields to upstreams;
  - `docs/connectors.md`, the packaged skill's routine, the surface pin
    (`tests/connectors/test_surface.py:117-119`).
- **Out**:
  - parsing, merging or storing wellness (owned by `wellness-store`);
  - intervals.icu's computed fields (`ctl`, `atl`, `rampRate`, `ctlLoad`,
    `atlLoad`, `sportInfo` eFTP/W′). fitdocs computes its own model and never
    imports another model's output as data;
  - writing wellness to intervals.icu (any push);
  - intervals.icu custom wellness fields. Users add sleep stages that way;
    how they appear in the JSON is unverified;
  - connectors for other services (follow-ons; see the roadmap).

## Boundary Candidates

- The connector-side protocol, dispatch and ledger: connectors amendment.
- The intervals.icu wellness client: intervals-connector amendment.
- The wellness file format on the inbox side: the contract with
  `wellness-store`, which owns its parser.

## Out of Boundary

- The wellness model, archive, series and merge (`wellness-store`).
- Any document or index change.

## Upstream / Downstream

- **Upstream**: `connectors` (protocol, ledger, delivery, HTTP seam,
  credentials), `intervals-connector` (auth, windows, status mapping),
  `wellness-store` (the format registry the delivered file must satisfy).
- **Downstream**: every Phase 12 consumer sees pulled wellness through the
  series. Future connectors that declare `pull-wellness` (a Garmin or
  HealthFit connector, if ever built) reuse the operation and dispatch.

## Existing Spec Touchpoints

- **Extends**:
  - `connectors`: amendment for driving `pull-wellness`, non-FIT delivery and
    the ledger keyspace;
  - `intervals-connector`: amendment for the wellness endpoint and capability.
- **Adjacent**: `wellness-store` (the inbox-side parser of the delivered
  file).

## Constraints

- No new runtime dependency. The stdlib HTTP seam is reused.
- The network is used only by `fitdocs pull`.
- Credentials stay outside the data root, and the key is never logged.
- Rate limits: 5,000 requests a day and 2,500 per 15 minutes per API key,
  with a 429 carrying `Retry-After` (research 2026-10-12). A wellness pull is
  one request per window.
- **Freshness trap**: some upstreams (Zepp, for example) poll only when the
  athlete visits intervals.icu, so a one-shot pull can read stale days.
  Re-pulling a trailing window covers late arrivals. Document the trap.
- **Garmin block risk** (<https://forum.intervals.icu/t/api-access-to-intervals-icu/609>):
  - **#752 (2026-10-09):** the intervals.icu developer wrote that Garmin data
    will "likely" be blocked from the API.
  - **#816 (2026-10-12):** the developer speculated the restriction would
    "probably" cover activities, FIT files, streams *and* wellness, and
    "likely apply to historical data, anything that came in via the Garmin
    API". Manual uploads are unaffected. There is no timeline, and nothing
    is final.
  - **Personal API keys** are still unanswered (asked in #755).
  - **Consequences:**
    - for Garmin athletes, `wellness-store`'s Garmin-export route is the
      fallback;
    - the pull must treat a refused or emptied Garmin-sourced field as
      absent, never as zero, and report it.
- **The delivery path is FIT-only in several places** (viability
  2026-10-12):
  - `delivery.py:76-111`: `delivery_name` always ends in `.fit`, so a JSON
    payload would be quarantined;
  - `delivery.py:272-273`: `sweep` resolves pending files only through the
    `.fit` archive path;
  - `ledger.py:99-102`: the sha invariant is tied to
    `fit-archive/<sha>.fit`;
  - `pull.py:589-603`: the `is_fit` gate;
  - `protocol.py:141-143`: `DRIVEN_CAPABILITIES`;
  - tests `tests/connectors/test_pull.py:375-403` and
    `tests/connectors/test_delivery.py:84-100`.
- Records change after the fact. A WHOOP sync replaces earlier values, and a
  manual edit can revert to the Oura value. The `updated` diff must therefore
  re-deliver a day whose values changed.
