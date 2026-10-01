"""Pins for the pull engine (design.md "PullEngine", Req 1.9, 4.7, 6.4-6.13,
7.2, 7.4, 7.7, 8.5, 10.1, 10.2, 10.5, 11.5, 13.4).

Most connectors used here need no credentials (``AuthStyle.NONE``). Task
4.4's own pins, at the bottom of this module, use
``ScriptedPersonalKeyConnector``/``ScriptedLoginConnector`` (``conftest.py``)
with ``capabilities`` overridden to add ``Capability.PULL_ACTIVITIES`` --
credential resolution's failure handling, a login-style token's renewal, and
per-item/per-instance failure isolation and redaction.

Fixtures deliberately defeat the specific wrong implementations the task
text calls out: the "second pull" pin counts the connector's fetches on the
second pull and requires none, so an engine that decides "new" from the
listing rather than the ledger is caught even though the R2 same-bytes rule
would leave its report and ledger looking unchanged. The
"identical bytes" pin uses two distinct remote ids so a hash-based
duplicate-suppression check is the only thing that can prevent a second
delivery; the watermark pins pair a positive control (all final -> watermark
advances) against the blocking case (one deferred -> watermark stays
``None``) so a naive "max of all dated entries" implementation is caught;
the channel-sort pin gives ``delivered`` entries a ``suggested_name`` whose
alphabetical order is the *reverse* of their ``remote_id`` order, so sorting
by path and sorting by remote id are distinguishable.
"""

from __future__ import annotations

import hashlib
import stat
import tomllib
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from fitdocs import layout
from fitdocs.connectors import delivery as delivery_mod
from fitdocs.connectors.credentials import (
    CredentialStore,
    CredentialStoreError,
    StoredCredentials,
    env_var_name,
)
from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    next_step,
)
from fitdocs.connectors.folder import FolderConnector, FolderSettings
from fitdocs.connectors.http import HttpRequest, HttpResponse, Transport, TransportError
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    Connector,
    ConnectorSession,
    Declined,
    Deferred,
    Fetched,
    Listing,
    ListingDeferral,
    RemoteActivity,
    TokenSet,
)
from fitdocs.connectors.pull import (
    Delivered,
    PullNote,
    PullOptions,
    PullReport,
    run_pull,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.settings import ConnectorInstance
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedLoginConnector,
    ScriptedPersonalKeyConnector,
    ScriptedPuller,
)

_NOW = datetime(2026, 6, 1, tzinfo=UTC)


def _fit_bytes(tag: bytes = b"") -> bytes:
    """Minimal, valid FIT header bytes; ``tag`` makes the content -- and so
    its hash -- distinct between calls."""
    return bytes([12, 0x10, 0, 0, 0, 0, 0, 0]) + b".FIT" + tag


def _instance(
    connector: Connector, *, name: str = "src", lookback_days: int = 30
) -> ConnectorInstance:
    return ConnectorInstance(
        name=name, connector=connector, lookback_days=lookback_days, settings=None
    )


def _folder_instance(
    source: Path,
    *,
    name: str = "folder",
    lookback_days: int = 30,
    settle_seconds: float = 0.0,
) -> ConnectorInstance:
    return ConnectorInstance(
        name=name,
        connector=FolderConnector(),
        lookback_days=lookback_days,
        settings=FolderSettings(source=source, settle_seconds=settle_seconds),
    )


def _run(
    data_root: Path,
    inbox: Path,
    instances: list[ConnectorInstance],
    *,
    dry_run: bool = False,
    since: datetime | None = None,
    redactor: Redactor | None = None,
    now: Callable[[], datetime] | None = None,
    store: CredentialStore | None = None,
    environ: Mapping[str, str] | None = None,
    transport: Transport | None = None,
) -> PullReport:
    return run_pull(
        data_root,
        instances,
        inbox=inbox,
        store=store,
        transport=transport if transport is not None else FakeTransport([]),
        options=PullOptions(since=since, dry_run=dry_run),
        environ=environ if environ is not None else {},
        now=now or (lambda: _NOW),
        sleep=lambda seconds: None,
        redactor=redactor or Redactor(),
    )


def _ledger_document(data_root: Path, instance: str) -> dict[str, Any]:
    path = layout.connector_ledger_path(data_root, instance)
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _snapshot(root: Path) -> dict[str, tuple[str, int, bytes | None]]:
    """Kind, permission bits, and (for files) content for every entry under
    ``root`` -- catches a stray write, permission change, or file creation
    that a byte-only comparison would miss."""
    result: dict[str, tuple[str, int, bytes | None]] = {}
    if not root.exists():
        return result
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        kind = "dir" if path.is_dir() else "file"
        content = path.read_bytes() if path.is_file() else None
        result[str(path.relative_to(root))] = (
            kind,
            stat.S_IMODE(info.st_mode),
            content,
        )
    return result


# ---------------------------------------------------------------------------
# The folder connector: second pull, unreadable-then-readable, changed file.
# ---------------------------------------------------------------------------


def test_second_pull_over_unchanged_folder_fetches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.fit").write_bytes(_fit_bytes(b"one"))

    instance = _folder_instance(source)
    first = _run(data_root, inbox, [instance])
    assert first.instances[0].delivered
    first_bytes = layout.connector_ledger_path(data_root, "folder").read_bytes()

    fetches: list[str] = []
    real_fetch = FolderConnector.fetch_activity

    def _counting_fetch(self: FolderConnector, *args: Any, **kwargs: Any) -> Any:
        fetches.append("fetch")
        return real_fetch(self, *args, **kwargs)

    monkeypatch.setattr(FolderConnector, "fetch_activity", _counting_fetch)
    second = _run(data_root, inbox, [_folder_instance(source)])
    second_bytes = layout.connector_ledger_path(data_root, "folder").read_bytes()

    assert fetches == []  # Req 6.5: a final id is never fetched again

    assert second.instances[0].delivered == ()
    assert second.instances[0].held == ("a.fit",)
    assert second.instances[0].listed == 1
    assert second_bytes == first_bytes


