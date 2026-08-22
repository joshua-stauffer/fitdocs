# Research & Design Decisions — training-load

## Summary
- **Feature**: `training-load`
- **Discovery Scope**: Extension (integration-focused) — greenfield code, but
  tightly constrained by two approved upstream specs (fit-ingest,
  workout-docs) and an extracted methodology reference.
- **Key Findings**:
  - workout-docs preserves the `load` region verbatim across regeneration
    but regenerates frontmatter from scratch — the region must be the store
    of record, with frontmatter re-derived from it.
  - Real HealthFit/Stryd running files carry ~99%-coverage pace/speed and
    power but HR can gap to 62–72% coverage; sessions carry no
    NP/TSS/IF/thresholds and no user_profile/zones messages — athlete
    parameters can only come from the profile + prompting.
  - The withdrawn methodology's workbook math was evaluated against its
    (now-removed) extracted reference and found exactly reproducible. That
    reproduction is redacted below under `encumbered-content-purge`
    Requirement 1; the evaluation finding is retained.

## Research Log

### Upstream contract audit (fit-ingest, workout-docs)
- **Context**: Both upstream specs are approved; this spec must align
  exactly with their interfaces and claim no files they own.
- **Sources Consulted**: `.kiro/specs/fit-ingest/design.md` /
  `requirements.md`, `.kiro/specs/workout-docs/design.md` /
  `requirements.md` / `tasks.md` boundary lines.
