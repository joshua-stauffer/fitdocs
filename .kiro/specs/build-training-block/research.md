# Research & Design Decisions

## Summary
- **Feature**: `build-training-block`
- **Discovery Scope**: Extension (light discovery) -- a package-data
  directory, one pure leaf, one read-only command, and tests that bind a
  document to the tool; it consumes two unimplemented upstream designs and
  amends a third spec.
- **Key Findings**:
  - Hatchling ships non-`.py` files under `src/fitdocs/` with no include
    rule and honours `.gitignore`: verified by building a wheel from a tree
    carrying probe files -- `fitdocs/skills/build-training-block/SKILL.md`
    and `example-block.toml` were members; `fitdocs/skills/build-training-block/data/trap.md`
    and `fitdocs/data/trap2.md` were silently absent. `skills/` needs no
    `__init__.py`; no directory under it may be named `data`.
  - `importlib.resources.files("fitdocs")` returns a `pathlib.Path` for the
    installed package and traverses into plain subdirectories; no
    `importlib.resources` use exists anywhere in the tree today (the
    methodology tables distribution's design cites were purged), so this is
    the first site.
  - The typer registry is fully introspectable through
    `typer.main.get_command(app)`: `.commands` (today `check`,
    `derive-benchmarks`, `history`, `load`, `plugins`, `regen`, `sync`) and
    each command's `.params[*].opts` -- the concrete registry the
    conformance test resolves names against.
  - Every vocabulary the skill must teach is an importable `StrEnum` in the
    upstream designs (`BlockStatus`, `RowState`, `Confidence`, `Sport`,
    `Modality`); the reconcile report's line prefixes are not (prose in
    `cli._report_reconcile`), so they are bound behaviourally by the e2e
    walk, not by identity.
  - `declaration.CONTRACT_DOCUMENTATION_URL` is the one published URL the
    emitted `AGENTS.md` carries; the skill's ownership link is that value.
  - Distribution major 4 has not started (0 of 33 tasks); its locator design
    is single-skill (`SKILL_NAME`, no-argument functions). Landing here and
    amending is the roadmap's stated path; the "ships first" alternative is
    a precondition in the landing task.

## Research Log

### Does a non-Python directory under the package ship in the wheel, and does `.gitignore` bite?
- **Context**: roadmap Phase 7 constraint "Wheel packaging is silent today";
  brief constraint "the skill directory avoids ignored names".
- **Sources Consulted**: `pyproject.toml:23-24` (`[tool.hatch.build.targets.wheel] packages = ["src/fitdocs"]`,
  no include/exclude); `.gitignore` (`data/`, `*.fit`, `*.gpx`, `*.xlsx`);
  a wheel built with `uv build --wheel` from a tree carrying
  `src/fitdocs/skills/build-training-block/{SKILL.md,example-block.toml,data/trap.md}`
  and `src/fitdocs/data/trap2.md` (2026-09-16; the tree's `.git` was a
  fresh, empty repository at the time -- hatchling applied `.gitignore`
  regardless).
- **Findings**: 96 members; `fitdocs/py.typed`,
  `fitdocs/skills/build-training-block/SKILL.md`,
  `fitdocs/skills/build-training-block/example-block.toml` present; both
  `data/` files absent; no `__init__.py` needed under `skills/`.
- **Implications**: the directory name `skills/` is safe; a `data/`
  subdirectory anywhere under it would half-ship silently -- pinned
  negatively by the wheel-member test; the test is owed here because no
  existing test asserts a non-`.py` member (`tests/test_packaging.py` is an
  install smoke; `tests/test_forbidden_strings.py:1219-1224` checks only
  `__init__.py` and `METADATA` reach).

### How does the package find its own skill directory?
- **Context**: distribution's design says "the same resource mechanism the
  methodology tables already use"; those tables were purged.
