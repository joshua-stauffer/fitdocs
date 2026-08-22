---
id: 2026-07-26-tests-that-cannot-fail
title: Make fixture discrimination an explicit gate — six tests this session passed but could not fail
status: done
importance: high
importance_why: Six instances across two specs and two independent sessions in one day; every one passed review-by-reading and was caught only by mutation, so the current protocol detects them by luck of reviewer diligence rather than by rule.
effort: M
kind: gap
area: .claude/skills/kiro-impl, .claude/skills/kiro-review, .kiro/steering/change-protocol.md
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks and /kiro-impl load-channels (six reviewer findings across tasks 1.1, 1.2, 1.3)
pinned_at: fcc3452
resume_command: "do: add a fixture-discrimination gate to the implementer and reviewer templates so a task cannot report done without naming the mutation each new assertion dies on [queue: .kiro/queue/2026-07-26-tests-that-cannot-fail.md]"
context:
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .claude/skills/kiro-impl/templates/reviewer-prompt.md
  - .claude/skills/kiro-review/SKILL.md
  - .claude/skills/kiro-verify-completion/SKILL.md
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

Six times in one session, across two specs and two independent agent sessions,
a task was submitted with a green suite, correct production code, and at least
one assertion that **could not fail under any implementation**. Not one was a
logic error. Every one survived reading and was caught only because a reviewer
ran a targeted mutation.

The instances, all verified by mutation:

1. `load-channels` 1.1 — `assert not hasattr(Divergence, "key")`. A dataclass
   field without a default is an annotation, never a class attribute, so this
   is `False` whether or not the field exists. Req 8.8 pinned nothing.
2. `load-channels` 1.1 — `assert module is not None` and
   `assert not hasattr(sources, "compute")`. Neither can fail.
3. `athlete-benchmarks` 1.2 — the serializer's ascending-sort test supplied
   entries **already sorted**; deleting `sorted()` left all 36 green (Req 6.6).
4. `athlete-benchmarks` 1.2 — the int-storage test supplied `{"value": 190}`,
   already an `int`; deleting `int(numeric)` left all 1793 green.
5. `athlete-benchmarks` 1.3 — no fixture placed two `BenchmarkKind`s in one
   scope, so deleting the quantity filter left all 52 green. An `FTP_WATTS`
   query then returned a 170 bpm heart rate.
6. `athlete-benchmarks` 1.3 — every latest-wins fixture had value and date both
   ascending, so `max(key=measured_on)` and `max(key=value)` are
   indistinguishable. Req 3.2 says *latest date*; the tests equally admit
   "largest number".

A concurrent session hit the same class independently: its log records
`training-load` task 4.1 rejected with "3 of 10 bullets deletable with full
suite green; production code correct".

Two further sub-patterns worth naming, both observed:

- **Remediation can trade one blind spot for another.** Fixing 1.3's
  athlete-wide decoy by swapping it for a kind-defeated decoy removed the only
  coverage of the rule the test is *named* for. The round-2 mutation then
  passed.
- **Prose comments claiming discrimination are themselves untested.** Two
  fixture header comments asserted "returning the first-seen entry fails this
  test" when it demonstrably passed. A false claim in a test comment is worse
  than none — it tells the next editor the coverage exists.

## Why it matters

`CLAUDE.md` already says prose that instructs an agent is behavior. A test that
cannot fail is the same defect one level down: it is an *assertion* that
instructs future sessions the behavior is pinned, while pinning nothing. It is
strictly worse than a missing test, because a missing test is visible in
coverage and an insensitive one reads as done.

The current protocol catches these only when a reviewer independently invents
the right mutation. That happened here — the 1.3 reviewer went beyond its
mandated four mutations to twenty and found the two that mattered — but it
happened because that reviewer was thorough, not because anything required it.
Both `kiro-review` and the implementer template ask for "meaningful assertions"
and "tests that would fail if the implementation broke"; neither requires
naming the mutation, so the check degrades to a judgment call under time
pressure.

The cost is already measurable: three of the four task submissions in this
session were rejected on this class alone, each costing a remediation round and
a re-review. `athlete-benchmarks` 1.3 took three rounds. That is a protocol
efficiency problem, not just a quality one.

## Evidence

- `tests/load/channels/test_sources.py` and `tests/test_benchmarks.py` — the
  round-1 forms of each test named above (see git history at `0dc3be2` and
  `e50522c`).
- Task 1.1 round-2 reviewer: 24 mutants run, all caught after remediation;
  round 1's `hasattr` assertion proven vacuous by adding a real `key` field and
  observing the whole module still pass.
- Task 1.2 round-2 reviewer: "deleting `sorted(...)` at line 319 leaves all 36
  tests passing"; round-3: "`return raw` in place of `return int(numeric)`
  leaves the entire 1793-test suite green".
- Task 1.3 round-1 reviewer: 11 mutations, 2 survived — `if entry.kind is kind`
  → `if True` returned `lthr_bpm 170` for an `FTP_WATTS` query with 52 tests
  green.
