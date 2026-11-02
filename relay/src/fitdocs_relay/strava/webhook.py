"""Strava's webhook: the subscription validation and the deauthorization event.

Strava does not sign events, so the caller of this class has already matched
the path secret. A validation request is answered only when its verification
token equals the configured secret. The one event acted on is an athlete's
deauthorization, which forgets that athlete's connection; every other body,
including a hostile or unparsable one, is acknowledged and ignored. Nothing of
an event is logged or kept.
"""

from __future__ import annotations

import hmac
import json
from typing import Final

from fitdocs_relay.strava.api import MAX_ATHLETE_ID
from fitdocs_relay.strava.custody import Custody

WEBHOOK_PATH: Final = "/strava/webhook"
MAX_EVENT_BYTES: Final = 64 * 1024
SUBSCRIBE_MODE: Final = "subscribe"
CHALLENGE_KEY: Final = "hub.challenge"


class Webhook:
    def __init__(self, custody: Custody, *, secret: str) -> None:
        self._custody = custody
        self._secret = secret.encode("utf-8")

    def validate(
        self, mode: str | None, challenge: str | None, verify_token: str | None
    ) -> dict[str, str] | None:
        """The echo Strava expects, or `None` (answered as not found)."""
        if mode != SUBSCRIBE_MODE or challenge is None or verify_token is None:
            return None
        presented = verify_token.encode("utf-8", "replace")
        if not hmac.compare_digest(presented, self._secret):
            return None
        return {CHALLENGE_KEY: challenge}

    def event(self, body: bytes) -> None:
        """Act on a deauthorization; acknowledge (return) for anything else."""
        athlete_id = _deauthorized_athlete(body)
        if athlete_id is not None:
            self._custody.forget_account(athlete_id)


def _deauthorized_athlete(body: bytes) -> str | None:
    if len(body) > MAX_EVENT_BYTES:
        return None
    try:
        event = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(event, dict) or event.get("object_type") != "athlete":
        return None
    updates = event.get("updates")
    if not isinstance(updates, dict) or updates.get("authorized") != "false":
        return None
    owner = event.get("owner_id")
    if isinstance(owner, bool) or not isinstance(owner, int):
        return None
    return str(owner) if 0 < owner <= MAX_ATHLETE_ID else None
