# Requirements Document

## Project Description (Input)
The archive can describe what training did -- every page carries a load, the
history page draws fitness, fatigue and form across nine years -- and nothing
can state what training should do next. The athlete plans in prose somewhere
else, the plan drifts as the weeks go, and by the end of a block there is no
record of what was originally intended, what changed, when, or why. Phase 7 of
the roadmap lifts the first pass's deferral of cycles and blocks, and this spec
is its foundation: the plan as a document. The athlete (or the LLM curating
their wiki) writes **one source file per training block** -- dated bounds, a
goal in prose, a mesocycle length in days, an optional target load per
mesocycle, and the planned workouts, each with a stable id, a date, a sport
from fitdocs' own vocabulary, a title, a one-line summary and a prescription in
prose -- in a user-owned location fitdocs only reads. Changes are appended as
dated amendments with a reason; nothing earlier is edited, so the source is
its own history. `fitdocs plan` renders each block into **one block page**
(bounds, goal, mesocycle length, then one numbered section per derived
mesocycle with its date window, its target load and a table of every day --
rest days said so -- linking each planned workout to its own page, then the
revision record, then a user-owned notes region) and **one planned-workout
page per row**, in a new fitdocs-owned location declared, guarded and
versioned like every other. Both pages carry a resolution slot this spec
renders as *unresolved*; `plan-resolution` (the next spec) fills it by
matching logged workouts, and `build-training-block` (the spec after) teaches
the source grammar and the command. This spec also lands the wiki-contract's
Amendment 3: the user-owned plan-source location, the owned rendered location,
the two new document types, and the advanced contract version.
Source: `.kiro/specs/training-blocks/brief.md`; Phase 7 of
`.kiro/steering/roadmap.md`.

## Introduction

`training-blocks` is the first fitdocs feature whose primary input is a file
the athlete writes for fitdocs to read. Every earlier input is either a `.fit`
file the athlete never edits or a configuration file (`fitdocs.toml`,
`athlete.toml`) that carries settings rather than content. The plan source is
content: it is the athlete's statement of intent, it changes over the life of a
block, and its history matters as much as its current state. That is why the
source is append-only -- an amendment names what changed, when and why, and the
rendered page shows the current plan beside the original and each supersession
-- and why the source lives outside every location fitdocs owns: the ownership
contract defines "owned" as "fitdocs may create, rewrite, or delete wholesale",
and a regeneration entitled to delete the athlete's plan would be a defect, not
a feature.

The rendered pages are derived artifacts in the ordinary sense: byte-identical
for an unchanged source, rebuilt in full on every run, re-derivable from the
source alone, and never the place a fact is first written. The one exception is
the block page's `notes` region, which is the athlete's and is carried over
verbatim the way every workout document's `notes` region is. The planned pages
carry nothing of the athlete's; a moved workout keeps its page because its
identity is its id, not its date, and a removed workout's page is removed.

The feature stops at rendering. It never opens a workout page, never reads a
load value, and never decides whether a planned session was done -- the
resolution column on the block page and the resolution section on each planned
page exist so that the next spec can fill them, and this spec renders both as
*unresolved*. Validation is loud and total: a source with any problem is named
by file, entry and field, and that block's existing pages are left exactly as
they were, never half-rendered. Absent is `None`: a mesocycle with no target
says so, a mesocycle with no planned workouts renders its days as rest, and a
short final mesocycle says how short.

## Boundary Context

- **In scope**: the plan-source format -- its fields, its sport vocabulary, its
  append-only amendment entries, and the syntactic form of the override entries
  the next spec consumes; the loud, total validation of a source; mesocycle
  derivation from the bounds and the length; amendment application and the
  revision trail; the block page and the planned-workout page, each with its
  own document type, frontmatter and format version; the *unresolved* rendering
  of the resolution slot on both pages, and the seam through which a caller
  supplies a filled resolution; the user-owned source location and the setting
  that names it; the fitdocs-owned rendered location with its in-tree
  declaration, its entry in the published ownership contract and in the
  write-confinement guard, and the contract-version advance a new owned path
  forces; the `fitdocs plan` command, its settings and its run report; the
  wiki-contract amendment recording the locations and the document types.
