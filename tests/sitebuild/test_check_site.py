"""Tests for the site gate, ``scripts/check_site.py`` (task 2.6; 10.3-10.5).

The match data is a test-written synthetic file in ``tmp_path`` (nothing is
written inside the repository), holding an invented needle, not a real
forbidden string. The variable is removed before every test and set only where
a test says so.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import scripts.check_site as check_site
from scripts.check_site import Finding, FindingKind

from tests._content_fingerprints import SALT
from tests._content_oracle import ENTROPY_FLOOR_BITS, digest, tokens, windows
from tests._forbidden_strings import ENV_VAR

REPO_ROOT = Path(__file__).resolve().parents[2]

_NEEDLE = "PlantedSiteNeedle"

_needs_symlinks = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs privileges on Windows"
)
_needs_non_root = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="mode 000 does not stop root from reading",
)


@pytest.fixture(autouse=True)
def _no_forbidden_strings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)


def _use_match_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *values: str
) -> Path:
    match_file = tmp_path / "synthetic-match-data.txt"
    match_file.write_text("\n".join(values or (_NEEDLE,)) + "\n")
    monkeypatch.setenv(ENV_VAR, str(match_file))
    return match_file


def _tree(base: Path, name: str, files: Mapping[str, bytes | str]) -> Path:
    root = base / name
    root.mkdir()
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            target.write_text(content)
        else:
            target.write_bytes(content)
    return root


def _run(capsys: pytest.CaptureFixture[str], *roots: Path) -> tuple[int, str, str]:
    code = check_site.main([str(root) for root in roots])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _finding_lines(stderr: str) -> list[list[str]]:
    """The tab-separated finding lines (kind, subject, detail, remedy)."""
    return [line.split("\t") for line in stderr.splitlines() if "\t" in line]


def _kinds(stderr: str) -> list[str]:
    return [fields[0] for fields in _finding_lines(stderr)]


# --- clean tree ------------------------------------------------------------


def test_clean_trees_exit_0_and_print_no_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `check_trees` appending one finding per root unconditionally
    (or `main` returning 1 for an empty findings tuple).

    The trees hold text, binary and numeric content, so a gate that flags
    every file, or every number, cannot pass.
    """
    _use_match_file(monkeypatch, tmp_path)
    first = _tree(
        tmp_path,
        "first",
        {
            "index.md": "# Home\n\nSplit 4:52:31 at 3.14159.\n",
            "a/logo.png": b"\x89PNG\x00",
        },
    )
    second = _tree(tmp_path, "second", {"deep/er/page.md": "clean prose 12345\n"})
    assert list(first.rglob("*.md")) and list(second.rglob("*.md"))

    code, out, err = _run(capsys, first, second)

    assert (code, err) == (0, "")
    assert out.startswith("clean")


# --- token matches in content ----------------------------------------------


def test_needle_in_each_root_is_reported_once_per_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `roots` narrowed to one root in `check_trees` (`roots[:1]` or
    `roots[-1:]`) -- one finding instead of two.
    """
    _use_match_file(monkeypatch, tmp_path)
    first = _tree(
        tmp_path, "first", {"a.md": f"see {_NEEDLE} here\n", "ok.md": "fine\n"}
    )
    second = _tree(
        tmp_path, "second", {"n/est/b.md": f"{_NEEDLE}\n", "ok.md": "fine\n"}
    )

    code, out, err = _run(capsys, first, second)

    assert code == 1
    lines = _finding_lines(err)
    assert [fields[0] for fields in lines] == ["encumbered_content"] * 2
    subjects = sorted(fields[1] for fields in lines)
    assert subjects == sorted([str(first / "a.md"), str(second / "n" / "est" / "b.md")])
    assert _NEEDLE not in out + err


def test_needle_in_second_root_alone_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `check_trees` stopping after the first root that is clean
    (a `break` after the first root's walk).
    """
    _use_match_file(monkeypatch, tmp_path)
    first = _tree(tmp_path, "first", {"a.md": "fine\n"})
    second = _tree(tmp_path, "second", {"b.md": f"{_NEEDLE}\n"})

    code, _out, err = _run(capsys, first, second)

    assert code == 1
    assert _kinds(err) == ["encumbered_content"]