def test_file_unreadable_on_first_pull_is_delivered_by_the_second(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    source = tmp_path / "source"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(_fit_bytes(b"one"))
    target.chmod(0)
    try:
        first = _run(data_root, inbox, [_folder_instance(source)])
    finally:
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert first.instances[0].delivered == ()
    assert len(first.instances[0].deferred) == 1
    assert "could not be read" in first.instances[0].deferred[0].detail
    # Falsity in the starting state: nothing recorded yet.
    assert not layout.connector_ledger_path(data_root, "folder").exists()

    second = _run(data_root, inbox, [_folder_instance(source)])
    assert [d.remote_id for d in second.instances[0].delivered] == ["a.fit"]


def test_changed_file_is_fetched_again(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    source = tmp_path / "source"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(_fit_bytes(b"one"))

    first = _run(data_root, inbox, [_folder_instance(source)])
    assert [d.remote_id for d in first.instances[0].delivered] == ["a.fit"]
    first_doc = _ledger_document(data_root, "folder")
    first_revision = first_doc["entries"][0]["revision"]

    target.write_bytes(_fit_bytes(b"one-but-longer-now"))

    second = _run(data_root, inbox, [_folder_instance(source)])
    assert [d.remote_id for d in second.instances[0].delivered] == ["a.fit"]
    second_doc = _ledger_document(data_root, "folder")
    assert second_doc["entries"][0]["revision"] != first_revision
    assert second_doc["entries"][0]["sha256"] != first_doc["entries"][0]["sha256"]


# ---------------------------------------------------------------------------
# The scripted puller: archived/held, duplicate bytes, non-FIT, unavailable.
# ---------------------------------------------------------------------------


def test_archived_bytes_are_held_and_not_delivered(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    data = _fit_bytes(b"archived")
    sha = hashlib.sha256(data).hexdigest()
    archive_path = layout.archive_path(data_root, sha)
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(data)

    connector = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="remote-1", original_available=True, start=_NOW, revision="r1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=data))

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]
    assert inst.delivered == ()
    assert inst.held == ("remote-1",)
    assert not (inbox / "src").exists()

    doc = _ledger_document(data_root, "src")
    entry = doc["entries"][0]
    assert entry["outcome"] == "already-held"
    assert entry["sha256"] == sha
    assert entry["revision"] == "r1"


def test_two_remote_ids_with_identical_bytes_deliver_once(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    data = _fit_bytes(b"shared")
    connector = ScriptedPuller()
    first_activity = RemoteActivity(
        remote_id="remote-a",
        original_available=True,
        start=_NOW,
        revision="ra",
    )
    second_activity = RemoteActivity(
        remote_id="remote-b",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="rb",
    )
    connector.listing_script.append(
        Listing(activities=(second_activity, first_activity))
    )
    connector.fetch_script.extend([Fetched(data=data), Fetched(data=data)])

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]
    assert [d.remote_id for d in inst.delivered] == ["remote-a"]
    assert inst.held == ("remote-b",)


def test_tied_start_entries_process_in_ascending_remote_id_order(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    # Same instant as `t`, spelled with a different UTC offset -- a sort
    # keyed on the rendered text (e.g. isoformat()) rather than the instant
    # itself would place this entry differently than one keyed on the
    # instant, so this also catches a spelling-based sort.
    t_other_offset = t.astimezone(timezone(timedelta(hours=2)))

    activity_z = RemoteActivity(
        remote_id="z", original_available=True, start=t, revision="1"
    )
    activity_a = RemoteActivity(
        remote_id="a", original_available=True, start=t, revision="1"
    )
    activity_m = RemoteActivity(
        remote_id="m", original_available=True, start=t_other_offset, revision="1"
    )

    shared = _fit_bytes(b"shared-a-and-m")
    unique_z = _fit_bytes(b"unique-z")

    connector = ScriptedPuller()
    # Listing order (z, a, m) differs from both ascending remote-id order
    # (a, m, z) and descending/reverse remote-id order (z, m, a), so any of
    # the three can be distinguished from the correct one.
    connector.listing_script.append(
        Listing(activities=(activity_z, activity_a, activity_m))
    )
    # "a" is processed first and delivered; "m" (processed second) fetches
    # identical bytes, so it is caught by the held-hash dedup and reported
    # `held`, not delivered -- a tied-start consequence pin on top of the
    # order pin below.
    connector.fetch_script.extend(
        [Fetched(data=shared), Fetched(data=shared), Fetched(data=unique_z)]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert [activity.remote_id for activity in connector.fetch_calls] == [
        "a",
        "m",
        "z",
    ]
    assert {d.remote_id for d in inst.delivered} == {"a", "z"}
    assert inst.held == ("m",)


def test_non_fit_bytes_are_skipped_and_not_delivered(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="remote-1", original_available=True, start=_NOW, revision="r1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    non_fit_data = b"not a fit file, just text"
    connector.fetch_script.append(Fetched(data=non_fit_data))

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]
    assert inst.delivered == ()
    assert len(inst.skipped) == 1
    assert inst.skipped[0].detail == "not a FIT file"
    assert not (inbox / "src").exists()

    doc = _ledger_document(data_root, "src")
    entry = doc["entries"][0]
    assert entry["outcome"] == "skipped"
    assert entry["detail"] == "not a FIT file"
    assert entry["sha256"] == hashlib.sha256(non_fit_data).hexdigest()
    assert entry["revision"] == "r1"


def test_unavailable_entry_is_recorded_skipped(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="remote-1",
        original_available=False,
        unavailable_reason="quota exceeded",
        start=_NOW,
        revision="r1",
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    # fetch_script left empty: if the engine wrongly fetches an unavailable
    # entry, ScriptedPuller raises UnscriptedCall and this test fails loudly.

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]
    assert inst.delivered == ()
    assert [(n.subject, n.detail) for n in inst.skipped] == [
        ("remote-1", "quota exceeded")
    ]
    assert connector.fetch_calls == []
    assert inst.listed == 1

    doc = _ledger_document(data_root, "src")
    entry = doc["entries"][0]
    assert entry["outcome"] == "skipped"
    assert entry["detail"] == "quota exceeded"
    assert entry["revision"] == "r1"


def test_repeated_unavailable_listing_at_the_same_revision_is_held_not_reskipped(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    first_connector = ScriptedPuller()
    first_activity = RemoteActivity(
        remote_id="u1",
        original_available=False,
        unavailable_reason="r-one",
        start=_NOW,
        revision="rev1",
    )
    first_connector.listing_script.append(Listing(activities=(first_activity,)))
    # fetch_script left empty: unavailable entries are never fetched.

    first = _run(data_root, inbox, [_instance(first_connector)])
    assert [(n.subject, n.detail) for n in first.instances[0].skipped] == [
        ("u1", "r-one")
    ]
    first_bytes = layout.connector_ledger_path(data_root, "src").read_bytes()

    # Second pull: same remote id, same revision, still unavailable -- but
    # with a *different* reason, and nothing scripted to fetch. The already
    # final (skipped) entry must be reported `held`, not re-recorded.
    second_connector = ScriptedPuller()
    second_activity = RemoteActivity(
        remote_id="u1",
        original_available=False,
        unavailable_reason="r-two",
        start=_NOW,
        revision="rev1",
    )
    second_connector.listing_script.append(Listing(activities=(second_activity,)))

    second = _run(data_root, inbox, [_instance(second_connector)])
    inst = second.instances[0]
    second_bytes = layout.connector_ledger_path(data_root, "src").read_bytes()

    assert inst.held == ("u1",)
    assert inst.skipped == ()

    doc = _ledger_document(data_root, "src")
    entry = doc["entries"][0]
    assert entry["detail"] == "r-one"
    assert second_bytes == first_bytes
    assert "sha256" not in entry


# ---------------------------------------------------------------------------
# The window start.
# ---------------------------------------------------------------------------


def test_window_start_with_no_watermark_lists_from_the_beginning(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    connector = ScriptedPuller()

    connector.listing_script.append(Listing(activities=()))
    _run(data_root, inbox, [_instance(connector)])

    assert connector.list_calls == [None]


def test_window_start_with_a_watermark_subtracts_the_lookback(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    watermark_activity = RemoteActivity(
        remote_id="remote-1",
        original_available=True,
        start=datetime(2026, 5, 1, tzinfo=UTC),
        revision="r1",
    )
    first_connector = ScriptedPuller()
    first_connector.listing_script.append(Listing(activities=(watermark_activity,)))
    first_connector.fetch_script.append(Fetched(data=_fit_bytes(b"first")))
    _run(data_root, inbox, [_instance(first_connector, lookback_days=7)])

    doc = _ledger_document(data_root, "src")
    assert doc["watermark"] == datetime(2026, 5, 1, tzinfo=UTC)

    second_connector = ScriptedPuller()
    second_connector.listing_script.append(Listing(activities=()))
    _run(data_root, inbox, [_instance(second_connector, lookback_days=7)])

    assert second_connector.list_calls == [
        datetime(2026, 5, 1, tzinfo=UTC) - timedelta(days=7)
    ]


def test_window_start_override_wins_over_the_watermark(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    watermark_activity = RemoteActivity(
        remote_id="remote-1",
        original_available=True,
        start=datetime(2026, 5, 1, tzinfo=UTC),
        revision="r1",
    )
    first_connector = ScriptedPuller()
    first_connector.listing_script.append(Listing(activities=(watermark_activity,)))
    first_connector.fetch_script.append(Fetched(data=_fit_bytes(b"first")))
    _run(data_root, inbox, [_instance(first_connector, lookback_days=7)])

    override = datetime(2026, 5, 20, tzinfo=UTC)
    second_connector = ScriptedPuller()
    second_connector.listing_script.append(Listing(activities=()))
    _run(
        data_root,
        inbox,
        [_instance(second_connector, lookback_days=7)],
        since=override,
    )

    assert second_connector.list_calls == [override]


# ---------------------------------------------------------------------------
# The watermark: advances over a contiguous final prefix, blocked by a
# deferred entry at its own start.
# ---------------------------------------------------------------------------


def test_watermark_advances_over_the_contiguous_final_prefix(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t1 = datetime(2026, 5, 1, tzinfo=UTC)
    t2 = datetime(2026, 5, 2, tzinfo=UTC)
    t3 = datetime(2026, 5, 3, tzinfo=UTC)
    a1 = RemoteActivity(remote_id="r1", original_available=True, start=t1, revision="1")
    a2 = RemoteActivity(remote_id="r2", original_available=True, start=t2, revision="1")
    a3 = RemoteActivity(remote_id="r3", original_available=True, start=t3, revision="1")

    connector = ScriptedPuller()
    # Scrambled listing order: proves the engine orders by start, not by
    # listing order, before deciding the watermark.
    connector.listing_script.append(Listing(activities=(a3, a1, a2)))
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"one")),
            Fetched(data=_fit_bytes(b"two")),
            Fetched(data=_fit_bytes(b"three")),
        ]
    )

    _run(data_root, inbox, [_instance(connector)])
    doc = _ledger_document(data_root, "src")
    assert doc["watermark"] == t3


def test_deferred_entry_blocks_the_watermark_at_its_start(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t1 = datetime(2026, 5, 1, tzinfo=UTC)
    t2 = datetime(2026, 5, 2, tzinfo=UTC)
    t3 = datetime(2026, 5, 3, tzinfo=UTC)
    a1 = RemoteActivity(remote_id="r1", original_available=True, start=t1, revision="1")
    a2 = RemoteActivity(remote_id="r2", original_available=True, start=t2, revision="1")
    a3 = RemoteActivity(remote_id="r3", original_available=True, start=t3, revision="1")

    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(a3, a1, a2)))
    # a1 (the earliest) is deferred at fetch time; a2 and a3 both succeed and
    # are final, but the watermark must not skip past the still-unrecorded a1.
    connector.fetch_script.extend(
        [
            Deferred("not ready yet"),
            Fetched(data=_fit_bytes(b"two")),
            Fetched(data=_fit_bytes(b"three")),
        ]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    assert len(report.instances[0].deferred) == 1

    path = layout.connector_ledger_path(data_root, "src")
    assert not path.exists() or "watermark" not in _ledger_document(data_root, "src")


# ---------------------------------------------------------------------------
# The interrupt: one delivery recorded on disk, then re-raise.
# ---------------------------------------------------------------------------


def test_interrupt_after_one_delivery_leaves_it_recorded_and_reraises(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t1 = datetime(2026, 5, 1, tzinfo=UTC)
    t2 = datetime(2026, 5, 2, tzinfo=UTC)
    a1 = RemoteActivity(remote_id="r1", original_available=True, start=t1, revision="1")
    a2 = RemoteActivity(remote_id="r2", original_available=True, start=t2, revision="1")

    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(a2, a1)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"one")), KeyboardInterrupt("boom")]
    )

    assert not layout.connector_ledger_path(data_root, "src").exists()

    with pytest.raises(KeyboardInterrupt):
        _run(data_root, inbox, [_instance(connector)])

    doc = _ledger_document(data_root, "src")
    remote_ids = {e["remote_id"] for e in doc["entries"]}
    assert remote_ids == {"r1"}
    assert doc["entries"][0]["outcome"] == "delivered"


# ---------------------------------------------------------------------------
# Dry run.
# ---------------------------------------------------------------------------


def test_dry_run_leaves_the_sandbox_unchanged_and_reports_would_fetch(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    activity = RemoteActivity(
        remote_id="remote-1", original_available=True, start=_NOW, revision="r1"
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(activity,)))
    # fetch_script left empty: a dry run must never call fetch_activity.

    before_root = _snapshot(data_root)
    before_inbox = _snapshot(inbox)

    report = _run(data_root, inbox, [_instance(connector)], dry_run=True)

    after_root = _snapshot(data_root)
    after_inbox = _snapshot(inbox)

    assert before_root == after_root
    assert before_inbox == after_inbox
    assert connector.fetch_calls == []

    inst = report.instances[0]
    assert inst.would_fetch == ("remote-1",)
    assert inst.delivered == ()
    assert inst.listed == 1


# ---------------------------------------------------------------------------
# Channel sorting from an unsorted listing.
# ---------------------------------------------------------------------------


def test_report_channels_are_sorted_from_an_unsorted_listing(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    # Two delivered entries whose suggested_name (which drives the delivered
    # path) sorts in the *opposite* order of their remote_id, so sorting by
    # path and sorting by remote id are distinguishable.
    deliver_z = RemoteActivity(
        remote_id="remote-a-deliver",
        original_available=True,
        start=_NOW,
        revision="1",
        suggested_name="z-later-name.fit",
    )
    deliver_a = RemoteActivity(
        remote_id="remote-z-deliver",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
        suggested_name="a-earlier-name.fit",
    )
    skip_z = RemoteActivity(
        remote_id="remote-z-skip",
        original_available=False,
        unavailable_reason="no original",
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    skip_a = RemoteActivity(
        remote_id="remote-a-skip",
        original_available=False,
        unavailable_reason="no original",
        start=_NOW + timedelta(seconds=3),
        revision="1",
    )
    defer_z = RemoteActivity(
        remote_id="remote-z-defer",
        original_available=True,
        start=_NOW + timedelta(seconds=4),
        revision="1",
    )
    defer_a = RemoteActivity(
        remote_id="remote-a-defer",
        original_available=True,
        start=_NOW + timedelta(seconds=5),
        revision="1",
    )

    connector = ScriptedPuller()
    # Middle-of-listing shuffling: neither of a delivered/skipped/deferred
    # pair is placed first or last in the script.
    connector.listing_script.append(
        Listing(
            activities=(
                skip_z,
                deliver_z,
                defer_z,
                deliver_a,
                defer_a,
                skip_a,
            )
        )
    )
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"z")),
            Fetched(data=_fit_bytes(b"a")),
            Deferred("not ready"),
            Deferred("not ready"),
        ]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert [d.path for d in inst.delivered] == sorted(d.path for d in inst.delivered)
    assert inst.delivered[0].remote_id == "remote-z-deliver"  # a-earlier-name.fit
    assert inst.delivered[1].remote_id == "remote-a-deliver"  # z-later-name.fit

    assert [n.subject for n in inst.skipped] == ["remote-a-skip", "remote-z-skip"]
    assert [n.subject for n in inst.deferred] == ["remote-a-defer", "remote-z-defer"]


# ---------------------------------------------------------------------------
# Listing-level deferrals (design.md "PullEngine" step 6; Req 6.12).
# ---------------------------------------------------------------------------


def test_listing_deferral_becomes_a_deferred_note(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(),
            deferred=(
                ListingDeferral(subject="first-listing-item", reason="not ready A"),
                ListingDeferral(
                    subject="mid-listing-item", reason="cloud sync pending"
                ),
                ListingDeferral(subject="last-listing-item", reason="not ready B"),
            ),
        )
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert [(n.subject, n.detail) for n in inst.deferred] == [
        ("first-listing-item", "not ready A"),
        ("last-listing-item", "not ready B"),
        ("mid-listing-item", "cloud sync pending"),
    ]
    assert inst.failed == ()
    assert inst.delivered == ()
    assert inst.listed == 0


# ---------------------------------------------------------------------------
# _validate_entry: one failed-note case per check, each mid-listing between
# two entries that succeed normally, proving the bad entry neither stops nor
# is silently absorbed by its neighbors.
# ---------------------------------------------------------------------------


def test_control_character_remote_id_is_a_failed_note(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    good_1 = RemoteActivity(
        remote_id="good-1", original_available=True, start=_NOW, revision="1"
    )
    bad = RemoteActivity(
        remote_id="bad\x01id",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    good_2 = RemoteActivity(
        remote_id="good-2",
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(good_1, bad, good_2)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"g1")), Fetched(data=_fit_bytes(b"g2"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert [n.subject for n in inst.failed] == ["bad\x01id"]
    assert "invalid remote id" in inst.failed[0].detail
    assert {d.remote_id for d in inst.delivered} == {"good-1", "good-2"}
    assert all(a.remote_id != "bad\x01id" for a in connector.fetch_calls)
    # `listed` includes the entry that failed validation (Req 11.1).
    assert inst.listed == 3


def test_remote_id_length_limit_is_512_inclusive(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    at_limit_id = "a" * 512
    over_limit_id = "b" * 513
    good_before = RemoteActivity(
        remote_id="good-before", original_available=True, start=_NOW, revision="1"
    )
    at_limit = RemoteActivity(
        remote_id=at_limit_id,
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    over_limit = RemoteActivity(
        remote_id=over_limit_id,
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    good_after = RemoteActivity(
        remote_id="good-after",
        original_available=True,
        start=_NOW + timedelta(seconds=3),
        revision="1",
    )
    connector = ScriptedPuller()
    # Scrambled order; the two limit cases sit between the two good entries.
    connector.listing_script.append(
        Listing(activities=(good_before, over_limit, at_limit, good_after))
    )
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"before")),
            Fetched(data=_fit_bytes(b"at-limit")),
            Fetched(data=_fit_bytes(b"after")),
        ]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert [n.subject for n in inst.failed] == [over_limit_id]
    assert {d.remote_id for d in inst.delivered} == {
        "good-before",
        at_limit_id,
        "good-after",
    }


def test_naive_start_is_a_failed_note(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    good_1 = RemoteActivity(
        remote_id="good-1", original_available=True, start=_NOW, revision="1"
    )
    bad = RemoteActivity(
        remote_id="naive-start-id",
        original_available=True,
        start=datetime(2026, 6, 1, 0, 0, 5),  # no tzinfo
        revision="1",
    )
    good_2 = RemoteActivity(
        remote_id="good-2",
        original_available=True,
        start=_NOW + timedelta(seconds=10),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(good_1, bad, good_2)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"g1")), Fetched(data=_fit_bytes(b"g2"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert [n.subject for n in inst.failed] == ["naive-start-id"]
    assert "timezone-aware" in inst.failed[0].detail
    assert {d.remote_id for d in inst.delivered} == {"good-1", "good-2"}
    assert all(a.remote_id != "naive-start-id" for a in connector.fetch_calls)


def test_negative_duration_is_a_failed_note(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    good_1 = RemoteActivity(
        remote_id="good-1", original_available=True, start=_NOW, revision="1"
    )
    bad = RemoteActivity(
        remote_id="negative-duration-id",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        duration_s=-5.0,
        revision="1",
    )
    good_2 = RemoteActivity(
        remote_id="good-2",
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(good_1, bad, good_2)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"g1")), Fetched(data=_fit_bytes(b"g2"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert [n.subject for n in inst.failed] == ["negative-duration-id"]
    assert "duration" in inst.failed[0].detail
    assert {d.remote_id for d in inst.delivered} == {"good-1", "good-2"}
    assert all(a.remote_id != "negative-duration-id" for a in connector.fetch_calls)


def test_duplicate_remote_id_in_one_listing_is_a_failed_note(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    good_a = RemoteActivity(
        remote_id="good-a", original_available=True, start=_NOW, revision="1"
    )
    dup_first = RemoteActivity(
        remote_id="dup-id",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="rev1",
    )
    dup_second = RemoteActivity(
        remote_id="dup-id",
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="rev2",
    )
    good_b = RemoteActivity(
        remote_id="good-b",
        original_available=True,
        start=_NOW + timedelta(seconds=3),
        revision="1",
    )
    connector = ScriptedPuller()
    # dup_first precedes dup_second in listing order -- the first occurrence
    # is kept, the second is the failed note.
    connector.listing_script.append(
        Listing(activities=(good_a, dup_first, dup_second, good_b))
    )
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"a")),
            Fetched(data=_fit_bytes(b"dup")),
            Fetched(data=_fit_bytes(b"b")),
        ]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    assert report.instances[0].listed == 4
    inst = report.instances[0]

    assert [n.subject for n in inst.failed] == ["dup-id"]
    assert "more than once" in inst.failed[0].detail
    assert {d.remote_id for d in inst.delivered} == {"good-a", "dup-id", "good-b"}
    assert len(connector.fetch_calls) == 3


# ---------------------------------------------------------------------------
# PullReport.failed.
# ---------------------------------------------------------------------------


def test_pull_report_failed_true_only_for_a_failed_note(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    bad = RemoteActivity(
        remote_id="bad\x01id", original_available=True, start=_NOW, revision="1"
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(bad,)))

    report = _run(data_root, inbox, [_instance(connector)])

    assert report.instances[0].error is None
    assert report.instances[0].deferred == ()
    assert report.failed is True


def test_pull_report_not_failed_for_deferrals_only(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(),
            deferred=(ListingDeferral(subject="x", reason="not ready"),),
        )
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert report.instances[0].failed == ()
    assert len(report.instances[0].deferred) == 1
    assert report.failed is False


def test_pull_report_not_failed_for_a_clean_run(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    activity = RemoteActivity(
        remote_id="ok", original_available=True, start=_NOW, revision="1"
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"ok")))

    report = _run(data_root, inbox, [_instance(connector)])

    assert [d.remote_id for d in report.instances[0].delivered] == ["ok"]
    assert report.failed is False


# ---------------------------------------------------------------------------
# No ledger file or state directory until something is recorded (Req 7.5).
# ---------------------------------------------------------------------------


def test_no_ledger_file_or_state_dir_for_an_empty_pull(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=()))

    report = _run(data_root, inbox, [_instance(connector)])

    assert report.instances[0].error is None
    assert not (data_root / ".fitdocs").exists()


def test_ledger_file_and_state_dir_created_once_something_is_recorded(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    activity = RemoteActivity(
        remote_id="ok", original_available=True, start=_NOW, revision="1"
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"ok")))

    assert not (data_root / ".fitdocs").exists()

    _run(data_root, inbox, [_instance(connector)])

    assert layout.connector_ledger_path(data_root, "src").is_file()
    assert (data_root / ".fitdocs" / "connectors").is_dir()


def test_sweep_forgetting_the_last_entry_rewrites_the_ledger_file(
    tmp_path: Path,
) -> None:
    """M42: the ``ledger_existed`` half of the save guard. A sweep that
    forgets the sole entry (its pending file vanished before archiving)
    leaves ``has_content`` false, but the file existed before this run, so it
    must still be rewritten to reflect the forgetting.

    ``start=None`` is deliberate: a dated entry would leave a watermark
    behind even after the entry itself is forgotten, which alone makes
    ``has_content`` true and would pass even without the ``ledger_existed``
    half of the guard -- this fixture isolates that half.
    """
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="a", original_available=True, start=None, revision="1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"a")))
    _run(data_root, inbox, [_instance(connector)])

    ledger_path = layout.connector_ledger_path(data_root, "src")
    before = ledger_path.read_bytes()
    assert b"remote_id" in before  # falsity in the starting state: has content

    pending_file = next(inbox.rglob("*.fit"))
    pending_file.unlink()  # vanished before archiving -> forgotten by the sweep

    connector2 = ScriptedPuller()
    connector2.listing_script.append(Listing(activities=()))
    _run(data_root, inbox, [_instance(connector2)])

    after = ledger_path.read_bytes()
    assert after != before
    doc = _ledger_document(data_root, "src")
    assert doc["entries"] == []


# ---------------------------------------------------------------------------
# R1: sweep failures (an OSError reading or removing a pending file) become
# deferred notes, keyed by the pending path; the sweep and the pull continue.
# ---------------------------------------------------------------------------


def test_sweep_failure_becomes_a_deferred_note_and_the_pull_continues(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    data = _fit_bytes(b"cant-remove")
    connector = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=data))
    _run(data_root, inbox, [_instance(connector, name="aaa")])

    sha = hashlib.sha256(data).hexdigest()
    archive_path = layout.archive_path(data_root, sha)
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(data)

    pending_path = next(inbox.rglob("*.fit"))
    assert pending_path.is_file()  # falsity in the starting state

    # SW3: a secret registered with this run's Redactor, embedded in the
    # `_remove` stub's own message, pins that the sweep-failure detail is
    # redacted before it reaches the report.
    secret_token = "sw3-secret-token"  # noqa: S105 -- test fixture, not a real credential
    redactor = Redactor()
    redactor.add(secret_token)

    def _boom(path: Path) -> None:
        raise OSError(f"permission denied ({secret_token})")

    original_remove = delivery_mod._remove
    delivery_mod._remove = _boom
    try:
        connector2 = ScriptedPuller()
        connector2.listing_script.append(Listing(activities=()))
        connector3 = ScriptedPuller()
        connector3.listing_script.append(Listing(activities=()))
        report = _run(
            data_root,
            inbox,
            [_instance(connector2, name="aaa"), _instance(connector3, name="zzz")],
            redactor=redactor,
        )
    finally:
        delivery_mod._remove = original_remove

    inst = report.instances[0]
    assert inst.removed == ()
    assert inst.failed == ()
    assert len(inst.deferred) == 1
    pending_rel = pending_path.relative_to(inbox).as_posix()
    note = inst.deferred[0]
    assert note.subject == pending_rel
    assert note.detail.startswith("OSError: permission denied (")
    # SW3: the secret is redacted, not printed raw.
    assert REDACTED in note.detail
    assert secret_token not in note.detail
    assert pending_path.is_file()  # the mocked removal never actually happened
    # The second instance still ran normally after the first's sweep failure.
    assert report.instances[1].name == "zzz"
    assert report.instances[1].error is None


# ---------------------------------------------------------------------------
# R2: a new revision of an already-pending id -- same bytes keep the pending
# location; different bytes release the old copy (untracked) and deliver
# fresh.
# ---------------------------------------------------------------------------


def test_new_revision_with_identical_bytes_keeps_the_pending_location(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    data = _fit_bytes(b"same-bytes-across-revisions")
    connector1 = ScriptedPuller()
    activity1 = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="rev1"
    )
    connector1.listing_script.append(Listing(activities=(activity1,)))
    connector1.fetch_script.append(Fetched(data=data))
    first = _run(data_root, inbox, [_instance(connector1)])
    first_path = first.instances[0].delivered[0].path

    connector2 = ScriptedPuller()
    activity2 = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="rev2"
    )
    connector2.listing_script.append(Listing(activities=(activity2,)))
    connector2.fetch_script.append(Fetched(data=data))
    second = _run(data_root, inbox, [_instance(connector2)])

    # Nothing was written this run (Req 6.8, "already held", controller
    # ruling): the ledger entry's own outcome stays DELIVERED (checked
    # below), but it is reported in ``held``, not ``delivered``.
    assert second.instances[0].delivered == ()
    assert second.instances[0].held == ("a",)
    fit_files = list(inbox.rglob("*.fit"))
    assert len(fit_files) == 1  # no new file was written

    doc = _ledger_document(data_root, "src")
    entry = doc["entries"][0]
    assert entry["outcome"] == "delivered"
    assert entry["revision"] == "rev2"
    assert entry["pending"] == first_path


def test_new_revision_with_different_bytes_releases_the_old_copy(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    old_data = _fit_bytes(b"old-version-bytes")
    new_data = _fit_bytes(b"new-version-bytes-totally-different")
    connector1 = ScriptedPuller()
    activity1 = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="rev1"
    )
    connector1.listing_script.append(Listing(activities=(activity1,)))
    connector1.fetch_script.append(Fetched(data=old_data))
    first = _run(data_root, inbox, [_instance(connector1)])
    old_path = inbox / first.instances[0].delivered[0].path
    assert old_path.read_bytes() == old_data  # falsity in the starting state

    connector2 = ScriptedPuller()
    activity2 = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="rev2"
    )
    connector2.listing_script.append(Listing(activities=(activity2,)))
    connector2.fetch_script.append(Fetched(data=new_data))
    second = _run(data_root, inbox, [_instance(connector2)])

    new_path = inbox / second.instances[0].delivered[0].path
    assert new_path != old_path
    # The old copy is left in place, untouched, and no longer in the ledger.
    assert old_path.is_file()
    assert old_path.read_bytes() == old_data
    assert new_path.read_bytes() == new_data

    doc = _ledger_document(data_root, "src")
    assert len(doc["entries"]) == 1
    entry = doc["entries"][0]
    assert entry["outcome"] == "delivered"
    assert entry["revision"] == "rev2"
    assert entry["sha256"] == hashlib.sha256(new_data).hexdigest()
    assert entry["pending"] == new_path.relative_to(inbox).as_posix()


