# Implementation Plan

## Upstream Prerequisites

- **No upstream implementation prerequisite.** Every spec this plan builds on
  has shipped: `inbox` (selection, stability check, quarantine, dispositions,
  the drain), `sync`, `settings-foundation` (the per-table reader shape),
  `wiki-contract` (owned `.fitdocs/`, the confinement guard, the ownership
  contract), `route-maps` (the tile seam and its User-Agent), `plugin-api`
  (the registry shape mirrored here), `distribution` (the packaged skill and
  its pins).
- **This plan is the prerequisite of `intervals-connector`**, which must not
  start until this plan is merged to `main`: it implements the protocol,
  transport and credential store exactly as design.md states them. A task
  here that finds it must change a published shape (anything in
  `fitdocs.connectors.__all__`, the ledger or credentials file format, the
  environment-variable naming) stops and reports rather than changing it.
- **Sibling specs in flight** (`activity-identity`, `running-dynamics`,
  `channel-merge`, `docs-site`): see design.md "Cross-spec seams" and
  "Shared-file touches". Task 8.1 applies the contract-version rule; task 7
  adds the one `docs/index.md` row (append-only; rebase and keep a peer's row).

## Hard rules for every task

- **No network in tests, no real credentials.** `tests/connectors/conftest.py`
  (task 1.1) patches `socket.socket` to raise for every test in the package,
  points `FITDOCS_CREDENTIALS_DIR` and `HOME` at per-test temporary
  directories, and deletes `XDG_CONFIG_HOME` and every `FITDOCS_CONNECTOR_*`
  variable; a connector test outside that directory (task 6.3) applies the
  same isolation locally. Every test reaches the transport through
  `FakeTransport` or a patched `urllib.request.urlopen`. No test, fixture, doc or comment names an online
  service's endpoint; fixtures are synthesized (`tests/fixtures/builder.py`
  bytes, synthetic connectors). No personal data.
- **No new runtime dependency** (`tests/test_determinism.py:672-712`,
  `tests/test_packaging.py:503-519` stay green).
- **Module direction** (design.md "Allowed Dependencies" and "Dependency
  Direction"): a connectors module imports only leftward, only
  `fitdocs.layout`, `fitdocs.settings`, `fitdocs.inbox`, `fitdocs.version`
  from the rest of the package, and no third-party package except
  `tomli_w` (an existing runtime dependency), which only
  `connectors/ledger.py` and `connectors/credentials.py` import. Only
  `connectors/http.py` imports `urllib.request`/`urllib.error`. No clock
  call inside the package — `now` and `sleep` are injected.
- **No link to the connectors page before task 7.** Every docs URL in
  `README.md`, `CHANGELOG.md`, `src/fitdocs/**/*.py` or a `SKILL.md` must be
  a declared `[project.urls]` value (`tests/test_packaging.py:263-285`) and
  must exist on disk (`tests/test_install_docs.py`), and `Connectors` is
  declared only in task 7. No task before 7 links the connectors page;
  tasks 7, 8.2, 8.3 and 8.4 add the links.
- **Files this plan must not edit**: `src/fitdocs/plugins.py`, anything under
  `src/fitdocs/{render,load,metrics,ingest,plans,history,performance}/`,
  `src/fitdocs/inbox.py`, `src/fitdocs/quarantine.py`. `src/fitdocs/sync.py`
  is edited only in its module docstring's "Offline guarantee" paragraph
  (`:41-52`, task 6.2). `src/fitdocs/contract.py` only in `CONTRACT_VERSION`
  and its docstring (task 8.1).
- **Every new assertion owes a named mutation** it dies on, run through
  `uv run pytest` and reverted (`change-protocol.md` § Fixture
  Discrimination); each task below names its mutations. Fixtures must violate
  the property the code establishes (unsorted ledgers, permissive modes,
  secrets that would appear if unredacted).
- **Counts in prose move with the sets they count** (training-blocks WARN):
  `cli.py`'s "Nine commands" (`:5`) and `tests/test_cli_skill.py:266`, the
  "six tables" at `docs/configuration.md:51`, `docs/compatibility.md:24, 64`
  and `tests/test_compatibility_policy.py:270`, and the skill tests' channel
  counts are each moved by the task that grows the set.

## Shared files inside this plan

- `src/fitdocs/connectors/__init__.py`: created by 1.1 (docstring, empty
  surface), filled by 2.3 (the 46 published names), and given exactly one
  import-and-register line for the folder connector by 4.2. No other task
  edits it.
- `tests/connectors/conftest.py`: 1.1 (socket guard and environment
  isolation), 2.1 (`FakeTransport`),
  2.3 (registry snapshot/restore and the synthetic connectors every later
  test uses). Tasks 3.1 onward add no fixture there; they keep helpers local to
  their own test module, so parallel tasks never share it.
- `src/fitdocs/cli.py`: 1.4 (drain helper), 5.1 (`connect`), 5.2 (`pull`),
  5.3 (`--sync`), 6.2 (network paragraph). Sequential.
- `pyproject.toml`: 1.1 (`[tool.mypy].files` gains `tests/connectors`), 7
  (`[project.urls]` gains `Connectors`).
- `tests/connectors/test_docs.py`: created by 7, extended by 8.2 only.
- `README.md` and `docs/configuration.md`: 6.2 (network sentences) before
  8.2/8.3 (the rest). Sequential by group.

- [ ] 1. Foundation: the package's leaves, the User-Agent, the ledger path, and the shared drain helper

- [ ] 1.1 Scaffold the connectors package and its test package, isolate every connector test from the network and the developer's credentials, and add the secret type and the redactor
  - Create the package with a module docstring stating its boundary and an
    empty published surface; create the test package with its module marker
    and a conftest with two autouse fixtures: constructing a socket raises;
    and a plain helper (importable by task 6.3) the second fixture calls,
    which points `FITDOCS_CREDENTIALS_DIR` and `HOME` at per-test temporary
    directories (outside any sandbox data root a test builds) and deletes
    `XDG_CONFIG_HOME` and every `FITDOCS_CONNECTOR_*` variable; add
    `tests/connectors` to the mypy `files` list
  - The secret value: its text form, representation and formatted form show
    only the redaction marker; its value is read only through an explicit
    reveal; equal by value; a non-string value is rejected
  - The redactor: registers values (ignoring the empty string) and their
    percent-encoded forms, and replaces every registered value in a text,
    longest first
  - Pins: a secret inside an f-string, a `repr`, and an exception message
    never contains its value; a redacted text containing a value and its
    percent-encoded form shows neither; inside an ordinary test, constructing
    a socket raises and `FITDOCS_CREDENTIALS_DIR` names an existing
    temporary directory; a pin sets `FITDOCS_CONNECTOR_X_API_KEY` and
    `XDG_CONFIG_HOME` with `monkeypatch`, calls the helper, and finds both
    gone and `FITDOCS_CREDENTIALS_DIR` and `HOME` under the test's temporary
    directory
  - Named mutations: make the secret's `__repr__` return the value (the
    repr pin reds); drop the percent-encoded registration (the encoded pin
    reds); remove the `FITDOCS_CONNECTOR_*` deletion from the isolation
    helper (the isolation pin reds)
  - Observable: `uv run pytest tests/connectors` green over
    `test_secrets.py` and `test_isolation.py`; `uv run mypy` green with
    `tests/connectors` in scope
  - _Requirements: 10.1, 10.2, 10.3_

