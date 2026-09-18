"""Artifact-policy data and reader tests (task 1.4: ArtifactPolicy).

This is the design's `tests/test_release_artifacts.py` -- named there for
artifact tests generally; this task covers only the policy *data* and its
reader (`release/artifact-policy.toml`, `scripts/artifact_policy.py`). Later
tasks (2.1-2.3) extend this file with the builder and checker.

Six groups of assertions:

* the real policy file loads, and its content matches the design's declared
  end-state shape, including the inbox skill's `SKILL.md` (distribution
  task 4.2);
* every `[forbidden].members` pattern is exercised with fnmatch against both
  a positive control (something it must catch) and a negative control
  (something it must never catch);
* the reader (`load_policy`) is exercised over synthetic TOML documents for
  every failure and tolerance mode the design specifies;
* the real policy file is scanned for the categories of key it must never
  carry (permission state, a profile/variant, a prune list, a content-marker
  list, a licensing record), with a synthetic positive control proving the
  scan can actually catch one;
* task 2.1's `ReleaseBuilder` (`scripts/build_release.py`): the build's
  command line, its environment, its cwd, its output-directory clearing and
  failure cleanup, its refusal to clear the repository root, its
  reproducibility, and its command surface -- exercised both against real
  `uv build` invocations and, for the command/environment/cleanup contracts,
  against a fake `subprocess.run` recording exactly what it was called with;
* task 2.2's `ArtifactChecker` (`scripts/check_artifacts.py`): synthetic
  wheel/sdist fixtures (built with `zipfile`/`tarfile` directly, never a real
  `uv build`, for the per-rule tests) trip each of the four implemented
  violation kinds exactly once -- in the wheel AND, separately, in the sdist,
  so a check wired to only one artifact kind cannot pass by accident -- a
  clean fixture trips none, ordering is deterministic and pinned against
  both a missing-sort and a wrong-sort-key mutation, hard errors (wrong
  artifact counts, a missing/malformed policy file) are distinguished from
  violations by exit code, and a real `build_release.build()` output passes
  the real policy with zero violations.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from collections import Counter
from collections.abc import Iterator, Mapping
from datetime import date
from enum import StrEnum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest
import scripts.build_release as build_release
import scripts.check_artifacts as check_artifacts_module
from scripts.artifact_policy import (
    DEFAULT_POLICY_PATH,
    ArtifactPolicy,
    PolicyError,
    load_policy,
)
from scripts.check_artifacts import (
    CheckerError,
    Violation,
    ViolationKind,
    check_artifacts,
    check_version_consistency,
)
from scripts.check_artifacts import (
    main as check_artifacts_main,
)

from fitdocs import Sport
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.profile import AthleteProfile, save_profile
from tests._content_fingerprints import SALT as REAL_SALT
from tests._content_oracle import ENTROPY_FLOOR_BITS, digest, tokens, windows
from tests._forbidden_strings import ENV_VAR, ForbiddenStringsSourceError, require
from tests.fixtures import builder
from tests.test_packaging import _run

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH

#: The environment's REAL `FITDOCS_FORBIDDEN_STRINGS` value at module import
#: time -- i.e. whatever the invoking shell set (or did not) BEFORE this
#: module's autouse `_default_forbidden_strings_env` fixture ever runs. The
#: autouse fixture below unconditionally overrides the variable for every
#: test in this module (so the rest of the suite never trips a spurious
#: GATE_NOT_RUN); task 3.2's checkpoint test needs to observe the environment
#: as it *actually* is, so it captures this value once, at import time --
#: before any fixture has touched `os.environ` -- and restores exactly this
#: value inside its own body, overriding the autouse default the same way
#: the module's other unset/broken-source tests already do.
_REAL_ENV_FORBIDDEN_STRINGS: str | None = os.environ.get(ENV_VAR)


# ---------------------------------------------------------------------------
# Task 2.3: default environment for every test in this module
# ---------------------------------------------------------------------------
#
# Every test above this point (and most below it) calls `check_artifacts`
# not caring about the encumbered-content gate at all -- without a default,
# each would trip a spurious GATE_NOT_RUN violation the moment task 2.3's
# gate is wired in, purely because a developer shell has
# `FITDOCS_FORBIDDEN_STRINGS` unset. This autouse fixture points the
# variable at a throwaway, out-of-repository match file (so `load`'s
# inside-the-tree rule never fires for it) holding one needle that never
# occurs in any fixture elsewhere in this module. Tests that must exercise
# the unset / broken-source paths override it within their own body via the
# SAME `monkeypatch` instance (pytest caches a function-scoped fixture once
# per test, so a second request for `monkeypatch` is the identical object).


@pytest.fixture(autouse=True)
def _default_forbidden_strings_env(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_dir = tmp_path_factory.mktemp("default_forbidden_strings")
    match_file = source_dir / "match.txt"
    match_file.write_text("DefaultAutouseSyntheticNeedleNeverPlanted\n")
    monkeypatch.setenv(ENV_VAR, str(match_file))


# ---------------------------------------------------------------------------
# The real policy file: content
# ---------------------------------------------------------------------------


def test_real_policy_loads() -> None:
    policy = load_policy(REAL_POLICY_PATH)
    assert isinstance(policy, ArtifactPolicy)


def test_wheel_required_has_the_five_design_members_including_the_inbox_skill() -> None:
    policy = load_policy(REAL_POLICY_PATH)
    for member in (
        "fitdocs/__init__.py",
        "fitdocs/py.typed",
        "fitdocs/skills/build-training-block/SKILL.md",
        "fitdocs/skills/build-training-block/example-block.toml",
        "fitdocs/skills/fitdocs-workouts/SKILL.md",
    ):
        assert member in policy.wheel_required


def test_sdist_required_has_the_six_named_members() -> None:
    policy = load_policy(REAL_POLICY_PATH)
    for member in (
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "CHANGELOG.md",
        "src/fitdocs/__init__.py",
        "PKG-INFO",
    ):
        assert member in policy.sdist_required


def test_forbidden_members_has_the_named_patterns() -> None:
    policy = load_policy(REAL_POLICY_PATH)
    for pattern in ("agent-log", "tests/*", ".kiro/*", "uv.lock"):
        assert pattern in policy.forbidden_members


def test_metadata_required_fields_has_the_six_design_named_fields() -> None:
    policy = load_policy(REAL_POLICY_PATH)
    for field in (
        "Name",
        "Version",
        "Summary",
        "License-Expression",
        "Requires-Python",
        "Project-URL",
    ):
        assert field in policy.required_metadata_fields


# ---------------------------------------------------------------------------
# The real policy file: forbidden-pattern fnmatch discrimination
# ---------------------------------------------------------------------------

_NEGATIVE_MEMBERS = (
    ".gitignore",
    "PKG-INFO",
    "LICENSE",
    "README.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "src/fitdocs/__init__.py",
    "src/fitdocs/cli.py",
)

_POSITIVE_MEMBERS = (
    "tests/x.py",
    ".kiro/steering/a.md",
    "agent-log",
    "data/x",
    "uv.lock",
    "a/.fitdocs/b",
    ".fitdocs/quarantine.toml",
    "x.fit",
    # One control per remaining pattern that had no dedicated positive
    # control -- without these, deleting "scripts/*", "release/*",
    # "docs/*", "*.xlsx", or "*.gpx" from the policy left every existing
    # test green (round-1 finding).
    "scripts/check_artifacts.py",  # "scripts/*"
    "release/artifact-policy.toml",  # "release/*"
    "docs/reference/x.md",  # "docs/*"
    "x.xlsx",  # "*.xlsx"
    "x.gpx",  # "*.gpx"
)


@pytest.mark.parametrize("member", _NEGATIVE_MEMBERS)
def test_forbidden_patterns_never_match_shipped_members(member: str) -> None:
    policy = load_policy(REAL_POLICY_PATH)
    matches = [p for p in policy.forbidden_members if fnmatch(member, p)]
    assert matches == [], (
        f"{member!r} unexpectedly matched forbidden pattern(s) {matches!r}"
    )


@pytest.mark.parametrize("member", _POSITIVE_MEMBERS)
def test_forbidden_patterns_catch_every_named_category(member: str) -> None:
    policy = load_policy(REAL_POLICY_PATH)
    assert any(fnmatch(member, p) for p in policy.forbidden_members), (
        f"{member!r} matched no forbidden pattern"
    )


# ---------------------------------------------------------------------------
# Reader: synthetic TOML documents
# ---------------------------------------------------------------------------

_VALID_DOC = """
[wheel]
required = ["fitdocs/__init__.py"]

[sdist]
required = ["pyproject.toml"]

[forbidden]
members = ["tests/*"]

[metadata]
required_fields = ["Name"]
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "artifact-policy.toml"
    path.write_text(text)
    return path


_TABLE_BLOCKS = {
    "wheel": '[wheel]\nrequired = ["fitdocs/__init__.py"]\n',
    "sdist": '[sdist]\nrequired = ["pyproject.toml"]\n',
    "forbidden": '[forbidden]\nmembers = ["tests/*"]\n',
    "metadata": '[metadata]\nrequired_fields = ["Name"]\n',
}


def _doc_with_scalar_override(table: str) -> str:
    """A valid document except `table`'s value is the int 5, not a table.

    The scalar override line is written *before* any `[table]` header, so
    it parses as a genuine top-level key -- writing it after an already-open
    `[table]` header would nest it as a key *inside* that table instead
    (a real TOML trap: `[wheel]\\nrequired = [...]\\nsdist = 5` puts `sdist`
    inside `[wheel]`, not at the top level).
    """
    other_blocks = "\n".join(v for k, v in _TABLE_BLOCKS.items() if k != table)
    return f"{table} = 5\n\n{other_blocks}"


@pytest.mark.parametrize("table", ["wheel", "sdist", "forbidden", "metadata"])
def test_table_present_as_a_scalar_raises_policy_error(
    tmp_path: Path, table: str
) -> None:
    # The table's key name exists but is an int, not a table -- isolates
    # "table present but not a dict" from "key absent" (a fixture that
    # just deletes the whole `[table]` block cannot: both raise the same
    # way, one exercising the wrong branch). An int is deliberately not a
    # string: a string scalar still supports `in`, so a reader that skips
    # the dict-type check would raise for the wrong reason and this test
    # would stay green either way; an int makes `in` itself raise
    # TypeError, which is not PolicyError.
    path = _write(tmp_path, _doc_with_scalar_override(table))
    with pytest.raises(PolicyError):
        load_policy(path)


def test_table_wholly_absent_raises_policy_error(tmp_path: Path) -> None:
    text = _VALID_DOC.replace('[wheel]\nrequired = ["fitdocs/__init__.py"]\n', "")
    path = _write(tmp_path, text)
    with pytest.raises(PolicyError):
        load_policy(path)


@pytest.mark.parametrize(
    ("table", "key"),
    [
        ("wheel", "required"),
        ("sdist", "required"),
        ("forbidden", "members"),
        ("metadata", "required_fields"),
    ],
)
def test_missing_required_key_names_it_in_the_error(
    tmp_path: Path, table: str, key: str
) -> None:
    # Table present but empty (no key at all) rather than table absent --
    # exercises the "key not in table" branch distinctly from the
    # "table absent" branch above.
    text = _VALID_DOC.replace(f"[{table}]\n{key} = ", f"[{table}]\nother_key = ")
    path = _write(tmp_path, text)
    with pytest.raises(PolicyError, match=f"{table}.{key}"):
        load_policy(path)


def test_string_instead_of_list_raises_policy_error(tmp_path: Path) -> None:
    text = _VALID_DOC.replace(
        'required = ["fitdocs/__init__.py"]', 'required = "fitdocs/__init__.py"'
    )
    path = _write(tmp_path, text)
    with pytest.raises(PolicyError, match="wheel.required"):
        load_policy(path)


def test_list_with_an_int_item_raises_policy_error(tmp_path: Path) -> None:
    text = _VALID_DOC.replace('members = ["tests/*"]', "members = [5]")
    path = _write(tmp_path, text)
    with pytest.raises(PolicyError, match="forbidden.members"):
        load_policy(path)


def test_list_with_an_empty_string_item_raises_policy_error(tmp_path: Path) -> None:
    text = _VALID_DOC.replace('members = ["tests/*"]', 'members = [""]')
    path = _write(tmp_path, text)
    with pytest.raises(PolicyError, match="forbidden.members"):
        load_policy(path)


def test_empty_list_raises_policy_error(tmp_path: Path) -> None:
    # `[]` is a list of strings vacuously (no item fails the per-item
    # check), so only the separate "or not raw" emptiness check catches
    # it -- removing that clause from `_read_required_list` must red this
    # test without touching the int-item or empty-string-item tests.
    text = _VALID_DOC.replace('members = ["tests/*"]', "members = []")
    path = _write(tmp_path, text)
    with pytest.raises(PolicyError, match="forbidden.members"):
        load_policy(path)


def test_unknown_top_level_table_is_tolerated(tmp_path: Path) -> None:
    text = _VALID_DOC + "\n[extra]\nsomething = 1\n"
    path = _write(tmp_path, text)
    policy = load_policy(path)
    assert policy.wheel_required == ("fitdocs/__init__.py",)


def test_unknown_key_inside_a_known_table_is_tolerated(tmp_path: Path) -> None:
    text = _VALID_DOC.replace(
        "[wheel]\nrequired", '[wheel]\nextra_key = "anything"\nrequired'
    )
    path = _write(tmp_path, text)
    policy = load_policy(path)
    assert policy.wheel_required == ("fitdocs/__init__.py",)


def test_missing_file_raises_policy_error(tmp_path: Path) -> None:
    with pytest.raises(PolicyError):
        load_policy(tmp_path / "does-not-exist.toml")


def test_malformed_toml_raises_policy_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "[wheel\nrequired = [")
    with pytest.raises(PolicyError):
        load_policy(path)


