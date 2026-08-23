"""Tests for the substitutable heart-rate weighting seam (``weighting.py``).

Covers Requirements 5.4, 5.5, 5.6, 5.7, 5.8, 8.6, 9.8 -- see
``.kiro/specs/load-channels/requirements.md`` and the "Domain --
src/fitdocs/load/channels/weighting.py" / "HeartRateIntensityModel" component
in design.md (lines 751-824; ``#### HeartRateIntensityModel`` heading -- cite
the heading over the line range when following this pointer by hand, since
any future edit above this section shifts the range again exactly as this
task's own design.md amendment did).

**Worked example, computed not transcribed.** ``docs/reference/banister-trimp-
primary-sources.md`` section D4 records the standing ruling: Banister
(1991)'s own printed worked examples (Figs. 9.5-9.6 captions) disagree with
the equation on p. 408 by 8%-370% and are not usable as test vectors. D4
itself states no page number for those captions, so this module cites D4
alone rather than a page range that does not resolve against the primary
text. Every worked-example value in this module is therefore computed from
the formula itself -- reading the coefficient and exponent off the
production registry (:func:`fitdocs.metrics.sources.weighting_for`) rather
than hardcoding either -- and labelled as such, never transcribed from a
caption.
"""

from __future__ import annotations

import ast
import inspect
import math
import types
from collections.abc import Mapping
from dataclasses import fields

import pytest

from fitdocs.load.channels import weighting
from fitdocs.load.channels.weighting import (
    BANISTER_TRIMP_MODEL,
    BanisterTrimpModel,
    HeartRateIntensityModel,
    _one_hour_at,
)
from fitdocs.metrics import sources as metrics_sources
from fitdocs.metrics.stress import TrimpResult, trimp
from fitdocs.model import Samples

# ---------------------------------------------------------------------------
# fixture builders
# ---------------------------------------------------------------------------


def _samples(
    time_s: tuple[float, ...], heart_rate_bpm: tuple[int | None, ...]
) -> Samples:
    n = len(time_s)
    none_ints: tuple[int | None, ...] = (None,) * n
    none_floats: tuple[float | None, ...] = (None,) * n
    return Samples(
        time_s=time_s,
        heart_rate_bpm=heart_rate_bpm,
        power_w=none_ints,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )


def _expected_hourly_impulse(heart_rate: int, resting_hr: int, max_hr: int) -> float:
    """The one-hour-at-``heart_rate`` impulse, computed from the formula
    extracted off the production registry (not hardcoded), per the module
    docstring's construction: a single 3600 s interval integrated at a
    constant heart-rate-reserve ratio."""
    pair = metrics_sources.weighting_for(None)
    c = pair.coefficient.value
    k = pair.exponent.value
    hrr = (heart_rate - resting_hr) / (max_hr - resting_hr)
    return 60.0 * hrr * c * math.exp(k * hrr)


# ---------------------------------------------------------------------------
# 5.4 -- activity impulse delegates to the shipped metric, unchanged
# ---------------------------------------------------------------------------


def test_activity_impulse_equals_shipped_trimp_for_the_same_inputs() -> None:
    """A worked example (60 min steady at 150 bpm, rest 40, max 190),
    computed once through the shipped ``trimp`` directly and once through
    the seam -- the two must agree exactly, since the seam's whole job is
    delegation (Req 5.4)."""
    samples = _samples((0.0, 3600.0), (150, 150))
    weighting_pair = metrics_sources.weighting_for(None)
    direct = trimp(samples, resting_hr=40, max_hr=190, weighting=weighting_pair)
    assert direct is not None

    via_seam = BanisterTrimpModel().activity_impulse(samples, resting_hr=40, max_hr=190)
    assert via_seam == pytest.approx(direct.value)
    # And the worked value itself, extracted from the formula rather than
    # transcribed:
    assert via_seam == pytest.approx(_expected_hourly_impulse(150, 40, 190))


