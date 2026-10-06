"""Task 5.3: hand rendered pages to an optional synchronous callback."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import fields
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

from fitdocs import AthleteInputs, parse_fit
from fitdocs import sync as sync_module
from fitdocs.compose.types import Composition
from fitdocs.contract import DOC_VERSION, parse_frontmatter, source_refs
from fitdocs.identity.roles import DEFAULT_PRECEDENCE
from fitdocs.inbox import DEFAULT_INBOX_SETTINGS
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.quarantine import QuarantineRecord
from fitdocs.render import DocContext, TileRef, render_document
from fitdocs.sync import DocumentMatch, RenderedPage, drain, regen, sync
from tests.fixtures import merge

_TZ = timezone(timedelta(hours=-6))


class _Tiles:
    attribution = "test"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"tile" for ref in refs}


def _fixture(tmp_path: Path) -> tuple[Path, bytes, bytes]:
    source = tmp_path / "source"
    source.mkdir()
    base, extra = merge.run_pair_fit_bytes()
    (source / "base.fit").write_bytes(base)
    (source / "extra.fit").write_bytes(extra)
    return source, base, extra


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _copy_tree(source_root: Path, target_root: Path) -> None:
    target_root.mkdir()
    for path in sorted(source_root.rglob("*")):
        if path.is_file():
            target = target_root / path.relative_to(source_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())


def test_sync_exposes_the_rendered_page_callback_contract() -> None:
    rendered_page = getattr(sync_module, "RenderedPage", None)
    assert rendered_page is not None
    assert [field.name for field in fields(rendered_page)] == [
        "doc_ref",
        "sources",
        "composition",
        "metrics",
        "athlete",
    ]
    assert rendered_page.__dataclass_params__.frozen is True
    expected_hints = {
        "doc_ref": str,
        "sources": tuple[str, ...],
        "composition": Composition,
        "metrics": DerivedMetrics,
        "athlete": AthleteInputs | None,
    }
    assert get_type_hints(rendered_page) == expected_hints
    for function in (sync, drain, regen):
        parameter = inspect.signature(function).parameters["on_rendered"]
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is None
        assert get_type_hints(function)["on_rendered"] == (
            Callable[[rendered_page], None] | None
        )


def test_sync_hands_off_composed_render_inputs_after_the_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, base_bytes, _extra = _fixture(tmp_path)
    data_root = tmp_path / "callback-data"
    data_root.mkdir()
    athlete = AthleteInputs(ftp_watts=287.0, resting_hr_bpm=43)
    writes: list[str] = []
    events: list[object] = []
    rendered_contexts: list[DocContext] = []
    real_write = sync_module._write_outputs
    real_render = render_document

    def record_write(*args: Any, **kwargs: Any) -> None:
        real_write(*args, **kwargs)
        writes.append("finished")

    def record_render(context: DocContext) -> object:
        rendered_contexts.append(context)
        return real_render(context)

    def receive(page: object) -> None:
        events.append((page, bool(writes)))

    monkeypatch.setattr(sync_module, "_write_outputs", record_write)
    monkeypatch.setattr(sync_module, "render_document", record_render)
    report = sync(
        source,
        data_root,
        athlete=athlete,
        tz=_TZ,
        tiles=_Tiles(),
        on_rendered=receive,
    )

    assert report.failures == ()
    assert len(events) == 1
    page, after_write = cast(tuple[Any, bool], events[0])
    assert after_write is True
    assert page.athlete is athlete
    assert isinstance(page.metrics, DerivedMetrics)
    assert page.doc_ref == report.written[0]
    frontmatter = parse_frontmatter((data_root / page.doc_ref).read_text())
    assert frontmatter is not None
    assert page.sources == source_refs(frontmatter)
    assert page.composition.activity is rendered_contexts[0].activity
    assert page.metrics is rendered_contexts[0].metrics
    base_activity = parse_fit(base_bytes)
    assert all(value is None for value in base_activity.samples.form_power_w)
    assert any(
        value is not None for value in page.composition.activity.samples.form_power_w
    )


def test_callback_does_not_change_sync_output_bytes(tmp_path: Path) -> None:
    source, _base, _extra = _fixture(tmp_path)
    with_callback = tmp_path / "with-callback"
    without_callback = tmp_path / "without-callback"
    with_callback.mkdir()
    without_callback.mkdir()
    callback_source = with_callback / "source"
    callback_source.mkdir()
    for item in source.iterdir():
        (callback_source / item.name).write_bytes(item.read_bytes())
    plain_source = without_callback / "source"
    plain_source.mkdir()
    for item in source.iterdir():
        (plain_source / item.name).write_bytes(item.read_bytes())
    callback_root = with_callback / "data"
    plain_root = without_callback / "data"
    callback_root.mkdir()
    plain_root.mkdir()

    callback_report = sync(
        callback_source,
        callback_root,
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        on_rendered=lambda _page: None,
    )
    plain_report = sync(plain_source, plain_root, athlete=None, tz=_TZ, tiles=_Tiles())
    assert callback_report == plain_report
    assert _tree(callback_root) == _tree(plain_root)


def test_drain_and_regen_thread_callbacks_to_the_page_task(tmp_path: Path) -> None:
    _source, base, extra = _fixture(tmp_path)
    data_root = tmp_path / "drain-data"
    data_root.mkdir()
    inbox_root = tmp_path / "inbox"
    inbox_root.mkdir()
    (inbox_root / "base.fit").write_bytes(base)
    (inbox_root / "extra.fit").write_bytes(extra)
    drained: list[object] = []
    drain_report = drain(
        inbox_root,
        data_root,
        settings=DEFAULT_INBOX_SETTINGS,
        processed_dir=None,
        quarantine=QuarantineRecord(entries=()),
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        sleep=lambda _seconds: None,
        on_rendered=drained.append,
    )
    assert drain_report.sync.failures == ()
    assert len(drained) == 1
    assert cast(RenderedPage, drained[0]).athlete is None

    regenerated: list[object] = []
    regen_report = regen(
        data_root,
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        on_rendered=regenerated.append,
    )
    assert regen_report.failures == ()
    assert len(regenerated) == 1
    assert cast(Any, regenerated[0]).doc_ref == cast(Any, drained[0]).doc_ref


def test_version_gated_sync_page_has_no_callback(tmp_path: Path) -> None:
    source, base, extra = _fixture(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    first = sync(source, data_root, athlete=None, tz=_TZ, tiles=_Tiles())
    assert first.failures == ()
    page_path = data_root / first.written[0]
    original = page_path.read_text(encoding="utf-8")
    assert f"doc_version: {DOC_VERSION}" in original
    page_path.write_text(
        original.replace(f"doc_version: {DOC_VERSION}", "doc_version: 999", 1),
        encoding="utf-8",
    )
    (source / "base.fit").write_bytes(base)
    (source / "extra.fit").write_bytes(extra)
    callbacks: list[object] = []

    gated = sync(
        source,
        data_root,
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        force=True,
        on_rendered=callbacks.append,
    )

    assert callbacks == []
    assert gated.skipped


def test_write_failure_does_not_call_callback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _base, _extra = _fixture(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    callbacks: list[object] = []

    def fail_write(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic output refusal")

    monkeypatch.setattr(sync_module, "_write_outputs", fail_write)
    report = sync(
        source,
        data_root,
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        on_rendered=callbacks.append,
    )
    assert report.failures
    assert callbacks == []


def test_settle_pass_rerender_calls_callback_again(tmp_path: Path) -> None:
    source, _base, _extra = _fixture(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    callbacks: list[object] = []
    report = sync(
        source,
        data_root,
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        on_rendered=callbacks.append,
    )
    assert report.failures == ()
    assert len(callbacks) == 1
    original = data_root / report.written[0]
    suffixed = original.with_name(f"{original.stem}-00000000{original.suffix}")
    original.rename(suffixed)
    entry = sync_module._SettleEntry(path=suffixed, unsuffixed=original.stem)
    ledger = sync_module._RunLedger(settle=[entry])
    written: list[str] = []
    before_settle = len(callbacks)
    cast(Any, sync_module)._settle_pass(
        data_root,
        ledger,
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        precedence=DEFAULT_PRECEDENCE,
        written=written,
        failures=[],
        warnings=[],
        on_rendered=callbacks.append,
    )
    assert before_settle == 1
    assert len(callbacks) == 2
    assert not suffixed.exists()
    assert original.is_file()


def test_settle_stem_mismatch_returns_without_callback(tmp_path: Path) -> None:
    source, _base, _extra = _fixture(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_Tiles())
    assert report.failures == ()
    path = data_root / report.written[0]
    text = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(text)
    assert frontmatter is not None
    match = DocumentMatch(path=path, sources=source_refs(frontmatter))
    callbacks: list[object] = []
    result = cast(Any, sync_module)._page_task(
        data_root,
        match=match,
        news=(),
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        precedence=DEFAULT_PRECEDENCE,
        settling=True,
        quiet=False,
        expected_stem="deliberately-wrong-stem",
        on_rendered=callbacks.append,
    )
    assert result.doc_ref == path.relative_to(data_root).as_posix()
    assert callbacks == []


def test_callback_exception_propagates_as_the_original_object(tmp_path: Path) -> None:
    source, _base, _extra = _fixture(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    expected = RuntimeError("callback failed")

    def fail(_page: RenderedPage) -> None:
        raise expected

    with pytest.raises(RuntimeError) as raised:
        sync(
            source,
            data_root,
            athlete=None,
            tz=_TZ,
            tiles=_Tiles(),
            on_rendered=fail,
        )
    assert raised.value is expected


def test_regen_callback_exception_propagates_as_the_original_object(
    tmp_path: Path,
) -> None:
    source, _base, _extra = _fixture(tmp_path)
    data_root = tmp_path / "data"
    data_root.mkdir()
    first = sync(source, data_root, athlete=None, tz=_TZ, tiles=_Tiles())
    assert first.failures == ()
    expected = RuntimeError("regen callback failed")

    def fail(_page: RenderedPage) -> None:
        raise expected

    with pytest.raises(RuntimeError) as raised:
        regen(data_root, athlete=None, tz=_TZ, tiles=_Tiles(), on_rendered=fail)
    assert raised.value is expected


def test_callback_is_synchronous_between_distinct_page_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _base, _extra = _fixture(tmp_path)
    ride_garmin, ride_healthfit = merge.ride_pair_fit_bytes()
    (source / "ride-garmin.fit").write_bytes(ride_garmin)
    (source / "ride-healthfit.fit").write_bytes(ride_healthfit)
    data_root = tmp_path / "data"
    data_root.mkdir()
    writes: list[str] = []
    events: list[RenderedPage] = []
    real_write = sync_module._write_outputs

    def record_write(*args: Any, **kwargs: Any) -> None:
        real_write(*args, **kwargs)
        writes.append("finished")

    def receive(page: RenderedPage) -> None:
        assert len(writes) == len(events) + 1
        events.append(page)

    monkeypatch.setattr(sync_module, "_write_outputs", record_write)
    report = sync(
        source,
        data_root,
        athlete=None,
        tz=_TZ,
        tiles=_Tiles(),
        on_rendered=receive,
    )
    assert report.failures == ()
    assert len(report.written) == 4
    assert len(events) == 2


def _strand_page(root: Path, doc_ref: str) -> tuple[Path, Path]:
    from fitdocs.contract import document_uuid, sha_of_ref

    original = root / doc_ref
    frontmatter = parse_frontmatter(original.read_text(encoding="utf-8"))
    assert frontmatter is not None
    uid = document_uuid(frontmatter) or sha_of_ref(source_refs(frontmatter)[-1])
    assert uid is not None
    stranded = original.with_name(f"{original.stem}-{uid[:8]}{original.suffix}")
    original.rename(stranded)
    assert stranded.is_file()
    assert not original.exists()
    return original, stranded


def _assert_handoff_matches_context(
    page: RenderedPage,
    context: DocContext,
    root: Path,
    athlete: AthleteInputs | None,
    expected_written_path: Path,
) -> None:
    assert page.doc_ref == expected_written_path.relative_to(root).as_posix()
    assert page.sources == context.source_refs
    assert page.composition.activity is context.activity
    assert page.composition.provenance is context.channel_provenance
    assert page.metrics is context.metrics
    assert page.athlete is athlete
    assert (root / page.doc_ref).is_file()


@pytest.mark.parametrize("entrypoint", ["sync", "drain", "regen"])
def test_public_entrypoints_hand_off_stranded_settle_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrypoint: str
) -> None:
    source, _base, _extra = _fixture(tmp_path)
    root = tmp_path / "data"
    root.mkdir()
    initial = sync(source, root, athlete=None, tz=_TZ, tiles=_Tiles())
    assert initial.failures == ()
    original, stranded = _strand_page(root, initial.written[0])
    plain_root = tmp_path / "without-callback"
    _copy_tree(root, plain_root)

    contexts: list[DocContext] = []
    events: list[RenderedPage] = []
    real_render = cast(Any, sync_module).render_document

    def capture(context: DocContext) -> object:
        contexts.append(context)
        return real_render(context)

    monkeypatch.setattr(sync_module, "render_document", capture)
    isolated_calls: list[str] = []
    if entrypoint == "sync":
        callback_report = sync(
            source,
            root,
            athlete=None,
            tz=_TZ,
            tiles=_Tiles(),
            on_rendered=events.append,
        )
        assert callback_report.failures == ()
        plain_report = sync(source, plain_root, athlete=None, tz=_TZ, tiles=_Tiles())
        assert callback_report == plain_report
    elif entrypoint == "drain":
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        callback_drain_report = drain(
            inbox,
            root,
            settings=DEFAULT_INBOX_SETTINGS,
            processed_dir=None,
            quarantine=QuarantineRecord(entries=()),
            athlete=None,
            tz=_TZ,
            tiles=_Tiles(),
            sleep=lambda _seconds: None,
            on_rendered=events.append,
        )
        assert callback_drain_report.sync.failures == ()
        plain_drain_report = drain(
            inbox,
            plain_root,
            settings=DEFAULT_INBOX_SETTINGS,
            processed_dir=None,
            quarantine=QuarantineRecord(entries=()),
            athlete=None,
            tz=_TZ,
            tiles=_Tiles(),
            sleep=lambda _seconds: None,
        )
        assert plain_drain_report.sync.failures == ()
        assert callback_drain_report == plain_drain_report
    else:

        def defer_isolated(*_args: Any, **_kwargs: Any) -> None:
            isolated_calls.append("deferred")

        monkeypatch.setattr(sync_module, "_process_isolated", defer_isolated)
        callback_regen_report = regen(
            root, athlete=None, tz=_TZ, tiles=_Tiles(), on_rendered=events.append
        )
        assert callback_regen_report.failures == ()
        plain_regen_report = regen(plain_root, athlete=None, tz=_TZ, tiles=_Tiles())
        assert plain_regen_report.failures == ()
        assert callback_regen_report == plain_regen_report
        assert isolated_calls == ["deferred", "deferred"]

    assert original.is_file()
    assert not stranded.exists()
    assert len(events) == 1
    assert len(contexts) == 2
    _assert_handoff_matches_context(
        events[0], contexts[0], root, athlete=None, expected_written_path=original
    )
    assert _tree(root) == _tree(plain_root)


def test_regen_hands_off_unreferenced_archives_through_planner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from fitdocs.layout import archive_path

    root = tmp_path / "data"
    root.mkdir()
    base, extra = merge.run_pair_fit_bytes()
    for content in (base, extra):
        target = archive_path(root, hashlib.sha256(content).hexdigest())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    assert sorted((root / "fit-archive").rglob("*.fit"))
    plain_root = tmp_path / "without-callback"
    _copy_tree(root, plain_root)

    events: list[RenderedPage] = []
    contexts: list[DocContext] = []
    real_render = cast(Any, sync_module).render_document

    def capture(context: DocContext) -> object:
        contexts.append(context)
        return real_render(context)

    monkeypatch.setattr(sync_module, "render_document", capture)
    report = regen(
        root, athlete=None, tz=_TZ, tiles=_Tiles(), on_rendered=events.append
    )
    plain_report = regen(plain_root, athlete=None, tz=_TZ, tiles=_Tiles())

    assert report.failures == ()
    assert report.written
    assert report == plain_report
    assert len(events) == 1
    assert len(contexts) == 2
    assert (root / events[0].doc_ref).is_file()
    expected_refs = {
        archive_path(root, hashlib.sha256(content).hexdigest())
        .relative_to(root)
        .as_posix()
        for content in (base, extra)
    }
    assert set(events[0].sources) == expected_refs
    _assert_handoff_matches_context(
        events[0],
        contexts[0],
        root,
        athlete=None,
        expected_written_path=root / "workouts" / f"{contexts[0].doc_stem}.md",
    )
    assert _tree(root) == _tree(plain_root)


def test_handoff_preserves_complete_provenance_from_actual_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, _base, _extra = _fixture(tmp_path)
    root = tmp_path / "data"
    root.mkdir()
    contexts: list[DocContext] = []
    events: list[RenderedPage] = []
    real_render = cast(Any, sync_module).render_document

    def capture(context: DocContext) -> object:
        contexts.append(context)
        return real_render(context)

    monkeypatch.setattr(sync_module, "render_document", capture)
    report = sync(
        source, root, athlete=None, tz=_TZ, tiles=_Tiles(), on_rendered=events.append
    )

    assert report.failures == ()
    assert len(contexts) == len(events) == 1
    expected_provenance = contexts[0].channel_provenance
    assert expected_provenance is not None
    assert expected_provenance.extras
    assert events[0].composition.provenance is expected_provenance
    _assert_handoff_matches_context(
        events[0],
        contexts[0],
        root,
        athlete=None,
        expected_written_path=root / "workouts" / f"{contexts[0].doc_stem}.md",
    )


def test_settle_callback_exception_propagates_same_object_after_write(
    tmp_path: Path,
) -> None:
    source, _base, _extra = _fixture(tmp_path)
    root = tmp_path / "data"
    root.mkdir()
    initial = sync(source, root, athlete=None, tz=_TZ, tiles=_Tiles())
    assert initial.failures == ()
    original, stranded = _strand_page(root, initial.written[0])
    expected = RuntimeError("settle callback sentinel")
    callback_calls: list[Path] = []

    def fail(page: RenderedPage) -> None:
        written_path = root / page.doc_ref
        assert written_path.is_file()
        callback_calls.append(written_path)
        raise expected

    with pytest.raises(RuntimeError) as caught:
        sync(source, root, athlete=None, tz=_TZ, tiles=_Tiles(), on_rendered=fail)

    assert caught.value is expected
    assert len(callback_calls) == 1
    assert callback_calls[0] == original
    assert original.is_file()
    assert not stranded.exists()


@pytest.mark.parametrize("entrypoint", ["drain", "regen"])
def test_populated_athlete_reaches_renderer_and_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrypoint: str
) -> None:
    source, base, extra = _fixture(tmp_path)
    root = tmp_path / "data"
    root.mkdir()
    athlete = AthleteInputs(ftp_watts=287.0, resting_hr_bpm=43, max_hr_bpm=189)
    events: list[RenderedPage] = []
    contexts: list[DocContext] = []
    real_render = cast(Any, sync_module).render_document

    def capture(context: DocContext) -> object:
        contexts.append(context)
        return real_render(context)

    monkeypatch.setattr(sync_module, "render_document", capture)
    render_context: DocContext | None = None
    if entrypoint == "drain":
        inbox = tmp_path / "inbox"
        inbox.mkdir()
        (inbox / "base.fit").write_bytes(base)
        (inbox / "extra.fit").write_bytes(extra)
        plain_inbox = tmp_path / "without-callback-inbox"
        plain_inbox.mkdir()
        (plain_inbox / "base.fit").write_bytes(base)
        (plain_inbox / "extra.fit").write_bytes(extra)
        plain_root = tmp_path / "without-callback"
        plain_root.mkdir()
        drain_report = drain(
            inbox,
            root,
            settings=DEFAULT_INBOX_SETTINGS,
            processed_dir=None,
            quarantine=QuarantineRecord(entries=()),
            athlete=athlete,
            tz=_TZ,
            tiles=_Tiles(),
            sleep=lambda _seconds: None,
            on_rendered=events.append,
        )
        assert drain_report.sync.failures == ()
        assert len(contexts) == 1
        render_context = contexts[0]
        contexts.clear()
        plain_drain_report = drain(
            plain_inbox,
            plain_root,
            settings=DEFAULT_INBOX_SETTINGS,
            processed_dir=None,
            quarantine=QuarantineRecord(entries=()),
            athlete=athlete,
            tz=_TZ,
            tiles=_Tiles(),
            sleep=lambda _seconds: None,
        )
        assert plain_drain_report.sync.failures == ()
        assert _tree(root) == _tree(plain_root)
    else:
        initial = sync(source, root, athlete=None, tz=_TZ, tiles=_Tiles())
        assert initial.failures == ()
        contexts.clear()
        plain_root = tmp_path / "without-callback"
        _copy_tree(root, plain_root)
        regen_report = regen(
            root, athlete=athlete, tz=_TZ, tiles=_Tiles(), on_rendered=events.append
        )
        assert regen_report.failures == ()
        assert len(contexts) == 1
        render_context = contexts[0]
        contexts.clear()
        plain_regen_report = regen(plain_root, athlete=athlete, tz=_TZ, tiles=_Tiles())
        assert plain_regen_report.failures == ()
        assert regen_report == plain_regen_report
        assert _tree(root) == _tree(plain_root)

    assert len(events) == 1
    assert render_context is not None
    page = events[0]
    assert render_context.athlete is athlete
    assert page.athlete is athlete
    _assert_handoff_matches_context(
        page,
        render_context,
        root,
        athlete=athlete,
        expected_written_path=root / "workouts" / f"{render_context.doc_stem}.md",
    )
