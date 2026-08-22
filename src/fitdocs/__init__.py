"""fitdocs: a pure library that decodes ``.fit`` files into a typed activity
model and computes derived metrics.

The package root is the top-level composition point -- not a layer -- so it
publishes exactly one stable public API drawn from *both*
:mod:`fitdocs.ingest` and :mod:`fitdocs.metrics`:

- the two entry points, :func:`~fitdocs.ingest.parse_fit` (bytes/path ->
  :class:`~fitdocs.model.Activity`) and
  :func:`~fitdocs.metrics.compute_metrics` (Activity + athlete inputs ->
  :class:`~fitdocs.metrics.types.DerivedMetrics`);
- the activity-model types plus the ``SCHEMA_VERSION`` / ``fit_datetime``
  helpers (:mod:`fitdocs.model`);
- the metric-input and result contracts (:mod:`fitdocs.metrics.types`),
  including :class:`~fitdocs.metrics.types.TrimpWeighting` -- a caller has no
  type-checked way to state a training-impulse weighting selection (Req 17.1)
  without importing the type that names it;
- the decode error taxonomy (:mod:`fitdocs.ingest.errors`).

**Re-exports are lazy** (PEP 562 module ``__getattr__``): the names above are
resolved from their defining submodule only on first access, and the resolution
always reads a concrete submodule, never the ``fitdocs`` package name, so no
circular import can arise. Laziness is deliberate, not incidental -- it keeps
``import fitdocs.model`` free of the ``garmin-fit-sdk`` (which
:mod:`fitdocs.ingest` imports): the model stays consumable with zero FIT-format
knowledge (Req 2.6), and the SDK loads only when a caller actually reaches for
:func:`parse_fit`. Static tooling still sees fully typed re-exports via the
``TYPE_CHECKING`` block; ``__all__`` lists the complete public surface.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Statically-visible, fully typed re-exports for type checkers and IDEs.
    # The redundant ``as`` aliases mark each name as an explicit re-export.
    from fitdocs.ingest import parse_fit as parse_fit
    from fitdocs.ingest.errors import FitDecodeError as FitDecodeError
    from fitdocs.ingest.errors import FitIntegrityError as FitIntegrityError
    from fitdocs.ingest.errors import NotFitFileError as NotFitFileError
    from fitdocs.metrics import compute_metrics as compute_metrics
    from fitdocs.metrics.types import AthleteInputs as AthleteInputs
    from fitdocs.metrics.types import DerivedMetrics as DerivedMetrics
    from fitdocs.metrics.types import TrimpWeighting as TrimpWeighting
    from fitdocs.metrics.types import ZoneSpec as ZoneSpec
    from fitdocs.model import SCHEMA_VERSION as SCHEMA_VERSION
    from fitdocs.model import Activity as Activity
    from fitdocs.model import DeviceInfo as DeviceInfo
    from fitdocs.model import Lap as Lap
    from fitdocs.model import Modality as Modality
    from fitdocs.model import Provenance as Provenance
    from fitdocs.model import Samples as Samples
    from fitdocs.model import SessionSummary as SessionSummary
    from fitdocs.model import Sport as Sport
    from fitdocs.model import StrengthSet as StrengthSet
    from fitdocs.model import fit_datetime as fit_datetime

# Public name -> (defining submodule, attribute) for lazy runtime resolution.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "parse_fit": ("fitdocs.ingest", "parse_fit"),
    "compute_metrics": ("fitdocs.metrics", "compute_metrics"),
    "Activity": ("fitdocs.model", "Activity"),
    "Samples": ("fitdocs.model", "Samples"),
    "SessionSummary": ("fitdocs.model", "SessionSummary"),
    "Lap": ("fitdocs.model", "Lap"),
    "StrengthSet": ("fitdocs.model", "StrengthSet"),
    "DeviceInfo": ("fitdocs.model", "DeviceInfo"),
    "Provenance": ("fitdocs.model", "Provenance"),
    "Sport": ("fitdocs.model", "Sport"),
    "Modality": ("fitdocs.model", "Modality"),
    "SCHEMA_VERSION": ("fitdocs.model", "SCHEMA_VERSION"),
    "fit_datetime": ("fitdocs.model", "fit_datetime"),
    "AthleteInputs": ("fitdocs.metrics.types", "AthleteInputs"),
    "ZoneSpec": ("fitdocs.metrics.types", "ZoneSpec"),
    "DerivedMetrics": ("fitdocs.metrics.types", "DerivedMetrics"),
    "TrimpWeighting": ("fitdocs.metrics.types", "TrimpWeighting"),
    "FitDecodeError": ("fitdocs.ingest.errors", "FitDecodeError"),
    "NotFitFileError": ("fitdocs.ingest.errors", "NotFitFileError"),
    "FitIntegrityError": ("fitdocs.ingest.errors", "FitIntegrityError"),
}

__all__ = [
    "SCHEMA_VERSION",
    "Activity",
    "AthleteInputs",
    "DerivedMetrics",
    "DeviceInfo",
    "FitDecodeError",
    "FitIntegrityError",
    "Lap",
    "Modality",
    "NotFitFileError",
    "Provenance",
    "Samples",
    "SessionSummary",
    "Sport",
    "StrengthSet",
    "TrimpWeighting",
    "ZoneSpec",
    "compute_metrics",
    "fit_datetime",
    "parse_fit",
]


def __getattr__(name: str) -> object:
    """Resolve a public re-export lazily from its defining submodule (PEP 562).

    The resolved object is cached back onto the module globals so later access
    skips this hook. Unknown names raise :class:`AttributeError` as usual.
    """
    try:
        module_name, attr = _LAZY_EXPORTS[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(importlib.import_module(module_name), attr)
    globals()[name] = value  # cache: subsequent lookups bypass __getattr__
    return value


def __dir__() -> list[str]:
    """Include the lazy public names in ``dir(fitdocs)``."""
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
