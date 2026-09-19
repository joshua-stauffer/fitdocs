"""Conformance for task 6.3: the tag-triggered gate and verification chain
(design.md "Release pipeline", "CiWorkflow and ReleaseWorkflow"; Req 5.2,
5.3, 5.5, 5.8, 5.10).

`.github/workflows/release.yml` is the GATE CHAIN ONLY today: `gates`,
`version`, `build`, `check`, `verify-artifact`, each `needs:` the job before
it so a failure anywhere prevents every later job (5.8). Task 6.4 appends
three more jobs (`publish-testpypi`, `publish-pypi`, `verify-published`) to
the SAME file, and is the one that relaxes the "mentions no publishing
surface" assertion below and adds `id-token: write` -- until then, this file
publishes nothing and needs no credential.

Groups:

(a) trigger is `push.tags` including `v*`; top-level `permissions` is
    exactly `{contents: read}`; the job set is exactly the five gate-chain
    jobs; each job `needs` exactly the job before it, and the chain is
    linear in that order (gates -> version -> build -> check ->
    verify-artifact).
(b) the release job names are a subset of the eight `docs/releasing.md`
    "Automation jobs" table names, and the step-to-job mapping there
    matches for steps 1, 3, 4, 5, 6 (reusing
    `tests.test_releasing_docs`'s own table-parsing helpers).
(c) the `gates` job's three gate steps run the same commands as
    `CONTRIBUTING.md`'s "The three quality gates" section, as a set.
(d) `version` runs `--no-artifacts --tag "${GITHUB_REF_NAME}"` and never
    mentions a build.
(e) `build` uploads an artifact named `dist`.
(f) `check` downloads the `dist` artifact, writes the match data under
    `$RUNNER_TEMP`, guards an empty secret with `gate_not_run`, and runs the
    checker with `--tag` and WITHOUT `--no-version-check` or
    `--no-artifacts`.
(g) `verify-artifact` installs from `dist/` (never `--from .`), exports the
    tool-directory variables before the install, invokes the installed
    binary only by its `$UV_TOOL_BIN_DIR` path, and compares `--version`
    against `${GITHUB_REF_NAME#v}`.
(h) no job or step anywhere mentions `uv publish`, `pypi`, `twine`, or
    `id-token` yet (task 6.4 relaxes this); every `uses:` action is pinned
    to a version tag or a 40-hex commit SHA.
(i) every `scripts.<module>` invocation uses only flags that module's own
    argparse parser accepts.
(j) **Executes the parsed `run:` bodies** for `version`, `build`, `check`,
    and `verify-artifact` through `bash -eo pipefail -c`, from a real
    checkout / scratch directory, substituting only the literal `dist`
    output/input path for a scratch path (substitution count asserted to be
    exactly one, as in `tests/test_ci_workflow.py`) -- so a wrong flag, a
    wrong path, or a broken guard in any of the four bodies is executed and
    observed, not merely pattern-matched. This includes the empty-but-set
    secret case for the `check` job's write step (mirroring
    `tests/test_ci_workflow.py`'s own empty-secret execution test), which a
    purely static ever-present-token check cannot distinguish from a
    correctly-guarded body.
(k) the artifact hand-off path is pinned end to end: `build`'s
    upload-artifact `path:`, both `check` and `verify-artifact`'s
    download-artifact `path:` (normalized of a trailing slash), and every
    consuming command's literal (`--out-dir dist`, `--dist-dir dist`,
    `--from dist/`) all equal `"dist"` -- not merely each other's job name.
(l) none of today's five gate-chain jobs declares its own job-level
    `permissions:` key (task 6.4 is expected to add one to each of its own
    three jobs; this assertion is scoped to today's five only).
(m) every `"$UV_TOOL_BIN_DIR/fitdocs"` invocation line `docs/releasing.md`
    step 6 names appears verbatim in the `verify-artifact` job's body,
    parsed out of the doc rather than re-typed.
"""

from __future__ import annotations

