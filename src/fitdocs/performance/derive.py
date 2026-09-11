"""One outcome per quantity, for one activity, behind its own gate (design:
DerivationLeaf; Req 2.1-2.9, 8.7).

Pure: every function here takes the parsed `Activity`, the tagged page's
`EffortTag`, the page's own `date` and its data-root-relative path, and
returns a `DerivationOutcome` -- never raises, opens nothing, and consults no
clock. Every number this module reaches for a methodology constant comes
through `fitdocs.performance.sources` (never a bare numeric literal, Req
8.3); every declined outcome carries a non-empty `detail` (design's
DerivationLeaf invariant).

`threshold_pace` (task 3.1) is the first leaf: threshold pace, running only,
race kind only, solved through the Riegel race-equivalence model
(`fitdocs.performance.models.threshold_pace_s_per_km`). 3.2, 3.3 and 3.4 add
the remaining leaves and the `derive()` routing entry point to this module.
"""

from __future__ import annotations

import math
from datetime import date

from fitdocs import Sport
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.contract import EffortKind, EffortTag
from fitdocs.model import Activity
from fitdocs.performance import models, sources
from fitdocs.performance.types import (
    DeclineReason,
    DerivationDeclined,
    DerivationMethod,
    DerivationOutcome,
    DerivedBenchmark,
)


def _finite_positive(value: float | None) -> bool:
    """`True` only for a present, finite, strictly positive number -- the
    same absent-data rule `fitdocs.performance.models` applies to its own
    inputs (Req 2.6)."""
    if value is None:
        return False
    return math.isfinite(value) and value > 0


def _threshold_pace_inputs(
    activity: Activity, tag: EffortTag
) -> tuple[float | None, float | None, str]:
    """The (distance_m, time_s, inputs-text) triple `threshold_pace` solves
    from, following the design's "official beats recorded" rule (2.2-2.4):

    - the tag's official distance *and* official time, when both are
      present -- the official pair;
    - otherwise, when the tag carries a time alone (effort-tags lets time
      stand without a distance), the activity's recorded distance paired
      with that official time -- the mixed case, named as such;
    - otherwise the activity's recorded distance and recorded elapsed time
      -- the fully recorded pair.

    Either element of the returned pair may be `None` when its source did
    not carry a usable value; the caller checks that before use (Req 2.6).
    """
    if tag.distance_m is not None and tag.time_s is not None:
        distance_m = tag.distance_m
        time_s = tag.time_s
        inputs = (
            f"official distance {distance_m:g} m, official time {time_s:g} s "
            "(effort tag)"
        )
        return distance_m, time_s, inputs

    recorded_distance_m = activity.summary.total_distance_m
    if tag.time_s is not None:
        mixed_time_s = tag.time_s
        inputs = (
            f"recorded distance {_fmt(recorded_distance_m)} m (activity), "
            f"official time {mixed_time_s:g} s (effort tag)"
        )
        return recorded_distance_m, mixed_time_s, inputs

    recorded_time_s = activity.summary.total_elapsed_time_s
    inputs = (
        f"recorded distance {_fmt(recorded_distance_m)} m, "
        f"recorded elapsed time {_fmt(recorded_time_s)} s (activity)"
    )
    return recorded_distance_m, recorded_time_s, inputs


def _fmt(value: float | None) -> str:
    """Render a possibly-absent number for an `inputs`/`detail` string
    without fabricating a value: `None` renders as the literal `None` so an
    absent input is visible in the text rather than silently dropped."""
    if value is None:
        return "None"
    return f"{value:g}"


