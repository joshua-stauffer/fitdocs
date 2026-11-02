"""RelayLogs: JSON lines on stdout, and no secret in any record (9.8, 9.9)."""

from __future__ import annotations

import io
import json
import logging
import re
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from fitdocs_relay import logs
from fitdocs_relay.logs import (
    JsonFormatter,
    RedactingFilter,
    SecretRedactor,
    configure_logging,
    log_event,
)

TOKEN = "fdr1_" + "abcdefghijklmnop" + "_" + "qrstuvwxyz234567" * 3 + "abcd"
OTHER_TOKEN = "fdr1_" + "zzzzzzzzzzzzzzzz" + "_" + "2" * 52
PEPPER = "pepper-Zq8wLkT3mVx9RbN5cHd7YsJ1fGa4PoE6uIt0KhXyAeQ"
PASSWORD = "hunter2-db-passw0rd"
SECRETS = (TOKEN, OTHER_TOKEN, PEPPER, PASSWORD)

assert len(TOKEN) == len("fdr1_") + 16 + 1 + 52


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    names = ["", "uvicorn", "uvicorn.error", "uvicorn.access", "fitdocs_relay"]
    saved = [
        (n, list(logging.getLogger(n).handlers), logging.getLogger(n).level)
        for n in names
    ]
    propagate = {n: logging.getLogger(n).propagate for n in names}
    yield
    for name, handlers, level in saved:
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
    for name, value in propagate.items():
        logging.getLogger(name).propagate = value


def test_extra_secrets_share_one_longest_first_redactor_with_pepper_and_password() -> (
    None
):
    extra = "extra-" + PEPPER + "-tail"
    buffer = io.StringIO()
    configure_logging(
        pepper=PEPPER, password=PASSWORD, extra_secrets=(extra,), stream=buffer
    )
    logging.getLogger("fitdocs_relay.test").info(f"a {extra} b {PASSWORD} c {PEPPER}")
    text = buffer.getvalue()
    assert "extra-" not in text
    assert "-tail" not in text
    assert PASSWORD not in text
    assert PEPPER not in text
    assert "a [redacted] b [redacted] c [redacted]" in text


@pytest.fixture
def out() -> io.StringIO:
    buffer = io.StringIO()
    configure_logging(pepper=PEPPER, password=PASSWORD, stream=buffer)
    return buffer


def lines(buffer: io.StringIO) -> list[dict[str, object]]:
    text = buffer.getvalue()
    assert text.endswith("\n")
    rows = [json.loads(line) for line in text.splitlines()]
    assert rows, "nothing was logged"
    return rows


def assert_clean(text: str) -> None:
    for secret in SECRETS:
        assert secret not in text


# --- fields ------------------------------------------------------------------


def test_request_event_has_the_designed_fields_in_order(out: io.StringIO) -> None:
    log_event(
        logging.getLogger("fitdocs_relay.app"),
        "request",
        request_id="req-1",
        method="POST",
        route="/v1/token",
        status=429,
        code="rate-limited",
        duration_ms=12,
        token_id="abcdefghijklmnop",
    )
    (row,) = lines(out)
    assert list(row) == [
        "ts",
        "level",
        "event",
        "request_id",
        "method",
        "route",
        "status",
        "code",
        "duration_ms",
        "token_id",
    ]
    assert row["level"] == "INFO"
    assert row["event"] == "request"
    assert row["route"] == "/v1/token"
    assert row["status"] == 429
    assert row["duration_ms"] == 12
    assert row["token_id"] == "abcdefghijklmnop"
    assert row["code"] == "rate-limited"
    assert row["request_id"] == "req-1"
    assert row["method"] == "POST"


def test_unmatched_route_and_unauthenticated_request_keep_null_and_omit_token_id(
    out: io.StringIO,
) -> None:
    log_event(
        logging.getLogger("fitdocs_relay.app"),
        "request",
        request_id="r",
        method="GET",
        route=None,
        status=404,
        code="not-found",
        duration_ms=0,
    )
    (row,) = lines(out)
    assert "route" in row
    assert row["route"] is None
    assert "token_id" not in row
    assert row["duration_ms"] == 0


