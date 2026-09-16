# Brief: build-training-block

## Problem

A block is authored as a structured source with a grammar, a sport
vocabulary, derived mesocycles, append-only amendments and override
entries. Nobody should learn that by reading a parser. The maintainer's
wiki is curated by an LLM (the pkm repository's skills drain the inbox and
surface the day's training; they never write a workout page), and the
maintainer asked for one canonical way to build a block: a skill that asks
the right questions, writes a valid source, renders it, amends it midstream
without rewriting history, and settles an ambiguous match the way the
reconciler expects. Without it, every block is built ad hoc and the source
grammar is something the LLM guesses at.

## Current State

- No product-facing skill exists in this repository; all nineteen under
  `.claude/skills/` are developer-facing `kiro-*` workflow skills. The
  package ships no skill, prompt or template file
  (`pyproject.toml:23-24`; `find src -name "*.md"` is empty).
- `distribution` (unimplemented, 0 of 33 tasks) owns "the packaged agent
  skill": a locator holding one canonical name as a constant
  (`SKILL_NAME = "fitdocs-workouts"`, `skill_root()`, `skill_file()`,
  invariant "`skill_root()`'s final path component equals `SKILL_NAME`",
  `.kiro/specs/distribution/design.md:494-533`), a read-only `fitdocs skill`
  command printing the packaged directory and a copy recipe (tasks 4.1,
  4.2), a conformance test asserting name == directory == constant, and an
  artifact policy whose required-member set the skill file joins when it
  lands (`tasks.md:58-64`). The CLI docstring already names the command
  (`cli.py:58`) and the drain report keeps all eight channels so "the
  packaged agent skill can always find each channel by name" (`cli.py:841`).
- Hatchling ships non-`.py` files under `src/fitdocs/` by default (the built
  wheel carries `py.typed` with no include rule) and honours `.gitignore`,
  which ignores `data/`, `*.fit`, `*.gpx`, `*.xlsx`. No test asserts that
  a packaged data file is a wheel member: `tests/test_packaging.py` is an
  install smoke, and `tests/test_forbidden_strings.py:1180-1230` opens the
  wheel to scan it, asserting only `__init__.py` and `METADATA` (`:1219,
  :1224`).
- The install target's skills follow the open SKILL.md standard with
  frontmatter (`name`, `description`, `allowed-tools`, `argument-hint`) and
  a procedure that resolves the data root first, runs fitdocs with `--out`
  and `--no-prompt`, branches on the exit tier, and closes with pkm's own
  log line and data-root commit (`~/code/pkm/.claude/skills/process-workouts/SKILL.md`).
  Those closing rituals are pkm's, not fitdocs'.

## Desired Outcome

- **A packaged skill** at a canonical name (`build-training-block`) inside
  the wheel, found by `fitdocs skill build-training-block`, copied into an
  agent's tree by the printed recipe, and readable as plain instructions by
  a human or an agent environment without skill support.
- **Its body, in order**: when it applies (a new block; an amendment to a
  running block; settling a resolution); the questions to ask before
  writing — goal, dates, mesocycle length, key sessions and their days,
  weekly structure, cross-training and strength, per-mesocycle load targets
  if the athlete wants them — and what to do when an answer is missing
  (ask, never fabricate); the source grammar by example, including the
  sport vocabulary and the rule that a row's date must fall inside the
  bounds; where the source lives and that fitdocs never writes it; the
  command to run, with `--out`, and how to read every reported channel and
  exit tier; amending midstream — append a dated amendment with a reason,
  never edit an earlier entry, move a row rather than remove and re-add it,
  rerun; disambiguating — read the confidence label on the page, write an
  override naming the row and the logged stems (or mark it skipped), rerun;
  an ownership section that states the boundary and defers to the in-tree
  declaration and the published contract, enumerating no owned paths of its
  own; and what the skill never does (edit a workout page, edit rendered
  pages, run `regen`).
- **A conformance test** pinning the frontmatter contract (name equals
  directory equals the locator's constant, description within the standard's
  limit), that every command, option and channel the body names exists in
  the tool, that every documentation reference is a published URL and never
  a repository-relative path, and that the file is a wheel member.
- **The locator and command by name**, so two packaged skills coexist:
  `fitdocs skill` lists the packaged skills; `fitdocs skill <name>` prints
  one directory; an absent skill in an installed distribution is reported
  through the configuration-error path.
- The skill is exercised once end to end against a synthetic data root
  before it is declared done (`change-protocol.md` § Validation, the
  `.claude/skills/**` row applies to a shipped skill just as much), with the
  transcript or an explicit statement of what was inspected instead.

## Approach

Author the skill as package data under a skills directory in
`src/fitdocs/` (not named `data/`), with the locator widened to a registry
of packaged names; land the widened locator and by-name command here if
distribution major 4 has not shipped, and amend distribution's tasks 4.1,
4.2 and the artifact-policy member list to consume it — the pattern
`performance-benchmarks` used to land `athlete-benchmarks` Amendment 2. The
conformance test drives the body's command and channel names from the CLI's
own registry so they cannot drift.

## Scope

- **In**: the SKILL.md and any companion example source it ships; the
  by-name locator and `skill` command; packaging as a wheel member and the
  test that proves it; the conformance test; the README/docs lines that say
  where to install the skill, how to verify it is active and how to update
  it on upgrade (distribution Req 8.6's wording, applied to two skills); the
  end-to-end exercise.
- **Out**: pkm's wrapper skill, its `wiki-schema.md` section, its log line
  and data-root commit (the pkm repository's work, recorded in the roadmap's
  Phase 7 direct-implementation candidates); the inbox skill's own content
  (distribution 4.2); any change to the source grammar, the pages or the
  match rules; a Claude-specific skill format beyond the open standard.

## Boundary Candidates

- **The skill text**: procedure, examples, ownership section.
- **The locator and command**: registry of packaged names, path
  resolution through the package-resource mechanism, exit behaviour.
- **Conformance and packaging tests**.

## Out of Boundary

- Coaching content — the skill asks the athlete for the plan; it does not
  propose sessions, paces or progressions of its own.
- Anything the skill would need to know about pkm specifically.

## Upstream / Downstream

- **Upstream**: `training-blocks` (grammar, command, report), `plan-resolution`
  (confidence labels, override entries), `distribution` (the skill packaging
  design, the artifact policy, the docs' install wording).
- **Downstream**: the pkm wrapper; any later packaged skill reuses the
  registry.

## Existing Spec Touchpoints

- **Extends**: `distribution` — locator and command by name, artifact
  policy's required members holding every packaged skill file, task 4.2's
  conformance test generalized over the packaged set, and Req 8's wording
  for more than one skill. Landed here as a distribution amendment if major
  4 has not shipped; consumed otherwise.
- **Adjacent**: `inbox` (the report channels the skill must read exactly as
  distribution's inbox skill does); `wiki-contract` (the ownership section
  defers to the declaration and contract it publishes).

## Constraints

- **Grammar and commands are quoted from the shipped tool, never
  paraphrased from memory**: the conformance test resolves every named
  command, option and channel against the CLI and fails on a stale name.
- **No repository-relative paths in the skill**: it is copied into an
  agent's tree; documentation references are published URLs.
- **No personal data and no real plan** in the shipped example; the example
  source is synthetic and small.
- **The skill never edits a workout page, a rendered page, or runs
  `regen`**, and says so; the only files it writes are the plan source and
  what the agent environment itself owns.
- **Packaging honours `.gitignore`**: the skill directory avoids ignored
  names; a wheel-member test exists here until distribution's artifact
  policy subsumes it.
- Skill frontmatter conforms to the open standard's field contract exactly
  as distribution's design specifies for the inbox skill, so one conformance
  test covers both.
