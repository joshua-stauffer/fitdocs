"""Publish targets: listing, preparation and the guarded send (publish-core
Req 1.6, 8.6, 8.7, 12.3, 14.1, 14.2, 14.5)."""

from __future__ import annotations

import dataclasses
import logging
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import CredentialStore, env_var_name
from fitdocs.connectors.http import (
    BACKOFF_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    CallMode,
    HttpResponse,
)
from fitdocs.connectors.protocol import AuthStyle, Capability, CredentialField
from fitdocs.connectors.secrets import Secret
from fitdocs.publish.outcomes import (
    LANDED_CODES,
    TARGET_CODES,
    PublishCode,
)
from fitdocs.publish.request import (
    CompletedActivity,
    Post,
    PublishRequest,
    PublishResult,
)
from fitdocs.publish.targets import (
    Delivery,
    TargetChannel,
    TargetRow,
    is_publish_target,
    list_targets,
    prepare_target,
)
from tests.connectors.conftest import FakeTransport
from tests.publish.conftest import (
    ScriptedPublisher,
    publisher_instance,
    registered_publisher,
)

SENTINEL = "SENTINEL-7f3a91-service-text"
LINK = "https://example.test/activity/42"
NOW = datetime(2026, 6, 1, tzinfo=UTC)
KEY_FIELD = (CredentialField("api_key", "API Key", secret=True),)
ALL_PUBLISH = frozenset(
    {
        Capability.ANNOTATE_REMOTE_ACTIVITY,
        Capability.RESOLVE_REMOTE_ACTIVITY,
        Capability.PUSH_ACTIVITY,
    }
)
LANDED = sorted(LANDED_CODES)
NOT_LANDED_TARGET = sorted(TARGET_CODES - LANDED_CODES)
NOT_TARGET = [code for code in PublishCode if code not in TARGET_CODES]


def _request() -> PublishRequest:
    return PublishRequest(
        publication_id="a" * 32,
        post=Post(title="Morning Run", description="12.5 km"),
        subject=CompletedActivity(
            sport="Run",
            start=datetime(2026, 3, 4, 7, 5, tzinfo=UTC),
            elapsed_s=3725.0,
            distance_m=12500.0,
            source_shas=("b" * 64,),
            base_fit=None,
        ),
        recorded_link=None,
    )


def _channel(
    tmp_path: Path, publisher: ScriptedPublisher | None = None
) -> tuple[TargetChannel, ScriptedPublisher, FakeTransport]:
    connector = publisher if publisher is not None else ScriptedPublisher()
    transport = FakeTransport([])
    prepared = prepare_target(
        publisher_instance(connector),
        data_root=tmp_path,
        store=None,
        environ={},
        transport=transport,
        now=lambda: NOW,
        sleep=lambda seconds: None,
    )
    assert isinstance(prepared, TargetChannel)
    return prepared, connector, transport


def _send_with(tmp_path: Path, outcome: object) -> tuple[Delivery, ScriptedPublisher]:
    channel, publisher, _ = _channel(tmp_path)
    publisher.publish_script.append(outcome)
    return channel.send(_request()), publisher


# --------------------------------------------------------------- fixtures


def test_the_scripted_publisher_is_registered_for_a_block_and_unregistered_after() -> (
    None
):
    with pytest.raises(connector_registry.UnknownConnectorError):
        connector_registry.get("scripted-publisher")
    with registered_publisher() as publisher:
        assert connector_registry.get("scripted-publisher") is publisher
    with pytest.raises(connector_registry.UnknownConnectorError):
        connector_registry.get("scripted-publisher")


def test_the_scripted_publisher_is_unregistered_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError), registered_publisher():
        raise RuntimeError("boom")
    with pytest.raises(connector_registry.UnknownConnectorError):
        connector_registry.get("scripted-publisher")


def test_the_registration_fixture_registers_each_publisher_it_makes(
    register_scripted_publisher: Callable[..., ScriptedPublisher],
) -> None:
    first = register_scripted_publisher()
    second = register_scripted_publisher(connector_id="second-publisher")
    assert connector_registry.get("scripted-publisher") is first
    assert connector_registry.get("second-publisher") is second


def test_the_registry_refuses_push_without_annotate() -> None:
    options = {"capabilities": frozenset({Capability.PUSH_ACTIVITY})}
    with (
        pytest.raises(connector_registry.InvalidConnectorError),
        registered_publisher(**options),
    ):
        pass