- Task 1.3 round-2 reviewer: 20 mutations, 2 survived —
  `max(key=entry.value)` and an added `or entry.discipline is None` fallback
  each passed all 1810 tests.
- Peer session log, `.git/agent-log` 2026-07-25T23:59:20Z: "task 4.1 REJECTED
  round 1: 3 of 10 bullets deletable with full suite green".

### Added 2026-07-26 by `/kiro-impl training-load` — seven more, in a third spec

Task 4.1 (`1b40c02`) was rejected **three times**, all on this species, seven
clauses in total, with the production code traced correct in every round. This
raises the session total to **13 instances across three specs and three
independent sessions**, which is the strongest argument in this item: it is not
one implementer's habit.

Every one had the same shape — **the scenario was unreachable, so the assertion
never ran against the behavior it named.** None was a wrong assertion:

- Three of four stubs in `tests/load/conftest.py` self-guard their modality
  inside `compute`, so the calculator's own defence-in-depth *shadows the engine's
  support gate*: deleting the gate, or moving it after field collection, left all
  1801 tests green.
- The only two-calculator tests registered two calculators that **both** support
  the activity, so the substitutable state Req 10.5 forbids was never reached — a
  mutation silently substituting another supporter passed all 1806.
- Every `recompute=True` in the suite drove a COMPUTED or FOREIGN region, so the
  SUPERSEDED passthrough was never exercised; dropping `not recompute and` passed
  all 1806.
- A malformed-config test that owns a document cannot distinguish an up-front
  abort from a lazy one — both leave the bytes unchanged — so deferring the error
  into the document loop passed all 1804.

**The methodological finding, which belongs in the fix.** Incremental review
could not terminate this: rounds 1-3 found 3, then 2, then 2 more, each round
correct and each finding *new* ground, on a task listing 23 requirements. What
terminated it was an **exhaustive sweep** — the fourth review enumerated all 23
listed requirements and classified each as PINNED (naming the test),
PRESERVED-ONLY (naming the regression test), or UNPINNED (naming the mutation
run). That bounded the remainder at two and closed it in one round. A
per-finding gate alone would not have converged here; the gate needs a
*completeness* half.

Second methodological finding: **require each new pin to be the SOLE failure
under its mutation.** That is what separated genuine pins from tests reddening
for unrelated reasons — one candidate mutation reddened 13 tests and pinned
nothing specific.

Third: converging-but-incomplete and **oscillating** need different responses.
This spec's remediation converged and was correctly swept; the peer's
`athlete-benchmarks` task 1.3 oscillated (each fix installing a new confound)
and was correctly escalated to a debug subagent. A gate that cannot tell these
apart will either loop or escalate too early.

## How to pick it up

1. Read `.claude/skills/kiro-impl/templates/implementer-prompt.md` § Step 5
   (Self-Review) and `.claude/skills/kiro-review/SKILL.md`'s test-quality check.
   Both currently ask for judgment ("assertions are meaningful") where a
   mechanical rule is available.
2. Add a **fixture-discrimination gate** to the implementer template: for each
   new assertion, name the single-line mutation it dies on, run it, and record
   the failing test name in `RED_PHASE_OUTPUT`. An assertion whose mutation
   cannot be named is not done. This is the check that would have caught all
   six instances, and it costs the implementer one edit-run-revert cycle per
   assertion rather than a full rejection round.
3. Add the corresponding reviewer duty: re-run the implementer's claimed
   mutations *and invent at least two the implementer did not*. Every instance
   above that was caught late was caught by a reviewer exceeding its mandate;
   make that the mandate.
4. Add a named anti-pattern list to whichever doc is authoritative (candidate:
   a short section in `change-protocol.md` under validation, since it applies
   to every change class that ships tests): confounded fixtures (two orderings
   that co-vary), pre-satisfied fixtures (input already in the asserted state),
   `hasattr` on dataclass fields, and rejection cases that a second rule also
   rejects.
5. Done looks like: a task that ships an insensitive assertion is rejected by
   rule rather than by reviewer initiative, and the templates say so in words an
   implementer cannot read past.

## Open questions

- Should the gate apply to every new assertion, or only to assertions that pin
  a numbered requirement? Every-assertion is simpler to state and enforce;
  requirement-only is cheaper but needs a mapping the implementer must not get
  to choose.
- Is `kiro-verify-completion` the better home for the gate than the implementer
  template? It already exists to block success claims without fresh evidence,
  and "the mutation I ran and the test that died" is exactly fresh evidence.


---

## Update 2026-07-26 (training-load group 6, tasks 6.1-6.4, at 3121bb6)

Group 6 was four validation tasks whose entire deliverable was tests. Reviewers
ran roughly **70 independent mutations** and rejected **four of six**
submissions — every rejection on a test that could not fail, never on wrong
production code. The instances are all now fixed; what is durable is the
**taxonomy**, which is wider than this item previously recorded. Six distinct
shapes, each measured:

