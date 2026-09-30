"""End-to-end running-dynamics pins through the installed CLI (tasks 4.2, 5.2).

The 4.2 tests that sync use only the synthesized Stryd fixture, synced into a
temporary data root through :class:`typer.testing.CliRunner` with the tile
fetch seam patched offline and an explicit ``--out``, as
``tests/test_effort_tags_e2e.py`` does; this module also removes
``FITDOCS_DATA`` and runs from a temporary cwd. The developer-field test
renders the decoded Stryd fixture directly, without the CLI. Their
expectations come from the fixture builder's constants and from the fixture
decoded independently of the page; their literals are the labels the page
prints, the absent tokens (``104%``, ``Humidity``, ...) and the humidity value
104 the fixture records.

The 5.2 test syncs the native-dynamics fixture the same way, then edits the
synced page text to age it, runs ``check`` and ``regen``, and compares the
regenerated page to the hand edits (``_NOTE``, ``_EFFORT_TAG``) and to
``contract.DOC_VERSION``. Its literals are those two constants, the
``modality: run`` and ``doc_version:`` frontmatter lines, the section heading,
and the ``check`` output strings ``doc_version is N, below the current`` and
``No findings``; the chart asset path it looks up is read from the page's own
image link.

Covers requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.4, 9.2 and 9.3.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC
from pathlib import Path
from statistics import mean
from types import MappingProxyType

import pytest
from typer.testing import CliRunner

from fitdocs import contract
from fitdocs.cli import app
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import begin_marker, end_marker, extract_regions
from fitdocs.ingest import parse_fit
from fitdocs.ingest.decode import decode_fit
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.metrics import compute_metrics
from fitdocs.model import Activity
from fitdocs.render import DocContext, render_document
from fitdocs.render.format import ABSENT
from tests.fixtures import builder

runner = CliRunner()

_PRE_RUNNING_DYNAMICS_DOC_VERSION: int = 5
"""The document-format version `contract.DOC_VERSION` held on `main` before the
running-dynamics spec's task 5.1 advanced it to 6 (see that constant's own
docstring: "Raised from ``5`` to ``6`` by the running-dynamics spec"). Named
here, with its provenance, rather than left as a bare literal in a test body;
a run page aged to this version is one regeneration must bring current."""

_DYNAMICS_LINK_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+-dynamics\.svg)\)")


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ``sync`` network-free: the tile fetch seam returns fixed bytes."""
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _clock(seconds: float) -> str:
    """``m:ss`` as the page prints a duration under an hour."""
    whole = int(seconds)
    assert whole < 3600
    return f"{whole // 60}:{whole % 60:02d}"


def _body(text: str) -> str:
    """The text after the frontmatter's closing fence."""
    assert text.startswith("---\n")
    close = text.index("\n---\n", len("---\n"))
    return text[close + len("\n---\n") :]


def _table_rows(body: str, heading: str) -> list[list[str]]:
    """Cell lists of the data rows of the table that follows ``heading``."""
    lines = body.split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    rows: list[list[str]] = []
    in_table = False
    for line in lines[start + 1 :]:
        if line.startswith("|"):
            in_table = True
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif in_table:
            break
    return rows[2:]  # drop the header and its separator


@pytest.fixture
def synced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, str]:
    """(data root, page path text, output) after syncing only the Stryd file."""
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    source.mkdir()
    (source / "stryd.fit").write_bytes(builder.stryd_run_fit_bytes())

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert result.exit_code == 0, result.output
    pages = [
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.name != DECLARATION_FILENAME
    ]
    assert len(pages) == 1, pages
    return data_root, pages[0].read_text(encoding="utf-8"), result.output


def test_stryd_file_syncs_to_one_run_page_with_the_section_and_chart(
    synced: tuple[Path, str, str],
) -> None:
    """6.6, 8.4: one run page, one Running Dynamics section, and its chart
    asset exists and is reached by a link that resolves from the page."""
    data_root, text, _output = synced
    body = _body(text)
    assert "modality: run\n" in text
    assert body.count("\n## Running Dynamics\n") == 1

    links = _DYNAMICS_LINK_RE.findall(body)
    assert len(links) == 1, links
    workouts = data_root / WORKOUTS_DIR
    assert not Path(links[0]).is_absolute()
    asset = (workouts / links[0]).resolve()
    assert asset.is_file()
    assert asset.read_text(encoding="utf-8").lstrip().startswith("<svg")
    assert asset.parent == (workouts / "assets").resolve()


def test_page_heart_rate_comes_from_the_non_zero_samples(
    synced: tuple[Path, str, str],
) -> None:
    """6.1: the session records no average or maximum heart rate, so the page's
    Avg HR and max HR are derived from the non-zero record samples."""
    _root, text, _output = synced
    records = builder._stryd_records()
    all_hr: list[int] = []
    for native, _dev in records:
        hr = native["heart_rate"]
        assert isinstance(hr, int)
        all_hr.append(hr)
    nonzero = [hr for hr in all_hr if hr != 0]
    placeholders = len(all_hr) - len(nonzero)
    assert placeholders == len(builder._STRYD_PLACEHOLDERS) > 0

    avg = mean(nonzero)
    # The expectation must separate a mean over non-zero samples from a mean
    # that counts the placeholder zeros, and must not sit on a rounding tie.
    assert round(mean(all_hr)) != round(avg)
    assert abs(avg % 1 - 0.5) > 0.05

    expected = f"| Avg HR | {round(avg)} bpm (max {max(nonzero)} bpm) |"
    assert expected in _body(text)
    assert f"\navg_hr_bpm: {round(avg)}\n" in text


