"""Tests for ``fitdocs derive-benchmarks`` and its report rendering (design:
DeriveCommand; Req 1.1, 1.9, 1.10, 7.1, 7.2, 7.3, 7.8, 9.6).

Two layers, mirroring ``tests/test_cli_drain_report.py`` /
``tests/load/test_cli_load.py``:

* Report-rendering unit tests call ``fitdocs.cli._report_derive`` directly
  against a hand-built ``DeriveReport`` under ``capsys`` -- no CLI, no real
  data root -- to pin the exact shape of every printed section.
* End-to-end tests drive the installable entry point through
  ``typer.testing.CliRunner`` over a synthetic, real data root built with
  the minimal workout/archive helpers copied from
  ``tests/performance/test_engine.py`` (that module owns no importable
  helper module of its own), to pin exit codes, ``--dry-run``, ``--out``,
  and the command's wiring into the pass itself.
"""

from __future__ import annotations

import hashlib
import locale
import re
import socket
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from fitdocs import contract, docio
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.cli import _report_derive, app
from fitdocs.layout import ARCHIVE_DIR
from fitdocs.load.profile import PROFILE_FILENAME, load_profile
from fitdocs.model import Sport
from fitdocs.performance.engine import (
    DeriveEntry,
    DeriveFailure,
    DeriveReport,
    QuantitySummary,
)
from fitdocs.performance.types import (
    DeclineReason,
    DerivationDeclined,
    DerivationMethod,
    DerivedBenchmark,
)
from tests.fixtures import builder

runner = CliRunner()

# --- minimal fixture builders (copied from tests/performance/test_engine.py,
# which owns no importable helper module of its own) -----------------------

WORKOUT_FRONTMATTER = """---
type: workout
date: "{date}"
{effort_lines}{sources_lines}---
"""


def _effort_lines(
    *, kind: str | None = None, distance: float | None = None, time: float | None = None
) -> str:
    lines = []
    if kind is not None:
        lines.append(f"effort: {kind}\n")
    if distance is not None:
        lines.append(f"effort_distance_m: {distance}\n")
    if time is not None:
        lines.append(f"effort_time_s: {time}\n")
    return "".join(lines)


def _sources_lines(sources: Sequence[str] | None) -> str:
    if not sources:
        return ""
    lines = ["sources:\n"]
    lines.extend(f"  - {ref}\n" for ref in sources)
    return "".join(lines)


def _write_archive(data_root: Path, data: bytes) -> str:
    sha256 = hashlib.sha256(data).hexdigest()
    archive_dir = data_root / ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{sha256}.fit").write_bytes(data)
    return f"{ARCHIVE_DIR}/{sha256}.fit"


def _write_workout(
    data_root: Path,
    name: str,
    *,
    on: str = "2024-05-01",
    kind: str | None = None,
    distance: float | None = None,
    time: float | None = None,
    sources: Sequence[str] | None = None,
) -> Path:
    workouts = data_root / "workouts"
    workouts.mkdir(parents=True, exist_ok=True)
    path = workouts / name
    text = WORKOUT_FRONTMATTER.format(
        date=on,
        effort_lines=_effort_lines(kind=kind, distance=distance, time=time),
        sources_lines=_sources_lines(sources),
    )
    path.write_text(text + "\nBody.\n", encoding="utf-8")
    return path


def _block(output: str, heading: str) -> str:
    """Text printed under ``heading:`` up to the next ``Word:`` heading or
    end of output (idiom copied from ``tests/test_cli_drain_report.py``)."""
    after = output.split(f"{heading}:\n", maxsplit=1)[1]
    next_heading = re.search(r"\n[A-Za-z ]+:\n", "\n" + after)
    return after[: next_heading.start()] if next_heading else after


# --- report-rendering unit tests --------------------------------------------


def _derived(
    *,
    kind: BenchmarkKind = BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
    discipline: Sport = Sport.RUN,
    value: float = 210.5,
    on: date = date(2024, 5, 1),
    method: DerivationMethod = DerivationMethod.RIEGEL_RACE_EQUIVALENCE,
    document: str = "workouts/race.md",
) -> DerivedBenchmark:
    return DerivedBenchmark(
        kind=kind,
        discipline=discipline,
        value=value,
        measured_on=on,
        method=method,
        citation_key="riegel_1981",
        inputs="official distance 10000 m, official time 2400 s",
        note="note",
        document=document,
    )


def test_summary_counts_render_with_pairwise_distinct_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The summary table's five counts are each individually nameable --
    pairwise-distinct so a swap between any two columns reddens (Req 7.1).

    Falsity in the starting state: nothing has been printed before the call.
    """
    decline = DerivationDeclined(
        kind=BenchmarkKind.LTHR_BPM,
        method=DerivationMethod.SUSTAINED_EFFORT_MEAN_HR,
        reason=DeclineReason.STREAM_ABSENT,
        detail="no heart rate",
    )
    # Two entries, three derived, four declines over two declining documents:
    # every count differs from the entry count and from the number of
    # declining documents, so a count taken from the wrong source reddens.
    report = DeriveReport(
        considered=11,
        tagged=7,
        entries=(
            DeriveEntry(
                document="workouts/a.md",
                derived=(_derived(), _derived(on=date(2024, 5, 2))),
                declined=(decline,) * 3,
            ),
            DeriveEntry(
                document="workouts/b.md",
                derived=(_derived(on=date(2024, 5, 3)),),
                declined=(decline,),
            ),
        ),
        failures=(DeriveFailure(document="workouts/c.md", reason="bad"),) * 5,
        written=True,
    )
    assert len(report.entries) == 2
    assert len(report.derived) == 3
    assert len(report.declined) == 4

    _report_derive(report, dry_run=False)

    output = capsys.readouterr().out
    assert re.search(r"Considered\s*│\s*11", output)
    assert re.search(r"Tagged\s*│\s*7", output)
    assert re.search(r"Derived\s*│\s*3", output)
    assert re.search(r"Declined\s*│\s*4", output)
    assert re.search(r"Failed\s*│\s*5", output)


def test_written_line_states_yes_when_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = DeriveReport(considered=1, tagged=1, entries=(), failures=(), written=True)

    _report_derive(report, dry_run=False)

    assert "Profile written: yes" in capsys.readouterr().out


def test_written_line_states_no_when_not_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = DeriveReport(
        considered=1, tagged=1, entries=(), failures=(), written=False
    )

    _report_derive(report, dry_run=False)

    assert "Profile written: no" in capsys.readouterr().out


def test_dry_run_first_line_states_nothing_was_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--dry-run``'s report leads with a line stating nothing was written,
    strictly before the summary table (Req 1.9): the mutation that prints it
    after the table, rather than first, must redden this test's ordering
    check even though "nothing was written" would still appear somewhere in
    the output.
    """
    report = DeriveReport(
        considered=1, tagged=1, entries=(), failures=(), written=False
    )

    _report_derive(report, dry_run=True)

    output = capsys.readouterr().out
    first_line = output.splitlines()[0]
    assert "nothing" in first_line.lower()
    assert "written" in first_line.lower()


