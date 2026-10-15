# Implementation Plan

## Upstream Prerequisites

- **`wellness-store` is merged to `main` before any task here starts.** This
  plan uses its `layout.wellness_archive_path`, its
  `fitdocs.wellness.formats.intervals` constants (`FORMAT`,
  `DELIVERY_FORMAT`, `DELIVERY_VERSION`), `fitdocs.wellness.probe.JSON_PROBE_LIMIT`,
  `fitdocs.wellness.registry.recognize`, and (6.1) the drain's wellness step.
  `src/fitdocs/connectors/` never imports `fitdocs.wellness`; tests may.
- **One version constant moves.** `CONTRACT_VERSION` advances to **main + 1
  at landing** (design Decision 13, controller ruling R1): 5.2 makes the
  bump against the branch's base and 6.2 re-derives it after the final
  rebase. The other `CONTRACT_VERSION` bumpers, any of which may land first,
  are `dashboards` (Phase 11) and the four other Phase 12 landers that bump
  it: `wellness-store`, `hr-derivation`, `recovery` and `workout-wellness`
  (five Phase 12 bumpers in all, counting this one; `apple-health-import`
  does not bump). `DOC_VERSION` and the index `SCHEMA_VERSION` are
  untouched. `LEDGER_VERSION` is connectors-internal and moves in 2.2 only.
- **Peers.** `dashboards` (connectors Amendment 3, a row in
  `tests/connectors/test_e2e.py`'s offline parametrize list) and `recovery`
  (its own connectors amendment, another row in that list) may land first.
  This plan never edits that list's rows; 6.1 edits only the
  `_fresh_synced_root` settings. Amendment numbers are the next free at
  landing (5.2).
- **Task 1.1 belongs to the controller session.** It needs the maintainer's
  key. No task depends on it except the completion gate 6.3; list order does
  not make 1.2 onward wait for it.
- **Existing spec updates carried by this plan** (design § Existing Spec
  Amendments): `wiki-contract` Amendment N (5.2), and `connectors`
  Amendment N and `intervals-connector` Amendment 1 (5.3).

**Hard rules for every task**

- **No network, no real credentials.** Every new test lives under
  `tests/connectors/` (its `conftest.py` makes constructing a socket raise and
  isolates `FITDOCS_CREDENTIALS_DIR`, `HOME`, `XDG_CONFIG_HOME` and every
  `FITDOCS_CONNECTOR_*` variable) except the confinement entry in
  `tests/test_confinement.py` and the skill pins in `tests/test_agent_skill.py`,
  which reach no transport. The key is the synthetic `ik-synthetic-7Q2x9`.
- **No personal data.** Wellness records, athlete objects, dates and values
  are invented in the test (dates from `tests/fixtures/builder.py`'s epoch);
  nothing from a real account appears in a test, fixture, doc or spec file.
- **Imports** (design § Allowed Dependencies): the connectors allow-list in
  `tests/connectors/test_boundary.py:276-379` does not change;
  `connectors/intervals.py` imports only the standard library and
  `fitdocs.connectors.{errors,http,protocol,secrets}`; `connectors/ledger.py`
  does not import `protocol`; no clock call in the package. No new runtime
  dependency.
- **Absent is `None`**: no default, `0` or empty string for a value the
  service did not state.
- **The activity pull is unchanged.** Its FIT gate, its channels, its
  watermark and every existing test outside the re-pins this plan names stay
  as they are.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination): each named mutation is applied, observed red,
  reverted by restoring a `cp` taken before it, observed green, and recorded
  in Implementation Notes. A mutation that cannot be made red is reported
  UNPINNED. Run the prose-claim grep over changed test files and re-run or
  delete every surviving claim.
- **Fixtures discriminate.** Distinct values where a mapping is asserted;
  listing order, date order and revision order disagree; the interesting day
  is not first; an asserted end state shown false beforehand; "nothing
  written" asserted on bytes *and* `st_mtime_ns`.
- **Parallel streams.** `(P)` tasks run in separate worktrees and touch only
  the files their `_Boundary:_` names plus their own new test module.
  `tests/connectors/conftest.py` is edited by 1.2 only and is frozen
  afterwards; a later task that needs another helper defines it locally.
- **No literal service URL in a new test module.** Tests build intervals.icu
  addresses from `fitdocs.connectors.intervals.API_BASE`, so the NeutralScan
  exemption table (`tests/connectors/test_docs.py:615-622`) needs no new
  entry; a task that finds it needs one stops and reports.
- **Never run the CLI by hand while a full `uv run pytest` is in flight in the
  same worktree** (`tests/test_bytecode_hygiene.py`).
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`,
  `git clean` or `git checkout -- <path>`; never chain a destructive command
  after `cd`.
- **Types and lint.** Each task runs `uv run mypy`, `uv run ruff check` and
  `uv run ruff format --check`.
- **Stop and report** on any need for: importing `fitdocs.wellness` from
  `src/fitdocs/connectors/`; editing `wellness-store` code outside a 6.3
  repair task (7.x); changing activity-pull behavior; editing a row of the offline
  parametrize list; a runtime dependency; a write outside the inbox and the
  ledger from the pull.

## Shared source files

Each file below has more than one writer; its writers are sequential.

- `src/fitdocs/connectors/delivery.py` and
  `tests/connectors/test_wellness_delivery.py`: 2.3 (check, name,
  `deliver(suffix=)`), then 2.4 (the sweep).
- `src/fitdocs/connectors/intervals.py` and
  `tests/connectors/test_intervals_wellness.py`: 2.5 (listing, status
  mapping), then 2.6 (packaging, attribution, the capability declaration).
- `src/fitdocs/connectors/pull.py` and `tests/connectors/test_wellness_pull.py`:
  3.1 (run order, listing half), then 3.2 (packaging half).
- `tests/connectors/conftest.py`: 1.2 only.
- `tests/test_agent_skill.py`: 3.1 (one line: `"wellness"` joins
  `_PULL_EXCLUSIONS` at `:141`, in the same change that adds
  `InstancePullReport.wellness`), then 4.2 (the wellness binding).
- `src/fitdocs/cli.py`: 4.1 only. `SKILL.md`: 4.2 only. `docs/connectors.md`
  and its pins in `tests/connectors/test_docs.py` and
  `tests/connectors/test_intervals_docs.py`: 5.1 only.
- `src/fitdocs/contract.py`, `docs/ownership-contract.md`, the declaration
  goldens, the literal version pins, the head-paragraph phrase pins and the
  literal history assertion in `tests/identity/test_contract_docs.py`: 5.2,
  then 6.2 (re-derivation).
- `tests/connectors/test_wellness_records.py`: 5.2 creates it (contract
  records), then 5.3 appends (guide, changelog, amendment headings).
- `CHANGELOG.md`: 5.3, then 6.2 (the contract version numbers).
- `tests/connectors/test_e2e.py` and `tests/test_confinement.py`: 6.1 only.
- `.kiro/steering/roadmap.md`: 6.3 only.

## Cross-spec shared files (append-only, keep both sides on rebase)

`tests/connectors/test_surface.py` (`EXPECTED_ALL`, count),
`tests/connectors/test_e2e.py` (rows other plans append; this plan edits the
`_fresh_synced_root` settings and one key-variable line in the shared test
body beside `:349`, which `dashboards` 6.5 and `recovery` also edit),
`WRITING_ENTRY_POINTS`, `CHANGELOG.md` Unreleased, `CONTRACT_VERSION` and
its history paragraph, the declaration goldens' version line,
`docs/ownership-contract.md` (the version line, the "What changed at this
version" paragraph each lander replaces, and the `pull` bullet),
`.kiro/specs/wiki-contract/requirements.md`'s amendment list,
`tests/identity/test_contract_docs.py` (each bumper appends literal
assertions to `test_the_version_history_records_the_amendment` and re-pins
the head-paragraph phrases),
`docs/wellness.md` (`wellness-store`'s page; one passage), the
`fitdocs-workouts` skill's `## Reading the report`, the connectors
requirements' amendment list.

---

- [x] 1. Foundation: the live check and the protocol

- [x] 1.1 Run the live check against the maintainer's intervals.icu account and record what it finds
  - Performed by the implementation's **controller session**, never by an
    implementer subagent, following design.md "LiveCheckProcedure" TBC-W1 to
    TBC-W8, from a temporary directory outside the repository and the data
    root, deleted afterwards. A Python script reads the key in-process from
    the maintainer's gitignored `.env`; the key is never echoed, never on a
    command line, never written, never passed to a subagent, never committed.
    Read-only GETs only, with the fitdocs User-Agent.
  - Prints and records only key names, value types, booleans and counts:
    never a wellness value, a date, an identifier or the key.
  - Observable: `research.md` "Live check findings" names the check date and
    marks each of TBC-W1 to TBC-W8 confirmed or contradicted. This record is
    the only place a TBC item is marked; 6.3 reads it.
  - A contradiction is repaired through 6.3 (design amended at its marker, a
    numbered repair task 7.x appended); a contradicted `id` form, field name
    or `updated` form (TBC-W1, TBC-W3, TBC-W4) is a `wellness-store`
    intervals-format amendment carried by that repair task.
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 13.5_

- [x] 1.2 Drive pull-wellness in the protocol and the registry, and publish the four names
  - **Protocol** per design § WellnessProtocol: `WellnessDay` (its record
    left out of its representation), `WellnessListing`, `WellnessPackage`,
    `WellnessPuller`; `PULL_WELLNESS` driven; `DRIVEN_CAPABILITIES` holds
    both driven capabilities; the module docstring says two are driven.
  - **Registry** per design § RegistryRule: a connector declaring
    `PULL_WELLNESS` must have both wellness operations; docstrings updated.
  - **Surface**: the four names appended at the end of `__all__` (46 → 50)
    and the docstring's count at `src/fitdocs/connectors/__init__.py:21`;
    re-pin `tests/connectors/test_surface.py` (`EXPECTED_ALL`,
    `_DEFINING_MODULE`, the count at `:117-119`, and
    `test_import_fitdocs_connectors_exposes_exactly_46_names` at `:147-149`,
    renamed for 50) and `tests/connectors/test_protocol.py:191-194`.
  - **Fixtures**: the "non-driven capability" defaults move from
    `PULL_WELLNESS` to `PULL_PLANS` (`tests/connectors/conftest.py:359`,
    `tests/connectors/test_cli_connectors.py:106`); `conftest.py` gains a
    `ScriptedWellnessPuller` built on `_ScriptedActivityPullerMixin` with a
    `capabilities=` override, the way `ScriptedLoginConnector` is built
    (`conftest.py:331-368`): no authentication, default `{PULL_WELLNESS}`,
    `{PULL_ACTIVITIES, PULL_WELLNESS}` when a run-order test also scripts an
    activity listing (including one that raises `ConnectorError` or
    `AuthFailure`); scripted listing and package answers including
    exceptions; every call recorded, and the settings table its
    `parse_settings` saw. Two `_typed_*` structural lines check it as a
    `Connector` and as a `WellnessPuller` (beside `conftest.py:418-427`).
    `conftest.py` is frozen after this task.
  - **Tests** (`tests/connectors/test_wellness_protocol.py`): the driven set is
    exactly the two; the four types' fields by `dataclasses.fields`; a
    `WellnessDay`'s repr omits a distinctive record value; a `PULL_WELLNESS`
    connector without `package_wellness` is refused naming it, one without
    `list_wellness` likewise, one with both accepted and neither operation
    called; a `PULL_PLANS`-only connector still needs no operation.
  - **Mutations:** leave `PULL_WELLNESS` `driven=False`; drop it from
    `DRIVEN_CAPABILITIES`; delete the registry's wellness block; check only
    `list_wellness` (the missing-package case reds); drop `repr=False`; drop a
    name from `__all__`.
  - **Observable:** `uv run pytest tests/connectors` green with the re-pins;
    `get("intervals")` and `get("folder")` still register.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 2. Core: settings, ledger, delivery and the intervals.icu operations

- [x] 2.1 (P) Accept the `wellness` key on an instance whose connector pulls wellness
  - Per design § WellnessSettingsKey: a framework key beside
    `lookback_days`, default `false`, checked after `lookback_days`, never
    handed to the connector's own settings; `ConnectorInstance.wellness`;
    module docstring's check order.
  - **Tests** (`tests/connectors/test_wellness_settings.py`): absent →
    `False`; `true` on a registered `ScriptedWellnessPuller` instance → `True`
    and the connector's recorded settings table lacks the key; `"yes"`, `1`
    and `0` refused naming the settings file, the instance and `wellness`;
    `true` on a `folder` instance refused naming the folder connector;
    `false` on a `folder` instance accepted; `fitdocs pull` with the refused
    table exits 2 with no ledger file and no inbox directory created
    (`CliRunner`, no transport). Re-pin
    `tests/connectors/test_settings.py:853-855` (`ConnectorInstance`'s field
    names end with `wellness`).
  - **Mutations:** accept an `int` (drop the `bool` check); drop the
    capability check; leave `wellness` out of `_RESERVED_KEYS` (the recorded
    table gains the key).
  - **Observable:** `uv run pytest tests/connectors/test_wellness_settings.py
    tests/connectors/test_settings.py` green.
  - _Requirements: 2.1, 2.3, 2.4, 2.5_
  - _Boundary: WellnessSettingsKey_

- [x] 2.2 (P) Give the ledger its wellness keyspace and the version rule
  - Per design § WellnessLedger: the three version constants, the wellness
    types and methods, `Ledger.wellness` and `with_wellness`, copy methods
    through `dataclasses.replace`, the invariants inside
    `_invariant_violation`, serialization and parsing of `[wellness]`.
  - **Tests** (`tests/connectors/test_wellness_ledger.py`): an activity-only
    ledger saves byte-identical to a literal golden of today's format with
    `ledger_version = 1`; a wellness ledger saves `ledger_version = 2` and
    round-trips (fixture days and pending records built unsorted); version 1
    with `[wellness]` refused naming the file; version 3 refused; one refusal
    per invariant (a datetime `through`, unsorted or duplicate days, an empty
    or 513-character revision, a bad sha, an unsafe path, a `.fit` suffix, a
    non-slug format, unsorted origins), each also raising `ValueError` from
    `save_ledger` with nothing written; `with_entry`, `without` and
    `with_watermark` on a ledger with wellness keep it; `forget` on three days
    where two carry the forgotten sha and one of those was later re-recorded
    under another sha drops exactly one day and sets `through` to the day
    before it; `forget` of an unknown path is a no-op; `with_coverage` sets
    on `None`, advances on overlap and on adjacency, keeps on a gap; `entry`
    distinguishes "no entry" from an entry with `revision=None`. Re-pin
    `tests/connectors/test_ledger.py` (`:50`, `:146`, `:445-448`, `:651`).
  - **Mutations:** always stamp version 2 (the golden reds); accept wellness
    under version 1; build `Ledger` field by field in `with_entry` (the keep
    test reds); `forget` dropping by date range instead of sha; `forget`
    without lowering; `with_coverage` crossing a gap; accept a datetime
    `through`; serialize days in insertion order.
  - **Observable:** `uv run pytest tests/connectors/test_wellness_ledger.py
    tests/connectors/test_ledger.py` green.
  - _Requirements: 3.7, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 6.3_
  - _Boundary: WellnessLedger_

- [x] 2.3 (P) Check, name and deliver a wellness package by its declared extension
  - Per design § WellnessDelivery: `MAX_WELLNESS_JSON_BYTES`,
    `FORMAT_NAME_PATTERN`, `WELLNESS_CHECKS`, `wellness_package_problem`,
    `wellness_delivery_name`, `wellness_archived`, and `deliver`'s `suffix`
    keyword through `_candidates`; the module docstring no longer says every
    delivery is FIT.
  - **Tests** (`tests/connectors/test_wellness_delivery.py`): the name for a
    one-day and a multi-day span; `deliver(suffix=".json")` into an occupied
    name escalates to `-<sha8>.json` and then `-<sha8>-2.json`, while a
    default call still escalates to `.fit` (the existing
    `tests/connectors/test_delivery.py` stays unmodified and green);
    `wellness_archived` true only for a real file at
    `layout.wellness_archive_path(root, "intervals-icu", sha, ".json")` (a
    file at `fit-archive/<sha>.fit` does not count); a passing package and one
    refusal each for a non-slug format, `.fit`, `.csv`, a non-slug origin, empty
    data, invalid JSON, a byte-order mark, and one byte over the size bound
    (bound patched in the test); `MAX_WELLNESS_JSON_BYTES` equals
    `fitdocs.wellness.probe.JSON_PROBE_LIMIT`.
  - **Mutations:** keep the literal `.fit` in `_candidates`; accept `.fit` in
    `WELLNESS_CHECKS`; skip the size check; decode with `utf-8-sig`; skip the
    format check; compose the archived path with `layout.archive_path`.
  - **Observable:** `uv run pytest tests/connectors/test_wellness_delivery.py
    tests/connectors/test_delivery.py` green.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Boundary: WellnessDelivery_

- [x] 2.4 Resolve pending wellness deliveries in the sweep
  - Per design § WellnessSweep: after the unchanged activity loop, the
    five outcomes for `ledger.wellness.pending` against the wellness archive.
  - **Tests** (appended to `tests/connectors/test_wellness_delivery.py`): one
    ledger holding an activity pending entry and four wellness pending
    records, each in a different state (archived and equal → removed and in
    `removed`; archived and changed → released, file untouched; archived and
    gone → settled; not archived and present → still pending, file
    untouched); a fifth, not archived and gone → forgotten, its days dropped
    and `through` lowered; the activity entry resolved by its own archive; a
    read failure and a removal failure (the `_remove` seam) leave the record
    pending and appear in `failures` keyed by path.
  - **Mutations:** check wellness archived-ness with `layout.archive_path`;
    remove when the hash differs; treat "not archived, present" as
    forgotten; forget without dropping days.
  - **Observable:** `uv run pytest tests/connectors/test_wellness_delivery.py`
    green.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 9.7_
  - _Depends: 2.2, 2.3_

- [x] 2.5 (P) List intervals.icu wellness by year windows and map wellness statuses
  - Per design § IntervalsWellness "Listing" and "Status mapping": the
    wellness constants, `_wellness_windows`, `list_wellness`,
    `_content_revision`, `_raise_for_wellness_status` (used by 2.6 too). The
    connector's declared capabilities do not change here (2.6 declares
    `PULL_WELLNESS` once both operations exist, so registration never fails
    in between).
  - **Tests** (`tests/connectors/test_intervals_wellness.py`, `FakeTransport`):
    `_wellness_windows` for a three-year span and a one-day span (every date
    from `start − 1 day` to `end` inside a window; no window above 366 days);
    `list_wellness(oldest=None)` at a fixed `now` requests from 2009-12-31,
    ends at the day after the UTC date, sends the Basic header as a secret
    header, and makes one request per window; a record repeated across two
    windows listed once; `updated` as text → that revision; `updated` absent
    or a number → `sha256:` revision equal for two key orders of the same
    record; a record whose other fields have hostile types still lists (no
    other field read); refusals naming the problem for a non-array body, a
    non-object entry, a missing `id`, `2026-1-5`, `2026-02-30`; 401 →
    `AuthFailure` rejected; 403 → `ConnectorError` whose message names
    Garmin, `wellness = false` and Garmin's own export; 429 and 503 after the
    client's retries → the existing rate-limit and unavailable messages; 404
    → the status message naming 404; the key and its Basic form in no URL or
    message.
  - **Mutations:** drop the one-day widening of the first window (coverage
    reds); `<` → `<=` in the window loop; skip the seen-date check; take a
    non-string `updated` as the revision; digest without `sort_keys`; map 403
    through `auth_failure_from` (blocked) instead of the wellness message.
  - **Observable:** `uv run pytest tests/connectors/test_intervals_wellness.py
    tests/connectors/test_intervals.py` green; `IntervalsConnector().capabilities`
    unchanged.
  - _Requirements: 3.2, 7.2, 7.3, 7.4, 7.5, 7.6, 7.8, 9.1, 9.2, 9.3, 9.4, 9.8_
  - _Boundary: IntervalsWellness_

