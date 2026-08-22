# Research & Design Decisions: wiki-contract

**Date**: 2026-07-21
**Inputs**: `brief.md`, `requirements.md` (phase: requirements-generated), steering (`product.md`, `tech.md`, `structure.md`, `roadmap.md` Phase 3), full codebase investigation of `docmerge.py` / `layout.py` / `sync.py` / `render/frontmatter.py` / `render/views.py` / `render/sections.py` / `load/engine.py` / `load/docedit.py` / `cli.py`, the workout-docs and training-load spec documents, and external research on the AGENTS.md convention (web, current as of 2026-07-21).

---

## Summary

- **Feature**: `wiki-contract`
- **Discovery Scope**: Extension (integration-focused, brownfield). No new subsystem, no new dependency, no new I/O class. The feature is a consolidation refactor plus three declaration surfaces plus one read-only command.
- **Key Findings**:
  1. The duplication the brief describes is real and slightly worse than stated: the frontmatter parser exists in **three** variants, the session-UUID formatter in **two** byte-identical copies, the `"workout"` type constant in **two**, the document scan in **two**, and the source-history resolver in **two divergent** forms. `PRESERVED_REGIONS` is declared in `docmerge.py` and **imported nowhere** — every region id is hardcoded as a string literal at four call sites.
  2. `docmerge.py` is already a pure *mechanism* module (generic over region ids); the two policy constants that live there (`PRESERVED_REGIONS`, `LOAD_NOT_COMPUTED`) are unused by its own functions. Moving policy out and leaving mechanism behind is a pure-refactor move with zero behavior change.
  3. There is **no provenance surface at all** today beyond `sources` and `uuid`, and **no user-facing document** on regeneration or user-content preservation — that contract exists only in module docstrings and `README.md`.
  4. Adding any frontmatter key breaks eight committed golden documents and four inline byte-string assertions. That cost is unavoidable and is precisely what `doc_version` exists to signal, so the format bump and the golden regeneration are one coordinated change.
  5. `sync.py` has **no `doc_version` awareness whatsoever** — it never reads or compares it. Drift detection is entirely greenfield; migration-by-regeneration already works mechanically (regen re-renders from the archive) but is undocumented and unreported.
  6. `AGENTS.md` is the settled cross-tool convention (Linux Foundation / Agentic AI Foundation stewardship since Dec 2025, ~60k repositories, read natively by Codex, Cursor, Copilot coding agent, Gemini CLI, Zed, Aider, Jules, Devin and others), and **nested per-directory files are idiomatic** — agents read the nearest file in the tree. This maps exactly onto "declare ownership inside the directories fitdocs owns, and never touch the wiki root."

---

## Research Log

### Duplication inventory — what a single document-contract definition must absorb

- **Context**: The brief asserts frontmatter schema and `uuid`/`sources` identity are re-parsed in three places. Requirement 1 turns that into a behavior guarantee, so the exact inventory had to be established before designing the module.
- **Sources Consulted**: `src/fitdocs/sync.py`, `src/fitdocs/load/engine.py`, `src/fitdocs/load/docedit.py`, `src/fitdocs/render/frontmatter.py`, `src/fitdocs/layout.py`, `src/fitdocs/docmerge.py`, `src/fitdocs/render/views.py`, `src/fitdocs/render/sections.py`.
- **Findings**:

  | Concern | Copies | Locations | Divergence |
  |---------|--------|-----------|------------|
  | Fenced-frontmatter parse | 3 | `sync.py:679-692`, `load/engine.py:426-443`, `load/docedit.py:248-259` | The first two are **byte-identical**; `docedit`'s is a line-index variant over `split("\n")` (lossless, needed for line-level upsert) rather than `splitlines()` |
  | `"workout"` type constant | 2 | `sync.py:95`, `load/engine.py:82` | identical |
  | `"---"` fence constant | 3 | `sync.py:98`, `load/engine.py:85`, `load/docedit.py:64` | identical |
  | Session-UUID formatting | 2 | `layout.py:167-181`, `render/frontmatter.py:57-74` | **byte-identical**; the render copy exists only to keep `render` free of `layout` |
  | `sources` history reader | 2 | `sync.py:695-700` (tuple of strings), `load/engine.py:405-423` (last entry → path) | **divergent**: `sync` resolves a ref via `_sha_of_ref` + `archive_path`; `engine` joins the raw ref onto the data root |
  | Workout-document scan | 2 | `sync.py:594-612`, `load/engine.py:382-403` | same predicate, different return shape |
  | Region ids as literals | 4 | `views.py:194` (`"workout"`), `sections.py:558` (`"load"`), `sections.py:567` (`"notes"`), `docedit.py:63` (`_LOAD_REGION_ID`) | `PRESERVED_REGIONS` is imported by none of them |

