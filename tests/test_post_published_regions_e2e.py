"""The ``post`` and ``published`` regions on every workout page (publish-core
2.3; Req 3.1, 12.1, 13.2, 13.5, 13.6, 13.7), driven through the installed CLI.

A page written at the previous document-format version has neither region.
``regen`` brings it current: both regions appear in their fresh form, and the
``notes`` and ``load`` regions and the user-owned ``publish`` key are kept
byte-for-byte. Regenerating again changes nothing. Hand-written content in
either region is carried through a rewrite.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.docmerge import extract_regions
from tests.fixtures import builder
from tests.test_determinism import _no_socket
from tests.test_effort_tags_e2e import (
    _add_frontmatter_key,
    _doc,
    _offline_tiles,
    _put,
    _set_region,
)

__all__ = ["_offline_tiles"]  # the autouse fixture must be visible in this module

runner = CliRunner()

_POST_FRESH = (
    "<!-- post: to give this page its own post, write the title on one line, "
    "then a blank line, then the description. Left empty, the template is used. -->"
)
_NOTE = "Hand-written note."
_LOAD = "Hand-written load."
_PUBLISH_LINE = "publish:   [ strava ]   # opted in\n"


def _strip_region(text: str, region_id: str) -> str:
    pattern = re.compile(
        rf"<!-- fitdocs:begin:{region_id} -->.*?<!-- fitdocs:end:{region_id} -->\n\n?",
        re.DOTALL,
    )
    stripped, count = pattern.subn("", text)
    assert count == 1
    return stripped


def test_a_previous_version_page_gains_both_regions_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    _put(source, "run.fit", builder.run_fit_bytes())

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert result.exit_code == 0, result.output
        doc = _doc(data_root, "run")
        fresh = doc.read_text(encoding="utf-8")
        assert extract_regions(fresh)["published"] == ""
        assert extract_regions(fresh)["post"] == _POST_FRESH

        aged = _strip_region(_strip_region(fresh, "post"), "published")
        assert "\ndoc_version: 12\n" in aged
        aged = aged.replace("\ndoc_version: 12\n", "\ndoc_version: 11\n", 1)
        aged = _add_frontmatter_key(aged, _PUBLISH_LINE)
        aged = _set_region(aged, "notes", _NOTE)
        aged = _set_region(aged, "load", _LOAD)
        # The starting state lacks both regions and the new version.
        assert set(extract_regions(aged)) == {"notes", "morning", "load"}
        doc.write_text(aged, encoding="utf-8")

        result = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert result.exit_code == 0, result.output
        first = doc.read_text(encoding="utf-8")
        regions = extract_regions(first)
        assert regions["published"] == ""
        assert regions["post"] == _POST_FRESH
        assert regions["notes"] == _NOTE
        assert regions["load"] == _LOAD
        assert _PUBLISH_LINE in first
        assert "\ndoc_version: 12\n" in first

        result = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert result.exit_code == 0, result.output
        assert doc.read_bytes() == first.encode("utf-8")


def test_hand_written_post_and_published_content_is_carried_through_regen(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    _put(source, "run.fit", builder.run_fit_bytes())
    post = "Title line\n\nThe description."
    published = "[A](https://example.test/a)"

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert result.exit_code == 0, result.output
        doc = _doc(data_root, "run")
        edited = _set_region(
            _set_region(doc.read_text(encoding="utf-8"), "post", post),
            "published",
            published,
        )
        doc.write_text(edited, encoding="utf-8")

        result = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert result.exit_code == 0, result.output
        regions = extract_regions(doc.read_text(encoding="utf-8"))
        assert regions["post"] == post
        assert regions["published"] == published
