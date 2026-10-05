"""Stable fingerprints shared by analytics-index producers and readers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from fitdocs import contract, docmerge, version
from fitdocs.index.producer import CorpusProducer, CorpusSnapshot
from fitdocs.index.schema import SCHEMA_VERSION
from fitdocs.metrics.types import AthleteInputs, ZoneSpec


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return _digest(encoded)


def document_fingerprint(path: str, data: bytes) -> str:
    return _digest(path.encode("utf-8") + b"\0" + data)


def _body_after_frontmatter(text: str) -> str:
    close = contract.frontmatter_close_index(text.split("\n"))
    if close is None:
        return text
    return "\n".join(text.split("\n")[close + 1 :])


def _blank_preserved_regions(body: str) -> str:
    regions = docmerge.extract_regions(body)
    blanked = "".join(
        docmerge.region_block(
            region_id,
            "" if region_id in contract.PRESERVED_REGIONS else content,
        )
        for region_id, content in regions.items()
    )
    return docmerge.merge_regions(body, blanked)


def render_fingerprint(text: str, frontmatter: Mapping[str, object]) -> str:
    managed = {
        key: frontmatter[key]
        for key in sorted(frontmatter)
        if key in contract.MANAGED_KEYS and key not in contract.LOAD_KEYS
    }
    body = _blank_preserved_regions(_body_after_frontmatter(text))
    return _canonical_digest({"managed": managed, "body": body})


def _float_text(value: float | None) -> str | None:
    return None if value is None else repr(value)


def _zone_text(zone: ZoneSpec | None) -> list[str] | None:
    if zone is None:
        return None
    return [repr(divider) for divider in zone.dividers]


def athlete_fingerprint(inputs: AthleteInputs | None) -> str:
    if inputs is None:
        return _digest(b"absent")
    values: list[object] = [
        _float_text(inputs.ftp_watts),
        inputs.resting_hr_bpm,
        inputs.max_hr_bpm,
        _zone_text(inputs.hr_zones),
        _zone_text(inputs.power_zones),
        _zone_text(inputs.pace_zones),
        None if inputs.trimp_weighting is None else inputs.trimp_weighting.value,
    ]
    return _canonical_digest(values)


def corpus_fingerprint(
    producer_fingerprint: str,
    *,
    fitdocs_version: str | None,
    schema_version: int,
) -> str:
    return _canonical_digest(
        {
            "producer_fingerprint": producer_fingerprint,
            "fitdocs_version": fitdocs_version,
            "schema_version": schema_version,
        }
    )


def combined_corpus_fingerprint(
    producer: CorpusProducer, snapshot: CorpusSnapshot
) -> str:
    return corpus_fingerprint(
        producer.fingerprint(snapshot),
        fitdocs_version=version.tool_version(),
        schema_version=SCHEMA_VERSION,
    )