- **Findings**:
  - fit-ingest provides `Activity` (laps with timer/speed/HR summaries,
    `developer_fields` raw mapping incl. `WORKOUT RPE ESTIMATED`),
    `DerivedMetrics` (avg HR, avg pace s/km, moving time), and
    `AthleteInputs`/`ZoneSpec`; zone *definitions* are explicitly deferred
    to training-load.
  - workout-docs owns: region grammar (`docmerge`: `notes`/`workout`/`load`
    ids, `RegionError`), the load placeholder ("not computed" line in
    `render/sections.py`), frontmatter schema/emission, data-root layout
    (`workouts/`, `fit-archive/<sha256>.fit`), `athlete.toml` *read*
    contract (unknown keys ignored — explicitly "for forward compatibility
    with training-load"), and cli.py/sync.py. Its Req 8.3/11.4 forbid it
    from prompting or computing load; its Req 11.3 guarantees the load
    region can be replaced without affecting anything else.
- **Implications**: training-load may import docmerge marker functions,
  layout paths, config resolver, athlete reader, and the placeholder
  constant; it must not modify sync.py, docmerge.py, or the renderer. Only
  `cli.py` and `pyproject.toml` are touched.

### The withdrawn methodology's extraction
- **Context**: Implement the first methodology exactly.
- **Sources Consulted**: the withdrawn methodology's (now-removed) extracted
  writeup and lookup tables.
- **Findings**: the methodology defined a set of effort zones with HR
  bands as a percentage of tested max. It defined a continuous-effort
  formula and a repeats-based interval formula restricted to its upper
  zones. The interval formula reduced points by a repeat-count-keyed
  multiplier, selected by an exact match on the repeat count. It defined a
  pace-by-performance-level chart, with some ranges listed slow-to-fast
  and gaps between certain zone ranges. Its workbook carried two
  fully-worked sample calculations and input validation ranges for max HR
  and performance level. `encumbered-content-purge` Requirement 1.2
  redacts those values and the generating rule behind the multiplier from
  this document. The fact that they were extracted and evaluated for
  reproducibility is retained.
- **Implications**: the parser needed to normalize reversed pace ranges.
  Gap paces needed nearest-zone-with-caveat handling. Invalid (zone,
  repeats) combinations were to raise and be re-asked, never clamped.
  Weather/terrain pace adjustment factors needed temperature, dew point
  and terrain class. `.fit` data carries none of those, so they were
  excluded from that pass. These implications no longer apply, because the
  methodology was withdrawn (`training-load` Amendment 2). They are
  retained as a record of what the original evaluation found.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Load layer + engine pass over documents (chosen) | New `load` package; engine fills the reserved region post-sync; CLI thin | Zero changes to sync engine/renderer; doc = store of record; regen-safe | Load pass re-parses archived `.fit` files (acceptable: local, O(docs)) | Matches steering pipeline `cli → load → ingest` |
| Hook load computation inside the sync per-file pipeline | sync.py calls calculators before render | Single pass over files | Requires modifying workout-docs's sync engine and render contract (load content inside fresh render conflicts with region-merge semantics); prompting mid-render entangles layers | Rejected |
| Separate load database (JSON/SQLite in data root) | Results stored outside documents | Easy queries | Violates steering "state = the user's files / everything re-derivable"; duplicates truth; sync complexity | Rejected |

## Design Decisions

### Decision: The document is the store of record (payload comment in the load region)
- **Context**: Results must survive regeneration (workout-docs preserves
  region content verbatim but resets frontmatter), and the brief wants load
  queryable from frontmatter.
- **Alternatives Considered**:
  1. Store results in a sidecar file keyed by activity uid.
  2. Recompute on every regen (impossible: confirmation-gated, would
     re-prompt).
- **Selected Approach**: A single-line machine-readable payload
  (`<!-- fitdocs-load:v1 {json} -->`) embedded in the region beside the
  human markdown; frontmatter keys re-derived from the payload by a restore
  step in every pass.
- **Rationale**: Steering's "state = the user's files"; the preservation
  guarantee already exists in workout-docs; HTML comments are invisible in
  every renderer.
- **Trade-offs**: Frontmatter keys are stale between a regen and the next
  pass (regen wiring runs the restore immediately, closing the gap);
  hand-editing the region can orphan the payload (classification treats
  unrecognized content as FOREIGN and never overwrites it silently).
- **Follow-up**: Golden test that a workout-docs regen + restore round-trip
  is byte-stable.

### Decision: Confirmation-gated computation (no silent zone/structure guessing)
- **Context**: Brief: estimates are "surfaced for user confirmation rather
  than silently guessing"; hard project rule against fabricated values.
- **Alternatives Considered**:
  1. Auto-compute when the estimate is unambiguous; confirm only edge cases.
  2. `--yes` flag accepting all estimates.
- **Selected Approach**: The withdrawn calculator returns `NotConfirmed`
  whenever the session cannot confirm (non-interactive or declined);
  non-interactive passes therefore only restore frontmatter and write
  unsupported states.
- **Rationale**: Zone choice moves points substantially between adjacent
  zones at the top of the scale; a wrong silent guess poisons the training
  log. Confirmation is one keypress when the estimate is right.
- **Trade-offs**: Scripted/CI syncs never fill load for runs; acceptable —
  the standalone `fitdocs load` fills retroactively. A future opt-in
  auto-accept flag remains possible at the interface level.

### Decision: Generic field prompting + calculator-owned dialogs via InteractionSession
- **Context**: structure.md rule: "no calculator-specific prompting code in
  the CLI"; but zone/interval confirmation is inherently
  methodology-specific.
- **Selected Approach**: Declared `AthleteField`s drive a generic prompt
  flow (engine-side); workout-specific dialogs live inside the calculator
  but speak only through injected `InteractionSession` primitives
  (`confirm`/`ask_int`/`ask_float`/`choose`/`inform`, `None` = declined).
- **Rationale**: Keeps the CLI methodology-agnostic while letting each
  methodology own its dialog; scripted sessions make dialogs unit-testable
  without a TTY.
- **Trade-offs**: Two prompting layers (fields vs dialogs); documented in
  the contributor guide.

### Decision: Adopt `tomli-w` for profile writes
- **Context**: `tomllib` is read-only; the profile must be rewritten with
  unmanaged keys preserved.
- **Alternatives Considered**:
  1. Hand-rolled TOML emitter — avoidable code with escaping edge cases.
  2. `tomlkit` (style/comment-preserving round-trip) — heavier dependency
     for a tool-owned file.
- **Selected Approach**: `tomllib` parse → mutate dict → `tomli-w` dump,
  atomic replace.
- **Rationale**: tomli-w is tiny, maintained, the standard companion to
  tomllib; steering wants a small dependency footprint.
- **Trade-offs**: User comments in a hand-edited `athlete.toml` are lost on
  rewrite (values preserved). Documented; the file is primarily
  tool-managed.

### Decision: Running-only load; the withdrawn calculator declines everything else; no TRIMP/TSS calculators
- **Context**: User scope decision (authoritative): first pass computes
  load for running only; cycling/strength methodologies are future in-house
  work; the interface must stay pluggable.
- **Selected Approach**: `supported_modalities = {run}`; the engine writes
  an honest "unsupported" state (payload-tagged, number-free) that later
  passes automatically upgrade once a supporting calculator registers.
  TRIMP/power-TSS stay generic derived metrics (fit-ingest computes,
  workout-docs renders as chips) — wrapping them as calculators would
  produce non-running load, contradicting the scope decision.
- **Trade-offs**: The withdrawn methodology's HR-variant-for-cycling idea,
  noted as an open question during its (now-removed) extraction, is
  deliberately not taken.

### Decision: Conservative interval detection, isolated in its own module
- **Context**: Brief boundary candidate: zone determination / structure
  detection is "the fuzzy part; keep the points math pure". Real lap data
  is noisy.
- **Selected Approach**: `structure.py` detects work laps (faster than
  session average, ≥2 repeats, durations within ±15% of mean, separated by
  recovery laps, ends excluded); anything ambiguous returns no candidate.
  Manual interval entry remains available in the confirmation dialog, so a
  missed detection costs a few keystrokes, never correctness.
- **Trade-offs**: Under-detection by design; tuning can evolve inside one
  module without touching contracts.

### Decision: Line-level frontmatter upsert (no YAML re-emission)
- **Context**: workout-docs owns frontmatter emission with golden-guarded
  byte stability; re-serializing via pyyaml could reflow its bytes.
- **Selected Approach**: The doc editor removes/appends only its own three
  managed lines (`load_points`, `load_methodology`, `load_zone`) before the
  closing `---`; reads use `yaml.safe_load` (read-only).
- **Trade-offs**: Managed values are restricted to simple scalars — which
  they are by construction.

## Risks & Mitigations
- **Licensing restriction blocked redistribution** — the withdrawn
  methodology's tables shipped as package data for personal use only.
  Public redistribution required the third party's permission. That
  restriction was one of three drivers behind the methodology's withdrawal
  (`training-load` Requirement 13); it never reached resolution. Mitigation
  at the time isolated the tables in `withdrawn/data/` and `tables.py`,
  removable or replaceable without touching contracts.
- **Placeholder-text coupling** — region classification recognizes the
  workout-docs placeholder by its constant. Mitigation: import the constant
  (single source of truth) and list its change as a revalidation trigger.
- **Prompt fatigue** — one confirmation per new running workout.
  Mitigation: defaults accepted with a single keypress; answers to athlete
  fields persist; computed docs are never re-asked.
- **Discount-table drift vs workbook** — moot. The calculator and its
  discount table were withdrawn (`training-load` Requirement 13). The drift
  this risk anticipated never materialised.

## References
- The withdrawn methodology's (now-removed) extracted writeup and lookup
  tables — consulted for the original methodology extraction (formulas,
  tables, validation ranges, licensing note); removed from the repository
  under `encumbered-content-purge` Requirement 1.
- `.kiro/specs/fit-ingest/design.md` — activity model / metrics contract.
- `.kiro/specs/workout-docs/design.md` — document format contract, region
  grammar, `athlete.toml` read contract, revalidation triggers.
- `docs/reference/fitdocs-ai-reference.md` — TRIMP/TSS formulas (context:
  they remain generic metrics, not calculators).

---

# Gap Analysis — Amendment 1 (2026-07-25): the multi-channel result contract

_Generated by `/kiro-validate-gap training-load` against the amended
`requirements.md` (Req 1 and 7 revised; Req 10, 11, 12 added) and the shipped
`src/fitdocs/load/` implementation. This is a **brownfield** analysis: every
requirement in this amendment lands on code that already exists, is tested, and
is consumed by two other shipped specs (`wiki-contract`, `plugin-api`)._

## Summary

- **Shape**: not a feature addition — a **contract redefinition** through a
  4-module chain (`types.py` → `render.py` → `docedit.py` → `engine.py`) plus
  the withdrawn calculator that constructs the type, plus a new configuration
  table and a new arbitration policy in the engine.
- **The amendment's measured blast radius holds.** Verified independently:
  3 `LoadResult` construction sites in `src/`, field reads confined to
  `render.py` + `docedit.py` (+ one `calculator_id` read in `engine.py`), and
  1,088 lines of directly shape-pinned tests (`test_types.py` 390 +
  `test_render.py` 252 + `test_docedit.py` 446).
- **The hardest gap is not the type — it is `engine.py`'s selection loop.**
  Req 10.5 forbids exactly what `_compute_document` does today: on an
  `Unsupported` outcome it `continue`s to the next candidate calculator. That
  fallthrough must be deleted, not extended.
- **Two of the five new-requirement areas are already largely satisfied**
  (Req 10.6 by `load_methodology` + payload `calculator_id`; Req 11.1/11.3 by
  the existing `LOAD_PAYLOAD_VERSION` + `FOREIGN` protection). Req 11.2's
  *reason* is the real gap: the code cannot currently tell a superseded fitdocs
  payload from user-authored prose — both classify `FOREIGN`.
- **One correction to the amendment's own record**: `tests/test_public_api.py`
  does **not** need repinning. It is an inclusion-by-identity check
  (`test_public_api.py:132-165`), so redefining `LoadResult` in place keeps it
  green; only *new* published names need adding. The real compatibility
  obligation is in `docs/plugins.md:245-251`, which does **not** declare the
  surface unstable — see "Constraint C4" below.

## Current State — what the amendment lands on

### The type being redefined

`LoadResult` (`src/fitdocs/load/types.py:70-94`), frozen dataclass, 8 fields:
`calculator_id`, `display_name`, `points`, `zone`, `zone_label`, `structure`,
`inputs_used`, `notes`. Three of those eight (`zone`, `zone_label`,
`structure`) are the withdrawn methodology's vocabulary the amendment names.

The surrounding outcome union is **already the right shape** and needs no
change: `LoadOutcome = Computed | Unsupported | MissingInputs | NotConfirmed`
(`types.py:137`), closed and folded with `assert_never` at
`engine.py:410`. `threshold-load`'s brief confirms it expects to reuse it.

### Every site that touches the shape

| Site | What it does | Amendment impact |
| --- | --- | --- |
| `withdrawn/__init__.py:333-344` | constructs `LoadResult` (continuous) | must produce the redefined shape with **no** channels/flags (Req 1.11, 12.3) |
| `withdrawn/__init__.py` (interval branch) | constructs `LoadResult` | same |
| `render.py:_result_from_data:212-221` | reconstructs from payload JSON | field-by-field rebuild; every new field needs a validated decode |
| `render.py:encode_payload:91-113` | serializes 8 fields into payload v1 | payload **v2**: new fields + version bump |
| `render.py:render_computed:236-249` | headline / zone / structure / inputs / notes | new sections for non-selected values + flags, omitted when empty (Req 12.3) |
| `docedit.py:_managed_lines:274-282` | emits `load_points` / `load_methodology` / `load_zone` | `load_zone` → basis (Req 7.2); must **not** emit channels or flags |
| `engine.py:298` | reads `payload.result.calculator_id` on restore | unaffected by field changes |

### The arbitration site (Req 10)

`engine.py:365-411`. Today: candidates are `[registry.get(forced_id)]` when
`--calculator` is passed, else `registry.for_modality(activity.modality)` — a
**registration-order** tuple (`registry.py:186-190`). The loop then takes the
first calculator whose outcome is not `Unsupported`. `registry.py:4-8` documents
this as intended behavior. `threshold-load`'s brief calls it out as a blocker:
once `threshold` and `withdrawn` both declare `Modality.RUN`, the winner is an
accident of import order.

There is **no** load configuration surface today. `config.py` is data-root
resolution only. `fitdocs.toml` exists with `[tiles]`, `[inbox]`, `[plugins]`
tables read through `settings.load_settings_document` (`settings.py:50`) with a
per-table validating reader per table — `plugins.py:126` is the reference
implementation of that pattern (`DEFAULT_PLUGIN_SETTINGS`, a
`SettingsError` subclass, absent-table-is-not-an-error).

### The versioning/recognition site (Req 11)

`LOAD_PAYLOAD_VERSION = 1` (`render.py:51`). `parse_payload` (`render.py:129`)
returns `None` for an unknown version — "foreign content, never misread". That
`None` becomes `RegionState.FOREIGN` (`docedit.py:117-136`), which
`engine.py:302-312` skips with the reason *"load region has unrecognized
content; left untouched (use --recompute to overwrite)"*.

`DOC_VERSION = 2` (`contract.py:130`); `LOAD_KEYS = ("load_points",
"load_methodology", "load_zone")` (`contract.py:182`), a subset of
`MANAGED_KEYS` (`contract.py:216`), pinned by anti-drift tests at
`tests/test_contract.py:169` and `:265`.

## Requirement-to-Asset Map

Tags: **Missing** (no asset) · **Constraint** (asset exists and constrains the
design) · **Unknown** (needs a decision or research in design).

### Requirement 1 (revised) — the result contract

| Criterion | Asset | Gap |
| --- | --- | --- |
| 1.2 value + methodology + **basis** + inputs + notes | `LoadResult` | **Constraint** — `zone`/`zone_label` must generalize to a basis without losing the withdrawn calculator's zone detail (Req 12.2) |
| 1.5 threshold engine registered as built-in | `registry.register`, `load/__init__.py` | **Missing** — no `threshold` calculator exists; owned by `threshold-load`. This spec must not *require* it to exist (Boundary Context says so explicitly) |
| 1.8 non-selected values + reason each | — | **Missing** — new type (channel value + not-selected reason) |
| 1.9 quality flags carried, value unaltered | — | **Missing** — new type; `activity-qa-flags` defines detection, this spec defines the carrier |
| 1.10 selected value distinguishable from all others | `LoadResult.points` | **Constraint** — satisfied structurally if the selected value stays a distinct scalar field rather than an entry in a channel collection |
| 1.11 single-value case fabricates nothing | — | **Missing** — empty tuples, and the withdrawn calculator must pass them |

**Design tension worth naming**: 1.10 and 1.8 pull in opposite directions. A
`channels: tuple[...]` collection where the selected one is flagged satisfies
1.8 cleanly but weakens 1.10 (a consumer can iterate and misread). Keeping
`points` a top-level scalar and channels a separate diagnostics tuple satisfies
1.10 by construction and matches `threshold-load`'s brief ("Only the selected
value is the activity's load. The rest are diagnostics").

### Requirement 7 (revised) — documents

| Criterion | Asset | Gap |
| --- | --- | --- |
| 7.1 section carries value, methodology, basis, non-selected + reasons, flags, inputs, notes | `render_computed` (`render.py:227`) | **Missing** — two new rendered sections, both omitted when empty (Req 12.3) |
| 7.2 frontmatter = value + methodology + basis **only** | `docedit.py:_managed_lines`, `contract.LOAD_KEYS` | **Constraint (cross-spec)** — `load_zone` is the third key; renaming/redefining it touches `contract.py:182`, `MANAGED_KEYS`, and the two anti-drift tests. `wiki-contract` owns this |
| 7.3 machine-readable payload carries the complete result | `encode_payload` / `parse_payload` | **Missing** — payload v2 |
| 7.4-7.6 restore / no-overwrite / foreign protection | `engine.py:291-312` | **No change needed** — mechanism is field-agnostic |
| 7.7 honest unsupported state | `render_unsupported` (`render.py:252`) | **No change needed**, but Req 10.5 *qualifies* when it is written |

### Requirement 10 — arbitration (all Missing except 10.6)

| Criterion | Gap |
| --- | --- |
| 10.1 configured default wins over registration order | **Missing** — no `[load]` table; `plugins.py:126` is the pattern to copy |
| 10.2 no default configured → threshold engine | **Missing + Unknown** — what happens *before* `threshold-load` lands? A hard default of `"threshold"` makes today's suite fail with `UnknownCalculatorError`. See "Research Needed R1" |
| 10.3 `--calculator` beats the default | **Partial** — `engine.py:365` already gives the forced id precedence; needs to survive the rewrite |
| 10.4 unregistered default → instructive error naming value + registered ids, **no fallback** | **Partial** — `UnknownCalculatorError` (`registry.py:169`) already produces that exact message shape and is already in `_CONFIG_ERRORS` (`engine.py:119`) → aborts the pass, exit 2. Needs to be raised at up-front config validation |
| 10.5 arbitrated calculator declines → honest unsupported, **no substitution** | **Missing (behavioral reversal)** — `engine.py:408-409` `case Unsupported(): continue` is precisely the forbidden substitution. Delete the loop |
| 10.6 record which calculator produced the result | **Satisfied** — `load_methodology` + payload `calculator_id` |

### Requirement 11 — format versioning

| Criterion | Gap |
| --- | --- |
| 11.1 payload carries a result-format version | **Satisfied** — `LOAD_PAYLOAD_VERSION` (`render.py:51`), bump to 2 |
| 11.2 unknown version → unchanged, skipped, **with the reason**, no partial parse | **Partial** — unchanged/skipped/no-partial-parse all hold today; the *reason* is wrong. A v3 payload and a user's hand-written prose both classify `FOREIGN` and get the same generic message. Needs a distinguishable state (e.g. `RegionState.SUPERSEDED` / `UNRECOGNIZED_VERSION`) carrying the version it found |
| 11.3 superseded format not auto-recomputed | **Satisfied incidentally** — `FOREIGN` is skipped without `--recompute`. Should become intentional under the new state |
| 11.4 explicit recompute → recompute from archive, current format | **Satisfied** — `engine.py:317-329` |
| 11.5 result-format change ⇒ `doc_version` changes | **Missing (cross-spec)** — `DOC_VERSION` 2 → 3 in `contract.py:130`, whose docstring requires the bump to land "in the same change that regenerates every committed golden document" |

### Requirement 12 — the withdrawn calculator's continuity

| Criterion | Gap |
| --- | --- |
| 12.1 Req 4/5/6 still satisfied, workbook examples exact | **Constraint** — `withdrawn/test_points.py`, `test_calculator.py` (515 lines) are the existing guard; the workbook worked-example vectors (redacted, `encumbered-content-purge` Req 1.2) lived in `withdrawn/points.py`, since deleted under `training-load` Requirement 13, and were untouched by the contract change this gap analysis records |
| 12.2 zone + structure keep meaning and user-visible detail | **Constraint** — `zone_label=f"Zone {zone} ({ZONE_NAMES[zone]})"` and `structure=f"Continuous — {duration:.1f} min"` (`withdrawn/__init__.py:339-340`) must survive into whatever the basis/structure fields become |
| 12.3 no channel values ⇒ omit entirely | **Missing** — `render_computed` must conditionally emit, as it already does for `zone_label` / `inputs_used` / `notes` |
| 12.4 the withdrawn calculator selectable by id and as configured default | **Missing** — falls out of Req 10 |
| 12.5 same confirmed inputs ⇒ same point value | **Missing (test)** — a regression pin; cheap, and the strongest single guard on the whole amendment |

## Constraints from the existing architecture

- **C1 — dependency direction.** `types.py` imports nothing from
  `fitdocs.load.*` (its own docstring, `types.py:5-9`). Any new type (channel
  value, quality flag, basis) must land in `types.py` or below it, never in a
  module `types.py` would have to import.
- **C2 — byte-determinism.** `render.py` guarantees identical results render
  identically (compact JSON, `sort_keys=True`) and `engine.py` guarantees a
  repeated pass performs **no writes**. New collection fields must have a
  defined, stable order — tuples, not sets or dicts.
- **C3 — payload is the store of record.** `docedit.py:8-10`: the region holds
  the payload; frontmatter is a *derived, restorable projection* of it. Req 7.2
  (frontmatter omits channels and flags) is consistent with this only because
  restore re-derives frontmatter from the payload, never the reverse.
- **C4 — the published compatibility policy does not say what the amendment
  assumes.** `docs/plugins.md:245-251` states that within `0.x` the surface may
  change "only **additively** between patch releases — but nothing is removed
  or has its signature changed without an accompanying **minor** version bump,
  called out in the changelog." Redefining `LoadResult` **removes** fields, so
  under the shipped policy it is legitimate *with a minor version bump and a
  changelog entry* — not because the surface is undeclared-unstable. Today
  `pyproject.toml` is at `0.1.0` and **there is no CHANGELOG file**. The design
  must pick one: (a) bump to `0.2.0` and create the changelog the policy
  promises, or (b) amend `docs/plugins.md` to declare the surface unstable
  pre-1.0. (a) honors what is already published; (b) is what the amendment
  assumed. Either way this is `plugin-api` territory and needs coordination.
- **C5 — no load configuration surface exists.** A `[load]` table is genuinely
  new, and `activity-qa-flags`'s brief already claims the same table for its
  thresholds. Design it once, here, with room for that.

## Implementation Approach Options

### Option A — Extend `LoadResult` additively (new optional fields, keep `zone`/`zone_label`)

Add `basis`, `channels`, `flags` with defaulting-empty values; leave the withdrawn methodology's
fields in place; keep payload v1 readable.

- ✅ Smallest diff; existing tests mostly stay green; no `DOC_VERSION` bump
- ✅ The withdrawn calculator needs no change at all
- ❌ **Fails the amendment's stated rationale**: `zone`/`zone_label` remain the withdrawn methodology's
  vocabulary the threshold engine must either misuse or leave `None`, and
  frontmatter would carry `load_zone` for a calculator that has no zones
- ❌ Fails Req 7.2 as written (basis, not zone, is the third frontmatter key)
- ❌ Accumulates the "several values where the contract has one" problem rather
  than resolving it

**Verdict**: contradicts the amendment. Recorded for completeness only.

### Option B — Redefine `LoadResult` in place; payload v2; new `[load]` config; delete the selection fallthrough

One frozen dataclass rewritten in `types.py` with new sibling types
(`ChannelValue`, `QualityFlag`, and a basis representation), all three shipped
sites updated, `render.py` bumped to payload v2 with conditional sections,
`docedit.py`'s third managed key changed to basis, `engine.py`'s loop replaced
by single-calculator arbitration, plus a `[load]` settings reader modeled on
`plugins.py`.

- ✅ Exactly what the amendment specifies; `threshold-load` gets the shape its
  brief asks to be designed against
- ✅ Req 1.10 satisfied structurally (selected value stays a scalar field)
- ✅ Req 11.2's distinguishable superseded state falls out of the v1→v2 bump —
  and v2 is the first bump that ever exercises the version branch in anger
- ❌ Cross-spec coordination is mandatory and simultaneous: `contract.LOAD_KEYS`
  + `MANAGED_KEYS` + `DOC_VERSION` (`wiki-contract`), golden-document
  regeneration, the compatibility decision in C4 (`plugin-api`)
- ❌ ~1,088 lines of shape-pinned tests rewritten; `docs/contributing-calculators.md:107-109`
  documents the old shape and must follow

### Option C — Hybrid: land arbitration + versioning first, redefine the shape second

Two sequenced increments. **C1**: `[load]` config, arbitration (Req 10),
superseded-format recognition (Req 11.2), Req 12.4/12.5 regression pins — all
of which are *independent of the result shape*. **C2**: the contract
redefinition (Req 1.8-1.11, 7.1-7.3, 12.3), payload v2, `DOC_VERSION` bump,
cross-spec landing.

- ✅ Splits the one change that needs simultaneous cross-spec landing away from
  the ones that do not — C1 touches no other spec's assets
- ✅ Req 10.5 (the behavioral reversal, and the bug `threshold-load` is actually
  blocked on) ships first and independently testable
- ✅ Req 12.5's "same number before and after" pin exists *before* the shape
  changes, so it can be recorded against the current implementation and
  re-asserted after — which is the only way that criterion is a real guard
  rather than a tautology
- ❌ Req 10.2 ("no default → threshold engine") is unlandable in C1 while
  `threshold` is unregistered — needs the R1 decision either way
- ❌ Two rounds of engine test churn instead of one
- ❌ Between increments the contract is stable but the arbitration is
  single-calculator, which is a coherent but temporary state

## Effort & Risk

| Area | Effort | Risk | Justification |
| --- | --- | --- | --- |
| Contract redefinition (`types.py` + 3 sites) | **S** | Low | Frozen dataclasses, no logic; the compiler and `mypy --strict` find every site |
| Payload v2 encode/parse/render | **M** | Low | Established pattern; per-field validated decode is mechanical but must stay tolerant, and the conditional-omission rules (12.3) need their own tests |
| Arbitration + `[load]` settings reader | **M** | **Medium** | New configuration surface with no precedent in the load layer; Req 10.5 is a behavioral reversal of shipped, tested behavior; ordering of "forced id > configured default > error" has four failure modes to pin |
| Superseded-format recognition (11.2) | **S** | Low | One new `RegionState` + a version-carrying parse result |
| Test repinning (~1,088 lines direct, more indirect) | **L** | Low | Volume, not difficulty; `test_feature_e2e.py` (687) and `test_cli_load.py` (620) are indirectly affected |
| Cross-spec landing (`contract.py`, `DOC_VERSION`, goldens, compat policy) | **M** | **High** | Must land atomically with `wiki-contract` or documents report unmanaged keys; `DOC_VERSION` 3 obliges golden regeneration in the same change; C4 is an unresolved published-policy conflict |
| **Total** | **L (1-2 weeks)** | **Medium-High** | Driven by cross-spec coordination and test volume, not by algorithmic difficulty |

## Research Needed (carry into design)

- **R1 — Req 10.2 before `threshold-load` exists.** The requirement names the
  threshold engine as the no-config default, but the Boundary Context also says
  this feature "must not assume [threshold-load] has landed in order to keep
  working." Options: default to the threshold id and treat its absence as the
  Req 10.4 instructive error; default to "the single registered calculator when
  exactly one supports the modality, else require configuration"; or ship the
  threshold id as the default constant but gate it behind registration. **This
  is the one open question that changes what gets built** — flag it for the
  user before design freezes.
- **R2 — the basis representation.** Req 7.2 puts basis in frontmatter, so it
  must serialize to a single readable YAML scalar; Req 12.2 requires the
  withdrawn calculator's zone-label detail (a zone number with a named-zone
  qualifier, redacted per `encumbered-content-purge` Req 1.2) to survive;
  `threshold-load` needs `"pace channel"` / `"HR channel"`. A free string is
  simplest and satisfies all three; a typed enum + label is queryable but
  forces this spec to enumerate channel names it explicitly does not own.
