"""Run one serving instance with graceful shutdown (Serve, Requirements 1.2, 9.6, 9.7).

`run_server` configures logging first (so nothing it does can log through an
unredacted handler), opens storage, claims serving, runs uvicorn until a
termination or interrupt signal, then releases the claim and closes storage.
uvicorn is imported here and nowhere else in the relay.
"""

from __future__ import annotations

import base64
import logging
import signal
from collections.abc import Sequence
from types import FrameType
from typing import Final
from urllib.parse import quote, unquote, urlsplit

import uvicorn

from fitdocs_relay.app import create_app
from fitdocs_relay.config import PostgresTarget, RelayConfig
from fitdocs_relay.logs import configure_logging, failure_fields, log_event
from fitdocs_relay.seam import RelayExtension, load_extensions
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import ServingClaim, StorageError

_LOGGER: Final = logging.getLogger("fitdocs_relay.serve")
_SIGNALS: Final = (signal.SIGTERM, signal.SIGINT)


class _StopRequest:
    """Remembers a termination or interrupt signal that arrives before uvicorn runs.

    While uvicorn runs it captures the signals itself and re-raises them
    afterwards, which lands here harmlessly.
    """

    def __init__(self) -> None:
        self.signum: int | None = None
        self.server: uvicorn.Server | None = None

    def __call__(self, signum: int, frame: FrameType | None) -> None:
        self.signum = signum
        if self.server is not None:
            # uvicorn honours a flag set before run: it starts up, skips the
            # main loop and shuts down.
            self.server.should_exit = True


def _raw_query_values(query: str, key: str) -> list[str]:
    """The undecoded values of every `key` pair in `query` (decoded key match)."""
    found: list[str] = []
    for pair in query.split("&"):
        name, _, value = pair.partition("=")
        if unquote(name.replace("+", " ")).lower() == key.lower():
            found.append(value)
    return found


def database_secrets(config: RelayConfig) -> tuple[str, ...]:
    """Every form of the database password: the variable's, and one in the URL.

    A password in the URL (userinfo, or a `password` query parameter) is
    registered as written (percent-encoded), decoded, and re-encoded; the
    variable's password also in its percent-encoded form.
    """
    target = config.database
    if not isinstance(target, PostgresTarget):
        return ()
    forms: list[str] = []
    if target.password:
        forms += [target.password, quote(target.password, safe="")]
    parts = urlsplit(target.conninfo)
    embedded = [parts.password] if parts.password else []
    embedded += [raw for raw in _raw_query_values(parts.query, "password") if raw]
    for raw in embedded:
        decoded = unquote(raw)
        forms += [raw, decoded, quote(decoded, safe="")]
    return tuple(dict.fromkeys(forms))


def target_secrets(config: RelayConfig) -> tuple[str, ...]:
    """The configured target's secrets the log filter must redact: the client
    secret, the webhook secret, and each encryption key as its unpadded
    base64url text and as the `id:key` entry it was configured as."""
    found: list[str] = []
    if config.strava is not None:
        found += [config.strava.client_secret, config.strava.webhook_token]
    if config.targets is not None:
        for key in config.targets.keys:
            text = base64.urlsafe_b64encode(key.material).decode("ascii").rstrip("=")
            found += [text, f"{key.key_id}:{text}"]
    return tuple(dict.fromkeys(found))


def run_server(
    config: RelayConfig, extensions: Sequence[RelayExtension] | None = None
) -> int:
    """Serve until a termination signal. 0 on a clean stop, 1 when refused.

    `extensions` None loads `config.extensions`; a `SeamError` from the load
    propagates (nothing has been claimed by then).
    """
    secrets = database_secrets(config)
    configure_logging(
        pepper=config.pepper,
        password=None,
        extra_secrets=(*secrets, *target_secrets(config)),
        level=config.log_level.upper(),
    )

    loaded = load_extensions(config.extensions) if extensions is None else extensions

    try:
        storage = open_storage(config.database)
    except StorageError as error:
        log_event(
            _LOGGER,
            "serve-failed",
            level=logging.ERROR,
            **failure_fields((type(error), error, error.__traceback__)),
        )
        return 1
    claim: ServingClaim | None = None
    previous: dict[signal.Signals, object] = {}
    try:
        try:
            claim = storage.claim_serving()
        except StorageError as error:
            log_event(
                _LOGGER,
                "serve-failed",
                level=logging.ERROR,
                **failure_fields((type(error), error, error.__traceback__)),
            )
            return 1
        if claim is None:
            log_event(_LOGGER, "serve-refused", level=logging.ERROR)
            return 1
        stop = _StopRequest()
        for number in _SIGNALS:
            previous[number] = signal.signal(number, stop)
        app = create_app(config, extensions=loaded, storage=storage)
        uvicorn_config = uvicorn.Config(
            app,
            host=config.host,
            port=config.port,
            lifespan="on",
            access_log=False,
            log_config=None,
            proxy_headers=True,
            forwarded_allow_ips=list(config.forwarded_allow_ips),
            timeout_graceful_shutdown=config.shutdown_grace_s,
        )
        server = uvicorn.Server(uvicorn_config)
        stop.server = server
        if stop.signum is None:
            server.run()
        return 0
    finally:
        for number, old in previous.items():
            signal.signal(number, old)  # type: ignore[arg-type]
        try:
            if claim is not None:
                claim.release()
        finally:
            storage.close()
