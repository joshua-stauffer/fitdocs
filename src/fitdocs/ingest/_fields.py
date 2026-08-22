"""Shared defensive field-coercion helpers for the ingest extractors.

The decoded FIT message dicts hold plain Python scalars whose types depend on the
device and the decoder's ``convert_types_to_strings`` default. These helpers narrow
one decoded value onto a model field's type, applying the project's honest-absence
rule: a missing key (``None``) becomes ``None`` and a recorded ``0`` is preserved
as a real zero, never dropped (Req 12.3).

:func:`str_or_none` is *defensive by design*. Under ``convert_types_to_strings`` an
UNKNOWN enum -- an exotic ``sport``/``sub_sport``/``manufacturer``/``battery_status``/
``set_type`` the SDK profile cannot name -- stays a raw ``int`` rather than a
string. Coercing it with ``str(value)`` yields a FAITHFUL raw representation and
lets whole-file parsing proceed: it is neither a crash nor a fabricated default,
and downstream detection already maps an unknown sport string to the never-failing
``Workout`` label (:class:`SessionSummary.sport` is documented as the raw FIT
string). The numeric helpers, by contrast, stay strict: a present-but-non-numeric
value is a genuine contract violation and raises.

These helpers depend only on the standard library; they never import the SDK, the
model, or sibling ingest modules.
"""

from __future__ import annotations

from collections.abc import Mapping


def prefer_enhanced(
    mesg: Mapping[str, object], enhanced_key: str, basic_key: str
) -> object:
    """Prefer the ``enhanced_*`` variant when it is a usable scalar, else the basic.

    The reference decode flags (``expand_components=True``) can expand an
    ``enhanced_*`` speed/altitude field into a REDUNDANT array -- a real lap's
    ``enhanced_avg_speed`` decodes as e.g. ``[3.17, 3.17]`` while the plain
    ``avg_speed`` carries the same value as a clean scalar. A non-scalar enhanced
    value is therefore not usable on its own, so this falls back to the basic
    variant, which holds the faithful scalar; nothing is collapsed, averaged, or
    fabricated. When the enhanced value is a genuine scalar it wins (Req 3.3
    parity); when it is absent (or a non-scalar) the basic variant is returned,
    which may itself be ``None`` for an honestly-absent field.
    """
    enhanced = mesg.get(enhanced_key)
    if isinstance(enhanced, int | float):
        return enhanced
    return mesg.get(basic_key)


def str_or_none(value: object) -> str | None:
    """A string field value, or ``None`` when absent -- never a crash.

    ``None`` maps to ``None`` and a ``str`` passes through unchanged. Any OTHER
    present value (typically an unknown enum decoded as a raw ``int``) is coerced
    with ``str(value)``: a faithful raw representation, not a fabricated default,
    so a single exotic enum never aborts a whole-file parse.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def int_or_none(value: object) -> int | None:
    """An integer field value, unchanged, or ``None`` when absent (Req 12.3).

    A recorded ``0`` is preserved as a real zero. A present-but-non-integer value
    is a contract violation and raises :class:`TypeError`.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise TypeError(f"expected an integer field value, got {type(value).__name__}")


def float_or_none(value: object) -> float | None:
    """A real-valued field, unchanged, or ``None`` when absent (Req 12.3).

    Integers are accepted and returned verbatim (some FIT fields -- cadence,
    ascent -- decode as ``int`` yet are modelled as ``float``); a recorded ``0``
    is preserved as a real zero. A present-but-non-numeric value raises
    :class:`TypeError`.
    """
    if value is None:
        return None
    if isinstance(value, int | float):
        return value
    raise TypeError(f"expected a numeric field value, got {type(value).__name__}")