- **R3 — frontmatter key naming.** Keep `load_zone` (minimal cross-spec churn,
  wrong name for a channel basis) vs. rename to `load_basis` (correct, touches
  `contract.LOAD_KEYS`, `MANAGED_KEYS`, two anti-drift tests, and any wiki query
  the user has written). The amendment records zero generated documents
  currently carry these keys, which makes the rename cheap *now* and
  progressively less so.
- **R4 — `[load]` table shape.** `activity-qa-flags` claims the same table for
  detection thresholds and `threshold-load` claims it for per-discipline channel
  priority. Design the reader so those land additively rather than as three
  competing readers of one table.
- **R5 — C4 resolution.** Minor version bump + new CHANGELOG, or amend the
  published compatibility statement. Needs a decision, not research.

## Recommendations for the design phase

1. **Take Option C (hybrid), with the C1/C2 split as the task-plan boundary.**
   The arbitration work is what actually unblocks `threshold-load`, touches no
   other spec's assets, and contains the only behavioral reversal in the
   amendment. Isolating it from the cross-spec-atomic contract change is worth
   the extra round of engine test churn. If the user prefers a single landing,
   Option B is coherent — but then `contract.py`, `DOC_VERSION`, golden
   regeneration, and the C4 decision are all on the critical path of one change.