@pytest.mark.parametrize(
    "name, content",
    [
        ("page.md", f"before {_NEEDLE} after\n".encode()),
        ("logo.png", f"\x89PNG {_NEEDLE}".encode()),
        ("data.bin", b"\xff\xfe\x00" + _NEEDLE.encode() + b"\xff\xff"),
        ("no-suffix", f"{_NEEDLE}".encode()),
    ],
)
def test_needle_in_any_file_content_is_found_however_it_is_encoded(
    name: str,
    content: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dies on: the read decoding with `errors="strict"` (the invalid-UTF-8
    `data.bin` case raises), or the content check skipping files whose suffix
    is not text-like (the `.png`, `data.bin` and suffixless cases).
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {name: content})

    code, out, err = _run(capsys, root)

    assert code == 1
    assert _kinds(err) == ["encumbered_content"]
    assert _NEEDLE not in out + err


# --- token matches in paths ------------------------------------------------


@pytest.mark.parametrize(
    "files, empty_dirs, expected_kinds",
    [
        ({f"{_NEEDLE}.md": "clean\n"}, [], ["encumbered_path"]),
        ({}, [f"{_NEEDLE}-dir"], ["encumbered_path"]),
        (
            {f"{_NEEDLE}-dir/inner.md": "clean\n"},
            [],
            ["encumbered_path", "encumbered_path"],
        ),
    ],
)
def test_needle_in_a_path_is_found_and_never_echoed(
    files: dict[str, str],
    empty_dirs: list[str],
    expected_kinds: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dies on: the path check deleted (no finding), the path check applied to
    files only (the empty-directory case), the path check applied to the
    file's own name instead of its root-relative path (the nested case yields
    one finding, not two), or the finding's subject echoing the path.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", files)
    for directory in empty_dirs:
        (root / directory).mkdir()

    code, out, err = _run(capsys, root)

    assert code == 1
    assert _kinds(err) == expected_kinds
    assert _NEEDLE not in out + err


def test_content_finding_in_a_needle_named_file_does_not_echo_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: redacting the subject of path findings only, so that the
    content finding for the same file echoes the needle-bearing name.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {f"{_NEEDLE}.md": f"{_NEEDLE}\n"})

    code, out, err = _run(capsys, root)

    assert code == 1
    assert sorted(_kinds(err)) == ["encumbered_content", "encumbered_path"]
    assert _NEEDLE not in out + err


def test_redacted_subjects_still_tell_two_files_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: one constant placeholder subject for every redacted path."""
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(
        tmp_path,
        "site",
        {f"{_NEEDLE}-one.md": "x\n", f"{_NEEDLE}-two.md": "y\n"},
    )

    _code, _out, err = _run(capsys, root)

    subjects = [fields[1] for fields in _finding_lines(err)]
    assert len(subjects) == 2
    assert len(set(subjects)) == 2


# --- fingerprinted control value -------------------------------------------


def test_fingerprinted_value_is_found_through_the_module_level_constants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `check_trees` snapshotting `FINGERPRINTS` / `WINDOW_LENGTHS`
    at import (a default argument) so the patch never takes effect -- the
    second run stays clean -- or on the oracle call deleted.
    """
    _use_match_file(monkeypatch, tmp_path)
    sentence = (
        "distance 741.309285 km over 4:52:31 at a rate of 0.837162945 "
        "across 209581473 intervals"
    )
    toks = tokens(sentence)
    emitted = windows(toks, ENTROPY_FLOOR_BITS)
    assert emitted, "the invented control sentence does not clear the entropy floor"
    fingerprints = frozenset(
        digest(toks[start : start + length], SALT) for start, length in emitted
    )
    lengths = frozenset(length for _, length in emitted)
    root = _tree(tmp_path, "site", {"page.md": f"# {sentence}\n"})

    code_before, _out, err_before = _run(capsys, root)
    assert (code_before, err_before) == (0, "")

    monkeypatch.setattr(check_site, "FINGERPRINTS", fingerprints)
    monkeypatch.setattr(check_site, "WINDOW_LENGTHS", lengths)
    code, out, err = _run(capsys, root)

    assert code == 1
    lines = _finding_lines(err)
    assert [fields[0] for fields in lines] == ["encumbered_content"]
    assert "fingerprint" in lines[0][2]
    assert lines[0][1] == str(root / "page.md")
    for token in ("741.309285", "0.837162945", "209581473"):
        assert token not in out + err


