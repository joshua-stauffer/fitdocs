# Implementation Plan

> **SHELVED 2026-11-03 (maintainer). Do not implement.**
> - **Instead:** the hosted deployment serves `/privacy` and `/terms` as static
>   pages (hosted-policy, private). The relay keeps its built-in Strava policy
>   as it is.
> - **This spec stays as a record and a source.** Reusable parts:
>   - design.md "Supporting References" holds truth-reviewed text for the
>     common sections, Strava and intervals.icu;
>   - the terms, rights and breach drafts are at commit 73e210f8;
>   - research.md holds the retention and logging facts, with code
>     references.
> - **Why shelved:** see `.kiro/steering/roadmap.md`, Phase 14 extension,
>   "Specs".

Prerequisite: `main` at or after 5d1d3cc5, with strava-publish (f0ca31cd)
and relay-server (dbf34412) landed. No other spec in flight touches the
relay's pages, configuration or seam; relay-providers, which touches
`strava/pages.py` and the route table next, lands after this spec and builds
on the neutral page shell from task 1.

Streams: task 1 (the page shell and the empty `legal` package) comes first.
Group 2 then has two independent starts: the content model (2.1) and the
operator configuration (2.2). The fixed text (2.3), the intervals.icu group
(2.4) and the Strava group (2.5) each need only 2.1 and can run in parallel;
the composer (2.6) needs all three. Group 3 wires the seam (3.1), assembles the pages at start-up
(3.2), serves them and retires Strava's own privacy route (3.3), and proves
wrapper contributions end to end (3.4). Group 4 holds the documentation and
records, and group 5 the validation.

Ground rules:
- Work in `relay/` unless a task names a root file; relay commands are
  `cd relay && uv run pytest <paths>`, `uv run ruff check .`, `uv run ruff
  format --check .` and `uv run mypy`; a root file's tests run from the
  repository root with `uv run pytest <paths>`.
- Each task runs the tests it touches plus the neighbours it names, and ruff
  and mypy; branch CI on every push is the full-suite gate, and the full
  relay and root suites run locally only in task 5 (maintainer, 2026-11-02).
- Every new assertion names the production mutation it dies on, and the
  mutation is run before the task is reported done (`tech.md` Testing;
  `change-protocol.md` § Fixture Discrimination). Mutations run in a
  git-archive scratch copy with `PYTHONPATH=<copy>/src` (the editable
  install otherwise imports the original tree).
- Only code is under test (maintainer, 2026-11-03). No test reads `docs/`,
  `relay/CHANGELOG.md` or a spec, and no test pins the wording of the served
  pages: the pages are tested for structure (which parts appear, in which
  order, links, escaping, the announced lead, dates). The fixed text is
  written exactly as design.md's "Supporting References" gives it and checked
  by reading; a task that needs a wording change stops and asks rather than
  changing the text.
- A task that edits `docs/relay.md`, `docs/connectors.md`,
  `relay/CHANGELOG.md` or a spec deletes, rather than updates, each existing
  test that reads the edited part and would go red, and names each deleted
  test in its report; task 4.2's amendments list them.
- New relay test files use unique basenames (`test_legal_*.py`): the relay
  tests have no `__init__.py` and pytest's prepend import mode refuses a
  repeated basename.
- Version moves: `SEAM_VERSION` 1 → 2 (task 3.1). `DEPLOY_CONTRACT_VERSION`,
  the envelope version, the relay schema, and every fitdocs version and
  count (`CONTRACT_VERSION`, `DOC_VERSION`, CLI and connectors surface) do
  not move. Nothing under `website/content/` is edited.
- `relay/tests/test_boundary.py`: each task that creates a relay module, or
  gives an existing standard-library leaf a new run-time import, edits that
  module's entry in `STDLIB_ONLY_ALLOWED` (or the Starlette placement) and
  the literal leaf count in the leaf test in the same task. The count is one
  shared line; parallel tasks reconcile it on merge.
- Expected-value changes to existing tests are allowed only where a task
  names them and the requirement that changes them; each is recorded in the
  matching amendment (task 4.2).

