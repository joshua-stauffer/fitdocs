"""The per-target publish ledger (publish-core Req 10.3, 11.1-11.6, 11.8).

One TOML file per target at ``<data root>/.fitdocs/publish/<target>.toml``
records, page by page, the publication id, the digest of the last landed
post, the last outcome code and when it was received, and the last permitted
link with its label. Nothing else is ever written (Req 11.8): the record has
no field a target's answer could fill except the link, and a file carrying
any other key is refused.

A publication id shared between two targets' ledgers is refused on load,
naming the second file, so a ledger copied to rename a target is refused.

Reading creates nothing and a refused file is never rewritten. Every time
value is supplied by the caller; this module reads no clock.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import tomli_w

from fitdocs.docio import write_bytes_if_changed
from fitdocs.layout import PUBLISH_STATE_DIR, publish_ledger_path
from fitdocs.publish.request import valid_label, valid_link

PUBLISH_LEDGER_VERSION: Final[int] = 1
WORKOUT_PAGE_KIND: Final[str] = "workout"

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_PAGE_RE = re.compile(rf"{WORKOUT_PAGE_KIND}:([0-9a-f]{{64}})")
_ID_RE = re.compile(r"[0-9a-f]{32}")
_CODE_RE = re.compile(r"[a-z][a-z0-9_]*")
#: A target name is a connector instance name: a lowercase slug.
_TARGET_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")

_TOP_KEYS: Final[frozenset[str]] = frozenset(
    {"ledger_version", "connector", "publication"}
)
_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {"page", "id", "digest", "code", "at", "link", "label"}
)


def workout_page_key(sha256: str) -> str:
    """The ledger key of a workout page: ``workout:`` and its file digest."""
    if not _SHA256_RE.fullmatch(sha256):
        raise ValueError("a workout page key needs a lowercase 64-hex sha256")
    return f"{WORKOUT_PAGE_KIND}:{sha256}"


@dataclass(frozen=True)
class PublicationRecord:
    """What is known about one page's publications to one target."""

    page: str
    publication_id: str
    digest: str | None = None
    code: str | None = None
    at: datetime | None = None
    link: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class PublishLedger:
    """One target's ledger: its identity and its records."""

    target: str
    connector: str
    records: tuple[PublicationRecord, ...]

    def matching(self, shas: Collection[str]) -> tuple[PublicationRecord, ...]:
        """The records whose page key digest is one of ``shas``."""
        wanted = frozenset(shas)
        matched = []
        for record in self.records:
            found = _PAGE_RE.fullmatch(record.page)
            if found is not None and found.group(1) in wanted:
                matched.append(record)
        return tuple(matched)

    def with_record(self, record: PublicationRecord) -> PublishLedger:
        """A ledger with ``record`` replacing the one for its page, or added."""
        kept = tuple(r for r in self.records if r.page != record.page)
        return replace(self, records=(*kept, record))


class PublishLedgerError(Exception):
    """A ledger that cannot be used; the message names the file."""


def _fail(path: Path, reason: str) -> PublishLedgerError:
    return PublishLedgerError(f"publish ledger {path}: {reason}")


def _check_record(path: Path, record: PublicationRecord) -> None:
    """Raise unless one record satisfies every field invariant."""
    page = record.page
    if not isinstance(page, str) or not _PAGE_RE.fullmatch(page):
        raise _fail(path, "a record has no valid page key")
    if not isinstance(record.publication_id, str) or not _ID_RE.fullmatch(
        record.publication_id
    ):
        raise _fail(path, f"the record for {page} has no valid id")
    if record.digest is not None and (
        not isinstance(record.digest, str) or not _SHA256_RE.fullmatch(record.digest)
    ):
        raise _fail(path, f"the record for {page} has an invalid digest")
    if (record.code is None) != (record.at is None):
        raise _fail(path, f"the record for {page} must have code and at together")
    if record.code is not None and (
        not isinstance(record.code, str) or not _CODE_RE.fullmatch(record.code)
    ):
        raise _fail(path, f"the record for {page} has an invalid code")
    if record.at is not None and (
        not isinstance(record.at, datetime) or record.at.utcoffset() is None
    ):
        raise _fail(path, f"the record for {page} has a time without a timezone")
    if (record.link is None) != (record.label is None):
        raise _fail(path, f"the record for {page} must have link and label together")
    if record.link is not None and not valid_link(record.link):
        raise _fail(path, f"the record for {page} has an invalid link")
    if record.label is not None and not valid_label(record.label):
        raise _fail(path, f"the record for {page} has an invalid label")


def _check_ledger(path: Path, ledger: PublishLedger) -> None:
    """Raise unless the ledger satisfies every invariant of the design."""
    if not isinstance(ledger.target, str) or not _TARGET_RE.fullmatch(ledger.target):
        raise _fail(path, "the target name is not valid")
    if not isinstance(ledger.connector, str) or not ledger.connector:
        raise _fail(path, "the connector identity is empty")
    pages: set[str] = set()
    ids: set[str] = set()
    for record in ledger.records:
        _check_record(path, record)
        if record.page in pages:
            raise _fail(path, f"more than one record for {record.page}")
        if record.publication_id in ids:
            raise _fail(path, "a publication id is used by more than one record")
        pages.add(record.page)
        ids.add(record.publication_id)