def test_an_unscripted_publish_call_is_loud(tmp_path: Path) -> None:
    channel, publisher, _ = _channel(tmp_path)
    assert publisher.publish_script == []
    with pytest.raises(BaseException) as excinfo:  # noqa: PT011
        channel.send(_request())
    assert not isinstance(excinfo.value, Exception)


# ------------------------------------------------------------ is_publish_target


def test_a_target_is_an_instance_whose_connector_declares_annotate() -> None:
    assert is_publish_target(publisher_instance(ScriptedPublisher()))


@pytest.mark.parametrize(
    "capabilities",
    [
        frozenset({Capability.PULL_ACTIVITIES}),
        frozenset({Capability.RESOLVE_REMOTE_ACTIVITY}),
        frozenset({Capability.PUSH_ACTIVITY, Capability.RESOLVE_REMOTE_ACTIVITY}),
        frozenset(),
    ],
)
def test_other_capabilities_do_not_make_a_target(
    capabilities: frozenset[Capability],
) -> None:
    connector = ScriptedPublisher(capabilities=capabilities)
    assert not is_publish_target(publisher_instance(connector))


# ------------------------------------------------------------- list_targets


def test_a_row_carries_exactly_the_listed_fields() -> None:
    assert [field.name for field in dataclasses.fields(TargetRow)] == [
        "name",
        "connector",
        "display_name",
        "capabilities",
        "state",
    ]


def test_the_listing_has_each_target_with_its_details_in_name_order() -> None:
    zulu = ScriptedPublisher(
        connector_id="zulu-pub", display_name="Zulu Pub", capabilities=ALL_PUBLISH
    )
    plain = ScriptedPublisher(connector_id="plain-pub", display_name="Plain Pub")
    rows = list_targets(
        [
            publisher_instance(zulu, name="zeta"),
            publisher_instance(plain, name="alpha"),
            publisher_instance(plain, name="mid"),
        ],
        store=None,
        environ={},
    )
    assert [row.name for row in rows] == ["alpha", "mid", "zeta"]
    assert rows[0] == TargetRow(
        name="alpha",
        connector="plain-pub",
        display_name="Plain Pub",
        capabilities=("annotate-remote-activity",),
        state=PublishCode.READY,
    )
    assert rows[2] == TargetRow(
        name="zeta",
        connector="zulu-pub",
        display_name="Zulu Pub",
        capabilities=(
            "push-activity",
            "annotate-remote-activity",
            "resolve-remote-activity",
        ),
        state=PublishCode.READY,
    )


