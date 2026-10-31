# Research & Design Decisions

## Summary
- **Feature**: `publish-core`
- **Discovery Scope**: Extension (integration-focused discovery of the page
  contract, the region grammar, the connector framework and the CLI), plus a
  new package (`fitdocs.publish`) whose seams other specs consume.
- **Research mode (downgrade).** Research ran in-context: no subagent
  dispatch is available to batch writers in this `/kiro-spec-batch` run, so
  the skill's parallel codebase and external research subagents were not
  dispatched. Every codebase claim below was checked by reading or grepping
  the worktree at base `ef14cd9c`. No external research was needed: this
  spec talks to no service, and the target briefs carry the sourced service
  findings their own specs need.
- **Key Findings**:
  - The region grammar (`docmerge.merge_regions`) refuses a document whose
    existing markers name a region the fresh render lacks, so an athlete
    cannot add a `post` region by hand. Every workout page must render the
    `post` and `published` regions itself, which changes the page layout and
    takes a `DOC_VERSION` bump.
  - The connector transport already sends authentication requests once
    (`CallMode.AUTH`), but its DATA mode retries every method, `POST`
    included, on 429/5xx/transport failures (`connectors/http.py:297-317`).
    Only a per-request marker lets one DATA-mode session make retried reads
    and a single-attempt write, which a publish target needs.
  - A Strava publish goes through a relay that returns no Strava
    identifier, so the target contract cannot expose resolve, annotate and
    push as three separate operations: the only shape every target can
    implement is one publish operation that takes a request and answers one
    code (and an optional permitted link).

## Research Log

### Page anatomy, regions and ownership classes
- **Context**: where a post override and a links block can live, and how
  they survive regeneration.
