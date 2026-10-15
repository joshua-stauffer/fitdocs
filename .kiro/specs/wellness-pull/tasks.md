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

- [ ] 3. Integration: the pull engine

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

- [ ] 3.3 Pull intervals.icu wellness through the engine
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

- [ ] 4. The report and the agent surface

- [ ] 4.1 Print the wellness table in the pull report
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

- [ ] 4.2 Document the wellness channels in the packaged skill and bind them
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

- [ ] 5. Documentation and records

- [ ] 5.1 Document the wellness pull in the connectors guide
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

- [ ] 5.2 Advance the ownership contract for the pull's wellness deliveries (wiki-contract amendment)
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

- [ ] 5.3 Update the wellness guide and the changelog, and record the connectors and intervals.icu amendments
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
  - **Mutations:** delete an amendment heading; drop the guide's link (the
    records test reds; `tests/test_docs_guarantees.py:951-993` still resolves
    every remaining anchor).
  - **Observable:** `uv run pytest tests/connectors/test_wellness_records.py
    tests/test_docs_guarantees.py` green; `/kiro-spec-status connectors` and
    `intervals-connector` clean.
  - _Requirements: 12.3, 12.6, 12.7_
  - _Depends: 5.1, 5.2_

- [ ] 6. Validation

- [ ] 6.1 End to end through the drain, offline elsewhere, and confined
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

- [ ] 6.2 Whole-suite gate, exhaustive sweep and rebase
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

- [ ] 6.3 Completion gate: reconcile the live check with the design
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