def test_timestamp_is_utc_iso_8601(out: io.StringIO) -> None:
    before = datetime.now().astimezone()
    log_event(logging.getLogger("fitdocs_relay"), "startup", port=8080)
    (row,) = lines(out)
    ts = row["ts"]
    assert isinstance(ts, str)
    assert ts.endswith("Z")
    parsed = datetime.fromisoformat(ts)
    assert parsed.utcoffset() is not None
    assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    assert abs((parsed - before).total_seconds()) < 60


def test_startup_event_carries_integers_and_codes_only(out: io.StringIO) -> None:
    log_event(
        logging.getLogger("fitdocs_relay.serve"),
        "migrated",
        applied=2,
        client="203.0.113.9",
        body="secret body",
    )
    (row,) = lines(out)
    assert row["applied"] == 2
    assert "client" not in row
    assert "body" not in row
    assert "203.0.113.9" not in out.getvalue()
    assert "secret body" not in out.getvalue()


def test_values_that_are_not_scalars_are_dropped_and_floats_stay_finite(
    out: io.StringIO,
) -> None:
    log_event(
        logging.getLogger("fitdocs_relay.app"),
        "request",
        route=object(),
        method=["GET"],
        duration_ms=float("nan"),
        status=200,
    )
    (row,) = lines(out)
    assert "route" not in row
    assert "method" not in row
    assert "duration_ms" not in row
    assert row["status"] == 200


def test_output_is_one_object_per_line_on_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(pepper=PEPPER, password=None)
    log = logging.getLogger("fitdocs_relay.app")
    log_event(log, "first")
    log.info("multi\nline\r\nmessage")
    captured = capsys.readouterr()
    assert captured.err == ""
    rows = captured.out.splitlines()
    assert len(rows) == 2
    assert [json.loads(r)["event"] for r in rows] == ["first", "multi\nline\r\nmessage"]


def test_configuring_twice_does_not_double_the_output(out: io.StringIO) -> None:
    again = io.StringIO()
    configure_logging(pepper=PEPPER, password=PASSWORD, stream=again)
    log_event(logging.getLogger("fitdocs_relay"), "once")
    assert out.getvalue() == ""
    assert len(lines(again)) == 1


def test_level_threshold_is_applied() -> None:
    quiet = io.StringIO()
    configure_logging(pepper=PEPPER, password=None, level="WARNING", stream=quiet)
    log = logging.getLogger("fitdocs_relay")
    log.debug("d")
    log.info("quiet")
    log.warning("loud")
    assert [r["event"] for r in lines(quiet)] == ["loud"]

    verbose = io.StringIO()
    configure_logging(pepper=PEPPER, password=None, level="DEBUG", stream=verbose)
    log.debug("d")
    log.info("i")
    assert [r["event"] for r in lines(verbose)] == ["d", "i"]


# --- redaction: every place a secret can enter a record ----------------------


def _by_message(log: logging.Logger) -> None:
    log.info("planted %s %s %s", TOKEN, PEPPER, PASSWORD)


def _by_literal_message(log: logging.Logger) -> None:
    log.info(f"token={TOKEN} pepper={PEPPER} password={PASSWORD}")


def _by_args_mapping(log: logging.Logger) -> None:
    log.info("%(t)s %(p)s %(w)s", {"t": TOKEN, "p": PEPPER, "w": PASSWORD})


def _by_extra_string_fields(log: logging.Logger) -> None:
    log_event(
        log,
        f"event-{TOKEN}",
        request_id=PEPPER,
        method=PASSWORD,
        route=f"/x/{TOKEN}",
        code=OTHER_TOKEN,
        token_id=f"{PEPPER}{PASSWORD}",
    )


def _by_non_string_message(log: logging.Logger) -> None:
    log.info(("tuple-message", TOKEN, PEPPER, PASSWORD))


def _by_exception_message_and_local(log: logging.Logger) -> None:
    local = f"{TOKEN} {PEPPER} {PASSWORD}"
    try:
        raise RuntimeError(local)
    except RuntimeError:
        log.error("boom", exc_info=True)


def _by_chained_exception(log: logging.Logger) -> None:
    try:
        try:
            raise ValueError(PEPPER)
        except ValueError as inner:
            raise KeyError(PASSWORD) from inner
    except KeyError:
        log.exception("chained")


