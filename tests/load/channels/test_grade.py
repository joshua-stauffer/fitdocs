"""Tests for the grade-adjustment unit (``grade.py``).

Covers Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 7.8, 7.9 -- see
``.kiro/specs/load-channels/requirements.md`` and the "Domain --
src/fitdocs/load/channels/grade.py" / "GradeAdjustment" component in
design.md (``#### GradeAdjustment`` heading -- cite the heading over a line
range when following this pointer by hand, since any future edit above that
section shifts the range).

**What ``_reference_cr`` actually pins, precisely.** Where a test needs
Minetti's running-cost polynomial evaluated at a gradient, it reads
:data:`fitdocs.load.channels.grade.MINETTI_RUNNING_COEFFICIENTS` off the
module itself via ``_reference_cr`` and evaluates *that* tuple, rather than
retyping the polynomial's six coefficients a second time in this file. This
does **not** mean a coefficient mutation reds the value assertions built
from it: ``_reference_cr`` and :func:`grade.running_cost_ratio` read the
*same* tuple object, so a mutated coefficient moves both together and the
value assertions stay green on a coefficient-only mutation -- measured: a
``46.3`` -> ``60.0`` mutation reds exactly one test in this module,
``test_minetti_running_coefficients_pinned``, and nothing else. What the
value assertions actually pin is the polynomial's *structure* independently
of its coefficient values -- the exponents applied to the gradient, the
descending term order, and the division by the level-cost term -- since
``_reference_cr`` retypes that structure itself rather than reading it off
``grade.running_cost_ratio``. A structural mutation inside
``running_cost_ratio`` (a changed exponent, a term reordered against a
different coefficient, a missing division) diverges from ``_reference_cr``'s
independently-written structure and is caught by the value assertions;
retyping the exact coefficient values from
``MINETTI_RUNNING_COEFFICIENTS`` is what
``test_minetti_running_coefficients_pinned`` alone is responsible for.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import re

import pytest

from fitdocs.load.channels import grade
from fitdocs.metrics import aggregates as metrics_aggregates
from fitdocs.metrics import sources as metrics_sources
from fitdocs.model import Samples

_MODULE_SOURCE = inspect.getsource(grade)

# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------


def _samples(
    time_s: tuple[float, ...],
    distance_m: tuple[float | None, ...],
    altitude_m: tuple[float | None, ...],
) -> Samples:
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=none_ints,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=distance_m,
        altitude_m=altitude_m,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


def _reference_cr(gradient: float) -> float:
    """Evaluate Minetti's running-cost polynomial at ``gradient`` by reading
    the coefficient *values* off the production module
    (:data:`grade.MINETTI_RUNNING_COEFFICIENTS`) but retyping the
    polynomial's *structure* -- the exponents, the term order, which
    coefficient multiplies which power -- independently here (Fixture
    Discrimination Gate item 8). Because the coefficient values are shared
    with :func:`grade.running_cost_ratio`, a coefficient-only mutation (e.g.
    ``46.3`` -> ``60.0``) moves both together and is caught only by the
    direct tuple-equality assertion in
    ``test_minetti_running_coefficients_pinned``, not by any assertion built
    from this helper -- measured, not assumed. What a mutation *inside*
    ``running_cost_ratio``'s structure (a changed exponent, e.g.
    ``** 2`` -> ``** 3``, or a term applied to the wrong coefficient) does
    red is every assertion built from this helper, since this helper's own
    structure is retyped and does not move with such a mutation.
    """
    c5, c4, c3, c2, c1, c0 = grade.MINETTI_RUNNING_COEFFICIENTS
    return (
        c5 * gradient**5
        + c4 * gradient**4
        + c3 * gradient**3
        + c2 * gradient**2
        + c1 * gradient
        + c0
    )


# ---------------------------------------------------------------------------
# 7.1 -- published polynomial, coefficients cited and pinned
# ---------------------------------------------------------------------------


def test_minetti_running_coefficients_pinned() -> None:
    """Req 7.1: the published coefficient tuple, descending powers of the
    gradient, exactly as Fig. 1's caption gives it (see
    :data:`fitdocs.load.channels.sources.MINETTI_2002`)."""
    assert grade.MINETTI_RUNNING_COEFFICIENTS == (
        155.4,
        -30.4,
        -43.3,
        46.3,
        19.5,
        3.6,
    )


def test_minetti_level_cost_matches_coefficient_tuple_constant_term() -> None:
    """Req 7.1: the level-ground cost constant is *derived from* ``Cr(0)``
    -- the coefficient tuple's own constant term -- not an independently
    retyped ``3.6``.

    Neither a value-equality nor an ``is``-identity assertion pins this in
    practice: replacing ``MINETTI_LEVEL_COST_J_PER_KG_PER_M =
    MINETTI_RUNNING_COEFFICIENTS[-1]`` with the bare literal ``3.6`` gives
    the identical float object too, because CPython's compiler folds equal
    float literals appearing in the same module into one shared constant
    (measured: both variants leave ``is`` ``True`` on this exact module).
    So this pins the *code shape* directly via the AST instead: the
    assignment's right-hand side must be a subscript expression indexing
    ``MINETTI_RUNNING_COEFFICIENTS`` -- not a bare numeric literal -- which
    is false the moment the constant is retyped independently, regardless
    of what the compiler happens to do with the resulting float object.
    """
    tree = ast.parse(inspect.getsource(grade))
    target_name = "MINETTI_LEVEL_COST_J_PER_KG_PER_M"
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == target_name
    ]
    assert len(matches) == 1, (
        f"expected exactly one annotated assignment to {target_name!r}, "
        f"found {len(matches)} -- the AST walk is not finding the "
        f"declaration this test means to inspect"
    )
    rhs = matches[0].value
    assert isinstance(rhs, ast.Subscript), (
        f"{target_name} is not assigned from a subscript expression -- "
        f"got {ast.dump(rhs)!r}; it must read the coefficient tuple's own "
        f"constant term, not carry an independently retyped literal"
    )
    assert isinstance(rhs.value, ast.Name) and rhs.value.id == (
        "MINETTI_RUNNING_COEFFICIENTS"
    ), f"{target_name} is not subscripted from MINETTI_RUNNING_COEFFICIENTS"

    # Still assert the values agree, as a sanity check that the derivation
    # this AST shape describes is actually correct.
    assert (
        grade.MINETTI_RUNNING_COEFFICIENTS[-1]
        == grade.MINETTI_LEVEL_COST_J_PER_KG_PER_M
    )


def test_module_cites_minetti_2002() -> None:
    """Req 7.1, 8.1: the module names the governing citation record at the
    point the coefficients are defined, in code -- not only in the spec."""
    source = inspect.getsource(grade)
    assert "MINETTI_2002" in source


def test_module_does_not_carry_the_corrupted_linear_term() -> None:
    """Req 7.1: the widely-mirrored corrupted OCR transcription of this
    polynomial renders the linear term as ``-165*i`` instead of the correct
    ``+19.5*i`` (see ``.kiro/specs/load-channels/research.md``, "Minetti
    energy cost of running on a gradient", and
    :data:`fitdocs.load.channels.sources.MINETTI_2002`'s own note). The
    docstring is allowed -- required, even -- to *name* the corrupted
    variant so a future editor does not "fix" the correct value into it; what
    must never happen is ``-165`` (or ``165``) appearing as an actual numeric
    literal anywhere in the module's code. AST-scanned, so this only inspects
    real constants, never docstring or comment prose.
    """
    tree = ast.parse(inspect.getsource(grade))
    numeric_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
    }
    assert numeric_constants, (
        "the AST walk found no numeric constants at all -- the walk is not "
        "reaching the module body, not proving the module is clean"
    )
    assert -165 not in numeric_constants
    assert -165.0 not in numeric_constants
    assert 165 not in numeric_constants
    assert 19.5 in grade.MINETTI_RUNNING_COEFFICIENTS


# ---------------------------------------------------------------------------
# 7.4 -- clamp to the validated range, report whether clamping occurred
# ---------------------------------------------------------------------------


def test_running_cost_ratio_is_exactly_one_at_zero_gradient() -> None:
    """Req 7.4 postcondition: at ``i == 0`` the ratio is exactly ``1.0``,
    not merely close to it -- ``Cr(0) / Cr(0)``."""
    ratio, clamped = grade.running_cost_ratio(0.0)
    assert ratio == 1.0
    assert clamped is False


@pytest.mark.parametrize("gradient", [-0.45, 0.45])
def test_running_cost_ratio_accepts_boundary_unclamped(gradient: float) -> None:
    """Req 7.4: the validated range's own boundary (``±0.45``) is accepted
    without clamping -- the comparison against the boundary is strict, not
    inclusive."""
    ratio, clamped = grade.running_cost_ratio(gradient)
    assert clamped is False
    expected = _reference_cr(gradient) / grade.MINETTI_LEVEL_COST_J_PER_KG_PER_M
    assert ratio == pytest.approx(expected)


@pytest.mark.parametrize("gradient", [0.90, -0.90, 1.5])
def test_running_cost_ratio_clamps_beyond_boundary(gradient: float) -> None:
    """Req 7.4: a gradient outside ``[-0.45, 0.45]`` is clamped to the
    nearer boundary rather than extrapolated, and the clamp flag is set."""
    ratio, clamped = grade.running_cost_ratio(gradient)
    assert clamped is True
    boundary = (
        grade.MINETTI_MAX_ABS_GRADIENT
        if gradient > 0
        else -grade.MINETTI_MAX_ABS_GRADIENT
    )
    expected = _reference_cr(boundary) / grade.MINETTI_LEVEL_COST_J_PER_KG_PER_M
    assert ratio == pytest.approx(expected)
    # Not extrapolated: the clamped ratio must differ from what a naive,
    # unclamped evaluation at the raw (out-of-range) gradient would give.
    unclamped_reference = (
        _reference_cr(gradient) / grade.MINETTI_LEVEL_COST_J_PER_KG_PER_M
    )
    assert ratio != pytest.approx(unclamped_reference)


def test_clamped_intervals_counts_only_actually_clamped_intervals() -> None:
    """Req 7.4: ``clamped_intervals`` on the integrated result is neither
    the field's own default (0) nor tied to any other number the fixture
    carries -- it must reflect an actual per-interval count.

    Three positive, well-above-``MIN_GRADIENT_DISTANCE_M`` distance deltas;
    the middle one's smoothed gradient stays inside the validated range,
    the outer two exceed it in opposite directions. The expected count (2)
    is independently derived here by walking the same two production
    building blocks (:func:`grade.smoothed_altitude`,
    :func:`grade.running_cost_ratio`) the implementation under test must
    itself compose correctly -- not a hand-typed number that happens to
    match today's implementation. Replacing ``if clamped:
    clamped_intervals += 1`` with ``if False:`` (or hard-coding
    ``clamped_intervals=0``) must red this test.
    """
    time_s = (0.0, 1.0, 2.0, 3.0)
    distance_m: tuple[float, ...] = (0.0, 100.0, 200.0, 300.0)
    altitude_m: tuple[float, ...] = (100.0, 300.0, 310.0, 800.0)
    samples = _samples(time_s, distance_m, altitude_m)

    smoothed = grade.smoothed_altitude(altitude_m)
    expected_clamped = 0
    for i in range(len(distance_m) - 1):
        delta = distance_m[i + 1] - distance_m[i]
        a0, a1 = smoothed[i], smoothed[i + 1]
        assert a0 is not None and a1 is not None
        gradient = (a1 - a0) / delta
        _, clamped = grade.running_cost_ratio(gradient)
        if clamped:
            expected_clamped += 1
    # Sanity: the fixture must actually exercise a nontrivial, non-default
    # count, or this test cannot discriminate a broken counter.
    assert expected_clamped == 2
    assert expected_clamped not in (0, len(distance_m) - 1)

    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    assert result.clamped_intervals == 2
    assert result.clamped_intervals == expected_clamped


# ---------------------------------------------------------------------------
# 7.2, 7.3 -- smoothing before differencing, shared width and alignment
# ---------------------------------------------------------------------------


def test_smoothed_altitude_is_index_aligned_with_input() -> None:
    """Req 7.2, 7.3: unlike the shipped private helper this reuses the
    width and alignment of, ``smoothed_altitude`` emits one entry per input
    sample -- ``None`` where the trailing window holds nothing -- rather
    than compacting."""
    altitude: tuple[float | None, ...] = (None, None, 100.0, 102.0, 101.0)
    smoothed = grade.smoothed_altitude(altitude)
    assert len(smoothed) == len(altitude)
    assert smoothed[0] is None
    assert smoothed[1] is None
    assert smoothed[2] is not None


def test_smoothed_altitude_damps_a_lone_spike() -> None:
    """Req 7.2 observable: a single-sample altitude spike surrounded by
    flat, otherwise-constant readings is damped by the trailing boxcar
    smoothing -- the smoothed value at the spike is pulled well below the
    raw spike value, not equal to it."""
    flat = 100.0
    spike = 200.0
    altitude: tuple[float | None, ...] = (
        flat,
        flat,
        flat,
        flat,
        flat,
        spike,
        flat,
        flat,
        flat,
        flat,
    )
    spike_index = 5
    smoothed = grade.smoothed_altitude(altitude)
    smoothed_at_spike = smoothed[spike_index]
    assert smoothed_at_spike is not None
    assert smoothed_at_spike < spike
    # Damped substantially, not merely nudged: the raw jump is 100, the
    # smoothed jump over a width-10 trailing boxcar sampled here (6 samples
    # available: indices 0-5) must be far below it.
    assert smoothed_at_spike < flat + (spike - flat) / 2


def test_altitude_smoothing_window_reads_from_the_shared_metrics_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 7.3: the smoothing window width is bound from
    :data:`fitdocs.metrics.sources.ALTITUDE_SMOOTHING_WINDOW` -- the same
    record the shipped elevation metrics themselves read -- at import time,
    not a coincidentally-equal retyped literal.

    Follows the exact technique
    ``tests/metrics/test_aggregates.py::test_altitude_smoothing_window_is_read_from_its_record``
    uses for the shipped helper itself: swap the record for a materially
    different width, reload the module, and confirm the module constant (and
    therefore the smoothing behavior) tracks the swap.
    """
    original = metrics_sources.ALTITUDE_SMOOTHING_WINDOW
    mutated = dataclasses.replace(original, value=2)
    monkeypatch.setattr(metrics_sources, "ALTITUDE_SMOOTHING_WINDOW", mutated)
    importlib.reload(grade)
    try:
        assert grade.ALTITUDE_SMOOTHING_WINDOW == 2
        altitude: tuple[float | None, ...] = (100.0, 101.0, 100.0, 101.0)
        smoothed = grade.smoothed_altitude(altitude)
        # Width-2 trailing boxcar: (100, 100.5, 100.5, 100.5)
        assert smoothed == (100.0, 100.5, 100.5, 100.5)
    finally:
        monkeypatch.setattr(metrics_sources, "ALTITUDE_SMOOTHING_WINDOW", original)
        importlib.reload(grade)
    assert original.value == grade.ALTITUDE_SMOOTHING_WINDOW


def test_equivalent_distance_uses_smoothed_not_raw_altitude() -> None:
    """Req 7.2: pins the smoothing seam at its *consumer*, not just in
    isolation. ``test_smoothed_altitude_damps_a_lone_spike`` exercises
    :func:`grade.smoothed_altitude` on its own; a mutation that bypasses it
    entirely inside :func:`grade.equivalent_distance` (e.g. ``smoothed =
    tuple(samples.altitude_m)``, no smoothing at all) would still leave that
    isolated test green, because nothing else pins the *integration*.

    The fixture is longer than :data:`grade.ALTITUDE_SMOOTHING_WINDOW` (a
    lone spike surrounded by flat altitude, distance deltas well above
    :data:`grade.MIN_GRADIENT_DISTANCE_M`), so the smoothed and raw altitude
    series produce materially different results. Both halves are asserted:
    ``equivalent_distance_m`` equals the value independently computed from
    :func:`grade.smoothed_altitude`'s own output (pins *what* is used), and
    it differs from the value the raw, unsmoothed altitude would give (pins
    that smoothing *matters* here, not just that some value was reproduced).
    """
    n = grade.ALTITUDE_SMOOTHING_WINDOW + 3
    time_s = tuple(float(i) for i in range(n))
    distance_m: tuple[float, ...] = tuple(float(i * 10) for i in range(n))
    spike_index = 6
    altitude_list = [100.0] * n
    altitude_list[spike_index] = 140.0
    altitude_m: tuple[float, ...] = tuple(altitude_list)
    samples = _samples(time_s, distance_m, altitude_m)

    smoothed = grade.smoothed_altitude(altitude_m)
    expected_from_smoothed = 0.0
    for i in range(n - 1):
        delta = distance_m[i + 1] - distance_m[i]
        a0, a1 = smoothed[i], smoothed[i + 1]
        assert a0 is not None and a1 is not None
        gradient = (a1 - a0) / delta
        ratio, _ = grade.running_cost_ratio(gradient)
        expected_from_smoothed += delta * ratio

    expected_from_raw = 0.0
    for i in range(n - 1):
        delta = distance_m[i + 1] - distance_m[i]
        a0, a1 = altitude_m[i], altitude_m[i + 1]
        gradient = (a1 - a0) / delta
        ratio, _ = grade.running_cost_ratio(gradient)
        expected_from_raw += delta * ratio

    # Sanity: the fixture must make smoothing actually matter, or this test
    # cannot discriminate "smoothed" from "raw".
    assert expected_from_smoothed != pytest.approx(expected_from_raw)

    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    assert result.equivalent_distance_m == pytest.approx(expected_from_smoothed)
    assert result.equivalent_distance_m != pytest.approx(expected_from_raw)


def test_smoothed_altitude_agrees_with_shipped_helper_once_gaps_are_dropped() -> None:
    """Req 7.3: pins the trailing-alignment *convention* itself, not just
    the width, against the shipped private helper
    ``fitdocs.metrics.aggregates._smoothed_altitude`` -- which this module
    could not call directly because it is private and compacts its output
    (design.md's Implementation Notes). Dropping this module's ``None``
    entries must reproduce the shipped helper's compacted sequence exactly,
    for an altitude stream carrying a leading gap where the two shapes would
    otherwise diverge.

    The fixture is deliberately longer than
    ``grade.ALTITUDE_SMOOTHING_WINDOW`` (currently 10): with fewer samples
    than the window width, every trailing window starts at index 0
    regardless of an off-by-one in the window's lower bound, so a boundary
    (alignment) defect would go undetected against a short fixture. Once the
    series exceeds the window width, an off-by-one in the lower-bound
    computation (``i - window`` instead of ``i - window + 1``) changes which
    samples fall inside later windows and is caught here.
    """
    altitude: tuple[float | None, ...] = (
        None,
        None,
        100.0,
        None,
        102.0,
        103.0,
        101.5,
        None,
        100.5,
        104.0,
        105.5,
        103.0,
        106.0,
        107.5,
        102.5,
    )
    assert len(altitude) > grade.ALTITUDE_SMOOTHING_WINDOW, (
        "the fixture must be longer than the smoothing window, or a "
        "trailing-window boundary (alignment) defect goes unexercised"
    )
    ours = [v for v in grade.smoothed_altitude(altitude) if v is not None]
    shipped = metrics_aggregates._smoothed_altitude(altitude)  # noqa: SLF001
    assert ours == pytest.approx(shipped)
    assert ours, "the fixture produced no smoothed points -- strengthen it"


# ---------------------------------------------------------------------------
# 7.5 -- non-positive or too-small distance delta treated as level
# ---------------------------------------------------------------------------


def test_zero_distance_delta_treated_as_level() -> None:
    """Req 7.5: a zero recorded distance delta does not produce an extreme
    gradient -- the interval is treated as level (ratio 1.0)."""
    samples = _samples(
        time_s=(0.0, 1.0),
        distance_m=(0.0, 0.0),
        altitude_m=(100.0, 150.0),
    )
    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    assert result.equivalent_distance_m == result.raw_distance_m == 0.0
    assert result.clamped_intervals == 0


def test_negative_distance_delta_treated_as_level() -> None:
    """Req 7.5: a negative recorded distance delta (a device correction or
    GPS reset) is treated as level rather than producing an extreme
    gradient. The requirement's protected quantity is
    ``equivalent_distance_m`` ("rather than producing an extreme
    gradient") -- a value-equality assertion on ``raw_distance_m`` alone
    does not pin this, since a defect that computes the negative interval's
    gradient anyway (dividing by the signed, negative delta) and adds
    ``abs(delta) * ratio`` to ``equivalent_distance_m`` can still leave
    ``raw_distance_m`` matching by coincidence.

    The second interval's distance delta (``0.3``) is deliberately kept
    below :data:`grade.MIN_GRADIENT_DISTANCE_M` so *it* is independently
    forced level too, decoupling this fixture from altitude/smoothing
    arithmetic entirely: a correct implementation must report
    ``raw_distance_m == equivalent_distance_m`` exactly (both equal the
    lone positive delta) and ``clamped_intervals == 0``. The first
    interval's altitude jump (100 -> 500) is large enough that a defect
    processing it anyway would clamp -- so a wrong implementation reaches
    ``clamped_intervals >= 1``, a fixture-independent, non-zero, non-tied
    number, not merely a coincidentally-matching one.
    """
    samples = _samples(
        time_s=(0.0, 1.0, 2.0),
        distance_m=(100.0, 50.0, 50.3),
        altitude_m=(100.0, 500.0, 500.0),
    )
    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    # Only the second interval (50 -> 50.3, delta +0.3) is a positive
    # delta; the first interval's negative delta contributes nothing.
    assert result.raw_distance_m == pytest.approx(0.3)
    assert result.equivalent_distance_m == pytest.approx(result.raw_distance_m)
    assert result.clamped_intervals == 0


def test_small_distance_delta_below_minimum_treated_as_level() -> None:
    """Req 7.5: a positive but too-small distance delta (below
    :data:`grade.MIN_GRADIENT_DISTANCE_M`) is treated as level even though
    the recorded altitude delta over it would otherwise imply an extreme
    gradient."""
    small_delta = grade.MIN_GRADIENT_DISTANCE_M / 2
    samples = _samples(
        time_s=(0.0, 1.0),
        distance_m=(0.0, small_delta),
        altitude_m=(100.0, 150.0),
    )
    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    # Level (ratio 1.0): equivalent equals raw for this lone interval.
    assert result.equivalent_distance_m == pytest.approx(result.raw_distance_m)
    assert result.clamped_intervals == 0


def test_distance_delta_at_minimum_is_not_treated_as_level() -> None:
    """Req 7.5 boundary: a distance delta exactly at
    :data:`grade.MIN_GRADIENT_DISTANCE_M` is *not* below the minimum, so its
    gradient is derived and applied rather than forced level -- distinguishes
    a strict ``<`` comparison from an off-by-one ``<=``."""
    delta = grade.MIN_GRADIENT_DISTANCE_M
    # A steep, easily distinguishable-from-level climb over the minimum
    # displacement.
    samples = _samples(
        time_s=(0.0, 1.0),
        distance_m=(0.0, delta),
        altitude_m=(100.0, 100.0 + delta * 0.30),
    )
    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    assert result.equivalent_distance_m != pytest.approx(result.raw_distance_m)


def test_undefined_smoothed_altitude_endpoint_is_treated_as_level() -> None:
    """Coverage for the branch at ``a0 is None or a1 is None`` in
    :func:`grade.equivalent_distance` (see that module's own docstring,
    "Undefined smoothed altitude"): an interval whose distance delta clears
    :data:`grade.MIN_GRADIENT_DISTANCE_M` but whose smoothed altitude is
    undefined at either endpoint (unrecorded altitude reaching no window)
    is treated as level -- ``ratio == 1.0``, not clamped, not a crash.

    This is *not* one of Req 7.5's sanctioned level cases (those are all
    about the distance delta itself); it is documented separately as the
    module's own extension. Without the ``or a0 is None or a1 is None``
    guard, this exact fixture raises ``TypeError`` (``a1 - a0`` computes
    ``float`` minus ``None``, since ``a0`` -- the earlier endpoint here --
    is the undefined one) rather than merely producing a wrong number,
    since nothing else in the fixture forces the delta-based level branch
    first.
    """
    samples = _samples(
        time_s=(0.0, 1.0),
        distance_m=(0.0, 10.0),
        altitude_m=(None, 100.0),
    )
    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    assert result.raw_distance_m == 10.0
    assert result.equivalent_distance_m == pytest.approx(result.raw_distance_m)
    assert result.clamped_intervals == 0


# ---------------------------------------------------------------------------
# 7.7 -- untouched measured values; grade-equivalent alongside raw
# ---------------------------------------------------------------------------


def test_apply_grade_false_returns_raw_distance_exactly() -> None:
    """Req 7.6/7.7 observable: not applying the model returns the raw
    distance exactly, with the flag set to ``False``."""
    samples = _samples(
        time_s=(0.0, 1.0, 2.0),
        distance_m=(0.0, 100.0, 250.0),
        altitude_m=(100.0, 150.0, 100.0),
    )
    result = grade.equivalent_distance(samples, apply_grade=False)
    assert result is not None
    assert result.applied is False
    assert result.equivalent_distance_m == result.raw_distance_m
    assert result.note is not None


def test_grade_adjustment_differs_from_raw_under_a_real_gradient() -> None:
    """Req 7.7: the grade-equivalent distance is produced *alongside* the
    raw recorded distance, not in place of it -- when a real, sustained
    uphill gradient is present, ``equivalent_distance_m`` differs materially
    from ``raw_distance_m`` while ``raw_distance_m`` still equals the
    literal sum of the recorded positive distance deltas."""
    samples = _samples(
        time_s=(0.0, 1.0, 2.0, 3.0),
        distance_m=(0.0, 100.0, 200.0, 300.0),
        altitude_m=(100.0, 130.0, 160.0, 190.0),
    )
    result = grade.equivalent_distance(samples, apply_grade=True)
    assert result is not None
    assert result.raw_distance_m == 300.0
    assert result.equivalent_distance_m > result.raw_distance_m
    assert result.applied is True


def test_equivalent_distance_does_not_mutate_input_samples() -> None:
    """Req 7.7: no input array is mutated -- the caller's ``Samples`` (and
    its recorded distance and altitude channels specifically) are unchanged
    by the call."""
    distance = (0.0, 100.0, 200.0)
    altitude = (100.0, 130.0, 160.0)
    samples = _samples(time_s=(0.0, 1.0, 2.0), distance_m=distance, altitude_m=altitude)
    grade.equivalent_distance(samples, apply_grade=True)
    assert samples.distance_m == distance
    assert samples.altitude_m == altitude
    assert samples.distance_m is distance
    assert samples.altitude_m is altitude


def test_equivalent_distance_none_when_distance_cannot_be_derived() -> None:
    """Req 7.7 postcondition: with fewer than two samples (or an entirely
    unrecorded distance channel) ``equivalent_distance`` returns ``None``
    rather than fabricating a zero."""
    samples = _samples(time_s=(0.0,), distance_m=(0.0,), altitude_m=(100.0,))
    assert grade.equivalent_distance(samples, apply_grade=True) is None

    unrecorded = _samples(
        time_s=(0.0, 1.0, 2.0),
        distance_m=(None, None, None),
        altitude_m=(100.0, 130.0, 160.0),
    )
    assert grade.equivalent_distance(unrecorded, apply_grade=True) is None


# ---------------------------------------------------------------------------
# 7.8 -- kept separate from the pace channel's threshold-anchoring
# arithmetic
# ---------------------------------------------------------------------------


def test_module_imports_no_pace_or_threshold_anchoring_machinery() -> None:
    """Req 7.8: this module is kept separate from the pace channel's
    threshold-anchoring arithmetic, observable today (before the pace
    channel exists, task 3.3) as an import-level guard: nothing under this
    module's own import list names a pace, threshold, FTP, or benchmark
    module. Modeled directly on
    ``test_types.py::test_module_does_not_import_the_settings_reader``,
    including its own vacuity guard (``assert imported_names``), so an
    empty walk cannot pass this silently.

    This does not (and cannot yet) pin the *reverse* direction -- that the
    pace channel, once it exists, does not reach into this module's
    internals to build its own threshold arithmetic -- which is that future
    task's obligation, not observable from here.
    """
    tree = ast.parse(_MODULE_SOURCE)
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            resolved_module = "." * node.level + (node.module or "")
            imported_names.append(resolved_module)
            imported_names.extend(
                f"{resolved_module}.{alias.name}" for alias in node.names
            )
    assert imported_names, "the walk found no imports -- wrong module scanned"
    forbidden = re.compile(r"(^|\.)(pace|threshold|ftp|benchmark)", re.IGNORECASE)
    offenders = [name for name in imported_names if forbidden.search(name)]
    assert not offenders, (
        f"grade.py imports pace/threshold/FTP/benchmark machinery, "
        f"violating Req 7.8's separation from the pace channel's scale "
        f"contract: {offenders}"
    )


# ---------------------------------------------------------------------------
# 7.9 -- running only; walking form read but withheld as a scope choice
# ---------------------------------------------------------------------------


def test_no_walking_form_is_implemented() -> None:
    """Req 7.9: the module ships no walking-cost function or constant --
    the walking polynomial was read alongside the running one (Fig. 1's
    caption gives both) but is withheld by scope choice."""
    assert not hasattr(grade, "walking_cost_ratio")
    assert not hasattr(grade, "MINETTI_WALKING_COEFFICIENTS")


def test_docstring_states_scope_choice_not_a_sourcing_gap() -> None:
    """Req 7.9: the documentation records the *true*, corrected reason the
    walking form is unimplemented -- a scope decision, not because it "was
    not obtained" (the false wording Req 7.9's own amendment retired).

    A raw ``"not obtained" not in source`` substring check is defeated by
    line-wrap position alone: this module's docstring legitimately *quotes*
    the retired phrase while describing the amendment that retired it, and
    that quote happens to be split across a line break today
    (``"was not\nobtained"``), so the naive check currently passes by
    accident of formatting -- reflowing that one paragraph onto a single
    line (pure formatting, no content change) would flip the literal
    substring present and red this test for no real reason. Conversely, a
    genuinely false *new* sourcing claim inserted elsewhere and phrased with
    its own line break (e.g. ``"were not\nobtained from the paper"``) would
    slip past the naive check entirely.

    Whitespace is normalized first (so wrapping never matters), then the
    normalized text is split on sentence boundaries and, for every sentence
    containing ``"not obtained"``, that *same sentence* must also contain
    ``"now-false"`` and ``"amended"`` -- i.e. it is being quoted as Req
    7.9's retired wording, not asserted as a live fact. Sentence
    containment, not a fixed-width character window: a fixed-radius window
    (e.g. 200 characters after the occurrence) was tried first and proven
    unsound -- a false claim planted immediately after the legitimate
    amendment sentence inherits that sentence's own ``now-false`` /
    ``amended`` tokens through the window and passes, while the true axis
    of a planted false claim is *which sentence* it sits in, not how many
    characters away it is.
    """
    source = " ".join(inspect.getsource(grade).split())
    assert "scope choice" in source or "scope decision" in source

    phrase = "not obtained"
    sentences = re.split(r"(?<=\.)\s+", source)
    assert sentences, "the sentence split produced nothing -- wrong source scanned"
    offending = [
        sentence
        for sentence in sentences
        if phrase in sentence
        and not ("now-false" in sentence and "amended" in sentence)
    ]
    assert not offending, (
        f"a sentence contains '{phrase}' without also naming Req 7.9's "
        f"amendment (missing 'now-false' and/or 'amended' in the SAME "
        f"sentence) -- looks like a live (possibly false) sourcing claim "
        f"rather than a quote of the retired wording: {offending!r}"
    )
