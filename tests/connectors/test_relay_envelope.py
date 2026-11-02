"""Pins for the envelope v1 codec (relay-server task 1.2; Req 4.1, 4.4, 4.5,
4.6, 4.7, 15.6).

Every literal is copied from "SharedEnvelopeCodec" and "Data Contracts --
Envelope v1" in the relay-server design.md, not imported from the module, so
a change to the module reds the pin rather than the pin tracking the module.
Each bound is tested one step inside and one step outside. The design forces
two ties between bounds: MAX_POLL_INTERVAL_S and MIN_EXPIRES_IN_S are both 60,
and MAX_REQUEST_BYTES and MAX_ANSWER_BYTES are both 65,536. Under these ties,
using one name of a pair in place of the other changes no behaviour, so no
test here can detect it; the constants pin guards each name's value, not which
name a parser uses.
"""

from __future__ import annotations

import ast
import dataclasses
import json
from collections.abc import Callable
from pathlib import Path

import pytest

import fitdocs.connectors.relay_envelope as env
from fitdocs.connectors.relay_codes import RELAY_CODES, CodeOrigin, RelayCode
from fitdocs.connectors.relay_envelope import (
    Answer,
    CapabilitiesData,
    EnvelopeError,
    StartedData,
    decode_answer,
    decode_request,
    encode_answer,
    encode_request,
    is_email,
    is_poll_secret,
    is_user_code,
    parse_capabilities,
    parse_envelopes,
    parse_issued,
    parse_retry_after,
    parse_started,
    split_relay_token,
)

_ID = "a" * 16
_SECRET = "a" * 52
_TOKEN = f"fdr1_{_ID}_{_SECRET}"
_OK = b'{"envelope":1,"code":"ok","data":{}}'
_DEEP = b'{"envelope":1,"code":"ok","data":{"k":' + b"[" * 30000 + b"]" * 30000 + b"}}"

#: The module's fixed messages, copied here rather than imported.
_FIXED_MESSAGES = frozenset(
    {
        "The body is not a valid envelope JSON object.",
        "The body is larger than the envelope allows.",
        "The answer is not a valid envelope v1 answer.",
        "The request is not a valid envelope v1 request.",
        "The answer data does not match its route's schema.",
        "The value cannot be encoded as an envelope v1 body.",
    }
)


def _answer(**overrides: object) -> bytes:
    body: dict[str, object] = {"envelope": 1, "code": "ok", "data": {}}
    body.update(overrides)
    return json.dumps(body).encode()


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


def test_the_constants_are_the_designs_literals() -> None:
    assert env.ENVELOPE_VERSION == 1
    assert env.SERVED_ENVELOPES == (1,)
    assert env.ROUTE_LIVEZ == "/livez"
    assert env.ROUTE_READYZ == "/readyz"
    assert env.ROUTE_CAPABILITIES == "/v1/capabilities"
    assert env.ROUTE_TOKEN == "/v1/token"
    assert env.ROUTE_TOKEN_REVOKE == "/v1/token/revoke"
    assert env.ROUTE_REGISTRATIONS == "/v1/registrations"
    assert env.ROUTE_REGISTRATION_POLL == "/v1/registrations/poll"
    assert env.TOKEN_PREFIX == "fdr1"
    assert env.TOKEN_RE == r"^fdr1_([a-z2-7]{16})_([a-z2-7]{52})$"
    assert env.USER_CODE_RE == r"^[BCDFGHJKLMNPQRSTVWXZ]{4}-[BCDFGHJKLMNPQRSTVWXZ]{4}$"
    assert env.POLL_SECRET_RE == r"^[A-Za-z0-9_-]{32,128}$"
    assert env.TARGET_ID_RE == r"^[a-z][a-z0-9-]{0,31}$"
    assert env.EMAIL_RE == r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$"
    assert env.MAX_EMAIL_CHARS == 254
    assert env.MIN_POLL_INTERVAL_S == 1
    assert env.MAX_POLL_INTERVAL_S == 60
    assert env.SLOW_DOWN_STEP_S == 5
    assert env.MIN_EXPIRES_IN_S == 60
    assert env.MAX_EXPIRES_IN_S == 3600
    assert env.MAX_REQUEST_BYTES == 65_536
    assert env.MAX_ANSWER_BYTES == 65_536


# --------------------------------------------------------------------------- #
# Field formats
# --------------------------------------------------------------------------- #