def test_elapsed_and_moving_times_are_the_session_totals(
    synced: tuple[Path, str, str],
) -> None:
    """6.3: pins that elapsed time is not derived from the session timestamp and
    that moving time is not derived from the samples. On this fixture the timer
    and elapsed totals are both 43 s, so a swap of the two is not visible here;
    that pairing is pinned by
    ``tests/metrics/test_aggregates.py::test_moving_time_prefers_session_timer``,
    ``::test_elapsed_prefers_session_total_over_channel`` and
    ``tests/ingest/test_summary.py::test_full_session_maps_every_field``."""
    _root, text, _output = synced
    total = builder._STRYD_RECORD_COUNT - 1  # the fixture's timer and elapsed total
    # The session timestamp is the fourth lap's start, so the timestamp-derived
    # span is a different number from the total.
    timestamp_span = builder._STRYD_LAP_WINDOWS[-1][0]
    assert _clock(timestamp_span) != _clock(total)

    row = f"| Moving time | {_clock(total)} (elapsed {_clock(total)}) |"
    assert row in _body(text)
    assert f"\nmoving_time: {_clock(total)}\n" in text


def test_device_lap_table_has_one_row_per_recorded_lap_without_heart_rate(
    synced: tuple[Path, str, str],
) -> None:
    """6.2, 6.4: four device-lap rows (the session says num_laps 1), each with
    the absence marker in both heart-rate cells."""
    _root, text, _output = synced
    windows = builder._STRYD_LAP_WINDOWS
    assert len(windows) == 4
    # The session's stated lap count must disagree with the recorded laps.
    decoded = decode_fit(builder.stryd_run_fit_bytes()).messages
    session_num_laps = decoded["session_mesgs"][0]["num_laps"]
    recorded_laps = len(parse_fit(builder.stryd_run_fit_bytes()).laps)
    assert recorded_laps == len(windows)
    assert session_num_laps != recorded_laps

    rows = _table_rows(_body(text), "**Device laps**")
    lap_rows = [r for r in rows if r[0].startswith("Lap ")]
    assert [r[0] for r in lap_rows] == [f"Lap {n}" for n in range(1, 5)]
    for row, (start, end) in zip(lap_rows, windows, strict=True):
        assert row[2] == _clock(end - start + 1)
        assert row[3] == ABSENT  # Avg HR
        assert row[4] == ABSENT  # Max HR

    # Heart rate is not absent everywhere: the sibling table shows it, so the
    # marker above is the laps' own absence, not a page without heart rate.
    km_rows = _table_rows(_body(text), "**1 km splits**")
    assert km_rows[0][3].endswith(" bpm")


def test_no_record_environmental_developer_value_reaches_the_page(
    synced: tuple[Path, str, str],
) -> None:
    """6.5: humidity 104 is recorded (and stays on the model) yet the page body
    renders neither the value nor a label naming a record developer field."""
    _root, text, _output = synced
    activity = parse_fit(builder.stryd_run_fit_bytes())
    humidity = activity.record_developer_fields["Stryd Humidity"]
    assert 104 in humidity.values

    body = _body(text)
    assert "104%" not in body
    assert "Stryd Humidity" not in body
    assert "Stryd Temperature" not in body
    for token in ("Humidity", "Temperature", "°C"):
        assert token not in body, token
    # The Summary table shows exactly the rows the fixture supports: distance,
    # moving/elapsed time, run pace, climb (recorded altitude) and heart rate.
    # A row from a record developer field would add a label.
    summary = _table_rows(body, "## Summary")
    assert [r[0] for r in summary] == [
        "Distance",
        "Moving time",
        "Pace",
        "Climb",
        "Avg HR",
    ]
    coverage = _table_rows(body, "**Channel coverage**")
    assert coverage, "the coverage table is the thing under inspection"
    assert all(row[0] != "Temperature" for row in coverage)


def test_record_developer_fields_change_nothing_in_the_rendered_page() -> None:
    """6.5: rendering the activity with and without its record-level
    environmental developer fields gives the same markdown and the same
    assets, whatever surface a field might be drawn onto."""
    activity = parse_fit(builder.stryd_run_fit_bytes())
    environmental = {"Stryd Humidity", "Stryd Temperature"}
    assert environmental <= set(activity.record_developer_fields)
    stripped = dataclasses.replace(
        activity,
        record_developer_fields=MappingProxyType(
            {
                k: v
                for k, v in activity.record_developer_fields.items()
                if k not in environmental
            }
        ),
    )
    assert set(stripped.record_developer_fields) != set(
        activity.record_developer_fields
    )

    def render(subject: Activity) -> tuple[str, tuple[tuple[str, str], ...]]:
        ctx = DocContext(
            activity=subject,
            metrics=compute_metrics(subject),
            athlete=None,
            doc_stem="differential",
            source_refs=("fit-archive/differential.fit",),
            tz=UTC,
            map_data=None,
        )
        doc = render_document(ctx)
        return doc.markdown, tuple((a.rel_path, a.content) for a in doc.assets)

    with_fields = render(activity)
    without_fields = render(stripped)
    assert with_fields[1], "the page has assets, so the asset comparison is non-trivial"
    assert with_fields[0] == without_fields[0]
    assert with_fields[1] == without_fields[1]