import itertools
import os
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import scripts.build_release as build_release
import scripts.check_artifacts as check_artifacts
import yaml

from tests.test_ci_workflow import (
    _run_bash_body,
    _substitute_once,
)
from tests.test_releasing_docs import (
    _EXPECTED_JOBS,
    _EXPECTED_STEP_TO_JOB,
    _automation_job_table_rows,
    _fenced_blocks,
    _section,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RELEASE_PATH = _REPO_ROOT / ".github" / "workflows" / "release.yml"
_CONTRIB_PATH = _REPO_ROOT / "CONTRIBUTING.md"

_GATE_CHAIN_JOBS = ("gates", "version", "build", "check", "verify-artifact")

_GATE_STEP_NAMES = (
    "Run the test suite",
    "Lint and check formatting",
    "Run the strict type check",
)

_PARSER_FACTORY_BY_MODULE = {
    "check_artifacts": check_artifacts._build_parser,
    "build_release": build_release._build_parser,
}

_VERSION_PIN_RE = re.compile(r"@(v\d+(\.\d+){0,2}|[0-9a-f]{40})$")


def _manifest_version() -> str:
    """The real `[project].version` -- read at runtime rather than embedded
    as a literal, so this file never adds a second copy of the released
    version literal for `tests/test_version_identity.py`'s repository-wide
    scan to trip over. Using the tag that actually equals the manifest
    version also exercises the realistic "tag agrees with the manifest, but
    the changelog has no entry yet" release state, not a synthetic
    mismatch."""
    manifest = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    version = manifest["project"]["version"]
    assert isinstance(version, str) and version
    return version


def _text() -> str:
    assert _RELEASE_PATH.is_file(), ".github/workflows/release.yml does not exist"
    return _RELEASE_PATH.read_text(encoding="utf-8")


def _workflow() -> dict[Any, Any]:
    doc = yaml.safe_load(_text())
    assert isinstance(doc, dict)
    return doc


def _jobs(doc: dict[Any, Any]) -> dict[str, Any]:
    jobs = doc["jobs"]
    assert isinstance(jobs, dict)
    return jobs


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return steps


def _job_steps(doc: dict[Any, Any], job_name: str) -> list[dict[str, Any]]:
    return _steps(_jobs(doc)[job_name])


def _step_by_name(steps: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [s for s in steps if s.get("name") == name]
    assert len(matches) == 1, (
        f"expected exactly one step named {name!r}, found {len(matches)}"
    )
    return matches[0]


def _contributing_gate_commands() -> set[str]:
    contrib_text = _CONTRIB_PATH.read_text(encoding="utf-8")
    contrib_section = _section(contrib_text, "The three quality gates")
    commands = {block.strip() for block in _fenced_blocks(contrib_section)}
    assert commands, (
        "positive control failed -- CONTRIBUTING.md's quality-gates "
        "section has no fenced commands"
    )
    return commands


# --- (a) trigger, permissions, job set, linear needs chain ------------------


def test_trigger_is_push_tags_including_v_star() -> None:
    doc = _workflow()
    triggers = doc[True]  # PyYAML parses the bare key `on` as True
    assert isinstance(triggers, dict)
    push = triggers["push"]
    assert isinstance(push, dict)
    assert "v*" in push["tags"]


def test_top_level_permissions_are_exactly_contents_read() -> None:
    doc = _workflow()
    assert doc["permissions"] == {"contents": "read"}


def test_job_set_is_exactly_the_five_gate_chain_jobs() -> None:
    doc = _workflow()
    jobs = _jobs(doc)
    assert set(jobs.keys()) == set(_GATE_CHAIN_JOBS), (
        f"expected exactly {_GATE_CHAIN_JOBS!r}, got {sorted(jobs.keys())!r}"
    )


def test_no_gate_chain_job_declares_its_own_permissions_key() -> None:
    """None of today's five gate-chain jobs needs any permission beyond the
    top-level `contents: read` -- a job-level `permissions:` block here
    would silently widen (or narrow) that grant for just one job. Task 6.4
    is expected to add a job-scoped `permissions: {id-token: write}` to
    each of its own three upload/verification jobs; this assertion is
    scoped to today's five and must not be read as forbidding that."""
    doc = _workflow()
    jobs = _jobs(doc)
    for name in _GATE_CHAIN_JOBS:
        assert "permissions" not in jobs[name], (
            f"job {name!r} declares its own permissions: block: "
            f"{jobs[name].get('permissions')!r}"
        )


def test_needs_chain_is_linear_gates_through_verify_artifact() -> None:
    doc = _workflow()
    jobs = _jobs(doc)
    # Positive control: every job after the first names a `needs` at all.
    assert all("needs" in jobs[name] for name in _GATE_CHAIN_JOBS[1:]), (
        "not every downstream job declares a needs: dependency"
    )
    for earlier, later in itertools.pairwise(_GATE_CHAIN_JOBS):
        needs = jobs[later]["needs"]
        assert needs == earlier, (
            f"job {later!r} needs {needs!r}, expected exactly {earlier!r}"
        )
    # gates itself declares no needs -- it is the chain's root.
    assert "needs" not in jobs["gates"]


# --- (b) job names are a subset of the doc's eight, mapping matches --------


def test_job_names_are_a_subset_of_the_docs_eight_automation_jobs() -> None:
    doc = _workflow()
    job_names = set(_jobs(doc).keys())
    assert job_names <= _EXPECTED_JOBS, (
        f"release.yml job names {job_names} are not a subset of the "
        f"documented eight {_EXPECTED_JOBS}"
    )


def test_step_to_job_mapping_matches_the_docs_table_for_steps_1_3_4_5_6() -> None:
    from tests.test_releasing_docs import _text as _docs_text

    rows = _automation_job_table_rows(_docs_text())
    step_to_job: dict[int, str] = {}
    for step_cell, job_cell in rows:
        num_match = re.match(r"(\d+)\.", step_cell)
        assert num_match is not None
        job_match = re.search(r"`([a-z-]+)`", job_cell)
        if job_match is not None:
            step_to_job[int(num_match.group(1))] = job_match.group(1)
    for step_num in (1, 3, 4, 5, 6):
        assert step_to_job[step_num] == _EXPECTED_STEP_TO_JOB[step_num]
        # ... and that expected job actually exists as a job name today.
        assert _EXPECTED_STEP_TO_JOB[step_num] in _jobs(_workflow())


# --- (c) gates job's three gate steps equal CONTRIBUTING.md's commands -----


def test_gates_job_run_lines_equal_contributing_commands_exactly() -> None:
    contrib_commands = _contributing_gate_commands()
    doc = _workflow()
    steps = _job_steps(doc, "gates")
    run_lines: set[str] = set()
    for name in _GATE_STEP_NAMES:
        step = _step_by_name(steps, name)
        run = step.get("run")
        assert run is not None, f"step {name!r} has no run: command"
        run_lines.add(run.strip())
    assert run_lines == contrib_commands


def test_gates_job_does_not_build_or_check_artifacts() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "gates")
    for step in steps:
        run = step.get("run", "") or ""
        assert "scripts.build_release" not in run
        assert "scripts.check_artifacts" not in run


# --- (d) version: --no-artifacts --tag, no build mention -------------------


def test_version_job_runs_no_artifacts_tag_with_ref_name() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "version")
    matches = [s for s in steps if "scripts.check_artifacts" in (s.get("run") or "")]
    assert len(matches) == 1, (
        f"expected exactly one scripts.check_artifacts step in version, "
        f"found {len(matches)}"
    )
    run = matches[0]["run"]
    assert "--no-artifacts" in run
    assert "--tag" in run
    assert "GITHUB_REF_NAME" in run