# --- symlinks --------------------------------------------------------------


@_needs_symlinks
def test_every_symlink_is_a_link_finding_and_is_not_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: the link branch deleted or narrowed to files (the affected
    links fall into the not-a-regular-file branch and are reported
    `unreadable`, not `link`), a symlinked directory being descended into
    (`outside/` findings appear), or the finding echoing the link target
    (named with the needle).
    """
    _use_match_file(monkeypatch, tmp_path)
    outside = _tree(
        tmp_path,
        "outside",
        {"secret.md": f"{_NEEDLE}\n", f"{_NEEDLE}-dir/inner.md": f"{_NEEDLE}\n"},
    )
    root = _tree(tmp_path, "site", {"ok.md": "fine\n"})
    (root / "file-link").symlink_to(outside / "secret.md")
    (root / "dir-link").symlink_to(outside / f"{_NEEDLE}-dir", target_is_directory=True)
    (root / "broken-link").symlink_to(outside / f"{_NEEDLE}-missing")

    code, out, err = _run(capsys, root)

    assert code == 1
    lines = _finding_lines(err)
    assert sorted(fields[:2] for fields in lines) == sorted(
        [
            ["link", str(root / "broken-link")],
            ["link", str(root / "dir-link")],
            ["link", str(root / "file-link")],
        ]
    )
    assert _NEEDLE not in out + err


# --- unreadable entries ----------------------------------------------------


@_needs_non_root
def test_unreadable_file_is_a_finding_not_a_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `except OSError: continue` around the file read."""
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {"ok.md": "fine\n", "locked.md": f"{_NEEDLE}\n"})
    locked = root / "locked.md"
    locked.chmod(0o000)
    try:
        assert not os.access(locked, os.R_OK), "the file is still readable"
        code, out, err = _run(capsys, root)
    finally:
        locked.chmod(0o644)

    assert code == 1
    lines = _finding_lines(err)
    assert [fields[:2] for fields in lines] == [["unreadable", str(locked)]]
    assert _NEEDLE not in out + err


