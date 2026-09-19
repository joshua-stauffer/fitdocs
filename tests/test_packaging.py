"""Tool-install smoke test: install the console script and run it (task 5.3).

This is the automated counterpart to the design's Quality Gates smoke
(``uv tool install --from . fitdocs``; Req 14.1, 14.2, 14.3, 14.4). It installs
fitdocs from THIS checkout into an ISOLATED tool location -- ``UV_TOOL_DIR`` and
``UV_TOOL_BIN_DIR`` point at ``tmp_path`` subdirectories, so the user's real
global tool environment is never touched -- then executes the INSTALLED
``fitdocs`` binary (the packaged console entry point, not ``uv run``) to confirm:

* ``--version`` prints the installed package version (Req 14.2), matching the
  version declared in ``pyproject.toml`` (Req 14.3's 3.11+ floor is declared
  statically there and asserted by mypy/packaging, not exercised at runtime);
* ``--help`` exits 0 and documents both the ``sync`` and ``regen`` commands
  (Req 14.1, 14.2);

and finally ``uv tool uninstall``s it so nothing lingers.

The install runs OFFLINE (``--offline``): its dependencies are expected in the
uv cache from ``uv sync``, so no network is needed (Req 14.4). If a cold cache
can't satisfy an offline resolve, the cache is warmed with a single online
resolve into the same isolated dirs and the OFFLINE install is then proven from
the warm cache -- the asserted install is always the offline one.

Runtime: dominated by two-or-fewer ``uv tool install`` invocations (each builds
the wheel with hatchling and links cached deps); a few seconds on a warm cache,
longer on a cold one that must warm online once.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from collections.abc import Iterator
from email.parser import Parser
from pathlib import Path
from typing import cast

import pytest
import tomli_w
import typer.core
import typer.main
import yaml
from scripts.artifact_policy import DEFAULT_POLICY_PATH, load_policy

from fitdocs.agentskill import INBOX_SKILL_NAME, PACKAGED_SKILLS
from fitdocs.cli import app as cli_app
from fitdocs.version import UNKNOWN_VERSION
from tests.test_forbidden_strings import _build_artifact

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TIMEOUT_S = 300


def _project_version() -> str:
    """The version declared in ``pyproject.toml`` -- what ``--version`` must print."""
    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    assert isinstance(version, str) and version
    return version


def _run(
    cmd: list[str], env: dict[str, str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess capturing text output, without raising on failure."""
    return subprocess.run(
        cmd,
        env=env,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )


def _install_offline(uv: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Install fitdocs offline into the isolated tool dirs.

    A cold uv cache can fail an offline *resolution* even when the wheels exist;
    if so, warm the cache with a single online resolve into the same isolated
    dirs, uninstall, and retry offline -- the returned result is always the
    OFFLINE install, so the assertion still proves offline installability.
    """
    from_spec = str(_PROJECT_ROOT)
    offline = _run(
        [uv, "tool", "install", "--offline", "--from", from_spec, "fitdocs"], env
    )
    if offline.returncode == 0:
        return offline
    warm = _run([uv, "tool", "install", "--from", from_spec, "fitdocs"], env)
    assert warm.returncode == 0, (
        "could not install fitdocs offline (cold cache) and warming the uv cache "
        f"online also failed:\n{warm.stdout}\n{warm.stderr}"
    )
    _run([uv, "tool", "uninstall", "fitdocs"], env)
    return _run(
        [uv, "tool", "install", "--offline", "--from", from_spec, "fitdocs"], env
    )


def test_tool_install_exposes_working_console_script(tmp_path: Path) -> None:
    """Installing fitdocs from a clean checkout exposes a working ``fitdocs``
    console script: ``--version`` prints the packaged version and ``--help``
    documents ``sync``/``regen`` (Req 14.1, 14.2, 14.3, 14.4).

    The install is ISOLATED (``UV_TOOL_DIR``/``UV_TOOL_BIN_DIR`` under
    ``tmp_path``) and OFFLINE, and the installed binary -- not ``uv run`` -- is
    what's exercised, so this proves the packaged entry point itself works."""
    uv = shutil.which("uv")
    # Loud, clear failure if the required installer is missing (here uv IS present).
    assert uv is not None, (
        "uv is required for the packaging smoke test but was not found on PATH; "
        "install uv (https://docs.astral.sh/uv/) to run the install smoke"
    )

    tool_dir = tmp_path / "uv-tool-dir"
    bin_dir = tmp_path / "uv-tool-bin"
    tool_dir.mkdir()
    bin_dir.mkdir()
    # A COPY of the environment with the tool location redirected into tmp_path:
    # the user's real global tool dir and bin dir are never mutated.
    env = os.environ.copy()
    env["UV_TOOL_DIR"] = str(tool_dir)
    env["UV_TOOL_BIN_DIR"] = str(bin_dir)

    try:
        install = _install_offline(uv, env)
        assert install.returncode == 0, (
            f"offline `uv tool install` failed:\n{install.stdout}\n{install.stderr}"
        )

        exe = bin_dir / "fitdocs"
        if not exe.exists():  # console scripts are `.exe` on Windows
            exe = bin_dir / "fitdocs.exe"
        assert exe.exists(), f"installed fitdocs console script not found in {bin_dir}"

        version = _run([str(exe), "--version"], env)
        assert version.returncode == 0, f"--version failed:\n{version.stderr}"
        assert version.stdout.strip() == _project_version(), (
            f"--version printed {version.stdout.strip()!r}, "
            f"expected {_project_version()!r}"
        )

        help_out = _run([str(exe), "--help"], env)
        assert help_out.returncode == 0, f"--help failed:\n{help_out.stderr}"
        assert "sync" in help_out.stdout, "--help must document the sync command"
        assert "regen" in help_out.stdout, "--help must document the regen command"
    finally:
        # Clean up the isolated install regardless of assertion outcome; ignore the
        # result since a failed/partial install leaves nothing to uninstall.
        _run([uv, "tool", "uninstall", "fitdocs"], env)


def test_tool_install_ships_py_typed_marker(tmp_path: Path) -> None:
    """Installing fitdocs ships the PEP 561 ``py.typed`` marker inside the
    installed package (Req 5.1), so a third-party plugin's strict type checker
    resolves fitdocs types without stubs or suppressions.

    This looks for the marker inside the ISOLATED tool install's
    ``site-packages/fitdocs/`` directory -- not merely in the source tree --
    so a packaging regression that drops the marker from the built wheel (even
    though it still exists in the repo) is caught here. The glob avoids
    hardcoding a Python-version-specific ``site-packages`` path segment."""
    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required for the packaging smoke test but was not found on PATH; "
        "install uv (https://docs.astral.sh/uv/) to run the install smoke"
    )

    tool_dir = tmp_path / "uv-tool-dir"
    bin_dir = tmp_path / "uv-tool-bin"
    tool_dir.mkdir()
    bin_dir.mkdir()
    env = os.environ.copy()
    env["UV_TOOL_DIR"] = str(tool_dir)
    env["UV_TOOL_BIN_DIR"] = str(bin_dir)

    try:
        install = _install_offline(uv, env)
        assert install.returncode == 0, (
            f"offline `uv tool install` failed:\n{install.stdout}\n{install.stderr}"
        )

        matches = list(tool_dir.glob("**/site-packages/fitdocs/py.typed"))
        assert matches, (
            "py.typed marker not found under any 'site-packages/fitdocs/' directory "
            f"in the isolated tool install at {tool_dir}; searched "
            "'**/site-packages/fitdocs/py.typed'"
        )
    finally:
        _run([uv, "tool", "uninstall", "fitdocs"], env)


