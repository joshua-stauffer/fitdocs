"""Plugin-discovery install smoke test (task 4.1): verify entry-point discovery
against a REALLY installed plugin distribution, not only an injected source.

This mirrors ``tests/test_packaging.py``'s isolated ``uv tool install`` smoke
(``UV_TOOL_DIR``/``UV_TOOL_BIN_DIR`` under ``tmp_path``, offline-first with an
online cache-warm fallback, ``finally: uv tool uninstall``). The ONE
difference: alongside fitdocs from THIS checkout, it also installs the
minimal fixture distribution at ``tests/fixtures/plugin_pkg`` (``uv tool
install ... --with <fixture dir>``) which advertises a trivial RUN load
calculator via the ``fitdocs.load_calculators`` entry-point group
(``fitdocs-fixture-calc==9.9.9``, entry point ``fixture ->
fitdocs_fixture_calc:FixtureCalculator``).

It then runs the INSTALLED ``fitdocs plugins`` binary in the degraded-listing
path (an empty cwd with no fitdocs data-root variable set, so
``resolve_data_root`` fails, ``data_root`` is ``None``, and ``discover(None,
DEFAULT_PLUGIN_SETTINGS)`` runs the entry-point channel only -- Req 4.7) and
asserts the listing names the fixture calculator's id, the fixture
distribution's NAME, and its VERSION -- proving keyless discovery, provenance,
and version rendering all work from a real install (Req 1.1, 4.1, 4.2, 4.3,
6.1). It does not repeat the shipped-``py.typed`` assertion --
``tests/test_packaging.py::test_tool_install_ships_py_typed_marker`` owns that
(task 1.3).

Runtime: dominated by two-or-fewer ``uv tool install`` invocations, each of
which must additionally build the fixture's wheel; a few seconds on a warm
cache, longer on a cold one that must warm online once.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_DIST = _PROJECT_ROOT / "tests" / "fixtures" / "plugin_pkg"
_TIMEOUT_S = 300

_FIXTURE_CALCULATOR_ID = "fixture-calc"
_FIXTURE_DIST_NAME = "fitdocs-fixture-calc"
_FIXTURE_DIST_VERSION = "9.9.9"


def _run(
    cmd: list[str], env: dict[str, str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess capturing text output, without raising on failure."""
    return subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )


def _install_offline(uv: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Install fitdocs, together with the fixture plugin distribution, offline
    into the isolated tool dirs.

    Mirrors ``tests/test_packaging.py``'s ``_install_offline``: a cold uv cache
    can fail an offline *resolution* even when the wheels exist; if so, warm
    the cache with a single online resolve into the same isolated dirs,
    uninstall, and retry offline -- the returned result is always the OFFLINE
    install, so the assertion still proves offline installability.
    """
    from_spec = str(_PROJECT_ROOT)
    with_spec = str(_FIXTURE_DIST)
    offline = _run(
        [
            uv,
            "tool",
            "install",
            "--offline",
            "--from",
            from_spec,
            "--with",
            with_spec,
            "fitdocs",
        ],
        env,
    )
    if offline.returncode == 0:
        return offline
    warm = _run(
        [uv, "tool", "install", "--from", from_spec, "--with", with_spec, "fitdocs"],
        env,
    )
    assert warm.returncode == 0, (
        "could not install fitdocs + the fixture plugin distribution offline "
        f"(cold cache) and warming the uv cache online also failed:\n"
        f"{warm.stdout}\n{warm.stderr}"
    )
    _run([uv, "tool", "uninstall", "fitdocs"], env)
    return _run(
        [
            uv,
            "tool",
            "install",
            "--offline",
            "--from",
            from_spec,
            "--with",
            with_spec,
            "fitdocs",
        ],
        env,
    )


def test_installed_plugins_listing_names_fixture_distribution_and_version(
    tmp_path: Path,
) -> None:
    """A REALLY installed distribution's entry-point calculator is listed by
    the installed ``fitdocs plugins`` binary with its distribution name and
    version (Req 1.1, 4.1, 4.2, 4.3, 6.1) -- not merely with an injected
    ``entry_points_fn`` as in ``tests/test_plugins.py``.

    Install is ISOLATED (``UV_TOOL_DIR``/``UV_TOOL_BIN_DIR`` under
    ``tmp_path``) and OFFLINE-first, exactly like
    ``tests/test_packaging.py``. The listing itself runs in the degraded path
    (no resolvable data root, Req 4.7): an empty cwd with the fitdocs
    data-root environment variable scrubbed, so the entry-point channel runs
    without any local plugin configuration."""
    uv = shutil.which("uv")
    assert uv is not None, (
        "uv is required for the plugin-install smoke test but was not found on "
        "PATH; install uv (https://docs.astral.sh/uv/) to run the install smoke"
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
            f"offline `uv tool install` (fitdocs + fixture plugin) failed:\n"
            f"{install.stdout}\n{install.stderr}"
        )

        exe = bin_dir / "fitdocs"
        if not exe.exists():  # console scripts are `.exe` on Windows
            exe = bin_dir / "fitdocs.exe"
        assert exe.exists(), f"installed fitdocs console script not found in {bin_dir}"

        # The degraded-listing path (Req 4.7): an empty cwd with no fitdocs
        # data-root variable set, so `resolve_data_root` fails and
        # `data_root` is None -- only the entry-point channel runs, which is
        # exactly the channel this test exercises. `COLUMNS`/`TERM` keep the
        # installed binary's own rich table from wrapping/truncating the
        # assertions apart regardless of the invoking terminal.
        empty_cwd = tmp_path / "empty-cwd"
        empty_cwd.mkdir()
        listing_env = env.copy()
        listing_env.pop("FITDOCS_DATA", None)
        # `rich.Console.size` treats a `dumb` TERM as forcing a fixed 80x25
        # size regardless of COLUMNS, so a non-dumb TERM is required for
        # COLUMNS to actually widen the table and keep cell text unwrapped.
        listing_env["COLUMNS"] = "400"
        listing_env["TERM"] = "xterm-256color"

        listing = _run([str(exe), "plugins"], listing_env, cwd=empty_cwd)
        assert listing.returncode == 0, (
            f"installed `fitdocs plugins` failed:\n{listing.stdout}\n{listing.stderr}"
        )
        output = listing.stdout
        assert _FIXTURE_CALCULATOR_ID in output, (
            f"fixture calculator id {_FIXTURE_CALCULATOR_ID!r} not found in "
            f"`fitdocs plugins` output:\n{output}"
        )
        assert _FIXTURE_DIST_NAME in output, (
            f"fixture distribution name {_FIXTURE_DIST_NAME!r} not found in "
            f"`fitdocs plugins` output:\n{output}"
        )
        assert _FIXTURE_DIST_VERSION in output, (
            f"fixture distribution version {_FIXTURE_DIST_VERSION!r} not found in "
            f"`fitdocs plugins` output:\n{output}"
        )
    finally:
        # Clean up the isolated install regardless of assertion outcome; ignore the
        # result since a failed/partial install leaves nothing to uninstall.
        _run([uv, "tool", "uninstall", "fitdocs"], env)