class TestToken:
    def test_a_valid_token_splits_into_id_and_secret(self) -> None:
        token = "fdr1_" + "abcdefg234567abc" + "_" + "z" * 26 + "2" * 26
        assert split_relay_token(token) == ("abcdefg234567abc", "z" * 26 + "2" * 26)

    @pytest.mark.parametrize(
        ("id_len", "secret_len", "ok"),
        [
            (15, 52, False),
            (16, 52, True),
            (17, 52, False),
            (16, 51, False),
            (16, 53, False),
        ],
    )
    def test_the_lengths_are_exact_on_both_sides(
        self, id_len: int, secret_len: int, ok: bool
    ) -> None:
        got = split_relay_token(f"fdr1_{'b' * id_len}_{'c' * secret_len}")
        assert (got is not None) is ok

    @pytest.mark.parametrize("char", ["1", "0", "8", "9", "A", "-", "_", "=", " "])
    def test_characters_outside_a_to_z_and_2_to_7_are_refused(self, char: str) -> None:
        assert split_relay_token(f"fdr1_{char}{'a' * 15}_{_SECRET}") is None
        assert split_relay_token(f"fdr1_{_ID}_{char}{'a' * 51}") is None

    @pytest.mark.parametrize("char", ["2", "7", "a", "z"])
    def test_the_edge_characters_are_accepted(self, char: str) -> None:
        assert split_relay_token(f"fdr1_{char * 16}_{char * 52}") is not None

    @pytest.mark.parametrize(
        "value",
        [
            "",
            _TOKEN + "\n",
            "\n" + _TOKEN,
            " " + _TOKEN,
            _TOKEN + " ",
            "fdr2_" + _ID + "_" + _SECRET,
            "FDR1_" + _ID + "_" + _SECRET,
            f"fdr1{_ID}_{_SECRET}",
            f"fdr1_{_ID}{_SECRET}",
        ],
    )
    def test_malformed_wrappers_are_refused(self, value: str) -> None:
        assert split_relay_token(value) is None

    def test_a_non_string_is_refused(self) -> None:
        assert split_relay_token(None) is None  # type: ignore[arg-type]


_CONSONANTS = "BCDFGHJKLMNPQRSTVWXZ"


class TestUserCode:
    def test_every_permitted_letter_is_accepted(self) -> None:
        for letter in _CONSONANTS:
            assert is_user_code(f"{letter * 4}-{letter * 4}"), letter

    def test_every_other_letter_and_case_is_refused(self) -> None:
        import string

        outside = [c for c in string.ascii_uppercase if c not in _CONSONANTS]
        assert outside == ["A", "E", "I", "O", "U", "Y"]
        for letter in outside:
            assert not is_user_code(f"{letter}BCD-FGHJ"), letter
            assert not is_user_code(f"BCDF-GHJ{letter}"), letter
        for letter in _CONSONANTS:
            assert not is_user_code(f"{letter.lower()}CDF-GHJK"), letter

    @pytest.mark.parametrize(
        "value",
        [
            "BCDFGHJK",
            "BCD-FGHJK",
            "BCDFG-HJK",
            "BCD-FGH",
            "BCDFG-HJKLM",
            "BCDF_GHJK",
            "BCDF GHJK",
            "BCDF-GHJK\n",
            " BCDF-GHJK",
            "BCDF-GHJ1",
            "",
        ],
    )
    def test_malformed_shapes_are_refused(self, value: str) -> None:
        assert not is_user_code(value)

    def test_the_accepted_form(self) -> None:
        assert is_user_code("BCDF-GHJK")

    def test_a_non_string_is_refused(self) -> None:
        assert not is_user_code(12345678)


class TestPollSecret:
    @pytest.mark.parametrize(
        ("length", "ok"),
        [(31, False), (32, True), (33, True), (127, True), (128, True), (129, False)],
    )
    def test_the_length_bounds_on_both_sides(self, length: int, ok: bool) -> None:
        assert is_poll_secret("p" * length) is ok

    def test_the_alphabet_includes_underscore_hyphen_and_both_cases(self) -> None:
        assert is_poll_secret("aZ09_-" + "x" * 26)

    @pytest.mark.parametrize("char", ["+", "/", "=", " ", ".", "\n", "é"])
    def test_other_characters_are_refused(self, char: str) -> None:
        assert not is_poll_secret(char + "x" * 31)
        assert not is_poll_secret("x" * 31 + char)

    def test_a_non_string_is_refused(self) -> None:
        assert not is_poll_secret(b"x" * 40)