def test_version_job_mentions_no_build() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "version")
    for step in steps:
        run = step.get("run", "") or ""
        assert "scripts.build_release" not in run


# --- (e) build uploads dist -------------------------------------------------


def test_build_job_uploads_artifact_named_dist() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "build")
    upload_steps = [
        s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")
    ]
    assert len(upload_steps) == 1
    with_block = upload_steps[0].get("with", {})
    assert with_block.get("name") == "dist"


def _normalized(path: str) -> str:
    return path.rstrip("/")


def test_artifact_paths_consistent_across_upload_download_consumers() -> None:
    """The `dist` name alone does not pin the *path* every job actually
    reads/writes: `actions/upload-artifact` and `actions/download-artifact`
    each carry their own independent `path:`, and each consuming command
    (`--out-dir`, `--dist-dir`, `--from`) reads a literal string that must
    agree with those paths, not merely with each other's job name. Every one
    of these six values is asserted against the single literal `"dist"`,
    so a divergence anywhere in the chain -- upload writes to a different
    directory than build's `--out-dir`, check downloads to somewhere its
    `--dist-dir` does not read, or verify-artifact's `--from` does not match
    where it downloaded to -- is caught here even though each job's own
    tests above pass individually."""
    doc = _workflow()

    build_steps = _job_steps(doc, "build")
    build_run = _step_by_name(build_steps, "Build the artifacts")["run"]
    upload_step = next(
        s
        for s in build_steps
        if s.get("uses", "").startswith("actions/upload-artifact")
    )
    upload_path = upload_step.get("with", {}).get("path")
    assert upload_path is not None

    check_steps = _job_steps(doc, "check")
    check_run = _step_by_name(check_steps, "Check the artifacts")["run"]
    check_download_step = next(
        s
        for s in check_steps
        if s.get("uses", "").startswith("actions/download-artifact")
    )
    check_download_path = check_download_step.get("with", {}).get("path")
    assert check_download_path is not None

    verify_steps = _job_steps(doc, "verify-artifact")
    verify_download_step = next(
        s
        for s in verify_steps
        if s.get("uses", "").startswith("actions/download-artifact")
    )
    verify_download_path = verify_download_step.get("with", {}).get("path")
    assert verify_download_path is not None
    verify_install_run = next(
        s["run"] for s in verify_steps if "uv tool install" in (s.get("run") or "")
    )

    # Every hand-off point names the same directory, normalized of a
    # trailing slash (upload-artifact's `path:` and a `--from dist/` glob
    # both legitimately carry one; the flags do not).
    assert _normalized(upload_path) == "dist"
    assert _normalized(check_download_path) == "dist"
    assert _normalized(verify_download_path) == "dist"

    # ... and every consuming command reads/writes that same literal.
    assert "--out-dir dist" in build_run
    assert "--dist-dir dist" in check_run
    assert re.search(r"--from dist/", verify_install_run)


