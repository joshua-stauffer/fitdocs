# Implementation Plan

Streams after the foundation group (1.x):
- **page contract**: tasks 2.x (sequential: one contract module);
- **connector framework**: tasks 3.x;
- **composition**: tasks 4.x;
- **state and input**: tasks 5.x.

Delivery and orchestration (6.x) and the CLI (7.x) join them; contract
documentation, the skill, the docs and the amendments (8.x) follow; the
validation group (9.x) closes.

Every task leaves the full suite, ruff, ruff format and mypy green on its
own. Every new assertion names the mutation it dies on (`tech.md`,
Testing); run the named mutations before reporting a task done.

Shared, append-only files: the publish package's import-boundary registry
(task 1.3) and the contract-consumer registry
(`tests/test_contract_consumers.py`) gain one entry per module task; two
parallel tasks append distinct entries and never edit each other's. The
shared test fixtures (`tests/publish/conftest.py`: page builders and the
scripted publishing connector) are created by task 6.1; until then each (P)
task keeps its page builders local to its own test module.

Version constants: `DOC_VERSION` (task 2.3) and `CONTRACT_VERSION` (task
8.1) each take one more than their value on `main` at landing (12 and 18 if
this spec lands first). The CLI command count (task 7.1) also takes main + 1
at landing (16 if this spec lands first), because relay-server adds a
command too. The documentation site (`website/content/`) is never edited
(controller ruling R9); `.kiro/queue/2026-10-31-publish-core-site-copy.md`,
written with this spec, holds its copy. Every version-history pin is written as the landed
literals ("Raised from `11` to `12`"), appended, and never derived from the
live constant.

- [ ] 1. Foundation: the shared leaves and the package guard

- [ ] 1.1 Add the publish package and its outcome vocabulary
  - Create the publish package as a marker that imports nothing, and the
    `tests/publish` test package; add `tests/publish` to the type checker's
    file list so later test stubs are checked against the protocols they
    implement.
  - Add the closed vocabulary of 35 codes in the design's order (the 35th,
    `local_record_unreadable`, is a target code: a failure, not landed, not
    stopping), each with
    its fixed one-sentence explanation and its five flags (landed, failure,
    may come from a target, stops the target, a listing state), plus the
    derived code sets and the explanation lookup.
  - The module imports only the standard library.
  - Tests pin, as literals: the 35 values in order (a prefix pin, so
    appending stays free); each flag set; that every explanation is one
    sentence ending in a full stop with no brace; that the codes a target may
    return exclude every offline, core-assigned and listing-only code.
  - Tests prove the module can be carried alone: its syntax tree imports
    only standard-library modules, and importing it in a fresh interpreter
    loads no `fitdocs` module other than the package root and the publish
    package.
  - Done when the vocabulary tests pass and die on: swapping two members;
    renaming a value; flipping one flag; adding a `fitdocs` import to the
    module; adding an import to the package marker.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 1.2 Add the publish request and result values
  - Add the post (title, description), the completed-activity subject, the
    publish request (publication id, post, subject, recorded link) and the
    publish result (one code, an optional link), as frozen plain values.
  - Add the one link rule (an `https` link with a host, bounded length, no
    whitespace, control character or markdown-breaking character) and the
    one label rule (non-empty, bounded, no control character or bracket).
  - The module imports only the standard library and the vocabulary; the
    fresh-interpreter isolation test covers it too.
  - Done when the value and rule tests pass, including the boundary cases of
    each rule (length limits exactly at and one past the bound, each
    refused character), and die on loosening any one refused character.
  - _Requirements: 9.3, 9.4, 12.3_

- [ ] 1.3 Guard the publish package's boundary
  - Add a boundary test modelled on the connectors guard:
    - each publish module's direct non-standard-library imports pinned by
      equality against a hand-written registry, with the registry checked
      against the package directory in both directions;
    - a forbidden-name scan (rendering, load, metrics, ingestion, sync,
      index, query, dashboards, identity, and every network-capable
      standard-library module);
    - a scan for clock reads and randomness spellings, so `now` and the
      publication-id source stay injected.
  - Seed the registry with the two leaves from 1.1 and 1.2; each later
    module task appends its own entry.
  - Done when the guard passes over the two leaves and its positive controls
    catch a synthetic module importing the render layer, a socket, a clock
    call and a random-token call.
  - _Requirements: 6.1, 7.5_

