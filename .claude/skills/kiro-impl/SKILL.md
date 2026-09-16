---
name: kiro-impl
description: Implement approved tasks using TDD with native subagent dispatch. Runs all pending tasks autonomously or selected tasks manually.
disable-model-invocation: true
allowed-tools: Read, Write, Edit, MultiEdit, Bash, Glob, Grep, Agent, WebSearch, WebFetch
argument-hint: <feature-name> [task-numbers]
---

# kiro-impl Skill

## Role
You operate in two modes:
- **Autonomous mode** (no task numbers): Dispatch a fresh subagent per task, with independent review after each
- **Manual mode** (task numbers provided): Execute selected tasks directly in the main context

## Core Mission
- **Success Criteria**:
  - All tests written before implementation code
  - Code passes all tests with no regressions
  - Tasks marked as completed in tasks.md
  - Implementation aligns with design and requirements
  - Independent reviewer approves each task before completion

## Execution Steps

**Queue directive**: if the arguments contain `[queue: <path>]`, read that file first and scope this run to that item. Its `What`, `Evidence` and `How to pick it up` are the brief, its `context` paths are the reading list, and the text trailing the directive is the one-line intent. Do **not** treat the run as a full regeneration of the named feature unless the item asks for one, and do not let the directive text be parsed as a feature name — the feature is the first token only. Name the item you addressed in your report, and if the work is finished say so, so it can be closed with `/kiro-queue close <id>`. Contract: `.kiro/queue/README.md`.

### Step 1: Gather Context

If steering/spec context is already available from conversation, skip redundant file reads.
Otherwise, load all necessary context:
- `.kiro/specs/{feature}/spec.json`, `requirements.md`, `design.md`, `tasks.md`
- Core steering context: `product.md`, `tech.md`, `structure.md`
- Additional steering files only when directly relevant to the selected task's boundary, runtime prerequisites, integrations, domain rules, security/performance constraints, or team conventions that affect implementation or validation
- Relevant local agent skills or playbooks only when they clearly match the task's host environment or use case; read the specific artifact(s) you need, not entire directories

#### Parallel Research

The following research areas are independent and can be executed in parallel:
1. **Spec context loading**: spec.json, requirements.md, design.md, tasks.md
2. **Steering, playbooks, & patterns**: Core steering, task-relevant extra steering, matching local agent skills/playbooks, and existing code patterns

After all parallel research completes, synthesize implementation brief before starting.

#### Preflight

**Read the shared log, then claim the spec** (do this first — it decides whether the rest of preflight is even the right work):
- `cat "$(git rev-parse --git-common-dir)/agent-log"`. This is the only way to learn that peer sessions exist; your own worktree will never show you. Look for: a live `CLAIM` on this spec — if one is held, do not take it; pick another spec or stop and report, unless the claiming session itself already closed it (`MERGED`/`RELEASE`) or the maintainer has confirmed that session is gone. Claim staleness is defined once, in `.kiro/steering/concurrency.md` § Stale claims — no skill in this repo carries a local heuristic for it. Also look for what peers have `MERGED` since you last saw `main`, any `TOUCHING` on modules your tasks enter, and any `WARN` that changes how you should implement
- Then append your own claim, before the first edit:
  ```bash
  LOG="$(git rev-parse --git-common-dir)/agent-log"
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "impl-<spec>" CLAIM "<spec> (worktree ../fitdocs-<spec>, branch impl/<spec>, base <sha>)" >> "$LOG"
  ```
- Use `impl-<spec>` as this session's id for every later line. Contract, including the full event vocabulary and read/write points: `.kiro/steering/concurrency.md`
- On a **resumed** session, re-read the whole log before anything else — your picture of `main` and of peer progress is stale by exactly the length of the pause

**Confirm the worktree**:
- Run `git rev-parse --abbrev-ref HEAD`. If it reports `main`, stop and create the spec's worktree (`git worktree add ../fitdocs-<spec> -b impl/<spec>`), then work there — implementer subagents inherit this tree, so starting on `main` puts every task's commits on it. Contract: `.kiro/steering/change-protocol.md` and `concurrency.md` — both apply to every spec run, not only when you know a peer is active, because the log read above is what tells you whether one is

**Identify choke points**:
- Cross-reference this spec's tasks against modules other specs also extend (`grep -ho 'src/fitdocs/[a-zA-Z0-9_/]*\.py' .kiro/specs/*/tasks.md | sort | uniq -c | sort -rn | head`). Note which of your tasks enter one — those are the tasks that owe a `TOUCHING` line and a fresh log read before they start