2. **Record Req 12.5's regression vector before touching `types.py`.** Capture
   the exact point values the current withdrawn-calculator implementation produces for a fixed
   set of confirmed inputs and assert them from a test that survives the
   redefinition. Done after the fact, that criterion proves nothing.
3. **Delete `engine.py:408-409`'s `continue`, do not guard it.** Req 10.5 makes
   the multi-candidate loop itself the defect; arbitration should resolve to
   exactly one calculator before `compute` is ever called, and an `Unsupported`
   from it goes straight to `render_unsupported`.
4. **Model the `[load]` reader on `plugins.py:126`** — `DEFAULT_LOAD_SETTINGS`,
   a `SettingsError` subclass, absent-table-is-not-an-error, validated per key,
   read through the already-shared `load_settings_document`.
5. **Keep the selected value a top-level scalar.** It is the cheapest structural
   satisfaction of Req 1.10, and it keeps `docedit.py`'s frontmatter projection
   a direct field read rather than a search through a collection.
6. **Resolve R1 with the user before writing design.md.** Every other open item
   is a design decision this spec can make; R1 changes observable CLI behavior
   on a data root with only the withdrawn calculator registered, which is the state of every
   installation today.

---

# Design Discovery — Amendment 2 (2026-07-25): the carrier without a calculator

