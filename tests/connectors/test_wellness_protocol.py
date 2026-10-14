"""The wellness-pull protocol, registry rule and published declarations."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from fitdocs.connectors.errors import AuthFailure, AuthFailureKind, ConnectorError
from fitdocs.connectors.http import CallMode, HttpClient, HttpResponse
from fitdocs.connectors.intervals import API_BASE
from fitdocs.connectors.protocol import (
    CAPABILITIES,
    DRIVEN_CAPABILITIES,
    AuthStyle,
    Capability,
    Connector,
    ConnectorSession,
    Fetched,
    Listing,
    RemoteActivity,
    SettingsContext,
    WellnessDay,
    WellnessListing,
    WellnessPackage,
    WellnessPuller,
)
from fitdocs.connectors.registry import (
    InvalidConnectorError,
    UnknownConnectorError,
    get,
    register,
)
from fitdocs.connectors.secrets import Redactor
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedWellnessPuller,
    UnscriptedCall,
)
from tests.fixtures.builder import FIT_TIMESTAMP_BASE


def test_only_activity_and_wellness_pulls_are_driven() -> None:
    assert {capability for capability, info in CAPABILITIES.items() if info.driven} == {
        Capability.PULL_ACTIVITIES,
        Capability.PULL_WELLNESS,
    }
    assert (
        frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})
        == DRIVEN_CAPABILITIES
    )


@pytest.mark.parametrize(
    ("cls", "expected"),
    [
        (
            WellnessDay,
            (("day", "date"), ("revision", "str | None"), ("record", "object")),
        ),
        (
            WellnessListing,
            (
                ("oldest", "date"),
                ("newest", "date"),
                ("days", "tuple[WellnessDay, ...]"),
            ),
        ),
        (
            WellnessPackage,
            (
                ("data", "bytes"),
                ("suffix", "str"),
                ("format", "str"),
                ("origins", "frozenset[str]"),
            ),
        ),
    ],
)
def test_wellness_value_fields(
    cls: type, expected: tuple[tuple[str, str], ...]
) -> None:
    fields = dataclasses.fields(cls)
    assert tuple((field.name, field.type) for field in fields) == expected
    assert cls.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    assert all(
        field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
        for field in fields
    )


def test_day_preserves_absent_revision_and_omits_record_from_repr() -> None:
    day = (
        datetime(1989, 12, 31, tzinfo=UTC) + timedelta(seconds=FIT_TIMESTAMP_BASE)
    ).date()
    record = {"synthetic_marker": "opaque-record-7Q2x9"}
    subject = WellnessDay(day, None, record)
    assert subject.record is record
    assert subject.revision is None
    assert "opaque-record-7Q2x9" not in repr(subject)


@pytest.mark.parametrize(
    ("operation", "signature"),
    [
        (
            "list_wellness",
            "(self, session: 'ConnectorSession', oldest: 'date | None')"
            " -> 'WellnessListing'",
        ),
        (
            "package_wellness",
            "(self, session: 'ConnectorSession', days: 'tuple[WellnessDay, ...]')"
            " -> 'WellnessPackage'",
        ),
    ],
)
def test_wellness_operations_receive_only_session_and_selection(
    operation: str, signature: str
) -> None:
    assert str(inspect.signature(getattr(WellnessPuller, operation))) == signature


def _candidate(calls: list[str]) -> SimpleNamespace:
    def list_wellness(session: object, oldest: object) -> None:
        calls.append("list_wellness")

    def package_wellness(session: object, days: object) -> None:
        calls.append("package_wellness")

    return SimpleNamespace(
        connector_id="wellness-protocol-test",
        display_name="Synthetic Wellness",
        auth_style=AuthStyle.NONE,
        capabilities=frozenset({Capability.PULL_WELLNESS}),
        credential_fields=(),
        parse_settings=lambda table, context: None,
        list_wellness=list_wellness,
        package_wellness=package_wellness,
    )


@pytest.mark.parametrize("missing", ["list_wellness", "package_wellness"])
@pytest.mark.parametrize("non_callable", [False, True])
def test_registration_refuses_either_missing_wellness_operation(
    missing: str, non_callable: bool
) -> None:
    connector = _candidate([])
    if non_callable:
        setattr(connector, missing, 42)
    else:
        delattr(connector, missing)
    with pytest.raises(
        InvalidConnectorError,
        match=f"{missing} must be callable when PULL_WELLNESS is declared",
    ):
        register(cast(Connector, connector))
    with pytest.raises(UnknownConnectorError):
        get(connector.connector_id)


def test_registration_accepts_both_wellness_operations_without_calling_them() -> None:
    calls: list[str] = []
    connector = _candidate(calls)
    register(cast(Connector, connector))
    assert get(connector.connector_id) is connector
    assert calls == []


@pytest.mark.parametrize(
    "capability",
    [
        Capability.PUSH_ACTIVITY,
        Capability.ANNOTATE_REMOTE_ACTIVITY,
        Capability.RESOLVE_REMOTE_ACTIVITY,
        Capability.PUSH_PLANNED_WORKOUT,
        Capability.PULL_PLANNED_WORKOUTS,
        Capability.PULL_PLANS,
        Capability.PULL_THRESHOLDS,
    ],
)
def test_other_seven_capabilities_remain_reserved_without_operations(
    capability: Capability,
) -> None:
    connector = _candidate([])
    connector.capabilities = frozenset({capability})
    del connector.list_wellness
    del connector.package_wellness
    register(cast(Connector, connector))
    assert get(connector.connector_id) is connector


@pytest.mark.parametrize(
    ("capabilities", "expected"),
    [
        (None, frozenset({Capability.PULL_WELLNESS})),
        (
            frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS}),
            frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS}),
        ),
        (frozenset(), frozenset()),
    ],
    ids=["default", "activity-and-wellness", "explicit-empty"],
)
def test_scripted_wellness_puller_capabilities_and_no_auth(
    capabilities: frozenset[Capability] | None, expected: frozenset[Capability]
) -> None:
    connector = ScriptedWellnessPuller(capabilities=capabilities)
    assert connector.capabilities == expected
    assert connector.auth_style is AuthStyle.NONE
    assert connector.credential_fields == ()


def _synthetic_day(offset: int = 0) -> date:
    return (
        datetime(1989, 12, 31, tzinfo=UTC)
        + timedelta(seconds=FIT_TIMESTAMP_BASE, days=offset)
    ).date()


def _wellness_days() -> tuple[WellnessDay, WellnessDay]:
    return (
        WellnessDay(_synthetic_day(), "revision-13", {"invented": 17}),
        WellnessDay(_synthetic_day(3), "revision-29", {"invented": 31}),
    )


def test_scripted_wellness_listing_fifo_and_date_recording() -> None:
    connector = ScriptedWellnessPuller()
    session = cast(ConnectorSession, object())
    first, second = _wellness_days()
    answers = (
        WellnessListing(first.day, first.day, (first,)),
        WellnessListing(second.day, second.day, (second,)),
    )
    connector.wellness_listing_script.extend(answers)
    assert connector.wellness_list_calls == []
    assert connector.list_wellness(session, None) is answers[0]
    assert connector.list_wellness(session, second.day) is answers[1]
    assert connector.wellness_list_calls == [None, second.day]


def test_scripted_wellness_package_fifo_and_exact_selection_recording() -> None:
    connector = ScriptedWellnessPuller()
    session = cast(ConnectorSession, object())
    first, second = _wellness_days()
    selected = (second, first)
    next_selection = (first,)
    answers = (
        WellnessPackage(b'{"invented": 37}', ".json", "synthetic-a", frozenset()),
        WellnessPackage(b'{"invented": 43}', ".json", "synthetic-b", frozenset()),
    )
    connector.wellness_package_script.extend(answers)
    assert connector.wellness_package_calls == []
    assert connector.package_wellness(session, selected) is answers[0]
    assert connector.package_wellness(session, next_selection) is answers[1]
    assert connector.wellness_package_calls == [selected, next_selection]
    assert connector.wellness_package_calls[0] is selected


@pytest.mark.parametrize("operation", ["list_wellness", "package_wellness"])
@pytest.mark.parametrize("failure_kind", ["connector", "auth", "base"])
def test_scripted_wellness_failed_and_exhausted_calls_are_recorded(
    operation: str, failure_kind: str
) -> None:
    connector = ScriptedWellnessPuller()
    session = cast(ConnectorSession, object())
    first, second = _wellness_days()
    if failure_kind == "connector":
        failure: BaseException = ConnectorError("synthetic wellness listing failure")
    elif failure_kind == "auth":
        failure = AuthFailure(AuthFailureKind.REJECTED, "synthetic wellness refusal")
    else:
        failure = UnscriptedCall("synthetic queued base failure")
    assert connector.calls == []
    if operation == "list_wellness":
        assert connector.wellness_list_calls == []
        connector.wellness_listing_script.append(failure)
        with pytest.raises(type(failure)) as caught:
            connector.list_wellness(session, None)
        assert caught.value is failure
        assert connector.wellness_list_calls == [None]
        with pytest.raises(
            UnscriptedCall,
            match="ScriptedWellnessPuller.list_wellness called with no scripted answer",
        ):
            connector.list_wellness(session, second.day)
        assert connector.wellness_list_calls == [None, second.day]
    else:
        assert connector.wellness_package_calls == []
        selected = (second, first)
        connector.wellness_package_script.append(failure)
        with pytest.raises(type(failure)) as caught:
            connector.package_wellness(session, selected)
        assert caught.value is failure
        assert connector.wellness_package_calls == [selected]
        with pytest.raises(
            UnscriptedCall,
            match=(
                "ScriptedWellnessPuller.package_wellness called with no scripted answer"
            ),
        ):
            connector.package_wellness(session, (first,))
        assert connector.wellness_package_calls == [selected, (first,)]
    assert connector.calls == [operation, operation]


def test_scripted_wellness_settings_count_and_table_snapshots(tmp_path: Path) -> None:
    connector = ScriptedWellnessPuller()
    context = SettingsContext(tmp_path, tmp_path / "inbox")
    table: dict[str, object] = {"invented_setting": 47}
    assert connector.parse_settings_calls == 0
    assert connector.parse_settings_tables == []
    connector.parse_settings(table, context)
    assert connector.parse_settings_calls == 1
    table["invented_setting"] = 53
    connector.parse_settings(table, context)
    assert connector.parse_settings_calls == 2
    assert connector.parse_settings_tables == [
        {"invented_setting": 47},
        {"invented_setting": 53},
    ]


def test_scripted_wellness_inherits_activity_answers_arguments_and_mixed_order() -> (
    None
):
    connector = ScriptedWellnessPuller(
        capabilities=frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})
    )
    session = cast(ConnectorSession, object())
    first, second = _wellness_days()
    since = datetime.combine(first.day, datetime.min.time(), tzinfo=UTC)
    remote = RemoteActivity("synthetic-activity-59", True)
    listing = Listing((remote,))
    fetched = Fetched(b"invented original bytes")
    wellness_listing = WellnessListing(first.day, second.day, (first, second))
    package = WellnessPackage(b'{"invented": 61}', ".json", "synthetic", frozenset())
    connector.listing_script.append(listing)
    connector.fetch_script.append(fetched)
    connector.wellness_listing_script.append(wellness_listing)
    connector.wellness_package_script.append(package)
    selected = (second,)
    assert connector.list_calls == []
    assert connector.fetch_calls == []
    assert connector.calls == []
    assert connector.list_activities(session, since) is listing
    assert connector.list_wellness(session, first.day) is wellness_listing
    assert connector.fetch_activity(session, remote) is fetched
    assert connector.package_wellness(session, selected) is package
    assert connector.list_calls == [since]
    assert connector.fetch_calls == [remote]
    assert connector.calls == [
        "list_activities",
        "list_wellness",
        "fetch_activity",
        "package_wellness",
    ]


@pytest.mark.parametrize("failure_kind", ["connector", "auth"])
def test_scripted_wellness_supports_activity_errors_with_both_capabilities(
    failure_kind: str,
) -> None:
    connector = ScriptedWellnessPuller(
        capabilities=frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS})
    )
    session = cast(ConnectorSession, object())
    first, second = _wellness_days()
    since = datetime.combine(first.day, datetime.min.time(), tzinfo=UTC)
    remote = RemoteActivity("synthetic-activity-67", True)
    failure = (
        ConnectorError("synthetic activity listing failure")
        if failure_kind == "connector"
        else AuthFailure(AuthFailureKind.REJECTED, "synthetic activity refusal")
    )
    connector.listing_script.append(failure)
    connector.fetch_script.append(failure)
    wellness_listing = WellnessListing(first.day, second.day, (first, second))
    package = WellnessPackage(b'{"invented": 71}', ".json", "synthetic", frozenset())
    connector.wellness_listing_script.append(wellness_listing)
    connector.wellness_package_script.append(package)
    assert connector.list_calls == []
    assert connector.fetch_calls == []
    assert connector.calls == []
    with pytest.raises(type(failure)) as listing_error:
        connector.list_activities(session, since)
    assert listing_error.value is failure
    assert connector.list_wellness(session, None) is wellness_listing
    with pytest.raises(type(failure)) as fetch_error:
        connector.fetch_activity(session, remote)
    assert fetch_error.value is failure
    assert connector.package_wellness(session, (first,)) is package
    assert connector.list_calls == [since]
    assert connector.fetch_calls == [remote]
    assert connector.calls == [
        "list_activities",
        "list_wellness",
        "fetch_activity",
        "package_wellness",
    ]


def test_scripted_wellness_inherits_activity_data_transport() -> None:
    data_url = API_BASE + "/synthetic-wellness-helper"
    connector = ScriptedWellnessPuller(
        capabilities=frozenset({Capability.PULL_ACTIVITIES, Capability.PULL_WELLNESS}),
        data_url=data_url,
    )
    response = HttpResponse(200, {}, b"synthetic helper response")
    transport = FakeTransport([response])
    http = HttpClient(
        transport,
        mode=CallMode.DATA,
        redactor=Redactor(),
        sleep=lambda seconds: None,
    )
    session = cast(ConnectorSession, SimpleNamespace(http=http))
    connector.listing_script.append(Listing(()))
    assert connector.http_responses == []
    connector.list_activities(session, None)
    assert connector.http_responses == [response]
    assert transport.requests[0].url == data_url