# ---------------------------------------------------------------------------
# (a) CRITICAL: the watermark is applied only when it would move forward.
# ---------------------------------------------------------------------------


def test_watermark_never_moves_backward_and_the_next_instance_still_runs(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t1 = datetime(2026, 5, 1, tzinfo=UTC)
    t10 = datetime(2026, 5, 10, tzinfo=UTC)
    first_connector = ScriptedPuller()
    first_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="a", original_available=True, start=t1, revision="1"
                ),
                RemoteActivity(
                    remote_id="b", original_available=True, start=t10, revision="1"
                ),
            )
        )
    )
    first_connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"a")), Fetched(data=_fit_bytes(b"b"))]
    )
    _run(data_root, inbox, [_instance(first_connector)])
    assert _ledger_document(data_root, "src")["watermark"] == t10

    t5 = datetime(2026, 5, 5, tzinfo=UTC)
    second_connector = ScriptedPuller()
    second_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="a", original_available=True, start=t1, revision="1"
                ),
                RemoteActivity(
                    remote_id="new", original_available=True, start=t5, revision="1"
                ),
                RemoteActivity(
                    remote_id="b", original_available=True, start=t10, revision="1"
                ),
            )
        )
    )
    second_connector.fetch_script.append(Deferred("later"))
    third_connector = ScriptedPuller()
    third_connector.listing_script.append(Listing(activities=()))

    report = _run(
        data_root,
        inbox,
        [
            _instance(second_connector, name="src"),
            _instance(third_connector, name="zzz"),
        ],
    )

    assert _ledger_document(data_root, "src")["watermark"] == t10  # unchanged
    assert report.instances[1].name == "zzz"
    assert report.instances[1].error is None


