"""The one configuration reader: environment variables only, against the contract table.

Every `ConfigError` message is one fixed form `"<VARIABLE>: <reason>"` (or the
unknown-variable form); no value from the environment is ever interpolated, so
a secret cannot reach an error (Requirement 9.4). The `ConfigError` for an
unknown name carries that name, which is the variable being refused.
"""

from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlsplit

from fitdocs_relay.contract import (
    ENV_CLIENT_RATE_LIMIT,
    ENV_DATABASE_PASSWORD,
    ENV_DATABASE_URL,
    ENV_EXTENSIONS,
    ENV_FORWARDED_ALLOW_IPS,
    ENV_HOST,
    ENV_LOG_LEVEL,
    ENV_PORT,
    ENV_PREFIX,
    ENV_SHUTDOWN_GRACE,
    ENV_STRAVA_CLIENT_ID,
    ENV_TOKEN_PEPPER,
    ENV_TOKEN_RATE_LIMIT,
    ENVIRONMENT,
)

if TYPE_CHECKING:
    from fitdocs_relay.strava.config import StravaConfig, TargetsConfig

PEPPER_MIN_CHARACTERS = 43
PORT_RANGE = (1, 65535)
RATE_LIMIT_RANGE = (1, 100000)
GRACE_RANGE = (0, 600)
LOG_LEVELS = ("debug", "info", "warning", "error")


class ConfigError(Exception):
    """A configuration problem; names the variable, never a secret value."""

    def __init__(self, variable: str, message: str) -> None:
        super().__init__(message)
        self.variable = variable


@dataclass(frozen=True)
class SqliteTarget:
    path: Path


@dataclass(frozen=True)
class PostgresTarget:
    conninfo: str = field(repr=False)
    password: str | None = field(repr=False)


DatabaseTarget = SqliteTarget | PostgresTarget


@dataclass(frozen=True)
class RelayConfig:
    database: DatabaseTarget
    pepper: bytes = field(repr=False)
    host: str
    port: int
    forwarded_allow_ips: tuple[str, ...]
    token_limit_per_minute: int
    client_limit_per_minute: int
    shutdown_grace_s: int
    log_level: str
    extensions: tuple[str, ...]
    targets: TargetsConfig | None = None
    strava: StravaConfig | None = None


def _fail(variable: str, reason: str) -> ConfigError:
    return ConfigError(variable, f"{variable}: {reason}")


def _int_in_range(name: str, raw: str, bounds: tuple[int, int]) -> int:
    low, high = bounds
    if not (raw.isascii() and raw.isdigit()):
        raise _fail(name, f"must be an integer from {low} to {high}")
    value = int(raw)
    if not low <= value <= high:
        raise _fail(name, f"must be an integer from {low} to {high}")
    return value


_SQLITE_PREFIX = "sqlite:///"
_POSTGRES_SCHEMES = ("postgresql", "postgres")
_URL_REASON = (
    "must be a sqlite:/// or sqlite://// file path, "
    + "or a postgresql:// or postgres:// URL"
)


def _sqlite_target(raw: str) -> SqliteTarget:
    rest = raw[len(_SQLITE_PREFIX) :]
    if not rest or "?" in rest or "#" in rest or "\x00" in rest:
        raise _fail(ENV_DATABASE_URL, _URL_REASON)
    path = Path(rest)
    # Path() normalises (./, //, trailing /), so the in-memory and file: forms
    # are judged on the stored path and on every component of it.
    if (
        rest.endswith("/")
        or path.name in ("", ".", "..")
        or any(part == ":memory:" or part.startswith("file:") for part in path.parts)
    ):
        raise _fail(ENV_DATABASE_URL, _URL_REASON)
    return SqliteTarget(path)


def _url_carries_password(raw: str) -> bool:
    parts = urlsplit(raw)
    if parts.password is not None:
        return True
    query = parse_qsl(parts.query, keep_blank_values=True)
    return any(key.lower() == "password" for key, _ in query)


def _is_postgres_url(raw: str) -> bool:
    return any(raw.startswith(scheme + "://") for scheme in _POSTGRES_SCHEMES)


def _check_postgres_url(raw: str) -> None:
    try:
        urlsplit(raw).port  # noqa: B018 - raises ValueError for a malformed port
        parts = urlsplit(raw)
    except ValueError:
        raise _fail(ENV_DATABASE_URL, _URL_REASON) from None
    if parts.fragment or any(ch.isspace() or ord(ch) < 32 for ch in raw):
        raise _fail(ENV_DATABASE_URL, _URL_REASON)


