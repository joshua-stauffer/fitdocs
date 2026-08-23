---
id: 2026-07-26-prior-mutation-evidence-predates-the-cache-fix
title: Every discrimination claim recorded before the bytecode fix was gathered under a hazard that could falsify it
status: open
importance: medium
importance_why: The gate's whole output is claims of the form "mutation X reds test Y" / "X leaves the suite green"; the second form is the one the hazard corrupts into a confident wrong conclusion, and an unknown number of those were recorded before the fix landed.
effort: M
kind: research
area: tooling, .kiro/steering/change-protocol.md, tests/
created: 2026-07-26
surfaced_by: /kiro-queue — implementing 2026-07-26-stale-pyc-can-falsify-mutation-evidence
pinned_at: c3d2201
resume_command: "do: re-verify the subset of recorded discrimination evidence the stale-pyc hazard could have falsified — only claims whose mutation was SAME-SIZE and whose recorded result was 'stayed green' / 'does not discriminate', since that is the direction that yields a wrong conclusion rather than a visible failure. Re-run each under the now-cache-proof pytest and record the outcome [queue: .kiro/queue/2026-07-26-prior-mutation-evidence-predates-the-cache-fix.md]"
context:
  - .kiro/steering/change-protocol.md
  - conftest.py
  - tests/test_bytecode_hygiene.py
  - .kiro/queue/closed/2026-07-26-stale-pyc-can-falsify-mutation-evidence.md
blocked_by: []
---

## What

`e5d7319` closed the stale-bytecode hazard: a same-size mutation reverted
within one filesystem second left CPython running the mutated code, because
`.pyc` validation compares only the source's mtime and size. The fix is
structural and prospective — the root `conftest.py` makes a pytest run
cache-proof from now on.

It says nothing about evidence already recorded. Every `DISCRIMINATION` table
in a task report, every "mutation caught:" docstring, and every queue item
whose Evidence section reports a mutation result was gathered before the fix
existed, under an interpreter that could silently disagree with the tree.

This was explicitly raised as an open question by the parent item and
deliberately not attempted while closing it.

## Why it matters

The two directions are not equally dangerous, and that is what makes this
tractable rather than a full re-audit.

- **"The mutation reddened the test."** Low risk. A stale cache would have made
  the mutation *not* take effect, so the test would have stayed green and the
  claim would never have been written. A recorded red is self-validating.
- **"The mutation left the suite green" / "this clause is UNPINNED."** This is
  the corruptible direction. If the `.pyc` predated the mutation and mtime and
  size collided, the mutation never ran, the suite stayed green for the wrong
  reason, and the conclusion drawn — that the assertion does not discriminate —
  is confident, evidence-backed and wrong. That leads to an UNPINNED
  declaration for a clause that is in fact pinned, or worse, to rewriting a
  working test to chase a mutation that was never applied.

`change-protocol.md` § The completeness half makes UNPINNED declarations a
first-class, acceptable outcome, so these claims are load-bearing: a later
session reads "UNPINNED, verified by mutation" and does not re-check.

## Evidence

The hazard, reproduced at `43dd31b` and again while implementing the fix, on a
tree with an empty `git diff`:

```
$ grep -c "LOAD_PAYLOAD_VERSION: Final\[int\] = 2" src/fitdocs/load/render.py
1                                          # source says 2
$ uv run python -c "from fitdocs.load.render import LOAD_PAYLOAD_VERSION as v; print(v)"
3                                          # interpreter says 3
```

That it is now closed prospectively — `conftest.py` at `e5d7319`, pinned by
`tests/test_bytecode_hygiene.py`, all three lines mutation-verified.

The corpus this item is about, as a starting point rather than a complete list:

```
$ grep -rn "Mutation caught\|stays green\|left the suite green\|UNPINNED" tests/ .kiro/specs/ .kiro/queue/closed/
```

Note the hazard is **intermittent by construction** — it needs same-size *and*
same-second — so most recorded evidence is probably sound. This item is about
bounding "probably", not about distrusting the corpus.

## How to pick it up

1. Read the closed parent item
   (`.kiro/queue/closed/2026-07-26-stale-pyc-can-falsify-mutation-evidence.md`)
   for the mechanism, and `conftest.py` for what is now guaranteed.
2. **Do not re-run everything.** Filter to claims meeting BOTH conditions: the
   mutation was same-size (constant swap, comparison flip, dropping a `not` —
   not deleting a line or a call), AND the recorded result was "green" /
   "survived" / "UNPINNED". Anything recorded as reddening needs no re-check,
   for the reason in **Why it matters**.
