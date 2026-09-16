# Requirements Document

## Project Description (Input)
A training block is authored as a structured source with a grammar, a sport
vocabulary, derived mesocycles, append-only amendments and override entries
(`training-blocks`), and reconciled against the logged workouts with five row
states and three confidence labels (`plan-resolution`). Nobody should learn
that by reading a parser. The maintainer's wiki is curated by an LLM, and the
maintainer asked for one canonical way to build a block: a packaged skill that
asks the right questions, writes a valid source, renders it with `fitdocs
plan`, amends it midstream without rewriting history, and settles an ambiguous
match the way the reconciler expects. The skill ships inside the fitdocs wheel
as a second packaged skill beside distribution's inbox skill, located by name
through `fitdocs skill <name>`; a conformance test resolves every command,
option, outcome, state and label the skill names against the tool's own
registries so the skill cannot drift; a wheel-member test proves the skill
ships; and the skill is exercised once end to end against a synthetic data
root before it is declared done. Because distribution's agent-skill packaging
(its major 4) has not shipped, this spec lands the by-name locator and command
and amends distribution to consume them. Source:
`.kiro/specs/build-training-block/brief.md`; Phase 7 of
`.kiro/steering/roadmap.md`.

## Introduction

`build-training-block` is the third and last Phase 7 spec and the first
product-facing skill this repository ships. Everything the two upstream specs
fix as a contract -- the plan-source grammar and its vocabulary, the `fitdocs
plan` command with its report and exit tiers, the row states and confidence
labels, the override entry and its semantics -- is what this skill teaches,
and the skill's one hard rule is that it teaches those things as the shipped
tool defines them, never from memory. That rule is enforced by construction:
the only grammar exhibit in the skill is an example source the shipped parser
must accept, and every command, option, outcome, state and label the body
names is resolved against the tool's own registry by a test that fails on a
stale name.

The skill is a directory of package data inside the wheel. `fitdocs skill`
lists the packaged skills and `fitdocs skill <name>` prints where one landed
and how to copy it into an agent's tree, because the open SKILL.md standard
defines no install location and the tool never installs into a place it does
not own. That by-name locator and command are distribution's to define;
distribution has not built them, so this spec lands them and amends
distribution to consume them -- the pattern `performance-benchmarks` used for
`athlete-benchmarks` Amendment 2 and `load-history` used for `wiki-contract`
Amendment 2.

The skill writes one kind of file, the plan source, and reads one kind of
page, the rendered block page, to find the label it must settle. It never
edits a workout page or a rendered page and never runs `regen`, and it says
so. It proposes no training of its own: the plan is the athlete's, and a
missing answer is asked for, never invented.

## Boundary Context

- **In scope**: the `build-training-block` skill file and the companion
  example source it ships with; the by-name skill registry, the `fitdocs
  skill` command's listing and by-name forms and their exit behavior; packaging
  the skill as a wheel member and the test that proves it; the conformance
  test over frontmatter, body order, commands, options, outcomes, states,
  labels, vocabularies, the example and the documentation references; the
  distribution amendment (locator and command by name, artifact-policy members,
  the conformance test generalized over the packaged set, the documentation
  obligation for more than one skill); the README lines on where to install a
  packaged skill, how to verify it is active and how to update it on upgrade;
  the end-to-end exercise and its automated half.