@_needs_non_root
def test_unlistable_directory_is_a_finding_not_a_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `except OSError: return` around the directory listing."""
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(
        tmp_path, "site", {"ok.md": "fine\n", "locked/inner.md": f"{_NEEDLE}\n"}
    )
    locked = root / "locked"
    locked.chmod(0o000)
    try:
        assert not os.access(locked, os.R_OK), "the directory is still listable"
        code, out, err = _run(capsys, root)
    finally:
        locked.chmod(0o755)

    assert code == 1
    lines = _finding_lines(err)
    assert [fields[:2] for fields in lines] == [["unreadable", str(locked)]]
    assert _NEEDLE not in out + err


@_needs_non_root
def test_unlistable_needle_named_directory_does_not_echo_its_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: the unreadable finding for a directory using its raw path
    as subject instead of the redacted one.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {f"{_NEEDLE}-dir/inner.md": "fine\n"})
    locked = root / f"{_NEEDLE}-dir"
    locked.chmod(0o000)
    try:
        assert not os.access(locked, os.R_OK), "the directory is still listable"
        code, out, err = _run(capsys, root)
    finally:
        locked.chmod(0o755)

    assert code == 1
    assert sorted(_kinds(err)) == ["encumbered_path", "unreadable"]
    assert _NEEDLE not in out + err


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no FIFOs on this platform")
def test_fifos_are_reported_unreadable_without_being_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dies on: the walk opening any entry that is not a directory or a link
    (opening a FIFO blocks; the subprocess times out and the test errors), the
    special-entry finding using the raw path as subject (the needle-named FIFO
    is echoed), or the path check not applying to a special entry.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {"ok.md": "fine\n"})
    os.mkfifo(root / "pipe")
    os.mkfifo(root / f"{_NEEDLE}-pipe")
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("FITDOCS_SITE_CONTENT", "FITDOCS_DATA")
    }

    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_site", str(root)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 1
    lines = _finding_lines(result.stderr)
    assert sorted(fields[0] for fields in lines) == [
        "encumbered_path",
        "unreadable",
        "unreadable",
    ]
    assert str(root / "pipe") in [fields[1] for fields in lines]
    assert _NEEDLE not in result.stdout + result.stderr


# --- missing root ----------------------------------------------------------


def test_missing_root_exits_2_even_beside_a_clean_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: a nonexistent root being skipped (`if not root.is_dir():
    continue`) -- the run would exit 0.
    """
    _use_match_file(monkeypatch, tmp_path)
    clean = _tree(tmp_path, "clean", {"ok.md": "fine\n"})
    missing = tmp_path / "absent"

    code, out, err = _run(capsys, clean, missing)

    assert code == 2
    assert not out.startswith("clean")
    assert str(missing) in err


def test_a_file_given_as_root_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: the root check using `exists()` instead of `is_dir()`."""
    _use_match_file(monkeypatch, tmp_path)
    a_file = tmp_path / "plain.md"
    a_file.write_text("fine\n")

    code, out, err = _run(capsys, a_file)

    assert code == 2
    assert not out.startswith("clean")
    assert str(a_file) in err


# --- fail closed -----------------------------------------------------------


@_needs_symlinks
def test_unset_variable_is_exactly_one_gate_not_run_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `main` returning 0 when `load` returns `None` (a skip), on
    the walk running anyway (the planted symlink adds a second finding), or
    on the finding not naming the variable.
    """
    assert ENV_VAR not in os.environ
    root = _tree(tmp_path, "site", {"ok.md": "fine\n"})
    (root / "link").symlink_to(root / "ok.md")

    code, out, err = _run(capsys, root)

    assert code == 1
    lines = _finding_lines(err)
    assert len(lines) == 1
    assert lines[0][0] == "gate_not_run"
    assert ENV_VAR in err
    assert "gate_not_run" in err
    assert not out.startswith("clean")


