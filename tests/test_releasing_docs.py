"""Conformance for task 5.6: the release procedure document (design.md
"ReleaseProcedure -- summary-only", "System Flows -> Release pipeline"; Req
5.1, 5.3, 5.6, 5.9, 5.10, 6.9).

`docs/releasing.md` is the ordered, ten-step release procedure. This module
pins:

(a) the ten numbered step headings appear, in the fixed design order, and
    the walk that finds them is non-vacuous.
(b) every fenced `uv run python -m scripts.<name>` command names a module
    that actually exists under `scripts/`, and every `--flag` it passes is a
    real option of that module's own argparse parser (positive control: at
    least three such commands appear).
(c) every fenced `uv run pytest ...` command selects a path that exists.
(d) step 3 and step 5's exact `--tag` invocations are pinned verbatim, so
    dropping `--tag` (the cheapest way to silently stop comparing against
    the release tag) reddens directly rather than only failing a
    flag-membership check.
(e) step 5 names `FITDOCS_FORBIDDEN_STRINGS` and `gate_not_run`, and states
    the polarity-bearing phrase that an unrun gate is a failed gate, never a
    step to skip -- and "skip" appears nowhere else in that section in a
    permissive sense.
(f) step 1's three fenced commands are exactly the set `CONTRIBUTING.md`'s
    own "The three quality gates" section names -- set equality, not a
    one-way containment.
(g) the section order Build < Artifact conformance < Tag < Rehearsal <
    Public < Post-publication, derived from the heading list.
(h) the "Automation jobs" table names each of the fixed eight job names
    (`gates`, `version`, `build`, `check`, `verify-artifact`,
    `publish-testpypi`, `publish-pypi`, `verify-published`) exactly once.
(i) every relative link on the page resolves to a real file, and every
    `#anchor` resolves to a real heading slug in its target.
(j) step 5 draws a hard line between the two failure kinds: only an UNSET
    `FITDOCS_FORBIDDEN_STRINGS` produces `gate_not_run` (exit 1); a SET but
    unusable source (missing, unreadable, empty, or inside the repository)
    is a hard error (exit 2). The `gate_not_run` bullet must not also claim
    the other four causes, and the hard-error bullet must name all four.
(k) step 5's fenced command starts with the `FITDOCS_FORBIDDEN_STRINGS=`
    assignment.
(l) step 2 names the three tracked locations the release literal must be
    bumped in (the manifest and both packaged skills' `SKILL.md`), runs all
    three keeping tests (`test_changelog.py`, `test_version_identity.py`,
    `test_agent_skill.py`), states the change is committed and step 1 is
    re-run against it, and names the two pre-release test pins plus the
    `docs/plugins.md` allowlist that need updating at the first real cut.
(m) step 6 and step 10 invoke the installed console script by its
    `$UV_TOOL_BIN_DIR` path in every fenced `--version` command, never
    bareword, and export `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` before the install
    command in the same fenced block.
(n) step 6's fenced commands and the `-k checkpoint` pytest selector are
    pinned verbatim, and the keyword actually selects at least one real
    test (checked via `pytest --collect-only`).
(o) step 8 names TestPyPI's endpoint and never the real public upload
    endpoint.
(p) step 10 names the install-and-check commands verbatim, including the
    exact rehearsal install form (`--index`, never the deprecated,
    priority-inverted `--index-url`/`--extra-index-url` pair, anywhere in
    the document), and no fenced block anywhere runs `uv publish` by hand.
(q) the Automation jobs table maps each automated step number to its exact
    expected job (not just set membership), and every `**Automation:**`
    line's job reference is drawn from that same fixed set.
(r) the "nothing is published before step 5 passes" rule is stated
    verbatim, exactly once, and that occurrence precedes the first numbered
    step heading -- a duplicate inside a step section is caught, not just
    an absent one.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import scripts.build_release as build_release
import scripts.check_artifacts as check_artifacts

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC_PATH = _REPO_ROOT / "docs" / "releasing.md"
_CONTRIB_PATH = _REPO_ROOT / "CONTRIBUTING.md"

_EXPECTED_STEP_HEADINGS = (
    "1. Quality gates",
    "2. Cut the changelog entry",
    "3. Version consistency",
    "4. Build",
    "5. Artifact conformance and encumbered-content gates",
    "6. Clean-environment verification",
    "7. Tag",
    "8. Rehearsal publication",
    "9. Public publication",
    "10. Post-publication verification",
)

_EXPECTED_JOBS = frozenset(
    {
        "gates",
        "version",
        "build",
        "check",
        "verify-artifact",
        "publish-testpypi",
        "publish-pypi",
        "verify-published",
    }
)

_EXPECTED_STEP_TO_JOB = {
    1: "gates",
    3: "version",
    4: "build",
    5: "check",
    6: "verify-artifact",
    8: "publish-testpypi",
    9: "publish-pypi",
    10: "verify-published",
}

_PARSER_FACTORY_BY_MODULE = {
    "check_artifacts": check_artifacts._build_parser,
    "build_release": build_release._build_parser,
}


# --- shared markdown helpers -------------------------------------------------


def _text() -> str:
    assert _DOC_PATH.is_file(), "docs/releasing.md does not exist"
    return _DOC_PATH.read_text(encoding="utf-8")


def _strip_fenced_blocks(text: str) -> str:
    """``text`` with every fenced code block's *content* lines blanked out
    (fence markers kept), so a literal ``## ...`` line inside an example
    fenced block (step 2's ``## [X.Y.Z] - YYYY-MM-DD`` heading example) is
    never mistaken for a real ATX heading."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    in_fence = False
    for line in lines:
        if line.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append(line if not in_fence else "\n")
    return "".join(out)


def _h2_headings(text: str) -> list[str]:
    return re.findall(r"^## (.+)$", _strip_fenced_blocks(text), re.M)


def _section(text: str, heading: str) -> str:
    """The text of the H2 section named ``heading``, up to the next H2 (or EOF)."""
    headings = _h2_headings(text)
    idx = headings.index(heading)
    start_pat = re.escape(f"## {heading}")
    if idx + 1 < len(headings):
        end_pat = re.escape(f"## {headings[idx + 1]}")
        match = re.search(f"{start_pat}(.*?){end_pat}", text, re.S)
    else:
        match = re.search(f"{start_pat}(.*)", text, re.S)
    assert match is not None, f"could not isolate section {heading!r}"
    return match.group(1)


def _fenced_blocks(text: str) -> list[str]:
    return re.findall(r"```\n(.*?)```", text, re.S)


def _heading_slugs(markdown: str) -> set[str]:
    """GitHub-flavoured anchor slugs for every ATX heading in ``markdown``."""
    slugs: set[str] = set()
    for line in markdown.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if match is None:
            continue
        text = match.group(2).lower()
        text = re.sub(r"[^\w\s-]", "", text.replace("_", ""))
        slugs.add(re.sub(r"\s+", "-", text.strip()))
    return slugs


def _anchor_links(markdown: str) -> list[tuple[str, str]]:
    """Every ``(target_file, anchor)`` pair the inline ``[label](file#anchor)``
    form links to."""
    links: list[tuple[str, str]] = []
    for target in re.findall(r"\]\(([^)]+)\)", markdown):
        if target.startswith(("http://", "https://")):
            continue
        if "#" not in target:
            continue
        file_part, anchor = target.split("#", 1)
        links.append((file_part, anchor))
    return links


# --- (a) fixed step heading order, non-vacuous ------------------------------


def test_ten_step_headings_appear_in_fixed_order() -> None:
    headings = _h2_headings(_text())
    assert headings, "the heading walk found no H2 headings at all"
    assert len(_EXPECTED_STEP_HEADINGS) == 10
    positions = [headings.index(h) for h in _EXPECTED_STEP_HEADINGS]
    assert positions == sorted(positions), f"step headings out of order: {headings!r}"
    assert len(set(positions)) == 10


# --- (b) every scripts.<name> command is real, with real flags -------------


_SCRIPTS_CMD_RE = re.compile(r"uv run python -m scripts\.([\w]+)([^\n]*)")


def _scripts_commands(text: str) -> list[tuple[str, str]]:
    """``(module_name, rest_of_line)`` for every fenced
    ``uv run python -m scripts.<name>`` command, after joining backslash
    line continuations so a command split across two lines is inspected
    whole (step 5's command is written this way in the doc)."""
    commands: list[tuple[str, str]] = []
    for block in _fenced_blocks(text):
        joined = re.sub(r"\\\s*\n\s*", " ", block)
        commands.extend(_SCRIPTS_CMD_RE.findall(joined))
    return commands


def _flags(rest: str) -> set[str]:
    return set(re.findall(r"(--[A-Za-z][\w-]*)", rest))


def test_every_scripts_command_names_a_real_module_with_valid_flags() -> None:
    commands = _scripts_commands(_text())
    # Positive control: at least three such commands, or this walk checks
    # almost nothing.
    assert len(commands) >= 3, (
        f"expected at least 3 `uv run python -m scripts.<name>` commands, "
        f"found {len(commands)}: {commands!r}"
    )
    for module_name, rest in commands:
        module_path = _REPO_ROOT / "scripts" / f"{module_name}.py"
        assert module_path.is_file(), (
            f"docs/releasing.md names scripts.{module_name}, but "
            f"{module_path} does not exist"
        )
        assert module_name in _PARSER_FACTORY_BY_MODULE, (
            f"no known argparse parser factory registered in this test for "
            f"scripts.{module_name} -- add one"
        )
        parser = _PARSER_FACTORY_BY_MODULE[module_name]()
        valid_flags = {
            option
            for action in parser._actions
            for option in action.option_strings
            if option.startswith("--")
        }
        for flag in _flags(rest):
            assert flag in valid_flags, (
                f"docs/releasing.md's scripts.{module_name} command uses "
                f"unknown flag {flag!r}; known flags: {sorted(valid_flags)}"
            )


# --- (c) every pytest command selects an existing path ----------------------


_PYTEST_CMD_RE = re.compile(r"uv run pytest([^\n]*)")


def test_every_pytest_command_selects_a_path_that_exists() -> None:
    text = _text()
    rests = []
    for block in _fenced_blocks(text):
        rests.extend(_PYTEST_CMD_RE.findall(block))
    assert len(rests) >= 2, (
        f"expected at least 2 `uv run pytest ...` commands, found {rests!r}"
    )
    checked_paths = 0
    for rest in rests:
        for token in rest.split():
            if token.startswith("tests/"):
                checked_paths += 1
                path = _REPO_ROOT / token
                assert path.exists(), (
                    f"docs/releasing.md's pytest command references missing "
                    f"path {token!r}"
                )
    # Positive control: at least one command actually named a tests/ path,
    # or the loop above checked nothing.
    assert checked_paths >= 2, (
        f"expected at least 2 tests/ paths named across pytest commands, "
        f"found {checked_paths}"
    )


# --- (d) --tag is pinned verbatim in steps 3 and 5 ---------------------------


def test_version_consistency_step_pins_the_exact_no_artifacts_tag_command() -> None:
    section = _section(_text(), "3. Version consistency")
    assert (
        "uv run python -m scripts.check_artifacts --no-artifacts --tag vX.Y.Z"
        in section
    )


def test_artifact_conformance_step_pins_the_exact_tag_command() -> None:
    section = _section(_text(), "5. Artifact conformance and encumbered-content gates")
    joined = re.sub(r"\\\s*\n\s*", " ", section)
    assert "uv run python -m scripts.check_artifacts --tag vX.Y.Z" in joined


# --- (e) gate_not_run is a failed gate, never a step to skip -----------------


def test_step5_states_gate_not_run_is_a_failed_gate_never_a_skip() -> None:
    section = _section(_text(), "5. Artifact conformance and encumbered-content gates")
    assert "FITDOCS_FORBIDDEN_STRINGS" in section
    assert "gate_not_run" in section
    assert "is a failed gate, never a step to skip" in section

    # "skip" must not appear anywhere else in this section in a way that
    # could read as permissive -- every sentence containing it must be the
    # pinned polarity phrase itself.
    sentences_with_skip = [
        sentence
        for sentence in re.split(r"(?<=[.:])\s+", section)
        if "skip" in sentence.lower()
    ]
    assert sentences_with_skip, (
        "positive control failed -- 'skip' does not appear at all"
    )
    for sentence in sentences_with_skip:
        assert "never a step to skip" in sentence, (
            f"docs/releasing.md's step 5 section uses 'skip' in a sentence "
            f"that is not the pinned failed-gate phrase: {sentence!r}"
        )


# --- (f) step 1 commands equal CONTRIBUTING.md's gate commands exactly ------


def test_quality_gates_step_matches_contributing_commands_exactly() -> None:
    contrib_text = _CONTRIB_PATH.read_text(encoding="utf-8")
    contrib_section = _section(contrib_text, "The three quality gates")
    contrib_commands = {block.strip() for block in _fenced_blocks(contrib_section)}
    # Positive control: CONTRIBUTING.md must actually carry fenced commands
    # here, or the equality below would pass by both sides being empty.
    assert contrib_commands, (
        "positive control failed -- CONTRIBUTING.md's quality-gates section "
        "has no fenced commands"
    )

    doc_section = _section(_text(), "1. Quality gates")
    doc_commands = {block.strip() for block in _fenced_blocks(doc_section)}
    assert doc_commands == contrib_commands, (
        f"docs/releasing.md step 1 commands {doc_commands} do not equal "
        f"CONTRIBUTING.md's quality-gate commands {contrib_commands}"
    )


# --- (g) section ordering: Build < Artifact conformance < Tag < Rehearsal
#     < Public < Post-publication ------------------------------------------


def test_step_order_build_through_post_publication() -> None:
    headings = _h2_headings(_text())
    ordered_targets = (
        "4. Build",
        "5. Artifact conformance and encumbered-content gates",
        "7. Tag",
        "8. Rehearsal publication",
        "9. Public publication",
        "10. Post-publication verification",
    )
    positions = [headings.index(h) for h in ordered_targets]
    assert positions == sorted(positions), (
        f"expected strictly increasing section order, got {positions} for "
        f"{ordered_targets!r}"
    )
    assert len(set(positions)) == len(positions)


# --- (h) the eight automation job names, each exactly once ------------------


def _automation_job_table_rows(text: str) -> list[tuple[str, str]]:
    section = _section(text, "Automation jobs")
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if re.fullmatch(r"\|[-:\s|]+\|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 2:
            continue
        if cells == ["Step", "Automation job"]:
            continue
        rows.append((cells[0], cells[1]))
    return rows


def test_automation_job_table_names_each_of_the_eight_jobs_exactly_once() -> None:
    rows = _automation_job_table_rows(_text())
    # Positive control: the walk over the table must actually find rows, or
    # every assertion below passes vacuously.
    assert rows, "the Automation jobs table walk found no rows at all"
    assert len(rows) == 10, (
        f"expected 10 step rows in the Automation jobs table, found "
        f"{len(rows)}: {rows!r}"
    )

    job_names = [
        match.group(1)
        for _, job_cell in rows
        for match in [re.search(r"`([a-z-]+)`", job_cell)]
        if match is not None
    ]
    assert len(job_names) == 8, (
        f"expected exactly 8 backticked job names across the table, found "
        f"{len(job_names)}: {job_names!r}"
    )
    assert len(set(job_names)) == 8, (
        f"a job name repeats in the Automation jobs table: {job_names!r}"
    )
    assert set(job_names) == _EXPECTED_JOBS, (
        f"automation job set mismatch: {set(job_names)} != {sorted(_EXPECTED_JOBS)}"
    )


def test_automation_job_table_maps_each_step_number_to_its_exact_job() -> None:
    """Set equality (above) would not catch two steps swapping jobs; this
    pins the per-step mapping the table must carry."""
    rows = _automation_job_table_rows(_text())
    assert rows, "the Automation jobs table walk found no rows at all"
    step_to_job: dict[int, str] = {}
    for step_cell, job_cell in rows:
        num_match = re.match(r"(\d+)\.", step_cell)
        assert num_match is not None, (
            f"could not parse a step number from {step_cell!r}"
        )
        job_match = re.search(r"`([a-z-]+)`", job_cell)
        if job_match is not None:
            step_to_job[int(num_match.group(1))] = job_match.group(1)
    assert step_to_job == _EXPECTED_STEP_TO_JOB, (
        f"step-to-job mapping mismatch: {step_to_job} != {_EXPECTED_STEP_TO_JOB}"
    )


_AUTOMATION_JOB_LINE_RE = re.compile(r"\*\*Automation:\*\*[^\n]*?the `([a-z-]+)` job")


def test_every_automation_line_job_reference_is_in_the_expected_set() -> None:
    matches = _AUTOMATION_JOB_LINE_RE.findall(_text())
    # Positive control: every one of the eight automated steps names its job
    # in its own "**Automation:**" line, so this must find exactly eight.
    assert len(matches) == 8, (
        f"expected exactly 8 '**Automation:** the `<job>` job' references, "
        f"found {matches!r}"
    )
    for job in matches:
        assert job in _EXPECTED_JOBS, (
            f"an '**Automation:**' line references unknown job {job!r}"
        )


# --- (i) every relative link, and every anchor, resolves --------------------


def test_every_relative_link_in_releasing_doc_resolves() -> None:
    text = _text()
    targets = re.findall(r"\]\(([^)]+)\)", text)
    relative = [t for t in targets if not t.startswith(("http://", "https://", "#"))]
    # Positive control: the page must link at least three sibling/parent
    # files, or this walk checks almost nothing.
    assert len(relative) >= 3, (
        f"docs/releasing.md carries only {len(relative)} relative link(s); "
        "expected at least three"
    )
    for target in relative:
        path_part = target.split("#", 1)[0]
        resolved = (_DOC_PATH.parent / path_part).resolve()
        assert resolved.is_file(), (
            f"docs/releasing.md links {target!r}, which resolves to "
            f"{resolved}, a file that does not exist"
        )


def test_every_anchor_link_in_releasing_doc_resolves_to_a_real_heading() -> None:
    text = _text()
    links = _anchor_links(text)
    # Positive control: the page must carry at least one #anchor link.
    assert links, "docs/releasing.md carries no #anchor links to check"
    for target_file, anchor in links:
        target_path = (_DOC_PATH.parent / target_file).resolve()
        assert target_path.is_file(), (
            f"docs/releasing.md links anchor target {target_file!r}, which "
            f"does not exist"
        )
        real_slugs = _heading_slugs(target_path.read_text(encoding="utf-8"))
        assert anchor in real_slugs, (
            f"docs/releasing.md links {target_file}#{anchor}, which matches "
            f"no heading in {target_file} (real slugs: {sorted(real_slugs)})"
        )


# --- (j) gate_not_run (unset, exit 1) vs hard error (set-but-unusable, ------
#     exit 2) are drawn as two distinct causes, not blurred into one --------


def _step5_section() -> str:
    return _section(_text(), "5. Artifact conformance and encumbered-content gates")


def test_step5_gate_not_run_bullet_is_unset_only() -> None:
    section = _step5_section()
    match = re.search(r"- A `gate_not_run` violation.*?(?=\n- )", section, re.S)
    assert match is not None, "could not find the gate_not_run bullet in step 5"
    bullet = match.group(0)
    assert "exit 1" in bullet
    assert "unset" in bullet
    for word in ("unreadable", "empty", "inside the repository"):
        assert word not in bullet, (
            f"the gate_not_run bullet wrongly folds in the set-but-unusable "
            f"cause {word!r} -- that is a hard error, not gate_not_run"
        )


def test_step5_hard_error_bullet_covers_all_four_set_but_unusable_causes() -> None:
    section = _step5_section()
    match = re.search(r"- Any other broken source.*", section, re.S)
    assert match is not None, "could not find the hard-error bullet in step 5"
    bullet = match.group(0)
    assert "exit 2" in bullet
    for phrase in (
        "does not exist",
        "could not be read",
        "no entries",
        "resolves inside the repository working tree",
    ):
        assert phrase in bullet, (
            f"the hard-error bullet is missing the {phrase!r} cause"
        )


# --- (k) step 5's fenced command starts with the env-var assignment --------


def test_step5_fenced_command_starts_with_the_env_var_assignment() -> None:
    section = _step5_section()
    candidates = [b for b in _fenced_blocks(section) if "scripts.check_artifacts" in b]
    assert candidates, "expected a fenced scripts.check_artifacts command in step 5"
    assert candidates[0].startswith("FITDOCS_FORBIDDEN_STRINGS="), (
        f"step 5's command does not start with the env-var assignment: "
        f"{candidates[0]!r}"
    )


# --- (l) step 2: three version locations, three tests, commit+re-run, -----
#     and the before-first-release note --------------------------------------


def _step2_section() -> str:
    return _section(_text(), "2. Cut the changelog entry")


def test_step2_names_the_three_version_locations() -> None:
    section = _step2_section()
    assert "[project].version" in section
    assert "src/fitdocs/skills/fitdocs-workouts/SKILL.md" in section
    assert "src/fitdocs/skills/build-training-block/SKILL.md" in section


def test_step2_pytest_command_runs_all_three_keeping_tests() -> None:
    section = _step2_section()
    candidates = [
        b for b in _fenced_blocks(section) if b.strip().startswith("uv run pytest")
    ]
    assert candidates, "expected a fenced `uv run pytest` command in step 2"
    command = candidates[0]
    for path in (
        "tests/test_changelog.py",
        "tests/test_version_identity.py",
        "tests/test_agent_skill.py",
    ):
        assert path in command, f"step 2's pytest command is missing {path!r}"


def test_step2_states_the_change_is_committed_and_step1_is_rerun() -> None:
    section = _step2_section()
    assert "Commit this change" in section
    assert "step 1" in section
    assert "re-run" in section.lower()


def test_step2_before_first_release_note_names_the_pinned_tests_and_allowlist() -> None:
    section = _step2_section()
    assert "test_real_changelog_has_no_released_version_literal" in section
    assert "test_real_changelog_has_added_entries_under_unreleased" in section
    assert "docs/plugins.md" in section


# --- (m) step 6/10 invoke by $UV_TOOL_BIN_DIR path, and export the tool ----
#     dirs before installing, in the same fenced block ----------------------


def test_step6_and_step10_version_commands_invoke_by_path_not_bareword() -> None:
    for heading in (
        "6. Clean-environment verification",
        "10. Post-publication verification",
    ):
        section = _section(_text(), heading)
        blocks = _fenced_blocks(section)
        version_blocks = [b for b in blocks if "--version" in b]
        assert version_blocks, f"{heading}: expected a fenced --version command"
        for block in version_blocks:
            assert '"$UV_TOOL_BIN_DIR/fitdocs"' in block, (
                f"{heading}: a --version command does not invoke via "
                f"$UV_TOOL_BIN_DIR: {block!r}"
            )


def test_step6_and_step10_export_tool_dirs_before_install_in_same_block() -> None:
    for heading in (
        "6. Clean-environment verification",
        "10. Post-publication verification",
    ):
        section = _section(_text(), heading)
        blocks = _fenced_blocks(section)
        install_blocks = [b for b in blocks if "uv tool install" in b]
        assert install_blocks, f"{heading}: expected a fenced uv tool install command"
        for block in install_blocks:
            assert "export UV_TOOL_DIR=" in block, f"{heading}: {block!r}"
            assert "export UV_TOOL_BIN_DIR=" in block, f"{heading}: {block!r}"
            assert block.index("export UV_TOOL_DIR=") < block.index("uv tool install")
            assert block.index("export UV_TOOL_BIN_DIR=") < block.index(
                "uv tool install"
            )


# --- (n) step 6's exact commands, and the checkpoint keyword actually ------
#     selects at least one real test ------------------------------------------


def test_step6_pins_the_exact_install_and_checkpoint_commands() -> None:
    section = _section(_text(), "6. Clean-environment verification")
    assert (
        "uv tool install --offline --from dist/fitdocs-X.Y.Z-py3-none-any.whl fitdocs"
        in section
    )
    assert "uv run pytest tests/test_release_artifacts.py -k checkpoint" in section


def test_step6_checkpoint_keyword_selects_at_least_one_real_test() -> None:
    section = _section(_text(), "6. Clean-environment verification")
    keyword_match = re.search(
        r"uv run pytest tests/test_release_artifacts\.py -k (\S+)", section
    )
    assert keyword_match is not None, (
        "could not find a `uv run pytest tests/test_release_artifacts.py "
        "-k <keyword>` command in step 6 to extract the keyword from"
    )
    keyword = keyword_match.group(1).rstrip("`")

    result = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "tests/test_release_artifacts.py",
            "-k",
            keyword,
            "--collect-only",
            "-q",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"collecting the `-k checkpoint` selection failed:\n{result.stdout}\n"
        f"{result.stderr}"
    )
    match = re.search(r"(\d+)/\d+ tests? collected", result.stdout)
    assert match is not None, (
        f"could not parse a collected-test count from: {result.stdout!r}"
    )
    assert int(match.group(1)) >= 1, (
        f"the `-k checkpoint` keyword selected zero tests: {result.stdout!r}"
    )


# --- (o) step 8 names TestPyPI, never the real public upload endpoint ------


def test_step8_names_testpypi_never_the_real_upload_endpoint() -> None:
    section = _section(_text(), "8. Rehearsal publication")
    assert "test.pypi.org" in section
    assert "upload.pypi.org" not in section


# --- (p) step 10 names the install-and-check commands verbatim -------------


def test_step10_contains_install_and_version_commands() -> None:
    section = _section(_text(), "10. Post-publication verification")
    install_blocks = [b for b in _fenced_blocks(section) if "uv tool install" in b]
    # Positive control: step 10 documents two install-and-check commands
    # (public and rehearsal) -- both must pin the version, not merely one.
    assert len(install_blocks) == 2, (
        f"expected 2 fenced `uv tool install` commands in step 10, found "
        f"{len(install_blocks)}: {install_blocks!r}"
    )
    for block in install_blocks:
        assert "fitdocs==X.Y.Z" in block, (
            f"step 10's install command does not pin the version: {block!r}"
        )
        assert "--version" in block


# --- (r) the "nothing is published before step 5" rule, verbatim -----------


def test_step10_pins_the_exact_rehearsal_install_form() -> None:
    section = _section(_text(), "10. Post-publication verification")
    assert (
        "uv tool install --no-cache --index https://test.pypi.org/simple/ "
        "fitdocs==X.Y.Z" in section
    )


def test_no_fenced_block_uses_the_deprecated_priority_inverted_index_flags() -> None:
    for block in _fenced_blocks(_text()):
        assert "--index-url" not in block, (
            f"a fenced block uses the deprecated `--index-url` flag: {block!r}"
        )
        assert "--extra-index-url" not in block, (
            f"a fenced block uses the deprecated `--extra-index-url` flag: {block!r}"
        )


def test_no_fenced_block_runs_uv_publish_by_hand() -> None:
    for block in _fenced_blocks(_text()):
        assert "uv publish" not in block, (
            f"a fenced block runs `uv publish` by hand, contradicting the "
            f"no-long-lived-credential design: {block!r}"
        )


def test_nothing_published_before_step5_rule_is_stated_verbatim_once_up_front() -> None:
    phrase = "nothing is published before step 5 passes"
    text = _text()
    assert text.count(phrase) == 1, (
        f"expected the rule stated exactly once, found {text.count(phrase)} "
        "occurrence(s)"
    )
    first_step_heading_pos = text.index("## 1. Quality gates")
    phrase_pos = text.index(phrase)
    assert phrase_pos < first_step_heading_pos, (
        "the rule must be stated in the document's front matter, before the "
        "first numbered step, not inside a step section"
    )
