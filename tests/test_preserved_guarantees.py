"""Task 7.2: preserved guarantees, re-asserted at the *feature* level (Req
10.1, 10.4, 10.5).

This feature (distribution) must cost nothing in behavior: no new runtime
dependency, no new runtime network access, a stable public import surface,
and reproducible builds. Every one of these properties already has *some*
coverage from an earlier task in this plan (``tests/test_determinism.py``,
``tests/test_release_artifacts.py``, ``tests/test_public_api.py``,
``tests/test_version_identity.py``, the golden suites). This module does not
re-derive that coverage; it adds the one assertion each earlier task's own
scope did not need: a pin against the *pre-feature revision* (``e74af37``,
the commit this plan's worktree branched from) for the runtime dependency
set.

**Retired after the feature landed (2026-09-30, maintainer-approved).** Three
further pins held ``fitdocs.__all__``, every golden-document tree and
``src/fitdocs/render/`` byte-identical to ``e74af37``. They guarded the
distribution plan while it was in flight; once it shipped they could only
red on every later feature that adds a public name, a sample channel or
a page section (Phase 8, first met by running-dynamics). The standing
guarantees are held where they always were: ``tests/test_public_api.py``'s
``_EXPECTED`` for the public surface and each golden suite for its documents.

**Fetch-depth-1 safety (round-1 rejection).** CI checks out at
``actions/checkout@v4``'s default ``fetch-depth: 1`` and that workflow
setting is not being changed for this task. A shallow clone does not carry
the ``e74af37`` commit object, so ``git show e74af37:...``, ``git diff
e74af37 HEAD``, and ``git rev-list --max-parents=0`` all fail there even
though they work in this full-history worktree. The dependency comparison
below instead reads a committed snapshot of what ``e74af37`` held:
``tests/fixtures/pre_distribution_e74af37.py`` (dependency list, optional-
dependencies). No test in this module reads git history.

Five groups below:

1. Runtime dependencies unchanged vs the pre-feature snapshot (10.1).
2. No new runtime network access from the two runtime surfaces this feature
   added -- :mod:`fitdocs.version` and the ``skill``/``plugins``/``--version``
   CLI paths that read it (10.4).
3. Reproducibility re-asserted at the feature level: two full builds of HEAD,
   member names AND per-member digests (10.5).
4. Neither new package module is reachable from the package root -- as an
   ``__all__`` member, as a runtime attribute, or as a top-level import
   (10.1, policy's documented-is-public rule).
5. Observable: a build attempted offline against the real ``uv`` cache
   first, falling back to a real-network warm-up and offline retry only
   when that cache turns out cold, plus a subprocess import check.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest import mock

import pytest
import scripts.build_release as build_release
from typer.testing import CliRunner

import tests.fixtures.pre_distribution_e74af37 as pre_distribution
from fitdocs.agentskill import PACKAGED_SKILLS, skill_file, skill_files, skill_root
from fitdocs.cli import app
from fitdocs.version import UNKNOWN_VERSION, tool_version, version_display
from tests.test_determinism import _no_socket

REPO_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


# ---------------------------------------------------------------------------
# 1. Runtime dependencies unchanged vs the pre-feature snapshot (10.1)
# ---------------------------------------------------------------------------


def _dependencies_on_disk() -> list[str]:
    """The CURRENT working tree's ``[project].dependencies`` -- read straight
    off disk, never via a git history read, so an uncommitted mutation to
    ``pyproject.toml`` (the discrimination fixture) is actually observed
    rather than silently masked by comparing two committed snapshots."""
    manifest = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    dependencies = manifest["project"]["dependencies"]
    assert dependencies, "working tree's [project].dependencies is empty"
    return list(dependencies)


def test_dependencies_unchanged_from_pre_feature_snapshot_as_set_and_ordered_list() -> (
    None
):
    base = list(pre_distribution.DEPENDENCIES)
    head = _dependencies_on_disk()

    assert len(base) > 1  # the snapshot is non-trivial, not a vacuous pass
    assert set(head) == set(base)
    assert head == base  # ordering preserved too, not just membership


def test_no_new_runtime_optional_dependency_group_vs_pre_feature_snapshot() -> None:
    head_manifest = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())

    assert pre_distribution.OPTIONAL_DEPENDENCIES == {}
    assert head_manifest["project"].get("optional-dependencies", {}) == {}


# ---------------------------------------------------------------------------
# 2. No new runtime network access (10.4)
# ---------------------------------------------------------------------------


def _plain_data_root(tmp_path: Path) -> Path:
    """A bare, unconfigured data root. ``--version``/``skill``/``plugins``
    read no ``[tiles]`` settings (only ``sync``/``regen`` build a
    ``TileStore``), so no ``fitdocs.toml`` is written here -- writing one
    that disables tiles would misleadingly imply these commands consult it.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    return data_root


