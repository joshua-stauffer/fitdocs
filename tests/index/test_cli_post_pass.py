"""Analytics-index refresh integration after writing CLI commands."""

from __future__ import annotations

import hashlib
import inspect
import os
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import cast, get_type_hints

import pytest
from rich.console import Console
from typer.testing import CliRunner

from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs import cli as cli_module
from fitdocs.cli import app
from fitdocs.index import derive, registry
from fitdocs.index import refresh as refresh_module
from fitdocs.index.bookkeeping import ComputedState
from fitdocs.index.derive import Derived
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.location import resolve_index_location
from fitdocs.index.producer import CorpusSnapshot, Rows
from fitdocs.index.refresh import IndexReport, Outcome, ProgressCallback, RefreshResult
from fitdocs.index.schema import TableSpec
from fitdocs.load import registry as load_registry
from fitdocs.load.types import (
    Computed,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
)
from fitdocs.metrics.types import AthleteInputs
from fitdocs.plugins import PluginLoadError, PluginReport
from tests.fixtures import builder
from tests.index._helpers import hold_index

runner = CliRunner()


@contextmanager
def _track_derivations(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[object]]:
    calls: list[object] = []
    original = derive.derive_page

    def spy(
        data_root: Path, sources: Sequence[str], athlete: AthleteInputs | None
    ) -> Derived | ComputedState:
        calls.append((data_root, sources, athlete))
        return original(data_root, sources, athlete)

    with monkeypatch.context() as owned:
        owned.setattr(derive, "derive_page", spy)
        yield calls
    assert derive.derive_page is original


@contextmanager
def _ordered_plan_and_plugin(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    original_plan = cli_module._run_plan_pass
    original_plugins = cli_module._plugin_report
    errors = PluginReport((), (PluginLoadError("ordered-plugin", "load failed"),))

    def plan(_root: Path, *, today: date, chained: bool) -> SimpleNamespace:
        Console().print("Reconciled: ordered plan")
        return SimpleNamespace(failed=False)

    with monkeypatch.context() as owned:
        owned.setattr(cli_module, "_run_plan_pass", plan)
        owned.setattr(cli_module, "_plugin_report", lambda _root: errors)
        yield
    assert cli_module._run_plan_pass is original_plan
    assert cli_module._plugin_report is original_plugins


class _IndexLoadCalculator:
    supported_modalities = frozenset({Modality.RUN})

    def __init__(self, calculator_id: str, value: float) -> None:
        self.calculator_id = calculator_id
        self.display_name = calculator_id
        self.value = value

    def required_athlete_fields(self) -> tuple[()]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return Computed(
            LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=self.value,
                basis=f"value {self.value}",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


class _RaisingCorpusProducer:
    name = "synthetic.failure"
    tables: tuple[TableSpec, ...] = ()

    def fingerprint(self, _corpus: CorpusSnapshot) -> str:
        return "synthetic-corpus-fingerprint"

    def rows(self, _corpus: CorpusSnapshot) -> Rows:
        raise RuntimeError("synthetic producer failure")


def _seed_indexed_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "initial-source"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )
    initial = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert initial.exit_code == 0, initial.output
    built = runner.invoke(app, ["index", "--out", str(data_root)])
    assert built.exit_code == 0, built.output
    return data_root


def _workout_pages(data_root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in (data_root / "workouts").glob("*.md")
            if path.name != "AGENTS.md"
        )
    )


def test_sync_reports_an_unbuilt_index_after_writing_the_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )

    response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert "Index: not built; run 'fitdocs index' to build it." in response.output
    assert len(_workout_pages(data_root)) == 1


