# Implementation Plan

## Upstream Prerequisites

- **`training-blocks` and `plan-resolution` must both be implemented first.**
  This plan consumes, exactly as their designs state them: the plan-source
  grammar and `parse_block` (`src/fitdocs/plans/source.py`), the parsed
  `Block` and its change-record types (`plans/model.py`), the pass's
  `BlockStatus` (`plans/engine.py`), the `fitdocs plan` command with its one
  option `--out` and its report, the row states and confidence labels
  (`plans/matching.py`), the override semantics (latest wins by date then
  file position; a missing stem renders `not found` and exits 1), the
  placement grammar the pages carry, and `cli._today()` spelled
  `date.today()` so the fake-date contextmanager
  `_fake_system_date(fixed_timestamp, *, tz)` at
  `tests/test_history_e2e.py:211-245` can pin it. A task that finds any of
  these shaped differently stops and reports; it never edits a `plans/`
  module.
- **`distribution` is `tasks-generated` with 0 of 33 tasks done at this
  base** (its agent-skill packaging, major 4, has not shipped). Task 1.1
  begins with a precondition that decides between *landing* the by-name
  locator (the expected case) and *widening* an already-landed single-skill
  one; task 3.3 records whichever happened as distribution's Amendment 1.
  No distribution file is edited by any task other than 3.3.
- **`wiki-contract`** publishes the ownership contract at
  `declaration.CONTRACT_DOCUMENTATION_URL`; the skill links that value and
  nothing else about ownership. Its Amendment 3 (landed by training-blocks)
  puts `blocks/` into `OWNED_PATHS`, which the whole-body owned-path pin in
  2.2 relies on.