# --- (f) check downloads dist, guards secret, runs full checker -----------


def test_check_job_downloads_dist_artifact() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "check")
    download_steps = [
        s for s in steps if s.get("uses", "").startswith("actions/download-artifact")
    ]
    assert len(download_steps) == 1
    with_block = download_steps[0].get("with", {})
    assert with_block.get("name") == "dist"


def test_check_job_write_step_writes_under_runner_temp_and_guards_gate_not_run() -> (
    None
):
    doc = _workflow()
    steps = _job_steps(doc, "check")
    step = _step_by_name(steps, "Write the match data outside the checkout")
    run = step["run"]
    assert "RUNNER_TEMP" in run
    assert "GITHUB_WORKSPACE" not in run
    assert "exit 1" in run
    assert "gate_not_run" in run
    env = step.get("env", {})
    assert env.get("FITDOCS_FORBIDDEN_STRINGS_CONTENT") == (
        "${{ secrets.FITDOCS_FORBIDDEN_STRINGS_CONTENT }}"
    )


def test_check_write_step_body_exits_one_when_the_secret_content_is_empty(
    tmp_path: Path,
) -> None:
    """Mirrors `tests/test_ci_workflow.py`'s
    `test_write_step_body_exits_one_when_the_secret_content_is_empty`
    against `release.yml`'s own `check` job body -- an empty-but-set secret
    is exactly the fork-PR / misconfigured-repository shape, and it must
    fail exactly like the fully-unset case (`gate_not_run`, exit 1), never
    write a match file, and never fall through to a silent pass. An
    ever-present-token version of the guard (for example `if false; then
    ... fi` with the error text left in place but unreachable) would leave
    the static assertions in
    `test_check_job_write_step_writes_under_runner_temp_and_guards_gate_not_run`
    green while this executes the real body and observes exit 0 -- the gap
    that test alone cannot see."""
    doc = _workflow()
    steps = _job_steps(doc, "check")
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
    assert not list(runner_temp.iterdir()), (
        "the write step wrote a match file despite the empty secret: "
        f"{list(runner_temp.iterdir())!r}"
    )


