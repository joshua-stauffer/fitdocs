"""A test extension for the end-to-end exercise: a scripted registration provider.

`start` accepts any email except one beginning `fail`, which raises with the
email and the poll secret in the message (the failure path: the relay must log
the type only). `poll` issues a token when the poll secret matches. The poll
secret comes from the environment so the test can plant it.
"""

import logging
import os
from pathlib import Path

from fitdocs_relay.seam import (
    SEAM_VERSION,
    ExtensionContext,
    ExtensionParts,
    PollIssued,
    PollPending,
    StartAccepted,
)

POLL_SECRET_VARIABLE = "E2E_POLL_SECRET"
LOGGED_TOKEN_FILE_VARIABLE = "E2E_LOGGED_TOKEN_FILE"
_LOGGER = logging.getLogger("e2e_extension")


class Provider:
    def __init__(self, context: ExtensionContext) -> None:
        self.context = context

    def start(self, email: str) -> StartAccepted:
        secret = os.environ[POLL_SECRET_VARIABLE]
        if email.startswith("fail"):
            # A careless extension: it logs the relay's secrets through plain
            # logging. The relay's last-line redaction is all that stands
            # between this line and the output.
            logged = self.context.tokens.issue(principal_id=None, label=None)
            Path(os.environ[LOGGED_TOKEN_FILE_VARIABLE]).write_text(
                logged.token, encoding="utf-8"
            )
            _LOGGER.error(
                "provider trouble: pepper=%s database password=%s token=%s url=%s",
                os.environ["FITDOCS_RELAY_TOKEN_PEPPER"],
                os.environ.get("FITDOCS_RELAY_DATABASE_PASSWORD", "(none)"),
                logged.token,
                os.environ["FITDOCS_RELAY_DATABASE_URL"],
            )
            raise RuntimeError(f"cannot register {email} with poll secret {secret}")
        return StartAccepted("BCDF-GHJK", secret, 5, 600)

    def poll(self, poll_secret: str) -> PollIssued | PollPending:
        if poll_secret != os.environ[POLL_SECRET_VARIABLE]:
            return PollPending()
        return PollIssued(self.context.tokens.issue(principal_id=None, label=None))


class E2eExtension:
    name = "e2e"
    seam_version = SEAM_VERSION

    def build(self, context: ExtensionContext) -> ExtensionParts:
        return ExtensionParts(registration=Provider(context))


EXTENSION = E2eExtension()
