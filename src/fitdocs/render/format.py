"""Display formatting and the missing-data-honesty absence rules (Req 13).

This module is the single home for how derived values become strings and how
absence is represented. Two conventions carry the honesty requirement:

- **Absent input -> ``None``.** Every ``fmt_*`` function returns ``None`` when
  its numeric input is ``None``. Block-level callers omit the whole element for
  a ``None`` result; table-cell callers pass the result through :func:`cell`,
  which renders the in-table absence marker :data:`ABSENT`. The formatters
  themselves never return :data:`ABSENT` -- absence is the caller's rendering
  decision (13.1).
- **A recorded zero is a genuine value, never absence.** ``0`` / ``0.0`` map to
  real formatted strings (``"0:00"``, ``"0 w"``, ``"0.00 km"``, ...), never to
  ``None`` or :data:`ABSENT`. Every guard tests ``value is None`` rather than
  truthiness so a true zero is never mistaken for missing data (13.3).

Precision is fixed and deterministic (golden-file friendly):

- ``fmt_duration`` / ``fmt_pace`` round to whole seconds (Python ``round``,
  banker's rounding) and zero-pad the minute/second sub-parts.
- ``fmt_speed_kmh`` converts m/s to km/h (x3.6) at **one** decimal place.
- ``fmt_distance_km`` converts metres to km at **two** decimal places.
- ``fmt_int`` rounds to the nearest whole number and appends the unit.

Rounding uses Python's built-in round-half-to-even, which is deterministic for
identical inputs across runs.
"""

from __future__ import annotations

from typing import Final

ABSENT: Final[str] = "–"
"""In-table absence marker: EN DASH (U+2013). Used *inside* tables only; block
-level callers omit an absent element rather than printing this marker."""


def fmt_duration(seconds: float | None) -> str | None:
    """Format a duration: ``h:mm:ss`` at >= 1 h, else ``m:ss`` (13.3).

    ``None`` -> ``None`` (absent). A true zero renders ``"0:00"``. Whole minutes
    and seconds are zero-padded; the leading hour/minute field is not.
    """
    if seconds is None:
        return None
    total = round(seconds)
    if total >= 3600:
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def fmt_pace(s_per_km: float | None) -> str | None:
    """Format a pace in seconds-per-km as ``"m:ss /km"`` (13.3).

    ``None`` -> ``None`` (absent). A true zero renders ``"0:00 /km"``. Seconds
    are zero-padded; minutes are not clamped (a pace over an hour per km would
    show as ``"61:01 /km"``).
    """
    if s_per_km is None:
        return None
    total = round(s_per_km)
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d} /km"


def fmt_speed_kmh(mps: float | None) -> str | None:
    """Format a speed in metres-per-second as ``"<km/h> km/h"`` at 1 decimal.

    ``None`` -> ``None`` (absent). A true zero renders ``"0.0 km/h"``.
    """
    if mps is None:
        return None
    return f"{mps * 3.6:.1f} km/h"


def fmt_distance_km(m: float | None) -> str | None:
    """Format a distance in metres as ``"<km> km"`` at 2 decimals.

    ``None`` -> ``None`` (absent). A true zero renders ``"0.00 km"``.
    """
    if m is None:
        return None
    return f"{m / 1000:.2f} km"


def fmt_int(value: float | None, unit: str) -> str | None:
    """Round ``value`` to the nearest whole number and append ``unit``.

    ``None`` -> ``None`` (absent). A true zero renders ``"0 <unit>"`` (e.g.
    ``fmt_int(0, "w")`` -> ``"0 w"``).
    """
    if value is None:
        return None
    return f"{round(value)} {unit}"


def cell(value: str | None) -> str:
    """Render a table cell: :data:`ABSENT` for ``None``, else ``value`` verbatim.

    Only ``None`` -- true absence -- becomes the marker; an already-formatted
    zero string is passed through unchanged (13.1, 13.3).
    """
    return ABSENT if value is None else value
