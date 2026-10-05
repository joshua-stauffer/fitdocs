"""Repository wiring for the website build: manifest, git, test conventions."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from tests.sitebuild.conftest import SKIP_REASON, copy_fixture_tree

ROOT = Path(__file__).resolve().parents[2]

# Literal values of the runtime manifest before the docs-site spec (8.1).
PRE_SPEC_DEPENDENCIES = [
    "garmin-fit-sdk>=21.208.0",
    "typer>=0.12",
    "rich>=13",
    "pyyaml>=6.0",
    "tomli-w>=1.0",
]

_DIES_ON = re.compile(r"^\s*Dies on:\s*\S", re.MULTILINE)


def _pyproject() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        data: dict[str, Any] = tomllib.load(handle)
    return data


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def _undocumented_tests(source: str) -> list[str]:
    """Names of ``test_*`` functions in ``source`` lacking a ``Dies on:`` line."""
    missing: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and (
            node.name.startswith("test_")
        ):
            doc = ast.get_docstring(node) or ""
            if not _DIES_ON.search(doc):
                missing.append(node.name)
    return missing


def _test_names(source: str) -> list[str]:
    return [
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    ]


def test_runtime_dependencies_are_the_pre_spec_literals() -> None:
    """Analytics-index adds DuckDB as the deliberate runtime dependency delta.

    Dies on: adding any runtime dependency besides DuckDB.
    """
    project = _pyproject()["project"]
    assert project["dependencies"] == PRE_SPEC_DEPENDENCIES + ["duckdb>=1.2,<2"]
    assert project.get("optional-dependencies", {}) == {}


def test_docs_group_is_the_single_exact_pin() -> None:
    """The `docs` group is exactly one `==` pin of the generator (8.2).

    Dies on: loosening the `docs` entry in `pyproject.toml` to `zensical>=0.0.65`.
    """
    groups = _pyproject()["dependency-groups"]
    assert groups["docs"] == ["zensical==0.0.65"]


def _expand_group(
    groups: dict[str, list[Any]], name: str, seen: frozenset[str] = frozenset()
) -> list[str]:
    """Requirement strings of group `name`, following `include-group` entries."""
    if name in seen:
        return []
    found: list[str] = []
    for entry in groups[name]:
        if isinstance(entry, dict):
            found.extend(
                _expand_group(groups, str(entry["include-group"]), seen | {name})
            )
        else:
            found.append(str(entry))
    return found


def _has_zensical(requirements: list[str]) -> bool:
    return any(r.strip().lower().startswith("zensical") for r in requirements)


def test_zensical_is_only_in_the_docs_group() -> None:
    """Only `docs` reaches zensical: directly, by include-group, or by default (8.2).

    Groups are expanded through `{include-group = ...}` entries. The groups in
    `[tool.uv] default-groups` (`["dev"]` when absent) and the legacy
    `[tool.uv] dev-dependencies` list must not reach it either.

    Dies on: adding `zensical` or `{include-group = "docs"}` to the `dev` group,
    setting `[tool.uv] default-groups` to include `docs`, or adding `zensical`
    to `[tool.uv] dev-dependencies`, in `pyproject.toml`.
    """
    data = _pyproject()
    groups = data["dependency-groups"]
    assert "docs" in groups
    for name in groups:
        if name != "docs":
            assert not _has_zensical(_expand_group(groups, name)), name
    uv_table = data.get("tool", {}).get("uv", {})
    legacy = uv_table.get("dev-dependencies", [])
    assert not _has_zensical([str(e) for e in legacy])
    defaults = uv_table.get("default-groups", ["dev"])
    assert isinstance(defaults, list), defaults
    for name in defaults:
        assert not _has_zensical(_expand_group(groups, name)), name


def test_build_output_is_ignored_and_untracked() -> None:
    """`website/build/` is git-ignored and nothing under it is tracked (6.7).

    Dies on: deleting the `/website/build/` line from `.gitignore`.
    """
    ignored = _git("check-ignore", "-v", "website/build/probe")
    assert ignored.returncode == 0, ignored.stderr
    # The general `build/` rule also matches; the explicit line must be the
    # one git reports, so deleting it is visible.
    assert ignored.stdout.split("\t")[0].endswith(":/website/build/"), ignored.stdout
    tracked = _git("ls-files", "website/build")
    assert tracked.returncode == 0, tracked.stderr
    assert tracked.stdout == ""


def _run_inner_pytest(
    tmp_path: Path, *, with_zensical: bool, require: str | None
) -> subprocess.CompletedProcess[str]:
    """Run a one-test suite that requests `requires_zensical`.

    The inner run gets the real conftest and an interpreter path whose
    directory holds a `zensical` file only when `with_zensical` is set.
    """
    inner = tmp_path / "inner"
    bin_dir = tmp_path / "fake-venv" / "bin"
    inner.mkdir()
    bin_dir.mkdir(parents=True)
    fake_python = bin_dir / "python"
    fake_python.symlink_to(Path(getattr(sys, "_base_executable", sys.executable)))
    if with_zensical:
        (bin_dir / "zensical").write_text("")
    (inner / "conftest.py").write_text(
        (ROOT / "tests" / "sitebuild" / "conftest.py").read_text()
    )
    (inner / "test_inner.py").write_text(
        "def test_needs_tooling(requires_zensical):\n    pass\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "FITDOCS_REQUIRE_SITE_TOOLING"}
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    if require is not None:
        env["FITDOCS_REQUIRE_SITE_TOOLING"] = require
    return subprocess.run(
        [str(fake_python), "-m", "pytest", "-p", "no:cacheprovider", "-rs", "-q"],
        cwd=inner,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_requires_zensical_skips_with_the_stated_reason(tmp_path: Path) -> None:
    """Without the tool the fixture skips with the exact reason (9.4).

    Dies on: changing the `pytest.skip(...)` reason (or removing the skip) in
    `tests/sitebuild/conftest.py`.
    """
    assert SKIP_REASON == "site tooling not installed: uv sync --group docs"
    run = _run_inner_pytest(tmp_path, with_zensical=False, require=None)
    assert "1 skipped" in run.stdout, run.stdout + run.stderr
    assert "SKIPPED [1] test_inner.py:" in run.stdout
    assert SKIP_REASON in run.stdout


def test_requires_zensical_only_a_value_of_one_turns_skip_into_failure(
    tmp_path: Path,
) -> None:
    """Any value other than `1` still skips (9.4, 9.5).

    Dies on: making the environment check truthy-by-presence
    (`if os.environ.get(REQUIRE_ENV):`) in `tests/sitebuild/conftest.py`.
    """
    run = _run_inner_pytest(tmp_path, with_zensical=False, require="0")
    assert "1 skipped" in run.stdout, run.stdout + run.stderr
    assert "failed" not in run.stdout
    assert "error" not in run.stdout


def test_requires_zensical_fails_when_the_tool_is_required(tmp_path: Path) -> None:
    """With `FITDOCS_REQUIRE_SITE_TOOLING=1` a missing tool fails (9.5).

    Dies on: dropping the `pytest.fail` branch in `tests/sitebuild/conftest.py`.
    """
    run = _run_inner_pytest(tmp_path, with_zensical=False, require="1")
    assert "1 error" in run.stdout, run.stdout + run.stderr
    assert "skipped" not in run.stdout
    assert SKIP_REASON in run.stdout


def test_requires_zensical_passes_when_the_tool_is_installed(tmp_path: Path) -> None:
    """A `zensical` next to the interpreter lets the test run, even if required.

    Dies on: making the fixture skip or fail unconditionally in
    `tests/sitebuild/conftest.py`.
    """
    run = _run_inner_pytest(tmp_path, with_zensical=True, require="1")
    assert "1 passed" in run.stdout, run.stdout + run.stderr


def test_copy_fixture_tree_copies_into_tmp_path_and_keeps_links(
    tmp_path: Path,
) -> None:
    """The helper copies files and directories and preserves symlinks.

    Dies on: dropping `symlinks=True` from `copy_fixture_tree` in
    `tests/sitebuild/conftest.py`.
    """
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "page.md").write_text("body")
    (source / "link.md").symlink_to("nested/page.md")
    destination = copy_fixture_tree(source, tmp_path / "work")
    assert destination.parent == tmp_path / "work"
    assert (destination / "nested" / "page.md").read_text() == "body"
    assert (destination / "link.md").is_symlink()
    assert os.readlink(destination / "link.md") == "nested/page.md"


def test_meta_checker_flags_a_test_without_a_dies_on_line() -> None:
    """The checker names a test lacking a `Dies on:` line and passes one with it.

    Dies on: making `_undocumented_tests` return an empty list.
    """
    source = (
        "def test_bare():\n    pass\n"
        "def test_other():\n    '''No mutation named.'''\n"
        "def test_ok():\n    '''Doc.\n\n    Dies on: deleting the call.\n    '''\n"
        "def test_empty():\n    '''Doc.\n\n    Dies on:\n    '''\n"
        "def test_inline():\n    '''It never Dies on: anything here.'''\n"
        "class TestGroup:\n    def test_method(self):\n        pass\n"
        "async def test_async():\n    pass\n"
        "def helper():\n    pass\n"
    )
    assert sorted(_undocumented_tests(source)) == sorted(
        [
            "test_bare",
            "test_other",
            "test_empty",
            "test_inline",
            "test_method",
            "test_async",
        ]
    )


def test_every_site_test_names_its_mutation() -> None:
    """Every test function under `tests/sitebuild` has a `Dies on:` line (9.3).

    Dies on: removing the `Dies on:` line from any test docstring in a scanned
    module, or scanning no files.
    """
    paths = sorted((ROOT / "tests" / "sitebuild").glob("*.py"))
    workflow = ROOT / "tests" / "test_docs_workflow.py"
    if workflow.exists():
        paths.append(workflow)
    own = Path(__file__).resolve()
    assert own in [p.resolve() for p in paths], "the scan misses this module"
    own_tests = _test_names(own.read_text())
    assert len(own_tests) >= 10, "the walk is looking at the wrong module"
    scanned = 0
    missing: list[str] = []
    for path in paths:
        source = path.read_text()
        scanned += len(_test_names(source))
        missing.extend(f"{path.name}::{n}" for n in _undocumented_tests(source))
    assert scanned >= len(own_tests)
    assert missing == []


BUILD_LOGIC_FILES = [
    "scripts/build_site.py",
    "scripts/sitebuild/__init__.py",
    "scripts/sitebuild/config.py",
    "scripts/sitebuild/content.py",
    "scripts/sitebuild/generator.py",
    "scripts/sitebuild/links.py",
    "scripts/sitebuild/model.py",
    "scripts/sitebuild/outline.py",
    "scripts/sitebuild/pipeline.py",
    "scripts/sitebuild/preview.py",
    "scripts/sitebuild/stage.py",
]
ALLOWED_TOP_LEVEL = {"yaml", "__future__"}


def _foreign_imports(source: str, module: str) -> list[str]:
    """Imports in ``source`` outside the build-logic allowance (8.4).

    ``module`` is the dotted name of the module being scanned. An import is
    allowed when its top-level package is standard library, ``yaml`` or
    ``__future__``, or when it is ``scripts.sitebuild`` or a submodule. A
    relative import is resolved against ``module`` first. ``import scripts`` and
    a relative import that climbs to ``scripts`` are refused, and
    ``from scripts import x`` is judged as ``scripts.x``.
    """
    package = module.rsplit(".", 1)[0] if "." in module else ""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".") if package else []
                parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join([*parts, *([node.module] if node.module else [])])
                names = [base]
            elif base == "scripts":
                names = [f"scripts.{alias.name}" for alias in node.names]
            else:
                names = [base]
        for name in names:
            top = name.split(".")[0]
            if (
                top in sys.stdlib_module_names
                or top in ALLOWED_TOP_LEVEL
                or name == "scripts.sitebuild"
                or name.startswith("scripts.sitebuild.")
            ):
                continue
            found.append(name)
    return found


def test_build_logic_imports_only_the_standard_library_yaml_and_the_package() -> None:
    """No build-logic module imports anything else (8.4).

    The scanned set is exactly the ten modules of `scripts/sitebuild/` named in
    the design plus `scripts/build_site.py`, so a new module or a moved file
    reds the set check instead of escaping the scan.

    Dies on: adding `import fitdocs` (or any non-allowed import) to a scanned
    module, or a scan that finds a different set of files.
    """
    scanned = sorted(
        p.relative_to(ROOT).as_posix()
        for p in [ROOT / "scripts" / "build_site.py"]
        + list((ROOT / "scripts" / "sitebuild").rglob("*.py"))
    )
    assert scanned == BUILD_LOGIC_FILES, "the walk is looking at the wrong files"
    offenders: dict[str, list[str]] = {}
    for rel in scanned:
        module = rel.removesuffix(".py").replace("/", ".")
        bad = _foreign_imports((ROOT / rel).read_text(encoding="utf-8"), module)
        if bad:
            offenders[rel] = bad
    assert offenders == {}


def test_the_import_guard_refuses_each_kind_of_foreign_import() -> None:
    """The guard flags absolute, from, submodule and relative-escape imports.

    Every allowed spelling in the same source is passed, so a guard that flags
    everything also fails.

    Dies on: skipping `ast.ImportFrom` or `ast.Import`, judging
    `from scripts import x` as `scripts`, ignoring relative imports, or
    allowing an import whose top-level name is not on the allowance.
    """
    ok = (
        "from __future__ import annotations\nimport os, yaml\nimport os.path\n"
        "from collections.abc import Mapping\nimport scripts.sitebuild.model\n"
        "from scripts.sitebuild.model import Problem\nfrom scripts import sitebuild\n"
    )
    assert _foreign_imports(ok, "scripts.build_site") == []
    bad = (
        "import fitdocs\nfrom tests import x\nimport markdown_it.token\n"
        "import zensical\nfrom fitdocs.render import y\nimport scripts.check_site\n"
        "from scripts import check_site\nfrom .. import sibling\n"
        "from . import model\nfrom .model import Problem\nimport scripts\n"
    )
    assert _foreign_imports(bad, "scripts.sitebuild.stage") == [
        "fitdocs",
        "tests",
        "markdown_it.token",
        "zensical",
        "fitdocs.render",
        "scripts.check_site",
        "scripts.check_site",
        "scripts",
        "scripts",
    ]


# Literal `[project.urls]` entries (eleven) before the docs-site spec (11.1).
PRE_SPEC_PROJECT_URLS = {
    "Source": "https://github.com/joshua-stauffer/fitdocs",
    "Documentation": (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/index.md"
    ),
    "Changelog": "https://github.com/joshua-stauffer/fitdocs/blob/main/CHANGELOG.md",
    "Issues": "https://github.com/joshua-stauffer/fitdocs/issues",
    "Ownership Contract": (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/"
        "ownership-contract.md"
    ),
    "Plugin Platform": (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/plugins.md"
    ),
    "Inbox": "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md",
    "Configuration": (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md"
    ),
    "Install": "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/install.md",
    "Compatibility": (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/compatibility.md"
    ),
    "Wiki Integration": (
        "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/wiki-integration.md"
    ),
}


def _project_urls() -> dict[str, str]:
    urls: dict[str, str] = _pyproject()["project"]["urls"]
    return urls


def test_homepage_is_the_first_project_url() -> None:
    """`Homepage` is the site address and the first `[project.urls]` key (11.1).

    Dies on: moving the `Homepage` line below another key, or changing its
    value, in `pyproject.toml`.
    """
    urls = _project_urls()
    assert list(urls)[0] == "Homepage"
    assert urls["Homepage"] == "https://fitdocs.ai"


def test_every_pre_spec_project_url_keeps_its_literal_value() -> None:
    """Each of the eleven pre-spec URL keys is present, unchanged (11.1).

    A subset check: keys added later (such as `Connectors`) are allowed.

    Dies on: deleting or editing the value of any pre-existing key in
    `[project.urls]` in `pyproject.toml`.
    """
    urls = _project_urls()
    assert len(PRE_SPEC_PROJECT_URLS) == 11
    for key, value in PRE_SPEC_PROJECT_URLS.items():
        assert urls.get(key) == value, key


def _contributing_website_section() -> str:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert headings[-1] == "Building the website", headings
    return text.split("## Building the website", 1)[1]


def test_contributing_ends_with_a_building_the_website_section() -> None:
    """The last H2 of CONTRIBUTING.md is one fence-free paragraph (11.8).

    Dies on: renaming or moving the `## Building the website` heading, adding
    a fenced block to it, or splitting it into two paragraphs, in
    `CONTRIBUTING.md`.
    """
    body = _contributing_website_section().strip()
    assert body, "the section is empty"
    assert "```" not in body
    assert "\n\n" not in body, "more than one paragraph"
    for command in (
        "uv sync --group docs",
        "uv run --group docs python -m scripts.build_site build",
        "uv run --group docs python -m scripts.build_site serve",
    ):
        assert f"`{command}`" in body, command


def test_contributing_website_section_links_the_website_doc() -> None:
    """The section links `docs/website.md`, which exists (11.8).

    Dies on: changing the link target to another path in `CONTRIBUTING.md`.
    """
    body = _contributing_website_section()
    targets = re.findall(r"\]\(([^)]+)\)", body)
    assert targets == ["docs/website.md"]
    assert (ROOT / "docs" / "website.md").is_file()


def test_changelog_unreleased_added_declares_the_homepage_url() -> None:
    """`## [Unreleased]` / `### Added` carries a bullet naming the Homepage URL (11.8).

    Dies on: deleting the Homepage bullet from the Unreleased `### Added`
    section of `CHANGELOG.md`, or moving it under a released heading.
    """
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    added = unreleased.split("### Added", 1)[1].split("\n### ", 1)[0]
    bullets = [b for b in re.split(r"\n(?=- )", added) if "Homepage" in b]
    assert len(bullets) == 1, bullets
    assert "https://fitdocs.ai" in bullets[0]