- [ ] 1.2 Add the typed failures with their next steps, and the atomic writer
  - The failure vocabulary: the six authentication-failure kinds, the
    authentication failure (kind, the service's message, an optional
    retry-after), the instance-ending connector error, the not-connected
    error, the connector settings error (key, message); the next-step table
    for each kind with its instance-name and retry placeholders, and the
    function that renders one
  - The atomic writer: a dot-prefixed temporary file in the target's
    directory, flushed and synced, replaced over the target, removed on any
    failure; the resulting file readable and writable only by its owner
  - Pins: each next step names the instance and, for rate-limited with a
    known wait, the wait (and no wait when unknown); a failing write leaves
    no temporary file and the old target intact; a written file's mode is
    `0o600`; the temporary name begins with a dot
  - Named mutations: render the rate-limited step without the wait (its pin
    reds); remove the cleanup in the writer's failure path (the no-temp pin
    reds)
  - Observable: `uv run pytest tests/connectors/test_errors.py
    tests/connectors/test_atomic.py` green; `uv run mypy` green
  - _Requirements: 4.3, 5.6_

- [ ] 1.3 (P) Define the one fitdocs User-Agent in the version leaf, delegate the tile fetcher to it, and add the ledger path to the layout leaf
  - The version leaf gains the project URL constant and a User-Agent
    composed at call time from the display version and that URL; the tile
    fetcher's own User-Agent function returns it, so there is one
    definition
  - The layout leaf gains the connector-state directory under the tool-state
    directory and the per-instance ledger path; the tool-state directory's
    docstring names the ledger as its second tenant; the owned-path set is
    unchanged
  - Pins (in `tests/test_version_identity.py` and `tests/test_layout.py`,
    since `tests/connectors/` is being created in parallel by 1.1 and 1.2):
    the
    composed agent equals the literal format with a patched version; it
    degrades to the unknown token; the tile fetcher's agent is the same
    string; the ledger path for an instance; `OWNED_PATHS` unchanged
  - Named mutations: cache the agent at import (the patched-version pin
    reds); give the tile fetcher its own literal (the same-string pin reds)
  - Observable: `tests/test_tiles.py` green unchanged (it patches
    `fitdocs.version.version`), `tests/test_version_identity.py` green (no
    import-time metadata read), `tests/test_layout.py` and the new pins green
  - _Requirements: 7.1, 9.1_
  - _Boundary: VersionUA, LayoutPaths_

- [ ] 1.4 (P) Extract the no-source drain of `fitdocs sync` into a helper both `sync` and a later `pull --sync` call
  - Move the body of `sync_command`'s no-source branch (`cli.py:340-374`:
    plugin discovery, the inbox preflight, the drain, the drain report, the
    load pass, the plan pass, plugin errors) into one helper taking the data
    root, timezone, athlete inputs, force, retry-quarantined, no-prompt and
    the report's command label, and returning whether anything failed;
    `sync_command` calls it and then exits as before
  - No behavior change: same output bytes, same exit codes, same order of
    configuration errors
  - Named mutations: drop the plan pass from the helper
    (`tests/test_cli_reconcile.py::test_sync_drain_chains_the_pass_and_prints_reconciled`
    reds); drop the drain's per-file failures from the returned flag
    (`tests/test_cli_sync_inbox.py::test_drain_with_a_genuine_failure_exits_one`
    reds)
  - Observable: the whole existing suite green with no test edited, in
    particular `tests/test_cli_sync_inbox.py`, `tests/test_cli_reconcile.py`,
    `tests/test_drain.py`, `tests/test_inbox_e2e.py`
  - _Requirements: 12.1, 12.3_
  - _Boundary: CliCommands_

- [ ] 2. The published protocol: transport, vocabulary, registry