- **Out of scope**: matching logged workouts to planned rows, summing actual
  load per mesocycle, confidence labels, unplanned-workout listings, applying
  override entries, and chaining the pass after `sync`, `drain` or `regen`
  (`plan-resolution`); the packaged authoring skill and the by-name skill
  locator (`build-training-block`); writing or editing the plan source in any
  way; forecasting; per-row load targets; a structured interval or pace
  grammar (the prescription is prose); macrocycles or any page spanning
  several blocks; any judgement about the plan's quality -- no periodisation
  rules, no progression checks, no volume warnings; any change to how a
  workout is scored, to the history page, or to the workout document; any
  change to the pkm repository.
- **Adjacent expectations**: `wiki-contract` owns the document contract, the
  ownership document, the in-tree declaration mechanism and the contract
  version; this feature adds one owned location and two document types to each
  and leaves every existing guarantee in force, and it declares the new types'
  vocabularies in its own package rather than in the shared contract leaf, the
  way the history page's type is declared. `workout-docs` owns the region
  grammar and the frontmatter conventions the block page follows; this feature
  reuses the generic region mechanism for the block page's `notes` region
  without widening the published preserved-region list, which describes
  workout documents. `inbox` established that a location named in the athlete's
  settings file is resolved against the data root and validated loudly; the
  plan-source setting follows that shape but grants no write right, because
  fitdocs only reads there. `load-history` established the shape of a
  non-activity owned location and everything that moves with it; this feature
  follows that shape exactly. `distribution` is touched only in that the
  README names the new command.
- **Downstream contract**: `plan-resolution` consumes the parsed block (its
  current rows after amendments, its derived mesocycles, and its override
  entries), the planned page's frontmatter, the resolution seam and its
  *unresolved* default, and the rendered location's writing entry point;
  `build-training-block` teaches the source grammar and the command exactly as
  this spec defines them. A change to the source grammar, the page frontmatter,
  the resolution seam's shape, or the rendered location is a change both must
  re-check.

## Requirements

### Requirement 1: The Plan Source, Written by the Athlete and Only Read by fitdocs
**Objective:** As an athlete (or the LLM curating my wiki), I want to state a training block once, in a structured file I own, so that the plan lives in my wiki as data fitdocs can render and nothing fitdocs does can ever rewrite or lose it.

#### Acceptance Criteria
1. The fitdocs CLI shall read each training block from one plan-source file in a user-owned plan-source directory under the data root, and shall take the block's identity from that file's name.
2. The fitdocs CLI shall never create, write, rename, or delete a plan-source file or the plan-source directory, under any command, option, or failure condition.
3. The fitdocs CLI shall accept a plan source that states the block's title, its first and last day, its goal in prose, and its mesocycle length in days, and shall treat each of these as required.
4. The fitdocs CLI shall accept, per mesocycle, an optional target load and an optional focus in prose, and shall treat an unstated target as absent -- never as zero and never as a default.
5. The fitdocs CLI shall accept any number of planned workouts, each stating a stable id, a date, a sport, a title, a one-line summary, and a prescription in prose, and shall accept any number of planned workouts of any sport on one day.
6. The fitdocs CLI shall accept as a planned workout's sport exactly the sport vocabulary a generated workout document carries -- `Run`, `Ride`, `Swim`, `Walk`, `Hike`, `Rowing`, `Workout` -- and no other spelling.
7. Where a planned workout's sport is the generic `Workout`, the fitdocs CLI shall accept an optional modality drawn from the vocabulary a generated workout document carries, and shall accept an optional indoor flag on any planned workout.
8. The fitdocs CLI shall accept a plan-source directory name configured in the shared settings file, shall default it when unconfigured, shall resolve a relative name against the data root and use an absolute one as given, and shall treat an absent settings file or an absent table as the default rather than as an error.
9. If the configured plan-source directory resolves to the data root itself or to a location inside any fitdocs-owned path, the fitdocs CLI shall stop with a configuration error naming the settings file, the key and the resolved path, because fitdocs may delete owned paths wholesale and a plan there would not be safe.
10. If a plan-source directory name is configured and the directory does not exist, the fitdocs CLI shall stop with a configuration error naming the path; while no name is configured and the default directory does not exist, the fitdocs CLI shall say so plainly, write nothing, and complete without reporting a failure.