def test_frozen_dataclass_rejects_attribute_assignment() -> None:
    policy = ArtifactPolicy(
        wheel_required=("a",),
        sdist_required=("b",),
        forbidden_members=("c",),
        required_metadata_fields=("d",),
    )
    with pytest.raises(AttributeError):
        policy.wheel_required = ("z",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Policy-file scan: no key named for a removed category
# ---------------------------------------------------------------------------

_FORBIDDEN_KEY_SUBSTRINGS = (
    "permission",
    "profile",
    "prune",
    "marker",
    "bundl",  # matches "bundle", "bundled", AND "bundling" (the task's
    # Observable names "bundling" specifically -- "bundle"/"bundled" alone
    # let a "when_bundling"-named key pass the scan; round-1 finding).
    "licens",
)


def _walk_keys(document: Mapping[str, Any]) -> Iterator[str]:
    """Yield every key name in `document`, at any nesting depth.

    Recurses into nested tables (`dict` values) and into tables nested
    inside lists (TOML array-of-tables), which is how a planted key could
    hide from a shallow, non-recursive scan.
    """
    for key, value in document.items():
        yield key
        if isinstance(value, dict):
            yield from _walk_keys(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield from _walk_keys(item)


def _count_tables(document: Mapping[str, Any]) -> int:
    count = 0
    for value in document.values():
        if isinstance(value, dict):
            count += 1 + _count_tables(value)
    return count


def _forbidden_keys(document: Mapping[str, Any]) -> list[str]:
    """Every key in `document`, at any nesting depth, matching a forbidden
    category by substring -- case-insensitively, so `PermissionState` is
    caught exactly as `permission_state` is.

    The one scan used by both the real-file assertion and every planted
    positive control, so a change to the walk or the case-folding is
    checked in one place and every caller inherits the fix (round-1: the
    real-file test and the three planted tests each open-coded their own
    lowering, which is why a missing `.lower()` in the walk could survive
    review).
    """
    return [
        key
        for key in _walk_keys(document)
        if any(forbidden in key.lower() for forbidden in _FORBIDDEN_KEY_SUBSTRINGS)
    ]


def test_walk_helper_is_non_vacuous_on_an_empty_document() -> None:
    # Falsity-in-the-starting-state control for the real-file assertion
    # below: an empty document has zero tables, so the real file's count
    # is not trivially satisfied by a helper that always returns >= 4.
    assert _count_tables({}) == 0
    assert list(_walk_keys({})) == []
    assert _forbidden_keys({}) == []


def test_real_policy_file_carries_no_forbidden_category_key() -> None:
    with REAL_POLICY_PATH.open("rb") as handle:
        document = tomllib.load(handle)

    tables_seen = _count_tables(document)
    assert tables_seen >= 4, "the walk is looking at the wrong document"

    keys = list(_walk_keys(document))
    assert keys, "the walk visited no keys"

    hits = _forbidden_keys(document)
    assert hits == [], f"forbidden-category key(s) found: {hits!r}"


def test_scan_catches_a_planted_forbidden_key_nested_in_a_table() -> None:
    with REAL_POLICY_PATH.open("rb") as handle:
        document: dict[str, Any] = dict(tomllib.load(handle))

    # Plant a nested forbidden key two levels deep -- deep enough that a
    # non-recursive (top-level-only) scan would miss it -- and mixed-case,
    # so dropping `.lower()` from `_forbidden_keys` reds this test rather
    # than passing by coincidence (round-1: the inline-lowercased fixtures
    # could not have caught a missing `.lower()`).
    planted = dict(document)
    planted["extra"] = {"nested": {"PermissionState": "granted"}}

    hits = _forbidden_keys(planted)
    assert hits == ["PermissionState"], "the planted key was not reachable by the walk"


def test_scan_catches_a_planted_forbidden_table_name() -> None:
    with REAL_POLICY_PATH.open("rb") as handle:
        document: dict[str, Any] = dict(tomllib.load(handle))

    planted = dict(document)
    planted["prune"] = {"exclude": ["x"]}

    hits = _forbidden_keys(planted)
    assert hits == ["prune"]


def test_scan_catches_a_planted_forbidden_key_inside_an_array_of_tables() -> None:
    with REAL_POLICY_PATH.open("rb") as handle:
        document: dict[str, Any] = dict(tomllib.load(handle))

    # TOML array-of-tables parses as a list of dicts; a shallow walk that
    # only recurses into `dict` values (never into `list` values) would
    # miss a key planted here.
    planted = dict(document)
    planted["extra"] = [{"other": 1}, {"licensing_grant": "yes"}]

    hits = _forbidden_keys(planted)
    assert hits == ["licensing_grant"]


def test_scan_catches_a_planted_bundling_key() -> None:
    # "bundle"/"bundled" alone do not match "bundling" as a substring
    # (neither is a substring of "bundling"); this pins the task's
    # Observable, which names "bundling" specifically, and reds if the
    # `_FORBIDDEN_KEY_SUBSTRINGS` fix ("bundl") is reverted.
    with REAL_POLICY_PATH.open("rb") as handle:
        document: dict[str, Any] = dict(tomllib.load(handle))

    planted = dict(document)
    planted["extra"] = {"bundling_state": "on"}

    hits = _forbidden_keys(planted)
    assert hits == ["bundling_state"]


# ---------------------------------------------------------------------------
# Nothing ships: scripts/ and release/ absent from the sdist allowlist
# ---------------------------------------------------------------------------


def test_sdist_allowlist_excludes_scripts_and_release() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        manifest = tomllib.load(handle)

    only_include = manifest["tool"]["hatch"]["build"]["targets"]["sdist"][
        "only-include"
    ]
    assert "scripts" not in only_include
    assert "release" not in only_include


# ---------------------------------------------------------------------------
# Task 2.1: ReleaseBuilder (`scripts/build_release.py`)
# ---------------------------------------------------------------------------

_EPOCH_A = 1_700_000_000
_EPOCH_B = 1_600_000_000


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _zip_manifest(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {name: _sha256(archive.read(name)) for name in archive.namelist()}


def _tar_manifest(path: Path) -> dict[str, str]:
    with tarfile.open(path, "r:gz") as archive:
        manifest = {}
        for member in archive.getmembers():
            if member.isfile():
                extracted = archive.extractfile(member)
                assert extracted is not None
                manifest[member.name] = _sha256(extracted.read())
        return manifest


def _artifact(paths: tuple[Path, ...], suffix: str) -> Path:
    matches = [p for p in paths if p.name.endswith(suffix)]
    assert len(matches) == 1, f"expected exactly one {suffix!r} artifact in {paths!r}"
    return matches[0]


@pytest.fixture(scope="module")
def build_a(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ...]:
    out_dir = tmp_path_factory.mktemp("dist_a")
    return build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_A)


@pytest.fixture(scope="module")
def build_a_repeat(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ...]:
    out_dir = tmp_path_factory.mktemp("dist_a_repeat")
    return build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_A)


@pytest.fixture(scope="module")
def build_b(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ...]:
    out_dir = tmp_path_factory.mktemp("dist_b")
    return build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_B)


def test_build_yields_exactly_one_wheel_and_one_sdist(
    build_a: tuple[Path, ...],
) -> None:
    assert len(build_a) == 2
    suffixes = sorted(".whl" if p.name.endswith(".whl") else ".tar.gz" for p in build_a)
    assert suffixes == [".tar.gz", ".whl"]
    for path in build_a:
        assert path.exists()


def test_build_clears_a_stale_artifact_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out_dir = tmp_path / "dist"
    out_dir.mkdir()
    stale = out_dir / "stale.whl"
    stale.write_text("not a real wheel")
    stale_other = out_dir / "stale.txt"
    stale_other.write_text("not an artifact at all")
    # falsity-before: both stale files are really there
    assert stale.exists()
    assert stale_other.exists()

    def fake_run(
        cmd: list[str],
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        (out_dir / "fitdocs-0.0.0-py3-none-any.whl").write_bytes(b"whl")
        (out_dir / "fitdocs-0.0.0.tar.gz").write_bytes(b"tgz")
        returncode = 0
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_A)

    assert not stale.exists()
    assert not stale_other.exists()
    assert stale not in result
    assert all(p.exists() for p in result)


def test_build_removes_partial_output_on_build_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out_dir = tmp_path / "dist"

    def failing_run(
        cmd: list[str],
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        # A real failed `uv build` can still leave partial files behind --
        # both artifact kinds, so a cleanup that only unlinks one kind
        # (e.g. `*.whl` alone) still leaves visible wreckage.
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "partial.whl").write_bytes(b"partial")
        (out_dir / "partial.tar.gz").write_bytes(b"partial")
        if check:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", failing_run)
    with pytest.raises(build_release.BuildError):
        build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_A)

    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_build_rejects_a_wrong_artifact_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out_dir = tmp_path / "dist"

    def two_wheels_run(
        cmd: list[str],
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "a-0.0.0-py3-none-any.whl").write_bytes(b"a")
        (out_dir / "b-0.0.0-py3-none-any.whl").write_bytes(b"b")
        (out_dir / "a-0.0.0.tar.gz").write_bytes(b"tgz")
        returncode = 0
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", two_wheels_run)
    with pytest.raises(build_release.BuildError):
        build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_A)

    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_build_invokes_uv_with_expected_command_env_and_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exact command line, cwd, and SOURCE_DATE_EPOCH the build issues.

    Uses a fake `subprocess.run` (no real `uv build`) so it stays fast and
    can assert on the literal recorded values rather than inferring them
    indirectly from archive contents.
    """
    out_dir = tmp_path / "dist"
    calls: list[dict[str, Any]] = []

    def _record_and_succeed(
        cmd: list[str],
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append({"cmd": cmd, "cwd": cwd, "env": env, "check": check})
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _record_and_succeed)

    # First call: explicit epoch. The fake never writes artifacts, so
    # `build()` will raise on the post-build count check -- that is fine,
    # this test only cares about what `subprocess.run` was called with.
    with pytest.raises(build_release.BuildError):
        build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_A)

    assert len(calls) == 1
    call = calls[0]
    assert call["cmd"][1:] == [
        "build",
        "--sdist",
        "--wheel",
        "--out-dir",
        str(out_dir.resolve()),
    ]
    assert call["cwd"] == str(build_release.REPO_ROOT.resolve())
    # Literal strings, not `str(_EPOCH_A)` -- a reader constructing the
    # expected value the same way the production code does would not
    # notice a wrong constant on either side.
    assert call["env"]["SOURCE_DATE_EPOCH"] == "1700000000"

    calls.clear()
    out_dir_default = tmp_path / "dist_default"
    with pytest.raises(build_release.BuildError):
        build_release.build(out_dir=out_dir_default, source_date_epoch=None)

    assert len(calls) == 1
    assert calls[0]["env"]["SOURCE_DATE_EPOCH"] == "315532800"


def test_build_refuses_a_relative_out_dir_that_resolves_to_the_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_root = tmp_path / "fake_repo"
    fake_root.mkdir()
    marker = fake_root / "marker.txt"
    marker.write_text("x")
    monkeypatch.setattr(build_release, "REPO_ROOT", fake_root)
    monkeypatch.chdir(fake_root)

    def _must_not_be_called(
        cmd: list[str],
        *,
        cwd: str,
        capture_output: bool,
        text: bool,
        env: dict[str, str],
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError(
            "subprocess.run must not be called once the repo-root guard trips"
        )

    monkeypatch.setattr(subprocess, "run", _must_not_be_called)

    with pytest.raises(ValueError):
        build_release.build(out_dir=Path("."), source_date_epoch=_EPOCH_A)

    assert marker.exists()


def test_build_refuses_to_clear_the_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_root = tmp_path / "nested" / "fake_repo"
    fake_root.mkdir(parents=True)
    marker = fake_root / "marker.txt"
    marker.write_text("x")
    monkeypatch.setattr(build_release, "REPO_ROOT", fake_root)

    with pytest.raises(ValueError):
        build_release.build(out_dir=fake_root, source_date_epoch=_EPOCH_A)

    assert marker.exists()


@pytest.mark.parametrize("levels_up", [1, 2])
def test_build_refuses_to_clear_an_ancestor_of_the_repo_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, levels_up: int
) -> None:
    fake_root = tmp_path / "nested" / "fake_repo"
    fake_root.mkdir(parents=True)
    marker = tmp_path / "marker.txt"
    marker.write_text("x")
    monkeypatch.setattr(build_release, "REPO_ROOT", fake_root)

    ancestor = fake_root.parents[levels_up - 1]
    with pytest.raises(ValueError):
        build_release.build(out_dir=ancestor, source_date_epoch=_EPOCH_A)

    assert marker.exists()


def test_build_runs_regardless_of_process_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out_dir = tmp_path / "dist"
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    result = build_release.build(out_dir=out_dir, source_date_epoch=_EPOCH_A)
    assert len(result) == 2


def test_reproducible_build_same_epoch_matches_member_names_and_digests(
    build_a: tuple[Path, ...], build_a_repeat: tuple[Path, ...]
) -> None:
    wheel_a = _artifact(build_a, ".whl")
    wheel_a2 = _artifact(build_a_repeat, ".whl")
    sdist_a = _artifact(build_a, ".tar.gz")
    sdist_a2 = _artifact(build_a_repeat, ".tar.gz")

    manifest_a = _zip_manifest(wheel_a)
    manifest_a2 = _zip_manifest(wheel_a2)
    assert manifest_a, "the wheel manifest is empty -- nothing was actually scanned"
    assert sorted(manifest_a) == sorted(manifest_a2)
    assert manifest_a == manifest_a2
    assert _sha256(wheel_a.read_bytes()) == _sha256(wheel_a2.read_bytes())

    tar_manifest_a = _tar_manifest(sdist_a)
    tar_manifest_a2 = _tar_manifest(sdist_a2)
    assert tar_manifest_a, "the sdist manifest is empty -- nothing was actually scanned"
    assert sorted(tar_manifest_a) == sorted(tar_manifest_a2)
    assert tar_manifest_a == tar_manifest_a2
    assert _sha256(sdist_a.read_bytes()) == _sha256(sdist_a2.read_bytes())


def test_different_epoch_changes_whole_archive_digest_but_not_member_names(
    build_a: tuple[Path, ...], build_b: tuple[Path, ...]
) -> None:
    wheel_a = _artifact(build_a, ".whl")
    wheel_b = _artifact(build_b, ".whl")
    sdist_a = _artifact(build_a, ".tar.gz")
    sdist_b = _artifact(build_b, ".tar.gz")

    assert sorted(_zip_manifest(wheel_a)) == sorted(_zip_manifest(wheel_b))
    assert _sha256(wheel_a.read_bytes()) != _sha256(wheel_b.read_bytes())

    assert sorted(_tar_manifest(sdist_a)) == sorted(_tar_manifest(sdist_b))
    assert _sha256(sdist_a.read_bytes()) != _sha256(sdist_b.read_bytes())


def test_help_mentions_out_dir_and_epoch_but_no_profile_variant_or_prune(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_release.main(["--help"])
    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--out-dir" in output
    assert "--source-date-epoch" in output
    for forbidden in ("profile", "variant", "prune"):
        assert forbidden not in output.lower()


def test_parser_option_strings_are_exactly_the_expected_set() -> None:
    parser = build_release._build_parser()
    option_strings = {
        opt for action in parser._actions for opt in action.option_strings
    }
    assert option_strings == {"-h", "--help", "--out-dir", "--source-date-epoch"}


def test_main_returns_0_and_prints_both_paths_on_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    fake_wheel = tmp_path / "fitdocs-0.0.0-py3-none-any.whl"
    fake_sdist = tmp_path / "fitdocs-0.0.0.tar.gz"
    fake_wheel.write_bytes(b"w")
    fake_sdist.write_bytes(b"t")

    def fake_build(*, out_dir: Path, source_date_epoch: int | None) -> tuple[Path, ...]:
        return (fake_sdist, fake_wheel)

    monkeypatch.setattr(build_release, "build", fake_build)
    exit_code = build_release.main(["--out-dir", str(tmp_path)])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert str(fake_wheel) in output
    assert str(fake_sdist) in output


def test_main_returns_1_and_prints_stderr_on_build_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    def failing_build(
        *, out_dir: Path, source_date_epoch: int | None
    ) -> tuple[Path, ...]:
        raise RuntimeError("synthetic build failure -- distinguishable in stderr")

    monkeypatch.setattr(build_release, "build", failing_build)
    exit_code = build_release.main(["--out-dir", str(tmp_path)])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "synthetic build failure" in captured.err
    assert captured.out == ""


def test_build_release_module_imports_nothing_from_fitdocs() -> None:
    source = (REPO_ROOT / "scripts" / "build_release.py").read_text()
    tree = ast.parse(source)
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module.split(".")[0])
    assert imported_names, "the import scan found no imports -- wrong file parsed"
    assert "fitdocs" not in imported_names


# ---------------------------------------------------------------------------
# Task 2.2: ArtifactChecker (`scripts/check_artifacts.py`)
# ---------------------------------------------------------------------------

# A metadata document satisfying the REAL policy's `[metadata].required_fields`
# plus the checker's own always-on checks (`Requires-Dist` present, a
# non-empty body).
_CLEAN_METADATA = """Metadata-Version: 2.1
Name: fitdocs
Version: 9.9.9
Summary: Turn .fit files into rich per-workout markdown documents.
License-Expression: MIT
Requires-Python: >=3.11
Project-URL: Source, https://github.com/joshua-stauffer/fitdocs
Author-email: Josh Stauffer <x@example.com>
Requires-Dist: typer>=0.12

