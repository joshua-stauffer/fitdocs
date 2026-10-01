"""One build into one root: the order of steps, the guard and the failure rules.

Covers 2.9, 6.6 and 6.7. The generator is replaced by a recording stub, so no
test here runs Zensical. Every build goes into a ``tmp_path`` root, and every
test that changes the template, the content or the repository layout works on a
``tmp_path`` copy; the real fixture tree and the real ``website/`` are only
read.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from scripts.sitebuild import pipeline
from scripts.sitebuild.generator import GeneratorResult
from scripts.sitebuild.model import Problem
from scripts.sitebuild.pipeline import (
    DEFAULT_BUILD_ROOT,
    DEFAULT_PREVIEW_ROOT,
    BuildOutcome,
    BuildRootRefused,
    build,
    guard_root,
)

from tests.sitebuild.conftest import copy_fixture_tree

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "site"
TEMPLATE = REPO_ROOT / "website" / "mkdocs.template.yml"

EXPECTED_TREE = {
    "mkdocs.yml",
    "overrides/home.html",
    "staged/_brand/brand.css",
    "staged/_brand/hero-chart.svg",
    "staged/_brand/logo.svg",
    "staged/get-started/first-run.md",
    "staged/get-started/install.md",
    "staged/guides/nested/deep.md",
    "staged/images/diagram.svg",
    "staged/index.md",
    "staged/llms-full.txt",
    "staged/llms.txt",
    "staged/llms/prompts.md",
    "staged/why.md",
}


class Recorder:
    """A stand-in for ``run_build`` that records its calls."""

    def __init__(self) -> None:
        self.roots: list[Path] = []
        self.seen_on_disk: list[set[str]] = []
        self.result = GeneratorResult(
            ok=True, problems=(), output="generator said hi\n"
        )
        self.make_html = True

    def __call__(self, root: Path) -> GeneratorResult:
        self.roots.append(root)
        self.seen_on_disk.append({p.name for p in root.iterdir()})
        if self.make_html:
            (root / "html").mkdir(exist_ok=True)
            (root / "html" / "index.html").write_text("<html></html>")
        return self.result


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(pipeline, "run_build", recorder)
    return recorder


def make_repo(tmp_path: Path, *, template: str | None = None) -> Path:
    """A repository skeleton under ``tmp_path`` with copies of website/ and docs/."""
    repo = tmp_path / "repo"
    website = repo / "website"
    website.mkdir(parents=True)
    for name in ("assets", "overrides"):
        shutil.copytree(REPO_ROOT / "website" / name, website / name)
    shutil.copytree(REPO_ROOT / "docs", repo / "docs")
    text = TEMPLATE.read_text(encoding="utf-8") if template is None else template
    (website / "mkdocs.template.yml").write_text(text, encoding="utf-8")
    return repo


def edited_template(old: str, new: str) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    return text.replace(old, new)


def break_a_link(content: Path) -> None:
    """Add a link to a file that does not exist, ahead of the annotation block."""
    why = content / "why.md"
    text = why.read_text(encoding="utf-8")
    anchor = "## Why a fixture exists\n"
    assert text.count(anchor) == 1
    why.write_text(
        text.replace(anchor, anchor + "\n[gone](missing-image.svg)\n"), encoding="utf-8"
    )


def rendered(outcome: BuildOutcome) -> list[str]:
    return [problem.render() for problem in outcome.problems]


def seed_stale_root(root: Path) -> None:
    """A root that an earlier successful build left behind, plus generator cache."""
    for name in ("html", "staged", "overrides"):
        (root / name).mkdir(parents=True)
        (root / name / "old.txt").write_text("old")
    (root / "mkdocs.yml").write_text("site_name: old\n")
    (root / ".cache").mkdir()
    (root / ".cache" / "keep.txt").write_text("cache")


def test_defaults_are_the_documented_relative_paths() -> None:
    """The two default roots are the documented ones, both under website/build.

    Dies on: `DEFAULT_BUILD_ROOT` set to `Path("website/build")` (or any other path).
    """
    assert Path("website/build/site") == DEFAULT_BUILD_ROOT
    assert Path("website/build/preview") == DEFAULT_PREVIEW_ROOT


def test_the_fixture_builds_its_expected_tree(tmp_path: Path, stub: Recorder) -> None:
    """The fixture plans exactly the documented tree, and the tree is on disk.

    The drafted page and the excluded ``_``/dot entries are absent, the llms
    files come from the build, the brand assets and the override are present,
    and the page count is the six included pages (the draft is not counted).

    Dies on: `page_count` off by one; `write_tree` skipped; the asset check
    looking up the bare reference instead of `staged/<reference>` (a false
    problem for the brand CSS).
    """
    root = tmp_path / "site"
    outcome = build(FIXTURE, root, repo_root=REPO_ROOT)
    assert outcome.problems == ()
    assert outcome.ok is True
    assert outcome.tree is not None
    assert set(outcome.tree) == EXPECTED_TREE
    assert outcome.page_count == 6
    on_disk = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.parts[len(root.parts)] != "html"
    }
    assert on_disk == EXPECTED_TREE
    assert (root / "mkdocs.yml").read_bytes() == outcome.tree["mkdocs.yml"]


def test_the_generator_sees_a_written_root_and_success_keeps_html(
    tmp_path: Path, stub: Recorder
) -> None:
    """A success calls the generator once, on the written root, and keeps ``html/``.

    Dies on: `run_build` called before `write_tree`; `html/` removed after a
    successful build; the generator output dropped from the outcome.
    """
    root = tmp_path / "site"
    outcome = build(FIXTURE, root, repo_root=REPO_ROOT)
    assert stub.roots == [root.resolve()]
    assert {"mkdocs.yml", "staged", "overrides"} <= stub.seen_on_disk[0]
    assert outcome.ok is True
    assert outcome.generator_output == "generator said hi\n"
    assert (root / "html" / "index.html").is_file()


def test_llms_texts_take_the_site_fields_from_the_template(
    tmp_path: Path, stub: Recorder
) -> None:
    """``site_name``, ``site_description`` and ``site_url`` come from the template.

    Three distinct values, so a swap of two of them shows.

    Dies on: `render_llms` given the description as `site_name` (or the name as
    the summary); `site_url` taken from anywhere but the template's `site_url`.
    """
    template = edited_template("site_name: fitdocs\n", "site_name: Zebra Docs\n")
    template = template.replace(
        "site_url: https://fitdocs.ai/\n", "site_url: https://zebra.example/x/\n"
    ).replace(
        "site_description: Turn .fit files into markdown workout pages you own.\n",
        "site_description: Stripes for everyone.\n",
    )
    assert "Zebra Docs" in template
    assert "zebra.example" in template
    assert "Stripes" in template
    repo = make_repo(tmp_path, template=template)
    outcome = build(FIXTURE, tmp_path / "out", repo_root=repo)
    assert outcome.ok is True and outcome.tree is not None
    llms = outcome.tree["staged/llms.txt"].decode("utf-8").splitlines()
    assert llms[0] == "# Zebra Docs"
    assert llms[2] == "> Stripes for everyone."
    assert any("(https://zebra.example/x/why/)" in line for line in llms)
    full = outcome.tree["staged/llms-full.txt"].decode("utf-8")
    assert "Source: https://zebra.example/x/why/\n" in full


@pytest.mark.parametrize("key", ["site_name", "site_description", "site_url"])
def test_a_template_without_a_llms_field_is_a_problem_not_a_crash(
    tmp_path: Path, stub: Recorder, key: str
) -> None:
    """A template lacking a field the llms texts need is reported and not built.

    The template also carries an unknown key, so the config problem is
    reported alongside the missing field.

    Dies on: the check for a missing template field removed, so the llms texts
    are rendered from whatever the template lacks; the config check skipped
    when a field is missing.
    """
    lines = TEMPLATE.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if not line.startswith(f"{key}:")]
    assert len(kept) == len(lines) - 1
    repo = make_repo(tmp_path, template="".join(kept) + "bogus_key: 1\n")
    outcome = build(FIXTURE, tmp_path / "out", repo_root=repo)
    assert outcome.ok is False
    assert outcome.tree is None
    assert sorted((p.path, p.where) for p in outcome.problems) == sorted(
        [
            ("website/mkdocs.template.yml", key),
            ("website/mkdocs.template.yml", "bogus_key"),
        ]
    )
    assert stub.roots == []


def test_content_and_template_problems_are_reported_together(
    tmp_path: Path, stub: Recorder
) -> None:
    """Content problems and an unreadable template come out of one build (2.9).

    The links and the config are not checked when the content did not load, so
    only the two upstream classes are present.

    Dies on: `build` returning after the content problems, before the template
    is loaded.
    """
    content = copy_fixture_tree(FIXTURE, tmp_path, "content")
    (content / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")
    repo = make_repo(tmp_path, template="site_name: [unclosed\n")
    outcome = build(content, tmp_path / "out", repo_root=repo)
    lines = rendered(outcome)
    assert len(lines) == 2, lines
    assert any(line.startswith("bad.md:") for line in lines)
    assert any(line.startswith("website/mkdocs.template.yml:") for line in lines)
    assert outcome.ok is False
    assert outcome.tree is None
    assert outcome.page_count == 0
    assert stub.roots == []
    assert not (tmp_path / "out").exists()


def test_link_and_config_problems_are_reported_together(
    tmp_path: Path, stub: Recorder
) -> None:
    """A broken link and a bad config key come out of one build, plus the asset check.

    The template carries an unknown top-level key and names a stylesheet that no
    planned path provides, so three classes are present at once (2.9).

    Dies on: `check_links` skipped; the first non-empty problem class returned
    alone; the referenced-asset check skipped.
    """
    content = copy_fixture_tree(FIXTURE, tmp_path, "content")
    break_a_link(content)
    template = edited_template(
        "extra_css:\n  - _brand/brand.css\n",
        "extra_css:\n  - _brand/absent.css\nbogus_key: 1\n",
    )
    repo = make_repo(tmp_path, template=template)
    outcome = build(content, tmp_path / "out", repo_root=repo)
    lines = rendered(outcome)
    assert len(lines) == 3, lines
    assert any(
        line.startswith("why.md:") and "missing-image.svg" in line for line in lines
    )
    assert any("bogus_key" in line for line in lines)
    assert any("_brand/absent.css" in line for line in lines)
    assert outcome.ok is False
    assert outcome.tree is None
    assert outcome.page_count == 6
    assert stub.roots == []


def test_a_broken_link_alone_is_reported_with_the_template_unloadable(
    tmp_path: Path, stub: Recorder
) -> None:
    """A template that cannot be read does not hide the link problems.

    Dies on: `check_links` placed after (and skipped by) the template-loaded
    guard.
    """
    content = copy_fixture_tree(FIXTURE, tmp_path, "content")
    break_a_link(content)
    repo = make_repo(tmp_path, template="- not\n- a mapping\n")
    outcome = build(content, tmp_path / "out", repo_root=repo)
    lines = rendered(outcome)
    assert len(lines) == 2, lines
    assert any(line.startswith("why.md:") for line in lines)
    assert any(line.startswith("website/mkdocs.template.yml:") for line in lines)
    assert stub.roots == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("extra_css:\n  - _brand/brand.css\n", "extra_css:\n  - _brand/absent.css\n"),
        ("  logo: _brand/logo.svg\n", "  logo: _brand/no-logo.svg\n"),
        ("  favicon: _brand/logo.svg\n", "  favicon: _brand/no-icon.svg\n"),
    ],
)
def test_a_referenced_asset_missing_from_the_planned_tree_is_reported(
    tmp_path: Path, stub: Recorder, old: str, new: str
) -> None:
    """An ``extra_css``, logo or favicon absent from ``staged/`` is one problem.

    The generator is not called and no ``html/`` remains.

    Dies on: the referenced-asset check skipped, or limited to `extra_css`.
    """
    repo = make_repo(tmp_path, template=edited_template(old, new))
    root = tmp_path / "out"
    seed_stale_root(root)
    outcome = build(FIXTURE, root, repo_root=repo)
    absent = new.split("_brand/")[1].split("\n")[0]
    lines = rendered(outcome)
    assert len(lines) == 1, lines
    assert absent in lines[0]
    assert outcome.ok is False
    assert outcome.tree is None
    assert stub.roots == []
    assert not (root / "html").exists()


def test_a_content_asset_satisfies_a_reference(tmp_path: Path, stub: Recorder) -> None:
    """A stylesheet reference to a content asset is in the planned tree, so it passes.

    The reference is to ``images/diagram.svg``, which only the content provides.

    Dies on: the asset check consulting only the brand assets instead of the
    whole planned tree.
    """
    template = edited_template(
        "extra_css:\n  - _brand/brand.css\n",
        "extra_css:\n  - _brand/brand.css\n  - images/diagram.svg\n",
    )
    repo = make_repo(tmp_path, template=template)
    outcome = build(FIXTURE, tmp_path / "out", repo_root=repo)
    assert outcome.problems == ()
    assert outcome.ok is True


def test_a_script_level_failure_clears_the_managed_paths_and_leaves_no_html(
    tmp_path: Path, stub: Recorder
) -> None:
    """A failed plan removes the stale managed paths (``html/`` too), not ``.cache/``.

    The root starts with a previous site in it, so absence afterwards is the
    build's doing.

    Dies on: clearing `html/` only after a successful build; the whole root
    removed instead of the managed paths.
    """
    content = copy_fixture_tree(FIXTURE, tmp_path, "content")
    (content / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")
    root = tmp_path / "out"
    seed_stale_root(root)
    for name in ("html", "staged", "overrides", "mkdocs.yml"):
        assert (root / name).exists()
    outcome = build(content, root, repo_root=REPO_ROOT)
    assert outcome.ok is False
    assert stub.roots == []
    assert sorted(p.name for p in root.iterdir()) == [".cache"]
    assert (root / ".cache" / "keep.txt").read_text() == "cache"


def test_a_generator_failure_removes_html_even_when_the_generator_made_it(
    tmp_path: Path, stub: Recorder
) -> None:
    """The generator's own problems are reported and ``html/`` is deleted (6.6).

    The stub writes ``html/`` and then fails, as the real generator does.

    Dies on: the `html/` removal on generator failure deleted; the generator's
    `tree` dropped from the failed outcome.
    """
    stub.result = GeneratorResult(
        ok=False,
        problems=(Problem("why.md", "3:1", "generator complained"),),
        output="raw generator output\n",
    )
    root = tmp_path / "out"
    outcome = build(FIXTURE, root, repo_root=REPO_ROOT)
    assert len(stub.roots) == 1
    assert (root / "mkdocs.yml").is_file()
    assert outcome.ok is False
    assert rendered(outcome) == ["why.md: 3:1: generator complained"]
    assert outcome.generator_output == "raw generator output\n"
    assert outcome.tree is not None
    assert set(outcome.tree) == EXPECTED_TREE
    assert not (root / "html").exists()


def test_generator_lines_on_the_home_page_are_mapped_to_source_lines(
    tmp_path: Path, stub: Recorder
) -> None:
    """Generator problems on ``index.md`` report the content file's line (6.5).

    The staged home page has one injected line, so the generator's line is one
    too high; other pages and path-less problems pass through unchanged.

    Dies on: the mapping dropped from ``build``; the mapping applied to every
    page; a path-less problem altered; ``where`` replaced by a fixed value.
    """
    stub.result = GeneratorResult(
        ok=False,
        problems=(
            Problem("index.md", "16:58", "home"),
            Problem("why.md", "16:58", "other"),
            Problem("site generator", "", "none"),
        ),
        output="",
    )
    outcome = build(FIXTURE, tmp_path / "out", repo_root=REPO_ROOT)
    assert rendered(outcome) == [
        "index.md: 15:58: home",
        "why.md: 16:58: other",
        "site generator: none",
    ]


def test_the_managed_paths_are_cleared_before_the_content_is_loaded(
    tmp_path: Path, stub: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stale site is gone by the time ``load_content`` runs (6.6, step 1).

    The wrapper looks at the root when it is called, and then raises, so a
    later clear cannot be what removed the files.

    Dies on: the clear moved to just before the `if collected:` check, or after
    the content is loaded.
    """
    root = tmp_path / "out"
    seed_stale_root(root)
    seen: list[tuple[bool, bool]] = []

    def spy(content_dir: Path) -> object:
        seen.append(((root / "html").exists(), (root / "mkdocs.yml").exists()))
        raise OSError("stop here")

    monkeypatch.setattr(pipeline, "load_content", spy)
    with pytest.raises(OSError, match="stop here"):
        build(FIXTURE, root, repo_root=REPO_ROOT)
    assert seen == [(False, False)]
    assert sorted(p.name for p in root.iterdir()) == [".cache"]
    assert stub.roots == []