class TestTargetId:
    @pytest.mark.parametrize(
        ("value", "ok"),
        [
            ("a", True),
            ("strava", True),
            ("a" + "b" * 30, True),
            ("a" + "b" * 31, True),
            ("a" + "b" * 32, False),
            ("a-1", True),
            ("1a", False),
            ("-a", False),
            ("Aa", False),
            ("a_b", False),
            ("", False),
            ("a\n", False),
        ],
    )
    def test_the_format(self, value: str, ok: bool) -> None:
        assert env.is_target_id(value) is ok

    def test_the_longest_id_is_32_characters(self) -> None:
        assert env.is_target_id("t" * 32)
        assert not env.is_target_id("t" * 33)


def _email_of_length(total: int, local_len: int = 10) -> str:
    domain_len = total - local_len - 1
    domain = "d" * (domain_len - 3) + ".co"
    email = "l" * local_len + "@" + domain
    assert len(email) == total
    return email


class TestEmail:
    def test_a_plain_address_is_accepted(self) -> None:
        assert is_email("someone@example.org")

    def test_the_local_part_is_at_most_64_characters(self) -> None:
        assert is_email("l" * 64 + "@example.org")
        assert not is_email("l" * 65 + "@example.org")

    def test_the_whole_address_is_at_most_254_characters(self) -> None:
        assert is_email(_email_of_length(253))
        assert is_email(_email_of_length(254))
        assert not is_email(_email_of_length(255))
        assert not is_email(_email_of_length(300))

    def test_the_254_limit_is_independent_of_the_local_part_limit(self) -> None:
        assert is_email(_email_of_length(254, local_len=64))
        assert not is_email(_email_of_length(255, local_len=64))

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "plain",
            "@example.org",
            "a@b",
            "a@b.",
            "a@.b",
            "a@@b.co",
            "a@b@c.co",
            "a b@c.co",
            "a@b c.co",
            "a@b.co\n",
            " a@b.co",
            "a\t@b.co",
        ],
    )
    def test_malformed_addresses_are_refused(self, value: str) -> None:
        assert not is_email(value)

    def test_a_non_string_is_refused(self) -> None:
        assert not is_email(None)


# --------------------------------------------------------------------------- #
# Answers: encode
# --------------------------------------------------------------------------- #


class TestEncodeAnswer:
    def test_the_canonical_form_is_compact_with_the_envelope_first(self) -> None:
        assert encode_answer(Answer(RelayCode.OK, {})) == _OK

    def test_outcome_is_written_last_when_present(self) -> None:
        raw = encode_answer(Answer(RelayCode.OK, {"z": 1, "a": 2}, outcome="done"))
        assert (
            raw == b'{"envelope":1,"code":"ok","data":{"z":1,"a":2},"outcome":"done"}'
        )

    def test_data_keys_keep_the_order_given(self) -> None:
        raw = encode_answer(
            Answer(RelayCode.REGISTRATION_STARTED, {"m": 1, "b": 2, "x": 3})
        )
        assert raw == (
            b'{"envelope":1,"code":"registration-started","data":{"m":1,"b":2,"x":3}}'
        )

    def test_text_is_utf8_not_escaped(self) -> None:
        raw = encode_answer(Answer(RelayCode.OK, {"k": "é"}))
        assert raw.endswith('"data":{"k":"é"}}'.encode())

    def test_a_client_origin_code_cannot_be_emitted(self) -> None:
        for code in RelayCode:
            if RELAY_CODES[code].origin is CodeOrigin.CLIENT:
                with pytest.raises(EnvelopeError):
                    encode_answer(Answer(code, {}))

    @pytest.mark.parametrize("outcome", ["", 5])
    def test_a_blank_or_non_string_outcome_is_refused(self, outcome: object) -> None:
        with pytest.raises(EnvelopeError):
            encode_answer(Answer(RelayCode.OK, {}, outcome=outcome))  # type: ignore[arg-type]

    def test_nan_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            encode_answer(Answer(RelayCode.OK, {"k": float("nan")}))

    def test_an_unserialisable_value_is_refused_with_envelope_error(self) -> None:
        with pytest.raises(EnvelopeError):
            encode_answer(Answer(RelayCode.OK, {"k": object()}))

    def test_the_size_limit_on_both_sides(self) -> None:
        shell = len(encode_answer(Answer(RelayCode.OK, {"k": ""})))
        fits = encode_answer(Answer(RelayCode.OK, {"k": "x" * (65_536 - shell)}))
        assert len(fits) == 65_536
        with pytest.raises(EnvelopeError):
            encode_answer(Answer(RelayCode.OK, {"k": "x" * (65_537 - shell)}))

    def test_every_relay_code_round_trips(self) -> None:
        seen = 0
        for code, info in RELAY_CODES.items():
            if info.origin is CodeOrigin.RELAY:
                seen += 1
                answer = Answer(code, {"n": seen}, outcome="o")
                assert decode_answer(encode_answer(answer)) == answer
        assert seen >= 20


