"""CLI wiring of the ``[identity]`` precedence setting and hold-record errors
(activity-identity task 5.2, Req 2.7).

Driven through :class:`typer.testing.CliRunner` over temporary data roots. The
``connectors`` spec is not on this branch, so the ``pull`` scenarios are out of
scope here (connectors does that wiring when it lands). The explicit-source
``sync`` loads the hold record itself, so its hold-record scenario runs the real
engine over a damaged ``.fitdocs/held.toml``, and so does the inbox drain,
which loads the record before any write.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from fitdocs import cli as cli_module
from fitdocs.cli import app
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.identity.roles import DEFAULT_PRECEDENCE, Precedence
from fitdocs.identity.settings import load_identity_settings
from fitdocs.layout import WORKOUTS_DIR, archive_path, held_path, source_ref
from tests.fixtures import identity as fx

runner = CliRunner()

_ORIGINAL_FIRST = 'precedence = ["original", "phone_copy", "unknown"]'
_MALFORMED = 'precedence = "original"'


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _settings(data_root: Path, precedence_line: str | None) -> None:
    data_root.mkdir(parents=True, exist_ok=True)
    text = "[inbox]\nsettle_seconds = 0\n"
    if precedence_line is not None:
        text += f"\n[identity]\n{precedence_line}\n"
    (data_root / "fitdocs.toml").write_text(text, encoding="utf-8")


def _stage(directory: Path) -> Path:
    """A HealthFit copy and a Stryd file of one activity (a phone copy and an
    original, so the two precedence orders pick different bases)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "copy.fit").write_bytes(fx.healthfit_copy().data)
    (directory / "stryd.fit").write_bytes(fx.stryd_file().data)
    return directory


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
        for p in sorted(root.rglob("*"))
    }


def _base_kind(data_root: Path) -> object:
    pages = [
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.name != DECLARATION_FILENAME
    ]
    assert len(pages) == 1, [p.name for p in pages]
    block = pages[0].read_text(encoding="utf-8").split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert len(parsed["sources"]) == 2, parsed["sources"]
    return parsed["source_kind"]


def _staged_page(tmp_path: Path) -> Path:
    """A data root whose one page lists a HealthFit copy and a Stryd file.

    The page is synced from the copy alone through the CLI; the Stryd file is
    then archived and listed by hand (the staged shape ``regen`` rebuilds from).
    """
    data_root = tmp_path / "data"
    _settings(data_root, None)
    copy, stryd = fx.healthfit_copy(), fx.stryd_file()
    source = tmp_path / "src"
    source.mkdir()
    (source / "copy.fit").write_bytes(copy.data)
    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0, first.output
    archived = archive_path(data_root, hashlib.sha256(stryd.data).hexdigest())
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_bytes(stryd.data)
    (page,) = [
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.name != DECLARATION_FILENAME
    ]
    refs = [source_ref(hashlib.sha256(s.data).hexdigest()) for s in (copy, stryd)]
    text = page.read_text(encoding="utf-8")
    edited, count = re.subn(
        r"^sources:\n(?:- .*\n)+",
        "sources:\n" + "".join(f"- {r}\n" for r in refs),
        text,
        flags=re.MULTILINE,
    )
    assert count == 1
    page.write_text(edited, encoding="utf-8")
    return data_root


def _spy(monkeypatch: pytest.MonkeyPatch, name: str) -> list[dict[str, Any]]:
    """Wrap ``fitdocs.cli.<name>``: record its keyword arguments, call through."""
    real: Callable[..., Any] = getattr(cli_module, name)
    calls: list[dict[str, Any]] = []

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(cli_module, name, wrapper)
    return calls