3. Re-run each survivor through `uv run pytest`, which is now cache-proof. A
   claim that flips from "green" to "red" was falsified: the clause is pinned
   after all, and whatever was done in response to the false conclusion needs
   revisiting.
4. Record the outcome — including "all N re-checked, none flipped", which is
   the likely result and is worth writing down so this is not re-derived.

Done means: the set of at-risk claims is enumerated and each is either
re-verified or explicitly accepted, and no session has to wonder again whether
pre-`e5d7319` evidence can be trusted.

## Open questions

- Is the `tests/` docstring corpus in scope, or only the spec `tasks.md`
  `DISCRIMINATION` tables and queue Evidence sections? The docstrings are the
  larger set and the ones a future editor actually reads, which argues for
  including them; they are also the least structured to enumerate.

## Resolution

**Re-verified 2026-07-27, branch `chore/mutation-evidence-reverify`, worktree
`../fitdocs-mutation-evidence` (left in place, not merged — see below). Not
closing: that is the human's call, per the resume instructions.**

### Bounding the candidate set

Included the `tests/` docstring corpus (the open question above): a future
editor reads those, not the queue, so excluding them would leave the larger
half unchecked. Search performed on `main` at `80cc5c5` (parent of this
worktree's branch point):

```
$ grep -rln "Mutation caught\|stays green\|left the suite green\|does not discriminate\|UNPINNED\|survived\|stayed green" \
    tests/ .kiro/specs/ .kiro/queue/closed/
```

37 files matched (corrected 2026-07-27 — the original grep `-l` count of 31
was wrong; a re-run of the identical command against the identical corpus
returns 37; the 110 line count was already right), 110 individual lines.
Cutoff commit: `e5d7319`
(2026-07-26 22:52:11+02:00), the conftest fix. For every match, `git blame`
on the exact line established whether it was written before or after that
timestamp — the file having other content post-cutoff does not clear a
pre-cutoff line, so this was done per-line, not per-file.

Two more filters, applied in order, per the queue item's own scoping rule
(claims must be BOTH pre-cutoff AND same-size-mutation-with-a-green/UNPINNED
result):

1. **Timestamp.** Lines written after `e5d7319` are out of scope by
   construction (gathered under the fix already). This removed the two most
   recently touched hits (`tests/load/test_arbitration_e2e.py:955` at
   `1bd4dad`, 23:17:33; `tests/test_plugin_regression.py:298` at `1727b0b`,
   23:23:20 — both ~25-30 minutes *after* the fix landed).
2. **Mechanism.** Of the remaining pre-cutoff hits, most were disqualified by
   what "does not discriminate" actually meant on inspection, not by the
   pyc hazard:
   - Several are **not mutation-testing claims at all**: task-planning prose
     using "survived" to mean "data survived a round-trip" (`athlete-benchmarks
     design.md:1273`, `tasks.md:85`), or "survived code review" (human review,
     not a pytest run — `activity-qa-flags tasks.md:298`).
   - One (`test_docs_guarantees.py:451`, `DECLARED UNPINNED`) is a **mypy
     --strict** claim (Protocol contravariance defeats a parameter-widening
     mutation). **Correction (round 2, see below): the reason given here —
     "mypy has its own `.mypy_cache` keyed differently and was not
     implicated" — is false.** `mypy/build.py::validate_meta` accepts a
     cached module without hashing whenever `int(st.st_mtime) == meta.mtime`
     AND `path == meta.path` — structurally the same mtime+size fast path as
     CPython's `.pyc`, and `conftest.py` does nothing to purge or invalidate
     `.mypy_cache`. This specific claim is still safe, but for a different
     reason: `test_docs_guarantees.py:451` checks a file written fresh to
     `tmp_path` on every run, so `path != meta.path` forces the hash check
     every time regardless of mtime/size. See "Remediation round 2" for the
     full argument and why `.mypy_cache` is a live, un-mitigated instance of
     the same hazard class for any *non*-tmp_path mypy-gated claim.
   - Several recorded mutations were **not same-size**: deleting a whole line
     (`tests/test_cli_check.py:242`'s `finding.detail` print line;
     `2026-07-26-quarantine-sort-sites-masked-by-save.md`'s `.sort(...)` →
     `pass`), deleting a paragraph
     (`2026-07-26-sample-aggregate-postcondition-unpinned.md`), or replacing a
     short name with a longer one
     (`2026-07-26-load-command-no-prompt-forwarding-unpinned.md`'s
     `no_prompt=no_prompt` → `no_prompt=True`/`False`, 9 chars → 4/5). A size
     change is caught by ordinary `.pyc` invalidation regardless of the
     same-second collision, so these were never at risk from this specific
     hazard — noted, not re-run on that basis.
   - `tests/test_public_api.py:476` and `tests/load/test_packaging.py:46`:
     the recorded direction for the *target* assertion is RED (the primary
     "Mutation caught" claim), with "N other tests stayed green" only a
     side observation about sole-failure, not the claim under test. Low-risk
     direction per the queue item's own "Why it matters" — a stale cache
     would have prevented the red, not produced a false one.
   - `tests/test_cli.py:1158`: the "stays green" claim is about a *sibling*
     test's inherent indistinguishability (an up-front and a lazy error both
     leave the same exit code and message) — the `change-protocol.md` named
     anti-pattern **Indistinguishable outcome**, stated as such in the same
     docstring. Not a caching artifact; re-running it would prove nothing the
     text doesn't already say.

