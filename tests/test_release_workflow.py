"""Conformance for task 6.3 and task 6.4: the tag-triggered gate chain and
the publication and post-publication chain (design.md "Release pipeline",
"CiWorkflow and ReleaseWorkflow"; Req 2.5, 5.2, 5.3, 5.5, 5.6, 5.7, 5.8, 5.9,
5.10).

`.github/workflows/release.yml` is now the FULL eight-job chain:
`gates`, `version`, `build`, `check`, `verify-artifact` (task 6.3, the gate
chain -- publishes nothing, needs no credential), then `publish-testpypi`,
`publish-pypi`, `verify-published` (task 6.4, the publication and
post-publication chain), each `needs:` the job before it so a failure
anywhere prevents every later job (5.8).

TASK 6.4 DELIBERATELY RELAXES two of task 6.3's own assertions, each noted
where it happens below:
- `test_workflow_publishes_nothing_yet_and_pins_every_action` no longer
  forbids `pypi`/`id-token`/`uv publish`-adjacent action refs -- it now
  positively requires them, scoped to exactly the two publish jobs, and
  still pins every `uses:` action's version.
- `test_job_set_is_exactly_the_five_gate_chain_jobs` remains as a
  gate-chain-only assertion (renamed group below to `_GATE_CHAIN_JOBS`); a
  new assertion pins the full eight-job set instead.

Groups:

(a) trigger is `push.tags` including `v*`; top-level `permissions` is
    exactly `{contents: read}`; the gate-chain sub-sequence is exactly the
    five gate-chain jobs; the FULL job set is exactly the documented eight;
    each job `needs` exactly the job before it, and the chain is linear in
    that order across ALL eight (gates -> version -> build -> check ->
    verify-artifact -> publish-testpypi -> publish-pypi -> verify-published).
(b) the release job names equal the eight `docs/releasing.md` "Automation
    jobs" table names exactly, and the step-to-job mapping there matches for
    steps 1, 3, 4, 5, 6, 8, 9, 10 (reusing `tests.test_releasing_docs`'s own
    table-parsing helpers).
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
(h) RELAXED BY TASK 6.4: `twine` and bare `uv publish` still never appear
    anywhere; `pypi` and `id-token` now appear, but ONLY inside
    `publish-testpypi` and `publish-pypi`; every `uses:` action anywhere
    (gate-chain and publish jobs alike) is still pinned to a version tag or
    a 40-hex commit SHA.
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
(l) none of the five gate-chain jobs declares its own job-level
    `permissions:` key -- this remains true after task 6.4 (the gate chain
    is untouched); `id-token: write` appears ONLY as the two publish jobs'
    job-level `permissions`, nowhere else (not the gate chain, not
    `verify-published`, not the top level).
(m) every `"$UV_TOOL_BIN_DIR/fitdocs"` invocation line `docs/releasing.md`
    step 6 names appears verbatim in the `verify-artifact` job's body,
    parsed out of the doc rather than re-typed.
(n) `publish-testpypi` and `publish-pypi` are inline steps (no
    `jobs.*.uses:` reusable-workflow call anywhere in the file); both
    download the `dist` artifact to `dist`; both use
    `pypa/gh-action-pypi-publish` pinned to an immutable `vX.Y.Z` tag or a
    40-hex SHA, never the floating `release/v1` alias, a bare `@v1`, or
    `@main`.
(o) `publish-testpypi` sets `repository-url: https://test.pypi.org/legacy/`
    and environment `testpypi`; `publish-pypi` sets no `repository-url` (or
    PyPI's own), environment `pypi`, and `skip-existing: false` explicitly
    (2.5).
(p) `verify-published` checks out nothing, downloads no artifact, runs no
    `uv sync`; installs `fitdocs==${GITHUB_REF_NAME#v}` with `--no-cache`
    from the public index (no `--index`/`--index-url`/`--from`), invokes the
    binary only by its `$UV_TOOL_BIN_DIR` path, compares to the
    tag-with-`v`-stripped, and carries a bounded retry (`for`/`sleep`).
(q) no `secrets.` reference anywhere in the three publish/verify jobs (OIDC
    needs none), and no `UV_PUBLISH_TOKEN`/`TWINE_PASSWORD`/
    `PYPI_API_TOKEN` anywhere in the file (5.7).
(r) `verify-published`'s body is executed for real via a LOCAL variant that
    substitutes the install command's package spec (`"fitdocs==..."`) with
    `--from <a locally built wheel> fitdocs` exactly once, so the retry
    loop, the `test -x` existence check, the by-path invocation, and the
    version comparison all actually run -- once against the manifest's own
    version (exit 0) and once against a version nobody built, `9.9.9` (exit
    1, falsity). The publish jobs' own steps carry no `run:` bodies at all
    (every step is `uses:`), so there is nothing of theirs to execute; that
    absence is asserted, not silently skipped.
"""

from __future__ import annotations