- [ ] 2.1 Build the transport and the HTTP client with the explicit User-Agent, the timeout, the bounded data-call retries and the single authentication attempt
  - The request and response values; the transport error whose message
    names only scheme, host and path (or the signed-location marker); the
    transport seam type; the standard-library transport: ordinary headers
    plus the User-Agent, credential headers added so a redirect never
    carries them, the timeout, a body read capped at the maximum size,
    error statuses returned as responses, network failures as transport
    errors
  - The client in two modes: authentication (exactly one call, any status
    returned) and data (at most three calls on a network failure or a
    retryable status, waiting the service's stated wait when within the
    maximum, else the backoff sequence; a stated wait beyond the maximum
    stops retrying); the User-Agent always replaces a caller's; secret
    header values and a secret URL are registered with the redactor before
    the first call; the status-to-failure helper (401, 403, 429 with its
    wait, 5xx)
  - Add the scripted fake transport to the test conftest (queued responses
    or errors; records every request and timeout)
  - Pins: authentication mode makes one call on 429, 503 and a network
    error; data mode makes three calls on persistent 503 and sleeps 2 then
    4; `Retry-After: 7` sleeps 7; `Retry-After: 120` returns after one
    call; 401 and 403 are never retried; the sent agent is the composed one
    even when the caller passes another; the transport's `Request` carries
    the credential header only among unredirected headers, the agent among
    ordinary headers, and the timeout; an error status becomes a response;
    a body one byte over the cap raises; a failure message carries no query
    string
  - Named mutations: route authentication mode through the retry loop (the
    one-call pin reds); `range(2)` for the attempt count (the three-call
    pin reds); add the credential with `add_header` (the unredirected pin
    reds); keep the query in the error message (the message pin reds)
  - Observable: `uv run pytest tests/connectors/test_http.py` green with
    the socket guard active; `uv run mypy` green
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 10.4_

- [ ] 2.2 Declare the capability and authentication vocabularies and the protocol's value types and protocols
  - The nine capabilities with their summaries and flags (the three
    remote-changing members irreversible, every other member reversible,
    only pulling activities driven); the four authentication styles with
    browser consent reserved; credential fields; the listed activity with
    absent values as `None`; the listing and its deferrals; the three fetch
    answers; granted scopes; token sets; the settings context; the
    credential-access protocol; the session value with its secret-wrapping
    method; the connector protocol and the three optional-operation
    protocols exactly as design.md states them
  - Pure declarations: no I/O, no clock
  - Pins: exactly nine capabilities in declaration order; exactly the three
    remote-changing members irreversible; exactly one driven member; exactly
    four styles and one reserved; a listed activity's unset optional fields
    are `None`; a session's secret method registers the value with its
    redactor; a minimal typed stub in `test_protocol.py` assigned to
    `Connector`- and `ActivityPuller`-typed names, so mypy checks the
    protocols in this task
  - Named mutations: mark resolve-remote-activity irreversible (the flag pin
    reds); add a second driven member (the driven pin reds); default a
    duration to `0.0` (the absent pin reds)
  - Observable: `uv run pytest tests/connectors/test_protocol.py` green;
    `uv run mypy` green, the stub checked against the protocols
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

- [ ] 2.3 Add the registry with its validation gate, publish the package surface, and add the synthetic connectors every later test uses
  - Register, unregister, look up and list connectors by id; validate a
    declaration in the order design.md states without calling any
    operation, never raising for a malformed object; reject a duplicate id
    keeping the incumbent and naming the id; an unknown id names every
    registered id
  - Fill the package's published surface with exactly the 46 names
    design.md lists, and pin it (equality, no duplicates, identity with
    each defining module)
  - Conftest: a fixture snapshotting and restoring the registry around every
    test; typed synthetic connectors — personal-key, login-style (login and
    refresh), and a scriptable puller — reused by every later task
  - Pins: one rejection per violated member, each with its own reason; a
    connector whose operations raise still validates; a reserved capability
    or the reserved style requires no operation; duplicate and unknown
    messages; unregistering an unknown id is a no-op
  - Named mutations: skip the "none style declares no fields" rule (its
    rejection pin reds); call `parse_settings` during validation (the
    raising-operations pin reds); drop a name from `__all__` (the surface
    pin reds)
  - Observable: `uv run pytest tests/connectors/test_registry.py
    tests/connectors/test_surface.py` green; `uv run mypy` green with the
    synthetic connectors typed against the protocols; `import
    fitdocs.connectors` exposes 46 names; `src/fitdocs/plugins.py` has no
    diff
  - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [ ] 3. State: credentials, ledger, settings

- [ ] 3.1 (P) Build the credential store: its location order, its refusal inside the data root, owner-only atomic files, environment overrides, and token replacement
  - Resolve the directory from the dedicated variable (absolute, else a
    location error), then an absolute configuration-home variable, then the
    home default; refuse a directory that is or lies inside the data root;
    name each instance's file; build environment-variable names
  - Save creates the directory owner-only and writes the file atomically,
    owner-only; load returns nothing for an absent file, refuses a file
    other users can access (naming the permission fix), a malformed file,
    or a newer format
  - Resolve an instance's credentials: none style has no values; personal
    key takes each field from a non-empty environment variable first,
    else the store, and a missing field is not-connected naming the connect
    command and the variables; login style reads only the store and its
    replacement saves the new token set before returning; credentials issued
    for another connector are not-connected; every value is registered with
    the redactor
  - Pins: each location branch with the variables set, unset and relative;
    the data-root refusal; modes `0o700` and `0o600` after save; a `0o644`
    file refused; environment beats store (fixture where the two differ); a
    login-style store never holds the typed answers; a replacement is on
    disk when `replace` returns; absent scopes stay absent; a foreign
    connector id is not-connected
  - Named mutations: swap environment and store precedence (the precedence
    pin reds); skip the mode check (the `0o644` pin reds); drop the
    data-root check (the refusal pin reds)
  - Observable: `uv run pytest tests/connectors/test_credentials.py` green;
    `uv run mypy` green
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_
  - _Boundary: CredentialStore_