def test_check_job_runs_full_checker_with_tag_and_neither_skip_flag() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "check")
    step = _step_by_name(steps, "Check the artifacts")
    run = step["run"]
    assert "scripts.check_artifacts" in run
    assert "--tag" in run
    assert "--dist-dir dist" in run
    assert "--no-version-check" not in run
    assert "--no-artifacts" not in run
    match = re.search(r"FITDOCS_FORBIDDEN_STRINGS=(\S+)", run)
    assert match is not None
    assert "RUNNER_TEMP" in match.group(1)


# --- (g) verify-artifact installs from dist/, exports before install, ------
#     invokes by path, strips the v ------------------------------------------


def test_verify_artifact_installs_from_dist_never_from_dot() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "verify-artifact")
    install_steps = [s for s in steps if "uv tool install" in (s.get("run") or "")]
    assert len(install_steps) == 1
    run = install_steps[0]["run"]
    assert re.search(r"--from dist/", run), (
        f"verify-artifact does not install --from dist/: {run!r}"
    )
    assert "--from ." not in run
    assert "--from  " not in run.replace("--from dist/", "")


def test_verify_artifact_exports_tool_dirs_before_install() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "verify-artifact")
    install_steps = [s for s in steps if "uv tool install" in (s.get("run") or "")]
    assert len(install_steps) == 1
    run = install_steps[0]["run"]
    assert "export UV_TOOL_DIR=" in run
    assert "export UV_TOOL_BIN_DIR=" in run
    install_idx = run.index("uv tool install")
    assert run.index("export UV_TOOL_DIR=") < install_idx
    assert run.index("export UV_TOOL_BIN_DIR=") < install_idx


def test_verify_artifact_invokes_by_tool_bin_dir_path_never_bareword() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "verify-artifact")
    install_steps = [s for s in steps if "uv tool install" in (s.get("run") or "")]
    run = install_steps[0]["run"]
    assert '"$UV_TOOL_BIN_DIR/fitdocs"' in run
    # A bareword invocation would resolve through PATH to whatever copy (if
    # any) happens to be installed on the runner, silently exercising the
    # wrong binary. None of the three invocation forms may appear unqualified.
    assert re.search(r"(?<!\$UV_TOOL_BIN_DIR/)\bfitdocs --version\b", run) is None
    assert re.search(r"(?<!\$UV_TOOL_BIN_DIR/)\bfitdocs --help\b", run) is None
    assert re.search(r"(?<!\$UV_TOOL_BIN_DIR/)\bfitdocs plugins\b", run) is None


def test_verify_artifact_compares_version_to_ref_name_stripped_of_v() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "verify-artifact")
    install_steps = [s for s in steps if "uv tool install" in (s.get("run") or "")]
    run = install_steps[0]["run"]
    assert "${GITHUB_REF_NAME#v}" in run
    assert (
        'test "$("$UV_TOOL_BIN_DIR/fitdocs" --version)" = "${GITHUB_REF_NAME#v}"' in run
    )


