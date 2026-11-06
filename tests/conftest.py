"""Shared pytest fixtures for the fitdocs test suite.

Encoded synthetic ``.fit`` byte fixtures are produced by
:mod:`tests.fixtures.builder`; they are session-scoped because every builder is
deterministic and side-effect-free, so one shared instance is safe to reuse. The
decoded message-dict builders there (:func:`~tests.fixtures.builder.run_messages`
and friends) return the dicts later extractor unit-tests consume directly.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Generator
from dataclasses import replace
from pathlib import Path

import pytest

from fitdocs import inbox, plugins
from tests.fixtures import builder
from tests.support import network

network.install()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown() -> Generator[None, object, object]:
    """Fail a test that tried to leave this machine, once its own teardown has run.

    The attempt was already refused. This is what makes it visible when the code
    under test handled the refusal and the test would otherwise pass.
    """
    try:
        return (yield)
    finally:
        attempts = network.take_attempts()
        if attempts:
            pytest.fail(
                f"this test tried to reach {sorted(set(attempts))}. Tests stay on "
                "this machine: inject a fake instead (map tiles: "
                'monkeypatch.setattr("fitdocs.tiles._default_fetch", '
                "tile_factory.fetch_stub()), from tests/support/tiles.py).",
                pytrace=False,
            )


@pytest.fixture(scope="session")
def per_test_directory(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[str], Path]:
    """Make a new directory for one test, cheaply enough to do for every test.

    ``tmp_path_factory.mktemp`` lists the whole base temp directory to choose the
    next number, so an autouse fixture calling it once per test makes the suite's
    run time quadratic in its test count: on 32,696 tests that scan was 65% of a
    serial run. A shared parent and a counter avoid the listing.
    """
    parent = tmp_path_factory.mktemp("per-test")
    counter = itertools.count()

    def make(name: str) -> Path:
        directory = parent / f"{name}-{next(counter)}"
        directory.mkdir()
        return directory

    return make


@pytest.fixture
def no_settle_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the inbox's default 2 s wait, for a test that drains with no settings.

    A test that writes a settings file says ``settle_seconds = 0`` there instead.
    """
    monkeypatch.setattr(
        inbox,
        "DEFAULT_INBOX_SETTINGS",
        replace(inbox.DEFAULT_INBOX_SETTINGS, settle_seconds=0.0),
    )


@pytest.fixture(autouse=True)
def _isolate_index_directory(
    per_test_directory: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give each test its own temporary analytics-index directory."""
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(per_test_directory("fitdocs-index")))


@pytest.fixture(autouse=True)
def _reset_plugin_discovery() -> None:
    """Unregister every plugin-attributed calculator id after each test.

    ``fitdocs.load.registry`` is a process-global store and a discovery test
    that registers plugin calculators would otherwise leak them into
    unrelated tests. This fixture calls :func:`fitdocs.plugins.reset`, which
    unregisters only the ids it attributed to a plugin channel -- never a
    built-in -- so any built-in calculator is never disturbed.
    """
    plugins.reset()


@pytest.fixture(scope="session")
def run_fit_bytes() -> bytes:
    """Outdoor-run ``.fit`` bytes: GPS, heart rate, cadence, three laps."""
    return builder.run_fit_bytes()


@pytest.fixture(scope="session")
def ride_fit_bytes() -> bytes:
    """Ride ``.fit`` bytes: power, heart rate, cadence, plain speed (no GPS)."""
    return builder.ride_fit_bytes()


@pytest.fixture(scope="session")
def strength_fit_bytes() -> bytes:
    """Strength-session ``.fit`` bytes: ``set_mesgs`` with partial fields."""
    return builder.strength_fit_bytes()


@pytest.fixture(scope="session")
def minimal_fit_bytes() -> bytes:
    """Minimal ``.fit`` bytes: records only, no ``session`` message."""
    return builder.minimal_fit_bytes()


@pytest.fixture(scope="session")
def non_fit_bytes() -> bytes:
    """Bytes with no valid FIT header (``is_fit`` is False)."""
    return builder.non_fit_bytes()


@pytest.fixture(scope="session")
def truncated_fit_bytes() -> bytes:
    """A valid file cut short so its integrity check fails."""
    return builder.truncated_fit_bytes()


@pytest.fixture(scope="session")
def bad_message_fit_bytes() -> bytes:
    """A valid file that decodes overall while surfacing a message-level error."""
    return builder.bad_message_fit_bytes()


# --- Real-shaped variants (task 1.6) ----------------------------------------


@pytest.fixture(scope="session")
def run_native_power_sparse_hr_fit_bytes() -> bytes:
    """Run ``.fit`` bytes: native power on every sample, sparse heart rate."""
    return builder.run_native_power_sparse_hr_fit_bytes()


@pytest.fixture(scope="session")
def run_no_gps_fit_bytes() -> bytes:
    """Run ``.fit`` bytes: no GPS position and no altitude channel."""
    return builder.run_no_gps_fit_bytes()


@pytest.fixture(scope="session")
def ride_no_power_fit_bytes() -> bytes:
    """Ride ``.fit`` bytes: no power channel (HR + speed hero fallback)."""
    return builder.ride_no_power_fit_bytes()


@pytest.fixture(scope="session")
def strength_no_sets_fit_bytes() -> bytes:
    """Strength ``.fit`` bytes: HR-only records and NO set messages."""
    return builder.strength_no_sets_fit_bytes()


@pytest.fixture(scope="session")
def session_dev_fields_fit_bytes() -> bytes:
    """Run ``.fit`` bytes carrying session-scoped HealthFit developer fields."""
    return builder.session_dev_fields_fit_bytes()


@pytest.fixture(scope="session")
def session_dev_fields_declared_scale_fit_bytes() -> bytes:
    """Run ``.fit`` bytes like ``session_dev_fields_fit_bytes`` but ``AVG METs``
    declares ``scale=100`` on its ``field_description`` (Req 14.2, as amended)."""
    return builder.session_dev_fields_declared_scale_fit_bytes()


@pytest.fixture(scope="session")
def reexport_a_fit_bytes() -> bytes:
    """Re-export pair, file A: fixed ``SESSION UUID``, distinct bytes."""
    return builder.reexport_a_fit_bytes()


@pytest.fixture(scope="session")
def reexport_b_fit_bytes() -> bytes:
    """Re-export pair, file B: SAME ``SESSION UUID`` as A, different bytes."""
    return builder.reexport_b_fit_bytes()
