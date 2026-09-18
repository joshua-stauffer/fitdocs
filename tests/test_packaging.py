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
from email.parser import Parser
from pathlib import Path

import tomli_w

from tests.test_forbidden_strings import _build_artifact

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TIMEOUT_S = 300


def _project_version() -> str:
    """The version declared in ``pyproject.toml`` -- what ``--version`` must print."""
    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = data["project"]["version"]
    assert isinstance(version, str) and version
    return version


def _run(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a subprocess capturing text output, without raising on failure."""
    return subprocess.run(
        cmd,
        env=env,
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