def test_non_dry_run_has_no_dry_run_line(capsys: pytest.CaptureFixture[str]) -> None:
    report = DeriveReport(considered=1, tagged=1, entries=(), failures=(), written=True)

    _report_derive(report, dry_run=False)

    assert "nothing was written" not in capsys.readouterr().out.lower()


def test_derived_entry_renders_quantity_discipline_date_method_document(
    capsys: pytest.CaptureFixture[str],
) -> None:
    benchmark = _derived(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=256.0,
        on=date(2023, 8, 15),
        method=DerivationMethod.TIME_TRIAL_MEAN_POWER,
        document="workouts/tt.md",
    )
    report = DeriveReport(
        considered=1,
        tagged=1,
        entries=(
            DeriveEntry(document="workouts/tt.md", derived=(benchmark,), declined=()),
        ),
        failures=(),
        written=True,
    )

    _report_derive(report, dry_run=False)

    derived_block = _block(capsys.readouterr().out, "Derived")
    assert "ftp_watts" in derived_block
    assert "Ride" in derived_block
    assert "2023-08-15" in derived_block
    assert "time_trial_mean_power" in derived_block
    assert "workouts/tt.md" in derived_block


@pytest.mark.parametrize(
    ("kind", "discipline", "value", "unit"),
    [
        (BenchmarkKind.FTP_WATTS, Sport.RIDE, 256.0, "W"),
        (BenchmarkKind.LTHR_BPM, Sport.RUN, 172.0, "bpm"),
        (BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN, 210.5, "s/km"),
    ],
)
def test_derived_entry_renders_the_correct_unit_for_each_quantity(
    capsys: pytest.CaptureFixture[str],
    kind: BenchmarkKind,
    discipline: Sport,
    value: float,
    unit: str,
) -> None:
    """Each of the three quantities carries its own unit; swapping any two
    units (M8b: watts labelled "W" on an LTHR entry, M8c: pace labelled
    "bpm") must redden only its own case, so the three values are
    pairwise-distinct and each parametrization checks the exact
    ``"{value:g} {unit}"`` substring the real format string produces.
    """
    benchmark = _derived(kind=kind, discipline=discipline, value=value)
    report = DeriveReport(
        considered=1,
        tagged=1,
        entries=(
            DeriveEntry(document="workouts/race.md", derived=(benchmark,), declined=()),
        ),
        failures=(),
        written=True,
    )

    _report_derive(report, dry_run=False)

    derived_block = _block(capsys.readouterr().out, "Derived")
    assert f"{value:g} {unit}" in derived_block


def test_declines_are_grouped_under_their_own_document_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Three documents -- two declining a different, pairwise-distinct
    reason, and one with only a derived benchmark and no decline at all --
    so each reason must appear only in its own document's block (Req 7.2's
    grouping requirement): a decline folded under the wrong document, or
    all declines flattened into one list, would leak the other document's
    reason into this document's block, and a filter that stops excluding
    declines-free entries would leak the third document into this block at
    all even though it never declined anything.
    """
    decline_a = DerivationDeclined(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        method=DerivationMethod.RIEGEL_RACE_EQUIVALENCE,
        reason=DeclineReason.EFFORT_KIND_NOT_USED,
        detail="effort kind 'test' is not used for threshold pace (race only)",
    )
    decline_b = DerivationDeclined(
        kind=BenchmarkKind.FTP_WATTS,
        method=None,
        reason=DeclineReason.SPORT_NOT_COVERED,
        detail="sport 'strength' is not covered",
    )
    report = DeriveReport(
        considered=3,
        tagged=3,
        entries=(
            DeriveEntry(document="workouts/a.md", derived=(), declined=(decline_a,)),
            DeriveEntry(document="workouts/b.md", derived=(), declined=(decline_b,)),
            DeriveEntry(document="workouts/c.md", derived=(_derived(),), declined=()),
        ),
        failures=(),
        written=True,
    )

    _report_derive(report, dry_run=False)

    output = capsys.readouterr().out
    declined_block = _block(output, "Declined")
    assert "workouts/c.md" not in declined_block
    a_start = declined_block.index("workouts/a.md")
    b_start = declined_block.index("workouts/b.md")
    a_section = declined_block[a_start:b_start]
    b_section = declined_block[b_start:]

    assert "threshold_pace_s_per_km: effort_kind_not_used" in a_section
    assert "sport_not_covered" not in a_section
    assert "ftp_watts: sport_not_covered" in b_section
    assert "effort_kind_not_used" not in b_section


def test_decline_reports_observed_and_required_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    decline = DerivationDeclined(
        kind=BenchmarkKind.LTHR_BPM,
        method=DerivationMethod.SUSTAINED_EFFORT_MEAN_HR,
        reason=DeclineReason.OUTSIDE_VALIDITY_WINDOW,
        detail="duration 12s is outside the sustained-effort validity window",
        observed=12.0,
        required=480.0,
    )
    report = DeriveReport(
        considered=1,
        tagged=1,
        entries=(
            DeriveEntry(document="workouts/a.md", derived=(), declined=(decline,)),
        ),
        failures=(),
        written=False,
    )

    _report_derive(report, dry_run=False)

    declined_block = _block(capsys.readouterr().out, "Declined")
    # The exact labelled tokens, not just the bare numbers: a swap between
    # the observed= and required= labels leaves both numbers present but
    # under the wrong label, so pin the label-value pairing directly. The
    # two values are pairwise-distinct so a swap cannot hide behind equal
    # numbers.
    assert "observed=12.0" in declined_block
    assert "required=480.0" in declined_block


def test_decline_reports_observed_alone_when_required_is_absent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A decline carrying `observed` but no `required` (the shape the
    MISSING_INPUT leaves produce) still prints its observed value; one
    carrying neither prints no observed line at all (Req 7.3)."""
    one_sided = DerivationDeclined(
        kind=BenchmarkKind.LTHR_BPM,
        method=DerivationMethod.SUSTAINED_EFFORT_MEAN_HR,
        reason=DeclineReason.MISSING_INPUT,
        detail="mean heart rate 0 bpm is not a usable value",
        observed=0.0,
        required=None,
    )
    neither = DerivationDeclined(
        kind=BenchmarkKind.FTP_WATTS,
        method=None,
        reason=DeclineReason.SPORT_NOT_COVERED,
        detail="sport 'strength' is not covered",
    )
    report = DeriveReport(
        considered=2,
        tagged=2,
        entries=(
            DeriveEntry(document="workouts/a.md", derived=(), declined=(one_sided,)),
            DeriveEntry(document="workouts/b.md", derived=(), declined=(neither,)),
        ),
        failures=(),
        written=False,
    )

    _report_derive(report, dry_run=False)

    declined_block = _block(capsys.readouterr().out, "Declined")
    a_start = declined_block.index("workouts/a.md")
    b_start = declined_block.index("workouts/b.md")
    assert "observed=0.0" in declined_block[a_start:b_start]
    assert "observed=" not in declined_block[b_start:]