def test_every_entry_point_is_redacted_but_present_without_the_filter(
    out: io.StringIO,
) -> None:
    entries = [
        _by_message,
        _by_literal_message,
        _by_args_mapping,
        _by_extra_string_fields,
        _by_non_string_message,
    ]
    for entry in entries:
        out.seek(0)
        out.truncate()
        entry(logging.getLogger("fitdocs_relay.app"))
        (row,) = lines(out)
        assert_clean(out.getvalue())
        assert logs.REDACTED in out.getvalue(), entry.__name__
        assert row["level"] == "INFO"

        # Reachability: the same record through the formatter alone does carry
        # the secrets, so the filter is what removes them.
        raw = io.StringIO()
        handler = logging.StreamHandler(raw)
        handler.setFormatter(JsonFormatter())
        bare = logging.getLogger(f"bare.{entry.__name__}")
        bare.propagate = False
        bare.addHandler(handler)
        entry(bare)
        assert any(s in raw.getvalue() for s in SECRETS), entry.__name__


def test_extra_fields_each_secret_alone_is_redacted(out: io.StringIO) -> None:
    for field in ("request_id", "method", "route", "code", "token_id"):
        for secret in SECRETS:
            out.seek(0)
            out.truncate()
            logging.getLogger("fitdocs_relay").info(
                "e", extra={"event": "e", field: secret}
            )
            (row,) = lines(out)
            assert row[field] == logs.REDACTED, (field, secret)


def test_event_name_is_redacted(out: io.StringIO) -> None:
    log_event(logging.getLogger("fitdocs_relay"), TOKEN)
    (row,) = lines(out)
    assert row["event"] == logs.REDACTED


def test_logger_name_cannot_carry_a_secret(out: io.StringIO) -> None:
    named = logging.getLogger(f"app.{TOKEN}.{PEPPER}")
    named.info("hello")
    named.info("planted %s", named.name)
    assert_clean(out.getvalue())
    assert len(lines(out)) == 2


def test_record_name_is_redacted_by_the_filter() -> None:
    record = logging.LogRecord(f"a.{TOKEN}", logging.INFO, "f", 1, "m", None, None)
    RedactingFilter(SecretRedactor(PEPPER, PASSWORD)).filter(record)
    assert record.name == f"a.{logs.REDACTED}"


def test_token_mid_word_and_in_a_url_query_is_redacted(out: io.StringIO) -> None:
    log = logging.getLogger("fitdocs_relay")
    log.info("prefix%ssuffix", TOKEN)
    log.info("GET /v1/thing?x=1&token=%s&y=2 HTTP/1.1", TOKEN)
    log.info("%s,%s;%s", TOKEN, OTHER_TOKEN, TOKEN)
    rows = lines(out)
    assert_clean(out.getvalue())
    assert rows[0]["event"] == f"prefix{logs.REDACTED}suffix"
    assert rows[1]["event"] == f"GET /v1/thing?x=1&token={logs.REDACTED}&y=2 HTTP/1.1"
    assert rows[2]["event"] == f"{logs.REDACTED},{logs.REDACTED};{logs.REDACTED}"


def test_non_secrets_pass_through_unchanged(out: io.StringIO) -> None:
    near_miss = "fdr1_" + "a" * 16 + "_" + "b" * 51  # one character short
    upper = "FDR1_" + "a" * 16 + "_" + "b" * 52
    logging.getLogger("fitdocs_relay").info("%s | %s | plain text", near_miss, upper)
    (row,) = lines(out)
    assert row["event"] == f"{near_miss} | {upper} | plain text"


def test_token_pattern_comes_from_the_shared_envelope() -> None:
    from fitdocs_relay.shared import relay_envelope

    redact = SecretRedactor()
    assert redact(f"[{TOKEN}]") == f"[{logs.REDACTED}]"
    # The format is read from the shared constant, not restated here.
    assert re.fullmatch(relay_envelope.TOKEN_RE, TOKEN)
    source = Path(logs.__file__).read_text(encoding="utf-8")
    assert "fdr1" not in source
    assert "a-z2-7" not in source