def test_sync_refreshes_after_the_load_report_and_consumes_rendered_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    source = tmp_path / "new-source"
    source.mkdir()
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())
    errors = PluginReport((), (PluginLoadError("synthetic-plugin", "load failed"),))

    def fake_plan(_root: Path, *, today: date, chained: bool) -> SimpleNamespace:
        Console().print("Reconciled: synthetic plan row")
        return SimpleNamespace(failed=False)

    original_plan = cli_module._run_plan_pass
    original_plugins = cli_module._plugin_report
    with monkeypatch.context() as owned:
        owned.setattr(cli_module, "_run_plan_pass", fake_plan)
        owned.setattr(cli_module, "_plugin_report", lambda _root: errors)
        with _track_derivations(monkeypatch) as derived:
            response = runner.invoke(
                app, ["sync", str(source), "--out", str(data_root)]
            )

    assert response.exit_code == 0, response.output
    assert "Index: 1 added, 0 updated, 0 removed." in response.output
    assert response.output.index("fitdocs load") < response.output.index(
        "Index: 1 added"
    )
    assert response.output.index("Index: 1 added") < response.output.index(
        "Plugin errors:"
    )
    assert response.output.index(
        "Reconciled: synthetic plan row"
    ) < response.output.index("Index: 1 added")
    assert "synthetic-plugin" in response.output
    assert len(_workout_pages(data_root)) == 2
    assert derived == []
    assert cli_module._run_plan_pass is original_plan
    assert cli_module._plugin_report is original_plugins


