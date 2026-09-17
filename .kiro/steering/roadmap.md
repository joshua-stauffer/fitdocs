# Roadmap

## Overview

Ship the leanest complete value first: **consume `.fit` files and write
one-to-one markdown workout documents**, strong at the workout level, with
computed training load. Doc structure and metric coverage are modeled on
fitdocs.ai's activity views (running, cycling, weight training), approximated
as markdown + pre-rendered charts. Cycle/block organization was explicitly
deferred from the first pass through Phase 6; Phase 7 (discovery 2026-09-15)
lifts that deferral with training-block documents.

The work is decomposed into three specs in dependency order, each a reviewable
increment; the second delivers the first end-to-end user-visible value and the
third delivers the differentiating feature (training load).

## Approach Decision

- **Chosen**: Python package (installable CLI) with a layered pipeline —
  `.fit` → normalized activity model → derived metrics → markdown render with
  pre-generated SVG charts → pluggable load calculators.
- **Why**: Python has the strongest `.fit` ecosystem and is what fitdocs.ai
  already proved out; pre-rendered SVG charts embedded as ordinary image links
  render in Obsidian, GitHub, and any markdown viewer with zero plugins;
  a normalized model keeps renderers and load calculators independent of
  parsing details.
- **Rejected alternatives**:
  - *Mermaid/chart code blocks in the markdown* — renderer-dependent
    (xychart can't do dual-axis power-vs-HR, needs plugin support in some
    viewers); rejected for the hero graph, may still be used for simple bars.
  - *TypeScript/Node implementation* — weaker `.fit` parsing options, no reuse
    of fitdocs.ai's proven metric logic.
  - *Obsidian plugin* — ties the project to one PKM; markdown files + CLI keep
    it PKM-agnostic with Obsidian as a first-class consumer.

## Scope

- **In**: `.fit` ingestion from a target directory; one markdown doc per
  activity; running/cycling/weight-training views; full fitdocs.ai metric
  parity; rich charts (power-vs-HR hero graph and supporting charts);
  `LoadCalculator` interface (the interface stays pluggable and must cleanly
  decline unsupported sports; the methodology behind it is Phase 4's threshold
  engine — the withdrawn methodology that filled this slot in the first pass
  was withdrawn 2026-07-25); interactive prompting for
  missing required data; standalone and pkm-integrated output paths.
  Weight-training docs render metrics from standard watch `.fit` files and
  reserve a section the user fills in manually with the actual workout as
  free-form markdown; regeneration must preserve user-authored content.
- **In (phase 2)**: route maps for activities with GPS data — basemap-tile
  look, rendered as static SVG assets (route-maps spec). Determinism
  constraint is carved out to "byte-identical given a warm tile cache".
- **Out** (deferred): training cycles/blocks/plan-level docs *(lifted in
  Phase 7, 2026-09-15 — `training-blocks`, `plan-resolution` and
  `build-training-block` own the plan level)*; weekly load
  aggregation views *(lifted in Phase 6, 2026-09-09 — `load-history` owns the
  longitudinal page)*; automated `.fit`
  acquisition; non-`.fit` formats
  (GPX/TCX — measured on real HealthFit exports 2026-07-16: GPX sidecars
  are the FIT track re-encoded, mm-level deltas only, so ingesting them
  gains nothing); web UI; cycling and weight-training load methodologies
  (will likely be built in-house later); structured weight-training workout
  templates (first pass: free-form markdown filled in by the user).

## Constraints

- Output must be plain markdown + image files, readable without fitdocs
  installed; PKM affordances (frontmatter, `[[wikilinks]]`) must degrade
  gracefully in vanilla renderers.
- Personal data (`.fit` files, generated docs) never lives in a code repo —
  data-root contract mirrors joshua-stauffer/pkm (`FITDOCS_DATA` env /
  `.fitdocs/data-root` file / explicit flag; loud failure, no repo fallback).
- **Third-party methodology licensing — resolved by withdrawal (2026-07-25).**
  The withdrawn methodology's lookup tables and trademarked name required the
  methodology's author's permission before public redistribution. That
  permission was never obtained. It gated any release of this repository. The
  methodology is withdrawn from the shipped tool (training-load Amendment 2)
  rather than licensed.
  **Retention reversed 2026-07-30 (Phase 5 discovery).** The writeup and the
  extracted tables were kept as research record on the reading that a private
  repository and a published one are the same artifact. Publishing 0.1.0 makes
  them different. The `encumbered-content-purge` spec deleted the writeup and
  the extracted tables from the working tree. That spec's history rewrite
  removes both from git history as well, once it runs.
- No methodology is running-only any more, but the constraint it created
  stands: the load interface must let a calculator decline unsupported sports
  rather than force bad numbers.

## Boundary Strategy

- **Why this split**: parsing/modeling, document rendering, and load
  calculation have different change cadences and contributors (new device
  quirks vs. template/chart polish vs. new methodologies). The normalized
  activity model is the contract between them, so each spec can proceed and
  be reviewed independently.
- **Shared seams to watch**:
  - The **activity model** schema (spec 1) is consumed by both later specs —
    breaking changes ripple.
  - The **workout doc template** (spec 2) reserves a training-load section
    that spec 3 fills; agree on the placeholder contract early.
  - **Athlete profile / interactive prompting** (spec 3) may later be wanted
    by renderers (e.g. zone-colored charts); keep it a separate module, not
    buried in a calculator implementation.

## Specs (dependency order)