def test_a_dotted_reference_to_a_planned_asset_is_accepted(
    tmp_path: Path, stub: Recorder
) -> None:
    """``./_brand/brand.css`` names the planned ``staged/_brand/brand.css``.

    Dies on: the reference looked up without `posixpath.normpath`.
    """
    template = edited_template(
        "extra_css:\n  - _brand/brand.css\n", "extra_css:\n  - ./_brand/brand.css\n"
    )
    repo = make_repo(tmp_path, template=template)
    outcome = build(FIXTURE, tmp_path / "out", repo_root=repo)
    assert outcome.problems == ()
    assert outcome.ok is True


def test_one_absent_file_named_twice_is_one_problem(
    tmp_path: Path, stub: Recorder
) -> None:
    """A logo and a favicon that share an absent file give one line.

    Dies on: the references not de-duplicated before the check.
    """
    template = edited_template(
        "  logo: _brand/logo.svg\n  favicon: _brand/logo.svg\n",
        "  logo: _brand/none.svg\n  favicon: _brand/none.svg\n",
    )
    repo = make_repo(tmp_path, template=template)
    outcome = build(FIXTURE, tmp_path / "out", repo_root=repo)
    lines = rendered(outcome)
    assert len(lines) == 1, lines
    assert "_brand/none.svg" in lines[0]


