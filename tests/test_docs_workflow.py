"""Conformance for docs-site task 5.1: `.github/workflows/docs.yml`
(design.md "DocsWorkflow"; Req 9.5, 10.1-10.9).

The workflow builds and gates every relevant change and publishes `main`
only. The structural tests load the YAML with `yaml.safe_load` (PyYAML parses the
bare key `on` as the boolean `True`); each test docstring names the edit
to `docs.yml` (or, for the two control tests, to this module) that turns it
red.

Groups:

(a) triggers and their `paths` lists (10.1);
(b) deploy scope, ordering, gate failure, empty content (10.2, 10.3, 10.5,
    10.6);
(c) the fail-closed secret step, its body run through `bash -eo pipefail`
    (10.4);
(d) permissions and pins (10.7, 10.8);
(e) tooling required and command flags (9.5, and the flags of every
    `scripts.<name>` command);
(f) `actionlint`, when present on PATH, skipped with a reason otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import scripts.build_site as build_site
import scripts.check_site as check_site
import yaml
from scripts.sitebuild.pipeline import DEFAULT_BUILD_ROOT

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOCS_PATH = _REPO_ROOT / ".github" / "workflows" / "docs.yml"
_CI_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_EXPECTED_PATHS = {
    "website/**",
    "scripts/build_site.py",
    "scripts/check_site.py",
    "scripts/make_hero_chart.py",
    "scripts/sitebuild/**",
    "tests/sitebuild/**",
    "tests/test_docs_workflow.py",
    "tests/_forbidden_strings.py",
    "tests/_content_oracle.py",
    "tests/_content_fingerprints.py",
    "docs/**",
    "pyproject.toml",
    "uv.lock",
    ".github/workflows/docs.yml",
}

_HAS_CONTENT = "steps.content.outputs.has_content == 'true'"
_NO_CONTENT = "steps.content.outputs.has_content != 'true'"
_PUSH_TO_MAIN = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
_UPLOAD_IF = f"{_PUSH_TO_MAIN} && {_HAS_CONTENT}"
_DEPLOY_IF = f"{_PUSH_TO_MAIN} && needs.build.outputs.has_content == 'true'"

_PIN_RE = re.compile(r"@(v\d+\.\d+\.\d+|[0-9a-f]{40})$")
_SHA = "0123456789abcdef0123456789abcdef01234567"


def _text() -> str:
    assert _DOCS_PATH.is_file(), ".github/workflows/docs.yml does not exist"
    return _DOCS_PATH.read_text(encoding="utf-8")


def _workflow() -> dict[Any, Any]:
    doc = yaml.safe_load(_text())
    assert isinstance(doc, dict)
    return doc


def _job(doc: dict[Any, Any], name: str) -> dict[str, Any]:
    jobs = doc["jobs"]
    assert list(jobs.keys()) == ["build", "deploy"], (
        f"expected exactly the jobs build and deploy, got {list(jobs.keys())!r}"
    )
    job = jobs[name]
    assert isinstance(job, dict)
    return job


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return steps


def _index_by_run(steps: list[dict[str, Any]], fragment: str) -> int:
    """Index of the one step whose `run:` contains `fragment` -- found by the
    command itself, never by the step's free-text `name:`."""
    hits = [
        i
        for i, s in enumerate(steps)
        if isinstance(s.get("run"), str) and fragment in s["run"]
    ]
    assert len(hits) == 1, f"expected one step running {fragment!r}, found {hits}"
    return hits[0]


def _index_by_uses(steps: list[dict[str, Any]], action: str) -> int:
    hits = [
        i
        for i, s in enumerate(steps)
        if str(s.get("uses", "")).startswith(action + "@")
    ]
    assert len(hits) == 1, f"expected one step using {action!r}, found {hits}"
    return hits[0]


def _gate_index(steps: list[dict[str, Any]]) -> int:
    return _index_by_run(steps, "scripts.check_site")


