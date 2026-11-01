"""Per-token and per-client request limits, counted in the database."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable

from fitdocs_relay.storage.interface import RateDecision, Storage

WINDOW_S = 60
UNKNOWN_CLIENT_KEY = "c:unknown"


class RateLimiter:
    def __init__(
        self,
        storage: Storage,
        *,
        pepper: bytes,
        clock: Callable[[], int],
        token_limit: int,
        client_limit: int,
    ) -> None:
        self._storage = storage
        self._pepper = pepper
        self._clock = clock
        self._token_limit = token_limit
        self._client_limit = client_limit

    def check_token(self, token_id: str) -> RateDecision:
        return self._count("t:" + token_id, self._token_limit)

    def check_client(self, address: str | None) -> RateDecision:
        return self._count(self._client_key(address), self._client_limit)

    def _client_key(self, address: str | None) -> str:
        if address is None:
            return UNKNOWN_CLIENT_KEY
        digest = hmac.new(self._pepper, b"client\0" + address.encode(), hashlib.sha256)
        return "c:" + digest.hexdigest()[:32]

    def _count(self, key: str, limit: int) -> RateDecision:
        return self._storage.count_request(
            key=key, window_s=WINDOW_S, limit=limit, now=self._clock()
        )
