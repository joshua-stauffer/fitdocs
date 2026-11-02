"""The storage port: value types, errors and per-area protocols.

Every operation is one transaction. Storage never reads a clock: each
operation that depends on time takes `now` (seconds since the epoch) as an
argument. A later spec adds an operation by declaring an area protocol based
on `StorageBase` and adding it to `Storage`'s bases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, Protocol


@dataclass(frozen=True)
class Principal:
    principal_id: str
    label: str | None
    created_at: int


@dataclass(frozen=True)
class NewPrincipal:
    principal_id: str
    label: str | None


@dataclass(frozen=True)
class NewToken:
    token_id: str
    verifier: str
    label: str | None


@dataclass(frozen=True)
class TokenRecord:
    token_id: str
    principal_id: str
    verifier: str = field(repr=False)
    label: str | None
    created_at: int
    revoked_at: int | None


@dataclass(frozen=True)
class TokenSummary:
    token_id: str
    principal_id: str
    label: str | None
    created_at: int
    revoked_at: int | None


class RevokeResult(StrEnum):
    REVOKED = "revoked"
    ALREADY_REVOKED = "already-revoked"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    count: int
    retry_after_s: int | None  # None when allowed


@dataclass(frozen=True)
class SchemaState:
    current: int
    expected: int


@dataclass(frozen=True)
class SchemaChange:
    version: int
    name: str
    sql: str


class ServingClaim(Protocol):
    def release(self) -> None: ...


class StorageError(Exception):
    """An unexpected backend failure (relay-failure)."""


class StorageUnreachable(StorageError):
    """A connection failure (unavailable / storage-unreachable)."""


class DuplicateIdentifier(StorageError):
    """An identifier that already exists."""


class UnknownPrincipal(StorageError):
    """A principal that does not exist."""


class SchemaAhead(StorageError):
    """A database newer than this build."""


class StorageBase(Protocol):
    """The base of every area protocol."""

    @property
    def backend(self) -> Literal["sqlite", "postgres"]: ...

    def ping(self) -> None:
        """Raise `StorageUnreachable` when the store cannot be reached."""
        ...

    def close(self) -> None: ...


class PrincipalStore(StorageBase, Protocol):
    def create_principal(self, principal: NewPrincipal, *, now: int) -> Principal: ...

    def get_principal(self, principal_id: str) -> Principal | None: ...

    def list_principals(self) -> tuple[Principal, ...]:
        """By `created_at`, then id."""
        ...

    def delete_principal(self, principal_id: str) -> bool:
        """Cascades the principal's owned rows."""
        ...


class TokenStore(StorageBase, Protocol):
    def mint_token(
        self,
        token: NewToken,
        *,
        principal_id: str | None,
        new_principal: NewPrincipal | None,
        now: int,
    ) -> TokenRecord:
        """Exactly one of `principal_id` and `new_principal` is given."""
        ...

    def find_token(self, token_id: str) -> TokenRecord | None: ...

    def list_tokens(self, principal_id: str | None) -> tuple[TokenSummary, ...]: ...

    def revoke_token(self, token_id: str, *, now: int) -> RevokeResult: ...


class RateLimitStore(StorageBase, Protocol):
    def count_request(
        self, *, key: str, window_s: int, limit: int, now: int
    ) -> RateDecision: ...


class RecordStore(StorageBase, Protocol):
    def put_record(
        self, *, namespace: str, key: str, value: bytes, expires_at: int, now: int
    ) -> None: ...

    def get_record(self, *, namespace: str, key: str, now: int) -> bytes | None: ...

    def take_record(self, *, namespace: str, key: str, now: int) -> bytes | None: ...

    def delete_record(self, *, namespace: str, key: str) -> bool: ...


class SchemaStore(StorageBase, Protocol):
    def schema_state(self) -> SchemaState:
        """Raise `StorageUnreachable` when the store cannot be reached."""
        ...

    def apply_schema_change(self, change: SchemaChange, *, now: int) -> bool:
        """False when the change was already applied."""
        ...


class ServingStore(StorageBase, Protocol):
    def claim_serving(self) -> ServingClaim | None:
        """None when another instance holds the claim."""
        ...


class Storage(
    PrincipalStore,
    TokenStore,
    RateLimitStore,
    RecordStore,
    SchemaStore,
    ServingStore,
    Protocol,
):
    """All state; `backend`, `ping` and `close` come from `StorageBase`."""