def _secret_step(steps: list[dict[str, Any]]) -> dict[str, Any]:
    return steps[_index_by_run(steps, "printf ")]


def _normalized(cond: str) -> str:
    return " ".join(str(cond).split())


# --- (a) triggers (10.1) ----------------------------------------------------


def test_push_and_pull_request_carry_exactly_the_same_paths() -> None:
    """Both triggers filter on the design's `paths` list, no more, no fewer (10.1).

    Dies on: dropping or adding one entry in either `paths:` list of docs.yml,
    leaving one trigger without `paths`, or adding a `branches` or `types`
    filter to either trigger.
    """
    triggers = _workflow()[True]
    assert isinstance(triggers, dict)
    assert sorted(triggers.keys()) == ["pull_request", "push"]
    for name in ("push", "pull_request"):
        assert set(triggers[name]) == {"paths"}, (name, set(triggers[name]))
        paths = triggers[name]["paths"]
        assert len(paths) == len(set(paths)), f"{name} repeats a path"
        assert set(paths) == _EXPECTED_PATHS, (
            f"{name} paths differ: missing {_EXPECTED_PATHS - set(paths)}, "
            f"extra {set(paths) - _EXPECTED_PATHS}"
        )


# --- (b) deploy scope, ordering, gate, empty content ------------------------


def test_deploy_job_and_upload_step_carry_the_push_main_content_condition() -> None:
    """The deploy job and the upload step publish only a push to `main` that
    has content (10.2).

    Dies on: dropping the deploy job's `if`, dropping the `github.ref` clause
    from either condition, or `needs.build.outputs.has_content` /
    `steps.content.outputs.has_content` becoming `!= 'true'`.
    """
    doc = _workflow()
    deploy = _job(doc, "deploy")
    assert _normalized(deploy["if"]) == _DEPLOY_IF
    assert deploy["needs"] == "build"
    build = _job(doc, "build")
    steps = _steps(build)
    upload = steps[_index_by_uses(steps, "actions/upload-pages-artifact")]
    assert _normalized(upload["if"]) == _UPLOAD_IF
    assert build["outputs"] == {
        "has_content": "${{ steps.content.outputs.has_content }}"
    }


def test_gate_names_both_trees_and_runs_before_the_upload() -> None:
    """The gate scans the staged and the built trees, after both builds and
    the match-data step, and before the upload (10.3).

    Dies on: moving the gate step below the upload step, deleting either
    directory argument from the gate command, moving the secret step
    below the gate, or prefixing the gate's `run` with `echo `, `true || `
    or a first line `exit 0`.
    """
    steps = _steps(_job(_workflow(), "build"))
    gate = steps[_gate_index(steps)]
    run = gate["run"].strip()
    words = shlex.split(run)
    check_at = words.index("scripts.check_site")
    assert words[check_at + 1 :] == [
        "website/build/site/staged",
        "website/build/site/html",
    ]
    root = DEFAULT_BUILD_ROOT.as_posix()
    assert run == (
        'FITDOCS_FORBIDDEN_STRINGS="$RUNNER_TEMP/forbidden-strings.txt" '
        f"uv run python -m scripts.check_site {root}/staged {root}/html"
    )
    gate_at = _gate_index(steps)
    assert _index_by_uses(steps, "actions/upload-pages-artifact") > gate_at
    assert _index_by_run(steps, "printf ") < gate_at
    build_steps = [
        i
        for i, s in enumerate(steps)
        if isinstance(s.get("run"), str) and "scripts.build_site build" in s["run"]
    ]
    assert len(build_steps) == 2
    assert max(build_steps) < gate_at