_Discovery type: **light (extension)**. Every requirement lands on shipped,
tested code; no new external dependency is introduced and none is removed
(`tomli-w` is still required — the profile write path survives the withdrawn calculator). The
Amendment 1 gap analysis above remains valid for Requirements 1, 7, 10 and 11;
this section records what Amendment 2 changed, what the codebase survey
measured, and the decisions the design commits to._

## Summary

- **Key finding 1 — Requirement 13.4 is satisfied by Requirement 11.2, not by
  calculator-specific code.** Every result from the withdrawn calculator in
  the wild is a payload **v1** record, because the withdrawn calculator is
  deleted in the same change that introduces v2. A v1 payload is a
  superseded format, and the superseded-format path already leaves the
  section unchanged and reports the document skipped. No calculator name is
  hardcoded anywhere in the removal.
- **Key finding 2 — the removal's cost is mostly in *other specs'* test files.**
  `src/` loses 1,163 lines cleanly (the whole `load/withdrawn/` package plus
  one `register()` call). But `tests/test_plugins.py` (plugin-api's) uses
  `withdrawn` as the built-in anchor in ~35 assertions, and three load
  test modules use it as their compute subject. Those need a test-owned
  stub calculator, which
  becomes a first-class deliverable rather than incidental churn.
- **Key finding 3 — after the deletion, `src/` constructs `LoadResult` in
  exactly one place**: `render._result_from_data`, the payload decoder. Every
  *production* of a result now comes from outside the package. That makes the
  contract redefinition almost free on the source side and concentrates all
  risk in the payload/render/frontmatter projection.

## Research Log

### Codebase survey — the withdrawn calculator's blast radius (Amendment 2)

- **Context**: Requirement 13.1 demands no implementation, no tables, no
  derived constants and no shipped data files remain; 13.3 demands no
  documentation presents the withdrawn methodology as available.
- **Sources consulted**: full-tree grep for the third party's tokens
  (case-insensitive) across
  `.py`, `.toml`, `.md`, `.csv`; `pyproject.toml` build config; the eight
  golden documents under `tests/render/golden_docs/`.
- **Findings**:
  - **Source**: `src/fitdocs/load/withdrawn/` (5 modules, 2 CSVs, 1,163
    lines) and one `register(WithdrawnCalculator())` call plus one export in
    `src/fitdocs/load/__init__.py`. Three further files mention the
    withdrawn calculator only in prose docstrings (`load/profile.py`,
    `load/prompts.py`, `metrics/stress.py`) and one in a CLI help string
    (`cli.py:175`).
  - **Packaging**: `pyproject.toml` declares only
    `[tool.hatch.build.targets.wheel] packages = ["src/fitdocs"]` — the CSVs
    ship because they sit inside the package directory, so deleting the
    directory removes them from the wheel with no build-config change. There is
    no `package-data` stanza to edit.
  - **Tests**: `tests/load/withdrawn/` (5 files, 1,489 lines) deletes
    wholesale. `tests/load/test_packaging.py` and
    `tests/load/test_install_smoke.py` exist substantially to prove the
    withdrawn methodology's CSVs ship — their subject disappears, but their
    `tomli-w`-is-a-runtime-dependency half must survive. Cross-spec:
    `tests/test_plugins.py` (~35 assertions anchored on the id `withdrawn`),
    `tests/test_plugin_regression.py`, `tests/test_cli.py`, `tests/conftest.py`.
  - **Documents**: 8 golden markdown documents carry `doc_version: 2`; none
    carries a load frontmatter key, confirming the amendment's record that
    migration-by-regen has nothing to migrate in practice.
- **Implications**: the removal is mechanical in `src/` and substantial in
  tests, and the *replacement* of the withdrawn calculator as the tests'
  calculator subject is the real design obligation (see the stub-calculator
  decision below).

### Requirement 13.4 vs Requirement 11.2 — reconciling two "leave it alone" rules

- **Context**: 13.4 requires a document carrying a result from the
  withdrawn calculator to be left unchanged and reported skipped *with a
  reason naming the unavailable
  methodology*. 11.2 requires an unrecognized result-format version to be left
  unchanged and reported skipped *without partial parsing or inferred fields*.
  Both apply to the same documents.
- **Findings**: the two are the same document state. A result from the
  withdrawn calculator can only exist as a payload v1 record; the payload
  version bump to v2 makes it
  superseded by construction. The only friction is the *message*: naming the
  methodology requires reading `calculator_id` out of a payload 11.2 forbids
  parsing into a result.
- **Implications**: separate *reading a diagnostic stamp* from *reconstructing a
  result*. A best-effort stamp read that can only ever affect a message, never a
  value, satisfies both — see the decision below.

## Design Decisions

### Decision: `LoadResult` is redefined around one selected value plus explicitly-not-the-load diagnostics

- **Context**: Req 1.2, 1.8-1.11 and 7.1-7.3.
- **Alternatives considered**:
  1. A `channels: tuple[...]` collection with the selected entry flagged —
     satisfies 1.8 cleanly but weakens 1.10, since any consumer can iterate the
     collection and read the wrong entry as the activity's load.
  2. Additive optional fields on the shipped type (gap-analysis Option A) —
     rejected by the amendment's own rationale; leaves the withdrawn
     methodology's vocabulary in a tool that ships no such methodology.
- **Selected approach**: `value: float` and `basis: str` stay top-level scalars;
  `non_selected: tuple[NonSelectedValue, ...]` and `flags:
  tuple[QualityFlag, ...]` are separate diagnostic tuples, empty when the
  methodology has none. `zone`, `zone_label`, `structure` and `points` are gone.
- **Rationale**: 1.10 is satisfied *structurally* rather than by convention —
  there is exactly one field of type "the load", and nothing in a diagnostic
  tuple has the same shape or name. 1.11 falls out: the single-value case is an
  empty tuple, and rendering omits empty sections entirely.
- **Trade-offs**: a methodology wanting to expose a value that is neither
  selected nor explainable must still supply a reason string — the contract
  forbids a bare number with no account of why it is not the load. That is
  intentional.

### Decision: `NonSelectedValue.value` is `float | None`, and `reason` is always required

- **Context**: Req 1.8 covers values that were *computed but not selected*;
  `threshold-load`'s brief also needs to carry channels that *could not be
  computed*, with their insufficiency reasons.
- **Selected approach**: one type covers both. `value` is `None` when the
  methodology produced no number for that entry; `reason` is non-empty in every
  case and says why the entry is not the activity's load.
- **Rationale**: the project rule is that absent data is `None`, never a
  fabricated `0` — a second type distinguished only by the presence of a number
  would duplicate the vocabulary and let a `0.0` insufficiency slip through.
  Detecting insufficiency stays out of boundary (`load-channels`); only carrying
  it is in.

### Decision: the quality-flag verdict is a closed three-value vocabulary defined here

- **Context**: Req 1.9 requires the result to carry flags. `activity-qa-flags`
  owns *detection* and its brief asks for the flag vocabulary to be first-class
  in this contract from the start, with "not assessed" as a first-class state
  distinct from a passed check.
- **Alternatives considered**: a minimal `key`/`label`/`detail` flag with the
  verdict encoded in prose — rejected, because Req 7.1 requires the section to
  *render* flags, and a renderer cannot distinguish "checked and clean" from
  "never checked" out of free text, which is exactly the failure the downstream
  brief calls out.
- **Selected approach**: `verdict: Literal["detected", "not-detected",
  "not-assessed"]`, with `key`, `label` and `detail` owned by the detector.
- **Trade-offs**: this spec fixes a vocabulary it does not produce. Adding a
  fourth verdict is therefore a revalidation trigger, recorded as such.

### Decision: `basis` is a free-form, methodology-owned string

- **Context**: R2. Req 7.2 puts the basis in frontmatter, so it must serialize
  to one readable YAML scalar; `threshold-load` needs `"pace"`/`"HR"`; Req
  12.2's constraint (preserve the withdrawn calculator's zone label) is
  withdrawn with Req 12.
