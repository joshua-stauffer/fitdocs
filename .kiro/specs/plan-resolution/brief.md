# Brief: plan-resolution

## Problem

A block page that lists planned workouts is a plan; a block page that also
says which of them were done, by which logged activity, and how the
mesocycle's actual load compares with its target, is a training record. The
base case is trivial — a run planned for Tuesday and a run logged on Tuesday
are the same workout — but real logs are messier: a track session planned as
one workout is logged as three activities (warm-up, intervals, cool-down);
two runs on one day compete for one planned row; a workout done on Wednesday
was planned for Tuesday; a strength session was added that was never planned.
The resolver must do its best, revise its answer when a better-fitting
activity arrives later, and leave the final word to the athlete and their
curating LLM without inventing a classifier it cannot justify.

## Current State

- `training-blocks` (upstream) renders the block page and planned pages with
  a `Resolution` seam that reads "unresolved", and defines the override entry
  grammar in the plan source without applying it.
- A logged workout page exposes, in frontmatter, `date` (local, quoted),
  `start_time`, `sport`, `modality`, `indoor` (when true), `moving_time`,
  `distance_km` and the three load keys (`src/fitdocs/render/frontmatter.py:109-151`,
  `contract.LOAD_KEYS`). `sub_sport` is not there (`model.py:127`, consumed at
  ingest only), so activity type is `sport` + `modality` (+ `indoor`) and
  nothing finer.
- One contract reader exists for the date (`contract.document_date`,
  `contract.py:869-907`, returns `None` for undated pages, never a fabricated
  day) and none for `sport` or `modality`. The consumers test would not catch
  an inline `frontmatter.get("sport")`: `FORBIDDEN_LITERALS` holds only the
  fence and the workout type (`tests/test_contract_consumers.py:246-249`).
- The pattern for a pass chained after the writer is the load pass:
  `cli.py:279-284` (sync), `:306-309` (drain), `:385-386` (regen) call
  `_run_load_pass` → `load.engine.apply_load`, which re-discovers
  `workouts/*.md` itself and reports. A reconciler follows that shape, after
  the load pass, because it reads load values.
- `fitdocs.history` publishes `select_methodology` and `partition_pages`
  (`history/series.py:230+`) for the one-methodology rule; its
  `scan_documents` is unpublished (`history/__init__.py:45-65`) and its
  `PageRecord` carries no sport or modality, so it cannot be the reconciler's
  scan.
- In-place region editing exists only for the load region
  (`load/docedit.py:208-291`, hard-bound to `LOAD_REGION` and `LoadResult`;
  `_atomic_write` private to `load/engine.py:652-671`). This spec does not
  need it: the block page and planned pages are regenerated whole from
  (source, corpus, settings), the history page's model.

## Desired Outcome