import itertools
import os
import re
import subprocess
import time
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

_PUBLISH_JOBS = ("publish-testpypi", "publish-pypi", "verify-published")

_ALL_JOBS = _GATE_CHAIN_JOBS + _PUBLISH_JOBS

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


def test_job_set_is_exactly_the_eight_release_jobs() -> None:
    """RELAXED BY TASK 6.4: was "exactly the five gate-chain jobs"; the gate
    chain sub-sequence is still pinned separately by
    `test_needs_chain_is_linear_across_all_eight_jobs` below, but the job
    *set* the file declares is now the full eight (a job dropped, renamed,
    or an extra one added would fail here)."""
    doc = _workflow()
    jobs = _jobs(doc)
    assert set(jobs.keys()) == set(_ALL_JOBS), (
        f"expected exactly {_ALL_JOBS!r}, got {sorted(jobs.keys())!r}"
    )


def test_no_gate_chain_job_declares_its_own_permissions_key() -> None:
    """None of the five gate-chain jobs needs any permission beyond the
    top-level `contents: read` -- a job-level `permissions:` block here
    would silently widen (or narrow) that grant for just one job. The three
    task 6.4 jobs (`publish-testpypi`, `publish-pypi`, `verify-published`)
    DO each declare their own job-level `permissions:` block -- pinned
    exactly, not merely "some block exists", by the three tests immediately
    below -- and this assertion is deliberately scoped to the five
    gate-chain jobs only, so it does not contradict that."""
    doc = _workflow()
    jobs = _jobs(doc)
    for name in _GATE_CHAIN_JOBS:
        assert "permissions" not in jobs[name], (
            f"job {name!r} declares its own permissions: block: "
            f"{jobs[name].get('permissions')!r}"
        )


def test_publish_testpypi_permissions_are_exactly_id_token_write() -> None:
    doc = _workflow()
    assert _jobs(doc)["publish-testpypi"]["permissions"] == {"id-token": "write"}


def test_publish_pypi_permissions_are_exactly_id_token_write() -> None:
    """Exact equality, not merely "id-token is present": a stray extra key
    such as `contents: write` alongside `id-token: write` would still pass
    a membership check but grants this job a permission Req 5.7's
    short-lived, minimally-scoped credential exchange does not call for."""
    doc = _workflow()
    assert _jobs(doc)["publish-pypi"]["permissions"] == {"id-token": "write"}


def test_verify_published_permissions_are_exactly_contents_read() -> None:
    """`verify-published` authenticates nothing and publishes nothing -- its
    permissions must be exactly the read-only grant, never `id-token` and
    never a widened `contents: write`."""
    doc = _workflow()
    assert _jobs(doc)["verify-published"]["permissions"] == {"contents": "read"}


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


def test_needs_chain_is_linear_across_all_eight_jobs() -> None:
    """Extends the gate-chain-only check above across the publish chain
    (5.8): `publish-pypi.needs: verify-artifact` (bypassing the rehearsal)
    or `verify-published.needs: publish-testpypi` (bypassing the approval
    gate) would each still pass every one of that job's OWN unit tests below
    -- only a walk of the full linear order catches a skipped link."""
    doc = _workflow()
    jobs = _jobs(doc)
    for earlier, later in itertools.pairwise(_ALL_JOBS):
        needs = jobs[later]["needs"]
        assert needs == earlier, (
            f"job {later!r} needs {needs!r}, expected exactly {earlier!r}"
        )


# --- (b) job names are a subset of the doc's eight, mapping matches --------


def test_job_names_are_a_subset_of_the_docs_eight_automation_jobs() -> None:
    doc = _workflow()
    job_names = set(_jobs(doc).keys())
    assert job_names <= _EXPECTED_JOBS, (
        f"release.yml job names {job_names} are not a subset of the "
        f"documented eight {_EXPECTED_JOBS}"
    )


def test_step_to_job_mapping_matches_the_docs_table_for_all_automated_steps() -> None:
    """Extended by task 6.4 from steps (1, 3, 4, 5, 6) to every automated
    step in the docs table, including the three this task adds (8, 9, 10)."""
    from tests.test_releasing_docs import _text as _docs_text

    rows = _automation_job_table_rows(_docs_text())
    step_to_job: dict[int, str] = {}
    for step_cell, job_cell in rows:
        num_match = re.match(r"(\d+)\.", step_cell)
        assert num_match is not None
        job_match = re.search(r"`([a-z-]+)`", job_cell)
        if job_match is not None:
            step_to_job[int(num_match.group(1))] = job_match.group(1)
    for step_num in (1, 3, 4, 5, 6, 8, 9, 10):
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


# --- (n) publish jobs are inline, download dist, use the pinned action ----


