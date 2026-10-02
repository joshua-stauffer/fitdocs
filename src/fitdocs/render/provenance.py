"""The ``## Channel Sources`` section body (channel-merge Req 4.1-4.6, 4.8).

States which file each channel of a composed page came from and how each extra
was put on the base's timeline. Pure: a string out of a
:class:`~fitdocs.render.DocContext`; it reads no frontmatter and writes none.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from fitdocs.compose.alignment import ALIGNMENT_KEYS
from fitdocs.compose.types import ExtraAlignment, SourceContribution
from fitdocs.identity.kinds import SourceKind
from fitdocs.layout import source_ref
from fitdocs.render import DocContext
from fitdocs.render.format import ABSENT

__all__ = ["CHANNEL_LABELS", "channel_sources_section"]

CHANNEL_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "heart_rate_bpm": "Heart rate",
        "power_w": "Power",
        "cadence_rpm": "Cadence",
        "speed_mps": "Speed",
        "distance_m": "Distance",
        "altitude_m": "Altitude",
        "latitude_deg": "GPS",
        "longitude_deg": "GPS",
        "temperature_c": "Temperature",
        "stance_time_ms": "Ground contact time",
        "stance_time_balance_pct": "Ground contact time balance",
        "vertical_oscillation_mm": "Vertical oscillation",
        "vertical_oscillation_balance_pct": "Vertical oscillation balance",
        "vertical_ratio_pct": "Vertical ratio",
        "step_length_mm": "Step length",
        "leg_spring_stiffness_kn_m": "Leg spring stiffness",
        "leg_spring_stiffness_balance_pct": "Leg spring stiffness balance",
        "form_power_w": "Form power",
        "air_power_w": "Air power",
        "impact_bw": "Impact",
        "impact_loading_rate_balance_pct": "Impact loading rate balance",
    }
)

_SENTENCE: Final[str] = (
    "Each channel below comes from one file: the base when it records the "
    "channel, otherwise the highest-ranked extra that records it."
)
_HEADER: Final[str] = (
    "| File | Role | Kind | Channels | Alignment |\n| --- | --- | --- | --- | --- |"
)
_SECONDS_PER_HOUR: Final[int] = 3600
_FALLBACK_PART: Final[str] = "at exact timestamps (no lag established)"


def _kind_text(contribution: SourceContribution) -> str:
    if contribution.kind is SourceKind.PHONE_COPY:
        return "phone copy"
    if contribution.kind is SourceKind.ORIGINAL:
        if contribution.manufacturer is None:
            return "original"
        return f"original ({contribution.manufacturer})"
    return "unknown"


def _channels_text(channels: tuple[str, ...]) -> str:
    labels: list[str] = []
    for channel in channels:
        label = CHANNEL_LABELS[channel]
        if label not in labels:
            labels.append(label)
    return ", ".join(labels) if labels else ABSENT


def _alignment_text(alignment: ExtraAlignment | None) -> str:
    if alignment is None:
        return ABSENT
    parts: list[str] = []
    for key in ALIGNMENT_KEYS:
        count = sum(1 for s in alignment.stretches if s.key == key.channel)
        if count:
            parts.append(f"{count} by {key.label}")
    fallback = sum(1 for s in alignment.stretches if s.key is None)
    if fallback:
        parts.append(f"{fallback} {_FALLBACK_PART}")
    total = len(alignment.stretches)
    noun = "stretch" if total == 1 else "stretches"
    text = f"{total} {noun}: {', '.join(parts)}"
    if alignment.hour_shift_s != 0:
        moved = -alignment.hour_shift_s // _SECONDS_PER_HOUR
        text = f"moved {moved:+d} h to the base's clock; {text}"
    return text


def _row(contribution: SourceContribution, role: str) -> str:
    return (
        f"| `{source_ref(contribution.sha256)}` | {role} "
        f"| {_kind_text(contribution)} "
        f"| {_channels_text(contribution.channels)} "
        f"| {_alignment_text(contribution.alignment)} |"
    )


def channel_sources_section(ctx: DocContext) -> str | None:
    """The section body, or ``None`` with no provenance or no extra (Req 4.6)."""
    provenance = ctx.channel_provenance
    if provenance is None or not provenance.extras:
        return None
    rows = [_row(provenance.base, "base")]
    rows.extend(_row(extra, "extra") for extra in provenance.extras)
    return "\n".join([_SENTENCE, "", _HEADER, *rows])
