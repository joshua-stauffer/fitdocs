"""Tests for `fitdocs.performance.engine` (design: PassEngine, Req 1.2, 1.3,
1.4, 1.5, 1.6, 7.1, 7.2, 7.3, 9.3, 9.7, 10.3).

`tests/performance/test_engine.py` is created by task 4.1 with the skeleton
section below; task 4.2 appends the archive-and-failure section and task 4.3
appends the write/reconciliation section. Neither edits the other's
assertions, except the two disclosed edits below.

Task 4.1 covered discovery (sorted, filtered through
`fitdocs.contract.is_workout_document`), the single frontmatter read per
document, and the three-way branch over `fitdocs.contract.effort_tag`
(untagged / valid / malformed). At that task, no archive was resolved and
nothing was written, so `entries` was always empty and `written` was always
`False`.

Task 4.2 lands archive resolution for the valid-tag arm (Req 1.4, 1.5), which
necessarily changes the observable outcome for a *valid-tag* fixture that
carries no resolvable archive: it is no longer silently entry-less, it is a
recorded failure (Req 1.5). Two of task 4.1's own tests used exactly that
shape (a valid tag, no `sources` key) and are updated in place, disclosed
here rather than silently: `test_considers_both_pages_and_tags_only_the_valid_one`
now expects the tagged page as a failure instead of asserting `failures ==
()`, and `test_undated_tagged_page_is_tagged_with_no_failure_and_no_fabricated_date`
now gives its fixture a resolvable archive so archive resolution stays
irrelevant to what that test actually pins (the undated-page invariant). No
other assertion in the task-4.1 section changes. The shared `_write_workout`
helper gains an additive `sources` parameter (default `None`, i.e. task
4.1's original no-archive shape) and a new `_write_archive` helper is added;
neither changes behavior for a call site that does not pass `sources`.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

import fitdocs.load.engine as load_engine
from fitdocs import contract, docio
from fitdocs.layout import ARCHIVE_DIR
from fitdocs.load.channels.types import SufficiencySettings
from fitdocs.performance.engine import DeriveFailure, DeriveReport, derive_benchmarks
from fitdocs.performance.types import DerivationDeclined, DerivedBenchmark
from tests.fixtures import builder

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
    """Write `data` into `<data_root>/fit-archive/<sha256>.fit` and return
    its `sources`-ready ref (Req 1.4) -- the same shape
    `fitdocs.layout.archive_path`/`source_ref` produce in production."""
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

    Neither fixture carries a `sources` key, so task 4.2's archive resolution
    (Req 1.4, 1.5) records the tagged page as one "unresolvable archive"
    failure rather than an entry -- superseding this test's task-4.1-era
    `entries == (), failures == ()` pin, which predated archive resolution
    entirely. `entries` still stays empty either way, which is what task
    4.1's real invariant here -- the untagged page contributes no outcome of
    any kind -- continues to mean.
    """
    _write_workout(tmp_path, "tagged.md", kind="race", distance=10000, time=2400)
    _write_workout(tmp_path, "untagged.md", kind=None)

    report = derive_benchmarks(tmp_path)

    assert report.considered == 2
    assert report.tagged == 1
    assert report.entries == ()
    assert [f.document for f in report.failures] == ["workouts/tagged.md"]
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

    Carries a resolvable `sources` archive (task 4.2, Req 1.4) so the only
    thing this fixture can fail on is the date-parsing question this test is
    actually about -- without one, task 4.2's archive resolution would add
    an unrelated "unresolvable archive" failure that has nothing to do with
    the undated-page invariant this test pins.
    """
    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path,
        "undated.md",
        on="not-a-date",
        kind="race",
        distance=10000,
        time=2400,
        sources=[ref],
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


# --- archive resolution, re-parsing and failure classification (task 4.2) --
#
# Design: PassEngine; Req 1.3, 1.4, 1.5, 1.6. This section owns everything
# from here to the end of the file; the skeleton section above is task 4.1's
# and is not edited here except for the two disclosed, minimal fixes at the
# top of the module docstring and at each affected test (Req 1.4/1.5 making
# an archive-less valid tag a failure rather than a silent no-op).


def test_only_the_tagged_pages_archive_is_ever_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over a data root holding one tagged and one untagged page, only the
    tagged page's archive is ever accessed at all -- resolved, read, or
    opened by any means -- never merely "never passed to `parse_fit`"
    (design: PassEngine Validation; Req 1.3).

    The untagged page's `sources` ref points at real bytes that are not a
    FIT file at all (`builder.non_fit_bytes()`): if the pass ever opened it,
    `parse_fit` would raise `NotFitFileError` and the run would either crash
    or record a spurious failure -- neither of which this test needs to
    detect the violation, because the recorder below observes the *call*
    itself, not merely its absence of a crash.

    Mutation caught: resolving the archive before the tag branch (so the
    untagged page's archive is opened too) makes the recorded archive-access
    set grow to two paths -- a plain crash from the untagged page's
    undecodable bytes would also fail a `parse_fit`-only recorder, but the
    assertion below discriminates independent of that: it also catches a
    resolver that merely `is_file()`s or `read_bytes()`s the untagged page's
    archive without ever reaching `parse_fit` at all (Req 1.3 forbids
    "opened", not only "parsed").

    Every access under `<data_root>/fit-archive/` -- through
    `pathlib.Path.is_file`, `.exists`, `.stat`, `.read_bytes`, `.open`, or
    the builtin `open` -- is recorded, each delegating to the real
    implementation so the run completes normally; the recorded set is
    asserted to be exactly the tagged page's archive. Patching `.exists`
    and `.stat` too (not only `.is_file`) is what makes "opened ... by any
    means" in the claim above actually true: a resolver written against
    `.exists()`/`.stat()` instead of `.is_file()` is caught by the same
    recorder rather than passing unseen.
    """
    tagged_ref = _write_archive(tmp_path, builder.run_fit_bytes())
    untagged_ref = _write_archive(tmp_path, builder.non_fit_bytes())
    _write_workout(
        tmp_path,
        "tagged.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[tagged_ref],
    )
    _write_workout(tmp_path, "untagged.md", kind=None, sources=[untagged_ref])

    archive_dir = tmp_path / ARCHIVE_DIR
    accessed: set[Path] = set()

    def _record(path: Path) -> None:
        try:
            path.relative_to(archive_dir)
        except ValueError:
            return
        accessed.add(path)

    import builtins
    from typing import Any

    real_is_file: Any = Path.is_file
    real_exists: Any = Path.exists
    real_stat: Any = Path.stat
    real_read_bytes: Any = Path.read_bytes
    real_path_open: Any = Path.open
    real_builtin_open: Any = builtins.open

    def recording_is_file(self: Path, *args: Any, **kwargs: Any) -> bool:
        _record(self)
        return bool(real_is_file(self, *args, **kwargs))

    def recording_exists(self: Path, *args: Any, **kwargs: Any) -> bool:
        _record(self)
        return bool(real_exists(self, *args, **kwargs))

    def recording_stat(self: Path, *args: Any, **kwargs: Any) -> Any:
        _record(self)
        return real_stat(self, *args, **kwargs)

    def recording_read_bytes(self: Path) -> bytes:
        _record(self)
        return bytes(real_read_bytes(self))

    def recording_path_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        _record(self)
        return real_path_open(self, *args, **kwargs)

    def recording_builtin_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(file, (str, Path)):
            _record(Path(file))
        return real_builtin_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", recording_is_file)
    monkeypatch.setattr(Path, "exists", recording_exists)
    monkeypatch.setattr(Path, "stat", recording_stat)
    monkeypatch.setattr(Path, "read_bytes", recording_read_bytes)
    monkeypatch.setattr(Path, "open", recording_path_open)
    monkeypatch.setattr("builtins.open", recording_builtin_open)

    report = derive_benchmarks(tmp_path)

    tagged_archive = tmp_path / tagged_ref
    # Falsity in the starting state: before the run nothing has been
    # accessed at all, so a non-empty `accessed` here is entirely produced
    # by this run.
    assert accessed == {tagged_archive}
    assert report.tagged == 1
    assert len(report.entries) == 1


