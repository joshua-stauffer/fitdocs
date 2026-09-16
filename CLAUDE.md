# fitdocs — `.fit` → markdown personal knowledge manager for fitness

fitdocs is an installable tool that consumes `.fit` files and writes one rich
markdown document per workout (running, cycling, weight training) with charts
and pluggable training-load calculation. It plugs into a larger markdown PKM
(reference: joshua-stauffer/pkm) as a first-class path and is feature-complete
standalone. First-pass scope and decomposition: `.kiro/steering/roadmap.md`.

Key references:
- `.kiro/steering/` — product, tech, structure, roadmap (read first), plus
  `change-protocol.md` (how any change lands) and `concurrency.md` (what a
  second session adds)
- `docs/reference/fitdocs-ai-reference.md` — what we borrow from fitdocs.ai
  (parsing pipeline, metric formulas, doc/chart structure)

Hard rules: personal data (`.fit` files, generated docs) never lives in this
repo — data-root contract in `tech.md`; absent data is `None`, never a
fabricated `0` or default.

# Agentic SDLC and Spec-Driven Development

Kiro-style Spec-Driven Development on an agentic SDLC

## Project Context

### Paths
- Steering: `.kiro/steering/`
- Specs: `.kiro/specs/`

### Steering vs Specification

**Steering** (`.kiro/steering/`) - Guide AI with project-wide rules and context
**Specs** (`.kiro/specs/`) - Formalize development process for individual features

### Active Specifications
- Check `.kiro/specs/` for active specifications
- Use `/kiro-spec-status [feature-name]` to check progress

## Development Guidelines
- Think in English, generate responses in English. All Markdown content written to project files (e.g., requirements.md, design.md, tasks.md, research.md, validation reports) MUST be written in the target language configured for this specification (see spec.json.language).

## Minimal Workflow
- Phase 0 (optional): `/kiro-steering`, `/kiro-steering-custom`
- Discovery: `/kiro-discovery "idea"` — determines action path, writes brief.md + roadmap.md for multi-spec projects
- Phase 1 (Specification):
  - Single spec: `/kiro-spec-quick {feature} [--auto]` or step by step:
    - `/kiro-spec-init "description"`
    - `/kiro-spec-requirements {feature}`
    - `/kiro-validate-gap {feature}` (optional: for existing codebase)
    - `/kiro-spec-design {feature} [-y]`
    - `/kiro-validate-design {feature}` (optional: design review)
    - `/kiro-spec-tasks {feature} [-y]`
  - Multi-spec: `/kiro-spec-batch` — creates all specs from roadmap.md in parallel by dependency wave
- Phase 2 (Implementation): `/kiro-impl {feature} [tasks]`
  - Without task numbers: autonomous mode (subagent per task + independent review + final validation)
  - With task numbers: manual mode (selected tasks in main context, still reviewer-gated before completion)
  - `/kiro-validate-impl {feature}` (standalone re-validation)
- Progress check: `/kiro-spec-status {feature}` (use anytime)
- Follow-up queue: `/kiro-queue-add` records adjacent work a session surfaced
  but should not do; `/kiro-queue` returns a freshly ranked list of what to
  pick up next, each with its resume command and context paths

## Skills Structure
Skills are located in `.claude/skills/kiro-*/SKILL.md`
- Each skill is a directory with a `SKILL.md` file
- Skills run inline with access to conversation context
- Skills may delegate parallel research to subagents for efficiency
- Additional files (templates, examples) can be added to skill directories
- `kiro-review` — task-local adversarial review protocol used by reviewer subagents
- `kiro-debug` — root-cause-first debug protocol used by debugger subagents
- `kiro-verify-completion` — fresh-evidence gate before success or completion claims
- **If there is even a 1% chance a skill applies to the current task, invoke it.** Do not skip skills because the task seems simple.