### Requirement 2: Loud, Total Validation
**Objective:** As an athlete whose plan is written by hand or by an LLM, I want every mistake in a source named precisely and nothing rendered from a broken source, so that a typo never becomes a silently wrong page.

#### Acceptance Criteria
1. If a plan source cannot be read, is not well-formed, or lacks a required field, the fitdocs CLI shall report the file, the entry and the field concerned, in words that say what was expected.
2. The fitdocs CLI shall report every problem it can determine independently in one source at once, rather than stopping at the first, so that a hand-written source is corrected in one pass.
3. If a block's last day precedes its first, if its mesocycle length is not a whole number of at least one day, or if its title, goal, or a workout's title, summary or prescription is empty, the fitdocs CLI shall report each as a problem naming the field.
4. If a planned workout's date falls outside the block's bounds, the fitdocs CLI shall report it as a problem naming that workout by id, never silently placing it in the nearest mesocycle.
5. If a planned workout names a sport outside the accepted vocabulary, states a modality for a sport other than the generic one, or states a modality outside the accepted vocabulary, the fitdocs CLI shall report it as a problem naming the workout and the field.
6. If two planned workouts share an id, if a block's file name or a workout's id is not a lowercase identifier of letters, digits and hyphens beginning with a letter or digit, or if a block's file name equals, ignoring case, the stem of the in-tree ownership declaration's filename, the fitdocs CLI shall report it as a problem naming the id and where it occurs.
7. If a workout's title or summary contains a line break, the fitdocs CLI shall report it as a problem, because both are rendered on a single line of a table.
8. If a mesocycle target names a mesocycle number outside the derived range, or names one twice, the fitdocs CLI shall report it as a problem naming the number.
9. If an amendment names a workout id that does not exist at that point in the plan's history, removes an id already removed, adds an id ever used before in the block's history, changes no field, changes a field the grammar does not allow, or moves a workout outside the block's bounds, the fitdocs CLI shall report it as a problem naming the amendment and the id.
10. If an override entry names a workout id that does not exist as of the override's date, names no logged workout while not marking the row skipped, or does both, the fitdocs CLI shall report it as a problem naming the override and the id; the override's meaning is otherwise not this feature's to judge.
11. While a source has any reported problem, the fitdocs CLI shall render nothing from it and shall leave that block's existing pages, if any, exactly as they were -- never half-rendered, never partially removed.
12. The fitdocs CLI shall warn about nothing: every condition it reports is a problem that withholds rendering, and every source it renders is one it found no problem with.

### Requirement 3: Mesocycles Derived, Amendments Appended, History Kept
**Objective:** As an athlete whose plan changes as the block goes on, I want mesocycles to follow from the dates I stated and every change to be an addition with a date and a reason, so that the plan's history is in the source itself and no earlier intention is ever overwritten.

#### Acceptance Criteria
1. The fitdocs CLI shall derive the block's mesocycles from its first day, its last day and its mesocycle length alone: consecutive, numbered from one, each of the stated length except the last, which ends on the block's last day and may be shorter.
2. The fitdocs CLI shall place each planned workout in the mesocycle whose date window contains the workout's date, and shall place it nowhere else.
3. The fitdocs CLI shall read amendments as a dated, ordered list of additions to the source, each carrying a reason, and shall apply them in order to the plan as first written to obtain the current plan.
4. The fitdocs CLI shall accept, within one amendment, any number of changes of these kinds: a change to the named fields of an existing planned workout, the addition of a planned workout, the removal of a planned workout by id, and a change to a mesocycle's target load or focus -- whether or not that mesocycle had a stated target before, in which case the superseded value is the absent target.
5. If amendments are not in non-decreasing date order, the fitdocs CLI shall report it as a problem naming the amendment, because the amendment list is the block's chronology.
6. When an amendment changes a planned workout's date, the fitdocs CLI shall keep that workout's identity -- the same id, the same planned page -- and shall place it in the mesocycle its new date falls in, whether or not that is a different mesocycle.
7. The fitdocs CLI shall keep the revision trail: the plan as first written, and, per amendment, its date, its reason, and each change with its superseded value beside its replacement.
8. The fitdocs CLI shall read override entries -- a date, a workout id, and either one or more logged-workout identifiers or a skipped mark, with an optional reason -- as part of the same source grammar, shall validate their form and their reference to a workout, and shall attach no meaning to them beyond that.
9. The fitdocs CLI shall never interpret an amendment or an override as an instruction to edit the source, and shall never itself append to a source.