- [ ] 2. Page contract: the `publish` key and the two regions

- [ ] 2.1 Add the contract readers publishing needs
  - Add the `publish` key constant and its reader: an absent key or an
    empty list reads as no targets; one non-empty name or a list of distinct
    non-empty names reads as those names; anything else reads as an invalid
    key with a fitdocs-written reason. The reader never raises.
  - Add the summary reader for the page's title, distance, moving time,
    average heart rate and power, elevation gain and calories: a genuine
    finite non-negative number (never a boolean) or `None`; moving time only
    from `h:mm:ss` or `m:ss`.
  - The key is not yet user-owned; nothing else in the contract changes.
  - Add each new public name (the key constant, the two readers and their
    two result types) to the contract surface pin
    (`tests/test_public_api.py`, `_CONTRACT_SURFACE`).
  - Done when reader tests cover every accepted and refused shape and die on
    accepting a boolean, a duplicate name, an empty name, or a moving time
    with minutes over 59.
  - _Requirements: 2.1, 5.2_

- [ ] 2.2 Make the `publish` key user-owned
  - Add the key to the user-owned set through a documentation-order tuple
    (the four effort keys, then `publish`); the workouts declaration lists
    user-owned keys from that tuple.
  - Update the pins that hold the user-owned set equal to the effort keys:
    the set is now the effort keys plus `publish`, and stays disjoint from
    the managed keys and from every key the frontmatter builder can emit.
  - Add `publish` to the published contract's "User-Owned Frontmatter
    Keys" list, which `tests/test_ownership_contract.py:294` holds equal to
    the user-owned set, and the documentation-order tuple to the contract
    surface pin.
  - Regenerate the workouts declaration golden (its tuple-driven user-key
    sentence).
  - Done when tests show a `publish` line, including a multi-line list
    value and a malformed value, is carried byte-for-byte through `sync`,
    `sync --force`, `regen` and the load pass, and is never named by the
    unmanaged-key warning or the `check` finding; the pins die on dropping
    `publish` from the set.
  - _Requirements: 2.1, 2.2, 2.8, 13.3, 13.7_

- [ ] 2.3 Render the `post` and `published` regions on every workout page
  - Add the two region ids, the `post` region's hidden-comment placeholder
    and the empty `published` placeholder; `post` joins the user-owned
    regions and `published` the refreshed regions; the preserved regions
    become notes, workout, post, load, still in document order.
  - Render the `published` region directly after the title and attribution
    line, and the `post` region directly before the `morning` region, in
    the run/ride, strength and generic views, with no heading.
  - Advance `DOC_VERSION` to one more than its value at landing, with an
    appended history paragraph naming this spec and the two regions.
  - Regenerate every golden document and the workouts declaration golden
    (its tuple-driven region list); update the region-tuple pins, the
    declaration's region checks and the merge tests' preserved-region loop;
    add the four region constants to the contract surface pin. The
    declaration's sentence about the `published` region lands with 8.1.
  - In the published contract, the lists held equal to the tuples move in
    this task: `post` joins "User-Owned and Tool-Filled Regions"
    (`tests/test_ownership_contract.py:130-133`), a "The Published Region"
    section joins "The Morning-Of Region", and the refreshed-region pin
    (`:136-138`) is rewritten to hold the union of both sections' lists
    equal to the refreshed regions.
  - Move every literal pin of the current document-format version,
    appending, never deriving from the constant:
    `tests/metrics/test_sources.py:2270`,
    `tests/render/test_frontmatter.py:45` and
    `tests/morning/test_e2e.py:394, 400, 454`. Rewrite
    `tests/test_local_time_docs.py:46`, which derives `(DOC_VERSION - 1,
    DOC_VERSION)` from the constant, to the literal `(10, 11)` of the
    changelog line it reads; leave that changelog entry unchanged.
  - Done when:
    - goldens show both regions in each view's stated position, and an
      empty `published` region renders as nothing;
    - a page written at the previous version, regenerated, gains both
      regions in their fresh form and keeps its notes, workout, load and
      user-owned keys byte-for-byte; regenerating twice is byte-identical;
    - the index render fingerprint is unchanged by edits inside either new
      region (it blanks preserved and refreshed regions);
    - the pins die on placing `post` after `morning` and on leaving
      `published` out of the refreshed regions.
  - _Requirements: 3.1, 12.1, 13.2, 13.3, 13.5, 13.6, 13.7_