**Validate approvals**:
- Verify tasks are approved in spec.json (stop if not, see Safety & Fallback)

**Discover validation commands**:
- Inspect repository-local sources of truth in this order: project scripts/manifests (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, app manifests), task runners (`Makefile`, `justfile`), CI/workflow files, existing e2e/integration configs, then `README*`
- Derive a canonical validation set for this repo: `TEST_COMMANDS`, `BUILD_COMMANDS`, and `SMOKE_COMMANDS`
- Prefer commands already used by repo automation over ad hoc shell pipelines
- For `SMOKE_COMMANDS`, choose the lightest trustworthy runtime-liveness check for the app shape (for example: root URL load, Electron launch, CLI `--help`, service health endpoint, mobile simulator/e2e harness if one already exists)
- Keep the full command set in the parent context, and pass only the task-relevant subset to implementer and reviewer subagents

**Establish repo baseline**:
- Run `git status --porcelain` and note any pre-existing uncommitted changes

### Step 2: Select Tasks & Determine Mode

**Parse arguments**:
- Extract feature name from first argument
- If task numbers provided (e.g., "1.1" or "1,2,3"): **manual mode**
- If no task numbers: **autonomous mode** (all pending tasks)

**Build task queue**:
- Read tasks.md, identify actionable sub-tasks (X.Y numbering like 1.1, 2.3)
- Major tasks (1., 2.) are grouping headers, not execution units
- Skip tasks with `_Blocked:_` annotation
- For each selected task, check `_Depends:_` annotations -- verify referenced tasks are `[x]`
- If prerequisites incomplete, execute them first or warn the user
- Use `_Boundary:_` annotations to understand the task's component scope

### Step 3: Execute Implementation

#### Autonomous Mode (subagent dispatch)

**Iteration discipline**: Process exactly ONE sub-task (e.g., 1.1) per iteration. Do NOT batch multiple sub-tasks into a single subagent dispatch. Each iteration follows the full cycle: dispatch implementer → review → commit → re-read tasks.md → next.

**Context management**: At the start of each iteration, re-read `tasks.md` to determine the next actionable sub-task. Do NOT rely on accumulated memory of previous iterations. After completing each iteration, retain only a one-line summary (e.g., "1.1: READY_FOR_REVIEW, 3 files changed") and discard the full status report and reviewer details.

For each task (one at a time):

**a) Dispatch implementer**:
- **If this task's boundary enters a choke-point or otherwise peer-visible module**: re-read the log first (a peer may have changed that module's shape since preflight), then append a `TOUCHING <path>` line naming the module and the task. Subagents do not read or write the log — the parent session owns both, on their behalf
- Read `templates/implementer-prompt.md` from this skill's directory
- Construct a prompt by combining the template with task-specific context:
  - Task description and boundary scope
  - Paths to spec files: requirements.md, design.md, tasks.md
  - Exact requirement and design section numbers this task must satisfy (using source numbering, NOT invented `REQ-*` aliases)
  - Task-relevant steering context and parent-discovered validation commands (tests/build/smoke as relevant)
  - Whether the task is behavioral (Feature Flag Protocol) or non-behavioral
  - **If the task ships or changes tests** (nearly all of them): the `## Fixture Discrimination` section of `.kiro/steering/change-protocol.md`, verbatim or by path. The implementer template gates on it, and it is the most common rejection species in this repo
  - **Previous learnings**: Include any `## Implementation Notes` entries from tasks.md that are relevant to this task's boundary or dependencies (e.g., "better-sqlite3 requires separate rebuild for Electron"). This prevents the same mistakes from recurring.
- The implementer subagent will read the spec files and build its own Task Brief (acceptance criteria, completion definition, design constraints, verification method) before implementation
- Dispatch via **Agent tool** as a fresh subagent with `subagent_type: implementer`

**b) Handle implementer status**:
- Parse implementer status only from the exact `## Status Report` block and `- STATUS:` field.
- If `STATUS` is missing, ambiguous, or replaced with prose, re-dispatch the implementer once requesting the exact structured status block only. Do NOT proceed to review without a parseable `READY_FOR_REVIEW | BLOCKED | NEEDS_CONTEXT` value.
- **READY_FOR_REVIEW** → proceed to review
- **BLOCKED** → dispatch debug subagent (see section below); do NOT immediately skip
- **NEEDS_CONTEXT** → re-dispatch once with the requested additional context; if still unresolved → dispatch debug subagent

