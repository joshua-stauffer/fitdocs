---
name: kiro-review
description: Review a task implementation against approved specs, task boundaries, and verification evidence. Use after an implementer finishes a task, after remediation, or before accepting a task as complete.
allowed-tools: Read, Bash, Grep, Glob
argument-hint: <task-id>
---

# kiro-review

## Overview

This skill performs task-local adversarial review. It verifies that the implementation is real, complete, bounded, aligned with approved requirements and design, and supported by mechanical verification evidence.

Boundary terminology continuity:
- discovery identifies `Boundary Candidates`
- design fixes `Boundary Commitments`
- tasks constrain execution with `_Boundary:_`
- review rejects concrete `Boundary Violations`

## When to Use

- After an implementer reports `READY_FOR_REVIEW`
- After remediation for a rejected review
- Before marking a task `[x]`
- Before accepting a task into feature-level validation

Do not use this skill to invent missing requirements or silently reinterpret the spec.

## Inputs

Provide:
- Task ID and exact task text from `tasks.md`
- Relevant requirement section numbers
- Relevant design section numbers
- Spec file paths (`requirements.md`, `design.md`, optionally `tasks.md`)
- The implementer's status report
- The task `_Boundary:_` scope constraints
- Validation commands discovered by the controller
- Relevant steering excerpts when applicable
- Relevant `## Implementation Notes` entries when applicable

## Outputs

Return one of:
- `APPROVED`
- `REJECTED`

Also return:
- Mechanical results
- Findings with severity
- Required remediation
- One-sentence summary

Use the language specified in `spec.json`.

## First Action

Run `git diff` to inspect the actual code changes. If the diff is large or ambiguous, read the changed files directly. Do not trust the implementer report as source of truth.

## Core Principle

Read the spec yourself. Read the diff yourself. Verify mechanically where possible. Reject on concrete failures rather than interpretive optimism.
The main review question is not just "does it work?" but "does it stay inside the approved responsibility boundary without hiding new coupling?"

## Mechanical Checks

Run these checks and use the result as primary signal.

### 1. Regression Safety
- Run the project's canonical test suite using the validation commands discovered by the controller.
- If tests fail, reject.

### 2. No Residual Placeholder Markers
- Check changed files for `TBD`, `TODO`, `FIXME`, `HACK`, `XXX`.
- Reject if new placeholder markers were introduced without explicit task justification.

### 3. No Hardcoded Secrets
- Check changed files for hardcoded secrets or credentials.
- Reject if concrete secret patterns are introduced.

### 4. Boundary Respect
- Compare changed files against the task `_Boundary:_` scope.
- Reject if the change spills outside the approved boundary without explicit justification.
- Reject if the implementation introduces hidden cross-boundary coordination inside what should be a local task.

### 5. RED Phase Evidence
- For behavioral tasks, verify that the implementer status report includes `RED_PHASE_OUTPUT`.
- Reject if RED evidence is missing, empty, or unrelated to the task's acceptance criteria.

### 5.5 Fixture Discrimination

Applies whenever the diff changes tests. **Green is not evidence; the mutation is
the evidence.** A passing suite proves the assertions ran, not that they could
have failed. Thirteen assertions that could not fail under any implementation
landed in one day across three specs — every one with correct production code,
every one surviving review by reading, every one found only by mutation. Every
late catch came from a reviewer exceeding its mandate; that is now the mandate.

- Reject if the diff changes tests and the implementer's `DISCRIMINATION` is
  missing or empty.
- Re-run every mutation the report claims: apply it, run the suite, confirm the
  named test goes red, revert. Reject a claimed mutation that does not red.
- **Design at least two mutations the implementer did not**, more on a test-only
  or guard task, derived from reading the production code rather than from the
  report's table. Never accept an implementer's mutation table as the review — on
  a guard task the reviewer's mutations *are* the deliverable and the
  implementer's are only a claim.
- Reject any mutation you apply that leaves the full suite green, naming the
  mutation and the assertion it defeats.