- **Implications**: The contract module must expose (a) a frontmatter parse returning a mapping or `None`, (b) a fence-locating helper for line-level editing that does not force `docedit` to change its lossless split, (c) the type/identity/sources accessors, (d) the session-UUID formatter, (e) the region ownership policy, (f) `DOC_VERSION`, (g) the managed-key set. `sync` and `engine`'s divergent source resolvers must converge on `sync`'s (ref-parsing) form, which validates the ref shape instead of trusting it — a strictly safer behavior that keeps existing outcomes for well-formed refs.

### Region policy vs. region mechanism

- **Context**: The brief's hard constraint is "no behavior change to merge semantics". The contract module must therefore not touch the merge algorithm.
- **Findings**: `docmerge.py` imports only `re` and is fully generic over region ids: `_scan`, `extract_regions`, and `merge_regions` never reference `PRESERVED_REGIONS`. Both `PRESERVED_REGIONS` and `LOAD_NOT_COMPUTED` are *policy* constants parked in the mechanism module — `LOAD_NOT_COMPUTED` is imported by `render/sections.py` and `load/docedit.py`; `PRESERVED_REGIONS` by nobody.
- **Implications**: Move the policy constants into the contract module and leave `docmerge.py` as pure grammar + merge. The dependency direction is clean: `docmerge` (leaf, stdlib only) ← `contract` (leaf, `docmerge` + `yaml`) ← every consumer. The marker grammar, `RegionError` semantics, and `merge_regions` behavior are declared verbatim by the contract document and changed in no way.

### Frontmatter key ownership — what actually happens today

- **Context**: The brief says user frontmatter keys "survive merge by accident, not by contract". The truth had to be checked before writing Requirement 6.
- **Findings**: They do **not** survive at all. `build_frontmatter` constructs the mapping from scratch and emits it with one `yaml.safe_dump`; `merge_regions` takes everything outside regions from the fresh render, and the frontmatter block is outside every region. Confirmation from the adjacent spec: training-load's engine has a dedicated *restore* pass precisely because its three keys are wiped by every regeneration (`training-load/design.md`: "regenerated documents lose them until the next pass").
- **Implications**: The honest contract is "the frontmatter block is tool-owned and rewritten in full; unmanaged keys are not preserved; hand-authored content belongs in the `notes` region". Implementing preservation instead would change merge semantics (forbidden by the brief) and would collide with training-load's restore design. But *silent* loss contradicts the existing `merge_regions` philosophy ("silent content loss is forbidden"), so the drop is reported through the document-scoped warning channel — declaration plus observability, no mechanism change.

### Provenance surface and determinism

- **Context**: Requirement 4 wants a generated-by stamp; Requirement 1.5/1.6 forbid non-determinism.
- **Findings**: Nothing in a generated document names fitdocs today (checked against `tests/render/golden_docs/minimal.md`). `fitdocs.model.Provenance` exists but carries decode diagnostics and surfaces only in the Device & Data Quality section. A tool version or generation timestamp in the document would make every release rewrite every document and would break the "same inputs → same bytes" guarantee that the golden suite enforces.
- **Implications**: Provenance is two fixed, version-free artifacts: a `generator: fitdocs` frontmatter key (machine-readable ownership marker, distinct from the forgeable `type: workout`) and an HTML-comment banner immediately after the frontmatter (visible in source, invisible when rendered, outside every region). `doc_version` remains the only compatibility signal.

### `doc_version` today and the migration story