# ---------------------------------------------------------------------------
# (b) _compute_watermark: group by start, stop before any non-final start;
# every listed entry with an aware start blocks, including invalid/repeated
# ones.
# ---------------------------------------------------------------------------


def test_watermark_stops_before_a_middle_deferred_entry_exact_value(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t1 = datetime(2026, 5, 1, tzinfo=UTC)
    t2 = datetime(2026, 5, 2, tzinfo=UTC)
    t3 = datetime(2026, 5, 3, tzinfo=UTC)
    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="a3", original_available=True, start=t3, revision="1"
                ),
                RemoteActivity(
                    remote_id="a1", original_available=True, start=t1, revision="1"
                ),
                RemoteActivity(
                    remote_id="a2", original_available=True, start=t2, revision="1"
                ),
            )
        )
    )
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"1")),
            Deferred("wait"),
            Fetched(data=_fit_bytes(b"3")),
        ]
    )

    _run(data_root, inbox, [_instance(connector)])

    assert _ledger_document(data_root, "src")["watermark"] == t1


def test_watermark_tie_group_blocks_when_any_member_is_non_final(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 2, tzinfo=UTC)  # tie group
    connector = ScriptedPuller()
    # The tied group's *final* member (a1a) is listed BEFORE its non-final
    # sibling (a1b) deliberately: `_compute_watermark`'s sort is stable and
    # keyed on `start` alone, so a tie's relative order in `dated` follows
    # this listing order, not remote-id. Listing the non-final member first
    # would let a wrong "no real grouping" implementation, or one that only
    # checks a group's first member, get this case right by accident (the
    # first-scanned entry already being the non-final one) -- listing the
    # final member first defeats that coincidence.
    connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="a0", original_available=True, start=t0, revision="1"
                ),
                RemoteActivity(
                    remote_id="a1a", original_available=True, start=t1, revision="1"
                ),
                RemoteActivity(
                    remote_id="a1b", original_available=True, start=t1, revision="1"
                ),
            )
        )
    )
    # Fetch processing order (start, remote_id): a0(t0), a1a(t1), a1b(t1).
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"0")),
            Fetched(data=_fit_bytes(b"1a")),
            Deferred("wait"),
        ]
    )

    _run(data_root, inbox, [_instance(connector)])

    assert _ledger_document(data_root, "src")["watermark"] == t0


def test_watermark_tie_is_by_instant_not_by_spelling(tmp_path: Path) -> None:
    """Two starts at the same instant spelled with different UTC offsets
    form one tie group: the final member (listed first) cannot carry the
    watermark past its non-final twin."""
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1_utc = datetime(2026, 5, 2, tzinfo=UTC)
    t1_plus2 = datetime(2026, 5, 2, 2, 0, tzinfo=timezone(timedelta(hours=2)))
    assert t1_utc == t1_plus2 and t1_utc.isoformat() != t1_plus2.isoformat()
    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="a0", original_available=True, start=t0, revision="1"
                ),
                RemoteActivity(
                    remote_id="a1a",
                    original_available=True,
                    start=t1_utc,
                    revision="1",
                ),
                RemoteActivity(
                    remote_id="a1b",
                    original_available=True,
                    start=t1_plus2,
                    revision="1",
                ),
            )
        )
    )
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"0")),
            Fetched(data=_fit_bytes(b"1a")),
            Deferred("wait"),
        ]
    )

    _run(data_root, inbox, [_instance(connector)])

    assert _ledger_document(data_root, "src")["watermark"] == t0


def test_watermark_tie_group_blocks_when_the_non_final_member_is_listed_first(
    tmp_path: Path,
) -> None:
    """The mirror image of ``..._is_non_final`` above: the tied group's
    *non-final* member is listed FIRST here. Together the two fixtures
    defeat both "only the group's first member is checked" and "only the
    group's last member is checked" -- a single ordering can only catch one
    of the two."""
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 2, tzinfo=UTC)  # tie group
    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="a1b", original_available=True, start=t1, revision="1"
                ),
                RemoteActivity(
                    remote_id="a0", original_available=True, start=t0, revision="1"
                ),
                RemoteActivity(
                    remote_id="a1a", original_available=True, start=t1, revision="1"
                ),
            )
        )
    )
    # Fetch processing order (start, remote_id): a0(t0), a1a(t1), a1b(t1).
    connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"0")),
            Fetched(data=_fit_bytes(b"1a")),
            Deferred("wait"),
        ]
    )

    _run(data_root, inbox, [_instance(connector)])

    assert _ledger_document(data_root, "src")["watermark"] == t0