def _database(url: str, password: str | None) -> DatabaseTarget:
    if url.startswith(_SQLITE_PREFIX):
        if password is not None:
            raise _fail(
                ENV_DATABASE_PASSWORD,
                f"is only valid with a PostgreSQL {ENV_DATABASE_URL}",
            )
        return _sqlite_target(url)
    if _is_postgres_url(url):
        _check_postgres_url(url)
        if password is not None and _url_carries_password(url):
            raise _fail(
                ENV_DATABASE_PASSWORD,
                f"is not allowed when {ENV_DATABASE_URL} carries a password",
            )
        return PostgresTarget(conninfo=url, password=password)
    raise _fail(ENV_DATABASE_URL, _URL_REASON)


_HOST_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def _host(raw: str) -> str:
    try:
        ipaddress.ip_address(raw)
        return raw
    except ValueError:
        pass
    labels = raw.split(".")
    if len(raw) <= 253 and all(_HOST_LABEL.match(label) for label in labels):
        return raw
    raise _fail(ENV_HOST, "must be an IP address or a host name")


def _forwarded_allow_ips(raw: str) -> tuple[str, ...]:
    if raw == "":
        return ()
    found: list[str] = []
    for item in raw.split(","):
        entry = item.strip()
        try:
            ipaddress.ip_network(entry, strict=False)
        except ValueError:
            raise _fail(
                ENV_FORWARDED_ALLOW_IPS,
                "must be comma-separated IP addresses or networks",
            ) from None
        found.append(entry)
    return tuple(found)


def _log_level(raw: str) -> str:
    if raw not in LOG_LEVELS:
        raise _fail(ENV_LOG_LEVEL, "must be one of debug, info, warning or error")
    return raw


def _is_identifier_path(text: str) -> bool:
    return all(part.isascii() and part.isidentifier() for part in text.split("."))


def _extensions(raw: str) -> tuple[str, ...]:
    if raw == "":
        return ()
    found: list[str] = []
    for item in raw.split(","):
        entry = item.strip()
        module, sep, attribute = entry.partition(":")
        if not (sep and _is_identifier_path(module) and _is_identifier_path(attribute)):
            raise _fail(
                ENV_EXTENSIONS, "must be comma-separated module:attribute references"
            )
        found.append(entry)
    return tuple(found)


def _pepper(raw: str) -> bytes:
    if len(raw) < PEPPER_MIN_CHARACTERS:
        raise _fail(
            ENV_TOKEN_PEPPER, f"must be at least {PEPPER_MIN_CHARACTERS} characters"
        )
    return raw.encode("utf-8")


def load_config(environ: Mapping[str, str] | None = None) -> RelayConfig:
    """Read the relay's configuration from `environ` (default: `os.environ`)."""
    env = os.environ if environ is None else environ
    known = {var.name for var in ENVIRONMENT}
    for name in sorted(env):
        if name.startswith(ENV_PREFIX) and name not in known:
            raise ConfigError(
                name, f"{name}: unknown variable with the reserved prefix {ENV_PREFIX}"
            )

    # strava.config imports ConfigError from here, so it is imported here late.
    from fitdocs_relay.strava.config import load_strava_config, load_targets_config

    values: dict[str, str] = {}
    for var in ENVIRONMENT:
        raw = env.get(var.name)
        if raw is None:
            if var.required:
                raise _fail(var.name, "is required")
            if var.default is None:
                continue
            raw = var.default
        elif raw == "" and (var.required or var.default != ""):
            raise _fail(var.name, "must not be empty")
        values[var.name] = raw

    def integer(name: str, bounds: tuple[int, int]) -> int:
        return _int_in_range(name, values[name], bounds)

    password = values.get(ENV_DATABASE_PASSWORD)
    return RelayConfig(
        database=_database(values[ENV_DATABASE_URL], password),
        pepper=_pepper(values[ENV_TOKEN_PEPPER]),
        host=_host(values[ENV_HOST]),
        port=integer(ENV_PORT, PORT_RANGE),
        forwarded_allow_ips=_forwarded_allow_ips(values[ENV_FORWARDED_ALLOW_IPS]),
        token_limit_per_minute=integer(ENV_TOKEN_RATE_LIMIT, RATE_LIMIT_RANGE),
        client_limit_per_minute=integer(ENV_CLIENT_RATE_LIMIT, RATE_LIMIT_RANGE),
        shutdown_grace_s=integer(ENV_SHUTDOWN_GRACE, GRACE_RANGE),
        log_level=_log_level(values[ENV_LOG_LEVEL]),
        extensions=_extensions(values[ENV_EXTENSIONS]),
        targets=load_targets_config(env, any_target=ENV_STRAVA_CLIENT_ID in env),
        strava=load_strava_config(env),
    )