def test_a_stale_html_link_is_removed_and_its_target_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a failed generator run a ``html`` symlink is unlinked, not followed.

    The stub replaces ``html/`` with a link to a directory outside the root.

    Dies on: the `is_symlink()` branch of the removal dropped.
    """
    target = tmp_path / "target"
    target.mkdir()
    (target / "precious.txt").write_text("keep")
    root = tmp_path / "out"

    def link_html(built: Path) -> GeneratorResult:
        (built / "html").symlink_to(target)
        return GeneratorResult(ok=False, problems=(), output="")

    monkeypatch.setattr(pipeline, "run_build", link_html)
    outcome = build(FIXTURE, root, repo_root=REPO_ROOT)
    assert outcome.ok is False
    assert not (root / "html").is_symlink()
    assert not (root / "html").exists()
    assert (target / "precious.txt").read_text() == "keep"


def test_a_generator_failure_without_problems_is_still_a_failure(
    tmp_path: Path, stub: Recorder
) -> None:
    """``ok`` follows the generator's ``ok``, not the presence of problems.

    Dies on: `ok` computed as `not problems`; the `html/` removal keyed on
    `result.problems` instead of `result.ok`.
    """
    stub.result = GeneratorResult(ok=False, problems=(), output="exit 3\n")
    root = tmp_path / "out"
    outcome = build(FIXTURE, root, repo_root=REPO_ROOT)
    assert outcome.ok is False
    assert not (root / "html").exists()


def test_a_generator_that_raises_leaves_no_html(
    tmp_path: Path, stub: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exception out of the generator still removes ``html/`` (6.6).

    The stub creates ``html/`` and then raises, as a crashed generator
    might.

    A `KeyboardInterrupt` gets the same treatment.

    Dies on: the `html/` removal on an exception deleted (a bare call after
    `run_build` with no `except`); the handler narrowed to `Exception`.
    """

    def boom(root: Path) -> GeneratorResult:
        stub(root)
        raise RuntimeError("generator crashed")

    def interrupted(root: Path) -> GeneratorResult:
        stub(root)
        raise KeyboardInterrupt

    monkeypatch.setattr(pipeline, "run_build", boom)
    root = tmp_path / "out"
    with pytest.raises(RuntimeError, match="generator crashed"):
        build(FIXTURE, root, repo_root=REPO_ROOT)
    assert len(stub.roots) == 1
    assert (root / "html").exists() is False
    assert (root / "staged").is_dir()

    monkeypatch.setattr(pipeline, "run_build", interrupted)
    with pytest.raises(KeyboardInterrupt):
        build(FIXTURE, root, repo_root=REPO_ROOT)
    assert len(stub.roots) == 2
    assert (root / "html").exists() is False


