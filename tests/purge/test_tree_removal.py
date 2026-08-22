"""Task 3.1's own observables (Req 1.1, 2.1, 9.7, 11.4): the writeup, both
extracted tables and the prior rewrite map are gone from the working tree;
the packaging build-target section that existed only to exclude two of them
is gone entirely; and a built sdist carries none of the four removed paths.

No wheel check is included: a built wheel could never have carried any of
these four paths, before or after this task -- hatchling's wheel target is
scoped to ``packages = ["src/fitdocs"]`` (`pyproject.toml`), and none of the
four removed paths ever lived under `src/fitdocs`. Measured directly: a
member planted at the removed writeup's own path in a real build of this
checkout still does not appear in the built wheel's member list, so an
absence assertion here would be structurally unable to fail and is
therefore not included (`change-protocol.md`'s Fixture Discrimination gate:
an insensitive assertion is worse than a missing one). The task's own stated
observable is sdist-only for the same reason.

Every check here is keyed on the removed paths' own values -- resolved from
`FITDOCS_FORBIDDEN_STRINGS` rather than hard-coded (task 6.3: this module
used to hold all five removed paths and two tokens literally). Every test
now depends on the variable being set, unlike before task 6.3; `require()`
(`tests._forbidden_strings`) skips when it is unset (Req 11.8's one
legitimate silent outcome) rather than this module pinning nothing while
reporting green.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

from scripts.purge.sweep import entries_by_category, load_categorized_entries

from tests._forbidden_strings import ForbiddenStrings, matches, require

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_TIMEOUT_S = 120


def _load() -> ForbiddenStrings:
    """`require()` against the real repository -- the single call site every
    test below uses, so a source that is set but broken raises the same way
    everywhere rather than each test re-deriving its own posture."""
    return require(_REPO_ROOT)


def _path_category_values(forbidden_strings: ForbiddenStrings) -> tuple[str, ...]:
    """Every ``path``-category value from `forbidden_strings.source`, in
    file order -- the category-preserving parse `scripts/purge/sweep.py`
    already defines (`load_categorized_entries` / `entries_by_category`),
    reused rather than re-implemented a third time."""
    entries = load_categorized_entries(forbidden_strings.source)
    return entries_by_category(entries).get("path", ())


def _removed_file_paths(forbidden_strings: ForbiddenStrings) -> tuple[str, ...]:
    """The ``path``-category entries that name a removed FILE task 3.1
    deleted -- filters out the one entry naming a containing directory
    (identified by carrying no `.` in its basename, unlike every file
    entry): task 3.1 removed that directory only as a consequence of
    removing every file inside it, so it is not one of `git ls-files`'s
    removed entries and does not belong in a needle set checked against
    `git ls-files` or a built sdist's member list.
    """
    return tuple(
        value
        for value in _path_category_values(forbidden_strings)
        if "." in value.rsplit("/", 1)[-1]
    )


def _existed_before_deletion(path: str) -> bool:
    """Whether `path` existed in the tree immediately before task 3.1 deleted
    it, checked through history so it stays correct whether the deletion is
    still staged, has been committed, or (after Major 7) has been rewritten
    into an unresolvable commit-ish. Never raises: returns `False` when no
    resolvable pre-deletion state can be found.

    This is the needle-side positive control for the two absence checks
    below: an absence assertion over an EMPTY needle set passes vacuously
    (Implementation Notes / `tests/load/test_packaging.py`'s own
    ``_WITHDRAWN_CONTENT_FINGERPRINTS`` non-empty guard is the precedent this
    mirrors), and a needle set that has silently shrunk to a path that was
    never actually removed would pass the same way. Checking "did this path
    exist before the deletion" closes both: it is asserted FALSE-then-TRUE,
    not merely present, so a needle that was never real cannot pass by
    construction.
    """
    exists_at_head = subprocess.run(
        ["git", "cat-file", "-e", f"HEAD:{path}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if exists_at_head.returncode == 0:
        return True

    rev_list = subprocess.run(
        ["git", "rev-list", "-1", "HEAD", "--", path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    touching_commit = rev_list.stdout.strip()
    if rev_list.returncode != 0 or not touching_commit:
        return False

    parent_exists = subprocess.run(
        ["git", "cat-file", "-e", f"{touching_commit}~1:{path}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return parent_exists.returncode == 0


def test_removed_paths_actually_existed_before_the_deletion() -> None:
    # The needle-set positive control itself, pinned directly: every entry
    # of the resolved removed-file-paths set must be confirmed to have
    # existed in history before task 3.1 removed it. Without this, an empty
    # needle set (or one silently shrunk to paths that were never real)
    # would leave the two absence checks below vacuously green.
    forbidden_strings = _load()
    removed_paths = _removed_file_paths(forbidden_strings)
    assert removed_paths, (
        "the needle set is empty -- the absence checks below cannot fail "
        "regardless of what they scan"
    )
    never_existed = [
        path for path in removed_paths if not _existed_before_deletion(path)
    ]
    assert not never_existed, (
        f"not confirmed to have existed before task 3.1's deletion: {never_existed} "
        "-- the needle set may have shrunk to a name that was never actually "
        "removed"
    )


# --- git ls-files -------------------------------------------------------------


def test_removed_paths_are_absent_from_git_ls_files() -> None:
    forbidden_strings = _load()
    removed_paths = _removed_file_paths(forbidden_strings)
    assert removed_paths, (
        "the needle set is empty -- this check cannot fail regardless of "
        "what git ls-files returns"
    )

    result = subprocess.run(
        ["git", "ls-files"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = result.stdout.splitlines()
    assert tracked, (
        "git ls-files returned nothing -- the walk is looking at the wrong directory"
    )

    still_tracked = [path for path in removed_paths if path in tracked]
    assert not still_tracked, f"still tracked by git: {still_tracked}"


def test_removed_directory_no_longer_exists_on_disk() -> None:
    # A positive control distinct from git ls-files: the containing directory
    # itself (not merely its two files) must be gone, not left behind empty.
    # The directory fragment is the one `path`-category entry
    # `_removed_file_paths` filters OUT (no extension in its basename).
    forbidden_strings = _load()
    path_values = _path_category_values(forbidden_strings)
    file_values = set(_removed_file_paths(forbidden_strings))
    directory_fragments = [value for value in path_values if value not in file_values]
    assert directory_fragments, (
        "no directory-shaped path-category entry was found -- this check "
        "cannot fail regardless of what exists on disk"
    )

    for fragment in directory_fragments:
        assert not (_REPO_ROOT / fragment).exists()


# --- pyproject.toml -------------------------------------------------------------


def test_pyproject_has_no_sdist_build_target_section() -> None:
    forbidden_strings = _load()
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    # Positive control: the sibling wheel section must survive -- proving
    # this test reads the real file and is not vacuously passing over an
    # empty or unrelated one.
    assert "[tool.hatch.build.targets.wheel]" in text, (
        "the wheel build-target section is missing -- this test is reading "
        "the wrong file, not proving the sdist section is gone"
    )

    assert "[tool.hatch.build.targets.sdist]" not in text

    path_values = _path_category_values(forbidden_strings)
    assert path_values, (
        "the needle set is empty -- the absence checks below cannot fail "
        "regardless of what pyproject.toml contains"
    )
    present = [value for value in path_values if value.lower() in text.lower()]
    assert not present, f"pyproject.toml still references removed path(s): {present}"


def test_pyproject_carries_no_third_party_copyright_or_trademark_notice() -> None:
    # Req 11.4: the deleted comment block above the exclude array reproduced
    # the third party's copyright notice. Distinct from the section-absence
    # check above -- a section could in principle be deleted while a stray
    # copy of this notice survived elsewhere in the file, and this asserts
    # the notice itself is gone, not merely the section that used to carry
    # it.
    forbidden_strings = _load()
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()

    present = matches(text, forbidden_strings)
    assert not present, f"pyproject.toml still contains forbidden value(s): {present}"
    assert "rights reserved" not in text


# --- built artifacts -------------------------------------------------------------


def _build(fmt: str, out_dir: Path) -> Path:
    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required to build the artifact for this observable but was "
        "not found on PATH"
    )
    result = subprocess.run(
        [uv, "build", f"--{fmt}", "--out-dir", str(out_dir)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=_BUILD_TIMEOUT_S,
        check=False,
    )
    assert result.returncode == 0, (
        f"`uv build --{fmt}` failed:\n{result.stdout}\n{result.stderr}"
    )
    suffix = "*.tar.gz" if fmt == "sdist" else "*.whl"
    built = sorted(out_dir.glob(suffix))
    assert len(built) == 1, f"expected exactly one built {fmt}, got {built}"
    return built[0]


def _sdist_member_names(archive: Path) -> list[str]:
    with tarfile.open(archive) as sdist:
        names = sdist.getnames()
    # Archive members carry the `fitdocs-X.Y.Z/` version prefix; strip it so
    # membership is comparable to repo-relative paths.
    return [name.split("/", 1)[-1] for name in names]


def test_built_sdist_contains_no_removed_path(tmp_path: Path) -> None:
    forbidden_strings = _load()
    removed_paths = _removed_file_paths(forbidden_strings)
    assert removed_paths, (
        "the needle set is empty -- this check cannot fail regardless of "
        "what the built sdist contains"
    )

    archive = _build("sdist", tmp_path)
    names = _sdist_member_names(archive)
    assert names, (
        "the built sdist has no members at all -- this guard's archive is "
        "empty or malformed, so the absence check below would otherwise "
        "pass having inspected nothing"
    )

    present = [path for path in removed_paths if path in names]
    assert not present, f"built sdist still contains removed path(s): {present}"
