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
  acquisition *(lifted in Phase 8, 2026-09-23 — `connectors` and
  `intervals-connector` pull into the inbox; pushing to platforms stays
  out)*; non-`.fit` formats
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
  Website artwork is the one narrow exception (`structure.md` rule 1).
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
- [x] distribution — **done 2026-09-19** (26/26; spec complete at `4f0ae00`;
  fitdocs 0.1.0 released from tag `v0.1.0` on `3c5281b`, release run
  35446284407). Publishable package and wiki-integration packaging:
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
- [x] activity-qa-flags — **implemented 2026-09-18 at d26b682, 14/14 tasks** —
  cadence-lock detection (HR-vs-cadence temporal correlation), cross-channel
  divergence (Efficiency Factor / aerobic decoupling), and
  threshold-staleness surfacing. Dependencies: athlete-benchmarks,
  load-channels, threshold-load, training-load (it consumes `QualityFlag`,
  payload v2 and the flags renderer — an implicit dependency the first pass
  omitted, though the spec's own tasks.md lists it). Phase 4 (the threshold
  load engine) is now complete: all four specs shipped.

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

- [x] distribution — **done 2026-09-19** (spec complete at `4f0ae00`; 0.1.0
  released from `3c5281b`). The status below is as written at the Phase 5
  discovery: the release half of this phase, already approved and
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
  encumbered-content-purge. **Both amendments landed 2026-09-18 as
  distribution Amendment 2** (Requirement 6 re-based: the artifact scan
  stays as a standing property reading the purge's out-of-repository match
  data and failing closed; one artifact set, no bundled/unencumbered
  profiles; the root `agent-log` symlink excluded and any link member a
  violation). The spec is `ready_for_implementation` again; the release
  half itself is still unstarted, which is what this checkbox tracks.

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
  *(Promoted 2026-10-12 to Phase 12's `hr-derivation`.)*

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
- [x] distribution — `AgentSkillLocator` and the `skill` command by name
  (`fitdocs skill <name>`, listing the packaged skills with no argument),
  the artifact policy's required members holding every packaged skill file,
  and task 4.2's conformance test generalized over the packaged set. Landed
  by `build-training-block`. Dependencies: none
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

- [x] training-blocks — **implemented 2026-09-16 at `68fe42e`**; **spec written 2026-09-16** (Phase 7 batch, `tasks-generated`, all approvals set; 8 requirements / 73 criteria, 4 majors / 15 executable tasks; cross-spec reviewed, two rounds, PASS). the plan-source format and validation, the block page
  and planned-workout pages, the user-owned source location and the owned
  rendered location with their declaration, guards and contract version, the
  `Resolution` seam rendered unresolved, and the `fitdocs plan` command.
  Dependencies: none
- [x] plan-resolution — **implemented 2026-09-17 at `fbba78b`**; **spec written 2026-09-16** (Phase 7 batch, `tasks-generated`, all approvals set; 8 requirements / 58 criteria, 3 majors / 12 executable tasks; cross-spec reviewed, two rounds, PASS). matching logged workouts to planned rows by date and
  type with confidence labels, the split-session and same-day-ambiguity
  rules, overrides from the source, the per-mesocycle actual-load sum with
  one methodology and a coverage statement, the unplanned-workout listing,
  and chaining after `sync`, `drain` and `regen`. Dependencies:
  training-blocks
- [x] build-training-block — **implemented 2026-09-17 at `e45f114`** (Phase 7 complete); **spec written 2026-09-16** (Phase 7 batch, `tasks-generated`, all approvals set; 7 requirements / 48 criteria, 3 majors / 8 executable tasks; cross-spec reviewed, two rounds, PASS). the packaged skill that builds, amends and
  disambiguates a block through `fitdocs plan`, its conformance and
  wheel-member tests, and the by-name skill locator (distribution's update)
  it is found through. Dependencies: training-blocks, plan-resolution

### Phase 8 — source connectors (discovery 2026-09-23)

**Goal**: stop moving `.fit` files by hand, and stop losing the data that
phone-side copies never carried. Until now the athlete put every file into
the inbox themselves. For the maintainer that meant HealthFit's exports of
Apple Health as the canonical store, plus hand exports from Garmin Connect
for rides. The Health round trip loses data. Against the device original, a
HealthFit copy of a Garmin ride lacks altitude, temperature and pedal
dynamics, and in 4 of 5 measured pairs lacks GPS. A HealthFit copy of a
Stryd run lacks every running-dynamics channel. Phase 8 adds connectors that
fetch what the athlete does not yet have into the inbox. It also teaches the
engine that a second file of an activity it already holds is the same
activity: a source of extra channels, not a duplicate page.

**Approach decision: connectors fill the inbox, and the engine reconciles.**
A connector is a thin fetcher. It lists remote activities, fetches their
bytes, delivers them atomically into the configured inbox, and records what
it fetched in a ledger under `.fitdocs/`. Everything after delivery is the
existing drain, which gains two abilities:

- **Cross-source identity.** A file whose session start, elapsed time and
  distance agree with an existing page belongs to that page.
- **Composition.** There is one page per activity. It is rendered from a
  base file, and extra files contribute only the channels the base lacks.

Because reconciliation lives in the engine, a hand-dropped file, a HealthFit
export and a connector download behave identically. The 761-document
adoption gap (queue item
`2026-09-12-adopting-a-higher-fidelity-re-export-needs-a-hand-edit`) closes
as a side effect.

Rejected:

- *Connector-aware direct attach*, where connectors match remote metadata
  against pages themselves. It is a second ingestion path beside the drain,
  hand-dropped files would still duplicate, and every future push connector
  would have to understand documents.
- *Best file wins*, where the richest file replaces the others wholesale.
  Measured, it loses the watch's HR on a ride recorded without a chest
  strap. It also adds nothing to a run: the Stryd file's value is the
  channels the HealthFit copy lacks, while only the HealthFit copy carries
  the session UUID, the session summaries and the HR laps.
- *A direct Garmin Connect login.* Garmin's developer program is
  business-only. `garth` was deprecated on 2026-03-27 after Garmin added
  TLS fingerprinting. `garminconnect` needs Python ≥3.12 and a native
  `curl_cffi` wheel, against fitdocs's ≥3.11 and its frozen dependency
  list. The discovery probe's single login drew HTTP 429. Garmin rides come
  through intervals.icu instead, which receives them over Garmin's official
  partner API.
- *A Garmin export-zip importer as the only path.* Robust, but a manual step
  per batch, so it is kept as a follow-on.

#### Decisions taken at discovery (2026-09-23)

- **Path E: five new specs and five existing-spec updates** (maintainer,
  2026-09-23):
  - `activity-identity`: which page a file belongs to, and which file is its
    base.
  - `running-dynamics`: the channels a Stryd file carries.
  - `connectors`: the framework, the pull, and the folder connector.
  - `channel-merge`: base plus extras.
  - `intervals-connector`: the activity pull only.
- **Connectors fill the inbox, and the engine reconciles** (maintainer,
  2026-09-23), over direct attach.
- **Garmin rides come via intervals.icu** (maintainer, 2026-09-23), over a
  direct Garmin login and over an export-zip-only path. The intervals.icu
  connector's pull capability moves into this phase. Its push,
  planned-workout, threshold and plan capabilities stay follow-ons. The
  viability check (2026-09-24) found intervals.icu's copy is Garmin's
  partner-API file, not the device's. Garmin strips undocumented messages
  and fields and workout steps before sending, and in 2026-03 briefly
  stripped more. Documented record fields (power, pedal dynamics, developer
  fields) survive. A device original, when one exists, therefore outranks
  the intervals.icu copy of the same ride.
- **Base plus extras** (maintainer, 2026-09-23): one page per activity,
  rendered from a base file chosen by a configurable source precedence.
  Other files of the same activity contribute only channels the base lacks,
  and the base wins every channel both carry.
- **Running dynamics are in this phase, as their own spec** (maintainer,
  2026-09-23). Without them, a Stryd file is archived and read by nothing.
- **No shipped Stryd connector; a connector plugin slot instead**
  (maintainer, 2026-09-24). Stryd has no public API. Its Terms of Use
  (revised 2021-04-06, the only terms file in Stryd's public legal folder)
  permit connecting only through Stryd's own applications or "approved
  third-party applications", and prohibit encouraging or assisting others to
  do otherwise. fitdocs is public, so it ships no Stryd connector and
  documents no Stryd endpoint. Stryd files arrive by manual download from
  Stryd's site, or through a connector plugin the athlete installs and owns
  themselves. The slot is plugin-api's second plugin kind.
- Taken without asking, consistent with the above:
  - **A folder connector** ships as the reference connector and the
    network-free test bed for the framework. It copies from a local
    directory into the inbox, keeping a ledger. Pointed at HealthFit's
    iCloud export folder, it makes HealthFit stop being a manual move.
  - **Credentials and tokens never live under the data root.** The data root
    may be a git repository (`docs/ownership-contract.md:671-693`).
  - **The pull is a one-shot command,** safe under cron or launchd, never a
    daemon (`tech.md`: no background jobs).
  - **No new runtime dependencies.** Stdlib `urllib`, `gzip` and `json` are
    enough, so the frozen dependency list stays green
    (`tests/test_determinism.py:672-712`,
    `tests/test_packaging.py:503-519`).

#### Scope

- **In**:
  - the connector protocol and its capability vocabulary;
  - the ledger;
  - credential and token storage;
  - a connect command and a pull command (names provisional: `sync` is taken
    by the inbox drain);
  - atomic delivery into the inbox;
  - the folder connector;
  - the intervals.icu connector's activity pull;
  - the connector plugin kind;
  - cross-source activity identity, with base selection and page rename;
  - base-plus-extras composition;
  - record-level developer fields and running dynamics, in ingest and on run
    pages;
  - "Garmin <model>" attribution on pages rendered from Garmin data;
  - the packaged skill's routine learning the pull.
- **Out**:
  - any push: Strava posts, intervals.icu uploads or descriptions, planned
    workouts;
  - pulling thresholds, wellness, workout libraries or plans (wellness
    promoted 2026-10-12 to Phase 12's `wellness-pull`);
  - a direct Garmin Connect connector, and a Garmin export-zip importer;
  - a shipped Stryd connector (see the decisions above);
  - a daemon, watcher or scheduler (the OS schedules the one-shot command);
  - cycling dynamics in the model (pedal dynamics, gears, training effect);
  - GPX-only activities (queue
    `2026-09-12-gpx-only-activities-in-a-garmin-export-are-unrepresentable`);
  - joining recordings that are not the same session.

#### Constraints

- **The network is used only by explicit connector commands.**
  - `sync`, `regen`, `load`, `history`, `plan` and rendering stay offline,
    apart from the existing map tiles. Connectors never import render, load
    or metrics.
  - The "only network module" statements (`cli.py:98-102`, `sync.py:41-52`,
    `tiles.py:7`) are revised to name the connector package, not deleted.
    *(Corrected at the Phase 8 spec batch, 2026-09-29: no existing test pins
    those statements. `tests/test_contract.py:1345` bans `urllib` from
    `contract.py` only, `tests/performance/test_purity.py:525` covers the
    pure performance modules only, and `tests/test_determinism.py:124, 226`
    guard sockets during parse and compute only. `connectors` adds the real
    guard: a tree-wide network allow-list in
    `tests/connectors/test_boundary.py`, task 6.1.)*
- **Every request sends an explicit User-Agent.** intervals.icu sits behind
  Cloudflare, which answers urllib's default `Python-urllib/3.x` agent with
  403 "error code: 1010" (viability check, 2026-09-24). The precedent is
  `tiles._user_agent()` (`tiles.py:252`).
- **Secrets never live under the data root and are never logged.**
  - Tokens and keys live in a per-user config location, as 0600 files
    written atomically.
  - A service with a refresh flow never has its password persisted.
  - Environment variables override the stored values for unattended runs.
  - A signed download URL is a secret too.
- **Authentication is never retried.** A 429, an MFA challenge or a lockout
  at login is reported, and the connector stops. Retries with backoff apply
  only to data calls, and are bounded. Garmin's login rate limit, hit during
  discovery, is reported to last 48–72 h and to extend on retry.
- **Terms first.**
  - fitdocs ships a connector only for a service whose terms permit the
    access it makes: a documented API with a personal key or OAuth.
  - Pages rendered from Garmin data carry "Garmin <model>" attribution
    (intervals.icu API terms §1.1; Garmin API Brand Guidelines, v6.30.2025).
  - When a Strava connector exists, nothing read from Strava ever reaches a
    page. The Strava API agreement effective 2026-06-01 bars use in
    "ingestion into a context window", and an agent-read wiki is one.
- **Identity never guesses.**
  - A match is one-to-one. Two candidates is ambiguity: it is reported and
    left unmerged, never settled by arrival order.
  - The rule is calibrated on measured pairs:
    - Stryd↔HealthFit copies agree on start time to the second and on
      distance to 0.01 m, but differ by 8–9 s in elapsed time.
    - Garmin↔HealthFit copies agree on start time to the second, on
      distance within 5 m and on elapsed time within about 1 s. Their timer
      times differ by up to 400 s, because HealthFit sets timer = elapsed.
    - 244 older HealthFit re-exports are shifted by whole hours.
    - Under a 90 s / 300 m rule, two similar 10 k runs matched falsely.
- **Arrival order never changes the page.** The page for a set of files is a
  function of the set. The base is chosen by precedence and the extras by
  rule, with the same result whichever file arrived first.
- **Absent is `None`.** Stryd writes zeros at pauses and at the first
  sample, and developer values arrive raw with no sentinel filtering.
  Neither becomes a value.
- **Personal data never enters the repository.**
  - Fixtures are synthesized FIT files with the measured shapes.
  - Connector tests run against an injected fetch seam, never the network.
  - Service specifics a public repository may not document (see the Stryd
    decision) stay out of specs, docs and tests.
- **Real use waits for identity.** Until `activity-identity` has merged, a
  pull against a real corpus that already holds phone-side copies writes
  duplicates. `connectors` may merge first, but no connector is pointed at a
  real data root before identity lands.

#### Boundary Strategy

- **Why this split.** Each part has a different kind of input and a
  different way of being tested:
  - Identity is about pages: which page a file belongs to and which file is
    its base. It changes the contract (keys, version, filenames), so it is
    one spec.
  - Composition is about samples: aligning two decoded activities and
    donating channels between them. It is pure and golden-testable, so it
    is another.
  - Running dynamics widen the model and the run page. They are useful on a
    single Stryd file with no merge at all.
  - The connector framework is network, credentials and state, with no
    knowledge of pages.
  - Each service's connector is then a small spec against a fixed protocol,
    so a service that breaks costs one module.
- **Shared seams to watch**:
  - `model.py` `Samples` (97) and `Activity` receive append-only edits,
    landing in dependency order:
    - `running-dynamics` adds channels;
    - `activity-identity` adds file identity (the `file_id` serial, time
      created, manufacturer and product; `file_id` is not read today,
      `ingest/__init__.py:56-66`);
    - `channel-merge` composes over the channel set, and must be generic
      over it or cover `running-dynamics`' channels by name.
  - The contract versions and managed keys: `DOC_VERSION` (5,
    `contract.py:174`), `CONTRACT_VERSION` ("4", `contract.py:275`) and
    `MANAGED_KEYS` (`contract.py:364`).
    - `activity-identity` records source roles on the page.
    - `channel-merge` may record which file each channel came from.
    - Each bump lands once, in merge order, and the second lander re-pins.
  - `sync.py`:
    - `find_document` (236) and `_process_file` (1126) carry identity and
      base selection, which are `activity-identity`'s;
    - the composition call is `channel-merge`'s. *(Corrected at the Phase 8
      spec batch, 2026-09-29: the page task already holds every listed file
      parsed, so `sync.py` makes no second archive read. The archive reads
      of the extras land in `load/engine.py` and `performance/engine.py`,
      which re-parse a page's last listed file rather than reading the page;
      `channel-merge` composes the listed files there through
      `compose.archive.compose_listed`.)*
    - the stem left stale for a matched page (1269-1272) is
      `activity-identity`'s to fix.
  - `cli.py` and confinement: `connectors` adds the connect and pull
    commands and registers them in `WRITING_ENTRY_POINTS`
    (`tests/test_confinement.py:815`). The ledger is owned tool state under
    `.fitdocs/`.
  - The inbox. Connectors deliver under dot-prefixed temporary names, which
    `select_candidates` already skips (`inbox.py:563`). `connectors` must
    decide what LEAVE disposition means for pulled files: today every drain
    re-reads and re-hashes them (queue
    `2026-09-17-inbox-drain-leaves-source-fit-in-inbox`).
  - `plugins.py` is hard-wired to one kind (`ENTRY_POINT_GROUP =
    "fitdocs.load_calculators"`, 207; `PluginInfo` carries calculator
    fields). The plugin-api update generalizes it by kind, against the
    protocol `connectors` publishes.
  - The packaged `fitdocs-workouts` skill's routine fence is pinned to
    exactly `sync` and `check` (`tests/test_agent_skill.py:681`). The pull
    is added there by `connectors`.
  - Garmin device names: `DeviceInfo.product_name` is `None` for every
    Garmin device, because a numeric product code is never turned into a
    name (`ingest/summary.py:372-385`). The SDK resolves it (e.g.
    `edge_1040`). Attribution needs the model name, so
    `intervals-connector` owns that change to fit-ingest.

#### Existing Spec Updates

- [ ] plugin-api — a second plugin kind. Connectors are:
  - discovered from an entry-point group and from the local plugin-file
    fallback;
  - validated against the published protocol, with per-plugin failure
    isolation;
  - listed by `fitdocs plugins` with their kind and capabilities.

  The machinery in `plugins.py` is parameterized by kind, not copied. This
  is the slot a user-installed connector lives in. Dependencies: connectors
- [x] wiki-contract — Amendment 4:
  - source roles (base and extras) on the page;
  - which file each channel came from, if `channel-merge` records it;
  - the version advances;
  - the ownership contract states that credentials never live under the data
    root and that the connector ledger is owned tool state.

  Landed by `activity-identity`, `connectors` and `channel-merge`, the way
  Amendment 3 was landed by `training-blocks`. Dependencies: none
  (activity-identity part landed) (connectors part landed) (channel-merge part landed)
- [x] fit-ingest — `file_id` identity fields (landed by
  `activity-identity`); record-level developer fields and running dynamics
  (landed by `running-dynamics`) (running-dynamics part landed); Garmin product names (landed by
  `intervals-connector`). Dependencies: none
  (activity-identity part landed) (intervals-connector part landed)
- [x] workout-docs — a running-dynamics section on run pages (landed by
  `running-dynamics`) (running-dynamics part landed); Garmin attribution (landed by
  `intervals-connector`); a note that a page's provenance is its base
  (landed by `activity-identity`); channel provenance on composed pages
  (landed by `channel-merge`). Dependencies: none
  (activity-identity part landed) (intervals-connector part landed) (channel-merge part landed)
- [x] distribution — the packaged `fitdocs-workouts` skill's routine learns
  the pull, and its pins move (`tests/test_agent_skill.py:614, 681`); Req
  8.1/8.2 (the skill also pulls) and Req 10.4 (network beyond tiles is the
  explicit connector commands) are amended. Landed by `connectors`.
  Dependencies: connectors
- [x] inbox — Req 6.1/6.6 read as the drain's guarantees; a connector's own
  delivery is removed by the next pull once identical bytes are archived.
  Landed by `connectors`. Dependencies: connectors *(added at the Phase 8
  spec batch, 2026-09-29)*
- [x] route-maps — an amendment note on Req 4.2 ("only to fetch missing
  basemap tiles") naming the connector commands. Landed by `connectors`.
  Dependencies: connectors *(added at the Phase 8 spec batch, 2026-09-29)*
- [x] training-load — a document listing several archived files is scored
  from their composition (Req 9). Landed by `channel-merge`. Dependencies:
  channel-merge *(added at the Phase 8 spec batch, 2026-09-29)*
- [x] performance-benchmarks — the same, for benchmark derivation (Req 1).
  Landed by `channel-merge`. Dependencies: channel-merge *(added at the
  Phase 8 spec batch, 2026-09-29)*

#### Direct Implementation Candidates

- [x] `product.md`'s "Explicitly deferred" line on automated acquisition,
  its first-capability line, and the roadmap's Scope copy: lifted in this
  discovery change.
- [x] Roadmap bookkeeping: Phase 7's three specs and distribution ticked
  with their merge SHAs, in this discovery change.

#### Follow-on candidates (not scheduled)

This is the connector ecosystem the phase is shaped for. The candidates are
named here so that the protocol's capability vocabulary, the ledger and the
credential store are designed for them now and built later.

- **intervals.icu, the rest of the connector.** Auth is a personal API key
  (HTTP Basic, athlete `0`); OAuth would need an approved app. The
  capabilities:
  - push an activity with post text;
  - update the name and description of an activity already there;
  - push planned workouts, including future ones, from the `training-blocks`
    plan source. Upsert by `external_id` works only for OAuth apps; an
    API-key client upserts on `uid` or keeps the event id in the ledger;
  - pull thresholds: the current sport settings, plus per-activity
    snapshots for history, into athlete benchmarks through a new benchmark
    source kind (the vocabulary is closed today, `benchmarks.py:85-95`);
  - pull workout plans and library items as a proposal the plan-source
    skill can adopt (fitdocs never writes the plan source,
    `docs/ownership-contract.md:444-449`);
  - pull wellness and fitness series. *(Wellness promoted 2026-10-12 to
    Phase 12's `wellness-pull`; intervals.icu's computed fitness series
    stay out, because fitdocs computes its own.)*
- **Strava, push only.**
  - Auth: OAuth2 with the athlete's own registered app. A Strava
    subscription is required to register one since 2026-06-01. The access
    token lasts 6 h, and the refresh token rotates and must be saved
    atomically.
  - The API has no delete, so every post is irreversible: dry-run by
    default, and confirm.
  - Garmin's auto-sync usually lands first. "Post" is therefore mostly
    *find the synced activity by time window and set its name and
    description*, with an upload only when none exists.
  - That lookup is a read. Its result may be used only to address the post,
    never rendered, and kept no longer than the terms allow.
- **Post text.** One templating seam shared by Strava and intervals.icu,
  rendering from a workout page's frontmatter and regions. A skill can have
  the curating LLM write it instead.
- **A direct Garmin Connect connector, and a Garmin export-zip importer,**
  for athletes without intervals.icu. The importer is the no-login fallback
  (the maintainer's 2026-09-12 backfill route).
- **Stryd data beyond files**: CP history and stress. These arrive through
  whatever channel Stryd's terms allow, and map onto athlete benchmarks.
- **Cycling dynamics**: pedal dynamics, power phase, gears and training
  effect. Every Edge original carries them, and the model drops them today.
- **Connector authoring as an ecosystem**: a guide and an example plugin,
  once the plugin kind has been used by at least one out-of-tree connector.

#### Specs (dependency order)

- [x] activity-identity — **implemented 2026-10-01** (21/21 tasks, validate-impl GO after remediation; rebased onto running-dynamics: DOC_VERSION 7, CONTRACT_VERSION "5", fit-ingest Amendment 4); **spec written 2026-09-29** (Phase 8 batch, `tasks-generated`, all approvals set; 9 requirements / 73 criteria, 7 majors / 21 executable tasks; cross-spec reviewed, three rounds, READY; default base precedence `original:garmin > phone_copy > original > unknown`, maintainer decision 2026-09-29). the file-identity fields from `file_id`; the
  cross-source match rule (one-to-one, calibrated on measured pairs,
  ambiguity reported and never merged); source roles on the page; base
  selection by configurable precedence (a device original outranks a
  partner-API or phone-side copy of the same session); re-render on a base
  change, with the stem recomputed, the page renamed and the old assets
  removed; the session UUID kept when the base changes; `check` findings for
  ambiguous and orphaned sources. Promoted from queue
  `2026-09-12-adopting-a-higher-fidelity-re-export-needs-a-hand-edit`.
  Dependencies: none
- [ ] running-dynamics — **spec written 2026-09-29** (Phase 8 batch, `tasks-generated`, all approvals set; 10 requirements / 57 criteria, 6 majors / 15 executable tasks; cross-spec reviewed, three rounds, READY). record-level developer fields read by field
  description (name, units, declared scale, invalid values filtered), and
  native running dynamics (step length, vertical oscillation, stance time and
  its balance, vertical ratio) as sample channels. Stryd's channels (form
  power, air power, leg spring stiffness, impact, the balance channels) are
  recognized by name. Stryd-file quirks are handled: zeros at pauses, no
  session HR summary, a wrong lap count, a session timestamp that is not the
  end. A running-dynamics section and chart on run pages. Dependencies: none
- [x] connectors — **implemented 2026-10-02** (28/28 tasks, validate-impl GO after one remediation: a pull never adopts an inbox file it did not deliver with those bytes; Req 15.4 qualified to path+bytes recognition, maintainer decision 2026-10-02; CONTRACT_VERSION "6"; `fitdocs connect`/`fitdocs pull`, folder connector); **spec written 2026-09-29** (Phase 8 batch, `tasks-generated`, all approvals set; 15 requirements / 122 criteria, 9 majors / 28 executable tasks; cross-spec reviewed, three rounds, READY). the connector protocol and its capability vocabulary
  (pull activities now; the follow-ons' kinds named and reserved, with an
  irreversible flag); the built-in registry and the published surface the
  plugin kind validates against; per-user credential and token storage
  outside the data root; the ledger under `.fitdocs/`; the HTTP seam
  (stdlib, explicit User-Agent, timeouts, no auth retries); atomic inbox
  delivery; the connect and pull commands, the pull optionally chaining the
  drain; the folder connector; the revised network statements and guards;
  the packaged skill's routine. Dependencies: none
- [x] channel-merge — **implemented 2026-10-02** (17/17 tasks; landed second after intervals-connector: DOC_VERSION 9, CONTRACT_VERSION "7", workout-docs Amendment 3, wiki-contract Amendment 4 channel part, training-load Amendment 5, performance-benchmarks Amendment 2; donor devices wired into the Garmin attribution line; validate-impl GO); **spec written 2026-09-29** (Phase 8 batch, `tasks-generated`, all approvals set; 9 requirements / 54 criteria, 6 majors / 17 executable tasks; cross-spec reviewed, three rounds, READY; also composes the listed files in the load and benchmark passes). composing one activity from a base and its extras.
  Alignment is by timestamp, with a per-stretch lag between pauses (Stryd
  and HealthFit copies drift between 0 and +1 s from one stretch to the
  next, measured). Extras donate only the channels the base lacks, and the
  base wins every shared channel. The page states which file each channel
  came from, and summaries are recomputed only where a donated channel
  feeds them. Dependencies: activity-identity, running-dynamics
- [x] intervals-connector — **implemented 2026-10-02, merged at 9d08482** (13/13 tasks; live check 1.1 run 2026-10-02 at the maintainer's request with the maintainer's key, Req 9.5 amended: TBC-5/6/8 contradicted, 422 now declined as no-file, the rest design amendments; validate-impl NO-GO -> remediated (docs model route, redaction before the byte bound) -> GO verified; DOC_VERSION 8, fit-ingest Amendment 5, workout-docs Amendment 2; donor wiring of the attribution left to channel-merge, ruling R2); **spec written 2026-09-29** (Phase 8 batch, all approvals set; 10 requirements / 57 criteria, 5 majors / 13 executable tasks; cross-spec reviewed, three rounds, READY). the intervals.icu activity pull. Auth is a
  personal API key. Listing is by date range; Strava-sourced stubs are
  skipped, and a source filter is configurable. The original file is
  downloaded (gzip) and checked for a FIT header. Garmin product names are
  resolved, and "Garmin <model>" attribution is rendered. Dependencies:
  connectors

### Phase 9 — the docs site (discovery 2026-09-28)

**Goal**: give the published tool a front door. 0.1.0 is on PyPI
(2026-09-19), but everything a newcomer reads is either the README or the
contract-grade pages under `docs/`, which are written to be exact rather
than welcoming. The maintainer wants fitdocs.ai to be a standard Python docs
site: what fitdocs is, how to install and set it up, copy-paste LLM prompts,
and the philosophy behind it (local first, private first, own your data
forever, first-class LLM compatible). The site's copy is authored and edited
by hand. A first draft of 21 pages exists outside the repo, and the
maintainer revises it while the build is implemented. The copy lands in the
repo later, as its own commit, once edited.

**Approach decision — Zensical plus a generator-agnostic build script.** A
small `scripts/` build step does the custom work:
- stage the content into a build directory, stripping each file's trailing
  iA Writer annotation block and excluding `_`-prefixed files;
- generate the nav from each page's `section` and `order` frontmatter;
- inject the home page's `template`;
- write `llms.txt` and `llms-full.txt`;
- allowlist the config keys it writes.

A pinned Zensical then builds the staged tree in strict mode, from a
Material-compatible `mkdocs.yml`. Falling back to Material for MkDocs is a
dependency swap, not a rewrite, because no logic lives in generator hooks.

Rejected:
- *Material for MkDocs 9.7 on MkDocs 1.6.* Mature, and uv/Ruff/Pydantic
  still use it, but it is in maintenance mode with end of life on 2027-05-05
  (zensical.org/upcoming-changes, checked 2026-09-28), and MkDocs 1.x has
  not released since 1.6.1 (2024-08-30). Choosing it schedules a migration.
- *MkDocs 2.0.* Pre-release (2.0.dev6, 2026-09-15). It removes the plugin
  system and Material cannot run on it.
- *Sphinx + Furo + MyST.* The most stable governance, but the wrong shape for
  a small CLI site: toctree nav, hero and admonitions all need extra work.
- *Nav from awesome-nav.* It sorts only by path, filename or title, not by
  arbitrary frontmatter keys. Zensical has no `hooks:`, so a hook is out too.

#### Decisions taken at discovery (2026-09-28)

- **Path E: one new spec (`docs-site`) plus direct fixes** (maintainer,
  2026-09-28).
- **The site is a friendly layer, and `docs/` stays canonical**
  (maintainer, 2026-09-28). The site links out to
  `https://github.com/joshua-stauffer/fitdocs/blob/main/docs/...` for full
  detail. `docs/` keeps its guards, its "documented means public" status
  (`docs/compatibility.md`) and its pinned GitHub URLs in shipped surfaces.
  The site never becomes a second contract.
- **GitHub Pages, deployed from an Actions workflow in this repo**
  (maintainer, 2026-09-28). The custom domain is set in repo Settings →
  Pages, and a CNAME file is not required for Actions publishing. DNS
  records and domain verification are maintainer-only steps, like Trusted
  Publishers for the release.
- **Brand is a brief in the spec** (maintainer, 2026-09-28): palette,
  typeface, and a hero driven by `index.md` frontmatter, with the
  power-vs-HR hero chart as its image. A later design pass can restyle
  templates without touching content.
- **Zensical, pinned exactly** (maintainer, 2026-09-28). The pin is
  `zensical==0.0.65`, alpha, releasing every few days. 0.1.0, "a dependable
  release line", is due 2026-11-05. A pin bump is a deliberate change that
  must pass the site smoke test. It never floats.
- **Content and build are separate deliverables** (maintainer,
  2026-09-28). The spec builds and tests against fixture pages. Its build
  reads content from a configurable directory, so the maintainer can preview
  the real draft from outside the repo. It never reads, commits or rewrites
  the maintainer's copy. Importing the edited copy is the maintainer's own
  step. It goes through the same staging and validation the build uses.
- **Viability (2026-09-28)**: a throwaway prototype built the actual 21-page
  draft with `zensical==0.0.65` (Python 3.14.6). The staging script was
  55 lines and used only PyYAML. It confirmed:
  - nav order from frontmatter;
  - `strict: true` exits 1 on a missing page and on a missing anchor,
    cross-page and same-page;
  - copy button, light/dark toggle, admonitions, edit links, search;
  - a `custom_dir` home template reading `page.meta.hero_*`, which needs
    `template: home.html` in the page frontmatter (injected by the script);
  - every cross-page anchor in the draft resolves (`` `[load]` `` → `#load`);
  - the build runs in about 0.3 s and the output is 1.5 MB.

  Caveats the spec must own:
  - unknown config keys, plugins and theme features are silently ignored,
    even under strict;
  - a strict failure prints a Python traceback;
  - `zensical serve` watches only the staged tree, and `serve --strict` is
    unsupported;
  - Zensical has no llms.txt support (backlog#83, open).
- Taken without asking, consistent with the above:
  - **The source directory is `website/`, not `site/`.** MkDocs and
    Zensical build into `site/` by default, and `.gitignore` has no
    `site/` entry today. Content lives in `website/content/`, templates in
    `website/overrides/`, and build output in a gitignored directory.
  - **Docs dependencies go in `[dependency-groups] docs`.** Using
    `optional-dependencies` fails `tests/test_determinism.py:715`, and the
    runtime list is frozen (`tests/test_determinism.py:672-712`,
    `tests/test_packaging.py:503-519`). The sdist stays exact by
    construction: its allowlist is derived from `only-include`
    (`tests/test_release_artifacts.py:3366-3433`).
  - **The deploy workflow runs its own forbidden-strings check** over the
    content and the built output before publishing. CI's pytest run skips
    the tracked-tree scan (the `FITDOCS_FORBIDDEN_STRINGS` variable is unset
    in `ci.yml`). Published pages are a distribution surface exactly as the
    wheel is.
  - **Workflow action refs are pinned by exact tag or SHA,** and
    `docs.yml` gets its own workflow test in the style of
    `tests/test_ci_workflow.py`. No existing test globs
    `.github/workflows/`.
  - **`Documentation` in `[project.urls]` keeps pointing at
    `docs/index.md` on GitHub.** Repointing it breaks
    `tests/test_packaging.py:302`, `tests/test_docs_guarantees.py:1203`,
    `tests/test_install_docs.py:69,202` and the `CONTRACT_DOCUMENTATION_URL`
    goldens. `Homepage = "https://fitdocs.ai"` is added instead, and no
    test pins the key set.
  - **"fitdocs.ai" is disambiguated.** Until now the name meant the
    reference application (github.com/joshua-stauffer/fitdocs.ai): README
    line 34, `product.md`, `tech.md`, this roadmap and `CLAUDE.md`. Prose
    is to say "the fitdocs.ai reference app" where it means the app (a
    direct-implementation candidate below, not done in this discovery). The
    runtime provenance strings ("inherited from fitdocs.ai",
    `src/fitdocs/metrics/sources.py`, pinned by
    `tests/metrics/test_sources.py:1155-1173`) stay. They are historically
    accurate, and re-pinning them buys nothing.

#### Scope

- **In**:
  - the `website/` source layout;
  - the build script: staging, annotation stripping, nav, home template
    injection, llms files, config allowlist, readable failures;
  - the `mkdocs.yml` template and theme overrides, including the hero and
    brand brief;
  - the `docs` dependency group;
  - a local preview command that can point at an out-of-repo content
    directory and rebuild on change;
  - the content contract (frontmatter keys, layout, link form, annotation
    block) as a published page for the maintainer;
  - fixture-based tests and a smoke test over built output;
  - the GitHub Pages deploy workflow with its forbidden-strings gate and
    workflow test;
  - `Homepage` in `[project.urls]`;
  - `CONTRIBUTING.md` build instructions;
  - the site's own documentation (content contract, build and preview,
    maintainer runbook) as one new `docs/` page linked from
    `docs/index.md` (maintainer, 2026-09-28).
- **Out**:
  - the site's copy (the maintainer's own commit);
  - existing `docs/` content and its guards;
  - API reference via mkdocstrings (a follow-on);
  - versioned docs;
  - analytics of any kind;
  - DNS and Pages settings (maintainer steps).

#### Existing Spec Updates

- [x] distribution — (done inside docs-site task 6.2, 2026-10-01) `Homepage = "https://fitdocs.ai"` in `[project.urls]`,
  and `CONTRIBUTING.md` gains the site build beside its pinned `uv sync`
  text (`tests/test_contributing_doc.py:111-118`). Carried out inside
  `docs-site`. It is listed here because the files are distribution's.
  Dependencies: docs-site

#### Direct Implementation Candidates

- [ ] `docs/install.md:23-32` and `docs/wiki-integration.md:96-99` still say
  "Until the package is published to PyPI…" and "before the package is
  published". Stale since 0.1.0 (2026-09-19), and no test pins either
  sentence.
- [ ] README line 34 and steering prose: say "the fitdocs.ai reference app"
  where the old application is meant (see the decision above). The snapshot
  `tests/fixtures/readme_pre_5_2.md` is a historical fixture and stays
  unchanged.
- [ ] `fitdocs plan` prints "Pass --methodology, set [history].methodology,
  or [load].default_calculator" (`src/fitdocs/history/series.py:314-328`,
  reached through `src/fitdocs/plans/reconcile.py:169-171`), but `plan` has
  no `--methodology` option (`src/fitdocs/cli.py:547-549`). Either make the
  hint caller-aware or give `plan` the option. Pinned by
  `tests/plans/test_placement.py:174-177` and the golden
  `tests/plans/golden/reconciled-block-problem.md:113`.
- [ ] `CHANGELOG.md` 0.1.0 lists the platform but omits the headline
  features that shipped in it: route maps, `fitdocs history`, effort tags
  and `derive-benchmarks`, training blocks and `fitdocs plan`, data-quality
  flags. Amend it so the site's changelog page can be a pure projection.
  Check the `test_changelog` pins first.

#### Follow-on candidates (not scheduled)

- API reference for the plugin surface (`fitdocs`, `fitdocs.load`) via
  mkdocstrings, which Zensical supports.
- A GitHub Release object for each tag. `v0.1.0` exists only as a tag.
- A Claude Design pass on the brand and hero, once the brief-built site is
  live.
- Rendering `docs/` on the site as a read-only "Specification" section, if
  the friendly-layer split proves too thin.

#### Specs (dependency order)

- [x] docs-site — **implemented 2026-10-01** (22/22 tasks, validate-impl GO; merged to main). **spec written 2026-09-30** (`/kiro-spec-quick --auto`, `tasks-generated`, all approvals set; 11 requirements / 74 criteria, 7 majors / 22 executable tasks; independent Step 3.5 review two rounds -> PASS; brand values and `hero_actions` shape await maintainer confirmation, queue `2026-09-30-docs-site-design-proposals-await-maintainer`). the fitdocs.ai build: `website/` layout, a
  generator-agnostic build script (staging, annotation strip, frontmatter
  nav, home template injection, llms.txt, config allowlist), a pinned
  Zensical strict build, theme overrides with a frontmatter-driven hero,
  preview against an out-of-repo content directory, fixture and smoke tests,
  and a GitHub Pages workflow gated on forbidden strings. Builds and tests
  without the maintainer's copy. Dependencies: none

### Phase 10 — the analytics index (discovery 2026-10-04)

**Goal**: let agents ask fitdocs statistical questions instead of computing
the answers themselves. Today an agent in the athlete's PKM that wants
"weekly running volume since March", "time above 170 bpm in September" or
"best 20-minute power this year" has two options:

- **Read hundreds of documents** and do the arithmetic in context.
  Frontmatter carries only distance, moving time, average HR and power,
  elevation, calories and the selected load. Everything else sits in
  rendered tables, and per-second data isn't in any document.
- **Re-implement fitdocs's parsing, composition and metric rules** over the
  archived `.fit` files.

The maintainer wants fitdocs to ship an analytics engine: a DuckDB database
written on intake and read with standard SQL.

**Approach decision — a derived DuckDB projection, reconciled after every
writing command.** One DuckDB file per data root, in a per-user cache
directory outside the data root. It holds activities, laps, strength sets,
per-second records, zone times and per-channel loads, plus derived tables:
mean-max curves, the daily load series, the benchmark timeline and training
blocks.

- **Written by one post-pass.** At the end of `sync`, drain, `pull --sync`,
  `regen` and `load`, the pass fingerprints each workout page against the
  index and updates only what moved. It reuses the composed activity and
  metrics when the run already holds them.
- **Rebuild is the same pass.** `fitdocs index --rebuild` runs it against an
  empty database.
- **Read with `fitdocs query`**, a sandboxed, read-only command with schema
  introspection, and taught to agents by a packaged skill.
- **Documents and archived `.fit` files stay the truth.** The index is a
  cache with a schema version, and deleting it costs only rebuild time. This
  reconciles the steering rule "no database … everything is re-derivable"
  (`tech.md`) with the request, and answers the earlier rejection of a load
  database for "duplicating truth"
  (`.kiro/specs/training-load/research.md:79`). Nothing reads the index
  back into a document. *(Phase 11, 2026-10-11, makes one named exception:
  dashboard chart regions and their assets are produced from the index.
  Workout, history and block documents still never read it.)*

Rejected:
- *Inline write hooks*, inserting rows at each write site from objects in
  memory. There are five sites (`sync.py:_page_task` → `_write_outputs`,
  and `load/engine.py:379`, `:526`, `:594`) owned by four specs. A hand
  edit to a page, such as an effort tag, would never reach the index until
  fitdocs itself rewrote that page. A missed site means silent drift, and a
  second, separate backfill path would still be needed.
- *Refresh on query.* Intake stays untouched, but the first query after a
  big sync pays the whole cost, and an outside DuckDB client reading the
  file sees stale data. It also isn't "written on intake".
- *Per-activity Parquet files behind DuckDB views.* Their advantage, being
  immutable and sync-friendly, disappears once the file lives outside the
  data root. They leave thousands of small files, a schema-evolution
  problem across them, and writing Parquet would still need DuckDB or
  pyarrow.
- *SQLite.* It's in the standard library, so the dependency list wouldn't
  move. But it's row-oriented, has no columnar compression and has weaker
  analytic SQL. The request names DuckDB, and per-second scans across about
  9M rows are exactly what DuckDB is built for.

#### Decisions taken at discovery (2026-10-04)

- **Path E: three new specs, plus existing-spec updates carried out inside
  them** (maintainer, 2026-10-04): `analytics-index`, `analytics-query`,
  `analytics-derived`.
- **Everything is queryable, including per-second streams** (maintainer,
  2026-10-04), over summary-only and summary-plus-precomputed. Agents can
  then answer questions nobody planned for.
- **The index lives in a per-user cache, outside the data root**
  (maintainer, 2026-10-04): a dedicated absolute env override, then
  `$XDG_CACHE_HOME/fitdocs/…`, then `~/.cache/fitdocs/…`, keyed by the
  resolved data root and refused inside it, like the credentials directory.
  The real data root is in iCloud Drive (its git repository ignores
  `.cache/` and `.fitdocs/`). A ~200 MB binary rewritten on every sync there
  would risk conflict copies and eviction. It would also fall within
  `tests/test_inbox_e2e.py:100`'s "a second sync changes nothing" scan.
  Each machine builds its own index.
- **DuckDB is a core runtime dependency** (maintainer, 2026-10-04,
  re-confirmed after viability reported the footprint below), over an
  optional `fitdocs[analytics]` extra that would make two product modes.
  This deliberately unfreezes plugin-api's Req 7.2 baseline
  (`tests/test_determinism.py:666-715`, which also forbids any
  `optional-dependencies`), `tests/test_packaging.py:503-519`,
  `tests/test_preserved_guarantees.py:93-108` and docs-site's Req 8.1 pin
  (`tests/sitebuild/test_repo_wiring.py:18-24, 64-72`). The last two were
  found during the spec batch. Plugin discovery itself must still add no
  dependency and never import `duckdb`.
- **A reconciling post-pass** (maintainer, 2026-10-04), over inline write
  hooks and refresh-on-query (see Rejected).
- **Derived tables in this phase** (maintainer, 2026-10-04): mean-max
  curves, the daily load series, the benchmark timeline and training blocks.
  All four, in `analytics-derived`.
- **Out of this phase** (maintainer, 2026-10-04):
  - an MCP or HTTP server;
  - existing passes (history, derive-benchmarks, plan, check) reading the
    index;
  - free-text columns (notes, the hand-written strength section);
  - cross-machine index sync.
- **Viability (2026-10-04)**: duckdb 1.5.6, macOS arm64, Python 3.11, in a
  scratch environment.
  - **Maintenance and fit.** MIT licensed, with permissive bundled code,
    released roughly monthly (1.5.6 on 2026-09-28). No hard dependencies;
    numpy, pandas and pyarrow are only in its `[all]` extra. It ships
    `py.typed` plus stubs, and a sample module passed `mypy --strict`.
    Importing and querying writes nothing to the current directory or HOME.
    DuckDB never connected to the network on its own, tested under a
    sandbox that kills the process on any outbound connection.
  - **Size and speed.** 9.0M records rows over 2,502 activities make a
    224 MB file. A group-by over them runs in 11–14 ms, and a rolling 60 s
    max over every row in 150–180 ms. Peak memory is about 480 MB.
  - **Insert route.** Pure Python, one JSON-columnar parameter through
    `from_json` + `unnest`, runs at about 186k rows/s. `executemany` and
    list parameters manage about 1.4k rows/s; `con.append` needs pandas;
    `read_csv` from a file-like object needs fsspec.
  - **Comments.** Table and column comments are readable from
    `duckdb_columns()` and `information_schema`, even on a locked read-only
    connection.

  Caveats the specs must own:
  - **`read_only=True` alone is no sandbox.** It still allowed reading
    `/etc/passwd`, `COPY TO`, `INSTALL httpfs`, `ATTACH 'md:'` (which
    opened a browser login) and `CALL start_ui()`. A locked configuration
    measured to refuse all of these is recorded in the `analytics-query`
    brief.
  - **Extensions can fetch themselves.** Under default settings, one SQL
    string mentioning `https://` auto-installs httpfs over plain HTTP. Every
    fitdocs connection, the writer's included, turns auto-install and
    auto-load off.
  - **Locks never wait.** One read-write process or many read-only ones.
    Every conflict fails at once, and an outside client left open blocks
    refreshes.
  - **Errors look alike.** Lock, version and missing-file errors are all
    `duckdb.IOException`, told apart only by message text.
  - **Open corruption bugs** are tied to primary-key/ART indexes and
    checkpoints (duckdb/duckdb #22823, #25928, #23046).
  - **2.0 changes the format.** DuckDB 2.0 pre-releases write a file format
    1.x refuses, while files from 1.0–1.5 are mutually readable.
  - **No statement timeout.** `connection.interrupt()` works (stops within
    1 s).
  - **`CREATE OR REPLACE` drops comments.**
  - **Footprint:** about 44 MB installed (13–21 MB wheels). No musllinux
    wheels since 1.4.0, so Alpine must compile from source, and no
    free-threaded 3.14t wheels.
- Taken without asking, consistent with the above:
  - **`duckdb>=1.2,<2`.** An agent's own 1.x client must be able to read
    the file, so a move to 2.x is a deliberate change. A version-mismatch
    error means rebuild. The floor was 1.1 at discovery. The spec batch
    raised it to 1.2 (2026-10-05): on 1.1.0–1.1.3, `INSTALL` under the
    locked configuration still creates `~/.duckdb/extensions/…` in HOME
    before refusing, while 1.2.0–1.5.6 refuse everything and create nothing
    (`analytics-query` research). Readability by older 1.x clients rests on
    the writer's storage version, not on this floor.
  - **No automatic pass ever starts a full rebuild.** When the index is
    absent, unreadable or on another schema version, a writing command
    reports that `fitdocs index` is needed and leaves it alone. A routine
    `sync` never turns into a 25-minute backfill (the full real drain took
    27:58 for 2,478 files).
  - **Index failures never cost the pipeline.** A held lock, a full disk or
    a corrupt file is reported, and never fails, rolls back or skips a
    document write. The pass reconciles against disk state, so a skipped
    refresh heals at the next successful one.
  - **No `PRIMARY KEY`, `UNIQUE` or index in the schema.** Page uniqueness
    is delete-then-insert per page in one transaction, pinned by a test.
  - **A rebuild writes a temp file and `os.replace`s it into place.**
    Measured on macOS with a reader open. Windows is verified in the design.
  - **Schema comments are the single source of column meaning.**
    `fitdocs query --schema` and the docs page's schema reference both
    project them, and a test holds the doc to the live schema.
  - **One computation, two projections.** Every derived table calls the
    owning engine's code (history's series builder, the profile reader,
    plan resolution), so the index can never disagree with the history or
    block page for the same inputs. Mean-max is the only new computation,
    and it lives in `fitdocs.metrics`.
  - **`query` and `index` join the no-network command list** (`tech.md`,
    `tests/connectors/test_e2e.py:205`). The allow-list gains a sentence:
    it binds fitdocs's connections, not an outside DuckDB client opening the
    file.

#### Scope

- **In**:
  - the per-user index location and its refusal inside the data root;
  - DuckDB as a core dependency, and the reworded dependency guards;
  - the connection policy;
  - the core schema with comments and a schema version;
  - the producer seam (per-page and corpus-level producers);
  - fingerprints and the reconciling post-pass after every writing command,
    with the in-memory handoff from sync;
  - `fitdocs index [--rebuild]` with progress;
  - failure isolation;
  - `fitdocs query` with formats, row cap, the sandbox, a statement
    timeout, schema introspection, freshness reporting and lock retry;
  - a packaged agent skill for querying;
  - `docs/analytics.md`;
  - the four derived tables;
  - steering updates (`tech.md`'s database rule, Key Libraries, Network);
  - CHANGELOG entries.
- **Out**:
  - an MCP or HTTP server, and a natural-language "ask" wrapper;
  - existing passes reading the index;
  - documents showing anything new (a mean-max section is a follow-on);
  - free-text columns;
  - write access, user tables, saved queries *(saved queries lifted in
    Phase 11, 2026-10-11: a dashboard chart directive is a saved SELECT —
    `dashboards`)*;
  - cross-machine sync;
  - charting query results *(lifted in Phase 11, 2026-10-11 — `chart-kit`,
    `dashboards`, `chart-catalog`)*;
  - new load or fitness methodologies.

#### Constraints

- Absent data is NULL, never 0 or a default (CLAUDE.md hard rule). This
  covers NaN from the JSON insert route and curve points an activity can't
  support.
- No network from any fitdocs connection. Only the index store module
  imports `duckdb`, pinned by a boundary test.
- `query` writes nothing anywhere. The index writer writes only inside the
  resolved index directory. A confinement entry covers the new location.
- Determinism means the same rows for the same inputs. File bytes aren't
  compared.
- The schema version advances by one per lander across the three specs,
  the second lander re-pinning, as `DOC_VERSION` does. `analytics-query`
  doesn't change the schema.
- Python 3.11 floor, `mypy --strict`.

#### Boundary Strategy

- **Why this split**:
  - **`analytics-index`** owns everything that writes: location, store,
    schema, the producer seam, the pass and its CLI wiring.
  - **`analytics-query`** owns everything that reads: the sandbox,
    formatting, freshness, skill and docs. It changes no schema and no
    write path.
  - **`analytics-derived`** owns four producers registered through the
    seam, and touches neither the pass nor the read side.

  Once the index lands, query and derived proceed in parallel.
- **Shared seams to watch**:
  - The **producer seam**: its shape (per-page versus corpus-level, input
    fingerprints, transaction boundaries) is the contract `analytics-derived`
    builds on. Settle it in `analytics-index`'s design, not after.
  - The **schema version** and table names. Each lander advances the
    version from `main`'s value, and the second lander re-pins.
  - **Schema comments**. `analytics-query`'s schema view and docs reference
    project them, so a derived table without comments is a defect the query
    side would surface.
  - The **stale-document rule** (`analytics-index` brief, Constraints).
    `athlete.toml` changes alter IF, TSS, TRIMP and zone times, but
    documents change only on `regen`. One stated rule governs both the core
    tables and mean-max.
  - **`cli.py` command count, the no-network command list, the confinement
    entry list and `PACKAGED_SKILLS`**: append-only, keep both on rebase.

#### Existing Spec Updates

- [x] plugin-api — Req 7.2's guard (`tests/test_determinism.py:666-715`)
  reworded. Plugin discovery adds no dependency and never imports
  `duckdb`, but the runtime baseline gains `duckdb` for the index. Carried
  out inside `analytics-index`. Dependencies: analytics-index
- [x] distribution — the exact dependency list
  (`tests/test_packaging.py:503-519`, `tests/test_preserved_guarantees.py:93-108`),
  and the install footprint and platform gap in the install docs. Carried
  out inside `analytics-index`. Dependencies: analytics-index
- [x] docs-site — Req 8.1's runtime dependency baseline amendment
  (`tests/sitebuild/test_repo_wiring.py:18-24, 64-72`) amended for
  `duckdb` (docs-site Amendment 1). Carried out inside `analytics-index`.
  Found during the spec batch. Dependencies: analytics-index
- [x] workout-docs — an append-only in-memory handoff out of
  `sync.py:_page_task` (the composed activity, metrics, identity and roles)
  for the post-pass. Nothing it renders changes. Carried out inside
  `analytics-index`. Dependencies: analytics-index
- [x] connectors — `index` and `query` join the no-network command list
  (`tech.md`, `tests/connectors/test_e2e.py:205`). Carried out inside
  whichever spec adds each command: `analytics-index` takes connectors
  Amendment 1 (`index`), and `analytics-query` records Amendment 2 (`query`)
  on its feature branch. (Both parts landed; Amendment 2 with the
  analytics-query merge, 2026-10-08.)
  Dependencies: analytics-index, analytics-query
- [x] fit-ingest — Requirement 19 and Amendment 6 publish best-effort
  computation at library level and classify its duration and step choices
  under criterion 15.8, outside criterion 15.6's enumeration. Carried out
  inside `analytics-derived`. Found during the spec batch. Dependencies:
  analytics-derived

`analytics-derived` also extracts behaviour-preserving seams from the
history and plans engines, and appends them to the `fitdocs.history` and
`fitdocs.plans` public surfaces. This needs no load-history or
plan-resolution amendment, which is the same treatment plan-resolution's
earlier `_HISTORY_SURFACE` append received. The engines' rendered output
and existing tests stay unchanged.

#### Direct Implementation Candidates

None. Every piece of the work has a spec home.

#### Follow-on candidates (not scheduled)

- A stdio MCP server wrapping `analytics-query`'s sandboxed connection
  factory, with query and schema tools.
- A mean-max section in the workout documents, reusing the
  `fitdocs.metrics` function.
- Existing passes (history, plan, derive-benchmarks) reading the index once
  it has proven itself, if their scans become a cost.
- A free first build. When every page of a brand-new data root's first
  sync is in the in-memory hand-over, the index could be built without a
  separate `fitdocs index`. This was rejected for `analytics-index`, which
  keeps "no automatic pass ever starts a full build" (its research,
  Decision 6).
- Free-text columns (notes, the strength section) with DuckDB's full-text
  search, which is a downloadable extension and so needs a network-policy
  decision.
- Moving to DuckDB 2.x, once 2.0 is stable and clients have caught up.

#### Specs (dependency order)

- [x] analytics-index — **implemented and verified 2026-10-07; all31 executable tasks complete, feature GO. Plain/UTC/CI each9388 passed with two expected skips; floor62, artifacts/installed-wheel smoke and authorized real-data measurements approved.** **spec written 2026-10-05** (Phase 10 batch, wave 1, `implementation-complete`, all approvals set; 14 requirements / 94 criteria, 8 majors / 31 executable tasks, 8.5 explicitly delegated by the maintainer; independent Step 3.5 review, two rounds; cross-spec reviewed, two rounds, READY; DuckDB floor raised to `>=1.2,<2`; carries plugin-api, distribution, workout-docs, docs-site and connectors Amendment 1). Implement first. The derived DuckDB index:
  - per-user location outside the data root;
  - core dependency with the reworded guards and the connection policy;
  - core schema with comments and a schema version;
  - the producer seam;
  - the fingerprint-reconciling post-pass after every writing command, with
    the in-memory handoff;
  - `fitdocs index [--rebuild]`;
  - failure isolation;
  - steering updates.
  Dependencies: none
- [x] analytics-query — **implemented and verified 2026-10-08** (21/21 leaf tasks accepted; task 2.3 resolved by a maintainer-approved measured test-contract revision of the spill fixture; duckdb 1.2.0 floor 233/233 under sandbox-exec; feature validation GO after one remediation round: clean Ctrl-C exit 130, trailing newline, schema advice; full suite 10135 passed/8 skipped plus plain/UTC/CI and forbidden-strings modes). **Spec written 2026-10-05** (Phase 10 batch, wave 2, `tasks-generated`, all approvals set; 12 requirements / 79 criteria, 8 majors / 21 executable tasks, 8.3 maintainer-only; independent Step 3.5 review, two rounds; cross-spec reviewed, two rounds, READY; connectors Amendment 2). Analytics-index prerequisite fully verified on 2026-10-07 and available on main. Parallel with analytics-derived, and whichever of the two lands second does the docs schema block and the derived skill examples. `fitdocs query`:
  - sandboxed read-only connection, statement timeout, formats, row cap;
  - schema introspection and freshness reporting, lock retry;
  - the packaged agent skill;
  - `docs/analytics.md` with a live-schema pin.
  Dependencies: analytics-index
- [x] analytics-derived — **implemented and verified 2026-10-07** (20/20 leaf tasks accepted; plain/UTC/CI and final canonical 9629 passed/2 optional skips; artifact/liveness gates and review of all 64 criteria passed; first-lander publication handoff to analytics-query task 7.3). **Spec written 2026-10-05** (Phase 10 batch, wave 2, `tasks-generated`, all approvals set; 10 requirements / 64 criteria, 6 majors / 20 executable tasks, 6.4 maintainer-only; independent Step 3.5 review, two rounds; cross-spec reviewed, two rounds, READY; SCHEMA_VERSION main+1 at landing; fit-ingest amendment, next free number). Analytics-index prerequisite fully verified on 2026-10-07 and available on main. Parallel with analytics-query. Four producers through the seam:
  - mean-max curves (new `fitdocs.metrics` function);
  - daily load series (history's builder);
  - benchmark timeline (`athlete.toml`);
  - training blocks with planned-versus-logged resolution (plan
    resolution).
  Dependencies: analytics-index

### Phase 11 — analytics dashboards (discovery 2026-10-11)

**Goal**: turn what the athlete learns from the analytics index into
charts on pages in their wiki. Phase 10 made the training corpus answerable
in SQL. Its first real use (2026-10-11, 2,562 workouts) asked "how do
cadence, HR and pace relate?" and got answers in one or two seconds per
query. But those answers live in a chat transcript:

- nothing puts a chart of them on a wiki page next to the athlete's own
  reading of it;
- nothing keeps a "last 12 weeks" chart current as workouts arrive;
- nothing holds a point-in-time finding still once the data under it moves.

The maintainer wants a fitdocs-owned directory of dashboard pages, written
by the athlete's LLM assistant against an API fitdocs ships. Charts come in
two kinds:

- **frozen**, which always shows the same thing;
- **relative**, which re-queries the most recent data on a cadence.

There should be a broad set of chart kinds, markdown-native and as
lightweight as possible. **fitdocs builds the charts. The athlete, with or
without an LLM, owns all the prose that gives them context.**

**Approach decision — hidden chart directives in athlete-owned pages,
rendered by a generic SVG chart kit.**

- **Pages.** A dashboard is a markdown page under `dashboards/` in the data
  root. The athlete or their agent writes everything on it: frontmatter,
  headings, prose.
- **Directives.** Each chart is declared by a hidden, multi-line HTML
  comment, `<!-- fitdocs:chart … -->`, wherever the prose wants it. Its YAML
  body gives an id, kind, mode, SQL, encodings and a title.
- **Regions.** Directly below each directive, fitdocs owns one region
  (`<!-- fitdocs:begin:chart:<id> -->` … `end`). It holds:
  - a standard image link to an SVG in `dashboards/assets/`;
  - a caption;
  - optionally, the plotted rows as a small markdown table.

  fitdocs rewrites only the bytes between its markers, the
  `load/docedit.py` polarity. It never touches the prose or the directive.
- **Relative charts** re-run their SQL in `analytics-query`'s locked,
  read-only sandbox, with `$today` bound to the run's local date. They do
  this after every successful index refresh (sync, drain, `pull --sync`,
  regen, load) and on demand.
- **Frozen charts are snapshots.**
  - The SQL runs once, and fitdocs stores the result rows with the chart.
  - Every later render draws from the stored rows and never re-queries. So a
    frozen chart survives index deletion, a schema bump, and a machine with
    no index.
- **The chart kit.**
  - **Shared layer:** scales, nice ticks, unit-aware labels, axes, legend and
    a light/dark theme.
  - **Kind registry:** a registry of named kinds over that layer takes typed
    columns plus named encodings and writes byte-deterministic,
    dependency-free SVG.
  - **Markdown kinds:** two kinds, `stat` and `table`, are plain markdown.

Rejected:
- *Mermaid code blocks.* Text-only and diffable, but Mermaid can only draw
  bar, line, pie and quadrant charts: no scatter, heatmap, histogram or
  dual axis. Rendering also varies by viewer. Phase 1 rejected it for the
  hero chart on the same grounds.
- *Inline `<svg>` in the page.* GitHub's sanitizer strips it, and kilobytes
  of markup bury the prose for anyone reading the plain text.
- *Pinned-range frozen charts* (absolute dates, re-queried on every
  refresh). The picture changes silently when the data moves (a late
  import, a threshold or methodology change), and a schema bump can break
  it. That is not "always shows the same thing".
- *A separate spec file per dashboard* (`dashboards/<name>.toml` generating
  the page, with prose in user regions). Two files per dashboard, and prose
  can only go in the slots fitdocs leaves.
- *A CLI-only API* (`fitdocs dashboard add-chart …`). Worst for hand edits
  and for an agent iterating on SQL.
- *Visible fenced directives* (```` ```fitdocs-chart ````). Every chart
  would sit under 10–15 lines of YAML and SQL in reading view.
- *A composable chart grammar* (Vega-Lite-style marks × encodings ×
  transforms). Far larger to build and test, and it gives an agent many
  more ways to write a valid but wrong spec.
- *A plotting dependency* (matplotlib or similar). It's heavy, and it emits
  large SVGs with text drawn as paths and random ids, which are hard to
  theme or pin with goldens. `tech.md` keeps matplotlib out unless a spec
  proves the need.

#### Decisions taken at discovery (2026-10-11)

- **Path E: three new specs, plus existing-spec updates carried out inside
  them** (maintainer, 2026-10-11): `chart-kit`, `dashboards`,
  `chart-catalog`, in the shape chart-kit → (dashboards ∥ chart-catalog).
  This mirrors Phase 10's index → (query ∥ derived).
- **SVG files plus standard image links** (maintainer, 2026-10-11), as
  workout charts already do. This was chosen over Mermaid and inline SVG.
- **Frozen means snapshot** (maintainer, 2026-10-11), over a pinned date
  range.
- **The chart definition is an inline directive in the page** (maintainer,
  2026-10-11), over a separate spec file or a CLI-only API.
- **The directive is a hidden HTML comment** (maintainer, 2026-10-11), over
  a visible fenced block.
- **Relative charts refresh after every successful index refresh, plus on
  demand** (maintainer, 2026-10-11), over an explicit-only or regen-only
  cadence.
- **Named kinds over a shared layer** (maintainer, 2026-10-11), over a
  composable grammar or a plotting dependency. The four existing renderers
  (hero, calendar, zone strip, map) are left alone.
- **The whole catalogue ships in this phase** (maintainer, 2026-10-11):
  - `chart-kit` holds the shared layer and the core kinds:
    - SVG: `line`, `area`, `bar`, `hbar`, `scatter`, `histogram`;
    - markdown: `stat`, `table`.
  - `chart-catalog` holds `calendar-heatmap`, `heatmap`, `dual-axis`,
    `band`, `box`, `mean-max`, `small-multiples` and `stacked-100`.
  - Pie and donut are excluded on purpose.
- **Consequence: the Phase 10 rule "the index is never read back into a
  document" gets one named exception.** Dashboard chart regions and their
  assets are the only document content produced from the index. Workout,
  history and block documents still never read it. The rule's copies move
  with `dashboards`:
  - `tech.md:12-17`;
  - `docs/ownership-contract.md:10-11` and `:191-193`;
  - analytics-index Req 5.6;
  - the text pins in `tests/index/test_contract_docs.py:56`,
    `tests/identity/test_contract_docs.py:183` and
    `tests/connectors/test_network_statements.py:640-644`.
  Until it lands, `tech.md` keeps the Phase 10 wording, because those tests
  pin it.
- **Viability (2026-10-11)**: probes are in the discovery session's scratch
  directory; no showstopper. Every item below is a constraint the specs
  own.
  - **Theme through `<img>`.**
    - An SVG drawn by an element answers `prefers-color-scheme` from that
      element's used `color-scheme`. That is Chromium commit 2e97c36
      (crbug 1345247) and Media Queries 5.
    - In Chromium and Firefox it follows the embedding page's theme:
      - **Obsidian desktop**: `.theme-dark { color-scheme: dark }` in the
        1.14.4 bundle. It follows Obsidian's theme, not the OS, on
        installers with Chromium ≥ 110.
      - **GitHub**: `?sanitize=true` keeps `<style>` and media queries, and
        Primer sets `color-scheme` from the site theme.
      - **The docs site**: Zensical maps `default`/`slate` to light/dark.
    - On WebKit (Obsidian iOS, Safari) an SVG in `<img>` ignores the query
      (bug 199134) or follows only the system appearance. WebKit never
      honours the page's `color-scheme` (bug 316640).
    - Hence chart-kit's rule:
      - a transparent background;
      - base inks that reach at least 3:1 on `#ffffff`, `#1e1e1e`,
        `#0d1117` and `#1e2129`;
      - an embedded `<style>` that raises small text to at least 4.5:1
        where the query is honoured.
    - `light-dark()`, `currentColor` and `<picture>` don't help.
    - **Today's workout charts are unreadable in dark mode.** Their text,
      `#333333`, is 1.32:1 on `#1e1e1e` (see Follow-on).
  - **Hidden directive.**
    - **Where it hides.** The example directive, with blank lines, a
      `sql: |` block, `--` comments, `<`, `<>`, `>=` and `$today`, stays
      hidden in every renderer tested:
      - Python-Markdown with Zensical's default extensions;
      - cmark-gfm;
      - markdown-it;
      - GitHub's `/markdown` API;
      - Obsidian Reading view (its bundled remark tokenizer).
    - **Live Preview.** Obsidian Live Preview shows it as dimmed source.
    - **What breaks it.** A body containing `-->` or `--!>`, or starting
      with `>` or `->`, ends the comment early and leaks the SQL. Four
      spaces of indent turn it into a visible code block.
  - **`$today` under the sandbox** (duckdb 1.2.0 and 1.5.6, locked
    configuration replicated):
    - **What works.** Binding works, and `extract_statements` still
      classifies the statement as SELECT. `Statement.named_parameters`
      reports `today` only when it is used outside literals and comments.
    - **Binding when unused is an error.** Binding `today` when the SQL
      doesn't use it fails ("excess parameters").
    - **Date arithmetic.** `$today - INTERVAL 12 WEEK` is a TIMESTAMP, and
      `$today - 84` is a DATE.
    - **Issue.** The facade's `IndexConnection.execute` uses
      `.sql(sql, params=…)`. With params, that materialises the whole result
      before `fetchmany` caps it: 60M rows reached 7 GB on 1.5.6, and a 2 s
      interrupt landed at 21 s. `connection.execute(sql, params)` +
      `fetchmany` stays flat. The query sandbox has never run a
      parameterised statement, so nothing shipped is affected yet.
    - **Type names differ by version.** `cursor.description` spells them
      differently on each (1.2.0 `Date`/`NUMBER`, 1.5.6
      `DATE`/`DOUBLE`/`BIGINT`).
  - **pkm.** There's no collision: pkm defines no `dashboards/` and no
    `type: dashboard`. But pkm's `wiki-schema.md` registers only
    `workouts/`, `fit-archive/`, `.cache/` and `.fitdocs/`.
    - `history/` was never registered.
    - `blocks/` is tracked in Phase 7 › Direct Implementation Candidates.
    - pkm's rule "never add a region marker to a document that lacks one"
      conflicts with dashboards' inverse ownership shape.
  - **YAML.** PyYAML `safe_load` silently changes values:
    - `mode: no` becomes `False`;
    - `id: 2026-10-11` becomes a date, and `012` becomes 10;
    - with duplicate keys, the last one wins;
    - a plain `sql: SELECT 1 # x` loses its tail;
    - a folded `sql: >` merges a `--` comment line into the next line.
  - **Markers.** `docmerge._MARKER_RE` isn't fence-aware.
  - **Asset names.** `assets/<page>-<id>.svg` can collide across pages.
- Taken without asking, consistent with the above:
  - **The run date never enters rendered bytes.** Captions state the window
    as written and the latest date in the result, never the run date. A day
    with no new data rewrites nothing in an iCloud- and git-backed wiki, and
    "a second sync changes nothing" holds.
  - **No pass ever builds the index** (the Phase 10 rule is unchanged).
    When the refresh didn't succeed, relative charts are left as they were
    and the report says why.
  - **Dashboard failures never cost the pipeline.** The pass never fails a
    command and never changes its exit code. One chart's failure never
    blocks another chart or page.
  - **Snapshots are the one tool-written artifact in the data root that
    can't be re-derived.** They are never deleted automatically, and they
    survive `regen`, `index --rebuild` and chart-kit upgrades.
  - **SQL runs only through `analytics-query`'s sandbox**: SELECT only, the
    same settings and timeout. There is no second SQL surface.
  - **Units ride on column-name suffixes** (`index/schema.py:77-97`). An
    alias keeps its suffix (`AS distance_km`) to get unit-aware axes.
  - **No network.** `dashboard` joins the no-network command list, and
    there is no map kind in this phase.
  - **One clock read.** `$today` comes from `cli._today()`. Neither
    `chart-kit` nor `dashboards` reads a clock.
  - **One new command**, `fitdocs dashboard`, taking the command count from
    13 to 14. Its forms (check, refresh, freeze, kinds) are a design
    decision.
  - **A fourth packaged skill**, `fitdocs-dashboards`.

#### Scope

- **In**:
  - the generic chart kit (data contract, shared layer, theme, registry,
    validation, mark bounds) with the core kinds;
  - the extended kinds;
  - the `dashboards/` owned location, with its declaration and contract
    entry;
  - the directive and region grammar;
  - sandboxed execution with `$today` and typed columns;
  - frozen snapshots and their lifecycle;
  - the chained pass and `fitdocs dashboard`;
  - per-chart failure isolation;
  - idempotence;
  - the packaged skill and `docs/dashboards.md`;
  - the existing-spec updates below;
  - steering updates (`tech.md`'s database and network paragraphs,
    `structure.md`'s import direction);
  - CHANGELOG entries.
- **Out**:
  - charts in workout, history or block documents;
  - moving the four existing renderers onto the kit (follow-on);
  - fitdocs writing prose or calling an LLM;
  - interactive or JavaScript charts, HTML dashboards;
  - a scheduler or daemon;
  - write SQL, user tables, persisted views;
  - map, pie and donut kinds;
  - an auto-generated index page of dashboards;
  - cross-machine coordination of relative renders.

#### Constraints

- **Absent data is never drawn as zero** (CLAUDE.md hard rule):
  - NULL is a gap, a missing bar, or an em dash;
  - an empty result renders an explicit no-data state;
  - a heatmap cell with no value differs visibly from one whose value is
    zero.
- **Stdlib only.** Neither `chart-kit` nor `chart-catalog` adds a runtime
  dependency. `dashboards` adds none beyond the existing `duckdb` and
  `pyyaml`.
- **Byte-deterministic** for the same inputs (relative charts: for the same
  rows). Pinned by goldens.
- **Write confinement.** Writes go only to `dashboards/` and
  `dashboards/assets/`. Symlinks and foreign occupants are refused the way
  history and plans refuse them, and writes are atomic.
- **Import direction.**
  - `chart-kit` and `chart-catalog` import nothing from `index`, `query`,
    `dashboards`, `model` or `ingest`.
  - `dashboards` reaches DuckDB only through `fitdocs.query`.
  - Only `fitdocs.index.store` imports `duckdb`.
- Python 3.11 floor, `mypy --strict`. Every new assertion owes a named
  mutation it dies on.

#### Boundary Strategy

- **Why this split**:
  - **`chart-kit`** owns how any chart looks: data contract, layout, theme,
    units, the registry and encoding validation. It knows nothing about SQL
    or pages.
  - **`dashboards`** owns pages, directives, regions, data binding,
    snapshots, refresh and the agent surface. It draws only through the
    registry.
  - **`chart-catalog`** only appends kinds.

  Once chart-kit lands, dashboards and chart-catalog proceed in parallel.
- **Shared seams to watch**:
  - The **data contract and encoding schema**. This is what `dashboards`
    builds from query results and what `chart-catalog` renders. Settle it
    in chart-kit's design, as Phase 10 settled the producer seam in
    analytics-index's.
  - The **unit vocabulary**. `index/schema.py`'s suffixes name units, and
    chart-kit formats them. `dashboards` maps one to the other. One table
    of unit tokens, not two drifting copies.
  - The **kind registry**: append-only. Whichever of `dashboards` and
    `chart-catalog` lands second re-pins any registered-kind count and the
    kinds block in `docs/dashboards.md`, which is pinned live against the
    registry. The skill points at `fitdocs dashboard`'s kinds listing
    rather than copying the catalogue.
  - The **theme**. One mechanism, from chart-kit, for every kind.
  - **`cli.py` command count, the no-network command list,
    `WRITING_ENTRY_POINTS`, `OWNED_PATHS`/`DECLARED_DIRS` and
    `PACKAGED_SKILLS`**: append-only. Keep both sides on rebase.

#### Existing Spec Updates

- [x] analytics-index — Req 5.6 gains the named dashboards exception, and
  the copies of the rule move in the same change (see Decisions).
  `cli._run_index_pass` returns its `IndexReport` outcome instead of
  discarding it (`cli.py:503-519`). The facade gains
  `IndexConnection.execute_named(sql, Mapping)`, which streams through
  `connection.execute` + `fetchmany`. Positional `IndexConnection.execute`
  is left as it is, because the index writer binds `$1` through it in seven
  places. *(Corrected 2026-10-12 by the Phase 11 spec batch: this line used
  to say the `execute` params path itself moves to a `Mapping`, which would
  have broken every index write.)* This is analytics-index Amendment 1,
  carried out inside `dashboards`. Dependencies: dashboards
- [ ] analytics-index (unnumbered, value-preserving) —
  `index.schema.UNIT_SUFFIXES` becomes a projection of the new single unit
  table `fitdocs.units`, with its value unchanged. A dated note goes into
  analytics-index's `design.md`. `units` joins the `index` bullet in
  `structure.md`, and its text pin moves. Carried out inside `chart-kit`.
  Dependencies: chart-kit
- [x] analytics-query — result columns keep their type names (dropped at
  `statement.py:200-205`). `fitdocs.dashboards` joins the importer
  allow-list (`tests/query/test_boundary.py:15`). The out-of-scope line on
  saved queries and charting (`requirements.md:85-88`) is marked superseded.
  This is analytics-query Amendment 1, carried out inside `dashboards`.
  Dependencies: dashboards
- [x] wiki-contract — a new owned location and declared directory
  (`dashboards/`, `dashboards/assets/`), the inverse ownership shape
  (fitdocs-owned chart regions inside an athlete-owned page) as a new
  category in `docs/ownership-contract.md`, the page type, and
  `CONTRACT_VERSION` `"9"` → `"10"`. This is wiki-contract Amendment 5,
  carried out inside `dashboards`. Dependencies: dashboards
- [x] connectors — `dashboard` joins the no-network command list (`tech.md`,
  `tests/connectors/test_e2e.py:205`). This is connectors Amendment 3,
  carried out inside `dashboards`. Dependencies: dashboards

#### Direct Implementation Candidates

- [ ] pkm repository (external): register `dashboards/` and
  `dashboards/assets/` in `wiki-schema.md`. That means:
  - an owned-paths row;
  - a frontmatter exemption, and a reconciliation with "never add a region
    marker to a document that lacks one";
  - an area line in `index.md`;
  - a `.gitignore` decision. GitHub shows charts only if
    `dashboards/assets/` is committed, while `workouts/assets/` is ignored
    today.

  While there, register the missing `history/`, which has been unregistered
  since Phase 6. This is not this repository's work; it's recorded so the
  install target isn't forgotten when `dashboards` ships.

#### Follow-on candidates (not scheduled)

- Moving the hero, calendar, zone-strip and map renderers onto chart-kit's
  shared layer and theme. Workout and history charts are unreadable in dark
  mode today (`#333333` text is 1.32:1 on Obsidian's `#1e1e1e`; viability
  2026-10-11).
- Chart directives outside `dashboards/`: in a block page's `notes` region,
  for example, or in a race report.
- An auto-generated index page listing every dashboard.
- A stdio MCP tool that renders a chart from a directive (pairs with
  Phase 10's MCP follow-on).
- A mean-max section in workout documents (Phase 10's follow-on) drawn with
  the `mean-max` kind.

#### Specs (dependency order)

- [x] chart-kit — **implemented and verified 2026-10-12** (28/28 leaf tasks accepted, 7.2* maintainer-only visual check open; ~20 controller rulings recorded in the spec's tasks.md Implementation Notes and design.md amended to match — dashboards and chart-catalog read those first; hbar 20-bar size budget raised 8,000 → 13,400 by ruling; validate-impl GO, full suite 11459 passed/44 skipped, CI green; 9 follow-ups queued as `2026-10-12-chart-kit-*`). **Brief written 2026-10-11; spec written 2026-10-12**
  (Phase 11 batch, wave 1, `tasks-generated`, all approvals set; 18
  requirements / 105 criteria, 7 majors / 28 executable tasks plus the
  optional maintainer-only visual check 7.2*; independent Step 3.5 review,
  two rounds; cross-spec reviewed, two rounds, READY; owns the single unit
  table `fitdocs.units` and the facade `fitdocs.render.charts.kit`). A
  generic, stdlib-only SVG chart kit:
  - the typed data contract;
  - scales (linear, log, date, category), nice ticks and unit-aware labels;
  - axes, legend and layout;
  - the light/dark theme mechanism from viability;
  - the declared kind registry with encoding schemas and structured
    validation;
  - mark bounds;
  - the core kinds `line`, `area`, `bar`, `hbar`, `scatter` and
    `histogram`, plus the markdown kinds `stat` and `table`.

  Implement first. Dependencies: none
- [x] dashboards — **implemented and verified 2026-10-13** (28/28 leaf tasks accepted; landed second of the Phase 11 pair, 7.3 found the kinds block already current; CONTRACT_VERSION "10"; carried analytics-index Amendment 1, analytics-query Amendment 1, wiki-contract Amendment 5, connectors Amendment 3; validate-impl GO, design.md amended to the landed engine and requirements 12.2 + ten more amended to match the code (maintainer ruling on 12.2: image written before the page, no code change); full suite 13499 passed/44 skipped, CI green; 28 follow-ups queued 2026-10-13). **Brief written 2026-10-11; spec written 2026-10-12**
  (Phase 11 batch, wave 2, `tasks-generated`, all approvals set; 20
  requirements / 129 criteria, 8 majors / 28 executable tasks; independent
  Step 3.5 review: RETURN_TO_DESIGN on the params path, which became
  `IndexConnection.execute_named`, then NEEDS_FIXES, applied; cross-spec
  reviewed, two rounds, READY; carries analytics-index Amendment 1,
  analytics-query Amendment 1, wiki-contract Amendment 5 and connectors
  Amendment 3). The `dashboards/` owned location and its declaration:
  - hidden chart directives with fitdocs-owned regions;
  - sandboxed execution with `$today`;
  - frozen snapshots;
  - the pass chained after a successful index refresh;
  - `fitdocs dashboard`;
  - per-chart failure isolation;
  - the `fitdocs-dashboards` skill and `docs/dashboards.md`;
  - analytics-index, analytics-query, wiki-contract and connectors updates.

  Parallel with chart-catalog. Dependencies: chart-kit
- [x] chart-catalog — **implemented and verified 2026-10-12** (21/21 leaf tasks accepted, 4.3* maintainer-only visual check open; landed first of the Phase 11 pair, so `dashboards`' task 7.3 regenerates the docs/dashboards.md kinds block; upstream chart-kit fix `frame.axis(title_room=)` at 431a5a7; budgets for calendar-heatmap, box and stacked-100 raised by controller ruling; design.md amended to the implementation rulings; validate-impl GO, full suite 12249 passed/8 skipped, CI green; follow-ups queued 2026-10-12). **Brief written 2026-10-11; spec written 2026-10-12**
  (Phase 11 batch, wave 2, `tasks-generated`, all approvals set; 13
  requirements / 92 criteria, 4 majors / 17 executable tasks plus the
  optional maintainer-only visual check 4.3*; independent Step 3.5 review,
  two rounds, PASS; cross-spec reviewed, two rounds, READY; grid kinds
  carry magnitude by cell area with colour second, and signed grid values
  are refused). Eight more kinds through chart-kit's registry:
  `calendar-heatmap`, `heatmap`, `dual-axis`, `band`, `box`, `mean-max`,
  `small-multiples` and `stacked-100`, plus any appended shared-layer
  extension a kind proves it needs. Parallel with dashboards.
  Dependencies: chart-kit

### Phase 12 — wellness and recovery (discovery 2026-10-12)

**Goal**: let fitdocs see the days between workouts. The maintainer wants
the athlete's full wellness data — resting HR, HRV, sleep, weight, SpO2,
VO2max, steps, stress — inside fitdocs. The aim is to understand how
training and recovery are going, and how life outside workouts affects
fitness. It should also work for athletes on Garmin, COROS and other
platforms, not only for the maintainer's Apple Watch.

At the very least the data should derive max and resting HR. Load already
consumes both (TRIMP's heart-rate reserve and the threshold HR channel),
but today they exist only as hand-typed values that nobody keeps current.

**Approach decision — wellness files fill the inbox; the engine archives
them and normalizes them into one daily series.**

- **Delivery** follows Phase 8's rule, extended from activities to wellness:
  connectors fill the inbox, and the engine reconciles (maintainer,
  2026-10-12).
  - A wellness file dropped by hand and one a connector delivers are handled
    identically.
  - The intervals.icu connector delivers wellness now. A future Garmin or
    HealthFit connector would do the same.
- **The drain**:
  1. recognizes a wellness file through a format registry;
  2. archives it, content-hashed, in a new `wellness-archive/` beside
     `fit-archive/`;
  3. parses it into per-day, per-field records tagged with their source;
  4. merges the sources by a per-field precedence into one normalized daily
     series, written as fitdocs-owned yearly files.
- **Consumers.** Every consumer reads that series:
  - the analytics index;
  - a new recovery page;
  - a morning-of block on each workout page;
  - a derivation pass that writes resting and max HR into the benchmark
    timeline.
- `regen` rebuilds the series from the archive.

Rejected:

- *Archive only, re-parsed on every pass.* One truth, but an Apple Health
  export is gigabytes of XML: about 10 s per GB, on every pass. It would push
  toward a parse cache that `.cache/` (re-fetchable data only) cannot hold.
- *Index-backed.* Wellness would live only in the DuckDB index. Workout pages
  carrying a morning-of block would then depend on a per-machine cache, and
  a fresh machine would render different pages. That breaks determinism and
  the Phase 10 rule that documents never read the index.
- *Direct per-platform connectors now.*
  - Garmin's Health API is business-only, and new applications are paused in
    2026.
  - Suunto offers no personal API.
  - The Fitbit Web API shuts down on 2026-10-30.
  - Oura's API agreement (effective 2026-06-08) bars storing or caching user
    data and supplying it to AI. WHOOP's terms (effective 2026-10-06) bar
    "permanent copies". A public tool that writes markdown for an LLM-run
    wiki cannot honour either. That is Stryd's reason (Phase 8), applied
    again.
  - intervals.icu already relays wellness from Garmin, COROS, Polar,
    Suunto, Oura, WHOOP, Zepp and Huawei, though not from Fitbit or Withings.
    The Garmin export files cover Garmin history without any login.
- *A readiness verdict or score.* The recovery page and the morning-of block
  are descriptive: each signal against the athlete's own baseline and normal
  range. They give no status label and no advice. load-history's "no
  readiness verdict" stance (Req 2.11) carries over.
- *Archiving the whole Apple Health export.* The maintainer chose this first,
  then reversed it after viability (see below).

#### Decisions taken at discovery (2026-10-12)

- **Path E: six new specs, plus existing-spec updates carried out inside
  them** (maintainer, 2026-10-12). The shape is `wellness-store` →
  (`wellness-pull` ∥ `apple-health-import` ∥ `hr-derivation` ∥ `recovery`) →
  `workout-wellness`.
- **Wellness reaches four surfaces** (maintainer, 2026-10-12):
  - the analytics index;
  - a recovery document;
  - a morning-of block on workout pages;
  - derived HR benchmarks.
- **The inbox approach for every source** (maintainer, 2026-10-12): accept
  whatever arrives in the inbox.
  - intervals.icu is pulled now.
  - Garmin's "Export Your Data" wellness JSON is imported. It is the
    maintainer's 2018-11 → 2023-02 history.
  - An Apple Health export fills 2023-03 → 2025-06 and adds sleep stages.
- **Derived HR applies automatically, as a dated benchmark source**
  (maintainer, 2026-10-12), over suggestions the athlete adopts. A
  hand-recorded value always wins. Benchmarks resolve by date alone today
  (`benchmarks.py:189-243`), so `hr-derivation`'s requirements must make the
  rule precise. The maintainer is asked at requirements approval. Historic HR
  load moves when the derivation moves, and the maintainer accepted that.
  - _Made precise at spec time (maintainer, 2026-10-12)._ Selection
    (`BenchmarkSet.applicable`) stays unchanged for every kind. "Hand-recorded
    wins" is a write-time rule of the HR pass: a derived entry is written
    only when evidence dated after the value in force disagrees with it by
    more than the hysteresis step, and every takeover of a hand value is
    announced. A hand entry's `applies_from` keeps filling only gaps. See
    hr-derivation `requirements.md`, Maintainer Decisions.
- **Archive plus series** (maintainer, 2026-10-12), over archive-only and
  index-backed storage.
- **Apple Health archives a canonical extract, not the export** (maintainer,
  2026-10-12, after viability reversed "archive the whole file"):
  - the extract holds only the wellness record types, as raw records,
    deterministic and compressed;
  - it carries the original's sha256, size and export date;
  - a later export's extract supersedes the earlier one.
- **The recovery page is descriptive** (maintainer, 2026-10-12), over a
  readiness verdict and over bare charts:
  - HRV as a 7-day ln mean against a 60-day normal range;
  - resting HR and sleep against rolling baselines;
  - days outside the range are marked;
  - fitness, fatigue and form on the same axis;
  - every method cited.
- Taken without asking, consistent with the above and the research:
  - **Baselines are per source and metric.** Apple's SDNN and the rMSSD that
    Garmin, Oura, WHOOP and Polar report are never spliced or converted.
    Even two rMSSD sources measure over different windows. Resting HR
    definitions also differ by platform:
    - Garmin: the lowest 30-minute average;
    - Apple: a sedentary estimate, revised during the day;
    - Oura and Suunto: the lowest HR in sleep;
    - Polar: none.
  - **Default source precedence**: a device-native export (Garmin export,
    Apple Health) outranks the intervals.icu relay. This mirrors Phase 8's
    "a device original outranks a partner-API or phone-side copy". It is
    configurable.
  - **intervals.icu's computed fields are never imported**: `ctl`, `atl`,
    `rampRate` and `sportInfo` eFTP/W′. fitdocs computes its own model.
  - **A non-activity FIT never becomes a workout page.** A Garmin
    monitoring or sleep FIT is held and reported; parsing its wellness
    messages is a follow-on.
  - **The day-boundary rule for nights is set once**, in `wellness-store`'s
    model.

#### Measured at discovery (2026-10-12, maintainer's data, shapes only)

- **intervals.icu**: one read-only GET at the maintainer's request.
  - `GET /api/v1/athlete/0/wellness` returns 483 day records with 47
    fields, 2025-06-17 → 2026-10-12.
  - Non-null counts:

    | Field | Days |
    |---|---|
    | `restingHR` | 452 |
    | `hrvSDNN` | 481 |
    | `hrv` (rMSSD) | 0 |
    | `sleepSecs` | 476 (no stages, score or sleeping HR) |
    | `spO2` | 479 |
    | `steps` | 481 |
    | `vo2max` | 242 |
    | `weight` | 29 |
    | subjective scores | 10 |
    | respiration, readiness | 0 |

  - The source is HealthFit relaying Apple Health.
  - Every record has `updated`.
  - The athlete object lists per-integration `*_wellness_keys` and download
    switches for Garmin, COROS, Polar, Suunto, Oura, WHOOP, Zepp, Huawei and
    Google.
- **HealthFit's iCloud folder** holds no wellness. It has 2,520 `.fit` and
  2,517 `.gpx` activity files and 13 app-database CSVs (gear, goals,
  routes, workout names and notes). HealthFit sends health metrics straight
  to intervals.icu.
- **Garmin export** (`pkm-data/raw/garmin_complete_dump_2026_09_12/`):
  - wellness is real only from 2018-11 to 2023-02;
  - `UDSFile` daily summaries give resting HR on 937 days, min/max HR,
    stress, body battery (2022), respiration, SpO2 and steps;
    - the daily value is `currentDayRestingHeartRate`;
    - `restingHeartRate` is a trailing 7-day mean (measured at spec time,
      2026-10-13; wellness-store `research.md`);
  - `sleepData` has 1,065 nights, 604 with stages;
  - `MetricsMaxMetData` gives VO2max, and `userBioMetrics` 23 weights;
  - there is no HRV JSON. Garmin keeps HRV in FIT files inside the upload
    zips;
  - after 2023-02 the Garmin is a bike computer, and its files are near
    empty.
- **The gap**: 2023-03 → 2025-06 exists only in Apple Health.

#### Viability (2026-10-12)

- **Apple Health parsing is viable on the stdlib.**
  - Streaming `iterparse` over a `zipfile` member, with root clearing, runs
    at about 10 s per GB of XML with flat ~33 MiB RSS on 3.11 and 3.13.
  - ZIP64 members over 4 GB stream fine.
  - Three export defects each break `iterparse`, and each has a byte-level
    fix:
    - the iOS 16 malformed DOCTYPE;
    - stray C0 control characters;
    - a duplicate `startDate` on `WorkoutStatistics` (Apple forum 714063).
  - Errors surface mid-stream, so an import is all-or-nothing.
- **Archiving the whole Apple export is unworkable**, hence the extract
  decision:
  - GitHub blocks files over 100 MiB, and LFS caps a file at 2 GB on the
    free plan;
  - every export is the whole history, so the hash-based archive never
    de-duplicates, and the archive grows by a full export each time;
  - in an iCloud git repository, each copy is stored and synced twice;
  - under "Optimize Mac Storage", macOS does not materialise an evicted file
    on read by default, so a rebuild from it would fail.
- **The inbox and the connector delivery path are FIT-only in many places.**
  `wellness-store` and `wellness-pull` list the pins they must move. Today a
  `.json` or `.zip` in the inbox is silently ignored, forever. The drain reads
  every candidate whole into memory (`sync.py:890`), so wellness candidates
  must stream.
- **Garmin-origin data on intervals.icu is at risk**
  (<https://forum.intervals.icu/t/api-access-to-intervals-icu/609>).
  - #752 (2026-10-09): the block is "likely".
  - #816 (2026-10-12): it would "probably" cover activities, FIT files,
    streams *and* wellness, and "likely" historical data received through
    Garmin's API. Manual uploads are unaffected. There is no timeline, and
    personal API keys are unanswered.
  - The maintainer's wellness comes from HealthFit and is unaffected. The
    maintainer's Garmin rides, which Phase 8 pulls through intervals.icu,
    may be affected (queued, see Direct Implementation Candidates).
  - For Garmin athletes, the Garmin-export route in `wellness-store` is the
    fallback.

#### Scope

- **In**:
  - the wellness format registry and non-FIT inbox recognition;
  - the wellness archive (`wellness-archive/`) and the normalized series
    location;
  - the per-day, per-field, source-attributed model, with a day-boundary
    rule;
  - per-field source precedence;
  - the rebuild on `regen`;
  - the parsers:
    - intervals.icu wellness JSON;
    - Garmin export JSON (`UDSFile`, `sleepData`, `MetricsMaxMetData`,
      `userBioMetrics`), as individual files;
    - Apple Health `export.zip`/`export.xml`, through a canonical extract;
  - the intervals.icu wellness pull, with the connector protocol, dispatch,
    delivery and ledger changes it needs;
  - derived resting and max HR as dated benchmark entries;
  - per-source baselines;
  - the recovery page and its owned location;
  - the morning-of block on workout pages, refreshed only when its bytes
    change;
  - the `wellness_daily` index table (and a baselines table if the design
    needs one);
  - the non-activity-FIT guard;
  - docs, the packaged skills, CHANGELOG entries and the existing-spec
    updates below.
- **Out**:
  - Garmin wellness FIT messages: monitoring, sleep, HRV status, Body
    Battery;
  - a whole Garmin-export-zip importer;
  - direct connectors for Garmin, COROS, Polar, Withings, Oura, WHOOP,
    Fitbit, Suunto and Zepp;
  - Health Auto Export and other third-party file exporters;
  - a generic wellness CSV;
  - intervals.icu custom wellness fields;
  - any push of wellness;
  - a readiness score, status label, recommendation or overload warning;
  - wellness on the history page;
  - fitdocs writing into athlete-owned daily notes;
  - HRV-derived thresholds;
  - nutrition, blood pressure, glucose and menstrual-cycle analysis. The
    model may reserve names, but nothing renders them.

#### Constraints

- **Personal data never enters the repository.** Tests use synthetic files
  shaped like the measured ones.
- **Absent is `None`, never 0.** That covers:
  - wellness values;
  - source sentinels (Garmin `-1`/`-2` stress);
  - baselines with too few days;
  - a derived benchmark with no qualifying evidence: no entry at all.
- **No new runtime dependency.** JSON, XML, zipfile and CSV come from the
  stdlib.
- **Wellness handling stays offline.** Wellness connector requests belong to
  `fitdocs pull`; recognizing, archiving, parsing, merging, rebuilding,
  checking and indexing wellness make no network request. The existing
  network owners remain `fitdocs.tiles` (map-tile fetches during rendering)
  and `fitdocs.connectors.http` (explicit `fitdocs connect` and `fitdocs pull`
  requests), as defined in `tech.md`.
- **Determinism.** Same archive, series and profile give the same bytes. The
  run date never enters a page (Phase 11's rule against daily churn).
- **Churn.** Two things land in the maintainer's iCloud and git wiki, and
  both must stay sparse:
  - morning-of re-renders, which happen only when a page's own day's inputs
    change;
  - derived-HR entries, which use hysteresis.
- **Writes are confined** to declared owned locations, atomically. Symlinks
  and foreign occupants are refused the way history and dashboards refuse
  them.
- Python 3.11 floor, `mypy --strict`. Every new assertion owes a named
  mutation it dies on.

#### Boundary Strategy

- **Why this split**:
  - **`wellness-store`** owns what a wellness value *is*: format
    recognition, archive, model, merge, series and the index table. Every
    other spec plugs into it or reads from it.
  - **`wellness-pull`** is connector work only: protocol, dispatch, delivery,
    ledger and the intervals.icu endpoint.
  - **`apple-health-import`** is the one heavy parser: streaming, defects,
    reduction, the extract. It is isolated so its risk does not hold the
    store.
  - **`hr-derivation`** touches benchmarks and load provenance, a different
    review surface from documents.
  - **`recovery`** owns baselines and the page. **`workout-wellness`** owns
    the page block and its re-render pass. It consumes the baselines, so it
    goes last.
- **Shared seams to watch**:
  - **The format registry and the delivered-file contract.**
    `wellness-pull`'s file must satisfy `wellness-store`'s intervals.icu
    parser, and `apple-health-import` registers through the same registry.
    Settle the registry in `wellness-store`'s design, as Phase 10 settled the
    producer seam.
  - **The series schema and the day-boundary rule.** Settle them once, in
    `wellness-store`. Every consumer reads them and none redefines them.
  - **The baselines library** from `recovery`, which `workout-wellness`
    consumes. One computation, so the page and the block never disagree.
  - **`CONTRACT_VERSION`.** Five Phase 12 specs bump it (settled at spec
    time, 2026-10-13): `wellness-store`, `wellness-pull`, `hr-derivation`,
    `recovery` and `workout-wellness`. `dashboards` (Phase 11) takes "10"
    first. Each lander does three things:
    - re-derives main + 1 at landing;
    - appends a literal "Raised from N to N+1 by <spec>" history pin;
    - re-pins every peer "What changed at this version" pin on main.

    `DOC_VERSION` moves only in `workout-wellness`, and the index
    `SCHEMA_VERSION` only in `wellness-store`. `recovery` adds no table.
  - **Append-only lists. Keep both sides on rebase**:
    - `OWNED_PATHS` / `DECLARED_DIRS`;
    - the `cli.py` command count;
    - the no-network command list;
    - `WRITING_ENTRY_POINTS`;
    - `PACKAGED_SKILLS`;
    - the connectors surface pin (`tests/connectors/test_surface.py`).

    The no-network order settled at spec time is: `sync, regen, load,
    dashboard, recovery, check, query, history, plan, derive-benchmarks,
    index`.
  - **The derived-benchmark write.** `with_derived_benchmarks` replaces the
    whole derived subset today (`load/profile.py:342-447`). `hr-derivation`
    partitions it, so the performance pass and the HR pass never erase each
    other.

#### Existing Spec Updates

All carried out inside the new specs, as in Phases 10 and 11. Amendment
numbers are the next free number at landing.

- [ ] inbox — non-FIT recognition through the wellness format registry, a
  reported "unrecognized" channel, and streamed reads for large candidates.
  The folder connector's reuse of `select_candidates` must not silently
  widen. Carried by wellness-store. Dependencies: wellness-store
- [ ] fit-ingest — the non-activity-FIT guard (`file_id.type` and the
  absence of a session), if the design places it in ingest. The design does:
  wellness-store carries `FileIdentity.file_type` and `is_activity_file`.
  Dependencies: wellness-store
- [ ] wiki-contract — owned locations, declared directories and stated
  guarantees, with `CONTRACT_VERSION` main + 1 per lander. Five specs carry
  a part each (settled at spec time, 2026-10-13):
  - wellness-store: `wellness-archive/` and `wellness/`;
  - recovery: `recovery/` and `recovery/assets/`;
  - wellness-pull: the `pull` guarantees;
  - hr-derivation: what `derive-benchmarks` reads and writes;
  - workout-wellness: the refreshed-region class.

  Dependencies: wellness-store, wellness-pull, hr-derivation, recovery,
  workout-wellness
- [ ] analytics-derived / analytics-index:
  - wellness-store carries the `wellness_daily` corpus producer,
    `SCHEMA_VERSION` + 1 and the regenerated `docs/analytics.md` block;
  - workout-wellness makes the render fingerprint ignore refreshed regions;
  - recovery adds no baselines table.

  Dependencies: wellness-store, workout-wellness
- [ ] connectors — `pull-wellness` becomes driven:
  - a new optional operation and capability dispatch;
  - format-keyed delivery instead of FIT-only;
  - a ledger keyspace and watermark for wellness;
  - Req 1.2-1.4 and 1.9 amended.

  The recovery command joins the no-network list. Dependencies:
  wellness-pull, recovery
- [ ] intervals-connector — the wellness endpoint, the trailing-window
  `updated` diff, the capability declaration and re-pinned mutation, the
  enable setting, and the Garmin attribution derived from
  `*_wellness_keys`. Dependencies: wellness-pull
- [ ] athlete-benchmarks — provenance for a series-derived entry (`document`
  relaxed or a series reference) and the precise hand-wins rule. At spec
  time, the hand-wins rule became write-time in hr-derivation, so
  selection is not amended. The amendment is provenance only: a `series`
  reference. Dependencies: hr-derivation
- [ ] performance-benchmarks — Req 10.4 ("shall derive no maximum heart rate
  and no resting heart rate") lifted, and the derived write partitioned.
  Dependencies: hr-derivation
- [ ] workout-docs — the morning-of section and any frontmatter key, plus
  the `DOC_VERSION` bump. Dependencies: workout-wellness
- [ ] load-channels _(found at spec time, 2026-10-13)_ — the heart-rate
  channel reports which dated resting and max entries it used.
  Dependencies: hr-derivation
- [ ] chart-catalog _(found at spec time)_ — Amendment 1, the
  `reference-band` kind. Dependencies: recovery
- [ ] chart-kit _(found at spec time)_ — the units `ml_per_kg_min` and
  `brpm`, appended to `fitdocs.units`. Dependencies: wellness-store

#### Direct Implementation Candidates

- [x] `product.md`: capability 7 (wellness and recovery, planned) added,
  and "wellness" lifted from the "Still deferred" acquisition line, in this
  discovery change.
- [x] Queue: Garmin-origin data may be blocked from the intervals.icu API,
  which threatens Phase 8's Garmin-ride pull. Recorded in this discovery
  change as `.kiro/queue/2026-10-12-intervals-garmin-data-block-risk.md`.
- [ ] pkm repository (external): register the new owned locations in
  `wiki-schema.md` when they ship. That means `wellness-archive/`, the
  series location and the recovery page, with `.gitignore` decisions and an
  area line in `index.md`. This is not this repository's work.

#### Follow-on candidates (not scheduled)

- **Garmin wellness FIT messages**, all in the public profile 21.218:
  - `monitoring_hr_data` (resting HR);
  - `sleep_level` and `sleep_assessment`;
  - `hrv_status_summary` and `hrv_value`;
  - `hsa_body_battery_data`, `respiration_rate`, `spo2_data` and
    `skin_temp_overnight`.

  Dispatch on message types, not `file_id.type`: Garmin's sleep and
  HRV-status file types are not in the public enum. A Garmin connector or a
  whole-export importer would need these. It would also bring Garmin
  overnight HRV, which the JSON export lacks.
- **A Garmin export-zip importer**: Phase 8's follow-on, now covering both
  activities and wellness.
- **Connectors where terms allow a personal client**:
  - Polar AccessLink: any Polar Flow user can register a client, but list
    endpoints cover only 28 days, and the licence is framed around
    proprietary applications, so check it;
  - Withings: a public API, no contract;
  - COROS: self-service OAuth through its MCP server since May 2026, a
    non-REST protocol, terms unverified.
- **File exporters through the folder connector**: Health Auto Export's
  iCloud JSON/CSV (a paid tier, which runs only while the phone is unlocked),
  and HealthFit if it ever writes wellness files. HealthFit 12.16 adds a
  "Recovery HRV" export to platforms.
- **Apple's rMSSD.** iOS/watchOS 27 adds
  `HeartRateVariabilityRMSSD` ("Recovery HRV" on Series 12 / Ultra 4). Once
  it is documented, it is a new metric in the model, never a continuation of
  SDNN.
- A generic wellness CSV, and intervals.icu custom wellness fields (users
  keep sleep stages there).
- A readiness score, if a published, citable method earns it. Rejected for
  now.
- Wellness overlays in dashboards: through `wellness_daily` and the chart
  catalogue, this needs no new spec.

#### Specs (dependency order)

- [ ] wellness-store — **brief written 2026-10-12; spec written 2026-10-13**
  (Phase 12 batch, wave 1, `tasks-generated`, all approvals set; 20
  requirements / 125 criteria, 6 majors / 27 executable tasks plus the
  optional maintainer-only smoke 6.3*; independent Step 3.5 review, two
  rounds; amended in place for the wave-2 seams: `MetricInfo.label`,
  winner-only `LATEST_ENTRY` rebuilds, extractor edge cases, the zip read
  rule, and the sanctioned `write_series` test builder; cross-spec reviewed,
  two rounds, PASS). The foundation:
  - the wellness format registry and non-FIT inbox recognition;
  - `wellness-archive/` (originals for JSON formats, a canonical extract
    where a format declares one);
  - the per-day, per-field, source-attributed model and the day-boundary
    rule;
  - per-field source precedence, with device-native exports over the
    intervals.icu relay by default;
  - fitdocs-owned yearly series files, rebuilt on `regen`;
  - the intervals.icu wellness JSON and Garmin export JSON parsers;
  - the non-activity-FIT guard and `check` findings;
  - the `wellness_daily` index table;
  - the inbox, wiki-contract, analytics-index and fit-ingest updates.

  Implement first. Dependencies: none
- [ ] wellness-pull — **brief written 2026-10-12; spec written 2026-10-13**
  (Phase 12 batch, wave 2, `tasks-generated`, all approvals set; 13
  requirements / 91 criteria, 6 majors / 19 executable tasks; task 1.1 is a
  live API check run by the controller session; independent Step 3.5
  review, two rounds; cross-spec reviewed, two rounds, PASS; bumps
  `CONTRACT_VERSION`). The connector side:
  - `pull-wellness` driven through a new optional operation and a capability
    dispatch;
  - format-keyed delivery of non-FIT bytes, and a ledger keyspace and
    watermark;
  - the intervals.icu wellness endpoint with trailing-window `updated`
    diffs, first-pull backfill and Garmin attribution;
  - connectors and intervals-connector amendments.

  Parallel with apple-health-import, hr-derivation and recovery.
  Dependencies: wellness-store
- [ ] apple-health-import — **brief written 2026-10-12; spec written
  2026-10-13** (Phase 12 batch, wave 2, `tasks-generated`, all approvals
  set; 14 requirements / 84 criteria, 6 majors / 12 executable tasks plus
  the optional maintainer-only smoke 6.2*; independent Step 3.5 review, two
  rounds; cross-spec reviewed, two rounds, PASS). Registering `apple-health`
  changes the default source order to garmin-export, apple-health,
  intervals-icu, so existing series rebuild once:
  - streaming stdlib parsing of `export.zip`/`export.xml`, with the three
    defect rewrites and all-or-nothing imports;
  - the canonical extract as the archived form;
  - per-type daily reductions (final resting-HR sample, an SDNN daily
    statistic, sleep-segment union by source preference);
  - source de-duplication, and supersession by a later export.

  Dependencies: wellness-store
- [ ] hr-derivation — **brief written 2026-10-12; spec written 2026-10-13**
  (Phase 12 batch, wave 2, `tasks-generated`, all approvals set; 11
  requirements / 87 criteria, 5 majors / 21 executable tasks plus the
  optional 2.8* (citations) and 5.3* (maintainer dry run); three maintainer
  decisions recorded; independent Step 3.5 review, two rounds; cross-spec
  reviewed, two rounds, PASS; bumps `CONTRACT_VERSION`):
  - derived resting HR from the series (per-source baselines, hysteresis);
  - derived max HR from workout HR (sustained maxima, artifact and
    cadence-lock rejection, recency window);
  - both as dated derived benchmark entries that apply automatically, with
    hand-recorded entries winning. Per the 2026-10-12 maintainer decision,
    this is a write-time rule and selection is unchanged;
  - athlete-benchmarks and performance-benchmarks amendments, with the
    derived write partitioned.

  Dependencies: wellness-store
- [ ] recovery — **brief written 2026-10-12; spec written 2026-10-13**
  (Phase 12 batch, wave 2, `tasks-generated`, all approvals set; 18
  requirements / 90 criteria, 6 majors / 20 executable tasks plus the
  optional maintainer-only page look 6.3*; independent Step 3.5 review, two
  rounds; cross-spec reviewed, two rounds, PASS). It adds the standalone
  `fitdocs recovery` command and the Garmin attribution helpers in
  `render/attribution.py`, carries chart-catalog Amendment 1
  (`reference-band`), and bumps `CONTRACT_VERSION`:
  - per-source, per-metric baselines (HRV 7-day ln mean against a 60-day
    range, resting HR, sleep);
  - a descriptive, cited recovery page with fitness, fatigue and form
    computed through load-history's functions, and the page's owned
    location;
  - charts from chart-kit and chart-catalog kinds;
  - no baselines index table (decided at spec time);
  - wiki-contract and connectors amendments.

  Dependencies: wellness-store, chart-catalog
- [ ] workout-wellness — **brief written 2026-10-12; spec written
  2026-10-13** (Phase 12 batch, wave 3, `tasks-generated`, all approvals
  set; 12 requirements / 66 criteria, 5 majors / 15 executable tasks;
  independent Step 3.5 review, two rounds; cross-spec reviewed, two rounds,
  PASS). It adds the refreshed-region class `REFRESHED_REGIONS`, the
  `morning` region and a morning-of pass that visits every page and
  compares bytes. It bumps `DOC_VERSION` and `CONTRACT_VERSION`:
  - the morning-of block on workout pages (that morning's resting HR and HRV
    against baseline, and the previous night's sleep);
  - a fingerprint of the printed facts, and a pass that visits every page
    and rewrites a block only when its bytes change. This replaced the
    targeted re-render at spec time;
  - the `DOC_VERSION` bump and the workout-docs amendment.

  Implement last. Dependencies: recovery
