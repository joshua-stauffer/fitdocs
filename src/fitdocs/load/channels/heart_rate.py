"""The heart-rate channel: Banister TRIMP normalized to one hour at LTHR
(design: HeartRateChannel).

**The injected seam, never the flat-profile-keyed derived metric (Req 5.1).**
:func:`compute` forms both terms of its ratio -- the activity's impulse and
the impulse of one hour spent at the threshold heart rate -- through the
caller-injected :class:`~fitdocs.load.channels.weighting.HeartRateIntensityModel`
(``model``, defaulting to the shipped
:data:`~fitdocs.load.channels.weighting.BANISTER_TRIMP_MODEL`), never through
``metrics.trimp``: that field is populated by the shipped metrics facade
against the athlete's *flat* profile keys and would silently anchor on
whatever those keys happen to hold rather than on the dated benchmarks this
channel was actually handed. ``metrics`` is accepted, for the uniform
three-channel ``compute`` shape, and read nowhere in this module.

**Load before, and independent of, intensity (Req 5.11).** ``load`` is
computed first, straight from the two impulse terms
(``activity_impulse / hourly_impulse_at(lthr) * 100``), and reads no
intensity value at any point. ``intensity`` is derived *from* ``load``
afterward, as the square root of the mean impulse rate relative to threshold
-- ``sqrt((load / 100) / (scored_duration_s / 3600))``. The bare impulse
rate, ``(load / 100) / (scored_duration_s / 3600)``, is *not* the intensity:
it is the square of what the power and pace channels report (``np / ftp``
and ``gap_speed / threshold_speed`` respectively), so it agrees with them
only at the multiplicative identity, threshold, and diverges everywhere
else. Taking the square root puts this channel on the one shared semantic
this feature defines once, on
:attr:`~fitdocs.load.channels.types.ChannelLoad.intensity`'s own docstring::

    load == (scored_duration_s / 3600) * intensity ** 2 * 100

which the square root satisfies by construction and the bare ratio does not,
away from threshold. Because ``intensity`` is computed from ``load`` and
never the reverse, no change to how ``intensity`` is derived can move
``load``'s numeric value (Req 1.7, 5.11) -- pinned directly in this
channel's own tests.

**Three required benchmarks, one wrong-quantity guard each (Req 1.9, 5.2).**
Every supplied benchmark -- ``lthr``, ``resting_hr``, ``max_hr`` -- is
checked with :func:`~fitdocs.load.channels.types.require_kind` at entry,
before any other condition, exactly as the power channel checks ``ftp``: a
benchmark of the wrong quantity is a programming error and fails loudly
rather than being computed from or reported as insufficiency. Only once all
three pass that guard (or are absent) does the module report
:data:`~fitdocs.load.channels.types.InsufficiencyReason.NO_BENCHMARK`,
naming every one of the three that is missing, when at least one is
``None`` (Req 5.2).

**Mutually inconsistent benchmarks reject rather than compute (Req 5.3).**
Given all three, a maximum not strictly above the resting rate, or a
threshold not strictly above the resting rate and not at-or-below the
maximum, is
:data:`~fitdocs.load.channels.types.InsufficiencyReason.BENCHMARKS_INCONSISTENT`
-- no computed value, even a nominal one, is ever returned for a set of
benchmarks that cannot describe one athlete.

**Gate on the heart-rate stream; scored duration is covered time (Req
5.9).** The shared :func:`~fitdocs.load.channels.sufficiency.evaluate` gate
runs against ``activity.samples.heart_rate_bpm`` after the benchmark checks
above and before any impulse is computed. ``scored_duration_s`` on a
successful result is the gate's own ``covered_s`` -- the span the impulse
integration actually accumulated dt over (the same time-weighted-coverage
domain :func:`fitdocs.metrics.stress.trimp` accumulates, per
``sufficiency.py``'s own docstring) -- not the activity's total elapsed or
recorded span.

**The intervals.icu material (Req 5.10, 5.11) -- claims no more than the
source supports.** :data:`fitdocs.load.channels.sources.INTERVALS_ICU_HRSS`
establishes that intervals.icu's heart-rate load, HRSS (normalized TRIMP),
is on the same scale this channel's load is: 100 corresponds to one hour at
max effort. That citation's own note is explicit about the limit of what it
supports: intervals.icu's founder posts never publish an HRSS formula and
never state HRSS's inputs, so the shared scale is as far as the read text
goes -- this module does not claim intervals.icu is known to derive its
load through the same arithmetic or from the same three benchmark inputs
this channel requires. The
``heart_rate_reported_intensity`` entry of
:data:`fitdocs.load.channels.sources.DIVERGENCES` states this channel's
load is "directly comparable" to HRSS on that shared scale, and states
plainly, in words quoted here rather than paraphrased so a future edit
cannot silently invert them: "Numeric identity is not claimed". The
reported *intensity* is that same entry's one stated divergence:
intervals.icu publishes no heart-rate intensity definition at all, so there
is no published value to match this channel's ``sqrt(impulse_ratio)``
against; the reason this channel reports that square root anyway -- so one
intensity semantic spans all three channels -- is recorded on that same
entry, cited here rather than restated further (see task 1.1).

**Known, queued design gap the weighting seam carries (do not work around
it here).** :class:`~fitdocs.load.channels.weighting.BanisterTrimpModel`
resolves ``metrics.sources.weighting_for(None)`` unconditionally, ignoring
any athlete ``trimp_weighting`` selection the shipped metrics facade would
otherwise honour -- see ``weighting.py``'s own docstring and
``.kiro/queue/2026-08-23-hr-weighting-seam-ignores-athlete-trimp-selection.md``.
This channel consumes the injected :class:`~fitdocs.load.channels.weighting.
HeartRateIntensityModel` Protocol exactly as it stands and does not widen it
with a weighting parameter of its own.
"""

