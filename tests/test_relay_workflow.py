"""Conformance for relay-server task 1.5: `.github/workflows/relay.yml`
(design.md "RelayImage and RelayWorkflow"; Requirements 1.5, 7.6).

The relay's own CI runs on every push and pull request with read-only
permissions, against a PostgreSQL 17 service container pinned by digest, and
fails rather than skips when that server is unreachable. It publishes nothing.
Every check parses the YAML and asserts on structure; the whole-text scan is
only for a word that must not appear anywhere, comments included.

Image steps arrive with task 5.3, which extends the pins here.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RELAY_PATH = _REPO_ROOT / ".github" / "workflows" / "relay.yml"

_VERSION_PIN_RE = re.compile(r"@(v\d+(\.\d+){0,2}|[0-9a-f]{40})$")
_DIGEST_IMAGE_RE = re.compile(r"^postgres:17@sha256:[0-9a-f]{64}$")


def _text() -> str:
    assert _RELAY_PATH.is_file(), ".github/workflows/relay.yml does not exist"
    return _RELAY_PATH.read_text(encoding="utf-8")


def _workflow(text: str | None = None) -> dict[Any, Any]:
    doc = yaml.safe_load(_text() if text is None else text)
    assert isinstance(doc, dict)
    return doc


def _job(doc: dict[Any, Any]) -> dict[str, Any]:
    jobs = doc["jobs"]
    assert list(jobs) == ["relay"], f"expected exactly the job relay, got {list(jobs)}"
    job = jobs["relay"]
    assert isinstance(job, dict)
    return job


def _steps(doc: dict[Any, Any]) -> list[dict[str, Any]]:
    steps = _job(doc)["steps"]
    assert isinstance(steps, list) and steps
    return steps


def _run_step(doc: dict[Any, Any], command: str) -> dict[str, Any]:
    """The one step whose `run:` body, stripped, equals `command` -- found by
    the command, never by the step's free-text name."""
    matches = [
        s
        for s in _steps(doc)
        if isinstance(s.get("run"), str) and s["run"].strip() == command
    ]
    assert len(matches) == 1, f"expected one step running {command!r}: {len(matches)}"
    return matches[0]


def _pin_violations(doc: dict[Any, Any]) -> list[str]:
    uses = [s["uses"] for s in _steps(doc) if "uses" in s]
    assert len(uses) >= 2, "the walk found fewer than two actions"
    return [u for u in uses if not _VERSION_PIN_RE.search(u)]


def _service_findings(doc: dict[Any, Any]) -> list[str]:
    services = _job(doc)["services"]
    assert list(services) == ["postgres"]
    svc = services["postgres"]
    findings = []
    if not _DIGEST_IMAGE_RE.match(svc["image"]):
        findings.append(f"image {svc['image']!r} is not postgres:17 pinned by digest")
    options = svc.get("options", "")
    if "--health-cmd" not in options or "pg_isready" not in options:
        findings.append("no pg_isready health check")
    return findings


# --- triggers, permissions, shape -------------------------------------------


def test_runs_on_every_push_and_pull_request_with_no_filter() -> None:
    triggers = _workflow()[True]  # PyYAML reads the bare key `on` as True
    assert set(triggers) == {"push", "pull_request"}
    for name, config in triggers.items():
        # `push:` and `pull_request:` with no body parse as None; any filter
        # would be a dict naming paths or branches.
        assert config is None, f"{name} carries a filter: {config!r}"


def test_top_level_permissions_are_exactly_contents_read() -> None:
    doc = _workflow()
    assert doc["permissions"] == {"contents": "read"}
    assert "permissions" not in _job(doc), "the job widens the permissions"


def test_one_relay_job_on_ubuntu() -> None:
    assert _job(_workflow())["runs-on"] == "ubuntu-latest"


# --- publishes nothing ------------------------------------------------------


_FORBIDDEN_RUN_WORDS = re.compile(r"\b(publish|login|push|upload|twine)\b")


def _publishing_runs(doc: dict[Any, Any]) -> list[str]:
    return [
        s["run"]
        for s in _steps(doc)
        if isinstance(s.get("run"), str) and _FORBIDDEN_RUN_WORDS.search(s["run"])
    ]


def test_no_run_step_publishes_logs_in_pushes_or_uploads() -> None:
    assert _publishing_runs(_workflow()) == []
    # Positive controls: each spelling the pattern exists to catch.
    for run in (
        "hatch publish",
        "uv  publish",
        "oras login ghcr.io",
        "gh release upload v1 x",
        "docker push x",
        "twine upload dist/*",
    ):
        assert _FORBIDDEN_RUN_WORDS.search(run), run


def test_no_identity_token_grant_anywhere() -> None:
    # Whole text, comments included: the one word that must never appear.
    assert "id-token" not in _text().lower()


# --- every action pinned ----------------------------------------------------


def test_every_action_is_pinned_to_a_version_tag_or_sha() -> None:
    assert _pin_violations(_workflow()) == []
    # Positive control: the pattern must reject a mutable ref.
    assert _VERSION_PIN_RE.search("actions/checkout@main") is None


def test_the_two_expected_actions_are_present() -> None:
    uses = [s["uses"] for s in _steps(_workflow()) if "uses" in s]
    names = {u.split("@")[0] for u in uses}
    assert names == {"actions/checkout", "astral-sh/setup-uv"}