- [ ] 3. Connector framework: the target contract and single-attempt writes

- [ ] 3.1 (P) Add the single-attempt request mode
  - A request marked single-attempt is sent to the transport exactly once,
    whatever the status or network failure, in data and authentication
    modes; the post helper takes the marker as an optional keyword.
  - Unmarked data requests keep their bounded retries; authentication
    requests stay single.
  - Done when transport-seam tests with a scripted transport show one call
    for a marked request answered 429, 503, or a transport failure, in both
    modes, and three calls for the same unmarked data request; the marked
    tests die on removing the guard, and the existing retry tests pass
    unchanged.
  - _Requirements: 10.1, 10.2_
  - _Boundary: ConnectorChanges (transport only)_

- [ ] 3.2 (P) Drive the publish capabilities through the publish operation
  - Mark push-activity, annotate-remote-activity and resolve-remote-activity
    driven, keep their remote-change and irreversible marks, keep the four
    other reserved capabilities undriven, and name the three as the publish
    capabilities.
  - Add the publish operation protocol (a fixed link label and one publish
    operation over a session and a request), with the target obligations
    from the design in its docstring.
  - Registration rejects, naming the problem: resolve or push declared
    without annotate; a publish capability declared without a callable
    publish operation or with a label that fails the label rule.
  - Append the protocol, the capability set, the four request and result
    value types, and the outcome code type and the set of codes a target may
    return (R11) to the published surface. All six re-exported names go
    through the protocol module, which imports the value types from the
    request leaf and the two code names from the vocabulary leaf, so the
    package module imports them from the protocol and its own boundary
    entry (`tests/connectors/test_boundary.py:277`) is unchanged. Connector
    target modules import these names from the protocol, never from the
    publish package.
  - Move the surface count pins (`tests/connectors/test_surface.py:127,
    158`) by eight as literals at landing; admit the request and vocabulary
    leaves in the protocol module's boundary pin and the request leaf in the
    registry module's; update the package docstring's allowed-import
    sentence.
  - Move the two tests that assume the three are undriven:
    `tests/connectors/test_wellness_protocol.py:176-195` keeps only the four
    capabilities still reserved, and
    `tests/connectors/test_registry.py:573-576`'s capability that needs no
    operation becomes push-planned-workout.
  - Done when registry tests cover each rejection and an accepted publishing
    connector, the capability tests pin the driven set as a literal, and the
    boundary and surface pins pass; the registry tests die on dropping the
    annotate requirement or the label check.
  - _Requirements: 9.1, 9.2, 9.5, 9.6, 9.7, 9.8, 9.9_
  - _Boundary: ConnectorChanges (protocol, registry, surface)_
  - _Depends: 1.2_

- [ ] 4. Composition: templates, values and posts

- [ ] 4.1 (P) Build the template grammar
  - Parse templates left to right into text, placeholders and optional
    clauses: `{{` and `}}` escapes, `{name}` placeholders checked against a
    given name set, `{?...}` clauses holding at least one placeholder and no
    clause; every other brace is a syntax error with a 1-based line, column
    and fitdocs-written reason.
  - Render: the first bare placeholder without a value is reported as
    missing; a clause with any placeholder lacking a value renders nothing;
    values are inserted literally and never re-parsed.
  - Add the pair of title and description templates a target uses.
  - Done when grammar tests cover `{?{x}}`, `{?{x}}}}`, a lone brace, a
    nested clause, a clause without a placeholder, an unknown name and
    whitespace inside braces, each with its position, and rendering tests
    die on a clause rendered with an absent value or on an absent value
    rendered as `0`.
  - _Requirements: 4.4, 4.5, 5.7_
  - _Boundary: TemplateGrammar_