# ---------------------------------------------------------------------------
# Task 1.2: package manifest completeness -- authors/keywords/classifiers,
# the license file, the sdist allowlist, and the project-URL coverage of
# every documentation page a shipped or emitted artifact references
# (design.md "PackageManifest", "Modified Files -> pyproject.toml", "Data
# Models -> Artifact contents" and "Doc references leave the repository...").
# ---------------------------------------------------------------------------

#: The project's published repository base URL -- the form
#: ``src/fitdocs/declaration.py:92`` and ``README.md`` already use for the
#: ownership contract (Req 1.9).
_REPO_URL = "https://github.com/joshua-stauffer/fitdocs"

#: Doc pages a *shipped or emitted* artifact references, by design's naming
#: (1.9): the ownership contract, the plugin platform, the inbox, and
#: configuration. Each must resolve to a declared ``[project.urls]`` entry.
_NAMED_DOC_PAGES = frozenset(
    {
        f"{_REPO_URL}/blob/main/docs/ownership-contract.md",
        f"{_REPO_URL}/blob/main/docs/plugins.md",
        f"{_REPO_URL}/blob/main/docs/inbox.md",
        f"{_REPO_URL}/blob/main/docs/configuration.md",
    }
)

#: Files a *shipped or emitted* artifact can carry documentation links
#: through: the README (rendered into the wheel's long description), every
#: module under ``src/fitdocs`` (e.g. the ownership declaration emitted into
#: a user's tree), every packaged skill's ``SKILL.md`` (a wheel member), and
#: the changelog (an sdist member, task 1.3).
_DOC_URL_SOURCE_FILES: tuple[Path, ...] = (
    _PROJECT_ROOT / "README.md",
    _PROJECT_ROOT / "CHANGELOG.md",
    *sorted((_PROJECT_ROOT / "src" / "fitdocs").rglob("*.py")),
    *sorted((_PROJECT_ROOT / "src" / "fitdocs" / "skills").rglob("SKILL.md")),
)

#: A project-documentation-page URL in the form the design mandates:
#: ``https://github.com/joshua-stauffer/fitdocs/blob/main/<docs/*.md or
#: CHANGELOG.md>`` -- never a repo-relative path.
_DOC_URL_PATTERN = re.compile(
    re.escape(_REPO_URL) + r"/blob/main/(?:docs/[\w.\-/]+\.md|CHANGELOG\.md)"
)


def _collect_referenced_doc_urls() -> frozenset[str]:
    """Every project-documentation-page URL found in a shipped/emitted
    source file (README, package modules, packaged skill files)."""
    found: set[str] = set()
    for path in _DOC_URL_SOURCE_FILES:
        text = path.read_text(encoding="utf-8")
        found.update(_DOC_URL_PATTERN.findall(text))
    return frozenset(found)


def _project_urls() -> dict[str, str]:
    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = data["project"].get("urls", {})
    assert isinstance(urls, dict)
    return urls


def test_every_referenced_documentation_page_has_a_declared_project_url() -> None:
    """Requirement 1.9: every documentation page a shipped or emitted
    artifact references (README, ``CHANGELOG.md``, ``src/fitdocs/**/*.py``,
    every packaged skill's ``SKILL.md``) is a value in ``[project.urls]``.

    Positive control: the collected reference set itself must be non-empty
    -- otherwise the membership assertion below would pass having found
    nothing to check (a vacuous walk). The four named pages (ownership
    contract, plugin platform, inbox, configuration) are asserted
    individually too, since design.md names them explicitly.
    """
    referenced = _collect_referenced_doc_urls()
    assert referenced, (
        "no project-documentation-page URL was found in any shipped/emitted "
        "source file -- this walk is looking at the wrong files/pattern, not "
        "proving the reference set is covered"
    )

    declared = frozenset(_project_urls().values())
    missing = sorted(referenced - declared)
    assert not missing, (
        f"documentation page(s) referenced by a shipped/emitted artifact have "
        f"no declared [project.urls] entry: {missing}"
    )

    missing_named = sorted(_NAMED_DOC_PAGES - declared)
    assert not missing_named, (
        f"the named documentation pages (ownership contract, plugin platform, "
        f"inbox, configuration) must each have a declared [project.urls] "
        f"entry; missing: {missing_named}"
    )


def test_project_urls_declares_source_documentation_changelog_and_issues() -> None:
    """Requirement 1.3: the manifest declares links to source and
    documentation at minimum; design.md additionally names Changelog and
    Issues explicitly."""
    urls = _project_urls()
    assert urls.get("Source") == _REPO_URL
    assert urls.get("Documentation") == f"{_REPO_URL}/blob/main/docs/index.md"
    assert urls.get("Changelog") == f"{_REPO_URL}/blob/main/CHANGELOG.md"
    assert urls.get("Issues") == f"{_REPO_URL}/issues"


