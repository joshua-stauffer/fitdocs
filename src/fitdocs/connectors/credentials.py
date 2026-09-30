"""Per-user credentials and tokens, outside the data root (Req 4.1-4.9).

Nothing secret touches the data root: a connector's credentials live in one
TOML file per configured instance, inside a per-user directory this module
resolves from the environment or the user's home -- never inside the data
root, which may be a git repository or a shared wiki (Req 4.1, 4.2). The
directory and every credentials file are created owner-only, and every write
goes through :func:`fitdocs.connectors._atomic.write_atomic` so an
interruption never leaves a partial file (Req 4.3). A file any other user
could read or write is refused outright, naming the fix (Req 4.4).

:func:`resolve_credentials_dir` implements the three-step location order
(Req 4.1); :func:`check_outside_data_root` is the standalone refusal check
(Req 4.2); :func:`env_var_name` builds the one environment-variable name a
personal-key connector's field can be overridden from (Req 4.5).

:class:`CredentialStore` is the plain owner-only file store for one resolved
directory: :meth:`~CredentialStore.load` and :meth:`~CredentialStore.save`
read and write a single instance's :class:`StoredCredentials` -- the
connector id, auth style, values, expiry and granted scopes -- and never
prompt, log the clock, or interpret a connector's own field names.

:func:`resolve_credentials` is the higher-level read a connector session
uses: it builds a :class:`ResolvedCredentials` (a
:class:`fitdocs.connectors.protocol.CredentialAccess`) for one instance,
applying the auth-style rules design.md states -- ``NONE`` has no values,
``API_KEY`` prefers a non-empty environment variable over the stored value
per field and reports which field and variable are missing when neither is
set, ``LOGIN`` reads only the store (an environment override could not be
written back for a rotating token) and its :meth:`~ResolvedCredentials.replace`
persists a new token set before returning -- and refuses an instance whose
stored credentials were issued for a different connector (Req 4.6-4.9).
Every value :func:`resolve_credentials` hands back is registered with the
caller's :class:`~fitdocs.connectors.secrets.Redactor` before it is
returned.

This module imports :mod:`tomli_w` (an existing runtime dependency) and
:mod:`fitdocs.connectors._atomic`, as design.md's "Allowed Dependencies"
permits; ``tomli_w`` may be imported only here and in
``connectors/ledger.py``, which also uses it for its own TOML file.
"""

from __future__ import annotations

import os
import stat
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

import tomli_w

from fitdocs.connectors._atomic import write_atomic
from fitdocs.connectors.errors import ConnectorError, NotConnectedError
from fitdocs.connectors.protocol import AuthStyle, Connector, CredentialAccess, TokenSet
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.settings import SettingsError

CREDENTIALS_DIR_ENV: Final[str] = "FITDOCS_CREDENTIALS_DIR"
XDG_CONFIG_HOME_ENV: Final[str] = "XDG_CONFIG_HOME"
ENV_PREFIX: Final[str] = "FITDOCS_CONNECTOR_"
CREDENTIALS_VERSION: Final[int] = 1


class CredentialsLocationError(SettingsError):
    """The resolved credentials directory is unusable (exit 2 at the CLI).

    Raised when the dedicated environment variable is set to a relative
    path (Req 4.1), or when the resolved directory is the data root or lies
    inside it (Req 4.2).
    """


class CredentialStoreError(Exception):
    """A stored credentials file could not be trusted.

    Raised for a file no other user should be able to read but can, a file
    that cannot be read or is not valid TOML, or one that records a newer
    ``credentials_version`` than this version of fitdocs reads (Req 4.4,
    4.9).
    """