def test_watermark_blocked_by_an_invalid_entrys_own_aware_start(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t1 = datetime(2026, 5, 1, tzinfo=UTC)
    t2 = datetime(2026, 5, 2, tzinfo=UTC)
    t3 = datetime(2026, 5, 3, tzinfo=UTC)
    bad = RemoteActivity(
        remote_id="bad",
        original_available=True,
        start=t2,
        duration_s=-1.0,
        revision="1",
    )
    good_before = RemoteActivity(
        remote_id="good-before", original_available=True, start=t1, revision="1"
    )
    # A later, otherwise-final entry: if "bad" (invalid, so excluded from the
    # engine's own processed/valid entries) were also excluded from the
    # watermark's input, this group would wrongly look like the very next
    # one after good-before's, letting the watermark jump straight to t3.
    good_after = RemoteActivity(
        remote_id="good-after", original_available=True, start=t3, revision="1"
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(bad, good_after, good_before)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"before")), Fetched(data=_fit_bytes(b"after"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert [n.subject for n in report.instances[0].failed] == ["bad"]
    assert _ledger_document(data_root, "src")["watermark"] == t1


def test_watermark_blocked_by_a_repeated_entrys_own_start(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    t1 = datetime(2026, 5, 1, tzinfo=UTC)
    t2 = datetime(2026, 5, 2, tzinfo=UTC)  # tie: dup_a and dup_b share this start
    good = RemoteActivity(
        remote_id="good", original_available=True, start=t1, revision="1"
    )
    dup_a = RemoteActivity(
        remote_id="dup", original_available=True, start=t2, revision="rev-a"
    )
    dup_b = RemoteActivity(
        remote_id="dup", original_available=True, start=t2, revision="rev-b"
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(dup_b, good, dup_a)))
    # dup_b precedes dup_a in listing order, so dup_b (rev-b) is the kept,
    # first occurrence; dup_a is the failed, repeated one.
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"good")), Fetched(data=_fit_bytes(b"dup"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert [n.subject for n in report.instances[0].failed] == ["dup"]
    assert _ledger_document(data_root, "src")["watermark"] == t1
    assert report.instances[0].listed == 3


# ---------------------------------------------------------------------------
# (c)/(d): sweep failures -> deferred notes (see test above); deliver OSError
# -> failed note with the redacted "<Type>: <message>"; the run continues.
# ---------------------------------------------------------------------------


def test_deliver_oserror_is_a_failed_note_and_the_run_continues(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    # The instance name doubles as a secret registered with this run's
    # Redactor: it appears in the OSError's message (as the inbox
    # subdirectory name it could not create), so it also pins D1 (the
    # deliver-OSError detail is redacted, not raw) alongside the failed-note
    # and continuation pins.
    secret_instance_name = "topsecretinstance"
    redactor = Redactor()
    redactor.add(secret_instance_name)
    # The instance's delivery subdirectory can't be created: a plain file
    # already occupies that path.
    (inbox / secret_instance_name).write_text("i am a file, not a directory")

    connector = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"a")))

    other_connector = ScriptedPuller()
    other_connector.listing_script.append(Listing(activities=()))

    report = _run(
        data_root,
        inbox,
        [
            _instance(connector, name=secret_instance_name),
            _instance(other_connector, name="zzz"),
        ],
        redactor=redactor,
    )

    inst = report.instances[0]
    assert inst.delivered == ()
    assert len(inst.failed) == 1
    assert inst.failed[0].subject == "a"
    detail = inst.failed[0].detail
    assert detail.startswith("FileExistsError: ")
    # D3: the message part (not just the exception type) survives -- the
    # standard library's own wording for this OSError.
    stripped = detail.replace(str(tmp_path), "")
    assert "File exists" in stripped
    # D1: the secret instance name is redacted, not printed raw.
    assert REDACTED in detail
    assert secret_instance_name not in detail
    # The second instance still ran.
    assert report.instances[1].name == "zzz"
    assert report.instances[1].error is None
    assert report.failed is True


# ---------------------------------------------------------------------------
# M1/M44/M46: a dry run over an archived pending delivery plus an unavailable
# entry leaves the sandbox snapshot unchanged.
# ---------------------------------------------------------------------------


def test_dry_run_with_archived_pending_and_unavailable_entry_leaves_sandbox_unchanged(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    data = _fit_bytes(b"archived-pending")
    first_connector = ScriptedPuller()
    first_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="archived-id",
                    original_available=True,
                    start=_NOW,
                    revision="1",
                ),
            )
        )
    )
    first_connector.fetch_script.append(Fetched(data=data))
    _run(data_root, inbox, [_instance(first_connector)])

    sha = hashlib.sha256(data).hexdigest()
    archive_path = layout.archive_path(data_root, sha)
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(data)

    dry_connector = ScriptedPuller()
    unavailable = RemoteActivity(
        remote_id="unavailable-mid",
        original_available=False,
        unavailable_reason="license restricted",
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    available = RemoteActivity(
        remote_id="would-fetch-id",
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    dry_connector.listing_script.append(Listing(activities=(unavailable, available)))
    # fetch_script left empty: neither entry should reach fetch_activity
    # under a dry run.

    before_root = _snapshot(data_root)
    before_inbox = _snapshot(inbox)

    report = _run(data_root, inbox, [_instance(dry_connector)], dry_run=True)

    after_root = _snapshot(data_root)
    after_inbox = _snapshot(inbox)

    assert before_root == after_root
    assert before_inbox == after_inbox
    assert dry_connector.fetch_calls == []

    inst = report.instances[0]
    assert inst.removed == ()
    assert inst.delivered == ()
    assert [n.subject for n in inst.skipped] == ["unavailable-mid"]
    assert inst.would_fetch == ("would-fetch-id",)


# ---------------------------------------------------------------------------
# M2/M3/M36: a pull with an archived delivery gives removed, sorted; the
# saved ledger reflects the sweep (pending cleared).
# ---------------------------------------------------------------------------


def test_pull_with_archived_deliveries_gives_removed_sorted(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    # remote_id sorts "aaa-id" < "zzz-id", but the delivered *paths* sort the
    # other way -- defeats a mutation that forgets to sort by path.
    data_low_path = _fit_bytes(b"zzz-path")
    data_high_path = _fit_bytes(b"aaa-path")
    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="aaa-id",
                    original_available=True,
                    start=_NOW,
                    revision="1",
                    suggested_name="zzz-name.fit",
                ),
                RemoteActivity(
                    remote_id="zzz-id",
                    original_available=True,
                    start=_NOW + timedelta(seconds=1),
                    revision="1",
                    suggested_name="aaa-name.fit",
                ),
            )
        )
    )
    connector.fetch_script.extend(
        [Fetched(data=data_low_path), Fetched(data=data_high_path)]
    )
    first = _run(data_root, inbox, [_instance(connector)])
    paths = {d.remote_id: d.path for d in first.instances[0].delivered}
    for data, _remote_id in ((data_low_path, "aaa-id"), (data_high_path, "zzz-id")):
        sha = hashlib.sha256(data).hexdigest()
        archive_path = layout.archive_path(data_root, sha)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(data)

    second_connector = ScriptedPuller()
    second_connector.listing_script.append(Listing(activities=()))
    second = _run(data_root, inbox, [_instance(second_connector)])

    expected_sorted = tuple(sorted(paths.values()))
    assert second.instances[0].removed == expected_sorted

    doc = _ledger_document(data_root, "src")
    for entry in doc["entries"]:
        assert "pending" not in entry


# ---------------------------------------------------------------------------
# M20/M21: a Declined entry, in the ledger and the report.
# ---------------------------------------------------------------------------


def test_declined_entry_is_recorded_and_reported_as_skipped(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="declined-1", original_available=True, start=_NOW, revision="r1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Declined("license restricted"))

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]
    assert inst.delivered == ()
    assert inst.deferred == ()
    assert [(n.subject, n.detail) for n in inst.skipped] == [
        ("declined-1", "license restricted")
    ]

    doc = _ledger_document(data_root, "src")
    entry = doc["entries"][0]
    assert entry["outcome"] == "skipped"
    assert entry["detail"] == "license restricted"
    assert entry["revision"] == "r1"
    assert "sha256" not in entry


# ---------------------------------------------------------------------------
# M28: the exact Delivered.path literal.
# ---------------------------------------------------------------------------


def test_delivered_path_is_instance_slash_delivery_name(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    activity = RemoteActivity(
        remote_id="remote-1",
        original_available=True,
        start=_NOW,
        revision="r1",
        suggested_name="My Run.FIT",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"x")))

    report = _run(data_root, inbox, [_instance(connector, name="src")])

    # A literal, not `delivery_name(activity)`: the same function backs the
    # implementation under test, so calling it here would make this a
    # self-referential compare that cannot catch a change to `delivery_name`
    # itself. "My Run.FIT" -> the space (outside [A-Za-z0-9._-]) becomes "-";
    # it already ends in ".fit" case-insensitively, so that extension is
    # kept verbatim.
    assert report.instances[0].delivered == (
        Delivered(remote_id="remote-1", path="src/My-Run.FIT"),
    )


# ---------------------------------------------------------------------------
# M30: an earlier-run pending hash matched by a new id.
# ---------------------------------------------------------------------------


def test_pending_hash_from_an_earlier_run_matches_a_new_id(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    data = _fit_bytes(b"shared-across-separate-runs")
    first_connector = ScriptedPuller()
    first_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="first-id",
                    original_available=True,
                    start=_NOW,
                    revision="1",
                ),
            )
        )
    )
    first_connector.fetch_script.append(Fetched(data=data))
    first = _run(data_root, inbox, [_instance(first_connector)])
    assert [d.remote_id for d in first.instances[0].delivered] == ["first-id"]

    second_connector = ScriptedPuller()
    second_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="second-id",
                    original_available=True,
                    start=_NOW + timedelta(seconds=1),
                    revision="1",
                ),
            )
        )
    )
    second_connector.fetch_script.append(Fetched(data=data))
    second = _run(data_root, inbox, [_instance(second_connector)])

    assert second.instances[0].delivered == ()
    assert second.instances[0].held == ("second-id",)


# ---------------------------------------------------------------------------
# M31: held_hashes only reflects still-pending deliveries, never a resolved
# (already-held, not pending) entry's stale sha.
# ---------------------------------------------------------------------------


def test_a_resolved_already_held_entrys_sha_does_not_suppress_a_later_delivery(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    data = _fit_bytes(b"once-archived-later-purged")
    sha = hashlib.sha256(data).hexdigest()
    archive_path = layout.archive_path(data_root, sha)
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(data)

    first_connector = ScriptedPuller()
    first_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="old-held",
                    original_available=True,
                    start=_NOW,
                    revision="1",
                ),
            )
        )
    )
    first_connector.fetch_script.append(Fetched(data=data))
    first = _run(data_root, inbox, [_instance(first_connector)])
    assert first.instances[0].held == ("old-held",)

    # The archive copy is later purged -- the entry is neither pending nor
    # archived any more, so it must not suppress a fresh delivery of the
    # same bytes under a different id.
    archive_path.unlink()
    assert not archive_path.exists()  # falsity in the starting state

    second_connector = ScriptedPuller()
    second_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="new-id",
                    original_available=True,
                    start=_NOW + timedelta(seconds=1),
                    revision="1",
                ),
            )
        )
    )
    second_connector.fetch_script.append(Fetched(data=data))
    second = _run(data_root, inbox, [_instance(second_connector)])

    assert [d.remote_id for d in second.instances[0].delivered] == ["new-id"]
    assert second.instances[0].held == ()


# ---------------------------------------------------------------------------
# M33-M35: two or more out-of-order entries in would_fetch, held and failed.
# ---------------------------------------------------------------------------


def test_would_fetch_is_sorted_from_an_unsorted_listing(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="zzz",
                    original_available=True,
                    start=_NOW,
                    revision="1",
                ),
                RemoteActivity(
                    remote_id="mmm",
                    original_available=True,
                    start=_NOW + timedelta(seconds=1),
                    revision="1",
                ),
                RemoteActivity(
                    remote_id="aaa",
                    original_available=True,
                    start=_NOW + timedelta(seconds=2),
                    revision="1",
                ),
            )
        )
    )

    report = _run(data_root, inbox, [_instance(connector)], dry_run=True)

    assert report.instances[0].would_fetch == ("aaa", "mmm", "zzz")


