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


_P_YEAR = _D.year + (-_D.year % 4)
_P_DATES = (
    date(_P_YEAR - 1, 12, 31),
    date(_P_YEAR, 2, 29),
    date(_P_YEAR, 3, 2),
    date(_P_YEAR + 1, 1, 1),
)
_P_BYTES = (b'{"synthetic": 71}\n', b"[false, 23, null]\n", b'"synthetic-109"\n')
_P_FORMATS = ("a", "format-2", "7")
_P_ORIGINS: tuple[frozenset[str], ...] = (
    frozenset({"zeta", "beta"}),
    frozenset({"alpha"}),
    frozenset(),
)
_P_SPANS = (
    f"{_P_DATES[0]}..{_P_DATES[0]}",
    f"{_P_DATES[1]}..{_P_DATES[2]}",
    f"{_P_DATES[3]}..{_P_DATES[3]}",
)
_P_PATHS = (
    f"src/wellness-{_P_DATES[0]}_{_P_DATES[0]}.json",
    f"src/wellness-{_P_DATES[1]}_{_P_DATES[2]}.json",
    f"src/wellness-{_P_DATES[3]}_{_P_DATES[3]}.json",
)
_P_HASHES = tuple(hashlib.sha256(data).hexdigest() for data in _P_BYTES)


def _p_days() -> tuple[WellnessDay, ...]:
    return (
        WellnessDay(_P_DATES[3], "b", {"value": 61, "updated": False}),
        WellnessDay(_P_DATES[2], "a", {"value": 13, "id": None}),
        WellnessDay(_P_DATES[0], "z", {"value": 47, "sport": [None, False]}),
        WellnessDay(_P_DATES[1], "y", {"value": 89, "fitness": {"x": 0}}),
    )


def _p_listing(days: tuple[WellnessDay, ...]) -> WellnessListing:
    return WellnessListing(_P_DATES[0], _P_DATES[3] + timedelta(days=4), days)


def _p_packages() -> list[WellnessPackage | BaseException]:
    return [
        WellnessPackage(data, ".json", fmt, origins)
        for data, fmt, origins in zip(_P_BYTES, _P_FORMATS, _P_ORIGINS, strict=True)
    ]


def _p_loaded(root: Path) -> WellnessLedger | None:
    return load_ledger(root, "src", connector_id="scripted-wellness-puller").wellness


def _p_projection(state: WellnessLedger | None, field: str) -> object:
    return getattr(state, field, None)


_P_YEARS_OBSERVATIONS = (
    "groups",
    "identities",
    "record-identities",
    "records",
    "session",
    "settings",
    "names",
    "bytes",
    "days",
    "pending",
    "coverage",
    "origins",
    "delivered",
    "notices",
    "counts",
    "owned",
    "suffix",
    "archive-arguments",
    "validator-arguments",
    "holder-days",
    "holder-pending",
    "holder-origins",
)