def test_activity_impulse_is_none_for_an_entirely_unrecorded_heart_rate_channel() -> (
    None
):
    """The shipped metric's ``None`` passthrough for an unrecorded channel
    must survive delegation unchanged -- a reimplementation that fabricates
    ``0.0`` instead would violate the "absent data is ``None``" rule."""
    samples = _samples((0.0, 60.0, 120.0), (None, None, None))
    assert (
        BanisterTrimpModel().activity_impulse(samples, resting_hr=40, max_hr=190)
        is None
    )


def test_activity_impulse_calls_trimp_once_with_the_callers_exact_samples_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the CALL PATH, not just the returned value (Req 5.4): a second,
    independent TRIMP integration that never calls
    :func:`fitdocs.metrics.stress.trimp` can still return the right number
    by coincidence on one fixture -- it cannot make ``trimp`` itself get
    called. Monkeypatches the module-level ``trimp`` name
    ``weighting.py`` calls and asserts it was invoked exactly once, with
    the caller's *exact* ``Samples`` object (``is``, not just ``==``), the
    given thresholds, and the pair :func:`weighting_for(None) <fitdocs.
    metrics.sources.weighting_for>` resolves; and that its return value
    passes through unmodified."""
    calls: list[tuple[Samples, int, int, metrics_sources.WeightingPair]] = []
    expected_pair = metrics_sources.weighting_for(None)
    sentinel = TrimpResult(value=99.0, weighting=expected_pair.selection)

    def fake_trimp(
        samples: Samples,
        resting_hr: int,
        max_hr: int,
        weighting_pair: metrics_sources.WeightingPair,
    ) -> TrimpResult:
        calls.append((samples, resting_hr, max_hr, weighting_pair))
        return sentinel

    monkeypatch.setattr(weighting, "trimp", fake_trimp)

    samples = _samples((0.0, 3600.0), (150, 150))
    result = BanisterTrimpModel().activity_impulse(samples, resting_hr=40, max_hr=190)

    assert len(calls) == 1
    called_samples, called_resting_hr, called_max_hr, called_pair = calls[0]
    assert called_samples is samples
    assert called_resting_hr == 40
    assert called_max_hr == 190
    assert called_pair == expected_pair
    assert result == 99.0


# ---------------------------------------------------------------------------
# 5.5 -- the one-hour reference goes through the same shipped function
# ---------------------------------------------------------------------------


def test_hourly_impulse_at_equals_trimp_scored_over_the_synthetic_series() -> None:
    """The reference is not an independent formula: it must equal
    ``trimp`` called directly over the exact synthetic series the module
    documents (Req 5.5)."""
    synthetic = _samples((0.0, 3600.0), (150, 150))
    weighting_pair = metrics_sources.weighting_for(None)
    direct = trimp(synthetic, resting_hr=40, max_hr=190, weighting=weighting_pair)
    assert direct is not None

    via_seam = BanisterTrimpModel().hourly_impulse_at(150, resting_hr=40, max_hr=190)
    assert via_seam == pytest.approx(direct.value)


def test_hourly_impulse_at_calls_trimp_with_the_one_hour_synthetic_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the CALL PATH, not just the returned value (Req 5.5): a
    restated closed form -- no ``trimp`` call, no ``_one_hour_at`` call --
    can still reproduce the right *number* for one fixture. Monkeypatches
    the module-level ``trimp`` name and asserts it was invoked exactly
    once, with a ``Samples`` whose ``time_s == (0.0, 3600.0)`` and
    ``heart_rate_bpm == (150, 150)`` -- the synthetic series
    :func:`_one_hour_at` documents -- and that the double's return value is
    what comes back unmodified."""
    calls: list[Samples] = []
    expected_pair = metrics_sources.weighting_for(None)
    sentinel = TrimpResult(value=77.0, weighting=expected_pair.selection)

    def fake_trimp(
        samples: Samples,
        resting_hr: int,
        max_hr: int,
        weighting_pair: metrics_sources.WeightingPair,
    ) -> TrimpResult:
        calls.append(samples)
        return sentinel

    monkeypatch.setattr(weighting, "trimp", fake_trimp)

    result = BanisterTrimpModel().hourly_impulse_at(150, resting_hr=40, max_hr=190)

    assert len(calls) == 1
    assert calls[0].time_s == (0.0, 3600.0)
    assert calls[0].heart_rate_bpm == (150, 150)
    assert result == 77.0