- **Every planned row resolves to one of**: matched (the logged stems that
  fulfil it, with a confidence label), overridden (the source said so),
  skipped (the source said so), not logged (its date has passed and nothing
  matched), or upcoming (its date is after the pass's `today`). The block
  page's resolution column and each planned page's resolution section show
  it, with links to the logged pages.
- **Match rules, stated and mutation-tested**: the base case is equal `date`
  and equal type (`sport`, and `modality` when the row states one); one row
  may absorb several same-day same-type activities when no other row on that
  day competes for them (the split-session case) and says it did; several
  rows on one day with the same type and several candidate activities is
  ambiguous — the resolver may propose an assignment by start-time order and
  must label it ambiguous, never present it as settled; a workout logged on a
  different day than planned is not matched by heuristics (moving a row is an
  amendment, and the skill teaches that). Confidence is a closed
  enumeration the page shows.
- **Overrides win.** An override entry naming a row and stems replaces any
  heuristic result for that row and removes those stems from every other
  row's candidates; an override naming a stem that does not exist in the
  corpus is reported on the page and in the run report, never dropped.
- **Statelessness.** Each run recomputes from the current source and corpus;
  a better-fitting activity logged later replaces an earlier match with no
  migration and no persisted match table.
- **Per-mesocycle load.** For every mesocycle: the sum of `load_value` over
  all logged workouts dated in its window (matched or not — an unplanned
  session still loads the athlete), under one methodology (the configured
  default; pages scored by another are excluded and the exclusion stated),
  with a coverage statement (n of m pages scored), shown beside the source's
  target or "no target". Unscored pages make the sum a lower bound and the
  page says so; a window with no scored page shows "not computed", never 0.
- **Unplanned workouts** logged inside a mesocycle's window are listed under
  it, so the sum's composition is visible.
- **Chaining and command.** The pass runs at the end of `sync`, `drain` and
  `regen` after the load pass, and standalone as part of `fitdocs plan`; it
  never prompts, never opens a `.fit`, and writes only under the rendered
  location.

## Approach

A reconciling module in the same package as `training-blocks` (working name
`fitdocs.plans.resolve`) that scans workout frontmatter through `docio` and
new `contract` readers into its own record type (stem, date, sport, modality,
indoor, start time, load, methodology), runs the match rules per block, sums
load per mesocycle through `history`'s published methodology helpers, and
returns a `Resolution` for the render defined upstream. The pass wires it in
front of the existing renderer and is registered as a second writing entry
point into the rendered location.

## Scope

- **In**: the corpus scan and its contract readers (`document_sport`,
  `document_modality`, and the `FORBIDDEN_LITERALS` extension that keeps
  them the only readers); the match rules and confidence enumeration;
  override application and its problems; the per-mesocycle sum, methodology
  selection and coverage; the unplanned listing; the `Resolution` filled
  in; the chaining and the `fitdocs plan` integration; the run report lines;
  the confinement registration.
- **Out**: any change to what the block or planned pages *are*
  (`training-blocks`); editing the source; writing anything into logged
  workout pages (a back-link key is a listed candidate, not a deliverable);
  scoring a logged workout against its prescription; sub-sport or interval
  detection from records; forecasting; the skill.

## Boundary Candidates

- **Corpus scan** (pure over frontmatter): readers, record type, one
  methodology.
- **Matching** (pure): rules, cardinality, confidence, overrides, problems.
- **Aggregation** (pure): per-mesocycle sum, coverage, unplanned listing.
- **The pass**: wiring, chaining, report, confinement.

## Out of Boundary

- Whether a workout was done *well* — no comparison of logged pace, distance
  or duration against the prescription beyond what the athlete reads on the
  two linked pages.
- The plan-source grammar (owned upstream; this spec applies overrides, it
  does not define their syntax).
- Load values themselves — read, summed, never computed or altered.

## Upstream / Downstream

- **Upstream**: `training-blocks` (`Block`, planned-page frontmatter, the
  `Resolution` seam, the rendered location and its `plan` entry point);
  `training-load` (load keys and the pass this one runs after);
  `load-history` (methodology helpers); `wiki-contract` (contract readers).
- **Downstream**: `build-training-block` teaches the confidence labels, the
  override entry and when to write one; a future forecast reads the
  per-mesocycle sums; a future back-link key would be written here.

## Existing Spec Touchpoints

- **Extends**: `wiki-contract` only if the design adds anything to the
  published contract (a second writer into an already-declared location is
  a contract-document note, not a version bump); `workout-docs` only if a
  back-link key is chosen, which would make it managed and move the
  `MANAGED_KEYS` pins (`tests/test_contract.py:186-212, 230-272`).
- **Adjacent**: `load-history` (shares the one-methodology helpers; must not
  deep-import its unpublished scan); `threshold-load` (its boundary test
  `tests/load/threshold/test_boundary.py` pins the calculator's imports —
  the reconciler must not become reachable from it); `activity-qa-flags`
  (a flagged page still matches; flags are not a reason to exclude).

## Constraints

- **Documents only; stateless; deterministic.** No `.fit`, no network, no
  prompt, no persisted match state; the only clock is the pass's resolved
  `today`, used solely to separate "upcoming" from "not logged".
- **One contract reader per field**, added to `contract.py` with the key
  literals added to `FORBIDDEN_LITERALS` in the same change, and the new
  module registered in both `CONVERTED_MODULES` and `CONTRACT_BINDINGS`
  (`tests/test_contract_consumers.py:83`).
- **Absent is `None`.** Undated pages belong to no day and never match; a
  page without a load counts as unscored, never as 0; no target means no
  comparison.
- **No classifier.** Same-day same-type ambiguity is labelled, not resolved
  by guessing from distance or duration; the enumeration of confidence
  labels is closed and every label has a stated rule.
- **Every rule owes a named mutation** (`change-protocol.md` § Fixture
  Discrimination): the split-session absorb, the competing-row ambiguity,
  the override precedence, the cross-day non-match, the methodology
  exclusion and the coverage count each have a test that reds under a
  one-line change to the rule.
- **Confinement**: a second `EntryPoint` writing only under the rendered
  location, with its own `non_vacuous`; the guard's permitted set already
  holds the location after `training-blocks`.
- Stdlib only; synthetic fixtures; no personal data.