@pytest.mark.parametrize("observation", _P_YEARS_OBSERVATIONS)
def test_packaging_years(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observation: str
) -> None:
    import json

    from fitdocs.connectors import delivery as delivery_mod

    connector = ScriptedWellnessPuller()
    days = _p_days()
    before_records = tuple(json.dumps(day.record, sort_keys=True) for day in days)
    before_record_ids = tuple(id(day.record) for day in days)
    connector.wellness_listing_script = [_p_listing(days)]
    connector.wellness_package_script = _p_packages()
    sessions: list[ConnectorSession] = []
    settings = object()
    holders: list[Any] = []
    holder_states: list[WellnessLedger | None] = []
    original_holder = pull_mod._LedgerHolder

    def make_holder(ledger: Ledger) -> Any:
        holder = original_holder(ledger)
        holders.append(holder)
        return holder

    monkeypatch.setattr(pull_mod, "_LedgerHolder", make_holder)
    original_list = connector.list_wellness
    original_package = connector.package_wellness
    original_deliver = delivery_mod.deliver
    deliveries: list[tuple[Any, ...]] = []
    archives: list[tuple[object, ...]] = []
    checks: list[tuple[object, ...]] = []

    def list_days(session: ConnectorSession, oldest: date | None) -> WellnessListing:
        sessions.append(session)
        return original_list(session, oldest)

    def package(
        session: ConnectorSession, group: tuple[WellnessDay, ...]
    ) -> WellnessPackage:
        sessions.append(session)
        holder_states.append(holders[-1].ledger.wellness)
        return original_package(session, group)

    def deliver(*args: Any, **kwargs: Any) -> Any:
        deliveries.append((*args, dict(kwargs)))
        return original_deliver(*args, **kwargs)

    def archived(*args: Any) -> bool:
        archives.append(args)
        return delivery_mod.wellness_archived(*args)

    def check(*args: Any) -> str | None:
        checks.append(args)
        return delivery_mod.wellness_package_problem(*args)

    monkeypatch.setattr(connector, "list_wellness", list_days)
    monkeypatch.setattr(connector, "package_wellness", package)
    monkeypatch.setattr(pull_mod, "deliver", deliver)
    monkeypatch.setattr(pull_mod, "wellness_archived", archived, raising=False)
    monkeypatch.setattr(pull_mod, "wellness_package_problem", check, raising=False)
    was_absent = not (tmp_path / "inbox").exists() and _p_loaded(tmp_path) is None
    report = _run(
        tmp_path, connector, instances=[_instance(connector, settings=settings)]
    )
    result = report.instances[0].wellness
    state = _p_loaded(tmp_path)
    groups = connector.wellness_package_calls
    expected_groups = ((days[2],), (days[3], days[1]), (days[0],))
    actual = {
        "holder-days": tuple(_p_projection(state, "days") for state in holder_states),
        "holder-pending": tuple(
            _p_projection(state, "pending") for state in holder_states
        ),
        "holder-origins": tuple(
            _p_projection(state, "origins") for state in holder_states
        ),
        "groups": tuple(tuple(day.day for day in group) for group in groups),
        "identities": tuple(tuple(id(day) for day in group) for group in groups),
        "record-identities": tuple(
            tuple(id(day.record) for day in group) for group in groups
        ),
        "records": tuple(json.dumps(day.record, sort_keys=True) for day in days),
        "session": (len(sessions), tuple(id(session) for session in sessions[1:])),
        "settings": tuple(session.settings is settings for session in sessions),
        "names": tuple(
            sorted(
                path.relative_to(tmp_path / "inbox").as_posix()
                for path in (tmp_path / "inbox").rglob("*.json")
            )
        ),
        "bytes": tuple(
            (tmp_path / "inbox" / path).read_bytes()
            if (tmp_path / "inbox" / path).is_file()
            else None
            for path in _P_PATHS
        ),
        "days": _p_projection(state, "days"),
        "pending": _p_projection(state, "pending"),
        "coverage": _p_projection(state, "through"),
        "origins": _p_projection(state, "origins"),
        "delivered": getattr(result, "delivered", None),
        "notices": getattr(result, "notices", None),
        "counts": (
            getattr(result, "listed", None),
            getattr(result, "unchanged", None),
            report.failed,
        ),
        "owned": tuple(call[-1].get("owned") for call in deliveries),
        "suffix": tuple(call[-1].get("suffix") for call in deliveries),
        "archive-arguments": tuple(archives),
        "validator-arguments": tuple(checks),
    }[observation]
    from fitdocs.connectors.ledger import WellnessDayEntry

    notice = (
        "the connector no longer attributes any wellness field to {p}; "
        "if {p} data stopped reaching the service, import {p}'s own "
        "export instead (see the wellness guide)"
    )
    expected: object = {
        "holder-days": (
            None,
            (WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),),
            (
                WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),
                WellnessDayEntry(_P_DATES[1], "y", _P_HASHES[1]),
                WellnessDayEntry(_P_DATES[2], "a", _P_HASHES[1]),
            ),
        ),
        "holder-pending": (
            None,
            (WellnessPending(_P_PATHS[0], _P_HASHES[0], _P_FORMATS[0], ".json"),),
            (
                WellnessPending(_P_PATHS[0], _P_HASHES[0], _P_FORMATS[0], ".json"),
                WellnessPending(_P_PATHS[1], _P_HASHES[1], _P_FORMATS[1], ".json"),
            ),
        ),
        "holder-origins": (None, ("beta", "zeta"), ("alpha",)),
        "groups": ((_P_DATES[0],), (_P_DATES[1], _P_DATES[2]), (_P_DATES[3],)),
        "identities": tuple(
            tuple(id(day) for day in group) for group in expected_groups
        ),
        "record-identities": (
            (before_record_ids[2],),
            (before_record_ids[3], before_record_ids[1]),
            (before_record_ids[0],),
        ),
        "records": before_records,
        "session": (4, (id(sessions[0]),) * 3) if sessions else (4, ()),
        "settings": (True,) * 4,
        "names": _P_PATHS,
        "bytes": _P_BYTES,
        "days": (
            WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),
            WellnessDayEntry(_P_DATES[1], "y", _P_HASHES[1]),
            WellnessDayEntry(_P_DATES[2], "a", _P_HASHES[1]),
            WellnessDayEntry(_P_DATES[3], "b", _P_HASHES[2]),
        ),
        "pending": tuple(
            WellnessPending(path, sha, fmt, ".json")
            for path, sha, fmt in zip(_P_PATHS, _P_HASHES, _P_FORMATS, strict=True)
        ),
        "coverage": _P_DATES[3] + timedelta(days=4),
        "origins": (),
        "delivered": tuple(
            WellnessDelivered(span, count, path)
            for span, count, path in zip(_P_SPANS, (1, 2, 1), _P_PATHS, strict=True)
        ),
        "notices": tuple(
            PullNote(p, notice.format(p=p)) for p in ("alpha", "beta", "zeta")
        ),
        "counts": (4, 0, False),
        "owned": (
            {},
            {_P_PATHS[0]: _P_HASHES[0]},
            {_P_PATHS[0]: _P_HASHES[0], _P_PATHS[1]: _P_HASHES[1]},
        ),
        "suffix": (".json",) * 3,
        "archive-arguments": tuple(
            (tmp_path, fmt, sha, ".json")
            for fmt, sha in zip(_P_FORMATS, _P_HASHES, strict=True)
        ),
        "validator-arguments": tuple(
            (data, ".json", fmt, origins)
            for data, fmt, origins in zip(_P_BYTES, _P_FORMATS, _P_ORIGINS, strict=True)
        ),
    }[observation]
    assert (was_absent, actual) == (True, expected)


@pytest.mark.parametrize(
    "observation",
    [
        "changed-group",
        "state-transition",
        "changed-report",
        "changed-days",
        "pending",
        "unchanged-report",
        "unchanged-bytes",
        "unchanged-calls",
    ],
)
def test_packaging_revision_retry(tmp_path: Path, observation: str) -> None:
    connector = ScriptedWellnessPuller()
    days = _p_days()
    connector.wellness_listing_script = [_p_listing(days)]
    connector.wellness_package_script = _p_packages()
    _run(tmp_path, connector)
    old_paths = tuple(
        (
            data,
            (tmp_path / "inbox" / path).stat().st_mtime_ns
            if (tmp_path / "inbox" / path).is_file()
            else None,
        )
        for path, data in zip(_P_PATHS, _P_BYTES, strict=True)
    )
    changed = replace(days[1], revision="A-new", record={"value": None})
    newer = (days[0], changed, days[2], days[3])
    data = b'{"new-revision": false}\n'
    sha = hashlib.sha256(data).hexdigest()
    path = f"src/wellness-{_P_DATES[2]}_{_P_DATES[2]}.json"
    before = _p_loaded(tmp_path)
    connector.wellness_listing_script = [_p_listing(newer), _p_listing(newer)]
    connector.wellness_package_script = [
        WellnessPackage(data, ".json", "changed-3", frozenset({"new"})),
        *_p_packages(),
        *_p_packages(),
    ]
    result = _run(tmp_path, connector).instances[0].wellness
    after = _p_loaded(tmp_path)
    ledger_path = layout.connector_ledger_path(tmp_path, "src")
    ledger_before = _snapshot(ledger_path) if ledger_path.is_file() else None
    unchanged = _run(tmp_path, connector).instances[0].wellness
    from fitdocs.connectors.ledger import WellnessDayEntry

    actual = {
        "state-transition": before != after,
        "changed-group": connector.wellness_package_calls[3:],
        "changed-report": result,
        "changed-days": _p_projection(after, "days"),
        "pending": _p_projection(after, "pending"),
        "unchanged-report": unchanged,
        "unchanged-bytes": (
            _snapshot(ledger_path) if ledger_path.is_file() else None,
            tuple(
                _snapshot(tmp_path / "inbox" / p)
                if (tmp_path / "inbox" / p).is_file()
                else None
                for p in _P_PATHS
            ),
            (tmp_path / "inbox" / path).read_bytes()
            if (tmp_path / "inbox" / path).is_file()
            else None,
        ),
        "unchanged-calls": connector.calls,
    }[observation]
    expected = {
        "state-transition": True,
        "changed-group": [(changed,)],
        "changed-report": WellnessPullReport(
            4,
            3,
            (WellnessDelivered(f"{_P_DATES[2]}..{_P_DATES[2]}", 1, path),),
            (),
            (),
            (),
            (),
            None,
        ),
        "changed-days": (
            WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),
            WellnessDayEntry(_P_DATES[1], "y", _P_HASHES[1]),
            WellnessDayEntry(_P_DATES[2], "A-new", sha),
            WellnessDayEntry(_P_DATES[3], "b", _P_HASHES[2]),
        ),
        "pending": tuple(
            sorted(
                [
                    *(
                        WellnessPending(p, s, f, ".json")
                        for p, s, f in zip(_P_PATHS, _P_HASHES, _P_FORMATS, strict=True)
                    ),
                    WellnessPending(path, sha, "changed-3", ".json"),
                ],
                key=lambda p: p.path,
            )
        ),
        "unchanged-report": WellnessPullReport(4, 4, (), (), (), (), (), None),
        "unchanged-bytes": (ledger_before, old_paths, data),
        "unchanged-calls": [
            "list_wellness",
            "package_wellness",
            "package_wellness",
            "package_wellness",
            "list_wellness",
            "package_wellness",
            "list_wellness",
        ],
    }[observation]
    assert actual == expected


