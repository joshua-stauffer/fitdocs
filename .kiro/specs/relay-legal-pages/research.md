# Research & Design Decisions

## Summary
- **Feature**: `relay-legal-pages`
- **Discovery Scope**: Extension (light discovery): the relay's page layer,
  configuration loader and wrapper seam, at `main` 5d1d3cc5.
- **Key Findings**:
  - strava-publish's tests pin all nine Strava policy sections word for word
    (`relay/tests/strava/test_pages.py::SHARED_POLICY`,
    `test_every_policy_section_is_pinned_word_for_word`), including "The
    relay's operator" and "Contact". Splitting those two across common
    sections would change pinned values, so Strava's group keeps all nine
    sections and the common sections repeat what holds for the whole relay.
    Requirement 4.1 was tightened to this during design.
  - `load_targets_config` refuses `FITDOCS_RELAY_OPERATOR_NAME`,
    `..._SUPPORT_CONTACT` and `..._PRIVACY_POLICY_URL` unless a target's
    client id is set (`strava/config.py:206-226`). Announcing, and a wrapper
    contributing a provider, both need those values without a target, so the
    four operator variables move to their own loader and are accepted
    whenever set.
  - Only versioned routes wait for readiness in the pipeline
    (`app.py:330-340`); Strava's pages gate themselves inside `browser()`
    (`strava/routes.py:223-248`), including a database-backed client rate
    check. The legal pages are fixed bytes per process, so they bypass both.

## Research Log

### Where the policy lives and how it is pinned
- **Context**: Requirement 4 (Strava text unchanged) and 1.6 (terms link on every page).
- **Sources Consulted**: `relay/src/fitdocs_relay/strava/policy.py`,
  `strava/pages.py`, `relay/tests/strava/test_pages.py`,
  `relay/tests/strava/test_policy_docs.py`.
- **Findings**:
  - `policy_sections(links)` returns the nine `(heading, text)` pairs;
    `privacy_page` adds "Operator: <name>" after "The relay's operator" and
    "Support contact: <contact>" after "Contact".
  - `_footer` renders one "Privacy policy" link and the support contact on
    every page; tests count `/privacy` hrefs per page.
  - A brand scan (`_BRANDISH`, `_STRAVA_THEN_CAPITAL`) runs over the visible
    text of every Strava page, `privacy` included.
  - `test_policy_docs.py` binds `docs/relay.md`'s Strava policy summary to
    `POLICY_HEADINGS`.
- **Implications**: `policy_sections` and `POLICY_HEADINGS` stay unchanged;
  a Strava group builder wraps them. The page shell (`Page`, `Operator`,
  `PAGE_HEADERS`, document and footer) moves to a target-neutral module so
  the legal pages do not import the Strava package; `strava.pages` keeps
  re-exporting the moved names so its tests change no import. The brand scan
  must run over the legal pages, whose visible text keeps block boundaries
  (a group heading "Strava" directly followed by a capitalised heading on the
  same line would match `_STRAVA_THEN_CAPITAL`).

### Configuration and start-up refusals
- **Context**: Requirements 1.8, 2.2, 2.3, 9.1.
- **Sources Consulted**: `relay/src/fitdocs_relay/config.py`,
  `contract.py`, `strava/config.py`, `cli.py:444-505`, `serve.py:95-145`.
- **Findings**:
  - `EnvVar.required_with` names variables any one of which makes a row
    required; the four target-neutral rows use `_WITH_ANY_TARGET`.
  - `load_config` raises `ConfigError`; the CLI prints it and exits 2 for
    every command.
  - `create_app` runs inside `run_server`; a `SeamError` from it exits 2
    naming the wrapper, but any other exception (a `ConfigError` included)
    reaches the CLI's last-resort handler and exits 1 as an unexpected
    failure.
- **Implications**: The announce variable and the operator rows are checked
  in `load_config` (every command). The one case known only after wrappers
  are built (a wrapper's provider section with no operator name or support
  contact) is raised as a `SeamError` naming the wrapper and the variable.

### The wrapper seam
- **Context**: Requirement 8.
- **Sources Consulted**: `relay/src/fitdocs_relay/seam.py`,
  `app.py:195-241`, `relay/tests/test_seam.py`, `docs/relay.md` "Seam v1".
- **Findings**: The seam refuses any version other than `SEAM_VERSION`;
  `test_the_seam_surface_is_the_designed_one_whole` pins the surface; wrappers
  are installed after the core services and before `core_routes`, so
  contributions are available when the routes are built.
- **Implications**: `ExtensionParts` gains one optional field; the seam
  re-exports the content types; `SEAM_VERSION` becomes 2 and the changelog
  marks it breaking for wrappers. Validation reuses `SeamError`.

### Retention truth
- **Context**: Requirements 6.6 and 6.7.
- **Sources Consulted**: `storage/sqlite.py:311,331,698` (and the PostgreSQL
  equivalents), `ratelimit.py`, `strava/connect.py:135-155`,
  `docs/relay.md` "Logs" and "What the relay keeps".
- **Findings**:
  - Rate counts are keyed by relay token or an HMAC of the client address;
    budget counts by key and principal (cascade on principal delete). Both
    delete windows that have ended on the next count, not on a timer.
  - Wrapper and connect-session records carry an expiry; every
    `put_record` deletes all expired records first.
  - Logs carry `token_id` but no token, body, header value, query string or
    client address; retention of the log stream is the deployment's.
  - Revoked relay tokens stay listed until the principal is deleted.
