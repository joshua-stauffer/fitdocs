"""Tests for the load-channels result vocabulary and sufficiency value
(``types.py``).

Covers Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.9, 1.11, 2.7, 3.2, 3.3, 3.9,
3.10 -- see ``.kiro/specs/load-channels/requirements.md`` and the "Leaf --
src/fitdocs/load/channels/types.py" / "ChannelVocabulary" component in
design.md (lines 540-664).
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
import typing
from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from fitdocs import Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.load.channels import types
from fitdocs.load.channels.types import (
    DEFAULT_MIN_DURATION_S,
    DEFAULT_MIN_STREAM_COVERAGE,
    ChannelId,
    ChannelInsufficient,
    ChannelLoad,
    ChannelOutcome,
    InsufficiencyReason,
    StreamCoverage,
    SufficiencySettings,
    require_kind,
)

_MODULE_SOURCE = inspect.getsource(types)


def _bench(kind: BenchmarkKind, value: float, day: date) -> Benchmark:
    return Benchmark(
        kind=kind,
        discipline=Sport.RUN if kind != BenchmarkKind.RESTING_HR_BPM else None,
        value=value,
        measured_on=day,
    )


# ---------------------------------------------------------------------------
# 1.1 -- three identified channels, closed set
# ---------------------------------------------------------------------------


def test_channel_id_is_the_closed_three_member_set() -> None:
    assert {member.value for member in ChannelId} == {
        "power",
        "heart_rate",
        "pace",
    }
    assert len(ChannelId) == 3


def test_channel_id_members_are_directly_comparable_to_plain_strings() -> None:
    """Design (line 551) mandates ``StrEnum``, not plain ``Enum``: a caller
    that writes ``channel == "power"`` (no ``.value``) must work, because
    downstream consumers rely on it. ``{member.value ...}`` reads identically
    under either base, so that assertion alone would not catch a regression
    to plain ``Enum`` -- this compares a member directly."""
    assert ChannelId.POWER == "power"
    assert isinstance(ChannelId.POWER, str)


def test_insufficiency_reason_members_are_directly_comparable_to_plain_strings() -> (
    None
):
    assert InsufficiencyReason.NO_BENCHMARK == "no_benchmark"
    assert isinstance(InsufficiencyReason.NO_BENCHMARK, str)


# ---------------------------------------------------------------------------
# 1.5 -- closed set of insufficiency reasons
# ---------------------------------------------------------------------------


def test_insufficiency_reason_is_the_closed_seven_member_set() -> None:
    assert {member.value for member in InsufficiencyReason} == {
        "no_benchmark",
        "benchmarks_inconsistent",
        "stream_absent",
        "stream_coverage",
        "too_short",
        "model_not_defined",
        "not_computable",
    }
    assert len(InsufficiencyReason) == 7


# ---------------------------------------------------------------------------
# StreamCoverage -- frozen, equal, derived fraction (2.2 groundwork, 2.7)
# ---------------------------------------------------------------------------


def test_stream_coverage_is_frozen() -> None:
    coverage = StreamCoverage(stream="power", covered_s=30.0, total_s=60.0)
    with pytest.raises(FrozenInstanceError):
        coverage.covered_s = 999.0  # type: ignore[misc]


def test_stream_coverage_equal_for_equal_inputs() -> None:
    a = StreamCoverage(stream="power", covered_s=30.0, total_s=60.0)
    b = StreamCoverage(stream="power", covered_s=30.0, total_s=60.0)
    c = StreamCoverage(stream="power", covered_s=31.0, total_s=60.0)
    assert a == b
    assert a != c


def test_stream_coverage_fraction_is_derived_not_stored() -> None:
    coverage = StreamCoverage(stream="heart_rate", covered_s=3.0, total_s=4.0)
    assert coverage.fraction == pytest.approx(0.75)
    field_names = {f.name for f in dataclasses.fields(StreamCoverage)}
    assert field_names == {"stream", "covered_s", "total_s"}
    assert "fraction" not in field_names


# ---------------------------------------------------------------------------
# ChannelLoad -- shape, frozen, equal, required fields (1.3, 2.7)
# ---------------------------------------------------------------------------


def _make_channel_load(**overrides: object) -> ChannelLoad:
    defaults: dict[str, object] = dict(
        channel=ChannelId.POWER,
        load=100.0,
        intensity=1.0,
        anchor=_bench(BenchmarkKind.FTP_WATTS, 250.0, date(2026, 1, 1)),
        scored_duration_s=3600.0,
        coverage=StreamCoverage(stream="power", covered_s=3600.0, total_s=3600.0),
        inputs_used=(("NP", "250 W"),),
    )
    defaults.update(overrides)
    return ChannelLoad(**defaults)  # type: ignore[arg-type]


def test_channel_load_is_frozen() -> None:
    load = _make_channel_load()
    with pytest.raises(FrozenInstanceError):
        load.load = 0.0  # type: ignore[misc]


def test_channel_load_equal_for_equal_inputs() -> None:
    a = _make_channel_load()
    b = _make_channel_load()
    c = _make_channel_load(load=50.0)
    assert a == b
    assert a != c


def test_channel_load_field_names_match_the_spec_exactly() -> None:
    field_names = {f.name for f in dataclasses.fields(ChannelLoad)}
    assert field_names == {
        "channel",
        "load",
        "intensity",
        "anchor",
        "scored_duration_s",
        "coverage",
        "inputs_used",
        "notes",
    }


def test_channel_load_required_fields_have_no_default_except_notes() -> None:
    """Every field but ``notes`` must be supplied by the caller: neither a
    plain default nor a ``default_factory`` may stand in for it, since either
    one would let a channel construct a ``ChannelLoad`` while omitting a
    required field such as ``coverage`` or ``scored_duration_s`` (2.7)."""
    fields_by_name = {f.name: f for f in dataclasses.fields(ChannelLoad)}
    for required in (
        "channel",
        "load",
        "intensity",
        "anchor",
        "scored_duration_s",
        "coverage",
        "inputs_used",
    ):
        assert fields_by_name[required].default is dataclasses.MISSING, required
        assert fields_by_name[required].default_factory is dataclasses.MISSING, required
    assert fields_by_name["notes"].default == ()


def test_channel_load_construction_fails_when_coverage_is_omitted() -> None:
    """Positive control for the field-defaults test above: actually try to
    build a ``ChannelLoad`` without ``coverage`` and confirm construction
    itself rejects it, naming the missing field (2.7)."""
    with pytest.raises(TypeError, match="coverage"):
        ChannelLoad(  # type: ignore[call-arg]
            channel=ChannelId.POWER,
            load=100.0,
            intensity=1.0,
            anchor=_bench(BenchmarkKind.FTP_WATTS, 250.0, date(2026, 1, 1)),
            scored_duration_s=3600.0,
            inputs_used=(("NP", "250 W"),),
        )


def test_channel_load_notes_defaults_to_empty_tuple() -> None:
    load = _make_channel_load()
    assert load.notes == ()


# ---------------------------------------------------------------------------
# ChannelInsufficient -- shape, frozen, equal, defaults (1.4)
# ---------------------------------------------------------------------------


def _make_insufficient(**overrides: object) -> ChannelInsufficient:
    defaults: dict[str, object] = dict(
        channel=ChannelId.HEART_RATE,
        reason=InsufficiencyReason.STREAM_COVERAGE,
        detail="heart-rate coverage 0.60 is below the configured minimum 0.80",
    )
    defaults.update(overrides)
    return ChannelInsufficient(**defaults)  # type: ignore[arg-type]


def test_channel_insufficient_is_frozen() -> None:
    result = _make_insufficient()
    with pytest.raises(FrozenInstanceError):
        result.detail = "changed"  # type: ignore[misc]


def test_channel_insufficient_equal_for_equal_inputs() -> None:
    a = _make_insufficient()
    b = _make_insufficient()
    c = _make_insufficient(detail="a different explanation")
    assert a == b
    assert a != c


def test_channel_insufficient_field_names_match_the_spec_exactly() -> None:
    field_names = {f.name for f in dataclasses.fields(ChannelInsufficient)}
    assert field_names == {"channel", "reason", "detail", "observed", "required"}


def test_channel_insufficient_observed_and_required_default_to_none() -> None:
    result = _make_insufficient()
    assert result.observed is None
    assert result.required is None


def test_channel_insufficient_can_carry_observed_and_required_for_threshold() -> None:
    result = _make_insufficient(
        reason=InsufficiencyReason.TOO_SHORT, observed=45.0, required=60.0
    )
    assert result.observed == 45.0
    assert result.required == 60.0


# ---------------------------------------------------------------------------
# ChannelOutcome -- closed two-variant union, no third state (1.2)
# ---------------------------------------------------------------------------


def test_channel_outcome_is_exactly_the_two_documented_variants() -> None:
    variants = frozenset(typing.get_args(ChannelOutcome))
    assert variants == frozenset({ChannelLoad, ChannelInsufficient})
    assert len(variants) == 2


# ---------------------------------------------------------------------------
# SufficiencySettings -- defaults, override resolution (3.2, 3.3)
# ---------------------------------------------------------------------------


def test_default_min_stream_coverage_and_duration_constants() -> None:
    assert DEFAULT_MIN_STREAM_COVERAGE == 0.80
    assert DEFAULT_MIN_DURATION_S == 60


def test_sufficiency_settings_is_frozen() -> None:
    settings = SufficiencySettings()
    with pytest.raises(FrozenInstanceError):
        settings.min_duration_s = 120  # type: ignore[misc]


def test_sufficiency_settings_equal_for_equal_inputs() -> None:
    a = SufficiencySettings(min_duration_s=90)
    b = SufficiencySettings(min_duration_s=90)
    c = SufficiencySettings(min_duration_s=120)
    assert a == b
    assert a != c


def test_minimum_for_uses_shared_default_when_no_override_set() -> None:
    settings = SufficiencySettings()
    assert settings.minimum_for(ChannelId.POWER) == 0.80
    assert settings.minimum_for(ChannelId.HEART_RATE) == 0.80
    assert settings.minimum_for(ChannelId.PACE) == 0.80


def test_minimum_for_resolves_per_channel_override_and_falls_back_when_unset() -> None:
    """Pairwise-distinct values on purpose: a shared minimum, two distinct
    per-channel overrides, and one channel left unset -- so no plausible wrong
    implementation (always-override, always-shared, swapped channel lookup)
    can pass by accident."""
    settings = SufficiencySettings(
        min_stream_coverage=0.90,
        power_min_stream_coverage=0.65,
        hr_min_stream_coverage=0.55,
        pace_min_stream_coverage=None,
    )
    assert settings.minimum_for(ChannelId.POWER) == 0.65
    assert settings.minimum_for(ChannelId.HEART_RATE) == 0.55
    assert settings.minimum_for(ChannelId.PACE) == 0.90


# ---------------------------------------------------------------------------
# require_kind -- the wrong-quantity guard (1.9)
# ---------------------------------------------------------------------------


def test_require_kind_returns_none_for_a_matching_benchmark() -> None:
    bench = _bench(BenchmarkKind.FTP_WATTS, 250.0, date(2026, 1, 1))
    assert require_kind(bench, BenchmarkKind.FTP_WATTS) is None


def test_require_kind_raises_naming_both_quantities_on_mismatch() -> None:
    bench = _bench(BenchmarkKind.FTP_WATTS, 250.0, date(2026, 1, 1))
    with pytest.raises(ValueError) as exc_info:
        require_kind(bench, BenchmarkKind.LTHR_BPM)
    message = str(exc_info.value)
    assert "ftp_watts" in message
    assert "lthr_bpm" in message


def test_require_kind_raises_for_every_mismatched_pair_not_just_one() -> None:
    """Guards against a guard that only checks one hard-coded pair."""
    bench = _bench(BenchmarkKind.RESTING_HR_BPM, 50.0, date(2026, 1, 1))
    with pytest.raises(ValueError) as exc_info:
        require_kind(bench, BenchmarkKind.THRESHOLD_PACE_S_PER_KM)
    message = str(exc_info.value)
    assert "resting_hr_bpm" in message
    assert "threshold_pace_s_per_km" in message


# ---------------------------------------------------------------------------
# 1.11 -- the intensity semantic, stated once, at ChannelLoad's definition
# ---------------------------------------------------------------------------


def test_intensity_semantic_is_stated_exactly_once_in_this_module() -> None:
    _RELATION = "load == (scored_duration_s / 3600) * intensity ** 2 * 100"
    normalized_module = re.sub(r"\s+", " ", _MODULE_SOURCE)
    assert normalized_module.count(_RELATION) == 1, (
        "the shared intensity semantic must be stated exactly once in this module"
    )
    # The count above alone does not pin *where* -- relocating the sentence
    # into another class's docstring (still exactly one module-wide
    # occurrence) would leave that assertion green. Read only ChannelLoad's
    # own source to confirm the statement lives at its definition.
    normalized_class = re.sub(r"\s+", " ", inspect.getsource(ChannelLoad))
    assert normalized_class.count(_RELATION) == 1, (
        "the shared intensity semantic must be stated at the definition of "
        "ChannelLoad specifically, not merely once somewhere in the module"
    )


def test_intensity_semantic_extracted_from_source_matches_worked_example() -> None:
    """Extracts the exact relation text this module states -- the module's
    docstring holds ``load == <expression>`` on a single source line -- and
    evaluates *that* extracted text, rather than a hand-transcribed copy,
    against a worked example. Changing the exponent or the formula in
    ``types.py`` changes the text this test extracts and evaluates, so a
    mutation such as ``** 2`` -> ``** 3`` changes the *computed* result and
    reds this assertion directly, not only the sibling "stated once" test."""
    match = re.search(r"^\s*load == (.+)$", _MODULE_SOURCE, re.MULTILINE)
    assert match is not None, "no 'load == <expr>' line found in the module source"
    relation_text = match.group(1).strip()
    scored_duration_s = 1800.0
    intensity = 0.8
    computed = eval(  # noqa: S307 -- trusted source text extracted above
        relation_text, {"scored_duration_s": scored_duration_s, "intensity": intensity}
    )
    assert computed == pytest.approx(32.0)


# ---------------------------------------------------------------------------
# 3.10 -- default coverage cites the published precedent
# ---------------------------------------------------------------------------


def test_default_min_stream_coverage_cites_the_trainingpeaks_precedent() -> None:
    assert "TRAININGPEAKS_COVERAGE_GATE" in _MODULE_SOURCE


# ---------------------------------------------------------------------------
# 3.9 -- channels receive resolved configuration; this module never reads it
# ---------------------------------------------------------------------------


def test_module_does_not_import_the_settings_reader() -> None:
    tree = ast.parse(_MODULE_SOURCE)
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # ``node.module`` is ``None`` for a bare ``from . import x``, and
            # relative imports (``from .. import settings``, ``from
            # ..settings import X``) carry ``node.level > 0`` with the dots
            # not represented in ``node.module`` at all -- reconstruct the
            # written spelling so both absolute and relative forms resolve.
            resolved_module = "." * node.level + (node.module or "")
            imported_names.append(resolved_module)
            imported_names.extend(
                f"{resolved_module}.{alias.name}" for alias in node.names
            )
    assert imported_names, "the walk found no imports -- wrong module scanned"
    assert not any("load.settings" in name for name in imported_names)
    # Matches a trailing ``settings`` component however it was reached: a
    # dotted absolute name ("fitdocs.load.settings"), a resolved relative
    # name ("..settings"), or a bare top-level name ("settings", from an
    # absolute ``import settings``). ``from . import settings`` resolves to
    # "..settings", which the same pattern matches -- never to a bare
    # "settings" (verified against ``ast``: it yields ['.', '..settings']).
    assert not any(re.search(r"(^|\.)settings$", name) for name in imported_names)