**c) Dispatch reviewer**:
- Read `templates/reviewer-prompt.md` from this skill's directory
- Construct a review prompt with:
  - The task description and relevant spec section numbers
  - Paths to spec files (requirements.md, design.md) so the reviewer can read them directly
  - The implementer's status report (for reference only — reviewer must verify independently)
- The reviewer must apply the `kiro-review` protocol to this task-local review.
- Preserve the existing task-specific context: task text, spec refs, `_Boundary:_` scope, validation commands, implementer report, and the actual `git diff` as the primary source of truth.
- The reviewer subagent will run `git diff` itself to read the actual code changes and verify against the spec
- **If the diff changes tests**: state in the prompt that the reviewer must run its own mutations under `kiro-review` § 5.5 — re-running the implementer's `DISCRIMINATION` claims and designing at least two of its own — and must not accept the implementer's mutation table as the review. On a test-only or guard task the reviewer's mutations are the deliverable
- Dispatch via **Agent tool** as a fresh subagent with `subagent_type: reviewer`

**d) Handle reviewer verdict**:
- Parse reviewer verdict only from the exact `## Review Verdict` block and `- VERDICT:` field.
- If `VERDICT` is missing, ambiguous, or replaced with prose, re-dispatch the reviewer once requesting the exact structured verdict only. Do NOT mark the task complete, commit, or continue to the next task without a parseable `APPROVED | REJECTED` value.
- **APPROVED** → before marking the task `[x]` or making any success claim, apply `kiro-verify-completion` using fresh evidence from the current code state; then mark task `[x]` in tasks.md and perform selective git commit
- **REJECTED (round 1-2)** → re-dispatch implementer with review feedback
- **REJECTED (round 3)** → dispatch debug subagent (see section below)
- **Repeat rejections on fixture discrimination** are the exception to that count, because the two ways they recur need opposite responses (`kiro-review` § 5.6):
  - **Converging but incomplete** — each round finds new, real insensitive assertions. Do not keep discovering one round at a time: re-dispatch instructing an *exhaustive* sweep that classifies every requirement the task lists as PINNED / PRESERVED-ONLY / UNPINNED. This terminates; incremental review does not
  - **Oscillating** — each fix installs a new blind spot in place of the old one (a fixture moved off a value collision loses the boundary coverage it existed for). Escalate to the debug subagent at round 2 rather than spending round 3

**e) Commit** (parent-only, selective staging):
- Stage only the files actually changed for this task, plus tasks.md
- **NEVER** use `git add -A` or `git add .`
- Use `git add <file1> <file2> ...` with explicit file paths
- Commit message format: `feat(<feature-name>): <task description>`
- Push in the same line: `git push -u origin impl/<spec>` on the first commit, `git push` after (`git push --force-with-lease origin impl/<spec>` after a rebase). A task commit that exists only on this machine is not landed — `.kiro/steering/change-protocol.md`, "Push On Commit"

**f) Record learnings** — two destinations, different audiences:
- If this task revealed cross-cutting insights, append a one-line note to the `## Implementation Notes` section at the bottom of tasks.md (audience: later tasks in *this* spec)
- Append to the shared log (audience: *peer sessions*, who cannot see tasks.md on your branch):
  - `TASK-DONE` with the commit sha when the task changes what a peer may assume — a new module or public API now on your branch, a shared surface you extended, a spec-level blocker you cleared. Say what they should do about it: *"consume it, do not add a second"* beats *"1.2 done"*
  - `WARN` when the task cost you something a peer is positioned to repeat — a review-rejection species, a guard that turned out to be bypassable, a fixture pattern that made a test unable to fail. These are the highest-value lines in the log
  - Nothing at all for a task that is purely internal to your spec's own leaf modules — the log is for what crosses session boundaries, and padding it with routine progress makes peers stop reading it

**g) Debug subagent** (triggered by BLOCKED, NEEDS_CONTEXT unresolved, or REJECTED after 2 remediation rounds):

The debug subagent runs in a **fresh context** — it receives only the error information, not the failed implementation history. This avoids the context pollution that causes infinite retry loops.

- Read `templates/debugger-prompt.md` from this skill's directory
- Construct a debug prompt with:
  - The error description / blocker reason / reviewer rejection findings
  - `git diff` of the current uncommitted changes
  - The task description and relevant spec section numbers
  - Paths to spec files so the debugger can read them
