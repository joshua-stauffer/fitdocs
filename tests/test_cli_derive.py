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
import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

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
