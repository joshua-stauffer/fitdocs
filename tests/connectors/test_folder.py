"""Pins for the built-in local-folder connector (design.md "FolderConnector",
Req 2.1, 13.1-13.9).

Every mutation-worthy fixture below is built to defeat the specific wrong
implementation the task text calls out: the three overlap refusals are
checked as three *separate* branches so dropping any one of them reds only
its own test, and each message assertion strips the *other* path's text out
of the message before checking a path is present, so a nested/parent pair
whose string forms are prefixes of each other cannot pass on one path's text
alone; the settle-interval pin uses a fake ``sleep`` that grows the file
between the two observations; the source-tree snapshot pin records every
entry's kind, permission bits, modification time, and (for files) bytes,
before and after, so a stray directory creation or permission change is
caught exactly as a stray write would be, not only a changed file's bytes.
"""

from __future__ import annotations

import dataclasses
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fitdocs import inbox as fitdocs_inbox
from fitdocs.connectors import registry
from fitdocs.connectors.errors import ConnectorError, ConnectorSettingsError
from fitdocs.connectors.folder import (
    FOLDER_CONNECTOR_ID,
    FolderConnector,
    FolderSettings,
)
from fitdocs.connectors.http import CallMode, HttpClient
from fitdocs.connectors.protocol import (
    Capability,
    ConnectorSession,
    Deferred,
    Fetched,
    RemoteActivity,
    SettingsContext,
)
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.inbox import DEFAULT_INBOX_SETTINGS
from tests.connectors.conftest import FakeTransport


class _StubCredentials:
    def value(self, field: str) -> Secret:  # pragma: no cover - unused by these tests
        raise AssertionError("the folder connector needs no credentials")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: object) -> None:  # pragma: no cover - unused
        raise AssertionError("the folder connector needs no credentials")


def _session(
    settings: object,
    *,
    data_root: Path,
    sleep: Callable[[float], None] | None = None,
) -> ConnectorSession:
    redactor = Redactor()
    http = HttpClient(
        FakeTransport([]),
        mode=CallMode.DATA,
        redactor=redactor,
        sleep=lambda seconds: None,
    )
    return ConnectorSession(
        instance="folder-instance",
        settings=settings,
        http=http,
        credentials=_StubCredentials(),
        data_root=data_root,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        sleep=sleep if sleep is not None else (lambda seconds: None),
        redactor=redactor,
    )


def _context(data_root: Path, inbox: Path) -> SettingsContext:
    return SettingsContext(data_root=data_root, inbox=inbox)


def _tree_snapshot(root: Path) -> dict[str, tuple[str, int, int, bytes | None]]:
    """Kind, permission bits, modification time, and (for files) content for
    every entry under *root* -- proves the source tree is genuinely
    untouched, not merely that files which already existed still hold the
    same bytes (a stray ``mkdir`` or ``chmod`` shows up here too)."""
    snapshot: dict[str, tuple[str, int, int, bytes | None]] = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        kind = "dir" if path.is_dir() else "file"
        content = path.read_bytes() if path.is_file() else None
        snapshot[str(path.relative_to(root))] = (
            kind,
            stat.S_IMODE(info.st_mode),
            info.st_mtime_ns,
            content,
        )
    return snapshot


def _assert_names_both_independently(message: str, path_a: Path, path_b: Path) -> None:
    """Assert both *path_a* and *path_b* appear in *message*, defeating the
    prefix confound where a parent directory's path string is a lexical
    prefix of its own child's (e.g. ``/data/inbox`` is a prefix of
    ``/data/inbox/phone``): checking each string's mere presence would pass
    even if only the longer one -- which already embeds the shorter one --
    were actually printed. The longer string is stripped out first; the
    shorter one must still be found, meaning it was printed on its own.
    """
    str_a, str_b = str(path_a), str(path_b)
    longer, shorter = (str_a, str_b) if len(str_a) >= len(str_b) else (str_b, str_a)
    assert longer in message
    without_longer = message.replace(longer, "")
    assert shorter in without_longer