def test_bracketed_reason_renders_literally_not_as_markup(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A bracketed document path and a bracketed decline detail that does
    NOT repeat the document path (so the document line is not
    incidentally pinned by the detail assertion), plus a bracketed Failed
    document and a Failed reason built from a real Rich tag pair
    (``[bold]...[/bold]``, which Rich renders as bold and strips when
    interpreted) -- each printed with ``markup=False``. If any of the three
    ``console.print`` calls this test pins dropped that keyword, Rich would
    interpret the brackets and the exact literal line assertion reddens on
    that call independently of the other two.
    """
    decline = DerivationDeclined(
        kind=BenchmarkKind.FTP_WATTS,
        method=None,
        reason=DeclineReason.SPORT_NOT_COVERED,
        detail="a [bracketed] reason, sport not covered",
    )
    report = DeriveReport(
        considered=1,
        tagged=1,
        entries=(
            DeriveEntry(
                document="workouts/[weird].md", derived=(), declined=(decline,)
            ),
        ),
        failures=(
            DeriveFailure(
                document="workouts/[bold].md",
                reason="effort_event: got '[bold]Boston[/bold]'",
            ),
        ),
        written=False,
    )

    _report_derive(report, dry_run=False)

    output = capsys.readouterr().out
    declined_block = _block(output, "Declined")
    declined_lines = declined_block.splitlines()
    assert "  workouts/[weird].md" in declined_lines
    assert "a [bracketed] reason, sport not covered" in declined_block

    failed_block = _block(output, "Failed")
    assert "  workouts/[bold].md" in failed_block.splitlines()
    assert "    effort_event: got '[bold]Boston[/bold]'" in failed_block.splitlines()


def test_failures_list_document_and_reason(capsys: pytest.CaptureFixture[str]) -> None:
    report = DeriveReport(
        considered=1,
        tagged=1,
        entries=(),
        failures=(
            DeriveFailure(document="workouts/broken.md", reason="undecodable archive"),
        ),
        written=False,
    )

    _report_derive(report, dry_run=False)

    failed_block = _block(capsys.readouterr().out, "Failed")
    assert "workouts/broken.md" in failed_block
    assert "undecodable archive" in failed_block


def test_quantity_summary_names_dominant_reason_and_never_attempted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One quantity that was attempted and declined every time (a real
    dominant reason) and one that was never even attempted (``None``, which
    must render as the honest "never attempted" rather than an empty
    string) -- each on its own line, so a mutation collapsing ``None`` into
    an empty reason string reddens this test without also reddening the
    dominant-reason line.
    """
    report = DeriveReport(
        considered=1,
        tagged=1,
        entries=(),
        failures=(),
        written=False,
        summaries=(
            QuantitySummary(
                kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
                dominant_reason=DeclineReason.EFFORT_KIND_NOT_USED,
            ),
            QuantitySummary(kind=BenchmarkKind.FTP_WATTS, dominant_reason=None),
        ),
    )

    _report_derive(report, dry_run=False)

    summary_block = _block(capsys.readouterr().out, "Quantity summaries")
    pace_line = next(
        line for line in summary_block.splitlines() if "threshold_pace_s_per_km" in line
    )
    ftp_line = next(line for line in summary_block.splitlines() if "ftp_watts" in line)
    assert "effort_kind_not_used" in pace_line
    assert "never attempted" not in pace_line
    assert "never attempted" in ftp_line


# --- end-to-end tests over a real, synthetic data root ----------------------


def test_command_help_shows_out_and_dry_run_options() -> None:
    result = runner.invoke(app, ["derive-benchmarks", "--help"])

    assert result.exit_code == 0
    assert "--out" in result.output
    assert "--dry-run" in result.output


def test_successful_run_prints_every_section_writes_once_and_exits_zero(
    tmp_path: Path,
) -> None:
    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path, "race.md", kind="race", distance=10000, time=2400, sources=[ref]
    )
    _write_workout(tmp_path, "untagged.md", kind=None)

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    for heading in ("Considered", "Tagged", "Derived", "Declined", "Failed"):
        assert heading in result.output
    assert "Profile written: yes" in result.output
    assert "workouts/race.md" in _block(result.output, "Derived")

    profile_path = tmp_path / PROFILE_FILENAME
    assert profile_path.is_file()
    assert profile_path.read_bytes() != b""


def test_malformed_tag_on_one_page_still_writes_the_other_pages_benchmark(
    tmp_path: Path,
) -> None:
    """A run whose only defect is a malformed tag on one page still writes
    the other page's derived benchmark and exits non-zero (design's stated
    observable; Req 1.5, 1.6, 1.9).
    """
    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path, "race.md", kind="race", distance=10000, time=2400, sources=[ref]
    )
    _write_workout(tmp_path, "broken.md", kind="marathon")

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "workouts/broken.md" in _block(result.output, "Failed")

    profile = load_profile(tmp_path)
    assert any(
        entry.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
        for entry in profile.benchmarks.entries
    )


def test_failure_only_run_exits_one_with_zero_declines(tmp_path: Path) -> None:
    """A data root with ONLY a malformed-tag page (no tagged page at all,
    so ``declined`` is necessarily empty) still exits 1: this pins the
    failure-path exit on ``failures`` alone, defeating a mutation that
    additionally requires a non-empty ``declined`` set (the only other
    failure-path fixture in this module also declines, which let that
    mutation survive).
    """
    _write_workout(tmp_path, "broken.md", kind="marathon")

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert re.search(r"Declined\s*│\s*0", result.output)
    assert "workouts/broken.md" in _block(result.output, "Failed")


def test_decline_only_run_exits_zero(tmp_path: Path) -> None:
    """A tagged page whose sport is not covered declines every derivation
    but fails nothing -- the exit status stays 0, never 1 (design's named
    mutation: treating a decline as a failure)."""
    ref = _write_archive(tmp_path, builder.strength_fit_bytes())
    _write_workout(tmp_path, "lift.md", kind="race", sources=[ref])

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert result.exit_code != 1
    declined_block = _block(result.output, "Declined")
    assert "sport_not_covered" in declined_block
    assert not (tmp_path / PROFILE_FILENAME).is_file()


