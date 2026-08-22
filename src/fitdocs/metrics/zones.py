"""Generic time-in-band occupancy: the pure band-math for time-in-zone.

:func:`time_in_zone` attributes the duration between consecutive samples to
bands defined by caller-supplied ascending dividers. It is deliberately
*generic* over the channel: it knows nothing about heart rate, power, or pace.
The facade (a later task) maps each channel onto values and passes the caller's
:class:`~fitdocs.metrics.types.ZoneSpec`; this module owns only the math.

Two rules, matching the band semantics documented on
:class:`~fitdocs.metrics.types.ZoneSpec`:

- **Earlier-sample attribution.** For consecutive samples ``i`` and ``i+1`` the
  gap ``dt = time_s[i+1] - time_s[i]`` is credited to the band of the *earlier*
  sample, ``values[i]`` (Req 10.2). The final sample has no outgoing gap and so
  is never attributed on its own.
- **Boundary via ``bisect_right``.** A value ``v`` belongs to band
  ``i = bisect_right(spec.dividers, v)`` -- ``n`` dividers partition the value
  line into ``n + 1`` bands, and a value exactly equal to a divider falls into
  the *upper* band.

``None`` earlier values are "not recorded": their outgoing ``dt`` is credited
to *no* band (Req 10.3), so the occupied total can fall short of the elapsed
span. There are **no** embedded default or fallback boundaries: the result
length is exactly ``len(spec.dividers) + 1`` for any divider count, and the
function reads nothing but the caller's ``spec`` (Req 10.4).

The function is **total** for valid inputs: it never returns ``None`` and never
raises. Fewer than two samples yield an all-zero tuple of the right length
(there is no gap to attribute); a value below all dividers lands in band ``0``
and a value above all dividers in the last band. ``spec.dividers`` is validated
strictly ascending and non-empty at :class:`ZoneSpec` construction, so this
function may assume it is well-formed.

This module imports :class:`~fitdocs.metrics.types.ZoneSpec` and the standard
library (:mod:`bisect`) only -- never :mod:`fitdocs.ingest`, the FIT SDK, or
even :mod:`fitdocs.model`.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence

from fitdocs.metrics.types import ZoneSpec


def time_in_zone(
    values: Sequence[float | None],
    time_s: Sequence[float],
    spec: ZoneSpec,
) -> tuple[float, ...]:
    """Return seconds spent in each band, ``len == len(spec.dividers) + 1``.

    Each gap ``dt = time_s[i+1] - time_s[i]`` is credited to the band of the
    earlier sample ``values[i]`` (band ``bisect_right(spec.dividers, values[i])``);
    a ``None`` earlier value credits its gap to no band. The accumulator starts
    at ``0.0`` per band, so the returned tuple is always ``float`` even when
    ``time_s`` carries integer-valued offsets.

    ``values`` and ``time_s`` are assumed aligned (the facade passes parallel
    :class:`~fitdocs.model.Samples` channels); should their lengths differ, only
    the aligned prefix (``min`` length) is iterated -- the function never raises
    for that mismatch.
    """
    seconds: list[float] = [0.0] * (len(spec.dividers) + 1)
    n = min(len(values), len(time_s))
    for i in range(n - 1):
        value = values[i]
        if value is None:
            # A "not recorded" earlier value credits its gap to no band (10.3).
            continue
        dt = time_s[i + 1] - time_s[i]
        band = bisect.bisect_right(spec.dividers, value)
        seconds[band] += dt
    return tuple(seconds)