### Requirement 4: One Block Page
**Objective:** As a PKM user, I want one readable page per block that shows the current plan by mesocycle and day, links to every planned workout, and keeps the record of how the plan changed, so that the block is a first-class page in my wiki.

#### Acceptance Criteria
1. The fitdocs CLI shall write one block page per valid plan source, named by the block's identity, in the fitdocs-owned rendered location.
2. The fitdocs CLI shall give the block page a frontmatter block carrying the block's title, its own document type -- distinct from the workout document's and from the history page's -- the generator, the page's own format version, the block's identity, its first and last day, its goal, and its mesocycle length, and shall carry the generated-document provenance marking.
3. The fitdocs CLI shall open the block page's body with the block's first and last day, its goal, and its mesocycle length together with the number of mesocycles derived.
4. The fitdocs CLI shall write one section per mesocycle, numbered, stating its date window and its length, saying so when it is shorter than the stated length, stating its focus where one is stated, and stating its target load or that no target is stated.
5. The fitdocs CLI shall write in each mesocycle section a table with one row per calendar day of the window, in date order, in which a day with no planned workout is shown as a rest day and a day with several planned workouts has one row per workout in the order the source states them.
6. The fitdocs CLI shall show, for each planned workout's row, the date, the workout's title as a link to its planned page, the one-line summary, and a resolution cell.
7. The fitdocs CLI shall render every planned workout's resolution cell as *unresolved*, and shall render no logged-workout information anywhere on the page.
8. The fitdocs CLI shall write the revision record after the mesocycles: the plan as first written, then each amendment in order with its date, its reason, and each change shown with the superseded value beside its replacement; and shall say plainly when there are no amendments.
9. The fitdocs CLI shall place on the block page exactly one user-owned region, named as the workout document's notes region is, and shall carry that region's content over verbatim whenever it rewrites the page; if the existing page's region markers are damaged, the fitdocs CLI shall report that block as failed and leave the page untouched.
10. The fitdocs CLI shall build every link on the block page as a link relative to the page's own directory, in plain markdown link syntax with no wiki-specific syntax, so that the link resolves in any common renderer and survives a move of the whole data root.
11. The fitdocs CLI shall write the block page as valid markdown that renders in any common renderer, with every table cell on one line and any table-breaking character in a title or summary escaped.

### Requirement 5: One Planned-Workout Page per Row
**Objective:** As an athlete opening tomorrow's session, I want a page of its own for each planned workout with the full prescription, so that the plan is readable session by session and linkable like any other note before any `.fit` file exists.

#### Acceptance Criteria
1. The fitdocs CLI shall write one planned-workout page per planned workout in the current plan, named by the workout's id, in a directory named by the block's identity inside the rendered location, and shall never write a planned page under the generated workout-documents directory.
2. The fitdocs CLI shall give the planned page a frontmatter block carrying the workout's title, its own document type -- distinct from the workout document's, the history page's and the block page's -- the generator, the page's own format version, the block's identity, the workout's id, its mesocycle number, its date, its sport, its modality where stated, and its indoor flag where set.
3. The fitdocs CLI shall write in the planned page's body the title, the date and sport, the one-line summary, a link back to the block page, the prescription verbatim, and a resolution section.
4. The fitdocs CLI shall render every planned page's resolution section as *unresolved*, and shall render no logged-workout information on the page.
5. When an amendment moves a planned workout to another date, the fitdocs CLI shall keep the same planned page at the same path and update its contents.
6. When an amendment removes a planned workout, the fitdocs CLI shall remove that workout's planned page on the next run, provided the page carries fitdocs' provenance marking, and the block page's revision record shall say the workout was removed.
7. The fitdocs CLI shall write no user-owned region on a planned page, and shall rewrite a planned page in full on every run.

