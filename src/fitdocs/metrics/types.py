"""Caller-input and result contracts for every metric function.

These three standalone frozen dataclasses are the boundary between the metric
computations and their callers. They import nothing internal (stdlib only), so
they carry no FIT-format or activity-model knowledge:

- :class:`ZoneSpec` -- caller-supplied, strictly ascending zone dividers. It
  *fails fast* (raises :class:`ValueError`) on empty or non-ascending input, so
  malformed boundaries can never silently misbin samples and fabricate zone
  data (Req 10.4). There are deliberately **no** embedded default or fallback
  zone boundaries: zone *definitions* are the caller's (they live downstream in
  training-load); this spec owns only the band *math*.
- :class:`TrimpWeighting` -- the training-impulse weighting-curve selection
  (Amendment 1, Req 17.2, 17.3, 17.6). A member names the fitted CURVE, not the
  athlete. This module stays stdlib-only and citation-free: only the selection
  *vocabulary* lives here, while each selection's *values* live with the
  records downstream (MetricsSources) -- that split keeps the caller-facing
  contract clear of the provenance layer. The selection reaches the library
  only through caller-supplied :class:`AthleteInputs` (Req 17.3); nothing in
  this module reads a profile or a configuration file. The member *names* are
  an open maintainer decision (see ``spec.json``'s open-decisions record and
  ``.kiro/queue/2026-07-27-trimp-weighting-default-is-sex-named.md``) -- a
  later rename is expected, not a break in this contract.
- :class:`AthleteInputs` -- the optional athlete thresholds and zone
  definitions. Every field defaults to ``None``; an absent value means "not
  provided", and the metrics that need it simply return ``None``.
- :class:`DerivedMetrics` -- the full derived-metric result. Every field is
  independently ``None``-able so that a missing input never fabricates a value
  (Req 12.1); each field also defaults to ``None`` so the computation facade can
  populate only what it can honestly derive.

Units follow the model convention: watts (``w``), beats per minute (``bpm``),
seconds (``s``), metres (``m``), metres per second (``mps``), seconds per
kilometre (``s_per_km``), degrees Celsius (``c``), kilocalories (``kcal``).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TrimpWeighting(StrEnum):
    """Training-impulse weighting-curve selection (Amendment 1, Req 17.2,
    17.3, 17.6).

    Each member names a fitted curve the cited primary text publishes, not the
    athlete it was fitted to. This enumeration carries no weighting-pair
    values -- the weighting pair each member maps to lives downstream, with
    the records, so that this stdlib-only module never imports the citation
    layer. Nothing in this module resolves a member to a pair; a
    caller-supplied member threads through :class:`AthleteInputs` and back
    out on :class:`DerivedMetrics` (see :attr:`AthleteInputs.trimp_weighting`
    and :attr:`DerivedMetrics.trimp_weighting`) -- the resolution itself is
    wired in :mod:`fitdocs.metrics.sources` (:func:`~fitdocs.metrics.sources.
    weighting_for`), called by the metrics facade, which hands the
    resolved pair to :mod:`fitdocs.metrics.stress`;
    this module itself only ever declares the vocabulary and the two fields,
    never resolving or populating either.
    """

    BANISTER_MALE = "banister_male"
    BANISTER_FEMALE = "banister_female"


@dataclass(frozen=True)
class ZoneSpec:
    """Strictly ascending, non-empty zone dividers (Req 10.4).

    ``dividers`` are the caller-supplied band boundaries for a single channel
    (bpm for heart rate, watts for power, seconds-per-kilometre for pace). They
    must be strictly ascending and non-empty; ``n`` dividers partition the value
    line into ``n + 1`` bands. Band-occupancy math (which sample lands in which
    band) is computed downstream, not here -- this type only guarantees the
    boundaries are well-formed.

    Construction *fails fast*: a malformed ``dividers`` raises
    :class:`ValueError` at construction rather than allowing silent misbinning
    that would fabricate zone data. A list is accepted and normalized to a
    tuple for hashability.
    """

    dividers: tuple[float, ...]

    def __post_init__(self) -> None:
        # Normalize to a tuple so the frozen instance stays hashable even when a
        # caller passes a list; the annotation stays ``tuple[float, ...]``.
        object.__setattr__(self, "dividers", tuple(self.dividers))
        if not self.dividers:
            raise ValueError("ZoneSpec.dividers must be non-empty")
        if any(a >= b for a, b in zip(self.dividers, self.dividers[1:], strict=False)):
            raise ValueError(
                f"ZoneSpec.dividers must be strictly ascending; got {self.dividers!r}"
            )


@dataclass(frozen=True)
class AthleteInputs:
    """Optional athlete thresholds and zone definitions (all caller-supplied).

    Every field defaults to ``None``: thresholds and zone boundaries are the
    caller's to provide, and any of them may be absent. A metric that depends on
    an absent input returns ``None`` rather than substituting a default.
    :attr:`trimp_weighting` is the training-impulse weighting selection (Req
    17.2, 17.3): it reaches this record only from the caller, never from a
    stored profile or configuration file.
    """

    ftp_watts: float | None = None
    resting_hr_bpm: int | None = None
    max_hr_bpm: int | None = None
    hr_zones: ZoneSpec | None = None
    power_zones: ZoneSpec | None = None
    pace_zones: ZoneSpec | None = None
    trimp_weighting: TrimpWeighting | None = None


@dataclass(frozen=True)
class DerivedMetrics:
    """The full derived-metric result; every field is independently ``None``.

    A field is ``None`` whenever the inputs needed to compute it were absent or
    insufficient -- never a fabricated zero or default (Req 12.1). Every field
    also defaults to ``None`` so the computation facade populates only what it
    can honestly derive. All scalar fields are ``float | None`` except
    :attr:`calories_kcal` (``int | None``, a session passthrough); the three
    time-in-zone fields are ``tuple[float, ...] | None`` (seconds per band, or
    ``None`` when the channel or its :class:`ZoneSpec` is absent);
    :attr:`trimp_weighting` is a :class:`TrimpWeighting` (Req 17.6) that a
    later resolver populates so it is non-``None`` exactly when :attr:`trimp`
    is -- this module only declares the field, it does not populate it.
    """

    moving_time_s: float | None = None
    elapsed_time_s: float | None = None
    distance_m: float | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None
    avg_pace_s_per_km: float | None = None
    avg_heart_rate_bpm: float | None = None
    max_heart_rate_bpm: float | None = None
    avg_power_w: float | None = None
    max_power_w: float | None = None
    avg_cadence_rpm: float | None = None
    max_cadence_rpm: float | None = None
    normalized_power_w: float | None = None
    intensity_factor: float | None = None
    variability_index: float | None = None
    efficiency_factor: float | None = None
    decoupling_pct: float | None = None
    elevation_gain_m: float | None = None
    elevation_loss_m: float | None = None
    min_altitude_m: float | None = None
    max_altitude_m: float | None = None
    min_temperature_c: float | None = None
    max_temperature_c: float | None = None
    avg_temperature_c: float | None = None
    hr_time_in_zone_s: tuple[float, ...] | None = None
    power_time_in_zone_s: tuple[float, ...] | None = None
    pace_time_in_zone_s: tuple[float, ...] | None = None
    trimp: float | None = None
    trimp_weighting: TrimpWeighting | None = None
    power_tss: float | None = None
    calories_kcal: int | None = None