1. **A post-condition already true of the fixture's starting state.** A
   re-render was asserted via `classify_load_region(...).state is UNSUPPORTED`,
   but a *prior*-format stamp classifies `UNSUPPORTED` too. Under a mutation
   making the writer emit the old format marker, four sibling tests reddened and
   that one survived. **Rule: before asserting a post-condition, verify it is
   FALSE in the starting state.**
2. **Tied fixture values hide swap mutations.** Five printed summary rows were
   asserted against buckets `1/0/1/0/0`; two rows tie at 1 and three at 0, so
   **4 of the 10 pairwise row swaps left the whole suite green** — including the
   swap over the two buckets the test's own comment called "distinguishable".
   **Rule: any N-to-N mapping needs pairwise-distinct values.**
3. **A label the renderer always emits is not evidence.** `assert "Unsupported"
   in output` matched a row printed on every pass regardless of the report.
   **Rule: assert the count, not the label.**
4. **A spy-and-compare test is self-referential about content.** Comparing
   printed output to a report captured from the same run passes against an
   all-zero report, so a pass that discovered no documents passed. **Rule: assert
   the captured subject is non-trivial before comparing against it.**
5. **`dir(SomeProtocol)` omits annotation-only members.** A "this Protocol
   exposes no per-pass member" guard admitted all three forbidden members spelled
   as plain annotations. Now filed separately as
   `2026-07-26-protocol-purity-guards-miss-annotations`.
6. **Every AST/filesystem-walking guard needs a positive control.** Two guards in
   task 6.4 passed green having scanned **zero files**. Notably: one was rejected
   for it, the fix was applied to that one and **not** to its sibling in the same
   round, and the sibling was then rejected for the identical defect.
   `Path(__file__).parents[N]` is depth-sensitive and goes vacuous silently.
   **Rule: `assert scanned, "the walk is looking at the wrong directory"`.**

Two method findings that matter more than any individual instance:

- **A docstring is not evidence.** Group 6 shipped **three** false claims of the
  form *"Mutation caught: ... verified by hand"*, each on a guard a reviewer then
  broke with the suite staying green, plus one *"tracked as follow-up work"*
  naming a queue item that did not exist. **Grep changed test files for
  `verified|caught|proven|tracked|regardless|always|never|impossible` and re-run
  every surviving claim.**
- **On a guard task, the reviewer's mutations are the deliverable; the
  implementer's are a claim.** In 6.1 the implementer's sweep reported ten clause
  groups PINNED and an independent sweep found two were not. In 6.4 the
  implementer died before reporting and the guards still landed correctly,
  because the reviewer designed its own 20 mutations rather than checking a
  table. **Never let a reviewer accept an implementer's mutation table.**

This strengthens, and does not replace, this item's original proposal: the gate
should require *sole-failure* discrimination evidence, and for any task listing
more than a handful of requirements, an **exhaustive** up-front sweep — task
4.1's four-round rejection loop was terminated by exactly that, after
incremental discovery had failed to tell anyone when it was finished.

---

## Closed 2026-07-26 by `chore/fixture-discrimination`

Landed as the `## Fixture Discrimination` section of
`.kiro/steering/change-protocol.md` (authoritative: the three-step gate, the
three evidence properties, ten named anti-patterns, prose-is-not-evidence, the
exhaustive PINNED / PRESERVED-ONLY / UNPINNED sweep, converging-vs-oscillating),
plus:

- `kiro-impl/templates/implementer-prompt.md` — Step 5 is now a gate with the
  anti-patterns inline and a mandatory `DISCRIMINATION` status field;
  `READY_FOR_REVIEW` with an unnamed or unrun mutation is forbidden by constraint
- `kiro-impl/templates/reviewer-prompt.md` and `kiro-review/SKILL.md` — checks
  5.5/5.6: re-run every claimed mutation, design at least two the implementer did
  not, never accept an implementer's mutation table as the review, sweep instead
  of iterating on multi-requirement tasks, and respond differently to converging
  vs oscillating rounds. Eight new rationalization rows
- `kiro-impl/SKILL.md` — passes the steering section to implementers, mandates
  reviewer-designed mutations, and escalates oscillation at round 2 rather than 3
- `kiro-verify-completion/SKILL.md` — a `TASK` claim resting on green alone is
  `NOT_VERIFIED`
- `tech.md` § Testing — one-line pointer, so the rule is reachable from the
  testing entry point

**Open questions, answered.** The gate applies to *every* new assertion, not only
those pinning a numbered requirement — every-assertion is simpler to state, and a
requirement-only rule needs a mapping the implementer must not get to choose. The
exhaustive requirement sweep is layered on top for multi-requirement tasks, which
is where requirement numbering earns its place. `kiro-verify-completion` is not
the primary home — it fires too late to save a rejection round — but it now
refuses a green-only claim as a backstop.

**Validated by exercising the gate on a real target**, not only by reading: four
mutations run against `src/fitdocs/quarantine.py` at `47ab90c` found two sort
sites deletable with all 1852 tests green, and the mandated prose-claim grep
pointed straight at a docstring asserting the missing coverage. Filed as
`2026-07-26-quarantine-sort-sites-masked-by-save`. The gate found a real defect
the first time it was run.
