"""A trivial RUN load calculator advertised via a distribution entry point.

This module is built into the ``fitdocs-fixture-calc`` fixture distribution
(``tests/fixtures/plugin_pkg/pyproject.toml``) and exists solely so
``tests/test_plugins_install.py`` can install a REAL third-party distribution
alongside fitdocs and prove that entry-point discovery (Req 1.1, 4.1-4.3, 6.1)
finds it in a genuinely installed environment, not only via an injected
``entry_points_fn`` in unit tests. It imports only ``fitdocs`` -- co-installed
alongside this fixture -- and no third-party dependencies.

``FixtureCalculator`` is never called by anything: it never computes, it only
needs to satisfy the ``LoadCalculator`` contract shape well enough to register.
"""

from __future__ import annotations

from fitdocs import Modality
from fitdocs.load import Unsupported


class FixtureCalculator:
    """A minimal, valid ``LoadCalculator`` for RUN, advertised by an entry point."""

    calculator_id = "fixture-calc"
    display_name = "Fixture Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[object, ...]:
        return ()

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: object,
    ) -> Unsupported:
        return Unsupported(reason="fixture calculator never computes")