def test_pepper_as_bytes_and_empty_secrets() -> None:
    redact = SecretRedactor(PEPPER.encode("utf-8"), "", None, b"")
    assert redact(f"x{PEPPER}y") == f"x{logs.REDACTED}y"
    assert redact("nothing to hide") == "nothing to hide"


def test_overlapping_secrets_are_replaced_whole() -> None:
    redact = SecretRedactor("abc", "abcdef")
    assert redact("1abcdef2") == f"1{logs.REDACTED}2"


# --- uvicorn -----------------------------------------------------------------


def test_uvicorn_loggers_are_routed_through_the_formatter_and_filter(
    out: io.StringIO,
) -> None:
    logging.getLogger("uvicorn.error").error("failed for %s", TOKEN)
    logging.getLogger("uvicorn").info("Started with %s", PEPPER)
    rows = lines(out)
    assert len(rows) == 2
    assert_clean(out.getvalue())
    assert rows[0]["event"] == f"failed for {logs.REDACTED}"
    assert rows[1]["event"] == f"Started with {logs.REDACTED}"
    assert [r["level"] for r in rows] == ["ERROR", "INFO"]


def test_uvicorn_access_log_is_silent(
    out: io.StringIO, capsys: pytest.CaptureFixture[str]
) -> None:
    access = logging.getLogger("uvicorn.access")
    assert access.propagate is False
    # With a handler present the logging module's stderr fallback is not used.
    assert any(isinstance(h, logging.NullHandler) for h in access.handlers)
    access.info(
        '%s - "%s %s HTTP/%s" %d',
        "198.51.100.7",
        "GET",
        f"/v1/token/revoke?token={TOKEN}",
        "1.1",
        200,
    )
    access.warning("198.51.100.7 warned")
    assert out.getvalue() == ""
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_uvicorn_exception_record_is_reduced(out: io.StringIO) -> None:
    log = logging.getLogger("uvicorn.error")
    try:
        raise OSError(f"cannot bind {PEPPER}")
    except OSError:
        log.exception("Exception in ASGI application")
    (row,) = lines(out)
    assert_clean(out.getvalue())
    assert row["error_type"] == "OSError"


def test_handlers_uvicorn_installed_itself_are_removed() -> None:
    leftover = io.StringIO()
    theirs = logging.StreamHandler(leftover)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.addHandler(theirs)
        lg.propagate = False
    buffer = io.StringIO()
    configure_logging(pepper=PEPPER, password=PASSWORD, stream=buffer)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).warning("secret %s", TOKEN)
    assert leftover.getvalue() == ""
    assert len(lines(buffer)) == 2
    assert_clean(buffer.getvalue())


def test_logs_module_does_not_import_uvicorn() -> None:
    import ast

    tree = ast.parse(Path(logs.__file__).read_text(encoding="utf-8"))
    imported = {
        (n.module or "").split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
    } | {
        a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import)
        for a in n.names
    }
    assert imported, "the walk saw no imports"
    assert "uvicorn" not in imported


# --- failures ----------------------------------------------------------------


def _raise_deep(secret: str) -> None:
    local_secret = secret + "-local"
    raise RuntimeError(f"{secret} {local_secret}")


def _call_deep(secret: str) -> None:
    _raise_deep(secret)


def test_failure_record_is_type_and_frames_only(out: io.StringIO) -> None:
    secret = "msg-secret-7f3a"
    try:
        _call_deep(secret)
    except RuntimeError:
        logging.getLogger("fitdocs_relay.app").error(
            "relay-failure", exc_info=True, extra={"event": "relay-failure"}
        )
    (row,) = lines(out)
    text = out.getvalue()
    assert secret not in text
    assert "-local" not in text
    assert row["event"] == "relay-failure"
    assert row["error_type"] == "RuntimeError"
    frames = row["frames"]
    assert isinstance(frames, list)
    assert [f["function"] for f in frames][-2:] == ["_call_deep", "_raise_deep"]
    for frame in frames:
        assert set(frame) == {"file", "line", "function"}
        assert isinstance(frame["line"], int)
    assert frames[-1]["file"] == __file__
    assert frames[-1]["line"] == _raise_deep.__code__.co_firstlineno + 2
    assert "Traceback" not in text
    assert "RuntimeError:" not in text