def test_the_listing_names_only_publish_capabilities_and_only_targets() -> None:
    mixed = ScriptedPublisher(
        capabilities=frozenset(
            {Capability.ANNOTATE_REMOTE_ACTIVITY, Capability.PULL_ACTIVITIES}
        )
    )
    puller = ScriptedPublisher(
        connector_id="only-pull", capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    rows = list_targets(
        [publisher_instance(puller, name="aaa"), publisher_instance(mixed, name="bbb")],
        store=None,
        environ={},
    )
    assert [row.name for row in rows] == ["bbb"]
    assert rows[0].capabilities == ("annotate-remote-activity",)


def test_no_instances_and_no_targets_give_an_empty_listing() -> None:
    assert list_targets([], store=None, environ={}) == ()
    puller = ScriptedPublisher(capabilities=frozenset({Capability.PULL_ACTIVITIES}))
    assert list_targets([publisher_instance(puller)], store=None, environ={}) == ()


def _key_publisher() -> ScriptedPublisher:
    return ScriptedPublisher(auth_style=AuthStyle.API_KEY, credential_fields=KEY_FIELD)


def test_the_states_are_ready_not_connected_and_unreadable(tmp_path: Path) -> None:
    connector = _key_publisher()
    key_var = env_var_name("keyed", "api_key")
    credentials_dir = tmp_path / "credentials"
    credentials_dir.mkdir()
    store = CredentialStore(credentials_dir)
    unreadable = store.path_for("broken")
    unreadable.write_text("credentials_version = 1\n")
    os.chmod(unreadable, 0o644)
    instances = [
        publisher_instance(connector, name="keyed"),
        publisher_instance(connector, name="missing"),
        publisher_instance(connector, name="broken"),
    ]
    rows = list_targets(instances, store=store, environ={key_var: SENTINEL})
    assert {row.name: row.state for row in rows} == {
        "keyed": PublishCode.READY,
        "missing": PublishCode.NOT_CONNECTED,
        "broken": PublishCode.CREDENTIALS_UNREADABLE,
    }


def test_the_listing_shows_no_credential_value_and_makes_no_call(
    tmp_path: Path,
) -> None:
    connector = _key_publisher()
    key_var = env_var_name("keyed", "api_key")
    rows = list_targets(
        [publisher_instance(connector, name="keyed")],
        store=None,
        environ={key_var: SENTINEL},
    )
    assert rows[0].state is PublishCode.READY
    assert SENTINEL not in repr(rows)
    for row in rows:
        for field in dataclasses.fields(row):
            assert SENTINEL not in repr(getattr(row, field.name))
    assert connector.publish_calls == []


# ----------------------------------------------------------- prepare_target


def _prepare(
    tmp_path: Path,
    connector: ScriptedPublisher,
    *,
    name: str = "alpha",
    store: CredentialStore | None = None,
    environ: dict[str, str] | None = None,
) -> tuple[TargetChannel | PublishCode, FakeTransport]:
    transport = FakeTransport([])
    result = prepare_target(
        publisher_instance(connector, name=name),
        data_root=tmp_path,
        store=store,
        environ=environ or {},
        transport=transport,
        now=lambda: NOW,
        sleep=lambda seconds: None,
    )
    return result, transport


def test_not_connected_is_a_code_and_no_request(tmp_path: Path) -> None:
    connector = _key_publisher()
    result, transport = _prepare(tmp_path, connector)
    assert result is PublishCode.NOT_CONNECTED
    assert transport.requests == []
    assert connector.publish_calls == []


def test_unreadable_credentials_are_a_code_and_no_request(tmp_path: Path) -> None:
    connector = _key_publisher()
    credentials_dir = tmp_path / "credentials"
    credentials_dir.mkdir()
    store = CredentialStore(credentials_dir)
    bad = store.path_for("alpha")
    bad.write_text("credentials_version = 1\n")
    os.chmod(bad, 0o644)
    result, transport = _prepare(
        tmp_path,
        connector,
        store=store,
        environ={env_var_name("alpha", "api_key"): SENTINEL},
    )
    assert result is PublishCode.CREDENTIALS_UNREADABLE
    assert transport.requests == []
    assert connector.publish_calls == []


def test_a_ready_target_gets_a_data_mode_session_built_as_the_pull_builds_it(
    tmp_path: Path,
) -> None:
    connector = ScriptedPublisher(link_label="Posted copy")
    settings_sentinel = object()
    instance = publisher_instance(connector, name="beta")
    instance = dataclasses.replace(instance, settings=settings_sentinel)
    transport = FakeTransport([])
    sleeps: list[float] = []
    prepared = prepare_target(
        instance,
        data_root=tmp_path,
        store=None,
        environ={},
        transport=transport,
        now=lambda: NOW,
        sleep=sleeps.append,
    )
    assert isinstance(prepared, TargetChannel)
    assert (prepared.name, prepared.label) == ("beta", "Posted copy")
    connector.publish_script.append(PublishResult(PublishCode.POSTED))
    request = _request()
    prepared.send(request)
    [(session, received)] = connector.publish_calls
    assert received is request
    assert session.instance == "beta"
    assert session.settings is settings_sentinel
    assert session.data_root == tmp_path
    assert session.now() == NOW
    assert session.http.mode is CallMode.DATA
    session.sleep(1.5)
    assert sleeps == [1.5]


def test_the_session_sends_through_the_given_transport_with_its_clock_and_redactor(
    tmp_path: Path,
) -> None:
    connector = ScriptedPublisher()
    transport = FakeTransport(
        [HttpResponse(503, {}, b""), HttpResponse(200, {}, b"ok")]
    )
    sleeps: list[float] = []
    prepared = prepare_target(
        publisher_instance(connector),
        data_root=tmp_path,
        store=None,
        environ={},
        transport=transport,
        now=lambda: NOW,
        sleep=sleeps.append,
    )
    assert isinstance(prepared, TargetChannel)
    connector.publish_script.append(PublishResult(PublishCode.POSTED))
    prepared.send(_request())
    [(session, _seen)] = connector.publish_calls
    token = "tok-SENTINEL"
    assert session.redactor.redact(token) == token
    response = session.http.get(
        "https://example.test/x", secret_headers={"Authorization": Secret(token)}
    )
    assert response.status == 200
    assert len(transport.requests) == 2
    assert sleeps == [BACKOFF_SECONDS[0]]
    assert transport.timeouts == [DEFAULT_TIMEOUT_SECONDS] * 2
    assert session.redactor.redact(token) != token


def test_preparing_with_an_environment_key_resolves_the_credential(
    tmp_path: Path,
) -> None:
    connector = _key_publisher()
    result, _ = _prepare(
        tmp_path,
        connector,
        environ={env_var_name("alpha", "api_key"): SENTINEL},
    )
    assert isinstance(result, TargetChannel)
    connector.publish_script.append(PublishResult(PublishCode.POSTED))
    result.send(_request())
    [(session, _request_seen)] = connector.publish_calls
    assert session.credentials.value("api_key").reveal() == SENTINEL


def test_each_preparation_has_its_own_redactor(tmp_path: Path) -> None:
    connector = _key_publisher()
    first, _ = _prepare(
        tmp_path, connector, environ={env_var_name("alpha", "api_key"): SENTINEL}
    )
    second, _ = _prepare(
        tmp_path,
        connector,
        environ={env_var_name("alpha", "api_key"): "another-value"},
    )
    assert isinstance(first, TargetChannel) and isinstance(second, TargetChannel)
    connector.publish_script.extend([PublishResult(PublishCode.POSTED)] * 2)
    first.send(_request())
    second.send(_request())
    (first_session, _), (second_session, _) = connector.publish_calls
    assert first_session.redactor is not second_session.redactor
    assert first_session.redactor.redact(SENTINEL) != SENTINEL
    assert second_session.redactor.redact(SENTINEL) == SENTINEL


# --------------------------------------------------------------------- send


@pytest.mark.parametrize("code", LANDED)
def test_a_landed_code_keeps_a_valid_link(tmp_path: Path, code: PublishCode) -> None:
    delivery, publisher = _send_with(tmp_path, PublishResult(code, LINK))
    assert delivery == Delivery(code, LINK, False)
    assert len(publisher.publish_calls) == 1


def test_the_landed_set_is_not_empty_and_has_a_decoy_per_side() -> None:
    assert len(LANDED) >= 2
    assert len(NOT_LANDED_TARGET) >= 2
    assert not set(LANDED) & set(NOT_LANDED_TARGET)


@pytest.mark.parametrize("code", NOT_LANDED_TARGET)
def test_a_link_with_a_code_that_is_not_landed_is_dropped_and_flagged(
    tmp_path: Path, code: PublishCode
) -> None:
    delivery, _ = _send_with(tmp_path, PublishResult(code, LINK))
    assert delivery == Delivery(code, None, True)


@pytest.mark.parametrize("code", [*LANDED, *NOT_LANDED_TARGET])
def test_an_answer_without_a_link_has_no_link_and_no_flag(
    tmp_path: Path, code: PublishCode
) -> None:
    delivery, _ = _send_with(tmp_path, PublishResult(code))
    assert delivery == Delivery(code, None, False)


@pytest.mark.parametrize(
    "link",
    [
        "http://example.test/a",
        "https://",
        "https://example.test/a b",
        "https://example.test/a\nb",
        "https://example.test/a)b",
        "javascript:alert(1)",
        "",
        "https://example.test/" + "a" * 5000,
    ],
)
def test_a_landed_code_with_an_invalid_link_drops_it_and_flags_it(
    tmp_path: Path, link: str
) -> None:
    delivery, _ = _send_with(tmp_path, PublishResult(PublishCode.POSTED, link))
    assert delivery == Delivery(PublishCode.POSTED, None, True)


def test_a_non_string_link_is_dropped_and_flagged(tmp_path: Path) -> None:
    answer = PublishResult(PublishCode.POSTED, 42)  # type: ignore[arg-type]
    delivery, _ = _send_with(tmp_path, answer)
    assert delivery == Delivery(PublishCode.POSTED, None, True)


@pytest.mark.parametrize("offered", [LINK, ""])
@pytest.mark.parametrize("code", NOT_TARGET)
def test_a_code_a_target_may_not_return_becomes_the_failure_code(
    tmp_path: Path, code: PublishCode, offered: str
) -> None:
    delivery, _ = _send_with(tmp_path, PublishResult(code, offered))
    assert delivery == Delivery(PublishCode.TARGET_ERROR, None, True)


@pytest.mark.parametrize("code", NOT_TARGET)
def test_a_code_a_target_may_not_return_without_a_link_is_not_flagged(
    tmp_path: Path, code: PublishCode
) -> None:
    delivery, _ = _send_with(tmp_path, PublishResult(code))
    assert delivery == Delivery(PublishCode.TARGET_ERROR, None, False)


def test_the_three_send_groups_partition_the_vocabulary() -> None:
    assert set(LANDED) | set(NOT_LANDED_TARGET) | set(NOT_TARGET) == set(PublishCode)
    assert NOT_TARGET
    assert PublishCode.NOT_ATTEMPTED in NOT_TARGET


@pytest.mark.parametrize(
    "answer",
    [
        None,
        "posted",
        PublishCode.POSTED,
        {"code": PublishCode.POSTED},
        (PublishCode.POSTED, LINK),
        object(),
        SimpleNamespace(code=PublishCode.POSTED, link=LINK),
    ],
)
def test_a_non_result_answer_becomes_the_failure_code(
    tmp_path: Path, answer: object
) -> None:
    delivery, _ = _send_with(tmp_path, answer)
    assert delivery == Delivery(PublishCode.TARGET_ERROR, None, False)


def test_a_result_whose_code_is_a_plain_string_becomes_the_failure_code(
    tmp_path: Path,
) -> None:
    answer = PublishResult("posted", LINK)  # type: ignore[arg-type]
    assert "posted" in TARGET_CODES  # a plain string equals the member
    delivery, _ = _send_with(tmp_path, answer)
    assert delivery == Delivery(PublishCode.TARGET_ERROR, None, True)
    assert type(delivery.code) is PublishCode


def test_a_plain_string_code_without_a_link_is_not_flagged(tmp_path: Path) -> None:
    answer = PublishResult("posted")  # type: ignore[arg-type]
    delivery, _ = _send_with(tmp_path, answer)
    assert delivery == Delivery(PublishCode.TARGET_ERROR, None, False)


def _chained(sentinel: str) -> Exception:
    try:
        try:
            raise OSError(f"inner {sentinel}")
        except OSError as inner:
            raise ValueError(f"middle {sentinel}") from inner
    except ValueError as middle:
        error = RuntimeError(sentinel, {"detail": sentinel})
        error.__cause__ = middle
        return error


class _SentinelError(Exception):
    def __repr__(self) -> str:
        return f"_SentinelError({SENTINEL})"


def _every_text(value: object) -> list[str]:
    texts = [repr(value), str(value)]
    if dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            texts.extend(_every_text(getattr(value, field.name)))
    return texts


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError(SENTINEL),
        ValueError("a", SENTINEL),
        _SentinelError(),
        _chained(SENTINEL),
        LookupError({"k": SENTINEL}),
    ],
    ids=["message", "args", "repr", "chain", "mapping-arg"],
)
def test_a_raising_target_gives_the_failure_code_and_no_exception_text(
    tmp_path: Path,
    error: Exception,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    channel, publisher, transport = _channel(tmp_path)
    publisher.publish_script.append(error)
    with caplog.at_level(logging.DEBUG):
        delivery = channel.send(_request())
    assert delivery == Delivery(PublishCode.TARGET_ERROR, None, False)
    assert len(publisher.publish_calls) == 1
    for text in _every_text(delivery):
        assert SENTINEL not in text
    for text in _every_text(channel):
        assert SENTINEL not in text
    assert set(vars(channel)) == {"name", "label", "_publisher", "_session"}
    assert not any(isinstance(v, BaseException) for v in vars(channel).values())
    assert SENTINEL not in caplog.text
    assert caplog.records == []
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")
    assert sys.exc_info() == (None, None, None)
    assert transport.requests == []


def test_service_text_in_a_dropped_link_or_refused_code_is_not_kept(
    tmp_path: Path,
) -> None:
    for answer in (
        PublishResult(PublishCode.REJECTED, f"https://example.test/{SENTINEL}"),
        PublishResult(PublishCode.POSTED, f"https://example.test/{SENTINEL} x"),
        PublishResult(PublishCode.NOT_ATTEMPTED, f"https://example.test/{SENTINEL}"),
    ):
        delivery, _ = _send_with(tmp_path, answer)
        for text in _every_text(delivery):
            assert SENTINEL not in text


def test_an_interrupt_propagates_and_is_not_swallowed(tmp_path: Path) -> None:
    channel, publisher, _ = _channel(tmp_path)
    publisher.publish_script.append(KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        channel.send(_request())
    assert len(publisher.publish_calls) == 1


def test_a_failure_is_not_retried(tmp_path: Path) -> None:
    channel, publisher, _ = _channel(tmp_path)
    publisher.publish_script.extend(
        [RuntimeError(SENTINEL), PublishResult(PublishCode.POSTED)]
    )
    assert channel.send(_request()).code is PublishCode.TARGET_ERROR
    assert len(publisher.publish_calls) == 1
    assert len(publisher.publish_script) == 1
