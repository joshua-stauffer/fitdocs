"""The three training-load channels: Power, Heart Rate and Pace.

This package is a **re-export point**: given one activity, one already-
resolved threshold benchmark and one resolved sufficiency configuration, each
channel returns either a load value on the shared "one hour at threshold =
100" scale or a typed statement of why no honest value exists. Nothing in
this layer reads a file, consults a clock, prompts, or decides which channel
wins -- that is ``threshold-load``'s job.

This module itself holds no logic and performs no import side effect (Req
9.7): every name below is a direct re-export of an object already fully
defined in a leaf module, bound once at package-import time. Nothing is
computed, registered, or resolved here.

**What is published (design: ChannelSurface, Req 9.1-9.7).**

- The channel-result vocabulary and the sufficiency configuration it is
  scored against -- :class:`ChannelId`, :class:`InsufficiencyReason`,
  :class:`StreamCoverage`, :class:`ChannelLoad`, :class:`ChannelInsufficient`,
  :data:`ChannelOutcome`, :class:`SufficiencySettings`,
  :func:`require_kind`, :data:`DEFAULT_MIN_STREAM_COVERAGE` and
  :data:`DEFAULT_MIN_DURATION_S` -- all defined in ``types.py``.
- The three computation entry points, each bound under a **channel-qualified**
  name so all three can be imported from one place without colliding on the
  bare name ``compute``: ``power.py``, ``heart_rate.py`` and ``pace.py`` each
  define their own module-level ``compute`` (the package's other five leaf
  modules -- ``grade.py``, ``sufficiency.py``, ``types.py``, ``weighting.py``
  and ``sources.py`` -- do not) --
  :func:`power_compute`, :func:`heart_rate_compute`, :func:`pace_compute`.
- The heart-rate weighting seam and its one shipped instance --
  :class:`HeartRateIntensityModel`, :data:`BANISTER_TRIMP_MODEL` -- from
  ``weighting.py``.
- The provenance records -- :class:`Citation`, :class:`VerificationStatus`,
  :class:`Divergence`, :data:`CITATIONS`, :data:`DIVERGENCES` and
  :data:`BLOCKED_CITATIONS` -- from ``sources.py``.

**What is deliberately absent.** ``load/settings.py``'s ``[load.sufficiency]``
projection (``load_load_settings``, owned by ``training-load``) is not part
of this surface: this package hands callers the *type* it is projected into
(``SufficiencySettings``) and nothing that reads a settings file, matching
Req 3.9 -- a channel receives resolved configuration, it never reads it.
Nothing internal to ``grade.py`` or ``sufficiency.py`` is re-exported either;
both stay reachable only via their own module path. This is this module's own
scope choice: design.md's "Package surface" section (ChannelSurface /
PublicSurfacePin) is marked ``Summary-only.`` and names only
``HeartRateIntensityModel`` among the re-exports, so it is not read here as
an exhaustive enumeration and makes no statement about ``grade.py`` or
``sufficiency.py`` by name either way.

``tests/test_public_api.py`` pins this surface: its ``__all__`` for exact
membership, the shape of ``ChannelLoad``, ``ChannelInsufficient`` and
``InsufficiencyReason`` by real dataclass/enum introspection, and the three
``*_compute`` names' identity against their defining module in a fresh
interpreter (the reload hazard ``test_pace.py`` and ``test_grade.py``
exercise on their own modules makes an in-process identity check order-
dependent; a fresh interpreter sidesteps that entirely).
"""

from __future__ import annotations

from fitdocs.load.channels.heart_rate import compute as heart_rate_compute
from fitdocs.load.channels.pace import compute as pace_compute
from fitdocs.load.channels.power import compute as power_compute
from fitdocs.load.channels.sources import BLOCKED_CITATIONS as BLOCKED_CITATIONS
from fitdocs.load.channels.sources import CITATIONS as CITATIONS
from fitdocs.load.channels.sources import DIVERGENCES as DIVERGENCES
from fitdocs.load.channels.sources import Citation as Citation
from fitdocs.load.channels.sources import Divergence as Divergence
from fitdocs.load.channels.sources import VerificationStatus as VerificationStatus
from fitdocs.load.channels.types import (
    DEFAULT_MIN_DURATION_S as DEFAULT_MIN_DURATION_S,
)
from fitdocs.load.channels.types import (
    DEFAULT_MIN_STREAM_COVERAGE as DEFAULT_MIN_STREAM_COVERAGE,
)
from fitdocs.load.channels.types import ChannelId as ChannelId
from fitdocs.load.channels.types import ChannelInsufficient as ChannelInsufficient
from fitdocs.load.channels.types import ChannelLoad as ChannelLoad
from fitdocs.load.channels.types import ChannelOutcome as ChannelOutcome
from fitdocs.load.channels.types import InsufficiencyReason as InsufficiencyReason
from fitdocs.load.channels.types import StreamCoverage as StreamCoverage
from fitdocs.load.channels.types import SufficiencySettings as SufficiencySettings
from fitdocs.load.channels.types import require_kind as require_kind
from fitdocs.load.channels.weighting import (
    BANISTER_TRIMP_MODEL as BANISTER_TRIMP_MODEL,
)
from fitdocs.load.channels.weighting import (
    HeartRateIntensityModel as HeartRateIntensityModel,
)

__all__ = [
    "BANISTER_TRIMP_MODEL",
    "BLOCKED_CITATIONS",
    "CITATIONS",
    "ChannelId",
    "ChannelInsufficient",
    "ChannelLoad",
    "ChannelOutcome",
    "Citation",
    "DEFAULT_MIN_DURATION_S",
    "DEFAULT_MIN_STREAM_COVERAGE",
    "DIVERGENCES",
    "Divergence",
    "HeartRateIntensityModel",
    "InsufficiencyReason",
    "StreamCoverage",
    "SufficiencySettings",
    "VerificationStatus",
    "heart_rate_compute",
    "pace_compute",
    "power_compute",
    "require_kind",
]
