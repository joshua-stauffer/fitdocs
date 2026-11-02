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


@dataclass(frozen=True)
class SealedTokens:
    """A connection's tokens as the keyring sealed them; storage keeps them opaque."""

    access: str = field(repr=False)
    refresh: str | None = field(repr=False)
    access_expires_at: int | None  # None: no stated expiry, so no time-based refresh


@dataclass(frozen=True)
class NewConnection:
    principal_id: str
    target: str
    account_key: str
    tokens: SealedTokens


@dataclass(frozen=True)
class StoredConnection:
    principal_id: str
    target: str
    account_key: str
    tokens: SealedTokens
    generation: int
    lease_id: str | None
    lease_until: int | None
    token_id: str | None
    created_at: int
    updated_at: int


class TargetConnectionStore(StorageBase, Protocol):
    def put_connection(self, connection: NewConnection, *, now: int) -> None:
        """Store the principal's connection to `connection.target`.

        Upserts by (principal, target) with generation 1 and no lease. Another
        principal's connection to the same (target, account) is deleted with
        its publications and its connection token revoked; when this
        principal's own account changes, its publications for the target are
        deleted. Raises `UnknownPrincipal` for a principal that does not exist.
        """
        ...

    def get_connection(
        self, principal_id: str, target: str
    ) -> StoredConnection | None: ...

    def list_connections(self, target: str | None) -> tuple[StoredConnection, ...]:
        """By target, then principal id; every target when `target` is None."""
        ...

    def claim_refresh(
        self,
        principal_id: str,
        target: str,
        *,
        generation: int,
        lease_id: str,
        lease_until: int,
        now: int,
    ) -> bool:
        """Take the refresh lease; True for the one caller that gets it.

        Succeeds only when the connection's generation is `generation` and no
        lease is live (`lease_until` absent or `<= now`).
        """
        ...

    def swap_tokens(
        self,
        principal_id: str,
        target: str,
        *,
        generation: int,
        lease_id: str | None,
        tokens: SealedTokens,
        now: int,
    ) -> bool:
        """Replace the tokens, advance the generation by one and clear the lease.

        Succeeds only when the generation matches and either `lease_id` is the
        stored lease or, with `lease_id=None`, no lease is live (`lease_until`
        absent or `<= now`). Otherwise nothing changes.
        """
        ...

    def release_refresh(self, principal_id: str, target: str, *, lease_id: str) -> None:
        """Clear the lease when `lease_id` holds it; otherwise change nothing."""
        ...

    def issue_connection_token(
        self, principal_id: str, target: str, token: NewToken, *, now: int
    ) -> TokenRecord | None:
        """Insert `token` for the principal, revoke the connection's previous
        token and record the new one, in one transaction.

        `None`, with nothing inserted, when the principal has no connection to
        `target`. Raises `DuplicateIdentifier` for a token id already in use.
        """
        ...

    def delete_connection(
        self, principal_id: str, target: str, *, generation: int | None, now: int
    ) -> bool:
        """Delete the connection (when `generation` is given, only if it matches),
        its publications, and revoke its connection token."""
        ...

    def delete_connection_by_account(
        self, target: str, account_key: str, *, now: int
    ) -> bool:
        """As `delete_connection`, for the connection to the account."""
        ...


@dataclass(frozen=True)
class Publication:
    """A link record: what resolving the link needs; no athlete or activity id."""

    target: str
    publication_id: str
    principal_id: str
    sport: str
    start_s: float
    elapsed_s: float | None
    distance_m: float | None


class PublicationStore(StorageBase, Protocol):
    def put_publication(self, publication: Publication, *, now: int) -> bool:
        """Upsert by (target, publication id), only for the owning principal.

        False, with nothing changed, when the id belongs to another principal.
        An owner's put replaces the record's fields and its update time and keeps
        its creation time. Raises `UnknownPrincipal` for a principal that does not
        exist.
        """
        ...

    def get_publication(
        self, target: str, publication_id: str
    ) -> Publication | None: ...


@dataclass(frozen=True)
class BudgetCharge:
    """One window of a spend: `amount` units against a `ceiling` of `window_s`."""

    key: str
    window_s: int
    ceiling: int
    amount: int
    principal_id: str | None = None


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    retry_after_s: int | None  # None when allowed


class BudgetStore(StorageBase, Protocol):
    def spend_budget(
        self, charges: tuple[BudgetCharge, ...], *, now: int
    ) -> BudgetDecision:
        """Charge every window, or none.

        Windows are fixed, starting at `now - now % window_s`. The spend is
        allowed only when every charged window stays within its ceiling after
        its amount is added; then every count rises. Otherwise nothing rises and
        the decision carries the longest wait among the windows that would have
        gone over (seconds to the end of each). Windows that have ended are
        deleted, except that PostgreSQL leaves one another transaction holds
        (the cleanup never waits); a later spend deletes it. A charge with a
        `principal_id` tags its row with that principal, and the row goes with
        the principal. Raises `UnknownPrincipal` for a
        tagged principal that does not exist, and `ValueError` for a window
        shorter than a second, an amount below one, a negative ceiling, or two
        charges of one window.
        """
        ...

    def exhaust_budget(self, *, key: str, window_s: int, count: int, now: int) -> None:
        """Raise the current window's count of `key` to at least `count`.

        Never lowers a count. Raises `ValueError` for a window shorter than a
        second or a negative count.
        """
        ...


class Storage(
    PrincipalStore,
    TokenStore,
    RateLimitStore,
    RecordStore,
    SchemaStore,
    ServingStore,
    TargetConnectionStore,
    PublicationStore,
    BudgetStore,
    Protocol,
):
    """All state; `backend`, `ping` and `close` come from `StorageBase`."""