# --------------------------------------------------------------------------- #
# Answers: decode
# --------------------------------------------------------------------------- #


class TestDecodeAnswer:
    def test_a_valid_answer(self) -> None:
        got = decode_answer(_answer(code="registration-pending", data={"k": 1}))
        assert got == Answer(RelayCode.REGISTRATION_PENDING, {"k": 1}, None)
        assert got.outcome is None

    def test_any_top_level_key_order_is_accepted(self) -> None:
        raw = b'{"data":{},"outcome":"x","code":"ok","envelope":1}'
        assert decode_answer(raw) == Answer(RelayCode.OK, {}, "x")

    def test_an_answer_carrying_outcome_decodes_with_it_preserved(self) -> None:
        got = decode_answer(_answer(outcome="published"))
        assert got.outcome == "published"

    @pytest.mark.parametrize("outcome", ["", None, 5, True, ["x"], {"a": 1}])
    def test_a_blank_or_non_string_outcome_is_malformed(self, outcome: object) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(_answer(outcome=outcome))

    def test_any_other_top_level_key_is_malformed(self) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(_answer(extra=1))

    def test_an_unknown_key_beside_a_valid_outcome_is_still_malformed(self) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(_answer(outcome="x", extra=1))

    @pytest.mark.parametrize("key", ["envelope", "code", "data"])
    def test_each_required_key_is_required(self, key: str) -> None:
        body = json.loads(_OK)
        del body[key]
        with pytest.raises(EnvelopeError):
            decode_answer(json.dumps(body).encode())

    @pytest.mark.parametrize("version", [True, False, 0, 2, -1, 1.0, "1", None, [1]])
    def test_the_envelope_must_be_a_served_int_never_a_bool(
        self, version: object
    ) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(_answer(envelope=version))

    def test_a_client_origin_code_is_refused(self) -> None:
        for name in ("relay-unreachable", "answer-malformed"):
            with pytest.raises(EnvelopeError):
                decode_answer(_answer(code=name))

    @pytest.mark.parametrize("code", ["nope", "OK", "", 1, None, ["ok"]])
    def test_an_unknown_or_non_string_code_is_refused(self, code: object) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(_answer(code=code))

    @pytest.mark.parametrize("data", [[], None, "x", 1, True])
    def test_data_must_be_an_object(self, data: object) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(_answer(data=data))

    @pytest.mark.parametrize(
        "raw",
        [
            b'{"envelope":1,"envelope":1,"code":"ok","data":{}}',
            b'{"envelope":1,"code":"ok","data":{"k":1,"k":2}}',
            b'{"envelope":1,"code":"ok","data":{"n":{"k":1,"k":1}}}',
        ],
    )
    def test_duplicate_keys_are_refused_at_any_depth(self, raw: bytes) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(raw)

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e999"])
    def test_non_finite_numbers_are_refused(self, literal: str) -> None:
        raw = f'{{"envelope":1,"code":"ok","data":{{"k":{literal}}}}}'.encode()
        with pytest.raises(EnvelopeError):
            decode_answer(raw)

    def test_finite_floats_in_data_are_accepted(self) -> None:
        assert decode_answer(b'{"envelope":1,"code":"ok","data":{"k":1.5}}').data == {
            "k": 1.5
        }

    @pytest.mark.parametrize(
        "raw",
        [
            b"",
            b"not json",
            b"[]",
            b"null",
            b"1",
            b'"ok"',
            b'{"envelope":1,"code":"ok","data":{}} trailing',
            _OK[:-1],
            b"\xff\xfe" + _OK,
            b"\xef\xbb\xbf" + _OK,
            _OK.decode().encode("utf-16"),
            _OK.decode().encode("utf-32"),
            b'{"envelope":1,"code":"ok","data":{"k":"\xff"}}',
        ],
    )
    def test_non_object_or_non_utf8_bodies_are_refused(self, raw: bytes) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(raw)

    def test_deep_nesting_within_the_size_limit_is_refused(self) -> None:
        raw = _DEEP
        assert len(raw) < 65_536, "the size rule would refuse it before parsing"
        with pytest.raises(EnvelopeError):
            decode_answer(raw)

    def test_a_non_bytes_body_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            decode_answer(_OK.decode())  # type: ignore[arg-type]

    def test_the_size_limit_on_both_sides(self) -> None:
        shell = len(b'{"envelope":1,"code":"ok","data":{"k":""}}')

        def body(total: int) -> bytes:
            raw = (
                '{"envelope":1,"code":"ok","data":{"k":"%s"}}' % ("x" * (total - shell))
            ).encode()
            assert len(raw) == total
            return raw

        assert decode_answer(body(65_536)).data == {"k": "x" * (65_536 - shell)}
        with pytest.raises(EnvelopeError):
            decode_answer(body(65_537))


