"""Deterministic load-section content: human markdown + a machine payload.

This module owns the *content* of a workout document's reserved training-load
region -- what fills the space between the region markers workout-docs emits.
Every rendered region carries two things:

* **Human-readable markdown** -- a headline value, the methodology name, the
  basis it was derived from, an inputs table, notes, and -- only when they are
  not empty -- a non-selected-values block and a quality-flags block, rendered
  visibly subordinate to the headline (Req 7.1, 1.10).
* **A single machine-readable payload comment** -- ``<!-- fitdocs-load:v2
  {...} -->`` on the first line -- so the tool recognizes and recovers its own
  previously computed results (Req 7.3). The payload is the durable record: the
  region markdown and the document's load frontmatter are both derivable from
  it, and it carries every result field, including the diagnostics frontmatter
  omits.

Two invariants make the seam safe:

* **Byte-determinism.** Identical results render identically -- no timestamps,
  no randomness. The payload JSON is emitted compact (``separators=(",", ":")``)
  with ``sort_keys=True``, so re-rendering an unchanged result is a no-op diff.
  Every array preserves the producer's order; nothing is sorted at the value
  level.
* **Tolerant, versioned parsing.** :func:`parse_payload` returns ``None`` for
  absent, malformed, incomplete, *or unknown-version* payloads. An unrecognized
  payload is treated as foreign content the engine must never silently
  overwrite, so a newer on-disk format is preserved rather than clobbered.
  ``non_selected`` and ``flags`` decode as empty tuples when absent from the
  JSON, so a later additive field does not invalidate the format (Req 11.1).

A ``null`` non-selected value is meaningful -- no value was computed -- and is
never coerced to ``0`` (Req 1.11, 9.1): it renders its label and reason with no
number.

The unsupported state (Req 7.7) is honest: it names the sport and its
human-visible line contains no digits, because no load value was computed.

Pure: no I/O, no timestamps, no randomness. The only non-stdlib import is the
:class:`~fitdocs.load.types.LoadResult` contract it renders and reconstructs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Final, Literal, cast

from fitdocs.load.types import LoadResult, NonSelectedValue, QualityFlag

__all__ = [
    "LOAD_PAYLOAD_VERSION",
    "LoadPayload",
    "PayloadStamp",
    "encode_payload",
    "inspect_payload",
    "parse_payload",
    "render_computed",
    "render_unsupported",
]

LOAD_PAYLOAD_VERSION: Final[int] = 2
"""The payload schema version. Bumping it makes older parsers treat the newer
payload as unrecognized (foreign) rather than misread it (Req 11.1)."""

_MARKER_PREFIX: Final[str] = "<!-- fitdocs-load:v"
"""The literal opening of the payload comment, up to the version digits."""

_PAYLOAD_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*<!-- fitdocs-load:v(\d+) (.+?) -->\s*$"
)
"""Matches a single payload-comment line: ``v<N>`` marker and its JSON body."""

_VALID_VERDICTS: Final[frozenset[str]] = frozenset(
    {"detected", "not-detected", "not-assessed"}
)
"""The closed :class:`~fitdocs.load.types.QualityFlag` verdict vocabulary."""


@dataclass(frozen=True)
class LoadPayload:
    """The parsed/renderable form of a load region's machine payload.

    Exactly one of the two statuses holds: ``"computed"`` carries a
    :class:`LoadResult` (and ``sport is None``); ``"unsupported"`` carries the
    declined ``sport`` name (and ``result is None``).
    """

    status: Literal["computed", "unsupported"]
    result: LoadResult | None
    """The full result for a computed payload; ``None`` when unsupported."""
    sport: str | None
    """The declined sport for an unsupported payload; ``None`` when computed."""


# --- payload encoding -------------------------------------------------------


def encode_payload(payload: LoadPayload) -> str:
    """Encode ``payload`` as its single-line HTML-comment record.

    The JSON is compact with sorted keys, so identical payloads encode
    byte-identically. ``ensure_ascii=False`` keeps ``×``/``—`` in labels and
    basis text readable while staying deterministic. Returns the comment line
    with no trailing newline; the renderer composes surrounding blank lines.
    """
    if payload.status == "computed":
        result = payload.result
        if result is None:
            raise ValueError("a computed load payload requires a result")
        data: dict[str, object] = {
            "v": LOAD_PAYLOAD_VERSION,
            "status": "computed",
            "calculator_id": result.calculator_id,
            "display_name": result.display_name,
            "value": result.value,
            "basis": result.basis,
            "non_selected": [
                {
                    "key": entry.key,
                    "label": entry.label,
                    "value": entry.value,
                    "reason": entry.reason,
                }
                for entry in result.non_selected
            ],
            "flags": [
                {
                    "key": flag.key,
                    "label": flag.label,
                    "verdict": flag.verdict,
                    "detail": flag.detail,
                }
                for flag in result.flags
            ],
            "inputs_used": [list(pair) for pair in result.inputs_used],
            "notes": list(result.notes),
        }
    else:
        data = {
            "v": LOAD_PAYLOAD_VERSION,
            "status": "unsupported",
            "sport": payload.sport,
        }
    return f"{_MARKER_PREFIX}{LOAD_PAYLOAD_VERSION} {_encode_json(data)} -->"


def _encode_json(data: dict[str, object]) -> str:
    """Serialize ``data`` compactly with sorted keys, safe to embed in a comment.

    Any ``>`` is escaped as its JSON ``\\u003e`` unicode form so the payload can
    never contain the HTML-comment terminator ``-->`` (none of the contract
    fields produce ``>`` naturally; this is purely defensive). The escape is
    reversible -- :func:`json.loads` decodes ``\\u003e`` back to ``>`` -- so the
    round-trip stays lossless.
    """
    text = json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return text.replace(">", "\\u003e")


def parse_payload(region_content: str) -> LoadPayload | None:
    """Reconstruct the :class:`LoadPayload` embedded in ``region_content``.

    Scans for the payload-comment line and returns ``None`` -- *unrecognized* --
    when there is none, when its JSON is malformed, when required fields are
    missing or wrongly typed, or when the marker version differs from
    :data:`LOAD_PAYLOAD_VERSION` (an unknown/newer version is foreign content,
    never misread). Unknown extra JSON fields are ignored tolerantly, and an
    absent ``non_selected``/``flags`` array decodes as an empty tuple (Req
    11.1). On a valid v2 payload the sequence fields are rebuilt as tuples so a
    computed ``result`` compares equal to the ``LoadResult`` that produced it.
    """
    for line in region_content.splitlines():
        match = _PAYLOAD_RE.match(line)
        if match is None:
            continue
        if int(match.group(1)) != LOAD_PAYLOAD_VERSION:
            return None  # unknown/newer version -> foreign, never misread
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            return None
        return _payload_from_data(data)
    return None


def _payload_from_data(data: object) -> LoadPayload | None:
    """Build a :class:`LoadPayload` from decoded JSON, or ``None`` if invalid."""
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    if status == "computed":
        result = _result_from_data(data)
        if result is None:
            return None
        return LoadPayload("computed", result, None)
    if status == "unsupported":
        sport = data.get("sport")
        if not isinstance(sport, str):
            return None
        return LoadPayload("unsupported", None, sport)
    return None


def _result_from_data(data: dict[str, object]) -> LoadResult | None:
    """Rebuild a :class:`LoadResult` from a computed payload's JSON fields.

    Returns ``None`` when a required field is absent or wrongly typed (all-
    or-nothing); unknown extra fields are ignored. ``non_selected`` and
    ``flags`` are optional -- absent decodes as an empty tuple -- but a
    *present* value must be well-formed or decoding fails entirely (Req 11.1).
    """
    try:
        calculator_id = data["calculator_id"]
        display_name = data["display_name"]
        value = data["value"]
        basis = data["basis"]
        inputs_used_raw = data["inputs_used"]
        notes_raw = data["notes"]
    except KeyError:
        return None

    if not (
        isinstance(calculator_id, str)
        and isinstance(display_name, str)
        and isinstance(basis, str)
    ):
        return None
    # bool is an int subclass, so reject it explicitly for numeric fields.
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not isinstance(inputs_used_raw, list) or not isinstance(notes_raw, list):
        return None

    non_selected = _non_selected_from_data(data.get("non_selected", []))
    if non_selected is None:
        return None
    flags = _flags_from_data(data.get("flags", []))
    if flags is None:
        return None

    try:
        inputs_used = tuple((str(pair[0]), str(pair[1])) for pair in inputs_used_raw)
    except (TypeError, IndexError, KeyError):
        return None
    notes = tuple(str(note) for note in notes_raw)

    return LoadResult(
        calculator_id=calculator_id,
        display_name=display_name,
        value=float(value),
        basis=basis,
        non_selected=non_selected,
        flags=flags,
        inputs_used=inputs_used,
        notes=notes,
    )


def _non_selected_from_data(raw: object) -> tuple[NonSelectedValue, ...] | None:
    """Decode a ``non_selected`` array, or ``None`` on any malformed entry.

    A ``null`` per-entry ``value`` decodes as ``None`` -- never coerced to
    ``0`` -- because it records that no number was computed for that
    candidate (Req 1.11, 9.1).
    """
    if not isinstance(raw, list):
        return None
    entries: list[NonSelectedValue] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        try:
            key = item["key"]
            label = item["label"]
            value = item["value"]
            reason = item["reason"]
        except KeyError:
            return None
        if not (
            isinstance(key, str) and isinstance(label, str) and isinstance(reason, str)
        ):
            return None
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int | float)
        ):
            return None
        entries.append(
            NonSelectedValue(
                key=key,
                label=label,
                value=None if value is None else float(value),
                reason=reason,
            )
        )
    return tuple(entries)


def _flags_from_data(raw: object) -> tuple[QualityFlag, ...] | None:
    """Decode a ``flags`` array, or ``None`` on any malformed or unknown entry."""
    if not isinstance(raw, list):
        return None
    entries: list[QualityFlag] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        try:
            key = item["key"]
            label = item["label"]
            verdict = item["verdict"]
            detail = item["detail"]
        except KeyError:
            return None
        if not (
            isinstance(key, str)
            and isinstance(label, str)
            and isinstance(detail, str)
            and isinstance(verdict, str)
            and verdict in _VALID_VERDICTS
        ):
            return None
        entries.append(
            QualityFlag(
                key=key,
                label=label,
                verdict=cast(
                    'Literal["detected", "not-detected", "not-assessed"]', verdict
                ),
                detail=detail,
            )
        )
    return tuple(entries)


# --- payload stamp inspection ------------------------------------------------


@dataclass(frozen=True)
class PayloadStamp:
    """What can be learned from a payload comment without decoding a result.

    Every field after ``version`` is independently best-effort: each resolves
    on its own from whatever the body happens to decode to, regardless of
    whether the others do. Nothing here constructs a :class:`LoadResult`,
    feeds :func:`parse_payload`'s callers, or feeds a frontmatter projection
    (Req 11.2) -- ``status`` is the one field ever used for routing, and
    ``calculator_id`` can only ever reach a human-readable message (Req
    13.4). Both stay ``None`` when the marker line's body cannot be read as
    the shape they need.
    """

    version: int
    status: Literal["computed", "unsupported"] | None
    """The recorded status -- routing, never result data. ``None`` when the
    body does not decode to a mapping carrying a recognized status string."""
    calculator_id: str | None
    """The recorded methodology id -- message-only, never data. ``None``
    when the body does not decode to a mapping carrying a string here."""


def inspect_payload(region_content: str) -> PayloadStamp | None:
    """Learn what can be known from a payload marker without decoding a
    result, for *any* marker version -- including one this tool's strict
    :func:`parse_payload` refuses.

    Returns ``None`` only when no payload-comment line exists at all.
    Whenever a marker line is found, ``version`` is always reported; ``status``
    and ``calculator_id`` are each independently best-effort, resolving only
    when the body happens to decode to a JSON object carrying a recognized
    string under the respective key. An undecodable, non-object, or
    key-missing body yields those two fields as ``None`` without affecting
    ``version``. This function never partially reconstructs a result --
    Req 11.2's guarantee that an unrecognized format is never parsed
    partially or inferred rests on this output staying pure inspection.
    """
    for line in region_content.splitlines():
        match = _PAYLOAD_RE.match(line)
        if match is None:
            continue
        version = int(match.group(1))
        status: Literal["computed", "unsupported"] | None = None
        calculator_id: str | None = None
        try:
            data = json.loads(match.group(2))
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            raw_status = data.get("status")
            if raw_status == "computed" or raw_status == "unsupported":
                status = raw_status
            raw_calculator_id = data.get("calculator_id")
            if isinstance(raw_calculator_id, str):
                calculator_id = raw_calculator_id
        return PayloadStamp(version=version, status=status, calculator_id=calculator_id)
    return None


# --- region rendering -------------------------------------------------------


def render_computed(result: LoadResult) -> str:
    """Render the region content for a computed ``result`` (Req 7.1, 7.3).

    The first line is the machine payload comment; the rest is human-readable
    markdown -- a headline value (one decimal, trailing ``.0`` dropped) with the
    methodology name, the basis line, an inputs table (when any inputs), notes
    as bullets (when any), and -- only when non-empty -- a non-selected-values
    block and a quality-flags block, rendered after the notes so they read as
    visibly subordinate to the headline (Req 1.10). Empty ``non_selected``/
    ``flags`` tuples produce no heading, no table, and no placeholder row (Req
    1.11). Rendering the same result twice yields byte-identical output.
    """
    blocks: list[str] = [
        encode_payload(LoadPayload("computed", result, None)),
        f"**{_format_value(result.value)}** — {result.display_name}",
        f"**Basis:** {result.basis}",
    ]
    if result.inputs_used:
        rows = ["| Input | Value |", "| --- | --- |"]
        rows += [f"| {label} | {value} |" for label, value in result.inputs_used]
        blocks.append("\n".join(rows))
    if result.notes:
        blocks.append("\n".join(f"- {note}" for note in result.notes))
    if result.non_selected:
        lines = ["**Not selected:**"]
        lines += [f"- {_format_non_selected(entry)}" for entry in result.non_selected]
        blocks.append("\n".join(lines))
    if result.flags:
        lines = ["**Quality flags:**"]
        lines += [f"- {_format_flag(flag)}" for flag in result.flags]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_unsupported(sport: str) -> str:
    """Render the honest unsupported-state region content (Req 7.7).

    The first line is the machine payload comment; the single human line names
    ``sport`` and contains no numbers, because no load value was computed. A
    later load pass replaces this once a supporting calculator is available.
    """
    payload = encode_payload(LoadPayload("unsupported", None, sport))
    human = f"_No training-load methodology supports {sport} activities yet._"
    return f"{payload}\n\n{human}"


def _format_value(value: float) -> str:
    """Format ``value`` with one decimal, dropping a trailing ``.0``.

    ``1700.0 -> "1700"``, ``2473.2 -> "2473.2"``.
    """
    text = f"{value:.1f}"
    if text.endswith(".0"):
        return text[:-2]
    return text


def _format_non_selected(entry: NonSelectedValue) -> str:
    """Render one non-selected entry, never fabricating a number for ``None``."""
    if entry.value is None:
        return f"**{entry.label}:** not computed — {entry.reason}"
    return f"**{entry.label}:** {_format_value(entry.value)} — {entry.reason}"


def _format_flag(flag: QualityFlag) -> str:
    """Render one quality flag."""
    return f"**{flag.label}:** {flag.verdict} — {flag.detail}"
