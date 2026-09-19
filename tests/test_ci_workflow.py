"""Conformance for task 6.2: the continuous integration workflow
(design.md "CiWorkflow and ReleaseWorkflow"; Req 5.2, 6.9).

`.github/workflows/ci.yml` runs on every push and pull request: the three
quality gates on the project's supported Python floor, then a build and an
artifact conformance check, so a manifest edit that would break a release
fails on the change rather than at release time (5.2). The encumbered-content
gate's match data is written to a runner-local file OUTSIDE the checkout from
the `FITDOCS_FORBIDDEN_STRINGS_CONTENT` secret; a run with that secret absent
must fail on `gate_not_run` rather than pass (6.9, Amendment 2) -- and this
module continuously proves that property by actually running the checker
both ways in a scratch directory, not merely asserting the YAML's shape.

Groups:

(a) YAML shape: `on` (parsed as the boolean key `True` by `yaml.safe_load`)
    includes `push` and `pull_request`; top-level `permissions` is exactly
    `{contents: read}` (no `id-token` -- CI publishes nothing); exactly one
    job, named `gates`.
(b) exactly one step's `run:` body, stripped, equals the literal
    `uv python install <floor>` where `<floor>` is parsed from
    `pyproject.toml`'s `requires-python` (derived, not hardcoded) -- found
    by the `run:` command's own prefix, never by a step *name* (a step
    could be named "Install Python 3.11" and still install the wrong
    version).
(c) the `run:` lines of the three named gate steps equal, as a set,
    `CONTRIBUTING.md`'s own "The three quality gates" fenced commands --
    reusing `tests.test_releasing_docs._fenced_blocks`/`_section` so
    CONTRIBUTING:41-43's claim about CI is literally checked, not merely
    asserted in a docstring.
(d) the build step runs `scripts.build_release --out-dir dist`; the check
    step runs `scripts.check_artifacts --no-version-check --dist-dir dist`
    and points `FITDOCS_FORBIDDEN_STRINGS` at a path under `$RUNNER_TEMP`,
    never under `$GITHUB_WORKSPACE` (the checkout).
(e) the write-step guards an empty secret (`::error::gate_not_run: ...` /
    `exit 1`) and references `secrets.FITDOCS_FORBIDDEN_STRINGS_CONTENT`;
    the emitted error message itself carries the `gate_not_run` vocabulary,
    so a fork PR's run log reads as the gate-not-run failure it is.
(f) the fail-closed step unsets `FITDOCS_FORBIDDEN_STRINGS` (`env -u`) and
    greps `gate_not_run` in its own output.
(g) no step anywhere mentions `uv publish`, `pypi`, `twine`, or `id-token`;
    every `uses:` action is pinned to a version tag (`@v\\d+`,
    `@v\\d+\\.\\d+`, `@v\\d+\\.\\d+\\.\\d+`) or a 40-hex commit SHA -- never a
    branch ref like `@main`. Only a SHA is truly immutable; a bare major
    tag floats, which is why the rule is "a version tag or a SHA", not
    "immutable". `astral-sh/setup-uv` additionally carries a minor-or-patch
    tag or a commit SHA, never a bare major: it stopped publishing floating
    major tags at v8, and a bare `@v10` 404s on GitHub even though it
    parses as a valid major tag
    (verified once by hand against the live GitHub API -- see the task's
    status report -- not by a live network call in this offline suite).
(h) step ordering: gates precede build precedes check precedes fail-closed.
(i) every `run:` command invoking `scripts.<module>` uses only flags that
    module's own argparse parser accepts (the 5.6 technique).
(j) **Executes the YAML's own `run:` bodies**, not a hand-copied
    reimplementation -- parsed straight out of `_workflow()` and run
    through `bash -eo pipefail -c` (GitHub Actions' own default shell for a
    multi-line `run:` block), from the repository root, with only the
    literal `--dist-dir dist` (or `--out-dir dist`) substituted for a
    scratch directory -- substitution count asserted to be exactly one, so
    a step that stopped mentioning the flag would be caught rather than
    silently no-opping. The local-exec tests read and run exactly the four
    script-invoking `run:` bodies (`build`, `write`, `check`,
    `fail-closed`) -- a wrong flag, a wrong path, or a broken guard inside
    any of those four bodies is executed and observed, not merely
    pattern-matched. A mutation to a step outside that set of four (or to
    ci.yml's YAML structure generally) is instead caught, if at all, by
    groups (a)-(i) above.
(k) `actionlint`, when present on PATH, is run against the file; skipped
    (with a message) when absent -- it is not installed in this
    environment.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest
import scripts.build_release as build_release
import scripts.check_artifacts as check_artifacts
import yaml

from tests.test_releasing_docs import _fenced_blocks, _section

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CI_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_CONTRIB_PATH = _REPO_ROOT / "CONTRIBUTING.md"

_GATE_STEP_NAMES = (
    "Run the test suite",
    "Lint and check formatting",
    "Run the strict type check",
)


def _text() -> str:
    assert _CI_PATH.is_file(), ".github/workflows/ci.yml does not exist"
    return _CI_PATH.read_text(encoding="utf-8")


def _workflow() -> dict[Any, Any]:
    doc = yaml.safe_load(_text())
    assert isinstance(doc, dict)
    return doc


def _gates_job(doc: dict[Any, Any]) -> dict[str, Any]:
    jobs = doc["jobs"]
    assert list(jobs.keys()) == ["gates"], (
        f"expected exactly one job named gates, got {jobs.keys()!r}"
    )
    job = jobs["gates"]
    assert isinstance(job, dict)
    return job


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return steps


def _step_by_name(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [s for s in steps if s.get("name") == name]
    assert len(matches) == 1, (
        f"expected exactly one step named {name!r}, found {len(matches)}"
    )
    return matches[0]


def _step_by_run_prefix(steps: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    """The one step whose `run:` body, stripped, starts with `prefix` --
    found by the command itself, never by the step's `name:` label (a
    step's name is free text and proves nothing about what it runs)."""
    matches = [
        s
        for s in steps
        if isinstance(s.get("run"), str) and s["run"].strip().startswith(prefix)
    ]
    assert len(matches) == 1, (
        f"expected exactly one step whose run: starts with {prefix!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _required_python_floor() -> str:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    requires = pyproject["project"]["requires-python"]
    match = re.match(r">=\s*(\d+\.\d+)", requires)
    assert match is not None, (
        f"could not parse a floor from requires-python={requires!r}"
    )
    return match.group(1)


def _contributing_gate_commands() -> set[str]:
    contrib_text = _CONTRIB_PATH.read_text(encoding="utf-8")
    contrib_section = _section(contrib_text, "The three quality gates")
    commands = {block.strip() for block in _fenced_blocks(contrib_section)}
    assert commands, (
        "positive control failed -- CONTRIBUTING.md's quality-gates "
        "section has no fenced commands"
    )
    return commands


# --- (a) triggers, permissions, single job ----------------------------------


def test_triggers_include_push_and_pull_request() -> None:
    doc = _workflow()
    # PyYAML parses the bare key `on` as the boolean True.
    triggers = doc[True]
    assert isinstance(triggers, dict)
    assert "push" in triggers
    assert "pull_request" in triggers


def test_top_level_permissions_are_exactly_contents_read() -> None:
    doc = _workflow()
    assert doc["permissions"] == {"contents": "read"}


def test_exactly_one_job_named_gates() -> None:
    doc = _workflow()
    jobs = doc["jobs"]
    assert list(jobs.keys()) == ["gates"]


# --- (b) python floor derived from pyproject.toml ---------------------------


def test_job_installs_the_exact_python_floor_version() -> None:
    floor = _required_python_floor()
    # Positive control: the floor must actually be the known value today,
    # or this test would pass no matter what pyproject.toml says.
    assert floor == "3.11"
    doc = _workflow()
    job = _gates_job(doc)
    steps = _steps(job)
    step = _step_by_run_prefix(steps, "uv python install")
    assert step["run"].strip() == f"uv python install {floor}", (
        f"expected the run: body to install exactly {floor!r}, got {step['run']!r}"
    )


# --- (c) the three gate steps equal CONTRIBUTING.md's commands exactly -----


def test_gate_steps_run_lines_equal_contributing_commands_exactly() -> None:
    contrib_commands = _contributing_gate_commands()
    doc = _workflow()
    job = _gates_job(doc)
    steps = _steps(job)
    run_lines: set[str] = set()
    for name in _GATE_STEP_NAMES:
        step = _step_by_name(steps, name)
        run = step.get("run")
        assert run is not None, f"step {name!r} has no run: command"
        run_lines.add(run.strip())
    assert run_lines == contrib_commands, (
        f"CI gate step run: lines {run_lines} do not equal CONTRIBUTING.md's "
        f"gate commands {contrib_commands}"
    )


# --- (d) build/check commands and RUNNER_TEMP, never GITHUB_WORKSPACE -----


def test_build_step_runs_build_release_with_dist_out_dir() -> None:
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    step = _step_by_name(steps, "Build the artifacts")
    run = step["run"]
    assert "scripts.build_release" in run
    assert "--out-dir dist" in run


def test_check_step_runs_check_artifacts_and_points_at_runner_temp() -> None:
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    step = _step_by_name(steps, "Check the artifacts")
    run = step["run"]
    assert "scripts.check_artifacts" in run
    assert "--no-version-check" in run
    assert "--dist-dir dist" in run
    match = re.search(r"FITDOCS_FORBIDDEN_STRINGS=(\S+)", run)
    assert match is not None, "check step does not set FITDOCS_FORBIDDEN_STRINGS"
    value = match.group(1)
    assert "RUNNER_TEMP" in value, (
        f"FITDOCS_FORBIDDEN_STRINGS value {value!r} is not under $RUNNER_TEMP"
    )
    assert "GITHUB_WORKSPACE" not in value, (
        f"FITDOCS_FORBIDDEN_STRINGS value {value!r} is under the checkout"
    )


# --- (e) the write step guards an empty secret ------------------------------


def test_write_step_guards_empty_secret_and_references_the_content_secret() -> None:
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    step = _step_by_name(steps, "Write the match data outside the checkout")
    run = step["run"]
    assert "exit 1" in run
    assert "::error::" in run
    # The emitted error message itself carries the checker's own vocabulary,
    # so the observable "fails on the gate-not-run violation" holds in the
    # run log for the empty-secret case too (fork PRs included).
    assert "gate_not_run" in run
    env = step.get("env", {})
    assert env.get("FITDOCS_FORBIDDEN_STRINGS_CONTENT") == (
        "${{ secrets.FITDOCS_FORBIDDEN_STRINGS_CONTENT }}"
    )


# --- (f) the fail-closed step unsets the variable and greps gate_not_run ---


def test_fail_closed_step_unsets_variable_and_greps_gate_not_run() -> None:
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    step = _step_by_name(steps, "Prove the gate fails closed")
    run = step["run"]
    assert "env -u FITDOCS_FORBIDDEN_STRINGS" in run
    assert "gate_not_run" in run


# --- (g) no publishing surface, every action pinned to a version tag or SHA ---


_VERSION_PIN_RE = re.compile(r"@(v\d+(\.\d+){0,2}|[0-9a-f]{40})$")


def test_workflow_publishes_nothing_and_pins_every_action() -> None:
    text = _text()
    lowered = text.lower()
    for forbidden in ("uv publish", "pypi", "twine", "id-token"):
        assert forbidden not in lowered, f"CI workflow mentions {forbidden!r}"
    uses_lines = re.findall(r"uses:\s*(\S+)", text)
    assert len(uses_lines) >= 2, "expected at least two uses: actions"
    for use in uses_lines:
        assert _VERSION_PIN_RE.search(use), (
            f"action {use!r} is not pinned to a version tag or commit SHA"
        )
    # Positive control: a mutable ref must actually be rejected, or the
    # pattern above could be satisfied by anything.
    assert not _VERSION_PIN_RE.search("actions/checkout@main")


def test_setup_uv_is_pinned_to_a_specific_release_not_a_bare_major() -> None:
    """`astral-sh/setup-uv` stopped publishing floating major tags at v8
    (confirmed against GitHub: `git/ref/tags/v10` 404s, `git/ref/tags/v10.1.0`
    resolves to a real commit) -- a bare `@v10` here would be a pin to
    nothing. This module makes no live network call (the project's tests
    stay offline); the live verification is recorded in the task's status
    report instead. This test instead pins the *shape* that verification
    demands: the action's ref carries at least a minor component, or is a
    40-hex commit SHA (the form setup-uv's own README prescribes)."""
    text = _text()
    match = re.search(r"astral-sh/setup-uv@(\S+)", text)
    assert match is not None, "workflow does not pin astral-sh/setup-uv"
    ref = match.group(1)
    assert re.fullmatch(r"v\d+\.\d+(\.\d+)?|[0-9a-f]{40}", ref), (
        f"astral-sh/setup-uv is pinned to {ref!r}, which is not a "
        "minor-or-patch release tag or a commit SHA"
    )


# --- (h) step ordering: gates < build < check < fail-closed ----------------


def test_step_ordering_gates_then_build_then_check_then_fail_closed() -> None:
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    names = [s.get("name") for s in steps]
    indices = {name: names.index(name) for name in names if name is not None}
    last_gate_idx = max(indices[name] for name in _GATE_STEP_NAMES)
    build_idx = indices["Build the artifacts"]
    check_idx = indices["Check the artifacts"]
    fail_closed_idx = indices["Prove the gate fails closed"]
    assert last_gate_idx < build_idx < check_idx < fail_closed_idx, (
        f"expected gates < build < check < fail-closed, got indices "
        f"gates={last_gate_idx}, build={build_idx}, check={check_idx}, "
        f"fail_closed={fail_closed_idx}"
    )


# --- (i) every scripts.<module> command uses only real flags --------------

_PARSER_FACTORY_BY_MODULE = {
    "check_artifacts": check_artifacts._build_parser,
    "build_release": build_release._build_parser,
}

_SCRIPTS_CMD_RE = re.compile(r"scripts\.(\w+)([^\n&|]*)")


def test_every_scripts_command_in_the_workflow_uses_only_real_flags() -> None:
    text = _text()
    commands = _SCRIPTS_CMD_RE.findall(text)
    assert len(commands) >= 2, "expected at least two scripts.<module> invocations"
    for module_name, rest in commands:
        assert module_name in _PARSER_FACTORY_BY_MODULE, (
            f"no known parser factory for scripts.{module_name}"
        )
        parser = _PARSER_FACTORY_BY_MODULE[module_name]()
        valid_flags = {
            option
            for action in parser._actions
            for option in action.option_strings
            if option.startswith("--")
        }
        used_flags = set(re.findall(r"(--[A-Za-z][\w-]*)", rest))
        for flag in used_flags:
            assert flag in valid_flags, (
                f"scripts.{module_name} command uses unknown flag {flag!r}; "
                f"known flags: {sorted(valid_flags)}"
            )


# --- (j) local executability: execute the YAML's own run: bodies ----------
#
# Every test below runs the literal `run:` text this module also asserts
# the shape of, through `bash -eo pipefail -c <body>` -- GitHub Actions'
# own default shell for a multi-line `run:` block -- so a typo in the YAML
# (a wrong flag, a wrong path, a broken guard) is executed, not merely
# pattern-matched. These tests read the `run:` text out of the parsed
# workflow itself, so they cannot pass with `ci.yml` absent or against a
# body they never looked at; the `--dist-dir dist` / `--out-dir dist`
# substitution is asserted to occur exactly once.


_SYNTHETIC_SECRET_CONTENT = (
    "CiWorkflowSyntheticNeedleLineOne\nCiWorkflowSyntheticNeedleLineTwo\n"
)


@pytest.fixture(scope="module")
def _built_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Built once per module via the ReleaseBuilder API directly (not the
    YAML) purely as a cheap source of a real wheel+sdist pair for the
    check/fail-closed body tests below to point `--dist-dir` at. The
    correctness of the *build step's own* `run:` text is separately
    exercised for real in `test_build_step_body_actually_builds`."""
    out_dir = tmp_path_factory.mktemp("ci_workflow_dist")
    build_release.build(out_dir=out_dir, source_date_epoch=315532800)
    return out_dir


def _run_body(steps: list[dict[str, Any]], name: str) -> str:
    step = _step_by_name(steps, name)
    run = step.get("run")
    assert isinstance(run, str), f"step {name!r} has no run: body"
    return run


def _substitute_once(body: str, old: str, new: str) -> str:
    """Replace the single occurrence of `old` in `body` with `new`.

    Asserts the occurrence count is exactly one first, so a step that
    stopped mentioning `old` (or started mentioning it twice) is caught
    here rather than silently substituting zero or many times.
    """
    count = body.count(old)
    assert count == 1, (
        f"expected exactly one occurrence of {old!r} to substitute, found "
        f"{count} in: {body!r}"
    )
    return body.replace(old, new)


def _run_bash_body(
    body: str, *, cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", body],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_build_step_body_actually_builds(tmp_path: Path) -> None:
    """Runs the real "Build the artifacts" `run:` text (only `--out-dir
    dist` substituted for a scratch directory), proving the command and
    every flag it passes actually build a wheel and an sdist -- catches,
    for example, an invalid `--source-date-epoch` value that a flag-name-only
    check would wave through."""
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    body = _run_body(steps, "Build the artifacts")
    out_dir = tmp_path / "dist"
    substituted = _substitute_once(body, "--out-dir dist", f"--out-dir {out_dir}")

    result = _run_bash_body(substituted, cwd=_REPO_ROOT, env=os.environ.copy())
    assert result.returncode == 0, (
        f"the build step's run: body failed: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert len(list(out_dir.glob("*.whl"))) == 1
    assert len(list(out_dir.glob("*.tar.gz"))) == 1


def test_write_step_body_actually_writes_the_match_file_where_check_expects_it(
    tmp_path: Path,
) -> None:
    """Runs the real "Write the match data outside the checkout" `run:`
    text with a synthetic (two-line) secret value, then confirms the file
    it wrote exists at EXACTLY the path the "Check the artifacts" step's
    own `FITDOCS_FORBIDDEN_STRINGS=` assignment names -- catching both a
    write to a cwd-relative path (never under `$RUNNER_TEMP`) and a
    filename mismatch between the two steps."""
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    write_body = _run_body(steps, "Write the match data outside the checkout")
    check_body = _run_body(steps, "Check the artifacts")

    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()
    # The script's cwd is deliberately a DIFFERENT scratch directory than
    # $RUNNER_TEMP -- a mutation that writes to a bare, cwd-relative
    # filename (dropping the "$RUNNER_TEMP/" prefix) would write here
    # instead, and the assertion below would find nothing at the expected
    # path.
    write_cwd = tmp_path / "write_cwd"
    write_cwd.mkdir()

    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(runner_temp)
    env["FITDOCS_FORBIDDEN_STRINGS_CONTENT"] = _SYNTHETIC_SECRET_CONTENT

    result = _run_bash_body(write_body, cwd=write_cwd, env=env)
    assert result.returncode == 0, (
        f"the write step's run: body failed: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )

    match = re.search(r"FITDOCS_FORBIDDEN_STRINGS=(\S+)", check_body)
    assert match is not None, "check step does not set FITDOCS_FORBIDDEN_STRINGS"
    raw_value = match.group(1).strip('"')
    expanded = raw_value.replace("$RUNNER_TEMP", str(runner_temp))
    written_path = Path(expanded)
    assert written_path.is_file(), (
        f"the write step did not create the file the check step expects "
        f"at {written_path}"
    )
    assert written_path.read_text() == _SYNTHETIC_SECRET_CONTENT


def test_write_step_body_exits_one_when_the_secret_content_is_empty(
    tmp_path: Path,
) -> None:
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    write_body = _run_body(steps, "Write the match data outside the checkout")

    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()

    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(runner_temp)
    env["FITDOCS_FORBIDDEN_STRINGS_CONTENT"] = ""

    result = _run_bash_body(write_body, cwd=tmp_path, env=env)
    assert result.returncode == 1, (
        f"expected exit 1 with an empty secret, got {result.returncode}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "gate_not_run" in result.stdout + result.stderr


def test_check_step_body_actually_succeeds_against_the_written_match_file(
    tmp_path: Path, _built_dist: Path
) -> None:
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    write_body = _run_body(steps, "Write the match data outside the checkout")
    check_body = _substitute_once(
        _run_body(steps, "Check the artifacts"),
        "--dist-dir dist",
        f"--dist-dir {_built_dist}",
    )

    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()

    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(runner_temp)
    env["FITDOCS_FORBIDDEN_STRINGS_CONTENT"] = _SYNTHETIC_SECRET_CONTENT

    write_result = _run_bash_body(write_body, cwd=tmp_path, env=env)
    assert write_result.returncode == 0

    check_result = _run_bash_body(check_body, cwd=_REPO_ROOT, env=env)
    assert check_result.returncode == 0, (
        f"the check step's run: body failed against a real match file: "
        f"stdout={check_result.stdout!r} stderr={check_result.stderr!r}"
    )


def test_fail_closed_step_body_exits_zero_when_the_property_holds(
    tmp_path: Path, _built_dist: Path
) -> None:
    """Runs the real "Prove the gate fails closed" `run:` text with
    `FITDOCS_FORBIDDEN_STRINGS` deliberately set (to a real, valid match
    file) in the PARENT environment -- so the step's own `env -u
    FITDOCS_FORBIDDEN_STRINGS` is what has to strip it before invoking the
    checker. If `env -u` named the wrong variable, the checker would see
    the real value, find a clean artifact, exit 0 -- and the wrapping
    script's own `-ne 1` guard would then treat that as the failure it's
    designed to catch, turning this whole step red."""
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    write_body = _run_body(steps, "Write the match data outside the checkout")
    fail_closed_body = _substitute_once(
        _run_body(steps, "Prove the gate fails closed"),
        "--dist-dir dist",
        f"--dist-dir {_built_dist}",
    )

    runner_temp = tmp_path / "runner_temp"
    runner_temp.mkdir()

    write_env = os.environ.copy()
    write_env["RUNNER_TEMP"] = str(runner_temp)
    write_env["FITDOCS_FORBIDDEN_STRINGS_CONTENT"] = _SYNTHETIC_SECRET_CONTENT
    write_result = _run_bash_body(write_body, cwd=tmp_path, env=write_env)
    assert write_result.returncode == 0

    match_file = runner_temp / "forbidden-strings.txt"
    assert match_file.is_file(), "positive control: the write step did not run"

    env = os.environ.copy()
    env["FITDOCS_FORBIDDEN_STRINGS"] = str(match_file)

    result = _run_bash_body(fail_closed_body, cwd=_REPO_ROOT, env=env)
    assert result.returncode == 0, (
        f"the fail-closed step's run: body did not exit 0 when the "
        f"underlying gate correctly failed closed: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "gate_not_run" in result.stdout


def test_fail_closed_guard_rejects_a_non_one_exit_code_even_with_the_right_text(
    tmp_path: Path,
) -> None:
    """Pins the `-ne 1` guard itself: a stand-in for `check_artifacts` that
    prints `gate_not_run` but exits 2 (a hard error, never a gate-not-run
    failure) must still be rejected by the wrapping script -- proving the
    guard checks the EXACT exit code, not merely the presence of the
    word."""
    doc = _workflow()
    steps = _steps(_gates_job(doc))
    fail_closed_body = _run_body(steps, "Prove the gate fails closed")

    cmd_pattern = re.compile(r"uv run python -m scripts\.check_artifacts[^\n)]*")
    match = cmd_pattern.search(fail_closed_body)
    assert match is not None, (
        "fail-closed step does not invoke scripts.check_artifacts where expected"
    )
    stub = "bash -c 'echo gate_not_run; exit 2'"
    mutated_body = fail_closed_body.replace(match.group(0), stub)

    result = _run_bash_body(mutated_body, cwd=_REPO_ROOT, env=os.environ.copy())
    assert result.returncode == 1, (
        "the fail-closed guard accepted a non-1 exit code as a valid "
        "gate-not-run failure just because the output text matched"
    )


# --- (k) actionlint, when present -------------------------------------------


def test_actionlint_if_available() -> None:
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        pytest.skip("actionlint is not installed in this environment")
    result = subprocess.run(
        [actionlint, str(_CI_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