def test_a_repo_internal_root_outside_website_build_is_refused(tmp_path: Path) -> None:
    """Inside the repository only ``website/build/`` may hold a root (6.7).

    Dies on: `guard_root` accepting the `website/build` directory itself, or
    matching `website/build` by string prefix (`website/build2`); the check
    limited to the repository root.
    """
    repo = tmp_path / "repo"
    (repo / "website" / "build").mkdir(parents=True)
    (repo / "website" / "content").mkdir()
    for refused in (
        repo,
        repo / "website",
        repo / "website" / "content",
        repo / "website" / "build",
        repo / "docs",
        repo / "website" / "build2",
        repo / "website" / "buildx" / "site",
    ):
        with pytest.raises(BuildRootRefused):
            guard_root(refused, repo_root=repo)


def test_the_repo_and_its_ancestors_are_refused_as_roots(tmp_path: Path) -> None:
    """A root equal to the repository, its parent or a grandparent is refused (6.7).

    Clearing the managed paths of such a root would reach outside
    ``website/build/``. A sibling of the repository stays allowed, and a link to
    the parent is refused because ``resolve`` follows it.

    Dies on: removing the ancestor check from `guard_root`.
    """
    repo = tmp_path / "parent" / "repo"
    (repo / "website" / "build").mkdir(parents=True)
    (tmp_path / "parent" / "sibling").mkdir()
    (tmp_path / "up").symlink_to(tmp_path / "parent", target_is_directory=True)
    for refused in (repo, repo.parent, tmp_path, tmp_path / "up", repo / ".." / ".."):
        with pytest.raises(BuildRootRefused):
            guard_root(refused, repo_root=repo)
    sibling = tmp_path / "parent" / "sibling"
    assert guard_root(sibling, repo_root=repo) == sibling.resolve()


