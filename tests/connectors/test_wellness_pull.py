"""Wellness listing and orchestration acceptance observations."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_type_hints

import pytest

from fitdocs import layout
from fitdocs.connectors import pull as pull_mod
from fitdocs.connectors.credentials import resolve_credentials
from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    next_step,
)
from fitdocs.connectors.ledger import (
    Ledger,
    LedgerEntry,
    Outcome,
    WellnessLedger,
    WellnessPending,
    load_ledger,
    save_ledger,
)
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    Listing,
    RemoteActivity,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
)
from fitdocs.connectors.pull import (
    InstancePullReport,
    PullNote,
    PullOptions,
    PullReport,
    WellnessDelivered,
    WellnessPullReport,
    run_pull,
)
from fitdocs.connectors.secrets import REDACTED, Redactor
from fitdocs.connectors.settings import ConnectorInstance
from tests.connectors.conftest import FakeTransport, ScriptedWellnessPuller
from tests.fixtures.builder import FIT_TIMESTAMP_BASE

_NOW = datetime(1989, 12, 31, tzinfo=UTC) + timedelta(seconds=FIT_TIMESTAMP_BASE)
_D = _NOW.date()
_SHA = "a" * 64
_KEY = "ik-synthetic-7Q2x9"
_BOTH = frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})


def _day(offset: int, revision: Any = "zeta") -> WellnessDay:
    return WellnessDay(_D + timedelta(days=offset), revision, object())


def _listing(*days: Any, start: int = -20, end: int = 20) -> WellnessListing:
    return WellnessListing(_D + timedelta(days=start), _D + timedelta(days=end), days)


def _instance(
    connector: ScriptedWellnessPuller,
    *,
    enabled: bool = True,
    name: str = "src",
    lookback: int = 7,
    settings: object = None,
) -> ConnectorInstance:
    return ConnectorInstance(name, connector, lookback, settings, enabled)


def _run(
    root: Path,
    connector: ScriptedWellnessPuller,
    *,
    enabled: bool = True,
    dry: bool = False,
    since: datetime | None = None,
    lookback: int = 7,
    instances: list[ConnectorInstance] | None = None,
    redactor: Redactor | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> PullReport:
    return run_pull(
        root,
        instances or [_instance(connector, enabled=enabled, lookback=lookback)],
        inbox=root / "inbox",
        store=None,
        transport=FakeTransport([]),
        options=PullOptions(since, dry),
        environ={},
        now=now if now is not None else lambda: _NOW,
        sleep=sleep if sleep is not None else lambda _: None,
        redactor=redactor or Redactor(),
    )


def _seed(
    root: Path, wellness: WellnessLedger | None, *, activity: bool = False
) -> Path:
    ledger = Ledger(connector_id="scripted-wellness-puller", watermark=None, entries=())
    if wellness is not None:
        ledger = ledger.with_wellness(wellness)
    if activity:
        ledger = ledger.with_entry(
            LedgerEntry("legacy", Outcome.SKIPPED, revision="old", detail="manual")
        )
    save_ledger(root, "src", ledger)
    return layout.connector_ledger_path(root, "src")


def _snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


@pytest.mark.parametrize(
    "caps",
    [
        frozenset({Capability.PULL_PLANS}),
        frozenset({Capability.PULL_WELLNESS}),
        frozenset({Capability.PULL_ACTIVITIES}),
        _BOTH,
        frozenset({Capability.PULL_PLANS, Capability.PULL_WELLNESS}),
        frozenset({Capability.PULL_PLANS, Capability.PULL_ACTIVITIES}),
        frozenset({Capability.PULL_PLANS, *_BOTH}),
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_runnable_matrix(
    tmp_path: Path, caps: frozenset[Capability], enabled: bool
) -> None:
    connector = ScriptedWellnessPuller(capabilities=caps)
    connector.listing_script = [Listing(())]
    connector.wellness_listing_script = [_listing()]
    result = _run(tmp_path, connector, enabled=enabled, dry=True).instances[0]
    expected_calls = (
        ["list_activities"] if Capability.PULL_ACTIVITIES in caps else []
    ) + (["list_wellness"] if enabled and Capability.PULL_WELLNESS in caps else [])
    assert connector.calls == expected_calls
    assert (result.wellness is not None) is (
        enabled and Capability.PULL_WELLNESS in caps
    )
    expected_detail = (
        None
        if expected_calls
        else (
            "pulls only wellness, which is not enabled for this instance; "
            "set wellness = true in [connectors.src]"
            if Capability.PULL_WELLNESS in caps
            else "does not pull activities or wellness"
        )
    )
    assert result.error == (
        None if expected_detail is None else PullNote("src", expected_detail)
    )


def test_disabled_activity_only_bytes(tmp_path: Path) -> None:
    path = _seed(tmp_path, None, activity=True)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    connector.listing_script = [Listing(())]
    connector.wellness_listing_script = [_listing()]
    result = _run(tmp_path, connector, enabled=False).instances[0]
    assert (result.wellness, connector.wellness_list_calls, _snapshot(path)) == (
        None,
        [],
        before,
    )


@pytest.mark.parametrize("site", ["listing", "fetch"])
@pytest.mark.parametrize(
    "failure",
    [
        ConnectorError("ordinary"),
        ValueError("native"),
        AuthFailure(AuthFailureKind.REJECTED, "key rejected"),
    ],
)
def test_activity_failure_order(tmp_path: Path, site: str, failure: Exception) -> None:
    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    activity = RemoteActivity("activity", True, start=_NOW, revision="r")
    connector.listing_script = [failure if site == "listing" else Listing((activity,))]
    connector.fetch_script = [failure]
    connector.wellness_listing_script = [_listing()]
    result = _run(tmp_path, connector).instances[0]
    prefix = ["list_activities"] + (["fetch_activity"] if site == "fetch" else [])
    expected = prefix + ([] if isinstance(failure, AuthFailure) else ["list_wellness"])
    assert connector.calls == expected
    assert (result.wellness is None) is isinstance(failure, AuthFailure)
    assert (result.error is not None, len(result.failed)) == (
        (False, 1) if site == "fetch" and isinstance(failure, ValueError) else (True, 0)
    )


def test_one_session_and_activity_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    connector.listing_script = [Listing(())]
    connector.wellness_listing_script = [_listing()]
    sessions: list[ConnectorSession] = []
    constructors: list[dict[str, Any]] = []
    real_session = ConnectorSession

    def construct(**kwargs: Any) -> ConnectorSession:
        constructors.append(kwargs)
        return real_session(**kwargs)

    def activity(session: ConnectorSession, since: datetime | None) -> Listing:
        sessions.append(session)
        return ScriptedWellnessPuller.list_activities(connector, session, since)

    def wellness(session: ConnectorSession, oldest: date | None) -> WellnessListing:
        sessions.append(session)
        return ScriptedWellnessPuller.list_wellness(connector, session, oldest)

    monkeypatch.setattr(pull_mod, "ConnectorSession", construct)
    monkeypatch.setattr(connector, "list_activities", activity)
    monkeypatch.setattr(connector, "list_wellness", wellness)
    credentials = resolve_credentials("src", connector, None, {}, Redactor())
    monkeypatch.setattr(pull_mod, "resolve_credentials", lambda *args: credentials)

    def now() -> datetime:
        return _NOW

    def sleep(seconds: float) -> None:
        pass

    settings = {"distinct": object()}
    instance = _instance(connector, settings=settings)
    result = _run(
        tmp_path, connector, dry=True, instances=[instance], now=now, sleep=sleep
    ).instances[0]
    assert (len(constructors), len(sessions)) == (1, 2)
    assert (
        sessions[0] is sessions[1],
        sessions[0].settings is settings,
        sessions[0].data_root,
        sessions[0].now(),
        sessions[0].instance,
        sessions[0].http.mode.value,
        sessions[0].credentials is credentials,
        sessions[0].now is now,
        sessions[0].sleep is sleep,
    ) == (True, True, tmp_path, _NOW, "src", "data", True, True, True)
    assert (
        result.listed,
        result.delivered,
        result.held,
        result.failed,
        result.error,
    ) == (0, (), (), (), None)


@pytest.mark.parametrize(
    "through,since,lookback,expected",
    [
        (None, None, 7, None),
        (_D, None, 7, _D - timedelta(days=7)),
        (_D, None, 30, _D - timedelta(days=30)),
        (
            _D,
            datetime.combine(_D, datetime.min.time(), timezone(timedelta(hours=5))),
            7,
            _D - timedelta(days=1),
        ),
        (
            None,
            datetime.combine(_D, datetime.min.time(), timezone(timedelta(hours=-9))),
            30,
            _D,
        ),
    ],
)
def test_oldest_precedence(
    tmp_path: Path,
    through: date | None,
    since: datetime | None,
    lookback: int,
    expected: date | None,
) -> None:
    _seed(tmp_path, WellnessLedger(through=through))
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing()]
    _run(tmp_path, connector, dry=True, since=since, lookback=lookback)
    assert connector.wellness_list_calls == [expected]


@pytest.mark.parametrize(
    "exc",
    [
        AuthFailure(AuthFailureKind.REJECTED, _KEY),
        ConnectorError(_KEY),
        ValueError(_KEY),
    ],
)
def test_listing_errors_redacted_and_continue(tmp_path: Path, exc: Exception) -> None:
    first = ScriptedWellnessPuller()
    first.wellness_listing_script = [exc]
    second = ScriptedWellnessPuller()
    second.wellness_listing_script = [_listing()]
    redactor = Redactor()
    redactor.add(_KEY)
    report = _run(
        tmp_path,
        first,
        instances=[_instance(first), _instance(second, name="next")],
        redactor=redactor,
    )
    extra = (
        " " + next_step(exc.kind, name="src", retry_after_s=None)
        if isinstance(exc, AuthFailure)
        else ""
    )
    assert report.instances[0].wellness == WellnessPullReport(
        0,
        0,
        (),
        (),
        (),
        (),
        (),
        PullNote("src", f"{type(exc).__name__}: {REDACTED}{extra}"),
    )
    assert (report.failed, second.calls, [r.name for r in report.instances]) == (
        True,
        ["list_wellness"],
        ["src", "next"],
    )


@pytest.mark.parametrize(
    "oldest,newest",
    [
        (_D + timedelta(days=1), _D),
        (_NOW, _D),
        (_D, _NOW),
        (None, _D),
        (_D, "bad"),
        (False, _D),
    ],
)
def test_bad_listing_bounds(tmp_path: Path, oldest: Any, newest: Any) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [WellnessListing(oldest, newest, ())]
    result = _run(tmp_path, connector).instances[0]
    assert result.wellness == WellnessPullReport(
        0,
        0,
        (),
        (),
        (),
        (),
        (),
        PullNote("src", "the connector's wellness listing is malformed"),
    )
    assert layout.connector_ledger_path(tmp_path, "src").exists() is False


_INVALID_REVISIONS: list[Any] = [
    "",
    "x" * 513,
    *["left" + chr(c) + "right" for c in range(32)],
    *["left" + chr(c) + "right" for c in range(127, 160)],
    False,
    0,
    1,
    0.0,
    -0.0,
    [],
    {},
    b"raw",
    True,
    -1,
    -2.5,
    1.5,
    [1],
    {"tag": 31},
    (),
    (1,),
    b"",
]


@pytest.mark.parametrize("revision", _INVALID_REVISIONS)
def test_bad_revision_failure(tmp_path: Path, revision: Any) -> None:
    path = _seed(tmp_path, WellnessLedger(through=_D - timedelta(days=3)))
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(_day(2, revision))]
    result = _run(tmp_path, connector).instances[0]
    assert result.wellness is not None
    assert (
        result.wellness.listed,
        result.wellness.unchanged,
        [n.subject for n in result.wellness.failed],
        result.wellness.error,
        result.wellness.would_deliver,
    ) == (1, 0, [(_D + timedelta(days=2)).isoformat()], None, ())
    reason = (
        "wellness revision must be text or absent"
        if not isinstance(revision, str)
        else "wellness revision must contain 1 to 512 characters"
        if not revision or len(revision) > 512
        else "wellness revision must not contain control characters"
    )
    assert result.wellness.failed == (
        PullNote((_D + timedelta(days=2)).isoformat(), reason),
    )
    assert (
        _snapshot(path),
        load_ledger(tmp_path, "src", connector_id=connector.connector_id).wellness,
    ) == (before, WellnessLedger(through=_D - timedelta(days=3)))


@pytest.mark.parametrize(
    "revision", [None, "x", "x" * 512, " ", "zå漢🙂", "\u00a0", "\u2028", "\u200b"]
)
def test_valid_revision(tmp_path: Path, revision: str | None) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(_day(2, revision))]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert result.wellness == WellnessPullReport(
        1, 0, (), ((_D + timedelta(days=2)).isoformat(),), (), (), (), None
    )


@pytest.mark.parametrize("bad_date", [_NOW, None, False, 0, "bad"])
def test_bad_day_date(tmp_path: Path, bad_date: Any) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(WellnessDay(bad_date, "r", object()))]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert result.wellness is not None
    assert (
        [n.subject for n in result.wellness.failed],
        result.wellness.would_deliver,
        result.wellness.unchanged,
    ) == (["listing"], (), 0)
    assert result.wellness.failed == (
        PullNote("listing", "wellness day must be a date"),
    )


@pytest.mark.parametrize(
    "first,second,expected_unchanged,expected_would",
    [
        ("saved", "changed", 1, ()),
        ("changed", "saved", 0, ((_D + timedelta(days=2)).isoformat(),)),
    ],
)
def test_duplicate_keeps_first(
    tmp_path: Path,
    first: str,
    second: str,
    expected_unchanged: int,
    expected_would: tuple[str, ...],
) -> None:
    _seed(
        tmp_path,
        WellnessLedger(through=_D).with_days([(_D + timedelta(days=2), "saved")], _SHA),
    )
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(_day(2, first), _day(2, second))]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert result.wellness is not None
    assert (
        result.wellness.listed,
        result.wellness.unchanged,
        result.wellness.would_deliver,
        [n.subject for n in result.wellness.failed],
    ) == (2, expected_unchanged, expected_would, [(_D + timedelta(days=2)).isoformat()])


def test_diff_sort_missing_and_none(tmp_path: Path) -> None:
    state = WellnessLedger(through=_D).with_days(
        [
            (_D + timedelta(days=1), None),
            (_D + timedelta(days=4), "saved"),
            (_D + timedelta(days=6), "kept"),
            (_D - timedelta(days=4), "omitted"),
        ],
        _SHA,
    )
    path = _seed(tmp_path, state)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [
        _listing(
            _day(8, "alpha"),
            _day(1, None),
            _day(4, "beta"),
            _day(6, "kept"),
            _day(-2, None),
        )
    ]
    connector.wellness_package_script = [
        WellnessPackage(b"{}", ".json", "synthetic", frozenset())
    ]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert result.wellness == WellnessPullReport(
        5,
        2,
        (),
        tuple((_D + timedelta(days=i)).isoformat() for i in [-2, 4, 8]),
        (),
        (),
        (),
        None,
    )
    assert (
        connector.wellness_package_calls,
        _snapshot(path),
        (tmp_path / "inbox").exists(),
    ) == ([], before, False)


@pytest.mark.parametrize(
    "through,start,end,expected",
    [(None, -10, 10, 10), (0, -3, 7, 7), (0, 1, 9, 9), (0, 2, 8, 0), (0, -10, -2, 0)],
)
def test_clean_coverage_and_identical_second_pull(
    tmp_path: Path, through: int | None, start: int, end: int, expected: int
) -> None:
    state = WellnessLedger(
        through=None if through is None else _D + timedelta(days=through)
    ).with_days([(_D, None), (_D - timedelta(days=15), "omitted")], _SHA)
    path = _seed(tmp_path, state)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [
        _listing(_day(0, None), start=start, end=end)
    ] * 2
    connector.wellness_package_script = [
        WellnessPackage(b"{}", ".json", "synthetic", frozenset())
    ] * 2
    result = _run(tmp_path, connector).instances[0]
    ledger = load_ledger(tmp_path, "src", connector_id=connector.connector_id)
    assert ledger.wellness == replace(state, through=_D + timedelta(days=expected))
    assert result.wellness == WellnessPullReport(1, 1, (), (), (), (), (), None)
    before = _snapshot(path)
    _run(tmp_path, connector)
    assert (_snapshot(path), connector.wellness_package_calls) == (before, [])


def test_failed_duplicate_prevents_coverage(tmp_path: Path) -> None:
    state = WellnessLedger(through=_D).with_days(
        [(_D + timedelta(days=2), "saved")], _SHA
    )
    path = _seed(tmp_path, state)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(_day(2, "saved"), _day(2, "other"))]
    _run(tmp_path, connector)
    assert _snapshot(path) == before


def _pending(root: Path) -> tuple[Path, Path, WellnessLedger]:
    data = b'{"synthetic":31}\n'
    sha = hashlib.sha256(data).hexdigest()
    rel = "src/wellness.json"
    delivery = root / "inbox" / rel
    delivery.parent.mkdir(parents=True)
    delivery.write_bytes(data)
    archive = layout.wellness_archive_path(root, "intervals-icu", sha, ".json")
    archive.parent.mkdir(parents=True)
    archive.write_bytes(data)
    state = (
        WellnessLedger(through=_D)
        .with_days([(_D, "saved")], sha)
        .with_pending(WellnessPending(rel, sha, "intervals-icu", ".json"))
    )
    return delivery, archive, state


@pytest.mark.parametrize("enabled", [False, True])
def test_pending_sweep_even_when_disabled(tmp_path: Path, enabled: bool) -> None:
    delivery, archive, state = _pending(tmp_path)
    _seed(tmp_path, state)
    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    connector.listing_script = [Listing(())]
    connector.wellness_listing_script = [_listing(_day(0, "saved"), end=0)]
    result = _run(tmp_path, connector, enabled=enabled).instances[0]
    assert (
        delivery.exists(),
        archive.is_file(),
        result.removed,
        load_ledger(tmp_path, "src", connector_id=connector.connector_id).wellness,
    ) == (False, True, ("src/wellness.json",), replace(state, pending=()))


def test_dry_run_preserves_pending_bytes_and_mtime(tmp_path: Path) -> None:
    delivery, archive, state = _pending(tmp_path)
    path = _seed(tmp_path, state)
    before = (_snapshot(path), _snapshot(delivery), _snapshot(archive))
    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    connector.listing_script = [
        Listing(
            (
                RemoteActivity(
                    "dry-unavailable", False, unavailable_reason="synthetic absent"
                ),
            )
        )
    ]
    connector.wellness_package_script = [
        WellnessPackage(b"{}", ".json", "synthetic", frozenset())
    ]
    connector.wellness_listing_script = [_listing(_day(0, "saved"))]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert delivery.is_file() is True
    assert (
        _snapshot(path),
        _snapshot(delivery),
        _snapshot(archive),
        result.removed,
        connector.wellness_package_calls,
    ) == (*before, (), [])


@pytest.mark.parametrize(
    "channel",
    [
        "none",
        "unchanged",
        "held",
        "notice",
        "failed",
        "error",
        "instance-error",
        "instance-failed",
    ],
)
def test_failed_channels(channel: str) -> None:
    wellness = (
        None
        if channel == "none"
        else WellnessPullReport(
            17,
            3 if channel == "unchanged" else 0,
            (),
            (),
            ("span",) if channel == "held" else (),
            (PullNote("bad", "detail"),) if channel == "failed" else (),
            (PullNote("origin", "notice"),) if channel == "notice" else (),
            PullNote("src", "error") if channel == "error" else None,
        )
    )
    inst = InstancePullReport(
        "src",
        "synthetic",
        0,
        (),
        (),
        (),
        (),
        (),
        (PullNote("activity", "failed"),) if channel == "instance-failed" else (),
        (),
        PullNote("src", "error") if channel == "instance-error" else None,
        wellness,
    )
    assert PullReport("inbox", False, (inst,)).failed is (
        channel in {"failed", "error", "instance-error", "instance-failed"}
    )


def test_report_shapes_and_trailing_default() -> None:
    assert tuple(f.name for f in fields(WellnessDelivered)) == ("span", "days", "path")
    assert tuple(f.name for f in fields(WellnessPullReport)) == (
        "listed",
        "unchanged",
        "delivered",
        "would_deliver",
        "held",
        "failed",
        "notices",
        "error",
    )
    assert tuple(f.name for f in fields(InstancePullReport))[-1] == "wellness"
    assert (
        InstancePullReport(
            "src", "synthetic", 0, (), (), (), (), (), (), (), None
        ).wellness
        is None
    )


def test_failure_notes_are_sorted(tmp_path: Path) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [
        _listing(_day(8, ""), _day(-2, "\x7f"), _day(3, "x" * 513))
    ]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert result.wellness is not None
    assert result.wellness.failed == (
        PullNote(
            (_D - timedelta(days=2)).isoformat(),
            "wellness revision must not contain control characters",
        ),
        PullNote(
            (_D + timedelta(days=3)).isoformat(),
            "wellness revision must contain 1 to 512 characters",
        ),
        PullNote(
            (_D + timedelta(days=8)).isoformat(),
            "wellness revision must contain 1 to 512 characters",
        ),
    )


def test_interim_changed_nondry_keeps_seeded_mark(tmp_path: Path) -> None:
    state = WellnessLedger(through=_D).with_days([(_D, "saved")], _SHA)
    path = _seed(tmp_path, state)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(_day(0, "changed"))]
    result = _run(tmp_path, connector).instances[0]
    assert (result.wellness, _snapshot(path), connector.wellness_package_calls) == (
        WellnessPullReport(1, 0, (), (), (), (), (), None),
        before,
        [],
    )


@pytest.mark.parametrize(
    "item", [None, object(), SimpleNamespace(revision="r"), SimpleNamespace(day=_D)]
)
def test_missing_day_attributes(tmp_path: Path, item: Any) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(item)]
    result = _run(tmp_path, connector, dry=True).instances[0]
    subject = _D.isoformat() if hasattr(item, "day") else "listing"
    detail = (
        "wellness revision must be text or absent"
        if hasattr(item, "day")
        else "wellness day must be a date"
    )
    assert result.wellness == WellnessPullReport(
        1, 0, (), (), (), (PullNote(subject, detail),), (), None
    )


@pytest.mark.parametrize("item", [None, object(), SimpleNamespace(newest=_D)])
def test_missing_listing_bounds(tmp_path: Path, item: Any) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [item]
    result = _run(tmp_path, connector).instances[0]
    assert result.wellness == WellnessPullReport(
        0,
        0,
        (),
        (),
        (),
        (),
        (),
        PullNote("src", "the connector's wellness listing is malformed"),
    )


@pytest.mark.parametrize("site", ["credentials", "renewal"])
def test_credential_failure_prevents_data_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, site: str
) -> None:
    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    events: list[str] = []
    modes: list[object] = []
    real_session = ConnectorSession

    def construct(**kwargs: Any) -> ConnectorSession:
        modes.append(kwargs["http"].mode)
        return real_session(**kwargs)

    def credentials(*args: Any) -> Any:
        events.append("credentials")
        if site == "credentials":
            raise ConnectorError("credential failure")
        return SimpleNamespace(expires_at=_NOW)

    def refresh(session: ConnectorSession) -> Any:
        events.append("renewal")
        raise ConnectorError("renewal failure")

    if site == "renewal":
        connector.auth_style = AuthStyle.LOGIN
    monkeypatch.setattr(pull_mod, "ConnectorSession", construct)
    monkeypatch.setattr(pull_mod, "resolve_credentials", credentials)
    monkeypatch.setattr(connector, "refresh", refresh, raising=False)
    result = _run(tmp_path, connector).instances[0]
    from fitdocs.connectors.http import CallMode

    assert (events, modes, connector.calls, result.wellness, result.error) == (
        ["credentials"] + (["renewal"] if site == "renewal" else []),
        [CallMode.AUTH] if site == "renewal" else [],
        [],
        None,
        PullNote(
            "src",
            "ConnectorError: credential failure"
            if site == "credentials"
            else "ConnectorError: renewal failure",
        ),
    )


def test_interruption_saves_current_holder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing()]
    real_wellness = pull_mod._pull_wellness

    def interrupt(holder: Any, **kwargs: Any) -> Any:
        real_wellness(holder, **kwargs)
        raise KeyboardInterrupt("synthetic interruption")

    monkeypatch.setattr(pull_mod, "_pull_wellness", interrupt)
    with pytest.raises(KeyboardInterrupt, match="synthetic interruption"):
        _run(tmp_path, connector)
    assert load_ledger(
        tmp_path, "src", connector_id=connector.connector_id
    ).wellness == WellnessLedger(through=_D + timedelta(days=20))


@pytest.mark.parametrize("record", [None, False, 0, 1.5, "opaque", [], {}, object()])
def test_record_domain_is_opaque(tmp_path: Path, record: object) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(WellnessDay(_D, None, record))]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert result.wellness == WellnessPullReport(
        1, 0, (), (_D.isoformat(),), (), (), (), None
    )


def test_invalid_first_duplicate_stays_unrecorded(tmp_path: Path) -> None:
    state = WellnessLedger(through=_D)
    path = _seed(tmp_path, state)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing(_day(2, ""), _day(2, "valid"))]
    result = _run(tmp_path, connector, dry=True).instances[0]
    assert result.wellness == WellnessPullReport(
        2,
        0,
        (),
        (),
        (),
        (
            PullNote(
                (_D + timedelta(days=2)).isoformat(),
                "wellness revision must contain 1 to 512 characters",
            ),
            PullNote(
                (_D + timedelta(days=2)).isoformat(),
                "wellness date listed more than once",
            ),
        ),
        (),
        None,
    )
    assert _snapshot(path) == before


def test_listing_error_keeps_seeded_mark(tmp_path: Path) -> None:
    state = WellnessLedger(through=_D).with_days([(_D, "prior")], _SHA)
    path = _seed(tmp_path, state)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [ConnectorError("failed list")]
    _run(tmp_path, connector)
    assert _snapshot(path) == before


def test_empty_first_pull_persists_wellness_coverage(tmp_path: Path) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing()]
    result = _run(tmp_path, connector).instances[0]
    assert (
        result.wellness,
        load_ledger(tmp_path, "src", connector_id=connector.connector_id),
    ) == (
        WellnessPullReport(0, 0, (), (), (), (), (), None),
        Ledger(
            connector.connector_id,
            None,
            (),
            WellnessLedger(through=_D + timedelta(days=20)),
        ),
    )


def test_omitted_day_keeps_deliveries_and_archive(tmp_path: Path) -> None:
    delivery, archive, state = _pending(tmp_path)
    state = replace(state, pending=())
    _seed(tmp_path, state)
    before_files = (_snapshot(delivery), _snapshot(archive))
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_listing()]
    _run(tmp_path, connector)
    assert (
        load_ledger(tmp_path, "src", connector_id=connector.connector_id).wellness,
        _snapshot(delivery),
        _snapshot(archive),
    ) == (replace(state, through=_D + timedelta(days=20)), *before_files)


@pytest.mark.parametrize(
    "report_type,expected",
    [
        (WellnessDelivered, {"span": str, "days": int, "path": str}),
        (
            WellnessPullReport,
            {
                "listed": int,
                "unchanged": int,
                "delivered": tuple[WellnessDelivered, ...],
                "would_deliver": tuple[str, ...],
                "held": tuple[str, ...],
                "failed": tuple[PullNote, ...],
                "notices": tuple[PullNote, ...],
                "error": PullNote | None,
            },
        ),
    ],
)
def test_wellness_report_type_contract(
    report_type: type[Any], expected: dict[str, object]
) -> None:
    assert (get_type_hints(report_type), report_type.__dataclass_params__.frozen) == (
        expected,
        True,
    )


@pytest.mark.parametrize(
    "caps",
    [
        frozenset({Capability.PULL_PLANS}),
        frozenset({Capability.PULL_WELLNESS}),
        frozenset({Capability.PULL_ACTIVITIES}),
        _BOTH,
        frozenset({Capability.PULL_PLANS, Capability.PULL_WELLNESS}),
        frozenset({Capability.PULL_PLANS, Capability.PULL_ACTIVITIES}),
        frozenset({Capability.PULL_PLANS, *_BOTH}),
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_runnable_declaration_order(caps: frozenset[Capability], enabled: bool) -> None:
    connector = ScriptedWellnessPuller(capabilities=caps)
    expected = (
        (Capability.PULL_ACTIVITIES,) if Capability.PULL_ACTIVITIES in caps else ()
    ) + (
        (Capability.PULL_WELLNESS,)
        if enabled and Capability.PULL_WELLNESS in caps
        else ()
    )
    assert pull_mod._runnable(_instance(connector, enabled=enabled)) == expected


@pytest.mark.parametrize(
    "role,listed_count,unchanged_count",
    [
        ("empty", 0, 0),
        ("new", 1, 0),
        ("old", 1, 1),
        ("mixed", 5, 2),
        ("old-many", 3, 3),
        ("bad-day", 2, 1),
        ("missing-day", 2, 1),
        ("duplicate-old", 2, 1),
        ("duplicate-new", 2, 0),
        ("malformed-bounds", 0, 0),
        ("listing-error", 0, 0),
    ],
)
@pytest.mark.parametrize(
    "observation", ["listed-type", "unchanged-type", "listed-value", "unchanged-value"]
)
def test_runtime_counter_family(
    tmp_path: Path, role: str, listed_count: int, unchanged_count: int, observation: str
) -> None:
    state = WellnessLedger(through=_D).with_days(
        [
            (_D + timedelta(days=1), None),
            (_D + timedelta(days=4), "saved"),
            (_D + timedelta(days=6), "kept"),
        ],
        _SHA,
    )
    _seed(tmp_path, state)
    cases: dict[str, WellnessListing | BaseException] = {
        "empty": _listing(),
        "new": _listing(_day(2, None)),
        "old": _listing(_day(1, None)),
        "mixed": _listing(
            _day(8, "alpha"),
            _day(1, None),
            _day(4, "beta"),
            _day(6, "kept"),
            _day(-2, None),
        ),
        "old-many": _listing(_day(6, "kept"), _day(1, None), _day(4, "saved")),
        "bad-day": _listing(_day(2, ""), _day(1, None)),
        "missing-day": _listing(SimpleNamespace(revision="r"), _day(1, None)),
        "duplicate-old": _listing(_day(6, "kept"), _day(6, "changed")),
        "duplicate-new": _listing(_day(6, "changed"), _day(6, "kept")),
        "malformed-bounds": WellnessListing(
            _D + timedelta(days=1), _D, (_day(1, None),)
        ),
        "listing-error": ConnectorError("counter listing failure"),
    }
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [cases[role]]
    wellness = _run(tmp_path, connector, dry=True).instances[0].wellness
    assert wellness is not None
    actual = {
        "listed-type": type(wellness.listed),
        "unchanged-type": type(wellness.unchanged),
        "listed-value": wellness.listed,
        "unchanged-value": wellness.unchanged,
    }[observation]
    expected = {
        "listed-type": int,
        "unchanged-type": int,
        "listed-value": listed_count,
        "unchanged-value": unchanged_count,
    }[observation]
    assert actual == expected


_ROUND2_CAPABILITY_ROLES = tuple(
    (
        frozenset(
            capability for bit, capability in enumerate(Capability) if mask & (1 << bit)
        ),
        enabled,
    )
    for mask in range(1, 1 << len(Capability))
    for enabled in (False, True)
    if not enabled or mask & (1 << tuple(Capability).index(Capability.PULL_WELLNESS))
)


@pytest.mark.parametrize("caps,enabled", _ROUND2_CAPABILITY_ROLES)
def test_round2_all_registered_capability_roles(
    tmp_path: Path, caps: frozenset[Capability], enabled: bool
) -> None:
    from fitdocs.connectors.registry import register

    connector = ScriptedWellnessPuller(capabilities=caps)
    register(connector)
    connector.listing_script = [Listing(())]
    connector.wellness_listing_script = [_listing()]
    expected = (
        (Capability.PULL_ACTIVITIES,) if Capability.PULL_ACTIVITIES in caps else ()
    ) + ((Capability.PULL_WELLNESS,) if enabled else ())
    instance = _instance(connector, enabled=enabled)
    result = _run(tmp_path, connector, enabled=enabled, dry=True).instances[0]
    assert pull_mod._runnable(instance) == expected
    expected_error = (
        None
        if expected
        else PullNote(
            "src",
            "pulls only wellness, which is not enabled for this instance; "
            "set wellness = true in [connectors.src]"
            if Capability.PULL_WELLNESS in caps
            else "does not pull activities or wellness",
        )
    )
    assert result.error == expected_error
    assert connector.calls == [
        "list_activities"
        if capability is Capability.PULL_ACTIVITIES
        else "list_wellness"
        for capability in expected
    ]
    assert (result.wellness is not None) is enabled


def _round2_revision_roles() -> tuple[tuple[bool, str | None, str | None, bool], ...]:
    rows: list[tuple[bool, str | None, str | None, bool]] = [
        (False, None, None, True),
        (False, None, "text", True),
        (True, None, None, False),
        (True, None, "None", True),
        (True, "None", None, True),
        (True, "same", "same", False),
        (True, "alpha", "beta", True),
        (True, "ABC", "abc", True),
        (True, "abc", "ABC", True),
        (True, "ß", "ss", True),
        (True, "ss", "ß", True),
        (True, "Σ", "σ", True),
        (True, "σ", "ς", True),
        (True, "É", "é", True),
        (True, "İ", "i\u0307", True),
        (True, "é", "e\u0301", True),
        (True, "e\u0301", "é", True),
        (True, "Å", "A\u030a", True),
        (True, "Ａ", "A", True),
        (True, "ﬀ", "ff", True),
        (True, "é" * 512, "é" * 511 + "É", True),
        (True, "a b", "ab", True),
        (True, "a  b", "a b", True),
        (True, "a\u00a0b", "a b", True),
        (True, "a\u2003b", "ab", True),
        (True, "31", "31.0", True),
        (True, "0", "00", True),
        (True, "0", "-0", True),
        (True, "1", "+1", True),
        (True, "1", "1e0", True),
        (True, _D.isoformat(), _D.isoformat() + " ", True),
        (True, _D.isoformat(), _D.strftime("%Y%m%d"), True),
        (True, "é", "é", False),
        (True, "🙂" * 512, "🙂" * 512, False),
        (True, " same ", " same ", False),
    ]
    for whitespace in (
        " ",
        "\u00a0",
        "\u2002",
        "\u2003",
        "\u2007",
        "\u2009",
        "\u202f",
        "\u3000",
        "\u2028",
    ):
        rows.extend(
            (
                (True, whitespace + "text", "text", True),
                (True, "text" + whitespace, "text", True),
                (True, "text", whitespace + "text", True),
                (True, "text", "text" + whitespace, True),
                (True, whitespace, whitespace, False),
            )
        )
    return tuple(rows)


@pytest.mark.parametrize("recorded,prior,revision,changed", _round2_revision_roles())
@pytest.mark.parametrize("observation", ["unchanged", "would", "failed", "ledger"])
def test_round2_exact_revision_identity(
    tmp_path: Path,
    recorded: bool,
    prior: str | None,
    revision: str | None,
    changed: bool,
    observation: str,
) -> None:
    from fitdocs.connectors.registry import register

    state = WellnessLedger(through=_D)
    if recorded:
        state = state.with_days([(_D, prior)], _SHA)
    path = _seed(tmp_path, state)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    register(connector)
    connector.wellness_listing_script = [_listing(WellnessDay(_D, revision, object()))]
    wellness = _run(tmp_path, connector, dry=True).instances[0].wellness
    assert wellness is not None
    actual = {
        "unchanged": wellness.unchanged,
        "would": wellness.would_deliver,
        "failed": (wellness.failed, wellness.error),
        "ledger": _snapshot(path),
    }[observation]
    expected = {
        "unchanged": 0 if changed else 1,
        "would": (_D.isoformat(),) if changed else (),
        "failed": ((), None),
        "ledger": before,
    }[observation]
    assert actual == expected


@pytest.mark.parametrize("char", ["x", "é", "漢", "🙂"])
@pytest.mark.parametrize("length", [1, 127, 128, 255, 256, 511, 512, 513])
@pytest.mark.parametrize("dry", [False, True])
@pytest.mark.parametrize("observation", ["unchanged", "would", "failed", "ledger"])
def test_round2_revision_character_lengths(
    tmp_path: Path, char: str, length: int, dry: bool, observation: str
) -> None:
    from fitdocs.connectors.registry import register

    revision = char * length
    valid = length <= 512
    state = WellnessLedger(through=_D - timedelta(days=3))
    if not dry:
        state = state.with_days([(_D, revision if valid else "prior")], _SHA)
    _seed(tmp_path, state)
    connector = ScriptedWellnessPuller()
    register(connector)
    connector.wellness_listing_script = [_listing(WellnessDay(_D, revision, object()))]
    wellness = _run(tmp_path, connector, dry=dry).instances[0].wellness
    assert wellness is not None
    failure = (
        ()
        if valid
        else (
            PullNote(
                _D.isoformat(), "wellness revision must contain 1 to 512 characters"
            ),
        )
    )
    actual = {
        "unchanged": wellness.unchanged,
        "would": wellness.would_deliver,
        "failed": (wellness.failed, wellness.error),
        "ledger": load_ledger(
            tmp_path, "src", connector_id=connector.connector_id
        ).wellness,
    }[observation]
    expected = {
        "unchanged": 1 if valid and not dry else 0,
        "would": (_D.isoformat(),) if valid and dry else (),
        "failed": (failure, None),
        "ledger": replace(state, through=_D + timedelta(days=20))
        if valid and not dry
        else state,
    }[observation]
    assert actual == expected


_ROUND2_INTERRUPTION_ROLES = tuple(
    (kind, completed_activity, observation)
    for kind in (KeyboardInterrupt, SystemExit, GeneratorExit)
    for completed_activity in (False, True)
    for observation in (
        (
            "propagation",
            "wellness",
            "calls",
            "activity-entry",
            "activity-file",
            "watermark",
        )
        if completed_activity
        else ("propagation", "wellness", "calls")
    )
)


@pytest.mark.parametrize(
    "kind,completed_activity,observation", _ROUND2_INTERRUPTION_ROLES
)
def test_round2_direct_listing_interruption(
    tmp_path: Path,
    kind: type[BaseException],
    completed_activity: bool,
    observation: str,
) -> None:
    from fitdocs.connectors.protocol import Fetched
    from fitdocs.connectors.registry import register

    connector = ScriptedWellnessPuller(
        capabilities=_BOTH
        if completed_activity
        else frozenset({Capability.PULL_WELLNESS})
    )
    register(connector)
    state = WellnessLedger(through=_D).with_days([(_D, "prior")], _SHA)
    _seed(tmp_path, state)
    data = bytes([12, 0x10, 0, 0, 0, 0, 0, 0]) + b".FIT" + b"synthetic round2 activity"
    sha = hashlib.sha256(data).hexdigest()
    if completed_activity:
        connector.listing_script = [
            Listing(
                (
                    RemoteActivity(
                        "fresh-activity",
                        True,
                        start=_NOW,
                        revision="new",
                        suggested_name="round2-activity.fit",
                    ),
                )
            )
        ]
        connector.fetch_script = [Fetched(data)]
    connector.wellness_listing_script = [kind("synthetic round2 stop")] * 2
    caught: BaseException | None = None
    try:
        _run(tmp_path, connector)
    except BaseException as exc:
        caught = exc
    ledger = load_ledger(tmp_path, "src", connector_id=connector.connector_id)
    path = tmp_path / "inbox" / "src" / "round2-activity.fit"
    actual = {
        "propagation": type(caught),
        "wellness": ledger.wellness,
        "calls": connector.calls,
        "activity-entry": ledger.get("fresh-activity"),
        "activity-file": path.read_bytes() if path.is_file() else None,
        "watermark": ledger.watermark,
    }[observation]
    expected = {
        "propagation": kind,
        "wellness": state,
        "calls": ["list_activities", "fetch_activity", "list_wellness"]
        if completed_activity
        else ["list_wellness"],
        "activity-entry": LedgerEntry(
            "fresh-activity",
            Outcome.DELIVERED,
            revision="new",
            sha256=sha,
            pending="src/round2-activity.fit",
        ),
        "activity-file": data,
        "watermark": _NOW,
    }[observation]
    assert actual == expected


@pytest.mark.parametrize(
    "failure",
    [
        Exception("round2 ordinary"),
        ValueError("round2 ordinary"),
        RuntimeError("round2 ordinary"),
        ConnectorError("round2 ordinary"),
        AuthFailure(AuthFailureKind.REJECTED, "round2 ordinary"),
    ],
)
@pytest.mark.parametrize(
    "observation", ["error", "next", "failed-flag", "calls", "ledger"]
)
def test_round2_ordinary_listing_failures_continue(
    tmp_path: Path, failure: Exception, observation: str
) -> None:
    from fitdocs.connectors.registry import register

    connector = ScriptedWellnessPuller()
    register(connector)
    state = WellnessLedger(through=_D).with_days([(_D, "prior")], _SHA)
    path = _seed(tmp_path, state)
    before = _snapshot(path)
    connector.wellness_listing_script = [failure, _listing()]
    report = _run(
        tmp_path,
        connector,
        instances=[_instance(connector), _instance(connector, name="next")],
    )
    extra = (
        " " + next_step(failure.kind, name="src", retry_after_s=None)
        if isinstance(failure, AuthFailure)
        else ""
    )
    actual = {
        "error": getattr(report.instances[0].wellness, "error", None),
        "next": next(
            (item.wellness for item in report.instances if item.name == "next"),
            "missing",
        ),
        "failed-flag": report.failed,
        "calls": connector.calls,
        "ledger": _snapshot(path),
    }[observation]
    expected = {
        "error": PullNote("src", f"{type(failure).__name__}: round2 ordinary{extra}"),
        "next": WellnessPullReport(0, 0, (), (), (), (), (), None),
        "failed-flag": True,
        "calls": ["list_wellness", "list_wellness"],
        "ledger": before,
    }[observation]
    assert actual == expected


class _Round3AuthFailure(AuthFailure):
    pass


@pytest.mark.parametrize("failure_type", [AuthFailure, _Round3AuthFailure])
@pytest.mark.parametrize("kind", list(AuthFailureKind))
@pytest.mark.parametrize("site", ["listing", "fetch"])
@pytest.mark.parametrize("observation", ["calls", "wellness", "error"])
def test_round3_activity_authentication_roles(
    tmp_path: Path,
    failure_type: type[AuthFailure],
    kind: AuthFailureKind,
    site: str,
    observation: str,
) -> None:
    from fitdocs.connectors.registry import register

    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    register(connector)
    failure = failure_type(kind, "synthetic round3 refusal", retry_after_s=17)
    activity = RemoteActivity("activity", True, start=_NOW, revision="r")
    connector.listing_script = [failure if site == "listing" else Listing((activity,))]
    connector.fetch_script = [failure]
    connector.wellness_listing_script = [_listing()]
    result = _run(tmp_path, connector).instances[0]
    actual = {
        "calls": connector.calls,
        "wellness": result.wellness,
        "error": (result.error, result.failed),
    }[observation]
    expected = {
        "calls": ["list_activities"] + (["fetch_activity"] if site == "fetch" else []),
        "wellness": None,
        "error": (
            PullNote(
                "src",
                f"{failure_type.__name__}: synthetic round3 refusal "
                + next_step(kind, name="src", retry_after_s=17),
            ),
            (),
        ),
    }[observation]
    assert actual == expected


@pytest.mark.parametrize(
    "failure_type", [Exception, ValueError, RuntimeError, ConnectorError]
)
@pytest.mark.parametrize("site", ["listing", "fetch"])
@pytest.mark.parametrize("observation", ["calls", "wellness", "error"])
def test_round3_ordinary_activity_continues(
    tmp_path: Path,
    failure_type: type[Exception],
    site: str,
    observation: str,
) -> None:
    from fitdocs.connectors.registry import register

    connector = ScriptedWellnessPuller(capabilities=_BOTH)
    register(connector)
    failure = failure_type("synthetic round3 ordinary")
    activity = RemoteActivity("activity", True, start=_NOW, revision="r")
    connector.listing_script = [failure if site == "listing" else Listing((activity,))]
    connector.fetch_script = [failure]
    connector.wellness_listing_script = [_listing()]
    result = _run(tmp_path, connector).instances[0]
    detail = f"{failure_type.__name__}: synthetic round3 ordinary"
    terminal = site == "listing" or failure_type is ConnectorError
    actual = {
        "calls": connector.calls,
        "wellness": result.wellness,
        "error": (result.error, result.failed),
    }[observation]
    expected = {
        "calls": ["list_activities"]
        + (["fetch_activity"] if site == "fetch" else [])
        + ["list_wellness"],
        "wellness": WellnessPullReport(0, 0, (), (), (), (), (), None),
        "error": (PullNote("src", detail), ())
        if terminal
        else (None, (PullNote("activity", detail),)),
    }[observation]
    assert actual == expected


@pytest.mark.parametrize("lookback", [0, 1, 7, 30, 365, 3649, 3650])
@pytest.mark.parametrize("marked", [False, True])
@pytest.mark.parametrize("explicit_since", [False, True])
def test_round3_date_window_roles(
    tmp_path: Path, lookback: int, marked: bool, explicit_since: bool
) -> None:
    from fitdocs.connectors.registry import register

    connector = ScriptedWellnessPuller()
    register(connector)
    if marked:
        _seed(tmp_path, WellnessLedger(through=_D))
    since = (
        datetime.combine(
            _D + timedelta(days=2),
            datetime.min.time(),
            timezone(timedelta(hours=5)),
        )
        if explicit_since
        else None
    )
    connector.wellness_listing_script = [_listing()]
    _run(tmp_path, connector, dry=True, lookback=lookback, since=since)
    expected = (
        _D + timedelta(days=1)
        if explicit_since
        else _D - timedelta(days=lookback)
        if marked
        else None
    )
    assert connector.wellness_list_calls == [expected]


@pytest.mark.parametrize("relation", ["singleton", "increasing", "decreasing"])
@pytest.mark.parametrize(
    "nonempty,seeded,dry",
    [
        (False, False, False),
        (False, False, True),
        (False, True, False),
        (False, True, True),
        (True, True, False),
        (True, True, True),
        (True, False, True),
    ],
)
@pytest.mark.parametrize("observation", ["report", "ledger"])
def test_round3_listing_bound_relations(
    tmp_path: Path,
    relation: str,
    nonempty: bool,
    seeded: bool,
    dry: bool,
    observation: str,
) -> None:
    from fitdocs.connectors.registry import register

    connector = ScriptedWellnessPuller()
    register(connector)
    state = WellnessLedger(through=_D - timedelta(days=1)) if seeded else None
    if seeded:
        if nonempty:
            state = WellnessLedger(through=_D - timedelta(days=1)).with_days(
                [(_D, "kept")], _SHA
            )
        _seed(tmp_path, state)
    newest = _D + timedelta(
        days={"singleton": 0, "increasing": 2, "decreasing": -1}[relation]
    )
    days = (WellnessDay(_D, "kept", object()),) if nonempty else ()
    connector.wellness_listing_script = [WellnessListing(_D, newest, days)]
    wellness = _run(tmp_path, connector, dry=dry).instances[0].wellness
    valid = relation != "decreasing"
    report = (
        WellnessPullReport(
            int(nonempty),
            int(nonempty and seeded),
            (),
            (_D.isoformat(),) if nonempty and not seeded and dry else (),
            (),
            (),
            (),
            None,
        )
        if valid
        else WellnessPullReport(
            0,
            0,
            (),
            (),
            (),
            (),
            (),
            PullNote("src", "the connector's wellness listing is malformed"),
        )
    )
    actual = {
        "report": wellness,
        "ledger": load_ledger(
            tmp_path, "src", connector_id=connector.connector_id
        ).wellness,
    }[observation]
    expected = {
        "report": report,
        "ledger": replace(state or WellnessLedger(), through=newest)
        if valid and not dry
        else state,
    }[observation]
    assert actual == expected
