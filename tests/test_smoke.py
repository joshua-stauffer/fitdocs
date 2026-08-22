"""Smoke test: the package imports cleanly on a fresh checkout."""

import fitdocs


def test_package_imports() -> None:
    assert fitdocs.__doc__ is not None


def test_public_api_exports_entry_points() -> None:
    # The package root now re-exports the public surface; the two entry points
    # must be present in __all__ (full coverage lives in test_public_api.py).
    assert "parse_fit" in fitdocs.__all__
    assert "compute_metrics" in fitdocs.__all__
