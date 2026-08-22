"""Tests for the ``[inbox]`` settings reader, inbox path preparation, candidate
selection, the stability check, and the disposition policy.

Req 1.1-1.7, 3.4, 4.4, 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 8.5.

These exercise several slices of ``src/fitdocs/inbox.py``:

* :func:`fitdocs.inbox.load_inbox_settings`, the strictly read-only, typed
  projection of the already-parsed settings document's ``[inbox]`` table onto
  :class:`~fitdocs.inbox.InboxSettings` (design: "InboxSettings +
  ``load_inbox_settings``").
* :func:`fitdocs.inbox.prepare_inbox`, which turns a validated
  :class:`~fitdocs.inbox.InboxSettings` into usable, existing directories --
  the only filesystem writes this module performs (design: "InboxPaths +
  ``prepare_inbox``").
* :func:`fitdocs.inbox.move_processed`, the opt-in move disposition (design:
  "Disposition"): subpath-preserving, collision-safe, and never a source of
  deletion -- a failed move returns an :class:`~fitdocs.inbox.InboxNote`
  rather than raising. Leave-in-place (:attr:`~fitdocs.inbox.Disposition.LEAVE`)
  is a no-op *by construction* -- there is no function to call for it, so no
  code path in this module can touch, move, or delete a file under it. What
  is directly asserted here is narrower: :class:`~fitdocs.inbox.Disposition`
  has exactly two members, ``leave`` and ``move``, so a delete (or any third)
  disposition is unrepresentable in the type system, not merely undocumented
  (Req 6.6).

Two invariants govern every ``load_inbox_settings`` case, mirroring the
established ``[tiles]`` table-reader contract:

* *Absent is the default, never an error.* No settings file (an empty
  mapping) -- or a document with no ``[inbox]`` table -- yields
  :data:`~fitdocs.inbox.DEFAULT_INBOX_SETTINGS`. Each key defaults
  independently, so a partial ``[inbox]`` table fills only the keys it names,
  and unknown keys (inside ``[inbox]`` or at the top level) are ignored.
* *Malformed fails loudly.* Every validation failure raises
  :class:`~fitdocs.inbox.InboxSettingsError`, naming the settings file and the
  offending key. File-level faults -- an unreadable file, invalid TOML --
  are never this module's concern: they are raised by the shared settings
  reader as :class:`~fitdocs.settings.SettingsError` before this module ever
  sees a mapping.

``load_inbox_settings`` reads no file: it is a pure function of the mapping
and the data root it is handed. ``prepare_inbox``, by contrast, does touch
the filesystem: it resolves the inbox and (under the move disposition) the
processed-files destination, creates whichever is missing and lies inside
the data root (Req 1.5, 6.7), and raises :class:`~fitdocs.inbox.InboxSettingsError`
naming the offending path otherwise (Req 1.6, 6.7) -- validating both paths
before creating either, so a refusal leaves the filesystem untouched.
"""

from __future__ import annotations

import inspect
import os
import re
import time
from pathlib import Path

import pytest

from fitdocs.inbox import (
    DEFAULT_IGNORE_PATTERNS,
    DEFAULT_INBOX_SETTINGS,
    Candidate,
    Disposition,
    InboxNote,
    InboxPaths,
    InboxSettings,
    InboxSettingsError,
    SettleResult,
    _ignore_patterns,
    _matches_any_ignore_pattern,
    load_inbox_settings,
    move_processed,
    prepare_inbox,
    select_candidates,
    settle,
)
from fitdocs.settings import SettingsError, load_settings_document

# --- helpers ------------------------------------------------------------


def _write_settings(data_root: Path, content: str) -> Path:
    """Write ``<data_root>/fitdocs.toml`` with *content* and return its path."""
    path = data_root / "fitdocs.toml"
    path.write_text(content)
    return path


# --- The default (Req 1.2) ------------------------------------------------


def test_default_inbox_settings_is_leave_in_place_with_no_ignores() -> None:
    """The all-defaults value: default inbox dir, 2s settle, leave, no ignores."""
    expected = InboxSettings(
        path="inbox",
        settle_seconds=2.0,
        ignore=(),
        disposition=Disposition.LEAVE,
        processed_dir=None,
    )
    assert expected == DEFAULT_INBOX_SETTINGS


# --- Absent file / table -> defaults (never an error) (Req 1.2) -----------


def test_absent_file_returns_defaults(tmp_path: Path) -> None:
    """An empty mapping (settings file absent) -> the documented defaults."""
    assert load_inbox_settings({}, data_root=tmp_path) == DEFAULT_INBOX_SETTINGS


def test_absent_inbox_table_returns_defaults(tmp_path: Path) -> None:
    """A parsed document with no ``[inbox]`` table -> defaults; other tables ignored."""
    path = _write_settings(
        tmp_path,
        """
        [some_other_feature]
        setting = "value"
        """,
    )
    document = load_settings_document(tmp_path)
    assert path.exists()
    assert load_inbox_settings(document, data_root=tmp_path) == DEFAULT_INBOX_SETTINGS


def test_empty_inbox_table_returns_defaults(tmp_path: Path) -> None:
    """A present but empty ``[inbox]`` table -> defaults."""
    _write_settings(tmp_path, "[inbox]\n")
    document = load_settings_document(tmp_path)
    assert load_inbox_settings(document, data_root=tmp_path) == DEFAULT_INBOX_SETTINGS


# --- Each key overrides independently (Req 1.3) ----------------------------