- [ ] 3.2 (P) Build the ledger: its entries and invariants, the watermark that never moves backward, and its versioned, sorted, write-if-different file
  - The three outcomes; an entry per remote id with revision, content hash,
    reason and pending location, with the invariants design.md states; the
    ledger value with lookup, the final-outcome test for an id at a
    revision, replacement, removal, the pending entries, and a watermark
    setter that never moves backward
  - Load: absent file is an empty ledger for the expected connector and
    creates nothing; unreadable, invalid, mis-shaped, duplicated, invariant
    breaking, newer-format or foreign-connector files raise the ledger error
    naming the file. Save: entries sorted by remote id, absent fields
    omitted, no clock value, skipped when the bytes are unchanged, the
    directory created on demand, atomic
  - Pins: a round trip; an unsorted in-memory ledger saves sorted (fixture
    deliberately unsorted); a second save returns `False` and leaves the
    file's mtime; each malformed shape raises; a foreign connector raises;
    absent file creates no directory; the watermark setter refuses to move
    back; revision `None` equals `None` and differs from a string
  - Named mutations: drop the sort (the unsorted pin reds); drop the
    write-if-different check (the mtime pin reds); let the watermark move
    backward (its pin reds)
  - Observable: `uv run pytest tests/connectors/test_ledger.py` green;
    `uv run mypy` green
  - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6, 7.8_
  - _Boundary: Ledger_

- [ ] 3.3 Read the connectors table into validated instances
  - Project the table from the already-parsed settings document: absent is
    no instances; each sub-table is an instance named by its key; the
    connector defaults to the name and is resolved through the registry;
    the look-back is a whole number of days within range, defaulting to 30;
    a key named like a credential field is refused with the
    credentials-belong-elsewhere message; the connector validates the rest
    through its settings parser with the settings context, its own errors
    wrapped naming the key and anything else wrapped naming the connector;
    two instances sharing a credential variable are refused naming both;
    instances returned sorted by name
  - Every error is a settings error naming the file, the instance and the
    key; the reader reads no file and writes nothing
  - Pins: absent table; defaulted connector; each malformed key; a
    `bool` look-back rejected; the credential-key refusal; a collision
    between `a-b`/`c` and `a`/`b_c`-shaped pairs; unknown keys ignored;
    parser errors wrapped with the key; sorted output from unsorted
    sub-tables
  - Named mutations: accept `True` as a look-back (its pin reds); skip the
    collision check (its pin reds); stop defaulting the connector to the
    name (its pin reds)
  - Observable: `uv run pytest tests/connectors/test_settings.py` green;
    `uv run mypy` green
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [ ] 4. Delivery, the folder connector, and the two engines

- [ ] 4.1 Deliver bytes into the inbox atomically and sweep archived deliveries
  - The FIT-header check; the delivery-name rule (hint or remote id, last
    path component, sanitized, stem capped, `.fit` ensured); delivery into
    the instance's subdirectory of the inbox (created on demand) under the
    primary name, reusing an identical file already there, escalating to
    content-derived names when a different file holds it, written through
    the atomic writer so the temporary name is dot-prefixed, bytes
    unchanged
  - The sweep over the pending entries, with the six outcomes design.md
    states (removed, released, settled, unchanged, forgotten, removal
    failed), hashing a pending file only when its bytes are archived
  - Pins: the header check on a valid file, a 12-byte header, a non-FIT
    payload and a short payload; the name table; collision escalation;
    identical reuse writes nothing; the temporary file's name begins with a
    dot and never ends in `.fit`; the delivered bytes equal the input; each
    sweep outcome with a fixture where the asserted state is false before
    the sweep (a pending file present before removal, an entry present
    before it is forgotten)
  - Named mutations: remove without checking the hash (the released pin
    reds); remove when the archive copy is absent (the unchanged pin reds);
    use `os.replace` over an existing different file instead of escalating
    (the collision pin reds)
  - Observable: `uv run pytest tests/connectors/test_delivery.py` green;
    nothing is removed that the ledger does not record as pending
  - _Requirements: 6.7, 6.8, 8.1, 8.2, 8.3, 8.5, 8.6, 8.7, 8.8_