def test_missing_archive_is_a_failure_and_the_pass_continues_to_the_next_document(
    tmp_path: Path,
) -> None:
    """A tagged page whose archive file is missing from the archive becomes
    exactly one failure, and the pass still processes the next document
    (design: PassEngine Validation; Req 1.5).

    Mutation caught: recording the failure but then `break`-ing out of the
    document loop instead of `continue`-ing would leave `b_second.md`
    unprocessed, so `report.entries` would stay empty -- the assertion on
    `entries` is what distinguishes `continue` from `break`, not merely the
    failure count.
    """
    missing_ref = "fit-archive/" + ("0" * 64) + ".fit"  # never written to disk
    real_ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path,
        "a_first.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[missing_ref],
    )
    _write_workout(
        tmp_path,
        "b_second.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[real_ref],
    )

    report = derive_benchmarks(tmp_path)

    assert [f.document for f in report.failures] == ["workouts/a_first.md"]
    assert [e.document for e in report.entries] == ["workouts/b_second.md"]
    entry = report.entries[0]
    assert len(entry.derived) + len(entry.declined) >= 1


def test_traversal_sources_ref_is_refused_by_both_passes_resolvers(
    tmp_path: Path,
) -> None:
    """A traversal-shaped `sources` ref (`fit-archive/../secrets.fit`) is
    refused, not resolved outside the archive directory (design: PassEngine
    Responsibilities & Constraints; Req 1.4).

    `secrets.fit` is written as a *real, decodable* archive one directory
    above `fit-archive/`, and `fit-archive/` itself is created (empty) so the
    traversal path is OS-resolvable to that real file -- POSIX path
    resolution requires every intermediate component, including one a `..`
    later discards, to exist and be traversable; without `fit-archive/`
    present, `<root>/fit-archive/../secrets.fit` fails to stat *regardless*
    of whether the ref is validated, and a resolver that skipped validation
    entirely would still (wrongly) return `None`, hiding the bug. With the
    directory present, a resolver that joined the raw ref onto the data root
    without validating it (bypassing `contract.sha_of_ref`) would
    successfully resolve and derive from it -- this fixture would pass
    silently under that bug. Refusing it is asserted from *both* this pass's
    own resolver and the training-load pass's private `_resolve_archive`
    (the shared-behavioural-test mitigation design.md names for stating this
    rule in two passes), so a divergence between the two rules is caught
    here too.

    Mutation caught: accepting a traversal reference (e.g. skipping the
    `sha_of_ref` validation and joining the raw ref onto the data root)
    resolves a real, existing file -- turning `None` into a `Path` -- so
    this assertion goes red rather than merely "the pass didn't crash".
    """
    traversal_ref = "fit-archive/../secrets.fit"
    (tmp_path / ARCHIVE_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / "secrets.fit").write_bytes(builder.run_fit_bytes())
    path = _write_workout(
        tmp_path,
        "tagged.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[traversal_ref],
    )

    import fitdocs.performance.engine as engine_module

    frontmatter = docio.read_frontmatter(path)
    assert frontmatter is not None
    assert engine_module._resolve_pass_archive(tmp_path, frontmatter) is None
    markdown_text = path.read_text(encoding="utf-8")
    assert load_engine._resolve_archive(tmp_path, markdown_text) is None

    report = derive_benchmarks(tmp_path)
    assert report.entries == ()
    assert len(report.failures) == 1
    assert "unresolvable" in report.failures[0].reason


