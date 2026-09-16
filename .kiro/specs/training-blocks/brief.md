# Brief: training-blocks

## Problem

The archive can describe what training did — every page carries a load, the
history page draws fitness, fatigue and form across nine years — and nothing
can state what training should do next. The athlete plans in prose somewhere
else, the plan drifts as the weeks go, and by the end of a block there is no
record of what was originally intended, what changed, when, or why. The
roadmap deferred cycles and blocks from the first pass through Phase 6
(roadmap `## Overview`, `## Scope`; product.md "Explicitly deferred"). Phase 7
lifts that deferral, and this spec is its foundation: the plan as a document.

## Current State

- The data root holds two document types, both fitdocs-owned and both
  derived: workout pages under `workouts/` (`type: workout`,
  `contract.WORKOUT_TYPE`, `src/fitdocs/contract.py:282`) and the history page
  under `history/` (`type: training-history`, declared in its own package,
  `src/fitdocs/history/page.py:75`). There is no central type registry; the
  second type was added by declaring its own constants and frontmatter
  vocabulary in its own package (`docs/ownership-contract.md:73-100`), and
  that is the precedent.
- Adding a non-activity location has a complete precedent in `load-history`:
  `layout.py` constants and path helpers (`:98-115, 248-269`), `OWNED_PATHS`
  and `DECLARED_DIRS` extended (`:120-121, 146`), a declaration branch in
  `declaration.py` (`_HISTORY_CONTENT:253`, `declaration_text:316`), a new
  `EntryPoint` with its own `non_vacuous` in `tests/test_confinement.py`
  (`:606-611`), a contract version bump with a "what changed" note in
  `docs/ownership-contract.md`, and a new package with an append-only
  `__all__` pinned in `tests/test_public_api.py`.
- User-owned files fitdocs only reads have a precedent too: `athlete.toml`
  (written key-wise, never deleted) and `fitdocs.toml` ("read-only to
  fitdocs: nothing in fitdocs ever creates, writes, or modifies it",
  `docs/ownership-contract.md:361-380`), both deliberately outside
  `OWNED_PATHS` (`tests/test_layout.py:603-614`). A configured read location
  has one as well: `[inbox] path` in `fitdocs.toml` (`inbox` spec).
- TOML is parsed by `tomllib` in four modules with no shared helper
  (`settings.py:50-70`, `athlete.py`, `quarantine.py`, `load/profile.py`).
  YAML is barred from registered modules by
  `tests/test_contract_consumers.py:261-343`.
- fitdocs emits no wikilinks and no cross-document links anywhere; charts are
  doc-relative image links and that is the only link form
  (`src/fitdocs/render/views.py:25-29`). Relative POSIX link strings are
  built by plain joins, never `os.path.join` (`layout.py:28-33`).
- The region grammar is generic over region ids (`src/fitdocs/docmerge.py`),
  so a block page may carry a `notes` region without touching
  `PRESERVED_REGIONS` — which is pinned by exact equality
  (`tests/test_contract.py:67-68`) and must not grow for a page of another
  type.

## Desired Outcome

- **One source file per block, written by the athlete or their LLM, read by
  fitdocs, never written by it.** TOML. It states the block's title, `starts`,
  `ends`, the goal in prose, the mesocycle length in days, an optional target
  load and focus per mesocycle, and the planned workouts: each with a stable
  id, a date, a sport from fitdocs' own vocabulary (`Run`, `Ride`, `Swim`,
  `Walk`, `Hike`, `Rowing`, `Workout`; optional `modality` for the generic
  sport; optional `indoor`), a title, a one-line summary for the table, and a
  prescription in prose for its own page (for example: warm up 2 miles,
  20 × 400 m starting around 70 s and working toward 66, 200 m jog between,
  cool down 2 miles). Any number of workouts of any type on a day.
  Amendments are appended, dated, with a reason, naming a row by id and the
  fields it changes, or adding or removing a row, or changing a mesocycle's
  target; nothing earlier is edited. Override entries (consumed by
  `plan-resolution`) are part of the same grammar so the format is defined
  once.
- **One block page**, rendered from the source into an owned location. Its
  frontmatter carries the bounds, the goal, the mesocycle length and the
  page's own type and version. Its body opens with the bounds, the goal and
  the mesocycle length; then one section per mesocycle, numbered, with its
  date window, its target load line (or "no target"), and a table of that
  mesocycle's days — every day, rest days included and said so — with each
  planned workout's title, summary and a link to its planned page, plus a
  resolution column this spec renders as unresolved; then the revision
  record: the original plan as first written and each amendment with its
  date and reason, superseded values shown beside their replacements; and a
  user-owned `notes` region.
- **One planned-workout page per row**, typed as its own document kind, with
  frontmatter the reconciler and the PKM can read (block, mesocycle number,
  date, sport, modality, title, version) and a body holding the title, the
  prescription, a link back to the block page, and a resolution section this
  spec renders as unresolved. A moved workout keeps its page; a removed one's
  page is removed and the revision record says so.
- **`fitdocs plan`** renders every block whose source is present, validates
  loudly, reports per block (rendered, unchanged, invalid) and exits by the
  established 0/1/2 policy. Byte-identical output for an unchanged source.
- The locations are declared, guarded and versioned like every other: the
  source directory stated as user-owned in the contract, the rendered
  directory in `OWNED_PATHS`, `DECLARED_DIRS` with its own `AGENTS.md` text,
  the confinement guard and the contract version.

