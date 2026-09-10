# Implementation Plan

> **Supersedes the pre-amendment plan.** The first pass of this spec is shipped;
> its task list (foundation, the withdrawn calculator, document integration,
> CLI, validation) is complete and lives in git history. This plan implements
> Amendment 1 (the multi-channel result contract and arbitration) and
> Amendment 2 (withdrawal of the withdrawn methodology) against the
> regenerated design of 2026-07-25.
>
> Sequencing precondition: the shipped load layer — contract, registry, profile
> store, prompt flow, renderer, document editor, engine and CLI surface — is in
> place. Every task below modifies or removes existing behavior rather than
> building it from nothing.
>
> **Green-at-every-boundary rule.** Each task leaves `uv run pytest`,
> `uv run ruff check .` and `uv run mypy src/` passing. This is why the
> withdrawn methodology's withdrawal is split into "repin the suite off it"
> then "delete it", and why the
> result type and its payload serialization move together: the intermediate
> states of any other ordering are red.
>
> **Two independent chains.** Major task 2 (the contract chain) and major task 3
> (the policy chain) share no files and converge on major task 4. They may
> proceed concurrently once major task 1 is complete.

### Amendment 3 (2026-07-25) — what changed, relative to the committed work

Tasks **1.1, 1.2, 1.3, 2.1, 2.2 and 2.3 are committed** (`8a8f008`, `7ae2ade`,
`6386361`, `4396c45`, `c686ae4`, `2c5cbaa`). **None of them is reopened or
rewritten.** Amendment 3 changes only pending work, and its contract changes are
*additive to* what 2.1 shipped rather than a revision of it:

- **2.1 shipped `LoadResult`, `NonSelectedValue` and `QualityFlag` in their final
  shape.** Amendment 3 does not touch them. What it touches — `LoadContext`,
  `supports_activity`, the `NotConfirmed` → `NotComputed` rename and the
  `ProfileView` purity rule — are the parts of `load/types.py` that 2.1
  deliberately left alone ("Unchanged by this design"). They land in **new task
  3.3**, not by editing 2.1.
- **The stub calculators (1.1) and the repinned suite (1.2) move with the
  contract.** Task 3.3 updates the four fixtures' `compute` signatures, adds
  `supports` where a stub needs to answer `False`, and swaps `NotConfirmed` for
  `NotComputed` in the three places they construct it. That is a mechanical
  follow-on, not a re-do of 1.1/1.2.
- **Task 3.1's scope grew** from "a `[load]` reader" to "*the* `[load]` reader,
  with a pinned surface and total defaulting" (Req 14.1-14.3, 14.6). Four
  sibling specs extend this exact module, so the names and the signature are now
  contractual.
- **Task 4.1 absorbs the settings read** that task 4.2 used to own, and gains the
  `LoadContext` construction and the `supports` call. **Task 4.2 shrinks**
  accordingly: the CLI no longer reads `[load]` and no longer threads
  `default_calculator` into `apply_load`, whose parameter is deleted.
- **Task 5.1's subject grew** by three contract changes, and it now depends on
  3.3 rather than on 2.1.
- **Tasks 6.1 and 6.4 gain guards** for the context, the support question, the
  settings surface and the renamed outcome.

Nothing committed becomes false as a result: the shipped `load/types.py` still
compiles and the suite is still green at HEAD; 3.3 is the first task that edits
it again. **The two chains are no longer fully independent** — 3.3 needs 3.1's
`LoadSettings` type — so the concurrency claim above now reads: 3.1 and 3.2 run
concurrently with major task 2; 3.3 follows 3.1.

**Correction (2026-07-25, cross-spec import-direction ruling).** Amendment 3 also
moved `load/settings.py` *below* `load/types.py`, justified by the claim that
`settings.py` imports nothing from `fitdocs.load.*`. That claim was false —
`LoadSettings` aggregates three sibling specs' sub-settings types, each in its own
`fitdocs.load.*` module — and the resulting cycle was reproduced experimentally on
every entry point. `settings.py` returns *above* `types.py`; the contract module
names `LoadSettings` under `TYPE_CHECKING` only. Tasks 3.1, 3.3 and 6.4 are
adjusted below and Requirement 14 gains criterion 14.7. **Nothing committed is
reopened** — the ruling touches only the pending contract task's import line, and
the 3.3-depends-on-3.1 edge is kept as sequencing even though the type edge is
now annotation-only.

### Design re-validation (2026-07-25) — three corrections to pending tasks

A design review after Amendment 3 and the import-direction correction found three
defects, all in **pending** work. Tasks 1.1-1.3, 2.1-2.4 and 3.1 are committed and
**none is reopened**; no requirement is renumbered and no criterion changes.

1. **Task 4.1 depended on an accessor that does not exist and lay outside its
   declared boundary.** `contract.document_date` resolves nowhere in `src/` or
   `tests/`, and `athlete-benchmarks` — nominated to add it by "whichever spec
   lands first" — is at `tasks-generated` with no committed task. Task 4.1's
   boundary named only `LoadEngine`, so an implementer was caught between a
   blocked task and an out-of-boundary edit the review gate rejects. **This spec
   lands first, so 4.1 adds the accessor**, with its boundary extended to
   `DocumentContract` — the same treatment task 2.4 was given for the same module.
2. **Arbitration's no-default branch was modality-granular where Reqs 1.6 and
   10.2 are sport-granular.** Filtering candidates on declared modalities alone
   meant two calculators declaring the catch-all modality — the declaration
   `threshold-load` must make to reach Walk and Hike — would resolve a Rowing
   document to an ambiguity, telling the user to configure a default that cannot
   help because neither candidate covers Rowing, where Reqs 7.7 and 10.5 require
   the honest unsupported state. **Task 3.2 now narrows the no-default candidate
   set by the support question** Amendment 3 put on the contract, and takes the
   activity rather than the bare modality. The configured and forced paths stay
   sport-blind — that argument was correct and survives untouched.
3. **Task 6.4's import guard named a module this spec does not create.** It
   prescribed extending the fresh-interpreter check with `import
   fitdocs.load.qa`, which is `activity-qa-flags`' package and does not exist —
   reddening the final quality gate on the day it is written, with the obvious
   workaround silently discarding the invariant's only real test. **The guard now
   discovers sub-packages rather than naming them**, which also means no sibling
   spec has to edit it.

Correction 2 changes a *pending* module's signature only (`arbitrate`, written by
task 3.2, which has not started). Corrections 1 and 3 change task scope and test
construction. `design.md` is amended in place at each affected component.

- [x] 1. Foundation: give the suite a calculator subject, then withdraw the withdrawn methodology
- [x] 1.1 Build stub calculators as the test suite's calculator subject
  - Minimal calculators constructed only from the published contract — no privilege a plugin author lacks — registered and unregistered around each test that needs one: one that computes a result, one that declines every sport with the typed unsupported outcome, one declaring a methodology-scoped athlete field, and one declaring a per-field confirmation hint
  - The computing stub is deliberately shaped to cover the full result vocabulary later required by the redefined contract, so extending it in task 2.1 is additive rather than a rewrite
  - Registration is scoped per test so no stub leaks into another test's registry, keeping the empty-registry invariant assertable
  - Observable: a self-test registers each stub, addresses it by identifier, exercises its declared outcome, and confirms the registry is empty again afterwards
  - _Requirements: 1.1, 1.3, 2.7, 3.6, 13.6_
  - _Boundary: TestCalculators_
- [x] 1.2 Repin the test suite off the withdrawn calculator onto the stubs
  - Replace every assertion based on the withdrawn calculator across the load-layer tests — profile lifecycle and scoped keys, prompt flow and hints, registry behavior, renderer, document editor, engine, CLI load, feature end-to-end — with the stub calculators, preserving the coverage of each surviving requirement rather than deleting the cases
  - Replace the withdrawn-methodology anchors in the cross-cutting suite: the plugin report's built-in anchor becomes a directly registered stub (still attributed a built-in origin, since origin is assigned by discovery channel), and the confinement, plugin-regression, athlete-reader, CLI, public-API and stress-metric anchors lose their dependency on it
  - The withdrawn methodology's package stays installed and importable throughout this task; only its own dedicated tests still reference it, and assertions that it is a registered built-in are deliberately left for task 1.3 to invert
  - Cross-spec: the plugin report's built-in anchor is `plugin-api` territory and changes here by coordination
  - Observable: no test outside the withdrawn-methodology-specific modules names the withdrawn methodology, and the full suite is green with its package still present
  - _Requirements: 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 13.6_
  - _Boundary: TestCalculators, load-layer and cross-cutting test suites_
  - _Depends: 1.1_
- [x] 1.3 Delete the withdrawn implementation, its bundled tables and its packaging traces
  - Remove the methodology package (tables, zone estimation, points math, interval structure, calculator) together with its bundled lookup tables and its dedicated test modules
  - The load layer's package initializer registers nothing and exports no calculator, so importing it has no registration side effect and the registry reports no calculators on a fresh interpreter
  - Redact the prose that remains in shipped source of the withdrawn methodology's identity: the profile store's and prompt flow's docstring examples move to a neutral illustrative key, the stress-metric docstring drops its sentence naming the withdrawn methodology, and the calculator-selection flag's help text loses its withdrawn-methodology example
  - Invert the packaging test's data-inclusion half into a withdrawal guard — a built wheel must contain no methodology path and no bundled table under the load layer — while retaining its TOML-writing runtime-dependency assertion, which the profile write path still needs; remove the now-dead ignore-file negation that existed only to ship those tables
  - Flip the registration-presence assertions left behind by task 1.2 to the empty-registry invariant
  - Observable: no module under the package source names or imports a symbol of the withdrawn methodology, a built wheel contains no methodology data file, a fresh interpreter importing the load layer reports no registered calculators, and the full suite is green
  - _Requirements: 1.5, 13.1, 13.2, 13.3_
  - _Boundary: WithdrawnCalculatorRemoval, LoadPackageInit, Packaging_
  - _Depends: 1.2_

- [x] 2. The contract chain: redefine the result and how documents record it
- [x] 2.1 Redefine the load result and its machine payload together
  - Replace the single-methodology result vocabulary with the selected load value, the basis it was derived from, the values the methodology computed but did not select each carrying the reason it was not, and the quality verdicts raised about the data behind it — the selected value staying structurally the only field of its kind so no consumer can read a diagnostic as the activity's load
  - A methodology with nothing to diagnose supplies empty collections and nothing is fabricated on its behalf; a non-selected entry that carries no number records that absence explicitly rather than standing in a zero
  - Advance the payload format version and carry every result field through it, including the diagnostics frontmatter will omit; decoding stays all-or-nothing for required fields while absent diagnostic collections decode as empty, so a later additive field does not invalidate the format
  - Omit the non-selected block and the flags block from the rendered section entirely when they are empty — no headings, no empty tables, no placeholder rows — and render diagnostics visibly subordinate to the headline value
  - Extend the computing stub to the full shape: a non-selected entry with no number, and every quality verdict the vocabulary allows
  - Record the sample-aggregate obligation on the contract's compute postconditions — a value derived from a recorded stream is an aggregate over the samples actually recorded, never treating missing samples as zeros — as a documented obligation this feature states and does not enforce
  - Observable: a full result round-trips through encode and parse to an equal value and re-encodes byte-identically; the single-value case renders neither diagnostic block; strict type checking is clean across the redefinition
  - _Requirements: 1.2, 1.8, 1.9, 1.10, 1.11, 7.1, 7.3, 9.2, 11.1_
  - _Boundary: LoadContracts, LoadSectionRenderer_
  - _Depends: 1.3_
