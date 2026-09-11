"""Tests for `fitdocs.performance.engine` (design: PassEngine, Req 1.2, 7.1,
7.2, 7.3, 9.3, 9.7, 10.3).

`tests/performance/test_engine.py` is created by task 4.1 with the skeleton
section below; task 4.2 appends the archive-and-failure section and task 4.3
appends the write/reconciliation section. Neither edits this section.

Task 4.1 covers discovery (sorted, filtered through
`fitdocs.contract.is_workout_document`), the single frontmatter read per
document, and the three-way branch over `fitdocs.contract.effort_tag`
(untagged / valid / malformed). No archive is resolved and nothing is
written at this task, so `entries` is always empty and `written` is always
`False` here.
"""

from __future__ import annotations

import ast
import inspect
from datetime import date
from pathlib import Path

import pytest

from fitdocs import contract, docio
from fitdocs.performance.engine import DeriveFailure, DeriveReport, derive_benchmarks

WORKOUT_FRONTMATTER = """---
type: workout
date: "{date}"
{effort_lines}---
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


def _write_workout(
    data_root: Path,
    name: str,
    *,
    on: str = "2024-05-01",
    kind: str | None = None,
    distance: float | None = None,
    time: float | None = None,
) -> Path:
    workouts = data_root / "workouts"
    workouts.mkdir(parents=True, exist_ok=True)
    path = workouts / name
    text = WORKOUT_FRONTMATTER.format(
        date=on,
        effort_lines=_effort_lines(kind=kind, distance=distance, time=time),
    )
    path.write_text(text + "\nBody.\n", encoding="utf-8")
    return path


def _write_non_workout(data_root: Path, name: str) -> Path:
    workouts = data_root / "workouts"
    workouts.mkdir(parents=True, exist_ok=True)
    path = workouts / name
    path.write_text(
        '---\ntype: something-else\ndate: "2024-05-01"\n---\n\nBody.\n',
        encoding="utf-8",
    )
    return path


# --- skeleton: discovery, the tag branch, the report types (task 4.1) ------


def test_considers_both_pages_and_tags_only_the_valid_one(tmp_path: Path) -> None:
    """One tagged, one untagged page: considered counts both, tagged counts
    only the valid one, and the untagged page produces no entry or failure.

    Falsity in the starting state: before the run, nothing has been counted
    at all -- the assertion pins the exact post-run counts, not merely their
    presence.
    """
    _write_workout(tmp_path, "tagged.md", kind="race", distance=10000, time=2400)
    _write_workout(tmp_path, "untagged.md", kind=None)

    report = derive_benchmarks(tmp_path)

    assert report.considered == 2
    assert report.tagged == 1
    assert report.entries == ()
    assert report.failures == ()
    assert report.written is False


def test_untagged_page_alone_is_considered_but_never_tagged(tmp_path: Path) -> None:
    """A lone untagged page is considered once and never counted as tagged --
    the named mutation (counting an untagged page as tagged) reddens this
    directly rather than only the two-page test above."""
    _write_workout(tmp_path, "untagged.md", kind=None)

    report = derive_benchmarks(tmp_path)

    assert report.considered == 1
    assert report.tagged == 0


def test_discovery_is_sorted_independent_of_creation_order(tmp_path: Path) -> None:
    """Files are created in an order that would defeat directory/creation-time
    iteration (`b` before `a`), each with a distinct malformed tag so the
    order in which they are processed is directly observable in
    `report.failures`. A pure count (`considered == 2`) would not
    discriminate an unsorted traversal from a sorted one -- only the
    *ordering* of the two distinctly-reasoned failures does, which is why
    this asserts the failures list in the sorted-name order `a_first` then
    `b_second`, not merely that both are present."""
    _write_workout(tmp_path, "b_second.md", kind="marathon")
    _write_workout(tmp_path, "a_first.md", kind="triathlon")

    report = derive_benchmarks(tmp_path)

    assert report.considered == 2
    assert [f.document for f in report.failures] == [
        "workouts/a_first.md",
        "workouts/b_second.md",
    ]
    # Falsity in the starting state: the two reasons differ (distinct
    # malformed `effort` values), so a swap in traversal order is visible
    # as a swap in this list, not masked by identical content.
    assert report.failures[0].reason != report.failures[1].reason


def test_non_workout_document_is_not_considered(tmp_path: Path) -> None:
    """A `.md` file under `workouts/` whose `type` is not `workout` must not
    be counted as considered -- pins the `is_workout_document` filter, not
    merely "some filter exists"."""
    _write_workout(tmp_path, "tagged.md", kind="race", distance=10000, time=2400)
    _write_non_workout(tmp_path, "not-a-workout.md")

    report = derive_benchmarks(tmp_path)

    assert report.considered == 1
    assert report.tagged == 1


def test_malformed_tag_is_recorded_as_failure_never_as_tagged_or_untagged(
    tmp_path: Path,
) -> None:
    """An unrecognised `effort` value is a malformed tag: it must be recorded
    as a failure using the contract's own `describe()` text, must not be
    counted as tagged, and must not be silently treated as untagged (which
    would leave `considered == 1, tagged == 0, failures == ()`)."""
    _write_workout(tmp_path, "malformed.md", kind="marathon")

    report = derive_benchmarks(tmp_path)

    assert report.considered == 1
    assert report.tagged == 0
    assert report.entries == ()
    assert len(report.failures) == 1
    failure = report.failures[0]
    assert isinstance(failure, DeriveFailure)
    assert failure.document == "workouts/malformed.md"

    frontmatter = docio.read_frontmatter(tmp_path / "workouts" / "malformed.md")
    tag = contract.effort_tag(frontmatter)
    assert isinstance(tag, contract.InvalidEffortTag)
    assert failure.reason == tag.describe()
    assert failure.reason != ""


def test_frontmatter_is_read_exactly_once_per_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docio.read_frontmatter` must be called exactly once per candidate
    document -- once for both the `is_workout_document` filter and every
    later branch, never a second time for the same file."""
    _write_workout(tmp_path, "tagged.md", kind="race", distance=10000, time=2400)
    _write_workout(tmp_path, "untagged.md", kind=None)

    calls: list[Path] = []
    real_read = docio.read_frontmatter

    def counting_read(path: Path) -> dict[str, object] | None:
        calls.append(path)
        return real_read(path)

    monkeypatch.setattr("fitdocs.performance.engine.read_frontmatter", counting_read)

    derive_benchmarks(tmp_path)

    assert len(calls) == 2
    assert len(calls) == len(set(calls))


