# Research & Design Decisions: effort-tags

---
**Purpose**: Discovery findings and the rationale behind the design of the
user-owned frontmatter key class and the effort tag. Everything here was read
from the worktree at the Phase 6 discovery commit (`1251a98`) on 2026-09-09/10;
line numbers cite that tree.
---

## Summary
- **Feature**: `effort-tags`
- **Discovery Scope**: Extension (light discovery) -- the feature adds no
  module, no command, no dependency and no owned path; it extends one pure leaf
  (`src/fitdocs/contract.py`) and threads one value through the existing
  rewrite path.
- **Key Findings**:
  - The contract already has the *region* analogue of what this spec adds
    (`USER_REGIONS`, carried verbatim by `docmerge.merge_regions`); the
    frontmatter block has no equivalent -- `MANAGED_KEYS` is the exact set the
    builder emits and everything else is dropped with a warning
    (`contract.py:291-334`, `sync.py:1191-1204`, `audit.py:243-252`).
  - The regeneration path already holds the existing document's full text at
    the moment it rebuilds the block (`sync.py:1176-1177`, reused for the
    merge at `sync.py:1264`), so carrying lines forward costs one lossless
    `split("\n")` and no second read.
  - The load pass's frontmatter surgery is line-level and touches only
    column-zero lines whose key is in `LOAD_KEYS` (`docedit.py:334-344`); a
    user-owned line is untouched by construction and needs only a test.
  - The reference wiki's schema states that a workout page's frontmatter is
    fitdocs' own and "must not be corrected toward" the wiki's standard
    (`~/code/pkm/wiki-schema.md:716-721`), and the wiki's own standard is flat
    keys plus lists -- so flat `effort*` keys are a valid shape there.
  - PyYAML's reading of plausible hand-typed values decides three validation
    rules: an unquoted wikilink parses as a nested list, `yes`/`true` parse as
    `bool` (a subclass of `int`), and `3:32:10` parses as the sexagesimal
    integer `12730` -- the reader must reject lists and bools by type and must
    not lean on the sexagesimal accident.

## Research Log

### How the frontmatter block is rebuilt today, and what survives
- **Context**: The brief says a hand-added key "survives until the next pass
  and then silently stops existing". Where exactly is it lost, and what is in
  scope at that moment?
- **Sources Consulted**: `src/fitdocs/sync.py` (`_process_file`,
  lines 1101-1270; `regen`, 895-1025), `src/fitdocs/render/frontmatter.py`,
  `src/fitdocs/render/views.py:_assemble` (133-143), `src/fitdocs/docmerge.py`.
- **Findings**:
  - `render_document(ctx)` builds the whole document including the block from
    `DocContext` alone; `merge_regions(rendered.markdown, existing_text)`
    splices only region *interiors* from the existing document, so the block
    comes wholly from the fresh render (`sync.py:1252-1266`).
  - The existing document is read exactly once (`existing_text`) for the
    version gate and reused for the merge; the same parse feeds
    `unmanaged_keys` (`sync.py:1176-1204`). A version-gated document returns
    before any of this and is never rewritten.
  - `build_frontmatter` emits one ordered mapping through one
    `yaml.safe_dump` and returns `"---\n{dumped}---\n"` (`frontmatter.py:135-138`);
    an anti-drift test walks its AST for `data[<key>] = ...` assignments and
    asserts `emittable | LOAD_KEYS == MANAGED_KEYS`
    (`tests/test_contract.py:228-265`).
  - `DocContext` is a frozen dataclass with one already-defaulted field
    (`map_data: MapData | None = None`), constructed at 10 sites across `src/`
    and `tests/`.
- **Implications**: The cheapest correct place to carry user-owned lines is
  the builder, fed through a new defaulted `DocContext` field, exactly as
  `source_refs` is assembled by the sync engine and rendered verbatim by the
  builder. Appending verbatim lines adds no `data[...]` assignment, so the
  managed-key anti-drift pin keeps holding unchanged.

### The load pass's frontmatter surgery
- **Context**: Req 4.3 requires the load pass to leave user-owned lines
  byte-identical. Does it already?