- [ ] 1. Move the page shell out of the Strava package and link the terms when they exist
  - Move the page value, the operator value, the page headers, escaping, the document wrapper, the footer and the built-in policy path into a target-neutral relay module, adding the built-in terms path, the operator's optional terms address, whether the relay serves its own terms, and the terms address rule (the operator's own address, else the built-in path while the relay serves terms, else none).
  - The footer links the privacy policy, then the terms ("Terms of use") when there is a terms address, then shows the support contact.
  - The Strava pages module imports the shell and re-exports the moved names explicitly, so every Strava test keeps its imports; its own page functions, the privacy page included, are unchanged apart from the footer.
  - Create the `legal` package with its docstring only, so group 2's parallel tasks each add their own module to it.
  - Add the boundary entries: the shell module is a standard-library leaf; the Strava pages module may also import it; the leaf count moves to match.
  - Done when, with the default operator, every Strava page's footer is unchanged (one `/privacy` link, no terms link) and the Strava page and route tests pass unchanged; an operator that serves terms gets one `/terms` link on every page; and an operator terms address replaces it while `/privacy` is untouched. The terms-link test dies on removing the terms anchor from the footer; the default test dies on linking `/terms` regardless of whether the relay serves terms; the override test dies on ignoring the operator's terms address.
  - _Requirements: 1.3, 1.6, 1.7, 4.3, 4.4, 7.4_

- [ ] 2. Core: content, configuration, fixed text and composition

- [ ] 2.1 (P) Build the content model and contribution validation
  - Define the plain-text blocks (paragraph, bullet list, operator line, support-contact line), sections, provider pages with their keys, names, retention statement, announced flag and text dates, operator pages, and the legal contribution, as frozen values in a standard-library leaf.
  - Implement the validation that returns one distinct reason for each malformed case the design lists (types, bounds, printability, repeated headings within a part, keys and casefolded names already taken, operator headings that repeat a common heading or a service name, missing retention, a text date present exactly when its sections are) and none for a valid contribution; it never raises on bad input.
  - Done when one test per reason shows that reason returned for a contribution broken in only that way, and a fully populated valid contribution returns none. The case-insensitive name test dies on dropping the casefold; the reserved-heading test dies on skipping that check; the tuple test dies on accepting a list.
  - _Requirements: 2.8, 8.1, 8.2, 8.6_
  - _Boundary: LegalContent_

- [ ] 2.2 (P) Load the operator configuration and the announce row
  - Load the operator name, support contact, privacy policy address, terms address and announced built-in providers whether or not a target is configured, using the existing value rules (moving the operator-name and contact validators out of the Strava configuration, and the web-address validator to the general configuration module).
  - Refuse an unknown or repeated announced provider, naming the variable and the entry; refuse a missing operator name or support contact while a target is configured or a provider is announced, naming the missing variable.
  - Narrow the Strava targets loader's "only with a target" refusal to the public address and the encryption keys, and fill its unchanged operator fields from the loaded operator configuration.
  - Add the two deploy-contract rows after the privacy-policy row, widen the operator name and support contact rows' required-with list to include the announce row, and update `docs/relay.md`'s environment table in the same task; delete the environment-table binding group in `relay/tests/test_docs_relay.py` (the table-equals-code test, its was-read guard and the row, cell, rendering and order mutation tests) rather than updating it.
  - Keep the existing refusal wording (`<VARIABLE>: is required`) for a missing operator name or support contact.
  - Expected-value changes under 9.1, named here: in `relay/tests/test_config_strava.py`, the operator rows' required-with pin, the literal refusal group and its count, the refusal labels drawn from the narrowed variable groups, and the order in which the contract-order refusal test meets its first refusal (the operator values are now loaded before the public address and the keys); the per-row refusal coverage gains cases for the two new rows; in `relay/tests/test_config.py`, the whole-config comparison gains the loaded operator configuration.
  - Done when every command accepts the operator variables without a target, each refusal above prints its message and exits 2, the contract table pin shows the two new rows and the widened required-with lists, and `test_config_strava.py` and `test_config.py` pass with only the changes named above. The unknown-entry test dies on accepting any entry; the required-while-announced test dies on requiring the operator values only with a target.
  - _Requirements: 1.7, 1.8, 2.2, 2.3, 9.1_
  - _Boundary: LegalConfig, Contract_