def test_date_is_read_through_the_contracts_document_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The recorded date on the internal per-document record must come from
    `contract.document_date`, not a second date computation -- monkeypatching
    it to a fixed sentinel and observing that sentinel propagate proves the
    binding, since a coincidental match with the real file date would not."""
    _write_workout(
        tmp_path, "tagged.md", on="2024-05-01", kind="race", distance=10000, time=2400
    )

    sentinel = date(1999, 1, 1)
    monkeypatch.setattr(
        "fitdocs.performance.engine.document_date", lambda frontmatter: sentinel
    )

    captured: dict[str, object] = {}
    import fitdocs.performance.engine as engine_module

    real_init = engine_module._TaggedDocument.__init__

    def capturing_init(self: object, *, document: str, tag: object, on: object) -> None:
        captured["on"] = on
        real_init(self, document=document, tag=tag, on=on)  # type: ignore[arg-type]

    monkeypatch.setattr(engine_module._TaggedDocument, "__init__", capturing_init)

    derive_benchmarks(tmp_path)

    assert captured["on"] is sentinel
    # Falsity in the starting state: the real page date is not the sentinel,
    # so a coincidental pass is impossible.
    assert sentinel != date(2024, 5, 1)


def test_discovery_is_top_level_only_not_recursive(tmp_path: Path) -> None:
    """Discovery covers only `*.md` directly under `workouts/`, not files in
    subdirectories -- a page and a byte-identical copy nested one directory
    deeper must not both be considered/tagged, which pins `glob` over
    `rglob` (Req 9.1)."""
    _write_workout(tmp_path, "top.md", kind="race", distance=10000, time=2400)
    nested = tmp_path / "workouts" / "sub"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "nested.md").write_text(
        (tmp_path / "workouts" / "top.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    report = derive_benchmarks(tmp_path)

    assert report.considered == 1
    assert report.tagged == 1


def test_undated_tagged_page_is_tagged_with_no_failure_and_no_fabricated_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tagged page whose `date` frontmatter value does not parse (so
    `contract.document_date` returns `None`) is still counted as tagged, is
    never recorded as a failure, and the internal per-document record's `on`
    stays `None` -- never a fallback to `date.today()` (Req 7.6, 9.3).

    Two distinct wrong implementations are pinned here: treating an undated
    tagged page as a failure (`considered == 1, tagged == 1` would still hold
    but `failures` would be non-empty), and substituting today's date for the
    missing one (`captured["on"] is None` would go false). Capturing the
    `_TaggedDocument` construction the same way the sentinel-date test does
    makes the second observable even though `on` never reaches the report.
    """
    _write_workout(
        tmp_path, "undated.md", on="not-a-date", kind="race", distance=10000, time=2400
    )

    import fitdocs.performance.engine as engine_module

    real_init = engine_module._TaggedDocument.__init__
    captured: dict[str, object] = {}

    def capturing_init(self: object, *, document: str, tag: object, on: object) -> None:
        captured["on"] = on
        real_init(self, document=document, tag=tag, on=on)  # type: ignore[arg-type]

    monkeypatch.setattr(engine_module._TaggedDocument, "__init__", capturing_init)

    report = derive_benchmarks(tmp_path)

    assert report.considered == 1
    assert report.tagged == 1
    assert report.failures == ()
    assert captured["on"] is None


