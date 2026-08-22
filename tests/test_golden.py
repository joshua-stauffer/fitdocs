"""Golden snapshot suite: end-to-end model + metrics parity and determinism.

For each synthetic fixture (run / ride / strength / minimal) this suite parses
the ``.fit`` bytes, computes the full derived-metric set (without and with a
fixed athlete), serializes the whole graph deterministically, and asserts it
equals a committed JSON snapshot in ``tests/golden/<name>.json``. The committed
files are the frozen contract every downstream consumer (workout-docs,
training-load) reads against: if any activity-model field or metric formula
changes shape or value, the regenerated snapshot diverges from the committed one
and these tests fail loudly (Req 2.1). A second group pins determinism -- parse +
compute + serialize twice yields byte-identical output and re-parsing the same
bytes serializes identically (Req 13.2) -- and a third pins the bespoke
serializer's handling of the model's non-JSON leaves (the ``MappingProxyType``
``developer_fields`` that ``dataclasses.asdict`` cannot serialize, plus
datetime/enum/tuple).

Regenerating the committed files (only when a model/metric change is intended):
``uv run python -m tests.golden.generate`` (see that module).
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType

import pytest

from fitdocs.ingest import parse_fit
from fitdocs.model import (
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
)
from tests.golden._serialize import (
    FIXTURE_BYTES,
    FIXTURE_NAMES,
    build_snapshot,
    canonical_json,
    to_jsonable,
)

_GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_golden(name: str) -> object:
    """Parse the committed JSON snapshot for ``name`` (structure, not raw text)."""
    return json.loads((_GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))


# --- 1. snapshot equality: full-model + metrics parity guard (Req 2.1) -------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_golden_snapshot_matches_committed(name: str) -> None:
    # Compare parsed structures (robust to whitespace): a live re-derivation of
    # the snapshot must equal the committed one. Any model-field or formula
    # change breaks this. json-roundtripping the live snapshot too, so both sides
    # are the same JSON type domain (tuples already became lists in to_jsonable).
    live = json.loads(canonical_json(build_snapshot(name)))
    assert live == _load_golden(name)


# --- 2. determinism (Req 13.2) ----------------------------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_snapshot_is_deterministic(name: str) -> None:
    first = build_snapshot(name)
    second = build_snapshot(name)
    assert first == second
    # Stronger than structural equality: identical canonical text every time.
    assert canonical_json(first) == canonical_json(second)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_reparsing_same_bytes_serializes_identically(name: str) -> None:
    data = FIXTURE_BYTES[name]()
    first = to_jsonable(parse_fit(data))
    second = to_jsonable(parse_fit(data))
    assert first == second
    assert canonical_json(first) == canonical_json(second)


# --- 3. serializer correctness: the asdict landmine and the leaf types -------


def _empty_summary() -> SessionSummary:
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=None,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )


def _empty_samples() -> Samples:
    empty: tuple[object, ...] = ()
    return Samples(
        time_s=(),
        heart_rate_bpm=empty,  # type: ignore[arg-type]
        power_w=empty,  # type: ignore[arg-type]
        cadence_rpm=empty,  # type: ignore[arg-type]
        speed_mps=empty,  # type: ignore[arg-type]
        distance_m=empty,  # type: ignore[arg-type]
        altitude_m=empty,  # type: ignore[arg-type]
        latitude_deg=empty,  # type: ignore[arg-type]
        longitude_deg=empty,  # type: ignore[arg-type]
        temperature_c=empty,  # type: ignore[arg-type]
    )


def _activity_with_developer_fields() -> Activity:
    """A minimal Activity carrying a non-empty MappingProxyType developer_fields."""
    return Activity(
        schema_version="1.0",
        provenance=Provenance(sha256="0" * 64, source_path=None, decode_errors=()),
        sport=Sport.RIDE,
        modality=Modality.BIKE,
        is_indoor=False,
        start_time=datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        summary=_empty_summary(),
        laps=(),
        samples=_empty_samples(),
        sets=(),
        devices=(),
        developer_fields=MappingProxyType({"Form Power": (1, 2, 3), "Leg Spring": 7}),
    )


def test_asdict_crashes_on_developer_fields_but_to_jsonable_does_not() -> None:
    # Documents exactly why the bespoke serializer exists: vanilla asdict cannot
    # serialize the MappingProxyType, but to_jsonable walks it via dict(...).
    activity = _activity_with_developer_fields()
    with pytest.raises(TypeError):
        dataclasses.asdict(activity)

    result = to_jsonable(activity)
    assert isinstance(result, dict)
    assert result["developer_fields"] == {"Form Power": [1, 2, 3], "Leg Spring": 7}
    # Enum -> value, datetime -> ISO-8601 string, all reachable on this graph.
    assert result["sport"] == "Ride"
    assert result["modality"] == "bike"
    assert result["start_time"] == "2024-01-02T03:04:05+00:00"


def test_to_jsonable_handles_bare_mappingproxy() -> None:
    proxy = MappingProxyType({"a": (1, 2), "b": None})
    assert to_jsonable(proxy) == {"a": [1, 2], "b": None}
    assert to_jsonable(MappingProxyType({})) == {}


def test_to_jsonable_leaf_conversions() -> None:
    assert to_jsonable(datetime(2020, 6, 1, 12, 0, tzinfo=UTC)) == (
        "2020-06-01T12:00:00+00:00"
    )
    assert to_jsonable(Sport.RIDE) == "Ride"
    assert to_jsonable(Modality.STRENGTH) == "strength"
    assert to_jsonable((1, 2, 3)) == [1, 2, 3]
    assert to_jsonable([None, "x", 1.5]) == [None, "x", 1.5]
    # bool is not coerced to int and passes through as-is.
    assert to_jsonable(True) is True
    assert to_jsonable(None) is None


def test_to_jsonable_rejects_unexpected_type() -> None:
    # A future model change to an unserializable leaf must fail loudly, not
    # silently mis-encode. Sets are not part of the model's type domain.
    with pytest.raises(TypeError):
        to_jsonable({1, 2, 3})


# --- 4. snapshots are distinct across fixtures ------------------------------


def test_snapshots_are_distinct_across_fixtures() -> None:
    # Guard against a copy/paste mistake where two fixtures share a golden file:
    # every fixture's live snapshot matches only its own committed file.
    for name in FIXTURE_NAMES:
        live = json.loads(canonical_json(build_snapshot(name)))
        for other in FIXTURE_NAMES:
            if other == name:
                continue
            assert live != _load_golden(other), f"{name} snapshot matched {other}.json"