- **Out of scope**: the inbox skill's own content and its channel binding
  (distribution task 4.2); pkm's wrapper skill, its `wiki-schema.md` section,
  its log line and its data-root commit (the pkm repository's work); any
  change to the plan-source grammar, the rendered pages, the match rules, the
  override semantics or the report wording (`training-blocks`,
  `plan-resolution`); coaching content of any kind; a client-specific skill
  format beyond the open standard; plugin-marketplace packaging; the release
  artifact policy file and checker themselves (distribution tasks 1.4, 2.2 --
  this spec states what they must hold once they exist).
- **Adjacent expectations**: `training-blocks` provides the grammar, the
  `plan` command, its report outcomes and exit tiers, and exposes the parsed
  block and the outcome vocabulary as importable values; `plan-resolution`
  provides the row states, the confidence labels and the override semantics
  as importable values and renders the label on the page the skill reads;
  `wiki-contract` publishes the ownership contract at the URL the in-tree
  declaration already carries; `distribution` owns the skill-packaging design
  this spec extends and will consume the by-name locator for its inbox skill;
  the agent environment owns where a copied skill lives and whether it is
  active.

## Requirements

### Requirement 1: A Packaged Skill, Located by Name
**Objective:** As someone running an LLM-curated wiki, I want the
block-building skill to arrive with the tool and be findable by name, so that
installing fitdocs is enough to install the skill.

#### Acceptance Criteria
1. The fitdocs distribution shall ship the `build-training-block` skill as a directory inside the installed package, present in every built wheel, so that an installation from the package index alone carries it.
2. The fitdocs distribution shall locate every packaged skill through one registry of packaged skill names, so that a second packaged skill (the inbox skill distribution publishes) coexists with this one under the same mechanism and the same command.
3. When `fitdocs skill` is invoked with no argument, the fitdocs CLI shall print every packaged skill's name and its installed directory, one per line, and exit successfully when every packaged skill is present.
4. When `fitdocs skill <name>` is invoked with a packaged skill's name, the fitdocs CLI shall print that skill's installed directory as an absolute path and a one-line recipe for copying it into an agent's skills directory, and exit successfully.
5. If `fitdocs skill <name>` names a skill that is not packaged, the fitdocs CLI shall report the unknown name and list the packaged names, through the configuration-error path (exit 2).
6. If a packaged skill's files are absent from the installed distribution, the fitdocs CLI shall report the incomplete installation, naming the skill, through the configuration-error path (exit 2) rather than a traceback -- for both the listing and the by-name form.
7. The `skill` command shall resolve no data root, read no settings file, load no profile and write nothing anywhere; it describes the installed tool, not a tree, and needs no data root to succeed.
8. The packaged skill shall be readable and followable as plain markdown by a human, and by an agent environment that does not support the packaged skill format, using no client-specific syntax.
9. The fitdocs project shall prove, by inspecting a built wheel, that every file of every packaged skill is a member of the wheel.

### Requirement 2: Frontmatter Conforming to the Open Standard
**Objective:** As a maintainer, I want the skill's frontmatter to satisfy the
open SKILL.md standard exactly as distribution specifies for the inbox skill,
so that one conformance test covers every packaged skill.

#### Acceptance Criteria
1. The packaged skill's frontmatter shall carry a `name` equal to its directory name and to its entry in the registry of packaged names, made of lowercase letters, digits and hyphens, between 1 and 64 characters.
2. The frontmatter shall carry a `description` between 1 and 1024 characters that states both what the skill does and when to use it.
3. The frontmatter shall carry the project's license identifier, a compatibility note of at most 500 characters stating that the `fitdocs` command must be installed and reachable, and the released version under the `metadata` map.
4. The recorded version shall equal the version the package declares.
5. The frontmatter shall carry no key outside `name`, `description`, `license`, `compatibility` and `metadata`, and in particular no pre-approved-tools declaration.
6. The frontmatter contract of 2.1-2.5 shall be the one distribution specifies for the inbox skill, verified by one test that runs over every name in the registry of packaged skills.

### Requirement 3: The Body, in Order
**Objective:** As the curating LLM, I want the skill to walk me from the
athlete's intent to a rendered, reconciled block, so that every block is built
the one canonical way.

#### Acceptance Criteria
1. The skill body shall present its sections in this order: when the skill applies; what to ask before writing; the plan source by example; where the source lives; the command to run and how to read its report; amending midstream; settling an ambiguous match; ownership; what the skill never does.
2. The skill shall state that it applies in three situations: building a new block, amending a running block, and settling a resolution the reconciler reported as ambiguous or could not honor.
3. The skill shall list the questions to settle before writing -- the goal, the start and end dates, the mesocycle length, the key sessions and their days, the weekly structure, cross-training and strength work, and whether the athlete wants a load target per mesocycle -- and shall instruct the agent to ask for a missing answer and never to invent one.
4. The skill shall state that it proposes no sessions, paces or progressions of its own: the plan's content is the athlete's.
5. The skill shall teach the source grammar by one complete example that the shipped parser accepts, covering the block header, a mesocycle target with a focus, workouts including one with a modality and an indoor flag, an amendment carrying each change kind, and an override of each form.
6. The skill shall state the sport vocabulary and the modality vocabulary exactly as the tool defines them, the rule that a modality is stated only with the `Workout` sport, the identifier form for row ids, and the rule that a row's date must fall inside the block's bounds.
7. The skill shall state where the source lives -- the plan directory named by the `[plans]` setting, `plans/` under the data root by default -- that fitdocs never creates, writes, renames or deletes that directory or anything in it, and that the source file's name without its extension is the block's id.
8. The skill shall state the command to run with its `--out` option, that the same reconciling pass also runs at the end of `sync` and `regen`, how to read every outcome the run reports, and what each exit tier means.
9. The skill shall state, for an invalid source, a blocked or failed block, a missing override stem and an ambiguous match, that each is reported and what the agent does about each.
10. The skill's amending section shall instruct: append a dated amendment with a reason; never edit an earlier entry; move a row rather than remove and re-add it; then rerun the command and read the report.
11. The skill's settling section shall instruct: read the confidence label on the rendered page named in the report; write an override naming the row and the logged workout stems that fulfil it, or mark the row skipped; then rerun -- and shall state that a later override for the same row supersedes an earlier one, and that a stem the tool cannot find is reported and fails the run.
12. The skill's ownership section shall state the boundary and then defer -- naming the in-tree ownership declaration as the authority and the published contract as the detail -- and shall enumerate no owned paths, region identifiers or managed frontmatter keys of its own.
13. The skill shall state what it never does: edit a workout page, edit a rendered page, run `regen`, or write anything other than the plan source and files the agent environment itself owns.

### Requirement 4: Quoted from the Shipped Tool, Never Paraphrased
**Objective:** As a maintainer, I want every name the skill teaches to be
checked against the tool, so that the skill cannot drift when a command,
option, outcome, state, label or vocabulary changes.

#### Acceptance Criteria
1. Every `fitdocs` command the skill body names shall exist in the CLI's registered command surface, and every option the body names shall belong to the command it is named with.
2. The runnable command blocks in the skill shall invoke exactly one command, `plan`, and never `regen`; outside the section stating what the skill never does, `regen` shall be named only in the sentence stating that the reconciling pass also runs at the end of `sync` and `regen`, never as a command for the agent to run.
3. The set of run outcomes the skill documents shall equal the set the plan pass reports, and the set of row states and the set of confidence labels it documents shall equal the sets the reconciler defines, each entry paired with its meaning and the action to take.
4. The exit tiers the skill documents shall be exactly the three the CLI defines.
5. The sport and modality vocabularies the skill states shall equal the tool's; the example source embedded in the body shall be byte-identical to the shipped companion file; and that example shall parse as a valid block whose amendments together carry every change kind and whose overrides include one naming stems and one marking a row skipped.
6. Every documentation reference in the skill shall be a published project URL and never a repository-relative path, and the ownership-contract reference shall be the same URL the in-tree ownership declaration carries.
7. The shipped example shall be synthetic and small: it shall name no real athlete, race, place or logged workout, its ids and titles shall be plainly illustrative, and its row count shall be bounded.
8. If any of 4.1-4.7 ceases to hold, the project's test suite shall fail, naming the stale name, the missing entry or the offending reference.

### Requirement 5: Distribution's Skill Packaging, by Name
**Objective:** As the distribution spec's implementer, I want the by-name
locator, command and generalized conformance test landed once, so that the
inbox skill consumes them instead of re-adding a single-skill version.

#### Acceptance Criteria
1. Where distribution's agent-skill packaging (its major 4) has not shipped, the fitdocs project shall land the by-name locator, the `skill` command and the generalized conformance test here, and shall amend the distribution spec's requirements, design, tasks and metadata so that its tasks 4.1 and 4.2 consume them, its artifact policy's required members hold every packaged skill file, and nothing existing is renumbered.
2. Where distribution's major 4 has shipped first with a single-skill locator, the fitdocs project shall widen that locator to the registry in place, keep the inbox skill registered and its conformance covered, and record the amendment as a consumption rather than a landing.
3. The distribution amendment shall extend distribution's documentation obligation -- where to install a skill, how to verify it is active, and how to update it on upgrade -- to every packaged skill.
4. The fitdocs documentation shall state, for the packaged skills, where to install a skill, how to verify it is active, and how to update it when fitdocs is upgraded, without naming a skill that has not shipped.

### Requirement 6: Exercised Once Before It Is Declared Done
**Objective:** As the maintainer, I want the skill followed end to end against
a synthetic data root before it ships, so that its procedure is known to work
and not only to read well.

#### Acceptance Criteria
1. The fitdocs project shall follow the skill's own procedure against a synthetic data root -- build a block from the shipped example, render it, append an amendment and rerun, create a same-day ambiguity with synthetic logged pages and settle it with an override and rerun -- and shall record the observed outcome lines of each run and the final rendered resolution cells.
2. The fitdocs project shall automate the mechanical half of 6.1 as a test that follows the skill's steps and asserts each run's reported outcome and the rendered resolution cell after each step, so that the exercise repeats on every suite run.
3. If the exercise cannot be run by an agent, the record shall state why and what was inspected instead.

### Requirement 7: Preserved Guarantees
**Objective:** As an existing user, I want the tool to behave exactly as
before apart from the one new command, so that adopting the skill costs
nothing.

#### Acceptance Criteria
1. The change shall add no runtime dependency.
2. The `skill` command shall change the behavior, output and exit code of no existing command.
3. The skill locator shall not join the package's documented public import surface and shall import nothing from the fitdocs package.
4. Every generated document shall be byte-identical before and after this change.
5. The tool shall write nothing during any invocation of `skill`, including into the agent's skills directory; installation is the documented copy the user performs.