# --------------------------------------------------------------------------- #
# Requests
# --------------------------------------------------------------------------- #

_EMAIL_FIELDS = frozenset({"email"})


class TestRequests:
    def test_encode_is_compact_and_keeps_the_order_given(self) -> None:
        assert encode_request({"b": 1, "a": "é"}) == '{"b":1,"a":"é"}'.encode()

    def test_a_request_round_trips(self) -> None:
        raw = encode_request({"email": "a@b.co"})
        got = decode_request(raw, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS)
        assert got == {"email": "a@b.co"}

    def test_the_empty_request(self) -> None:
        none = frozenset[str]()
        assert decode_request(b"{}", required=none, allowed=none) == {}

    def test_a_missing_required_field_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            decode_request(b"{}", required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS)

    def test_a_field_outside_allowed_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            decode_request(
                b'{"email":"a@b.co","x":1}',
                required=_EMAIL_FIELDS,
                allowed=_EMAIL_FIELDS,
            )

    def test_an_optional_allowed_field_may_be_absent_or_present(self) -> None:
        allowed = frozenset({"email", "note"})
        assert decode_request(b'{"email":"e"}', required=_EMAIL_FIELDS, allowed=allowed)
        assert decode_request(
            b'{"email":"e","note":"n"}', required=_EMAIL_FIELDS, allowed=allowed
        ) == {"email": "e", "note": "n"}

    @pytest.mark.parametrize(
        "raw",
        [
            b'{"email":"a","email":"b"}',
            b'{"email":NaN}',
            b'{"email":Infinity}',
            b'{"email":1e999}',
            b"[]",
            b"",
            b"\xff",
        ],
    )
    def test_strict_decoding_applies_to_requests(self, raw: bytes) -> None:
        with pytest.raises(EnvelopeError):
            decode_request(raw, required=frozenset(), allowed=_EMAIL_FIELDS)

    def test_the_decode_size_limit_on_both_sides(self) -> None:
        shell = len(b'{"email":""}')
        fits = ('{"email":"%s"}' % ("x" * (65_536 - shell))).encode()
        over = ('{"email":"%s"}' % ("x" * (65_537 - shell))).encode()
        assert len(fits) == 65_536 and len(over) == 65_537
        assert decode_request(fits, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS)
        with pytest.raises(EnvelopeError):
            decode_request(over, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS)

    def test_the_encode_size_limit_on_both_sides(self) -> None:
        shell = len(encode_request({"email": ""}))
        assert len(encode_request({"email": "x" * (65_536 - shell)})) == 65_536
        with pytest.raises(EnvelopeError):
            encode_request({"email": "x" * (65_537 - shell)})

    def test_an_explicit_larger_bound_governs_decode_on_both_sides(self) -> None:
        bound = 100_000
        shell = len(b'{"email":""}')
        fits = ('{"email":"%s"}' % ("x" * (bound - shell))).encode()
        over = ('{"email":"%s"}' % ("x" * (bound + 1 - shell))).encode()
        assert len(fits) == bound and len(over) == bound + 1
        got = decode_request(
            fits, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS, max_bytes=bound
        )
        assert len(got["email"]) == bound - shell  # type: ignore[arg-type]
        with pytest.raises(EnvelopeError):
            decode_request(
                over, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS, max_bytes=bound
            )

    def test_an_explicit_larger_bound_governs_encode_on_both_sides(self) -> None:
        bound = 100_000
        shell = len(encode_request({"email": ""}))
        fits = encode_request({"email": "x" * (bound - shell)}, max_bytes=bound)
        assert len(fits) == bound
        with pytest.raises(EnvelopeError):
            encode_request({"email": "x" * (bound + 1 - shell)}, max_bytes=bound)

    def test_an_explicit_smaller_bound_also_governs(self) -> None:
        shell = len(encode_request({"email": ""}))
        assert len(encode_request({"email": "x" * (50 - shell)}, max_bytes=50)) == 50
        with pytest.raises(EnvelopeError):
            encode_request({"email": "x" * (51 - shell)}, max_bytes=50)

    def test_an_explicit_smaller_bound_also_governs_decode(self) -> None:
        shell = len(b'{"email":""}')
        fits = ('{"email":"%s"}' % ("x" * (50 - shell))).encode()
        over = ('{"email":"%s"}' % ("x" * (51 - shell))).encode()
        assert len(fits) == 50 and len(over) == 51
        decode_request(
            fits, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS, max_bytes=50
        )
        with pytest.raises(EnvelopeError):
            decode_request(
                over, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS, max_bytes=50
            )

    def test_deep_nesting_within_the_size_limit_is_refused(self) -> None:
        raw = b'{"email":' + b"[" * 30000 + b"]" * 30000 + b"}"
        assert len(raw) < 65_536, "the size rule would refuse it before parsing"
        with pytest.raises(EnvelopeError):
            decode_request(raw, required=_EMAIL_FIELDS, allowed=_EMAIL_FIELDS)

    def test_encode_refuses_nan(self) -> None:
        with pytest.raises(EnvelopeError):
            encode_request({"k": float("nan")})