- [x] fit-ingest — parse `.fit` files into a normalized activity model
  (sessions, laps, records, sets) with derived metrics at fitdocs.ai parity.
  All 24 checklist items of the first pass shipped. **Reopened 2026-07-26** by
  Amendment 1 (the constant-sourcing work — see Phase 4 › Existing Spec
  Updates, which is the same item) and amended again 2026-07-27 by Amendment 2
  (a developer field's file-declared scale/offset is now applied; shipped).
  **Amendment 1 shipped 2026-07-30 — closure record in Phase 4 › Existing Spec
  Updates.** All three gates it reset are met and `tasks.md` was regenerated in
  merge mode; `spec.json` is back to `phase: tasks-generated`,
  `ready_for_implementation: true`, all approvals `true`, and every one of the
  47 checklist items is ticked (majors 1–7 the first pass, 8–13 the amendment).
  Dependencies: none
- [x] workout-docs — render one markdown doc per activity (per-sport views,
  SVG charts incl. the power-vs-HR hero graph, PKM frontmatter/links), plus
  the CLI, data-root config, and packaging. Dependencies: fit-ingest
- [x] training-load — `LoadCalculator` interface, athlete profile store,
  interactive prompting for missing inputs, and the document integration that
  writes results. Originally shipped with the withdrawn methodology;
  **reopened 2026-07-25** by Amendment 1 (multi-channel result contract) and
  Amendment 2 (the withdrawn calculator withdrawn — the spec now ships the
  carrier and no calculator); **both amendments shipped 2026-07-26 — closure
  record in Phase 4 › Existing Spec Updates.** Dependencies: fit-ingest,
  workout-docs

### Phase 2

- [x] route-maps — **done 2026-07-19** (`tiles.py`, the Map section, and the
  end-to-end determinism/offline validation at task 7.1, `da0bd3e`). Route map
  SVG for outdoor activities (glow polyline +
  start/finish pins over basemap tiles, fitdocs.ai look): slippy tiles
  fetched from a configurable provider via stdlib, cached under the data
  root, embedded as data URIs in an SVG authored with the existing chart
  pattern. 21 of 23 checklist items done (15 of 16 leaves, 6 of 7 parent
  headers). Both unticked lines are bookkeeping, not work: the parent header
  `7. Feature-level validation`, and the **optional** leaf 7.2 (`- [ ]*` — a
  manual push to a scratch GitHub repo to confirm data-URI SVG rendering
  through the image proxy), an empirical spot-check that was never shipped
  work. Dependencies: fit-ingest, workout-docs

### Phase 3 — plugin platform (discovery 2026-07-21)

**Goal**: publish fitdocs as an installable plugin for LLM-powered markdown
wikis (reference: joshua-stauffer/pkm and the Karpathy LLM-wiki pattern).
Design pillars, validated against ecosystem practice during discovery:
(a) fitdocs defines *interfaces* — an inbox where `.fit` files land, an
extension point for user logic; (b) fitdocs is the **sole writer** of its
region of the wiki, except bounded user-owned zones (the Notes region);
(c) tool updates never clobber user customization — user intent lives in
config and plugins, never in forked generated files.

**Approach decision**: formalize what already exists rather than re-architect.
The sync engine, region-marker merge (`docmerge.py`), archive-as-state
idempotency, and `LoadCalculator` Protocol are the right foundations —
matching the converged patterns of paperless-ngx (consume dir),
obsidian-zotero-integration (persist regions), projen (tool-owned files,
user intent in config), and pytest/datasette/mkdocs (entry-point plugins).
Rejected: append-only sync (Readwise model — goes stale; wrong for
immutable workout data), template-forking customization (breaks on update),
pluggy (overkill for a one-object registry).

**Constraint (lifted 2026-07-25)**: the withdrawn calculator's licensing
gated public distribution. Resolved by withdrawing the methodology (training-load
Amendment 2) rather than by sign-off, so the distribution spec no longer
carries it as an external release gate.

_Spec status (updated 2026-07-27): all four specs generated, reviewed, and
approved (`ready_for_implementation: true`); checkboxes below track
**implementation**. wiki-contract, plugin-api, and inbox are all complete;
**distribution is the only Phase 3 spec not started** (0 of 33 checklist
items). Cross-spec consistency review run after generation — its findings
produced the sequencing correction and the pre-wave item below. (plugin-api's
four parent task headers remain unticked in its `tasks.md` while all 12 of
its leaves are done — the headers are a bookkeeping artifact, not remaining
work.)_

#### Direct Implementation Candidates (pre-wave)

- [x] settings-foundation — **done 2026-07-21.** `layout.SETTINGS_FILE` +
  `layout.settings_path()`, new `fitdocs/settings.py`
  (`load_settings_document`, `SettingsError`), `tiles.py` redirected onto the
  shared parse with `tile_settings_from_document` as its per-table reader and
  `TileSettingsError` now subclassing `SettingsError`. One intended behavior
  change: invalid TOML now raises the shared `SettingsError` instead of
  `TileSettingsError`, so the shared file has one file-level voice; the CLI
  catches the shared type. 1194 tests pass, ruff and `mypy --strict` clean.
  Original scope: pure refactor, no behavior change, must land
  before inbox and plugin-api. Three Phase 3 specs independently proposed
  moving `SETTINGS_FILE` into `layout.py` and each added its own reader for
  the same `fitdocs.toml`; left as specified, they collide on `layout.py`
  and `tiles.py` and give three different error voices for one malformed
  file. Extract once: `layout.SETTINGS_FILE` + `layout.settings_path(
  data_root)`, and a `settings.py` that reads/parses the document a single
  time raising one `SettingsError` for file-level problems. Per-table typed
  readers (`[tiles]`, `[inbox]`, `[plugins]`) stay with their owning specs,
  over the already-parsed mapping. Too small and too mechanical for a spec.
  Two details both consuming specs assert as inherited, and which have no
  spec of their own to catch: **an absent settings file yields an empty
  mapping, never an error** (today's `load_tile_settings` returns defaults
  for a missing file — raising instead would silently break shipped
  route-maps behavior); and **`tiles.py` is redirected as part of this
  item** — `tiles.load_tile_settings` is re-pointed onto the shared parse
  and `tiles.SETTINGS_FILE` gives way to `layout.SETTINGS_FILE`. The
  `[tiles]` table's owning spec (route-maps) is already implemented, so
  nobody else will do that redirection.

#### Shared seams to watch (from cross-spec review)

- **Owned-path set**: `wiki-contract` publishes `OWNED_PATHS` and a guard
  test; `inbox` creates `inbox/`, an optional `processed/`, and
  `.fitdocs/quarantine.toml`. The contract must cover tool state
  (`.fitdocs/`) and admit user-configured locations, or whichever lands
  second breaks the other.
- **Skip semantics**: `wiki-contract`'s newer-`doc_version` gate skips
  *without archiving* so the next run retries; `inbox`'s move disposition
  must therefore key on archive presence, never on the `skipped` label, or
  it orphans the file and defeats the retry.
- **Declaration refresh**: `inbox` adds a third engine entry point
  (`drain()`); `wiki-contract` wires `ensure_declarations` only into
  `sync()`/`regen()`. The drain becomes the primary ingestion path, so it
  must refresh declarations too.

- [x] wiki-contract — **done 2026-07-22.** formalize the ownership contract: single
  document-contract module (frontmatter schema + identity + region policy,
  today parsed in 3 places), doc_version migration-by-regen story,
  generated-by provenance, emitted AGENTS.md/ownership declaration in the
  owned tree so humans *and* LLM agents respect the sole-writer boundary.
  Dependencies: none (builds on workout-docs)
- [x] plugin-api — **done 2026-07-27** (all 12 leaves; task 4.4 landed at
  `ff3b7c4`/`68eccac`). Third-party extension without forking: entry-point
  group for load calculators, local plugin-file fallback for bespoke
  vault-resident logic, `fitdocs plugins` listing, registration validation
  with per-plugin failure isolation, versioned typed public API (py.typed).
  Task 4.4 reconciled `design.md`'s public-surface enumeration against the
  shipped `training-load` contract; `design.md:133-139` no longer names
  `supports(activity)` as a coming `LoadCalculator` member, matching the
  reversal recorded under Phase 4. **Open, and out of that task's scope: the
  enumeration re-staled the same day it was reconciled.** `design.md` still
  lists 24 names for `fitdocs.load` and mentions no benchmark vocabulary,
  while the shipped `__all__` is 30 — athlete-benchmarks landed hours later
  and updated `docs/plugins.md` but not this design. Tracked at
  `.kiro/queue/2026-07-27-plugin-api-enumeration-restaled-by-benchmarks.md`,
  `2026-07-27-design-md-enumeration-unguarded.md` (high — nothing guards the
  enumeration against exactly this), and
  `2026-07-27-plugin-api-req5-additive-only-stale.md`.
  Dependencies: settings-foundation
- [x] inbox — **done 2026-07-25** (all 19 checklist items, zero unticked;
  completed by `c6176cd`, task 5.2. `772ab52` on 2026-07-26 touched this
  `tasks.md` once more but ticked no box — an Implementation Note only).
  Promote ingestion from CLI arg to a standing configured
  inbox interface: no-arg `fitdocs sync` drains the inbox with the standard
  watch-folder safeguards (stability check, ignore patterns, quarantine
  channel for failing files, explicit disposition policy). Sequenced after
  wiki-contract so it can extend the owned-path contract, wire declarations
  into `drain()`, and gate disposition on archive presence within its own
  tasks. Dependencies: settings-foundation, wiki-contract (soft: land
  plugin-api's smaller `sync_command` wiring before inbox's CLI task — both
  edit the same region, and the agreed order avoids a merge conflict).
  **Open, but out of this spec's scope**: the feature-validation gate left a
  block of post-implementation follow-ups at the foot of
  `.kiro/specs/inbox/tasks.md`, each needing a human decision because each
  would change behavior or contract beyond the approved spec — headed by the
  unguarded `save_quarantine` in `drain()`, the one path where completed work
  is reported nowhere. None blocked the gate; none is remaining spec work.
- [ ] distribution — publishable package and wiki-integration packaging:
  PyPI release process, semver + changelog, install/upgrade docs, SKILL.md
  (agent-skills packaging) and pkm integration recipe.
  Dependencies: wiki-contract, inbox, plugin-api

### Phase 4 — the threshold load engine (discovery 2026-07-25)

**Goal**: replace the not-working first pass at load with a deterministic,
multi-channel per-activity engine designed for **interop with intervals.icu**,
behind the shipped `LoadCalculator` seam. **Updated 2026-07-25**: the
withdrawn methodology no longer ships (training-load Amendment 2), so the
threshold engine
does not sit alongside it — it becomes fitdocs' only built-in calculator, and
`threshold-load` is therefore on the critical path for fitdocs computing any
load at all.

**Approach decision — compute-all, select-one.** Compute a load for every
channel with sufficient data (Power, HR, Pace), then **select exactly one** via
a user-configurable priority with fallback. Only the selected value feeds
downstream aggregates; the non-selected channel values persist alongside it as
diagnostics. Power = Coggan NP→IF→TSS anchored to FTP; HR = Banister
TRIMP→HRSS anchored to LTHR; Pace = grade-adjusted pace anchored to threshold
pace. Cross-discipline portability comes from the shared **"1 hour at threshold
= 100"** scale, with sport-specificity carried by per-discipline benchmarks —
not from a bespoke fused number.

**Rejected: the original per-activity two-channel synthesis / cross-correction.**
A deep-research pass (2026-07-20; 6 angles → 23 sources → 105 claims → 25
adversarially verified 3-vote; 21 confirmed / 4 refuted) found the fusion step
has **no prior art in any product, paper, or open-source implementation
surveyed, intervals.icu included.** Every platform computes single-channel
loads and selects one with fallback. A bespoke fused number would diverge from
intervals.icu — the opposite of the interop strategy. The *intent* behind
cross-correction is preserved two ways: as a QA divergence flag
(Efficiency Factor / aerobic decoupling), and as the optional later
build-time HR regression. Report:
`raw/docs/2026-07-20-2026-07-20-hr-power-training-load-prior-art.md` in the
pkm data root; synthesis at `wiki/concepts/training-load-calculation.md`.

**Also rejected (refuted 0-3 unless noted, respect these)**: Xert-style
"real-time FTP avoids staleness" (keep the staleness flag); a hardcoded
`Power > Pace > HR` priority (split vote 1-2 — priority is configurable, and
running often prefers pace).

**Refutation withdrawn 2026-07-27.** This list previously also rejected the
web-quoted Banister HR-reserve coefficient string (`0.64·e^(1.92·%HRR)` men /
`1.67` women). The primary text states exactly that pair — Banister (1991)
p. 408 gives `y = 0.64e^(1.92x)` for males and `y = 0.86e^(1.67x)` for females,
where `x` is the delta-HR ratio. The web sources were right; the 0-3 refutation
was wrong and is withdrawn rather than re-marked, because leaving it here told
every later session to reject a string the defining work confirms. What that
refutation was *right* about survives as a live requirement: the coefficients
must be cited to the primary literature in code, and they now can be. Full
extraction, including seven discrepancies between the two defining texts:
`docs/reference/banister-trimp-primary-sources.md`.

#### Scope

- **In**: dated per-discipline benchmark store; Power/HR/Pace channel math with
  explicit data-sufficiency gates; the `threshold` calculator (compute-all,
  select-one, configurable priority with fallback); a widened multi-channel
  result contract and its document representation (payload v2, frontmatter,
  rendered breakdown); the QA flag layer (cadence-lock detection, cross-channel
  divergence, threshold staleness).
- **Out**: per-activity load fusion of any kind; build-time power-calibrated HR
  regression (deferred — see the constraint below); auto-FTP / eFTP
  estimation *(Phase 6, 2026-09-09: `performance-benchmarks` derives dated
  thresholds from tagged races in its own pass; the calculator's own exclusion,
  threshold-load Req 11.6, stands)*; weekly/CTL/ATL aggregation (deferred
  with the plan level *— until Phase 6 for aggregation, `load-history`; until
  Phase 7 for the plan level itself, 2026-09-15*);
  a strength-training load number; the withdrawal of the withdrawn calculator
  (training-load Amendment 2 owns that); getting `.fit` files into the data
  root (inbox owns that).

#### Decisions taken at discovery (2026-07-25)

Resolving the six open questions the discovery brief posed:

1. **Strength load: omitted.** The `threshold` calculator returns the honest
   `Unsupported` outcome for strength. Every strength file in Josh's real data
   has 100% HR coverage, so HRSS is *technically* computable — but the research
   found no basis for folding resistance work into an endurance load number,
   and a computable-but-meaningless value is worse than an absent one.
2. **Running power: no model needed — read recorded watts.** Measured across
   all 74 real HealthFit files (2026-07-25): **every one of the ~45 runs
   carries a power stream at 99–100% sample coverage** (Apple Watch native
   2023–24, Stryd from 2026). So the running power channel is Coggan
   NP→IF→TSS over recorded power against a running FTP; **no Stryd RSS / GOVSS
   / Skiba model is implemented.** *Stated divergence from intervals.icu*: it
   does not ingest Stryd fields natively, so fitdocs's running Power Load is
   computed from data intervals.icu does not have. This is the reason raw FIT
   parsing exists.
3. **Pace channel: in scope for v1.** Three channels, not two. Justified by the
   real data: one run has 100% power but 0% GPS, and **7 of 9 rides carry no
   power at all** — priority-with-fallback is load-bearing, not theoretical.
   Two channels would also make the configurable-priority feature nearly
   vacuous.
4. **Modalities: Run + Ride + Walk/Hike** (the latter two scored via the HR
   channel — Josh's 5 hikes and 3 walks all carry good HR and no power).
   Strength and anything else: `Unsupported`.
5. **Configuration split**: per-discipline benchmarks and their measurement
   dates live in `athlete.toml` under the data root (extending the shipped
   read-only reader); channel priority, sufficiency thresholds, the staleness
   window, and the default calculator live in `fitdocs.toml` `[load]`, read
   through the shipped `settings.py`. Both carry an explicit schema version.
6. **Calculator arbitration**: a configured default calculator names the
   winner, with `--calculator` still forcing one. Today's engine takes the
   first non-`Unsupported` calculator in *registration order*, which a
   third-party plugin could exploit to silently displace a built-in. **Revised
   2026-07-25** (the withdrawn methodology withdrawn, so the two-built-ins
   case is gone): with no
   default configured, exactly one supporting calculator is used and several
   is a reported skip naming the candidates — never registration order.
7. **Build-time HR regression: deferred entirely, not stubbed.** No dead code.
   The constraint on `load-channels` is that the HR channel's intensity
   weighting is sourced through a substitutable component, so the regression
   can slot in later without a rewrite. Fixed physiological TRIMP/HRSS is the
   v1 default — correct anyway for the low-history athlete, which is the
   standalone default case.

#### Constraints

- **Deterministic math only.** All load computation lives in code; the LLM
  layer sits on top and only interprets. No LLM in the numeric path.
- **Interop with intervals.icu, not competition.** Where intervals.icu has an
  established behavior, match it; every divergence needs a stated reason
  recorded in the spec (see the Stryd note above).
- **The public contract may be redefined freely** (ratified 2026-07-25).
  fitdocs is pre-production and has no external plugin authors, so
  `LoadResult`, `ProfileView` and the rest of the plugin-author surface carry
  **no backward-compatibility obligation**. Design the right multi-channel
  contract rather than bolting optional fields onto the single-channel one.
  `tests/test_public_api.py` remains the place the surface is pinned — update
  the pin to the new shape; it is a guard against *accidental* drift, not a
  freeze. Consequence for plugin-api: its Req 5.4 compatibility-policy
  document should state the surface is unstable pre-1.0, which is what makes
  this freedom legitimate rather than a violation.
- **Document migration is already solved.** wiki-contract shipped
  `doc_version` with migration-by-regen and `docio.py` as the single
  frontmatter enforcement point. Payload v2 rides that mechanism; it must not
  invent a second one.
- Absent data is `None`, never a fabricated `0` — a channel without sufficient
  data reports insufficiency, it does not report a load of zero.

#### Boundary Strategy

- **Why this split**: the four new boundaries have genuinely different inputs,
  change cadences, and review criteria. Benchmarks are a *store* (schema,
  dates, migration). Channels are *pure math* (verifiable against published
  worked examples, no I/O). The calculator is *policy* (priority, fallback,
  sufficiency). QA flags are *stream analysis* whose output is not a load value
  at all. Merging channels into the calculator would produce a ~22-task spec;
  keeping the contract redefinition separate is an ownership call — it rewrites
  `load/types.py`, `engine.py`, `render.py` and `docedit.py`, all
  training-load's, which is a different review question from "does the
  threshold calculator select correctly". (Before Amendment 2 this split also
  had to keep the withdrawn methodology working; with it withdrawn the
  contract is defined for the multi-channel case outright, and the ownership
  argument alone carries the split.)
- **Shared seams to watch**:
  - The **widened result contract** is defined by the `training-load` update
    and consumed by `threshold-load`; the contract leads, the calculator
    conforms. Sequence accordingly.
  - **`metrics/stress.py` is fit-ingest-owned** and its `trimp` is already
    rendered into shipped documents. Re-sourcing its coefficients changes
    existing output — that is the fit-ingest update below, and HRSS must
    agree with whatever it lands on. **Resolved 2026-07-30 — HRSS now has a
    landed answer to agree with**: no coefficient moved (`0.64` / `1.92` held,
    now `PRIMARY_TEXT` to Banister 1991 p. 408), but the *shape* did —
    `stress.trimp()` returns `TrimpResult | None` carrying the
    `TrimpWeighting` selection, not a bare float, and the weighting is a
    caller-supplied argument (Req 17.3 forbids fit-ingest reading it from
    profile or config). **The consumer is `load-channels`' weighting seam
    (task 2.1), not its HR channel (task 3.2)** — 2.1 delegates the impulse to
    the shipped function "restating none of its coefficients and editing none
    of its module", while 3.2 is forbidden to read `DerivedMetrics.trimp`, the
    precomputed field. So the return-shape change lands on 2.1 and lands
    early: it is the first task of major 2 and the HR channel depends on it.
    Two knock-ons for whoever implements it — the call must unpack
    `TrimpResult` rather than a float and decide what weighting selection to
    pass (the default is the male curve, `DEFAULT_TRIMP_WEIGHTING`), and 2.1's
    observable "rescaling the shipped multiplicative coefficient scales both
    returned values by the same factor" now means rescaling
    `BANISTER_MALE_COEFFICIENT` in `metrics/sources.py`, not a literal in
    `stress.py` — the constant guard reds on bare literals in that module.
  - **Benchmark applicability is date-scoped, not just dated.** Josh's runs
    cross a measurement-system boundary (Apple Watch native power 2023–24 →
    Stryd 2026). A running FTP measured on Stryd must not retroactively score
    Apple Watch runs; the store's `measured_on` date is what makes that
    expressible.
  - **`athlete.toml` is read-only by construction today** (`athlete.py`, Req
    8.3) while `load/profile.py` writes a separate prompt-driven store. Phase 4
    must reconcile these two, not add a third.

#### Implemented-code survey (2026-07-25) — what the redefinition actually costs

`training-load` is fully implemented, so the contract change was measured
rather than assumed. _The measurements below describe the tree as it stood
before Amendment 2; they name the withdrawn methodology because it was still
shipped when they were taken. Withdrawing it removes two of the three
`LoadResult`
construction sites and a further ~2,650 lines (1,163 src + 1,490 test), which
makes every figure here an upper bound on the remaining work (historical:
the redefinition below shipped 2026-07-26, so the remaining work these
figures bound is now zero):_

- **`LoadResult` has 3 construction sites in `src/`** (two are the withdrawn
  methodology's continuous and interval paths) and its fields are read in
  exactly two
  consumers: `render.py` (payload encode, markdown render, JSON parse-back) and
  `docedit.py` (frontmatter emission). The blast radius is small and
  well-factored.
- **~1,090 lines of test pin the shape directly** (`test_types.py`,
  `test_render.py`, `test_docedit.py`), with `test_engine.py` and
  `test_feature_e2e.py` (~1,210 more) exercising it indirectly.
- **The type is shaped by the withdrawn methodology, not merely
  single-channel.** `zone`, `zone_label` and `structure` (`"3 × 20:00 Z6"`)
  are the withdrawn methodology's vocabulary; a threshold calculator has no
  zone in that sense and no meaningful structure
  string. This is why the contract must be **redefined** rather than extended:
  the problem is not too few fields, it is fields modeled on one methodology
  that the second one cannot fill honestly.
- **No generated document carries the load frontmatter keys** — the demo repo
  has none, consistent with the first pass never having worked. So
  migration-by-regen has nothing to migrate in practice, and the doc-format
  concern is theoretical.

#### Existing Spec Updates

- [x] training-load — **done 2026-07-26.** Redefined the result contract
  around a selected channel plus the non-selected computed channel values and
  QA flags; withdrew the withdrawn calculator (Amendment 2); replaced
  registration-order arbitration with a configured default calculator
  (`load/arbitrate.py`, `engine.py`); shipped payload v2 (`render.py`,
  `LOAD_PAYLOAD_VERSION = 2`) with the `doc_version` bump (`contract.py`,
  `DOC_VERSION = 3` — that was this update's advance and is left as the record
  of it; **the current value is 4**, advanced by fit-ingest Amendment 1 on
  2026-07-30, see its entry below) via wiki-contract's migration-by-regen;
  and added
  frontmatter and rendered breakdown for selected-vs-computed (`render.py`,
  `docedit.py`). Landed Amendment 3's cross-spec rulings — `load/settings.py`
  ownership, a per-pass `LoadContext`, and `NotConfirmed` renamed
  `NotComputed` — with one plan reversal on measured grounds: the
  `LoadCalculator` Protocol does **not** gain a `supports(activity)` member.
  Declaring it on the Protocol would make it mandatory for structural
  conformance under `mypy --strict`, and three of the four stub calculators,
  the installed plugin fixture, and the plain-class shape in
  `docs/plugins.md` all answer `hasattr(cls, "supports") == False` — they
  would raise
  `AttributeError` the first time the engine's gate called it. The sport-
  support question is instead answered by the module-level
  `supports_activity(calculator, activity)` (`src/fitdocs/load/types.py:378`),
  which reads a calculator's own optional `supports` when one is defined and
  otherwise falls back to `supported_modalities` membership; see the
  rationale recorded at `src/fitdocs/load/types.py:18-35`. **Downstream specs
  were repinned on this reversal** (queue item
  `2026-07-26-phase4-specs-pin-withdrawn-supports-member`, closed): the
  unsatisfiable hard prerequisite `threshold-load` recorded for its task 3.3
  is **marked superseded in place** — `tasks.md:43-52` and the `spec.json`
  `phase_note` both keep the original sentence with a dated repin beside it,
  so a grep still finds the old text — and `activity-qa-flags/design.md:62-67`
  explicitly corrects the withdrawn member. Two
  low-importance documentation residuals stay open —
  `.kiro/queue/2026-07-26-training-load-own-supports-references-not-repinned.md`
  and `.kiro/queue/2026-07-27-traceability-table-supports-references-not-repinned.md`
  — both prose naming bare `supports` where the shipped symbol is
  `supports_activity`; neither blocks anything.
  (`load-channels` is unaffected; it implements no calculator.) All 18/18 leaf
  tasks (24/24 checklist items including the 6 parent headers) done; merged to
  main at `762478b` with 1852 tests green. Closes the Phase 1 entry
  above (`training-load` — "reopened 2026-07-25" by Amendment 1 and Amendment
  2): both amendments are now shipped and this line is the closure record.
  **Original scope** (historical — preserved verbatim for audit; see the
  landing note above for what actually shipped): **redefine** the result
  contract around a selected
  channel plus the non-selected computed channel values and QA flags, rather
  than widening the single-channel one. Replace registration-order
  arbitration with a configured default calculator; payload v2 + `doc_version`
  bump via wiki-contract's migration-by-regen; frontmatter and rendered
  breakdown for selected-vs-computed. **Also withdraws the withdrawn
  calculator** (Amendment 2): delete the implementation, its bundled tables
  and packaging,
  and its tests; the spec becomes the carrier and registers no built-in, so
  every document honestly reports unsupported until `threshold-load` lands.
  **Amendment 3 (2026-07-25)** adds the cross-spec rulings from the Phase 4
  batch review: this spec owns `src/fitdocs/load/settings.py` and the pinned
  `load_load_settings(document, settings_file)` surface for the whole `[load]`
  table; `apply_load` reads that table once and owns the resolved
  `LoadSettings` (the CLI keeps only `--calculator`); `compute` gains a
  per-pass `LoadContext(activity_date, settings)` so `ProfileView` stays a
  pure store view; `NotConfirmed` is renamed `NotComputed`; and the
  `LoadCalculator` Protocol gains `supports(activity)` so the engine can
  refuse by sport before running the prompt flow — **this last clause was
  reversed during implementation and did NOT ship; the gate is the
  module-level `supports_activity`, see the landing note above and
  `src/fitdocs/load/types.py:18-35`.**
  Dependencies: none — this update now leads Phase 4. (It previously
  read `load-channels`, which was false in both directions: the redefined
  `LoadResult` landed at task 2.1 before `load-channels` started, and under
  Amendment 3 every Phase 4 spec consumes this one's contract.)
- [x] wiki-contract — **done 2026-07-26.** The `LOAD_KEYS` rename this line
  called for landed inside `training-load` task 2.4 as a declared
  cross-boundary incursion (commit `a782034`): `contract.LOAD_KEYS` is now
  `("load_value", "load_methodology", "load_basis")`, `load_zone`/the
  withdrawn methodology's vocabulary is gone, and an anti-drift test
  (`test_contract.py`) still pins
  `LOAD_KEYS` and `MANAGED_KEYS` together. No separate wiki-contract pass ran.
- [x] fit-ingest — **done 2026-07-30.** Amendment 1 shipped: majors 8–13, 24
  commits, merged `--ff-only` to `main` at `68be52c` with 2286 tests green
  after the rebase and `ruff check` / `ruff format --check` / `mypy` clean over
  74 source files. Every one of the spec's 47 checklist items is now ticked.
  **New surface downstream specs must consume rather than re-add**:
  `src/fitdocs/citation.py` — the single shared citation vocabulary
  (`VerificationStatus`, `Citation`, `FitdocsChoice`, `Agreement`,
  `Corroboration`, `Departure`, `CitedConstant`), sited below `fitdocs.load` in
  the dependency graph so fit-ingest can use it; `load/channels/sources.py`
  re-exports from it and adds no second vocabulary.
  `src/fitdocs/metrics/sources.py` holds **ten** `CitedConstant` bindings, all
  ten collected in the `CONSTANT_SOURCES` registry, plus three `Citation`
  records (`BANISTER_1991`, `MORTON_1990`, `COGGAN_2003`), **three**
  `FitdocsChoice` records, `WEIGHTING_PAIRS`, `DEFAULT_TRIMP_WEIGHTING`,
  `weighting_for` and `DEPARTURES`. (This entry said eleven bindings and four
  choices until 2026-07-30, counting `POWER_ABSENT_SAMPLE_FILL` and
  `POWER_ABSENT_SAMPLE_CHOICE`. Both were **deleted** at `dd10f9f`: an absent
  power sample no longer resamples as a fabricated `0.0`, and a leading dropout
  truncates the grid instead of filling it, so no fill value exists anywhere
  and the record had nothing left to bind. Counts re-measured from the live
  module — do not restore the eleventh.) **`stress.trimp()` now returns
  `TrimpResult | None`, not a float** — it carries the weighting selection
  alongside the value (Req 17.6), which `load-channels`' HR channel consumes
  directly. A new guard, `tests/metrics/test_constant_guard.py`, **reds on any
  bare numeric literal in `aggregates.py` / `power.py` / `stress.py`** (50
  literals, 50 exemptions, keyed by line + column + value), so an edit to those
  three modules owes the exemption list an entry.
  **`BANISTER_TRIMP` is `PRIMARY_TEXT` and `BLOCKED_CITATIONS` is now empty**
  (kept in place rather than deleted — it is the honest record that the
  exception mechanism holds nothing today).
  **The "no migration owed" reading below is superseded — a value did move**,
  though not a coefficient. `0.64` held exactly as the maintainer ruled, and no
  cited constant's value changed; the movement came from the design-gate
  ruling that normalized power emit only *complete* rolling windows (task
  13.1), which moves NP — and with it IF, VI, TSS and bike EF — in whichever
  direction the dropped leading windows' mean fourth power differs from the
  retained series' (a constant-power stream is one instance where it does
  not). So `DOC_VERSION` advanced 3 → 4 unconditionally, every committed
  golden was regenerated, and the regeneration rehearsal (13.3) ran rather
  than being skipped as a branch never taken. **Measured on real data, not
  asserted** (13.4): all 77 of the maintainer's `.fit` files parse and
  compute with zero failures; 54 yield an NP, and across those the median
  move is +0.48 W (+0.17%), max +1.01 W (+0.42%), **53 rose and 1 fell** — a
  hard opener spiking to 737–781 W whose dropped partial windows averaged
  *above* the retained series. That single faller confirmed the direction is
  conditional, correcting an unconditional direction claim `tasks.md` made at
  the time; closed at
  `.kiro/queue/closed/2026-07-30-np-direction-claim-is-conditional.md`.
  **Still open, and out of this amendment's scope**: the two decisions
  `spec.json`'s `design_revision_open_decisions` flags for the maintainer — the
  `TrimpWeighting` member names (`BANISTER_MALE` / `BANISTER_FEMALE`, reported
  in every document via Req 17.6, so the name is what an athlete sees) and the
  two `VerificationStatus` vocabulary gaps — are **not** settled by this
  landing. One queue item was deliberately left open pending this merge because
  it could only be verified from `main`:
  `.kiro/queue/2026-07-27-coggan-2003-sources-three-amendment-1-constants.md`
  is now verifiable and ready to close, which is the maintainer's call.
  **Original scope** (historical — preserved verbatim for audit; the landing
  note above records what actually shipped, and supersedes this text's
  "no migration-by-regen is owed" conclusion): The amendment widened this item
  beyond TRIMP to *every* fit-ingest constant citing
  `docs/reference/fitdocs-ai-reference.md` §2 (`stress.py`, `power.py`,
  `aggregates.py` — eight constants across seven enumerated items; two of the
  eight are bare literals rather than named constants, the NP averaging
  exponent and the moving-time threshold at `aggregates.py:103`),
  added Requirements 15–18 (criteria 71 → 95, then 95 → 98 when the
  design-gate revision added 15.8, 15.9 and 16.7 for the fitdocs-chosen
  category), and made Banister's weighting a
  caller-supplied selection defaulting to today's pair so no athlete's number
  changes silently. `requirements.md` is approved and `design.md` regenerated;
  **design approval is the open gate and `tasks.md` is not yet regenerated.**
  ~~[Superseded 2026-07-30: both gates are met — design approved at the
  2026-07-28 fast-track, `tasks.md` regenerated in merge mode the same day, and
  the amendment is implemented. See the landing note above.]~~
  Original scope: re-source `metrics/stress.py`'s Banister TRIMP coefficients
  from the primary literature (Banister 1991 / Morton 1990) and cite them in
  code — undertaken on the assumption that it would move `DerivedMetrics.trimp`
  and so owe migration-by-regen. **Obstacle cleared 2026-07-27: the maintainer
  supplied both primary texts and both have been read in full.** Banister
  (1991) as page scans of the complete chapter 9 (pp. 403–424) and Morton,
  Fitz-Clarke & Banister (1990) as the publisher PDF; extracted with page and
  equation numbers to `docs/reference/banister-trimp-primary-sources.md`. This
  supersedes the earlier "searched for and not obtained" finding and the
  document-access warning that followed from it — the remaining work is an
  ordinary edit. Three consequences a session picking this up must carry:
  - **The coefficient is settled: keep `0.64`** (maintainer ruling
    2026-07-27). It is what Banister p. 408 states, and it is what Morton's own
    worked example implies even though Morton's Eq. 2 prints the weighting
    without it. Because the shipped value does not move, this item no longer
    changes any rendered `trimp` and **no migration-by-regen is owed** — but the
    citation note must record that the two primary texts disagree, since
    flattening that is exactly what the citation-vocabulary work was about.
  - **`BANISTER_TRIMP` is unblocked**, so the premise for its
    `SECONDARY_ATTESTATION` status and its `BLOCKED_CITATIONS` membership is
    gone. The maintainer's earlier ruling that the tracked exception was
    acceptable for load-channels rested on the search genuinely failing; that
    rationale has expired. fit-ingest's Req 15.4 was never relaxed and now has
    no unsatisfiable-requirement risk to carry here.
  - **Do not pin Banister's printed worked examples as test vectors** — all
    three contradict his own equation. Queue:
    `2026-07-27-banister-figure-captions-unusable-as-vectors`.

  Dependencies: none

#### Specs (dependency order)

_Spec status (updated 2026-07-30): all four specs generated, reviewed and approved
(`ready_for_implementation: true`); the checkboxes below track **implementation**,
per the Phase 3 convention. **athlete-benchmarks is complete**; load-channels is
in flight at its first task; threshold-load and activity-qa-flags have not
started. **All three Existing Spec Updates above are now shipped, so nothing
upstream blocks Phase 4 any longer: `load-channels` is the next work on the
critical path** (19 of its 20 checklist items open) and it is the only Phase 4
spec whose dependencies are all met — threshold-load and activity-qa-flags wait
on it, in that order. Generated in four sequential waves — the dependency
chain is linear — then run through two cross-spec consistency rounds. Round 1
found four blocking issues; round 2 found one more and re-verified the rest.
All are resolved:_

1. _**The heart-rate channel's `intensity` was on a different scale from power's
   and pace's** — it was the square of theirs for the same load, agreeing only at
   exactly 1.0, which was the sole point `load-channels`' own scale test
   exercised. `activity-qa-flags`' divergence flag would have read DIVERGENT on
   easy aerobic sessions where the channels agreed perfectly. Fixed to
   `intensity = sqrt(impulse_ratio)`, with `load == hours × intensity² × 100`
   stated once as an invariant and pinned at more than one point. HR load values
   are unchanged._
2. _**`src/fitdocs/load/settings.py` had up to four claimants**, two reader
   names and two shapes. Pinned to `training-load`:
   `load_load_settings(document, settings_file)`, every field defaulted, unknown
   keys and sub-tables ignored so siblings extend one dataclass. Canonical test
   module `tests/load/test_settings.py`._
3. _**A calculator had no route to its own configuration.** `compute()` gains a
   per-pass `LoadContext(activity_date, settings)`; `ProfileView` reverts to a
   pure store view rather than accumulating per-pass state._
4. _**`[load]` was read twice** — the CLI and `apply_load` both. `apply_load`
   now reads it once and owns the resolved settings._
5. _**A real import cycle** (`types → settings → qa → qa.flags → types`) that
   Amendment 3 introduced and mis-diagnosed as absent. Reproduced failing on
   every entry point, then cut by a `TYPE_CHECKING`-only import in
   `load/types.py`. Two alternatives were empirically tested and rejected._

_Also carried: `NotConfirmed` → `NotComputed`; the module-level
`supports_activity(calculator, activity)` (not a Protocol member — see the
training-load Existing Spec Update entry above) so unsupported sports stop
prompting first. Deferred by decision:
`required_athlete_fields()` stays activity-blind, so a runner with no bicycle is
still asked for a cycling FTP each interactive pass — recorded as a known
limitation in `training-load` and `threshold-load`._

- [x] athlete-benchmarks — **done 2026-07-27.** All 15 leaf tasks (21
  checklist items); merged to `main` at `acf5778`, validated on `main` with
  2064 tests green and `ruff check` / `ruff format --check` / `mypy --strict`
  clean. Dated, per-discipline threshold store (running and
  cycling FTP, LTHR, HRmax/HRrest, threshold pace) with staleness computation,
  reconciling today's read-only `athlete.toml` with the writable prompt-driven
  profile. **New public surface downstream specs must consume rather than
  re-add**: `fitdocs.load` exports `Benchmark`, `BenchmarkKind`,
  `BenchmarkRef`, `BenchmarkAge`, `benchmark_age` (30 names total);
  `ProfileView` gained `benchmark(kind, discipline, on=)` and
  `has_benchmark()`; `AthleteField` gained an optional `benchmark:
  BenchmarkRef`; `src/fitdocs/benchmarks.py` is a new pure domain leaf (no
  `fitdocs.load.*` imports, no I/O, no clock); `athlete.toml`'s schema version
  is now 2; `load/settings.py` gained the `benchmark_staleness_days` field
  **and the public `DEFAULT_STALENESS_WINDOW_DAYS: Final[int] = 84`** — the
  rest of training-load's reader/error/defaults surface is untouched. (The 30
  names above are the shipped `__all__`; `plugin-api/design.md`'s enumeration
  still says 24 — see that entry's residual note.)
  Dependencies: training-load — it extends `LoadSettings` in
  `load/settings.py`, and after Amendment 3 removed `activity_date` from
  `ProfileView` its only route to the activity date is
  `LoadContext.activity_date`, so without that amendment it cannot compute
  staleness at all. (Read `none` in the first pass; corrected 2026-07-25 by the
  same reasoning applied to load-channels and activity-qa-flags.)
- [x] load-channels — **implemented 2026-08-25 at e350709, 20/20 tasks (ticked 2026-09-15; spec.json phase still reads tasks-generated).**
  The channel package and its provenance record ship
  (`src/fitdocs/load/channels/sources.py`), guarded by
  `tests/load/channels/test_sources.py::test_every_module_level_citation_is_registered_in_citations`
  — a *test*, by namespace reflection; the shipped module itself validates
  nothing at import. The channel math itself
  is not written yet. The pure per-channel load math: Power (NP→IF→TSS), HR
  (Banister TRIMP → HRSS), Pace (grade-adjusted), each with an explicit
  data-sufficiency gate. Dependencies: athlete-benchmarks, training-load
  (it extends `LoadSettings` in `load/settings.py`, which the training-load
  update creates — an implicit dependency the first pass omitted)
- [x] threshold-load — **implemented 2026-08-29 at 09aa9b2, 18/18 tasks (roadmap bullet ticked 2026-09-15)** — the `threshold` calculator: compute every channel with
  sufficient data, select one by configurable priority with fallback, emit the
  selection and the diagnostics. Dependencies: athlete-benchmarks,
  load-channels, and the training-load contract update
- [ ] activity-qa-flags — cadence-lock detection (HR-vs-cadence temporal
  correlation), cross-channel divergence (Efficiency Factor / aerobic
  decoupling), and threshold-staleness surfacing. Dependencies:
  athlete-benchmarks, load-channels, threshold-load, training-load (it
  consumes `QualityFlag`, payload v2 and the flags renderer — an implicit
  dependency the first pass omitted, though the spec's own tasks.md lists it)

### Phase 5 — going public (discovery 2026-07-30)

**Goal**: publish the repository and ship 0.1.0 as an sdist. The trigger for
this phase is that everything in it is a consequence of *publication*, not of
any feature: content that was acceptable in a private repository is not
acceptable in a public one, and a package with no audience needs no licence
file, no changelog and no CI.

**Approach decision — purge first, release second.** A git history rewrite
costs almost nothing while the repository is private with no clones, and grows
more expensive with every one. The encumbered material is removed and the
history rewritten *before* any release work, and `distribution` then proceeds
at its own pace against a tree that is already clean. Rejected: cutting a
minimal release slice in parallel (couples an irreversible one-shot operation
to a deadline), and doing the full `distribution` spec first (would publish
the encumbered blobs, which is the thing this phase exists to prevent).

#### Decisions taken at discovery (2026-07-30)

- **Purge depth — two things discovery's reading got wrong.** Discovery
  scoped the removal to the writeup and the two extracted tables under
  `docs/reference/`, and decided that the third party's name is retained
  wherever it records the decision. `training-load/research.md` reproduces
  the methodology's operative content in symbolic form: the two load
  formulas, the rule that generates the fingerprinted discount factors, and
  two worked-example vectors. Requirements therefore widened the sweep to
  every tracked file, not only `docs/reference/` (2026-07-30). Requirements
  also reversed the name-retention decision (2026-07-31). The third party's
  identity is erased instead, with no replacement name substituted, wherever
  it appears in the tree — steering, spec documents, commit messages, and
  the guards that stop the material being re-added. What survives is the
  fact that a third-party methodology was evaluated, found to carry a
  redistribution restriction, and withdrawn, naming neither the methodology
  nor its author. Rejected: substituting a pseudonym (risks colliding with a
  real person) and total erasure of the audit trail (loses both the guard
  and the record that anything was evaluated at all).
- **`.kiro/` is public, and excluded from the sdist.** The planning record
  stays visible in the repository — it is the audit trail for the purge and
  the record of how the project was built — while the package stays lean.
  `tests/` is excluded on the same grounds. Today neither is excluded and both
  ship.
- **`main` is force-pushed.** Authorised by the maintainer: the repository is
  private with no other contributors. *(Superseded in mechanism, Amendment 2,
  2026-08-22: there is no force-push. The replacement pushes a single fresh
  root to a **renamed, empty** remote, `joshua-stauffer/fitdocs`. The
  authorisation and its grounds stand -- they are why the operation costs
  nothing. Amendment 3, same date: the old `fitdocs_oss` is **retained**, not
  deleted, as a private remote-side archive; it keeps serving the old history,
  and its privacy is what keeps that unpublished.)*

#### Constraints

- **A root-commit rewrite invalidates every SHA in the repository.** The
  initial commit introduced the writeup and both tables and is the *only*
  commit on `main` that ever touches them — which is why the blast radius is
  total rather than narrow: every commit on `main` carries the material, so
  every one changes identity. Every queue item carries a `pinned_at:` field
  without exception, and `tests/fixtures/report_baseline_faa6d09.py` names a
  commit in its filename. `docs/reference/history-rewrites.md` is the
  provenance record. The purge owns stating its position on each class
  there, with the remainder recorded in that document's part two once the
  rewrite runs. Nobody repairs them by hand.
- **The rewrite halts rather than orphans unlanded work.** Before rewriting,
  the purge checks whether any branch other than `main` exists, whether any
  additional worktree exists, and whether any tree carries uncommitted
  tracked changes. If it finds any of those, it halts without rewriting and
  reports what it found, leaving the repository exactly as it was. This is
  still a hard sequencing constraint on a repository that routinely runs four
  concurrent sessions — see `concurrency.md` — because a halted purge blocks
  release rather than because unlanded work would be destroyed. The rewrite
  is scheduled against a quiet tree, not squeezed between merges.
  **Scheduled 2026-07-31, as a solo session** (maintainer, 2026-07-30). Any
  session starting work before then owes itself the question of whether it can
  land first, since a blocked purge is everyone's problem. Nothing else runs
  concurrently with the rewrite.
- **A force-push may not be sufficient to remove the blobs from GitHub.**
  Unreachable objects can remain fetchable by SHA until the remote garbage
  collects, on a schedule the maintainer does not control. Establish what the
  remote actually still serves rather than assuming. *(Settled: the
  encumbered-content-purge replaces history with a fresh root and publishes it
  to a renamed remote — Amendment 2, 2026-08-22. Deleting and recreating is no
  longer the live option it was when this line was written: under Amendment 3,
  same date, the old repository is **retained** rather than deleted, so
  Requirement 8 is satisfied with respect to the canonical repository and the
  old one stays private with its history intact.)*
- **`refs/original/` held the only copies of two never-pushed branches**
  (`impl/athlete-benchmarks`, `impl/training-load`) from the 2026-07-26 email
  rewrite. **Settled during requirements (2026-07-30):** both branches'
  commits later landed on `main` by rebase, under different commit
  identifiers carrying the same subjects. Preserving the refs verbatim would
  have preserved the maintainer's personal address the 2026-07-26 rewrite
  existed to remove, so they were deleted during this spec's design phase,
  before Major 3 began. Task 7.1 asserts their absence again rather than
  relying on that prior deletion.
- No validation regression: the full suite, `ruff check`, `ruff format --check`
  and `mypy` are green on `main` and must be green on the rewritten tree.
  Measure the suite rather than quoting a size — every count written into this
  phase during discovery was superseded within a day, and the commit and queue
  figures moved again during the requirements phase.

#### Existing Spec Updates

- [ ] distribution — the release half of this phase, already approved and
  unstarted (0 of 33 checklist items). It owns everything the purge does not:
  the `LICENSE` file that `pyproject.toml:7` declares but does not ship,
  classifiers and project URLs (neither present), the `.kiro/` and `tests/`
  sdist excludes, the README rewrite (task 5.2), the CI workflow (task 6.2),
  the changelog, the release procedure and tag/publish. **Two amendments are
  owed before implementation, and both should be written after the purge
  lands so the requirement is amended once against the final state rather
  than twice**: Requirement 6 is premised on a bundled calculator withdrawn
  on 2026-07-25 (queue item `2026-07-30-distribution-req6-assumes-a-bundled-calculator`,
  high), and its artifact-licensing gate — designed at `design.md:279-295`,
  unbuilt — is the only thing that would stop a `uv build && uv publish` from
  shipping encumbered material, since there is no CI at all (queue item
  `2026-07-30-no-release-gate-on-the-publish-path`, high). Dependencies:
  encumbered-content-purge

#### Direct Implementation Candidates

- [ ] The stale `## Status` section of `README.md:10-16` — "Early discovery /
  spec phase. No installable package yet." — contradicts a working 0.1.0 with
  five CLI commands and a fully green suite. `distribution` task 5.2 rewrites
  the readme wholesale and owns this; correcting the one paragraph sooner is
  cheap and stops the repository lying about itself in the interim. Only do
  this directly if `distribution` is still unstarted when someone notices.
- [ ] Root housekeeping visible to a first-time reader: the untracked
  `agent-log` symlink, and the stale `dist/fitdocs-0.1.0-py3-none-any.whl`
  from 2026-07-25. Both are gitignored, neither is tracked, and neither
  reaches an artifact — cosmetic, and listed so it is not rediscovered as a
  finding.

#### Specs (dependency order)

- [x] encumbered-content-purge — **done 2026-08-23** (all 57 checklist items;
  merged to `main` at `87ce085`). The history was replaced rather than pruned
  in place: a fresh root commit, `c3d2201`, now carries the certified tree, and
  no pre-replacement commit identifier resolves against it or ever will — there
  is no mapping by construction. The durable account is
  `docs/reference/history-rewrites.md`; the epoch-pin convention it forces on
  queue items is documented in `.kiro/queue/README.md`.

  **What a later session must know.** The one-shot tooling (`scripts/purge/`
  entire, `tests/purge/` less three relocations) was deleted at task 9.3 and
  the operation is **not repeatable** — do not file or act on defects in it.
  Three guards survive and are live: `tests/_forbidden_strings.py`,
  `tests/test_forbidden_strings.py` and `tests/_content_oracle.py` (with their
  test modules). Req 11.4 is verified satisfied on the tip: a case-insensitive
  search for the notice's reserved-rights phrase over all tracked files returns
  no hits. Two release gates remain open and belong to `distribution`, not
  here: the sdist member allowlist and the `agent-log` symlink that ships in
  the sdist.

  Post-completion queue triage on 2026-08-23 closed 56 of the 85
  purge-related items (199 open -> 141) — see
  `.kiro/queue/closed/2026-08-23-forty-five-queue-items-cite-the-retired-purge-machinery.md`.

  Original scope: delete the withdrawn methodology's writeup
  and its two extracted tables from the working tree and from git history;
  erase the third party's identity from the tracked record; re-base the two
  guards that read them onto an oracle that outlives them; move the retention
  rulings in `roadmap.md`, `structure.md`, `training-load/design.md` and
  `training-load/tasks.md`; remove a third party's contact detail and the
  maintainer's personal address from tracked files; one rewrite across all
  refs with verification that no object reaches the removed paths, locally and
  on the remote. Dependencies: none — but see the sequencing constraint above,
  which is stronger than a dependency edge

### Phase 6 — historical fitness from races (discovery 2026-09-09)

**Goal**: let the athlete use the archive to plan. Two things are missing:
the archive's pages score *not computed* because no benchmark on file is dated
before today, and nothing shows how load accumulates and decays over months.
The athlete's races are dated maximal performances — the literature has
converted such results into threshold estimates for forty years, and they are
the criterion performances Banister's model was fitted to in the first place.
Phase 6 turns tagged races and hard efforts into dated benchmarks, draws the
fitness/fatigue/form curve over the whole archive on one page, and — as a
separate, gated step — fits the model's constants to the athlete's own results.

**Approach decision — tag on the page, benchmarks written to `athlete.toml`,
history read from documents only.** The athlete marks a workout page as a
race, test or hard effort with a user-owned frontmatter key (the contract's
first such key; today any unmanaged key is dropped on regeneration). A
derivation pass re-parses only tagged activities and writes dated, provenanced
entries into the one place thresholds already live, so the shipped calculator
scores the archive with no change to its code. The history page reads every
page's date and load from frontmatter and never opens a `.fit`. Rejected: *a
race registry in `athlete.toml`* (no contract change, but the tag lives away
from the page it describes, same-day activities are ambiguous, and race
markers need a second lookup); *deriving anchors inside the calculator with
nothing written* (contradicts threshold-load Req 11.4/11.6, the permanent
exclusions that keep estimation and aggregation out of the calculator, and
would leave the derived numbers invisible to the athlete).

#### Decisions taken at discovery (2026-09-09)

- **Fitness in two steps.** Step one draws fitness/fatigue/form with the
  exponentially-weighted recursion of Morton, Fitz-Clarke & Banister (1990)
  eq. (4)/(5) using *published seed constants*, labelled as seeds (reference
  doc D5). Step two, its own spec, fits k₁/k₂/τ₁/τ₂ to tagged race results as
  criterion performances — and the viability check found that step to be on
  thin ice (below), which is exactly why it is separate and gated.
- **Hand-tagged efforts only.** No auto-detection of best efforts in this
  phase; a mean-maximal pass over 2,478 files that would also pick up tempo
  runs and GPS artefacts is listed as a follow-on candidate, not scheduled.
- **One longitudinal page.** Fitness/fatigue/form chart with race markers,
  weekly table, coverage statement. No forecasting, no plan/cycle/block
  documents — those stayed deferred as product.md said *(lifted by Phase 7,
  2026-09-15)*.
- **Running and cycling.** The maintainer chose both over running-only.
  Running derives threshold pace and LTHR; cycling derives FTP and LTHR.
  Caveat recorded: the 2026-07-15 HealthFit sample carried no cycling power,
  so the FTP derivation may derive nothing on this archive — it must say so,
  never fabricate.
- **Wave 0 is the prompt-date fix.** Queue item
  `2026-08-27-prompt-date-strands-historical-documents` (critical, maintainer
  ruling 2026-08-29: extend the design to handle past dates) lands first via
  its own resume command, so the history page also covers activities before
  the first tagged race. Derived entries carry their own dates and do not
  depend on whichever semantic wave 0 picks.

#### Scope

- **In**: user-owned frontmatter keys and the effort-tag vocabulary; the
  derivation of threshold pace, LTHR and FTP from tagged efforts, written as
  dated, provenanced benchmarks; the daily load series from documents, the
  fitness/fatigue/form recursion with cited seed constants, and one history
  page with an SVG chart, race markers, weekly table and coverage statement;
  a gated least-squares fit of the model's constants to tagged race results
  with a fidelity report; the commands, owned paths and settings each needs.
- **Out**: auto-detection of races or best efforts; forecasting form at a
  future date; plan, cycle and block documents *(lifted by Phase 7,
  2026-09-15)*; deriving maximum or resting
  heart rate; any change to channel arithmetic, selection, or the calculator;
  sports other than running and cycling; non-Morton model variants.

#### Constraints

- **Citation discipline decides what ships, and the viability check
  (2026-09-09) mapped the ground.** Full tables are in the briefs. In short:
  Riegel's power law (1981; the 1.06 exponent from Riegel 1977, attested in
  Drake et al. 2024) is the cleanest single-race path to a one-hour pace and
  cites as *secondary attestation* until the JSTOR-only 1981 text is read;
  Daniels' VDOT coefficients are not printed in either Daniels text and cannot
  cite to a page; critical speed needs ≥ 2 race distances and is not a one-hour
  pace. LTHR from a sustained effort has a primary chain (McGehee et al. 2005,
  30-min TT; Dumke et al. 2006, 60-min TT — both whole-effort average); the
  coaching-book "final 20 of 30 minutes" is secondary and its discard
  unsourced. FTP's definition is in Coggan (2003), in hand; the 0.95 ×
  20-minute rule is Allen & Coggan's with the **book page unverified** and
  Borszcz et al. 2018 as the measured attestation (limits of agreement about
  ±40 W). Coggan's 42/7-day constants have **no peer-reviewed origin** — trade
  and vendor literature only — and the `1/τ` vs `e^(−1/τ)` recursion form is a
  fitdocs choice to record.
- **The fit is not citable as meaningful on sparse data.** Hellard et al.
  2006 and Marchal et al. 2025 report non-identifiable k₁/k₂ even with 35–54
  performances in ≤ 15 weeks; there is no peer-reviewed minimum-N rule; a few
  dozen races over nine years is sparser than any published dataset.
  `performance-model-fit` therefore ships a refusal gate, confidence intervals
  or a flatness check, and a fitness-only variant as a first-class option, and
  proceeds to requirements only after `load-history` has reported how many
  criterion points the archive actually holds.
- **Absent data is `None`, never a fabricated value** — a declined
  derivation, a suppressed curve segment and a refused fit are outcomes with
  reasons, not zeros.
- **Documents are the history page's only input** (no `.fit`, no network, no
  clock beyond the pass's `today`); the derivation pass re-parses only tagged
  activities. Both are byte-deterministic.
- **Stdlib only.** The optimiser is written in Python; cross-platform golden
  tests on fitted constants use a stated tolerance because `math.exp` is
  libm-backed.
- **The data root has no home for a non-activity page today**
  (`layout.py`, `OWNED_PATHS`, `DECLARED_DIRS`, `tests/test_confinement.py`):
  `load-history` adds one, and every guard moves in the same change.
- No personal data in the repository; the athlete's real wiki is a manual
  check, never a fixture.

#### Boundary Strategy

- **Why this split**: the tag is a document-contract fact consumed by three
  specs, so it is its own small spec rather than a corner of the first
  consumer; derivation writes the store and the history reads documents, and
  they share nothing but the tag, so they run in parallel; the fit is the one
  piece whose viability is in doubt, so it is last and gated.
- **Shared seams to watch**: `src/fitdocs/contract.py` — the `MANAGED_KEYS`
  anti-drift pin must keep holding while a separate user-owned key set is
  added (effort-tags); the benchmark entry's `source` field — the merge in
  `load/profile.py` already preserves unknown keys but the serializer emits
  only three, so parser, serializer and `with_benchmark` move together
  (performance-benchmarks); `layout.py` + confinement guard for the history
  page (load-history); `load-channels`' sufficiency rules — reused or mirrored
  by the derivation leaf, but the channels package's purity guard forbids any
  import back into it; `tests/load/threshold/test_boundary.py` pins the
  calculator's allowed imports, and neither new pass may become reachable from
  it.

#### Existing Spec Updates

- [x] training-load — **wave 0**: the prompt-date semantic, picked up with the
  queue item's own resume command (`/kiro-impl training-load [queue:
  .kiro/queue/2026-08-27-prompt-date-strands-historical-documents.md] Decide
  how a prompt-answered benchmark is dated, then implement`); and its
  out-of-scope line ("weekly/cycle load aggregation … auto-updating athlete
  fitness from race results") amended to point at `load-history` and
  `performance-benchmarks`. Dependencies: none. *Landed 2026-09-10 as
  training-load Amendment 4 / athlete-benchmarks Amendment 1: the answer
  keeps its measurement date and the athlete is asked whether it also
  applies back to the prompting activity's date, persisted as an optional
  `applies_from` on the entry; selection falls back to such an entry only
  when no earlier measurement covers the activity. Derived Phase 6 entries
  carry their own dates and need no `applies_from`.*
- [x] athlete-benchmarks — a `source` provenance field on a benchmark entry
  (parser, serializer, `with_benchmark`), the never-overwrite rule for entries
  the deriver did not write, and its boundary line excluding estimation
  amended to point at `performance-benchmarks`. Landed by
  `performance-benchmarks`' tasks, the way athlete-benchmarks itself amended
  training-load's settings reader. Dependencies: effort-tags. *Done
  2026-09-11, performance-benchmarks task 5.3, at athlete-benchmarks
  Amendment 2: requirements 1.13, 2.12-2.14, 6.11-6.12 added (the source
  field's optionality, closed origin class, derived-origin required fields,
  ignored-unknown-inner-key rule, rewrite preservation/overlay, and the
  never-modify rule for a non-derived entry), the estimation-boundary line in
  requirements.md and design.md amended, and spec.json's amendments list and
  updated_at bumped. No existing criterion renumbered.*
- [ ] wiki-contract — user-owned frontmatter keys as a contract class with
  their own pin (landed by `effort-tags`), and the history page's owned
  location and, if typed, document type (landed by `load-history`).
  Dependencies: none

#### Direct Implementation Candidates

- [x] product.md's "Explicitly deferred" line — weekly aggregation views
  lifted, cycles/blocks kept. Done in this discovery change.
- [ ] Verify the Allen & Coggan chapter/page locators (2nd ed. 2010: FTP
  testing and the 0.95 rule; the Performance Management Chart constants) from
  a physical copy before either `CitedConstant` is written. A reading task,
  not code; owed to `performance-benchmarks` and `load-history` and listed
  here so it is not rediscovered as a blocker inside a task.

#### Follow-on candidates (not scheduled)

- `effort-detection` — mean-maximal best-effort mining over the archive to
  propose tags for confirmation; needs a pass over every `.fit` and a
  false-positive story.
- A forecast on the history page — form at a target date given a planned
  weekly load.
- Critical-speed derivation once an athlete has two or more tagged races at
  different distances (Monod & Scherrer 1965; Jones & Vanhatalo 2017).
- Maximum and resting heart-rate derivation, if a defensible method exists.

#### Specs (dependency order)

- [x] effort-tags — **spec written 2026-09-10; implemented 2026-09-11 at 1dc8633, 18/18 tasks (ticked 2026-09-15)** (Phase 6 batch, `tasks-generated`, all approvals set; 6 requirements, 5 majors / 14 executable tasks, major 3 a single promoted task; cross-spec reviewed). User-owned frontmatter keys marking a workout page as a
  race, test or hard effort, with optional official distance, time and event
  link; preserved byte-for-byte across sync, regen and the load pass;
  validated; read through one contract reader. Dependencies: none
- [x] performance-benchmarks — **spec written 2026-09-10; implemented 2026-09-12 at bee5d59, 23/23 tasks (ticked 2026-09-15)** (Phase 6 batch, `tasks-generated`, all approvals set; 10 requirements, 5 majors / 18 executable tasks; cross-spec reviewed). A pass that derives dated threshold pace, LTHR
  and FTP from tagged efforts through cited models and writes them to
  `athlete.toml` with provenance, never overwriting what the athlete typed.
  Dependencies: effort-tags
- [x] load-history — **spec written 2026-09-10; implemented 2026-09-11 at 9a86e48, 25/25 tasks (ticked 2026-09-15)** (Phase 6 batch, `tasks-generated`, all approvals set; 8 requirements, 5 majors / 20 executable tasks; cross-spec reviewed). The daily load series from documents, the
  fitness/fatigue/form recursion with cited seed constants, and one history
  page with chart, race markers, weekly table and coverage statement.
  Dependencies: effort-tags
- [ ] performance-model-fit — **gated**: a least-squares fit of the model's
  constants to tagged race results with a sufficiency gate, confidence
  intervals and a fitness-only option, offered to the history page in place of
  the seeds; requirements begin only after `load-history` reports the
  archive's criterion-point count. Dependencies: performance-benchmarks,
  load-history

### Phase 7 — training blocks (discovery 2026-09-15)

**Goal**: let the athlete plan. Phase 6 gave every page a load and drew the
fitness curve over the archive; the archive can now describe what training
*did*. Nothing can yet state what training *should* do next. Phase 7 adds the
plan level as one document per training block: dated bounds, a goal in prose,
a mesocycle length, and a table — organized by numbered mesocycle and day — of
planned workouts that link out to their own pages before any `.fit` exists.
Logged workouts are reconciled against the plan as they arrive, the plan is
expected to change midstream and the page keeps the record of it, and one
packaged skill is the canonical way a curating LLM builds a block.

**Approach decision — an athlete-owned plan source, rendered pages, one
reconciling pass.** The block is authored as one structured source file
(TOML; the maintainer's LLM writes it through the skill) in a user-owned
location fitdocs only reads, exactly as `athlete.toml` and `fitdocs.toml`
are read. fitdocs renders the block page and one planned-workout page per row
into a new owned location, the way a `.fit` becomes a workout page. Changes to
the plan are appended to the source as dated amendments, never edits to
earlier entries, so the source is its own history and the render shows the
current table beside the original plan and each supersession. A reconciling
pass — pure over (source, the corpus's frontmatter, settings) — matches
logged workouts to planned rows, sums actual load per mesocycle against the
source's target, and rerenders; it keeps no state of its own, so a better fit
logged later replaces an earlier match without a migration. The athlete's
final say on an ambiguous match is an entry in the source, not a key on the
workout page. Rejected: *a hand-authored block page with tool regions*
(makes LLM-written markdown an input format, inverts the ownership model on
one page, and has no natural revision record); *a user-owned override key on
the logged workout page* (viability check 2026-09-15: a key outside
`MANAGED_KEYS` ∪ `USER_KEYS` is dropped by the next regeneration, so it would
need a second user-owned key class and move both exact pins on `USER_KEYS` —
`tests/test_contract.py:296-306`, `tests/test_ownership_contract.py:137` —
for a fact that is about the plan, not the workout); *the plan source inside
the owned directory* (the ownership contract defines owned as "may create,
rewrite, or delete wholesale", `docs/ownership-contract.md:37-40,61-67`, and a
regeneration would be entitled to delete the athlete's plan); *in-place
region editing of the block page by the reconciler* (`load/docedit.py` is
hard-bound to the load region and `LoadResult`, `_atomic_write` is private to
`load/engine.py`; whole-page regeneration from two inputs, the history page's
model, needs none of it).

#### Decisions taken at discovery (2026-09-15)

- **Path E, three new specs, three existing-spec updates** (maintainer,
  2026-09-15): `training-blocks` (source, pages, location, command),
  `plan-resolution` (matching, per-mesocycle load, chaining, overrides),
  `build-training-block` (the packaged skill). Folding the skill into
  `training-blocks` was offered and declined: the skill must teach
  disambiguation, so it cannot ship before the reconciler.
- **Plan source, rendered pages** (maintainer, 2026-09-15) over a
  hand-authored page with tool regions.
- **Per-mesocycle load targets are in scope** (maintainer, 2026-09-15): the
  source may carry a target load per mesocycle; the block page shows it
  beside the actual sum of the logged workouts dated inside that mesocycle,
  with a coverage statement. Per-row load targets are out (offered and
  declined).
- **The skill ships in the fitdocs wheel** (maintainer, 2026-09-15), a second
  packaged skill beside distribution's inbox skill, located by name. A pkm-side
  wrapper adding pkm's own closing rituals is that repository's work.
- **Rendered links are relative markdown links, never wikilinks.** Workout
  pages carry no wikilinks by design (`src/fitdocs/render/views.py:25-29`);
  the roadmap's constraint that PKM affordances degrade gracefully in vanilla
  renderers (`## Constraints`) permits wikilinks but is met most simply by
  not emitting them. The block page → planned page and block page → logged
  page links are the project's first cross-document links and follow the
  same rule; Obsidian resolves relative links, `cat` and GitHub show them.
- **Mesocycles are derived, not typed.** The source states `starts`, `ends`
  and a mesocycle length in days; mesocycle numbers and their date windows
  follow from those, the last may be short, and a row belongs to the
  mesocycle its date falls in. Moving a workout across a boundary changes its
  mesocycle, which is correct. A row dated outside the bounds is a validation
  error naming the row.
- **Rows carry a stable id.** Amendments and overrides name a row by id, so a
  workout moved two days is the same workout, its planned page keeps its
  identity, and the revision record can say "moved", not "removed and added".
- **Disambiguation lives in the source.** An override entry names a row and
  the logged workout stems that fulfil it (or marks the row skipped). The
  curating LLM edits the source it already authors and reruns the command.
  fitdocs never writes the source.
- **The reconciler is stateless.** Every run recomputes matches from the
  current source and corpus; the only sticky facts are overrides. No
  persisted match table, no migration when heuristics change.
- **Planned pages never live under `workouts/`.** Every discovery path globs
  `workouts/*.md` and filters on `type == "workout"` (`sync._discover_documents`,
  `load.engine._discover_workout_docs`, `history.documents.scan_documents`,
  `audit`), and `regen` rebuilds from the archive a planned page does not
  have. Planned pages carry their own type in their own directory, and
  "this planned workout was done" is a link between two pages, never an
  in-place promotion.
- **The activity-type match is `sport` + `modality` (+ `indoor`), nothing
  finer.** `sub_sport` is not in frontmatter (`model.py:127`, consumed at
  ingest only), so "track session" and "easy run" are the same type to the
  base case. Same-day, same-type rows are the ambiguous case the athlete
  settles; the spec says so rather than inventing a classifier.

#### Scope

- **In**: the plan-source format and its loud validation; the block page
  (bounds, goal, mesocycle length, the mesocycle-by-day table with title,
  summary and link per row, per-mesocycle target vs actual load, the revision
  record); one planned-workout page per row; a user-owned source location and
  an owned rendered location, declared, guarded and versioned like every
  other; the `fitdocs plan` command; the reconciling pass, its match rules,
  confidence labels, unplanned-workout listing and chaining after `sync`,
  `drain` and `regen`; overrides; the packaged `build-training-block` skill
  with a conformance test, and the by-name skill locator it needs.
- **Out**: forecasting fitness/form from the plan (a listed follow-on since
  Phase 6, now reachable); per-row load targets; macrocycles or any page
  spanning several blocks; a back-link key written into logged workout pages
  (candidate); auto-generating a plan from history or from a goal race;
  structured interval grammars (the prescription is prose); any change to
  channel arithmetic, selection, the calculator or the history page;
  pkm-side wrappers, schema sections and skills (the pkm repository's work);
  editing the plan source from fitdocs.

#### Constraints

- **The source is user-owned and fitdocs only reads it.** It lives outside
  every `OWNED_PATHS` prefix — a data-root directory of its own, configurable
  through `fitdocs.toml` the way `[inbox]` is — and is documented in the
  ownership contract's shared-and-user-owned section (which has no equality
  pin, `tests/test_ownership_contract.py` covers only owned paths, regions
  and keys). A malformed source is a per-block error naming the file, the
  entry and the field; a block that fails validation is left unrendered and
  its existing pages untouched, never half-rendered.
- **TOML, parsed with `tomllib`.** Four modules already do
  (`settings.py`, `athlete.py`, `quarantine.py`, `load/profile.py`) and none
  share a helper — the plan reader is a fifth `tomllib.load` idiom unless a
  task extracts one. YAML is barred: `tests/test_contract_consumers.py:261-343`
  forbids `import yaml` in any registered module, and an unquoted
  `[[wikilink]]` in a YAML value is a nested list (`contract.py:516-519`).
- **Documents are the reconciler's only corpus input.** No `.fit`, no
  network, no prompting, no clock beyond the pass's resolved `today` (used
  only to tell "upcoming" from "not logged"). Byte-identical output for an
  unchanged source and corpus.