- [x] 2.6 Package intervals.icu wellness with Garmin attribution and declare the capability
  - Per design § IntervalsWellness "Packaging": the athlete-settings
    request, `_wellness_origins`, the envelope bytes, `package_wellness`;
    `capabilities = {PULL_ACTIVITIES, PULL_WELLNESS}`; re-pin
    `tests/connectors/test_intervals.py:118`.
  - **Tests** (appended to `tests/connectors/test_intervals_wellness.py`):
    the package for two synthetic records given in reverse date order equals
    a golden byte literal (records sorted by `id`, keys sorted at every
    level, computed fields and `null`s kept, one trailing newline, no other
    key); with no attributable field the bytes carry no `origins` key;
    `suffix`, `format` and `origins` of the result; the athlete request made
    once per call; origins for: Garmin alone, Garmin and Oura sharing one
    field (that field unattributed, the others kept), an empty list, a
    non-string element, `google_fit_wellness_keys` → `google-fit`,
    `icu_wellness_keys` → nothing; a malformed athlete body and each status
    of 2.5's mapping on the athlete request; a record that is not a `dict` →
    `ConnectorError`; capabilities exactly the two and `validate_connector`
    accepts the connector; the literal pins `WELLNESS_FORMAT ==
    FORMAT.id`, `WELLNESS_SUFFIX == FORMAT.archived_suffix`,
    `WELLNESS_DELIVERY_FORMAT == DELIVERY_FORMAT`,
    `WELLNESS_DELIVERY_VERSION == DELIVERY_VERSION`
    (`fitdocs.wellness.formats.intervals`); **contract test**: the package
    bytes, written to a temporary `.json`, are recognized by
    `fitdocs.wellness.registry.recognize` as the `intervals-icu` format and
    its parser yields the delivered dates, a mapped value and origin
    `garmin`, and no metric from a computed field.
  - **Mutations:** drop `sort_keys`; add a pull-time key; emit
    `"origins": {}`; attribute on `>= 1` claims; strip the computed fields;
    sort records by revision (fixture revisions disagree with ids); add
    `PULL_THRESHOLDS` to the capabilities.
  - **Observable:** `uv run pytest tests/connectors` green; the contract test
    passes against `wellness-store`'s real parser.
  - _Requirements: 7.1, 7.6, 7.7, 7.8, 8.1, 8.2, 8.3, 8.4, 8.5, 9.4, 13.3_
  - _Depends: 2.5_

- [x] 3. Integration: the pull engine

- [x] 3.1 Run each instance's driven capabilities in order, and list and diff wellness
  - Per design § RunOrder and § WellnessStep steps 1-5 and 7: the report
    types, `InstancePullReport.wellness`, `PullReport.failed`, `_runnable` and
    the nothing-to-pull detail (replacing the refusal at `pull.py:419-424`),
    the session built once, the activity step's authentication flag, the
    ledger holder and the `finally` save, and `_pull_wellness` through the
    listing, its validation, the diff, the dry run, and the mark when no day
    changed. Until 3.2, changed days in a non-dry run are left unrecorded and
    the mark is not advanced; 3.1's tests use dry runs, unchanged listings
    and seeded ledgers only, and 3.1 records this interim branch in
    Implementation Notes so that 3.2's first test retires it.
  - **Re-pins the new report field turns red**:
    `tests/connectors/test_cli_connectors.py:1737-1738` (the channel set
    derived from `InstancePullReport` also excludes `wellness`) and
    `tests/test_agent_skill.py:141` (`"wellness"` joins `_PULL_EXCLUSIONS`,
    so `test_literal_pull_channel_set_matches_the_derived_dataclass_fields`
    still derives eight channels); this one line is 3.1's only edit to that
    file.
  - **Tests** (`tests/connectors/test_wellness_pull.py`, `run_pull` with
    `ScriptedWellnessPuller` and a scripted activity puller): wellness not
    enabled → no listing call, `wellness is None`, and an activity-only
    ledger byte-identical to before; the two nothing-to-pull details (re-pin
    `tests/connectors/test_pull.py:2497-2511`); an activity listing
    `ConnectorError` → the wellness step still lists; an activity
    `AuthFailure` → no wellness listing, `wellness is None`; `oldest` is
    `None` with no mark, mark less a look-back of 7 (not the default 30),
    and `--since`'s UTC date when given (fixture where the UTC date differs
    from the date of the local-midnight instant's naive form); a listing
    raising `AuthFailure` → wellness error carrying the reconnect step,
    `ConnectorError` and `ValueError` → wellness error; a listing with
    `oldest > newest` or a datetime bound → error; a duplicate date, an
    empty revision, a 513-character revision and a control character →
    failed notes, the first occurrence kept, the mark not advanced; `None`
    equals `None` in the diff; a dry run → sorted `would_deliver`, ledger
    bytes and `st_mtime_ns` unchanged, no package call; an unchanged listing
    → `unchanged` counted, the mark advanced, and a second identical pull
    leaving the ledger byte-identical; with wellness disabled, a pending
    wellness record is still swept; `PullReport.failed` true for a wellness
    error or failed note and false for unchanged days alone.
  - **Mutations:** run wellness after an activity `AuthFailure`; ignore
    `instance.wellness` in `_runnable`; drop the look-back subtraction;
    ignore `--since`; let a failed note advance the mark; leave wellness out
    of `PullReport.failed`; keep the last occurrence of a repeated date
    (observable through `unchanged` versus `would_deliver` when the two
    occurrences carry different revisions).
  - **Observable:** `uv run pytest tests/connectors tests/test_agent_skill.py`
    green.
  - _Requirements: 2.2, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 5.6, 6.6, 9.5, 9.6, 10.5_
  - _Depends: 1.2, 2.1, 2.2, 2.4_