def threshold_pace(
    activity: Activity,
    tag: EffortTag,
    *,
    on: date | None,
    document: str,
) -> DerivationOutcome:
    """Threshold pace for a running race, through Riegel's race-equivalence
    law solved for the one-hour distance (design: DerivationLeaf; Req
    2.1-2.9, 8.7).

    Declines, each carrying a non-empty `detail` and never raising:

    - `UNDATED_DOCUMENT` -- `on` is `None` (7.6). Checked first, ahead of
      every other gate including the kind gate: an undated page always
      declines `UNDATED_DOCUMENT`, never a downstream reason, regardless of
      which kind or quantity was attempted (design DerivationLeaf
      postcondition).
    - `EFFORT_KIND_NOT_USED` -- the tag's kind is not `race` (2.8; the
      routing table names pace `race`-only for running).
    - `MISSING_INPUT` -- the distance or time this derivation would use is
      absent, non-positive, or non-finite (2.6).
    - `OUTSIDE_VALIDITY_WINDOW` -- the effort's duration falls outside
      Riegel's published window; both bounds are named in the detail and the
      duration is never clamped into range (2.5).
    """
    method = DerivationMethod.RIEGEL_RACE_EQUIVALENCE

    # Gate order rule (copy for 3.2/3.3): UNDATED_DOCUMENT is checked before
    # every other gate, including the kind gate, so an undated page always
    # declines UNDATED_DOCUMENT regardless of the attempted kind.
    if on is None:
        return DerivationDeclined(
            kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
            method=method,
            reason=DeclineReason.UNDATED_DOCUMENT,
            detail=f"{document} carries no parseable date to derive against",
        )

    if tag.kind is not EffortKind.RACE:
        return DerivationDeclined(
            kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
            method=method,
            reason=DeclineReason.EFFORT_KIND_NOT_USED,
            detail=(
                f"effort kind {tag.kind.value!r} is not used for threshold "
                "pace (race only)"
            ),
        )

    distance_m, time_s, inputs = _threshold_pace_inputs(activity, tag)

    if not _finite_positive(distance_m) or not _finite_positive(time_s):
        missing = []
        if not _finite_positive(distance_m):
            missing.append(f"distance ({_fmt(distance_m)} m)")
        if not _finite_positive(time_s):
            missing.append(f"time ({_fmt(time_s)} s)")
        return DerivationDeclined(
            kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
            method=method,
            reason=DeclineReason.MISSING_INPUT,
            detail=(
                "threshold pace needs a positive, finite "
                + " and ".join(missing)
                + f"; {inputs}"
            ),
        )

    assert distance_m is not None and time_s is not None  # narrowed above

    min_duration_s = sources.RIEGEL_MIN_DURATION_S.value
    max_duration_s = sources.RIEGEL_MAX_DURATION_S.value
    if not (min_duration_s <= time_s <= max_duration_s):
        # `required` names the specific bound this duration actually
        # crossed (never both, and never the bound it satisfied), while
        # `detail` still names both bounds for a human reader.
        required = min_duration_s if time_s < min_duration_s else max_duration_s
        return DerivationDeclined(
            kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
            method=method,
            reason=DeclineReason.OUTSIDE_VALIDITY_WINDOW,
            detail=(
                f"duration {time_s:g}s is outside Riegel's validity window "
                f"[{min_duration_s:g}s, {max_duration_s:g}s]"
            ),
            observed=time_s,
            required=required,
        )

    pace_s_per_km = models.threshold_pace_s_per_km(distance_m=distance_m, time_s=time_s)
    if pace_s_per_km is None:
        # Both gates above already establish finite, positive inputs inside
        # the validity window, so `models` cannot decline here in practice --
        # this is a defensive absent-data outcome, never a fabricated value.
        return DerivationDeclined(
            kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
            method=method,
            reason=DeclineReason.MISSING_INPUT,
            detail=f"the race-equivalence model produced no value from {inputs}",
        )

    return DerivedBenchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=pace_s_per_km,
        measured_on=on,
        method=method,
        citation_key=sources.RIEGEL_1981.key,
        inputs=inputs,
        note=(
            "Threshold pace via Riegel's race-equivalence law, solved for "
            "the one-hour distance (fitdocs' own further step, RIEGEL_SOLVE"
            "_TARGET_S) and expressed as pace in seconds per kilometre."
        ),
        document=document,
    )
