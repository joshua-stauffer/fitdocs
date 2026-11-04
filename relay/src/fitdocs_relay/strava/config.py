"""The targets and Strava configuration, read from the environment only.

`config.load_config` calls both loaders. Every `ConfigError` is the fixed form
`"<VARIABLE>: <reason>"`; no value from the environment is ever interpolated
(Requirement 13.1, 13.2).
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final
from urllib.parse import urlsplit

from fitdocs_relay.config import ConfigError
from fitdocs_relay.contract import (
    ENV_ENCRYPTION_KEYS,
    ENV_OPERATOR_NAME,
    ENV_PRIVACY_POLICY_URL,
    ENV_PUBLIC_URL,
    ENV_STRAVA_API_URL,
    ENV_STRAVA_CLIENT_ID,
    ENV_STRAVA_CLIENT_SECRET,
    ENV_STRAVA_OAUTH_URL,
    ENV_STRAVA_RATE_LIMIT,
    ENV_STRAVA_READ_RATE_LIMIT,
    ENV_STRAVA_WEB_URL,
    ENV_STRAVA_WEBHOOK_TOKEN,
    ENV_SUPPORT_CONTACT,
    ENVIRONMENT,
    EnvVar,
)
from fitdocs_relay.crypto import EncryptionKey, parse_keys

TARGETS_VARIABLES: Final = (
    ENV_PUBLIC_URL,
    ENV_ENCRYPTION_KEYS,
    ENV_OPERATOR_NAME,
    ENV_SUPPORT_CONTACT,
    ENV_PRIVACY_POLICY_URL,
)
STRAVA_VARIABLES: Final = (
    ENV_STRAVA_CLIENT_ID,
    ENV_STRAVA_CLIENT_SECRET,
    ENV_STRAVA_WEBHOOK_TOKEN,
    ENV_STRAVA_API_URL,
    ENV_STRAVA_OAUTH_URL,
    ENV_STRAVA_WEB_URL,
    ENV_STRAVA_RATE_LIMIT,
    ENV_STRAVA_READ_RATE_LIMIT,
)

OPERATOR_NAME_MAX = 100
CONTACT_MAX = 254
SECRET_MAX = 256
LIMIT_RANGE = (1, 1_000_000)


@dataclass(frozen=True)
class Limits:
    overall_15m: int
    overall_day: int
    read_15m: int
    read_day: int


@dataclass(frozen=True)
class TargetsConfig:
    public_url: str
    keys: tuple[EncryptionKey, ...] = field(repr=False)
    operator_name: str
    support_contact: str
    privacy_policy_url: str | None


@dataclass(frozen=True)
class StravaConfig:
    client_id: str
    client_secret: str = field(repr=False)
    webhook_token: str = field(repr=False)
    api_url: str
    oauth_url: str
    web_url: str
    limits: Limits


def _fail(variable: str, reason: str) -> ConfigError:
    return ConfigError(variable, f"{variable}: {reason}")


def _row(name: str) -> EnvVar:
    return next(var for var in ENVIRONMENT if var.name == name)


def _present(environ: Mapping[str, str], names: tuple[str, ...]) -> list[str]:
    """The names set in `environ`, in the contract table's order."""
    return [
        var.name for var in ENVIRONMENT if var.name in names and var.name in environ
    ]


def _value(environ: Mapping[str, str], name: str) -> str:
    """The variable's value, its contract default when unset.

    Called through `load_config`, an empty value never gets here: `load_config`
    refuses it first, for every row whose default is not the empty string."""
    raw = environ.get(name)
    if raw is None:
        default = _row(name).default
        assert default is not None, name  # only rows that have a default come here
        return default
    return raw


def _require(environ: Mapping[str, str], name: str) -> str:
    """The variable's value; called through `load_config`, an empty one never
    gets here (see `_value`)."""
    raw = environ.get(name)
    if raw is None:
        raise _fail(name, "is required")
    return raw


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _web_address(
    name: str, raw: str, *, loopback_http: bool, reason: str | None = None
) -> str:
    """A base address: `https` (or, when allowed, `http` to loopback), no
    userinfo, query or fragment; a trailing slash is dropped."""
    if reason is None:
        reason = "must be an https address" + (
            " (or http to a loopback host)" if loopback_http else ""
        )
    if any(ch.isspace() or not ch.isprintable() or not ch.isascii() for ch in raw):
        raise _fail(name, reason)
    try:
        parts = urlsplit(raw)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        raise _fail(name, reason) from None
    ok_scheme = parts.scheme == "https" or (
        loopback_http
        and parts.scheme == "http"
        and host is not None
        and _is_loopback(host)
    )
    if not ok_scheme or not host or "@" in parts.netloc or "?" in raw or "#" in raw:
        raise _fail(name, reason)
    return raw.rstrip("/")


_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")


def _contact(raw: str) -> str:
    reason = "must be an email address or an https address"
    if len(raw) > CONTACT_MAX:
        raise _fail(ENV_SUPPORT_CONTACT, reason)
    if raw.isascii() and raw.isprintable() and _EMAIL.fullmatch(raw):
        return raw
    return _web_address(ENV_SUPPORT_CONTACT, raw, loopback_http=False, reason=reason)


