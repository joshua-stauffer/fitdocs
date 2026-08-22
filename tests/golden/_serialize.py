"""Test-only deterministic JSON serializer and golden-snapshot builder.

The golden suite (:mod:`tests.test_golden`) freezes the full parsed-model +
derived-metrics shape of every synthetic fixture into a committed JSON snapshot,
then re-derives it and compares. That needs a *deterministic* projection of the
frozen dataclass model into JSON-native types. This module owns that projection
(:func:`to_jsonable`), the fixed athlete inputs (:data:`GOLDEN_ATHLETE`), and the
snapshot/canonicalization helpers the test and the one-time generator both call,
so the committed files and the live comparison are produced by identical code.

Why a bespoke serializer instead of :func:`dataclasses.asdict`
--------------------------------------------------------------
``dataclasses.asdict`` deep-copies every leaf value, and
:class:`Activity.developer_fields` is a :class:`types.MappingProxyType`, which is
not deep-copyable -- ``asdict`` raises ``TypeError: cannot pickle 'mappingproxy'
object`` *even when the mapping is empty*, and a ``json`` ``default=`` hook cannot
intercept it because the failure happens inside ``asdict`` before ``json`` runs.
Immutability of ``developer_fields`` is the model's core ethos and serialization
is "a test concern, not a public contract" (design: Data Models / Serialization),
so the model keeps its ``MappingProxyType`` and this serializer walks the model
by hand: it reads each dataclass field with :func:`getattr` (no deep copy) and
converts the mapping via ``dict(...)``.

:func:`to_jsonable` also handles the other non-JSON leaves the model carries:
``datetime`` -> ISO-8601 string (tz-aware UTC keeps its ``+00:00`` offset),
``StrEnum``/``Enum`` -> its ``.value``, ``tuple`` -> ``list``, and
``frozenset`` (:attr:`Activity.developer_fields_declared_scale`, Req 14.2 as
amended) -> a SORTED list, since a set has no inherent order and the snapshot
must be byte-stable across runs. Any type it does not recognize raises
:class:`TypeError` loudly, so a future model change that introduces an
unserializable field is caught here rather than silently mis-encoded.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum

from fitdocs.ingest import parse_fit
from fitdocs.metrics import compute_metrics
from fitdocs.metrics.types import AthleteInputs, ZoneSpec
from tests.fixtures import builder

# A fixed, deterministic athlete so the "with athlete" snapshot exercises the
# threshold-dependent fields too. FTP + resting/max HR + all three ZoneSpecs are
# present, so TRIMP and time-in-zone compute over the short fixtures even though
# normalized power (and everything derived from it) is legitimately None: the
# run/ride fixtures span ~9 s and NP needs >= 30 s of power stream. Recording
# None for NP/IF/VI/EF/decoupling/power_tss in the snapshots is correct -- the
# golden suite guards determinism and full-model shape parity; NP correctness is
# pinned by the unit tests in the power module.
GOLDEN_ATHLETE = AthleteInputs(
    ftp_watts=250.0,
    resting_hr_bpm=45,
    max_hr_bpm=185,
    hr_zones=ZoneSpec((120.0, 150.0, 170.0)),
    power_zones=ZoneSpec((100.0, 200.0, 300.0)),
    pace_zones=ZoneSpec((300.0, 360.0, 420.0)),
)

# name -> zero-arg builder returning byte-deterministic .fit bytes. The corrupt
# variants are intentionally excluded: golden snapshots are for files that parse.
FIXTURE_BYTES: dict[str, Callable[[], bytes]] = {
    "run": builder.run_fit_bytes,
    "ride": builder.ride_fit_bytes,
    "strength": builder.strength_fit_bytes,
    "minimal": builder.minimal_fit_bytes,
}

FIXTURE_NAMES: tuple[str, ...] = tuple(FIXTURE_BYTES)


def to_jsonable(obj: object) -> object:
    """Recursively convert a frozen-model object graph to JSON-native types.

    Deterministic and total for the types the activity model uses; deliberately
    does **not** call :func:`dataclasses.asdict` (which crashes on the
    ``MappingProxyType`` ``developer_fields``). Field order is preserved
    (dataclass declaration order), so the canonical serialization is stable.
    Unrecognized types raise :class:`TypeError` rather than being silently
    dropped or mis-encoded.
    """
    if obj is None:
        return None
    # StrEnum is a str subclass, so the Enum check must precede the scalar check.
    if isinstance(obj, Enum):
        return to_jsonable(obj.value)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bool | int | float | str):
        return obj
    # A dataclass *instance* (not the class object) -> field-ordered dict, read
    # via getattr so no deep copy touches the MappingProxyType developer_fields.
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in fields(obj)}
    # dict and MappingProxyType (developer_fields) both land here.
    if isinstance(obj, Mapping):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, tuple | list):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, frozenset):
        return sorted(to_jsonable(x) for x in obj)
    raise TypeError(f"to_jsonable cannot serialize {type(obj).__name__!r}: {obj!r}")


def build_snapshot(name: str) -> dict[str, object]:
    """Parse fixture ``name`` and project model + both metric sets to JSON types.

    The snapshot is the full-model parity payload: the parsed :class:`Activity`
    plus :func:`compute_metrics` derived both without and with
    :data:`GOLDEN_ATHLETE`, so a change to any model field or metric formula
    changes the snapshot and trips the committed-file comparison.
    """
    activity = parse_fit(FIXTURE_BYTES[name]())
    return {
        "activity": to_jsonable(activity),
        "metrics_no_athlete": to_jsonable(compute_metrics(activity)),
        "metrics_with_athlete": to_jsonable(compute_metrics(activity, GOLDEN_ATHLETE)),
    }


def canonical_json(snapshot: object) -> str:
    """Stable, human-diffable JSON text for a snapshot (trailing newline).

    Fixed formatting (2-space indent, declaration field order preserved, no
    ASCII escaping) so committed golden files and regenerated ones are byte
    identical for identical inputs.
    """
    return json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