def test_upload_path_is_the_directory_the_builder_writes_html_to() -> None:
    """The artifact uploaded is the builder's `html/` tree, the same one the
    gate scans (10.3).

    Dies on: pointing the upload `path:` anywhere but `website/build/site/html`,
    or adding a second `with:` key such as `name: not-github-pages`.
    """
    steps = _steps(_job(_workflow(), "build"))
    upload = steps[_index_by_uses(steps, "actions/upload-pages-artifact")]
    assert upload["with"] == {"path": f"{DEFAULT_BUILD_ROOT.as_posix()}/html"}
    gate_args = shlex.split(steps[_gate_index(steps)]["run"])
    assert upload["with"]["path"] in gate_args


def test_no_job_or_step_continues_on_error_and_the_gate_is_unconditional() -> None:
    """No job and no step of docs.yml sets `continue-on-error`, and the gate
    step has exactly the keys `name` and `run`, so it carries no `if`, `shell`
    or `continue-on-error` (10.5, 10.3).

    Dies on: adding `continue-on-error: true` to any job or step (the gate,
    the secret step, the site-test step, a build step), or adding `if:` (for
    example `if: false` or a pull_request-only `if`) or `shell:` to the gate
    step.
    """
    doc = _workflow()
    walked = 0
    for name in ("build", "deploy"):
        job = _job(doc, name)
        assert "continue-on-error" not in job, name
        for step in _steps(job):
            walked += 1
            assert "continue-on-error" not in step, step
    assert walked >= 12, f"the walk saw {walked} steps"
    steps = _steps(_job(doc, "build"))
    assert set(steps[_gate_index(steps)]) == {"name", "run"}


_BUILD_JOB_KEYS = {"runs-on", "outputs", "steps"}
_DEPLOY_JOB_KEYS = {
    "needs",
    "if",
    "runs-on",
    "permissions",
    "environment",
    "concurrency",
    "steps",
}
# One key set per build step, in file order: checkout, setup-uv, python
# install, sync, site tests, status, real build, fixture build, secret, gate,
# upload.
_BUILD_STEP_KEYS = [
    {"name", "uses"},
    {"name", "uses"},
    {"name", "run"},
    {"name", "run"},
    {"name", "env", "run"},
    {"name", "id", "run"},
    {"name", "if", "run"},
    {"name", "if", "run"},
    {"name", "env", "run"},
    {"name", "run"},
    {"name", "if", "uses", "with"},
]
_DEPLOY_STEP_KEYS = [{"name", "id", "uses"}]


def test_jobs_and_steps_carry_exactly_the_designed_keys() -> None:
    """Every job and every step has exactly the keys the design gives it, so no
    key outside that set (`defaults`, `continue-on-error`, `timeout-minutes`,
    `shell`, `env`, an extra `if`, `strategy`, `container`, `services`) is
    present on a job or a step (10.3, 10.4, 10.5).

    Dies on: adding any key to the build or deploy job, or to any step, or
    removing one from them (for example `defaults: {run: {shell: "true {0}"}}`
    on `build`, `continue-on-error` or `if` on the gate step, `timeout-minutes`
    or `env` on the deploy job or its step).
    """
    doc = _workflow()
    build = _job(doc, "build")
    deploy = _job(doc, "deploy")
    assert set(build) == _BUILD_JOB_KEYS, set(build) ^ _BUILD_JOB_KEYS
    assert set(deploy) == _DEPLOY_JOB_KEYS, set(deploy) ^ _DEPLOY_JOB_KEYS
    assert build["runs-on"] == "ubuntu-latest"
    assert deploy["runs-on"] == "ubuntu-latest"
    assert [set(s) for s in _steps(build)] == _BUILD_STEP_KEYS
    assert [set(s) for s in _steps(deploy)] == _DEPLOY_STEP_KEYS


