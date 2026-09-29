"""Developer-field decoding shared by the session and record readers.

Requirements 1.2, 1.4-1.7, 1.10, 1.12 and 2.1.

A FIT file describes each developer field in a ``field_description`` message
and records its values against that description. This module is the ONE place
that turns a recorded developer value into the value fitdocs exposes:

* :func:`parse_field_descriptions` reads the decoded ``field_description``
  messages into :class:`FieldDescription` records, keeping file order. A
  description's ``key`` is the integer the SDK stamps on it (its position in
  the message list) and is what recorded values are paired by, never the
  ``field_definition_number``. The ``native_mesg_num`` and ``native_field_num``
  a description may carry are never read: a developer field never fills or
  overrides a native channel (Req 1.10).
* :func:`decode_developer_value` decodes one recorded value, in order: the
  invalid-value sentinel of the declared base type (or a non-finite float) is
  "not recorded" (``None``); a float32 becomes the shortest decimal that packs
  to the same 32-bit pattern; a declared scale/offset is then applied by
  :func:`apply_declared_scale`. Nothing undeclared is inferred (Req 1.12).
* :func:`application_ids` maps a developer data index to the lowercase hex of
  its 16-byte application id.

This module depends only on the standard library.
"""

from __future__ import annotations

import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_BASE_TYPE_MASK = 0x1F
_FLOAT32 = 0x08
_FLOAT64 = 0x09

# The FIT protocol's invalid value for each integer base type (enum, sint/uint
# 8/16/32/64, the ``z`` forms and byte). String, float32 and float64 are not in
# the table: a string has no sentinel here and a float's is "non-finite".
INVALID_VALUES: Mapping[int, int] = {
    0x00: 0xFF,  # enum
    0x01: 0x7F,  # sint8
    0x02: 0xFF,  # uint8
    0x03: 0x7FFF,  # sint16
    0x04: 0xFFFF,  # uint16
    0x05: 0x7FFFFFFF,  # sint32
    0x06: 0xFFFFFFFF,  # uint32
    0x0A: 0x00,  # uint8z
    0x0B: 0x0000,  # uint16z
    0x0C: 0x00000000,  # uint32z
    0x0D: 0xFF,  # byte
    0x0E: 0x7FFFFFFFFFFFFFFF,  # sint64
    0x0F: 0xFFFFFFFFFFFFFFFF,  # uint64
    0x10: 0x0000000000000000,  # uint64z
}


@dataclass(frozen=True)
class FieldDescription:
    """One decoded ``field_description`` message."""

    key: int  # position in field_description_mesgs (SDK key)
    name: str
    developer_data_index: int | None
    field_definition_number: int | None
    base_type: int | None  # fit_base_type_id & 0x1F; None when absent
    units: str | None
    scale: int | float | None
    offset: int | float | None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number_or_none(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def parse_field_descriptions(
    field_description_mesgs: Sequence[Mapping[str, object]],
) -> tuple[FieldDescription, ...]:
    """Read the decoded ``field_description`` messages, in file order.

    A description whose ``field_name`` is not a ``str``, or whose ``key`` is not
    an ``int``, cannot be named or paired and is skipped.
    """
    parsed: list[FieldDescription] = []
    for message in field_description_mesgs:
        name = message.get("field_name")
        key = _int_or_none(message.get("key"))
        if not isinstance(name, str) or key is None:
            continue
        type_id = _int_or_none(message.get("fit_base_type_id"))
        units = message.get("units")
        parsed.append(
            FieldDescription(
                key=key,
                name=name,
                developer_data_index=_int_or_none(message.get("developer_data_index")),
                field_definition_number=_int_or_none(
                    message.get("field_definition_number")
                ),
                base_type=None if type_id is None else type_id & _BASE_TYPE_MASK,
                units=units if isinstance(units, str) else None,
                scale=_number_or_none(message.get("scale")),
                offset=_number_or_none(message.get("offset")),
            )
        )
    return tuple(parsed)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _shortest_float32(value: float) -> float:
    """The shortest decimal that packs to the same 32-bit pattern as ``value``."""
    target = struct.pack("<f", value)
    for precision in range(1, 10):
        candidate = float(f"{value:.{precision}g}")
        if struct.pack("<f", candidate) == target:
            return candidate
    return value


def _drop_sentinel(value: object, base_type: int | None) -> object:
    """Step 1: the invalid value of the declared base type is not recorded."""
    invalid = INVALID_VALUES.get(base_type) if base_type is not None else None
    if invalid is not None:
        if isinstance(value, list):
            # Only an array of nothing but sentinels is "not recorded"; any other
            # array is kept element for element, sentinel elements included.
            if value and all(_is_number(item) and item == invalid for item in value):
                return None
            return value
        if _is_number(value) and value == invalid:
            return None
        return value
    if base_type in (_FLOAT32, _FLOAT64):
        if isinstance(value, list):
            cleaned = [
                None
                if isinstance(item, (int, float))
                and not isinstance(item, bool)
                and not math.isfinite(item)
                else item
                for item in value
            ]
            if cleaned and all(item is None for item in cleaned):
                return None
            return cleaned
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and not math.isfinite(value)
        ):
            return None
    return value


def _round_float32(value: object) -> object:
    """Step 2: express each finite float32 as its shortest decimal."""
    if isinstance(value, list):
        return [_round_float32(item) for item in value]
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if is_number and math.isfinite(value):  # type: ignore[arg-type]
        return _shortest_float32(float(value))  # type: ignore[arg-type]
    return value