- [ ] 4.2 (P) Build the folder connector and register it as the built-in connector
  - Its declaration (id `folder`, no authentication, pulls activities, no
    credential fields); its settings parser (required path resolved against
    the data root and normalized without filesystem access, refused when it
    equals, lies inside or contains the inbox, naming both; optional settle
    interval defaulting to the inbox's; unknown keys ignored)
  - Listing: a missing source is a connector error naming it; candidates by
    the inbox's own selection rules, settled through the session's sleep;
    unstable files are deferrals; each stable file listed by its
    source-relative path with a size-and-modification-time revision and its
    basename as the suggested name, no start, sport or duration
  - Fetching: a read failure or a revision that changed during the read is a
    deferral; otherwise the bytes
  - Add the one import-and-register line to the package `__init__`
  - Pins: the three overlap refusals; a relative path resolves against the
    data root; dot-prefixed and junk files are not listed; a file changing
    across the settle interval is deferred (fake sleep that grows the file);
    an unreadable file is deferred; the source tree's snapshot is identical
    before and after listing and fetching; `get("folder")` returns it after
    a fresh import
  - Named mutations: list without the dot-component rule (its pin reds);
    ignore the settle result (the deferral pin reds); drop the overlap check
    for "contains" (its pin reds)
  - Observable: `uv run pytest tests/connectors` green with the socket guard
    active — the whole package, because registering the folder connector at
    import changes the registry every earlier registry and settings test
    sees
  - _Requirements: 2.1, 13.1, 13.2, 13.3, 13.5, 13.6, 13.7, 13.8, 13.9_
  - _Boundary: FolderConnector, PackageInit_

- [ ] 4.3 Orchestrate one pull: listing, classification, fetch answers, delivery, the ledger's watermark, and saving on every exit
  - The pull options, notes, delivered records, per-instance report and pull
    report exactly as design.md states, the run failing on any instance
    error or failed note; channels sorted
  - Per instance, in design.md's order, for connectors that need no
    credentials (task 4.4 adds credentials): load the ledger (an unusable
    ledger is the instance's error); sweep (not under dry run); refuse a
    connector that does not pull activities; the window start (the
    override, else the watermark less the look-back, else none); list and
    validate each entry (an invalid or repeated entry is a failed note;
    listing deferrals are deferred notes); classify each entry in
    start-then-id order — held, unavailable (recorded skipped), would-fetch
    under dry run, else fetched: deferred, declined (recorded skipped),
    not-FIT (recorded skipped with its hash), already held against the
    archive or a pending delivery including one made earlier in this run
    (recorded), or delivered (recorded with its pending location); advance
    the watermark over the contiguous prefix of final start-bearing entries;
    save the ledger in a `finally` (not under dry run), re-raising an
    interrupt after saving
  - Pins (folder connector and the scriptable puller, socket guard): a
    second pull over unchanged sources fetches nothing and leaves the ledger
    byte-identical; a file unreadable on the first pull is delivered by the
    second; a changed file is fetched again; archived bytes are held and not
    delivered; two remote ids with identical bytes deliver once; non-FIT
    bytes are skipped and not delivered; an unavailable entry is recorded
    skipped; the window start with no watermark, with one, and with the
    override; a deferred entry blocks the watermark at its start; an
    interrupt after one delivery leaves it recorded on disk; dry run leaves
    the sandbox snapshot unchanged and reports would-fetch; entries in each
    channel sorted from an unsorted listing
  - Named mutations: decide "new" from the listing instead of the ledger
    (the second-pull pin reds); save the ledger only on success (the
    interrupt pin reds); advance the watermark past a deferred entry (its pin
    reds); drop the pending-hash check (the identical-bytes pin reds)
  - Observable: `uv run pytest tests/connectors/test_pull.py` green;
    `uv run mypy` green
  - _Requirements: 1.9, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.12, 6.13, 7.2, 7.4, 7.7, 8.5, 11.5, 13.4_

- [ ] 4.4 Give the pull its credentials, its token renewal, its failure isolation, and its redaction
  - Resolve each instance's credentials through the store and the
    environment; a not-connected instance is the instance's error carrying
    the next step; a login-style token expiring within the margin is renewed
    through an authentication-mode session and replaced — on disk before
    any data request, and also under dry run
  - An authentication failure or connector error from renewal, listing or a
    fetch ends that instance with its kind's next step; any other fetch
    exception or transport error is a failed note and the instance
    continues; a listing exception ends the instance
  - Every reported string passes the run's redactor; exceptions are
    reported as type and redacted message, never a traceback
  - Pins (synthetic personal-key and login-style connectors, fake
    transport): not-connected names the connect command and the variable;
    an expired token is renewed and the credentials file already holds the
    new token when the fake transport sees the first data request; renewal
    happens under dry run and nothing else is written; one instance's
    authentication failure does not stop the next; one item's exception
    does not stop its instance; a connector error quoting the key is
    reported with the marker and without the key; a `Declined` reason and an
    `unavailable_reason` quoting the key are saved in the ledger redacted,
    and a byte scan of every file under the sandbox's data root (ledger,
    inbox, archive) after the pull finds no registered secret
  - Named mutations: persist the renewed tokens after listing (the on-disk
    pin reds); treat an item's `TransportError` as instance-ending (the
    isolation pin reds); skip redaction of connector reasons (the redaction
    pin reds); store the raw reason in the ledger entry's detail (the
    ledger-redaction and byte-scan pins red)
  - Observable: `uv run pytest tests/connectors/test_pull.py` green;
    `uv run mypy` green
  - _Requirements: 4.7, 6.10, 6.11, 10.1, 10.2, 10.5_

- [ ] 4.5 (P) Make one authentication attempt at connect and store only on success
  - The connected and connect-failed results; wrap every answer as a secret
    registered with the redactor; one authentication-mode session; a
    personal-key connector's verification then a store of the answers and
    granted scopes; a login-style connector's login then a store of only the
    token set; an authentication failure or a transport error becomes a
    connect-failed result with the redacted message and the kind's next
    step, storing nothing; a successful connect replaces an existing file;
    the variables that will override stored values are reported
  - Pins: exactly one request for each failure kind (fake transport
    scripted with 429, 401, 403, 503 and a network error); nothing stored on
    failure; the stored personal-key file holds the answers and scopes; the
    stored login-style file holds the tokens and not the password; the
    service message quoting the key is redacted; a second connect replaces
    the first file
  - Named mutations: store before verifying (the nothing-stored pin reds);
    persist the login answers (the password pin reds); build a data-mode
    session (the one-request pin reds on 503)
  - Observable: `uv run pytest tests/connectors/test_connect.py` green;
    `uv run mypy` green
  - _Requirements: 4.6, 4.8, 5.5, 5.6, 5.7, 5.8, 10.2_
  - _Boundary: ConnectEngine_

- [ ] 5. The commands

- [ ] 5.1 Add `fitdocs connect`
  - The command and its module-level seams (transport, terminal check,
    secret prompt, visible prompt); the data root, settings, inbox
    validation without creation, and connectors table read, each failure a
    configuration error; an unknown name lists the configured instances;
    the none style prints nothing-to-connect and exits `0`; the reserved
    style exits `2`; the credentials-directory checks; a non-terminal exits
    `2` naming the environment variables for a personal-key connector; each
    field prompted, secret fields through the no-echo prompt; an empty
    answer exits `2` before any request; the connect engine's result printed
    (instance, path, scopes or "the service reported no scopes", overriding
    variables; or the kind, the redacted message, the next step) with exit
    `0` or `1`
  - Set the application's crash handler to never print local variables
  - No message, docstring or help text links the connectors page (task 7
    declares it)
  - The command count becomes ten: `cli.py`'s opening sentence and
    `tests/test_cli_skill.py:266` move together, and the docstring gains the
    `connect` bullet
  - Pins (`CliRunner`, seams patched, socket guard): each configuration
    error's exit `2` and message; the secret field read through the no-echo
    seam and its value absent from the output; success output and a
    `0o600` file; each failure kind's output and exit `1` with no file;
    nothing written under the data root (sandbox snapshot); the app's
    show-locals setting is false
  - Named mutations: prompt a secret field through the visible prompt (its
    pin reds); exit `0` on a failed connect (its pin reds); enable
    show-locals (its pin reds)
  - Observable: `uv run pytest tests/connectors/test_cli_connectors.py
    tests/test_cli_skill.py` green; `fitdocs connect --help` lists the
    argument
  - _Requirements: 1.7, 3.9, 4.2, 5.1, 5.2, 5.3, 5.4, 5.9, 10.6_