_P_BAD_PACKAGES: tuple[tuple[bytes, str, str, frozenset[str], str], ...] = (
    (
        b"{}",
        ".fit",
        "ok",
        frozenset(),
        "No wellness check is available for extension '.fit'.",
    ),
    (
        b"{}",
        ".csv",
        "ok",
        frozenset(),
        "No wellness check is available for extension '.csv'.",
    ),
    (b"", ".json", "ok", frozenset(), "Wellness package is empty."),
    (b"[1,2,3]", ".json", "ok", frozenset(), "Wellness JSON package exceeds 6 bytes."),
    (
        b"{}{}",
        ".json",
        "ok",
        frozenset(),
        "Wellness package is not one well-formed UTF-8 JSON document.",
    ),
    (
        b"\xef\xbb\xbf{}",
        ".json",
        "ok",
        frozenset(),
        "Wellness package is not one well-formed UTF-8 JSON document.",
    ),
    (
        b"{}",
        ".json",
        "BAD",
        frozenset(),
        "Wellness format 'BAD' is not a lowercase slug.",
    ),
    (
        b"{}",
        ".json",
        "ok",
        frozenset({"BAD"}),
        "Wellness origin 'BAD' is not a lowercase slug.",
    ),
)


@pytest.mark.parametrize("data,suffix,fmt,origins,reason", _P_BAD_PACKAGES)
@pytest.mark.parametrize("observation", ["report", "state", "files"])
def test_packaging_refusals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
    suffix: str,
    fmt: str,
    origins: frozenset[str],
    reason: str,
    observation: str,
) -> None:
    from fitdocs.connectors import delivery as delivery_mod

    monkeypatch.setattr(delivery_mod, "MAX_WELLNESS_JSON_BYTES", 6)
    state = WellnessLedger(through=_P_DATES[0] - timedelta(days=3), origins=("prior",))
    path = _seed(tmp_path, state, activity=True)
    before = _snapshot(path)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing((_p_days()[2],))]
    connector.wellness_package_script = [WellnessPackage(data, suffix, fmt, origins)]
    report = _run(tmp_path, connector)
    result = report.instances[0].wellness
    actual = {
        "report": (result, report.failed),
        "state": (_p_loaded(tmp_path), _snapshot(path)),
        "files": tuple((tmp_path / "inbox").rglob("*")),
    }[observation]
    expected = {
        "report": (
            WellnessPullReport(
                1, 0, (), (), (), (PullNote(_P_SPANS[0], reason),), (), None
            ),
            True,
        ),
        "state": (state, before),
        "files": (),
    }[observation]
    assert (connector.wellness_package_calls, actual) == ([(_p_days()[2],)], expected)


