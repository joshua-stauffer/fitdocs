"""Artifact-policy data and reader tests (task 1.4: ArtifactPolicy).

This is the design's `tests/test_release_artifacts.py` -- named there for
artifact tests generally; this task covers only the policy *data* and its
reader (`release/artifact-policy.toml`, `scripts/artifact_policy.py`). Later
tasks (2.1-2.3) extend this file with the builder and checker.

Four groups of assertions:

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
  scan can actually catch one.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Mapping
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import pytest
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