- [x] 3.2 Package changed days by year, check, deliver or hold, and record them
  - Per design § WellnessStep steps 6-9: yearly groups, package error
    mapping, the package check, held detection, delivery with the declared
    suffix, recording through the holder after every group, the
    attribution-change notice, the mark after a clean step, sorted report
    tuples.
  - **Tests** (appended to `tests/connectors/test_wellness_pull.py`): changed
    days across two years → two files with the design's names, two pending
    records, every day recorded with its file's sha; a second pull where one
    day's revision changed → one file holding that day alone; the first
    year's package raising `ValueError` → a failed note for its span, the
    second year delivered, the mark unchanged; `ConnectorError` from the
    first package → wellness error, no second package call; a package failing
    its check (`.fit`, invalid JSON, non-slug format) → failed note, nothing
    written; held because the bytes are archived (a real file at the wellness
    archive path) and because they equal a pending delivery → days recorded,
    span in `held`, no file written; `deliver` raising `OSError` → failed
    note, days unrecorded; `KeyboardInterrupt` from the second year's
    package → re-raised, and the saved ledger holds the first year's days and
    pending record; recorded origins `garmin, oura` and a package attributing
    only `oura` → one notice for `garmin`, not a failure, origins now `oura`;
    a held package leaves origins unchanged; a delivery left pending (the
    drain refused it) and an unchanged listing → nothing delivered again;
    failed and notice subjects sorted from an unsorted fixture.
  - **Mutations:** one file for all years; skip the held check; update
    origins on a held package; keep the ledger local to the step and assign it
    on return (the interrupt test reds); deliver without `suffix`; advance
    the mark despite a failed year; record days before `deliver` returns.
  - **Observable:** `uv run pytest tests/connectors` green.
  - _Requirements: 1.3, 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 5.6, 8.6, 9.5, 9.7, 10.6_
  - _Depends: 2.3, 3.1_

- [x] 3.3 Pull intervals.icu wellness through the engine
  - `run_pull` with the registered intervals.icu connector, `wellness =
    true`, and `FakeTransport` serving synthetic listing windows and an
    athlete object.
  - **Tests** (`tests/connectors/test_intervals_wellness_pull.py`): a first
    pull at a fixed `now` makes the window requests from 2009-12-31 plus one
    athlete request per delivered year and delivers files whose bytes equal
    `package_wellness`'s for the same days; after the test places each
    delivered file's bytes at its wellness archive path (standing in for the
    drain), a second pull removes them, makes one listing request (the
    look-back window) and no athlete request, and delivers nothing; a changed
    `updated` on one day in a later listing → one file with that day; a 403
    on the wellness listing → wellness error with the Garmin remedies while
    the same run's activity delivery stands; a 401 → wellness error with
    `fitdocs connect <name>`; the key and its Basic form appear in no report
    detail, ledger byte or delivered byte.
  - **Mutations:** skip the wellness half of the sweep (the removal reds);
    pass `oldest=through` without the look-back (the request window reds).
  - **Observable:** `uv run pytest tests/connectors` green.
  - _Requirements: 3.1, 3.2, 6.1, 7.2, 7.8, 9.1, 9.2, 9.6, 9.8, 13.4_
  - _Depends: 2.6, 3.2_

- [x] 4. The report and the agent surface

- [x] 4.1 Print the wellness table in the pull report
  - Per design § WellnessReportTable: `_WELLNESS_REPORT_ROWS`, the table and
    detail blocks in `_report_pull`, the `pull` command docstring.
  - **Tests** (`tests/connectors/test_cli_wellness.py`, `CliRunner`, a
    registered `ScriptedWellnessPuller` instance): the table titled
    `fitdocs pull: <name> wellness` with all eight rows at zero; counts from
    a run with one delivered file, one held span, one failure and one notice
    (distinct counts per row); the detail lines; a dry run's would-deliver
    dates; an instance without wellness prints no wellness table; exit 1 on a
    wellness failure, 0 with only notices and unchanged days.
  - **Mutations:** drop a row; print the table when `wellness is None`;
    count `listed` with `len`.
  - **Observable:** `uv run pytest tests/connectors/test_cli_wellness.py
    tests/connectors/test_cli_connectors.py` green.
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.7_
  - _Depends: 3.1_

- [x] 4.2 Document the wellness channels in the packaged skill and bind them
  - Per design § SkillWellnessTable: the paragraph and the `Wellness
    channel` table under `## Reading the report`; in
    `tests/test_agent_skill.py` (where 3.1 already added `wellness` to
    `_PULL_EXCLUSIONS`), `_WELLNESS_EXCLUSIONS`,
    `_WELLNESS_CHANNELS_LITERAL` (seven names), `_SkillProfile.wellness_channels`,
    and three tests mirroring the pull-table pins against
    `WellnessPullReport` and `_WELLNESS_REPORT_ROWS`.
  - **Mutations:** drop the `notices` row from the skill (the binding reds);
    rename a label (the label test reds); add a field to
    `WellnessPullReport` (the literal test reds).
  - **Observable:** `uv run pytest tests/test_agent_skill.py tests/test_cli_skill.py`
    green.
  - _Requirements: 12.5_

- [x] 5. Documentation and records

- [x] 5.1 Document the wellness pull in the connectors guide
  - Per design § ConnectorsDocs: the intro, the `wellness` row, the
    `lookback_days` and `--since` additions, `### Reading the wellness
    report`, the delivery-and-removal and ledger paragraphs, and `### Wellness`
    in the intervals.icu section before `### Garmin attribution`; re-pin
    `tests/connectors/test_docs.py`'s `_EXPECTED_HEADINGS`, its
    instance-table key pin (`:353-361`, now `== _RESERVED_KEYS`, which holds
    `_WELLNESS_KEY`), and `tests/connectors/test_intervals_docs.py:60-65`.
  - **Tests** (`tests/connectors/test_wellness_docs.py`): the wellness report
    table's rows equal `_WELLNESS_REPORT_ROWS`' labels; the `### Wellness`
    section states `WELLNESS_HISTORY_START.isoformat()`, `wellness = false`
    and a link to the wellness guide; the `wellness` row names its default;
    the NeutralScan stays green.
  - **Mutations:** change `WELLNESS_HISTORY_START` (the date pin reds); rename
    a report label (the table pin reds); delete the `wellness` row from the
    instance table (the key pin reds).
  - **Observable:** `uv run pytest tests/connectors/test_docs.py
    tests/connectors/test_intervals_docs.py tests/connectors/test_wellness_docs.py`
    green.
  - _Requirements: 12.1, 12.2_

- [x] 5.2 Advance the ownership contract for the pull's wellness deliveries (wiki-contract amendment)
  - Per design § ContractWording: the `pull` bullet of
    `docs/ownership-contract.md` names wellness files written under
    `<inbox>/<name>/`, their removal once `wellness-archive/` holds identical
    bytes, and `wellness-archive/*` and `wellness/*` in its never-writes
    list; `CONTRACT_VERSION` advances by one from the branch's value
    (controller ruling R1; 6.2 re-derives main + 1 after the final rebase)
    with the design's history paragraph adjacent to it; the doc's version
    line and its "What changed at this version" paragraph replaced; every
    declaration golden under `tests/declaration_golden/` regenerated; the
    literal pins `tests/index/test_contract_docs.py:140` and
    `tests/index/derived/test_preserved.py:246` moved; the head-paragraph
    phrase pin `tests/identity/test_contract_docs.py:177-187` (and any
    head-paragraph pin a peer has added on `main`; grep for the outgoing
    paragraph's phrases) re-pinned to wellness-pull's paragraph, the outgoing
    phrases moved into an assertion on the history docstring;
    `test_the_version_history_records_the_amendment`
    (`tests/identity/test_contract_docs.py:189-209`) gains, append-only, the
    literal assertion "Raised from ``N`` to ``N+1`` by wellness-pull" with
    the branch's numbers written as literals (6.2 rewrites them to the landed
    numbers; never computed from the live `CONTRACT_VERSION`, which would go
    red at a later spec's bump) and one literal sentence of design §
    ContractWording's paragraph; `## Amendment N` on
    `.kiro/specs/wiki-contract/requirements.md` (Requirement 2 criterion
    2.15 extended) with `spec.json`'s `updated_at`.
  - **Tests** (`tests/connectors/test_wellness_records.py`): the `pull`
    bullet names wellness files, `wellness-archive/` and `wellness/`; the
    "What changed at this version" paragraph names wellness-pull's change.
    The two literal history assertions above live in
    `tests/identity/test_contract_docs.py`. The version-following pins
    (`tests/test_ownership_contract.py:82-85`, `tests/test_declaration.py:98`)
    and the existing history assertions
    (`tests/identity/test_contract_docs.py:189-209`,
    `tests/compose/test_contract_docs.py:144-158`) stay green.
  - **Mutations:** delete the bullet's wellness clause (its pin reds); leave
    `CONTRACT_VERSION` at the base value (the literal pins and the doc head
    pin red); drop wellness-pull's paragraph from the history docstring (the
    appended literal history assertion reds).
  - **Observable:** `uv run pytest tests/connectors/test_wellness_records.py
    tests/identity tests/index/test_contract_docs.py
    tests/index/derived/test_preserved.py tests/test_declaration.py
    tests/test_declaration_goldens.py tests/test_ownership_contract.py`
    green; `/kiro-spec-status wiki-contract` clean.
  - _Requirements: 12.4, 12.7_
  - _Depends: 5.1_

- [x] 5.3 Update the wellness guide and the changelog, and record the connectors and intervals.icu amendments
  - Per design § WellnessDocs, ChangelogEntry, SpecRecords:
    `docs/wellness.md`'s getting-files-in passage linking
    `connectors.md#wellness` (the anchor 5.1 creates); the CHANGELOG entries,
    including the contract version change; `## Amendment N` in
    `.kiro/specs/connectors/requirements.md` and `## Amendment 1` in
    `.kiro/specs/intervals-connector/requirements.md`, each with
    `spec.json`'s `updated_at`.
  - **Tests** (appended to `tests/connectors/test_wellness_records.py`): the
    wellness guide links `connectors.md#wellness` and names `wellness = true`;
    both amendment headings exist and name wellness-pull; the CHANGELOG
    Unreleased section names the `wellness` key, the ledger format and the
    contract version change.
  - **Existing literal re-pin (canonical finding, 2026-10-15):** replace only
    the obsolete wellness-pull-planned topic value in
    `tests/wellness/test_docs_wellness.py::test_guide_topics` with the
    published intervals.icu pull sentence. Preserve every other parameter,
    helper and assertion; this is the existing guard for the guide passage
    this task changes, not a new wellness-store behavior or contract.
  - **Mutations:** delete an amendment heading; drop the guide's link (the
    records test reds; `tests/test_docs_guarantees.py:951-993` still resolves
    every remaining anchor).
  - **Observable:** `uv run pytest tests/connectors/test_wellness_records.py
    tests/test_docs_guarantees.py` green; `/kiro-spec-status connectors` and
    `intervals-connector` clean.
  - _Requirements: 12.3, 12.6, 12.7_
  - _Depends: 5.1, 5.2_

- [x] 6. Validation