def _damage_holds(data_root: Path) -> Path:
    path = held_path(data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("this is [not valid toml\n", encoding="utf-8")
    return path


# --- a malformed table exits 2 and writes nothing -------------------------------


@pytest.mark.parametrize("path", ["explicit", "drain", "regen"])
def test_malformed_identity_table_exits_2_and_writes_nothing(
    tmp_path: Path, path: str
) -> None:
    data_root = tmp_path / "data"
    _settings(data_root, _MALFORMED)
    if path == "drain":
        _stage(data_root / "inbox")
    args = {
        "explicit": ["sync", str(_stage(tmp_path / "src"))],
        "drain": ["sync"],
        "regen": ["regen"],
    }[path]
    before = _snapshot(data_root)

    result = runner.invoke(app, [*args, "--out", str(data_root)])

    assert result.exit_code == 2, result.output
    assert "[identity]" in result.output
    assert str(data_root / "fitdocs.toml") in result.output
    assert "precedence" in result.output
    assert _snapshot(data_root) == before


def test_malformed_table_is_rejected_before_the_engine_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    _settings(data_root, _MALFORMED)
    calls = [_spy(monkeypatch, n) for n in ("sync", "drain", "regen")]
    source = _stage(tmp_path / "src")

    runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    runner.invoke(app, ["sync", "--out", str(data_root)])
    runner.invoke(app, ["regen", "--out", str(data_root)])

    assert calls == [[], [], []]


# --- a configured precedence changes the base end to end ---------------------------


def test_default_precedence_bases_the_regenerated_page_on_the_phone_copy(
    tmp_path: Path,
) -> None:
    data_root = _staged_page(tmp_path)

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert _base_kind(data_root) == "phone_copy"


def test_configured_precedence_makes_the_stryd_file_the_regenerated_base(
    tmp_path: Path,
) -> None:
    data_root = _staged_page(tmp_path)
    _settings(data_root, _ORIGINAL_FIRST)

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert _base_kind(data_root) == "original"


# --- the engines see the configured precedence ----------------------------------------


def _configured() -> Precedence:
    document = {"identity": {"precedence": ["original", "phone_copy", "unknown"]}}
    return load_identity_settings(document, Path("fitdocs.toml")).precedence


@pytest.mark.parametrize(
    ("name", "args"),
    [("sync", ["sync", "SRC"]), ("drain", ["sync"]), ("regen", ["regen"])],
)
def test_engine_receives_the_configured_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    args: list[str],
) -> None:
    data_root = tmp_path / "data"
    _settings(data_root, _ORIGINAL_FIRST)
    source = _stage(tmp_path / "src")
    calls = _spy(monkeypatch, name)
    args = [str(source) if a == "SRC" else a for a in args]

    result = runner.invoke(app, [*args, "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert calls[0]["precedence"] == _configured()
    assert calls[0]["precedence"] != DEFAULT_PRECEDENCE


# --- a damaged hold record ------------------------------------------------------------


@pytest.mark.parametrize("path", ["explicit", "drain"])
def test_damaged_hold_record_exits_2_naming_the_file_and_regen(
    tmp_path: Path, path: str
) -> None:
    data_root = tmp_path / "data"
    _settings(data_root, None)
    # The drain's inbox is staged in place, so the CLI has no empty directory
    # to create and the whole data root is byte-compared on both paths.
    source = _stage(tmp_path / "src" if path == "explicit" else data_root / "inbox")
    held = _damage_holds(data_root)
    args = ["sync", str(source)] if path == "explicit" else ["sync"]
    before = _snapshot(data_root)
    if path == "drain":  # the precondition: candidates waited in the inbox
        assert any(name.endswith(".fit") for name in before)

    result = runner.invoke(app, [*args, "--out", str(data_root)])

    assert result.exit_code == 2, result.output
    assert _snapshot(data_root) == before
    assert str(held) in result.output.replace("\n", "")
    assert "fitdocs regen" in result.output


_MOVE_INBOX = (
    '[inbox]\nsettle_seconds = 0\ndisposition = "move"\nprocessed_dir = "done"\n'
)


@pytest.mark.parametrize("fault", ["identity_table", "damaged_holds"])
@pytest.mark.parametrize("disposition", ["default", "move"])
def test_drain_config_fault_creates_no_inbox_or_processed_directory(
    tmp_path: Path, fault: str, disposition: str
) -> None:
    """The drain has no inbox yet, so the inbox pre-flight would create one."""
    data_root = tmp_path / "data"
    _settings(data_root, _MALFORMED if fault == "identity_table" else None)
    if disposition == "move":
        text = (data_root / "fitdocs.toml").read_text(encoding="utf-8")
        text = text.replace("[inbox]\nsettle_seconds = 0\n", _MOVE_INBOX)
        assert 'processed_dir = "done"' in text
        (data_root / "fitdocs.toml").write_text(text, encoding="utf-8")
    if fault == "damaged_holds":
        _damage_holds(data_root)
    before = _snapshot(data_root)
    assert not (data_root / "inbox").exists()  # the precondition

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2, result.output
    assert _snapshot(data_root) == before
    assert not (data_root / "inbox").exists()
    assert not (data_root / "done").exists()


def test_regen_succeeds_after_the_damaged_hold_record_failed_sync(
    tmp_path: Path,
) -> None:
    data_root = _staged_page(tmp_path)
    source = tmp_path / "src"
    _damage_holds(data_root)
    failed = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert failed.exit_code == 2

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0, result.output
    assert _base_kind(data_root) == "phone_copy"