def test_verify_artifact_does_not_sync_or_checkout_source() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "verify-artifact")
    for step in steps:
        uses = step.get("uses", "") or ""
        assert not uses.startswith("actions/checkout"), (
            "verify-artifact checks out the source tree; the install must "
            "come from the built artifact alone (design decision (c))"
        )
        run = step.get("run", "") or ""
        assert not run.strip().startswith("uv sync"), (
            f"verify-artifact syncs project dependencies: {run!r}"
        )


def test_verify_artifact_body_contains_every_step6_tool_bin_invocation() -> None:
    """`docs/releasing.md` step 6 is the manual equivalent of this job
    (Req 5.10). Its `"$UV_TOOL_BIN_DIR/fitdocs" --version` and
    `"$UV_TOOL_BIN_DIR/fitdocs" --help` lines are parsed straight out of the
    doc's own fenced block, not re-typed here, and each must appear
    verbatim in the workflow's install-and-smoke-test body -- a `--help`
    invocation dropped from the workflow would leave every other assertion
    in this module green."""
    from tests.test_releasing_docs import _text as _docs_text

    doc_section = _section(_docs_text(), "6. Clean-environment verification")
    doc_invocation_lines = [
        line.strip()
        for block in _fenced_blocks(doc_section)
        for line in block.splitlines()
        if line.strip().startswith('"$UV_TOOL_BIN_DIR/fitdocs"')
    ]
    # Positive control: the doc must actually name at least the version and
    # help invocations, or this walk checks nothing.
    assert len(doc_invocation_lines) >= 2, (
        f"expected at least 2 $UV_TOOL_BIN_DIR invocation lines in "
        f"docs/releasing.md step 6, found {doc_invocation_lines!r}"
    )

    doc = _workflow()
    steps = _job_steps(doc, "verify-artifact")
    install_run = next(
        s["run"] for s in steps if "uv tool install" in (s.get("run") or "")
    )
    for line in doc_invocation_lines:
        assert line in install_run, (
            f"docs/releasing.md step 6 names {line!r}, which does not "
            f"appear verbatim in release.yml's verify-artifact body"
        )


# --- (h) no publish surface yet; every action pinned -----------------------


def test_workflow_publishes_nothing_yet_and_pins_every_action() -> None:
    # This assertion is intentionally strict for task 6.3: no job or step
    # anywhere mentions a publishing surface. Task 6.4 appends the publish
    # jobs to this same file and is expected to relax this exact assertion
    # (it will legitimately add `uv publish`-adjacent action refs, `pypi`,
    # and `id-token: write` for its own three jobs) -- this is a downgrade
    # to record in that task's own report, not a silent one.
    text = _text()
    lowered = text.lower()
    for forbidden in ("uv publish", "pypi", "twine", "id-token"):
        assert forbidden not in lowered, f"release workflow mentions {forbidden!r}"
    uses_lines = re.findall(r"uses:\s*(\S+)", text)
    assert len(uses_lines) >= 2, "expected at least two uses: actions"
    for use in uses_lines:
        assert _VERSION_PIN_RE.search(use), (
            f"action {use!r} is not pinned to a version tag or commit SHA"
        )
    assert not _VERSION_PIN_RE.search("actions/checkout@main")


def test_setup_uv_is_pinned_to_a_specific_release_not_a_bare_major() -> None:
    text = _text()
    matches = re.findall(r"astral-sh/setup-uv@(\S+)", text)
    assert matches, "release workflow does not pin astral-sh/setup-uv"
    for ref in matches:
        assert re.fullmatch(r"v\d+\.\d+(\.\d+)?|[0-9a-f]{40}", ref), (
            f"astral-sh/setup-uv is pinned to {ref!r}, not a minor-or-patch "
            "release tag or a commit SHA"
        )


# --- (i) every scripts.<module> command uses only real flags --------------

_SCRIPTS_CMD_RE = re.compile(r"scripts\.(\w+)([^\n&|]*)")


def test_every_scripts_command_uses_only_real_flags() -> None:
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


