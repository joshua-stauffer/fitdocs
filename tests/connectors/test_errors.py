"""Pins for the typed connector failures and their next-step text.

Every literal expected string below is copied from design.md's "Kind / Next
step (as printed)" table under ConnectEngine, not from any constant imported
from ``errors.py`` -- so a change to the table's wording in production code
reds the pin, rather than the pin silently tracking whatever the module says.
"""

from __future__ import annotations

import pytest

from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    ConnectorSettingsError,
    NotConnectedError,
    next_step,
)


def test_auth_failure_kind_has_the_six_members_with_the_designed_values() -> None:
    assert AuthFailureKind.REJECTED.value == "rejected"
    assert AuthFailureKind.RATE_LIMITED.value == "rate-limited"
    assert AuthFailureKind.CHALLENGE.value == "challenge"
    assert AuthFailureKind.LOCKED.value == "locked"
    assert AuthFailureKind.BLOCKED.value == "blocked"
    assert AuthFailureKind.UNAVAILABLE.value == "unavailable"
    assert {member.value for member in AuthFailureKind} == {
        "rejected",
        "rate-limited",
        "challenge",
        "locked",
        "blocked",
        "unavailable",
    }


def test_auth_failure_carries_kind_message_and_retry_after() -> None:
    failure = AuthFailure(
        AuthFailureKind.RATE_LIMITED, "too many requests", retry_after_s=12.0
    )
    assert failure.kind is AuthFailureKind.RATE_LIMITED
    assert failure.service_message == "too many requests"
    assert failure.retry_after_s == 12.0


def test_auth_failure_kind_reflects_the_kind_given_not_a_fixed_one() -> None:
    # Two distinct, pairwise-different kinds must each come back out
    # unchanged -- defeats an implementation that stores a fixed kind
    # regardless of what was passed in (e.g. always RATE_LIMITED).
    rate_limited = AuthFailure(AuthFailureKind.RATE_LIMITED, "too many requests")
    blocked = AuthFailure(AuthFailureKind.BLOCKED, "forbidden")
    assert rate_limited.kind is AuthFailureKind.RATE_LIMITED
    assert blocked.kind is AuthFailureKind.BLOCKED
    kinds: tuple[AuthFailureKind, AuthFailureKind] = (rate_limited.kind, blocked.kind)
    assert kinds[0] is not kinds[1]


def test_auth_failure_retry_after_defaults_to_none() -> None:
    failure = AuthFailure(AuthFailureKind.REJECTED, "bad credentials")
    assert failure.retry_after_s is None


def test_not_connected_error_is_a_connector_error() -> None:
    # Structural pin: NotConnectedError must be catchable wherever
    # ConnectorError is caught (design.md: "class NotConnectedError(ConnectorError)").
    assert issubclass(NotConnectedError, ConnectorError)


def test_connector_settings_error_carries_key_and_message() -> None:
    error = ConnectorSettingsError("path", "must be inside the data root")
    assert error.key == "path"
    assert error.message == "must be inside the data root"
    assert str(error) == "must be inside the data root"


@pytest.mark.parametrize("kind", [AuthFailureKind.REJECTED, AuthFailureKind.CHALLENGE])
def test_next_step_names_the_instance_for_two_different_instances(
    kind: AuthFailureKind,
) -> None:
    # A hardcoded instance name would pass an exact-string check against one
    # fixture; using two distinct instance names and requiring the outputs to
    # differ defeats that. Both REJECTED and CHALLENGE embed "{name}" in their
    # template (design.md), so both must be checked -- a fixture covering only
    # REJECTED cannot catch a hardcoded name in CHALLENGE's template.
    first = next_step(kind, name="acme-primary", retry_after_s=None)
    second = next_step(kind, name="zeta-secondary", retry_after_s=None)
    assert "acme-primary" in first
    assert "zeta-secondary" in second
    assert first != second


def test_next_step_rejected_matches_the_design_literal() -> None:
    assert next_step(
        AuthFailureKind.REJECTED, name="acme-primary", retry_after_s=None
    ) == ("Check the credentials and run `fitdocs connect acme-primary` again.")


def test_next_step_rate_limited_with_a_known_wait_names_the_wait() -> None:
    assert next_step(
        AuthFailureKind.RATE_LIMITED, name="acme-primary", retry_after_s=30.0
    ) == (
        "Wait at least 30 seconds before trying again. fitdocs never retries "
        "a sign-in: some services extend the limit on every attempt."
    )


def test_next_step_rate_limited_with_an_unknown_wait_names_no_wait() -> None:
    assert next_step(
        AuthFailureKind.RATE_LIMITED, name="acme-primary", retry_after_s=None
    ) == (
        "Wait before trying again. fitdocs never retries a sign-in: some "
        "services extend the limit on every attempt."
    )


def test_next_step_rate_limited_with_a_fractional_wait_renders_it_untruncated() -> None:
    result = next_step(
        AuthFailureKind.RATE_LIMITED, name="acme-primary", retry_after_s=12.5
    )
    assert "12.5 seconds" in result
    assert "12 seconds" not in result


def test_next_step_rate_limited_wait_changes_with_the_seconds_given() -> None:
    # Two distinct, pairwise-different retry_after_s values must produce two
    # distinct rendered waits -- defeats an implementation that always renders
    # a single fixed placeholder text regardless of the value passed in.
    short_wait = next_step(
        AuthFailureKind.RATE_LIMITED, name="acme-primary", retry_after_s=5.0
    )
    long_wait = next_step(
        AuthFailureKind.RATE_LIMITED, name="acme-primary", retry_after_s=90.0
    )
    assert "5 seconds" in short_wait
    assert "90 seconds" in long_wait
    assert short_wait != long_wait


def test_next_step_challenge_matches_the_design_literal() -> None:
    assert next_step(
        AuthFailureKind.CHALLENGE, name="acme-primary", retry_after_s=None
    ) == (
        "The service asked for a verification step fitdocs cannot complete. "
        "Complete it on the service's own site, then run `fitdocs connect "
        "acme-primary` again."
    )


def test_next_step_locked_matches_the_design_literal() -> None:
    result = next_step(AuthFailureKind.LOCKED, name="acme-primary", retry_after_s=None)
    assert result == (
        "The service reports the account locked. Unlock it on the service's "
        "own site; do not try again until it is unlocked."
    )


def test_next_step_blocked_matches_the_design_literal() -> None:
    result = next_step(AuthFailureKind.BLOCKED, name="acme-primary", retry_after_s=None)
    assert result == (
        "The service refused this client. Please report it at "
        "https://github.com/joshua-stauffer/fitdocs/issues with the message above."
    )


def test_next_step_unavailable_matches_the_design_literal() -> None:
    result = next_step(
        AuthFailureKind.UNAVAILABLE, name="acme-primary", retry_after_s=None
    )
    assert result == "The service could not be reached. Try again later."
