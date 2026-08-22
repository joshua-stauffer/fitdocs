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

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

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
