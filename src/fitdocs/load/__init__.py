"""The load layer: pluggable training-load calculators and the load pass.

This package turns each workout into a single comparable training-load number
through a pluggable calculator contract, owns the athlete profile store, and
writes results into the reserved load section and frontmatter of workout
documents. It is the carrier -- the contract, the registry, the profile store,
the prompt flow, and the document integration -- and ships no methodology of
its own (Req 13.2).

Importing this package registers no built-in calculator: ``available()`` is
empty on a fresh interpreter, and stays empty until a plugin author or a
downstream spec registers one.
"""

from __future__ import annotations

from fitdocs.benchmarks import Benchmark, BenchmarkAge, BenchmarkKind, benchmark_age
from fitdocs.load import registry
from fitdocs.load.registry import (
    DuplicateCalculatorIdError,
    InvalidCalculatorError,
    UnknownCalculatorError,
    available,
    for_modality,
    get,
    register,
)
from fitdocs.load.settings import (
    DEFAULT_LOAD_SETTINGS,
    LoadSettings,
    LoadSettingsError,
)
from fitdocs.load.types import (
    AthleteField,
    BenchmarkRef,
    Computed,
    InteractionSession,
    LoadCalculator,
    LoadContext,
    LoadOutcome,
    LoadResult,
    MissingInputs,
    NonSelectedValue,
    NotComputed,
    ProfileView,
    QualityFlag,
    Unsupported,
    supports_activity,
)

__all__ = [
    "AthleteField",
    "Benchmark",
    "BenchmarkAge",
    "BenchmarkKind",
    "BenchmarkRef",
    "Computed",
    "DEFAULT_LOAD_SETTINGS",
    "DuplicateCalculatorIdError",
    "InteractionSession",
    "InvalidCalculatorError",
    "LoadCalculator",
    "LoadContext",
    "LoadOutcome",
    "LoadResult",
    "LoadSettings",
    "LoadSettingsError",
    "MissingInputs",
    "NonSelectedValue",
    "NotComputed",
    "ProfileView",
    "QualityFlag",
    "UnknownCalculatorError",
    "Unsupported",
    "available",
    "benchmark_age",
    "for_modality",
    "get",
    "register",
    "registry",
    "supports_activity",
]
