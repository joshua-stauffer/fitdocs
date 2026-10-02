"""Hand-built activities for the pure composition tests.

No FIT bytes are encoded: an activity is assembled directly from a recorded
start, a list of per-sample offsets and keyword channel arrays. Every
``Samples`` channel the caller does not name is an all-``None`` array of the
same length, so an omitted channel reads as "not recorded", never as ``0``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import datetime

from fitdocs.model import (
    SCHEMA_VERSION,
    Activity,
    DeviceInfo,
    FileIdentity,
    Lap,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
)

#: Every ``Samples`` channel a caller may name: all fields but ``time_s``.
CHANNEL_NAMES: tuple[str, ...] = tuple(
    f.name for f in dataclasses.fields(Samples) if f.name != "time_s"
)


def make_summary(**values: object) -> SessionSummary:
    """A session summary with every field ``None`` except those named."""
    names = {f.name for f in dataclasses.fields(SessionSummary)}
    unknown = set(values) - names
    if unknown:
        raise ValueError(f"unknown SessionSummary fields: {sorted(unknown)}")
    blank: dict[str, object] = {name: None for name in names}
    blank.update(values)
    return SessionSummary(**blank)  # type: ignore[arg-type]


def make_lap(**values: object) -> Lap:
    """A lap with every field ``None`` except those named."""
    names = {f.name for f in dataclasses.fields(Lap)}
    unknown = set(values) - names
    if unknown:
        raise ValueError(f"unknown Lap fields: {sorted(unknown)}")
    blank: dict[str, object] = {name: None for name in names}
    blank.update(values)
    return Lap(**blank)  # type: ignore[arg-type]


def make_activity(
    start: datetime | None,
    offsets: Sequence[float],
    *,
    laps: Sequence[Lap] = (),
    summary: SessionSummary | None = None,
    sha256: str = "0" * 64,
    manufacturer: str | None = None,
    file_identity: FileIdentity | None = None,
    devices: Sequence[DeviceInfo] = (),
    sport: Sport = Sport.RUN,
    modality: Modality = Modality.RUN,
    developer_fields: Mapping[str, object] | None = None,
    **channels: Sequence[object],
) -> Activity:
    """An activity recorded at ``start`` with one sample per entry of
    ``offsets`` (seconds after ``start``).

    ``channels`` are ``Samples`` field names mapped to arrays as long as
    ``offsets``; a channel not named is all-``None``. ``manufacturer`` fills
    the file identity's manufacturer unless ``file_identity`` is given.
    """
    n = len(offsets)
    unknown = set(channels) - set(CHANNEL_NAMES)
    if unknown:
        raise ValueError(f"unknown Samples channels: {sorted(unknown)}")
    arrays: dict[str, tuple[object, ...]] = {}
    for name in CHANNEL_NAMES:
        values = tuple(channels[name]) if name in channels else (None,) * n
        if len(values) != n:
            raise ValueError(f"{name} has {len(values)} entries; expected {n}")
        arrays[name] = values
    samples = Samples(
        time_s=tuple(float(o) for o in offsets),
        **arrays,  # type: ignore[arg-type]
    )
    if file_identity is None:
        file_identity = FileIdentity(
            manufacturer=manufacturer,
            product=None,
            serial_number=None,
            time_created=None,
        )
    extra: dict[str, object] = {}
    if developer_fields is not None:
        extra["developer_fields"] = developer_fields
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(
            sha256=sha256,
            source_path=None,
            decode_errors=(),
            undocumented_messages=0,
        ),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=start,
        summary=summary if summary is not None else make_summary(start_time=start),
        laps=tuple(laps),
        samples=samples,
        sets=(),
        devices=tuple(devices),
        file_identity=file_identity,
        **extra,  # type: ignore[arg-type]
    )