@pytest.mark.parametrize(
    "data",
    [b"null", b"false", b"0", b'""', b"[]", b"{}", b'[1, {"v": null}]', b'"synthetic"'],
)
@pytest.mark.parametrize(
    "fmt,origins,suffix",
    [
        ("a", frozenset(), ".json"),
        ("7", frozenset({"z"}), ".json"),
        ("f-2", frozenset({"a-1", "8"}), ".json"),
    ],
)
@pytest.mark.parametrize("observation", ["bytes", "metadata", "suffix"])
def test_packaging_native_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
    fmt: str,
    origins: frozenset[str],
    suffix: str,
    observation: str,
) -> None:
    from fitdocs.connectors import delivery as delivery_mod

    monkeypatch.setattr(
        delivery_mod,
        "WELLNESS_CHECKS",
        {".json": delivery_mod._json_problem, ".data": delivery_mod._json_problem},
    )
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing((_p_days()[2],))]
    connector.wellness_package_script = [WellnessPackage(data, suffix, fmt, origins)]
    original = delivery_mod.deliver
    calls: list[dict[str, Any]] = []

    def deliver(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(pull_mod, "deliver", deliver)
    _run(tmp_path, connector)
    path = f"src/wellness-{_P_DATES[0]}_{_P_DATES[0]}{suffix}"
    state = _p_loaded(tmp_path)
    actual = {
        "bytes": (tmp_path / "inbox" / path).read_bytes()
        if (tmp_path / "inbox" / path).is_file()
        else None,
        "metadata": (_p_projection(state, "pending"), _p_projection(state, "origins")),
        "suffix": tuple(call.get("suffix") for call in calls),
    }[observation]
    expected = {
        "bytes": data,
        "metadata": (
            (WellnessPending(path, hashlib.sha256(data).hexdigest(), fmt, suffix),),
            tuple(sorted(origins)),
        ),
        "suffix": (suffix,),
    }[observation]
    assert actual == expected


@pytest.mark.parametrize(
    "role",
    [
        "archive",
        "pending",
        "pending-collision",
        "current",
        "collision",
        "other-format",
        "other-suffix",
        "fit-archive",
    ],
)
@pytest.mark.parametrize(
    "observation",
    ["report", "days", "pending", "origins", "preserved", "archive-arguments"],
)
def test_packaging_held_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str, observation: str
) -> None:
    from fitdocs.connectors import delivery as delivery_mod
    from fitdocs.connectors.ledger import WellnessDayEntry

    data = b'{"synthetic-collision": 17312}\n'
    old_data = b'{"synthetic-collision": 4681}\n'
    sha = hashlib.sha256(data).hexdigest()
    old_sha = hashlib.sha256(old_data).hexdigest()
    fmt = "synthetic-8"
    days = _p_days()
    chosen = days if role == "current" else (days[2],)
    original = WellnessLedger(
        through=_P_DATES[0] - timedelta(days=2), origins=("prior",)
    )
    preserved: list[Path] = []
    if role in {"pending", "pending-collision"}:
        old_path = tmp_path / "inbox" / "src" / "refused.json"
        old_path.parent.mkdir(parents=True)
        old_path.write_bytes(old_data if role == "pending-collision" else data)
        preserved.append(old_path)
        original = original.with_pending(
            WellnessPending(
                "src/refused.json",
                old_sha if role == "pending-collision" else sha,
                "other-9",
                ".json",
            )
        )
    elif role != "current":
        path = (
            layout.archive_path(tmp_path, sha)
            if role == "fit-archive"
            else layout.wellness_archive_path(
                tmp_path,
                "other" if role == "other-format" else fmt,
                old_sha if role == "collision" else sha,
                ".csv" if role == "other-suffix" else ".json",
            )
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(old_data if role == "collision" else data)
        preserved.append(path)
    _seed(tmp_path, original, activity=True)
    before_files = tuple(_snapshot(path) for path in preserved)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing(chosen)]
    connector.wellness_package_script = [
        WellnessPackage(data, ".json", fmt, frozenset({"new"}))
    ] * 3
    archive_calls: list[tuple[object, ...]] = []

    def archived(*args: Any) -> bool:
        archive_calls.append(args)
        return delivery_mod.wellness_archived(*args)

    monkeypatch.setattr(pull_mod, "wellness_archived", archived, raising=False)
    report = _run(tmp_path, connector)
    result = report.instances[0].wellness
    state = _p_loaded(tmp_path)
    held = role in {"archive", "pending", "current"}
    delivered = (
        ()
        if role in {"archive", "pending"}
        else (WellnessDelivered(_P_SPANS[0], 1, _P_PATHS[0]),)
    )
    held_spans = (
        (_P_SPANS[1], _P_SPANS[2])
        if role == "current"
        else ((_P_SPANS[0],) if held else ())
    )
    new_pending = tuple(
        sorted(
            (
                *original.pending,
                *(
                    (WellnessPending(_P_PATHS[0], sha, fmt, ".json"),)
                    if delivered
                    else ()
                ),
            ),
            key=lambda p: p.path,
        )
    )
    old_notice = PullNote(
        "prior",
        "the connector no longer attributes any wellness field to prior; "
        "if prior data stopped reaching the service, import prior's own "
        "export instead (see the wellness guide)",
    )
    actual = {
        "report": (result, report.failed),
        "days": _p_projection(state, "days"),
        "pending": _p_projection(state, "pending"),
        "origins": _p_projection(state, "origins"),
        "preserved": (
            tuple(_snapshot(path) for path in preserved),
            tuple(
                (tmp_path / "inbox" / path).read_bytes()
                for path in _P_PATHS
                if (tmp_path / "inbox" / path).is_file()
            ),
        ),
        "archive-arguments": tuple(archive_calls),
    }[observation]
    expected = {
        "report": (
            WellnessPullReport(
                len(chosen),
                0,
                delivered,
                (),
                held_spans,
                (),
                (old_notice,) if delivered else (),
                None,
            ),
            False,
        ),
        "days": (WellnessDayEntry(_P_DATES[0], "z", sha),)
        + (
            (
                WellnessDayEntry(_P_DATES[1], "y", sha),
                WellnessDayEntry(_P_DATES[2], "a", sha),
                WellnessDayEntry(_P_DATES[3], "b", sha),
            )
            if role == "current"
            else ()
        ),
        "pending": new_pending,
        "origins": ("new",) if delivered else ("prior",),
        "preserved": (before_files, (data,) if delivered else ()),
        "archive-arguments": ((tmp_path, fmt, sha, ".json"),)
        * (3 if role == "current" else 1),
    }[observation]
    assert (sha != old_sha, sha[:8], old_sha[:8], actual) == (
        True,
        "684793b8",
        "684793b8",
        expected,
    )


_P_FAILURES = (
    Exception("package " + _KEY),
    ValueError("package " + _KEY),
    RuntimeError("package " + _KEY),
    ConnectorError("package " + _KEY),
    *(
        cls(kind, "package " + _KEY)
        for cls in (AuthFailure, _Round3AuthFailure)
        for kind in AuthFailureKind
    ),
)


