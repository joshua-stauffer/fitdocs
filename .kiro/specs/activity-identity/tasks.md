# Implementation Plan

## Upstream Prerequisites

- **Every spec this plan builds on has shipped**: `fit-ingest` (the model and
  the decode wrapper), `workout-docs` (render, sync), `wiki-contract` (the
  document contract, declarations, audit, confinement), `inbox` (drain,
  quarantine, disposition), `plan-resolution` (the chained plan pass). This
  plan has no upstream implementation prerequisite.
- **It is the prerequisite of `channel-merge`** (wave 2), which consumes the
  seams design.md states under "Cross-spec seams": `fitdocs.identity.roles`
  (`SourceMember`, `PageRoles`, `rank_members`), the parsed-member mapping, and
  `sync._render_activity`. A task that finds it must change one of those shapes
  stops and reports rather than changing it.
- **Siblings in flight** (`running-dynamics`, `connectors`, wave 1): no code
  dependency either way; the shared files are listed below under "Cross-spec
  shared files".

**Hard rules for every task**

- No module under `src/fitdocs/identity/` imports `fitdocs.sync`,
  `fitdocs.render`, `fitdocs.audit`, `fitdocs.cli`, `fitdocs.ingest`,
  `fitdocs.metrics`, `fitdocs.load`, `fitdocs.history`, `fitdocs.plans`,
  `fitdocs.tiles`, `fitdocs.inbox`, `yaml`, `urllib` or `socket`, or names a
  clock function. Only `identity/pages.py` and `identity/holds.py` touch the
  filesystem; only `identity/kinds.py` and `identity/pages.py` import
  `fitdocs.contract`.
- No tolerance constant is changed to make a test pass. A fixture that the
  rule now reads as one session is re-shaped so the test's premise holds.
- Absent is `None`: no task writes a default, a `0` or an empty string for a
  value a file did not record.
- No fixture holds personal data: every `.fit` input is synthesized by
  `tests/fixtures/builder.py` or `tests/fixtures/identity.py`; no value comes
  from the athlete's archive.
- `DOC_VERSION` and `CONTRACT_VERSION` each advance by **one from the value on
  the branch when the task runs**; before merge, after the rebase, the
  implementer checks that each equals `main`'s value plus one and re-pins if a
  sibling landed a bump first. No task hard-codes the resulting number as if
  this plan landed first.
- No module under `src/fitdocs` other than `contract.py` names `uuid` as an
  identifier -- not a dataclass field, a parameter, a local or an import:
  `tests/test_contract_consumers.py:502-529` reads any `ast.Name` `uuid` as a
  second session-UUID implementation. Use `session_uuid`, `page_uuid` and the
  like. No registered contract consumer defines a name listed in that file's
  `FORBIDDEN_LOCAL_NAMES` (`:149-163`, e.g. `_session_uuid`, `_sources`).
- Every task that creates a typed test or fixture module type-checks it clean
  with `uv run mypy <its paths>` as part of its observable; 7.1 registers them
  all in `pyproject.toml` (the file's rule, `pyproject.toml:97-98`: a module
  joins the list with its errors already fixed), so the parallel tasks never
  share `pyproject.toml`.
- The default source precedence is the **maintainer decision of 2026-09-29**:
  Garmin originals (device file, Connect export, partner-API copy), then the
  HealthFit phone copy, then every other original (a Stryd file), then unknown
  files. A HealthFit copy is a phone copy whatever device recorded the
  activity. No task changes this default.
- A task that finds it needs a new runtime dependency, a new command, a new
  owned path prefix, or a change to a cross-spec seam's shape stops and
  reports.

## Shared source files

Each file below has more than one writer in this plan; the owners are
strictly sequential (none is marked `(P)`).

- `src/fitdocs/sync.py` -- 3.2 (`find_document` delegates to the page index),
  4.1 (roles and render from the base), 4.2 (rename, cleanup, settle), 4.3
  (planned runs in `sync`), 4.4 (planned runs in `drain`), 4.5 (regeneration).
- `src/fitdocs/contract.py` -- 3.1 (keys, reader, managed set,
  `DOC_VERSION`), 6.2 (`CONTRACT_VERSION`).
- `docs/ownership-contract.md` -- 3.1 (the four keys in the "Managed
  Frontmatter Keys" list only, because `tests/test_ownership_contract.py:131-134`
  holds that list equal to `MANAGED_KEYS`), 6.2 (everything else).
- `tests/test_public_api.py` -- 1.2 (`_EXPECTED` gains `FileIdentity`), 3.1
  (`_CONTRACT_SURFACE` gains the new contract names), 7.1
  (`_IDENTITY_SURFACE`); each edits only its own table.
- `tests/test_contract_consumers.py` -- 2.1 (registers `identity.kinds`), 3.1
  (`FORBIDDEN_LITERALS` and the frontmatter bindings), 3.2 (registers
  `identity.pages`; `sync`'s bindings), 4.1-4.5 and 5.1 (only the binding
  tuple of a module the task changed). Rule: a task that changes which
  contract names a registered module binds updates that module's
  `CONTRACT_BINDINGS` entry in the same task, and nothing else in the file.
- `src/fitdocs/layout.py` -- 2.5 only. `src/fitdocs/model.py` -- 1.2 only.
  `src/fitdocs/render/*` -- 3.1 only. `src/fitdocs/audit.py` -- 5.1 only.
  `src/fitdocs/cli.py` -- 5.2 only. `src/fitdocs/declaration.py` -- 6.2 only.
  `tests/fixtures/builder.py` -- 1.1 only. `pyproject.toml` -- 7.1 only.