def test_no_yaml_import_or_fence_literal_in_engine_module() -> None:
    """The pass binds the contract's readers and never a YAML parser or a
    fence literal of its own (design: PassEngine invariants, Req 10.3).

    Scans the engine module's own AST for any `import yaml` / `from yaml
    import ...` and its source text for the `"---"` fence literal, so a
    future edit that reaches for either fails this test immediately rather
    than only failing a downstream reachability guard.
    """
    import fitdocs.performance.engine as engine_module

    source = inspect.getsource(engine_module)
    tree = ast.parse(source)

    scanned_nodes = 0
    for node in ast.walk(tree):
        scanned_nodes += 1
        if isinstance(node, ast.Import):
            assert not any(alias.name == "yaml" for alias in node.names), (
                "engine.py must not import yaml"
            )
        if isinstance(node, ast.ImportFrom):
            assert node.module != "yaml", "engine.py must not import from yaml"
    assert scanned_nodes, "the AST walk scanned nothing -- wrong module?"

    assert '"---"' not in source
    assert "'---'" not in source


def test_dry_run_does_not_affect_the_skeletons_report(tmp_path: Path) -> None:
    """`dry_run=True` produces the identical report shape at this task (no
    write path exists yet): `written` stays `False` either way, distinguishing
    this from a stub that hardcodes `written=False` only for one branch."""
    _write_workout(tmp_path, "tagged.md", kind="race", distance=10000, time=2400)

    default_report = derive_benchmarks(tmp_path)
    dry_report = derive_benchmarks(tmp_path, dry_run=True)

    assert default_report.written is False
    assert dry_report.written is False
    assert default_report.considered == dry_report.considered
    assert default_report.tagged == dry_report.tagged