def test_held_is_sorted_from_an_unsorted_listing(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    first_connector = ScriptedPuller()
    first_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="zzz", original_available=True, start=_NOW, revision="1"
                ),
                RemoteActivity(
                    remote_id="mmm",
                    original_available=True,
                    start=_NOW + timedelta(seconds=1),
                    revision="1",
                ),
                RemoteActivity(
                    remote_id="aaa",
                    original_available=True,
                    start=_NOW + timedelta(seconds=2),
                    revision="1",
                ),
            )
        )
    )
    first_connector.fetch_script.extend(
        [
            Fetched(data=_fit_bytes(b"z")),
            Fetched(data=_fit_bytes(b"m")),
            Fetched(data=_fit_bytes(b"a")),
        ]
    )
    _run(data_root, inbox, [_instance(first_connector)])

    second_connector = ScriptedPuller()
    second_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="zzz", original_available=True, start=_NOW, revision="1"
                ),
                RemoteActivity(
                    remote_id="mmm",
                    original_available=True,
                    start=_NOW + timedelta(seconds=1),
                    revision="1",
                ),
                RemoteActivity(
                    remote_id="aaa",
                    original_available=True,
                    start=_NOW + timedelta(seconds=2),
                    revision="1",
                ),
            )
        )
    )
    second = _run(data_root, inbox, [_instance(second_connector)])

    assert second.instances[0].held == ("aaa", "mmm", "zzz")


def test_failed_is_sorted_from_an_unsorted_listing(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="zzz\x01bad",
                    original_available=True,
                    start=_NOW,
                    revision="1",
                ),
                RemoteActivity(
                    remote_id="mmm\x01bad",
                    original_available=True,
                    start=_NOW + timedelta(seconds=1),
                    revision="1",
                ),
                RemoteActivity(
                    remote_id="aaa\x01bad",
                    original_available=True,
                    start=_NOW + timedelta(seconds=2),
                    revision="1",
                ),
            )
        )
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert [n.subject for n in report.instances[0].failed] == [
        "aaa\x01bad",
        "mmm\x01bad",
        "zzz\x01bad",
    ]


# ---------------------------------------------------------------------------
# M17: a start=None entry is processed last.
# ---------------------------------------------------------------------------


def test_start_none_entry_is_processed_last(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    no_start = RemoteActivity(
        remote_id="no-start", original_available=True, start=None, revision="1"
    )
    has_start = RemoteActivity(
        remote_id="has-start", original_available=True, start=_NOW
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(no_start, has_start)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"1")), Fetched(data=_fit_bytes(b"2"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert [a.remote_id for a in connector.fetch_calls] == ["has-start", "no-start"]
    assert report.instances[0].listed == 2


# ---------------------------------------------------------------------------
# M10, M11, M13, M14: a DEL char and an empty id rejected, duration 0
# accepted, unavailable-without-reason rejected.
# ---------------------------------------------------------------------------


def test_del_character_in_remote_id_is_rejected(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    good_1 = RemoteActivity(
        remote_id="good-1", original_available=True, start=_NOW, revision="1"
    )
    bad = RemoteActivity(
        remote_id="del\x7fid",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    good_2 = RemoteActivity(
        remote_id="good-2",
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(good_1, bad, good_2)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"g1")), Fetched(data=_fit_bytes(b"g2"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert [n.subject for n in report.instances[0].failed] == ["del\x7fid"]


def test_empty_remote_id_is_rejected(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    good_1 = RemoteActivity(
        remote_id="good-1", original_available=True, start=_NOW, revision="1"
    )
    bad = RemoteActivity(
        remote_id="",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    good_2 = RemoteActivity(
        remote_id="good-2",
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(good_1, bad, good_2)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"g1")), Fetched(data=_fit_bytes(b"g2"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert [n.subject for n in report.instances[0].failed] == [""]


def test_zero_duration_is_accepted(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    activity = RemoteActivity(
        remote_id="instant",
        original_available=True,
        start=_NOW,
        revision="1",
        duration_s=0.0,
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"instant")))

    report = _run(data_root, inbox, [_instance(connector)])

    assert report.instances[0].failed == ()
    assert [d.remote_id for d in report.instances[0].delivered] == ["instant"]


def test_unavailable_without_a_reason_is_rejected(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    good_1 = RemoteActivity(
        remote_id="good-1", original_available=True, start=_NOW, revision="1"
    )
    bad = RemoteActivity(
        remote_id="no-reason-id",
        original_available=False,
        unavailable_reason=None,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    good_2 = RemoteActivity(
        remote_id="good-2",
        original_available=True,
        start=_NOW + timedelta(seconds=2),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(good_1, bad, good_2)))
    connector.fetch_script.extend(
        [Fetched(data=_fit_bytes(b"g1")), Fetched(data=_fit_bytes(b"g2"))]
    )

    report = _run(data_root, inbox, [_instance(connector)])

    assert [n.subject for n in report.instances[0].failed] == ["no-reason-id"]
    assert report.instances[0].skipped == ()


# ---------------------------------------------------------------------------
# M38/M39/M61: PullReport.inbox, .dry_run, connector_id.
# ---------------------------------------------------------------------------


def test_report_field_literals(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=()))

    report = _run(data_root, inbox, [_instance(connector, name="src")], dry_run=True)

    assert report.inbox == str(inbox)
    assert report.dry_run is True
    assert report.instances[0].connector_id == "scripted-puller"


def test_report_dry_run_is_false_in_a_non_dry_run(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=()))

    report = _run(data_root, inbox, [_instance(connector)], dry_run=False)

    assert report.dry_run is False


# ---------------------------------------------------------------------------
# M57: the fetch-deferral subject is the remote id, not the suggested name.
# ---------------------------------------------------------------------------


def test_fetch_deferral_subject_is_the_remote_id(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    activity = RemoteActivity(
        remote_id="rid-1",
        original_available=True,
        start=_NOW,
        revision="1",
        suggested_name="pretty-name.fit",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(Deferred("try later"))

    report = _run(data_root, inbox, [_instance(connector)])

    assert report.instances[0].deferred == (
        PullNote(subject="rid-1", detail="try later"),
    )
    assert report.instances[0].listed == 1


# ---------------------------------------------------------------------------
# M4/M48-M51/M40: the unusable-ledger and non-puller ``error`` literals; and
# ``PullReport.failed`` via ``error`` alone (no failed notes).
# ---------------------------------------------------------------------------


def test_unusable_ledger_is_the_instance_error(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    ledger_path = layout.connector_ledger_path(data_root, "src")
    ledger_path.parent.mkdir(parents=True)
    ledger_path.write_text("this is not valid toml {{{")

    connector = ScriptedPuller()
    # No listing script queued: the connector must never be asked to list.

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert inst.error is not None
    assert inst.error.subject == "src"
    assert str(ledger_path) in inst.error.detail
    assert inst.failed == ()
    assert connector.list_calls == []
    assert report.failed is True


def test_connector_without_pull_activities_is_the_instance_error(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.capabilities = frozenset()

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert inst.error == PullNote(subject="src", detail="does not pull activities")
    assert inst.failed == ()
    assert report.failed is True


# ---------------------------------------------------------------------------
# M62: two-instance runs -- order preserved (not reversed); an instance
# error does not stop the next.
# ---------------------------------------------------------------------------


def test_two_instances_preserve_order_and_an_error_does_not_stop_the_next(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    bad_ledger_path = layout.connector_ledger_path(data_root, "aaa")
    bad_ledger_path.parent.mkdir(parents=True)
    bad_ledger_path.write_text("this is not valid toml {{{")

    bad_connector = ScriptedPuller()
    good_connector = ScriptedPuller()
    good_connector.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="ok", original_available=True, start=_NOW, revision="1"
                ),
            )
        )
    )
    good_connector.fetch_script.append(Fetched(data=_fit_bytes(b"ok")))

    report = _run(
        data_root,
        inbox,
        [_instance(bad_connector, name="aaa"), _instance(good_connector, name="zzz")],
    )

    assert [i.name for i in report.instances] == ["aaa", "zzz"]
    assert report.instances[0].error is not None
    assert [d.remote_id for d in report.instances[1].delivered] == ["ok"]


def test_same_revision_duplicate_counts_in_listed(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    first = RemoteActivity(
        remote_id="dup", original_available=True, start=_NOW, revision="r"
    )
    again = RemoteActivity(
        remote_id="dup",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="r",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(first, again)))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"d")))
    report = _run(data_root, inbox, [_instance(connector)])
    assert [n.subject for n in report.instances[0].failed] == ["dup"]
    assert report.instances[0].listed == 2


# ---------------------------------------------------------------------------
# Task 4.4: credentials, token renewal, per-item/per-instance isolation, and
# redaction (design.md "PullEngine" step 3, Req 4.7, 6.10, 6.11, 10.1, 10.2,
# 10.5).
#
# ``ScriptedPersonalKeyConnector``/``ScriptedLoginConnector`` (conftest.py,
# closed to new fixtures) are used with ``capabilities`` overridden to add
# ``Capability.PULL_ACTIVITIES``, exactly as their own docstrings describe.
# ---------------------------------------------------------------------------


def _store_login_credentials(
    store: CredentialStore,
    name: str,
    connector_id: str,
    *,
    token_value: str,
    expires_at: datetime,
) -> None:
    store.save(
        name,
        StoredCredentials(
            connector_id=connector_id,
            auth_style=AuthStyle.LOGIN,
            values={"access_token": Secret(token_value)},
            expires_at=expires_at,
            scopes=None,
        ),
    )


def _bytes_under(root: Path) -> list[tuple[Path, bytes]]:
    """Every regular file's bytes under ``root`` -- the ledger, the inbox,
    and (if present) the archive alike -- for a byte-level secret scan after
    a pull."""
    if not root.exists():
        return []
    return [
        (path, path.read_bytes()) for path in sorted(root.rglob("*")) if path.is_file()
    ]


class _CredentialObservingTransport:
    """A :data:`~fitdocs.connectors.http.Transport` that reads the
    credentials file straight off disk the instant it is called -- the
    first data request a connector makes -- rather than after returning, so
    a renewal only persisted *after* listing (instead of before it) would
    still be caught (Req 4.7)."""

    def __init__(self, store: CredentialStore, instance_name: str) -> None:
        self._store = store
        self._instance_name = instance_name
        self.observed_token_at_first_call: str | None = "unobserved"

    def __call__(self, request: HttpRequest, timeout: float) -> HttpResponse:
        if self.observed_token_at_first_call == "unobserved":
            stored = self._store.load(self._instance_name)
            self.observed_token_at_first_call = (
                stored.values["access_token"].reveal() if stored is not None else None
            )
        return HttpResponse(status=200, headers={}, body=b"{}")


def test_not_connected_names_the_connect_command_and_the_variable(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")

    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    instance = _instance(connector, name="keyed")

    report = _run(data_root, inbox, [instance], store=store)
    inst = report.instances[0]

    assert inst.error is not None
    assert inst.error.detail == (
        "NotConnectedError: keyed is not connected: run `fitdocs connect keyed`"
        " or set FITDOCS_CONNECTOR_KEYED_API_KEY"
    )
    # Reachability: the connector was never asked to list -- this is the
    # instance's terminal error, not a failed note about a listed entry.
    assert connector.list_calls == []
    assert inst.failed == ()


def test_credentials_are_resolved_before_the_capability_refusal(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")

    # No PULL_ACTIVITIES *and* no usable credentials: design.md's order
    # (credentials at step 3, before the capability refusal at step 4)
    # means the not-connected error is reported, never "does not pull
    # activities" -- a reviewer-visible way to defeat the plausible wrong
    # order (capability check first, as task 4.3 had it).
    connector = ScriptedPersonalKeyConnector(capabilities=frozenset())
    instance = _instance(connector, name="keyed")

    report = _run(data_root, inbox, [instance], store=store)
    inst = report.instances[0]

    assert inst.error is not None
    assert "does not pull activities" not in inst.error.detail
    assert f"fitdocs connect {instance.name}" in inst.error.detail


def test_expired_login_token_is_renewed_and_on_disk_before_the_first_data_request(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    name = "logged"

    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES}),
        data_url="https://svc.example/activities",
    )
    _store_login_credentials(
        store,
        name,
        connector.connector_id,
        token_value="old-token",
        # Exactly at the 60s margin (design.md step 3): the inclusive
        # boundary, paired below against one second past it.
        expires_at=_NOW + timedelta(seconds=60),
    )
    connector.refresh_script.append(
        TokenSet(
            values={"access_token": Secret("new-token")},
            expires_at=_NOW + timedelta(hours=1),
            scopes=None,
        )
    )
    connector.listing_script.append(Listing(activities=()))

    observing_transport = _CredentialObservingTransport(store, name)

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name=name)],
        store=store,
        now=lambda: _NOW,
        transport=observing_transport,
    )

    inst = report.instances[0]
    assert inst.error is None
    # Falsity in the starting state: the credentials file held "old-token"
    # before this pull; the renewed value must already be on disk at the
    # moment of the first data request, not merely by the time the pull
    # finishes.
    assert observing_transport.observed_token_at_first_call == "new-token"
    stored_after = store.load(name)
    assert stored_after is not None
    assert stored_after.values["access_token"].reveal() == "new-token"
    assert connector.refresh_calls == 1


def test_a_token_not_yet_within_the_renewal_margin_is_not_renewed(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    name = "logged"

    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store,
        name,
        connector.connector_id,
        token_value="still-good",
        # One second past the 60s margin boundary pinned above.
        expires_at=_NOW + timedelta(seconds=61),
    )
    connector.listing_script.append(Listing(activities=()))
    # refresh_script deliberately left empty: UnscriptedCall (a
    # BaseException) would propagate out of this test if refresh were ever
    # called, since nothing here catches it.

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name=name)],
        store=store,
        now=lambda: _NOW,
    )

    inst = report.instances[0]
    assert inst.error is None
    assert connector.refresh_calls == 0
    stored_after = store.load(name)
    assert stored_after is not None
    assert stored_after.values["access_token"].reveal() == "still-good"