from __future__ import annotations

import math

from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity

from .sufficiency import evaluate
from .types import (
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
    InsufficiencyReason,
    SufficiencySettings,
    require_kind,
)
from .weighting import BANISTER_TRIMP_MODEL, HeartRateIntensityModel

_MISSING_NAMES: dict[str, str] = {
    "lthr": "a threshold heart rate (lthr_bpm)",
    "resting_hr": "a resting heart rate (resting_hr_bpm)",
    "max_hr": "a maximum heart rate (max_hr_bpm)",
}


def compute(
    activity: Activity,
    metrics: DerivedMetrics,
    *,
    lthr: Benchmark | None,
    resting_hr: Benchmark | None,
    max_hr: Benchmark | None,
    settings: SufficiencySettings,
    # mypy strict flags a frozen dataclass's fields as "read-only" against a
    # plain (non-ClassVar) Protocol attribute (``model_id: str``), which it
    # then treats as requiring a settable variable -- a known mypy
    # limitation with structural Protocol matching against frozen
    # dataclasses, not a real type error: BanisterTrimpModel does satisfy
    # HeartRateIntensityModel at runtime and by every method/attribute it
    # declares. weighting.py (task 2.1, out of this task's boundary) is not
    # touched to work around it.
    model: HeartRateIntensityModel = BANISTER_TRIMP_MODEL,  # type: ignore[assignment]
) -> ChannelOutcome:
    """Score ``activity``'s heart-rate channel, or report why it cannot be
    scored (design: HeartRateChannel Service Interface).

    ``metrics`` is accepted for the uniform three-channel ``compute`` shape
    and read nowhere in this function -- ``metrics.trimp`` is the flat-
    profile-keyed derived metric this channel must never anchor on (Req
    5.1); see this module's docstring.

    Evaluation order, fixed and documented here because it is what makes the
    reported reason deterministic when more than one condition fails:

    1. :func:`~fitdocs.load.channels.types.require_kind` on every supplied
       benchmark, before anything else (Req 1.9) -- a benchmark of the
       wrong quantity raises rather than being reported as insufficiency or
       computed from.
    2. :data:`~fitdocs.load.channels.types.InsufficiencyReason.NO_BENCHMARK`
       when any of ``lthr``, ``resting_hr``, ``max_hr`` is absent, naming
       every absent one (Req 5.2).
    3. :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       BENCHMARKS_INCONSISTENT` when the three cannot describe one athlete
       (Req 5.3) -- decided before the stream is even gated.
    4. The shared sufficiency gate on ``activity.samples.heart_rate_bpm``
       (Req 5.9); its own insufficiency, whichever reason it names, is
       returned unchanged.
    5. :data:`~fitdocs.load.channels.types.InsufficiencyReason.
       NOT_COMPUTABLE` when either impulse ``model`` returns is ``None``, or
       the one-hour-at-threshold reference is not strictly positive --
       checked only once the gate has passed.
    6. Otherwise, a :class:`~fitdocs.load.channels.types.ChannelLoad`: the
       load, computed first and independently of the intensity (Req 5.11).
    """
    if lthr is not None:
        require_kind(lthr, BenchmarkKind.LTHR_BPM)
    if resting_hr is not None:
        require_kind(resting_hr, BenchmarkKind.RESTING_HR_BPM)
    if max_hr is not None:
        require_kind(max_hr, BenchmarkKind.MAX_HR_BPM)

    missing = [
        name
        for name, value in (
            ("lthr", lthr),
            ("resting_hr", resting_hr),
            ("max_hr", max_hr),
        )
        if value is None
    ]
    if missing:
        detail = "missing: " + ", ".join(_MISSING_NAMES[name] for name in missing)
        return ChannelInsufficient(
            channel=ChannelId.HEART_RATE,
            reason=InsufficiencyReason.NO_BENCHMARK,
            detail=detail,
        )

    assert lthr is not None and resting_hr is not None and max_hr is not None

    # ``max_hr.value <= resting_hr.value`` is logically redundant given the
    # other two disjuncts (if ``lthr > resting_hr`` and ``lthr <= max_hr``
    # both hold, ``max_hr >= lthr > resting_hr`` follows transitively, so
    # ``max_hr <= resting_hr`` can never be true there) -- kept explicit
    # anyway because "max must exceed resting" is a named, independently
    # readable half of "these three cannot describe one athlete" (Req 5.3),
    # not something a reader should have to derive by transitivity.
    if (
        max_hr.value <= resting_hr.value
        or lthr.value <= resting_hr.value
        or lthr.value > max_hr.value
    ):
        return ChannelInsufficient(
            channel=ChannelId.HEART_RATE,
            reason=InsufficiencyReason.BENCHMARKS_INCONSISTENT,
            detail=(
                "heart-rate benchmarks are mutually inconsistent: require "
                "max_hr > resting_hr and resting_hr < lthr <= max_hr "
                f"(resting_hr={resting_hr.value:g}, lthr={lthr.value:g}, "
                f"max_hr={max_hr.value:g})"
            ),
        )

    gated = evaluate(
        activity.samples,
        activity.samples.heart_rate_bpm,
        channel=ChannelId.HEART_RATE,
        stream="heart_rate",
        settings=settings,
    )
    if isinstance(gated, ChannelInsufficient):
        return gated
    coverage = gated

    resting_int = int(resting_hr.value)
    max_int = int(max_hr.value)
    lthr_int = int(lthr.value)

    activity_impulse = model.activity_impulse(
        activity.samples, resting_hr=resting_int, max_hr=max_int
    )
    reference = model.hourly_impulse_at(
        lthr_int, resting_hr=resting_int, max_hr=max_int
    )
    if activity_impulse is None or reference is None or reference <= 0:
        return ChannelInsufficient(
            channel=ChannelId.HEART_RATE,
            reason=InsufficiencyReason.NOT_COMPUTABLE,
            detail=(
                "the activity's training impulse or the one-hour-at-"
                "threshold reference could not be derived from the data "
                "present"
            ),
        )

    scored_duration_s = coverage.covered_s
    load = activity_impulse / reference * 100
    intensity = math.sqrt((load / 100) / (scored_duration_s / 3600))

    inputs_used = (
        ("impulse", f"{activity_impulse:g}"),
        ("reference", f"{reference:g}"),
        # Req 1.3: the values reported here are the ones the computation
        # actually used -- the truncated integers handed to ``model``
        # (``lthr_int``/``resting_int``/``max_int``), not the raw
        # ``Benchmark.value`` fields. In practice ``benchmarks.py``'s own
        # parser already forecloses a fractional value ever reaching this
        # module: all three of ``lthr``/``resting_hr``/``max_hr`` are
        # ``INTEGRAL_KINDS`` and ``_validate_value`` REJECTS a fractional
        # entry outright (stated policy: "rejected rather than rounded or
        # truncated") rather than truncating it on the way in. ``Benchmark``
        # itself is still an unvalidated, directly-constructible frozen
        # dataclass, so this module's own tests pin the unit-level
        # int()-not-round() behavior for a fractional value regardless --
        # documenting what this function does with an input the domain
        # forecloses, not a real ingestion-path hazard.
        ("lthr_bpm", str(lthr_int)),
        ("resting_hr_bpm", str(resting_int)),
        ("max_hr_bpm", str(max_int)),
        ("lthr_measured_on", lthr.measured_on.isoformat()),
    )

    return ChannelLoad(
        channel=ChannelId.HEART_RATE,
        load=load,
        intensity=intensity,
        anchor=lthr,
        scored_duration_s=scored_duration_s,
        coverage=coverage,
        inputs_used=inputs_used,
    )