This is the long description body.
"""

_CLEAN_WHEEL_MEMBERS = {
    "fitdocs/__init__.py": b"",
    "fitdocs/py.typed": b"",
    "fitdocs/skills/build-training-block/SKILL.md": b"# skill",
    "fitdocs/skills/build-training-block/example-block.toml": b"",
    "fitdocs/skills/fitdocs-workouts/SKILL.md": b"# skill",
}

_CLEAN_SDIST_MEMBERS = {
    "pyproject.toml": b"[project]\nname = 'fitdocs'\n",
    "README.md": b"# fitdocs",
    "LICENSE": b"MIT License",
    "CHANGELOG.md": b"# Changelog",
    "src/fitdocs/__init__.py": b"",
}


def _make_wheel(
    dir_: Path,
    members: dict[str, bytes],
    *,
    metadata: str,
    links: dict[str, str] | None = None,
    name: str = "fitdocs",
    version: str = "9.9.9",
) -> Path:
    """Write a valid-shaped wheel: `<name>-<version>-py3-none-any.whl` with a
    `<name>-<version>.dist-info/METADATA` entry, `members`, and, for each
    `links` entry, a symlink member whose data is the target path (the
    Unix-mode bits packed into `ZipInfo.external_attr`'s upper 16 bits mark
    it as a link -- `0o120777`: S_IFLNK plus rwxrwxrwx permission bits).
    """
    links = links or {}
    path = dir_ / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as zf:
        for member_name, data in members.items():
            zf.writestr(member_name, data)
        zf.writestr(f"{name}-{version}.dist-info/METADATA", metadata)
        for link_name, target in links.items():
            info = zipfile.ZipInfo(link_name)
            info.external_attr = 0o120777 << 16
            zf.writestr(info, target)
    return path


def _make_sdist(
    dir_: Path,
    members: dict[str, bytes],
    *,
    pkg_info: str,
    links: dict[str, str] | None = None,
    dirs: tuple[str, ...] = (),
    name: str = "fitdocs",
    version: str = "9.9.9",
) -> Path:
    """Write a valid-shaped sdist: `<name>-<version>.tar.gz` with every
    member under a `<name>-<version>/` top directory, a `PKG-INFO` entry at
    that directory's root, `members`, `links` symlink members, and `dirs`
    explicit directory entries.
    """
    links = links or {}
    prefix = f"{name}-{version}"
    path = dir_ / f"{prefix}.tar.gz"
    with tarfile.open(path, "w:gz") as tf:
        for member_name, data in members.items():
            info = tarfile.TarInfo(name=f"{prefix}/{member_name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        pkg_info_bytes = pkg_info.encode("utf-8")
        pkg_info_info = tarfile.TarInfo(name=f"{prefix}/PKG-INFO")
        pkg_info_info.size = len(pkg_info_bytes)
        tf.addfile(pkg_info_info, io.BytesIO(pkg_info_bytes))

        for link_name, target in links.items():
            link_info = tarfile.TarInfo(name=f"{prefix}/{link_name}")
            link_info.type = tarfile.SYMTYPE
            link_info.linkname = target
            tf.addfile(link_info)

        for dir_name in dirs:
            dir_info = tarfile.TarInfo(name=f"{prefix}/{dir_name}")
            dir_info.type = tarfile.DIRTYPE
            dir_info.mode = 0o755
            tf.addfile(dir_info)
    return path


@pytest.fixture
def clean_dist(tmp_path: Path) -> Path:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)
    return dist_dir


@pytest.fixture
def agreeing_manifest_and_changelog(tmp_path: Path) -> tuple[Path, Path]:
    """A synthetic `pyproject.toml` (version `9.9.9`) and `CHANGELOG.md`
    (newest released entry `## [9.9.9] - 2026-01-01`) that agree with each
    other and with `_CLEAN_METADATA` / `clean_dist`'s version -- so a test
    exercising `main`'s artifact-side behavior can pass `--manifest` /
    `--changelog` and get a no-op from the version-consistency gate.
    """
    manifest_path = tmp_path / "agreeing-pyproject.toml"
    manifest_path.write_text('[project]\nname = "fitdocs"\nversion = "9.9.9"\n')
    changelog_path = tmp_path / "agreeing-CHANGELOG.md"
    changelog_path.write_text(
        "# Changelog\n\n## [Unreleased]\n\n"
        "## [9.9.9] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    return manifest_path, changelog_path


# --- report shape ------------------------------------------------------


def test_violation_field_order_is_subject_kind_detail_remedy() -> None:
    assert tuple(f.name for f in dataclasses.fields(Violation)) == (
        "subject",
        "kind",
        "detail",
        "remedy",
    )


def test_violation_kind_is_a_strenum_with_the_seven_members_in_design_order() -> None:
    assert issubclass(ViolationKind, StrEnum)
    assert [member.name for member in ViolationKind] == [
        "MISSING_REQUIRED",
        "FORBIDDEN_MEMBER",
        "LINK_MEMBER",
        "ENCUMBERED_CONTENT",
        "GATE_NOT_RUN",
        "METADATA_INCOMPLETE",
        "VERSION_MISMATCH",
    ]


# --- clean fixture: trips nothing ---------------------------------------


def test_clean_fixture_against_the_real_policy_trips_no_violations(
    clean_dist: Path,
) -> None:
    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(clean_dist, policy=policy, repo_root=REPO_ROOT)
    assert violations == ()


# --- MISSING_REQUIRED ----------------------------------------------------


def test_missing_required_wheel_member_reported_exactly_once(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    # The required member is MOVED (to "src/fitdocs/py.typed"), not deleted:
    # it is still present as a suffix/substring of another member's path,
    # only absent as an exact match. A membership check weakened to
    # `any(m.endswith(name) for m in present)` would wrongly treat the moved
    # file as satisfying the requirement and stay green here. A
    # differently-cased path ("fitdocs/PY.TYPED") is also present, pinning
    # exact-match case-sensitivity the same way: a check weakened to
    # case-insensitive membership would treat it as satisfying the
    # requirement too.
    members = dict(_CLEAN_WHEEL_MEMBERS)
    del members["fitdocs/py.typed"]
    members["src/fitdocs/py.typed"] = b""
    members["fitdocs/PY.TYPED"] = b""
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.MISSING_REQUIRED
    assert violation.subject == wheel_path.name  # the filename, not a full path
    assert "py.typed" in violation.detail


def test_missing_required_sdist_member_reported_exactly_once(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    sdist_members = dict(_CLEAN_SDIST_MEMBERS)
    del sdist_members["CHANGELOG.md"]
    sdist_path = _make_sdist(dist_dir, sdist_members, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.MISSING_REQUIRED
    assert violation.subject == sdist_path.name  # not the wheel -- the sdist is clean
    assert "CHANGELOG.md" in violation.detail


# --- FORBIDDEN_MEMBER ------------------------------------------------------


def test_forbidden_member_reported_exactly_once(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    sdist_members = dict(_CLEAN_SDIST_MEMBERS)
    sdist_members["tests/x.py"] = b""
    sdist_path = _make_sdist(dist_dir, sdist_members, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.FORBIDDEN_MEMBER
    assert violation.subject == sdist_path.name
    assert "tests/x.py" in violation.detail


def test_forbidden_directory_entry_is_reported(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    policy = ArtifactPolicy(
        wheel_required=(),
        sdist_required=("PKG-INFO",),
        forbidden_members=("bad/*",),
        required_metadata_fields=(),
    )
    metadata = "Name: x\nRequires-Dist: y\n\nbody text\n"
    _make_wheel(dist_dir, {}, metadata=metadata)
    _make_sdist(dist_dir, {}, pkg_info=metadata, dirs=("bad/",))

    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.FORBIDDEN_MEMBER
    assert "bad/" in violations[0].detail


def test_fnmatchcase_positive_control_a_lowercase_match_is_caught(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    policy = ArtifactPolicy(
        wheel_required=(),
        sdist_required=("PKG-INFO",),
        forbidden_members=("tests/*",),
        required_metadata_fields=(),
    )
    metadata = "Name: x\nRequires-Dist: y\n\nbody text\n"
    _make_wheel(dist_dir, {"tests/x.py": b""}, metadata=metadata)
    _make_sdist(dist_dir, {}, pkg_info=metadata)

    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.FORBIDDEN_MEMBER


def test_fnmatchcase_is_case_sensitive_a_capital_t_is_not_forbidden(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    policy = ArtifactPolicy(
        wheel_required=(),
        sdist_required=("PKG-INFO",),
        forbidden_members=("tests/*",),
        required_metadata_fields=(),
    )
    metadata = "Name: x\nRequires-Dist: y\n\nbody text\n"
    _make_wheel(dist_dir, {"Tests/x.py": b""}, metadata=metadata)
    _make_sdist(dist_dir, {}, pkg_info=metadata)

    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert violations == ()


# --- LINK_MEMBER -----------------------------------------------------------


def test_link_member_reported_even_when_its_target_text_is_clean(
    tmp_path: Path,
) -> None:
    dist_dir_without_link = tmp_path / "dist_without_link"
    dist_dir_without_link.mkdir()
    _make_wheel(dist_dir_without_link, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir_without_link, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)
    policy = load_policy(REAL_POLICY_PATH)

    # Falsity-before: the same fixture minus the link is clean.
    assert (
        check_artifacts(dist_dir_without_link, policy=policy, repo_root=REPO_ROOT) == ()
    )

    dist_dir_with_link = tmp_path / "dist_with_link"
    dist_dir_with_link.mkdir()
    wheel_path = _make_wheel(
        dist_dir_with_link,
        _CLEAN_WHEEL_MEMBERS,
        metadata=_CLEAN_METADATA,
        links={"fitdocs/extra.md": "LICENSE"},
    )
    _make_sdist(dist_dir_with_link, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    violations = check_artifacts(dist_dir_with_link, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.LINK_MEMBER
    assert violation.subject == wheel_path.name
    assert "fitdocs/extra.md" in violation.detail
    assert "LICENSE" in violation.detail


def test_link_member_in_sdist_reported_when_wheel_is_clean(tmp_path: Path) -> None:
    dist_dir_without_link = tmp_path / "dist_without_link"
    dist_dir_without_link.mkdir()
    _make_wheel(dist_dir_without_link, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir_without_link, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)
    policy = load_policy(REAL_POLICY_PATH)

    # Falsity-before: the same fixture minus the link is clean.
    assert (
        check_artifacts(dist_dir_without_link, policy=policy, repo_root=REPO_ROOT) == ()
    )

    dist_dir_with_link = tmp_path / "dist_with_link"
    dist_dir_with_link.mkdir()
    _make_wheel(dist_dir_with_link, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    sdist_path = _make_sdist(
        dist_dir_with_link,
        _CLEAN_SDIST_MEMBERS,
        pkg_info=_CLEAN_METADATA,
        links={"extra.md": "LICENSE"},
    )

    violations = check_artifacts(dist_dir_with_link, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.LINK_MEMBER
    assert violation.subject == sdist_path.name  # not the wheel -- the wheel is clean
    assert "extra.md" in violation.detail
    assert "LICENSE" in violation.detail


def test_link_named_as_a_required_member_is_both_link_and_missing_required(
    tmp_path: Path,
) -> None:
    """A link whose name IS a required member's path satisfies neither
    check: it must still be reported as LINK_MEMBER (a link is never
    scanned for what it names), AND the required member is still MISSING
    (`present` only counts `is_regular` members, so a link can never
    silently stand in for the file the policy requires).
    """
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    del members["fitdocs/py.typed"]
    wheel_path = _make_wheel(
        dist_dir,
        members,
        metadata=_CLEAN_METADATA,
        links={"fitdocs/py.typed": "LICENSE"},
    )
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 2
    kinds = {v.kind for v in violations}
    assert kinds == {ViolationKind.LINK_MEMBER, ViolationKind.MISSING_REQUIRED}
    assert all(v.subject == wheel_path.name for v in violations)
    link_violation = next(v for v in violations if v.kind == ViolationKind.LINK_MEMBER)
    missing_violation = next(
        v for v in violations if v.kind == ViolationKind.MISSING_REQUIRED
    )
    assert "fitdocs/py.typed" in link_violation.detail
    assert "py.typed" in missing_violation.detail


# --- METADATA_INCOMPLETE ----------------------------------------------------


def test_metadata_incomplete_missing_field_reported_exactly_once(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata_missing_author = _CLEAN_METADATA.replace(
        "Author-email: Josh Stauffer <x@example.com>\n", ""
    )
    wheel_path = _make_wheel(
        dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=metadata_missing_author
    )
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.METADATA_INCOMPLETE
    assert violation.subject == wheel_path.name
    assert "Author-email" in violation.detail


def test_metadata_incomplete_empty_value_is_treated_as_absent(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata_empty_author = _CLEAN_METADATA.replace(
        "Author-email: Josh Stauffer <x@example.com>\n", "Author-email: \n"
    )
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=metadata_empty_author)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.METADATA_INCOMPLETE
    assert "Author-email" in violations[0].detail


def test_metadata_incomplete_missing_requires_dist_reported(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata_no_requires_dist = _CLEAN_METADATA.replace(
        "Requires-Dist: typer>=0.12\n", ""
    )
    wheel_path = _make_wheel(
        dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=metadata_no_requires_dist
    )
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.METADATA_INCOMPLETE
    assert violation.subject == wheel_path.name
    assert "Requires-Dist" in violation.detail


def test_metadata_incomplete_empty_body_reported(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata_no_body = _CLEAN_METADATA.split("\n\n", 1)[0] + "\n\n"
    wheel_path = _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=metadata_no_body)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.METADATA_INCOMPLETE
    assert violation.subject == wheel_path.name
    assert "body" in violation.detail


def test_metadata_incomplete_in_sdist_reported_when_wheel_is_clean(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    sdist_pkg_info_missing_requires_dist = _CLEAN_METADATA.replace(
        "Requires-Dist: typer>=0.12\n", ""
    )
    sdist_path = _make_sdist(
        dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=sdist_pkg_info_missing_requires_dist
    )

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.METADATA_INCOMPLETE
    assert violation.subject == sdist_path.name  # not the wheel -- the wheel is clean
    assert "Requires-Dist" in violation.detail


# --- ordering ---------------------------------------------------------------


def test_violations_sort_deterministically_by_subject_then_kind(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    policy = ArtifactPolicy(
        wheel_required=("required.txt",),
        sdist_required=("required.txt", "PKG-INFO"),
        forbidden_members=("bad/*",),
        required_metadata_fields=(),
    )
    metadata = "Name: x\nRequires-Dist: y\n\nbody text\n"
    # "aaa..." sdist: missing "required.txt" -> exactly one MISSING_REQUIRED.
    _make_sdist(dist_dir, {}, pkg_info=metadata, name="aaa")
    # "zzz..." wheel: missing "required.txt" (MISSING_REQUIRED) AND carrying
    # "bad/y.py" (FORBIDDEN_MEMBER) -- two violations on the SAME subject,
    # so the expected sequence also pins the (kind, detail) tiebreak
    # *within* one subject, not merely subject-vs-subject ordering.
    #
    # Natural emission order -- the order `check_artifacts` appends findings
    # in, before any sort -- is [(zzz, MISSING_REQUIRED), (aaa,
    # MISSING_REQUIRED), (zzz, FORBIDDEN_MEMBER)] (missing-required runs
    # wheel-then-sdist, then forbidden-member runs wheel-then-sdist): this
    # does not equal the sorted sequence asserted below on any of its three
    # positions, so the fixture cannot be satisfied by a no-op "sort".
    _make_wheel(dist_dir, {"bad/y.py": b""}, metadata=metadata, name="zzz")

    violations_first_run = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    violations_second_run = check_artifacts(
        dist_dir, policy=policy, repo_root=REPO_ROOT
    )

    assert violations_first_run == violations_second_run

    subjects_and_kinds = [(v.subject, v.kind) for v in violations_first_run]
    assert subjects_and_kinds == [
        ("aaa-9.9.9.tar.gz", ViolationKind.MISSING_REQUIRED),
        ("zzz-9.9.9-py3-none-any.whl", ViolationKind.FORBIDDEN_MEMBER),
        ("zzz-9.9.9-py3-none-any.whl", ViolationKind.MISSING_REQUIRED),
    ]


# --- every violation within each check, not only the first -----------------


def test_every_violation_within_each_check_is_reported_not_only_the_first(
    tmp_path: Path,
) -> None:
    """One artifact (the wheel) trips every implemented check TWICE OR MORE
    at once, while the sdist is entirely clean -- so a check that silently
    stops after its first finding (`break`, or slicing the result to one
    element) reds this test even though every single-violation fixture
    elsewhere in this file stays green (a fixture with only one trigger per
    check cannot distinguish "reports one" from "reports all").
    """
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    policy = ArtifactPolicy(
        wheel_required=("a.txt", "b.txt"),
        sdist_required=("PKG-INFO",),
        forbidden_members=("bad/*",),
        required_metadata_fields=("Alpha", "Beta"),
    )
    wheel_path = _make_wheel(
        dist_dir,
        {"bad/one.py": b"", "bad/two.py": b""},
        metadata="Name: x\n\n",
        links={"extra_link_one": "target_one", "extra_link_two": "target_two"},
        name="x",
    )
    # The sdist satisfies its own policy entirely -- required member
    # present, no forbidden member, no link, and metadata with both
    # required fields, `Requires-Dist`, and a non-empty body -- so every
    # violation below must be attributed to the wheel alone.
    _make_sdist(
        dist_dir,
        {"a.txt": b"", "b.txt": b""},
        pkg_info="Name: x\nAlpha: 1\nBeta: 2\nRequires-Dist: y\n\nbody\n",
        name="x",
    )

    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert violations, "the fixture must trip at least one violation"
    assert all(v.subject == wheel_path.name for v in violations), (
        f"expected every violation on the wheel only (the sdist is clean): "
        f"{violations!r}"
    )

    kind_counts = Counter(v.kind for v in violations)
    assert kind_counts == Counter(
        {
            ViolationKind.MISSING_REQUIRED: 2,
            ViolationKind.FORBIDDEN_MEMBER: 2,
            ViolationKind.LINK_MEMBER: 2,
            ViolationKind.METADATA_INCOMPLETE: 4,
        }
    )
    assert all(v.remedy.strip() for v in violations)


# --- hard errors -------------------------------------------------------


def test_two_wheels_is_a_hard_checker_error(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata = "Name: x\nRequires-Dist: y\n\nbody text\n"
    _make_wheel(dist_dir, {}, metadata=metadata, name="a")
    _make_wheel(dist_dir, {}, metadata=metadata, name="b")
    _make_sdist(dist_dir, {}, pkg_info=metadata, name="c")
    policy = ArtifactPolicy(
        wheel_required=(),
        sdist_required=(),
        forbidden_members=(),
        required_metadata_fields=(),
    )

    with pytest.raises(CheckerError):
        check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)


def test_zero_sdists_is_a_hard_checker_error(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata = "Name: x\nRequires-Dist: y\n\nbody text\n"
    _make_wheel(dist_dir, {}, metadata=metadata)
    policy = ArtifactPolicy(
        wheel_required=(),
        sdist_required=(),
        forbidden_members=(),
        required_metadata_fields=(),
    )

    with pytest.raises(CheckerError):
        check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)


def test_zero_wheels_is_a_hard_checker_error(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata = "Name: x\nRequires-Dist: y\n\nbody text\n"
    _make_sdist(dist_dir, {}, pkg_info=metadata)
    policy = ArtifactPolicy(
        wheel_required=(),
        sdist_required=(),
        forbidden_members=(),
        required_metadata_fields=(),
    )

    with pytest.raises(CheckerError):
        check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)


def test_main_missing_policy_returns_2_and_names_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    missing_policy = tmp_path / "does-not-exist.toml"

    exit_code = check_artifacts_main(
        ["--dist-dir", str(dist_dir), "--policy", str(missing_policy)]
    )

    assert exit_code == 2
    assert str(missing_policy) in capsys.readouterr().err


def test_main_malformed_policy_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    bad_policy = tmp_path / "bad.toml"
    bad_policy.write_text("[wheel\nrequired = [")

    exit_code = check_artifacts_main(
        ["--dist-dir", str(dist_dir), "--policy", str(bad_policy)]
    )

    assert exit_code == 2
    assert capsys.readouterr().err  # a message was printed, not silence


# --- main() ----------------------------------------------------------------


def test_main_on_a_clean_dir_returns_0_and_names_both_filenames(
    clean_dist: Path,
    agreeing_manifest_and_changelog: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    # task 2.4: main now also runs the version-consistency gate FIRST, using
    # a synthetic manifest/changelog agreeing with `clean_dist`'s "9.9.9" --
    # the real repo's pyproject.toml/CHANGELOG.md would otherwise trip the
    # real no-released-entry violation here (see the dedicated real-files
    # test below), which is not what THIS test is pinning.
    manifest_path, changelog_path = agreeing_manifest_and_changelog
    before = sorted(clean_dist.iterdir())

    exit_code = check_artifacts_main(
        [
            "--dist-dir",
            str(clean_dist),
            "--policy",
            str(REAL_POLICY_PATH),
            "--manifest",
            str(manifest_path),
            "--changelog",
            str(changelog_path),
        ]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "fitdocs-9.9.9-py3-none-any.whl" in out
    assert "fitdocs-9.9.9.tar.gz" in out
    # Writes nothing: the directory listing is unchanged across the call.
    assert sorted(clean_dist.iterdir()) == before


def test_main_on_a_violating_dir_returns_1_and_lists_every_violation(
    tmp_path: Path,
    agreeing_manifest_and_changelog: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path, changelog_path = agreeing_manifest_and_changelog
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, {}, metadata="Name: x\n\nbody\n")
    _make_sdist(dist_dir, {}, pkg_info="Name: x\n\nbody\n")

    policy = load_policy(REAL_POLICY_PATH)
    expected_violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert len(expected_violations) > 1, (
        "the fixture must trip more than one violation for this test to mean anything"
    )
    # falsity-before / independence check: the agreeing manifest/changelog
    # contribute nothing of their own here, so the exit-code and count
    # assertions below are pinning ONLY the artifact-side violations.
    assert check_version_consistency(manifest_path, changelog_path, None) == ()

    exit_code = check_artifacts_main(
        [
            "--dist-dir",
            str(dist_dir),
            "--policy",
            str(REAL_POLICY_PATH),
            "--manifest",
            str(manifest_path),
            "--changelog",
            str(changelog_path),
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert f"{len(expected_violations)} violation(s)" in err
    # One line per violation plus the summary line.
    assert err.count("\n") == len(expected_violations) + 1


def test_main_with_real_manifest_and_changelog_reports_only_the_no_entry_violation(
    clean_dist: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main` with its DEFAULT `--manifest`/`--changelog` (the real
    `pyproject.toml` / `CHANGELOG.md`) against an otherwise-clean artifact
    set: today the real changelog has no released entry (task 1.3's pinned
    state), so this is exit 1 with EXACTLY one violation -- the no-entry
    finding -- and the artifact checks report nothing on top of it. This
    will need updating the day the first release entry is written (see
    `tests/test_changelog.py::test_real_changelog_has_no_released_version_literal`,
    which pins the same real-file state from the changelog's side).
    """
    exit_code = check_artifacts_main(
        ["--dist-dir", str(clean_dist), "--policy", str(REAL_POLICY_PATH)]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "1 violation(s)" in err
    assert "version_mismatch" in err
    assert "no released entry" in err


# --- real-artifact smoke -----------------------------------------------


def test_real_build_with_the_real_policy_has_zero_violations(
    build_a: tuple[Path, ...],
) -> None:
    dist_dir = build_a[0].parent
    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert violations == (), f"real build failed conformance: {violations!r}"


# --- import isolation (superseded by the task 2.3 import-audit test below) -


def test_check_artifacts_module_imports_nothing_from_fitdocs() -> None:
    source = (REPO_ROOT / "scripts" / "check_artifacts.py").read_text()
    tree = ast.parse(source)
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module.split(".")[0])
    assert imported_names, "the import scan found no imports -- wrong file parsed"
    assert "fitdocs" not in imported_names


