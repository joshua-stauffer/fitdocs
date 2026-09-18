"""Artifact-policy data and reader tests (task 1.4: ArtifactPolicy).

This is the design's `tests/test_release_artifacts.py` -- named there for
artifact tests generally; this task covers only the policy *data* and its
reader (`release/artifact-policy.toml`, `scripts/artifact_policy.py`). Later
tasks (2.1-2.3) extend this file with the builder and checker.

Six groups of assertions:

* the real policy file loads, and its content matches the design's declared
  end-state shape (minus the not-yet-added inbox skill entry);
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
import subprocess
import tarfile
import tomllib
import zipfile
from collections import Counter
from collections.abc import Iterator, Mapping
from enum import StrEnum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest
import scripts.build_release as build_release
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
)
from scripts.check_artifacts import (
    main as check_artifacts_main,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_POLICY_PATH = REPO_ROOT / DEFAULT_POLICY_PATH


# ---------------------------------------------------------------------------
# The real policy file: content
# ---------------------------------------------------------------------------


def test_real_policy_loads() -> None:
    policy = load_policy(REAL_POLICY_PATH)
    assert isinstance(policy, ArtifactPolicy)


def test_wheel_required_has_the_four_design_members_and_not_the_inbox_skill() -> None:
    policy = load_policy(REAL_POLICY_PATH)
    for member in (
        "fitdocs/__init__.py",
        "fitdocs/py.typed",
        "fitdocs/skills/build-training-block/SKILL.md",
        "fitdocs/skills/build-training-block/example-block.toml",
    ):
        assert member in policy.wheel_required
    # Not yet: task 4.2 adds this entry when the inbox skill lands.
    assert "fitdocs/skills/fitdocs-workouts/SKILL.md" not in policy.wheel_required


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
    clean_dist: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = sorted(clean_dist.iterdir())

    exit_code = check_artifacts_main(
        ["--dist-dir", str(clean_dist), "--policy", str(REAL_POLICY_PATH)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "fitdocs-9.9.9-py3-none-any.whl" in out
    assert "fitdocs-9.9.9.tar.gz" in out
    # Writes nothing: the directory listing is unchanged across the call.
    assert sorted(clean_dist.iterdir()) == before


def test_main_on_a_violating_dir_returns_1_and_lists_every_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    _make_wheel(dist_dir, {}, metadata="Name: x\n\nbody\n")
    _make_sdist(dist_dir, {}, pkg_info="Name: x\n\nbody\n")

    policy = load_policy(REAL_POLICY_PATH)
    expected_violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert len(expected_violations) > 1, (
        "the fixture must trip more than one violation for this test to mean anything"
    )

    exit_code = check_artifacts_main(
        ["--dist-dir", str(dist_dir), "--policy", str(REAL_POLICY_PATH)]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert f"{len(expected_violations)} violation(s)" in err
    # One line per violation plus the summary line.
    assert err.count("\n") == len(expected_violations) + 1


# --- real-artifact smoke -----------------------------------------------


def test_real_build_with_the_real_policy_has_zero_violations(
    build_a: tuple[Path, ...],
) -> None:
    dist_dir = build_a[0].parent
    policy = load_policy(REAL_POLICY_PATH)
    violations = check_artifacts(dist_dir, policy=policy, repo_root=REPO_ROOT)
    assert violations == (), f"real build failed conformance: {violations!r}"


# --- import isolation --------------------------------------------------


def test_check_artifacts_module_imports_nothing_from_fitdocs_or_tests() -> None:
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
    assert "tests" not in imported_names