- **Selected approach**: a required non-empty `str`, short and stable, emitted
  verbatim into the section and as the frontmatter scalar (`docedit`'s existing
  defensive `_yaml_scalar` quoting already handles anything ambiguous).
- **Rationale**: a typed enum would force this spec to enumerate channel names
  that its Boundary Context explicitly assigns to `threshold-load`. A free
  string claims no vocabulary and satisfies all three consumers.
- **Trade-offs**: frontmatter basis values are only as queryable as the
  methodologies are disciplined. Acceptable — the payload is the store of
  record, and the basis is a label, not a key.

### Decision: rename all three frontmatter keys — `load_value`, `load_methodology`, `load_basis`

- **Context**: R3. Req 7.2 requires the third key to carry the basis;
  `load_zone` is the withdrawn methodology's vocabulary. `load_points` is
  likewise methodology-flavored in a carrier that ships no points-based
  methodology.
- **Selected approach**: `LOAD_KEYS = ("load_value", "load_methodology",
  "load_basis")`.
- **Rationale**: renaming `load_zone` is required by 7.2; renaming
  `load_points` is not, and is recorded here as a deliberate scope choice. The
  marginal cost is zero — the same file, the same two anti-drift tests, and the
  `DOC_VERSION` bump that 11.5 already mandates — and leaving `load_points`
  reintroduces exactly the "field named after one methodology" defect that
  Amendment 2 was written to eliminate. Zero generated documents carry these
  keys today, so the rename is free now and progressively less so later.