@pytest.mark.parametrize("state", ["missing", "empty", "inside_repo", "unreadable"])
def test_unusable_source_exits_2_and_reports_no_finding(
    state: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dies on: `ForbiddenStringsSourceError` being caught in `main` and
    turned into a `gate_not_run` finding (exit 1) or a clean pass (exit 0),
    or `check_trees` catching it.
    """
    root = _tree(tmp_path, "site", {"ok.md": "fine\n"})
    source = tmp_path / "match.txt"
    if state == "missing":
        pass
    elif state == "empty":
        source.write_text("# only a comment\n\n")
    elif state == "inside_repo":
        source = REPO_ROOT / "pyproject.toml"
    else:
        if not hasattr(os, "geteuid") or os.geteuid() == 0:
            pytest.skip("mode 000 does not stop root from reading")
        source.write_text(f"{_NEEDLE}\n")
        source.chmod(0o000)
    monkeypatch.setenv(ENV_VAR, str(source))
    try:
        code, out, err = _run(capsys, root)
    finally:
        if state == "unreadable":
            source.chmod(0o644)

    assert code == 2
    assert not out.startswith("clean")
    assert ENV_VAR in err
    assert _finding_lines(err) == []


# --- walk coverage ---------------------------------------------------------


@pytest.mark.parametrize("name", [".hidden", ".well-known/x.txt", "a/.b/.c"])
def test_needle_in_dotfiles_and_dot_directories_is_found(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dies on: the listing dropping names that start with `.` (`.hidden`),
    or the walk not descending into dot-directories (`.well-known/`).
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {name: f"{_NEEDLE}\n"})

    code, out, err = _run(capsys, root)

    assert code == 1
    assert _kinds(err) == ["encumbered_content"]
    assert _NEEDLE not in out + err


def test_needle_after_three_mebibytes_of_padding_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: the read truncating a file to a prefix (`read_bytes()[:65536]`)."""
    _use_match_file(monkeypatch, tmp_path)
    padding = b"lorem ipsum\n" * (3 * 1024 * 1024 // 12 + 1)
    assert len(padding) > 3 * 1024 * 1024
    root = _tree(tmp_path, "site", {"big.md": padding + _NEEDLE.encode() + b"\n"})

    code, out, err = _run(capsys, root)

    assert code == 1
    assert _kinds(err) == ["encumbered_content"]


def test_matching_ignores_case_and_line_wraps_in_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: a case-sensitive content match (the lowercase needle and the
    lowercase phrase are missed).
    """
    _use_match_file(monkeypatch, tmp_path, _NEEDLE, "Planted Phrase")
    root = _tree(
        tmp_path,
        "site",
        {"lower.md": f"{_NEEDLE.lower()}\n", "wrapped.md": "planted\nphrase\n"},
    )

    code, out, err = _run(capsys, root)

    assert code == 1
    assert _kinds(err) == ["encumbered_content"] * 2
    assert _NEEDLE.lower() not in (out + err).lower()


def test_matching_ignores_case_in_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: a case-sensitive path match."""
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {f"{_NEEDLE.swapcase()}.md": "clean\n"})

    code, out, err = _run(capsys, root)

    assert code == 1
    assert _kinds(err) == ["encumbered_path"]
    assert _NEEDLE.lower() not in (out + err).lower()


def test_invalid_bytes_inside_a_value_do_not_join_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: decoding with `errors="ignore"`, which drops the `\\xff` and
    so manufactures a match out of `PlantedSite<xff>Needle`.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(
        tmp_path,
        "site",
        {"split.bin": b"PlantedSite\xffNeedle", "ok.md": "fine\n"},
    )

    code, out, err = _run(capsys, root)

    assert (code, err) == (0, "")


def test_redacted_subjects_are_distinct_across_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: the ordinal restarting in each directory (a redacted file
    in one directory then shares a subject with a redacted directory in
    another).
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(
        tmp_path,
        "site",
        {f"{_NEEDLE}-a/x.md": "x\n", f"{_NEEDLE}-b/y.md": "y\n"},
    )

    _code, out, err = _run(capsys, root)

    subjects = [fields[1] for fields in _finding_lines(err)]
    assert len(subjects) == 4
    assert len(set(subjects)) == 4
    assert _NEEDLE not in out + err


def test_unexpected_error_mid_walk_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: `check_trees` wrapping the walk in `except Exception: pass`
    (the run then exits 0 over an unscanned tree).
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {"ok.md": "fine\n"})

    def boom(*_args: object) -> bool:
        raise RuntimeError("synthetic mid-walk failure")

    monkeypatch.setattr(check_site, "oracle_scan", boom)

    with pytest.raises(RuntimeError, match="synthetic mid-walk failure"):
        _run(capsys, root)