# --- (j) execute the parsed run: bodies for real ---------------------------


_SYNTHETIC_SECRET_CONTENT = (
    "ReleaseWorkflowSyntheticNeedleLineOne\nReleaseWorkflowSyntheticNeedleLineTwo\n"
)


def _run_body(steps: list[dict[str, Any]], name: str) -> str:
    step = _step_by_name(steps, name)
    run = step.get("run")
    assert isinstance(run, str), f"step {name!r} has no run: body"
    return run


def test_version_body_exits_one_with_version_mismatch_today(tmp_path: Path) -> None:
    doc = _workflow()
    steps = _job_steps(doc, "version")
    body = [s for s in steps if "scripts.check_artifacts" in (s.get("run") or "")][0][
        "run"
    ]
    version = _manifest_version()
    env = os.environ.copy()
    env["GITHUB_REF_NAME"] = f"v{version}"
    result = _run_bash_body(body, cwd=_REPO_ROOT, env=env)
    assert result.returncode == 1, (
        f"expected exit 1 (no released changelog entry for {version} yet), "
        f"got {result.returncode}: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "version_mismatch" in result.stdout + result.stderr


def test_build_body_actually_builds(tmp_path: Path) -> None:
    doc = _workflow()
    steps = _job_steps(doc, "build")
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


@pytest.fixture(scope="module")
def _built_dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("release_workflow_dist")
    build_release.build(out_dir=out_dir, source_date_epoch=315532800)
    return out_dir


def test_check_body_exits_one_with_exactly_one_version_mismatch_and_no_other_kind(
    tmp_path: Path, _built_dist: Path
) -> None:
    doc = _workflow()
    steps = _job_steps(doc, "check")
    write_body = _run_body(steps, "Write the match data outside the checkout")
    check_body = _substitute_once(
        _run_body(steps, "Check the artifacts"),
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

    version = _manifest_version()
    check_env = os.environ.copy()
    check_env["RUNNER_TEMP"] = str(runner_temp)
    check_env["GITHUB_REF_NAME"] = f"v{version}"
    check_result = _run_bash_body(check_body, cwd=_REPO_ROOT, env=check_env)
    assert check_result.returncode == 1, (
        f"expected exit 1 (no released changelog entry for {version} yet), "
        f"got {check_result.returncode}: stdout={check_result.stdout!r} "
        f"stderr={check_result.stderr!r}"
    )
    output = check_result.stdout + check_result.stderr
    assert output.count("version_mismatch") == 1, (
        f"expected exactly one version_mismatch violation, got: {output!r}"
    )
    assert "gate_not_run" not in output, (
        "the artifact gates did not pass cleanly against the real match "
        f"file -- unexpected gate_not_run in: {output!r}"
    )
    assert "encumbered_content" not in output, (
        f"unexpected encumbered_content violation in: {output!r}"
    )


def test_verify_artifact_body_exits_zero_and_version_matches_the_tag(
    tmp_path: Path, _built_dist: Path
) -> None:
    doc = _workflow()
    steps = _job_steps(doc, "verify-artifact")
    install_steps = [s for s in steps if "uv tool install" in (s.get("run") or "")]
    body = install_steps[0]["run"]

    scratch = tmp_path / "verify_scratch"
    dist = scratch / "dist"
    dist.mkdir(parents=True)
    for whl in _built_dist.glob("*.whl"):
        (dist / whl.name).write_bytes(whl.read_bytes())

    version = _manifest_version()
    env = os.environ.copy()
    env["GITHUB_REF_NAME"] = f"v{version}"
    result = _run_bash_body(body, cwd=scratch, env=env)
    assert result.returncode == 0, (
        f"the verify-artifact step's run: body failed: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    version_lines = [
        line
        for line in result.stdout.splitlines()
        if re.fullmatch(r"\d+\.\d+\.\d+", line)
    ]
    assert version_lines, f"no bare version line found in stdout: {result.stdout!r}"
    assert version_lines[0] == version
