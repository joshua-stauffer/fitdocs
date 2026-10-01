"""Staging a build root: the byte map, the fresh write and the in-place sync.

Covers 1.3, 1.5, 1.6, 1.8, 3.3 and 7.2. Planning tests read the real fixture
and the real ``website/assets`` and ``website/overrides`` (read only); every
test that writes uses a ``tmp_path`` build root.
"""

from __future__ import annotations

import difflib
import os
from dataclasses import replace
from pathlib import Path

import pytest
from scripts.sitebuild.content import load_content, strip_annotation
from scripts.sitebuild.model import HOME_PAGE, Asset, Page, SiteContent
from scripts.sitebuild.stage import (
    HTML,
    INJECTED_LINE,
    MANAGED,
    STAGED,
    plan_tree,
    source_where,
    sync_tree,
    write_tree,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "site"
ASSETS_DIR = REPO_ROOT / "website" / "assets"
OVERRIDES_DIR = REPO_ROOT / "website" / "overrides"

CONFIG = "site_name: Fixture — café\n"
LLMS = "# llms é\n"
LLMS_FULL = "# full é\r\nbody\n"
INJECTED = "template: home.html"

PLANNED = ("mkdocs.yml", "staged", "overrides")


def _content() -> SiteContent:
    content, problems = load_content(FIXTURE)
    assert content is not None and not problems
    return content


def _plan(
    content: SiteContent | None = None,
    *,
    assets_dir: Path = ASSETS_DIR,
    overrides_dir: Path = OVERRIDES_DIR,
    config_text: str = CONFIG,
) -> dict[str, bytes]:
    return plan_tree(
        content if content is not None else _content(),
        config_text=config_text,
        llms=LLMS,
        llms_full=LLMS_FULL,
        assets_dir=assets_dir,
        overrides_dir=overrides_dir,
    )


def _source(page: Page) -> str:
    return (FIXTURE / page.path).read_bytes().decode("utf-8")


def _page(path: str, text: str) -> Page:
    return Page(
        path=path,
        title="T",
        description="D",
        section="Guides",
        order=1,
        staged_text=text,
        body=text,
        hero_title=None,
        hero_tagline=None,
        hero_actions=None,
    )


def _files(root: Path, tops: tuple[str, ...] = PLANNED) -> dict[str, bytes]:
    """Every regular file under the planned top-level names, by relative path."""
    found: dict[str, bytes] = {}
    for top in tops:
        base = root / top
        if base.is_file():
            found[top] = base.read_bytes()
        elif base.is_dir():
            for path in sorted(base.rglob("*")):
                if path.is_file():
                    found[path.relative_to(root).as_posix()] = path.read_bytes()
    return found


def _everything(root: Path) -> dict[str, tuple[str, bytes | str]]:
    """Every entry under root: files by bytes, dirs by marker, links by target."""
    seen: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            seen[rel] = ("link", os.readlink(path))
        elif path.is_dir():
            seen[rel] = ("dir", "")
        else:
            seen[rel] = ("file", path.read_bytes())
    return seen


# --- plan_tree ---------------------------------------------------------------


def test_non_home_pages_equal_stripped_source() -> None:
    """Every non-home staged page is exactly the stripped source bytes (1.6, 1.8).

    Dies on: `plan_tree` injecting the template line on every page instead of
    only ``HOME_PAGE``, or converting each page's text (CRLF round trip).
    """
    content = _content()
    tree = _plan(content)
    others = [p for p in content.pages if p.path != HOME_PAGE]
    assert len(others) >= 4
    annotated = [p for p in others if strip_annotation(_source(p)) != _source(p)]
    assert annotated, "no fixture page carries an annotation block to strip"
    for page in others:
        expected = strip_annotation(_source(page)).encode("utf-8")
        assert tree[f"{STAGED}/{page.path}"] == expected


def test_page_text_is_encoded_verbatim() -> None:
    """Non-ASCII, CR and lone-CR text reaches the map unchanged as UTF-8 (1.6).

    Dies on: encoding the text with a lossy or newline-translating step, such
    as ``.replace("\\r\\n", "\\n")`` or an ASCII/latin-1 encode.
    """
    text = "---\ntitle: café\n---\n\nline one\r\nline two\rend — 日本\n"
    content = SiteContent(root=FIXTURE, pages=(_page("guides/x.md", text),), assets=())
    tree = _plan(content)
    assert "\r\n" in text and "\r" in text.replace("\r\n", "")
    assert tree["staged/guides/x.md"] == text.encode("utf-8")


def test_home_page_differs_by_exactly_the_injected_line() -> None:
    """The home page is the stripped source plus one line after the opening `---`.

    Dies on: inserting the line before the opening fence, at the end of the
    frontmatter, or not at all.
    """
    content = _content()
    home = next(p for p in content.pages if p.path == HOME_PAGE)
    stripped = strip_annotation(_source(home))
    assert stripped.startswith("---\n")
    assert INJECTED not in stripped
    staged = _plan(content)[f"{STAGED}/{HOME_PAGE}"].decode("utf-8")
    before = stripped.splitlines(keepends=True)
    after = staged.splitlines(keepends=True)
    assert after[0] == "---\n"
    assert after[1] == INJECTED + "\n"
    assert after[:1] + after[2:] == before
    delta = [d for d in difflib.ndiff(before, after) if d[0] in "+-"]
    assert delta == [f"+ {INJECTED}\n"]


def test_injected_line_constant_is_the_staged_line_of_the_template_line() -> None:
    """``INJECTED_LINE`` is the 1-based staged line holding the injected text.

    Dies on: ``INJECTED_LINE`` drifting from where ``_inject_template`` puts the
    line.
    """
    staged = _plan(_content())[f"{STAGED}/{HOME_PAGE}"].decode("utf-8")
    assert staged.splitlines()[INJECTED_LINE - 1] == INJECTED


@pytest.mark.parametrize(
    ("path", "where", "expected"),
    [
        (HOME_PAGE, "16:58", "15:58"),
        (HOME_PAGE, "3:1", "2:1"),
        (HOME_PAGE, "2:5", "2:5"),
        (HOME_PAGE, "1:1", "1:1"),
        (HOME_PAGE, "", ""),
        (HOME_PAGE, "title", "title"),
        (HOME_PAGE, "x:58", "x:58"),
        (HOME_PAGE, "16:x", "16:x"),
        ("why.md", "16:58", "16:58"),
        ("guides/index.md", "16:58", "16:58"),
    ],
)
def test_source_where_corrects_only_home_lines_after_the_injection(
    path: str, where: str, expected: str
) -> None:
    """A home-page location after the injected line moves up one; nothing else moves.

    Dies on: no correction; correcting every page; subtracting 0 or 2; correcting
    the opening-fence line or the injected line itself; touching a non-``line:col``
    ``where``.
    """
    assert source_where(path, where) == expected


def test_only_the_root_home_page_gets_the_template_line() -> None:
    """A nested ``index.md`` is an ordinary page and is left exactly as staged (3.3).

    Dies on: matching the home page by ``endswith("index.md")`` (or any basename
    rule) instead of comparing the whole path to ``HOME_PAGE``.
    """
    text = "---\ntitle: nested\n---\n\nbody\n"
    home_text = "---\ntitle: home\n---\n\nhome\n"
    content = SiteContent(
        root=FIXTURE,
        pages=(_page("guides/index.md", text), _page(HOME_PAGE, home_text)),
        assets=(),
    )
    tree = _plan(content)
    assert tree["staged/guides/index.md"] == text.encode("utf-8")
    assert tree["staged/index.md"] == (
        b"---\ntemplate: home.html\ntitle: home\n---\n\nhome\n"
    )


def test_assets_are_byte_identical_at_the_same_path(tmp_path: Path) -> None:
    """Every asset lands at ``staged/<path>`` with its exact bytes (1.5).

    Dies on: reading assets as text (decode/encode or universal newlines), or
    staging them under a different path.
    """
    content = _content()
    binary = tmp_path / "blob.bin"
    binary.write_bytes(b"\x00\xff\xfe\r\n\x80abc\r\x00")
    combined = replace(
        content,
        assets=(*content.assets, Asset(path="data/blob.bin", source=binary)),
    )
    tree = _plan(combined)
    assert len(content.assets) >= 1
    for asset in combined.assets:
        assert tree[f"{STAGED}/{asset.path}"] == asset.source.read_bytes()
    assert tree["staged/data/blob.bin"] == b"\x00\xff\xfe\r\n\x80abc\r\x00"


def test_plan_has_exactly_the_documented_paths() -> None:
    """The map holds config, pages, assets, brand files, llms texts and overrides.

    Dies on: staging the fixture's underscore-named content entries, dropping
    the llms, ``_brand`` or overrides entries, or adding any other key.
    """
    content = _content()
    tree = _plan(content)
    assert (FIXTURE / "_notes.md").exists() and (FIXTURE / "_private").is_dir()
    assert (FIXTURE / "reference" / "cli.md").exists()
    expected = {"mkdocs.yml", "staged/llms.txt", "staged/llms-full.txt"}
    expected |= {f"staged/{p.path}" for p in content.pages}
    expected |= {f"staged/{a.path}" for a in content.assets}
    expected |= {f"staged/_brand/{p.name}" for p in ASSETS_DIR.iterdir() if p.is_file()}
    expected |= {f"overrides/{p.name}" for p in OVERRIDES_DIR.iterdir()}
    assert set(tree) == expected


def test_brand_llms_config_and_overrides_bytes(tmp_path: Path) -> None:
    """``_brand/`` comes only from the assets dir, the rest from their inputs (3.5).

    Dies on: reading ``_brand`` from anywhere but ``assets_dir``, or writing
    the llms texts or config with a different encoding.
    """
    assets = tmp_path / "assets"
    (assets / "sub").mkdir(parents=True)
    (assets / "a.css").write_bytes(b"a\r\n")
    (assets / "sub" / "b.bin").write_bytes(b"\x00\xff")
    overrides = tmp_path / "over"
    (overrides / "partials").mkdir(parents=True)
    (overrides / "home.html").write_bytes(b"<h1>\xc3\xa9</h1>\r\n")
    (overrides / "partials" / "p.html").write_bytes(b"p")
    tree = _plan(assets_dir=assets, overrides_dir=overrides)
    brand = {k: v for k, v in tree.items() if k.startswith(f"{STAGED}/_brand")}
    assert brand == {
        "staged/_brand/a.css": b"a\r\n",
        "staged/_brand/sub/b.bin": b"\x00\xff",
    }
    over = {k: v for k, v in tree.items() if k.startswith("overrides/")}
    assert over == {
        "overrides/home.html": b"<h1>\xc3\xa9</h1>\r\n",
        "overrides/partials/p.html": b"p",
    }
    assert tree["staged/llms.txt"] == LLMS.encode("utf-8")
    assert tree["staged/llms-full.txt"] == LLMS_FULL.encode("utf-8")
    assert tree["mkdocs.yml"] == CONFIG.encode("utf-8")


def test_real_brand_files_are_planned_byte_for_byte() -> None:
    """The three shipped brand files appear under ``staged/_brand/`` (3.5).

    Dies on: skipping a file of ``website/assets/`` or staging it elsewhere.
    """
    tree = _plan()
    names = sorted(p.name for p in ASSETS_DIR.iterdir())
    assert names == ["brand.css", "hero-chart.svg", "logo.svg"]
    for name in names:
        assert tree[f"staged/_brand/{name}"] == (ASSETS_DIR / name).read_bytes()
    assert tree["overrides/home.html"] == (OVERRIDES_DIR / "home.html").read_bytes()


def test_no_content_underscore_name_reaches_staged() -> None:
    """Under ``staged/`` the only ``_`` first component is ``_brand`` (1.3, 3.5).

    Dies on: staging the fixture's ``_notes.md`` or ``_private/`` entries.
    """
    tree = _plan()
    assert (FIXTURE / "_notes.md").exists() and (FIXTURE / "_private").is_dir()
    staged = [k.split("/")[1] for k in tree if k.startswith(f"{STAGED}/")]
    assert staged
    assert {n for n in staged if n.startswith("_")} == {"_brand"}
    assert not [k for k in tree if "secret" in k or "_notes" in k]


def test_a_colliding_path_is_refused(tmp_path: Path) -> None:
    """Two sources for one path are an error, never a silent overwrite (3.5).

    Dies on: dropping the duplicate-key check in ``plan_tree``.
    """
    content = _content()
    clash = tmp_path / "brand.css"
    clash.write_bytes(b"content-owned")
    hostile = replace(
        content,
        assets=(*content.assets, Asset(path="_brand/brand.css", source=clash)),
    )
    with pytest.raises(ValueError, match=r"staged/_brand/brand\.css"):
        _plan(hostile)


# --- write_tree ---------------------------------------------------------------


def test_write_tree_writes_the_map_and_removes_stale_managed_paths(
    tmp_path: Path,
) -> None:
    """A fresh write removes ``mkdocs.yml``, ``staged/``, ``overrides/``, ``html/``.

    Dies on: skipping the removal (stale files survive), removing the whole
    root (``.cache/`` and the stray file vanish), or skipping ``html/``.
    """
    root = tmp_path / "root"
    (root / "staged" / "old").mkdir(parents=True)
    (root / "staged" / "old" / "gone.md").write_text("stale")
    (root / "overrides").mkdir()
    (root / "overrides" / "gone.html").write_text("stale")
    (root / HTML).mkdir()
    (root / HTML / "index.html").write_text("old site")
    (root / "mkdocs.yml").write_text("old: true\n")
    (root / ".cache").mkdir()
    (root / ".cache" / "keep").write_bytes(b"cache")
    (root / "stray.txt").write_bytes(b"stray")
    assert MANAGED == ("mkdocs.yml", "staged", "overrides", "html")

    tree = _plan()
    write_tree(tree, root)

    assert _files(root) == tree
    assert not (root / HTML).exists()
    assert not (root / "staged" / "old").exists()
    assert (root / ".cache" / "keep").read_bytes() == b"cache"
    assert (root / "stray.txt").read_bytes() == b"stray"


def test_write_tree_creates_a_missing_root(tmp_path: Path) -> None:
    """Writing into a root that does not exist yet creates it.

    Dies on: writing without creating the root and its parents.
    """
    root = tmp_path / "a" / "b" / "root"
    tree = {"mkdocs.yml": b"x: 1\n", "staged/p.md": b"p"}
    write_tree(tree, root)
    assert _files(root) == tree


def test_write_tree_refuses_paths_that_escape_the_root(tmp_path: Path) -> None:
    """A ``..``, absolute or unplanned key is refused before anything is written.

    Dies on: removing the key validation (the ``..`` file lands beside the root
    and the valid entries are written first).
    """
    outer = tmp_path / "outer"
    root = outer / "root"
    root.mkdir(parents=True)
    before = _everything(outer)
    bad_keys = (
        "../evil.txt",
        "staged/../../evil.txt",
        "staged/../../../evil.txt",
        str(tmp_path / "abs.txt"),
        "/abs.txt",
        "staged//x.md",
        "staged/./x.md",
        "html/x",
        "staged",
        "mkdocs.yml/x",
        "staged/a\0b.md",
        "stray.txt",
        "",
    )
    for bad in bad_keys:
        for writer in (write_tree, sync_tree):
            with pytest.raises(ValueError):
                writer({"mkdocs.yml": b"ok", bad: b"evil"}, root)
            assert _everything(outer) == before, (writer.__name__, bad)
    assert not (tmp_path / "evil.txt").exists()


def test_write_tree_does_not_follow_a_symlinked_managed_path(tmp_path: Path) -> None:
    """A symlink at a managed name is replaced, and its target is left alone.

    Dies on: clearing managed paths by following links (the target is emptied),
    or ``write_tree`` not removing a symlinked managed path such as ``html``,
    which no map entry replaces.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"keep")
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside, root / "staged")
    os.symlink(outside, root / HTML)
    os.symlink(outside, root / "overrides")
    (root / "mkdocs.yml").symlink_to(outside / "keep.txt")

    tree = _plan()
    write_tree(tree, root)

    assert _everything(outside) == {"keep.txt": ("file", b"keep")}
    assert _files(root) == tree
    assert not (root / "staged").is_symlink()
    assert not os.path.lexists(root / HTML)


# --- sync_tree ----------------------------------------------------------------


def _seed_live(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    """A live root holding plan A, plus html/ and .cache/ contents."""
    root = tmp_path / "live"
    tree_a = _plan()
    write_tree(tree_a, root)
    (root / HTML).mkdir()
    (root / HTML / "index.html").write_bytes(b"site")
    (root / ".cache").mkdir()
    (root / ".cache" / "state").write_bytes(b"cache")
    old = 1_000_000_000
    for path in root.rglob("*"):
        if path.is_file():
            os.utime(path, (old, old))
    return root, tree_a


def _stat_key(path: Path) -> tuple[int, int, int]:
    st = path.stat()
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def test_sync_tree_modifies_adds_and_deletes_in_place(tmp_path: Path) -> None:
    """Sync leaves the live root equal to the map, with no directory replaced (7.2).

    Dies on: syncing by removing and re-copying ``staged/`` (the directory
    inode changes), or by renaming a fresh directory into place.
    """
    root, tree_a = _seed_live(tmp_path)
    tree_b = dict(tree_a)
    tree_b["staged/why.md"] = tree_a["staged/why.md"] + b"\nmodified\n"
    tree_b["staged/brand-new/deep/page.md"] = b"new page\n"
    del tree_b["staged/guides/nested/deep.md"]
    del tree_b["staged/get-started/install.md"]
    assert (
        "staged/guides/nested/deep.md" in tree_a and (root / "staged/guides").is_dir()
    )

    inodes = {
        rel: (root / rel).stat().st_ino
        for rel in ("staged", "staged/get-started", "overrides", "staged/_brand")
    }
    html_before = _stat_key(root / HTML / "index.html")
    cache_before = _stat_key(root / ".cache" / "state")
    untouched = "staged/index.md"
    mtime_before = (root / untouched).stat().st_mtime_ns

    sync_tree(tree_b, root)

    assert _files(root) == tree_b
    assert inodes == {rel: (root / rel).stat().st_ino for rel in inodes}
    assert _stat_key(root / HTML / "index.html") == html_before
    assert _stat_key(root / ".cache" / "state") == cache_before
    assert (root / untouched).stat().st_mtime_ns == mtime_before
    assert (root / "staged/get-started/first-run.md").exists()


def test_sync_tree_prunes_emptied_directories_but_keeps_top_level(
    tmp_path: Path,
) -> None:
    """A directory left empty is removed, nested parents too; ``staged/`` stays.

    Dies on: never pruning (empty ``guides/nested/`` stays), or removing the
    top-level ``staged/`` once it is empty (it no longer exists).
    """
    root, tree_a = _seed_live(tmp_path)
    assert (root / "staged/guides/nested").is_dir()
    tree_b = {k: v for k, v in tree_a.items() if not k.startswith("staged/guides")}
    sync_tree(tree_b, root)
    assert not (root / "staged/guides").exists()
    assert (root / "staged/why.md").exists()

    sync_tree({k: v for k, v in tree_b.items() if not k.startswith("staged/")}, root)
    assert (root / STAGED).is_dir()
    assert list((root / STAGED).iterdir()) == []


def test_sync_tree_writes_only_files_that_differ(tmp_path: Path) -> None:
    """Syncing an identical map touches no file (7.2).

    Dies on: rewriting every file (mtime moves off the fixed old value).
    """
    root, tree_a = _seed_live(tmp_path)
    marks = {rel: _stat_key(root / rel) for rel in tree_a}
    assert {m[1] for m in marks.values()} == {1_000_000_000 * 10**9}
    sync_tree(tree_a, root)
    assert {rel: _stat_key(root / rel) for rel in tree_a} == marks


def test_sync_tree_leaves_unmanaged_entries_and_html_alone(tmp_path: Path) -> None:
    """Only ``mkdocs.yml``, ``staged/`` and ``overrides/`` are compared; the rest stays.

    Dies on: deleting every entry of the root that is absent from the map.
    """
    root, tree_a = _seed_live(tmp_path)
    (root / "stray.txt").write_bytes(b"stray")
    (root / HTML / "deep").mkdir()
    (root / HTML / "deep" / "x.html").write_bytes(b"x")
    before = {k: v for k, v in _everything(root).items() if not k.startswith(PLANNED)}
    assert set(before) >= {"stray.txt", "html/deep/x.html", ".cache/state"}
    sync_tree({"mkdocs.yml": b"only: one\n", "staged/a.md": b"a"}, root)
    after = {k: v for k, v in _everything(root).items() if not k.startswith(PLANNED)}
    assert after == before
    assert _files(root) == {"mkdocs.yml": b"only: one\n", "staged/a.md": b"a"}


def test_sync_tree_handles_file_and_directory_swaps(tmp_path: Path) -> None:
    """A path that flips between file and directory still syncs, ``staged/`` intact.

    Dies on: clearing by removing and re-creating the top-level directory (its
    inode changes).
    """
    root = tmp_path / "live"
    sync_tree({"staged/x": b"file", "staged/d/y.md": b"y"}, root)
    inode = (root / STAGED).stat().st_ino
    sync_tree({"staged/x/inner.md": b"i", "staged/d": b"now a file"}, root)
    assert _files(root) == {"staged/x/inner.md": b"i", "staged/d": b"now a file"}
    assert (root / STAGED).stat().st_ino == inode


def test_sync_tree_never_writes_through_a_symlink(tmp_path: Path) -> None:
    """A link inside a managed directory is removed, not followed (1.3).

    Dies on: following a link when deleting (the target is emptied), or the
    writer no longer removing a link that stands where a file belongs (the write
    lands in the target).
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"keep")
    root = tmp_path / "live"
    (root / "staged").mkdir(parents=True)
    os.symlink(outside, root / "staged" / "sub")
    os.symlink(outside / "keep.txt", root / "staged" / "stale.md")
    os.symlink(outside / "keep.txt", root / "staged" / "want.md")

    sync_tree({"staged/sub/new.md": b"n", "staged/want.md": b"w"}, root)

    assert _everything(outside) == {"keep.txt": ("file", b"keep")}
    assert _files(root) == {"staged/sub/new.md": b"n", "staged/want.md": b"w"}
    assert not (root / "staged" / "stale.md").exists()
    assert not (root / "staged" / "sub").is_symlink()