### Requirement 6: The Resolution Seam
**Objective:** As the maintainer sequencing the plan-resolution spec after this one, I want the pages to carry a resolution slot whose unresolved rendering is fixed here and whose filled rendering needs no change to the page structure, so that the next spec plugs a value in rather than rewriting the renderer.

#### Acceptance Criteria
1. The fitdocs CLI shall render the block page and every planned page from the parsed block together with one resolution value, and shall use, when no caller supplies one, a default that renders every row as *unresolved*, adds nothing to any mesocycle section, and adds no resolution section to the block page.
2. The fitdocs CLI shall accept a resolution value supplied by a caller in place of the default, and shall render it into the same slots -- the resolution cell of each planned row, a resolution section on each planned page, lines beside each mesocycle's target and after each mesocycle's table, and one resolution section on the block page -- without any other change to the pages' structure.
3. If a supplied resolution value names a workout id or a mesocycle number the block does not have, or supplies a resolution cell containing a line break, the fitdocs CLI shall report it as a failure for that block rather than rendering a malformed page.
4. The fitdocs CLI shall expose the parsed block -- its identity, bounds, goal, mesocycle length, derived mesocycles, the current planned workouts after amendments, the revision trail and the override entries -- in a form the next spec can read without re-parsing the source.

### Requirement 7: A User-Owned Source Location and a New Owned Location in the Data Root
**Objective:** As someone whose wiki fitdocs installs into, I want the plan directory stated as mine and the rendered directory declared and guarded like every other place fitdocs writes, so that the ownership promise stays complete and checkable.

#### Acceptance Criteria
1. The fitdocs CLI shall write block pages and planned pages only into a data-root location that the ownership contract names as fitdocs-owned, declared in the same change that first writes there.
2. The fitdocs CLI shall name the rendered location in the published ownership contract, in an in-tree ownership declaration placed inside it, and in the write-confinement guard's permitted set.
3. The published ownership contract shall state that the plan-source directory is user-owned and read-only to fitdocs, that it is located by the settings key and defaults to a named directory, that it must not lie inside an owned path, and that fitdocs never creates, writes or deletes anything there.
4. The published ownership contract shall state that the rendered location holds two further document types, distinct from the workout document and the history page, declared and versioned by this feature rather than by the document contract, and shall state which region of the block page is user-owned and that the planned page has none.
5. The fitdocs CLI shall advance the published ownership contract version, because a new owned path and new document types change guarantees that document states.
6. The in-tree ownership declaration for the rendered location shall state what the directory holds, that the block page's notes region is the athlete's and carried over, that the planned pages carry no user-owned content, that the pages are re-derivable from the plan sources alone, and that the plan sources are never written by fitdocs.
7. During a plan run, the fitdocs CLI shall create, modify and delete files only inside the owned paths, and shall write no workout document, no history page, no plan source, and neither the athlete profile nor the settings file.
8. If a file at a path the run would write does not carry fitdocs' provenance marking, the fitdocs CLI shall leave that file untouched, shall write nothing for that block, and shall report the path and the block as blocked.
9. If a file inside a block's page directory carries fitdocs' provenance marking but corresponds to no planned workout in the current plan, the fitdocs CLI shall remove it; if it does not carry the marking, the fitdocs CLI shall leave it untouched and report it.
10. If the rendered location holds a block page or a block directory for which no plan source exists, the fitdocs CLI shall leave it untouched and report it as having no source, rather than deleting it.

### Requirement 8: The Command, Its Report, and Determinism
**Objective:** As an athlete, I want one command that renders every block from whatever my plan directory currently says, tells me per block what happened, and produces the same bytes every time, so that the pages are reliable artifacts and never diff noise.

