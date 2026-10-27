"""A hand-edited page whose frontmatter PyYAML cannot construct is not a document.

``date: 2026-02-30`` is valid YAML syntax but raises ``ValueError`` out of
``yaml.safe_load``. Under wiki-contract Req 1.2 the page is "not a fitdocs
document in every command" and the run continues: ``check``, ``regen``,
``load`` and ``sync`` must each exit without a traceback, and the neighbouring
real page is still counted by ``check``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.layout import WORKOUTS_DIR
from tests.fixtures import builder
from tests.support import tiles as tile_factory

runner = CliRunner()

_BAD = "---\ntype: workout\ndate: 2026-02-30\n---\nhand-edited\n"


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fitdocs.tiles._default_fetch", tile_factory.fetch_stub())


def _root_with_bad_page(tmp_path: Path) -> Path:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "run.fit").write_bytes(builder.run_fit_bytes())
    root = tmp_path / "root"
    root.mkdir()
    built = runner.invoke(app, ["sync", str(inbox), "--out", str(root), "--no-prompt"])
    assert built.exit_code == 0, built.output
    (root / WORKOUTS_DIR / "bad.md").write_text(_BAD, encoding="utf-8")
    return root


@pytest.mark.parametrize("command", ["check", "regen"])
def test_out_commands_do_not_raise_on_an_unconstructible_page(
    tmp_path: Path, command: str
) -> None:
    root = _root_with_bad_page(tmp_path)

    result = runner.invoke(app, [command, "--out", str(root)])

    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 0, result.output
    if command == "check":
        assert re.search(r"Documents inspected\D*1\b", result.output)
    if command == "regen":
        assert (root / WORKOUTS_DIR / "bad.md").read_text(encoding="utf-8") == _BAD


def test_load_does_not_raise_on_an_unconstructible_page(tmp_path: Path) -> None:
    root = _root_with_bad_page(tmp_path)

    result = runner.invoke(app, ["load", "--out", str(root), "--no-prompt"])

    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 0, result.output


def test_sync_does_not_raise_on_an_unconstructible_page(tmp_path: Path) -> None:
    root = _root_with_bad_page(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    result = runner.invoke(app, ["sync", str(empty), "--out", str(root), "--no-prompt"])

    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 0, result.output