@pytest.mark.parametrize("failure", _P_FAILURES)
@pytest.mark.parametrize("position", [0, 1])
@pytest.mark.parametrize(
    "observation",
    [
        "error",
        "failed",
        "calls",
        "days",
        "pending",
        "mark",
        "next",
        "failed-flag",
        "bytes",
        "origins",
    ],
)
def test_packaging_failures(
    tmp_path: Path, failure: Exception, position: int, observation: str
) -> None:
    from fitdocs.connectors.ledger import WellnessDayEntry

    connector = ScriptedWellnessPuller()
    days = _p_days()
    connector.wellness_listing_script = [_p_listing(days), _p_listing(())]
    packages: list[WellnessPackage | BaseException] = list(_p_packages())
    packages[position] = failure
    connector.wellness_package_script = packages
    state = WellnessLedger(through=_P_DATES[0] - timedelta(days=2), origins=("prior",))
    _seed(tmp_path, state, activity=True)
    redactor = Redactor()
    redactor.add(_KEY)
    report = _run(
        tmp_path,
        connector,
        instances=[_instance(connector), _instance(connector, name="next")],
        redactor=redactor,
    )
    result = report.instances[0].wellness
    terminal = isinstance(failure, (AuthFailure, ConnectorError))
    successful = tuple(
        index
        for index in range(3)
        if index != position and (not terminal or index < position)
    )
    entry_groups = (
        (WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),),
        (
            WellnessDayEntry(_P_DATES[1], "y", _P_HASHES[1]),
            WellnessDayEntry(_P_DATES[2], "a", _P_HASHES[1]),
        ),
        (WellnessDayEntry(_P_DATES[3], "b", _P_HASHES[2]),),
    )
    detail = f"{type(failure).__name__}: package {REDACTED}"
    if isinstance(failure, AuthFailure):
        detail += " " + next_step(failure.kind, name="src", retry_after_s=None)
    loaded = _p_loaded(tmp_path)
    actual = {
        "bytes": tuple(
            (path, (tmp_path / "inbox" / path).read_bytes())
            for path in _P_PATHS
            if (tmp_path / "inbox" / path).is_file()
        ),
        "origins": _p_projection(loaded, "origins"),
        "error": getattr(result, "error", None),
        "failed": getattr(result, "failed", None),
        "calls": connector.calls,
        "days": _p_projection(loaded, "days"),
        "pending": _p_projection(loaded, "pending"),
        "mark": _p_projection(loaded, "through"),
        "next": tuple(
            item.wellness for item in report.instances if item.name == "next"
        ),
        "failed-flag": report.failed,
    }[observation]
    expected = {
        "bytes": tuple((_P_PATHS[index], _P_BYTES[index]) for index in successful),
        "origins": tuple(sorted(_P_ORIGINS[successful[-1]]))
        if successful
        else ("prior",),
        "error": PullNote("src", detail) if terminal else None,
        "failed": () if terminal else (PullNote(_P_SPANS[position], detail),),
        "calls": ["list_wellness"]
        + ["package_wellness"] * (position + 1 if terminal else 3)
        + ["list_wellness"],
        "days": tuple(entry for index in successful for entry in entry_groups[index]),
        "pending": tuple(
            WellnessPending(
                _P_PATHS[index], _P_HASHES[index], _P_FORMATS[index], ".json"
            )
            for index in successful
        ),
        "mark": state.through,
        "next": (WellnessPullReport(0, 0, (), (), (), (), (), None),),
        "failed-flag": True,
    }[observation]
    assert actual == expected


@pytest.mark.parametrize("kind", [KeyboardInterrupt, SystemExit, GeneratorExit])
@pytest.mark.parametrize(
    "observation",
    ["propagation", "calls", "days", "pending", "mark", "origins", "bytes", "legacy"],
)
def test_packaging_interruption(
    tmp_path: Path, kind: type[BaseException], observation: str
) -> None:
    from fitdocs.connectors.ledger import WellnessDayEntry

    state = WellnessLedger(through=_P_DATES[0] - timedelta(days=2), origins=("prior",))
    _seed(tmp_path, state, activity=True)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing(_p_days())]
    connector.wellness_package_script = [
        _p_packages()[0],
        kind("synthetic stop"),
        _p_packages()[2],
    ]
    caught: BaseException | None = None
    try:
        _run(tmp_path, connector)
    except BaseException as exc:
        caught = exc
    ledger = load_ledger(tmp_path, "src", connector_id=connector.connector_id)
    path = tmp_path / "inbox" / _P_PATHS[0]
    actual = {
        "propagation": type(caught),
        "calls": connector.calls,
        "days": _p_projection(ledger.wellness, "days"),
        "pending": _p_projection(ledger.wellness, "pending"),
        "mark": _p_projection(ledger.wellness, "through"),
        "origins": _p_projection(ledger.wellness, "origins"),
        "bytes": path.read_bytes() if path.is_file() else None,
        "legacy": ledger.entries,
    }[observation]
    expected = {
        "propagation": kind,
        "calls": ["list_wellness", "package_wellness", "package_wellness"],
        "days": (WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),),
        "pending": (
            WellnessPending(_P_PATHS[0], _P_HASHES[0], _P_FORMATS[0], ".json"),
        ),
        "mark": state.through,
        "origins": ("beta", "zeta"),
        "bytes": _P_BYTES[0],
        "legacy": (
            LedgerEntry("legacy", Outcome.SKIPPED, revision="old", detail="manual"),
        ),
    }[observation]
    assert actual == expected


@pytest.mark.parametrize(
    "observation", ["failed", "days", "pending", "mark", "preserved"]
)
def test_packaging_delivery_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observation: str
) -> None:
    from fitdocs.connectors.delivery import deliver as original
    from fitdocs.connectors.ledger import WellnessDayEntry

    state = WellnessLedger(through=_P_DATES[0] - timedelta(days=2), origins=("prior",))
    _seed(tmp_path, state, activity=True)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing(_p_days())]
    connector.wellness_package_script = _p_packages()
    calls: list[str] = []

    def deliver(*args: Any, **kwargs: Any) -> Any:
        calls.append(args[2])
        if len(calls) == 2:
            raise OSError("write " + _KEY)
        return original(*args, **kwargs)

    monkeypatch.setattr(pull_mod, "deliver", deliver)
    redactor = Redactor()
    redactor.add(_KEY)
    report = _run(tmp_path, connector, redactor=redactor)
    result = report.instances[0].wellness
    loaded = _p_loaded(tmp_path)
    actual = {
        "failed": (getattr(result, "failed", None), report.failed, calls),
        "days": _p_projection(loaded, "days"),
        "pending": _p_projection(loaded, "pending"),
        "mark": _p_projection(loaded, "through"),
        "preserved": (tmp_path / "inbox" / _P_PATHS[1]).exists(),
    }[observation]
    expected = {
        "failed": (
            (PullNote(_P_SPANS[1], f"OSError: write {REDACTED}"),),
            True,
            [Path(p).name for p in _P_PATHS],
        ),
        "days": (
            WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),
            WellnessDayEntry(_P_DATES[3], "b", _P_HASHES[2]),
        ),
        "pending": (
            WellnessPending(_P_PATHS[0], _P_HASHES[0], _P_FORMATS[0], ".json"),
            WellnessPending(_P_PATHS[2], _P_HASHES[2], _P_FORMATS[2], ".json"),
        ),
        "mark": state.through,
        "preserved": False,
    }[observation]
    assert actual == expected


