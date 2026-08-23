---
id: 2026-08-18-liveness-era-branch-is-unexercisable
title: The source-liveness test's post-replacement branch is unreachable from a pre-replacement repository
status: done
importance: medium
importance_why: Task 7.2's own observable claims the liveness test reports a named skip post-replacement; nothing in the suite can drive that branch, so 8.3 must check it by hand.
effort: S
kind: gap
area: encumbered-content-purge, tests/test_forbidden_strings_source.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 review rounds 2 and 3)
pinned_at: c3d2201
resume_command: "do: at task 8.3, verify by hand that the source-liveness test reports its named post-replacement skip on the replaced repository, and record the observation -- no suite test can drive that branch"
context:
  - tests/test_forbidden_strings_source.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`test_forbidden_string_source_is_live_when_supplied` hardcodes `_repo_root()`,
so its era branch can only ever be driven against this repository -- which is
pre-replacement. The post-replacement branch, which reports a named skip, is
not reachable from any test.

Relatedly, nothing asserts that *this* repository currently reads
pre-replacement. Such an assertion would be era-dependent and must flip at
task 8.2, which is presumably why it was omitted.

## Why it matters

Task 7.2's stated observable is: "with the source supplied against a tree
whose era signal reads post-replacement, the liveness test reports a named
skip". No standing test backs that half. The era *signal* is well pinned --
15 fixtures, every loosening reds -- but the *posture* the signal selects is
not.

The consequence is bounded and known rather than dangerous: the branch first
executes at task 8.3, so 8.3 should verify it by inspection and record the
result.

## Evidence

Reported by two independent reviewers during task 7.2, the second measuring
it directly: replacing the branch's `pytest.skip(...)` with a silent `return`
leaves the module green, and replacing `if _is_post_replacement_era(repo_root):`
with `if False and ...` -- deleting the named skip *and* the paired hard-failure
assertion outright -- also leaves it green.

Confirmed at `dac1a7a`: `_repo_root()` is called at
`tests/test_forbidden_strings_source.py:325` and `:337`; the era-dependent
assertions live in the same function.

## How to pick it up

Two options, and the first is probably right. (a) At task 8.3, run the suite
with the source supplied on the replaced repository and record that the
liveness test reports its named post-replacement skip -- 8.3's task text
already says a failure from it is validation red. (b) Parametrise the
function's repo root so a synthetic post-replacement fixture can drive it.
Done means either the observation is recorded at 8.3, or a fixture exercises
the branch.

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.