- [ ] 4.2 (P) Produce placeholder values from a page
  - Publish the 17 placeholder names in the design's order and produce each
    as fixed-format text from the contract readers only, or `None`.
  - Derive miles, pace (run modality only) and speed (bike modality only)
    only from present, positive inputs; a recorded zero renders as zero.
  - Format durations with the same rule as the render layer's duration
    formatter, held equal by a table test, without importing the render
    layer.
  - Register the module with the contract-consumer guard and the boundary
    registry; keep its page builders local to its own test module.
  - Done when value tests cover each placeholder present, absent, malformed
    and zero, and die on: a missing distance rendered `0.00`; pace computed
    for a ride; a boolean read as a number.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: PlaceholderValues_
  - _Depends: 2.1_

- [ ] 4.3 Compose posts and read the post region
  - Read the `post` region: normalize line endings, remove hidden comments
    (an unclosed one is invalid), drop leading and trailing blank lines;
    nothing left means no override; otherwise the first line is the title,
    a second line must be blank, and the rest is the description.
  - Turn an override into templates (a syntax error or unknown placeholder
    is an invalid-template refusal naming title or description and the
    position).
  - Compose a post from a target's templates and the page's values:
    normalized single-line title, description with normalized line endings,
    no leading blank lines and no trailing whitespace; an empty title and a
    missing bare value are refusals with their codes.
  - Compute the post digest over exactly the title and description.
  - Done when composition tests cover title-only regions, CRLF, comments
    inside the title line, a missing blank line and an unclosed comment;
    identical inputs compose identical bytes; and the digest tests die on
    including anything but the title and description.
  - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.7, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5_
  - _Boundary: Composer_

- [ ] 4.4 (P) Read the `[publish]` settings and ship the built-in default
  - Ship the built-in default title and description templates from the
    design, parsed against the placeholder names.
  - Read `[publish]` and `[publish.targets.<name>]`: per target and per
    field, the target's own template, then the table-wide one, then the
    built-in default.
  - Refuse, naming the settings file, the table and the key (and for a
    template the position and reason): a non-table, an unknown key, a
    non-string value, a title template with a newline, a template error, and
    a target table naming something that is not a configured publish
    target.
  - Done when settings tests cover the resolution order and each refusal,
    and rendering the built-in default templates with only `title` given a
    value yields that title and an empty description (dies on a default
    clause left bare).
  - _Requirements: 4.1, 4.2, 4.3, 4.6, 4.8_
  - _Boundary: PublishSettings_
  - _Depends: 4.1, 4.2_

- [ ] 5. State and input: the ledger, the published region and pages

- [ ] 5.1 (P) Keep the publish ledger
  - Add the ledger location under the tool-owned state directory, one file
    per target, and the page key for a workout page (`workout:` and the
    file digest).
  - Load every ledger file present plus an empty ledger for each configured
    target without one; reading creates nothing; refuse, naming the file,
    an unreadable file, invalid TOML, a wrong shape, a newer version, a
    ledger identity other than the target's (its connector id), and every
    violated invariant from
    the design; never rewrite a ledger it refused.
  - Save sorted by page, omitting absent fields, atomically and only when
    the bytes change.
  - Match records to a page by its source digests.
  - Done when ledger tests cover a round trip, each refusal, an unknown
    appended code string read as text, and an unchanged save leaving the
    file's bytes and modification time untouched; they die on saving
    unsorted or on accepting a record with a link and no label.
  - _Requirements: 10.3, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.8_
  - _Boundary: PublishLedger_
  - _Depends: 1.2_

- [ ] 5.2 (P) Render and splice the published region
  - Build the region's content from a page's recorded links: empty with no
    link, otherwise `Published:` and each `[label](link)` joined by the
    separator, in target-name order.
  - Replace only the `published` region's inner content of a page's text,
    leaving every other byte, the `post` region included, unchanged; a page
    without the region is reported, never given one.
  - Register the module with the contract-consumer guard and the boundary
    registry; keep its page builders local to its own test module.
  - Done when tests show the line format and ordering, that a splice of a
    page changes only the region (byte comparison outside it), and they die
    on reordering targets or touching the `post` region.
  - _Requirements: 3.8, 12.2, 12.4, 12.5_
  - _Boundary: PublishedRegion_
  - _Depends: 1.2, 2.3_

