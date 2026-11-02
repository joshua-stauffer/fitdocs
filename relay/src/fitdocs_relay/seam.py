"""The wrapper seam, version 1: what an in-process wrapper may rely on.

A wrapper is a `RelayExtension`: it names itself, declares the seam version it
was written against, and returns routes (all under `/x/<name>/`, served outside
the envelope) and at most one registration provider from `build`. The app
factory refuses the whole set, naming the extension and the reason, when any of
that is wrong (`SeamError`). Changing any name or signature here is a seam
version change.

`fitdocs_relay.app` supplies the token issuance and record store a context
carries; this module holds the surface and the loader.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol

from starlette.responses import Response
from starlette.routing import BaseRoute

from fitdocs_relay.answers import answer
from fitdocs_relay.shared.relay_codes import RelayCode

SEAM_VERSION: Final = 1
EXTENSION_ROUTE_PREFIX: Final = "/x/"  # every extension route is under /x/<name>/


@dataclass(frozen=True)
class IssuedToken:
    token_id: str
    principal_id: str
    token: str = field(repr=False)


class TokenIssuance(Protocol):
    def issue(self, *, principal_id: str | None, label: str | None) -> IssuedToken: ...
    def revoke(self, token_id: str) -> bool: ...
    def delete_principal(self, principal_id: str) -> bool: ...


class ExtensionRecords(Protocol):
    # namespace = extension name; key <=128 chars; value <=4096 bytes; ttl 1..2592000 s
    def put(self, key: str, value: bytes, *, ttl_s: int) -> None: ...
    def get(self, key: str) -> bytes | None: ...
    def take(self, key: str) -> bytes | None: ...
    def delete(self, key: str) -> bool: ...


@dataclass(frozen=True)
class StartAccepted:
    user_code: str
    poll_secret: str
    interval_s: int
    expires_in_s: int


@dataclass(frozen=True)
class StartRefused:
    pass


@dataclass(frozen=True)
class RateLimitedAnswer:
    retry_after_s: int


@dataclass(frozen=True)
class PollPending:
    pass


@dataclass(frozen=True)
class PollSlowDown:
    pass


@dataclass(frozen=True)
class PollIssued:
    token: IssuedToken


@dataclass(frozen=True)
class PollRefused:
    pass


@dataclass(frozen=True)
class PollExpired:
    pass


StartAnswer = StartAccepted | StartRefused | RateLimitedAnswer
PollAnswer = (
    PollPending
    | PollSlowDown
    | PollIssued
    | PollRefused
    | PollExpired
    | RateLimitedAnswer
)


class RegistrationProvider(Protocol):
    def start(self, email: str) -> StartAnswer: ...  # sync; run in a worker thread
    def poll(self, poll_secret: str) -> PollAnswer: ...


@dataclass(frozen=True)
class ExtensionContext:
    tokens: TokenIssuance
    records: ExtensionRecords
    clock: Callable[[], int]
    logger: logging.Logger


@dataclass(frozen=True)
class ExtensionParts:
    routes: tuple[BaseRoute, ...] = ()
    registration: RegistrationProvider | None = None


class RelayExtension(Protocol):
    @property
    def name(self) -> str: ...  # ^[a-z][a-z0-9-]{0,31}$
    @property
    def seam_version(self) -> int: ...
    def build(self, context: ExtensionContext) -> ExtensionParts: ...


def envelope_response(
    code: RelayCode, data: Mapping[str, object] | None = None
) -> Response:
    return answer(code, data)


class SeamError(Exception):
    """Names the extension and the reason; `serve` exits 2."""


def _refuse_reference(reference: str, reason: str) -> SeamError:
    return SeamError(f"extension reference {reference!r}: {reason}")


def _load(reference: str) -> RelayExtension:
    module_name, sep, attribute = reference.partition(":")
    if not (sep and module_name and attribute):
        raise _refuse_reference(reference, "not a module:attribute reference")
    try:
        target: object = importlib.import_module(module_name)
    except Exception as error:
        raise _refuse_reference(
            reference, f"the module could not be imported ({type(error).__name__})"
        ) from None
    for part in attribute.split("."):
        try:
            target = getattr(target, part)
        except AttributeError:
            raise _refuse_reference(
                reference, "the module has no such attribute"
            ) from None
    extension: RelayExtension = target  # type: ignore[assignment]
    return extension


def load_extensions(references: tuple[str, ...]) -> tuple[RelayExtension, ...]:
    return tuple(_load(reference) for reference in references)
