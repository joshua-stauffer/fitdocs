"""Artifact-policy data and reader tests (task 1.4: ArtifactPolicy).

This is the design's `tests/test_release_artifacts.py` -- named there for
artifact tests generally; this task covers only the policy *data* and its
reader (`release/artifact-policy.toml`, `scripts/artifact_policy.py`). Later
tasks (2.1-2.3) extend this file with the builder and checker.

Five groups of assertions:

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
  against a fake `subprocess.run` recording exactly what it was called with.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import tarfile
import tomllib
import zipfile
from collections.abc import Iterator, Mapping
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