That left **2 genuine candidates** meeting both conditions cleanly, plus one
already-remediated item worth a confirmatory spot-check:

| # | Claim | File:line | Pre-cutoff commit | Same-size mutation |
|---|---|---|---|---|
| 1 | Round-1 "that one survived" (`region.payload is not None` was the fix) | `.kiro/specs/training-load/tasks.md:474` / `tests/load/test_migration_e2e.py:406` | `b43cb0d2`, 2026-07-26 09:39 | yes — writer emits a prior-format marker while still reporting the doc as unsupported |
| 2 | "three of four remedies could be blanked with the suite green" (remedy-fragment distinctiveness) | `.kiro/specs/wiki-contract/tasks.md:186` (**corrected — the original row cited `:184`, which is a different line and a different claim; `:184` is now its own candidate, see Remediation round 2**) / `tests/test_cli_check.py:230-238` | `656ca223`, 2026-07-22 16:42 | **Correction: NO, not same-size.** The re-run mutation (`_REMEDY_MOVE_UNMANAGED = _REMEDY_FIX_MARKERS`) deletes the 3-line multi-line-string literal that defined `_REMEDY_MOVE_UNMANAGED` and replaces it with a 1-line alias — a large size change, not a same-size swap. The original "yes" was asserted by narrative, not measured by byte count. The re-run below is still valid evidence (it did not depend on this classification being right), but this candidate was never actually in the hazard's risk class; it is mechanism-excluded like #3, just not yet known to be at the time. |
| 3 (spot-check) | "`finding.detail` print line... left the suite green until these were added" | `tests/test_cli_check.py:242` | `a579ad5`, 2026-07-22 19:55 | not same-size (deletes a whole line) — checked anyway since it's the same test file as #2 |

### Re-verification, under `uv run pytest` (cache-proof)

Baseline on the untouched worktree tree: `1869 passed`.

**#1 — `tests/load/test_migration_e2e.py::test_prior_format_unsupported_docs_nothing_registered_rerender_unsupported`.**
Mutated `src/fitdocs/load/engine.py::_write_unsupported` so a document already
classified `UNSUPPORTED` (any format) is reported into `report.unsupported`
without its body actually being rewritten into the current format — the exact
scenario the docstring names ("a writer emitting the prior-format marker").
Result: **2 failed** (`test_migration_e2e.py`'s own test, sole line
`region.payload is not None` at `:406`; and the sibling
`test_engine.py::test_superseded_unsupported_stamp_still_refills_and_is_then_byte_stable`,
on its own separate byte-stability assertion). Reverted; `1869 passed`.
**Confirmed. Does not flip. The assertion is genuinely pinned now**, and by
extension the round-1 "survived" finding this task's remediation responded to
was a real defect, not a stale-cache artifact.

**#2 — `tests/test_cli_check.py::test_check_reports_every_finding_kind_and_exits_one`.**
Mutated `src/fitdocs/audit.py` to alias `_REMEDY_MOVE_UNMANAGED` to
`_REMEDY_FIX_MARKERS` (collapsing two of the four remedy strings, mirroring
the historical "blanked out" defect). Result: **1 failed**, sole failure, on
`assert "move any content worth keeping" in output` at `:237` exactly.
Reverted; `1869 passed`. **Confirmed. Does not flip.**

