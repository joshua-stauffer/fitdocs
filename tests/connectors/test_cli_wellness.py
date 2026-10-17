"""Wellness pull CLI observations and a renderer-only count supplement."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner, Result

import fitdocs.cli as cli
from fitdocs import layout
from fitdocs.connectors import delivery, registry
from fitdocs.connectors.errors import AuthFailure, AuthFailureKind
from fitdocs.connectors.ledger import (
    Ledger,
    WellnessLedger,
    WellnessPending,
    save_ledger,
)
from fitdocs.connectors.protocol import (
    Capability,
    Listing,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.pull import (
    Delivered,
    InstancePullReport,
    PullNote,
    PullReport,
    WellnessDelivered,
    WellnessPullReport,
)
from tests.connectors.conftest import ScriptedWellnessPuller

_LABELS = (
    "Days listed",
    "Days unchanged",
    "Delivered",
    "Would deliver",
    "Already held",
    "Failed",
    "Notices",
    "Error",
)
_ZERO = tuple(zip(_LABELS, ("0",) * 8, strict=True))
_BOTH = frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})


def _day(text: str) -> WellnessDay:
    return WellnessDay(date.fromisoformat(text), "revision", object())


def _listing(*texts: str) -> WellnessListing:
    return WellnessListing(
        date(2020, 1, 1), date(2026, 1, 1), tuple(_day(t) for t in texts)
    )


def _package(data: bytes = b'{"source": "new"}') -> WellnessPackage:
    return WellnessPackage(data, ".json", "synthetic", frozenset({"retained"}))


def _seed(root: Path, wellness: WellnessLedger, name: str = "src") -> None:
    save_ledger(root, name, Ledger("scripted-wellness-puller", None, (), wellness))


def _register(
    root: Path,
    puller: ScriptedWellnessPuller,
    *,
    enabled: bool = True,
    names: tuple[str, ...] = ("src",),
) -> None:
    registry.register(puller)
    (root / "fitdocs.toml").write_text(
        "\n".join(
            f'[connectors.{name}]\nconnector = "scripted-wellness-puller"\n'
            f"wellness = {str(enabled).lower()}\n"
            for name in names
        )
    )


def _invoke(root: Path, *args: str) -> Result:
    return CliRunner().invoke(cli.app, ["pull", "--out", str(root), *args])


def _titles_unwrapped(output: str) -> str:
    return re.sub(
        r"fitdocs pull:.*?(?=^[┏┌])",
        lambda match: " ".join(match[0].split()) + "\n",
        output,
        flags=re.MULTILINE | re.DOTALL,
    )


def _wellness(
    output: str, name: str = "src"
) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    lines = _titles_unwrapped(output).splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip() == f"fitdocs pull: {name} wellness"
        ),
        len(lines),
    )
    block = lines[start + 1 :]
    end = next(
        (i for i, line in enumerate(block) if line.strip().startswith("fitdocs pull:")),
        len(block),
    )
    block = block[:end]
    rows = tuple(
        (m[1].strip(), m[2].strip())
        for line in block
        if (m := re.fullmatch(r"│([^│]*)│([^│]*)│", line))
    )
    bottom = next(
        (i for i, line in enumerate(block) if line.startswith("└")), len(block)
    )
    return rows, tuple(line for line in block[bottom + 1 :] if line)


def _counts(*values: int) -> tuple[tuple[str, str], ...]:
    return tuple(zip(_LABELS, map(str, values), strict=True))


def test_registered_zero(tmp_path: Path) -> None:
    puller = ScriptedWellnessPuller()
    puller.wellness_listing_script = [_listing()]
    _register(tmp_path, puller)
    result = _invoke(tmp_path)
    assert (
        result.exit_code,
        _wellness(result.output),
        re.findall(r"┃\s*(\w+)\s*┃\s*(\w+)\s*┃", result.output),
    ) == (0, (_ZERO, ()), [("Result", "Count"), ("Result", "Count")])


def test_registered_mixed(tmp_path: Path) -> None:
    puller = ScriptedWellnessPuller()
    puller.wellness_listing_script = [
        _listing(
            "2021-02-01",
            "2021-02-02",
            "2022-03-01",
            "2022-03-02",
            "2022-03-04",
            "2023-04-05",
            "2024-05-06",
        )
    ]
    held = b'{"source": "archived"}'
    sha = hashlib.sha256(held).hexdigest()
    archive = layout.wellness_archive_path(tmp_path, "synthetic", sha, ".json")
    archive.parent.mkdir(parents=True)
    archive.write_bytes(held)
    _seed(
        tmp_path,
        WellnessLedger(origins=("lost", "retained")).with_days(
            ((date(2021, 2, 1), "revision"), (date(2021, 2, 2), "revision")), "a" * 64
        ),
    )
    puller.wellness_package_script = [
        _package(),
        _package(held),
        RuntimeError("[bold]failure[/bold] 314"),
    ]
    _register(tmp_path, puller)
    result = _invoke(tmp_path)
    assert (result.exit_code, _wellness(result.output)) == (
        1,
        (
            _counts(7, 2, 1, 0, 1, 1, 1, 0),
            (
                "Delivered:",
                "  src/wellness-2022-03-01_2022-03-04.json "
                "(2022-03-01..2022-03-04, 3 days)",
                "Already held:",
                "  2023-04-05..2023-04-05",
                "Failed:",
                "  2024-05-06..2024-05-06",
                "    RuntimeError: [bold]failure[/bold] 314",
                "Notices:",
                "  lost",
                "    the connector no longer attributes any wellness field to lost; "
                "if lost data stopped reaching the service, import lost's own "
                "export instead (see the wellness guide)",
            ),
        ),
    )


def test_registered_dry_dates(tmp_path: Path) -> None:
    puller = ScriptedWellnessPuller()
    puller.wellness_listing_script = [
        _listing("2025-06-09", "2023-02-02", "2025-06-01")
    ]
    _register(tmp_path, puller)
    result = _invoke(tmp_path, "--dry-run")
    assert (
        result.exit_code,
        "Dry run — nothing fetched or written." in result.output,
        _wellness(result.output),
    ) == (
        0,
        True,
        (
            _counts(3, 0, 0, 3, 0, 0, 0, 0),
            ("Would deliver:", "  2023-02-02", "  2025-06-01", "  2025-06-09"),
        ),
    )


def test_registered_notices_and_unchanged_succeed(tmp_path: Path) -> None:
    puller = ScriptedWellnessPuller()
    puller.wellness_listing_script = [
        _listing("2021-01-01", "2021-01-02", "2022-01-03")
    ]
    puller.wellness_package_script = [_package()]
    _seed(
        tmp_path,
        WellnessLedger(origins=("lost",)).with_days(
            ((date(2021, 1, 1), "revision"), (date(2021, 1, 2), "revision")), "b" * 64
        ),
    )
    _register(tmp_path, puller)
    result = _invoke(tmp_path)
    assert (result.exit_code, _wellness(result.output)[0]) == (
        0,
        _counts(3, 2, 1, 0, 0, 0, 1, 0),
    )


def test_registered_held_succeeds(tmp_path: Path) -> None:
    puller = ScriptedWellnessPuller()
    puller.wellness_listing_script = [_listing("2025-01-01")]
    package = _package()
    archive = layout.wellness_archive_path(
        tmp_path, "synthetic", hashlib.sha256(package.data).hexdigest(), ".json"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(package.data)
    puller.wellness_package_script = [package]
    _register(tmp_path, puller)
    result = _invoke(tmp_path)
    assert (result.exit_code, _wellness(result.output)) == (
        0,
        (
            _counts(1, 0, 0, 0, 1, 0, 0, 0),
            ("Already held:", "  2025-01-01..2025-01-01"),
        ),
    )


def test_registered_error(tmp_path: Path) -> None:
    puller = ScriptedWellnessPuller()
    puller.wellness_listing_script = [
        AuthFailure(AuthFailureKind.REJECTED, "[bold]expired[/bold]")
    ]
    _register(tmp_path, puller)
    result = _invoke(tmp_path)
    assert (result.exit_code, _wellness(result.output)) == (
        1,
        (
            _counts(0, 0, 0, 0, 0, 0, 0, 1),
            (
                "Error:",
                "  AuthFailure: [bold]expired[/bold] Check the credentials and run "
                "`fitdocs connect src` again.",
            ),
        ),
    )


@pytest.mark.parametrize("mode", ["disabled", "activity-only"])
def test_registered_absent(tmp_path: Path, mode: str) -> None:
    puller = ScriptedWellnessPuller(
        capabilities=_BOTH
        if mode == "disabled"
        else frozenset({Capability.PULL_ACTIVITIES})
    )
    puller.listing_script = [Listing(())]
    _register(tmp_path, puller, enabled=False)
    result = _invoke(tmp_path)
    assert (
        result.exit_code,
        re.findall(r"fitdocs pull: [a-z]+ wellness", _titles_unwrapped(result.output)),
        "fitdocs pull: src" in result.output,
    ) == (0, [], True)


def test_registered_sweep_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    puller = ScriptedWellnessPuller()
    puller.wellness_listing_script = [_listing()]
    pending = []
    for name, data in (("removed", b'{"removed":1}'), ("deferred", b'{"deferred":2}')):
        sha = hashlib.sha256(data).hexdigest()
        inbox_file = tmp_path / "inbox" / "src" / f"{name}.json"
        inbox_file.parent.mkdir(parents=True, exist_ok=True)
        inbox_file.write_bytes(data)
        archive = layout.wellness_archive_path(tmp_path, "synthetic", sha, ".json")
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(data)
        pending.append(WellnessPending(f"src/{name}.json", sha, "synthetic", ".json"))
    _seed(
        tmp_path, WellnessLedger(pending=tuple(sorted(pending, key=lambda p: p.path)))
    )
    original = delivery._remove

    def remove(path: Path) -> None:
        if path.name == "deferred.json":
            raise OSError("[bold]busy[/bold]")
        original(path)

    monkeypatch.setattr(delivery, "_remove", remove)
    _register(tmp_path, puller)
    result = _invoke(tmp_path)
    before, _, after = result.output.partition("fitdocs pull: src wellness")
    assert (
        result.exit_code,
        "│ Deferred     │     1 │" in before,
        "│ Removed      │     1 │" in before,
        "Deferred:\n  src/deferred.json\n    OSError: [bold]busy[/bold]" in before,
        "Removed:\n  src/removed.json" in before,
        _wellness(result.output),
        "Deferred" in after,
        "Removed" in after,
    ) == (0, True, True, True, True, (_ZERO, ()), False, False)


def test_registered_instances(tmp_path: Path) -> None:
    puller = ScriptedWellnessPuller(capabilities=_BOTH)
    puller.listing_script = [Listing(()), Listing(())]
    puller.wellness_listing_script = [
        _listing("2025-01-02", "2025-01-01"),
        _listing("2024-02-03"),
    ]
    _register(tmp_path, puller, names=("alpha", "zeta"))
    result = _invoke(tmp_path, "--dry-run")
    titles = re.findall(
        r"fitdocs pull: (alpha|zeta)( wellness)?", _titles_unwrapped(result.output)
    )
    assert (
        result.exit_code,
        titles,
        _wellness(result.output, "alpha"),
        _wellness(result.output, "zeta"),
    ) == (
        0,
        [("alpha", ""), ("alpha", " wellness"), ("zeta", ""), ("zeta", " wellness")],
        (
            _counts(2, 0, 0, 2, 0, 0, 0, 0),
            ("Would deliver:", "  2025-01-01", "  2025-01-02"),
        ),
        (_counts(1, 0, 0, 1, 0, 0, 0, 0), ("Would deliver:", "  2024-02-03")),
    )


def test_renderer_distinct_counts_and_literal_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Renderer-only supplement using a typed, non-dry report carrier."""
    stream = io.StringIO()
    monkeypatch.setattr(
        cli,
        "Console",
        lambda: Console(
            file=stream,
            width=79,
            force_terminal=True,
            color_system="standard",
            no_color=False,
        ),
    )
    long = "[bold]literal[/bold] " + "long-text-" * 19 + " 123"
    delivered = (
        WellnessDelivered(
            "2021-01-01..2021-01-03",
            3,
            "src/[bold]first[/bold]-long-path-long-path-long-path-long-path-long-path-long-path-long-path-long-path-long-path-long-path-long-path-long-path-.json",
        ),
        WellnessDelivered("2022-04-01..2022-04-09", 9, "src/second.json"),
        WellnessDelivered("2022-05-05..2022-05-05", 1, "src/third.json"),
    )
    held = (
        "2023-01-01..2023-01-02",
        "2024-02-03..2024-02-06",
        "2025-03-01..2025-03-04",
    )
    failed = tuple(
        PullNote(f"{2026 + i}-01-01..{2026 + i}-01-01", f"{long} reason-{i}")
        for i in range(4)
    )
    notice_subjects = (
        "notice-" + "long-slug-" * 20,
        "[bold]notice[/bold]",
        "notice-2",
        "notice-3",
        "notice-4",
    )
    notices = tuple(
        PullNote(subject, f"{long} advice-{i}")
        for i, subject in enumerate(notice_subjects)
    )
    wellness = WellnessPullReport(
        34,
        7,
        delivered,
        (),
        held,
        failed,
        notices,
        PullNote("src", long + " reconnect"),
    )
    instance = InstancePullReport(
        "src",
        "synthetic",
        23,
        (Delivered("activity", "activity.fit"),),
        (),
        (),
        (),
        (PullNote("deferred", "wait"),),
        (),
        ("old.fit",),
        PullNote("src", "activity error"),
        wellness,
    )
    cli._report_pull(
        PullReport(
            "inbox",
            False,
            (
                instance,
                replace(
                    instance,
                    name="tail",
                    listed=0,
                    delivered=(),
                    deferred=(),
                    removed=(),
                    error=None,
                    wellness=WellnessPullReport(0, 0, (), (), (), (), (), None),
                ),
            ),
        )
    )
    raw = stream.getvalue()
    plain = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    section = plain.partition("fitdocs pull: src wellness")[2].partition(
        "fitdocs pull: tail"
    )[0]
    expected_details = (
        "Delivered:",
        "  src/[bold]first[/bold]-long-path-long-path-long-path-long-path-"
        "long-path-long-path-long-path-long-path-long-path-long-path-long-path-"
        "long-path-.json (2021-01-01..2021-01-03, 3 days)",
        "  src/second.json (2022-04-01..2022-04-09, 9 days)",
        "  src/third.json (2022-05-05..2022-05-05, 1 day)",
        "Already held:",
        *(f"  {span}" for span in held),
        "Failed:",
        *(
            line
            for i in range(4)
            for line in (
                f"  {2026 + i}-01-01..{2026 + i}-01-01",
                f"    {long} reason-{i}",
            )
        ),
        "Notices:",
        *(
            line
            for i, subject in enumerate(notice_subjects)
            for line in (f"  {subject}", f"    {long} advice-{i}")
        ),
        "Error:",
        f"  {long} reconnect",
    )
    assert (
        _wellness(plain),
        _wellness(plain, "tail"),
        "\n".join(expected_details) in raw,
        section.find("Days listed") < section.find("Error"),
        plain.find("activity error") < plain.find("fitdocs pull: src wellness"),
    ) == (
        (_counts(34, 7, 3, 0, 3, 4, 5, 1), expected_details),
        (_ZERO, ()),
        True,
        True,
        True,
    )