def resolve_credentials_dir(environ: Mapping[str, str], home: Path) -> Path:
    """Resolve the per-user credentials directory (Req 4.1).

    Order: ``FITDOCS_CREDENTIALS_DIR`` when set to a non-empty value (which
    must then be absolute, else :class:`CredentialsLocationError`); else
    ``$XDG_CONFIG_HOME/fitdocs/credentials`` when that variable is set to a
    non-empty *absolute* path (a set-but-relative value is silently skipped,
    not an error -- only the dedicated variable is authoritative enough to
    fail loudly); else ``<home>/.config/fitdocs/credentials``.
    """
    dedicated = environ.get(CREDENTIALS_DIR_ENV, "")
    if dedicated:
        candidate = Path(dedicated)
        if not candidate.is_absolute():
            raise CredentialsLocationError(
                f"{CREDENTIALS_DIR_ENV}={dedicated!r} is not an absolute path"
            )
        return candidate

    xdg = environ.get(XDG_CONFIG_HOME_ENV, "")
    if xdg:
        candidate = Path(xdg)
        if candidate.is_absolute():
            return candidate / "fitdocs" / "credentials"

    return home / ".config" / "fitdocs" / "credentials"


def check_outside_data_root(directory: Path, data_root: Path) -> None:
    """Refuse a credentials directory that is, or lies inside, ``data_root``.

    Both paths are resolved (symlinks followed, without requiring either to
    exist) before comparison, so a data root reached through a symlink or a
    relative argument is still caught (Req 4.2).
    """
    resolved_dir = directory.resolve()
    resolved_root = data_root.resolve()
    if resolved_dir.is_relative_to(resolved_root):
        raise CredentialsLocationError(
            f"credentials directory {resolved_dir} is the data root {resolved_root} "
            "or lies inside it; credentials may never be stored under the data root"
        )


def env_var_name(instance: str, field: str) -> str:
    """The environment-variable name that overrides ``field`` for ``instance``."""
    return f"{ENV_PREFIX}{instance.upper().replace('-', '_')}_{field.upper()}"


@dataclass(frozen=True)
class StoredCredentials:
    """What a credentials file holds for one connected instance (Req 4.6, 4.8)."""

    connector_id: str
    auth_style: AuthStyle
    values: Mapping[str, Secret]
    expires_at: datetime | None
    scopes: tuple[str, ...] | None


class CredentialStore:
    """Owner-only, atomic file storage for one resolved credentials directory."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    @property
    def directory(self) -> Path:
        return self._directory

    def path_for(self, instance: str) -> Path:
        """The file ``instance``'s credentials are (or would be) stored at."""
        return self._directory / f"{instance}.toml"

    def load(self, instance: str) -> StoredCredentials | None:
        """Read ``instance``'s credentials; ``None`` when absent (Req 4.4, 4.9)."""
        path = self.path_for(instance)
        try:
            file_stat = path.stat()
        except FileNotFoundError:
            return None

        mode = stat.S_IMODE(file_stat.st_mode)
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise CredentialStoreError(
                f"{path} is accessible by other users; run: chmod 600 {path}"
            )

        try:
            with path.open("rb") as handle:
                document = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise CredentialStoreError(f"{path} is not valid TOML: {exc}") from exc
        except OSError as exc:
            raise CredentialStoreError(f"{path} could not be read: {exc}") from exc

        return _credentials_from_document(path, document)

    def save(self, instance: str, credentials: StoredCredentials) -> Path:
        """Write ``instance``'s credentials, owner-only, atomically (Req 4.3).

        The directory is created mode ``0o700`` only when it does not
        already exist; an existing directory's mode is left exactly as it
        is (design.md's "create the credentials directory accessible only
        by the user" describes creation, not an on-every-save repair of a
        directory a user may have deliberately shared some other way).
        """
        path = self.path_for(instance)
        violation = _tz_violation(credentials.expires_at)
        if violation is not None:
            raise CredentialStoreError(f"{path}: {violation}")
        if not self._directory.exists():
            self._directory.mkdir(parents=True)
            os.chmod(self._directory, 0o700)
        document = _document_from_credentials(credentials)
        payload = tomli_w.dumps(document).encode("utf-8")
        write_atomic(path, payload, prefix=instance)
        return path


def _tz_violation(expires_at: datetime | None) -> str | None:
    """The one shape check shared by load and save for ``expires_at``.

    Mirrors ``connectors/ledger.py``'s ``watermark`` check: a naive
    (timezone-less) ``expires_at`` is refused wherever it is found, so a
    credentials file :meth:`CredentialStore.save` writes is always one
    :meth:`CredentialStore.load` would accept back.
    """
    if expires_at is not None and expires_at.tzinfo is None:
        return "'expires_at' must be timezone-aware"
    return None


