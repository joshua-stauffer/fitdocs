"""Derivation of dated athlete benchmarks from tagged workout documents.

Published surface: the pure names first, then the pass entry point --
appended by task 4.3, now that the engine exists (design: PerformanceTypes'
`__init__.py` note). This is the one addition this file makes after 1.1: the
five names above and their `__all__` order are unchanged, and
`derive_benchmarks` is appended last rather than inserted alphabetically.
"""

from __future__ import annotations

from fitdocs.performance.engine import derive_benchmarks as derive_benchmarks
from fitdocs.performance.types import DeclineReason as DeclineReason
from fitdocs.performance.types import DerivationDeclined as DerivationDeclined
from fitdocs.performance.types import DerivationMethod as DerivationMethod
from fitdocs.performance.types import DerivationOutcome as DerivationOutcome
from fitdocs.performance.types import DerivedBenchmark as DerivedBenchmark

__all__ = [
    "DeclineReason",
    "DerivationDeclined",
    "DerivationMethod",
    "DerivationOutcome",
    "DerivedBenchmark",
    "derive_benchmarks",
]