- The debugger must apply the `kiro-debug` protocol to this failure investigation.
- Preserve rich failure context: error output, reviewer findings, current `git diff`, task/spec refs, and any relevant Implementation Notes.
- When available, the debugger should inspect runtime/config state and use web or official documentation research to validate root-cause hypotheses before proposing a fix plan.
- Dispatch via **Agent tool** as a fresh subagent

**Handle debug report**:
- Parse `NEXT_ACTION` from the debug report's exact structured field.
- If `NEXT_ACTION: STOP_FOR_HUMAN` → append `_Blocked: <ROOT_CAUSE>_` to tasks.md, stop the feature run, and report that human review is required before continuing
- If `NEXT_ACTION: BLOCK_TASK` → append `_Blocked: <ROOT_CAUSE>_` to tasks.md, skip to next task
- If `NEXT_ACTION: RETRY_TASK` → preserve the current worktree; do NOT reset or discard unrelated changes. Spawn a **new** implementer subagent (`subagent_type: implementer`) with the debug report's `FIX_PLAN`, `NOTES`, and the current `git diff`, and require it to repair the task with explicit edits only
  - If the new implementer succeeds (READY_FOR_REVIEW → reviewer APPROVED) → normal flow
  - If the new implementer also fails → repeat debug cycle (max 2 debug rounds total). After 2 failed debug rounds → append `_Blocked: debug attempted twice, still failing — <ROOT_CAUSE>_` to tasks.md, skip
- **Max 2 debug rounds per task**. Each round: fresh debug subagent → fresh implementer. If still failing after 2 rounds, the task is blocked.
- Record debug findings in `## Implementation Notes` (this helps subsequent tasks avoid the same issue)

**`(P)` markers**: Tasks marked `(P)` in tasks.md indicate they have no inter-dependencies and could theoretically run in parallel. However, kiro-impl processes them sequentially (one at a time) to avoid git conflicts and simplify review. The `(P)` marker is informational for task planning, not an execution directive.

**Completion check**: If all remaining tasks are BLOCKED, stop and report blocked tasks with reasons to the user.

#### Manual Mode (main context)

For each selected task:

**1. Build Task Brief**:
Before writing any code, read the relevant sections of requirements.md and design.md for this task and clarify:
- What observable behaviors must be true when done (acceptance criteria)
- What files/functions/tests must exist (completion definition)
- What technical decisions to follow from design.md (design constraints)
- How to confirm the task works (verification method)

