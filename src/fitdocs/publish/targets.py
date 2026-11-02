"""Publish targets: which connector instances are targets, their state, and a
guarded send (publish-core Req 1.6, 8.6, 8.7, 12.3, 14.1, 14.2, 14.5).

A connector instance is a publish target when its connector declares
annotate-remote-activity. Listing and preparing both resolve credentials
through ``fitdocs.connectors.credentials.resolve_credentials`` with a fresh
redactor; neither makes a request, and the listing keeps no credential value.

``TargetChannel.send`` is the only place a target's answer is read. It keeps
a code, and a link only with a landed code that passes ``valid_link``. It
keeps nothing of an exception: the failure becomes the target-failure code,
and ``Delivery`` has no field that could hold an exception's text.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from fitdocs.connectors.credentials import (
    CredentialStore,
    CredentialStoreError,
    resolve_credentials,
)
from fitdocs.connectors.errors import NotConnectedError
from fitdocs.connectors.http import CallMode, HttpClient, Transport
from fitdocs.connectors.protocol import (
    PUBLISH_CAPABILITIES,
    Capability,
    ConnectorSession,
    PostPublisher,
)
from fitdocs.connectors.secrets import Redactor
from fitdocs.connectors.settings import ConnectorInstance
from fitdocs.publish.outcomes import LANDED_CODES, TARGET_CODES, PublishCode
from fitdocs.publish.request import PublishRequest, PublishResult, valid_link

__all__ = [
    "Delivery",
    "TargetChannel",
    "TargetRow",
    "is_publish_target",
    "list_targets",
    "prepare_target",
]


def is_publish_target(instance: ConnectorInstance) -> bool:
    """Whether the instance's connector declares annotate-remote-activity."""
    return Capability.ANNOTATE_REMOTE_ACTIVITY in instance.connector.capabilities


@dataclass(frozen=True)
class TargetRow:
    name: str
    connector: str
    display_name: str
    capabilities: tuple[str, ...]  # declared publish capabilities, vocabulary order
    state: PublishCode  # READY, NOT_CONNECTED or CREDENTIALS_UNREADABLE


@dataclass(frozen=True)
class Delivery:
    code: PublishCode
    link: str | None
    link_refused: bool


def _credential_state(
    instance: ConnectorInstance,
    *,
    store: CredentialStore | None,
    environ: Mapping[str, str],
    redactor: Redactor,
) -> PublishCode:
    """Resolve credentials and say only what state they are in."""
    try:
        resolve_credentials(instance.name, instance.connector, store, environ, redactor)
    except NotConnectedError:
        return PublishCode.NOT_CONNECTED
    except CredentialStoreError:
        return PublishCode.CREDENTIALS_UNREADABLE
    return PublishCode.READY


def list_targets(
    instances: Sequence[ConnectorInstance],
    *,
    store: CredentialStore | None,
    environ: Mapping[str, str],
) -> tuple[TargetRow, ...]:
    """Every publish target in name order, each with its credential state."""
    rows: list[TargetRow] = []
    for instance in sorted(instances, key=lambda candidate: candidate.name):
        if not is_publish_target(instance):
            continue
        connector = instance.connector
        rows.append(
            TargetRow(
                name=instance.name,
                connector=connector.connector_id,
                display_name=connector.display_name,
                capabilities=tuple(
                    capability.value
                    for capability in Capability
                    if capability in PUBLISH_CAPABILITIES
                    and capability in connector.capabilities
                ),
                state=_credential_state(
                    instance, store=store, environ=environ, redactor=Redactor()
                ),
            )
        )
    return tuple(rows)


class TargetChannel:
    """One prepared target: sends a request and answers with a code only."""

    def __init__(
        self,
        *,
        name: str,
        label: str,
        publisher: PostPublisher,
        session: ConnectorSession,
    ) -> None:
        self.name = name
        self.label = label
        self._publisher = publisher
        self._session = session

    def send(self, request: PublishRequest) -> Delivery:
        """Send one request. Never raises ``Exception``; an interrupt propagates."""
        delivery: Delivery | None = None
        try:
            delivery = self._interpret(self._publisher.publish(self._session, request))
        except Exception:  # noqa: BLE001 - no service text may outlive the failure
            delivery = None
        if delivery is None:
            return Delivery(PublishCode.TARGET_ERROR, None, False)
        return delivery

    @staticmethod
    def _interpret(answer: object) -> Delivery | None:
        if not isinstance(answer, PublishResult):
            return None
        offered = answer.link
        refused = offered is not None
        code = answer.code
        if not isinstance(code, PublishCode) or code not in TARGET_CODES:
            return Delivery(PublishCode.TARGET_ERROR, None, refused)
        if offered is None:
            return Delivery(code, None, False)
        if code in LANDED_CODES and valid_link(offered):
            return Delivery(code, offered, False)
        return Delivery(code, None, True)


def prepare_target(
    instance: ConnectorInstance,
    *,
    data_root: Path,
    store: CredentialStore | None,
    environ: Mapping[str, str],
    transport: Transport,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> TargetChannel | PublishCode:
    """Resolve credentials and build the data-mode session, as the pull does.

    Not connected and unreadable credentials come back as their codes; no
    request has been made in either case.
    """
    redactor = Redactor()
    try:
        credentials = resolve_credentials(
            instance.name, instance.connector, store, environ, redactor
        )
    except NotConnectedError:
        return PublishCode.NOT_CONNECTED
    except CredentialStoreError:
        return PublishCode.CREDENTIALS_UNREADABLE
    session = ConnectorSession(
        instance=instance.name,
        settings=instance.settings,
        http=HttpClient(transport, mode=CallMode.DATA, redactor=redactor, sleep=sleep),
        credentials=credentials,
        data_root=data_root,
        now=now,
        sleep=sleep,
        redactor=redactor,
    )
    publisher = cast(PostPublisher, instance.connector)
    return TargetChannel(
        name=instance.name,
        label=publisher.link_label,
        publisher=publisher,
        session=session,
    )
