"""The substitutable heart-rate weighting seam (Req 5.4, 5.5, 5.6, 5.7, 5.8,
8.6, 9.8).

**Why this module exists.** Roadmap decision 7
(``.kiro/steering/roadmap.md``, "Build-time HR regression: deferred entirely,
not stubbed") requires the heart-rate channel's intensity weighting to be
reached through a substitutable component so that a later, build-time
power-calibrated regression can slot in as a *second* implementer of
:class:`HeartRateIntensityModel` without a rewrite of the channel that
consumes it (Req 5.7). That regression is explicitly out of this feature's
scope (roadmap "Out": build-time power-calibrated HR regression, deferred)
and is not stubbed, registered, or otherwise anticipated here: this module
ships **exactly one** implementer, :class:`BanisterTrimpModel`, below -- no
second implementation, no registry, no configuration key selecting one, and
no unreachable branch anticipating one (Req 5.8).

**Delegation, not restatement.** Both :meth:`BanisterTrimpModel.activity_impulse`
and :meth:`BanisterTrimpModel.hourly_impulse_at` delegate to the shipped
:func:`fitdocs.metrics.stress.trimp` unchanged (Req 5.4). This module edits
no line of ``metrics/stress.py`` and restates none of its disputed
multiplicative coefficient / exponent pair -- the one governed by
:data:`fitdocs.load.channels.sources.BANISTER_TRIMP` (task 1.1's citation
record) -- anywhere in its own code, not even in prose (Req 5.6, 8.6, 9.8).

**What "the same resolution" actually means, precisely.** Both methods call
:func:`fitdocs.metrics.sources.weighting_for` with ``None``, always -- the
seam has no athlete input and so always resolves
:data:`~fitdocs.metrics.sources.DEFAULT_TRIMP_WEIGHTING` (Req 17.2's
no-selection default), never a caller-selected pair. This is *not* the same
resolution :mod:`fitdocs.metrics` itself performs when computing the
shipped, rendered TRIMP: the metrics facade (``fitdocs/metrics/__init__.py``)
calls ``sources.weighting_for(athlete.trimp_weighting)``, honouring whatever
selection the athlete's own profile carries. When that selection is the
default, the two calls resolve to the identical pair and a re-sourcing of it
moves both together. When an athlete carries a *non-default* selection (for
example ``TrimpWeighting.BANISTER_FEMALE``), the shipped, rendered TRIMP for
that athlete uses the female pair while this seam still silently uses the
male default -- a real, measured divergence (3600 s at a constant 150 bpm,
resting 40, max 190: the shipped metric under the female selection yields
``128.7707138467988``; this seam yields ``115.11165050078277`` regardless of
the athlete's selection), not a hypothetical one. This is recorded here as a
deliberate scope limit, not fixed silently: the Protocol
(:class:`HeartRateIntensityModel`) carries no weighting-selection parameter
(design.md's Service Interface), so the heart-rate channel that will
consume this seam (task 3.2) has no way to pass an athlete's selection
through it either -- closing this gap, if it should be closed, is a design
question for the consuming channel and the Protocol shape, not something
this module can resolve unilaterally by reading extra state it is not
given.

**The one-hour reference is not test scaffolding.** The reference used by
:meth:`BanisterTrimpModel.hourly_impulse_at` is obtained by scoring a
synthetic one-hour, constant-heart-rate :class:`~fitdocs.model.Samples`
through that *same* shipped function (Req 5.5), via :func:`_one_hour_at`
below. :func:`fitdocs.metrics.stress.trimp` has no closed-form shortcut for
"one hour at a constant heart rate" -- its only definition is the
sample-pair integration -- so scoring a synthetic series is the production
mechanism by which this module obtains that number, not a test fixture that
happens to live in ``src/``. Because the reference is produced by the exact
same call path as the activity value, the two can never be weighted
differently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from fitdocs.metrics import sources as metrics_sources
from fitdocs.metrics.stress import trimp
from fitdocs.model import Samples


class HeartRateIntensityModel(Protocol):
    """The one substitutable seam through which heart rate becomes a
    training impulse and its one-hour reference (Req 5.7).

    A later build-time power-calibrated regression becomes a *second*
    implementer of this Protocol when it lands; none exists yet, and this
    module holds no registry, configuration key, or unreachable branch that
    anticipates one (Req 5.8).
    """

    model_id: str

    def activity_impulse(
        self, samples: Samples, *, resting_hr: int, max_hr: int
    ) -> float | None: ...

    def hourly_impulse_at(
        self, heart_rate: int, *, resting_hr: int, max_hr: int
    ) -> float | None: ...


def _one_hour_at(heart_rate: int) -> Samples:
    """A synthetic one-hour, constant-heart-rate :class:`Samples` -- the
    smallest input :func:`fitdocs.metrics.stress.trimp` integrates a full
    hour over: a single interval from offset ``0.0`` s to ``3600.0`` s
    carrying ``heart_rate`` on its earlier (and only governing) sample.
    Every other channel is unrecorded (``None``); the reference depends on
    heart rate alone.

    This is production code, not test scaffolding: it is how
    :meth:`BanisterTrimpModel.hourly_impulse_at` obtains its answer
    (Req 5.5), by handing the shipped metric the same shape of input it
    always expects rather than by approximating the metric's formula here.
    """
    none_ints: tuple[int | None, ...] = (None, None)
    none_floats: tuple[float | None, ...] = (None, None)
    return Samples(
        time_s=(0.0, 3600.0),
        heart_rate_bpm=(heart_rate, heart_rate),
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


@dataclass(frozen=True)
class BanisterTrimpModel:
    """The one shipped implementation of :class:`HeartRateIntensityModel`
    (Req 5.8): the fixed Banister/Morton physiological weighting, delegated
    to :func:`fitdocs.metrics.stress.trimp` unchanged (Req 5.4, 5.6, 8.6,
    9.8; :data:`fitdocs.load.channels.sources.BANISTER_TRIMP`). No second
    implementation, no registry, no configuration key and no unreachable
    branch exist in this module.
    """

    model_id: str = "banister-trimp"

    def activity_impulse(
        self, samples: Samples, *, resting_hr: int, max_hr: int
    ) -> float | None:
        """The activity's training impulse, from the shipped metric
        unchanged (Req 5.4). Returns ``None`` exactly when
        :func:`fitdocs.metrics.stress.trimp` does -- an entirely unrecorded
        heart-rate channel, or a non-positive reserve.
        """
        weighting = metrics_sources.weighting_for(None)
        result = trimp(samples, resting_hr, max_hr, weighting)
        return None if result is None else result.value

    def hourly_impulse_at(
        self, heart_rate: int, *, resting_hr: int, max_hr: int
    ) -> float | None:
        """The impulse of one hour held at ``heart_rate``, scored through
        the same shipped metric over the synthetic one-hour sample series
        :func:`_one_hour_at` builds (Req 5.5). Strictly positive whenever
        ``resting_hr < heart_rate`` and ``max_hr > resting_hr`` hold, since
        every term of the shipped formula is then strictly positive.
        """
        weighting = metrics_sources.weighting_for(None)
        result = trimp(_one_hour_at(heart_rate), resting_hr, max_hr, weighting)
        return None if result is None else result.value


BANISTER_TRIMP_MODEL: Final[BanisterTrimpModel] = BanisterTrimpModel()
"""The single shipped :class:`HeartRateIntensityModel` implementation (Req
5.8) -- the value a caller (the heart-rate channel, task 3.2) injects rather
than selecting from a registry."""