def _credentials_from_document(
    path: Path, document: Mapping[str, object]
) -> StoredCredentials:
    try:
        version = document["credentials_version"]
        connector_id = document["connector"]
        auth_style_raw = document["auth_style"]
    except KeyError as exc:
        raise CredentialStoreError(f"{path} is missing {exc}") from exc

    if not isinstance(version, int) or isinstance(version, bool):
        raise CredentialStoreError(f"{path} has a malformed credentials_version")
    if version > CREDENTIALS_VERSION:
        raise CredentialStoreError(
            f"{path} records credentials_version {version}, newer than this "
            "version of fitdocs reads"
        )
    if version != CREDENTIALS_VERSION:
        raise CredentialStoreError(
            f"{path} records an unsupported credentials_version {version}"
        )

    if not isinstance(connector_id, str):
        raise CredentialStoreError(f"{path} has a malformed connector")

    if not isinstance(auth_style_raw, str):
        raise CredentialStoreError(f"{path} has a malformed auth_style")

    try:
        auth_style = AuthStyle(auth_style_raw)
    except ValueError as exc:
        raise CredentialStoreError(f"{path} has a malformed auth_style") from exc

    values_raw = document.get("values", {})
    if not isinstance(values_raw, Mapping):
        raise CredentialStoreError(f"{path} has a malformed [values] table")
    values: dict[str, Secret] = {}
    for key, value in values_raw.items():
        if not isinstance(value, str):
            raise CredentialStoreError(f"{path} has a malformed value for {key!r}")
        values[key] = Secret(value)

    scopes_raw = document.get("scopes")
    scopes: tuple[str, ...] | None
    if scopes_raw is None:
        scopes = None
    elif isinstance(scopes_raw, list) and all(
        isinstance(item, str) for item in scopes_raw
    ):
        scopes = tuple(scopes_raw)
    else:
        raise CredentialStoreError(f"{path} has a malformed scopes list")

    expires_at = document.get("expires_at")
    if expires_at is not None and not isinstance(expires_at, datetime):
        raise CredentialStoreError(f"{path} has a malformed expires_at")
    violation = _tz_violation(expires_at)
    if violation is not None:
        raise CredentialStoreError(f"{path}: {violation}")

    return StoredCredentials(
        connector_id=connector_id,
        auth_style=auth_style,
        values=values,
        expires_at=expires_at,
        scopes=scopes,
    )


def _document_from_credentials(credentials: StoredCredentials) -> dict[str, object]:
    document: dict[str, object] = {
        "credentials_version": CREDENTIALS_VERSION,
        "connector": credentials.connector_id,
        "auth_style": credentials.auth_style.value,
    }
    if credentials.scopes is not None:
        document["scopes"] = list(credentials.scopes)
    if credentials.expires_at is not None:
        document["expires_at"] = credentials.expires_at
    document["values"] = {
        key: value.reveal() for key, value in credentials.values.items()
    }
    return document


class ResolvedCredentials:
    """A :class:`~fitdocs.connectors.protocol.CredentialAccess` for one instance.

    Built only by :func:`resolve_credentials`. ``replace`` persists a new
    login-style token set through ``store`` before this object's own view
    of the values changes, so a caller that reads the values again
    immediately after ``replace`` returns sees what is now on disk (Req
    4.7).
    """

    def __init__(
        self,
        *,
        connector_id: str,
        auth_style: AuthStyle,
        values: Mapping[str, Secret],
        expires_at: datetime | None,
        scopes: tuple[str, ...] | None,
        store: CredentialStore | None,
        instance_name: str,
    ) -> None:
        self._connector_id = connector_id
        self._auth_style = auth_style
        self._values = dict(values)
        self._expires_at = expires_at
        self._scopes = scopes
        self._store = store
        self._instance_name = instance_name

    def value(self, field: str) -> Secret:
        try:
            return self._values[field]
        except KeyError as exc:
            raise NotConnectedError(
                f"{self._instance_name} has no value for {field!r}"
            ) from exc

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return self._scopes

    @property
    def expires_at(self) -> datetime | None:
        return self._expires_at

    def replace(self, tokens: TokenSet) -> None:
        if self._store is None:
            raise ConnectorError(
                f"{self._instance_name} has no credential store configured; "
                "cannot persist a new token set"
            )
        stored = StoredCredentials(
            connector_id=self._connector_id,
            auth_style=self._auth_style,
            values=tokens.values,
            expires_at=tokens.expires_at,
            scopes=tokens.scopes,
        )
        self._store.save(self._instance_name, stored)
        self._values = dict(tokens.values)
        self._expires_at = tokens.expires_at
        self._scopes = tokens.scopes


