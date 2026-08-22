"""Lap projection: ``lap_mesgs`` -> :class:`Lap` tuple with sample index ranges.

:func:`extract_laps` maps each decoded lap message onto the model's :class:`Lap`
contract and projects it onto the record stream as an INCLUSIVE start/end sample
index range (Req 4.3). Every recorded summary field is read verbatim by FIT key
with ``dict.get`` so an unrecorded field becomes ``None`` while a recorded ``0``
is preserved as a real zero (Req 12.3); ``start_time`` is converted from raw
FIT-epoch seconds with the shared :func:`fitdocs.model.fit_datetime` helper.

Projection algorithm:

- ``record_timestamps`` is the non-decreasing tuple of absolute record timestamps
  the record extractor returns. For a lap with a ``start_time``, its
  ``start_index`` is the first record at or after that start --
  ``bisect_left(record_timestamps, start_time)`` (Req 4.3).
- Laps that HAVE a ``start_time`` are considered in ``start_time`` order; their
  ``start_index`` values partition the record stream. A lap's ``end_index`` is
  the index just before the NEXT such lap's ``start_index``; the LAST one ends at
  the final record index. Both ends are inclusive. For real files -- whose laps
  are already chronological -- this tiles ``[0, N-1]`` into contiguous,
  non-overlapping windows.
- A lap whose window contains no records -- because it starts after every record
  (``start_index >= N``) or its computed window is empty (``start_index >
  end_index``), or ANY lap when there are no records at all, or a lap lacking a
  ``start_time`` -- gets ``start_index = end_index = None`` while its recorded
  summary fields are preserved (Req 4.4).

The returned tuple preserves the ORIGINAL message order (the model's
"laps preserve message order" invariant); the projection is computed in
``start_time`` order internally and mapped back onto that message order.

This module depends on :mod:`fitdocs.model` and the shared ingest field-coercion
helpers in :mod:`fitdocs.ingest._fields` (the within-layer home for defensive
decode-value handling, as used by the summary and set extractors) plus the
standard library (``bisect``, ``datetime``); it never imports the SDK or the
metrics layer.
"""

from __future__ import annotations

import bisect
from datetime import datetime

from fitdocs.ingest._fields import prefer_enhanced
from fitdocs.model import Lap, fit_datetime


def extract_laps(
    lap_mesgs: list[dict[str, object]],
    record_timestamps: tuple[datetime, ...],
) -> tuple[Lap, ...]:
    """Project laps onto inclusive record-index ranges (Req 4.3, 4.4).

    ``lap_mesgs`` is the decoded ``lap_mesgs`` list; ``record_timestamps`` is the
    non-decreasing tuple of absolute record timestamps produced by the record
    extractor. Returns one :class:`Lap` per message in the ORIGINAL message order.

    Each lap's ``start_index``/``end_index`` are inclusive indices into the sample
    arrays. Laps with a ``start_time`` are projected in ``start_time`` order so
    their windows partition the stream (``end_index`` = the index before the next
    lap's ``start_index``; the last ends at the final record). A lap that matches
    no records -- it starts after every record, its window is empty, it lacks a
    ``start_time``, or there are no records at all -- gets ``None`` indices with
    its recorded summary fields preserved (Req 4.4). An empty input yields an
    empty tuple.
    """
    n = len(record_timestamps)
    start_times = [_lap_start_time(mesg) for mesg in lap_mesgs]
    ranges: list[tuple[int | None, int | None]] = [(None, None)] * len(lap_mesgs)

    if n > 0:
        # (start_time, original message index, start_index) for projectable laps.
        projectable: list[tuple[datetime, int, int]] = [
            (start_time, index, bisect.bisect_left(record_timestamps, start_time))
            for index, start_time in enumerate(start_times)
            if start_time is not None
        ]
        projectable.sort(key=lambda item: item[0])  # start_time order

        for position, (_start, index, start_index) in enumerate(projectable):
            if position + 1 < len(projectable):
                end_index = projectable[position + 1][2] - 1
            else:
                end_index = n - 1  # the last projectable lap ends at the final record
            # A lap starting past the stream, or with an empty window, matches no
            # records -> leave its (None, None) indices in place (Req 4.4).
            if start_index < n and start_index <= end_index:
                ranges[index] = (start_index, end_index)

    return tuple(
        _build_lap(mesg, start_time, start_index, end_index)
        for mesg, start_time, (start_index, end_index) in zip(
            lap_mesgs, start_times, ranges, strict=True
        )
    )


def _build_lap(
    mesg: dict[str, object],
    start_time: datetime | None,
    start_index: int | None,
    end_index: int | None,
) -> Lap:
    """Map one lap message plus its projected index range to a :class:`Lap`.

    Summary fields are read verbatim by FIT key: absent keys become ``None`` and
    recorded zeros are preserved (Req 12.3). Speed prefers the ``enhanced_*``
    variant when it is a usable scalar, else the basic variant (Req 3.3 parity) --
    a real lap's ``enhanced_avg_speed`` can decode as a component-expanded array,
    in which case the plain ``avg_speed`` scalar is used. ``start_time`` is the
    already-converted datetime shared with the projection step.
    """
    return Lap(
        start_time=start_time,
        total_elapsed_time_s=_float_or_none(mesg.get("total_elapsed_time")),
        total_timer_time_s=_float_or_none(mesg.get("total_timer_time")),
        total_distance_m=_float_or_none(mesg.get("total_distance")),
        avg_heart_rate_bpm=_int_or_none(mesg.get("avg_heart_rate")),
        max_heart_rate_bpm=_int_or_none(mesg.get("max_heart_rate")),
        avg_power_w=_int_or_none(mesg.get("avg_power")),
        max_power_w=_int_or_none(mesg.get("max_power")),
        avg_cadence_rpm=_float_or_none(mesg.get("avg_cadence")),
        avg_speed_mps=_float_or_none(
            prefer_enhanced(mesg, "enhanced_avg_speed", "avg_speed")
        ),
        max_speed_mps=_float_or_none(
            prefer_enhanced(mesg, "enhanced_max_speed", "max_speed")
        ),
        total_ascent_m=_float_or_none(mesg.get("total_ascent")),
        total_descent_m=_float_or_none(mesg.get("total_descent")),
        start_index=start_index,
        end_index=end_index,
    )


def _lap_start_time(mesg: dict[str, object]) -> datetime | None:
    """Convert a lap's raw FIT-epoch ``start_time`` to a UTC datetime, or ``None``.

    With the decoder's ``convert_datetimes_to_dates=False``, ``start_time`` arrives
    as raw integer seconds since the FIT epoch; an absent start stays ``None``
    (Req 2.4).
    """
    value = mesg.get("start_time")
    if value is None:
        return None
    if isinstance(value, int):
        return fit_datetime(value)
    raise TypeError(f"expected an integer FIT timestamp, got {type(value).__name__}")


def _int_or_none(value: object) -> int | None:
    """An integer field value, unchanged, or ``None`` when absent (Req 12.3)."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise TypeError(f"expected an integer field value, got {type(value).__name__}")


def _float_or_none(value: object) -> float | None:
    """A real-valued field, unchanged, or ``None`` when absent (Req 12.3).

    Integers are accepted and returned verbatim (some FIT fields -- cadence,
    ascent -- decode as ``int`` yet are modelled as ``float``); a recorded ``0``
    is preserved as a real zero, never dropped.
    """
    if value is None:
        return None
    if isinstance(value, int | float):
        return value
    raise TypeError(f"expected a numeric field value, got {type(value).__name__}")