def test_renewal_persists_under_dry_run_and_nothing_else_is_written(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    name = "logged"

    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store,
        name,
        connector.connector_id,
        token_value="old-token",
        expires_at=_NOW + timedelta(seconds=1),
    )
    connector.refresh_script.append(
        TokenSet(
            values={"access_token": Secret("fresh-token")},
            expires_at=_NOW + timedelta(hours=1),
            scopes=None,
        )
    )
    connector.listing_script.append(Listing(activities=()))

    before_root = _snapshot(data_root)
    before_inbox = _snapshot(inbox)

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name=name)],
        store=store,
        dry_run=True,
        now=lambda: _NOW,
    )

    after_root = _snapshot(data_root)
    after_inbox = _snapshot(inbox)

    inst = report.instances[0]
    assert inst.error is None
    assert connector.refresh_calls == 1
    stored_after = store.load(name)
    assert stored_after is not None
    assert stored_after.values["access_token"].reveal() == "fresh-token"
    # Nothing else was written: a dry run's renewal is the one exception to
    # "writes nothing under the data root or in the inbox".
    assert before_root == after_root
    assert before_inbox == after_inbox


def test_one_instances_not_connected_error_does_not_stop_the_next(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")

    failing = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    # No stored or environment credentials at all for "failing".

    ok = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    activity = RemoteActivity(
        remote_id="r1", original_available=True, start=_NOW, revision="1"
    )
    ok.listing_script.append(Listing(activities=(activity,)))
    ok.fetch_script.append(Fetched(data=_fit_bytes(b"ok")))

    environ = {env_var_name("ok-instance", "api_key"): "k-value"}

    report = _run(
        data_root,
        inbox,
        [_instance(failing, name="aaa"), _instance(ok, name="ok-instance")],
        store=store,
        environ=environ,
    )

    assert [i.name for i in report.instances] == ["aaa", "ok-instance"]
    assert report.instances[0].error is not None
    assert report.instances[1].error is None
    assert [d.remote_id for d in report.instances[1].delivered] == ["r1"]


def test_one_items_exception_does_not_stop_its_instance(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    first = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="1"
    )
    second = RemoteActivity(
        remote_id="b",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(first, second)))
    connector.fetch_script.append(ValueError("transient glitch"))
    connector.fetch_script.append(Fetched(data=_fit_bytes(b"second")))

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert inst.error is None
    assert [note.subject for note in inst.failed] == ["a"]
    assert "ValueError" in inst.failed[0].detail
    assert [d.remote_id for d in inst.delivered] == ["b"]


def test_connector_error_quoting_the_key_is_reported_redacted(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    name = "keyed"
    api_key = "sekrit-abc-999"

    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    activity = RemoteActivity(
        remote_id="r1", original_available=True, start=_NOW, revision="1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(ConnectorError(f"upstream rejected key {api_key}"))

    environ = {env_var_name(name, "api_key"): api_key}
    report = _run(data_root, inbox, [_instance(connector, name=name)], environ=environ)
    inst = report.instances[0]

    assert inst.error is not None
    assert REDACTED in inst.error.detail
    assert api_key not in inst.error.detail
    assert inst.failed == ()


def test_declined_and_unavailable_reason_are_redacted_and_leave_no_secret_on_disk(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    name = "keyed"
    api_key = "key-for-redaction-check"

    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    declined_activity = RemoteActivity(
        remote_id="declined-1", original_available=True, start=_NOW, revision="1"
    )
    unavailable_activity = RemoteActivity(
        remote_id="unavailable-1",
        original_available=False,
        start=_NOW + timedelta(seconds=1),
        revision="1",
        unavailable_reason=f"blocked for key {api_key}",
    )
    connector.listing_script.append(
        Listing(activities=(declined_activity, unavailable_activity))
    )
    connector.fetch_script.append(
        Declined(reason=f"declined, key {api_key} over quota")
    )

    environ = {env_var_name(name, "api_key"): api_key}
    report = _run(data_root, inbox, [_instance(connector, name=name)], environ=environ)
    inst = report.instances[0]

    assert len(inst.skipped) == 2
    for note in inst.skipped:
        assert api_key not in note.detail
        assert REDACTED in note.detail

    doc = _ledger_document(data_root, name)
    assert len(doc["entries"]) == 2
    for entry in doc["entries"]:
        detail = entry.get("detail", "")
        assert api_key not in detail
        assert REDACTED in detail

    scanned = _bytes_under(data_root) + _bytes_under(inbox)
    assert scanned, "the byte scan is looking at the wrong directory"
    for _path, content in scanned:
        assert api_key.encode() not in content


def test_auth_failure_from_listing_ends_the_instance_with_its_next_step(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(
        AuthFailure(AuthFailureKind.RATE_LIMITED, "slow down", retry_after_s=30.0)
    )

    report = _run(data_root, inbox, [_instance(connector, name="src")])
    inst = report.instances[0]

    assert inst.error is not None
    assert "slow down" in inst.error.detail
    expected_step = next_step(
        AuthFailureKind.RATE_LIMITED, name="src", retry_after_s=30.0
    )
    assert expected_step in inst.error.detail
    assert inst.failed == ()


def test_a_generic_listing_exception_ends_the_instance(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    connector = ScriptedPuller()
    connector.listing_script.append(RuntimeError("source unreachable"))

    report = _run(data_root, inbox, [_instance(connector, name="src")])
    inst = report.instances[0]

    assert inst.error is not None
    # Exact: an ordinary (non-AuthFailure, non-TransportError) listing
    # exception gets no addendum -- just its type and message, not a
    # traceback (kills O18, `traceback.format_exception` in
    # `_instance_error`).
    assert inst.error.detail == "RuntimeError: source unreachable"
    assert inst.listed == 0


# ---------------------------------------------------------------------------
# Task 4.4 remediation round 2: a fetch TransportError is a failed note (not
# instance-ending); a fetch AuthFailure still ends the instance and the next
# instance still runs; a renewal AuthFailure/TransportError/
# CredentialStoreError each end only their own instance, redacted; an item
# exception's message is redacted; the renewal session is built in
# CallMode.AUTH, not CallMode.DATA.
# ---------------------------------------------------------------------------


def test_item_transport_error_is_a_failed_note_and_the_instance_continues(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    a = RemoteActivity(remote_id="a", original_available=True, start=_NOW, revision="1")
    b = RemoteActivity(
        remote_id="b",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(a, b)))
    connector.fetch_script.extend(
        [
            TransportError("timed out: https://svc.example/x"),
            Fetched(data=_fit_bytes(b"b")),
        ]
    )

    report = _run(data_root, inbox, [_instance(connector)])
    inst = report.instances[0]

    assert inst.error is None
    assert [n.subject for n in inst.failed] == ["a"]
    # Exact "<Type>: <message>" (kills O19, `f"{exc!r}"` in the item note);
    # a fetch TransportError must stay a failed note, not instance-ending
    # (kills N2, adding TransportError to the instance-ending fetch tuple).
    assert inst.failed[0].detail == "TransportError: timed out: https://svc.example/x"
    assert [d.remote_id for d in inst.delivered] == ["b"]


def test_fetch_auth_failure_ends_the_instance_and_the_next_instance_runs(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"

    a = RemoteActivity(remote_id="a", original_available=True, start=_NOW, revision="1")
    b = RemoteActivity(
        remote_id="b",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    aaa = ScriptedPuller()
    aaa.listing_script.append(Listing(activities=(a, b)))
    aaa.fetch_script.extend(
        [AuthFailure(AuthFailureKind.REJECTED, "nope"), Fetched(data=_fit_bytes(b"b"))]
    )

    zzz = ScriptedPuller()
    zzz_activity = RemoteActivity(
        remote_id="z1", original_available=True, start=_NOW, revision="1"
    )
    zzz.listing_script.append(Listing(activities=(zzz_activity,)))
    zzz.fetch_script.append(Fetched(data=_fit_bytes(b"z")))

    report = _run(
        data_root,
        inbox,
        [_instance(aaa, name="aaa"), _instance(zzz, name="zzz")],
    )
    inst_aaa, inst_zzz = report.instances

    assert inst_aaa.error is not None
    # The design's NEXT_STEPS[REJECTED] literal, named "aaa" -- a literal
    # copy, not the imported `next_step` constant, so a change to the
    # table's own text is pinned rather than compared against itself.
    assert (
        "Check the credentials and run `fitdocs connect aaa` again."
        in inst_aaa.error.detail
    )
    assert inst_aaa.failed == ()
    assert inst_aaa.delivered == ()
    # "b" was never fetched: the instance-ending break happened on "a"
    # before "b" was reached (kills O11, break -> continue after an
    # instance-ending fetch error).
    assert [activity.remote_id for activity in aaa.fetch_calls] == ["a"]
    assert len(aaa.fetch_script) == 1

    assert inst_zzz.error is None
    assert [d.remote_id for d in inst_zzz.delivered] == ["z1"]


def test_renewal_auth_failure_ends_the_instance_redacted_and_the_next_runs(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    name = "logged"

    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store,
        name,
        connector.connector_id,
        token_value="tok-secret-1",
        expires_at=_NOW,
    )
    connector.refresh_script.append(
        AuthFailure(AuthFailureKind.REJECTED, "token tok-secret-1 revoked")
    )

    healthy = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="z1", original_available=True, start=_NOW, revision="1"
    )
    healthy.listing_script.append(Listing(activities=(activity,)))
    healthy.fetch_script.append(Fetched(data=_fit_bytes(b"z")))

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name=name), _instance(healthy, name="zzz")],
        store=store,
        now=lambda: _NOW,
    )
    inst, inst2 = report.instances

    assert inst.error is not None
    assert REDACTED in inst.error.detail
    assert "tok-secret-1" not in inst.error.detail
    expected_step = next_step(AuthFailureKind.REJECTED, name=name, retry_after_s=None)
    assert expected_step in inst.error.detail

    # The store started with "tok-secret-1"; a failed renewal must leave
    # it exactly as it was.
    stored_after = store.load(name)
    assert stored_after is not None
    assert stored_after.values["access_token"].reveal() == "tok-secret-1"

    assert inst2.error is None
    assert [d.remote_id for d in inst2.delivered] == ["z1"]


def test_renewal_transport_error_ends_the_instance_and_the_next_runs(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    name = "logged"

    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store, name, connector.connector_id, token_value="old-token", expires_at=_NOW
    )
    connector.refresh_script.append(
        TransportError("timed out: https://svc.example/token")
    )

    healthy = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="z1", original_available=True, start=_NOW, revision="1"
    )
    healthy.listing_script.append(Listing(activities=(activity,)))
    healthy.fetch_script.append(Fetched(data=_fit_bytes(b"z")))

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name=name), _instance(healthy, name="zzz")],
        store=store,
        now=lambda: _NOW,
    )
    inst, inst2 = report.instances

    assert inst.error is not None
    assert inst.error.detail.startswith("TransportError: ")
    expected_step = next_step(
        AuthFailureKind.UNAVAILABLE, name=name, retry_after_s=None
    )
    assert expected_step in inst.error.detail
    stored_after = store.load(name)
    assert stored_after is not None
    assert stored_after.values["access_token"].reveal() == "old-token"

    assert inst2.error is None
    assert [d.remote_id for d in inst2.delivered] == ["z1"]