def test_one_hour_at_builds_a_single_3600_second_interval_carrying_the_heart_rate() -> (
    None
):
    """Pins the synthetic construction itself (Req 5.5): two samples, an
    offset span of exactly one hour, the heart rate present at the earlier
    (governing) sample, and every other channel unrecorded."""
    built = _one_hour_at(150)
    assert built.time_s == (0.0, 3600.0)
    assert built.heart_rate_bpm == (150, 150)
    assert built.power_w == (None, None)
    assert built.altitude_m == (None, None)


def test_hourly_impulse_at_is_strictly_positive_for_valid_inputs() -> None:
    """Req 5.5's postcondition: strictly positive whenever the
    preconditions (resting < heart_rate <= max) hold."""
    value = BanisterTrimpModel().hourly_impulse_at(150, resting_hr=40, max_hr=190)
    assert value is not None
    assert value > 0.0


def test_hourly_impulse_at_is_none_for_a_non_positive_reserve() -> None:
    """The absent-data rule (``None`` never a fabricated ``0``): a
    non-positive reserve (``max_hr <= resting_hr``) is exactly the case the
    shipped ``trimp`` returns ``None`` for, and that ``None`` must survive
    delegation unchanged rather than being replaced by a fabricated
    ``0.0``. Mirrors the existing ``activity_impulse`` ``None`` guard,
    which this seam's ``hourly_impulse_at`` previously had no
    counterpart for."""
    assert (
        BanisterTrimpModel().hourly_impulse_at(150, resting_hr=190, max_hr=190) is None
    )


# ---------------------------------------------------------------------------
# 5.6 / 8.6 -- no coefficient restated, and consumed from the single place
# ---------------------------------------------------------------------------


def _disputed_weighting_values() -> set[float]:
    """Both sexes' coefficient and exponent, read off the registry rather
    than hardcoded here -- shared by the structural and textual guards
    below so the two axes check the same set."""
    disputed_values: set[float] = set()
    for pair in metrics_sources.WEIGHTING_PAIRS.values():
        disputed_values.add(pair.coefficient.value)
        disputed_values.add(pair.exponent.value)
    assert len(disputed_values) >= 4, (
        "expected both sexes' coefficient and exponent -- registry shrank?"
    )
    return disputed_values


def test_module_has_no_literal_equal_to_any_registered_weighting_value() -> None:
    """Structural (Req 5.6, 8.6): parses the module with ``ast`` and
    asserts no numeric literal *as code* -- a constant, a default, an
    argument -- anywhere in its source equals any coefficient or exponent
    value registered in :data:`fitdocs.metrics.sources.WEIGHTING_PAIRS`,
    for **every** sex the registry defines, immune to how the literal is
    spelled (``6.4e-1`` and ``0.64`` parse to the identical
    ``ast.Constant``). This test's own scope is the syntax tree only: an
    ``ast.Constant`` walk cannot see a value written into a comment or a
    docstring -- that is
    :func:`test_module_source_text_names_no_disputed_value_in_any_spelling`
    below's job, kept as a second, independent scan rather than folded into
    or replacing this one, because the two axes (code vs. prose) are not
    reducible to each other."""
    tree = ast.parse(inspect.getsource(weighting))
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    assert literals, "the walk saw no numeric literal at all -- vacuous walk"

    assert literals.isdisjoint(_disputed_weighting_values())


