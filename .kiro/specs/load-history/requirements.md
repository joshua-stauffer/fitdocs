# Requirements Document

## Project Description (Input)
fitdocs computes a training load per activity and stops. The athlete's archive
holds 2,478 workout pages spanning 2017 to 2026, every one of which already
carries its date and, once a load pass has run, its load value and the
methodology that produced it in its own frontmatter -- so a complete daily load
series is readable from the documents alone, without opening a single `.fit`
file. Nothing aggregates it. The question "what did my fitness look like going
into that marathon, and what did the twelve weeks before it look like" has no
answer inside the wiki, and the roadmap deferred weekly aggregation views from
the first pass onward. Phase 6 lifts that one deferral: this spec assembles the
daily load series from documents, runs the exponentially-weighted
fitness/fatigue recursion of Morton, Fitz-Clarke & Banister (1990) over it with
published seed constants labelled as seeds, and writes **one** longitudinal page
-- an SVG chart of fitness, fatigue and form on a calendar axis with each tagged
race marked, a weekly table, and a coverage statement that refuses to let a
stretch of *not computed* pages read as rest. It also reports how many
criterion performances the archive actually holds, because `performance-model-fit`
is gated on that number. Cycles, blocks and forecasting stay deferred.
Source: `.kiro/specs/load-history/brief.md`; Phase 6 of `.kiro/steering/roadmap.md`.

## Introduction

`load-history` is the first fitdocs feature whose input is *the wiki* rather
than a `.fit` file. Every page a load pass has touched already carries the two
facts this feature needs -- the day it happened and the load it scored -- so the
whole longitudinal view is a read over the data root's own documents. That
constraint is not incidental: it is what keeps the pass fast on a 2,478-page
archive, what makes it byte-deterministic, and what keeps it out of the
calculator's business entirely. This spec reads load values; it never computes,
adjusts, or second-guesses one.

The feature's hard problem is honesty about absence. On the athlete's archive
today, nearly every page reads *not computed*, because prompt-answered
benchmarks are dated today and never apply to the past (the roadmap's wave 0
lands that fix separately, and this spec must be correct whichever semantic
wave 0 chooses). A page with no recorded load is **missing data**; a day inside
the archive's span with no page at all is a **genuine rest day**. On a
fitness curve those two look identical and mean opposite things, so the page
must never let them look identical: the missing ones are counted, stated, and
where they are too many the curve is suppressed rather than drawn through them.
Absent is `None`; it is never a fabricated zero.

The model is the one the primary texts define and every platform draws. The
recursion is Morton, Fitz-Clarke & Banister (1990) equations (4) and (5); form
is fitness minus fatigue. The time constants are configuration whose shipped
defaults are **seed values that were never fitted to anybody**, and the page
says so in those terms, because the reference document is explicit (D5) that
45 d / 15 d are illustrative starting values and that the same paper's own
least-squares fits landed elsewhere. Replacing seeds with the athlete's own
fitted constants is `performance-model-fit`'s job; this spec's obligation is to
leave a seam that accepts a fitted constant set without changing a line of the
recursion, and to report the criterion-point count that decides whether
`performance-model-fit` proceeds at all.

## Boundary Context

- **In scope**: the daily load series assembled from generated workout
  documents; the fitness/fatigue/form recursion with configurable, cited seed
  constants and the stated choice of recursion form; race markers taken from
  the effort tag; the weekly table; the coverage measure, the suppression rule
  and the coverage statement; the criterion-point report; one history document
  and one chart image beside it; the new data-root location they live in,
  together with its ownership declaration, its entry in the published ownership
  contract and in the write-confinement guard, and the contract-version advance
  a new owned path forces; the `fitdocs history` command and the settings table
  it reads.
- **Out of scope**: fitting any constant to the athlete's results
  (`performance-model-fit`); forecasting form at a future date; plan, cycle or
  block documents; per-sport or per-channel split curves; back-links from
  workout pages to the history page; any change to how a single activity is
  scored, to which channel is selected, or to any recorded load value; reading
  `.fit` files; deriving benchmarks or thresholds (`performance-benchmarks`);
  defining or validating the effort-tag vocabulary (`effort-tags`); attaching
  meaning to a fitness, fatigue or form value.
