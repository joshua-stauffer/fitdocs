"""Project the ``[connectors]`` table into validated instances (Req 3.1-3.8).

``<data-root>/fitdocs.toml`` is shared: :func:`fitdocs.settings.load_settings_document`
locates, reads, and parses it exactly once per invocation and raises the shared
:class:`~fitdocs.settings.SettingsError` for file-level problems (an unreadable
file, invalid TOML). This module receives only the mapping that reader already
produced and validates just the ``[connectors]`` table -- exactly as
:func:`fitdocs.plugins.load_plugin_settings` does for ``[plugins]``.

``[connectors]`` differs from every sibling table in shape: it holds one named
sub-table per configured instance rather than a fixed set of keys, so this
reader's job is to project each sub-table into a :class:`ConnectorInstance`
rather than to fill a single dataclass's fields (Req 3.1).

Order of checks, per instance, matching design.md's own order exactly (design.md
"State layer": "table shape; name pattern; connector ...; lookback_days ...;
any remaining key ...; connector.parse_settings(...)"):

1. the sub-table's shape (must be a TOML table);
2. the instance name against :data:`INSTANCE_NAME_PATTERN`;
3. the ``connector`` key -- a non-empty string resolved through
   :func:`fitdocs.connectors.registry.get`, or the instance's own name when
   the key is absent (Req 3.2);
4. ``lookback_days`` -- an ``int`` that is not a ``bool``, within
   ``0..MAX_LOOKBACK_DAYS``, defaulting to :data:`DEFAULT_LOOKBACK_DAYS`
   (Req 3.3);
5. every remaining key against the connector's declared credential field
   names -- a match is refused with the Req 3.5 message, before the
   connector ever sees the key;
6. the remaining table (``connector``/``lookback_days`` removed) handed to
   ``connector.parse_settings`` with the caller's :class:`~fitdocs.connectors.
   protocol.SettingsContext`; a :class:`~fitdocs.connectors.errors.
   ConnectorSettingsError` it raises is wrapped naming the key, any other
   exception is wrapped naming the connector (Req 3.4).

After every instance passes those six checks, one more pass runs across all of
them: two instances whose (instance, credential field) pairs resolve to the
same environment-variable name via :func:`fitdocs.connectors.credentials.
env_var_name` are refused together, naming both instances (Req 3.6) -- this
is a cross-instance rule and so cannot run per instance.

**Absent is not an error** (Req 3.7): no settings file, or a settings file
with no ``[connectors]`` table, projects to ``()`` -- no connectors -- not a
failure. **This reader never opens a file and never writes, creates, or
modifies one** (Req 3.8): it only reads the mapping it was given.

Every raised :class:`ConnectorsSettingsError` names the settings file, the
instance, and the key so a user can find and fix the exact line.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fitdocs.connectors import registry
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.errors import ConnectorSettingsError
from fitdocs.connectors.protocol import Connector, SettingsContext
from fitdocs.settings import SettingsError

CONNECTORS_TABLE: Final[str] = "connectors"
DEFAULT_LOOKBACK_DAYS: Final[int] = 30
MAX_LOOKBACK_DAYS: Final[int] = 3650
INSTANCE_NAME_PATTERN: Final[str] = r"^[a-z0-9][a-z0-9-]{0,63}$"

_NAME_RE = re.compile(INSTANCE_NAME_PATTERN)

_CONNECTOR_KEY: Final[str] = "connector"
_LOOKBACK_KEY: Final[str] = "lookback_days"
_RESERVED_KEYS: Final[frozenset[str]] = frozenset({_CONNECTOR_KEY, _LOOKBACK_KEY})


@dataclass(frozen=True)
class ConnectorInstance:
    """One validated ``[connectors.<name>]`` sub-table (Req 3.1-3.4)."""

    name: str
    connector: Connector
    lookback_days: int
    settings: object


class ConnectorsSettingsError(SettingsError):
    """The ``[connectors]`` table, or one of its sub-tables, is malformed.

    Every message names the settings file, the offending instance, and the
    offending key (Req 3.4, 3.5, 3.6) -- faults that belong to this table, not
    to the file as a whole (an unreadable file or invalid TOML raises the
    shared :class:`~fitdocs.settings.SettingsError` instead, before this
    module ever sees a mapping). This module never opens, creates, or writes
    the settings file (Req 3.8).
    """


def _fail(
    settings_file: Path, name: str, key: str, detail: str
) -> ConnectorsSettingsError:
    return ConnectorsSettingsError(
        f"{settings_file}: [connectors.{name}] {key}: {detail}"
    )


def _resolve_connector(
    table: Mapping[str, object], *, name: str, settings_file: Path
) -> Connector:
    if _CONNECTOR_KEY not in table:
        connector_id = name
    else:
        value = table[_CONNECTOR_KEY]
        if not isinstance(value, str) or not value:
            raise _fail(
                settings_file,
                name,
                _CONNECTOR_KEY,
                f"must be a non-empty string, got {value!r} ({type(value).__name__})",
            )
        connector_id = value

    try:
        return registry.get(connector_id)
    except registry.UnknownConnectorError as exc:
        raise _fail(settings_file, name, _CONNECTOR_KEY, str(exc)) from exc


def _resolve_lookback_days(
    table: Mapping[str, object], *, name: str, settings_file: Path
) -> int:
    if _LOOKBACK_KEY not in table:
        return DEFAULT_LOOKBACK_DAYS
    value = table[_LOOKBACK_KEY]
    # bool is an int subclass in Python; a TOML boolean must never pass as a
    # whole number of days.
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(
            settings_file,
            name,
            _LOOKBACK_KEY,
            f"must be a whole number of days, got {value!r} ({type(value).__name__})",
        )
    if not (0 <= value <= MAX_LOOKBACK_DAYS):
        raise _fail(
            settings_file,
            name,
            _LOOKBACK_KEY,
            f"must be between 0 and {MAX_LOOKBACK_DAYS}, got {value!r}",
        )
    return value


def _check_no_credential_keys(
    rest: Mapping[str, object],
    *,
    name: str,
    connector: Connector,
    settings_file: Path,
) -> None:
    field_names = {field.name for field in connector.credential_fields}
    for key in rest:
        if key in field_names:
            raise _fail(
                settings_file,
                name,
                key,
                "credentials belong in `fitdocs connect` or the environment, "
                "never in the settings file",
            )


def _parse_connector_settings(
    rest: Mapping[str, object],
    *,
    name: str,
    connector: Connector,
    context: SettingsContext,
    settings_file: Path,
) -> object:
    try:
        return connector.parse_settings(rest, context)
    except ConnectorSettingsError as exc:
        raise _fail(settings_file, name, exc.key, exc.message) from exc
    except Exception as exc:
        raise _fail(
            settings_file,
            name,
            _CONNECTOR_KEY,
            f"{connector.connector_id} settings error: {exc}",
        ) from exc


def _check_credential_collisions(
    instances: tuple[ConnectorInstance, ...], *, settings_file: Path
) -> None:
    seen: dict[str, str] = {}
    for instance in instances:
        for field in instance.connector.credential_fields:
            var_name = env_var_name(instance.name, field.name)
            earlier = seen.get(var_name)
            if earlier is not None:
                raise ConnectorsSettingsError(
                    f"{settings_file}: [connectors] instances {earlier!r} and "
                    f"{instance.name!r} would both read the environment "
                    f"variable {var_name}"
                )
            seen[var_name] = instance.name


def load_connectors_settings(
    document: Mapping[str, object],
    *,
    settings_file: Path,
    context: SettingsContext,
) -> tuple[ConnectorInstance, ...]:
    """Project the ``[connectors]`` table of an already-parsed settings document.

    Returns ``()`` when the file or its ``[connectors]`` table is absent
    (Req 3.7). Otherwise validates every named sub-table in the order
    documented on this module, then checks for a shared credential
    environment variable across every instance, and returns the result
    sorted by instance name. Reads no file and writes nothing (Req 3.8).
    """
    if CONNECTORS_TABLE not in document:
        return ()
    connectors_table = document[CONNECTORS_TABLE]
    if not isinstance(connectors_table, dict):
        raise ConnectorsSettingsError(
            f"{settings_file}: [connectors] must be a table, "
            f"got {connectors_table!r} ({type(connectors_table).__name__})"
        )

    instances: list[ConnectorInstance] = []
    for name, raw_table in connectors_table.items():
        if not isinstance(raw_table, dict):
            raise _fail(
                settings_file,
                name,
                "table",
                f"must be a table, got {raw_table!r} ({type(raw_table).__name__})",
            )
        if not _NAME_RE.fullmatch(name):
            raise _fail(
                settings_file,
                name,
                "name",
                f"must be a lowercase slug matching {INSTANCE_NAME_PATTERN!r}",
            )

        connector = _resolve_connector(
            raw_table, name=name, settings_file=settings_file
        )
        lookback_days = _resolve_lookback_days(
            raw_table, name=name, settings_file=settings_file
        )
        rest = {
            key: value for key, value in raw_table.items() if key not in _RESERVED_KEYS
        }
        _check_no_credential_keys(
            rest, name=name, connector=connector, settings_file=settings_file
        )
        settings = _parse_connector_settings(
            rest,
            name=name,
            connector=connector,
            context=context,
            settings_file=settings_file,
        )

        instances.append(
            ConnectorInstance(
                name=name,
                connector=connector,
                lookback_days=lookback_days,
                settings=settings,
            )
        )

    result = tuple(instances)
    _check_credential_collisions(result, settings_file=settings_file)
    return tuple(sorted(result, key=lambda instance: instance.name))