@pytest.mark.parametrize(
    "prior,current",
    [
        ((), frozenset()),
        ((), frozenset({"new"})),
        (("lost",), frozenset()),
        (("kept",), frozenset({"kept"})),
        (("a", "z"), frozenset({"x", "y"})),
        (("a", "kept", "z"), frozenset({"kept", "new"})),
        (("a", "b", "c"), frozenset({"a", "b"})),
    ],
)
@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("observation", ["origins", "notices", "failed-flag"])
def test_packaging_origins(
    tmp_path: Path,
    prior: tuple[str, ...],
    current: frozenset[str],
    held: bool,
    observation: str,
) -> None:
    _seed(tmp_path, WellnessLedger(origins=prior))
    if held:
        path = layout.wellness_archive_path(tmp_path, "meta", _P_HASHES[0], ".json")
        path.parent.mkdir(parents=True)
        path.write_bytes(_P_BYTES[0])
    connector = ScriptedWellnessPuller()
    day = WellnessDay(_P_DATES[0], None, {"origin": "misleading", "weight": None})
    connector.wellness_listing_script = [_p_listing((day,))]
    connector.wellness_package_script = [
        WellnessPackage(_P_BYTES[0], ".json", "meta", current)
    ]
    redactor = Redactor()
    redactor.add("lost")
    report = _run(tmp_path, connector, redactor=redactor)
    actual = {
        "origins": _p_projection(_p_loaded(tmp_path), "origins"),
        "notices": getattr(report.instances[0].wellness, "notices", None),
        "failed-flag": report.failed,
    }[observation]

    def message(platform: str) -> str:
        token = REDACTED if platform == "lost" else platform
        return (
            f"the connector no longer attributes any wellness field to {token}; "
            f"if {token} data stopped reaching the service, import {token}'s own "
            "export instead (see the wellness guide)"
        )

    expected = {
        "origins": prior if held else tuple(sorted(current)),
        "notices": ()
        if held
        else tuple(PullNote(p, message(p)) for p in sorted(set(prior) - current)),
        "failed-flag": False,
    }[observation]
    assert actual == expected


