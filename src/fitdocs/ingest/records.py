"""Per-sample channel extraction: ``record_mesgs`` -> :class:`Samples` (Req 3.1-3.6).

:func:`extract_samples` maps the decoded FIT record stream onto the model's
parallel channel arrays. Every array is the same length and index-aligned: index
``i`` describes the same sample across all ten channels, and a channel the device
did not record at ``i`` holds ``None`` there (Req 3.1, 3.2).

Channel policy:

- **Enhanced preference** (Req 3.3): speed and altitude prefer the
  ``enhanced_speed``/``enhanced_altitude`` variant when it is a usable scalar for
  that sample, falling back to the basic ``speed``/``altitude`` otherwise (via the
  shared :func:`fitdocs.ingest._fields.prefer_enhanced` helper, which also guards
  against a component-expanded array value). The choice is made per-sample.
- **Semicircles -> degrees** (Req 3.4): ``position_lat``/``position_long`` are
  raw semicircles and are converted with ``deg = semicircles * (180 / 2**31)``;
  an absent position stays ``None``.
- **Units** (Req 3.5): the decoder already applied scale/offset
  (``apply_scale_and_offset=True``), so decoded speed (m/s), distance (m),
  altitude (m), and temperature (deg C) are read through in their model units
  unchanged. Only position needs conversion.
- **Raw values** (Req 3.6): sample values are stored verbatim -- no smoothing,
  resampling, or reordering. Smoothing is a downstream metric/renderer concern.

Timeline: a record's raw ``timestamp`` (FIT-epoch seconds) is converted with the
shared :func:`fitdocs.model.fit_datetime` helper. ``time_s`` is the offset in
seconds from an anchor -- ``start_time`` when the caller supplies it, otherwise
the first retained record's timestamp, so offsets are well-defined even when this
function is called in isolation. The absolute record timestamps are returned
alongside the samples for later lap projection.

Records without a ``timestamp`` are dropped -- they cannot be placed on the
timeline -- and that is the only record-level exclusion. An empty record list (or
one where no record has a timestamp) yields an empty :class:`Samples` with empty
channel arrays and an empty timestamps tuple.

This module depends on :mod:`fitdocs.model` and the shared enhanced-preference
helper in :mod:`fitdocs.ingest._fields`; it never imports the SDK or the metrics
layer.
"""

from __future__ import annotations

from datetime import datetime

from fitdocs.ingest._fields import prefer_enhanced
from fitdocs.model import Samples, fit_datetime

# semicircles -> decimal degrees: deg = semicircles * (180 / 2**31) (Req 3.4).
_SEMICIRCLE_TO_DEGREE = 180 / 2**31

_EMPTY_SAMPLES = Samples(
    time_s=(),
    heart_rate_bpm=(),
    power_w=(),
    cadence_rpm=(),
    speed_mps=(),
    distance_m=(),
    altitude_m=(),
    latitude_deg=(),
    longitude_deg=(),
    temperature_c=(),
)


def extract_samples(
    record_mesgs: list[dict[str, object]],
    start_time: datetime | None,
) -> tuple[Samples, tuple[datetime, ...]]:
    """Extract parallel channel arrays plus absolute record timestamps (Req 3.1-3.6).

    ``record_mesgs`` is the decoded ``record_mesgs`` list; ``start_time`` is the
    activity start used as the ``time_s`` anchor. When ``start_time`` is ``None``
    the anchor is the first retained record's timestamp (so ``time_s`` starts at
    ``0.0``).

    Returns the :class:`Samples` and the tuple of absolute record timestamps (one
    per retained record, in file order) for downstream lap projection. Records
    lacking a ``timestamp`` are dropped -- the only record-level exclusion; if
    none remain, an empty :class:`Samples` and empty timestamps tuple are
    returned. Values are stored raw: no smoothing, resampling, or reordering
    (Req 3.6).
    """
    retained = [
        record for record in record_mesgs if record.get("timestamp") is not None
    ]
    if not retained:
        return _EMPTY_SAMPLES, ()

    timestamps = tuple(
        fit_datetime(_raw_timestamp(record["timestamp"])) for record in retained
    )
    anchor = start_time if start_time is not None else timestamps[0]

    samples = Samples(
        time_s=tuple((ts - anchor).total_seconds() for ts in timestamps),
        heart_rate_bpm=tuple(_int_channel(r.get("heart_rate")) for r in retained),
        power_w=tuple(_int_channel(r.get("power")) for r in retained),
        cadence_rpm=tuple(_float_channel(r.get("cadence")) for r in retained),
        speed_mps=tuple(
            _float_channel(prefer_enhanced(r, "enhanced_speed", "speed"))
            for r in retained
        ),
        distance_m=tuple(_float_channel(r.get("distance")) for r in retained),
        altitude_m=tuple(
            _float_channel(prefer_enhanced(r, "enhanced_altitude", "altitude"))
            for r in retained
        ),
        latitude_deg=tuple(
            _semicircles_to_degrees(r.get("position_lat")) for r in retained
        ),
        longitude_deg=tuple(
            _semicircles_to_degrees(r.get("position_long")) for r in retained
        ),
        temperature_c=tuple(_float_channel(r.get("temperature")) for r in retained),
    )
    return samples, timestamps


def _raw_timestamp(value: object) -> int:
    """Narrow a decoded ``timestamp`` to the raw FIT-epoch integer it always is.

    The decoder is configured with ``convert_datetimes_to_dates=False``, so record
    timestamps arrive as raw integer seconds since the FIT epoch.
    """
    if isinstance(value, int):
        return value
    raise TypeError(f"expected an integer FIT timestamp, got {type(value).__name__}")


def _int_channel(value: object) -> int | None:
    """An integer channel reading (heart rate, power), unchanged, or ``None``.

    A present value is returned verbatim (Req 3.6); an absent one is ``None``
    (Req 3.2).
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise TypeError(f"expected an integer channel value, got {type(value).__name__}")


def _float_channel(value: object) -> float | None:
    """A real-valued channel reading, unchanged, or ``None``.

    Integers are accepted and returned verbatim (some channels -- cadence,
    temperature -- decode as ``int`` yet are modelled as ``float``); no coercion
    or smoothing is applied (Req 3.6). Absent values are ``None`` (Req 3.2).
    """
    if value is None:
        return None
    if isinstance(value, int | float):
        return value
    raise TypeError(f"expected a numeric channel value, got {type(value).__name__}")


def _semicircles_to_degrees(value: object) -> float | None:
    """Convert a raw semicircle coordinate to decimal degrees, or ``None`` (Req 3.4)."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return value * _SEMICIRCLE_TO_DEGREE
    raise TypeError(f"expected a numeric semicircle value, got {type(value).__name__}")