- **Trade-offs**: widens the cross-spec footprint from two key names to three.
  Cheap to reverse if review disagrees; nothing else in the design depends on it.

### Decision: a diagnostic-only payload stamp reconciles Req 11.2 and Req 13.4

- **Context**: see the research-log entry above.
- **Selected approach**: `inspect_payload(content) -> PayloadStamp | None`
  returns the marker's `version` and a **best-effort** `calculator_id` used for
  message text only. It never constructs a `LoadResult`, never feeds restore or
  the frontmatter projection, and yields `None` for the id whenever the body
  does not decode — in which case the skip reason simply omits the methodology
  name.
- **Rationale**: 11.2 forbids parsing a superseded payload *into a result* or
  inferring missing fields; it does not require the tool to be unable to read
  its own marker. Confining the read to a message keeps the prohibition intact
  while letting 13.4's reason name the methodology the user actually recorded.
- **Trade-offs**: the stamp read knows that v1 payloads carried a
  `calculator_id` key. This is a one-way, failure-tolerant assumption about a
  format the tool itself wrote, not a decode path.

### Decision: arbitration is a pure function resolving to exactly one calculator before `compute`

- **Context**: Req 10.1-10.5; gap-analysis recommendation 3.
- **Selected approach**: a new pure `arbitrate` module returning a closed union
  `Selected | Ambiguous | NoCalculator`. Precedence: forced `--calculator` id >
  configured `[load] default_calculator` > (no default) the sole registered
  calculator supporting the modality. Several supporting calculators with no
  default is `Ambiguous` → skipped with a reason naming the candidates. The
  engine's candidate loop and its `case Unsupported(): continue` are deleted.