@pytest.mark.parametrize(
    "role", ["different", "identical-unowned", "sha8-taken", "owned-other"]
)
@pytest.mark.parametrize("suffix", [".json", ".data"])
@pytest.mark.parametrize("observation", ["name", "preserved", "owned", "suffix"])
def test_packaging_occupied_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    suffix: str,
    observation: str,
) -> None:
    from fitdocs.connectors import delivery as delivery_mod

    monkeypatch.setattr(
        delivery_mod,
        "WELLNESS_CHECKS",
        {".json": delivery_mod._json_problem, ".data": delivery_mod._json_problem},
    )
    data = _P_BYTES[0]
    sha = _P_HASHES[0]
    primary = f"src/wellness-{_P_DATES[0]}_{_P_DATES[0]}{suffix}"
    collision = f"src/wellness-{_P_DATES[0]}_{_P_DATES[0]}-{sha[:8]}{suffix}"
    occupied = tmp_path / "inbox" / primary
    occupied.parent.mkdir(parents=True)
    old_data = data if role == "identical-unowned" else b'{"manual": 997}\n'
    occupied.write_bytes(old_data)
    preserved = [occupied]
    if role == "sha8-taken":
        extra = tmp_path / "inbox" / collision
        extra.write_bytes(b'{"manual": 53}\n')
        preserved.append(extra)
    state = WellnessLedger()
    if role == "owned-other":
        state = state.with_pending(
            WellnessPending(
                primary, hashlib.sha256(old_data).hexdigest(), "manual", suffix
            )
        )
    _seed(tmp_path, state)
    before = tuple(_snapshot(path) for path in preserved)
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing((_p_days()[2],))]
    connector.wellness_package_script = [
        WellnessPackage(data, suffix, "new", frozenset())
    ]
    original = delivery_mod.deliver
    calls: list[dict[str, Any]] = []

    def deliver(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(pull_mod, "deliver", deliver)
    result = _run(tmp_path, connector).instances[0].wellness
    actual = {
        "name": getattr(result, "delivered", None),
        "preserved": tuple(_snapshot(path) for path in preserved),
        "owned": tuple(call.get("owned") for call in calls),
        "suffix": tuple(call.get("suffix") for call in calls),
    }[observation]
    expected_path = (
        f"src/wellness-{_P_DATES[0]}_{_P_DATES[0]}-{sha[:8]}-2{suffix}"
        if role == "sha8-taken"
        else collision
    )
    expected = {
        "name": (WellnessDelivered(_P_SPANS[0], 1, expected_path),),
        "preserved": before,
        "owned": (
            {primary: hashlib.sha256(old_data).hexdigest()}
            if role == "owned-other"
            else {},
        ),
        "suffix": (suffix,),
    }[observation]
    assert actual == expected


@pytest.mark.parametrize("mode", ["none", "overlap", "adjacent", "gap"])
@pytest.mark.parametrize(
    "outcome", ["delivered", "held", "ordinary", "terminal", "invalid"]
)
@pytest.mark.parametrize("observation", ["mark", "days"])
def test_packaging_coverage(
    tmp_path: Path, mode: str, outcome: str, observation: str
) -> None:
    from fitdocs.connectors.ledger import WellnessDayEntry

    start = _P_DATES[0]
    prior = {
        "none": None,
        "overlap": start,
        "adjacent": start - timedelta(days=1),
        "gap": start - timedelta(days=2),
    }[mode]
    _seed(tmp_path, WellnessLedger(through=prior))
    connector = ScriptedWellnessPuller()
    day = _p_days()[2]
    days = (day, replace(day, revision="")) if outcome == "invalid" else (day,)
    connector.wellness_listing_script = [
        WellnessListing(start, start + timedelta(days=5), days)
    ]
    connector.wellness_package_script = [
        ValueError("ordinary")
        if outcome == "ordinary"
        else ConnectorError("terminal")
        if outcome == "terminal"
        else _p_packages()[0]
    ]
    if outcome == "held":
        path = layout.wellness_archive_path(
            tmp_path, _P_FORMATS[0], _P_HASHES[0], ".json"
        )
        path.parent.mkdir(parents=True)
        path.write_bytes(_P_BYTES[0])
    _run(tmp_path, connector)
    state = _p_loaded(tmp_path)
    actual = {
        "mark": _p_projection(state, "through"),
        "days": _p_projection(state, "days"),
    }[observation]
    expected = {
        "mark": start + timedelta(days=5)
        if outcome in {"delivered", "held"} and mode != "gap"
        else prior,
        "days": ()
        if outcome in {"ordinary", "terminal"}
        else (WellnessDayEntry(start, "z", _P_HASHES[0]),),
    }[observation]
    assert actual == expected


@pytest.mark.parametrize(
    "observation", ["failed", "notices", "held", "delivered", "counts", "mark"]
)
def test_packaging_mixed_sorted_channels(tmp_path: Path, observation: str) -> None:
    connector = ScriptedWellnessPuller()
    days = _p_days()
    extra = WellnessDay(date(_P_YEAR + 2, 4, 1), "v", {"value": None})
    invalid = WellnessDay(_P_DATES[1] - timedelta(days=1), "", {})
    connector.wellness_listing_script = [_p_listing((extra, invalid, *days))]
    connector.wellness_package_script = [
        ValueError("bad early year"),
        _p_packages()[1],
        _p_packages()[2],
        WellnessPackage(b'{"fourth": 251}', ".json", "fourth", frozenset({"beta"})),
    ]
    original = WellnessLedger(
        through=_P_DATES[0] - timedelta(days=1), origins=("gamma", "zeta")
    )
    _seed(tmp_path, original)
    archive = layout.wellness_archive_path(
        tmp_path, _P_FORMATS[2], _P_HASHES[2], ".json"
    )
    archive.parent.mkdir(parents=True)
    archive.write_bytes(_P_BYTES[2])
    report = _run(tmp_path, connector)
    result = report.instances[0].wellness
    extra_path = f"src/wellness-{extra.day}_{extra.day}.json"
    actual = {
        "failed": getattr(result, "failed", None),
        "notices": getattr(result, "notices", None),
        "held": getattr(result, "held", None),
        "delivered": getattr(result, "delivered", None),
        "counts": (
            getattr(result, "listed", None),
            getattr(result, "unchanged", None),
            report.failed,
        ),
        "mark": _p_projection(_p_loaded(tmp_path), "through"),
    }[observation]

    def note(p: str) -> PullNote:
        return PullNote(
            p,
            f"the connector no longer attributes any wellness field to {p}; "
            f"if {p} data stopped reaching the service, import {p}'s own "
            "export instead (see the wellness guide)",
        )

    expected = {
        "failed": (
            PullNote(_P_SPANS[0], "ValueError: bad early year"),
            PullNote(
                invalid.day.isoformat(),
                "wellness revision must contain 1 to 512 characters",
            ),
        ),
        "notices": (note("alpha"), note("gamma"), note("zeta")),
        "held": (_P_SPANS[2],),
        "delivered": (
            WellnessDelivered(_P_SPANS[1], 2, _P_PATHS[1]),
            WellnessDelivered(f"{extra.day}..{extra.day}", 1, extra_path),
        ),
        "counts": (6, 0, True),
        "mark": original.through,
    }[observation]
    assert actual == expected


@pytest.mark.parametrize("suffix", [".JSON", ".json"])
def test_packaging_hypothetical_verbatim_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    from fitdocs.connectors.delivery import DeliveryResult
    from fitdocs.connectors.http import CallMode, HttpClient

    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing((_p_days()[2],))]
    connector.wellness_package_script = [
        WellnessPackage(_P_BYTES[0], suffix, "synthetic", frozenset())
    ]
    calls: list[tuple[object, ...]] = []

    def deliver(*args: Any, **kwargs: Any) -> DeliveryResult:
        calls.append((args[2], kwargs.get("suffix")))
        return DeliveryResult(f"src/hypothetical{suffix}", False)

    monkeypatch.setattr(pull_mod, "wellness_package_problem", lambda *args: None)
    monkeypatch.setattr(pull_mod, "deliver", deliver)
    redactor = Redactor()
    session = ConnectorSession(
        instance="src",
        settings=None,
        http=HttpClient(
            FakeTransport([]),
            mode=CallMode.DATA,
            redactor=redactor,
            sleep=lambda _: None,
        ),
        credentials=resolve_credentials("src", connector, None, {}, redactor),
        data_root=tmp_path,
        now=lambda: _NOW,
        sleep=lambda _: None,
        redactor=redactor,
    )
    holder = pull_mod._LedgerHolder(Ledger(connector.connector_id, None, ()))
    pull_mod._pull_wellness(
        holder,
        instance=_instance(connector),
        session=session,
        options=PullOptions(None, False),
        data_root=tmp_path,
        inbox=tmp_path / "inbox",
        redactor=redactor,
    )
    assert calls == [(f"wellness-{_P_DATES[0]}_{_P_DATES[0]}{suffix}", suffix)]


def test_packaging_uppercase_suffix_is_refused(tmp_path: Path) -> None:
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing((_p_days()[2],))]
    connector.wellness_package_script = [
        WellnessPackage(b"{}", ".JSON", "valid", frozenset())
    ]
    report = _run(tmp_path, connector)
    assert (
        report.instances[0].wellness,
        _p_loaded(tmp_path),
        tuple((tmp_path / "inbox").rglob("*")),
    ) == (
        WellnessPullReport(
            1,
            0,
            (),
            (),
            (),
            (
                PullNote(
                    _P_SPANS[0], "No wellness check is available for extension '.JSON'."
                ),
            ),
            (),
            None,
        ),
        None,
        (),
    )


@pytest.mark.parametrize(
    "record", [None, False, 0, "opaque", [], {}, {"value": False}, object()]
)
def test_packaging_opaque_record_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record: object
) -> None:
    connector = ScriptedWellnessPuller()
    day = WellnessDay(_P_DATES[0], "opaque-revision", record)
    original_id = id(record)
    connector.wellness_listing_script = [_p_listing((day,))]
    connector.wellness_package_script = [_p_packages()[0]]
    original = connector.package_wellness
    seen: list[int] = []

    def package(
        session: ConnectorSession, group: tuple[WellnessDay, ...]
    ) -> WellnessPackage:
        seen.extend(id(item.record) for item in group)
        return original(session, group)

    monkeypatch.setattr(connector, "package_wellness", package)
    result = _run(tmp_path, connector).instances[0].wellness
    assert (seen, id(day.record), getattr(result, "delivered", None)) == (
        [original_id],
        original_id,
        (WellnessDelivered(_P_SPANS[0], 1, _P_PATHS[0]),),
    )


