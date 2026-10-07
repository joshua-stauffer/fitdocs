"""Version 2 pins the canonical table/column/type/order digest.

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
    2: "ebe1601c10d1c48150fe9266d11e907712882cc95b5a483e4e66bde9500fd0d4",
}


def test_schema_version_is_known_and_matches_registered_schema_digest() -> None:
    assert SCHEMA_VERSION == 2
    assert max(_DIGESTS_BY_VERSION) == SCHEMA_VERSION
    assert schema_digest(registered_tables()) == _DIGESTS_BY_VERSION[SCHEMA_VERSION]
