"""Page selection, page state and the publish subject (publish-core Req 6.6,
7.2, 7.3, 7.8, 11.7).

The page builders here are local to this module (task 5.3).
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from fitdocs.docmerge import RegionError, extract_regions, region_block
from fitdocs.layout import ARCHIVE_DIR, WORKOUTS_DIR
from fitdocs.publish.pages import (
    PageSelectionError,
    PageStatus,
    PageView,
    SelectedPage,
    completed_activity,
    read_page,
    select_pages,
    sha_index,
    source_shas,
)

SHA_A = "a" * 63 + "1"
SHA_B = "b" * 63 + "2"
SHA_C = "c" * 63 + "3"
SHA_D = "d" * 63 + "4"

#: The landed document-format version a current page carries.
CURRENT_VERSION = 12


def _ref(sha: str) -> str:
    return f"fit-archive/{sha}.fit"


def _frontmatter(**changes: object) -> dict[str, object]:
    """A current run page's frontmatter; a ``None`` change removes the key."""
    fm: dict[str, object] = {
        "type": "workout",
        "doc_version": CURRENT_VERSION,
        "sport": "Run",
        "start_time": "2026-03-04T07:05:00+01:00",
        "source_elapsed_s": 3725.5,
        "source_distance_m": 12500.25,
        "sources": [_ref(SHA_A)],
    }
    for key, value in changes.items():
        if value is None:
            del fm[key]
        else:
            fm[key] = value
    return fm


def _text(fm: dict[str, object], body: str | None = None) -> str:
    if body is None:
        body = (
            "# Run\n\n"
            + region_block("notes", "my notes")
            + region_block("post", "my post")
            + region_block("published", "")
        )
    return f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n\n{body}"


def _write(
    root: Path, name: str, fm: dict[str, object], body: str | None = None
) -> Path:
    workouts = root / WORKOUTS_DIR
    workouts.mkdir(parents=True, exist_ok=True)
    path = workouts / name
    path.write_text(_text(fm, body), encoding="utf-8")
    return path


def _rels(pages: tuple[SelectedPage, ...]) -> list[str]:
    return [page.rel for page in pages]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    return data


@pytest.fixture
def elsewhere(tmp_path: Path) -> Path:
    other = tmp_path / "elsewhere"
    other.mkdir()
    return other


# ------------------------------------------------------------------ selection


class TestSelectAll:
    def test_every_top_level_workout_page_in_file_name_order(self, root: Path) -> None:
        # Created out of name order; start dates run opposite to the names.
        _write(root, "b-ride.md", _frontmatter(start_time="2026-01-01T07:00:00+01:00"))
        _write(root, "c.md", _frontmatter(start_time="2026-02-01T07:00:00+01:00"))
        _write(root, "a-run.md", _frontmatter(start_time="2026-03-01T07:00:00+01:00"))
        pages = select_pages(root, [], cwd=root)
        assert _rels(pages) == [
            "workouts/a-run.md",
            "workouts/b-ride.md",
            "workouts/c.md",
        ]
        assert [page.path for page in pages] == [
            root / "workouts" / "a-run.md",
            root / "workouts" / "b-ride.md",
            root / "workouts" / "c.md",
        ]
        assert [page.named for page in pages] == [False, False, False]

    def test_skips_what_is_not_a_top_level_workout_page(
        self, root: Path, elsewhere: Path
    ) -> None:
        _write(root, "keep.md", _frontmatter())
        workouts = root / "workouts"
        # A symlink to a real workout page, a page of somebody else's type,
        # text with no frontmatter, a nested page, a directory named like a
        # page, a non-markdown file, and a page with an unreadable block.
        real = _write(elsewhere, "real.md", _frontmatter())
        (workouts / "link.md").symlink_to(real)
        _write(root, "other.md", _frontmatter(type="note"))
        (workouts / "plain.md").write_text("no frontmatter\n", encoding="utf-8")
        _write(root / "workouts", "nested.md", _frontmatter())
        (workouts / "folder.md").mkdir()
        (workouts / "folder.md" / "inner.md").write_text(
            _text(_frontmatter()), encoding="utf-8"
        )
        (workouts / "page.txt").write_text(_text(_frontmatter()), encoding="utf-8")
        (workouts / "bad.md").write_bytes(b"---\ntype: workout\n\xff\xfe\n---\n")
        assert (workouts / "link.md").is_symlink()
        assert _rels(select_pages(root, [], cwd=root)) == ["workouts/keep.md"]

    def test_no_workouts_directory_selects_nothing(self, root: Path) -> None:
        assert not (root / "workouts").exists()
        assert select_pages(root, [], cwd=root) == ()