- **Context**: Requirement 5 needs drift detection and a downgrade refusal.
- **Findings**: `DOC_VERSION = 1` is written by `build_frontmatter` and read by nothing. `regen` already reconstructs every document from `fit-archive/` + `athlete.toml`, so migration-by-regeneration is mechanically true and merely undeclared. There is no guard against rewriting a document produced by a newer fitdocs.
- **Implications**: Bump to `2` (the provenance stamp changes the format), add a read of the existing document's version at the two points that rewrite documents (`sync`'s matched-document path and `regen`), skip-and-report when it is newer, and report out-of-date documents through the same channel. Missing or unusable versions count as out of date (never as newer) so a hand-made or corrupted document is never mistaken for a future format.

### AGENTS.md as the declaration format

- **Context**: The declaration must be read by LLM agents maintaining the wiki, without fitdocs writing outside its own tree.
- **Sources Consulted**: [agents.md](https://agents.md/), [OpenAI Codex AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md), [AGENTS.md advanced patterns — nested hierarchies](https://codex.danielvaughan.com/2026/03/26/agents-md-advanced-patterns/), [The agent-native repo](https://www.harness.io/blog/the-agent-native-repo-why-agents-md-is-the-new-standard).
- **Findings**: `AGENTS.md` is stewarded by the Agentic AI Foundation (Linux Foundation) since December 2025, is present in roughly 60k repositories, and is read natively by Codex, Cursor, GitHub Copilot's coding agent, Windsurf, Amp, Aider, Gemini CLI, Zed, Jules, Devin and Junie. Nested per-directory files are the documented idiom: agents read the nearest file in the tree, so a directory-scoped file governs work inside that directory. OpenAI's own Codex repository ships 88 of them.
- **Implications**: `AGENTS.md` is the correct filename and the nested idiom is exactly the boundary fitdocs needs — a file in `workouts/` and one in `fit-archive/`, and **never** one at the data root, which the wiki owns. Tools keyed to a different filename (e.g. `CLAUDE.md`) are handled by documentation: the published contract shows the one-line reference a user adds to their own root instructions file. fitdocs does not write that file.

### Write semantics of the existing pipeline (accuracy check for the published contract)

- **Context**: A published contract must not over-claim. The brief's Current State says "writes are atomic".
- **Findings**: `sync._write_outputs` uses plain `Path.write_text` / `write_bytes` in a deliberate commit order — assets, then the document, then the archive **last and write-once**, because archive presence is the processed-state marker. `load/engine._atomic_write` does use `tempfile.mkstemp` + `os.replace`. So per-file atomicity holds for the load pass but not for the sync writer; what the sync writer guarantees is *crash-safe idempotency* via commit ordering, not per-file atomic replacement.
- **Implications**: The published contract states commit ordering and re-derivability, not blanket atomicity. Changing `sync`'s write strategy is out of boundary for this spec (it is a behavior change with no requirement behind it); the discrepancy is recorded here so a later spec can pick it up.

### Where drift and inspection findings surface

- **Context**: Requirements 3.6, 5.3, 5.5, 6.3 and 8 all need a reporting channel.
- **Findings**: route-maps added `DocWarning(doc, detail)` and `SyncReport.warnings` as a strictly additive, exit-code-neutral channel (`sync.py:168-206`); the CLI already renders a warnings count row and per-document detail. Exit codes are fixed at 0 / 1 / 2 (`cli.py:76-80`).
- **Implications**: Every new non-fatal signal from sync/regen rides the existing warnings channel — no new reporting concept, no exit-code change. The inspection command needs its own report type because its findings are not sync outcomes, but it reuses the same rich-table presentation and the same three exit codes.

---

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Verdict |
|--------|-------------|-----------|---------------------|---------|
| **A. Contract as a pure leaf module** | One new `contract.py` leaf holding schema, identity, region policy, managed keys, `DOC_VERSION`; every consumer imports it | Matches the existing leaf pattern (`docmerge`, `layout`); no cycles; trivially testable; mypy-strict friendly | Slightly widens the number of leaves | **Selected** |
| B. Extend `docmerge.py` into the contract module | Put the schema and identity next to the region grammar | One fewer module | Conflates mechanism with policy; forces `docmerge` to depend on `yaml`; contradicts "declare the merge mechanism as-is" | Rejected |
| C. Contract as a package (`contract/`) with submodules | Split schema / identity / regions / declaration | Room to grow | Speculative structure for ~200 lines of policy; violates the simplification lens | Rejected |
| D. Runtime-enforced ownership (read-only files, git hooks) | Prevent edits mechanically | Strong guarantee | Explicitly out of scope in the brief; hostile in a user's own wiki; breaks the user-owned regions | Rejected |

## Design Decisions

### Decision: One pure contract leaf, mechanism left untouched

- **Context**: Requirement 1 demands identical interpretation across commands without altering merge semantics.
- **Alternatives Considered**: 1. Absorb `docmerge` into the contract module. 2. Leave the duplicates and only publish documentation.
- **Selected Approach**: `src/fitdocs/contract.py` — a pure leaf importing `docmerge` and `yaml` — owns the frontmatter schema (managed key set, `DOC_VERSION`), document identity (`type`, `uuid`, `sources`, session-UUID formatting, archive-ref resolution), and region ownership policy (`USER_REGIONS`, `TOOL_REGIONS`, `PRESERVED_REGIONS`, placeholder and not-computed constants). `docmerge.py` keeps grammar, `extract_regions`, `merge_regions`, `RegionError` and loses only the two policy constants.
- **Rationale**: Preserves the "leaf modules with one responsibility" structure already in the codebase, keeps the merge algorithm literally untouched (the strongest possible answer to the no-behavior-change constraint), and gives the declaration artifacts a single place to read the contract from so the emitted `AGENTS.md` can never drift from the code.
- **Trade-offs**: Consumers gain one import; `render/frontmatter.py` gains a dependency on a non-render module — acceptable because `contract` is a leaf with no I/O and no CLI/layout coupling, which was the original reason the render copy existed.
- **Follow-up**: Verify `mypy --strict` and that no import cycle appears between `render` and `contract`.

### Decision: Frontmatter is tool-owned; drops are warned, not prevented

- **Context**: Requirement 6; the brief forbids merge-semantics changes.
- **Alternatives Considered**: 1. Preserve unmanaged keys through regeneration. 2. Fail the document when unmanaged keys are present. 3. Say nothing.
- **Selected Approach**: Declare the block tool-owned and rewritten in full; publish the managed key set; emit a document-scoped warning naming the document and the dropped keys when a regeneration would lose unmanaged keys.
- **Rationale**: Preservation would change merge behavior and collide with training-load's restore pass, which exists because the keys *are* wiped. Failing would make a benign user habit block a run. Warning matches `docmerge`'s existing rule that content loss must never be silent.
- **Trade-offs**: Users who want durable custom metadata must use the `notes` region; the contract and the emitted declaration both say so.
- **Follow-up**: Confirm the warning never fires for the three training-load keys (they are managed) and never for a first-time render.

### Decision: Version-free provenance

- **Context**: Requirement 4 vs. Requirements 1.5/1.6 and the golden suite.
- **Alternatives Considered**: 1. `fitdocs_version` frontmatter key. 2. `generated_at` timestamp. 3. Body banner only. 4. Frontmatter key only.
- **Selected Approach**: Both surfaces, both constant: a `generator: fitdocs` frontmatter key plus an HTML-comment banner immediately after the frontmatter block, outside every region, naming the tool, stating that everything outside the marked regions is replaced, and pointing at the in-tree declaration.
- **Rationale**: The frontmatter key is what code matches on (and what distinguishes a fitdocs document from a hand-written `type: workout` note); the banner is what a human or an agent sees the instant it opens the file. Neither varies, so byte-identical regeneration survives. `doc_version` remains the single compatibility signal, which is exactly the role the migration story needs it to play.
- **Trade-offs**: A document cannot report which fitdocs release produced it. Accepted: `doc_version` answers the only question that changes behavior, and the archive plus the contract version answer the rest.
- **Follow-up**: Regenerate all eight golden documents and update the four inline frontmatter byte-string assertions in one coordinated change.

### Decision: `AGENTS.md` in owned directories only, never at the data root

- **Context**: Requirement 3; the data root may *be* the user's wiki root.
- **Alternatives Considered**: 1. One declaration at the data root. 2. Emit both `AGENTS.md` and `CLAUDE.md`. 3. Configurable filename.
- **Selected Approach**: `workouts/AGENTS.md` and `fit-archive/AGENTS.md`, generated from the contract module's constants, refreshed only when content differs, never written over a file lacking fitdocs' provenance stamp, and never emitted at the data root or in `.cache/`.
- **Rationale**: The nested-file idiom is the documented AGENTS.md behavior, and it is also the exact shape of fitdocs' sole-writer boundary. A root-level file would write outside the owned tree — the very violation the contract prohibits. Multiple filenames multiply the tool's footprint for no gain when a one-line reference from the user's own root file solves it.
- **Trade-offs**: Agents whose tooling only reads a root-level file need that one-line reference, which the published contract supplies.
- **Follow-up**: Confirm the declarations are invisible to every `workouts/*.md` scan (they carry no `type: workout`), and that "no new files + current declarations" leaves the data root untouched.

### Decision: A read-only `fitdocs check` command rather than more sync output

- **Context**: Requirement 8 wants an inspection that gates automation.
- **Alternatives Considered**: 1. Fold every finding into the sync/regen report. 2. A `--check` flag on `regen`.
- **Selected Approach**: A separate read-only command that scans the owned tree, reports version drift, damaged markers, unmanaged frontmatter keys, and declaration problems, and exits 0 / 1 / 2 under the existing exit-code contract.
- **Rationale**: Sync and regen only see the documents they touch, and both write; an agent or CI needs to ask "is this tree consistent with the installed fitdocs?" without side effects. A dedicated command also gives the damaged-marker check a home — today a damaged document is only discovered when a regeneration tries to rewrite it.
- **Trade-offs**: One more command surface in a deliberately small CLI. Justified by the wiki-integration goal that this whole spec exists to serve.
- **Follow-up**: Keep the command free of `.fit` decoding and network access so it stays fast on a large wiki.

## Risks & Mitigations

- **Golden-suite churn masking a real regression** — the format bump touches every golden document at once. Mitigation: land the pure consolidation refactor first and prove byte-identical output *before* introducing the provenance stamp, so any diff in the refactor step is a bug, and the format step's diff is exactly the two added lines.
- **`render` → `contract` import creating a cycle** — `render/frontmatter.py` currently avoids importing `layout` on purpose. Mitigation: `contract` is a leaf that imports only `docmerge` and `yaml`; enforced by a test asserting the contract module imports nothing from `render`, `sync`, `load`, `cli`, or `layout`.
- **Declaration files being mistaken for workout documents** — they live in `workouts/` alongside real documents and match `*.md`. Mitigation: they carry no `type: workout` frontmatter, so every existing scan already skips them; a regression test asserts sync, regen, load, and check all ignore them.
- **Overwriting a user's pre-existing `AGENTS.md`** — plausible when installing into an established wiki. Mitigation: write only when the existing file carries fitdocs' provenance stamp; otherwise leave it and warn.
- **Downgrade guard firing on hand-edited documents** — a user typo in `doc_version` could freeze a document. Mitigation: only a value strictly greater than the current version blocks a rewrite; missing, non-integer, or unusable values are treated as out of date, and the message names the file and the key.
- **Contract text drifting from behavior** — the classic failure mode of published contracts. Mitigation: the emitted declaration is generated from the same constants the code uses (owned paths, region ids, managed keys, contract version), and a test asserts the published document lists exactly the region ids and managed keys the contract module exposes.

## References

- [AGENTS.md](https://agents.md/) — the convention, its nested-directory semantics, and its stewardship.
- [OpenAI Codex — custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md) — precedence and per-directory resolution.
- [AGENTS.md advanced patterns: nested hierarchies, override files and fallbacks](https://codex.danielvaughan.com/2026/03/26/agents-md-advanced-patterns/) — nearest-file resolution order.
- [The agent-native repo: why AGENTS.md is the new standard](https://www.harness.io/blog/the-agent-native-repo-why-agents-md-is-the-new-standard) — adoption breadth across agent tooling.
- `.kiro/specs/workout-docs/design.md` §RegionMerger, §FrontmatterBuilder — the mechanisms this spec publishes unchanged.
- `.kiro/specs/training-load/design.md` §LoadDocEditor — the three managed load keys and the restore pass that proves frontmatter is rewritten wholesale.