class _NoAuthCredentials:
    """The access for an :attr:`AuthStyle.NONE` connector: no values, ever."""

    def value(self, field: str) -> Secret:
        raise ConnectorError(
            f"this connector requires no authentication; there is no {field!r}"
        )

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        raise ConnectorError(
            "this connector requires no authentication; there is nothing to replace"
        )


def resolve_credentials(
    instance_name: str,
    connector: Connector,
    store: CredentialStore | None,
    environ: Mapping[str, str],
    redactor: Redactor,
) -> CredentialAccess:
    """Build the :class:`CredentialAccess` a session uses for ``instance_name``.

    ``NONE`` -> an access with no values at all. ``API_KEY`` -> per declared
    field, a non-empty environment variable wins over the stored value; a
    field with neither raises :class:`NotConnectedError` naming
    ``fitdocs connect <instance_name>`` and every missing variable.
    ``LOGIN`` -> stored values only, no environment override. Either style
    raises :class:`NotConnectedError` when the stored credentials were
    issued for a different connector (Req 4.9). Every value returned is
    registered with ``redactor`` (Req 10).
    """
    auth_style = connector.auth_style

    if auth_style is AuthStyle.NONE:
        return _NoAuthCredentials()

    if auth_style is AuthStyle.API_KEY:
        stored = store.load(instance_name) if store is not None else None
        if stored is not None and stored.connector_id != connector.connector_id:
            raise NotConnectedError(
                f"{instance_name} is connected for {stored.connector_id!r}, not "
                f"{connector.connector_id!r}; run: fitdocs connect {instance_name}"
            )

        values: dict[str, Secret] = {}
        missing_fields: list[str] = []
        missing_vars: list[str] = []
        for field in connector.credential_fields:
            var_name = env_var_name(instance_name, field.name)
            env_value = environ.get(var_name, "")
            if env_value:
                secret = Secret(env_value)
                values[field.name] = secret
            elif stored is not None and field.name in stored.values:
                values[field.name] = stored.values[field.name]
            else:
                missing_fields.append(field.name)
                missing_vars.append(var_name)

        if missing_fields:
            raise NotConnectedError(
                f"{instance_name} is not connected: run "
                f"`fitdocs connect {instance_name}` or set {', '.join(missing_vars)}"
            )

        for secret in values.values():
            redactor.add(secret)

        return ResolvedCredentials(
            connector_id=connector.connector_id,
            auth_style=auth_style,
            values=values,
            expires_at=stored.expires_at if stored is not None else None,
            scopes=stored.scopes if stored is not None else None,
            store=store,
            instance_name=instance_name,
        )

    if auth_style is AuthStyle.LOGIN:
        stored = store.load(instance_name) if store is not None else None
        if stored is None:
            raise NotConnectedError(
                f"{instance_name} is not connected: run "
                f"`fitdocs connect {instance_name}`"
            )
        if stored.connector_id != connector.connector_id:
            raise NotConnectedError(
                f"{instance_name} is connected for {stored.connector_id!r}, not "
                f"{connector.connector_id!r}; run: fitdocs connect {instance_name}"
            )

        for secret in stored.values.values():
            redactor.add(secret)

        return ResolvedCredentials(
            connector_id=connector.connector_id,
            auth_style=auth_style,
            values=stored.values,
            expires_at=stored.expires_at,
            scopes=stored.scopes,
            store=store,
            instance_name=instance_name,
        )

    raise NotConnectedError(
        f"{instance_name}'s connector uses an authentication style this version of "
        "fitdocs does not support"
    )