# --------------------------------------------------------------------------- #
# Per-route data parsers
# --------------------------------------------------------------------------- #

_PS = "p" * 40


def _started(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "user_code": "BCDF-GHJK",
        "poll_secret": _PS,
        "interval_s": 7,
        "expires_in_s": 900,
    }
    data.update(overrides)
    return data


class TestParseStarted:
    def test_a_valid_start(self) -> None:
        assert parse_started(_started()) == StartedData("BCDF-GHJK", _PS, 7, 900)

    @pytest.mark.parametrize(
        ("interval", "ok"),
        [(0, False), (1, True), (2, True), (59, True), (60, True), (61, False)],
    )
    def test_the_interval_bounds_on_both_sides(self, interval: int, ok: bool) -> None:
        if ok:
            assert parse_started(_started(interval_s=interval)).interval_s == interval
        else:
            with pytest.raises(EnvelopeError):
                parse_started(_started(interval_s=interval))

    @pytest.mark.parametrize(
        ("expires", "ok"),
        [
            (59, False),
            (60, True),
            (61, True),
            (3599, True),
            (3600, True),
            (3601, False),
        ],
    )
    def test_the_expiry_bounds_on_both_sides(self, expires: int, ok: bool) -> None:
        if ok:
            assert parse_started(_started(expires_in_s=expires)).expires_in_s == expires
        else:
            with pytest.raises(EnvelopeError):
                parse_started(_started(expires_in_s=expires))

    def test_the_two_ranges_are_not_confused(self) -> None:
        with pytest.raises(EnvelopeError):
            parse_started(_started(interval_s=900))
        with pytest.raises(EnvelopeError):
            parse_started(_started(expires_in_s=7))

    @pytest.mark.parametrize("value", [True, 5.0, "5", None, [5]])
    def test_the_numbers_must_be_non_bool_ints(self, value: object) -> None:
        with pytest.raises(EnvelopeError):
            parse_started(_started(interval_s=value))
        with pytest.raises(EnvelopeError):
            parse_started(_started(expires_in_s=value))

    def test_a_user_code_with_a_vowel_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            parse_started(_started(user_code="BCDA-GHJK"))

    def test_a_malformed_poll_secret_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            parse_started(_started(poll_secret="p" * 31))
        assert parse_started(_started(poll_secret="p" * 32)).poll_secret == "p" * 32

    @pytest.mark.parametrize("value", [None, 5, ["BCDF-GHJK"]])
    def test_non_string_codes_are_refused(self, value: object) -> None:
        with pytest.raises(EnvelopeError):
            parse_started(_started(user_code=value))
        with pytest.raises(EnvelopeError):
            parse_started(_started(poll_secret=value))

    @pytest.mark.parametrize(
        "key", ["user_code", "poll_secret", "interval_s", "expires_in_s"]
    )
    def test_every_field_is_required(self, key: str) -> None:
        data = _started()
        del data[key]
        with pytest.raises(EnvelopeError):
            parse_started(data)

    def test_an_extra_field_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            parse_started(_started(extra=1))


class TestParseIssued:
    def test_a_valid_token(self) -> None:
        assert parse_issued({"token": _TOKEN}) == _TOKEN

    @pytest.mark.parametrize("token", ["", "fdr1_x", _TOKEN + "\n", None, 5])
    def test_a_malformed_token_is_refused(self, token: object) -> None:
        with pytest.raises(EnvelopeError):
            parse_issued({"token": token})

    @pytest.mark.parametrize("data", [{}, {"token": _TOKEN, "x": 1}, {"tok": _TOKEN}])
    def test_the_field_set_is_exactly_token(self, data: dict[str, object]) -> None:
        with pytest.raises(EnvelopeError):
            parse_issued(data)