def test_packaging_attribution_constant_type() -> None:
    from typing import Final

    assert get_type_hints(pull_mod).get("ATTRIBUTION_DROPPED") == Final[str]


@pytest.mark.parametrize(
    "kind", [ConnectorError, KeyboardInterrupt, SystemExit, GeneratorExit]
)
def test_packaging_held_partial_exit(tmp_path: Path, kind: type[BaseException]) -> None:
    from fitdocs.connectors.ledger import WellnessDayEntry

    through = _P_DATES[0] - timedelta(days=1)
    _seed(tmp_path, WellnessLedger(through=through, origins=("prior",)), activity=True)
    archived = layout.wellness_archive_path(
        tmp_path, _P_FORMATS[0], _P_HASHES[0], ".json"
    )
    archived.parent.mkdir(parents=True)
    archived.write_bytes(_P_BYTES[0])
    archive_mtime = archived.stat().st_mtime_ns
    connector = ScriptedWellnessPuller()
    connector.wellness_listing_script = [_p_listing(_p_days())]
    connector.wellness_package_script = [
        _p_packages()[0],
        kind("synthetic held exit"),
        _p_packages()[2],
    ]
    caught: BaseException | None = None
    result: WellnessPullReport | None = None
    try:
        result = _run(tmp_path, connector).instances[0].wellness
    except BaseException as exc:
        caught = exc
    ledger = load_ledger(tmp_path, "src", connector_id=connector.connector_id)
    expected_ledger = Ledger(
        connector_id="scripted-wellness-puller",
        watermark=None,
        entries=(
            LedgerEntry("legacy", Outcome.SKIPPED, revision="old", detail="manual"),
        ),
        wellness=WellnessLedger(
            through=through,
            origins=("prior",),
            days=(WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),),
            pending=(),
        ),
    )
    expected_report = (
        WellnessPullReport(
            4,
            0,
            (),
            (),
            (_P_SPANS[0],),
            (),
            (),
            PullNote("src", "ConnectorError: synthetic held exit"),
        )
        if kind is ConnectorError
        else None
    )
    assert (
        type(caught),
        ledger,
        result,
        connector.calls,
        _snapshot(archived),
        tuple((tmp_path / "inbox").rglob("*")),
    ) == (
        type(None) if kind is ConnectorError else kind,
        expected_ledger,
        expected_report,
        ["list_wellness", "package_wellness", "package_wellness"],
        (_P_BYTES[0], archive_mtime),
        (),
    )


class _Round2PackagingError(ConnectorError):
    pass


@pytest.mark.parametrize("subtype", ["native", "derived"])
@pytest.mark.parametrize("position", [0, 1])
@pytest.mark.parametrize(
    "observation",
    [
        "error",
        "failed",
        "calls",
        "next",
        "mark",
        "days",
        "pending",
        "bytes",
        "origins",
        "failed-flag",
    ],
)
def test_round2_packaging_connector_error_subtypes(
    tmp_path: Path, subtype: str, position: int, observation: str
) -> None:
    from fitdocs.connectors.errors import NotConnectedError
    from fitdocs.connectors.ledger import WellnessDayEntry

    failure_type = NotConnectedError if subtype == "native" else _Round2PackagingError
    failure = failure_type(f"synthetic package {_KEY}; run `fitdocs connect src` again")
    connector = ScriptedWellnessPuller()
    through = _P_DATES[0] - timedelta(days=1)
    initial = WellnessLedger(through=through, origins=("seed-origin",))
    _seed(tmp_path, initial, activity=True)
    initially_empty = (
        _p_loaded(tmp_path) == initial
        and connector.wellness_package_calls == []
        and not (tmp_path / "inbox").exists()
    )
    connector.wellness_listing_script = [_p_listing(_p_days()), _p_listing(())]
    packages = _p_packages()
    packages[position] = failure
    connector.wellness_package_script = packages
    redactor = Redactor()
    redactor.add(_KEY)
    report = _run(
        tmp_path,
        connector,
        instances=[_instance(connector), _instance(connector, name="next")],
        redactor=redactor,
    )
    result = report.instances[0].wellness
    state = _p_loaded(tmp_path)
    actual = {
        "error": getattr(result, "error", None),
        "failed": getattr(result, "failed", None),
        "calls": connector.calls,
        "next": tuple(
            item.wellness for item in report.instances if item.name == "next"
        ),
        "mark": _p_projection(state, "through"),
        "days": _p_projection(state, "days"),
        "pending": _p_projection(state, "pending"),
        "bytes": tuple(
            (path, (tmp_path / "inbox" / path).read_bytes())
            for path in _P_PATHS
            if (tmp_path / "inbox" / path).is_file()
        ),
        "origins": _p_projection(state, "origins"),
        "failed-flag": report.failed,
    }[observation]
    expected: object = {
        "error": PullNote(
            "src",
            f"{failure_type.__name__}: synthetic package {REDACTED}; "
            "run `fitdocs connect src` again",
        ),
        "failed": (),
        "calls": ["list_wellness"]
        + ["package_wellness"] * (position + 1)
        + ["list_wellness"],
        "next": (WellnessPullReport(0, 0, (), (), (), (), (), None),),
        "mark": through,
        "days": ()
        if position == 0
        else (WellnessDayEntry(_P_DATES[0], "z", _P_HASHES[0]),),
        "pending": ()
        if position == 0
        else (WellnessPending(_P_PATHS[0], _P_HASHES[0], _P_FORMATS[0], ".json"),),
        "bytes": () if position == 0 else ((_P_PATHS[0], _P_BYTES[0]),),
        "origins": ("seed-origin",) if position == 0 else ("beta", "zeta"),
        "failed-flag": True,
    }[observation]
    reached = tuple(
        tuple(day.day for day in group)
        for group in connector.wellness_package_calls[: position + 1]
    )
    expected_reached = ((_P_DATES[0],), (_P_DATES[1], _P_DATES[2]))[: position + 1]
    assert (actual, initially_empty, connector.auth_style, reached) == (
        expected,
        True,
        AuthStyle.NONE,
        expected_reached,
    )