- **Sources Consulted**: `grep -rn importlib.resources src/ tests/` (empty);
  `files('fitdocs') / 'skills' / 'build-training-block'` on the worktree's
  interpreter (a `PosixPath`, joinable, `is_dir()` answers).
- **Findings**: `files()` yields a filesystem path for an unzipped install;
  `str()` of it is the path. A zipped import would yield a non-filesystem
  traversable.
- **Implications**: `skill_root` treats "not a directory holding SKILL.md"
  as absent; a zipped install reports the skill absent (an honest
  degradation, documented; no supported install is zipped).

### What is the concrete registry a conformance test resolves names against?
- **Context**: brief constraint "the conformance test resolves every named
  command, option and channel against the CLI".
- **Sources Consulted**: `typer.main.get_command(app)` on typer 0.27.0;
  `src/fitdocs/cli.py` (`_EXIT_SUCCESS/_EXIT_FILE_FAILURES/_EXIT_CONFIG_ERROR`
  at `:130-134`); training-blocks design (PlanEngine `BlockStatus`,
  PlanCommand `--out` only); plan-resolution design (`RowState`,
  `Confidence`, the placement grammar, `_report_reconcile`'s prose lines).
- **Findings**: commands and options -- the click group; outcomes, states,
  labels -- three `StrEnum`s; sports and modalities -- `model.Sport` /
  `model.Modality`; exit tiers -- the three private constants (importable
  in tests); report prefixes -- prose only.
- **Implications**: set-equality pins over the enums (not mere presence, so
  a dropped row reds); the report prefixes are asserted to appear in real
  e2e output.

### How were earlier cross-spec amendments expressed?
- **Context**: the roadmap's `distribution` Existing Spec Update is to be
  landed by this spec "as a distribution amendment".
- **Sources Consulted**: `.kiro/specs/wiki-contract/requirements.md:104-139`
  and `spec.json` (Amendments 1 and 2, landed by effort-tags and
  load-history); `.kiro/specs/performance-benchmarks/tasks.md:579-605`
  (task 5.3 landing athlete-benchmarks Amendment 2);
  `.kiro/specs/training-blocks/tasks.md` task 4.5 (wiki-contract Amendment
  3); `.kiro/specs/plan-resolution/tasks.md` task 3.4 (training-blocks
  Amendment 1); `.claude/skills/kiro-spec-tasks/SKILL.md`.
- **Findings**: an amendment is a task of the landing spec that edits the
  target's `requirements.md` (an `## Amendment N (date): ..., landed by X`
  block plus `_(added by Amendment N)_` criteria, nothing renumbered), its
  `design.md` (an appended note on the affected component) and its
  `spec.json` (`amendments[]` entry), and ticks the roadmap checkbox.
- **Implications**: DistributionSpecUpdate follows that shape exactly and,
  because distribution's tasks are unstarted, also rewrites what its tasks
  1.4, 4.1 and 4.2 say so an implementer consumes rather than re-adds.

### The open SKILL.md standard's field contract
- **Context**: Requirement 2; "one conformance test covers both skills".
- **Sources Consulted**: `.kiro/specs/distribution/research.md:155-183`
  (agentskills.io findings recorded there: `name` 1-64 lowercase
  alphanumeric and hyphens equal to the directory; `description` 1-1024
  stating what and when; optional `license`, `compatibility` ≤ 500,
  `metadata` string map; `allowed-tools` experimental; body under ~500
  lines) and `design.md:841-849` (the frontmatter table).
- **Findings**: distribution's contract is exactly the five-key set this
  spec adopts; the nineteen `.claude/skills/kiro-*` files carry
  `allowed-tools` and `argument-hint`, which the shipped skill must not.
- **Implications**: the frontmatter test is parametrized over the registry
  with no per-skill branch; per-skill content (heading tuple, channel
  binding) lives in a map 4.2 appends to.

### What the skill must teach, and where each fact is fixed
- **Context**: brief constraint "quoted from the shipped tool, never
  paraphrased".