- **Adjacent expectations**: `effort-tags` publishes the user-owned frontmatter
  keys, the closed effort-kind vocabulary and the **one** typed reader for
  them; this feature reads a race marker through that reader and defines no
  second one, treats a malformed tag as a reportable condition on that page and
  never as untagged, and takes a page's date from the document contract's own
  date reader rather than from any tag field. `training-load` owns the load
  keys, the load pass and the wave-0 prompt-date decision; this feature reads
  those keys and is unaffected by which dating semantic wave 0 picks, because a
  page with no recorded load is a counted gap either way. `wiki-contract` owns
  the document contract, the ownership document, the in-tree declaration and
  the contract version; this feature adds one owned location to each and leaves
  every existing guarantee in force. `threshold-load` is relevant only as the
  producer of the loads summed; the calculator's permanent exclusion of
  aggregation is respected, not amended. `performance-benchmarks` adds its own
  command and its own writes to the athlete profile; this feature adds neither.
- **Downstream contract**: `performance-model-fit` consumes this feature's
  daily series and its criterion-point count, and supplies a fitted constant set
  in place of the seeds through the same interface the seeds use.

## Requirements

### Requirement 1: The Daily Load Series, From Documents Alone
**Objective:** As an athlete with a nine-year archive, I want the load already recorded in my pages assembled into a daily series, so that the longitudinal view costs no re-parsing of my `.fit` files and tells the truth about which days it knows about.

#### Acceptance Criteria
1. The fitdocs CLI shall assemble the daily load series exclusively from the data root's generated workout documents, and shall open no `.fit` file, issue no network request, and read no clock while doing so.
2. The fitdocs CLI shall take each contributing page's calendar date from the date the document itself records, and shall not infer a date from a filename, a tag field, or a file timestamp.
3. The fitdocs CLI shall take a page's training load from the load value recorded in that page's frontmatter, together with the methodology recorded alongside it.
4. While a page records no load value, the fitdocs CLI shall treat that page as contributing no load -- never as contributing zero -- whatever the reason the value is absent.
5. When two or more contributing pages share a calendar date, the fitdocs CLI shall sum their loads into that date's total.
6. The fitdocs CLI shall span the series from the earliest to the latest contributing page date inclusive and shall include every calendar date between them, with no date omitted.
7. While a date inside the span carries no workout document at all, the fitdocs CLI shall treat that date's load as a genuine zero and shall keep it distinguishable, in every output, from a date whose pages record no load.
8. Before the earliest page date and after the latest, the fitdocs CLI shall treat the series as absent rather than zero, and shall draw and tabulate nothing there.
9. If a document cannot be read, or its date cannot be read, the fitdocs CLI shall skip that document, name it and the reason in the run report, and continue.
10. If no document in the data root records a usable load, the fitdocs CLI shall say so plainly, shall write no history page, shall leave any existing history page untouched, and shall complete without reporting a failure.

### Requirement 2: The Fitness, Fatigue and Form Model
**Objective:** As a self-coached athlete, I want fitness, fatigue and form computed by the model the primary literature defines, with constants I can see and change, so that I know exactly what the curve is and what it is not.

#### Acceptance Criteria
1. The fitdocs CLI shall compute fitness and fatigue from the daily load series by the exponentially-weighted recursion of Morton, Fitz-Clarke & Banister (1990) equations (4) and (5), advancing exactly one step per calendar day of the span.
2. The fitdocs CLI shall report fitness and fatigue on a daily-average scale obtained by a stated constant rescaling of that recursion's accumulators, and shall name the scale on the page.
3. The fitdocs CLI shall define form as fitness minus fatigue and shall show form on the same scale as the other two series.
4. The fitdocs CLI shall carry every constant of the model as a citation record naming its source, its locator and its verification status, and shall hold no methodologically significant numeric value of the model anywhere but in such a record.
5. The fitdocs CLI shall record the shipped time constants as starting values that were never fitted to any athlete, and shall state that on the page in those terms.
6. The fitdocs CLI shall record its choice between the primary text's exact exponential decay and the reciprocal-of-time-constant approximation used by vendor documentation as a fitdocs choice with its justification, never as an instruction taken from a source.
7. Where the athlete configures different time constants or weighting constants, the fitdocs CLI shall compute the curve with them and shall state on the page which constants produced it and that they are the athlete's, not the shipped ones.
8. If a constant's published locator has not been verified, the fitdocs CLI shall not ship that constant as a citation record; the absence shall withhold only the configuration preset that constant belongs to, and shall not withhold the curve, the page, or any other constant.
9. The fitdocs CLI shall reproduce the primary text's own published worked figures for this recursion when given that text's stated inputs.
10. The fitdocs CLI shall accept a complete constant set supplied by a caller in place of the shipped defaults, with no change to the recursion, and shall label the resulting curve with that set's stated origin.
11. The fitdocs CLI shall attach no interpretation to any fitness, fatigue or form value -- no zones, no readiness verdict, no overload warning, and no recommendation.

