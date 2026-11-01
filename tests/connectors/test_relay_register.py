"""Registering against a relay that offers it (relay-server task 6.4;
Requirements 13.1, 13.3-13.10, 15.2, 15.4).

Every request goes through a scripted ``FakeTransport``; time is a fake clock
whose ``sleep`` advances it and raises once a bounded number of sleeps is
exceeded, so a loop that should have ended fails the test instead of hanging
it. The relay is the real ``RelayConnector``; the store is a real
``CredentialStore`` in a temporary directory.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fitdocs.connectors.http import HttpRequest, HttpResponse, TransportError
from fitdocs.connectors.protocol import AuthStyle
from fitdocs.connectors.relay_codes import RELAY_CODES, RelayCode, explain
from fitdocs.connectors.relay_connect import (
    RegistrationEmailError,
    RegistrationShown,
    RelayConnected,
    RelayConnectFailed,
    relay_next_step,
    run_relay_connect,
    run_relay_registration,
)
from fitdocs.connectors.relay_envelope import (
    MAX_POLL_INTERVAL_S,
    ROUTE_CAPABILITIES,
    ROUTE_REGISTRATION_POLL,
    ROUTE_REGISTRATIONS,
    SLOW_DOWN_STEP_S,
)
from fitdocs.connectors.secrets import REDACTED, Redactor
from tests.connectors.conftest import FakeTransport
from tests.connectors.test_relay_connect import (
    _BASE,
    _CLOCK,
    _OLD_TOKEN,
    _PLANT,
    _TOKEN,
    _envelope,
    _instance,
    _scripted_for,
    _store,
    _stored_files,
)

_EMAIL = "runner.person@example.org"
_USER_CODE = "BCDF-GHJK"
_POLL_SECRET = "PollSecret_" + "x" * 30 + "-9"
_MAX_SLEEPS = 12


# --------------------------------------------------------------------------
# Fixtures: a bounded fake clock, scripted answers, one runner
# --------------------------------------------------------------------------


@dataclass
class _Clock:
    """``sleep`` advances ``now`` by the requested seconds and records it; the
    guard raises ``AssertionError`` past ``max_sleeps`` so a missing end
    condition fails instead of looping."""

    start: datetime = _CLOCK
    max_sleeps: int = _MAX_SLEEPS
    sleeps: list[float] = field(default_factory=list)
    elapsed: float = 0.0

    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.elapsed)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if len(self.sleeps) > self.max_sleeps:
            raise AssertionError(
                f"fake-clock guard: more than {self.max_sleeps} sleeps, the "
                "registration loop did not end"
            )
        self.elapsed += seconds


def _caps(registration: bool = True) -> HttpResponse:
    return _envelope(
        RelayCode.OK,
        {"envelopes": [1], "registration": registration, "targets": []},
    )


def _started(
    *,
    interval_s: object = 10,
    expires_in_s: object = 600,
    user_code: object = _USER_CODE,
    poll_secret: object = _POLL_SECRET,
    extra: Mapping[str, object] | None = None,
) -> HttpResponse:
    data: dict[str, object] = {
        "user_code": user_code,
        "poll_secret": poll_secret,
        "interval_s": interval_s,
        "expires_in_s": expires_in_s,
    }
    data.update(extra or {})
    return _envelope(RelayCode.REGISTRATION_STARTED, data)


def _pending() -> HttpResponse:
    return _envelope(RelayCode.REGISTRATION_PENDING)


def _slow() -> HttpResponse:
    return _envelope(RelayCode.REGISTRATION_SLOW_DOWN)


def _issued(token: str = _TOKEN) -> HttpResponse:
    return _envelope(RelayCode.REGISTRATION_ISSUED, {"token": token})


Script = list[HttpResponse | TransportError]


@dataclass
class _Run:
    result: RelayConnected | RelayConnectFailed
    transport: FakeTransport
    clock: _Clock
    shown: list[RegistrationShown]
    redactor: Redactor
    events: list[str]


def _register(
    tmp_path: Path,
    script: Sequence[HttpResponse | TransportError],
    *,
    email: str = _EMAIL,
    clock: _Clock | None = None,
    redactor: Redactor | None = None,
    environ: Mapping[str, str] | None = None,
) -> _Run:
    transport = FakeTransport(list(script))
    clock = clock if clock is not None else _Clock()
    redactor = redactor if redactor is not None else Redactor()
    shown: list[RegistrationShown] = []
    events: list[str] = []

    def recording(request: HttpRequest, timeout: float) -> HttpResponse:
        events.append(f"{request.method} {request.url.removeprefix(_BASE)}")
        return transport(request, timeout)

    def on_started(value: RegistrationShown) -> None:
        events.append("shown")
        shown.append(value)

    def sleep(seconds: float) -> None:
        events.append("sleep")
        clock.sleep(seconds)

    result = run_relay_registration(
        _instance(),
        email,
        store=_store(tmp_path),
        transport=recording,
        environ=environ or {},
        now=clock.now,
        sleep=sleep,
        redactor=redactor,
        on_started=on_started,
    )
    return _Run(result, transport, clock, shown, redactor, events)


def _body(request: HttpRequest) -> object:
    assert request.body is not None
    return json.loads(request.body)


def _all_written_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def _assert_not_written(root: Path, *needles: str) -> None:
    written = _all_written_bytes(root)
    for name, content in written.items():
        for needle in needles:
            assert needle.encode() not in content, f"{needle!r} written to {name}"


# --------------------------------------------------------------------------
# Req 13.1, 13.3, 13.6: the whole happy path
# --------------------------------------------------------------------------


def test_register_reads_capabilities_starts_shows_polls_then_stores_the_token(
    tmp_path: Path,
) -> None:
    run = _register(tmp_path, [_caps(), _started(), _pending(), _issued()])
    assert isinstance(run.result, RelayConnected)
    assert run.result.instance == "relay"
    assert run.result.path == tmp_path / "credentials" / "relay.toml"
    assert run.result.env_override == ()
    # Route order, the shown callback strictly between start and first poll,
    # and one sleep before each poll.
    assert run.events == [
        f"GET {ROUTE_CAPABILITIES}",
        f"POST {ROUTE_REGISTRATIONS}",
        "shown",
        "sleep",
        f"POST {ROUTE_REGISTRATION_POLL}",
        "sleep",
        f"POST {ROUTE_REGISTRATION_POLL}",
    ]
    assert run.clock.sleeps == [10, 10]
    assert run.shown == [
        RegistrationShown(email=_EMAIL, user_code=_USER_CODE, expires_in_s=600)
    ]
    caps, start, poll1, poll2 = run.transport.requests
    assert caps.body is None
    assert _body(start) == {"email": _EMAIL}
    assert _body(poll1) == {"poll_secret": _POLL_SECRET}
    assert _body(poll2) == {"poll_secret": _POLL_SECRET}
    for request in run.transport.requests:
        assert request.secret_headers == {}  # no token before one is issued
        assert _EMAIL not in request.url and _POLL_SECRET not in request.url


def test_an_issued_token_is_stored_exactly_as_a_paste_stores_it(
    tmp_path: Path,
) -> None:
    run = _register(tmp_path / "reg", [_caps(), _started(), _issued()])
    assert isinstance(run.result, RelayConnected)
    pasted = run_relay_connect(
        _instance(),
        _TOKEN,
        store=_store(tmp_path / "paste"),
        transport=FakeTransport([_envelope(RelayCode.OK)]),
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )
    assert isinstance(pasted, RelayConnected)
    registered = (tmp_path / "reg" / "credentials" / "relay.toml").read_bytes()
    assert (
        registered == (tmp_path / "paste" / "credentials" / "relay.toml").read_bytes()
    )
    assert _TOKEN.encode() in registered
    stored = _store(tmp_path / "reg").load("relay")
    assert stored is not None
    assert stored.auth_style is AuthStyle.RELAY_TOKEN
    assert stored.connector_id == "relay"
    assert stored.expires_at is None and stored.scopes is None


def test_an_issued_token_replaces_an_earlier_one_and_revokes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_relay_connect(
        _instance(),
        _OLD_TOKEN,
        store=_store(tmp_path),
        transport=FakeTransport([_envelope(RelayCode.OK)]),
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )
    before = (tmp_path / "credentials" / "relay.toml").read_bytes()
    assert _OLD_TOKEN.encode() in before
    directory = tmp_path / "credentials"
    events: list[tuple[str, str]] = []
    real_mkstemp = tempfile.mkstemp
    real_replace = os.replace

    def spy_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        fd, name = real_mkstemp(*args, **kwargs)  # type: ignore[call-overload]
        events.append(("mkstemp", name))
        return fd, name

    def spy_replace(src: object, dst: object) -> None:
        events.append(("replace", f"{src}->{dst}"))
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(tempfile, "mkstemp", spy_mkstemp)
    monkeypatch.setattr(os, "replace", spy_replace)
    run = _register(tmp_path, [_caps(), _started(), _issued()])
    assert isinstance(run.result, RelayConnected)
    assert [kind for kind, _ in events] == ["mkstemp", "replace"]
    temp = Path(events[0][1])
    assert temp.parent == directory and temp.name.startswith(".")
    assert events[1][1] == f"{temp}->{directory / 'relay.toml'}"
    after = (directory / "relay.toml").read_bytes()
    assert after != before and _TOKEN.encode() in after
    assert _OLD_TOKEN.encode() not in after
    assert [r.url.removeprefix(_BASE) for r in run.transport.requests] == [
        ROUTE_CAPABILITIES,
        ROUTE_REGISTRATIONS,
        ROUTE_REGISTRATION_POLL,
    ]
    assert _stored_files(tmp_path) == ["relay.toml"]


def test_the_env_override_is_reported_for_a_registration_too(tmp_path: Path) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(), _issued()],
        environ={"FITDOCS_CONNECTOR_RELAY_TOKEN": "x"},
    )
    assert isinstance(run.result, RelayConnected)
    assert run.result.env_override == ("FITDOCS_CONNECTOR_RELAY_TOKEN",)


# --------------------------------------------------------------------------
# Req 13.1: a relay without registration
# --------------------------------------------------------------------------


def test_a_relay_without_registration_is_not_offered_and_nothing_else_happens(
    tmp_path: Path,
) -> None:
    run = _register(tmp_path, [_caps(registration=False), _started(), _issued()])
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.NOT_OFFERED
    assert run.result.explanation == explain(RelayCode.NOT_OFFERED)
    assert run.result.next_step == "Ask the relay's operator for a token."
    assert run.result.retry_after_s is None
    assert [r.url.removeprefix(_BASE) for r in run.transport.requests] == [
        ROUTE_CAPABILITIES
    ]
    assert run.shown == [] and run.clock.sleeps == []
    assert _stored_files(tmp_path) == []


# --------------------------------------------------------------------------
# Req 13.5: slow-down adds the fixed step, capped at the maximum
# --------------------------------------------------------------------------


def test_the_step_and_the_cap_are_the_documented_literals() -> None:
    assert SLOW_DOWN_STEP_S == 5
    assert MAX_POLL_INTERVAL_S == 60


def test_each_slow_down_lengthens_the_next_wait_by_the_fixed_step(
    tmp_path: Path,
) -> None:
    run = _register(
        tmp_path,
        [
            _caps(),
            _started(interval_s=10),
            _slow(),
            _slow(),
            _pending(),
            _pending(),
            _issued(),
        ],
    )
    assert isinstance(run.result, RelayConnected)
    # The wait before the first poll is the stated interval; each slow-down
    # answer lengthens every later wait; pending leaves it alone.
    assert run.clock.sleeps == [10, 15, 20, 20, 20]


def test_repeated_slow_downs_never_exceed_the_maximum(tmp_path: Path) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(interval_s=52, expires_in_s=3600)]
        + [_slow()] * 4
        + [_issued()],
    )
    assert isinstance(run.result, RelayConnected)
    assert run.clock.sleeps == [52, 57, 60, 60, 60]
    assert max(run.clock.sleeps) == MAX_POLL_INTERVAL_S


def test_a_stated_interval_at_the_maximum_stays_there_after_a_slow_down(
    tmp_path: Path,
) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(interval_s=60, expires_in_s=3600), _slow(), _issued()],
    )
    assert isinstance(run.result, RelayConnected)
    assert run.clock.sleeps == [60, 60]


# --------------------------------------------------------------------------
# Req 13.8: the local deadline
# --------------------------------------------------------------------------


def test_passing_the_deadline_gives_expired_and_no_poll_past_it(
    tmp_path: Path,
) -> None:
    # Deadline 70 s after the start; polls fall at 20, 40 and 60 s; the sleep
    # to 80 s passes the deadline, so there is no fourth poll even though the
    # script would answer one.
    clock = _Clock(start=_CLOCK + timedelta(days=3, hours=5))
    run = _register(
        tmp_path,
        [_caps(), _started(interval_s=20, expires_in_s=70)]
        + [_pending()] * (_MAX_SLEEPS + 5),
        clock=clock,
    )
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.REGISTRATION_EXPIRED
    assert run.result.explanation == explain(RelayCode.REGISTRATION_EXPIRED)
    assert run.result.next_step == "Run `fitdocs connect relay --register` again."
    polls = [
        r for r in run.transport.requests if r.url.endswith(ROUTE_REGISTRATION_POLL)
    ]
    assert len(polls) == 3
    assert clock.sleeps == [20, 20, 20, 20]
    assert run.shown == [
        RegistrationShown(email=_EMAIL, user_code=_USER_CODE, expires_in_s=70)
    ]
    assert _stored_files(tmp_path) == []


def test_a_wait_that_lands_exactly_on_the_deadline_is_expired_with_no_further_poll(
    tmp_path: Path,
) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(interval_s=20, expires_in_s=60)]
        + [_pending()] * (_MAX_SLEEPS + 5),
    )
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.REGISTRATION_EXPIRED
    assert run.clock.sleeps == [20, 20, 20]
    assert run.clock.elapsed == 60  # the clock sits exactly on the deadline
    polls = [
        r for r in run.transport.requests if r.url.endswith(ROUTE_REGISTRATION_POLL)
    ]
    assert len(polls) == 2
    assert _stored_files(tmp_path) == []


def test_a_wait_that_lands_one_second_before_the_deadline_still_polls(
    tmp_path: Path,
) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(interval_s=20, expires_in_s=61)]
        + [_pending()] * (_MAX_SLEEPS + 5),
    )
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.REGISTRATION_EXPIRED
    assert run.clock.sleeps == [20, 20, 20, 20]
    polls = [
        r for r in run.transport.requests if r.url.endswith(ROUTE_REGISTRATION_POLL)
    ]
    assert len(polls) == 3


def test_an_issued_answer_inside_the_deadline_still_wins(tmp_path: Path) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(interval_s=20, expires_in_s=70)]
        + [_pending()] * 2
        + [_issued()],
    )
    assert isinstance(run.result, RelayConnected)
    assert run.clock.sleeps == [20, 20, 20]


def test_a_slowed_interval_can_carry_the_wait_past_the_deadline(
    tmp_path: Path,
) -> None:
    # 60 s deadline plus one: t=30 poll (slow-down -> 35), then t=65 is past it.
    run = _register(
        tmp_path,
        [_caps(), _started(interval_s=30, expires_in_s=61), _slow(), _issued()],
    )
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.REGISTRATION_EXPIRED
    assert run.clock.sleeps == [30, 35]


def test_the_fake_clock_guard_fails_a_loop_that_never_ends(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="fake-clock guard"):
        _register(
            tmp_path,
            [_caps(), _started(interval_s=1, expires_in_s=3600)]
            + [_pending()] * (_MAX_SLEEPS + 5),
        )


# --------------------------------------------------------------------------
# Req 13.4, 13.7, 15.3: every other ending stops with its code, stores nothing
# --------------------------------------------------------------------------

_STAGES = ("capabilities", "start", "poll")
_SUCCESS_SHAPED = frozenset(
    {
        RelayCode.OK,
        RelayCode.REGISTRATION_STARTED,
        RelayCode.REGISTRATION_PENDING,
        RelayCode.REGISTRATION_SLOW_DOWN,
        RelayCode.REGISTRATION_ISSUED,
    }
)
# What a stage treats as a success or as "keep going".
_STAGE_SUCCESS = {
    "capabilities": frozenset({RelayCode.OK}),
    "start": frozenset({RelayCode.REGISTRATION_STARTED}),
    "poll": frozenset(
        {
            RelayCode.REGISTRATION_PENDING,
            RelayCode.REGISTRATION_SLOW_DOWN,
            RelayCode.REGISTRATION_ISSUED,
        }
    ),
}
_PREFIX = {
    "capabilities": 0,
    "start": 1,
    "poll": 2,
}
_BAIT = {
    "capabilities": lambda: [_caps(), _started(), _issued()],
    "start": lambda: [_started(), _issued(), _issued()],
    "poll": lambda: [_issued(), _issued()],
}


def _staged(stage: str, failing: Sequence[HttpResponse | TransportError]) -> Script:
    prefix = [_caps(), _started()][: _PREFIX[stage]]
    return [*prefix, *failing, *_BAIT[stage]()]


def _expected(code: RelayCode) -> RelayCode:
    return RelayCode.ANSWER_MALFORMED if code in _SUCCESS_SHAPED else code


_FAILURE_CASES = [
    pytest.param(stage, code, id=f"{stage}-{code.value}")
    for stage in _STAGES
    for code in RELAY_CODES
    if code not in _STAGE_SUCCESS[stage]
]


def test_the_failure_cases_cover_every_code_but_each_stages_success_codes() -> None:
    for stage in _STAGES:
        stage_codes = {p.values[1] for p in _FAILURE_CASES if p.values[0] == stage}
        assert stage_codes | _STAGE_SUCCESS[stage] == set(RelayCode)
        assert stage_codes.isdisjoint(_STAGE_SUCCESS[stage])
    assert len(RELAY_CODES) >= 21
    assert len(_FAILURE_CASES) == sum(
        len(RELAY_CODES) - len(_STAGE_SUCCESS[s]) for s in _STAGES
    )


@pytest.mark.parametrize(("stage", "code"), _FAILURE_CASES)
def test_every_non_success_ending_stops_with_its_code_and_stores_nothing(
    tmp_path: Path, stage: str, code: RelayCode
) -> None:
    failing = _scripted_for(code)
    first = failing[0]
    if isinstance(first, HttpResponse):
        assert _PLANT.encode() in first.body  # the planted string is on the wire
    run = _register(tmp_path, _staged(stage, failing))
    assert isinstance(run.result, RelayConnectFailed)
    expected = _expected(code)
    assert run.result.instance == "relay"
    assert run.result.code is expected
    assert run.result.explanation == explain(expected)
    assert run.result.next_step == relay_next_step(
        expected, name="relay", retry_after_s=run.result.retry_after_s
    )
    # The failing request is the stage's own and the last one made.
    assert len(run.transport.requests) == _PREFIX[stage] + 1
    assert run.clock.sleeps == ([10] if stage == "poll" else [])
    assert _PLANT not in repr(run.result)
    assert (stage == "poll") == (len(run.shown) == 1)
    assert _stored_files(tmp_path) == []
    assert not (tmp_path / "credentials").exists()
    _assert_not_written(tmp_path, _EMAIL, _POLL_SECRET, _TOKEN)


@pytest.mark.parametrize(("stage", "code"), _FAILURE_CASES)
def test_any_failed_registration_leaves_an_existing_token_untouched(
    tmp_path: Path, stage: str, code: RelayCode
) -> None:
    run_relay_connect(
        _instance(),
        _OLD_TOKEN,
        store=_store(tmp_path),
        transport=FakeTransport([_envelope(RelayCode.OK)]),
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
    )
    path = tmp_path / "credentials" / "relay.toml"
    before = path.read_bytes()
    assert _OLD_TOKEN.encode() in before
    run = _register(tmp_path, _staged(stage, _scripted_for(code)))
    assert isinstance(run.result, RelayConnectFailed)
    assert path.read_bytes() == before
    assert _stored_files(tmp_path) == ["relay.toml"]


def test_a_pending_answer_carrying_data_stops_as_malformed(tmp_path: Path) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(), _envelope(RelayCode.REGISTRATION_PENDING, {"n": 1})]
        + [_issued()],
    )
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.ANSWER_MALFORMED
    assert len(run.transport.requests) == 3
    assert _stored_files(tmp_path) == []


@pytest.mark.parametrize(
    "issued",
    [
        _envelope(RelayCode.REGISTRATION_ISSUED, {"token": "not-a-relay-token"}),
        _envelope(RelayCode.REGISTRATION_ISSUED, {}),
        _envelope(RelayCode.REGISTRATION_ISSUED, {"token": _TOKEN, "extra": _PLANT}),
    ],
    ids=["bad-token", "no-token", "extra-key"],
)
def test_an_issued_answer_without_a_valid_token_stores_nothing(
    tmp_path: Path, issued: HttpResponse
) -> None:
    run = _register(tmp_path, [_caps(), _started(), issued, _issued()])
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.ANSWER_MALFORMED
    assert len(run.transport.requests) == 3
    assert _stored_files(tmp_path) == []
    assert _PLANT not in repr(run.result)


# --------------------------------------------------------------------------
# Req 13.4: the started answer is validated before anything is shown
# --------------------------------------------------------------------------

_BAD_STARTED = {
    "user-code-wrong-shape": _started(user_code="abcd-efgh"),
    "user-code-vowel": _started(user_code="ABCD-EFGH"),
    "user-code-type": _started(user_code=12),
    "poll-secret-short": _started(poll_secret="short"),
    "interval-zero": _started(interval_s=0),
    "interval-over-max": _started(interval_s=MAX_POLL_INTERVAL_S + 1),
    "expiry-under-min": _started(expires_in_s=59),
    "expiry-over-max": _started(expires_in_s=3601),
    "extra-key": _started(extra={"note": _PLANT}),
    "empty": _envelope(RelayCode.REGISTRATION_STARTED, {}),
}


@pytest.mark.parametrize("name", list(_BAD_STARTED))
def test_a_malformed_started_answer_shows_nothing_and_stops(
    tmp_path: Path, name: str
) -> None:
    run = _register(tmp_path, [_caps(), _BAD_STARTED[name], _issued(), _issued()])
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.code is RelayCode.ANSWER_MALFORMED
    assert run.shown == []
    assert len(run.transport.requests) == 2
    assert run.clock.sleeps == []
    assert _stored_files(tmp_path) == []
    assert _PLANT not in repr(run.result)


def test_only_the_user_code_the_relay_sent_is_shown_and_no_other_value(
    tmp_path: Path,
) -> None:
    run = _register(tmp_path, [_caps(), _started(), _issued()])
    assert [f.name for f in RegistrationShown.__dataclass_fields__.values()] == [
        "email",
        "user_code",
        "expires_in_s",
    ]
    assert _POLL_SECRET not in repr(run.shown)
    assert _POLL_SECRET not in repr(run.result)


# --------------------------------------------------------------------------
# Req 13.2 (engine side), 13.10: the email is validated and never kept
# --------------------------------------------------------------------------

_BAD_EMAILS = [
    "",
    "no-at-sign",
    "a@b",
    "two words@example.org",
    "a@@example.org",
    "x" * 250 + "@example.org",
    _EMAIL + "\n",
]


@pytest.mark.parametrize("bad", _BAD_EMAILS)
def test_an_implausible_email_is_refused_before_any_request(
    tmp_path: Path, bad: str
) -> None:
    transport = FakeTransport([_caps(), _started(), _issued()])
    shown: list[RegistrationShown] = []
    with pytest.raises(RegistrationEmailError) as raised:
        run_relay_registration(
            _instance(),
            bad,
            store=_store(tmp_path),
            transport=transport,
            environ={},
            now=lambda: _CLOCK,
            sleep=lambda seconds: None,
            redactor=Redactor(),
            on_started=shown.append,
        )
    assert transport.requests == []
    assert shown == []
    assert str(raised.value) == "That is not a plausible email address."
    assert not (tmp_path / "credentials").exists()


def test_neither_the_email_nor_the_poll_secret_is_written_anywhere(
    tmp_path: Path,
) -> None:
    run = _register(tmp_path, [_caps(), _started(), _pending(), _issued()])
    assert isinstance(run.result, RelayConnected)
    written = _all_written_bytes(tmp_path)
    assert list(written) == [str(Path("credentials") / "relay.toml")]  # non-vacuous
    assert _TOKEN.encode() in written["credentials/relay.toml"]
    _assert_not_written(tmp_path, _EMAIL, _POLL_SECRET)
    assert _EMAIL not in repr(run.result)


# --------------------------------------------------------------------------
# Req 13.10, 15.4: redaction before first use
# --------------------------------------------------------------------------


def test_the_poll_secret_and_the_issued_token_are_redacted(tmp_path: Path) -> None:
    redactor = Redactor()
    seen: list[tuple[str, str]] = []
    base = FakeTransport([_caps(), _started(), _issued()])

    def transport(request: HttpRequest, timeout: float) -> HttpResponse:
        seen.append((request.url.removeprefix(_BASE), redactor.redact(_POLL_SECRET)))
        return base(request, timeout)

    assert redactor.redact(_POLL_SECRET) == _POLL_SECRET  # false beforehand
    assert redactor.redact(_TOKEN) == _TOKEN
    result = run_relay_registration(
        _instance(),
        _EMAIL,
        store=_store(tmp_path),
        transport=transport,
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=redactor,
        on_started=lambda shown: None,
    )
    assert isinstance(result, RelayConnected)
    # Not yet known when the capabilities and start requests go out; known by
    # the time the first poll sends it.
    assert [url for url, _ in seen] == [
        ROUTE_CAPABILITIES,
        ROUTE_REGISTRATIONS,
        ROUTE_REGISTRATION_POLL,
    ]
    assert [value for _, value in seen[:2]] == [_POLL_SECRET, _POLL_SECRET]
    assert seen[2][1] == REDACTED
    assert redactor.redact(f"a {_POLL_SECRET} b") == f"a {REDACTED} b"
    assert redactor.redact(f"a {_TOKEN} b") == f"a {REDACTED} b"


# --------------------------------------------------------------------------
# Req 15.2: capabilities, start and a poll each make exactly one transport call
# --------------------------------------------------------------------------

_RETRYABLE = {
    "503-envelope": lambda: _envelope(RelayCode.UNAVAILABLE),
    "503-plain": lambda: HttpResponse(status=503, headers={}, body=b"<html/>"),
    "429-plain": lambda: HttpResponse(
        status=429, headers={"retry-after": "1"}, body=b""
    ),
    "429-envelope": lambda: _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 1}),
}


@pytest.mark.parametrize("stage", _STAGES)
@pytest.mark.parametrize("variant", list(_RETRYABLE))
def test_a_503_and_a_429_each_produce_exactly_one_transport_call_per_request(
    tmp_path: Path, stage: str, variant: str
) -> None:
    run = _register(tmp_path, _staged(stage, [_RETRYABLE[variant]()]))
    assert isinstance(run.result, RelayConnectFailed)
    assert len(run.transport.requests) == _PREFIX[stage] + 1
    assert _stored_files(tmp_path) == []
    assert run.clock.sleeps == ([10] if stage == "poll" else [])


def test_the_429_wait_the_relay_stated_reaches_the_result(tmp_path: Path) -> None:
    run = _register(
        tmp_path,
        [_caps(), _started(), _envelope(RelayCode.RATE_LIMITED, {"retry_after_s": 37})],
    )
    assert isinstance(run.result, RelayConnectFailed)
    assert run.result.retry_after_s == 37
    assert run.result.next_step == "Wait 37 seconds, then try again."


# --------------------------------------------------------------------------
# Req 13.9: an interrupt from sleep propagates with nothing stored
# --------------------------------------------------------------------------


@pytest.mark.parametrize("interrupt_at", [1, 2, 3])
def test_an_interrupt_from_sleep_propagates_and_nothing_is_stored(
    tmp_path: Path, interrupt_at: int
) -> None:
    clock = _Clock()
    count = 0
    transport = FakeTransport(
        [_caps(), _started(), _pending(), _pending(), _issued(), _issued()]
    )

    def sleep(seconds: float) -> None:
        nonlocal count
        count += 1
        if count == interrupt_at:
            raise KeyboardInterrupt
        clock.sleep(seconds)

    with pytest.raises(KeyboardInterrupt):
        run_relay_registration(
            _instance(),
            _EMAIL,
            store=_store(tmp_path),
            transport=transport,
            environ={},
            now=clock.now,
            sleep=sleep,
            redactor=Redactor(),
            on_started=lambda shown: None,
        )
    assert len(transport.requests) == 2 + (interrupt_at - 1)
    assert not (tmp_path / "credentials").exists()
    _assert_not_written(tmp_path, _EMAIL, _POLL_SECRET, _TOKEN)


# --------------------------------------------------------------------------
# The style guard
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "style",
    [style for style in AuthStyle if style is not AuthStyle.RELAY_TOKEN],
    ids=lambda style: style.value,
)
def test_a_connector_that_is_not_a_relay_token_connector_is_refused_untouched(
    tmp_path: Path, style: AuthStyle
) -> None:
    from fitdocs.connectors.settings import ConnectorInstance

    class _KeyConnector:
        connector_id = "key"
        display_name = "key"
        auth_style = style
        capabilities: frozenset[object] = frozenset()
        credential_fields = ()

    instance = ConnectorInstance(
        name="key",
        connector=_KeyConnector(),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )
    transport = FakeTransport([])
    with pytest.raises(AssertionError):
        run_relay_registration(
            instance,
            _EMAIL,
            store=_store(tmp_path),
            transport=transport,
            environ={},
            now=lambda: _CLOCK,
            sleep=lambda seconds: None,
            redactor=Redactor(),
            on_started=lambda shown: None,
        )
    assert transport.requests == []
    assert not (tmp_path / "credentials").exists()


def test_a_connector_that_reports_issued_without_a_token_stops_as_malformed(
    tmp_path: Path,
) -> None:
    from fitdocs.connectors.protocol import (
        RegistrationPolled,
        RegistrationStarted,
        RelayCapabilities,
    )
    from fitdocs.connectors.settings import ConnectorInstance

    class _Odd:
        connector_id = "relay"
        display_name = "odd"
        auth_style = AuthStyle.RELAY_TOKEN
        capabilities: frozenset[object] = frozenset()
        credential_fields = ()

        def read_capabilities(self, session: object) -> RelayCapabilities:
            return RelayCapabilities(envelopes=(1,), registration=True, targets=())

        def start_registration(
            self, session: object, email: str
        ) -> RegistrationStarted:
            return RegistrationStarted(
                user_code=_USER_CODE,
                poll_secret=session.secret(_POLL_SECRET),  # type: ignore[attr-defined]
                interval_s=5,
                expires_at=_CLOCK + timedelta(seconds=600),
            )

        def poll_registration(
            self, session: object, started: object
        ) -> RegistrationPolled:
            return RegistrationPolled(code=RelayCode.REGISTRATION_ISSUED, token=None)

    instance = ConnectorInstance(
        name="odd",
        connector=_Odd(),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )
    result = run_relay_registration(
        instance,
        _EMAIL,
        store=_store(tmp_path),
        transport=FakeTransport([]),
        environ={},
        now=lambda: _CLOCK,
        sleep=lambda seconds: None,
        redactor=Redactor(),
        on_started=lambda shown: None,
    )
    assert isinstance(result, RelayConnectFailed)
    assert result.code is RelayCode.ANSWER_MALFORMED
    assert _stored_files(tmp_path) == []


@pytest.mark.parametrize(
    "code",
    [RelayCode.OK, RelayCode.REGISTRATION_STARTED, RelayCode.NOT_OFFERED],
    ids=lambda c: c.value,
)
def test_a_poll_result_with_a_code_that_is_not_a_poll_code_stops_as_malformed(
    tmp_path: Path, code: RelayCode
) -> None:
    from fitdocs.connectors.protocol import (
        RegistrationPolled,
        RegistrationStarted,
        RelayCapabilities,
    )
    from fitdocs.connectors.settings import ConnectorInstance

    polls: list[object] = []

    class _Odd:
        connector_id = "relay"
        display_name = "odd"
        auth_style = AuthStyle.RELAY_TOKEN
        capabilities: frozenset[object] = frozenset()
        credential_fields = ()

        def read_capabilities(self, session: object) -> RelayCapabilities:
            return RelayCapabilities(envelopes=(1,), registration=True, targets=())

        def start_registration(
            self, session: object, email: str
        ) -> RegistrationStarted:
            return RegistrationStarted(
                user_code=_USER_CODE,
                poll_secret=session.secret(_POLL_SECRET),  # type: ignore[attr-defined]
                interval_s=7,
                expires_at=_CLOCK + timedelta(seconds=600),
            )

        def poll_registration(
            self, session: object, started: object
        ) -> RegistrationPolled:
            polls.append(started)
            return RegistrationPolled(code=code, token=None)

    clock = _Clock()
    instance = ConnectorInstance(
        name="odd",
        connector=_Odd(),  # type: ignore[arg-type]
        lookback_days=30,
        settings=None,
    )
    result = run_relay_registration(
        instance,
        _EMAIL,
        store=_store(tmp_path),
        transport=FakeTransport([]),
        environ={},
        now=clock.now,
        sleep=clock.sleep,
        redactor=Redactor(),
        on_started=lambda shown: None,
    )
    assert isinstance(result, RelayConnectFailed)
    assert result.code is RelayCode.ANSWER_MALFORMED
    assert len(polls) == 1
    assert clock.sleeps == [7]
    assert _stored_files(tmp_path) == []


def test_a_clock_already_past_the_deadline_shows_zero_seconds_and_expires_unpolled(
    tmp_path: Path,
) -> None:
    reads = 0

    def now() -> datetime:
        nonlocal reads
        reads += 1
        # The connector's read (the start) sees the start; later reads are
        # long past the 60 s expiry.
        return _CLOCK if reads == 1 else _CLOCK + timedelta(seconds=500)

    transport = FakeTransport(
        [_caps(), _started(expires_in_s=60), _issued(), _issued()]
    )
    shown: list[RegistrationShown] = []
    result = run_relay_registration(
        _instance(),
        _EMAIL,
        store=_store(tmp_path),
        transport=transport,
        environ={},
        now=now,
        sleep=lambda seconds: None,
        redactor=Redactor(),
        on_started=shown.append,
    )
    assert shown == [RegistrationShown(_EMAIL, _USER_CODE, expires_in_s=0)]
    assert isinstance(result, RelayConnectFailed)
    assert result.code is RelayCode.REGISTRATION_EXPIRED
    assert len(transport.requests) == 2  # capabilities and start, no poll
    assert _stored_files(tmp_path) == []