def test_dry_run_writes_no_bytes_even_when_a_benchmark_would_be_derived(
    tmp_path: Path,
) -> None:
    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path, "race.md", kind="race", distance=10000, time=2400, sources=[ref]
    )
    profile_path = tmp_path / PROFILE_FILENAME
    assert not profile_path.exists()

    result = runner.invoke(
        app, ["derive-benchmarks", "--out", str(tmp_path), "--dry-run"]
    )

    assert result.exit_code == 0, result.output
    first_line = result.output.splitlines()[0]
    assert "nothing" in first_line.lower()
    assert "Profile written: yes" not in result.output
    assert "Profile written: no" in result.output
    assert not profile_path.exists(), "dry-run must create no file at all"


def test_out_option_is_honored_over_the_default_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--out`` selects the resolved data root: the profile lands under the
    named directory, never under an unrelated default one a stray env/CWD
    fallback might otherwise pick (Req 9.6)."""
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    named_root = tmp_path / "named-root"
    decoy_root = tmp_path / "decoy-root"
    named_root.mkdir()
    decoy_root.mkdir()
    monkeypatch.chdir(decoy_root)

    ref = _write_archive(named_root, builder.run_fit_bytes())
    _write_workout(
        named_root, "race.md", kind="race", distance=10000, time=2400, sources=[ref]
    )

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(named_root)])

    assert result.exit_code == 0, result.output
    assert (named_root / PROFILE_FILENAME).is_file()
    assert not (decoy_root / PROFILE_FILENAME).exists()


def test_unresolvable_data_root_is_a_configuration_fault_exiting_two(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(missing)])

    assert result.exit_code == 2, result.output


def test_malformed_load_table_is_a_configuration_fault_exiting_two(
    tmp_path: Path,
) -> None:
    """A malformed ``[load]`` table -- read via the same
    :func:`~fitdocs.load.settings.load_load_settings` reader the load pass
    uses -- surfaces here as :class:`~fitdocs.settings.SettingsError` and
    exits 2, before anything is written; it names the settings file, never a
    per-document failure (exit 1) or a silent success (exit 0)."""
    # A [load.sufficiency] value that is not itself a table is the malformed
    # shape load_load_settings rejects (verified against the real reader).
    (tmp_path / "fitdocs.toml").write_text(
        "[load]\nsufficiency = 'nope'\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 2, result.output
    # Stderr is soft-wrapped by Rich, so match the settings filename rather
    # than the full absolute path on one line.
    assert "fitdocs.toml" in result.output
    assert not (tmp_path / PROFILE_FILENAME).exists()


def test_malformed_athlete_toml_is_a_configuration_fault_exiting_two(
    tmp_path: Path,
) -> None:
    """A malformed ``athlete.toml`` -- read while loading the profile inside
    the pass -- is a configuration fault (exit 2), never a per-document
    failure (exit 1) or a silent success (exit 0)."""
    (tmp_path / PROFILE_FILENAME).write_text("not [ valid toml", encoding="utf-8")

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 2, result.output


# === end-to-end: determinism, the powerless archive and the mixed run =======
#
# Task 5.2 (design E2E/CLI Tests #5, Integration Tests #3/#5/#6; Req 1.8,
# 1.9, 4.6, 6.5, 7.7, 9.1). Everything below drives the real
# ``derive-benchmarks`` command through ``CliRunner`` over synthetic, real
# ``.fit`` archives -- no mocked activity, no direct call into
# ``fitdocs.performance``.
#
# ``builder.py`` provides no long-duration, full-coverage-stream fixture (its
# own run/ride fixtures span a fixed 9 seconds -- adequate for exercising the
# Riegel *official-pair* path, which never consults the recorded span, but far
# too short for the LTHR or FTP validity windows, both measured in minutes).
# The two helpers below build one with the same garmin_fit_sdk message shapes
# ``builder.py``'s own fixtures use (record/session/sport/file_id/
# device_info/activity, the FIT SDK's own global ``mesg_num`` values), so a
# real parse produces a real, several-thousand-second recorded span.

_E2E_MESG_FILE_ID = 0
_E2E_MESG_SPORT = 12
_E2E_MESG_SESSION = 18
_E2E_MESG_RECORD = 20
_E2E_MESG_DEVICE_INFO = 23
_E2E_MESG_ACTIVITY = 34


def _long_run_fit_bytes(
    *, duration_s: int, interval_s: int, distance_m: float, serial: int
) -> bytes:
    """A running ``.fit`` file with a real ``duration_s``-second recorded
    span and a heart-rate sample on every record (full coverage) -- long
    enough to clear the LTHR sustained-effort validity window, which
    ``builder.run_fit_bytes()``'s fixed 9-second span cannot."""
    count = duration_s // interval_s + 1
    records: list[dict[str, object]] = []
    for i in range(count):
        t = i * interval_s
        records.append(
            {
                "mesg_num": _E2E_MESG_RECORD,
                "timestamp": builder.FIT_TIMESTAMP_BASE + t,
                "heart_rate": 150 + (i % 5),
                "distance": distance_m * (t / duration_s),
                "enhanced_speed": distance_m / duration_s,
                "cadence": 85,
            }
        )
    mesgs: list[dict[str, object]] = [
        {
            "mesg_num": _E2E_MESG_FILE_ID,
            "type": "activity",
            "manufacturer": "garmin",
            "product": 1,
            "serial_number": serial,
            "time_created": builder.FIT_TIMESTAMP_BASE,
        },
        {
            "mesg_num": _E2E_MESG_DEVICE_INFO,
            "timestamp": builder.FIT_TIMESTAMP_BASE,
            "device_index": 0,
            "manufacturer": "garmin",
            "serial_number": serial,
            "product": 1,
            "software_version": 4.2,
            "battery_status": "good",
            "product_name": "SyntheticE2ERunWatch",
        },
        {"mesg_num": _E2E_MESG_SPORT, "sport": "running", "sub_sport": "generic"},
        *records,
        {
            "mesg_num": _E2E_MESG_SESSION,
            "start_time": builder.FIT_TIMESTAMP_BASE,
            "timestamp": builder.FIT_TIMESTAMP_BASE + duration_s,
            "sport": "running",
            "sub_sport": "generic",
            "total_elapsed_time": float(duration_s),
            "total_timer_time": float(duration_s),
            "total_distance": distance_m,
            "avg_heart_rate": 152,
            "max_heart_rate": 155,
            "avg_speed": distance_m / duration_s,
            "max_speed": distance_m / duration_s,
            "avg_cadence": 85,
            "max_cadence": 85,
        },
        {
            "mesg_num": _E2E_MESG_ACTIVITY,
            "timestamp": builder.FIT_TIMESTAMP_BASE + duration_s,
            "total_timer_time": float(duration_s),
            "num_sessions": 1,
            "type": "manual",
        },
    ]
    return builder.encode(mesgs)