- [ ] 5.3 (P) Select and read pages
  - Select every top-level workout page in file-name order, or the named
    ones: a bare name in `workouts/` with or without `.md`, or a path from
    the working directory to a file directly in `workouts/`; refuse a name
    that resolves to nothing, a symlink, a file elsewhere or a page that is
    not a workout page; collapse duplicates.
  - Read a page's state (current, older, newer, damaged with the region
    error, or a current page missing either new region).
  - Build the completed-activity subject only when the page records its
    sport and a start time with its offset; take elapsed time and distance
    from the base-identity keys, the source digests in rank order, and the
    base file's archive path when it is a file.
  - Index every workout page's source digests, so one digest in several
    pages is detectable.
  - Register the module with the contract-consumer guard and the boundary
    registry; keep its page builders local to its own test module.
  - Done when page tests cover each selection form and refusal, each state,
    each subject absence, and a shared digest found in two pages; they die
    on accepting a symlink or a naive start time.
  - _Requirements: 6.6, 7.2, 7.3, 7.8, 11.7_
  - _Boundary: PageReader_
  - _Depends: 1.2, 2.1, 2.3_

- [ ] 6. Delivery and orchestration

- [ ] 6.1 Prepare targets and send to them safely
  - Treat a connector instance as a publish target when its connector
    declares annotate-remote-activity.
  - List targets with their state (ready, not connected, unreadable
    credentials) from credential resolution alone, never showing a value
    and making no request.
  - Prepare a target: resolve its credentials (not connected and unreadable
    credentials become codes, with no request) and build a data-mode
    session as the pull does.
  - Send one request: any exception, a non-result answer or a code a target
    may not return becomes the target-failure code with no exception text
    kept; a link is kept only with a landed code and only when valid, and a
    refused link is flagged; an interrupt propagates.
  - Create the shared test fixtures: page builders (moving the local
    builders of 4.2, 5.2 and 5.3 here where they coincide) and the scripted
    publishing connector, registered for a test and unregistered after it,
    type-checked against the publish protocol.
  - Done when tests show a target raising an exception that carries a
    sentinel string yields the target-failure code and the sentinel appears
    in no field of the result, and die on keeping a link with a non-landed
    code.
  - _Requirements: 1.6, 8.6, 8.7, 12.3, 14.1, 14.2, 14.5_
  - _Depends: 3.2_

- [ ] 6.2 Run the decision and the dry run
  - Over the selected pages and targets, in order: refuse unreadable named
    pages, invalid opt-ins, unknown target names, older, newer and damaged
    pages, pages without activity facts, conflicting ledger records, and
    every composition refusal, each with its code and fitdocs detail; count
    pages that opt in to no considered target, and list a named one as not
    opted in.
  - Decide would-post, would-update or unchanged from the ledger's landed
    digest, and keep each would-post or would-update post for the report.
  - A dry run makes no request and writes nothing.
  - Done when engine tests over a temporary data root show each refusal
    path, each decision, and an unchanged file tree (names, bytes and
    modification times) after a dry run; they die on a dry run that creates
    the ledger directory.
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 7.5, 7.6, 7.7, 7.8, 11.7, 12.6, 13.5_

- [ ] 6.3 Post, record and refresh the published region
  - For each would-post or would-update pair: open the target on first use
    (a preparation code applies to that pair and stops the target); mint and
    save a publication id before the first request; send; record the code,
    the time, the landed digest and a kept link with its label; save the
    ledger before the next request.
  - A stopping code stops that target only; its remaining pairs are not
    attempted.
  - Rewrite each considered current page's published region from every
    ledger whenever its content differs, whatever the page's current
    opt-in; report a failed rewrite with its code; never write an older or
    newer page or the `post` region.
  - Done when engine tests with the scripted target show:
    - a second posting run sends nothing and leaves ledger and pages
      byte-identical;
    - an edited post region or template produces an update;
    - the scripted target reads the saved publication id from the ledger
      file during its call, and an interrupted attempt's id is reused;
    - an unconfirmed result is not counted as landed and is sent again
      next run;
    - a rate-limited target stops while a second target continues;
    - links from two targets appear in target-name order, a hand edit to
      the region is replaced, and a page that stopped naming a target keeps
      its link.
  - _Requirements: 1.6, 2.7, 3.8, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 10.3, 10.4, 10.5, 12.2, 12.5, 12.7, 12.8_