- **Absent is `None`, never `0`.** No target → no comparison; loads not
  computed → the sum says how many pages were unscored; a row in the future
  is "upcoming", not "missed"; an override naming a stem that does not exist
  is a reported problem, never silently dropped.
- **One methodology per sum.** Reuse `fitdocs.history`'s published
  `select_methodology` / `partition_pages`; do not deep-import
  `history.documents.scan_documents` (unpublished, and its `PageRecord` has no
  sport or modality). The reconciler scans frontmatter through `docio` and
  `contract` readers of its own.
- **One contract reader per matched field.** `contract.py` has
  `document_date` but no `document_sport` / `document_modality`; the
  consumers test would *not* catch an inline `frontmatter.get("sport")`
  (`FORBIDDEN_LITERALS` is only the fence and the workout type,
  `tests/test_contract_consumers.py:246-249`). `plan-resolution` adds the
  readers and the literals to that pin in the same change.
- **Every pin moves in the change that needs it.** New owned path:
  `layout.OWNED_PATHS` / `DECLARED_DIRS` (`tests/test_layout.py:537-545, 670`),
  the ownership contract's list and version (`tests/test_ownership_contract.py:81-108`),
  a declaration golden (`tests/test_declaration_goldens.py:41-46`, or the
  new dir raises `KeyError`), `tests/test_declaration.py:160`'s derived cases,
  `tests/test_confinement.py`'s permitted set and a new `EntryPoint` with its
  own `non_vacuous` (the `history` registration at `:606-611` is the
  template; `tests/test_effort_tags_e2e.py:506` only subset-checks the
  registered ids and does not move), a new package's `__all__` surface pin in `tests/test_public_api.py`,
  `CONVERTED_MODULES` and `CONTRACT_BINDINGS` together in
  `tests/test_contract_consumers.py:83`, and the mypy `files` list in
  `pyproject.toml:60-92`. New document types declare their own vocabulary in
  their own package (the `training-history` precedent,
  `docs/ownership-contract.md:73-100`), so `MANAGED_KEYS`, `USER_KEYS`,
  `PRESERVED_REGIONS` and `DOC_VERSION` do not move.
