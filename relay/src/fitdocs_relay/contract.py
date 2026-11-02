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
)