- `src/fitdocs/identity/__init__.py` -- created by 2.1 as a package marker
  that re-exports nothing (`__all__: list[str] = []`); no later task edits it.
  Consumers import the submodules.

**Cross-spec shared files** (siblings written in parallel; the partition rule:
append a field, a row, an entry or a block, never rewrite or reorder a
sibling's):

- `src/fitdocs/model.py` (`Activity`, `Provenance`; running-dynamics also
  appends) and `tests/golden/*.json` (the second lander regenerates).
- `DOC_VERSION` literal sites both specs move (second lander re-pins):
  `tests/test_cli_check.py:196, 198` (this plan rewrites them as
  `f"doc_version: {DOC_VERSION}"`), `tests/render/test_frontmatter.py:44,
  101`, `tests/metrics/test_sources.py:2270`; running-dynamics'
  `_PRE_RUNNING_DYNAMICS_DOC_VERSION` constant keeps the value it recorded.
- `tests/fixtures/builder.py` `_file_id`: running-dynamics' task 1.2 gives it
  keyword-only, defaulted `manufacturer`, `product` and `time_created`
  parameters -- the shape 1.1 needs. Whichever lands first adds them; the
  other reuses them; every default equals today's value.
- `src/fitdocs/contract.py` (`DOC_VERSION`, `CONTRACT_VERSION`,
  `MANAGED_KEYS`; running-dynamics, connectors, channel-merge also advance or
  append).
- `tests/test_contract_consumers.py`, `tests/test_confinement.py`,
  `tests/test_public_api.py` (appended registrations).
- `docs/ownership-contract.md` (connectors appends `.fitdocs/` and credential
  statements), `docs/compatibility.md` and
  `tests/test_compatibility_policy.py` (connectors adds a table: the count
  advances once per lander), `docs/configuration.md`, `CHANGELOG.md`
  `[Unreleased]`.
- `.kiro/specs/wiki-contract/requirements.md` Amendment 4 (created by the
  first lander, appended by the others), `.kiro/specs/fit-ingest/requirements.md`
  (running-dynamics and intervals-connector also amend it: take the next free
  amendment number on the branch).

## Test File Ownership

- `tests/fixtures/identity.py`, `tests/fixtures/test_identity_fixtures.py`,
  the `builder.py` parameter and its `tests/fixtures/test_builder.py` pin → 1.1.
- `tests/ingest/test_file_id.py`, `tests/golden/*.json` (regenerated) → 1.2;
  `tests/test_public_api.py` `_EXPECTED` entry → 1.2.
- `tests/identity/__init__.py`, `tests/identity/test_kinds.py` → 2.1.
- `tests/identity/test_matching.py` → 2.2.
- `tests/identity/test_roles.py`, `tests/identity/test_settings.py` → 2.3.
- `tests/identity/test_planning.py` → 2.4.
- `tests/identity/test_holds.py`, `tests/test_layout.py` (the held path) → 2.5.
- `tests/test_contract.py`, `tests/render/test_frontmatter.py`,
  `tests/render/golden_docs/*.md` (regenerated), `tests/metrics/test_sources.py`
  (the one constant), `tests/test_cli_check.py` (the `doc_version` literal at
  `:196-198` only), `tests/test_public_api.py` (`_CONTRACT_SURFACE` only) → 3.1.
- `tests/identity/test_pages.py` → 3.2.
- `tests/test_identity_e2e.py` -- one headed section per task: roles → 4.1;
  renames → 4.2; planned sync runs → 4.3; drain → 4.4; regeneration → 4.5;
  measured-shape CLI scenarios → 7.2. No task edits another's section.
- `tests/test_sync.py`, `tests/test_sync_e2e.py` → 4.1 (only assertions 4.1
  moves) and 4.3 (the collision sweep); `tests/test_portability.py` → 4.3;
  `tests/test_drain.py` → 4.4; `tests/test_confinement.py` → 4.2.
- **The collision sweep** (4.3, 4.4, 4.5): each of these tasks may re-shape a
  test outside its own files when the rule, newly applied by that task, reads
  the test's corpus as one session; it re-shapes the fixture so the test's
  premise holds (never a tolerance) and lists every re-shaped test in its
  report.
- `tests/test_audit.py` → 5.1. `tests/test_cli_identity.py` (new) → 5.2.
- `tests/test_compatibility_policy.py`, `tests/identity/test_settings_docs.py`
  → 6.1.
- `tests/test_ownership_contract.py`, `tests/test_declaration.py`,
  `tests/declaration_golden/*` (regenerated),
  `tests/identity/test_contract_docs.py` → 6.2.
- `tests/identity/test_boundary.py`, `tests/test_public_api.py`
  (`_IDENTITY_SURFACE`) → 7.1.

**Every new assertion names its mutation** (change-protocol § Fixture
Discrimination): each task's bullets name the production mutation that must
redden its assertions; the implementer runs it through `uv run pytest`,
observes red, reverts, observes green, and says so in the report. Boundary
fixtures sit one unit inside and one unit outside each tolerance; a fixture
never co-varies two keys a rule distinguishes.

- [ ] 1. Foundation: file identity at ingest and the synthesized identity fixtures

- [ ] 1.1 Synthesize the measured file shapes as fixtures
  - Add a parameterized builder for one session (sport, start, elapsed, timer,
    distance, manufacturer, product, serial, creation time, optional HealthFit
    session UUID with its developer-field registration, optional position) with
    a small record stream spanning the session, plus a splice that appends N
    messages of an undocumented global number and recomputes the header data
    size and both CRCs
  - Provide the named species design.md lists -- Garmin-style original (with
    undocumented messages), partner copy (same `file_id`, none), HealthFit-style
    copy, HealthFit-style copy shifted by whole hours, a HealthFit-style
    re-export pair sharing one session UUID whose older export is shifted by one
    hour and whose newer export carries the corrected start, Stryd-style file,
    and the two-10 k counter-example pair -- as synthetic constants
  - Give `builder._file_id` keyword-only, defaulted `manufacturer`, `product`
    and `time_created` parameters unless running-dynamics already added them on
    the branch (then reuse them), and `builder._encode_run_with_developer_fields`
    a keyword-only `time_created`; every default equals today's value, so every
    existing fixture's bytes stay identical. Pass a later creation time for
    `reexport_b`, so the canonical rank of 4.1 keeps the re-export pair in its
    current order; pin in `tests/fixtures/test_builder.py` that only
    `reexport_b`'s bytes moved
  - Tests (`tests/fixtures/test_identity_fixtures.py`): each species decodes
    with `builder.decode_messages` without decode errors, passes the SDK's
    integrity check, and carries exactly the stated `file_id`, session values
    and undocumented-message count
  - Named mutations: skip the CRC recomputation (integrity check reds); splice
    one message fewer (count pin reds); give the partner copy a different serial
    (its `file_id` pin reds)
  - Observable: `uv run pytest tests/fixtures` green; `uv run mypy
    tests/fixtures/identity.py tests/fixtures/test_identity_fixtures.py` clean;
    every other fixture's bytes unchanged except `reexport_b`
  - _Requirements: 2.2, 2.3, 3.2, 3.3, 3.4, 3.5_

- [ ] 1.2 Read the file-identity record and count undocumented messages at ingest
  - Add the file-identity value to the model (manufacturer, product code,
    serial number, creation time, each absent when not recorded), append it to
    the activity with an all-absent default, and append an undocumented-message
    count to provenance with an absent default; the schema version does not
    move
  - Decode the first `file_id` message into it: manufacturer as the profile's
    name or the recorded number as text, product only as a genuine integer and
    never from the `garmin_product` sub-field, creation time as an aware UTC
    instant; count the messages the decoder filed under all-digit keys;
    `parse_fit` passes both explicitly
  - Export the file-identity type from the package root (lazy export,
    `__all__`, the public-API pin's `_EXPECTED`, and `docs/plugins.md`'s public
    import surface list)
  - Regenerate `tests/golden/*.json` with `tests/golden/generate.py`; the diff
    adds the two new fields and changes no existing value
  - Record fit-ingest's amendment: `## Amendment N (date): file identity,
    landed by activity-identity` (N the next free number on the branch);
    Requirement 4 gains two criteria tagged `_(added by Amendment N)_`;
    `spec.json` gains an `amendments` entry; nothing renumbered
  - Tests (`tests/ingest/test_file_id.py`): encoded `file_id` messages for
    `development`, `stryd`, `garmin` with product 3843, a file with no
    `file_id`, one with a missing serial, one with two `file_id` messages of
    different serials; a file spliced by 1.1's helper with a known undocumented count
  - Named mutations: read the last `file_id` instead of the first; read
    `garmin_product` into the product; default a missing serial to `0`; count
    every decoded key; convert the creation time without a timezone
  - Observable: `parse_fit` of a Garmin-shaped file exposes manufacturer
    `"garmin"`, product `3843`, its serial and a UTC creation time; a file
    without `file_id` exposes all four as `None`; `uv run pytest tests/ingest
    tests/test_golden.py tests/test_public_api.py` green; `uv run mypy
    tests/ingest/test_file_id.py` clean
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 2. Core: the pure identity rule, the precedence, the planner and the hold record

- [ ] 2.1 Classify files into source kinds and derive the identity a page records for its base
  - Create the identity package as a marker that re-exports nothing, and the
    kinds module: the closed vocabulary, the HealthFit writer marker, the kind
    derivation from the file's own manufacturer and session developer field,
    the device-identity digest (16 hex digits of a SHA-256 over manufacturer,
    serial and UTC creation time; absent unless all three are recorded), and
    the base-identity value (kind, recorded elapsed, recorded distance,
    digest, own session UUID)
  - Publish the session-UUID developer-field name here once
  - Register the module as a contract consumer (it binds the session-UUID
    formatter) in `tests/test_contract_consumers.py`
  - Tests (`tests/identity/test_kinds.py`): the three kinds from activities
    built with and without the marker and each manufacturer shape, including a
    HealthFit copy of a Garmin ride (its `file_id` says `development`; its
    devices say `garmin`) classified `phone_copy`; the digest's absence rules,
    determinism, and that it differs when only the creation time differs
  - Named mutations: accept the marker without `development`; classify
    `development` without the marker as `phone_copy`; classify by the device
    list's manufacturer instead of `file_id`'s (the HealthFit-copy-of-a-Garmin-ride
    case reds); leave the creation time out of the digest; take elapsed from the
    timer
  - Observable: `uv run pytest tests/identity/test_kinds.py
    tests/test_contract_consumers.py` green; `uv run mypy tests/identity` clean
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 5.4_

- [ ] 2.2 Implement the match rule with its stated tolerances
  - Add the tolerance constants with their measured sources exactly as
    design.md's table states, the evidence vocabulary, the comparable session
    key (no timer field) built from an activity, and the symmetric pair-evidence
    function with the device, strict and shifted tiers and their absent-value
    rules; comparisons inclusive
  - Tests (`tests/identity/test_matching.py`, over session-key values): one
    just-inside and one just-outside pair per constant; a same-everything pair
    of different sports; a whole-hour shift where neither side is a phone copy;
    a pair with equal elapsed and timers 400 s apart; the two-10 k
    counter-example; absent start, absent elapsed (device still matches),
    one-sided and two-sided absent distance; symmetry for every case
  - Named mutations: widen each constant by one unit (its outside pair reds);
    delete the sport check; delete the phone-copy gate; use `<` for `≤`; allow
    37 hours; compare the shift without its 1 s tolerance
  - Observable: every tolerance's boundary is pinned by a test that reds under
    its widening; `uv run pytest tests/identity/test_matching.py` green; `uv run
    mypy tests/identity/test_matching.py` clean
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.11_

- [ ] 2.3 (P) Rank a page's files by precedence and read the precedence setting
  - Add the precedence entries (a kind, or `original:<manufacturer>`), the
    default `original:garmin`, `phone_copy`, `original`, `unknown` (maintainer
    decision 2026-09-29), resolution of a configured list (it replaces the
    default; kinds it does not name are appended in the order `original`,
    `phone_copy`, `unknown`, where only a bare kind entry names a kind and an
    `original:<m>` entry never does; the default's `original:garmin` is not
    appended), the source-member value built from a parsed file, the four-key rank
    key of Req 2.8, the page roles (base, extras best first, unresolved refs,
    and the ascending-rank `sources` with the base last), and the page session
    UUID rule (base, then extras, then the page's recorded value)
  - Add the `[identity]` table reader with its error type (a subclass of the
    shared settings error) and every validation case of Req 2.7, naming the
    settings file and `[identity] precedence`; unknown keys in the table ignored
  - Tests (`tests/identity/test_roles.py`, `tests/identity/test_settings.py`):
    every permutation of a four-member input yields the same roles, with the
    fixture varying kind rank, undocumented count, creation time and hash
    against one another; the default pinned directly -- a Garmin original
    above a HealthFit copy above a Stryd file above an unknown file; a
    configured `["original", "phone_copy", "unknown"]` puts the Stryd file
    above the HealthFit copy, and resolves to exactly those three entries; a
    configured `["original:stryd", "phone_copy"]` ranks a Stryd file first,
    then the HealthFit copy, then a Garmin original at the appended `original`
    position, then an unknown file; `original:<m>` beats its kind's entry wherever it
    sits; unresolved refs first and never base; UUID retention through an extra and
    through the recorded value; each validation error's message
  - Named mutations: swap the `original:garmin` and `phone_copy` tiers of the
    default (the Garmin-over-HealthFit pin reds); swap the `phone_copy` and
    `original` tiers (the HealthFit-over-Stryd pin reds); append the default's
    `original:garmin` to a configured list (the exact-resolution assertion reds,
    and the Garmin original falls below the unknown file in the
    `original:stryd` test); drop the undocumented-count key;
    reverse the creation-time key; rank an absent count first; ignore
    `original:<m>` entries; count an `original:<m>` entry as naming `original`
    (the Garmin original loses its rank position in the `original:stryd` test);
    emit the base first in `sources`; accept `original:development`
  - Observable: `uv run pytest tests/identity/test_roles.py
    tests/identity/test_settings.py` green; `uv run mypy
    tests/identity/test_roles.py tests/identity/test_settings.py` clean
  - _Requirements: 2.5, 2.6, 2.7, 2.8, 5.1, 5.2, 5.3, 5.5, 7.7_
  - _Boundary: PrecedenceAndRoles, IdentitySettings_

- [ ] 2.4 (P) Plan a run's files onto pages and find duplicate pages
  - Add the page record (`path`, `sources`, `session_uuid`, `key`), the page
    index with the exact match reproducing `find_document`'s semantics (session
    UUID first, then source-list membership, each first in path order), the run
    file (`id`, `ref`, `session_uuid`, `key`) -- no field, parameter or local
    named `uuid` -- the three decisions,
    the task plan, the run plan, and the planner of design.md (pinned files,
    groups by linkage including shared session UUIDs, candidate pages through
    base keys and through pinned files, one claim joins, a bridge or a double
    claim holds, tasks ordered by first member)
  - Add duplicate sets over an index (shared source ref, shared session UUID,
    or pair evidence), bucketed by sport and sorted by start
  - Tests (`tests/identity/test_planning.py`): pinned files always join; a
    fresh group of three linked files is one task; a group bridging two pages is
    held with both candidates; two unlinked groups claiming one page are both
    held; a pinned re-export and a strict-matching original in one run share a
    task; every permutation of each scenario yields equal decisions and tasks;
    duplicate sets for each of the three links
  - Named mutations: resolve a bridge to its first page; resolve a double claim
    to its first group; drop the pinned-file linkage (the shared-task scenario
    splits); order tasks by page path instead of first member
  - Observable: `uv run pytest tests/identity/test_planning.py
    tests/test_contract_consumers.py` green, including the permutation tests
    and the single-UUID-implementation guard; `uv run mypy
    tests/identity/test_planning.py` clean
  - _Requirements: 3.7, 3.9, 3.10, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8, 4.9, 5.7, 8.3_
  - _Boundary: RunPlanner_

- [ ] 2.5 (P) Store held files in owned tool state
  - Add the held-record path helper to the layout leaf (inside `.fitdocs/`) and
    rebind the layout's session-UUID field name to the kinds module's constant,
    removing the private copy
  - Add the hold store: entry and record values, load (absent file is an empty
    record and creates nothing; unreadable, invalid, wrong shape or duplicate
    hash raise an error naming the file), save (temp file then replace,
    directory created on demand, nothing written when the bytes are unchanged,
    entries sorted by hash, no clock value)
  - Append the `identity/holds.py` site to
    `.kiro/queue/2026-09-15-atomic-write-helper-copied-per-engine.md` (its
    title and resume command count the private atomic-write copies; this is
    another)
  - Tests (`tests/identity/test_holds.py`, `tests/test_layout.py`): round trip;
    write-if-different leaves the mtime unchanged; each malformed shape raises;
    loading an absent record creates no directory
  - Named mutations: skip the unchanged-bytes check; accept a duplicate hash;
    create `.fitdocs/` on load
  - Observable: a saved record re-loads equal and a second save reports no
    write; `uv run pytest tests/identity/test_holds.py tests/test_layout.py`
    green; `uv run mypy tests/identity/test_holds.py` clean
  - _Requirements: 4.7, 4.10, 8.4_
  - _Boundary: HoldStore_

- [ ] 3. Contract, render and the page scan

- [ ] 3.1 Put the base identity on every page and advance the document format
  - Add the four key constants, their tuple, their membership in the managed
    set, the reader of Req 5.4's values (degrading, never raising, rejecting
    `bool` and non-finite numbers), and the base-last wording of the source-list
    reader's docstring
  - Advance `DOC_VERSION` by one with its docstring paragraph (four keys,
    canonical `sources` order, retained `uuid`); re-pin
    `tests/metrics/test_sources.py`'s `CONSTANT_REGISTRY_ASOF_DOC_VERSION` to
    the new value (it is asserted equal while the registry is clean)
  - Give the render context an optional base-identity value; emit `uuid` and
    the four keys from it inside `build_frontmatter` as direct assignments
    (the anti-drift test reads them from the function's AST), after
    `calories_kcal` and before `sources`, with the stated rounding; when the
    context carries none, derive it from the context's activity; bind the
    session-UUID field name from the kinds module
  - Add the four keys to `FORBIDDEN_LITERALS` and to the frontmatter module's
    `CONTRACT_BINDINGS`; update `tests/test_contract.py`'s published-key set
  - Move, in this task, every pin the new keys or the version advance turn red:
    `docs/ownership-contract.md`'s "Managed Frontmatter Keys" list gains the
    four keys (`tests/test_ownership_contract.py:131-134`);
    `tests/test_public_api.py`'s `_CONTRACT_SURFACE` gains the new contract
    names (`:324-398`); `tests/test_cli_check.py:196-198` becomes
    `f"doc_version: {DOC_VERSION}"`; `tests/render/test_frontmatter.py:44, 101`
    follow the advanced version; any other exact-frontmatter assertion the full
    suite shows red is re-pinned and listed in the report
  - Regenerate every golden document with `tests/render/test_golden_docs.py`'s
    own generator; the only diffs are `doc_version` and the new keys
  - Named mutations: emit a key through a helper instead of a direct assignment
    (the anti-drift test reds); emit `source_device` when the serial is absent;
    let the reader accept `True` as an elapsed time; derive `uuid` from the
    activity even when the context carries identity
  - Observable: a synced run page's frontmatter carries `source_kind`,
    `source_elapsed_s`, `source_distance_m` and `source_device` before
    `sources`; the full `uv run pytest` green
  - _Requirements: 5.2, 5.4, 5.5, 7.4, 9.2, 9.6_

- [ ] 3.2 Build the page index from one frontmatter scan and route the exact match through it
  - Add the page scan: a page record from parsed frontmatter through the
    contract readers only, its recorded `uuid` key read into `session_uuid` (a
    page lacking the identity keys yields a key no rule tier can match), and the sorted scan of `workouts/*.md` that refuses
    symlinks and skips non-workout files and the declaration
  - `find_document` returns `DocumentMatch` built from the index's exact match;
    its signature and semantics are unchanged
  - Register the page scan as a contract consumer; update `fitdocs.sync`'s
    binding tuple to what it binds after the change
  - Tests (`tests/identity/test_pages.py`): parity with the existing
    `find_document` tests' scenarios (session UUID before sources, first in path
    order, symlink refused, a garbled neighbour skipped); a legacy page's record
    key has `elapsed_s`, `distance_m`, `device` and `kind` all `None`, asserted
    field by field, and matches nothing by rule
  - Named mutations: prefer sources over uuid; scan in reverse order; build a
    key from `distance_km`
  - Observable: `uv run pytest tests/identity/test_pages.py tests/test_sync.py
    tests/test_contract_consumers.py` green with `tests/test_sync.py`'s
    `find_document` tests unedited; `uv run mypy tests/identity/test_pages.py`
    clean
  - _Requirements: 3.9, 3.10, 7.4_
  - _Depends: 2.4_

- [ ] 4. Engine: roles, renames and planned runs

- [ ] 4.1 Render every page from its base, with its files in canonical order
  - Give `sync`, `drain` and `regen` a keyword `precedence` defaulting to the
    default precedence
  - For a matched page, resolve every listed file, parse each resolved one
    once, rank them with the new file, and render from the base: canonical
    `sources`, the retained session UUID (held in a local such as `page_uuid`,
    never `uuid`), the base identity computed from the
    base's own parse and passed to the render context, the page's uid from the
    retained UUID or the base hash
  - Add the channel-merge seam `_render_activity(roles, parsed)` returning the
    base's activity; metrics and the map plan come from its result
  - A new file that ranks below the base leaves the base and the filename
    unchanged; no resolved file is a failure with today's reason
  - Regeneration rebuilds every page's roles from its archived files with the
    given precedence
  - Tests (`tests/test_identity_e2e.py`, roles section): the re-export pair in
    either order produces byte-identical pages with `sources` `[a, b]`; a staged
    page shaped like the 2026-09-12 hand adoption (`sources` phone copy then
    device original) regenerates from the original and keeps the copy's UUID;
    an unresolvable listed ref stays first; a page whose listed files are all
    missing fails with the existing reason; the four arrival-order assertions in
    `tests/test_sync.py` and `tests/test_sync_e2e.py` stay green unedited
  - Named mutations: render from the last listed file instead of the base; drop
    UUID retention; order `sources` by arrival
  - Observable: `uv run pytest` green; `uv run mypy tests/test_identity_e2e.py`
    clean; a regenerated hand-adopted page renders the original's values and
    still carries the copy's `uuid`
  - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 6.1, 6.3, 7.1, 7.2, 7.3, 7.6, 7.7_
  - _Depends: 2.3, 3.1, 3.2_

- [ ] 4.2 Rename a page when its base changes, clean its old assets, and settle collisions
  - On a base change whose computed filename differs, rename the page to it;
    otherwise keep the filename (user renames and timezone changes as today)
  - On a rename, remove every chart asset the previous generated content
    linked that the new render does not write and no preserved region links;
    only single-component `assets/<name>.svg` links count
  - Write in the crash-healing order: new assets, stale assets removed, the
    document moved with a same-directory replace, the document written, archive
    copies last; route each step through one private helper so a test can
    inject a fault after any step
  - Report every rename as a warning naming both paths and the link and
    plan-override consequence; grow `SyncReport`'s warning-cause enumeration by
    one
  - After every file of a run, repeat the settle pass until no rename happens:
    a page written this run under a collision-suffixed name moves to its
    unsuffixed name when that name is free; `sync`, `drain` and `regen` all run
    it
  - Register a confinement entry (`sync-base-change`) whose run renames a page
    through a session-UUID re-export whose corrected start changes the name, and
    whose non-vacuity check requires one workout document deleted and another
    created
  - Tests (`tests/test_identity_e2e.py`, renames section): a re-export pair
    whose newer export corrects the start renames the page, removes the old
    assets, keeps a note written before, and warns once; a user-renamed page
    whose base does not change keeps its name; a note-region link to an old
    chart keeps that chart; two pages trading names in one run end unsuffixed;
    a fault injected after each write step leaves the page at one path and the
    next run completes the rename with no orphaned asset
  - Named mutations: skip the stale-asset removal; write the document before the
    move; remove assets linked from a preserved region; drop the settle pass;
    rename on every rewrite rather than on a base change
  - Observable: the full `uv run pytest` green; no workouts path is ever
    present twice in any fault-injection snapshot
  - _Requirements: 6.2, 6.4, 6.5, 6.6, 6.7_

- [ ] 4.3 Plan every `sync` run and hold what is ambiguous
  - Restructure `sync` into preparation (read, hash, skip archived or already
    seen, parse once, failures with today's reasons), one page scan, the
    planner, and tasks applied in first-member order; a task re-reads its files
    and fails a member whose bytes changed during the run
  - Apply group tasks (several new files to one page, rendered once) and hold
    tasks (upsert the record before archiving, archive, `skipped` plus a
    warning naming every candidate and the evidence); rewrite held candidates
    through the run's renames at the end; load the hold record before any write
    and let its error propagate
  - Report outcomes in discovery order; grow the warning-cause enumeration to
    eight and the skipped-bucket causes to three
  - Sweep the suite for corpora the rule now joins or holds and re-shape each
    so its premise holds, never by changing a tolerance: at least
    `tests/test_sync.py::test_name_collision_between_activities_disambiguates`
    (replace `reexport_a` with a genuinely different same-minute activity) and
    `tests/test_portability.py` (`run_native_power_sparse_hr` and `run_no_gps`
    get distinct data roots or starts); list every re-shaped test in the report
  - Tests (`tests/test_identity_e2e.py`, planned-sync section): a HealthFit copy
    and its Garmin original in one run and in two runs give one page; every
    permutation of original, partner copy and HealthFit copy, in one run and
    across three, gives a byte-identical tree; a file matching two pages is
    held, archived, recorded, warned and skipped, and a second sync skips it;
    two unlinked files claiming one page are both held; the default pinned end
    to end (maintainer decision 2026-09-29) -- a Stryd file and a HealthFit copy
    of one run take the HealthFit copy as base, a Garmin original and a
    HealthFit copy of one ride take the Garmin original as base -- and under
    `precedence=["original", "phone_copy", "unknown"]` the run's base becomes
    the Stryd file; a planned group claiming a page that records a newer
    document-format version leaves the page, its filename and its assets
    byte-unchanged and archives no member; with `save_holds` made to raise, the
    held file is not archived and the next run re-plans and holds it
  - Named mutations: decide per file against the corpus as it stands (the
    permutation test reds); archive a held file before recording it (the
    `save_holds` fault test reds); count a held file as a failure; apply the
    version gate after ranking or renaming (the newer-version test reds); swap
    the `original:garmin` and `phone_copy` default tiers (the ride pin reds)
  - Observable: `uv run pytest` green; the two-page ambiguity leaves both pages
    byte-unchanged and one entry in `.fitdocs/held.toml`
  - _Requirements: 2.5, 3.9, 3.10, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.11, 5.7, 6.8, 7.1, 7.5_
  - _Depends: 2.4, 2.5_

- [ ] 4.4 Plan every inbox drain the same way
  - After selection, settling, the probe read and the quarantine partition,
    prepare the admitted candidates from the probe bytes, plan, and apply
    tasks; per-candidate quarantine bookkeeping and the archive-presence
    disposition are unchanged, so a held candidate (archived) is moved under
    the move disposition and never quarantined
  - Load the hold record at the start of the drain, before the declaration
    refresh, so a damaged record raises before any write
  - `_process_isolated` keeps its name and is still called after the
    declaration refresh (`tests/test_drain.py:519-546`)
  - Carry the collision sweep: any test whose inbox corpus the rule now joins
    or holds is re-shaped (never a tolerance), outside this task's own files if
    need be, and listed in the report
  - Tests (`tests/test_identity_e2e.py`, drain section; `tests/test_drain.py`
    only where an assertion moves): a HealthFit page then a Garmin original
    dropped in the inbox joins and is moved; an ambiguous candidate is held,
    moved and absent from the quarantine record; a document-level failure in a
    group task is not quarantined; a damaged hold record raises before any write
    (the data root's snapshot is unchanged)
  - Named mutations: skip planning in the drain (the join test reds); quarantine
    a held candidate; load the hold record after the declaration refresh (the
    snapshot test reds)
  - Observable: the full `uv run pytest` green
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.11, 7.5_

- [ ] 4.5 Regenerate roles and re-evaluate held and unreferenced archives
  - After rebuilding every page, rescan, parse every archived file no page
    lists, plan them against the rebuilt pages, apply tasks without archive
    writes, save the hold record equal to exactly this run's holds (never
    reading the old record), and settle
  - Carry the collision sweep: unreferenced archives were rendered fresh before
    this task (`tests/test_sync.py:858-`), so any test whose regenerated corpus
    the rule now joins or holds is re-shaped (never a tolerance), outside this
    task's own files if need be, and listed in the report
  - Tests (`tests/test_identity_e2e.py`, regeneration section): deleting one of
    two duplicate pages and regenerating joins its files to the other and
    empties the hold; a damaged hold record is rebuilt; a precedence change
    re-bases and renames at regeneration; regeneration reproduces the synced
    tree byte for byte
  - Named mutations: skip held files in regeneration; merge with the old record
    instead of replacing it; render unreferenced archives fresh without planning
  - Observable: `uv run pytest` green; after the duplicate is removed and
    `regen` runs, `.fitdocs/held.toml` holds no entry
  - _Requirements: 4.10, 7.2, 7.3_

- [ ] 5. Surfaces: inspection and the CLI

- [ ] 5.1 (P) Report held, orphaned and duplicated sources in `fitdocs check`
  - Add the three finding kinds with design.md's subjects, details and
    remedies: one per held entry (or one naming an unreadable record), one per
    archived source no readable workout page lists and no hold names, one per
    page of each duplicate set built from the frontmatter the audit already
    parsed
  - List the archive; open no `.fit` file; write nothing
  - Update `fitdocs.audit`'s binding tuple
  - Tests (`tests/test_audit.py`): each finding with its subject and remedy; an
    unreadable record; a spy proving no `.fit` is opened and nothing written;
    exit status 1 with findings
  - Named mutations: count a held archive as orphaned; drop the shared-UUID link
    from duplicate sets; read the archived file to build a record
  - Observable: `fitdocs check` on a staged tree prints the three kinds and
    exits 1; `uv run pytest tests/test_audit.py tests/test_cli_check.py
    tests/test_contract_consumers.py` green
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - _Boundary: AuditIdentityFindings_
  - _Depends: 2.4, 2.5, 3.2_

- [ ] 5.2 (P) Load the precedence setting and map identity errors in the CLI
  - Load `[identity]` once per `sync` (both paths) and `regen` through a helper
    mirroring the tile-store helper, before any engine call; pass the precedence
    to `sync`, `drain` and `regen`; a hold-record error from `sync` or the drain
    becomes a configuration error naming the file and `fitdocs regen`
  - Tests (`tests/test_cli_identity.py`): a malformed table exits 2 and writes
    nothing; a configured precedence changes the base end to end; a damaged
    hold record exits 2 on `sync` and `fitdocs regen` then succeeds
  - Named mutations: skip passing the precedence to `regen`; load the settings
    after the engine call
  - Observable: `uv run pytest tests/test_cli_identity.py tests/test_cli.py`
    green; `uv run mypy tests/test_cli_identity.py` clean
  - _Requirements: 2.7_
  - _Boundary: CliIdentityWiring_

- [ ] 6. The published contract, the settings documentation and the spec records

- [ ] 6.1 Document the precedence setting and the upgrade step
  - Lands before 6.2 (not parallel): `tests/test_docs_guarantees.py:951-997`
    requires every cross-file `*.md#anchor` link in `docs/` to resolve, and the
    two tasks link each other's pages. This task creates the `[identity]`
    heading in `docs/configuration.md` that 6.2 links to with an anchor; every
    link this task writes to `docs/ownership-contract.md` is unanchored, because
    6.2's new section does not exist yet
  - `docs/configuration.md` gains `[identity]` (vocabulary, `original:<m>`
    entries, the default `original:garmin`, `phone_copy`, `original`, `unknown`
    as the maintainer decision of 2026-09-29, validation and exit status, and an
    example that lets every original outrank the phone copy);
    `docs/compatibility.md` adds `[identity]` to both table enumerations and
    advances the count by one from the branch's value, with
    `tests/test_compatibility_policy.py` in the same change;
    `docs/upgrading.md` states regenerate-before-first-pull; `docs/inbox.md`
    states that a held file is archived and disposed; `CHANGELOG.md`
    `[Unreleased]` names the document contract and settings changes with the
    action, referencing docs only by `https://github.com/joshua-stauffer/fitdocs/blob/main/...`
  - Tests (`tests/identity/test_settings_docs.py`): the documented default and
    vocabulary equal the code's
  - Named mutations: swap two tiers of the default precedence (the doc pin
    reds); drop `[identity]` from the compatibility list (its pin reds)
  - Observable: `uv run pytest tests/test_compatibility_policy.py
    tests/identity/test_settings_docs.py tests/test_changelog.py
    tests/test_docs_guarantees.py` green; `uv run mypy
    tests/identity/test_settings_docs.py` clean
  - _Requirements: 9.7, 9.8_

- [ ] 6.2 Publish the roles, renames and held files in the ownership contract and advance its version
  - Advance `CONTRACT_VERSION` by one with its docstring paragraph; update the
    contract document's version line and "What changed at this version"
  - Add the section "Source Files and Their Roles" (roles, kinds, the
    precedence pointer linked to 6.1's `[identity]` heading in
    `configuration.md` with its anchor, the four keys and the digest, UUID
    retention, the match rule with a tolerance table of value and measured
    source, held files and their resolution); the `.fitdocs/` bullet naming the
    hold record without an exhaustive claim; the `sync` and `regen` overwrite
    bullets; the rename order under Commit Ordering; the
    regenerate-before-pull note under Document-Format Versions. The managed-key
    list already carries the four keys (3.1) and does not move here. Where 6.1
    linked `ownership-contract.md` without an anchor, this task may add the
    anchor to the new section
  - Add the two declaration sentences (workouts: renames; archive: held files)
    with their claim anchors and no quantifier word; regenerate
    `tests/declaration_golden/*` with its own generator
  - Tests (`tests/identity/test_contract_docs.py`): the tolerance table's values
    and sources equal the constants and `TOLERANCE_SOURCES`, parsed from the
    document; `tests/test_ownership_contract.py`'s version pin moves with the
    doc
  - Named mutations: change one tolerance constant (the doc pin reds); break
    the anchor to `configuration.md`'s `[identity]` heading (the anchor test
    reds)
  - Observable: `uv run pytest tests/test_ownership_contract.py
    tests/test_declaration.py tests/test_declaration_goldens.py
    tests/identity/test_contract_docs.py tests/test_docs_guarantees.py` green;
    `uv run mypy tests/identity/test_contract_docs.py` clean
  - _Requirements: 3.11, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8_

- [ ] 6.3 Record the wiki-contract and workout-docs amendments and annotate the roadmap
  - wiki-contract: create Amendment 4's section if no sibling has, else append
    this spec's paragraph to it; Requirement 2 and Requirement 6 each gain the
    next free criterion, tagged `_(added by Amendment 4)_`; `design.md`'s
    `DocumentContract` gains an amendment note; `spec.json` an `amendments`
    entry
  - workout-docs: a note recording that Req 3.4's provenance is the base (the
    last `sources` entry) and that Req 3.6 is generalized by this spec's
    Requirements 3 and 4; no criterion renumbered or reworded; `spec.json`
    entry
  - Roadmap Phase 8 `#### Existing Spec Updates`: annotate the fit-ingest and
    wiki-contract entries with the parts landed here; tick a checkbox only if
    every part it names has landed on `main`
  - Observable: `/kiro-spec-status wiki-contract`, `fit-ingest` and
    `workout-docs` clean; the annotations name this spec
  - _Requirements: 9.1, 9.2, 9.6_

- [ ] 7. Validation: guards and the measured-shape scenarios

- [ ] 7.1 Pin the identity package's boundary and surfaces
  - `tests/identity/test_boundary.py`: the package's import closure per module
    (allowed and forbidden targets from the hard rules, alias forms included),
    only `pages` and `holds` touching the filesystem, only `kinds` and `pages`
    importing the contract, no clock name; a positive control that the walk
    scanned every module
  - `tests/test_public_api.py`: `_IDENTITY_SURFACE` asserts the package marker
    re-exports nothing and no identity name is re-exported from the root
  - `pyproject.toml` `[tool.mypy].files` gains every typed test and fixture
    module the earlier tasks created and type-checked clean; if registering one
    surfaces an error, its creating task's observable was false -- report it
    rather than editing that module here
  - Named mutations: add an `import fitdocs.sync` to `planning.py` (the closure
    reds); add a `Path.write_text` to `roles.py` (the filesystem pin reds)
  - Observable: `uv run mypy` and `uv run pytest tests/identity/test_boundary.py
    tests/test_public_api.py` green
  - _Requirements: 1.1, 3.10, 9.2_

- [ ] 7.2 Prove the queue item's case and the measured shapes end to end through the CLI
  - `tests/test_identity_e2e.py`, CLI section: a data root with HealthFit-style
    pages (one shifted by two hours) gains the Garmin-style originals through
    `fitdocs sync` from the inbox -- one page per session, the shifted page
    renamed to the original's start, old assets gone, the copies' UUIDs kept,
    `fitdocs check` clean; the partner copy arriving later changes nothing but
    `sources`; the two-10 k pair stays two pages; an ambiguous file shows in the
    report and in `fitdocs check`, and `fitdocs regen` resolves it after the
    duplicate page is deleted
  - Run the full validation: `uv run pytest && uv run ruff check . && uv run
    ruff format --check . && uv run mypy`
  - Observable: all green; the report lists the named mutations run by every
    task and their outcomes
  - _Requirements: 3.5, 4.8, 5.7, 6.2, 6.4, 7.3, 8.1, 8.5_
