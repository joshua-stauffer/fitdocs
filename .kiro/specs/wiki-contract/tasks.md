# Implementation Plan

> Sequencing precondition: this plan builds on the implemented workout-docs,
> training-load, and route-maps specs — the region merge module, the frontmatter
> builder, the data-root layout, the sync/regen/load engines, the CLI shell, and
> the document-scoped warnings channel must all be in place before these tasks
> start.
>
> Ordering rule from the design's Migration Strategy: tasks 1 and 2 are a
> **byte-neutral refactor**. Any golden-document diff before task 3.1 is a bug,
> not expected churn — revert rather than regenerate.

- [x] 1. Foundation: the document-contract leaf
- [x] 1.1 Move the region ownership policy out of the merge mechanism
  - A new pure contract module holding the region ids, the user-owned and tool-filled groupings, the preserved set in its existing order, the two placeholder texts, and the not-computed constant; the merge module keeps only grammar, extraction, merging, and its error type, with its docstring amended to point at the contract for policy
  - Scope limit: this task only defines the constants and repoints the two existing import sites of the not-computed constant (the shared sections module and the load document editor). Migrating the remaining region-id and placeholder literals is owned by tasks 2.2 and 2.3 — do not touch them here
  - The four test modules that import the moved constants from the merge module are repointed at the contract module as part of this task
  - Explicit constant-move task: it crosses module boundaries by design — the two import sites must move with the constants — and lands as one commit
  - Observable: the merge module exports no policy constant, behavior is unchanged with the full suite green after the four test-module import updates, and rendered documents are byte-identical to the committed goldens
  - _Requirements: 1.4_
  - _Boundary: DocumentContract, RegionMerger, SharedSections, LoadDocEditor_

- [x] 1.2 Implement the contract's pure readers and vocabulary
  - Document vocabulary (workout type, generator name, frontmatter fence, key names, the managed key set including the three training-load keys, the format and contract version numbers) plus the readers: fenced-frontmatter parse, frontmatter close-index for line-level editing, workout-document predicate, generated-file predicate, document identity, document format version, source history, archive-ref resolution, unmanaged-key listing, and session-UUID formatting
  - Every reader degrades to an absent value instead of raising; a format version is returned only for a genuine integer (a boolean is rejected), and a missing or unusable value is absent rather than zero
  - Byte-neutrality guard: the document-format version constant is **moved at its existing value**; raising it is task 3.1's job alone, so nothing in tasks 1 and 2 can change a rendered byte
  - The contract re-exports the merge module's marker helpers so consumers need one import, and the public-API test gains the contract module's exported surface
  - Observable: unit tests cover each reader's success and degradation paths, a purity test asserts the module imports nothing from render, sync, load, cli, layout, or model, a policy test asserts the preserved-region order and that the load keys are a subset of the managed keys, and the public-API test pins the new surface
  - _Requirements: 1.1, 1.2, 1.3, 5.7, 6.2_
  - _Boundary: DocumentContract_