# ---------------------------------------------------------------------------
# Declaration
# ---------------------------------------------------------------------------


def test_declaration_matches_design() -> None:
    connector = FolderConnector()
    assert connector.connector_id == "folder"
    assert connector.connector_id == FOLDER_CONNECTOR_ID
    # Design literals (design.md "FolderConnector"), not derived from the
    # connector's own attributes -- a change to either constant reds this.
    assert connector.display_name == "Local folder"
    assert connector.auth_style.value == "none"
    assert connector.capabilities == frozenset({Capability.PULL_ACTIVITIES})
    assert connector.credential_fields == ()
    reason = registry.validate_connector(connector)
    assert reason is None


def test_get_folder_connector_in_a_fresh_interpreter() -> None:
    # Every other test in this module shares one interpreter with the whole
    # `tests/connectors` run, so `fitdocs.connectors` is already imported
    # (and the folder connector already registered) before any test body
    # runs. A genuinely fresh process is the only way to observe the
    # registration actually happening *at import time*, not merely having
    # already happened by the time this test executes.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import fitdocs.connectors as c\n"
            "connector = c.get('folder')\n"
            "assert connector.connector_id == 'folder', connector.connector_id\n",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# parse_settings: path resolution
# ---------------------------------------------------------------------------


def test_relative_path_resolves_against_the_data_root(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    source_dir = data_root / "phone-exports"
    source_dir.mkdir(parents=True)
    inbox = tmp_path / "inbox"

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": "phone-exports"}, _context(data_root, inbox)
    )

    assert isinstance(settings, FolderSettings)
    # Falsity in the starting state: a wrong implementation that used the
    # raw string unresolved would produce a *relative* Path here, which
    # would fail the equality below against the absolute, resolved one.
    assert settings.source == source_dir


def test_absolute_path_is_used_as_given(tmp_path: Path) -> None:
    data_root = tmp_path / "data-root"
    data_root.mkdir()
    absolute_source = tmp_path / "elsewhere"
    absolute_source.mkdir()
    inbox = tmp_path / "inbox"

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(absolute_source)}, _context(data_root, inbox)
    )

    assert settings.source == absolute_source


def test_path_missing_is_a_settings_error_naming_the_key() -> None:
    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings({}, _context(Path("/data"), Path("/data/inbox")))
    assert excinfo.value.key == "path"


def test_non_string_path_is_a_settings_error() -> None:
    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings(
            {"path": 5}, _context(Path("/data"), Path("/data/inbox"))
        )
    assert excinfo.value.key == "path"


def test_empty_path_is_refused() -> None:
    # The inbox lies outside the data root (an absolute [inbox] path), so no
    # overlap rule can refuse "" -- only the non-empty rule can.
    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings(
            {"path": ""}, _context(Path("/data"), Path("/elsewhere/inbox"))
        )
    assert excinfo.value.key == "path"
    assert "inbox" not in str(excinfo.value)


def test_parse_settings_touches_no_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # "Resolved ... and normalized without filesystem access" (design.md):
    # neither the source nor its containment check against the inbox may
    # read the filesystem. Every stat-like Path/os entry point is wired to
    # raise -- but only when called on a path under *this test's* tmp_path,
    # so a call pytest's own machinery makes on some unrelated path (its
    # cache directory, its numbered tmp-dir cleanup, ...) is left alone and
    # cannot crash the run; only a filesystem touch on a path this test
    # actually constructed proves the violation under test. A non-existent
    # ".." component still resolves correctly because normalization here is
    # purely lexical (`os.path.normpath`).
    scope = str(tmp_path)

    def _in_scope(path_arg: object) -> bool:
        return str(path_arg).startswith(scope)

    def _patch_method(cls: type, name: str, real: Callable[..., object]) -> None:
        def _wrapper(self: Path, *args: object, **kwargs: object) -> object:
            if _in_scope(self):
                raise AssertionError(
                    f"path resolution must not touch the filesystem ({name})"
                )
            return real(self, *args, **kwargs)

        monkeypatch.setattr(cls, name, _wrapper)

    for name in ("resolve", "stat", "lstat", "exists", "is_dir", "is_file"):
        _patch_method(Path, name, getattr(Path, name))

    real_os_stat, real_os_lstat = os.stat, os.lstat

    def _os_stat_wrapper(path: object, *args: object, **kwargs: object) -> object:
        if _in_scope(path):
            raise AssertionError(
                "path resolution must not touch the filesystem (os.stat)"
            )
        return real_os_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    def _os_lstat_wrapper(path: object, *args: object, **kwargs: object) -> object:
        if _in_scope(path):
            raise AssertionError(
                "path resolution must not touch the filesystem (os.lstat)"
            )
        return real_os_lstat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "stat", _os_stat_wrapper)
    monkeypatch.setattr(os, "lstat", _os_lstat_wrapper)

    data_root = tmp_path / "data-root"  # deliberately never created
    inbox = data_root / "inbox"

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": "phone/../phone-exports"}, _context(data_root, inbox)
    )

    assert settings.source == data_root / "phone-exports"