def _power_ride_fit_bytes(
    *,
    duration_s: int,
    interval_s: int,
    power_w: int | None,
    serial: int,
    hr_partial_coverage: bool = False,
) -> bytes:
    """A cycling ``.fit`` file with a real ``duration_s``-second recorded
    span, a power sample on every record (full coverage) when ``power_w``
    is given -- or no power channel at all when it is ``None``, which is
    what makes the FTP leaf decline ``STREAM_ABSENT`` rather than
    ``TOO_SHORT``: a real recorded span long enough to clear the
    sufficiency gate's own minimum duration, just with nothing recorded on
    the power channel.

    No heart-rate channel at all by default (so this pass's own RIDE->LTHR
    routing leg declines ``STREAM_ABSENT`` rather than confounding the
    FTP-only assertions this helper exists for) -- unless
    ``hr_partial_coverage`` is set, which puts a heart-rate value on only
    the FIRST record, well below the sufficiency gate's minimum coverage,
    so LTHR declines ``STREAM_COVERAGE`` instead: a reason distinct from
    the FTP leaf's own ``STREAM_ABSENT``, deliberately so no assertion that
    reads "the dominant reason across every declined quantity" can pass by
    accident when every quantity happens to share one reason.

    Parameterized so the same helper builds the time trial (inside the FTP
    definition's own window), the 20-minute test (inside the blocked
    short-protocol range), and the powerless ride, all at a real
    multi-minute span."""
    count = duration_s // interval_s + 1
    records: list[dict[str, object]] = []
    for i in range(count):
        t = i * interval_s
        record: dict[str, object] = {
            "mesg_num": _E2E_MESG_RECORD,
            "timestamp": builder.FIT_TIMESTAMP_BASE + t,
            "cadence": 90,
            "speed": 8.0,
            "distance": 8.0 * t,
        }
        if power_w is not None:
            record["power"] = power_w
        if hr_partial_coverage and i == 0:
            record["heart_rate"] = 140
        records.append(record)
    session: dict[str, object] = {
        "mesg_num": _E2E_MESG_SESSION,
        "start_time": builder.FIT_TIMESTAMP_BASE,
        "timestamp": builder.FIT_TIMESTAMP_BASE + duration_s,
        "sport": "cycling",
        "sub_sport": "generic",
        "total_elapsed_time": float(duration_s),
        "total_timer_time": float(duration_s),
        "total_distance": 8.0 * duration_s,
        "total_calories": 400,
        "avg_cadence": 90,
        "max_cadence": 90,
        "avg_speed": 8.0,
        "max_speed": 8.0,
    }
    if power_w is not None:
        session["avg_power"] = power_w
        session["max_power"] = power_w
    mesgs: list[dict[str, object]] = [
        {
            "mesg_num": _E2E_MESG_FILE_ID,
            "type": "activity",
            "manufacturer": "garmin",
            "product": 1,
            "serial_number": serial,
            "time_created": builder.FIT_TIMESTAMP_BASE,
        },
        {
            "mesg_num": _E2E_MESG_DEVICE_INFO,
            "timestamp": builder.FIT_TIMESTAMP_BASE,
            "device_index": 0,
            "manufacturer": "garmin",
            "serial_number": serial,
            "product": 1,
            "software_version": 4.2,
            "battery_status": "good",
            "product_name": "SyntheticE2ERideComputer",
        },
        {"mesg_num": _E2E_MESG_SPORT, "sport": "cycling", "sub_sport": "generic"},
        *records,
        session,
        {
            "mesg_num": _E2E_MESG_ACTIVITY,
            "timestamp": builder.FIT_TIMESTAMP_BASE + duration_s,
            "total_timer_time": float(duration_s),
            "num_sessions": 1,
            "type": "manual",
        },
    ]
    return builder.encode(mesgs)


# Fixed, pairwise-distinct calendar dates for every tagged document below,
# all far from "today" (2026-09-12 at authoring time) so a leaf that dated an
# entry from the run's own wall-clock notion of today rather than from the
# page would be immediately visible rather than accidentally landing near a
# fixture date.
_E2E_RACE_ON = "2019-03-04"
_E2E_TT_ON = "2019-04-11"
_E2E_TWENTY_ON = "2019-05-18"
_E2E_POWERLESS_ON = "2019-06-22"


def _build_mixed_root(tmp_path: Path, *, include_malformed: bool) -> dict[str, str]:
    """Build the six-document synthetic root task 5.2 names: a tagged race
    (threshold pace + LTHR), a tagged >=50-minute time trial (FTP), a tagged
    20-minute test (blocked FTP method), a tagged powerless ride (FTP
    declines for a different reason), an untagged page, and -- only when
    ``include_malformed`` -- a page with a malformed tag. Returns the
    archive refs keyed by document so callers can assert exactly which
    archives were opened.
    """
    race_ref = _write_archive(
        tmp_path,
        _long_run_fit_bytes(
            duration_s=2400, interval_s=60, distance_m=10000.0, serial=9001
        ),
    )
    _write_workout(
        tmp_path,
        "race.md",
        on=_E2E_RACE_ON,
        kind="race",
        distance=10000,
        time=2400,
        sources=[race_ref],
    )

    tt_ref = _write_archive(
        tmp_path,
        _power_ride_fit_bytes(
            duration_s=3300, interval_s=300, power_w=220, serial=9002
        ),
    )
    _write_workout(tmp_path, "tt.md", on=_E2E_TT_ON, kind="race", sources=[tt_ref])

    twenty_ref = _write_archive(
        tmp_path,
        _power_ride_fit_bytes(
            duration_s=1200, interval_s=300, power_w=220, serial=9003
        ),
    )
    _write_workout(
        tmp_path, "twenty.md", on=_E2E_TWENTY_ON, kind="test", sources=[twenty_ref]
    )

    powerless_ref = _write_archive(
        tmp_path,
        _power_ride_fit_bytes(
            duration_s=3300,
            interval_s=300,
            power_w=None,
            serial=9004,
            hr_partial_coverage=True,
        ),
    )
    _write_workout(
        tmp_path,
        "powerless.md",
        on=_E2E_POWERLESS_ON,
        kind="race",
        sources=[powerless_ref],
    )

    untagged_ref = _write_archive(tmp_path, builder.non_fit_bytes())
    _write_workout(tmp_path, "untagged.md", kind=None, sources=[untagged_ref])

    refs = {
        "race": race_ref,
        "tt": tt_ref,
        "twenty": twenty_ref,
        "powerless": powerless_ref,
        "untagged": untagged_ref,
    }

    if include_malformed:
        _write_workout(tmp_path, "malformed.md", kind="marathon")

    return refs


