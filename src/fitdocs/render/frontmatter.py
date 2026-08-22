"""PKM-compatible YAML frontmatter: fixed schema, deterministic emission.

This module is the single source of a workout document's frontmatter block
(Req 5.1, 5.2, 5.6, 3.4). It builds one ordered mapping in a fixed key order and
emits it through a single ``yaml.safe_dump`` call -- the only pyyaml *emission*
touchpoint in the codebase, so golden files can guard against style drift. Two
honesty rules govern the schema:

- **A key whose value is absent is omitted entirely** -- never ``null``, ``0``,
  or a placeholder (Req 5.2). Only keys that are actually present are inserted
  into the mapping, so omission is the single emission path rather than a
  special case. Numeric guards test ``is None`` so a genuine recorded ``0`` (for
  example zero power while coasting) is emitted as a real value, never mistaken
  for missing data (Req 13.3).
- **Deterministic output** -- identical context yields byte-identical
  frontmatter (Req 4.1). ``sort_keys=False`` plus the fixed insertion order
  fixes the key order; local dates and times are emitted as ISO **strings** so
  pyyaml never coerces them into its own date/timestamp forms.

Local dates and times use the timezone carried on the :class:`DocContext` (the
CLI supplies the system zone; tests pin a fixed one), so the ``title``,
``date``, and ``start_time`` are user-correct yet reproducible.

Precision is fixed and documented so goldens stay stable:

- ``distance_km`` -- metres/1000 rounded to **two** decimals (a numeric float).
- ``elevation_gain_m`` -- metres rounded to **one** decimal (a numeric float).
- ``moving_time`` -- the ``h:mm:ss`` / ``m:ss`` string from
  :func:`fitdocs.render.format.fmt_duration`.
- ``avg_hr_bpm`` / ``avg_power_w`` -- rounded to the nearest whole number
  (``int``); ``calories_kcal`` is the recorded ``int`` passthrough.

**What a document *says* comes from :mod:`fitdocs.contract`** (design:
DocumentContract): the format version, the key names that carry the document's
type, version, identity, and source history, the workout-type marker, the
``---`` fence, and the session-UUID format. This module decides only *what to
emit and how to spell the values*; it holds no second opinion about what a
fitdocs document is, so the block it writes is read back identically by every
command that opens the file (wiki-contract Req 1.1, 5.1). Emission stays here --
serializing the managed block is not an interpretation of it.
"""

from __future__ import annotations

from typing import Final

import yaml

from fitdocs.contract import (
    DOC_VERSION,
    DOC_VERSION_KEY,
    FRONTMATTER_FENCE,
    GENERATOR,
    GENERATOR_KEY,
    SOURCES_KEY,
    TYPE_KEY,
    UUID_KEY,
    WORKOUT_TYPE,
    format_session_uuid,
)
from fitdocs.render import DocContext
from fitdocs.render.format import fmt_duration

__all__ = ["build_frontmatter"]

_SESSION_UUID_FIELD: Final[str] = "SESSION UUID"
"""Developer-field key carrying the recorded 16-byte session identifier."""


def _title(ctx: DocContext) -> str:
    """The document title: ``"<Sport> <YYYY-MM-DD> <HH:MM>"`` in local time.

    Degrades gracefully when the activity has no recorded start time: the title
    becomes ``"<Sport> <doc_stem>"`` -- always a non-empty, deterministic string
    with a stable identity suffix, never a fabricated date.
    """
    sport = ctx.activity.sport.value
    start = ctx.activity.start_time
    if start is None:
        return f"{sport} {ctx.doc_stem}"
    local = start.astimezone(ctx.tz)
    return f"{sport} {local:%Y-%m-%d} {local:%H:%M}"


def build_frontmatter(ctx: DocContext) -> str:
    """Build the ``---``-fenced YAML frontmatter block for a workout document.

    Inserts only the present keys, in the fixed schema order -- ``generator``
    immediately after ``type`` and before ``doc_version`` (Req 4.1) -- then
    emits them with a single ``yaml.safe_dump`` (Req 5.1, 5.2, 5.6, 3.4, 4.1).
    """
    activity = ctx.activity
    metrics = ctx.metrics
    data: dict[str, object] = {}

    data["title"] = _title(ctx)
    data[TYPE_KEY] = WORKOUT_TYPE
    data[GENERATOR_KEY] = GENERATOR
    data[DOC_VERSION_KEY] = DOC_VERSION

    session_uuid = format_session_uuid(
        activity.developer_fields.get(_SESSION_UUID_FIELD)
    )
    if session_uuid is not None:
        data[UUID_KEY] = session_uuid

    if activity.start_time is not None:
        local = activity.start_time.astimezone(ctx.tz)
        data["date"] = f"{local:%Y-%m-%d}"
        data["start_time"] = local.isoformat()

    data["sport"] = activity.sport.value
    data["modality"] = activity.modality.value

    if activity.is_indoor:
        data["indoor"] = True

    if metrics.distance_m is not None:
        data["distance_km"] = round(metrics.distance_m / 1000, 2)
    moving_time = fmt_duration(metrics.moving_time_s)
    if moving_time is not None:
        data["moving_time"] = moving_time
    if metrics.avg_heart_rate_bpm is not None:
        data["avg_hr_bpm"] = int(round(metrics.avg_heart_rate_bpm))
    if metrics.avg_power_w is not None:
        data["avg_power_w"] = int(round(metrics.avg_power_w))
    if metrics.elevation_gain_m is not None:
        data["elevation_gain_m"] = round(float(metrics.elevation_gain_m), 1)
    if metrics.calories_kcal is not None:
        data["calories_kcal"] = metrics.calories_kcal

    if ctx.source_refs:
        data[SOURCES_KEY] = list(ctx.source_refs)

    dumped = yaml.safe_dump(
        data, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    return f"{FRONTMATTER_FENCE}\n{dumped}{FRONTMATTER_FENCE}\n"