- [x] 2.2 Add payload stamp inspection and the routing distinction it exists for
  - A read path that learns what it can from a payload marker without decoding a result: the format version whenever a payload line exists, and — independently best-effort — the recorded status and methodology name only when the body happens to decode to a mapping carrying them
  - Stamp output never constructs a result, never feeds frontmatter restoration, and never feeds the frontmatter projection, so a result written under a format this tool cannot read is never partially parsed or inferred; the methodology name can only ever reach a human-readable reason
  - The recorded status is the one stamped field that reaches routing, and it is what separates a superseded *result* worth protecting from a superseded record of nothing having been computed
  - Retain a recorded prior-format result under the withdrawn methodology and a recorded prior-format unsupported state as test data only, proving that the strict parser refuses the first, that inspection names its methodology, and that the two are distinguished by stamped status rather than by calculator name
  - Observable: inspection reports version, status and methodology for a well-formed prior-format payload, and reports the version alone with both other fields absent for a corrupted body
  - _Requirements: 7.7, 11.1, 11.2, 13.4_
  - _Boundary: LoadSectionRenderer_
  - _Depends: 2.1_
- [x] 2.3 Classify a superseded region without freezing the refillable unsupported state
  - Introduce a superseded region state for a payload whose format version is not current and whose stamped status records a computed result, and return classification as a single value carrying the state, the decoded payload for current-format regions only, and the stamp for the non-current ones
  - A non-current payload stamped as an unsupported state classifies as unsupported, not superseded: it records no result, only that nothing supported the sport when it was written, so it rejoins the compute path and is re-rendered in the current format on the next pass — a no-op-equivalent while the sport stays unsupported and a real fill once a calculator lands
  - A current-format payload whose body is invalid stays foreign content and is never silently overwritten; a non-current payload whose status cannot be determined classifies superseded, the protective default
  - Update the classification call site to the new single return value
  - Observable: each of the five classification cases resolves to its stated state, the decoded payload and the stamp are never both populated, and a prior-format unsupported region carries a stamp with no decoded payload
  - _Requirements: 7.5, 7.6, 7.7, 11.2, 11.3, 13.4_
  - _Boundary: LoadDocEditor_
  - _Depends: 2.2_
- [x] 2.4 Rename the managed load frontmatter keys atomically with the document-format version
  - Integration task crossing this spec's document editor and the document contract owned by `wiki-contract`: the managed load keys become the selected value, the methodology and the basis, and they stay a subset of the managed-key set so no document that has had a load pass reports an unmanaged key
  - Advance the document-format version because the result format changed, making documents needing regeneration detectable without opening the load section, and regenerate the golden documents in the same change with no diff beyond that version
  - The basis key is emitted unconditionally because the result always carries a basis — unlike the conditionally omitted third key it replaces; diagnostics have no frontmatter projection at all
  - Repin the anti-drift assertions that pair the managed load keys with the managed-key set, so a partial edit fails loudly
  - Must land as one commit: new keys written against the previous document-format version make every load-touched document report unmanaged keys
  - Observable: the golden documents differ only in their recorded format version, the anti-drift assertions pass, and the frontmatter upsert remains idempotent with every non-managed line preserved byte-for-byte
  - _Requirements: 7.2, 10.6, 11.5_
  - _Boundary: LoadDocEditor, DocumentContract, golden documents_
  - _Depends: 2.1, 2.3_

- [x] 3. The policy chain: configuration and arbitration
- [x] 3.1 (P) Add the load configuration table reader — the single one, with a pinned surface
  - Project the load table of the already-parsed settings document, owning exactly one key today — the default calculator — and never opening a file itself, so the settings file is read once per invocation
  - _(Amendment 3)_ This module is **the** reader for the load table and every sub-table beneath it, and its surface is contractual because four sibling specs extend it: the settings dataclass, its module-level default instance, its error type subclassing the shared settings error, and the single reader function taking the already-parsed document and the settings file path. No second reader of this table may exist anywhere in the tool
  - _(Amendment 3)_ **Every field carries a default**, so constructing the settings type with no arguments always yields the documented default and a sibling adding a field breaks no existing construction site; the default calculator key defaults to absent rather than being required at construction
  - An absent file or absent table yields the documented defaults; that is the normal case and never an error
  - Unknown keys *and unknown sub-tables* inside the table are ignored, which is the additivity contract four downstream specs depend on to add their own keys and sub-tables without touching this reader
  - Reject a non-table value or a non-string, empty default with an error naming the file and the key, raised as a configuration error the CLI already maps to its configuration exit status; whether the named identifier is registered is deliberately not checked here
  - _(corrected 2026-07-25 by the import-direction ruling)_ Sits **above** the contract module in the dependency order, not below it. Amendment 3's justification for the inversion — "it imports nothing from the load package" — was false: three sibling specs deliver their configuration as typed sub-settings living in their own load modules, so this reader imports them. The contract module instead types its per-pass context against the settings type through a **type-checking-only** import (task 3.3), which is the one edge that must never become a runtime import
  - _(Amendment 3)_ The tests live in **`tests/load/test_settings.py`** — the canonical name, pinned because three sibling specs each name a test module for this reader and every one of them extends this file rather than opening a second. It follows the suite's `tests/<package>/test_<module>.py` convention, and sharing a basename with the root-level `tests/test_settings.py` is not a collision: both directories are packages and `tests/load/test_packaging.py` already coexists with `tests/test_packaging.py`
  - Runs concurrently with major task 2: no shared files, and it depends only on the shared settings reader that already ships
  - Observable: absent file, absent table and a valid key each resolve as specified; a non-string default raises naming file and key; a document carrying two unknown downstream sub-tables parses cleanly; and constructing the settings type with no arguments equals the module-level default — the guard that reddens when a sibling adds an undefaulted field
  - _Requirements: 10.1, 10.2, 14.1, 14.2, 14.3, 14.6_
  - _Boundary: LoadSettings_
  - _Depends: 1.3_
- [x] 3.2 Implement calculator arbitration as a pure policy decision
  - Resolve exactly one calculator for an activity, or state why not, with fixed total precedence: an explicitly requested identifier, then the configured default, then the sole calculator supporting *this activity*, then either no calculator at all or an ambiguity naming the sorted candidate identifiers
  - Never consult registration or discovery order; several supporters with no configured default is an ambiguity, not the first one found
  - An explicitly requested or configured calculator is returned regardless of the activity's sport — substituting a different calculator for a declining one is exactly what the arbitration requirements forbid, so for *that* path the sport question is settled downstream in the engine
  - _(design re-validation 2026-07-25)_ **The no-default branch narrows its candidates by the contract's support question**, after the registry's cheap modality prefilter. Both requirements governing this branch are written in terms of the activity's *sport*, and Amendment 3 put exactly that question on the contract, so candidate selection asks it. Without the narrowing, two calculators declaring the catch-all modality — which the first real calculator must declare to reach two of its sports — resolve a document in a third, uncovered sport to an ambiguity, directing the user to configure a default that cannot help because neither candidate covers it, where the requirements demand the honest unsupported state. All three sub-cases become correct: several support it → ambiguity; exactly one supports it → selected; none supports it → no calculator, and the engine writes the honest unsupported state
  - _(same)_ The module therefore takes **the activity**, not the bare modality. It stays pure — no filesystem, no document knowledge, no *methodology execution*: the support question is contractually prompt-free, athlete-data-free and side-effect-free, so this module remains unit-testable with no filesystem. The narrowing direction is what makes the two filters composable: the support question may only narrow a declared modality, never widen it, so the registry prefilter can never drop a calculator the support question would have reinstated
  - _(same)_ The engine's own support check stays **unconditional**, so on the no-default path the question is asked twice — once here to select, once there to enforce. That is deliberate: selection and enforcement are different requirements, and the engine must not have to know which branch produced its selection. Do not "optimize" it away
  - Validate only the identifier actually in play, up front, raising an error naming the offending value, *where it came from* (the command-line flag, or the configuration key in the named settings file) and the registered identifiers, with no fallback attempted — so an explicit request makes a stale configured default irrelevant rather than fatal
  - Correct the registry's module docstring, whose "try applicable calculators in registration order and use the first non-declining outcome" narrative this task makes false
  - Observable: unit cases cover an empty registry, one supporter, two supporters with no default resolving to a sorted ambiguity, a configured default that does not support the activity still resolving as selected, an explicit request overriding both a valid and a stale default, and an unregistered identifier in play raising with value, source and registered identifiers named
  - _(design re-validation)_ Observable, the three narrowing cases — with two calculators declaring the same modality: exactly one supporting the activity resolves as **selected**, neither supporting it resolves as **no calculator**, and both supporting it resolves as the sorted **ambiguity**. A stub declaring a broad modality and answering the support question negatively for one sport inside it is the fixture for all three
  - _Requirements: 1.6, 8.4, 10.1, 10.2, 10.3, 10.4, 13.5_
  - _Boundary: Arbitration, CalculatorRegistry_
  - _Depends: 1.3, 3.3_ — **the `(P)` marker is dropped by the 2026-07-25 design re-validation.** This task now calls the support question, which task 3.3 adds to the contract, so it can no longer run concurrently with 3.3 and strict type checking would fail if it did. It loses nothing in practice: the concurrency it was granted was with major task 2, which is committed in full