- [ ] 2.3 (P) Write the fixed common text of the policy, with its date
  - Add the policy's opening, security, artificial-intelligence, retention lead and relay-wide retention, contact and changes text, the announced lead and provider-list wording, both page titles, the closing format, the policy's common heading list and its text date, exactly as design.md's Supporting References give them. Write no terms text, breach-notice promise or request-handling process (7.3).
  - Check each relay-wide retention statement against the storage code it describes (record expiry purged on the next stored record; rate and budget counts removed as new counts of the same kind are recorded; tokens deleted with their principal) before writing it, and record the check in the task's report.
  - Test the module's structure: the common heading list equals the headings of the policy's common sections, in order; the announced and list-entry formats render a given service name; the closing format renders an ISO date.
  - Done when the structure tests pass, a read of the module against design.md's Supporting References finds every sentence as written (recorded in the report), and the fixed text names no legal entity, governing law, jurisdiction, AI product or agent and holds no terms text or operator commitment. The heading-list test dies on moving one section without its heading list.
  - _Requirements: 2.4, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.3, 9.6_
  - _Boundary: LegalText_
  - _Depends: 2.1_

- [ ] 2.4 (P) Write the intervals.icu relay-route group
  - Build the intervals.icu provider pages (key `intervals`, name "intervals.icu") with the seven sections and the retention statement from design.md's Supporting References, announced as the caller says, with its own text date.
  - Re-read each statement against the relay-intervals criteria design.md lists for it, and report any disagreement instead of editing either side.
  - Done when, in its own test module, the group has the seven sections in the designed order and a retention statement, the announced flag follows the builder's argument, and the group passes the content validation; and a read of its text against design.md and the relay-intervals criteria is recorded in the report, including that "Your choices" states the direct route with the athlete's own key does not involve the relay. The announced test dies on the builder ignoring its announced argument.
  - _Requirements: 5.1, 5.2, 5.3, 6.5, 8.6_
  - _Boundary: IntervalsGroup_
  - _Depends: 2.1_

- [ ] 2.5 (P) Wrap Strava's nine sections as its provider group
  - Build the Strava provider pages (key `strava`, name "Strava") from the unchanged nine sections for a link setting, mapping each to a section of one paragraph and adding the operator line after "The relay's operator" and the support-contact line after "Contact", with the Strava retention statement and its text date.
  - Leave the nine sections, their headings and the consent text untouched.
  - The Strava policy module gains a run-time import of the content model: add it to that module's boundary entry.
  - Done when, in its own test module, for both link settings each section's paragraph is the matching text the unchanged section function returns (code against code, not a literal), the operator and contact lines sit where today's privacy page shows them, the group has a retention statement and passes the content validation, and the boundary test passes; strava-publish's existing word-for-word policy and consent tests run unchanged. The placement test dies on attaching the operator line to another section.
  - _Requirements: 2.5, 4.1, 6.5, 8.6_
  - _Boundary: StravaGroup_
  - _Depends: 2.1_

- [ ] 2.6 Compose and render the policy and the contributed terms
  - Compose the privacy policy (opening with the provider list, one group per provider with the announced lead where announced, the common sections, the retention group with one subsection per provider and the relay-wide subsection, contact and changes, operator sections) and the terms only from contributions (provider terms groups in provider order, then operator terms sections), none when nothing contributes terms; each page is dated with the latest date among the parts it shows. Compose both before rendering, so the operator's footer knows whether the relay serves terms.
  - Render through the shell: an `h1` title, top-level parts as `h2` sections, groups with `h3` subsections, every string escaped, elements separated by line breaks, then the closing line.
  - Done when a fixture with Strava offered, intervals.icu announced and two contributed providers and operator parts with terms (pairwise-distinct names, the latest date on the second operator part) renders in the designed order on both pages with the right dates; the same fixture without contributed terms yields no terms page and footers without a terms link; for one link setting, the announced Strava group's rendering equals the offered one with only the announced lead removed (2.5); a hostile heading, paragraph, item and operator name appear only escaped; and composing twice yields identical bytes. No wording or brand-phrase test is added for these pages. Named mutations: reversing contributed order; dating by the common date alone; returning an empty terms page instead of none; dropping the announced lead; rendering anything else differently when announced; removing escaping from headings.
  - _Requirements: 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 6.7, 7.1, 7.2, 7.4, 8.4_
  - _Depends: 1, 2.3, 2.4, 2.5_

- [ ] 3. Integration: seam, assembly and routes

