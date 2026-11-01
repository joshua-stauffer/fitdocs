"""The `fitdocs-relay` operator command (OperatorCli, Requirements 3, 8.1, 8.6).

Exit codes: 0 ok; 1 the operation failed (unknown id, unreachable, schema not
current or ahead, serve refused); 2 configuration error or a usage error;
3 migrations pending (`migrate --check`). Every message printed on a failure
is a fixed form plus, at most, an identifier the operator typed; once the
configuration has loaded, all of it passes through one redactor (the token
format, the pepper, the database password), and no command prints a secret.
Only `token mint` writes a token, and only to standard output.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import secrets
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Final, cast

from fitdocs_relay.config import ConfigError, PostgresTarget, RelayConfig, load_config
from fitdocs_relay.contract import (
    ENV_DATABASE_PASSWORD,
    ENV_DATABASE_URL,
    ENV_TOKEN_PEPPER,
)
from fitdocs_relay.identity import TokenService
from fitdocs_relay.logs import SecretRedactor
from fitdocs_relay.seam import SeamError
from fitdocs_relay.serve import database_secrets, run_server
from fitdocs_relay.storage import MissingPostgresSupport, open_storage
from fitdocs_relay.storage.interface import (
    RevokeResult,
    SchemaAhead,
    Storage,
    StorageError,
    StorageUnreachable,
    UnknownPrincipal,
)
from fitdocs_relay.storage.migrate import migrate, pending

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_CONFIG: Final = 2
EXIT_PENDING: Final = 3

LABEL_MAX: Final = 64
PEPPER_BYTES: Final = 32  # secrets.token_urlsafe(32) is 43 characters

MSG_UNREACHABLE: Final = "the database is unreachable"
MSG_OPEN_FAILED: Final = "the database could not be opened"
MSG_BEHIND: Final = (
    "the database schema is not current (found {current}, expected {expected}); "
    "run 'fitdocs-relay migrate'"
)
MSG_AHEAD: Final = (
    "the database schema is newer than this build (found {current}, "
    "expected {expected})"
)
MSG_PENDING: Final = "migrations are pending"
MSG_SERVE_FAILED: Final = "the server could not start"
MSG_UNEXPECTED: Final = "unexpected failure: {kind}"
MSG_UNKNOWN_PRINCIPAL: Final = "unknown principal: {identifier}"
MSG_UNKNOWN_TOKEN: Final = "unknown token: {identifier}"
MSG_LABEL: Final = f"must be 1 to {LABEL_MAX} printable characters"
MSG_PRINCIPAL_LABEL: Final = "--principal-label needs --new-principal"


def _wall_clock() -> int:
    return int(time.time())


def _iso(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _out(line: str) -> None:
    sys.stdout.write(line + "\n")


def _err(line: str) -> None:
    sys.stderr.write(line + "\n")


def _err_raw(text: str) -> None:
    sys.stderr.write(text)


def _environment_redactor() -> SecretRedactor:
    """The token format and the raw pepper and password values, unvalidated.

    A password embedded in the raw database URL is included; a URL that cannot
    be read contributes nothing, and this builder never raises.
    """
    password = os.environ.get(ENV_DATABASE_PASSWORD)
    extra: tuple[str, ...] = ()
    url = os.environ.get(ENV_DATABASE_URL, "")
    try:
        if url.startswith(("postgresql://", "postgres://")):
            target = PostgresTarget(conninfo=url, password=password)
            extra = database_secrets(
                cast(RelayConfig, SimpleNamespace(database=target))
            )
    except Exception:  # noqa: BLE001 - a malformed URL must not break error output
        extra = ()
    return SecretRedactor(os.environ.get(ENV_TOKEN_PEPPER), password, *extra)


def _label(text: str) -> str:
    if not 1 <= len(text) <= LABEL_MAX or not text.isprintable():
        raise argparse.ArgumentTypeError(MSG_LABEL)
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fitdocs-relay", description="Operate a fitdocs relay."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("serve", help="run the relay server")

    migrate_parser = commands.add_parser("migrate", help="apply schema changes")
    migrate_parser.add_argument(
        "--check",
        action="store_true",
        help="change nothing; exit 3 when schema changes are pending",
    )

    principal = commands.add_parser("principal", help="manage principals")
    principal_commands = principal.add_subparsers(dest="action", required=True)
    create = principal_commands.add_parser("create", help="create a principal")
    create.add_argument("--label", type=_label)
    principal_commands.add_parser("list", help="list principals")
    delete = principal_commands.add_parser("delete", help="delete a principal")
    delete.add_argument("principal_id", metavar="ID")

    token = commands.add_parser("token", help="manage relay tokens")
    token_commands = token.add_subparsers(dest="action", required=True)
    mint = token_commands.add_parser("mint", help="mint a relay token")
    owner = mint.add_mutually_exclusive_group(required=True)
    owner.add_argument("--principal", metavar="ID")
    owner.add_argument("--new-principal", action="store_true")
    mint.add_argument("--label", type=_label)
    mint.add_argument("--principal-label", type=_label)
    listing = token_commands.add_parser("list", help="list relay tokens")
    listing.add_argument("--principal", metavar="ID")
    revoke = token_commands.add_parser("revoke", help="revoke a relay token")
    revoke.add_argument("token_id", metavar="TOKEN_ID")

    commands.add_parser("new-pepper", help="print a fresh token-hashing secret")
    return parser


class _Session:
    """An open, current-schema database and what an error message must hide."""

    def __init__(self, config: RelayConfig, storage: Storage) -> None:
        self.storage = storage
        self.redact = _redactor(config)
        self.tokens = TokenService(storage, pepper=config.pepper, clock=_wall_clock)


def _redactor(config: RelayConfig) -> SecretRedactor:
    return SecretRedactor(config.pepper, *database_secrets(config))


def _fail(redact: SecretRedactor, message: str, code: int = EXIT_FAILED) -> int:
    _err(redact(message))
    return code


def _listing_label(session: _Session, label: str | None) -> str:
    return "" if label is None else session.redact(label)


# --- the commands -----------------------------------------------------------


def _principal_create(session: _Session, args: argparse.Namespace) -> int:
    created = session.tokens.create_principal(args.label)
    _out(created.principal_id)
    return EXIT_OK


def _principal_list(session: _Session, args: argparse.Namespace) -> int:
    del args
    for principal in session.storage.list_principals():
        _out(
            "\t".join(
                (
                    principal.principal_id,
                    _listing_label(session, principal.label),
                    _iso(principal.created_at),
                )
            )
        )
    return EXIT_OK


def _principal_delete(session: _Session, args: argparse.Namespace) -> int:
    if not session.tokens.delete_principal(args.principal_id):
        return _fail(
            session.redact,
            MSG_UNKNOWN_PRINCIPAL.format(identifier=args.principal_id),
        )
    _out(f"deleted {args.principal_id}")
    return EXIT_OK


def _token_mint(session: _Session, args: argparse.Namespace) -> int:
    try:
        minted = session.tokens.mint(
            principal_id=args.principal,
            label=args.label,
            principal_label=args.principal_label,
        )
    except UnknownPrincipal:
        return _fail(
            session.redact,
            MSG_UNKNOWN_PRINCIPAL.format(identifier=args.principal),
        )
    _out(minted.token)
    _err(f"token_id={minted.token_id}")
    _err(f"principal_id={minted.principal_id}")
    return EXIT_OK


def _token_list(session: _Session, args: argparse.Namespace) -> int:
    if args.principal is not None and (
        session.storage.get_principal(args.principal) is None
    ):
        return _fail(
            session.redact,
            MSG_UNKNOWN_PRINCIPAL.format(identifier=args.principal),
        )
    for token in session.storage.list_tokens(args.principal):
        _out(
            "\t".join(
                (
                    token.token_id,
                    token.principal_id,
                    _listing_label(session, token.label),
                    _iso(token.created_at),
                    "active" if token.revoked_at is None else "revoked",
                    "" if token.revoked_at is None else _iso(token.revoked_at),
                )
            )
        )
    return EXIT_OK


def _token_revoke(session: _Session, args: argparse.Namespace) -> int:
    result = session.tokens.revoke(args.token_id)
    if result is RevokeResult.UNKNOWN:
        return _fail(session.redact, MSG_UNKNOWN_TOKEN.format(identifier=args.token_id))
    if result is RevokeResult.ALREADY_REVOKED:
        _out(f"already revoked {args.token_id}")
    else:
        _out(f"revoked {args.token_id}")
    return EXIT_OK


_SESSION_COMMANDS: Final[dict[tuple[str, str], Callable[..., int]]] = {
    ("principal", "create"): _principal_create,
    ("principal", "list"): _principal_list,
    ("principal", "delete"): _principal_delete,
    ("token", "mint"): _token_mint,
    ("token", "list"): _token_list,
    ("token", "revoke"): _token_revoke,
}


# --- running ----------------------------------------------------------------


def _open(config: RelayConfig, redact: SecretRedactor) -> Storage | int:
    """The opened storage, or the exit code after printing why not."""
    try:
        return open_storage(config.database)
    except MissingPostgresSupport as error:
        return _fail(redact, str(error), EXIT_CONFIG)
    except StorageUnreachable:
        return _fail(redact, MSG_UNREACHABLE)
    except StorageError:
        return _fail(redact, MSG_OPEN_FAILED)


def _require_current(storage: Storage, redact: SecretRedactor) -> int | None:
    """None when the schema is current; otherwise the exit code after printing why."""
    state = storage.schema_state()
    if state.current > state.expected:
        return _fail(
            redact, MSG_AHEAD.format(current=state.current, expected=state.expected)
        )
    if state.current < state.expected:
        return _fail(
            redact, MSG_BEHIND.format(current=state.current, expected=state.expected)
        )
    return None


def _migrate(storage: Storage, check: bool, redact: SecretRedactor) -> int:
    if check:
        state = storage.schema_state()
        if state.current > state.expected:
            return _fail(
                redact,
                MSG_AHEAD.format(current=state.current, expected=state.expected),
            )
        _out(f"schema {state.current} -> {state.expected}")
        if pending(storage):
            _err(MSG_PENDING)
            return EXIT_PENDING
        return EXIT_OK
    state = storage.schema_state()
    if state.current > state.expected:
        return _fail(
            redact, MSG_AHEAD.format(current=state.current, expected=state.expected)
        )
    report = migrate(storage, now=_wall_clock())
    _out(f"schema {report.found} -> {report.left}")
    return EXIT_OK


def _run_on_storage(args: argparse.Namespace, config: RelayConfig) -> int:
    redact = _redactor(config)
    opened = _open(config, redact)
    if isinstance(opened, int):
        return opened
    storage = opened
    try:
        try:
            if args.command == "migrate":
                return _migrate(storage, args.check, redact)
            refused = _require_current(storage, redact)
            if refused is not None:
                return refused
            handler = _SESSION_COMMANDS[(args.command, args.action)]
            return handler(_Session(config, storage), args)
        except SchemaAhead as error:
            return _fail(redact, str(error))
        except StorageUnreachable:
            return _fail(redact, MSG_UNREACHABLE)
    finally:
        storage.close()


def _serve(config: RelayConfig) -> int:
    redact = _redactor(config)
    try:
        return run_server(config)
    except SeamError as error:
        return _fail(redact, str(error), EXIT_CONFIG)
    except MissingPostgresSupport as error:
        return _fail(redact, str(error), EXIT_CONFIG)
    except SystemExit as stop:
        # uvicorn exits 3 when it cannot start (e.g. the port is taken); 3 is
        # this command's "migrations pending", so it is reported as 1.
        if stop.code in (None, 0):
            return EXIT_OK
        return _fail(redact, MSG_SERVE_FAILED)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command; the return value is the process exit code."""
    # argparse echoes an offending argument; it is printed through a redactor
    # built from the raw environment, before any configuration is loaded.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stderr(captured):
            args = build_parser().parse_args(argv)
    except SystemExit as stop:
        _err_raw(_environment_redactor()(captured.getvalue()))
        return stop.code if isinstance(stop.code, int) else EXIT_CONFIG
    if args.command == "new-pepper":
        _out(secrets.token_urlsafe(PEPPER_BYTES))
        return EXIT_OK
    if (
        (args.command, getattr(args, "action", None)) == ("token", "mint")
        and args.principal is not None
        and args.principal_label is not None
    ):
        # The label belongs to a principal this command would create.
        _err(f"fitdocs-relay: {MSG_PRINCIPAL_LABEL}")
        return EXIT_CONFIG
    try:
        config = load_config()
    except ConfigError as error:
        _err(str(error))
        return EXIT_CONFIG
    try:
        if args.command == "serve":
            return _serve(config)
        return _run_on_storage(args, config)
    except Exception as error:  # noqa: BLE001 - the last line: type name only
        return _fail(
            _redactor(config), MSG_UNEXPECTED.format(kind=type(error).__name__)
        )