- [x] 1.3 (P) Declare the owned paths and declaration directories in the data-root layout
  - Constants naming every path the ownership contract calls fitdocs-owned — the documents directory, its assets subdirectory, the source archive, the cache directory, and the dot-prefixed tool-state directory under the data root (which later holds the sibling ingestion spec's quarantine record) — plus the subset of top-level directories that receive an ownership declaration; the owned-path set must already admit the declaration files themselves, so the guard still holds once task 4.2 makes sync write them; the tool-state directory receives no declaration and is distinct from the data-root pointer file, which lives in the source tree outside the data root; the layout stays a pure leaf with no I/O
  - A guard test that a full run against a fresh data root creates, modifies, and deletes nothing outside the permitted locations. Write it parameterized on two axes so it does not need rewriting later: (a) the **entry point** under test — sync and regeneration today, with a third ingestion entry point expected from the sibling spec — and (b) the **permitted set** — the owned paths plus any location the settings under test configure fitdocs to write into, so that writing into a legitimately configured location is a pass, not a failure. Task 7.2 re-asserts it once declarations, the version gate, and the audit are all in place
  - Observable: the guard test passes for every registered entry point, fails if a stray write is introduced anywhere in the pipeline, and passes when a configured write location is exercised
  - _Requirements: 7.5, 7.6_
  - _Boundary: DataRootLayout_

- [x] 2. Byte-neutral consumer conversion
- [x] 2.1 (P) Convert the sync engine to the contract readers
  - The engine's local frontmatter parser, fence constant, workout-type constant, source-history reader, and archive-ref resolver are deleted in favor of the contract's; document matching precedence (identity first, then source history) is unchanged
  - Observable: the sync test suite passes unchanged and the engine module contains no frontmatter parsing of its own
  - _Requirements: 1.1, 1.2, 1.3_
  - _Boundary: SyncEngine_
  - _Depends: 1.2_

- [x] 2.2 (P) Convert the load engine and document editor to the contract readers
  - The load engine drops its duplicate parser and constants; its archived-source resolution converges on the ref-validating form so a malformed hand-edited entry is skipped rather than joined onto the data root
  - The document editor takes the close-index helper, the load region id, and the managed load-key tuple from the contract, keeping its existing public key tuple as a re-export; its line-level upsert and region classification are untouched
  - Observable: the entire existing load suite passes unchanged, plus a new test showing a malformed source entry resolves to nothing
  - _Requirements: 1.1, 1.3, 1.4_
  - _Boundary: LoadEngine, LoadDocEditor_
  - _Depends: 1.2_

- [x] 2.3 (P) Convert the render layer and layout to the contract definitions
  - The frontmatter builder takes the format version and the session-UUID formatter from the contract and drops its local copy; the layout's identity helper delegates to the same formatter; views and sections take every remaining region id and placeholder text from the contract, so no region literal is left in the render layer
  - The frontmatter test's format-version import is repointed at the contract; the version's value is untouched here
  - Observable: only one session-UUID implementation remains in the package, no region-id literal remains in the render layer, and rendered documents are byte-identical to the committed goldens
  - _Requirements: 1.4, 5.1_
  - _Boundary: FrontmatterBuilder, DocViews, DataRootLayout_
  - _Depends: 1.2_

- [x] 2.4 Prove the consolidation is byte-neutral
  - Run the full suite against the **unmodified** committed golden documents and inline frontmatter assertions; run sync and regen twice over a fixture data root and compare every byte of every document and asset
  - Strict type checking and lint pass over the converted modules
  - Observable: zero golden diffs, byte-identical repeat runs, clean type check and lint — the checkpoint that separates refactor bugs from the intentional format change that follows
  - _Requirements: 1.5, 1.6, 7.1, 7.2, 7.3_
  - _Depends: 2.1, 2.2, 2.3_

- [x] 3. Provenance stamp and document-format version
- [x] 3.1 Add the generator key, the generated-by banner, and the version bump
  - A generator key emitted immediately after the document type and before the format version, keeping the fixed key order and the single serialization path; a constant one-line HTML comment placed between the frontmatter block and the title heading, naming the tool, stating that everything outside the marked regions is replaced on regeneration, and pointing at the in-tree declaration; the format version raised to its next value
  - Nothing in either surface varies between runs or between releases — no tool version, no timestamp
  - The anti-drift test lands here (it can only pass once the generator key is emitted): the managed key set equals exactly the keys the frontmatter builder can emit plus the three training-load keys
  - Observable: tests assert the banner sits outside every extracted region, survives a region round-trip unchanged, is absent from rendered markdown output while present in the source, that two renders of the same inputs are byte-identical, and that the managed key set matches the builder's emittable keys
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 6.1_
  - _Boundary: FrontmatterBuilder, DocViews_
  - _Depends: 2.4_

- [x] 3.2 Regenerate the golden documents and inline frontmatter assertions
  - All committed golden workout documents regenerated through the existing regeneration entry point; the inline frontmatter byte-string assertions in the frontmatter and sync suites updated
  - Observable: the golden diff contains exactly the two added lines per document and nothing else, and the full suite passes
  - _Requirements: 1.5, 1.6_
  - _Depends: 3.1_

- [x] 4. In-tree ownership declaration
- [x] 4.1 (P) Implement the ownership declaration text and placement
  - A declaration module composing each owned directory's agent-instruction file purely from the contract's constants — written-and-tool-owned statement, the owning tool, the contract version, and a pointer to the published contract, plus (for directories holding generated documents only) the user-owned region names and re-derivability by regeneration — with the archive directory's variant stating instead that archived sources are primary, non-derived inputs that are immutable and must not be edited, renamed, or deleted
  - **Amended 2026-07-22 after three review rejections** (see `spec.json` amendments and the Implementation Notes): the emitted text carries **only** the mandated claims of Req 3.2/3.2a/3.3 plus one actionable rule — never add a region marker fitdocs did not write. All long-form editing guidance is deferred to task 7.1's published contract, reached by the URL. Every claim is composed from a single shared fragment table, written once and reused by both directories; no prose may quantify over documents ("each"/"every"/"all documents"), because only strength documents reserve a `workout` region. The emitted texts are pinned as committed byte-goldens, not substring assertions
  - The pointer to the published contract uses the **project documentation URL form**, never a repo-relative documentation path: this text lands in a user's tree, which has no repository layout, and the same text may ship in a distribution artifact whose file list excludes the documentation directory
  - The declaration-state enum uses the project's agreed string-valued enum style
  - Placement rules: write only when absent or when content differs; never write over a file that lacks the generated marker; never write at the data root, in the cache directory, or in the tool-state directory; a read-only inspection variant that classifies each directory as current, missing, stale, or foreign
  - Observable: the two emitted texts match committed byte-goldens; every sentence maps to a mandated Req 3.2/3.2a/3.3 element or the never-add-a-marker rule, and any sentence mapping to none is deleted; unit tests cover creation when absent, an untouched file (bytes and mtime) when already current, a refresh when stale, and a preserved foreign file; the emitted text is plain markdown with no frontmatter and contains no repo-relative documentation path
  - _Requirements: 3.1, 3.2, 3.2a, 3.3, 3.4, 3.5, 3.6_
  - _Boundary: DeclarationWriter_
  - _Depends: 1.2, 1.3_

- [x] 4.2 Wire declaration refresh into sync and regen
  - Both commands refresh the declarations once per run after the data root is resolved and before per-file processing; a foreign file becomes a document-scoped warning that never affects the written/skipped/failed classification or the exit code; the load command does not place declarations
  - The rule is *every engine entry point that writes into the owned tree refreshes the declarations*, not "sync and regen do". Implement the refresh as one shared step both entry points call, so the sibling ingestion spec's third entry point — expected to become the primary ingestion path — reuses it rather than duplicating it. Do not implement that third entry point here; it does not exist in this spec's scope
  - Observable: integration tests show a first run creating both declarations, a second run with no new files leaving every path under the data root byte- and mtime-identical, a foreign declaration preserved with a warning and exit 0, and sync, regen, and load all reporting unchanged document counts with declarations present; the refresh has exactly one implementation, reachable from both entry points
  - _Requirements: 3.5, 3.6, 3.7, 3.8_
  - _Depends: 4.1_

- [x] 5. Document-format gate and frontmatter-key warning
- [x] 5.1 Add the document-format version gate to sync and regen
  - The matched document's frontmatter is parsed once before any write; a version strictly greater than the current one means write nothing for that document, record a warning naming it, and count it as skipped; missing, unusable, or lower versions proceed to the normal merge-and-write path and come out at the current version
  - Both entry points are covered, and their differing consequences are stated: in sync the skipped source stays unarchived and is retried idempotently on the next run, while regen rebuilds from the archive and performs no archive interaction at all — each has its own warning list
  - Document, in the sync engine's module docstring and in the published contract's overwrite section, that this outcome is **not** a completed file: it counts as skipped only because skipped is the report's shared bucket, and no disposition, cleanup, or archival policy may act on it. The authoritative discriminator for a fully-processed source is its presence in the archive, never the skipped label — a downstream policy that relocated a version-gated source would orphan it and permanently defeat the retry
  - Observable: integration tests confirm, for sync, a newer document left byte-identical with its source unarchived, no archive entry created, the run exiting 0, and a second run over the same source repeating the gate rather than treating the source as done; for regen, a newer document left byte-identical, warned, counted as skipped, with the archive untouched; and for both, an older document upgraded with its user-owned regions carried over verbatim
  - _Requirements: 5.4, 5.5, 5.6, 5.8, 5.9_
  - _Boundary: SyncEngine_
  - _Depends: 3.2_

- [x] 5.2 Warn when a rewrite would drop unmanaged frontmatter keys
  - Reusing the frontmatter parsed by the version gate, subtract the managed key set and, when anything remains, record a document-scoped warning naming the document and the sorted key names; the rewrite still proceeds and the run still succeeds
  - Observable: a regeneration over a document carrying a hand-added key warns with that key named, exits 0, and the rewritten document no longer carries it; a document with only managed keys — including after a training-load pass — produces no warning
  - _Requirements: 6.3_
  - _Boundary: SyncEngine_
  - _Depends: 5.1_

- [x] 6. Contract inspection
- [x] 6.1 Implement the read-only contract audit
  - A sorted scan of the documents directory producing findings for out-of-date versions (including missing or unusable ones), newer-than-supported versions, damaged region markers, unmanaged frontmatter keys, and missing, stale, or foreign declarations; each finding carries the affected subject, what was observed, and the action that resolves it
  - Report-value convention shared with the sibling specs: the finding's fields follow the agreed subject/detail/remedy naming — the subject field is named for the convention and documented as always holding a data-root-relative path — and the finding-kind enum uses the project's agreed string-valued enum style. The existing document-scoped warning type from the route-maps spec is already shipped and is not renamed
  - The pass opens no `.fit` file, performs no network access, creates no directory, and reports an unreadable document as a finding rather than raising; a missing documents directory yields zero documents rather than an error
  - Observable: unit tests produce every finding kind from purpose-built fixture trees, a clean tree yields no findings, and a before/after directory snapshot proves the pass writes nothing
  - _Requirements: 5.3, 5.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.8_
  - _Boundary: ContractAudit_
  - _Depends: 1.2, 4.1_

- [x] 6.2 Add the check command and its findings presentation
  - A command resolving the data root through the existing resolver, running the audit, and rendering a summary table plus a per-finding detail listing in the established reporting style; no tile store, no athlete profile, no load pass
  - Exit codes map onto the existing contract: nothing found exits success, any findings exit with the per-document failure status, an unresolvable data root exits with the configuration-error status after scanning nothing
  - State the project-wide data-root posture rule in the command's documentation, since this is the first new command to exercise it: *a command that describes a tree requires a data root; a command that describes the installed tool does not.* This command describes a tree, so an unresolvable data root is a hard configuration error. Note that the sibling distribution spec's compatibility document carries the project-wide statement of the rule; do not restate it for the sibling specs' commands here
  - Observable: CLI tests cover a clean tree (success exit with a no-findings line), a tree containing an out-of-date document, a damaged document, an unmanaged key, and a missing declaration (failure exit with every path and remedy present in the output), and an unresolvable data root
  - _Requirements: 8.1, 8.6, 8.7_
  - _Depends: 6.1_

- [x] 7. Published contract and feature validation
- [x] 7.1 (P) Write the published ownership contract and its conformance test
  - A versioned contract document covering: the owned paths — including the dot-prefixed tool-state directory — and the statement that fitdocs writes nowhere else; an explicit clause for **user-configured locations fitdocs may create**, stating that configuring such a location (today, the sibling ingestion spec's intake directory and its optional processed subdirectory) grants fitdocs create/write rights there, that these locations are named in the settings file rather than fixed by the contract, and that configuring one widens nothing else; the user-owned regions and how to edit them, plus the tool-filled load region; what regeneration replaces and preserves; frontmatter ownership with the full managed key list and the rule that hand-authored content belongs in the notes region; the user-owned and shared configuration files and the unknown-key preservation guarantee for those fitdocs writes; the overwrite semantics of every command including forced re-processing and the statement that no operation discards user-owned region content; commit ordering and re-derivability from the archive; document-format versions, regeneration as the migration path, and the newer-version refusal — **including task 5.1's deferred clause** (Req 5.9): a version-gated document counts as *skipped* only because skipped is the report's shared presentation bucket, it is **not** a completed file, no disposition/cleanup/archival policy may act on it, and presence in the archive — never the skipped label — is the authoritative discriminator for a fully-processed source. The wording ships in `src/fitdocs/sync.py`'s module docstring and must be echoed here; guidance for marking generated files in a version-controlled wiki together with the statement that fitdocs writes no such configuration; and how to reference the in-tree declaration from a root instructions file the wiki owns
  - A README ownership section pointing at it by the project documentation URL, not a repo-relative path — the README is rendered into the distribution metadata, where a repo-relative documentation path does not resolve
  - Observable: a conformance test parses the document's enumerated lists and asserts set equality with the layout's owned paths (now including the tool-state directory), the contract's preserved regions, and the contract's managed keys, and asserts the stated contract version matches the code; the configured-location clause is present and is prose rather than an enumerated owned path
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 6.4, 7.4_
  - _Boundary: ContractDocs_
  - _Depends: 1.2, 1.3_

- [x] 7.2 End-to-end ownership and migration validation
  - A full round trip: sync a fixture source into an empty data root, hand-edit the user-owned region, run forced re-processing and a regeneration, and assert the edit survives both, the provenance stamp and generator key are present, declarations exist, and no path outside the permitted set (owned paths plus any configured write location) was created or modified
  - **Version-gate bypass, found during 7.1 review (Req 5.5, 5.8) — a genuine engine defect, not a doc bug:** `sync`/`regen` correctly refuse to rewrite a document recording a newer `doc_version`, but the training-load pass the *CLI commands* run afterwards (`cli.py`'s `_run_load_pass`) never consults `doc_version`, so it rewrites the gated document's `load` region and its three load keys anyway. Req 5.5 says such a document is left unchanged; end-to-end it is not. Task 5.1's tests pass because they exercise the `sync()`/`regen()` engine functions, not the commands. Proven against the real CLI: set `doc_version: 99`, run `fitdocs regen`, observe exit 0, the "newer" warning, and a modified load region. Fix here and assert it end-to-end; the contract currently documents the gap as a parenthetical
  - **Cross-command symlink defect, found during 6.1 review (Req 7.5, 7.6):** a `workouts/*.md` symlink pointing outside the data root is returned by `sync._discover_documents`, so a writing entry point follows it and writes **outside the data root**. The audit refuses to follow symlinks and reports them, so the two commands disagree about the same file. Reproduction: place a `workouts/x.md` symlink to a path outside the root and run regen. Confinement is this task's territory; fix it here, not in 6.x (an audit reports, it does not change engine behavior)
  - Re-assert task 1.3's confinement guard for every entry point this spec ships, using the parameterized form, so registering the sibling ingestion spec's entry point later is an addition to a list rather than a rewrite
  - Migration by regeneration: seed a data root with previous-format documents carrying user-owned content, confirm the inspection reports them as out of date, run a regeneration, and confirm every document returns at the current format version with its regions intact and the inspection then clean
  - Observable: the full test suite, strict type checking, and lint pass clean with the new coverage, and the whole run stays offline
  - _Requirements: 1.6, 3.7, 5.4, 5.5, 5.6, 5.8, 7.1, 7.3, 7.5, 7.6_
  - _Depends: 5.2, 6.2, 7.1_

## Implementation Notes

- 3.1: the goldens and the inline frontmatter assertions are intentionally left failing at this commit (8 golden docs, 3 assertions in `tests/render/test_frontmatter.py`, and `test_contract.py::test_doc_version_equals_the_version_stamped_on_the_committed_goldens`, which reads a golden). Task 3.2 owns all four. Baseline carries 5 unrelated rich-console-width failures in `tests/load/test_cli_load.py`, `tests/load/test_prompts.py`, and `tests/test_cli.py` — not caused by this spec.
- 3.1: the anti-drift test walks `build_frontmatter`'s AST for `data[<key>] = ...` assignments only; `data.update(...)`, `data |= {...}`, and `data.setdefault(...)` would evade it. Safe while `data[k] = v` stays the module's sole emission idiom — if that changes, tighten the walk.
- 3.1: `ruff format --check` is NOT clean repo-wide (18 pre-existing files). It is not in the canonical validation set; use `ruff check` + `mypy src/`.
- 3.2: the golden regeneration entry point is `uv run python -m tests.render.test_golden_docs` (documented in that module's docstring). Goldens are never hand-edited — the suite reads them back and asserts byte-equality with live render output.
- 3.2: task 3.2's observable says "exactly the two added lines per document"; the real per-golden diff is 4 insertions / 1 deletion — the two content lines (`generator:`, banner) plus the `doc_version` 1→2 modification and the banner's blank separator. Spec phrasing, not drift.
- 3.2: `design.md`'s Modified Files listing of `tests/test_sync.py` is over-broad. Its `doc_version: 1` sites are hand-authored *old-format* fixtures asserted byte-for-byte unchanged; the only helper reading a written document asserts `sources` only. Correctly left untouched — do not "fix" them in a later task.
- 4.1: was blocked mid-implementation on a spec conflict and unblocked by a human-ratified amendment (Req 3.2 / new 3.2a, recorded in `spec.json`); the `_Blocked:_` marker was removed when the task resumed, so this note is the surviving record. Root cause was not wording: `design.md`'s DeclarationWriter section specifies placement exhaustively and the wording of zero sentences, so the implementer must invent policy prose from the code while task 7.1 (which authors the authoritative version) is three waves later.
- 4.1: substring assertions on generated prose are not a viable verification strategy — a text asserting the opposite of the truth on all three load-bearing claims passed 40/40. If 4.1 is retried, pin the emitted texts as committed byte-goldens (mirroring `tests/render/test_golden_docs.py`) so every prose change is a reviewable diff, and keep only structural assertions in `test_declaration.py`.
- 4.1: never let declaration prose quantify over documents ("each"/"every"/"all documents"). `WORKOUT_REGION` is emitted only by `render_strength`, so 7 of 8 goldens carry `notes` + `load` alone. Rounds 2 and 3 both died on this. Name the regions from `contract.USER_REGIONS`/`TOOL_REGIONS` and state that the markers present in a file are authoritative.
- 4.1: `regen` drops the three tool-written frontmatter load keys (`load_points`, `load_methodology`, `load_zone`) while preserving the `load` *region* body — `merge_regions` splices region interiors only, so frontmatter comes wholly from the fresh render. Self-healing: `apply_load`'s Restore path (`load/engine.py:163-166`) re-derives the keys from the preserved region payload with no recomputation or prompting. Left unstated in the declaration deliberately — narrowing the first re-derivability clause would re-add the wording bloat the 2026-07-22 amendment removed, and no user content is at risk.
- 4.1: took 5 review rounds + a debug cycle + a spec amendment. What finally worked: one shared claim-fragment table with a CLAIM ANCHOR comment per fragment naming the code that makes it true, emitted texts pinned as committed byte-goldens, and behavioral anchor tests for the facts the prose asserts. What did not work: substring assertions on generated prose — a text asserting the opposite of the truth passed 40/40 of them.
- 4.2: writing `AGENTS.md` on every run silently defeats any tree-walking assertion that proves "a document was written" by matching `workouts/*.md`. Five such assertions existed; four were narrowed with the task, and `tests/test_confinement.py`'s task-1.3 non-vacuity check was missed until review — a zero-writing `sync` passed it. All five now exclude `DECLARATION_FILENAME`. Any future task adding a file to an owned directory must re-audit them.
- 4.2: `tests/load/test_engine_contract.py` had the suite's only unfiltered `next(glob("*.md"))`; it became order-dependent once `AGENTS.md` shared the directory (name order on APFS, hash order on ext4/CI). Now sorted and declaration-filtered.
- 4.2: a once-per-run step needs ≥2 sources to be distinguishable from a per-file one. The foreign-declaration sync test stages two deliberately; with one, moving the refresh into the loop was undetectable.
- 5.1: adding a second cause to an existing report bucket or warning channel falsifies every docstring that enumerated the old causes. `SyncReport.skipped` said "already archived" and `SyncReport.warnings` said "a map that could not be rendered"; both are field-level docs a downstream consumer reads first, and both were wrong before review caught them. When adding a cause, grep the whole file for prose enumerating that field.
- 5.1: the warning channel now has exactly three causes — map omission (4.3/4.4), foreign ownership declaration (3.6), version-gate skip (5.5) — at three `DocWarning(` sites reaching two append sites. Verified mechanically; re-verify rather than trusting this note.
- 5.1: `--force` does NOT bypass the version gate (Req 5.5 grants no exemption). Pinned by the `[force]` parametrization of the gate test; before that it was pinned only incidentally via regen, which passes `force=True` internally.
- 5.2: `_process_file`/`_process_isolated` now return `tuple[DocWarning, ...]`, not an optional scalar — one rewrite can legitimately emit both an unmanaged-key notice and a map omission. Intra-file order is fixed by statement order (unmanaged-key before map) and is now a documented guarantee on `SyncReport.warnings`, not an accident.
- 5.2: `DocWarning`'s summary line no longer enumerates its causes at all — it points at `SyncReport.warnings`. That line had been falsified three times running (4.2, 5.1, 5.2); a line that lists nothing cannot go stale. `cli.py:337-338` still says "every map warning" and is the last stale enumeration — out of 5.2's boundary, fix it in a later task.
- 5.2: an ordering test needs NON-MONOTONIC input. Keys inserted in strictly descending order make `reversed(insertion) == sorted()`, so the test cannot tell sorted from reversed-insertion at any key count — adding a third key does not help.
- 5.2: a widened signature needs a test that dies when it is narrowed back. `tuple(warnings[:1])` passed all 1398 tests until one was added for the two-warning case.
- 6.1: a finding's `remedy` must be traced, not guessed. Every unreadable document originally said "run `fitdocs regen`" — but `sync._read_frontmatter` swallows `OSError`/`UnicodeDecodeError`, so regen SKIPS those paths and the remedy resolved nothing. Req 8.6 says "the action that resolves it"; if you name a command, run it against the condition first.
- 6.1: `except OSError` is one bucket for many causes. Mapping it to "restore read permission" emitted that remedy for a file deleted between the scan and the read ("No such file or directory"). `PermissionError` is now caught first.
- 6.1: asserting `remedy != ""` pins nothing. Collapsing all four unreadable remedies to one shared string survived the suite until each cause asserted a distinctive substring.
- 6.2: the five pre-existing CLI failures are caused by Rich's *highlighting*, not wrapping — `--out` renders as `\x1b[1;36m-\x1b[0m\x1b[1;36m-out\x1b[0m`, so the literal is absent from the raw bytes. Two are in `test_cli.py`, one in `load/test_cli_load.py`, two in `load/test_prompts.py` (no table involved). Stripping ANSI fixes all of them; whitespace collapsing does not, and cannot recover a wrapped bordered table cell.
- 6.2: assert remedy fragments that are DISTINCTIVE to one remedy. `"fitdocs regen"` also appears in the declaration remedy and `"notes"`/`"region"` in the damaged-regions detail, so three of four remedies could be blanked with the suite green.
- 6.2 (non-blocking, for a later task): only the load-pass half of the design's "no tile store, no athlete profile, no load pass" is test-guarded; the other two were proven by hand but are unpinned. Also `cli.py`'s docstring cites Req 8.1 for two different specs' numbering four lines apart.
- 7.1: took three rounds, each of which introduced a NEW false absolute while fixing the last one. The document opened by claiming every owned directory carries an `AGENTS.md` (2 of 5 do, and it contradicted itself 27 lines later) and that all three contract surfaces are generated so they "cannot disagree with the tool's actual behavior" (this document is hand-written; only its four enumerated lists are tested). Grep the finished text for every/all/never/always/cannot/only and check each hit against code — and produce the list, don't assert you did it.
- 7.1: `sync` and `regen` each run a training-load pass AFTER writing documents, over every workout document in the data root — not only the ones the run wrote. `regen`'s pass is not restore-only: placeholder and unsupported regions fall through to full computation. Non-interactive prevents prompting, not computing.
- 7.1: a conformance test on prose must assert set EQUALITY, not membership. A subset check passes when the document lists paths that are not owned — the dangerous direction for a document telling users what a tool may touch.
- 7.2: the archive-orphan duplicate — `regen` rendering a second, separate document from an archive that is referenced only by a symlink `_discover_documents` refused to read — is accepted as-is for this spec; the warning already names the consequence, so it is not a silent failure. Do **not** describe this as "unavoidable without reading through the symlink": Req 7.5/7.6 forbid *writing* outside owned paths, not *reading* a symlink's target to check whether its sha is referenced elsewhere, and reading it would not violate confinement on its own. A conservative alternative exists at zero cost: when the once-per-run symlink scan (`_scan_symlinked_documents`) finds at least one symlink under `workouts/`, the "which archives are referenced" accounting for that run is known incomplete, so `regen` could suppress the unreferenced-archive-renders-fresh step entirely for that run and say so in a warning, trading the duplicate for a documented no-op on the orphaned archive. This alternative is **not implemented** — the duplicate remains the shipped behavior — this note exists only so a future task does not repeat the false "unavoidable" justification while deciding whether to take it.
- 7.2: testing an ENGINE FUNCTION is not testing the COMMAND. Both defects this task fixed were invisible to green suites because the tests called `sync()`/`regen()` while the bug lived in what `cli.py` runs afterwards. Any guarantee a requirement states about a command must be asserted through the CLI.
- 7.2: redundant guards HIDE the one that matters. `sync.py` carried its own `is_symlink` checks, so deleting the shared refusal in `docio.py` killed zero tests; removing the redundant copies made the same mutation kill five. One enforcement point, mutation-guarded.
- 7.2: a per-file scan cannot see a property of the data root. Moving the symlink scan to once per run (beside `refresh_declarations`) closed the steady-state-resync hole, made sync and regen warn identically by construction, and let the `warnings` threading and dedup be DELETED — less machinery, more coverage.
- 7.2: `_scan_symlinked_documents` is the fifth `*.md` walk in `src/` and the first added since 4.2; it shipped without the `AGENTS.md` exclusion, violating Req 3.7, exactly as 4.2's note warned. The note existed and was still missed — when adding a walk, grep the other four and copy their filter.
- **Feature-level validation gate (2026-07-22, NO-GO — fixed post-hoc, all 24 tasks stayed complete).** A sixth `*.md` walk had the same defect 7.2's note warned about, in a place none of the audits above checked: `audit()` itself. Its unreadable-document branch (a symlink, non-UTF-8, permission-denied, or directory-at-path `workouts/AGENTS.md`) ran *before* the declaration-filename exclusion, so an unreadable declaration produced a spurious `OUTDATED_VERSION` finding in addition to the correct `DECLARATION_*` one — violating Req 3.7 in exactly the module whose own docstring claimed the opposite. Fixed by excluding `DECLARATION_FILENAME` before the unreadable branch in `audit()`; `tests/test_audit.py` gained four mutation-guarded regression tests (symlink, non-UTF-8, permission-denied, directory) plus the pre-existing readable-case test.
- Same gate: `load` was an unregistered writing entry point. `apply_load` writes `<data_root>/athlete.toml` via `save_profile` — a real write outside `OWNED_PATHS` (by design: the published contract calls `athlete.toml` *shared*, not owned) that `tests/test_confinement.py`'s `WRITING_ENTRY_POINTS` never exercised. Fixed by adding `PERMITTED_SHARED_FILES` as a set distinct from `OWNED_PATHS` (documented as such, not a widening of it) and registering `load` as a third `WRITING_ENTRY_POINTS` entry with a scripted withdrawn-calculator compute session that genuinely writes both a document and `athlete.toml` — proven by mutation (reverting the permitted-set union fails the new `load` case).
- Same gate: Req 8.8 ("no network, no `.fit` read") had no test. Added `tests/test_audit.py::test_audit_completes_without_network_access_or_reading_any_fit_file`, reusing `tests.test_determinism._no_socket` (not a second copy) plus a dedicated guard over `builtins.open`, `Path.read_bytes`, and `Path.read_text` — all three, since `read_text`/`read_bytes` bypass `builtins.open` entirely — over a data root holding a real archived `.fit` source. Verified by mutation (making `audit` read the archived file trips the guard immediately).
- Same gate: the vocabulary anti-drift guard (`tests/test_contract_consumers.py`) omitted every module this feature itself added — `audit.py`, `declaration.py`, `docio.py`, `cli.py` — leaving exactly its own new surface unguarded. Proven: injecting `_fence = "---"`, `_type = "workout"`, `_region = "notes"` into `audit.py` passed the full suite before registration. Fixed by adding all four to `CONVERTED_MODULES` with their `CONTRACT_BINDINGS` (`cli.py` binds nothing directly — it delegates to `audit`/`declaration`/`sync` — and is registered with an empty binding tuple purely so a future direct contract literal in the CLI is caught).
- Same gate: `Finding.detail` (the "what was observed" half of Req 8.6) was printed by `_report_audit` but never asserted — deleting the print line left the full suite green. Fixed by adding a distinctive detail-fragment assertion per finding kind to `tests/test_cli_check.py`'s existing four-finding-kind test, mirroring the existing remedy assertions. Verified by mutation (deleting the print line fails the four new assertions).
- Same gate: two structural changes from task 7.2 — `docio.py` and the `LoadEngine` document-format version gate — were real and sound but undocumented. `design.md`'s File Structure Plan now lists `docio.py`; the `LoadEngine` component section now states the version-gate duplication and its requirement coverage (5.5, 5.8); a fourth cross-spec integration obligation records that a writing entry point must read through `docio.read_frontmatter` and run the once-per-run symlink scan beside `refresh_declarations`; `spec.json` gained a corresponding amendment entry; `tests/test_public_api.py` now pins `docio`'s exported surface alongside `contract`, `declaration`, and `audit`.