- **Sources Consulted**: training-blocks design -- the grammar table
  (SourceParser), `MUTABLE_FIELDS`, `IDENTIFIER`, the `[plans]` reader
  (default `plans/`, never created), PlanEngine's outcomes and report,
  PlanCommand's exit mapping; plan-resolution design -- `RowState`,
  `Confidence` and each label's rule, `effective_overrides` (latest by
  `(date, index)` wins), the missing-stem problem and `ReconcileReport.failed`,
  the placement grammar (`matched (ambiguous): <link>`, `Settle it with an
  override entry naming this row and the logged workout stems.`, `Logged on
  this day:` bullets with the stem as link text, `Ambiguous: ... -- settle
  them with override entries.`), the chaining after `sync`/`regen`.
- **Findings**: everything the skill needs the agent to read is on the block
  page or in the report; no owned path needs naming (the `rendered` line
  names the page; the page's bullets name the stems).
- **Implications**: the ownership section can defer completely (3.12) and
  the whole-body "no owned path" pin is satisfiable.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Declared registry + package data (selected) | `PACKAGED_SKILLS` tuple; `files()` resolution; static files | a dropped skill is an error, not a silent omission; distribution's constant-based invariant holds per skill | one append per new skill | both-ways directory pin keeps it honest |
| Directory scan | list `skills/*/SKILL.md` at call time | no constant to append | a skill missing from the wheel vanishes from the listing with no error; nothing for the conformance test to assert "both against" | rejected |
| Repository-only skill | keep `SKILL.md` under `.claude/skills/` | no packaging | unreachable from an index install; the maintainer's decision was "ships in the wheel" | rejected |
| Skill as a Python module docstring | `agentskill.SKILL_TEXT` | trivially a wheel member | not a `SKILL.md` directory the standard defines; unreadable as plain markdown by a non-supporting client | rejected |

## Design Decisions

### Decision: the example source is the only grammar exhibit, and it is one file shown twice
- **Context**: "grammar quoted from the shipped tool" cannot be pinned for
  prose; it can for a file the parser accepts.
- **Alternatives Considered**: (1) prose table only; (2) an example in the
  body and a different, larger example file; (3) one example, embedded
  byte-for-byte and shipped as a companion.
- **Selected Approach**: (3). The body's ```toml fence equals
  `example-block.toml`; the test parses it and pins its shape (every
  change kind, both override forms, a same-day same-type pair, ≤ 12 rows,
  a future year).
- **Rationale**: an agent reads the body; a test reads the file; identity
  makes them the same artifact. Parsing binds the grammar to the shipped
  parser without restating rules.
- **Trade-offs**: the body carries ~60 lines of TOML; the key table stays
  as a reading aid, unbound except through the example's keys.
- **Follow-up**: if training-blocks' parser gains a source version key, the
  example must carry it and the identity pin will make that visible.

### Decision: the example is staged by comment markers for the e2e walk
- **Context**: the skill teaches three situations (new, amend, settle) but
  ships one example; the e2e must run stage by stage, and an override
  naming a stem before the page exists would exit 1 in stage A.
- **Alternatives Considered**: three example files; one file cut at markers.
- **Selected Approach**: one file with three comment markers; the test cuts
  at them; the skill explains that the parts correspond to the three
  situations.
- **Rationale**: one artifact, one identity pin, a walk that mirrors the
  skill's own order.
- **Trade-offs**: the markers are load-bearing for a test; the conformance
  test pins their presence.

### Decision: the reconcile report's line prefixes are bound behaviourally
- **Context**: `reconciled`, `mesocycle`, `ambiguous:`, `methodology:` are
  prose in `cli._report_reconcile` (plan-resolution CliChaining), not
  constants.
- **Alternatives Considered**: ask plan-resolution to publish constants;
  leave unbound; assert presence in real e2e output.
- **Selected Approach**: the e2e walk asserts each token the skill lists
  appears in the union of the five runs' stdout; guarded from the other
  side by the observation that a token no run prints reds it.
- **Rationale**: no upstream change; a real run is the truest registry.
- **Trade-offs**: a prefix rename reds the e2e, not the conformance test;
  stated as a limitation in design.md's cross-spec obligations.

### Decision: a sibling wheel-member test, importing the existing builder
- **Context**: `tests/test_forbidden_strings.py:1180-1230` already builds
  and opens a wheel.
- **Alternatives Considered**: extend that test; a sibling with its own
  build; a sibling importing the builder.
- **Selected Approach**: sibling `tests/test_skill_wheel.py` importing
  `tests.test_forbidden_strings._build_artifact`.
- **Rationale**: the existing test is another spec's Req 11.7 guard and
  asserts absence, not presence; one builder keeps one build recipe.
- **Trade-offs**: one more `uv build` in the suite.

### Decision: land the by-name locator here; a precondition selects "widen" if distribution moved first
- **Context**: roadmap: "landed by build-training-block if distribution
  major 4 has not shipped first; otherwise consumed".
- **Selected Approach**: task 1.1 asserts `src/fitdocs/agentskill.py` is
  absent before creating it; if present, it widens in place and the
  amendment task records consumption.
- **Rationale**: the race is real (distribution is `tasks-generated`); a
  precondition costs one line and removes the ambiguity from the
  implementer.

### Decision: the README says "the packaged skills" and names only the shipped one
- **Context**: distribution Req 8.6's wording, applied to two skills, one of
  which does not exist yet.
- **Selected Approach**: generic wording for the set, `build-training-block`
  named, a negative docs pin on `fitdocs-workouts` that distribution 4.2
  removes when it ships.
- **Rationale**: a README that names an unshipped skill is a false statement
  the docs-guarantee test would otherwise let stand.

## Risks & Mitigations
- Table-parsing fragility in the conformance test -- one small parser with a
  positive control over a synthetic table.
- An agent copying the example as a real plan -- future year, illustrative
  names, and the section-2 "ask, never invent" rule.
- Distribution's major 4 starting between approval and implementation --
  the precondition in task 1.1 and the header note in distribution's
  amended tasks.
- The e2e's `upcoming` assertions depend on `today` being before the 2030
  rows -- pinned by running every stage inside the fake-date contextmanager
  at `tests/test_history_e2e.py:211-245` (`2029-12-01`), which
  `cli._today()`'s `date.today()` honours (plan-resolution CliChaining chose
  that spelling for exactly this reason); the walk never depends on the
  wall clock and never asserts `not logged`.