### Requirement 3: Honesty About Gaps
**Objective:** As an athlete whose archive has stretches of unscored pages, I want missing data to look like missing data, so that the curve never tells me I rested when in fact fitdocs did not know.

#### Acceptance Criteria
1. The fitdocs CLI shall measure, for the whole archive and for each reported period, how many of that period's pages record a load and how many do not.
2. The fitdocs CLI shall never substitute a zero, an average, an interpolation, a carried-forward value, or any other stand-in for a page whose load is absent.
3. While a period's share of pages recording a load falls below the configured coverage threshold, the fitdocs CLI shall suppress the drawn curve across that period rather than drawing a line the missing data cannot support.
4. The fitdocs CLI shall use a coverage threshold whose shipped default is recorded as a measured choice with the measurement stated, shall let the athlete configure it, and shall state the threshold in force on the page.
5. The fitdocs CLI shall publish a coverage statement on the page giving, for each reported period, the number of pages, the number recording a load, and the number excluded for recording another methodology; and, for the whole archive, those three figures together with the number of documents skipped as unreadable.
6. While a period contains no pages at all, the fitdocs CLI shall treat that period's coverage as complete rather than as zero, because nothing is missing from it.
7. The fitdocs CLI shall continue the recursion across a suppressed period rather than restarting it, and shall state on the page that values following a suppressed period understate fitness and fatigue by whatever load is missing.
8. The fitdocs CLI shall render a suppressed period as a break in the drawn curve, annotated as suppressed, and never as a line joining the values on either side of it.
9. If a page carries a malformed effort tag, the fitdocs CLI shall report that page and each offending field, shall place no marker for it, and shall still count that page's load in the series.
10. Where a skipped document cannot be attributed to a period -- a document whose date is the thing that could not be read belongs to no period at all -- the fitdocs CLI shall report it in the archive-wide figure only and shall show no skipped count against any period, rather than attributing it to a guessed one.

### Requirement 4: One Methodology Per Curve
**Objective:** As an athlete who has changed calculators, I want the curve to sum one methodology and say which, so that loads on incompatible scales are never silently added together.

#### Acceptance Criteria
1. The fitdocs CLI shall sum only the loads recorded under a single methodology and shall name that methodology on the page.
2. When the athlete names a methodology for the run, the fitdocs CLI shall use it; otherwise it shall use the configured default calculator.
3. While no methodology is named and none is configured, and the archive's pages record exactly one methodology, the fitdocs CLI shall use that methodology and shall state on the page that it was inferred from the archive.
4. If no methodology is named and none is configured, and the archive's pages record more than one, the fitdocs CLI shall stop with a configuration error that names every methodology found with its page count and how to choose one, and shall write no page.
5. If the methodology in force is recorded by no page in the archive, the fitdocs CLI shall stop with a configuration error naming it and the methodologies that are present, and shall write no page.
6. The fitdocs CLI shall count pages recording another methodology as excluded, shall name each excluded methodology and its page count in the coverage statement, and shall never add their loads into the series.

### Requirement 5: One Longitudinal Page
**Objective:** As a PKM user, I want a single readable page showing fitness, fatigue and form across the whole archive with my races marked, so that I can see what a race was run off and plan the next block from it.