def test_drain_refreshes_after_the_load_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n", encoding="utf-8"
    )
    inbox = data_root / "inbox"
    inbox.mkdir()
    (inbox / "ride.fit").write_bytes(builder.ride_fit_bytes())
    with (
        _ordered_plan_and_plugin(monkeypatch),
        _track_derivations(monkeypatch) as derived,
    ):
        response = runner.invoke(app, ["sync", "--no-prompt", "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert "Index: 1 added, 0 updated, 0 removed." in response.output
    assert response.output.index("fitdocs load") < response.output.index(
        "Index: 1 added"
    )
    assert response.output.index("Reconciled: ordered plan") < response.output.index(
        "Index: 1 added"
    )
    assert response.output.index("Index: 1 added") < response.output.index(
        "Plugin errors:"
    )
    assert len(_workout_pages(data_root)) == 2
    assert derived == []


def test_pull_sync_refreshes_after_the_chained_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    source = tmp_path / "folder-source"
    source.mkdir()
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n\n"
        "[connectors.folder-src]\n"
        'connector = "folder"\n'
        f'path = "{source.as_posix()}"\n'
        "settle_seconds = 0\n",
        encoding="utf-8",
    )
    with (
        _ordered_plan_and_plugin(monkeypatch),
        _track_derivations(monkeypatch) as derived,
    ):
        response = runner.invoke(
            app,
            ["pull", "--sync", "--no-prompt", "--out", str(data_root)],
        )

    assert response.exit_code == 0, response.output
    assert (data_root / "inbox" / "folder-src" / "ride.fit").is_file()
    assert "Index: 1 added, 0 updated, 0 removed." in response.output
    assert response.output.index("fitdocs load") < response.output.index(
        "Index: 1 added"
    )
    assert response.output.index("Reconciled: ordered plan") < response.output.index(
        "Index: 1 added"
    )
    assert response.output.index("Index: 1 added") < response.output.index(
        "Plugin errors:"
    )
    assert len(_workout_pages(data_root)) == 2
    assert derived == []


def test_regen_refreshes_after_the_load_report_and_uses_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    additional_fit = builder.ride_fit_bytes()
    archive_path = (
        data_root / "fit-archive" / f"{hashlib.sha256(additional_fit).hexdigest()}.fit"
    )
    assert not archive_path.exists()
    archive_path.write_bytes(additional_fit)
    assert archive_path.read_bytes() == additional_fit
    with (
        _ordered_plan_and_plugin(monkeypatch),
        _track_derivations(monkeypatch) as derived,
    ):
        response = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert "Index: 1 added, 0 updated, 0 removed." in response.output
    assert response.output.index("fitdocs load") < response.output.index(
        "Index: 1 added"
    )
    assert response.output.index("Reconciled: ordered plan") < response.output.index(
        "Index: 1 added"
    )
    assert response.output.index("Index: 1 added") < response.output.index(
        "Plugin errors:"
    )
    assert len(_workout_pages(data_root)) == 2
    assert derived == []


def test_load_alone_updates_document_rows_without_deriving_archives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _IndexLoadCalculator("index-load-a", 11.25)
    second = _IndexLoadCalculator("index-load-b", 29.5)
    load_registry.register(first)
    load_registry.register(second)
    try:
        data_root = tmp_path / "data"
        data_root.mkdir()
        source = tmp_path / "source"
        source.mkdir()
        (source / "run.fit").write_bytes(builder.run_fit_bytes())
        (data_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "index-load-a"\n', encoding="utf-8"
        )
        monkeypatch.setattr(
            "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
        )
        initial = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert initial.exit_code == 0, initial.output
        built = runner.invoke(app, ["index", "--out", str(data_root)])
        assert built.exit_code == 0, built.output
        from fitdocs.docio import read_frontmatter

        (page,) = _workout_pages(data_root)
        prior_frontmatter = read_frontmatter(page)
        assert prior_frontmatter is not None
        assert prior_frontmatter["load_methodology"] == "index-load-a"
        (data_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "index-load-b"\n', encoding="utf-8"
        )
        handoffs: list[object] = []
        original_refresh = refresh_module.refresh_after_command
        original_plugins = cli_module._plugin_report
        plugin_errors = PluginReport(
            (), (PluginLoadError("load-plugin", "load failed"),)
        )

        def spy_refresh(
            data_root: Path,
            *,
            environ: Mapping[str, str],
            home: Path,
            handoff: HandoffCollector | None,
            today: date,
            progress: ProgressCallback | None,
        ) -> IndexReport:
            handoffs.append(handoff)
            return original_refresh(
                data_root,
                environ=environ,
                home=home,
                handoff=handoff,
                today=today,
                progress=progress,
            )

        with monkeypatch.context() as owned:
            owned.setattr(refresh_module, "refresh_after_command", spy_refresh)
            owned.setattr(cli_module, "_plugin_report", lambda _root: plugin_errors)
            with _track_derivations(monkeypatch) as derived:
                response = runner.invoke(
                    app, ["load", "--out", str(data_root), "--recompute"]
                )

        assert response.exit_code == 0, response.output
        updated_frontmatter = read_frontmatter(page)
        assert updated_frontmatter is not None
        assert updated_frontmatter["load_methodology"] == "index-load-b"
        assert "Index: 0 added, 1 updated, 0 removed." in response.output
        assert response.output.index("fitdocs load") < response.output.index(
            "Index: 0 added"
        )
        assert response.output.index("Index: 0 added") < response.output.index(
            "Plugin errors:"
        )
        assert derived == []
        assert handoffs == [None]
        assert refresh_module.refresh_after_command is original_refresh
        assert cli_module._plugin_report is original_plugins
    finally:
        load_registry.unregister(first.calculator_id)
        load_registry.unregister(second.calculator_id)


def test_unchanged_report_still_prints_page_and_producer_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n", encoding="utf-8"
    )
    result = RefreshResult(
        added=(),
        updated=(),
        removed=(),
        without_computed=(),
        page_errors=(("workouts/page.md", "synthetic page detail"),),
        producer_errors=(("synthetic.producer", "synthetic producer detail"),),
        left_out=(),
        corpus_refreshed=(),
        pages_held=0,
    )
    location = resolve_index_location(data_root, {}, tmp_path / "home")
    original_refresh = refresh_module.refresh_after_command
    with monkeypatch.context() as owned:
        owned.setattr(
            refresh_module,
            "refresh_after_command",
            lambda *args, **kwargs: IndexReport(
                Outcome.UNCHANGED, location, None, None, result
            ),
        )
        response = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert refresh_module.refresh_after_command is original_refresh

    assert response.exit_code == 0, response.output
    assert (
        "Index: could not index workouts/page.md: synthetic page detail"
        in response.output
    )
    assert (
        "Index: could not refresh synthetic.producer: synthetic producer detail"
        in response.output
    )
    assert "Index: 0 added" not in response.output


