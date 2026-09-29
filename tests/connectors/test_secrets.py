"""Pins for :mod:`fitdocs.connectors.secrets` (Requirements 10.1, 10.2, 10.3)."""

from __future__ import annotations

import pytest

from fitdocs.connectors.secrets import REDACTED, Redactor, Secret

VALUE = "sk-super-secret-token-9f8e7d"


def test_redacted_marker_matches_the_design_literal() -> None:
    # A pin on the literal itself: a redactor that swapped in a different
    # marker string would pass every other test here by construction.
    assert REDACTED == "<redacted>"


def test_str_repr_and_format_show_only_the_marker() -> None:
    secret = Secret(VALUE)

    assert str(secret) == REDACTED
    assert repr(secret) == REDACTED
    assert format(secret) == REDACTED
    assert VALUE not in str(secret)
    assert VALUE not in repr(secret)


def test_format_with_a_format_spec_still_shows_only_the_marker() -> None:
    secret = Secret(VALUE)

    assert format(secret, ">40") == REDACTED
    assert format(secret, ".3") == REDACTED
    assert format(secret, "d") == REDACTED


def test_secret_inside_an_fstring_never_contains_the_value() -> None:
    secret = Secret(VALUE)

    rendered = f"token={secret}"

    assert VALUE not in rendered
    assert REDACTED in rendered


def test_secret_repr_conversion_inside_an_fstring_never_contains_the_value() -> None:
    secret = Secret(VALUE)

    rendered = f"token={secret!r}"

    assert VALUE not in rendered
    assert REDACTED in rendered


def test_secret_inside_an_exception_message_built_with_an_fstring() -> None:
    secret = Secret(VALUE)

    try:
        raise ValueError(f"auth failed with token {secret!r}")
    except ValueError as exc:
        message = str(exc)

    assert VALUE not in message
    assert REDACTED in message


def test_secret_passed_directly_as_an_exception_argument() -> None:
    secret = Secret(VALUE)

    try:
        raise ValueError(secret)
    except ValueError as exc:
        message = str(exc)

    assert VALUE not in message
    assert REDACTED in message


def test_reveal_is_the_only_way_to_read_the_value() -> None:
    secret = Secret(VALUE)

    # Falsity first: the ordinary text forms do not equal the raw value.
    assert str(secret) != VALUE
    assert repr(secret) != VALUE

    assert secret.reveal() == VALUE


def test_secrets_are_equal_by_value() -> None:
    assert Secret(VALUE) == Secret(VALUE)
    assert hash(Secret(VALUE)) == hash(Secret(VALUE))
    assert Secret(VALUE) != Secret(VALUE + "x")


def test_secret_rejects_a_non_string_value() -> None:
    with pytest.raises(TypeError):
        Secret(12345)  # type: ignore[arg-type]


def test_redactor_ignores_the_empty_string() -> None:
    redactor = Redactor()

    redactor.add("")
    text = "nothing secret in this sentence"

    assert redactor.redact(text) == text


def test_redactor_replaces_a_registered_value() -> None:
    redactor = Redactor()
    redactor.add(VALUE)

    text = f"Authorization: Bearer {VALUE}"

    assert VALUE not in redactor.redact(text)
    assert REDACTED in redactor.redact(text)


def test_redactor_replaces_every_occurrence_not_just_the_first() -> None:
    redactor = Redactor()
    redactor.add(VALUE)

    text = f"first={VALUE} again second={VALUE}"
    result = redactor.redact(text)

    assert VALUE not in result
    assert result.count(REDACTED) == 2


def test_redactor_registers_both_the_raw_and_percent_encoded_forms() -> None:
    redactor = Redactor()
    # A value containing characters that percent-encoding changes.
    raw = "top secret/value with spaces"
    encoded = "top%20secret%2Fvalue%20with%20spaces"
    redactor.add(raw)

    # Both forms appear in the same text -- a redactor that registered only
    # the encoded form (dropping the raw one) would leave the raw occurrence
    # exposed here.
    text = f"raw={raw} url?token={encoded}"
    result = redactor.redact(text)

    assert raw not in result
    assert encoded not in result
    assert result.count(REDACTED) == 2


@pytest.mark.parametrize(
    ("short", "long"),
    [
        # `short` sorts after `long`: defeats descending-alphabetical order.
        ("zz9", "a-zz9-tail"),
        # `short` sorts before `long`: defeats ascending-alphabetical order.
        ("b12", "zz-b12-tail"),
    ],
)
def test_redactor_prefers_the_longest_registered_value_first(
    short: str, long: str
) -> None:
    # In both pairs `short` sits inside `long` but not at its start, so
    # ascending-length order leaves fragments of `long` exposed too.
    redactor = Redactor()
    redactor.add(long)
    redactor.add(short)

    result = redactor.redact(f"see {long} here")

    # Replacing `short` first would consume it inside `long`, leaving the
    # fragments of `long` around it exposed once the full `long` value no
    # longer matches.
    assert result == f"see {REDACTED} here"


def test_redactor_accepts_a_secret_instance_directly() -> None:
    redactor = Redactor()
    redactor.add(Secret(VALUE))

    result = redactor.redact(f"leaked: {VALUE}")

    assert VALUE not in result
    assert REDACTED in result