def test_undecodable_and_unresolvable_failures_are_distinct_and_name_their_document(
    tmp_path: Path,
) -> None:
    """An undecodable archive (real file, not a FIT file) and an
    unresolvable one (missing file) produce two different failure reasons,
    each naming its own document -- not one constant string reused for both
    (design: PassEngine Responsibilities & Constraints; Req 1.5).

    No fixture name below contains a label the assertions check for
    ("undecodable", "unresolvable", "unreadable"): the assertions check the
    reason *text* itself, so a fixture name that happened to embed the
    expected substring could not silently satisfy them by coincidence.

    A hardcoded failure reason (the same literal string for every failure)
    fails `reason_a != reason_c` first, and the `startswith`/`in` checks
    would each fail independently.

    The undecodable document is deliberately placed FIRST in sort order,
    with a resolvable document immediately after it: the pass must continue
    past the undecodable failure rather than stop there, which the trailing
    `entries` assertion pins directly (mutation B3: `continue` -> `break`
    after the undecodable failure).
    """
    notfit_ref = _write_archive(tmp_path, builder.non_fit_bytes())
    resolvable_ref = _write_archive(tmp_path, builder.run_fit_bytes())
    missing_ref = "fit-archive/" + ("1" * 64) + ".fit"
    _write_workout(
        tmp_path,
        "a_notfit.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[notfit_ref],
    )
    _write_workout(
        tmp_path,
        "b_resolves.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[resolvable_ref],
    )
    _write_workout(
        tmp_path,
        "c_missing.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[missing_ref],
    )

    report = derive_benchmarks(tmp_path)

    by_doc = {f.document: f.reason for f in report.failures}
    assert set(by_doc) == {"workouts/a_notfit.md", "workouts/c_missing.md"}
    reason_a = by_doc["workouts/a_notfit.md"]
    reason_c = by_doc["workouts/c_missing.md"]
    assert reason_a != reason_c
    assert reason_a.startswith("undecodable archive for workouts/a_notfit.md")
    assert "unreadable" not in reason_a
    assert "c_missing.md" in reason_c
    assert "unresolvable" in reason_c

    # Falsity in the starting state: a `break` after the undecodable failure
    # would leave this list empty (`b_resolves.md` never reached), so a
    # non-empty, exact match here is only possible under `continue`.
    assert [e.document for e in report.entries] == ["workouts/b_resolves.md"]