- **Sources Consulted**: `src/fitdocs/load/docedit.py` (`apply_frontmatter_load`
  264-290, `strip_frontmatter_load` 314-328, `_is_managed_line` 334-344),
  `src/fitdocs/load/engine.py:_process_document` (312-421).
- **Findings**: The editor removes only column-zero `key:` lines whose key is
  in `FRONTMATTER_LOAD_KEYS` and re-appends fresh ones just before the closing
  fence; every other line inside the fence is kept in order. Indented lines
  and `- ` items are never treated as managed. The engine reads the document
  once, classifies the `load` region, and writes through an atomic replace.
- **Implications**: No code change. The consequence worth stating in the
  contract is positional: after a load pass the load keys sit *after* any
  carried user-owned lines, because the editor re-appends its own lines last;
  a later regeneration reproduces the same order (managed, user-owned, then
  load keys restored by the pass that follows).

### The audit and the `check` command
- **Sources Consulted**: `src/fitdocs/audit.py` (`FindingKind` 90-119,
  `_document_findings` 189-254), `src/fitdocs/cli.py:check_command` (408-434)
  and `_report_audit` (888-925), `tests/test_cli_check.py:181`.
- **Findings**: Findings are independent per document; a `StrEnum` names the
  kind; remedies are module-level constants named once; the CLI prints subject,
  detail and remedy generically for every kind. `test_check_reports_every_
  finding_kind_and_exits_one` enumerates the kinds and asserts a distinctive
  detail and remedy fragment per kind.
- **Implications**: A new `FindingKind.INVALID_EFFORT_TAG` needs one branch in
  `_document_findings`, one remedy constant, and the CLI test's fixture and
  assertions extended; `_report_audit` itself is untouched.

### The in-tree declaration and its goldens
- **Sources Consulted**: `src/fitdocs/declaration.py` (fragment table 152-236,
  `declaration_text` 259-330), `tests/declaration_golden/*.AGENTS.md`,
  `tests/test_declaration.py` (90-128), `tests/test_declaration_goldens.py`.
- **Findings**: The text is composed from named fragments each carrying a
  CLAIM ANCHOR comment; the emitted text is pinned as byte-goldens regenerated
  by `uv run python -m tests.test_declaration_goldens`; a guard forbids the
  quantifiers "each/every/all documents/any document" on any line mentioning
  "region" (the false-claim shape that cost the original task five rounds);
  the workouts declaration must name every id in `contract.USER_REGIONS`.
- **Implications**: Adding a user-owned-keys sentence to the workouts
  declaration is one fragment plus a golden refresh, and it must follow the
  same discipline: a claim anchor, no per-document quantifier, and a companion
  test that every key in `USER_KEYS` is named. `CONTRACT_VERSION` is restated
  in both goldens, so a version bump changes both files regardless.

### The published ownership contract and its conformance test
- **Sources Consulted**: `docs/ownership-contract.md` (sections "Frontmatter
  Ownership" 114-117, "Managed Frontmatter Keys" 119-156), `tests/test_
  ownership_contract.py` (`_section` 40-62, `_backticked_list_items` 65-79,
  `test_managed_keys_equal_contract_exactly` 131-134).
- **Findings**: `_section(text, heading)` runs from a heading to the next
  heading of the same or shallower level, so a `###` subsection is *inside*
  its `##` parent; `_backticked_list_items` takes the first backticked token of
  every list line in the section. The document's own preamble says the
  contract version "changes whenever a guarantee stated in this document
  changes -- ... a different managed key set".
- **Implications**: The user-owned key list must live in its own `##` section
  containing no other backticked list items (the effort tag's kinds and rules
  go in a sibling `##` section), so set-equality against `contract.USER_KEYS`
  is exact. Preserving a new key class is a changed guarantee by the
  document's own rule, so `CONTRACT_VERSION` advances.

### The reference wiki's frontmatter conventions
- **Context**: The brief requires confirming the shape (flat keys or a
  mapping) against the pkm `wiki-schema.md` before choosing.
- **Sources Consulted**: `~/code/pkm/wiki-schema.md` -- "Frontmatter standard"
  (86-104), the fitdocs section (700-775), the provenance amendment (908-914).
- **Findings**: The wiki's standard is flat scalar keys plus `aliases`,
  `tags` and `sources` lists. Workout pages are explicitly exempt: "Their
  frontmatter is fitdocs' (`type: workout`, `generator: fitdocs`,
  `doc_version:`, `uuid:`, plus per-sport metrics); it is not governed by the
  Frontmatter standard above and must not be 'corrected' toward it." The
  wiki links workouts by `[[<stem>]]` and keeps `sources:` raw-only. Its
  editing rule currently reads "Everything outside a document's region
  markers is replaced on regeneration."
