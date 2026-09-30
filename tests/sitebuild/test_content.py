"""Content resolution, discovery and annotation stripping (1.1-1.8, 2.11), part 1."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import pytest
from scripts.sitebuild import model
from scripts.sitebuild.content import (
    ContentDirMissing,
    discover,
    resolve_content_dir,
    strip_annotation,
)
from scripts.sitebuild.model import Asset, ContentSource, ResolvedContent

from tests.sitebuild.conftest import copy_fixture_tree

FIXTURE = Path(__file__).parent / "fixtures" / "site"

FIXTURE_PAGES = (
    "get-started/first-run.md",
    "get-started/install.md",
    "guides/nested/deep.md",
    "index.md",
    "llms/prompts.md",
    "reference/cli.md",
    "why.md",
)
FIXTURE_ASSETS = ("images/diagram.svg",)


def _write(root: Path, rel: str, text: str = "x\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode())
    return path


def _tree_hash(root: Path) -> str:
    """Hash ``root`` itself and every path, mode, mtime and file byte under it."""
    digest = hashlib.sha256()
    root_info = root.lstat()
    entries: list[str] = [f".|{root_info.st_mode:o}|{root_info.st_mtime_ns}"]
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        for name in [*dirnames, *filenames]:
            path = Path(dirpath) / name
            info = path.lstat()
            record = f"{path.relative_to(root).as_posix()}|{info.st_mode:o}"
            record += f"|{info.st_mtime_ns}"
            if stat.S_ISLNK(info.st_mode):
                record += f"|->{os.readlink(path)}"
            elif stat.S_ISREG(info.st_mode):
                record += f"|{hashlib.sha256(path.read_bytes()).hexdigest()}"
            entries.append(record)
    for record in sorted(entries):
        digest.update(record.encode() + b"\n")
    return digest.hexdigest()


def _dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Three distinct existing directories: option, environment, default."""
    option = tmp_path / "opt"
    env = tmp_path / "env"
    default = tmp_path / "repo" / "website" / "content"
    for directory in (option, env, default):
        directory.mkdir(parents=True)
    return option, env, default


# --- resolution (1.1, 1.2) ---------------------------------------------------


def test_resolution_uses_the_option_when_all_three_are_set(tmp_path: Path) -> None:
    """The option beats the environment and the default (1.1).

    Dies on: `resolve_content_dir` consulting the environment or the default
    before the option.
    """
    option, env, _default = _dirs(tmp_path)
    environ = {model.CONTENT_ENV_VAR: str(env)}
    resolved = resolve_content_dir(option, environ, tmp_path / "repo")
    assert resolved == ResolvedContent(option, ContentSource.OPTION)


def test_resolution_option_beats_the_default_alone(tmp_path: Path) -> None:
    """Option plus default, no environment: the option (1.1).

    Dies on: `resolve_content_dir` returning the default whenever it exists,
    ahead of the option.
    """
    option, _env, _default = _dirs(tmp_path)
    resolved = resolve_content_dir(option, {}, tmp_path / "repo")
    assert resolved == ResolvedContent(option, ContentSource.OPTION)


def test_resolution_environment_beats_the_default(tmp_path: Path) -> None:
    """Environment plus default, no option: the environment (1.1).

    Dies on: `resolve_content_dir` checking the default before the
    environment variable.
    """
    _option, env, _default = _dirs(tmp_path)
    resolved = resolve_content_dir(
        None, {model.CONTENT_ENV_VAR: str(env)}, tmp_path / "repo"
    )
    assert resolved == ResolvedContent(env, ContentSource.ENVIRONMENT)


def test_resolution_uses_the_environment_when_no_default_exists(tmp_path: Path) -> None:
    """The environment variable alone, with no default directory (1.1).

    Dies on: `resolve_content_dir` ignoring `environ` (always falling to the
    default).
    """
    env = tmp_path / "env"
    env.mkdir()
    resolved = resolve_content_dir(
        None, {model.CONTENT_ENV_VAR: str(env)}, tmp_path / "repo"
    )
    assert resolved == ResolvedContent(env, ContentSource.ENVIRONMENT)