def test_mixed_run_derives_declines_fails_and_never_opens_the_untagged_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The full mixed scenario in one CLI invocation (Req 1.3, 1.6, 1.9, 4.6,
    7.8, 9.2, plus 4.3/4.4 for the twenty-minute test's blocked method): the
    race derives both threshold pace and LTHR, the time trial derives FTP,
    the 20-minute test declines ``method_unverified``,
    the powerless ride declines ``stream_absent``, the malformed page fails
    carrying the contract's own ``describe()`` text, the untagged page's
    archive is never opened through any of the six access paths this test
    patches, no network connection is opened, and every derived entry is
    dated from its own page rather than from today.

    Falsity in the starting state: before the run nothing under
    ``fit-archive/`` has been accessed and no socket has been requested, so
    a non-empty ``accessed``/``socket_calls`` afterward is entirely produced
    by this run.
    """
    refs = _build_mixed_root(tmp_path, include_malformed=True)

    fm = docio.read_frontmatter(tmp_path / "workouts" / "malformed.md")
    tag = contract.effort_tag(fm)
    assert isinstance(tag, contract.InvalidEffortTag)
    expected_failure_reason = tag.describe()
    assert expected_failure_reason != ""

    archive_dir = tmp_path / ARCHIVE_DIR
    accessed: set[Path] = set()

    def _record(path: Path) -> None:
        try:
            path.relative_to(archive_dir)
        except ValueError:
            return
        accessed.add(path)

    real_is_file: Any = Path.is_file
    real_exists: Any = Path.exists
    real_stat: Any = Path.stat
    real_read_bytes: Any = Path.read_bytes
    real_path_open: Any = Path.open
    real_builtin_open: Any = open

    def recording_is_file(self: Path, *a: Any, **k: Any) -> bool:
        _record(self)
        return bool(real_is_file(self, *a, **k))

    def recording_exists(self: Path, *a: Any, **k: Any) -> bool:
        _record(self)
        return bool(real_exists(self, *a, **k))

    def recording_stat(self: Path, *a: Any, **k: Any) -> Any:
        _record(self)
        return real_stat(self, *a, **k)

    def recording_read_bytes(self: Path) -> bytes:
        _record(self)
        return bytes(real_read_bytes(self))

    def recording_path_open(self: Path, *a: Any, **k: Any) -> Any:
        _record(self)
        return real_path_open(self, *a, **k)

    def recording_builtin_open(file: Any, *a: Any, **k: Any) -> Any:
        if isinstance(file, (str, Path)):
            _record(Path(file))
        return real_builtin_open(file, *a, **k)

    monkeypatch.setattr(Path, "is_file", recording_is_file)
    monkeypatch.setattr(Path, "exists", recording_exists)
    monkeypatch.setattr(Path, "stat", recording_stat)
    monkeypatch.setattr(Path, "read_bytes", recording_read_bytes)
    monkeypatch.setattr(Path, "open", recording_path_open)
    monkeypatch.setattr("builtins.open", recording_builtin_open)

    socket_calls: list[object] = []

    def _raise_on_socket(*a: object, **k: object) -> None:
        socket_calls.append((a, k))
        raise AssertionError("derive-benchmarks must never open a socket")

    monkeypatch.setattr(socket, "socket", _raise_on_socket)

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert socket_calls == [], "the pass opened a network connection"

    untagged_archive = tmp_path / refs["untagged"]
    assert untagged_archive not in accessed
    for key in ("race", "tt", "twenty", "powerless"):
        assert tmp_path / refs[key] in accessed

    derived_block = _block(result.output, "Derived")
    assert "threshold_pace_s_per_km" in derived_block
    assert "lthr_bpm" in derived_block
    assert "ftp_watts" in derived_block
    assert _E2E_RACE_ON in derived_block
    assert _E2E_TT_ON in derived_block
    today = date.today().isoformat()
    assert today not in derived_block

    declined_block = _block(result.output, "Declined")
    # Slice per document on the "  workouts/..." heading line rather than by
    # a fixed pair of indices, so neither section can silently absorb a
    # THIRD document's lines regardless of print order.
    markers = list(re.finditer(r"^  (workouts/\S+)\n", declined_block, re.MULTILINE))
    per_document: dict[str, str] = {}
    for i, marker in enumerate(markers):
        end = markers[i + 1].start() if i + 1 < len(markers) else len(declined_block)
        per_document[marker.group(1)] = declined_block[marker.end() : end]
    twenty_section = per_document["workouts/twenty.md"]
    powerless_section = per_document["workouts/powerless.md"]
    assert "method_unverified" in twenty_section
    assert "ftp_watts: stream_absent" in powerless_section

    failed_block = _block(result.output, "Failed")
    assert "workouts/malformed.md" in failed_block
    assert expected_failure_reason in failed_block

    # FTP derived in this run (the time trial), so the CLI's "never
    # attempted / explicit decline reason" quantity-summary section (Req
    # 4.6, 7.7) does not print at all -- distinct from the separate-root
    # test below, where FTP derives nowhere and that section does print.
    assert "Quantity summaries:" not in result.output

    profile = load_profile(tmp_path)
    by_kind = {entry.kind: entry for entry in profile.benchmarks.entries}
    assert by_kind[
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM
    ].measured_on == date.fromisoformat(_E2E_RACE_ON)
    assert by_kind[BenchmarkKind.LTHR_BPM].measured_on == date.fromisoformat(
        _E2E_RACE_ON
    )
    assert by_kind[BenchmarkKind.FTP_WATTS].measured_on == date.fromisoformat(
        _E2E_TT_ON
    )
    assert by_kind[BenchmarkKind.FTP_WATTS].measured_on != date.today()


def test_same_root_minus_the_malformed_page_exits_zero_despite_declines(
    tmp_path: Path,
) -> None:
    """The identical root without the malformed page exits 0 (Req 1.9,
    7.8): the exit-status split is driven by ``failures`` alone, not by the
    presence of declines, which this root still has (the 20-minute test and
    the powerless ride both decline).
    """
    _build_mixed_root(tmp_path, include_malformed=False)

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    declined_block = _block(result.output, "Declined")
    assert "method_unverified" in declined_block
    assert "stream_absent" in declined_block


def test_ftp_summary_names_stream_absent_when_no_ride_anywhere_derives_it(
    tmp_path: Path,
) -> None:
    """A SEPARATE root holding only the powerless ride (no time trial, so
    FTP derives nowhere in this run) states in the quantity-summary section
    that no FTP was derived and names the dominant decline reason (Req 4.6,
    7.7) -- distinct from the mixed root above, where the time trial DOES
    derive FTP and the per-quantity summary line is correctly omitted for
    it (`engine`'s own "omit a quantity that derived anywhere" rule, pinned
    at the engine layer; this test pins the CLI-visible complement: the
    explicit statement when it truly derived nowhere).
    """
    powerless_ref = _write_archive(
        tmp_path,
        _power_ride_fit_bytes(
            duration_s=3300,
            interval_s=300,
            power_w=None,
            serial=9005,
            hr_partial_coverage=True,
        ),
    )
    _write_workout(
        tmp_path,
        "powerless-only.md",
        on=_E2E_POWERLESS_ON,
        kind="race",
        sources=[powerless_ref],
    )

    result = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    summary_block = _block(result.output, "Quantity summaries")
    ftp_line = next(line for line in summary_block.splitlines() if "ftp_watts" in line)
    lthr_line = next(line for line in summary_block.splitlines() if "lthr_bpm" in line)
    assert "stream_absent" in ftp_line
    assert "never attempted" not in ftp_line
    # The two quantities decline for two DIFFERENT reasons (LTHR's partial
    # heart-rate coverage vs FTP's total absence of power): if the reason
    # pool were pooled across quantities instead of filtered to each one,
    # this line would show the other quantity's reason instead of its own.
    assert "stream_coverage" in lthr_line
    assert "stream_absent" not in lthr_line


def test_third_run_after_a_removal_is_a_byte_level_no_op(tmp_path: Path) -> None:
    """Run, remove the tag, run again (the entry is gone, ``written`` is
    ``True``), run a THIRD time with no further change: the profile bytes
    are identical to the second run's and the report states nothing was
    written (Req 6.5's reconciliation invariant, extended one run further
    than the engine-level integration test, which stops at the second run).

    Falsity in the starting state, at each step: the entry exists after run
    1 (asserted before removal), is gone after run 2 (asserted before the
    byte comparison), and the second and third runs' bytes are compared only
    after confirming the second run actually changed the file relative to
    the first (otherwise a no-op comparison at any step would be vacuous).
    """
    ref = _write_archive(
        tmp_path,
        _long_run_fit_bytes(
            duration_s=2400, interval_s=60, distance_m=10000.0, serial=9101
        ),
    )
    _write_workout(
        tmp_path,
        "race.md",
        on=_E2E_RACE_ON,
        kind="race",
        distance=10000,
        time=2400,
        sources=[ref],
    )

    first = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])
    assert first.exit_code == 0, first.output
    profile_path = tmp_path / PROFILE_FILENAME
    bytes_after_first = profile_path.read_bytes()
    profile_after_first = load_profile(tmp_path)
    assert any(
        entry.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
        for entry in profile_after_first.benchmarks.entries
    )

    _write_workout(tmp_path, "race.md", on=_E2E_RACE_ON, kind=None, sources=[ref])

    second = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])
    assert second.exit_code == 0, second.output
    assert "Profile written: yes" in second.output
    bytes_after_second = profile_path.read_bytes()
    assert bytes_after_second != bytes_after_first
    profile_after_second = load_profile(tmp_path)
    assert not any(
        entry.kind is BenchmarkKind.THRESHOLD_PACE_S_PER_KM
        for entry in profile_after_second.benchmarks.entries
    )

    third = runner.invoke(app, ["derive-benchmarks", "--out", str(tmp_path)])
    assert third.exit_code == 0, third.output
    assert "Profile written: no" in third.output
    bytes_after_third = profile_path.read_bytes()
    assert bytes_after_third == bytes_after_second


def _write_two_document_root(root: Path, *, distance_m: float = 10000.0) -> None:
    """Write the race and time-trial documents every determinism test below
    shares into ``root``."""
    race_ref = _write_archive(
        root,
        _long_run_fit_bytes(
            duration_s=2400, interval_s=60, distance_m=distance_m, serial=9201
        ),
    )
    tt_ref = _write_archive(
        root,
        _power_ride_fit_bytes(
            duration_s=3300, interval_s=300, power_w=220, serial=9202
        ),
    )
    _write_workout(
        root,
        "a_race.md",
        on=_E2E_RACE_ON,
        kind="race",
        distance=10000,
        time=2400,
        sources=[race_ref],
    )
    _write_workout(root, "z_tt.md", on=_E2E_TT_ON, kind="race", sources=[tt_ref])


def test_discovery_order_perturbed_by_reversing_the_raw_glob_leaves_bytes_identical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The identical two-document root, discovered once in whatever raw
    order this filesystem's ``Path.glob`` happens to return and once with
    that same raw order reversed -- the sandboxed perturbation of "the
    order documents are discovered in" Req 9.1 names -- produces
    byte-identical ``athlete.toml``.

    Reversing the raw glob result directly (rather than relying on file
    creation order, which this filesystem's directory enumeration does not
    actually follow -- confirmed empirically before writing this test) is
    what makes the two runs' raw discovery orders provably different by
    construction, for exactly the two documents this fixture has. The
    positive control this test asserts before trusting the byte comparison:
    ``perturbed_calls`` records that the reversing branch of the patched
    ``glob`` actually ran exactly once against the perturbed invocation, and
    the baseline profile is confirmed (before it is deleted) to hold one
    entry from each document -- a run-discipline entry and a ride-discipline
    entry -- so the two documents genuinely land in different scope tables
    and order between them is an observable that could differ.

    Mutation tested: dropping `sorted()` from
    `fitdocs.performance.engine`'s own discovery glob, in isolation, does
    NOT redden this assertion -- confirmed by running it -- because
    `fitdocs.benchmarks.benchmarks_to_document` independently re-sorts every
    entry by `measured_on` before grouping it into scope/kind tables, so a
    perturbed *discovery* order for two documents at two different dates
    never reaches the write path as a different *table* order. Dropping
    that write-path date sort AS WELL (so nothing normalizes order anywhere)
    does redden it: the perturbed run's document sequence then drives which
    scope table (`run`/`ride`) is inserted first, changing the written
    bytes. This is disclosed rather than silently claimed: the isolated
    engine-level `sorted()` is redundant, not load-bearing, for this
    non-colliding two-document fixture, and the property Req 9.1 actually
    promises -- order-independent bytes -- holds through the write path's
    own normalization, which this test verifies directly.
    """
    root = tmp_path
    _write_two_document_root(root)

    baseline_result = runner.invoke(app, ["derive-benchmarks", "--out", str(root)])
    assert baseline_result.exit_code == 0, baseline_result.output
    baseline_bytes = (root / PROFILE_FILENAME).read_bytes()
    assert baseline_bytes != b""

    # Precondition for order to be observable at all: the baseline profile
    # holds an entry in BOTH scope tables the two documents populate. If
    # either table were empty there would be only one table to insert
    # first, and the byte comparison below would hold regardless of order.
    baseline_profile = load_profile(root)
    baseline_kinds = {entry.kind for entry in baseline_profile.benchmarks.entries}
    assert baseline_kinds & {
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        BenchmarkKind.LTHR_BPM,
    }
    assert BenchmarkKind.FTP_WATTS in baseline_kinds

    (root / PROFILE_FILENAME).unlink()

    workouts_dir = (root / "workouts").resolve()
    real_glob = Path.glob
    perturbed_calls: list[int] = []

    def reversed_glob(self: Path, pattern: str, *a: object, **k: object) -> list[Path]:
        results = list(real_glob(self, pattern, *a, **k))
        if self.resolve() == workouts_dir and pattern == "*.md":
            reversed_results = list(reversed(results))
            # Falsity in the starting state: with two distinct documents,
            # reversal is guaranteed to change the order, so the perturbed
            # run's raw discovery order is provably different from the
            # baseline's, not accidentally identical.
            assert reversed_results != results
            perturbed_calls.append(1)
            return reversed_results
        return results

    monkeypatch.setattr(Path, "glob", reversed_glob)

    perturbed_result = runner.invoke(app, ["derive-benchmarks", "--out", str(root)])

    # The reversing branch actually ran, exactly once, against the
    # perturbed invocation -- without this, an engine that never calls
    # `Path.glob("*.md")` against `workouts/` at all (e.g. an unsorted
    # `os.listdir` walk) would pass the byte comparison below vacuously.
    assert perturbed_calls == [1]

    assert perturbed_result.exit_code == 0, perturbed_result.output
    perturbed_bytes = (root / PROFILE_FILENAME).read_bytes()
    assert perturbed_bytes == baseline_bytes


def test_determinism_under_a_pinned_non_system_time_zone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same two-document fixture, run once under a pinned zone twelve
    hours behind UTC (``Etc/GMT+12``) and once under a pinned zone fourteen
    hours ahead (``Pacific/Kiritimati``) -- a 26-hour spread chosen so that
    the fixture's recorded FIT timestamp (``2021-09-08T01:46:40Z``) falls on
    a DIFFERENT local calendar date under the two zones (2021-09-07 under
    ``Etc/GMT+12``, 2021-09-08 under ``Pacific/Kiritimati``) -- produces
    byte-identical ``athlete.toml`` (Req 9.1's time-zone axis).

    In production, every entry's ``measured_on`` is read from the tagged
    page's own frontmatter date string (``fitdocs.contract.document_date``,
    ``date.fromisoformat``) and never from the activity's recorded start
    time or the wall clock (Req 7.6), so there is no naive local-time
    conversion on this path for a time-zone change to perturb -- confirmed
    directly, not merely reasoned about: temporarily changing
    ``measured_on=on`` to
    ``measured_on=activity.start_time.astimezone().date()`` in each of the
    three leaves in ``fitdocs.performance.derive`` DOES redden this
    assertion under the recorded FIT timestamp and zones above (the
    baseline run's entries land on 2021-09-07, the ``Pacific/Kiritimati``
    run's on 2021-09-08, producing different bytes), because Python's
    naive ``astimezone()`` resolves the system zone through ``time.tzset()``
    at call time, which does follow the ``TZ`` environment variable this
    test pins around each invocation. So this fixture is a working pin
    against exactly the regression Req 7.6 forbids, not only a determinism
    measurement.
    """
    baseline_root = tmp_path / "baseline"
    tz_root = tmp_path / "pinned-tz"
    baseline_root.mkdir()
    tz_root.mkdir()
    _write_two_document_root(baseline_root)
    _write_two_document_root(tz_root)

    monkeypatch.setenv("TZ", "Etc/GMT+12")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        baseline_result = runner.invoke(
            app, ["derive-benchmarks", "--out", str(baseline_root)]
        )
    finally:
        monkeypatch.delenv("TZ", raising=False)
        if hasattr(time, "tzset"):
            time.tzset()
    assert baseline_result.exit_code == 0, baseline_result.output

    monkeypatch.setenv("TZ", "Pacific/Kiritimati")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        tz_result = runner.invoke(app, ["derive-benchmarks", "--out", str(tz_root)])
    finally:
        monkeypatch.delenv("TZ", raising=False)
        if hasattr(time, "tzset"):
            time.tzset()

    assert tz_result.exit_code == 0, tz_result.output
    baseline_bytes = (baseline_root / PROFILE_FILENAME).read_bytes()
    tz_bytes = (tz_root / PROFILE_FILENAME).read_bytes()
    assert baseline_bytes != b""
    assert baseline_bytes == tz_bytes


def test_determinism_under_a_perturbed_numeric_locale(tmp_path: Path) -> None:
    """The same two-document fixture, run once under the ambient locale and
    once under a comma-decimal numeric locale (``de_DE.UTF-8``), produces
    byte-identical ``athlete.toml`` (Req 9.1's locale axis) -- a value
    formatted through one of Python's actually locale-sensitive paths
    (``format(x, "n")``, ``locale.str``, ``locale.format_string``, none of
    which this test's production code should ever reach -- an ordinary
    ``f"{x}"`` or ``str.format`` call never consults the C locale) would
    render its decimal point as a comma there and nowhere else.

    Skipped, naming the locale explicitly, when ``de_DE.UTF-8`` is not
    installed on the running machine -- never silently passed.
    """
    original = locale.setlocale(locale.LC_ALL)
    try:
        locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")
    except locale.Error:
        pytest.skip("locale 'de_DE.UTF-8' is not installed on this machine")
    finally:
        locale.setlocale(locale.LC_ALL, original)

    baseline_root = tmp_path / "baseline"
    locale_root = tmp_path / "perturbed-locale"
    baseline_root.mkdir()
    locale_root.mkdir()
    _write_two_document_root(baseline_root)
    _write_two_document_root(locale_root)

    baseline_result = runner.invoke(
        app, ["derive-benchmarks", "--out", str(baseline_root)]
    )
    assert baseline_result.exit_code == 0, baseline_result.output

    locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")
    try:
        locale_result = runner.invoke(
            app, ["derive-benchmarks", "--out", str(locale_root)]
        )
    finally:
        locale.setlocale(locale.LC_ALL, original)

    assert locale_result.exit_code == 0, locale_result.output
    baseline_bytes = (baseline_root / PROFILE_FILENAME).read_bytes()
    locale_bytes = (locale_root / PROFILE_FILENAME).read_bytes()
    assert baseline_bytes != b""
    assert baseline_bytes == locale_bytes
