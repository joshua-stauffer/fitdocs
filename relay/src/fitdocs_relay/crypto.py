"""Authenticated encryption of stored tokens under rotating keys (Keyring).

AES-256-GCM with a fresh 96-bit random nonce per seal. The caller's context is
the associated data, so a sealed value opens only for the principal, target and
field it was sealed for. This module is the only importer of `cryptography`.
"""

from __future__ import annotations

import base64
import binascii
import re
import secrets
from dataclasses import dataclass, field

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SEALED_VERSION = "v1"
KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
MAX_KEYS = 8

_KEY_ID = re.compile(r"[a-z0-9]{1,16}")
_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_NEW_ID_LENGTH = 8

KEYS_ERROR = (
    "The encryption keys must be 1 to 8 comma-separated id:key entries, each id "
    "1 to 16 lowercase letters or digits and distinct, each key 32 bytes in "
    "unpadded base64url."
)


@dataclass(frozen=True)
class EncryptionKey:
    key_id: str
    material: bytes = field(repr=False)


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(text: str) -> bytes | None:
    """Strict unpadded base64url, or None."""
    if not text.isascii() or "=" in text:
        return None
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        return None
    return raw if _encode(raw) == text else None


def _split(sealed: str) -> tuple[str, bytes] | None:
    parts = sealed.split(".")
    if len(parts) != 3 or parts[0] != SEALED_VERSION or not _KEY_ID.fullmatch(parts[1]):
        return None
    body = _decode(parts[2])
    if body is None or len(body) < NONCE_BYTES + TAG_BYTES:
        return None
    return parts[1], body


class Keyring:
    def __init__(self, keys: tuple[EncryptionKey, ...]) -> None:
        if not keys:
            raise ValueError("A keyring needs at least one key.")
        self._keys = {key.key_id: AESGCM(key.material) for key in reversed(keys)}
        self._current = keys[0]

    @property
    def current_id(self) -> str:
        return self._current.key_id

    def seal(self, plaintext: str, *, context: str) -> str:
        nonce = secrets.token_bytes(NONCE_BYTES)
        body = AESGCM(self._current.material).encrypt(
            nonce, plaintext.encode("utf-8"), context.encode("utf-8")
        )
        return f"{SEALED_VERSION}.{self._current.key_id}.{_encode(nonce + body)}"

    def open(self, sealed: str, *, context: str) -> str | None:
        split = _split(sealed)
        if split is None:
            return None
        cipher = self._keys.get(split[0])
        if cipher is None:
            return None
        body = split[1]
        try:
            plain = cipher.decrypt(
                body[:NONCE_BYTES], body[NONCE_BYTES:], context.encode("utf-8")
            )
            return plain.decode("utf-8")
        except (InvalidTag, UnicodeDecodeError):
            return None

    def key_id_of(self, sealed: str) -> str | None:
        split = _split(sealed)
        if split is None or split[0] not in self._keys:
            return None
        return split[0]


def parse_keys(value: str) -> tuple[EncryptionKey, ...]:
    """Parse `<id>:<key>[,<id>:<key>...]`; the error text never carries the value."""
    entries = value.split(",")
    if not 1 <= len(entries) <= MAX_KEYS:
        raise ValueError(KEYS_ERROR)
    keys: list[EncryptionKey] = []
    for entry in entries:
        key_id, separator, text = entry.partition(":")
        material = _decode(text) if separator else None
        if (
            not _KEY_ID.fullmatch(key_id)
            or material is None
            or len(material) != KEY_BYTES
            or any(key.key_id == key_id for key in keys)
        ):
            raise ValueError(KEYS_ERROR)
        keys.append(EncryptionKey(key_id, material))
    return tuple(keys)


def new_key() -> str:
    """A fresh `<id>:<key>` with an 8-character random id."""
    key_id = "".join(secrets.choice(_ID_ALPHABET) for _ in range(_NEW_ID_LENGTH))
    return f"{key_id}:{_encode(secrets.token_bytes(KEY_BYTES))}"