def test_resolution_falls_back_to_the_repository_default(tmp_path: Path) -> None:
    """Neither option nor variable: `<repo>/website/content` (1.1).

    Dies on: changing the default path literal (for example to
    `repo_root / "content"`).
    """
    _option, _env, default = _dirs(tmp_path)
    unrelated = {"PATH": "/usr/bin", "OTHER": str(tmp_path / "opt")}
    resolved = resolve_content_dir(None, unrelated, tmp_path / "repo")
    assert resolved == ResolvedContent(default, ContentSource.DEFAULT)


def test_resolution_treats_an_empty_variable_as_unset(tmp_path: Path) -> None:
    """A set-but-empty variable falls through to the default (1.1).

    Dies on: testing `CONTENT_ENV_VAR in environ` instead of its truthiness.
    """
    _option, _env, default = _dirs(tmp_path)
    resolved = resolve_content_dir(None, {model.CONTENT_ENV_VAR: ""}, tmp_path / "repo")
    assert resolved == ResolvedContent(default, ContentSource.DEFAULT)


def test_missing_option_names_path_and_source_without_falling_through(
    tmp_path: Path,
) -> None:
    """A missing option dir fails naming both, though env and default exist (1.2).

    Dies on: `resolve_content_dir` skipping a non-existent option and taking the
    next source, or a message that omits the path or the source.
    """
    _option, env, _default = _dirs(tmp_path)
    missing = tmp_path / "nowhere"
    with pytest.raises(ContentDirMissing) as caught:
        resolve_content_dir(
            missing, {model.CONTENT_ENV_VAR: str(env)}, tmp_path / "repo"
        )
    assert caught.value.resolved == ResolvedContent(missing, ContentSource.OPTION)
    message = str(caught.value)
    assert str(missing) in message
    assert ContentSource.OPTION.value in message
    assert ContentSource.ENVIRONMENT.value not in message


def test_missing_environment_dir_names_path_and_source(tmp_path: Path) -> None:
    """A missing environment dir fails naming both, though the default exists (1.2).

    Dies on: a message that names the source by a fixed label instead of the
    resolved `ContentSource`, or a fall-through to the default.
    """
    _option, _env, _default = _dirs(tmp_path)
    missing = tmp_path / "gone"
    with pytest.raises(ContentDirMissing) as caught:
        resolve_content_dir(
            None, {model.CONTENT_ENV_VAR: str(missing)}, tmp_path / "repo"
        )
    assert caught.value.resolved == ResolvedContent(missing, ContentSource.ENVIRONMENT)
    message = str(caught.value)
    assert str(missing) in message
    assert ContentSource.ENVIRONMENT.value in message
    assert ContentSource.OPTION.value not in message


