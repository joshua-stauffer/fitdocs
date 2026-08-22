"""Session summary, activity fallback, device, and developer-field extraction.

Requirements 4.1, 4.2, 4.5, and 14.1-14.4.

This module turns the decoded session/activity/device-info message lists into the
model's recorded-value contracts:

* :func:`extract_summary` reads the FIRST ``session`` message and maps every
  :class:`SessionSummary` field from its FIT key verbatim -- recorded values
  only, no derivation (Req 4.1). Every key is read with ``dict.get`` so an
  unrecorded field becomes ``None`` while a recorded ``0`` is preserved as a real
  zero (Req 12.3). When no session message exists it falls back to the first
  ``activity`` message for ``total_timer_time_s`` and leaves every other field
  ``None`` (Req 4.2). It ALWAYS returns a :class:`SessionSummary` (never ``None``).
* :func:`extract_devices` deduplicates ``device_info`` reports -- which repeat
  over an activity -- by ``(device_index, serial_number)``, keeping the LAST
  report per device, with absent fields ``None`` (Req 4.5).
* :func:`extract_developer_fields` maps session-scoped developer-defined fields
  to a read-only ``name -> value`` mapping, keyed by the described field names
  verbatim, empty when the file describes none (Req 14.1-14.4). The value is
  decoded per that field's own description -- a declared scale/offset is
  applied (Req 14.2, as amended); a field with neither declared is unchanged.
  It is a thin wrapper over :func:`extract_developer_fields_with_declared_scale`,
  kept for callers that only need the values (every existing test and caller
  before this amendment). A description declaring ``scale=0`` is unrepresentable
  (division by zero) and is OMITTED entirely rather than emitting a raw,
  wrong-by-a-constant-factor value -- the maintainer's ruling (2026-07-27, see
  the amendment record), applied directly: see that function's docstring for
  the reasoning.
* :func:`extract_developer_fields_with_declared_scale` additionally reports
  WHICH resolved field names had a scale and/or offset declared, so a
  downstream layer (workout-docs' ``render/sections.py``) can tell an
  already-decoded value apart from a raw one instead of guessing, which is the
  render-layer defect Amendment 2 exists to close (see that function's
  docstring and ``Activity.developer_fields_declared_scale``).

Channel policy parity: speed prefers the ``enhanced_*`` variant when it is a
usable scalar, else the basic variant, matching the record and lap extractors'
enhanced preference (Req 3.3); the shared :func:`fitdocs.ingest._fields.prefer_enhanced`
helper falls back to the basic scalar when a device decodes ``enhanced_*`` as a
component-expanded array.

Activity-fallback start_time: an ``activity`` message carries an END ``timestamp``
(the activity's finish), not a start, so it is NOT used as ``start_time`` --
doing so would fabricate a start the file never recorded (the hard no-fabrication
rule). ``start_time`` stays ``None`` in the fallback unless a genuinely-start
field is present, which standard activity messages do not carry.

Device index typing: with the decoder's ``convert_types_to_strings`` default, a
real ``device_info`` message decodes the reporting device's ``device_index`` as the
string enum ``'creator'`` (FIT value 0). It is normalized back to the true int
``0`` -- so :attr:`DeviceInfo.device_index` holds ``0``, not ``None`` -- for both
the model field and the dedup identity, keeping the stored value and dedup key in
step. Any OTHER non-integer recorded index (an exotic string enum the ``int``-typed
field cannot hold) still maps to ``None`` in the field while its raw value keys
deduplication, preserving that device's identity.

This module depends only on :mod:`fitdocs.model`; it never imports the SDK, the
metrics layer, or sibling ingest modules.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType

from fitdocs.ingest._fields import (
    float_or_none,
    int_or_none,
    prefer_enhanced,
    str_or_none,
)
from fitdocs.model import DeviceInfo, SessionSummary, fit_datetime

_EMPTY_DEVELOPER_FIELDS: Mapping[str, object] = MappingProxyType({})

# The FIT ``device_index`` enum name for value 0; the reporting device itself. The
# decoder stringifies it under ``convert_types_to_strings``, so it is normalized
# back to the true int ``0`` for both the model field and the dedup identity.
_CREATOR_DEVICE_INDEX = "creator"


def extract_summary(
    session_mesgs: list[dict[str, object]],
    activity_mesgs: list[dict[str, object]],
) -> SessionSummary:
    """Map the first session message to a :class:`SessionSummary` (Req 4.1, 4.2).

    When ``session_mesgs`` is non-empty its FIRST entry supplies every field,
    read verbatim by FIT key: absent keys become ``None`` and recorded zeros are
    preserved (Req 12.3). ``start_time`` is converted from raw FIT-epoch seconds
    with the shared :func:`fitdocs.model.fit_datetime` helper (Req 2.4). Speed
    prefers the ``enhanced_*`` variant when it is a usable scalar, else the basic
    variant (Req 3.3 parity).

    When ``session_mesgs`` is empty the summary falls back to the first
    ``activity`` message for ``total_timer_time_s`` only; every other field --
    including ``start_time`` -- stays ``None`` (Req 4.2). The function ALWAYS
    returns a :class:`SessionSummary`; it never returns ``None`` and never raises
    for missing data.
    """
    if not session_mesgs:
        return _fallback_summary(activity_mesgs)
    return _session_summary(session_mesgs[0])


def extract_devices(
    device_info_mesgs: list[dict[str, object]],
) -> tuple[DeviceInfo, ...]:
    """Deduplicate ``device_info`` reports into a :class:`DeviceInfo` tuple (Req 4.5).

    ``device_info`` messages repeat over an activity (battery status and other
    fields are re-reported periodically). Reports are deduplicated by their raw
    ``(device_index, serial_number)`` identity, keeping the LAST report's values
    for each device and preserving first-appearance order. Absent fields are
    ``None``. An empty input yields an empty tuple (never ``None``).
    """
    deduped: dict[tuple[object, object], DeviceInfo] = {}
    for device in device_info_mesgs:
        key = (
            _device_index_key(device.get("device_index")),
            device.get("serial_number"),
        )
        deduped[key] = _build_device(device)
    return tuple(deduped.values())


def extract_developer_fields(
    field_description_mesgs: list[dict[str, object]],
    session_mesgs: list[dict[str, object]],
) -> Mapping[str, object]:
    """Map described developer fields recorded on the session (Req 14.1-14.4).

    A thin wrapper over :func:`extract_developer_fields_with_declared_scale`
    that returns only the value mapping, for the callers (every one before
    Amendment 2) that do not need to distinguish a declared-scale value from a
    raw one. See that function for the full contract.
    """
    values, _declared = extract_developer_fields_with_declared_scale(
        field_description_mesgs, session_mesgs
    )
    return values


def extract_developer_fields_with_declared_scale(
    field_description_mesgs: list[dict[str, object]],
    session_mesgs: list[dict[str, object]],
) -> tuple[Mapping[str, object], frozenset[str]]:
    """Map described developer fields recorded on the session (Req 14.1-14.4).

    Returns a pair: a READ-ONLY mapping from each described developer-field
    name to the value the session recorded for it, DECODED per that field's
    own description (Req 14.2, as amended -- see below); and a ``frozenset`` of
    the names IN that mapping whose description declared a ``scale`` and/or
    ``offset`` -- so a caller can tell an already-decoded value apart from a
    raw one instead of guessing (this is what lets ``render/sections.py`` stop
    hardcoding a hundredths-guess factor on a value ingest may have already
    scaled; see ``Activity.developer_fields_declared_scale``). The described
    name is taken verbatim from each ``field_description`` message's
    ``field_name`` (no renaming).

    SDK exposure convention (verified by round-trip in the tests): the decoder
    stamps each decoded ``field_description`` message with an integer ``key`` equal
    to its position in ``field_description_mesgs``, and exposes the values recorded
    on a message under ``message['developer_fields']`` as a dict keyed by that
    SAME ``key`` (NOT the ``field_definition_number``). This function therefore
    pairs a description's ``field_name`` with the FIRST session message's
    ``developer_fields[key]``.

    Decoding, not interpretation (Req 14.2): a description may declare a
    ``scale`` and/or ``offset`` for its field -- ``garmin-fit-sdk`` parses both
    but never applies them to a developer field (only to native profile
    fields), so this function applies them itself, per :func:`_developer_value`.
    Applying a scale/offset the file ITSELF declares is decoding the value the
    file recorded, not an fitdocs-supplied interpretation of it; inferring an
    UNDECLARED convention (for example, guessing that an integer field is
    "really" hundredths because no writer would store a value that granular)
    remains forbidden -- that is interpretation, and stays out of this
    function. A description with neither ``scale`` nor ``offset`` declared
    (the shape of every field in the current corpus) is passed through
    unchanged: an array (list) value becomes a ``tuple`` -- a 16-entry
    identifier stays a 16-entry tuple -- while a scalar is returned unchanged;
    nothing is renamed. A described field the session did not record is
    OMITTED, never fabricated (Req 14.4).

    A declared ``scale`` of ``0`` cannot be divided by and is UNREPRESENTABLE:
    rather than emit a raw, wrong-by-a-constant-factor value with no signal
    (the exact defect this amendment exists to close) or silently substitute a
    default, the field is OMITTED from the result entirely -- the same
    never-fabricate treatment Req 14.4 already gives an unrecorded field. This
    is the maintainer's RULING (2026-07-27, recorded in Amendment 2's
    revision), reached exactly on the reviewer's reasoning: the raw-value
    fallback would reinstate the wrong-by-a-constant-factor, no-signal shape
    the queue item that started this amendment condemned, and it conflicts
    with CLAUDE.md's absent-data-is-``None`` rule and Req 14.4's own
    never-fabricate posture. Pinned by a test.

    When there are no descriptions, no session message, or the session records
    none of the described fields, the mapping is EMPTY -- never ``None`` and
    never an error (Req 14.3); the declared-scale set is empty in that case too.
    """
    if not session_mesgs:
        return _EMPTY_DEVELOPER_FIELDS, frozenset()
    recorded = session_mesgs[0].get("developer_fields")
    if not isinstance(recorded, Mapping) or not recorded:
        return _EMPTY_DEVELOPER_FIELDS, frozenset()

    resolved: dict[str, object] = {}
    declared_scale: set[str] = set()
    for description in field_description_mesgs:
        name = description.get("field_name")
        if not isinstance(name, str):
            continue  # a description without a usable name cannot be keyed
        key = description.get("key")
        if key not in recorded:
            continue  # described but not recorded on the session (Req 14.4)
        scale = description.get("scale")
        offset = description.get("offset")
        if scale == 0:
            continue  # unrepresentable declared scale: omit, never fabricate
        resolved[name] = _developer_value(recorded[key], scale, offset)
        if scale is not None or offset is not None:
            declared_scale.add(name)

    if not resolved:
        return _EMPTY_DEVELOPER_FIELDS, frozenset()
    return MappingProxyType(resolved), frozenset(declared_scale)


def _developer_value(value: object, scale: object, offset: object) -> object:
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
      (:func:`extract_developer_fields_with_declared_scale`) OMITS such a
      field before calling here, so ``scale`` is always either ``None`` or
      nonzero by this point (see that function's docstring for why omission
      rather than a raw-value fallback).
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


def _session_summary(session: dict[str, object]) -> SessionSummary:
    """Build a :class:`SessionSummary` from one recorded session message (Req 4.1)."""
    return SessionSummary(
        sport=str_or_none(session.get("sport")),
        sub_sport=str_or_none(session.get("sub_sport")),
        start_time=_fit_datetime_or_none(session.get("start_time")),
        total_elapsed_time_s=float_or_none(session.get("total_elapsed_time")),
        total_timer_time_s=float_or_none(session.get("total_timer_time")),
        total_distance_m=float_or_none(session.get("total_distance")),
        total_calories_kcal=int_or_none(session.get("total_calories")),
        total_ascent_m=float_or_none(session.get("total_ascent")),
        total_descent_m=float_or_none(session.get("total_descent")),
        avg_heart_rate_bpm=int_or_none(session.get("avg_heart_rate")),
        max_heart_rate_bpm=int_or_none(session.get("max_heart_rate")),
        avg_power_w=int_or_none(session.get("avg_power")),
        max_power_w=int_or_none(session.get("max_power")),
        avg_cadence_rpm=float_or_none(session.get("avg_cadence")),
        max_cadence_rpm=float_or_none(session.get("max_cadence")),
        avg_speed_mps=float_or_none(
            prefer_enhanced(session, "enhanced_avg_speed", "avg_speed")
        ),
        max_speed_mps=float_or_none(
            prefer_enhanced(session, "enhanced_max_speed", "max_speed")
        ),
    )


def _fallback_summary(activity_mesgs: list[dict[str, object]]) -> SessionSummary:
    """Session-less summary: activity ``total_timer_time`` only, else all None (4.2)."""
    activity = activity_mesgs[0] if activity_mesgs else None
    total_timer_time_s = (
        float_or_none(activity.get("total_timer_time"))
        if activity is not None
        else None
    )
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=total_timer_time_s,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )


def _build_device(device: dict[str, object]) -> DeviceInfo:
    """Map one ``device_info`` message to a :class:`DeviceInfo` (Req 4.5)."""
    return DeviceInfo(
        device_index=_int_index_or_none(device.get("device_index")),
        manufacturer=str_or_none(device.get("manufacturer")),
        product_name=_product_name(device),
        serial_number=int_or_none(device.get("serial_number")),
        software_version=float_or_none(device.get("software_version")),
        battery_status=str_or_none(device.get("battery_status")),
    )


def _product_name(device: dict[str, object]) -> str | None:
    """Resolve a device product name, or ``None`` when only a numeric code exists.

    ``product_name`` wins when recorded as a string; otherwise a string
    ``product`` field is used. A numeric ``product`` code is not a name and is
    never turned into one -- the field stays ``None`` (no fabrication, Req 4.5).
    """
    name = device.get("product_name")
    if isinstance(name, str):
        return name
    product = device.get("product")
    if isinstance(product, str):
        return product
    return None


def _fit_datetime_or_none(value: object) -> datetime | None:
    """Convert a raw FIT-epoch timestamp to a UTC datetime, or ``None`` (Req 2.4)."""
    if value is None:
        return None
    if isinstance(value, int):
        return fit_datetime(value)
    raise TypeError(f"expected an integer FIT timestamp, got {type(value).__name__}")


def _device_index_key(value: object) -> object:
    """The dedup identity for a recorded ``device_index``.

    The FIT ``'creator'`` enum (value 0) is normalized to the true int ``0`` so a
    device that reports its index as the ``'creator'`` string dedups against -- and
    matches -- the int ``0`` stored on the model field. Any OTHER recorded index is
    kept raw, preserving each distinct device's identity.
    """
    return 0 if value == _CREATOR_DEVICE_INDEX else value


def _int_index_or_none(value: object) -> int | None:
    """A device index as ``int``, else ``None`` (Req 4.5).

    The ``'creator'`` string enum decodes to FIT ``device_index`` 0, so it is
    normalized to the true int ``0``. Any other non-integer recorded index (an
    exotic string enum the ``int``-typed model field cannot hold) maps to ``None``;
    deduplication keys off the same normalized identity, so device identity is
    preserved regardless.
    """
    normalized = _device_index_key(value)
    return normalized if isinstance(normalized, int) else None
