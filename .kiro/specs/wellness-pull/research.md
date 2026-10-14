# Research & Design Decisions — wellness-pull

## Summary
- **Feature**: `wellness-pull`
- **Discovery Scope**: Extension (Phase 8 connector framework and the
  intervals.icu connector), integrating with a sibling spec's seam
  (`wellness-store`'s intervals.icu delivery contract). Codebase-first, no
  network: nothing was fetched from intervals.icu and no web page was read in
  this session. The service facts below come from the brief's 2026-10-12
  measurement (one read-only GET at the maintainer's request, shapes only),
  the intervals-connector research record, and the live-check plan this spec
  adds (Requirement 11).
- **Key Findings**:
  1. The pull pipeline is FIT-only in six places, and every one of them has a
     single caller in `src/` (`connectors/pull.py`), so the change is contained:
     `is_fit` gate (`pull.py:590-604`), `delivery_name` (`delivery.py:77-105`),
     `_candidates`' literal `.fit` (`delivery.py:179-206`), the sweep's
     `layout.archive_path` (`delivery.py:272-274`), the ledger's sha invariant
     wording (`ledger.py:99-102`), and the hard-coded capability branch
     (`pull.py:419-445`). `DRIVEN_CAPABILITIES` (`protocol.py:141-143`) is
     re-exported but read by no `src/` module; the registry hard-codes
     `PULL_ACTIVITIES` (`registry.py:193-207`).
  2. The ledger reader silently ignores unknown top-level keys
     (`ledger.py:305-338` reads four keys by `data.get`) and the writer
     re-serializes only those four (`ledger.py:429-451`). An older fitdocs
     would therefore *drop* a wellness table on its next save. Only a format
     version bump makes the older version refuse instead
     (`ledger.py:310-314`).
  3. The test fixtures use `Capability.PULL_WELLNESS` as "a non-driven
     capability" in three places (`tests/connectors/conftest.py:359`,
     `tests/connectors/test_cli_connectors.py:106`, and through the login
     connector default, `tests/connectors/test_pull.py:2667-2690`). Driving the
     capability makes those connectors fail registration unless they move to a
     still-reserved capability.

## Research Log

### The connector framework today
- **Context**: what must change to drive a second capability and deliver a
  non-FIT file.
- **Sources Consulted**: `src/fitdocs/connectors/{protocol,registry,pull,delivery,ledger,settings,intervals,_atomic}.py`,
  `src/fitdocs/cli.py:1268-1546`, `.kiro/specs/connectors/{requirements,design}.md`,
  `.kiro/specs/intervals-connector/{requirements,design,research,tasks}.md`.
- **Findings**:
  - `_pull_one` (`pull.py:341-712`) runs, in order: ledger load
    (`:359-366`), sweep (`:379-386`), credential resolution and login renewal
    (`:388-417`), the capability refusal (`:420-424`), then the activity
    listing/fetch/deliver loop (`:426-693`), and a `finally` save
    (`:694-698`). Only `PULL_ACTIVITIES` is looked at.
  - `deliver` (`delivery.py:119-176`) writes through `write_atomic`
    (`_atomic.py:24-44`, dot-prefixed temp, fsync, `os.replace`) and reuses
    only an owned path with the same sha. `_candidates` escalates with a
    literal `.fit` (`delivery.py:197-206`).
  - `sweep` (`delivery.py:233-302`) resolves pending activity entries against
    `layout.archive_path` (`layout.py:296-298`), six outcomes.
  - The ledger (`ledger.py:78`, `LEDGER_VERSION = 1`) is a flat `entries`
    list keyed by `remote_id`, one aware `watermark`, invariants shared by
    load and save through `_invariant_violation` (`ledger.py:230-279`).
  - Settings strip two framework keys before the connector's own parser
    (`settings.py:72-74`, `:257-259`); `lookback_days` defaults to 30 and is
    capped at 3650 (`settings.py:66-67`).
  - The pull report is a flat per-instance dataclass (`pull.py:162-183`)
    printed by `cli._report_pull` (`cli.py:1470-1546`) from the ordered
    `_PULL_REPORT_ROWS` (`cli.py:1452-1468`); the packaged skill's pull table
    is bound to the dataclass fields minus three exclusions
    (`tests/test_agent_skill.py:137-178`, `:780-855`).
  - The intervals connector lists activities in overlapping 90-day windows
    (`intervals.py:251-272`), maps statuses in `_raise_for_status`
    (`intervals.py:384-405`) and declares exactly `{PULL_ACTIVITIES}`
    (`intervals.py:139`), pinned by `tests/connectors/test_intervals.py:118`
    with the named mutation "add `PULL_THRESHOLDS`"
    (intervals-connector `design.md:939-942`).
- **Implications**: the change is a framework extension plus one connector
  extension; no other package changes behavior. The folder connector keeps
  its `.fit`-only listing (`folder.py:161-163` calls
  `inbox.select_candidates`, which `wellness-store` leaves unchanged).

### The delivery contract with `wellness-store`
- **Context**: the delivered file must satisfy `wellness-store`'s intervals.icu
  format exactly.
- **Sources Consulted**: `.kiro/specs/wellness-store/design.md` § "Seams for
  downstream specs" 2 (normative), § IntervalsFormat, § Archive, § Merge;
  `requirements.md` Req 9, 15.
- **Findings**:
  - Envelope `{"format":"fitdocs.intervals-icu-wellness","version":1,
    "origins":{...},"records":[...]}`; `origins` optional; records verbatim,
    only the delivered days, sorted by `id`, no duplicate `id`; no other key;
    no pull timestamp; bytes are `json.dumps(sort_keys=True,
    separators=(",",":"), ensure_ascii=False) + "\n"`.
  - Archived as original bytes at
    `layout.wellness_archive_path(data_root, "intervals-icu", sha256, ".json")`;
    the connectors package may not import `fitdocs.wellness`, so the literals
    are repeated and pinned by a test to `intervals.FORMAT.id` and
    `intervals.FORMAT.archived_suffix`.
  - The merge keeps, per `(source, day, metric)`, the snapshot with the
    greatest revision; the intervals revision is `updated` normalized to UTC
    (`None` when absent or unparseable); a later revision with a field `null`
    makes the value absent (Req 9.2). Equal revisions with different values
    are a `check` conflict kept by `(entry_ref, ordinal)`.
  - Recognition parses the whole JSON only up to 64 MiB
    (`probe.JSON_PROBE_LIMIT`); a larger file is unrecognized.
- **Implications**: the pull must (a) produce the canonical bytes, (b) deliver
  re-deliveries only with a newer `updated` (or the merge would conflict), (c)
  keep each file far below 64 MiB (yearly chunks), and (d) depend on
  `updated` carrying an offset (TBC-W3), because a naive `updated` would
  normalize to `None` and turn every correction into a conflict.

### intervals.icu wellness (measured 2026-10-12 by the discovery, shapes only)
- `GET /api/v1/athlete/0/wellness?oldest=…&newest=…` returned a JSON list of
  483 records, 47 fields, every record with `updated`; computed fields `ctl`,
  `atl`, `rampRate`, `sportInfo` present on every record. Non-null counts are
  in the brief. The athlete object carries per-integration
  `*_wellness_keys` lists and download switches for Garmin, COROS, Polar,
  Suunto, Oura, WHOOP, Zepp, Huawei and Google (roadmap Phase 12, "Measured
  at discovery").
- Unverified, and planned for the live check (design.md "LiveCheckProcedure"):
  bound inclusivity, the `updated` form, whether `updated` moves when only
  computed fields are recomputed, the names `avgSleepingHR`, `respiration`,
  the seven subjective fields and `sleepQuality`, the exact
  `*_wellness_keys` names and element form, and which switch turns an
  integration's wellness import on.
- Rate limits: 5,000 requests a day and 2,500 per 15 minutes per key; 429
  carries `Retry-After` (brief). The transport retries data calls three times
  with `Retry-After` up to 60 s (`http.py:82-87`).

### Terms and attribution
- intervals.icu API terms §1.1 (effective 2025-10-23) require Garmin
  attribution "if your application displays information derived from
  Garmin-sourced data"; Garmin's API Brand Guidelines (V 6.30.2025) forbid
  implying Garmin endorsement of other devices' data (intervals-connector
  `research.md:97-133`).
- intervals.icu does not say which upstream supplied each day's value of a
  field; the per-integration `*_wellness_keys` lists name the fields an
  integration is set to import. A field one integration imports and another
  app also writes (HealthFit pushes through the API) cannot be attributed per
  value.
- **Implication**: attribute a field only when exactly one integration set
  to import wellness lists it; never guess; document the limit and the remedy
  (turn the field off in intervals.icu for an integration that never supplies
  it). The exact enable switch is TBC-W5.

### The Garmin data block (queue `2026-10-12-intervals-garmin-data-block-risk`)
- Forum 609 #752 and #816: Garmin-origin data, possibly including wellness and
  history, "likely" to be blocked from the API; no timeline; personal keys
  unanswered.
- **Implications**: (1) a withheld field arrives as `null` or missing and is
  delivered verbatim, so it is absent, never zero; (2) a whole-endpoint 403 on
  wellness becomes a wellness-specific error that names the restriction and
  the remedies (`wellness = false`; the Garmin export route), not the generic
  "report this client block" step; (3) nothing re-delivers a day because the
  drain could not use a delivery, so a changed payload shape cannot loop; (4)
  an integration whose attribution list vanishes produces a notice.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Second driven capability in the same engine (selected) | `WellnessPuller` operations; `_pull_one` runs a fixed step order (activities, then wellness) over one session and one ledger | One ledger save, one sweep, one credential resolution, one report per instance | `pull.py` grows; the step order is a contract | Mirrors `ActivityPuller` |
| A separate `pull_wellness` engine | Its own load/sweep/save per instance | Isolation | Two ledger saves race; two sweeps; credentials resolved twice | Rejected |
| Wellness as listed "activities" | Map each day to a `RemoteActivity`, deliver one file per day | No protocol change | 483 files per backfill, `.fit` naming and gate everywhere, no year chunking, revisions per day only | Rejected |

## Design Decisions

### Decision: a connector-declared extension and wellness format name, checked by a framework gate keyed by extension
- **Context**: Req 4.4-4.5; the framework must stay service-neutral
  (connectors Req 14.6) and may not import `fitdocs.wellness`.
- **Alternatives Considered**:
  1. A framework table of delivery formats naming `intervals-icu` and the
     envelope literals — puts a service's contract in framework modules.
  2. The connector declares `suffix` and `format` on its package; the
     framework checks the bytes by extension (`.json`: one well-formed JSON
     document ≤ 64 MiB), validates the format name as a slug, and composes
     the archive path through `layout.wellness_archive_path` (selected).
- **Rationale**: the framework knows how to check a JSON file and where
  `wellness-store` archives one; only the connector knows the envelope. The
  envelope's correctness is pinned by a cross-package contract test that runs
  the connector's bytes through `wellness-store`'s real recognizer and parser.
- **Trade-offs**: a connector could declare a format name `wellness-store`
  does not register; the sweep then never finds it archived and the delivery
  stays pending (visible, not destructive). The contract test prevents it for
  the shipped connector.

### Decision: wellness keyspace in the same ledger file; format version 2 written only when present
- **Context**: Req 5.3, 5.4; finding 2 above.
- **Alternatives Considered**: a second ledger file per instance; always
  stamping version 2.
- **Selected Approach**: a `[wellness]` table in `<instance>.toml`;
  `save_ledger` writes `ledger_version = 2` when the table is present and `1`
  otherwise; `load_ledger` reads both and refuses a wellness table under 1.
- **Rationale**: one atomic save keeps activity and wellness records
  consistent; activity-only ledgers stay byte-identical (connectors Req 7.3);
  an older fitdocs refuses a ledger it would otherwise truncate.

### Decision: change detection by an opaque revision the connector supplies
- **Context**: Req 3.4; the brief's "`updated` diff".
- **Selected Approach**: the framework compares the listed revision with the
  recorded one (inequality, not order). intervals.icu's revision is `updated`
  verbatim; a record without a text `updated` gets `sha256:<digest of the
  canonical record>`.
- **Follow-up**: TBC-W6 measures whether `updated` moves on recomputation of
  intervals.icu's own fitness model; if it does, the repair changes only the
  connector's revision rule (digest of the record without `updated` and the
  computed fields) and leaves the framework untouched.