# ---------------------------------------------------------------------------
# Task 2.3: the encumbered-content gate (ENCUMBERED_CONTENT / GATE_NOT_RUN)
# ---------------------------------------------------------------------------
#
# Discrimination sweep for the token matcher's every relaxation class, per
# `.kiro/steering/change-protocol.md` -- {absent, wrong text, case,
# whitespace, partial match, type, scope/off-by-one}:
#
# | class           | test                                                        |
# |------------------|--------------------------------------------------------------|
# | absent           | test_needle_absent_from_a_member_trips_no_encumbered_content |
# | wrong text       | test_needle_absent_from_a_member_trips_no_encumbered_content |
# | case             | test_case_variant_needle_is_still_caught                     |
# | whitespace       | test_wrapped_multiword_needle_across_a_line_break_is_caught  |
# | partial match    | test_needle_absent_from_a_member_trips_no_encumbered_content |
# |                  | (member content shares no substring with the needle)         |
# | type (name-only  | test_needle_in_binary_member_name_is_caught_by_name_only,    |
# | vs content scan) | test_needle_in_binary_member_content_only_is_not_caught      |
# | scope/off-by-one | test_metadata_body_only_needle_is_caught_... tests (member-  |
# |                  | name-only fixtures leave the body clean; body-only fixtures  |
# |                  | leave every non-metadata member clean -- the two cannot be   |
# |                  | confused); test_needle_in_binary_member_directory_component_ |
# |                  | is_caught (a directory component, not only the basename,     |
# |                  | must match)                                                   |
#
# Additional round-1 rejection follow-ups, not a distinct relaxation class:
# test_needle_deep_in_a_large_member_is_still_caught (no truncated read),
# test_needle_beside_an_undecodable_byte_is_still_caught (no strict-decode
# skip), test_needle_in_an_ordinary_sdist_text_member_is_caught and
# test_needle_in_an_sdist_binary_member_name_is_caught_by_name_only (the
# sdist side of both the text and binary paths, not only the wheel side).
#
# Round-2 rejection follow-up, not a distinct relaxation class:
# test_fingerprinted_control_value_in_the_sdist_is_caught (the sdist side
# of the value-oracle control, not only the wheel side).

_NEEDLE = "PlantedForbiddenValue"