def test_permissive_credentials_file_is_the_instance_error_and_the_next_runs(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    name = "keyed"

    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    store.save(
        name,
        StoredCredentials(
            connector_id=connector.connector_id,
            auth_style=AuthStyle.API_KEY,
            values={"api_key": Secret("k-value")},
            expires_at=None,
            scopes=None,
        ),
    )
    path = store.path_for(name)
    path.chmod(0o644)  # group/other-readable -- CredentialStore.load refuses this

    healthy = ScriptedPuller()
    activity = RemoteActivity(
        remote_id="z1", original_available=True, start=_NOW, revision="1"
    )
    healthy.listing_script.append(Listing(activities=(activity,)))
    healthy.fetch_script.append(Fetched(data=_fit_bytes(b"z")))

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name=name), _instance(healthy, name="zzz")],
        store=store,
    )
    inst, inst2 = report.instances

    assert inst.error is not None
    assert inst.error.detail == (
        f"CredentialStoreError: {path} is accessible by other users;"
        f" run: chmod 600 {path}"
    )

    assert inst2.error is None
    assert [d.remote_id for d in inst2.delivered] == ["z1"]


def test_item_exception_message_is_redacted(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    name = "keyed"
    api_key = "key-for-item-redaction"

    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    activity = RemoteActivity(
        remote_id="r1", original_available=True, start=_NOW, revision="1"
    )
    connector.listing_script.append(Listing(activities=(activity,)))
    connector.fetch_script.append(ValueError(f"bad {api_key}"))

    environ = {env_var_name(name, "api_key"): api_key}
    report = _run(data_root, inbox, [_instance(connector, name=name)], environ=environ)
    inst = report.instances[0]

    # Exact: catches both a missing redaction (kills O5) and a `repr`-shaped
    # note (kills O19).
    assert inst.failed[0].detail == f"ValueError: bad {REDACTED}"


class _AuthModeCheckingConnector(ScriptedLoginConnector):
    """Calls ``session.http.get`` itself before delegating to the scripted
    ``refresh`` -- lets a test observe the ``HttpClient`` mode the renewal
    session was actually built with. ``CallMode.AUTH`` makes exactly one
    request whatever the response; ``CallMode.DATA`` would retry a 503 up to
    ``MAX_DATA_ATTEMPTS`` times (``connectors/http.py``, Req 9.3-9.5)."""

    def refresh(self, session: ConnectorSession) -> TokenSet:
        session.http.get("https://svc.example/token")
        return super().refresh(session)


def test_renewal_session_uses_auth_mode_not_data_mode(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    name = "logged"

    connector = _AuthModeCheckingConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store, name, connector.connector_id, token_value="old", expires_at=_NOW
    )
    connector.refresh_script.append(
        TokenSet(
            values={"access_token": Secret("new")},
            expires_at=_NOW + timedelta(hours=1),
            scopes=None,
        )
    )
    connector.listing_script.append(Listing(activities=()))

    # A 503: a DATA-mode session would retry this up to MAX_DATA_ATTEMPTS
    # times; an AUTH-mode session makes exactly one request regardless.
    transport = FakeTransport([HttpResponse(status=503, headers={}, body=b"")])

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name=name)],
        store=store,
        now=lambda: _NOW,
        transport=transport,
    )

    assert report.instances[0].error is None
    # Kills O9 (the renewal session built with CallMode.DATA).
    assert len(transport.requests) == 1


# --- reviewer round-2 proposed pins -------------------------------------


@pytest.mark.parametrize(
    "store_exc",
    [
        OSError(28, "No space left on device"),
        CredentialStoreError("creds/logged.toml could not be written"),
    ],
    ids=["oserror", "credential-store-error"],
)
def test_renewal_store_failure_ends_the_instance_and_the_next_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, store_exc: Exception
) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    store = CredentialStore(tmp_path / "creds")
    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store, "logged", connector.connector_id, token_value="old", expires_at=_NOW
    )
    connector.refresh_script.append(
        TokenSet(
            values={"access_token": Secret("new")},
            expires_at=_NOW + timedelta(hours=1),
            scopes=None,
        )
    )

    def failing_save(self: CredentialStore, name: str, stored: object) -> None:
        raise store_exc

    monkeypatch.setattr(CredentialStore, "save", failing_save)

    healthy = ScriptedPuller()
    healthy.listing_script.append(
        Listing(
            activities=(
                RemoteActivity(
                    remote_id="z1", original_available=True, start=_NOW, revision="1"
                ),
            )
        )
    )
    healthy.fetch_script.append(Fetched(data=_fit_bytes(b"z")))

    report = _run(
        data_root,
        inbox,
        [_instance(connector, name="logged"), _instance(healthy, name="zzz")],
        store=store,
        now=lambda: _NOW,
    )
    inst, inst2 = report.instances
    assert inst.error is not None
    assert inst.error.detail == f"{type(store_exc).__name__}: {store_exc}"
    assert connector.list_calls == []
    assert [d.remote_id for d in inst2.delivered] == ["z1"]


def test_a_renewed_token_quoted_by_a_later_error_is_redacted(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    store = CredentialStore(tmp_path / "creds")
    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store, "logged", connector.connector_id, token_value="old", expires_at=_NOW
    )
    # Built with Secret(...) directly, not session.secret(...): only the pull
    # engine's own registration of the issued TokenSet can redact it.
    connector.refresh_script.append(
        TokenSet(
            values={"access_token": Secret("brand-new-tok-77")},
            expires_at=_NOW + timedelta(hours=1),
            scopes=None,
        )
    )
    connector.listing_script.append(
        ConnectorError("listing refused for brand-new-tok-77")
    )
    report = _run(
        data_root,
        tmp_path / "inbox",
        [_instance(connector, name="logged")],
        store=store,
        now=lambda: _NOW,
    )
    error = report.instances[0].error
    assert error is not None
    assert error.detail == "ConnectorError: listing refused for <redacted>"


def test_failed_fetches_are_left_unrecorded(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "inbox"
    first = RemoteActivity(
        remote_id="a", original_available=True, start=_NOW, revision="1"
    )
    second = RemoteActivity(
        remote_id="b",
        original_available=True,
        start=_NOW + timedelta(seconds=1),
        revision="1",
    )
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(first, second)))
    connector.fetch_script.extend(
        [ValueError("glitch"), Fetched(data=_fit_bytes(b"b"))]
    )
    _run(data_root, inbox, [_instance(connector)])
    doc = _ledger_document(data_root, "src")
    assert [entry["remote_id"] for entry in doc["entries"]] == ["b"]


def test_fetch_auth_failure_leaves_the_item_unrecorded(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    a = RemoteActivity(remote_id="a", original_available=True, start=_NOW, revision="1")
    connector = ScriptedPuller()
    connector.listing_script.append(Listing(activities=(a,)))
    connector.fetch_script.append(AuthFailure(AuthFailureKind.REJECTED, "nope"))
    _run(data_root, tmp_path / "inbox", [_instance(connector)])
    assert not layout.connector_ledger_path(data_root, "src").exists()


def test_deferral_reasons_are_redacted(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    name = "keyed"
    api_key = "key-in-a-deferral"
    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    activity = RemoteActivity(
        remote_id="r1", original_available=True, start=_NOW, revision="1"
    )
    connector.listing_script.append(
        Listing(
            activities=(activity,),
            deferred=(
                ListingDeferral(subject="page-2", reason=f"page {api_key} later"),
            ),
        )
    )
    connector.fetch_script.append(Deferred(reason=f"not ready for {api_key}"))
    environ = {env_var_name(name, "api_key"): api_key}
    report = _run(
        data_root,
        tmp_path / "inbox",
        [_instance(connector, name=name)],
        environ=environ,
    )
    assert [(n.subject, n.detail) for n in report.instances[0].deferred] == [
        ("page-2", "page <redacted> later"),
        ("r1", "not ready for <redacted>"),
    ]


def test_an_interrupt_during_listing_or_renewal_propagates(tmp_path: Path) -> None:
    data_root = tmp_path / "root"
    data_root.mkdir()
    lister = ScriptedPuller()
    lister.listing_script.append(KeyboardInterrupt("stop"))
    with pytest.raises(KeyboardInterrupt):
        _run(data_root, tmp_path / "inbox", [_instance(lister)])

    store = CredentialStore(tmp_path / "creds")
    renewer = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    _store_login_credentials(
        store, "logged", renewer.connector_id, token_value="old", expires_at=_NOW
    )
    renewer.refresh_script.append(KeyboardInterrupt("stop"))
    with pytest.raises(KeyboardInterrupt):
        _run(
            data_root,
            tmp_path / "inbox",
            [_instance(renewer, name="logged")],
            store=store,
            now=lambda: _NOW,
        )
