"""Content resolution, discovery, stripping and validation (1.1-1.8, 2.1-2.9, 2.11).

Part 1 covers resolution, discovery and stripping. Part 2 covers frontmatter
and site-level validation, `load_content` and `count_included_pages`.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

import pytest
import yaml
from scripts.sitebuild import model
from scripts.sitebuild.content import (
    ContentDirMissing,
    count_included_pages,
    discover,
    load_content,
    resolve_content_dir,
    strip_annotation,
)
from scripts.sitebuild.model import (
    Asset,
    ContentSource,
    HeroAction,
    Problem,
    ResolvedContent,
)

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


# =============================================================================
# Part 2: frontmatter and site-level validation (2.1, 2.3-2.9)
# =============================================================================

_VALID = {
    "title": "Guide",
    "description": "A guide.",
    "section": "Guides",
    "order": "1",
}
_HOME = {
    "title": "Home",
    "description": "The home page.",
    "section": "Home",
    "order": "1",
}


NO_HOME = (
    "index.md: no home page: the content root needs an index.md that is not a draft"
)


def _fm(base: dict[str, str], **changes: str | None) -> str:
    """A page: `base` frontmatter with `changes` applied, ``None`` dropping a key."""
    merged: dict[str, str | None] = {**base, **changes}
    lines = [f"{key}: {value}" for key, value in merged.items() if value is not None]
    return "---\n" + "\n".join(lines) + "\n---\n\nBody.\n"


def _site(root: Path, pages: dict[str, str] | None = None) -> Path:
    """A content dir with a valid home page plus ``pages`` (which may replace it)."""
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in {"index.md": _fm(_HOME), **(pages or {})}.items():
        _write(root, rel, text)
    return root


def _lines(root: Path) -> list[str]:
    """The rendered problem lines of a load that must fail."""
    content, problems = load_content(root)
    assert content is None
    assert problems  # the failure carries its problems
    return [problem.render() for problem in problems]


def test_the_fixture_loads_into_exactly_its_six_pages() -> None:
    """The valid fixture: six pages sorted by path, no draft or `_` page (2.1, 2.4)

    Dies on: `load_content` keeping the drafted `reference/cli.md`, re-sorting the
    pages by title, or dropping the assets.
    """
    content, problems = load_content(FIXTURE)
    assert problems == ()
    assert content is not None
    assert content.root == FIXTURE
    assert [page.path for page in content.pages] == [
        "get-started/first-run.md",
        "get-started/install.md",
        "guides/nested/deep.md",
        "index.md",
        "llms/prompts.md",
        "why.md",
    ]
    assert [asset.path for asset in content.assets] == ["images/diagram.svg"]
    assert [(page.title, page.section, page.order) for page in content.pages] == [
        ("First run", "Get started", 2),
        ("Install", "Get started", 1),
        ("Deep guide", "Guides", 1),
        ("Fixture home", "Home", 1),
        ("Prompts", "Working with LLMs", 1),
        ("Why a fixture", "Why", 1),
    ]


def test_the_fixture_home_page_carries_its_hero_fields() -> None:
    """The home page's hero fields come through typed; other pages carry none (2.3).

    Dies on: dropping the `primary` default (the second action must be
    False), mapping `label` and `href` to each other, or keeping `hero_tagline`
    as an empty string instead of None.
    """
    content, _ = load_content(FIXTURE)
    assert content is not None
    home = next(page for page in content.pages if page.path == "index.md")
    assert home.hero_title == "Fixture hero title"
    assert home.hero_tagline is None
    assert home.hero_actions == (
        HeroAction("Read the story", "https://example.org/story", True),
        HeroAction("Install", "get-started/install/", False),
    )
    others = [page for page in content.pages if page.path != "index.md"]
    assert len(others) == 5
    assert all(
        (page.hero_title, page.hero_tagline, page.hero_actions) == (None, None, None)
        for page in others
    )


def test_staged_text_and_body_split_at_the_closing_fence() -> None:
    """`staged_text` is the file minus its annotation block; `body` follows the fence.

    Dies on: `staged_text` keeping the annotation block, `body` keeping the
    frontmatter, an off-by-one in the body offset, or `staged_text` set to the
    body.
    """
    content, _ = load_content(FIXTURE)
    assert content is not None
    why = next(page for page in content.pages if page.path == "why.md")
    source = (FIXTURE / "why.md").read_bytes().decode()
    assert "\n\n---\nAnnotations:" in source  # the page really has a block
    header = (
        "---\ntitle: Why a fixture\ndescription: The Why page of the fixture site.\n"
        "section: Why\norder: 1\n---\n"
    )
    assert why.staged_text == strip_annotation(source)
    assert why.staged_text.startswith(header)
    assert "Annotations:" not in why.staged_text
    assert why.body == why.staged_text[len(header) :]
    assert why.body.startswith("\n## Why a fixture exists\n")


def test_a_closing_fence_on_the_last_line_leaves_an_empty_body(tmp_path: Path) -> None:
    """A file that ends at its closing fence, with or without a newline (2.1).

    Dies on: an off-by-one in the fence line's length when the body offset is
    computed (the body then keeps the last fence characters).
    """
    root = _site(tmp_path / "c")
    plain = _fm(_VALID).split("\n\nBody.")[0] + "\n"  # ends "---\n"
    _write(root, "a.md", plain)
    _write(root, "b.md", plain.replace("order: 1", "order: 2").removesuffix("\n"))
    content, problems = load_content(root)
    assert problems == ()
    assert content is not None
    bodies = {page.path: page.body for page in content.pages}
    assert bodies["a.md"] == ""
    assert bodies["b.md"] == ""
    assert bodies["index.md"] == "\nBody.\n"


def test_text_fields_are_kept_as_written(tmp_path: Path) -> None:
    """A padded title is valid and stored unchanged; only emptiness is judged (2.1).

    Dies on: storing `value.strip()` instead of the value, or testing
    `len(value)` instead of `value.strip()`.
    """
    root = _site(tmp_path / "c", {"a.md": _fm(_VALID, title='"  Padded  "')})
    content, problems = load_content(root)
    assert problems == ()
    assert content is not None
    assert next(p for p in content.pages if p.path == "a.md").title == "  Padded  "


def test_order_zero_and_negative_are_valid_integers(tmp_path: Path) -> None:
    """`order: 0` and `order: -1` are integers, not absent values (2.1).

    Dies on: testing `not order`, `order > 0` or `order < 1` for validity.
    """
    root = _site(
        tmp_path / "c",
        {"a.md": _fm(_VALID, order="0"), "b.md": _fm(_VALID, order="-1")},
    )
    content, problems = load_content(root)
    assert problems == ()
    assert content is not None
    orders = {page.path: page.order for page in content.pages}
    assert (orders["a.md"], orders["b.md"]) == (0, -1)


# --- one violation class at a time (2.5, 2.9) --------------------------------


@pytest.mark.parametrize("key", ["title", "description", "section", "order"])
def test_a_missing_required_key_names_the_file_and_the_key(
    tmp_path: Path, key: str
) -> None:
    """Each required key, dropped alone, is reported by file and key (2.1, 2.5).

    Dies on: dropping one of the four keys from the required set, or a message with
    an empty `where`.
    """
    root = _site(tmp_path / "c", {"g/p.md": _fm(_VALID, **{key: None})})
    assert _lines(root) == [f"g/p.md: {key}: required key is missing"]


def test_an_unknown_key_is_refused_by_name(tmp_path: Path) -> None:
    """A key outside the contract is reported with its own name (2.5).

    Dies on: ignoring unknown keys, or leaving `where` empty.
    """
    root = _site(tmp_path / "c", {"p.md": _fm(_VALID, colour="red")})
    assert _lines(root) == ["p.md: colour: key is not allowed by the content contract"]


def test_a_template_key_is_an_unknown_key(tmp_path: Path) -> None:
    """`template` is not a content key, on any page, home included (2.5, 3.3).

    Dies on: adding `template` to the allowed set, or exempting the home page.
    """
    root = _site(
        tmp_path / "c",
        {
            "p.md": _fm(_VALID, template="home.html"),
            "index.md": _fm(_HOME, template="home.html"),
        },
    )
    assert _lines(root) == [
        "index.md: template: key is not allowed by the content contract",
        "p.md: template: key is not allowed by the content contract",
    ]


def test_a_non_string_key_is_an_unknown_key(tmp_path: Path) -> None:
    """A YAML key that is not text is reported, rendered as text (2.5).

    Dies on: sorting keys without `key=str` (`TypeError`), putting the raw key in
    `where`, or skipping non-string keys.
    """
    root = _site(
        tmp_path / "c", {"p.md": _fm(_VALID).replace("order: 1\n", "order: 1\n7: x\n")}
    )
    assert _lines(root) == ["p.md: 7: key is not allowed by the content contract"]


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("hero_title", "A title"),
        ("hero_tagline", "A tagline"),
        ("hero_actions", "[{label: L, href: 'https://e.org'}]"),
    ],
)
def test_a_hero_key_off_the_home_page_is_refused(
    tmp_path: Path, key: str, value: str
) -> None:
    """Each hero key is refused on a page that is not the root `index.md` (2.3, 2.5).

    Dies on: dropping one key from the hero set, or allowing hero keys on any page.
    """
    root = _site(tmp_path / "c", {"g/p.md": _fm(_VALID, **{key: value})})
    assert _lines(root) == [f"g/p.md: {key}: hero key is only allowed on index.md"]


def test_a_nested_index_is_not_the_home_page(tmp_path: Path) -> None:
    """`a/index.md` takes no hero key: only the root `index.md` is the home page (2.3).

    Dies on: comparing the file name (`endswith("index.md")`) instead of the path.
    """
    root = _site(tmp_path / "c", {"a/index.md": _fm(_VALID, hero_title="T")})
    assert _lines(root) == [
        "a/index.md: hero_title: hero key is only allowed on index.md"
    ]


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("guides", "'guides'"),
        ('" Guides"', "' Guides'"),
        ("Get", "'Get'"),
        ("Home Why", "'Home Why'"),
        ("Nowhere", "'Nowhere'"),
        ("3", "3"),
        ("[Guides]", "['Guides']"),
    ],
)
def test_a_section_outside_the_canonical_list_is_refused(
    tmp_path: Path, value: str, shown: str
) -> None:
    """A section must equal one of `SECTIONS` exactly, case included (2.1, 2.2, 2.5).

    Dies on: a case-insensitive comparison, a `strip()` before the comparison,
    a substring test (`in` against the joined text), or a message that hides
    the offending value.
    """
    root = _site(tmp_path / "c", {"p.md": _fm(_VALID, section=value)})
    expected = f"p.md: section: {shown} is not a section; use one of: " + ", ".join(
        model.SECTIONS
    )
    assert _lines(root) == [expected]


@pytest.mark.parametrize(
    ("value", "kind"),
    [
        ("true", "bool"),
        ("false", "bool"),
        ("'1'", "str"),
        ("1.0", "float"),
        ("null", "null"),
    ],
)
def test_order_must_be_an_integer_and_never_a_boolean(
    tmp_path: Path, value: str, kind: str
) -> None:
    """`order` accepts an int only; `true` is a bool, not 1 (2.1, 2.5).

    Dies on: `isinstance(order, int)` (accepts `True`), or accepting a float
    (`isinstance(order, (int, float))`).
    """
    root = _site(tmp_path / "c", {"p.md": _fm(_VALID, order=value)})
    assert _lines(root) == [f"p.md: order: must be an integer, not {kind}"]


@pytest.mark.parametrize(
    ("value", "kind"), [("'true'", "str"), ("1", "int"), ("0", "int"), ("null", "null")]
)
def test_draft_must_be_a_boolean(tmp_path: Path, value: str, kind: str) -> None:
    """`draft` accepts true or false only (2.3, 2.5).

    Dies on: skipping the `draft` type check, or widening it to accept an int.
    """
    root = _site(tmp_path / "c", {"p.md": _fm(_VALID, draft=value)})
    assert _lines(root) == [f"p.md: draft: must be true or false, not {kind}"]


@pytest.mark.parametrize("key", ["title", "description"])
@pytest.mark.parametrize(
    ("value", "kind"),
    [('""', "str"), ('"   "', "str"), ("5", "int"), ("null", "null"), ("[a]", "list")],
)
def test_title_and_description_must_be_non_empty_text(
    tmp_path: Path, key: str, value: str, kind: str
) -> None:
    """Empty, blank and non-text title or description values are refused (2.1, 2.5).

    Dies on: dropping `.strip()` (blank text passes), skipping the type test
    (`5` passes), or checking only one of the two keys.
    """
    root = _site(tmp_path / "c", {"p.md": _fm(_VALID, **{key: value})})
    assert _lines(root) == [f"p.md: {key}: must be non-empty text, not {kind}"]


@pytest.mark.parametrize("key", ["hero_title", "hero_tagline"])
@pytest.mark.parametrize("value", ['""', '"  "', "5"])
def test_hero_text_keys_must_be_non_empty_text(
    tmp_path: Path, key: str, value: str
) -> None:
    """A present `hero_title` or `hero_tagline` must be non-empty text (2.3, 2.5).

    Dies on: skipping the check for either key.
    """
    kind = "int" if value == "5" else "str"
    root = _site(tmp_path / "c", {"index.md": _fm(_HOME, **{key: value})})
    assert _lines(root) == [f"index.md: {key}: must be non-empty text, not {kind}"]


def test_one_page_with_five_violations_reports_five_lines(tmp_path: Path) -> None:
    """Every key of one page is judged: five violations on one page, five lines (2.9).

    Dies on: returning after the first violation of a page.
    """
    text = _fm(
        _VALID, title='""', order="true", section="Nope", colour="red", description=None
    )
    root = _site(tmp_path / "c", {"p.md": text})
    assert _lines(root) == [
        "p.md: colour: key is not allowed by the content contract",
        "p.md: description: required key is missing",
        "p.md: order: must be an integer, not bool",
        "p.md: section: 'Nope' is not a section; use one of: "
        + ", ".join(model.SECTIONS),
        "p.md: title: must be non-empty text, not str",
    ]


# --- hero_actions (2.3, 2.5) -------------------------------------------------


def test_valid_hero_actions_load_with_primary_defaulting_to_false(
    tmp_path: Path,
) -> None:
    """A valid action list loads; `primary` defaults to False when absent (2.3).

    Dies on: requiring `primary` (`entry["primary"]`), defaulting it to True, or
    swapping label and href.
    """
    text = _fm(
        _HOME,
        hero_title="Big",
        hero_tagline="Small",
        hero_actions="\n  - label: A\n    href: get-started/install/\n"
        "  - {label: B, href: 'https://e.org/b', primary: true}\n"
        "  - {label: C, href: c/, primary: false}",
    )
    content, problems = load_content(_site(tmp_path / "c", {"index.md": text}))
    assert problems == ()
    assert content is not None
    home = content.pages[0]
    assert (home.hero_title, home.hero_tagline) == ("Big", "Small")
    assert home.hero_actions == (
        HeroAction("A", "get-started/install/", False),
        HeroAction("B", "https://e.org/b", True),
        HeroAction("C", "c/", False),
    )


@pytest.mark.parametrize(
    ("actions", "expected"),
    [
        ("[]", "hero_actions: must be a non-empty list, not list"),
        ("{label: A, href: b/}", "hero_actions: must be a non-empty list, not dict"),
        ("text", "hero_actions: must be a non-empty list, not str"),
        ("null", "hero_actions: must be a non-empty list, not null"),
        ("[oops]", "hero_actions: entry 1 must be a mapping, not str"),
        (
            "[{label: A, href: b/}, 5]",
            "hero_actions: entry 2 must be a mapping, not int",
        ),
        (
            "[{label: A, href: b/, colour: red}]",
            "hero_actions: entry 1: key 'colour' is not one of label, href, primary",
        ),
        (
            "[{label: A, href: b/}, {label: B, href: c/, template: x}]",
            "hero_actions: entry 2: key 'template' is not one of label, href, primary",
        ),
        (
            "[{href: b/}]",
            "hero_actions: entry 1: label must be non-empty text, not null",
        ),
        (
            "[{label: A}]",
            "hero_actions: entry 1: href must be non-empty text, not null",
        ),
        (
            "[{label: '', href: b/}]",
            "hero_actions: entry 1: label must be non-empty text, not str",
        ),
        (
            "[{label: A, href: '  '}]",
            "hero_actions: entry 1: href must be non-empty text, not str",
        ),
        (
            "[{label: 5, href: b/}]",
            "hero_actions: entry 1: label must be non-empty text, not int",
        ),
        (
            "[{label: A, href: b/, primary: 'yes'}]",
            "hero_actions: entry 1: primary must be true or false, not str",
        ),
        (
            "[{label: A, href: b/, primary: 1}]",
            "hero_actions: entry 1: primary must be true or false, not int",
        ),
    ],
)
def test_each_hero_actions_violation_is_one_line_naming_key_and_entry(
    tmp_path: Path, actions: str, expected: str
) -> None:
    """Each malformed `hero_actions` shape gives exactly one line (2.3, 2.5).

    The entry number is 1-based and distinguishes the offending entry.

    Dies on: accepting an empty list, a mapping or a string as the list,
    skipping the per-entry mapping test, allowing an extra entry key (or
    checking only the first entry), not requiring `label` or `href`,
    accepting blank text there, accepting a non-bool `primary` (a truthiness
    test lets `1` through), or numbering entries from 0.
    """
    root = _site(tmp_path / "c", {"index.md": _fm(_HOME, hero_actions=actions)})
    assert _lines(root) == [f"index.md: {expected}"]


def test_hero_actions_reports_every_bad_entry_and_key(tmp_path: Path) -> None:
    """Three bad entries give their lines together, in entry order (2.9).

    Dies on: stopping at the first bad entry, at a non-mapping entry (a bad
    entry follows it), or at the first bad key of one entry (entry 3 carries
    two).
    """
    actions = "[{label: A}, 9, {label: B, href: c/, x: 1, y: 2}]"
    root = _site(tmp_path / "c", {"index.md": _fm(_HOME, hero_actions=actions)})
    assert _lines(root) == [
        "index.md: hero_actions: entry 1: href must be non-empty text, not null",
        "index.md: hero_actions: entry 2 must be a mapping, not int",
        "index.md: hero_actions: entry 3: key 'x' is not one of label, href, primary",
        "index.md: hero_actions: entry 3: key 'y' is not one of label, href, primary",
    ]


def test_a_hero_href_is_not_judged_here(tmp_path: Path) -> None:
    """2.2 checks only that `href` is text; whether it names a page is 2.8's link check.

    Dies on: requiring an `https://` href (the relative one is rejected), or
    requiring a trailing slash or `https://` (the `http://` one is rejected).
    """
    actions = "[{label: A, href: nowhere/}, {label: B, href: 'http://e.org'}]"
    content, problems = load_content(
        _site(tmp_path / "c", {"index.md": _fm(_HOME, hero_actions=actions)})
    )
    assert problems == ()
    assert content is not None
    assert content.pages[0].hero_actions == (
        HeroAction("A", "nowhere/", False),
        HeroAction("B", "http://e.org", False),
    )


# --- frontmatter splitting and YAML errors (2.1, 2.5) ------------------------


def test_a_page_without_frontmatter_is_refused(tmp_path: Path) -> None:
    """A file that does not begin with a `---` line has no frontmatter (2.1).

    Dies on: accepting the opening fence on the second line (`_FENCE not in lines[:2]`).
    """
    root = _site(
        tmp_path / "c",
        {"a.md": "Just prose.\n", "b.md": "\n" + _fm(_VALID), "c.md": ""},
    )
    line = "no frontmatter: the file must begin with a line ---"
    assert _lines(root) == [f"a.md: {line}", f"b.md: {line}", f"c.md: {line}"]


def test_an_unterminated_frontmatter_block_is_refused(tmp_path: Path) -> None:
    """A block with no closing `---` line is refused, even when it parses (2.1).

    Dies on: taking end of file as the closing fence.
    """
    root = _site(tmp_path / "c", {"a.md": "---\ntitle: x\ndescription: y\n"})
    assert _lines(root) == ["a.md: unterminated frontmatter: no closing line ---"]


def test_a_fence_line_must_be_exactly_three_dashes(tmp_path: Path) -> None:
    """`----` or `--- x` opens nothing and closes nothing (2.1).

    Dies on: `startswith("---")` for the opening line (the first page loads) or
    for the closing line (the second page closes early and loads).
    """
    body = "title: x\ndescription: y\nsection: Guides\norder: 1\n"
    root = _site(
        tmp_path / "c",
        {"a.md": "----\n" + body + "---\n", "b.md": "---\n" + body + "--- x\n"},
    )
    assert _lines(root) == [
        "a.md: no frontmatter: the file must begin with a line ---",
        "b.md: unterminated frontmatter: no closing line ---",
    ]


def test_carriage_returns_and_a_byte_order_mark_are_not_a_fence(tmp_path: Path) -> None:
    """A CRLF page and a BOM page have no `---` line, so both are refused (2.1).

    Dies on: splitting lines with `splitlines()` (the CRLF page loads), or
    decoding with `utf-8-sig` (the BOM page loads).
    """
    crlf = _fm(_VALID).replace("\n", "\r\n")
    root = _site(tmp_path / "c", {"a.md": crlf, "b.md": "\ufeff" + _fm(_VALID)})
    line = "no frontmatter: the file must begin with a line ---"
    assert _lines(root) == [f"a.md: {line}", f"b.md: {line}"]


def test_a_non_utf8_page_is_a_problem_naming_the_file(tmp_path: Path) -> None:
    """Bytes that are not UTF-8 give one problem, not an exception (2.1).

    Dies on: decoding with `errors="replace"` (the page loads), or letting
    `UnicodeDecodeError` escape.
    """
    root = _site(tmp_path / "c")
    (root / "bad.md").write_bytes(_fm(_VALID).encode() + b"\xff\xfe\n")
    assert _lines(root) == ["bad.md: file is not UTF-8"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode-000 file")
def test_an_unreadable_page_is_a_problem_naming_the_file(tmp_path: Path) -> None:
    """A page that cannot be opened gives one problem, not an exception (2.5).

    Dies on: letting `PermissionError` escape from `load_content`.
    """
    root = _site(tmp_path / "c", {"locked.md": _fm(_VALID)})
    locked = root / "locked.md"
    locked.chmod(0o000)
    try:
        with pytest.raises(PermissionError):
            locked.read_bytes()  # the precondition: really unreadable
        lines = _lines(root)
    finally:
        locked.chmod(0o644)
    assert lines == ["locked.md: cannot read file: Permission denied"]


def test_a_yaml_syntax_error_renders_line_column_and_problem(tmp_path: Path) -> None:
    """A syntax error is one line: file, file line:col, then the problem (2.1, 2.9).

    The block starts on file line 2, so this error on block line 2 is file
    line 3. The raw PyYAML text spans several lines, and only the one-line
    form reaches the message.

    Dies on: rendering `str(error)` (multi-line, carries the snippet), an
    off-by-one in line or column, forgetting the opening fence's line, or
    dropping the position.
    """
    text = "---\ntitle: ok\ndescription: a: b\nsection: Guides\norder: 1\n---\n"
    root = _site(tmp_path / "c", {"bad.md": text})
    with pytest.raises(yaml.YAMLError) as raised:
        yaml.safe_load(text.split("---\n")[1])
    assert "\n" in str(raised.value)  # the raw text really is multi-line
    lines = _lines(root)
    assert lines == [
        "bad.md: 3:15: invalid frontmatter YAML: mapping values are not allowed here"
    ]
    assert all("\n" not in line for line in lines)


def test_a_yaml_syntax_error_on_the_first_block_line_is_file_line_two(
    tmp_path: Path,
) -> None:
    """Block line 1 is file line 2 (2.1).

    Dies on: an offset that forgets the opening fence's line (`+ 1`).
    """
    root = _site(tmp_path / "c", {"bad.md": "---\n: [\n---\n"})
    assert _lines(root)[0].startswith("bad.md: 2:")


def test_a_duplicate_key_is_refused_at_its_second_occurrence(tmp_path: Path) -> None:
    """A repeated key is refused rather than last-wins, with its position (2.1).

    Dies on: `yaml.SafeLoader` without the duplicate check (the last value
    wins and the page loads), or a message that omits the key.
    """
    text = (
        "---\ntitle: one\ndescription: d\nsection: Guides\norder: 1\ntitle: two\n---\n"
    )
    root = _site(tmp_path / "c", {"dup.md": text})
    assert _lines(root) == [
        "dup.md: 6:1: invalid frontmatter YAML: found duplicate key 'title'"
    ]


def test_an_unhashable_key_is_a_problem_not_an_exception(tmp_path: Path) -> None:
    """A list used as a mapping key is refused with its position (2.1, 2.9).

    Dies on: putting the key in the duplicate check's set without guarding
    `TypeError` (the exception escapes `load_content`).
    """
    root = _site(tmp_path / "c", {"k.md": "---\n? [a]\n: b\n---\n"})
    assert _lines(root) == ["k.md: 2:3: invalid frontmatter YAML: found unhashable key"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-02-30", "3:7: invalid frontmatter YAML: day is out of range for month"),
        (
            "!!int abc",
            "3:7: invalid frontmatter YAML: "
            "invalid literal for int() with base 10: 'abc'",
        ),
    ],
)
def test_pyyaml_value_errors_become_problems_not_exceptions(
    tmp_path: Path, value: str, expected: str
) -> None:
    """A bare PyYAML `ValueError` for an unbuildable value is a problem (2.1, 2.9).

    The key is `date` on block line 2 (file line 3), column 7.

    Dies on: replacing the `except` of `_StrictLoader.construct_object` (the
    line loses its position, or the exception escapes `load_content`)."""
    text = (
        f"---\ntitle: t\ndate: {value}\ndescription: d\nsection: Guides\n"
        "order: 1\n---\n"
    )
    root = _site(tmp_path / "c", {"d.md": text})
    with pytest.raises(ValueError):
        yaml.safe_load(text.split("---\n")[1])  # the raw exception is a ValueError
    lines = _lines(root)
    assert lines == [f"d.md: {expected}"]


def test_an_out_of_range_timezone_offset_is_a_problem(tmp_path: Path) -> None:
    """A timestamp offset of 24 hours or more raises `ValueError` too (2.1, 2.9).

    The library's own wording is not pinned beyond its first words.

    Dies on: replacing the `except` of `_StrictLoader.construct_object` (the
    line loses its position, or the exception escapes `load_content`)."""
    text = "---\ndate: 2026-02-01 00:00:00 +25:00\n---\n"
    root = _site(tmp_path / "c", {"d.md": text})
    with pytest.raises(ValueError):
        yaml.safe_load(text.split("---\n")[1])
    (line,) = _lines(root)
    assert line.startswith(
        "d.md: 2:7: invalid frontmatter YAML: offset must be a timedelta strictly"
    )


@pytest.mark.parametrize(
    ("escape", "error", "message"),
    [
        ("UFFFFFFFF", OverflowError, "Python int too large to convert to C int"),
        ("U00110000", ValueError, "chr() arg not in range(0x110000)"),
    ],
)
def test_a_scanner_escape_past_the_code_space_is_a_problem(
    tmp_path: Path, escape: str, error: type[Exception], message: str
) -> None:
    """A `\\U` escape past the code space raises unpositioned (2.1, 2.9).

    PyYAML raises `OverflowError` for one and `ValueError` for the other,
    outside its constructor, so neither carries a mark.

    Dies on: catching `ValueError` and `yaml.YAMLError` but not `OverflowError`
    (the first case), or `OverflowError` and `yaml.YAMLError` but not
    `ValueError` (the second).
    """
    text = f'---\ntitle: "\\{escape}"\n---\n'
    root = _site(tmp_path / "c", {"o.md": text})
    with pytest.raises(error):
        yaml.safe_load(text.split("---\n")[1])
    assert _lines(root) == [f"o.md: invalid frontmatter YAML: {message}"]


def test_absurd_nesting_is_a_problem_not_an_exception(tmp_path: Path) -> None:
    """Deeply nested flow sequences exhaust the recursion limit (2.1, 2.9).

    Dies on: not catching `RecursionError`.
    """
    text = "---\ntitle: " + "[" * 5000 + "]" * 5000 + "\n---\n"
    root = _site(tmp_path / "c", {"deep.md": text})
    (line,) = _lines(root)
    assert line.startswith("deep.md: invalid frontmatter YAML: maximum recursion depth")


def test_a_second_yaml_document_is_a_problem(tmp_path: Path) -> None:
    """A `--- ` line inside the block starts a second document, which is refused (2.1).

    Dies on: reading only the first document of the block
    (`next(yaml.load_all(...))`).
    """
    text = "---\ntitle: t\n--- \nx: 1\n---\n"
    root = _site(tmp_path / "c", {"m.md": text})
    (line,) = _lines(root)
    assert line.startswith(
        "m.md: 3:1: invalid frontmatter YAML: but found another document"
    )


@pytest.mark.parametrize(
    ("block", "kind"),
    [
        ("- a\n- b", "list"),
        ("just text", "str"),
        ("42", "int"),
        ("", "null"),
        ("# c", "null"),
    ],
)
def test_frontmatter_must_be_a_mapping(tmp_path: Path, block: str, kind: str) -> None:
    """A block that parses to a list, a scalar or nothing is refused (2.1).

    Dies on: removing the mapping check.
    """
    text = f"---\n{block}\n---\n" if block else "---\n---\n"
    root = _site(tmp_path / "c", {"n.md": text})
    assert _lines(root) == [f"n.md: frontmatter must be a YAML mapping, not {kind}"]


def test_the_annotation_block_is_stripped_before_the_frontmatter_is_split(
    tmp_path: Path,
) -> None:
    """A block cut off by the annotation marker is unterminated (1.6, 2.1).

    The frontmatter ends with a blank line, and the closing `---` is followed
    by an `Annotations:` line, so `strip_annotation` removes the closing fence.

    Dies on: splitting the unstripped text (the page loads instead).
    """
    text = (
        "---\ntitle: t\ndescription: d\nsection: Guides\norder: 1\n\n"
        "---\nAnnotations: z\n"
    )
    assert strip_annotation(text).endswith("order: 1\n")  # precondition
    root = _site(tmp_path / "c", {"a.md": text})
    assert _lines(root) == ["a.md: unterminated frontmatter: no closing line ---"]


# --- drafts (2.4) ------------------------------------------------------------


def test_a_draft_page_is_omitted_and_its_asset_kept(tmp_path: Path) -> None:
    """`draft: true` omits the page only; `draft: false` keeps it; assets stay (2.4).

    Dies on: dropping the draft filter, treating `draft: false` as a draft,
    or removing the assets beside a drafted page.
    """
    root = _site(
        tmp_path / "c",
        {
            "drafted.md": _fm(_VALID, draft="true", order="1"),
            "kept.md": _fm(_VALID, draft="false", order="2"),
            "img/pic.png": "png",
        },
    )
    content, problems = load_content(root)
    assert problems == ()
    assert content is not None
    assert [page.path for page in content.pages] == ["index.md", "kept.md"]
    assert [asset.path for asset in content.assets] == ["img/pic.png"]


def test_a_draft_does_not_take_part_in_the_duplicate_order_check(
    tmp_path: Path,
) -> None:
    """A draft sharing `(section, order)` with an included page is fine (2.4, 2.6).

    Dies on: running the duplicate check over drafted pages too.
    """
    root = _site(
        tmp_path / "c",
        {"a.md": _fm(_VALID), "b.md": _fm(_VALID, draft="true")},
    )
    content, problems = load_content(root)
    assert problems == ()
    assert content is not None
    assert [page.path for page in content.pages] == ["a.md", "index.md"]


def test_a_draft_with_a_violation_is_still_reported(tmp_path: Path) -> None:
    """Every page is examined, drafts included; a bad draft fails the load (2.9).

    Dies on: skipping validation for a page that says `draft: true`.
    """
    root = _site(tmp_path / "c", {"d.md": _fm(_VALID, draft="true", order="'x'")})
    assert _lines(root) == ["d.md: order: must be an integer, not str"]


# --- site-level rules (2.6, 2.7, 2.8) ----------------------------------------


def test_a_duplicate_order_in_a_section_names_both_files(tmp_path: Path) -> None:
    """Two included pages with one `(section, order)` give one line naming both (2.6).

    The same order in different sections is allowed, and so is a different
    order in the same section.

    Dies on: keying on `order` alone (the `Why` page collides), keying on
    `section` alone, or naming only one file.
    """
    root = _site(
        tmp_path / "c",
        {
            "z.md": _fm(_VALID, order="5"),
            "a/b.md": _fm(_VALID, order="5"),
            "other.md": _fm(_VALID, section="Why", order="5"),
            "next.md": _fm(_VALID, order="6"),
        },
    )
    assert _lines(root) == [
        "a/b.md: order: duplicate order 5 in section 'Guides', also used by z.md"
    ]


def test_three_pages_sharing_a_slot_are_one_line_naming_all_three(
    tmp_path: Path,
) -> None:
    """A slot used three times gives one line that names every page (2.6).

    Dies on: naming only the first two pages.
    """
    root = _site(
        tmp_path / "c",
        {name: _fm(_VALID, order="3") for name in ("c.md", "a.md", "b.md")},
    )
    assert _lines(root) == [
        "a.md: order: duplicate order 3 in section 'Guides', also used by b.md, c.md"
    ]


def test_a_missing_home_page_is_reported(tmp_path: Path) -> None:
    """Included pages but no root `index.md` is a violation (2.7).

    A nested `sub/index.md` is not the home page.

    Dies on: not checking for the home page, or accepting any file whose name
    ends `index.md`.
    """
    root = tmp_path / "c"
    _write(root, "sub/index.md", _fm(_VALID))
    assert _lines(root) == [NO_HOME]


def test_a_drafted_home_page_is_a_missing_home_page(tmp_path: Path) -> None:
    """`index.md` with `draft: true` leaves the site without a home page (2.7).

    Dies on: checking the discovered file list for `index.md` instead of the
    included pages.
    """
    root = _site(
        tmp_path / "c",
        {"index.md": _fm(_HOME, draft="true"), "a.md": _fm(_VALID)},
    )
    assert _lines(root) == [NO_HOME]


def test_a_broken_home_page_is_not_also_a_missing_one(tmp_path: Path) -> None:
    """A broken `index.md` counts as present: its own problems only (2.7, 2.9).

    Dies on: judging the home page by the valid pages alone (a second, false
    "no home page" line appears).
    """
    root = _site(tmp_path / "c", {"index.md": _fm(_HOME, order="true")})
    assert _lines(root) == ["index.md: order: must be an integer, not bool"]


def test_an_empty_tree_holds_no_included_page(tmp_path: Path) -> None:
    """An empty content directory fails with a message saying so, once (2.8).

    Dies on: removing the no-included-page check, or reporting the missing home page
    as well.
    """
    root = tmp_path / "c"
    root.mkdir()
    assert _lines(root) == ["the content directory holds no included page"]


def test_an_all_underscore_tree_holds_no_included_page(tmp_path: Path) -> None:
    """Pages that are all excluded by name leave nothing included (2.8, 1.4).

    Dies on: removing the no-included-page check.
    """
    root = tmp_path / "c"
    _write(root, "_index.md", _fm(_HOME))
    _write(root, "_notes/deep/x.md", _fm(_VALID))
    _write(root, ".hidden/y.md", _fm(_VALID))
    assert _lines(root) == ["the content directory holds no included page"]


def test_a_drafts_only_tree_holds_no_included_page(tmp_path: Path) -> None:
    """A tree of drafts has no included page (2.4, 2.8).

    Dies on: counting drafts as included for the emptiness check.
    """
    root = tmp_path / "c"
    _write(root, "index.md", _fm(_HOME, draft="true"))
    _write(root, "a.md", _fm(_VALID, draft="true"))
    assert _lines(root) == ["the content directory holds no included page"]


# --- every violation in one run (2.9) ----------------------------------------


def test_five_violations_of_five_kinds_are_all_reported_in_one_call(
    tmp_path: Path,
) -> None:
    """A symlink, a YAML error, a missing key, a duplicate order and no home page (2.9).

    All five come from one call, as one sorted tuple of `Problem`s.

    Dies on: stopping at the first bad file, dropping the discovery problems,
    skipping the site-level checks when a page failed,
    or leaving the problems unsorted (the site-level lines are appended last
    but the missing-home one sorts before `link.md`).
    """
    root = tmp_path / "c"
    _write(root, "a.md", _fm(_VALID, order="7"))
    _write(root, "b.md", _fm(_VALID, order="7"))
    _write(root, "broken.md", "---\ntitle: a: b\n---\n")
    _write(root, "gap.md", _fm(_VALID, title=None, order="8"))
    (root / "link.md").symlink_to(root / "a.md")
    content, problems = load_content(root)
    assert content is None
    assert isinstance(problems, tuple)
    assert [problem.render() for problem in problems] == [
        "a.md: order: duplicate order 7 in section 'Guides', also used by b.md",
        "broken.md: 2:9: invalid frontmatter YAML: mapping values are not allowed here",
        "gap.md: title: required key is missing",
        NO_HOME,
        "link.md: symbolic link is not allowed",
    ]
    assert list(problems) == sorted(
        problems, key=lambda p: (p.path, p.where, p.message)
    )


def test_problems_are_sorted_by_path_then_where_then_message(tmp_path: Path) -> None:
    """Problems come back in `(path, where, message)` order (2.9).

    `m.md` carries three problems. They are found in the order `zzz`, `title`,
    `order`, sorted by `where` as `order`, `title`, `zzz`, and sorted by
    message as `zzz`, `order`, `title`: all three orders differ. The missing
    home page is found last and sorts between `a.md` and `m.md`.

    Dies on: returning the problems in emission order, sorting by message
    alone (or by path and message), or sorting on `path` alone.
    """
    root = tmp_path / "c"
    root.mkdir()
    _write(root, "m.md", _fm(_VALID, title=None, order="true", zzz="1"))
    _write(root, "a.md", _fm(_VALID, section="Nope"))
    content, problems = load_content(root)
    assert content is None
    assert [(p.path, p.where) for p in problems] == [
        ("a.md", "section"),
        ("index.md", ""),
        ("m.md", "order"),
        ("m.md", "title"),
        ("m.md", "zzz"),
    ]


def test_a_problem_is_a_problem_value_with_path_where_and_message(
    tmp_path: Path,
) -> None:
    """The returned problems are `Problem` values with the three fields set (2.9).

    Dies on: putting the key in `path`.
    """
    root = _site(tmp_path / "c", {"g/p.md": _fm(_VALID, order="'x'")})
    _content, problems = load_content(root)
    assert problems == (Problem("g/p.md", "order", "must be an integer, not str"),)


def test_a_clean_load_returns_the_content_and_an_empty_tuple(tmp_path: Path) -> None:
    """Success is `(SiteContent, ())` with the tuple type, not a list (2.9).

    Dies on: returning `[]` or `None` for the problems of a clean load.
    """
    content, problems = load_content(_site(tmp_path / "c"))
    assert content is not None
    assert problems == ()
    assert isinstance(problems, tuple)
    assert [page.path for page in content.pages] == ["index.md"]


def test_load_content_leaves_the_tree_untouched(tmp_path: Path) -> None:
    """A byte hash of the content dir is unchanged by a clean or failing load (1.3).

    Both loads run over tmp copies of the fixture.

    Dies on: `load_content` rewriting a page's bytes, setting its times, chmod-ing
    it, or creating a file or a directory in the content root.
    """
    good = copy_fixture_tree(FIXTURE, tmp_path, "good")
    bad = copy_fixture_tree(FIXTURE, tmp_path, "bad")
    (bad / "why.md").write_bytes(b"no frontmatter\n")
    for root, ok in ((good, True), (bad, False)):
        before = _tree_hash(root)
        content, problems = load_content(root)
        assert (content is not None) is ok  # each path really ran
        assert (problems == ()) is ok
        count_included_pages(root)
        assert _tree_hash(root) == before


# --- count_included_pages (10.6) ---------------------------------------------


def test_count_of_an_empty_tree_is_zero(tmp_path: Path) -> None:
    """An empty content dir has no included page (10.6).

    Dies on: adding one to the count.
    """
    root = tmp_path / "c"
    root.mkdir()
    assert count_included_pages(root) == 0


def test_count_of_a_drafts_only_tree_is_zero(tmp_path: Path) -> None:
    """Drafted pages and `_` pages are not counted (10.6, 2.4, 1.4).

    Dies on: counting drafts.
    """
    root = tmp_path / "c"
    _write(root, "index.md", _fm(_HOME, draft="true"))
    _write(root, "a.md", _fm(_VALID, draft="true"))
    _write(root, "_private/b.md", _fm(_VALID))
    assert count_included_pages(root) == 0


def test_count_of_the_fixture_is_six() -> None:
    """The fixture holds six included pages (10.6).

    Dies on: counting the drafted page (7).
    """
    assert count_included_pages(FIXTURE) == 6


def test_a_page_whose_frontmatter_cannot_be_read_counts_as_included(
    tmp_path: Path,
) -> None:
    """Broken YAML, no frontmatter, non-UTF-8 and a non-boolean draft each count (10.6).

    One drafted page beside them is not counted, so the total is exactly the
    number of unreadable pages.

    Dies on: counting only pages that validate, treating a read failure as a
    draft, or testing `draft` by truthiness (`draft: 'true'` would be a draft).
    """
    root = tmp_path / "c"
    _write(root, "yaml.md", "---\ntitle: a: b\n---\n")
    _write(root, "none.md", "prose\n")
    _write(root, "quoted.md", _fm(_VALID, draft="'true'"))
    (root / "bytes.md").write_bytes(b"\xff\xfe")
    _write(root, "drafted.md", _fm(_VALID, draft="true"))
    assert count_included_pages(root) == 4


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a mode-000 file")
def test_an_unreadable_file_counts_as_included(tmp_path: Path) -> None:
    """A page that cannot be opened counts as included (10.6).

    Dies on: letting `PermissionError` escape, or treating a read failure as a draft.
    """
    root = tmp_path / "c"
    _write(root, "locked.md", _fm(_VALID))
    (root / "locked.md").chmod(0o000)
    try:
        assert count_included_pages(root) == 1
    finally:
        (root / "locked.md").chmod(0o644)


def test_a_draft_with_other_violations_is_not_counted(tmp_path: Path) -> None:
    """Readable frontmatter with `draft: true` is a draft, whatever else (10.6).

    Dies on: requiring the whole page to validate before honouring `draft`.
    """
    root = tmp_path / "c"
    _write(root, "d.md", "---\ndraft: true\n---\n")
    assert count_included_pages(root) == 0


# --- round 1 additions --------------------------------------------------------

_BARE_FAILURES = [
    ('!!int ""', "string index out of range"),
    ("!!int _", "string index out of range"),
    ('!!float ""', "string index out of range"),
    ("!!bool abc", "not a valid bool: 'abc'"),
    ('!!bool ""', "not a valid bool: ''"),
    ("!!timestamp abc", "'NoneType' object has no attribute"),
    ('!!timestamp ""', "'NoneType' object has no attribute"),
]


@pytest.mark.parametrize(("value", "message"), _BARE_FAILURES)
def test_any_exception_from_a_pyyaml_constructor_is_a_positioned_problem(
    tmp_path: Path, value: str, message: str
) -> None:
    """`IndexError`, `KeyError` and `AttributeError` become problems (2.1, 2.9).

    The value is on block line 1 (file line 2), after `x: `, so column 4.

    Dies on: narrowing the `except` in `_StrictLoader.construct_object` to
    `(ValueError, OverflowError)` (the exception escapes `load_content`).
    """
    text = f"---\nx: {value}\n---\n"
    root = _site(tmp_path / "c", {"k.md": text})
    (line,) = _lines(root)
    assert line.startswith(f"k.md: 2:4: invalid frontmatter YAML: {message}")
    assert "\n" not in line


def test_a_page_with_a_constructor_failure_counts_as_included(tmp_path: Path) -> None:
    """Such a page counts as included (10.6).

    Dies on: narrowing the `except` in `_StrictLoader.construct_object` to
    `(ValueError, OverflowError)` (`IndexError` escapes `count_included_pages`).
    """
    root = tmp_path / "c"
    _write(root, "k.md", '---\nx: !!int ""\n---\n')
    assert count_included_pages(root) == 1


def test_a_control_character_is_positioned_in_the_file(tmp_path: Path) -> None:
    """A control character is a reader error, located by file line and column (2.1).

    In `x: ab\\x01c` the character is the sixth on block line 2, and another
    line follows it: file line 3, column 6. The line has no run of spaces left
    over from PyYAML's multi-line text.

    Dies on: dropping the `position` branch of `_yaml_problem` (no position),
    rendering `str(error)` (a double space), a fixed `column = 0`, or taking
    the line as the block's line count.
    """
    root = _site(tmp_path / "c", {"r.md": "---\ntitle: t\nx: ab\x01c\ny: 2\n---\n"})
    assert _lines(root) == [
        "r.md: 3:6: invalid frontmatter YAML: unacceptable character #x0001: "
        "special characters are not allowed"
    ]


def test_a_duplicate_key_inside_a_hero_action_is_refused(tmp_path: Path) -> None:
    """The duplicate-key rule holds in nested mappings, with position (2.1, 2.3).

    Dies on: checking duplicate keys at the top level only.
    """
    actions = "\n  - label: A\n    href: b/\n    label: B"
    text = (
        "---\n"
        + "\n".join(f"{k}: {v}" for k, v in {**_HOME, "hero_actions": actions}.items())
        + "\n---\n"
    )
    root = _site(tmp_path / "c", {"index.md": text})
    assert _lines(root) == [
        "index.md: 9:5: invalid frontmatter YAML: found duplicate key 'label'"
    ]


@pytest.mark.parametrize(
    ("line", "shown"),
    [
        ('"": x', "''"),
        ('"  ": x', "'  '"),
        ("2026-01-01: x", "2026-01-01"),
        ("7: x", "7"),
    ],
)
def test_an_unknown_key_is_named_as_the_author_wrote_it(
    tmp_path: Path, line: str, shown: str
) -> None:
    """A non-text key is named by `str`, an empty or blank text key by `repr` (2.5).

    Dies on: naming every key with `str(key)` (the empty and blank keys give
    an empty or invisible `where`), naming every key with `repr(key)` (the
    date key renders `datetime.date(...)`), or `str(key) or repr(key)` (the
    blank key stays invisible).
    """
    text = _fm(_VALID).replace("order: 1\n", f"order: 1\n{line}\n")
    root = _site(tmp_path / "c", {"p.md": text})
    assert _lines(root) == [
        f"p.md: {shown}: key is not allowed by the content contract"
    ]


def test_a_page_with_a_violation_still_takes_part_in_the_duplicate_check(
    tmp_path: Path,
) -> None:
    """A page with an unknown key and a page in its slot: both lines appear (2.6, 2.9).

    Dies on: building the slot map from fully valid pages only.
    """
    root = _site(
        tmp_path / "c",
        {"a.md": _fm(_VALID, colour="red"), "b.md": _fm(_VALID)},
    )
    assert _lines(root) == [
        "a.md: colour: key is not allowed by the content contract",
        "a.md: order: duplicate order 1 in section 'Guides', also used by b.md",
    ]


def test_a_page_with_an_invalid_order_or_section_has_no_slot(tmp_path: Path) -> None:
    """A page whose own order or section is invalid takes no slot (2.6).

    Two pages share an invalid section, and two share a text `order`. Neither
    pair is reported as a duplicate.

    Dies on: recording a slot from the raw `section` and `order` values.
    """
    root = _site(
        tmp_path / "c",
        {
            "a.md": _fm(_VALID, section="Nope"),
            "a2.md": _fm(_VALID, section="Nope"),
            "b.md": _fm(_VALID, order="'1'"),
            "b2.md": _fm(_VALID, order="'1'"),
        },
    )
    assert [line.split(": ")[:2] for line in _lines(root)] == [
        ["a.md", "section"],
        ["a2.md", "section"],
        ["b.md", "order"],
        ["b2.md", "order"],
    ]


def test_draft_one_is_a_type_violation_not_a_draft(tmp_path: Path) -> None:
    """`draft: 1` is an invalid value: counted as included, home not missing (2.3, 2.4).

    `1 == True` in Python; only `True` itself drafts a page.

    Dies on: testing `draft == True` instead of `draft is True`.
    """
    root = tmp_path / "c"
    _write(root, "index.md", _fm(_HOME, draft="1"))
    assert count_included_pages(root) == 1
    assert _lines(root) == ["index.md: draft: must be true or false, not int"]


def test_an_error_inside_a_mapping_key_keeps_its_own_position(tmp_path: Path) -> None:
    """A duplicate inside a flow mapping used as a key is located there (2.1).

    The duplicate `a` is at block line 1, column 10; the enclosing key starts at
    column 3.

    Dies on: dropping `except yaml.YAMLError: raise` in
    `_StrictLoader.construct_object` (the error is re-positioned at the
    enclosing key).
    """
    root = _site(tmp_path / "c", {"k.md": "---\n? {a: 1, a: 2}\n: x\n---\n"})
    assert _lines(root) == [
        "k.md: 2:10: invalid frontmatter YAML: found duplicate key 'a'"
    ]


def test_the_home_page_takes_part_in_the_duplicate_check(tmp_path: Path) -> None:
    """A second `Home` page with the home page's order is a duplicate (2.6).

    Dies on: leaving `index.md` out of the slot map.
    """
    root = _site(tmp_path / "c", {"a.md": _fm(_HOME)})
    assert _lines(root) == [
        "a.md: order: duplicate order 1 in section 'Home', also used by index.md"
    ]
