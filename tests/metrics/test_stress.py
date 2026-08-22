"""Hand-computed tests for the generic training-stress metrics.

These exercise :mod:`fitdocs.metrics.stress`: Banister TRIMP over the heart-rate
channel and power TSS from an already-computed normalized power. Every expected
number below is hand-computed from the formulas ``stress.py``'s own module
docstring documents (values read from :mod:`fitdocs.metrics.sources`) so the
formulas are pinned exactly, not merely snapshotted (the lesson from task 5.4:
no loose bounds for formula-defining behaviour).

The invariants under test:

* **TRIMP (Banister)** -- per consecutive sample pair with ``dt > 0`` and the
  *earlier* sample's heart rate present:
  ``HRr = clamp((hr - rest) / (max - rest), 0, 1)`` and
  ``trimp += dt_min * HRr * c * exp(k * HRr)`` where
  ``dt_min = (time_s[i+1] - time_s[i]) / 60`` and ``c``/``k`` are the
  *caller-supplied* weighting pair's coefficient and exponent (Req 17.1) --
  :func:`~fitdocs.metrics.stress.trimp` takes that pair as an argument and
  resolves nothing itself (task 11; the resolution happens in the metrics
  facade, through :func:`fitdocs.metrics.sources.weighting_for`).
* **Clamped reserve** -- a heart rate below rest clamps ``HRr`` to 0 (that pair
  contributes nothing); above max clamps to 1.
* **Missing / invalid thresholds -> ``None``** -- no resting HR, no max HR, or a
  non-positive reserve (``max <= rest``) yields ``None``, never a fabricated 0,
  regardless of which weighting pair was supplied (Req 17.5).
* **Absent HR channel -> ``None``** -- an entirely unrecorded heart-rate channel
  yields ``None``, not ``0.0`` (Req 12.2): TRIMP depends on the HR channel.
* **The value never travels without its weighting (Req 17.6)** -- a successful
  call returns a :class:`~fitdocs.metrics.stress.TrimpResult` bundling the
  accumulated value with the supplied pair's own selection, not a bare float.
* **Power TSS** -- ``IF = np / ftp`` and
  ``TSS = moving_time_s * np * IF / (ftp * 3600) * scale`` (Req 11.2), where
  ``scale`` is ``100.0`` today; the canonical one-hour-at-FTP case is exactly
  ``100.0``.
* **Missing TSS inputs -> ``None``** -- absent NP, moving time, FTP, or a
  non-positive FTP yields ``None`` (Req 12.1).
* **No methodology load (Req 11.4)** -- the module carries only these two plain
  functions (plus private helpers) and the ``TrimpResult`` record; no
  ``LoadCalculator`` or methodology object.
* **Never raises (Req 12.1)** -- every missing-data path returns ``None``.
* **The TSS scale is read from its record (task 10.3; Req 11.2, 15.1, 15.5,
  15.6)** -- bound from :mod:`fitdocs.metrics.sources`, not a bare literal.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect

import pytest

from fitdocs import metrics
from fitdocs.metrics import sources, stress
from fitdocs.metrics.types import TrimpWeighting
from fitdocs.model import Samples

# The two registered weighting pairs, used throughout as caller-supplied
# arguments -- trimp() no longer resolves a default of its own (task 11).
_MALE_PAIR = sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_MALE]
_FEMALE_PAIR = sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_FEMALE]

# --- test-model builders ----------------------------------------------------


def _samples(
    time_s: tuple[float, ...] = (),
    *,
    heart_rate_bpm: tuple[int | None, ...] | None = None,
) -> Samples:
    """A ``Samples`` whose channels default to all-``None`` arrays of length
    ``len(time_s)``; pass ``heart_rate_bpm`` to populate the only channel TRIMP
    reads. Every other channel stays all-``None``.
    """
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm if heart_rate_bpm is not None else none_ints,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


# --- module wiring ----------------------------------------------------------


def test_module_imports_from_metrics_package() -> None:
    # stress lives under the metrics package (design File Structure Plan).
    assert stress is metrics.stress


# --- 1. TRIMP worked example, single + multi pair (Req 11.1) ----------------


def test_trimp_single_pair_worked_example() -> None:
    # rest=60, max=200 -> reserve = 140.
    # One pair: time_s (0, 60) -> dt = 60 s -> dt_min = 1.0; earlier HR = 130.
    #   HRr = (130 - 60) / 140 = 70/140 = 0.5
    #   term = dt_min * HRr * 0.64 * exp(1.92 * HRr)
    #        = 1.0 * 0.5 * 0.64 * exp(0.96)
    #        = 0.32 * 2.611696473423118
    #        = 0.8357428714953977
    samples = _samples((0.0, 60.0), heart_rate_bpm=(130, 999))
    # The later sample's HR (999) is deliberately absurd; it is NEVER used
    # because only the EARLIER sample of each pair is attributed.
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    assert result is not None
    assert result.value == pytest.approx(0.8357428714953977, rel=1e-12)
    # The value never travels without the pair that produced it (Req 17.6).
    assert result.weighting == TrimpWeighting.BANISTER_MALE


def test_trimp_multi_pair_accumulates_earlier_sample_hr() -> None:
    # rest=60, max=200 -> reserve = 140. time_s (0, 60, 90); HR (130, 165, 180).
    #   pair 0->1: dt = 60 s -> dt_min = 1.0 ; earlier HR = 130 -> HRr = 0.5
    #       term0 = 1.0  * 0.5  * 0.64 * exp(0.96) = 0.8357428714953977
    #   pair 1->2: dt = 30 s -> dt_min = 0.5 ; earlier HR = 165 -> HRr = 105/140 = 0.75
    #       term1 = 0.5  * 0.75 * 0.64 * exp(1.44) = 1.0129669960791725
    #   total = 1.8487098675745703
    # The final sample's HR (180) is present but has no outgoing pair, so it is
    # never attributed -- pinning both the accumulation and the earlier-sample
    # rule (a later-sample rule would use 165 and 180 instead of 130 and 165).
    samples = _samples((0.0, 60.0, 90.0), heart_rate_bpm=(130, 165, 180))
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    assert result is not None
    assert result.value == pytest.approx(1.8487098675745703, rel=1e-12)


# --- 2. TRIMP clamp of the heart-rate reserve (Req 11.1) --------------------


def test_trimp_below_rest_clamps_to_zero() -> None:
    # earlier HR (50) is below rest (60): raw reserve = (50-60)/140 < 0 -> clamp 0.
    # That pair contributes dt_min * 0 * 0.64 * exp(0) = 0 exactly.
    samples = _samples((0.0, 60.0), heart_rate_bpm=(50, 130))
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    assert result is not None
    assert result.value == 0.0


def test_trimp_above_max_clamps_to_one() -> None:
    # earlier HR (210) is above max (200): raw reserve = (210-60)/140 > 1 -> clamp 1.
    # dt = 60 s -> dt_min = 1.0, so term = 1.0 * 1.0 * 0.64 * exp(1.92)
    #   = 0.64 * 6.8209584692907494 = 4.36541342034608
    samples = _samples((0.0, 60.0), heart_rate_bpm=(210, 130))
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    assert result is not None
    assert result.value == pytest.approx(4.36541342034608, rel=1e-12)


# --- 2b. TRIMP reads the SUPPLIED pair, not a hard-wired curve (Req 17.1) ----


def test_trimp_uses_the_coefficient_and_exponent_of_the_supplied_pair() -> None:
    """The male and female pairs produce numerically different results for the
    identical samples and thresholds -- pinning that :func:`stress.trimp`
    reads ``weighting.coefficient.value`` / ``weighting.exponent.value`` off
    whichever :class:`~fitdocs.metrics.sources.WeightingPair` it is given,
    rather than a curve fixed inside the function. A hard-wired
    ``WEIGHTING_PAIRS[TrimpWeighting.BANISTER_MALE]`` (the exact trap 10.3's
    mutation-discrimination note warns about for this task) would return the
    same value for both calls below and fail this test.
    """
    samples = _samples((0.0, 60.0), heart_rate_bpm=(130, 999))
    male = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    female = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_FEMALE_PAIR)
    assert male is not None
    assert female is not None
    # rest=60, max=200 -> HRr = 0.5 (as above).
    # male:   1.0 * 0.5 * 0.64 * exp(1.92 * 0.5) = 0.8357428714953977
    # female: 1.0 * 0.5 * 0.86 * exp(1.67 * 0.5) = 0.9910700407634154
    assert male.value == pytest.approx(0.8357428714953977, rel=1e-12)
    assert female.value == pytest.approx(0.9910700407634154, rel=1e-12)
    assert male.value != female.value
    assert male.weighting == TrimpWeighting.BANISTER_MALE
    assert female.weighting == TrimpWeighting.BANISTER_FEMALE


def test_trimp_result_weighting_matches_the_supplied_pairs_selection_field() -> None:
    """A mutation that computed the right arithmetic but always reported
    ``TrimpWeighting.BANISTER_MALE`` on the returned :class:`TrimpResult`
    (rather than ``weighting.selection``) would pass every *value* assertion
    in this file yet report the wrong pairing (Req 17.6).

    This does not discriminate anything the preceding test does not: that
    mutation reds its ``female.weighting`` assertion too, and no mutation run
    for this task has failed this test alone. It is kept because it states the
    17.6 pairing claim on its own -- one supplied pair, the selection read back
    off the :class:`TrimpResult` -- rather than as the last two lines of a test
    whose subject is the arithmetic.
    """
    samples = _samples((0.0, 60.0), heart_rate_bpm=(130, 999))
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_FEMALE_PAIR)
    assert result is not None
    assert result.weighting == TrimpWeighting.BANISTER_FEMALE
    assert result.weighting == _FEMALE_PAIR.selection


# --- 3. TRIMP missing / invalid thresholds -> None (Req 11.1, 17.5) ---------


def test_trimp_none_resting_hr_returns_none() -> None:
    samples = _samples((0.0, 60.0), heart_rate_bpm=(130, 140))
    assert (
        stress.trimp(samples, resting_hr=None, max_hr=200, weighting=_MALE_PAIR) is None
    )


def test_trimp_none_max_hr_returns_none() -> None:
    samples = _samples((0.0, 60.0), heart_rate_bpm=(130, 140))
    assert (
        stress.trimp(samples, resting_hr=60, max_hr=None, weighting=_MALE_PAIR) is None
    )


def test_trimp_non_positive_reserve_returns_none() -> None:
    # max <= rest -> reserve <= 0 -> division would be by zero / negative; None.
    samples = _samples((0.0, 60.0), heart_rate_bpm=(130, 140))
    assert (
        stress.trimp(samples, resting_hr=200, max_hr=200, weighting=_MALE_PAIR) is None
    )  # reserve == 0
    assert (
        stress.trimp(samples, resting_hr=200, max_hr=150, weighting=_MALE_PAIR) is None
    )  # reserve < 0


def test_trimp_missing_thresholds_return_none_under_every_weighting() -> None:
    """Req 17.5: absent resting/max HR yields ``None`` *regardless* of which
    weighting was supplied -- pinned against both registered pairs, not just
    the one the other tests in this file happen to use, so a bug that only
    checked the thresholds for one particular pair (e.g. reading them off
    ``weighting`` itself, which carries no threshold data at all) cannot hide
    behind an untested pair.
    """
    samples = _samples((0.0, 60.0), heart_rate_bpm=(130, 140))
    for pair in (_MALE_PAIR, _FEMALE_PAIR):
        assert (
            stress.trimp(samples, resting_hr=None, max_hr=200, weighting=pair) is None
        )
        assert stress.trimp(samples, resting_hr=60, max_hr=None, weighting=pair) is None


# --- 4. TRIMP absent HR channel -> None, NOT 0.0 (Req 12.2) -----------------


def test_trimp_absent_hr_channel_returns_none() -> None:
    # Thresholds supplied, but the HR channel is entirely unrecorded -> None
    # (a metric depending on an absent channel is None, never a fabricated 0.0).
    samples = _samples((0.0, 60.0, 120.0), heart_rate_bpm=(None, None, None))
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    # None, NOT a fabricated 0.0 (Req 12.2): the metric depends on the HR channel.
    assert result is None
    assert result != 0.0


def test_trimp_empty_samples_returns_none() -> None:
    # No samples at all -> no qualifying pair -> None (not 0.0).
    assert (
        stress.trimp(_samples(()), resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
        is None
    )


def test_trimp_skips_pairs_with_none_earlier_hr_but_uses_present_ones() -> None:
    # Only the middle pair has a present earlier HR; the others are skipped, so
    # the result is that single pair's contribution -- not None (some HR exists)
    # and not a sum polluted by the None-earlier pairs.
    #   time_s (0, 60, 120, 180); HR (None, 130, None, 999)
    #   pair 0->1: earlier HR None -> skipped
    #   pair 1->2: earlier HR 130 -> HRr 0.5, dt_min 1.0 -> 0.8357428714953977
    #   pair 2->3: earlier HR None -> skipped
    samples = _samples((0.0, 60.0, 120.0, 180.0), heart_rate_bpm=(None, 130, None, 999))
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    assert result is not None
    assert result.value == pytest.approx(0.8357428714953977, rel=1e-12)


def test_trimp_skips_non_positive_dt_pairs() -> None:
    # A duplicated timestamp gives dt == 0 for that pair -> it is skipped, so the
    # result equals the one qualifying pair. time_s (0, 0, 60); HR (130, 999, 999)
    #   pair 0->1: dt 0 -> skipped
    #   pair 1->2: dt 60 -> dt_min 1.0, earlier HR 999 -> clamp 1 -> 0.64*exp(1.92)
    samples = _samples((0.0, 0.0, 60.0), heart_rate_bpm=(130, 999, 130))
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=_MALE_PAIR)
    assert result is not None
    assert result.value == pytest.approx(4.36541342034608, rel=1e-12)


# --- 5. power TSS: one-hour-at-FTP and a hand-computed off-threshold case ----


def test_power_tss_one_hour_at_ftp_is_exactly_100() -> None:
    # NP == FTP == 250, moving_time == 3600 s (one hour):
    #   IF  = 250 / 250 = 1.0
    #   TSS = 3600 * 250 * 1.0 / (250 * 3600) * 100 = 100.0  (exact)
    assert stress.power_tss(np_w=250.0, moving_time_s=3600.0, ftp=250.0) == 100.0


def test_power_tss_off_threshold_hand_computed() -> None:
    # NP 200, FTP 250, moving_time 3600 s:
    #   IF  = 200/250 = 0.8
    #   TSS = 3600 * 200 * 0.8 / (250 * 3600) * 100
    #       = (200 * 0.8 * 100) / 250 = 16000 / 250 = 64.0
    assert stress.power_tss(
        np_w=200.0, moving_time_s=3600.0, ftp=250.0
    ) == pytest.approx(64.0, rel=1e-12)


def test_power_tss_half_hour_at_ftp_is_50() -> None:
    # NP == FTP == 250, moving_time == 1800 s (half hour):
    #   TSS = 1800 * 250 * 1.0 / (250 * 3600) * 100 = 1800/3600 * 100 = 50.0
    assert stress.power_tss(
        np_w=250.0, moving_time_s=1800.0, ftp=250.0
    ) == pytest.approx(50.0, rel=1e-12)


# --- 6. power TSS missing / invalid inputs -> None (Req 11.2, 12.1) ---------


def test_power_tss_none_np_returns_none() -> None:
    assert stress.power_tss(np_w=None, moving_time_s=3600.0, ftp=250.0) is None


def test_power_tss_none_moving_time_returns_none() -> None:
    assert stress.power_tss(np_w=250.0, moving_time_s=None, ftp=250.0) is None


def test_power_tss_none_ftp_returns_none() -> None:
    assert stress.power_tss(np_w=250.0, moving_time_s=3600.0, ftp=None) is None


def test_power_tss_non_positive_ftp_returns_none() -> None:
    assert stress.power_tss(np_w=250.0, moving_time_s=3600.0, ftp=0.0) is None
    assert stress.power_tss(np_w=250.0, moving_time_s=3600.0, ftp=-250.0) is None


# --- 7. no methodology load (Req 11.4) --------------------------------------


def test_module_has_only_the_two_generic_functions() -> None:
    # The public surface is exactly the two plain functions; no LoadCalculator.
    public = {
        name
        for name, obj in inspect.getmembers(stress, inspect.isfunction)
        if obj.__module__ == stress.__name__ and not name.startswith("_")
    }
    assert public == {"trimp", "power_tss"}


def test_module_carries_no_methodology_code() -> None:
    # Structural guard (Req 11.4): stress.py is generic derived-metric math
    # only. Inspect real code identifiers via the AST -- NOT raw source text --
    # so the docstring may document the boundary (fitdocs ships no methodology)
    # while the executable code carries no methodology object at all.
    tree = ast.parse(inspect.getsource(stress))
    identifiers = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    identifiers |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    identifiers |= {
        n.name
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    for banned in ("LoadCalculator", "points"):
        assert banned not in identifiers
    # Exactly one class is defined: TrimpResult, a plain value-carrying record
    # (Req 17.6), not a LoadCalculator or any methodology object -- pinned by
    # name so a future LoadCalculator-shaped class added alongside it reddens
    # this test rather than silently passing because *some* class exists.
    class_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert class_names == {"TrimpResult"}


def test_module_imports_only_model_sources_and_stdlib() -> None:
    # Dependency direction (design "Allowed Dependencies"): stress imports
    # fitdocs.model, fitdocs.metrics.sources (intra-metrics reuse is allowed),
    # and stdlib only -- never ingest, the FIT SDK, or the sibling power /
    # aggregates modules. Checked via the AST import nodes, not the
    # docstring (which names those modules to explain the boundary).
    #
    # Every import name in the module is collected first (not just the
    # ``fitdocs``-prefixed ones), so a stray FIT-SDK or stdlib import is
    # still visible to the assertions below even though it is not part of
    # the ``fitdocs_imports`` equality pin. ``fitdocs_imports`` then narrows
    # to full dotted names (``module.alias``, e.g. "fitdocs.metrics.sources")
    # rather than just ``node.module`` -- a bare ``node.module`` check cannot
    # tell ``from fitdocs.metrics import sources`` apart from ``from
    # fitdocs.metrics import power``, since both share the same ``module``
    # ("fitdocs.metrics") and differ only in the imported name. Relative
    # ``ImportFrom`` nodes (``node.level > 0``, e.g. ``from . import power``)
    # are resolved against this module's own package (``fitdocs.metrics``)
    # the same way ``test_sources.py``'s internal-import guard does -- a
    # collector that only handled absolute imports would give ``node.module
    # is None`` for a relative sibling import and silently drop it.
    tree = ast.parse(inspect.getsource(stress))
    own_package_parts = ["fitdocs", "metrics"]
    all_imports: set[str] = set()
    fitdocs_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                module = node.module or ""
            else:
                trim = len(own_package_parts) - (node.level - 1)
                base_parts = own_package_parts[:trim]
                extra = [node.module] if node.module else []
                module = ".".join(base_parts + extra)
            for alias in node.names:
                dotted = f"{module}.{alias.name}" if module else alias.name
                all_imports.add(dotted)
                if dotted.startswith("fitdocs"):
                    fitdocs_imports.add(dotted)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                all_imports.add(alias.name)
                if alias.name.startswith("fitdocs"):
                    fitdocs_imports.add(alias.name)
    assert fitdocs_imports == {
        "fitdocs.model.Samples",
        "fitdocs.metrics.sources",
        "fitdocs.metrics.types.TrimpWeighting",
    }
    assert not any("ingest" in name for name in all_imports)
    assert not any("garmin" in name for name in all_imports)
    assert "fitdocs.metrics.power" not in fitdocs_imports
    assert "fitdocs.metrics.aggregates" not in fitdocs_imports
    # The module docstring's "standard library only" claim (task 10.3, revised
    # task 11) is checkable here directly against the non-fitdocs imports
    # already collected above -- rather than leaving it as an assertion
    # nothing can red. ``typing`` (``Final``), ``__future__`` (``annotations``)
    # and ``dataclasses`` (``TrimpResult``, task 11) are named explicitly here
    # (not swallowed into a bare "stdlib" allowance) so a genuinely new stdlib
    # import (e.g. ``os``) still reds this test.
    allowed_non_fitdocs_modules = {"math", "typing", "__future__", "dataclasses"}
    non_stdlib_non_fitdocs = {
        name
        for name in all_imports
        if not name.startswith("fitdocs")
        and name.split(".")[0] not in allowed_non_fitdocs_modules
    }
    assert non_stdlib_non_fitdocs == set(), non_stdlib_non_fitdocs


# --- 8. constants read from their records, not bare literals (task 10.3;
#         Req 11.1, 11.2, 15.1, 15.5, 15.6) ----------------------------------


def _numeric_constants_in_source(module: object) -> list[int | float]:
    """Every bare ``int``/``float`` literal an AST walk finds in ``module``'s
    own source text (booleans excluded -- ``bool`` is an ``int`` subclass in
    Python and ``True``/``False`` carry no methodological weight here)."""
    tree = ast.parse(inspect.getsource(module))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ]


def test_module_source_has_no_bare_trimp_or_tss_scale_literal() -> None:
    """The training-impulse coefficient (historically the bare literal
    ``0.64``), the exponent (historically ``1.92``), and the TSS scale
    (historically ``100.0``) must all be read from their records
    (:mod:`fitdocs.metrics.sources`), not re-declared inline.

    Non-vacuous: the module carries plenty of OTHER numeric literals (``0.0``,
    ``1.0``, ``60.0``, ``3600.0``, loop bounds, ...), so this first asserts the
    walk actually visited a non-trivial number of constants, and that it is
    scanning THIS module rather than some other one, before checking that none
    of the three historical values is among them -- a walk that silently found
    nothing, or was pointed at the wrong module, would pass for the wrong
    reason.
    """
    assert stress.__name__ == "fitdocs.metrics.stress"  # scanning THIS module
    constants = _numeric_constants_in_source(stress)
    assert len(constants) > 5, (
        f"AST walk over {stress.__name__} found suspiciously few numeric "
        f"constants ({constants!r}); the scan may not be reaching the module body"
    )
    assert 0.64 not in constants
    assert 1.92 not in constants
    assert 100.0 not in constants


def test_module_source_does_not_name_the_working_reference_document() -> None:
    """Req 15.5: no constant in this module may be cited to
    ``docs/reference/fitdocs-ai-reference.md``, or any other working document
    under ``docs/reference/``, as its source -- not even in a docstring."""
    source = inspect.getsource(stress)
    assert "docs/reference" not in source
    assert "fitdocs-ai-reference" not in source


def test_tss_scale_is_read_from_its_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Req 11.2, 15.1: the TSS scale is bound from
    :data:`fitdocs.metrics.sources.TSS_SCALE` at import time -- not a
    coincidentally-equal literal.

    ``100.0`` is both the shipped record value and the historical bare
    literal, so this test swaps the record for ``50.0`` and confirms the
    canonical one-hour-at-FTP case (``np_w == ftp == 250.0``,
    ``moving_time_s == 3600.0``) -- which cancels every term except the scale
    itself -- now returns exactly ``50.0`` rather than the shipped ``100.0``.
    """
    original = sources.TSS_SCALE
    mutated = dataclasses.replace(original, value=50.0)
    monkeypatch.setattr(sources, "TSS_SCALE", mutated)
    importlib.reload(stress)
    try:
        assert stress._TSS_SCALE == 50.0
        result = stress.power_tss(np_w=250.0, moving_time_s=3600.0, ftp=250.0)
        assert result == 50.0
    finally:
        monkeypatch.setattr(sources, "TSS_SCALE", original)
        importlib.reload(stress)
    assert original.value == stress._TSS_SCALE


# --- 9. never raises for missing data (Req 12.1) ----------------------------


def test_missing_data_paths_never_raise() -> None:
    # None of the missing-data paths raise -- they all return None cleanly.
    assert (
        stress.trimp(_samples(()), resting_hr=None, max_hr=None, weighting=_MALE_PAIR)
        is None
    )
    assert (
        stress.trimp(_samples((0.0,), heart_rate_bpm=(130,)), 60, 200, _MALE_PAIR)
        is None
    )
    assert stress.power_tss(None, None, None) is None
    assert stress.power_tss(0.0, 0.0, 0.0) is None
