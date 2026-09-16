# Requirements Document

## Project Description (Input)
A block page that lists planned workouts is a plan; a block page that also
says which of them were done, by which logged activity, and how the
mesocycle's actual load compares with its target, is a training record.
`training-blocks` renders the plan and leaves a resolution slot that reads
*unresolved*; this spec fills it. A reconciling pass -- pure over the plan
source as `training-blocks` parses it, the corpus's workout-page frontmatter,
and the settings -- matches logged workouts to planned rows by date and type
under stated rules (the base case, the split session one row absorbs, the
same-day same-type ambiguity that is labelled and never guessed, the
different-day case that is never matched), applies the override entries the
athlete writes in the plan source, sums the actual load logged inside every
mesocycle's window under one methodology with an honest coverage statement,
lists the workouts nobody planned, and places all of it into the seam
`training-blocks` renders. It runs at the end of `sync` (both paths) and
`regen` after the load pass, and as part of `fitdocs plan`; it keeps no state
of its own, so a better-fitting activity logged later replaces an earlier
match with no migration. It adds the contract readers the matched fields
lack, registers a second writing entry point into the rendered location, and
writes nothing into a workout page or the plan source.
Source: `.kiro/specs/plan-resolution/brief.md`; Phase 7 of
`.kiro/steering/roadmap.md`; the seams in
`.kiro/specs/training-blocks/design.md` § "Cross-spec obligations
(training-blocks ↔ plan-resolution)".

## Introduction

`plan-resolution` turns the block page from a statement of intent into a
record. Everything it needs is already in the wiki: every logged workout page
carries its date, sport, modality, indoor flag, start time and, once the load
pass has run, a load value and the methodology it was scored under; every
plan source carries the rows, the mesocycle windows and targets, and the
athlete's own override entries. The reconciler reads both sides, decides per
row, sums per mesocycle, and hands the renderer strings to place. It never
writes the source, never writes a workout page, never opens a `.fit` file and
never asks a question.

The rules are deliberately small and deliberately stated. The base case --
same date, same type -- is what most days are. A track session logged as
three activities is one planned workout absorbing three, and the page says
so. Two runs planned on one day with two runs logged is a case the tool cannot
settle and does not pretend to: it proposes an assignment by start-time order,
labels it ambiguous, and points at the override entry that settles it. A
workout logged on Wednesday that was planned for Tuesday is not matched by
any heuristic, because moving a workout is an amendment to the source, and
the source is the athlete's. Confidence is a closed enumeration whose every
label has one rule, and nothing beyond date and type is ever consulted -- no
distance, no duration, no title -- because a classifier the tool cannot
justify would be worse than an honest "ambiguous".

Absent is `None` throughout: an undated page belongs to no day; an unscored
page makes a mesocycle's sum a lower bound and the page says so; a window with
no scored page shows "not computed", never zero; a mesocycle with no target
gets no comparison; a planned workout dated today or later is "upcoming", not
"missed"; an override that names a page that does not exist is reported, on
the page and in the run report, never dropped. The pass is stateless: every
run recomputes from the current source and corpus, and the only clock it
knows is the `today` the command resolves once and hands in, used solely to
tell "not logged" from "upcoming".

## Boundary Context

- **In scope**: reading the logged-workout corpus through the shared document
  contract, with one contract reader per field the reconciler matches or
  sums and the guard that keeps those readers the only ones; the five row
  states and the three confidence labels with their rules; the split-session
  absorb, the same-day ambiguity proposal and the cross-day non-match;
  applying the plan source's override entries and reporting the ones that
  name a page that does not exist; the per-mesocycle actual-load sum under
  one methodology with exclusions, coverage and lower bounds stated; the
  unplanned-workout listing per mesocycle; the text placed into the block
  page's resolution cells and sections and into each planned page's
  resolution section, with links to the logged pages; running the pass at
  the end of `sync` (explicit source and inbox drain) and `regen` after the
  load pass, and as part of `fitdocs plan`; the run report lines; the
  second writing entry point in the write-confinement guard; the note in the
  published ownership contract that the rendered location has a second
  writer.
- **Out of scope**: any change to what the block page or a planned page *is*
  -- their frontmatter, sections, order, region or types (`training-blocks`);
  the plan-source grammar, including the override entry's syntax
  (`training-blocks`); editing or creating the plan source; writing anything
  into a logged workout page -- a back-link key from a logged page to the
  planned row it fulfilled is a listed candidate and is explicitly **not**
  written by this feature; scoring a logged workout against its prescription
  (pace, distance, duration, structure); sub-sport or interval detection from
  records; forecasting; the packaged skill (`build-training-block`); any
  change to load values, channel arithmetic, calculator selection or the
  history page; chaining after `fitdocs load`, `fitdocs history` or
  `fitdocs check`.