# ---------------------------------------------------------------------------
# parse_settings: the three overlap refusals (Req 13.7)
# ---------------------------------------------------------------------------


def test_path_equal_to_the_inbox_is_refused_naming_both(tmp_path: Path) -> None:
    data_root = tmp_path
    inbox = data_root / "inbox"
    inbox.mkdir()

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings({"path": str(inbox)}, _context(data_root, inbox))

    assert excinfo.value.key == "path"
    # Both sides of "equal" are the same path here by construction, so
    # there is only one string to look for -- the prefix confound that
    # motivates `_assert_names_both_independently` for "inside"/"contains"
    # below does not apply to a single value.
    message = str(excinfo.value)
    assert str(inbox) in message


def test_path_inside_the_inbox_is_refused_naming_both(tmp_path: Path) -> None:
    data_root = tmp_path
    inbox = data_root / "inbox"
    nested = inbox / "phone"
    nested.mkdir(parents=True)

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings({"path": str(nested)}, _context(data_root, inbox))

    assert excinfo.value.key == "path"
    _assert_names_both_independently(str(excinfo.value), nested, inbox)


def test_path_containing_the_inbox_is_refused_naming_both(tmp_path: Path) -> None:
    data_root = tmp_path
    outer = data_root / "outer"
    inbox = outer / "inbox"
    inbox.mkdir(parents=True)

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings({"path": str(outer)}, _context(data_root, inbox))

    assert excinfo.value.key == "path"
    _assert_names_both_independently(str(excinfo.value), outer, inbox)


def test_path_with_dotdot_normalizing_to_equal_the_inbox_is_refused(
    tmp_path: Path,
) -> None:
    # The configured path is not lexically under the inbox, but
    # `os.path.normpath` collapses it to exactly the inbox, so only a
    # comparison of the normalized form refuses it.
    data_root = tmp_path
    inbox = data_root / "inbox"
    inbox.mkdir()
    unnormalized = f"{data_root}/decoy/../inbox"

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings({"path": unnormalized}, _context(data_root, inbox))
    assert excinfo.value.key == "path"


def test_inbox_path_with_dotdot_is_normalized_before_comparison(
    tmp_path: Path,
) -> None:
    # This time the *inbox* (context.inbox), not the configured path, is
    # given with an unnormalized ".."-bearing form; the refusal still fires
    # because the inbox side is normalized too, independently of the
    # configured-path side above.
    data_root = tmp_path
    real_inbox = data_root / "inbox"
    real_inbox.mkdir()
    unnormalized_inbox = data_root / "decoy" / ".." / "inbox"

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings(
            {"path": str(real_inbox)},
            _context(data_root, unnormalized_inbox),
        )
    assert excinfo.value.key == "path"


