"""The ``build_site`` command: subcommands, paths, exit codes (1.1-1.2, 6.5, 7.1, 10.6).

Every call goes through ``main(argv)``. ``generator_executable`` is patched to
succeed unless the test is about a missing generator, and the generator run
inside ``pipeline.build`` is replaced by a stub, so no test here runs Zensical.
Build roots, preview roots and repository skeletons are under ``tmp_path``; the
real fixture tree and the real ``website/`` are only read. ``REPO_ROOT`` in the
module under test is patched to a ``tmp_path`` skeleton wherever the default
content directory or a repository-relative path is the subject, so no test
reads the real ``website/content/``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from scripts import build_site
from scripts.sitebuild import pipeline
from scripts.sitebuild.generator import GeneratorMissing, GeneratorResult
from scripts.sitebuild.model import CONTENT_ENV_VAR, ContentSource, Problem
from scripts.sitebuild.pipeline import (
    DEFAULT_BUILD_ROOT,
    DEFAULT_PREVIEW_ROOT,
    BuildOutcome,
)

FIXTURE = Path(__file__).parent / "fixtures" / "site"
GENERATOR_OUTPUT = "GENERATOR-OUTPUT-LINE-1\nGENERATOR-OUTPUT-LINE-2\n"
PAGE = "---\ntitle: T\ndescription: D\nsection: Why\norder: 1\n{extra}---\n\nBody.\n"


class Spy:
    """Records calls and returns a fixed value."""

    def __init__(self, result: Any) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.result = result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return self.result


@pytest.fixture(autouse=True)
def _generator_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the generator look installed and the environment content-free."""
    monkeypatch.delenv(CONTENT_ENV_VAR, raising=False)
    monkeypatch.setattr(
        build_site, "generator_executable", lambda: Path(sys.executable).parent / "z"
    )


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository skeleton holding only ``website/content/.gitkeep``."""
    root = tmp_path / "repo"
    (root / "website" / "content").mkdir(parents=True)
    (root / "website" / "content" / ".gitkeep").write_text("")
    monkeypatch.setattr(build_site, "REPO_ROOT", root)
    return root


def _outcome(*problems: Problem, output: str = "", pages: int = 3) -> BuildOutcome:
    ok = not problems
    return BuildOutcome(ok, problems, output, {} if ok else None, pages)


def _snapshot(root: Path) -> dict[str, bytes | None]:
    """Every path under ``root`` (directories map to None) with its bytes."""
    found: dict[str, bytes | None] = {}
    for path in sorted(root.rglob("*")):
        found[path.relative_to(root).as_posix()] = (
            None if path.is_dir() else path.read_bytes()
        )
    return found


def _seed_stale_root(root: Path) -> dict[str, bytes | None]:
    """A build root holding a stale earlier build; returns its snapshot."""
    (root / "html").mkdir(parents=True)
    (root / "html" / "index.html").write_text("STALE", encoding="utf-8")
    (root / "mkdocs.yml").write_text("STALE: true\n", encoding="utf-8")
    (root / "staged").mkdir()
    (root / "staged" / "old.md").write_text("STALE", encoding="utf-8")
    before = _snapshot(root)
    assert before["html/index.html"] == b"STALE", "the seed did not take"
    return before


def _content(path: Path, *, drafted: bool = False, valid: bool = True) -> Path:
    """A content directory with one page (drafted, or with broken frontmatter)."""
    path.mkdir(parents=True, exist_ok=True)
    if valid:
        extra = "draft: true\n" if drafted else ""
        (path / "p.md").write_text(PAGE.format(extra=extra), encoding="utf-8")
    else:
        (path / "p.md").write_text("---\ntitle: [unclosed\n---\n", encoding="utf-8")
    return path


def _stub_generator(monkeypatch: pytest.MonkeyPatch, output: str = "") -> None:
    """Replace the generator run inside ``pipeline.build`` with an ok result."""
    monkeypatch.setattr(
        pipeline, "run_build", lambda root: GeneratorResult(True, (), output)
    )


# ------------------------------------------------------------------- build


def test_build_reports_the_page_count_and_the_html_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clean build of the fixture exits 0 with one exact line on stdout.

    The real pipeline runs over the real fixture into ``tmp_path``; only the
    generator is stubbed. The fixture has six included pages.

    Dies on: printing ``len(outcome.problems)`` instead of ``outcome.page_count``,
    or naming the root instead of ``<root>/html``.
    """
    _stub_generator(monkeypatch)
    root = tmp_path / "out"
    code = build_site.main(
        ["build", "--content", str(FIXTURE), "--build-dir", str(root)]
    )
    captured = capsys.readouterr()
    assert (code, captured.err) == (0, "")
    assert captured.out == f"built 6 pages into {root.resolve()}/html\n"
    assert (root / "mkdocs.yml").is_file(), "the pipeline did not run"