- [x] 3.3 Repin the calculator contract on a per-pass context _(added by Amendment 3)_
  - Add a frozen per-activity context type carrying exactly two members — the activity's own recorded local calendar date, absent when the document records none, and the resolved load configuration for the pass — and make it the calculator contract's fifth compute parameter, so a methodology reaches its configuration and the activity's date through the contract rather than by opening a settings file or reading a clock
  - Keep the athlete-profile view a **store view**: it must not gain the activity date, a configured window, or the load configuration. Those are per-pass state and belong on the context; this is what keeps the protocol's documented meaning true and the import direction one-way, and it is the property three downstream specs must now conform to
  - Add a prompt-free, athlete-data-free support question to the contract — "does this methodology cover this activity?" — with a default implementation identical to the modality membership test it supersedes, so an existing calculator answers it without writing one. Declaring supported modalities stays mandatory; the question may only narrow that declaration, never widen it
  - Rename the fourth outcome variant from the confirmation-shaped name to one that says nothing was computed, and rewrite its docstring for that meaning alone: a non-interactive pass, a declined confirmation, or a methodology that could score nothing. Its routing in the pass is already correct and does not change. Doing this now costs one spec; after the first calculator lands it costs two
  - Carry the rename and the signature change through the package initializer's exports and the public-surface pin, and export the context and the settings type — a calculator author annotates both. The pin is repinned, not frozen: the pre-1.0 plugin-author surface carries no backward-compatibility obligation
  - Move the four stub calculators onto the new signature, give the one that must refuse a sport inside a modality it declares an explicit support answer, and swap the renamed outcome at its three construction sites — a mechanical follow-on to committed tasks 1.1 and 1.2, not a re-do of them
  - _(corrected 2026-07-25 by the import-direction ruling; supersedes Amendment 3's "the contract module may now import the settings module … the settings module imports nothing from it", which was false)_ The context's settings member is typed through a **`TYPE_CHECKING`-only** import of the settings type. The contract module keeps **zero runtime imports** from the load package — the settings module sits above it and imports three sibling specs' sub-settings modules, so a runtime import here is a genuine cycle that fails on every entry point. `from __future__ import annotations` is already present, so the dataclass stays constructible and its field type stays a string
  - _(same correction)_ Amend the contract module's own docstring — the shipped sentence declaring it "the bottom of the load dependency chain … no imports from other `fitdocs.load.*` modules" — with **one** sentence recording the type-checking-only exception, so the invariant it states stays true rather than becoming folklore
  - _(same correction)_ No package initializer beneath the load package may eagerly import a module that reaches the settings module (Req 14.7); this task introduces none and the guard for it lands in 6.4
  - Cross-spec, to be reconciled in this same pass rather than discovered twice: `plugin-api`'s design still lists the old outcome name in its published plugin surface (`plugin-api/design.md:806`). The rename here obsoletes that entry, and `plugin-api` already carries an unmet Amendment 1/2 obligation to declare the pre-1.0 surface unstable — task 5.2 is where that statement lands, and the surface list must be corrected with it. `activity-qa-flags` deletes the lazy package-initializer workaround it adopted for the cycle this ruling actually cuts
  - Observable: strict type checking is clean across the signature change; the context type is frozen with exactly the two members; the default support answer agrees with the modality test for every modality; the profile-view protocol exposes no per-pass member; the old outcome name resolves nowhere in the package; the public-surface pin passes with the new names; and a fresh interpreter importing the contract module alone succeeds — the runtime-edge proof, which an in-process import cannot give
  - _Requirements: 1.12, 1.13, 1.14, 1.15, 14.5, 14.7_
  - _Boundary: LoadContracts, LoadPackageInit, TestCalculators_
  - _Depends: 2.1, 3.1_ — a **sequencing** edge only, kept deliberately: the type edge from the contract module to the settings type is now annotation-only, but the settings type must still exist before the contract module names it and before strict type checking can pass

- [x] 4. Integration: the load pass and the command surface
- [x] 4.1 Rework the load pass around arbitration, its own configuration read, and the superseded state
  - Replace the candidate list and its loop — including the branch that continued past a declining calculator — with a single arbitration call per document folded exhaustively: no calculator writes the honest unsupported state, an ambiguity records a skip whose reason names the candidates and the setting to configure, and a selection proceeds. _(design re-validation 2026-07-25)_ Hand arbitration **the activity**, not the bare modality — it needs the activity to narrow its no-default candidates by the support question, and the pass already holds the parsed activity at this point, so nothing new is resolved for it
  - _(Amendment 3)_ **Read the load configuration table once per pass, inside the pass**, beside the existing athlete and profile loads and before the document scan, and hold the resolved settings for the whole pass; take the configured default calculator from it. The pass therefore has **no** configured-default parameter — it is deleted, because the value is a member of the settings the pass already owns and threading both would read the file twice per invocation. A malformed table aborts before anything is read or written, through the configuration-error envelope the command surface already maps to its configuration exit status
  - _(Amendment 3)_ **Build a per-activity context before each compute call** carrying the resolved settings and the document's own recorded local calendar date. The date comes from the frontmatter mapping the pass has already parsed, read through the document contract's single date accessor — never an inline frontmatter key read, which would break this module's "every frontmatter read goes through the document contract" invariant. Cross-spec: that accessor is `athlete-benchmarks`' (`document_date(frontmatter: Mapping[str, object] | None) -> date | None`); whichever of the two specs lands first adds it with that exact signature and the other consumes it. The pass reads no clock and holds no time zone; an undated or unparseable document binds an absent date and a calculator needing one must decline rather than substitute today
  - _(design re-validation 2026-07-25)_ **That "whichever lands first" is resolved: it is this task.** The accessor resolves nowhere in the source or the suite, and `athlete-benchmarks` has generated tasks but committed none, so this task **adds** `document_date` to the document-contract module with that exact signature, plus its tests in the contract module's own test file. This is a **declared cross-boundary incursion**, listed in this task's boundary for the same reason task 2.4 declared one into the same module: an undeclared edit there is a review-gate rejection, and a task blocked waiting on a peer spec that has not started is worse. Add only the accessor — do not touch the managed keys or the document-format version, which 2.4 already settled — and `athlete-benchmarks` then consumes it unchanged rather than redefining it
  - _(Amendment 3)_ Place the **support question** between selection and field collection as a contract call, not an attribute read: a calculator that does not cover the activity writes the honest unsupported state immediately, and missing-input collection is never reached for it — so a running-only configured default never prompts while syncing a ride, and such a document is reported unsupported rather than filed under missing inputs. Asking the calculator rather than reading its modality set is what gives the gate *sport* granularity, which the first real calculator needs because it must declare a catch-all modality to reach two of its sports. This ordering is load-bearing, not incidental
  - Keep the declining-outcome handling the check narrows but does not replace: a calculator that answers yes may still decline the specific activity, and that reaches the same honest unsupported state
  - Add the superseded branch beside the existing foreign-content branch and before the compute path: without an explicit recomputation request the document is left byte-identical and a skip is recorded whose reason names the recorded format version and, when the stamp carries one, the methodology — needing no methodology-specific code path and no hardcoded calculator name
  - Validate the configured or requested identifier up front beside the existing athlete and profile loads, so an unregistered identifier aborts before anything is written
  - Preserve unchanged: the document-version gate ahead of every branch, the frontmatter restore path, archive resolution and its failure isolation, atomic whole-document writes, the report's buckets, and full offline operation
  - Observable: with nothing registered every fillable document takes the no-calculator path and the pass completes cleanly with an all-unsupported report; a repeated identical pass performs no writes except the single write that brings a prior-format unsupported region into the current format, stable from the second pass onward; a stub records a context whose settings are the data root's configured values and whose date is the document's own, absent for an undated document; and a malformed load table aborts with nothing written
  - _Requirements: 1.3, 1.4, 1.12, 1.14, 3.1, 7.4, 7.5, 7.7, 8.3, 8.5, 8.7, 9.1, 9.3, 10.4, 10.5, 11.3, 11.4, 13.4, 13.5, 13.6, 14.4, 14.5, 14.6_
  - _Boundary: LoadEngine, DocumentContract (declared incursion: the document-date accessor only)_
  - _Depends: 2.4, 3.2, 3.3_
- [x] 4.2 Keep the command surface free of load configuration _(rewritten by Amendment 3)_
  - **Supersedes this task's pre-amendment scope.** It used to read the load table in the command surface and thread the configured default into all three places the load pass is invoked; task 4.1 now owns both, so what remains here is making sure the command surface acquires *no* knowledge of that table
  - The three invocation sites — after sync writes documents, after a prompt-free regeneration, and on the standalone load command — drop the configured-default argument along with the pass's deleted parameter, and the explicit calculator flag remains the sole command-line override with its existing precedence over the configured default
  - The command surface performs no read of the load table and holds no load-settings type: four sibling specs are about to add keys to that table and none of them should have to touch this module
  - The configuration error needs no new handler and now arrives from the pass rather than from a surface-level read: it subclasses the shared settings error the surface already maps to its distinct exit status before anything is written
  - Preserve unchanged: the three commands and their flags, the single interactivity decision point, the exit status for per-document failures, and the printed summary
  - Observable: a configured default in the settings file changes which calculator a load pass uses on all three entry points with no configuration read in the command surface at all, and a malformed load table exits with the configuration status having written nothing
  - _Requirements: 2.4, 3.5, 8.1, 8.2, 8.3, 8.4, 8.6, 10.4, 14.4, 14.6_
  - _Boundary: CliIntegration_
  - _Depends: 4.1_

- [x] 5. Documentation of the contract and the withdrawal
- [x] 5.1 (P) Rewrite the contributor guide against the redefined result
  - Rework the worked example for the new result shape: when to report a value the methodology computed but did not select and how to phrase its reason, the three quality verdicts and what "not assessed" means, and the rule that the selected value is the only load
  - Make the sections that pointed at a shipped reference implementation self-contained, since no calculator ships
  - Generalize the bundled-data and licensing guidance while keeping its point — data shipped inside a calculator package must be redistributable — and stop presenting any methodology as available
  - _(Amendment 3)_ Carry the three contract changes into the worked example: it implements the support question, takes the per-pass context in compute, reads its configuration and the activity's date from that context rather than from any file or clock, and returns the renamed "nothing was computed" outcome. State plainly that the athlete-profile view is stored data only and that per-pass state arrives on the context, so a calculator author does not repeat the workaround three sibling specs had to be talked out of
  - Observable: the guide's example type-checks against the shipped contract and names no shipped methodology
  - _Requirements: 1.7, 13.3_
  - _Boundary: ContributorGuide_
  - _Depends: 3.3_
- [x] 5.2 (P) Correct the shipped documentation and the plugin compatibility statement
  - Remove the withdrawn calculator from the plugin documentation, the ownership contract and the project readme wherever they present it as an available methodology, and reframe the load layer as the carrier that ships no methodology of its own
  - Cross-spec (`plugin-api`): the published surface's compatibility statement promises additive-only change within the current major series, which redefining the result contradicts — replace it with a declaration that the surface is unstable before the first stable release, which is what makes the redefinition legitimate rather than a violation
  - _(added 2026-07-25)_ Reconcile `plugin-api`'s published **surface list** with task 3.3's outcome rename in this same pass: it still enumerates the confirmation-shaped name (`plugin-api/design.md:806`), which resolves nowhere once 3.3 lands. It rides with the compatibility statement rather than being discovered a second time. This spec does not edit `plugin-api`'s files; the obligation is recorded for whoever lands them
  - _(encumbered-content-purge, 2026-07-31)_ Corrects this bullet's original instruction to leave the reference writeup and its extracted tables in place. They document the withdrawn methodology. They were retained as a research record of the withdrawal. That retention was reversed on 2026-07-30 because publishing this repository would publish them. The original retention was a decision taken under the circumstances then in force, not an error corrected here
  - Touches a documentation set disjoint from 5.1, so the two run concurrently
  - Observable: no shipped documentation presents the withdrawn methodology as available, and the compatibility statement no longer promises additive-only change across the redefinition
  - _Requirements: 13.3_
  - _Boundary: WithdrawnCalculatorRemoval, plugin documentation_
  - _Depends: 2.1_

- [x] 6. Validation
- [x] 6.1 (P) Prove the arbitration and prompting boundaries end to end
  - A configured default that does not support the activity's sport, with a second registered calculator that does: the document receives the honest unsupported state and the second calculator is never invoked
  - A configured default supporting running only, a fully interactive session, and a profile missing every field it requires: a pass over a cycling document writes the honest unsupported state, issues zero prompts asserted on the session rather than on printed output, and reports the document as unsupported — not as skipped for missing inputs; the same pass over a running document in the same data root does prompt, proving the check is activity-scoped rather than a blanket suppression
  - _(Amendment 3)_ A stub that **declares** a modality but answers the support question negatively for one sport inside it: no prompt is issued and the document is reported unsupported — the sport-granularity case the first real calculator creates by declaring a catch-all modality to reach two of its sports, and the case a modality-only gate cannot express
  - _(design re-validation 2026-07-25)_ **Two** stubs declaring the same broad modality, no configured default, and a document in a sport *neither* supports: the document is reported **unsupported**, not skipped as an ambiguity, and the printed output directs the user to configure nothing — there is nothing to configure. The same pair with exactly one supporting the sport computes it with no configuration at all. This is the end-to-end proof of the candidate narrowing; 3.2 proves it at the unit level
  - _(Amendment 3)_ A stub records the context it was handed: its settings are the projection of the data root's configured load table rather than the module defaults, and its date is the document's own recorded date — absent for a document whose frontmatter carries no parseable date, with the calculator declining rather than substituting today
  - An unregistered configured default aborts with the configuration exit status, a message naming the value, its source and the registered identifiers, and no document modified
  - _(Amendment 3)_ A malformed load table aborts the same way, before any document is read or written
  - A stub calculator declaring a methodology-scoped field and a confirmation hint is asked once, the answer lands under that calculator's own table, the hint is echoed before persistence, and a second document does not re-ask
  - Lives in its own test module, disjoint from 6.2 and 6.3
  - Observable: every scenario above asserts on the report bucket and the prompt count, not only on the document text
  - _Requirements: 1.12, 1.14, 3.1, 10.2, 10.4, 10.5, 14.5, 14.6_
  - _Boundary: LoadEngine, PromptFlow integration tests_
  - _Depends: 4.2_
- [x] 6.2 (P) Prove the result-format migration lifecycle
  - A prior-format computed document is skipped and byte-identical after a normal pass, and under an explicit recomputation request is recomputed into the current format — or receives the honest unsupported state when nothing supports it
  - A data root whose documents carry prior-format *unsupported* payloads, passed over without any recomputation request and with a stub calculator supporting their sport, computes all of them; the same data root with nothing registered re-renders them into the current format as a no-op-equivalent honest state and reports them unsupported. This is the regression guard for the twenty-four such documents measured in the maintainer's own data root — freezing them would have made the retroactive-fill requirement unobservable for the entire existing corpus
  - A regenerated computed document has its load frontmatter re-derived from the preserved section by a non-interactive pass, with no prompt and no recomputation
  - Lives in its own test module, disjoint from 6.1 and 6.3
  - Observable: each scenario asserts both the report bucket and whether the document's bytes changed
  - _Requirements: 7.4, 7.7, 11.2, 11.3, 11.4, 13.4, 13.5_
  - _Boundary: LoadEngine, LoadDocEditor integration tests_
  - _Depends: 4.2_
- [x] 6.3 (P) Prove the command surface with an empty registry
  - The standalone load command across several workout documents with nothing registered: every document receives the honest unsupported state, the summary reports them, the exit status is success, and a second identical run performs no writes
  - Sync writes documents and runs the pass, with the printed summary lines matching the report's buckets
  - A calculator named on the command line is used even when a different default is configured
  - Two registered supporters and no configured default: the run succeeds, the document is unchanged, and the printed reason names both identifiers and the setting to configure — the ambiguity is actionable rather than merely reported
  - Lives in the command-surface and feature-level test modules, disjoint from 6.1 and 6.2
  - Observable: exit statuses, printed summary lines and write counts all assert as stated, fully offline
  - _Requirements: 8.1, 8.2, 8.6, 10.2, 10.3, 13.2, 13.6_
  - _Boundary: CliIntegration, LoadE2ESuite_
  - _Depends: 4.2_
- [x] 6.4 Close the withdrawal guards and the quality gates
  - Withdrawal guards: a built wheel contains no withdrawn-methodology path and no bundled table under the load layer; no shipped module names or imports a withdrawn symbol; a fresh interpreter importing the load layer reports no registered calculators; and no shipped documentation presents the methodology as available, with the reference writeup exempt by design
  - Repin the public-surface test to the redefined contract, adding the two new result vocabulary types, so its inclusion check keeps passing across the redefinition
  - _(Amendment 3)_ Close the contract guards the rulings introduce, each of which is a property a sibling spec could silently reverse: the public-surface pin also carries the per-pass context and the settings vocabulary and no longer carries the old outcome name; the old outcome name resolves nowhere in the package; the athlete-profile view protocol exposes no per-pass member; and constructing the settings type with no arguments equals its module-level default — the total-defaulting guard, which reddens the moment a sibling adds an undefaulted field
  - _(Amendment 3)_ Guard the single-reader rule: exactly one module parses the load table, and neither the command surface nor any other module reads it independently
  - _(added 2026-07-25 by the import-direction ruling; **corrected the same day by the design re-validation**)_ Guard the import direction (Req 14.7) by extending the suite's existing **fresh-interpreter** import check — `tests/test_public_api.py`'s subprocess-based no-circular-import test, ~line 353 — to cover the load package's entry points alongside the existing `import fitdocs`. It must stay a subprocess: an in-process re-import is a `sys.modules` cache hit and proves nothing, so this is the only test in the suite that can catch a re-inversion. Extend the existing test rather than adding a parallel one
  - _(the correction)_ The ruling first wrote this guard as "at minimum `import fitdocs.load.qa` and `import fitdocs.load.types`". **Do not implement that literally**: the quality-assurance sub-package belongs to `activity-qa-flags` and does not exist in this checkout, so a named import reddens this gate the day it is written — and deleting the offending line, the obvious fix, silently discards the invariant's only real test. Instead **discover** the targets: enumerate the immediate sub-packages of the load package on disk, and in a *separate* fresh interpreter import the load package, its contract module, its settings module and each discovered sub-package. Today that resolves to exactly the three modules that exist; when the channel, priority and quality-assurance modules land, each is covered the moment it appears, and **no sibling spec ever has to edit this test** — which is the coordination cost this requirement exists to eliminate
  - Quality gates: full suite green, lint clean, and strict type checking clean over the package source — the last being the mechanical proof that every reader of the removed result fields and every caller of the changed compute signature was updated
  - Atomicity guard for the cross-spec document-contract change: the consistency check reports no unmanaged keys on a document that has had a load pass, and the golden documents show no diff beyond the recorded format version
  - Observable: all guard groups and all three quality gates pass from a clean checkout
  - _Requirements: 1.10, 1.13, 1.15, 13.1, 13.2, 13.3, 14.1, 14.2, 14.7_
  - _Depends: 5.1, 5.2, 6.1, 6.2, 6.3_

- [ ] 7. Amendment 4 (2026-09-10): dating a prompt-answered benchmark — queue item `2026-08-27-prompt-date-strands-historical-documents`
  > Cross-spec by construction: 7.1 and 7.2 edit modules athlete-benchmarks owns (its Amendment 1 of the same date records the rulings and the module-level obligations), and 7.4's end-to-end proof drives threshold-load's registered calculator (its Amendment 2 records that no calculator change is required). All four tasks land on one branch in this order; each leaves `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` green. Phase 6's `performance-benchmarks` is about to add a `source` field to the same parser/serializer/`with_benchmark` trio — it consumes the shape 7.1 and 7.2 leave, it does not re-add.
- [x] 7.1 Give a benchmark entry an athlete-declared applies-from date in the store leaf
  - `Benchmark` gains `applies_from: date | None = None` (trailing, defaulted, so every existing keyword construction is unchanged); the parser accepts an optional `applies_from` key on an entry table with exactly the bare-local-date strictness `measured_on` already has, and rejects — loudly, naming the entry — a value that is not a bare date or that falls after the entry's `measured_on`; the serializer emits `applies_from` after `measured_on` when present and omits it otherwise, and the round-trip property holds for entries with and without it
  - `BenchmarkSet.applicable` becomes two-tier: the latest entry measured on or before `on` as today; failing that, among entries whose `applies_from` is on or before `on`, the one with the *earliest* `measured_on`; never an entry carrying neither. `has` is unchanged. The duplicate-key rule stays `(discipline, kind, measured_on)`, so the tier-2 minimum is unambiguous
  - `benchmark_age` no longer raises for `measured_on > activity_date`: it returns the negative `age_days` the subtraction yields and `is_stale=False`, because a retroactively applied entry legitimately reaches it; the `window_days < 1` guard stays loud. Its docstring and `BenchmarkAge`'s state that a negative age is the signal a caller reads as "measured after this activity" — a fact of the arithmetic, not a sentinel
  - Fixtures must defeat the plausible wrong rules: two tier-2 cases, each with two retroactive entries — one where the `measured_on` order agrees with the `applies_from` order and one where it reverses it — so that both "earliest applies-from" and "latest applies-from" are defeated (one case alone always agrees with one of them); a tier-2 case with retroactive entries of another discipline and another kind (tier 2 must re-filter scope and kind); a tier-2 case reaching the inclusive boundary `applies_from == on`; a tier-2 case asserted equal over the entries tuple and its reverse (order independence, 3.8); a tier-1 entry present alongside a retroactive one measured closer to the activity (tier 1 must still win); an entry with `applies_from` later than `on` (not applicable, presence still true); and an `applies_from == measured_on` entry (accepted, behaves as if absent)
  - Observable: the unit suite for the leaf module pins every bullet above by mutation, and the existing selection, staleness and round-trip tests stay green unchanged
  - _Requirements: athlete-benchmarks 1.12, 2.11, 3.3, 3.10, 3.11, 4.6_
  - _Boundary: athlete-benchmarks' BenchmarkVocabulary, BenchmarkSelection and StalenessCalculation — `src/fitdocs/benchmarks.py` and `tests/test_benchmarks.py` only_
- [x] 7.2 Persist and preserve the applies-from date through the profile store
  - `AthleteProfile.with_benchmark` gains `applies_from: date | None = None` (keyword-only, trailing) and carries it onto the entry it builds; a value later than `measured_on` is refused with `ValueError` and nothing stored, in the same voice as the existing scope and value refusals
  - The merge that preserves unmanaged entry keys on rewrite treats `applies_from` exactly as it treats `note`: a fresh entry carrying one overlays it; a fresh entry without one (`None`, "not supplied") leaves an existing `applies_from` on that `measured_on` untouched; the round trip through `save_profile` then `load_profile` returns the date
  - `ProfileView.benchmark`'s docstring in `src/fitdocs/load/types.py` and `AthleteProfile.benchmark`'s no longer claim "never a later-measured entry" without the athlete-declared exception; no signature changes
  - Observable: a profile written through `with_benchmark(applies_from=...)` + `save_profile` and read back through `load_profile` resolves the entry for an activity between `applies_from` and `measured_on`; a second `with_benchmark` on the same `measured_on` without `applies_from` does not erase it
  - _Requirements: athlete-benchmarks 6.4, 6.9, 6.10_
  - _Boundary: AthleteProfileStore — `src/fitdocs/load/profile.py`, `tests/load/test_profile_benchmarks.py`, `tests/load/test_profile.py`; docstring-only edits to `src/fitdocs/load/types.py`_
  - _Depends: 7.1_
- [ ] 7.3 Ask the retroactive-application question in the prompt flow, and thread the activity date from the engine
  - `collect_missing_fields` gains keyword-only, required `activity_date: date | None`; for a benchmark field, after the value is accepted and any hint confirmed, and only when `activity_date is not None and activity_date < on`, it asks through `session.confirm` (no new session member) whether the answer applies to earlier activities back to `activity_date`, naming both dates in ISO form with `default=True`; `True` → `with_benchmark(..., measured_on=on, applies_from=activity_date)`, `False` → `measured_on=on` only, `None` → declined, nothing persisted, still-missing. Flat fields, undated activities and activities dated on or after `on` are never asked and persist exactly as before
  - `_compute_document` passes its already-resolved `activity_date` into the flow; the pass keeps its single clock read
  - The existing engine probe that runs against the real calendar date with a 2021-dated document now reaches the question and must queue a `confirm` answer; the injected-`today` probe (2019, earlier than its document) must *not* reach it — pin both, so the condition is proven from both sides at the engine level
  - Fixtures must defeat the plausible wrong implementations: asked once per accepted benchmark answer and never for a flat field in the same declaration list; not asked when `activity_date == on`; not asked when `activity_date is None`; the `None` branch persists nothing (assert the profile is unchanged *and* the persist callback never ran); the `False` branch persists with `applies_from is None`; the question text carries both ISO dates
  - `docs/contributing-calculators.md`'s athlete-field paragraph gains one sentence: the generic flow may ask the athlete whether a benchmark answer applies to earlier activities, and a calculator never sees or handles that question
  - Observable: prompt-level and engine-level tests pin every branch by mutation; the full suite is green
  - _Requirements: 3.3, 3.4, 3.7, 3.8, 3.9, 9.1; athlete-benchmarks 6.2, 8.7_
  - _Boundary: PromptFlow, LoadEngine — `src/fitdocs/load/prompts.py`, `src/fitdocs/load/engine.py`, `tests/load/test_prompts.py`, `tests/load/test_engine.py`, and the one paragraph in `docs/contributing-calculators.md`_
  - _Depends: 7.2_
- [ ] 7.4 Prove prompt → score for an activity older than the prompt date end to end, and document the question
  - A new module `tests/load/test_prompt_date_e2e.py` drives the real sync pipeline, an *absent* `athlete.toml`, the registered built-in threshold calculator and a scripted session through `apply_load(today=<a date after the documents>)`: a running document dated before `today` is prompted for every declared field, every retroactive question is answered *yes*, and the document lands in `report.computed`; the written `athlete.toml` carries each entry with `measured_on == today` and `applies_from == the document's date`, read back through the real store
  - Control, same fixture, every retroactive question answered *no*: the document is *not* computed (it lands in `report.skipped` with the calculator's not-computed reason — assert the bucket and that it is not `computed`, not the reason text, which queue item `2026-08-27-not-applicable-has-no-readers` owns), and every entry is written with `measured_on == today` and no `applies_from`
  - Two documents of the same sport on different dates, both before `today`: the questions fire while the earlier one is processed (the session's recorded questions name the earlier date), a single *yes* per field covers both, both compute, and a second identical pass prompts nothing, computes nothing anew and writes no bytes (asked once, 3.3)
  - The scripted session's recorded questions must show both ISO dates in each retroactive question; the number of questions must equal the number of declared benchmark fields (no question for a flat field, none repeated)
  - `docs/ownership-contract.md`'s `athlete.toml` bullet gains the fact that a prompt answer is dated the day it is given and may carry an athlete-chosen `applies_from` date, and that both are plain keys a hand edit can change; `README.md`'s "prompts for it" sentence gains a clause that fitdocs asks whether the answer also covers earlier activities
  - Observable: the new module is green, is the suite's sole failure under a mutation that drops `applies_from` from the persisted entry or that skips the question, and the documentation sentences match the shipped prompt
  - _Requirements: 3.3, 3.7, 3.8, 3.9, 9.1; athlete-benchmarks 3.10, 6.2, 6.10_
  - _Boundary: LoadE2ESuite — new `tests/load/test_prompt_date_e2e.py`; `docs/ownership-contract.md` and `README.md`, one passage each_
  - _Depends: 7.3_

## Coverage Notes

- **Withdrawn requirements are intentionally uncovered.** Requirements 4, 5, 6
  and 12 are withdrawn by Amendment 2 and have no tasks. Their numbers are
  retired, not reused. Criterion 5.4's obligation — that bundled methodology
  data ship with the installed tool under its licensing note — retires with the
  tables themselves; task 1.3 inverts its former test into a guard that no such
  data ships. Criterion 12.3's surviving intent — a methodology reporting no
  channel values renders none rather than empty or placeholder entries — is
  carried by Requirements 1.11 and 7.1 in task 2.1.
- **This spec registers no calculator.** Requirements 3.2, 3.3, 3.4 and 3.5 and
  the whole of Requirement 2 are satisfied by shipped behavior; they are
  re-proven without a bundled calculator in task 1.2 rather than reimplemented.
  Until `threshold-load` lands, every document correctly receives the honest
  unsupported state of Requirement 7.7 — a specified interim, not a regression.

## Cross-Spec Coordination

Three tasks change assets another spec owns, and each must land with this spec's
change rather than separately:

- **Task 2.4** — the managed load keys and the document-format version belong to
  `wiki-contract`. A mismatch makes every load-touched document report unmanaged
  keys, which is why the key rename, the version bump and the golden
  regeneration are one commit.
- **Task 5.2** — the published plugin surface's compatibility statement belongs
  to `plugin-api`. Redefining the result removes published fields, so the
  statement must declare the surface unstable before the first stable release.
- **Task 1.2** — the plugin report's built-in anchor belongs to `plugin-api` and
  becomes a test-registered stub once no built-in ships.

Added by Amendment 3:

- **Task 4.1 reads the document date through `contract.document_date`**, an
  accessor `athlete-benchmarks` specifies
  (`document_date(frontmatter: Mapping[str, object] | None) -> date | None`)
  and `wiki-contract` owns the module for. Whichever of the two specs
  lands first adds it with that exact signature; the other consumes it and does
  not redefine it. **It must not interleave with task 2.4**, which edits the same
  module (`src/fitdocs/contract.py`) and the same test module
  (`tests/test_contract.py`) and has to be a single atomic commit. One lands
  completely, the other rebases.
- **`athlete-benchmarks` now depends on this amendment landing.** It has dropped
  `activity_date` and `staleness_window_days` from `ProfileView` (and with them
  `AthleteProfile.for_activity` and `load_profile`'s window parameter), so
  `LoadContext.activity_date` — task 3.3 — is its only route to the activity's
  date. Task 3.3 is therefore on that spec's critical path, not just this one's.
- **The canonical test module for the `[load]` reader is
  `tests/load/test_settings.py`** (task 3.1). `load-channels`, `threshold-load`
  and `activity-qa-flags` said `tests/load/test_load_settings.py` and were
  corrected 2026-07-25; `athlete-benchmarks` already matched. Every sibling
  extends this one file.

Added by the import-direction ruling (2026-07-25):

- **`activity-qa-flags` deletes its lazy `__getattr__` re-export in
  `load/qa/__init__.py`.** The cycle that workaround dodged is real — Amendment 3
  said it "does not exist", and that was falsified experimentally — but it is cut
  here instead, by task 3.3's `TYPE_CHECKING`-only import in `load/types.py`.
  With that edge annotation-only, `qa/__init__.py` is an ordinary eager
  initializer, `qa/flags.py` imports `fitdocs.load.types` directly and
  `load/settings.py` imports `qa/types.py`. That spec is being amended in
  parallel; this entry records the coordination, and task 6.4's fresh-interpreter
  guard is what keeps both sides honest afterwards.
- **`plugin-api`'s published surface list must be reconciled with task 3.3's
  outcome rename**, in the same pass as the compatibility statement task 5.2
  already owes it (`plugin-api/design.md:806` still lists the old name). Recorded
  here so it is not discovered twice; this spec edits none of `plugin-api`'s
  files.

Steering (`product.md`, `tech.md`, `structure.md`, `roadmap.md`) still presents
the withdrawn methodology as shipped in places; that is steering maintenance
outside this task graph, tracked by Requirement 13.3's documentation scope.

## Implementation Notes

From task 6.4 (four review rounds), binding on any spec that ships a guard:

- **A negative obligation guarded by a NAME cannot see a violation spelled
  without that name.** Four rounds each found a strictly deeper escape of the
  same single-reader rule, and every one passed pytest + ruff + mypy together:
  (1) `importlib` + `getattr`; (2) a plain `reader = load_load_settings`
  alias; (3) a **module-level `from x import y as _alias`**, which defeats an
  `ast.Call.func` walk *and* a `monkeypatch` spy, because a from-import binds
  the original object into the importing module's namespace before the patch
  runs; (4) a module **parsing `[load]` directly**, never calling the reader at
  all. The obligation was "exactly one module *parses the table*"; three rounds
  of guards had only ever asked "who *calls this function*". Those are
  different guards and a spec that states the first needs both.
- **"Spying both binding surfaces" is a category error.** There are as many
  binding surfaces as there are importing modules. The working shape is a
  sweep: for every module in `sys.modules` under the package, patch every
  attribute that `is` the original object.
- **Every AST-based guard needs a positive control.** Two guards in this task
  passed green having scanned zero files — one was rejected for it, the fix was
  applied to that one and not to its sibling in the same round, and the sibling
  was then rejected for the identical defect. `assert scanned, ...` before the
  offender loop; the path expression is depth-sensitive and drifts silently.
- **A docstring is not evidence.** This task shipped *three* false claims of
  the form "Mutation caught: … verified by hand" — each on a guard that a
  reviewer then broke with the suite staying green — plus one "tracked as
  follow-up work" naming a queue item that did not exist. Round 4's review
  disproved a fifth by running it. Grep changed test files for the current
  prose-claim pattern — `.kiro/steering/change-protocol.md` § Fixture
  Discrimination → "Prose is not evidence" is the single copy to read, since
  the vocabulary has since widened and this note would otherwise go stale
  again — and re-run every surviving claim. That section also states plainly
  that a clean grep is not evidence a claim is true; read the changed
  sentences regardless.
- **Reviewer mutations are the deliverable on a guard task.** The implementer
  for this task died before reporting and left nothing but docstrings; the
  guards were still landed, because the reviewer designed and ran its own 20
  mutations rather than checking a table. Across group 6 the reviewers ran ~70
  independent mutations and rejected 4 of 6 submissions — every rejection on a
  test that could not fail, never on wrong production code.


From task 6.3, binding on task 6.4:

- **Tied fixture values hide swap mutations.** Bullet 2 asserted five printed
  summary rows against buckets `computed=1, restored=0, unsupported=1,
  skipped=0, failures=0`. Two rows tie at 1 and three tie at 0, so any swap
  *within* a tie group is invisible: 4 of the 10 pairwise row swaps left the
  entire 1840-test suite green — including the swap over the two buckets the
  test's own comment called "distinguishable". **Any test mapping N things to N
  values needs pairwise-distinct values** (1/2/3/4/5). The fix was a direct
  `capsys` call on the printer with a synthetic report; all ten swaps now redden.
- **A label the renderer always prints is not evidence.** `assert "Unsupported"
  in output` matched a row emitted on every pass regardless of the report, so
  "the summary reports them" had nothing behind it — a mutation under-reporting
  *only* when more than one document is unsupported (exactly the multi-document
  case the bullet exists for) passed the whole suite. **Assert the count, not
  the label.**
- **A test that compares output to a report it captured from the same run is
  self-referential about content.** An all-zero report matches an all-zero
  table, so a pass that discovered no documents passed. One line
  (`assert report.computed and report.unsupported`) closes it. Applies to any
  spy-and-compare shape.
- **A remediation instruction can be wrong; verify before complying.** Round 1
  asked for "assert both document names appear in the output". `_report_load`
  emits per-document lines for `computed`, `skipped` and `failures` only —
  `unsupported` gets a count row and nothing else — so the assertion would have
  been permanently false. The implementer declined with evidence and the
  reviewer confirmed against source. Declining with evidence beats complying
  into a broken test.
- **For 6.4 specifically:** Req 13.2's *structural* half is invisible to
  behavioural tests. A **declining** built-in registered at `fitdocs.load`
  import is behaviourally identical to no built-in at all — 1837 tests pass
  with one present. 6.4's fresh-interpreter guard must assert the registry is
  **empty**, not merely that no withdrawn name is registered.


From task 6.2, binding on tasks 6.3 and 6.4:

- **A state assertion that holds *before* the pass as well proves nothing about
  the pass.** Bullet 2's "re-renders them into the **current format**" was
  asserted as `classify_load_region(...).state is UNSUPPORTED` — but a
  *prior*-format unsupported stamp classifies `UNSUPPORTED` too, so the
  assertion was already true of the fixture. Under a mutation making the writer
  emit the prior-format marker, four of the module's five tests reddened and
  that one survived. The discriminating half is `region.payload is not None`:
  `payload` is populated only for a current-format region. **Before asserting a
  post-condition, check it is false in the fixture's starting state.**
- **Assert on the exact version token, never a bare substring.** `assert "1" in
  skip_entry.detail` also passes for 10, 11, 12, 21 — live the moment
  `LOAD_PAYLOAD_VERSION` reaches 10 or a second prior format is retained.
  Queued; `tests/load/test_engine.py:701` carries the same shape.
- **Build prior-format subjects by a real `sync` with only the *region* line
  replaced**, never as a hand-written legacy document — task 2.4's warning. The
  frontmatter then carries no stale `load_points`/`load_zone` for
  `strip_frontmatter_load` to leave behind under `--recompute`, so the fixture
  cannot contradict itself.
- **Four of five scenarios were sole failures under a mutation nothing else in
  the 1836-test suite caught** (a restore path that prompts; a refill that
  reaches only the first document; recompute-over-superseded with an *empty*
  registry). That is what a validation module is for. The fifth reddened only
  alongside its `test_engine.py` analogue — legitimate as the boundary module's
  own statement, but it added no coverage.


From task 6.1, binding on tasks 6.2, 6.3 and 6.4 — **every remaining task in
this spec writes only tests, so "can this test fail?" is the whole review:**

- **A persisted athlete answer absorbs a wrongly-issued prompt.** Bullet 2's
  "issues zero prompts" was first written as a pass-wide `len(ask_int) == 1`
  over a root holding a Ride and a Run document. Under a mutation moving the
  support gate *after* field collection, the Ride document prompts, persists
  the answer, the Run document then finds the value present — and the total is
  still 1. The test passed. Any "zero prompts" obligation needs either its own
  `apply_load` call against a fresh profile (`session.prompts == []` outright),
  or **distinct** required fields per calculator so the answers cannot
  substitute for each other.
- **The bullet-2 same-root control the task text mandates is provably inert**
  and was deliberately not implemented. The reviewer wrote the literal same-root
  form and ran it under the gate-moved mutation: it passed, in either scan
  order, for the same absorption reason. Two roots differing only in sport is
  the controlled form. Queued as a tasks.md correction, not a deviation.
- **A "before any document is read or written" claim cannot be tested on a data
  root that owns a document** — a lazy per-document abort raises there too and
  also writes nothing, so `pytest.raises` plus a byte-snapshot both pass either
  way. This is the trap task 4.1's notes already named, and it was reproduced
  verbatim. The discriminating fixture is an **empty** `workouts/` directory:
  a lazy abort then has nothing to raise on. Split the message-content claim
  (which a document-owning root does prove) from the timing claim.
- **Known residual, accepted:** the empty-root test pins "before the
  per-document loop", not literally "before any document is *read*".
  `_discover_workout_docs` reads every candidate's frontmatter, and moving the
  settings read to sit after it leaves all 1831 tests green. Pinning that needs
  read-instrumentation unlike anything else in the suite; queued rather than
  built. A future "skip settings I/O when there are no documents" refactor
  lands exactly there.
- **Make a stub raise, not decline, when you mean to test the engine's gate.**
  A stub that *declines* for the wrong modality shadows the gate — deleting the
  gate changes nothing. A stub that *raises* turns a gate defect into a visible
  failure. Both shapes are needed and the module carries both.
- **Method that worked:** the reviewer re-ran every mutation independently
  rather than trusting the implementer's sweep, and found two survivors the
  implementer's own sweep had reported as pinned. On a test-only task the
  reviewer's mutations are the evidence; the implementer's are a claim.


From task 3.3, binding on every task that asks the support question (3.2, 4.1,
5.1) — **read this before writing `calculator.supports(activity)`:**

- **The support question is asked through `supports_activity(calculator,
  activity)`, a module-level function in `fitdocs.load.types`, never as an
  attribute call on the calculator.** design.md **formerly** prescribed
  `calculator.supports(activity)` with a default supplied as a body on the
  `LoadCalculator` `Protocol` — corrected in full as of task 6.4's feature
  validation (`grep -c 'calculator\.supports(' design.md` is now 0, and the
  `LoadCalculator` Service Interface block carries the rationale inline rather
  than the member). Retained here because the reasoning still governs. That is not
  expressible in Python: a `Protocol` method body is inherited **only by explicit
  subclasses**, so a duck-typed calculator never receives the default — and
  declaring the member on the Protocol simultaneously makes it **mandatory** for
  structural conformance, which is the opposite of Requirement 1.14's "a
  methodology that declares nothing more specific shall answer it by its declared
  modalities". Measured, not theorized: as a Protocol member, three of the four
  stub calculators, the installed plugin fixture
  (`tests/fixtures/plugin_pkg/fitdocs_fixture_calc.py`) and every plain-class
  shape in `docs/` answered `hasattr(cls, "supports") == False` and would have
  raised `AttributeError` at the engine's gate.
- **Adjudicated:** Requirement 1.14 governs; the call shape does not. The
  semantics design.md specifies are unchanged and were implemented as written —
  pure, prompt-free, athlete-data-free, asked before field collection, defaulting
  to the modality membership test, permitted to **narrow** a declared modality but
  never widen it. `supports_activity` uses a calculator's own `supports` when it
  defines one (`getattr`-detected, the same additive seam as
  `athlete_field_hints`) and falls back to membership otherwise.
- **A reviewer must not reject 3.2/4.1/5.1 for deviating from design.md's literal
  attribute-call wording.** Queue item
  `2026-07-26-supports-call-shape-design-drift.md` closed most of it; its
  done-criteria grepped `calculator\.supports(` and folded `default[ ]*
  implementation`, neither of which matches a `def supports(self, ...)`
  *declaration*, so the Service Interface block survived that closure and was
  corrected during 6.4's feature validation. **Lesson for any doc-drift queue
  item: grep the declaration form as well as the call form.**
- **The narrowing-only obligation is documented, not mechanically enforced**, and
  it was violated on its first and only implementation: `DecliningCalculator`
  shipped a `supports` with no modality condition, answering `True` for a
  `Modality.RUN` activity while declaring only `Modality.OTHER`. Any new
  `supports` must gate on `activity.modality in self.supported_modalities` first,
  or the registry's `for_modality` prefilter stops being a sound prefilter.
- **`DecliningCalculator` is the fixture tasks 3.2 and 6.1 need** for the
  "declares a broad modality, refuses one sport inside it" role: it declares
  `Modality.OTHER`, refuses `Sport.ROWING`, and still returns `Unsupported`
  unconditionally from `compute` — so Requirement 10.5's "answers yes, then
  declines" path stays reachable through `Modality.OTHER`/`Sport.HIKE`.
- **Task 4.1 will break the installed plugin fixture.**
  `tests/fixtures/plugin_pkg/fitdocs_fixture_calc.py:31-33` still declares a
  4-parameter `compute`; it was out of 3.3's boundary and is only registered and
  discovered today, never invoked, so the suite is green. 4.1's 5-arg call site
  is where it must be updated.
- **Method note that closed this task:** two review rounds rejected it on
  evidence that did not discriminate — a mutation targeting a branch no test
  reached, and an observable demonstrated on a subject rewritten to make it pass.
  Trace which branch actually executes before claiming a test covers it.

From task 5.2, binding on task 6.4 and on any future cross-spec boundary call:

- **"Owner: <other-spec>" in the Cross-Spec Coordination table does not mean
  "do not edit".** That table is headed *"must land in one change"*. 5.2 first
  read the row `docs/plugins.md compatibility statement | Owner: plugin-api` as
  a prohibition and left the statement unedited — leaving shipped documentation
  promising additive-only change within `0.x` while this branch had already
  removed `NotConfirmed`, changed `compute`'s signature and added `supports`.
  The precedent that settles it: task **1.2 already edited a `plugin-api`-owned
  asset** (`tests/test_plugins.py`) under the identical "cross-spec" label.
- **The distinguishing test is the file, not the label.** Item 3 carries an
  explicit *"This spec does not edit `plugin-api`'s files"* carve-out and its
  target is `plugin-api/design.md` — a spec file. Item 2 carries no carve-out
  and its target is `docs/plugins.md` — a repo doc inside this task's own
  boundary. **When a task's own Observable requires a change, that change is in
  scope; if it genuinely were not, the Observable would be unsatisfiable.** Read
  the Observable as the boundary's tie-breaker.
- **Recording is what you do for work you cannot land.** `plugin-api` has zero
  open leaf tasks — every leaf is `[x]`, and its design note says "Not a
  re-spec". An obligation recorded into a completed spec has no vehicle and is
  lost. Before recording rather than doing, check the receiving spec actually
  has somewhere to put it.
- **For 6.4 specifically:** the existing name-absence guards are package-scoped
  (`test_not_confirmed_resolves_nowhere_in_the_package` walks `src/fitdocs`
  only) and `tests/test_contributing_calculators_doc.py` reads only its own
  guide. `docs/plugins.md:263-266` deliberately mentions `NotConfirmed` as
  *history* — what changed and why an old calculator will not run — and carries
  an inline `<!-- historical-note: ... -->` marker. If 6.4 generalizes a
  name-absence guard to the `README.md + docs/**/*.md` corpus that
  `tests/test_docs_guarantees.py` already scans, that paragraph is its only
  offender; exempt it by the marker rather than deleting the prose.
- **6.4's documentation guard is name-keyed and will not catch surface drift.**
  It asserts no shipped doc presents *the methodology* as available. It would
  not have caught either defect this task fixed — a false compatibility promise,
  and a published name that no longer imports. Consider asserting that every
  name in `docs/plugins.md`'s surface list actually imports.

From task 5.1, binding on any task that ships or checks a documentation example:

- **Type-checking a doc example proves it is internally consistent, not that it
  satisfies the contract it claims to implement.** 5.1's first mechanism
  extracted the worked example and ran `mypy --strict` on it. A bogus required
  6th parameter on the example's `compute` left all tests green, and so did
  renaming the *shipped* Protocol's parameter — the exact stale-guide drift the
  check existed to catch. Assign the example to the protocol type inside the
  checked block: `_conformance: LoadCalculator = ExampleCalculator()`.
- **That assignment alone is still not enough, and this is non-obvious.** mypy's
  structural conformance ignores **parameter names** for ordinary
  positional-or-keyword parameters — only arity, types and order matter — so a
  bare rename passes the assignment silently. Both the implementer and the
  reviewer built minimal repros confirming it. The fix is to *also* make a
  never-called **keyword call** on the protocol-typed variable
  (`_conformance.compute(activity=..., context=...)`), which checks the
  parameter names against the Protocol's own signature. Only that reddens on a
  rename.
- **A deleted rule cannot be caught by a type checker.** The worked example's
  narrowing-only modality gate is valid Python whether present or absent, so its
  removal needs a **textual** assertion on the extracted source. Any rule the
  guide teaches that is not expressible as a type needs one.
- **In an author-facing document, a correct guard is not automatically a good
  one.** The conformance helper lives inside a block plugin authors copy from,
  so it opens by telling the reader to delete it. Correct-but-confusing has a
  real cost in documentation that exists to be copied.

From task 4.2, binding on tasks 6.1-6.4 (every remaining task writes a guard):

- **A structural guard asserting "this module does not import/read X" is
  bypassed by alternate spellings, and will pass review looking correct.** 4.2's
  first attempt matched only `ast.ImportFrom` with `module == "fitdocs.load.settings"`
  plus bare alias names. The reviewer added a *real, working, guarded* `[load]`
  read to `load_command` spelled `from fitdocs.load import settings` and got
  **1813 passed, zero failures**. `import fitdocs.load.settings` and
  `from fitdocs import load` also evaded it, as did a read of any `[load]` key
  other than the one literal in its substring guard — which is exactly the case
  the obligation exists for, since four sibling specs add `[load.sufficiency]`,
  `[load.priority]` and `[load.flags]`.
- **The fix that held: two complementary tests, not a better regex.** A
  resolution-based structural check (walk the AST resolving *dotted targets*, or
  assert against `module.__dict__` that no bound name resolves into the forbidden
  module — the latter is spelling-proof by construction), **plus** a behavioural
  companion counting real calls to the reader during one command run. The
  behavioural half is not redundant: an `importlib`/`getattr`-routed read is
  invisible to any AST walk and makes the counter the sole failure.
- **Known residual, accepted (updated by queue item
  2026-07-26-second-load-reader-spellings-escape-guards's remediation):** a
  module-level alias (`_T = "load"`; `doc.get(_T)`) still evades the
  literal-key AST check — the generic limit of literal-based guards, which
  the behavioural companion below does not close either since a literal-key
  read never calls `load_load_settings` at all. Task 6.4's guards did widen
  past this note once, on four further spellings the queue item surfaced;
  what held and what did not, after measurement:
  - **Closed** — `document["load"]["channels"]` (subscript), the unbound
    form `dict.get(document, "load")` (queue spelling 2, key at `args[1]`
    only when the receiver is literally `dict`), and a default-parameter
    capture, `def f(..., _r=load_load_settings)` including the
    keyword-only form (queue spelling 4 — closed via the behavioural spy's
    `sys.modules` walk extended one dereference to each swept function's own
    `__defaults__`/`__kwdefaults__`, not by widening the literal-key walk).
  - **Accepted as residual, alongside the aliased-key case above** — dict
    iteration, `for k, v in doc.items(): if k == "load"` (queue spelling 1),
    and `document.pop("load")` (queue spelling 3). Both were reachable via
    pattern-matching (`ast.Compare(==)` and a `.pop`-carrying `.get`/`.pop`
    clause), but both clauses false-positived on real, legitimate code
    reachable from this same repo — `"load"` is simultaneously this settings
    table, `fitdocs.contract.LOAD_REGION` (a rendered document region), and
    the `@app.command("load")` CLI verb, so `command_name == "load"` and a
    hypothetical `regions.pop("load")` region-removal are syntactically
    identical to the two second-reader spellings they were meant to catch.
    Measured: both constructs, added as real code, left the full suite,
    ruff and mypy green with the narrower clauses in place. Guarding these
    two spellings would mean banning the literal string `"load"` from most
    of `src/fitdocs`, not guarding `[load]`'s single-reader rule — not a
    trade this task takes. Task 6.4's guards should assume this narrower
    limit (subscript and `.get` only, both argument positions bound to
    where a key can actually appear) rather than trying to close spellings
    1 and 3 with more pattern-matching.
- **Verify a negative obligation by violating it.** The only evidence that
  counts is: add the forbidden thing, in several spellings, and watch a test
  fail. Reading the guard tells you nothing — 4.2's first guard read correctly.
- **A seam between two tasks is where user-facing bugs hide.** 4.1 moved the
  `[load]` read inside `apply_load` but could not touch the CLI; 4.2's
  pre-amendment scope assumed the CLI did the reading. Between them,
  `_run_load_pass` caught only `(ProfileError, AthleteFileError,
  UnknownCalculatorError)`, so a malformed `[load]` table **crashed with a
  traceback instead of exiting 2**. Neither task's tests could have caught it
  alone. When a behaviour moves across a boundary, one task must own a test that
  spans both sides.

From task 4.1, binding on every remaining task in this spec — **read this before
writing a test that claims to cover a normative clause:**

- **A "shall" clause whose *scenario* no fixture reaches will pass review
  indefinitely**, because a green suite is indistinguishable from a covered one.
  Task 4.1 was rejected **three times** on this single defect species, seven
  clauses in total, with the production code traced correct every round. Each
  rejection found *new* unpinned clauses rather than relitigating old ones, so
  the loop was converging but only two clauses per round.
- **What actually terminated it: an exhaustive sweep.** The fourth review
  enumerated all 23 of the task's listed requirements and classified each as
  PINNED (with the test), PRESERVED-ONLY (with the regression test), or UNPINNED
  (with the mutation run). That bounded the remainder at two and closed it in one
  round. **Ask for the sweep up front on any task listing more than a handful of
  requirements** — incremental discovery cannot tell you when it is finished.
- **The specific traps found, all of the same shape — the scenario was
  unreachable, not the assertion wrong:** every stub in `tests/load/conftest.py`
  except `DecliningCalculator` self-guards its modality inside `compute`, so the
  calculator's own defence-in-depth *shadows the engine's gate* and deleting the
  gate changes nothing; the only two-calculator tests registered two calculators
  that **both** support the activity, so the substitutable state Req 10.5 forbids
  was never reached; every `recompute=True` in the suite drove a COMPUTED or
  FOREIGN region, so the SUPERSEDED passthrough was never exercised; and a
  malformed-table test that owns a document cannot distinguish an up-front abort
  from a lazy one, because both leave the bytes unchanged. In each case the fix
  was a fixture that *can observe* the difference — an empty `workouts/`, a
  two-document root, a non-self-guarding stub, a second calculator that must
  never be invoked.
- **Discrimination means sole failure.** Requiring each new test to be the *only*
  failure under its mutation is what caught tests that reddened for unrelated
  reasons. A test that goes red alongside twelve others has not been shown to pin
  anything.
- The peer session on `athlete-benchmarks` hit this same species independently
  and in the same window, and escalated its task 1.3 to a debug subagent when its
  remediation began **oscillating** (each fix installing a new confound) rather
  than converging. Converging-but-incomplete and oscillating need different
  responses: sweep the first, escalate the second.

From task 3.2, binding on task 4.1 (the engine is `arbitrate`'s only call site):

- **`validate_configured` takes a keyword-only `settings_file: Path`**, beyond
  design.md's illustrative pseudocode at ~1140. It is not optional and not drift:
  design.md's own *Error envelope* prose in the same section requires the message
  to name `[load] default_calculator` **in the named settings file**, and
  `LoadSettings` carries only `default_calculator: str | None` with no path —
  `load_load_settings` takes the path separately and uses it for messages alone.
  Task 4.1 supplies it from the `settings_path` it already resolves.
- **`arbitrate` takes the activity, not the modality**, and returns `Selected |
  Ambiguous | NoCalculator`. The forced and configured paths are deliberately
  **sport-blind** — pinned by two mutations that redden when either is narrowed by
  sport. Task 4.1 must therefore keep the engine's own support check
  **unconditional**, per task 3.2's third bullet: selection and enforcement are
  different requirements and the engine must not know which branch selected.
- **RED-phase precedent, deliberately not set.** This task's RED evidence was a
  bare `ModuleNotFoundError` collection error — a new module has no prior behavior
  to flag off and no caller until 4.1. That form is indistinguishable from a test
  file of trivial assertions and proves nothing about discrimination. It was
  accepted only because the reviewer independently ran nine mutations, each
  reddening exactly the tests claiming that branch, none surviving. Do not cite
  this task as licence for a collection-error RED phase without that corroboration.

Carried forward from the shipped first pass, still load-bearing:

- **Athlete-field hint seam (Requirement 3.6):** the calculator contract has no
  hints method. A calculator exposes hints as an *additive* instance attribute
  and the engine reads it generically, keeping the engine and the command surface
  methodology-agnostic per steering. Task 1.1's hinted stub is what exercises
  this now that no calculator ships.
- **Integer-serialization seam:** integer-kind athlete fields must serialize as
  bare TOML integers, because the read-only athlete-inputs reader that
  `workout-docs` uses rejects a float where it wants an integer. Any new scoped
  field must honor this.

From tasks 1.1 and 1.2, now closed but load-bearing:

- **`isolated_registry` is defined once**, in `tests/load/conftest.py`, yielding
  `None`; `test_registry.py` and `test_registry_validation.py` import
  `fitdocs.load.registry` directly. Task 1.2 consolidated the former three-way
  divergence. Do not reintroduce a local redefinition.
- **The stub leakage guard covers all four fixtures** and reads their
  `calculator_id` class attributes, never string literals, so an id rename cannot
  make it vacuous. Each of the four teardowns independently reddens it. Keep this
  property: the guard underwrites the Requirement 13.2 empty-registry invariant.
- **The leakage guard depends on pytest's file-definition collection order**,
  adjudicated as acceptable: the failure mode is fail-open rather than flaky, the
  toolchain is deterministic (no `xdist`, no `pytest-randomly`), and a real leak
  independently reddens ~20 cross-suite plugin tests. Do not "fix" it by adding an
  ordering plugin or chaining it through `isolated_registry` — the latter's
  snapshot/restore would mask exactly the leak under test.

Prose falsified by task 1.3's deletion, deferred to the task owning each file's
boundary. Each statement is currently **factually false** in shipped source:

- `src/fitdocs/load/registry.py:11-13` — named the withdrawn methodology's
  calculator as the built-in registered first on import. Owner: **task 3.2**,
  which already scopes the registry docstring correction.
- `src/fitdocs/load/engine.py:30-31` — described the withdrawn methodology's
  calculator as the built-in registered by importing :mod:`fitdocs.load`.
  Owner: **task 4.1** (added here; it was unassigned).
- ~~`src/fitdocs/load/types.py:57,59,80,82`~~ — **CLOSED by task 2.1**, which
  rewrote those exact docstrings while redefining the result vocabulary and
  neutralized them to `"mycalc.custom_threshold"` / `"mycalc"`. Verified by the
  2.1 reviewer as in-passing cleanup rather than scope creep. **Drop this bullet
  from task 6.4's scope** rather than duplicating the work.
- **Requirement 13.1's "no constants derived from the withdrawn methodology"
  clause has no guard.** Task 1.3's withdrawal guard targets the withdrawn
  calculator's class symbol and its import paths, so it cannot detect a table
  value copied into a surviving module under a neutral name. The 1.3 reviewer
  verified no such copy exists today, but the property is unproven. Owner:
  **task 6.4** — pin the absence of the specific table values.

Requirement 11.2's behavioral invariant is **substantially discharged by task
2.3**, with one narrow residue for task 4.1. Corrected record, superseding the
prescription written during 2.2 and 2.3 — the 2.3 reviewer retracted two clauses
of its own wording as defective:

- **Already proven and mutation-pinned.** Byte-identity and frontmatter identity
  over a full `apply_load` pass on a prior-format computed document are pinned by
  `tests/load/test_engine.py::test_superseded_computed_result_is_skipped_byte_identical_not_erased`.
  A mutation in which the engine's superseded branch infers a `LoadResult` from
  the stamp and atomically writes the frontmatter projection reddens it.
- **Retracted as invalid evidence:** the earlier mutation that had the *classifier*
  build a `LoadResult` and call `apply_frontmatter_load` inline. That function is
  pure and the only writer is `_atomic_write`, so the mutation touched dead code.
  An unobservable violation is not a coverage gap. The invariant is unobservable
  at `docedit`'s boundary by construction, since `classify_load_region` returns a
  classification and cannot write.
- **Retracted as unsatisfiable:** the clause requiring the stamp's
  `calculator_id` to appear *only* inside the skip entry's detail. The
  retained v1 fixture's computed-line constant encodes the withdrawn
  methodology's calculator id inside its own `calculator_id` field, so a
  byte-identical document necessarily still contains the name.
- **The residue task 4.1 must close.** `tests/load/test_engine.py:492-495`
  asserts the document is in `report.skipped` and not in `unsupported`/`computed`,
  but says nothing about `report.restored` — the "never feeds frontmatter restore"
  half of design.md:925-928. A mutation appending a stamp-derived entry to
  `buckets.restored` while writing no bytes **survives all 1732 tests**. Close it
  by asserting the document appears in **none** of `report.computed`,
  `report.restored`, `report.unsupported`; and once 4.1 introduces the
  stamp-derived skip reason, that the stamp's `calculator_id` reaches the skip
  entry's `detail` and no other report field. It must redden under that mutation.
- **Also for 4.1:** HEAD's generic skip reason is now slightly inaccurate prose
  for a superseded region ("load region has unrecognized content" — the content is
  recognized, just unreadable). Correct under 2.3's minimal guard; 4.1 replaces it
  with wording naming the recorded format version and methodology.

Also for task 4.1, from the 2.3 review: `tests/load/test_engine.py:264`
`test_second_identical_pass_writes_nothing` and its `test_feature_e2e.py`
counterpart survive total classifier sabotage because neither asserts the *first*
pass computed anything. Confirmed pre-existing at clean HEAD. 4.1's observable
("a repeated identical pass performs no writes except the single write that brings
a prior-format unsupported region into the current format, stable from the second
pass onward") is where they must be strengthened.

The original 2.2 statement of the obligation follows:

- **Requirement 11.2's behavioral invariant is not yet proven, and the stand-in
  for it expires when 2.3 lands.** design.md:925-928 requires that stamp output
  never constructs a `LoadResult`, never feeds frontmatter restore, and never
  feeds the frontmatter projection — that is what keeps 11.2's "shall not parse
  it partially or infer missing fields" true. At 2.2 there are no callers, so the
  property rests solely on a no-callers grep (`inspect_payload`/`PayloadStamp`
  appear only inside `render.py`). **The moment 2.3 introduces a caller, that
  grep stops being evidence.** Tasks 2.3 and 4.1 must re-establish, with callers
  present, that stamp output never reaches `_result_from_data`, frontmatter
  restore, or `docedit._managed_lines`. A structural field-disjointness test is
  not sufficient — it survives total sabotage of `inspect_payload`.

Intermediate state task 2.4 must resolve, created deliberately by task 2.1:

- **`load_zone` can never be emitted, and `load_points` carries `result.value`.**
  The zone concept is gone from `LoadResult`, so `docedit._managed_lines` has no
  field to derive `load_zone` from and the block was deleted; `result.value` is
  written under the old `load_points` name pending 2.4's rename. Verified safe in
  the interim: `contract.unmanaged_keys` only flags keys *outside*
  `MANAGED_KEYS`, so absence is always legal, and no golden document carries a
  load key. 2.4 renames all three keys atomically with the document-format bump.

From task 2.4's review, for downstream tasks:

- **Task 6.4's atomicity guard must build its subject via a current-format load
  pass, not a legacy document.** `engine.py:319` calls `strip_frontmatter_load` on
  `--recompute`; post-rename that no longer removes `load_points`/`load_zone`, so a
  hypothetical legacy document with a *computed* v1 payload put through
  `--recompute` would end up with the three new keys plus two stale unmanaged ones.
  The population is empirically empty (`~/code/fitdocs-demo/wiki/` has zero
  documents carrying either old key; all 71 are `doc_version: 1`) and `engine.py`
  is task 4.1's boundary, so this is not a defect — but a guard built on a legacy
  document would contradict itself.
- **Legacy-key behavior is settled as acceptable migration, not a defect.** A
  document carrying the old keys now reports them unmanaged, *and* `check` names
  `doc_version is 2, below the current 3` with the remedy `run fitdocs regen` —
  which is the actual fix, since regen rebuilds frontmatter wholesale and the
  restore path re-derives the new keys from the preserved payload. Task 2.4's
  bullet 6 ("every non-managed line preserved byte-for-byte") makes preserving a
  post-rename `load_zone` line mandatory; stripping it would violate the task text.
- **Stale sibling-spec documentation, for `wiki-contract` to pick up:**
  `.kiro/specs/wiki-contract/design.md:365,664` and `.kiro/steering/roadmap.md:432`
  still spell the old `LOAD_KEYS` names.

Method note for every remaining task, learned the hard way in 1.1 and 1.2:

- **Mutation evidence must discriminate.** A mutation whose expected outcome is
  the same under both the correct and the broken implementation is not evidence.
  Two rounds were spent on reports whose stated conclusions did not follow from
  the experiment run. Break the production behavior a test claims to cover,
  confirm that test goes red, and restore byte-identically.
- **Batched mutation loops need `__pycache__` cleared between iterations.**
  Same-size edits inside Python's `(mtime, size)` pyc-invalidation window silently
  reuse the previous iteration's bytecode and fabricate a contradiction.

Obsolete and deliberately dropped:

- **Packaging seam:** the scoped ignore-file negation that existed only to ship
  the withdrawn methodology's tables is removed in task 1.3. No package data
  ships from the load layer, so the broad ignore rule needs no exception.

### From task 7.1 (Amendment 4; seven review rounds, production correct from round 1)

- **A fixture set that varies every axis but one leaves that axis entirely
  unpinned, and no amount of reading finds it.** Each round's survivors sat
  on one unvaried axis: (R1) tier-2 fixtures with `measured_on` and
  `applies_from` ascending *together*; (R2) no serializer fixture with
  `applies_from == measured_on`; (R3) 108 `applies_from` occurrences, none
  in the athlete-wide scope; (R4) the duplicate key never exercised with
  differing `applies_from`; (R5) every `applies_from` fixture in a
  single-entry or homogeneous group, so tier-1 filtering, serializer sort
  and own-entry validation were never reached with a *mixed* group; (R6) no
  ISO-*string* `applies_from` case, and 3.11 pinned on tier 2 only. What
  terminated it was not another incremental round but three explicit
  enumerations: layer × scope × kind (R3), every sentence of the task text
  (R4), and every production site that reads the field in group context
  (R5). Do those enumerations *before* the first report on any task that
  adds a field to a shared record shape.
- **A one-fixture rule with two wrong alternatives needs two fixtures.**
  "Earliest `measured_on`" versus "latest `applies_from`" and "earliest
  `applies_from`": whichever order one fixture uses agrees with one of the
  two wrong keys. The task text originally asked for the reverse-order case
  alone and mis-stated which rule it defeats.
- **`-x` hides the second failure.** A parent-run mutation reported as
  "red, first failure X" proved nothing about the assertion it was written
  for; the reviewer had to re-run without `-x`. Report sole-failure counts
  from a full module run.
- **A reviewer subagent ran `git checkout <file>` on the uncommitted
  implementation (R5)** and rebuilt it from a diff it had captured at
  review start; the blob matched by luck of the capture. The
  no-destructive-reset rule reaches neither template (queue item
  `2026-07-29-destructive-reset-reaches-implementers-nowhere`); until it
  does, every subagent prompt for uncommitted work must say so verbatim and
  prescribe cp-and-restore for mutations.
- **Subagents dispatched from a session rooted at `main` need the absolute
  worktree path and a `cd` prefix on every command**, or the change-guard
  denies their edits; the shell cwd resets between calls.
- **Round-6 remediation was applied by the parent directly** (four
  assertions), a stated downgrade from a subagent implementer; the round-7
  reviewer re-broke every site independently.
- **Non-blocking, left open**: `applies_from`'s participation in
  `Benchmark.__eq__` is unpinned (`field(compare=False)` stays green); the
  carry is pinned by direct field reads. One inequality assertion closes it
  if 7.2's merge tests lean on entry equality.

### From task 7.2 (two review rounds; production correct from round 1)

- **A "nothing stored" assertion over an empty starting profile is `{} ==
  {}`.** Both refusal tests snapshotted `load_profile(tmp_path)` on an empty
  directory; replacing the snapshots with bare literals left the module
  green, under a docstring saying the opposite. The module's own older 6.9
  tests already show the shape: seed a real file, `assert before != {}`,
  compare `path.read_bytes()`. Falsity-before is not satisfied by a
  snapshot -- the snapshot must be *non-trivial*.
- The matrix discipline from 7.1 (layers x scopes x group shapes, built
  before the first report) held: one round, one finding, no oscillation.
- Non-blocking, left open: the refusal message's two dates are asserted
  present but not which label each sits behind.