- [ ] 3.1 Advance the seam with the legal contribution
  - Add the optional legal contribution to the wrapper's parts, re-export the content types from the seam, and advance the seam version to 2.
  - Validate each wrapper's contribution while wrappers are installed, passing the built-in keys and names and those of earlier wrappers, and refuse a malformed one naming the wrapper and the reason; collect valid contributions in installation order.
  - In the same task, update the relay changelog's Unreleased version lines to seam version 2 under the breaking-for-deployments marker (rewriting its sentence that seam 1 is restated because no seam call changed), and `docs/relay.md`'s seam heading, anchor, version list and code block. Delete, rather than update, the tests that read those parts: the changelog group and its helper in `relay/tests/test_contract.py`, the versions binding group in `relay/tests/test_docs_relay.py`, and the restated-versions and marks-nothing-breaking tests in the root `tests/connectors/test_strava_changelog.py`.
  - Move `relay/tests/test_seam.py`'s version pin and its wrong-version cases (today version 2, with the message naming version 1) to versions 1 and 3; these test code.
  - Done when the seam surface pin lists the new field and types, a wrapper declaring version 1 is refused, a malformed contribution is refused naming its wrapper and reason, the seam tests pass at version 2, and the relay suite and the root changelog module collect and pass without the deleted tests. The refusal test dies on skipping validation for wrappers after the first.
  - _Requirements: 8.1, 8.2, 8.5_
  - _Depends: 2.3_

- [ ] 3.2 Assemble the pages once at start-up
  - Build the operator value from the operator configuration, including its terms address; after composing, take the operator the composition returns (which knows whether the relay serves terms) as the services' operator and replace the Strava services' operator with it before routes are built.
  - Decide the applying providers (Strava while configured or announced, with the default link setting when only announced; intervals.icu only while announced; then contributions in installation order), compose the policy and any contributed terms once, and keep them on the services; keep nothing when no provider applies.
  - Refuse to start when only contributed groups apply and the operator name or support contact is missing, naming the first contributing wrapper and the variable.
  - Expected-value change, named here: the app surface pin in `relay/tests/test_seam.py` (the designed services fields) gains the operator and the pages.
  - Done when, through the app factory, with only `strava` announced the Strava group shows the `activity` link setting's text after the announced lead (4.2); the services hold no pages with nothing applying, the composed pages with Strava configured or `intervals` announced, and the capabilities' targets are unchanged by announcing; with a wrapper contributing terms, the Strava services' operator serves terms; and the wrapper-only case is refused naming the wrapper and `FITDOCS_RELAY_OPERATOR_NAME`. Named mutations: including intervals.icu when not announced; listing announced providers among the targets; building the announced Strava group with the `relay` link setting; falling back to a blank operator.
  - _Requirements: 1.8, 2.1, 2.6, 2.7, 3.2, 4.2, 8.3_
  - _Depends: 2.2, 2.6, 3.1_

- [ ] 3.3 Serve `/privacy`, and `/terms` when contributed, and retire Strava's own privacy route
  - Serve the assembled pages from fixed bytes, without store access, readiness or client counting, adding the `/terms` route only when terms were composed; the handler answers HEAD itself with 405, the page headers and `Allow: GET`; reserve `/terms`.
  - Retire Strava's privacy route and page function; move the Strava privacy-page tests to the composed page, changing only imports, setup and where they look for the Strava group (4.4). The shared Strava test world (`make_world` in `relay/tests/test_strava_routes.py`), which builds its app from the services and core routes without the app factory, gains the legal pages through the same assembly the app factory uses, so `/privacy` is served in every Strava world.
  - Expected-behaviour changes under 1.5, named here: in `relay/tests/test_strava_pages_routes.py`, the page-route list and the not-ready, store-unreachable, client-limited and shared-client-count tests stop using `/privacy` and use another Strava page path, and so do the wrong-secret webhook test's closing 429 check and the page-status test's `/privacy` case (which answers 200 from the composed page instead); the route-table literal pins (`RESERVED_PREFIXES`) gain `/terms`; in `docs/relay.md`, the Strava routes table drops the `/privacy` row and the "Pages." bullet under the Strava routes stops listing `/privacy` among the pages that answer "Not available" (task 4.1 documents both pages in their own section); the routes-table binding group in `relay/tests/strava/test_policy_docs.py` (the table-equals-code test, its was-read guard and its three mutation tests) is deleted rather than updated.
  - Done when, through the app factory: with nothing applying both paths answer `not-offered`; announcing `intervals` serves `/privacy`, answers `/terms` as unoffered, and leaves `/v1/targets/intervals/connect` and `/connect/intervals` unoffered (2.7); a test wrapper contributing terms makes `/terms` answer 200 and every page link it; the served pages answer 200 with the page headers and no cookie while the store is unreachable and readiness is false; HEAD answers 405 with `Allow: GET` and the page headers; and with `FITDOCS_RELAY_TERMS_URL` set every Strava page and the served legal pages link that address (1.7). Named mutations: gating the pages on readiness; letting HEAD reach the page; adding `/terms` without composed terms; building the operator without its terms address.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.7, 4.4, 7.2, 9.1_
  - _Depends: 3.2_