#### Acceptance Criteria
1. The fitdocs CLI shall write exactly one history document per data root, with exactly one chart image beside it.
2. The fitdocs CLI shall draw fitness, fatigue and form as three visually distinguishable series on one chart whose horizontal axis is the calendar span of the series and whose ticks a reader can read without the tool installed.
3. The fitdocs CLI shall plot all three series against one shared absolute value scale, shall never band-normalise one series against another, and shall show the zero line because form can be negative.
4. When a page is tagged as a race, the fitdocs CLI shall mark that page's date on the chart and shall present the result the tag records alongside the chart, keyed to the marker.
5. Where a tagged race records no result, the fitdocs CLI shall still mark its date and shall present no fabricated result for it.
6. The fitdocs CLI shall write a weekly table with one row per week of the span, giving the week, its total load, its session count, the fitness, fatigue and form at the week's end, and how many of that week's pages record a load.
7. Where a week is suppressed, the fitdocs CLI shall show the suppression in that week's row instead of fitness, fatigue and form values.
8. The fitdocs CLI shall write the page as valid markdown that renders in any common renderer, carrying the generated-document provenance marking and a frontmatter block consistent with the document contract's conventions.
9. The fitdocs CLI shall reference the chart image by a link relative to the history document's own directory, so that moving the whole data root does not break it.
10. The fitdocs CLI shall forecast nothing, shall prescribe nothing, and shall write no plan, cycle or block content on the page.

### Requirement 6: The Criterion-Point Report
**Objective:** As the maintainer deciding whether model fitting is even viable on this archive, I want the page to state how many dated maximal performances it holds, so that the gated fitting spec's requirements can begin from a measured number instead of a guess.

#### Acceptance Criteria
1. The fitdocs CLI shall count the pages carrying a valid effort tag whose kind is a race or a test and which record an official time, and shall state that count on the page as the archive's criterion-point count.
2. The fitdocs CLI shall break the count down by effort kind and shall give the dates of the earliest and latest counted page.
3. The fitdocs CLI shall state how many tagged pages were excluded from the count, grouped by reason, with one stated reason per group.
4. The fitdocs CLI shall publish the criterion-point count in the history page's frontmatter as a machine-readable value, so that a later pass reads it without parsing prose.
5. The fitdocs CLI shall attach no judgement to the count -- no sufficiency verdict, no confidence claim, and no recommendation to fit or not to fit.

### Requirement 7: A New Owned Location In The Data Root
**Objective:** As someone whose wiki fitdocs installs into, I want the new page's location declared and guarded exactly like every other place fitdocs writes, so that the ownership promise stays complete and checkable.

#### Acceptance Criteria
1. The fitdocs CLI shall write the history document and its chart image into a data-root location that the ownership contract names as fitdocs-owned, declared in the same change that first writes there.
2. The fitdocs CLI shall name the new location in the published ownership contract, in an in-tree ownership declaration placed inside it, and in the write-confinement guard's permitted set.
3. The fitdocs CLI shall advance the published ownership contract version, because a new owned path changes a guarantee that document states.
4. During a history run, the fitdocs CLI shall create, modify and delete files only inside the owned paths and the locations the athlete's settings configure.
5. During a history run, the fitdocs CLI shall write no workout document, shall alter no recorded load value, and shall write neither the athlete profile nor the settings file.
6. If a file in the history location was not written by fitdocs, the fitdocs CLI shall leave it untouched and shall report it rather than overwriting it.

### Requirement 8: The Command, Its Settings, And Determinism
**Objective:** As an athlete, I want one command that rebuilds the page from whatever my wiki currently says, producing the same bytes every time, so that the page is a reliable artifact and not a source of diff noise.

#### Acceptance Criteria
1. When the athlete runs the history command, the fitdocs CLI shall regenerate the history document and its chart image from the data root's documents as they currently stand.
2. The fitdocs CLI shall resolve the data root by the same precedence every other command uses and shall fail loudly, with the same guidance, when it cannot.
3. The fitdocs CLI shall read its own configuration from a table in the shared settings file, shall default every key, and shall treat an absent settings file or an absent table as those defaults rather than as an error.
4. If that settings table is malformed, the fitdocs CLI shall stop with a configuration error naming the settings file and the offending key.
5. The fitdocs CLI shall produce byte-identical output for an unchanged data root across repeated runs, across different calendar days, and across supported platforms.
6. When the run finishes, the fitdocs CLI shall report what it wrote, how many documents it read, how many contributed, how many were excluded and why, and every document it skipped with the reason.
7. The fitdocs CLI shall not run the history pass as part of the sync, regeneration or training-load passes.
8. If the history document or its chart cannot be written, the fitdocs CLI shall report a failure and exit with a failure status; suppressed periods, excluded pages and skipped documents shall not on their own make the run a failure.
