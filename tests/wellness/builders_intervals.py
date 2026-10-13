"""Synthetic intervals.icu payloads for downstream integration tests."""

import json
from collections.abc import Mapping, Sequence
from datetime import date


def intervals_record(
    day: str | date, *, updated: object = None, **fields: object
) -> dict[str, object]:
    return {"id": str(day), "updated": updated, **fields}


def intervals_list_bytes(records: Sequence[Mapping[str, object]]) -> bytes:
    return json.dumps(list(records)).encode("utf-8")


def intervals_delivery_bytes(
    records: Sequence[Mapping[str, object]], *, origins: Mapping[str, str] | None = None
) -> bytes:
    envelope: dict[str, object] = {
        "format": "fitdocs.intervals-icu-wellness",
        "version": 1,
        "records": sorted(records, key=lambda record: str(record["id"])),
    }
    if origins is not None:
        envelope["origins"] = dict(origins)
    return (
        json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
