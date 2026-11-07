"""Custody of a principal's Strava tokens (Custody).

A connection's tokens are sealed under the keyring with the connection's
context; the athlete is kept only as a keyed hash. A token near expiry is
refreshed by the one request that holds the connection's lease; the others
wait for the generation to advance. A refusal Strava gives for good deletes
the connection, a transient failure leaves the tokens as they are.

A refresh's outbound timeout is clamped to `REFRESH_TIMEOUT_S` and to the
time left; it applies to each socket operation, so the call's total duration
is not bounded by it, and a holder's lease may lapse before its swap. A swap by
a holder whose lease nevertheless lapsed still lands when nothing changed the
row meanwhile.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

from fitdocs_relay.crypto import Keyring
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.shared.relay_targets import STRAVA
from fitdocs_relay.storage.interface import (
    NewConnection,
    SealedTokens,
    Storage,
    StoredConnection,
)
from fitdocs_relay.strava.api import Failure, Grant, StravaApi, StravaFailure, TokenPair
from fitdocs_relay.strava.budget import StravaBudget

REFRESH_MARGIN_S: Final = 300
LEASE_S: Final = 60
LEASE_WAIT_S: Final = 5.0
LEASE_POLL_S: Final = 0.25
REFRESH_TIMEOUT_S: Final = 8.0
REVOKE_TIMEOUT_S: Final = 8.0

_ACCOUNT_DOMAIN: Final = b"fitdocs-relay-account-v1\0"
_DEFINITIVE: Final = frozenset({Failure.AUTH, Failure.FORBIDDEN, Failure.INVALID})


@dataclass(frozen=True)
class Usable:
    principal_id: str
    access: str = field(repr=False)


def account_key(pepper: bytes, target: str, athlete_id: str) -> str:
    """hex(HMAC-SHA256(pepper, domain + target + NUL + athlete id))."""
    message = _ACCOUNT_DOMAIN + target.encode("utf-8") + b"\0" + athlete_id.encode()
    return hmac.new(pepper, message, hashlib.sha256).hexdigest()


def context(principal_id: str, field_name: str, *, target: str = STRAVA) -> str:
    """The associated data of one sealed field."""
    return f"fitdocs-relay:v1:{target}:{principal_id}:{field_name}"


class Custody:
    def __init__(
        self,
        storage: Storage,
        keyring: Keyring,
        api: StravaApi,
        budget: StravaBudget,
        *,
        pepper: bytes,
        clock: Callable[[], int],
        monotonic: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self._storage = storage
        self._keyring = keyring
        self._api = api
        self._budget = budget
        self._pepper = pepper
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep

    # --- sealing ---------------------------------------------------------

    def _seal(
        self,
        principal_id: str,
        access: str,
        refresh: str | None,
        expires_at: int | None,
    ) -> SealedTokens:
        return SealedTokens(
            access=self._keyring.seal(access, context=context(principal_id, "access")),
            refresh=(
                None
                if refresh is None
                else self._keyring.seal(
                    refresh, context=context(principal_id, "refresh")
                )
            ),
            access_expires_at=expires_at,
        )

    def _open(self, connection: StoredConnection) -> tuple[str, str | None] | None:
        """The access and refresh tokens, or None when a stored field is unreadable."""
        who = connection.principal_id
        access = self._keyring.open(
            connection.tokens.access, context=context(who, "access")
        )
        if access is None:
            return None
        sealed = connection.tokens.refresh
        if sealed is None:
            return access, None
        refresh = self._keyring.open(sealed, context=context(who, "refresh"))
        return None if refresh is None else (access, refresh)

    # --- the lifecycle ---------------------------------------------------

    def store_grant(self, principal_id: str, grant: Grant) -> None:
        self._storage.put_connection(
            NewConnection(
                principal_id,
                STRAVA,
                account_key(self._pepper, STRAVA, grant.athlete_id),
                self._seal(principal_id, grant.access, grant.refresh, grant.expires_at),
            ),
            now=self._clock(),
        )

    def access_token(
        self, principal_id: str, *, deadline: float
    ) -> Usable | PublishCode:
        while True:
            connection = self._storage.get_connection(principal_id, STRAVA)
            if connection is None:
                return PublishCode.NOT_CONNECTED
            tokens = self._open(connection)
            if tokens is None:
                return PublishCode.NOT_CONNECTED
            access, refresh = tokens
            expires_at = connection.tokens.access_expires_at
            if expires_at is None or expires_at > self._clock() + REFRESH_MARGIN_S:
                return Usable(principal_id, access)
            if refresh is None:
                return PublishCode.NOT_CONNECTED
            lease_id = secrets.token_hex(16)
            now = self._clock()
            if self._storage.claim_refresh(
                principal_id,
                STRAVA,
                generation=connection.generation,
                lease_id=lease_id,
                lease_until=now + LEASE_S,
                now=now,
            ):
                return self._refresh_held(
                    connection, refresh, lease_id, deadline=deadline
                )
            if not self._wait_for_new_generation(
                principal_id, connection.generation, deadline
            ):
                return PublishCode.UNAVAILABLE

    def _wait_for_new_generation(
        self, principal_id: str, generation: int, deadline: float
    ) -> bool:
        """True once the connection's generation differs from `generation` or the
        connection is gone; False when the wait or the deadline ran out."""
        stop = min(self._monotonic() + LEASE_WAIT_S, deadline)
        while self._monotonic() < stop:
            self._sleep(LEASE_POLL_S)
            current = self._storage.get_connection(principal_id, STRAVA)
            if current is None or current.generation != generation:
                return True
        return False

    def _refresh_held(
        self,
        connection: StoredConnection,
        refresh: str,
        lease_id: str,
        *,
        deadline: float,
    ) -> Usable | PublishCode:
        who = connection.principal_id
        timeout = min(REFRESH_TIMEOUT_S, deadline - self._monotonic())
        if timeout <= 0:
            self._release(who, lease_id)
            return PublishCode.UNAVAILABLE
        try:
            allowed = self._budget.spend(who).allowed
            answer = self._api.refresh(refresh, timeout=timeout) if allowed else None
        except BaseException:
            self._release(who, lease_id)
            raise
        if answer is None:
            self._release(who, lease_id)
            return PublishCode.RATE_LIMITED
        if isinstance(answer, StravaFailure):
            return self._refresh_failed(connection, lease_id, answer)
        return self._swap_refreshed(connection, lease_id, answer)

    def _release(self, principal_id: str, lease_id: str) -> None:
        self._storage.release_refresh(principal_id, STRAVA, lease_id=lease_id)

    def _refresh_failed(
        self, connection: StoredConnection, lease_id: str, failure: StravaFailure
    ) -> PublishCode:
        who = connection.principal_id
        if failure.failure in _DEFINITIVE:
            self._storage.delete_connection(
                who,
                STRAVA,
                generation=connection.generation,
                lease_id=lease_id,
                now=self._clock(),
            )
            return PublishCode.AUTH_REJECTED
        self._release(who, lease_id)
        if failure.failure is Failure.LIMITED:
            self._budget.mark_spent(daily=failure.daily_spent)
            return PublishCode.RATE_LIMITED
        return PublishCode.UNAVAILABLE

    def _swap_refreshed(
        self, connection: StoredConnection, lease_id: str, pair: TokenPair
    ) -> Usable | PublishCode:
        who = connection.principal_id
        landed = self._storage.swap_tokens(
            who,
            STRAVA,
            generation=connection.generation,
            lease_id=lease_id,
            tokens=self._seal(who, pair.access, pair.refresh, pair.expires_at),
            now=self._clock(),
        )
        if landed:
            return Usable(who, pair.access)
        if self._storage.get_connection(who, STRAVA) is None:
            return PublishCode.NOT_CONNECTED
        return PublishCode.UNAVAILABLE

    def withdraw(self, principal_id: str) -> bool:
        """Revoke at Strava when possible, then delete the connection.

        True when Strava accepted the revoke or there was no connection; False
        when no revoke was accepted (unreadable tokens, no refresh token, the
        budget spent, or a failure Strava or the network gave). The connection
        is deleted either way, and an exception from the revoke is re-raised
        after the delete."""
        connection = self._storage.get_connection(principal_id, STRAVA)
        if connection is None:
            return True
        try:
            return self._revoke_once(connection)
        finally:
            self._storage.delete_connection(
                principal_id, STRAVA, generation=None, now=self._clock()
            )

    def _revoke_once(self, connection: StoredConnection) -> bool:
        tokens = self._open(connection)
        if tokens is None or tokens[1] is None:
            return False
        if not self._budget.spend(connection.principal_id).allowed:
            return False
        return self._api.revoke(tokens[1], timeout=REVOKE_TIMEOUT_S) is None

    def forget_account(self, athlete_id: str) -> bool:
        return self._storage.delete_connection_by_account(
            STRAVA, account_key(self._pepper, STRAVA, athlete_id), now=self._clock()
        )

    def reencrypt_all(self) -> tuple[int, int]:
        """(re-encrypted, unreadable).

        The second number counts the connections with a field no configured key
        opens; they are left unchanged. A readable connection whose swap is
        refused because a refresh lease holds it is retried, polling every
        `LEASE_POLL_S`, for up to `LEASE_S` of the monotonic clock; one that is
        by then current under the current key (the holder's refresh seals under
        it) is counted in neither number. A connection whose swap is still
        refused after `LEASE_S` is left as it is and counted in neither number:
        running the command again picks it up. A connection deleted during the
        wait is counted in neither number."""
        done = 0
        unreadable = 0
        for listed in self._storage.list_connections(STRAVA):
            stop = self._monotonic() + LEASE_S
            connection: StoredConnection | None = listed
            while connection is not None:
                tokens = self._open(connection)
                if tokens is None:
                    unreadable += 1
                    break
                if self._current(connection):
                    break
                if self._swap_current(connection, tokens):
                    done += 1
                    break
                connection = self._storage.get_connection(
                    connection.principal_id, STRAVA
                )
                if connection is not None and not self._current(connection):
                    if self._monotonic() >= stop:
                        break
                    self._sleep(LEASE_POLL_S)
        return done, unreadable

    def _current(self, connection: StoredConnection) -> bool:
        sealed = connection.tokens.refresh
        return self._keyring.key_id_of(connection.tokens.access) == (
            self._keyring.current_id
        ) and (
            sealed is None
            or self._keyring.key_id_of(sealed) == self._keyring.current_id
        )

    def _swap_current(
        self, connection: StoredConnection, tokens: tuple[str, str | None]
    ) -> bool:
        return self._storage.swap_tokens(
            connection.principal_id,
            STRAVA,
            generation=connection.generation,
            lease_id=None,
            tokens=self._seal(
                connection.principal_id,
                tokens[0],
                tokens[1],
                connection.tokens.access_expires_at,
            ),
            now=self._clock(),
        )
