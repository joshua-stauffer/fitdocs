"""Conformance for `.github/workflows/specs.yml`, the spec-only workflow.

A push or pull request that changes only `.kiro/specs/**` skips `ci.yml`
(its `paths-ignore`) and runs `specs.yml`, which keeps the one gate only CI
can run: the encumbered-content scan of every tracked file, armed by the same
fail-closed match-data step `ci.yml` uses. It also runs the test files that
read spec text.

Dies on:
- the two workflows' path filters drifting apart, so that a spec-only change
  runs neither workflow, or a code change skips `ci.yml`;
- the write or mask step diverging from `ci.yml`'s;
- the test step dropping the scan, a spec-reading test file, or the variable
  that arms the scan;
- any publishing permission or step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SPECS_PATH = _REPO_ROOT / ".github" / "workflows" / "specs.yml"
_CI_PATH = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

SPEC_ONLY_PATHS = [".kiro/specs/**"]
TEST_FILES = (
    "tests/test_forbidden_strings.py",
    "tests/test_docs_guarantees.py",
    "tests/connectors/test_wellness_records.py",
)


def _load(path: Path) -> dict[Any, Any]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    return doc


def _steps(doc: dict[Any, Any], job: str) -> list[dict[str, Any]]:
    steps = doc["jobs"][job]["steps"]
    assert isinstance(steps, list)
    return steps


def _index_by_run(steps: list[dict[str, Any]], needle: str) -> int:
    hits = [i for i, s in enumerate(steps) if needle in str(s.get("run", ""))]
    assert len(hits) == 1, f"expected one step whose run contains {needle!r}"
    return hits[0]


def test_triggers_are_exactly_spec_only_paths_on_push_and_pull_request() -> None:
    # PyYAML parses the bare key `on` as the boolean True.
    triggers = _load(_SPECS_PATH)[True]
    assert set(triggers) == {"push", "pull_request"}
    assert triggers["push"] == {"paths": SPEC_ONLY_PATHS}
    assert triggers["pull_request"] == {"paths": SPEC_ONLY_PATHS}


def test_ci_ignores_exactly_the_paths_this_workflow_runs_on() -> None:
    triggers = _load(_CI_PATH)[True]
    assert triggers["push"] == {"paths-ignore": SPEC_ONLY_PATHS}
    assert triggers["pull_request"] == {"paths-ignore": SPEC_ONLY_PATHS}


def test_permissions_are_exactly_contents_read_and_one_job() -> None:
    doc = _load(_SPECS_PATH)
    assert doc["permissions"] == {"contents": "read"}
    assert set(doc["jobs"]) == {"spec-scan"}


def test_write_and_mask_steps_are_ci_steps_verbatim() -> None:
    ci = _steps(_load(_CI_PATH), "gates")
    steps = _steps(_load(_SPECS_PATH), "spec-scan")
    for needle in ("printf ", "::add-mask::"):
        assert steps[_index_by_run(steps, needle)] == ci[_index_by_run(ci, needle)]


def test_test_step_runs_the_armed_scan_and_the_spec_reading_tests() -> None:
    steps = _steps(_load(_SPECS_PATH), "spec-scan")
    write = _index_by_run(steps, "printf ")
    mask = _index_by_run(steps, "::add-mask::")
    test = _index_by_run(steps, "uv run pytest")
    assert write < mask < test
    step = steps[test]
    assert step["run"] == "uv run pytest " + " ".join(TEST_FILES)
    assert step["env"] == {
        "FITDOCS_FORBIDDEN_STRINGS": "${{ runner.temp }}/forbidden-strings.txt"
    }
    for name in TEST_FILES:
        assert (_REPO_ROOT / name).is_file(), name


def test_workflow_publishes_nothing() -> None:
    text = _SPECS_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "id-token",
        "upload-artifact",
        "pypa/gh-action-pypi-publish",
        "docker push",
    ):
        assert forbidden not in text, forbidden