def test_setup_uv_carries_a_minor_or_patch_tag_or_sha() -> None:
    uses = [s["uses"] for s in _steps(_workflow()) if "uses" in s]
    (ref,) = [u.split("@")[1] for u in uses if u.startswith("astral-sh/setup-uv@")]
    assert re.fullmatch(r"v\d+\.\d+(\.\d+)?|[0-9a-f]{40}", ref), ref


# --- the PostgreSQL service -------------------------------------------------


def test_postgres_service_is_pinned_by_digest_with_a_pg_isready_health_check() -> None:
    assert _service_findings(_workflow()) == []
    svc = _job(_workflow())["services"]["postgres"]
    assert svc["env"]["POSTGRES_PASSWORD"], "the service has no password"
    # Positive controls: the checks above must be able to fail.
    broken = _text().replace(svc["image"], "postgres:17")
    assert _service_findings(_workflow(broken)) != []


# --- the steps --------------------------------------------------------------


def test_python_floor_is_installed_before_the_sync() -> None:
    doc = _workflow()
    steps = _steps(doc)
    install = _run_step(doc, "uv python install 3.11")
    (sync,) = [s for s in steps if s.get("run", "").strip().startswith("uv sync")]
    assert steps.index(install) < steps.index(sync)


def test_sync_is_locked_with_the_postgres_extra() -> None:
    syncs = [
        s["run"].strip()
        for s in _steps(_workflow())
        if s.get("run", "").strip().startswith("uv sync")
    ]
    assert syncs == ["uv sync --directory relay --locked --extra postgres"]


def _require_flag_findings(doc: dict[Any, Any]) -> list[str]:
    step = _run_step(doc, "uv run --directory relay pytest")
    flag = step.get("env", {}).get("FITDOCS_RELAY_REQUIRE_POSTGRES")
    return [] if flag == "1" else [f"require flag is {flag!r}, not '1'"]


def test_relay_tests_run_with_the_url_and_the_require_flag() -> None:
    step = _run_step(_workflow(), "uv run --directory relay pytest")
    env = step["env"]
    assert _require_flag_findings(_workflow()) == []
    parts = urlsplit(env["FITDOCS_RELAY_TEST_POSTGRES_URL"])
    password = _job(_workflow())["services"]["postgres"]["env"]["POSTGRES_PASSWORD"]
    assert parts.scheme == "postgresql"
    assert parts.username == "postgres"
    assert parts.password == password
    assert parts.hostname == "127.0.0.1"
    assert parts.port == 5432
    assert parts.path == "/postgres"
    assert parts.query == "" and parts.fragment == ""
    # The service publishes this port on the runner's loopback.
    assert "5432:5432" in _job(_workflow())["services"]["postgres"]["ports"]


def test_require_flag_removed_in_memory_reds_the_pin() -> None:
    flag = '          FITDOCS_RELAY_REQUIRE_POSTGRES: "1"\n'
    assert _text().count(flag) == 1
    assert _require_flag_findings(_workflow(_text().replace(flag, ""))) != []


def test_relay_lint_format_and_type_gates_run_after_the_tests() -> None:
    doc = _workflow()
    steps = _steps(doc)
    tests = _run_step(doc, "uv run --directory relay pytest")
    lint = _run_step(
        doc,
        "uv run --directory relay ruff check . "
        "&& uv run --directory relay ruff format --check .",
    )
    mypy = _run_step(doc, "uv run --directory relay mypy")
    assert steps.index(tests) < steps.index(lint) < steps.index(mypy)


_STEP_KEYS = {"name", "uses", "run", "env"}


def test_every_level_allows_only_keys_that_cannot_skip_or_mask_a_step() -> None:
    """Allow-lists at workflow, job, service and step level: nothing like
    `defaults`, `if`, `continue-on-error`, `timeout-minutes`, `strategy`,
    `container`, `needs`, `shell` or `working-directory` can be added. Task
    5.3 extends these sets for its image steps."""
    doc = _workflow()
    # PyYAML reads the bare key `on` as True.
    assert set(doc) == {True, "permissions", "env", "jobs"}
    assert set(_job(doc)) == {"runs-on", "services", "steps"}
    assert set(_job(doc)["services"]["postgres"]) == {
        "image",
        "env",
        "ports",
        "options",
    }
    for step in _steps(doc):
        assert set(step) <= _STEP_KEYS, step
    test_step = _run_step(doc, "uv run --directory relay pytest")
    assert set(test_step) == {"name", "env", "run"}
    assert set(test_step["env"]) == {
        "FITDOCS_RELAY_TEST_POSTGRES_URL",
        "FITDOCS_RELAY_REQUIRE_POSTGRES",
    }
    assert set(doc["env"]) == {"TERM", "NO_COLOR"}


def test_no_image_step_yet() -> None:
    """Task 5.3 adds the image build and smoke steps and replaces this pin."""
    for step in _steps(_workflow()):
        assert "docker" not in step.get("run", "")


def test_actionlint_if_available() -> None:
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        pytest.skip("actionlint is not installed in this environment")
    result = subprocess.run(
        [actionlint, str(_RELAY_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
