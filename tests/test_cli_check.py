"""CLI end-to-end tests: the ``fitdocs check`` command (task 6.2).

Drives the installable entry point through :class:`typer.testing.CliRunner`
over real temporary data roots (built with the workout-docs pipeline via
:func:`fitdocs.sync.sync`), locking the observable contract of task 6.2:

* ``fitdocs check [--out PATH]`` resolves the data root through the existing
  resolver, runs the read-only :func:`fitdocs.audit.audit` pass, and prints a
  summary table plus a per-finding detail listing (subject, detail, remedy)
  -- never a tile store, an athlete profile, or the load pass.
* Exit codes map onto the existing contract (Req 8.7): ``0`` when nothing is
  found, ``1`` when the audit reports one or more findings, ``2`` when the
  data root cannot be resolved -- and in that last case, nothing is scanned:
  ``audit`` is never called.

Content assertions read ``result.output`` directly. Every detail line the CLI
prints uses ``markup=False, soft_wrap=True`` (mirroring
``_report``/``_report_load``): ``soft_wrap=True`` disables Rich's line wrapping
altogether, so a long remedy sentence is written back unbroken regardless of
console width, and ``markup=False`` means no highlight escapes are injected
into it. Only ``--help`` needs :func:`_plain` -- see its docstring for the one
mechanism that actually defeats a naive substring assertion.

Remedy fragments asserted here must be **distinctive to a single remedy**.
Loose ones alias each other: ``"fitdocs regen"`` appears in the declaration
remedy as well as the out-of-date one, and ``"notes"``/``"region"`` appear in
the damaged-regions detail, so three of the four remedies could be blanked
entirely with this module still green until the fragments were tightened.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import cli
from fitdocs.athlete import load_athlete_inputs
from fitdocs.cli import app
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.sync import sync
from tests.fixtures import builder

runner = CliRunner()

# PINNED timezone (never the system zone) so document stems are byte-stable
# (mirrors ``tests/load/test_cli_load.py``).
_TZ = timezone(timedelta(hours=-6))


class _ServingTiles:
    """An inert always-succeeding tile source, offline (mirrors the load tests)."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    """``text`` with ANSI escapes stripped.

    Rich's highlighting inserts SGR escapes *inside* the literal it renders:
    ``--out`` is emitted as ``\\x1b[1;36m-\\x1b[0m\\x1b[1;36m-out\\x1b[0m``, so
    ``"--out" in result.stdout`` is false even though the flag is plainly on
    screen. That single mechanism -- not line wrapping -- is what causes all
    five pre-existing failures in this repo: two in ``tests/test_cli.py``, one
    in ``tests/load/test_cli_load.py``, and two in ``tests/load/test_prompts.py``
    (where ``Zone 2`` renders as ``Zone \\x1b[1;36m2\\x1b[0m``, no table
    involved). Stripping the escapes restores the literal substring.

    Deliberately does *not* try to undo wrapping. A bordered Rich table keeps
    its ``|`` cell borders through any whitespace normalization, and Rich
    ellipsizes over-long words outright, so no post-processing can recover a
    wrapped cell -- an assertion that needs that is asking the wrong question.

    Needed only for ``--help``. The findings listing prints with
    ``soft_wrap=True``, which disables wrapping altogether, so the rest of this
    module asserts on ``result.output`` directly.
    """
    return _ANSI_RE.sub("", text)


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the setup ``sync`` calls network-free (mirrors ``test_cli.py``)."""
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    """Render ``fixtures`` into a fresh temp data root via the real sync pipeline."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(
        src,
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_TILES,
    )
    return data_root


def _doc(data_root: Path, needle: str) -> Path:
    """The single workout document whose filename contains ``needle``."""
    return next(
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if needle in p.name and p.name != DECLARATION_FILENAME
    )


# --- help / smoke -------------------------------------------------------------


def test_check_help_documents_out_flag() -> None:
    """``check --help`` documents the ``--out`` flag."""
    result = runner.invoke(app, ["check", "--help"])
    assert result.exit_code == 0
    assert "--out" in _plain(result.stdout)


def test_root_help_lists_check_command() -> None:
    """The top-level help lists the new ``check`` command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "check" in result.stdout


# --- clean tree: exit 0, "no findings" line (Req 8.1, 8.7) -------------------


def test_check_clean_tree_exits_zero_with_no_findings_line(tmp_path: Path) -> None:
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})

    result = runner.invoke(app, ["check", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "No findings" in result.output
    # The summary table names the inspected-document count.
    assert "Documents inspected" in result.output


# --- never a tile store, athlete profile, or load pass (design constraint) --


def test_check_never_runs_the_load_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``check`` must never call ``apply_load`` -- a load-only concern."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("check must never run the load pass")

    monkeypatch.setattr(cli, "apply_load", _boom)
    result = runner.invoke(app, ["check", "--out", str(data_root)])
    assert result.exit_code == 0


# --- every finding kind: exit 1, every path and remedy present (Req 8.2-8.7) -


def test_check_reports_every_finding_kind_and_exits_one(tmp_path: Path) -> None:
    data_root = _build_data_root(
        tmp_path,
        {
            "run.fit": builder.run_fit_bytes(),
            "ride.fit": builder.ride_fit_bytes(),
            "strength.fit": builder.strength_fit_bytes(),
        },
    )
    run_doc = _doc(data_root, "run")
    ride_doc = _doc(data_root, "ride")
    strength_doc = _doc(data_root, "strength")

    # Out-of-date: force run.fit's doc_version below the current one.
    run_text = run_doc.read_text(encoding="utf-8")
    assert "doc_version: 5" in run_text
    run_doc.write_text(
        run_text.replace("doc_version: 5", "doc_version: 1"), encoding="utf-8"
    )

    # Damaged region markers: drop the closing "notes" marker on ride.fit.
    ride_text = ride_doc.read_text(encoding="utf-8")
    assert "<!-- fitdocs:end:notes -->" in ride_text
    ride_text = ride_text.replace("<!-- fitdocs:end:notes -->\n", "", 1)
    ride_doc.write_text(ride_text, encoding="utf-8")

    # Unmanaged frontmatter key: add a hand-authored key to strength.fit's doc.
    # Also add a malformed effort tag to the same document, proving the two
    # findings are independent -- neither suppresses the other.
    strength_text = strength_doc.read_text(encoding="utf-8")
    strength_doc.write_text(
        strength_text.replace(
            "title:",
            "custom_tag: hand-added\neffort: race\neffort_time_s: abc\ntitle:",
            1,
        ),
        encoding="utf-8",
    )

    # Missing declaration: delete the workouts/ ownership declaration.
    declaration = data_root / WORKOUTS_DIR / DECLARATION_FILENAME
    assert declaration.is_file()
    declaration.unlink()

    result = runner.invoke(app, ["check", "--out", str(data_root)])

    assert result.exit_code == 1
    output = result.output

    # Every affected path is present.
    assert run_doc.name in output
    assert ride_doc.name in output
    assert strength_doc.name in output
    assert f"{WORKOUTS_DIR}/{DECLARATION_FILENAME}" in output

    # Every remedy is present. Each fragment must be DISTINCTIVE to one remedy:
    # loose fragments alias each other and pin nothing. "fitdocs regen" alone is
    # satisfied by the declaration remedy, and "notes"/"region" by the
    # damaged-regions detail, so blanking those two remedies left the suite
    # green until these assertions were tightened.
    assert "to bring it to the current format" in output  # out-of-date
    assert "region markers by hand" in output  # damaged regions
    assert "move any content worth keeping" in output  # unmanaged keys
    assert "to write the current declaration" in output  # missing declaration
    assert "not in effect" in output  # invalid effort tag (distinctive remedy fragment)

    # Every finding's `detail` -- the "what was observed" half of Req 8.6 --
    # is also present, not just its `remedy`. Deleting the `finding.detail`
    # print line from `_report_audit` left the suite green until these were
    # added; each fragment below is distinctive to its own finding's detail
    # text so a single blanked-out `detail` cannot hide behind another finding's.
    assert "doc_version is 1, below the current" in output  # out-of-date
    assert "begins before region 'notes' is closed" in output  # damaged regions
    assert "unmanaged frontmatter keys: custom_tag" in output  # unmanaged keys
    assert "no AGENTS.md ownership declaration is present" in output  # missing decl
    # Malformed effort tag: distinctive detail fragment is the offending key
    # name, carried on the same document (strength.fit) as the unmanaged key
    # above -- proving the two findings are independent.
    assert "effort_time_s: must be a positive number of seconds" in output


def test_check_reports_invalid_effort_tag_and_exits_one(tmp_path: Path) -> None:
    """A malformed effort tag alone is a distinct finding, per-document
    failure status, naming the offending key and the remedy (Req 3.3, 3.5)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run_doc = _doc(data_root, "run")

    run_text = run_doc.read_text(encoding="utf-8")
    run_doc.write_text(
        run_text.replace("title:", "effort: race\neffort_time_s: abc\ntitle:", 1),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["check", "--out", str(data_root)])

    assert result.exit_code == 1
    output = result.output
    assert run_doc.name in output
    assert "effort_time_s: must be a positive number of seconds" in output
    assert "not in effect" in output


# --- unresolvable data root: exit 2, nothing scanned (Req 8.7) ---------------


def test_check_unresolvable_data_root_exits_two_and_scans_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    cwd = tmp_path / "cwd"  # a directory with no .fitdocs/data-root pointer
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    def _boom(_data_root: Path) -> None:
        raise AssertionError(
            "audit() must never run when the data root fails to resolve"
        )

    monkeypatch.setattr(cli, "audit", _boom)

    result = runner.invoke(app, ["check"])

    assert result.exit_code == 2
    # The instructive message lists all three configuration options (Req 2.2).
    assert "--out" in result.output
    assert "FITDOCS_DATA" in result.output
    assert ".fitdocs/data-root" in result.output