_EFFORT_TAG = (
    "effort: race\n"
    "effort_distance_m: 42195\n"
    "effort_time_s: 10692\n"
    'effort_event: "[[Boston Marathon 2024]]"\n'
)
_NOTE = "Felt smooth through the last kilometre."


def test_regeneration_brings_a_pre_feature_run_page_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """9.2, 9.3: a run page written before the Running Dynamics section existed
    (older version, no section, no image link) is reported stale by ``check``;
    ``regen`` restores the section and stamps the current version while the
    notes region and the effort-tag lines survive byte for byte; a second
    ``check`` reports it current."""
    # A forward assertion: a later sibling advance leaves it true.
    assert contract.DOC_VERSION > _PRE_RUNNING_DYNAMICS_DOC_VERSION

    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    source.mkdir()
    (source / "native.fit").write_bytes(builder.run_native_dynamics_fit_bytes())

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert result.exit_code == 0, result.output
    pages = [
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.name != DECLARATION_FILENAME
    ]
    assert len(pages) == 1, pages
    page = pages[0]
    synced_text = page.read_text(encoding="utf-8")
    assert "modality: run\n" in synced_text
    assert f"\ndoc_version: {contract.DOC_VERSION}\n" in synced_text
    assert synced_text.count("\n## Running Dynamics\n") == 1
    assert len(_DYNAMICS_LINK_RE.findall(synced_text)) == 1

    # Age the page: drop the section (heading through the image link, up to the
    # next heading), record the old version, and delete the chart asset the
    # first sync wrote so that only regeneration can bring it back.
    start = synced_text.index("## Running Dynamics\n")
    end = synced_text.index("\n## ", start + 1) + 1
    aged = synced_text[:start] + synced_text[end:]
    aged = aged.replace(
        f"\ndoc_version: {contract.DOC_VERSION}\n",
        f"\ndoc_version: {_PRE_RUNNING_DYNAMICS_DOC_VERSION}\n",
        1,
    )
    # Hand edits: text in the notes region, a valid effort tag in the frontmatter.
    begin, finish = begin_marker("notes"), end_marker("notes")
    n0 = aged.index(begin)
    n1 = aged.index(finish) + len(finish)
    aged = aged[:n0] + f"{begin}\n{_NOTE}\n{finish}" + aged[n1:]
    fence = aged.index("---\n", len("---\n"))
    aged = aged[:fence] + _EFFORT_TAG + aged[fence:]
    page.write_text(aged, encoding="utf-8")
    dynamics_assets = [
        data_root / WORKOUTS_DIR / rel for rel in _DYNAMICS_LINK_RE.findall(synced_text)
    ]
    assert len(dynamics_assets) == 1
    for asset_file in dynamics_assets:
        asset_file.unlink()

    # The aging really happened: preconditions are live.
    assert "## Running Dynamics" not in aged
    assert not _DYNAMICS_LINK_RE.findall(aged)
    assert f"\ndoc_version: {_PRE_RUNNING_DYNAMICS_DOC_VERSION}\n" in aged
    assert f"\ndoc_version: {contract.DOC_VERSION}\n" not in aged
    assert extract_regions(aged)["notes"] == _NOTE
    assert _EFFORT_TAG in aged
    assert not dynamics_assets[0].exists()

    stale = runner.invoke(app, ["check", "--out", str(data_root)])
    assert stale.exit_code == 1, stale.output
    assert page.name in stale.output
    assert (
        f"doc_version is {_PRE_RUNNING_DYNAMICS_DOC_VERSION}, below the current"
        in stale.output
    )
    assert "No findings" not in stale.output

    regen = runner.invoke(app, ["regen", "--out", str(data_root)])
    assert regen.exit_code == 0, regen.output

    text = page.read_text(encoding="utf-8")
    assert text.count("\n## Running Dynamics\n") == 1
    links = _DYNAMICS_LINK_RE.findall(text)
    assert len(links) == 1, links
    assert (data_root / WORKOUTS_DIR / links[0]).is_file()
    assert (data_root / WORKOUTS_DIR / links[0]) == dynamics_assets[0]
    assert f"\ndoc_version: {contract.DOC_VERSION}\n" in text
    assert f"\ndoc_version: {_PRE_RUNNING_DYNAMICS_DOC_VERSION}\n" not in text
    assert extract_regions(text)["notes"] == _NOTE
    assert _EFFORT_TAG in text

    current = runner.invoke(app, ["check", "--out", str(data_root)])
    assert current.exit_code == 0, current.output
    assert "No findings" in current.output