def _operator_name(raw: str) -> str:
    if (
        not (1 <= len(raw) <= OPERATOR_NAME_MAX and raw.isprintable())
        or not raw.strip()
    ):
        raise _fail(
            ENV_OPERATOR_NAME,
            f"must be 1 to {OPERATOR_NAME_MAX} printable characters",
        )
    return raw


def _keys(raw: str) -> tuple[EncryptionKey, ...]:
    try:
        return parse_keys(raw)
    except ValueError:
        raise _fail(
            ENV_ENCRYPTION_KEYS,
            "must be 1 to 8 comma-separated id:key entries with distinct ids, "
            "each key 32 bytes in unpadded base64url",
        ) from None


def _refuse_unless_enabled(
    environ: Mapping[str, str], group: tuple[str, ...], *, enabled: bool, why: str
) -> None:
    """Refuse a variable of `group` that is set while its target is not enabled."""
    if enabled:
        return
    for name in _present(environ, group):
        raise _fail(name, f"is only valid with {why}")


def load_targets_config(
    environ: Mapping[str, str], *, any_target: bool
) -> TargetsConfig | None:
    """The settings every target shares; None while no target is configured."""
    _refuse_unless_enabled(
        environ,
        TARGETS_VARIABLES,
        enabled=any_target,
        why="a configured target (" + ENV_STRAVA_CLIENT_ID + ")",
    )
    if not any_target:
        return None
    public_url = _web_address(
        ENV_PUBLIC_URL, _require(environ, ENV_PUBLIC_URL), loopback_http=True
    )
    keys = _keys(_require(environ, ENV_ENCRYPTION_KEYS))
    operator_name = _operator_name(_require(environ, ENV_OPERATOR_NAME))
    support_contact = _contact(_require(environ, ENV_SUPPORT_CONTACT))
    policy = (
        _web_address(
            ENV_PRIVACY_POLICY_URL,
            _require(environ, ENV_PRIVACY_POLICY_URL),
            loopback_http=False,
        )
        if ENV_PRIVACY_POLICY_URL in environ
        else None
    )
    return TargetsConfig(public_url, keys, operator_name, support_contact, policy)


_CLIENT_ID = re.compile(r"[0-9]{1,20}")
_WEBHOOK_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}")


def _client_secret(raw: str) -> str:
    if (
        len(raw) > SECRET_MAX
        or not raw.isascii()
        or not raw.isprintable()
        or any(ch.isspace() for ch in raw)
    ):
        raise _fail(
            ENV_STRAVA_CLIENT_SECRET,
            f"must be at most {SECRET_MAX} printable characters without spaces",
        )
    return raw


def _limit_pair(name: str, raw: str) -> tuple[int, int]:
    low, high = LIMIT_RANGE
    reason = (
        f"must be two comma-separated integers from {low} to {high}: the limit "
        "per 15 minutes, then the limit per day"
    )
    parts = raw.split(",")
    if len(parts) != 2 or not all(p.isascii() and p.isdigit() for p in parts):
        raise _fail(name, reason)
    short, day = int(parts[0]), int(parts[1])
    if not (low <= short <= high and low <= day <= high):
        raise _fail(name, reason)
    if short > day:
        raise _fail(name, "the limit per 15 minutes must not exceed the limit per day")
    return short, day


def load_strava_config(environ: Mapping[str, str]) -> StravaConfig | None:
    """The Strava target's settings; None while its client id is unset."""
    enabled = ENV_STRAVA_CLIENT_ID in environ
    _refuse_unless_enabled(
        environ,
        STRAVA_VARIABLES,
        enabled=enabled,
        why=ENV_STRAVA_CLIENT_ID,
    )
    if not enabled:
        return None
    client_id = _require(environ, ENV_STRAVA_CLIENT_ID)
    if not _CLIENT_ID.fullmatch(client_id):
        raise _fail(ENV_STRAVA_CLIENT_ID, "must be digits")
    secret = _client_secret(_require(environ, ENV_STRAVA_CLIENT_SECRET))
    token = _require(environ, ENV_STRAVA_WEBHOOK_TOKEN)
    if not _WEBHOOK_TOKEN.fullmatch(token):
        raise _fail(
            ENV_STRAVA_WEBHOOK_TOKEN,
            "must be 32 to 128 characters of letters, digits, underscore or hyphen",
        )

    def address(name: str) -> str:
        return _web_address(name, _value(environ, name), loopback_http=True)

    api_url = address(ENV_STRAVA_API_URL)
    oauth_url = address(ENV_STRAVA_OAUTH_URL)
    web_url = address(ENV_STRAVA_WEB_URL)
    overall = _limit_pair(ENV_STRAVA_RATE_LIMIT, _value(environ, ENV_STRAVA_RATE_LIMIT))
    read = _limit_pair(
        ENV_STRAVA_READ_RATE_LIMIT, _value(environ, ENV_STRAVA_READ_RATE_LIMIT)
    )
    return StravaConfig(
        client_id=client_id,
        client_secret=secret,
        webhook_token=token,
        api_url=api_url,
        oauth_url=oauth_url,
        web_url=web_url,
        limits=Limits(overall[0], overall[1], read[0], read[1]),
    )