- [ ] 6.4 (P) Render run reports and target listings
  - Text: the run's mode line, one line per page and target with its code
    (and fitdocs detail), the post indented for would-post and would-update,
    the link for a posted pair, the counts by code, the not-opted-in count,
    and each printed code's explanation once.
  - JSON: the versioned shapes from the design for runs and listings, with
    counts and explanations in vocabulary order.
  - Done when report tests pin both shapes against literals and die on
    reordering a key or omitting an explanation.
  - _Requirements: 1.6, 7.9, 7.10, 8.10, 14.1, 14.6_
  - _Boundary: Report_
  - _Depends: 6.2_

- [ ] 7. The `fitdocs publish` command

- [ ] 7.1 Add `fitdocs publish` with its preflight and exit codes
  - Arguments and options: PAGES, repeatable `--to`, `--yes`, `--targets`,
    `--format text|json`, `--out`; the publish package is imported lazily,
    pinned by a test that importing the CLI loads no publish module other
    than the package marker, the vocabulary and the request leaf (the CLI
    imports the connector protocol at load, which imports the request
    leaf).
  - Move the command-count pins to the literal main + 1 at landing (16 if
    this spec lands first): `tests/test_cli_skill.py:266` and its count
    word at `:268`, `tests/query/test_cli_query.py:811`,
    `tests/index/test_cli_index.py:609`, and the count word in the CLI
    module docstring.
  - Preflight in the design's order, each failure exiting 2 before any
    request or write, naming what to fix; credentials directory checked only
    when posting to an authenticating target.
  - Run with the real clock, a random publication-id source and the real
    transport; exit 0 or 1 by the report's failure codes; print that no
    publish target is configured when that is so and no page opts in;
    exit 130 on an interrupt with every received outcome kept.
  - Done when CLI tests cover each preflight refusal (nothing written), the
    exit codes 0, 1, 2 and 130, and a dry run and a posting run through the
    scripted target in text and JSON.
  - _Requirements: 4.6, 4.8, 7.1, 7.3, 7.4, 7.10, 7.11, 8.9_

- [ ] 7.2 Add the target listing
  - `--targets` lists every configured publish target in text or JSON,
    reading the credentials store only for state; it refuses PAGES, `--to`
    and `--yes`; with no target it says so and exits 0.
  - Done when CLI tests cover each state, the refusals, the empty case, and
    that no credential value and no request appear (the scripted transport
    records no call).
  - _Requirements: 4.8, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [ ] 8. Contract, skill, documentation and amendments

- [ ] 8.1 Advance the ownership contract
  - Raise `CONTRACT_VERSION` to one more than its value at landing, with an
    appended history paragraph naming the two regions, the `publish` key,
    the ledger location, `[publish]` and `fitdocs publish`'s writes.
  - In the published ownership contract (the region and key lists already
    moved with 2.2 and 2.3): the version head; the ledger under the
    tool-owned state; `[publish]` among the shared files; a `publish` entry
    in the overwrite semantics (it writes only ledgers and `published`
    regions); "What Regeneration Replaces and Preserves" naming the
    `published` region as generated content the merge carries; the
    document-format version history.
  - The workouts declaration gains its sentence naming the `published`
    region as generated content refilled from the publish ledger.
  - Regenerate the declaration goldens and move every literal version pin
    with its pinned paragraph (the contract-docs, retimed-rename,
    asset-write, index contract-docs and derived-preserved tests).
  - Done when the contract docs tests, declaration goldens and every
    version pin pass at the new value.
  - _Requirements: 13.1, 13.3, 13.4_
  - _Depends: 2.2, 2.3, 7.1_