class _ProxyEntry:
    """A `DirEntry` stand-in whose method named `fail_method` raises an
    OSError naming the entry's path, when the entry is called `fail_name`."""

    def __init__(
        self, real: os.DirEntry[str], fail_name: str, fail_method: str
    ) -> None:
        self._real = real
        self._fail_name = fail_name
        self._fail_method = fail_method
        self.name = real.name
        self.path = real.path

    def _maybe_fail(self, method: str) -> None:
        if self.name == self._fail_name and method == self._fail_method:
            raise OSError(f"synthetic stat failure for {self.path}")

    def is_symlink(self) -> bool:
        self._maybe_fail("is_symlink")
        return self._real.is_symlink()

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        self._maybe_fail("is_file")
        return self._real.is_file(follow_symlinks=follow_symlinks)

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        self._maybe_fail("is_dir")
        return self._real.is_dir(follow_symlinks=follow_symlinks)


@pytest.mark.parametrize("fail_method", ["is_symlink", "is_dir", "is_file"])
def test_entry_that_fails_to_stat_is_a_redacted_finding_not_a_traceback(
    fail_method: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dies on: the per-entry `is_symlink`/`is_dir`/`is_file` calls left
    outside a `try` (the OSError propagates, and its text names the needle
    file), or the finding for such an entry using the raw path.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {"ok.md": "fine\n", f"{_NEEDLE}.md": "clean\n"})
    real_scandir = os.scandir

    class _Scan:
        def __init__(self, path: str) -> None:
            self._inner = real_scandir(path)

        def __enter__(self) -> list[_ProxyEntry]:
            return [
                _ProxyEntry(entry, f"{_NEEDLE}.md", fail_method)
                for entry in self._inner.__enter__()
            ]

        def __exit__(self, *exc: object) -> None:
            self._inner.__exit__(*exc)

    monkeypatch.setattr(os, "scandir", _Scan)

    code, out, err = _run(capsys, root)

    assert code == 1
    assert sorted(_kinds(err)) == ["encumbered_path", "unreadable"]
    assert _NEEDLE not in out + err


@_needs_non_root
def test_needle_named_unreadable_file_is_redacted_everywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: the unreadable finding's detail carrying `str(exc)` (an
    OSError's text includes the file name), or its subject being the raw path.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {f"{_NEEDLE}.md": "clean\n"})
    locked = root / f"{_NEEDLE}.md"
    locked.chmod(0o000)
    try:
        assert not os.access(locked, os.R_OK), "the file is still readable"
        code, out, err = _run(capsys, root)
    finally:
        locked.chmod(0o644)

    assert code == 1
    assert sorted(_kinds(err)) == ["encumbered_path", "unreadable"]
    assert _NEEDLE not in out + err


@_needs_symlinks
def test_needle_named_symlink_is_a_path_finding_and_a_link_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dies on: the link branch running before the path check (no
    `encumbered_path`), or the link finding using the raw path as subject.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(tmp_path, "site", {"ok.md": "fine\n"})
    (root / f"{_NEEDLE}-link").symlink_to(root / "ok.md")

    code, out, err = _run(capsys, root)

    assert code == 1
    assert sorted(_kinds(err)) == ["encumbered_path", "link"]
    assert _NEEDLE not in out + err


# --- structured API --------------------------------------------------------


def test_check_trees_returns_sorted_findings_with_the_documented_kinds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dies on: `check_trees` returning `tuple(findings)` unsorted (the walk
    visits `c.md`, then `b/`, then `a/`), `Finding` losing `order=True`, or
    `check_trees` returning a list instead of a tuple.
    """
    _use_match_file(monkeypatch, tmp_path)
    root = _tree(
        tmp_path,
        "site",
        {
            "c.md": f"{_NEEDLE}\n",
            "b/inner.md": f"{_NEEDLE}\n",
            "a/inner.md": f"{_NEEDLE}\n",
        },
    )

    findings = check_site.check_trees([root], repo_root=REPO_ROOT)

    assert isinstance(findings, tuple)
    assert len(findings) == 3
    assert all(isinstance(finding, Finding) for finding in findings)
    assert all(finding.kind is FindingKind.ENCUMBERED_CONTENT for finding in findings)
    assert list(findings) == sorted(findings)
    assert [finding.subject for finding in findings] == [
        str(root / name) for name in ("a/inner.md", "b/inner.md", "c.md")
    ]