def test_an_ancestor_root_is_refused_by_identity_not_path_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With ``Path.resolve`` made a no-op, a link to the parent is still refused.

    A comparison of the unresolved path text misses the link;
    ``os.path.samefile`` does not.

    Dies on: testing the ancestor check by path text, e.g.
    `resolved in [repo_root.resolve(), *repo_root.resolve().parents]`.
    """
    repo = tmp_path / "parent" / "repo"
    (repo / "website" / "build").mkdir(parents=True)
    (tmp_path / "up").symlink_to(tmp_path / "parent", target_is_directory=True)
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: self.absolute())
    with pytest.raises(BuildRootRefused):
        guard_root(tmp_path / "up", repo_root=repo)


def test_roots_under_website_build_and_outside_the_repo_are_allowed(
    tmp_path: Path,
) -> None:
    """A root under ``website/build/`` or outside the repository resolves and passes.

    Dies on: `guard_root` refusing every root; `guard_root` returning its input
    unresolved.
    """
    repo = tmp_path / "repo"
    (repo / "website" / "build").mkdir(parents=True)
    inside = repo / "website" / "build" / "preview" / "check"
    outside = tmp_path / "elsewhere" / "site"
    assert guard_root(inside, repo_root=repo) == inside.resolve()
    assert guard_root(repo / "website" / "build" / "site", repo_root=repo) == (
        repo.resolve() / "website" / "build" / "site"
    )
    assert guard_root(outside, repo_root=repo) == outside.resolve()
    dotted = repo / "website" / "build" / "x" / ".." / "site"
    assert guard_root(dotted, repo_root=repo) == repo.resolve() / "website/build/site"


def test_traversal_and_links_are_resolved_before_the_check(tmp_path: Path) -> None:
    """``..`` and symbolic links cannot carry a root across the boundary (6.7).

    Covers a ``..`` escape from ``website/build/``, a link inside it that points
    at ``website/content``, a link outside the repository that points into it,
    and a repository reached through a link.

    Dies on: `guard_root` comparing the unresolved path's text against
    `website/build`.
    """
    repo = tmp_path / "repo"
    (repo / "website" / "build").mkdir(parents=True)
    (repo / "website" / "content").mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    dotdot = repo / "website" / "build" / ".." / "content"
    with pytest.raises(BuildRootRefused):
        guard_root(dotdot, repo_root=repo)

    inner_link = repo / "website" / "build" / "link"
    inner_link.symlink_to(repo / "website" / "content")
    with pytest.raises(BuildRootRefused):
        guard_root(inner_link, repo_root=repo)

    outer_link = outside / "into-repo"
    outer_link.symlink_to(repo / "website" / "content")
    with pytest.raises(BuildRootRefused):
        guard_root(outer_link, repo_root=repo)

    escape = repo / "website" / "build" / "escape"
    escape.symlink_to(outside)
    assert guard_root(escape / "site", repo_root=repo) == outside.resolve() / "site"

    repo_link = tmp_path / "repo-link"
    repo_link.symlink_to(repo)
    with pytest.raises(BuildRootRefused):
        guard_root(repo_link / "website" / "content", repo_root=repo)
    with pytest.raises(BuildRootRefused):
        guard_root(repo / "website" / "content", repo_root=repo_link)
    assert guard_root(repo_link / "website/build/site", repo_root=repo) == (
        repo.resolve() / "website/build/site"
    )


def test_a_refused_root_is_refused_before_anything_is_touched(
    tmp_path: Path, stub: Recorder
) -> None:
    """A refused root keeps its files: nothing is cleared, written or run.

    Dies on: the managed paths cleared before `guard_root` is called.
    """
    repo = tmp_path / "repo"
    victim = repo / "website" / "content"
    (victim / "html").mkdir(parents=True)
    (victim / "html" / "keep.txt").write_text("keep")
    (victim / "mkdocs.yml").write_text("keep")
    with pytest.raises(BuildRootRefused):
        build(FIXTURE, victim, repo_root=repo)
    assert (victim / "html" / "keep.txt").read_text() == "keep"
    assert (victim / "mkdocs.yml").read_text() == "keep"
    assert stub.roots == []


def test_a_build_into_website_build_of_a_repo_copy_is_allowed(
    tmp_path: Path, stub: Recorder
) -> None:
    """A root under ``<repo>/website/build/`` builds; the copy, not the real repo.

    Dies on: `guard_root` refusing every root inside the repository.
    """
    repo = make_repo(tmp_path)
    root = repo / "website" / "build" / "site"
    outcome = build(FIXTURE, root, repo_root=repo)
    assert outcome.ok is True
    assert (root / "html" / "index.html").is_file()


def _alternate_spellings(repo: Path) -> list[Path]:
    """Other paths to ``repo`` that ``Path.resolve`` does not fold, where they exist."""
    spellings = [Path(str(repo).swapcase()), Path("/System/Volumes/Data" + str(repo))]
    return [p for p in spellings if p != repo and p.exists() and p.samefile(repo)]


def test_an_alternate_spelling_of_the_repo_cannot_reach_a_refused_root(
    tmp_path: Path,
) -> None:
    """Letter-case and firmlink spellings of the repository are still the repository.

    Skipped where the filesystem offers no such spelling (case-sensitive
    Linux). Containment is decided by file identity, so a root spelled through
    the variant into `website/content` is refused, and one into
    `website/build/site` is allowed.

    Dies on: `guard_root` deciding containment by comparing resolved path text.
    """
    repo = tmp_path / "repo"
    (repo / "website" / "build").mkdir(parents=True)
    (repo / "website" / "content").mkdir()
    variants = _alternate_spellings(repo)
    if not variants:
        pytest.skip("no alternate spelling of the same directory on this filesystem")
    for variant in variants:
        with pytest.raises(BuildRootRefused):
            guard_root(variant / "website" / "content", repo_root=repo)
        with pytest.raises(BuildRootRefused):
            guard_root(repo / "website" / "content", repo_root=variant)
        guard_root(variant / "website" / "build" / "site", repo_root=repo)