def test_fixture_build_step_is_the_negation_of_the_real_build_and_notices() -> None:
    """With no included page the fixture site is built, a notice is emitted and
    the real build is skipped (10.6).

    Dies on: making the fixture step's `if` equal to the real step's, dropping
    `--content tests/sitebuild/fixtures/site`, deleting the `::notice::` line,
    appending `> /dev/null` to the notice, pointing `--content` at
    `tests/sitebuild/fixtures/site/../../../website/content`, appending
    `|| true` to the fixture build, or appending `|| true` to the real build.
    """
    steps = _steps(_job(_workflow(), "build"))
    fixture = steps[_index_by_run(steps, "build_site build --content")]
    real = next(
        s
        for s in steps
        if isinstance(s.get("run"), str)
        and "scripts.build_site build" in s["run"]
        and "--content" not in s["run"]
    )
    assert real["if"] == _HAS_CONTENT
    assert fixture["if"] == _NO_CONTENT
    assert real["if"].replace("==", "!=") == fixture["if"]
    assert fixture["run"].strip().splitlines() == [
        "uv run --group docs python -m scripts.build_site build "
        "--content tests/sitebuild/fixtures/site",
        'echo "::notice::website/content holds no included page; '
        'built the fixture site; deploy skipped"',
    ]
    assert real["run"].strip() == (
        "uv run --group docs python -m scripts.build_site build"
    )
    assert _index_by_run(steps, "build_site status") < steps.index(real)


# --- (c) fail-closed secret step (10.4) -------------------------------------


