"""The ingest layer: decode ``.fit`` bytes and map FIT messages onto the model.

This package exposes :func:`parse_fit`, the public parsing entry point that
composes the decode wrapper (:mod:`fitdocs.ingest.decode`) and every extractor into
one frozen :class:`~fitdocs.model.Activity`. The decode error taxonomy lives in
:mod:`fitdocs.ingest.errors`.

``parse_fit`` is *pure composition*: it holds no extraction logic of its own and
performs no writes, prompts, or network access (Req 13.1). Every FIT-epoch
timestamp conversion is applied by the extractors via the model-owned
:func:`fitdocs.model.fit_datetime` helper -- the orchestrator creates none of its
own. It never imports the metrics layer.
"""

from __future__ import annotations

from pathlib import Path

from fitdocs.ingest.decode import decode_fit
from fitdocs.ingest.laps import extract_laps
from fitdocs.ingest.records import extract_samples
from fitdocs.ingest.sets import extract_sets
from fitdocs.ingest.sport import detect_sport
from fitdocs.ingest.summary import (
    extract_developer_fields_with_declared_scale,
    extract_devices,
    extract_summary,
)
from fitdocs.model import SCHEMA_VERSION, Activity, Provenance

__all__ = ["parse_fit"]


def parse_fit(source: str | Path | bytes) -> Activity:
    """Decode a ``.fit`` file or bytes into a frozen :class:`Activity` (Req 1.1-2.4).

    ``source`` is a filesystem path (``str``/:class:`~pathlib.Path`) or a raw byte
    buffer. The bytes are decoded once by :func:`fitdocs.ingest.decode.decode_fit`
    and every message list is handed to the matching extractor; the results are
    composed into one immutable :class:`Activity` stamped with
    :data:`~fitdocs.model.SCHEMA_VERSION`.

    Validation failures propagate as the decode wrapper raises them --
    :class:`~fitdocs.ingest.errors.NotFitFileError` for non-FIT input (Req 1.1,
    1.2) and :class:`~fitdocs.ingest.errors.FitIntegrityError` for a failed
    integrity check (Req 1.3) -- before any Activity is built. Message-level decoder
    errors do NOT abort: they ride on :attr:`Provenance.decode_errors` for callers
    to surface (Req 1.4).

    The returned :attr:`Activity.start_time` follows the anchor policy: the session
    start when recorded, otherwise the first record timestamp, otherwise ``None``
    (Req 2.4). This function performs no I/O beyond reading ``source`` and never
    mutates it (Req 13.1).
    """
    result = decode_fit(source)
    messages = result.messages

    record_mesgs = messages.get("record_mesgs", [])
    session_mesgs = messages.get("session_mesgs", [])
    activity_mesgs = messages.get("activity_mesgs", [])
    lap_mesgs = messages.get("lap_mesgs", [])
    set_mesgs = messages.get("set_mesgs", [])
    exercise_title_mesgs = messages.get("exercise_title_mesgs", [])
    device_info_mesgs = messages.get("device_info_mesgs", [])
    sport_mesgs = messages.get("sport_mesgs", [])
    field_description_mesgs = messages.get("field_description_mesgs", [])

    summary = extract_summary(session_mesgs, activity_mesgs)

    # Anchor policy: a session start when present, else the first record timestamp,
    # else None. ``extract_samples`` anchors ``time_s`` to the first record when the
    # session start is None, and returns the absolute record timestamps for laps.
    session_start = summary.start_time
    samples, record_ts = extract_samples(record_mesgs, session_start)
    if session_start is not None:
        start_time = session_start
    elif record_ts:
        start_time = record_ts[0]
    else:
        start_time = None

    laps = extract_laps(lap_mesgs, record_ts)
    sets = extract_sets(set_mesgs, exercise_title_mesgs)
    devices = extract_devices(device_info_mesgs)
    developer_fields, developer_fields_declared_scale = (
        extract_developer_fields_with_declared_scale(
            field_description_mesgs, session_mesgs
        )
    )

    # Sport source precedence: the session values, falling back to the standalone
    # ``sport`` message when the session did not record them (Req 5 wiring).
    sport_str = summary.sport
    sub_sport_str = summary.sub_sport
    if sport_mesgs:
        first_sport = sport_mesgs[0]
        if sport_str is None:
            sport_str = _as_str(first_sport.get("sport"))
        if sub_sport_str is None:
            sub_sport_str = _as_str(first_sport.get("sub_sport"))
    sport, modality, is_indoor = detect_sport(sport_str, sub_sport_str)

    provenance = Provenance(
        sha256=result.sha256,
        source_path=result.source_path,
        decode_errors=result.errors,
    )

    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=provenance,
        sport=sport,
        modality=modality,
        is_indoor=is_indoor,
        start_time=start_time,
        summary=summary,
        laps=laps,
        samples=samples,
        sets=sets,
        devices=devices,
        developer_fields=developer_fields,
        developer_fields_declared_scale=developer_fields_declared_scale,
    )


def _as_str(value: object) -> str | None:
    """Narrow a decoded sport-message value to ``str`` for detection, else ``None``.

    Sport detection only interprets known sport/sub-sport strings, so a non-string
    fallback value (an unknown enum decoded as a raw int) is treated as absent --
    ``detect_sport`` then applies its never-failing ``Workout`` fallback.
    """
    return value if isinstance(value, str) else None