- [x] 6.1 End to end through the drain, offline elsewhere, and confined
  - **E2E** (`tests/connectors/test_wellness_e2e.py`, `CliRunner`, the CLI's
    transport seam patched to a `FakeTransport`): `fitdocs pull intervals
    --sync --no-prompt` with `wellness = true` delivers a `wellness-*.json`,
    the chained drain archives it at
    `wellness-archive/intervals-icu/<sha>.json`, and `read_series` holds the
    synthetic values with origin `garmin`; a second `fitdocs pull` removes
    the delivery, delivers nothing, and the drain reports no series change.
  - **Offline**: `tests/connectors/test_e2e.py`'s `_fresh_synced_root`
    settings gain `[connectors.wellness-src]` (`connector = "intervals"`,
    `wellness = true`), and the shared test body sets that instance's key
    variable beside the existing one (`:349`); every offline command still
    makes no socket attempt. The parametrize rows are not edited; the test
    body is shared with `dashboards` 6.5 (index staging) and `recovery`, so a
    rebase keeps both sides.
  - **Confinement**: `WRITING_ENTRY_POINTS` appends `pull-wellness`
    (`run_pull` with a test-local wellness puller, no transport) whose
    non-vacuous check needs the ledger and a
    `data/inbox/<instance>/wellness-*.json`.
  - **Mutations:** skip the sweep's wellness half (the second pull's removal
    reds); make `_run_drain_passes` start a pull (the offline guard reds).
  - **Observable:** `uv run pytest tests/connectors tests/test_confinement.py`
    green.
  - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 6.2 Whole-suite gate, exhaustive sweep and rebase
  - Rebase onto `main`; keep both sides of every append-only list named
    above; re-derive `CONTRACT_VERSION` as main + 1 (the history paragraph's
    numbers, the doc's version line and "What changed" paragraph, every
    declaration golden including peers', the two literal pins, any
    head-paragraph pin a peer added, the literal numbers in this plan's
    history assertion in `tests/identity/test_contract_docs.py` (rewritten
    to the landed numbers, never made relative), the CHANGELOG entry's
    "from N to N+1" numbers and any records-test pin on them); re-derive
    the connectors and wiki-contract amendment numbers; re-run `uv run pytest
    && uv run ruff check . && uv run ruff format --check . && uv run mypy`;
    check branch CI with `gh run list --branch`.
  - Classify every acceptance criterion as PINNED (test and mutation),
    PRESERVED-ONLY or UNPINNED in Implementation Notes.
  - **Observable:** the suite, lint and types green after the final rebase;
    `CONTRACT_VERSION` equals main + 1; the sweep table complete;
    `/kiro-spec-status wellness-pull` clean.
  - _Requirements: 11.7, 12.4, 12.7, 13.2_

