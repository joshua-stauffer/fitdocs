"""Pluggable remote data sources for fitdocs (design: connectors spec).

This package is the boundary between fitdocs and any remote service that
supplies ``.fit`` files: authentication, listing, fetching, and delivery into
the inbox. It owns the one place in ``src/`` (besides :mod:`fitdocs.tiles`)
allowed to open a network connection. It defines
:class:`fitdocs.connectors.secrets.Secret`, which carries credentials and
tokens and shows only a redaction marker in every text form, and
:class:`fitdocs.connectors.secrets.Redactor`, which scrubs every registered
secret value (signed download locations included) from any text before it
is reported.

A module inside this package may import only the standard library,
``fitdocs.layout``, ``fitdocs.settings``, ``fitdocs.inbox``,
``fitdocs.version``, and -- in ``connectors/ledger.py`` and
``connectors/credentials.py`` only -- ``tomli_w``. Only
``connectors/http.py`` may import ``urllib.request``/``urllib.error``. No
module here reads the system clock directly; ``now`` and ``sleep`` are always
passed in by the caller.

The published surface (``__all__``) is filled in by a later task as the
package's components land; today it is intentionally empty.
"""

from __future__ import annotations

__all__: list[str] = []