@pytest.mark.parametrize(
    ("corpus_refreshed", "pages_held"),
    [((), 0), (("core.corpus",), 3)],
)
def test_refreshed_corpus_or_meta_only_result_has_no_page_summary(
    corpus_refreshed: tuple[str, ...],
    pages_held: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = RefreshResult(
        added=(),
        updated=(),
        removed=(),
        without_computed=(),
        page_errors=(),
        producer_errors=(),
        left_out=(),
        corpus_refreshed=corpus_refreshed,
        pages_held=pages_held,
    )
    cli_module._report_index_pass(
        IndexReport(Outcome.REFRESHED, None, None, None, result)
    )

    assert capsys.readouterr().out == ""


def test_refreshed_corpus_only_still_reports_producer_errors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = RefreshResult(
        added=(),
        updated=(),
        removed=(),
        without_computed=(),
        page_errors=(),
        producer_errors=(("corpus.synthetic", "write failed"),),
        left_out=(),
        corpus_refreshed=("core.corpus",),
        pages_held=2,
    )

    cli_module._report_index_pass(
        IndexReport(Outcome.REFRESHED, None, None, None, result)
    )

    assert capsys.readouterr().out.strip() == (
        "Index: could not refresh corpus.synthetic: write failed"
    )


def test_refreshed_report_counts_distinct_added_updated_and_removed_pages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = RefreshResult(
        added=("workouts/added-a.md", "workouts/added-b.md"),
        updated=(
            "workouts/updated-a.md",
            "workouts/updated-b.md",
            "workouts/updated-c.md",
        ),
        removed=(
            "workouts/removed-a.md",
            "workouts/removed-b.md",
            "workouts/removed-c.md",
            "workouts/removed-d.md",
        ),
        without_computed=(),
        page_errors=(),
        producer_errors=(),
        left_out=(),
        corpus_refreshed=(),
        pages_held=0,
    )

    cli_module._report_index_pass(
        IndexReport(Outcome.REFRESHED, None, None, None, result)
    )

    assert capsys.readouterr().out.strip() == ("Index: 2 added, 3 updated, 4 removed.")


def test_index_wrapper_contract_progress_callback_and_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    signature = inspect.signature(cli_module._run_index_pass)
    assert tuple(signature.parameters) == ("data_root", "handoff")
    assert signature.parameters["handoff"].kind is inspect.Parameter.KEYWORD_ONLY
    assert get_type_hints(
        cli_module._run_index_pass,
        globalns={"Path": Path, "HandoffCollector": HandoffCollector},
    ) == {
        "data_root": Path,
        "handoff": HandoffCollector | None,
        "return": type(None),
    }

    progress_calls: list[tuple[int, int]] = []

    def progress(done: int, total: int) -> None:
        progress_calls.append((done, total))
        Console(stderr=True, markup=False, highlight=False, soft_wrap=True).print(
            f"Indexing: {done}/{total} pages"
        )

    observed: list[ProgressCallback | None] = []
    original_refresh = refresh_module.refresh_after_command
    original_progress = cli_module._index_progress

    def healthy_refresh(
        _root: Path,
        *,
        environ: Mapping[str, str],
        home: Path,
        handoff: HandoffCollector | None,
        today: date,
        progress: ProgressCallback | None,
    ) -> IndexReport:
        observed.append(progress)
        assert progress is not None
        progress(100, 101)
        return IndexReport(Outcome.UNCHANGED, None, None, None, None)

    with monkeypatch.context() as owned:
        owned.setattr(cli_module, "_index_progress", lambda: progress)
        owned.setattr(refresh_module, "refresh_after_command", healthy_refresh)
        run_pass = cast(Callable[..., object], cli_module._run_index_pass)
        returned = run_pass(Path("synthetic-root"), handoff=None)
    assert cli_module._index_progress is original_progress
    assert refresh_module.refresh_after_command is original_refresh
    assert observed == [progress]
    assert returned is None
    assert progress_calls == [(100, 101)]
    assert capsys.readouterr().err.strip() == "Indexing: 100/101 pages"

    interrupt = KeyboardInterrupt("preserve identity")

    def interrupted(
        _root: Path,
        *,
        environ: Mapping[str, str],
        home: Path,
        handoff: HandoffCollector | None,
        today: date,
        progress: ProgressCallback | None,
    ) -> IndexReport:
        raise interrupt

    with monkeypatch.context() as owned:
        owned.setattr(refresh_module, "refresh_after_command", interrupted)
        with pytest.raises(KeyboardInterrupt) as raised:
            cli_module._run_index_pass(Path("synthetic-root"), handoff=None)
    assert raised.value is interrupt
    assert refresh_module.refresh_after_command is original_refresh


def test_raising_corpus_producer_is_reported_without_changing_sync_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    source = tmp_path / "empty-source"
    source.mkdir()
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (_RaisingCorpusProducer(),))

    response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert (
        "Index: could not refresh synthetic.failure: RuntimeError: "
        "synthetic producer failure" in response.output
    )