- **Wheel packaging is silent today.** Hatchling ships non-`.py` files under
  `src/fitdocs/` by default (the built wheel carries `py.typed` with no
  include rule) and honours `.gitignore`, which ignores `data/` — no skill
  directory may be named that. No test asserts that a packaged data file is
  a wheel member (`tests/test_packaging.py` is an install smoke;
  `tests/test_forbidden_strings.py:1219-1224` checks only `__init__.py` and
  `METADATA`; distribution's artifact policy is unimplemented), so
  `build-training-block` owes its own
  wheel-member test until that policy lands.
- **Stdlib only; no personal data in the repository.** Fixtures are synthetic
  sources and pages; the athlete's real wiki is a manual check, never a
  fixture.

#### Boundary Strategy

- **Why this split**: the source format and the pages are a pure
  contract — source in, bytes out, golden-testable, no corpus — and carry the
  whole layout/declaration/contract-version ritual, so they are one spec;
  matching is heuristic, corpus-dependent and the thing a reviewer must be
  able to mutate row by row, so it is its own spec that plugs a `Resolution`
  value into the render; the skill depends on both and on distribution's
  unbuilt packaging, so it is last.
- **Shared seams to watch**: the `Resolution` value type and the "nothing
  resolved" default — `training-blocks` defines and renders it (an
  unresolved column, the way workout-docs rendered the load placeholder),
  `plan-resolution` fills it; the rendered location — `training-blocks`
  declares it and registers the `plan` entry point, `plan-resolution`
  registers a second writer into the same location with the chaining after
  `sync`/`drain`/`regen` (`cli.py:279-284, 306-309, 385-386`, after the load
  pass, since it reads load values); `contract.py` readers and
  `FORBIDDEN_LITERALS` (`plan-resolution`); distribution's `AgentSkillLocator`
  (`SKILL_NAME` constant, `skill_root()`, the name-equals-directory
  conformance test at `distribution/design.md:494-533`) widened to by-name
  before or by `build-training-block`; `history.__init__`'s append-only
  `__all__` if `plan-resolution` needs anything not yet published.