def test_module_source_text_names_no_disputed_value_in_any_spelling() -> None:
    """Textual (Req 5.6, 8.6) -- kept *alongside* the ast scan above, not in
    its place: ``ast.Constant`` walks the parsed syntax tree and cannot see
    a value written into a comment or a docstring, which is exactly where a
    disputed coefficient/exponent can still leak even with the structural
    guard in place. This is what backs ``weighting.py``'s own module
    docstring commitment that it restates the disputed pair "not even in
    prose". Scans the raw source text -- code, comments and docstrings
    alike -- for every disputed value's plain and ``:g``-formatted string
    spelling, both sexes."""
    source = inspect.getsource(weighting)
    for value in _disputed_weighting_values():
        for spelling in (f"{value}", f"{value:g}"):
            assert spelling not in source, (
                f"{value!r} (spelled {spelling!r}) appears in weighting.py's "
                "source text -- restates a disputed training-impulse "
                "coefficient or exponent, even if only in a comment or "
                "docstring"
            )


def test_shipped_stress_module_is_byte_identical_to_its_pre_task_hash() -> None:
    """Req 9.8: this task edits no line of ``metrics/stress.py``. Pinned by
    content hash rather than by review, so an edit to that file --
    including one that happens to preserve behavior -- fails this test."""
    import hashlib

    from fitdocs.metrics import stress

    source_path = inspect.getsourcefile(stress)
    assert source_path is not None
    with open(source_path, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    assert digest == "432e0add5f5451e7c6c331d663ef2c2e40d0cffa9a0def5a7f3dec7c76b3c563"


# ---------------------------------------------------------------------------
# 5.7 -- the substitutable Protocol shape
# ---------------------------------------------------------------------------


def _protocol_member_names(protocol: type) -> set[str]:
    """The union of ``dir()`` and ``__annotations__`` walked over
    ``__mro__`` -- ``dir()`` alone omits annotation-only Protocol members
    (a peer session proved a purity guard blind to exactly this)."""
    names: set[str] = {n for n in dir(protocol) if not n.startswith("_")}
    for klass in protocol.__mro__:
        names.update(
            n for n in getattr(klass, "__annotations__", {}) if not n.startswith("_")
        )
    return names


def test_protocol_defines_exactly_model_id_activity_impulse_and_hourly_impulse_at() -> (
    None
):
    assert _protocol_member_names(HeartRateIntensityModel) == {
        "model_id",
        "activity_impulse",
        "hourly_impulse_at",
    }


def test_banister_trimp_model_implements_every_protocol_member() -> None:
    instance = BanisterTrimpModel()
    assert isinstance(instance.model_id, str)
    assert callable(instance.activity_impulse)
    assert callable(instance.hourly_impulse_at)


# ---------------------------------------------------------------------------
# 5.8 -- exactly one implementation, no registry, no configuration key
# ---------------------------------------------------------------------------


def test_module_public_surface_is_exactly_the_seam_and_its_one_implementation() -> None:
    """No second implementer, no registry object, no configuration-key
    constant is exported (Req 5.8): the module's public names are exactly
    this fixed set. Adding any additional public name -- a registry dict, a
    second model class, a selector constant -- reds this test."""
    public_names = {name for name in vars(weighting) if not name.startswith("_")}
    assert public_names == {
        "HeartRateIntensityModel",
        "BanisterTrimpModel",
        "BANISTER_TRIMP_MODEL",
        "annotations",  # from `from __future__ import annotations`
        "dataclass",
        "Final",
        "Protocol",
        "metrics_sources",
        "trimp",
        "Samples",
    }


def test_module_defines_exactly_one_class_implementing_both_protocol_methods() -> None:
    """Structural: scans **every** name in the module's namespace, public
    or private, for a class carrying both ``activity_impulse`` and
    ``hourly_impulse_at`` callables -- so a second implementer smuggled in
    under a private (underscore-prefixed) name, which the public-surface
    pin above cannot see, is still caught (Req 5.8)."""
    implementers = [
        obj
        for obj in vars(weighting).values()
        if isinstance(obj, type)
        and not getattr(obj, "_is_protocol", False)
        and callable(getattr(obj, "activity_impulse", None))
        and callable(getattr(obj, "hourly_impulse_at", None))
    ]
    assert implementers == [BanisterTrimpModel]


def test_module_holds_no_multi_key_mapping_and_no_extra_module_level_function() -> None:
    """Req 5.8's "no configuration key selecting one" checked over **all**
    of ``vars(weighting)``, public or private -- the earlier public-surface
    pin only ever saw public spellings, and the class-scan test above only
    closes the private-*class* hole, not a private *mapping* or a private
    *selector function*. A ``_MODEL_REGISTRY`` dict keyed by more than one
    weighting name, or a ``_select(key)`` function alongside it, both pass
    the earlier two guards; this one is written to catch exactly that
    shape: any mapping-typed module attribute with more than one entry, and
    any module-level function other than the one this module is documented
    to define (``_one_hour_at``)."""
    for name, obj in vars(weighting).items():
        if name.startswith("__"):
            continue
        if isinstance(obj, Mapping):
            assert len(obj) <= 1, (
                f"{name} is a mapping with {len(obj)} keys -- looks like a "
                "weighting-selection registry"
            )

    module_level_functions = {
        name
        for name, obj in vars(weighting).items()
        if isinstance(obj, types.FunctionType)
    }
    # ``trimp`` and ``dataclass`` are imported, not defined, here --
    # ``_one_hour_at`` is the module's own only defined function.
    assert module_level_functions == {"_one_hour_at", "trimp", "dataclass"}


def test_banister_trimp_model_has_no_field_beyond_model_id() -> None:
    """No configuration key selecting a weighting exists on the shipped
    implementation (Req 5.8): its only field is the fixed ``model_id``."""
    assert {f.name for f in fields(BanisterTrimpModel)} == {"model_id"}


def test_banister_trimp_model_id_is_pinned() -> None:
    assert BanisterTrimpModel().model_id == "banister-trimp"


def test_banister_trimp_model_singleton_is_an_instance_of_the_one_shipped_class() -> (
    None
):
    assert isinstance(BANISTER_TRIMP_MODEL, BanisterTrimpModel)
    assert type(BANISTER_TRIMP_MODEL) is BanisterTrimpModel


def test_banister_trimp_model_singleton_model_id_is_the_shipped_default() -> None:
    """The exported singleton is the value a caller actually injects (task
    3.2 consumes ``BANISTER_TRIMP_MODEL`` itself, not a freshly-constructed
    instance) -- so it, specifically, must carry the pinned ``model_id``,
    not merely some other instance of the same class."""
    assert BANISTER_TRIMP_MODEL.model_id == "banister-trimp"


# ---------------------------------------------------------------------------
# Observable: rescaling the shipped multiplicative coefficient scales both
# returned values by the same factor (5.8's stated observable; also verifies
# 5.4/5.5 delegate through one shared resolution rather than two).
# ---------------------------------------------------------------------------


def test_rescaling_the_shipped_coefficient_scales_both_values_by_the_same_factor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    original_pair = metrics_sources.weighting_for(None)
    factor = 3.0
    rescaled_coefficient = replace(
        original_pair.coefficient, value=original_pair.coefficient.value * factor
    )
    rescaled_pair = replace(original_pair, coefficient=rescaled_coefficient)

    samples = _samples((0.0, 3600.0), (150, 150))
    model = BanisterTrimpModel()

    baseline_activity = model.activity_impulse(samples, resting_hr=40, max_hr=190)
    baseline_hourly = model.hourly_impulse_at(150, resting_hr=40, max_hr=190)
    assert baseline_activity is not None
    assert baseline_hourly is not None

    monkeypatch.setattr(
        metrics_sources, "weighting_for", lambda selection: rescaled_pair
    )

    rescaled_activity = model.activity_impulse(samples, resting_hr=40, max_hr=190)
    rescaled_hourly = model.hourly_impulse_at(150, resting_hr=40, max_hr=190)
    assert rescaled_activity is not None
    assert rescaled_hourly is not None

    assert rescaled_activity == pytest.approx(baseline_activity * factor)
    assert rescaled_hourly == pytest.approx(baseline_hourly * factor)