def test_corrupt_index_is_reported_without_changing_sync_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    location = resolve_index_location(data_root, os.environ, tmp_path / "home")
    location.database.write_bytes(b"synthetic corrupt index bytes")
    corrupted = location.database.read_bytes()
    source = tmp_path / "new-source"
    source.mkdir()
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())

    response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert len(_workout_pages(data_root)) == 2
    assert location.database.read_bytes() == corrupted
    assert "Index: " in response.output
    assert "run 'fitdocs index' to rebuild it." in response.output


def test_held_database_lock_is_reported_without_changing_sync_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    location = resolve_index_location(data_root, os.environ, tmp_path / "home")
    source = tmp_path / "new-source"
    source.mkdir()
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())

    with hold_index(location.database, read_only=False) as holder_pid:
        response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert response.exit_code == 0, response.output
        assert len(_workout_pages(data_root)) == 2
        assert (
            "Index: not refreshed; it is open in another program "
            f"(process {holder_pid}). Close it;"
        ) in response.output


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        (
            "writer lock is held for /synthetic/index.lock",
            "Index: not refreshed; another fitdocs command is writing it. "
            "The next writing command or 'fitdocs index' will catch up.",
        ),
        (
            "database is locked",
            "Index: not refreshed; it is open in another program. Close it; "
            "the next writing command or 'fitdocs index' will catch up.",
        ),
    ],
)
def test_busy_report_without_pid_uses_the_matching_message(
    detail: str, expected: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_module._report_index_pass(IndexReport(Outcome.BUSY, None, detail, None, None))

    assert capsys.readouterr().out.strip() == expected


def test_needs_rebuild_report_includes_reason_and_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_module._report_index_pass(
        IndexReport(
            Outcome.NEEDS_REBUILD, None, "synthetic schema mismatch", None, None
        )
    )

    assert capsys.readouterr().out.strip() == (
        "Index: synthetic schema mismatch; run 'fitdocs index' to rebuild it."
    )


def test_refused_index_location_does_not_change_sync_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    source = tmp_path / "new-source"
    source.mkdir()
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())
    forbidden_index_base = data_root / "inside"
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(forbidden_index_base))

    response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert len(_workout_pages(data_root)) == 2
    assert not forbidden_index_base.exists()
    assert "Index: not refreshed;" in response.output


def test_sync_file_failure_keeps_the_original_failure_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    source = tmp_path / "bad-source"
    source.mkdir()
    (source / "bad.fit").write_bytes(builder.non_fit_bytes())

    response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert response.exit_code == 1, response.output
    assert "bad.fit" in response.output
    assert "Index:" not in response.output