- **Sources Consulted**: `src/fitdocs/contract.py` (`USER_REGIONS`,
  `TOOL_REGIONS`, `PRESERVED_REGIONS`, `REFRESHED_REGIONS` at lines
  945-967; `MANAGED_KEYS` 602-626; `USER_KEYS` 665; `user_owned_lines`
  1140), `src/fitdocs/docmerge.py` (`merge_regions`, `_scan`),
  `src/fitdocs/render/views.py` (`render_run_ride`, `render_strength`,
  `render_generic`), `src/fitdocs/render/sections.py` (`morning_region`,
  `notes_region`), `src/fitdocs/morning/engine.py` and `docedit.py`,
  `docs/ownership-contract.md` ("User-Owned and Tool-Filled Regions", "The
  Morning-Of Region", "User-Owned Frontmatter Keys").
- **Findings**:
  - Three region classes exist: user-owned (`notes`, `workout`),
    tool-filled (`load`) and refreshed (`morning`). `PRESERVED_REGIONS =
    USER_REGIONS + TOOL_REGIONS` is contractually in document order
    (`("notes", "workout", "load")`, pinned in `tests/test_contract.py:81`).
  - The `morning` region is the precedent for a fitdocs-owned region written
    from data outside the page's files: an empty fresh render, carried by
    the merge, replaced by its own pass through a regex splice
    (`morning/docedit.py:replace_morning`).
  - The index's render fingerprint blanks every region in
    `PRESERVED_REGIONS + REFRESHED_REGIONS`
    (`index/fingerprint.py:_blank_preserved_regions`), so new regions placed
    in those classes are excluded from the computed-value fingerprint with
    no index change.
  - User-owned frontmatter keys are carried line-by-line through
    `contract.user_owned_lines`, a scan over `USER_KEYS`; adding a key to
    `USER_KEYS` extends the carry everywhere it is applied (sync rewrite,
    regen, load pass) with no change to those callers.
  - The declaration lists `USER_REGIONS` in tuple order and the effort keys
    from `EFFORT_KEYS` (`declaration.py:532-533`).
- **Implications**: `post` joins `USER_REGIONS` placed after the `workout`
  region and before `morning`, so `PRESERVED_REGIONS` becomes `("notes",
  "workout", "post", "load")` and stays in document order. `published` joins
  `REFRESHED_REGIONS`. `publish` joins `USER_KEYS`; the declaration needs a
  documentation-order tuple for user keys rather than `EFFORT_KEYS`.

### Managed values a placeholder can read
- **Context**: "Placeholders are filled only from the page's managed
  values."
- **Sources Consulted**: `render/frontmatter.py:build_frontmatter` (key
  formats: `distance_km` two decimals, `elevation_gain_m` one decimal,
  `moving_time` `h:mm:ss`/`m:ss` string, `avg_hr_bpm`/`avg_power_w` ints,
  `calories_kcal` int, `title` `"<Sport> <YYYY-MM-DD> <HH:MM>"`),
  `contract.py` readers (`document_date`, `document_start_time`,
  `document_sport`, `document_modality`, `document_load`,
  `document_source_identity`), `model.py` (`Sport` values `Run`, `Ride`,
  ...; `Modality` values `run`, `bike`, ...), `render/format.py:fmt_duration`.
- **Findings**: no contract reader exists for `title`, `distance_km`,
  `moving_time`, `avg_hr_bpm`, `avg_power_w`, `elevation_gain_m` or
  `calories_kcal` (grep of `src/fitdocs` finds those names only in
  `contract.py` and `render/frontmatter.py`). The contract module's own rule
  is that every frontmatter read goes through a contract reader
  (`document_date` docstring), and `tests/test_contract_consumers.py` holds
  converted consumers to it.
- **Implications**: the wiki-contract amendment adds one pure reader,
  `document_summary`, for the summary keys; `fitdocs.publish.values` reads
  only contract readers and joins `CONVERTED_MODULES`.

### Connector framework seams
- **Context**: the target contract, credentials, the transport, the
  boundary guard.
- **Sources Consulted**: `connectors/protocol.py` (nine capabilities;
  `PUSH_ACTIVITY`/`ANNOTATE_REMOTE_ACTIVITY` `changes_remote=True,
  irreversible=True, driven=False`; `RESOLVE_REMOTE_ACTIVITY` all false;
  `DRIVEN_CAPABILITIES`), `connectors/registry.py:validate_connector`,
  `connectors/http.py` (`HttpRequest.method: Literal["GET", "POST"]` at 98,
  `CallMode`, `send`, `_send_data` 297-317, `post` 337-353),
  `connectors/credentials.py:resolve_credentials` (391-),
  `connectors/pull.py:_pull_one` (session construction 683-724),
  `connectors/settings.py:load_connectors_settings`,
  `tests/connectors/test_boundary.py` (`_ALLOWED_IMPORT_TARGETS` equality
  pins, `_FORBIDDEN_TARGETS` naming `fitdocs.contract`, `fitdocs.docio`,
  `fitdocs.docmerge`, the network allow-list, the clock scan),
  `tests/connectors/test_surface.py` (`__all__` pinned at 50 names).
- **Findings**:
  - `validate_connector` requires an operation only for a driven
    capability (`PULL_ACTIVITIES`, `PULL_WELLNESS`); wellness-pull's
    Amendment 4 is the precedent for driving a reserved capability.
  - `HttpClient.post` is called only by two test connectors in
    `tests/connectors/test_connect.py` (lines 84 and 112), in AUTH mode; no
    shipped connector calls it.
  - Credential resolution (`resolve_credentials`) is public and already
    used by both `connect` and `pull`; it raises `NotConnectedError` for a
    missing credential or a credential issued for another connector, and
    the store raises `CredentialStoreError` for an unreadable or permissive
    file.
  - The forbidden list does not include `fitdocs.publish`, but the
    per-module equality pin means any new import by a connectors module must
    be added to `_ALLOWED_IMPORT_TARGETS` deliberately.
- **Implications**: the request and result value types live in a
  standard-library-only `fitdocs.publish.request` leaf beside
  `fitdocs.publish.outcomes`; `connectors.protocol` imports those two
  leaves only, and re-exports the value types, `PublishCode` and
  `TARGET_CODES` so that connector target modules never import
  `fitdocs.publish.*` (controller ruling R11, folded at cross-spec review).
  `fitdocs/publish/__init__.py` must import
  nothing, or importing the leaf from `connectors` would load
  `contract`/`docio`/`docmerge` transitively.

### CLI conventions
- **Sources Consulted**: `cli.py` (exit constants 314-321; `_config_error`;
  `dashboard_command` lazy imports and `--format text|json`;
  `pull_command`'s preflight order; `_connector_transport`; the credentials
  directory check `resolve_credentials_dir` + `check_outside_data_root`),
  `tests/connectors/test_e2e.py` (socket-guarded offline-command
  parametrization, 355-371).
- **Findings**: the configuration-error path exits 2 before any write; JSON
  output exists for `query` and `dashboard`; `dashboard` imports its
  package lazily and a test pins that importing `fitdocs.cli` loads no
  dashboards module; `KeyboardInterrupt` maps to 130 in `query` and
  `dashboard`.
- **Implications**: `fitdocs publish` follows `dashboard` (lazy package
  import, `text|json`) and `pull` (preflight order, credentials directory
  check only when a selected target authenticates).

### Index refresh and the published region
- **Sources Consulted**: `cli.py` (`_run_index_pass` called from `sync`,
  `regen`, `load` and the drain), `docs/ownership-contract.md` ("The
  analytics index").
- **Findings**: `plan`, `recovery`, `history` and `dashboard` write
  documents without an index refresh; the refresh rule replaces rows of
  pages that moved on the next refresh.
- **Implications**: `fitdocs publish --yes` does not run an index pass. It
  changes only the `published` region, which the render fingerprint
  blanks; the next refresh sees the changed bytes.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A. Connectors operation protocol, one `publish` operation | A connector that declares annotate-remote-activity implements `PostPublisher.publish(session, request) -> PublishResult` | Reuses instances, credentials, transport and settings; drives the reserved capabilities R5 names; works for relay-backed targets | `connectors` must import a publish leaf (boundary pin change) | Selected |
| B. Three operations (resolve, annotate, push) | The core calls resolve, then annotate or push | Finer-grained | A relay target cannot return the remote activity id (nothing from Strava crosses the relay), so `resolve` cannot be implemented; puts matching in the core, against R8 | Rejected |
| C. Own seam in `fitdocs.publish` | A `PublishTarget` protocol outside connectors | No connectors boundary change | Duplicates instance configuration, credentials and session building; R5 says the reserved capabilities are driven by this contract | Rejected |

## Design Decisions

### Decision: opt-in is a user-owned `publish` frontmatter key
- **Context**: Req 2; brief candidate.
- **Alternatives Considered**:
  1. A first line inside the `post` region naming targets.
  2. A list of pages or rules in `fitdocs.toml`.
- **Selected Approach**: `publish: <target>` or `publish: [a, b]`, joining
  `USER_KEYS`.
- **Rationale**: visible in the page's metadata, carried by the existing
  line carry, per page and per target, and needs no `post` region.
- **Trade-offs**: amends `effort-tags` Req 2.1 ("exactly four user-owned
  keys"); rule-based opt-in stays a roadmap follow-on.

### Decision: template syntax with one optional-clause construct
- **Context**: Req 4, 5; "the design chooses between omitting the clause, a
  declared fallback, or refusing the page with a code".
- **Alternatives Considered**: a template engine (Jinja-like; rejected: a
  runtime dependency and code-like power), `str.format` (rejected:
  attribute and index access, format specs), per-placeholder fallbacks
  (`{x|text}`, rejected: a second way to express absence).
- **Selected Approach**: `{name}`, `{{`/`}}`, and `{?...}`. A bare
  placeholder with no value refuses the page with `value_missing`; a clause
  with any absent placeholder contributes nothing.
- **Rationale**: two behaviors, both explicit in the template; an absent
  value can never render as `0`.

### Decision: one built-in default, overridable table-wide and per target
- **Context**: "each target has a built-in default".
- **Selected Approach**: publish-core ships one default (title `{title}`,
  description a list of optional metric lines). `[publish]` overrides it for
  all targets, `[publish.targets.<name>]` for one. Targets declare no
  template.
- **Rationale**: keeps template strings out of the connector framework;
  both Phase 14 targets post a name and a description.

### Decision: the ledger is keyed by page identity plus target
- **Context**: Req 11.2; controller ruling R8.
- **Selected Approach**: one ledger file per target,
  `.fitdocs/publish/<target>.toml`; each record's `page` is
  `workout:<sha256>`, the base file's content digest at the record's
  creation. A page matches a record when that digest is among its `sources`.
- **Rationale**: an archived file stays in its page's `sources` when the
  base changes and through every rename, so the key is stable; the `workout:`
  prefix names the page kind so that a later kind records itself the same
  way.

### Decision: the single-attempt write mode is a request marker
- **Context**: R4; Req 10.1.
- **Alternatives Considered**: a third `CallMode` (rejected: a session has
  one client, and a target needs retried reads and a single write in one
  request); a separate `send_once` method (rejected: the choice would not
  travel with the request, so a scripted transport could not assert it).
- **Selected Approach**: `HttpRequest.single_attempt: bool = False`; when
  true, `HttpClient.send` calls the transport exactly once in either mode.
  `HttpClient.post` gains a `single_attempt` keyword.

### Decision: idempotency key is the publication id, saved before sending
- **Selected Approach**: 32 lowercase hex characters from
  `secrets.token_hex(16)`, minted once per page and target and saved to the
  ledger before the first request. Targets use it as an upload's external
  id or the relay's publication id.

### Decision: no network-statement rewrites in this spec
- **Context**: R7 assigns `tech.md` network amendments to relay-server;
  intervals-publish's brief claims `docs/connectors.md`'s statements.
- **Selected Approach**: publish-core ships no target, so `fitdocs publish
  --yes` can reach no service until a target lands. The existing
  statements ("connector requests happen only during `fitdocs connect` and
  `fitdocs pull`") stay true at this spec's landing. publish-core adds the
  dry run and `--targets` to the socket-guarded offline test only.
- **Follow-up**: the first target lander rewrites the statements; recorded
  as a revalidation trigger.

## Risks & Mitigations
- A template change re-sends every published page as an update on the next
  `--yes` run. Mitigation: the dry run lists every `would_update`; the docs
  say so.
- Deleting a ledger file loses the record; every page reads as never
  posted. Mitigation: targets resolve before creating (Req 10.6), so a
  re-post updates rather than duplicates; the docs say so.
- Parallel landers append to `connectors.__all__`, `Capability` docs and
  `CHANGELOG.md`. Mitigation: append-only edits; the surface count pin moves
  by this spec's eight names at landing.
- Cross-spec folds (controller rulings R11, R13, 2026-10-31): the code
  `local_record_unreadable` appended at position 35 for a target that cannot
  read its own local record of the connection's activities (intervals.icu's
  pull ledger) and so never uploads; the ledger-identity wording of Req 11.6
  ("the target's ledger identity (its connector id)"), so that
  relay-intervals' later amendment changes only that definition; the
  changelog pins anchored at `V0_2_0`; the structure-steering clauses
  appended after whatever the sentence holds at landing.
- Site copy goes stale (example `doc_version`, contract version) and has no
  publishing page. Mitigation: per controller ruling R9 the site is not
  edited by a Phase 14 spec; `.kiro/queue/2026-10-31-publish-core-site-copy.md`
  records it for the next release's site update.
- A target leaking service text through an exception message. Mitigation:
  the core prints no exception text from a target, only `target_error`.

## References
- `.kiro/specs/publish-core/brief.md` and the four other Phase 14 briefs.
- `.kiro/steering/roadmap.md` "Phase 14 — publishing posts".
- Controller rulings R1-R8 (Phase 14 settled seams, 2026-10-31).