def _run_bash(body: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-eo", "pipefail", "-c", body],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_secret_step_is_byte_identical_to_the_ci_workflow_step() -> None:
    """The match-data step is `ci.yml`'s fail-closed step, body and env alike
    (10.4).

    Dies on: any edit to the secret step's `run:` body or `env:` in docs.yml
    that ci.yml does not share, or adding `if:`, `shell:` or
    `continue-on-error` to the secret step.
    """
    ci_steps = _steps(
        yaml.safe_load(_CI_PATH.read_text(encoding="utf-8"))["jobs"]["gates"]
    )
    ci_step = ci_steps[_index_by_run(ci_steps, "printf ")]
    step = _secret_step(_steps(_job(_workflow(), "build")))
    assert set(step) == {"name", "env", "run"}
    assert step["run"] == ci_step["run"]
    assert step["env"] == ci_step["env"]
    assert step["env"] == {
        "FITDOCS_FORBIDDEN_STRINGS_CONTENT": (
            "${{ secrets.FITDOCS_FORBIDDEN_STRINGS_CONTENT }}"
        )
    }


def test_secret_step_body_exits_one_with_gate_not_run_when_the_secret_is_empty(
    tmp_path: Path,
) -> None:
    """An empty secret exits 1 printing `gate_not_run` and writes no file (10.4).

    Dies on: dropping the `-z` guard, changing `exit 1` to `exit 0`, or
    removing `gate_not_run` from the message in docs.yml's secret step.
    """
    body = _secret_step(_steps(_job(_workflow(), "build")))["run"]
    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(tmp_path)
    env["FITDOCS_FORBIDDEN_STRINGS_CONTENT"] = ""
    result = _run_bash(body, env)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "gate_not_run" in result.stdout + result.stderr
    assert not (tmp_path / "forbidden-strings.txt").exists()


def test_secret_step_body_writes_the_match_file_when_the_secret_is_set(
    tmp_path: Path,
) -> None:
    """A set secret is written, unmodified, to `$RUNNER_TEMP/forbidden-strings.txt`,
    the path the gate step reads (10.4).

    Dies on: writing to a different file name, or a different directory, than
    the gate step's `FITDOCS_FORBIDDEN_STRINGS`, or altering the content.
    """
    steps = _steps(_job(_workflow(), "build"))
    body = _secret_step(steps)["run"]
    env = os.environ.copy()
    env["RUNNER_TEMP"] = str(tmp_path)
    env["FITDOCS_FORBIDDEN_STRINGS_CONTENT"] = "alpha\nbeta"
    target = tmp_path / "forbidden-strings.txt"
    assert not target.exists()
    result = _run_bash(body, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert target.read_text(encoding="utf-8") == "alpha\nbeta"
    assert (
        'FITDOCS_FORBIDDEN_STRINGS="$RUNNER_TEMP/forbidden-strings.txt"'
        in (steps[_gate_index(steps)]["run"])
    )


# --- (d) permissions and pins (10.7, 10.8) ----------------------------------


def test_workflow_level_keys_are_exactly_triggers_permissions_env_and_jobs() -> None:
    """The workflow has exactly the keys `on`, `permissions`, `env` and `jobs`,
    and `env` is exactly `TERM: dumb` and `NO_COLOR: "1"`; a workflow-level
    `concurrency` (which could cancel a running deploy) is therefore absent.

    Dies on: dropping or changing either `env` entry, or adding a top-level
    key such as `concurrency`, `defaults` or `run-name` to docs.yml.
    """
    doc = _workflow()
    assert set(doc) == {True, "permissions", "env", "jobs"}
    assert doc["env"] == {"TERM": "dumb", "NO_COLOR": "1"}


def test_permissions_are_read_only_except_on_the_deploy_job() -> None:
    """Workflow permissions are exactly `contents: read`; only `deploy` carries
    job permissions, exactly `pages: write` and `id-token: write` (10.7).

    Dies on: widening the workflow-level `permissions`, adding `permissions`
    to the `build` job, or adding or dropping a scope on `deploy`.
    """
    doc = _workflow()
    assert doc["permissions"] == {"contents": "read"}
    assert "permissions" not in _job(doc, "build")
    assert _job(doc, "deploy")["permissions"] == {
        "pages": "write",
        "id-token": "write",
    }


def test_deploy_job_uses_the_github_pages_environment_and_never_cancels() -> None:
    """`deploy` runs one `deploy-pages` step in the `github-pages` environment,
    serialised on the `pages` group without cancelling (10.2).

    Dies on: renaming the environment, `cancel-in-progress: true`, or adding
    a second step to the deploy job.
    """
    deploy = _job(_workflow(), "deploy")
    assert deploy["environment"] == {
        "name": "github-pages",
        "url": "${{ steps.deployment.outputs.page_url }}",
    }
    assert deploy["concurrency"] == {"group": "pages", "cancel-in-progress": False}
    steps = _steps(deploy)
    assert len(steps) == 1
    assert steps[0]["uses"].startswith("actions/deploy-pages@")
    assert steps[0]["id"] == "deployment"


def _unpinned(uses: list[str]) -> list[str]:
    return [u for u in uses if not _PIN_RE.search(u)]


def test_every_action_is_pinned_to_an_exact_version_or_a_sha() -> None:
    """Every `uses:` ends in `@vX.Y.Z` or a 40-hex commit (10.8).

    Dies on: pinning any action in docs.yml to a branch, a bare major, or a
    minor-only tag.
    """
    uses = [
        s["uses"]
        for name in ("build", "deploy")
        for s in _steps(_job(_workflow(), name))
        if "uses" in s
    ]
    assert len(uses) == 4, f"expected four actions, found {uses}"
    assert _unpinned(uses) == []


def test_pin_rule_rejects_floating_refs_and_accepts_exact_ones() -> None:
    """The pin rule itself: `@main`, `@v5`, `@v5.0` fail; an exact tag and a
    SHA pass (10.8).

    Dies on: loosening `_PIN_RE` in this module to accept a branch or a bare major.
    """
    bad = [
        "actions/checkout@main",
        "actions/checkout@v7",
        "actions/checkout@v7.0",
        f"actions/checkout@{_SHA[:39]}",
        "actions/checkout",
    ]
    assert _unpinned(bad) == bad
    good = ["actions/checkout@v7.0.1", f"actions/checkout@{_SHA}"]
    assert _unpinned(good) == []


# --- (e) tooling and flags (9.5) --------------------------------------------


def test_site_test_step_requires_the_site_tooling() -> None:
    """The site tests run with `FITDOCS_REQUIRE_SITE_TOOLING: "1"`, so a
    skipped generator test fails the job (9.5).

    Dies on: dropping the step's `env`, changing the value, or running the
    site tests without `--group docs`.
    """
    steps = _steps(_job(_workflow(), "build"))
    step = steps[_index_by_run(steps, "pytest tests/sitebuild")]
    assert step["env"] == {"FITDOCS_REQUIRE_SITE_TOOLING": "1"}
    assert step["run"].strip() == (
        "uv run --group docs pytest tests/sitebuild tests/test_docs_workflow.py"
    )


def test_build_job_sets_up_python_and_the_docs_group_before_anything_runs() -> None:
    """The job installs Python 3.11 and syncs the `docs` group before the site
    tests, and every generator invocation keeps `--group docs` (9.5).

    Dies on: dropping `uv python install 3.11` or `uv sync --group docs`,
    moving either below the test step, or dropping `--group docs` from a
    `scripts.build_site build` command.
    """
    steps = _steps(_job(_workflow(), "build"))
    assert steps[0]["uses"].startswith("actions/checkout@")
    assert steps[1]["uses"].startswith("astral-sh/setup-uv@")
    assert steps[2]["run"].strip() == "uv python install 3.11"
    assert steps[3]["run"].strip() == "uv sync --group docs"
    assert _index_by_run(steps, "pytest tests/sitebuild") == 4
    builds = [
        s["run"]
        for s in steps
        if isinstance(s.get("run"), str) and "scripts.build_site build" in s["run"]
    ]
    assert len(builds) == 2
    for run in builds:
        assert run.strip().startswith("uv run --group docs python -m ")
    assert steps[5]["run"].strip() == (
        'uv run python -m scripts.build_site status >> "$GITHUB_OUTPUT"'
    )
    assert steps[5]["id"] == "content"


_PARSER_FACTORY: dict[str, Callable[[], argparse.ArgumentParser]] = {
    "build_site": build_site._build_parser,
    "check_site": check_site._build_parser,
}

_SCRIPTS_CMD_RE = re.compile(r"python -m scripts\.(\w+)([^\n&|>]*)")


def _parse_error(module: str, rest: str) -> str | None:
    """None when the module's own parser accepts `rest`; else its complaint."""
    parser = _PARSER_FACTORY[module]()
    try:
        parser.parse_args(shlex.split(rest))
    except SystemExit as exc:
        return repr(exc)
    return None


def test_every_scripts_command_parses_with_its_modules_own_parser() -> None:
    """Every `python -m scripts.<name>` command in docs.yml parses with that
    module's `_build_parser()`: subcommand, flags and positional roots.

    Dies on: renaming a flag or subcommand in docs.yml (`--content` to
    `--source`, `build` to `render`), or dropping the gate's roots.
    """
    text = _text()
    commands = _SCRIPTS_CMD_RE.findall(text)
    assert [m for m, _ in commands].count("build_site") == 3
    assert [m for m, _ in commands].count("check_site") == 1
    for module, rest in commands:
        assert module in _PARSER_FACTORY, f"no parser factory for scripts.{module}"
        assert _parse_error(module, rest) is None, (module, rest)


def test_parser_check_rejects_a_bad_flag_and_a_missing_root() -> None:
    """The parse check can fail: an unknown flag, an unknown subcommand and a
    gate with no roots are all refused.

    Dies on: `_parse_error` in this module returning None unconditionally.
    """
    assert _parse_error("build_site", " build --source x") is not None
    assert _parse_error("build_site", " render") is not None
    assert _parse_error("check_site", " ") is not None
    assert _parse_error("build_site", " build --content x") is None


# --- (f) actionlint, when present -------------------------------------------


def test_actionlint_if_available() -> None:
    """`actionlint` accepts docs.yml when it is installed; skipped when absent.

    Dies on: any syntax or expression error in docs.yml that actionlint reports.
    """
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        pytest.skip("actionlint is not installed in this environment")
    result = subprocess.run(
        [actionlint, str(_DOCS_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