def test_path_override_only(tmp_path: Path) -> None:
    document = {"inbox": {"path": "drop-zone"}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.path == "drop-zone"
    assert result.settle_seconds == DEFAULT_INBOX_SETTINGS.settle_seconds
    assert result.ignore == DEFAULT_INBOX_SETTINGS.ignore
    assert result.disposition == DEFAULT_INBOX_SETTINGS.disposition
    assert result.processed_dir == DEFAULT_INBOX_SETTINGS.processed_dir


def test_settle_seconds_override_only(tmp_path: Path) -> None:
    document = {"inbox": {"settle_seconds": 5}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.settle_seconds == 5.0
    assert result.path == DEFAULT_INBOX_SETTINGS.path
    assert result.ignore == DEFAULT_INBOX_SETTINGS.ignore
    assert result.disposition == DEFAULT_INBOX_SETTINGS.disposition


def test_settle_seconds_zero_is_accepted(tmp_path: Path) -> None:
    """A settle_seconds of zero is valid -- it disables the wait (Req 4.4)."""
    document = {"inbox": {"settle_seconds": 0}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.settle_seconds == 0.0


def test_settle_seconds_float_override(tmp_path: Path) -> None:
    document = {"inbox": {"settle_seconds": 1.5}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.settle_seconds == 1.5


def test_ignore_override_only(tmp_path: Path) -> None:
    document = {"inbox": {"ignore": ["staging/*", "*.bak"]}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.ignore == ("staging/*", "*.bak")
    assert result.path == DEFAULT_INBOX_SETTINGS.path
    assert result.settle_seconds == DEFAULT_INBOX_SETTINGS.settle_seconds
    assert result.disposition == DEFAULT_INBOX_SETTINGS.disposition


def test_disposition_move_override_with_processed_dir(tmp_path: Path) -> None:
    document = {
        "inbox": {"disposition": "move", "processed_dir": "processed"},
    }
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.disposition == Disposition.MOVE
    assert result.processed_dir == "processed"
    assert result.path == DEFAULT_INBOX_SETTINGS.path
    assert result.settle_seconds == DEFAULT_INBOX_SETTINGS.settle_seconds
    assert result.ignore == DEFAULT_INBOX_SETTINGS.ignore


def test_explicit_leave_disposition_without_processed_dir(tmp_path: Path) -> None:
    """Explicitly naming "leave" needs no ``processed_dir`` (it is optional then)."""
    document = {"inbox": {"disposition": "leave"}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.disposition == Disposition.LEAVE
    assert result.processed_dir is None


def test_full_override_maps_every_key(tmp_path: Path) -> None:
    document = {
        "inbox": {
            "path": "/absolute/drop-zone",
            "settle_seconds": 10,
            "ignore": ["*.tmp2"],
            "disposition": "move",
            "processed_dir": "/absolute/processed",
        }
    }
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result == InboxSettings(
        path="/absolute/drop-zone",
        settle_seconds=10.0,
        ignore=("*.tmp2",),
        disposition=Disposition.MOVE,
        processed_dir="/absolute/processed",
    )


# --- Unknown-key tolerance (Req 1.3) ----------------------------------------


def test_unknown_keys_within_inbox_are_ignored(tmp_path: Path) -> None:
    document = {"inbox": {"path": "drop-zone", "made_up_key": "whatever"}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.path == "drop-zone"


def test_unknown_top_level_table_is_ignored(tmp_path: Path) -> None:
    document = {"plugins": {"enabled": True}, "inbox": {"path": "drop-zone"}}
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.path == "drop-zone"


# --- Reading writes nothing --------------------------------------------------


def test_reading_writes_nothing(tmp_path: Path) -> None:
    before = set(tmp_path.rglob("*"))
    load_inbox_settings({"inbox": {"path": "drop-zone"}}, data_root=tmp_path)
    assert set(tmp_path.rglob("*")) == before


# --- Validation failures (Req 1.4) ------------------------------------------


def test_non_table_inbox_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*\[inbox\]"):
        load_inbox_settings({"inbox": "not-a-table"}, data_root=Path("/data"))


def test_non_string_path_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*path"):
        load_inbox_settings({"inbox": {"path": 123}}, data_root=Path("/data"))


def test_empty_path_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*path"):
        load_inbox_settings({"inbox": {"path": ""}}, data_root=Path("/data"))


def test_non_string_processed_dir_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*processed_dir"):
        load_inbox_settings(
            {"inbox": {"disposition": "move", "processed_dir": 42}},
            data_root=Path("/data"),
        )


def test_empty_processed_dir_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*processed_dir"):
        load_inbox_settings(
            {"inbox": {"disposition": "move", "processed_dir": ""}},
            data_root=Path("/data"),
        )


def test_negative_settle_seconds_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*settle_seconds"):
        load_inbox_settings({"inbox": {"settle_seconds": -1}}, data_root=Path("/data"))


def test_boolean_settle_seconds_raises() -> None:
    """A ``bool`` is explicitly rejected: ``bool`` subclasses ``int`` in Python."""
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*settle_seconds"):
        load_inbox_settings(
            {"inbox": {"settle_seconds": True}}, data_root=Path("/data")
        )


def test_string_settle_seconds_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*settle_seconds"):
        load_inbox_settings({"inbox": {"settle_seconds": "5"}}, data_root=Path("/data"))


def test_non_list_ignore_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*ignore"):
        load_inbox_settings({"inbox": {"ignore": "*.tmp"}}, data_root=Path("/data"))


def test_ignore_with_non_string_item_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*ignore"):
        load_inbox_settings(
            {"inbox": {"ignore": ["*.tmp", 7]}}, data_root=Path("/data")
        )


def test_ignore_with_empty_string_item_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*ignore"):
        load_inbox_settings(
            {"inbox": {"ignore": ["*.tmp", ""]}}, data_root=Path("/data")
        )


def test_unknown_disposition_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*disposition"):
        load_inbox_settings(
            {"inbox": {"disposition": "delete"}}, data_root=Path("/data")
        )


def test_move_disposition_without_processed_dir_raises() -> None:
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*disposition"):
        load_inbox_settings({"inbox": {"disposition": "move"}}, data_root=Path("/data"))


def test_processed_dir_equal_to_inbox_raises(tmp_path: Path) -> None:
    document = {
        "inbox": {
            "path": "inbox",
            "disposition": "move",
            "processed_dir": "inbox",
        }
    }
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*processed_dir"):
        load_inbox_settings(document, data_root=tmp_path)


def test_processed_dir_nested_inside_inbox_raises(tmp_path: Path) -> None:
    document = {
        "inbox": {
            "path": "inbox",
            "disposition": "move",
            "processed_dir": "inbox/processed",
        }
    }
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*processed_dir"):
        load_inbox_settings(document, data_root=tmp_path)


def test_processed_dir_nested_inside_absolute_inbox_raises(tmp_path: Path) -> None:
    """The containment check applies to absolute inbox/processed paths too."""
    inbox = tmp_path / "inbox"
    document = {
        "inbox": {
            "path": str(inbox),
            "disposition": "move",
            "processed_dir": str(inbox / "processed"),
        }
    }
    with pytest.raises(InboxSettingsError, match=r"fitdocs\.toml.*processed_dir"):
        load_inbox_settings(document, data_root=tmp_path)


def test_processed_dir_sibling_of_inbox_is_accepted(tmp_path: Path) -> None:
    """A processed dir that merely shares a prefix with the inbox name is fine."""
    document = {
        "inbox": {
            "path": "inbox",
            "disposition": "move",
            "processed_dir": "inbox-processed",
        }
    }
    result = load_inbox_settings(document, data_root=tmp_path)
    assert result.processed_dir == "inbox-processed"


# --- File-level faults surface as SettingsError, never InboxSettingsError (Req 1.7) --


def test_unreadable_settings_file_raises_shared_settings_error_not_inbox_error(
    tmp_path: Path,
) -> None:
    """Invalid TOML raises the shared file-level error, never ``InboxSettingsError``.

    ``load_inbox_settings`` never opens the settings file itself; the shared
    reader (`fitdocs.settings.load_settings_document`) is the only place a
    file-level fault can be raised, and it must not be ``InboxSettingsError``.
    """
    _write_settings(tmp_path, "not valid toml [[[")

    with pytest.raises(SettingsError) as excinfo:
        load_settings_document(tmp_path)

    assert not isinstance(excinfo.value, InboxSettingsError)


def test_load_inbox_settings_never_reads_the_settings_file(tmp_path: Path) -> None:
    """``load_inbox_settings`` is a pure projection: an invalid file on disk is
    irrelevant because the function is never handed a path, only a mapping."""
    _write_settings(tmp_path, "not valid toml [[[")

    # No SettingsError/InboxSettingsError -- the malformed file on disk is
    # simply never touched by this function.
    result = load_inbox_settings({}, data_root=tmp_path)
    assert result == DEFAULT_INBOX_SETTINGS


# --- prepare_inbox: resolution and creation (Req 1.1, 1.5, 1.6, 6.7, 8.5) ---
#
# Exercises :func:`fitdocs.inbox.prepare_inbox`, which turns validated
# :class:`~fitdocs.inbox.InboxSettings` into usable directories -- or refuses
# loudly before anything is processed (design: "InboxPaths + `prepare_inbox`").


def _settings(
    *,
    path: str,
    disposition: Disposition = Disposition.LEAVE,
    processed_dir: str | None = None,
) -> InboxSettings:
    return InboxSettings(
        path=path,
        settle_seconds=DEFAULT_INBOX_SETTINGS.settle_seconds,
        ignore=DEFAULT_INBOX_SETTINGS.ignore,
        disposition=disposition,
        processed_dir=processed_dir,
    )


def test_relative_inbox_resolves_against_data_root(tmp_path: Path) -> None:
    """A relative ``path`` resolves against the data root (Req 1.1)."""
    settings = _settings(path="drop-zone")
    result = prepare_inbox(tmp_path, settings)
    assert result.inbox == tmp_path / "drop-zone"
    assert result.processed is None


def test_absolute_inbox_used_as_given(tmp_path: Path) -> None:
    """An absolute ``path`` is used as given, even outside the data root, as
    long as it already exists (Req 1.1, 1.6)."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside-inbox"
    outside.mkdir()
    try:
        settings = _settings(path=str(outside))
        result = prepare_inbox(tmp_path, settings)
        assert result.inbox == outside
    finally:
        outside.rmdir()


def test_missing_inside_root_inbox_is_created(tmp_path: Path) -> None:
    """A missing inbox that resolves inside the data root is created (Req 1.5)."""
    settings = _settings(path="drop-zone")
    target = tmp_path / "drop-zone"
    assert not target.exists()
    result = prepare_inbox(tmp_path, settings)
    assert result.inbox == target
    assert target.is_dir()


def test_missing_inside_root_inbox_with_missing_parents_is_created(
    tmp_path: Path,
) -> None:
    """Parents are created too (Req 1.5)."""
    settings = _settings(path="a/b/drop-zone")
    target = tmp_path / "a" / "b" / "drop-zone"
    result = prepare_inbox(tmp_path, settings)
    assert result.inbox == target
    assert target.is_dir()


def test_missing_inside_root_processed_dir_is_created_under_move(
    tmp_path: Path,
) -> None:
    """A missing processed_dir inside the data root is created under the move
    disposition (Req 1.5, 6.7)."""
    (tmp_path / "inbox").mkdir()
    settings = _settings(
        path="inbox", disposition=Disposition.MOVE, processed_dir="processed"
    )
    target = tmp_path / "processed"
    assert not target.exists()
    result = prepare_inbox(tmp_path, settings)
    assert result.processed == target
    assert target.is_dir()


def test_missing_outside_root_inbox_raises_naming_the_path(tmp_path: Path) -> None:
    """A missing inbox outside the data root raises, naming the path (Req 1.6)."""
    outside = tmp_path.parent / f"{tmp_path.name}-missing-outside-inbox"
    assert not outside.exists()
    settings = _settings(path=str(outside))
    with pytest.raises(InboxSettingsError, match=re.escape(str(outside))):
        prepare_inbox(tmp_path, settings)


def test_missing_outside_root_processed_dir_raises_naming_the_path(
    tmp_path: Path,
) -> None:
    """A missing processed_dir outside the data root raises, naming the path
    (Req 1.6, 6.7)."""
    (tmp_path / "inbox").mkdir()
    outside = tmp_path.parent / f"{tmp_path.name}-missing-outside-processed"
    assert not outside.exists()
    settings = _settings(
        path="inbox", disposition=Disposition.MOVE, processed_dir=str(outside)
    )
    with pytest.raises(InboxSettingsError, match=re.escape(str(outside))):
        prepare_inbox(tmp_path, settings)


def test_outside_root_path_that_is_not_a_directory_raises(tmp_path: Path) -> None:
    """An outside-the-root path that exists but is a file raises (Req 1.6)."""
    outside = tmp_path.parent / f"{tmp_path.name}-outside-file"
    outside.write_text("not a directory")
    try:
        settings = _settings(path=str(outside))
        with pytest.raises(InboxSettingsError, match=re.escape(str(outside))):
            prepare_inbox(tmp_path, settings)
    finally:
        outside.unlink()


def test_inside_root_path_that_is_not_a_directory_raises(tmp_path: Path) -> None:
    """An inside-the-root path that exists but is a file raises regardless of
    location (design: "An inbox that exists but is not a directory is an
    error regardless of location")."""
    (tmp_path / "drop-zone").write_text("not a directory")
    settings = _settings(path="drop-zone")
    with pytest.raises(InboxSettingsError, match="drop-zone"):
        prepare_inbox(tmp_path, settings)


def test_refusal_creates_nothing(tmp_path: Path) -> None:
    """A valid inbox plus an invalid outside-the-root destination refuses
    before creating either -- the inbox is *not* created just because it was
    validated first (Req 1.5, 1.6, 6.7)."""
    outside = tmp_path.parent / f"{tmp_path.name}-refusal-outside-processed"
    assert not outside.exists()
    settings = _settings(
        path="drop-zone", disposition=Disposition.MOVE, processed_dir=str(outside)
    )
    inbox_target = tmp_path / "drop-zone"
    assert not inbox_target.exists()

    with pytest.raises(InboxSettingsError, match=re.escape(str(outside))):
        prepare_inbox(tmp_path, settings)

    assert not inbox_target.exists()
    assert not outside.exists()


def test_leave_in_place_never_prepares_a_processed_dir(tmp_path: Path) -> None:
    """The processed_dir is only prepared when the move disposition is active
    (design: "InboxPaths + `prepare_inbox`"); leave-in-place creates nothing
    beyond the inbox itself."""
    settings = _settings(path="drop-zone")
    result = prepare_inbox(tmp_path, settings)
    assert result.processed is None
    assert list(tmp_path.iterdir()) == [tmp_path / "drop-zone"]


def test_prepare_inbox_returns_inbox_paths(tmp_path: Path) -> None:
    (tmp_path / "inbox").mkdir()
    (tmp_path / "processed").mkdir()
    settings = _settings(
        path="inbox", disposition=Disposition.MOVE, processed_dir="processed"
    )
    result = prepare_inbox(tmp_path, settings)
    assert isinstance(result, InboxPaths)
    assert result.inbox == tmp_path / "inbox"
    assert result.processed == tmp_path / "processed"


# --- CandidateSelector: select_candidates (Req 3.1-3.5) ---------------------
#
# Exercises :func:`fitdocs.inbox.select_candidates` (design: "CandidateSelector"):
# deterministic ``.fit`` discovery over an already-resolved inbox directory,
# with the dot-component rule, the default junk-name patterns, and additive
# user-configured patterns all applied as *exclusions* -- ignored files never
# appear in the returned tuple, which is the only place a caller could observe
# them (Req 3.5).


def _write(path: Path, content: str = "fit-bytes") -> Path:
    """Write *content* to *path*, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_default_ignore_patterns_are_exactly_the_documented_set() -> None:
    """The documented default junk-name patterns (Req 3.3, design's exact set)."""
    assert DEFAULT_IGNORE_PATTERNS == ("*.tmp", "*.part", ".syncthing.*", ".DS_Store")


def test_nested_discovery_order_is_deterministic_by_inbox_relative_path(
    tmp_path: Path,
) -> None:
    """Candidates are sorted by inbox-relative path, nested included (Req 3.1)."""
    inbox = tmp_path
    _write(inbox / "b.fit")
    _write(inbox / "a.fit")
    _write(inbox / "sub" / "c.fit")
    _write(inbox / "sub" / "aa" / "d.fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert [c.rel for c in result] == [
        "a.fit",
        "b.fit",
        "sub/aa/d.fit",
        "sub/c.fit",
    ]
    assert all(isinstance(c, Candidate) for c in result)


def test_candidate_rel_is_inbox_relative_posix_path(tmp_path: Path) -> None:
    """``rel`` is the inbox-relative label every report entry uses (Req 3.1)."""
    inbox = tmp_path
    target = _write(inbox / "sub" / "run.fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert len(result) == 1
    assert result[0].path == target
    assert result[0].rel == "sub/run.fit"


def test_uppercase_extension_is_a_candidate(tmp_path: Path) -> None:
    """The ``.fit`` extension match is case-insensitive (Req 3.1)."""
    inbox = tmp_path
    _write(inbox / "RUN.FIT")
    _write(inbox / "walk.Fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert {c.rel for c in result} == {"RUN.FIT", "walk.Fit"}


def test_directory_named_dot_fit_is_not_a_candidate(tmp_path: Path) -> None:
    """A directory whose name ends in ``.fit`` is not a regular file (Req 3.1)."""
    inbox = tmp_path
    (inbox / "looks-like-a-file.fit").mkdir()
    _write(inbox / "real.fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert [c.rel for c in result] == ["real.fit"]


def test_non_fit_extension_is_not_a_candidate(tmp_path: Path) -> None:
    inbox = tmp_path
    _write(inbox / "notes.txt")
    _write(inbox / "real.fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert [c.rel for c in result] == ["real.fit"]


def test_hidden_companion_file_is_excluded(tmp_path: Path) -> None:
    """AppleDouble ``._*`` companions are dot-prefixed basenames (Req 3.2)."""
    inbox = tmp_path
    _write(inbox / "._run.fit")
    _write(inbox / "run.fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert [c.rel for c in result] == ["run.fit"]


def test_hidden_subdirectory_excludes_everything_beneath_it(tmp_path: Path) -> None:
    """A dot-prefixed directory component excludes the whole subtree, including
    nested non-hidden-looking files (Req 3.2)."""
    inbox = tmp_path
    _write(inbox / ".stversions" / "run.fit")
    _write(inbox / "sub" / ".AppleDouble" / "run.fit")
    _write(inbox / "sub" / "real.fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert [c.rel for c in result] == ["sub/real.fit"]


def test_dot_prefixed_top_level_file_is_excluded(tmp_path: Path) -> None:
    inbox = tmp_path
    _write(inbox / ".hidden.fit")
    _write(inbox / "visible.fit")

    result = select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    assert [c.rel for c in result] == ["visible.fit"]


# Every default pattern is unreachable through a real ``.fit`` candidate: a
# name ending in ``.tmp``/``.part`` cannot also end in ``.fit`` (the extension
# predicate excludes it before pattern matching ever runs), and
# ``.syncthing.*``/``.DS_Store`` are themselves dot-prefixed, so the
# dot-component rule (Req 3.2) already excludes them independently. Each
# default's *matching semantics* is therefore pinned directly against
# :func:`fitdocs.inbox._matches_any_ignore_pattern` -- proving the pattern
# itself, not the unreachable end-to-end walk -- one match case and one
# non-match case per pattern, so a mutation to any single pattern is caught.


def test_default_pattern_tmp_matches_and_does_not_overmatch() -> None:
    lowered = tuple(pattern.lower() for pattern in DEFAULT_IGNORE_PATTERNS)
    assert _matches_any_ignore_pattern("partial.tmp", "partial.tmp", lowered) is True
    assert _matches_any_ignore_pattern("keep.fit", "keep.fit", lowered) is False


def test_default_pattern_part_matches_and_does_not_overmatch() -> None:
    lowered = tuple(pattern.lower() for pattern in DEFAULT_IGNORE_PATTERNS)
    assert _matches_any_ignore_pattern("partial.part", "partial.part", lowered) is True
    assert _matches_any_ignore_pattern("keep.fit", "keep.fit", lowered) is False


def test_default_pattern_syncthing_matches_and_does_not_overmatch() -> None:
    lowered = tuple(pattern.lower() for pattern in DEFAULT_IGNORE_PATTERNS)
    assert (
        _matches_any_ignore_pattern(".syncthing.abc", ".syncthing.abc", lowered) is True
    )
    assert _matches_any_ignore_pattern("keep.fit", "keep.fit", lowered) is False


def test_default_pattern_ds_store_matches_and_does_not_overmatch() -> None:
    lowered = tuple(pattern.lower() for pattern in DEFAULT_IGNORE_PATTERNS)
    assert _matches_any_ignore_pattern(".DS_Store", ".DS_Store", lowered) is True
    assert _matches_any_ignore_pattern("keep.fit", "keep.fit", lowered) is False


def test_ignore_patterns_composition_is_additive_not_replacing() -> None:
    """``_ignore_patterns`` composes the defaults *plus* configured entries --
    never the configured set replacing the defaults (Req 3.4). This is the
    mutation-sensitive check for additivity: a composition that returned
    ``settings.ignore`` alone whenever it is non-empty (silently dropping the
    defaults) fails this assertion, even though every default pattern is
    otherwise unreachable through a real inbox walk (see note above)."""
    settings = InboxSettings(
        path=DEFAULT_INBOX_SETTINGS.path,
        settle_seconds=DEFAULT_INBOX_SETTINGS.settle_seconds,
        ignore=("staging/*", "*.bak"),
        disposition=DEFAULT_INBOX_SETTINGS.disposition,
        processed_dir=DEFAULT_INBOX_SETTINGS.processed_dir,
    )

    patterns = _ignore_patterns(settings)

    for default in DEFAULT_IGNORE_PATTERNS:
        assert default in patterns
    for configured in settings.ignore:
        assert configured in patterns


def test_ignore_patterns_with_no_configured_entries_is_exactly_the_defaults() -> None:
    patterns = _ignore_patterns(DEFAULT_INBOX_SETTINGS)
    assert patterns == DEFAULT_IGNORE_PATTERNS


def test_configured_ignore_pattern_applies_alongside_the_default_set(
    tmp_path: Path,
) -> None:
    """An end-to-end proof that a configured pattern excludes a candidate
    while the drain still ran with the full (default + configured) pattern
    set composed by :func:`fitdocs.inbox._ignore_patterns` (Req 3.4)."""
    inbox = tmp_path
    _write(inbox / "staging" / "run.fit")
    keep = _write(inbox / "keep.fit")
    settings = InboxSettings(
        path=DEFAULT_INBOX_SETTINGS.path,
        settle_seconds=DEFAULT_INBOX_SETTINGS.settle_seconds,
        ignore=("staging/*",),
        disposition=DEFAULT_INBOX_SETTINGS.disposition,
        processed_dir=DEFAULT_INBOX_SETTINGS.processed_dir,
    )

    result = select_candidates(inbox, settings)

    assert [c.path for c in result] == [keep]


def test_configured_ignore_pattern_matches_basename(tmp_path: Path) -> None:
    inbox = tmp_path
    _write(inbox / "sub" / "excludeme.fit")
    _write(inbox / "keep.fit")
    settings = InboxSettings(
        path=DEFAULT_INBOX_SETTINGS.path,
        settle_seconds=DEFAULT_INBOX_SETTINGS.settle_seconds,
        ignore=("excludeme.fit",),
        disposition=DEFAULT_INBOX_SETTINGS.disposition,
        processed_dir=DEFAULT_INBOX_SETTINGS.processed_dir,
    )

    result = select_candidates(inbox, settings)

    assert [c.rel for c in result] == ["keep.fit"]


def test_configured_ignore_pattern_matches_relative_path(tmp_path: Path) -> None:
    """A pattern like ``staging/*`` matches the inbox-relative path, letting a
    user exclude a whole subtree by relative path rather than basename alone
    (Req 3.4)."""
    inbox = tmp_path
    _write(inbox / "staging" / "run.fit")
    _write(inbox / "other" / "run.fit")
    settings = InboxSettings(
        path=DEFAULT_INBOX_SETTINGS.path,
        settle_seconds=DEFAULT_INBOX_SETTINGS.settle_seconds,
        ignore=("staging/*",),
        disposition=DEFAULT_INBOX_SETTINGS.disposition,
        processed_dir=DEFAULT_INBOX_SETTINGS.processed_dir,
    )

    result = select_candidates(inbox, settings)

    assert [c.rel for c in result] == ["other/run.fit"]


def test_pattern_matching_is_case_normalized(tmp_path: Path) -> None:
    """A configured pattern matches regardless of the case of either the
    pattern or the path on disk, so behavior is identical on case-sensitive
    and case-insensitive filesystems (Req 3.3, 3.4)."""
    inbox = tmp_path
    excluded = _write(inbox / "STAGING" / "RUN.fit")
    kept = _write(inbox / "keep.fit")
    settings = InboxSettings(
        path=DEFAULT_INBOX_SETTINGS.path,
        settle_seconds=DEFAULT_INBOX_SETTINGS.settle_seconds,
        # Mixed-case pattern against a mixed-case directory on disk.
        ignore=("Staging/*",),
        disposition=DEFAULT_INBOX_SETTINGS.disposition,
        processed_dir=DEFAULT_INBOX_SETTINGS.processed_dir,
    )

    result = select_candidates(inbox, settings)

    assert [c.path for c in result] == [kept]
    assert excluded not in [c.path for c in result]


def test_ignored_files_are_absent_from_selection_entirely(tmp_path: Path) -> None:
    """Ignored files never reach the returned tuple -- the only channel
    selection has -- covering dot-prefixed files, a dot-prefixed hidden
    subdirectory, and a configured pattern together (Req 3.5). (Default
    junk-name patterns are proven separately against
    :func:`fitdocs.inbox._matches_any_ignore_pattern`, since none of them is
    reachable through a real ``.fit`` candidate -- see the note above.)"""
    inbox = tmp_path
    _write(inbox / ".hidden.fit")
    _write(inbox / "._companion.fit")
    _write(inbox / ".stversions" / "run.fit")
    _write(inbox / "excluded-by-config.fit")
    kept = _write(inbox / "keep.fit")
    settings = InboxSettings(
        path=DEFAULT_INBOX_SETTINGS.path,
        settle_seconds=DEFAULT_INBOX_SETTINGS.settle_seconds,
        ignore=("excluded-by-config.fit",),
        disposition=DEFAULT_INBOX_SETTINGS.disposition,
        processed_dir=DEFAULT_INBOX_SETTINGS.processed_dir,
    )

    result = select_candidates(inbox, settings)

    assert [c.path for c in result] == [kept]


def test_selection_reads_but_does_not_write_the_inbox(tmp_path: Path) -> None:
    """Selection only reads the inbox -- no candidate is created, moved, or
    deleted (design: "the inbox is only read")."""
    inbox = tmp_path
    _write(inbox / "run.fit")
    before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in inbox.rglob("*")}

    select_candidates(inbox, DEFAULT_INBOX_SETTINGS)

    after = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in inbox.rglob("*")}
    assert before == after


# --- StabilityCheck: settle (Req 4.1-4.5) ------------------------------------
#
# Exercises :func:`fitdocs.inbox.settle` (design: "StabilityCheck"): the
# batched, stateless, two-observation stability protocol -- observe every
# candidate, sleep at most once for the whole batch, observe every candidate
# again, and partition the input into ``stable`` and ``deferred`` (each an
# :class:`~fitdocs.inbox.InboxNote` naming the file and the reason).


class _RecordingSleep:
    """A sleep stub that records every call instead of blocking (design:
    "the wait is performed through an injected `sleep` callable so tests
    never spend real time")."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _candidate(path: Path, inbox: Path) -> Candidate:
    return Candidate(path=path, rel=path.relative_to(inbox).as_posix())


def test_unchanged_candidate_is_stable(tmp_path: Path) -> None:
    """Identical size and mtime across both observations -> stable (Req 4.1)."""
    inbox = tmp_path
    target = _write(inbox / "run.fit")
    candidate = _candidate(target, inbox)
    sleep = _RecordingSleep()

    result = settle([candidate], settle_seconds=2.0, sleep=sleep)

    assert result.stable == (candidate,)
    assert result.deferred == ()


def test_size_changed_between_observations_is_deferred(tmp_path: Path) -> None:
    """A candidate whose size changes between observations is deferred, named,
    with a human-readable reason (Req 4.2) -- with the modification time
    forced back to its original value, isolating the size comparison from
    the mtime comparison (a mutant that compares mtime only must fail this)."""
    import os as _os

    inbox = tmp_path
    target = _write(inbox / "run.fit", content="short")
    candidate = _candidate(target, inbox)
    original_mtime_ns = target.stat().st_mtime_ns

    def growing_sleep(seconds: float) -> None:
        atime_ns = target.stat().st_atime_ns
        target.write_text("this content is much longer than before")
        _os.utime(target, ns=(atime_ns, original_mtime_ns))

    result = settle([candidate], settle_seconds=2.0, sleep=growing_sleep)

    assert target.stat().st_mtime_ns == original_mtime_ns  # mtime genuinely unchanged
    assert result.stable == ()
    assert len(result.deferred) == 1
    note = result.deferred[0]
    assert isinstance(note, InboxNote)
    assert note.subject == candidate.rel
    assert note.detail  # human-readable, non-empty


def test_mtime_changed_between_observations_is_deferred(tmp_path: Path) -> None:
    """A same-size candidate whose mtime changes between observations is
    deferred (Req 4.2) -- proves mtime is compared independently of size."""
    inbox = tmp_path
    target = _write(inbox / "run.fit", content="fixed-size")
    candidate = _candidate(target, inbox)
    original_mtime = target.stat().st_mtime_ns

    def touch_sleep(seconds: float) -> None:
        new_mtime = original_mtime + 10_000_000_000  # +10s in ns, same size
        os_stat_result = target.stat()
        import os as _os

        _os.utime(target, ns=(os_stat_result.st_atime_ns, new_mtime))

    result = settle([candidate], settle_seconds=2.0, sleep=touch_sleep)

    assert target.stat().st_size == len("fixed-size")  # size genuinely unchanged
    assert result.stable == ()
    assert len(result.deferred) == 1
    assert result.deferred[0].subject == candidate.rel
    assert candidate.rel in result.deferred[0].detail


def test_vanished_candidate_is_deferred_not_stable_or_error(tmp_path: Path) -> None:
    """A candidate that disappears between the two observations is deferred,
    never raises, and is never treated as stable (Req 4.2)."""
    inbox = tmp_path
    target = _write(inbox / "run.fit")
    candidate = _candidate(target, inbox)

    def vanish_sleep(seconds: float) -> None:
        target.unlink()

    result = settle([candidate], settle_seconds=2.0, sleep=vanish_sleep)

    assert result.stable == ()
    assert len(result.deferred) == 1
    assert result.deferred[0].subject == candidate.rel
    assert candidate.rel in result.deferred[0].detail


def test_deferred_file_is_left_completely_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deferred file's bytes are never read/opened by :func:`settle` -- only
    ``stat`` is used (design: "no candidate is opened or read"). Every
    content-reading API on :class:`~pathlib.Path` is patched to explode, so a
    call to any of them fails the test rather than silently succeeding."""
    inbox = tmp_path
    target = _write(inbox / "run.fit", content="original")
    candidate = _candidate(target, inbox)

    def _boom(self: Path, *args: object, **kwargs: object) -> None:
        raise AssertionError(f"settle opened a candidate via {self}")

    monkeypatch.setattr(Path, "open", _boom)
    monkeypatch.setattr(Path, "read_bytes", _boom)
    monkeypatch.setattr(Path, "read_text", _boom)

    def growing_sleep(seconds: float) -> None:
        # Mutate via os-level calls only, never through a patched Path API.
        with open(target, "a") as fh:  # noqa: PTH123 -- deliberately bypasses Path.open patch target
            fh.write("-plus-more")

    result = settle([candidate], settle_seconds=2.0, sleep=growing_sleep)

    assert result.stable == ()
    assert len(result.deferred) == 1


def test_zero_settle_interval_performs_no_sleep_and_admits_all(tmp_path: Path) -> None:
    """``settle_seconds == 0`` disables the wait entirely: zero sleep calls and
    every stat-able candidate is stable, in input order (Req 4.4)."""
    inbox = tmp_path
    a = _candidate(_write(inbox / "a.fit"), inbox)
    b = _candidate(_write(inbox / "b.fit"), inbox)
    sleep = _RecordingSleep()

    result = settle([a, b], settle_seconds=0.0, sleep=sleep)

    assert sleep.calls == []
    assert result.stable == (a, b)
    assert result.deferred == ()


def test_exactly_one_sleep_call_for_a_batch_of_many_candidates(tmp_path: Path) -> None:
    """The settle wait costs exactly one interval per drain, regardless of
    candidate count -- the most distinctive property of the design (Req 4.5).
    The stable partition is asserted in input order (design: "both ordered as
    the input")."""
    inbox = tmp_path
    candidates = [_candidate(_write(inbox / f"f{i}.fit"), inbox) for i in range(25)]
    sleep = _RecordingSleep()

    result = settle(candidates, settle_seconds=2.0, sleep=sleep)

    assert sleep.calls == [2.0]
    assert result.stable == tuple(candidates)
    assert result.deferred == ()


def test_fractional_settle_seconds_still_waits_and_is_honored(tmp_path: Path) -> None:
    """A legal fractional ``settle_seconds`` (design.md: ``float``, ``>= 0``;
    Req 4.4) still performs the wait and the stability check -- a guard
    against a mutant like ``if settle_seconds < 1`` that would silently treat
    a sub-second interval as disabled."""
    inbox = tmp_path
    target = _write(inbox / "run.fit", content="short")
    candidate = _candidate(target, inbox)
    sleep = _RecordingSleep()

    def growing_sleep(seconds: float) -> None:
        sleep(seconds)
        target.write_text("now much longer than before, definitely a size change")

    result = settle([candidate], settle_seconds=0.5, sleep=growing_sleep)

    assert sleep.calls == [0.5]
    assert result.stable == ()
    assert len(result.deferred) == 1
    assert result.deferred[0].subject == candidate.rel


def test_zero_interval_unobservable_candidate_is_deferred(tmp_path: Path) -> None:
    """Under the zero-interval bypass, a candidate that cannot be stat'd at
    all is deferred, not silently admitted -- pinning "admits every candidate
    that can be observed" (design.md:481) rather than every candidate
    unconditionally (Req 4.2, 4.4)."""
    inbox = tmp_path
    missing = _candidate(inbox / "gone.fit", inbox)  # never created

    result = settle([missing], settle_seconds=0.0)

    assert result.stable == ()
    assert len(result.deferred) == 1
    assert result.deferred[0].subject == missing.rel


def test_settle_result_is_dataclass_with_stable_and_deferred_fields() -> None:
    result = SettleResult(stable=(), deferred=())
    assert result.stable == ()
    assert result.deferred == ()


def test_mixed_batch_partitions_stable_and_deferred(tmp_path: Path) -> None:
    """A batch containing both a stable and a changing candidate partitions
    correctly, both parts ordered as the input (design: "stable and deferred
    partition the input, both ordered as the input")."""
    inbox = tmp_path
    stable_candidate = _candidate(_write(inbox / "stable.fit"), inbox)
    changing_target = _write(inbox / "changing.fit", content="short")
    changing_candidate = _candidate(changing_target, inbox)

    def mutate_one_sleep(seconds: float) -> None:
        changing_target.write_text("now much longer than the original content")

    result = settle(
        [stable_candidate, changing_candidate],
        settle_seconds=2.0,
        sleep=mutate_one_sleep,
    )

    assert result.stable == (stable_candidate,)
    assert len(result.deferred) == 1
    assert result.deferred[0].subject == changing_candidate.rel


def test_deferred_ordering_matches_input_order_with_two_deferrals(
    tmp_path: Path,
) -> None:
    """With two deferring candidates and one stable candidate, ``deferred`` is
    ordered exactly as the input was -- not reversed, not sorted (design.md:
    "both ordered as the input"), pinning ordering on ``deferred`` (the
    single-deferral tests above only pin ``stable``'s ordering)."""
    inbox = tmp_path
    changing_a_target = _write(inbox / "a-changing.fit", content="short")
    changing_a = _candidate(changing_a_target, inbox)
    stable = _candidate(_write(inbox / "b-stable.fit"), inbox)
    changing_c_target = _write(inbox / "c-changing.fit", content="short")
    changing_c = _candidate(changing_c_target, inbox)

    def mutate_two_sleep(seconds: float) -> None:
        changing_a_target.write_text("now much longer than the original content")
        changing_c_target.write_text("also now much longer than the original")

    result = settle(
        [changing_a, stable, changing_c],
        settle_seconds=2.0,
        sleep=mutate_two_sleep,
    )

    assert result.stable == (stable,)
    assert [note.subject for note in result.deferred] == [
        changing_a.rel,
        changing_c.rel,
    ]


def test_settle_is_stateless_across_calls(tmp_path: Path) -> None:
    """No deferral state persists: re-observing the same (now stable) file in a
    fresh call succeeds cleanly (Req 4.3)."""
    inbox = tmp_path
    target = _write(inbox / "run.fit", content="short")
    candidate = _candidate(target, inbox)

    def growing_sleep(seconds: float) -> None:
        target.write_text("now much longer than before")

    first = settle([candidate], settle_seconds=2.0, sleep=growing_sleep)
    assert first.stable == ()
    assert len(first.deferred) == 1

    # A fresh call over the now-stable file admits it, with nothing carried over.
    second = settle([candidate], settle_seconds=2.0, sleep=_RecordingSleep())
    assert second.stable == (candidate,)
    assert second.deferred == ()


def test_inbox_note_has_exactly_subject_and_detail_fields() -> None:
    """`InboxNote` has exactly two fields -- no optional remedy field (design:
    "This spec adds no `remedy` field")."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(InboxNote)}
    assert field_names == {"subject", "detail"}


def test_default_settle_sleep_parameter_is_time_sleep() -> None:
    """The default ``sleep`` parameter is ``time.sleep`` itself (design's
    Service Interface signature: ``sleep: Callable[[float], None] =
    time.sleep``) -- pinned directly on the function signature so a default
    of any other no-op callable is caught, without spending wall-clock time
    actually invoking it. (The default is bound once at function-definition
    time, so it cannot be exercised end-to-end via a post-import monkeypatch
    of ``time.sleep``; the signature check is the faithful assertion.)"""
    signature = inspect.signature(settle)
    assert signature.parameters["sleep"].default is time.sleep


# --- Disposition: move_processed (design: "Disposition", Req 6.1-6.6) ------
#
# Exercises :func:`fitdocs.inbox.move_processed`, the opt-in move
# disposition: subpath preservation with parent creation, collision-safe
# naming that escalates deterministically and never overwrites, and a
# failure that returns an :class:`~fitdocs.inbox.InboxNote` rather than
# raising, leaving the source file exactly where it was. Whether a file is
# *eligible* to move (archive presence, never failed/deferred/quarantined)
# is a later task's concern (drain orchestration); these tests hand
# :func:`move_processed` files already assumed eligible, matching the
# component's boundary.


SHA_A = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef01234567"
SHA_B = "1122334455667788112233445566778811223344556677881122334455667"


def test_disposition_has_exactly_two_members_deletion_unrepresentable() -> None:
    """:class:`Disposition` has exactly the two members ``leave`` and
    ``move`` -- this is what is asserted here -- so a delete disposition
    cannot be expressed in the type system, not merely left undocumented
    (Req 6.6).

    Not asserted by this test, but true by inspection: leave-in-place is a
    no-op by construction, since there is no function in this module a
    caller invokes to apply :attr:`Disposition.LEAVE`. The never-delete
    guarantee's real, end-to-end assertion is the preserved-guarantee test
    Req 8.4 requires (a later task)."""
    assert {member.value for member in Disposition} == {"leave", "move"}
    assert len(list(Disposition)) == 2


def test_move_preserves_subpath_and_creates_parent_directories(tmp_path: Path) -> None:
    """A candidate nested under an inbox subdirectory lands at the same
    relative subpath beneath ``processed_dir``, with every missing parent
    directory created on demand (Req 6.2)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    source = _write(inbox / "2024" / "07" / "run.fit", content="workout-bytes")
    candidate = _candidate(source, inbox)

    result = move_processed(candidate, processed, SHA_A)

    expected_destination = processed / "2024" / "07" / "run.fit"
    assert result == str(expected_destination)
    assert expected_destination.read_text() == "workout-bytes"
    assert not source.exists()


def test_move_collision_produces_distinct_content_derived_name_both_intact(
    tmp_path: Path,
) -> None:
    """When the destination path already exists, the moved file is stored
    under a distinct, content-derived name instead of overwriting: the
    pre-existing file's content is unchanged and the newly moved file is
    also present under its own name (Req 6.3)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    existing = _write(processed / "run.fit", content="pre-existing-content")
    source = _write(inbox / "run.fit", content="new-content")
    candidate = _candidate(source, inbox)

    result = move_processed(candidate, processed, SHA_A)

    expected_destination = processed / f"run-{SHA_A[:8]}.fit"
    assert result == str(expected_destination)
    assert expected_destination.read_text() == "new-content"
    # The pre-existing file at the primary name is untouched.
    assert existing.read_text() == "pre-existing-content"
    assert not source.exists()


def test_move_repeated_collisions_escalate_deterministically(tmp_path: Path) -> None:
    """When both the primary name and the first content-derived name are
    already taken, the moved file escalates to ``-2``, and both
    pre-existing files survive untouched (Req 6.3)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    primary = _write(processed / "run.fit", content="primary-content")
    first_hashed = _write(
        processed / f"run-{SHA_A[:8]}.fit", content="first-hashed-content"
    )
    source = _write(inbox / "run.fit", content="new-content")
    candidate = _candidate(source, inbox)

    result = move_processed(candidate, processed, SHA_A)

    expected_destination = processed / f"run-{SHA_A[:8]}-2.fit"
    assert result == str(expected_destination)
    assert expected_destination.read_text() == "new-content"
    assert primary.read_text() == "primary-content"
    assert first_hashed.read_text() == "first-hashed-content"
    assert not source.exists()


def test_move_repeated_collision_escalation_is_deterministic_across_calls(
    tmp_path: Path,
) -> None:
    """The same collision state and the same content hash always escalate to
    the same resulting name -- run twice, independently, against identical
    pre-existing collisions, both moves land on the identical ``-2`` name
    (Req 6.3)."""

    def _run_once(root: Path) -> str | InboxNote:
        inbox = root / "inbox"
        processed = root / "processed"
        processed.mkdir(parents=True)
        _write(processed / "run.fit", content="primary-content")
        _write(processed / f"run-{SHA_A[:8]}.fit", content="first-hashed-content")
        source = _write(inbox / "run.fit", content="new-content")
        candidate = _candidate(source, inbox)
        return move_processed(candidate, processed, SHA_A)

    first_result = _run_once(tmp_path / "first")
    second_result = _run_once(tmp_path / "second")

    assert isinstance(first_result, str)
    assert isinstance(second_result, str)
    assert Path(first_result).name == Path(second_result).name
    assert first_result.endswith(f"run-{SHA_A[:8]}-2.fit")


def test_move_three_way_collision_escalates_to_dash_three(tmp_path: Path) -> None:
    """A third occupant at the ``-2`` name escalates once more, to ``-3``,
    confirming the escalation sequence beyond the first step (Req 6.3)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    _write(processed / "run.fit", content="primary-content")
    _write(processed / f"run-{SHA_A[:8]}.fit", content="first-hashed-content")
    _write(processed / f"run-{SHA_A[:8]}-2.fit", content="second-hashed-content")
    source = _write(inbox / "run.fit", content="new-content")
    candidate = _candidate(source, inbox)

    result = move_processed(candidate, processed, SHA_A)

    expected_destination = processed / f"run-{SHA_A[:8]}-3.fit"
    assert result == str(expected_destination)
    assert expected_destination.read_text() == "new-content"
    assert not source.exists()


def test_move_different_content_hash_uses_its_own_collision_name(
    tmp_path: Path,
) -> None:
    """A collision is escalated using *this candidate's* content hash, not a
    fixed suffix -- two different files colliding on the same primary name
    land on two different, non-overwriting destinations (Req 6.3)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    _write(processed / "run.fit", content="primary-content")
    source = _write(inbox / "run.fit", content="new-content")
    candidate = _candidate(source, inbox)

    result = move_processed(candidate, processed, SHA_B)

    expected_destination = processed / f"run-{SHA_B[:8]}.fit"
    assert result == str(expected_destination)
    assert expected_destination.read_text() == "new-content"


def test_move_uncreatable_parent_returns_note_not_raise(tmp_path: Path) -> None:
    """When a candidate's subpath requires a parent directory that cannot be
    created (a plain file already occupies that name), the move fails and
    returns an :class:`InboxNote` describing the failure instead of raising
    -- and the source file is left exactly where it was (Req 6.5)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    # "blocked" exists as a plain file, so mkdir(parents=True) for
    # processed/blocked/run.fit cannot succeed.
    _write(processed / "blocked", content="i am a file, not a directory")
    source = _write(inbox / "blocked" / "run.fit", content="workout-bytes")
    candidate = _candidate(source, inbox)

    result = move_processed(candidate, processed, SHA_A)

    assert isinstance(result, InboxNote)
    assert result.subject == candidate.rel
    assert result.detail  # a human-readable reason is present
    # The already-completed processing stands; the source is untouched.
    assert source.exists()
    assert source.read_text() == "workout-bytes"


def test_move_unwritable_destination_returns_note_not_raise(tmp_path: Path) -> None:
    """A destination directory that exists but denies write permission is
    the literal "unwritable destination" the task's Observable bullet and
    design.md name -- distinct from an uncreatable parent (a name collision
    with a plain file) covered above. The move fails and returns an
    :class:`InboxNote` instead of raising, and the source is left exactly
    where it was, unchanged (Req 6.5)."""
    if os.geteuid() == 0:
        pytest.skip("permission bits have no effect when running as root")

    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    source = _write(inbox / "run.fit", content="workout-bytes")
    candidate = _candidate(source, inbox)

    os.chmod(processed, 0o500)  # read + execute only: cannot create a file here
    try:
        result = move_processed(candidate, processed, SHA_A)
    finally:
        os.chmod(processed, 0o700)  # restore so tmp_path cleanup can proceed

    assert isinstance(result, InboxNote)
    assert result.subject == candidate.rel
    assert result.detail
    assert source.exists()
    assert source.read_text() == "workout-bytes"


def test_move_vanished_source_returns_note_not_raise(tmp_path: Path) -> None:
    """If the source file no longer exists by the time the move is attempted
    (e.g. removed out-of-band between processing and disposition), the move
    fails and returns an :class:`InboxNote` rather than raising -- there is
    nothing left to leave in place, but no exception propagates and no other
    file is touched (Req 6.5)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    vanished_path = inbox / "run.fit"
    candidate = Candidate(path=vanished_path, rel="run.fit")

    result = move_processed(candidate, processed, SHA_A)

    assert isinstance(result, InboxNote)
    assert result.subject == "run.fit"
    assert result.detail
    assert not (processed / "run.fit").exists()


def test_move_uses_shutil_move_not_a_bare_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The move goes through :func:`shutil.move`, which falls back to
    copy-then-unlink across filesystems, rather than a bare ``os.rename``
    (or ``Path.rename``), which raises ``EXDEV`` when the inbox lives on a
    different volume than the data root -- the common iCloud/Dropbox case
    (design's Technology Stack: "Cross-device safe... via shutil.move").
    This is pinned by observing that :func:`fitdocs.inbox.shutil.move` is
    actually invoked with the expected source and destination, since a
    same-filesystem tmp_path cannot itself distinguish the two mechanisms
    by observed behavior alone."""
    import fitdocs.inbox as inbox_module

    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    source = _write(inbox / "run.fit", content="workout-bytes")
    candidate = _candidate(source, inbox)

    calls: list[tuple[str, str]] = []
    real_move = inbox_module.shutil.move

    def recording_move(src: str, dst: str) -> str:
        calls.append((src, dst))
        return real_move(src, dst)

    monkeypatch.setattr(inbox_module.shutil, "move", recording_move)

    result = move_processed(candidate, processed, SHA_A)

    expected_destination = processed / "run.fit"
    assert result == str(expected_destination)
    assert calls == [(str(source), str(expected_destination))]


def test_move_success_returns_destination_as_string(tmp_path: Path) -> None:
    """A successful move returns the destination path as a plain string
    (design's Service Interface: ``-> str | InboxNote``), distinct in type
    from the :class:`InboxNote` failure case, so callers can branch on
    ``isinstance`` (Req 6.2)."""
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    processed.mkdir()
    source = _write(inbox / "run.fit", content="workout-bytes")
    candidate = _candidate(source, inbox)

    result = move_processed(candidate, processed, SHA_A)

    assert isinstance(result, str)
    assert not isinstance(result, InboxNote)
