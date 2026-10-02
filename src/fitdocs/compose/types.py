"""The values a composition returns and the render layer reads.

Pure, frozen data: no behaviour, no I/O. ``SourceContribution``'s field names
and order are a seam read by ``render/views.py`` (``.devices``, ``.channels``).
"""

from __future__ import annotations

from dataclasses import dataclass

from fitdocs.identity.kinds import SourceKind
from fitdocs.model import Activity, DeviceInfo


@dataclass(frozen=True)
class StretchLag:
    """The lag applied to one stretch of an extra's samples."""

    start: int
    """First extra sample index of the stretch (inclusive)."""
    stop: int
    """One past the stretch's last extra sample index."""
    lag_s: int
    """The lag applied: the established one, or ``0`` on fallback."""
    key: str | None
    """The ``Samples`` channel that established it; ``None`` is the
    exact-timestamp fallback."""


@dataclass(frozen=True)
class ExtraAlignment:
    """How one extra was put on the base's timeline."""

    hour_shift_s: int
    """``0``, or ``k * SHIFT_STEP_S`` subtracted from every extra instant."""
    stretches: tuple[StretchLag, ...]
    """Every stretch's lag, in file order."""


@dataclass(frozen=True)
class Placement:
    """Where an extra's samples land on the base's samples."""

    alignment: ExtraAlignment
    extra_index: tuple[int | None, ...]
    """Per base sample: the extra sample placed there, or ``None``."""


@dataclass(frozen=True)
class SourceContribution:
    """What one file contributed to a composed page."""

    sha256: str
    """The file's ``Provenance.sha256``."""
    kind: SourceKind
    """``identity.kinds.source_kind`` of the file."""
    manufacturer: str | None
    """The file's ``FileIdentity.manufacturer``."""
    devices: tuple[DeviceInfo, ...]
    """The file's own ``Activity.devices``, never another file's."""
    channels: tuple[str, ...]
    """``Samples`` field names this file supplies with data, in field order."""
    alignment: ExtraAlignment | None
    """``None`` for the base, and for an extra that supplies nothing."""


@dataclass(frozen=True)
class ChannelProvenance:
    """Which file supplied which channel."""

    base: SourceContribution
    extras: tuple[SourceContribution, ...]
    """Every extra passed in, rank order, best first."""


@dataclass(frozen=True)
class Composition:
    """A composed activity and where its channels came from."""

    activity: Activity
    provenance: ChannelProvenance
