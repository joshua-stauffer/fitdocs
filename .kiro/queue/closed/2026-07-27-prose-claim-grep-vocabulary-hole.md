---
id: 2026-07-27-prose-claim-grep-vocabulary-hole
title: The mandated prose-claim grep passed clean on a file whose docstring contradicted its own UNPINNED declaration
status: done
importance: high
importance_why: The grep is the only mechanical check standing between a false claim and a merge, and it has now missed NINE across five tasks and two specs — six of them in a single /kiro-impl fit-ingest run on 2026-07-28, where this species caused most of one task's four review rounds. Raised from medium because the misses are now known to share a grammatical category (consequence and mechanism-justification claims) that no word list can enumerate, so the currently-proposed fix — widening the vocabulary — is known in advance not to close it.
effort: S
kind: gap
area: steering, .kiro/steering/change-protocol.md, .claude/skills/kiro-impl, .claude/skills/kiro-review
created: 2026-07-27
surfaced_by: /kiro-impl athlete-benchmarks (task 6.1 review, round 1)
pinned_at: 1b43caa
resume_command: "do: widen the Fixture Discrimination prose-claim grep vocabulary in .kiro/steering/change-protocol.md and both skill templates, and say plainly that the grep nets phrasings rather than verifying claims [queue: .kiro/queue/2026-07-27-prose-claim-grep-vocabulary-hole.md]"
context:
  - .kiro/steering/change-protocol.md
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .claude/skills/kiro-review/SKILL.md
  - tests/load/test_benchmark_selection_e2e.py
blocked_by: []
---

## What

`.kiro/steering/change-protocol.md` § Fixture Discrimination mandates grepping
changed test files for
`verified|caught|proven|tracked|regardless|always|never|impossible` and
re-running or deleting every surviving claim. Both the `kiro-impl` implementer
template and the `kiro-review` protocol repeat it.

On `athlete-benchmarks` task 6.1 that vocabulary returned **8 hits, all of them
genuinely factual**, while the three claims that were actually false used none of
those words. They said "stand on their own mutation **evidence**", "**implicit**:
`apply_load` above completed without raising", and "**immediate**, loud test
failure". The grep passed clean on a file whose module docstring directly
contradicted the submission's own UNPINNED declaration.

## Why it matters

A false coverage claim is worse than a missing test: it tells the next editor the
behavior is pinned when nothing pins it. The grep is the only mechanical
enforcement in the protocol — everything else is judgment — so a hole in its
vocabulary is a hole in the gate. The failure mode is silent and reads as
success: a clean grep is currently taken as evidence that no false claims remain.

## Why the vocabulary fix alone is not enough

Any fixed word list nets a *known phrasing*, never the truth of a claim. Widening
it closes this instance and not the class. The steering should say so explicitly,
so the grep is understood as a cheap first pass rather than the check itself —
the only real check is re-running or deleting every sentence that asserts what a
test would catch.

## Evidence

- `tests/load/test_benchmark_selection_e2e.py` at the round-1 submission:
  `grep -rniE "verified|caught|proven|tracked|regardless|always|never|impossible"`
  → 8 hits, each independently re-verified true by the round-1 reviewer.
- The same file's three false passages, all rejected: module docstring
  (`:22-24`), the no-prompt comment (`:447-450`), and `_RaisingSession`'s
  docstring (`:223-225`). None matched the mandated pattern.
- Proposed addition, from the reviewer that found the gap:
  `evidence|implicit|outright|immediate|would (have )?(fail|catch|red)`.
- **A third phrasing family, found one task later** — task 6.2 shipped "an
  aborted or short-circuited pass **could not produce** this", which matches
  *neither* the mandated set nor the extension above. Further addition:
  `could not (produce|be satisfied)|cannot be satisfied by|nothing else (can|could)`.
  That two independent widenings were needed within two tasks is itself the
  argument: the enumeration is chasing a generative space. Each round of
  widening closes the instance that prompted it and predicts nothing about the
  next phrasing an author will reach for.

### Six more instances the next day, and what they have in common

`/kiro-impl fit-ingest` (2026-07-28) hit this **six times across three
consecutive tasks**, and the grep returned CLEAN or all-true on every one. This
is no longer a vocabulary gap being chased instance by instance — the misses
share a *grammatical category* the word list cannot express.

Task 8.1 (`tests/test_citation.py`, `src/fitdocs/citation.py`), three rounds:
- a guard docstring claiming *"no module-level arithmetic exists **anywhere in
  the module**"* — falsified by arithmetic inside `if`/`try`/`for`/`return`
- *"Recurses into class/function bodies so a default field value or **a nested
  helper cannot hide either**"* — falsified by `def tss_scale(): return 100.0/3600.0`
- an exclusion set justified as *"all three legitimately use `|` for a union
  type … the identical accommodation"* — the accommodation was never needed,
  because `ast.BitOr` was not in the arithmetic-operator set at all