def decode_developer_value(value: object, description: FieldDescription) -> object:
    """Decode one recorded developer value the way its description declares.

    In order: the sentinel of the declared base type (``None`` for not
    recorded), the float32 shortest decimal, then the declared scale/offset
    (:func:`apply_declared_scale`; a list becomes a tuple). A string, an unknown
    base type and an absent one get no sentinel check.
    """
    value = _drop_sentinel(value, description.base_type)
    if value is None:
        return None
    if description.base_type == _FLOAT32:
        value = _round_float32(value)
    return apply_declared_scale(value, description.scale, description.offset)


def application_ids(
    developer_data_id_mesgs: Sequence[Mapping[str, object]],
) -> Mapping[int, str]:
    """Map a ``developer_data_index`` to the lowercase hex of its application id.

    Only an ``application_id`` that is a 16-entry list of ints in ``0..255``
    qualifies; anything else leaves the index out.
    """
    ids: dict[int, str] = {}
    for message in developer_data_id_mesgs:
        index = _int_or_none(message.get("developer_data_index"))
        raw = message.get("application_id")
        if index is None or not isinstance(raw, list) or len(raw) != 16:
            continue
        if not all(_int_or_none(b) is not None and 0 <= b <= 255 for b in raw):
            continue
        ids[index] = bytes(raw).hex()
    return ids


def apply_declared_scale(value: object, scale: object, offset: object) -> object:
    """Decode a developer-field value, applying a declared scale/offset (Req 14.2).

    Req 14.2 (as amended) draws the decoding/interpretation line: a scale or
    offset the file's OWN ``field_description`` declares is part of the
    encoding, so applying it is decoding, not interpretation, and is done here.
    ``garmin-fit-sdk`` parses both into its field profile but never applies
    them to a developer field -- only to native profile fields
    (``decoder.py``'s ``__apply_scale_and_offset``, called only from
    ``__apply_profile``) -- so this function closes that gap using the SAME
    FIT-protocol formula the SDK applies to native fields, confirmed by
    reading that method: ``value / scale - offset``.

    * A declared ``scale`` divides the value; a declared ``offset`` is then
      subtracted. Either left undeclared defaults to the FIT-protocol
      identity for that term -- an undeclared ``scale`` behaves as 1, an
      undeclared ``offset`` as 0 -- so a description declaring NEITHER (the
      shape of every field in the current corpus, and the only shape before
      this change) reduces to a no-op: division by an effective scale of 1
      is skipped entirely, and subtracting an effective offset of 0 leaves an
      ``int`` an ``int`` -- so the value is unchanged and byte-identical to
      the pre-existing pass-through behavior. ``offset`` declared alone (an
      unusual but legal description) still applies, against that implicit
      scale of 1. An array value is scaled ELEMENT-WISE, matching the SDK's
      own per-element treatment of a native array field, and still becomes a
      ``tuple``.
    * A declared ``scale`` of ``0`` never reaches this function: the caller
      (the session reader,
      :func:`fitdocs.ingest.summary.extract_developer_fields_with_declared_scale`)
      OMITS such a field before calling here, so
      ``scale`` is always either ``None`` or nonzero by this point (see the
      session reader's docstring for why omission rather than a raw-value
      fallback).
    * A non-numeric raw value under a declared scale (for example a
      ``string``-typed developer field, or a ``None`` array element) passes
      through un-scaled rather than raising or defaulting -- the malformed
      part is the declaration, not the value, and the value is real data
      worth keeping (see :func:`_scale_one`).
    * A ``bool`` raw value (an unusual but possible developer-field type) is
      preserved as a ``bool``, not silently widened to ``int``, when there is
      nothing to actually apply -- see :func:`_scale_one`.
    """
    if isinstance(value, list):
        return tuple(_scale_one(item, scale, offset) for item in value)
    return _scale_one(value, scale, offset)


def _scale_one(value: object, scale: object, offset: object) -> object:
    """Apply one declared scale/offset to a single value (Req 14.2, see caller).

    A non-numeric ``value`` (including ``None``, an absent array element) is
    returned unchanged: it fails the ``isinstance`` check below before any
    arithmetic is attempted, so it can never raise here. ``scale`` is never
    ``0`` here -- the caller omits that field before this is reached.

    When there is nothing to actually apply -- an undeclared (or explicitly
    identity: ``scale=1``, ``offset=0``) scale/offset pair -- ``value`` is
    returned UNCHANGED rather than computed as ``value / 1 - 0``, so its exact
    type is preserved. This matters for ``bool``: ``bool`` is an ``int``
    subclass, so ``True - 0`` would silently return the ``int`` ``1``,
    defeating ``sections.py``'s own ``isinstance(value, bool)`` guard. No real
    developer field is boolean-typed today, but preserving identity here keeps
    this function byte-identical to the pre-existing pass-through for every
    type, not just the numeric ones the current corpus exercises.
    """
    if not isinstance(value, (int, float)):
        return value  # non-numeric under a declared scale: cannot decode, pass through
    divisor = scale if isinstance(scale, (int, float)) else 1
    subtrahend = offset if isinstance(offset, (int, float)) else 0
    if divisor == 1 and subtrahend == 0:
        return value  # nothing declared (or declared as identity): preserve type
    scaled = value if divisor == 1 else value / divisor
    return scaled - subtrahend