def test_unchanged_refresh_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    source = tmp_path / "empty-source"
    source.mkdir()

    response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert "Index:" not in response.output


def test_index_failure_does_not_change_sync_exit_or_skip_written_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _seed_indexed_run(tmp_path, monkeypatch)
    location = resolve_index_location(data_root, os.environ, tmp_path / "home")
    location.database.write_bytes(b"synthetic corrupt index bytes")
    corrupted = location.database.read_bytes()
    source = tmp_path / "new-source"
    source.mkdir()
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())

    response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert response.exit_code == 0, response.output
    assert len(_workout_pages(data_root)) == 2
    assert location.database.read_bytes() == corrupted
    assert (
        "Index: " in response.output
        and "run 'fitdocs index' to rebuild it." in response.output
    )


@pytest.mark.parametrize("entrypoint", ["sync", "drain", "pull-sync", "regen", "load"])
def test_post_pass_failure_never_changes_writing_command_exit_code(
    entrypoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n", encoding="utf-8"
    )
    source = tmp_path / "source"
    source.mkdir()
    if entrypoint == "sync":
        args = ["sync", str(source), "--out", str(data_root)]
    elif entrypoint == "drain":
        args = ["sync", "--no-prompt", "--out", str(data_root)]
    elif entrypoint == "pull-sync":
        args = ["pull", "--sync", "--no-prompt", "--out", str(data_root)]
    elif entrypoint == "regen":
        args = ["regen", "--out", str(data_root)]
    else:
        args = ["load", "--out", str(data_root)]
    location = resolve_index_location(data_root, {}, tmp_path / "home")
    fixed_today = date(2031, 4, 5)
    synthetic_home = tmp_path / "home"
    monkeypatch.setattr(cli_module, "_today", lambda: fixed_today)
    monkeypatch.setattr(Path, "home", lambda: synthetic_home)
    calls: list[
        tuple[
            Path,
            Mapping[str, str],
            Path,
            HandoffCollector | None,
            date,
            ProgressCallback | None,
        ]
    ] = []

    def failed_refresh(
        data_root_arg: Path,
        *,
        environ: Mapping[str, str],
        home: Path,
        handoff: HandoffCollector | None,
        today: date,
        progress: ProgressCallback | None,
    ) -> IndexReport:
        calls.append((data_root_arg, environ, home, handoff, today, progress))
        return IndexReport(
            Outcome.FAILED, location, "synthetic refresh failure", None, None
        )

    original_refresh = refresh_module.refresh_after_command
    with monkeypatch.context() as owned:
        owned.setattr(refresh_module, "refresh_after_command", failed_refresh)
        response = runner.invoke(app, args)
    assert refresh_module.refresh_after_command is original_refresh

    assert response.exit_code == 0, response.output
    assert len(calls) == 1
    data_root_arg, environ, home, handoff, today, progress = calls[0]
    assert data_root_arg == data_root
    assert environ is os.environ
    assert home == synthetic_home
    assert (handoff is None) is (entrypoint == "load")
    assert today == fixed_today
    assert progress is not None
    assert "Index: not refreshed; synthetic refresh failure." in response.output


def test_unexpected_refresh_exception_is_reported_without_raising_to_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "source"
    source.mkdir()

    def raise_refresh(
        _data_root: Path,
        *,
        environ: Mapping[str, str],
        home: Path,
        handoff: HandoffCollector | None,
        today: date,
        progress: ProgressCallback | None,
    ) -> IndexReport:
        raise RuntimeError("synthetic refresh exception")

    original_refresh = refresh_module.refresh_after_command
    with monkeypatch.context() as owned:
        owned.setattr(refresh_module, "refresh_after_command", raise_refresh)
        response = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert refresh_module.refresh_after_command is original_refresh

    assert response.exit_code == 0, response.output
    assert (
        "Index: not refreshed; RuntimeError: synthetic refresh exception."
        in response.output
    )