- **Adjacent expectations**: `training-blocks` owns the parsed block, the
  resolution seam and its unresolved default, the rendered location and its
  `plan` entry point, and the pass whose discovery, validation, foreign-file
  rule, atomic writes, stale removal and report this feature reuses
  unchanged by supplying the resolver the pass already accepts. `wiki-contract`
  owns the document contract; this feature adds readers and key constants to
  it for the fields it matches and sums, the way `document_date` was added for
  `athlete-benchmarks`, and publishes nothing new about ownership -- a second
  writer into an already-declared location is a note in the ownership
  document, not a contract-version advance. `training-load` owns the load
  keys and the pass this one runs after; their values are read and summed,
  never computed or altered. `load-history` owns the one-methodology rule and
  its published helpers, which this feature reuses so the block page and the
  history page agree on which methodology a sum is under; its unpublished
  scan is not reached into. `activity-qa-flags` marks pages; a flagged page
  still matches and still counts. `workout-docs` is not changed: no key is
  written into a logged page.
- **Downstream contract**: `build-training-block` teaches the five states,
  the three confidence labels, when the ambiguous label appears and the
  override entry that settles it, and the exact wording of the not-computed,
  lower-bound and not-found statements. A future forecast reads the
  per-mesocycle sums. A future back-link key would be written by this pass.

## Requirements

### Requirement 1: The Logged-Workout Corpus, Read Through the Contract
**Objective:** As an athlete whose plan is reconciled, I want the reconciler to see exactly the workout pages my wiki holds, read the way every other command reads them, so that a page one command recognizes is never invisible to the plan and a field is never read two different ways.

#### Acceptance Criteria
1. The fitdocs CLI shall take as the reconciler's only corpus the generated workout documents at the top level of the workouts directory, recognized by the same test every other scan uses, and shall read no `.fit` file, no network resource and no other directory for it.
2. The fitdocs CLI shall read, per workout document, its recorded date, sport, modality, indoor flag, start time, load value and load methodology through the shared document contract, one reader per field, and the document contract shall be the only place those field names are spelled, so that no consumer can read them another way.
3. If a workout document's date cannot be read, the fitdocs CLI shall treat the document as belonging to no day: it shall match no planned workout, shall count toward no mesocycle, and shall never be given a fabricated date.
4. If a workout document's sport cannot be read, the fitdocs CLI shall treat its type as unknown: it shall match no planned workout, and shall still count toward its day's mesocycle as a logged workout.
5. If a workout document carries no usable load value, or a load value without a methodology beside it, the fitdocs CLI shall treat it as unscored -- never as a load of zero.
6. The fitdocs CLI shall treat a symlink, an unreadable file, a file without frontmatter and a document of another type exactly as every other scan does: skipped, never followed, never reported as a workout.
7. The fitdocs CLI shall not read a workout document's activity-quality flags, and shall not exclude a flagged document from matching or from any sum.

### Requirement 2: Every Planned Workout Resolves to One State
**Objective:** As an athlete reading my block page, I want every planned row to say plainly whether it was done, by which logged workouts, and how sure the tool is, so that the plan is a training record and not a to-do list.

#### Acceptance Criteria
1. The fitdocs CLI shall resolve every planned workout of a valid block to exactly one of five states: matched, overridden, skipped, not logged, upcoming.
2. When one or more logged workouts fulfil a planned workout under the match rules, the fitdocs CLI shall resolve it as matched, naming every fulfilling logged workout and exactly one confidence label.
3. When the plan source's effective override for a planned workout names logged workouts, the fitdocs CLI shall resolve it as overridden; when the effective override marks it skipped, the fitdocs CLI shall resolve it as skipped.
4. While a planned workout's date is earlier than the pass's today, and no logged workout fulfils it, and no override names it, the fitdocs CLI shall resolve it as not logged.
5. While a planned workout's date is the pass's today or later, and no logged workout fulfils it, and no override names it, the fitdocs CLI shall resolve it as upcoming, because a day that has not ended cannot have been missed.
6. The fitdocs CLI shall use the pass's today only to tell not logged from upcoming, and for nothing else.
7. The fitdocs CLI shall never resolve a planned workout by any measure beyond its date and its type -- not distance, duration, pace, title or record content -- and shall label every match with one of a closed set of confidence labels, each with a stated rule.

### Requirement 3: The Match Rules and the Confidence Labels
**Objective:** As an athlete whose real log is messier than the plan, I want the match rules stated so plainly that I can predict them and every label to mean one thing, so that I trust a "matched" and know when to settle a case myself.

