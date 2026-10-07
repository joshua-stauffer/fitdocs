"""CLI contract for the explicit analytics-index build/refresh command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.index import build
from fitdocs.index.bookkeeping import ComputedState
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.refresh import IndexReport, Outcome, RefreshResult
from fitdocs.index.schema import SCHEMA_VERSION
from fitdocs.metrics.types import AthleteInputs, TrimpWeighting, ZoneSpec
from tests.index._helpers import hold_index

runner = CliRunner()


def _set_roots(
    monkeypatch: pytest.MonkeyPatch, data_root: Path, index_base: Path
) -> None:
    monkeypatch.setenv("FITDOCS_DATA", str(data_root))
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_base))


def _fake_report(
    location: IndexLocation,
    outcome: Outcome,
    *,
    result: RefreshResult | None = None,
    detail: str | None = None,
    holder_pid: int | None = None,
) -> IndexReport:
    return IndexReport(outcome, location, detail, holder_pid, result)


def _fixed_report(report: IndexReport) -> Callable[..., IndexReport]:
    def run(*args: object, **kwargs: object) -> IndexReport:
        return report

    return run


def _table_count(output: str, label: str) -> int:
    for line in output.splitlines():
        cells = [cell.strip() for cell in line.split("│")]
        if len(cells) == 4 and cells[1] == label:
            return int(cells[2])
    raise AssertionError(f"missing {label!r} count in index table:\n{output}")


def _write_missing_source_pages(data_root: Path, count: int) -> None:
    workout_dir = data_root / "workouts"
    workout_dir.mkdir(parents=True)
    for number in range(count):
        sha = f"{number + 1:064x}"
        (workout_dir / f"missing-{number:03}.md").write_text(
            "---\n"
            "type: workout\n"
            "doc_version: 9\n"
            f"title: Missing source {number}\n"
            "date: 2026-10-06\n"
            "sport: running\n"
            "modality: run\n"
            f"sources:\n  - fit-archive/{sha}.fit\n"
            "---\n"
            "\n"
            "<!-- fitdocs:begin:notes -->\n"
            "Synthetic notes.\n"
            "<!-- fitdocs:end:notes -->\n"
            "\n"
            "<!-- fitdocs:begin:workout -->\n"
            "Synthetic workout.\n"
            "<!-- fitdocs:end:workout -->\n"
            "\n"
            "<!-- fitdocs:begin:load -->\n"
            "_Training load not computed._\n"
            "<!-- fitdocs:end:load -->\n",
            encoding="utf-8",
        )


def test_first_run_builds_and_second_run_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
) -> None:
    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    fallback_root = tmp_path / "different-fitdocs-data"
    monkeypatch.setenv("FITDOCS_DATA", str(fallback_root))
    assert not fallback_root.exists()

    first = runner.invoke(app, ["index", "--out", str(synced_corpus)])

    assert first.exit_code == 0, first.output
    assert "fitdocs index" in first.stdout
    assert "Pages held" in first.stdout
    assert "Added" in first.stdout
    assert "Index file:" in first.stdout
    assert f"Schema version: {SCHEMA_VERSION}" in first.stdout
    assert {
        label: _table_count(first.stdout, label)
        for label in (
            "Pages held",
            "Added",
            "Updated",
            "Removed",
            "Without computed values",
            "Left out",
            "Errors",
        )
    } == {
        "Pages held": 2,
        "Added": 2,
        "Updated": 0,
        "Removed": 0,
        "Without computed values": 0,
        "Left out": 0,
        "Errors": 0,
    }
    location = resolve_index_location(
        synced_corpus,
        {"FITDOCS_INDEX_DIR": str(index_base)},
        tmp_path / "home",
    )
    assert location.database.is_absolute()
    assert location.database.is_relative_to(index_base.resolve())
    assert location.database.exists()
    assert str(location.database) in first.stdout

    second = runner.invoke(app, ["index", "--out", str(synced_corpus)])

    assert second.exit_code == 0, second.output
    assert "UNCHANGED" in second.stdout
    assert "Pages held" in second.stdout
    assert "Index file:" in second.stdout
    assert f"Schema version: {SCHEMA_VERSION}" in second.stdout
    assert "Added" in second.stdout
    assert "Updated" in second.stdout
    assert "Removed" in second.stdout
    assert {
        label: _table_count(second.stdout, label)
        for label in ("Pages held", "Added", "Updated", "Removed")
    } == {"Pages held": 2, "Added": 0, "Updated": 0, "Removed": 0}

    rebuilt = runner.invoke(app, ["index", "--out", str(synced_corpus), "--rebuild"])
    assert rebuilt.exit_code == 0, rebuilt.output
    assert "Result" in rebuilt.stdout and "BUILT" in rebuilt.stdout
    assert "Rebuilt: rebuild requested" in rebuilt.stdout
    assert _table_count(rebuilt.stdout, "Pages held") == 2
    assert _table_count(rebuilt.stdout, "Added") == 2


def test_report_lists_without_computed_and_left_out_details_and_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
) -> None:
    from fitdocs.index.corpus import LeftOutPage

    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    location = resolve_index_location(
        synced_corpus, {"FITDOCS_INDEX_DIR": str(index_base)}, tmp_path / "home"
    )
    result = RefreshResult(
        added=("page-a", "page-b"),
        updated=("page-c",),
        removed=("page-d", "page-e"),
        without_computed=(
            ("workouts/missing.md", ComputedState.SOURCE_MISSING),
            ("workouts/unreadable.md", ComputedState.SOURCE_UNREADABLE),
            ("workouts/undecodable.md", ComputedState.SOURCE_UNDECODABLE),
        ),
        page_errors=(),
        producer_errors=(),
        left_out=(
            LeftOutPage(
                path="workouts/duplicate.md",
                reason="duplicate_base",
                collides_with="workouts/first.md",
                document_fingerprint="b" * 64,
            ),
            LeftOutPage(
                path="workouts/no-base.md",
                reason="no_base_reference",
                collides_with=None,
                document_fingerprint="c" * 64,
            ),
        ),
        corpus_refreshed=(),
        pages_held=4,
    )
    monkeypatch.setattr(
        build,
        "run_index_command",
        lambda *args, **kwargs: _fake_report(
            location, Outcome.REFRESHED, result=result
        ),
    )

    response = runner.invoke(app, ["index", "--out", str(synced_corpus)])

    assert response.exit_code == 0, response.output
    assert "workouts/missing.md: base file missing from the archive" in response.stdout
    assert "workouts/unreadable.md: base file could not be read" in response.stdout
    assert "workouts/undecodable.md: base file could not be decoded" in response.stdout
    assert (
        "workouts/duplicate.md: lists the same base file as "
        "workouts/first.md; not indexed" in response.stdout
    )
    assert "workouts/no-base.md: no archived base reference" in response.stdout
    assert "Errors" in response.stdout
    assert {
        label: _table_count(response.stdout, label)
        for label in (
            "Pages held",
            "Added",
            "Updated",
            "Removed",
            "Without computed values",
            "Left out",
            "Errors",
        )
    } == {
        "Pages held": 4,
        "Added": 2,
        "Updated": 1,
        "Removed": 2,
        "Without computed values": 3,
        "Left out": 2,
        "Errors": 0,
    }


def test_staged_and_page_and_producer_errors_exit_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
) -> None:
    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    location = resolve_index_location(
        synced_corpus, {"FITDOCS_INDEX_DIR": str(index_base)}, tmp_path / "home"
    )
    reports = (
        (
            _fake_report(location, Outcome.STAGED, detail="Permission denied"),
            ("STAGED", "Permission denied"),
            0,
        ),
        (
            _fake_report(
                location,
                Outcome.REFRESHED,
                result=RefreshResult(
                    (),
                    (),
                    (),
                    (),
                    (("workouts/a.md", "Synthetic page failure"),),
                    (),
                    (),
                    (),
                    1,
                ),
            ),
            ("Synthetic page failure",),
            1,
        ),
        (
            _fake_report(
                location,
                Outcome.REFRESHED,
                result=RefreshResult(
                    (),
                    (),
                    (),
                    (),
                    (),
                    (("test.producer", "Synthetic producer failure"),),
                    (),
                    (),
                    1,
                ),
            ),
            ("Synthetic producer failure",),
            1,
        ),
        (
            _fake_report(
                location,
                Outcome.REFRESHED,
                result=RefreshResult(
                    (),
                    (),
                    (),
                    (),
                    (
                        ("workouts/page-one.md", "PAGE error one"),
                        ("workouts/page-two.md", "PAGE error two"),
                    ),
                    (
                        ("producer.alpha", "PRODUCER error one"),
                        ("producer.beta", "PRODUCER error two"),
                        ("producer.gamma", "PRODUCER error three"),
                    ),
                    (),
                    (),
                    1,
                ),
            ),
            (
                "PAGE error one",
                "PAGE error two",
                "PRODUCER error one",
                "PRODUCER error two",
                "PRODUCER error three",
            ),
            5,
        ),
    )
    for report, details, error_count in reports:
        monkeypatch.setattr(build, "run_index_command", _fixed_report(report))
        response = runner.invoke(app, ["index", "--out", str(synced_corpus)])
        assert response.exit_code == 1, response.output
        assert _table_count(response.stdout, "Errors") == error_count
        for detail in details:
            assert detail in response.stdout
        if report.result is not None and len(report.result.page_errors) == 1:
            assert "Could not index workouts/a.md: Synthetic page failure" in (
                response.stdout
            )
        if report.result is not None and report.result.producer_errors:
            for producer_name, message in report.result.producer_errors:
                expected_line = f"Could not refresh {producer_name}: {message}"
                assert expected_line in response.stdout
        if report.result is not None and len(report.result.page_errors) == 2:
            assert "Could not index workouts/page-one.md: PAGE error one" in (
                response.stdout
            )
            assert "Could not index workouts/page-two.md: PAGE error two" in (
                response.stdout
            )
        if report.result is not None and len(report.result.producer_errors) == 3:
            assert "Could not refresh producer.alpha: PRODUCER error one" in (
                response.stdout
            )
            assert "Could not refresh producer.beta: PRODUCER error two" in (
                response.stdout
            )
            assert "Could not refresh producer.gamma: PRODUCER error three" in (
                response.stdout
            )


@pytest.mark.parametrize(
    ("outcome", "error_kind", "expected_exit", "expected_error_count"),
    [
        (outcome, error_kind, 0 if error_kind is None else 1, count)
        for outcome in (Outcome.BUILT, Outcome.REFRESHED, Outcome.UNCHANGED)
        for error_kind, count in (
            (None, 0),
            ("page", 1),
            ("producer", 1),
            ("both", 5),
        )
    ],
    ids=(
        "built-no-errors",
        "built-page-error",
        "built-producer-error",
        "built-both-errors",
        "refreshed-no-errors",
        "refreshed-page-error",
        "refreshed-producer-error",
        "refreshed-both-errors",
        "unchanged-no-errors",
        "unchanged-page-error",
        "unchanged-producer-error",
        "unchanged-both-errors",
    ),
)
def test_success_outcomes_with_page_or_producer_errors_exit_correctly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
    outcome: Outcome,
    error_kind: str | None,
    expected_exit: int,
    expected_error_count: int,
) -> None:
    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    location = resolve_index_location(
        synced_corpus, {"FITDOCS_INDEX_DIR": str(index_base)}, tmp_path / "home"
    )
    page_errors = (
        (
            ("workouts/page-unique.md", "PAGE sentinel"),
            ("workouts/page-second.md", "PAGE second sentinel"),
        )
        if error_kind == "both"
        else (("workouts/page-unique.md", "PAGE sentinel"),)
        if error_kind in {"page", "both"}
        else ()
    )
    producer_errors = (
        (
            ("producer.unique", "PRODUCER sentinel"),
            ("producer.second", "PRODUCER second sentinel"),
            ("producer.third", "PRODUCER third sentinel"),
        )
        if error_kind == "both"
        else (("producer.unique", "PRODUCER sentinel"),)
        if error_kind in {"producer", "both"}
        else ()
    )
    result = RefreshResult(
        (),
        (),
        (),
        (("workouts/missing.md", ComputedState.SOURCE_MISSING),),
        page_errors,
        producer_errors,
        (),
        (),
        1,
    )
    report = _fake_report(location, outcome, result=result)
    monkeypatch.setattr(build, "run_index_command", _fixed_report(report))

    response = runner.invoke(app, ["index", "--out", str(synced_corpus)])

    assert response.exit_code == expected_exit, response.output
    assert _table_count(response.stdout, "Errors") == expected_error_count
    assert "workouts/missing.md: base file missing from the archive" in response.stdout


@pytest.mark.parametrize(
    ("outcome", "detail", "holder_pid", "expected"),
    [
        (Outcome.NEEDS_REBUILD, "schema 99", None, "Rebuilt: schema 99"),
        (Outcome.BUSY, None, None, "Index is busy; close the other writer"),
        (
            Outcome.FAILED,
            "synthetic open error",
            None,
            "Index failed: synthetic open error",
        ),
        (Outcome.NOT_BUILT, None, None, "Index is not built."),
    ],
)
def test_non_success_report_outcomes_include_their_remedy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
    outcome: Outcome,
    detail: str | None,
    holder_pid: int | None,
    expected: str,
) -> None:
    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    location = resolve_index_location(
        synced_corpus, {"FITDOCS_INDEX_DIR": str(index_base)}, tmp_path / "home"
    )
    report = _fake_report(
        location,
        outcome,
        detail=detail,
        holder_pid=holder_pid,
    )
    monkeypatch.setattr(build, "run_index_command", _fixed_report(report))

    response = runner.invoke(app, ["index", "--out", str(synced_corpus)])

    assert response.exit_code == 1, response.output
    assert expected in response.stdout


def test_duplicate_and_missing_source_details_from_real_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
) -> None:
    from fitdocs.contract import is_workout_document, source_refs
    from fitdocs.docio import read_frontmatter
    from fitdocs.layout import WORKOUTS_DIR

    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    pages = sorted(
        path
        for path in (synced_corpus / WORKOUTS_DIR).glob("*.md")
        if is_workout_document(read_frontmatter(path))
    )
    assert len(pages) == 2
    single_source_page = next(
        page for page in pages if len(source_refs(read_frontmatter(page) or {})) == 1
    )
    missing_ref = source_refs(read_frontmatter(single_source_page) or {})[-1]
    missing_base = synced_corpus / missing_ref
    assert missing_base.is_file()
    missing_base.unlink()

    duplicate_source_page = next(page for page in pages if page != single_source_page)
    duplicate = duplicate_source_page.with_name("000-duplicate.md")
    duplicate.write_bytes(duplicate_source_page.read_bytes())
    assert duplicate != duplicate_source_page

    response = runner.invoke(app, ["index", "--out", str(synced_corpus)])

    assert response.exit_code == 0, response.output
    assert (
        f"{single_source_page.relative_to(synced_corpus).as_posix()}: "
        "base file missing from the archive"
    ) in response.stdout
    assert (
        f"{duplicate_source_page.relative_to(synced_corpus).as_posix()}: "
        "lists the same base file as workouts/000-duplicate.md; not indexed"
    ) in response.stdout


def test_duckdb_writer_lock_reports_holder_pid_and_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
) -> None:
    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    built = runner.invoke(app, ["index", "--out", str(synced_corpus)])
    assert built.exit_code == 0, built.output
    location = resolve_index_location(
        synced_corpus, {"FITDOCS_INDEX_DIR": str(index_base)}, tmp_path / "home"
    )

    with hold_index(location.database, read_only=False) as holder_pid:
        response = runner.invoke(app, ["index", "--out", str(synced_corpus)])
        assert response.exit_code == 1
        assert f"process {holder_pid}" in response.stdout
        assert "close it" in response.stdout


def test_configuration_failures_exit_two_without_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    index_base = tmp_path / "index-cache"
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_base))
    monkeypatch.setenv("FITDOCS_DATA", str(data_root))

    relative = runner.invoke(
        app,
        ["index", "--out", str(data_root)],
        env={"FITDOCS_INDEX_DIR": "relative-index"},
    )
    assert relative.exit_code == 2
    assert "FITDOCS_INDEX_DIR" in relative.stderr
    assert not index_base.exists()

    (data_root / "athlete.toml").write_text("[athlete\n", encoding="utf-8")
    malformed = runner.invoke(app, ["index", "--out", str(data_root)])
    assert malformed.exit_code == 2
    assert "athlete" in malformed.stderr.lower()
    assert not index_base.exists()

    missing_root = runner.invoke(app, ["index", "--out", str(tmp_path / "absent")])
    assert missing_root.exit_code == 2
    assert "does not exist" in missing_root.stderr.lower()
    assert not index_base.exists()


@pytest.mark.parametrize("page_count", [100, 101])
def test_progress_callback_threshold_is_reported_only_on_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    page_count: int,
) -> None:
    data_root = tmp_path / "data"
    _write_missing_source_pages(data_root, page_count)
    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, data_root, index_base)
    response = runner.invoke(app, ["index", "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    if page_count == 101:
        assert "Indexing:" not in response.stdout
        assert response.stderr.count("Indexing:") == 2
        assert "Indexing: 100/101 pages" in response.stderr
        assert "Indexing: 101/101 pages" in response.stderr
    else:
        assert "Indexing:" not in response.stderr
    assert "Indexing:" not in response.stdout


def test_module_docstring_describes_command_count_and_exit_behavior() -> None:
    import fitdocs.cli as cli_module

    doc = cli_module.__doc__ or ""
    assert "Thirteen" in doc[:400]
    normalized = " ".join(doc.split())
    command_list = normalized.split("Two further commands", maxsplit=1)[0]
    assert "* ``fitdocs index [--out PATH] [--rebuild]``" in command_list
    assert (
        "fitdocs index`` exits 0 when it is current, 1 when it cannot be "
        "brought current, and 2 for invalid configuration"
    ) in normalized
    assert "post-pass never changes another command's exit code" in normalized


def test_index_help_lists_rebuild() -> None:
    response = runner.invoke(app, ["index", "--help"])

    assert response.exit_code == 0
    assert "--rebuild" in response.stdout
    assert "--rebuild-force" not in response.stdout


def test_index_command_passes_its_resolved_context_to_the_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    synced_corpus: Path,
) -> None:
    import os
    from datetime import date

    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, synced_corpus, index_base)
    profile = AthleteInputs(
        ftp_watts=287.5,
        resting_hr_bpm=42,
        max_hr_bpm=193,
        hr_zones=ZoneSpec((101.0, 129.0, 158.0)),
        power_zones=ZoneSpec((117.5, 188.0, 253.25)),
        pace_zones=ZoneSpec((247.0, 331.5, 496.0)),
        trimp_weighting=TrimpWeighting.BANISTER_FEMALE,
    )
    expected_profile = AthleteInputs(
        ftp_watts=287.5,
        resting_hr_bpm=42,
        max_hr_bpm=193,
        hr_zones=ZoneSpec((101.0, 129.0, 158.0)),
        power_zones=ZoneSpec((117.5, 188.0, 253.25)),
        pace_zones=ZoneSpec((247.0, 331.5, 496.0)),
        trimp_weighting=TrimpWeighting.BANISTER_FEMALE,
    )
    expected_home = tmp_path / "home"
    expected_today = date(2026, 9, 7)
    location = resolve_index_location(
        synced_corpus, {"FITDOCS_INDEX_DIR": str(index_base)}, expected_home
    )
    captured: dict[str, object] = {}

    def capture_runner(*args: object, **kwargs: object) -> IndexReport:
        captured["args"] = args
        captured.update(kwargs)
        return _fake_report(location, Outcome.UNCHANGED)

    monkeypatch.setattr(build, "run_index_command", capture_runner)
    monkeypatch.setattr(cli_module, "load_athlete_inputs", lambda root: profile)
    monkeypatch.setattr(Path, "home", lambda: expected_home)
    monkeypatch.setattr(cli_module, "_today", lambda: expected_today)

    response = runner.invoke(app, ["index", "--out", str(synced_corpus), "--rebuild"])

    assert response.exit_code == 0, response.output
    assert captured["args"] == (synced_corpus,)
    assert captured["environ"] is os.environ
    assert captured["home"] == expected_home
    assert captured["today"] == expected_today
    assert captured["rebuild"] is True
    athlete = captured["athlete"]
    assert isinstance(athlete, AthleteInputs)
    assert athlete is profile
    assert athlete == expected_profile
    assert callable(captured["progress"])


def test_index_passes_the_profile_read_from_athlete_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "athlete.toml").write_text(
        "ftp_watts = 312.5\n"
        "resting_hr_bpm = 44\n"
        "max_hr_bpm = 188\n"
        "hr_zones = [100, 131, 162]\n"
        "power_zones = [120.5, 190.0, 251.25]\n"
        "pace_zones = [248.0, 333.5, 501.0]\n",
        encoding="utf-8",
    )
    index_base = tmp_path / "index-cache"
    _set_roots(monkeypatch, data_root, index_base)
    expected = AthleteInputs(
        ftp_watts=312.5,
        resting_hr_bpm=44,
        max_hr_bpm=188,
        hr_zones=ZoneSpec((100.0, 131.0, 162.0)),
        power_zones=ZoneSpec((120.5, 190.0, 251.25)),
        pace_zones=ZoneSpec((248.0, 333.5, 501.0)),
        trimp_weighting=None,
    )
    location = resolve_index_location(
        data_root, {"FITDOCS_INDEX_DIR": str(index_base)}, tmp_path / "home"
    )
    captured: dict[str, object] = {}

    def capture_runner(*args: object, **kwargs: object) -> IndexReport:
        captured["athlete"] = kwargs["athlete"]
        return _fake_report(location, Outcome.UNCHANGED)

    monkeypatch.setattr(build, "run_index_command", capture_runner)

    response = runner.invoke(app, ["index", "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    athlete = captured["athlete"]
    assert isinstance(athlete, AthleteInputs)
    assert athlete == expected
