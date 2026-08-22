"""The only module that touches the ``garmin-fit-sdk`` decoder (Req 1.1-1.5, 2.3).

:func:`decode_fit` accepts a filesystem path or a raw byte buffer, validates it,
and returns a :class:`DecodeResult`: the raw decoded message dict, any
message-level decoder errors as strings, the content ``sha256`` of the exact
source bytes, and the source path when one was given.

Validation is loud and typed. Non-FIT input raises :class:`NotFitFileError`; a
FIT file that fails its integrity check raises :class:`FitIntegrityError` (both
before any message parsing). Message-level errors surfaced by ``Decoder.read``
are *collected*, never re-raised (Req 1.4), so a file that decodes overall while
reporting a bad message still returns a result carrying those errors.

Decode flags mirror the project reference: ``apply_scale_and_offset=True`` and
``expand_components=True`` so channel values arrive in real-world units, and
``convert_datetimes_to_dates=False`` so timestamps stay raw FIT-epoch integers
(downstream owns the conversion via :func:`fitdocs.model.fit_datetime`). The SDK
defaults are retained for every other flag. The source bytes are read exactly
once and never written back — decoding is side-effect-free (Req 1.5).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# garmin-fit-sdk ships no type stubs / py.typed marker; ignore the untyped
# import here — this is the sole module that touches the SDK decoder.
from garmin_fit_sdk import Decoder, Stream  # type: ignore[import-untyped]

from fitdocs.ingest.errors import FitIntegrityError, NotFitFileError


@dataclass(frozen=True)
class DecodeResult:
    """The outcome of a successful decode (validation failures raise instead).

    ``messages`` is the SDK's decoded message dict passed through untouched;
    ``errors`` holds message-level decoder errors as strings (empty on a clean
    decode); ``sha256`` is the content hash of the exact source bytes; and
    ``source_path`` is the string path when decoded from a file, else ``None``.
    """

    messages: dict[str, list[dict[str, object]]]
    errors: tuple[str, ...]
    sha256: str
    source_path: str | None


def decode_fit(source: str | Path | bytes) -> DecodeResult:
    """Decode and validate FIT ``source`` (a path or raw bytes) (Req 1.1-1.5, 2.3).

    Reads the bytes exactly once (from the path or the passed buffer), computes
    their ``sha256``, and decodes them. Raises :class:`NotFitFileError` when the
    input is not a FIT file (Req 1.2) or :class:`FitIntegrityError` when its
    integrity check fails (Req 1.3), in both cases before any message parsing.
    Otherwise returns a :class:`DecodeResult`; ``Decoder.read`` errors are
    stringified into ``errors`` and never re-raised (Req 1.4). The source file is
    never written or mutated (Req 1.5).
    """
    if isinstance(source, bytes):
        raw_bytes = source
        source_path: str | None = None
    else:
        path = Path(source)
        raw_bytes = path.read_bytes()
        source_path = str(source)

    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    # Decode from the exact bytes we hashed so provenance and content agree.
    stream = Stream.from_byte_array(raw_bytes)
    decoder = Decoder(stream)

    # ``is_fit`` and ``check_integrity`` each advance the stream, so the stream
    # must be reset before ``read`` (a reference-documented pitfall).
    if not decoder.is_fit():
        location = f" ({source_path})" if source_path is not None else ""
        raise NotFitFileError(
            f"Source is not a FIT file: header check failed{location}."
        )
    if not decoder.check_integrity():
        location = f" ({source_path})" if source_path is not None else ""
        raise FitIntegrityError(
            f"FIT file failed its integrity check (truncated or corrupt "
            f"bytes){location}."
        )

    stream.reset()
    messages, read_errors = decoder.read(
        apply_scale_and_offset=True,
        expand_components=True,
        convert_datetimes_to_dates=False,
    )

    # Surface message-level decoder errors as strings; never re-raise (Req 1.4).
    errors = tuple(str(error) for error in read_errors)

    return DecodeResult(
        messages=messages,
        errors=errors,
        sha256=sha256,
        source_path=source_path,
    )