class TestParseRetryAfter:
    def test_an_unstated_retry_is_none_never_zero(self) -> None:
        assert parse_retry_after({}) is None

    def test_a_stated_retry_is_returned(self) -> None:
        assert parse_retry_after({"retry_after_s": 37}) == 37

    def test_zero_is_a_stated_value_not_none(self) -> None:
        assert parse_retry_after({"retry_after_s": 0}) == 0

    @pytest.mark.parametrize("value", [-1, True, 1.5, "3", None])
    def test_a_malformed_value_is_refused(self, value: object) -> None:
        with pytest.raises(EnvelopeError):
            parse_retry_after({"retry_after_s": value})

    def test_other_fields_are_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            parse_retry_after({"retry_after_s": 3, "x": 1})
        with pytest.raises(EnvelopeError):
            parse_retry_after({"x": 1})


class TestParseEnvelopes:
    def test_the_served_list(self) -> None:
        assert parse_envelopes({"envelopes": [1]}) == (1,)
        assert parse_envelopes({"envelopes": [3, 1, 2]}) == (3, 1, 2)

    @pytest.mark.parametrize(
        "value", [[], [True], [0], [-1], [1.0], ["1"], 1, None, "1"]
    )
    def test_a_malformed_list_is_refused(self, value: object) -> None:
        with pytest.raises(EnvelopeError):
            parse_envelopes({"envelopes": value})

    def test_the_field_set_is_exactly_envelopes(self) -> None:
        for data in ({}, {"envelopes": [1], "x": 1}, {"envelope": [1]}):
            with pytest.raises(EnvelopeError):
                parse_envelopes(data)


def _capabilities(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "envelopes": [1],
        "registration": True,
        "targets": ["strava", "intervals"],
    }
    data.update(overrides)
    return data


class TestParseCapabilities:
    def test_valid_capabilities(self) -> None:
        assert parse_capabilities(_capabilities()) == CapabilitiesData(
            (1,), True, ("strava", "intervals")
        )

    def test_registration_false_and_no_targets(self) -> None:
        got = parse_capabilities(_capabilities(registration=False, targets=[]))
        assert got == CapabilitiesData((1,), False, ())

    @pytest.mark.parametrize("value", [1, 0, "true", None])
    def test_registration_must_be_a_bool(self, value: object) -> None:
        with pytest.raises(EnvelopeError):
            parse_capabilities(_capabilities(registration=value))

    @pytest.mark.parametrize(
        "targets",
        [["Strava"], ["1x"], [""], ["a" * 33], [5], "strava", None, ["ok", None]],
    )
    def test_targets_must_be_a_list_of_target_ids(self, targets: object) -> None:
        with pytest.raises(EnvelopeError):
            parse_capabilities(_capabilities(targets=targets))

    @pytest.mark.parametrize("envelopes", [[], [True], "1", None])
    def test_envelopes_are_parsed_as_in_parse_envelopes(
        self, envelopes: object
    ) -> None:
        with pytest.raises(EnvelopeError):
            parse_capabilities(_capabilities(envelopes=envelopes))

    @pytest.mark.parametrize("key", ["envelopes", "registration", "targets"])
    def test_every_field_is_required(self, key: str) -> None:
        data = _capabilities()
        del data[key]
        with pytest.raises(EnvelopeError):
            parse_capabilities(data)

    def test_an_extra_field_is_refused(self) -> None:
        with pytest.raises(EnvelopeError):
            parse_capabilities(_capabilities(extra=1))


# --------------------------------------------------------------------------- #
# The module's own imports
# --------------------------------------------------------------------------- #


