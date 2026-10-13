"""Validation and recognition against synthetic declarations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from fitdocs.wellness import registry
from fitdocs.wellness.model import Metric
from fitdocs.wellness.probe import HEAD_BYTES, CandidateProbe
from fitdocs.wellness.spec import (
    SourceKind,
    SourceSpec,
)
from tests.wellness._helpers import (
    EXTRACT_FORMAT,
    EXTRACT_SOURCE,
    ORIGINAL_FORMAT,
    ORIGINAL_SOURCE,
    CountingOpener,
    assert_untouched,
    tree_snapshot,
    use_formats,
)


def test_empty_registry() -> None:
    assert registry.SOURCES == ()
    assert registry.FORMATS == ()
    registry.validate_registry()
    assert registry.candidate_suffixes() == frozenset()
    assert registry.default_source_order() == ()
    assert registry.format_named("missing") is None
    assert registry.source_named("missing") is None


def test_valid_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(
        monkeypatch,
        (ORIGINAL_FORMAT, EXTRACT_FORMAT),
        (ORIGINAL_SOURCE, EXTRACT_SOURCE),
    )
    registry.validate_registry()


@pytest.mark.parametrize(
    "bad_id", ["", "Upper", "under_score", "-leading", "trailing-", "double--dash"]
)
@pytest.mark.parametrize("declaration", ["source", "format"])
def test_bad_ids(
    monkeypatch: pytest.MonkeyPatch, bad_id: str, declaration: str
) -> None:
    source = (
        replace(ORIGINAL_SOURCE, id=bad_id)
        if declaration == "source"
        else ORIGINAL_SOURCE
    )
    form = replace(
        ORIGINAL_FORMAT,
        source=source,
        id=bad_id if declaration == "format" else "test-original",
    )
    use_formats(monkeypatch, (form,), (source,))
    with pytest.raises(ValueError) as failure:
        registry.validate_registry()
    assert repr(bad_id) in str(failure.value)


@pytest.mark.parametrize("declaration", ["source", "format"])
def test_duplicate_ids(monkeypatch: pytest.MonkeyPatch, declaration: str) -> None:
    sources = (
        (ORIGINAL_SOURCE, ORIGINAL_SOURCE)
        if declaration == "source"
        else (ORIGINAL_SOURCE,)
    )
    forms = (
        (
            ORIGINAL_FORMAT,
            replace(ORIGINAL_FORMAT, metrics=frozenset({Metric.WEIGHT_KG})),
        )
        if declaration == "format"
        else (ORIGINAL_FORMAT,)
    )
    use_formats(monkeypatch, forms, sources)
    with pytest.raises(ValueError, match="test-original"):
        registry.validate_registry()


@pytest.mark.parametrize(
    "case",
    [
        "unknown-source",
        "fit",
        "uppercase",
        "dot",
        "original-suffix",
        "original-extract",
        "extract-missing",
        "latest-order",
        "version",
    ],
)
def test_invalid_format(monkeypatch: pytest.MonkeyPatch, case: str) -> None:
    forms = {
        "unknown-source": replace(ORIGINAL_FORMAT, source=EXTRACT_SOURCE),
        "fit": replace(ORIGINAL_FORMAT, suffixes=frozenset({".json", ".fit"})),
        "uppercase": replace(ORIGINAL_FORMAT, suffixes=frozenset({".json", ".JSON"})),
        "dot": replace(ORIGINAL_FORMAT, suffixes=frozenset({".json", "json"})),
        "original-suffix": replace(ORIGINAL_FORMAT, archived_suffix=".else"),
        "original-extract": replace(ORIGINAL_FORMAT, extract=EXTRACT_FORMAT.extract),
        "extract-missing": replace(EXTRACT_FORMAT, extract=None),
        "latest-order": replace(EXTRACT_FORMAT, entry_order=None),
        "version": replace(ORIGINAL_FORMAT, rules_version=0),
    }
    form = replace(forms[case], id="offending-format")
    use_formats(
        monkeypatch,
        (form,),
        (ORIGINAL_SOURCE, EXTRACT_SOURCE)
        if case != "unknown-source"
        else (ORIGINAL_SOURCE,),
    )
    with pytest.raises(ValueError, match="offending-format"):
        registry.validate_registry()


def test_disjoint_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    second = replace(
        ORIGINAL_FORMAT, id="second-format", metrics=frozenset({Metric.WEIGHT_KG})
    )
    use_formats(monkeypatch, (ORIGINAL_FORMAT, second), (ORIGINAL_SOURCE,))
    registry.validate_registry()
    use_formats(
        monkeypatch,
        (ORIGINAL_FORMAT, replace(second, metrics=ORIGINAL_FORMAT.metrics)),
        (ORIGINAL_SOURCE,),
    )
    with pytest.raises(ValueError, match="second-format"):
        registry.validate_registry()


def test_cross_source_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(
        monkeypatch,
        (ORIGINAL_FORMAT, replace(EXTRACT_FORMAT, metrics=ORIGINAL_FORMAT.metrics)),
        (ORIGINAL_SOURCE, EXTRACT_SOURCE),
    )
    registry.validate_registry()


def test_lookups_and_suffixes_are_dynamic(monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(monkeypatch, (ORIGINAL_FORMAT,), (ORIGINAL_SOURCE,))
    assert registry.format_named(ORIGINAL_FORMAT.id) is ORIGINAL_FORMAT
    assert registry.source_named(ORIGINAL_SOURCE.id) is ORIGINAL_SOURCE
    assert registry.candidate_suffixes() == frozenset({".json"})
    assert registry.default_source_order() == ("test-original",)
    use_formats(monkeypatch, (EXTRACT_FORMAT,), (EXTRACT_SOURCE,))
    assert registry.format_named(ORIGINAL_FORMAT.id) is None
    assert registry.source_named(ORIGINAL_SOURCE.id) is None
    assert registry.format_named(EXTRACT_FORMAT.id) is EXTRACT_FORMAT
    assert registry.source_named(EXTRACT_SOURCE.id) is EXTRACT_SOURCE
    assert registry.candidate_suffixes() == frozenset({".test-extract"})
    assert registry.default_source_order() == ("test-extract",)


def test_source_order(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = (
        SourceSpec("a-relay", "Relay", SourceKind.RELAY),
        SourceSpec("z-device", "Second device", SourceKind.DEVICE),
        SourceSpec("b-hub", "Hub", SourceKind.HUB),
        SourceSpec("y-device", "First device", SourceKind.DEVICE),
    )
    use_formats(monkeypatch, (), sources)
    assert registry.default_source_order() == (
        "y-device",
        "z-device",
        "b-hub",
        "a-relay",
    )


def _candidate(tmp_path: Path, suffix: str = ".json") -> CandidateProbe:
    path = tmp_path / ("arbitrary" + suffix)
    path.write_bytes(b'{"test_original":true,"day":"2024-02-03","value":61}')
    return CandidateProbe.open(path)


@pytest.mark.parametrize("claims", [0, 1, 2])
def test_claims(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claims: int) -> None:
    calls: list[str] = []

    def recognizer(name: str, claim: bool) -> Callable[[CandidateProbe], bool]:
        def ask(probe: CandidateProbe) -> bool:
            calls.append(name)
            return claim

        return ask

    forms = tuple(
        replace(ORIGINAL_FORMAT, id=name, recognize=recognizer(name, index < claims))
        for index, name in enumerate(("alpha-format", "beta-format", "gamma-format"))
    )
    use_formats(monkeypatch, forms, (ORIGINAL_SOURCE,))
    candidate = _candidate(tmp_path)
    before = tree_snapshot(tmp_path)
    result = registry.recognize(candidate)
    assert calls == ["alpha-format", "beta-format", "gamma-format"]
    if claims == 1:
        assert result == registry.Recognized(forms[0])
    else:
        assert isinstance(result, registry.NotRecognized)
        assert result.reason == (
            "no supported wellness format reads this file"
            if claims == 0
            else "multiple wellness formats read this file: alpha-format, beta-format"
        )
    assert_untouched(before, tree_snapshot(tmp_path))


def test_suffix_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(probe: CandidateProbe) -> bool:
        pytest.fail("suffix mismatch was asked")

    use_formats(
        monkeypatch,
        (replace(ORIGINAL_FORMAT, recognize=forbidden),),
        (ORIGINAL_SOURCE,),
    )
    assert registry.recognize(
        _candidate(tmp_path, ".unknown")
    ) == registry.NotRecognized("no supported wellness format reads this file")


@pytest.mark.parametrize("exception", [ValueError, RuntimeError, TypeError])
def test_content_error_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exception: type[Exception]
) -> None:
    def broken(probe: CandidateProbe) -> bool:
        raise exception("synthetic malformed content")

    second = replace(ORIGINAL_FORMAT, id="second-format")
    use_formats(
        monkeypatch,
        (replace(ORIGINAL_FORMAT, recognize=broken), second),
        (ORIGINAL_SOURCE,),
    )
    assert registry.recognize(_candidate(tmp_path)) == registry.Recognized(second)


def test_oserror_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "partial.json"
    path.write_bytes(b" " * HEAD_BYTES + b"{}")
    assert path.stat().st_size > HEAD_BYTES
    opener = CountingOpener(path, fail_past_head=True)
    opener.install(monkeypatch)
    candidate = CandidateProbe.open(path)
    calls: list[str] = []

    def failing(probe: CandidateProbe) -> bool:
        calls.append("first")
        return probe.json() is not None

    def remaining(probe: CandidateProbe) -> bool:
        calls.append("second")
        return True

    use_formats(
        monkeypatch,
        (
            replace(ORIGINAL_FORMAT, recognize=failing),
            replace(ORIGINAL_FORMAT, id="second-format", recognize=remaining),
        ),
        (ORIGINAL_SOURCE,),
    )
    with pytest.raises(OSError, match="candidate unavailable past head"):
        registry.recognize(candidate)
    assert calls == ["first"]


def test_recognition_is_dynamic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _candidate(tmp_path)
    use_formats(monkeypatch, (ORIGINAL_FORMAT,), (ORIGINAL_SOURCE,))
    assert registry.recognize(candidate) == registry.Recognized(ORIGINAL_FORMAT)
    use_formats(monkeypatch, (), ())
    assert registry.recognize(candidate) == registry.NotRecognized(
        "no supported wellness format reads this file"
    )


def test_no_runtime_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        pytest.fail("runtime validation")

    monkeypatch.setattr(registry, "validate_registry", forbidden)
    use_formats(monkeypatch, (ORIGINAL_FORMAT,), (ORIGINAL_SOURCE,))
    assert registry.recognize(_candidate(tmp_path)) == registry.Recognized(
        ORIGINAL_FORMAT
    )
    assert registry.format_named("test-original") is ORIGINAL_FORMAT
    assert registry.source_named("test-original") is ORIGINAL_SOURCE
    assert registry.candidate_suffixes() == frozenset({".json"})
    assert registry.default_source_order() == ("test-original",)


def test_registry_contracts() -> None:
    assert registry.__annotations__ == {
        "SOURCES": "Final[tuple[SourceSpec, ...]]",
        "FORMATS": "Final[tuple[FormatSpec, ...]]",
    }
    assert [(field.name, field.type) for field in fields(registry.Recognized)] == [
        ("format", "FormatSpec")
    ]
    assert [(field.name, field.type) for field in fields(registry.NotRecognized)] == [
        ("reason", "str")
    ]
    for result, field, replacement in (
        (registry.Recognized(ORIGINAL_FORMAT), "format", EXTRACT_FORMAT),
        (registry.NotRecognized("reason"), "reason", "changed"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(result, field, replacement)


def test_use_formats_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(
        monkeypatch,
        [EXTRACT_FORMAT, ORIGINAL_FORMAT],
        [EXTRACT_SOURCE, ORIGINAL_SOURCE],
    )
    assert registry.FORMATS == (EXTRACT_FORMAT, ORIGINAL_FORMAT)
    assert registry.SOURCES == (EXTRACT_SOURCE, ORIGINAL_SOURCE)


@pytest.mark.parametrize("valid_id", ["a", "0", "alpha-2", "z9"])
def test_valid_ids(monkeypatch: pytest.MonkeyPatch, valid_id: str) -> None:
    source = replace(ORIGINAL_SOURCE, id=valid_id)
    use_formats(
        monkeypatch, (replace(ORIGINAL_FORMAT, id=valid_id, source=source),), (source,)
    )
    registry.validate_registry()


def test_candidate_suffix_union(monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(
        monkeypatch,
        (
            replace(ORIGINAL_FORMAT, suffixes=frozenset({".json", ".other"})),
            EXTRACT_FORMAT,
        ),
        (ORIGINAL_SOURCE, EXTRACT_SOURCE),
    )
    assert registry.candidate_suffixes() == frozenset(
        {".json", ".other", ".test-extract"}
    )


def test_lookup_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    use_formats(
        monkeypatch,
        (ORIGINAL_FORMAT, EXTRACT_FORMAT),
        (ORIGINAL_SOURCE, EXTRACT_SOURCE),
    )
    assert registry.format_named("test-extract") is EXTRACT_FORMAT
    assert registry.source_named("test-extract") is EXTRACT_SOURCE