#### Existing Spec Updates

- [x] wiki-contract — a user-owned plan-source location stated in the
  shared-and-user-owned section (read-only to fitdocs, like `fitdocs.toml`);
  a new owned rendered location; two further document types
  (`training-block`, `planned-workout`) declared and versioned by the spec
  that owns them; the contract version advanced. Landed by `training-blocks`
  as Amendment 3, the way Amendments 1 and 2 were landed by `effort-tags` and
  `load-history`. Dependencies: none
- [ ] distribution — `AgentSkillLocator` and the `skill` command by name
  (`fitdocs skill <name>`, listing the packaged skills with no argument),
  the artifact policy's required members holding every packaged skill file,
  and task 4.2's conformance test generalized over the packaged set. Landed
  by `build-training-block` if distribution major 4 has not shipped first;
  otherwise consumed. Dependencies: none
- [x] workout-docs — no change: no back-link key is written (plan-resolution
  design § Decisions recorded for the roadmap). Dependencies: plan-resolution

#### Direct Implementation Candidates

- [x] product.md's "Explicitly deferred" line and the roadmap's three copies
  of the cycles/blocks deferral — lifted in this discovery change.
- [ ] pkm repository (external): a `## Plans` section in `wiki-schema.md`
  naming the two new fitdocs locations, and a thin wrapper skill that runs
  `build-training-block` and closes with pkm's log line and data-root commit.
  Not this repository's work; recorded so the install target is not
  forgotten when `training-blocks` ships.