def test_the_module_imports_the_standard_library_and_one_relative_vocabulary() -> None:
    path = Path(env.__file__)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    absolute: set[str] = set()
    relative: list[tuple[int, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            absolute.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                assert node.module is not None
                absolute.add(node.module.split(".")[0])
            else:
                relative.append((node.level, node.module))
    assert absolute, "the walk found no imports; it is looking at the wrong file"
    assert "http" not in absolute
    assert absolute <= {
        "__future__",
        "collections",
        "dataclasses",
        "json",
        "math",
        "re",
        "typing",
    }
    assert relative == [(1, "relay_codes")]


# --------------------------------------------------------------------------- #
# Fixed error messages, frozen values, encode-side robustness
# --------------------------------------------------------------------------- #

_CANARY = "CANARY-7f3a"


def _message_of(call: Callable[[], object]) -> str:
    with pytest.raises(EnvelopeError) as caught:
        call()
    return str(caught.value)


class TestFixedMessages:
    def test_every_decode_failure_carries_a_fixed_message_without_the_input(
        self,
    ) -> None:
        canary_token = f"fdr1_{_CANARY}"
        cases: list[Callable[[], object]] = [
            lambda: decode_answer(_answer(code=_CANARY)),
            lambda: decode_answer(_answer(envelope=_CANARY)),
            lambda: decode_answer(_answer(extra=_CANARY)),
            lambda: decode_answer(_answer(**{_CANARY: 1})),
            lambda: decode_answer(_answer(outcome="")),
            lambda: decode_answer(f'{{"{_CANARY}":1,"{_CANARY}":2}}'.encode()),
            lambda: decode_answer(
                f'{{"envelope":1,"code":"ok","data":{{"k":NaN,"{_CANARY}":1}}}}'.encode()
            ),
            lambda: decode_answer(_CANARY.encode()),
            lambda: decode_answer(b'{"k":"\xff' + _CANARY.encode() + b'"}'),
            lambda: decode_answer(b" " * 65_537),
            lambda: decode_request(
                f'{{"{_CANARY}":1}}'.encode(),
                required=frozenset({"email"}),
                allowed=frozenset({"email"}),
            ),
            lambda: decode_request(
                f'{{"email":1,"{_CANARY}":1}}'.encode(),
                required=frozenset({"email"}),
                allowed=frozenset({"email"}),
            ),
            lambda: decode_request(
                _CANARY.encode(), required=frozenset(), allowed=frozenset()
            ),
            lambda: parse_started(_started(user_code=_CANARY)),
            lambda: parse_started(_started(poll_secret=_CANARY)),
            lambda: parse_started(_started(interval_s=_CANARY)),
            lambda: parse_started(_started(**{_CANARY: 1})),
            lambda: parse_issued({"token": canary_token}),
            lambda: parse_issued({"token": _TOKEN, _CANARY: 1}),
            lambda: parse_capabilities(_capabilities(targets=[_CANARY])),
            lambda: parse_capabilities(_capabilities(**{_CANARY: 1})),
            lambda: parse_envelopes({"envelopes": [_CANARY]}),
            lambda: parse_envelopes({_CANARY: [1]}),
            lambda: parse_retry_after({"retry_after_s": _CANARY}),
            lambda: parse_retry_after({_CANARY: 1}),
        ]
        seen = set()
        for call in cases:
            message = _message_of(call)
            assert message in _FIXED_MESSAGES
            assert _CANARY not in message
            seen.add(message)
        assert len(seen) >= 4, "the cases reach too few distinct messages"

    def test_encode_failures_carry_a_fixed_message(self) -> None:
        for call in (
            lambda: encode_request({_CANARY: object()}),
            lambda: encode_request({"k": float("nan")}),
            lambda: encode_answer(Answer(RelayCode.RELAY_UNREACHABLE, {})),
            lambda: encode_request({"k": "x" * 65_537}),
        ):
            assert _message_of(call) in _FIXED_MESSAGES


class TestFrozenValues:
    @pytest.mark.parametrize(
        ("value", "field"),
        [
            (Answer(RelayCode.OK, {}), "outcome"),
            (CapabilitiesData((1,), True, ()), "registration"),
            (StartedData("BCDF-GHJK", "p" * 40, 7, 900), "interval_s"),
        ],
    )
    def test_assignment_raises(self, value: object, field: str) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, field, None)


class TestEncodeRobustness:
    def test_deep_nesting_in_answer_data_is_refused_not_crashed(self) -> None:
        nested: object = "leaf"
        for _ in range(5000):
            nested = [nested]
        with pytest.raises(EnvelopeError):
            encode_answer(Answer(RelayCode.OK, {"k": nested}))

    def test_deep_nesting_in_request_fields_is_refused_not_crashed(self) -> None:
        nested: object = "leaf"
        for _ in range(5000):
            nested = {"k": nested}
        with pytest.raises(EnvelopeError):
            encode_request({"k": nested})

    def test_non_string_keys_are_refused_at_any_depth(self) -> None:
        with pytest.raises(EnvelopeError):
            encode_answer(Answer(RelayCode.OK, {1: "a", "1": "b"}))  # type: ignore[dict-item]
        with pytest.raises(EnvelopeError):
            encode_answer(Answer(RelayCode.OK, {"k": {2: "a"}}))
        with pytest.raises(EnvelopeError):
            encode_request({"k": [{3: "a"}]})
        with pytest.raises(EnvelopeError):
            encode_request({"k": ({4: "a"},)})

    def test_string_keys_at_depth_are_still_accepted(self) -> None:
        assert encode_request({"k": [{"a": {"b": 1}}]}) == b'{"k":[{"a":{"b":1}}]}'
