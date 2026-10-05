"""Version 1 pins the canonical table/column/type/order digest.

SCHEMA_VERSION advances by exactly one from main's value at landing for every
schema change and every change to how any producer derives rows from unchanged
inputs, because the per-page tiers do not recompute on an upgrade. A new
version's digest may equal the previous one when row derivation changes without
a schema-manifest change.
"""

from __future__ import annotations

from fitdocs.index.registry import registered_tables
from fitdocs.index.schema import SCHEMA_VERSION, schema_digest

_DIGESTS_BY_VERSION = {
    1: "7573846fdac5174d36fb0617b922404a3352362a3be7bc8e44bad0d2a5483a26",
}


def test_schema_version_is_known_and_matches_registered_schema_digest() -> None:
    assert max(_DIGESTS_BY_VERSION) == SCHEMA_VERSION
    assert schema_digest(registered_tables()) == _DIGESTS_BY_VERSION[SCHEMA_VERSION]