- Require **sole failure**: the mutation must red the assertion being pinned and
  as little else as possible. A mutation reddening a dozen tests proves the suite
  is alive, not that this assertion discriminates.
- Check each new assertion against the named anti-patterns in
  `.kiro/steering/change-protocol.md` § Fixture Discrimination.
- Run:
  ```
  grep -rniE "verified|caught|proven|tracked|regardless|always|never|impossible|evidence|implicit|outright|immediate|would (have )?(fail|catch|red)|could not (produce|be satisfied)|cannot be satisfied by|nothing else (can|could)" <changed-test-files>
  ```
  against changed test files (`-E` is load-bearing — plain BRE `grep` matches
  nothing here and a real hit reads as clean). Prose claiming discrimination is
  itself untested; re-verify or reject each claim, and confirm any "tracked"
  queue item exists.
- **The grep nets phrasings, not claims — a clean grep is not evidence that
  no false claim remains.** Nine such claims across five tasks and two specs
  used none of the listed words: consequence claims ("so a later rename does
  not fail this suite", "a nested helper cannot hide either") and
  mechanism-justification claims ("this exclusion exists because `|` is a
  union type"), a shape no word list enumerates because an author writes it
  exactly when explaining why the code is shaped as it is, and least likely
  to have re-tested it. Read every factual sentence in a changed test file,
  whether or not it matched, and for any asserting a consequence or a
  mechanism, make it happen and observe — rename the thing, indent the
  arithmetic, call the function and print the field — rather than judging
  whether the sentence reads true.
- On a task listing more than a handful of requirements, sweep exhaustively
  rather than incrementally: classify every listed requirement PINNED /
  PRESERVED-ONLY / UNPINNED yourself. Incremental discovery does not terminate on
  this class — one task was rejected three rounds running, each finding new real
  ground, and closed in one round once swept.
- **Apply and observe every mutation through `uv run pytest`.** Cached bytecode
  is validated on the source's mtime and size, which a same-size mutation
  reverted within the same second leaves unchanged, so the interpreter can run
  code nobody wrote. The root `conftest.py` makes a pytest run cache-proof; a
  bare `uv run python -c` bypasses it. Since a mutation that leaves the suite
  green is a rejection ground, a mutation that silently never applied
  manufactures a false rejection.
- Revert every mutation before writing the verdict and confirm green at the state
  under review.

### 5.6 Remediation Shape (second and later rounds)

- **Converging but incomplete** — each round finds new, real ground. Switch from
  incremental discovery to the exhaustive sweep and bound the remainder.
- **Oscillating** — each fix installs a new blind spot in place of the old one.
  Recommend escalation to a debug subagent; further rounds of the same review
  will not converge.

### 6. Runtime-Sensitive Static Checks
- If the project already has lint or equivalent static analysis for the touched stack, run the relevant command for the task boundary.
- Pay attention to patterns that can survive typecheck/build yet fail at runtime: type-only imports used as values, missing namespace value imports for qualified-name access, unresolved globals, and newly introduced runtime-sensitive dependencies without matching boot/runtime handling.
- If no project lint command exists, perform a targeted diff-based spot check in the changed files for those patterns.
- Reject on concrete findings that create a realistic boot-time or module-load failure.

## Judgment Checks

### 7. Reality Check
- Confirm the implementation is real production code, not a placeholder, stub, fake path, or deferred-work shell.

### 8. Acceptance Criteria Coverage
- Read the task description and confirm all aspects are implemented, not only the primary happy path.

### 9. Requirements Alignment
- Read the referenced sections in `requirements.md`.
- Confirm each requirement is satisfied by concrete observable behavior.
- Use original section numbers only.

### 10. Design Alignment
- Read the referenced sections in `design.md`.
- Confirm the implementation uses the prescribed structures, interfaces, and dependency direction.
- Reject silent substitutions for design-mandated choices.

### 10.5 Boundary Audit
- Compare the implementation against the design's boundary commitments and out-of-boundary statements.
- Reject if downstream-specific behavior is pushed into an upstream boundary for convenience.
- Reject if the implementation creates new hidden dependencies, shared ownership, or undeclared coupling across adjacent boundaries.
- Reject if a task that is not an explicit integration task now behaves like one.

### 11. Test Quality
- Confirm tests prove the required behavior rather than only scaffolding.
- Confirm tests would fail if the implementation were removed or broken. Answer this from check 5.5's mutation results, not from inspection — this item has a mechanical equivalent, so run it.
- Confirm each assertion pins the rule its requirement names rather than a weaker rule that happens to hold over the fixture.

### 12. Error Handling
- Confirm relevant failure paths are handled and not silently swallowed.

## Severity Model

Use:
- `Critical` for broken functionality, invalid verification, data loss, security risk, or major scope violation
- `Important` for required fixes before acceptance
- `Suggestion` for non-blocking improvements
- `FYI` for informational notes

## Stop / Escalate

Escalate instead of papering over the issue when:
- The approved spec is ambiguous in a correctness-critical way
- The design conflicts with what is technically possible
- Required evidence cannot be gathered
- The implementation only works by silently deviating from approved scope
- Boundary ownership cannot be determined cleanly from requirements, design, and task scope

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| “Tests pass, so approve” | Passing tests do not prove spec compliance or boundary respect. |
| “The extra behavior is useful” | Extra behavior outside approved scope is still drift. |
| “The implementer said RED was done” | RED must be evidenced, not asserted. |
| “This gap is small enough to let through” | Real gaps must be rejected or escalated. |
| “The tests are green, so they discriminate” | Green proves they ran. Only a mutation proves they could fail. |
| “The assertions read as meaningful” | Every insensitive assertion on record read as meaningful. Reading is the method that failed. |
| “The implementer's mutation table covers it” | That table is a claim under review, not evidence. Design your own mutations. |
| “The test comment says the mutation was caught” | Prose claiming discrimination is untested. Break it yourself. |
| “The production code is obviously correct” | Correct code behind an insensitive assertion is exactly this defect's signature — nothing stops the next session from breaking it. |
| “Rounds 1–3 each found real problems, so the process is working” | Incremental discovery does not terminate. Switch to the exhaustive sweep. |

## Output Format

```md
## Review Verdict
- VERDICT: APPROVED | REJECTED
- TASK: <task-id>
- MECHANICAL_RESULTS:
  - Tests: PASS | FAIL (command and exit code)
  - TBD/TODO grep: CLEAN | <count> matches
  - Secrets grep: CLEAN | <count> matches
  - Static checks: PASS | FAIL | SPOT_CHECKED
  - Boundary: WITHIN | <files outside boundary>
  - Boundary audit: CLEAN | <spillover / hidden dependency findings>
  - RED phase: VERIFIED | MISSING | N/A
  - Discrimination: <claimed mutations re-run N/N> | <own mutations N, survivors N> | MISSING | N/A (no test changes)
  - Discrimination sweep: <PINNED / PRESERVED-ONLY / UNPINNED counts> | N/A
  - Prose-claim grep: CLEAN | <count re-verified> | <count false>
- FINDINGS:
  1. <specific finding with exact files/spec refs>
- FOLLOW_UPS:
  1. <real problem outside this task's boundary — see below; `none` if none>
- REMEDIATION: <mandatory if REJECTED>
- SUMMARY: <one sentence>
```

## Follow-ups

A review often finds real problems that are not this task's to fix: an
upstream contract defect, an inconsistency in a neighbouring spec, an
unsourced constant, a test that passes for the wrong reason. Rejecting the
task for them is wrong, and dropping them loses them.

Report each in `FOLLOW_UPS` with enough for someone else to act:
`<one-line problem> | evidence: <file:line or command output> | area: <spec or
module> | importance: high|medium|low`.

This is a handoff, not a verdict input — `FOLLOW_UPS` never changes `VERDICT`.
The dispatching orchestrator is responsible for recording them in
`.kiro/queue/`; as a read-only reviewer, do not write the files yourself.