def test_build_problems_exit_1_one_line_each_in_outcome_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Problems exit 1, one rendered line each on stderr, in the outcome's order.

    The two problems are out of alphabetical order, so a sort or a reversal
    changes the lines. The generator output is not shown without ``--verbose``.

    Dies on: sorting or reversing the problems before printing them, printing
    the generator output without the flag, or printing a problem to stdout.
    """
    problems = (
        Problem("z.md", "title", "second alphabetically, first reported"),
        Problem("a.md", "", "first alphabetically, second reported"),
    )
    spy = Spy(_outcome(*problems, output=GENERATOR_OUTPUT))
    monkeypatch.setattr(build_site, "build", spy)
    content = _content(tmp_path / "c")
    code = build_site.main(
        ["build", "--content", str(content), "--build-dir", str(tmp_path / "out")]
    )
    captured = capsys.readouterr()
    assert len(spy.calls) == 1, "the build was not reached"
    assert code == 1
    assert captured.out == ""
    assert captured.err == (
        "z.md: title: second alphabetically, first reported\n"
        "a.md: first alphabetically, second reported\n"
    )


def test_build_verbose_appends_the_generator_output_after_the_problems(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--verbose`` puts the whole generator output after the problem lines.

    Dies on: dropping the ``args.verbose`` branch, or printing the output before
    the problem lines.
    """
    problem = Problem("site generator", "", "the one-line summary")
    monkeypatch.setattr(
        build_site, "build", Spy(_outcome(problem, output=GENERATOR_OUTPUT))
    )
    code = build_site.main(
        [
            "build",
            "--verbose",
            "--content",
            str(_content(tmp_path / "c")),
            "--build-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err == "site generator: the one-line summary\n" + GENERATOR_OUTPUT


def test_build_verbose_appends_nothing_when_the_generator_did_not_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A script-level failure has no generator output, so ``--verbose`` adds no line.

    Dies on: printing an empty line for an empty ``generator_output``.
    """
    problem = Problem("a.md", "", "bad")
    monkeypatch.setattr(build_site, "build", Spy(_outcome(problem, output="")))
    code = build_site.main(
        [
            "build",
            "--verbose",
            "--content",
            str(_content(tmp_path / "c")),
            "--build-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == 1
    assert capsys.readouterr().err == "a.md: bad\n"


def test_build_verbose_output_gets_a_final_newline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Generator output without a trailing newline still ends its last line.

    Dies on: writing ``outcome.generator_output`` without appending a newline
    when it lacks one.
    """
    problem = Problem("a.md", "", "bad")
    monkeypatch.setattr(build_site, "build", Spy(_outcome(problem, output="tail")))
    build_site.main(
        [
            "build",
            "--verbose",
            "--content",
            str(_content(tmp_path / "c")),
            "--build-dir",
            str(tmp_path / "out"),
        ]
    )
    assert capsys.readouterr().err == "a.md: bad\ntail\n"


# ------------------------------------------------ could-not-run (exit 2)


@pytest.mark.parametrize(
    ("scenario", "source"),
    [
        ("option", ContentSource.OPTION),
        ("environment", ContentSource.ENVIRONMENT),
        ("default", ContentSource.DEFAULT),
    ],
)
def test_a_missing_content_dir_exits_2_naming_the_dir_and_its_source(
    scenario: str,
    source: ContentSource,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2 names the missing directory and which source chose it (1.2).

    The option case also sets the environment variable, and the option wins even
    though the environment names an existing directory. The default case points
    ``REPO_ROOT`` at a skeleton with no ``website/content``.

    Dies on: letting the environment override the option, dropping the source
    from the message, or ignoring the option or the environment.
    """
    spy = Spy(_outcome())
    monkeypatch.setattr(build_site, "build", spy)
    existing = _content(tmp_path / "exists")
    missing = tmp_path / "missing"
    monkeypatch.setattr(build_site, "REPO_ROOT", tmp_path / "bare")
    argv = ["build", "--build-dir", str(tmp_path / "out")]
    expected = missing
    if scenario == "option":
        monkeypatch.setenv(CONTENT_ENV_VAR, str(existing))
        argv += ["--content", str(missing)]
    elif scenario == "environment":
        monkeypatch.setenv(CONTENT_ENV_VAR, str(missing))
    else:
        expected = tmp_path / "bare" / "website" / "content"
    code = build_site.main(argv)
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert str(expected) in captured.err
    assert f"(resolved from {source.value})" in captured.err
    assert len(captured.err.splitlines()) == 1
    assert spy.calls == []


def test_a_missing_content_dir_for_serve_and_status_exits_2(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``serve`` and ``status`` also exit 2 on a missing directory, running nothing.

    Dies on: removing the ``except ContentDirMissing`` handler.
    """
    spy = Spy(0)
    monkeypatch.setattr(build_site, "serve", spy)
    missing = str(tmp_path / "missing")
    assert build_site.main(["serve", "--content", missing]) == 2
    assert build_site.main(["status", "--content", missing]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("does not exist") == 2
    assert spy.calls == []


def test_a_missing_generator_exits_2_and_leaves_the_build_root_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A run that cannot start the generator touches nothing (design: exit 2).

    The root already holds a stale build. The real ``pipeline.build`` is used
    with only its generator run stubbed, so a build that ran first would clear
    ``html/`` and write ``mkdocs.yml`` over the seed.

    Dies on: calling ``generator_executable()`` after ``build(...)``.
    """

    def missing() -> Path:
        raise GeneratorMissing("the site generator is not installed at /nowhere/z")

    monkeypatch.setattr(build_site, "generator_executable", missing)
    _stub_generator(monkeypatch)
    root = tmp_path / "out"
    before = _seed_stale_root(root)
    code = build_site.main(
        ["build", "--content", str(FIXTURE), "--build-dir", str(root)]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.err == "the site generator is not installed at /nowhere/z\n"
    assert captured.out == ""
    assert _snapshot(root) == before


def test_a_missing_generator_stops_serve_before_it_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``serve`` with no generator exits 2 without starting the loop or writing.

    Dies on: calling ``generator_executable()`` after ``serve(...)``, or not
    calling it for ``serve``.
    """

    def missing() -> Path:
        raise GeneratorMissing("the site generator is not installed")

    monkeypatch.setattr(build_site, "generator_executable", missing)
    spy = Spy(0)
    monkeypatch.setattr(build_site, "serve", spy)
    root = tmp_path / "live"
    before = _seed_stale_root(root)
    code = build_site.main(
        ["serve", "--content", str(FIXTURE), "--build-dir", str(root)]
    )
    assert code == 2
    assert capsys.readouterr().err == "the site generator is not installed\n"
    assert spy.calls == []
    assert _snapshot(root) == before


@pytest.mark.parametrize("command", ["build", "serve"])
def test_a_build_root_inside_the_repo_but_outside_website_build_exits_2(
    command: str,
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A repository path outside ``website/build/`` is refused and nothing is made.

    The skeleton is the patched ``REPO_ROOT``, and ``--build-dir`` is given
    relative, so it is anchored there first.

    Dies on: dropping the ``BuildRootRefused`` handler, or resolving the root
    without ``guard_root``.
    """
    build_spy, serve_spy = Spy(_outcome()), Spy(0)
    monkeypatch.setattr(build_site, "build", build_spy)
    monkeypatch.setattr(build_site, "serve", serve_spy)
    code = build_site.main([command, "--build-dir", "website/elsewhere"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "refusing to build into" in captured.err
    assert build_spy.calls == [] and serve_spy.calls == []
    assert not (repo / "website" / "elsewhere").exists()


# ---------------------------------------------- content / root overlap (2)


def _overlap_case(tmp_path: Path, kind: str) -> tuple[Path, Path]:
    """``(content_dir, build_root)`` for one overlap species, under tmp_path."""
    work = tmp_path / "work"
    if kind == "root-inside-content":
        content = _content(work / "content")
        return content, content / "site" / "out"
    if kind == "root-equals-content":
        content = _content(work / "content")
        return content, content
    if kind == "root-contains-content":
        return _content(work / "root" / "content"), work / "root"
    if kind == "root-inside-content-via-symlink":
        content = _content(work / "content")
        (work / "alias").symlink_to(content, target_is_directory=True)
        return work / "alias", content / "out"
    assert kind == "content-via-symlink-inside-root"
    root = work / "root"
    _content(root / "real")
    (work / "alias").symlink_to(root / "real", target_is_directory=True)
    return work / "alias", root


OVERLAPS = [
    "root-inside-content",
    "root-equals-content",
    "root-contains-content",
    "root-inside-content-via-symlink",
    "content-via-symlink-inside-root",
]


@pytest.mark.parametrize("command", ["build", "serve"])
@pytest.mark.parametrize("kind", OVERLAPS)
def test_a_build_root_overlapping_the_content_dir_exits_2_naming_both(
    kind: str,
    command: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A root inside, equal to, or holding the content dir is refused (7.4, 1.3).

    The paths are outside the repository, where ``guard_root`` allows anything,
    so only the overlap check can refuse them. The symlinked spellings defeat a
    check on the paths as typed. Nothing is built, served or written, and the
    message names both resolved paths.

    Dies on: removing the overlap check, testing only one direction of
    containment, or comparing the paths as typed instead of by file identity.
    """
    build_spy, serve_spy = Spy(_outcome()), Spy(0)
    monkeypatch.setattr(build_site, "build", build_spy)
    monkeypatch.setattr(build_site, "serve", serve_spy)
    content, root = _overlap_case(tmp_path, kind)
    before = _snapshot(tmp_path)
    code = build_site.main(
        [command, "--content", str(content), "--build-dir", str(root)]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert str(content.resolve()) in captured.err
    assert str(root.resolve()) in captured.err
    assert len(captured.err.splitlines()) == 1
    assert build_spy.calls == [] and serve_spy.calls == []
    assert _snapshot(tmp_path) == before


def test_a_build_root_beside_the_content_dir_is_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Siblings, including one whose name extends the content dir's, may build.

    ``c2`` starts with the text of ``c``, so a prefix comparison refuses it.

    Dies on: refusing every root, or comparing path text with ``startswith``.
    """
    spy = Spy(_outcome())
    monkeypatch.setattr(build_site, "build", spy)
    content = _content(tmp_path / "c")
    for name in ("out", "c2"):
        argv = ["build", "--content", str(content), "--build-dir", str(tmp_path / name)]
        assert build_site.main(argv) == 0, capsys.readouterr().err
    assert len(spy.calls) == 2


def test_overlap_is_decided_by_file_identity_not_letter_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A root spelled in another letter case than the content dir is still inside it.

    Runs only on a case-insensitive filesystem; elsewhere the two spellings are
    different directories and the test skips.

    Dies on: comparing resolved paths as text instead of with ``samefile``.
    """
    content = _content(tmp_path / "Content")
    if not (tmp_path / "content").exists():
        pytest.skip("case-sensitive filesystem")
    spy = Spy(_outcome())
    monkeypatch.setattr(build_site, "build", spy)
    code = build_site.main(
        [
            "build",
            "--content",
            str(content),
            "--build-dir",
            str(tmp_path / "content" / "out"),
        ]
    )
    assert code == 2
    assert "content" in capsys.readouterr().err
    assert spy.calls == []


# --------------------------------------------------------------------- serve


@pytest.mark.parametrize("returned", [0, 2])
def test_serve_passes_its_arguments_and_maps_the_return_value_to_the_exit(
    returned: int, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``serve`` exits with what the loop returns: 0 on interrupt, 2 when it died.

    Dies on: returning 0 whatever ``serve`` returned, or passing another content
    directory, root, repository root or address.
    """
    spy = Spy(returned)
    monkeypatch.setattr(build_site, "serve", spy)
    code = build_site.main(["serve", "--addr", "0.0.0.0:9999"])
    assert code == returned
    [(args, kwargs)] = spy.calls
    assert args == (
        (repo / "website" / "content").resolve(),
        (repo / DEFAULT_PREVIEW_ROOT).resolve(),
    )
    assert kwargs == {"repo_root": repo, "addr": "0.0.0.0:9999"}


def test_serve_defaults_to_the_local_address(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``--addr`` the loop gets ``127.0.0.1:8000``.

    Dies on: changing the default address.
    """
    spy = Spy(0)
    monkeypatch.setattr(build_site, "serve", spy)
    assert build_site.main(["serve"]) == 0
    assert spy.calls[0][1]["addr"] == "127.0.0.1:8000"


# ----------------------------------------------------------- paths


def test_relative_paths_resolve_against_the_repo_root_not_the_cwd(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Relative ``--content`` and ``--build-dir`` are read from the repository root.

    The command runs from a directory holding neither path, and the content path
    exists only under the skeleton, so a cwd-relative reading exits 2.

    Dies on: leaving ``--content`` or ``--build-dir`` relative to the cwd.
    """
    _content(repo / "docs-here")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    spy = Spy(_outcome())
    monkeypatch.setattr(build_site, "build", spy)
    code = build_site.main(
        ["build", "--content", "docs-here", "--build-dir", "website/build/mine"]
    )
    assert code == 0, capsys.readouterr().err
    [(args, kwargs)] = spy.calls
    assert args == (
        (repo / "docs-here").resolve(),
        (repo / "website" / "build" / "mine").resolve(),
    )
    assert kwargs == {"repo_root": repo}
    assert list(elsewhere.iterdir()) == []


def test_a_relative_environment_path_resolves_against_the_repo_root(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``FITDOCS_SITE_CONTENT`` given relative is read from the repository root.

    Dies on: passing the environment to ``resolve_content_dir`` unanchored.
    """
    _content(repo / "from-env")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv(CONTENT_ENV_VAR, "from-env")
    assert build_site.main(["status"]) == 0
    assert capsys.readouterr().out == "has_content=true\n"


def test_default_roots_are_under_website_build(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without ``--build-dir``, ``build`` uses the pipeline's default root.

    Dies on: using the preview root for ``build``, or an unanchored default.
    """
    spy = Spy(_outcome())
    monkeypatch.setattr(build_site, "build", spy)
    assert build_site.main(["build"]) == 0
    assert spy.calls[0][0] == (
        (repo / "website" / "content").resolve(),
        (repo / DEFAULT_BUILD_ROOT).resolve(),
    )
    assert DEFAULT_BUILD_ROOT != DEFAULT_PREVIEW_ROOT


def test_an_empty_environment_value_counts_as_unset(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``FITDOCS_SITE_CONTENT=""`` falls to the default directory (1.1, 10.6).

    Read as set, the empty value would anchor to the repository root itself.

    Dies on: testing the environment value with ``is not None`` instead of
    for truth.
    """
    monkeypatch.setenv(CONTENT_ENV_VAR, "")
    spy = Spy(_outcome())
    monkeypatch.setattr(build_site, "build", spy)
    assert build_site.main(["build"]) == 0
    assert spy.calls[0][0][0] == (repo / "website" / "content").resolve()


def test_an_empty_environment_value_gives_the_default_status(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With an empty variable and an empty default dir, ``status`` is ``false``.

    The skeleton's repository root holds a page, so reading the variable as the
    repository root prints ``true``.

    Dies on: testing the environment value with ``is not None``.
    """
    _content(repo / "docs")
    (repo / "top.md").write_text(PAGE.format(extra=""), encoding="utf-8")
    monkeypatch.setenv(CONTENT_ENV_VAR, "")
    assert build_site.main(["status"]) == 0
    assert capsys.readouterr().out == "has_content=false\n"


@pytest.mark.parametrize("command", ["build", "serve", "status"])
def test_an_empty_content_option_is_refused(
    command: str,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--content ""`` exits 2 with one line and runs nothing.

    The skeleton's root holds a page, so reading the empty value as ``.``
    would make ``status`` print ``true``.

    Dies on: converting the option to ``Path`` before the emptiness check.
    """
    (repo / "top.md").write_text(PAGE.format(extra=""), encoding="utf-8")
    build_spy, serve_spy = Spy(_outcome()), Spy(0)
    monkeypatch.setattr(build_site, "build", build_spy)
    monkeypatch.setattr(build_site, "serve", serve_spy)
    assert build_site.main([command, "--content", ""]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "--content must not be empty\n"
    assert build_spy.calls == [] and serve_spy.calls == []


def test_relative_content_from_a_foreign_cwd_for_status_and_serve(
    repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Relative ``--content`` is read from the repository root (status, serve).

    Dies on: leaving ``--content`` relative to the cwd (status exits 2, serve
    is handed the wrong directory).
    """
    _content(repo / "docs-here")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert build_site.main(["status", "--content", "docs-here"]) == 0
    assert capsys.readouterr().out == "has_content=true\n"
    spy = Spy(0)
    monkeypatch.setattr(build_site, "serve", spy)
    assert build_site.main(["serve", "--content", "docs-here"]) == 0
    assert spy.calls[0][0][0] == (repo / "docs-here").resolve()


def test_verbose_prints_nothing_extra_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A successful ``--verbose`` build prints the one line and nothing on stderr.

    Dies on: printing ``generator_output`` whenever ``--verbose`` is given.
    """
    monkeypatch.setattr(build_site, "build", Spy(_outcome(output=GENERATOR_OUTPUT)))
    argv = [
        "build",
        "--verbose",
        "--content",
        str(_content(tmp_path / "c")),
        "--build-dir",
        str(tmp_path / "out"),
    ]
    assert build_site.main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.count("\n") == 1


def test_overlap_is_decided_by_identity_when_resolve_does_not_fold_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """With ``Path.resolve`` made a no-op, a symlinked content path still overlaps.

    A comparison of the unresolved path text misses the link;
    ``os.path.samefile`` does not.

    Dies on: comparing the unresolved path text (e.g. `candidate == outer`)
    instead of file identity.
    """
    content = _content(tmp_path / "content")
    (tmp_path / "alias").symlink_to(content, target_is_directory=True)
    spy = Spy(_outcome())
    monkeypatch.setattr(build_site, "build", spy)
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: self.absolute())
    code = build_site.main(
        [
            "build",
            "--content",
            str(tmp_path / "alias"),
            "--build-dir",
            str(content / "out"),
        ]
    )
    assert code == 2
    assert "overlaps" in capsys.readouterr().err
    assert spy.calls == []


# ---------------------------------------------------------------- status


def test_status_default_dir_with_only_a_gitkeep_has_no_content(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The default directory holding only ``.gitkeep`` prints ``has_content=false``.

    Dies on: printing ``true`` for an empty tree, or a different line format.
    """
    assert build_site.main(["status"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("has_content=false\n", "")


def test_status_reads_the_default_dir_of_the_repo_root_it_is_given(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A page under the skeleton's default directory makes the status ``true``.

    The real ``website/content/`` holds no page, so a status that read it would
    print ``false`` here.

    Dies on: resolving the default directory from anything but ``REPO_ROOT``.
    """
    _content(repo / "website" / "content")
    assert build_site.main(["status"]) == 0
    assert capsys.readouterr().out == "has_content=true\n"


def test_status_of_a_drafts_only_dir_has_no_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory whose only page is a draft has no content (10.6).

    Dies on: counting drafted pages, for instance with ``len(discover(...).pages)``.
    """
    drafts = _content(tmp_path / "drafts", drafted=True)
    assert (drafts / "p.md").read_text(encoding="utf-8").count("draft: true") == 1
    assert build_site.main(["status", "--content", str(drafts)]) == 0
    assert capsys.readouterr().out == "has_content=false\n"


def test_status_of_the_fixture_has_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The fixture, which has both included pages and a draft, is content.

    Dies on: printing ``false`` when included pages exist.
    """
    assert build_site.main(["status", "--content", str(FIXTURE)]) == 0
    assert capsys.readouterr().out == "has_content=true\n"


def test_status_counts_an_unreadable_page_as_content(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A page with broken frontmatter is content that must fail the build (10.6).

    Dies on: treating a page whose frontmatter cannot be read as absent.
    """
    broken = _content(tmp_path / "broken", valid=False)
    assert build_site.main(["status", "--content", str(broken)]) == 0
    assert capsys.readouterr().out == "has_content=true\n"


def test_status_takes_the_environment_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``status`` follows the same option, environment, default order as ``build``.

    Dies on: ignoring the environment in ``status``.
    """
    monkeypatch.setenv(CONTENT_ENV_VAR, str(_content(tmp_path / "e")))
    assert build_site.main(["status"]) == 0
    assert capsys.readouterr().out == "has_content=true\n"


# ---------------------------------------------------------------- parser


def _subcommand_flags(parser: argparse.ArgumentParser) -> Mapping[str, set[str]]:
    [action] = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return {
        name: {
            flag
            for a in sub._actions
            for flag in a.option_strings
            if flag not in ("-h", "--help")
        }
        for name, sub in action.choices.items()
    }


def test_the_parser_accepts_exactly_the_documented_subcommands_and_flags() -> None:
    """Three subcommands, each with its documented flags and no others (design).

    Dies on: adding, dropping or renaming a subcommand or flag.
    """
    assert _subcommand_flags(build_site._build_parser()) == {
        "build": {"--content", "--build-dir", "--verbose"},
        "serve": {"--content", "--build-dir", "--addr"},
        "status": {"--content"},
    }


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["deploy"],
        ["build", "--addr", "x:1"],
        ["serve", "--verbose"],
        ["status", "--build-dir", "x"],
        ["build", "--nope"],
    ],
)
def test_the_parser_rejects_anything_else(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing subcommand, an unknown one, or another subcommand's flag is refused.

    Dies on: making the subcommand optional, or sharing one flag set.
    """
    with pytest.raises(SystemExit) as raised:
        build_site.main(argv)
    assert raised.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_the_parser_reads_the_documented_values() -> None:
    """``--build-dir`` parses into ``Path``, ``--content`` and the address stay text.

    ``--content`` stays text so that an empty value can be told from ``.``.

    Dies on: dropping ``type=Path`` from ``--build-dir``, renaming a destination, or
    changing a default.
    """
    parser = build_site._build_parser()
    built = parser.parse_args(
        ["build", "--content", "c", "--build-dir", "b", "--verbose"]
    )
    assert (built.content, built.build_dir, built.verbose) == (
        "c",
        Path("b"),
        True,
    )
    plain = parser.parse_args(["build"])
    assert (plain.content, plain.build_dir, plain.verbose) == (None, None, False)
    served = parser.parse_args(["serve", "--addr", "h:1"])
    assert (served.content, served.build_dir, served.addr) == (None, None, "h:1")
