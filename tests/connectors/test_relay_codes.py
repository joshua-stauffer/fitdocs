"""Pins for the closed relay code vocabulary (relay-server task 1.1; Req 4.2,
4.3, 4.10, 15.6).

Every literal below is copied from the table under "SharedRelayCodes" in the
relay-server design.md, not imported from the module, so a change to the
module reds the pin rather than the pin tracking the module.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import fitdocs.connectors.relay_codes as relay_codes
from fitdocs.connectors.relay_codes import (
    RELAY_CODES,
    CodeOrigin,
    RelayCode,
    RelayCodeInfo,
    explain,
)

#: The vocabulary in declaration order: (name, value, status, origin,
#: explanation).
_PINNED: tuple[tuple[str, str, int | None, str, str], ...] = (
    ("OK", "ok", 200, "relay", "The relay accepted the request."),
    (
        "TOKEN_MISSING",
        "token-missing",
        401,
        "relay",
        "The request carried no relay token.",
    ),
    (
        "TOKEN_UNKNOWN",
        "token-unknown",
        401,
        "relay",
        "The relay does not recognise this token.",
    ),
    (
        "TOKEN_REVOKED",
        "token-revoked",
        401,
        "relay",
        "This relay token has been revoked.",
    ),
    (
        "ENVELOPE_UNSUPPORTED",
        "envelope-unsupported",
        400,
        "relay",
        "The relay does not serve this envelope version.",
    ),
    (
        "REQUEST_MALFORMED",
        "request-malformed",
        400,
        "relay",
        "The relay could not read the request.",
    ),
    (
        "REQUEST_TOO_LARGE",
        "request-too-large",
        413,
        "relay",
        "The request is larger than the relay accepts.",
    ),
    ("NOT_OFFERED", "not-offered", 404, "relay", "This relay does not offer that."),
    (
        "RATE_LIMITED",
        "rate-limited",
        429,
        "relay",
        "The relay is limiting requests; wait before trying again.",
    ),
    (
        "UNAVAILABLE",
        "unavailable",
        503,
        "relay",
        "The relay is temporarily unavailable.",
    ),
    (
        "RELAY_FAILURE",
        "relay-failure",
        500,
        "relay",
        "The relay failed while handling the request.",
    ),
    (
        "STORAGE_UNREACHABLE",
        "storage-unreachable",
        503,
        "relay",
        "The relay cannot reach its database.",
    ),
    (
        "SCHEMA_BEHIND",
        "schema-behind",
        503,
        "relay",
        "The relay's database needs migrating.",
    ),
    (
        "SCHEMA_AHEAD",
        "schema-ahead",
        503,
        "relay",
        "The relay's database was migrated by a newer relay.",
    ),
    (
        "REGISTRATION_STARTED",
        "registration-started",
        200,
        "relay",
        "The relay started the registration.",
    ),
    (
        "REGISTRATION_PENDING",
        "registration-pending",
        200,
        "relay",
        "The registration is waiting for confirmation.",
    ),
    (
        "REGISTRATION_SLOW_DOWN",
        "registration-slow-down",
        200,
        "relay",
        "The relay asked fitdocs to poll less often.",
    ),
    (
        "REGISTRATION_ISSUED",
        "registration-issued",
        200,
        "relay",
        "The relay issued a relay token.",
    ),
    (
        "REGISTRATION_REFUSED",
        "registration-refused",
        403,
        "relay",
        "The relay refused the registration.",
    ),
    (
        "REGISTRATION_EXPIRED",
        "registration-expired",
        410,
        "relay",
        "The registration expired before it was confirmed.",
    ),
    (
        "RELAY_UNREACHABLE",
        "relay-unreachable",
        None,
        "client",
        "fitdocs could not reach the relay.",
    ),
    (
        "ANSWER_MALFORMED",
        "answer-malformed",
        None,
        "client",
        "The relay's answer was not a valid fitdocs relay answer.",
    ),
)


def test_the_pin_itself_has_22_distinct_codes() -> None:
    assert len(_PINNED) == 22
    assert len({row[1] for row in _PINNED}) == 22


def test_names_and_values_are_the_22_codes_in_declaration_order() -> None:
    assert [(m.name, m.value) for m in RelayCode][:22] == [
        (r[0], r[1]) for r in _PINNED
    ]


def test_the_registry_covers_exactly_the_enum() -> None:
    assert set(RELAY_CODES) == set(RelayCode)
    for code, info in RELAY_CODES.items():
        assert isinstance(info, RelayCodeInfo)
        assert info.code is code


def test_every_code_has_a_nonblank_single_sentence_explanation() -> None:
    explanations = []
    for code in RelayCode:
        text = explain(code)
        assert text.strip() == text and text, code
        assert text.endswith("."), code
        assert sum(text.count(c) for c in ".!?") == 1, code
        explanations.append(text)
    assert len(set(explanations)) == len(explanations)


def test_explain_returns_the_registry_explanation() -> None:
    for code in RelayCode:
        assert explain(code) == RELAY_CODES[code].explanation


@pytest.mark.parametrize(("name", "value", "status", "origin", "explanation"), _PINNED)
def test_status_origin_and_explanation_per_code(
    name: str, value: str, status: int | None, origin: str, explanation: str
) -> None:
    info = RELAY_CODES[RelayCode(value)]
    assert info.http_status == status
    assert info.origin == CodeOrigin(origin)
    assert info.explanation == explanation
    assert explain(RelayCode(value)) == explanation


def test_a_status_is_present_exactly_when_the_origin_is_the_relay() -> None:
    every = list(RELAY_CODES.values())
    relay_side = [i for i in every if i.origin is CodeOrigin.RELAY]
    client_side = [i for i in every if i.origin is CodeOrigin.CLIENT]
    assert relay_side and client_side, "a side of the rule is empty"
    assert all(isinstance(i.http_status, int) for i in relay_side)
    assert all(i.http_status is None for i in client_side)


def test_origin_values() -> None:
    assert [o.value for o in CodeOrigin] == ["relay", "client"]


def test_the_module_imports_only_the_standard_library_and_no_http() -> None:
    path = Path(relay_codes.__file__ or "")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import leaves the module"
            names.append(node.module or "")
    assert names, "the walk found no imports; it is looking at the wrong file"
    allowed = {"__future__", "enum", "dataclasses", "typing", "collections.abc"}
    assert set(names) <= allowed, sorted(set(names) - allowed)
