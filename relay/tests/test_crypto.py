"""The keyring: authenticated encryption of tokens under rotating keys (Keyring)."""

from __future__ import annotations

import base64
import re

import pytest

from fitdocs_relay.crypto import EncryptionKey, Keyring, new_key, parse_keys

CONTEXT = "fitdocs-relay:v1:strava:principal-a:access"
OTHER_CONTEXT = "fitdocs-relay:v1:strava:principal-a:refresh"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


KEY_A = EncryptionKey("aaa", bytes(range(32)))
KEY_B = EncryptionKey("bbb", bytes(range(100, 132)))


def _entry(key_id: str, material: bytes) -> str:
    return f"{key_id}:{_b64(material)}"


def test_a_sealed_value_opens_to_the_plaintext() -> None:
    ring = Keyring((KEY_A,))
    sealed = ring.seal("access-token-value", context=CONTEXT)
    assert "access-token-value" not in sealed
    assert ring.open(sealed, context=CONTEXT) == "access-token-value"


def test_the_empty_and_non_ascii_plaintexts_round_trip() -> None:
    ring = Keyring((KEY_A,))
    for value in ("", "tokén-\U0001f3c3"):
        assert ring.open(ring.seal(value, context=CONTEXT), context=CONTEXT) == value


def test_two_seals_of_one_value_differ_and_both_open() -> None:
    ring = Keyring((KEY_A,))
    first = ring.seal("same", context=CONTEXT)
    second = ring.seal("same", context=CONTEXT)
    assert first != second
    assert ring.open(first, context=CONTEXT) == "same"
    assert ring.open(second, context=CONTEXT) == "same"


def test_the_sealed_form_is_version_key_id_and_nonce_ciphertext_tag() -> None:
    ring = Keyring((KEY_A,))
    sealed = ring.seal("abc", context=CONTEXT)
    version, key_id, body = sealed.split(".")
    assert (version, key_id) == ("v1", "aaa")
    assert "=" not in body
    # 96-bit nonce, 3 bytes of ciphertext, 128-bit tag.
    assert len(_unb64(body)) == 12 + 3 + 16


def test_a_wrong_context_gives_none() -> None:
    ring = Keyring((KEY_A,))
    sealed = ring.seal("secret", context=CONTEXT)
    assert ring.open(sealed, context=CONTEXT) == "secret"
    assert ring.open(sealed, context=OTHER_CONTEXT) is None
    assert ring.open(sealed, context="") is None


def test_a_tampered_tag_gives_none() -> None:
    ring = Keyring((KEY_A,))
    sealed = ring.seal("secret", context=CONTEXT)
    version, key_id, body = sealed.split(".")
    raw = bytearray(_unb64(body))
    raw[-1] ^= 0x01
    assert ring.open(f"{version}.{key_id}.{_b64(bytes(raw))}", context=CONTEXT) is None
    assert ring.open(sealed, context=CONTEXT) == "secret"


def test_a_tampered_ciphertext_or_nonce_gives_none() -> None:
    ring = Keyring((KEY_A,))
    sealed = ring.seal("secret", context=CONTEXT)
    version, key_id, body = sealed.split(".")
    for index in (0, 12):
        raw = bytearray(_unb64(body))
        raw[index] ^= 0x80
        forged = f"{version}.{key_id}.{_b64(bytes(raw))}"
        assert ring.open(forged, context=CONTEXT) is None


def test_an_unknown_key_id_gives_none() -> None:
    sealed = Keyring((KEY_A,)).seal("secret", context=CONTEXT)
    assert Keyring((KEY_A,)).open(sealed, context=CONTEXT) == "secret"
    assert Keyring((KEY_B,)).open(sealed, context=CONTEXT) is None


def test_the_same_id_with_different_material_gives_none() -> None:
    sealed = Keyring((KEY_A,)).seal("secret", context=CONTEXT)
    impostor = EncryptionKey("aaa", bytes(range(1, 33)))
    assert Keyring((impostor,)).open(sealed, context=CONTEXT) is None


@pytest.mark.parametrize(
    "malformed",
    [
        "",
        "garbage",
        "v1",
        "v1.aaa",
        "v1.aaa.",
        "v1.aaa.!!!!",
        "v1.aaa.AAAA",
        "v1.aaa.a.b",
        "v2.aaa.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        ".aaa.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    ],
)
def test_a_malformed_value_gives_none(malformed: str) -> None:
    ring = Keyring((KEY_A,))
    assert ring.open(malformed, context=CONTEXT) is None


def test_a_valid_sealed_value_with_the_version_changed_gives_none() -> None:
    ring = Keyring((KEY_A,))
    sealed = ring.seal("secret", context=CONTEXT)
    assert ring.open("v2" + sealed[2:], context=CONTEXT) is None


def test_a_non_ascii_sealed_value_gives_none() -> None:
    ring = Keyring((KEY_A,))
    assert ring.open("v1.aaa.éééé", context=CONTEXT) is None