- **Implications**: Flat keys are the conforming shape; `tags` must not be
  reused (it has a wiki-wide meaning); a quoted `[[wikilink]]` string in
  `effort_event` matches how the wiki links entities. The wiki's editing
  sentence becomes slightly imprecise once user-owned keys exist -- a pkm-side
  edit, outside this repository, noted for the maintainer.

### What PyYAML makes of plausible hand-typed values
- **Context**: Validation rules must be written against what the parser
  actually yields, not against what the athlete meant.
- **Sources Consulted**: `uv run python` in the worktree venv against
  `yaml.safe_load` (PyYAML 6), 2026-09-10.
- **Findings** (observed):
  - `effort_event: [[Boston Marathon 2024]]` -> `[['Boston Marathon 2024']]`
    (a nested list); quoted, it is the string.
  - `effort_time_s: 3:32:10` -> `12730` and `32:10` -> `1930` (YAML 1.1
    sexagesimal integers); quoted, the string `'3:32:10'`.
  - `effort_distance_m: yes` -> `True` (a `bool`, which subclasses `int`);
    `.inf` -> `inf`; `10_000` -> `10000`; `10,000` -> the string `'10,000'`;
    `1e4` -> the string `'1e4'` (YAML 1.1 requires a dot in a float
    exponent form).
  - `effort:` with no value -> `None`; `effort: Race` -> `'Race'`.
  - Duplicate keys: the last occurrence wins silently.
  - Block scalars (`>-`, `|`) yield plain strings whose *source* spans
    several lines.
- **Implications**: Reject `bool` explicitly (the same discipline
  `document_version` applies), require `math.isfinite`, reject non-numeric
  strings rather than parsing them, name quoting as the remedy for a
  list-valued `effort_event`, and do not document or depend on the
  sexagesimal reading. The line carry must include continuation lines or a
  block-scalar value would be corrupted on regeneration. Duplicate keys are
  invisible to a mapping-level validator -- recorded as a known limitation.

### Existing pins the change must keep green
- **Sources Consulted**: `tests/test_contract.py`, `tests/test_public_api.py:
  281-340` (`_CONTRACT_SURFACE`), `tests/test_contract_consumers.py`
  (`CONTRACT_BINDINGS`, the YAML-emitter rule, the render-layer literal scan),
  `tests/test_ownership_contract.py`, `tests/render/test_frontmatter.py:58-83`
  (exact block), `tests/render/golden_docs/*.md`.
- **Findings**: `contract.__all__` is pinned exactly; the frontmatter builder
  is the only module allowed to name `yaml`, and only `safe_dump`; converted
  modules must bind contract objects by identity for the names the registry
  lists (additional bindings are allowed but should be registered so the
  identity check covers them); the exact-block test and the eight goldens
  carry no user-owned key.
- **Implications**: The surface pin, the binding registry, and the ownership
  document test are edited deliberately by named tasks; the builder must
  append verbatim text rather than call any second YAML function; goldens and
  the exact-block test are unaffected by construction because
  `user_frontmatter` defaults to `()`.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Verbatim line carry through the builder (selected) | Sync reads the existing block's user-owned entries as raw lines and hands them to `build_frontmatter` via a new `DocContext` field, which appends them after the managed keys | Byte-for-byte on the athlete's own text; one emission site for the block; managed-key anti-drift pin untouched; mirrors how `source_refs` already flows | Position inside the block is normalized on the first rewrite; a continuation-line rule is needed for multi-line values | The pattern the brief asks for ("carries verbatim ... re-emit them after the managed keys") |