def test_derive_report_derived_and_declined_flatten_across_entries_in_order() -> None:
    """`DeriveReport.derived` and `.declined` each flatten the matching field
    across every entry, in entry order -- built directly from two entries
    each carrying two distinct outcomes, so a swapped field (`derived`
    returning `declined`) or a truncation to only the first entry is
    observable rather than masked by a single-entry or single-outcome
    fixture."""
    from datetime import date as date_

    from fitdocs.benchmarks import BenchmarkKind
    from fitdocs.model import Sport
    from fitdocs.performance.types import (
        DeclineReason,
        DerivationDeclined,
        DerivationMethod,
        DerivedBenchmark,
    )

    d1 = DerivedBenchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=250.0,
        measured_on=date_(2024, 1, 1),
        method=DerivationMethod.RIEGEL_RACE_EQUIVALENCE,
        citation_key="riegel-1980",
        inputs="one.md",
        note="first",
        document="workouts/one.md",
    )
    d2 = DerivedBenchmark(
        kind=BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=165.0,
        measured_on=date_(2024, 2, 2),
        method=DerivationMethod.SUSTAINED_EFFORT_MEAN_HR,
        citation_key="other-cite",
        inputs="two.md",
        note="second",
        document="workouts/two.md",
    )
    x1 = DerivationDeclined(
        kind=BenchmarkKind.FTP_WATTS,
        method=DerivationMethod.TIME_TRIAL_MEAN_POWER,
        reason=DeclineReason.SPORT_NOT_COVERED,
        detail="first decline",
    )
    x2 = DerivationDeclined(
        kind=BenchmarkKind.MAX_HR_BPM,
        method=None,
        reason=DeclineReason.MISSING_INPUT,
        detail="second decline",
    )

    from fitdocs.performance.engine import DeriveEntry

    entry_a = DeriveEntry(document="workouts/one.md", derived=(d1,), declined=(x1,))
    entry_b = DeriveEntry(document="workouts/two.md", derived=(d2,), declined=(x2,))
    report = DeriveReport(
        considered=2, tagged=2, entries=(entry_a, entry_b), failures=(), written=False
    )

    # Falsity in the starting state: the two derived/declined values differ
    # from each other and from the other field's values, so a swap or a
    # truncation is directly visible rather than masked by identical content.
    assert d1 != d2
    assert x1 != x2

    assert report.derived == (d1, d2)
    assert report.declined == (x1, x2)


def test_report_type_shapes_are_frozen_dataclasses() -> None:
    """`DeriveEntry`, `DeriveFailure`, `DeriveReport` are frozen dataclasses
    with the field order given in design.md's Service Interface -- pins
    immutability on all three types (not only `DeriveReport`) and exact field
    order (not merely the field-name set, which cannot detect a swap between
    two same-typed fields)."""
    from dataclasses import fields, is_dataclass

    from fitdocs.performance.engine import DeriveEntry

    assert is_dataclass(DeriveEntry)
    assert is_dataclass(DeriveFailure)
    assert is_dataclass(DeriveReport)

    entry = DeriveEntry(document="a.md", derived=(), declined=())
    with pytest.raises(AttributeError):
        entry.document = "b.md"  # type: ignore[misc]

    failure = DeriveFailure(document="a.md", reason="r")
    with pytest.raises(AttributeError):
        failure.reason = "other"  # type: ignore[misc]

    report = derive_benchmarks(Path("/nonexistent-data-root-for-shape-check"))
    with pytest.raises(AttributeError):
        report.considered = 99  # type: ignore[misc]

    assert [f.name for f in fields(DeriveEntry)] == ["document", "derived", "declined"]
    assert [f.name for f in fields(DeriveFailure)] == ["document", "reason"]
    assert [f.name for f in fields(DeriveReport)] == [
        "considered",
        "tagged",
        "entries",
        "failures",
        "written",
    ]