**#3 (spot-check, mechanism already excludes it) —** deleted the
`console.print(f"    {finding.detail}", ...)` line in
`src/fitdocs/cli.py::_report_audit`. Result: **1 failed**, sole failure, on
`assert "doc_version is 1, below the current" in output` at `:245`. Reverted;
`1869 passed`. Consistent with the mechanism-based exclusion — this was never
at risk, and it isn't corrupted.

### Disagreements found

**None.** Zero of the candidates flipped from a recorded "stayed green" /
"survived" conclusion to red under a cache-proof re-run. **Correction: "all
three re-verified assertions are sole failures" as originally written here
directly contradicted this round's own #1 result ("Result: 2 failed") two
sections up — that was wrong, not just imprecise.** The accurate statement:
#1's mutation reddened two tests (the named assertion plus a dependent
sibling's separate byte-stability check — still a small, traceable set, not a
suite-wide red); #2 and #3 were each a sole failure. "Disagreement" here means
"flipped from green to red compared to the original recorded conclusion" —
none did, regardless of how many tests any individual re-run reddened.

### What was not checked

- The mechanism-excluded items (non-same-size mutations, mypy-based claims,
  indistinguishable-outcome claims, sibling-test side observations) were read
  and classified but their mutations were **not re-run** — the queue item's
  own scoping rule excludes them, and re-running a mutation that changes file
  size adds no information about the pyc hazard specifically. If a future
  session wants those re-verified anyway (e.g. as ordinary fixture-quality
  spot checks, unrelated to this hazard), they are listed above with file:line.
- The two post-cutoff hits (`test_arbitration_e2e.py:955`,
  `test_plugin_regression.py:298`) were not re-run — they postdate the fix by
  construction and are covered by ordinary cache-proof pytest already.
- Prose elsewhere using "survived"/"stays green" in a sense unrelated to
  mutation testing (round-trip data survival, human code review) was
  identified and excluded but not enumerated exhaustively beyond the three
  instances found — the grep corpus (110 lines, 31 files) was read in full,
  so nothing in that corpus was skipped, only classified out.
- Did **not** re-audit evidence gathered *after* `e5d7319` on the theory that
  it might still be wrong for unrelated reasons — out of this item's scope.

### Bottom line (round 1 — superseded, kept for the record; see Remediation round 2)

13 pre-cutoff hits from the corpus were mechanism-excluded (not same-size, not
a pytest mutation claim, or the red/green direction already low-risk); 2 met
both conditions and were re-verified with a fresh mutation cycle; 1 more was
spot-checked despite being mechanism-excluded. All 3 hold. No evidence in the
repo was found to have been corrupted by the stale-`.pyc` hazard. This
narrows, rather than fully discharges, the parent item's "probably sound"
claim — enough that a later session does not need to re-derive the bounding
argument, but the docstring corpus outside the 110-line grep window (any
claim using different wording than the **seven** grepped terms — not "six":
`Mutation caught`, `stays green`, `left the suite green`,
`does not discriminate`, `UNPINNED`, `survived`, `stayed green`) was not
searched.

**Full accounting of the 110-line corpus, added in round 2 because the above
never named where the other ~92 lines went:** 76 of the 110 lines match
`Mutation caught` (the red/self-validating direction) and were excluded en
masse without per-line mechanism review — that is a deliberate bulk rule, not
an oversight, per the queue item's own "Why it matters": a recorded red is
self-validating regardless of the pyc hazard. Of the remaining 34: 2 are
post-cutoff (`test_arbitration_e2e.py:955`, `test_plugin_regression.py:298`);
of the other 32, the table above accounts for 2 (now corrected to be
mechanism-excluded, not same-size) plus 1 spot-check; a further 4 are
not-same-size mutations disqualified above (`no_prompt=`, two `.sort()` →
`pass` deletions, one paragraph deletion); 2 are sole-failure side
observations (`test_public_api.py:476`, `test_packaging.py:46`); 1 is the
indistinguishable-outcome case (`test_cli.py:1158`); 1 is the mypy claim
(`test_docs_guarantees.py:451`); the remaining ~21 are prose using
"survived"/"stays green" for something other than a live same-size mutation
claim — data or region survival across a round-trip, human code-review
survival, `uv run ruff check . && uv run mypy` boilerplate in a design doc's
Definition-of-Done language, or meta-references to this hazard/the
PINNED-PRESERVED-ONLY-UNPINNED taxonomy itself — read individually in round 2
(see below) and none found to be a live, at-risk claim.

