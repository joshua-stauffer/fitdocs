"""The load layer: pluggable training-load calculators and the load pass.

This package turns each workout into a single comparable training-load number
through a pluggable calculator contract, owns the athlete profile store, and
writes results into the reserved load section and frontmatter of workout
documents. It is the carrier -- the contract, the registry, the profile store,
the prompt flow, and the document integration. ``training-load`` (Req 13.2)
shipped it with no methodology of its own; ``threshold-load`` supersedes that
by registering fitdocs' first and only built-in here.

Importing this package registers fitdocs' one built-in calculator: on a fresh
interpreter, ``available()`` returns exactly ``(THRESHOLD_CALCULATOR,)``,
addressed by the id ``"threshold"`` (``threshold-load``, Req 1.1-1.3). This
supersedes ``training-load`` Req 13.2's "the registry is empty of
built-ins" (a recorded revalidation trigger there): the ``register()`` call
lives here, in the package initializer, rather than in
``fitdocs.load.threshold`` or its ``calculator`` module -- so importing
either of those alone never performs a *second*, duplicate registration of
its own (Python still runs this file first, as this package's parent, and so
still registers the built-in once on any import path that reaches a leaf
under it). The registration goes through the same
:func:`~fitdocs.load.registry.register` gate -- and the same
:func:`~fitdocs.load.registry.validate_calculator` validation -- every
third-party calculator passes; the built-in needs no privilege a plugin
author lacks.
"""

from __future__ import annotations

from fitdocs.benchmarks import Benchmark, BenchmarkAge, BenchmarkKind, benchmark_age
from fitdocs.load import registry
from fitdocs.load.qa import FlagKey, FlagSettings
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
from fitdocs.load.threshold.calculator import THRESHOLD_CALCULATOR
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
    "FlagKey",
    "FlagSettings",
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
    "THRESHOLD_CALCULATOR",
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

# Registers fitdocs' one built-in calculator at package-import time (Req
# 1.1-1.3, threshold-load design: BuiltInRegistration). Goes through the
# same validation gate -- validate_calculator, via register() -- every
# third-party calculator passes; no bypass, no privileged path. The call
# lives here, not in fitdocs.load.threshold or its calculator module, so
# neither of those performs a second, duplicate registration of its own.
register(THRESHOLD_CALCULATOR)