def test_sync_tree_creates_a_missing_root(tmp_path: Path) -> None:
    """Syncing into a root that does not exist yet writes the whole map.

    Dies on: assuming the root and managed directories already exist.
    """
    root = tmp_path / "x" / "live"
    tree = _plan()
    sync_tree(tree, root)
    assert _files(root) == tree


def test_sync_tree_replaces_a_symlinked_managed_directory(tmp_path: Path) -> None:
    """A link standing where ``staged/`` belongs is replaced; its target is left alone.

    Dies on: writing through a link, which puts the planned pages into the target
    directory outside the root or overwrites ``keep.txt`` through the
    ``mkdocs.yml`` link.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"keep")
    root = tmp_path / "live"
    root.mkdir()
    os.symlink(outside, root / "staged")
    os.symlink(outside, root / "overrides")
    os.symlink(outside / "keep.txt", root / "mkdocs.yml")

    tree = _plan()
    sync_tree(tree, root)

    assert _everything(outside) == {"keep.txt": ("file", b"keep")}
    assert _files(root) == tree
    assert not (root / "mkdocs.yml").is_symlink()
    assert not (root / "staged").is_symlink()
    assert not (root / "overrides").is_symlink()


def test_sync_tree_deletes_an_absent_top_level_file(tmp_path: Path) -> None:
    """A ``mkdocs.yml`` the map no longer has is deleted from the live root.

    Dies on: keeping a top-level managed entry that is absent from the map,
    including a link that stands where ``overrides/`` was, or a dangling one
    where ``mkdocs.yml`` was (nothing is created or removed at the targets).
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_bytes(b"keep")
    root = tmp_path / "live"
    sync_tree({"mkdocs.yml": b"a: 1\n", "staged/p.md": b"p"}, root)
    assert (root / "mkdocs.yml").is_file()
    os.symlink(outside, root / "overrides")
    sync_tree({"staged/p.md": b"p"}, root)
    assert not os.path.lexists(root / "mkdocs.yml")
    assert not os.path.lexists(root / "overrides")
    assert _everything(outside) == {"keep.txt": ("file", b"keep")}
    assert _files(root) == {"staged/p.md": b"p"}
    os.symlink(outside / "absent.yml", root / "mkdocs.yml")
    sync_tree({"staged/p.md": b"p"}, root)
    assert not os.path.lexists(root / "mkdocs.yml")
    assert _everything(outside) == {"keep.txt": ("file", b"keep")}