- [ ] 5.2 Add `fitdocs pull` with its preflight, its report, its dry run, and its exit codes
  - The command with instance names, `--since`, `--dry-run`, `--sync` and
    `--no-prompt` declared (the chaining itself is task 5.3; until then
    `--sync` is accepted and validated, and 5.3 makes it act); the preflight
    in design.md's order, every failure a configuration error before any
    request or write (data root, the `--sync`/`--dry-run` conflict, the
    `--since` date, settings, inbox validation, connectors table, unknown
    names, the credentials-directory checks when a selected instance
    authenticates); the inbox created only when not a dry run; the
    no-connectors message
  - The pull report printed as design.md states: the inbox line or the
    dry-run line, one always-complete table per instance, then the detail
    blocks; exit `1` when the pull failed, else `0`
  - The command count becomes eleven (`cli.py:5` "Eleven",
    `tests/test_cli_skill.py:266`); the docstring gains the `pull` bullet
    and the exit-code paragraph's new cases; no link to the connectors page
  - Pins (`CliRunner`, folder source, patched transport seam, socket
    guard): each preflight error's exit `2` with the sandbox unchanged;
    unknown names listed; no connectors configured exits `0`; every table
    row present with zero counts; one failing and one healthy instance:
    the healthy one delivered, exit `1`; deferral-only exits `0`;
    `--dry-run` writes nothing and lists would-fetch; `--sync --dry-run`
    exits `2`
  - Named mutations: create the inbox under dry run (the snapshot pin
    reds); exit `0` when an instance failed (its pin reds); omit a
    zero-count row (the rows pin reds)
  - Observable: `uv run pytest tests/connectors/test_cli_connectors.py
    tests/test_cli_skill.py` green; `fitdocs pull --help` lists the five
    options
  - _Requirements: 3.9, 4.2, 6.1, 6.2, 6.3, 6.9, 8.4, 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 5.3 Chain the drain after the pull with `--sync`
  - Under `--sync`, the preflight also checks the athlete profile, the
    plugins table, the tiles table and the quarantine record (the checks the
    drain path makes before its first write); after the pull report, the
    drain helper from 1.4 runs labeled `pull`, even when an instance
    failed and even when no connector is configured (no early return),
    honoring `--no-prompt`; the exit is `1` when the pull or the chained
    passes failed
  - Pins: `--sync` produces workout documents from delivered files and
    prints the drain table after the pull table; a malformed `[plugins]`
    table under `--sync` exits `2` with no request made (the fake
    transport records none); a failing instance still drains; a chained
    load failure exits `1`; `--no-prompt` reaches the load pass; a second
    `--sync` run reports the first run's deliveries removed; with no
    `[connectors]` table, `pull --sync --no-prompt` prints the
    no-connectors line and then the drain table, writes the same workout
    documents a `sync --no-prompt` over the same inbox writes (compared in
    two sandboxes), and exits by the drain's outcome (`0`, and `1` with a
    per-file failure in the inbox)
  - Named mutations: run the drain before the pull report (the ordering pin
    reds); skip the drain when an instance failed (its pin reds); validate
    `[plugins]` only inside the helper (the no-request pin reds); return
    early when no instance is configured (the no-connectors pin reds)
  - Observable: `uv run pytest tests/connectors/test_cli_connectors.py
    tests/test_cli_sync_inbox.py` green
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ] 6. Guards and true network statements

- [ ] 6.1 (P) Guard the package boundary and confine network code to two modules
  - The four layers design.md states: each module's *direct* (not
    transitive) non-stdlib imports — `fitdocs.*` targets and third-party
    top-level names, stdlib decided by `sys.stdlib_module_names` — pinned by
    equality per module, `tomli_w` appearing only in `ledger.py`'s and
    `credentials.py`'s sets, with the directory enumerated both ways; the
    forbidden-name scan (the forbidden `fitdocs.*` modules and any
    third-party name other than `tomli_w` in its two modules), including
    `from X import y` forms; the tree-wide network allow-list over
    `src/fitdocs/` naming only the tile module and the connector transport;
    the clock scan over the package
  - Positive controls: the tree-wide scan finds both allowed modules and more
    than a hundred files; the closure test fails on a synthetic module
    importing the render package; the network scan fails on a synthetic
    module importing `socket`
  - Named mutations: add `import urllib.request` to `connectors/pull.py`
    (the allow-list reds); import `fitdocs.sync` in `connectors/pull.py`
    (the forbidden scan reds); add `import yaml` to `connectors/pull.py`
    (the forbidden scan reds on the third-party rule); call `datetime.now`
    in `connectors/credentials.py` (the clock scan reds)
  - Observable: `uv run pytest tests/connectors/test_boundary.py` green;
    each named mutation reds its named layer (the `fitdocs.sync` and `yaml`
    mutations also red the layer-1 equality pin, which pins every direct
    import)
  - _Requirements: 1.9, 2.8, 14.2, 14.3_
  - _Boundary: BoundaryGuard_