def _write_match_file(tmp_path: Path, *values: str) -> Path:
    match_file = tmp_path / "synthetic-match-data.txt"
    match_file.write_text("\n".join(values) + "\n")
    return match_file


# --- GATE_NOT_RUN: fails closed, never a skip -------------------------------


def test_gate_not_run_on_clean_fixture_is_exactly_one_violation(
    clean_dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    policy = load_policy(REAL_POLICY_PATH)

    violations = check_artifacts(clean_dist, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1, (
        "an unset FITDOCS_FORBIDDEN_STRINGS must be reported as a violation, "
        f"not silently skipped or passed: {violations!r}"
    )
    violation = violations[0]
    assert violation.kind == ViolationKind.GATE_NOT_RUN
    assert violation.subject == ""
    assert ENV_VAR in violation.detail


def test_gate_not_run_main_exits_1_never_0(
    clean_dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    exit_code = check_artifacts_main(
        ["--dist-dir", str(clean_dist), "--policy", str(REAL_POLICY_PATH)]
    )
    assert exit_code == 1


def test_gate_not_run_does_not_suppress_the_forbidden_member_and_link_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    wheel_path = _make_wheel(
        dist_dir,
        _CLEAN_WHEEL_MEMBERS,
        metadata=_CLEAN_METADATA,
        links={"fitdocs/extra.md": "LICENSE"},
    )
    sdist_members = dict(_CLEAN_SDIST_MEMBERS)
    sdist_members["tests/x.py"] = b""
    _make_sdist(dist_dir, sdist_members, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    kinds = {v.kind for v in violations}
    assert kinds == {
        ViolationKind.FORBIDDEN_MEMBER,
        ViolationKind.LINK_MEMBER,
        ViolationKind.GATE_NOT_RUN,
    }, "an unset gate must not suppress the other checks that already ran"
    assert any(v.subject == wheel_path.name for v in violations)


def test_gate_not_run_against_the_real_build_reuses_the_module_fixture(
    build_a: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    dist_dir = build_a[0].parent
    policy = load_policy(REAL_POLICY_PATH)

    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert violations == (
        Violation(
            subject="",
            kind=ViolationKind.GATE_NOT_RUN,
            detail=f"{ENV_VAR} is unset; the encumbered-content gate did not run",
            remedy=f"set {ENV_VAR} to the out-of-repository match-data file and re-run",
        ),
    )


# --- set but unusable: a hard error, never GATE_NOT_RUN ---------------------


def test_source_inside_the_repo_raises_forbidden_strings_source_error(
    clean_dist: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(REPO_ROOT / "tests" / "_forbidden_strings.py"))
    policy = load_policy(REAL_POLICY_PATH)

    with pytest.raises(ForbiddenStringsSourceError):
        check_artifacts(clean_dist, policy=policy, repo_root=REPO_ROOT)


def test_main_source_inside_the_repo_returns_2_with_the_cores_own_message(
    clean_dist: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(ENV_VAR, str(REPO_ROOT / "tests" / "_forbidden_strings.py"))
    exit_code = check_artifacts_main(
        ["--dist-dir", str(clean_dist), "--policy", str(REAL_POLICY_PATH)]
    )
    assert exit_code == 2
    assert "inside the repository working tree" in capsys.readouterr().err


def test_main_source_nonexistent_path_returns_2(
    clean_dist: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(ENV_VAR, "/does/not/exist/at-all.txt")
    exit_code = check_artifacts_main(
        ["--dist-dir", str(clean_dist), "--policy", str(REAL_POLICY_PATH)]
    )
    assert exit_code == 2
    assert capsys.readouterr().err  # the core's own message, not silence


# --- clean fixture with a real synthetic match file set: zero violations ---


def test_clean_fixture_with_gate_enabled_trips_no_violations(
    clean_dist: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(clean_dist, policy=policy, repo_root=REPO_ROOT)
    assert violations == ()


def test_real_build_with_gate_enabled_trips_no_violations(
    build_a: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = build_a[0].parent
    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert violations == (), (
        f"real build failed the encumbered-content gate: {violations!r}"
    )


# --- needle in a text-like member --------------------------------------


def test_needle_in_a_member_is_caught_and_does_not_echo_the_needle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = f"# {_NEEDLE} lives here\n".encode()
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name
    assert "fitdocs/x.py" in violation.detail
    assert _NEEDLE not in violation.detail


def test_needle_absent_from_a_member_trips_no_encumbered_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = b"# nothing forbidden lives here\n"
    _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert violations == ()


def test_case_variant_needle_is_still_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = f"# {_NEEDLE.lower()} lives here\n".encode()
    _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.ENCUMBERED_CONTENT


def test_wrapped_multiword_needle_across_a_line_break_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multi-word value whose words land either side of a line break is
    still a match -- the checker calls the core's `matches()` unmodified,
    which is wrap-tolerant for a multi-word value (see
    `tests/_forbidden_strings.py::matches`'s own docstring). Pins that this
    module does not substitute a flat substring test for it.
    """
    wrapped_needle = "Planted Wrapped Needle"
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, wrapped_needle)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = b"# Planted Wrapped\nNeedle here\n"
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name


def test_needle_deep_in_a_large_member_is_still_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A needle placed after 64+ KiB of clean filler is still caught --
    pins that the member's content is decoded and scanned in full, not
    truncated to some short prefix.
    """
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    filler = b"# clean filler line, nothing forbidden here\n" * 2000
    assert len(filler) >= 64 * 1024, "the filler must actually clear 64 KiB"
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = filler + f"# {_NEEDLE}\n".encode()
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name


def test_needle_beside_an_undecodable_byte_is_still_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A member whose bytes are not valid UTF-8 must still be scanned for a
    needle elsewhere in its content -- the same technique and the same
    defect class `tests/load/test_packaging.py
    ::test_decode_and_scan_flags_a_value_beside_an_undecodable_byte`
    documents: a strict decode that skips the whole member on
    `UnicodeDecodeError` would blind the scan to a genuinely present value.
    """
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    undecodable_content = b"# \xff " + f"{_NEEDLE}\n".encode()
    with pytest.raises(UnicodeDecodeError):
        undecodable_content.decode("utf-8")
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = undecodable_content
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name
    assert "fitdocs/x.py" in violation.detail


# --- needle only in the distribution metadata body ----------------------


def test_metadata_body_only_needle_is_caught_naming_metadata_in_the_wheel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    metadata_with_needle = _CLEAN_METADATA + f"\n{_NEEDLE} in the long description.\n"
    wheel_path = _make_wheel(
        dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=metadata_with_needle
    )
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name
    assert "METADATA" in violation.detail


def test_metadata_body_only_needle_is_caught_naming_pkg_info_in_the_sdist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    pkg_info_with_needle = _CLEAN_METADATA + f"\n{_NEEDLE} in the long description.\n"
    sdist_path = _make_sdist(
        dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=pkg_info_with_needle
    )

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == sdist_path.name
    assert "PKG-INFO" in violation.detail


# --- binary members: matched by NAME only, content never scanned -----------


def test_needle_in_binary_member_name_is_caught_by_name_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members[f"fitdocs/data/{_NEEDLE}.bin"] = bytes(range(256))
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name
    assert _NEEDLE in violation.detail  # the member NAME, not the needle-as-value


def test_needle_in_binary_member_content_only_is_not_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/data/asset.bin"] = _NEEDLE.encode() + bytes(range(256))
    _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert violations == (), (
        "binary member CONTENT must not be scanned -- by design, matched by name only"
    )


def test_needle_in_binary_member_directory_component_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A binary member whose NAME carries the needle only in a directory
    component -- not its basename -- is still caught: a name-only match
    must be evaluated against the member's full path, never its basename
    alone.
    """
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members[f"fitdocs/{_NEEDLE}/asset.bin"] = bytes(range(256))
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name
    assert _NEEDLE in violation.detail


# --- sdist-side twins: the same checks, exercised on the sdist -------------


def test_needle_in_an_ordinary_sdist_text_member_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    sdist_members = dict(_CLEAN_SDIST_MEMBERS)
    sdist_members["src/fitdocs/x.py"] = f"# {_NEEDLE} lives here\n".encode()
    sdist_path = _make_sdist(dist_dir, sdist_members, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == sdist_path.name
    assert "src/fitdocs/x.py" in violation.detail
    assert _NEEDLE not in violation.detail


def test_needle_in_an_sdist_binary_member_name_is_caught_by_name_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    sdist_members = dict(_CLEAN_SDIST_MEMBERS)
    sdist_members[f"src/fitdocs/assets/{_NEEDLE}.bin"] = bytes(range(256))
    sdist_path = _make_sdist(dist_dir, sdist_members, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == sdist_path.name
    assert _NEEDLE in violation.detail


# --- fingerprinted control value ------------------------------------------


def _build_control_fingerprints(sentence: str) -> tuple[frozenset[str], frozenset[int]]:
    toks = tokens(sentence)
    emitted = windows(toks, ENTROPY_FLOOR_BITS)
    assert emitted, (
        "the invented control sentence does not clear the entropy floor -- "
        "strengthen the fixture rather than weakening the assertion below"
    )
    fps = frozenset(
        digest(toks[start : start + length], REAL_SALT) for start, length in emitted
    )
    lengths = frozenset(length for _, length in emitted)
    return fps, lengths


def test_fingerprinted_control_value_is_caught_via_monkeypatched_constants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    invented_sentence = (
        "distance 741.309285 km over 4:52:31 at a rate of 0.837162945 "
        "across 209581473 intervals"
    )
    control_fps, control_lengths = _build_control_fingerprints(invented_sentence)
    monkeypatch.setattr(check_artifacts_module, "FINGERPRINTS", control_fps)
    monkeypatch.setattr(check_artifacts_module, "WINDOW_LENGTHS", control_lengths)

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = f"# {invented_sentence}\n".encode()
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == wheel_path.name
    assert "fitdocs/x.py" in violation.detail
    assert "fingerprinted value" in violation.detail


def test_fingerprinted_control_value_in_the_sdist_is_caught(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sdist-side twin of
    `test_fingerprinted_control_value_is_caught_via_monkeypatched_constants`
    -- pins that the value oracle runs over the sdist too, not only the
    wheel.
    """
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    invented_sentence = (
        "distance 741.309285 km over 4:52:31 at a rate of 0.837162945 "
        "across 209581473 intervals"
    )
    control_fps, control_lengths = _build_control_fingerprints(invented_sentence)
    monkeypatch.setattr(check_artifacts_module, "FINGERPRINTS", control_fps)
    monkeypatch.setattr(check_artifacts_module, "WINDOW_LENGTHS", control_lengths)

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    sdist_members = dict(_CLEAN_SDIST_MEMBERS)
    sdist_members["src/fitdocs/x.py"] = f"# {invented_sentence}\n".encode()
    sdist_path = _make_sdist(dist_dir, sdist_members, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 1
    violation = violations[0]
    assert violation.kind == ViolationKind.ENCUMBERED_CONTENT
    assert violation.subject == sdist_path.name
    assert "src/fitdocs/x.py" in violation.detail
    assert "fingerprinted value" in violation.detail


def test_fingerprinted_control_clean_sibling_trips_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    invented_sentence = (
        "distance 741.309285 km over 4:52:31 at a rate of 0.837162945 "
        "across 209581473 intervals"
    )
    control_fps, control_lengths = _build_control_fingerprints(invented_sentence)
    monkeypatch.setattr(check_artifacts_module, "FINGERPRINTS", control_fps)
    monkeypatch.setattr(check_artifacts_module, "WINDOW_LENGTHS", control_lengths)

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, _CLEAN_WHEEL_MEMBERS, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert violations == ()


# --- multiplicity: violations are per-occurrence, never deduplicated -------


def test_two_members_each_carrying_the_needle_is_two_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/a.py"] = f"# {_NEEDLE}\n".encode()
    members["fitdocs/b.py"] = f"# {_NEEDLE}\n".encode()
    _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 2
    assert {v.kind for v in violations} == {ViolationKind.ENCUMBERED_CONTENT}
    members_named = {v.detail for v in violations}
    assert len(members_named) == 2, "both members must be individually named"


def test_one_member_with_both_token_and_fingerprint_hit_is_two_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    invented_sentence = (
        "distance 741.309285 km over 4:52:31 at a rate of 0.837162945 "
        "across 209581473 intervals"
    )
    control_fps, control_lengths = _build_control_fingerprints(invented_sentence)
    monkeypatch.setattr(check_artifacts_module, "FINGERPRINTS", control_fps)
    monkeypatch.setattr(check_artifacts_module, "WINDOW_LENGTHS", control_lengths)

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/x.py"] = f"# {_NEEDLE} -- {invented_sentence}\n".encode()
    wheel_path = _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert len(violations) == 2
    assert all(v.subject == wheel_path.name for v in violations)
    assert all(v.kind == ViolationKind.ENCUMBERED_CONTENT for v in violations)
    details = {v.detail for v in violations}
    assert len(details) == 2, "the two hits must be distinguishable by detail"
    assert any("token" in d for d in details)
    assert any("fingerprinted value" in d for d in details)


# --- determinism -------------------------------------------------------


def test_encumbered_content_check_is_deterministic_across_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VAR, str(_write_match_file(tmp_path, _NEEDLE)))
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    members = dict(_CLEAN_WHEEL_MEMBERS)
    members["fitdocs/a.py"] = f"# {_NEEDLE}\n".encode()
    members["fitdocs/b.py"] = f"# {_NEEDLE}\n".encode()
    _make_wheel(dist_dir, members, metadata=_CLEAN_METADATA)
    _make_sdist(dist_dir, _CLEAN_SDIST_MEMBERS, pkg_info=_CLEAN_METADATA)

    policy = load_policy(REAL_POLICY_PATH)
    first = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    second = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)

    assert first == second


# --- import audit: exactly two non-stdlib import groups --------------------


def test_check_artifacts_import_audit_is_exactly_scripts_and_tests() -> None:
    source = (REPO_ROOT / "scripts" / "check_artifacts.py").read_text()
    tree = ast.parse(source)
    roots: set[str] = set()
    tests_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            roots.add(root)
            if root == "tests":
                tests_modules.add(node.module)

    non_stdlib_roots = roots - set(sys.stdlib_module_names)
    assert non_stdlib_roots, "the import scan found no non-stdlib imports"
    assert non_stdlib_roots == {"scripts", "tests"}
    assert tests_modules == {
        "tests._forbidden_strings",
        "tests._content_oracle",
        "tests._content_fingerprints",
    }


def test_forbidden_strings_and_content_oracle_modules_import_nothing_from_fitdocs() -> (
    None
):
    for relative in (
        "tests/_forbidden_strings.py",
        "tests/_content_oracle.py",
        "tests/_content_fingerprints.py",
    ):
        source = (REPO_ROOT / relative).read_text()
        tree = ast.parse(source)
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module.split(".")[0])
        assert "fitdocs" not in imported_names, f"{relative} must not import fitdocs"


# ---------------------------------------------------------------------------
# Task 2.4: check_version_consistency (the version-consistency gate)
# ---------------------------------------------------------------------------
#
# THE RULE IS PURE PAIRWISE (round-1 review correction): each of the three
# possible comparisons -- manifest-vs-changelog, manifest-vs-tag,
# changelog-vs-tag -- runs and is reported INDEPENDENTLY, with NO
# deduplication when two of the three sources happen to already agree with
# each other. `manifest == changelog != tag` and `manifest == tag !=
# changelog` both produce 2 violations (the odd one out disagrees with BOTH
# of the other two, and BOTH disagreements are reported); all three distinct
# produces 3; no tag produces at most 1. A changelog with no released entry
# is its own violation, reported ADDITIONALLY to a manifest-vs-tag
# comparison when a tag is supplied (changelog-vs-tag is the only
# comparison skipped there, since there is no changelog value at all).
#
# Discrimination sweep for the version-consistency gate's every relaxation
# class, per `.kiro/steering/change-protocol.md` -- {absent, wrong text,
# case, whitespace, partial match, type, scope/off-by-one}:
#
# | class      | test                                                              |
# |-------------|--------------------------------------------------------------------|
# | absent      | test_no_released_entry_with_agreeing_tag_is_exactly_one_violation  |
# |             | (no entry at all); test_agreement_with_no_tag_supplied_returns_no_ |
# |             | violations (a tag that is absent is tolerated, not a mismatch);    |
# |             | test_empty_string_tag_is_treated_as_no_tag_supplied                |
# | wrong text  | test_all_three_distinct_produces_three_violations                 |
# | case        | test_tag_capital_v_is_not_normalized_and_is_a_mismatch             |
# | whitespace  | test_tag_whitespace_padded_is_stripped_before_comparison           |
# | partial     | test_manifest_version_prefix_of_changelog_is_still_a_mismatch;     |
# | match       | test_agreeing_manifest_and_changelog_prefix_extension_tag_is_two_  |
# |             | violations; test_tag_with_prerelease_suffix_is_a_mismatch;         |
# |             | test_tag_with_refs_prefix_is_a_mismatch_not_normalized (a wrong-   |
# |             | text case in disguise -- see the comment above the real partial-   |
# |             | match tests); test_version_looking_prose_in_unreleased_is_not_an_  |
# |             | entry                                                              |
# | type/regex  | test_malformed_date_heading_is_not_an_entry;                       |
# | anchoring   | test_v_prefixed_heading_is_not_an_entry;                           |
# |             | test_heading_with_trailing_text_after_the_date_is_not_an_entry     |
# | scope/      | test_newest_entry_is_first_listed_not_highest_or_last (first       |
# | off-by-one  | heading wins, not sorted-highest, not last-in-document)            |


def _write_manifest(dir_: Path, version: str, *, name: str = "manifest.toml") -> Path:
    path = dir_ / name
    path.write_text(f'[project]\nname = "fitdocs"\nversion = "{version}"\n')
    return path


def _write_changelog(
    dir_: Path, *release_headings: str, name: str = "CHANGELOG.md"
) -> Path:
    """A changelog with a standing `## [Unreleased]` section followed by
    `release_headings` in the given order (document order -- callers control
    which heading is "first", i.e. "newest" by this gate's rule).
    """
    lines = ["# Changelog", "", "## [Unreleased]", ""]
    for heading in release_headings:
        lines.append(heading)
        lines.append("")
        lines.append("### Added")
        lines.append("")
        lines.append("- x")
        lines.append("")
    path = dir_ / name
    path.write_text("\n".join(lines))
    return path


# --- agreement: no violations -----------------------------------------------


@pytest.mark.parametrize("tag", ["v9.9.9", "9.9.9"])
def test_agreement_all_three_sources_returns_no_violations(
    tmp_path: Path, tag: str
) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    # newest entry (9.9.9) listed above an older one (9.9.8) -- the older
    # entry is present so this fixture cannot be satisfied by a "there is
    # only one entry" coincidence.
    changelog = _write_changelog(
        tmp_path,
        "## [9.9.9] - 2026-01-02",
        "## [9.9.8] - 2026-01-01",
    )
    assert check_version_consistency(manifest, changelog, tag) == ()


def test_agreement_with_no_tag_supplied_returns_no_violations(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    assert check_version_consistency(manifest, changelog, None) == ()


# --- the four disagreement shapes -------------------------------------------


def test_all_three_distinct_produces_three_violations(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.8] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, "9.9.7")

    assert len(violations) == 3
    assert all(v.kind == ViolationKind.VERSION_MISMATCH for v in violations)
    assert all(v.subject == "" for v in violations)
    details = [v.detail for v in violations]
    assert any("9.9.9" in d and "9.9.8" in d for d in details)
    assert any("9.9.9" in d and "9.9.7" in d for d in details)
    assert any("9.9.8" in d and "9.9.7" in d for d in details)
    # Exact detail order, pinned: lexicographic sort of the detail strings
    # puts "changelog..." before "manifest version...", and between the two
    # manifest-prefixed details, "...changelog newest entry..." sorts
    # before "...tag..." ('c' < 't'). A missing-sort or wrong-sort-key
    # mutation would emit these in construction order instead
    # (manifest-vs-changelog, manifest-vs-tag, changelog-vs-tag).
    assert details == [
        "changelog newest entry 9.9.8 != tag 9.9.7",
        "manifest version 9.9.9 != changelog newest entry 9.9.8",
        "manifest version 9.9.9 != tag 9.9.7",
    ]


def test_manifest_agrees_with_tag_changelog_differs_produces_two_violations(
    tmp_path: Path,
) -> None:
    # PURE PAIRWISE: manifest==tag, changelog is the odd one out. Both the
    # manifest-vs-changelog pair AND the changelog-vs-tag pair disagree, so
    # BOTH are reported -- no deduplication just because manifest and tag
    # happen to already agree with each other.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.8] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, "9.9.9")

    assert len(violations) == 2
    details = [v.detail for v in violations]
    assert any("9.9.9" in d and "9.9.8" in d and "manifest" in d for d in details)
    assert any("9.9.9" in d and "9.9.8" in d and "changelog" in d for d in details)


def test_manifest_agrees_with_changelog_tag_differs_produces_two_violations(
    tmp_path: Path,
) -> None:
    # PURE PAIRWISE, mirror image of the case above: manifest==changelog,
    # tag is the odd one out. Both the manifest-vs-tag pair AND the
    # changelog-vs-tag pair disagree, so BOTH are reported -- manifest and
    # changelog already agreeing with each other does NOT collapse the two
    # tag-mismatch findings into one.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, "9.9.8")

    assert len(violations) == 2
    details = [v.detail for v in violations]
    assert any("9.9.9" in d and "9.9.8" in d and "manifest" in d for d in details)
    assert any("9.9.9" in d and "9.9.8" in d and "changelog" in d for d in details)


def test_tag_none_manifest_and_changelog_differ_produces_one_violation(
    tmp_path: Path,
) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.8] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, None)

    assert len(violations) == 1
    assert violations[0].subject == ""
    assert "9.9.9" in violations[0].detail
    assert "9.9.8" in violations[0].detail
    assert violations[0].remedy.strip()


# --- no released entry -------------------------------------------------


def test_no_released_entry_with_agreeing_tag_is_exactly_one_violation(
    tmp_path: Path,
) -> None:
    # No-entry is reported ADDITIONALLY to, never instead of, a
    # manifest-vs-tag comparison -- but here the tag AGREES with the
    # manifest, so there is nothing for the manifest-vs-tag comparison to
    # report: exactly the no-entry finding, alone.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path)  # Unreleased only, like the real file
    violations = check_version_consistency(manifest, changelog, "9.9.9")

    assert len(violations) == 1
    assert violations[0].subject == ""
    assert violations[0].kind == ViolationKind.VERSION_MISMATCH
    assert "9.9.9" in violations[0].detail
    assert "no released entry" in violations[0].detail


def test_no_released_entry_with_disagreeing_tag_is_exactly_two_violations(
    tmp_path: Path,
) -> None:
    # No-entry is reported ADDITIONALLY to a manifest-vs-tag comparison when
    # the supplied tag actually disagrees with the manifest: the no-entry
    # finding AND the manifest-vs-tag finding, both present -- changelog-vs-
    # tag is the only comparison skipped, since there is no changelog value
    # to compare against.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path)  # Unreleased only, like the real file
    violations = check_version_consistency(manifest, changelog, "9.9.8")

    assert len(violations) == 2
    no_entry = [v for v in violations if "no released entry" in v.detail]
    manifest_vs_tag = [v for v in violations if "no released entry" not in v.detail]
    assert len(no_entry) == 1
    assert "9.9.9" in no_entry[0].detail
    assert len(manifest_vs_tag) == 1
    assert "9.9.9" in manifest_vs_tag[0].detail
    assert "9.9.8" in manifest_vs_tag[0].detail
    assert "manifest" in manifest_vs_tag[0].detail
    assert "changelog" not in manifest_vs_tag[0].detail


def test_real_repository_state_pins_the_no_entry_violation() -> None:
    """Pins Requirement 4.7 against the REAL `pyproject.toml` and
    `CHANGELOG.md`: nothing has been released yet (task 1.3's state), so
    this must yield exactly the no-entry violation today. Update this test
    the day the first `## [X.Y.Z] - YYYY-MM-DD` entry is written --
    `tests/test_changelog.py::test_real_changelog_has_no_released_version_literal`
    pins the same real-file fact from the changelog side and will need the
    same update.
    """
    real_manifest = REPO_ROOT / "pyproject.toml"
    real_changelog = REPO_ROOT / "CHANGELOG.md"
    with real_manifest.open("rb") as handle:
        real_version = tomllib.load(handle)["project"]["version"]

    violations = check_version_consistency(real_manifest, real_changelog, None)

    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.VERSION_MISMATCH
    assert real_version in violations[0].detail
    assert "no released entry" in violations[0].detail


# --- newest-entry selection: first-listed, not highest, not last -----------


def test_newest_entry_is_first_listed_not_highest_or_last(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.8")
    # Out-of-order: the SMALLER version is listed first. "Newest" means
    # "first heading in document order" for this gate, not "highest
    # version" and not "last heading" -- the manifest agrees with the FIRST
    # entry (9.9.8) but not the highest (9.9.9) and not the last (9.9.7).
    changelog = _write_changelog(
        tmp_path,
        "## [9.9.8] - 2026-01-01",
        "## [9.9.9] - 2026-01-02",
        "## [9.9.7] - 2025-12-31",
    )
    assert check_version_consistency(manifest, changelog, None) == ()


# --- heading and prose that must NOT be treated as a released entry --------


def test_version_looking_prose_in_unreleased_is_not_an_entry(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n"
        "- mentions version 9.9.9 in prose, not a heading\n"
    )
    # Falsity-before: a real entry for 9.9.9 WOULD agree.
    real_entry_changelog = _write_changelog(
        tmp_path, "## [9.9.9] - 2026-01-01", name="real-entry.md"
    )
    assert check_version_consistency(manifest, real_entry_changelog, None) == ()

    violations = check_version_consistency(manifest, changelog_path, None)
    assert len(violations) == 1
    assert "no released entry" in violations[0].detail


def test_unanchored_heading_shaped_text_mid_line_is_not_an_entry(
    tmp_path: Path,
) -> None:
    """Pins the regex's leading `^` anchor: a line whose release-heading
    shape does not start the line (a bullet referencing it, `- see ## [...]
    - ...`) must NOT be treated as a released entry. `re.match` (used in
    production) is anchored at position 0 by construction; a change to
    `re.search` (which finds a match anywhere in the line) would wrongly
    treat this as an entry.
    """
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- see ## [9.9.9] - 2026-01-01\n"
    )
    violations = check_version_consistency(manifest, changelog_path, None)
    assert len(violations) == 1
    assert "no released entry" in violations[0].detail


def test_malformed_date_heading_is_not_an_entry(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-1-1")
    violations = check_version_consistency(manifest, changelog, None)
    assert len(violations) == 1
    assert "no released entry" in violations[0].detail


def test_v_prefixed_heading_is_not_an_entry(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [v9.9.9] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, None)
    assert len(violations) == 1
    assert "no released entry" in violations[0].detail


def test_heading_with_trailing_text_after_the_date_is_not_an_entry(
    tmp_path: Path,
) -> None:
    # Pins the regex's trailing `$` anchor: a well-formed `X.Y.Z` version and
    # date followed by extra text must NOT be treated as a released entry.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01 draft")
    violations = check_version_consistency(manifest, changelog, None)
    assert len(violations) == 1
    assert "no released entry" in violations[0].detail


# --- tag normalization -------------------------------------------------


def test_tag_capital_v_is_not_normalized_and_is_a_mismatch(tmp_path: Path) -> None:
    # manifest == changelog, so under pure pairwise BOTH the manifest-vs-tag
    # AND changelog-vs-tag comparisons fire (2 violations), not 1 -- 'V' is
    # not stripped, so the un-normalized "V9.9.9" is what both must name.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, "V9.9.9")
    assert len(violations) == 2
    assert all("V9.9.9" in v.detail for v in violations)
    assert any("manifest" in v.detail for v in violations)
    assert any("changelog" in v.detail for v in violations)


def test_tag_with_refs_prefix_is_a_mismatch_not_normalized(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, "refs/tags/v9.9.9")
    assert len(violations) == 2
    assert all("refs/tags/v9.9.9" in v.detail for v in violations)
    assert any("manifest" in v.detail for v in violations)
    assert any("changelog" in v.detail for v in violations)


def test_tag_whitespace_padded_is_stripped_before_comparison(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    assert check_version_consistency(manifest, changelog, " 9.9.9") == ()
    assert check_version_consistency(manifest, changelog, " v9.9.9 ") == ()
    # A trailing newline (e.g. from a shell command substitution the caller
    # forgot to strip) must be stripped exactly like leading/trailing
    # spaces -- `str.strip()` handles all whitespace, not only spaces.
    assert check_version_consistency(manifest, changelog, "v9.9.9\n") == ()


def test_empty_string_tag_is_treated_as_no_tag_supplied(tmp_path: Path) -> None:
    # `--tag ""` (e.g. a CI step whose tag-detection produced nothing) must
    # behave exactly like omitting `--tag` entirely -- never as a tag that
    # mismatches every real version.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.8] - 2026-01-01")
    with_empty_tag = check_version_consistency(manifest, changelog, "")
    with_no_tag = check_version_consistency(manifest, changelog, None)
    assert with_empty_tag == with_no_tag
    assert len(with_empty_tag) == 1  # only the manifest-vs-changelog mismatch


# --- partial match: substring/prefix relationships are NOT equality --------


def test_manifest_version_prefix_of_changelog_is_still_a_mismatch(
    tmp_path: Path,
) -> None:
    # "9.9.90" is a superstring of "9.9.9" -- `"9.9.90".startswith("9.9.9")`
    # is True, so a comparison weakened from equality to `startswith` would
    # wrongly treat these as matching. No tag supplied, so this isolates the
    # manifest-vs-changelog comparison alone.
    manifest = _write_manifest(tmp_path, "9.9.90")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, None)
    assert len(violations) == 1
    assert "9.9.90" in violations[0].detail
    assert "9.9.9 " in violations[0].detail or violations[0].detail.endswith("9.9.9")


def test_agreeing_manifest_and_changelog_prefix_extension_tag_is_two_violations(
    tmp_path: Path,
) -> None:
    # manifest == changelog == "9.9.9"; tag "9.9.90" is a superstring of
    # both. Isolates the tag comparisons (manifest-vs-tag AND
    # changelog-vs-tag): a `startswith`-weakened comparison would wrongly
    # report zero violations here since "9.9.90".startswith("9.9.9") is True.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, "9.9.90")
    assert len(violations) == 2
    details = [v.detail for v in violations]
    assert any("manifest" in d and "9.9.90" in d for d in details)
    assert any("changelog" in d and "9.9.90" in d for d in details)


def test_tag_with_prerelease_suffix_is_a_mismatch(tmp_path: Path) -> None:
    # manifest == changelog == "9.9.9"; tag "9.9.9-rc1" has "9.9.9" as a
    # genuine prefix (`"9.9.9-rc1".startswith("9.9.9")` is True) -- a real
    # pre-release tag must still mismatch a release version, not be treated
    # as equal because one is a prefix of the other.
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    violations = check_version_consistency(manifest, changelog, "9.9.9-rc1")
    assert len(violations) == 2
    details = [v.detail for v in violations]
    assert any("manifest" in d and "9.9.9-rc1" in d for d in details)
    assert any("changelog" in d and "9.9.9-rc1" in d for d in details)


# --- hard errors ---------------------------------------------------------


def test_missing_manifest_raises_checker_error(tmp_path: Path) -> None:
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    with pytest.raises(CheckerError):
        check_version_consistency(tmp_path / "does-not-exist.toml", changelog, None)


def test_manifest_without_project_version_raises_checker_error(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text('[project]\nname = "fitdocs"\n')
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    with pytest.raises(CheckerError):
        check_version_consistency(manifest, changelog, None)


def test_manifest_malformed_toml_raises_checker_error(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text("[project\nversion = ")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    with pytest.raises(CheckerError):
        check_version_consistency(manifest, changelog, None)


def test_missing_changelog_raises_checker_error(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    with pytest.raises(CheckerError):
        check_version_consistency(manifest, tmp_path / "does-not-exist.md", None)


def test_manifest_version_not_a_string_raises_checker_error(tmp_path: Path) -> None:
    # `version = 1` (an int, not a string) -- TOML happily parses this, so
    # the reader must reject it explicitly rather than let a later
    # `str`-only operation (e.g. `.strip()`) raise something other than
    # `CheckerError`.
    manifest = tmp_path / "manifest.toml"
    manifest.write_text('[project]\nname = "fitdocs"\nversion = 1\n')
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    with pytest.raises(CheckerError):
        check_version_consistency(manifest, changelog, None)


def test_manifest_version_empty_string_raises_checker_error(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.toml"
    manifest.write_text('[project]\nname = "fitdocs"\nversion = ""\n')
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    with pytest.raises(CheckerError):
        check_version_consistency(manifest, changelog, None)


# --- ordering and determinism -------------------------------------------


def test_main_reports_version_violations_before_artifact_violations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Integration-level pin of the design's ordering, exercised through
    `main` with a fixture that trips BOTH a version violation (subject "")
    AND an artifact violation (a non-empty subject): the version line must
    come first in the printed listing. This is a genuine end-to-end
    observable of the combined `violations` list `main` builds -- unlike a
    standalone `sorted()` call over a hand-picked artifact subject, which
    would be pre-satisfied no matter what production code does (an empty
    string sorts before ANY non-empty string in Python, so that shape of
    test cannot fail).
    """
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.8] - 2026-01-01")
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, {}, metadata="Name: x\n\nbody\n")
    _make_sdist(dist_dir, {}, pkg_info="Name: x\n\nbody\n")

    exit_code = check_artifacts_main(
        [
            "--manifest",
            str(manifest),
            "--changelog",
            str(changelog),
            "--policy",
            str(REAL_POLICY_PATH),
            "--dist-dir",
            str(dist_dir),
        ]
    )

    assert exit_code == 1
    lines = capsys.readouterr().err.splitlines()
    kind_lines = [line for line in lines if "\t" in line]
    assert kind_lines, "no violation lines printed -- fixture produced nothing"
    assert kind_lines[0].startswith("version_mismatch\t")
    assert any(not line.startswith("version_mismatch\t") for line in kind_lines)


def test_check_version_consistency_is_deterministic_across_runs(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.8] - 2026-01-01")
    first = check_version_consistency(manifest, changelog, "9.9.7")
    second = check_version_consistency(manifest, changelog, "9.9.7")
    assert first == second


# ---------------------------------------------------------------------------
# Task 2.4: wiring into main() -- --tag / --manifest / --changelog /
# --no-artifacts
# ---------------------------------------------------------------------------


def test_main_no_artifacts_agreeing_files_returns_0_and_never_opens_dist_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")

    def _must_not_be_called(dist_dir: Path) -> tuple[Path, Path]:
        raise AssertionError("--no-artifacts must never open the dist directory")

    monkeypatch.setattr(check_artifacts_module, "_find_artifacts", _must_not_be_called)

    exit_code = check_artifacts_main(
        [
            "--no-artifacts",
            "--manifest",
            str(manifest),
            "--changelog",
            str(changelog),
            "--tag",
            "v9.9.9",
            "--dist-dir",
            str(tmp_path / "does-not-exist-at-all"),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip()


def test_main_no_artifacts_disagreeing_files_returns_1_with_both_values_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write_manifest(tmp_path, "9.9.9")
    changelog = _write_changelog(tmp_path, "## [9.9.8] - 2026-01-01")

    exit_code = check_artifacts_main(
        [
            "--no-artifacts",
            "--manifest",
            str(manifest),
            "--changelog",
            str(changelog),
            "--dist-dir",
            str(tmp_path / "does-not-exist-at-all"),
        ]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.startswith("version_mismatch")]
    assert len(lines) == 1
    assert "9.9.9" in lines[0]
    assert "9.9.8" in lines[0]


def test_main_hard_error_from_version_check_returns_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing_manifest = tmp_path / "does-not-exist.toml"
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")

    exit_code = check_artifacts_main(
        [
            "--no-artifacts",
            "--manifest",
            str(missing_manifest),
            "--changelog",
            str(changelog),
        ]
    )

    assert exit_code == 2
    assert str(missing_manifest) in capsys.readouterr().err


def test_main_version_check_error_reported_before_a_missing_dist_dir_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both a hard version-check error (missing manifest) AND a hard
    artifact error (nonexistent dist dir) are possible in the same call --
    with the version check running FIRST (design: cheapest failure first),
    its own error message is what gets reported, never the dist-directory
    one. A production reordering that ran the artifact check first would
    report the dist-directory message instead, which this pins by asserting
    the ABSENCE of that message alongside the presence of the manifest one.
    """
    missing_manifest = tmp_path / "does-not-exist.toml"
    changelog = _write_changelog(tmp_path, "## [9.9.9] - 2026-01-01")
    missing_dist_dir = tmp_path / "does-not-exist-at-all"

    exit_code = check_artifacts_main(
        [
            "--manifest",
            str(missing_manifest),
            "--changelog",
            str(changelog),
            "--policy",
            str(REAL_POLICY_PATH),
            "--dist-dir",
            str(missing_dist_dir),
        ]
    )

    assert exit_code == 2
    err = capsys.readouterr().err
    assert str(missing_manifest) in err
    assert str(missing_dist_dir) not in err


# ---------------------------------------------------------------------------
# Task 2.4 remediation (round 1): --no-version-check
# ---------------------------------------------------------------------------
#
# CI (task 6.2) runs the artifact checks on every commit, but there is no
# released changelog entry until the first release -- so `main`'s DEFAULT
# behavior (both gates) would exit 1 on every pre-release commit if CI ran
# it unmodified. `--no-version-check` lets CI run the artifact checks alone;
# `--no-artifacts` (already covered above) lets the release workflow run
# the version gate alone before a dist directory exists; the default runs
# both. The two flags are mutually exclusive: together they would run
# nothing at all, so `main` treats that combination as a usage error via
# `argparse`'s own `parser.error` (exit 2, same mechanism `--help` uses).


def test_main_no_version_check_with_real_manifest_changelog_and_clean_dist_returns_0(
    clean_dist: Path,
) -> None:
    """`--no-version-check` against the REAL manifest/changelog (no
    released entry -- see `test_main_with_real_manifest_and_changelog_
    reports_only_the_no_entry_violation` for the same files WITHOUT this
    flag, which is exit 1) must skip the version gate entirely and pass on
    an otherwise-clean artifact set: exit 0. This also pins the
    "flag ignored" mutation -- an implementation that parses but never
    consults `--no-version-check` would run the version check anyway
    against these real, disagreeing files and exit 1 instead.
    """
    exit_code = check_artifacts_main(
        [
            "--no-version-check",
            "--dist-dir",
            str(clean_dist),
            "--policy",
            str(REAL_POLICY_PATH),
        ]
    )
    assert exit_code == 0


def test_main_no_version_check_and_no_artifacts_together_is_an_argparse_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        check_artifacts_main(["--no-version-check", "--no-artifacts"])
    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "mutually exclusive" in err


def test_main_default_mode_runs_both_the_version_and_artifact_checks(
    clean_dist: Path, agreeing_manifest_and_changelog: tuple[Path, Path]
) -> None:
    """Falsity-before / independence check for `--no-version-check`: with
    NEITHER flag supplied, `main` must still run BOTH checks -- proven by
    showing the version check's own violation (a real disagreement) reaches
    the exit code even though the artifact set is clean, which distinguishes
    "default runs both" from "default silently runs artifacts only".
    """
    manifest_path, _ = agreeing_manifest_and_changelog
    disagreeing_changelog = _write_changelog(
        manifest_path.parent, "## [9.9.8] - 2026-01-01", name="disagreeing-CHANGELOG.md"
    )

    exit_code = check_artifacts_main(
        [
            "--dist-dir",
            str(clean_dist),
            "--policy",
            str(REAL_POLICY_PATH),
            "--manifest",
            str(manifest_path),
            "--changelog",
            str(disagreeing_changelog),
        ]
    )
    assert exit_code == 1


# ---------------------------------------------------------------------------
# Task 3.2: the release-path checkpoint (ReleaseArtifactTest)
# ---------------------------------------------------------------------------
#
# The migration's stage-3 validation checkpoint, proved against the REAL
# built artifacts rather than a synthetic fixture: the real gate passes with
# real match data supplied through the SAME mechanism the purge's own guards
# use (`tests._forbidden_strings.require`); the same real artifacts fail
# closed with the gate unset; the real sdist's member set equals the task
# 1.2 allowlist exactly (both directions); and a clean, isolated install of
# the built wheel completes a full ingestion, with the `threshold` built-in
# computing load (Req 1.10, 6.2, 6.3, 6.9, 6.10).
#
# The planted-link non-vacuity proof is task 1.2's own
# (`tests/test_packaging.py::
# test_sdist_allowlist_excludes_forbidden_paths_and_the_agent_log_symlink`)
# and is not repeated here; this section proves the REAL build's member set
# against the REAL allowlist instead.


# --- 1: real gate pass with match data supplied via `require` --------------


def test_checkpoint_real_gate_pass_with_match_data_via_require(
    build_a: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real artifact set, gated with match data supplied through
    `tests._forbidden_strings.require` -- the exact call the purge's own
    guards make -- passes cleanly, both through `check_artifacts` directly
    and through `main` (`--no-version-check`: the real changelog carries no
    released entry yet; 2.4's own tests pin that state, not repeated here).

    `require(REPO_ROOT)` is called against the environment's REAL state
    (`_REAL_ENV_FORBIDDEN_STRINGS`, captured at module import -- before this
    module's autouse `_default_forbidden_strings_env` fixture ever touches
    `os.environ`), overriding that autouse default the same way the module's
    other unset/broken-source tests already do. So in a shell without
    `FITDOCS_FORBIDDEN_STRINGS` set, THIS test skips distinguishably (a real
    `pytest.skip`, never a silent pass) -- see
    `test_checkpoint_requires_own_skip_names_the_env_var` below for the
    proof that the skip is the core's own -- while `check_artifacts`/`main`
    exercised here would have failed closed instead (see
    `test_checkpoint_fail_closed_against_real_artifacts_gate_not_run`).
    """
    if _REAL_ENV_FORBIDDEN_STRINGS is None:
        monkeypatch.delenv(ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(ENV_VAR, _REAL_ENV_FORBIDDEN_STRINGS)

    forbidden = require(REPO_ROOT)
    assert forbidden.values, "require() returned match data with no values"

    dist_dir = build_a[0].parent
    policy = load_policy(REAL_POLICY_PATH)

    violations_1 = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert violations_1 == (), f"real build failed the real gate: {violations_1!r}"

    exit_code = check_artifacts_main(
        [
            "--no-version-check",
            "--dist-dir",
            str(dist_dir),
            "--policy",
            str(REAL_POLICY_PATH),
        ]
    )
    assert exit_code == 0

    # --- 6: determinism over the real artifacts, real match data ----------
    violations_2 = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert violations_2 == violations_1


def test_checkpoint_requires_own_skip_names_the_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins that `require(REPO_ROOT)` -- the exact call the checkpoint test
    above makes -- is what produces "skip distinguishably": with the
    variable genuinely unset, `require` raises pytest's own skip exception
    naming `FITDOCS_FORBIDDEN_STRINGS` in the reason, never a bare `None`
    return and never a plain exception a caller could swallow silently.
    """
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(pytest.skip.Exception) as exc_info:
        require(REPO_ROOT)
    assert ENV_VAR in str(exc_info.value), (
        f"the skip reason does not name {ENV_VAR!r}: {exc_info.value!r}"
    )


# --- 2: fail-closed against the REAL artifacts, gate genuinely unset -------


def test_checkpoint_fail_closed_against_real_artifacts_gate_not_run(
    build_a: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real built artifacts, checked with `FITDOCS_FORBIDDEN_STRINGS`
    truly unset, report exactly one GATE_NOT_RUN violation and `main` exits
    1 -- never a skip, never a pass. Deliberately calls `check_artifacts`/
    `main` directly, never `require` -- this test itself must not skip, so
    the unset case is observed as a violation, not dodged.
    """
    monkeypatch.delenv(ENV_VAR, raising=False)
    dist_dir = build_a[0].parent
    policy = load_policy(REAL_POLICY_PATH)

    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert violations != (), "an unset gate against the real build must be a violation"
    assert len(violations) == 1
    assert violations[0].kind == ViolationKind.GATE_NOT_RUN

    exit_code = check_artifacts_main(
        [
            "--no-version-check",
            "--dist-dir",
            str(dist_dir),
            "--policy",
            str(REAL_POLICY_PATH),
        ]
    )
    assert exit_code == 1


# --- 3: the real sdist's member set equals the allowlist, exactly ----------


def _tracked_or_untracked_not_ignored(*relative_paths: str) -> tuple[str, ...]:
    """`git ls-files -co --exclude-standard <relative_paths>` from
    REPO_ROOT: every tracked file plus every untracked-but-not-gitignored
    file under the given paths -- what hatchling's default sdist directory
    scan actually ships for a directory named in `only-include` (hatchling
    honors `.gitignore` the same way `git ls-files` does for the "untracked"
    half). The plain tracked-only form (`git ls-files` with no `-co`) is NOT
    equivalent in general -- it would silently miss an untracked-and-not-
    ignored file hatchling would still ship -- even though, verified
    empirically against this tree, the two forms currently agree (both list
    the same 116 paths under `src/fitdocs`).
    """
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", *relative_paths],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line)


def _expected_sdist_member_set() -> frozenset[str]:
    """The sdist member set `[tool.hatch.build.targets.sdist].only-include`
    implies: every entry listed directly, every file under an entry that is
    a directory (`src/fitdocs`), plus the two members hatchling ALWAYS adds
    regardless of `only-include` (`PKG-INFO`, `.gitignore`; task 1.2's
    Implementation Note)."""
    manifest = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    only_include = manifest["tool"]["hatch"]["build"]["targets"]["sdist"][
        "only-include"
    ]

    expected: set[str] = set()
    for entry in only_include:
        path = REPO_ROOT / entry
        if path.is_dir():
            expected.update(_tracked_or_untracked_not_ignored(entry))
        else:
            expected.add(entry)

    expected.add("PKG-INFO")
    expected.add(".gitignore")
    return frozenset(expected)


def test_checkpoint_sdist_member_set_equals_the_allowlist_exactly(
    build_a: tuple[Path, ...],
) -> None:
    """The REAL sdist's member set -- regular files only, prefix-stripped --
    equals, in both directions, the allowlist `_expected_sdist_member_set`
    derives from the manifest plus hatchling's two always-added extras. No
    directory entry counted on either side; no link member at all; and
    specifically none of `agent-log`, `tests/`, `.kiro/`, `scripts/`,
    `release/`, `docs/`, `uv.lock` (Req 1.6, 1.10, 6.10).
    """
    expected = _expected_sdist_member_set()
    assert expected, "the expected set is empty -- the allowlist derivation is broken"
    assert "src/fitdocs/__init__.py" in expected
    assert "LICENSE" in expected
    assert "CHANGELOG.md" in expected

    sdist_path = _artifact(build_a, ".tar.gz")
    with tarfile.open(sdist_path) as archive:
        members = archive.getmembers()
        assert members, "the real sdist has no members -- wrong archive opened"
        prefix = members[0].name.split("/", 1)[0]
        regular = [m for m in members if m.isfile()]
        actual = frozenset(m.name[len(prefix) + 1 :] for m in regular)
        link_names = [m.name for m in members if m.issym() or m.islnk()]

    assert not link_names, f"the real sdist ships a link member: {link_names!r}"

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    assert not missing and not unexpected, (
        f"real sdist member set differs from the allowlist: "
        f"missing={missing!r} unexpected={unexpected!r}"
    )

    forbidden_prefixes = ("tests/", ".kiro/", "scripts/", "release/", "docs/")
    forbidden_hits = [
        n
        for n in actual
        if n.startswith(forbidden_prefixes) or n in ("uv.lock", "agent-log")
    ]
    assert not forbidden_hits, (
        f"forbidden path(s) in the real sdist: {forbidden_hits!r}"
    )


# --- 4: clean isolated install + full ingestion (the E2E) ------------------


def _project_manifest_version() -> str:
    manifest = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = manifest["project"]["version"]
    assert isinstance(version, str) and version
    return version


def _install_offline_from_wheel(
    uv: str, env: dict[str, str], wheel_path: Path
) -> subprocess.CompletedProcess[str]:
    """Install `fitdocs` offline FROM THE BUILT WHEEL FILE (not the
    checkout) into the isolated tool dirs `env` names -- the cold-cache
    warm-then-retry technique `tests/test_packaging.py::_install_offline`
    uses, adapted to a `--from <wheel path>` spec. The returned result is
    always the OFFLINE install."""
    from_spec = str(wheel_path)
    offline = _run(
        [uv, "tool", "install", "--offline", "--from", from_spec, "fitdocs"], env
    )
    if offline.returncode == 0:
        return offline
    warm = _run([uv, "tool", "install", "--from", from_spec, "fitdocs"], env)
    assert warm.returncode == 0, (
        "could not install the built wheel offline (cold cache) and warming "
        f"the uv cache online also failed:\n{warm.stdout}\n{warm.stderr}"
    )
    _run([uv, "tool", "uninstall", "fitdocs"], env)
    return _run(
        [uv, "tool", "install", "--offline", "--from", from_spec, "fitdocs"], env
    )


_CHECKPOINT_RECORD_COUNT = 90
"""Comfortably above the threshold built-in's default 60s minimum duration
(`fitdocs.load.channels.types.DEFAULT_MIN_DURATION_S`) at 1 record/second --
`tests/fixtures/builder.ride_fit_bytes`/`hike_fit_bytes` are far too short
(a handful of records) and land in `NotComputed`, not `Computed`."""
_CHECKPOINT_SPEED_MPS = 3.0


def _checkpoint_fit_bytes(
    serial: int, fit_sport: str, *, power_w: int | None = None, hr_base: int = 140
) -> bytes:
    """A no-GPS, long-enough synthetic FIT fixture for this checkpoint's
    E2E: continuous heart rate and (when `power_w` is given) continuous
    power over `_CHECKPOINT_RECORD_COUNT` seconds -- long enough for the
    threshold built-in to reach `Computed` rather than refuse for
    insufficient duration, and with no GPS so no tile fetch is ever
    attempted. Built from the same low-level `tests.fixtures.builder`
    primitives `tests/load/threshold/test_feature_e2e.py::_long_fit_bytes`
    uses, kept local and minimal here.
    """
    mesgs: list[builder.Mesg] = [
        builder._file_id(serial),
        builder._device_info(serial, f"Checkpoint{fit_sport.title()}Watch"),
        {"mesg_num": builder._MESG_SPORT, "sport": fit_sport, "sub_sport": "generic"},
    ]
    for i in range(_CHECKPOINT_RECORD_COUNT):
        record: builder.Mesg = {
            "mesg_num": builder._MESG_RECORD,
            "timestamp": builder.FIT_TIMESTAMP_BASE + i,
            "distance": _CHECKPOINT_SPEED_MPS * i,
            "heart_rate": hr_base + (i % 5),
        }
        if power_w is not None:
            record["power"] = power_w
        mesgs.append(record)
    session: builder.Mesg = {
        "mesg_num": builder._MESG_SESSION,
        "start_time": builder.FIT_TIMESTAMP_BASE,
        "timestamp": builder.FIT_TIMESTAMP_BASE + (_CHECKPOINT_RECORD_COUNT - 1),
        "sport": fit_sport,
        "sub_sport": "generic",
        "total_elapsed_time": float(_CHECKPOINT_RECORD_COUNT - 1),
        "total_timer_time": float(_CHECKPOINT_RECORD_COUNT - 1),
        "total_distance": _CHECKPOINT_SPEED_MPS * (_CHECKPOINT_RECORD_COUNT - 1),
        "avg_heart_rate": hr_base,
        "max_heart_rate": hr_base + 4,
    }
    if power_w is not None:
        session["avg_power"] = power_w
        session["max_power"] = power_w
    mesgs.append(session)
    mesgs.append(
        builder._activity(
            _CHECKPOINT_RECORD_COUNT - 1, float(_CHECKPOINT_RECORD_COUNT - 1)
        )
    )
    return builder.encode(mesgs)


def _write_release_checkpoint_profile(data_root: Path) -> None:
    """A real `athlete.toml`, written through the real profile store, with
    just enough benchmarks for the threshold built-in to COMPUTE (not
    refuse as `MissingInputs`) for a no-GPS ride (power channel) and a
    no-GPS hike (heart-rate channel), non-interactively -- the same shape
    `tests/load/threshold/test_feature_e2e.py::_populated_profile` uses,
    narrowed to only the two disciplines this checkpoint's fixtures need.
    """
    measured_on = date(2021, 1, 1)  # well before the ~2021-09-07 fixture date
    profile = AthleteProfile(data={})
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=210.0,
        measured_on=measured_on,
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM,
        discipline=Sport.RIDE,
        value=160.0,
        measured_on=measured_on,
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM,
        discipline=Sport.HIKE,
        value=115.0,
        measured_on=measured_on,
    )
    profile = profile.with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190.0,
        measured_on=measured_on,
    )
    profile = profile.with_benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=50.0,
        measured_on=measured_on,
    )
    save_profile(data_root, profile)


def test_checkpoint_installed_wheel_syncs_and_computes_load(
    build_a: tuple[Path, ...], tmp_path: Path
) -> None:
    """The E2E the migration checkpoint names: install the REAL built wheel
    into a clean, isolated environment, run a full ingestion over a
    synthetic source there, and confirm the installed tool wrote documents
    with the `threshold` built-in computing load, exiting successfully (Req
    1.10, 6.2, 6.3, 6.9, 6.10; design.md "E2E Tests -> Installed tool from
    the built artifact").

    Both fixtures (`_checkpoint_fit_bytes` for ride/hike) carry no GPS -- so
    no tile fetch is ever attempted -- and are long enough (90s, above the
    threshold built-in's 60s minimum) with continuous heart rate (both) and
    continuous power (ride) so the built-in reaches `Computed`, never
    `NotComputed`/`Unsupported`, non-interactively; `[tiles] enabled =
    false` is set anyway, so the isolated install can perform no network
    access even if a future fixture change adds GPS.
    """
    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required for this checkpoint's install but was not found on PATH"
    )

    tool_dir = tmp_path / "uv-tool-dir"
    bin_dir = tmp_path / "uv-tool-bin"
    tool_dir.mkdir()
    bin_dir.mkdir()
    install_env = os.environ.copy()
    install_env["UV_TOOL_DIR"] = str(tool_dir)
    install_env["UV_TOOL_BIN_DIR"] = str(bin_dir)

    wheel_path = _artifact(build_a, ".whl")

    try:
        install = _install_offline_from_wheel(uv, install_env, wheel_path)
        assert install.returncode == 0, (
            f"offline install of the built wheel failed:\n"
            f"{install.stdout}\n{install.stderr}"
        )

        exe = bin_dir / "fitdocs"
        if not exe.exists():  # console scripts are `.exe` on Windows
            exe = bin_dir / "fitdocs.exe"
        assert exe.exists(), f"installed fitdocs console script not found in {bin_dir}"

        version_result = _run([str(exe), "--version"], install_env)
        assert version_result.returncode == 0, (
            f"--version failed:\n{version_result.stderr}"
        )
        assert version_result.stdout.strip() == _project_manifest_version()

        # --- build a data root + synthetic source, isolated from HOME ----
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        data_root = tmp_path / "data"
        data_root.mkdir()
        source_dir = tmp_path / "src"
        source_dir.mkdir()

        # Falsity-before: no workouts/ exists prior to the sync.
        assert not (data_root / "workouts").exists()

        _write_release_checkpoint_profile(data_root)
        (data_root / "fitdocs.toml").write_text(
            "[tiles]\nenabled = false\n", encoding="utf-8"
        )
        (source_dir / "ride.fit").write_bytes(
            _checkpoint_fit_bytes(9101, "cycling", power_w=200, hr_base=150)
        )
        (source_dir / "hike.fit").write_bytes(
            _checkpoint_fit_bytes(9102, "hiking", hr_base=115)
        )

        sync_env = dict(install_env)
        sync_env["FITDOCS_DATA"] = str(data_root)
        sync_env["HOME"] = str(home_dir)

        sync_result = _run([str(exe), "sync", str(source_dir), "--no-prompt"], sync_env)
        assert sync_result.returncode == 0, (
            f"installed `fitdocs sync` failed:\n"
            f"{sync_result.stdout}\n{sync_result.stderr}"
        )

        workouts_dir = data_root / "workouts"
        assert workouts_dir.is_dir(), "sync wrote no workouts/ directory at all"
        doc_paths = sorted(
            p for p in workouts_dir.glob("*.md") if p.name != "AGENTS.md"
        )
        assert len(doc_paths) >= 2, (
            f"expected at least 2 workout documents, found {doc_paths!r}"
        )
        assert (workouts_dir / "AGENTS.md").is_file(), (
            "the ownership declaration (AGENTS.md) was not emitted under workouts/"
        )

        doc_texts = [p.read_text(encoding="utf-8") for p in doc_paths]
        assert any("load_methodology: threshold" in text for text in doc_texts), (
            "no installed-tool-written document shows the threshold built-in "
            f"having computed load: {doc_texts!r}"
        )
    finally:
        _run([uv, "tool", "uninstall", "fitdocs"], install_env)