def test_failure_in_every_secret_path_prints_no_secret(out: io.StringIO) -> None:
    log = logging.getLogger("fitdocs_relay.app")
    for entry in (_by_exception_message_and_local, _by_chained_exception):
        out.seek(0)
        out.truncate()
        entry(log)
        (row,) = lines(out)
        assert_clean(out.getvalue())
        assert "frames" in row
        assert row["error_type"] in {"RuntimeError", "KeyError"}


def test_formatter_alone_never_prints_the_exception_message() -> None:
    raw = io.StringIO()
    handler = logging.StreamHandler(raw)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("bare.exc")
    log.propagate = False
    log.addHandler(handler)
    try:
        raise RuntimeError("do-not-print-me")
    except RuntimeError:
        log.exception("failed")
    assert "do-not-print-me" not in raw.getvalue()
    assert json.loads(raw.getvalue())["error_type"] == "RuntimeError"


def test_an_unformattable_message_does_not_crash_or_leak(out: io.StringIO) -> None:
    logging.getLogger("fitdocs_relay").info("%d %d", TOKEN)
    (row,) = lines(out)
    assert_clean(out.getvalue())
    assert row["event"] == "[unformattable log message]"


def test_default_stream_is_stdout_resolved_at_call_time(
    capsys: pytest.CaptureFixture[str],
) -> None:
    handler = configure_logging(pepper=PEPPER, password=PASSWORD)
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stdout


# --- caller-supplied failure fields, ordering, ASCII ---------------------------


def test_caller_supplied_failure_fields_are_redacted(out: io.StringIO) -> None:
    log_event(
        logging.getLogger("fitdocs_relay"),
        "e",
        error_type=f"X{PASSWORD}{PEPPER}",
        frames=[{"file": TOKEN, "line": 3, "function": f"f{PEPPER}"}],
    )
    (row,) = lines(out)
    assert_clean(out.getvalue())
    assert row["error_type"] == f"X{logs.REDACTED}{logs.REDACTED}"
    assert row["frames"] == [
        {"file": logs.REDACTED, "line": 3, "function": f"f{logs.REDACTED}"}
    ]


@pytest.mark.parametrize(
    "frames",
    [
        [object()],
        object(),
        "frames",
        [{"file": "a", "line": 1}],
        [{"file": "a", "line": 1, "function": "f", "locals": TOKEN}],
        [{"file": 1, "line": 1, "function": "f"}],
        [{"file": "a", "line": "1", "function": "f"}],
        [{"file": "a", "line": True, "function": "f"}],
        [{"file": {TOKEN}, "line": 1, "function": "f"}],
    ],
)
def test_invalid_caller_frames_are_dropped_without_a_logging_error(
    out: io.StringIO, capsys: pytest.CaptureFixture[str], frames: object
) -> None:
    log_event(logging.getLogger("fitdocs_relay"), "e", frames=frames, error_type=7)
    (row,) = lines(out)
    assert "frames" not in row
    assert "error_type" not in row
    assert_clean(out.getvalue())
    assert capsys.readouterr().err == ""


def test_formatter_alone_survives_invalid_caller_frames() -> None:
    raw = io.StringIO()
    handler = logging.StreamHandler(raw)
    handler.setFormatter(JsonFormatter())
    log = logging.getLogger("bare.frames")
    log.setLevel(logging.INFO)
    log.propagate = False
    log.addHandler(handler)
    log_event(log, "e", frames=[object()], error_type=object())
    assert list(json.loads(raw.getvalue())) == ["ts", "level", "event"]


def test_token_is_redacted_whole_even_when_a_short_secret_is_inside_it() -> None:
    secret_part = TOKEN.split("_")[2]
    short = secret_part[10:14]
    assert short in TOKEN
    text = SecretRedactor(short, PEPPER)(f"x {TOKEN} y")
    assert text == f"x {logs.REDACTED} y"


def test_output_is_ascii_and_one_line_for_unicode_line_separators(
    out: io.StringIO,
) -> None:
    logging.getLogger("fitdocs_relay").info("a\u2028b\u0085c\u2029d\x1ce\u00e9")
    assert out.getvalue().isascii()
    assert len(out.getvalue().splitlines()) == 1
    (row,) = lines(out)
    assert row["event"] == "a\u2028b\u0085c\u2029d\x1ce\u00e9"
