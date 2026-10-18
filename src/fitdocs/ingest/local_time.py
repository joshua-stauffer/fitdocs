"""Read the activity's recorded local-time offset (Amendment 8, Req 4.13, 4.14).

One pure function over the decoded ``activity`` messages. The FIRST message's
``local_timestamp`` is the recording device's local clock at the instant its
``timestamp`` names, so their difference is the offset from UTC the device was
keeping: east of UTC is positive, west negative. Both values arrive as raw
FIT-epoch integers (the decode wrapper keeps ``convert_datetimes_to_dates``
off), so the difference is exact.

A difference no time zone could have -- not a whole number of 15-minute steps,
or outside -12 h to +14 h -- is ``None``, as is a missing or non-integer value:
the offset is never rounded, clamped, or replaced by any other zone.

Imports only the standard library.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Final

__all__ = ["extract_local_offset"]

_STEP_S: Final[int] = 15 * 60
_WESTMOST_S: Final[int] = -12 * 3600
_EASTMOST_S: Final[int] = 14 * 3600


def _genuine_int(value: object) -> int | None:
    """``value`` when it is an ``int`` that is not a ``bool``, else ``None``."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def extract_local_offset(activity_mesgs: list[dict[str, object]]) -> timedelta | None:
    """The first ``activity`` message's recorded UTC offset, or ``None``."""
    if not activity_mesgs:
        return None
    first = activity_mesgs[0]
    timestamp = _genuine_int(first.get("timestamp"))
    local = _genuine_int(first.get("local_timestamp"))
    if timestamp is None or local is None:
        return None
    delta = local - timestamp
    if delta % _STEP_S or not _WESTMOST_S <= delta <= _EASTMOST_S:
        return None
    return timedelta(seconds=delta)