## Approach

A new top-level package (working name `fitdocs.plans`) with a pure model
(source → `Block` with derived mesocycles and the current rows after
amendments, plus the revision trail), a validator that names the file, entry
and field on every error, a `Resolution` value type with an "unresolved"
default, and renderers for the block page and the planned page that take
(`Block`, `Resolution`) and return bytes. The pass reads the source
directory, renders, and writes with the same commit discipline as the other
passes. The source lives in its own data-root directory, configurable under a
`[plans]` table in `fitdocs.toml` with a default, outside every owned prefix;
rendered pages live in a new owned directory — the design names both (the
roadmap's working names are `plans/` for sources and `blocks/` for pages).
Links are relative markdown links, never wikilinks (roadmap Phase 7
decisions).

## Scope

- **In**: the source grammar, its parser and validation; mesocycle
  derivation; amendment application and the revision trail; the two page
  types, their frontmatter vocabularies and versions, declared in the new
  package; the `Resolution` seam and its unresolved rendering; the source
  location and its settings key; the rendered location with `layout`
  helpers, declaration text, confinement registration and contract version
  bump; the `fitdocs plan` command and its report; the wiki-contract
  amendment recording the locations and types; goldens for both pages.
- **Out**: any matching of logged workouts, load sums, or chaining after
  `sync` (`plan-resolution`); the skill (`build-training-block`); writing or
  editing the source; forecasting; per-row load targets; a structured
  interval grammar; macrocycles; pkm-side schema and wrappers.

## Boundary Candidates

- **Source model** (pure): parse, validate, derive mesocycles, apply
  amendments, expose the current rows and the revision trail.
- **Page rendering** (pure): block page and planned page from
  (`Block`, `Resolution`); the link helpers in `layout.py`.
- **The pass and its locations**: settings key, source discovery, write
  commit order, declaration, confinement, contract version, command and
  report.

## Out of Boundary

- What a good plan is — no periodisation rules, no load progression checks,
  no warnings about volume jumps.
- Any reading of workout pages or `athlete.toml` beyond nothing: this spec
  never opens the corpus.
- The override entries' semantics (defined here syntactically so the grammar
  is one; applied by `plan-resolution`).

## Upstream / Downstream

- **Upstream**: `wiki-contract` (locations, types, version), `workout-docs`
  (the region grammar and the frontmatter builder pattern), `inbox` (the
  configured-location pattern), `load-history` (the non-activity page
  precedent), `distribution` only as the README's command list.
- **Downstream**: `plan-resolution` consumes `Block`, the planned-page
  frontmatter and the `Resolution` seam; `build-training-block` teaches the
  source grammar and the command; a future forecast reads the per-mesocycle
  targets.

## Existing Spec Touchpoints

- **Extends**: `wiki-contract` — Amendment 3: the user-owned source location,
  the owned rendered location, two further document types declared and
  versioned by this spec, `CONTRACT_VERSION` advanced.
- **Adjacent**: `load-history` (same package shape; nothing shared but
  `render/charts` primitives if a chart is ever wanted — none is here);
  `effort-tags` (a user-owned *key* precedent this spec deliberately does not
  use); `training-load` (the load placeholder → fill pattern the
  `Resolution` seam mirrors).

## Constraints

- **The source is never written by fitdocs**, and lives outside every
  `OWNED_PATHS` prefix (viability check 2026-09-15: the contract defines
  owned as deletable wholesale, `docs/ownership-contract.md:37-40,61-67`).
  It is documented in the shared-and-user-owned section, which carries no
  equality pin.
- **TOML via `tomllib`; no YAML** (`tests/test_contract_consumers.py:261-343`).
  A shared parse helper is welcome but is a task decision, not a
  requirement.
- **Validation is loud and total**: an invalid source leaves that block's
  pages untouched and names file, entry and field; a row outside the bounds,
  an unknown sport, a duplicate id, an amendment naming an unknown id, or an
  override before the row exists are each errors, never warnings.
- **Absent is `None`**: no target → the line says so; a mesocycle with no
  rows renders its days as rest, not as an empty table; the last mesocycle
  may be shorter and the window says so.
- **Byte-determinism**: identical source → identical bytes; no clock, no
  corpus. The only time this spec reads is the source's own dates.
- **New types declare their own vocabulary in the new package** (the
  `training-history` precedent), so `MANAGED_KEYS`, `USER_KEYS`,
  `PRESERVED_REGIONS` and `DOC_VERSION` do not move; the `notes` region on
  the block page uses the generic grammar without joining
  `PRESERVED_REGIONS`.
- **Every pin moves in the same change**: `tests/test_layout.py:537-545,
  670`, `tests/test_ownership_contract.py:81-108`,
  `tests/test_declaration_goldens.py:41-46`, `tests/test_declaration.py:160`,
  `tests/test_confinement.py` (`EntryPoint` at `:568-591`, the `history`
  registration at `:606-611` as template; `tests/test_effort_tags_e2e.py:506`
  only subset-checks the ids and does not move), a new `__all__` pin in `tests/test_public_api.py`, `CONVERTED_MODULES` +
  `CONTRACT_BINDINGS` together in `tests/test_contract_consumers.py:83`, and
  the mypy `files` list in `pyproject.toml:60-92`.
- **Links are relative markdown links** built by string joins in
  `layout.py`; no wikilinks; no `os.path.join`.
- Stdlib only. Fixtures are synthetic sources; no personal data.