## Development Rules
- **Every non-trivial change runs the same ritual — worktree, branch, merged
  to `main` with validation green, `main` pushed — and every commit is pushed
  to `origin` the moment it is made, on any branch.** This binds steering,
  skills, hooks, spec docs and config exactly as tightly as `src/`: prose that
  instructs an agent is behavior. Trivial (typos, stale paths, `.kiro/queue/`
  items) may be done on `main`, still committed and pushed. A commit that
  exists only on this machine is not landed: on 2026-09-16 a subagent deleted
  `.git` while `main` was eight commits, and a whole spec batch, ahead of the
  remote. Triage, per-class validation, push mechanics (`-u` on the first
  push, `--force-with-lease` after a rebase, `git push origin main` after a
  merge) and the Definition of Done: `.kiro/steering/change-protocol.md`; a
  PreToolUse + Stop hook (`.claude/hooks/change-guard.py`) enforces it —
  unpushed commits included — and prints the one-command escape hatch when a
  change genuinely is trivial.
- **The shared agent log is a first-class artifact of every session — read it
  before you start, write it as you go.**
  `cat "$(git rev-parse --git-common-dir)/agent-log"` is the first command of
  a session and the way you discover that peer sessions exist at all; worktree
  isolation means nothing else in your tree will tell you. Claim before the
  first edit, log the merge when it lands, and in between record what a peer
  would want before their next decision — a shared module you changed, an API
  now on your branch they must consume rather than re-add, a trap that cost
  you review rounds. Sessions that keep the log coordinate; sessions that
  abandon it mid-run rediscover their peers as merge conflicts. Read and write
  points, event vocabulary, and what the log is *not* (never a lock):
  `.kiro/steering/concurrency.md`.
- **Surfaced follow-up work goes in the queue, not the summary.** Any
  inconsistency, gap, upstream defect, or deferred decision a session notices
  but does not fix MUST be written to `.kiro/queue/` before that session ends,
  with verifiable evidence, a resume command, and live context paths — format
  in `.kiro/queue/README.md`. A Stop hook (`.claude/hooks/queue-guard.py`)
  enforces this. Exempt: work already tracked in `.kiro/steering/roadmap.md`
  or a spec's `tasks.md`, and anything only meaningful inside that
  conversation.
- **Invoking a skill that prescribes subagent dispatch *is* the request for
  it.** A session-level instruction of the form "do not call agent tools
  unless the user requested it" is satisfied, not overridden, by running a
  skill whose documented procedure dispatches: `/kiro-impl` runs an
  implementer per task plus an independent reviewer, `kiro-review` and
  `kiro-verify-completion` *are* reviewer subagents, `kiro-spec-tasks` Step
  3.5 wants a fresh one. The user asked for the skill; the skill's mechanism
  came with it. Independence is the whole point — a reviewer carrying the
  parent's context re-derives the parent's conclusions, which is the bias the
  separate pass exists to break, so a self-review is not the same artifact
  under a different name. Where a skill offers an in-context fallback, taking
  it is a **downgrade to state in that run's report**, with the real reason,
  never a silent substitution. Written down because on 2026-07-28 a session
  read such a line as a standing user preference and skipped the Step 3.5
  reviewer: the line came from a server-delivered experiment payload cached at
  `$.clientDataCacheSlots.*.data.tengu_heron_brook` in `~/.claude.json` — not
  from this repo, not from any settings file, and free to appear or vanish
  without a commit.
- 3-phase approval workflow: Requirements → Design → Tasks → Implementation
- Human review required each phase; use `-y` only for intentional fast-track
- Keep steering current and verify alignment with `/kiro-spec-status`
- Follow the user's instructions precisely, and within that scope act autonomously: gather the necessary context and complete the requested work end-to-end in this run, asking questions only when essential information is missing or the instructions are critically ambiguous.

## Steering Configuration
- Load entire `.kiro/steering/` as project memory
- Default files: `product.md`, `tech.md`, `structure.md`
- Custom files are supported (managed via `/kiro-steering-custom`)