- **Rationale**: Req 10.5 makes the loop itself the defect. Making arbitration a
  pure function over (forced id, default, modality, registry snapshot) puts all
  four failure modes under unit test without touching the filesystem.
- **Trade-offs**: a configured default applies to every activity, so a default
  that does not support a sport yields the honest unsupported state rather than
  quietly using another calculator that would have. That is precisely 10.5.

### Decision: only the calculator actually in play is validated up front

- **Context**: Req 10.3 (explicit request beats the default) and 10.4
  (unregistered default is an instructive abort).
- **Selected approach**: when `--calculator` is supplied, validate that id and
  ignore the configured default entirely; otherwise validate the configured
  default. Either way validation happens before the document scan, so the abort
  precedes any write.
- **Rationale**: a stale `default_calculator` in `fitdocs.toml` must not block a
  user who has explicitly named a different calculator on the command line.

### Decision: `[load]` is opened here with one key and an explicit additivity contract

- **Context**: R4 — `threshold-load` claims `[load]` for per-discipline channel
  priority, `activity-qa-flags` for detection thresholds, `athlete-benchmarks`
  for the staleness window.
- **Selected approach**: `src/fitdocs/load/settings.py` modeled directly on
  `plugins.load_plugin_settings`: a frozen `LoadSettings`, a
  `DEFAULT_LOAD_SETTINGS` constant, a `LoadSettingsError(SettingsError)`
  subclass, absent-table-is-not-an-error, read through the already-shared
  `settings.load_settings_document`. It owns exactly one key,
  `default_calculator`, and **ignores unknown keys and unknown sub-tables**
  inside `[load]`.
- **Rationale**: the tolerance is the whole point — it is what lets
  `[load.priority]`, `[load.flags]` and a staleness window land additively in
  three later specs instead of as three competing readers of one table.
- **Trade-offs**: `load_load_settings` reads awkwardly, but matching
  `load_tile_settings` / `load_plugin_settings` keeps one discoverable pattern.

### Decision: a test-owned stub calculator replaces the withdrawn calculator as the tests' subject

- **Context**: Req 13.2 leaves the registry empty of built-ins, but the engine,
  CLI, e2e and plugin-discovery tests all need *some* calculator to exercise the
  computed path, and Req 2.7/3.6 require the methodology-scoping and hint seams
  to be exercised "by contract, not by a bundled calculator".
- **Selected approach**: shared fixtures in `tests/load/conftest.py` providing
  minimal calculators (a computing one, a declining one, one declaring a scoped
  athlete field and a hint) registered and unregistered around each test.
- **Rationale**: this is the only way the surviving requirements stay covered
  with an empty shipped registry, and it makes the tests exercise the *public*
  contract rather than a privileged built-in — which is also the check
  `threshold-load`'s brief asks for ("it should not need privileges a plugin
  author lacks").
- **Trade-offs**: `tests/test_plugins.py` is plugin-api's file and needs its
  built-in anchor replaced; that churn is unavoidable and is called out as a
  cross-spec coordination item rather than hidden.

## Synthesis Outcomes

- **Generalization.** Req 13.4 (results from the withdrawn calculator) and
  Req 11.2 (superseded formats) are one problem — "this document records a result this tool can no
  longer read" — and get one mechanism. Likewise Req 1.8 (computed-not-selected)
  and `threshold-load`'s insufficiency reporting are one type, distinguished
  only by whether `value` is `None`.
- **Build vs adopt.** Nothing new is adopted. The `[load]` settings reader
  adopts the shipped `plugins.py` per-table pattern verbatim; frontmatter
  editing keeps the line-level upsert rather than adopting a YAML round-tripper,
  for the byte-stability reason already recorded. `tomli-w` stays.
- **Simplification.** Three candidate components were cut: a typed basis enum
  (would claim `threshold-load`'s vocabulary), a second type for
  could-not-be-computed values (folded into `NonSelectedValue.value = None`),
  and a withdrawn-calculator-aware skip path in the engine (subsumed by
  superseded-format recognition). `arbitrate.py` is the one genuinely new
  module, and it exists
  because Req 10 has four failure modes that are worth testing without a
  filesystem.

## Risks & Mitigations (Amendment 2)

- **Cross-spec atomicity.** `contract.py`'s `LOAD_KEYS`, `MANAGED_KEYS`
  membership and `DOC_VERSION` are wiki-contract's, and must change in the same
  commit as the payload/result redefinition or `fitdocs check` reports unmanaged
  keys on every document that has had a load pass. Mitigation: the design places
  these edits in this spec's file plan with an explicit coordination note, and
  the `DOC_VERSION` 2→3 bump carries the regeneration of the eight golden
  documents in the same change.
- **Published compatibility policy (C4).** `docs/plugins.md:245-251` promises
  additive-only change within `0.x`. Redefining `LoadResult` removes fields.
  `WithdrawnCalculator` is already declared *not* public surface
  (`docs/plugins.md:219`), so it is only `LoadResult` that is affected. The
  requirements settle the resolution: the Boundary Context states the statement
  "must declare the surface unstable before 1.0". Mitigation: this design makes
  that paragraph edit alongside the Req 13.3 edit it must make to the same file
  anyway, and records `plugin-api` as the owner needing revalidation.
- **An installation that computes nothing.** Between this spec and
  `threshold-load`, every document receives the honest unsupported state. This
  is specified (Req 13.6), not a regression — but it is user-visible, and the
  unsupported line must read as a deliberate state rather than a failure.
  Mitigation: covered by an explicit end-to-end test over a multi-document data
  root with an empty registry.