- [ ] 6.2 (P) Rewrite every network statement to name the connector commands and pin it
  - Rewrite `cli.py`'s network paragraph (`:98-102`), `sync.py`'s
    "Offline guarantee" paragraph (`:41-52`, adding that the engine makes
    no connector request), `tiles.py:7`, `:246` and `:407` (the tile code
    and the connector transport are the two network modules), the
    configuration page's network sentences (`docs/configuration.md:72-74,
    92-93`: tiles and the connector commands, and how to switch each off)
    and `README.md:66`
  - Pin in a new statements test: none of these retired phrases appears
    (whitespace collapsed) in `src/fitdocs/**/*.py`, `README.md` or
    `docs/*.md` — "Network access is confined to :mod:`fitdocs.tiles`"
    (`cli.py:98`); "That is the *only* network access" (`sync.py:44`);
    "**only** network-touching code" (`tiles.py:7`); "The only
    network-touching code in the package" (`tiles.py:246`); "The package's
    only network call" (`tiles.py:407`); "the only time fitdocs touches the
    network" (`README.md:66`); "the *only* time fitdocs touches the network"
    (`docs/configuration.md:73-74`). Exact phrases only, so the true
    statements the plan must not edit (`load/engine.py:32`,
    `audit.py:10-14`, `docs/contributing-calculators.md:466`,
    `docs/plugins.md:26`) stay green. Positive half: each rewritten place
    names both the map tiles and `fitdocs pull`
  - No rewritten statement links the connectors page (task 7 declares it)
  - Named mutations: restore `README.md:66`'s old sentence (the retired
    phrase pin reds); drop `fitdocs pull` from the configuration page's
    paragraph (the positive pin reds)
  - Observable: `uv run pytest tests/connectors/test_network_statements.py
    tests/test_install_docs.py tests/test_docs_guarantees.py
    tests/test_packaging.py tests/test_tiles.py` green
  - _Requirements: 14.4_
  - _Boundary: NetworkStatements_

- [ ] 6.3 (P) Register `pull` with the write-confinement guard and prove `connect` writes only its credentials file
  - A staging function writing a settings file with the inbox and one
    folder instance whose path is the sandbox's source directory; a run
    function driving the settings, inbox, connectors reader, inbox creation
    and the pull engine with a transport that raises if called; a
    non-vacuous predicate requiring the instance's ledger and at least one
    delivered file; the `pull` entry point registered, with a registration
    test
  - A connect test: a synthetic personal-key connector, a transport
    answering success, the credentials directory inside the sandbox but
    outside the data root; the sandbox's touched set is exactly the
    credentials directory and file
  - The test doubles (the synthetic personal-key connector,
    `FakeTransport`) and the environment-isolation helper are imported as
    plain objects from `tests.connectors.conftest`; that conftest's autouse
    fixtures do not reach this module, so both connector cases call the
    helper themselves and patch `socket.socket` to raise
  - Named mutations: drop the `pull` registration (the registration test
    reds); have the pull write a report file at the data root (the guard
    reds); save the credentials under the data root (the connect test reds)
  - Observable: `uv run pytest tests/test_confinement.py
    tests/test_effort_tags_e2e.py` green; the parametrized guard shows a
    `pull` case
  - _Requirements: 5.9, 13.5, 15.3_
  - _Boundary: ConfinementRegistration_

- [ ] 7. Write the connectors page, link it from the documentation index and the project URLs, and pin it service-neutral
  - `docs/connectors.md` with every subject design.md lists (the instance
    table and its keys, the folder connector, connecting, the credentials
    directory order, modes, variables and the login-style limitation, the
    pull and its options and report channels, delivery and removal, the
    ledger, what leaves the machine and how to switch it off, the
    terms-first policy, the duplicate-page caution while identity has not
    shipped, a cron/launchd example); no protocol names documented
  - One `docs/index.md` row (append-only; keep a peer's row on rebase);
    `[project.urls]` gains `Connectors`; `_REQUIRED_ENTRY_POINT_LINKS` gains
    the page
  - A new docs test: the page's headings; the look-back default equals the
    code constant; every variable name it shows is what the naming function
    produces; a service-neutral scan over the connectors package, its tests
    and the page (every URL is the project's own or a reserved example
    host)
  - Named mutations: change the documented look-back default (its pin
    reds); add an external URL to a connectors test (the neutral scan reds);
    drop the index row
    (`test_documentation_entry_point_links_every_required_page` reds)
  - Observable: `uv run pytest tests/connectors/test_docs.py
    tests/test_docs_guarantees.py tests/test_packaging.py` green
  - _Requirements: 14.6, 15.5_

- [ ] 8. Contracts, documentation, and the packaged skill (four independent documents)

- [ ] 8.1 (P) Publish the credential, ledger and command statements in the ownership contract and apply the contract-version rule
  - The `.fitdocs/` bullet names the connector ledgers, keeping `.fitdocs/`
    its first backticked token; a shared-and-user-owned bullet for the
    credentials store outside the data root; `[connectors]` in the
    settings-file bullet; overwrite-semantics bullets for `pull` and
    `connect`
  - The contract-version rule: read `CONTRACT_VERSION` on the rebased
    branch; if it equals the latest release's value (`"4"`, 0.1.0), advance
    it by one, add its docstring line, update the document's version line,
    and regenerate the declaration goldens; if a sibling already advanced it
    since that release, keep it and append this spec's changes to the "What
    changed at this version" paragraph only
  - Add this spec's part of wiki-contract Amendment 4: criteria on the
    published-ownership-contract requirement taking the next free numbers,
    appended to the Amendment 4 block if a sibling created it, else creating
    the block titled for the joint landing; the design note and the
    amendments entry in that spec's metadata
  - Named mutations: add `.fitdocs/connectors/` as its own list item (the
    owned-paths equality pin reds); leave the document's version line behind
    the code (`test_contract_version_matches_code` reds)
  - Observable: `uv run pytest tests/test_ownership_contract.py
    tests/test_declaration.py tests/test_declaration_goldens.py
    tests/test_contract.py` green; `/kiro-spec-status wiki-contract` clean
  - _Requirements: 15.1, 15.2, 15.6_
  - _Boundary: ContractVersion, OwnershipContractDocs_

- [ ] 8.2 (P) State the delivery-removal carve-out and the seventh settings table in the inbox, configuration and compatibility pages
  - `docs/inbox.md`: the opening bold sentence keeps "fitdocs performs no
    watching and no scheduling of any kind" and says delivering files is
    the athlete's concern unless a connector is configured; the disposition
    policy keeps both pinned sentences and adds the carve-out paragraph
    design.md states
  - `docs/compatibility.md`: the inbox item and subsection name the
    carve-out; "six tables" becomes "seven tables" at both places, adding
    `[connectors]`; `docs/configuration.md`: "six" becomes "seven", a table
    row and a short section pointing at the connectors page, and the
    data-root paragraph's command list gains `connect` and `pull`
  - Tests: `SETTINGS_TABLE_LITERALS` gains `"[connectors]"`, the "six" test
    name and messages become "seven"; the docs test gains the carve-out pin
    (the three statements present on the inbox page and the pinned
    never-delete sentences still present)
  - Named mutations: delete the carve-out paragraph (its pin reds); leave
    `[connectors]` out of the compatibility subsection
    (`test_settings_schema_subsection_names_all_seven_tables` reds)
  - Observable: `uv run pytest tests/test_compatibility_policy.py
    tests/test_install_docs.py tests/test_docs_guarantees.py
    tests/connectors/test_docs.py` green
  - _Requirements: 8.9, 15.4, 15.6_
  - _Boundary: InboxDocs, CompatibilityDocs, ConfigurationDocs_

- [ ] 8.3 (P) Update the README, the wiki-integration page and the changelog
  - `README.md`: `:31`'s ingest line names connectors; `:113`'s skill
    summary names the pull; a short `## Connectors` section linking the
    connectors page by project URL; a "Learn more" bullet
  - `docs/wiki-integration.md`: the `fitdocs-workouts` summary line names
    the pull
  - `CHANGELOG.md` `[Unreleased]`: the Added and Changed entries design.md
    lists, each naming the contract and the user action; the ownership
    entry names the new statements and no contract-version number, so it is
    right whichever Amendment 4 part (8.1 here, or a sibling spec) advanced
    the value — this task does not depend on 8.1's decision
  - Named mutations: link the connectors page by a relative path from the
    README (`test_shipped_and_emitted_doc_references_use_project_urls`
    reds); add a non-canonical category (the changelog test reds)
  - Observable: `uv run pytest tests/test_changelog.py
    tests/test_install_docs.py tests/test_docs_guarantees.py
    tests/test_packaging.py tests/test_wiki_integration_docs.py` green
  - _Requirements: 15.8_
  - _Boundary: ReadmeAndIndex, ChangelogEntry_

- [ ] 8.4 (P) Teach the packaged skill the pull and move its pins
  - The skill's description, commands section (the routine fence exactly
    `fitdocs pull --sync --no-prompt` then `fitdocs check`; the no-connector
    equivalence; the retry-quarantined instruction unchanged; never run
    `fitdocs connect`), the pull-channel table with the eight rows and their
    Do cells, and the further-reading link, all as design.md states; no
    owned path spelled
  - Tests: the routine-fence pin becomes pull-and-check; the profile gains
    the pull-channel literal, pinned against the per-instance report's
    fields minus the three exclusions (with a non-vacuity check on the
    exclusions); the binding test over the `Pull channel` table; the
    `error` row's Do cell pin; the block-skill docstring's stale "fences
    sync" sentence corrected
  - Named mutations: fence `fitdocs sync --no-prompt` instead (the routine
    pin reds); drop the `would_fetch` row (the binding pin reds); remove
    "never run `fitdocs connect`" from the error row (its pin reds)
  - Observable: `uv run pytest tests/test_agent_skill.py
    tests/test_skill_wheel.py tests/test_packaging.py` green
  - _Requirements: 15.7_
  - _Boundary: PackagedSkill, SkillPins_

- [ ] 9. Records and validation

- [ ] 9.1 Record the steering rules and the other specs' amendments
  - `.kiro/steering/tech.md`: the network-and-credentials subsection;
    `.kiro/steering/structure.md`: the connectors dependency line; a grep of
    steering and `CLAUDE.md` for contradicted network statements, each moved
  - Amendment records, each with a `spec.json` amendments entry and no
    renumbering: `inbox` Amendment 1 (Req 6.1 and 6.6 are the drain's
    guarantees; the pull's removal of its own archived deliveries);
    `distribution` Amendment 3 (Req 8.1, 8.2 and 10.4); `route-maps` (Req
    4.2)
  - Roadmap Phase 8 Existing Spec Updates: tick `distribution` "landed by
    connectors"; add a ticked `inbox` line "landed by connectors"; tick
    `wiki-contract` only when the other two Amendment 4 parts are on `main`,
    otherwise append "(connectors part landed)"
  - Observable: `/kiro-spec-status inbox`, `distribution`, `route-maps` and
    `wiki-contract` clean; the steering grep for "only network" and
    "fully offline" finds no contradicted statement
  - _Requirements: 14.7_

- [ ] 9.2 End-to-end pull and drain, offline commands under the socket guard, and the whole-suite gate
  - An end-to-end test over a synthetic folder source and a synthetic
    personal-key connector behind the patched transport seam: `fitdocs pull
    --sync --no-prompt` delivers, drains into workout documents and exits
    `0`; the next run removes the archived deliveries and fetches nothing;
    a hand-dropped file in the same inbox is never removed
  - With `[connectors]` configured and constructing a socket patched to
    raise: `sync`, `regen`, `load`, `check`, `history`, `plan` and
    `derive-benchmarks` each complete as before
  - The frozen dependency tests, the confinement guard, the boundary guard
    and the surface pin unchanged and green
  - The exhaustive sweep: every acceptance criterion classified PINNED
    (test and mutation), PRESERVED-ONLY (existing test) or UNPINNED (with
    the mutation run that proves it), recorded in the task's report
  - Named mutations: have `sync` import and call a connector (the offline
    test reds); remove a hand-dropped file in the sweep (the hand-drop pin
    reds)
  - Observable: `uv run pytest && uv run ruff check . && uv run ruff format
    --check . && uv run mypy` green; `/kiro-spec-status connectors` clean
  - _Requirements: 8.5, 8.9, 12.1, 14.1, 14.5_
