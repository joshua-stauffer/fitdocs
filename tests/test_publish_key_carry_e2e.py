"""The ``publish`` frontmatter key is user-owned (publish-core 2.2; Req 2.1, 2.2,
2.8, 13.3, 13.7), driven through the installed CLI the way
``tests/test_effort_tags_e2e.py`` drives the effort tag.

A hand-added ``publish`` entry -- a multi-line list with odd spacing and
comments, a malformed value, or a one-line value with a quote style and a
trailing comment -- is carried byte-for-byte through plain ``sync`` (when a
file joins the page), ``sync --force``, ``regen`` and the load pass, and is
never named by the unmanaged-key warning or by ``check``. Each fixture is one a
YAML re-dump would rewrite (indentation, spacing, quoting, comments), so a
carry that re-serialises the value fails it. Before the real runs, a
preliminary control run on the same page, carrying an unknown key
(``bogus_key``), shows that the regen warning and ``check`` do name an
unmanaged key in this harness. The ``publish`` presence checks are scoped to
the frontmatter block, so a body that mentions publishing does not move them.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from fitdocs.cli import app
from fitdocs.contract import frontmatter_close_index, parse_frontmatter
from fitdocs.docmerge import extract_regions
from tests.fixtures import builder
from tests.test_determinism import _no_socket
from tests.test_effort_tags_e2e import (
    _STUB_CALCULATOR_ID,
    _add_frontmatter_key,
    _doc,
    _forced_stub_calculator,
    _offline_tiles,
    _put,
    _set_region,
    _warnings_count,
)

__all__ = ["_offline_tiles"]  # the autouse fixture must be visible in this module

runner = CliRunner()


def _frontmatter_publish_lines(text: str) -> int:
    """Lines inside the frontmatter block whose key is ``publish``."""
    lines = text.split("\n")
    close = frontmatter_close_index(lines)
    assert close is not None, "the page has no frontmatter block"
    return sum(1 for line in lines[1:close] if line.startswith("publish"))


_LIST_VALUE = (
    "publish:\n"
    "  -   strava   # the second one\n"
    "\n"
    "  # a comment between items\n"
    "  - 'intervals'\n"
    "    \n"
    '  - "a b"\n'
)
_MALFORMED_VALUE = "publish:   [ strava ,3 ,  {a: 1} ]   # not names\n"
_INLINE_VALUE = "publish: 'strava'   # one target\n"
_CONTROL = "bogus_key: 1\n"
_NOTE = "Hand-written note."


@pytest.mark.parametrize(
    "publish_lines",
    [_LIST_VALUE, _MALFORMED_VALUE, _INLINE_VALUE],
    ids=["multi-line-list", "malformed", "one-line"],
)
def test_publish_lines_are_carried_byte_for_byte_and_never_reported(
    tmp_path: Path, publish_lines: str
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
        assert "publish" not in (parse_frontmatter(fresh) or {"publish": 0})
        assert _frontmatter_publish_lines(fresh) == 0  # never written

        # Control: an unmanaged key IS named by the regen warning and by check,
        # so the later "publish is not named" assertions can fail.
        doc.write_text(_add_frontmatter_key(fresh, _CONTROL), encoding="utf-8")
        control_regen = runner.invoke(app, ["regen", "--out", str(data_root)])
        assert control_regen.exit_code == 0, control_regen.output
        assert _warnings_count(control_regen.output) == 1
        assert "bogus_key" in control_regen.output
        doc.write_text(_add_frontmatter_key(fresh, _CONTROL), encoding="utf-8")
        control_check = runner.invoke(app, ["check", "--out", str(data_root)])
        assert control_check.exit_code == 1
        assert "bogus_key" in control_check.output

        edited = _add_frontmatter_key(fresh, publish_lines)
        edited = _set_region(edited, "notes", _NOTE)
        doc.write_text(edited, encoding="utf-8")
        assert publish_lines in doc.read_text(encoding="utf-8")

        for args in (
            ["sync", str(source), "--out", str(data_root), "--force"],
            ["regen", "--out", str(data_root)],
        ):
            result = runner.invoke(app, args)
            assert result.exit_code == 0, result.output
            # No warning of any kind was produced.
            assert _warnings_count(result.output) == 0, result.output
            assert "publish" not in result.output
            rewritten = doc.read_text(encoding="utf-8")
            assert publish_lines in rewritten
            assert _frontmatter_publish_lines(rewritten) == 1
            assert extract_regions(rewritten)["notes"] == _NOTE

            check_result = runner.invoke(app, ["check", "--out", str(data_root)])
            assert check_result.exit_code == 0, check_result.output
            assert "publish" not in check_result.output

        before_load = doc.read_text(encoding="utf-8")
        assert "load_value:" not in before_load
        with _forced_stub_calculator():
            load_result = runner.invoke(
                app,
                ["load", "--out", str(data_root), "--calculator", _STUB_CALCULATOR_ID],
            )
        assert load_result.exit_code == 0, load_result.output
        after_load = doc.read_text(encoding="utf-8")
        assert "load_value:" in after_load
        assert publish_lines in after_load
        assert "publish" not in load_result.output

        check_result = runner.invoke(app, ["check", "--out", str(data_root)])
        assert check_result.exit_code == 0, check_result.output
        assert "publish" not in check_result.output


def test_plain_sync_carries_publish_when_a_file_joins_the_page(
    tmp_path: Path,
) -> None:
    """Plain ``sync`` (no ``--force``) rewrites the page because a second file
    joins it, and the hand-added ``publish`` lines survive that rewrite."""
    from tests.fixtures.merge import ride_pair_fit_bytes

    garmin, healthfit = ride_pair_fit_bytes()
    data_root = tmp_path / "data"
    data_root.mkdir()
    first, second = tmp_path / "first", tmp_path / "second"
    _put(first, "garmin.fit", garmin)
    _put(second, "healthfit.fit", healthfit)

    with mock.patch("socket.socket", _no_socket):
        result = runner.invoke(app, ["sync", str(first), "--out", str(data_root)])
        assert result.exit_code == 0, result.output
        doc = _doc(data_root, "")
        fresh = doc.read_text(encoding="utf-8")
        edited = _set_region(_add_frontmatter_key(fresh, _LIST_VALUE), "notes", _NOTE)
        doc.write_text(edited, encoding="utf-8")

        result = runner.invoke(app, ["sync", str(second), "--out", str(data_root)])
        assert result.exit_code == 0, result.output
        after = doc.read_text(encoding="utf-8")
        assert after != edited  # the page really was rewritten
        assert _LIST_VALUE in after
        assert _frontmatter_publish_lines(after) == 1
        assert extract_regions(after)["notes"] == _NOTE
        assert _warnings_count(result.output) == 0, result.output
        assert "publish" not in result.output

        check_result = runner.invoke(app, ["check", "--out", str(data_root)])
        assert check_result.exit_code == 0, check_result.output