def _tracked_files(repo_root: Path) -> tuple[str, ...]:
    """Every git-tracked file path (relative, forward-slash) under
    ``repo_root``, via ``git ls-files -z`` (NUL-separated so no filename can
    be mis-split)."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(repo_root),
        capture_output=True,
        check=True,
    )
    names = tuple(n for n in result.stdout.decode("utf-8").split("\0") if n)
    return names


def _copy_tracked_tree(source_root: Path, dest_root: Path) -> tuple[str, ...]:
    """Copy every git-tracked file from ``source_root`` into ``dest_root``,
    preserving relative paths. Returns the tracked-file list, so callers can
    assert it is non-empty before trusting anything built from the copy."""
    names = _tracked_files(source_root)
    for rel in names:
        src = source_root / rel
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
    return names


def _strip_prefix(names: tuple[str, ...]) -> frozenset[str]:
    """Strip the sdist's ``fitdocs-<version>/`` top-level prefix from every
    member name."""
    stripped: set[str] = set()
    for name in names:
        parts = name.split("/", 1)
        stripped.add(parts[1] if len(parts) == 2 else "")
    return frozenset(stripped)


def test_sdist_allowlist_excludes_forbidden_paths_and_the_agent_log_symlink(
    tmp_path: Path,
) -> None:
    """Requirement 1.6, 1.10, 10.3: a built sdist over a tree carrying a
    root ``agent-log`` symlink contains none of it, none of ``tests/``,
    ``.kiro/``, ``docs/``, ``scripts/``, no ``uv.lock``, no ``*.xlsx``/
    ``*.fit``/``*.gpx``, and no symbolic-link member of any name -- while
    still carrying the required sdist members.

    Built over a TEMPORARY COPY of the tracked tree (never the primary
    checkout): the design record is explicit that the dangling ``agent-log``
    symlink "exists only in the primary checkout, never in a worktree or a
    CI checkout" (task 1.2's Observable), so an assertion that depended on
    this checkout's own state would be vacuous. The copy plants the link
    itself and proves the plant succeeded before building (reachability),
    then proves the SAME tree WITHOUT the ``[tool.hatch.build.targets.sdist]``
    table WOULD ship it (the positive control that makes the exclusion
    assertion meaningful rather than a coincidence of an already-clean sdist
    -- "falsity in the starting state"). The table is removed at the TOML
    data level (parse, delete the one key, re-serialize with ``tomli_w``) --
    never by a text/regex edit -- so the control cannot accidentally consume
    or corrupt any other table in the manifest, wherever those tables happen
    to sit in the file.
    """
    source_copy = tmp_path / "with-allowlist"
    source_copy.mkdir()
    tracked = _copy_tracked_tree(_PROJECT_ROOT, source_copy)
    assert tracked, "git ls-files returned nothing -- the tree copy is empty"

    planted_link = source_copy / "agent-log"
    planted_link.symlink_to("/nonexistent/agent-log")
    assert planted_link.is_symlink(), (
        "the planted agent-log symlink does not exist in the copy before "
        "building -- the scenario this test names was never reached"
    )

    out_dir_with = tmp_path / "dist-with-allowlist"
    _build_artifact(source_copy, out_dir_with, "--sdist")
    sdists_with = sorted(out_dir_with.glob("*.tar.gz"))
    assert len(sdists_with) == 1, f"expected exactly one built sdist, got {sdists_with}"

    with tarfile.open(sdists_with[0]) as archive:
        members_with = archive.getmembers()
        names_with = _strip_prefix(tuple(m.name for m in members_with))

    forbidden_prefixes = ("tests/", ".kiro/", "docs/", "scripts/", "release/")
    forbidden_hits = [
        n
        for n in names_with
        if n.startswith(forbidden_prefixes)
        or n == "uv.lock"
        or n.endswith((".xlsx", ".fit", ".gpx"))
    ]
    assert not forbidden_hits, (
        f"the allowlisted sdist still ships forbidden path(s): {forbidden_hits}"
    )
    assert "agent-log" not in names_with, (
        "the allowlisted sdist still ships the root agent-log member"
    )
    link_members_with = [m.name for m in members_with if m.issym() or m.islnk()]
    assert not link_members_with, (
        f"the allowlisted sdist still ships (a) symbolic-link member(s): "
        f"{link_members_with}"
    )

    required = {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "src/fitdocs/__init__.py",
        "src/fitdocs/py.typed",
        "src/fitdocs/skills/build-training-block/SKILL.md",
        "PKG-INFO",
    }
    missing_required = sorted(required - names_with)
    assert not missing_required, (
        f"the allowlisted sdist is missing required member(s): {missing_required}"
    )

    # Positive control: the SAME copy, but with the sdist allowlist table
    # removed, WOULD ship the planted link -- proving the exclusion above is
    # a property of the allowlist, not an accident of what hatchling's
    # default happens to skip. The removal is done at the TOML DATA level
    # (parse -> delete the one key -> re-serialize), never by a text/regex
    # edit: a text-based removal risks over-consuming everything after the
    # sdist table if its "up to the next top-level header" pattern is even
    # slightly wrong (e.g. `[^\[].*\n` also matches blank lines, which are
    # indistinguishable from "more table body" to a regex, so it silently
    # swallows every later table too -- `[build-system]`, `[tool.ruff]`,
    # `[tool.mypy]`, and so on). Removing the parsed key cannot have that
    # failure mode: only the named key is gone, and the guard below proves it.
    without_dir = tmp_path / "without-allowlist"
    _copy_tracked_tree(_PROJECT_ROOT, without_dir)
    (without_dir / "agent-log").symlink_to("/nonexistent/agent-log")

    manifest_path = without_dir / "pyproject.toml"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    original = tomllib.loads(manifest_text)
    assert "sdist" in original.get("tool", {}).get("hatch", {}).get("build", {}).get(
        "targets", {}
    ), (
        "could not find [tool.hatch.build.targets.sdist] in the parsed "
        "manifest -- the positive control has nothing to remove"
    )

    control = copy.deepcopy(original)
    del control["tool"]["hatch"]["build"]["targets"]["sdist"]
    manifest_path.write_text(tomli_w.dumps(control), encoding="utf-8")

    # Guard: re-parse what was actually written and prove EXACTLY one key
    # changed -- the sdist table is gone, and everything else (including
    # [build-system] and the wheel target, both load-bearing for the build
    # below to even run under the project's own backend) survived intact.
    reparsed = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    assert "sdist" not in reparsed["tool"]["hatch"]["build"]["targets"], (
        "the sdist table is still present after the control's deletion -- "
        "the edit did not take effect"
    )
    reparsed_without_sdist = copy.deepcopy(reparsed)
    reparsed_without_sdist["tool"]["hatch"]["build"]["targets"]["sdist"] = original[
        "tool"
    ]["hatch"]["build"]["targets"]["sdist"]
    assert reparsed_without_sdist == original, (
        "the control's manifest differs from the original by more than just "
        "the deleted sdist table -- the removal must be scoped to exactly "
        "that one key"
    )
    assert reparsed["build-system"] == original["build-system"], (
        "the control's manifest lost [build-system] -- the build below would "
        "silently fall back to a different backend instead of proving "
        "hatchling's own default sdist behavior"
    )
    assert (
        reparsed["tool"]["hatch"]["build"]["targets"]["wheel"]
        == original["tool"]["hatch"]["build"]["targets"]["wheel"]
    ), "the control's manifest lost the wheel target"

    out_dir_without = tmp_path / "dist-without-allowlist"
    _build_artifact(without_dir, out_dir_without, "--sdist")
    sdists_without = sorted(out_dir_without.glob("*.tar.gz"))
    assert len(sdists_without) == 1, (
        f"expected exactly one built sdist, got {sdists_without}"
    )

    with tarfile.open(sdists_without[0]) as archive:
        link_members_without = [
            m.name for m in archive.getmembers() if m.issym() or m.islnk()
        ]
    stripped_without = _strip_prefix(tuple(link_members_without))
    assert "agent-log" in stripped_without, (
        "positive control failed: without the sdist allowlist table, the "
        "built sdist should ship the planted agent-log symlink member, but "
        f"it did not (link members seen: {link_members_without}) -- either "
        "hatchling's default already excludes it (making the exclusion "
        "assertion above unfalsifiable) or the control's manifest edit was "
        "not actually applied"
    )


def test_dependencies_declaration_is_unchanged() -> None:
    """Requirement 10.1: becoming publishable costs no new runtime
    dependency. PRESERVED-ONLY here: pinned by
    ``tests/test_determinism.py::test_no_new_third_party_runtime_dependency_was_added``,
    which already asserts ``[project].dependencies`` equals the frozen
    pre-plugin-api baseline. Not duplicated; this test only asserts the
    manifest's dependency list is present and matches that exact literal
    list, byte for byte, so a reviewer can see the two tests agree."""
    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    assert dependencies == [
        "garmin-fit-sdk>=21.208.0",
        "typer>=0.12",
        "rich>=13",
        "pyyaml>=6.0",
        "tomli-w>=1.0",
    ]


def test_license_file_and_manifest_declaration_agree(tmp_path: Path) -> None:
    """Requirement 1.8: the published distribution carries a license file
    whose terms match the declared license. Checks the LICENSE file's text,
    the manifest's SPDX expression, and (built) the wheel's distribution
    metadata for ``License-Expression`` and ``License-File``.
    """
    license_path = _PROJECT_ROOT / "LICENSE"
    assert license_path.is_file(), "LICENSE file does not exist"
    license_text = license_path.read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Permission is hereby granted" in license_text

    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["license"] == "MIT"
    assert data["project"]["license-files"] == ["LICENSE"]

    out_dir = tmp_path / "dist"
    _build_artifact(_PROJECT_ROOT, out_dir, "--wheel")
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, got {wheels}"

    with zipfile.ZipFile(wheels[0]) as wheel:
        metadata_members = [
            n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")
        ]
        assert len(metadata_members) == 1, (
            f"expected exactly one METADATA member, got {metadata_members}"
        )
        metadata_text = wheel.read(metadata_members[0]).decode("utf-8")

    headers = Parser().parsestr(metadata_text)
    assert headers.get("License-Expression") == "MIT", (
        f"expected 'License-Expression: MIT' in built wheel metadata, got "
        f"{headers.get('License-Expression')!r} (full headers: "
        f"{dict(headers.items())})"
    )
    assert headers.get("License-File") == "LICENSE"

    project_url_lines = headers.get_all("Project-URL") or []
    assert project_url_lines, (
        "built wheel metadata declares no Project-URL header at all"
    )


def test_wheel_and_sdist_authors_keywords_classifiers_are_declared() -> None:
    """Requirement 1.3: the manifest declares authors (with the noreply
    address, never a personal one), keywords, and classifiers including the
    MIT license and supported Python versions."""
    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]

    authors = project.get("authors")
    assert authors == [
        {
            "name": "Josh Stauffer",
            "email": "66793731+joshua-stauffer@users.noreply.github.com",
        }
    ]

    keywords = project.get("keywords")
    assert isinstance(keywords, list) and keywords

    classifiers = project.get("classifiers")
    assert isinstance(classifiers, list) and classifiers
    assert "License :: OSI Approved :: MIT License" in classifiers
    assert any(c.startswith("Development Status ::") for c in classifiers)
    assert any(c.startswith("Intended Audience ::") for c in classifiers)
    assert any(c.startswith("Environment ::") for c in classifiers)
    assert any(c.startswith("Typing :: Typed") for c in classifiers)
    for floor_version in ("3.11", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {floor_version}" in classifiers
    assert "Programming Language :: Python :: 3" in classifiers


# ---------------------------------------------------------------------------
# Task 7.1: installed-tool behavior and version identity end to end
# (design.md "E2E Tests -> Installed tool from the built artifact",
# "Source-tree version", "Skill command"; Req 1.2, 1.7, 2.2, 2.4).
#
# Unlike the 5.3 smoke test above (``--from .``, "sync"/"regen" only), this
# section installs the wheel the release actually SHIPS, checks every
# released command's help, checks the installed distribution's own METADATA
# file for completeness, proves the install and a run of the no-data-root
# commands create no user-facing state, exercises the REAL uninstalled-
# checkout case (not a patched-metadata simulation), and drives the
# installed tool's ``skill`` command end to end.
# ---------------------------------------------------------------------------

_REAL_POLICY_PATH = _PROJECT_ROOT / DEFAULT_POLICY_PATH

#: Every command the typer app actually registers -- read from the app
#: itself (the technique ``tests/test_agent_skill.py`` uses), not
#: hand-copied, so a command added or removed in ``src/fitdocs/cli.py``
#: changes this set without anyone editing this file.
_EXPECTED_COMMANDS: tuple[str, ...] = tuple(
    cast(typer.core.TyperGroup, typer.main.get_command(cli_app)).commands
)


@pytest.fixture(scope="module")
def _real_uv_cache_dir() -> str:
    """The developer machine's actual, already-warm ``uv`` package cache --
    reused (never copied or wiped) so every ``--offline`` install/venv
    below can run without a fresh download, passed through explicitly via
    ``UV_CACHE_DIR`` independent of the isolated/fake ``HOME`` used
    elsewhere in this section."""
    result = subprocess.run(
        ["uv", "cache", "dir"], capture_output=True, text=True, check=True
    )
    cache_dir = result.stdout.strip()
    assert cache_dir, "`uv cache dir` printed nothing"
    return cache_dir


@pytest.fixture(scope="module")
def _built_wheel_7_1(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The project's wheel, built once (module scope) for every test below
    -- design.md's "install the built artifact", as opposed to the 5.3
    smoke test's ``--from .``."""
    out_dir = tmp_path_factory.mktemp("dist_7_1")
    _build_artifact(_PROJECT_ROOT, out_dir, "--wheel")
    wheels = sorted(out_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected exactly one built wheel, got {wheels}"
    return wheels[0]


def _hermetic_tool_env(
    tmp_path: Path, cache_dir: str
) -> tuple[dict[str, str], Path, Path, Path]:
    """A fresh, isolated environment for one ``uv tool install``: a fake
    ``HOME`` (with ``XDG_*`` dirs under it) so a stray write lands in
    ``tmp_path`` rather than the real machine, dead proxies on both schemes
    so a surprise network call fails loudly instead of silently succeeding,
    and the real warm ``uv`` cache passed through explicitly so the install
    can run ``--offline``. Returns ``(env, fake_home, tool_dir, bin_dir)``;
    ``tool_dir``/``bin_dir`` are siblings of ``fake_home``, never nested
    under it, so a before/after snapshot of ``fake_home`` alone already
    proves the install touched nothing but its own uv-owned dirs."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    tool_dir = tmp_path / "uv-tool-dir"
    bin_dir = tmp_path / "uv-tool-bin"
    tool_dir.mkdir()
    bin_dir.mkdir()
    env = os.environ.copy()
    # Never inherit the developer/CI process's own data-root pointer or
    # forbidden-strings match-file location: a leaked FITDOCS_DATA would
    # make an installed-tool invocation silently resolve the operator's
    # REAL vault (or a malformed one, turning "no user-facing state" into a
    # false pass/fail unrelated to this test) instead of the "no data root
    # configured" state the no-data-root commands are exercised under.
    env.pop("FITDOCS_DATA", None)
    env.pop("FITDOCS_FORBIDDEN_STRINGS", None)
    env["HOME"] = str(fake_home)
    env["XDG_DATA_HOME"] = str(fake_home / "xdg_data_home")
    env["XDG_CONFIG_HOME"] = str(fake_home / "xdg_config_home")
    env["XDG_CACHE_HOME"] = str(fake_home / "xdg_cache_home")
    env["XDG_BIN_HOME"] = str(fake_home / "xdg_bin_home")
    env["UV_TOOL_DIR"] = str(tool_dir)
    env["UV_TOOL_BIN_DIR"] = str(bin_dir)
    env["UV_CACHE_DIR"] = cache_dir
    env["HTTP_PROXY"] = "http://127.0.0.1:9"
    env["HTTPS_PROXY"] = "http://127.0.0.1:9"
    return env, fake_home, tool_dir, bin_dir


def _without_dead_proxies(env: dict[str, str]) -> dict[str, str]:
    """*env* minus the dead-proxy variables :func:`_hermetic_tool_env` sets.

    The dead proxies exist to make a *surprise* network call fail loudly
    during an offline-only test run; the deliberate ONE-TIME online warm
    fallback below needs a real network path (a CI runner's cache, unlike a
    developer machine's, starts populated only by ``uv sync`` and can miss
    the exact wheel/sdist resolution an isolated ``uv tool install``/``uv
    pip install`` needs), so it must not inherit them -- otherwise a
    legitimate cache-miss is masked by "Connection refused" from the dead
    proxy instead of the real resolver error.
    """
    return {k: v for k, v in env.items() if k not in ("HTTP_PROXY", "HTTPS_PROXY")}


def _install_wheel_offline(
    uv: str, wheel: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """``uv tool install --offline --from <wheel> fitdocs``, warming the
    passed-through cache with one online resolve and retrying offline if a
    cold cache rejects the offline resolution (mirrors ``_install_offline``
    above, but installs from an already-BUILT wheel path, never ``--from
    .``) -- the returned result is always the offline install.

    The online warm step runs under an env copy with the dead proxies
    removed (:func:`_without_dead_proxies`); the retried offline install
    that produces the returned/asserted result still runs under the
    original, proxied *env*.
    """
    offline = _run(
        [uv, "tool", "install", "--offline", "--from", str(wheel), "fitdocs"], env
    )
    if offline.returncode == 0:
        return offline
    warm_env = _without_dead_proxies(env)
    warm = _run([uv, "tool", "install", "--from", str(wheel), "fitdocs"], warm_env)
    assert warm.returncode == 0, (
        f"could not install the built wheel offline (cold cache) and "
        f"warming the uv cache online also failed:\n{warm.stdout}\n{warm.stderr}"
    )
    _run([uv, "tool", "uninstall", "fitdocs"], warm_env)
    return _run(
        [uv, "tool", "install", "--offline", "--from", str(wheel), "fitdocs"], env
    )


@pytest.fixture(scope="module")
def _installed_tool_from_wheel(
    tmp_path_factory: pytest.TempPathFactory,
    _built_wheel_7_1: Path,
    _real_uv_cache_dir: str,
) -> Iterator[tuple[Path, dict[str, str], Path, Path]]:
    """Installs :func:`_built_wheel_7_1` into one isolated, hermetic tool
    environment, shared (module scope) by every test that only reads from
    the installed tool without needing its own before/after filesystem
    snapshot. Yields ``(console-script path, env, tool_dir, cwd_dir)`` --
    every invocation of the installed binary below runs with ``cwd_dir`` as
    its working directory, never the repository root, so a regression that
    writes into the *current directory* (e.g. an emitted ``fitdocs.toml``)
    lands in a throwaway tmp dir and never touches this checkout. Uninstalls
    at teardown regardless of test outcome."""
    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required for the 7.1 E2E tests but was not found on PATH"
    )
    tmp_path = tmp_path_factory.mktemp("installed_tool_7_1")
    env, _fake_home, tool_dir, bin_dir = _hermetic_tool_env(
        tmp_path, _real_uv_cache_dir
    )
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    install = _install_wheel_offline(uv, _built_wheel_7_1, env)
    assert install.returncode == 0, (
        f"install of the built wheel failed:\n{install.stdout}\n{install.stderr}"
    )
    exe = bin_dir / "fitdocs"
    if not exe.exists():  # console scripts are `.exe` on Windows
        exe = bin_dir / "fitdocs.exe"
    assert exe.exists(), f"installed fitdocs console script not found in {bin_dir}"
    try:
        yield exe, env, tool_dir, cwd_dir
    finally:
        _run([uv, "tool", "uninstall", "fitdocs"], env)


def test_installed_tool_version_matches_manifest_and_help_lists_every_command(
    _installed_tool_from_wheel: tuple[Path, dict[str, str], Path, Path],
) -> None:
    """Req 1.2, 2.2: the installed console script's ``--version`` equals the
    manifest's declared version, and ``--help`` lists every command the
    typer app actually registers (positive control: at least 8)."""
    exe, env, _tool_dir, cwd_dir = _installed_tool_from_wheel

    assert len(_EXPECTED_COMMANDS) >= 8, (
        f"positive control: expected at least 8 released commands, got "
        f"{_EXPECTED_COMMANDS!r} -- the typer app registration is not "
        "being read"
    )

    version = _run([str(exe), "--version"], env, cwd=cwd_dir)
    assert version.returncode == 0, f"--version failed:\n{version.stderr}"
    assert version.stdout.strip() == _project_version(), (
        f"--version printed {version.stdout.strip()!r}, expected {_project_version()!r}"
    )

    help_out = _run([str(exe), "--help"], env, cwd=cwd_dir)
    assert help_out.returncode == 0, f"--help failed:\n{help_out.stderr}"
    # Row-anchored: a bare substring check (`c in help_out.stdout`) is fooled
    # by a command name that is itself a substring of another row's help TEXT
    # -- "load" appears inside "sync"'s and "plugins"'s description prose in
    # the real rich-rendered table above, so hiding the "load" command from
    # the Commands table entirely would still leave a naive substring check
    # green. Anchored at the start of a table row (optional box-drawing
    # prefix, then the command name, then >=2 spaces before the help text)
    # so only the command's OWN row can satisfy it.
    missing_from_help = [
        c
        for c in _EXPECTED_COMMANDS
        if re.search(rf"^\W*{re.escape(c)}\s{{2,}}", help_out.stdout, re.M) is None
    ]
    assert not missing_from_help, (
        f"--help output omits released command(s) from its Commands table: "
        f"{missing_from_help}\nfull output:\n{help_out.stdout}"
    )


def test_installed_tool_runs_every_released_commands_help_successfully(
    _installed_tool_from_wheel: tuple[Path, dict[str, str], Path, Path],
) -> None:
    """Task 7.1's named observable: "the installed console script runs
    every released command's help successfully"."""
    exe, env, _tool_dir, cwd_dir = _installed_tool_from_wheel
    assert _EXPECTED_COMMANDS, (
        "no released commands were collected -- the typer introspection is "
        "looking at the wrong app"
    )

    failures: list[tuple[str, int, str]] = []
    for command in _EXPECTED_COMMANDS:
        result = _run([str(exe), command, "--help"], env, cwd=cwd_dir)
        if result.returncode != 0:
            failures.append((command, result.returncode, result.stderr))
    assert not failures, (
        f"these installed command(s)' --help did not exit 0: {failures}"
    )


def test_installed_distribution_metadata_declares_every_required_field(
    _installed_tool_from_wheel: tuple[Path, dict[str, str], Path, Path],
) -> None:
    """Req 1.2: every field ``release/artifact-policy.toml``'s
    ``[metadata].required_fields`` names is present and non-empty in the
    INSTALLED distribution's own METADATA file -- read from disk inside the
    tool env, not via ``importlib.metadata`` (awkward across the tool's own
    interpreter boundary) -- plus a non-empty ``Requires-Dist`` and a
    non-empty message body (the long description hatchling writes there,
    never as a header)."""
    _exe, _env, tool_dir, _cwd_dir = _installed_tool_from_wheel

    metadata_files = sorted(
        p
        for p in tool_dir.glob("**/*.dist-info/METADATA")
        if p.parent.name.startswith("fitdocs-")
    )
    assert len(metadata_files) == 1, (
        f"expected exactly one installed fitdocs METADATA file under "
        f"{tool_dir}, found {metadata_files}"
    )
    metadata_text = metadata_files[0].read_text(encoding="utf-8")
    headers = Parser().parsestr(metadata_text)

    policy = load_policy(_REAL_POLICY_PATH)
    assert policy.required_metadata_fields, (
        "positive control: the policy declares no required metadata fields"
    )
    missing_or_empty = [
        field
        for field in policy.required_metadata_fields
        if not (headers.get(field) or "").strip()
    ]
    assert not missing_or_empty, (
        "installed distribution METADATA is missing or has an empty "
        f"value for required field(s): {missing_or_empty}"
    )

    requires_dist = headers.get_all("Requires-Dist") or []
    assert requires_dist, (
        "installed distribution METADATA declares no Requires-Dist entries"
    )

    _header_text, _sep, body = metadata_text.partition("\n\n")
    assert body.strip(), "installed distribution METADATA has an empty body"


def test_installed_tool_skill_lists_both_packaged_skills(
    _installed_tool_from_wheel: tuple[Path, dict[str, str], Path, Path],
) -> None:
    """Design.md E2E "Skill command": ``fitdocs skill`` (no argument) lists
    :data:`PACKAGED_SKILLS`, from the installed tool."""
    exe, env, _tool_dir, cwd_dir = _installed_tool_from_wheel
    assert PACKAGED_SKILLS, "positive control: the skill registry is empty"

    result = _run([str(exe), "skill"], env, cwd=cwd_dir)
    assert result.returncode == 0, f"`fitdocs skill` failed:\n{result.stderr}"
    missing = [name for name in PACKAGED_SKILLS if name not in result.stdout]
    assert not missing, (
        f"`fitdocs skill` listing omits registered skill(s): {missing}\n"
        f"full output:\n{result.stdout}"
    )


def test_installed_tool_skill_name_prints_a_directory_matching_frontmatter(
    tmp_path: Path,
    _installed_tool_from_wheel: tuple[Path, dict[str, str], Path, Path],
) -> None:
    """Design.md E2E "Skill command": ``fitdocs skill <name>`` prints an
    existing directory inside the tool env whose final path component is
    the skill name, and copying it (the 5.4 recipe technique) into a
    scratch skills directory yields a ``SKILL.md`` whose frontmatter
    ``name`` matches the directory it was copied to."""
    exe, env, tool_dir, cwd_dir = _installed_tool_from_wheel
    name = INBOX_SKILL_NAME

    result = _run([str(exe), "skill", name], env, cwd=cwd_dir)
    assert result.returncode == 0, f"`fitdocs skill {name}` failed:\n{result.stderr}"

    first_line = result.stdout.splitlines()[0].strip()
    printed_root = Path(first_line)
    assert printed_root.is_dir(), (
        f"printed skill path {printed_root} is not a directory"
    )
    assert printed_root.name == name, (
        f"printed skill path's final component {printed_root.name!r} != {name!r}"
    )
    assert str(printed_root).startswith(str(tool_dir)), (
        f"printed skill path {printed_root} is not inside the installed "
        f"tool env {tool_dir}"
    )

    skill_md = printed_root / "SKILL.md"
    assert skill_md.is_file(), f"{skill_md} does not exist"

    scratch_skills_dir = tmp_path / "skills" / name
    shutil.copytree(printed_root, scratch_skills_dir)
    copied_text = (scratch_skills_dir / "SKILL.md").read_text(encoding="utf-8")
    _opening, frontmatter_text, _body = copied_text.split("---\n", 2)
    frontmatter = yaml.safe_load(frontmatter_text)
    assert isinstance(frontmatter, dict)
    assert frontmatter["name"] == scratch_skills_dir.name == name


# --- Req 1.7: install and no-data-root commands create no user-facing state


def _snapshot_tree(root: Path) -> frozenset[Path]:
    """Every path (file or directory) under *root*, or the empty set if
    *root* does not exist -- a full recursive walk, not merely a
    top-level listing, so a write nested several directories deep is
    caught too."""
    if not root.exists():
        return frozenset()
    return frozenset(root.rglob("*"))


def test_install_and_no_data_root_commands_write_only_inside_uv_owned_dirs(
    tmp_path: Path,
    _built_wheel_7_1: Path,
    _real_uv_cache_dir: str,
) -> None:
    """Req 1.7: installing creates no directory, configuration file,
    profile, or data root anywhere on the user's machine; running the
    commands that need no data root (``--version``, ``--help``,
    ``plugins``, ``skill``) writes nothing either.

    ``tool_dir``/``bin_dir`` are siblings of ``fake_home``, never nested
    under it (see :func:`_hermetic_tool_env`), so any new path found under
    ``fake_home`` after the install/run is, by construction, outside the
    uv-owned dirs the tool is allowed to write to.
    """
    uv = shutil.which("uv")
    assert uv is not None
    env, fake_home, _tool_dir, bin_dir = _hermetic_tool_env(
        tmp_path, _real_uv_cache_dir
    )
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()

    # Falsity in the starting state: both trees are empty before anything
    # runs, so "no new state" below is not vacuously true.
    before_home = _snapshot_tree(fake_home)
    before_cwd = _snapshot_tree(cwd_dir)
    assert not before_home, f"fake HOME is not empty before the install: {before_home}"
    assert not before_cwd, (
        f"fake cwd is not empty before running the tool: {before_cwd}"
    )

    install = _install_wheel_offline(uv, _built_wheel_7_1, env)
    assert install.returncode == 0, (
        f"install failed:\n{install.stdout}\n{install.stderr}"
    )
    exe = bin_dir / "fitdocs"
    assert exe.exists(), f"installed fitdocs console script not found in {bin_dir}"

    for args in (["--version"], ["--help"], ["plugins"], ["skill"]):
        result = subprocess.run(
            [str(exe), *args],
            env=env,
            cwd=str(cwd_dir),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
            check=False,
        )
        assert result.returncode == 0, (
            f"`fitdocs {' '.join(args)}` failed (cwd needs no data root):\n"
            f"{result.stderr}"
        )

    after_home = _snapshot_tree(fake_home)
    after_cwd = _snapshot_tree(cwd_dir)

    new_home_paths = sorted(after_home - before_home)
    new_cwd_paths = sorted(after_cwd - before_cwd)
    all_new_paths = (*new_home_paths, *new_cwd_paths)

    # Named markers first (Req 1.7's data-root shape) -- computed and
    # asserted BEFORE the broader emptiness checks below, so this specific,
    # named-category check is itself reached (and can itself fail) rather
    # than being unreachable dead code behind a stricter assertion that
    # already failed first.
    forbidden_names = {".fitdocs", "fitdocs.toml", "athlete.toml", "workouts"}
    forbidden_hits = [path for path in all_new_paths if path.name in forbidden_names]
    assert not forbidden_hits, f"data-root-shaped path(s) appeared: {forbidden_hits}"

    assert not new_home_paths, (
        "install and running --version/--help/plugins/skill created new "
        f"path(s) under the fake HOME: {new_home_paths}"
    )
    assert not new_cwd_paths, (
        "running the no-data-root commands created new path(s) in the "
        f"working directory: {new_cwd_paths}"
    )

    _run([uv, "tool", "uninstall", "fitdocs"], env)


# --- Req 2.4: the real uninstalled-checkout case ----------------------------


@pytest.fixture(scope="module")
def _uninstalled_checkout_python(
    tmp_path_factory: pytest.TempPathFactory, _real_uv_cache_dir: str
) -> Path:
    """A scratch venv holding fitdocs' five runtime dependencies but NOT
    fitdocs itself as an installed distribution -- the REAL "uninstalled
    checkout" case (Req 2.4), distinct from task 1.1's patched-metadata-
    lookup simulation (``tests/test_version_identity.py``), which only
    proves the code path degrades gracefully under a *simulated* absence.
    Built once (module scope): a fresh ``uv venv`` plus an ``--offline
    uv pip install`` of exactly ``[project].dependencies`` from the warm
    project cache -- both well under a second warm.
    """
    uv = shutil.which("uv")
    assert uv is not None
    scratch = tmp_path_factory.mktemp("uninstalled_checkout_venv")
    venv_dir = scratch / "venv"
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = _real_uv_cache_dir

    create = _run([uv, "venv", str(venv_dir), "--python", "3.11"], env)
    assert create.returncode == 0, (
        f"`uv venv` failed:\n{create.stdout}\n{create.stderr}"
    )

    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    assert dependencies, (
        "positive control: pyproject.toml declares no runtime dependencies"
    )

    python = venv_dir / "bin" / "python"
    offline = _run(
        [uv, "pip", "install", "--python", str(python), "--offline", *dependencies],
        env,
    )
    if offline.returncode != 0:
        # Cold cache (e.g. a CI runner whose cache was populated only by
        # `uv sync`, not by an isolated `uv pip install` into a bare venv):
        # warm it with one online resolve, then retry offline so the
        # asserted install is still the offline one.
        warm = _run([uv, "pip", "install", "--python", str(python), *dependencies], env)
        assert warm.returncode == 0, (
            "could not offline-install fitdocs' runtime dependencies into the "
            "scratch venv from the warm project cache, and warming the cache "
            f"online also failed:\n{warm.stdout}\n{warm.stderr}"
        )
        offline = _run(
            [uv, "pip", "install", "--python", str(python), "--offline", *dependencies],
            env,
        )
    assert offline.returncode == 0, (
        "could not offline-install fitdocs' runtime dependencies into the "
        "scratch venv even after warming the cache:\n"
        f"{offline.stdout}\n{offline.stderr}"
    )
    assert python.is_file(), f"scratch venv python not found at {python}"
    return python


_UNINSTALLED_RUN_SCRIPT = """
import sys
sys.path.insert(0, {src!r})
from fitdocs.cli import app
from typer.testing import CliRunner

runner = CliRunner()
result = runner.invoke(app, {args!r})
print("EXIT", result.exit_code)
sys.stdout.write("OUT_START\\n")
sys.stdout.write(result.output)
sys.stdout.write("OUT_END\\n")
"""


def _run_uninstalled(python: Path, args: list[str]) -> tuple[int, str]:
    script = _UNINSTALLED_RUN_SCRIPT.format(src=str(_PROJECT_ROOT / "src"), args=args)
    result = subprocess.run(
        [str(python), "-c", script],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    assert result.returncode == 0, (
        f"driver script itself failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    exit_line = next(
        line for line in result.stdout.splitlines() if line.startswith("EXIT ")
    )
    exit_code = int(exit_line.split()[1])
    out_start = result.stdout.index("OUT_START\n") + len("OUT_START\n")
    out_end = result.stdout.index("OUT_END\n")
    return exit_code, result.stdout[out_start:out_end]


def test_real_uninstalled_checkout_reports_unknown_version_and_exits_0(
    _uninstalled_checkout_python: Path,
) -> None:
    """Req 2.4, the REAL case: ``fitdocs.cli`` imported from ``src/`` via
    ``sys.path`` in an interpreter where fitdocs is NOT an installed
    distribution reports :data:`UNKNOWN_VERSION` and exits 0, and
    continues to operate normally (``--help`` also exits 0)."""
    # Precondition / reachability: fitdocs really is not resolvable as an
    # installed distribution in this interpreter -- otherwise "unknown"
    # below would hold for the wrong reason (or vacuously).
    check = subprocess.run(
        [
            str(_uninstalled_checkout_python),
            "-c",
            "import importlib.metadata as m\n"
            "try:\n"
            "    m.version('fitdocs')\n"
            "    print('INSTALLED')\n"
            "except m.PackageNotFoundError:\n"
            "    print('NOT_INSTALLED')\n",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.stdout.strip() == "NOT_INSTALLED", (
        "scratch venv precondition failed -- fitdocs IS resolvable as an "
        f"installed distribution there: {check.stdout!r} {check.stderr!r}"
    )

    exit_code, output = _run_uninstalled(_uninstalled_checkout_python, ["--version"])
    assert exit_code == 0, f"--version exited {exit_code}, output: {output!r}"
    assert output.strip() == UNKNOWN_VERSION, (
        f"expected the unknown-version token {UNKNOWN_VERSION!r}, got "
        f"{output.strip()!r}"
    )

    help_exit, help_output = _run_uninstalled(_uninstalled_checkout_python, ["--help"])
    assert help_exit == 0, f"--help exited {help_exit}, output: {help_output!r}"


def test_venv_installed_checkout_reports_the_real_version_not_unknown() -> None:
    """Contrast for the test above, proving the scrub in the scratch venv
    is doing real work rather than the driver script always printing
    "unknown" regardless of environment: this repo's OWN ``.venv`` (where
    ``uv sync`` installs fitdocs editable, so it IS a resolvable
    distribution) reports the real released version through the identical
    CLI invocation path, never the unknown token."""
    venv_python = _PROJECT_ROOT / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        venv_python = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    assert venv_python.is_file(), f".venv python not found at {venv_python}"

    result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "from fitdocs.cli import app\n"
            "from typer.testing import CliRunner\n"
            "r = CliRunner().invoke(app, ['--version'])\n"
            "print(r.exit_code)\n"
            "print(r.output, end='')\n",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"`.venv` invocation failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    lines = result.stdout.splitlines()
    assert lines, "no output from `.venv` invocation"
    assert lines[0] == "0", f"exit code line was {lines[0]!r}, not '0'"
    printed_version = lines[1].strip() if len(lines) > 1 else ""
    assert printed_version == _project_version(), (
        f"`.venv` install printed {printed_version!r}, expected the real "
        f"released version {_project_version()!r}"
    )
    assert printed_version != UNKNOWN_VERSION