def test_unreadable_archive_is_its_own_failure_reason_distinct_from_undecodable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An archive that resolves to a real, existing file but cannot be
    *read* (an `OSError`, e.g. a permission failure) is reported as its own
    failure class, distinct from an archive that reads fine but fails to
    *decode* as FIT (design: PassEngine Responsibilities & Constraints; Req
    1.5).

    `Path.is_file()` reports `True` (the fixture archive genuinely exists),
    so this exercises the read step in isolation from the resolution step --
    a resolver bug could not produce this failure, only a read-error
    classification bug could.

    A second, genuinely readable document follows the unreadable one:
    `parse_fit` is patched to raise only for the first document's archive,
    so the pass must continue past the unreadable failure to reach the
    second document at all -- pinned directly by the trailing `entries`
    assertion (mutation B2: `continue` -> `break` after the unreadable
    failure).
    """
    unreadable_ref = _write_archive(tmp_path, builder.run_fit_bytes())
    readable_ref = _write_archive(tmp_path, builder.ride_fit_bytes())
    _write_workout(
        tmp_path,
        "a_denied.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[unreadable_ref],
    )
    _write_workout(
        tmp_path,
        "b_second.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[readable_ref],
    )

    import fitdocs.performance.engine as engine_module
    from fitdocs import parse_fit as real_parse_fit

    unreadable_path = tmp_path / unreadable_ref

    def selective_raising_parse_fit(source: Path) -> object:
        if source == unreadable_path:
            raise OSError(13, "Permission denied", str(source))
        return real_parse_fit(source)

    monkeypatch.setattr(engine_module, "parse_fit", selective_raising_parse_fit)

    report = derive_benchmarks(tmp_path)

    assert len(report.failures) == 1
    assert report.failures[0].document == "workouts/a_denied.md"
    reason = report.failures[0].reason
    assert reason.startswith("unreadable archive for workouts/a_denied.md")
    assert "undecodable" not in reason

    # Falsity in the starting state: a `break` after the unreadable failure
    # would leave this list empty (`b_second.md` never reached).
    assert [e.document for e in report.entries] == ["workouts/b_second.md"]


def test_the_last_sources_ref_is_resolved_not_the_first(tmp_path: Path) -> None:
    """When a document's `sources` history carries more than one ref, the
    *last* one is resolved -- the current render source -- never the first
    (design: PassEngine Responsibilities & Constraints; Req 1.4).

    The two archives hold genuinely different bytes (`run_fit_bytes()` vs.
    `ride_fit_bytes()`), so their `sources` refs are pairwise-distinct and
    which one was actually opened is directly observable through the
    recorder, not inferred from a report field that both choices could
    satisfy identically.

    Mutation caught: resolving `sources[0]` instead of `sources[-1]` records
    the first (run) archive instead of the second (ride) one.
    """
    first_ref = _write_archive(tmp_path, builder.run_fit_bytes())
    last_ref = _write_archive(tmp_path, builder.ride_fit_bytes())
    assert first_ref != last_ref
    _write_workout(
        tmp_path,
        "tagged.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[first_ref, last_ref],
    )

    import fitdocs.performance.engine as engine_module
    from fitdocs import parse_fit as real_parse_fit

    calls: list[Path] = []

    def recording_parse_fit(source: Path) -> object:
        calls.append(source)
        return real_parse_fit(source)

    monkeypatch_ctx = pytest.MonkeyPatch()
    monkeypatch_ctx.setattr(engine_module, "parse_fit", recording_parse_fit)
    try:
        derive_benchmarks(tmp_path)
    finally:
        monkeypatch_ctx.undo()

    assert calls == [tmp_path / last_ref]


def test_sufficiency_settings_are_read_once_and_threaded_into_derive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[load.sufficiency]` is read exactly once per invocation (never once
    per document) through the training-load reader, and the resulting
    `SufficiencySettings` -- not a hardcoded default -- is threaded into
    every `derive()` call (design: PassEngine Batch Contract; Req 9.7).

    Two tagged documents make "called once" and "called per document"
    observably different (a per-document reader would be called twice, not
    once). The configured value (`min_stream_coverage=0.42`) is not the
    dataclass default, so a call that received `SufficiencySettings()`
    instead of the resolved settings is directly distinguishable by value,
    not merely by identity.
    """
    (tmp_path / "fitdocs.toml").write_text(
        "[load.sufficiency]\nmin_stream_coverage = 0.42\n", encoding="utf-8"
    )
    ref_a = _write_archive(tmp_path, builder.run_fit_bytes())
    ref_b = _write_archive(tmp_path, builder.ride_fit_bytes())
    _write_workout(
        tmp_path, "a.md", kind="race", distance=10000, time=2400, sources=[ref_a]
    )
    _write_workout(
        tmp_path, "b.md", kind="test", distance=10000, time=2400, sources=[ref_b]
    )

    import fitdocs.performance.engine as engine_module
    from fitdocs.load.settings import load_load_settings as real_load_load_settings

    settings_calls: list[object] = []

    def counting_load_load_settings(document: object, settings_file: object) -> object:
        settings_calls.append(document)
        return real_load_load_settings(document, settings_file)  # type: ignore[arg-type]

    from fitdocs.performance.derive import derive as real_derive

    derive_sufficiency_args: list[SufficiencySettings] = []

    def capturing_derive(activity: object, tag: object, **kwargs: object) -> object:
        sufficiency = kwargs["sufficiency"]
        assert isinstance(sufficiency, SufficiencySettings)
        derive_sufficiency_args.append(sufficiency)
        return real_derive(activity, tag, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        engine_module, "load_load_settings", counting_load_load_settings
    )
    monkeypatch.setattr(engine_module, "derive", capturing_derive)

    report = derive_benchmarks(tmp_path)

    assert report.tagged == 2
    assert len(settings_calls) == 1
    assert len(derive_sufficiency_args) == 2
    expected = SufficiencySettings(min_stream_coverage=0.42)
    # Falsity in the starting state: the configured value differs from the
    # dataclass default, so a hardcoded `SufficiencySettings()` would not
    # equal `expected` here.
    assert expected != SufficiencySettings()
    for captured in derive_sufficiency_args:
        assert captured == expected