- **Implications**: Each retention statement names the trigger that actually
  deletes ("the next time it counts", "the next time it stores a
  short-lived record", "until your relay account is deleted") or gives an
  upper bound ("no longer than until ...").

### The intervals.icu relay route's facts
- **Context**: Requirement 5.
- **Sources Consulted**: `.kiro/specs/relay-intervals/requirements.md`
  Requirements 4, 5, 6, 7, 8, 11, 12.
- **Findings**: The relay asks only for activity-write permission (4.3);
  keeps the encrypted token with no expiry or renewal and a keyed hash of
  the athlete id (5.2, 5.6); fitdocs sends the publication id, sport, start
  with offset, elapsed time, distance, title, description and up to two known
  activities (6.5, 7.10), and the file only on an upload request after a
  definite not-found (6.7); the relay keeps no page-to-activity record
  (7.9); it returns only the activity identifier (12.1); deletion on
  disconnect, on the first refused use, on principal deletion, and when the
  account moves to another principal (4.8, 5.3, 11.3-11.5).
- **Implications**: The section is written from these criteria. Because
  relay-intervals is unimplemented and due for a cross-spec rewrite, its
  amendment records that it owns keeping this section true.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Compose at start-up, serve bytes | Contributions validated and both pages rendered once in `create_app` | Deterministic (3.2), no database on the request path (1.5), refusals at start-up (8.2, 8.3) | A configuration change needs a restart (already true of every variable) | Selected |
| Compose per request | Render on each GET from configuration | None over the above | Repeats work; invites state reads | Rejected |
| Strava policy lifted into `targets/` now | relay-intervals' planned `targets/policy.py` | Matches a later layout | Pulls relay-providers' lift into this spec | Rejected: relay-providers owns the lift |

## Design Decisions

### Decision: Strava's nine sections stay one group, verbatim
- **Context**: Requirement 4; the brief asks for Strava's text "unchanged".
- **Alternatives Considered**:
  1. Move "The relay's operator" and "Contact" into common sections, keep seven in Strava's group.
  2. Keep all nine in Strava's group; common sections restate what holds for the whole relay.
- **Selected Approach**: 2.
- **Rationale**: Option 1 splits a pinned text ("This relay is a service that
  publishes workouts from fitdocs to Strava on your behalf. It is operated by
  the person or organization named below.") whose second sentence refers to
  the operator line below it; moving it changes pinned values or makes "named
  below" point at nothing.
- **Trade-offs**: The page repeats the operator and contact once per Strava
  group. Every sentence stays true.

### Decision: Announcing by an environment row for built-ins, by a flag for contributions
- **Context**: Requirement 2; the brief left the shape to design.
- **Alternatives Considered**:
  1. One row `FITDOCS_RELAY_ANNOUNCED_PROVIDERS` naming built-ins; a wrapper marks its own provider announced.
  2. Only wrappers declare announcements.
- **Selected Approach**: 1.
- **Rationale**: The intervals.icu application needs the intervals.icu
  section before any wrapper exists for it, and a self-hoster has no wrapper.
- **Trade-offs**: Two mechanisms, each where its owner already configures
  things.

### Decision: Announced Strava follows the default link setting
- **Context**: Requirement 4.2.
- **Selected Approach**: `FITDOCS_RELAY_STRAVA_LINKS` stays refused without
  the client id, so an announced-only Strava group shows the `activity`
  variant; configuring `relay` later changes the page with the configuration.
- **Rationale**: No change to Strava's configuration rules.

### Decision: A neutral page shell
- **Context**: Requirements 1.3, 1.6, 1.7.
- **Selected Approach**: `fitdocs_relay/pages.py` holds `Page`, `Operator`
  (gaining `terms_url`), `PAGE_HEADERS`, the document shell and the footer;
  `strava/pages.py` imports and re-exports them.
- **Rationale**: The legal pages must not depend on the Strava package, and
  relay-providers' later lift then moves only Strava's own pages.

### Decision: Dates and digests for fixed text
- **Context**: Requirements 6.9, 6.10, 7.1.
- **Selected Approach**: Each fixed part (policy common, terms common,
  Strava group, intervals.icu group) carries a `date` constant; a test pins a
  literal history of `(date, sha256)` per part over every variant of that
  part's text, so a text change without a new history entry fails. A page's
  date is the latest date among the parts it shows.
- **Trade-offs**: A history edit in place (rather than an append) is caught
  by review, not by the test.

### Decision: The access/export operator command stays out
- **Context**: Requirement 6.4 says requests go to the support contact.
- **Selected Approach**: No new operator command; the docs state the
  obligation. Queued as a follow-up.
- **Rationale**: Keeps the unblocker small; the operator can answer from the
  database today.

## Synthesis Outcomes
- **Generalization**: built-in providers and wrapper contributions use one
  `ProviderPages` shape (8.6), which relay-providers' providers and
  relay-held-files' section then reuse.
- **Build vs adopt**: nothing to adopt; the pages are fixed text over the
  existing HTML shell.
- **Simplification**: no per-request composition, no new storage, no new
  dependency, no lift of `strava/` (relay-providers owns that).

## Risks & Mitigations
- Policy text drifts from what the relay does: pinned word for word, dated,
  and each retention statement checked against the storage code named above.
- The seam version bump breaks the hosted wrapper until it declares 2: the
  changelog marks it breaking; the hosted deployment updates in step.
- The intervals.icu section goes stale when relay-intervals is rewritten:
  relay-intervals' amendment records that it owns the section from then on.
- The brand scan flags new text: the scan runs over the legal pages in
  tests, with block boundaries kept as line breaks.

## References
- `.kiro/specs/relay-legal-pages/brief.md` — discovery brief.
- `.kiro/steering/roadmap.md` Phase 14 extension — decisions and public-text rule.
- `.kiro/specs/strava-publish/requirements.md` Requirement 16.
- `.kiro/specs/relay-server/requirements.md` Requirements 9, 10 and Amendment 1.
- `.kiro/specs/relay-intervals/requirements.md` Requirements 4-12.
