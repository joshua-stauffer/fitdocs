"""Extract the file's own identity and count its undocumented messages (Req 1.1-1.6).

Two pure functions over the decoded message dict, kept out of
:mod:`fitdocs.ingest.decode` (the only module that touches the SDK):

* :func:`extract_file_identity` reads the FIRST ``file_id`` message into a
  :class:`~fitdocs.model.FileIdentity`; a value the message omits, or records as
  the wrong type, is ``None``. The SDK's ``garmin_product`` sub-field (a product
  *name* it adds beside ``product``) is never read;
* :func:`count_undocumented_messages` counts the messages the decoder filed under
  a key made only of digits -- the SDK's naming for a global message number its
  profile does not define.

Imports only :mod:`fitdocs.model` and :mod:`fitdocs.ingest._fields`.
"""

from __future__ import annotations

from collections.abc import Mapping

from fitdocs.ingest._fields import str_or_none
from fitdocs.model import FileIdentity, fit_datetime


def _genuine_int(value: object) -> int | None:
    """``value`` when it is an ``int`` that is not a ``bool``, else ``None``."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def extract_file_identity(file_id_mesgs: list[dict[str, object]]) -> FileIdentity:
    """The first ``file_id`` message's identity; all ``None`` when there is none."""
    if not file_id_mesgs:
        return FileIdentity(
            manufacturer=None, product=None, serial_number=None, time_created=None
        )
    first = file_id_mesgs[0]
    raw_created = _genuine_int(first.get("time_created"))
    return FileIdentity(
        manufacturer=str_or_none(first.get("manufacturer")),
        product=_genuine_int(first.get("product")),
        serial_number=_genuine_int(first.get("serial_number")),
        time_created=None if raw_created is None else fit_datetime(raw_created),
    )


def count_undocumented_messages(
    messages: Mapping[str, list[dict[str, object]]],
) -> int:
    """The number of messages under decoded keys that consist only of digits."""
    return sum(len(mesgs) for key, mesgs in messages.items() if key.isdigit())