def test_missing_default_dir_names_path_and_source(tmp_path: Path) -> None:
    """A missing default dir fails naming both (1.2).

    Dies on: dropping `source` from the message, or building the default path
    without `website/content`.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    expected = repo / "website" / "content"
    with pytest.raises(ContentDirMissing) as caught:
        resolve_content_dir(None, {}, repo)
    assert caught.value.resolved == ResolvedContent(expected, ContentSource.DEFAULT)
    message = str(caught.value)
    assert str(expected) in message
    assert ContentSource.DEFAULT.value in message


def test_a_file_where_the_directory_should_be_is_missing(tmp_path: Path) -> None:
    """A path that exists but is not a directory is refused (1.2).

    Dies on: replacing `is_dir()` with `exists()` in `resolve_content_dir`.
    """
    a_file = _write(tmp_path, "notadir.txt")
    assert a_file.exists()
    with pytest.raises(ContentDirMissing) as caught:
        resolve_content_dir(a_file, {}, tmp_path)
    assert caught.value.resolved == ResolvedContent(a_file, ContentSource.OPTION)


# --- discovery (1.3, 1.4, 1.5, 2.11) -----------------------------------------


def test_fixture_discovery_yields_exactly_the_expected_sets() -> None:
    """The fixture tree gives its literal page and asset sets (1.4, 1.5).

    Dies on: dropping the `_`/`.` exclusion (the `_notes.md`, `_private` and
    `.editor-state` species then appear), or dropping the draft-agnostic page
    rule (the drafted `reference/cli.md` is a candidate here).
    """
    found = discover(FIXTURE)
    assert found.pages == FIXTURE_PAGES
    assert found.assets == tuple(Asset(rel, FIXTURE / rel) for rel in FIXTURE_ASSETS)
    assert found.problems == ()
    # The excluded species really exist on disk, so their absence means something.
    for rel in ("_notes.md", "_private/secret.md", ".editor-state"):
        assert (FIXTURE / rel).is_file()


def test_underscore_and_dot_components_are_excluded_with_their_subtrees(
    tmp_path: Path,
) -> None:
    """`_` and `.` prefixed files and directories vanish with everything below (1.4).

    Dies on: testing only the last path component instead of every component,
    or skipping the prefix test for directories (their subtree is then walked).
    """
    root = tmp_path / "c"
    for rel in (
        "keep.md",
        "sub/keep.md",
        "sub/data.csv",
        "_file.md",
        "_dir/nested/x.md",
        "_dir/y.png",
        ".hidden/z.md",
        ".hidden/_w.md",
        "sub/_inner/deep/q.md",
        "sub/.dotdir/r.txt",
        "sub/.dotfile",
        "sub/_under.png",
    ):
        _write(root, rel)
    found = discover(root)
    assert found.pages == ("keep.md", "sub/keep.md")
    assert [asset.path for asset in found.assets] == ["sub/data.csv"]
    assert found.problems == ()


def test_prefix_test_is_on_the_name_start_only(tmp_path: Path) -> None:
    """Names merely containing `_` or `.` (a `.md` suffix, `a_b`) stay included (1.4).

    Dies on: replacing `startswith` with `in` in the exclusion test.
    """
    root = tmp_path / "c"
    for rel in ("a_b.md", "my.notes.md", "d_1/e.f.txt"):
        _write(root, rel)
    found = discover(root)
    assert found.pages == ("a_b.md", "my.notes.md")
    assert [asset.path for asset in found.assets] == ["d_1/e.f.txt"]


def test_assets_keep_their_relative_path_and_source(tmp_path: Path) -> None:
    """Every non-markdown file is an `Asset` at its relative POSIX path (1.5).

    Dies on: flattening `Asset.path` to the file name, using a path relative to
    the current directory, pointing `source` anywhere but the file, testing
    `".md" in name` instead of `endswith` (`backup.md.bak` becomes a page), or
    matching the suffix case-insensitively (`data.MD` becomes a page).
    """
    root = tmp_path / "c"
    _write(root, "images/deep/pic.svg")
    _write(root, "notes.txt")
    _write(root, "data.MD")
    _write(root, "backup.md.bak")
    _write(root, "page.md")
    found = discover(root)
    assert found.assets == (
        Asset("backup.md.bak", root / "backup.md.bak"),
        Asset("data.MD", root / "data.MD"),
        Asset("images/deep/pic.svg", root / "images" / "deep" / "pic.svg"),
        Asset("notes.txt", root / "notes.txt"),
    )
    assert found.pages == ("page.md",)


def test_reserved_root_names_are_reported_and_not_carried(tmp_path: Path) -> None:
    """Root `llms.txt` / `llms-full.txt` are problems, not assets (2.11).

    Dies on: emptying the reserved-name check (they become assets), reporting
    without excluding them from `assets`, or matching by the `llms` prefix
    (`llms-notes.txt` and `llms.txt.bak` are then reported).
    """
    root = tmp_path / "c"
    _write(root, "llms.txt")
    _write(root, "llms-full.txt")
    _write(root, "llms-notes.txt")
    _write(root, "llms.txt.bak")
    _write(root, "index.md")
    found = discover(root)
    assert [p.path for p in found.problems] == ["llms-full.txt", "llms.txt"]
    for problem in found.problems:
        assert problem.where == ""
        assert "reserved" in problem.message
        assert problem.path in problem.render()
    assert [asset.path for asset in found.assets] == ["llms-notes.txt", "llms.txt.bak"]
    assert found.pages == ("index.md",)


def test_reserved_names_below_the_root_are_ordinary_assets(tmp_path: Path) -> None:
    """The same names in a subdirectory are carried as assets, no problem (2.11).

    Dies on: matching reserved names by file name anywhere instead of at the
    root only.
    """
    root = tmp_path / "c"
    _write(root, "sub/llms.txt")
    _write(root, "sub/deeper/llms-full.txt")
    found = discover(root)
    assert found.problems == ()
    assert [asset.path for asset in found.assets] == [
        "sub/deeper/llms-full.txt",
        "sub/llms.txt",
    ]


def test_symlinks_are_problems_and_never_followed(tmp_path: Path) -> None:
    """A symlink anywhere in an included tree is a problem and is not entered (2.11).

    Dies on: dropping the symlink branch (no problem is reported, `alias.md`
    becomes a page and the other links become assets).
    """
    target_dir = tmp_path / "outside"
    _write(target_dir, "linked-page.md")
    real_file = _write(tmp_path, "outside-file.md")
    root = tmp_path / "c"
    _write(root, "index.md")
    _write(root, "guides/real.md")
    (root / "alias.md").symlink_to(real_file)
    (root / "guides" / "dirlink").symlink_to(target_dir, target_is_directory=True)
    (root / "guides" / "asset-link.png").symlink_to(real_file)
    (root / "dangling.txt").symlink_to(tmp_path / "does-not-exist")
    found = discover(root)
    assert [p.path for p in found.problems] == [
        "alias.md",
        "dangling.txt",
        "guides/asset-link.png",
        "guides/dirlink",
    ]
    for problem in found.problems:
        assert problem.where == ""
        assert "symbolic link" in problem.message
    assert found.pages == ("guides/real.md", "index.md")
    assert found.assets == ()


def test_symlinks_under_excluded_names_are_still_reported(tmp_path: Path) -> None:
    """A symlink named `_x`/`.x`, or inside a `_`/`.` directory, is reported (2.11).

    Nothing else beneath an excluded directory becomes a page or an asset (1.4).

    Dies on: testing the `_`/`.` prefix before the symlink check (the five
    links go unreported), or not walking excluded directories for links.
    """
    target = _write(tmp_path, "target.md")
    root = tmp_path / "c"
    _write(root, "index.md")
    _write(root, "_dir/nested/x.md")
    _write(root, "_dir/y.png")
    _write(root, ".hidden/z.md")
    _write(root, ".hidden/deep/w.png")
    (root / "_link").symlink_to(target)
    (root / ".dotlink").symlink_to(target)
    (root / "_dir" / "inner-link").symlink_to(target)
    (root / ".hidden" / "inner-link").symlink_to(target)
    (root / "_dir" / "nested" / "deep-link").symlink_to(target)
    found = discover(root)
    assert [p.path for p in found.problems] == [
        ".dotlink",
        ".hidden/inner-link",
        "_dir/inner-link",
        "_dir/nested/deep-link",
        "_link",
    ]
    assert found.pages == ("index.md",)
    assert found.assets == ()


def test_a_reserved_name_that_is_a_directory_is_reported_not_entered(
    tmp_path: Path,
) -> None:
    """A root directory named `llms.txt` is reported and yields no page or asset.

    A symlink inside it is still reported (2.11).

    Dies on: applying the reserved check to files only (its `inner.png`
    becomes an asset and no problem is reported for the directory), or not
    queueing the reserved directory for the symlink walk (`inner-link` goes
    unreported).
    """
    target = _write(tmp_path, "target.md")
    root = tmp_path / "c"
    _write(root, "llms.txt/inner.png")
    (root / "llms.txt" / "inner-link").symlink_to(target)
    _write(root, "llms-full.txt/deeper/inner.md")
    _write(root, "sub/llms.txt/kept.png")
    found = discover(root)
    assert [p.path for p in found.problems] == [
        "llms-full.txt",
        "llms.txt",
        "llms.txt/inner-link",
    ]
    assert [a.path for a in found.assets] == ["sub/llms.txt/kept.png"]
    assert found.pages == ()


def test_a_directory_named_like_a_page_is_walked_not_a_page(tmp_path: Path) -> None:
    """A directory `notes.md/` is descended into and is not itself a page (1.5).

    Dies on: testing the `.md` suffix before the directory check (`notes.md`
    becomes a page and its contents are never found).
    """
    root = tmp_path / "c"
    _write(root, "notes.md/inner.png")
    _write(root, "notes.md/inner.md")
    found = discover(root)
    assert found.pages == ("notes.md/inner.md",)
    assert found.assets == (
        Asset("notes.md/inner.png", root / "notes.md" / "inner.png"),
    )
    assert found.problems == ()


@pytest.mark.skipif(os.geteuid() == 0, reason="root can list a mode-000 directory")
def test_an_unreadable_excluded_directory_is_skipped(tmp_path: Path) -> None:
    """Unlistable excluded directories are skipped and the rest is unchanged.

    The locked directories are root-level `_locked/` and `.locked/`, a
    `_dir/nested/` whose own name has no prefix, and a reserved `llms.txt/`
    (still reported). The walk is last-in, first-out over each sorted
    listing, so `2024/` and `Guides/` are processed after `llms.txt/`,
    `_locked/` and `_dir/nested/` (`.locked/` sorts first and is processed
    last): each page must still appear.

    Dies on: dropping the `except OSError` around `os.scandir` (`PermissionError`
    propagates); testing the directory's own name rather than the inherited
    flag (`_dir/nested/` and `llms.txt/` raise); `break` for `continue` in the
    except (`2024/p.md` and `Guides/g.md` vanish).
    """
    root = tmp_path / "c"
    _write(root, "index.md")
    _write(root, "img/a.png")
    _write(root, "2024/p.md")
    _write(root, "Guides/g.md")
    _write(root, "_locked/x.md")
    _write(root, ".locked/y.md")
    _write(root, "_dir/nested/z.md")
    _write(root, "llms.txt/inner.png")
    locked = (
        root / "_locked",
        root / ".locked",
        root / "_dir" / "nested",
        root / "llms.txt",
    )
    for directory in locked:
        directory.chmod(0o000)
    try:
        for directory in locked:
            with pytest.raises(PermissionError):
                os.scandir(directory)  # the precondition: really unreadable
        found = discover(root)
    finally:
        for directory in locked:
            directory.chmod(0o755)
    assert found.pages == ("2024/p.md", "Guides/g.md", "index.md")
    assert [a.path for a in found.assets] == ["img/a.png"]
    assert [p.path for p in found.problems] == ["llms.txt"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can list a mode-000 directory")
def test_an_unreadable_included_directory_raises(tmp_path: Path) -> None:
    """An unlistable included directory is an error, never a silent omission.

    Dies on: swallowing `OSError` for included directories (`guides/` and its
    page vanish and `discover` returns normally).
    """
    root = tmp_path / "c"
    _write(root, "index.md")
    _write(root, "guides/page.md")
    guides = root / "guides"
    guides.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            os.scandir(guides)  # the precondition: it really is unreadable
        with pytest.raises(PermissionError):
            discover(root)
    finally:
        guides.chmod(0o755)


def test_a_reserved_name_that_is_a_symlink_is_one_problem(tmp_path: Path) -> None:
    """A symlink named `llms.txt` at the root yields exactly one problem (2.11).

    Dies on: reporting the reserved name and the symlink as two problems, or
    carrying the link as an asset.
    """
    target = _write(tmp_path, "target.txt")
    root = tmp_path / "c"
    root.mkdir()
    (root / "llms.txt").symlink_to(target)
    found = discover(root)
    assert len(found.problems) == 1
    assert found.problems[0].path == "llms.txt"
    assert found.assets == ()


def test_results_are_sorted_whatever_order_the_directory_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pages, assets and problems come back sorted by path (determinism).

    The walk appends a directory's own files before descending, so its raw
    order puts `z.md` ahead of `a/b.md` and `z.png` ahead of `m/n.png`. The
    directory listing is also reversed here, though the final sort makes that
    second dimension invisible.

    Dies on: deleting the final `sorted(...)` of pages, assets or problems
    (problems: `a/x1` is found after the root's links in walk order).
    """
    root = tmp_path / "c"
    for rel in ("a/b.md", "a.md", "z.md", "m/n.png", "m.png", "k.txt", "z.png"):
        _write(root, rel)
    target = _write(tmp_path, "t.txt")
    for name in ("s2", "s1", "s3", "a/x1"):
        (root / name).symlink_to(target)

    real_scandir = os.scandir

    def reversed_scandir(
        path: str | os.PathLike[str],
    ) -> AbstractContextManager[Iterator[os.DirEntry[str]]]:
        with real_scandir(path) as it:
            entries = sorted(it, key=lambda e: e.name, reverse=True)
        return nullcontext(iter(entries))

    monkeypatch.setattr(os, "scandir", reversed_scandir)
    found = discover(root)
    assert found.pages == ("a.md", "a/b.md", "z.md")
    assert [a.path for a in found.assets] == [
        "k.txt",
        "m.png",
        "m/n.png",
        "z.png",
    ]
    assert [p.path for p in found.problems] == ["a/x1", "s1", "s2", "s3"]


