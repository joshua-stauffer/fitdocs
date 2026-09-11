"""The derivation pass: discover, resolve, derive, reconcile, report, write
once (design: PassEngine; Req 1.1-1.10, 6.1-6.8, 7.1-7.9, 9.1-9.7, 10.3).

This module is the *impure* half of the feature: it is the only place in
this package that touches the filesystem. The purity and reachability guards
that govern the rest of `fitdocs.performance` exclude this module by name for
that reason, and the constant guard's scanned tuple does not list it.

Task 4.1 landed the skeleton: discovery in sorted order, one frontmatter read
per document, and the three-way branch over
:func:`fitdocs.contract.effort_tag` -- untagged (skipped, no archive ever
opened, Req 1.3), a well-formed tag, or a malformed tag (recorded as a
:class:`DeriveFailure` rendering the contract's own
:meth:`~fitdocs.contract.InvalidEffortTag.describe`, Req 1.6).

Task 4.2 adds archive resolution, re-parsing and derivation for
the valid-tag arm, plus the remaining failure classes. It resolves a tagged
document's archived source by the *same rule* :func:`fitdocs.load.engine`'s
private `_resolve_archive` uses -- the document's last `sources` ref,
validated through :func:`fitdocs.contract.sha_of_ref` (which refuses a
traversal-shaped ref) and joined through :func:`fitdocs.layout.archive_path`
-- restated here rather than imported (design: PassEngine Implementation
Notes: "duplicating a private helper is rejected"; importing it would drag
the whole load pass's import surface into this one and couple two passes
through a private name). The mitigation the design names is a *shared
behavioural test*, not an import: `tests/performance/test_engine.py` proves
both passes discover the identical document set and resolve one fixture
document -- including a traversal ref -- to the identical answer.

Task 4.3 (this task) adds the collision filter, the single reconciling
write and the per-quantity summary (design: PassEngine, ProfileDerivedWrite;
Req 1.7, 1.8, 6.2, 6.4, 6.5, 7.7, 9.1, 9.4, 9.5). The profile is loaded
exactly once, and deliberately *after* every document has been processed --
not at the top of the run, which is what the mermaid sequence diagram in
design.md § "The pass" sketches, but what the task's own build order and
named mutation ("load_profile before documents are processed") require:
reconciliation reads the *complete* candidate set, so nothing about it can
depend on discovery order or on when, during the loop, a given document
happened to be reached. Each candidate `DerivedBenchmark` is then checked
against `profile.is_recorded(...)`; a hit is turned into a
`SUPERSEDED_BY_RECORDED` decline naming the existing entry's value and date
and the candidate is dropped from `entries[i].derived` -- it can never
shadow a recorded entry (Req 6.2). The whole accepted set is converted to
`Benchmark` values carrying derived `BenchmarkSource` provenance and handed
to `AthleteProfile.with_derived_benchmarks` in one call, persisted through
one `save_profile` call -- but only when the derived subset actually
*changes*: the accepted set is compared against the profile's own
already-recorded derived subset, and the write (and `written=True`) happens
only on a difference, which is what makes a re-run over an unchanged tag set
leave the file's bytes (and mtime) untouched rather than merely
byte-identical after a redundant rewrite (Req 6.5), and what makes removing
a tag actually remove the entry it produced on the next run (Req 6.4) --
including the sole remaining tagged page, where the accepted set becomes
empty: the profile is still untouched only when nothing was previously
derived either, never merely because the fresh accepted set itself is
empty, so a run that empties a previously non-empty derived subset still
writes (Req 6.4).
`dry_run=True` computes the identical reconciliation and report but never
calls `with_derived_benchmarks` or `save_profile` at all, so `written` is
always `False` and nothing under the data root is touched (Req 1.8, 9.4,
9.5). The per-quantity summary (Req 7.7) covers every `BenchmarkKind` the
routing table in :func:`fitdocs.performance.derive.derive` can attempt
(threshold pace, LTHR, FTP): a quantity with zero *final* (post-filter)
derivations anywhere in the run gets a `QuantitySummary` naming the most
frequent decline reason recorded for it across the whole run, ties broken by
the reason's position in `DeclineReason`'s own declared member order --
never by which reason was merely seen first while counting.

The stream-sufficiency settings (`LoadSettings.sufficiency`, Req 9.7) are
now read exactly once per invocation, here, through
:func:`fitdocs.settings.load_settings_document` and
:func:`fitdocs.load.settings.load_load_settings` -- the same single reader
the training-load pass uses. `tests/load/test_settings.py`'s
`test_load_load_settings_is_called_from_exactly_the_licensed_modules`
(originally `..._from_exactly_one_module`) pinned `load/engine.py` as
training-load's *only* caller (training-load Req 14.1); that assertion's
expected caller set is widened, by this task, to name this module as a
sanctioned caller alongside load-history's engine -- the controller ruling
recorded in
`.kiro/specs/performance-benchmarks/tasks.md` § Implementation Notes
`(4.1 -> 4.2)` and in
`.kiro/queue/2026-09-11-performance-pass-sufficiency-read-vs-single-reader-guard.md`
(see that file's `## Resolution` section). The reader is still called from
nowhere else: two *passes*, one *reader*.

Every frontmatter field this module reads comes through
:mod:`fitdocs.contract`'s published readers
(:func:`~fitdocs.contract.is_workout_document`,
:func:`~fitdocs.contract.effort_tag`, :func:`~fitdocs.contract.document_date`,
:func:`~fitdocs.contract.source_refs`, :func:`~fitdocs.contract.sha_of_ref`)
reached from exactly one :func:`fitdocs.docio.read_frontmatter` call per
document (Req 10.3) -- this module defines no second reader of the effort
tag, no second spelling of an effort key, and parses no frontmatter of its
own (Req 10.3): no `yaml` import and no fence-delimiter literal of its own
appear here, and a guard test in this task's own test module pins that.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fitdocs import FitDecodeError, parse_fit
from fitdocs.benchmarks import (
    Benchmark,
    BenchmarkKind,
    BenchmarkSource,
    BenchmarkSourceKind,
)
from fitdocs.contract import (
    EffortTag,
    InvalidEffortTag,
    document_date,
    effort_tag,
    is_workout_document,
    sha_of_ref,
    source_refs,
)
from fitdocs.docio import read_frontmatter
from fitdocs.layout import WORKOUTS_DIR, archive_path, settings_path
from fitdocs.load.profile import AthleteProfile, load_profile, save_profile
from fitdocs.load.settings import load_load_settings
from fitdocs.performance.derive import derive
from fitdocs.performance.types import (
    DeclineReason,
    DerivationDeclined,
    DerivedBenchmark,
)
from fitdocs.settings import load_settings_document

__all__ = [
    "DeriveEntry",
    "DeriveFailure",
    "DeriveReport",
    "QuantitySummary",
    "derive_benchmarks",
]

# The three quantities `fitdocs.performance.derive.derive`'s routing table
# ever attempts (its own docstring's "Routing table" section: `Sport.RUN`
# attempts pace then LTHR, `Sport.RIDE` attempts FTP then LTHR). Restated
# here, not imported, because the router expresses this as control flow, not
# as a published constant -- the summary needs the closed *set*, which is a
# property of this feature's whole scope, not of one routing decision.
_ROUTED_KINDS: tuple[BenchmarkKind, ...] = (
    BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
    BenchmarkKind.LTHR_BPM,
    BenchmarkKind.FTP_WATTS,
)


@dataclass(frozen=True)
class DeriveEntry:
    """One tagged document's outcomes (design: PassEngine Service Interface,
    Req 7.2, 7.3, 7.9). Empty in task 4.1: no derivation runs yet."""

    document: str
    derived: tuple[DerivedBenchmark, ...]
    declined: tuple[DerivationDeclined, ...]


@dataclass(frozen=True)
class DeriveFailure:
    """A document the pass could not process at all: an unresolvable,
    unreadable or undecodable archive, or a malformed tag (Req 1.5, 1.6,
    7.8). An unreadable *page* never reaches here: `read_frontmatter` never
    raises, so such a page is not a workout document and is skipped, exactly
    as the load pass skips it."""

    document: str
    reason: str


@dataclass(frozen=True)
class QuantitySummary:
    """States, for one routed quantity, that the whole run derived nothing
    for it and names why (design: PassEngine Responsibilities & Constraints
    "summary line per quantity with zero derivations"; Req 7.7).

    Only emitted for a quantity whose *final*, post-collision-filter
    `derived` count across the whole run is zero -- a quantity that did
    derive something never gets one, however many declines it also
    accumulated elsewhere in the run (Req 7.7's own example: no cycling file
    carrying power is what earns FTP a summary, not "FTP was declined
    somewhere"). ``dominant_reason`` is the most frequent
    :class:`~fitdocs.performance.types.DeclineReason` recorded for this
    quantity across every document, or `None` when the quantity was never
    even attempted (no decline and no derivation at all -- e.g. an archive
    with no cycling documents whatsoever). Ties are broken by the reason's
    position in `DeclineReason`'s own declared member order, never by which
    reason merely appeared first while counting -- see
    :func:`_dominant_reason`.
    """

    kind: BenchmarkKind
    dominant_reason: DeclineReason | None


@dataclass(frozen=True)
class DeriveReport:
    """The pass's whole output (design: PassEngine Service Interface, Req
    7.1).

    ``summaries`` is task 4.3's addition, appended last with a default so
    every existing positional and keyword construction (including task
    4.1's own shape-pinning test) is unchanged unless it explicitly opts
    in."""

    considered: int
    tagged: int
    entries: tuple[DeriveEntry, ...]
    failures: tuple[DeriveFailure, ...]
    written: bool
    summaries: tuple[QuantitySummary, ...] = ()

    @property
    def derived(self) -> tuple[DerivedBenchmark, ...]:
        """Every derived benchmark across every entry, in entry order."""
        return tuple(outcome for entry in self.entries for outcome in entry.derived)

    @property
    def declined(self) -> tuple[DerivationDeclined, ...]:
        """Every declined derivation across every entry, in entry order."""
        return tuple(outcome for entry in self.entries for outcome in entry.declined)


@dataclass(frozen=True)
class _TaggedDocument:
    """One workout document that carried a well-formed effort tag, holding
    exactly what a page's frontmatter can tell the pass before any archive is
    touched: its data-root-relative path, its parsed tag, and its own
    recorded calendar date (`None` when the page carries none, Req 7.6) --
    never a wall-clock or file-timestamp substitute (Req 9.3).

    Deliberately held nothing task 4.1 could not construct: task 4.2 uses this
    same record, unchanged, to carry `tag`/`on`/`document` into archive
    resolution and the `derive()` call rather than re-deriving any of them --
    the resolved archive and the parsed activity are local values in
    `derive_benchmarks`, not fields added here, because neither survives past
    the single document iteration that produces it.
    """

    document: str
    tag: EffortTag
    on: date | None


def _sorted_workout_paths(data_root: Path) -> list[Path]:
    """Every `*.md` directly under `<data_root>/workouts/`, sorted (Req 9.1).

    Not yet filtered to a fitdocs workout document -- that check needs the
    parsed frontmatter, and this pass reads a document's frontmatter exactly
    once (Req 10.3), so the filter is applied by the caller against the same
    read rather than here against a second one. An absent `workouts/`
    directory yields an empty list, exactly as the training-load pass's own
    discovery does.
    """
    workouts = data_root / WORKOUTS_DIR
    if not workouts.is_dir():
        return []
    return sorted(workouts.glob("*.md"))


def _resolve_pass_archive(
    data_root: Path, frontmatter: dict[str, object]
) -> Path | None:
    """Resolve a tagged document's archived source, or `None` (Req 1.4).

    The *same rule* :func:`fitdocs.load.engine`'s private `_resolve_archive`
    applies -- the document's last `sources` ref (:func:`source_refs`),
    validated by :func:`sha_of_ref` (which refuses a traversal-shaped ref
    such as `fit-archive/../secrets.fit` by returning `None` rather than
    joining it onto the data root), then joined through
    :func:`archive_path`. Restated here rather than imported (module
    docstring); `tests/performance/test_engine.py` proves the two resolvers
    agree, including on a traversal ref, by calling both directly.

    Returns `None` when the history is empty, its last entry is not a
    resolvable archive ref, or the referenced file is missing -- every case
    the caller reports as an "unresolvable archive" failure.
    """
    sources = source_refs(frontmatter)
    if not sources:
        return None
    sha = sha_of_ref(sources[-1])
    if sha is None:
        return None
    archive = archive_path(data_root, sha)
    return archive if archive.is_file() else None


def derive_benchmarks(data_root: Path, *, dry_run: bool = False) -> DeriveReport:
    """Run the benchmark-derivation pass over `data_root` (design: PassEngine
    Service Interface; Req 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.1, 9.1, 9.3, 9.7,
    10.3).

    Task 4.1 implemented discovery, the frontmatter read and the three-way
    tag branch. Task 4.2 adds, for the valid-tag arm only, archive
    resolution, re-parsing, and the call into
    :func:`fitdocs.performance.derive.derive` -- never for an untagged
    document (Req 1.3), and only after the tag branch has already committed
    to "valid tag" (a malformed or absent tag never reaches
    :func:`_resolve_pass_archive`). Task 4.3 (this task) adds the
    collision filter, the single reconciling write and the per-quantity
    summary (module docstring's "Task 4.3" paragraph). The
    stream-sufficiency settings (Req 9.7) are read exactly once here, before
    the document loop, through the same single reader the training-load pass
    uses (module docstring) -- never once per document. The profile,
    conversely, is read exactly once *after* the document loop -- see the
    module docstring's ordering ruling.

    `dry_run=True` runs the identical document loop and reconciliation and
    returns the identical report, but never calls
    :meth:`~fitdocs.load.profile.AthleteProfile.with_derived_benchmarks` or
    :func:`~fitdocs.load.profile.save_profile`, so `written` is always
    `False` and nothing under `data_root` is created, modified or deleted
    (Req 1.8, 9.4, 9.5).
    """
    settings_document = load_settings_document(data_root)
    settings = load_load_settings(settings_document, settings_path(data_root))

    considered = 0
    tagged = 0
    failures: list[DeriveFailure] = []
    entries: list[DeriveEntry] = []

    for path in _sorted_workout_paths(data_root):
        frontmatter = read_frontmatter(path)
        if not is_workout_document(frontmatter):
            continue
        assert frontmatter is not None  # is_workout_document(None) is False
        considered += 1
        rel = path.relative_to(data_root).as_posix()

        tag = effort_tag(frontmatter)
        if tag is None:
            # Untagged: never opens the archive, contributes no outcome of
            # any kind (Req 1.3).
            continue
        if isinstance(tag, InvalidEffortTag):
            failures.append(DeriveFailure(document=rel, reason=tag.describe()))
            continue

        tagged += 1
        on = document_date(frontmatter)
        tagged_doc = _TaggedDocument(document=rel, tag=tag, on=on)

        archive = _resolve_pass_archive(data_root, frontmatter)
        if archive is None:
            failures.append(
                DeriveFailure(
                    document=rel,
                    reason=(
                        f"unresolvable archive for {rel}: the document's "
                        "'sources' history is empty, its last entry is not "
                        "a resolvable archive reference, or the referenced "
                        "file is missing from the archive"
                    ),
                )
            )
            continue

        try:
            activity = parse_fit(archive)
        except OSError as exc:
            failures.append(
                DeriveFailure(
                    document=rel,
                    reason=f"unreadable archive for {rel}: {exc}",
                )
            )
            continue
        except FitDecodeError as exc:
            failures.append(
                DeriveFailure(
                    document=rel,
                    reason=f"undecodable archive for {rel}: {exc}",
                )
            )
            continue

        outcomes = derive(
            activity,
            tagged_doc.tag,
            on=tagged_doc.on,
            document=tagged_doc.document,
            sufficiency=settings.sufficiency,
        )
        entries.append(
            DeriveEntry(
                document=tagged_doc.document,
                derived=tuple(o for o in outcomes if isinstance(o, DerivedBenchmark)),
                declined=tuple(
                    o for o in outcomes if isinstance(o, DerivationDeclined)
                ),
            )
        )

    # Reconciliation runs only now, after every document has been
    # processed and every candidate is known -- never inside the loop above
    # and never before it (module docstring's ordering ruling; the named
    # mutation this guards against is loading the profile before the
    # document loop runs at all).
    profile = load_profile(data_root)

    reconciled_entries: list[DeriveEntry] = []
    accepted: list[Benchmark] = []
    for entry in entries:
        kept_derived: list[DerivedBenchmark] = []
        collision_declines: list[DerivationDeclined] = []
        for candidate in entry.derived:
            existing = _recorded_collision(profile, candidate)
            if existing is not None:
                collision_declines.append(_supersede_decline(candidate, existing))
                continue
            kept_derived.append(candidate)
            accepted.append(_to_benchmark(candidate))
        reconciled_entries.append(
            DeriveEntry(
                document=entry.document,
                derived=tuple(kept_derived),
                declined=(*entry.declined, *collision_declines),
            )
        )
    entries = reconciled_entries

    previous_derived = frozenset(
        candidate
        for candidate in profile.benchmarks.entries
        if candidate.source is not None and candidate.source.is_derived
    )
    written = False
    if frozenset(accepted) != previous_derived and not dry_run:
        save_profile(data_root, profile.with_derived_benchmarks(accepted))
        written = True

    return DeriveReport(
        considered=considered,
        tagged=tagged,
        entries=tuple(entries),
        failures=tuple(failures),
        written=written,
        summaries=_quantity_summaries(entries),
    )


def _recorded_collision(
    profile: AthleteProfile, candidate: DerivedBenchmark
) -> Benchmark | None:
    """The existing recorded (non-derived) entry `candidate` would collide
    with, or `None` (design: PassEngine Responsibilities & Constraints
    "Collision filter"; Req 6.1, 6.2).

    Decides through :meth:`AthleteProfile.is_recorded` -- exactly the
    interface the design names -- then locates the colliding entry itself
    (which `is_recorded` does not return) so the decline can name its value
    and date. A `True` verdict from `is_recorded` with no matching entry
    found would be a contradiction between that method and
    `profile.benchmarks.entries`, not a case this pass can reach.
    """
    if not profile.is_recorded(
        candidate.kind,
        discipline=candidate.discipline,
        measured_on=candidate.measured_on,
    ):
        return None
    key = (candidate.discipline, candidate.kind, candidate.measured_on)
    for recorded in profile.benchmarks.entries:
        if (recorded.discipline, recorded.kind, recorded.measured_on) == key:
            return recorded
    raise AssertionError(  # pragma: no cover - is_recorded contradiction
        f"{candidate.kind.value} at {candidate.measured_on.isoformat()}: "
        "is_recorded() reported a collision but no matching entry exists"
    )


def _supersede_decline(
    candidate: DerivedBenchmark, existing: Benchmark
) -> DerivationDeclined:
    """The decline a collision produces, naming the existing entry's value
    and date (Req 6.2)."""
    return DerivationDeclined(
        kind=candidate.kind,
        method=candidate.method,
        reason=DeclineReason.SUPERSEDED_BY_RECORDED,
        detail=(
            f"a recorded entry already exists for {candidate.kind.value} at "
            f"{existing.measured_on.isoformat()} with value {existing.value:g}; "
            "the derived candidate is dropped rather than shadowing it"
        ),
        observed=candidate.value,
        required=existing.value,
    )


def _to_benchmark(candidate: DerivedBenchmark) -> Benchmark:
    """Map a `DerivedBenchmark` outcome onto the store's `Benchmark` value,
    carrying derived `BenchmarkSource` provenance (design: BenchmarkProvenance;
    Req 5.2, 5.3). Never writes `applies_from` -- a derived entry is dated
    by `measured_on` alone (Amendment 1, item 5)."""
    return Benchmark(
        kind=candidate.kind,
        discipline=candidate.discipline,
        value=candidate.value,
        measured_on=candidate.measured_on,
        note=candidate.note,
        applies_from=None,
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method=candidate.method.value,
            document=candidate.document,
            inputs=candidate.inputs,
            citation=candidate.citation_key,
        ),
    )


def _dominant_reason(reasons: Sequence[DeclineReason]) -> DeclineReason | None:
    """The most frequent reason in `reasons`, or `None` when empty.

    Ties are broken by `DeclineReason`'s own declared member order -- the
    earliest-declared member among the tied reasons wins -- never by which
    reason was merely encountered first while counting. `1x A` followed by
    `2x B` must select `B`: `A` being seen first must not survive into the
    result once `B`'s count overtakes it.
    """
    if not reasons:
        return None
    order = {reason: index for index, reason in enumerate(DeclineReason)}
    counts: dict[DeclineReason, int] = {}
    for reason in reasons:
        counts[reason] = counts.get(reason, 0) + 1
    return max(counts, key=lambda reason: (counts[reason], -order[reason]))


def _quantity_summaries(entries: Sequence[DeriveEntry]) -> tuple[QuantitySummary, ...]:
    """One `QuantitySummary` per routed quantity with zero final derivations
    anywhere in the run (design: PassEngine Responsibilities & Constraints
    "summary line per quantity"; Req 7.7)."""
    derived_kinds = {outcome.kind for entry in entries for outcome in entry.derived}
    summaries: list[QuantitySummary] = []
    for kind in _ROUTED_KINDS:
        if kind in derived_kinds:
            continue
        reasons = [
            outcome.reason
            for entry in entries
            for outcome in entry.declined
            if outcome.kind is kind
        ]
        summaries.append(
            QuantitySummary(kind=kind, dominant_reason=_dominant_reason(reasons))
        )
    return tuple(summaries)