def test_symlink_is_not_resolved_for_the_containment_check(tmp_path: Path) -> None:
    # design.md: normalization is lexical (`os.path.normpath`), never a
    # filesystem-resolving call. A symlink whose *target* is the inbox, but
    # whose own lexical path is not, must be accepted: an implementation
    # that called `Path.resolve()` (which dereferences symlinks) would
    # instead see the real inbox path and wrongly refuse it.
    data_root = tmp_path
    inbox = data_root / "inbox"
    inbox.mkdir()
    shortcut = data_root / "shortcut"
    shortcut.symlink_to(inbox, target_is_directory=True)

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(shortcut)}, _context(data_root, inbox)
    )

    assert settings.source == Path(os.path.normpath(shortcut))


def test_unrelated_sibling_path_is_accepted(tmp_path: Path) -> None:
    # A confounding neighbor of the "contains" case: the source shares the
    # inbox's parent but does not contain it, so a broken containment check
    # (e.g. comparing only the parent directory) would wrongly refuse this.
    data_root = tmp_path
    inbox = data_root / "inbox"
    inbox.mkdir()
    sibling = data_root / "phone-exports"
    sibling.mkdir()

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(sibling)}, _context(data_root, inbox)
    )
    assert settings.source == sibling


def test_sibling_dir_whose_name_string_prefixes_the_inbox_name_is_accepted(
    tmp_path: Path,
) -> None:
    # "inbox-archive" starts with the same characters as "inbox" -- a naive
    # `str.startswith` containment check (instead of a real path-segment
    # comparison) would wrongly refuse this as "inside" or "equal".
    data_root = tmp_path
    inbox = data_root / "inbox"
    inbox.mkdir()
    archive = data_root / "inbox-archive"
    archive.mkdir()

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(archive)}, _context(data_root, inbox)
    )
    assert settings.source == archive


def test_source_whose_name_is_a_string_prefix_of_the_inbox_name_is_accepted(
    tmp_path: Path,
) -> None:
    # The reverse confound: "in" is a string prefix of "inbox" itself (not
    # the other way around); a naive prefix check on the *source* string
    # could wrongly treat it as "containing" the inbox.
    data_root = tmp_path
    inbox = data_root / "inbox"
    inbox.mkdir()
    source = data_root / "in"
    source.mkdir()

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(source)}, _context(data_root, inbox)
    )
    assert settings.source == source


# ---------------------------------------------------------------------------
# parse_settings: settle_seconds
# ---------------------------------------------------------------------------


def test_settle_seconds_default_flows_from_the_inbox_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Not a self-referential compare against the same constant the
    # production code reads: patch the inbox's default to a value that
    # exists nowhere else in this test, then confirm it -- not the
    # hardcoded 2.0 -- is what flows through when `settle_seconds` is
    # absent from the table.
    distinct_default = dataclasses.replace(DEFAULT_INBOX_SETTINGS, settle_seconds=3.25)
    monkeypatch.setattr(fitdocs_inbox, "DEFAULT_INBOX_SETTINGS", distinct_default)

    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    inbox = data_root / "inbox"

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(source)}, _context(data_root, inbox)
    )

    assert settings.settle_seconds == 3.25


def test_settle_seconds_override_is_used(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    inbox = data_root / "inbox"

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(source), "settle_seconds": 7},
        _context(data_root, inbox),
    )

    assert settings.settle_seconds == 7.0
    assert settings.settle_seconds != DEFAULT_INBOX_SETTINGS.settle_seconds


def test_settle_seconds_zero_is_accepted(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    inbox = data_root / "inbox"

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(source), "settle_seconds": 0},
        _context(data_root, inbox),
    )

    assert settings.settle_seconds == 0.0


