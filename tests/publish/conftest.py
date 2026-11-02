"""Shared fixtures for ``tests/publish`` (publish-core task 6.1).

* Page builders: :func:`run_page` and :func:`ride_page` build the page
  dictionaries the placeholder values read.
* The scripted publishing connector: :class:`ScriptedPublisher` answers each
  ``publish`` call from a queue, and :func:`registered_publisher` registers it
  for the length of a ``with`` block (the ``register_scripted_publisher``
  fixture wraps it per test) and unregisters it afterwards. The class is
  checked against the ``Connector`` and ``PostPublisher`` protocols by the
  annotated assignments at the bottom of the module, which mypy covers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from typing import Any, cast

import pytest

from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    Connector,
    ConnectorSession,
    CredentialField,
    PostPublisher,
    SettingsContext,
)
from fitdocs.connectors.settings import ConnectorInstance
from fitdocs.publish.request import PublishRequest, PublishResult
from tests.connectors.conftest import UnscriptedCall

# ------------------------------------------------------------ page builders


def run_page(**changes: object) -> dict[str, object]:
    """A run page whose figures are pairwise distinct; ``changes`` override and
    a ``None`` change removes the key."""
    page: dict[str, object] = {
        "title": "Morning Run",
        "sport": "Run",
        "modality": "run",
        "date": "2026-03-04",
        "start_time": "2026-03-04T07:05:00+01:00",
        "distance_km": 12.5,
        "moving_time": "58:20",
        "source_elapsed_s": 3725.0,
        "avg_hr_bpm": 148.6,
        "avg_power_w": 231.4,
        "elevation_gain_m": 87.6,
        "calories_kcal": 811.4,
        "load_value": 61.7,
        "load_methodology": "TRIMP",
    }
    for key, value in changes.items():
        if value is None:
            del page[key]
        else:
            page[key] = value
    return page


def ride_page(**changes: object) -> dict[str, object]:
    return run_page(modality="bike", sport="Ride", **changes)


# ------------------------------------------------- scripted publishing connector


class ScriptedPublisher:
    """A synthetic connector that declares the publish capabilities.

    ``publish_script`` holds one outcome per expected call, consumed in order:
    a ``BaseException`` is raised, anything else is returned as the answer
    (so a test can script a non-result answer on purpose). A call with
    nothing queued raises :class:`UnscriptedCall`. Every call is recorded in
    ``publish_calls`` as ``(session, request)``.
    """

    def __init__(
        self,
        *,
        connector_id: str = "scripted-publisher",
        display_name: str = "Scripted Publisher",
        auth_style: AuthStyle = AuthStyle.NONE,
        credential_fields: tuple[CredentialField, ...] = (),
        capabilities: frozenset[Capability] | None = None,
        link_label: str = "Scripted post",
    ) -> None:
        self.connector_id = connector_id
        self.display_name = display_name
        self.auth_style = auth_style
        self.credential_fields = credential_fields
        self.capabilities = (
            capabilities
            if capabilities is not None
            else frozenset({Capability.ANNOTATE_REMOTE_ACTIVITY})
        )
        self.link_label = link_label
        self.publish_script: list[object] = []
        self.publish_calls: list[tuple[ConnectorSession, PublishRequest]] = []

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> object:
        return None

    def publish(
        self, session: ConnectorSession, request: PublishRequest
    ) -> PublishResult:
        self.publish_calls.append((session, request))
        if not self.publish_script:
            raise UnscriptedCall("ScriptedPublisher.publish called with no answer")
        outcome = self.publish_script.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return cast(PublishResult, outcome)


@contextmanager
def registered_publisher(**options: Any) -> Iterator[ScriptedPublisher]:
    """Register a :class:`ScriptedPublisher` for the block, unregister after."""
    publisher = ScriptedPublisher(**options)
    connector_registry.register(publisher)
    try:
        yield publisher
    finally:
        connector_registry.unregister(publisher.connector_id)


@pytest.fixture
def register_scripted_publisher() -> Iterator[Callable[..., ScriptedPublisher]]:
    """Register scripted publishers for one test; all are unregistered after it."""
    with ExitStack() as stack:

        def make(**options: Any) -> ScriptedPublisher:
            return stack.enter_context(registered_publisher(**options))

        yield make


def publisher_instance(
    connector: Connector, *, name: str = "alpha"
) -> ConnectorInstance:
    """A configured instance of ``connector`` (no registration needed)."""
    return ConnectorInstance(
        name=name, connector=connector, lookback_days=30, settings=None
    )


# mypy checks the scripted publisher against the protocols it claims.
_typed_publisher_as_connector: Connector = ScriptedPublisher()
_typed_publisher_as_post_publisher: PostPublisher = ScriptedPublisher()