| Value re-emission | Parse the existing block, copy user-owned *values* into `data`, let `yaml.safe_dump` emit them | Handles multi-line values for free; simplest code | Not byte-for-byte on the first rewrite (PyYAML re-quotes: `"[[X]]"` becomes `'[[X]]'`); breaks the AST anti-drift pin unless it learns to subtract user keys; the builder becomes a second interpreter of the block | Rejected: the guarantee is verbatim, not equivalent |
| Post-render splice in `sync` | Leave the builder alone; after `merge_regions`, splice the lines into the fresh block the way `docedit` does | No render-layer change; goldens untouched by construction | A second writer of the frontmatter block outside the module wiki-contract names as its single source; the splice needs the fence index twice | Rejected: `docedit` splices because it edits an *existing* block; the rebuild path has a builder for exactly this |
| Nested `effort:` mapping | One key holding `kind`, `distance_m`, `time_s`, `event` | Keeps the fields together; one key to carry | First nested value in a fitdocs block; harder to grep; a partially typed mapping produces more validation shapes | Rejected: flat keys match every key fitdocs writes and the reference wiki's own standard |

## Design Decisions

### Decision: Flat keys, four of them, closed
- **Context**: The brief left flat keys versus a nested mapping to the spec.
- **Alternatives Considered**:
  1. Flat `effort`, `effort_distance_m`, `effort_time_s`, `effort_event`.
  2. One `effort:` mapping.
- **Selected Approach**: Flat. `EFFORT_KEYS` is the published tuple in
  documentation order; `USER_KEYS = frozenset(EFFORT_KEYS)` is the class.
- **Rationale**: Every key fitdocs writes is flat; the reference wiki's own
  standard is flat; flat keys are grep-able from the shell; the load pass's
  editor and the new line carry both reason about column-zero keys. The suffix
  spells the unit (`_m`, `_s`) so a value is never ambiguous.
- **Trade-offs**: Four keys to validate as a group (the `effort`-required and
  distance-requires-time rules) instead of one mapping.
- **Follow-up**: None. An `effort_*` key outside the four is unmanaged and is
  dropped with the existing warning -- the prefix is not reserved.

### Decision: Byte-for-byte carry of the athlete's lines, appended after the managed keys
- **Context**: The whole feature is the preservation guarantee; the brief and
  the roadmap say "byte-for-byte".
- **Alternatives Considered**: see the pattern table.
- **Selected Approach**: A pure contract function `user_owned_lines(lines)`
  returns, verbatim, the lines of every top-level user-owned entry (the key
  line plus its continuation lines) in document order; `sync` passes them as
  `DocContext.user_frontmatter`; `build_frontmatter` writes them after the
  dumped managed block and before the closing fence.
- **Rationale**: The athlete's quoting, spacing and comments on those lines
  are theirs. Position is the one thing normalized -- after every managed key
  -- and it is stated in the contract so a second regeneration is
  byte-identical to the first.
- **Trade-offs**: The first rewrite after a hand edit may move the lines
  within the block (never alter them). A comment line above a user-owned key
  belongs to the preceding managed entry and is dropped; a comment line
  below it travels with it.
- **Follow-up**: Pin the round trip: `user_owned_lines(build_frontmatter(ctx
  with lines).split("\n")) == lines`.

### Decision: The reader returns a three-way value and never raises
- **Context**: Contract readers "degrade, never raise"; the brief requires
  validation that is loud and never reads a malformed tag as absent.
- **Alternatives Considered**:
  1. `effort_tag(...) -> EffortTag | None` plus a raising validator.
  2. `effort_tag(...) -> EffortTag | InvalidEffortTag | None`.
- **Selected Approach**: Option 2. `InvalidEffortTag.problems` is a non-empty
  tuple of `EffortTagProblem(key, detail)` in `EFFORT_KEYS` order, at most one
  per key; `InvalidEffortTag.describe()` renders them once for every reporter.