# --- read-only (1.3) ---------------------------------------------------------


def test_tree_hash_sees_a_byte_a_mode_and_an_added_file(tmp_path: Path) -> None:
    """The hash helper reacts to content, mode, mtime and new-entry changes (control).

    Dies on: dropping the byte digest, the mode, the mtime or the directory
    entries from `_tree_hash` (mutations of this helper, not of production code).
    """
    root = copy_fixture_tree(FIXTURE, tmp_path)
    base = _tree_hash(root)
    assert _tree_hash(root) == base
    page = root / "why.md"
    original_bytes = page.read_bytes()
    original_stat = page.stat()
    page.write_bytes(original_bytes.replace(b"fixture", b"fixturf", 1))
    os.utime(page, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert _tree_hash(root) != base  # same size, same mtime: bytes alone differ
    page.write_bytes(original_bytes)
    os.utime(page, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert _tree_hash(root) == base
    page.chmod(original_stat.st_mode & 0o777 ^ 0o200)
    assert _tree_hash(root) != base
    page.chmod(original_stat.st_mode & 0o777)
    assert _tree_hash(root) == base
    os.utime(page, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 10**9))
    assert _tree_hash(root) != base  # only the mtime moved
    os.utime(page, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert _tree_hash(root) == base
    (root / "empty-dir").mkdir()
    assert _tree_hash(root) != base  # a directory with no files in it
    (root / "empty-dir").rmdir()
    _write(root, "added.txt")
    assert _tree_hash(root) != base


def test_resolution_discovery_and_strip_leave_the_tree_untouched(
    tmp_path: Path,
) -> None:
    """A byte hash of the content dir is unchanged after all three steps (1.3).

    Dies on: `discover` touching a file, chmod-ing a file or the content root,
    rewriting a file with its own bytes, or creating and unlinking a file in
    the root (each run over this test's tmp copy).
    """
    root = copy_fixture_tree(FIXTURE, tmp_path)
    (root / "why.md").chmod(0o444)
    (root / "guides").chmod(0o555)
    try:
        before = _tree_hash(root)
        resolved = resolve_content_dir(root, {}, tmp_path)
        found = discover(resolved.path)
        assert found.pages == FIXTURE_PAGES  # the walk really ran
        for rel in found.pages:
            strip_annotation((root / rel).read_bytes().decode())
        assert _tree_hash(root) == before
    finally:
        (root / "guides").chmod(0o755)


# --- strip_annotation (1.6, 1.7, 1.8) ----------------------------------------


def test_strip_removes_a_trailing_block_and_keeps_the_last_newline() -> None:
    """The block goes; the newline ending the last content line stays (1.6, 1.8).

    Dies on: keeping `text[:i]` (drops that newline) or `text[: i + 2]` (keeps
    a blank line).
    """
    text = "title\n\nbody line\n\n---\nAnnotations: 0,1 SHA\n&Claude: note\n@Josh: \n"
    assert strip_annotation(text) == "title\n\nbody line\n"


def test_strip_of_a_page_that_is_only_a_block_keeps_one_newline() -> None:
    """A marker at index 0 is still a marker: the kept text is the lone newline (1.6).

    Dies on: testing `i <= 0` (or `not i`) instead of `i < 0` for "no marker".
    """
    assert strip_annotation("\n\n---\nAnnotations: x\n") == "\n"


def test_strip_without_a_marker_returns_the_text_unchanged() -> None:
    """No annotation block: identical text, including an unterminated last line (1.6).

    Dies on: appending a newline, stripping whitespace, or normalising line
    endings (CRLF to LF) when no marker is found.
    """
    text = "just text\n\nno newline at end"
    assert strip_annotation(text) == text
    assert strip_annotation("") == ""
    assert strip_annotation("a\r\nb\r\n") == "a\r\nb\r\n"


def test_strip_keeps_a_plain_rule_and_a_near_miss_marker() -> None:
    """A `---` rule not followed by `Annotations:` survives (1.7).

    The near misses are a rule followed by a different label, `Annotations:`
    without the blank line before the rule, and an unfenced `---` with the
    word after a blank line.

    Dies on: matching on `"\\n\\n---\\n"` alone (no `Annotations:`), or on
    `"\\n---\\nAnnotations:"` (no blank line).
    """
    rule = "a\n\n---\n\nb\n"
    assert strip_annotation(rule) == rule
    other_label = "a\n\n---\nNotes: kept\n"
    assert strip_annotation(other_label) == other_label
    no_blank_line = "a\n---\nAnnotations: kept\n"
    assert strip_annotation(no_blank_line) == no_blank_line
    label_after_blank = "a\n\n---\n\nAnnotations: kept\n"
    assert strip_annotation(label_after_blank) == label_after_blank


def test_strip_keeps_a_rule_that_precedes_the_block() -> None:
    """A plain rule earlier in the page is kept, the trailing block goes (1.6, 1.7).

    Dies on: cutting at the first `---` rather than at the marker.
    """
    text = "intro\n\n---\n\nmiddle\n\n---\nAnnotations: 1\n&Claude: c\n"
    assert strip_annotation(text) == "intro\n\n---\n\nmiddle\n"


def test_strip_with_two_markers_removes_from_the_last() -> None:
    """With two markers only the final block goes (1.6).

    Dies on: `text.find` instead of `text.rfind` (the first marker's text and
    everything after is cut).
    """
    text = "one\n\n---\nAnnotations: A\nbetween A and B\n\n---\nAnnotations: B\ntail\n"
    assert strip_annotation(text) == "one\n\n---\nAnnotations: A\nbetween A and B\n"


def test_strip_leaves_the_remainder_byte_for_byte() -> None:
    """The kept text keeps CRLF, tabs, trailing spaces and non-ASCII exactly (1.6).

    Dies on: `.rstrip()`, `.splitlines()`/`join`, or newline translation
    applied to the kept text.
    """
    kept = "café — \U0001f3c3\r\n  \ttabbed \t \r\n\n\n   trailing spaces   \n"
    text = kept + "\n---\nAnnotations: z\n﻿&Claude: é\n"
    result = strip_annotation(text)
    assert result == kept
    assert result.encode() == kept.encode()


def test_strip_of_a_fixture_page_removes_only_its_block() -> None:
    """On the fixture's Why page the block goes and the body stays (1.6-1.8).

    Dies on: cutting at the plain rule instead of the marker (the paragraph
    after the rule goes), keeping `text[:i]` (the final `computation).` blank
    line goes), or ignoring the marker.
    """
    raw = (FIXTURE / "why.md").read_bytes().decode()
    assert "ANNOTSENTINELAMBER" in raw
    stripped = strip_annotation(raw)
    assert "ANNOTSENTINELAMBER" not in stripped
    assert "Annotations:" not in stripped
    assert raw.startswith(stripped)
    assert "\n---\n\nThe `[load]`" in stripped  # the plain rule before the link
    assert stripped.endswith("computation).\n\n")
    assert len(raw) > len(stripped)


def test_strip_of_every_fixture_page_is_a_prefix_without_the_sentinel() -> None:
    """Every fixture page with an annotation block loses it and only it (1.8).

    Dies on: `strip_annotation` returning its input unchanged.
    """
    stripped_any = 0
    for rel in FIXTURE_PAGES:
        raw = (FIXTURE / rel).read_bytes().decode()
        stripped = strip_annotation(raw)
        assert raw.startswith(stripped)
        assert "ANNOTSENTINELAMBER" not in stripped
        if len(stripped) < len(raw):
            stripped_any += 1
            assert raw[len(stripped) :].startswith("\n---\nAnnotations:")
    assert stripped_any >= 2, "the fixture no longer carries annotation blocks"