- **`encumbered-content-purge`'s wheel builder is a test-side dependency**:
  task 3.1 imports `tests.test_forbidden_strings._build_artifact(repo_root,
  out_dir, flag)` (`tests/test_forbidden_strings.py:721`, a private helper
  of that spec's Req 11.7 artifact guards) as the suite's one `uv build`
  recipe. `tests/test_skill_wheel.py` is a sibling module that imports it;
  `test_forbidden_strings.py` is not edited and gains no assertion (design §
  SkillWheelTest).

**Hard rules for every task**

- No task writes anything from the `skill` command or from the skill's
  procedure other than a plan source under a test's `tmp_path`; no task
  edits a workout page, a rendered page, the plan-source grammar, a report
  string or a `plans/` module.
- `src/fitdocs/agentskill.py` imports nothing from `fitdocs`; the `skill`
  command resolves no data root and reads no settings.
- Every name the skill teaches is bound by a test to the object that makes
  it true (the typer registry, `BlockStatus`, `RowState`, `Confidence`,
  `Sport`, `Modality`, the CLI's exit constants, `CONTRACT_DOCUMENTATION_URL`,
  `parse_block`); prose that cannot be bound (the reconcile report's line
  prefixes) sits on one anchored `Report lines:` line in the skill's report
  section and is asserted against real e2e output.
- In the skill, every command mention is an inline code span or a fence
  line; running prose uses "fitdocs" only as the tool's name. The
  conformance scan reads code spans and fence lines, not prose; a span that
  is solely `fitdocs` is the tool's name and is skipped.
- The skill directory and everything under it avoids the names
  `.gitignore` drops (`data/`, `*.fit`, `*.gpx`, `*.xlsx`); documentation
  references are published URLs only.
- The shipped example is synthetic: dated in 2030, illustrative names, at
  most twelve rows, no real athlete, race, place or workout.
- Each task that creates a typed test module appends that module to
  `pyproject.toml`'s mypy `files` list and leaves `uv run mypy` green in the
  same change (`pyproject.toml:58-59`'s rule); no task fixes another task's
  type errors.
- A task that finds it needs a new dependency, an upstream shape change, an
  edit to a `plans/` module or a `.gitignore` change, stops and reports.

## Shared source files

- **`src/fitdocs/agentskill.py`** -- created (or widened) by 1.1 only.
- **`src/fitdocs/cli.py`** -- 1.2 only (the `skill` command, one private
  helper, the docstring).
- **`src/fitdocs/skills/build-training-block/SKILL.md`** -- scaffolded by 1.1
  (frontmatter + H1 + one placeholder line), written in full by 2.1;
  **`example-block.toml`** -- 2.1 only.
- **`pyproject.toml`** (mypy `files`) -- one appended entry each by 1.1,
  1.2, 2.2, 3.1 and 3.4, in the task that creates the module. 3.1 is the
  only parallel task that touches it (3.2 and 3.3 do not).
- **`README.md`** -- 3.2 only.
- **`.kiro/specs/distribution/{requirements.md,design.md,tasks.md,spec.json}`**
  and the roadmap's `distribution` checkbox -- 3.3 only.
- 3.1, 3.2 and 3.3 are parallel: no two touch the same file.

## Test File Ownership

- `tests/test_skill_locator.py` → 1.1. `tests/test_cli_skill.py` → 1.2.
- `tests/test_agent_skill.py` → 2.2 (the frame and every binding; 3.2 and
  3.4 do not edit it).
- `tests/test_skill_wheel.py` → 3.1. `tests/test_docs_guarantees.py` (one
  appended test) → 3.2. `tests/test_skill_e2e.py` → 3.4.
- Synthetic workout pages for the e2e are written by that module's own
  `_page(...)` helper in the shape of `tests/history/test_engine.py:43-64`,
  extended with `sport`, `modality`, `indoor`, `start_time`; no conftest is
  added.

**Every new assertion names its mutation** (change-protocol § Fixture
Discrimination): each task's bullets name the production mutation that must
redden it; the implementer runs it through `uv run pytest`, observes red,
reverts, observes green, and says so in the task's Implementation Notes.
"Production" for the packaging pins includes the build inputs (`.gitignore`,
the skill files) because they are what the assertion is about. Where a
mutation is stated to red more than one pin, that is the expected reading,
not a discrepancy.

**Documentation deviation, stated**: the skill (2.1) and the README section
(3.2) are documentation by the task rules' definition and are tasks anyway --
the skill *is* the feature, and distribution set the precedent (its tasks
4.2, 5.x). Each is paired with the test that keeps it honest.

- [ ] 1. Foundation: the by-name locator and the read-only command
- [x] 1.1 Land the skill registry and by-name locator, with the scaffold skill directory
  - **Precondition, run first and recorded**: assert
    `src/fitdocs/agentskill.py` does not exist. If it does (distribution's
    major 4 shipped first), switch to the widen path: rename its single-name
    constant to the inbox skill's name, add the registry holding both names,
    make the two no-argument resolvers take a name, add the file-listing
    resolver, adapt every existing caller and test in the same change, and
    write "WIDENED" in this task's Implementation Notes so task 3.3 records
    consumption
  - Create the pure leaf: the skills directory name, the skill file name,
    this skill's canonical name, the registry tuple of packaged names holding
    it, and three by-name resolvers -- the packaged directory (present iff it
    is a directory holding the skill file, else absent), the skill file, and
    every regular file under the directory sorted by relative path (empty
    when absent). Resolution goes through the standard package-resource
    lookup, **bound at module level** (`from importlib.resources import
    files`) so tests have one attribute to monkeypatch, and runs at call
    time; nothing at import time; nothing from `fitdocs` imported; nothing
    written; a zipped import resolves as absent and the docstring says so
  - Scaffold `src/fitdocs/skills/build-training-block/SKILL.md` with the
    complete five-key frontmatter (name, a description saying what and when,
    `MIT`, the compatibility note, `metadata.version` equal to the manifest
    version) followed by the H1 and one placeholder line -- so the locator,
    the command and the both-ways pin are live before the body exists (task
    2.1 replaces the body and adds the companion file). The directory is
    named `skills/`, never `data/`, and carries no `__init__.py`
  - Pins (`tests/test_skill_locator.py`, typed; its mypy `files` entry
    appended here): the registry contains the canonical name; the resolved
    root exists, is a directory, and its final path component equals the
    constant; the skill file is inside it; the file listing contains it and
    nothing outside the root; an unregistered name resolves to absent and an
    empty listing; monkeypatching the module-level `files` to a `tmp_path`
    tree whose skill directory lacks `SKILL.md` resolves as absent; the
    module's import set is exactly `__future__`, `importlib.resources`,
    `pathlib`, `typing` (AST over both import forms); none of its names
    appears in `fitdocs.__all__`; the set of subdirectories under `skills/`
    equals the set of registered names, both ways
  - Named mutations: return the skills parent directory from the root
    resolver (the final-component pin reds); drop the skill-file presence
    check (the empty-directory fixture reds); append `"phantom"` to the
    registry (the both-ways pin reds); add `from fitdocs.layout import
    settings_path` (the import-set pin reds)
  - Observable: `uv run pytest tests/test_skill_locator.py` and `uv run
    mypy` green; `uv run python -c "from fitdocs.agentskill import
    skill_root, BLOCK_SKILL_NAME; print(skill_root(BLOCK_SKILL_NAME))"`
    prints an existing directory ending in `build-training-block`; the
    Implementation Notes say LANDED or WIDENED
  - _Requirements: 1.2, 1.6, 5.1, 5.2, 7.3_
  - _Boundary: AgentSkillLocator, AgentSkillPackage (scaffold only)_

- [x] 1.2 Add the skill command: listing, by-name, the unknown and absent cases, and the docstring
  - One command, `skill`, with one optional positional argument and no
    options. No argument: one line per registered name -- the name and its
    absolute directory, or the name and "(not present in this installation)"
    -- in registry order; if any is absent, the configuration-error path
    naming the absent skill(s) and saying the installation is incomplete
    (exit 2), else exit 0. With an argument: an unregistered name → the
    configuration-error path naming it and listing the packaged names (exit
    2); a registered name whose directory is absent → the configuration-error
    path naming it as packaged but not present (exit 2); present → the
    absolute path on the first line and a one-line copy recipe on the second
    (`cp -R <path> <skills-dir>/<name>`, the target a placeholder because
    the standard fixes no location), exit 0. Path lines print with markup
    and highlighting off and soft wrap on
  - The command resolves no data root, reads no settings, loads no profile,
    builds no tile store, runs no engine and writes nothing
  - Module docstring: the command list gains `fitdocs skill [NAME]` and its
    stale opening count ("Four feature commands", `cli.py:5`) is corrected
    to the registered set; the exit-code paragraph gains the
    unknown-or-absent skill case under `2`; the data-root posture
    paragraph's sentence deferring `skill` to distribution is replaced by
    one naming `skill` as the second instance of "describes the installed
    tool" beside `plugins`
  - Pins (`tests/test_cli_skill.py`, `CliRunner`, typed; its mypy entry
    appended here): listing exit 0 with one line per registered name whose
    second field is an existing directory; by-name exit 0, first line an
    absolute existing directory whose final component is the name, second
    line containing `cp -R` and the name; an unknown name exit 2 with stderr
    naming it and listing `build-training-block`; absence (monkeypatch
    `fitdocs.agentskill.files` to a `tmp_path` tree without the directory)
    → listing exit 2 and by-name exit 2, each naming the skill, no
    `Traceback` in the output; no data root needed -- `FITDOCS_DATA` unset,
    cwd an empty `tmp_path`, no pointer file → exit 0, with `check` under
    the same setup exiting 2 as the reachability control; no writes -- a
    recursive snapshot of the cwd and of the skill directory before and
    after each invocation is identical; the command's parameter set is
    exactly `{"name"}`; `skill` appears in `--help`; an AST pin that the
    command body names none of `resolve_data_root`, `_resolved_data_root`,
    `load_settings_document`, `load_athlete_inputs`, `apply_load`,
    `run_history`, `run_reconcile`, `_run_plan_pass`
  - Named mutations: exit 0 on an unknown name (its pin reds); map absence
    to exit 1 (its pin reds); add `out: Path | None = _OUT_OPTION` (the
    parameter pin reds); call `_resolved_data_root(None)` first (the
    no-data-root pin and the AST pin red); print the recipe without the name
    (its pin reds); `mkdir` `<cwd>/<name>` before printing (the no-writes
    snapshot pin reds)
  - Observable: `uv run fitdocs skill` prints `build-training-block  <abs
    dir>` and exits 0 in a shell with no data root configured; `uv run
    fitdocs skill nope` exits 2 and names the packaged skill; `uv run pytest
    tests/test_cli_skill.py tests/test_cli.py` and `uv run mypy` green
  - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 7.2, 7.5_
  - _Boundary: SkillCommand_

- [ ] 2. Core: the skill and its conformance test
- [x] 2.1 Write the example plan source and the skill body in the fixed nine-section order
  - Write `example-block.toml` (block id `example-block`): title `Example
    block`, `starts = 2030-01-07`, `ends = 2030-02-17`, `mesocycle_days =
    14`, a two-line goal; a mesocycle entry with a target and a focus and one
    with a focus only; at most twelve workouts, among them a `Workout` row
    with `modality = "strength"` and `indoor = true`, a long run, a `Ride`,
    and **two `Run` rows on `2030-01-22` (`w2-tue`, `w2-tue-b`), `w2-tue`'s
    table written before `w2-tue-b`'s** (plan-resolution pairs an ambiguous
    group in `block.current.rows` order, file order for original rows; task
    3.4's stage-C pin that `w2-tue` takes the 07:00 stem depends on it); one
    amendment dated `2030-01-15` with reason `Travel week` carrying one
    update (a two-day move across no boundary), one add (a `Walk`), one
    remove, and one mesocycle target change; two overrides dated
    `2030-01-23`: one naming `w2-tue` with `stems = ["2030-01-22-run-0700"]`
    and a reason, one marking `w2-tue-b` skipped with a reason. Three
    comment markers split the file -- `# --- the plan as first written ---`,
    `# --- amendments: appended, never edited ---`, `# --- overrides:
    appended when settling ---`. Every name is illustrative; nothing in it
    is real
  - Write the body of `SKILL.md` under the frontmatter task 1.1 scaffolded,
    as **nine H2 sections in exactly this order and wording**: `When this
    applies` (new block; amendment to a running block; settling a
    resolution the report called ambiguous or could not honor); `Before you
    write: what to ask` (goal; start and end dates; mesocycle length; key
    sessions and their days; weekly structure; cross-training and strength;
    whether the athlete wants a load target per mesocycle -- "a missing
    answer is asked for, never invented"; the skill proposes no sessions,
    paces or progressions); `The plan source, by example` (a ```toml fence
    holding the example **byte for byte**, a compact key table restating the
    grammar's keys, types, required flags and rules, a `Sports:` line
    listing every sport value in backticks, a `Modalities:` line listing
    every modality value in backticks, the rule that `modality` goes only
    with `sport = "Workout"`, the id form `[a-z0-9][a-z0-9-]*` unique for the
    block's life, bare TOML dates, **a row's date must fall inside
    `starts..ends`**, the filename stem is the block id, and what the three
    markers mean); `Where the source lives` (`<data root>/plans/` or the
    `[plans] path` setting; **fitdocs never creates, writes, renames or
    deletes it -- create it yourself**; one file per block); `Render it and
    read the report` (one ```bash fence: `fitdocs plan --out <data root>`;
    **one sentence** that the same pass runs at the end of `fitdocs sync`
    and `fitdocs regen` -- the only mention of `regen` outside the last
    section, on a line that also names `sync`; an `| Outcome | Meaning |
    Do |` table with exactly one row per pass outcome -- `rendered`,
    `unchanged`, `invalid`, `blocked`, `failed` -- and what the agent does
    for each; the `No source:` and declaration lines and the note in prose;
    **one anchored line beginning `Report lines:`** listing exactly the four
    reconcile prefixes in backticks -- `reconciled`, `mesocycle`,
    `ambiguous:`, `methodology:` -- then prose on the indented problem
    lines; an `| Exit | Meaning |` table with rows `0`, `1`, `2`); `Amend
    midstream` (append one dated amendment with a reason; never edit an
    earlier entry; update to move -- **move a row, never remove and re-add
    it**; add, remove, mesocycle for the other kinds; the seven mutable
    fields; non-decreasing amendment dates; rerun); `Settle an ambiguous
    match` (open the block page the `rendered` line names; a `| State |
    Meaning | Do |` table with exactly one row per row state -- `matched`,
    `overridden`, `skipped`, `not logged`, `upcoming`; a `| Label | Rule |
    Do |` table with exactly one row per label -- `exact`, `absorbed`,
    `ambiguous` -- restating each label's rule; the cell shape `matched
    (ambiguous): [stem](...)` and the planned page's "Settle it with an
    override entry" sentence; **where the stems are**: the link text of each
    competing row's cell in the block table, the bullets under a competing
    row's `Matched (ambiguous)` sentence on its planned page, and the
    `Unplanned:` list under the mesocycle's table for a logged workout no
    row claimed -- `Logged on this day:` appears only on a row that got no
    stem; write an override with `date`, `id`, `stems` or `skipped = true`,
    optional `reason`; the latest override for a row -- by date, then file
    position -- wins, so correct by appending; a stem the tool cannot find
    renders `not found`, is listed under `Problems:` and fails the run with
    exit 1; rerun); `Ownership` (fitdocs owns and rewrites the rendered
    pages; the source is the athlete's and fitdocs only reads it; **the
    in-tree `AGENTS.md` declaration is the authority and the published
    contract at the ownership-contract URL is the detail**; no owned path,
    region id or frontmatter key listed); `What this skill never does`
    (edit a workout page; edit a rendered page; run `fitdocs regen`; write
    anything but the plan source and files the agent environment owns;
    propose a plan of its own)
  - Plain markdown throughout; no client-specific syntax; every command
    mention is an inline code span or a fence line (prose says "fitdocs"
    only as the tool's name); the only URLs are published project URLs and
    the ownership link is the declaration's constant value; no fence
    contains `regen`; no owned path is spelled anywhere; the body stays
    under ~500 lines
  - Observable: `uv run python -c "from fitdocs.plans.source import
    parse_block; from fitdocs.agentskill import skill_root, BLOCK_SKILL_NAME;
    p = skill_root(BLOCK_SKILL_NAME) / 'example-block.toml';
    b = parse_block(p.read_text(), block_id='example-block');
    print(len(b.current.rows), len(b.amendments), len(b.overrides))"`
    prints a row count of at most 12, `1` amendment and `2` overrides; the
    body's nine H2 lines, read with `grep '^## '`, appear in the stated
    order; the toml fence's content diffs empty against the companion file;
    `grep -n regen SKILL.md` shows exactly one line outside the last section
    and that line contains `sync`; `grep -c '^Report lines:' SKILL.md` is 1
  - _Requirements: 1.1, 1.8, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 4.7_
  - _Boundary: AgentSkillPackage_

- [x] 2.2 Bind every name the skill teaches to the tool: the conformance test
  - `tests/test_agent_skill.py`, typed (its mypy entry appended here),
    parametrized over the registry of packaged names for the shared
    contract, with a per-skill map (heading tuple; later, the inbox skill's
    channel binding) that distribution 4.2 appends to without touching the
    frame
  - Frontmatter: the file opens with the fence; the block parses (test-side
    YAML) as a mapping; `name` equals the parameter and the directory's
    final component and matches `^[a-z0-9]+(-[a-z0-9]+)*$` within 64 chars;
    `description` 1-1024 chars containing `when` case-insensitively;
    `license` equals the manifest's license text; `compatibility` at most
    500 chars and contains `fitdocs`; `metadata.version` equals the manifest
    version; the key set is exactly the five (so no `allowed-tools`)
  - Order: the H2 headings in file order equal the nine-heading tuple
  - Commands and options -- **code scope only**: the scan reads inline code
    spans and lines inside bash/sh fences, never running prose; in each
    scanned span or line whose first word is `fitdocs`, the second word is a
    key of the typer registry's command map and each following `--` token
    is one of that command's option spellings; a span that is solely
    `fitdocs` is the tool's name and is skipped; the set of commands invoked
    in fences is exactly `{"plan"}`
  - Scoping of `regen`: no fence line contains `regen`; every line outside
    the last section that contains `regen` also contains `sync`
  - Tables: the first column of the `Outcome` table equals the set of pass
    outcome values; the `State` table's first column equals the set of row
    state values; the `Label` table's equals the set of confidence values;
    the `Exit` table's equals `{"0","1","2"}` derived from the CLI's three
    exit constants; every row's `Do`/`Rule` cell is non-empty
  - Vocabularies: backticked tokens on the `Sports:` line equal the sport
    enum's values; on the `Modalities:` line the modality enum's values; the
    body contains `sport = "Workout"`; exactly one line begins
    `Report lines:` and it carries at least one backticked token (the e2e
    test's anchor exists)
  - The example: the first toml fence's content equals the companion file's
    text; parsing it yields a block; the change types across its amendments
    are exactly the four kinds; its overrides include one with stems and one
    skipped; at most twelve current rows; some date carries two rows of one
    sport; the start year is at least 2030; the three markers are present
  - References: every markdown link target and bare URL starts with the
    project's published URL prefix; the body contains the declaration's
    ownership-contract URL constant by identity; none of `](docs/`, `](./`,
    `](../`, `.kiro/`, `src/fitdocs` occurs
  - Ownership: no member of the owned-path tuple occurs anywhere in the
    body; inside the Ownership section no preserved region id and no managed
    key occurs as a backticked token
  - Positive controls: nine sections found; each table parser finds at
    least one row; at least one bash and one toml fence and at least one
    inline `fitdocs <command>` span found; the table parser is pinned over a
    synthetic table string
  - Named mutations (each reds the pin or pins named): `metadata.version:
    0.0.0`; swap the amend and settle sections; `fitdocs plans --out` in the
    fence; `--dry-run` added to the fence; a second fence line `fitdocs regen
    --out <data root>` (the fence-set pin reds; the fence clause of the
    scoping pin reds -- one rule, two clauses); the prose "then run `fitdocs
    regen` to rebuild" in the amend section (the same-line-as-`sync` clause
    reds, the fence-set pin stays green); the unbackticked sentence "fitdocs
    never creates the directory" added to section 4 (nothing reds -- the
    control that prose is not scanned), then backticked as `` `fitdocs never`
    `` (the command pin reds); the `blocked` row deleted from the outcome
    table; `Confidence.ABSORBED` revalued to `"merged"` in
    `plans/matching.py` (upstream-side, reverted -- it is the drift this test
    exists to catch); `Swim` dropped from the `Sports:` line; one byte
    changed in the companion; the amendment's `remove` deleted from the
    example; the ownership URL replaced with `docs/ownership-contract.md`;
    `blocks/` written into the source section; `` `notes` `` written into the
    Ownership section
  - Observable: `uv run pytest tests/test_agent_skill.py` and `uv run mypy`
    green; each named mutation run, red, reverted, green, recorded
  - _Requirements: 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.5, 3.6, 3.8, 3.12, 3.13, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_
  - _Boundary: SkillConformance_

- [ ] 3. Integration: packaging proof, documentation, the distribution amendment, and validation
- [x] 3.1 (P) Prove every packaged skill file is a wheel member
  - `tests/test_skill_wheel.py`, typed (its mypy entry appended here -- the
    one `pyproject.toml` touch among the parallel tasks): a module-scoped
    fixture builds one wheel into `tmp_path` through the artifact builder
    the forbidden-strings suite already exposes (imported, not copied); for
    every registered name and every file the locator lists for it, the
    member path `fitdocs/skills/<name>/<relative path>` is in the wheel;
    positive controls `fitdocs/py.typed` and `fitdocs/__init__.py` are
    members and `fitdocs/skills/build-training-block/SKILL.md` is asserted
    by literal; negative pins -- no member under `fitdocs/skills/` names an
    unregistered directory, and no member path under `fitdocs/skills/` has a
    `data` component
  - A sibling of `tests/test_forbidden_strings.py`, not an extension: that
    module's artifact tests are another spec's absence guards
  - Named mutations: append `skills/` to `.gitignore` (the member pin reds;
    revert); rename `example-block.toml` to `example-block.fit` and update
    the fence (dropped by `*.fit`; the member pin reds through the locator's
    listing; revert); add `src/fitdocs/skills/phantom/SKILL.md` (the
    unregistered-directory pin reds; and the locator's both-ways pin reds
    too -- record which)
  - Observable: `uv run pytest tests/test_skill_wheel.py` and `uv run mypy`
    green and the test's output names the wheel and the member count; the
    `.gitignore` mutation observed red
  - _Requirements: 1.1, 1.9_
  - _Boundary: SkillWheelTest_

- [ ] 3.2 (P) Say where to install a packaged skill, how to verify it is active, and how to update it on upgrade
  - README: a `## Agent skills` section after `## Plugins` -- fitdocs
    packages agent skills inside the wheel; `fitdocs skill` lists them and
    `fitdocs skill <name>` prints one's directory and a copy recipe; install
    by copying that directory into the agent's skills directory (the open
    standard fixes no location; the agent's documentation does); verify by
    asking the agent to list its skills -- the packaged skill appears under
    its frontmatter name; update after upgrading fitdocs by running the
    command again and re-copying, the copied file's `metadata.version`
    saying which release it came from; `build-training-block` named with one
    sentence on what it does; "the packaged skills" for the set; no unshipped
    skill named
  - One appended test in `tests/test_docs_guarantees.py` over the
    documentation corpus: contains `fitdocs skill`, `build-training-block`,
    and one sentence each with `copy`, `verify` and `upgrade`; and does not
    contain `fitdocs-workouts` (a negative clause distribution 4.2 removes
    when the inbox skill ships -- say so in the test's docstring)
  - Named mutations: delete the update sentence (its pin reds); write
    `fitdocs-workouts` into the section (the negative pin reds)
  - Observable: `uv run pytest tests/test_docs_guarantees.py` green
    including the anchor-link check over the new section
  - _Requirements: 5.4_
  - _Boundary: SkillDocs_

- [x] 3.3 (P) Land the distribution Existing Spec Update as Amendment 1
  - Read task 1.1's Implementation Notes first: LANDED or WIDENED decides the
    wording below
  - Distribution `requirements.md`: an `## Amendment 1 (2026-09-16): a second
    packaged skill, located by name, landed by build-training-block` block in
    the shape of wiki-contract's amendments, and Requirement 8 criterion 8.9
    *(added by Amendment 1)* -- the distribution packages more than one
    agent skill under one skills location, lists them on request, reports
    one's location by name, and 8.6's install/verify/update obligations
    apply to every packaged skill. Renumber nothing
  - Distribution `design.md`: an appended amendment note on the locator
    block (the single-name constant retired for a registry; by-name
    resolvers plus the file-listing one; the inbox name appended by 4.2), on
    the skill-package block (a second skill; the conformance test exists as
    `tests/test_agent_skill.py`, generalized over the registry, to which 4.2
    adds its heading tuple and channel binding), on the CLI block (`skill
    [NAME]`, listing and unknown-name cases), on the artifact-policy data
    shape (`[wheel] required` gains this skill's two files), on the File
    Structure Plan (both skill directories; the test module marked
    existing), and on the three version-identity statements (the
    VersionSource risk, the Version identity data model, the Regression
    section): the permitted copies of the released version are one
    `metadata.version` per registered skill; each a note appended to the
    block, never a rewrite
  - Distribution `tasks.md`: task 1.1's observable ("... in the two places
    ... the agent skill's recorded version -- and nowhere else") becomes
    "the manifest, the changelog's newest entry, and every packaged skill's
    recorded version (one `SKILL.md` per registry entry) -- and nowhere
    else", the "two places" count going with it; task 1.4 gains this spec's
    two files as unconditionally required wheel members **and its "The
    packaged agent skill is deliberately not listed ... task 4.2 adds its
    entry" bullet is rewritten to name `fitdocs-workouts` as the one skill
    whose entry 4.2 adds**, dropping the singular subject; **task 4.1 is
    ticked as "landed by build-training-block"** (its locator and command
    exist by name) and its one residual -- appending the inbox name to the
    registry -- is folded into task 4.2, which creates the directory in the
    same change (this spec's both-ways pin and registry-parametrized
    conformance test red on a name without its directory and on a directory
    without its name, so the two cannot be separate tasks in either order);
    task 4.2's conformance bullet becomes extending the per-skill map
    (heading tuple, eight-channel binding), its packaging bullet becomes
    adding the inbox file to the policy's required set, and its `_Depends:
    4.1_` is dropped; the plan header gains the sequencing note. On the
    WIDENED path, 4.1 and 4.2 are instead ticked as shipped and the notes
    read "consumed and widened"
  - Distribution `spec.json`: an `amendments` entry with date, requirement
    `8.9 (new)`, reason and `also` naming this spec, the widened contract,
    the policy members, the version-scan allowance and the documentation
    obligation; the roadmap's `#### Existing Spec Updates` `distribution`
    checkbox ticked with "landed by build-training-block" (or "consumed")
  - Observable: `/kiro-spec-status distribution` clean with the amendments
    entry present; `grep -n "PACKAGED_SKILLS\|skill_root(name)\|example-block.toml"`
    over the four files finds each; `grep -n "the agent skill's recorded
    version\|The packaged agent skill is deliberately" tasks.md` finds
    nothing; task 4.2 carries no `_Depends: 4.1_`; the 8.x criteria above
    8.9 are unchanged against the pre-edit copy; and the roadmap's
    `distribution` entry under Phase 7 `#### Existing Spec Updates` reads `[x]`
  - _Requirements: 5.1, 5.2, 5.3_
  - _Boundary: DistributionSpecUpdate_

- [ ] 3.4 Walk the skill end to end: the automated stages, the recorded exercise, and feature validation
  - `tests/test_skill_e2e.py`, typed (its mypy entry appended here),
    `CliRunner`, a synthetic root under `tmp_path` with no settings file (so
    `plans/` is the default), **every run inside `_fake_system_date(...)`
    imported from `tests/test_history_e2e.py` and pinned to `2029-12-01`**
    so the walk never reads the wall clock: copy the companion example into
    `plans/example-block.toml` **cut at the markers** and run `plan --out
    ROOT` after each stage. Stage A (first-written part): exit 0, a
    `rendered` line naming the source, the block page exists, its count line
    says every row is `upcoming`, no cell reads `matched`. Stage B (+
    amendments): exit 0, `rendered`, the page carries `### Amendment 1 --
    2030-01-15` and `Reason: Travel week`, the moved row's planned page path
    is unchanged. Stage C (+ two synthetic generated `Run` pages **under
    `workouts/`** dated `2030-01-22` with stems `2030-01-22-run-0700` at
    07:00 and `2030-01-22-run-1800` at 18:00, each with a load under one
    methodology): exit 0, both rows' cells start `matched (ambiguous):`,
    stdout contains `ambiguous:` with both ids, `w2-tue`'s cell links the
    07:00 stem (the first row in `block.current.rows` order takes the
    earlier page -- the example writes `w2-tue` before `w2-tue-b`). Stage D
    (+ overrides): exit 0, `w2-tue`'s cell starts
    `overridden:` and links the 07:00 stem, `w2-tue-b`'s cell is `skipped`,
    the count line says `1 overridden, 1 skipped`, stdout has no
    `ambiguous:` line. Negative stage, which is also the supersession
    exercise (+ a third override `date = 2030-01-24, id = "w2-tue", stems =
    ["2030-01-22-run-0930"]`, no such page): exit 1, stdout contains `not
    found`, the page is still rendered, its `Problems:` section names
    `override[2]`, and **`w2-tue`'s cell no longer links the 07:00 stem** and
    starts `overridden:` carrying `` `2030-01-22-run-0930` (not found) `` --
    the latest override won. Across all runs: the source's bytes are
    unchanged by fitdocs (hash before and after each run); the union of
    stdout contains every backticked token on the skill's `Report lines:`
    line (read from that anchored line only) and `rendered`
  - Named mutations: cut one marker too early for stage B (the `Amendment 1`
    pin reds); write the stage-C pages with sport `Ride` (the ambiguous pin
    reds -- the type rule's reachability control); misspell the stage-D stem
    (stage D's exit-0 pin reds); date the negative override `2030-01-22`
    instead of `2030-01-24` (it loses to the stage-D override, so the
    cell-flip pin reds -- and, because only an effective override's stems
    are looked up, the exit-1 and `not found` pins red with it, as expected);
    pin today to `2030-03-01` (the stage-A `upcoming` pin reds); add `foo:`
    to the skill's `Report lines:` line (the token pin reds)
  - **The recorded exercise** (change-protocol § Validation, the
    `.claude/skills/**` row applied to a shipped skill): copy the skill into
    a scratch agent tree by the recipe `fitdocs skill build-training-block`
    prints; give an agent session (or follow it by hand) a synthetic data
    root and a *different* small plan supplied as answers to the skill's
    section-2 questions; follow the skill through stages A-D and the
    negative stage; record in this task's Implementation Notes the outcome
    line of each run, the exit codes, and the final cells of the settled
    rows -- or, if no agent can be run, an explicit statement of why and
    what was inspected instead
  - Feature validation: `uv run pytest && uv run ruff check . && uv run ruff
    format --check . && uv run mypy` green after rebasing onto `main`; every
    golden test and `tests/test_cli.py` green unedited (7.2, 7.4);
    `tests/test_determinism.py`'s dependency baseline green unedited (7.1);
    the prose grep from change-protocol § "Prose is not evidence" run over
    every changed test file and each surviving claim re-tested or deleted
  - Observable: the suite green; the Implementation Notes carry the
    transcript (five outcome lines, five exit codes, the two final cells) or
    the cannot-run statement
  - _Depends: 3.1, 3.2, 3.3_
  - _Requirements: 3.10, 3.11, 6.1, 6.2, 6.3, 7.1, 7.2, 7.4_
  - _Boundary: SkillE2E, PackagingPins_

## Implementation Notes
- 1.1 (round 2): **LANDED** -- `src/fitdocs/agentskill.py` and `src/fitdocs/skills/`
  did not exist at base ea6f879 (distribution major 4 unstarted), so the
  registry was created, not widened; task 3.3 records a landing. The locator's
  `_resolved_directory` `is_dir()` guard is *unobservable* on Python 3.11/macOS
  (`Path.is_file()` returns False on ENOTDIR rather than raising, so the later
  `SKILL.md` check already rejects a file at the skill path) -- kept for the
  design's literal wording, not pinned. Rejection species this round: an absence
  fixture that asserted two of three resolvers (`skill_file` unpinned), and a
  sort fixture whose four names ordered identically by basename and by relative
  path -- a sort-order pin needs a nested file whose basename sorts *before* a
  top-level name. Test files carry no process claims ("mutations recorded in
  the Implementation Notes") -- they do not exist when the file is written.
- 1.2 (round 2): controller ruling -- the config-error naming pins assert on
  `result.stderr` (the task text says stderr; typer 0.27's CliRunner keeps the
  streams separate), while `tests/test_cli.py`'s older `.output` convention is
  left alone. The by-name absent message carries the design's `-- the install
  is incomplete` clause; `fitdocs skill [NAME]` sits with `plugins` in a short
  paragraph after the tree-processing bullet list (not in it -- the sentence
  after that list says every listed command resolves a data root). Rejection
  species: a docstring pin whose `not in` literal never matched the ORIGINAL
  text because the original wrapped mid-sentence (whitespace-normalize before
  asserting on docstring prose); a recipe check satisfied by the source path
  alone; the mixed `result.output` stream cannot see a stdout/stderr swap; a
  files-only snapshot cannot see `mkdir`. Reversed registry order is UNPINNED
  by nature (one registered name).
- 2.1 (round 2): the rejection was content truth, not structure -- four
  sentences the tool contradicts survived a structurally perfect body:
  `No source:` names an ORPHANED RENDERED PAGE (no matching source), not a
  missing source entry; exit 0 does NOT mean nothing needs attention (an
  ambiguous match exits 0 -- `ReconcileReport.failed` is only
  invalid/blocked/failed blocks or override problems); `Problems:` is a block
  PAGE header while the report prints bare indented lines under `reconciled`;
  the default `plans/` directory must be named (it is deliberately outside
  OWNED_PATHS). Verify every report/page sentence in a skill by running the
  command and reading the page, never from the design's paraphrase. For 2.2:
  strip code spans/fences before collecting link targets (line ~233 has the
  design-mandated `[stem](...)` in a span), and grep OWNED_PATHS members as
  fixed strings (the regex `.fitdocs/` matches the URL's `/fitdocs/`).
- 2.2 (round 2): the reviewer ran 71 mutations of its own; the two that
  survived round 1 are species worth naming. (a) EVER-PRESENT TOKEN across two
  surfaces: `'sport = "Workout"' in body` was satisfied by the EXAMPLE FENCE's
  `w1-wed` row, so deleting or inverting the prose rule sentence stayed green
  -- a pin on a prose rule must scan the prose with the fences stripped. (b) A
  gate narrower than the design's rule: `startswith("fitdocs ")` silently
  waved through a tab- or NBSP-separated span; gate on the first whitespace
  word (`split(None, 1)[0]`) so every other separator reaches the LOUD parse.
  Controller ruling: an extra sub-key under `metadata` is not a pinned clause
  (Req 2.5 closes the top-level key set only; design clarification queued).
  Per-skill map `_SKILL_PROFILES` is where distribution 4.2 appends the inbox
  skill's heading tuple; the frame is not edited.
- 3.1 (round 2, prose only): the `data`-component negative pin cannot red on
  a real `references/data/` addition -- `.gitignore`'s `data/` rule drops the
  directory before the build, so that case is caught by the MEMBER pin (a
  listed file that did not ship); what the data pin observes is a file named
  `data` (the rule is directory-only) or the rule lifted. `_build_artifact` is
  not the suite's only `uv build` recipe (tests/load/test_packaging.py has two
  inline calls; design.md:189 is wrong -- queued). A wrong `_repo_root` fails
  loudly in `uv build`, never silently.
- 3.3 (round 2): LANDED wording throughout. Round-1 species: an amendment
  written from memory of the design rather than from the files -- "4.1 and
  4.2 ticked" (only 4.1 is), a pointer to a section that exists only in the
  SIBLING spec's design, the design-mandated `INBOX_SKILL_NAME` replaced by its
  literal value, and two skills' files conflated. Every identifier an
  amendment spells must be grepped in the source; every cross-reference must
  be opened. The design's "Regression section (:883)" label was wrong (that
  line is the Unit Tests version-resolution bullet) -- amended by content;
  queued.