#### Acceptance Criteria
1. The fitdocs CLI shall consider a logged workout a candidate for a planned workout only when their dates are equal and their types match: the sports are equal; where the planned workout states a modality, the modalities are equal; where the planned workout states an indoor flag, the logged workout's flag agrees with it, an unrecorded flag agreeing only with `false`; where the planned workout states neither, the logged workout's modality and flag are ignored.
2. The fitdocs CLI shall never match a logged workout to a planned workout dated on another day, however close, because moving a planned workout is an amendment to the plan source.
3. When exactly one candidate exists for a planned workout and no other planned workout on that day competes for it, the fitdocs CLI shall match them with the label exact.
4. When several candidates exist for a planned workout and no other planned workout on that day competes for any of them, the fitdocs CLI shall match all of them to it with the label absorbed and shall state how many it absorbed -- the split session, where a warm-up, a main set and a cool-down are logged as three activities.
5. When two or more planned workouts on one day compete for the same candidates, the fitdocs CLI shall propose an assignment by pairing the competing planned workouts in source order with their candidates in start-time order, shall label every resulting match ambiguous, shall name the competing planned workouts on each of their pages, and shall never present the proposal as settled.
6. When such a competition leaves a planned workout without a candidate, the fitdocs CLI shall resolve it as not logged or upcoming by its date and shall say on its page that its candidates were assigned to other planned workouts by start-time order; when it leaves candidates unassigned, the fitdocs CLI shall list them as unplanned.
7. When a planned workout is resolved as not logged or upcoming, the fitdocs CLI shall list on its page the logged workouts of that day with their sport and, where another planned workout of the block took one, that workout's id, so that the athlete can see what was done instead.
8. The fitdocs CLI shall order the logged workouts named for a matched planned workout by start time, a workout recording no start time last, then by stem.
9. The fitdocs CLI shall use exactly three confidence labels -- exact, absorbed, ambiguous -- under the rules above, and no other.

### Requirement 4: Overrides Win
**Objective:** As the athlete (or the LLM curating my wiki), I want my word in the plan source to be final, so that an ambiguous day is settled once, in the file I already write, and never re-guessed.

#### Acceptance Criteria
1. When the plan source carries one or more overrides for a planned workout, the fitdocs CLI shall apply the latest -- by date, then by position in the source -- and shall let it replace any heuristic result for that planned workout.
2. When an effective override names logged workouts, the fitdocs CLI shall remove those logged workouts from every other planned workout's candidates before matching, and shall count them as planned rather than unplanned in every listing and sum.
3. If an effective override names a logged workout that does not exist in the corpus, the fitdocs CLI shall still resolve the planned workout as overridden by the named logged workouts that do exist, shall mark the missing one as not found on the block page and on the planned page, shall report it in the run report naming the override entry and the stem, and shall never drop it silently.
4. If two effective overrides name the same logged workout for different planned workouts, the fitdocs CLI shall keep it on both, and shall report the conflict naming both override entries and the stem.
5. The fitdocs CLI shall show, on an overridden or skipped planned workout's page, the override's date and its reason where one is stated.
6. The fitdocs CLI shall never write, amend or annotate the plan source, and shall never write into a logged workout page, to record a match, an override or anything else.

### Requirement 5: Stateless and Deterministic
**Objective:** As an athlete who syncs daily, I want a better-fitting activity logged later to replace an earlier match with no migration and no stale record, so that the page is always what the log and the source currently say.

#### Acceptance Criteria
1. The fitdocs CLI shall recompute every resolution from the current plan source and the current corpus on every run, and shall keep no match state between runs in any file, region or key.
2. The fitdocs CLI shall produce byte-identical pages for an unchanged plan source, an unchanged corpus and an unchanged today, across repeated runs and across supported platforms; when only today changes, the pages shall differ only in the planned workouts whose state changes.
3. The fitdocs CLI shall write neither the pass's today nor any run time into any page, so that a day passing without a planned workout crossing it changes no byte.
4. When a logged workout is added, changed or removed between runs, the fitdocs CLI shall reflect it in the next run's resolution with no other action from the athlete.
5. The fitdocs CLI shall read no clock inside the reconciler: today shall be resolved once by the command and handed in.

### Requirement 6: Actual Load per Mesocycle, and the Unplanned Workouts
**Objective:** As an athlete comparing a mesocycle's intent with what my body actually absorbed, I want the sum of the load I actually logged in the window -- planned or not -- beside the target, under one methodology, with its coverage stated honestly, so that a number I read is never a fabricated total.