class TestSelectNamed:
    def test_a_bare_name_with_or_without_the_suffix(self, root: Path) -> None:
        _write(root, "a.md", _frontmatter())
        _write(root, "b.md", _frontmatter())
        for name in ("a", "a.md"):
            (page,) = select_pages(root, [name], cwd=root)
            assert page == SelectedPage(
                path=root / "workouts" / "a.md", rel="workouts/a.md", named=True
            )

    def test_a_path_from_the_working_directory(
        self, root: Path, elsewhere: Path
    ) -> None:
        _write(root, "a.md", _frontmatter())
        for cwd, name in (
            (root, "workouts/a.md"),
            (root / "workouts", "./a.md"),
            (elsewhere, os.path.relpath(root / "workouts" / "a.md", elsewhere)),
            (elsewhere, str(root / "workouts" / "a.md")),
        ):
            (page,) = select_pages(root, [name], cwd=cwd)
            assert page.rel == "workouts/a.md"
            assert page.named is True

    def test_duplicates_collapse_and_order_is_by_file_name(self, root: Path) -> None:
        for name in ("a.md", "b.md", "c.md"):
            _write(root, name, _frontmatter())
        pages = select_pages(
            root, ["c", "a.md", "workouts/c.md", "a", "b", "b.md"], cwd=root
        )
        assert _rels(pages) == ["workouts/a.md", "workouts/b.md", "workouts/c.md"]

    def test_named_pages_are_chosen_not_all(self, root: Path) -> None:
        for name in ("a.md", "b.md", "c.md"):
            _write(root, name, _frontmatter())
        assert _rels(select_pages(root, ["c"], cwd=root)) == ["workouts/c.md"]

    @pytest.mark.parametrize("name", ["missing", "missing.md", "workouts/missing.md"])
    def test_a_name_that_resolves_to_nothing_is_refused(
        self, root: Path, name: str
    ) -> None:
        _write(root, "a.md", _frontmatter())
        with pytest.raises(PageSelectionError, match="missing"):
            select_pages(root, [name], cwd=root)

    def test_a_directory_is_not_a_page(self, root: Path) -> None:
        _write(root, "a.md", _frontmatter())
        (root / "workouts" / "assets").mkdir()
        with pytest.raises(PageSelectionError, match="assets"):
            select_pages(root, ["assets"], cwd=root)

    @pytest.mark.parametrize("name", ["link", "link.md", "workouts/link.md"])
    def test_a_symlink_is_refused(self, root: Path, elsewhere: Path, name: str) -> None:
        real = _write(elsewhere, "real.md", _frontmatter())
        _write(root, "a.md", _frontmatter())
        (root / "workouts" / "link.md").symlink_to(real)
        assert (
            read_page(SelectedPage(real, "workouts/real.md", named=True)) is not None
        ), "the symlink's target is a readable workout page"
        with pytest.raises(PageSelectionError, match="symlink"):
            select_pages(root, [name], cwd=root)

    def test_a_symlink_to_a_page_in_workouts_is_refused(self, root: Path) -> None:
        real = _write(root, "real.md", _frontmatter())
        (root / "workouts" / "alias.md").symlink_to(real)
        with pytest.raises(PageSelectionError, match="symlink"):
            select_pages(root, ["alias.md"], cwd=root)
        with pytest.raises(PageSelectionError, match="symlink"):
            select_pages(root, ["workouts/alias.md"], cwd=root)

    def test_a_file_elsewhere_is_refused(self, root: Path, elsewhere: Path) -> None:
        _write(root, "a.md", _frontmatter())
        outside = _write(elsewhere, "a.md", _frontmatter())
        inside_data = root / "history" / "a.md"
        inside_data.parent.mkdir()
        inside_data.write_text(_text(_frontmatter()), encoding="utf-8")
        nested = _write(root / "workouts", "deep.md", _frontmatter())
        for name in (str(outside), str(inside_data), str(nested)):
            assert Path(name).is_file(), "the refused file is a readable workout page"
            with pytest.raises(PageSelectionError, match="directly in"):
                select_pages(root, [name], cwd=root)

    def test_a_page_that_is_not_a_workout_page_is_refused(self, root: Path) -> None:
        _write(root, "note.md", _frontmatter(type="note"))
        (root / "workouts" / "plain.md").write_text("hello\n", encoding="utf-8")
        for name in ("note", "plain"):
            with pytest.raises(PageSelectionError, match="not a workout page"):
                select_pages(root, [name], cwd=root)

    def test_a_readable_non_workout_or_non_document_is_still_refused(
        self, root: Path
    ) -> None:
        _write(root, "note.md", _frontmatter(type="note"))
        workouts = root / "workouts"
        (workouts / "bare.md").write_text("---\n- a\n- b\n---\n", encoding="utf-8")
        (workouts / "empty.md").write_bytes(b"")
        for name in ("note", "bare", "empty"):
            with pytest.raises(PageSelectionError, match="not a workout page"):
                select_pages(root, [name], cwd=root)

    @pytest.mark.parametrize("kind", ["utf8", "yaml", "permission"])
    def test_an_unreadable_named_page_is_selected_and_reads_as_none(
        self, root: Path, kind: str
    ) -> None:
        path = _write(root, "bad.md", _frontmatter())
        if kind == "utf8":
            path.write_bytes(b"---\ntype: workout\n\xff\xfe\n---\n")
        elif kind == "yaml":
            path.write_text("---\ndate: 2026-02-30\n---\n", encoding="utf-8")
        else:
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                pytest.skip("root reads files whatever their mode")
            path.chmod(0)
        try:
            (page,) = select_pages(root, ["bad"], cwd=root)
            assert page == SelectedPage(path, "workouts/bad.md", named=True)
            assert read_page(page) is None
        finally:
            path.chmod(0o644)

    def test_a_relative_name_cannot_escape_workouts_by_dotdot(self, root: Path) -> None:
        _write(root, "a.md", _frontmatter())
        history = root / "history"
        history.mkdir()
        (history / "a.md").write_text(_text(_frontmatter()), encoding="utf-8")
        with pytest.raises(PageSelectionError, match="directly in"):
            select_pages(root, ["workouts/../history/a.md"], cwd=root)
        with pytest.raises(PageSelectionError, match="directly in"):
            select_pages(root, ["../history/a.md"], cwd=root / "workouts")

    def test_a_relative_name_from_inside_workouts_to_a_sibling_is_refused(
        self, root: Path
    ) -> None:
        _write(root, "a.md", _frontmatter())
        other = root / "elsewhere"
        other.mkdir()
        (other / "a.md").write_text(_text(_frontmatter()), encoding="utf-8")
        with pytest.raises(PageSelectionError, match="directly in"):
            select_pages(root, ["../elsewhere/a.md"], cwd=root / "workouts")

    def test_a_symlinked_data_root_selects_by_identity(
        self, root: Path, tmp_path: Path
    ) -> None:
        real = _write(root, "a.md", _frontmatter())
        alias = tmp_path / "alias-root"
        alias.symlink_to(root, target_is_directory=True)
        real_workouts = root / "workouts"
        for name in ("./a.md", str(real)):
            (page,) = select_pages(alias, [name], cwd=real_workouts)
            assert page.rel == "workouts/a.md"
            assert page.path == alias / "workouts" / "a.md"
            assert page.named is True

    def test_a_directory_named_like_the_bare_name_does_not_shadow_the_page(
        self, root: Path
    ) -> None:
        _write(root, "x.md", _frontmatter())
        (root / "workouts" / "x").mkdir()
        (page,) = select_pages(root, ["x"], cwd=root)
        assert page.rel == "workouts/x.md"

    def test_case_variants_of_one_file_are_one_page_named_as_on_disk(
        self, root: Path
    ) -> None:
        _write(root, "a.md", _frontmatter())
        if not (root / "workouts" / "A.MD").exists():
            pytest.skip("case-sensitive file system")
        for names in (["A", "a"], ["A", "a", "A.md"], ["a", "Workouts/A.MD"]):
            pages = select_pages(root, names, cwd=root)
            assert _rels(pages) == ["workouts/a.md"], names
            assert pages[0].path == root / "workouts" / "a.md"

    def test_a_symlink_alias_sorting_first_does_not_take_the_real_page_name(
        self, root: Path
    ) -> None:
        real = _write(root, "real.md", _frontmatter())
        (root / "workouts" / "alias.md").symlink_to(real)
        expected = SelectedPage(real, "workouts/real.md", named=True)
        for name in ("real", "workouts/real.md"):
            assert select_pages(root, [name], cwd=root) == (expected,)
        assert read_page(expected) is not None

    def test_a_case_variant_beside_a_symlink_alias_is_named_as_on_disk(
        self, root: Path
    ) -> None:
        real = _write(root, "real.md", _frontmatter())
        (root / "workouts" / "alias.md").symlink_to(real)
        if not (root / "workouts" / "REAL.MD").exists():
            pytest.skip("case-sensitive file system")
        expected = SelectedPage(real, "workouts/real.md", named=True)
        assert select_pages(root, ["REAL"], cwd=root) == (expected,)

    def test_hard_links_keep_the_typed_name_and_collapse_to_the_first_named(
        self, root: Path
    ) -> None:
        a = _write(root, "a.md", _frontmatter())
        os.link(a, root / "workouts" / "b.md")
        workouts = root / "workouts"
        (only_b,) = select_pages(root, ["b"], cwd=root)
        assert only_b == SelectedPage(workouts / "b.md", "workouts/b.md", named=True)
        (only_a,) = select_pages(root, ["a"], cwd=root)
        assert only_a.rel == "workouts/a.md"
        (first_named,) = select_pages(root, ["a", "b"], cwd=root)
        assert first_named.rel == "workouts/a.md"
        (first_named,) = select_pages(root, ["b", "a"], cwd=root)
        assert first_named.rel == "workouts/b.md"

    def test_an_entry_that_vanishes_during_the_name_lookup_is_skipped(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = _write(root, "a.md", _frontmatter())
        os.link(a, root / "workouts" / "b.md")
        real_lstat = os.lstat

        def lstat(path: str | Path) -> os.stat_result:
            if Path(path).name == "a.md":
                raise FileNotFoundError(path)
            return real_lstat(path)

        monkeypatch.setattr(os, "lstat", lstat)
        (page,) = select_pages(root, ["b"], cwd=root)
        assert page.rel == "workouts/b.md"

    def test_a_directory_that_cannot_be_listed_keeps_the_typed_name(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(root, "a.md", _frontmatter())

        def listdir(path: object = ".") -> list[str]:
            raise PermissionError(path)

        monkeypatch.setattr(os, "listdir", listdir)
        (page,) = select_pages(root, ["a"], cwd=root)
        assert page == SelectedPage(
            root / "workouts" / "a.md", "workouts/a.md", named=True
        )

    def test_a_lookup_that_finds_no_entry_keeps_the_typed_name(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(root, "a.md", _frontmatter())
        real_lstat = os.lstat
        real_listdir = os.listdir
        listed: list[bool] = []

        def listdir(path: str | Path) -> list[str]:
            listed.append(True)
            return real_listdir(path)

        def lstat(path: str | Path) -> os.stat_result:
            if listed and Path(path).name == "a.md":
                raise FileNotFoundError(path)
            return real_lstat(path)

        monkeypatch.setattr(os, "listdir", listdir)
        monkeypatch.setattr(os, "lstat", lstat)
        (page,) = select_pages(root, ["a"], cwd=root)
        assert listed, "the name lookup listed the directory"
        assert page.rel == "workouts/a.md"

    def test_a_case_variant_of_hard_linked_pages_takes_the_first_in_name_order(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = _write(root, "a.md", _frontmatter())
        os.link(a, root / "workouts" / "b.md")
        if not (root / "workouts" / "A.MD").exists():
            pytest.skip("case-sensitive file system")
        for name in ("A", "B"):
            (page,) = select_pages(root, [name], cwd=root)
            assert page.rel == "workouts/a.md", name
        real_listdir = os.listdir

        def backwards(path: str | Path) -> list[str]:
            return sorted(real_listdir(path), reverse=True)

        monkeypatch.setattr(os, "listdir", backwards)
        (page,) = select_pages(root, ["B"], cwd=root)
        assert page.rel == "workouts/a.md", "whatever order the directory lists"

    def test_the_page_path_keeps_the_file_names_own_case(self, root: Path) -> None:
        _write(root, "Mixed-Case.md", _frontmatter())
        (page,) = select_pages(root, ["Mixed-Case"], cwd=root)
        assert page.path == root / "workouts" / "Mixed-Case.md"
        assert page.rel == "workouts/Mixed-Case.md"

    def test_a_bare_name_tries_itself_before_adding_the_suffix(
        self, root: Path
    ) -> None:
        _write(root, "x", _frontmatter(sport="Ride"))
        _write(root, "x.md", _frontmatter())
        (page,) = select_pages(root, ["x"], cwd=root)
        assert page.rel == "workouts/x"

    def test_a_name_with_the_suffix_is_not_tried_with_another(self, root: Path) -> None:
        _write(root, "a.md.md", _frontmatter())
        with pytest.raises(PageSelectionError, match="no such page"):
            select_pages(root, ["a.md"], cwd=root)

    def test_refusals_say_which_kind_of_miss_it_was(self, root: Path) -> None:
        _write(root, "a.md", _frontmatter())
        with pytest.raises(PageSelectionError, match="no such page"):
            select_pages(root, ["missing"], cwd=root)
        with pytest.raises(PageSelectionError, match="no such file"):
            select_pages(root, ["workouts/missing.md"], cwd=root)

    def test_a_dangling_symlink_by_path_is_a_symlink_not_a_missing_file(
        self, root: Path
    ) -> None:
        _write(root, "a.md", _frontmatter())
        (root / "workouts" / "dangling.md").symlink_to(root / "nowhere.md")
        for name in ("workouts/dangling.md", "dangling"):
            with pytest.raises(PageSelectionError, match="symlink"):
                select_pages(root, [name], cwd=root)

    def test_without_a_workouts_directory_a_path_elsewhere_is_refused(
        self, root: Path, elsewhere: Path
    ) -> None:
        outside = _write(elsewhere, "a.md", _frontmatter())
        assert not (root / "workouts").exists()
        assert read_page(SelectedPage(outside, "x", named=True)) is not None
        relative = os.path.relpath(outside, root)
        for name in (str(outside), relative):
            with pytest.raises(PageSelectionError, match="directly in"):
                select_pages(root, [name], cwd=root)

    def test_a_fifo_is_refused_without_being_opened(self, root: Path) -> None:
        if not hasattr(os, "mkfifo"):
            pytest.skip("no mkfifo")
        (root / "workouts").mkdir()
        os.mkfifo(root / "workouts" / "f.md")
        outcome: list[BaseException | None] = []

        def attempt(name: str) -> None:
            try:
                select_pages(root, [name], cwd=root)
                outcome.append(None)
            except BaseException as exc:  # noqa: BLE001 - reported below
                outcome.append(exc)

        for name in ("f", "workouts/f.md"):
            outcome.clear()
            thread = threading.Thread(target=attempt, args=(name,), daemon=True)
            thread.start()
            thread.join(timeout=5)
            assert not thread.is_alive(), f"{name}: selection hung on the fifo"
            (error,) = outcome
            assert isinstance(error, PageSelectionError), error
            assert "not a file" in str(error)

    def test_one_refused_name_refuses_the_selection(self, root: Path) -> None:
        _write(root, "a.md", _frontmatter())
        with pytest.raises(PageSelectionError, match="missing"):
            select_pages(root, ["a", "missing"], cwd=root)


# ---------------------------------------------------------------------- state


def _view(root: Path, fm: dict[str, object], body: str | None = None) -> PageView:
    path = _write(root, "p.md", fm, body)
    view = read_page(SelectedPage(path, "workouts/p.md", named=True))
    assert view is not None
    return view


class TestPageState:
    def test_current_carries_its_regions_and_frontmatter(self, root: Path) -> None:
        body = (
            region_block("notes", "N text")
            + region_block("post", "P text")
            + region_block("published", "Q text")
        )
        view = _view(root, _frontmatter(), body)
        assert view.status is PageStatus.CURRENT
        assert view.regions == {
            "notes": "N text",
            "post": "P text",
            "published": "Q text",
        }
        assert view.detail is None
        assert view.frontmatter["sport"] == "Run"
        assert view.text.endswith(body)
        assert view.text.startswith("---\n")

    @pytest.mark.parametrize(
        "version", [11, 1, 0, -3, None, "12", True, 12.0, [12]], ids=repr
    )
    def test_an_absent_lower_or_unusable_version_is_older(
        self, root: Path, version: object
    ) -> None:
        view = _view(root, _frontmatter(doc_version=version))
        assert view.status is PageStatus.OLDER
        assert view.regions is None
        assert view.detail is None

    @pytest.mark.parametrize("version", [13, 14, 999])
    def test_a_higher_version_is_newer(self, root: Path, version: int) -> None:
        view = _view(root, _frontmatter(doc_version=version))
        assert view.status is PageStatus.NEWER
        assert view.regions is None
        assert view.detail is None

    def test_version_decides_before_the_regions_are_read(self, root: Path) -> None:
        damaged = "<!-- fitdocs:begin:post -->\nno end\n"
        with pytest.raises(RegionError):
            extract_regions(damaged)
        assert _view(root, _frontmatter(doc_version=11), damaged).status is (
            PageStatus.OLDER
        )
        assert _view(root, _frontmatter(doc_version=13), damaged).status is (
            PageStatus.NEWER
        )

    def test_damaged_markers_carry_the_region_error(self, root: Path) -> None:
        body = (
            region_block("notes", "n")
            + "<!-- fitdocs:begin:post -->\nunclosed\n"
            + region_block("published", "")
        )
        with pytest.raises(RegionError) as raised:
            extract_regions(body)
        message = str(raised.value)
        assert message
        view = _view(root, _frontmatter(), body)
        assert view.status is PageStatus.DAMAGED
        assert view.detail == message
        assert view.regions is None

    @pytest.mark.parametrize(
        ("kept", "missing"),
        [
            (("notes", "published"), "post"),
            (("notes", "post"), "published"),
            (("notes",), "post"),
            ((), "post"),
        ],
        ids=["no-post", "no-published", "neither-names-post", "no-regions"],
    )
    def test_a_current_page_missing_a_new_region_is_damaged(
        self, root: Path, kept: tuple[str, ...], missing: str
    ) -> None:
        body = "".join(region_block(name, f"{name} text") for name in kept)
        assert "post" not in kept or "published" not in kept
        view = _view(root, _frontmatter(), body)
        assert view.status is PageStatus.DAMAGED
        assert view.regions is None
        assert view.detail == (f"the page has no {missing} region; run fitdocs regen")

    def test_unreadable_or_foreign_pages_read_as_none(
        self, root: Path, elsewhere: Path
    ) -> None:
        workouts = root / "workouts"
        workouts.mkdir()
        (workouts / "bad.md").write_bytes(b"\xff\xfe")
        (workouts / "plain.md").write_text("hello\n", encoding="utf-8")
        _write(root, "note.md", _frontmatter(type="note"))
        real = _write(elsewhere, "real.md", _frontmatter())
        (workouts / "link.md").symlink_to(real)
        for name in ("bad.md", "plain.md", "note.md", "link.md", "gone.md"):
            page = SelectedPage(workouts / name, f"workouts/{name}", named=True)
            assert read_page(page) is None, name


# -------------------------------------------------------------------- subject


def _archive(root: Path, sha: str, *, kind: str = "file") -> Path:
    path = root / ARCHIVE_DIR / f"{sha}.fit"
    path.parent.mkdir(exist_ok=True)
    if kind == "file":
        path.write_bytes(b"\x0e\x10")
    else:
        path.mkdir()
    return path


class TestCompletedActivity:
    def test_a_full_page_builds_every_field(self, root: Path) -> None:
        base = _archive(root, SHA_B)
        fm = _frontmatter(sources=[_ref(SHA_C), _ref(SHA_A), _ref(SHA_B)])
        subject = completed_activity(fm, root)
        assert subject is not None
        assert subject.sport == "Run"
        assert subject.start == datetime(
            2026, 3, 4, 7, 5, tzinfo=timezone(timedelta(hours=1))
        )
        assert subject.start.utcoffset() == timedelta(hours=1)
        assert subject.elapsed_s == 3725.5
        assert subject.distance_m == 12500.25
        assert subject.base_fit == base

    def test_source_digests_keep_rank_order_not_sorted_order(self, root: Path) -> None:
        refs = [_ref(SHA_C), _ref(SHA_A), _ref(SHA_D), _ref(SHA_B)]
        assert sorted(refs) != refs
        subject = completed_activity(_frontmatter(sources=refs), root)
        assert subject is not None
        assert subject.source_shas == (SHA_C, SHA_A, SHA_D, SHA_B)
        assert source_shas(_frontmatter(sources=refs)) == subject.source_shas

    def test_digests_are_lowercased_and_foreign_refs_dropped(self) -> None:
        fm = _frontmatter(
            sources=[
                _ref("AB" * 32),
                "elsewhere/" + SHA_A + ".fit",
                7,
                _ref("../" + SHA_B),
                _ref(SHA_C),
            ]
        )
        assert source_shas(fm) == ("ab" * 32, SHA_C)

    def test_an_uppercase_base_ref_finds_the_lowercase_archive_file(
        self, root: Path
    ) -> None:
        upper = SHA_A.upper()
        assert upper != SHA_A
        archived = _archive(root, SHA_A)
        subject = completed_activity(_frontmatter(sources=[_ref(upper)]), root)
        assert subject is not None
        assert subject.base_fit == archived

    def test_base_fit_is_the_last_ref_and_only_when_a_file(self, root: Path) -> None:
        _archive(root, SHA_A)  # an extra, present
        fm = _frontmatter(sources=[_ref(SHA_A), _ref(SHA_B)])
        subject = completed_activity(fm, root)
        assert subject is not None
        assert subject.base_fit is None, "base file absent; an extra is not the base"
        _archive(root, SHA_B, kind="dir")
        subject = completed_activity(fm, root)
        assert subject is not None
        assert subject.base_fit is None, "base path is a directory, not a file"

    def test_a_foreign_last_ref_has_no_base_file(self, root: Path) -> None:
        _archive(root, SHA_A)
        fm = _frontmatter(sources=[_ref(SHA_A), "elsewhere/x.fit"])
        subject = completed_activity(fm, root)
        assert subject is not None
        assert subject.source_shas == (SHA_A,)
        assert subject.base_fit is None

    def test_no_sources_is_empty_not_invented(self, root: Path) -> None:
        subject = completed_activity(_frontmatter(sources=None), root)
        assert subject is not None
        assert subject.source_shas == ()
        assert subject.base_fit is None

    def test_absent_elapsed_and_distance_are_none_each_alone(self, root: Path) -> None:
        no_elapsed = completed_activity(_frontmatter(source_elapsed_s=None), root)
        no_distance = completed_activity(_frontmatter(source_distance_m=None), root)
        neither = completed_activity(
            _frontmatter(source_elapsed_s=None, source_distance_m=None), root
        )
        assert (
            no_elapsed is not None and no_distance is not None and neither is not None
        )
        assert (no_elapsed.elapsed_s, no_elapsed.distance_m) == (None, 12500.25)
        assert (no_distance.elapsed_s, no_distance.distance_m) == (3725.5, None)
        assert (neither.elapsed_s, neither.distance_m) == (None, None)

    def test_a_recorded_zero_is_zero_and_an_unusable_value_is_none(
        self, root: Path
    ) -> None:
        zero = completed_activity(
            _frontmatter(source_elapsed_s=0, source_distance_m=0.0), root
        )
        junk = completed_activity(
            _frontmatter(source_elapsed_s="long", source_distance_m=-5.0), root
        )
        assert zero is not None and junk is not None
        assert (zero.elapsed_s, zero.distance_m) == (0.0, 0.0)
        assert (junk.elapsed_s, junk.distance_m) == (None, None)

    @pytest.mark.parametrize("sport", [None, "", 7, ["Run"]], ids=repr)
    def test_no_usable_sport_gives_no_subject(self, root: Path, sport: object) -> None:
        assert completed_activity(_frontmatter(sport=sport), root) is None

    @pytest.mark.parametrize(
        "start",
        [
            None,
            "2026-03-04T07:05:00",  # naive string
            "2026-03-04",  # a bare date
            "tomorrow",
            "",
            12,
            datetime(2026, 3, 4, 7, 5),  # naive datetime
        ],
        ids=repr,
    )
    def test_no_aware_start_gives_no_subject(self, root: Path, start: object) -> None:
        assert completed_activity(_frontmatter(start_time=start), root) is None

    def test_an_aware_datetime_value_is_accepted(self, root: Path) -> None:
        start = datetime(2026, 3, 4, 7, 5, tzinfo=UTC)
        subject = completed_activity(_frontmatter(start_time=start), root)
        assert subject is not None
        assert subject.start == start

    def test_sport_is_verbatim(self, root: Path) -> None:
        subject = completed_activity(_frontmatter(sport="Trail Run"), root)
        assert subject is not None
        assert subject.sport == "Trail Run"


# ------------------------------------------------------------------ sha index


class TestShaIndex:
    def test_a_digest_in_two_pages_lists_both_in_file_name_order(
        self, root: Path
    ) -> None:
        _write(root, "z.md", _frontmatter(sources=[_ref(SHA_A), _ref(SHA_B)]))
        _write(root, "m.md", _frontmatter(sources=[_ref(SHA_B), _ref(SHA_C)]))
        _write(root, "e.md", _frontmatter(sources=[_ref(SHA_D)]))
        index = sha_index(root)
        assert dict(index) == {
            SHA_A: ("workouts/z.md",),
            SHA_B: ("workouts/m.md", "workouts/z.md"),
            SHA_C: ("workouts/m.md",),
            SHA_D: ("workouts/e.md",),
        }

    def test_every_workout_page_counts_whatever_its_state(self, root: Path) -> None:
        _write(root, "cur.md", _frontmatter(sources=[_ref(SHA_A)]))
        _write(root, "old.md", _frontmatter(doc_version=3, sources=[_ref(SHA_A)]))
        _write(root, "new.md", _frontmatter(doc_version=99, sources=[_ref(SHA_A)]))
        _write(
            root,
            "dam.md",
            _frontmatter(sources=[_ref(SHA_A)]),
            "<!-- fitdocs:begin:post -->\n",
        )
        _write(root, "nosport.md", _frontmatter(sport=None, sources=[_ref(SHA_A)]))
        assert list(sha_index(root)[SHA_A]) == [
            "workouts/cur.md",
            "workouts/dam.md",
            "workouts/new.md",
            "workouts/nosport.md",
            "workouts/old.md",
        ]

    def test_other_files_do_not_count(self, root: Path, elsewhere: Path) -> None:
        _write(root, "ok.md", _frontmatter(sources=[_ref(SHA_A)]))
        _write(root, "note.md", _frontmatter(type="note", sources=[_ref(SHA_B)]))
        real = _write(elsewhere, "real.md", _frontmatter(sources=[_ref(SHA_C)]))
        (root / "workouts" / "link.md").symlink_to(real)
        assert dict(sha_index(root)) == {SHA_A: ("workouts/ok.md",)}

    def test_a_digest_repeated_inside_one_page_names_it_once(self, root: Path) -> None:
        _write(root, "a.md", _frontmatter(sources=[_ref(SHA_A), _ref(SHA_A)]))
        assert dict(sha_index(root)) == {SHA_A: ("workouts/a.md",)}

    def test_no_workouts_directory_is_an_empty_index(self, root: Path) -> None:
        assert dict(sha_index(root)) == {}