- [x] 6.3 Completion gate: reconcile the live check with the design
  - Reads `research.md` "Live check findings" (1.1 owns the record). For each
    TBC-W item marked contradicted: design.md amended at its marker and a
    numbered repair task (7.1, 7.2, …) appended with its own pins and named
    mutations, implemented and passing 6.2's gate before this task is
    ticked. TBC-W3 or TBC-W4 contradicted → the repair carries a
    `wellness-store` intervals-format amendment (`FIELD_METRICS`, revision
    normalization, `rules_version` + 1, `docs/wellness.md`'s table) recorded
    on `wellness-store`'s `requirements.md`. TBC-W1 contradicted → the
    repair covers `list_wellness`'s body and `id` checks and
    `_wellness_windows`, plus the same `wellness-store` amendment (its
    recognizer and parser read the `id` form too).
  - Then tick the roadmap's `wellness-pull` Specs line and the
    `intervals-connector` Existing Spec Update line. Tick the `connectors`
    line only if `recovery`'s half is on `main`. Tick the `wiki-contract`
    line only when all five Phase 12 wiki-contract halves are on `main`
    (`wellness-store`, `wellness-pull`, `hr-derivation`, `recovery` and
    `workout-wellness`). Otherwise annotate this spec's half as landed.
  - **Observable:** every contradicted item has an amended marker and a
    ticked repair task; the roadmap lines ticked or annotated; `spec.json`
    records completion.
  - _Requirements: 11.6, 11.7_
  - _Depends: 1.1, 6.2, 7.1_

- [x] 7. Live-check repairs required by 6.3

- [x] 7.1 Reconcile TBC-W5 platform namespaces and known wellness-download switches
  - Implements the 2026-10-15 TBC-W5 marker amendment and IntervalsWellness
    Packaging policy in design.md. `_wellness_origins` excludes both `icu`
    and `private` platform tokens, including prefixed aliases. Known switch
    mapping: garmin → `icu_garmin_download_wellness`, polar →
    `polar_download_wellness`, suunto → `suunto_download_wellness`, coros →
    `coros_download_wellness`, zepp → `zepp_download_wellness`, huawei →
    `huawei_download_wellness`. If present, only boolean True admits that
    platform's key lists; absent retains list-based compatibility. Unknown
    valid platform tokens stay list-based; do not invent suffix-based gates.
    `icu_garmin_health` never substitutes for the wellness switch. Filtering
    happens before claim cardinality; records remain opaque and byte-value
    preserving, and package metadata uses the resulting origins.
  - **Boundary:** production edits only `_wellness_origins` and local
    internal declarations in `src/fitdocs/connectors/intervals.py`. New tests
    in `tests/connectors/test_wellness_attribution.py`; existing
    `tests/connectors/test_intervals_wellness.py` changes only the old
    private-namespace expected-origin value to `{}`. Preserve all other
    parameters, helpers, assertions, protocol, activity operations, listing,
    packaging serialization, ledger and shared fixtures. Update the
    attribution passages of `docs/connectors.md` and `docs/wellness.md` to
    state the repaired policy, with visible passage pins in the new module.
    Parent owns the design/tasks amendments and all task-state changes.
  - **Tests:** actual public packaging path observes origin map and package
    origins independently for private/ICU aliases; each known switch and
    both key-list aliases; present True/False/None and non-boolean JSON
    families; absent-switch compatibility; independent Garmin health flag;
    non-platform and disabled-platform lists creating no ambiguity for an
    admitted real platform; enabled-platform collisions; unknown valid
    platform and invented switch ignored; original record values preserved.
    Test the changed old parameter at its own assertion and preserve the
    rest of its file. Keep synthetic records/dates and API_BASE addresses.
  - **Mutations:** admit private or ICU; ignore a known switch; swap two
    platform-switch bindings; accept truthy/non-boolean values; require an
    absent switch; use the health flag; filter only after cardinality; infer
    an unknown switch; alter records or leave stale package-origin metadata;
    remove a required visible policy passage. Every new/changed assertion
    incidence must fail its intended assertion under an applied fault and
    pass after exact restoration, with controls/equivalences explicit.
  - **Observable:** focused new attribution + unchanged intervals/listing/
    engine/integration/docs tests green; configured mypy/Ruff/diff checks
    green; fresh independent review and parent verification. Then rerun
    6.2's complete gate and update the 8.1/11.6/11.7 coverage record before
    6.3 is ticked. No wellness-store format amendment is needed because
    TBC-W1/W3/W4 were confirmed, not contradicted.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 11.6, 11.7, 12.1, 12.2, 12.3_
  - _Depends: 1.1, 6.2_

## Implementation Notes

- **Planning record (2026-10-12).** Independent Step 3.5 task-graph review,
  dispatched by the Phase 12 batch controller: round 1 NEEDS_FIXES (one
  critical, three important, six minor findings, all applied), round 2
  three further items applied, then finalized. Controller rulings: R1
  `CONTRACT_VERSION` advances main + 1 at landing (design Decision 13
  reversed; owned by 5.2, re-derived by 6.2); R2 no task of group 5 is
  `(P)`, and the task carrying the `connectors.md#wellness` anchor link
  (5.3) depends on 5.1; R3 the roadmap ticks belong to 6.3.

- **1.1 (2026-10-14).** Controller read-only live check independently APPROVED; TBC-W1/W2/W3/W4/W6/W7/W8 confirmed with stated observation limits. TBC-W5 contradicts generic upstream attribution (private namespace), recorded for 6.3 numbered repair; key and payload never persisted.

- **1.2 (2026-10-14).** READY_FOR_REVIEW → independently APPROVED round 2 → VERIFIED. Full suite 14,768 passed / 44 skipped; mypy 551 files, Ruff lint/format clean; final parent CLI+protocol 135 passed. Reviewer reproduced 35 original + 51 helper claims and five own mutations, all red and restored green. The initial surviving fixture-recording mutation is now caught. Shared `ScriptedWellnessPuller` is frozen: `capabilities=` defaults to wellness-only; override both capabilities for activity/wellness order or raised-activity tests (empty override is respected). Use `wellness_listing_script`, `wellness_package_script`, `wellness_list_calls`, `wellness_package_calls`, `calls`, `parse_settings_tables` and `parse_settings_calls`, plus inherited activity scripts/call arguments. Exact opaque-record identity and default/default_factory absence are pinned. No follow-ups.

- **2.1 (2026-10-14).** READY_FOR_REVIEW → independently APPROVED round 3 → VERIFIED. Full suite 14,827 passed / 44 skipped, mypy 552 and Ruff clean; fresh parent focused 106 passed. Reviewer replayed 51 claimed + four own mutations, zero survivors. Validation order is lookback → wellness → credential key, with strict-bool explanation before capability failure; explicit False/True keys are stripped. A 42-row value/capability matrix pins projection, parser residual table and precise errors across seven registry-valid capability representatives, including both driven capabilities. Registry requires nonempty capabilities; helper empty override is outside registered settings input domain. Runtime source was correct throughout two test-only remediations; no follow-ups.

- **2.2 (2026-10-14).** READY_FOR_REVIEW → independently APPROVED round 2 → VERIFIED. Full suite 15,009 passed / 44 skipped, mypy 553 and Ruff clean; fresh parent focused 255 passed and exact tested hashes matched. Reviewer reproduced 243 claims (240 RED plus three equivalent GREEN) and 15 fresh mutants RED, zero behavioral survivors. Activity-only literal bytes remain version 1; wellness saves version 2, latest reader is 2. Helpers normalize unsorted input; direct unsorted tuples are refused. Three defensive serializer sort deletions remain explicitly UNPINNED equivalent operations because invariants already require sorted values. Distinct day hashes and pending format/suffix pairs, independent literal SAVE/HAND-AUTHORED LOAD controls, and pre-call whole-input deep snapshots close the two bounded fixture families without changing production. Copy methods preserve both keyspaces; forget uses latest delivery SHA and lowers only to the earliest lost day minus one. No follow-ups.

- **2.3 (2026-10-14).** READY_FOR_REVIEW → independently APPROVED round 2 → VERIFIED. Full suite 15,107 passed / 44 skipped, mypy 554 and Ruff clean; fresh parent focused 138 passed and exact full-tested hashes matched. Reviewer reproduced all 109 claim applications and four fresh variants RED/restored GREEN, zero survivors. Declared-suffix JSON delivery preserves the unchanged 40 FIT tests, ownership, bytes and atomic writes. Positive slug roles and JSON type/falsey partitions now discriminate all ten first-review survivors; negative rows and a literal regex pin alone do not prove acceptance. Ordinary frozenset first-valid/later-invalid reachability is checked at four hash seeds. On macOS .JSON/.json paths alias: exact layout arguments pin verbatim forwarding separately from real .csv file behavior. WellnessSweep remains 2.4 and engine orchestration remains 3.2; no follow-ups.

- **2.4 (2026-10-14).** READY_FOR_REVIEW → independently APPROVED round 2 → VERIFIED. Full suite 15,152 passed / 44 skipped; configured mypy 554 and Ruff lint/format 739 clean; fresh parent 183 passed and exact reviewed hashes matched. Reviewer replayed all 69 mutation claims and four fresh defects RED/restored GREEN, all six scoped requirements PINNED. Five sweep outcomes accumulate against current ledger while iterating original path order; read/unlink failures retain pending and continue. Real JSON payloads with unequal full SHA256 but shared prefix 684793b8 now pin full-digest comparison; independent input snapshots and safe file observations preserve existing distinctions. Original activity loop and prior test bytes unchanged. No follow-ups.

- **2.5 (2026-10-14).** READY_FOR_REVIEW → independently APPROVED round 3 → VERIFIED. Full suite 15,299 passed / 44 skipped; configured mypy 555 and Ruff lint/format 740 clean; fresh parent focused 251 passed and exact reviewed hashes matched. Reviewer reproduced 66 variants / 117 intended RED applications, six fresh variants RED/restored GREEN, and 1,254 independent valid-domain probes; all twelve scoped contributions PINNED. Two test-only repairs closed a field-insensitive credential double and numeric/falsey plus body/entry/ID JSON type families. Real API-key-only credentials, all fifty appended observations and retained earlier tests discriminate their intended faults. Existing connector class/settings/activity/verify/fetch/capabilities remain unchanged; source stayed byte-identical after first implementation. Six unused packaging/attribution declarations remain explicitly deferred to 2.6, and the optional 401 None guard is behavior-equivalent for the real helper. No follow-ups.

- **2.6 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 3 → VERIFIED. Full suite 15,879 passed / 44 skipped; configured mypy 555 and Ruff lint/format 740 clean; fresh parent focused 831 passed with exact reviewed hashes. Reviewer reproduced 163 claim/history applications (162 behavioral RED plus one declared canonical-ID reconstruction equivalence GREEN), three fresh faults RED/restored GREEN and an independent 880-observation actual-listing sweep; all eleven scoped contributions PINNED. Settings-only envelope and carrier metadata are observed independently for absent fields and empty selections. Immutable canonical snapshots distinguish native JSON values, numeric aliases and signed zero through output and caller-owned input, including the complete updated field family. Two test-only remediations preserve the original source and all earlier cases; current 727 wellness observations plus 104 activity cases pass. Packaging makes one athlete-settings GET, preserves listed records verbatim and emits the format-consumer canonical envelope. TBC-W5 original private-namespace attribution semantics remain assigned to 6.3 numbered repair; no new follow-ups.

- **3.1 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 3 → VERIFIED. Full suite 17,678 passed / 44 skipped; configured mypy 556 and Ruff lint/format 741 clean; fresh parent focused 2,081 passed with exact six reviewed hashes. Reviewer independently reproduced 198 applications / 7,142 intended assertion failures, all 70 assertion sites, all 1,395 first-repair and 166 second-repair behavioral nodes, plus two fresh sole-failure faults with GREEN controls/restoration. All seventeen scoped contributions PINNED. One DATA session serves driven capabilities in declaration order; all AuthFailure kinds/subclasses at either activity site suppress wellness, ordinary failures continue it. Listing validation, exact opaque revisions, native count types, configured lookback 0..3650, UTC since, singleton coverage, dry-run bytes/mtime, disabled pending sweep and current-holder interruption saving are pinned. Existing activity AST and old tests are preserved except prescribed re-pins. **Authorized interim for 3.2:** changed non-dry days stay unrecorded and coverage does not advance; 3.2 must first retire `test_interim_changed_nondry_keeps_seeded_mark`, then implement year packaging/delivery and real interrupted-group saving. Every other existing case/control remains preserved. No new follow-ups.

- **3.2 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 2 → VERIFIED. Final canonical 18,376 passed / 44 skipped; configured mypy 556 and Ruff lint/format 741 clean; fresh parent focused 2,779 passed with exact reviewed source/test hashes. Reviewer independently reproduced 95 claimed applications (838 owning AssertionErrors), all 699 parameter nodes / 18 assertion sites, and two fresh sole-failure faults; parent raw audit confirmed 97 total applications / 840 intended failures, no helper errors and all restored selections GREEN. All twelve scoped engine requirements and completion partials 3.4/3.7/3.9 PINNED; reused atomic/candidate/validator/sweep primitives preserved. Calendar-year packaging forwards original opaque days/session, checks declared package metadata, holds full-SHA archived/current-pending bytes, delivers by declared suffix and records only after success. Immediate holder updates preserve delivered and held work across later terminal errors/interruption; held groups never change origins/notices. Actual deliveries update origins and emit redacted loss notices; clean steps alone advance coverage. Native NotConnectedError and valid custom ConnectorError subtype first/later cases close the independently found exact-class classifier gap; adjacent coverage makes single terminal-error guard deletion observable. Prior 1,798 cases and old source helpers/activity AST preserved; exactly the approved interim test retired. Two redundant downstream sorting deletions are honest equivalent GREEN. No new follow-ups.

- **3.3 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 1 → VERIFIED. Final canonical 18,397 passed / 44 skipped; configured mypy 557 and Ruff lint/format 742 clean; fresh parent focused 3,245 passed with all seven approved hashes exact. Reviewer independently reproduced 33 claimed faults / 55 owning AssertionErrors and four fresh faults / six owning failures; parent raw XML audit confirmed all 37 applications / 61 failures at the two owning assertions, zero helper errors, exact restorations and GREEN. All 21 collected nodes covered. Registered Intervals integration pins twelve synthetic historical windows, UTC day boundaries, two yearly packages with independent envelope expectations, actual archive/sweep cleanup, eleven-day lookback, updated-only singleton revision delivery, 401/403 dedicated errors after genuine FIT delivery and report/package/ledger credential containment. Eight current requirement contributions PINNED; 9.6 activity failure gates and 13.4 socket/environment isolation remain explicitly PRESERVED-ONLY through named existing regressions (102 activity cases, isolation control and fourteen date/window primitives verified in final JUnit). All production, prior tests and shared fixtures unchanged. No new follow-ups.

- **4.1 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 3 → VERIFIED. Final canonical 18,412 passed / 44 skipped; configured mypy 558 and Ruff lint/format 743 clean; fresh parent focused 209 passed with exact reviewed hashes. Reviewer independently replayed all 111 claimed applications / 144 owning output failures plus two fresh sole-failure programs, all restored GREEN; parent raw XML audit confirmed 113 programs / 146 intended failures across all 15 nodes / 12 assertion sites. All six scoped CLI criteria (10.1/10.2/10.3/10.4/10.5/10.7) PINNED, with reused engine primitives explicitly PRESERVED-ONLY. Eight-row per-instance wellness table follows activity details, prints zero counts and literal detail/date/span text, preserves instance-level sweep channels and failure exit semantics, and is absent for disabled/activity-only instances. Complete six-dynamic-site × three-formatting-flag sweep closed two bounded test-only date/held wrapping gaps; production stayed correct and unchanged after initial implementation. Rich width tests must set both width and height and observe actual width; width-only fixture controls are separate from production output evidence. Canonical ISO date/span markup changes remain honest equivalences. Old activity AST/tests, historical test prefixes and all literal values preserved; all owned processes exited. No new follow-ups.

- **4.2 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED → VERIFIED. Packaged skill documents seven wellness channels after the activity table and states row-specific athlete/export and printed-next-step/configuration guidance. Independent reviewer reproduced all 168 claims and seven fresh faults, each sole owning AssertionError followed by exact restoration and GREEN: 170 production/documentation faults and five explicitly separate fixture controls, all ten new nodes / eleven assertion sites. Requirement 12.5 and all seven scoped design components PINNED; existing pull/drain/other-skill regressions PRESERVED-ONLY. Final canonical before prose cleanup: 18,422 passed / 44 skipped; mypy 558 and Ruff lint/format 743 clean. A multiplicity-preserving pair comparison closes a duplicate-CLI-row blind spot; all 63 pairwise document-label/document-field/CLI-label swaps discriminate. Two stale pre-existing exclusion descriptions were corrected from three to four after canonical. Separate independent review verified that exact prose-only delta, all 251 assertion ASTs and all executable code unchanged, and a complete assertion line map; fresh focused 123 and statics passed on current bytes, followed by fresh parent 123. Parent raw XML audit confirmed all 175 failures/restorations, including the one-line shift from omitted-profile fixture control. Original full/mutation receipts keep their original hashes; only identical code claims transfer. All owned processes exited; stale-comment follow-up resolved without queue work. No remaining follow-ups.

- **5.1 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 3 → VERIFIED. Guide covers optional wellness, configuration and rechecks/backfill, all eight report rows with correct day/file units, yearly delivery/cleanup/ledger versioning, and intervals.icu provenance, freshness, Garmin/export and retention limits. Existing activity text and address/NeutralScan controls remain preserved; guide link uses the already-admitted own-project URL. Two bounded test-only repairs replaced raw scanners with existing MarkdownIt tokens for visible heading ancestry, prose/table cells, configuration roles and actual --since list-item ownership. All required 12.1/12.2 contributions PINNED; 49 unchanged focused regressions PRESERVED-ONLY; seven extra explanatory clauses honestly UNPINNED, each removed/restored with all 82 focused cases GREEN. Fresh reviewer reproduced all 474 current-byte pairs: 419 own AssertionError executions (414 distinct byte/owner operations) and 55 valid controls, plus eight fresh faults RED and two fresh controls GREEN; all restorations GREEN. Parent raw XML confirmed 427 intended failures / 57 controls, all 33 changed nodes/eight sites plus one unchanged regression separately. Nineteen former syntax faults are actual GFM required-table equivalents, independently verified, not missing semantic coverage. Final canonical 18,452 passed / 44 skipped; mypy 559 and Ruff lint/format 744 clean; fresh parent 82 with exact eight reviewed hashes. Annotation-only provenance (22 identical compiled code objects), expectation AST/26 IDs, duplicate mapping and separate 97-pair subset independently verified; all claims nevertheless freshly replayed on current bytes. All 986 reviewer processes exited. TBC-W5 remains explicitly owned by 6.3 numbered repair. No new follow-ups.

- **5.2 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED → VERIFIED. Contract 11→12 with literal appended history and current ownership guarantees for inbox wellness delivery, identical-byte archive cleanup and never-written archive/series. All seven declaration goldens change only their version line; prior activity/credential/connect/chained-operation guarantees and history preserved. Reviewer replayed all 61 claimed operators plus five fresh faults and one valid control: 134 pytest executions, 340 selected cases, 116 intended owning AssertionErrors, eight GREEN applied controls, every restore GREEN; parent raw XML/hash audit confirmed ten assertion sites and all fifteen hashes. Final canonical 18,460 passed / 44 skipped; mypy 560, Ruff lint/format 745 and whitespace clean; fresh parent focused 507 passed. New 12.4 wording/version/head/history guards PINNED, prior guarantees PRESERVED-ONLY. Wiki-contract Amendment 7, criterion 2.15 extension and timestamp manually verified and explicitly UNPINNED automatically by three surviving record controls; all approvals and 17/17 upstream task state preserved. Connectors/intervals amendments remain 5.3; landing-time version/amendment re-derivation remains 6.2. All owned processes exited. No new follow-ups.

- **5.3 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 3 → VERIFIED. Wellness intake links the actual connector guide and enabled pull command; Unreleased records pull/key/attribution/report, conditional ledger format 2, older-reader refusal, user action and contract 11→12. Connectors Amendment 4 and intervals-connector Amendment 1 preserve prior records; metadata changes only updated_at. Two bounded repairs close escaped literal-link false positives (actual href required in the matched visible paragraph) and migrate exactly one obsolete planned-pull topic literal in the existing wellness guide guard; all other parameter/helper/assertion AST and the 5.2 prefix preserved. Fresh reviewer replayed all 126 current claims plus seven new faults and two valid controls: 135 pairs/270 pytest runs, 233 intended owning AssertionErrors, sixteen valid GREEN controls and four declared manual-governance GREEN controls, every restoration GREEN. Parent raw XML/hash audit confirmed all twelve changed nodes/four sites and eight hashes. Finite audit: 23 PINNED, three PRESERVED-ONLY, four automatic UNPINNED mapping/timestamp units manually verified. Canonical 18,471 passed / 44 skipped; configured mypy 560, Ruff lint/format 745 and whitespace clean; fresh parent focused 245 passed. All 278 review processes exited. Landing-number re-derivation remains 6.2; TBC-W5 remains 6.3 numbered repair. No new follow-ups.

- **6.1 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED → VERIFIED. Real registered intervals CLI pull chains the actual drain, archives canonical synthetic wellness bytes, reads six distinct source/origin-attributed values, then removes its delivery on a second pull with no new delivery or series/archive byte or mtime change. Offline fixture adds wellness-src and its key while all ten command rows and the remaining shared body stay exact. New pull-wellness confinement entry requires both own ledger and direct own-instance wellness JSON; all eighteen previous entries and 115 old confinement definitions preserved. Reviewer reproduced all 56 credited sole-assertion faults and six fresh source faults, exact-restored GREEN; parent audited 65 pairs/130 raw executions, 62 intended assertion failures and three honest GREEN controls across 22 nodes, with exact applied-source hashes and identical Assert AST maps covering all fifteen new sites. All eight predicate and both snapshot-row incidences covered. Earlier activity-confounded offline probes are superseded; final wellness-only real-CLI faults and separate disabled-wellness/missing-key calibrations prove the new settings and key load-bearing. 13.1 PINNED; 13.2 PRESERVED-ONLY; 13.3/13.4 new workflow contributions PINNED and broader guarantees PRESERVED-ONLY. A refused-drain 9.7 scenario is explicitly UNPINNED by this new successful-drain test and covered by named pre-existing pending/held retry regressions. Broad 4,795 passed; final canonical 18,483 passed / 44 skipped, all twelve new nodes and six named preserved regressions passed; mypy 561, Ruff lint/format 746 and whitespace clean; fresh parent focused 84 passed. All 253 source/dependency/shared-fixture files unchanged; all 138 review PIDs exited. Parent also corrected the already-completed group-4 heading. No new follow-ups.

- **6.2 (2026-10-15).** Nonbehavioral whole-feature audit, ready for independent review; no repository source/test/assertion changes and no new feature flag or mutation campaign. Parent completed the authorized final fetch/rebase onto main; current HEAD `7df73fe5ea60b8d75b8a07034f2bf62c0c0d6312`, main and origin/main `6cac16d8763348b132fa6f9450c2e014fbc5ae2b`. Main is an ancestor; no rewrite or numeric re-edit needed. Contract main11→branch12; DOC_VERSION9 and schema3 unchanged. Seven declaration goldens differ only in the literal contract-version line. Identity current-head phrases, outgoing wellness-store history, literal 11→12 assertion, both index literal pins, CHANGELOG numbers, records pins and wiki Amendment7 literal numbers agree. Connectors Amendment4, wiki7 and intervals1 are next free against current main; prior amendments/names/confinement entries/offline rows preserved. `numeric-audit.json` retains exact comparisons and current hashes.

Fresh configured mypy passes (561 files); Ruff lint and format pass (746 files), whitespace clean; 144 focused version/history/declaration/records/dependency tests pass (`focused.xml`). Exact-head CI run [38781910921](https://github.com/joshua-stauffer/fitdocs/actions/runs/38781910921) completed SUCCESS; raw `ci.json` records SHA/workflow/status/conclusion. CI triggers every push/PR; no workflow write/retrigger used. No second implementer full suite: the fresh independent reviewer runs the one canonical post-audit suite. Prior actual canonical XML independently parses 18,527 cases:18,483 passed+44 optional-tooling skips, no failures/errors; 6.1 final reviewed hashes match current files. Prior canonical result is historical evidence, not the new review run.

All 91 source acceptance criteria are classified below. Detailed exact node lists, transformations, scopes and receipt paths: [acceptance-matrix.json](/private/tmp/wellness-pull-task6.2-implement/acceptance-matrix.json), [acceptance-matrix.md](/private/tmp/wellness-pull-task6.2-implement/acceptance-matrix.md). 116 selected existing receipt records inspected; 61 actual XML and40 raw log artifacts independently reparsed, with SHA256s in [selected-raw-receipt-audit.json](/private/tmp/wellness-pull-task6.2-implement/selected-raw-receipt-audit.json). This audit did not apply or replay those historical faults. Some early records retain actual pytest exits/nodes in their raw receipt rather than an accessible separate XML; this provenance limitation is explicit. 80 cited historical test-function ASTs match exact task commits;50 whole test files match, with later append-only changes distinguished. `historical-test-provenance.json` and `provenance.json` preserve commits/hashes and limits; no earlier full-file hash is claimed unchanged after later additions. All named tests actually passed in the last canonical XML (`canonical-row-incidence.json`).

Explicit limits: 8.1/TBC-W5 is pending the already-scheduled 6.3 reconciliation (private/nonplatform namespaces and known download switches); current tests deliberately pin the original private→private behavior and do not establish repaired semantics. 11.6/11.7 remain manual/pending final reconciliation, with a numbered7.x repair and rerun of6.2 required before6.3 ticks. 11.1–11.5 and13.5 use existing shapes-only controller research and manual task/provenance inspection; this subagent read no environment file/key and made no service request. This is task-level review readiness, not feature GO. Metadata phase/tasks/approvals stay untouched:17/19 feature leaves complete;6.2/6.3 pending. Upstream connectors27/27, intervals13/13, wiki17/17 preserve approvals. Allowed connector imports contain no wellness import/direct clock call; pyproject.toml/uv.lock unchanged from main. Downstream recovery/workout-wellness attribution needs revalidation after6.3; a later main change requires landing-number refresh.

Declared unpinning is bounded in [declared-unpinned-controls.json](/private/tmp/wellness-pull-task6.2-implement/declared-unpinned-controls.json): three equivalent ledger serializer sorts; two redundant engine sorts; seven optional guide explanations (mandatory12.1/12.2 visible guards remain pinned); detailed amendment mappings/timestamps/wiki governance controls (manual current-state correctness verified in numeric/status audits); and refused-drain9.7 scenario surviving the new successful-drain E2E while named pending/retry/held regressions remain PRESERVED-ONLY. These are existing declared limits, not new blockers. No new assertion in6.2: assertion discrimination N/A; no unsupported new test prose.

Receipt aliases below name actual applied-fault execution records; complete mutation text/selected node/RED/restored-GREEN details are in the linked receipt and selected raw audit. The compact table gives a representative existing test/fault; exhaustive per-clause scope and additional regressions remain in the detailed matrix.
- R1: [wellness-pull-task1.2-round2-review-claimed.log](/private/tmp/wellness-pull-task1.2-round2-review-claimed.log)
- R2: [mutation-results.json](/private/tmp/wellness-pull-task3.1-round3-review-replay/original-replay/mutation-results.json)
- R3: [replay-results.json](/private/tmp/wellness-pull-task3.2-round2-review/replay-results.json)
- R4: [wellness-pull-task2.1-round3-review-replay.log](/private/tmp/wellness-pull-task2.1-round3-review-replay.log)
- R5: [mutation-results.json](/private/tmp/wellness-pull-task3.1-round3-review-replay/new-family-gate/mutation-results.json)
- R6: [results.json](/private/tmp/wellness-pull-task2.5-review-replay/final-mutations/results.json)
- R7: [wellness-pull-task2.3-round2-review-replay-mutations.json](/private/tmp/wellness-pull-task2.3-round2-review-replay-mutations.json)
- R8: [wellness-pull-task2.2-round2-review-replay243.json](/private/tmp/wellness-pull-task2.2-round2-review-replay243.json)
- R9: [wellness-pull-task2.4-round2-review-replay-mutations.json](/private/tmp/wellness-pull-task2.4-round2-review-replay-mutations.json)
- R10: [inventories-results.json](/private/tmp/wellness-pull-task2.6-round3-review-replay/inventories-results.json)
- R11: [mutation-summary.json](/private/tmp/wellness-pull-task4.1-round3-review/mutation-summary.json)
- R12: [claimed474-independent-XML-audit.json](/private/tmp/wellness-pull-task5.1-round3-review/claimed474-independent-XML-audit.json)
- R13: [replay-receipts.json](/private/tmp/wellness-pull-task5.3-round3-review/replay-receipts.json)
- R14: [replay-results.json](/private/tmp/wellness-pull-task5.2-round1-review/replay-results.json)
- R15: [results.json](/private/tmp/wellness-pull-task4.2-round1-review/results.json)
- R16: [replay-results.json](/private/tmp/wellness-pull-task6.1-round1-review/replay-results.json)

| Criterion | Classification | Existing test / actual historical fault receipt |
|---|---|---|
| 1.1 | PINNED | `test_only_activity_and_wellness_pulls_are_driven`; `test_other_seven_capabilities_remain_reserved_without_operations`; `test_runnable_matrix`; R1 `## 1. wellness descriptor remains undriven` |
| 1.2 | PINNED | `test_wellness_value_fields`; `test_wellness_operations_receive_only_session_and_selection`; R1 `## 3. WellnessDay field annotation wrong` |
| 1.3 | PINNED | `test_packaging_opaque_record_domain`; `test_packaging_years`; R3 `replace-record` |
| 1.4 | PINNED | `test_registration_refuses_either_missing_wellness_operation`; `test_registration_accepts_both_wellness_operations_without_calling_them`; R1 `## 16. wellness registry block skipped` |
| 1.5 | PINNED | `test_day_preserves_absent_revision_and_omits_record_from_repr`; `test_diff_sort_missing_and_none`; R1 `## 12. record exposed in repr` |
| 1.6 | PINNED interface; boundary PRESERVED-ONLY | `test_wellness_operations_receive_only_session_and_selection`; `test_record_domain_is_opaque`; `test_packaging_opaque_record_domain`; `test_wellness_report_type_contract`; R1 `## 14. listing accepts wrong oldest type` |
| 1.7 | PINNED | `test_import_fitdocs_connectors_exposes_exactly_50_names`; `test_every_published_name_is_identical_to_its_defining_modules_object`; R1 `## 28. published wellness name omitted` |
| 2.1 | PINNED | `test_wellness_boolean_and_default`; `test_direct_instance_defaults_wellness_to_false`; `test_wellness_value_capability_matrix`; R4 `=== M01 absent default ===` |
| 2.2 | PINNED | `test_disabled_activity_only_bytes`; `test_pending_sweep_even_when_disabled`; R2 `drop_enable_setting` |
| 2.3 | PINNED | `test_pull_rejects_wellness_before_transport_or_writes`; `test_malformed_wellness_capability_matrix`; `test_non_boolean_wellness_is_rejected`; R4 `=== M19 early transport ===` |
| 2.4 | PINNED | `test_framework_strips_wellness_before_connector_parser`; `test_wellness_value_capability_matrix`; R4 `=== M05 reserved key ===` |
| 2.5 | PRESERVED-ONLY | `test_declaration_matches_design`; `test_folder_mixed_source_lists_only_fit` |
| 2.6 | PINNED | `test_runnable_matrix`; `test_round2_all_registered_capability_roles`; R2 `disable_wellness_capability` |
| 3.1 | PINNED | `test_oldest_precedence`; `test_round3_date_window_roles`; R2 `skip_since_override` |
| 3.2 | PINNED | `test_oldest_precedence`; `test_default_first_request_widens_history_start`; R2 `skip_since_override` |
| 3.3 | PINNED | `test_oldest_precedence`; `test_round3_date_window_roles`; R2 `skip_since_override` |
| 3.4 | PINNED | `test_round2_exact_revision_identity`; `test_diff_sort_missing_and_none`; `test_packaging_revision_retry`; R2 `listed_wrong` |
| 3.5 | PINNED | `test_diff_sort_missing_and_none`; `test_omitted_day_keeps_deliveries_and_archive`; `test_packaging_revision_retry`; R2 `listed_wrong` |
| 3.6 | PINNED | `test_bad_revision_failure`; `test_bad_day_date`; `test_duplicate_keeps_first`; `test_invalid_first_duplicate_stays_unrecorded`; R2 `disable_wellness_capability` |
| 3.7 | PINNED | `test_clean_coverage_and_identical_second_pull`; `test_empty_first_pull_persists_wellness_coverage`; `test_packaging_coverage`; R2 `unchanged_count_wrong` |
| 3.8 | PINNED | `test_dry_run_preserves_pending_bytes_and_mtime`; `test_packaging_years`; R2 `dry_sweeps` |
| 3.9 | PINNED | `test_packaging_revision_retry`; `test_clean_coverage_and_identical_second_pull`; R3 `alter-bytes` |
| 3.10 | PINNED | `test_omitted_day_keeps_deliveries_and_archive`; R2 `coverage_drops_old_days` |
| 4.1 | PINNED | `test_packaging_years`; R3 `one-year` |
| 4.2 | PINNED | `test_json_atomic_write`; `test_packaging_years`; R7 `atomic-prefix-forwarding` |
| 4.3 | PINNED | `test_json_collision`; `test_packaging_occupied_names`; R7 `candidates-literal-fit` |
| 4.4 | PINNED | `test_json_refusal`; `test_json_size_bound`; `test_format_refusal`; `test_suffix_refusal`; `test_packaging_refusals`; R7 `skip-json-parse` |
| 4.5 | PRESERVED-ONLY | `test_non_fit_bytes_are_skipped_and_not_delivered` |
| 4.6 | PINNED | `test_packaging_held_roles`; R3 `alter-bytes` |
| 4.7 | PINNED | `test_packaging_failures`; `test_packaging_delivery_oserror`; R3 `alter-bytes` |
| 5.1 | PINNED | `test_save_mixed_wellness_has_literal_data`; `test_load_hand_authored_mixed_wellness`; `test_packaging_years`; R8 `writer_day_hash_from_first` |
| 5.2 | PINNED observable order; equivalent sorts UNPINNED | `test_wellness_roundtrip_stable_order_and_omission`; `test_save_mixed_wellness_has_literal_data`; R8 `writer_always_1` |
| 5.3 | PINNED | `test_activity_only_literal_golden`; R8 `activity_constant` |
| 5.4 | PINNED | `test_version_constants_and_trailing_wellness_default`; `test_wellness_roundtrip_stable_order_and_omission`; `test_invalid_version_refused_naming_file_without_writes`; R8 `reader_constant` |
| 5.5 | PINNED | `test_invalid_wellness_refused_on_load_and_save_without_writes`; `test_invalid_version_refused_naming_file_without_writes`; `test_wellness_container_shapes_refused`; R8 `invariant_through` |
| 5.6 | PINNED | `test_packaging_interruption`; `test_packaging_failures`; `test_interruption_saves_current_holder`; `test_packaging_held_partial_exit`; R3 `alter-bytes` |
| 5.7 | PINNED | `test_invalid_wellness_refused_on_load_and_save_without_writes`; `test_save_mixed_wellness_has_literal_data`; R8 `invariant_through` |
| 6.1 | PINNED | `test_sweep_mixed_state`; `test_sweep_mixed_files`; `test_sweep_changed_file_with_matching_hash_prefix`; R9 `original-old-fit-archive` |
| 6.2 | PINNED | `test_sweep_mixed_files`; `test_sweep_changed_file_with_matching_hash_prefix`; R9 `original-remove-hash-diff` |
| 6.3 | PINNED | `test_sweep_forget_mark`; `test_sweep_mixed_state`; `test_forget_uses_latest_sha_and_lowers_before_earliest_dropped_day`; R9 `original-retain-mark` |
| 6.4 | PINNED | `test_sweep_mixed_state`; `test_sweep_mixed_files`; R9 `original-old-fit-archive` |
| 6.5 | PINNED | `test_sweep_failure_state`; `test_sweep_failure_files`; R9 `original-mutate-input` |
| 6.6 | PINNED | `test_pending_sweep_even_when_disabled`; R2 `sweep_disabled_skipped` |
| 7.1 | PINNED | `test_packaging_capabilities_are_exact`; R10 `inventories-010-replay-016-extra-capability` |
| 7.2 | PINNED | `test_one_get_per_window_and_exact_path_query`; `test_no_window_exceeds_366_days`; `test_earlier_window_duplicate_wins`; `test_nonempty_text_updated_preserved_exactly`; `test_now_is_converted_to_utc`; R6 `one-window-only` |
| 7.3 | PINNED | `test_default_logical_coverage`; `test_default_first_request_widens_history_start`; R6 `wrong-logical-default` |
| 7.4 | PINNED | `test_nontext_or_empty_updated_uses_whole_content_hash`; `test_content_revision_changes_with_arbitrary_field`; `test_absent_updated_uses_content_hash`; R6 `updated-not-string` |
| 7.5 | PINNED | `test_malformed_body_refused`; `test_malformed_entry_names_window_relative_index`; `test_json_id_type_errors_are_exact`; R6 `malformed-json-message` |
| 7.6 | PINNED | `test_only_id_and_updated_are_read_and_object_is_retained`; `test_listed_package_preserves_json_types_by_field_and_role`; R6 `opaque-copied` |
| 7.7 | PINNED | `test_package_golden_and_metadata`; `test_real_wellness_parser_reads_package`; `test_package_bytes_do_not_depend_on_clock_or_machine`; R10 `inventories-013-replay-019-keys-unsorted` |
| 7.8 | PINNED | `test_one_get_per_window_and_exact_path_query`; `test_athlete_request_contract`; R6 `one-window-only` |
| 8.1 | UNPINNED (pending 6.3); original algorithm partial PINNED | `test_settings_claim_cardinality_and_platform_names`; `test_only_list_setting_values_create_claims`; R10 `inventories-035-replay-042-accept-ambiguous-platform` |
| 8.2 | PINNED | `test_settings_claim_cardinality_and_platform_names`; `test_package_omits_empty_origins`; R10 `inventories-035-replay-042-accept-ambiguous-platform` |
| 8.3 | PINNED | `test_invalid_platform_names_make_no_claim`; `test_settings_claim_cardinality_and_platform_names`; R10 `inventories-042-replay-049-name-agnostic-matcher` |
| 8.4 | PINNED | `test_attribution_uses_settings_without_metric_value_filter`; `test_listed_package_attribution_has_independent_envelope_and_metadata`; R10 `inventories-053-replay-060-filter-origins-by-record-presence` |
| 8.5 | PINNED | `test_listed_package_preserves_json_types_by_field_and_role`; `test_package_retains_every_record_value`; R10 `inventories-110-prior-repair-exact-own04-at-existing-false-and-actual-listed-field` |
| 8.6 | PINNED | `test_packaging_origins`; R3 `wrong-origins` |
| 9.1 | PINNED | `test_401_is_rejected_auth_failure`; `test_rejections_are_not_retried`; `test_athlete_status_mapping`; R6 `unauthorized-blocked` |
| 9.2 | PINNED | `test_403_is_connector_error_with_garmin_remedies`; `test_athlete_status_mapping`; `test_service_echo_cannot_expose_secrets`; R6 `forbidden-authfailure` |
| 9.3 | PINNED | `test_retryable_status_messages`; `test_existing_client_retries_are_exhausted`; `test_athlete_request_retry_count`; R6 `rate-limit-wrong-message` |
| 9.4 | PINNED | `test_other_status_names_status_and_request`; `test_athlete_status_mapping`; R6 `other-status-wrong-code` |
| 9.5 | PINNED | `test_packaging_failures`; `test_packaging_interruption`; `test_packaging_held_partial_exit`; R3 `alter-bytes` |
| 9.6 | PINNED | `test_round3_activity_authentication_roles`; `test_round3_ordinary_activity_continues`; R5 `only_rejected_auth_suppresses_wellness` |
| 9.7 | PRESERVED-ONLY; refused-drain E2E UNPINNED | `test_packaging_revision_retry`; `test_packaging_held_roles`; R3 `alter-bytes` |
| 9.8 | PINNED | `test_no_secret_in_request_addresses`; `test_service_echo_cannot_expose_secrets`; `test_athlete_status_redacts_every_credential_form`; R6 `secret-url-leak` |
| 10.1 | PINNED | `test_registered_zero`; `test_renderer_distinct_counts_and_literal_details`; R11 `drop-listed` |
| 10.2 | PINNED | `test_renderer_distinct_counts_and_literal_details`; R11 `drop-listed` |
| 10.3 | PINNED | `test_registered_dry_dates`; `test_renderer_distinct_counts_and_literal_details`; R11 `drop-notices` |
| 10.4 | PINNED | `test_renderer_distinct_counts_and_literal_details`; R11 `drop-listed` |
| 10.5 | PINNED | `test_registered_error`; `test_failed_channels`; R11 `drop-notices` |
| 10.6 | PINNED | `test_failure_notes_are_sorted`; `test_packaging_mixed_sorted_channels`; R2 `disable_wellness_capability` |
| 10.7 | PINNED | `test_registered_absent`; `test_registered_absent`; R11 `render-None-table` |
| 11.1 | UNPINNED | Manual current-state/research evidence; no mutation claim |
| 11.2 | UNPINNED | Manual current-state/research evidence; no mutation claim |
| 11.3 | UNPINNED | Manual current-state/research evidence; no mutation claim |
| 11.4 | UNPINNED | Manual current-state/research evidence; no mutation claim |
| 11.5 | UNPINNED | Manual current-state/research evidence; no mutation claim |
| 11.6 | UNPINNED; pending6.3 repair | Manual current-state/research evidence; no mutation claim |
| 11.7 | UNPINNED manual dependency/task-state; final reconciliation pending | Manual current-state/research evidence; no mutation claim |
| 12.1 | PINNED mandatory; optional explanations UNPINNED | `test_guide_passage`; `test_report_rows_and_meanings`; `test_report_rows_match_cli`; R12 `prior-passage-intro` |
| 12.2 | PINNED mandatory; optional explanations UNPINNED | `test_guide_passage`; `test_guide_passage`; `test_history_start_matches_connector`; R12 `prior-passage-intro` |
| 12.3 | PINNED | `test_wellness_intake_names_enabled_pull_and_links_connector`; R13 `guide-source` |
| 12.4 | PINNED | `test_pull_bullet_states_wellness_guarantees`; `test_current_change_paragraph_states_wellness_pull`; `test_the_version_history_records_the_amendment`; `test_contract_bump_and_release_notes_are_current`; R14 `delete-pull-wellness-clause` |
| 12.5 | PINNED | `test_wellness_channel_binding_matches_report_fields`; `test_wellness_channel_athlete_instructions`; R15 `claimed-000-drop-row-unchanged` |
| 12.6 | PINNED | `test_unreleased_wellness_records`; R13 `The inte-role-comment` |
| 12.7 | PINNED headings/association; UNPINNED detailed governance (manual correct) | `test_upstream_amendment_records_wellness_pull`; R13 `connectors-heading-delete` |
| 13.1 | PINNED | `test_offline_commands_complete_unchanged_with_connectors_and_socket_guarded`; `test_offline_commands_complete_unchanged_with_connectors_and_socket_guarded`; R16 `offline-sync` |
| 13.2 | PRESERVED-ONLY | `test_no_new_third_party_runtime_dependency_was_added` |
| 13.3 | PINNED | `test_package_bytes_do_not_depend_on_clock_or_machine`; `test_wellness_roundtrip_stable_order_and_omission`; `test_intervals_pull_sync_archives_series_and_second_pull_cleans_delivery`; R10 `inventories-073-replay-081-clock-machine-metadata` |
| 13.4 | PINNED synthetic workflow; PRESERVED-ONLY shared network/environment guard | `test_an_ordinary_test_has_socket_guard_and_isolated_credentials_dir`; `test_autouse_isolation_fixture_removes_preexisting_stale_overrides`; `test_intervals_pull_sync_archives_series_and_second_pull_cleans_delivery`; R16 `e2e-canonical-bytes` |
| 13.5 | UNPINNED | Manual current-state/research evidence; no mutation claim |

All owned uv/pytest/audit subprocesses joined or independently observed absent; final process inspection showed only its own ps/rg commands. No task/spec metadata/log/commit changed by implementer. Final current tracked-feature hashes and evidence checksums: `final-manifest.json`. Fresh reviewer must run exactly one canonical full suite on the unchanged source/test bytes, then parent appends its result and owns final task state/push.

- **6.2 review gate (2026-10-15).** Independently APPROVED → VERIFIED. Fresh canonical 18,483 passed / 44 skipped (18,527 collected); Ruff lint/format 746, configured mypy 561 and whitespace clean. All 137 cited symbols passed. Independent audit matched all 91 source criteria, 58 current feature hashes, 27 evidence hashes, 80 historical test ASTs and 50 whole-file matches; reparsed 116 historical records, 61 XML, 40 logs and 34 declared-control XML artifacts. Parent rechecked the final hash manifest and raw canonical XML and ran fresh focused 144 passed. All five validation PIDs joined and gone; exact-head CI 38781910921 SUCCESS. The preceding readiness record remains historical context; this gate is complete. Task 6.3 still owns TBC-W5 design amendment, numbered repair and another full 6.2 gate before completion; this is not feature GO. No new follow-ups.

- **6.3 repair planning (2026-10-15).** Controller reconciled TBC-W5 at its design marker and Packaging/Decision 9, retained the contradictory shapes-only findings and observation limits, and appended numbered repair 7.1 before completion. Public unauthenticated API schema rechecked exact six boolean download-switch names; private/ICU exclusion and strict-present-True/absent-list compatibility are explicit fitdocs policy, not live toggle causality. Temporary public-schema settings evidence: /private/tmp/wellness-pull-completion/public-schema-settings.json. Task 6.3 now depends on 7.1 and its rerun of 6.2.

- **7.1 (2026-10-15).** READY_FOR_REVIEW → independently APPROVED round 2 → VERIFIED. Reconciled TBC-W5: private/ICU namespaces never create claims; six exact known wellness-download switches admit claims only for present boolean True, while missing switches and other valid platform tokens retain list compatibility. Garmin health never substitutes; filtering precedes cardinality; records and resulting package-origin metadata preserved. Only `_wellness_origins` changed in production; old private expected value alone migrated, all other 89 definitions/parameters preserved; existing docs retained with policy insertions. Behavioral OFF 183 owning failures/768 passes, ON and removed-flag 951 passes. Fresh reviewer replayed all 59 current applications and four new faults: 63 applications/126 pytest commands, 793 owning AssertionErrors, 538 GREEN applied cases, all 1,331 restored cases GREEN. Parent raw XML/exact applied-source/full Assert-AST/function-ordinal audit confirmed all 447 new assertion incidences across 224 new cases plus the changed old private case (23 sites/225 nodes), exact five hashes. Initial wrong synthetic credential literal was corrected to the hard-rule key with exact one-Constant proof; its interrupted canonical receives no credit. Current complete canonical 18,707 passed / 44 skipped (18,751 collected); mypy 562, Ruff lint/format 747 and whitespace clean; fresh parent focused 1,313 passed. All 1,932 initial hashes and 481 historical artifacts preserved, all 132 recorded review uv PIDs exited. No new follow-ups. Postrepair 6.2 numeric/coverage/status and exact-commit CI remain required before 6.3.

- **6.3 completion reconciliation / postrepair 6.2 delta (2026-10-15; implementation handoff, review gates pending).** This entry supersedes the historical 6.2 table's pending classifications for 8.1, 11.6 and 11.7; it does not rewrite the earlier implementation/review records or turn the original TBC-W5 contradiction into a confirmation. The requirement document still contains 13 requirements / **91 acceptance criteria**. Repair 7.1 adds one executable leaf, giving **7 groups / 20 mandatory leaves**; at this handoff **19/20 are checked, only controller-owned 6.3 remains unchecked**. Prospective `implementation-complete` metadata and the owned roadmap marks are reviewable implementation records; final completion approval, feature integration GO and main landing are still controller gates.

  **Current finding and governance resolution:** TBC-W1/W2/W3/W4/W6/W7/W8 remain confirmed within their original observation limits; TBC-W5 remains contradicted. The amended TBC-W5 marker, IntervalsWellness Packaging and Decision 9 specify the namespace and known-switch policy, and numbered repair 7.1 is independently APPROVED round 2, VERIFIED, checked and pushed in `8f050d7f05aef8a75346183a48446d91694f655c`. Neither public-schema property names/types nor the read-only account snapshot establishes toggle causality. No wellness-store format, field mapping or rules-version amendment is required, because W1/W3/W4 were confirmed. No original feature implementation task waited for the live check; only completion 6.3 has that gate. Repair 7.1 was generated by completion reconciliation after the contradiction, rather than being an original feature task held waiting for live evidence. Requirements 11.6/11.7 are **MANUALLY VERIFIED, automatically UNPINNED governance**, not new automated scheduler claims. Live-check privacy/provenance requirements 11.1–11.5 and 13.5 retain their honest manual/automatically UNPINNED classifications. This implementer read no environment/key file and made no service/account request.

  **Coverage delta on current bytes (all other original criterion classifications retained):**

  | Criterion | Current classification | Current repair proof / preserved scope |
  |---|---|---|
  | 8.1 | PINNED for reconciled attribution policy | `test_nonplatform_namespace_has_no_origins`, `test_present_switch_native_json_partition`, `test_absent_switch_retains_list_compatibility`, `test_each_switch_controls_its_own_platform`, `test_garmin_health_does_not_replace_wellness_switch`, `test_unknown_platform_ignores_invented_switch`. Current actual faults admit ICU/private, ignore a switch, swap any two of six bindings, accept nonboolean truthiness, require an absent switch, substitute health, or infer a gate for an unknown token. This replaces the historical pending/private→private partial claim. |
  | 8.2 | PINNED; original classification preserved, repair proof added | `test_ignored_lists_do_not_make_enabled_platform_ambiguous` and `test_enabled_platform_collision_omits_only_shared_field`; actual admit-disabled/ICU/private ambiguity and admit-enabled-collision faults. Admission precedes cardinality. Prior settings/cardinality and empty-origins tests remain. |
  | 8.3 | PINNED; original classification preserved, repair proof added | Nonplatform and unknown-platform tests; actual admit-private/admit-icu/infer-arbitrary-switch plus independent `own-round2-unknown-prefix-switch-inferred`. Prior invalid/unmatched platform tests and all other old parameters remain. |
  | 8.4 | PINNED; original classification preserved, repair proof added | `test_attribution_preserves_opaque_records`, `test_settings_input_is_preserved`; actual infer-origin-from-record-values/alter-settings-input plus independent record-empty-settings-fallback. Existing settings-only absent-field and independent package-envelope/metadata tests remain. |
  | 8.5 | PINNED; original classification preserved, repair proof added | Record output/input assertions killed independently by alter-delivered-record-values and alter-caller-record-input. Prior native JSON type/canonical-record tests remain; ordinary Python equality is not claimed to distinguish bool/int/float by itself. |
  | 11.6 | MANUALLY VERIFIED; automatically UNPINNED | Original contradiction preserved; marker/Packaging/Decision 9 amended, numbered 7.1 checked after independent review/verification. Whole-feature reviewer canonical and exact repair CI remain completion gates; no automatic governance mutation claim. |
  | 11.7 | MANUALLY VERIFIED; automatically UNPINNED | Original 19-leaf dependency graph and completion-generated repair inspected; original implementation tasks did not wait on 1.1, completion 6.3 depends on 1.1/6.2/7.1. No automated scheduling claim. |
  | 12.1–12.3 | Original classifications preserved | Mandatory guide/link/report/configuration tests remain; `test_visible_attribution_policy` adds current visible-policy passage pins in both guides. Actual clause-deletion and invisible/wrong-ancestry faults RED; emphasis/link/reflow equivalents GREEN. Existing optional explanatory gaps remain automatically UNPINNED. |

  **Raw discrimination provenance, inspected rather than rerun:** `/private/tmp/wellness-pull-task7.1-round2-review/{five-hashes.json,replay-summary.json,assertion-line-map.json,discrimination-audit.json,finite-audit.json}` plus every `mutations/<application>/{applied.json,applied.xml,restored.json,restored.xml,*applied}`. This handoff reparsed all **63 applications / 126 raw XML**: 59 claimed applications (56 faults, 3 valid controls) plus four independent reviewer faults, **793 owning AssertionErrors, 538 applied GREEN control cases, 1,331 restored GREEN cases**. Each of 793 failure-owner records matches the current source hash and actual Assert AST/function ordinal/restored line; the recorded repair covers all **447 new assertion incidences / 224 new cases**, plus the migrated old private case. Actual applied-source hashes match receipts. Full current audit: `/private/tmp/wellness-pull-task6.3-implement/coverage-provenance.json`. No test/assertion changed in task 6.3, so new discrimination is N/A. The older 91-row sweep retains its narrower limits and classifications; no historical fault is newly claimed rerun.

  Current source/test/document SHA256:

  - `src/fitdocs/connectors/intervals.py`: `9ee141a00d50a0242460536e4d412cb76f7503e0af853454e131701ac13fbfa1`.
  - `tests/connectors/test_wellness_attribution.py`: `0cba381b1979f1cfbcd7a8a33ba7eb046ea0173ac28454a8cbf5dcb7b8778d3c`.
  - `tests/connectors/test_intervals_wellness.py`: `4816d0f5c728c2e9b111265e268e6dee9ed526f4c3105beb0547935d64200d01`.
  - `docs/connectors.md`: `3015a8c425f00acf00f142e2870b9204f63f1e1368643e1254e09f9eecabb710`.
  - `docs/wellness.md`: `1d3fb8c0b6aa7dc21db471a9cf1359e8e0061632f706652eedd625ab4ee37c3f`.

  **Preservation and numeric gate, freshly checked:** HEAD `8f050d7f05aef8a75346183a48446d91694f655c`; main and origin/main both `6cac16d8763348b132fa6f9450c2e014fbc5ae2b`, main an ancestor. Contract main **11 → branch 12**, `DOC_VERSION` **9**, index `SCHEMA_VERSION` **3**, wellness ledger format **2**. All seven declaration goldens differ from main only in the literal contract-version line; outgoing wellness-store history is preserved, current head paragraph/literal 11→12 assertion/both index pins/CHANGELOG/records/wiki literal numbers agree. Actual main amendment sections show next-free connectors **4** (main last 3, dashboards), wiki-contract **7** (main last 6, wellness-store), intervals-connector **1** (none on main); all prior amendment sections remain exact. Shared roadmap connectors remains unchecked because recovery's no-network half is not on main; wiki remains unchecked because only wellness-store's half is on main. This branch's owned halves and intervals update are recorded without marking peers complete. The controller will reconcile main-landing/GO pending prose only after actual feature GO and main landing.

  The 58-file 6.2 feature manifest still has **52 byte-identical files**; the six changed files are exactly research/tasks historical append state, the one allowed production function, the single old private expected value, and the two guide insertions. All source AST outside `_wellness_origins` is exact against the 6.2 baseline; old test bytes differ in exactly the private expected value. The original interface/surface and all remaining source/test assertions are retained. The 46-name public prefix grows to 50, the 18 confinement entry prefix grows to 19, and the ten offline rows are preserved. Dependency files `pyproject.toml` and `uv.lock` remain identical to main; allowed import/dependency boundaries and no direct clock calls remain checked by the preserved AST and fresh boundary test. No new wellness-store imports, rendering/storage writes or runtime dependency. Detailed current receipts: `/private/tmp/wellness-pull-task6.3-implement/{numeric-audit.json,preservation-audit.json,status-audit.json}`. Upstream approvals remain true; connectors **27/27**, intervals **13/13**, wiki **17/17**, wellness-store **27/27**. Main changing again requires controller rebase/number refresh before landing; this implementer performed no Git mutation.

  **Validation and ownership:** The postrepair independent canonical on these exact five source/test/document hashes already completed **18,707 passed / 44 skipped / 18,751 collected**, with no failures/errors: `/private/tmp/wellness-pull-task7.1-round2-review/final/{result.json,pytest.xml,output.log}` and `final-audit.json`. This is the prior repair review's complete canonical, not a new 6.3 run. It includes actual downstream consumers and the synthetic real-CLI pull/drain/second-pull integration; no unfinished peer worktree checks or queued defect is needed. Fresh task-6.3 focused command after metadata edits passed **588 tests**, including all 224 repair cases, the migrated old expectation, docs/link/records, version/history/declaration, contract pins and dependency boundaries; Ruff lint PASS, format **747 files**, configured `uv run mypy` **562 files**, whitespace PASS. Exact commands/exits/JUnit: `/private/tmp/wellness-pull-task6.3-implement/{validation.json,focused.xml,focused.log,ruff-lint.log,ruff-format.log,mypy.log,whitespace.log}`. All five owned child validation PIDs were joined and are gone; process inspection found no owned wrapper/pytest/CLI, only unrelated existing wiki servers (untouched).

  At the latest implementer CI refresh, exact repair commit `8f050d7` docs workflow **38796254663 SUCCESS**, but main CI **38796254637 IN_PROGRESS** ([run](https://github.com/joshua-stauffer/fitdocs/actions/runs/38796254637)); `/private/tmp/wellness-pull-task6.3-implement/ci-final.json` records the actual final UTC check. Earlier successful CI for other commits is historical and does not satisfy this exact-commit gate. The fresh completion reviewer owns **one complete canonical after these metadata edits and this delta are present**, and must **hold approval until exact 8f050d7 CI is actually SUCCESS**. Parent then applies completion verification, ticks 6.3/group 6, commits/pushes and performs feature integration GO/main landing. No feature GO or completed final CI claim is made by this handoff. Nonbehavioral governance task: no feature flag and no new tests/assertions. No adjacent follow-up surfaced.

- **6.3 APPROVED / VERIFIED (2026-10-15).** Independent round-1 review completed one full canonical: 18,707 passed / 44 skipped / 18,751 collected, exit 0; configured mypy 562, Ruff lint/format 747 and whitespace clean. Exact repair commit `8f050d7` CI run 38796254637 and docs 38796254663 both SUCCESS. All 1,932 tracked hashes preserved through review, every validation process joined and absent; raw results and metadata/numeric/coverage audit: `/private/tmp/wellness-pull-task6.3-round1-review/`. Parent independently verified raw JUnit, current hashes, process closure and fresh 260 focused cases plus whitespace. No findings or adjacent follow-ups. This approval supersedes the historical pending task-review/repair-CI states above: all 20/20 mandatory leaves and all seven groups are checked. Final feature integration GO and main landing follow separately.

- **Final feature validation GO / VERIFIED (2026-10-15).** After fresh fetch/rebase onto unchanged main `6cac16d`, independent feature-level coverage assessed 13/13 requirements and 91/91 criteria (77 PINNED, 4 PRESERVED-ONLY, 8 manually verified/automatically UNPINNED, 2 mixed; all prior scope limits retained); design/integration reviewed 12 seams and 16 finite checks without findings. Fresh complete canonical at `6544e88`: 18,707 passed /44 skipped /18,751 collected, exit 0; mypy562/Ruff747/whitespace clean. The 44 local skips are 36 missing docs-tooling, two missing actionlint and six unset forbidden-string input checks; exact behavior-commit CI passed the configured remote gate. Canonical release build produced one wheel and one sdist. Isolated installed-wheel version/help/plugins and a synthetic actual-CLI pull/drain/archive/read_series/second-pull workflow passed, with six Garmin values despite private/ICU competing settings, 16 fake transport requests, zero real sockets, and unchanged archive/series bytes and mtimes after cleanup. Parent verified raw XML/exits, all 1,932 tracked hashes, 243 wheel Python member bytes, artifact hashes and all 15 recorded PIDs absent. Evidence: `/private/tmp/wellness-pull-final-{mechanical,coverage,design}/` and controller `validation-report.md`; artifacts preserved under mechanical `artifacts/`. All 20/20 leaves and seven groups complete, no blocked tasks, findings or adjacent follow-ups. These completed gates supersede historical prospective/pending handoff states above. Final metadata recording changes no source, test or shipped document bytes; main landing follows the change protocol.