- [ ] 8.2 (P) Write the skill's publishing section
  - Add the section and the "When this applies" bullet from the design to
    the workouts skill: several configured publish targets, named by none;
    `fitdocs publish --targets`; the `publish` key and the `post` region
    with placeholders and clauses; the dry run; `--yes` only when the
    athlete asked; reading codes, telling the athlete about failures, never
    running `fitdocs connect`; the publishing documentation link.
  - Update the skill's heading profile; add a scan that fails on any
    service, platform or brand name in the section (a literal list
    including both Phase 14 services and the relay's host); check every
    code it names is a vocabulary value; the existing command and option
    binding guard covers the new spans.
  - Done when the skill tests pass and the new scan dies on inserting a
    service name.
  - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_
  - _Boundary: SkillSection_
  - _Depends: 7.2_

- [ ] 8.3 (P) Write the publishing reference
  - A contract-grade publishing page: command, options, preflight and exit
    codes; `[publish]` and its resolution; the template grammar; the
    placeholder table; the `post` region syntax; the `publish` key; the code
    table with explanations and flags; the ledger and what deleting it
    means; the `published` region; the target obligations; the statement
    that nothing a service returns is printed, logged or written except
    permitted links. It names no service: each target documents itself in
    its own connector page.
  - Link it from the documentation index and add it to
    `tests/test_docs_guarantees.py`'s `_REQUIRED_ENTRY_POINT_LINKS`; declare
    it in the package's `[project.urls]`, which the skill's link requires;
    name `[publish]` and `fitdocs publish` in the configuration
    documentation.
  - Docs tests hold the code table equal to the vocabulary (values,
    explanations, flags) and the placeholder table equal to the names in
    order, and fail on a service name.
  - Done when the docs tests pass and die on one changed explanation or a
    dropped placeholder row.
  - _Requirements: 1.7, 9.6, 10.6, 16.1, 16.3_
  - _Boundary: PublishingDocs_
  - _Depends: 7.1_

- [ ] 8.4 Write the changelog entry and refresh the site-copy record
  - The changelog's Unreleased section describes publishing, the two
    regions, the `publish` key, both version changes and the `fitdocs regen`
    action, pinned through `unreleased_since(text, V0_2_0)` from the
    changelog view helper (the entry postdates 0.2.0).
  - Edit nothing under `website/content/` (R9). Refresh the evidence in
    `.kiro/queue/2026-10-31-publish-core-site-copy.md` to the landed line
    numbers and version values, and add any further site line this
    feature makes stale.
  - Done when the changelog tests pass and the queue item names every stale
    site line with the landed values.
  - _Requirements: 16.2, 16.4_
  - _Depends: 8.1, 8.3_

- [ ] 8.5 Record the amendments
  - Take the next free amendment number in each spec at landing and record,
    preserving every existing criterion and approval:
    - **wiki-contract**: criteria for the `post` region, the `published`
      region and the `publish` key, and for the published statements, with
      the contract version change;
    - **workout-docs**: the two regions' placement and the document-format
      version change;
    - **connectors**: Req 1.2-1.4 (three driven, four reserved), the publish
      operation criterion, Req 1.9's outputs, Req 2.3's validation, Req 2.7's
      surface, the single-attempt criterion in Req 9, and the allowed
      dependencies admitting the request and vocabulary leaves in the
      protocol module and the request leaf in the registry module;
    - **effort-tags**: Req 2.1 reads as the effort tag's four keys, the
      user-owned set also holding `publish`;
    - **distribution**: Req 8.1 and 8.2 gain publishing.
  - Add the publish package's entry to the structure steering, and correct
    both halves of its connectors sentence: the request and vocabulary
    leaves join what `connectors` imports, and the publish package's target
    module joins `cli` among what imports `connectors`. Append these clauses
    after whatever clauses the sentence holds at landing, line-disjoint from
    the relay's and other specs' entries.
  - Done when each spec carries its dated amendment naming this spec and its
    spec status check is clean.
  - _Requirements: 16.5, 16.6_

- [ ] 9. Validation

- [ ] 9.1 Prove the end-to-end guarantees
  - Add `fitdocs publish` (a dry run) and `fitdocs publish --targets` to
    the socket-guarded offline-command cases, both with connectors
    configured.
  - Through the CLI with the scripted target over a synced data root: a
    dry run, a posting run and a second posting run (nothing sent, bytes
    identical); `regen` afterwards keeps the `post` and `published` regions
    and the `publish` line; a page renamed by `regen` keeps its record and
    link.
  - A scripted target whose answers and exceptions carry a sentinel string:
    the sentinel appears in no output, ledger or page.
  - Register a posting run through the scripted target in
    `tests/test_confinement.py`'s writing entry points, with a non-vacuous
    check that it wrote a ledger and a `published` region, so its writes are
    confinement-checked like every other writing command.
  - Done when these tests pass in the full suite on macOS and on CI.
  - _Requirements: 1.6, 2.2, 7.5, 8.3, 11.2, 13.5, 13.6, 14.2_