def test_version_source_performs_no_network_access() -> None:
    """``tool_version()``/``version_display()`` construct no socket on the
    resolved (installed) path."""
    with mock.patch("socket.socket", _no_socket):
        tool_version()
        assert version_display() != ""  # never empty


def test_version_display_performs_no_network_access_on_the_unresolved_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The *unresolved* branch -- ``tool_version()`` returning ``None`` --
    is never reached under ``_no_socket`` in this dev venv (fitdocs IS
    installed here), so the resolved-path test above cannot catch a socket
    hidden behind ``except PackageNotFoundError``. Patches the lookup itself
    to raise, so the unresolved branch is genuinely exercised (round-1
    finding M2b)."""

    def _raise(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("fitdocs.version.version", _raise)

    with mock.patch("socket.socket", _no_socket):
        assert tool_version() is None
        assert version_display() == UNKNOWN_VERSION


def test_agentskill_resolution_performs_no_network_access() -> None:
    """Skill-path resolution for every packaged skill opens no socket."""
    assert len(PACKAGED_SKILLS) >= 2, (
        "fewer packaged skills than expected -- wrong data"
    )
    with mock.patch("socket.socket", _no_socket):
        for name in PACKAGED_SKILLS:
            root = skill_root(name)
            assert root is not None, f"packaged skill {name!r} not installed"
            assert skill_file(name) is not None
            assert skill_files(name), f"{name}'s skill_files() is empty"


def test_cli_version_skill_and_plugins_commands_perform_no_network_access(
    tmp_path: Path,
) -> None:
    """``--version``, ``skill`` (listing and by-name), and ``plugins`` --
    run against a plain tmp data root -- construct no socket.

    Real observable behavior asserted first (non-vacuous: each invocation
    actually did the thing, not merely "did not crash"), then the whole
    group re-run under the guard, including the unresolved-version path
    through the CLI (round-1 finding M2b, CLI half).
    """
    data_root = _plain_data_root(tmp_path)

    baseline_version = runner.invoke(app, ["--version"])
    assert baseline_version.exit_code == 0
    baseline_skill_list = runner.invoke(app, ["skill"])
    assert baseline_skill_list.exit_code == 0
    for name in PACKAGED_SKILLS:
        assert name in baseline_skill_list.stdout
    baseline_plugins = runner.invoke(app, ["plugins", "--out", str(data_root)])
    assert baseline_plugins.exit_code == 0
    # The degraded ("no data root resolved") branch's message must not
    # appear when a real data root WAS resolved and consulted.
    assert "no local plugin configuration was consulted" not in baseline_plugins.stdout

    with mock.patch("socket.socket", _no_socket):
        version_result = runner.invoke(app, ["--version"])
        assert version_result.exit_code == 0

        skill_list_result = runner.invoke(app, ["skill"])
        assert skill_list_result.exit_code == 0

        for name in PACKAGED_SKILLS:
            skill_by_name_result = runner.invoke(app, ["skill", name])
            assert skill_by_name_result.exit_code == 0

        plugins_result = runner.invoke(app, ["plugins", "--out", str(data_root)])
        assert plugins_result.exit_code == 0


def test_cli_version_unresolved_path_performs_no_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--version`` from an uninstalled tree (patched lookup) prints the
    unknown token, exits 0, and constructs no socket."""

    def _raise(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("fitdocs.version.version", _raise)

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert UNKNOWN_VERSION in result.stdout


# ---------------------------------------------------------------------------
# 3. Reproducibility at the feature level (10.5)
# ---------------------------------------------------------------------------

_FEATURE_EPOCH = 1_650_000_000


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _artifact(paths: tuple[Path, ...], suffix: str) -> Path:
    matches = [p for p in paths if p.name.endswith(suffix)]
    assert len(matches) == 1, (
        f"expected exactly one {suffix!r} artifact, got {matches!r}"
    )
    return matches[0]


def _zip_member_digests(path: Path) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        return {name: _sha256_bytes(archive.read(name)) for name in archive.namelist()}


def _tar_member_digests(path: Path) -> dict[str, str]:
    with tarfile.open(path, "r:gz") as archive:
        digests = {}
        for member in archive.getmembers():
            if member.isfile():
                extracted = archive.extractfile(member)
                assert extracted is not None
                digests[member.name] = _sha256_bytes(extracted.read())
        return digests


@pytest.fixture(scope="module")
def _feature_build_1(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ...]:
    out_dir = tmp_path_factory.mktemp("feature_build_1")
    return build_release.build(out_dir=out_dir, source_date_epoch=_FEATURE_EPOCH)


@pytest.fixture(scope="module")
def _feature_build_2(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ...]:
    out_dir = tmp_path_factory.mktemp("feature_build_2")
    return build_release.build(out_dir=out_dir, source_date_epoch=_FEATURE_EPOCH)


def test_two_builds_of_head_yield_identical_member_names_and_digests(
    _feature_build_1: tuple[Path, ...], _feature_build_2: tuple[Path, ...]
) -> None:
    wheel_1 = _artifact(_feature_build_1, ".whl")
    wheel_2 = _artifact(_feature_build_2, ".whl")
    sdist_1 = _artifact(_feature_build_1, ".tar.gz")
    sdist_2 = _artifact(_feature_build_2, ".tar.gz")

    wheel_digests_1 = _zip_member_digests(wheel_1)
    wheel_digests_2 = _zip_member_digests(wheel_2)
    assert wheel_digests_1, "wheel manifest is empty -- nothing was actually scanned"
    assert sorted(wheel_digests_1) == sorted(wheel_digests_2)
    assert wheel_digests_1 == wheel_digests_2
    assert _sha256_file(wheel_1) == _sha256_file(wheel_2)

    sdist_digests_1 = _tar_member_digests(sdist_1)
    sdist_digests_2 = _tar_member_digests(sdist_2)
    assert sdist_digests_1, "sdist manifest is empty -- nothing was actually scanned"
    assert sorted(sdist_digests_1) == sorted(sdist_digests_2)
    assert sdist_digests_1 == sdist_digests_2
    assert _sha256_file(sdist_1) == _sha256_file(sdist_2)


def test_reproducibility_assertion_is_sensitive_to_a_different_epoch(
    tmp_path_factory: pytest.TempPathFactory, _feature_build_1: tuple[Path, ...]
) -> None:
    """Discrimination control for the digest-equality assertion above: a
    build of HEAD at a different epoch must NOT match ``_feature_build_1``'s
    whole-file digest, proving the equality assertion actually compares
    content rather than being vacuously true for any two builds. The delta
    is large (not +1 second) because the ZIP format's DOS timestamp field
    has 2-second resolution -- a 1-second epoch bump would round-trip to
    the identical stored timestamp and falsely look reproducible.

    (Investigated but NOT pinned, round-1 finding: dropping
    ``SOURCE_DATE_EPOCH`` from the build environment entirely does not
    discriminate in this toolchain -- the hatchling resolved at build time
    (unpinned: ``build-system.requires = ["hatchling"]`` carries no version
    constraint and hatchling is absent from ``uv.lock``) defaults
    wheel/sdist member times to a fixed constant, not wall-clock time, when
    the variable is absent, so two such builds are still byte-identical to
    each other. ``build_release.build`` itself always sets the variable
    regardless; that call-shape is already pinned in
    ``tests/test_release_artifacts.py``'s
    ``test_build_invokes_uv_with_expected_command_env_and_cwd``.)
    """
    out_dir = tmp_path_factory.mktemp("feature_build_different_epoch")
    other_epoch_build = build_release.build(
        out_dir=out_dir, source_date_epoch=_FEATURE_EPOCH + 100_000
    )
    wheel_1 = _artifact(_feature_build_1, ".whl")
    wheel_other = _artifact(other_epoch_build, ".whl")
    assert _sha256_file(wheel_1) != _sha256_file(wheel_other)


# ---------------------------------------------------------------------------
# 4. Two new modules unreachable from the package root (10.1)
# ---------------------------------------------------------------------------

#: The two package modules this feature added/extended -- ``fitdocs.version``
#: (wholly new) and ``fitdocs.agentskill`` (pre-existing from
#: build-training-block, extended here with the by-name locator) -- per
#: design.md's Package (leaves) component list.
_NEW_MODULE_NAMES = ("version", "agentskill")

#: Every runtime-callable name from those two modules that must NOT be
#: reachable as a ``fitdocs.<name>`` attribute.
_NEW_MODULE_RUNTIME_NAMES = (
    "tool_version",
    "version_display",
    "skill_root",
    "skill_file",
    "skill_files",
)


def test_two_new_package_modules_absent_from_all_and_unreachable_at_runtime() -> None:
    """Neither new module's name, nor any of its runtime-callable members,
    is reachable from the package root -- not in ``__all__`` (a documentation
    pin) and not as an actual attribute access (a *runtime* pin: round-1
    finding M4c showed a stray ``_LAZY_EXPORTS`` entry stays green against
    an ``__all__``-only check, because ``__getattr__`` would still resolve
    it on demand)."""
    import fitdocs

    assert "version" not in fitdocs.__all__
    assert "agentskill" not in fitdocs.__all__
    for name in _NEW_MODULE_RUNTIME_NAMES:
        assert name not in fitdocs.__all__

    for name in _NEW_MODULE_RUNTIME_NAMES:
        with pytest.raises(AttributeError):
            getattr(fitdocs, name)


def _top_level_import_hits(tree: ast.Module, forbidden: frozenset[str]) -> set[str]:
    """Every top-level import in ``tree`` that reaches one of ``forbidden``'s
    module names: absolute-dotted (``import fitdocs.version`` /
    ``from fitdocs.version import x``), absolute-package (``from fitdocs
    import version``, round-2 finding: an ``ast.ImportFrom`` with
    ``module == "fitdocs"`` at ``level == 0`` was not covered by either the
    dotted-module branch or the relative branch and passed the scan
    silently), or package-relative (``from .version import x`` / ``from .
    import version``, i.e. ``ast.ImportFrom`` with ``level > 0``, round-1
    finding M4b: the original scan only recognized absolute
    ``fitdocs.<name>`` module strings and missed a relative import)."""
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                if node.module in forbidden:
                    hits.add(node.module)
                if node.module is None:
                    hits.update(
                        alias.name for alias in node.names if alias.name in forbidden
                    )
            elif node.module == "fitdocs":
                hits.update(
                    alias.name for alias in node.names if alias.name in forbidden
                )
            elif node.module:
                tail = node.module.rsplit(".", 1)[-1]
                if node.module.startswith("fitdocs") and tail in forbidden:
                    hits.add(tail)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                tail = alias.name.rsplit(".", 1)[-1]
                if alias.name.startswith("fitdocs") and tail in forbidden:
                    hits.add(tail)
    return hits


def test_two_new_package_modules_not_imported_at_package_root_top_level() -> None:
    init_source = (REPO_ROOT / "src" / "fitdocs" / "__init__.py").read_text()
    init_tree = ast.parse(init_source)

    hits = _top_level_import_hits(init_tree, frozenset(_NEW_MODULE_NAMES))
    assert hits == set()


def test_import_hit_scanner_is_non_vacuous() -> None:
    """Positive control for :func:`_top_level_import_hits`: both a relative
    and an absolute forbidden import are detected in synthetic source, so
    the scanner above is not vacuously permissive."""
    synthetic = "\n".join(
        [
            "from .version import tool_version",
            "from . import agentskill",
            "import fitdocs.version",
            "from fitdocs.version import tool_version as tv",
            "from fitdocs import agentskill",  # round-2 finding: absolute-package form
            "from fitdocs.model import Activity",  # negative control: unrelated
        ]
    )
    hits = _top_level_import_hits(ast.parse(synthetic), frozenset(_NEW_MODULE_NAMES))
    assert hits == {"version", "agentskill"}


# ---------------------------------------------------------------------------
# 5. Observable: the build stays offline once its uv cache is warm
# ---------------------------------------------------------------------------


def test_build_succeeds_offline_against_the_real_uv_cache_with_a_warm_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """7.1's ordering (round-2 finding: the round-1 version *always* warmed a
    scratch cache with one real-network build before attempting anything
    offline, which downloads ~2 MB from PyPI on every run and fails outright
    under ``UV_OFFLINE=1 uv run --offline pytest ...`` -- self-defeating for
    a test whose own point is proving the run stays offline).

    Ordering: attempt the build FIRST, under dead proxies, against ``uv
    cache dir``'s REAL cache -- whatever warmth a developer machine or CI
    already gave it. Only on ``BuildError`` (the cache was cold -- CI's
    cache is `uv sync`-only, never `uv build`-only, per the 6.4/7.1 note)
    does this test strip the proxies, warm that SAME cache with one real-
    network build, then retry under dead proxies again and assert the RETRY
    succeeded. On a warm cache (this dev machine; ``UV_OFFLINE=1``'s forced-
    offline mode) the fallback branch never runs and no network is ever
    touched.

    ``subprocess.run`` is wrapped to record every call's ``env``, so the
    final assertions can confirm the specific build whose result is being
    asserted on (the first attempt if it succeeded, otherwise the retry)
    actually ran with the dead proxies still in place -- not a silent
    "succeeded, but only because it went back online" false pass (round-2
    finding (d)).
    """
    cache_dir_result = subprocess.run(
        ["uv", "cache", "dir"], capture_output=True, text=True, check=True
    )
    cache_dir = cache_dir_result.stdout.strip()
    assert cache_dir, "`uv cache dir` printed nothing"

    dead_proxy = "http://127.0.0.1:9"
    monkeypatch.setenv("UV_CACHE_DIR", cache_dir)
    monkeypatch.setenv("HTTP_PROXY", dead_proxy)
    monkeypatch.setenv("HTTPS_PROXY", dead_proxy)

    recorded_envs: list[dict[str, str]] = []
    real_run = subprocess.run

    def _recording_run(
        cmd: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        recorded_envs.append(dict(kwargs.get("env") or {}))  # type: ignore[arg-type]
        return real_run(cmd, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", _recording_run)

    try:
        result = build_release.build(
            out_dir=tmp_path / "dist_offline_first",
            source_date_epoch=_FEATURE_EPOCH,
        )
    except build_release.BuildError:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        build_release.build(
            out_dir=tmp_path / "dist_warm_fallback",
            source_date_epoch=_FEATURE_EPOCH,
        )

        monkeypatch.setenv("HTTP_PROXY", dead_proxy)
        monkeypatch.setenv("HTTPS_PROXY", dead_proxy)
        result = build_release.build(
            out_dir=tmp_path / "dist_offline_retry",
            source_date_epoch=_FEATURE_EPOCH,
        )

    assert len(result) == 2
    for path in result:
        assert path.exists()
        assert path.stat().st_size > 0

    assert recorded_envs, (
        "subprocess.run was never called -- build_release.build changed?"
    )
    last_env = recorded_envs[-1]
    assert last_env.get("HTTP_PROXY") == dead_proxy
    assert last_env.get("HTTPS_PROXY") == dead_proxy


def test_release_tooling_import_performs_no_network_access() -> None:
    """Freshly importing the release-tooling and version-resolution modules
    performs no network access -- guards against a future import-time
    metadata/index fetch creeping into ``scripts.build_release``,
    ``scripts.check_artifacts``, or ``fitdocs.version`` (round-1 finding:
    the original version of this test reloaded ``build_release`` only via
    ``importlib.reload``, despite naming ``check_artifacts`` in its own
    title, and never touched ``fitdocs.version`` at all).

    Run in a SUBPROCESS, not ``importlib.reload`` in-process: reloading
    ``scripts.check_artifacts`` rebinds ``CheckerError`` to a brand-new
    class object in this process, which desyncs every ``pytest.raises
    (CheckerError)`` in ``tests/test_release_artifacts.py`` that captured
    the pre-reload class at its own collection time -- a real regression
    surfaced by running this file together with that one during
    remediation. A subprocess exercises a genuinely fresh import (as if the
    module had never been loaded) without corrupting any class identity the
    rest of the suite depends on.

    Invoked as ``[sys.executable, "-c", probe]`` (round-2 finding: not
    ``uv run python -c ...`` -- ``uv run`` can decide to resync or relock
    the project when it notices a manifest change mid-remediation, and a
    failure from THAT is indistinguishable from a real network regression
    without reading the subprocess's stderr closely). ``sys.executable`` is
    the exact interpreter already running this test, in the same venv, so
    ``scripts``/``fitdocs`` resolve identically with no extra resolution
    step.
    """
    probe = (
        "import socket\n"
        "class _NetworkAttempted(Exception):\n"
        "    pass\n"
        "def _no_socket(*a, **k):\n"
        "    raise _NetworkAttempted('socket construction attempted')\n"
        "socket.socket = _no_socket\n"
        "import scripts.build_release\n"
        "import scripts.check_artifacts\n"
        "import fitdocs.version\n"
        "assert fitdocs.version.DIST_NAME == 'fitdocs'\n"
        "print('IMPORT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout
