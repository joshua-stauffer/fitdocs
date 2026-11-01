"""A target that renews its credentials through its session updates only that
instance's credentials file (ownership contract, the ``publish`` entry)."""

from __future__ import annotations

from collections.abc import Mapping

from fitdocs.connectors.credentials import CredentialStore, StoredCredentials
from fitdocs.connectors.protocol import (
    AuthStyle,
    ConnectorSession,
    CredentialField,
    TokenSet,
)
from fitdocs.connectors.secrets import Secret
from fitdocs.publish.request import PublishRequest, PublishResult
from tests.publish.conftest import ScriptedPublisher
from tests.publish.test_cli_publish import (  # noqa: F401
    POSTED,
    World,
    invoke,
    register,
    world,
)
from tests.publish.test_engine import SHA_A


class RotatingPublisher(ScriptedPublisher):
    def verify(self, session: ConnectorSession, values: Mapping[str, Secret]) -> object:
        raise AssertionError

    def publish(
        self, session: ConnectorSession, request: PublishRequest
    ) -> PublishResult:
        session.credentials.replace(
            TokenSet(
                values={"api_key": Secret("rotated-key")},
                expires_at=None,
                scopes=None,
            )
        )
        return super().publish(session, request)


def _stored(key: str) -> StoredCredentials:
    return StoredCredentials(
        connector_id="scripted-alpha",
        auth_style=AuthStyle.API_KEY,
        values={"api_key": Secret(key)},
        expires_at=None,
        scopes=None,
    )


def test_publish_yes_updates_only_the_renewing_instances_credentials_file(
    world: World,  # noqa: F811
) -> None:
    pub = RotatingPublisher(
        connector_id="scripted-alpha",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", "Key", True),),
    )
    world.targets["alpha"] = pub
    world.settings()
    register(world)
    world.page("a.md", SHA_A)
    pub.publish_script.append(POSTED)
    store = CredentialStore(world.credentials)
    alpha = store.save("alpha", _stored("stored-key"))
    other = store.save("other", _stored("other-key"))
    alpha_before, other_before = alpha.read_bytes(), other.read_bytes()
    result = invoke(["--yes", "--out", str(world.root)])
    assert result.exit_code == 0, result.output
    assert alpha.read_bytes() != alpha_before
    assert b"rotated-key" in alpha.read_bytes()
    assert other.read_bytes() == other_before
    assert sorted(p.name for p in world.credentials.iterdir()) == sorted(
        [alpha.name, other.name]
    )