**2. Execute TDD cycle** (Kent Beck's RED → GREEN → REFACTOR):
- **RED**: Write test for the next small piece of functionality based on the acceptance criteria. Test should fail.
- **GREEN**: Implement simplest solution to make test pass, following the design constraints.
- **REFACTOR**: Improve code structure, remove duplication. All tests must still pass.
- **VERIFY**: All tests pass (new and existing), no regressions. Confirm verification method passes.
- **REVIEW**: Apply `kiro-review` before marking the task complete. If the host supports fresh subagents in manual mode, dispatch a fresh subagent with `subagent_type: reviewer`; otherwise perform the review in the main context using the `kiro-review` protocol. Do NOT continue until the verdict is parseably `APPROVED`.
- **MARK COMPLETE**: Only after review returns `APPROVED`, apply `kiro-verify-completion`, then update the checkbox from `- [ ]` to `- [x]` in tasks.md.

### Step 4: Final Validation

**Autonomous mode**:
- After all tasks complete, run `/kiro-validate-impl {feature}` as a GO/NO-GO gate
- If validation returns GO → before reporting feature success, apply `kiro-verify-completion` to the feature-level claim using the validation result and fresh supporting evidence
- If validation returns NO-GO:
  - Fix only concrete findings from the validation report
  - Cap remediation at 3 rounds; if still NO-GO, stop and report remaining findings
- If validation returns MANUAL_VERIFY_REQUIRED → stop and report the missing verification step

**Manual mode**:
- Suggest running `/kiro-validate-impl {feature}` but do not auto-execute

**Both modes — merge-back and the log** (a spec is not done when its last task is checked off):
- **Before the rebase**: re-read the log. What peers merged while you were implementing is exactly what you are about to rebase onto, and their `WARN` lines are the cheapest warning you will get about a conflict that is semantic rather than textual
- **After the branch lands on `main` and `main` is pushed** (`git push origin main` — the merge is landed nowhere until it is): append `MERGED` with the spec, the sha, and whether the spec is complete or leaves tasks open — that line is what tells a peer a choke point is free
- **If you park or hand back a claim instead of merging**: append `RELEASE` and say why, so the spec is takeable again
- Ritual: `.kiro/steering/change-protocol.md`; scope and Definition of Done for a spec run: `concurrency.md`

### Step 5: Queue Surfaced Follow-ups

Before reporting, collect the adjacent work this run surfaced and record it in
`.kiro/queue/` via the `kiro-queue-add` skill. Sources, in order:

- Every reviewer's `FOLLOW_UPS` field (they are read-only and cannot write)
- Anything routed away under **Upstream Ownership Detected**
- Debug reports whose `ROOT_CAUSE` lay outside the task boundary
- Validation findings classified `UPSTREAM`, and coverage gaps not remediated
- Tasks left `_Blocked:_`, when the blocker is a real defect rather than a
  pending human decision

Retain one line per queued item (`id` + title), not the full text. Skip
anything already tracked in `tasks.md` or `roadmap.md`. If nothing was
surfaced, record nothing and say so.

## Feature Flag Protocol

For tasks that add or change behavior, enforce RED → GREEN with a feature flag:

1. **Add flag** (OFF by default): Introduce a toggle appropriate to the codebase (env var, config constant, boolean, conditional -- agent chooses the mechanism)
2. **RED -- flag OFF**: Write tests for the new behavior. Run tests → must FAIL. If tests pass with flag OFF, the tests are not testing the right thing. Rewrite.
3. **GREEN -- flag ON + implement**: Enable the flag, write implementation. Run tests → must PASS.
4. **Remove flag**: Make the code unconditional. Run tests → must still PASS.

**Skip this protocol for**: refactoring, configuration, documentation, or tasks with no behavioral change.

## Critical Constraints
- **Log Throughout, Not At The End**: the log is a first-class artifact of the run — claim before the first edit, `TOUCHING` before a choke-point task, `TASK-DONE`/`WARN` as they happen, `MERGED` when the branch lands. Batched at the end it is a report; written as it happens it is coordination. Never `Edit` the log or rewrite it — append-only via `printf` with `>>`
- **Strict Handoff Parsing**: Never infer implementer `STATUS` or reviewer `VERDICT` from surrounding prose; only the exact structured fields count
- **No Destructive Reset**: Never use `git checkout .`, `git reset --hard`, or similar destructive rollback inside the implementation loop
- **Selective Staging**: NEVER use `git add -A` or `git add .`; always stage explicit file paths
- **Bounded Review Rounds**: Max 2 implementer re-dispatch rounds per reviewer rejection, then debug
- **Bounded Debug**: Max 2 debug rounds per task (debug + re-implementation per round); if still failing → BLOCKED
- **Bounded Remediation**: Cap final-validation remediation at 3 rounds

## Output Description

**Autonomous mode**: For each task, report:
1. Task ID, implementer status, reviewer verdict
2. Files changed, commit hash
3. After all tasks: final validation result (GO/NO-GO)
4. Follow-ups queued: `id` and title, one line each (or "none surfaced")

**Manual mode**:
1. Tasks executed: task numbers and test results
2. Status: completed tasks marked in tasks.md, remaining tasks count
3. Follow-ups queued: `id` and title, one line each (or "none surfaced")

**Format**: Concise, in the language specified in spec.json.

## Safety & Fallback

### Error Scenarios

**Tasks Not Approved or Missing Spec Files**:
- **Stop Execution**: All spec files must exist and tasks must be approved
- **Suggested Action**: "Complete previous phases: `/kiro-spec-requirements`, `/kiro-spec-design`, `/kiro-spec-tasks`"

**Test Failures**:
- **Stop Implementation**: Fix failing tests before continuing
- **Action**: Debug and fix, then re-run

**All Tasks Blocked**:
- Stop and report all blocked tasks with reasons
- Human review needed to resolve blockers

**Spec Conflicts with Reality**:
- If a requirement or design conflicts with reality (API doesn't exist, platform limitation), block the task with `_Blocked: <reason>_` -- do not silently work around it

**Upstream Ownership Detected**:
- If review, debug, or validation shows that the root cause belongs to an upstream, foundation, shared-platform, or dependency spec, do not patch around it inside the downstream feature
- Route the fix back to the owning upstream spec, keep the downstream task blocked until that contract is repaired, and re-run validation/smoke for dependent specs after the upstream fix lands

**Task Plan Invalidated During Implementation**:
- If debug returns `NEXT_ACTION: STOP_FOR_HUMAN` because of task ordering, boundary, or decomposition problems, stop and return for human review of `tasks.md` or the approved plan instead of forcing a code workaround