def test_an_extra_segment_on_an_authentic_value_gives_none() -> None:
    ring = Keyring((KEY_A,))
    sealed = ring.seal("secret", context=CONTEXT)
    version, key_id, body = sealed.split(".")
    for malformed in (sealed + ".x", f"{version}.{key_id}.x.{body}"):
        assert ring.open(malformed, context=CONTEXT) is None
        assert ring.key_id_of(malformed) is None


def test_an_authentic_value_whose_plaintext_is_not_utf8_gives_none() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = bytes(range(12))
    body = AESGCM(KEY_A.material).encrypt(nonce, b"\xff\xfe", CONTEXT.encode("utf-8"))
    sealed = f"v1.{KEY_A.key_id}.{_b64(nonce + body)}"
    assert Keyring((KEY_A,)).open(sealed, context=CONTEXT) is None


def test_the_first_key_seals_and_any_key_opens() -> None:
    old = Keyring((KEY_A,)).seal("old", context=CONTEXT)
    ring = Keyring((KEY_B, KEY_A))
    assert ring.current_id == "bbb"
    fresh = ring.seal("fresh", context=CONTEXT)
    assert ring.key_id_of(fresh) == "bbb"
    assert ring.key_id_of(old) == "aaa"
    assert ring.open(old, context=CONTEXT) == "old"
    assert ring.open(fresh, context=CONTEXT) == "fresh"
    assert Keyring((KEY_A,)).open(fresh, context=CONTEXT) is None


def test_key_id_of_reports_none_for_a_value_it_cannot_attribute() -> None:
    ring = Keyring((KEY_A,))
    other = Keyring((KEY_B,)).seal("x", context=CONTEXT)
    assert ring.key_id_of(other) is None
    for bad in ("", "garbage", "v2.aaa.AAAA", "v1.aaa", "v1..AAAA"):
        assert ring.key_id_of(bad) is None


def test_a_keyring_needs_at_least_one_key() -> None:
    with pytest.raises(ValueError):
        Keyring(())


def test_the_key_material_is_not_in_the_repr() -> None:
    assert _b64(KEY_A.material) not in repr(KEY_A)
    assert str(KEY_A.material) not in repr(KEY_A)


# --- parse_keys ------------------------------------------------------------


def test_parse_keys_keeps_order_ids_and_material() -> None:
    value = f"{_entry('one', KEY_A.material)},{_entry('two2', KEY_B.material)}"
    keys = parse_keys(value)
    assert keys == (
        EncryptionKey("one", KEY_A.material),
        EncryptionKey("two2", KEY_B.material),
    )


def test_parse_keys_accepts_the_bounds() -> None:
    longest = "a1" * 8
    assert len(longest) == 16
    assert parse_keys(_entry(longest, KEY_A.material))[0].key_id == longest
    eight = ",".join(_entry(f"k{i}", bytes([i]) * 32) for i in range(8))
    assert len(parse_keys(eight)) == 8


FIXED_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9 ,.:;()'\-]+$")


@pytest.mark.parametrize(
    "value",
    [
        "",
        ",",
        "aaa",
        "aaa:",
        ":" + _b64(bytes(32)),
        "AAA:" + _b64(bytes(32)),
        "a-b:" + _b64(bytes(32)),
        ("a" * 17) + ":" + _b64(bytes(32)),
        "aaa:" + _b64(bytes(31)),
        "aaa:" + _b64(bytes(33)),
        "aaa:" + _b64(bytes(32)) + "=",
        "aaa:" + _b64(bytes(32)).replace("A", "+", 1),
        "aaa:!!!!",
        "aaa:" + _b64(bytes(32)) + ",",
        "aaa:" + _b64(bytes(32)) + ",aaa:" + _b64(bytes(range(32))),
        ",".join(f"k{i}:{_b64(bytes([i]) * 32)}" for i in range(9)),
        "aaa:" + _b64(bytes(32)) + ":extra",
        " aaa:" + _b64(bytes(32)),
    ],
)
def test_parse_keys_refuses_a_bad_value_with_fixed_text(value: str) -> None:
    with pytest.raises(ValueError) as caught:
        parse_keys(value)
    message = str(caught.value)
    assert message
    assert FIXED_TEXT_PATTERN.match(message)
    assert _b64(bytes(32)) not in message


def test_parse_keys_error_text_does_not_echo_the_key() -> None:
    secret = _b64(bytes(range(7, 39))) + "x"  # 33 bytes: refused for its length
    with pytest.raises(ValueError) as caught:
        parse_keys(f"aaa:{secret}")
    assert secret not in str(caught.value)
    assert secret[:8] not in str(caught.value)


# --- new_key ---------------------------------------------------------------


def test_new_key_parses_and_has_a_fresh_eight_character_id() -> None:
    first, second = new_key(), new_key()
    assert first != second
    for text in (first, second):
        key_id, _, material = text.partition(":")
        assert re.fullmatch(r"[a-z0-9]{8}", key_id)
        assert len(_unb64(material)) == 32
        (parsed,) = parse_keys(text)
        assert parsed.key_id == key_id
        ring = Keyring((parsed,))
        assert ring.open(ring.seal("v", context=CONTEXT), context=CONTEXT) == "v"
    assert first.partition(":")[2] != second.partition(":")[2]
