"""Tests for the FIT decode wrapper and its error taxonomy (Req 1.1-1.5, 2.3).

These exercise :func:`fitdocs.ingest.decode.decode_fit` against the crafted byte
fixtures from :mod:`tests.fixtures.builder`:

* random / non-FIT bytes raise the descriptive :class:`NotFitFileError`;
* a truncated file raises the *distinguishable* :class:`FitIntegrityError`;
* a valid file returns every message list plus a content ``sha256``;
* a file with a message-level decoder error returns normally with those errors
  collected as strings (never re-raised);
* the source content hash matches :func:`hashlib.sha256` and is deterministic;
* path decoding never mutates the source file, and byte decoding reports no path.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from fitdocs.ingest.decode import DecodeResult, decode_fit
from fitdocs.ingest.errors import (
    FitDecodeError,
    FitIntegrityError,
    NotFitFileError,
)

_SHA256_HEX = re.compile(r"\A[0-9a-f]{64}\Z")


def test_non_fit_bytes_raise_not_fit_error(non_fit_bytes: bytes) -> None:
    """Random / non-FIT input raises the descriptive non-FIT error (Req 1.2)."""
    with pytest.raises(NotFitFileError) as exc_info:
        decode_fit(non_fit_bytes)
    # The non-FIT error is part of the shared decode-error taxonomy.
    assert isinstance(exc_info.value, FitDecodeError)
    assert str(exc_info.value)  # descriptive, non-empty message


def test_truncated_bytes_raise_integrity_error(truncated_fit_bytes: bytes) -> None:
    """A truncated valid file raises the integrity error (Req 1.3)."""
    with pytest.raises(FitIntegrityError) as exc_info:
        decode_fit(truncated_fit_bytes)
    err = exc_info.value
    assert isinstance(err, FitDecodeError)
    # Integrity failure is distinguishable from the non-FIT failure (Req 1.3).
    assert not isinstance(err, NotFitFileError)
    assert str(err)


def test_valid_bytes_return_messages_and_hash(run_fit_bytes: bytes) -> None:
    """A valid file returns all message lists plus a content hash (Req 1.1, 2.3)."""
    result = decode_fit(run_fit_bytes)
    assert isinstance(result, DecodeResult)
    # Every expected message list survives the passthrough untouched.
    assert "record_mesgs" in result.messages
    assert "session_mesgs" in result.messages
    assert "lap_mesgs" in result.messages
    assert result.messages["record_mesgs"]  # non-empty list of records
    # A clean decode carries no message-level errors.
    assert result.errors == ()
    # sha256 is a lowercase 64-hex-char digest.
    assert _SHA256_HEX.fullmatch(result.sha256) is not None


def test_bad_message_collects_errors_without_raising(
    bad_message_fit_bytes: bytes,
) -> None:
    """Message-level decode errors are collected as strings, not raised (Req 1.4)."""
    result = decode_fit(bad_message_fit_bytes)
    assert isinstance(result, DecodeResult)
    # Read errors are surfaced, never swallowed and never re-raised.
    assert result.errors  # non-empty
    assert all(isinstance(item, str) for item in result.errors)
    assert all(item for item in result.errors)  # each is a descriptive string
    # The already-decoded messages still come through.
    assert "record_mesgs" in result.messages


def test_sha256_matches_hashlib_and_is_deterministic(run_fit_bytes: bytes) -> None:
    """The content hash equals hashlib's digest and is stable (Req 2.3, 13.2)."""
    expected = hashlib.sha256(run_fit_bytes).hexdigest()
    first = decode_fit(run_fit_bytes)
    second = decode_fit(run_fit_bytes)
    assert first.sha256 == expected
    assert first.sha256 == second.sha256


def test_path_input_records_path_and_leaves_file_unchanged(
    run_fit_bytes: bytes, tmp_path: Path
) -> None:
    """Decoding by path records the path and never mutates the source (Req 1.5)."""
    fit_path = tmp_path / "activity.fit"
    fit_path.write_bytes(run_fit_bytes)
    hash_before = hashlib.sha256(fit_path.read_bytes()).hexdigest()
    mtime_before = fit_path.stat().st_mtime_ns

    result = decode_fit(fit_path)

    assert result.source_path == str(fit_path)
    # Same content hash as the in-memory decode of identical bytes (Req 2.3).
    assert result.sha256 == hashlib.sha256(run_fit_bytes).hexdigest()
    # The file is byte-for-byte and metadata unchanged (never written) (Req 1.5).
    assert hashlib.sha256(fit_path.read_bytes()).hexdigest() == hash_before
    assert fit_path.stat().st_mtime_ns == mtime_before


def test_str_path_input_records_path(run_fit_bytes: bytes, tmp_path: Path) -> None:
    """A ``str`` path is accepted and echoed back verbatim as ``source_path``."""
    fit_path = tmp_path / "activity.fit"
    fit_path.write_bytes(run_fit_bytes)

    result = decode_fit(str(fit_path))

    assert result.source_path == str(fit_path)


def test_bytes_input_has_no_source_path(run_fit_bytes: bytes) -> None:
    """Byte-buffer input reports ``source_path`` as ``None`` (Req 1.5)."""
    result = decode_fit(run_fit_bytes)
    assert result.source_path is None