#### Acceptance Criteria
1. When the athlete runs the plan command, the fitdocs CLI shall render every plan source present in the plan-source directory, in a fixed order independent of the filesystem's enumeration order.
2. The fitdocs CLI shall resolve the data root by the same precedence every other command uses and shall fail loudly, with the same guidance, when it cannot.
3. The fitdocs CLI shall read its own configuration from a table in the shared settings file, and if that table is malformed, shall stop with a configuration error naming the settings file and the offending key.
4. With the default (unresolved) resolution, the fitdocs CLI shall produce byte-identical pages for an unchanged source across repeated runs, across different calendar days, and across supported platforms; and nothing under this spec's package shall read a clock: the only dates it uses are the source's own. A resolver a caller supplies may depend on the pass's `today`, resolved outside the package -- `plan-resolution` supplies one -- and with it passed the byte-identity across calendar days holds only for two dates that lie on the same side of every planned row.
5. When a block's rendered pages would be byte-identical to the pages already present, the fitdocs CLI shall write nothing for that block and report it as unchanged.
6. When the run finishes, the fitdocs CLI shall report, per source, one of rendered, unchanged, invalid, blocked or failed, with the pages written and removed for a rendered block, every problem for an invalid block, the blocking path for a blocked block, and the reason for a failed block; and shall report every path in the rendered location with no source.
7. The fitdocs CLI shall write a block's planned pages before its block page, so that a block page never links to a planned page that was not written; and a failure while writing one block shall not prevent the other blocks from being rendered and reported.
8. This spec shall not chain the plan pass: `fitdocs plan` is standalone, and this spec leaves the sync, regeneration, load and history commands unchanged. `plan-resolution` chains the pass after `sync`, `drain` and `regen`, following the load pass, and never after `load`, `history` or `check`; the test that pins this criterion is written knowing that spec re-anchors it.
9. If any source is invalid, any block is blocked, or any page cannot be written or removed, the fitdocs CLI shall exit with the per-file-failure status; a configuration error shall exit with the configuration-error status and write nothing; a run with no plan sources shall exit with success and say so.
10. The fitdocs CLI shall place or refresh the in-tree ownership declarations only on a run that has at least one valid block to render, and shall create no directory otherwise; the declaration for the rendered location is therefore placed by the first run that has a page to write there.

## Amendment 1 (2026-09-17): the two test pins re-anchored, landed by plan-resolution

`plan-resolution` lands the resolver and the chaining criteria 8.4 and 8.8
already admit: 8.4 scopes the byte-identity guarantee to the default
(unresolved) resolution and states that a supplied resolver may depend on
`today`; 8.8 states that this spec does not chain the plan pass and that
`plan-resolution` does. Neither criterion changes meaning here. The two
test pins that spec's design named -- Cross-spec obligations item 5 -- were
re-anchored as it foresaw: `tests/test_cli_plan.py`'s AST pin was re-stated
under `plan-resolution`'s CLI chaining; the `tests/test_plan_e2e.py`
two-dates test's precondition (both fake dates on the same side of every
fixture row) was already present at this spec's own `be6c936`, so
`plan-resolution` added no precondition to it; its one edit to that test is
the staging line described next. Landing the resolver chained also
surfaced a fixture gap this spec's design did not foresee: with the
resolver in place, a plan-source override naming a stem the corpus lacks is
a per-file failure (`plan-resolution` Req 8.7), and `tests/plans/fixtures/
full.toml`'s `w1-mon` override names `run-2026-01-06-am`, a stem no wave-1
CLI corpus provided. Four wave-1 tests -- three further ones and the
two-dates pin itself --
`tests/test_cli_plan.py::test_success_prints_every_outcome_line_and_the_counts`,
`tests/test_plan_e2e.py::test_two_sources_render_every_owned_page_with_report_and_frontmatter`,
`::test_two_plain_runs_are_byte_identical_and_report_unchanged`, and
`::test_two_fake_dates_and_timezones_are_byte_identical` -- now stage that
logged page so the fixture stays coherent under reconciliation; the fixture
itself and every existing assertion are untouched. Separately,
`tests/test_plan_e2e.py`'s two-dates test carries a docstring sentence,
"With the default (unresolved) resolution, `fitdocs plan` reads no clock,"
that is now stale once the resolver is chained -- the test's own docstring
already says it was written knowing it moves, and it is left unedited here,
outside this amendment's scope. Nothing in this requirements document is
renumbered and no criterion's text is reworded.