- **Rationale**: A consumer cannot mistake malformed for absent (it is not
  `None`), the contract's never-raise convention holds, and every reporter
  (`check`, `sync`/`regen`, downstream passes) prints the same words.
- **Trade-offs**: Callers must branch on three outcomes; that is the point.

### Decision: `unmanaged_keys` subtracts the user-owned set too
- **Context**: The warning and the audit finding both use `unmanaged_keys`,
  whose documented meaning is "keys the rewrite will drop".
- **Selected Approach**: `unmanaged_keys` returns keys outside
  `MANAGED_KEYS | USER_KEYS`; its docstring and wiki-contract's Req 6.3/8.4
  wording are amended to say so.
- **Rationale**: The function's contract is "what the rewrite drops"; a
  user-owned key is not dropped. One change fixes both reporters.

### Decision: `CONTRACT_VERSION` advances to `"2"` and the workouts declaration names the keys
- **Context**: The published contract says its version changes when a stated
  guarantee changes; "the frontmatter block is rewritten in full" is a stated
  guarantee that is no longer exactly true.
- **Alternatives Considered**:
  1. Leave `"1"`; document the new class only.
  2. Bump to `"2"`; add one sentence to the workouts `AGENTS.md`.
- **Selected Approach**: Option 2.
- **Rationale**: Option 1 makes the document contradict its own rule. The
  goldens regenerate for the version line anyway, so the sentence naming the
  user-owned keys -- the fact an LLM wiki agent most needs before "tidying" a
  frontmatter block -- costs one fragment.
- **Trade-offs**: Every data root's `AGENTS.md` is rewritten on the next
  `sync`/`regen` (that is what a contract-version change is for).

### Decision: No `DOC_VERSION` bump; the provenance banner is left as it is
- **Context**: `DOC_BANNER` says "everything outside the notes/workout/load
  regions is replaced on regeneration". With user-owned keys that sentence is
  a simplification.
- **Selected Approach**: No bump. Existing documents without a tag are
  byte-identical before and after; a document-format bump would mark every
  page in every wiki as out of date for a wording change.
- **Rationale**: The brief forbids a bump unless forced; nothing forces it.
  The banner points at `AGENTS.md`, which will be precise.
- **Follow-up**: Reword the banner at the next `DOC_VERSION` bump taken for
  another reason. Recorded as a deferred item for the controller's queue.

## Risks & Mitigations
- A multi-line user-owned value corrupted by a key-line-only carry -- the
  carry includes continuation lines; a block-scalar fixture pins it.
- A quoted key (`"effort": race`) parsed by YAML as `effort` but missed by the
  line scanner -- the scanner strips one pair of surrounding quotes from the
  key token; a fixture pins it.
- Duplicate user-owned keys in one block -- carried verbatim (nothing lost);
  the mapping-level validator sees only the last value. Known limitation,
  stated in the design.
- The unmanaged-key warning silently stops firing for a real unmanaged key --
  the existing `tags:` fixtures keep asserting it fires; only `USER_KEYS` are
  exempted.
- A reporter inventing its own wording -- `InvalidEffortTag.describe()` is the
  one renderer; tests assert the audit detail and the sync warning contain the
  same `describe()` output.
- Declaration prose regressions -- fragment with a claim anchor, no
  per-document quantifier, golden pinned, companion test over `USER_KEYS`.

## References
- `.kiro/specs/effort-tags/brief.md` -- problem, approach, constraints.
- `.kiro/steering/roadmap.md` Phase 6 -- scope, shared seams, Existing Spec
  Updates.
- `.kiro/specs/wiki-contract/design.md` -- DocumentContract, the anti-drift
  pin, revalidation triggers, ContractDocs.
- `docs/ownership-contract.md` -- the published contract this spec amends.
- `~/code/pkm/wiki-schema.md` -- the reference integration's frontmatter
  conventions (outside this repository; read 2026-09-10).
- PyYAML 6 `safe_load` behaviour, observed in the worktree venv (see the
  research log entry above).