def test_settle_seconds_bool_is_rejected(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    inbox = data_root / "inbox"

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings(
            {"path": str(source), "settle_seconds": True},
            _context(data_root, inbox),
        )
    assert excinfo.value.key == "settle_seconds"


def test_settle_seconds_negative_is_rejected(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    inbox = data_root / "inbox"

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings(
            {"path": str(source), "settle_seconds": -1},
            _context(data_root, inbox),
        )
    assert excinfo.value.key == "settle_seconds"


def test_settle_seconds_string_is_rejected(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    inbox = data_root / "inbox"

    connector = FolderConnector()
    with pytest.raises(ConnectorSettingsError) as excinfo:
        connector.parse_settings(
            {"path": str(source), "settle_seconds": "5"},
            _context(data_root, inbox),
        )
    assert excinfo.value.key == "settle_seconds"


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    inbox = data_root / "inbox"

    connector = FolderConnector()
    settings = connector.parse_settings(
        {"path": str(source), "some_unknown_key": "whatever"},
        _context(data_root, inbox),
    )
    assert settings.source == source


# ---------------------------------------------------------------------------
# list_activities: missing source
# ---------------------------------------------------------------------------


def test_missing_source_is_a_connector_error_naming_it(tmp_path: Path) -> None:
    data_root = tmp_path
    missing = data_root / "does-not-exist"
    settings = FolderSettings(source=missing, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)

    connector = FolderConnector()
    with pytest.raises(ConnectorError) as excinfo:
        connector.list_activities(session, None)
    assert str(missing) in str(excinfo.value)


def test_source_that_is_a_file_not_a_directory_is_a_connector_error(
    tmp_path: Path,
) -> None:
    data_root = tmp_path
    not_a_dir = data_root / "a-file.txt"
    data_root.mkdir(exist_ok=True)
    not_a_dir.write_text("not a directory")
    settings = FolderSettings(source=not_a_dir, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)

    connector = FolderConnector()
    with pytest.raises(ConnectorError):
        connector.list_activities(session, None)


# ---------------------------------------------------------------------------
# list_activities: selection rules reused from the inbox
# ---------------------------------------------------------------------------


def test_dot_prefixed_and_junk_files_are_not_listed(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    (source / "real.fit").write_bytes(b"fit-bytes")
    (source / ".hidden.fit").write_bytes(b"fit-bytes")
    dotdir = source / ".synced"
    dotdir.mkdir()
    (dotdir / "inner.fit").write_bytes(b"fit-bytes")
    (source / "not-a-fit-file.txt").write_bytes(b"ignore me")
    (source / "trash.fit.tmp").write_bytes(b"junk")

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)

    connector = FolderConnector()
    listing = connector.list_activities(session, None)

    remote_ids = {activity.remote_id for activity in listing.activities}
    assert remote_ids == {"real.fit"}


def test_listed_file_uses_source_relative_path_and_basename(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    nested = source / "2026" / "09"
    nested.mkdir(parents=True)
    (nested / "workout.FIT").write_bytes(b"fit-bytes")

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)

    connector = FolderConnector()
    listing = connector.list_activities(session, None)

    assert len(listing.activities) == 1
    activity = listing.activities[0]
    assert activity.remote_id == "2026/09/workout.FIT"
    assert activity.suggested_name == "workout.FIT"
    assert activity.original_available is True
    assert activity.start is None
    assert activity.sport is None
    assert activity.duration_s is None
    assert activity.revision is not None


def test_revision_changes_when_size_changes_with_mtime_held_constant(
    tmp_path: Path,
) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(b"short")

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    first_revision = connector.list_activities(session, None).activities[0].revision
    before_ns = target.stat().st_mtime_ns

    target.write_bytes(b"a much longer payload than before")
    os.utime(target, ns=(before_ns, before_ns))

    assert target.stat().st_mtime_ns == before_ns  # falsity check: mtime held
    second_revision = connector.list_activities(session, None).activities[0].revision

    assert first_revision != second_revision


def test_revision_changes_when_mtime_changes_with_size_held_constant(
    tmp_path: Path,
) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(b"fixed-size-content")

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    first_revision = connector.list_activities(session, None).activities[0].revision
    size_before = target.stat().st_size

    later = target.stat().st_mtime + 5
    os.utime(target, (later, later))  # content, and so size, untouched

    assert target.stat().st_size == size_before  # falsity check: size did not move
    second_revision = connector.list_activities(session, None).activities[0].revision

    assert first_revision != second_revision


def test_since_is_ignored(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    (source / "old.fit").write_bytes(b"fit-bytes")

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    far_future = datetime(2999, 1, 1, tzinfo=UTC)
    listing = connector.list_activities(session, far_future)

    assert len(listing.activities) == 1


# ---------------------------------------------------------------------------
# list_activities: settle interval and deferrals
# ---------------------------------------------------------------------------


def test_file_changing_across_the_settle_interval_is_deferred(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "growing.fit"
    target.write_bytes(b"start")

    sleep_calls: list[float] = []

    def _growing_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        # Grow the file during the settle wait -- the injected sleep is the
        # only place this connector could observe the passage of time, so a
        # settle implementation that never calls it, or ignores its second
        # observation, would list this file as stable instead.
        target.write_bytes(b"start-plus-more-bytes")

    settings = FolderSettings(source=source, settle_seconds=1.5)
    session = _session(settings, data_root=data_root, sleep=_growing_sleep)
    connector = FolderConnector()

    listing = connector.list_activities(session, None)

    assert sleep_calls == [1.5]
    assert listing.activities == ()
    assert len(listing.deferred) == 1
    deferral = listing.deferred[0]
    assert deferral.subject == "growing.fit"
    # The reason must carry the inbox's own detail (why it deferred), not
    # merely repeat the subject under a different field name.
    assert deferral.reason != deferral.subject
    assert "size changed while settling" in deferral.reason


def test_stable_file_across_the_settle_interval_is_listed(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    (source / "stable.fit").write_bytes(b"unchanged")

    sleep_calls: list[float] = []

    def _noop_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    settings = FolderSettings(source=source, settle_seconds=1.5)
    session = _session(settings, data_root=data_root, sleep=_noop_sleep)
    connector = FolderConnector()

    listing = connector.list_activities(session, None)

    assert sleep_calls == [1.5]
    assert len(listing.activities) == 1
    assert listing.deferred == ()


def test_a_stat_failure_after_settling_stable_is_deferred_not_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Distinct from the settle-interval deferral above: this pins the
    # revision-computing `stat` design.md calls out separately ("a failing
    # `stat` -> deferral"), which runs only *after* `inbox.settle` has
    # already called the file stable. Rather than counting how many times
    # the stdlib happens to call `Path.stat` internally (fragile across
    # Python versions -- `Path.is_file()` calls `stat()` on 3.11 but not on
    # 3.14), this wraps `inbox.settle` itself: the real `settle` runs
    # first and unaffected, and only once it has returned does `Path.stat`
    # start failing for the target file, isolating the connector's own
    # extra stat as the only one that can fail.
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "flaky.fit"
    target.write_bytes(b"contents")

    real_settle = fitdocs_inbox.settle
    real_stat = Path.stat

    def _settle_then_break_stat(
        *args: object, **kwargs: object
    ) -> fitdocs_inbox.SettleResult:
        result = real_settle(*args, **kwargs)  # type: ignore[arg-type]

        def _failing_stat(
            self: Path, *, follow_symlinks: bool = True
        ) -> os.stat_result:
            if self == target:
                raise OSError("simulated stat failure after settle")
            return real_stat(self, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(Path, "stat", _failing_stat)
        return result

    monkeypatch.setattr(fitdocs_inbox, "settle", _settle_then_break_stat)

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    listing = connector.list_activities(session, None)

    # Falsity in the starting state: the file is real and readable, so an
    # implementation that skipped the extra stat entirely would list it.
    assert listing.activities == ()
    assert len(listing.deferred) == 1
    assert listing.deferred[0].subject == "flaky.fit"


# ---------------------------------------------------------------------------
# fetch_activity
# ---------------------------------------------------------------------------


def test_fetch_returns_bytes_when_revision_matches(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(b"the-real-bytes")
    info = target.stat()
    revision = f"{info.st_size}:{info.st_mtime_ns}"

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    activity = RemoteActivity(
        remote_id="a.fit", original_available=True, revision=revision
    )
    result = connector.fetch_activity(session, activity)

    assert isinstance(result, Fetched)
    assert result.data == b"the-real-bytes"


def test_fetch_defers_when_revision_changed_during_read(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(b"original")

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    # A revision that does not match what is on disk now, standing in for
    # "changed since the listing observed it" without needing to race an
    # actual concurrent writer.
    stale_activity = RemoteActivity(
        remote_id="a.fit", original_available=True, revision="0:0"
    )
    result = connector.fetch_activity(session, stale_activity)

    assert isinstance(result, Deferred)
    assert "changed" in result.reason


def test_fetch_defers_when_the_post_read_stat_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Distinct from the two deferrals above: the read itself succeeds, and
    # the file's on-disk revision still matches -- only the second `stat`
    # call design.md requires (the one that would detect the file changing
    # while being read) itself raises. An implementation that dropped that
    # `try`/`except` around the post-read `stat` would let the OSError
    # escape instead of deferring.
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(b"contents")
    info = target.stat()
    revision = f"{info.st_size}:{info.st_mtime_ns}"

    real_stat = Path.stat

    def _failing_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == target:
            raise OSError("simulated post-read stat failure")
        return real_stat(self, follow_symlinks=follow_symlinks)

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    activity = RemoteActivity(
        remote_id="a.fit", original_available=True, revision=revision
    )

    # `read_bytes()` does not call `stat()` (it opens and reads directly),
    # so patching only `Path.stat` leaves the read itself untouched.
    assert target.read_bytes() == b"contents"
    monkeypatch.setattr(Path, "stat", _failing_stat)

    result = connector.fetch_activity(session, activity)

    assert isinstance(result, Deferred)
    assert "changed" in result.reason


def test_fetch_defers_an_unreadable_file(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()
    target = source / "a.fit"
    target.write_bytes(b"contents")
    target.chmod(0)
    try:
        settings = FolderSettings(source=source, settle_seconds=0.0)
        session = _session(settings, data_root=data_root)
        connector = FolderConnector()

        activity = RemoteActivity(
            remote_id="a.fit", original_available=True, revision="irrelevant"
        )
        result = connector.fetch_activity(session, activity)

        assert isinstance(result, Deferred)
        assert "could not be read" in result.reason
    finally:
        target.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_fetch_defers_a_vanished_file(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    source.mkdir()

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    activity = RemoteActivity(
        remote_id="never-existed.fit", original_available=True, revision="0:0"
    )
    result = connector.fetch_activity(session, activity)

    assert isinstance(result, Deferred)
    assert "could not be read" in result.reason


# ---------------------------------------------------------------------------
# Reads only: the source tree's snapshot is unchanged before/after listing
# and fetching (Req 13.5)
# ---------------------------------------------------------------------------


def test_source_tree_snapshot_unchanged_by_listing_and_fetching(tmp_path: Path) -> None:
    data_root = tmp_path
    source = data_root / "src"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (source / "one.fit").write_bytes(b"one-bytes")
    (nested / "two.fit").write_bytes(b"two-bytes")

    before = _tree_snapshot(source)
    assert before  # the walk actually saw files

    settings = FolderSettings(source=source, settle_seconds=0.0)
    session = _session(settings, data_root=data_root)
    connector = FolderConnector()

    listing = connector.list_activities(session, None)
    for activity in listing.activities:
        result = connector.fetch_activity(session, activity)
        assert isinstance(result, Fetched)

    after = _tree_snapshot(source)
    assert after == before


# ---------------------------------------------------------------------------
# Registration: FolderConnector is the built-in connector (Req 2.1)
# ---------------------------------------------------------------------------


def test_get_folder_returns_the_folder_connector_after_import() -> None:
    # tests.connectors.conftest's registry-snapshot fixture already
    # triggered `import fitdocs.connectors` (transitively, via the module
    # under test) before this test body runs -- this is not a fresh
    # interpreter (see test_get_folder_connector_in_a_fresh_interpreter
    # above for that), but the registration line runs exactly once, at
    # that first import, and every test in this run shares its effect.
    import fitdocs.connectors as connectors_package

    connector = connectors_package.get("folder")
    assert isinstance(connector, FolderConnector)
    assert "FolderConnector" not in connectors_package.__all__