## Remediation round 2 (2026-07-27, same branch/worktree, after adversarial review rejected round 1)

Round 1's central negative claim ("no evidence was corrupted") rested on a
bounding that was unsound in three independent, confirmed ways, plus several
smaller defects. This section fixes the bounding itself and re-derives the
candidate set under it; round 1's text above is corrected in place for
citation/arithmetic slips and kept rather than deleted, since the two new
mutation cycles it ran (#1, #2/#3) are still valid evidence.

### Fix 1 — the same-size filter compared against the wrong baseline

CPython's `.pyc` validates against the source state that produced the
*current* cached bytecode — in a mutation **sweep** (several mutations applied
in sequence, each reverted before the next), that is the *previous mutation*,
not the pristine original. Two mutations can each be size-changing versus the
original yet same-size as *each other*; if applied back-to-back inside one
mtime second, the second one is the one that silently never took effect. The
corrected invariant: **any run of two or more mutations that are the same
size as one another is at risk, regardless of their size relative to the
original.**

The worst on-record instance of this shape is the training-load task 6.3/6.4
finding already in the corpus: ten pairwise row swaps over five printed
summary-bucket counts, every swap byte-identical in size by construction (a
swap never changes total length), with **4 of the 10 recorded GREEN**
(`.kiro/specs/training-load/tasks.md:433-437`,
`.kiro/queue/closed/2026-07-26-tests-that-cannot-fail.md:207-211`, both
pre-cutoff — `1987958a` 2026-07-26 10:16 and `762478b0` 2026-07-26 12:48).
Neither line matched round 1's 7-term grep (the phrase is "left the entire
1840-test suite green", not one of the seven exact strings) — it surfaces
under the broadened vocabulary in Fix 2 below. It is also the evidentiary
basis for the **Tied values** row of `change-protocol.md:189` ("Four of ten
did") — per the task boundary, that row is not touched here; this is a
finding about the underlying measurement, reported for the record.

**Re-run.** The defect was already fixed in response to the original finding:
`tests/load/test_feature_e2e.py::test_report_load_prints_each_bucket_count_distinctly`
now uses pairwise-distinct bucket sizes (1/2/3/4/5) specifically because of
this failure mode (see its own docstring, which names the tied-bucket
end-to-end test above as the one that "could not carry this assertion
alone"). Confirmed by mutation: swapped the `Restored`/`Unsupported` rows in
`cli._report_load` (`src/fitdocs/cli.py`) — same-size by construction, the
exact shape that hid 4 of 10 in the original sweep. **Result: reddens**
(`assert 3 == 2` on the `Restored` count). Reverted; full module green again.
**Does not flip — the current test discriminates the swap. The defect the
original finding named was real and is fixed; nothing in the current tree is
corrupted by it.**

### Fix 2 — the grep vocabulary undercounted

Reviewer-supplied minimum additions folded in: lowercase `unpinned`,
`surviv(e[sd]?|or)`, `still green`, `remains green`, `leaves the .* suite
green`, `insensitive`, `vacuous`, `cannot fail`, `still pass`, `not redden`,
`PRESERVED-ONLY`. One further addition was needed to actually catch the
claims the reviewer named as missing (`test_engine.py:686/1084`,
`test_settings.py:254/313/405`, `test_quarantine.py:73/96`,
`test_docs_guarantees.py:315`, both wiki-contract lines, both training-load
lines, both queue lines): a bare **`suite green`** term. Without it, several
of those lines (e.g. "the rest of the 1850-test suite green") match none of
the reviewer's own eleven additions either — verified by checking each named
line against the vocabulary before adding the term; all 14 match after.

Final vocabulary (18 terms, case-insensitive):
```
Mutation caught|stays? green|left the suite green|does not discriminate|
UNPINNED|surviv(e[sd]?|or)|stayed green|still green|remains green|
leaves the .* suite green|insensitive|vacuous|cannot fail|still pass|
not redden|PRESERVED-ONLY|suite green
```
Counts: **347 lines / 100 files**, versus round 1's 110/37 (corrected count).
This is a larger delta than the reviewer's own illustrative "393/106" figure,
because the exact regex construction differs (the reviewer was demonstrating
undercount, not prescribing a canonical count) — the two numbers are close
enough to confirm the same conclusion: round 1's corpus was a real
undercount, not a rounding difference.

**Triage of the 237-line delta (347 minus the original 110).** Grepping alone
is not classification; most of the delta is single common English words
(`surviv*` alone contributes 159 raw hits, the large majority of them "the
note survives regeneration" / "the region survives a round-trip" — the same
data-survival false-positive class round 1 already named for the
athlete-benchmarks/activity-qa-flags lines, reproduced at scale by the
broader vocabulary). Filtered the 231 pre-cutoff delta lines to the 31 whose
±8/+3-line window also contains "mutat" (a cheap, auditable proxy for "this
paragraph is actually describing a mutation-testing result," not a
substitute for reading each one) and read all 31 by hand. Findings:

- The two candidates already covered in round 1 resurface here with corrected
  citations (Fix 7): `.kiro/specs/wiki-contract/tasks.md:186` (not `:184`).
- `.kiro/specs/wiki-contract/tasks.md:184` itself — round 1 cited this line
  number for candidate #2 but the text actually at `:184` ("Collapsing all
  four unreadable remedies to one shared string survived the suite until each
  cause asserted a distinctive substring") is a **different, never-evaluated
  claim** about `tests/test_audit.py`'s unreadable-cause remedies, not about
  `test_cli_check.py`. Pre-cutoff (`656ca223`, 2026-07-22 16:42, same commit
  as :186). Already remediated in the current tree —
  `tests/test_audit.py:431/458/476/504` assert a distinctive substring per
  cause (`"directory"`, `"symlink"`, `"corrupt"`, `"permission"`). **Re-run:**
  collapsed `_UnreadableCause.DIRECTORY`'s remedy to alias
  `_REMEDY_RESTORE_PERMISSION` in `src/fitdocs/audit.py::_UNREADABLE_REMEDY`
  (mirroring the historical collapse). **Result: reddens**
  (`test_a_directory_named_like_a_document_is_a_finding_not_a_raise`, sole
  failure, `assert "directory" in finding.remedy.lower()`). Reverted; module
  green. **Does not flip.**
- `tests/load/test_arbitration_e2e.py:955` / `.kiro/specs/training-load/
  tasks.md:521` — this is Fix 6's finding; see below rather than repeating it
  here.
- `.kiro/specs/training-load/tasks.md:437`, `.kiro/queue/closed/
  2026-07-26-tests-that-cannot-fail.md:209` — the tied-bucket sweep, Fix 1
  above.
- `.kiro/queue/closed/2026-07-26-loadcalculator-stubs-outside-mypy-scope-
  have-drifted.md:63-64` and `.kiro/queue/closed/2026-07-26-forced-
  calculator-ride-test-passes-for-wrong-reason.md:65-66` — Fix 3's
  whitespace-normalized finds; see below.
- Everything else in the 31 (task 1.1/1.2/1.3 and 4.1 retrospective narrative
  in `tests-that-cannot-fail.md`; `inbox/tasks.md:169`'s own account of
  independently discovering this same stale-pyc hazard in a different spec's
  task 2.2, self-corrected within that round before shipping; `inbox/
  tasks.md:199`'s spy-retargeting lesson; `test_engine.py:421/646`
  (data-survival / superseded-test language, not live claims);
  `test_feature_e2e.py:850`, `test_power.py:193`, `test_audit.py:582`,
  `test_docs_guarantees.py:168/315/382`, `test_route_maps_e2e.py:162`,
  `test_sync_e2e.py:260` (all either red-direction "Mutation caught" or
  data-survival prose); `training-load/tasks.md:530/827` (already-remediated
  narrative, the :827 residue is now closed at `test_engine.py:646-655`,
  itself covered by round 1's #1 re-run since it's the named sibling
  test); `load-channels/design.md:1325` (Definition-of-Done boilerplate, not
  a claim about a specific assertion)) was read and classified as not a live,
  at-risk, unevaluated claim — none required a re-run beyond what is recorded
  above.

### Fix 3 — whitespace-normalized search

Round 1's 7 terms are mostly multi-word; the corpus is hard-wrapped markdown,
so a line-anchored grep cannot see a match split across a line break. Ran the
same terms with internal whitespace normalized to `\s+` against full file
text (not split by line) and diffed against the plain per-line grep. Two
files gain a hit that line-based grep cannot see at all:
- `.kiro/queue/closed/2026-07-26-forced-calculator-ride-test-passes-for-wrong-reason.md:65-66`
  — "this test stays green" split across the line break. Pre-cutoff
  (`943f17cf`, 2026-07-26 03:56). The named mutation
  (`calculator_id=None` at `cli.py:579`) is **not same-size**
  (`calculator_id` → `None`, 13 → 4 chars) — mechanism-excluded, same
  disposition as round 1's other not-same-size cases, just previously
  invisible.
- `.kiro/queue/closed/2026-07-26-loadcalculator-stubs-outside-mypy-scope-have-drifted.md:63-64`
  — "the suite stayed green" split across the line break. Pre-cutoff
  (`e83ac946`, 2026-07-26 17:46). Not a pytest same-size-mutation claim at
  all — it is a mypy-scope-gap narrative ("nothing type-checked them"), the
  same excluded category as the mypy claim in round 1, not the CPython `.pyc`
  hazard this item is scoped to. Mechanism-excluded.

**Corollary — per-line bucketing mis-sorts within the same doubling-up
paragraph.** `tests/load/test_engine.py:684` keys on `Mutation caught` (the
low-risk red bucket) but the sentence's actual reported outcome is two lines
later at `:686` — "leaves the full suite green" (the guard was NOT caught).
Read in full: the described mutation deletes `not recompute and ` (18 chars)
from a boolean guard — not same-size, mechanism-excluded regardless of which
bucket it was filed under, but the bucketing method itself (grep on the
opening phrase, not the paragraph) was wrong and would misfire on a
same-size instance. Same shape at `tests/load/test_settings.py:403/405`,
except there the paragraph's actual claim ("leaving every other test in the
suite green") is the *low-risk* sole-failure side observation already in
round 1's excluded category — so this one was already bucketed to the right
outcome by accident, not by a sound method.

### Fix 4 — case-sensitive `UNPINNED` missed lowercase filenames

19 of 25 files in `.kiro/queue/closed/` matched none of round 1's seven
terms, including three whose filenames literally end in `-unpinned` (lowercase):
`2026-07-26-region-preservation-unpinned-e2e.md`,
`2026-07-26-load-read-before-document-read-unpinned.md`,
`2026-07-26-payload-doc-version-pair-unpinned.md`. All three are now covered
by the case-insensitive vocabulary in Fix 2 and were read in full:
- `region-preservation-unpinned-e2e.md` — the "the suite would stay green"
  language (line 26) describes a *hypothetical*, not-yet-applied mutation
  (re-rendering from archived source instead of `replace_load_region`) used
  to justify writing a new e2e test; not same-size (a large structural
  change), and the item's own Resolution records the fix landed and verified
  against exactly that mutation. Mechanism-excluded.
- `load-read-before-document-read-unpinned.md` — this is Fix 6's finding
  (below).
- `payload-doc-version-pair-unpinned.md` — "proven by a version-21 mutation
  the old form would have passed" is counterfactual language about the
  *pre-fix* assertion (`assert "1" in skip_entry.detail`), already replaced
  by an exact-token assertion in the Resolution. Not a live claim about
  current code.

None of the three required a re-run beyond what Fix 6 already covers.

### Fix 5 — the mypy exclusion's stated reason was false; corrected reason

Verified directly against the installed interpreter:
`.venv/lib/python3.11/site-packages/mypy/build.py::validate_meta` (line
~2124) checks `data_mtime`/existence, then at line 2193 `if size !=
meta.size: ... return None`, then at line 2199 `if mtime != meta.mtime or
path != meta.path:` — **only entering that branch (and thus only hashing) if
mtime or path differ.** If mtime and size and path all match the cached
metadata, mypy accepts the cache **without ever computing or comparing a
hash.** That is structurally the identical mtime+size fast path as CPython's
`.pyc` invalidation that motivated this entire cleanup, and `conftest.py`
purges only `src/**/__pycache__` — it does nothing to `.mypy_cache`, and
`uv run mypy` is a Definition-of-Done gate for every `src/`/`tests/` change
(`change-protocol.md:106`).

Round 1's stated reason ("mypy has its own `.mypy_cache` keyed differently
and was not implicated by `e5d7319`") is corrected in place above. The one
specific claim excluded on this basis, `test_docs_guarantees.py:451`, is
still safe — but for the real reason: the file it checks is written fresh to
a `tmp_path` on every run, so `path` never matches a stale cache entry's
`meta.path`, which forces the hash branch regardless of mtime/size. Any
*other* mypy-gated claim that checks a fixed, non-tmp_path source file would
not have that protection. `conftest.py`'s purge scope is out of this task's
boundary per the SCOPE instructions (queued separately) — this section
records the corrected reasoning only, so a future session does not
generalize the false one.

### Fix 6 — blame the experiment, not the prose

Confirmed instance: `tests/load/test_arbitration_e2e.py:955` blames to
`1bd4dad` (2026-07-26 23:17:33, ~25 min *after* `e5d7319`), which round 1
correctly excluded "by construction" as post-cutoff prose — but the
*experiment* the docstring reports ("The whole suite stayed green under
exactly that move") is the pre-cutoff task-6.1 reviewer's run recorded at
`.kiro/specs/training-load/tasks.md:521` (blame `f4cc20ae`, 2026-07-26
09:15:46 — well before the cutoff) and
`.kiro/queue/closed/2026-07-26-load-read-before-document-read-unpinned.md:31`
("returned 1831 passed at that time... **Not re-measured at 3121bb6**"). The
mutation is a code **move** — relocating the settings-resolution/
`validate_configured` block to sit after `_discover_workout_docs(data_root)`
— which preserves total byte count exactly (same lines, reordered), the
single highest-risk shape for this hazard.

**Re-run.** Reproduced the move in `src/fitdocs/load/engine.py::apply_load`
(bound `_discover_workout_docs(data_root)` to a local before the
settings/`validate_configured` block, iterate over that local instead of
calling discovery inline in the `for`). Ran
`tests/load/test_arbitration_e2e.py::test_malformed_load_table_aborts_before_any_document_is_read`.
**Result: reddens** — `assert reads == []` fails with `['2021-09-07-ride-...md',
'2021-09-07-run-...md', 'AGENTS.md']`, i.e. frontmatter was read before the
malformed-table error was raised, exactly the violation Req 14.6 forbids.
Reverted; `tests/load/test_arbitration_e2e.py` (12 tests) green again.
**Does not flip.** The test that now exists (`1bd4dad`, written *after*
`e5d7319`, so its own apply/observe/revert cycle was already cache-proof when
it was created) correctly closes the gap the pre-cutoff "1831 passed"
measurement found. The pre-cutoff measurement itself was never re-verified
under a cache-proof pytest before now, and this re-run is that verification:
the requirement is genuinely pinned today, not by luck.

**Suite-count dating signal, generalized:** `1831`/`1840`/`1849`/`1852` (and
now, confirmed, `1869`) each identify a specific pre/post state of the suite
independent of when the surrounding prose was committed. Any future
docstring/queue prose reporting one of these counts should be blame-dated by
the count, not the file.

### New candidates admitted and re-run — summary

| Claim | Source | Pre-cutoff commit | Result | Flip? |
|---|---|---|---|---|
| Tied-bucket sweep (row-swap) | `training-load/tasks.md:433-437`, `tests-that-cannot-fail.md:207-211` | `1987958a`/`762478b0`, 2026-07-26 | Mutated `cli._report_load` row order — reddens (`assert 3 == 2`) | No |
| Settings-read-before-discovery move | `training-load/tasks.md:521`, `test_arbitration_e2e.py:955` | `f4cc20ae`, 2026-07-26 09:15 | Mutated `apply_load` to discover before validating — reddens (`reads == []` fails) | No |
| Unreadable-remedy collapse (DIRECTORY→PERMISSION) | `wiki-contract/tasks.md:184` | `656ca223`, 2026-07-22 16:42 | Mutated `_UNREADABLE_REMEDY` — reddens (`"directory" in remedy` fails) | No |

Three new mutation cycles run this round, on top of round 1's three. **Six
mutation cycles total across both rounds; zero flips.** No evidence in the
repo has been found to have been corrupted by the stale-`.pyc` hazard, under
either the original or the corrected bounding.

### What round 2 still does not claim

- The 200 delta lines without "mutat" nearby were read as grep output (file,
  line, matched term) but not individually opened and read in full sentence
  context the way the 31 with "mutat" nearby were — the heuristic is a
  triage aid, not a proof that none of the 200 is a live claim. A future
  session that wants a fully exhaustive read of all 347 lines can start from
  the vocabulary in Fix 2; this round's confidence is bounded by that gap,
  named rather than hidden.
- `.mypy_cache`'s purge scope (Fix 5) is a real, unmitigated gap, queued
  separately per SCOPE — not fixed here.
- `change-protocol.md:189`'s Tied-values row is not edited here per SCOPE —
  the measurement behind it (Fix 1) is now understood to have been gathered
  correctly (four ties recorded green, confirmed genuine, now also confirmed
  fixed), so the row's underlying claim holds; the anti-pattern is sound
  regardless per the reviewer's own note.