#### Follow-on candidates (not scheduled)

- A forecast on the history page — form at the block's end given its
  planned per-mesocycle load (the Phase 6 candidate, now with a plan to read).
- A back-link from a logged workout page to the planned row it fulfilled, as
  a managed key written by the reconciler.
- Per-row load targets and a prescription grammar (intervals, paces) the
  reconciler could score against, once the prose form has been used for a
  block or two.
- Macrocycle pages spanning several blocks.

#### Specs (dependency order)

- [ ] training-blocks — **spec written 2026-09-16** (Phase 7 batch, `tasks-generated`, all approvals set; 8 requirements / 73 criteria, 4 majors / 15 executable tasks; cross-spec reviewed, two rounds, PASS). the plan-source format and validation, the block page
  and planned-workout pages, the user-owned source location and the owned
  rendered location with their declaration, guards and contract version, the
  `Resolution` seam rendered unresolved, and the `fitdocs plan` command.
  Dependencies: none
- [ ] plan-resolution — **spec written 2026-09-16** (Phase 7 batch, `tasks-generated`, all approvals set; 8 requirements / 58 criteria, 3 majors / 12 executable tasks; cross-spec reviewed, two rounds, PASS). matching logged workouts to planned rows by date and
  type with confidence labels, the split-session and same-day-ambiguity
  rules, overrides from the source, the per-mesocycle actual-load sum with
  one methodology and a coverage statement, the unplanned-workout listing,
  and chaining after `sync`, `drain` and `regen`. Dependencies:
  training-blocks
- [ ] build-training-block — **spec written 2026-09-16** (Phase 7 batch, `tasks-generated`, all approvals set; 7 requirements / 48 criteria, 3 majors / 8 executable tasks; cross-spec reviewed, two rounds, PASS). the packaged skill that builds, amends and
  disambiguates a block through `fitdocs plan`, its conformance and
  wheel-member tests, and the by-name skill locator (distribution's update)
  it is found through. Dependencies: training-blocks, plan-resolution