def _publish_download_step(doc: dict[Any, Any], job_name: str) -> dict[str, Any]:
    steps = _job_steps(doc, job_name)
    matches = [
        s for s in steps if s.get("uses", "").startswith("actions/download-artifact")
    ]
    assert len(matches) == 1, (
        f"expected exactly one download-artifact step in {job_name!r}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _publish_upload_step(doc: dict[Any, Any], job_name: str) -> dict[str, Any]:
    steps = _job_steps(doc, job_name)
    matches = [
        s for s in steps if s.get("uses", "").startswith("pypa/gh-action-pypi-publish")
    ]
    assert len(matches) == 1, (
        f"expected exactly one pypa/gh-action-pypi-publish step in "
        f"{job_name!r}, found {len(matches)}"
    )
    return matches[0]


def test_both_publish_jobs_download_dist_to_dist() -> None:
    doc = _workflow()
    for job_name in ("publish-testpypi", "publish-pypi"):
        step = _publish_download_step(doc, job_name)
        with_block = step.get("with", {})
        assert with_block.get("name") == "dist"
        assert _normalized(with_block.get("path", "")) == "dist", (
            f"{job_name!r} downloads dist to {with_block.get('path')!r}, not 'dist'"
        )


def test_both_publish_jobs_use_the_same_pinned_publish_action() -> None:
    doc = _workflow()
    testpypi_upload = _publish_upload_step(doc, "publish-testpypi")["uses"]
    pypi_upload = _publish_upload_step(doc, "publish-pypi")["uses"]
    assert testpypi_upload == pypi_upload, (
        "publish-testpypi and publish-pypi use different action refs: "
        f"{testpypi_upload!r} != {pypi_upload!r}"
    )


def test_publish_jobs_packages_dir_matches_the_download_path() -> None:
    """The `dist` NAME alone (checked above) does not pin the *directory*
    the publish action actually uploads from: `packages-dir` is a
    completely independent input from `download-artifact`'s `path:`, and
    the two could diverge (upload from `.` while dist was downloaded to
    `dist/`, or vice versa) without either job's own tests above noticing.
    Checked for BOTH publish jobs, not only `publish-testpypi`."""
    doc = _workflow()
    for job_name in ("publish-testpypi", "publish-pypi"):
        download_path = (
            _publish_download_step(doc, job_name).get("with", {}).get("path")
        )
        packages_dir = (
            _publish_upload_step(doc, job_name).get("with", {}).get("packages-dir")
        )
        assert download_path is not None, f"{job_name!r} has no download path"
        assert packages_dir is not None, (
            f"{job_name!r} does not set packages-dir explicitly"
        )
        assert _normalized(download_path) == "dist", (
            f"{job_name!r} downloads to {download_path!r}, not 'dist'"
        )
        assert _normalized(packages_dir) == "dist", (
            f"{job_name!r} publishes packages-dir {packages_dir!r}, not 'dist'"
        )


def test_both_publish_jobs_pin_attestations_true_explicitly() -> None:
    """PEP 740 attestations default to on since v1.11.0, but the default is
    an upstream choice this file never states on its own -- pinned
    explicitly so a future upstream default flip (or a workflow edit) that
    silently disables them is caught here rather than discovered at a real
    release."""
    doc = _workflow()
    for job_name in ("publish-testpypi", "publish-pypi"):
        upload_with = _publish_upload_step(doc, job_name).get("with", {})
        assert "attestations" in upload_with, (
            f"{job_name!r} does not set attestations explicitly"
        )
        assert upload_with["attestations"] is True


# --- (o) testpypi/pypi environments, repository-url, skip-existing --------


def test_publish_testpypi_sets_repository_url_and_environment() -> None:
    doc = _workflow()
    job = _jobs(doc)["publish-testpypi"]
    assert job.get("environment", {}).get("name") == "testpypi"
    upload_with = _publish_upload_step(doc, "publish-testpypi").get("with", {})
    assert upload_with.get("repository-url") == "https://test.pypi.org/legacy/"


def test_publish_pypi_sets_environment_no_repository_url_override() -> None:
    doc = _workflow()
    job = _jobs(doc)["publish-pypi"]
    assert job.get("environment", {}).get("name") == "pypi"
    upload_with = _publish_upload_step(doc, "publish-pypi").get("with", {})
    repository_url = upload_with.get("repository-url")
    assert repository_url is None or "test.pypi.org" not in repository_url, (
        f"publish-pypi overrides repository-url to a TestPyPI endpoint: "
        f"{repository_url!r}"
    )


def test_publish_pypi_sets_skip_existing_false_explicitly() -> None:
    """2.5: a re-run of an already-published version must FAIL, not
    silently skip. `skip-existing` defaults to false in the action itself,
    but the key must be present and explicitly `False` here -- an absent
    key would rely on an upstream default this file never states."""
    doc = _workflow()
    upload_with = _publish_upload_step(doc, "publish-pypi").get("with", {})
    assert "skip-existing" in upload_with, (
        "publish-pypi does not set skip-existing explicitly"
    )
    assert upload_with["skip-existing"] is False


def test_publish_testpypi_also_sets_skip_existing_false_explicitly() -> None:
    """docs/releasing.md step 8: "a spent rehearsal version is not reused"
    -- 2.5's "publish exactly once" is not scoped to the public index only.
    Pinned explicitly here too (matching `publish-pypi` above) rather than
    left to the action's own default, for the same reason."""
    doc = _workflow()
    upload_with = _publish_upload_step(doc, "publish-testpypi").get("with", {})
    assert "skip-existing" in upload_with, (
        "publish-testpypi does not set skip-existing explicitly"
    )
    assert upload_with["skip-existing"] is False


# --- (p) verify-published: no checkout/download/sync, public-index install,
#     by-path invocation, bounded retry -------------------------------------


def _verify_published_install_run(doc: dict[Any, Any]) -> str:
    steps = _job_steps(doc, "verify-published")
    matches = [s for s in steps if "uv tool install" in (s.get("run") or "")]
    assert len(matches) == 1, (
        f"expected exactly one uv tool install step in verify-published, "
        f"found {len(matches)}"
    )
    run = matches[0]["run"]
    assert isinstance(run, str)
    return run


def test_verify_published_has_no_checkout_download_or_sync() -> None:
    doc = _workflow()
    steps = _job_steps(doc, "verify-published")
    for step in steps:
        uses = step.get("uses", "") or ""
        assert not uses.startswith("actions/checkout"), (
            "verify-published checks out the source tree"
        )
        assert not uses.startswith("actions/download-artifact"), (
            "verify-published downloads the built artifact -- it must "
            "install from the public index instead"
        )
        run = step.get("run", "") or ""
        assert not run.strip().startswith("uv sync"), (
            f"verify-published syncs project dependencies: {run!r}"
        )


def test_verify_published_installs_from_the_public_index_with_no_cache() -> None:
    run = _verify_published_install_run(_workflow())
    assert '"fitdocs==${GITHUB_REF_NAME#v}"' in run
    assert "--no-cache" in run
    for forbidden in ("--index-url", "--index ", "--extra-index-url", "--from"):
        assert forbidden not in run, (
            f"verify-published's install command names a package source "
            f"other than the public index: {forbidden!r} found in {run!r}"
        )


def test_verify_published_invokes_by_tool_bin_dir_path_and_compares_version() -> None:
    run = _verify_published_install_run(_workflow())
    assert '"$UV_TOOL_BIN_DIR/fitdocs"' in run
    assert (
        'test "$("$UV_TOOL_BIN_DIR/fitdocs" --version)" = "${GITHUB_REF_NAME#v}"' in run
    )
    assert re.search(r"(?<!\$UV_TOOL_BIN_DIR/)\bfitdocs --version\b", run) is None
    assert re.search(r"(?<!\$UV_TOOL_BIN_DIR/)\bfitdocs --help\b", run) is None


def test_verify_published_has_a_bounded_retry_loop() -> None:
    run = _verify_published_install_run(_workflow())
    assert re.search(r"\bfor\b.*\bdone\b", run, re.S), (
        f"verify-published's install command has no for/done retry loop: {run!r}"
    )
    assert "sleep" in run


# --- (q) no secrets, no long-lived token env var, anywhere in the file -----


def test_publish_and_verify_jobs_reference_no_secrets() -> None:
    doc = _workflow()
    for name in ("publish-testpypi", "publish-pypi", "verify-published"):
        job_text = _job_yaml(doc, name)
        assert "secrets." not in job_text, (
            f"job {name!r} references a secret, but OIDC needs none: {job_text!r}"
        )


def test_no_long_lived_publish_token_env_var_anywhere_in_the_file() -> None:
    text = _text()
    for forbidden in ("UV_PUBLISH_TOKEN", "TWINE_PASSWORD", "PYPI_API_TOKEN"):
        assert forbidden not in text, (
            f"release workflow references {forbidden!r}, a long-lived "
            "credential the OIDC-authenticated publish jobs must not need"
        )


# --- (h) publishing surface scoped to exactly the two publish jobs; --------
#     every action pinned -----------------------------------------------------


def _job_yaml(doc: dict[Any, Any], name: str) -> str:
    """A YAML dump of a single job's own subtree, so a substring search can
    be scoped to that job alone rather than the whole file."""
    return yaml.dump(_jobs(doc)[name])


def _job_yaml_excluding_needs(doc: dict[Any, Any], name: str) -> str:
    """Like `_job_yaml`, but with the `needs:` key removed first -- a
    downstream job's `needs: publish-pypi` legitimately contains the
    substring `pypi` as another job's *name*, which is not the publishing
    surface this check is scoped to."""
    job = dict(_jobs(doc)[name])
    job.pop("needs", None)
    return yaml.dump(job)


def test_workflow_never_mentions_uv_publish_or_twine_anywhere() -> None:
    # Unlike `pypi`/`id-token` (scoped below to the two publish jobs), a bare
    # `uv publish` invocation or `twine` reference would mean a long-lived
    # credential path outside the OIDC-authenticated action -- forbidden
    # everywhere in the file, gate chain and publish jobs alike.
    lowered = _text().lower()
    for forbidden in ("uv publish", "twine"):
        assert forbidden not in lowered, f"release workflow mentions {forbidden!r}"


def test_pypi_and_id_token_appear_only_in_the_two_publish_jobs() -> None:
    """RELAXES task 6.3's `test_workflow_publishes_nothing_yet_and_pins_every_action`,
    which forbade `pypi`/`id-token` anywhere: task 6.4 legitimately adds
    both, but ONLY inside `publish-testpypi` and `publish-pypi` -- not the
    gate chain, and not `verify-published` (which authenticates nothing).
    This is a second, independent check over the same property the exact
    `permissions ==` tests above already pin per job -- not a claim that it
    is the ONLY test that would catch a widening. `id-token: write` added to
    a gate-chain job is also caught by
    `test_no_gate_chain_job_declares_its_own_permissions_key`; added to
    `verify-published` is also caught by
    `test_verify_published_permissions_are_exactly_contents_read`; widened
    at the top level is also caught by
    `test_top_level_permissions_are_exactly_contents_read`. This test adds
    coverage for a widening spelled somewhere OTHER than the `permissions:`
    key entirely (an unused `with:` value, or a step `env:` naming
    `id-token` outside a `permissions:` block) that those structural checks
    would not see. It searches the PARSED job, so a YAML comment is not
    seen -- comments are dropped before the dump."""
    doc = _workflow()
    for name in _GATE_CHAIN_JOBS + ("verify-published",):
        job_text = _job_yaml_excluding_needs(doc, name).lower()
        assert "pypi" not in job_text, f"job {name!r} unexpectedly mentions 'pypi'"
        assert "id-token" not in job_text, (
            f"job {name!r} unexpectedly mentions 'id-token'"
        )
    assert "id-token" not in yaml.dump(doc.get("permissions", {})).lower()
    for name in ("publish-testpypi", "publish-pypi"):
        job_text = _job_yaml(doc, name).lower()
        # Positive control: each publish job must actually mention both, or
        # the negative assertions above are checking nothing meaningful.
        assert "pypi" in job_text, f"job {name!r} does not mention 'pypi' at all"
        assert "id-token" in job_text, f"job {name!r} does not set id-token"


def test_every_uses_action_is_pinned_to_a_version_tag_or_sha() -> None:
    text = _text()
    uses_lines = re.findall(r"uses:\s*(\S+)", text)
    assert len(uses_lines) >= 4, "expected at least four uses: actions"
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


_PYPI_PUBLISH_IMMUTABLE_PIN_RE = re.compile(r"^v\d+\.\d+\.\d+$|^[0-9a-f]{40}$")


def test_pypa_publish_action_is_pinned_to_an_immutable_tag_or_sha() -> None:
    """`pypa/gh-action-pypi-publish` handles the actual upload; its pin must
    be an immutable `vX.Y.Z` release tag or a 40-hex commit SHA, never the
    floating `release/v1` alias, a bare major (`@v1`), or a branch (`@main`).
    Of those three, only a bare major (`@v1`) would still satisfy the
    general `_VERSION_PIN_RE` used for every other action in this file
    (`release/v1` and `main` do not match its `v\\d+` pattern at all,
    verified directly against `_VERSION_PIN_RE`); this stricter,
    immutable-only regex exists specifically to reject that one case the
    general pin-format check would otherwise wave through for this action,
    where design.md calls for an immutable pin rather than merely "a
    version tag or a SHA"."""
    text = _text()
    matches = re.findall(r"pypa/gh-action-pypi-publish@(\S+)", text)
    assert len(matches) == 2, (
        f"expected exactly 2 pypa/gh-action-pypi-publish uses, found "
        f"{len(matches)}: {matches!r}"
    )
    for ref in matches:
        assert _PYPI_PUBLISH_IMMUTABLE_PIN_RE.fullmatch(ref), (
            f"pypa/gh-action-pypi-publish is pinned to {ref!r}, not an "
            "immutable vX.Y.Z tag or a 40-hex commit SHA"
        )
    assert not _PYPI_PUBLISH_IMMUTABLE_PIN_RE.fullmatch("release/v1")
    assert not _PYPI_PUBLISH_IMMUTABLE_PIN_RE.fullmatch("v1")
    assert not _PYPI_PUBLISH_IMMUTABLE_PIN_RE.fullmatch("main")


def test_no_jobs_uses_reusable_workflow_call_anywhere() -> None:
    """The publish jobs must stay inline (design.md: "the publish job is
    inline rather than factored into a reusable workflow, because trusted
    publishing does not work from one") -- a top-level `jobs.<name>.uses:`
    key (as opposed to a step's `uses:`) would turn a job into a call to a
    reusable workflow."""
    doc = _workflow()
    jobs = _jobs(doc)
    for name, job in jobs.items():
        assert "uses" not in job, (
            f"job {name!r} is a reusable-workflow call (jobs.*.uses:), "
            "which the design forbids for the publish jobs"
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


def test_version_body_exits_zero_against_the_manifest_tag(tmp_path: Path) -> None:
    doc = _workflow()
    steps = _job_steps(doc, "version")
    body = [s for s in steps if "scripts.check_artifacts" in (s.get("run") or "")][0][
        "run"
    ]
    version = _manifest_version()
    env = os.environ.copy()
    env["GITHUB_REF_NAME"] = f"v{version}"
    result = _run_bash_body(body, cwd=_REPO_ROOT, env=env)
    assert result.returncode == 0, (
        f"expected exit 0 (manifest, changelog and tag v{version} agree), "
        f"got {result.returncode}: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "version_mismatch" not in result.stdout + result.stderr


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


def test_check_body_exits_zero_with_no_violation_of_any_kind(
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
    assert check_result.returncode == 0, (
        f"expected exit 0 (manifest, changelog and tag v{version} agree; "
        f"artifacts clean), got {check_result.returncode}: "
        f"stdout={check_result.stdout!r} stderr={check_result.stderr!r}"
    )
    output = check_result.stdout + check_result.stderr
    assert "version_mismatch" not in output, (
        f"unexpected version_mismatch violation in: {output!r}"
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


# --- publish-testpypi/publish-pypi: no run: bodies exist to execute --------


# --- portability: workflow-level TERM/NO_COLOR, no job-level override -----
#
# Mirrors tests/test_ci_workflow.py's own structural assertions (see there
# for the full defect explanation): typer forces styled `--help` rendering
# whenever GITHUB_ACTIONS is set, breaking plain-text help assertions. The
# `gates` job here is the same shape as ci.yml's own `gates` job, so the same
# top-level env fix applies to release.yml.


def test_top_level_env_sets_term_dumb_and_no_color() -> None:
    doc = _workflow()
    env = doc.get("env")
    assert isinstance(env, dict), "release.yml has no top-level env: mapping"
    assert env.get("TERM") == "dumb", f"expected TERM: dumb, got {env.get('TERM')!r}"
    assert env.get("NO_COLOR") == "1", (
        f'expected NO_COLOR: "1" (string), got {env.get("NO_COLOR")!r}'
    )


def test_no_job_or_step_anywhere_overrides_term_away_from_dumb() -> None:
    doc = _workflow()
    jobs = _jobs(doc)
    for job_name, job in jobs.items():
        job_env = job.get("env", {})
        assert job_env.get("TERM", "dumb") == "dumb", (
            f"job {job_name!r} overrides TERM to {job_env.get('TERM')!r}"
        )
        for step in job.get("steps", []):
            step_env = step.get("env", {})
            assert step_env.get("TERM", "dumb") == "dumb", (
                f"job {job_name!r} step {step.get('name')!r} overrides TERM "
                f"to {step_env.get('TERM')!r}"
            )


def test_publish_job_steps_have_no_run_bodies() -> None:
    """Both publish jobs are `uses:`-only steps (download-artifact, then the
    pinned publish action) -- there is no shell body of theirs to execute
    the way the gate-chain jobs' bodies are executed above. Asserted
    explicitly, rather than left as a silent absence, per the task's own
    "no `run:` bodies to execute -- that is expected" note."""
    doc = _workflow()
    for job_name in ("publish-testpypi", "publish-pypi"):
        steps = _job_steps(doc, job_name)
        assert steps, f"job {job_name!r} has no steps at all"
        for step in steps:
            assert "run" not in step, (
                f"job {job_name!r} has a run: body ({step!r}), contradicting "
                "the inline-uses-only design for the publish jobs"
            )


# --- verify-published: NOT hermetic against the real network (it hits ------
#     PyPI) -- executed instead as a LOCAL variant, substituting the ---------
#     install command's package spec for a `--from <built wheel>` install, --
#     made offline-safe (real, warm uv cache; dead proxies; sleep 0) and -----
#     home-isolated (fake HOME/XDG dirs) so it runs fast, hits no real -------
#     network, and cannot pollute the machine actually running the suite ----


@pytest.fixture(scope="module")
def _real_uv_cache_dir() -> str:
    """The developer machine's actual, already-warm `uv` package cache
    (fitdocs' ~10 runtime dependencies were already downloaded into it by
    earlier tests in this session that ran real `uv tool install`/`uv
    sync` calls) -- reused, never copied or wiped, so the local-variant
    execution tests below can run fully `--offline` under dead proxies
    without a fresh per-test download. Isolating `HOME` for those tests
    does NOT redirect this: it is passed through explicitly via
    `UV_CACHE_DIR`, independent of `HOME`."""
    result = subprocess.run(
        ["uv", "cache", "dir"], capture_output=True, text=True, check=True
    )
    cache_dir = result.stdout.strip()
    assert cache_dir, "`uv cache dir` printed nothing"
    return cache_dir


def _hermetic_local_variant_env(
    tmp_path: Path, cache_dir: str, github_ref_name: str
) -> dict[str, str]:
    """Isolation for executing a LOCAL variant of `verify-published`'s body:
    a fake `HOME` (and `XDG_BIN_HOME`/`XDG_DATA_HOME` under it, belt and
    braces) so a workflow bug that drops an `export` and falls back to uv's
    default tool-install location writes into a throwaway tmp directory
    rather than the real machine's `~/.local/bin` / `~/.local/share/uv`
    (mirrors 5.4's `HOME=<tmp>` pattern); dead proxies on both schemes
    (`tests/test_wiki_integration_docs.py`'s own containment pattern) so any
    surprise network call fails loudly rather than silently succeeding; and
    the real, already-warm `uv` cache passed through via `UV_CACHE_DIR` so
    the body can run fully `--offline`."""
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["XDG_BIN_HOME"] = str(fake_home / "xdg_bin_home")
    env["XDG_DATA_HOME"] = str(fake_home / "xdg_data_home")
    env["UV_CACHE_DIR"] = cache_dir
    env["HTTP_PROXY"] = "http://127.0.0.1:9"
    env["HTTPS_PROXY"] = "http://127.0.0.1:9"
    env["GITHUB_REF_NAME"] = github_ref_name
    return env


_INSTALL_SUCCESS_MARKER = "Installed 1 executable: fitdocs"


def _local_variant_body(run: str, whl: Path) -> str:
    """The verify-published body with the public-index package spec swapped
    for a local wheel install, and made offline-safe for the test
    environment -- each substituted exactly once (`_substitute_once`
    asserts the single-occurrence count itself):

    - `"fitdocs==${GITHUB_REF_NAME#v}"` -> `--from <wheel> fitdocs` (the
      package spec itself, task-required).
    - `--no-cache` -> `--offline` (uses the warm, explicitly-passed
      `UV_CACHE_DIR` instead of forcing a real index round-trip; the real
      workflow keeps `--no-cache` for the actual release, where a fresh
      index check is exactly the point -- this substitution is a test-only
      hermeticity concession, not a claim that `--offline` belongs in
      `release.yml`).
    - `sleep 30` -> `sleep 0` (six real 30s sleeps would make a single red
      run over three minutes; the retry COUNT still executes six times on a
      genuine failure, only the delay is compressed).
    """
    local_run = _substitute_once(
        run, '"fitdocs==${GITHUB_REF_NAME#v}"', f"--from {whl} fitdocs"
    )
    local_run = _substitute_once(local_run, "--no-cache", "--offline")
    local_run = _substitute_once(local_run, "sleep 30", "sleep 0")
    return local_run


def test_verify_published_body_local_variant_substitutes_package_spec_once() -> None:
    """Confirms the substitution technique itself: the install command names
    the public-index package spec exactly once, so swapping it for a local
    wheel install is unambiguous (mirrors `_substitute_once`'s own
    single-occurrence guarantee, asserted here against the real body rather
    than assumed)."""
    run = _verify_published_install_run(_workflow())
    assert run.count('"fitdocs==${GITHUB_REF_NAME#v}"') == 1


def test_verify_published_local_variant_passes_when_the_version_matches(
    tmp_path: Path, _built_dist: Path, _real_uv_cache_dir: str
) -> None:
    """Not hermetic as written (it hits the public index) -- executed here
    as a LOCAL, offline, home-isolated variant (see `_local_variant_body`
    and `_hermetic_local_variant_env`) so the retry loop, the `test -x`
    existence check, the by-path invocation, and the version comparison all
    actually run against a real installed binary, against the manifest's
    own version tag, without touching the real network or the real
    machine's tool-install locations."""
    run = _verify_published_install_run(_workflow())
    whl = next(iter(_built_dist.glob("*.whl")))
    local_run = _local_variant_body(run, whl)

    scratch = tmp_path / "verify_published_scratch_match"
    scratch.mkdir()
    version = _manifest_version()
    env = _hermetic_local_variant_env(tmp_path, _real_uv_cache_dir, f"v{version}")

    start = time.monotonic()
    result = _run_bash_body(local_run, cwd=scratch, env=env)
    elapsed = time.monotonic() - start

    assert result.returncode == 0, (
        f"the local-variant verify-published body failed against a matching "
        f"tag: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    # Positive control for the sibling falsity test below: if the install
    # itself did not succeed here (offline, warm cache, matching tag), the
    # marker string check there proves nothing.
    assert _INSTALL_SUCCESS_MARKER in combined, (
        f"positive control failed -- the install did not report success: {combined!r}"
    )
    assert elapsed < 30, (
        f"expected a fast, offline, warm-cache run (dead proxies mean any "
        f"real network attempt would itself have to time out); took "
        f"{elapsed:.1f}s"
    )


def test_verify_published_local_variant_fails_when_the_version_does_not_match(
    tmp_path: Path, _built_dist: Path, _real_uv_cache_dir: str
) -> None:
    """Falsity: the same local variant, run against a tag (`v9.9.9`) that
    disagrees with the real built wheel's version, must exit nonzero -- the
    version-comparison `test` line is what fails it, not the install
    itself. That distinction is the entire point of the
    `_INSTALL_SUCCESS_MARKER` assertion below: under a broken environment
    (a dead proxy with no warm cache, for example) the install would fail,
    `test -x "$UV_TOOL_BIN_DIR/fitdocs"` would fail on the NEXT line, and
    the script would ALSO exit 1 -- an indistinguishable outcome from the
    genuine version-mismatch failure this test means to pin. Requiring the
    install-success marker in the captured output first rules that out.
    Removing the `test -x "$UV_TOOL_BIN_DIR/fitdocs"` line itself leaves this
    module green -- that line is defence-in-depth behind the marker and the
    version-comparison line, and its removal is the one accepted survivor."""
    run = _verify_published_install_run(_workflow())
    whl = next(iter(_built_dist.glob("*.whl")))
    local_run = _local_variant_body(run, whl)

    scratch = tmp_path / "verify_published_scratch_mismatch"
    scratch.mkdir()
    env = _hermetic_local_variant_env(tmp_path, _real_uv_cache_dir, "v9.9.9")

    result = _run_bash_body(local_run, cwd=scratch, env=env)
    combined = result.stdout + result.stderr
    assert _INSTALL_SUCCESS_MARKER in combined, (
        f"positive control failed -- the install itself did not succeed, "
        f"so exit 1 proves nothing about the version comparison: {combined!r}"
    )
    assert result.returncode == 1, (
        f"expected exit 1 from the version-comparison line for a tag that "
        f"disagrees with the installed version, got {result.returncode}: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_verify_published_local_variant_missing_export_fails_fast_and_stays_contained(
    tmp_path: Path, _built_dist: Path, _real_uv_cache_dir: str
) -> None:
    """A workflow bug that turns `export UV_TOOL_BIN_DIR=$(mktemp -d)` into
    a plain, unexported assignment would silently fall back to uv's default
    tool-bin location for the actual `uv tool install` child process -- on
    a real, unisolated developer machine that default is `~/.local/bin`,
    meaning a broken workflow could write a stray `fitdocs` shim onto
    whatever machine happens to execute it. This single test proves both
    halves at once: (1) the mutation is CAUGHT -- fast, bounded by the
    hermetic env's `sleep 0` substitution rather than the real 180s six
    retries would otherwise cost -- because `"$UV_TOOL_BIN_DIR/fitdocs"`
    (the shell variable is still set locally, just never exported to the
    `uv` subprocess) points at an empty scratch directory nothing ever
    wrote into; and (2) the REAL machine's `~/.local/bin` is untouched
    throughout, because `HOME` is redirected to a tmp directory before `uv`
    ever runs, so even the silent fallback lands inside the redirected
    home, never the real one."""
    run = _verify_published_install_run(_workflow())
    whl = next(iter(_built_dist.glob("*.whl")))
    local_run = _local_variant_body(run, whl)
    mutated = _substitute_once(
        local_run,
        "export UV_TOOL_BIN_DIR=$(mktemp -d)",
        "UV_TOOL_BIN_DIR=$(mktemp -d)",
    )

    scratch = tmp_path / "verify_published_scratch_missing_export"
    scratch.mkdir()
    version = _manifest_version()
    env = _hermetic_local_variant_env(tmp_path, _real_uv_cache_dir, f"v{version}")

    real_home_local_bin = Path.home() / ".local" / "bin"
    # Falsity-before / snapshot: recorded from the REAL home (never
    # overridden for the pytest process itself, only for the subprocess'
    # env= below), so a later divergence can only be this mutation's doing.
    before = (
        set(real_home_local_bin.iterdir()) if real_home_local_bin.is_dir() else set()
    )

    start = time.monotonic()
    result = _run_bash_body(mutated, cwd=scratch, env=env)
    elapsed = time.monotonic() - start

    assert result.returncode != 0, (
        f"a dropped `export` on UV_TOOL_BIN_DIR should fail the by-path "
        f"invocation, got exit 0: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert elapsed < 30, (
        f"expected a fast failure bounded by the sleep-0 substitution; "
        f"took {elapsed:.1f}s"
    )

    after = (
        set(real_home_local_bin.iterdir()) if real_home_local_bin.is_dir() else set()
    )
    assert after == before, (
        "the missing-export mutation wrote into the REAL machine's "
        f"~/.local/bin: new entries {after - before!r}"
    )
