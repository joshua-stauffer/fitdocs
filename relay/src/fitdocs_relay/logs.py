"""Secret-free JSON-lines logs on standard output (RelayLogs, Requirements 9.8, 9.9).

One JSON object per line. A record carries only the fields below (strings only
under the named request fields, plus the failure fields), and a last-line
redacting filter replaces anything matching the token format, the pepper or the
database password in every string the formatter can print.

uvicorn is configured here by logger name only (it may be imported in `serve`
alone): `uvicorn` and `uvicorn.error` pass through the same filter and
formatter; `uvicorn.access` is silenced (no handler, no propagation), so no
client address or query is ever logged by it.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sys
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import IO, Any, Final

from .shared.relay_envelope import TOKEN_RE

REDACTED: Final = "[redacted]"

# The token format with its anchors removed, so a token is found anywhere in a
# string (mid-word, in a URL query).
_TOKEN_ANYWHERE: Final = re.compile(TOKEN_RE.removeprefix("^").removesuffix("$"))

# String-valued fields, in output order, after `ts`, `level` and `event`.
REQUEST_FIELDS: Final[tuple[str, ...]] = (
    "request_id",
    "method",
    "route",
    "status",
    "code",
    "duration_ms",
    "token_id",
)
_STRING_FIELDS: Final = frozenset(
    {"event", "request_id", "method", "route", "code", "token_id"}
)
FAILURE_FIELDS: Final[tuple[str, ...]] = ("error_type", "frames")

_STANDARD: Final = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", *FAILURE_FIELDS}

_FRAME_KEYS: Final = frozenset({"file", "line", "function"})
_HANDLER_MARK: Final = "_fitdocs_relay_handler"
_UVICORN_LOGGERS: Final = ("uvicorn", "uvicorn.error", "uvicorn.access")


class SecretRedactor:
    """Replaces the token format and each registered secret with `[redacted]`."""

    def __init__(self, *secrets: str | bytes | None) -> None:
        found: set[str] = set()
        for secret in secrets:
            if isinstance(secret, bytes):
                secret = secret.decode("utf-8", errors="replace")
            if secret:
                found.add(secret)
        # Longest first, so a secret containing another is replaced whole.
        self._secrets = sorted(found, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        # The token pattern first: a short secret that is a substring of a
        # token would otherwise break the match and leave the rest printed.
        text = _TOKEN_ANYWHERE.sub(REDACTED, text)
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text


def failure_fields(
    exc_info: tuple[type[BaseException], BaseException, TracebackType | None]
    | tuple[None, None, None],
) -> dict[str, object]:
    """An exception as its type name and frame list; never message or locals."""
    exc_type, _value, tb = exc_info
    if exc_type is None:
        return {}
    frames = [
        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(tb)
    ]
    return {"error_type": exc_type.__name__, "frames": frames}


def _clean_frames(value: object, redact: Callable[[str], str]) -> list[object] | None:
    """`value` as a list of exactly {file, line, function} dicts, else None."""
    if not isinstance(value, list):
        return None
    cleaned: list[object] = []
    for frame in value:
        if not (isinstance(frame, dict) and set(frame) == _FRAME_KEYS):
            return None
        file, line, function = frame["file"], frame["line"], frame["function"]
        if not (
            isinstance(file, str)
            and isinstance(function, str)
            and isinstance(line, int)
            and not isinstance(line, bool)
        ):
            return None
        cleaned.append(
            {"file": redact(file), "line": line, "function": redact(function)}
        )
    return cleaned


def _clean_failure(
    record: logging.LogRecord, redact: Callable[[str], str]
) -> dict[str, object]:
    """The failure fields a caller put on `record`, validated; invalid ones dropped."""
    found: dict[str, object] = {}
    error_type = getattr(record, "error_type", None)
    if isinstance(error_type, str):
        found["error_type"] = redact(error_type)
    frames = _clean_frames(getattr(record, "frames", None), redact)
    if frames is not None:
        found["frames"] = frames
    return found


class RedactingFilter(logging.Filter):
    """Redacts the strings a record can print, and reduces exceptions."""

    def __init__(self, redactor: SecretRedactor) -> None:
        super().__init__()
        self._redact = redactor

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a bad format string or arguments
            message = "[unformattable log message]"
        record.msg = self._redact(message)
        record.args = ()
        record.name = self._redact(record.name)
        if record.exc_info and record.exc_info[0] is not None:
            for key, value in failure_fields(record.exc_info).items():
                setattr(record, key, value)
        else:
            cleaned = _clean_failure(record, self._redact)
            for key in FAILURE_FIELDS:
                if hasattr(record, key):
                    delattr(record, key)
            for key, value in cleaned.items():
                setattr(record, key, value)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        for key, value in list(record.__dict__.items()):
            if key not in _STANDARD and isinstance(value, str):
                setattr(record, key, self._redact(value))
        return True


def _scalar(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, int)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, event, then the allowed fields."""

    def format(self, record: logging.LogRecord) -> str:
        created = datetime.fromtimestamp(record.created, UTC)
        event = getattr(record, "event", None)
        out: dict[str, object] = {
            "ts": created.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "event": event if isinstance(event, str) else record.getMessage(),
        }
        for name in REQUEST_FIELDS:
            if not hasattr(record, name):
                continue
            value = getattr(record, name)
            if (name in _STRING_FIELDS and isinstance(value, str)) or _scalar(value):
                out[name] = value
        failure = _failure(record)
        out.update(failure)
        for name, value in record.__dict__.items():
            if name in _STANDARD or name in out or name == "event":
                continue
            if _scalar(value):  # None, bools, ints, finite floats; no strings
                out[name] = value
        return json.dumps(out, separators=(",", ":"), ensure_ascii=True)


def _failure(record: logging.LogRecord) -> dict[str, object]:
    if record.exc_info and record.exc_info[0] is not None:
        return failure_fields(record.exc_info)
    return _clean_failure(record, str)


def log_event(
    logger: logging.Logger, event: str, *, level: int = logging.INFO, **fields: Any
) -> None:
    """Log one named event with its fields (see `REQUEST_FIELDS`)."""
    logger.log(level, event, extra={"event": event, **fields})


def configure_logging(
    *,
    pepper: str | bytes | None,
    password: str | None,
    level: int | str = logging.INFO,
    stream: IO[str] | None = None,
) -> logging.Handler:
    """Route every log record, uvicorn's included, to stdout as redacted JSON lines."""
    handler = logging.StreamHandler(sys.stdout if stream is None else stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter(SecretRedactor(pepper, password)))
    setattr(handler, _HANDLER_MARK, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARK, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
    for name in _UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        for existing in list(logger.handlers):
            logger.removeHandler(existing)
        logger.propagate = name != "uvicorn.access"
    # Access records carry a client address and the query string; the access
    # log is off in `serve`, and this keeps it silent if it is ever turned on.
    logging.getLogger("uvicorn.access").addHandler(logging.NullHandler())
    return handler
