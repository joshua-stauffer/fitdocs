"""The deploy contract as data: version, image constants and the environment table.

The table below is the one documented list of the variables the relay reads
(Requirement 9.2); `config.py` reads exactly these and refuses any other name
carrying the reserved prefix (Requirement 9.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DEPLOY_CONTRACT_VERSION: Final = 1
ENV_PREFIX: Final = "FITDOCS_RELAY_"


@dataclass(frozen=True)
class EnvVar:
    """One row of the environment table."""

    name: str
    required: bool
    default: str | None
    secret: bool
    meaning: str
    required_with: tuple[str, ...] = ()
    """Variables any one of which, when set, makes this one required."""


IMAGE_USER_ID: Final = 10001
IMAGE_PORT: Final = 8080
IMAGE_ENTRYPOINT: Final = ("fitdocs-relay",)
IMAGE_DEFAULT_COMMAND: Final = ("serve",)
# The image's Python environment; its bin/ is first on PATH.
IMAGE_ENVIRONMENT: Final = "/opt/fitdocs-relay"
COMMANDS: Final[tuple[str, ...]] = (
    "serve",
    "migrate",
    "principal",
    "token",
    "new-pepper",
    "strava",
    "reencrypt",
    "new-encryption-key",
)

ENV_DATABASE_URL: Final = ENV_PREFIX + "DATABASE_URL"
ENV_DATABASE_PASSWORD: Final = ENV_PREFIX + "DATABASE_PASSWORD"
ENV_TOKEN_PEPPER: Final = ENV_PREFIX + "TOKEN_PEPPER"
ENV_HOST: Final = ENV_PREFIX + "HOST"
ENV_PORT: Final = ENV_PREFIX + "PORT"
ENV_FORWARDED_ALLOW_IPS: Final = ENV_PREFIX + "FORWARDED_ALLOW_IPS"
ENV_TOKEN_RATE_LIMIT: Final = ENV_PREFIX + "TOKEN_RATE_LIMIT_PER_MINUTE"
ENV_CLIENT_RATE_LIMIT: Final = ENV_PREFIX + "CLIENT_RATE_LIMIT_PER_MINUTE"
ENV_SHUTDOWN_GRACE: Final = ENV_PREFIX + "SHUTDOWN_GRACE_SECONDS"
ENV_LOG_LEVEL: Final = ENV_PREFIX + "LOG_LEVEL"
ENV_EXTENSIONS: Final = ENV_PREFIX + "EXTENSIONS"
ENV_PUBLIC_URL: Final = ENV_PREFIX + "PUBLIC_URL"
ENV_ENCRYPTION_KEYS: Final = ENV_PREFIX + "ENCRYPTION_KEYS"
ENV_OPERATOR_NAME: Final = ENV_PREFIX + "OPERATOR_NAME"
ENV_SUPPORT_CONTACT: Final = ENV_PREFIX + "SUPPORT_CONTACT"
ENV_PRIVACY_POLICY_URL: Final = ENV_PREFIX + "PRIVACY_POLICY_URL"
ENV_STRAVA_CLIENT_ID: Final = ENV_PREFIX + "STRAVA_CLIENT_ID"
ENV_STRAVA_CLIENT_SECRET: Final = ENV_PREFIX + "STRAVA_CLIENT_SECRET"
ENV_STRAVA_WEBHOOK_TOKEN: Final = ENV_PREFIX + "STRAVA_WEBHOOK_TOKEN"
ENV_STRAVA_API_URL: Final = ENV_PREFIX + "STRAVA_API_URL"
ENV_STRAVA_OAUTH_URL: Final = ENV_PREFIX + "STRAVA_OAUTH_URL"
ENV_STRAVA_WEB_URL: Final = ENV_PREFIX + "STRAVA_WEB_URL"
ENV_STRAVA_LINKS: Final = ENV_PREFIX + "STRAVA_LINKS"
ENV_STRAVA_RATE_LIMIT: Final = ENV_PREFIX + "STRAVA_RATE_LIMIT"
ENV_STRAVA_READ_RATE_LIMIT: Final = ENV_PREFIX + "STRAVA_READ_RATE_LIMIT"

# The variables that name an enabling client id. A target's own variables are
# required when its client id is set (`_WITH_STRAVA`); the target-neutral rows
# (`_WITH_ANY_TARGET`) are required when any target's client id is set, so a
# later target appends its client id to that tuple.
_WITH_STRAVA: Final = (ENV_STRAVA_CLIENT_ID,)
_WITH_ANY_TARGET: Final = (ENV_STRAVA_CLIENT_ID,)

ENVIRONMENT: Final[tuple[EnvVar, ...]] = (
    EnvVar(
        ENV_DATABASE_URL,
        True,
        None,
        True,
        "`sqlite:///relative.db`, `sqlite:////absolute/path.db`, or `postgresql://` / "
        "`postgres://user@host:port/db[?params]`; anything else, including in-memory "
        "SQLite, is an error",
    ),
    EnvVar(
        ENV_DATABASE_PASSWORD,
        False,
        None,
        True,
        "PostgreSQL password. An error with a SQLite URL, or when the URL already "
        "carries a password",
    ),
    EnvVar(
        ENV_TOKEN_PEPPER,
        True,
        None,
        True,
        "Token-hashing secret, at least 43 characters (`fitdocs-relay new-pepper` "
        "prints one)",
    ),
    EnvVar(
        ENV_HOST,
        False,
        "127.0.0.1",
        False,
        "Listen address (the image sets `0.0.0.0`)",
    ),
    EnvVar(ENV_PORT, False, "8080", False, "Listen port, 1-65535"),
    EnvVar(
        ENV_FORWARDED_ALLOW_IPS,
        False,
        "",
        False,
        "Comma-separated proxy addresses trusted for forwarded client addresses",
    ),
    EnvVar(
        ENV_TOKEN_RATE_LIMIT,
        False,
        "60",
        False,
        "Requests per token per minute, 1-100000",
    ),
    EnvVar(
        ENV_CLIENT_RATE_LIMIT,
        False,
        "20",
        False,
        "Unauthenticated requests per client address per minute, 1-100000",
    ),
    EnvVar(ENV_SHUTDOWN_GRACE, False, "20", False, "Graceful-shutdown wait, 0-600"),
    EnvVar(
        ENV_LOG_LEVEL,
        False,
        "info",
        False,
        "`debug`, `info`, `warning` or `error`",
    ),
    EnvVar(
        ENV_EXTENSIONS,
        False,
        "",
        False,
        "Comma-separated `module:attribute` references to `RelayExtension` objects",
    ),
    EnvVar(
        ENV_PUBLIC_URL,
        False,
        None,
        False,
        "The relay's public base address (`https`, or `http` to loopback); builds "
        "the callback `<url>/strava/callback` and page links",
        _WITH_ANY_TARGET,
    ),
    EnvVar(
        ENV_ENCRYPTION_KEYS,
        False,
        None,
        True,
        "Comma-separated `<id>:<key>` entries, 1-8; id `[a-z0-9]{1,16}` and "
        "distinct, key 32 bytes in unpadded base64url; the first encrypts "
        "(`fitdocs-relay new-encryption-key`)",
        _WITH_ANY_TARGET,
    ),
    EnvVar(
        ENV_OPERATOR_NAME,
        False,
        None,
        False,
        "The relay's operator, as the pages name them; 1-100 printable characters",
        _WITH_ANY_TARGET,
    ),
    EnvVar(
        ENV_SUPPORT_CONTACT,
        False,
        None,
        False,
        "An email address or `https` address where athletes reach the operator",
        _WITH_ANY_TARGET,
    ),
    EnvVar(
        ENV_PRIVACY_POLICY_URL,
        False,
        "the relay's /privacy",
        False,
        "An `https` address of the operator's own policy",
    ),
    EnvVar(
        ENV_STRAVA_CLIENT_ID,
        False,
        None,
        False,
        "The Strava application's client id (digits); setting it enables the "
        "Strava target",
    ),
    EnvVar(
        ENV_STRAVA_CLIENT_SECRET,
        False,
        None,
        True,
        "The application's client secret",
        _WITH_STRAVA,
    ),
    EnvVar(
        ENV_STRAVA_WEBHOOK_TOKEN,
        False,
        None,
        True,
        "32-128 characters of `[A-Za-z0-9_-]`; the webhook path secret and verify "
        "token",
        _WITH_STRAVA,
    ),
    EnvVar(
        ENV_STRAVA_API_URL,
        False,
        "https://www.strava.com/api/v3",
        False,
        "Strava's API base",
    ),
    EnvVar(
        ENV_STRAVA_OAUTH_URL,
        False,
        "https://www.strava.com/oauth",
        False,
        "Strava's OAuth base (authorize, token, revoke)",
    ),
    EnvVar(
        ENV_STRAVA_WEB_URL,
        False,
        "https://www.strava.com",
        False,
        "Base of activity pages (`/activities/<id>`)",
    ),
    EnvVar(
        ENV_STRAVA_LINKS,
        False,
        "activity",
        False,
        "The link setting: `activity` puts the activity's address "
        "`<web URL>/activities/<id>` in every posted or uploaded answer; `relay` "
        "puts none, and pages link to `/go/<publication id>`",
    ),
    EnvVar(
        ENV_STRAVA_RATE_LIMIT,
        False,
        "200,2000",
        False,
        "Overall limit per 15 minutes and per day",
    ),
    EnvVar(
        ENV_STRAVA_READ_RATE_LIMIT,
        False,
        "100,1000",
        False,
        "Non-upload limit per 15 minutes and per day",
    ),
)