### Decision: one delivery per calendar year of changed days
- **Context**: Req 4.1; the 64 MiB recognition bound; the archive's growth.
- **Rationale**: bounded files (at most 366 records, under a megabyte),
  deterministic grouping, and a scheduled pull (a 30-day re-check) produces
  one file, two across a new year.

### Decision: the wellness mark may move back, only through a forgotten delivery
- **Context**: Req 6.3. A forgotten activity is re-fetched only if a later
  listing reaches it; for wellness the first pull covers years, so a lost
  backfill file would otherwise never be re-listed.
- **Selected Approach**: forgetting a pending wellness delivery drops the days
  whose latest recorded delivery it was and lowers the wellness mark to the
  day before the earliest of them.

### Decision: `wellness` is a framework instance key, not an intervals.icu key
- **Context**: the roadmap lists "the enable setting" under the
  intervals-connector amendment. Taken without asking (auto-approve).
- **Rationale**: the dispatch must know per instance which driven capabilities
  run; a framework key needs no new protocol hook, validates uniformly ("this
  connector does not pull wellness"), and applies unchanged to a later Garmin
  or HealthFit connector. The intervals-connector amendment records that its
  instances use it.

### Decision: `CONTRACT_VERSION` advances (reversed at Step 3.5)
- **Context**: the ownership contract's `pull` bullet says "fetches new
  activity files" and lists what the pull never writes.
- **Draft position (rejected)**: no advance, because wiki-contract Req 2.15's
  guarantees were read as unchanged.
- **Controller ruling R1 (Step 3.5, round 1)**: advance to main + 1 at
  landing. The pull's stated removal guarantee now covers a second archive
  (`wellness-archive/`), it writes a non-activity file into the inbox, and
  its never-writes list grows. `contract.py:329-335` says the version
  "changes whenever a stated guarantee changes", and connectors' own 5 → 6
  bump (`contract.py:355-366`) was for exactly what `pull` writes and
  removes. A wiki-contract amendment records it; the declaration goldens are
  regenerated.

## Synthesis
- **Generalization**: "a connector delivers bytes with a declared form" covers
  both FIT activity files and wellness files; the delivery writer, its
  collision escalation and the sweep's six outcomes are generalized by
  extension and archive path rather than duplicated. The interface admits a
  future wellness connector (another format name, another extension with its
  own check) without a protocol change.
- **Build vs. adopt**: stdlib `json`, `hashlib` and `datetime` only; the
  existing transport, redactor, atomic writer, ledger and report machinery are
  reused. No new dependency.
- **Simplification**: no listing deferrals for wellness (no shipped connector
  defers a day); no separate wellness `since` key (`--since` and the
  connector's documented history start cover it); no caching of the athlete
  settings across packages (one request per yearly package is negligible);
  no per-value attribution (the service does not provide it).

## Risks & Mitigations
- `updated` lacks an offset → `wellness-store` normalizes it to `None` and a
  correction becomes a conflict. Mitigation: TBC-W3 in the live check; repair
  is a `wellness-store` intervals-format amendment (revision normalization).
- `updated` moves on every fitness recompute → the 30-day re-check re-delivers
  the window each pull (archive growth, no series change). Mitigation:
  TBC-W6; connector-local repair.
- Attribution over-claims when an integration is set to import a field it
  never supplies (a Garmin bike computer with wellness import on).
  Mitigation: TBC-W5 identifies the enable switch; documentation names the
  remedy in intervals.icu's settings.
- A Garmin block hides or nulls fields → re-delivered days lose
  intervals.icu-sourced Garmin values in the series (by `wellness-store`'s
  "latest record wins" rule). Mitigation: documented; the Garmin export
  (device source, outranks the relay by default) is the route; the
  attribution-change notice flags a vanished integration.
- A delivery the drain quarantines stays pending; its days are not re-sent.
  Mitigation: the drain reports it; documentation says to delete it to have
  the next pull fetch those days again.

## References
- `.kiro/specs/wellness-store/design.md` § "Seams for downstream specs" 2 —
  the delivery contract (normative).
- `.kiro/specs/connectors/design.md` "PullEngine", "Delivery lifecycle",
  "Ledger file" — the framework behavior extended here.
- `.kiro/specs/intervals-connector/design.md` "LiveCheckProcedure" and
  `tasks.md` 1.1/5.2 — the live-check shape reused.
- `.kiro/queue/2026-10-12-intervals-garmin-data-block-risk.md`.
- intervals.icu forum thread 609 (#752, #816), cited by the queue item.

## Live check findings

### Controller check — 2026-10-14 (task 1.1)

Read-only GETs with the composed fitdocs User-Agent and the gitignored key
read only in-process. Only shapes, names, booleans and counts were retained.
The requests ran from a temporary directory outside the repository and data
root; no response payload, account date, identifier, measurement or credential
was persisted. The temporary request directory was removed.

- **TBC-W1 — confirmed.** JSON array of 366 objects, 47 distinct keys;
  zero `id` form mismatches (`YYYY-MM-DD`). Key names:
  `abdomen`, `atl`, `atlLoad`, `avgSleepingHR`, `baevskySI`, `bloodGlucose`, `bodyFat`, `carbohydrates`, `comments`, `ctl`, `ctlLoad`, `diastolic`, `fatTotal`, `fatigue`, `floorsClimbed`, `hrv`, `hrvSDNN`, `hydration`, `hydrationVolume`, `id`, `injury`, `kcalConsumed`, `lactate`, `locked`, `menstrualPhase`, `menstrualPhasePredicted`, `mood`, `motivation`, `protein`, `rampRate`, `readiness`, `respiration`, `restingHR`, `sleepQuality`, `sleepScore`, `sleepSecs`, `soreness`, `spO2`, `sportInfo`, `steps`, `stress`, `systolic`, `tempRestingHR`, `tempWeight`, `updated`, `vo2max`, `weight`.
- **TBC-W2 — confirmed.** Equal oldest/newest bounds returned exactly one
  matching record. A newest bound after today returned HTTP 200 and an array.
- **TBC-W3 — confirmed.** Every `updated` value was text in the shape
  `YYYY-MM-DDTHH:MM:SS.fff+HH:MM`; zero lacked an offset.
- **TBC-W4 — confirmed for key presence and observed types.** Every planned
  field below was present. Fields with only null values have no observed
  non-null type; that is a limit of this check, not a default measurement.

| Field | Observed types | Non-null count |
|-------|----------------|----------------|
| `restingHR` | `NoneType`, `int` | 345 |
| `hrv` | `NoneType` | 0 |
| `hrvSDNN` | `NoneType`, `float` | 364 |
| `sleepSecs` | `NoneType`, `int` | 359 |
| `avgSleepingHR` | `NoneType` | 0 |
| `respiration` | `NoneType` | 0 |
| `spO2` | `NoneType`, `float` | 362 |
| `steps` | `NoneType`, `int` | 364 |
| `vo2max` | `NoneType`, `float` | 224 |
| `weight` | `NoneType`, `float` | 11 |
| `fatigue` | `NoneType`, `int` | 10 |
| `mood` | `NoneType`, `int` | 10 |
| `motivation` | `NoneType`, `int` | 10 |
| `soreness` | `NoneType`, `int` | 10 |
| `stress` | `NoneType`, `int` | 10 |
| `injury` | `NoneType`, `int` | 10 |
| `hydration` | `NoneType`, `int` | 10 |
| `sleepQuality` | `NoneType`, `int` | 1 |

- **TBC-W5 — contradicted (attribution namespace); switches observed.**
  The athlete response was an object. `*_wellness_keys` does not mean
  upstream-platform import keys in every case: `private_wellness_keys` is
  a visibility setting, and `icu_wellness_keys` is also not an upstream
  platform. The current broad pattern would attribute an ordinary record
  field to `private`. Task 6.3 must amend the TBC-W5 marker and add a
  numbered repair that excludes both non-platform namespaces. The download
  switches below are independent booleans; attribution should honor a
  known platform download switch when present, with its precise treatment
  specified by that repair. A read-only account check cannot establish
  causality by toggling settings; no setting was changed.

| Key | Value type | Element types | Length | Matching record keys |
|-----|------------|---------------|--------|----------------------|
| `google_wellness_keys` | `NoneType` | absent | absent | absent |
| `icu_garmin_wellness_keys` | `NoneType` | absent | absent | absent |
| `icu_wellness_keys` | `list` | str | 8 | 8 |
| `oura_wellness_keys` | `NoneType` | absent | absent | absent |
| `polar_wellness_keys` | `NoneType` | absent | absent | absent |
| `private_wellness_keys` | `list` | str | 1 | 1 |
| `whoop_wellness_keys` | `NoneType` | absent | absent | absent |

| Switch | Boolean |
|--------|---------|
| `icu_garmin_download_wellness` | `false` |
| `icu_garmin_health` | `true` |
| `polar_download_wellness` | `false` |

  The [public API schema](https://intervals.icu/api/v1/docs) confirms
  separate Garmin, Polar, Suunto, COROS, Zepp and Huawei wellness-download
  booleans, and string-list key settings. It documents no wellness-download
  boolean for Oura, WHOOP or Google. The schema lists `private_wellness_keys`
  separately from platform keys. Its bare property types do not explain
  visibility semantics; the observed non-platform namespace is the concrete
  contradiction being routed to the completion repair.
- **TBC-W6 — confirmed for the planned low-churn decision, with a limit.**
  Of 305 records older than 60 days, 25 had an update date more than seven
  days after their day. This small minority supplies no evidence of pervasive
  recomputation churn, so keep the stated `updated` revision. One snapshot
  cannot distinguish a genuine correction from recomputation.
- **TBC-W7 — confirmed.** A 366-day window returned HTTP 200, 366 records
  and approximately 330 KB (rounded to 10 KB).
- **TBC-W8 — confirmed.** All four check requests returned HTTP 200 with
  the fitdocs User-Agent. The shapes-only check was repeated to retain
  the permitted report and verify execution in the temporary working directory;
  every run agreed on all reported shapes and flags.

Task 1.1 records the contradiction; task 6.3 owns its design amendment and
numbered implementation repair. No upstream intervals-format field, date
or timestamp amendment is required by TBC-W1, TBC-W3 or TBC-W4.