#### Acceptance Criteria
1. For every mesocycle of a valid block, the fitdocs CLI shall sum the load values of every logged workout dated inside the mesocycle's window, matched or not, and shall show the sum beside the mesocycle's target.
2. The fitdocs CLI shall sum under exactly one methodology per run, chosen by the same rule the history page uses -- the history table's methodology, else the load table's default calculator, else the single methodology the corpus records -- and shall exclude from every sum each logged workout scored under another methodology, stating how many were excluded and under what.
3. The fitdocs CLI shall state coverage beside every sum as the number of scored logged workouts of the number considered in the window, and where any considered workout is unscored shall present the sum as a lower bound and say so.
4. If no considered logged workout in a window is scored, the fitdocs CLI shall show the sum as not computed, never as zero.
5. Where a mesocycle has a target and its sum is complete, the fitdocs CLI shall show the sum as a percentage of the target; where the sum is a lower bound, as at least that percentage; where the mesocycle has no target, the fitdocs CLI shall say so and make no comparison.
6. If no single methodology can be chosen -- none configured and none or several recorded -- the fitdocs CLI shall show every mesocycle's sum as not computed, shall state the reason once on the block page and once in the run report, shall still resolve every planned workout, and shall not stop the run for it.
7. The fitdocs CLI shall list under every mesocycle the logged workouts dated in its window that no planned workout of that block claims, each with a link, its date, its sport and its load or the word unscored, so that the sum's composition is visible.
8. The fitdocs CLI shall never compute, alter or re-derive a load value; it shall only read and sum what the pages record.

### Requirement 7: Placement on the Pages
**Objective:** As an athlete reading the block page in my wiki, I want every resolution visible where the plan is, with links to the logged pages, so that one page tells the whole story.

#### Acceptance Criteria
1. The fitdocs CLI shall show each planned workout's state in the resolution cell of its row on the block page, on one line, naming the state, the confidence label where there is one, and, for matched and overridden rows, a link to every fulfilling logged workout page.
2. The fitdocs CLI shall show each planned workout's state on its own page under the resolution heading, with the label's rule stated in a sentence, a link to every fulfilling logged page with that page's sport, start time and load or unscored, and the details Requirements 3 and 4 require.
3. The fitdocs CLI shall show each mesocycle's actual load, coverage and comparison on one line beside its target, and its unplanned workouts after its day table.
4. The fitdocs CLI shall add a resolution section to the block page stating the count of planned workouts per state, the methodology chosen and how it was chosen, every problem the run reports for that block, and the ambiguous planned workouts left to settle.
5. The fitdocs CLI shall build every link to a logged workout page as a relative markdown link from the page it sits on -- one directory up from the block page, two from a planned page -- and shall emit no wiki syntax.
6. The fitdocs CLI shall place its text only through the resolution seam the block renderer accepts, and shall change nothing else about the block page or the planned pages.
7. The fitdocs CLI shall use a fixed vocabulary for the five states, the three labels and the not-computed, lower-bound, no-target and not-found wordings, so that the packaged skill and a reader can rely on them.

### Requirement 8: Chaining, the Command, the Report and Confinement
**Objective:** As an athlete, I want the plan reconciled whenever my log changes and on demand, with a report that tells me what to settle, so that I never wonder whether the page is current.

#### Acceptance Criteria
1. When `fitdocs sync` has finished ingesting -- from an explicit source or by draining the inbox -- and its load pass has run, the fitdocs CLI shall run the reconciling pass over the data root; when `fitdocs regen` has finished rebuilding and its load pass has run, the fitdocs CLI shall run the reconciling pass likewise.
2. When the athlete runs `fitdocs plan`, the fitdocs CLI shall run the same reconciling pass, so that the pages it renders carry a resolution rather than the unresolved default.
3. The fitdocs CLI shall not run the reconciling pass as part of `fitdocs load`, `fitdocs history` or `fitdocs check`.
4. The fitdocs CLI shall never prompt during the reconciling pass, and shall open no `.fit` file for it.
5. While no plan-source directory is configured and the default one does not exist, a reconciling pass chained after `sync` or `regen` shall write nothing and print nothing, so that an athlete without a plan sees no change to those commands' output.
6. When the reconciling pass finishes, the fitdocs CLI shall report, per reconciled block and after the plan pass's own line for it, the count of planned workouts per state, the ambiguous planned workouts, every mesocycle's actual load and coverage, the count of unplanned workouts, and every problem -- a missing or conflicting override stem -- naming the override entry and the stem; and shall report once which methodology was chosen or why none could be.
7. If any block reports a problem, or the plan pass reports an invalid, blocked or failed block, the fitdocs CLI shall exit with the per-file-failure status; if the plans, history or load settings table is malformed, the fitdocs CLI shall exit with the configuration-error status; otherwise the exit status shall be the command's own.
8. During the reconciling pass, the fitdocs CLI shall create, modify and delete files only inside the rendered blocks location, shall write no workout document, no history page and no plan source, and shall write neither the athlete profile nor the settings file; and the pass shall be registered as a writing entry point of its own in the write-confinement guard.
9. The fitdocs CLI shall run the reconciling pass with the plan pass's discovery, validation, foreign-file rule, atomic writes, stale removal, byte comparison and report unchanged, so that a block that fails validation is left exactly as `fitdocs plan` would leave it.