def _record_from_table(path: Path, table: object) -> PublicationRecord:
    if not isinstance(table, dict):
        raise _fail(path, "a publication entry is not a table")
    unknown = set(table) - _RECORD_KEYS
    if unknown:
        raise _fail(path, f"a publication entry has an unknown key {sorted(unknown)}")
    for required in ("page", "id"):
        if required not in table:
            raise _fail(path, f"a publication entry has no {required!r}")
    for key in ("page", "id", "digest", "code", "link", "label"):
        if key in table and not isinstance(table[key], str):
            raise _fail(path, f"{key!r} in a publication entry is not text")
    at = table.get("at")
    if at is not None and not isinstance(at, datetime):
        raise _fail(path, "'at' in a publication entry is not a date-time")
    return PublicationRecord(
        page=table["page"],
        publication_id=table["id"],
        digest=table.get("digest"),
        code=table.get("code"),
        at=at,
        link=table.get("link"),
        label=table.get("label"),
    )


def _read_ledger(path: Path, target: str) -> PublishLedger:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _fail(path, f"cannot be read ({type(exc).__name__})") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise _fail(path, "is not valid TOML") from exc
    version = data.get("ledger_version")
    if type(version) is int and version > PUBLISH_LEDGER_VERSION:
        raise _fail(path, f"is version {version}, newer than this fitdocs reads")
    if type(version) is not int or version != PUBLISH_LEDGER_VERSION:
        raise _fail(path, "has no ledger_version of 1")
    unknown = set(data) - _TOP_KEYS
    if unknown:
        raise _fail(path, f"has an unknown key {sorted(unknown)}")
    connector = data.get("connector")
    if not isinstance(connector, str):
        raise _fail(path, "has no connector identity")
    entries = data.get("publication", [])
    if not isinstance(entries, list):
        raise _fail(path, "'publication' is not an array of tables")
    ledger = PublishLedger(
        target=target,
        connector=connector,
        records=tuple(_record_from_table(path, entry) for entry in entries),
    )
    _check_ledger(path, ledger)
    return ledger


def load_ledgers(
    data_root: Path, configured: Mapping[str, str]
) -> dict[str, PublishLedger]:
    """Every ledger on disk plus an empty one per configured target without one.

    ``configured`` maps each configured target to its ledger identity (its
    connector id). Reads create nothing. Raises :class:`PublishLedgerError`,
    naming the file, for anything unusable; nothing is rewritten.
    """
    ledgers: dict[str, PublishLedger] = {}
    directory = data_root / PUBLISH_STATE_DIR
    names: list[str] = []
    try:
        if directory.is_dir():
            names = sorted(
                entry.name
                for entry in directory.iterdir()
                if entry.name.endswith(".toml")
            )
    except OSError as exc:
        raise _fail(directory, f"cannot be listed ({type(exc).__name__})") from exc
    for name in names:
        target = name.removesuffix(".toml")
        path = publish_ledger_path(data_root, target)
        if path.is_symlink() or not path.is_file():
            raise _fail(path, "is not a regular file")
        ledger = _read_ledger(path, target)
        if target in configured and ledger.connector != configured[target]:
            raise _fail(path, "was written for a different connector")
        ledgers[target] = ledger
    seen_ids: dict[str, str] = {}
    for target, ledger in ledgers.items():
        for record in ledger.records:
            other = seen_ids.setdefault(record.publication_id, target)
            if other != target:
                raise _fail(
                    publish_ledger_path(data_root, target),
                    f"shares a publication id with the ledger of {other}",
                )
    for target, identity in configured.items():
        if target not in ledgers:
            ledgers[target] = PublishLedger(target, identity, ())
    return ledgers


def save_ledger(data_root: Path, ledger: PublishLedger) -> bool:
    """Write the ledger sorted by page; return whether the file changed."""
    path = publish_ledger_path(data_root, ledger.target)
    _check_ledger(path, ledger)
    publications: list[dict[str, object]] = []
    for record in sorted(ledger.records, key=lambda r: r.page):
        entry: dict[str, object] = {
            "page": record.page,
            "id": record.publication_id,
            "digest": record.digest,
            "code": record.code,
            "at": None if record.at is None else record.at.astimezone(UTC),
            "link": record.link,
            "label": record.label,
        }
        publications.append({k: v for k, v in entry.items() if v is not None})
    document: dict[str, object] = {
        "ledger_version": PUBLISH_LEDGER_VERSION,
        "connector": ledger.connector,
    }
    if publications:
        document["publication"] = publications
    data = tomli_w.dumps(document).encode("utf-8")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return write_bytes_if_changed(path, data)
    except OSError as exc:
        raise _fail(path, f"cannot be written ({type(exc).__name__})") from exc