def test_derive_is_never_reached_for_a_document_with_no_resolvable_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`derive()` is called only for a document whose archive actually
    resolved and re-parsed -- never for one recorded as a failure (design:
    PassEngine Batch Contract invariants; Req 1.5).
    """
    missing_ref = "fit-archive/" + ("2" * 64) + ".fit"
    _write_workout(
        tmp_path,
        "tagged.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=[missing_ref],
    )

    import fitdocs.performance.engine as engine_module

    def failing_derive(*args: object, **kwargs: object) -> object:
        raise AssertionError("derive() must not be reached with no resolvable archive")

    monkeypatch.setattr(engine_module, "derive", failing_derive)

    report = derive_benchmarks(tmp_path)

    assert report.entries == ()
    assert len(report.failures) == 1


def test_each_document_is_parsed_and_derived_from_its_own_activity_not_a_neighbours(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Over two tagged documents, `parse_fit` is called once per document
    against that document's own resolved archive, in document order, and the
    activity object handed to `derive()` for the second document is the
    exact object `parse_fit` returned for the *second* document's archive --
    never the first's (design: PassEngine Batch Contract; Req 1.4).

    The two archives hold genuinely different bytes (`run_fit_bytes()` vs.
    `ride_fit_bytes()`), and `parse_fit` is spied without shortcutting the
    real parse (each call still returns a real, distinct `Activity` object),
    so an implementation that parses only the first document's archive for
    every document is directly observable both in the recorded call list and
    in the identity check -- not merely in some downstream report field both
    a correct and a buggy implementation could satisfy identically.

    Mutation caught: parsing the first resolved archive for every document
    (mutation PA) makes `parse_calls` read `[archive_a, archive_a]` instead
    of `[archive_a, archive_b]`, and the activity passed to `derive()` for
    the second document would be identical to (not merely equal to) the
    first document's activity rather than the second's.
    """
    ref_a = _write_archive(tmp_path, builder.run_fit_bytes())
    ref_b = _write_archive(tmp_path, builder.ride_fit_bytes())
    assert ref_a != ref_b
    _write_workout(
        tmp_path, "a_first.md", kind="race", distance=10000, time=2400, sources=[ref_a]
    )
    _write_workout(
        tmp_path, "b_second.md", kind="race", distance=10000, time=2400, sources=[ref_b]
    )

    import fitdocs.performance.engine as engine_module
    from fitdocs import parse_fit as real_parse_fit
    from fitdocs.performance.derive import derive as real_derive

    parse_calls: list[Path] = []
    parsed_by_path: dict[Path, object] = {}

    def recording_parse_fit(source: Path) -> object:
        parse_calls.append(source)
        activity = real_parse_fit(source)
        parsed_by_path[source] = activity
        return activity

    derive_activities: list[object] = []

    def recording_derive(activity: object, tag: object, **kwargs: object) -> object:
        derive_activities.append(activity)
        return real_derive(activity, tag, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(engine_module, "parse_fit", recording_parse_fit)
    monkeypatch.setattr(engine_module, "derive", recording_derive)

    derive_benchmarks(tmp_path)

    archive_a = tmp_path / ref_a
    archive_b = tmp_path / ref_b
    assert parse_calls == [archive_a, archive_b]
    assert len(derive_activities) == 2
    # Falsity in the starting state: the two parsed activities are distinct
    # objects (different fixture bytes parsed independently), so an identity
    # match below cannot happen by coincidence.
    assert parsed_by_path[archive_a] is not parsed_by_path[archive_b]
    assert derive_activities[0] is parsed_by_path[archive_a]
    assert derive_activities[1] is parsed_by_path[archive_b]


def test_declined_outcomes_reach_the_entry_not_only_derived_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An undated tagged page reaches `derive()`, and every quantity
    `Sport.RUN` attempts for it declines `UNDATED_DOCUMENT` -- the entry
    records these declines rather than silently dropping them (design:
    PassEngine Batch Contract; Req 7.3, 7.9).

    A `derive()` spy captures the real outcome tuple so the entry's
    derived+declined count is checked against what `derive()` itself
    actually produced, not against a number this test assumes -- proving
    the scenario is reached (a spy that never captured anything would mean
    the fixture never got this far) before checking nothing was dropped.

    Mutation caught: hardcoding `declined=()` when building `DeriveEntry`
    (~engine.py:290) would leave `entry.declined` empty even though
    `derive()` genuinely returned two declines, making the entry's
    derived+declined count diverge from the spy's captured outcome count.
    """
    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path,
        "undated.md",
        on="not-a-date",
        kind="race",
        distance=10000,
        time=2400,
        sources=[ref],
    )

    import fitdocs.performance.engine as engine_module
    from fitdocs.performance.derive import derive as real_derive
    from fitdocs.performance.types import DeclineReason

    captured_outcomes: list[tuple[object, ...]] = []

    def capturing_derive(*args: object, **kwargs: object) -> tuple[object, ...]:
        outcomes = real_derive(*args, **kwargs)  # type: ignore[arg-type]
        captured_outcomes.append(outcomes)
        return outcomes

    monkeypatch.setattr(engine_module, "derive", capturing_derive)

    report = derive_benchmarks(tmp_path)

    assert len(report.entries) == 1
    entry = report.entries[0]
    assert len(captured_outcomes) == 1
    # Falsity in the starting state: reachability -- the spy actually
    # captured a non-empty outcome tuple carrying at least one decline,
    # before this test claims the entry preserves it.
    assert len(captured_outcomes[0]) >= 1
    assert any(isinstance(o, DerivationDeclined) for o in captured_outcomes[0])
    assert len(entry.declined) >= 1
    assert all(d.reason is DeclineReason.UNDATED_DOCUMENT for d in entry.declined)
    assert len(entry.derived) + len(entry.declined) == len(captured_outcomes[0])


# --- the shared behavioural test (design: PassEngine Implementation Notes) -


def test_this_pass_and_the_load_pass_discover_the_same_document_set(
    tmp_path: Path,
) -> None:
    """Over one fixture data root, this pass's discovery and the
    training-load pass's `_discover_workout_docs` find the identical
    document set -- the same sorted top-level `*.md` glob under `workouts/`
    behind the same `is_workout_document` filter (design: PassEngine Risks
    mitigation).

    A non-workout file and a nested (non-top-level) file are both included
    in the fixture so the assertion cannot pass merely because both
    resolvers found nothing to disagree on (the vacuous-walk anti-pattern).
    """
    _write_workout(tmp_path, "one.md", kind="race", distance=10000, time=2400)
    _write_workout(tmp_path, "two.md", kind=None)
    _write_non_workout(tmp_path, "not-a-workout.md")
    nested = tmp_path / "workouts" / "sub"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "nested.md").write_text(
        (tmp_path / "workouts" / "one.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    import fitdocs.performance.engine as engine_module

    performance_docs = {
        p.relative_to(tmp_path).as_posix()
        for p in engine_module._sorted_workout_paths(tmp_path)
        if contract.is_workout_document(docio.read_frontmatter(p))
    }
    load_docs = {
        p.relative_to(tmp_path).as_posix()
        for p in load_engine._discover_workout_docs(tmp_path)
    }

    assert performance_docs, "the walk is looking at the wrong directory"
    assert performance_docs == {"workouts/one.md", "workouts/two.md"}
    assert performance_docs == load_docs

    # Drives the equivalence through `derive_benchmarks` itself, not only
    # through the two discovery helpers called directly above -- a pass that
    # drops the `is_workout_document` filter (counting the non-workout page
    # too) would make `considered` diverge from `len(load_docs)` even though
    # the two helper-level sets above still agreed.
    assert derive_benchmarks(tmp_path).considered == len(load_docs)


def test_this_pass_and_the_load_pass_resolve_the_same_archive(tmp_path: Path) -> None:
    """One fixture document is resolved by this pass's `_resolve_pass_archive`
    and by the training-load pass's own `_resolve_archive`, with the two
    results asserted equal -- for a genuinely resolvable ref and, separately,
    for a traversal ref where both must refuse (design: PassEngine Risks
    mitigation).

    The traversal fixture also writes a real, decodable `secrets.fit` one
    directory above `fit-archive/` (which `_write_archive` above already
    created for the resolvable ref) so the traversal path is genuinely
    OS-resolvable to a real file rather than failing to stat regardless of
    whether the ref is validated -- see
    `test_traversal_sources_ref_is_refused_by_both_passes_resolvers` for why
    an absent `fit-archive/` directory would make this assertion pass under a
    resolver that skips validation entirely.
    """
    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    (tmp_path / "secrets.fit").write_bytes(builder.run_fit_bytes())
    resolvable = _write_workout(
        tmp_path, "resolvable.md", kind="race", distance=10000, time=2400, sources=[ref]
    )
    traversal = _write_workout(
        tmp_path,
        "traversal.md",
        kind="race",
        distance=10000,
        time=2400,
        sources=["fit-archive/../secrets.fit"],
    )

    import fitdocs.performance.engine as engine_module

    resolvable_frontmatter = docio.read_frontmatter(resolvable)
    assert resolvable_frontmatter is not None
    performance_answer = engine_module._resolve_pass_archive(
        tmp_path, resolvable_frontmatter
    )
    load_answer = load_engine._resolve_archive(
        tmp_path, resolvable.read_text(encoding="utf-8")
    )
    assert performance_answer is not None
    assert performance_answer == load_answer

    assert (
        engine_module._resolve_pass_archive(
            tmp_path, docio.read_frontmatter(traversal) or {}
        )
        is None
    )
    traversal_text = traversal.read_text(encoding="utf-8")
    assert load_engine._resolve_archive(tmp_path, traversal_text) is None


def test_report_entries_hold_the_typed_outcome_union_members(tmp_path: Path) -> None:
    """Every value inside `DeriveEntry.derived`/`.declined` is a real
    `DerivedBenchmark`/`DerivationDeclined` instance from
    `fitdocs.performance.derive.derive` -- not an ad hoc placeholder (design:
    PassEngine Service Interface).
    """
    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path, "tagged.md", kind="race", distance=10000, time=2400, sources=[ref]
    )

    report = derive_benchmarks(tmp_path)

    assert len(report.entries) == 1
    entry = report.entries[0]
    for outcome in entry.derived:
        assert isinstance(outcome, DerivedBenchmark)
    for declined_outcome in entry.declined:
        assert isinstance(declined_outcome, DerivationDeclined)
    assert len(entry.derived) + len(entry.declined) >= 1


def test_derive_call_is_wired_with_the_tagged_documents_own_tag_date_and_name(
    tmp_path: Path,
) -> None:
    """The `derive()` call inside the pass is wired with *this* document's own
    tag, date and name -- not `None`, not a constant, not another document's
    values (design: PassEngine Batch Contract; Req 1.4).

    Distance and time come through the tag as an official race result
    (`kind="race", distance=10000, time=2400`), so `derive.threshold_pace`
    resolves the "official pair" branch and its `inputs` text names both
    values verbatim (`_threshold_pace_inputs` in `derive.py`) -- proving the
    parsed tag, not merely *some* tag object, reached `derive()`.

    Mutations this pins:
    - `on=None` (dropping the page's date) -> `measured_on` would not equal
      the page's own date.
    - `document=` a constant string -> `.document` would not equal this
      page's own relative path.
    - `derived=()` (discarding derive's output) -> `report.entries[0].derived`
      would be empty, and `entry.derived[0]` would raise.
    - the tag stripped to `distance_m=None, time_s=None` before the call ->
      with the official pair gone, `threshold_pace` falls back to the
      activity's own recorded distance and elapsed time; for this fixture
      (`builder.run_fit_bytes()`) that recorded pair falls outside Riegel's
      validity window, so the outcome DECLINES `OUTSIDE_VALIDITY_WINDOW`
      instead of deriving -- `derived_by_kind` would no longer even contain
      `BenchmarkKind.THRESHOLD_PACE_S_PER_KM`, so the test reds at
      `assert len(entry.derived) >= 1`, before the membership check.
    """
    from fitdocs.benchmarks import BenchmarkKind

    ref = _write_archive(tmp_path, builder.run_fit_bytes())
    _write_workout(
        tmp_path,
        "tagged.md",
        on="2024-05-01",
        kind="race",
        distance=10000,
        time=2400,
        sources=[ref],
    )

    report = derive_benchmarks(tmp_path)

    assert len(report.entries) == 1
    entry = report.entries[0]
    assert len(entry.derived) >= 1
    derived_by_kind = {d.kind: d for d in entry.derived}
    assert BenchmarkKind.THRESHOLD_PACE_S_PER_KM in derived_by_kind
    threshold = derived_by_kind[BenchmarkKind.THRESHOLD_PACE_S_PER_KM]

    assert threshold.measured_on == date(2024, 5, 1)
    assert threshold.document == "workouts/tagged.md"
    # Falsity in the starting state: an activity fixture's own recorded
    # distance/time are not 10000 m / 2400 s, so these substrings appearing
    # in `inputs` can only come from the tag's official values reaching
    # `derive()`, not from the activity's recorded totals.
    assert "10000 m" in threshold.inputs
    assert "2400 s" in threshold.inputs


def test_derive_call_uses_each_documents_own_date_not_a_neighbours(
    tmp_path: Path,
) -> None:
    """Two tagged pages with distinct dates AND distinct tag values each
    produce a derived entry whose `measured_on` and threshold-pace `inputs`
    match its *own* page's values -- ruling out a cross-wired `on` or `tag`
    carried over from the previous document in the loop (design: PassEngine
    Batch Contract; Req 1.4).

    The two pages' tags are pairwise distinct (`a`: 10000 m / 2400 s, `b`:
    5000 m / 1200 s), not merely their dates: a bug that threads the
    *previous* iteration's `tag` into `derive()` while still resetting `on`
    correctly would leave the date assertions green but the `inputs`
    assertions red, so pinning only the date (as this test did before this
    revision) could not have caught a tag-only cross-wire.

    Mutation this pins:
    - threading the previous iteration's `on` (or a single shared variable
      never reset per document) into `derive()` -> at least one entry's
      `measured_on` would equal the *other* page's date instead of its own.
    - threading the previous iteration's `tag` into `derive()` -> document
      `b`'s threshold-pace `inputs` would name `10000 m`/`2400 s` (`a`'s
      values) instead of `5000 m`/`1200 s`.
    - swapping `document=` on the derived benchmark for the previous
      document's name -> `d.document == entry.document` would go false for
      at least one derived benchmark.

    None of this is detectable from a single-document fixture, which is why
    both documents' own values are asserted by name against both entries,
    not merely checked to be present somewhere in the report.
    """
    from fitdocs.benchmarks import BenchmarkKind

    # Both fixtures are running activities: the routing table (`derive`)
    # only ever attempts threshold pace for `Sport.RUN` at all -- a
    # `Sport.RIDE` activity is routed to FTP and LTHR instead and
    # `threshold_pace` is never called for it, so a ride fixture here would
    # make the `THRESHOLD_PACE_S_PER_KM` lookup below fail for reasons
    # unrelated to this test's own cross-wiring question. The ref bytes only
    # need to be file-distinct so the two archives are separate files.
    ref_a = _write_archive(tmp_path, builder.run_fit_bytes())
    ref_b = _write_archive(tmp_path, builder.run_native_power_sparse_hr_fit_bytes())
    _write_workout(
        tmp_path,
        "a_first.md",
        on="2024-05-01",
        kind="race",
        distance=10000,
        time=2400,
        sources=[ref_a],
    )
    _write_workout(
        tmp_path,
        "b_second.md",
        on="2024-08-15",
        kind="race",
        distance=5000,
        time=1200,
        sources=[ref_b],
    )

    report = derive_benchmarks(tmp_path)

    assert len(report.entries) == 2
    by_document = {e.document: e for e in report.entries}
    assert set(by_document) == {"workouts/a_first.md", "workouts/b_second.md"}

    for entry in report.entries:
        for derived in entry.derived:
            assert derived.document == entry.document

    def _threshold(entry_document: str) -> DerivedBenchmark:
        entry = by_document[entry_document]
        derived_by_kind = {d.kind: d for d in entry.derived}
        assert BenchmarkKind.THRESHOLD_PACE_S_PER_KM in derived_by_kind
        return derived_by_kind[BenchmarkKind.THRESHOLD_PACE_S_PER_KM]

    threshold_a = _threshold("workouts/a_first.md")
    threshold_b = _threshold("workouts/b_second.md")

    # Falsity in the starting state: the two page dates, and the two pages'
    # official distance/time pairs, all differ from each other, so each
    # entry matching its own page's values (rather than the other's) is a
    # non-trivial pairwise check.
    assert date(2024, 5, 1) != date(2024, 8, 15)
    assert threshold_a.measured_on == date(2024, 5, 1)
    assert threshold_b.measured_on == date(2024, 8, 15)
    assert "10000 m" in threshold_a.inputs
    assert "2400 s" in threshold_a.inputs
    assert "5000 m" in threshold_b.inputs
    assert "1200 s" in threshold_b.inputs
    assert "10000 m" not in threshold_b.inputs
    assert "2400 s" not in threshold_b.inputs