- three class docstrings asserting, present tense, that `load.channels.sources`
  *"imports and re-exports this enum verbatim"* when it still defined its own

Task 8.2 (`tests/load/channels/test_sources_citation_reexport.py`, `sources.py`):
- a docstring claiming a **top-level** `class` walk when the code uses
  `ast.walk` and visits every descendant (code stricter than documented)
- *"not unused imports"* offered as half the rationale for `as` aliasing, when
  both names are used in the module body and `ruff` reports nothing either way

Task 8.3 (`tests/metrics/test_types.py`, `src/fitdocs/metrics/types.py`):
- *"so a later rename does not fail this suite"* — renaming the enum members
  reds **three tests in that same file**
- *"a caller-supplied member simply threads through `AthleteInputs` and back out
  on `DerivedMetrics`"* — it returns `None`; the threading is task 11
- *"This enumeration carries no values"* — contradicted by the module's own test
  asserting `isinstance(TrimpWeighting.BANISTER_MALE.value, str)`

**The pattern.** Not one of these is a *coverage* claim of the form the grep
hunts ("this is verified/caught/proven"). They are **consequence claims** ("so X
does not happen", "a rename does not fail this suite", "a nested helper cannot
hide either") and **mechanism-justification claims** ("this exclusion exists
because `|`", "the aliases prevent unused-import warnings"). A word list cannot
enumerate those — they are ordinary declarative prose, and the author writes them
precisely when explaining *why* the code is shaped as it is, which is exactly
when they are least likely to re-test the belief.

Note also that three of the nine are the *inverse* error: prose **understating**
what the code does (a stricter walk described as top-level-only). Those are
harmless to correctness and still worth fixing, because a reader who trusts them
will believe a hole exists and route around it.

**What actually caught all six**: a reviewer reading each sentence and, for any
sentence asserting a consequence, *making the consequence happen and observing*
— renaming the members, indenting the arithmetic, calling `compute_metrics` and
printing the field. Not reasoning about the sentence; executing it.

## How to pick it up

1. Read `.kiro/steering/change-protocol.md` § Fixture Discrimination →
   "Prose is not evidence", and the two skill files that restate the grep.
1b. **Consider whether the fix is a rule rather than a longer word list.**
   Nine misses across five tasks and two specs now share one shape: a sentence
   asserting a consequence, written to justify a mechanism. A candidate rule,
   cheap to state and mechanical to apply: *any sentence in a diff that asserts
   what would happen — to a test, a suite, a caller, a later editor — is a claim,
   and is discharged only by making it happen and observing.* That covers every
   instance above, including the ones no vocabulary extension would have netted,
   and it tells the author what to do rather than what to grep for.
2. Widen the vocabulary in all three places (they must not drift apart), and add
   a sentence stating what the grep does and does not establish.
3. Consider whether this belongs in the `change-guard.py` hook as a mechanical
   check rather than an instruction an agent may skip — see
   `2026-07-26-agent-log-unenforced.md` for the same enforcement question.
4. Done looks like: the three 6.1 passages would have been caught by the widened
   pattern, and no skill states the grep as sufficient.

## Resolution

Closed 2026-07-29, merged to `main` as part of `212d046` (branch
`chore/claim-recovery-and-prose-grep`, `--ff-only`, validated after rebase:
2092 passed, all gates clean).

Both halves the item asked for landed, and the item's own diagnosis — that
widening the vocabulary is known in advance *not* to close the hole, because
the misses share a grammatical category no word list can enumerate — was
honoured rather than ignored:

- **The vocabulary was widened** across all four canonical copies
  (`.kiro/steering/change-protocol.md`, `kiro-impl/templates/implementer-prompt.md`,
  `kiro-impl/templates/reviewer-prompt.md`, `kiro-review/SKILL.md`), verified
  byte-identical by hashing the extracted pattern.
- **The limit is now stated in the steering text**: the grep nets *phrasings*,
  not claims; a clean grep is not evidence that no false claims remain; the
  obligation is to read every factual sentence in a changed test file, matched
  or not. That is the actual fix — the widening is marginal.

**A live defect was found and fixed in passing**: three of the four copies
stated the pattern with **no `grep` flags**. Under plain BRE the pattern
matches nothing and exits 1 — which reads as *clean* on a file full of true
positives. All four now carry `grep -rniE`, verified against a constructed
17-line sample (15 matches; the two misses are exactly the consequence and
mechanism-justification shapes the new prose says it cannot net).

**Two stale copies outside the canonical four were swept**:
`.kiro/specs/training-load/tasks.md:417-425`, which sat under a header
reading "binding on any spec that ships a guard" and imperatively instructed
the narrow grep — a live cross-spec instruction, not history — and
`.kiro/specs/athlete-benchmarks/tasks.md:550-563`, which asserted in the
present tense what `change-protocol.md` prescribes. Both are now past-tense
narration pointing at the current pattern.
