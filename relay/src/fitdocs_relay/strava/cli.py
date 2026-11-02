"""The Strava operator commands (RelayOperatorCli): what each prints, and its exit code.

Every line is written by fitdocs: a state word, a count, a failure class or a
fresh key. Nothing Strava answered is printed, and neither is the
subscription's address, which carries the webhook secret (and the client
credentials, in the calls that look subscriptions up).
`fitdocs_relay.cli` owns the parsing, the configuration and
the printing; this module owns the decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fitdocs_relay.crypto import new_key
from fitdocs_relay.strava.api import (
    StravaApi,
    StravaFailure,
    SubscriptionState,
)
from fitdocs_relay.strava.config import StravaConfig, TargetsConfig
from fitdocs_relay.strava.custody import Custody

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1

WEBHOOK_PATH: Final = "/strava/webhook"
WEBHOOK_TIMEOUT_S: Final = 30.0

MSG_NOT_CONFIGURED: Final = "the Strava target is not configured"

SUBSCRIBED: Final = "subscribed"
ALREADY_SUBSCRIBED: Final = "already subscribed"
SUBSCRIBED_ELSEWHERE: Final = "subscribed elsewhere"
NOT_SUBSCRIBED: Final = "not subscribed"
DELETED: Final = "deleted"


@dataclass(frozen=True)
class Report:
    """One line to print and the exit code; `stderr` names the stream."""

    code: int
    line: str
    stderr: bool = False


def webhook_callback(targets: TargetsConfig, strava: StravaConfig) -> str:
    """The address Strava is asked to call; it holds the webhook secret."""
    return f"{targets.public_url}{WEBHOOK_PATH}/{strava.webhook_token}"


def _failed(failure: StravaFailure) -> Report:
    return Report(EXIT_FAILED, f"strava failure: {failure.failure.value}", True)


def webhook_show(api: StravaApi, callback_url: str) -> Report:
    state = api.subscription_state(callback_url=callback_url, timeout=WEBHOOK_TIMEOUT_S)
    if isinstance(state, StravaFailure):
        return _failed(state)
    if state is SubscriptionState.OURS:
        return Report(EXIT_OK, SUBSCRIBED)
    if state is SubscriptionState.OTHER:
        return Report(EXIT_OK, SUBSCRIBED_ELSEWHERE)
    return Report(EXIT_OK, NOT_SUBSCRIBED)


def webhook_create(api: StravaApi, callback_url: str) -> Report:
    state = api.subscription_state(callback_url=callback_url, timeout=WEBHOOK_TIMEOUT_S)
    if isinstance(state, StravaFailure):
        return _failed(state)
    if state is SubscriptionState.OURS:
        return Report(EXIT_OK, ALREADY_SUBSCRIBED)
    if state is SubscriptionState.OTHER:
        # Nothing is created over another callback; delete it first.
        return Report(EXIT_FAILED, SUBSCRIBED_ELSEWHERE, True)
    created = api.create_subscription(
        callback_url=callback_url, timeout=WEBHOOK_TIMEOUT_S
    )
    if isinstance(created, StravaFailure):
        return _failed(created)
    return Report(EXIT_OK, SUBSCRIBED)


def webhook_delete(api: StravaApi) -> Report:
    deleted = api.delete_subscription(timeout=WEBHOOK_TIMEOUT_S)
    if isinstance(deleted, StravaFailure):
        return _failed(deleted)
    return Report(EXIT_OK, DELETED if deleted else NOT_SUBSCRIBED)


def reencrypt(custody: Custody) -> Report:
    done, unreadable = custody.reencrypt_all()
    return Report(
        EXIT_FAILED if unreadable > 0 else EXIT_OK,
        f"re-encrypted {done}, unreadable {unreadable}",
    )


def new_encryption_key() -> Report:
    return Report(EXIT_OK, new_key())