- [ ] 3.4 Prove wrapper contributions end to end
  - Through the app factory and the serve command with test wrappers: contributed providers and operator parts appear in installation order on the policy, and contributed terms on the terms page; a wrapper marking its provider announced gets the announced lead and list entry; a wrapper contributing nothing leaves the pages byte-identical to the pages without it; a malformed contribution and a wrapper-only provider with no operator values both exit 2 naming the wrapper.
  - Done when those five scenarios pass through `create_app`, and the two refusals pass through `fitdocs-relay serve` with exit 2 and the wrapper named on standard error. The byte-identity test dies on the composer emitting an empty operator section; the serve-refusal test dies on raising the wrapper-only refusal as a configuration error instead of a seam error (which would exit 1).
  - _Requirements: 1.8, 2.8, 7.1, 8.2, 8.3, 8.4_
  - _Depends: 3.3_

- [ ] 4. Documentation and records

- [ ] 4.1 Document the pages
  - Add `docs/relay.md` "Privacy policy and terms" before the Strava target as design.md's documentation outline gives it: when the pages are served and their routes (the terms only when a deployment contributes them), the addresses for a platform application, the policy's order and common headings, announcing, the operator's own addresses, that the relay ships no terms or operator commitments, what a wrapper contributes and must keep true, the operator obligations, and that the text is not legal advice; point the Strava "Privacy policy and consent" subsection at it without changing its section list.
  - Add the default relay's terms address beside its policy address in `docs/connectors.md`.
  - Add no documentation test; delete, rather than update, any existing docs test either edit would turn red.
  - Done when the section and the connectors line are written as design.md's documentation outline gives them, and a read of the changed docs and pages against the code, recorded in the report, finds them accurate and finds "Compatible with Strava" as the only Strava brand phrase in documentation, no Garmin section text, nothing from Garmin's developer documentation, no statement about any application or agreement with Garmin, and no AI product or agent named.
  - _Requirements: 9.2, 9.3, 9.4, 9.5, 9.6_

- [ ] 4.2 Record the change in the relay changelog and the extended specs
  - Add the relay changelog's additive entry under Unreleased: the pages served without a target, `/terms`, announcing, the two rows, the operator variables accepted without a target, deploy contract unchanged.
  - Append one amendment each, at the next free number at landing (today relay-server 2, strava-publish 1, relay-intervals 1): the seam's contribution and version, the rows, the reserved path, the pages served without a target, and the existing relay-server test expectations tasks 2.2 and 3.2 changed (the whole-config comparison, the app surface pin) (relay-server); the policy text moved into the composition, the terms link on every page while terms exist, the policy page served while the store is unreachable, and every existing Strava test expectation tasks 2.2, 3.1 and 3.3 changed (strava-publish); the composition and the intervals.icu group delivered here, which relay-intervals moves into its own package and owns from then on (relay-intervals). Each amendment names the tests that pin what it states and the documentation tests this feature deleted.
  - Done when the changelog entry and the three amendments are written, and each amendment names only tests that exist on the branch or, for a deleted documentation test, existed on `main` before this feature.
  - _Requirements: 8.5, 9.1, 9.7_

- [ ] 5. Validation: sweep the feature
  - Run the full relay suite on both database backends, the root suite, ruff, ruff format and mypy after rebasing onto `main`.
  - Classify every acceptance criterion as pinned (naming the test and the mutation it dies on), preserved-only (naming the existing test), verified by reading (wording and documentation criteria, naming what was read), or unpinned (stating so, with the mutation run that shows it).
  - Read both rendered pages once for each configuration the tests use, checking every sentence against design.md's Supporting References, what the relay does, the wording rules and the public-text rule.
  - Done when the suites are green after the rebase, the sweep lists all 51 criteria with no unexplained gap, and the sweep and the page reading are recorded in the task's report.
  - _Requirements: 3.3, 6.7, 9.6_