- Requirement 4.2 originally forbade `regen` anywhere outside the never-does
  section while 3.8 required the chaining sentence to name it (Step 3.5
  reviewer, round 1, blocking): 4.2 now scopes the rule to fences plus a
  same-line-as-`sync` clause, and the design's mutation set was re-derived so
  each mutation reds one pin.

## References
- `.kiro/specs/training-blocks/design.md` -- SourceParser grammar table,
  PlanEngine `BlockStatus` and report, PlanCommand exit mapping, PlanSettings.
- `.kiro/specs/plan-resolution/design.md` -- Matcher (`RowState`,
  `Confidence`, `effective_overrides`), Placement grammar, CliChaining.
- `.kiro/specs/distribution/design.md:480-539, 591-643, 841-849` --
  AgentSkillLocator, AgentSkillPackage, ArtifactPolicy, skill frontmatter.
- `.kiro/specs/distribution/tasks.md` major 4 (`:123-142`), task 1.4.
- `.kiro/specs/distribution/research.md:155-183` -- the open standard's
  field constraints as recorded there.
- `src/fitdocs/declaration.py:80-92` -- `CONTRACT_DOCUMENTATION_URL`.
- `tests/test_forbidden_strings.py:721-738, 1180-1230` -- `_build_artifact`
  and the wheel scan.
- `.kiro/steering/change-protocol.md` § Validation (`.claude/skills/**` row)
  and § Fixture Discrimination.