@pytest.mark.parametrize("width", [79, 7])
def test_renderer_dry_date_literal_output(
    monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    stream = io.StringIO()
    console = Console(
        file=stream,
        width=width,
        height=25,
        force_terminal=True,
        color_system="standard",
        no_color=False,
    )
    monkeypatch.setattr(cli, "Console", lambda: console)
    wellness = WellnessPullReport(1, 0, (), ("2025-01-01",), (), (), (), None)
    instance = InstancePullReport(
        "src", "synthetic", 0, (), (), (), (), (), (), (), None, wellness
    )
    cli._report_pull(PullReport("inbox", True, (instance,)))
    raw_dates = stream.getvalue().partition("Would deliver:\n")[2]
    assert (console.width, raw_dates) == (width, "  2025-01-01\n")


@pytest.mark.parametrize("width", [79, 7])
def test_renderer_held_span_literal_output(
    monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    stream = io.StringIO()
    console = Console(
        file=stream,
        width=width,
        height=25,
        force_terminal=True,
        color_system="standard",
        no_color=False,
    )
    monkeypatch.setattr(cli, "Console", lambda: console)
    wellness = WellnessPullReport(
        1, 0, (), (), ("2025-01-01..2025-01-01",), (), (), None
    )
    instance = InstancePullReport(
        "src", "synthetic", 0, (), (), (), (), (), (), (), None, wellness
    )
    cli._report_pull(PullReport("inbox", False, (instance,)))
    raw_spans = stream.getvalue().partition("Already held:\n")[2]
    assert (console.width, raw_spans) == (width, "  2025-01-01..2025-01-01\n")
