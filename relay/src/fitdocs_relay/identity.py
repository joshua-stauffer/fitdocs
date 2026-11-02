"""Relay tokens: format, generation, keyed hashing and authentication."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field

from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import TOKEN_PREFIX, split_relay_token
from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewPrincipal,
    NewToken,
    Principal,
    RevokeResult,
    Storage,
)

_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
_ID_LENGTH = 16
_SECRET_LENGTH = 52
_PRINCIPAL_PREFIX = "prn_"
_VERIFIER_DOMAIN = b"fitdocs-relay-token-v1\0"
# Compared against when the presented id is unknown, so that path costs the same.
_DUMMY_VERIFIER = "0" * 64


@dataclass(frozen=True)
class MintedToken:
    token_id: str
    principal_id: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class PreparedToken:
    """A token generated but not stored: the row to store and the token to show once."""

    new_token: NewToken
    token: str = field(repr=False)


@dataclass(frozen=True)
class Authenticated:
    principal_id: str
    token_id: str


def _random(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


class TokenService:
    def __init__(
        self, storage: Storage, *, pepper: bytes, clock: Callable[[], int]
    ) -> None:
        self._storage = storage
        self._pepper = pepper
        self._clock = clock

    def _verifier(self, token_id: str, secret: str) -> str:
        message = _VERIFIER_DOMAIN + token_id.encode() + b"\0" + secret.encode()
        return hmac.new(self._pepper, message, hashlib.sha256).hexdigest()

    def create_principal(self, label: str | None) -> Principal:
        try:
            return self._create_principal(label)
        except DuplicateIdentifier:
            return self._create_principal(label)

    def _create_principal(self, label: str | None) -> Principal:
        principal = NewPrincipal(_PRINCIPAL_PREFIX + _random(_ID_LENGTH), label)
        return self._storage.create_principal(principal, now=self._clock())

    def mint(
        self,
        *,
        principal_id: str | None,
        label: str | None,
        principal_label: str | None = None,
    ) -> MintedToken:
        try:
            return self._mint(principal_id, label, principal_label)
        except DuplicateIdentifier:
            return self._mint(principal_id, label, principal_label)

    def prepare(self, *, label: str | None) -> PreparedToken:
        """Generate a token and its row without storing either."""
        token_id = _random(_ID_LENGTH)
        secret = _random(_SECRET_LENGTH)
        return PreparedToken(
            NewToken(token_id, self._verifier(token_id, secret), label),
            f"{TOKEN_PREFIX}_{token_id}_{secret}",
        )

    def _mint(
        self, principal_id: str | None, label: str | None, principal_label: str | None
    ) -> MintedToken:
        prepared = self.prepare(label=label)
        new_principal = (
            None
            if principal_id is not None
            else NewPrincipal(_PRINCIPAL_PREFIX + _random(_ID_LENGTH), principal_label)
        )
        record = self._storage.mint_token(
            prepared.new_token,
            principal_id=principal_id,
            new_principal=new_principal,
            now=self._clock(),
        )
        return MintedToken(
            record.token_id,
            record.principal_id,
            prepared.token,
        )

    def authenticate(self, presented: str | None) -> Authenticated | RelayCode:
        if presented is None:
            return RelayCode.TOKEN_MISSING
        parts = split_relay_token(presented)
        if parts is None:
            return RelayCode.TOKEN_UNKNOWN
        token_id, secret = parts
        computed = self._verifier(token_id, secret)
        record = self._storage.find_token(token_id)
        if record is None:
            hmac.compare_digest(computed, _DUMMY_VERIFIER)
            return RelayCode.TOKEN_UNKNOWN
        if not hmac.compare_digest(computed, record.verifier):
            return RelayCode.TOKEN_UNKNOWN
        if record.revoked_at is not None:
            return RelayCode.TOKEN_REVOKED
        return Authenticated(record.principal_id, record.token_id)

    def revoke(self, token_id: str) -> RevokeResult:
        return self._storage.revoke_token(token_id, now=self._clock())

    def delete_principal(self, principal_id: str) -> bool:
        return self._storage.delete_principal(principal_id)
