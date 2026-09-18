"""Quality-flag verdicts about the data behind a computed load: cadence
lock, cross-channel divergence, aerobic drift and benchmark staleness
(design: Overview, FlagVocabulary).

This package reads sample streams and channel outcomes and emits typed
verdicts -- detected / not-detected / not-assessed, each carrying its basis
-- attached to the load result and rendered into the document. It computes
no load, adjusts no load, and provides no path by which a verdict could
reach a value (Req 9.1, 9.2).

This is an **ordinary eager** package initializer: every name below is a
plain re-export bound at import time, with no lazy ``__getattr__`` and no
``TYPE_CHECKING``-only import. An earlier design revision required this
package root to re-export only leaf vocabulary and, later, to defer its
imports to avoid a real import cycle; both constraints are withdrawn. The
cycle they guarded against -- ``load/types.py`` importing ``load/settings.py``
importing this package for :class:`~fitdocs.load.qa.types.FlagSettings`,
reproduced on every entry point -- is cut upstream by ``training-load``'s
``TYPE_CHECKING``-only import of ``LoadSettings`` in
``src/fitdocs/load/types.py``, so nothing here needs to guard against it.

This module re-exports ``qa/types.py``'s leaf vocabulary alongside
``evaluate_flags`` from ``qa/flags.py``, both the same way -- a plain
``from .flags import evaluate_flags``.
"""

from __future__ import annotations

from fitdocs.load.qa.flags import evaluate_flags as evaluate_flags
from fitdocs.load.qa.types import (
    DEFAULT_AEROBIC_DRIFT_MAX_PCT as DEFAULT_AEROBIC_DRIFT_MAX_PCT,
)
from fitdocs.load.qa.types import (
    DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM as DEFAULT_CADENCE_LOCK_MAX_DELTA_BPM,
)
from fitdocs.load.qa.types import (
    DEFAULT_CADENCE_LOCK_MIN_CORRELATION as DEFAULT_CADENCE_LOCK_MIN_CORRELATION,
)
from fitdocs.load.qa.types import (
    DEFAULT_CADENCE_LOCK_MIN_DURATION_S as DEFAULT_CADENCE_LOCK_MIN_DURATION_S,
)
from fitdocs.load.qa.types import (
    DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE as DEFAULT_CADENCE_LOCK_MIN_PAIRED_COVERAGE,  # noqa: E501
)
from fitdocs.load.qa.types import (
    DEFAULT_CADENCE_LOCK_WINDOW_S as DEFAULT_CADENCE_LOCK_WINDOW_S,
)
from fitdocs.load.qa.types import (
    DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA as DEFAULT_DIVERGENCE_MAX_INTENSITY_DELTA,
)
from fitdocs.load.qa.types import FLAG_LABELS as FLAG_LABELS
from fitdocs.load.qa.types import FLAG_ORDER as FLAG_ORDER
from fitdocs.load.qa.types import (
    STEPS_PER_CADENCE_REVOLUTION as STEPS_PER_CADENCE_REVOLUTION,
)
from fitdocs.load.qa.types import FlagKey as FlagKey
from fitdocs.load.qa.types import FlagSettings as FlagSettings