def test_sync_tree_rewrites_a_same_length_change(tmp_path: Path) -> None:
    """A file whose bytes change without changing length is rewritten.

    Dies on: deciding a file is unchanged by comparing lengths.
    """
    root, tree_a = _seed_live(tmp_path)
    key = "staged/get-started/first-run.md"
    old = tree_a[key]
    new = bytes([old[0] ^ 1]) + old[1:]
    assert new != old and len(new) == len(old)
    sync_tree({**tree_a, key: new}, root)
    assert (root / key).read_bytes() == new


def test_home_page_without_an_opening_fence_is_refused() -> None:
    """A home page whose text does not open with ``---`` cannot get the line.

    Dies on: injecting anyway (no ``ValueError``), which would put a
    ``template`` line into a page with no frontmatter and drop the page's first
    four characters.
    """
    content = SiteContent(
        root=FIXTURE, pages=(_page(HOME_PAGE, "no frontmatter\n"),), assets=()
    )
    with pytest.raises(ValueError, match="index.md"):
        _plan(content)


def test_dot_entries_of_the_assets_dir_are_not_planned(tmp_path: Path) -> None:
    """Dot-named files and directories of ``assets_dir`` never reach ``_brand/``.

    Dies on: staging dot-entries (a local ``.DS_Store`` would be copied into
    ``staged/_brand/``), or testing the absolute path's parts instead of the
    path relative to ``assets_dir`` (a dotted ancestor would hide every file).
    """
    assets = tmp_path / ".checkout" / "assets"
    (assets / ".hidden").mkdir(parents=True)
    (assets / ".hidden" / "x").write_bytes(b"x")
    (assets / ".DS_Store").write_bytes(b"junk")
    (assets / "sub").mkdir()
    (assets / "sub" / ".DS_Store").write_bytes(b"junk")
    (assets / "sub" / "ok.css").write_bytes(b"ok")
    tree = _plan(assets_dir=assets)
    brand = [k for k in tree if k.startswith("staged/_brand/")]
    assert brand == ["staged/_brand/sub/ok.css"]


def test_dangling_links_are_replaced_not_written_through(tmp_path: Path) -> None:
    """A link whose target is missing is replaced by a regular file, both ways.

    Dies on: deciding a link is absent because its target is (``exists()`` in
    place of ``lexists``), which creates the target outside the root.
    """
    for writer in (write_tree, sync_tree):
        outside = tmp_path / f"outside-{writer.__name__}"
        outside.mkdir()
        root = tmp_path / f"live-{writer.__name__}"
        (root / "staged").mkdir(parents=True)
        os.symlink(outside / "absent.yml", root / "mkdocs.yml")
        os.symlink(outside / "absent.md", root / "staged" / "want.md")
        tree = {"mkdocs.yml": b"a: 1\n", "staged/want.md": b"w"}
        writer(tree, root)
        assert list(outside.iterdir()) == [], writer.__name__
        assert _files(root) == tree
        assert not (root / "mkdocs.yml").is_symlink()
        assert not (root / "staged" / "want.md").is_symlink()
